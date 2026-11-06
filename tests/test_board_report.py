import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'overlay/usr/local/lib/chatbox'))
import board_report
sys.path.insert(0, str(ROOT / 'scripts'))
import image


class BoardReportTests(unittest.TestCase):
    def test_partial_board_reports_unknown_without_claiming_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []
            def run(argv):
                calls.append(argv)
                return {'error': 'unavailable'}
            result = board_report.collect(root, run)
            self.assertIsNone(result['rknpu_version'])
            self.assertIsNone(result['alsa_cards'])
            self.assertEqual(result['acceptance'], 'not_established')
            self.assertEqual(len(result['services']), 6)
            self.assertTrue(all('error' in value for value in result['services'].values()))
            self.assertEqual(len(calls), 9)
            self.assertFalse(any('start' in argv or 'mount' in argv for argv in calls))
            json.dumps(result)

    def test_registered_hardware_is_evidence_not_inference_and_private_files_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixtures = {
                'etc/chatbox/release.json': json.dumps({'release': 'test', 'kernel_abi': 'test-kernel',
                    'root_partuuid': 'private-identity', 'ROOT_PASSWORD': 'private-password'}),
                'proc/device-tree/model': 'Xunlong Orange Pi 5\x00',
                'proc/asound/cards': 'ES8388',
                'sys/kernel/debug/rknpu/version': 'v0.9.8',
                'sys/class/drm/card0-HDMI-A-1/status': 'connected',
                'dev/dri/renderD129': '',
                'CONFIG.TXT': 'private-password',
                'etc/shadow': 'private-hash',
            }
            for name, text in fixtures.items():
                dest = root / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(text)
            link = root / 'sys/class/drm/renderD129/device/driver'
            link.parent.mkdir(parents=True)
            link.symlink_to(root / 'sys/bus/platform/drivers/rknpu')
            result = board_report.collect(root, lambda argv: {'returncode': 0, 'stdout': ''})
            self.assertEqual(result['board_model'], 'Xunlong Orange Pi 5')
            self.assertEqual(result['render_drivers'], {'renderD129': 'rknpu'})
            self.assertEqual(result['display_connectors'], {'card0-HDMI-A-1': 'connected'})
            self.assertIn('/dev/dri/renderD129', result['devices'])
            self.assertEqual(result['rknpu_version'], 'v0.9.8')
            self.assertEqual(result['acceptance'], 'not_established')
            encoded = json.dumps(result)
            for secret in ('private-password', 'private-hash', 'private-identity'):
                self.assertNotIn(secret, encoded)
            self.assertEqual((root / 'etc/shadow').read_text(), 'private-hash')

    def test_failed_commands_and_timeouts_remain_bounded_evidence(self):
        with patch.object(board_report.subprocess, 'run', side_effect=subprocess.TimeoutExpired('x', 3)):
            self.assertEqual(board_report.command(['/usr/bin/false']), {'error': 'timeout'})
        with patch.object(board_report.subprocess, 'run', side_effect=FileNotFoundError):
            self.assertEqual(board_report.command(['/missing']), {'error': 'unavailable'})
        with patch.object(board_report.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, 'partial', 'secret')) as run:
            self.assertEqual(board_report.command(['/usr/bin/false']), {'returncode': 1, 'stdout': 'partial'})
            self.assertEqual(run.call_args.kwargs['timeout'], 3)


class OverlayTests(unittest.TestCase):
    def test_image_overlay_excludes_generated_bytecode_and_preserves_source_and_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            overlay = Path(directory)
            fixtures = ['usr/local/lib/chatbox/module.py',
                        'usr/local/lib/chatbox/__pycache__/module.cpython-313.pyc',
                        'usr/local/lib/chatbox/stale.pyc', 'usr/local/lib/chatbox/stale.pyo',
                        'usr/local/sbin/chatbox-board-report']
            for name in fixtures:
                path = overlay / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'fixture')
            writes = {}
            class FS:
                def write(self, name, data, mode):
                    writes[name] = (data, mode)
            image.install_overlay(FS(), overlay)
            self.assertEqual(writes, {
                '/usr/local/lib/chatbox/module.py': (b'fixture', 0o644),
                '/usr/local/sbin/chatbox-board-report': (b'fixture', 0o755)})


if __name__ == '__main__':
    unittest.main()
