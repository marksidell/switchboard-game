// wav.h - loading and validating a prompt (audio.md 7.2). Runs on the MQTT
// thread, never on the audio thread.
#pragma once

#include <string>

#include "ipc.h"

enum class LoadResult {
    Ok,
    BadName,        // payload contained '/' or '..', or was empty or too long
    NotFound,
    WrongRate,
    NotMono,
    TooLong,
    Unreadable
};

const char* load_result_text(LoadResult r);

// On Ok, `out` owns a newly allocated buffer the caller must hand to the audio
// thread. `hf_db` reports the energy above 5.5kHz, for the content warning of
// audio.md 5.3.
LoadResult load_wav(const std::string& dir, const std::string& base,
                    double max_seconds, AudioBuffer*& out, double& hf_db);
