#!/usr/bin/env python3
"""WSL2 image assembly with offline ARM64 kernel preparation. Never writes physical disks."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import struct
import subprocess
import sys
import tempfile
import uuid
import vendor
import offline

HERE = Path(__file__).resolve().parents[1]
ROOT_URL = 'https://dl.sd-card-images.johang.se/debians/2026-10-26/debian-trixie-arm64-uaw3to.bin.gz'
ROOT_SHA = '4e936990e4ab88ddfac2ef3c386e0358c33f8285841a9f42f81772c044114e5c'
KERNEL_VERSION = '6.12.113-1'
CONFIG_START = 2048
CONFIG_SECTORS = 131072
ROOT_START = CONFIG_START + CONFIG_SECTORS


def run(args, allowed=(0,)):
    p = subprocess.run([str(a) for a in args], text=True, capture_output=True)
    if p.returncode not in allowed:
        raise RuntimeError(f'{args[0]} failed ({p.returncode}):\n{p.stdout}\n{p.stderr}')
    return p.stdout + p.stderr


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def verify(path, expected):
    if not re.fullmatch('[0-9a-fA-F]{64}', expected or ''):
        raise ValueError('A 64-digit SHA-256 pin is required; no automatic trust-on-first-download.')
    actual = sha256(path)
    if actual != expected.lower():
        raise ValueError(f'SHA-256 mismatch for {Path(path).name}: expected {expected}, got {actual}')
    return actual


def make_mbr(disk_id, root_sectors):
    if not 0 < disk_id <= 0xffffffff or not 0 < root_sectors <= 0xffffffff - ROOT_START:
        raise ValueError('Image exceeds supported MBR geometry')
    b = bytearray(512)
    struct.pack_into('<I', b, 440, disk_id)
    for n, typ, start, size, active in [(0, 0x0c, CONFIG_START, CONFIG_SECTORS, 0),
                                      (1, 0x83, ROOT_START, root_sectors, 0x80)]:
        struct.pack_into('<B3sB3sII', b, 446 + 16*n, active, b'\xfe\xff\xff', typ,
                         b'\xfe\xff\xff', start, size)
    b[510:512] = b'\x55\xaa'
    return b


def quote(value):
    value = str(value)
    if '\n' in value or '\r' in value or '\x00' in value:
        raise ValueError('Invalid debugfs pathname')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


class Ext4:
    def __init__(self, image, scratch):
        self.image = Path(image)
        self.scratch = Path(tempfile.mkdtemp(prefix='ext4-io-',dir=scratch))
        self.counter = 0

    def command(self, cmd, write=False):
        return run(['debugfs', *(['-w'] if write else []), '-R', cmd, self.image])

    def exists(self, path):
        return 'Inode:' in self.command('stat ' + quote(path))

    def read(self, path, required=True):
        self.counter += 1
        local = self.scratch / f'read-{self.counter}'
        local.unlink(missing_ok=True)
        out = self.command('dump ' + quote(path) + ' ' + quote(local))
        if not local.is_file():
            if required:
                raise ValueError(f'Required file unavailable: {path}\n{out}')
            return None
        return local.read_bytes()

    def text(self, path, required=True):
        b = self.read(path, required)
        return None if b is None else b.decode('utf8')

    def names(self, path):
        out = self.command('ls -p ' + quote(path))
        return [line.split('/')[5] for line in out.splitlines()
                if line.startswith('/') and len(line.split('/')) > 6
                and line.split('/')[5] not in ('.', '..')]

    def mkdir(self, path):
        for parent in reversed(Path(path).parents):
            if str(parent) != '/' and not self.exists(str(parent)):
                self.command('mkdir ' + quote(parent), True)
        if not self.exists(path):
            self.command('mkdir ' + quote(path), True)
        if not self.exists(path):
            raise ValueError(f'Cannot create directory {path}')

    def remove(self, path):
        if self.exists(path):
            self.command('rm ' + quote(path), True)
            if self.exists(path):
                raise ValueError(f'Cannot remove {path}')

    def write(self, path, content, mode=0o644):
        self.mkdir(str(Path(path).parent))
        self.remove(path)
        self.counter += 1
        local = self.scratch / f'write-{self.counter}'
        local.write_bytes(content.encode() if isinstance(content, str) else content)
        self.command('write ' + quote(local) + ' ' + quote(path), True)
        for field, value in [('mode', '0' + format(0o100000 | mode, 'o')), ('uid', '0'), ('gid', '0')]:
            self.command(f'set_inode_field {quote(path)} {field} {value}', True)
        if self.read(path) != local.read_bytes():
            raise ValueError(f'Offline write verification failed: {path}')

    def symlink(self, path, target):
        self.mkdir(str(Path(path).parent))
        self.remove(path)
        self.command('symlink ' + quote(path) + ' ' + quote(target), True)
        if not self.exists(path):
            raise ValueError(f'Cannot create symlink {path}')


def package_records(text):
    records = {}
    for stanza in text.split('\n\n'):
        fields = dict(line.split(': ', 1) for line in stanza.splitlines() if ': ' in line and not line[0].isspace())
        if fields.get('Status') == 'install ok installed':
            records[fields.get('Package')] = fields
    return records


def select_kernel_package(packages,expected_version):
    kernels=[x for x in packages.values()
             if re.fullmatch(r'linux-image-[0-9]+\..*-arm64',x.get('Package',''))
             and x.get('Architecture')=='arm64' and x.get('Version')==expected_version]
    if len(kernels)!=1:
        raise ValueError(f'Expected exactly one installed ARM64 kernel package at {expected_version}')
    abi=kernels[0]['Package'][len('linux-image-'):]
    if not re.fullmatch('[A-Za-z0-9.+_-]+',abi):
        raise ValueError('Malformed kernel ABI')
    return abi


def validate_initrd_modules(config,listing):
    requirements=[('CONFIG_BLK_DEV_NVME','nvme'),('CONFIG_NVME_CORE','nvme-core'),
                  ('CONFIG_PCIE_ROCKCHIP_DW_HOST','pcie-dw-rockchip'),
                  ('CONFIG_PHY_ROCKCHIP_NANENG_COMBO_PHY','phy-rockchip-naneng-combphy'),
                  ('CONFIG_NVMEM_ROCKCHIP_OTP','nvmem-rockchip-otp'),('CONFIG_EXT4_FS','ext4')]
    for symbol,stem in requirements:
        if re.search('^'+symbol+'=m$',config,re.M):
            if not re.search(r'/'+re.escape(stem)+r'\.ko(?:\.(?:xz|zst|gz))?$',listing,re.M):
                raise ValueError(f'Boot prerequisite {stem} missing from initramfs')


def validate_platform(fs, scratch, expected_version=KERNEL_VERSION):
    osrelease = fs.text('/usr/lib/os-release')
    if not re.search(r'^VERSION_CODENAME=["\']?trixie["\']?$', osrelease, re.M):
        raise ValueError('Root is not Debian Trixie')
    packages = package_records(fs.text('/var/lib/dpkg/status'))
    abi = select_kernel_package(packages,expected_version)
    required_packages = ['openssh-server', 'systemd', 'systemd-resolved',
                         'systemd-timesyncd', 'util-linux', 'e2fsprogs', 'perl-base', 'passwd']
    missing = [p for p in required_packages if p not in packages]
    if missing:
        raise ValueError('Base root lacks required packages: ' + ', '.join(missing) +
                         '. Stage pinned ARM64 packages in a later release; do not install host binaries.')
    for path in [f'/boot/vmlinuz-{abi}', f'/boot/initrd.img-{abi}', f'/boot/config-{abi}',
                 f'/lib/modules/{abi}', '/usr/sbin/sshd', '/usr/bin/perl', '/bin/bash']:
        if not fs.exists(path):
            raise ValueError('Required runtime path absent: ' + path)
    dtb = f'/usr/lib/modules/{abi}/dtb/rockchip/rk3588s-orangepi-5.dtb'
    if not fs.exists(dtb):
        dtb = f'/usr/lib/linux-image-{abi}/rockchip/rk3588s-orangepi-5.dtb'
    if not fs.exists(dtb):
        raise ValueError('Orange Pi 5 DTB missing at ' + dtb)
    sys.path.insert(0, str(HERE / 'scripts'))
    import fdt_read
    dtb_bytes = fs.read(dtb)
    local = Path(scratch) / 'board.dtb'; local.write_bytes(dtb_bytes)
    root = fdt_read.parse(local)
    if not any(c in root.props.get('compatible', b'') for c in [b'xunlong,orangepi-5\0',b'rockchip,rk3588s-orangepi-5\0']):
        raise ValueError('DTB is not for the original Orange Pi 5')
    config = fs.text(f'/boot/config-{abi}')
    for symbol in ['CONFIG_BLK_DEV_NVME', 'CONFIG_EXT4_FS']:
        if not re.search('^' + symbol + '=[ym]$', config, re.M):
            raise ValueError(f'Kernel lacks {symbol}')
    if not any(re.search('^'+s+'=[ym]$',config,re.M) for s in ['CONFIG_PCIE_ROCKCHIP_DW_HOST','CONFIG_PCIE_DW_ROCKCHIP']):
        raise ValueError('Kernel lacks Rockchip PCIe host driver')
    initrd = Path(scratch) / 'initrd'; initrd.write_bytes(fs.read(f'/boot/initrd.img-{abi}'))
    listing = run(['lsinitramfs', initrd])
    validate_initrd_modules(config,listing)
    if expected_version != KERNEL_VERSION:
        validate_regdb_initrd(listing)
    return abi, dtb_bytes, packages


def validate_regdb_initrd(listing):
    for name in ('regulatory.db', 'regulatory.db.p7s'):
        if not re.search(r'^(?:usr/)?lib/firmware/' + re.escape(name) + r'$', listing, re.M):
            raise ValueError('Early boot firmware missing from initramfs: ' + name)


def sanitize_accounts(fs, scratch):
    stage = Path(scratch) / 'accounts'; (stage/'etc').mkdir(parents=True)
    for name in ['passwd','shadow','group','gshadow']:
        (stage/'etc'/name).write_bytes(fs.read('/etc/' + name))
    run([sys.executable, HERE/'scripts/prepare_login_accounts.py', stage])
    # Also reject aliases with UID 0 and human accounts outside Debian's normal range.
    for line in (stage/'etc/passwd').read_text().splitlines():
        p = line.split(':')
        if p[0] != 'root' and int(p[2]) == 0:
            raise ValueError('Unexpected UID-zero account: ' + p[0])
    # Replace, rather than retain, the locked inherited hash.
    shadow = (stage/'etc/shadow').read_text()
    shadow = re.sub(r'^root:[^:]*:', 'root:!:', shadow, flags=re.M)
    (stage/'etc/shadow').write_text(shadow)
    for name in ['passwd','shadow','group','gshadow']:
        fs.write('/etc/'+name, (stage/'etc'/name).read_bytes(), 0o600 if 'shadow' in name else 0o644)
    for p in fs.names('/etc/ssh'):
        if p.startswith('ssh_host_'):
            fs.remove('/etc/ssh/' + p)
    fs.remove('/root/.ssh/authorized_keys')
    for p in fs.names('/home'):
        if fs.exists('/home/'+p+'/.ssh/authorized_keys'):
            fs.remove('/home/'+p+'/.ssh/authorized_keys')
    fs.write('/etc/machine-id', '')
    fs.remove('/var/lib/systemd/random-seed')
    fs.remove('/var/lib/dbus/machine-id')
    fs.symlink('/var/lib/dbus/machine-id', '/etc/machine-id')
    fs.write('/etc/hostname', 'chatbox\n')
    fs.write('/etc/hosts', '127.0.0.1 localhost\n127.0.1.1 chatbox\n::1 localhost ip6-localhost ip6-loopback\n')
    # Firstboot alone enables SSH after credential setup. Socket activation is masked too.
    for unit in ['ssh.service', 'sshd.service', 'ssh.socket']:
        fs.symlink('/etc/systemd/system/'+unit, '/dev/null')


def install_overlay(fs, overlay):
    for local in sorted(overlay.rglob('*')):
        relative = local.relative_to(overlay)
        if '__pycache__' in relative.parts or local.suffix in {'.pyc', '.pyo'}:
            continue
        if local.is_file():
            path = '/' + relative.as_posix()
            fs.write(path, local.read_bytes(), 0o755 if '/sbin/' in path else 0o644)


def customize(fs, scratch, abi, dtb, packages, disk_id, root_uuid, input_sha):
    sanitize_accounts(fs, scratch)
    root_partuuid = f'{disk_id:08x}-02'; config_partuuid = f'{disk_id:08x}-01'
    fs.write('/boot/chatbox-orangepi-5.dtb', dtb)
    fs.write('/boot/extlinux/extlinux.conf', f'''DEFAULT chatbox
TIMEOUT 30
LABEL chatbox
  MENU LABEL Chatbox Debian Trixie
  LINUX /boot/vmlinuz-{abi}
  INITRD /boot/initrd.img-{abi}
  FDT /boot/chatbox-orangepi-5.dtb
  APPEND root=PARTUUID={root_partuuid} rw rootwait console=ttyS2,1500000n8 console=tty1 loglevel=6 systemd.show_status=yes
''')
    # Prevent an inherited update hook regenerating extlinux with the source root UUID.
    fs.write('/etc/default/u-boot', f'U_BOOT_UPDATE=false\nU_BOOT_ROOT="root=PARTUUID={root_partuuid}"\nU_BOOT_PARAMETERS="rw rootwait loglevel=6 systemd.show_status=yes"\nU_BOOT_FDT="/boot/chatbox-orangepi-5.dtb"\n')
    fs.write('/etc/fstab', f'PARTUUID={root_partuuid} / ext4 defaults,noatime 0 1\n')
    fs.write('/etc/chatbox/platform.conf', f'ROOT_PARTUUID={root_partuuid}\nCONFIG_PARTUUID={config_partuuid}\n')
    # A generated identity comes from systemd before firstboot; SSH keys are generated afterwards.
    fs.write('/etc/systemd/network/10-chatbox-ethernet.network', '[Match]\nType=ether\nName=!veth* !docker* !br*\n\n[Network]\nDHCP=ipv4\nIPv6AcceptRA=no\n')
    # Disable source-image network rules instead of letting competing DHCP configurations win.
    for name in fs.names('/etc/systemd/network'):
        if name.endswith('.network') and name != '10-chatbox-ethernet.network':
            fs.remove('/etc/systemd/network/'+name)
    fs.symlink('/etc/resolv.conf', '/run/systemd/resolve/stub-resolv.conf')
    for unit in ['systemd-networkd.service','systemd-resolved.service','systemd-timesyncd.service']:
        fs.symlink('/etc/systemd/system/multi-user.target.wants/'+unit, '/usr/lib/systemd/system/'+unit)
    for unit in ['chatbox-firstboot.service','chatbox-readiness.service','chatbox-app.service']:
        fs.symlink('/etc/systemd/system/multi-user.target.wants/'+unit, '/etc/systemd/system/'+unit)
    fs.write('/etc/systemd/journald.conf.d/chatbox.conf', '[Journal]\nStorage=persistent\nSystemMaxUse=64M\nRuntimeMaxUse=16M\nMaxRetentionSec=7day\n')
    kernel_patterns = 'linux-image-* linux-headers-* linux-base-* linux-binary-* linux-modules-*'
    hardware_version = json.loads((HERE/'inputs/hardware-lock.json').read_text())['version']
    policy = ''.join(f'Package: {kernel_patterns}\nPin: version {version}\nPin-Priority: 1001\n\n'
                     for version in [KERNEL_VERSION, hardware_version])
    policy += f'Package: {kernel_patterns}\nPin: version *\nPin-Priority: -1\n'
    fs.write('/etc/apt/preferences.d/chatbox-kernel', policy)
    mesa_version=json.loads((HERE/'inputs/hardware-lock.json').read_text())['gpu']['mesa_version']
    fs.write('/etc/apt/preferences.d/chatbox-mesa', 'Package: mesa-* libgbm1 libgl1-mesa-dri\nPin: version '+mesa_version+'\nPin-Priority: 1001\n\nPackage: mesa-* libgbm1 libgl1-mesa-dri\nPin: version *\nPin-Priority: -1\n')
    install_overlay(fs, HERE/'overlay')
    report = {'release':'2.0.1-gpu-experimental','board':'orangepi-5','architecture':'arm64','kernel_abi':abi,
              'kernel_package_version':json.loads((HERE/'inputs/hardware-lock.json').read_text())['version'],'root_input_sha256':input_sha,
              'root_partuuid':root_partuuid,'config_partuuid':config_partuuid,'root_filesystem_uuid':root_uuid,
              'hardware_validated':False,'npu_validated':False,'containers_validated':False,
              'rknpu_driver':'0.9.8','rkllm_runtime':'1.2.3',
              'gpu_kernel_driver':'panthor','vulkan_driver':'panvk','opencl_driver':'rusticl',
              'mesa_version':'26.1.6-1~bpo13+1','experimental':True,'vulkan_validated':False,
              'opencl_validated':False,'fresh_build':True,
              'scope':'hardware image; audio/NPU/Panthor GPU drivers, RKLLM, PanVK and Rusticl installed; local text coordinator installed; speech engines/models/OLED application not installed'}
    fs.write('/etc/chatbox/release.json', json.dumps(report, indent=2)+'\n')
    # Validate the final boot policy and credentials before publication.
    if fs.text('/etc/fstab').count(root_partuuid) != 1 or root_partuuid not in fs.text('/boot/extlinux/extlinux.conf'):
        raise ValueError('Final root discovery policy mismatch')
    if not fs.text('/etc/shadow').startswith('root:!:'):
        raise ValueError('Root lock verification failed')
    return report


def check_dependencies():
    if os.geteuid() != 0:
        raise ValueError('Run sudo ./build.sh: offline kernel installation needs loop mounts and chroot.')
    offline.check_emulation()
    required = ['debugfs','e2fsck','resize2fs','tune2fs','lsinitramfs','curl','dpkg-deb','mount','umount','chroot','depmod','make','aarch64-linux-gnu-gcc','flex','bison','bc','pkg-config','glslangValidator']
    missing = [x for x in required if not shutil.which(x)]
    if missing:
        raise ValueError('Missing host tools: '+', '.join(missing)+'. Run sudo ./setup-wsl.sh first.')


def build(root_input, root_sha, output):
    root_input, output = Path(root_input).resolve(), Path(output).resolve()
    if not root_input.is_file():
        raise ValueError('Root input must be a regular gzip file, never a device')
    # Atomic publication requires a new output filename; never overwrite another deliverable.
    if output.exists():
        raise ValueError('Output already exists: '+str(output))
    output.parent.mkdir(parents=True, exist_ok=True)
    input_sha = verify(root_input, root_sha)
    if shutil.disk_usage(output.parent).free < 24*1024**3:
        raise ValueError('At least 24 GiB free workspace is required')
    print('Building fresh audio/NPU/OpenCL hardware set...',flush=True)
    hardware_lock, hardware_paths = vendor.prepare(HERE, root_input.parent/'hardware-inputs', run, verify)
    if shutil.disk_usage(output.parent).free < 24*1024**3:
        raise ValueError('At least 24 GiB of free workspace is required')
    with offline.workspace(output.parent) as tmp:
        scratch = Path(tmp); root = scratch/'root.ext4'
        print('Extracting verified root...', flush=True)
        with gzip.open(root_input, 'rb') as src, root.open('wb') as dst:
            shutil.copyfileobj(src, dst, 1024*1024)
        with root.open('rb') as f:
            f.seek(1080)
            if f.read(2) != b'\x53\xef':
                raise ValueError('Input is not a standalone ext filesystem image')
        run(['e2fsck','-f','-p', root], allowed=(0,1))
        # Give injected files free space without executing ARM code on the host.
        with root.open('r+b') as f:
            f.truncate(((root.stat().st_size + 2048*1024**2 + 1024**2-1)//1024**2)*1024**2)
        run(['resize2fs', root])
        root_uuid = str(uuid.uuid4())
        run(['tune2fs','-U',root_uuid, '-L','CHATROOT', root])
        fs = Ext4(root, scratch)
        recovery_abi, recovery_dtb, packages = validate_platform(fs, scratch)
        offline.install(root,scratch,HERE,hardware_lock,hardware_paths,run)
        # Re-open only after clean unmount. Never mix debugfs writes with mounts.
        fs = Ext4(root,scratch)
        abi,dtb,packages = validate_platform(fs,scratch,hardware_lock['version'])
        if abi != hardware_lock['kernel_abi']:
            raise ValueError('Installed kernel ABI differs from input lock')
        local_dtb=scratch/'installed-display.dtb';local_dtb.write_bytes(dtb)
        vendor.check_tree(local_dtb)
        vendor.check_config(fs.text('/boot/config-'+abi))
        disk_id = secrets.randbelow(0xffffffff) + 1
        report = customize(fs,scratch,abi,dtb,packages,disk_id,root_uuid,input_sha)
        fs.write('/boot/chatbox-recovery.dtb',recovery_dtb)
        fs.write('/etc/chatbox/kernel-abi',abi+'\n')
        menu=run(['bash','-c','source "$1"; render_boot_menu display "$2" "$3"',
                  'bash',HERE/'overlay/usr/local/lib/chatbox/boot-menu.sh',abi,f'{disk_id:08x}-02'])
        fs.write('/boot/extlinux/extlinux.conf',menu)
        if not menu.startswith('DEFAULT display\n'):
            raise ValueError('Primary kernel not selected')
        fs.write('/etc/chatbox/build-inputs.json',json.dumps(hardware_lock,indent=2)+'\n')
        report['recovery_kernel_abi']=recovery_abi
        report['kernel_prepared_at']='WSL2 build time, before flashing'
        fs.write('/etc/chatbox/release.json',json.dumps(report,indent=2)+'\n')
        run(['e2fsck','-f','-p',root], allowed=(0,1))
        fat = scratch/'config.fat'
        run([sys.executable, HERE/'scripts/make_fat32.py', fat, str(CONFIG_SECTORS),
             HERE/'CONFIG.TXT', '--hidden-sectors', str(CONFIG_START), '--volume-id', str(disk_id)])
        mbr = make_mbr(disk_id, root.stat().st_size//512)
        print('Assembling fresh NVMe layout...', flush=True)
        compressed = scratch/'image.gz'
        with compressed.open('wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', filename='', mtime=0, compresslevel=6) as gz:
            gz.write(mbr)
            gz.write(bytes(CONFIG_START*512-512))
            for part in [fat, root]:
                with part.open('rb') as f:
                    shutil.copyfileobj(f, gz, 1024*1024)
        # Fully read the output once to check its gzip CRC, size and MBR geometry.
        expected_size = (ROOT_START*512) + root.stat().st_size
        with gzip.open(compressed, 'rb') as f:
            if f.read(512) != mbr:
                raise ValueError('Output MBR mismatch')
            size = 512
            for block in iter(lambda: f.read(1024*1024), b''):
                size += len(block)
        if size != expected_size:
            raise ValueError('Output image size mismatch')
        digest = sha256(compressed)
        os.replace(compressed, output)
        output.with_name(output.name+'.sha256').write_text(digest+'  '+output.name+'\n')
        output.with_name(output.name+'.json').write_text(json.dumps(report,indent=2)+'\n')
        print('Created '+str(output))
        print('UNTESTED ON HARDWARE: separate SPI provisioning is required.')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,default=HERE/'out/chatbox-2.0.1-gpu-experimental-orangepi5-nvme.img.gz')
    args = ap.parse_args()
    try:
        check_dependencies()
        args.output=args.output.resolve()
        if args.output.exists():raise ValueError('Output already exists: '+str(args.output))
        args.output.parent.mkdir(parents=True,exist_ok=True)
        if shutil.disk_usage(args.output.parent).free < 24*1024**3:
            raise ValueError('At least 24 GiB free workspace is required')
        with offline.workspace(args.output.parent) as fresh:
            root_input=fresh/'debian-root.bin.gz'
            print('Downloading fresh pinned Debian root...',flush=True)
            vendor.fetch(ROOT_URL,root_input,ROOT_SHA,run,verify)
            build(root_input,ROOT_SHA,args.output)
    except (ValueError,RuntimeError,OSError,EOFError) as e:
        print('ERROR: '+str(e),file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
