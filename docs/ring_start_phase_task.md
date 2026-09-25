# ring.ino — start the 20 Hz sine at a voltage peak, not a zero crossing

Task for Claude Code. Firmware is owned by the repo; this brief describes the
change against the `ring.ino` in project knowledge as of 2026-09-04, which may
lag the repo. Work from the repo copy.

## Why

T1 is changing from the OSD Black 70V audio transformer to a Hammond 1182G22
toroid (44V C.T. secondary driven as the primary, 234V series primary as the
ring output). This will be recorded in ring_generator.md Rev 48; it is not
in Rev 47.

The OSD transformer saturates at about 4 V RMS on its 4Ω winding at 20 Hz. The
bridge applies 15.3 V RMS (24V rail, g_amplitude 0.90). Measured on the bench
2026-09-04: supply current is linear in rail voltage up to about 5V, then
climbs faster than the voltage, and the 24V rail collapses to ~1V for ~10 ms of
every half-cycle behind a 1 A current limit.

The Hammond's 44V winding takes 44 × 20/50 = 17.6 V RMS at 20 Hz before rated
flux, so steady state at 15.3 V RMS is about 87% of rated. That is fine in
steady state. It is not fine on the first half-cycle:

Starting a sine at a zero crossing and integrating from zero flux puts the
first half-cycle's flux excursion at **twice** the steady-state peak — 0 to
2Φpk instead of −Φpk to +Φpk. At 87% steady state that is ~175% of rated flux
on the first half-cycle. The core saturates, magnetizing current spikes, and
the rail sees it. One 25 ms half-cycle of several amps through a 500 mA
slow-blow F1 is enough to open it; §7.2 of the generator document already
reasons that a slow-blow at ten times rating opens in a few ms.

Starting at a voltage peak instead starts the flux integral at the point where
the steady-state flux is zero. The first half-cycle then swings 0 to −Φpk,
which is the steady-state trajectory, and there is no transient.

The generator runs continuously from power-up (ring cadence is done downstream
by the trunk board's relays), so this happens once per power-up, not per ring.
It still needs fixing: once per power-up is once too often for F1.

## What to change

Only the starting phase. Nothing else in the waveform path moves.

In `startWaveform()`:

```
step_index = 0;
tick_count = 0;
pwmWrite(PIN_PWM_A, duty_a[0]);
pwmWrite(PIN_PWM_B, duty_b[0]);
```

becomes a start at the positive peak, `SINE_STEPS / 4` (index 62 of 250,
s ≈ +1.0). Give it a named constant — something like `START_STEP` — with a
comment carrying the flux argument above in two or three lines, so the next
person does not "fix" it back to zero. The pre-timer duty write uses the same
index.

Keep the rest of the sequence exactly as it is: timer starts, wait for the
first tick, SD HIGH last. The only difference at the moment SD goes high is
that the active leg is at ~90% duty instead of ~0%.

## Things to check while in there

1. **Which drive form is in the repo.** The project copy carries a TEMPORARY
   note dated 2026-09-04 saying the tables are still complemented for a
   74HCT02 and that the Rev 44 active-high form should be restored once the
   74HCT04 is fitted. Confirm which form the repo has and which chip is on the
   board before touching `startWaveform()`, because "parked leg" means
   `DUTY_MAX` in one form and `0` in the other, and the peak start has the
   parked leg's low-side MOSFET on continuously for 25 ms from the first tick.
   In both forms that is the intended state; just be certain the table you
   index is the one that produces it.

2. **Sync output.** `stepCallback()` writes GPIO15 HIGH at k == 0 and LOW at
   k == SINE_STEPS/2. Starting at k = 62, the first sync edge is the LOW write
   at k = 125, which is a no-op because `parkOutputs()` already idles it low.
   The first real edge is the rising one at k = 0, three quarters of a cycle
   after SD. Anything triggering on sync therefore sees the first 37.5 ms of
   output with sync low. That is acceptable; note it in the comment on
   `PIN_SYNC` so it is not reported as a bug.

3. **Bootstrap on the active leg at start.** With SD low before start, both
   low-side outputs are off and neither C_BOOT is charged. At 90% duty the
   active leg's low side is on for ~2.5 µs of each 25 µs period; C_BOOT charges
   through those windows and the IR2104 UVLO holds HO off until it has. Expect
   the first handful of carrier cycles on the active leg to show no high-side
   drive. Harmless — the parked leg's low side is on continuously, so the
   primary is simply held at zero for a few tens of µs. Rev 47 §8.3 records
   that 0.90 leaves a refill window every step; 1.00 does not, which is why
   `G_AMPLITUDE` must not be raised to make the start "cleaner".

4. **Stop sequence is unchanged.** `stopWaveform()` still drives SD low
   immediately at whatever phase it is at. A restart after a stop carries
   whatever remanent flux the toroid kept; the peak start removes the drive's
   own contribution but not that. Acceptable given continuous operation; write
   it down in the same comment rather than trying to solve it.

5. **Stale comments.** The `G_AMPLITUDE` block still says "leave at 1.00 until
   that measurement exists". Rev 47 §8.3 and §9.4 say the opposite: at 1.00
   the low side stops turning on at the sine peak, C_BOOT gets no refill and
   VB−VS collapses to ~2.6V; 0.90 holds 11.98V; a trim above ~0.95 means
   change the transformer tap, not the duty. Rewrite the comment to say that.
   The "48 Vpp at G_AMPLITUDE = 1.0" line in the duty-table comment is now a
   43 Vpp figure at 0.90 and should say so. The header's "Implements
   ring_generator.docx Rev 46" wants to become `ring_generator.md Rev 48` — the file was renamed too.

## How to test

Only with the Hammond fitted. On the OSD the core is saturated in steady state
and the start transient is invisible inside that.

Bench supply on the 24V rail, current limit 1 A. Analog Discovery 3:

- C1 differential across the T1 drive winding.
- C2 on the +24V rail at the bridge (or across a 0.1–1 Ω sense resistor in the
  supply's negative return if you want current rather than voltage).
- Trigger on GPIO14 (SD) rising, 10 ms/div, position set so the capture covers
  the first 100 ms after SD.

Pass: the rail holds through the first half-cycle the same as it does in
steady state, and the primary waveform's first half-cycle has the same
amplitude and shape as the ones that follow. For reference, capture the same
thing once with the old zero-crossing start; the difference should be obvious
on the rail trace. Both captures go in Rev 48 §9.

## Fallback

If the peak start turns out awkward — for example if something downstream
needs sync to lead the first output edge — the alternative is to keep the zero
crossing start and ramp `g` from 0 to `G_AMPLITUDE` over the first two cycles
(500 steps) with a second scale factor applied in `stepCallback()`. It solves
the same problem more slowly. Prefer the peak start; it is one constant.
