from pathlib import Path
import sys
import os
import tempfile
import struct
import tarfile
import subprocess
import json
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import vendor
import fdt_read

class HardwareValidationTests(unittest.TestCase):
    def test_codec_and_vendor_npu_cannot_be_replaced_by_node_presence(self):
        config=(ROOT/'inputs/kernel.fragment').read_text()
        vendor.check_config(config)
        for symbol in ['CONFIG_SND_SOC_ES8323','CONFIG_ROCKCHIP_RKNPU',
                       'CONFIG_ROCKCHIP_RKNPU_DRM_GEM','CONFIG_PCIE_DW_ROCKCHIP']:
            for setting in ['m','n']:
                with self.subTest(symbol=symbol,setting=setting):
                    with self.assertRaises(ValueError):
                        vendor.check_config(config.replace(symbol+'=y',symbol+'='+setting))
        with self.assertRaises(ValueError):
            vendor.check_config(config.replace('CONFIG_ROCKCHIP_RKNPU=y','CONFIG_DRM_ACCEL=y'))

    def test_enabled_nodes_must_also_have_matching_audio_and_iommu_links(self):
        root=fdt_read.Node('')
        root.props['compatible']=b'rockchip,rk3588s-orangepi-5\0'
        nodes={}
        for path in ['/vop@fdd90000','/hdmi@fde80000','/es8388-sound',
                     '/i2c@fec80000','/i2c@fec80000/es8388@10',
                     '/i2s@fe480000','/npu@fdab0000','/iommu@fdab9000','/gpu-panthor@fb000000','/gpu@fb000000','/thermal-zones/soc-thermal/cooling-maps/map3','/regulator-gpu']:
            parent=root
            for component in path.strip('/').split('/'):
                child=parent.child(component)
                if child is None:
                    child=fdt_read.Node(component,parent);parent.children.append(child)
                parent=child
            parent.props['status']=b'okay\0';nodes[path]=parent
        nodes['/regulator-gpu'].props['phandle']=struct.pack('>I',9)
        nodes['/gpu@fb000000'].props.update(status=b'disabled\0',compatible=b'arm,mali-valhall\0')
        nodes['/gpu-panthor@fb000000'].props.update({'compatible':b'arm,mali-valhall-csf\0','mali-supply':struct.pack('>I',9),'phandle':struct.pack('>I',7)})
        nodes['/thermal-zones/soc-thermal/cooling-maps/map3'].props['cooling-device']=struct.pack('>III',7,0xffffffff,0xffffffff)
        codec=nodes['/i2c@fec80000/es8388@10'];codec.props.update(compatible=b'everest,es8323\0',phandle=b'\0\0\0\1')
        cpu=nodes['/i2s@fe480000'];cpu.props['phandle']=b'\0\0\0\2'
        iommu=nodes['/iommu@fdab9000'];iommu.props['phandle']=b'\0\0\0\3'
        audio=nodes['/es8388-sound'];audio.props.update({'rockchip,codec':codec.props['phandle'],'rockchip,cpu':cpu.props['phandle']})
        npu=nodes['/npu@fdab0000'];npu.props.update(compatible=b'rockchip,rk3588-rknpu\0',iommus=iommu.props['phandle'])
        nodes['/gpu@fb000000'].props['power-off-delay-ms']=struct.pack('>I',200)
        for path in ['/gpio-leds','/gpio-leds/led@1','/pinctrl/gpio-func/leds-gpio','/pinctrl/gpio@fec20000']:
            parent=root
            for component in path.strip('/').split('/'):
                child=parent.child(component)
                if child is None:
                    child=fdt_read.Node(component,parent);parent.children.append(child)
                parent=child
            nodes[path]=parent
        nodes['/pinctrl/gpio@fec20000'].props['phandle']=struct.pack('>I',4)
        nodes['/gpio-leds/led@1'].props['gpios']=struct.pack('>III',4,2,0)
        nodes['/pinctrl/gpio-func/leds-gpio'].props.update({'phandle':struct.pack('>I',5),'rockchip,pins':struct.pack('>IIII',1,2,0,6)})
        nodes['/gpio-leds'].props['pinctrl-0']=struct.pack('>I',5)
        for path,compatible in [('/watchdog@feaf0000',b'snps,dw-wdt\0'),
                                ('/i2c@fec80000/hym8563@51',b'haoyu,hym8563\0'),
                                ('/reserved-memory/ramoops@110000',b'ramoops\0')]:
            parent=root
            for component in path.strip('/').split('/'):
                child=parent.child(component)
                if child is None:child=fdt_read.Node(component,parent);parent.children.append(child)
                parent=child
            parent.props.update(compatible=compatible,status=b'okay\0')
            if 'ramoops' in path:parent.props['reg']=struct.pack('>IIII',0,0x110000,0,0xe0000)
        with patch.object(vendor.fdt_read,'parse',return_value=root):
            vendor.check_tree(Path('unused'))
            audio.props['rockchip,cpu']=b'\0\0\0\4'
            with self.assertRaisesRegex(ValueError,'unmatched rockchip,cpu'):vendor.check_tree(Path('unused'))
            audio.props['rockchip,cpu']=cpu.props['phandle']
            nodes['/i2c@fec80000'].props['status']=b'disabled\0'
            with self.assertRaises(ValueError):vendor.check_tree(Path('unused'))

    def test_wrong_runtime_download_digest_is_fatal_without_publishing_cache(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'runtime.so'
            def run(args):
                Path(args[args.index('--output')+1]).write_bytes(b'wrong runtime')
            def reject(path,digest):raise ValueError('SHA mismatch')
            with self.assertRaisesRegex(ValueError,'SHA mismatch'):
                vendor.fetch('https://example.invalid/runtime',path,'0'*64,run,reject)
            self.assertFalse(path.exists())
            self.assertFalse(path.with_suffix('.so.partial').exists())

    def test_existing_input_is_never_reused(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'runtime.so';path.write_bytes(b'previous build')
            def forbidden(*args):self.fail('Existing inputs must be refused before any network or digest operation')
            with self.assertRaisesRegex(ValueError,'already exists'):
                vendor.fetch('https://example.invalid',path,'pin',forbidden,forbidden)
            self.assertEqual(path.read_bytes(),b'previous build')


class RuntimeKernelSelectionTests(unittest.TestCase):
    def test_builtin_root_drivers_need_no_modules_but_modular_ones_do(self):
        import subprocess
        script=ROOT/'overlay/usr/local/lib/chatbox/kernel.sh'
        with tempfile.TemporaryDirectory() as d:
            config=Path(d)/'config';listing=Path(d)/'listing'
            base='CONFIG_BLK_DEV_NVME=y\nCONFIG_NVME_CORE=y\nCONFIG_PHY_ROCKCHIP_NANENG_COMBO_PHY=y\nCONFIG_EXT4_FS=y\nCONFIG_PCIE_DW_ROCKCHIP=y\n'
            config.write_text(base);listing.write_text('')
            def check():
                return subprocess.run(['bash','-c','source "$1"; validate_root_drivers "$2" "$3"','bash',str(script),str(config),str(listing)],capture_output=True).returncode
            self.assertEqual(check(),0)
            config.write_text(base.replace('CONFIG_BLK_DEV_NVME=y','CONFIG_BLK_DEV_NVME=m'))
            self.assertNotEqual(check(),0)
            listing.write_text('/usr/lib/modules/abi/kernel/drivers/nvme/host/nvme.ko.zst\n')
            self.assertEqual(check(),0)
            config.write_text(base.replace('CONFIG_PCIE_DW_ROCKCHIP=y','CONFIG_PCIE_DW_ROCKCHIP=n'))
            self.assertNotEqual(check(),0)

class CleanConfigurationIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('CHATBOX_TEST_KERNEL_ARCHIVE'),
                         'Set CHATBOX_TEST_KERNEL_ARCHIVE to the pinned source tarball')
    def test_pinned_mpp_revision_avoids_git_lookup_in_archive_build(self):
        lock=json.loads((ROOT/'inputs/hardware-lock.json').read_text())
        revision='chatbox-pinned-'+lock['kernel']['commit']
        with tarfile.open(os.environ['CHATBOX_TEST_KERNEL_ARCHIVE']) as archive:
            member=archive.extractfile('linux-rockchip-'+lock['kernel']['commit']+'/drivers/video/rockchip/mpp/Makefile')
            makefile=member.read().decode()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'bin').mkdir()
            fake=root/'bin/git';fake.write_text('#!/bin/sh\ntouch "$CHATBOX_GIT_CALL_MARKER"\nexit 1\n');fake.chmod(0o755)
            file=root/'drivers/video/rockchip/mpp/Makefile';file.parent.mkdir(parents=True)
            file.write_text(makefile)
            vendor.apply_mpp_metadata(root)
            (root/'revision.c').write_text('#include <stdio.h>\nint main(void) { puts(MPP_VERSION); return 0; }\n')
            file.write_text(file.read_text()+"\n.PHONY: show-revision\nshow-revision:\n\t@$(CC) $(CFLAGS_mpp_service.o) revision.c -o revision-check\n\t@./revision-check\n")
            marker=root/'git-called'
            result=subprocess.run(['make','-s','-f',str(file),'MPP_GIT_REVISION='+revision,'show-revision'],
                cwd=root,env={**os.environ,'PATH':str(root/'bin')+':'+os.environ['PATH'],
                              'CHATBOX_GIT_CALL_MARKER':str(marker)},capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout.strip(),revision)
            self.assertFalse(marker.exists())

    @unittest.skipUnless(os.environ.get('CHATBOX_TEST_KERNEL_ARCHIVE'),
                         'Set CHATBOX_TEST_KERNEL_ARCHIVE to the pinned source tarball')
    def test_clean_prepare_reaches_compile_with_locked_abi(self):
        import os
        import image
        archive=Path(os.environ['CHATBOX_TEST_KERNEL_ARCHIVE']).resolve()
        original_stream=vendor.stream
        class ReachedCompile(Exception):pass
        def stop_at_compile(args):
            if 'Image' in args:
                raise ReachedCompile()
            original_stream(args)
        with tempfile.TemporaryDirectory() as d:
            # Exercise the real configure/sync/release path from a freshly
            # extracted source and empty object directory, stopping before the
            # expensive full compile. No mounted root or output image involved.
            with patch.object(vendor,'fetch',return_value=archive),patch.object(vendor,'stream',side_effect=stop_at_compile):
                with self.assertRaises(ReachedCompile):
                    vendor.prepare(ROOT,Path(d)/'downloads',image.run,image.verify)


if __name__=='__main__':unittest.main()
