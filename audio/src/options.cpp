// options.cpp - the command line. See options.h for the Options struct.

#include "options.h"

#include "channels.h"

#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>

// Options::device()                                                     [any]
//   Turns the --card value into an ALSA device string. See options.h.
std::string Options::device() const
{
    // The card by name is what audio.md 4 asks for - hw: and not plughw:,
    // so the driver's native S32_LE and 34-channel layout are used and nothing
    // inserts a conversion. A card index or a complete device string is
    // accepted too, because a bench session often has the index to hand and
    // USB enumeration order is why this is an option at all.
    //
    // The name is the ALSA card id, which is not "Digiface": snd-usb-audio
    // builds it from the device's serial number, so this unit is USB24306452
    // (/proc/asound/cards, 2026-09-18). It is stable across replugs and
    // reboots, unlike the index. Another Digiface would have another id, which
    // is why --card has no default (audio.md 4).
    if (card.find(':') != std::string::npos) return card;
    return "hw:" + card;
}

// usage()                                                            [startup]
//   Prints the option list to stderr. `p` is argv[0], for the first line.
static void usage(const char* p)
{
    std::fprintf(stderr,
"Usage: %s [options]\n"
"\n"
"  --card ID              ALSA card id from /proc/asound/cards (required)\n"
"  --period N             frames per period (256)\n"
"  --periods N            periods per buffer (3)\n"
"  --broker HOST[:PORT]   MQTT broker (localhost:1883)\n"
"  --mqtt-user NAME       broker username (mqtt.md 9: not anonymous)\n"
"  --mqtt-pass-file PATH  file whose first line is the password\n"
"  --mqtt-pass PASS       password on the command line - visible in ps, bench use\n"
"  --client-id NAME       MQTT client id (sbgame-audio)\n"
"  --wav-dir PATH         wav directory (wav)\n"
"  --max-file SECONDS     longest file accepted (120)\n"
"  --record-dir PATH      where loudspeaker recordings go (recordings)\n"
"  --record-max SECONDS   longest recording; it then stops itself (14400)\n"
"  --record-line SLOT[,SLOT...]  with each recording, also up to 8 slots' output\n"
"                         and capture, raw, as <name>.line<SLOT>[-<SLOT>...].wav\n"
"                         (none; bench use)\n"
"  --pilot-db DB          pilot level (-40)\n"
"  --op-db DB             operator tone level (-18)\n"
"  --tone-db DB           trunk tone peak level (-20)\n"
"  --tone-mod M           trunk tone modulation depth, 0-1 (1.0)\n"
"  --test-db DB           test tone level (-20)\n"
"  --margin-db DB         detector MARGIN_DB (20)\n"
"  --peer-window-db DB    detector PEER_WINDOW_DB: a pilot further than this\n"
"                         below the circuit's own is not heard (25)\n"
"  --op-window-db DB      detector OP_WINDOW_DB: the operator tone further than\n"
"                         this below the circuit's own pilot is not heard (20)\n"
"  --monitor DB           start with the monitor on at this gain (off)\n"
"  --monitor-ch LIST      playback channels for the monitor, comma-separated,\n"
"                         from 33, 34 (33,34), the Digiface analog pair\n"
"  --monitor-src SRC      monitor source at startup: tap, station/1-22 or 24,\n"
"                         trunk/1-8 (tap)\n"
"  --monitor-tap-trim DB  gain added only while the source is the tap (0)\n"
"  --monitor-file-trim DB gain added to a file on the monitor (0)\n"
"  --monitor-limit DB     the monitor limiter's threshold, dBFS, -60 to -3 (-3)\n"
"  --monitor-gate DB      mute the monitor's source while its line carries more\n"
"                         than this below 50Hz, dBFS, -90 to -10 (off)\n"
"  --monitor-gate-hold S  how long it stays muted after, 0.05 to 2 (0.25)\n"
"  --monitor-lp HZ HZ DB  monitor low-pass passband edge, stopband edge,\n"
"                         stopband dB (3600 5600 70)\n"
"  --vad-margin DB        speech threshold above floor (10)\n"
"  --vad-floor DB         speech absolute threshold (-50)\n"
"  --vad-hangover S       silence that ends speech (1.5)\n"
"  --vad-max-speech S     longest speech waited out before timeout (30)\n"
"  --dump CIRCUIT SECONDS spectrum dump to stdout, e.g. --dump station/5 10\n"
"  --window rect|hann     detector window (rect; see docs/pilot-map.md)\n"
"  --no-realtime          do not ask for SCHED_FIFO or lock memory\n"
"  --version, --help\n", p);
}

// want()                                                             [startup]
//   Checks that the option at argv[i] is followed by at least n more
//   arguments. Prints "--x needs n arguments" and returns false if not, so the
//   caller never reads past the end of argv.
// parse_record_line()                                                [startup]
//   "21" or "20,25,26" -> the slots, in the order given: circuits only, no
//   repeats, at most 8 (audio.md 10.6, Rev 25).
static bool parse_record_line(const char* s, std::vector<int>& out)
{
    out.clear();
    const std::string str = s;
    size_t i = 0;
    while (i <= str.size()) {
        const size_t c = str.find(',', i);
        const std::string tok = str.substr(i, (c == std::string::npos ? str.size() : c) - i);
        char* end = nullptr;
        const long n = std::strtol(tok.c_str(), &end, 10);
        if (tok.empty() || !end || *end != '\0' || !chan::is_circuit_slot((int)n)) {
            std::fprintf(stderr, "--record-line: \"%s\" is not a circuit's slot\n", tok.c_str());
            return false;
        }
        for (int have : out)
            if (have == (int)n) { std::fprintf(stderr, "--record-line: %ld given twice\n", n); return false; }
        out.push_back((int)n);
        if (c == std::string::npos) break;
        i = c + 1;
    }
    if (out.size() > 8) { std::fprintf(stderr, "--record-line: at most 8 slots\n"); return false; }
    return true;
}

// parse_monitor_ch()                                                 [startup]
//   "24", "33,34", "24,33" -> the channels, in the order given. Refuses
//   rather than clamps (audio.md 14): an empty list, a repeat, anything that
//   is not a number, and any channel outside {24, 33, 34} - a circuit or the
//   tap would displace a pilot or the operator tone, which is never what was
//   meant. Returns false having said which channel was wrong and why.
static bool parse_monitor_ch(const char* s, std::vector<int>& out)
{
    out.clear();
    const std::string str = s;
    size_t i = 0;
    while (i <= str.size()) {
        const size_t c = str.find(',', i);
        const std::string tok = str.substr(i, (c == std::string::npos ? str.size() : c) - i);
        if (tok.empty()) {
            std::fprintf(stderr, "--monitor-ch: empty channel in \"%s\"\n", s);
            return false;
        }
        char* end = nullptr;
        const long ch = std::strtol(tok.c_str(), &end, 10);
        if (!end || *end != '\0') {
            std::fprintf(stderr, "--monitor-ch: \"%s\" is not a channel number\n", tok.c_str());
            return false;
        }
        if (!chan::can_carry_monitor((int)ch)) {
            std::fprintf(stderr, "--monitor-ch: channel %ld is not 33 or 34, "
                                 "the Digiface pair\n", ch);
            return false;
        }
        for (int have : out) {
            if (have == (int)ch) {
                std::fprintf(stderr, "--monitor-ch: channel %ld given twice\n", ch);
                return false;
            }
        }
        out.push_back((int)ch);
        if (c == std::string::npos) break;
        i = c + 1;
    }
    if (out.empty()) { std::fprintf(stderr, "--monitor-ch: no channels given\n"); return false; }
    return true;
}

static bool want(int argc, int i, int n, const char* what)
{
    if (i + n < argc) return true;
    std::fprintf(stderr, "%s needs %d argument%s\n", what, n, n == 1 ? "" : "s");
    return false;
}

// parse_options()                                                    [startup]
//   See options.h. One pass over argv: each recognised option consumes its
//   own arguments by advancing i; anything unrecognised is an error rather
//   than being ignored, so a typo in the unit file fails loudly at start.
bool parse_options(int argc, char** argv, Options& o, bool& exit_now)
{
    exit_now = false;

    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        const char* nx = (i + 1 < argc) ? argv[i + 1] : nullptr;

        if (a == "--help" || a == "-h")     { usage(argv[0]); exit_now = true; return true; }
        if (a == "--version")               { std::printf("sbaudio 8 (audio.md Rev 8)\n");
                                              exit_now = true; return true; }

        if (a == "--no-realtime")           { o.no_rt = true; continue; }

        // Everything that survives to here takes at least one argument.
        if (!want(argc, i, 1, a.c_str())) return false;

        if      (a == "--card")           { o.card = nx; ++i; }
        else if (a == "--period")         { o.period = (unsigned)atoi(nx); ++i; }
        else if (a == "--periods")        { o.periods = (unsigned)atoi(nx); ++i; }
        else if (a == "--broker")         { std::string b = nx; ++i;
                                            const size_t c = b.rfind(':');
                                            if (c != std::string::npos) {
                                                o.port = atoi(b.substr(c + 1).c_str());
                                                b = b.substr(0, c);
                                            }
                                            o.broker = b; }
        else if (a == "--mqtt-user")      { o.user = nx; ++i; }
        else if (a == "--mqtt-pass")      { o.pass = nx; ++i; }
        else if (a == "--mqtt-pass-file") { o.pass_file = nx; ++i; }
        else if (a == "--client-id")      { o.client_id = nx; ++i; }
        else if (a == "--wav-dir")        { o.wav_dir = nx; ++i; }
        else if (a == "--max-file")       { o.max_file = atof(nx); ++i; }
        else if (a == "--record-dir")     { o.record_dir = nx; ++i; }
        else if (a == "--record-max")     { o.record_max = atof(nx); ++i; }
        else if (a == "--record-line")    { if (!parse_record_line(nx, o.record_line)) return false;
                                            ++i; }
        else if (a == "--pilot-db")       { o.pilot_db = atof(nx); ++i; }
        else if (a == "--op-db")          { o.op_db = atof(nx); ++i; }
        else if (a == "--tone-db")        { o.tone_db = atof(nx); ++i; }
        else if (a == "--tone-mod")       { o.tone_mod = atof(nx); ++i; }
        else if (a == "--test-db")        { o.test_db = atof(nx); ++i; }
        else if (a == "--margin-db")      { o.margin_db = atof(nx); ++i; }
        else if (a == "--peer-window-db") { o.peer_window_db = atof(nx); ++i; }
        else if (a == "--op-window-db")   { o.op_window_db = atof(nx); ++i; }
        else if (a == "--monitor")        { o.monitor_on = true; o.monitor_db = atof(nx); ++i; }
        else if (a == "--monitor-ch")     { if (!parse_monitor_ch(nx, o.monitor_ch)) return false;
                                            ++i; }
        else if (a == "--monitor-src")    { o.monitor_src = chan::monitor_source_channel(nx); ++i;
                                            if (o.monitor_src == 0) {
                                                std::fprintf(stderr, "--monitor-src: \"%s\" is not a source; "
                                                             "expected tap, station/1-%d or %d, or trunk/1-%d\n",
                                                             nx, chan::N_STATIONS, chan::PHONE_STATION,
                                                             chan::N_TRUNKS);
                                                return false;
                                            } }
        else if (a == "--monitor-tap-trim"){ o.monitor_tap_trim_db = atof(nx); ++i; }
        else if (a == "--monitor-file-trim"){ o.monitor_file_trim_db = atof(nx); ++i; }
        else if (a == "--monitor-limit")  { o.monitor_limit_db = atof(nx); ++i; }
        else if (a == "--monitor-gate")   { o.monitor_gate_db = atof(nx); ++i; }
        else if (a == "--monitor-gate-hold"){ o.monitor_gate_hold = atof(nx); ++i; }
        else if (a == "--monitor-lp")     { if (!want(argc, i, 3, "--monitor-lp")) return false;
                                            o.lp_pass = atof(argv[i + 1]);
                                            o.lp_stop = atof(argv[i + 2]);
                                            o.lp_att  = atof(argv[i + 3]); i += 3; }
        else if (a == "--vad-margin")     { o.vad_margin = atof(nx); ++i; }
        else if (a == "--vad-floor")      { o.vad_floor = atof(nx); ++i; }
        else if (a == "--vad-hangover")   { o.vad_hangover = atof(nx); ++i; }
        else if (a == "--vad-max-speech") { o.vad_max_speech = atof(nx); ++i; }
        else if (a == "--dump")           { if (!want(argc, i, 2, "--dump")) return false;
                                            o.dump_circuit  = argv[i + 1];
                                            o.dump_seconds  = atof(argv[i + 2]); i += 2; }
        else if (a == "--window")         { const std::string w = nx; ++i;
                                            if (w == "hann")      o.hann = true;
                                            else if (w == "rect") o.hann = false;
                                            else { std::fprintf(stderr, "--window: rect or hann\n");
                                                   return false; } }
        else { std::fprintf(stderr, "unknown option %s\n", a.c_str()); usage(argv[0]); return false; }
    }

    if (!o.pass_file.empty()) {
        // A password on ExecStart is in every ps listing on the host; a file
        // that root owns and the service user can read is not.
        std::ifstream f(o.pass_file);
        if (!f) { std::fprintf(stderr, "cannot read %s\n", o.pass_file.c_str()); return false; }
        std::getline(f, o.pass);
        while (!o.pass.empty() && (o.pass.back() == '\r' || o.pass.back() == '\n')) o.pass.pop_back();
    }

    if (o.card.empty()) {
        std::fprintf(stderr, "--card is required: the card id from /proc/asound/cards "
                             "(the Digiface here is USB24306452)\n");
        return false;
    }
    if (o.period < 16 || o.period > 8192) { std::fprintf(stderr, "--period out of range\n"); return false; }
    if (o.periods < 2 || o.periods > 32)  { std::fprintf(stderr, "--periods out of range\n"); return false; }
    if (o.tone_mod < 0.0 || o.tone_mod > 1.0) { std::fprintf(stderr, "--tone-mod must be 0..1\n"); return false; }
    // audio.md Rev 9: the trim is limited, but the commanded gain plus the trim
    // is deliberately not - clamping the sum would cap the tap at a lower
    // commanded gain than a circuit, which is the mismatch the trim exists to
    // remove. The -3dBFS limiter is what protects the output.
    if (o.monitor_tap_trim_db < -30.0 || o.monitor_tap_trim_db > 30.0) {
        std::fprintf(stderr, "--monitor-tap-trim: %g dB is outside -30 to +30\n",
                     o.monitor_tap_trim_db);
        return false;
    }
    if (o.monitor_file_trim_db < -30.0 || o.monitor_file_trim_db > 30.0) {
        std::fprintf(stderr, "--monitor-file-trim: %g dB is outside -30 to +30\n",
                     o.monitor_file_trim_db);
        return false;
    }
    if (o.monitor_limit_db < -60.0 || o.monitor_limit_db > -3.0) {
        std::fprintf(stderr, "--monitor-limit: %g dBFS is outside -60 to -3\n",
                     o.monitor_limit_db);
        return false;
    }
    if (o.monitor_gate_db != 0.0 && (o.monitor_gate_db < -90.0 || o.monitor_gate_db > -10.0)) {
        std::fprintf(stderr, "--monitor-gate: %g dBFS is outside -90 to -10\n", o.monitor_gate_db);
        return false;
    }
    if (o.monitor_gate_hold < 0.05 || o.monitor_gate_hold > 2.0) {
        std::fprintf(stderr, "--monitor-gate-hold: %g s is outside 0.05 to 2\n", o.monitor_gate_hold);
        return false;
    }
    if (o.lp_stop <= o.lp_pass)           { std::fprintf(stderr, "--monitor-lp: stopband edge must exceed passband edge\n"); return false; }
    if (o.max_file <= 0.0)                { std::fprintf(stderr, "--max-file must be positive\n"); return false; }
    if (o.record_max <= 0.0)              { std::fprintf(stderr, "--record-max must be positive\n"); return false; }
    // Both are counted in 10 ms frames, so anything under one frame would be
    // zero frames - speech that ends the instant it starts.
    if (o.vad_hangover < 0.01 || o.vad_hangover > 60.0) {
        std::fprintf(stderr, "--vad-hangover must be 0.01-60 s\n"); return false; }
    if (o.vad_max_speech < 0.01 || o.vad_max_speech > 3600.0) {
        std::fprintf(stderr, "--vad-max-speech must be 0.01-3600 s\n"); return false; }
    return true;
}
