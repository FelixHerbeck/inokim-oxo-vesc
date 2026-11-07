---
name: scooter-vesc
description: Operate Felix's Inokim OXO VESC scooter (Duet + Express + Dash 35B) from Claude - pull logs, read/write motor and app configs, upload the Lisp script, install the display package, REPL, check the scooter matches GitHub. Use when asked to do anything on the scooter itself.
---

# Scooter VESC operations

The scooter is a VESC Labs Duet (motors on CAN 48 rear, 49 front, firmware 7.00) with its Express (Wi-Fi, GPS, logs) and a Dash 35B display (VDisp 900, CAN 4, firmware 6.06). Source of truth is the GitHub repo `FelixHerbeck/inokim-oxo-vesc` (configs in `config/current/`, script `lisp/dash_esc_lights.lisp`, display package `display/dash35b-moto.vescpkg`, tool `tools/vesc_cli/`).

## How the connection works

Claude's cloud shell and the laptop's Linux VM (`device_bash`) both cannot reach the home network (the VM proxy refuses private addresses). The tool therefore runs on **Windows**, through a runner:

- Laptop folder `C:\Users\fherb\workspace\scooter` = `$HOME/mnt/workspace/scooter` in `device_bash` (needs folder access to `~/workspace`; request it with `device_request_folder_access` if `ls $HOME/mnt/` does not show `workspace`).
- `vesc_runner.py` (Windows Python) watches `queue/` and runs only `vesc_cli.py` commands. It is alive when `queue/heartbeat.txt` holds a time within a few seconds of `date +%s`.
- If it is not running: computer use, resolve + request access for **File Explorer** (click tier), open File Explorer, navigate to the user folder (address-bar chevron, user name) > `workspace` > `scooter` and double-click `start_runner.bat`. Typing into terminals or Explorer is blocked by design; do not try to work around that. Starting the runner needs the user's go-ahead in the conversation.
- Submit commands from `device_bash`: `cd $HOME/mnt/workspace/scooter && ./q.sh <unique-name> <timeout-s> --tcp 192.168.1.155 <vesc_cli args>`. Output starts with `rc=`. Use a new unique name every call. `device_bash` calls cap at 180 s; keep each command shorter (a full log is ~80 s per 2.7 MB).
- The runner handles one command at a time, so the heartbeat lags while a command runs. If a `q.sh` call returns nothing, run it again with a new name before concluding anything.
- Express address: 192.168.1.155 (last seen). If it fails, `./q.sh scan$RANDOM 60 discover` (broadcast is blocked by the firewall; the tool falls back to a subnet scan).

## Keeping the laptop copies current

`./fetch_repo.sh` downloads the repo files (configs, script, display package, tool, runner scripts) from GitHub `main` into `repo/` and `vesc_cli/`. Run it after any push. Files can also be pushed from the cloud with `device_commit_files`, but that may hand back a cached older copy when the staged path is reused: stage under a new file name each time and verify with `sha1sum`/`grep`.

## Commands (vesc_cli)

Read-only, any time:
- `info` (all nodes, firmware), `values` (both motors: erpm, current, voltage, FET temperature)
- `backup` (both mcconfs + appconf to `vesc_cli/backups/<time>/`)
- `logs list`, `logs pull --dest ../scooter/logs [--match REGEX]` (only new .csv)
- `mcconf get 48 FILE`, `appconf get 48 FILE`, `mcconf set ... --dry-run`
- `lisp repl --id 48 --expr "(expr)" --wait 3` (controller), `--id 4` for the display; `lisp stats --id 48`; `lisp read --id 48 --file F`
- `./check_sync.sh` compares everything on the scooter with `repo/` and prints OK/DIFF per item.

Writes (refused unless both wheels are below 100 erpm; each prints the changes, backs up first, reads back):
- `mcconf set 48|49 repo/<file>.xml`, `appconf set 48 repo/appconf_ID48.xml` (always shared appconf through 48)
- `lisp upload --id 48 --file repo/dash_esc_lights.lisp` (reboots the controller by itself if the script does not answer afterwards)
- `pkg repo/dash35b-moto.vescpkg` (finds the display on CAN)
- `lisp reboot --id 48`, `lisp stop|start --id 48 --wait 10` (shows console output)

## Rules

- **Wheels-in-the-air guardrail.** Before sending any command that makes a motor turn or pushes current through it, stop and ask the user in chat to confirm that the scooter is set up for it (rear and/or front wheel off the ground as needed, or the brake held where the procedure allows it, and nobody near the wheels), and wait for an explicit yes. This covers REPL calls such as `(therm-test)`, `(therm-cal)`, `(therm-cooldown ...)`, `set-current`, `set-rpm`, `set-duty`, `set-brake`, `conf-measure-res`/`conf-measure-ind`, motor detection, and any ABS, stick or spin test. Name the wheel(s) and what will happen (e.g. "25 A through the stationary rear motor for 0.3 s, small jerk"). One confirmation covers one command or one clearly described test sequence; ask again for anything new. No confirmation, no command, even when working unattended.
- Before any write: `values` must show 0 erpm on both motors; say what will change; after the write run `./check_sync.sh` or the matching read-back.
- Do not write `foc_offsets_*` (calibration) or the drive-mode runtime limits (`l_current_max_scale`, `l_current_min_scale`, `l_min_erpm`, `l_max_erpm`); the tool skips them unless `--include-profile`.
- Temporary changes (for example auto power-off disabled: appconf `shutdown_mode` 2 instead of 7) must be noted in the repo README and restored afterwards with `appconf set 48 repo/appconf_ID48.xml`.
- Config changes the user asks for go into the repo files first (commit and push), then onto the scooter from `repo/` after `./fetch_repo.sh`, so GitHub stays the source of truth.
- A new Lisp script changes how the scooter rides: tell the user to do the wheels-in-the-air checks (ABS, rear stick test) before riding.

## Known quirks

- Firmware 7.00: after replacing a running script the Lisp evaluator can stay wedged (REPL silent, `:ctxs` shows `main-u` stuck) until the controller reboots.
- The controller's `gnss-date-time` is all zeros without a GPS fix (indoors), so the display clock shows `--:--`.
- Log analysis of pulled logs: stage them into the container with `device_stage_files` and run the usual per-log summary (speed vs GPS, currents, field weakening, voltage sag, heat model).
