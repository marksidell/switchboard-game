// main.cpp - sbaudio, the 551 switchboard simulator's audio program.
//
// Specified by ~/s/game/audio.md, which is the authority for everything here.
// Three threads (audio.md 3): this one becomes the MQTT thread once the other
// two are running.
//
// Startup order is audio.md 13.1, and the order matters: the pilots and the
// operator tone are part of the switchboard's electrical environment and
// nothing about them depends on the broker, so the stream starts first.

#include <cerrno>
#include <csignal>
#include <cstdio>
#include <cstring>
#include <pthread.h>
#include <sys/mman.h>
#include <thread>

#include "alsa.h"
#include "detector.h"
#include "engine.h"
#include "ipc.h"
#include "net.h"
#include "options.h"
#include "util.h"

static Shared* g_shared = nullptr;

static void on_signal(int)
{
    if (g_shared) g_shared->quit.store(true);
}

static void ask_for_realtime(pthread_t t)
{
    // audio.md 14: the program logs and continues if these fail, at the cost of
    // xruns. It is a configuration problem - rtprio and memlock limits, or
    // rtkit - and not something the program can work around.
    sched_param p;
    p.sched_priority = 70;
    const int rc = pthread_setschedparam(t, SCHED_FIFO, &p);
    if (rc != 0)
        log_line("rt: SCHED_FIFO refused (%s); expect xruns. Grant rtprio to "
                 "this user, or run under rtkit.", std::strerror(rc));
    else
        log_line("rt: audio thread at SCHED_FIFO 70");
}

int main(int argc, char** argv)
{
    log_start();

    Options opt;
    bool exit_now = false;
    if (!parse_options(argc, argv, opt, exit_now)) return 2;
    if (exit_now) return 0;

    Shared sh;
    sh.opt   = opt;
    g_shared = &sh;

    log_line("sbaudio starting: broker %s:%d, wav dir %s, card %s",
             opt.broker.c_str(), opt.port, opt.wav_dir.c_str(), opt.device().c_str());

    struct sigaction sa;
    std::memset(&sa, 0, sizeof sa);
    sa.sa_handler = on_signal;
    sigaction(SIGINT,  &sa, nullptr);
    sigaction(SIGTERM, &sa, nullptr);
    std::signal(SIGPIPE, SIG_IGN);

    // ---- open and configure both directions, allocate, lock memory
    AlsaStream stream;
    if (!stream.open(opt)) return 1;
    sh.ncap  = (int)stream.ncap();
    sh.nplay = (int)stream.nplay();

    Engine engine(sh, stream);
    if (!engine.prepare()) return 1;

    Detector detector(sh);
    if (!detector.prepare()) return 1;

    Net net(sh);
    if (!net.prepare()) return 1;

    if (!opt.no_rt) {
        if (mlockall(MCL_CURRENT | MCL_FUTURE) != 0)
            log_line("rt: mlockall refused (%s); expect xruns", std::strerror(errno));
        else
            log_line("rt: memory locked");
    }

    // ---- start the stream, then the audio thread, then the analysis thread
    if (!stream.start()) return 1;

    std::thread audio_thread([&] { engine.run(); });
    if (!opt.no_rt) ask_for_realtime(audio_thread.native_handle());

    std::thread analysis_thread([&] { detector.run(); });

    // ---- this thread is the MQTT thread from here
    net.run();
    net.shutdown();

    sh.running.store(false);
    audio_thread.join();
    analysis_thread.join();
    stream.close();

    log_line("sbaudio stopped");
    return sh.audio_failed.load() ? 1 : 0;
}
