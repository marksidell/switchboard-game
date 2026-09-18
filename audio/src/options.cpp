#include "options.h"

#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>

std::string Options::device() const
{
    // "hw:Digiface" by name is what audio.md 4 asks for - hw: and not plughw:,
    // so the driver's native S32_LE and 34-channel layout are used and nothing
    // inserts a conversion. A card index or a complete device string is
    // accepted too, because a bench session often has the index to hand and
    // USB enumeration order is why this is an option at all.
    if (card.find(':') != std::string::npos) return card;
    return "hw:" + card;
}

static void usage(const char* p)
{
    std::fprintf(stderr,
"Usage: %s [options]\n"
"\n"
"  --card NAME            ALSA card name, index or device (default Digiface)\n"
"  --period N             frames per period (256)\n"
"  --periods N            periods per buffer (3)\n"
"  --broker HOST[:PORT]   MQTT broker (localhost:1883)\n"
"  --mqtt-user NAME       broker username (mqtt.md 9: not anonymous)\n"
"  --mqtt-pass-file PATH  file whose first line is the password\n"
"  --mqtt-pass PASS       password on the command line - visible in ps, bench use\n"
"  --client-id NAME       MQTT client id (sbgame-audio)\n"
"  --wav-dir PATH         wav directory (wav)\n"
"  --max-file SECONDS     longest file accepted (120)\n"
"  --pilot-db DB          pilot level (-40)\n"
"  --op-db DB             operator tone level (-18)\n"
"  --tone-db DB           trunk tone peak level (-20)\n"
"  --tone-mod M           trunk tone modulation depth, 0-1 (1.0)\n"
"  --test-db DB           test tone level (-20)\n"
"  --margin-db DB         detector MARGIN_DB (20)\n"
"  --monitor DB           start with the monitor on at this gain (off)\n"
"  --monitor-lp HZ HZ DB  monitor low-pass passband edge, stopband edge,\n"
"                         stopband dB (3600 5600 70)\n"
"  --vad-margin DB        speech threshold above floor (10)\n"
"  --vad-floor DB         speech absolute threshold (-50)\n"
"  --dump CIRCUIT SECONDS spectrum dump to stdout, e.g. --dump station/5 10\n"
"  --window rect|hann     detector window (rect; see docs/pilot-map.md)\n"
"  --no-realtime          do not ask for SCHED_FIFO or lock memory\n"
"  --version, --help\n", p);
}

static bool want(int argc, int i, int n, const char* what)
{
    if (i + n < argc) return true;
    std::fprintf(stderr, "%s needs %d argument%s\n", what, n, n == 1 ? "" : "s");
    return false;
}

bool parse_options(int argc, char** argv, Options& o, bool& exit_now)
{
    exit_now = false;

    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        const char* nx = (i + 1 < argc) ? argv[i + 1] : nullptr;

        if (a == "--help" || a == "-h")     { usage(argv[0]); exit_now = true; return true; }
        if (a == "--version")               { std::printf("sbaudio 1 (audio.md Rev 1)\n");
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
        else if (a == "--pilot-db")       { o.pilot_db = atof(nx); ++i; }
        else if (a == "--op-db")          { o.op_db = atof(nx); ++i; }
        else if (a == "--tone-db")        { o.tone_db = atof(nx); ++i; }
        else if (a == "--tone-mod")       { o.tone_mod = atof(nx); ++i; }
        else if (a == "--test-db")        { o.test_db = atof(nx); ++i; }
        else if (a == "--margin-db")      { o.margin_db = atof(nx); ++i; }
        else if (a == "--monitor")        { o.monitor_on = true; o.monitor_db = atof(nx); ++i; }
        else if (a == "--monitor-lp")     { if (!want(argc, i, 3, "--monitor-lp")) return false;
                                            o.lp_pass = atof(argv[i + 1]);
                                            o.lp_stop = atof(argv[i + 2]);
                                            o.lp_att  = atof(argv[i + 3]); i += 3; }
        else if (a == "--vad-margin")     { o.vad_margin = atof(nx); ++i; }
        else if (a == "--vad-floor")      { o.vad_floor = atof(nx); ++i; }
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

    if (o.period < 16 || o.period > 8192) { std::fprintf(stderr, "--period out of range\n"); return false; }
    if (o.periods < 2 || o.periods > 32)  { std::fprintf(stderr, "--periods out of range\n"); return false; }
    if (o.tone_mod < 0.0 || o.tone_mod > 1.0) { std::fprintf(stderr, "--tone-mod must be 0..1\n"); return false; }
    if (o.lp_stop <= o.lp_pass)           { std::fprintf(stderr, "--monitor-lp: stopband edge must exceed passband edge\n"); return false; }
    if (o.max_file <= 0.0)                { std::fprintf(stderr, "--max-file must be positive\n"); return false; }
    return true;
}
