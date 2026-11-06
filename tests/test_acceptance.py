import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'overlay/usr/local/lib/chatbox'))
import acceptance
import test_status as status_fixture


class AcceptanceTests(unittest.TestCase):
    def fixture(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        root=Path(temporary.name)
        def put(file,value):
            path=root/file.lstrip('/');path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(value if isinstance(value,bytes) else value.encode())
        self.put=put
        base='/sys/firmware/devicetree/base'
        for file,values in [('/pinctrl/gpio-func/leds-gpio/rockchip,pins',(1,2,0,10)),
                            ('/gpio-leds/led@1/gpios',(7,2,0)),
                            ('/pinctrl/gpio@fec20000/phandle',(7,)),
                            ('/pinctrl/gpio-func/leds-gpio/phandle',(8,)),
                            ('/gpio-leds/pinctrl-0',(8,)),
                            ('/gpu-panthor@fb000000/phandle',(9,)),
                            ('/thermal-zones/soc-thermal/cooling-maps/map3/cooling-device',(9,0xffffffff,0xffffffff))]:
            put(base+file,struct.pack('>'+'I'*len(values),*values))
        abi='6.1.172-chatbox8-arm64'
        for name in ['/boot/initrd.img-'+abi,'/lib/modules/'+abi+'/modules.dep',
                     '/boot/chatbox-orangepi-5.dtb','/usr/lib/firmware/regulatory.db.p7s']:
            put(name,'present')
        for name in ['/usr/lib/aarch64-linux-gnu/librkllmrt.so',
                     '/usr/lib/aarch64-linux-gnu/libvulkan_panfrost.so',
                     '/usr/lib/firmware/arm/mali/arch10.8/mali_csffw.bin',
                     '/etc/OpenCL/vendors/rusticl.icd','/usr/share/vulkan/icd.d/panfrost_icd.json']:
            put(name,'verified payload')
        for name in ('regulatory.db','regulatory.db.p7s'):
            put('/usr/lib/firmware/'+name+'-upstream','upstream signed firmware')
            alias=root/'usr/lib/firmware'/name
            alias.unlink(missing_ok=True);alias.symlink_to(name+'-upstream')
        digest=hashlib.sha256(b'verified payload').hexdigest()
        lock={'rkllm':{'files':[{'name':'librkllmrt.so','SHA256':digest}]},
              'gpu':{'assets':{name:digest for name in ['/usr/lib/aarch64-linux-gnu/libvulkan_panfrost.so','/usr/lib/firmware/arm/mali/arch10.8/mali_csffw.bin','/etc/OpenCL/vendors/rusticl.icd','/usr/share/vulkan/icd.d/panfrost_icd.json']}}}
        put('/etc/chatbox/build-inputs.json',json.dumps(lock))
        snapshot={'release':{'release':'2.0.1-gpu-experimental'},'kernel':abi,
                  'root_mount':{'stdout':'{"filesystems":[{"source":"/dev/nvme0n1p2"}]}'},
                  'root_capacity':{'stdout':'1B-blocks Used Available Use%\n254000000000 1000000000 253000000000 1%\n'}}
        def run(argv):
            if argv[0].endswith('systemctl'):return {'returncode':0,'stdout':''}
            if argv[0].endswith('timedatectl'):return {'returncode':0,'stdout':'yes\n'}
            if argv[0].endswith('lsinitramfs'):return {'returncode':0,'stdout':'lib/firmware/regulatory.db\nlib/firmware/regulatory.db.p7s\n'}
            if argv[0].endswith('lsblk'):
                return {'returncode':0,'stdout':json.dumps({'blockdevices':[{'name':'nvme0n1','size':256000000000,
                    'children':[{'name':'nvme0n1p2','size':255930000000}]}]})}
            self.fail('Unexpected command: '+repr(argv))
        return root,snapshot,run

    def rows(self,root,snapshot,run):
        return {row['component']:row for row in acceptance.vet_baseline(root,snapshot,run)}

    def test_complete_evidence_passes_checks_without_marking_functional_tests_passed(self):
        root,snapshot,run=self.fixture()
        before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
        rows=self.rows(root,snapshot,run)
        self.assertTrue(all(row['level']=='OK' for row in rows.values()),rows)
        self.assertTrue(all(row['tested']=='not-run' for row in rows.values()))
        self.assertEqual(before,{str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_old_release_does_not_pass_018_target_with_new_checker(self):
        root,snapshot,run=self.fixture()
        snapshot['release']['release']='0.1.7'
        self.assertEqual(self.rows(root,snapshot,run)['2.0.1-gpu-experimental target']['level'],'FAIL')

    def test_live_led_conflict_and_missing_gpu_delay_are_distinct_from_success(self):
        root,snapshot,run=self.fixture()
        self.put('/sys/firmware/devicetree/base/pinctrl/gpio-func/leds-gpio/rockchip,pins',struct.pack('>IIII',0,2,0,10))
        (root/'sys/firmware/devicetree/base/thermal-zones/soc-thermal/cooling-maps/map3/cooling-device').unlink()
        rows=self.rows(root,snapshot,run)
        self.assertEqual(rows['Live LED pin mapping']['level'],'FAIL')
        self.assertEqual(rows['Live GPU cooling map']['level'],'FAIL')

    def test_corrupt_runtime_and_missing_boot_asset_fail(self):
        root,snapshot,run=self.fixture()
        self.put('/usr/lib/aarch64-linux-gnu/libvulkan_panfrost.so','corrupt')
        (root/'boot/initrd.img-6.1.172-chatbox8-arm64').unlink()
        rows=self.rows(root,snapshot,run)
        self.assertEqual(rows['GPU asset hash /usr/lib/aarch64-linux-gnu/libvulkan_panfrost.so']['level'],'FAIL')
        self.assertEqual(rows['Matched initramfs']['level'],'FAIL')

    def test_provenance_cannot_select_private_files(self):
        root,snapshot,run=self.fixture()
        metadata=root/'etc/chatbox/build-inputs.json'
        lock=json.loads(metadata.read_text())
        lock['gpu']['assets']['/etc/shadow']='0'*64
        metadata.write_text(json.dumps(lock))
        self.put('/etc/shadow','secret-password-hash')
        original=Path.open
        def guarded(file,*args,**kwargs):
            self.assertNotEqual(file,root/'etc/shadow')
            return original(file,*args,**kwargs)
        with patch.object(Path,'open',guarded):
            rows=self.rows(root,snapshot,run)
        self.assertEqual(rows['Runtime/firmware hashes']['level'],'WARN')
        self.assertNotIn('secret-password-hash',json.dumps(rows))

    def test_unexpanded_partition_and_filesystem_are_detected_separately(self):
        root,snapshot,run=self.fixture()
        snapshot['root_capacity']['stdout']='Size Used Avail Use%\n4000000000 100000 3999900000 1%\n'
        self.assertEqual(self.rows(root,snapshot,run)['Root filesystem expansion']['level'],'FAIL')
        def small_partition(argv):
            if argv[0].endswith('lsblk'):
                return {'returncode':0,'stdout':json.dumps({'blockdevices':[{'size':256000000000,
                    'children':[{'name':'nvme0n1p2','size':4500000000}]}]})}
            return run(argv)
        self.assertEqual(self.rows(root,snapshot,small_partition)['NVMe partition expansion']['level'],'FAIL')

    def test_failed_unit_and_unsynchronized_clock_do_not_hide_behind_running_services(self):
        root,snapshot,run=self.fixture()
        def failed(argv):
            if argv[0].endswith('systemctl'):return {'returncode':0,'stdout':'other.service loaded failed failed Private description\n'}
            if argv[0].endswith('timedatectl'):return {'returncode':0,'stdout':'no\n'}
            return run(argv)
        rows=self.rows(root,snapshot,failed)
        self.assertEqual(rows['All failed units']['level'],'FAIL')
        self.assertEqual(rows['Time synchronization']['level'],'WARN')
        self.assertNotIn('Private description',json.dumps(rows))

    def test_100mbit_link_is_reported_without_claiming_gigabit(self):
        root,snapshot,run=self.fixture()
        self.put('/sys/class/net/end0/carrier','1\n')
        self.put('/sys/class/net/end0/speed','100\n')
        (root/'sys/class/net/end0/device').mkdir()
        row=self.rows(root,snapshot,run)['Ethernet link end0']
        self.assertEqual(row['level'],'WARN')
        self.assertIn('100 Mbps',row['detail'])
        self.put('/sys/class/net/end0/speed','1000\n')
        self.assertEqual(self.rows(root,snapshot,run)['Ethernet link end0']['level'],'OK')

    def test_unavailable_commands_remain_unknown(self):
        root,snapshot,run=self.fixture()
        rows=self.rows(root,snapshot,lambda argv:{'error':'unavailable'})
        self.assertEqual(rows['All failed units']['level'],'WARN')
        self.assertEqual(rows['NVMe expansion evidence']['level'],'WARN')

    def test_missing_early_firmware_fails_but_truncated_listing_is_unknown(self):
        root,snapshot,run=self.fixture()
        for listing,expected in [('lib/firmware/regulatory.db\n','FAIL'),('x'*16384,'WARN')]:
            def inspect(argv):
                return {'returncode':0,'stdout':listing} if argv[0].endswith('lsinitramfs') else run(argv)
            self.assertEqual(self.rows(root,snapshot,inspect)['Early regulatory firmware']['level'],expected)

    def test_summary_retains_physical_tests_after_gpu_pass(self):
        report={'checks':[{'component':'OpenCL GPU execution','tested':'pass','level':'OK'},{'component':'Vulkan GPU execution','tested':'pass','level':'OK'}],
                'notes':[],'acceptance':'not_established'}
        result=acceptance.finish(report,True)
        self.assertEqual(result['baseline_state'],'checks-passed')
        self.assertEqual(result['acceptance'],'not_established')
        self.assertTrue(any('RKLLM' in item for item in result['remaining_tests']))
        self.assertFalse(any('--compute' in item for item in result['remaining_tests']))

    def test_cli_explicitly_selects_vetting(self):
        from contextlib import redirect_stdout
        import io
        with patch.object(status_fixture.status,'collect',return_value={'failures':0}) as collect,redirect_stdout(io.StringIO()):
            self.assertEqual(status_fixture.status.main(['--vet','--json']),0)
            self.assertTrue(collect.call_args.kwargs['vet'])

    def test_checker_installer_updates_only_diagnostics_and_requires_existing_app(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)
            env={**os.environ,'DESTDIR':str(target)}
            installer=ROOT/'scripts/install-checker.sh'
            failed=subprocess.run(['bash',str(installer)],env=env,capture_output=True)
            self.assertNotEqual(failed.returncode,0)
            self.assertEqual(list(target.iterdir()),[])
            existing=target/'usr/local/lib/chatbox/coordinator.py'
            existing.parent.mkdir(parents=True);existing.write_text('existing application')
            result=subprocess.run(['bash',str(installer)],env=env,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(existing.read_text(),'existing application')
            names={str(p.relative_to(target)) for p in target.rglob('*') if p.is_file()}
            self.assertEqual(names,{'usr/local/lib/chatbox/coordinator.py','usr/local/lib/chatbox/acceptance.py',
                'usr/local/lib/chatbox/board_report.py','usr/local/sbin/chatbox-status','usr/local/sbin/chatbox-hardware-check',
                'usr/local/lib/chatbox/containers.py','usr/local/lib/chatbox/container-profile.json',
                'usr/local/lib/chatbox/container-test-input.json','usr/local/sbin/chatbox-container-test'})
            self.assertEqual((target/'usr/local/sbin/chatbox-status').stat().st_mode&0o777,0o755)
            self.assertEqual((target/'usr/local/lib/chatbox/acceptance.py').stat().st_mode&0o777,0o644)


if __name__=='__main__':unittest.main()
