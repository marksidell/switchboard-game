// cityring.h - the ringback waveform (audio.md 8.2).
//
// The Western Electric 803C tone alternator's "city ring": 420Hz mixed with the
// 20Hz ringing current, which beats at 40Hz, and the harmonics the machine and
// the mixing added. Measured from a recording of the Atlanta "755" step-by-step
// office (atlantatelephonehistory.org, atlanta:ringing, 1060-A-1333-755R.wav)
// by a least-squares fit of the harmonics of its ringing frequency, 19.744Hz -
// the machine ran 1.3% slow - and set here on 20Hz exactly, so 420Hz nominal,
// and one period is 2400 samples at 48kHz. Every component is a whole multiple
// of 20Hz; those within 40dB of the strongest are kept, which leaves nothing
// above 1.4kHz and nothing near the comb.
//
// Each row: harmonic of 20Hz, amplitude relative to the strongest, phase (rad),
// for amp * cos(2 pi n 20 t + phase). tts/cue reads these rows too, for the
// loudspeaker's ring cue, so keep one row to a line in this form.
#pragma once

struct CityPartial {
    int   n;
    float amp;
    float phase;
};

static constexpr unsigned CITY_RING_PERIOD = 2400;     // samples: 20Hz at 48kHz

static constexpr CityPartial CITY_RING[] = {
    {   1, 0.0117f, +1.4987f },
    {   3, 0.0308f, -2.7865f },
    {   4, 0.0149f, -2.5609f },
    {   5, 0.0480f, +0.1038f },
    {   6, 0.0131f, +1.2831f },
    {   7, 0.1361f, +2.2866f },
    {   8, 0.0273f, -2.8996f },
    {   9, 0.1312f, -1.1434f },
    {  10, 0.0206f, -0.6749f },
    {  11, 0.1463f, +1.7312f },
    {  12, 0.0646f, +1.7046f },
    {  13, 0.0845f, -2.3818f },
    {  14, 0.1279f, +2.5327f },
    {  15, 0.0147f, +0.9250f },
    {  16, 0.0669f, +0.3831f },
    {  17, 0.0275f, -2.2091f },
    {  18, 0.3061f, +1.8449f },
    {  19, 0.0230f, +0.6756f },
    {  20, 0.3537f, +0.0007f },
    {  21, 0.0160f, +3.1393f },
    {  22, 1.0000f, -1.5829f },
    {  23, 0.0108f, -0.6712f },
    {  24, 0.1282f, +3.0253f },
    {  26, 0.1812f, -1.8377f },
    {  28, 0.0550f, -2.7682f },
    {  30, 0.1056f, -2.0092f },
    {  32, 0.0392f, +3.0795f },
    {  33, 0.0242f, -3.0542f },
    {  34, 0.0375f, -2.4920f },
    {  35, 0.0237f, +0.4874f },
    {  36, 0.0175f, +2.6617f },
    {  37, 0.0234f, -1.9067f },
    {  38, 0.0200f, +3.0000f },
    {  42, 0.0212f, +2.7033f },
    {  46, 0.0176f, +2.0284f },
    {  49, 0.0164f, -3.1214f },
    {  50, 0.0207f, +1.6967f },
    {  51, 0.0174f, +1.0919f },
    {  53, 0.0165f, -1.7155f },
    {  54, 0.0118f, +1.6140f },
    {  55, 0.0140f, +1.6350f },
    {  56, 0.0144f, +3.0401f },
    {  58, 0.0306f, +2.0916f },
    {  60, 0.0286f, +2.6113f },
    {  62, 0.1276f, +1.8192f },
    {  64, 0.0716f, +0.1018f },
    {  66, 0.0331f, -1.5218f },
    {  68, 0.0153f, +0.7452f },
};
