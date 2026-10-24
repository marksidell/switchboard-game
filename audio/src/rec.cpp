// rec.cpp - the file side of recording and playback. rec.h has the picture.
// Everything here runs on the MQTT thread, except prepare(), which runs at
// startup.

#include "rec.h"

#include <algorithm>
#include <cerrno>
#include <csignal>
#include <cstring>
#include <ctime>
#include <spawn.h>
#include <sys/stat.h>
#include <dirent.h>
#include <sys/wait.h>
#include <unistd.h>

#include "ipc.h"
#include "util.h"

extern char** environ;

static constexpr size_t XFER = 8192;       // samples per sf_write or sf_read
// Playback keeps this much in play_ring ahead of the audio thread.
static constexpr size_t PLAY_AHEAD = 2 * chan::SAMPLE_RATE;

// The makeup gain of audio.md 10.6: --monitor-limit to -1 dBFS in the file.
static double makeup(const Shared& sh) { return db_to_lin(-1.0 - sh.opt.monitor_limit_db); }

// A recording's name: what start() makes, "YYYY-MM-DD-HH-MM-SS" and perhaps
// "-n" - digits and dashes only, so a name from the wire cannot leave the
// directory.
static bool is_recording_name(const std::string& n)
{
    if (n.size() < 19 || n.size() > 24) return false;
    for (char c : n) if (!(c == '-' || (c >= '0' && c <= '9'))) return false;
    return n[4] == '-' && n[7] == '-' && n[10] == '-' && n[13] == '-' && n[16] == '-';
}

Recorder::~Recorder()
{
    if (snd_) sf_close(snd_);
    if (line_) sf_close(line_);
}

// prepare()                                                          [startup]
//   The ring and the transfer buffer, and the makeup gain: audio.md 10.6 puts
//   the monitor limiter's threshold at -1 dBFS in the file, so a recording is
//   at a usable level whatever --monitor-limit the loudspeaker needs.
void Recorder::prepare()
{
    sh_.rec_ring.allocate();
    if (sh_.opt.record_line) sh_.line_ring.allocate();
    xfer_.assign(XFER, 0.0f);
    sh_.play_ring.allocate();
    gain_ = makeup(sh_);
}

// start()                                                               [mqtt]
std::string Recorder::start()
{
    if (snd_) return name_;

    // The local date and time, all fields joined by '-', so the names sort
    // in order (audio.md 10.6). A second start within the same second gets
    // a suffix rather than overwriting the first.
    char stamp[32];
    const time_t t = time(nullptr);
    struct tm lt;
    localtime_r(&t, &lt);
    strftime(stamp, sizeof stamp, "%Y-%m-%d-%H-%M-%S", &lt);

    std::string base = stamp, path;
    for (int n = 1; ; ++n) {
        if (n > 1) base = std::string(stamp) + "-" + std::to_string(n);
        path = sh_.opt.record_dir + "/" + base + ".wav";
        struct stat st;
        if (stat(path.c_str(), &st) != 0) break;
    }

    SF_INFO info;
    std::memset(&info, 0, sizeof info);
    info.samplerate = chan::SAMPLE_RATE;
    info.channels   = 1;
    info.format     = SF_FORMAT_WAV | SF_FORMAT_PCM_16;
    snd_ = sf_open(path.c_str(), SFM_WRITE, &info);
    if (!snd_) {
        log_line("record: cannot open %s: %s", path.c_str(), sf_strerror(nullptr));
        return "";
    }
    // Clip rather than wrap on the way to 16 bits, and keep the header true
    // after every write, so a crash leaves a WAV that plays to the last chunk.
    sf_command(snd_, SFC_SET_CLIPPING, nullptr, SF_TRUE);
    sf_command(snd_, SFC_SET_UPDATE_HEADER_AUTO, nullptr, SF_TRUE);

    // --record-line (Rev 25): the slot's output and capture beside it, as
    // two-channel float, unscaled. The '.' keeps it out of list().
    if (sh_.opt.record_line) {
        const std::string lp = sh_.opt.record_dir + "/" + base + ".line" +
                               std::to_string(sh_.opt.record_line) + ".wav";
        SF_INFO li;
        std::memset(&li, 0, sizeof li);
        li.samplerate = chan::SAMPLE_RATE;
        li.channels   = 2;
        li.format     = SF_FORMAT_WAV | SF_FORMAT_FLOAT;
        line_ = sf_open(lp.c_str(), SFM_WRITE, &li);
        if (!line_) log_line("record: cannot open %s: %s", lp.c_str(), sf_strerror(nullptr));
        else {
            sf_command(line_, SFC_SET_UPDATE_HEADER_AUTO, nullptr, SF_TRUE);
            log_line("record: slot %d output and capture to %s", sh_.opt.record_line, lp.c_str());
        }
    }

    name_  = base;
    since_ = monotonic_s();
    sh_.rec_ring.discard();
    if (sh_.opt.record_line) sh_.line_ring.discard();
    sh_.rec_on.store(true, std::memory_order_release);
    log_line("record: started %s (makeup %+.1f dB)", path.c_str(), lin_to_db(gain_));
    return name_;
}

// drain()                                                               [mqtt]
//   Everything in the ring into the file, with the makeup gain.
void Recorder::drain()
{
    size_t n;
    while ((n = sh_.rec_ring.read(xfer_.data(), xfer_.size())) > 0) {
        for (size_t i = 0; i < n; ++i) xfer_[i] = (float)(xfer_[i] * gain_);
        if ((size_t)sf_write_float(snd_, xfer_.data(), (sf_count_t)n) != n)
            log_line("record: write to %s.wav failed: %s", name_.c_str(), sf_strerror(snd_));
    }
    if (!sh_.opt.record_line) return;
    while ((n = sh_.line_ring.read(xfer_.data(), xfer_.size() & ~(size_t)1)) > 0) {
        if (line_) sf_writef_float(line_, xfer_.data(), (sf_count_t)(n / 2));
    }
}

// stop()                                                                [mqtt]
void Recorder::stop(bool conv)
{
    if (!snd_) return;
    sh_.rec_on.store(false, std::memory_order_release);
    drain();
    sf_close(snd_);
    if (line_) { sf_close(line_); line_ = nullptr; }
    snd_ = nullptr;
    log_line("record: stopped %s after %.0f s", name_.c_str(), monotonic_s() - since_);
    if (conv) convert(name_);
    else      log_line("record: %s.wav kept, not converted", name_.c_str());
    name_.clear();
}

// convert()                                                             [mqtt]
//   Starts `nice lame` on base.wav, writing base.mp3 beside it, and does not
//   wait: service() reaps it. The WAV is kept (audio.md 10.6).
void Recorder::convert(const std::string& base)
{
    const std::string wav = sh_.opt.record_dir + "/" + base + ".wav";
    const std::string mp3 = sh_.opt.record_dir + "/" + base + ".mp3";
    const char* argv[] = { "nice", "-n", "10", "lame", "--quiet", "-V", "4",
                           wav.c_str(), mp3.c_str(), nullptr };

    // SIGPIPE is ignored in this program, and an ignored signal stays ignored
    // across exec; give the child the default back.
    posix_spawnattr_t attr;
    posix_spawnattr_init(&attr);
    sigset_t def;
    sigemptyset(&def);
    sigaddset(&def, SIGPIPE);
    posix_spawnattr_setsigdefault(&attr, &def);
    posix_spawnattr_setflags(&attr, POSIX_SPAWN_SETSIGDEF);

    pid_t pid;
    const int rc = posix_spawnp(&pid, "nice", nullptr, &attr,
                                const_cast<char* const*>(argv), environ);
    posix_spawnattr_destroy(&attr);
    if (rc != 0) {
        log_line("record: cannot start lame for %s: %s", base.c_str(), std::strerror(rc));
        return;
    }
    lame_.push_back(pid);
    log_line("record: converting %s.wav to mp3 (pid %d)", base.c_str(), (int)pid);
}

// service()                                                             [mqtt]
bool Recorder::service(double now)
{
    for (size_t i = 0; i < lame_.size(); ) {
        int st = 0;
        const pid_t r = waitpid(lame_[i], &st, WNOHANG);
        if (r == 0) { ++i; continue; }
        if (r == lame_[i] && WIFEXITED(st) && WEXITSTATUS(st) == 0)
            log_line("record: mp3 made (pid %d)", (int)lame_[i]);
        else if (r == lame_[i] && WIFEXITED(st) && WEXITSTATUS(st) == 127)
            log_line("record: lame not found (pid %d) - apt install lame; the wav is kept",
                     (int)lame_[i]);
        else
            log_line("record: lame failed (pid %d, status %d); the wav is kept",
                     (int)lame_[i], st);
        lame_.erase(lame_.begin() + (long)i);
    }

    if (!snd_) return false;
    drain();
    if (now - since_ >= sh_.opt.record_max) {
        log_line("record: %s reached --record-max (%.0f s)", name_.c_str(), sh_.opt.record_max);
        stop(true);
        return true;
    }
    return false;
}

// list()                                                                [mqtt]
std::string Recorder::list(int most) const
{
    std::vector<std::string> names;
    if (DIR* d = opendir(sh_.opt.record_dir.c_str())) {
        while (const dirent* e = readdir(d)) {
            const std::string f = e->d_name;
            if (f.size() < 5 || f.compare(f.size() - 4, 4, ".wav") != 0) continue;
            const std::string n = f.substr(0, f.size() - 4);
            if (is_recording_name(n) && n != name_) names.push_back(n);
        }
        closedir(d);
    }
    // The names sort in time order, "-2" after its plain twin.
    std::sort(names.begin(), names.end(), [](const std::string& a, const std::string& b) {
        const int c = a.compare(0, 19, b, 0, 19);
        return c != 0 ? c > 0 : a.size() != b.size() ? a.size() > b.size() : a > b;
    });
    std::string out;
    for (int i = 0; i < (int)names.size() && i < most; ++i) {
        SF_INFO info;
        std::memset(&info, 0, sizeof info);
        const std::string path = sh_.opt.record_dir + "/" + names[(size_t)i] + ".wav";
        SNDFILE* f = sf_open(path.c_str(), SFM_READ, &info);
        const long secs = (f && info.samplerate > 0) ? (long)(info.frames / info.samplerate) : 0;
        if (f) sf_close(f);
        if (!out.empty()) out += '\n';
        out += names[(size_t)i] + " " + std::to_string(secs);
    }
    return out;
}

// ---------------------------------------------------------------- playback

Player::~Player()
{
    if (snd_) sf_close(snd_);
}

// open()                                                                [mqtt]
//   The file, checked as start() made it: 48 kHz mono.
bool Player::open(const std::string& name)
{
    const std::string path = sh_.opt.record_dir + "/" + name + ".wav";
    SF_INFO info;
    std::memset(&info, 0, sizeof info);
    snd_ = sf_open(path.c_str(), SFM_READ, &info);
    if (!snd_) {
        log_line("playback: cannot open %s: %s", path.c_str(), sf_strerror(nullptr));
        return false;
    }
    if (info.samplerate != chan::SAMPLE_RATE || info.channels != 1) {
        log_line("playback: %s is %d Hz, %d channels - not a recording, refused",
                 path.c_str(), info.samplerate, info.channels);
        sf_close(snd_);
        snd_ = nullptr;
        return false;
    }
    xfer_.assign(XFER, 0.0f);
    gain_ = 1.0 / makeup(sh_);
    eof_  = false;
    log_line("playback: %s, %.0f s", path.c_str(), (double)info.frames / info.samplerate);
    return true;
}

// start()                                                               [mqtt]
bool Player::start(const std::string& name)
{
    if (!is_recording_name(name)) {
        log_line("playback: %s is not a recording's name, refused", name.c_str());
        return false;
    }
    stop();
    // Opened now, so a bad name is reported at once, but the samples wait
    // for the next pass: the audio thread has to see play_on clear and
    // discard the last file's tail first (audio.md 10.7).
    if (!open(name)) return false;
    name_    = name;
    pending_ = name;
    return true;
}

// stop()                                                                [mqtt]
void Player::stop()
{
    sh_.play_on.store(false, std::memory_order_release);
    if (snd_) { sf_close(snd_); snd_ = nullptr; }
    if (!name_.empty()) log_line("playback: stopped %s", name_.c_str());
    name_.clear();
    pending_.clear();
}

// fill()                                                                [mqtt]
//   The ring topped up to PLAY_AHEAD from the file, at the monitor's level.
void Player::fill()
{
    while (!eof_ && sh_.play_ring.available() + XFER <= PLAY_AHEAD) {
        const sf_count_t n = sf_read_float(snd_, xfer_.data(), (sf_count_t)XFER);
        if (n <= 0) { eof_ = true; break; }
        for (sf_count_t i = 0; i < n; ++i) xfer_[(size_t)i] = (float)(xfer_[(size_t)i] * gain_);
        sh_.play_ring.write(xfer_.data(), (size_t)n);
    }
}

// service()                                                             [mqtt]
bool Player::service()
{
    if (!snd_) return false;
    if (!pending_.empty()) {
        // The audio thread empties play_ring every period while play_on is
        // clear, so by now - a pass is 20 ms, a period 5.3 - nothing of the
        // last file is left in it.
        // play_on first: while it is clear the audio thread would discard
        // what fill() puts in. Reading an empty ring for a period or two
        // before the first chunk lands is silence, not an underrun.
        pending_.clear();
        sh_.play_on.store(true, std::memory_order_release);
        fill();
        return false;
    }
    fill();
    if (eof_ && sh_.play_ring.available() == 0) {
        log_line("playback: %s finished", name_.c_str());
        sh_.play_on.store(false, std::memory_order_release);
        sf_close(snd_);
        snd_ = nullptr;
        name_.clear();
        return true;
    }
    return false;
}
