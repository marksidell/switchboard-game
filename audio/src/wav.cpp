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

// hf_filter()                                                            [mqtt]
//   The content check's high-pass, designed on the first load and kept.
//
//   It has to be steep: the top of the telephone band is only 2kHz below the
//   corner, and a gentle filter there measures the voice - a bright one reads
//   25dB above a dull one - rather than whether the file has anything above
//   5.5kHz. An elliptic high-pass 80dB down at 4kHz and flat from 5.5kHz
//   makes the reading a property of the file.
static const std::vector<Biquad>& hf_filter()
{
    static const std::vector<Biquad> hp = [] {
        double ripple_db = 0.0;
        return elliptic_highpass(8, 5500.0, 4000.0, 80.0, chan::SAMPLE_RATE, ripple_db);
    }();
    return hp;
}

// load_wav()                                                             [mqtt]
//   See wav.h. In order: check the name, open with libsndfile (which reads the
//   header), refuse on rate / channels / length before reading any audio,
//   read every sample as float, then measure the high-frequency content.
LoadResult load_wav(const std::string& dir, const std::string& base,
                    double max_seconds, std::unique_ptr<AudioBuffer>& out, double& hf_db)
{
    out.reset();
    hf_db = -200.0;
    if (!name_ok(base)) return LoadResult::BadName;

    const std::string path = dir + "/" + base + ".wav";

    SF_INFO info;
    std::memset(&info, 0, sizeof info);
    SNDFILE* f = sf_open(path.c_str(), SFM_READ, &info);
    if (!f) return LoadResult::NotFound;

    // Rate and channel count are content errors the program names rather than
    // hides (audio.md 7.2): there is no right answer to which side of a stereo
    // file to take. 16-bit, 24-bit and float all convert, which is what
    // libsndfile's float reader is for.
    if (info.samplerate != chan::SAMPLE_RATE) { sf_close(f); return LoadResult::WrongRate; }
    if (info.channels   != 1)                 { sf_close(f); return LoadResult::NotMono; }
    if ((double)info.frames > max_seconds * chan::SAMPLE_RATE) {
        sf_close(f);
        log_line("file %s: %.1fs exceeds --max-file %.0fs", path.c_str(),
                 (double)info.frames / chan::SAMPLE_RATE, max_seconds);
        return LoadResult::TooLong;
    }

    auto b = std::make_unique<AudioBuffer>();
    b->samples.resize((size_t)info.frames);
    std::snprintf(b->name, sizeof b->name, "%s", base.c_str());

    const sf_count_t got = info.frames
        ? sf_readf_float(f, b->samples.data(), info.frames) : 0;
    sf_close(f);
    if (got != info.frames) return LoadResult::Unreadable;

    // audio.md 5.3: programme energy above 5.5kHz within 20dB of the pilots
    // returns on the circuit's own receive and can cross the detector's
    // threshold in a neighbouring bin. Warned about, not refused and not
    // filtered: a filter in the audio thread would be paid for every period
    // to fix a content error that is fixed once offline. A filter rather than
    // a transform, because the question is only whether anything is there.
    const std::vector<Biquad>& hp = hf_filter();
    if (hp.empty()) return LoadResult::Unreadable;

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

    out = std::move(b);
    return LoadResult::Ok;
}
