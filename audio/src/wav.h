// wav.h - loading and validating a prompt (audio.md 7.2). Runs on the MQTT
// thread, never on the audio thread.
#pragma once

#include <string>

#include "ipc.h"

// Why a load failed, or Ok. The MQTT thread logs the text of anything but Ok
// and publishes "missing" on the circuit's `play` topic.
enum class LoadResult {
    Ok,
    BadName,        // payload contained '/' or '..', or was empty or too long
    NotFound,
    WrongRate,
    NotMono,
    TooLong,
    Unreadable
};

// load_result_text()                                                     [mqtt]
//   A LoadResult as a short phrase for the log: "not found", "wrong sample
//   rate" and so on.
const char* load_result_text(LoadResult r);

// load_wav()                                                             [mqtt]
//   Loads <dir>/<base>.wav whole into memory as float mono samples, after
//   checking the name, the sample rate (48000), the channel count (1) and the
//   length (max_seconds). On Ok, `out` owns a newly allocated buffer the
//   caller must hand to the audio thread. `hf_db` reports the energy above
//   5.5kHz, for the content warning of audio.md 5.3.
LoadResult load_wav(const std::string& dir, const std::string& base,
                    double max_seconds, AudioBuffer*& out, double& hf_db);
