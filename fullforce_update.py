#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""EVO-only FullForce installer. No root, kernel writes, or firmware operations."""
import argparse
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from kernel_update import RELEASE, VERSION

APPID = '3058630'
FLATPAK = 'com.github.Matoking.protontricks'
HERE = Path(__file__).resolve().parent
VENDOR = HERE/'vendor/fwfilterusb'
SERVICE = r'HKLM\SYSTEM\CurrentControlSet\Services\fwfilterusb'
HWKEY = r'HKLM\SYSTEM\CurrentControlSet\Enum\USB#VID_0EB7&PID_0020#001#6&12345678&0&000'

class Stop(RuntimeError):
    pass

def run(args, *, capture=False, check=True, env=None, timeout=600):
    result = subprocess.run([str(a) for a in args], text=True,
                            capture_output=capture, env=env, timeout=timeout)
    if check and result.returncode:
        detail=(result.stderr or result.stdout or '')[-2000:] if capture else ''
        raise Stop(f'Command failed ({result.returncode}): {args[0]}\n{detail}')
    return result

def parse_vdf(text):
    """Parse quoted Steam KeyValues. Reject malformed data rather than guessing."""
    tokens = re.findall(r'"((?:\\.|[^"\\])*)"|([{}])', re.sub(r'(?m)^\s*//.*$', '', text))
    seq=[re.sub(r'\\([\\"])', r'\1', s) if not brace else brace for s,brace in tokens]
    def read(i, nested=False):
        out={}
        while i<len(seq):
            if seq[i]=='}':
                if not nested: raise Stop('Malformed Steam library configuration.')
                return out,i+1
            key=seq[i]; i+=1
            if i>=len(seq): raise Stop('Incomplete Steam library configuration.')
            if seq[i]=='{': val,i=read(i+1,True)
            else: val=seq[i]; i+=1
            out[key]=val
        if nested: raise Stop('Unclosed Steam library configuration.')
        return out,i
    return read(0)[0]

def discover(home):
    roots=[home/'.local/share/Steam', home/'.steam/steam', home/'.steam/root']
    libraries=set()
    for root in roots:
        if not root.exists(): continue
        libraries.add(root.resolve())
        for config in (root/'steamapps/libraryfolders.vdf',root/'config/libraryfolders.vdf'):
            if not config.is_file(): continue
            data=parse_vdf(config.read_text())
            folders=data.get('libraryfolders',data.get('LibraryFolders',{}))
            if not isinstance(folders,dict): continue
            for k,v in folders.items():
                path=v.get('path') if isinstance(v,dict) else (v if k.isdigit() else None)
                if path and Path(path).is_absolute(): libraries.add(Path(path).resolve())
    return sorted({(lib/'steamapps/compatdata'/APPID/'pfx').resolve()
                   for lib in libraries if (lib/'steamapps/compatdata'/APPID/'pfx/system.reg').is_file()})

def validate_prefix(prefix):
    prefix=prefix.expanduser().resolve(strict=True)
    if prefix.name!='pfx' or prefix.parent.name!=APPID or prefix.parent.parent.name!='compatdata':
        raise Stop('Expected an EVO steamapps/compatdata/3058630/pfx directory.')
    if not (prefix/'system.reg').is_file() or not (prefix/'drive_c').is_dir():
        raise Stop('EVO prefix is incomplete. Launch EVO once, then close it.')
    drivers=prefix/'drive_c/windows/system32/drivers'
    if not drivers.resolve().is_relative_to(prefix):
        raise Stop('Driver destination resolves outside the EVO prefix.')
    return prefix

def check_hardware(sysroot=Path('/sys')):
    if not (sysroot/'module/hid_fanatec').exists():
        raise Stop('Existing Fanatec kernel driver is not loaded. Do not reinstall it blindly.')
    base=sysroot/'module/hid_fanatec/drivers/hid:fanatec'
    for dev in sorted(base.glob('0003:0EB7:0020.*')):
        try:
            wheel=int((dev/'wheel_type').read_text().strip(),0)
            rim=int((dev/'rim_id').read_text().strip(),0)
        except (OSError,ValueError): continue
        if wheel==17:
            print(f'Fanatec base family: {wheel}; rim ID: {rim}')
            return
    raise Stop('No supported GT DD Pro / CSL DD identification found. Connect the wheel in PC mode.')

def check_kernel_candidate():
    version = Path('/sys/module/hid_fanatec/version')
    if os.uname().release != RELEASE or not version.is_file() or version.read_text().strip() != VERSION:
        raise Stop('Stage the matching 0.3 kernel module and reboot before enabling the EVO add-on.')

def busy_processes(proc=Path('/proc')):
    found=[]
    for p in proc.iterdir():
        if not p.name.isdigit(): continue
        try:
            if p.stat().st_uid!=os.getuid(): continue
            name=(p/'comm').read_text().strip()
            if '.exe' in name.lower() or name.lower().startswith(('wine','wineserver')):
                found.append(f'{p.name}:{name}')
        except OSError: pass
    return found

def require_idle():
    busy=busy_processes()
    if busy:
        raise Stop('Close Windows games and Wine tools, then retry. Active: '+', '.join(busy[:10]))

def verify_vendor():
    manifest=json.loads((HERE/'vendor-sha256.json').read_text())
    for rel,expected in manifest.items():
        p=HERE/rel
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
            raise Stop('Bundled file checksum failed: '+rel)

def atomic_json(path, data):
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,indent=2)+'\n')
    os.replace(tmp,path)

def tree_size(path):
    total=0
    for root,dirs,files in os.walk(path,followlinks=False):
        dirs[:]=[d for d in dirs if not (Path(root)/d).is_symlink()]
        for f in files:
            p=Path(root)/f
            if not p.is_symlink(): total+=p.stat().st_size
    return total

def tree_fingerprint(path):
    """Hash regular files and symlink text without following links outside the prefix."""
    h=hashlib.sha256()
    for root,dirs,files in os.walk(path,followlinks=False):
        dirs.sort(); files.sort()
        for name in sorted(dirs+files):
            p=Path(root)/name
            h.update(str(p.relative_to(path)).encode()+b'\0')
            if p.is_symlink(): h.update(b'L'+os.readlink(p).encode())
            elif p.is_file():
                h.update(b'F')
                with p.open('rb') as f:
                    for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
            else: h.update(b'D')
    return h.hexdigest()

def backup_prefix(prefix, state_dir):
    backup=state_dir/('backup-'+str(time.time_ns()))
    need=tree_size(prefix)
    if shutil.disk_usage(state_dir).free<need+128*1024*1024:
        raise Stop(f'Insufficient space for backup (needs about {need//1048576+128} MiB).')
    print(f'Backing up EVO prefix ({need//1048576} MiB); symbolic links are preserved.')
    shutil.copytree(prefix,backup,symlinks=True)
    fingerprint=tree_fingerprint(backup)
    if fingerprint!=tree_fingerprint(prefix):
        raise Stop('Backup verification failed or the prefix changed during copying. No add-on installed.')
    return backup,fingerprint

def restore_prefix(prefix, state_dir, state):
    backup=(state_dir/state['backup']).resolve()
    if not backup.is_relative_to(state_dir.resolve()) or not backup.name.startswith('backup-'):
        raise Stop('Invalid backup path in state file.')
    if tree_fingerprint(backup)!=state['fingerprint']:
        raise Stop('Backup integrity check failed. Nothing restored.')
    need=tree_size(backup)
    if shutil.disk_usage(prefix.parent).free<need+128*1024*1024:
        raise Stop('Insufficient disk space to stage a restore. Backup retained.')
    stage=prefix.parent/('pfx-restore-'+str(time.time_ns()))
    shutil.copytree(backup,stage,symlinks=True)
    if tree_fingerprint(stage)!=state['fingerprint']:
        raise Stop('Restore staging verification failed. Current prefix unchanged.')
    retained=prefix.parent/('pfx-before-undo-'+str(time.time_ns()))
    prefix.rename(retained)
    try: stage.rename(prefix)
    except BaseException:
        retained.rename(prefix)
        raise
    state.update(status='restored',retained=str(retained))
    atomic_json(state_dir/'state.json',state)
    print('EVO prefix restored. Post-update prefix retained at: '+str(retained))
    print('If you played since installation, newer local saves/settings may be in that retained directory.')

class Protontricks:
    def __init__(self,prefix,allow_install=False):
        self.prefix=prefix
        self.env=os.environ.copy()
        for key in ('WINE','WINESERVER','WINEPREFIX','WINELOADER','WINEDLLPATH','STEAM_COMPAT_DATA_PATH'):
            self.env.pop(key,None)
        self.env['WINEDEBUG']='-all'
        native=shutil.which('protontricks')
        if native:
            self.base=[native]
        else:
            if not shutil.which('flatpak'):
                raise Stop('Install Protontricks from Discover, then run this update again.')
            available=run(['flatpak','info',FLATPAK],capture=True,check=False).returncode==0
            if not available:
                if not allow_install: raise Stop('Protontricks is missing. Run without --check to install it from Flathub.')
                remotes=run(['flatpak','remotes','--user','--columns=name'],capture=True).stdout.splitlines()
                if 'flathub' not in remotes:
                    raise Stop('No user Flathub remote found. Install Protontricks using Discover, then retry.')
                print('Installing Protontricks and required runtime from your configured Flathub remote...')
                run(['flatpak','install','--user','--noninteractive','flathub',FLATPAK],timeout=1800)
            library=prefix.parents[3]
            # Per-run permissions only. No persistent Flatpak overrides.
            self.base=['flatpak','run',f'--filesystem={HERE}:ro',f'--filesystem={library}',FLATPAK]
    def command(self,command,*,capture=False):
        # Stop before touching the wrong prefix if Protontricks resolves a different library.
        guard='test "$WINEPREFIX" -ef '+shlex.quote(str(self.prefix))+' || { echo "Wrong EVO prefix" >&2; exit 73; }; '
        return run(self.base+['-c',guard+command,APPID],env=self.env,capture=capture)
    def stop(self):
        self.command('wineserver -k; wineserver -w')


def transaction(prefix,state_dir,pt):
    backup,fingerprint=backup_prefix(prefix,state_dir)
    state={'version':'0.3.0','appid':APPID,'prefix':str(prefix),'backup':backup.name,
           'fingerprint':fingerprint,'status':'prepared'}
    atomic_json(state_dir/'state.json',state)
    try:
        dest=prefix/'drive_c/windows/system32/drivers/fwfilterusb.sys'
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(VENDOR/'fwfilterusb-x64.sys',dest)
        args=['bash',str(VENDOR/'setup_ftec_fwfilter.sh'),'--apply','--pid','0020',
              '--reg',str(VENDOR/'ftec_fwfilter.reg')]
        pt.command(shlex.join(args))
        checks=' && '.join(shlex.join(['wine','reg','query',key,'/v',value])
                for key,value in [(SERVICE,'ImagePath'),(SERVICE,'DeviceKey'),(SERVICE,'SysfsPath'),(HWKEY,'SystemReport')])
        pt.command(checks)
        pt.stop()
        if hashlib.sha256(dest.read_bytes()).digest()!=hashlib.sha256((VENDOR/'fwfilterusb-x64.sys').read_bytes()).digest():
            raise Stop('Installed add-on binary verification failed.')
        state['status']='installed'
        atomic_json(state_dir/'state.json',state)
    except BaseException:
        print('Update did not complete. Attempting to stop EVO Wine before restoring the backup...')
        try:
            pt.stop()
            require_idle()
            restore_prefix(prefix,state_dir,state)
        except BaseException as rollback_error:
            print('Automatic restore stopped: '+str(rollback_error))
            print('Backup retained. Close all games/tools, then run: bash update.sh --undo')
        raise
    print('\nFullForce add-on installed for EVO. Actual FullForce effects still need in-game testing.')
    print('Start EVO normally in Gaming Mode with the wheel in PC mode.')
    print('Keep your current normal FFB settings. Compare FullForce OFF vs ON in the same car.')
    print('Undo: bash update.sh --undo (close games first).')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--check',action='store_true',help='read-only preflight; no Proton/Wine launch')
    modes.add_argument('--undo',action='store_true',help='restore the verified pre-update EVO prefix')
    parser.add_argument('--prefix',type=Path,help='explicit EVO compatdata/3058630/pfx if detection is ambiguous')
    args=parser.parse_args(argv)
    if os.geteuid()==0: raise Stop('Run as your normal SteamOS user, not with sudo.')
    os.umask(0o077)
    if args.prefix: prefix=validate_prefix(args.prefix)
    else:
        candidates=discover(Path.home())
        if len(candidates)!=1:
            raise Stop('Expected one existing EVO prefix. Launch EVO once or specify --prefix. Found: '+str(candidates))
        prefix=validate_prefix(candidates[0])
    print('EVO prefix: '+str(prefix))
    state_dir=prefix.parent/'fanatec-fullforce'
    state_path=state_dir/'state.json'
    state=json.loads(state_path.read_text()) if state_path.is_file() else None
    if state and state.get('prefix')!=str(prefix): raise Stop('Backup belongs to a different prefix.')
    if args.check:
        verify_vendor(); check_hardware(); check_kernel_candidate(); require_idle()
        Protontricks(prefix)
        print('Preflight passed. No changes made. FullForce runtime behavior is not yet verified.')
        return 0
    require_idle()
    if not args.undo:
        verify_vendor(); check_hardware(); check_kernel_candidate()
    state_dir.mkdir(mode=0o700,exist_ok=True)
    with (state_dir/'lock').open('w') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise Stop('Another FullForce update/restore is running.')
        # Reread after acquiring the lock; never overwrite another run's backup state.
        state=json.loads(state_path.read_text()) if state_path.is_file() else None
        if args.undo:
            if not state or state.get('status') not in ('installed','prepared'):
                raise Stop('No active update to undo.')
            restore_prefix(prefix,state_dir,state)
        else:
            if state and state.get('status') in ('installed','prepared'):
                raise Stop('An update or incomplete transaction already exists. Use --undo before another install.')
            pt=Protontricks(prefix,allow_install=True)
            require_idle()
            transaction(prefix,state_dir,pt)
    return 0

if __name__=='__main__':
    try: sys.exit(main())
    except (Stop,OSError,subprocess.SubprocessError,ValueError) as error:
        print('STOP: '+str(error),file=sys.stderr)
        sys.exit(1)
