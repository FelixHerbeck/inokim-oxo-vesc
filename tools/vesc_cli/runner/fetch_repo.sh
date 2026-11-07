#!/bin/bash
# Refresh ./repo and ./vesc_cli from GitHub (main), without git.
cd "$(dirname "$0")"
R=https://raw.githubusercontent.com/FelixHerbeck/inokim-oxo-vesc/main
get() { mkdir -p "$(dirname "$2")"; curl -fsSL "$R/$1" -o "$2.tmp" && mv "$2.tmp" "$2" && echo "got $1"; }
get config/current/mcconf_rear_ID48.xml repo/mcconf_rear_ID48.xml
get config/current/mcconf_front_ID49.xml repo/mcconf_front_ID49.xml
get config/current/appconf_ID48.xml repo/appconf_ID48.xml
get lisp/dash_esc_lights.lisp repo/dash_esc_lights.lisp
get display/dash35b-moto.vescpkg repo/dash35b-moto.vescpkg
get tools/vesc_cli/vesc_cli.py vesc_cli/vesc_cli.py
get tools/vesc_cli/lib/code_server.lisp vesc_cli/lib/code_server.lisp
for f in q.sh check_sync.sh fetch_repo.sh vesc_runner.py start_runner.bat; do get tools/vesc_cli/runner/$f $f; done
chmod +x *.sh
