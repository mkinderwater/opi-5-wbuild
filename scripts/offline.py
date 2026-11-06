"""Prepare the image's ARM64 userspace using host binfmt/QEMU, before flashing."""
from contextlib import contextmanager, ExitStack
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


class CleanupError(RuntimeError):
    pass


def mountpoints(text=None):
    if text is None:
        text = Path('/proc/self/mountinfo').read_text()
    def decode(value):
        return re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1],8)), value)
    return [Path(decode(line.split()[4])).resolve() for line in text.splitlines() if len(line.split()) >= 6]


def mounts_under(path, points=None):
    root = Path(path).resolve()
    return [p for p in (mountpoints() if points is None else points) if p == root or root in p.parents]


@contextmanager
def workspace(parent):
    path = Path(tempfile.mkdtemp(prefix='chatbox-',dir=parent))
    try:
        yield path
    finally:
        # Never recurse through a surviving /dev, /proc, /sys or package bind mount.
        remaining = mounts_under(path)
        if remaining:
            raise CleanupError('Workspace retained because mounts remain: '+str(path)+'; '+', '.join(map(str,remaining)))
        shutil.rmtree(path)


def check_emulation(entry=Path('/proc/sys/fs/binfmt_misc/qemu-aarch64')):
    if not entry.is_file():
        raise ValueError('ARM64 binfmt handler is unavailable. Run sudo ./setup-wsl.sh in WSL2.')
    text = entry.read_text()
    match = re.search(r'^flags:\s*(\S+)',text,re.M)
    if not text.startswith('enabled\n') or not match or 'F' not in match[1]:
        raise ValueError('ARM64 binfmt must be enabled with fix-binary (F) support. Run setup-wsl.sh.')


@contextmanager
def mounted(source, destination, run, bind=False, readonly=False):
    destination = Path(destination)
    destination.mkdir(parents=True,exist_ok=True)
    if bind:
        run(['mount','--bind',source,destination])
    else:
        if not Path(source).is_file():
            raise ValueError('Offline root must be a regular image file')
        run(['mount','-o','loop,rw',source,destination])
    try:
        run(['mount','--make-private',destination])
        if readonly:
            run(['mount','-o','remount,bind,ro',destination])
        yield destination
    finally:
        # A failed unmount is fatal. The outer workspace refuses recursive cleanup.
        try:
            run(['umount',destination])
        except Exception as e:
            raise CleanupError('Unable to unmount '+str(destination)+'. No output will be published.') from e


@contextmanager
def temporary_file(path, content, mode=0o644):
    path = Path(path)
    backup = path.with_name(path.name+'.chatbox-saved')
    if backup.exists() or backup.is_symlink():
        raise ValueError('Unexpected temporary backup already exists: '+str(backup))
    existed = path.exists() or path.is_symlink()
    path.parent.mkdir(parents=True,exist_ok=True)
    if existed:
        path.rename(backup)
    try:
        path.write_bytes(content.encode() if isinstance(content,str) else content)
        path.chmod(mode)
        yield path
    finally:
        path.unlink(missing_ok=True)
        if existed:
            backup.rename(path)


def guest_environment():
    return ['/usr/bin/env','-i','PATH=/usr/sbin:/usr/bin:/sbin:/bin',
            'HOME=/root','LANG=C','LC_ALL=C','DEBIAN_FRONTEND=noninteractive']


def install(image, scratch, here, lock, paths, run, stream=None):
    """Only mounted scratch-root paths are changed. No device or SPI writes."""
    check_emulation()
    scratch, here = Path(scratch),Path(here)
    cache = paths[0].parent.resolve()
    if any(p.parent.resolve() != cache for p in paths):
        raise ValueError('Kernel packages must share one verified cache directory')
    target = scratch/'arm-root'
    with mounted(image,target,run):
        with ExitStack() as stack:
            for source,relative,readonly in [('/dev','dev',False),('/proc','proc',True),('/sys','sys',True),
                                              (cache,'run/chatbox-build/packages',True)]:
                stack.enter_context(mounted(source,target/relative,run,bind=True,readonly=readonly))
            stack.enter_context(temporary_file(target/'usr/sbin/policy-rc.d','#!/bin/sh\nexit 101\n',0o755))
            stack.enter_context(temporary_file(target/'etc/default/u-boot','U_BOOT_UPDATE=false\n'))
            stack.enter_context(temporary_file(target/'etc/initramfs-tools/conf.d/chatbox-build',
                                               'MODULES=most\nCOMPRESS=gzip\nRESUME=none\n'))
            manifest = '\n'.join('|'.join([item['Package'],item['Version'],path.name,item['SHA256']])
                                   for item,path in zip(lock['packages'],paths))+'\n'
            stack.enter_context(temporary_file(target/'run/chatbox-build/PACKAGES',manifest))
            stack.enter_context(temporary_file(target/'run/chatbox-build/KERNEL_ABI',lock['kernel_abi']+'\n'))
            stack.enter_context(temporary_file(target/'run/chatbox-build/install.sh',
                                  (here/'scripts/install-kernel-target.sh').read_bytes(),0o755))
            stack.enter_context(temporary_file(target/'run/chatbox-build/select-regdb.sh',
                                  (here/'inputs/select-upstream-regdb.sh').read_bytes(),0o755))
            cmd=['chroot',target,*guest_environment()]
            # This executes an actual ARM binary and proves child-interpreter support
            # before allowing the kernel package transaction to start.
            architecture=run([*cmd,'/usr/bin/dpkg','--print-architecture']).strip()
            if architecture != 'arm64':
                raise ValueError('Offline execution did not report ARM64: '+architecture)
            print('Installing ARM64 kernel and generating initramfs under QEMU...',flush=True)
            args=[*cmd,'/bin/bash','/run/chatbox-build/install.sh']
            if stream is None:
                result=subprocess.run([str(x) for x in args])
                if result.returncode:
                    raise RuntimeError('ARM64 kernel preparation failed; no image published')
            else:
                stream(args)
        # These directories belong to this build, not the installed OS.
        for relative in ['run/chatbox-build/packages','run/chatbox-build']:
            (target/relative).rmdir()
        os.sync()
