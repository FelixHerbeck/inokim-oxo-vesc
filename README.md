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
| Battery current max / regen | 50 A / −12 A | 35 A / −6 A (total 85 A) |
| Absolute max current | 150 A | 150 A |
| Battery cutoff start / end | 54.4 / 49.6 V | 54.4 / 49.6 V |
| Regen voltage cutoff start / end | 67.0 / 67.6 V | 67.0 / 67.6 V |
| Motor temp sensor | Disabled | Disabled |
| Temp compensation | Off | Off |
| Field weakening | 10 A, duty start 92%, ramp 0.2 s (testing) | 0 A (off) |
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

Untested on hardware. If the LDR is fitted later, uncomment the marked parts and calibrate the thresholds with `(get-adc 2)` in the REPL.

## Status

Working: both motors, throttle, regen brake, drive modes (Dash ESC), cruise control, headlight + tail light, aux front light, GPS logging.

## Known issues / to do

- Field weakening: 20 A at 85% duty start made the rear motor keep driving after the throttle was released (wheels in the air). Now testing 10 A at 92%; first ride showed the rear at 95% duty and about −2 A (slight drag) at top speed. Repeat the stick test with the wheel in the air before riding.
- Front motor round-connector pinout not yet documented.
- Brake light does not light up, with either a flashing or a steady signal on the light box yellow input. It most likely did not work with the original controller either, so the rear light itself (or its wiring) is suspected. Next test: 1 kΩ from rear pin 2 to pin 4 (6 V), then to pin 3 (GND).
- Optional: wheelie control (IMU, relative pitch) and regen ABS as LispBM additions.
