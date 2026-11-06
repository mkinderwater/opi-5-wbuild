"""Read-only board evidence, not a hardware acceptance verdict."""
import json
import os
from pathlib import Path
import platform
import subprocess
from datetime import datetime, timezone

from coordinator import diagnostics


def read_text(path):
    try:
        with path.open('rb') as stream:
            return stream.read(16384).decode('utf-8', errors='replace').replace('\x00', '').strip()
    except OSError:
        return None


def command(argv):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=3,
                                env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
        # Diagnostic stderr can contain paths or arguments; retain only status.
        return {'returncode': result.returncode, 'stdout': result.stdout[:16384].strip()}
    except subprocess.TimeoutExpired:
        return {'error': 'timeout'}
    except OSError:
        return {'error': 'unavailable'}


def boot_warning_counts(run=command):
    result = run(['/usr/bin/dmesg', '--level=err,warn', '--color=never'])
    if result.get('returncode') != 0:
        return {'available': False, 'counts': {}}
    text = result.get('stdout', '').lower()
    patterns = {
        'led_pin_conflict': ('already requested by spi2.0', 'cannot claim for gpio-leds'),
        'nvme_timeout': ('nvme', 'timeout'),
        'nvme_queues': ('nvme', 'io queues not created'),
        'npu_resource': ('rknpu', "can't request region"),
        'regulatory_database': ('regulatory.db',),
        'regulator_opp': ('no regulator (',),
        'optee_interface': ('optee', 'api uid mismatch'),
        'scmi_interface': ('scmi protocol', 'not active'),
    }
    return {'available': True, 'counts': {
        name: sum(all(part in line for part in parts) and
                  (name != 'regulatory_database' or any(word in line for word in
                   ('failed', 'malformed', 'invalid', 'missing', 'rejected', 'error')))
                  for line in text.splitlines())
        for name, parts in patterns.items()},
        'limited': len(result.get('stdout', '')) >= 16384}


def collect(root=Path('/'), run=command):
    def path(value):
        return root / value.lstrip('/')

    release = {}
    raw = read_text(path('/etc/chatbox/release.json'))
    if raw is not None:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                # Exclude identifiers and any future private metadata by default.
                release = {key: parsed[key] for key in (
                    'release', 'board', 'architecture', 'kernel_abi',
                    'kernel_package_version', 'root_input_sha256', 'rknpu_driver',
                    'rkllm_runtime', 'gpu_kernel_driver', 'vulkan_driver', 'opencl_driver', 'mesa_version', 'experimental',
                    'fresh_build') if key in parsed}
        except ValueError:
            release = {'error': 'invalid_release_metadata'}

    devices = {}
    for pattern in ('dri/*', 'mali*', 'dma_heap/*', 'gpiochip*', 'spidev*', 'i2c-*'):
        for device in sorted(path('/dev').glob(pattern)):
            devices['/' + device.relative_to(root).as_posix()] = {
                'readable': os.access(device, os.R_OK),
                'writable': os.access(device, os.W_OK)}

    drivers = {}
    for render in sorted(path('/sys/class/drm').glob('renderD*')):
        link = render / 'device/driver'
        if link.is_symlink():
            drivers[render.name] = link.resolve().name
    connectors = {}
    for status in sorted(path('/sys/class/drm').glob('card*-*/status')):
        connectors[status.parent.name] = read_text(status)

    services = {}
    for unit in ('chatbox-firstboot', 'chatbox-readiness', 'chatbox-app', 'ssh',
                 'systemd-networkd', 'systemd-timesyncd'):
        services[unit] = run(['/usr/bin/systemctl', 'show', unit + '.service',
                              '--property=LoadState,UnitFileState,ActiveState,SubState,Result,NRestarts',
                              '--no-pager'])
    return {
        'schema_version': 1,
        'collected_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'registration_and_state_only',
        'acceptance': 'not_established',
        'kernel': platform.release(),
        'board_model': read_text(path('/proc/device-tree/model')),
        'release': release,
        'root_mount': run(['/usr/bin/findmnt', '--json', '--target', '/',
                           '--output', 'SOURCE,FSTYPE,OPTIONS']),
        'root_capacity': run(['/usr/bin/df', '-B1', '--output=size,used,avail,pcent', '/']),
        'services': services,
        'devices': devices,
        'render_drivers': drivers,
        'display_connectors': connectors,
        'alsa_cards': read_text(path('/proc/asound/cards')),
        'alsa_pcm': read_text(path('/proc/asound/pcm')),
        'rknpu_version': read_text(path('/sys/kernel/debug/rknpu/version')),
        'metrics': diagnostics(path('/sys'), path('/proc')),
        'boot_warnings': boot_warning_counts(run),
        'remaining_manual_checks': [
            'HDMI visible output and SSH access',
            'Microphone intelligibility and speaker playback',
            'chatbox-opencl-check numerical GPU computation',
            'Matching RKLLM model inference and NPU activity',
            'Offline boot, recovery and sustained workload',
            'Complete speech-to-first-audible-response measurement'],
    }
