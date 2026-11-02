#!/usr/bin/env python3
"""Public dependency checks and an isolated, opt-in private build transport.

Never print private exception text, URLs, input names, keys, or subprocess output.
"""
import hashlib
import importlib.util
import os
from pathlib import Path, PurePosixPath
import platform
import re
import signal
import shutil
import stat
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile

GIB = 1024 ** 3
REPO = Path(__file__).resolve().parents[2]


def disk(gib, path):
    required = int(gib)
    if not 1 <= required <= 2048:
        raise ValueError('Disk requirement must be an integer from 1 to 2048 GiB')
    free = shutil.disk_usage(path).free
    print(f'Capacity: {free / GIB:.1f} GiB free, {required} GiB required', flush=True)
    if free < required * GIB:
        raise RuntimeError('Insufficient disk space. Use a runner with more storage or a smaller game.')


def preflight():
    if sys.platform != 'darwin' or platform.machine() != 'arm64':
        raise RuntimeError('Preflight requires native arm64 Python on macOS')
    if not any(line.startswith('10.') for line in subprocess.check_output(
            ['dotnet', '--list-sdks'], text=True).splitlines()):
        raise RuntimeError('.NET SDK 10 is missing')
    for name in ('lz4.block', 'capstone', 'fontTools', 'zbic', 'nsz'):
        if importlib.util.find_spec(name) is None:
            raise RuntimeError(f'Missing Python dependency: {name}')
    engine = REPO / 'engine'
    spec = importlib.util.spec_from_file_location('nsp_build', engine / 'scripts/build_ipa_from_nsp.py')
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    build.check_native_python()
    build.check_prereqs(dict(os.environ), engine / 'dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate')
    # Verify the committed translator and SPIRV-Cross fingerprints too. Never rebuild or bypass the lock.
    subprocess.run([sys.executable, str(engine / 'dm/gfx/tools/tool_lock.py'), '--check-tools'], check=True)
    out = Path(os.environ['SAFE_LOGS'])
    source = out / 'probe.metal'
    source.write_text('#include <metal_stdlib>\nusing namespace metal;\n'
                      'kernel void probe(device uint* p [[buffer(0)]], uint i [[thread_position_in_grid]]) { p[i] = i; }\n')
    for tool, args in [('metal', ['-c', str(source), '-o', str(out / 'probe.air')]),
                       ('metallib', [str(out / 'probe.air'), '-o', str(out / 'probe.metallib')])]:
        subprocess.run(['xcrun', '--sdk', 'iphoneos', tool, *args], check=True)
    print('Dependency preflight passed. No game build, GPU runtime or device installation was tested.')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirects are disabled for private transfers')


def validate_url(url):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.fragment or any(ord(c) < 33 for c in url)):
        raise ValueError('A direct HTTPS URL without credentials or a fragment is required')
    return url


def transfer(url, destination=None, source=None, limit=0):
    """Direct presigned GET/PUT only. Do not expose response bodies or exceptions."""
    opener = urllib.request.build_opener(NoRedirect())
    if source is not None:
        with source.open('rb') as stream:
            request = urllib.request.Request(validate_url(url), data=stream, method='PUT', headers={
                'Content-Type': 'application/zip', 'Content-Length': str(source.stat().st_size)})
            with opener.open(request, timeout=120) as response:
                if not 200 <= response.status < 300:
                    raise RuntimeError('Private PUT failed')
        return
    total = 0
    with opener.open(validate_url(url), timeout=120) as response, destination.open('xb') as output:
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > limit:
                raise ValueError('Input exceeds the transfer size limit')
            output.write(chunk)


def unpack(archive, destination, limit):
    """Only root-level game containers. No paths, links, keys, executables or zip bombs."""
    with zipfile.ZipFile(archive) as z:
        entries = z.infolist()
        if not entries or len(entries) > 128 or sum(e.file_size for e in entries) > limit:
            raise ValueError('Archive exceeds its expanded size or entry limit')
        seen = set()
        for entry in entries:
            name = PurePosixPath(entry.filename)
            mode = entry.external_attr >> 16
            if (len(name.parts) != 1 or name.name != entry.filename or '\\' in entry.filename
                    or ':' in entry.filename or any(ord(c) < 32 for c in entry.filename)
                    or name.suffix.lower() not in {'.nsp', '.xci', '.nsz', '.xcz'}
                    or (stat.S_IFMT(mode) not in (0, stat.S_IFREG))
                    or entry.filename.casefold() in seen):
                raise ValueError('Archive must contain only unique root-level game containers')
            seen.add(entry.filename.casefold())
        destination.mkdir(mode=0o700)
        for entry in entries:
            with z.open(entry) as src, (destination / entry.filename).open('xb') as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)


def private_root():
    base = Path(os.environ['RUNNER_TEMP']).resolve()
    root = Path(os.environ['PRIVATE_ROOT']).resolve()
    if root.parent != base or root.name != 'nx2apple-private':
        raise ValueError('Private directory must be directly under RUNNER_TEMP')
    return root


def cleanup():
    root = private_root()
    if root.exists():
        shutil.rmtree(root)
    # The synced engine is disposable in CI and can acquire game-derived shader tables.
    engine = REPO / 'engine'
    if os.environ.get('GITHUB_ACTIONS') == 'true' and engine.is_dir():
        shutil.rmtree(engine)


def private_build():
    stage = 'input validation'
    try:
        os.umask(0o077)
        root = private_root()
        root.mkdir(mode=0o700, exist_ok=False)
        required = int(os.environ['REQUIRED_FREE_GIB'])
        if required < 20:
            raise ValueError('Private build requires a budget of at least 20 GiB')
        disk(required, root)
        for key in ('INPUT_URL', 'INPUT_SHA256', 'PROD_KEYS', 'OUTPUT_URL'):
            if not os.environ.get(key):
                raise ValueError('Required environment secret is missing')
        validate_url(os.environ['INPUT_URL'])
        validate_url(os.environ['OUTPUT_URL'])
        expected = os.environ['INPUT_SHA256'].lower()
        if not re.fullmatch('[0-9a-f]{64}', expected):
            raise ValueError('A SHA-256 input digest is required')
        # Reserve space for source ZIP, extracted containers, decompressed content and output.
        limit = (required - 10) * GIB // 5
        stage = 'private download'
        archive = root / 'input.zip'
        transfer(os.environ['INPUT_URL'], destination=archive, limit=limit)
        with archive.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                raise ValueError('Input checksum mismatch')
        stage = 'archive validation'
        unpack(archive, root / 'game', limit)
        archive.unlink()
        keys = root / 'prod.keys'
        keys.write_text(os.environ['PROD_KEYS'], encoding='utf-8')
        # Never pass transport credentials or key contents to the build process.
        env = {k: v for k, v in os.environ.items() if k not in
               ('INPUT_URL', 'INPUT_SHA256', 'PROD_KEYS', 'OUTPUT_URL')}
        stage = 'game build'
        with (root / 'build.log').open('wb') as log:
            process = subprocess.Popen([sys.executable, str(REPO / 'engine/scripts/build_ipa_from_nsp.py'),
                str(root / 'game'), '-k', str(keys), '--platform', 'ios', '--romfs', 'separate',
                '--gpu', 'none', '--work-dir', str(root / 'work'), '-o', str(root / 'result.ipa'),
                '--progress', 'off'], env=env, stdin=subprocess.DEVNULL, stdout=log,
                stderr=subprocess.STDOUT, start_new_session=True)
            started = time.monotonic()
            while process.poll() is None:
                if shutil.disk_usage(root).free < 4 * GIB or time.monotonic() - started > 7200:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                    raise RuntimeError('Build stopped for capacity or time limit')
                time.sleep(5)
        stage = 'private result delivery'
        result = root / 'result.zip'
        images = [p for p in (root / 'work').rglob('*')
                  if p.is_file() and p.name.lower() == 'romfs.img'] if process.returncode == 0 else []
        outputs = [root / 'build.log'] + ([root / 'result.ipa', *images] if process.returncode == 0 else [])
        if shutil.disk_usage(root).free < sum(p.stat().st_size for p in outputs) + 4 * GIB:
            raise RuntimeError('Insufficient capacity for private result packaging')
        with zipfile.ZipFile(result, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as z:
            z.write(root / 'build.log', 'build.log')
            if process.returncode == 0:
                z.write(root / 'result.ipa', 'result.ipa')
                for image in images:
                    z.write(image, 'data/' + image.relative_to(root / 'work').as_posix())
        transfer(os.environ['OUTPUT_URL'], source=result)
        if process.returncode:
            print('::error::Game build failed. Raw diagnostics were sent only to your private output location.')
            return 1
        print('IPA and RomFS images sent only to your private output location. Signing and device runtime remain untested.')
        return 0
    except Exception:
        # Exception text can contain signed URLs, response bodies, filenames or keys.
        print(f'::error::Private stage failed during {stage}. Check secrets, capacity and private storage permissions.')
        return 1
    finally:
        cleanup()


if __name__ == '__main__':
    command = sys.argv[1:]
    if command and command[0] == 'disk':
        disk(*command[1:])
    elif command == ['preflight']:
        preflight()
    elif command == ['private-build']:
        sys.exit(private_build())
    elif command == ['cleanup']:
        cleanup()
    else:
        sys.exit('usage: apple_ci.py disk GIB PATH | preflight | private-build | cleanup')
