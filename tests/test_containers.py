import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'overlay/usr/local/lib/chatbox')]
import vendor
import containers

class ContainerChecks(unittest.TestCase):
    def test_each_required_feature_is_a_build_gate(self):
        fragment=(ROOT/'inputs/kernel.fragment').read_text()
        vendor.check_config(fragment)
        for flag in containers.PROFILE['required']:
            for value in ['m','n']:
                with self.subTest(flag=flag,value=value):
                    broken=fragment.replace('CONFIG_'+flag+'=y','CONFIG_'+flag+'='+value)
                    with self.assertRaisesRegex(ValueError,'CONFIG_'+flag+'=y'):vendor.check_config(broken)
    def fixture(self,root,fragment):
        (root/'proc').mkdir();(root/'sys/fs/cgroup').mkdir(parents=True)
        with gzip.open(root/'proc/config.gz','wt') as f:f.write(fragment)
        (root/'proc/filesystems').write_text('nodev\toverlay\nnodev\ttmpfs\n')
        (root/'sys/fs/cgroup/cgroup.controllers').write_text('cpu cpuset io memory pids')
    def test_live_config_available_and_no_daemon_autostart(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.fixture(root,(ROOT/'inputs/kernel.fragment').read_text())
            calls=[]
            def run(args):calls.append(args);return {'returncode':3}
            rows=containers.checks(root,'fake',run)
            self.assertFalse(any(x['level']=='FAIL' for x in rows))
            self.assertEqual(len(calls),1)
            self.assertIn('is-active',calls[0])
            self.assertEqual(rows[-1]['tested'],'not-run')
    def test_missing_memory_firewall_and_storage_are_failures(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);text=(ROOT/'inputs/kernel.fragment').read_text()
            for key in ['MEMCG','NF_TABLES','OVERLAY_FS']:text=text.replace('CONFIG_'+key+'=y','# CONFIG_'+key+' is not set')
            self.fixture(root,text)
            rows=containers.checks(root,'fake',lambda _: {'returncode':3})
            self.assertTrue(all(any('CONFIG_'+key in x['detail'] and x['level']=='FAIL' for x in rows) for key in ['MEMCG','NF_TABLES','OVERLAY_FS']))
    def test_installed_config_is_not_claimed_live(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'boot').mkdir();(root/'boot/config-fake').write_text((ROOT/'inputs/kernel.fragment').read_text())
            rows=containers.checks(root,'fake',lambda _: {'returncode':3})
            self.assertTrue(all(x['level']=='WARN' for x in rows))
    def test_191_build_profile_rejects_the_actual_190_omission(self):
        fragment=(ROOT/'inputs/kernel.fragment').read_text()
        with self.assertRaisesRegex(ValueError,'CONFIG_OVERLAY_FS'):
            vendor.check_config(fragment.replace('CONFIG_OVERLAY_FS=y',''))
if __name__=='__main__':unittest.main()
