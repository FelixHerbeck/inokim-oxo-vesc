#!/bin/bash
# Compare everything stored on the scooter with the repo copies in ./repo.
# usage: check_sync.sh [HOST]      (runs through the Windows runner via q.sh)
cd "$(dirname "$0")"
mkdir -p sync; S=sync/$(date +%s)
T="--tcp ${1:-192.168.1.155}"
ok=1
for x in "mcconf 48 repo/mcconf_rear_ID48.xml" "mcconf 49 repo/mcconf_front_ID49.xml" "appconf 48 repo/appconf_ID48.xml"; do
  set -- $x
  out=$(./q.sh sync$RANDOM 90 $T $1 set $2 $3 --dry-run)
  if echo "$out" | grep -q "no differences"; then echo "OK    $1 $2"; else ok=0; echo "DIFF  $1 $2:"; echo "$out" | grep -- " -> "; fi
done
./q.sh syncl48$RANDOM 175 $T lisp read --id 48 --file $S.48.bin >/dev/null
./q.sh syncl4$RANDOM 175 $T lisp read --id 4 --file $S.4.bin >/dev/null
S=$S python3 - <<'PY' || ok=0
import os, sys; sys.path.insert(0, 'vesc_cli'); import vesc_cli as V
want = V.pack_lisp('repo/dash_esc_lights.lisp', 'vesc_cli/lib')[2:]
pkg = V.read_vescpkg('repo/dash35b-moto.vescpkg')['lispData'][2:]
a = open(os.environ['S'] + '.48.bin', 'rb').read() == want
b = open(os.environ['S'] + '.4.bin', 'rb').read() == pkg
print(('OK   ' if a else 'DIFF ') + ' controller script (CAN 48)')
print(('OK   ' if b else 'DIFF ') + ' display package code (CAN 4)')
sys.exit(0 if a and b else 1)
PY
[ $ok = 1 ] && echo "ALL IN SYNC" || echo "NOT IN SYNC"
