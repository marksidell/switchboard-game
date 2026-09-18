#include "engine.h"

#include <algorithm>
#include <cstring>

#include "util.h"

using chan::FFT_N;
using chan::FFT_HOP;
using chan::SAMPLE_RATE;

// audio.md 8.2. The Bell System tones of the period the 551 belongs to, before
// the precise tone plan replaced them with two-frequency sums. Busy is the
// dial-tone waveform interrupted at 60 IPM, which is how the period offices
// made it - one tone source, one interrupter - and a listener tells the two
// apart by the cadence alone.
struct ToneSpec {
    double carrier_hz, mod_hz;
    unsigned on_samples, period_samples;   // period 0 = continuous
};

static const ToneSpec TONES[] = {
    { 0.0,   0.0,   0,                  0 },                  // Off
    { 600.0, 120.0, 0,                  0 },                  // Dial, continuous
    { 420.0,  40.0, 2 * SAMPLE_RATE,    6 * SAMPLE_RATE },    // Ringback 2s/4s
    { 600.0, 120.0, SAMPLE_RATE / 2,    SAMPLE_RATE }         // Busy 0.5s/0.5s
};

static const char* TONE_NAME[] = { "", "dial", "ringback", "busy" };

// Speech detection runs on 10ms frames (audio.md 9.2).
static const int VAD_FRAME  = SAMPLE_RATE / 100;    // 480 samples
static const int VAD_WIN    = 30;                   // frames in the decision window
static const int VAD_NEEDED = 20;                   // of which this many above threshold

bool Engine::prepare()
{
    period_ = st_.period();
    nplay_  = st_.nplay();
    ncap_   = st_.ncap();

    ibuf_.assign((size_t)period_ * ncap_,  0);
    obuf_.assign((size_t)period_ * nplay_, 0);
    capf_.assign((size_t)period_ * ncap_,  0.0f);
    ring_.assign((size_t)chan::N_CAP_CH * FFT_N, 0.0f);
    test_row_.assign(period_, 0.0f);
    mon_row_.assign(period_, 0.0f);

    for (int i = 0; i < 2; ++i) {
        sh_.snap[i].data.assign((size_t)chan::N_CAP_CH * FFT_N, 0.0f);
        sh_.snap[i].hop = 0;
    }

    pilot_amp_ = (float)db_to_lin(sh_.opt.pilot_db);
    op_amp_    = (float)db_to_lin(sh_.opt.op_db);
    tone_amp_  = (float)db_to_lin(sh_.opt.tone_db);
    test_amp_  = (float)db_to_lin(sh_.opt.test_db);
    tone_mod_  = sh_.opt.tone_mod;
    test_inc_  = SineTable::inc_q32(1000.0, SAMPLE_RATE);

    // Speech detector band-pass: the pilots at 6-9kHz are the loudest thing on
    // the channel and must not count; hum must not either (audio.md 9.2). Two
    // second-order sections is what that section specifies, and they leave the
    // lowest pilot only 10.9dB down - so the pilot residual is part of the
    // noise floor the detector measures, and it is the ratiometric floor +
    // --vad-margin term that keeps it from counting as speech. The absolute
    // --vad-floor is a lower bound for a dead-quiet channel and nothing more.
    const Biquad vhp = butter_highpass(300.0,  SAMPLE_RATE);
    const Biquad vlp = butter_lowpass (3400.0, SAMPLE_RATE);
    vad_hp_ = vhp;
    vad_lp_ = vlp;

    // Monitor chain, station 8.8 through audio.md 10.1.
    mon_hp_ = butter_highpass(150.0, SAMPLE_RATE);
    mon_lp_ = elliptic_lowpass(8, sh_.opt.lp_pass, sh_.opt.lp_stop,
                               sh_.opt.lp_att, SAMPLE_RATE, mon_ripple_db_);
    if (mon_lp_.empty()) { log_line("monitor: low-pass design failed"); return false; }
    mon_lp_s_.assign(mon_lp_.size(), BiquadState());
    lim_.init(-3.0, 0.100, SAMPLE_RATE);

    const double at_6k = cascade_mag_db(mon_lp_, 6000.0, SAMPLE_RATE);
    log_line("monitor: elliptic low-pass order 8, pass %.0f Hz, stop %.0f Hz, "
             "%.1f dB; ripple %.4f dB, %.1f dB at 6000 Hz",
             sh_.opt.lp_pass, sh_.opt.lp_stop, sh_.opt.lp_att,
             mon_ripple_db_, at_6k);
    if (at_6k > -sh_.opt.lp_att)
        log_line("monitor: WARNING the lowest pilot at 6000 Hz is only %.1f dB "
                 "down; station 8.8 asks for %.0f", -at_6k, sh_.opt.lp_att);

    // audio.md 10.2: the monitor is on at startup only if --monitor gives a
    // level. Started at its target rather than ramped to it - there is no
    // loudspeaker transient to avoid before the stream is running.
    mon_target_ = sh_.opt.monitor_on ? db_to_lin(sh_.opt.monitor_db) : 0.0;
    mon_gain_   = mon_target_;

    log_line("levels: pilot %.1f dBFS, operator tone %.1f dBFS, trunk tone "
             "%.1f dBFS peak (mod %.2f), test tone %.1f dBFS",
             sh_.opt.pilot_db, sh_.opt.op_db, sh_.opt.tone_db,
             sh_.opt.tone_mod, sh_.opt.test_db);
    return true;
}

// ---------------------------------------------------------------- results

void Engine::post(Topic t, int idx, const char* value)
{
    Result r;
    r.topic = t;
    r.idx   = (int16_t)idx;
    std::snprintf(r.value, sizeof r.value, "%s", value ? value : "");
    // Nothing to be done from here - no logging in this thread. The MQTT thread
    // drains continuously even while disconnected, so a full queue means it is
    // wedged, and the count is what says so.
    if (!sh_.res_audio.push(r)) sh_.res_dropped.fetch_add(1, std::memory_order_relaxed);
}

void Engine::post_free(AudioBuffer* b)
{
    if (!b) return;
    Result r;
    r.topic = Topic::FreeBuf;
    r.buf   = b;
    if (!sh_.res_audio.push(r)) sh_.res_dropped.fetch_add(1, std::memory_order_relaxed);
}

// ---------------------------------------------------------------- commands

void Engine::stop_source(int slot, const char* echo)
{
    Prog& p = prog_[slot];
    if (p.kind == Prog::Kind::File) {
        post_free(p.buf);
        p.buf = nullptr;
        if (echo) post(Topic::Play, slot, echo);
    } else if (p.kind == Prog::Kind::Tone) {
        if (echo) post(Topic::Tone, slot, echo);
    }
    p.kind = Prog::Kind::None;
    p.pos  = 0;
    p.tone = ToneKind::Off;
}

void Engine::start_listen(int slot, double seconds)
{
    Vad& v = vad_[slot];
    v.active = true;
    v.left   = (uint64_t)(seconds * SAMPLE_RATE);
    v.win    = 0;
    v.win_n  = 0;

    // The floor is the 10th percentile of the frame levels over the second
    // before the command arrived, which is why the history runs at all times.
    float tmp[100];
    const int n = v.hist_n;
    if (n > 0) {
        std::memcpy(tmp, v.hist, (size_t)n * sizeof(float));
        const int k = n / 10;
        std::nth_element(tmp, tmp + k, tmp + n);
        v.floor_db = tmp[k];
    } else {
        v.floor_db = -120.0;
    }
    post(Topic::Listen, slot, "listening");
}

void Engine::cancel_listen(int slot, const char* echo)
{
    vad_[slot].active = false;
    if (echo) post(Topic::Listen, slot, echo);
}

void Engine::drain_commands()
{
    Command c;
    while (sh_.cmdq.pop(c)) {
        switch (c.verb) {
        case Verb::Play: {
            const int slot = c.idx;
            // A play/set always replaces: a tone stops, a file is displaced,
            // and a load failure stops what was there and echoes "missing" -
            // otherwise `play` would read "missing" while a file kept playing.
            const bool was_tone = prog_[slot].kind == Prog::Kind::Tone;
            stop_source(slot, nullptr);
            if (c.buf) {
                prog_[slot].kind = Prog::Kind::File;
                prog_[slot].buf  = c.buf;
                prog_[slot].pos  = 0;
            }
            post(Topic::Play, slot, c.name);   // "" for stop, "missing" for a bad load
            if (was_tone) post(Topic::Tone, slot, "");
            break;
        }

        case Verb::Tone: {
            const int slot = c.idx;
            const ToneKind k = (ToneKind)(int)c.arg;
            const bool was_file = prog_[slot].kind == Prog::Kind::File;
            stop_source(slot, nullptr);
            if (was_file) post(Topic::Play, slot, "");
            if (k == ToneKind::Off) {
                post(Topic::Tone, slot, "");
            } else {
                Prog& p = prog_[slot];
                p.kind = Prog::Kind::Tone;
                p.tone = k;
                // The cadence starts at the beginning of the on period when the
                // tone is commanded, so the operator always hears a burst first.
                p.ph = p.mph = p.cad = 0;
                post(Topic::Tone, slot, TONE_NAME[(int)k]);
            }
            break;
        }

        case Verb::Listen:
            if (c.arg <= 0.0f) cancel_listen(c.idx, "");
            else               start_listen(c.idx, c.arg);
            break;

        case Verb::Monitor: {
            const double t = c.on ? db_to_lin(c.arg) : 0.0;
            // 20ms ramp so a level step does not click; "off" is a mute, ramped
            // the same way, and the filter keeps running so turning the monitor
            // on is instant and has no transient from a cold filter state.
            mon_target_ = t;
            mon_ramp_   = (int)(0.020 * SAMPLE_RATE);
            mon_step_   = (mon_target_ - mon_gain_) / (double)mon_ramp_;
            char buf[32];
            if (c.on) format_db(c.arg, buf, sizeof buf);
            else      std::snprintf(buf, sizeof buf, "off");
            post(Topic::Monitor, 0, buf);
            break;
        }

        case Verb::Test:
            if (c.idx >= 1 && c.idx <= (int)chan::N_PLAY_CH) {
                test_on_[c.idx] = c.on;
                post(Topic::Test, c.idx, c.on ? "on" : "off");
            }
            break;

        case Verb::StopGame:
            // audio.md 13.2. Pilots, the operator tone and the monitor continue
            // - they are not things the game started and are harmless without
            // it. Test tones continue: they are a bench diagnostic, not game
            // state, and stopping them under someone's meter is unhelpful.
            for (int s = 1; s <= chan::N_SLOTS; ++s) {
                if (!chan::is_circuit_slot(s)) continue;
                if (prog_[s].kind != Prog::Kind::None) stop_source(s, "");
                if (vad_[s].active) cancel_listen(s, "");
            }
            break;

        case Verb::Quit:
            sh_.running.store(false);
            break;
        }
    }
}

// ---------------------------------------------------------------- capture

void Engine::process_capture()
{
    const int ncirc = (int)std::min<unsigned>(ncap_, chan::N_CAP_CH);

    for (int c = 0; c < ncirc; ++c) {
        const float* src = &capf_[(size_t)c * period_];
        float*       rg  = &ring_[(size_t)c * FFT_N];

        // Append to this channel's 4096-sample ring. The oldest sample is
        // always the one at the write index, so the hop can linearise the
        // window from wherever it happens to fall - no alignment needed.
        size_t w = ring_w_;
        for (unsigned i = 0; i < period_; ++i) {
            rg[w] = src[i];
            w = (w + 1) & (FFT_N - 1);
        }

        const int slot = c + 1;
        if (!chan::is_circuit_slot(slot)) continue;

        // Speech detection front end, run for every circuit at all times so the
        // noise floor is available the instant a listen starts.
        Vad& v = vad_[slot];
        const bool src_active = prog_[slot].kind != Prog::Kind::None;
        if (src_active) v.src_seen = true;

        for (unsigned i = 0; i < period_; ++i) {
            const double y = v.lp.run(vad_lp_, v.hp.run(vad_hp_, (double)src[i]));
            v.acc += y * y;
            if (++v.nacc < VAD_FRAME) continue;

            const double rms = std::sqrt(v.acc / (double)VAD_FRAME);
            const float  db  = (float)lin_to_db(rms * M_SQRT2);
            v.acc  = 0.0;
            v.nacc = 0;

            const bool valid = !v.src_seen;
            v.src_seen = false;

            // audio.md 9.3: the two-wire interface has no hybrid, so everything
            // this channel transmits returns on its own receive at full
            // strength. Frames with a source running are discarded and the
            // window restarts, which also covers the few milliseconds of echo
            // that persist after the source stops. Such a frame is kept out of
            // the floor history too, or the floor would follow our own file up.
            if (!valid) { v.win = 0; v.win_n = 0; continue; }

            v.hist[v.hist_w] = db;
            v.hist_w = (v.hist_w + 1) % 100;
            if (v.hist_n < 100) ++v.hist_n;

            if (!v.active) continue;

            // The floor may rise at no more than 1dB/s and never fall, so a
            // slowly rising room does not trigger and a burst does not lower
            // the bar.
            float tmp[100];
            std::memcpy(tmp, v.hist, (size_t)v.hist_n * sizeof(float));
            const int k = v.hist_n / 10;
            std::nth_element(tmp, tmp + k, tmp + v.hist_n);
            const double cand = tmp[k];
            if (cand > v.floor_db) v.floor_db = std::min(cand, v.floor_db + 0.01);

            const double thr = std::max(v.floor_db + sh_.opt.vad_margin,
                                        sh_.opt.vad_floor);
            v.win = ((v.win << 1) | (db >= thr ? 1u : 0u)) & ((1u << VAD_WIN) - 1u);
            if (v.win_n < VAD_WIN) ++v.win_n;

            if (v.win_n >= VAD_WIN && __builtin_popcount(v.win) >= VAD_NEEDED) {
                v.active = false;
                post(Topic::Listen, slot, "speech");
            }
        }

        if (v.active) {
            if (v.left <= period_) { v.active = false; post(Topic::Listen, slot, "timeout"); }
            else                   { v.left -= period_; }
        }
    }

    // Monitor: the tap's receive channel through the chain of audio.md 10.1.
    // Run unconditionally, muted or not, so that turning the monitor on is
    // instant and has no transient from a cold filter state.
    if (ncap_ >= chan::TAP_SLOT) {
        const float* tap = &capf_[(size_t)(chan::TAP_SLOT - 1) * period_];
        for (unsigned i = 0; i < period_; ++i) {
            double y = mon_hp_s_.run(mon_hp_, (double)tap[i]);
            for (size_t s = 0; s < mon_lp_.size(); ++s) y = mon_lp_s_[s].run(mon_lp_[s], y);
            if (mon_ramp_ > 0) { mon_gain_ += mon_step_; --mon_ramp_; }
            else               { mon_gain_ = mon_target_; }
            mon_row_[i] = (float)lim_.run(y * mon_gain_);
        }
    } else {
        std::fill(mon_row_.begin(), mon_row_.end(), 0.0f);
    }

    ring_w_ = (ring_w_ + period_) & (FFT_N - 1);
    since_hop_ += period_;
    hop_if_due();
}

void Engine::hop_if_due()
{
    if (since_hop_ < FFT_HOP) return;
    since_hop_ -= FFT_HOP;

    const int w = snap_next_;
    if (sh_.snap_busy[w].load(std::memory_order_acquire)) {
        // The analysis thread is still on the buffer this hop would overwrite.
        // Drop the hop rather than corrupt it; a dropped hop costs 43ms of
        // detector latency and nothing else.
        sh_.hops_lost.fetch_add(1, std::memory_order_relaxed);
        return;
    }

    float* dst = sh_.snap[w].data.data();
    for (int c = 0; c < chan::N_CAP_CH; ++c) {
        const float* rg = &ring_[(size_t)c * FFT_N];
        float*       d  = dst + (size_t)c * FFT_N;
        const size_t a  = FFT_N - ring_w_;          // oldest run, from ring_w_
        std::memcpy(d,     rg + ring_w_, a * sizeof(float));
        std::memcpy(d + a, rg,           ring_w_ * sizeof(float));
    }
    sh_.snap[w].hop = ++hop_;
    sh_.snap_ready.store(w, std::memory_order_release);
    snap_next_ ^= 1;
}

// ---------------------------------------------------------------- render

void Engine::render()
{
    // One shared 1kHz row: every channel under test carries the same tone, so
    // it is generated once (audio.md 11.1).
    for (unsigned i = 0; i < period_; ++i) {
        test_row_[i] = test_amp_ * tbl_.at_q32(test_ph_);
        test_ph_ += test_inc_;
    }

    const int nout = (int)std::min<unsigned>(nplay_, chan::N_PLAY_CH);

    for (int ch = 1; ch <= nout; ++ch) {
        int32_t* out = obuf_.data() + (ch - 1);
        const size_t stride = nplay_;

        // The test tone replaces everything on its channel - the programme
        // source, and also the pilot, the operator tone or the monitor - so a
        // scope at the far end sees one clean tone at a known level. The
        // circuit therefore reports `deaf` while it is on, which is correct and
        // not a fault (audio.md 11.1).
        if (test_on_[ch]) {
            for (unsigned i = 0; i < period_; ++i)
                out[i * stride] = float_to_s32(test_row_[i]);
            continue;
        }

        if (ch == chan::MON_CH_A || ch == chan::MON_CH_B) {
            for (unsigned i = 0; i < period_; ++i)
                out[i * stride] = float_to_s32(mon_row_[i]);
            continue;
        }

        const int slot = ch;

        // The fixed source: the operator tone on the tap, a comb pilot on every
        // other circuit. Neither is a programme source and neither is ever
        // displaced by one. table[(b * n) & 4095] is the whole oscillator.
        const uint32_t b   = (slot == chan::TAP_SLOT)
                             ? (uint32_t)chan::OP_BIN : (uint32_t)chan::pilot_bin(slot);
        const float    amp = (slot == chan::TAP_SLOT) ? op_amp_ : pilot_amp_;

        uint32_t n = pilot_n_;
        for (unsigned i = 0; i < period_; ++i) {
            out[i * stride] = float_to_s32(amp * tbl_.at(b * n));
            n = (n + 1) & (FFT_N - 1);
        }

        Prog& p = prog_[slot];
        if (p.kind == Prog::Kind::None || slot == chan::TAP_SLOT) continue;

        // Sum the programme source over the fixed one, in float, hard-clipped
        // at +-1.0 with a clip count in the log (audio.md 5.1).
        if (p.kind == Prog::Kind::File) {
            const size_t have = p.buf->samples.size() - p.pos;
            const unsigned n_s = (unsigned)std::min<size_t>(have, period_);
            const float* s = p.buf->samples.data() + p.pos;
            n = pilot_n_;
            for (unsigned i = 0; i < n_s; ++i) {
                float v = amp * tbl_.at(b * n) + s[i];
                if (v > 1.0f)  { v =  1.0f; ++clips_; }
                if (v < -1.0f) { v = -1.0f; ++clips_; }
                out[i * stride] = float_to_s32(v);
                n = (n + 1) & (FFT_N - 1);
            }
            p.pos += n_s;
            if (p.pos >= p.buf->samples.size()) {
                // The `play` topic clears to empty from the period after the
                // file ends. That clearing is the "finished" response
                // (audio.md 7.4) - there is no event topic.
                stop_source(slot, "");
            }
        } else {
            const ToneSpec& t = TONES[(int)p.tone];
            const uint32_t inc  = SineTable::inc_q32(t.carrier_hz, SAMPLE_RATE);
            const uint32_t minc = SineTable::inc_q32(t.mod_hz,     SAMPLE_RATE);
            const float    g    = (float)(tone_amp_ / (1.0 + tone_mod_));
            n = pilot_n_;
            for (unsigned i = 0; i < period_; ++i) {
                const bool on = (t.period_samples == 0) || (p.cad < t.on_samples);
                float v = amp * tbl_.at(b * n);
                if (on) {
                    // Carrier times (1 + m sin), so the spectrum is the carrier
                    // plus one sideband either side - all inside the
                    // switchboard's passband and all well clear of the comb.
                    const float m = 1.0f + (float)tone_mod_ * tbl_.at_q32(p.mph);
                    v += g * tbl_.at_q32(p.ph) * m;
                }
                if (v > 1.0f)  { v =  1.0f; ++clips_; }
                if (v < -1.0f) { v = -1.0f; ++clips_; }
                out[i * stride] = float_to_s32(v);
                p.ph  += inc;
                p.mph += minc;
                if (t.period_samples) p.cad = (p.cad + 1) % t.period_samples;
                n = (n + 1) & (FFT_N - 1);
            }
        }
    }

    pilot_n_ = (pilot_n_ + period_) & (FFT_N - 1);
}

// ---------------------------------------------------------------- the loop

void Engine::run()
{
    double last_report = monotonic_s();

    while (sh_.running.load(std::memory_order_relaxed)) {
        const snd_pcm_sframes_t r = st_.read(ibuf_.data());
        if (r < 0) {
            sh_.xruns.fetch_add(1, std::memory_order_relaxed);
            if (!st_.recover((int)r)) { sh_.audio_failed.store(true); return; }
            continue;
        }

        // Integers to float once, channel-major, so everything downstream reads
        // one channel contiguously.
        for (unsigned i = 0; i < (unsigned)r; ++i)
            for (unsigned c = 0; c < ncap_; ++c)
                capf_[(size_t)c * period_ + i] = s32_to_float(ibuf_[(size_t)i * ncap_ + c]);

        // A short read is not supposed to happen on a blocking stream, but it
        // is cheaper to zero the tail than to reason about what stale samples
        // would do to the detector's window and the noise floor.
        for (unsigned i = (unsigned)r; i < period_; ++i)
            for (unsigned c = 0; c < ncap_; ++c)
                capf_[(size_t)c * period_ + i] = 0.0f;

        process_capture();
        drain_commands();
        render();

        const snd_pcm_sframes_t w = st_.write(obuf_.data());
        if (w < 0) {
            sh_.xruns.fetch_add(1, std::memory_order_relaxed);
            if (!st_.recover((int)w)) { sh_.audio_failed.store(true); return; }
        }

        // Clip and limiter counts are handed over once a second rather than
        // per period, so the atomics are touched 1/188th as often; the MQTT
        // thread is what turns them into log lines.
        const double now = monotonic_s();
        if (now - last_report >= 1.0) {
            if (clips_) { sh_.clips.fetch_add(clips_, std::memory_order_relaxed); clips_ = 0; }
            const unsigned l = lim_.take_active();
            if (l) sh_.limiter_hits.fetch_add(l, std::memory_order_relaxed);
            last_report = now;
        }
    }
}
