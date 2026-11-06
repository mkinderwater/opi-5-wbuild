import json
from pathlib import Path
import struct
import subprocess
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'overlay/usr/local/lib/chatbox'))
import vendor
import image
import board_report
import test_status as status_fixtures
status = status_fixtures.status


class CleanupTests(unittest.TestCase):
    def test_actual_uppercase_npu_driver_and_other_driver_names(self):
        fixture = status_fixtures.StatusTests()
        self.addCleanup(fixture.doCleanups)
        root, snapshot = fixture.fixture()
        for name, expected in [('RKNPU','registered'),('rknpu','registered'),
                               ('RkNpU','registered'),('rockchip-drm','not-observed')]:
            with self.subTest(driver=name):
                snapshot['render_drivers']={'renderD129':name}
                rows=fixture.rows(status.collect(root,snapshot,fixture.query))
                self.assertEqual(rows['NPU registration']['runtime'],expected)
                self.assertEqual(rows['NPU registration']['tested'],'not-run')

    def test_legacy_mali_is_rejected_without_pruning_unrelated_config(self):
        config=(ROOT/'inputs/kernel.fragment').read_text()
        vendor.check_config(config)
        for value in ['y','m']:
            with self.assertRaisesRegex(ValueError,'Legacy Mali400'):
                vendor.check_config(config+'\nCONFIG_MALI400='+value+'\n')
        vendor.check_config(config+'\nCONFIG_BT=y\nCONFIG_CFG80211=y\n')

    def test_board_fixes_require_a_fresh_source_and_do_not_edit_soc_definitions(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)
            board=source/'arch/arm64/boot/dts/rockchip/rk3588s-orangepi-5.dts'
            board.parent.mkdir(parents=True);board.write_text('// original\n')
            soc=board.with_name('rk3588s.dtsi');soc.write_text('// unchanged\n')
            vendor.apply_board_fixes(source,ROOT)
            self.assertTrue(board.read_text().startswith('// original\n'))
            self.assertEqual(board.with_name('chatbox-orangepi-5-fixes.dtsi').read_bytes(),(ROOT/'inputs/board-fixes.dtsi').read_bytes())
            self.assertEqual(soc.read_text(),'// unchanged\n')
            with self.assertRaisesRegex(ValueError,'fresh source'):
                vendor.apply_board_fixes(source,ROOT)

    def test_led_gpio_and_pinmux_must_agree_and_gpu_delay_preserves_default(self):
        from fdt_read import Node
        paths=['/gpio-leds','/gpio-leds/led@1','/pinctrl/gpio-func/leds-gpio',
               '/pinctrl/gpio@fec20000','/gpu-panthor@fb000000','/thermal-zones/soc-thermal/cooling-maps/map3']
        nodes={p:Node(p) for p in paths}
        nodes['/gpio-leds'].props['pinctrl-0']=struct.pack('>I',5)
        nodes['/pinctrl/gpio@fec20000'].props['phandle']=struct.pack('>I',4)
        nodes['/gpio-leds/led@1'].props['gpios']=struct.pack('>III',4,2,0)
        group=nodes['/pinctrl/gpio-func/leds-gpio']
        group.props.update({'phandle':struct.pack('>I',5),'rockchip,pins':struct.pack('>IIII',1,2,0,6)})
        nodes['/gpu-panthor@fb000000'].props['phandle']=struct.pack('>I',7)
        nodes['/thermal-zones/soc-thermal/cooling-maps/map3'].props['cooling-device']=struct.pack('>III',7,0xffffffff,0xffffffff)
        vendor.check_board_fixes(nodes)
        group.props['rockchip,pins']=struct.pack('>IIII',0,2,0,6)
        with self.assertRaisesRegex(ValueError,'GPIO1_A2'):vendor.check_board_fixes(nodes)
        group.props['rockchip,pins']=struct.pack('>IIII',1,2,0,6)
        nodes['/thermal-zones/soc-thermal/cooling-maps/map3'].props['cooling-device']=struct.pack('>III',99,0xffffffff,0xffffffff)
        with self.assertRaisesRegex(ValueError,'Thermal map'):vendor.check_board_fixes(nodes)

    def test_boot_warning_scan_redacts_logs_and_does_not_hide_unresolved_warnings(self):
        raw='''private-hash must never be emitted
rockchip-pinctrl: pin gpio0-2 already requested by spi2.0: cannot claim for gpio-leds
nvme nvme0: I/O QID 0 timeout, completion polled
nvme nvme0: IO queues not created
RKNPU: can't request region for resource
platform regulatory.0: Direct firmware load for regulatory.db failed with error -2
vop: error -ENODEV: _opp_set_regulators: no regulator (vop) found
optee: api uid mismatch
arm-scmi: SCMI protocol 17 not active.
'''
        result=board_report.boot_warning_counts(lambda argv:{'returncode':0,'stdout':raw})
        self.assertTrue(result['available'])
        self.assertTrue(all(value==1 for value in result['counts'].values()))
        self.assertNotIn('private-hash',json.dumps(result))
        self.assertFalse(board_report.boot_warning_counts(lambda argv:{'error':'permission'})['available'])
        self.assertTrue(board_report.boot_warning_counts(lambda argv:{'returncode':0,'stdout':'x'*16384})['limited'])

    def test_status_surfaces_warnings_and_legacy_driver(self):
        fixture=status_fixtures.StatusTests();self.addCleanup(fixture.doCleanups)
        root,snapshot=fixture.fixture()
        fixture.put('/boot/config-test-kernel',(root/'boot/config-test-kernel').read_text()+'\nCONFIG_MALI400=y\n')
        snapshot['boot_warnings']={'available':True,'counts':{'npu_resource':3},'limited':False}
        rows=fixture.rows(status.collect(root,snapshot,fixture.query))
        self.assertEqual(rows['Legacy Mali400']['level'],'FAIL')
        self.assertEqual(rows['Boot: npu_resource']['level'],'WARN')

    def test_early_regdb_and_signature_are_required(self):
        image.validate_regdb_initrd('lib/firmware/regulatory.db\nusr/lib/firmware/regulatory.db.p7s\n')
        for listing in ['', 'lib/firmware/regulatory.db\n']:
            with self.assertRaisesRegex(ValueError,'Early boot firmware'):
                image.validate_regdb_initrd(listing)

    def hook_fixture(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        root=Path(temporary.name);firmware=root/'firmware';firmware.mkdir()
        helper=ROOT/'tests/fixtures/debian-copy-file.sh'
        script=(ROOT/'inputs/initramfs-regdb-hook').read_text()
        script=script.replace('/usr/share/initramfs-tools/hook-functions',str(helper))
        script=script.replace('readlink -f "/usr/lib/firmware/$name"',
                              'readlink -f "'+str(firmware)+'/$name"')
        hook=root/'hook';hook.write_text(script)
        dest=root/'initramfs'
        env={**os.environ,'DESTDIR':str(dest),'verbose':'n'}
        def run():return subprocess.run(['sh',str(hook)],env=env,capture_output=True)
        def populate():
            for name in ('regulatory.db','regulatory.db.p7s'):
                actual=firmware/(name+'-debian');actual.write_text(name+' content')
                (firmware/name).symlink_to(actual.name)
        return root,dest,run,populate

    def test_initramfs_hook_copies_resolved_firmware_using_real_debian_helper(self):
        root,dest,run,populate=self.hook_fixture()
        first=run();self.assertEqual(first.returncode,0,first.stderr)
        self.assertFalse(dest.exists())
        populate();result=run()
        self.assertEqual(result.returncode,0,result.stderr)
        for name in ('regulatory.db','regulatory.db.p7s'):
            copied=dest/'usr/lib/firmware'/name
            self.assertFalse(copied.is_symlink())
            self.assertEqual(copied.read_text(),name+' content')

    def test_initramfs_hook_accepts_identical_already_copied_files(self):
        root,dest,run,populate=self.hook_fixture();populate()
        first=run();self.assertEqual(first.returncode,0,first.stderr)
        second=run();self.assertEqual(second.returncode,0,second.stderr)
        for name in ('regulatory.db','regulatory.db.p7s'):
            self.assertEqual((dest/'usr/lib/firmware'/name).read_text(),name+' content')

    def test_initramfs_hook_handles_one_existing_file_and_still_copies_the_other(self):
        for existing in ('regulatory.db','regulatory.db.p7s'):
            with self.subTest(existing=existing):
                root,dest,run,populate=self.hook_fixture();populate()
                target=dest/'usr/lib/firmware'/existing;target.parent.mkdir(parents=True)
                target.write_text(existing+' content')
                result=run();self.assertEqual(result.returncode,0,result.stderr)
                for name in ('regulatory.db','regulatory.db.p7s'):
                    self.assertEqual((dest/'usr/lib/firmware'/name).read_text(),name+' content')

    def test_initramfs_hook_rejects_different_existing_firmware(self):
        root,dest,run,populate=self.hook_fixture();populate()
        target=dest/'usr/lib/firmware/regulatory.db';target.parent.mkdir(parents=True)
        target.write_text('wrong data')
        result=run()
        self.assertNotEqual(result.returncode,0)
        self.assertIn(b'differs from its source',result.stderr)
        self.assertEqual(target.read_text(),'wrong data')

    def test_initramfs_hook_preserves_real_copy_failures(self):
        root,dest,run,populate=self.hook_fixture();populate()
        dest.mkdir();(dest/'usr').write_text('not a directory')
        result=run()
        self.assertGreater(result.returncode,1,result.stderr)


if __name__=='__main__':unittest.main()
