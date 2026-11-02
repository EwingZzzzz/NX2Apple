#!/usr/bin/env python3
"""Build only the committed original homebrew. No user paths, dumps, keys or URLs.

SPDX-License-Identifier: MIT
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import struct
import subprocess
import sys
import zipfile

REPO = Path(__file__).resolve().parents[2]
TITLE = '010000000000F000'  # Local test identifier, not a retail profile.
BUNDLE = 'org.nx2apple.homebrew.hello'
MESSAGE = b'NX2Apple original homebrew: rewritten guest code is running'
EXPORTS = ('_init_libc0', 'nnosInitialize', '_init_libc1', 'nninitInitializeSdkModule',
           '_ZN2nn2os11SetHostArgcEi', '_ZN2nn2os11SetHostArgvEPPc', 'nninitStartup', '_init_libc2', 'nnMain')


def run(*args, **kwargs):
    subprocess.run([str(a) for a in args], check=True, **kwargs)


def original_nso():
    text, ro, data = bytearray(0x1000), bytearray(0x4000), bytes(0x1000)
    # Virtual addresses: text 0, read-only 0x4000, data 0x8000, bss 0x9000.
    struct.pack_into('<II', text, 0, 0x14000020, 0x4000)  # b nnMain, MOD0 offset
    struct.pack_into('<I', text, 0x40, 0xd65f03c0)  # RET bootstrap stub
    delta = 0x4400 - 0x80
    adr = 0x10000000 | ((delta & 3) << 29) | (((delta >> 2) & 0x7ffff) << 5)
    words = (adr, 0xd2800001 | len(MESSAGE) << 5, 0xd4000001 | 0x27 << 5,
             0xd2800000 | 0xca00 << 5, 0xf2a00000 | 0x3b9a << 5,
             0xd4000001 | 0x0b << 5, 0x14000000 | ((-6) & 0x3ffffff))
    struct.pack_into('<7I', text, 0x80, *words)
    ro[:4] = b'MOD0'
    struct.pack_into('<6i', ro, 4, 0x40, 0x5000, 0x6000, 0x100, 0x10c, 0)
    # Empty unwind search table, valid for the rewriter's format reader.
    ro[0x100:0x104] = bytes((1, 0x1b, 3, 0x3b))
    struct.pack_into('<iI', ro, 0x104, 0, 0)
    symbols = [('vkCreateInstance', 0, 0)] + [(name, 1, 0x80 if name == 'nnMain' else 0x40) for name in EXPORTS]
    symtab = 0x4140
    strtab = symtab + (len(symbols) + 1) * 24
    strings = bytearray(b'\0')
    for i, (name, section, value) in enumerate(symbols, 1):
        struct.pack_into('<IBBHQQ', ro, symtab - 0x4000 + i * 24, len(strings), 0x12, 0, section, value, 4)
        strings += name.encode() + b'\0'
    ro[strtab - 0x4000:strtab - 0x4000 + len(strings)] = strings
    for i, pair in enumerate(((6, symtab), (5, strtab), (11, 24), (10, len(strings)), (0, 0))):
        struct.pack_into('<qQ', ro, 0x40 + i * 16, *pair)
    ro[0x400:0x400 + len(MESSAGE)] = MESSAGE
    build_id = hashlib.sha256(text + ro + data).digest()
    header, body = bytearray(0x100), bytearray()
    header[:4] = b'NSO0'
    header[0x40:0x60] = build_id
    struct.pack_into('<I', header, 0x0c, 0x38)  # all hashes checked, no compression
    for i, (segment, address) in enumerate(((text, 0), (ro, 0x4000), (data, 0x8000))):
        struct.pack_into('<III', header, 0x10 + i * 16, 0x100 + len(body), address, len(segment))
        struct.pack_into('<I', header, 0x60 + i * 4, len(segment))
        header[0xa0 + i * 32:0xc0 + i * 32] = hashlib.sha256(segment).digest()
        body += segment
    struct.pack_into('<I', header, 0x3c, 0x1000)
    return bytes(header + body), build_id.hex()[:32]


def generate(root):
    root.mkdir(parents=True, exist_ok=False)
    exefs, romfs = root / 'dump/base/exefs', root / 'dump/base/romfs'
    exefs.mkdir(parents=True)
    romfs.mkdir(parents=True)
    module, build_id = original_nso()
    (exefs / 'main').write_bytes(module)
    npdm = bytearray(0xa0)
    npdm[:4], npdm[0xc] = b'META', 1
    struct.pack_into('<II', npdm, 0x70, 0x80, 0x20)
    npdm[0x80:0x84] = b'ACI0'
    struct.pack_into('<Q', npdm, 0x90, int(TITLE, 16))
    (exefs / 'main.npdm').write_bytes(npdm)
    (romfs / 'homebrew.txt').write_text(MESSAGE.decode() + '\nOriginal MIT-licensed homebrew. No retail content.\n')
    profile = root / 'profiles' / TITLE
    profile.mkdir(parents=True)
    values = {'title_id': TITLE, 'program_id': TITLE, 'name': 'NX2Apple Homebrew Test',
              'ipa': 'NX2Apple-Homebrew.ipa', 'app_category': 'public.app-category.developer-tools',
              'package': 'v0', 'shader_versions': 'v0', 'modules': 'main', 'romfs_marker': 'homebrew.txt',
              'zip_store': '.metallib', 'mem_reserve': '0x10000000', 'mem_alias': '0x4000000',
              'mem_stack': '0x400000', 'app_pool': '0x8000000', 'mem_used': '0x100000', 'sys_resource': '0'}
    (profile / 'game.tsv').write_text(''.join(f'{k}\t{v}\n' for k, v in values.items()) + f'build\tv0\t1.0\tmain={build_id}\n')
    for name in ('shader_map.tsv', 'pso_manifest.tsv'):
        (profile / name).write_text('# Original CPU-only homebrew, no NVN shaders or PSOs.\n')
    (root / 'env.txt').write_text('DM_DBG=1\n')
    return root


def select_xcode():
    if sys.platform != 'darwin' or os.uname().machine != 'arm64':
        raise RuntimeError('This build needs an Apple Silicon macOS runner')
    for app in sorted(Path('/Applications').glob('Xcode*.app')):
        dev = str(app / 'Contents/Developer')
        env = dict(os.environ, DEVELOPER_DIR=dev)
        version = subprocess.run(['xcodebuild', '-version'], env=env, capture_output=True, text=True)
        if version.returncode == 0 and version.stdout.splitlines()[0] == 'Xcode 27.2':
            run('sudo', 'xcode-select', '--switch', dev)
            with open(os.environ['GITHUB_ENV'], 'a') as stream:
                stream.write(f'DEVELOPER_DIR={dev}\n')
            run('sw_vers')
            print(version.stdout, flush=True)
            run('xcrun', '--sdk', 'iphoneos', '--show-sdk-version', env=env)
            run('xcrun', '--sdk', 'iphoneos', '--show-sdk-build-version', env=env)
            return
    raise RuntimeError('Xcode 27.2 is not installed. No fallback compiler is used.')


def finish_ipa(raw, final, root):
    """Remove system fonts, add redistributable fonts/notices, then validate the archive."""
    font = REPO / 'frontend/fonts/Manrope.ttf'
    ext = root / 'homebrew-buttons.ttf'
    run(sys.executable, REPO / 'engine/dm/tools/make_ext_font.py', ext, font)
    prefix = 'Payload/DmIOS.app/'
    # Production's archive has no bundle resource signature. The sideloader signs the final bundle.
    with zipfile.ZipFile(raw) as source, zipfile.ZipFile(final, 'w', compression=zipfile.ZIP_DEFLATED) as output:
        for item in source.infolist():
            if item.filename.endswith(('dm/font/standard.ttf', 'dm/font/nintendo_ext.ttf')):
                continue
            if item.filename.endswith('embedded.mobileprovision') or '/_CodeSignature/' in item.filename:
                raise RuntimeError('Unexpected signing credential/resource signature in source IPA')
            output.writestr(item, source.read(item))
        output.write(font, prefix + 'dm/font/standard.ttf')
        output.write(ext, prefix + 'dm/font/nintendo_ext.ttf')
        output.write(REPO / 'frontend/fonts/Manrope-OFL.txt', prefix + 'dm/font/OFL.txt')
        output.write(REPO / 'LICENSE', prefix + 'LICENSES/NX2Apple-MIT.txt')
        output.write(REPO / 'engine/LICENSE', prefix + 'LICENSES/nxnative-MIT.txt')
        output.write(REPO / 'engine/dm/third_party/README.md', prefix + 'LICENSES/third-party-README.md')
        for path in (REPO / 'engine/dm').rglob('*'):
            if path.is_file() and path.name.upper().startswith(('LICENSE', 'COPYING', 'NOTICE', 'PATENTS', 'AUTHORS')):
                output.write(path, prefix + 'LICENSES/' + path.relative_to(REPO / 'engine/dm').as_posix())
        output.write(REPO / 'homebrew/hello/README.md', prefix + 'HOME BREW README.md')
    with zipfile.ZipFile(final) as z:
        if z.testzip() is not None or len(z.namelist()) != len(set(z.namelist())):
            raise RuntimeError('IPA CRC failure or duplicate paths')
        info = plistlib.loads(z.read(prefix + 'Info.plist'))
        if info['CFBundleIdentifier'] != BUNDLE:
            raise RuntimeError('Unexpected bundle identifier')
        executable = z.read(prefix + info['CFBundleExecutable'])
        if executable[:4] != bytes.fromhex('cffaedfe') or struct.unpack_from('<I', executable, 4)[0] != 0x0100000c:
            raise RuntimeError('Expected an arm64 Mach-O executable')
        if z.read(prefix + 'dm/font/standard.ttf') != font.read_bytes():
            raise RuntimeError('IPA standard font is not OFL Manrope')
        forbidden = ('.nsp', '.xci', '.nsz', '.xcz', '.nca', '.keys', '.p12', '.pfx', '.mobileprovision', '.p8', '.pem')
        if any(n.lower().endswith(forbidden) for n in z.namelist()):
            raise RuntimeError('Forbidden input or credential found in IPA')
        (final.parent / 'archive-files.txt').write_text('\n'.join(z.namelist()) + '\n')
    report = {'artifact': final.name, 'sha256': hashlib.sha256(final.read_bytes()).hexdigest(),
              'bytes': final.stat().st_size, 'bundle_id': BUNDLE, 'title_id': TITLE,
              'nx2apple_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'engine_pin': (REPO / '.upstream-ref').read_text().strip(),
              'built': True, 'signed_for_device': False, 'installed_on_ipad': False, 'guest_executed': False,
              'input': 'original unencrypted homebrew generated from committed source, no keys',
              'limits': 'Vulkan shader preparation tested, no runtime graphics or retail NVN validation'}
    (final.parent / 'build-report.json').write_text(json.dumps(report, indent=2) + '\n')
    (final.parent / 'SHA256SUMS.txt').write_text(f'{report["sha256"]}  {final.name}\n')
    print(json.dumps(report, indent=2), flush=True)


def build(root, output):
    root = generate(root)
    output.mkdir(parents=True, exist_ok=True)
    romfs = root / 'dump/base/romfs'
    for stage in ('vert', 'frag'):
        run('glslangValidator', '-V', REPO / f'homebrew/hello/triangle.{stage}', '-o', romfs / f'triangle.{stage}.spv')
    env = dict(os.environ, DM_GAMES_DIR=str(root / 'profiles'), DM_GAMES_FIRST='1', J='3', DM_REWRITE_J='1',
               STD_FONT=str(REPO / 'frontend/fonts/Manrope.ttf'), DM_ENTITLEMENTS='')
    raw = root / 'unpublished.ipa'
    run(sys.executable, REPO / 'engine/scripts/build_ipa_from_nsp.py', root / 'dump',
        '--work-dir', root / 'work', '--platform', 'ios', '--romfs', 'bundle', '--gpu', 'none',
        '--env-file', root / 'env.txt', '--bundle-id', BUNDLE, '--app-name', 'NX2Apple Homebrew Test',
        '--progress', 'lines', '-o', raw, env=env, stdin=subprocess.DEVNULL)
    finish_ipa(raw, output / 'NX2Apple-Homebrew.ipa', root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('select-xcode', 'build', 'generate'))
    parser.add_argument('--root', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.command == 'select-xcode':
        select_xcode()
    elif args.command == 'generate':
        generate(args.root)
    else:
        build(args.root, args.output)
