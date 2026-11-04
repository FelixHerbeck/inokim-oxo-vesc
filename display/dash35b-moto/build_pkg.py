#!/usr/bin/env python3
"""Build dash35b.vescpkg without VESC Tool.

Mirrors VESC Tool's CodeLoader::lispPackImports and packVescPackage
(vesc_tool/codeloader.cpp): the main LispBM file followed by a table of the
files it imports, wrapped in a qCompress'ed "VESC Packet" container.

Usage: build_pkg.py <package dir> <code_server.lisp> <output.vescpkg>
"""
import os, re, struct, sys, zlib, datetime, subprocess

pkg_dir, code_server_path, out_path = sys.argv[1:4]

def s(txt):              # vbAppendString
    return txt.encode() + b'\0'

def i16(v): return struct.pack('>h', v)
def i32(v): return struct.pack('>i', v)

version = open(os.path.join(pkg_dir, 'version')).read().strip()

def gen(src, dst):
    txt = open(os.path.join(pkg_dir, src)).read().replace('{{VERSION}}', version)
    open(os.path.join(pkg_dir, dst), 'w').write(txt)
    return txt

gen('version.lisp.in', 'version.lisp')
qml = gen('ui.qml.in', 'ui.qml')
readme = open(os.path.join(pkg_dir, 'README_Disp.md')).read()
readme += ('\n### Build Info\n\n- Version: %s\n- Build Date: %s\n'
           % (version, datetime.datetime.now().astimezone().isoformat(' ', 'seconds')))
open(os.path.join(pkg_dir, 'README_Disp-gen.md'), 'w').write(readme)

def import_from_line(line):
    line = line.lstrip(' ')
    while line.startswith('( '):
        line = '(' + line[2:]
    if not line.lower().startswith('(import '):
        return None
    a, b = line.find('"'), line.rfind('"')
    if not (a > 0 and b > a):
        raise SystemExit('invalid import: ' + line)
    path = line[a + 1:b]
    tag = line[b + 1:].replace('\r', '').replace(' ', '').replace(')', '').replace("'", '')
    if ';' in tag:
        tag = tag[:tag.index(';')]
    return path, tag

def pack_imports(code):
    vb = bytearray(i16(0))                     # flags
    vb += code.encode()
    if vb[-1] != 0:
        vb += b'\0'
    files = []
    for line in code.split('\n'):
        r = import_from_line(line)
        if not r:
            continue
        path, tag = r
        if path.startswith('pkg@'):
            # Library package from the VESC Tool archive: its main code is imported
            if 'code_server' not in path:
                raise SystemExit('unknown package import ' + path)
            data = open(code_server_path, 'rb').read() + b'\0'
        else:
            data = open(os.path.join(pkg_dir, path), 'rb').read() + b'\0'
        files.append((tag, data))
    table_size = sum(len(t) + 9 for t, _ in files)
    vb += i16(len(files))
    off = len(vb) + table_size - 2
    for tag, data in files:
        while off % 4:
            off += 1
        vb += s(tag) + i32(off) + i32(len(data))
        off += len(data)
    for tag, data in files:
        while (len(vb) - 2) % 4:
            vb += b'\0'
        vb += data
    return bytes(vb), [t for t, _ in files]

main = open(os.path.join(pkg_dir, 'main.lisp')).read()
lisp_data, tags = pack_imports(main)

desc = open(os.path.join(pkg_dir, 'pkgdesc.qml')).read()
name = re.search(r'pkgName:\s*"([^"]*)"', desc).group(1)

def field(key, data):
    return s(key) + i32(len(data)) + data

html = '<pre>' + readme.replace('&', '&amp;').replace('<', '&lt;') + '</pre>'
body = s('VESC Packet')
body += field('name', name.encode())
body += field('description', html.encode())
body += field('description_md', readme.encode())
body += field('lispData', lisp_data)
body += field('qmlFile', qml.encode())
body += field('pkgDescQml', desc.encode())
body += s('qmlIsFullscreen') + i32(1) + b'\0'

out = struct.pack('>I', len(body)) + zlib.compress(body, 9)   # qCompress
open(out_path, 'wb').write(out)
print('%s: %d bytes, lisp %d bytes, %d imports: %s' % (out_path, len(out), len(lisp_data), len(tags), ' '.join(tags)))
