#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Stage or restore the Fanatec kernel module. Reboot to activate either change."""
import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

RELEASE = '7.2.7-valve2-2-neptune-72-g31504582a073'
VERSION = 'fullforce-0.3-test'
HERE = Path(__file__).resolve().parent
PAYLOAD = HERE / 'kernel/hid-fanatec.ko'
STATE = Path('/var/lib/fanatec-fullforce') / RELEASE


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def replace_module(source, target):
    """Write on the target filesystem, then replace in one rename."""
    with tempfile.TemporaryDirectory(dir=target.parent) as directory:
        temporary = Path(directory) / target.name
        shutil.copy2(source, temporary)
        with temporary.open('rb') as stream:
            os.fsync(stream.fileno())
        temporary.replace(target)
        fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def restore(state_dir, target, refresh):
    original = state_dir / ('original-' + target.name)
    record = json.loads((state_dir / 'state.json').read_text())
    if record['target'] != str(target) or digest(original) != record['original']:
        raise RuntimeError('Target path or saved original failed verification.')
    if digest(target) not in (record['original'], record['candidate']):
        raise RuntimeError('The module changed independently. Original backup retained.')
    replace_module(original, target)
    refresh()


def install(state_dir, target, candidate, refresh):
    manifest = state_dir / 'state.json'
    original = state_dir / ('original-' + target.name)
    original_hash = digest(target)
    if manifest.exists():
        previous = json.loads(manifest.read_text())
        if previous['target'] != str(target) or previous['original'] != original_hash:
            raise RuntimeError('A pending install or unrelated module change exists.')
    replace_module(target, original)
    record = {'target': str(target), 'original': original_hash, 'candidate': digest(candidate)}
    temporary = state_dir / 'prepared.json'
    temporary.write_text(json.dumps(record) + '\n')
    replace_module(temporary, manifest)
    temporary.unlink()
    try:
        replace_module(candidate, target)
        refresh()
    except BaseException:
        try:
            restore(state_dir, target, refresh)
        except Exception as error:
            print(f'Automatic restore stopped. Backup retained at {original}. {error}')
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'undo'])
    args = parser.parse_args()
    if os.geteuid():
        parser.error('Run this kernel step with sudo.')
    if os.uname().release != RELEASE:
        parser.error(f'This build requires the running kernel {RELEASE}.')
    os.umask(0o077)
    module_root = Path(f'/lib/modules/{RELEASE}').resolve(strict=True)
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest = STATE / 'state.json'
        if args.action == 'undo':
            if not manifest.is_file():
                raise RuntimeError('No module backup exists.')
            target = Path(json.loads(manifest.read_text())['target'])
        else:
            target = Path(run('modinfo', '-k', RELEASE, '-n', 'hid_fanatec'))
        if (target.is_symlink() or not target.is_file() or
                not target.resolve().is_relative_to(module_root)):
            raise RuntimeError(f'Expected an existing regular module under {module_root}.')
        target = target.resolve()

        def refresh():
            run('depmod', '-a', RELEASE)
            if Path(run('modinfo', '-k', RELEASE, '-n', 'hid_fanatec')).resolve() != target:
                raise RuntimeError('The module index selects a different driver path.')

        if args.action == 'undo':
            restore(STATE, target, refresh)
        else:
            if run('modinfo', '-F', 'version', PAYLOAD) != VERSION:
                raise RuntimeError('Unexpected candidate module version.')
            expected = (HERE / 'kernel/SHA256').read_text().split()[0]
            if digest(PAYLOAD) != expected:
                raise RuntimeError('Candidate module failed checksum verification.')
            if run('modinfo', '-F', 'vermagic', PAYLOAD) != run('modinfo', '-F', 'vermagic', target):
                raise RuntimeError('Candidate and existing module have different build flags.')
            with tempfile.TemporaryDirectory(dir=STATE) as directory:
                encoded = Path(directory) / target.name
                compressors = {'.zst': ['zstd', '-q', '-c'], '.xz': ['xz', '-c'],
                               '.gz': ['gzip', '-n', '-c']}
                if target.suffix == '.ko':
                    shutil.copyfile(PAYLOAD, encoded)
                elif target.suffix in compressors:
                    with encoded.open('wb') as stream:
                        subprocess.run([*compressors[target.suffix], PAYLOAD],
                                       stdout=stream, check=True)
                else:
                    raise RuntimeError(f'Unsupported kernel module format {target.name}.')
                shutil.copymode(target, encoded)
                install(STATE, target, encoded, refresh)

    print(f'Kernel module staged at {target}. Reboot to activate the change.')
    print(f'Original backup is in {STATE}.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(f'STOP: {error}') from error
