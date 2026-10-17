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

// The most the monitor limiter's threshold may be (audio.md 10.1), and so the
// most the output self-check expects on a monitor channel (audio.md 11.4).
// --monitor-limit sets the threshold itself, at or below this (Rev 16).
static constexpr double MON_LIMIT_DB = -3.0;
// audio.md 10.5, Rev 17: the monitor source's delay ahead of the gate, 10ms.
static constexpr size_t GATE_DELAY = 480;
// Rev 19: the gate's band, below 50 Hz. At 100 Hz a man's voice, whose
// fundamental is near 100-130 Hz, reached it within a few dB of the threshold.
static constexpr double GATE_LP_HZ = 50.0;
static const float      MON_CEIL     = (float)std::pow(10.0, MON_LIMIT_DB / 20.0);

// audio.md 8.2. The Bell System tones of the period the 551 belongs to, before
// the precise tone plan replaced them with two-frequency sums. Busy is the
// dial-tone waveform interrupted at 60 IPM, which is how the period offices
// made it - one tone source, one interrupter - and a listener tells the two
// apart by the cadence alone. Reorder, the fast busy (Rev 20), is the same
// again at 120 IPM.
//
// ToneSpec - one row of the tone table: carrier and modulation frequency, and
// the cadence as "on for on_samples out of every period_samples". TONES[] is
// indexed by ToneKind, so TONES[Ringback] is ringback.
struct ToneSpec {
    double carrier_hz, mod_hz;
    unsigned on_samples, period_samples;   // period 0 = continuous
};

static const ToneSpec TONES[] = {
    { 0.0,   0.0,   0,                  0 },                  // Off
    { 600.0, 120.0, 0,                  0 },                  // Dial, continuous
    { 420.0,  40.0, 2 * SAMPLE_RATE,    6 * SAMPLE_RATE },    // Ringback 2s/4s
    { 600.0, 120.0, SAMPLE_RATE / 2,    SAMPLE_RATE },        // Busy 0.5s/0.5s
    { 600.0, 120.0, SAMPLE_RATE / 4,    SAMPLE_RATE / 2 }     // Reorder 0.25s/0.25s
};

// The payload echoed on `tone` for each ToneKind; "" for Off clears the topic.
static const char* TONE_NAME[] = { "", "dial", "ringback", "busy", "reorder" };

// Speech detection runs on 10ms frames (audio.md 9.2); the decisions and their
// constants are in vad.h.
static const int VAD_FRAME = Listener::FRAME_SAMPLES;          // 480 samples
static_assert(VAD_FRAME * Listener::FRAMES_PER_S == SAMPLE_RATE,
              "a speech frame is 10 ms");

// prepare()                                                          [startup]
//   Sizes every buffer from what the driver granted, converts the level
//   options from dBFS to amplitudes, designs the three filters (speech
//   band-pass, monitor high-pass, monitor elliptic low-pass), logs the
//   realised monitor response, and sets the monitor's starting gain. Returns
//   false only if the elliptic design fails.
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
    // the channel and must not count; hum must not either (audio.md 9.2). The
    // low-pass is sixth-order since Rev 18: one section left the lowest pilot
    // only 10.9dB down, so the pilot residual set the noise floor - about
    // -71dBFS on a station - and floor + --vad-margin put the bar above an
    // operator's normal voice. Three sections put it 30dB or more down, below
    // the line's own noise, and --vad-floor is the bar on a quiet line.
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

    // Monitor chain, station 8.8 through audio.md 10.1.
    mon_hp_ = butter_highpass(150.0, SAMPLE_RATE);
    mon_lp_ = elliptic_lowpass(8, sh_.opt.lp_pass, sh_.opt.lp_stop,
                               sh_.opt.lp_att, SAMPLE_RATE, mon_ripple_db_);
    if (mon_lp_.empty()) { log_line("monitor: low-pass design failed"); return false; }
    mon_lp_s_.assign(mon_lp_.size(), BiquadState());
    mon_file_lp_s_.assign(mon_lp_.size(), BiquadState());
    // audio.md 10.4, Rev 11: the file's own gain relative to the source's. It
    // shares the source's ramp, which carries the tap trim while the source is
    // the tap, so the trim is taken back out of the file's share.
    mon_file_lin_    = db_to_lin(sh_.opt.monitor_file_trim_db);
    mon_file_on_tap_ = db_to_lin(sh_.opt.monitor_file_trim_db - sh_.opt.monitor_tap_trim_db);
    // Rev 16: set just above speech, so a switch's click on the line is held
    // to the level of the loudest speech rather than reaching -3dBFS.
    lim_.init(sh_.opt.monitor_limit_db, 0.100, SAMPLE_RATE);
    log_line("monitor: limiter at %.1f dBFS", sh_.opt.monitor_limit_db);
    // audio.md 10.5, Rev 17. The delay line is allocated whether or not the
    // gate is on, so the chain's latency does not depend on a setting.
    gate_on_     = sh_.opt.monitor_gate_db != 0.0;
    gate_lp_     = butter_lowpass(GATE_LP_HZ, SAMPLE_RATE);
    gate_thr_    = db_to_lin(sh_.opt.monitor_gate_db);
    gate_hold_n_ = (int)(sh_.opt.monitor_gate_hold * SAMPLE_RATE);
    gate_dly_.assign(GATE_DELAY, 0.0f);
    if (gate_on_)
        log_line("monitor: gate at %.1f dBFS below %.0f Hz, hold %.2f s, delay %.0f ms",
                 sh_.opt.monitor_gate_db, GATE_LP_HZ, sh_.opt.monitor_gate_hold,
                 1000.0 * GATE_DELAY / SAMPLE_RATE);

    const double at_6k = cascade_mag_db(mon_lp_, 6000.0, SAMPLE_RATE);
    log_line("monitor: elliptic low-pass order 8, pass %.0f Hz, stop %.0f Hz, "
             "%.1f dB; ripple %.4f dB, %.1f dB at 6000 Hz",
             sh_.opt.lp_pass, sh_.opt.lp_stop, sh_.opt.lp_att,
             mon_ripple_db_, at_6k);
    if (at_6k > -sh_.opt.lp_att)
        log_line("monitor: WARNING the lowest pilot at 6000 Hz is only %.1f dB "
                 "down; station 8.8 asks for %.0f", -at_6k, sh_.opt.lp_att);

    for (int ch = 0; ch <= chan::N_PLAY_CH; ++ch) mon_out_[ch] = false;
    for (int ch : sh_.opt.monitor_ch) mon_out_[ch] = true;

    // audio.md 10.2: the monitor is on at startup only if --monitor gives a
    // level. Started at its target rather than ramped to it - there is no
    // loudspeaker transient to avoid before the stream is running.
    // audio.md Rev 9 1.9: a source the device does not capture is refused at
    // startup, as --monitor-ch already refuses an output channel it cannot
    // reach. Echoing a live line while the loudspeaker gets silence would look
    // like a quiet caller with nothing pointing at the fault.
    if (sh_.opt.monitor_src > (int)ncap_) {
        char name[24];
        chan::monitor_source_name(sh_.opt.monitor_src, name, sizeof name);
        log_line("--monitor-src %s is capture channel %d, but the device granted "
                 "only %u capture channels", name, sh_.opt.monitor_src, ncap_);
        return false;
    }
    mon_src_ch_ = sh_.opt.monitor_src;          // audio.md 10.3, --monitor-src
    mon_on_     = sh_.opt.monitor_on;
    mon_cmd_db_ = sh_.opt.monitor_db;
    mon_target_ = monitor_target(mon_src_ch_);
    mon_gain_   = mon_target_;

    // audio.md 2, and task 2 step 10: print the map actually in use, so a
    // wiring check can be done from the journal alone.
    {
        char mon[32] = { 0 };
        int  k = 0;
        for (size_t i = 0; i < sh_.opt.monitor_ch.size() && k < (int)sizeof mon - 8; ++i)
            k += std::snprintf(mon + k, sizeof mon - k, "%s%d",
                               i ? "," : "", sh_.opt.monitor_ch[i]);
        log_line("channel map: stations 1-%d, operator tap %d, monitor out %s, "
                 "trunks 1-%d on %d-%d (document channels; ALSA index is one less)",
                 chan::N_STATIONS, chan::TAP_CH, mon, chan::N_TRUNKS,
                 chan::trunk_slot(1), chan::trunk_slot(chan::N_TRUNKS));
    }

    log_line("levels: pilot %.1f dBFS, operator tone %.1f dBFS, trunk tone "
             "%.1f dBFS peak (mod %.2f), test tone %.1f dBFS",
             sh_.opt.pilot_db, sh_.opt.op_db, sh_.opt.tone_db,
             sh_.opt.tone_mod, sh_.opt.test_db);
    return true;
}

// ---------------------------------------------------------------- results

// monitor_target()                                                     [audio]
//   audio.md 10.2, 10.3. The gain the ramp heads for: the commanded gain, plus
//   --monitor-tap-trim while the source is the tap, or silence when muted. The
//   trim is not part of the commanded gain and is not echoed on `monitor`,
//   which carries what monitor/set asked for.
double Engine::monitor_target(int src_ch) const
{
    if (!mon_on_) return 0.0;
    const double db = mon_cmd_db_ +
                      (src_ch == chan::TAP_CH ? sh_.opt.monitor_tap_trim_db : 0.0);
    return db_to_lin(db);
}

// gate_step()                                                          [audio]
//   audio.md 10.5, Rev 17. One sample of the line-disturbance gate: `raw` is
//   the source's capture, `y` the same sample through the monitor's filters.
//   A switch on the line, or ringing near it, puts far more below 50 Hz on
//   it than speech ever does - telephone speech has nothing below 300 Hz. While
//   the low band's peak exceeds the threshold, and for the hold after, the
//   source is shut: 1ms down, 20ms back up. The filtered source is delayed by
//   GATE_DELAY so the gate is shut before a click's onset reaches the output.
//   Returns the delayed, gated sample.
double Engine::gate_step(float raw, double y)
{
    const double d = gate_dly_[gate_pos_];
    gate_dly_[gate_pos_] = (float)y;
    if (++gate_pos_ == gate_dly_.size()) gate_pos_ = 0;
    if (!gate_on_) return d;

    const double lf = gate_s2_.run(gate_lp_, gate_s1_.run(gate_lp_, (double)raw));
    if (std::fabs(lf) > gate_thr_) {
        if (gate_left_ == 0) ++gate_hits_;
        gate_left_ = gate_hold_n_;
    } else if (gate_left_ > 0) {
        --gate_left_;
    }
    if (gate_left_ > 0) gate_g_ = std::max(0.0, gate_g_ - 1.0 / (0.001 * SAMPLE_RATE));
    else                gate_g_ = std::min(1.0, gate_g_ + 1.0 / (0.020 * SAMPLE_RATE));
    return d * gate_g_;
}

// monitor_ramp_to()                                                    [audio]
//   Starts a 20ms ramp from wherever the gain is now. A ramp already running is
//   taken over from where it has reached, which is what audio.md 10.3 asks for
//   when a second source/set arrives mid-ramp.
void Engine::monitor_ramp_to(double target)
{
    mon_target_ = target;
    mon_ramp_   = (int)(0.020 * SAMPLE_RATE);
    mon_step_   = (mon_target_ - mon_gain_) / (double)mon_ramp_;
}

// monitor_switch_to()                                                  [audio]
//   The bottom of the ramp: change the input and echo. The filter state is
//   carried across rather than cleared - the step from one input to the other
//   happens at zero gain and has rung out before the ramp up is audible
//   (audio.md 10.3).
void Engine::monitor_switch_to(int ch)
{
    mon_src_ch_  = ch;
    mon_pend_ch_ = 0;
    char name[24];
    if (chan::monitor_source_name(ch, name, sizeof name)) post(Topic::MonitorSrc, 0, name);
}

// post()                                                               [audio]
//   Queues a Result for the MQTT thread: "topic t for slot/channel idx is now
//   value". This is how every state change the audio thread makes reaches the
//   broker. If the queue is full the result is dropped and counted.
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
    p.tone = ToneKind::Off;
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
            // 20ms ramp so a level step does not click; "off" is a mute, ramped
            // the same way, and the filter keeps running so turning the monitor
            // on is instant and has no transient from a cold filter state.
            mon_on_     = c.on;
            mon_cmd_db_ = c.arg;
            // A source switch is mid-flight: stay headed for silence, and let
            // the switch ramp back up to this new gain when it lands.
            if (!mon_pend_ch_) monitor_ramp_to(monitor_target(mon_src_ch_));
            char buf[32];
            if (c.on) format_db(c.arg, buf, sizeof buf);
            else      std::snprintf(buf, sizeof buf, "off");
            post(Topic::Monitor, 0, buf);
            break;
        }

        case Verb::MonitorSrc: {
            // audio.md 10.3. Already there: echo and do nothing else.
            if (c.idx == mon_src_ch_ && !mon_pend_ch_) {
                char name[24];
                if (chan::monitor_source_name(c.idx, name, sizeof name))
                    post(Topic::MonitorSrc, 0, name);
                break;
            }
            // Muted: the input changes at once, with no ramp, and is echoed.
            // There is nothing to click, and the filter keeps running either way.
            if (!mon_on_) {
                monitor_switch_to(c.idx);
                mon_target_ = monitor_target(mon_src_ch_);   // still 0 while muted
                break;
            }
            // Otherwise ramp to silence and change at the bottom. A second
            // source/set during a ramp replaces the pending channel and takes
            // the ramp over from wherever it has reached.
            mon_pend_ch_ = c.idx;
            monitor_ramp_to(0.0);
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
                if (vad_[s].lis.active()) cancel_listen(s, "");
            }
            // The tutor's voice on the monitor (audio.md 10.4, Rev 11) is the
            // game's, so it goes with the game's other files.
            if (prog_[chan::MONITOR_CH].kind != Prog::Kind::None)
                stop_source(chan::MONITOR_CH, "");
            // The monitor keeps running, but its source returns to the tap
            // under the 10.3 ramp: the calls a circuit source was following
            // have been torn down, and the tap is the one source that is not
            // about a call (audio.md 13.2, Rev 8).
            if (mon_src_ch_ != chan::TAP_CH || mon_pend_ch_) {
                if (!mon_on_) {
                    monitor_switch_to(chan::TAP_CH);
                    mon_target_ = monitor_target(mon_src_ch_);
                } else {
                    mon_pend_ch_ = chan::TAP_CH;
                    monitor_ramp_to(0.0);
                }
            }
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
//   then run the tap channel (23) through the monitor chain into mon_row_,
//   advance the ring position, and take a snapshot if a hop is due.
void Engine::process_capture()
{
    const int ncirc = (int)std::min<unsigned>(ncap_, chan::N_CAP_CH);

    for (int c = 0; c < ncirc; ++c) {
        // Capture 24 is read by nothing, so it is not even kept: no ring, no
        // snapshot, no speech detection (audio.md 2, Rev 7).
        if (!chan::is_read_channel(c + 1)) continue;

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
            double y = v.hp.run(vad_hp_, (double)src[i]);
            for (int s = 0; s < 3; ++s) y = v.lp[s].run(vad_lp_[s], y);
            v.acc += y * y;
            if (++v.nacc < VAD_FRAME) continue;

            const double rms = std::sqrt(v.acc / (double)VAD_FRAME);
            const float  db  = (float)lin_to_db(rms * M_SQRT2);
            v.acc  = 0.0;
            v.nacc = 0;

            // A frame during which this channel had a programme source
            // running is not valid (audio.md 9.3): the two-wire interface has
            // no hybrid, so our own file returns on this receive at full
            // strength. The Listener discards it and restarts its window.
            const bool valid = !v.src_seen;
            v.src_seen = false;

            switch (v.lis.frame(db, valid, vad_params_)) {
            case Listener::Event::Speech:  post(Topic::Listen, slot, "speech");  break;
            case Listener::Event::Silence: post(Topic::Listen, slot, "silence"); break;
            case Listener::Event::Timeout: post(Topic::Listen, slot, "timeout"); break;
            case Listener::Event::None:    break;
            }
        }
    }

    // Monitor: the source's receive channel through the chain of audio.md 10.1,
    // which is the tap unless monitor/source/set has named a circuit (10.3).
    // Run unconditionally, muted or not, so that turning the monitor on is
    // instant and has no transient from a cold filter state.
    //
    // A file on the monitor (audio.md 10.4, Rev 11) is summed in after the
    // filter, through a second copy of the same low-pass, so it is held out of
    // the pilot band exactly as the source is: the loudspeaker is in the room
    // with the operator's microphone. Its filter runs whether a file plays or
    // not, so a file never starts against a cold state either.
    Prog& mf = prog_[chan::MONITOR_CH];
    const float* fs = nullptr;
    unsigned     fn = 0;
    if (mf.kind == Prog::Kind::File) {
        fn = (unsigned)std::min<size_t>(mf.buf->samples.size() - mf.pos, period_);
        fs = mf.buf->samples.data() + mf.pos;
    }
    if ((int)ncap_ >= mon_src_ch_) {
        const float* src = &capf_[(size_t)(mon_src_ch_ - 1) * period_];
        for (unsigned i = 0; i < period_; ++i) {
            double y = mon_hp_s_.run(mon_hp_, (double)src[i]);
            for (size_t s = 0; s < mon_lp_.size(); ++s) y = mon_lp_s_[s].run(mon_lp_[s], y);
            y = gate_step(src[i], y);
            double f = (i < fn) ? (double)fs[i] : 0.0;
            for (size_t s = 0; s < mon_lp_.size(); ++s) f = mon_file_lp_s_[s].run(mon_lp_[s], f);
            if (mon_ramp_ > 0) { mon_gain_ += mon_step_; --mon_ramp_; }
            else               { mon_gain_ = mon_target_; }
            const double fg = (mon_src_ch_ == chan::TAP_CH) ? mon_file_on_tap_ : mon_file_lin_;
            mon_row_[i] = (float)lim_.run((y + f * fg) * mon_gain_);

            // The bottom of a source ramp, mid-period: change the input, echo,
            // and ramp back up to the commanded gain for the new source
            // (audio.md 10.3). Done here rather than at a period boundary so
            // the silence is the 20ms the specification asks for and not 20ms
            // plus whatever is left of this period.
            // mon_ramp_ reaching 0 is the test, not the gain reaching 0: the
            // last ramp step lands on the target by accumulation and can sit a
            // float's breadth either side of it. A pending channel is only ever
            // set together with a ramp to silence, so ramp == 0 means arrived.
            if (mon_pend_ch_ && mon_ramp_ == 0) {
                mon_gain_ = 0.0;
                const int want = mon_pend_ch_;
                if ((int)ncap_ >= want) {
                    monitor_switch_to(want);
                    src = &capf_[(size_t)(mon_src_ch_ - 1) * period_];
                } else {
                    mon_pend_ch_ = 0;       // not captured; stay where we are
                }
                monitor_ramp_to(monitor_target(mon_src_ch_));
            }
        }
    } else {
        std::fill(mon_row_.begin(), mon_row_.end(), 0.0f);
    }
    if (fs) {
        // As a circuit's file: `play` clears from the period after it ends.
        mf.pos += fn;
        if (mf.pos >= mf.buf->samples.size()) stop_source(chan::MONITOR_CH, "");
    }

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
        if (!chan::is_read_channel(c + 1)) continue;   // nothing reads capture 24
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
//     - the monitor feed, for whatever channels --monitor-ch named (24 by
//       default; 33 and 34 are the Digiface fallback);
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
        // (audio.md 10.1): channel 24, the A32 output wired to the amplifier,
        // by default; 33 and 34, the Digiface pair, as the fallback.
        if (mon_out_[ch]) {
            for (unsigned i = 0; i < period_; ++i)
                out[i * stride] = float_to_s32(mon_row_[i]);
            out_ceil_[ch] = MON_CEIL;
            continue;
        }

        const int slot = ch;

        // Silence on everything the map gives nothing to: the monitor channel
        // when the monitor is elsewhere, and the Digiface pair when it is not
        // there. No pilot is generated for slots 23 and 24 (audio.md 2).
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

        // The tap takes a file too (audio.md 7, Rev 10), summed over the
        // operator tone exactly as a circuit's is over its pilot. Never a tone:
        // the MQTT thread has no tone command for it.
        // A file or a tone can reach full scale by design, so only the fixed
        // source alone has a ceiling to check (audio.md 11.4).
        Prog& p = prog_[slot];
        out_ceil_[ch] = (p.kind == Prog::Kind::None) ? amp : -1.0f;
        if (p.kind == Prog::Kind::None) continue;

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
            if (gate_hits_) { sh_.gate_hits.fetch_add(gate_hits_, std::memory_order_relaxed); gate_hits_ = 0; }
            const unsigned l = lim_.take_active();
            if (l) sh_.limiter_hits.fetch_add(l, std::memory_order_relaxed);
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
