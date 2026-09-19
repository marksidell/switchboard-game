// alsa.cpp - opening, starting and recovering the duplex stream. See alsa.h.

#include "alsa.h"

#include <vector>

#include "channels.h"
#include "util.h"

// configure()                                                        [startup]
//   Opens one direction of `dev` and negotiates its hardware parameters:
//   interleaved S32_LE at 48 kHz with no resampling, all the channels the
//   device has (the Digiface's counts are fixed), and the nearest period and
//   buffer size the driver allows to what was asked for. Then the software
//   parameters: never start on its own - start() starts both together.
//   On success, reports what was granted through got_ch / got_period /
//   got_buffer. On failure, logs why and returns false; the handle, if
//   opened, is left for close() to release.
static bool configure(snd_pcm_t*& pcm, const char* dev, snd_pcm_stream_t dir,
                      unsigned want_ch, unsigned want_period, unsigned periods,
                      unsigned& got_ch, snd_pcm_uframes_t& got_period,
                      snd_pcm_uframes_t& got_buffer)
{
    const char* what = (dir == SND_PCM_STREAM_PLAYBACK) ? "playback" : "capture";
    int err = snd_pcm_open(&pcm, dev, dir, 0);
    if (err < 0) {
        log_line("alsa: open %s (%s): %s", dev, what, snd_strerror(err));
        pcm = nullptr;
        return false;
    }

    snd_pcm_hw_params_t* hw;
    snd_pcm_hw_params_alloca(&hw);
    snd_pcm_hw_params_any(pcm, hw);

    // No resampling and no conversion: hw: and not plughw: is only half of it,
    // and an accidental rate conversion would put the pilots off their bins.
    if ((err = snd_pcm_hw_params_set_rate_resample(pcm, hw, 0)) < 0 ||
        (err = snd_pcm_hw_params_set_access(pcm, hw, SND_PCM_ACCESS_RW_INTERLEAVED)) < 0 ||
        (err = snd_pcm_hw_params_set_format(pcm, hw, SND_PCM_FORMAT_S32_LE)) < 0) {
        log_line("alsa: %s configure: %s", what, snd_strerror(err));
        return false;
    }

    unsigned rate = chan::SAMPLE_RATE;
    if ((err = snd_pcm_hw_params_set_rate(pcm, hw, rate, 0)) < 0) {
        log_line("alsa: %s set rate %u: %s (is the clock locked to 48k?)",
                 what, rate, snd_strerror(err));
        return false;
    }

    unsigned cmin = 0, cmax = 0;
    snd_pcm_hw_params_get_channels_min(hw, &cmin);
    snd_pcm_hw_params_get_channels_max(hw, &cmax);
    unsigned ch = (cmin == cmax) ? cmin : want_ch;      // fixed-width, as RME is
    if ((err = snd_pcm_hw_params_set_channels_near(pcm, hw, &ch)) < 0) {
        log_line("alsa: %s set channels: %s (device allows %u..%u)",
                 what, snd_strerror(err), cmin, cmax);
        return false;
    }

    snd_pcm_uframes_t per = want_period;
    int dir0 = 0;
    if ((err = snd_pcm_hw_params_set_period_size_near(pcm, hw, &per, &dir0)) < 0) {
        log_line("alsa: %s set period: %s", what, snd_strerror(err));
        return false;
    }
    snd_pcm_uframes_t buf = per * periods;
    if ((err = snd_pcm_hw_params_set_buffer_size_near(pcm, hw, &buf)) < 0) {
        log_line("alsa: %s set buffer: %s", what, snd_strerror(err));
        return false;
    }
    if ((err = snd_pcm_hw_params(pcm, hw)) < 0) {
        log_line("alsa: %s hw_params: %s", what, snd_strerror(err));
        return false;
    }
    snd_pcm_hw_params_get_period_size(hw, &per, nullptr);
    snd_pcm_hw_params_get_buffer_size(hw, &buf);

    snd_pcm_sw_params_t* sw;
    snd_pcm_sw_params_alloca(&sw);
    snd_pcm_sw_params_current(pcm, sw);
    // Never auto-start: the pair is started explicitly, together.
    snd_pcm_sw_params_set_start_threshold(pcm, sw, buf * 2);
    snd_pcm_sw_params_set_avail_min(pcm, sw, per);
    if ((err = snd_pcm_sw_params(pcm, sw)) < 0) {
        log_line("alsa: %s sw_params: %s", what, snd_strerror(err));
        return false;
    }

    got_ch     = ch;
    got_period = per;
    got_buffer = buf;
    return true;
}

// AlsaStream::open()                                                 [startup]
//   configure() for each direction, then checks the two agree on period and
//   buffer - the audio loop reads one period and writes one period, so they
//   must be the same size - and links them.
bool AlsaStream::open(const Options& o)
{
    const std::string dev = o.device();

    snd_pcm_uframes_t pper = 0, pbuf = 0, cper = 0, cbuf = 0;
    if (!configure(play_, dev.c_str(), SND_PCM_STREAM_PLAYBACK, chan::N_PLAY_CH,
                   o.period, o.periods, nplay_, pper, pbuf)) return false;
    if (!configure(cap_, dev.c_str(), SND_PCM_STREAM_CAPTURE, chan::N_CAP_CH,
                   o.period, o.periods, ncap_, cper, cbuf)) return false;

    if (pper != cper || pbuf != cbuf) {
        log_line("alsa: playback and capture disagree on period/buffer "
                 "(%lu/%lu vs %lu/%lu)", (unsigned long)pper, (unsigned long)pbuf,
                 (unsigned long)cper, (unsigned long)cbuf);
        return false;
    }
    period_  = pper;
    buffer_  = pbuf;
    prefill_ = (unsigned)(buffer_ / period_);
    if (prefill_ > 1) prefill_ -= 1; else prefill_ = 1;

    // audio.md 4: linked, so the two directions share one start and one xrun.
    // The detector does not depend on their relative alignment - each pilot's
    // phase at the far end is arbitrary and only magnitude is measured - but
    // the speech detector's own-playback exclusion does depend on them running,
    // and linking is how that is guaranteed.
    const int err = snd_pcm_link(cap_, play_);
    if (err < 0) log_line("alsa: link: %s (continuing unlinked)", snd_strerror(err));

    log_line("alsa: %s  playback %u ch  capture %u ch  S32_LE %d Hz  "
             "period %lu (%.2f ms)  buffer %lu",
             dev.c_str(), nplay_, ncap_, chan::SAMPLE_RATE,
             (unsigned long)period_, 1000.0 * period_ / chan::SAMPLE_RATE,
             (unsigned long)buffer_);

    if (nplay_ < chan::N_PLAY_CH)
        log_line("alsa: WARNING only %u playback channels; the monitor pair is "
                 "33/34 and will not be reached", nplay_);
    if (ncap_ < chan::N_CAP_CH)
        log_line("alsa: WARNING only %u capture channels; circuits above that "
                 "cannot be detected", ncap_);
    return true;
}

// AlsaStream::close()                                                [startup]
void AlsaStream::close()
{
    if (play_) { snd_pcm_close(play_); play_ = nullptr; }
    if (cap_)  { snd_pcm_close(cap_);  cap_  = nullptr; }
}

// AlsaStream::start()                                                  [audio]
//   prepare() resets each direction to a stopped, empty state. The playback
//   buffer is then filled with all but one period of silence, and the pair
//   started; because they are linked, starting playback starts capture too
//   (the second start is for the unlinked fallback).
bool AlsaStream::start()
{
    int err;
    if ((err = snd_pcm_prepare(play_)) < 0) {
        log_line("alsa: prepare playback: %s", snd_strerror(err)); return false;
    }
    if ((err = snd_pcm_prepare(cap_)) < 0) {
        log_line("alsa: prepare capture: %s", snd_strerror(err)); return false;
    }

    // Prefill with silence so the DACs never see a hole, leaving one period
    // free: the stream is not running yet, so filling the buffer completely
    // would make the next write block forever waiting for space.
    std::vector<int32_t> zero((size_t)period_ * nplay_, 0);
    for (unsigned k = 0; k < prefill_; ++k) {
        const snd_pcm_sframes_t w = snd_pcm_writei(play_, zero.data(), period_);
        if (w < 0) { log_line("alsa: prefill: %s", snd_strerror((int)w)); return false; }
    }
    if ((err = snd_pcm_start(play_)) < 0) {
        log_line("alsa: start: %s", snd_strerror(err)); return false;
    }
    if (snd_pcm_state(cap_) != SND_PCM_STATE_RUNNING) {
        if ((err = snd_pcm_start(cap_)) < 0 && err != -EBADFD) {
            log_line("alsa: start capture: %s", snd_strerror(err)); return false;
        }
    }
    return true;
}

// AlsaStream::recover()                                                [audio]
//   Drops whatever is queued in both directions and starts afresh. Logging
//   from the audio thread is normally forbidden; an xrun is the exception,
//   because the stream has already stopped and the deadline already missed.
bool AlsaStream::recover(int err)
{
    // audio.md 4: log it with the uptime, recover both handles, count it, and
    // continue. A file that was playing continues from where it was - a few
    // milliseconds of silence is preferable to the game seeing a `play` state
    // flicker. Repeated xruns are a configuration problem, not something the
    // program works around.
    log_line("alsa: xrun/error: %s - recovering", snd_strerror(err));
    snd_pcm_drop(play_);
    snd_pcm_drop(cap_);
    return start();
}
