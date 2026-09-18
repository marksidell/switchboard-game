#include "wav.h"

#include <sndfile.h>

#include <cmath>
#include <cstring>

#include "dsp.h"
#include "util.h"

const char* load_result_text(LoadResult r)
{
    switch (r) {
    case LoadResult::Ok:         return "ok";
    case LoadResult::BadName:    return "bad name";
    case LoadResult::NotFound:   return "not found";
    case LoadResult::WrongRate:  return "wrong sample rate";
    case LoadResult::NotMono:    return "not mono";
    case LoadResult::TooLong:    return "too long";
    case LoadResult::Unreadable: return "unreadable";
    }
    return "?";
}

// mqtt.md 7: the base name only - no directory, no extension, no separator. A
// payload containing '/' or '..' is rejected rather than sanitised, because a
// game that sends one has a bug and the log should say so.
static bool name_ok(const std::string& b)
{
    if (b.empty() || b.size() > 31)           return false;
    if (b.find('/')  != std::string::npos)    return false;
    if (b.find('\\') != std::string::npos)    return false;
    if (b.find("..") != std::string::npos)    return false;
    for (unsigned char c : b) if (c < 0x20 || c == 0x7f) return false;
    return true;
}

LoadResult load_wav(const std::string& dir, const std::string& base,
                    double max_seconds, AudioBuffer*& out, double& hf_db)
{
    out = nullptr;
    hf_db = -200.0;
    if (!name_ok(base)) return LoadResult::BadName;

    const std::string path = dir + "/" + base + ".wav";

    SF_INFO info;
    std::memset(&info, 0, sizeof info);
    SNDFILE* f = sf_open(path.c_str(), SFM_READ, &info);
    if (!f) return LoadResult::NotFound;

    // Rate and channel count are content errors the program names rather than
    // hides (audio.md 7.2): the game's content is rendered at 48kHz on purpose,
    // and a channel is mono with no right answer to which side of a stereo file
    // to take. 16-bit, 24-bit and float all convert, which is what libsndfile's
    // float reader is for.
    if (info.samplerate != chan::SAMPLE_RATE) { sf_close(f); return LoadResult::WrongRate; }
    if (info.channels   != 1)                 { sf_close(f); return LoadResult::NotMono; }
    if ((double)info.frames > max_seconds * chan::SAMPLE_RATE) {
        sf_close(f);
        log_line("file %s: %.1fs exceeds --max-file %.0fs", path.c_str(),
                 (double)info.frames / chan::SAMPLE_RATE, max_seconds);
        return LoadResult::TooLong;
    }

    AudioBuffer* b = new AudioBuffer();
    b->samples.resize((size_t)info.frames);
    std::snprintf(b->name, sizeof b->name, "%s", base.c_str());

    const sf_count_t got = info.frames
        ? sf_readf_float(f, b->samples.data(), info.frames) : 0;
    sf_close(f);
    if (got != info.frames) { delete b; return LoadResult::Unreadable; }

    // audio.md 5.3: programme energy above 5.5kHz within 20dB of the pilots
    // returns on this circuit's own receive channel at full strength and can
    // cross the detector's threshold in a neighbouring bin. Authored speech is
    // band-limited offline and has nothing there; a file that was not authored
    // that way is warned about, not refused and not filtered - the cost of a
    // filter in the audio thread is paid on every period forever to fix a
    // content error that is fixed once offline.
    //
    // Measured with a fourth-order high-pass rather than a transform: the
    // question is only whether there is anything up there at all.
    const Biquad hp = butter_highpass(5500.0, chan::SAMPLE_RATE);
    BiquadState s1, s2;
    double acc = 0.0;
    for (float v : b->samples) {
        const double y = s2.run(hp, s1.run(hp, (double)v));
        acc += y * y;
    }
    if (!b->samples.empty()) {
        // Referenced to a full-scale sine, the convention docs/audio-io.md uses.
        const double rms = std::sqrt(acc / (double)b->samples.size());
        hf_db = lin_to_db(rms * M_SQRT2);
    }

    out = b;
    return LoadResult::Ok;
}
