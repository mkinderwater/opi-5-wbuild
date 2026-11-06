import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'overlay/usr/local/lib/chatbox'))
import board_report
import test_acceptance as fixtures


class SelectionTests(unittest.TestCase):
    def test_malformed_signature_and_missing_firmware_are_detected_without_false_positives(self):
        message='cfg80211: loaded regulatory.db is malformed or signature is missing/invalid'
        for text,count in [(message,1),('regulatory.db signature rejected',1),
                           ('Direct firmware load for regulatory.db failed with error -2',1),
                           ('cfg80211: loading regulatory.db',0),
                           ('Loading compiled-in X.509 certificates for regulatory database',0)]:
            with self.subTest(text=text):
                result=board_report.boot_warning_counts(lambda argv:{'returncode':0,'stdout':text})
                self.assertEqual(result['counts']['regulatory_database'],count)

    def test_checker_rejects_debian_alternative_for_vendor_kernel(self):
        fixture=fixtures.AcceptanceTests();self.addCleanup(fixture.doCleanups)
        root,snapshot,run=fixture.fixture()
        for name in ('regulatory.db','regulatory.db.p7s'):
            fixture.put('/usr/lib/firmware/'+name+'-debian','Debian signer')
            alias=root/'usr/lib/firmware'/name;alias.unlink();alias.symlink_to(name+'-debian')
        row=fixture.rows(root,snapshot,run)['Regulatory signing variant']
        self.assertEqual(row['level'],'FAIL')
        self.assertEqual(row['tested'],'not-run')

    def fixture(self):
        tool=shutil.which('update-alternatives')
        if tool is None:self.skipTest('update-alternatives required')
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        root=Path(temporary.name);fw=root/'firmware';fw.mkdir()
        admin=root/'admin';admin.mkdir();alt=root/'alternatives';alt.mkdir();binpath=root/'bin';binpath.mkdir()
        env={**os.environ,'PATH':str(binpath)+':'+os.environ['PATH']}
        wrapper=binpath/'update-alternatives'
        import shlex
        wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(tool)+' --admindir '+shlex.quote(str(admin))+' --altdir '+shlex.quote(str(alt))+' "$@"\n')
        wrapper.chmod(0o755)
        for variant,priority in [('debian',100),('upstream',50)]:
            (fw/('regulatory.db-'+variant)).write_text(variant+' database')
            (fw/('regulatory.db.p7s-'+variant)).write_text(variant+' signature')
            subprocess.run([str(wrapper),'--install',str(fw/'regulatory.db'),'regulatory.db',str(fw/('regulatory.db-'+variant)),str(priority),
                            '--slave',str(fw/'regulatory.db.p7s'),'regulatory.db.p7s',str(fw/('regulatory.db.p7s-'+variant))],
                           check=True,capture_output=True,env=env)
        text=(ROOT/'inputs/select-upstream-regdb.sh').read_text()
        text=text.replace('/usr/lib/firmware','@FW@').replace('/lib/firmware','@FW@').replace('@FW@',str(fw))
        script=root/'select.sh';script.write_text(text)
        return fw,script,env

    def test_real_alternatives_selects_upstream_database_and_slave_signature_together(self):
        fw,script,env=self.fixture()
        self.assertEqual((fw/'regulatory.db').read_text(),'debian database')
        for repeat in range(2):
            result=subprocess.run(['sh',str(script)],env=env,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual((fw/'regulatory.db').read_text(),'upstream database')
            self.assertEqual((fw/'regulatory.db.p7s').read_text(),'upstream signature')

    def test_missing_upstream_signature_fails_before_changing_alternatives(self):
        fw,script,env=self.fixture()
        (fw/'regulatory.db.p7s-upstream').unlink()
        result=subprocess.run(['sh',str(script)],env=env,capture_output=True)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual((fw/'regulatory.db').read_text(),'debian database')

    def test_live_repair_refuses_wrong_kernel_or_unverified_package_before_writes(self):
        for kernel,version,message in [('other-kernel','2026.05.30-1~deb13u1',b'chatbox8'),
                                       ('6.1.172-chatbox8-arm64','different-version',b'pinned wireless-regdb')]:
            with self.subTest(kernel=kernel,version=version),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);marker=root/'writes'
                for name,text in [('id','0'),('uname',kernel),('dpkg-query',version)]:
                    program=root/name;program.write_text('#!/bin/sh\nprintf "%s\\n" "'+text+'"\n');program.chmod(0o755)
                for name in ('install','update-initramfs','update-alternatives'):
                    program=root/name;program.write_text('#!/bin/sh\ntouch "'+str(marker)+'"\nexit 99\n');program.chmod(0o755)
                result=subprocess.run(['bash',str(ROOT/'scripts/fix-regdb.sh')],
                    env={**os.environ,'PATH':str(root)+':'+os.environ['PATH']},capture_output=True)
                self.assertNotEqual(result.returncode,0)
                self.assertIn(message,result.stderr)
                self.assertFalse(marker.exists())


if __name__=='__main__':unittest.main()
