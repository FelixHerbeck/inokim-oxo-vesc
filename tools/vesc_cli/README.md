# vesc_cli

Command-line access to the scooter's VESC setup (Duet motors 48/49, the Express with the GPS and logs, the Dash 35B display), for everything VESC Tool is used for here: logs, motor and app configuration, the Lisp script, the display package and the Lisp REPL. Python 3 standard library; `pyserial` only for USB.

The protocol follows the VESC firmware (vedderb/bldc), the Express firmware (vedderb/vesc_express) and VESC Tool (vedderb/vesc_tool). `config/<fw>/` holds VESC Tool's parameter definitions for firmware 6.05–7.01; the scooter runs 7.00.

## Connecting

- **Wi-Fi:** the Express in station mode on the home network. Without options the tool listens for its broadcast (UDP 65109) and connects on TCP 65102. `--tcp 192.168.1.50` connects directly.
- **USB:** `--serial COM5` (Windows) or `--serial /dev/ttyACM0`. Without options, USB is tried when no Wi-Fi broadcast is seen.

Motor 1 is CAN 48 and motor 2 is CAN 49 (`--esc-id`, `--m2-id`). Over Wi-Fi everything on the motors is forwarded over CAN; over USB the STM32 is local.

## Commands

```
python vesc_cli.py discover                       # Express devices on Wi-Fi
python vesc_cli.py info                           # every node: hardware, firmware
python vesc_cli.py values                         # live values of both motors
python vesc_cli.py logs list
python vesc_cli.py logs pull --dest logs          # new .csv logs only (--all to re-download)
python vesc_cli.py backup                         # both mcconfs + appconf to backups/<time>/
python vesc_cli.py mcconf get 48 rear.xml
python vesc_cli.py mcconf set 48 ../../config/current/mcconf_rear_ID48.xml --dry-run
python vesc_cli.py mcconf set 48 ../../config/current/mcconf_rear_ID48.xml
python vesc_cli.py appconf set 48 ../../config/current/appconf_ID48.xml
python vesc_cli.py lisp upload --file ../../lisp/dash_esc_lights.lisp
python vesc_cli.py lisp repl --expr "(therm-test)" --wait 3
python vesc_cli.py lisp stop | start
python vesc_cli.py pkg ../../display/dash35b-moto.vescpkg   # finds the display on CAN
```

## Safety

- Writes (configs, Lisp, packages) only when both motors are below 100 erpm; `--force` skips the check.
- `mcconf set`/`appconf set` read the device first, change only what differs from the file, print every change, save the device's config before and after in `backups/<time>/`, and read back afterwards.
- Current/voltage offset calibration (`foc_offsets_*`) is never taken from a file.
- The config signature must match one of the parameter definitions, otherwise nothing is decoded or written.

## Tests

`python test_sim.py` runs every command against a simulated Express + Duet + display: config dry run, write and read-back, standstill refusal, Lisp upload of the real script, display package install, log download. The config encoding was also checked against the firmware's own deserializer (bldc `confgenerator.c`, compiled on a PC): byte-identical round trips for the rear mcconf and the appconf, and signatures equal to the firmware's `MCCONF_SIGNATURE`/`APPCONF_SIGNATURE` for 7.01. Not yet run against the real scooter.
