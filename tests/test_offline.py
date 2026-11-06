from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import offline
import image

class KernelSelectionTests(unittest.TestCase):
    def test_bootstrap_and_display_kernels_can_coexist(self):
        packages={}
        for abi,version in [('6.12.113+deb13-arm64','6.12.113-1'),('7.2.11+deb13-arm64','7.2.11-1~bpo13+1'),('6.1.172-chatbox4-arm64','6.1.172-1+chatbox4')]:
            name='linux-image-'+abi
            packages[name]={'Package':name,'Architecture':'arm64','Version':version}
        self.assertEqual(image.select_kernel_package(packages,'6.12.113-1'),'6.12.113+deb13-arm64')
        self.assertEqual(image.select_kernel_package(packages,'7.2.11-1~bpo13+1'),'7.2.11+deb13-arm64')
        self.assertEqual(image.select_kernel_package(packages,'6.1.172-1+chatbox4'),'6.1.172-chatbox4-arm64')
        packages['linux-image-7.2.11+deb13-arm64']['Architecture']='amd64'
        with self.assertRaises(ValueError):image.select_kernel_package(packages,'7.2.11-1~bpo13+1')

class InitramfsTests(unittest.TestCase):
    def test_requires_root_drivers_and_accepts_supported_compression(self):
        config='CONFIG_BLK_DEV_NVME=m\nCONFIG_NVME_CORE=m\nCONFIG_EXT4_FS=m\n'
        for suffix in ['', '.xz','.zst','.gz']:
            listing='\n'.join('/usr/lib/modules/test/'+x+'.ko'+suffix for x in ['nvme','nvme-core','ext4'])
            image.validate_initrd_modules(config,listing)
            with self.assertRaises(ValueError):
                image.validate_initrd_modules(config,listing.replace('/ext4.ko','/wrong.ko'))
        image.validate_initrd_modules('CONFIG_BLK_DEV_NVME=y\nCONFIG_EXT4_FS=y\n','')

class EmulationTests(unittest.TestCase):
    def test_requires_enabled_fix_binary_handler(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'handler'
            with self.assertRaises(ValueError):offline.check_emulation(p)
            for text in ['disabled\nflags: POCF\n','enabled\nflags: POC\n']:
                p.write_text(text)
                with self.assertRaises(ValueError):offline.check_emulation(p)
            p.write_text('enabled\ninterpreter /usr/bin/qemu-aarch64-static\nflags: POCF\n')
            offline.check_emulation(p)

class CleanupTests(unittest.TestCase):
    def test_mountinfo_escape_and_path_boundary(self):
        text='1 0 0:1 / /tmp/build\\040space/root rw - ext4 x rw\n2 0 0:2 / /tmp/build-other rw - ext4 x rw\n'
        points=offline.mountpoints(text)
        self.assertEqual(points[0],Path('/tmp/build space/root'))
        self.assertEqual(offline.mounts_under('/tmp/build space',points),[points[0]])
        self.assertEqual(offline.mounts_under('/tmp/build',points),[])

    def test_workspace_removed_after_unmounted_failure(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(offline,'mountpoints',return_value=[]):
                with self.assertRaisesRegex(RuntimeError,'fixture failure'):
                    with offline.workspace(d) as p:
                        (p/'file').write_text('data')
                        raise RuntimeError('fixture failure')
                self.assertFalse(p.exists())

    def test_remaining_mount_prevents_recursive_deletion(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(offline,'mountpoints',return_value=[]) as points:
                with self.assertRaises(offline.CleanupError):
                    with offline.workspace(d) as p:
                        (p/'keep').write_text('do not remove')
                        points.return_value=[p/'arm-root/dev']
                self.assertEqual((p/'keep').read_text(),'do not remove')

    def test_bind_mount_unwinds_when_setup_fails(self):
        calls=[]
        def run(args):
            calls.append([str(x) for x in args])
            if '--make-private' in args:raise RuntimeError('cannot privatize')
            return ''
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                with offline.mounted('/proc',Path(d)/'proc',run,bind=True,readonly=True):pass
            self.assertEqual(calls[-1],['umount',str(Path(d)/'proc')])

    def test_temporary_file_restores_original_content_and_mode(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'policy';p.write_text('original');p.chmod(0o700)
            with self.assertRaises(RuntimeError):
                with offline.temporary_file(p,'temporary',0o755):
                    self.assertEqual(p.read_text(),'temporary')
                    raise RuntimeError('transaction failed')
            self.assertEqual(p.read_text(),'original')
            self.assertEqual(p.stat().st_mode&0o777,0o700)
            self.assertFalse(p.with_name('policy.chatbox-saved').exists())


class InstallOrchestrationTests(unittest.TestCase):
    def exercise(self,architecture='arm64',fail_transaction=False):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        root=Path(tmp.name);scratch=root/'work';scratch.mkdir()
        file=root/'root.ext4';file.write_bytes(b'fixture')
        cache=root/'cache';cache.mkdir();package=cache/'kernel.deb';package.write_bytes(b'package')
        calls=[];transactions=[]
        def run(args):
            calls.append([str(x) for x in args])
            if '--print-architecture' in args:return architecture+'\n'
            return ''
        def stream(args):
            transactions.append([str(x) for x in args])
            guest=scratch/'arm-root'
            self.assertTrue((guest/'run/chatbox-build/install.sh').is_file())
            self.assertEqual((guest/'run/chatbox-build/select-regdb.sh').read_bytes(),
                             (ROOT/'inputs/select-upstream-regdb.sh').read_bytes())
            self.assertEqual((guest/'etc/default/u-boot').read_text(),'U_BOOT_UPDATE=false\n')
            self.assertEqual((guest/'usr/sbin/policy-rc.d').read_text(),'#!/bin/sh\nexit 101\n')
            self.assertIn('kernel.deb',(guest/'run/chatbox-build/PACKAGES').read_text())
            self.assertIn('RESUME=none',(guest/'etc/initramfs-tools/conf.d/chatbox-build').read_text())
            if fail_transaction:raise RuntimeError('target dpkg failed')
        lock={'kernel_abi':'7.2.11+deb13-arm64','packages':[{'Package':'linux-image-test','Version':'test','SHA256':'a'*64}]}
        with patch.object(offline,'check_emulation'),patch.object(offline.os,'sync'):
            error=None
            try:offline.install(file,scratch,ROOT,lock,[package],run,stream)
            except Exception as e:error=e
        return error,calls,transactions,scratch

    def test_success_cleans_build_files_and_unmounts_in_reverse(self):
        error,calls,transactions,scratch=self.exercise()
        self.assertIsNone(error)
        self.assertEqual(len(transactions),1)
        self.assertFalse((scratch/'arm-root/run/chatbox-build').exists())
        unmounts=[x[1] for x in calls if x[0]=='umount']
        self.assertEqual(unmounts,[str(scratch/'arm-root'/x) for x in ['run/chatbox-build/packages','sys','proc','dev','']])
        self.assertFalse((scratch/'arm-root/usr/sbin/policy-rc.d').exists())

    def test_wrong_architecture_aborts_before_package_install(self):
        error,calls,transactions,scratch=self.exercise(architecture='amd64')
        self.assertIsInstance(error,ValueError)
        self.assertEqual(transactions,[])
        self.assertEqual(len([x for x in calls if x[0]=='umount']),5)

    def test_package_failure_still_restores_and_unmounts(self):
        error,calls,transactions,scratch=self.exercise(fail_transaction=True)
        self.assertIsInstance(error,RuntimeError)
        self.assertEqual(len([x for x in calls if x[0]=='umount']),5)
        self.assertFalse((scratch/'arm-root/usr/sbin/policy-rc.d').exists())

if __name__=='__main__':unittest.main()
