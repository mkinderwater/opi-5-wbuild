"""Read-only container capability checks. No daemon start, module loading or pulls."""
import gzip
import json
from pathlib import Path
import re
from board_report import command

PROFILE=json.loads(Path(__file__).with_name('container-profile.json').read_text())
def parse_config(text):return dict(re.findall(r'^CONFIG_(\w+)=(.+)$',text,re.M))
def read_kernel_config(root,kernel):
    def path(name):return root/name.lstrip('/')
    values=None;source='unavailable';live=False
    try:
        with gzip.open(path('/proc/config.gz'),'rt') as f:text=f.read(2*1024*1024)
        values=parse_config(text);source='/proc/config.gz';live=True
    except (OSError,EOFError,UnicodeError):
        try:
            text=path('/boot/config-'+kernel).read_text();values=parse_config(text);source='installed /boot/config-'+kernel
        except (OSError,UnicodeError):pass
    return values,source,live

def checks(root,kernel,run=command):
    rows=[]
    def row(name,state,detail,tested='not-run'):
        rows.append(dict(component=name,installed='unknown',configured='unknown',enabled='unknown',
            runtime=state,tested=tested,level={'pass':'OK','fail':'FAIL'}.get(state,'WARN'),detail=detail))
    def path(name):return root/name.lstrip('/')
    values,source,live=read_kernel_config(root,kernel)
    for group,flags in PROFILE['groups'].items():
        if values is None:row('Container '+group,'unknown','Running kernel config unavailable; no container-readiness claim');continue
        missing=[f'CONFIG_{k}={values.get(k,"unset")}' for k in flags if values.get(k)!='y']
        row('Container '+group,'fail' if missing else 'pass' if live else 'unknown',
            source+': '+(', '.join(missing) if missing else 'all profile flags built in'+('' if live else '; running kernel config not confirmed')))
    try:
        filesystems=path('/proc/filesystems').read_text().split()
        row('OverlayFS registered','pass' if 'overlay' in filesystems else 'fail',
            'Live filesystem registration only; no overlay mount attempted')
    except OSError:row('OverlayFS registered','unknown','Cannot read live filesystem list')
    try:
        controllers=set(path('/sys/fs/cgroup/cgroup.controllers').read_text().split())
        missing={'cpu','cpuset','io','memory','pids'}-controllers
        row('Cgroup v2 controllers','fail' if missing else 'pass',
            'Missing: '+', '.join(sorted(missing)) if missing else 'CPU, cpuset, I/O, memory and PID controllers available; limits not exercised')
    except OSError:row('Cgroup v2 controllers','unknown','Unified hierarchy unavailable; kernel flags alone do not establish live limits')
    active=run(['/usr/bin/systemctl','is-active','docker.service'])
    if active.get('returncode')==0:
        # Query only an already active daemon, avoiding socket activation during read-only checks.
        info=run(['/usr/bin/docker','info','--format','{{json .}}'])
        try:
            d=json.loads(info.get('stdout',''))
            if info.get('returncode')!=0:raise ValueError('unavailable')
            row('Docker daemon','pass',f'Driver={d.get("Driver","unknown")}; cgroup={d.get("CgroupVersion","unknown")}; process available, containers not tested')
        except (ValueError,TypeError):row('Docker daemon','fail','Active service did not provide Docker info')
    else:row('Docker daemon','unknown','Not active or not installed; checker does not start it. Kernel capability can be checked without Docker.')
    row('Container functional proof','unknown','Not run by this read-only checker. Run chatbox-container-test explicitly to exercise storage, bridge/NAT, port mapping and limits.')
    return rows
