"""Runs vesc_cli commands that Claude drops into the queue folder.

Start it once in a terminal on this computer:   python vesc_runner.py
Stop it with Ctrl+C. It only ever runs vesc_cli.py, with arguments from
queue/*.json files ({"args": [...]}), and writes queue/<name>.out.txt.
"""
import json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
Q = os.path.join(HERE, 'queue')
CLI = os.path.join(HERE, 'vesc_cli', 'vesc_cli.py')
ALLOWED = {'reboot', 'discover', 'info', 'values', 'logs', 'mcconf', 'appconf', 'backup', 'lisp', 'pkg'}
os.makedirs(Q, exist_ok=True)
print('vesc_runner: waiting for commands in', Q)
while True:
    with open(os.path.join(Q, 'heartbeat.txt'), 'w') as f:
        f.write(str(time.time()))
    for name in sorted(os.listdir(Q)):
        if not name.endswith('.json'):
            continue
        p = os.path.join(Q, name)
        out = p[:-5] + '.out.txt'
        try:
            args = [str(a) for a in json.load(open(p))['args']]
            sub = next((a for a in args if not a.startswith('-')), None)
            # allow options before the subcommand (e.g. --tcp HOST)
            if not any(a in ALLOWED for a in args):
                raise ValueError('not a vesc_cli command')
            print('running:', ' '.join(args))
            r = subprocess.run([sys.executable, CLI] + args, cwd=HERE, capture_output=True,
                               text=True, timeout=900)
            res = f'rc={r.returncode}\n{r.stdout}{r.stderr}'
        except Exception as e:
            res = f'rc=-1\nrunner error: {e}'
        with open(out + '.tmp', 'w') as f:
            f.write(res)
        os.replace(out + '.tmp', out)
        os.replace(p, p + '.done')
        print(res.splitlines()[0])
    time.sleep(0.5)
