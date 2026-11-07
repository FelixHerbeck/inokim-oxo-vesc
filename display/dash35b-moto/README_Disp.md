# Dash35B

VESC Dash35B UI for single horizontal display with 480x320 resolution and four buttons on a cable.

**Note**  
Version 2.4 goes with Dash ESC 2.4. The drive mode, the status banners and the logging button all need it.

## Motorcycle view (2.4-moto3)

This build replaces the standard screen with a full-screen view in the style of a motorcycle TFT. It is on by default; set `config-moto-view` to `false` in config.lisp for the original views.

- Left: drive mode (green N in neutral), power arc filling from the bottom up to `config-moto-kw-max`, range, power in kW.
- Middle: CRUISE and LIGHT badges, motor temperature (red above the motor warning setting), trip.
- Top: average energy use of the ride in Wh/km (regen subtracted), as a marker on a bar centred on 30 Wh/km (triangles at 20 and 40) with the value below it. Shown after 0.3 km.
- Right: speed, battery scale with percentage, controller temperature (red above the controller warning setting) and clock.
- Clock: GPS time (UTC) seen by the display, or UTC sent by the controller on CAN id 204, plus `config-moto-utc-offset` and Israeli summer time with `config-moto-dst-israel`. Shows --:-- without a time source.
- Reverse removed: drive mode down stops at N, and a mode beyond the configured number falls back to N instead of R.
- The on-display settings page and the other pages are not shown in this view; the settings are on the package page in VESC Tool. Drive mode, lights, cruise and logging buttons work as before.


Settings are on the package page and stored in eeprom, applied without a reinstall. The Editing selector at the top picks one section at a time.

**Live page**  
Four readings, two by two, each from one of 18 sources, with its own colour or a green to red ramp across a range.

**Display**  
Accent and text colour, boot splash, status strip icons and the battery bar colour.

**Pages**  
Which pages button 0 cycles through, and how many drive modes.

**Hardware**  
Units, warning thresholds, backlight and the controller mode.

**Buttons**  
Short and long press actions for all four buttons. Short presses are overridden while the on-display settings page is open so it can always be navigated. One of the actions starts and stops logging on the controller.

config.lisp still holds the defaults, written on a fresh install or when the settings version changes.

Drive mode values live in dash_esc. The display sends the mode and the controller applies it.

## Running without dash_esc

If no dash_esc frame arrives for three seconds the display reads the standard CAN status frames directly. Speed, duty, voltage, input current and both temperatures still work, and a VESC BMS is read for charge and the cell page. Watt hours, amp hours, odometer, range, efficiency, fault names, pitch, cruise, turn signals, high beam and kickstand are not in any status frame. Trip becomes distance since the controller booted.

Drive modes need dash_esc.

## Status banners

The display shows a banner across the middle when the controller reports something that makes what is on the rest of the screen misleading.

**SERVICE** means drive profiles are suspended on the controller. The mode shown means nothing while that is set, and neutral is not holding the throttle shut.

**MOTOR CONFIG BAD** means the controller's stored motor parameters cannot describe a real motor, so it will not run at all. The controller suspends its drive profile by itself in that state so the motor can be detected again.

## Changelog

**Version 2.4 (2026-09-13)**
* Drive mode follows the controller, so two displays always agree on it
* Button action to start and stop logging on the controller
* Banner while the controller has drive profiles suspended, or while its motor configuration cannot describe a real motor

**Version 2.3 (2026-09-10)**
* Load settings correctly on boot
* Fix bug where some values are shown as 0
* Show all settings when opening them the first time

**Version 2.1 (2026-09-04)**
* Settings page, stored in eeprom and applied without a reinstall
* Live page with four configurable readings
* Unit selection now converts speed, distance, efficiency and temperature
* Configurable status strip icons and colours
* Boot splash
* Read standard CAN status frames when dash_esc is absent
* Configurable button actions
* Backlight range corrected to 1-7

**Version 1.0 (2025-09-17)**

* Initial Release

