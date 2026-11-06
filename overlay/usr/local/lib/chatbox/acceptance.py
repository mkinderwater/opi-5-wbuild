"""Read-only acceptance checks for the 2.0.1-gpu-experimental platform. No model or audio tests."""
import hashlib
import json
from pathlib import Path
import re
import struct

from board_report import command, read_text

CHECKER_REVISION = '2.0.1-gpu-experimental'


def vet_baseline(root, snapshot, run=command):
    rows = []
    def path(name):
        return root / name.lstrip('/')
    def row(name, state, detail):
        rows.append(dict(component=name, installed='unknown', configured='unknown',
                         enabled='unknown', runtime=state, tested='not-run',
                         level='OK' if state == 'matches' else 'FAIL' if state == 'mismatch' else 'WARN',
                         detail=detail))
    def binary(name):
        try:
            with path(name).open('rb') as stream:
                return stream.read(4097)
        except OSError:
            return None
    def cells(name):
        raw=binary(name)
        return struct.unpack('>'+'I'*(len(raw)//4),raw) if raw and len(raw)<=4096 and len(raw)%4==0 else None
    release=snapshot.get('release',{})
    kernel=snapshot.get('kernel','')
    # This is deliberately a versioned acceptance target, not just a comparison
    # of two potentially old on-device metadata files.
    row('2.0.1-gpu-experimental target', 'matches' if release.get('release')=='2.0.1-gpu-experimental' and kernel=='6.1.172-chatbox8-arm64' else 'mismatch',
        'Requires image 2.0.1-gpu-experimental running 6.1.172-chatbox8-arm64; checker updates do not upgrade the image')
    base='/sys/firmware/devicetree/base'
    pins=cells(base+'/pinctrl/gpio-func/leds-gpio/rockchip,pins')
    gpio=cells(base+'/gpio-leds/led@1/gpios')
    controller=cells(base+'/pinctrl/gpio@fec20000/phandle')
    group=cells(base+'/pinctrl/gpio-func/leds-gpio/phandle')
    selected=cells(base+'/gpio-leds/pinctrl-0')
    available=all(value is not None for value in (pins,gpio,controller,group,selected))
    match=available and len(pins)==4 and pins[:3]==(1,2,0) and len(controller)==1 and gpio==(controller[0],2,0) and group==selected and len(group)==1
    row('Live LED pin mapping', 'matches' if match else 'mismatch' if available else 'unknown',
        'Checks live GPIO1_A2, active-high and matching pinctrl/GPIO phandles; physical LED remains untested')
    gpu_handle=cells(base+'/gpu-panthor@fb000000/phandle')
    cooling=cells(base+'/thermal-zones/soc-thermal/cooling-maps/map3/cooling-device')
    row('Live GPU cooling map','matches' if gpu_handle and cooling and cooling[:1]==gpu_handle else 'mismatch',
        'Cooling map must reference the active Panthor node')
    for name,file in [('Matched initramfs','/boot/initrd.img-'+kernel),
                      ('Matched module index','/lib/modules/'+kernel+'/modules.dep'),
                      ('Installed board DTB','/boot/chatbox-orangepi-5.dtb'),
                      ('Regulatory signature','/usr/lib/firmware/regulatory.db.p7s')]:
        try:
            stat=path(file).stat()
            okay=path(file).is_file() and stat.st_size>0
            row(name,'matches' if okay else 'mismatch','Nonempty asset present; file presence does not prove boot-time use')
        except FileNotFoundError:
            row(name,'mismatch','Required asset absent')
        except OSError:
            row(name,'unknown','Asset unreadable')

    try:
        db=path('/usr/lib/firmware/regulatory.db').resolve(strict=True)
        sig=path('/usr/lib/firmware/regulatory.db.p7s').resolve(strict=True)
        upstream=db.name=='regulatory.db-upstream' and sig.name=='regulatory.db.p7s-upstream'
        row('Regulatory signing variant','matches' if upstream else 'mismatch',
            'Upstream database/signature selected for the pinned kernel keys; kernel acceptance still requires boot verification')
    except (OSError,RuntimeError):
        row('Regulatory signing variant','unknown','Cannot resolve database/signature alternatives')

    initrd=run(['/usr/bin/lsinitramfs',str(path('/boot/initrd.img-'+kernel))])
    if initrd.get('returncode')==0:
        listing=initrd.get('stdout','')
        present=all(re.search(r'^(?:usr/)?lib/firmware/'+re.escape(name)+r'$',listing,re.M)
                    for name in ('regulatory.db','regulatory.db.p7s'))
        state='matches' if present else 'unknown' if len(listing)>=16384 else 'mismatch'
        row('Early regulatory firmware',state,
            'Database and signature listed in installed initramfs' if present else
            'Listing truncated; cannot establish early firmware presence' if state=='unknown' else
            'Database or signature absent from initramfs')
    else:row('Early regulatory firmware','unknown','Initramfs contents unavailable; no archive is modified')

    try:
        with path('/etc/chatbox/build-inputs.json').open('rb') as stream:
            raw=stream.read(1048577)
        if len(raw)>1048576:raise ValueError('oversized')
        lock=json.loads(raw)
        assets=[('RKLLM runtime hash','/usr/lib/aarch64-linux-gnu/librkllmrt.so',
                 next(x['SHA256'] for x in lock['rkllm']['files'] if x['name']=='librkllmrt.so'))]
        allowed={'/usr/lib/firmware/arm/mali/arch10.8/mali_csffw.bin',
                 '/usr/lib/aarch64-linux-gnu/libvulkan_panfrost.so',
                 '/etc/OpenCL/vendors/rusticl.icd','/usr/share/vulkan/icd.d/panfrost_icd.json'}
        if set(lock['gpu']['assets']) != allowed:raise ValueError('GPU asset paths')
        assets += [('GPU asset hash '+file,file,digest) for file,digest in lock['gpu']['assets'].items()]
        if not all(isinstance(h,str) and re.fullmatch('[0-9a-f]{64}',h) for _,_,h in assets):raise ValueError('digest')
        for name,file,digest in assets:
            try:
                if path(file).stat().st_size>512*1024**2:
                    row(name,'mismatch','Unexpectedly oversized asset; not hashed');continue
                calculated=hashlib.sha256()
                with path(file).open('rb') as stream:
                    while chunk:=stream.read(1048576):calculated.update(chunk)
                row(name,'matches' if calculated.hexdigest()==digest else 'mismatch',
                    'SHA-256 compared with local build provenance; not independent attestation or embedded firmware proof')
            except FileNotFoundError:
                row(name,'mismatch','Required asset absent')
            except OSError:
                row(name,'unknown','Asset unreadable')
    except (OSError,ValueError,TypeError,KeyError,StopIteration):
        row('Runtime/firmware hashes','unknown','Build provenance missing or invalid; contents suppressed')

    failed=run(['/usr/bin/systemctl','list-units','--state=failed','--no-legend','--plain','--no-pager'])
    if failed.get('returncode')==0:
        count=len([line for line in failed.get('stdout','').splitlines() if line.strip()])
        row('All failed units','matches' if count==0 else 'mismatch',
            str(count)+' failed unit(s); use systemctl --failed for details')
    else:row('All failed units','unknown','systemd failed-unit query unavailable')
    sync=run(['/usr/bin/timedatectl','show','--property=NTPSynchronized','--value'])
    synchronized=sync.get('stdout','').strip()
    row('Time synchronization','matches' if sync.get('returncode')==0 and synchronized=='yes' else 'unknown',
        'NTP synchronization confirmed' if sync.get('returncode')==0 and synchronized=='yes' else 'Not synchronized or unavailable; running timesyncd alone is insufficient')

    for interface in sorted(path('/sys/class/net').glob('*')):
        if not (interface/'device').exists():continue
        carrier=read_text(interface/'carrier');speed=read_text(interface/'speed')
        okay=carrier=='1' and speed is not None and speed.isdecimal() and int(speed)>=1000
        row('Ethernet link '+interface.name,'matches' if okay else 'unknown',
            'Physical link at '+speed+' Mbps' if carrier=='1' and speed and speed.isdecimal() else 'Physical Ethernet disconnected or link data unavailable')

    try:
        mount=json.loads(snapshot['root_mount']['stdout'])['filesystems'][0]
        source=mount['source']
        if not isinstance(source,str) or not re.fullmatch('/dev/nvme[0-9]+n[0-9]+p[0-9]+',source):raise ValueError('root')
        disk=re.sub('p[0-9]+$','',source)
        result=run(['/usr/bin/lsblk','--json','--bytes','--output','NAME,TYPE,SIZE,PKNAME',disk])
        if result.get('returncode')!=0:raise ValueError('lsblk')
        device=json.loads(result['stdout'])['blockdevices'][0]
        part=next(x for x in device.get('children',[]) if '/dev/'+x['name']==source)
        disk_size=int(device['size']);part_size=int(part['size'])
        if disk_size<=0 or part_size<=0 or part_size>disk_size:raise ValueError('size')
        expanded=disk_size-part_size<=256*1024**2
        row('NVMe partition expansion','matches' if expanded else 'mismatch',
            'Root partition occupies drive except up to 256 MiB for config/alignment; other layouts require manual review')
        lines=snapshot.get('root_capacity',{}).get('stdout','').splitlines()
        filesystem_size=int(lines[-1].split()[0])
        if filesystem_size<=0 or filesystem_size>part_size:raise ValueError('filesystem size')
        row('Root filesystem expansion','matches' if filesystem_size>=part_size*0.90 else 'mismatch',
            'Filesystem size compared with root partition; allows up to 10% metadata/reserve difference')
    except (KeyError,ValueError,TypeError,IndexError,StopIteration):
        row('NVMe expansion evidence','unknown','Cannot establish full disk/partition/filesystem sizes; no resizing attempted')
    return rows


def finish(report, vetted=False):
    report['checker_revision']=CHECKER_REVISION
    report['vet_mode']=vetted
    report['failures']=sum(row['level']=='FAIL' for row in report['checks'])
    report['warnings']=sum(row['level']=='WARN' for row in report['checks'])
    report['baseline_state']='blocked' if report['failures'] else 'review-required' if report['warnings'] else 'checks-passed'
    report['remaining_tests']=[
        'Confirm visible HDMI and physical heartbeat LED',
        'Record intelligible microphone audio and verify speaker playback; persist mixer settings',
        'Run a matching RKLLM model and observe NPU activity',
        'Validate Whisper Vulkan and MLC OpenCL application compatibility separately',
        'Repeat at least three cold boots and three warm reboots; retain each report',
        'Validate sustained load, clean shutdown and recovery boot',
    ]
    gpu=next((row for row in report['checks'] if row['component']=='OpenCL GPU execution'),{})
    vk=next((row for row in report['checks'] if row['component']=='Vulkan GPU execution'),{})
    if gpu.get('tested')!='pass' or vk.get('tested')!='pass':report['remaining_tests'].insert(0,'Run chatbox-status --vet --compute for OpenCL and Vulkan numerical GPU tests')
    report['notes'].append('Baseline state covers selected checks only. Remaining physical tests are never marked passed automatically.')
    return report
