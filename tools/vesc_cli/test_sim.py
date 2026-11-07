#!/usr/bin/env python3
"""Simulated scooter for testing vesc_cli without hardware.

Acts like the Express on Wi-Fi (TCP), with the Duet's two motors (CAN 48, 49)
and the display (CAN 4) behind it. Configs start from the repo XML files,
encoded with the firmware 7.00 definitions. Run the tests with:
    python3 test_sim.py
"""
import os, socket, struct, subprocess, sys, tempfile, threading, time, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vesc_cli as V

REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
FW = '7.00'
MDEF = V.ConfigDef(os.path.join(HERE, 'config', FW, 'parameters_mcconf.xml'))
ADEF = V.ConfigDef(os.path.join(HERE, 'config', FW, 'parameters_appconf.xml'))


def load_conf(d, kind, path):
    vals = V.xml_to_values(kind, path, d)
    for k in d.order:
        vals.setdefault(k, '' if d.params[k]['type'] == V.CFG_T_QSTRING else 0)
    return d.encode(vals)


class Node:
    def __init__(self, hw, hw_type, mc=None, erpm=0.0):
        self.hw, self.hw_type, self.mc, self.erpm = hw, hw_type, mc, erpm
        self.code = {'lisp': bytearray(), 'qml': bytearray()}
        self.running = False


class Sim:
    def __init__(self):
        self.nodes = {
            None: Node('VESC Express T', 2),
            48: Node('Duet', 0, load_conf(MDEF, 'mcconf', os.path.join(REPO, 'config/current/mcconf_rear_ID48.xml'))),
            49: Node('Duet', 0, load_conf(MDEF, 'mcconf', os.path.join(REPO, 'config/current/mcconf_front_ID49.xml'))),
            4: Node('VDisp 900', 2),
        }
        self.app = load_conf(ADEF, 'appconf', os.path.join(REPO, 'config/current/appconf_ID48.xml'))
        self.files = {'': [(True, 0, 'log')],
                      '/log': [(False, 3000, 'log_040_2026-11-07_09-00-00.csv'),
                               (False, 10, 'notes.txt'),
                               (False, 1200, 'log_041_2026-11-07_10-00-00.csv')]}
        self.content = {'/log/log_040_2026-11-07_09-00-00.csv': bytes((i * 7) % 251 for i in range(3000)),
                        '/log/log_041_2026-11-07_10-00-00.csv': b'x' * 1200}
        self.writes = []
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(('127.0.0.1', 0))
        self.srv.listen(5)
        self.port = self.srv.getsockname()[1]
        threading.Thread(target=self.accept, daemon=True).start()

    def accept(self):
        while True:
            c, _ = self.srv.accept()
            threading.Thread(target=self.serve, args=(c,), daemon=True).start()

    def serve(self, c):
        v = V.Vesc(None)
        v.t = type('T', (), {'read': lambda s: c.recv(4096), 'write': lambda s, b: c.sendall(b)})()
        c.settimeout(None)
        while True:
            try:
                p = v.recv(3600)
            except Exception:
                return
            if p is None:
                return
            nid = None
            if p[0] == V.COMM_FORWARD_CAN:
                nid, p = p[1], p[2:]
                if nid not in self.nodes:
                    continue
            for r in self.handle(nid, p):
                c.sendall(V.frame(r))

    def handle(self, nid, p):
        n = self.nodes[nid]
        cmd, d = p[0], p[1:]
        if cmd == V.COMM_FW_VERSION:
            maj, mi = map(int, FW.split('.'))
            yield bytes([cmd, maj, mi]) + n.hw.encode() + b'\0' + bytes(12) + bytes([0, 0, n.hw_type])
        elif cmd == V.COMM_PING_CAN and nid is None:
            yield bytes([cmd, 48, 49, 4])
        elif cmd == V.COMM_GET_VALUES and n.mc:
            yield bytes([cmd]) + struct.pack('>hhiiiihih', 250, 0, 0, 0, 0, 0, 0, int(n.erpm), 655)
        elif cmd == V.COMM_GET_MCCONF and n.mc:
            yield bytes([cmd]) + n.mc
        elif cmd == V.COMM_SET_MCCONF and n.mc:
            MDEF.decode(d)
            n.mc = bytes(d)
            self.writes.append(('mcconf', nid))
            yield bytes([cmd])
        elif cmd == V.COMM_GET_APPCONF and n.mc:
            yield bytes([cmd]) + self.app
        elif cmd == V.COMM_SET_APPCONF and n.mc:
            ADEF.decode(d)
            self.app = bytes(d)
            self.writes.append(('appconf', nid))
            yield bytes([cmd])
        elif cmd in (V.COMM_LISP_ERASE_CODE, V.COMM_QMLUI_ERASE):
            n.code['lisp' if cmd == V.COMM_LISP_ERASE_CODE else 'qml'] = bytearray()
            n.running = False
            yield bytes([cmd, 1])
        elif cmd in (V.COMM_LISP_WRITE_CODE, V.COMM_QMLUI_WRITE):
            off = struct.unpack('>I', d[:4])[0]
            buf = n.code['lisp' if cmd == V.COMM_LISP_WRITE_CODE else 'qml']
            if len(buf) < off:
                buf += bytes(off - len(buf))
            buf[off:off + len(d) - 4] = d[4:]
            yield bytes([cmd, 1]) + struct.pack('>I', off)
        elif cmd == V.COMM_LISP_SET_RUNNING:
            n.running = bool(d[0])
            yield bytes([cmd, 1])
        elif cmd == V.COMM_LISP_REPL_CMD:
            expr = d.rstrip(b'\0').decode()
            yield bytes([V.COMM_LISP_PRINT]) + (b'> 3' if expr == '(+ 1 2)' else b'> ' + expr.encode())
        elif cmd == V.COMM_FILE_LIST and nid is None:
            b = V.Buf(d)
            path, frm = b.string(), b.string()
            ents = self.files.get(path, [])
            names = [e[2] for e in ents]
            start = names.index(frm) + 1 if frm in names else 0
            page = ents[start:start + 2]
            out = bytes([cmd, 1 if start + 2 < len(ents) else 0])
            for isdir, size, name in page:
                out += bytes([isdir]) + struct.pack('>i', size) + name.encode() + b'\0'
            yield out
        elif cmd == V.COMM_FILE_READ and nid is None:
            b = V.Buf(d)
            path, off = b.string(), b.i32()
            data = self.content.get(path)
            if data is None:
                yield bytes([cmd]) + struct.pack('>ii', off, -1)
            else:
                yield bytes([cmd]) + struct.pack('>ii', off, len(data)) + data[off:off + 400]


def code_payload(buf):
    """Check header and CRC of an uploaded code area, return the data."""
    n, crc = struct.unpack('>IH', bytes(buf[:6]))
    data = bytes(buf[6:6 + n + 2])
    assert V.crc16(data) == crc, 'crc mismatch'
    return data


def run(sim, *args):
    cmd = [sys.executable, '-I', os.path.join(HERE, 'vesc_cli.py'), '--tcp', f'127.0.0.1:{sim.port}',
           '--backup-root', os.path.join(TMP, 'backups')] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout + r.stderr


def check(name, cond, out=''):
    print(('PASS ' if cond else 'FAIL ') + name)
    if not cond:
        print(out)
        global FAILS
        FAILS += 1


FAILS = 0
TMP = tempfile.mkdtemp()

if __name__ == '__main__':
    sim = Sim()

    rc, out = run(sim, 'info')
    check('info lists all nodes', rc == 0 and 'Duet' in out and 'VDisp 900' in out and 'fw 7.00' in out, out)

    rc, out = run(sim, 'values')
    check('values', rc == 0 and 'v_in 65.50' in out, out)

    rc, out = run(sim, 'backup')
    check('backup', rc == 0 and out.count('saved') == 3, out)

    # mcconf: change two values in a copy of the repo file
    src = open(os.path.join(REPO, 'config/current/mcconf_rear_ID48.xml')).read()
    mod = src.replace('<l_in_current_max>50</l_in_current_max>', '<l_in_current_max>52</l_in_current_max>') \
             .replace('<foc_fw_current_max>15</foc_fw_current_max>', '<foc_fw_current_max>18</foc_fw_current_max>')
    assert mod != src
    f = os.path.join(TMP, 'rear.xml')
    open(f, 'w').write(mod)
    rc, out = run(sim, 'mcconf', 'set', '48', f, '--dry-run')
    check('mcconf dry run shows exactly the two changes',
          rc == 0 and 'l_in_current_max: 50 -> 52' in out and 'foc_fw_current_max: 15 -> 18' in out
          and out.count(' -> ') == 2 and not sim.writes, out)
    rc, out = run(sim, 'mcconf', 'set', '48', f)
    check('mcconf write + read-back', rc == 0 and ('mcconf', 48) in sim.writes and 'READ-BACK' not in out, out)
    rc, out = run(sim, 'mcconf', 'get', '48', os.path.join(TMP, 'rb.xml'))
    rb = open(os.path.join(TMP, 'rb.xml')).read()
    check('mcconf read back has new values', '<l_in_current_max>52</l_in_current_max>' in rb
          and '<foc_fw_current_max>18</foc_fw_current_max>' in rb, rb[:300])
    check('front motor untouched', ('mcconf', 49) not in sim.writes)

    # appconf: same file as on the device -> nothing to write
    rc, out = run(sim, 'appconf', 'set', '48', os.path.join(REPO, 'config/current/appconf_ID48.xml'))
    check('appconf unchanged -> no write', rc == 0 and 'no differences' in out and ('appconf', 48) not in sim.writes, out)

    # standstill: a turning motor blocks writes
    sim.nodes[49].erpm = 3000
    rc, out = run(sim, 'mcconf', 'set', '48', os.path.join(REPO, 'config/current/mcconf_rear_ID48.xml'))
    check('write refused while a wheel turns', rc != 0 and 'standstill' in out, out)
    sim.nodes[49].erpm = 0

    # Lisp upload of the real script
    script = os.path.join(REPO, 'lisp/dash_esc_lights.lisp')
    rc, out = run(sim, 'lisp', 'upload', '--file', script)
    want = V.pack_lisp(script, os.path.join(HERE, 'lib'))
    got = code_payload(sim.nodes[48].code['lisp'])
    check('lisp upload: stored code identical, running, REPL answers',
          rc == 0 and got == want and sim.nodes[48].running and '> 3' in out, out)

    # Display package
    pkgf = os.path.join(REPO, 'display/dash35b-moto.vescpkg')
    rc, out = run(sim, 'pkg', pkgf)
    pkg = V.read_vescpkg(pkgf)
    disp = sim.nodes[4]
    lisp_ok = code_payload(disp.code['lisp']) == pkg['lispData']
    q = code_payload(disp.code['qml'])
    qml_ok = q[:2] == b'\0\1' and zlib.decompress(q[6:]).endswith(pkg['qmlFile'])
    check('package on display: lisp + qml identical, running', rc == 0 and lisp_ok and qml_ok and disp.running, out)
    check('package did not touch the motor controller', code_payload(sim.nodes[48].code['lisp']) == want)

    # Logs
    dest = os.path.join(TMP, 'logs')
    rc, out = run(sim, 'logs', 'pull', '--dest', dest)
    a = open(os.path.join(dest, 'log_040_2026-11-07_09-00-00.csv'), 'rb').read()
    check('logs pull: csv only, contents identical',
          rc == 0 and a == sim.content['/log/log_040_2026-11-07_09-00-00.csv']
          and not os.path.exists(os.path.join(dest, 'notes.txt')) and '2 log(s)' in out, out)
    rc, out = run(sim, 'logs', 'pull', '--dest', dest)
    check('logs pull again: nothing new', rc == 0 and '0 log(s)' in out, out)

    rc, out = run(sim, 'lisp', 'repl', '--expr', '(therm-test)')
    check('repl', rc == 0 and '(therm-test)' in out, out)

    print('\n%d failure(s)' % FAILS)
    sys.exit(1 if FAILS else 0)
