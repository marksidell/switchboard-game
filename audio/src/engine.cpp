// engine.cpp - the audio thread. engine.h has the per-period walk-through and
// the data structures; each function below says which step it is.
//
// Every function in this file runs on the audio thread, except prepare(),
// which runs once at startup before the thread exists.

#include "engine.h"

#include <algorithm>
#include <cmath>
#include <cstring>

#include "util.h"

using chan::FFT_N;
using chan::FFT_HOP;
using chan::SAMPLE_RATE;

// What the output self-check expects at most on a monitor channel.
static const float MON_CEIL = MonitorChain::ceiling();

// Speech detection runs on 10ms frames (audio.md 9.2); the decisions and their
// constants are in vad.h.
static const int VAD_FRAME = Listener::FRAME_SAMPLES;          // 480 samples
static_assert(VAD_FRAME * Listener::FRAMES_PER_S == SAMPLE_RATE,
              "a speech frame is 10 ms");

// prepare()                                                          [startup]
//   Sizes every buffer from what the driver granted, converts the level
//   options from dBFS to amplitudes, designs the speech band-pass, and
//   prepares the tones, the ring detector and the monitor chain. Returns
//   false only if the monitor chain cannot be prepared.
bool Engine::prepare()
{
    period_ = detached_ ? det_period_ : st_.period();
    nplay_  = detached_ ? det_nplay_  : st_.nplay();
    ncap_   = detached_ ? det_ncap_   : st_.ncap();

    ibuf_.assign((size_t)period_ * ncap_,  0);
    obuf_.assign((size_t)period_ * nplay_, 0);
    capf_.assign((size_t)period_ * ncap_,  0.0f);
    ring_.assign((size_t)chan::N_CAP_CH * FFT_N, 0.0f);
    test_row_.assign(period_, 0.0f);
    line_row_.assign((size_t)period_ * 2 * sh_.opt.record_line.size(), 0.0f);
    aec_.assign(chan::N_SLOTS + 1, EchoCanceller());
    ringdet_.prepare();
    for (auto& a : aec_) a.configure((int)std::lround(sh_.opt.aec_delay * 8.0));

    for (int i = 0; i < 2; ++i) {
        sh_.snap[i].data.assign((size_t)chan::N_CAP_CH * FFT_N, 0.0f);
        sh_.snap[i].hop = 0;
    }

    pilot_amp_ = (float)db_to_lin(sh_.opt.pilot_db);
    op_amp_    = (float)db_to_lin(sh_.opt.op_db);
    test_amp_  = (float)db_to_lin(sh_.opt.test_db);
    tones_.prepare(sh_.opt.tone_db, sh_.opt.tone_mod);
    test_inc_  = SineTable::inc_q32(1000.0, SAMPLE_RATE);

    // Speech detector band-pass: the pilots at 6-9kHz are the loudest thing on
    // the channel and must not count; hum must not either (audio.md 9.2). The
    // low-pass is sixth-order: second-order left the lowest pilot only 10.9dB
    // down, so its residual set the noise floor and floor + --vad-margin sat
    // above an operator's normal voice. Sixth puts it below the line's noise.
    vad_hp_ = butter_highpass(300.0, SAMPLE_RATE);
    const std::vector<Biquad> vlp = butter_lowpass6(3400.0, SAMPLE_RATE);
    for (int s = 0; s < 3; ++s) vad_lp_[s] = vlp[(size_t)s];
    vad_params_.margin_db         = sh_.opt.vad_margin;
    vad_params_.abs_floor_db      = sh_.opt.vad_floor;
    vad_params_.hangover_frames   =
        (uint32_t)std::lround(sh_.opt.vad_hangover * Listener::FRAMES_PER_S);
    vad_params_.max_speech_frames =
        (uint32_t)std::lround(sh_.opt.vad_max_speech * Listener::FRAMES_PER_S);
    log_line("speech: margin %.1f dB, floor %.1f dBFS, hangover %.2f s, "
             "max speech %.1f s", sh_.opt.vad_margin, sh_.opt.vad_floor,
             sh_.opt.vad_hangover, sh_.opt.vad_max_speech);

    if (!mon_.prepare(period_, ncap_)) return false;

    for (int ch = 0; ch <= chan::N_PLAY_CH; ++ch) mon_out_[ch] = false;
    for (int ch : sh_.opt.monitor_ch) mon_out_[ch] = true;

    // audio.md 2: the map in use, so a wiring check can be done from the
    // journal alone.
    {
        char mon[32] = { 0 };
        int  k = 0;
        for (size_t i = 0; i < sh_.opt.monitor_ch.size() && k < (int)sizeof mon - 8; ++i)
            k += std::snprintf(mon + k, sizeof mon - k, "%s%d",
                               i ? "," : "", sh_.opt.monitor_ch[i]);
        log_line("channel map: stations 1-%d and %d, operator tap %d, monitor out %s, "
                 "trunks 1-%d on %d-%d (document channels; ALSA index is one less)",
                 chan::N_STATIONS, chan::PHONE_STATION, chan::TAP_CH, mon, chan::N_TRUNKS,
                 chan::trunk_slot(1), chan::trunk_slot(chan::N_TRUNKS));
    }

    log_line("levels: pilot %.1f dBFS, operator tone %.1f dBFS, trunk tone "
             "%.1f dBFS peak (mod %.2f), test tone %.1f dBFS",
             sh_.opt.pilot_db, sh_.opt.op_db, sh_.opt.tone_db,
             sh_.opt.tone_mod, sh_.opt.test_db);
    return true;
}

// ---------------------------------------------------------------- results

// post_free()                                                          [audio]
//   Hands a finished file buffer back to the MQTT thread, which deletes it.
//   The audio thread never frees memory itself.
void Engine::post_free(AudioBuffer* b)
{
    if (!b) return;
    Result r;
    r.topic = Topic::FreeBuf;
    r.buf   = b;
    if (!sh_.res_audio.push(r)) sh_.res_dropped.fetch_add(1, std::memory_order_relaxed);
}

// ---------------------------------------------------------------- commands

// stop_source()                                                        [audio]
//   Stops whatever programme source the circuit has - file or tone - and
//   leaves it with just its pilot. A file's buffer goes back for freeing. If
//   echo is non-null it is published on the topic of the source that stopped
//   ("" to clear it); callers that are about to publish something else pass
//   nullptr.
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
    p.tone = TrunkTones::State();
}

// start_listen()                                                       [audio]
//   Begins (or restarts) a listen, allowing `seconds` for speech to start -
//   Listener::start() takes the floor and clears the window - and publishes
//   "listening".
void Engine::start_listen(int slot, double seconds)
{
    vad_[slot].lis.start(seconds);
    post(Topic::Listen, slot, "listening");
}

// cancel_listen()                                                      [audio]
//   Ends a listen with no result, publishing echo ("" clears the topic).
void Engine::cancel_listen(int slot, const char* echo)
{
    vad_[slot].lis.cancel();
    if (echo) post(Topic::Listen, slot, echo);
}

// drain_commands()                                                     [audio]
//   Step 4 of the period. Pops every Command waiting in the queue and acts on
//   it, so all commands received during the last period take effect in this
//   one. Each case updates the per-channel state that render() reads, then
//   posts the state topic's new value - the "echo" by which the game learns
//   the command took effect.
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
                prog_[slot].kind = Prog::Kind::Tone;
                tones_.start(prog_[slot].tone, k);
                post(Topic::Tone, slot, TrunkTones::name(k));
            }
            break;
        }

        case Verb::Listen:
            if (c.arg <= 0.0f) cancel_listen(c.idx, "");
            else               start_listen(c.idx, c.arg);
            break;

        case Verb::Monitor:     mon_.set_level(c.on, c.arg);  break;
        case Verb::MonitorSrc:  mon_.set_source(c.idx);       break;
        case Verb::MonitorPeer: mon_.set_peer(c.on, c.arg);   break;

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
                if (vad_[s].lis.active()) cancel_listen(s, "");
            }
            // A file on the tap or the monitor is the game's too.
            if (prog_[chan::TAP_CH].kind != Prog::Kind::None)
                stop_source(chan::TAP_CH, "");
            if (prog_[chan::MONITOR_PROG].kind != Prog::Kind::None)
                stop_source(chan::MONITOR_PROG, "");
            // The monitor keeps running, its source back to the tap.
            mon_.stop_game();
            break;

        case Verb::Quit:
            sh_.running.store(false);
            break;
        }
    }
}

// ---------------------------------------------------------------- capture

// process_capture()                                                    [audio]
//   Step 3 of the period. For each capture channel, in capf_:
//     - append its samples to that channel's 4096-sample ring (all channels);
//     - run the speech detector on it (circuits only, not the tap): filter,
//       accumulate 10 ms frames, and hand each frame to the Listener, which
//       keeps the history and reports speech, silence or timeout;
//   then the ring detector on every circuit, the monitor chain on its
//   source, the recording and its playback; advance the ring position, and
//   take a snapshot if a hop is due.
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

        // The echo canceller (audio.md 9.4) runs from a file's start until its
        // echo is over: the last sample sent, plus 50 ms.
        EchoCanceller& ec = aec_[slot];
        if (ec.on() && prog_[slot].kind != Prog::Kind::File &&
            (int32_t)((uint32_t)(g_ / EchoCanceller::DECIM) - aec_ref_[slot].until) >= 0)
            ec.stop((uint32_t)(g_ / EchoCanceller::DECIM));

        for (unsigned i = 0; i < period_; ++i) {
            double y = v.hp.run(vad_hp_, (double)src[i]);
            for (int s = 0; s < 3; ++s) y = v.lp[s].run(vad_lp_[s], y);
            v.acc += y * y;
            const uint64_t g = g_ + i;
            if (ec.on() && g % EchoCanceller::DECIM == 0)
                ec.step((uint32_t)(g / EchoCanceller::DECIM), (float)y);
            if (++v.nacc < VAD_FRAME) continue;

            const double rms = std::sqrt(v.acc / (double)VAD_FRAME);
            float db  = (float)lin_to_db(rms * M_SQRT2);
            v.acc  = 0.0;
            v.nacc = 0;

            // A frame during which this channel had a programme source
            // running is not valid (audio.md 9.3): the two-wire interface has
            // no hybrid, so our own file returns on this receive at full
            // strength. The Listener discards it and restarts its window -
            // unless the echo canceller ran for the whole frame and has
            // converged (9.4). Then the residual is judged, against
            // the echo it took out as well as the usual threshold, and kept
            // out of the history so the floor stays the quiet before the file.
            bool   valid = !v.src_seen;
            bool   keep  = valid;
            double min_db = -1e9;
            const EchoCanceller::Frame f = ec.end_frame((uint32_t)(g / EchoCanceller::DECIM));
            if (f.full) {
                valid  = f.valid;
                db     = (float)f.resid_db;
                min_db = f.echo_db - EchoCanceller::ECHO_MARGIN_DB;
            }
            v.src_seen = false;

            switch (v.lis.frame(db, valid, vad_params_, keep, min_db)) {
            case Listener::Event::Speech:  post(Topic::Listen, slot, "speech");  break;
            case Listener::Event::Silence: post(Topic::Listen, slot, "silence"); break;
            case Listener::Event::Timeout: post(Topic::Listen, slot, "timeout"); break;
            case Listener::Event::None:    break;
            }
        }
    }

    ringdet_.step(capf_.data(), period_, ncirc);

    // The monitor (audio.md 10), with its own file if it has one.
    Prog& mf = prog_[chan::MONITOR_PROG];
    const float* fs = nullptr;
    unsigned     fn = 0;
    if (mf.kind == Prog::Kind::File) {
        fn = (unsigned)std::min<size_t>(mf.buf->samples.size() - mf.pos, period_);
        fs = mf.buf->samples.data() + mf.pos;
    }
    for (int s = 1; s <= chan::N_SLOTS; ++s)
        listening_[s] = chan::is_circuit_slot(s) && vad_[s].lis.active();
    mon_.process(capf_.data(), fs, fn, g_, listening_);
    if (fs) {
        // As a circuit's file: `play` clears from the period after it ends.
        mf.pos += fn;
        if (mf.pos >= mf.buf->samples.size()) stop_source(chan::MONITOR_PROG, "");
    }

    // Playback of a recording (audio.md 10.7): in place of the monitor,
    // already at its level. A ring that runs dry once samples have started
    // arriving is counted; before the first ones, it is the start.
    std::vector<float>& row = mon_.row();
    if (sh_.play_on.load(std::memory_order_acquire)) {
        const size_t n = sh_.play_ring.read(row.data(), period_);
        if (n) play_fed_ = true;
        else if (play_fed_ && n < period_) ++play_short_;
        std::fill(row.begin() + (long)n, row.end(), 0.0f);
    } else {
        sh_.play_ring.discard();
        play_fed_ = false;
    }

    // The recording (audio.md 10.6): this period's loudspeaker feed, as sent,
    // to the MQTT thread's file. A full ring loses the period rather than wait.
    if (sh_.rec_on.load(std::memory_order_acquire) &&
        !sh_.rec_ring.write(row.data(), period_))
        ++rec_lost_;

    ring_w_ = (ring_w_ + period_) & (FFT_N - 1);
    since_hop_ += period_;
    hop_if_due();
}

// hop_if_due()                                                         [audio]
//   Every 2048 samples, copies the last 4096 samples of every capture channel
//   out of ring_ into the next Shared::snap[] buffer, in time order, marks it
//   busy and posts it to the analysis thread. The ring's oldest sample is at
//   ring_w_, so each channel is two memcpy()s: ring_w_..end, then 0..ring_w_.
//   See Shared in ipc.h for the hand-off protocol.
void Engine::hop_if_due()
{
    if (since_hop_ < FFT_HOP) return;
    since_hop_ -= FFT_HOP;

    const int w = snap_next_;
    if (sh_.snap_busy[w].load(std::memory_order_acquire)) {
        // The analysis thread is still on the buffer this hop would overwrite.
        // Drop the hop rather than corrupt it, and do not advance: the
        // analysis thread is behind and must never be waited for. A dropped
        // hop costs 43ms of detector latency and nothing else.
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

    // audio.md 6.1: this thread sets busy and the analysis thread clears it,
    // so there is no moment at which both believe the block is theirs. Busy
    // goes up before the index is posted - the analysis thread can only reach
    // the block through the mailbox, so by the time it can see the block it
    // is already marked.
    sh_.snap_busy[w].store(true, std::memory_order_release);
    const int stale = sh_.snap_ready.exchange(w, std::memory_order_acq_rel);
    if (stale >= 0) {
        // The analysis thread never collected the previous hop, and now never
        // will: the exchange that returned it to us is the same one that
        // took it out of the mailbox, so nobody else holds it. Hand the block
        // back and count the hop.
        sh_.snap_busy[stale].store(false, std::memory_order_release);
        sh_.hops_lost.fetch_add(1, std::memory_order_relaxed);
    }
    snap_next_ ^= 1;
}

// ---------------------------------------------------------------- render

// render()                                                             [audio]
//   Step 5 of the period: builds one period of playback in obuf_, channel by
//   channel. Each playback channel gets exactly one of:
//     - the 1 kHz test tone, if test_on_[ch] - it replaces everything;
//     - the monitor feed, for whatever channels --monitor-ch named (33 and
//       34, the Digiface pair, by default);
//     - the operator tone, for the tap (23);
//     - silence, for a monitor-capable channel the monitor is not on;
//     - its pilot, plus its programme source if it has one (every circuit).
//   A file that runs out during this period is stopped here, which is what
//   publishes `play` going empty. Finally advances the shared pilot counter.
//
//   obuf_ is interleaved, so channel ch's sample i is obuf_[i * nplay + ch-1]:
//   `out` points at the channel's first sample and `stride` steps between
//   frames.
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
            out_ceil_[ch] = test_amp_;
            continue;
        }

        // The monitor goes to whichever channels --monitor-ch named
        // (audio.md 10.1): 33 and 34, the Digiface pair, by default.
        if (mon_out_[ch]) {
            const std::vector<float>& row = mon_.row();
            for (unsigned i = 0; i < period_; ++i)
                out[i * stride] = float_to_s32(row[i]);
            out_ceil_[ch] = MON_CEIL;
            continue;
        }

        const int slot = ch;

        // Silence on everything the map gives nothing to: a Digiface channel
        // the monitor is not on. No pilot is generated for slot 23 (audio.md 2).
        if (!chan::is_circuit_slot(slot) && slot != chan::TAP_CH) {
            for (unsigned i = 0; i < period_; ++i) out[i * stride] = 0;
            out_ceil_[ch] = 0.0f;
            continue;
        }

        // The fixed source: the operator tone on the tap, a comb pilot on every
        // circuit. Neither is a programme source and neither is ever displaced
        // by one. table[(b * n) & 4095] is the whole oscillator.
        const uint32_t b   = (slot == chan::TAP_CH)
                             ? (uint32_t)chan::OP_BIN : (uint32_t)chan::pilot_bin(slot);
        const float    amp = (slot == chan::TAP_CH) ? op_amp_ : pilot_amp_;

        uint32_t n = pilot_n_;
        for (unsigned i = 0; i < period_; ++i) {
            out[i * stride] = float_to_s32(amp * tbl_.at(b * n));
            n = (n + 1) & (FFT_N - 1);
        }

        // The tap takes a file too (audio.md 7), summed over the
        // operator tone exactly as a circuit's is over its pilot. Never a tone:
        // the MQTT thread has no tone command for it.
        // A file or a tone can reach full scale by design, so only the fixed
        // source alone has a ceiling to check (audio.md 11.4).
        Prog& p = prog_[slot];
        out_ceil_[ch] = (p.kind == Prog::Kind::None) ? amp : -1.0f;
        if (p.kind != Prog::Kind::File) aec_feed(slot, nullptr, 0);
        if (p.kind == Prog::Kind::None) continue;

        // Sum the programme source over the fixed one, in float, hard-clipped
        // at +-1.0 with a clip count in the log (audio.md 5.1).
        if (p.kind == Prog::Kind::File) {
            const size_t have = p.buf->samples.size() - p.pos;
            const unsigned n_s = (unsigned)std::min<size_t>(have, period_);
            const float* s = p.buf->samples.data() + p.pos;
            if (slot != chan::TAP_CH) aec_feed(slot, s, n_s);
            if (chan::is_circuit_slot(slot)) {          // audio.md 10.8
                double e = 0.0;
                for (unsigned i = 0; i < n_s; ++i) e += (double)s[i] * s[i];
                mon_.file_sent(slot, e, g_ + n_s);
            }
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
            n = pilot_n_;
            for (unsigned i = 0; i < period_; ++i) {
                float v = amp * tbl_.at(b * n) + tones_.next(p.tone);
                if (v > 1.0f)  { v =  1.0f; ++clips_; }
                if (v < -1.0f) { v = -1.0f; ++clips_; }
                out[i * stride] = float_to_s32(v);
                n = (n + 1) & (FFT_N - 1);
            }
        }
    }

    pilot_n_ = (pilot_n_ + period_) & (FFT_N - 1);
    g_ += period_;
}

// aec_feed()                                                           [audio]
//   The echo canceller's reference for one circuit, this period (audio.md
//   9.4): n samples of its file, then silence, through the speech
//   detector's band-pass so that both sides of the subtraction are filtered
//   alike, every sixth sample kept. A file starting starts the canceller;
//   while it runs, silence is fed after the file ends, until its echo is over.
void Engine::aec_feed(int slot, const float* s, unsigned n)
{
    if (!sh_.opt.aec || !chan::is_circuit_slot(slot)) return;
    EchoCanceller& ec = aec_[slot];
    AecRef& r = aec_ref_[slot];
    constexpr int D = EchoCanceller::DECIM;
    if (n > 0) {
        if (!ec.on()) {
            ec.start((uint32_t)(g_ / D));
            r.hp.reset();
            for (auto& l : r.lp) l.reset();
        }
        r.until = (uint32_t)((g_ + n) / D) + 400;          // + 50 ms of echo
    }
    if (!ec.on()) return;
    for (unsigned i = 0; i < period_; ++i) {
        double y = r.hp.run(vad_hp_, i < n ? (double)s[i] : 0.0);
        for (int k = 0; k < 3; ++k) y = r.lp[k].run(vad_lp_[k], y);
        const uint64_t g = g_ + i;
        if (g % D == 0) ec.ref((uint32_t)(g / D), (float)y);
    }
}

// check_output()                                                       [audio]
//   The output self-check of audio.md 11.4: each checked channel's peak in
//   the buffer about to be written, against the ceiling render() set for it.
//   A peak more than 0.5dB over counts this period as an excess on that
//   channel and raises its highest peak. The samples are what ALSA will be
//   given, so anything wrong after the write does not show here - which is
//   what tells a fault in the program from one downstream of it.
void Engine::check_output()
{
    const int nout = (int)std::min<unsigned>(nplay_, chan::N_PLAY_CH);
    for (int ch = 1; ch <= nout; ++ch) {
        const float ceil = out_ceil_[ch];
        if (ceil < 0.0f) continue;
        const int32_t* out = obuf_.data() + (ch - 1);
        int64_t pk = 0;
        for (unsigned i = 0; i < period_; ++i) {
            const int64_t v = out[(size_t)i * nplay_];
            const int64_t a = v < 0 ? -v : v;
            if (a > pk) pk = a;
        }
        // 0.5dB, and 16 counts so that a silent channel is not flagged by a
        // rounding residue it cannot have but a corrupted one easily exceeds.
        const double lim = (double)ceil * 1.0593 * 2147483392.0 + 16.0;
        if ((double)pk > lim) {
            ++out_over_[ch];
            const float pkf = (float)((double)pk / 2147483648.0);
            if (pkf > out_pk_[ch]) out_pk_[ch] = pkf;
        }
    }
}

// record_line()                                                        [audio]
//   --record-line (audio.md 10.6): while a recording runs, each
//   slot's output as about to be written and its capture of this period, a
//   pair per slot in each frame, to the MQTT thread's second file. Raw: the
//   samples ALSA is given and gave, so the echo of a slot's own playback can
//   be measured against what was sent. A full ring loses the period, counted
//   with the recording's.
void Engine::record_line()
{
    const std::vector<int>& sl = sh_.opt.record_line;
    if (sl.empty() || !sh_.rec_on.load(std::memory_order_acquire)) return;
    const size_t w = 2 * sl.size();
    for (size_t k = 0; k < sl.size(); ++k) {
        const int s = sl[k];
        const bool have = (unsigned)s <= nplay_ && (unsigned)s <= ncap_;
        for (unsigned i = 0; i < period_; ++i) {
            line_row_[i * w + 2 * k]     = have ? s32_to_float(obuf_[(size_t)i * nplay_ + (s - 1)]) : 0.0f;
            line_row_[i * w + 2 * k + 1] = have ? capf_[(size_t)(s - 1) * period_ + i] : 0.0f;
        }
    }
    if (!sh_.line_ring.write(line_row_.data(), line_row_.size())) ++rec_lost_;
}

// ---------------------------------------------------------------- the loop

// run()                                                                [audio]
//   The loop in engine.h's walk-through, until told to stop. An xrun on
//   either direction is recovered and counted; a failure to recover sets
//   audio_failed and returns, and the MQTT thread then exits the program.
//   Once a second, clip and limiter counts are handed to Shared for the log.
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
        check_output();
        record_line();

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
            if (rec_lost_) { sh_.rec_dropped.fetch_add(rec_lost_, std::memory_order_relaxed); rec_lost_ = 0; }
            if (play_short_) { sh_.play_short.fetch_add(play_short_, std::memory_order_relaxed); play_short_ = 0; }
            mon_.hand_over();
            for (int ch = 1; ch <= chan::N_PLAY_CH; ++ch) {
                if (!out_over_[ch]) continue;
                sh_.out_over[ch].fetch_add(out_over_[ch], std::memory_order_relaxed);
                const int cdb = 100000 + (int)std::lround(2000.0 * std::log10(std::max(out_pk_[ch], 1e-9f)));
                int prev = sh_.out_over_cdb[ch].load(std::memory_order_relaxed);
                while (cdb > prev && !sh_.out_over_cdb[ch].compare_exchange_weak(
                           prev, cdb, std::memory_order_relaxed)) {}
                out_over_[ch] = 0;
                out_pk_[ch] = 0.0f;
            }
            last_report = now;
        }
    }
}
