from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class BootloaderGuardTests(unittest.TestCase):
    def test_exact_installed_status_only(self):
        with tempfile.TemporaryDirectory() as d:
            bindir=Path(d)
            for name,body in {
                'dpkg':'#!/bin/sh\nprintf "arm64\\n"\n',
                'dpkg-query':'#!/bin/sh\nprintf "%s" "$TEST_STATUS"\nexit "${TEST_QUERY_EXIT:-0}"\n',
                'grep':'#!/bin/sh\nfor arg do\n if [ "$arg" = /etc/default/u-boot ]; then echo PASSED-GUARD; exit 1; fi\ndone\nexec /bin/grep "$@"\n',
            }.items():
                p=bindir/name;p.write_text(body);p.chmod(0o755)
            for status,query_exit,expected in [('unknown ok not-installed',0,1),('deinstall ok config-files',0,1),('',1,1),('install ok installed',0,1)]:
                with self.subTest(status=status):
                    env={**os.environ,'PATH':str(bindir)+':'+os.environ['PATH'],'TEST_STATUS':status,'TEST_QUERY_EXIT':str(query_exit)}
                    r=subprocess.run(['bash',str(ROOT/'scripts/install-kernel-target.sh')],env=env,capture_output=True,text=True)
                    self.assertEqual(r.returncode,expected,r.stdout+r.stderr)
                    self.assertEqual('Unexpected flash-kernel' in r.stdout,status=='install ok installed')
                    self.assertEqual('PASSED-GUARD' in r.stdout,status!='install ok installed')
