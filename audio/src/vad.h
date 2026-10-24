// vad.h - the speech detector's decisions, one 10 ms frame at a time
// (audio.md 9.2, Rev 6).
//
// The engine does the signal processing - band-pass, square, sum 480 samples -
// and hands each frame's level in dBFS to Listener::frame(). Everything that
// decides anything is here: the one-second history the noise floor comes from,
// the floor itself, the 30-frame window, the three phases of a listen and its
// two timers. Kept apart from the engine so it can be driven frame by frame in
// the unit test, with no audio card, which is the only practical way to check
// a state machine whose timings are seconds long.
//
// A listen, as the game sees it on the `listen` topic (audio.md 9.1):
//
//      start()        "listening"   Waiting   for speech to start
//      Event::Speech  "speech"      Speaking  the listen continues
//      Event::Silence "silence"     Off       speech ended; finished
//      Event::Timeout "timeout"     Off       speech never started within the
//                                             command's seconds, or never
//                                             ended within --vad-max-speech
//      cancel()       ""            Off       cancelled
//
// Allocation-free and lock-free: safe in the audio thread.
#pragma once

#include <cstdint>

// The detector's settings, from the command line. Frame counts rather than
// seconds, because a frame is the detector's unit of time.
struct VadParams {
    double   margin_db       = 10.0;   // --vad-margin: threshold above the floor
    double   abs_floor_db    = -50.0;  // --vad-floor: threshold never below this
    uint32_t hangover_frames = 150;    // --vad-hangover 1.5 s: quiet that ends speech
    uint32_t max_speech_frames = 3000; // --vad-max-speech 30 s: longest speech waited out
};

class Listener {
public:
    static constexpr int FRAME_SAMPLES = 480;   // 10 ms at 48 kHz
    static constexpr int FRAMES_PER_S  = 100;
    static constexpr int WIN           = 30;    // frames in the decision window
    static constexpr int START_NEEDED  = 20;    // of 30 above threshold: speech
    static constexpr int END_ALLOWED   = 2;     // of 30 above threshold: quiet

    enum class Phase : uint8_t { Off, Waiting, Speaking };
    enum class Event : uint8_t { None, Speech, Silence, Timeout };

    // start()                                                          [audio]
    //   Begins a listen, allowing `seconds` for speech to start. Takes the
    //   noise floor from the history and clears the window. A listen already
    //   running is simply restarted (audio.md 9.1).
    void start(double seconds);

    // cancel()                                                         [audio]
    //   Ends a listen with no result.
    void cancel() { phase_ = Phase::Off; }

    // frame()                                                          [audio]
    //   One 10 ms frame: its level in dBFS (sine-referenced), and whether it
    //   counts - false when the channel had a programme source running during
    //   it (audio.md 9.3). Called for every frame whether or not a listen is
    //   running, because the history must always be current. Returns what
    //   happened, if anything; after Silence or Timeout the phase is Off.
    //   A frame the echo canceller cleaned (audio.md 9.4, Rev 26) counts but
    //   is kept out of the history, `keep` false, so the floor is still the
    //   quiet before the file; and it must clear `min_db` as well as the
    //   threshold.
    Event frame(float db, bool valid, const VadParams& p, bool keep = true,
                double min_db = -1e9);

    Phase  phase()    const { return phase_; }
    bool   active()   const { return phase_ != Phase::Off; }
    double floor_db() const { return floor_db_; }

private:
    void   clear_window() { win_ = 0; win_n_ = 0; quiet_ = 0; }
    double history_p10() const;

    // ---- always running: one second of frame levels, for the floor
    float    hist_[100] = { 0 };    // ring of the last 100 valid frames, dBFS
    int      hist_n_ = 0;           // how many are filled, up to 100
    int      hist_w_ = 0;           // next slot to write

    // ---- one listen
    Phase    phase_    = Phase::Off;
    double   floor_db_ = -120.0;    // may rise 1 dB/s during the listen, never fall
    uint32_t win_      = 0;         // last 30 frames, 1 bit each, bit 0 newest,
                                    // 1 = above threshold
    int      win_n_    = 0;         // valid frames in win_ since it last restarted
    uint32_t quiet_    = 0;         // Speaking: frames the quiet condition has held
    uint32_t elapsed_  = 0;         // frames in the current phase, valid or not
    uint32_t start_frames_ = 0;     // Waiting: frames allowed for speech to start
};
