#!/usr/bin/env python3
"""vesc_cli: command-line access to a VESC setup (Duet + Express + display).

Everything VESC Tool is used for on this scooter, without the GUI:
logs, motor and app configuration, the Lisp script, display packages and the
Lisp REPL. The protocol follows the VESC firmware (vedderb/bldc) and VESC Tool
(vedderb/vesc_tool) sources.

Connection:  --tcp HOST[:PORT]   (Express on Wi-Fi, port 65102)
             --serial PORT       (USB, e.g. COM5 or /dev/ttyACM0; needs pyserial)
             neither: listen for the Express Wi-Fi broadcast, then try USB.

Writes (configs, scripts, packages) only happen at standstill, always save a
backup of what is on the device first, and are read back afterwards.

Run `vesc_cli.py -h` and `vesc_cli.py <command> -h` for the commands.
Standard library only, plus pyserial for USB.
"""
import argparse, datetime, glob, math, os, re, socket, struct, sys, time, zlib
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- protocol ids
COMM_FW_VERSION = 0
COMM_GET_VALUES = 4
COMM_SET_MCCONF = 13
COMM_GET_MCCONF = 14
COMM_SET_APPCONF = 16
COMM_GET_APPCONF = 17
COMM_REBOOT = 29
COMM_FORWARD_CAN = 34
COMM_PING_CAN = 62
COMM_QMLUI_ERASE = 120
COMM_QMLUI_WRITE = 121
COMM_LISP_READ_CODE = 130
COMM_LISP_WRITE_CODE = 131
COMM_LISP_ERASE_CODE = 132
COMM_LISP_SET_RUNNING = 133
COMM_LISP_GET_STATS = 134
COMM_LISP_PRINT = 135
COMM_LISP_REPL_CMD = 138
COMM_FILE_LIST = 140
COMM_FILE_READ = 141

HW_TYPES = {0: 'VESC', 1: 'VESC BMS', 2: 'Custom module'}


class VescError(Exception):
    pass


# --------------------------------------------------------------- byte helpers
def crc16(data):
    """CRC-16/XMODEM, as util/crc.c in the firmware."""
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def crc32c(data):
    """Utility::crc32c in VESC Tool, used for the config signatures."""
    crc = 0xFFFFFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82F63B78 if crc & 1 else 0)
    return (~crc) & 0xFFFFFFFF


def frame(payload):
    n = len(payload)
    if n <= 255:
        head = bytes([2, n])
    elif n <= 65535:
        head = bytes([3]) + struct.pack('>H', n)
    else:
        head = bytes([4]) + struct.pack('>I', n)[1:]
    return head + payload + struct.pack('>H', crc16(payload)) + b'\x03'


class Buf:
    """Big-endian reader, like VByteArray::vbPopFront*."""
    def __init__(self, data):
        self.d = bytes(data)
        self.i = 0

    def left(self):
        return len(self.d) - self.i

    def take(self, n):
        if self.i + n > len(self.d):
            raise VescError('short packet')
        b = self.d[self.i:self.i + n]
        self.i += n
        return b

    def u8(self): return self.take(1)[0]
    def i8(self): return struct.unpack('>b', self.take(1))[0]
    def u16(self): return struct.unpack('>H', self.take(2))[0]
    def i16(self): return struct.unpack('>h', self.take(2))[0]
    def u32(self): return struct.unpack('>I', self.take(4))[0]
    def i32(self): return struct.unpack('>i', self.take(4))[0]

    def string(self):
        j = self.d.index(b'\0', self.i)
        s = self.d[self.i:j].decode('utf-8', 'replace')
        self.i = j + 1
        return s

    def f16(self, scale): return self.i16() / scale
    def f32(self, scale): return self.i32() / scale

    def f32auto(self):
        res = self.u32()
        e = (res >> 23) & 0xFF
        sig_i = res & 0x7FFFFF
        neg = res & (1 << 31)
        sig = 0.0
        if e != 0 or sig_i != 0:
            sig = sig_i / (8388608.0 * 2.0) + 0.5
            e -= 126
        if neg:
            sig = -sig
        return math.ldexp(sig, e)


def f32auto_bytes(x):
    """VByteArray::vbAppendDouble32Auto"""
    if abs(x) < 1.5e-38:
        x = 0.0
    fr, e = math.frexp(x)
    fr = struct.unpack('>f', struct.pack('>f', fr))[0]   # float precision, like frexpf
    fr_abs = abs(fr)
    fr_s = 0
    if fr_abs >= 0.5:
        fr_s = int((fr_abs - 0.5) * 2.0 * 8388608.0)
        e += 126
    res = ((e & 0xFF) << 23) | (fr_s & 0x7FFFFF)
    if fr < 0:
        res |= 1 << 31
    return struct.pack('>I', res)


def round_half_away(x):
    return int(math.floor(x + 0.5)) if x >= 0 else -int(math.floor(-x + 0.5))


# ------------------------------------------------------------------ transport
class TcpTransport:
    def __init__(self, host, port=65102):
        self.desc = f'tcp {host}:{port}'
        self.s = socket.create_connection((host, port), timeout=5)
        self.s.settimeout(0.05)

    def write(self, b):
        self.s.sendall(b)

    def read(self):
        try:
            d = self.s.recv(4096)
            if d == b'':
                raise VescError('connection closed')
            return d
        except socket.timeout:
            return b''

    def close(self):
        self.s.close()


class SerialTransport:
    def __init__(self, port):
        try:
            import serial
        except ImportError:
            raise VescError('USB needs pyserial: python -m pip install pyserial')
        self.desc = f'serial {port}'
        self.s = serial.Serial(port, 115200, timeout=0.05)

    def write(self, b):
        self.s.write(b)

    def read(self):
        return self.s.read(4096)

    def close(self):
        self.s.close()


def discover(seconds=3.0):
    """Express on Wi-Fi broadcasts 'name::ip::port' on UDP 65109 once a second."""
    found = {}
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        u.bind(('', 65109))
    except OSError as e:
        print(f'cannot listen on UDP 65109: {e}', file=sys.stderr)
        return found
    u.settimeout(0.2)
    t_end = time.time() + seconds
    while time.time() < t_end:
        try:
            d, addr = u.recvfrom(512)
        except socket.timeout:
            continue
        tok = d.decode('utf-8', 'replace').strip('\0 \r\n').split('::')
        if len(tok) == 3:
            found[tok[1]] = (tok[0], tok[1], int(tok[2]))
    u.close()
    return found


def scan_subnet(port=65102, timeout=0.4):
    """Fallback when the broadcast is blocked (e.g. by a firewall): try TCP 65102
    on every address of the local /24 and keep those that answer as a VESC."""
    import concurrent.futures
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))       # no packet is sent; picks the LAN interface
        me = s.getsockname()[0]
    finally:
        s.close()
    base = me.rsplit('.', 1)[0]

    def probe(ip):
        try:
            c = socket.create_connection((ip, port), timeout=timeout)
        except OSError:
            return None
        try:
            c.settimeout(1.0)
            c.sendall(frame(bytes([COMM_FW_VERSION])))
            v = Vesc(None)
            def rd(self):
                try:
                    return c.recv(4096)
                except socket.timeout:
                    return b''
            v.t = type('T', (), {'read': rd})()
            p = v.recv(1.5)
            if p and p[0] == COMM_FW_VERSION:
                b = Buf(p[1:])
                b.u8(); b.u8()
                return ip, b.string()
        except (OSError, VescError, ValueError):
            pass
        finally:
            c.close()
        return None

    found = {}
    with concurrent.futures.ThreadPoolExecutor(64) as ex:
        for r in ex.map(probe, [f'{base}.{i}' for i in range(1, 255) if f'{base}.{i}' != me]):
            if r:
                found[r[0]] = (r[1], r[0], port)
    return found


def serial_candidates():
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    res = []
    for p in list_ports.comports():
        txt = f'{p.description} {p.manufacturer} {p.product}'.lower()
        if p.vid == 0x0483 or 'stm' in txt or 'vesc' in txt or 'chibios' in txt:
            res.append(p.device)
    return res


# ----------------------------------------------------------------- connection
class Vesc:
    def __init__(self, transport, verbose=False):
        self.t = transport
        self.rx = bytearray()
        self.verbose = verbose
        self.prints = []          # COMM_LISP_PRINT text received
        self.local_id = None      # CAN id of the device we are connected to, if a motor controller

    def close(self):
        self.t.close()

    def send(self, payload, can_id=None):
        if can_id is not None:
            payload = bytes([COMM_FORWARD_CAN, can_id & 0xFF]) + payload
        self.t.write(frame(payload))

    def _parse(self):
        """Return one decoded packet from self.rx, or None."""
        while self.rx:
            st = self.rx[0]
            if st not in (2, 3, 4):
                del self.rx[0]
                continue
            hl = {2: 1, 3: 2, 4: 3}[st]
            if len(self.rx) < 1 + hl:
                return None
            n = int.from_bytes(self.rx[1:1 + hl], 'big')
            if n == 0 or n > 1 << 20:
                del self.rx[0]
                continue
            total = 1 + hl + n + 3
            if len(self.rx) < total:
                return None
            pl = bytes(self.rx[1 + hl:1 + hl + n])
            crc = int.from_bytes(self.rx[1 + hl + n:1 + hl + n + 2], 'big')
            if self.rx[total - 1] != 3 or crc != crc16(pl):
                del self.rx[0]
                continue
            del self.rx[:total]
            return pl
        return None

    def recv(self, timeout):
        t_end = time.time() + timeout
        while True:
            p = self._parse()
            if p is not None:
                return p
            if time.time() > t_end:
                return None
            self.rx += self.t.read()

    def request(self, payload, expect, can_id=None, timeout=1.5, retries=2, match=None):
        """Send and wait for a reply starting with command byte `expect`."""
        for attempt in range(retries + 1):
            self.send(payload, can_id)
            t_end = time.time() + timeout
            while time.time() < t_end:
                p = self.recv(t_end - time.time())
                if p is None:
                    break
                if p[0] == COMM_LISP_PRINT:
                    self.prints.append(p[1:].decode('latin-1'))
                    continue
                if p[0] == expect and (match is None or match(p)):
                    return p[1:]
        raise VescError(f'no reply to command {payload[0]}' + (f' via CAN {can_id}' if can_id is not None else ''))

    # -------- target: forward unless the id is the device we are plugged into
    def tgt(self, can_id):
        if can_id is None or can_id == self.local_id:
            return None
        return can_id

    def fw_version(self, can_id=None):
        b = Buf(self.request(bytes([COMM_FW_VERSION]), COMM_FW_VERSION, self.tgt(can_id)))
        info = {'major': b.u8(), 'minor': b.u8(), 'hw': b.string()}
        try:
            info['uuid'] = b.take(12).hex()
            info['paired'] = b.u8()
            info['test'] = b.u8()
            info['hw_type'] = HW_TYPES.get(b.u8(), '?')
        except (VescError, ValueError):
            pass
        info['fw'] = f"{info['major']}.{info['minor']:02d}"
        return info

    def ping_can(self):
        d = self.request(bytes([COMM_PING_CAN]), COMM_PING_CAN, timeout=3.0, retries=1)
        return list(d)

    def values(self, can_id=None):
        b = Buf(self.request(bytes([COMM_GET_VALUES]), COMM_GET_VALUES, self.tgt(can_id)))
        return {'temp_fet': b.f16(10), 'temp_motor': b.f16(10), 'current': b.f32(100),
                'current_in': b.f32(100), 'id': b.f32(100), 'iq': b.f32(100),
                'duty': b.f16(1000), 'erpm': b.f32(1), 'v_in': b.f16(10)}

    def repl(self, can_id, expr, wait=1.5):
        self.prints = []
        self.send(bytes([COMM_LISP_REPL_CMD]) + expr.encode() + b'\0', self.tgt(can_id))
        t_end = time.time() + wait
        while time.time() < t_end:
            p = self.recv(t_end - time.time())
            if p is not None and p[0] == COMM_LISP_PRINT:
                self.prints.append(p[1:].decode('latin-1'))
        return '\n'.join(self.prints)


def connect(args):
    if args.tcp:
        host, _, port = args.tcp.partition(':')
        tr = TcpTransport(host, int(port or 65102))
    elif args.serial:
        tr = SerialTransport(args.serial)
    else:
        found = discover(3.0)
        if not found:
            print('no Wi-Fi broadcast seen, scanning the local network for port 65102...', file=sys.stderr)
            found = scan_subnet()
        if found:
            name, ip, port = sorted(found.values())[0]
            print(f'found {name} at {ip}:{port}', file=sys.stderr)
            tr = TcpTransport(ip, port)
        else:
            ports = serial_candidates()
            if not ports:
                raise VescError('nothing found: no Wi-Fi broadcast and no USB port; use --tcp or --serial')
            tr = SerialTransport(ports[0])
    v = Vesc(tr, args.verbose)
    # Work out what we are plugged into: a motor controller (USB to the Duet's
    # STM32) answers as hardware type VESC; the Express (Wi-Fi) as a custom module.
    local = v.fw_version(None)
    if local.get('hw_type') == 'VESC':
        v.local_id = args.esc_id
    try:
        others = v.ping_can()
    except VescError:
        others = []
    v.can_ids = [c for c in others if c != v.local_id]
    print(f'connected ({tr.desc}); CAN nodes seen: {others}; local: '
          f'{"motor controller " + str(v.local_id) if v.local_id is not None else "not a motor (Express or display)"}',
          file=sys.stderr)
    return v


# ------------------------------------------------------------- configurations
CFG_T_DOUBLE, CFG_T_INT, CFG_T_QSTRING, CFG_T_ENUM, CFG_T_BOOL, CFG_T_BITFIELD = 1, 2, 3, 4, 5, 6
TX_UINT8, TX_INT8, TX_UINT16, TX_INT16, TX_UINT32, TX_INT32, TX_DOUBLE16, TX_DOUBLE32, TX_DOUBLE32_AUTO = range(1, 10)


class ConfigDef:
    """parameters_mcconf.xml / parameters_appconf.xml from VESC Tool."""
    def __init__(self, path):
        root = ET.parse(path).getroot()
        self.params = {}
        for p in root.find('Params'):
            g = lambda tag, d=None: p.find(tag).text if p.find(tag) is not None else d
            self.params[p.tag] = {
                'type': int(g('type', 0)),
                'vTx': int(g('vTx', 0)),
                'scale': float(g('vTxDoubleScale', 1)),
                'enum': [e.text or '' for e in p.findall('enumNames')],
            }
        self.order = [s.text for s in root.find('SerOrder')]
        self.signature = self._signature()

    def _signature(self):
        s = ''
        for name in self.order:
            s += name
            p = self.params.get(name)
            if p:
                s += str(p['type']) + str(p['vTx']) + ''.join(p['enum'])
        return crc32c(s.encode('utf-8'))

    def decode(self, data):
        b = Buf(data)
        sig = b.u32()
        if sig != self.signature:
            raise VescError(f'config signature {sig} does not match the definitions ({self.signature})')
        vals = {}
        for name in self.order:
            p = self.params[name]
            t, tx = p['type'], p['vTx']
            if t == CFG_T_DOUBLE:
                vals[name] = (b.f16(p['scale']) if tx == TX_DOUBLE16 else
                              b.f32(p['scale']) if tx == TX_DOUBLE32 else b.f32auto())
            elif t == CFG_T_INT:
                vals[name] = {TX_UINT8: b.u8, TX_INT8: b.i8, TX_UINT16: b.u16, TX_INT16: b.i16,
                              TX_UINT32: b.u32, TX_INT32: b.i32}[tx]()
            elif t == CFG_T_QSTRING:
                vals[name] = b.string()
            elif t in (CFG_T_ENUM, CFG_T_BOOL, CFG_T_BITFIELD):
                vals[name] = b.i8()
        return vals

    def encode(self, vals):
        out = bytearray(struct.pack('>I', self.signature))
        for name in self.order:
            p = self.params[name]
            t, tx, v = p['type'], p['vTx'], vals[name]
            if t == CFG_T_DOUBLE:
                if tx == TX_DOUBLE16:
                    out += struct.pack('>h', round_half_away(v * p['scale']))
                elif tx == TX_DOUBLE32:
                    out += struct.pack('>i', round_half_away(v * p['scale']))
                else:
                    out += f32auto_bytes(v)
            elif t == CFG_T_INT:
                fmt = {TX_UINT8: '>B', TX_INT8: '>b', TX_UINT16: '>H', TX_INT16: '>h',
                       TX_UINT32: '>I', TX_INT32: '>i'}[tx]
                out += struct.pack(fmt, int(v))
            elif t == CFG_T_QSTRING:
                out += str(v).encode('utf-8') + b'\0'
            elif t in (CFG_T_ENUM, CFG_T_BOOL, CFG_T_BITFIELD):
                out += struct.pack('>b', int(v))
        return bytes(out)

    def tolerance(self, name):
        p = self.params[name]
        if p['type'] != CFG_T_DOUBLE:
            return 0
        if p['vTx'] in (TX_DOUBLE16, TX_DOUBLE32):
            return 1.01 / p['scale']   # one step: the firmware truncates where VESC Tool rounds
        return None   # float32: relative


def find_def(kind, fw):
    """Definitions for this firmware version, or the nearest older one we have."""
    have = sorted(os.listdir(os.path.join(HERE, 'config')), key=lambda s: tuple(map(int, s.split('.'))))
    want = tuple(map(int, fw.split('.')))
    cands = [h for h in have if tuple(map(int, h.split('.'))) <= want] or have
    return [os.path.join(HERE, 'config', h, f'parameters_{kind}.xml') for h in reversed(cands)]


KINDS = {'mcconf': ('MCConfiguration', COMM_GET_MCCONF, COMM_SET_MCCONF),
         'appconf': ('APPConfiguration', COMM_GET_APPCONF, COMM_SET_APPCONF)}


def get_config(v, kind, can_id):
    """Read a configuration. Returns (definition, values)."""
    fw = v.fw_version(can_id)['fw']
    raw = v.request(bytes([KINDS[kind][1]]), KINDS[kind][1], v.tgt(can_id), timeout=2.0)
    sig = struct.unpack('>I', raw[:4])[0]
    for path in find_def(kind, fw):
        d = ConfigDef(path)
        if d.signature == sig:
            return d, d.decode(raw)
    raise VescError(f'no parameter definitions match {kind} signature {sig} (firmware {fw})')


def fmt_val(x):
    if isinstance(x, float):
        return f'{x:.6g}'    # QString::number(double) default
    return str(x)


def config_to_xml(kind, vals, path):
    root = ET.Element(KINDS[kind][0])
    ET.SubElement(root, 'ConfigVersion').text = '4'
    for k, x in vals.items():
        ET.SubElement(root, k).text = fmt_val(x)
    ET.indent(root, '    ')
    with open(path, 'wb') as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(ET.tostring(root, encoding='utf-8'))
        f.write(b'\n')


def xml_to_values(kind, path, d):
    root = ET.parse(path).getroot()
    if root.tag != KINDS[kind][0]:
        raise VescError(f'{path} is a {root.tag}, expected {KINDS[kind][0]}')
    vals = {}
    for e in root:
        if e.tag in d.params:
            t = d.params[e.tag]['type']
            txt = (e.text or '').strip()
            vals[e.tag] = (float(txt) if t == CFG_T_DOUBLE else txt if t == CFG_T_QSTRING else int(float(txt)))
    return vals


PROTECTED = ('foc_offsets_',)
PROFILE = ('l_current_max_scale', 'l_current_min_scale', 'l_min_erpm', 'l_max_erpm')


def differs(d, name, a, b):
    if isinstance(a, float) or isinstance(b, float):
        tol = d.tolerance(name)
        if tol is None:
            return abs(a - b) > 1e-6 * max(1.0, abs(a), abs(b))
        return abs(a - b) > tol
    return a != b


# ------------------------------------------------------------------- safety
def require_standstill(v, args):
    if args.force:
        print('WARNING: standstill check skipped (--force)', file=sys.stderr)
        return
    for cid in (args.esc_id, args.m2_id):
        try:
            erpm = v.values(cid)['erpm']
        except VescError as e:
            raise VescError(f'cannot read motor {cid} speed ({e}); refusing to write (use --force to override)')
        if abs(erpm) > 100:
            raise VescError(f'motor {cid} is turning ({erpm:.0f} erpm); writes only at standstill')


def backup_dir(args):
    d = os.path.join(args.backup_root, datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    os.makedirs(d, exist_ok=True)
    return d


# -------------------------------------------------------------- code upload
def pack_lisp(path, libdir):
    """VESC Tool's lispPackImports: code, then a table of imported files."""
    code = open(path, encoding='utf-8').read()
    base = os.path.dirname(os.path.abspath(path))
    vb = bytearray(b'\0\0') + code.encode('utf-8')
    if vb[-1] != 0:
        vb += b'\0'
    files = []
    for line in code.split('\n'):
        l = line.lstrip(' ')
        while l.startswith('( '):
            l = '(' + l[2:]
        if not l.lower().startswith('(import '):
            continue
        a, b = l.find('"'), l.rfind('"')
        if not (a > 0 and b > a):
            raise VescError('invalid import: ' + line)
        ipath = l[a + 1:b]
        tag = l[b + 1:].replace('\r', '').replace(' ', '').replace(')', '').replace("'", '')
        tag = tag.split(';')[0]
        if ipath.startswith('pkg@') or ipath.startswith('pkg::'):
            # Library package from the VESC Tool archive: use a local copy of its code
            stem = os.path.splitext(os.path.basename(ipath))[0]
            local = os.path.join(libdir, stem + '.lisp')
            if not os.path.exists(local):
                raise VescError(f'library {ipath} not available locally ({local})')
            data = open(local, 'rb').read() + b'\0'
        else:
            data = open(os.path.join(base, ipath), 'rb').read() + b'\0'
        files.append((tag, data))
    table = sum(len(t) + 9 for t, _ in files)
    vb += struct.pack('>h', len(files))
    off = len(vb) + table - 2
    for tag, data in files:
        while off % 4:
            off += 1
        vb += tag.encode() + b'\0' + struct.pack('>ii', off, len(data))
        off += len(data)
    for tag, data in files:
        while (len(vb) - 2) % 4:
            vb += b'\0'
        vb += data
    return bytes(vb)


def upload_code(v, can_id, data, erase_cmd, write_cmd, label):
    """Erase and write a code area (Lisp or QML) in 384-byte chunks, VESC Tool style."""
    blob = struct.pack('>IH', len(data) - 2, crc16(data)) + data
    r = v.request(bytes([erase_cmd]) + struct.pack('>i', len(data) + 100), erase_cmd,
                  v.tgt(can_id), timeout=10.0, retries=0)
    if not r or r[0] != 1:
        raise VescError(f'{label}: erase failed')
    off = 0
    while off < len(blob):
        chunk = blob[off:off + 384]
        r = v.request(bytes([write_cmd]) + struct.pack('>I', off) + chunk, write_cmd, v.tgt(can_id),
                      timeout=1.0, retries=4, match=lambda p, o=off: len(p) >= 6 and struct.unpack('>I', p[2:6])[0] == o)
        if r[0] != 1:
            raise VescError(f'{label}: write failed at offset {off}')
        off += len(chunk)
        print(f'\r{label}: {off}/{len(blob)} bytes', end='', file=sys.stderr)
    print(file=sys.stderr)


def set_lisp_running(v, can_id, on):
    r = v.request(bytes([COMM_LISP_SET_RUNNING, 1 if on else 0]), COMM_LISP_SET_RUNNING, v.tgt(can_id), timeout=3.0)
    return bool(r and r[0])


def read_vescpkg(path):
    raw = open(path, 'rb').read()
    n = struct.unpack('>I', raw[:4])[0]
    body = zlib.decompress(raw[4:])
    if len(body) != n:
        raise VescError('package size mismatch')
    b = Buf(body)
    if b.string() != 'VESC Packet':
        raise VescError('not a VESC package')
    pkg = {}
    while b.left() > 0:
        key = b.string()
        ln = b.i32()
        pkg[key] = b.take(ln)
    return pkg


def qcompress(data):
    return struct.pack('>I', len(data)) + zlib.compress(data, 9)


# ---------------------------------------------------------------- commands
def cmd_discover(args):
    found = discover(args.seconds)
    if not found:
        print('no Express broadcast seen; scanning the local network for port 65102')
        found = scan_subnet()
    for name, ip, port in found.values():
        print(f'{name}\t{ip}:{port}')


def cmd_info(args):
    v = connect(args)
    ids = [None] + [i for i in v.can_ids]
    if v.local_id is not None and args.m2_id not in v.can_ids:
        ids.append(args.m2_id)
    for cid in ids:
        try:
            i = v.fw_version(cid if cid is not None else None)
        except VescError as e:
            print(f'{"local" if cid is None else cid}: {e}')
            continue
        where = 'local' if cid is None else f'CAN {cid}'
        print(f'{where:8} {i["hw"]:<20} fw {i["fw"]}  {i.get("hw_type", "")}  uuid {i.get("uuid", "")}')


def cmd_values(args):
    v = connect(args)
    for cid in (args.esc_id, args.m2_id):
        x = v.values(cid)
        print(f'motor {cid}: ' + '  '.join(f'{k} {val:.2f}' for k, val in x.items()))


def log_node(v, args):
    """Logs live on the Express (or whatever --log-id says)."""
    if args.log_id is not None:
        return v.tgt(args.log_id)
    if v.local_id is None:
        return None
    for cid in v.can_ids:
        try:
            i = v.fw_version(cid)
        except VescError:
            continue
        if 'express' in i['hw'].lower() or i.get('hw_type') == 'Custom module' and 'disp' not in i['hw'].lower():
            return cid
    raise VescError('no Express found on CAN; give --log-id')


def file_list(v, node, path):
    files, frm = [], ''
    while True:
        d = Buf(v.request(bytes([COMM_FILE_LIST]) + path.encode() + b'\0' + frm.encode() + b'\0',
                          COMM_FILE_LIST, node, timeout=1.5, retries=3))
        more = d.i8()
        while d.left() > 0:
            files.append({'dir': bool(d.i8()), 'size': d.i32(), 'name': d.string()})
        if not more or not files:
            break
        frm = files[-1]['name']
    return sorted(files, key=lambda f: f['name'].lower())


def file_read(v, node, path):
    data = bytearray()
    size = None
    while size is None or len(data) < size:
        off = len(data)
        d = Buf(v.request(bytes([COMM_FILE_READ]) + path.encode() + b'\0' + struct.pack('>i', off),
                          COMM_FILE_READ, node, timeout=1.5, retries=3,
                          match=lambda p, o=off: struct.unpack('>i', p[1:5])[0] == o))
        d.i32()
        size = d.i32()
        if size < 0:
            raise VescError(f'cannot read {path}')
        chunk = d.take(d.left())
        if not chunk and len(data) < size:
            raise VescError(f'empty chunk reading {path}')
        data += chunk
        print(f'\r{path}: {len(data)}/{size}', end='', file=sys.stderr)
    print(file=sys.stderr)
    return bytes(data)


def walk_logs(v, node, path=''):
    for f in file_list(v, node, path):
        if f['name'] in ('.', '..'):
            continue
        full = (path + '/' + f['name']).replace('//', '/')
        if f['dir']:
            yield from walk_logs(v, node, full)
        elif f['name'].lower().endswith('.csv'):
            yield full, f['size']


def cmd_logs(args):
    v = connect(args)
    node = log_node(v, args)
    logs = list(walk_logs(v, node, args.path))
    if args.action == 'list':
        for p, s in logs:
            print(f'{s:>10}  {p}')
        return
    os.makedirs(args.dest, exist_ok=True)
    got = 0
    for p, s in logs:
        out = os.path.join(args.dest, os.path.basename(p))
        if not args.all and os.path.exists(out) and os.path.getsize(out) == s:
            continue
        if args.match and not re.search(args.match, p):
            continue
        data = file_read(v, node, p)
        with open(out, 'wb') as f:
            f.write(data)
        got += 1
    print(f'{got} log(s) downloaded to {args.dest}')


def cmd_conf_get(args):
    v = connect(args)
    d, vals = get_config(v, args.kind, args.id)
    config_to_xml(args.kind, vals, args.file)
    print(f'{args.kind} of {args.id} saved to {args.file} ({len(vals)} parameters)')


def cmd_conf_set(args):
    v = connect(args)
    d, cur = get_config(v, args.kind, args.id)
    new = dict(cur)
    want = xml_to_values(args.kind, args.file, d)
    # Never take current/voltage offset calibration from a file: it belongs to the
    # hardware it was measured on, and the firmware ignores it anyway unless told otherwise.
    for k in [k for k in want if k.startswith(PROTECTED)]:
        del want[k]
    # The Dash ESC drive modes rewrite these at runtime (neutral = scale 0 and a
    # speed limit), so the device usually shows the current mode, not the setting.
    if args.kind == 'mcconf' and not args.include_profile:
        for k in PROFILE:
            want.pop(k, None)
    missing = [k for k in d.order if k not in want]
    new.update(want)
    changes = [(k, cur[k], new[k]) for k in d.order if differs(d, k, cur[k], new[k])]
    if missing:
        print(f'{len(missing)} parameter(s) not in the file keep their device value')
    if not changes:
        print('no differences, nothing to write')
        return
    for k, a, b in changes:
        print(f'  {k}: {fmt_val(a)} -> {fmt_val(b)}')
    if args.dry_run:
        print('dry run, nothing written')
        return
    require_standstill(v, args)
    bdir = backup_dir(args)
    config_to_xml(args.kind, cur, os.path.join(bdir, f'{args.kind}_{args.id}_before.xml'))
    v.request(bytes([KINDS[args.kind][2]]) + d.encode(new), KINDS[args.kind][2], v.tgt(args.id),
              timeout=5.0, retries=0)
    time.sleep(0.5)
    d2, back = get_config(v, args.kind, args.id)
    bad = [k for k in d.order if differs(d, k, back[k], new[k])]
    config_to_xml(args.kind, back, os.path.join(bdir, f'{args.kind}_{args.id}_after.xml'))
    if bad:
        print('READ-BACK DIFFERS (the firmware may have limited these):')
        for k in bad:
            print(f'  {k}: wanted {fmt_val(new[k])}, device has {fmt_val(back[k])}')
    print(f'{len(changes)} change(s) written to {args.id}; backup in {bdir}')


def cmd_backup(args):
    v = connect(args)
    bdir = backup_dir(args)
    for kind, cid in (('mcconf', args.esc_id), ('mcconf', args.m2_id), ('appconf', args.esc_id)):
        d, vals = get_config(v, kind, cid)
        p = os.path.join(bdir, f'{kind}_{cid}.xml')
        config_to_xml(kind, vals, p)
        print(f'saved {p}')


def cmd_lisp(args):
    v = connect(args)
    cid = args.id
    if args.action == 'upload':
        data = pack_lisp(args.file, args.lib)
        require_standstill(v, args)
        upload_code(v, cid, data, COMM_LISP_ERASE_CODE, COMM_LISP_WRITE_CODE, 'lisp')
        ok = set_lisp_running(v, cid, True)
        print(f'uploaded {len(data)} bytes to {cid}; running: {ok}')
        time.sleep(2.0)
        out = v.repl(cid, '(+ 1 2)', 2.0)
        if not out.strip():
            # Seen on the Duet (fw 7.00): after replacing a running script the
            # evaluator can stay wedged until the controller reboots.
            print('no REPL answer, rebooting the controller', file=sys.stderr)
            v.send(bytes([COMM_REBOOT]), v.tgt(cid))
            time.sleep(12.0)
            out = v.repl(cid, '(+ 1 2)', 3.0)
        print('REPL check:', out.strip() or '(no answer)')
    elif args.action in ('start', 'stop'):
        v.prints = []
        print('ok' if set_lisp_running(v, cid, args.action == 'start') else 'failed')
        t_end = time.time() + args.wait
        while time.time() < t_end:
            p = v.recv(t_end - time.time())
            if p is not None and p[0] == COMM_LISP_PRINT:
                v.prints.append(p[1:].decode('latin-1'))
        if v.prints:
            print('\n'.join(v.prints))
    elif args.action == 'reboot':
        require_standstill(v, args)
        v.send(bytes([COMM_REBOOT]), v.tgt(cid))
        print(f'reboot sent to {cid}')
    elif args.action == 'read':
        data, total, off = bytearray(), None, 0
        while total is None or off < total:
            n = 400 if total is None else min(400, total - off)
            b = Buf(v.request(bytes([COMM_LISP_READ_CODE]) + struct.pack('>ii', n, off), COMM_LISP_READ_CODE,
                              v.tgt(cid), timeout=1.5, retries=3))
            total = b.i32()
            o = b.i32()
            if total == 0:
                break
            chunk = b.take(b.left())
            data += chunk
            off += len(chunk)
        open(args.file, 'wb').write(data)
        print(f'read {len(data)} bytes of stored code to {args.file}')
    elif args.action == 'stats':
        b = Buf(v.request(bytes([COMM_LISP_GET_STATS, 1]), COMM_LISP_GET_STATS, v.tgt(cid), timeout=2.0))
        print(f'cpu {b.f16(100)} %  heap {b.f16(100)} %  mem {b.f16(100)} %  stack {b.f16(100)} %')
        print('last context result:', b.string())
        n = 0
        while b.left() > 0 and n < args.globals:
            name = b.string()
            print(f'  {name} = {b.f32auto():.4g}')
            n += 1
    elif args.action == 'repl':
        print(v.repl(cid, args.expr, args.wait))


def cmd_pkg(args):
    v = connect(args)
    pkg = read_vescpkg(args.file)
    name = pkg.get('name', b'?').decode()
    cid = args.id
    if cid is None:
        for c in v.can_ids:
            try:
                if 'disp' in v.fw_version(c)['hw'].lower():
                    cid = c
                    break
            except VescError:
                pass
        if cid is None:
            raise VescError('no display found on CAN; give --id')
    info = v.fw_version(cid)
    print(f'installing "{name}" on {info["hw"]} (CAN {cid}, fw {info["fw"]})')
    require_standstill(v, args)
    qml = pkg.get('qmlFile', b'')
    if qml:
        script = b'import Vedder.vesc.vescinterface 1.0;import "qrc:/mobile";' + qml
        full = pkg.get('qmlIsFullscreen', b'\0')[:1] == b'\x01'
        data = struct.pack('>H', 2 if full else 1) + qcompress(script)
        upload_code(v, cid, data, COMM_QMLUI_ERASE, COMM_QMLUI_WRITE, 'qml')
    lisp = pkg.get('lispData', b'')
    if lisp:
        upload_code(v, cid, lisp, COMM_LISP_ERASE_CODE, COMM_LISP_WRITE_CODE, 'lisp')
        print('running:', set_lisp_running(v, cid, True))
    print('package installed')


def cmd_reboot(args):
    v = connect(args)
    require_standstill(v, args)
    v.send(bytes([COMM_REBOOT]), v.tgt(args.id))
    print(f'reboot sent to {args.id}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--tcp', help='HOST[:PORT] of the Express on Wi-Fi')
    ap.add_argument('--serial', help='USB serial port')
    ap.add_argument('--esc-id', type=int, default=48, help='motor 1 CAN id (default 48)')
    ap.add_argument('--m2-id', type=int, default=49, help='motor 2 CAN id (default 49)')
    ap.add_argument('--force', action='store_true', help='skip the standstill check')
    ap.add_argument('--backup-root', default=os.path.join(HERE, 'backups'))
    ap.add_argument('-v', '--verbose', action='store_true')
    sub = ap.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('discover', help='list Express devices broadcasting on Wi-Fi')
    s.add_argument('--seconds', type=float, default=3.0)
    s.set_defaults(fn=cmd_discover)

    sub.add_parser('info', help='firmware and hardware of every node').set_defaults(fn=cmd_info)
    sub.add_parser('values', help='live values of both motors').set_defaults(fn=cmd_values)

    s = sub.add_parser('logs', help='list or download logs')
    s.add_argument('action', choices=['list', 'pull'])
    s.add_argument('--dest', default='logs')
    s.add_argument('--path', default='')
    s.add_argument('--all', action='store_true', help='download again even if present')
    s.add_argument('--match', help='regex on the file path')
    s.add_argument('--log-id', type=int, help='CAN id of the node holding the logs (default: the Express)')
    s.set_defaults(fn=cmd_logs)

    for kind in ('mcconf', 'appconf'):
        s = sub.add_parser(kind, help=f'read or write the {kind}')
        ss = s.add_subparsers(dest='action', required=True)
        g = ss.add_parser('get')
        g.add_argument('id', type=int)
        g.add_argument('file')
        g.set_defaults(fn=cmd_conf_get, kind=kind)
        w = ss.add_parser('set')
        w.add_argument('id', type=int)
        w.add_argument('file')
        w.add_argument('--dry-run', action='store_true')
        w.add_argument('--include-profile', action='store_true',
                       help='also write current scales and erpm limits (normally set by the drive modes)')
        w.set_defaults(fn=cmd_conf_set, kind=kind)

    sub.add_parser('backup', help='save both motor configs and the app config').set_defaults(fn=cmd_backup)

    s = sub.add_parser('lisp', help='upload, start, stop the Lisp script, or run REPL expressions')
    s.add_argument('action', choices=['upload', 'start', 'stop', 'repl', 'stats', 'read', 'reboot'])
    s.add_argument('--globals', type=int, default=40, help='number of global numbers to show with stats')
    s.add_argument('--id', type=int, default=48)
    s.add_argument('--file', help='script for upload')
    s.add_argument('--expr', help='expression for repl')
    s.add_argument('--wait', type=float, default=1.5, help='seconds to collect REPL output')
    s.add_argument('--lib', default=os.path.join(HERE, 'lib'), help='local copies of pkg@ libraries')
    s.set_defaults(fn=cmd_lisp)

    s = sub.add_parser('reboot', help='reboot a node (standstill only)')
    s.add_argument('--id', type=int, default=48)
    s.set_defaults(fn=cmd_reboot)

    s = sub.add_parser('pkg', help='install a .vescpkg (default target: the display)')
    s.add_argument('file')
    s.add_argument('--id', type=int)
    s.set_defaults(fn=cmd_pkg)

    args = ap.parse_args()
    if args.cmd == 'lisp' and args.action in ('upload', 'read') and not args.file:
        ap.error('lisp upload/read needs --file')
    if args.cmd == 'lisp' and args.action == 'repl' and not args.expr:
        ap.error('lisp repl needs --expr')
    try:
        args.fn(args)
    except VescError as e:
        print(f'error: {e}', file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f'error: cannot reach the scooter ({e}); is it switched on and on Wi-Fi?', file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()
