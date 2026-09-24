// wav.cpp - loading and validating a prompt file. See wav.h.

#include "wav.h"

#include <sndfile.h>

#include <cmath>
#include <cstring>

#include "dsp.h"
#include "util.h"

// load_result_text()                                                     [mqtt]
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
// name_ok()                                                              [mqtt]
//   True if `b` is acceptable as a base filename.
static bool name_ok(const std::string& b)
{
    if (b.empty() || b.size() > 31)           return false;
    if (b.find('/')  != std::string::npos)    return false;
    if (b.find('\\') != std::string::npos)    return false;
    if (b.find("..") != std::string::npos)    return false;
    for (unsigned char c : b) if (c < 0x20 || c == 0x7f) return false;
    return true;
}

// load_wav()                                                             [mqtt]
//   See wav.h. In order: check the name, open with libsndfile (which reads the
//   header), refuse on rate / channels / length before reading any audio,
//   read every sample as float, then measure the high-frequency content.
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
    // Measured with a filter rather than a transform: the question is only
    // whether there is anything up there at all, and a filter answers it in
    // one pass with no buffer.
    //
    // The filter has to be a steep one, which the first version was not. Two
    // cascaded Butterworth biquads at 5.5kHz are only 18.7dB down at 3400Hz at
    // this sample rate, so they measure the top of the telephone band - the
    // wanted signal - almost as loudly as what is above the corner. On
    // correctly band-limited speech that read -71.6dBFS for a dull voice and
    // -45.7dBFS for a bright one against a -60dBFS threshold: a 25.9dB spread
    // that tracked the voice rather than the file, and tripped 46 of the 71
    // delivered lines while a transform put them all near -146dBFS. An
    // elliptic high-pass, 80dB down at 4kHz and flat from 5.5kHz, reads those
    // same two files 0.9dB apart. The reading is then a property of the file,
    // which is what the threshold is for.
    static const int    HF_ORDER   = 8;
    static const double HF_PASS_HZ = 5500.0;      // audio.md 5.3's corner
    static const double HF_STOP_HZ = 4000.0;      // above the telephone band
    static const double HF_STOP_DB = 80.0;
    double ripple_db = 0.0;
    const std::vector<Biquad> hp = elliptic_highpass(HF_ORDER, HF_PASS_HZ, HF_STOP_HZ,
                                                     HF_STOP_DB, chan::SAMPLE_RATE,
                                                     ripple_db);
    if (hp.empty()) { delete b; return LoadResult::Unreadable; }

    std::vector<BiquadState> st(hp.size());
    double acc = 0.0;
    for (float v : b->samples) {
        double y = (double)v;
        for (size_t i = 0; i < hp.size(); ++i) y = st[i].run(hp[i], y);
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
