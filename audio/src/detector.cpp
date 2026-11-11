// detector.cpp - the analysis thread: FFT and station_circuit.md §8.7. See detector.h
// for the detector in one paragraph and the data structures.

#include "detector.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <ctime>

#include "util.h"

using chan::FFT_N;

// docs/pilot-map.md is the table; this is the one place the program reads it.
// Nothing here recomputes the mapping - channels.h holds it.

// ~Detector()                                                        [startup]
Detector::~Detector()
{
    if (plan_) fftwf_destroy_plan(plan_);
    if (in_)   fftwf_free(in_);
    if (out_)  fftwf_free(out_);
}

// wisdom_path()                                                      [startup]
//   Where FFTW's saved planning results live: $SBAUDIO_WISDOM if set, else
//   ~/.cache/sbaudio-wisdom, else nowhere (plan afresh each start). Under
//   systemd the unit sets $SBAUDIO_WISDOM to /var/lib/sbaudio/wisdom: the unit
//   makes /home read-only, so the home-directory default could never be
//   written there, and the cache belongs to the service rather than to
//   whichever user it runs as.
static std::string wisdom_path()
{
    if (const char* e = std::getenv("SBAUDIO_WISDOM")) return e;
    if (const char* h = std::getenv("HOME")) return std::string(h) + "/.cache/sbaudio-wisdom";
    return "";
}

// prepare()                                                          [startup]
//   See detector.h.
bool Detector::prepare()
{
    in_  = fftwf_alloc_real(FFT_N);
    out_ = fftwf_alloc_complex(FFT_N / 2 + 1);
    if (!in_ || !out_) { log_line("fftw: allocation failed"); return false; }
    pw_.assign(FFT_N / 2 + 1, 0.0);

    // Import, plan, and save only if the plan was not already in the cache.
    // Both FFTW calls return 0 on failure; a failed save is logged, because
    // otherwise it is invisible - every start quietly pays the slow plan and
    // nothing says why.
    const std::string wp = wisdom_path();
    const bool had = !wp.empty() && fftwf_import_wisdom_from_filename(wp.c_str()) != 0;
    const double t0 = monotonic_s();
    plan_ = fftwf_plan_dft_r2c_1d(FFT_N, in_, out_, FFTW_MEASURE);
    if (!plan_) { log_line("fftw: plan failed"); return false; }
    const double plan_ms = 1000.0 * (monotonic_s() - t0);
    if (had) {
        log_line("fftw: plan from wisdom at %s (%.0f ms)", wp.c_str(), plan_ms);
    } else if (wp.empty()) {
        log_line("fftw: planned in %.0f ms; no wisdom path (no $SBAUDIO_WISDOM or "
                 "$HOME), so every start will plan afresh", plan_ms);
    } else if (fftwf_export_wisdom_to_filename(wp.c_str())) {
        log_line("fftw: planned in %.0f ms, wisdom saved to %s", plan_ms, wp.c_str());
    } else {
        log_line("fftw: planned in %.0f ms, but could not save wisdom to %s - "
                 "every start will plan afresh", plan_ms, wp.c_str());
    }

    if (sh_.opt.hann) {
        // Station 8.2's fallback, for a rig whose two clock domains are not
        // locked: Hann, and sum the three bins around each pilot. The guard
        // offsets move out with it - Hann's main lobe is +-2 bins wide, so
        // guards at +-2 and +-3 would be measuring the pilot's own skirt and
        // calling it the noise floor.
        win_.resize(FFT_N);
        for (int i = 0; i < FFT_N; ++i)
            win_[i] = 0.5f * (1.0f - std::cos(2.0f * (float)M_PI * i / FFT_N));
        spread_  = 1;
        guard_[0] = -5; guard_[1] = -4; guard_[2] = 4; guard_[3] = 5;
        log_line("detector: Hann window, 3-bin sum, guards at +-4/+-5");
    } else {
        // The specified configuration. Every pilot completes an integer number
        // of cycles per block, so leakage into other bins is zero by
        // construction and a rectangular window is optimal - provided
        // generation and analysis share one clock. audio.md 15 step 2 is the
        // check that they do.
        spread_ = 0;
        for (int i = 0; i < 4; ++i) guard_[i] = chan::GUARD_OFFSET[i];
        log_line("detector: rectangular window, guards at +-2/+-3, "
                 "MARGIN_DB %.1f, PEER_WINDOW_DB %.1f, OP_WINDOW_DB %.1f",
                 sh_.opt.margin_db, sh_.opt.peer_window_db, sh_.opt.op_window_db);
    }

    if (!sh_.opt.dump_circuit.empty()) {
        int n = 0;
        if (std::sscanf(sh_.opt.dump_circuit.c_str(), "station/%d", &n) == 1 &&
            chan::is_station(n)) {
            dump_slot_ = chan::station_slot(n);
        } else if (std::sscanf(sh_.opt.dump_circuit.c_str(), "trunk/%d", &n) == 1 &&
                   n >= 1 && n <= chan::N_TRUNKS) {
            dump_slot_ = chan::trunk_slot(n);
        } else {
            log_line("--dump: %s is not a circuit id (station/<n> or trunk/<n>)",
                     sh_.opt.dump_circuit.c_str());
            return false;
        }
        // The hop is 2048 samples, so a second is 23.4 of them.
        dump_hops_ = (int)(sh_.opt.dump_seconds * chan::SAMPLE_RATE / chan::FFT_HOP);
        log_line("--dump: %s for %.1fs (%d hops), CSV on stdout",
                 sh_.opt.dump_circuit.c_str(), sh_.opt.dump_seconds, dump_hops_);
    }
    return true;
}

// bin_power()                                                       [analysis]
//   Power at bin b in the block in hand: |X[b]|^2 in rectangular mode, or the
//   sum over b-1..b+1 in Hann mode, where a tone's energy spreads over three
//   bins.
double Detector::bin_power(int b) const
{
    double p = 0.0;
    for (int o = -spread_; o <= spread_; ++o) p += pw_[b + o];
    return p;
}

// bin_level()                                                       [analysis]
//   Power at bin b in dB, absolute rather than against a floor. The windows
//   of station_circuit.md §8.7 compare two bins' levels with each other, and
//   two bins' floors need not be the same: through the switchboard they were
//   found 15-30dB apart, which bin_db() differences carry straight through.
double Detector::bin_level(int b) const
{
    const double p = bin_power(b);
    return p > 0.0 ? 10.0 * std::log10(p) : -INFINITY;
}

// bin_db()                                                          [analysis]
//   dB of one bin above the median of its guard bins, station_circuit.md §8.7. Powers
//   rather than magnitudes, so the factor is 10 and not 20. The median of
//   four is the mean of the middle two after sorting, which ignores one
//   unusually loud or quiet guard bin. This number compared against
//   MARGIN_DB is the whole detection decision.
double Detector::bin_db(int b) const
{
    double g[4];
    for (int i = 0; i < 4; ++i) g[i] = bin_power(b + guard_[i]);
    std::sort(g, g + 4);
    const double floor = 0.5 * (g[1] + g[2]);          // median of four
    if (floor <= 0.0) return -INFINITY;
    return 10.0 * std::log10(bin_power(b) / floor);
}

// confirm()                                                         [analysis]
//   Feeds this hop's value for one topic into its Confirm, and posts a Result
//   if the rule below says it should be published. `first` forces a publish.
void Detector::confirm(Confirm& c, Topic t, int idx, const char* value, bool first)
{
    // audio.md 6.2: published on change only, and only after the same result
    // has been seen on two consecutive hops. The confirmation costs 43ms and
    // removes the flicker a cord produces as it is pushed into a jack. On the
    // first hop, and on a forced republish after a reconnect, it is published
    // regardless, so the broker carries a value for every circuit within about
    // 100ms of the stream starting.
    if (std::strcmp(c.pending, value) != 0) {
        std::snprintf(c.pending, sizeof c.pending, "%s", value);
        c.count = 1;
    } else if (c.count < 2) {
        ++c.count;
    }

    const bool settled = c.count >= 2;
    const bool changed = std::strcmp(c.last, value) != 0;
    if (!first && !(settled && changed)) return;

    std::snprintf(c.last, sizeof c.last, "%s", value);
    c.seen = true;

    Result r;
    r.topic = t;
    r.idx   = (int16_t)idx;
    std::snprintf(r.value, sizeof r.value, "%s", value);
    if (!sh_.res_ana.push(r)) sh_.res_dropped.fetch_add(1, std::memory_order_relaxed);
}

// analyse()                                                         [analysis]
//   Runs identify_peer() (station_circuit.md §8.7) on one capture channel, whose power
//   spectrum is already in pw_, and feeds the results to confirm(). The tap's
//   channel gets only the optone check; slot 23 is otherwise skipped.
void Detector::analyse(int cap_index)
{
    const int slot = cap_index + 1;
    const double margin = sh_.opt.margin_db;

    if (slot == chan::TAP_CH) {
        // audio.md 6.3: the tap's receive channel is not a detector input. The
        // one thing read from it is bin 768, the tap's own tone returning,
        // which is the health check on the tap's transmit path. A dead tap
        // transmit path makes every circuit's `op` read off, which looks
        // exactly like an operator who has not plugged in.
        const bool ok = bin_db(chan::OP_BIN) >= margin;
        confirm(optone_, Topic::OpTone, 0, ok ? "ok" : "deaf", !optone_.seen);
        return;
    }
    if (!chan::is_circuit_slot(slot)) return;

    const double own_db = bin_db(chan::pilot_bin(slot));
    const double op_db  = bin_db(chan::OP_BIN);
    // A pilot must also be within PEER_WINDOW_DB of the circuit's own pilot,
    // and the operator tone within OP_WINDOW_DB of it (station_circuit.md
    // §8.7), each by absolute level. A real peer arrives a few dB under
    // the own pilot and the operator tone above it; crosstalk in the boards
    // and the switchboard cabling arrives 46dB or more under it, which can
    // still be well above the noise floor.
    const double own_lvl   = bin_level(chan::pilot_bin(slot));
    const double window    = own_lvl - sh_.opt.peer_window_db;
    const double op_window = own_lvl - sh_.opt.op_window_db;

    confirm(op_[slot], Topic::Op, slot,
            op_db >= margin && bin_level(chan::OP_BIN) >= op_window ? "on" : "off",
            !op_[slot].seen);

    char value[40];
    int heard_slot = 0;                    // audio.md 10.8: for the peer boost
    if (own_db < margin) {
        // The local health check: a circuit always hears its own pilot, because
        // the two-wire interface has no hybrid and the signal never leaves the
        // board. Losing it means the fault is in this circuit's own transmit
        // path, transformer or cabling.
        std::snprintf(value, sizeof value, "deaf");
        amb_prev_[slot] = false;        // so a return to ambiguous logs at once
    } else {
        // Every comb slot is searched, including 23, which nothing generates
        // (audio.md 2). A pilot there cannot be a topology, so it
        // is reported as ambiguous rather than hidden: it means crosstalk,
        // a mis-wired strip, or a margin low enough to be reading noise.
        int heard[chan::N_SLOTS], n = 0;
        for (int s = 1; s <= chan::N_SLOTS; ++s) {
            if (s == slot) continue;               // own pilot: the deaf check above
            const int b = chan::pilot_bin(s);
            if (bin_db(b) >= margin && bin_level(b) >= window) heard[n++] = s;
        }
        if (n == 0) {
            value[0] = '\0';                       // idle: an empty retained payload
        } else if (n == 1 && chan::is_circuit_slot(heard[0])) {
            chan::circuit_id(heard[0], value, sizeof value);
            heard_slot = heard[0];
        } else {
            std::snprintf(value, sizeof value, "ambiguous");
        }

        // Log the full list with levels - above the floor, and in brackets
        // against the own pilot, which is what the window reads. That alone usually identifies which
        // of the three causes it is (station_circuit.md §8.7): a threshold problem shows
        // several weak pilots, crosstalk one strong and one weak, a cord fault
        // two strong. Logged when the circuit becomes ambiguous and then at
        // most once a second - every hop would be 23 lines a second for as
        // long as the condition lasts.
        const bool   amb = (n > 1) || (n == 1 && !chan::is_circuit_slot(heard[0]));
        const double now = monotonic_s();
        if (amb && (!amb_prev_[slot] || now - amb_logged_[slot] >= 1.0)) {
            amb_logged_[slot] = now;
            char line[384];
            int  k = std::snprintf(line, sizeof line, "detector: slot %d ambiguous, heard", slot);
            for (int i = 0; i < n && k < (int)sizeof line - 48; ++i) {
                char id[24];
                chan::circuit_id(heard[i], id, sizeof id);
                // A slot with no circuit has no id; name the slot itself, so
                // the line says which bin was heard.
                if (!id[0]) std::snprintf(id, sizeof id, "slot/%d", heard[i]);
                const int b = chan::pilot_bin(heard[i]);
                k += std::snprintf(line + k, sizeof line - k, " %s %.1fdB (%+.1f)",
                                   id, bin_db(b), bin_level(b) - own_lvl);
            }
            log_line("%s (own %.1fdB)", line, own_db);
        }
        amb_prev_[slot] = amb;
    }
    sh_.heard_peer[slot].store(heard_slot, std::memory_order_relaxed);
    confirm(peer_[slot], Topic::Peer, slot, value, !peer_[slot].seen);
}

// dump_row()                                                        [analysis]
//   --dump: writes one CSV line to stdout for the dumped circuit - the hop
//   number, its time in seconds, then every comb bin's and bin 768's level in
//   dB above its guard floor - with a header line first. Stops after the
//   requested number of hops.
void Detector::dump_row(uint64_t hop)
{
    if (!dump_header_) {
        std::printf("hop,seconds");
        for (int s = 1; s <= chan::N_SLOTS; ++s) std::printf(",slot%d", s);
        std::printf(",op\n");
        dump_header_ = true;
    }
    std::printf("%llu,%.3f", (unsigned long long)hop,
                (double)hop * chan::FFT_HOP / chan::SAMPLE_RATE);
    for (int s = 1; s <= chan::N_SLOTS; ++s)
        std::printf(",%.2f", bin_db(chan::pilot_bin(s)));
    std::printf(",%.2f\n", bin_db(chan::OP_BIN));
    if (--dump_hops_ <= 0) {
        std::fflush(stdout);
        log_line("--dump: finished");
        dump_slot_ = 0;
    }
}

// process_snapshot()                                                [analysis]
//   For each capture channel: copy (and window) its 4096 samples into in_,
//   run the FFT, turn the output into powers in pw_, then analyse(). If the
//   MQTT thread has asked for a full publish (on every connect), clears every
//   Confirm's `seen` first so this hop publishes everything, and reports the
//   pass done at the end so the MQTT thread can publish "online".
void Detector::process_snapshot(int w)
{
    const unsigned req   = sh_.publish_req.load(std::memory_order_acquire);
    const bool     force = req != publish_served_;
    if (force) {
        // After a (re)connect the broker has nothing; publish what we hold
        // rather than wait for the next change.
        for (int s = 1; s <= chan::N_SLOTS; ++s) { peer_[s].seen = false; op_[s].seen = false; }
        optone_.seen = false;
    }

    const float* base = sh_.snap[w].data.data();
    const int    ncap = std::min(sh_.ncap, (int)chan::N_CAP_CH);

    for (int c = 0; c < ncap; ++c) {
        // audio.md 2: every capture channel, the 31 circuits and the tap.
        const float* src = base + (size_t)c * FFT_N;
        if (spread_) for (int i = 0; i < FFT_N; ++i) in_[i] = src[i] * win_[i];
        else         std::memcpy(in_, src, FFT_N * sizeof(float));

        fftwf_execute(plan_);
        for (int b = 0; b <= FFT_N / 2; ++b)
            pw_[b] = (double)out_[b][0] * out_[b][0] + (double)out_[b][1] * out_[b][1];

        analyse(c);
        if (dump_slot_ == c + 1 && dump_hops_ > 0) dump_row(sh_.snap[w].hop);
    }

    if (force) {
        // Every result of the forced pass is in the queue by now; release
        // ordering makes sure the MQTT thread sees them once it sees this.
        publish_served_ = req;
        sh_.publish_done.store(req, std::memory_order_release);
    }
}

// run()                                                             [analysis]
//   Polls Shared::snap_ready every 2 ms. When a snapshot is waiting, takes it,
//   processes it and releases it by clearing its busy flag. The audio thread
//   set that flag before posting the block (audio.md 6.1); this thread only
//   ever clears it.
void Detector::run()
{
    while (sh_.running.load(std::memory_order_relaxed)) {
        const int w = sh_.snap_ready.exchange(-1, std::memory_order_acq_rel);
        if (w < 0) {
            // The hop is 43ms; 2ms of latency added to it is nothing, and a
            // condition variable would be one more thing the audio thread has
            // to touch.
            struct timespec ts = { 0, 2 * 1000 * 1000 };
            nanosleep(&ts, nullptr);
            continue;
        }
        process_snapshot(w);
        sh_.snap_busy[w].store(false, std::memory_order_release);
    }
}
