#!/bin/bash
# usage: q.sh name timeout_s args...   (submits to the Windows runner, waits for output)
n=$1; t=$2; shift 2
python3 -c 'import json,sys; json.dump({"args":sys.argv[2:]}, open(sys.argv[1],"w"))' queue/$n.json.tmp "$@"
mv queue/$n.json.tmp queue/$n.json
for i in $(seq 1 $((t*2))); do [ -f queue/$n.out.txt ] && { cat queue/$n.out.txt; exit 0; }; sleep 0.5; done
echo "TIMEOUT waiting for $n"
