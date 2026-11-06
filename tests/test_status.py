from contextlib import contextmanager
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'overlay/usr/local/lib/chatbox'))
loader = importlib.machinery.SourceFileLoader('chatbox_status', str(ROOT / 'overlay/usr/local/sbin/chatbox-status'))
spec = importlib.util.spec_from_loader(loader.name, loader)
status = importlib.util.module_from_spec(spec)
loader.exec_module(status)


class StatusTests(unittest.TestCase):
    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        def put(name, value='fixture'):
            p = root / name.lstrip('/')
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(value)
        self.put = put
        put('/boot/vmlinuz-test-kernel')
        symbols = ('CONFIG_BLK_DEV_NVME CONFIG_DRM_ROCKCHIP CONFIG_ROCKCHIP_VOP2 '
                   'CONFIG_SND_SOC_ES8323 CONFIG_SND_USB_AUDIO CONFIG_ROCKCHIP_RKNPU '
                   'CONFIG_DRM_PANTHOR CONFIG_GPIO_CDEV '
                   'CONFIG_SPI_SPIDEV CONFIG_I2C_CHARDEV').split()
        put('/boot/config-test-kernel', '# padding\n' * 3000 + '\n'.join(s + '=y' for s in symbols))
        for path in ('/var/lib/chatbox/provisioned',
                     '/usr/lib/firmware/arm/mali/arch10.8/mali_csffw.bin',
                     '/usr/lib/aarch64-linux-gnu/librkllmrt.so',
                     '/usr/lib/aarch64-linux-gnu/libvulkan_panfrost.so',
                     '/usr/lib/aarch64-linux-gnu/libOpenCL.so.1',
                     '/usr/local/sbin/chatbox-opencl-check'):
            put(path)
        put('/etc/OpenCL/vendors/rusticl.icd', 'libRusticlOpenCL.so.1\n')
        put('/etc/chatbox/app.json', '{"backend":null,"backends":{}}')
        for node in ('gpu-panthor@fb000000', 'npu@fdab0000'):
            (root / 'sys/firmware/devicetree/base' / node).mkdir(parents=True)
        snapshot = {'release': {'release': 'test', 'kernel_abi': 'test-kernel'},
                    'kernel': 'test-kernel',
                    'root_mount': {'stdout': '{"filesystems":[{"source":"/dev/nvme0n1p2"}]}'},
                    'services': {'chatbox-app': {'returncode': 0, 'stdout':
                        'LoadState=loaded\nUnitFileState=enabled\nActiveState=active\nSubState=running\nResult=success\nNRestarts=0'}},
                    'alsa_cards': 'rockchip-es8388', 'render_drivers': {'renderD129': 'rknpu','renderD128':'panthor'},
                    'rknpu_version': 'RKNPU driver: v0.9.8',
                    'devices': {'/dev/mali0': {'readable': True, 'writable': True}},
                    'display_connectors': {'card0-HDMI-A-1': 'connected'}}
        return root, snapshot

    def query(self, endpoint):
        return {'http_status': 200, 'ok': True} if endpoint == '/health' else {'http_status': 503, 'state': 'unconfigured'}

    def rows(self, report):
        return {r['component']: r for r in report['checks']}

    def test_expected_fresh_image_is_not_faulted_for_missing_models_or_claimed_tested(self):
        root, snapshot = self.fixture()
        compute = unittest.mock.Mock(return_value='pass')
        report = status.collect(root, snapshot, self.query)
        rows = self.rows(report)
        self.assertEqual(report['failures'], 0)
        self.assertEqual(rows['chatbox-app']['enabled'], 'enabled')
        self.assertEqual(rows['chatbox-app']['runtime'], 'active/running')
        self.assertEqual(rows['SPI userspace API']['enabled'], 'yes')
        self.assertEqual(rows['NPU device tree']['enabled'], 'yes')
        self.assertEqual(rows['Model readiness']['runtime'], 'unconfigured')
        self.assertEqual(rows['Voice/browser/button/OLED']['installed'], 'not-integrated')
        self.assertTrue(all(r['tested'] == 'not-run' for r in rows.values()))
        self.assertEqual(report['acceptance'], 'not_established')
        self.assertIn('Hardware acceptance: not established', status.render(report))
        compute.assert_not_called()

    def test_disabled_running_failed_and_unavailable_service_states_remain_distinct(self):
        root, snapshot = self.fixture()
        services = snapshot['services']
        services['disabled'] = {'returncode': 0, 'stdout': 'LoadState=loaded\nUnitFileState=disabled\nActiveState=active\nSubState=running\nResult=success'}
        services['failed'] = {'returncode': 0, 'stdout': 'LoadState=loaded\nUnitFileState=enabled\nActiveState=failed\nSubState=failed\nResult=exit-code'}
        services['unknown'] = {'error': 'timeout'}
        rows = self.rows(status.collect(root, snapshot, self.query))
        self.assertEqual(rows['disabled']['enabled'], 'disabled')
        self.assertEqual(rows['disabled']['runtime'], 'active/running')
        self.assertEqual(rows['disabled']['level'], 'WARN')
        self.assertEqual(rows['failed']['level'], 'FAIL')
        self.assertEqual(rows['unknown']['enabled'], 'unknown')
        self.assertEqual(rows['unknown']['level'], 'WARN')

    def test_disabled_kernel_and_live_dt_and_wrong_driver_are_failures(self):
        root, snapshot = self.fixture()
        self.put('/boot/config-test-kernel', '# CONFIG_ROCKCHIP_RKNPU is not set\n')
        self.put('/sys/firmware/devicetree/base/npu@fdab0000/status', 'disabled\x00')
        snapshot['rknpu_version'] = 'v0.9.6'
        rows = self.rows(status.collect(root, snapshot, self.query))
        for name in ('NPU driver', 'NPU device tree', 'NPU registration'):
            self.assertEqual(rows[name]['level'], 'FAIL')

    def test_unreadable_kernel_and_missing_debugfs_do_not_mean_disabled(self):
        root, snapshot = self.fixture()
        (root / 'boot/config-test-kernel').unlink()
        snapshot['rknpu_version'] = None
        rows = self.rows(status.collect(root, snapshot, self.query))
        self.assertEqual(rows['NPU driver']['enabled'], 'unknown')
        self.assertNotEqual(rows['NPU registration']['level'], 'FAIL')

    def test_missing_runtime_kernel_mismatch_and_invalid_config_are_reported_without_secrets(self):
        root, snapshot = self.fixture()
        (root / 'usr/lib/aarch64-linux-gnu/librkllmrt.so').unlink()
        snapshot['release']['kernel_abi'] = 'different'
        self.put('/etc/chatbox/app.json', '{"private-password": "secret"}')
        report = status.collect(root, snapshot, self.query)
        rows = self.rows(report)
        for name in ('RKLLM runtime', 'Kernel', 'Backend configuration'):
            self.assertEqual(rows[name]['level'], 'FAIL')
        self.assertNotIn('private-password', json.dumps(report))
        self.assertNotIn('secret', json.dumps(report))

    def test_ready_listing_does_not_claim_model_inference(self):
        root, snapshot = self.fixture()
        self.put('/etc/chatbox/app.json', '{"backend":"npu","backends":{"npu":{"base_url":"http://127.0.0.1:8000/v1","model":"private-model"}}}')
        report = status.collect(root, snapshot, lambda _: {'http_status': 200, 'ready': True, 'ok': True})
        row = self.rows(report)['Model readiness']
        self.assertEqual(row['runtime'], 'advertised')
        self.assertEqual(row['tested'], 'not-run')
        self.assertNotIn('private-model', json.dumps(report))

    def test_explicit_compute_only_marks_this_gpu_execution_and_preserves_overall_boundary(self):
        root, snapshot = self.fixture()
        for result in ('pass', 'fail', 'timeout', 'unavailable'):
            with self.subTest(result=result):
                compute = unittest.mock.Mock(return_value=result)
                report = status.collect(root, snapshot, self.query, run_compute=compute)
                compute.assert_called_once_with()
                row = self.rows(report)['OpenCL GPU execution']
                self.assertEqual(row['tested'], result)
                self.assertEqual(row['level'], 'OK' if result == 'pass' else 'FAIL')
                self.assertEqual(report['acceptance'], 'not_established')

    def test_compute_requires_success_and_pass_marker_and_handles_timeout(self):
        for code, text, expected in ((0, 'PASS: numbers verified', 'pass'), (1, 'PASS', 'fail'), (0, '', 'fail')):
            with patch.object(status.subprocess, 'run', return_value=subprocess.CompletedProcess([], code, text, '')) as run:
                self.assertEqual(status.compute(), expected)
                self.assertEqual(run.call_args.kwargs['timeout'], 65)
        with patch.object(status.subprocess, 'run', side_effect=subprocess.TimeoutExpired('test', 65)):
            self.assertEqual(status.compute(), 'timeout')

    def test_probe_uses_get_only_filters_private_fields_and_handles_bad_replies(self):
        calls = []
        @contextmanager
        def upstream(backend, endpoint, payload, deadline):
            calls.append((backend.base_url, endpoint, payload))
            class Reply:
                status = 200
                def read(self, limit):
                    return b'{"ok":true,"model":"private-model","state":"private-value"}'
            yield Reply()
        with patch.object(status, 'upstream', upstream):
            result = status.probe('/health')
        self.assertEqual(calls, [('http://127.0.0.1:8088', '/health', None)])
        self.assertEqual(result['state'], 'unknown')
        self.assertNotIn('private', json.dumps(result))
        with patch.object(status, 'upstream', side_effect=OSError('secret')):
            self.assertEqual(status.probe('/ready'), {'error': 'unavailable'})

    def test_cli_json_and_exit_status_and_opt_in_compute(self):
        from contextlib import redirect_stdout
        for failures in (0, 1):
            output = io.StringIO()
            with patch.object(status, 'collect', return_value={'failures': failures}) as collect, redirect_stdout(output):
                self.assertEqual(status.main(['--json']), failures)
                self.assertEqual(json.loads(output.getvalue()), {'failures': failures})
                self.assertIsNone(collect.call_args.kwargs['run_compute'])
        with patch.object(status, 'collect', return_value={'failures': 0}) as collect, redirect_stdout(io.StringIO()):
            status.main(['--json', '--compute'])
            self.assertIs(collect.call_args.kwargs['run_compute'], status.compute)


if __name__ == '__main__':
    unittest.main()
