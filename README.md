# Inokim OXO → VESC Duet conversion

Configs, LispBM script and wiring diagrams for converting an Inokim OXO scooter to a VESC Labs Duet dual-motor controller.

## Hardware

| Part | Details |
|---|---|
| Controller | VESC Labs Duet (STM32 dual motor + ESP32-C3 "Express") |
| Rear motor (M1, CAN ID 48) | Upgraded 2500 W hub, 30 poles, hall sensors, no thermistor |
| Front motor (M2, CAN ID 49) | Stock OXO 1500 W hub, 30 poles, hall sensors, no thermistor, direction inverted |
| Battery | Orcell 60 V 16S, 27.5 Ah, BMS ~100–110 A continuous |
| Tyres | 10×3.0, effective diameter 245 mm (GPS-corrected) |
| Display | VESC Dash 35B (CAN), package Dash35B + Dash ESC on the controller |
| Lights | Inokim light module LX1-60A (60 V DC converter + LED control); extra 12 V aux front light |
| Inputs | 3-wire hall throttle (ADC1), normally-open brake switch (ADC2); LDR light sensor on ADC3 planned, not fitted |
| GPS | u-blox type module on the ESP32 GPS port, logged by LogUI |

## Repository layout

```
config/original/   configs as exported from the controller (first export, plus the 2026-10-31 app config with IMU calibration)
config/current/    corrected configs (see "Config changes")
lisp/              Dash ESC 2.5 script + light box / brake light / auto-light control
tools/             fit_thermal.py: fits the motor heat model to logged resistance measurements
tools/vesc_cli/    command-line VESC access: logs, configs, Lisp, display package, REPL (see its README)
diagrams/          wiring diagrams and pinouts (JPEG)
```

## Duet connections

See `diagrams/duet_complete_wiring.jpg`.

| Duet port | Pin | Connected to |
|---|---|---|
| Power input | VBUS / GND | Battery via XT90-S anti-spark + fuse |
| M1 phases A/B/C | — | Rear motor yellow / green / blue (thick) |
| M1 sensor (JST PH 6) | 1 GND, 2 Hall A, 3 Hall B, 4 Hall C, 5 Temp (empty), 6 +5V | Rear black, yellow, green, blue, —, red |
| M2 phases / sensor | — | Front motor (round connector, pinout to be documented) |
| STM32 AUX (JST PH 8) | 1 +5V | Throttle red, brake switch wire 1 (LDR leg 1, planned) |
| | 3 GND | Throttle black |
| | 4 ADC1 | Throttle signal |
| | 5 TX (GPIO) | Light box pin 4 green (head + tail command) |
| | 6 RX (GPIO) | Light box pin 3 yellow (brake light command) |
| | 7 ADC2 | Brake switch wire 2 |
| | 8 ADC3 | Free (LDR leg 2, planned) |
| Switched VBUS (AUX 2) | 2 V+ / 1 GND | Light box pin 1 red (60 V in) / pin 2 black |
| Switched +12V (AUX 1) | 2 +12V / 1 GND | Aux front light (follows the Dash lights button, max 0.72 A) |
| CAN (JST PH 4) | GND, CANL, CANH, +5V | Dash 35B |
| ESP32 GPS (JST PH 4) | 1 GND, 2 RX2, 3 TX2, 4 +5V | GPS GND, TX, RX, VCC |

## Light module LX1-60A pinout

See `diagrams/inokim_light_module_pinout.jpg`. Measured with the scooter on.

| Connector | Pin | Wire | Function | Measured |
|---|---|---|---|---|
| Controller input (green, 5-pin) | 1 | Red | Supply in | 60 V when on |
| | 2 | Black | GND | — |
| | 3 | Yellow | Rear / brake command | 3.3 V lights on; flashes while braking (also lights off) |
| | 4 | Green | Head + tail command | 3.3 V lights on |
| | 5 | Blue | Unused | always 0 V |
| Rear light (blue, 4-pin) | 1 | Red | 60 V supply | constant 60 V |
| | 2 | Black | Brake (to confirm) | 0 V at rest |
| | 3 | Yellow | GND | — |
| | 4 | Blue | Tail light + | 6 V lights on |
| Front light A / B (orange, 2-pin) | 1 | Black | GND | — |
| | 2 | White | Headlight + | 6 V lights on |

## Motor detection results

| | Rear (ID 48) | Front (ID 49) |
|---|---|---|
| Resistance | 56.4 mΩ | 37.3 mΩ |
| Inductance | 135.3 µH | 89.0 µH |
| Lq − Ld | 25.6 µH | 14.7 µH |
| Flux linkage | 19.25 mWb | 14.64 mWb |
| Sensors | Hall | Hall |
| Torque constant (est.) | 0.43 Nm/A | 0.33 Nm/A |
| No-load top speed at 67 V (est.) | ~62 km/h | ~81 km/h |

## Key settings

| Setting | Rear (ID 48) | Front (ID 49) |
|---|---|---|
| Motor current max / brake | 90 A / −35 A | 70 A / −20 A |
| Battery current max / regen | 50 A / −12 A | 40 A / −6 A (total 90 A) |
| Absolute max current | 150 A | 150 A |
| Battery cutoff start / end | 54.4 / 49.6 V | 54.4 / 49.6 V |
| Regen voltage cutoff start / end | 67.0 / 67.6 V | 67.0 / 67.6 V |
| Motor temp sensor | Disabled | Disabled |
| Temp compensation | Off | Off |
| Field weakening | 15 A, duty start 92%, ramp 0.2 s (testing) | 0 A (off) |
| Poles / gear ratio / wheel | 30 / 1 / 245 mm | 30 / 1 / 245 mm |
| Inverted | No | Yes |

App (shared, ID 48): app to use *ADC* (not ADC and UART), permanent UART off (TX/RX are used as GPIO for the lights), control type *Current No Reverse Brake ADC2*, Multiple ESCs over CAN on, traction control on (2000 ERPM), ramp +0.30 s / −0.10 s, CAN status messages 1–5 at 50 Hz, cruise control enabled.

## Config changes (original → current)

| File | Setting | Was | Now |
|---|---|---|---|
| Rear | Motor current max brake | 0 A | −35 A |
| | Gear ratio | 2.769 | 1 (caused speedometer to read ~20 km/h) |
| | Temp compensation | On | Off |
| Front | Poles / gear ratio / wheel / Ah | 14 / 3 / 83 mm / 6 Ah | 30 / 1 / 250 mm / 27.5 Ah |
| | Temp compensation | On | Off |
| App | CAN status messages | 1–4 | 1–5 |
| | Traction control | Off | On, 2000 ERPM |
| | Brake ADC2 start voltage | 0.005 V | 0.15 V |
| **2026-10-31 (after first ride)** | | | |
| Front | Motor current max | 60 A | 70 A |
| | Battery current max | 30 A | 35 A |
| Rear | Field weakening current / duty start | 0 A / 85% | 10 A / 92% |
| App | App to use | ADC and UART | ADC |
| | Permanent UART | On | Off |
| | Cruise control (ADC buttons) | Off | On |
| Rear + front | Regen voltage cutoff start / end | 1000 / 1100 V (off) | 67.0 / 67.6 V (protects a full battery) |
| | Slow ABS current limit | On (rejected by firmware) | Off |
| **2026-11-03** | | | |
| Front | Battery current max | 35 A | 40 A (front was at its limit at top speed) |
| Rear | Field weakening current | 10 A | 15 A |
| Rear + front | Wheel diameter | 250 mm | 245 mm (VESC read 2% high vs GPS) |

Notes:
- *Slow ABS current limit* is forced off by the Duet firmware; it cannot be enabled with the standard firmware. The configs keep it off, so loading them no longer shows the "Parameters truncated" warning.
- `config/current/appconf_ID48.xml` is based on the controller export of 2026-10-31 (`config/original/appconf_ID48_2026-10-31_imu_calibrated.xml`) and contains the IMU calibration (rotation roll 70.4° / pitch −57.7° / yaw 150°, accel and gyro offsets). Older app files without it would erase the calibration when loaded.
- That export showed that CAN status message 5, traction control and the brake start voltage fix had not been applied on the controller; they are set again in the current file.

## LispBM script (`lisp/dash_esc_lights.lisp`)

Based on Dash ESC 2.5 from [vedderb/vesc_pkg](https://github.com/vedderb/vesc_pkg). Additions:
- Switched VBUS (AUX 2) kept on to power the light box.
- TX → headlight + tail: follows the Dash lights button.
- Automatic lights from an LDR on ADC3 (1.0 V on / 1.5 V off, 5 s delay) are written but commented out, as no sensor is fitted.
- RX → rear/brake command: 3.3 V while the brake is pulled (flashing like the original controller by default, or steady with `brake-flash` = 0), otherwise steady 3.3 V with lights on. The brake light has not lit in tests yet with either signal; the rear light itself is suspected.
- AUX 1 (switched 12 V) follows the Dash lights button and powers the aux front light.
- Motor winding temperature (the hubs have no sensors, see below).

### Motor winding temperature

No thermistor can be routed out of either hub, so the temperature is worked out in software:

- **Heat model, both motors, always running.** Two nodes per motor: winding + stator, heated by copper loss 1.5·R·(iq²+id²) (R rising 0.393 %/°C) plus iron loss growing with speed^1.5; and shell + magnets, cooling to ambient better the faster the wheel turns. One lumped node (the first version) spreads the heat over the whole motor and lags the winding on hard bursts: 60 s at 90 A gives 51 °C with one node, 67 °C with two. Ambient is the lowest FET temperature seen since power-on (the FET reads warm right after a ride).
  Starting constants, from the motor sizes (rear 2500 W, front 1500 W hub): rear Cw 900 J/K, Cs 1600 J/K, winding→shell 0.25 K/W, shell→air 1.0 W/K + 0.08 W/K per km/h, iron 25 W at 55 km/h; front 600 / 1100 / 0.35 / 0.8 + 0.06 / 15 W. These are estimates to be replaced by a fit (see "Calibrating the heat model").
  The 2026-11-04 rides (logs 020–024, script not yet installed) give a modelled rear winding peak of about 48 °C on the morning descent and 59 °C on the evening climb. The climb was mild: only 11 s above 60 A on the rear.
- **Reset after power-on.** The model starts at ambient, which is wrong after a hot ride, so the first rear resistance measurement after power-on always resets both models (front seeded at 0.7 × the rear rise above ambient). `therm-boot-correct` = 0 turns this off.
- **Rear resistance measurement at stops.** Standing still, throttle released and brake held for 2 s (at most once a minute): 25 A through the stationary rear motor for about 0.3 s, winding temperature from the resistance rise. Rear only, because selecting motor 2 in LispBM is global and would redirect the other threads during the measurement. With `therm-meas-correct` = 1 the rear model is reset to each measurement; it is 0 until the measurements have been checked in the logs.
- **Derating.** Above 100 °C (hottest winding) or 80 °C (hottest shell, where the magnets are) the drive mode current scale is reduced linearly, down to 30 % at 125 °C / 100 °C; the lower factor wins. It acts through the Dash ESC drive profile, so it needs the display connected.
- **Display and logs.** The Dash motor temperature shows the hottest modelled winding. New log fields: `Wind M1`, `Wind M2`, `Shell M1`, `Shell M2` (model), `Loss M1`, `Loss M2` (W), `Therm amb`, `Wind M1 meas`, `R M1 meas` (last measurement), `R M1 est` (firmware online resistance estimate, for comparison), `Therm derate`.

REPL commands, with the brake held or the wheel in the air:
- `(therm-test)`: one rear measurement, prints resistance, winding and FET temperature.
- `(therm-cooldown n period)`: n rear measurements, period seconds apart, for the cooldown curve after a ride; stops if the scooter moves or the throttle is touched. The stop measurement is held off while it runs.
- `(therm-cal)`: with a **cold** motor (parked for some hours), averages 5 measurements and stores them as the reference (eeprom 100/101). Without it the motor config resistance at an assumed 25 °C is used.
- All parameters can be changed live with `setq`, e.g. `(setq therm-meas-correct 1)`.

### Calibrating the heat model

The 10 Hz logs alone cannot calibrate it: the back-EMF does drift down about 0.8 % over a ride, which would suggest about 7 K of magnet warming, but the same drift follows the falling pack voltage and cannot be separated from it. The resistance measurements are the ground truth.

1. **Install and check.** Upload the script; confirm the log has `Wind M1 meas`, `Shell M1` and `Loss M1` columns.
2. **Repeatability.** Wheel in the air, `(therm-test)` five times. Spread should stay within about 1 mOhm (about 4 °C); if it is worse, the stop measurements cannot be trusted and the fit will not be either.
3. **Cold reference.** After the scooter has been parked indoors for some hours: `(therm-cal)`. Note the room temperature if you have a thermometer.
4. **Hot ride with measurements.** `(setq therm-meas-interval 20.0)` for denser points, then the hardest climb available (the evening route, or a steep hill two or three times). Stop every 2–3 minutes and hold the brake for 2 s standing still; expect a small jerk from the test current. The aim is to get the rear winding to about 90–100 °C measured; stop climbing if `Wind M1 meas` passes 110 °C.
5. **Cooldown curve.** At the top, rear wheel off the ground (or brake held), logging still running: `(therm-cooldown 40 60.0)`. Forty minutes of points is what separates the winding from the shell.
6. **Optional:** an IR thermometer on the hub shell (on a piece of matt tape) at a few of the same moments, to check `Shell M1`.
7. **Fit.** `python3 tools/fit_thermal.py <logs of the day, in order> --r0 <R0 from therm-cal> --t0 <its temperature>`. It prints `setq` lines for the REPL and flags the constants the data said little about (those stay close to the starting estimates), plus a check prediction for 10 min at 60 A. Put the values in the defs, and once the model tracks the measurements within about 5 K, consider `(setq therm-meas-correct 1)`.

Tested on synthetic data built from the 2026-11-04 climb (two climbs, 50 points, 2 K noise, deliberately different true constants): fitted to 1.8 K RMS; for 10 min at 60 A it predicts 146 °C against a true 140 °C (starting constants: 150 °C).

Untested on hardware. If the LDR is fitted later, uncomment the marked parts and calibrate the thresholds with `(get-adc 2)` in the REPL.

### Battery % by charge counting

The firmware's battery % comes from the pack voltage, which sags under load: on 2026-11-04 it read 51 % at the hardest part of the climb and 79 % at rest minutes later. The script counts charge through **both** motors instead (the firmware counters `cnt_ah`/`cnt_wh` in the log are the rear motor only, about half the real use), plus 0.08 A for the light box, Dash and controller, against `si_battery_ah` (27.5 Ah). The Dash battery % now shows this value.

- Anchors: at power-on the stored value is used unless the resting voltage says the pack was charged (more than 5 % higher) or the two disagree by more than 10 %; charging while switched on is followed; after 20 min standing still the count meets the resting voltage halfway.
- Stored in eeprom 102 at stops and at power-off. Range estimate (`Range` in the log) from this ride's Wh/km blended into a long-term value (eeprom 103, starting at 30 Wh/km).
- Replayed over the 2026-11-04 logs: 100 % → 70.6 % over the day, within 1.5 % of the resting voltage at every ride start (71.4 % at the end). Real use that day: 25 Wh/km on the descent, 36 Wh/km on the climb, both motors.
- Tuning: `soc-idle-a`, `soc-cap-ah` (set from the motor config), and the resting-voltage curve `soc-ocv-v`/`soc-ocv-s` (generic NMC, 0 % at the 3.4 V cutoff).

### Regen ABS

The brake is a switch, so the ADC app always asks for the full brake current. On 2026-11-04 at 05:36 the rear wheel locked for about 0.7 s at 10–15 km/h (0 rpm at −17.8 A while the front and the GPS read 10 → 6 km/h).

With the brake pulled and the faster wheel above 8 km/h, a wheel that is slower than the other by more than 25 % (and 0.8 m/s), or decelerates harder than 15 m/s², counts as slipping. The script then takes over braking from the ADC app (`app-disable-output` for 30 ms, renewed every 10 ms, so it lapses by itself if the thread stops), drops that motor to 20 % of its brake current, and ramps it back at 4× per second once the wheel has caught up; the other wheel keeps full braking. After 1.5 s it gives up and normal braking returns, so a faulty speed signal cannot take a wheel's brake away for longer.

Replayed over the 2026-11-04 logs it triggers once: the rear lock above. Brake onset differences of up to 1.9 km/h (the front brakes slightly first) stay well below the thresholds. Log fields: `ABS`, `ABS k M1`, `ABS k M2` (brake fraction). Off with `(setq abs-enable 0)`.

Test first with both wheels in the air: spin up, pull the brake. A free wheel stops far faster than 15 m/s², so `ABS` should go to 1 briefly. Then on a quiet, loose surface at low speed before trusting it in traffic.

## Display: motorcycle-style view (`display/`)

`display/dash35b-moto/` is the Dash35B 2.4 package (from vedderb/vesc_pkg) with a full-screen view in the style of a motorcycle TFT (`views/view_moto.lbm`), new fonts (Roboto Bold, Inter ExtraBold Italic for the speed) and settings in `config.lisp` (`config-moto-*`). `display/dash35b-moto.vescpkg` is the built package; `display/moto_view_renders.png` shows the view rendered by the LispBM REPL with the real drawing code.

- Install: VESC Tool, connect, select the display on the CAN bus, VESC Packages → Load Custom → choose the .vescpkg → Install.
- Rebuild without VESC Tool: `python3 build_pkg.py <package dir> <vesc_pkg>/lib_code_server/code_server.lisp dash35b-moto.vescpkg`.
- Clock: GPS time seen by the display, or UTC from the controller on CAN id 204 (sent by `lisp/dash_esc_lights.lisp`), with UTC+2 and Israeli summer time.
- Motor temperature shows the winding model from the controller script; with the older script it shows `--`.
- Top bar (2.4-moto3): average Wh/km of the ride instead of the slope marker. The IMU pitch and roll did not follow the road grade on 2026-11-04 (correlation about 0.15 against GPS altitude over 95 stretches; pitch −27° at rest), so the slope could not be shown.
- Reverse removed from the display (2.4-moto2): drive mode down stops at N. Reverse did nothing anyway (reverse current 0 in Dash ESC).

## Status

Working: both motors, throttle, regen brake, drive modes (Dash ESC), cruise control, headlight + tail light, aux front light, GPS logging.

## Known issues / to do

- Controller now runs the current `lisp/dash_esc_lights.lisp` and the display runs 2.4-moto3 (installed with vesc_cli on 2026-11-07). Before riding: ABS check with both wheels in the air, rear stick test, slow test ride.

- Field weakening: 20 A at 85% duty start made the rear motor keep driving after the throttle was released (wheels in the air). 10 A at 92% (Nov 3) works: rear id −10 A and +11 to +18 A motor current at top speed instead of −2 to −4 A drag, no torque after releasing the throttle, top speed 57 km/h (GPS). Now testing 15 A, with the front battery current raised to 40 A because the front was at its 35 A limit at top speed. Repeat the stick test with the wheel in the air before riding.
- Front motor round-connector pinout not yet documented.
- Brake light does not light up, with either a flashing or a steady signal on the light box yellow input. It most likely did not work with the original controller either, so the rear light itself (or its wiring) is suspected. Next test: 1 kΩ from rear pin 2 to pin 4 (6 V), then to pin 3 (GND).
- Motor temperature model and rear resistance measurement written but untested on hardware (see "Motor winding temperature").
- Optional: wheelie control (IMU, relative pitch) as a LispBM addition.
- Charge counting and regen ABS written but untested on hardware.
- Parked alarm / immobiliser tried and removed (2026-11-04): the motors' handbrake did not hold the wheels. A mechanical lock is the better answer; an LTE tracker may come with the modem.
- Motorcycle display view: rendered and checked in the LispBM REPL, not yet tested on the Dash 35B.
