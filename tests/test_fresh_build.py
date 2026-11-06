from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import image

class FreshInputTests(unittest.TestCase):
    def test_each_invocation_downloads_to_a_new_disposable_workspace(self):
        with tempfile.TemporaryDirectory() as d:
            output=Path(d)/'out/result.img.gz';seen=[]
            def fetch(url,path,digest,run,verify):
                self.assertFalse(path.exists());path.write_bytes(b'new input');seen.append(path)
                self.assertEqual(url,image.ROOT_URL);self.assertEqual(digest,image.ROOT_SHA)
            def build(root,digest,destination):
                self.assertEqual(root.read_bytes(),b'new input')
                self.assertEqual(destination,output)
            with patch.object(image,'check_dependencies'),patch.object(image.vendor,'fetch',side_effect=fetch),patch.object(image,'build',side_effect=build),patch.object(image.shutil,'disk_usage',return_value=shutil._ntuple_diskusage(100*1024**3,0,100*1024**3)),patch.object(sys,'argv',['image.py','--output',str(output)]):
                self.assertEqual(image.main(),0);self.assertFalse(seen[0].exists())
                self.assertEqual(image.main(),0);self.assertFalse(seen[1].exists())
            self.assertNotEqual(seen[0],seen[1])

class WindowsEntryTests(unittest.TestCase):
    def test_repeated_runs_create_distinct_workspaces_and_copy_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);source=base/'Windows source with spaces';source.mkdir()
            home=base/'home';home.mkdir();binpath=base/'bin';binpath.mkdir()
            (source/'windows-entry.sh').write_bytes((ROOT/'windows-entry.sh').read_bytes())
            (source/'setup-wsl.sh').write_text('#!/bin/bash\nset -eu\nprintf setup\\n\n')
            (source/'build.sh').write_text('#!/bin/bash\nset -eu\nmkdir out\nprintf fixture >out/chatbox-2.0.1-gpu-experimental-orangepi5-nvme.img.gz\nprintf manifest >out/chatbox-2.0.1-gpu-experimental-orangepi5-nvme.img.gz.json\n')
            sudo=binpath/'sudo';sudo.write_text('#!/bin/sh\nexec "$@"\n');sudo.chmod(0o755)
            env={**os.environ,'HOME':str(home),'PATH':str(binpath)+':'+os.environ['PATH']}
            for i in range(2):
                p=subprocess.run(['bash',str(source/'windows-entry.sh')],cwd=source,env=env,capture_output=True,text=True)
                self.assertEqual(p.returncode,0,p.stdout+p.stderr)
                self.assertEqual((source/'out/chatbox-2.0.1-gpu-experimental-orangepi5-nvme.img.gz').read_bytes(),b'fixture')
                self.assertTrue((source/'out/build.log').is_file())
                (source/'out').rename(base/('output-'+str(i)))
            work=list((home/'chatbox-builds').iterdir())
            self.assertEqual(len(work),2);self.assertNotEqual(work[0],work[1])

class FreshImportTests(unittest.TestCase):
    def test_entrypoint_ignores_preexisting_python_bytecode(self):
        import importlib._bootstrap_external
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'scripts').mkdir();(root/'bin').mkdir()
            (root/'build.sh').write_bytes((ROOT/'build.sh').read_bytes())
            source=root/'scripts/helper.py';source.write_text('value = "fresh source"\n')
            compiled=compile('value = "stale compiled code"\n',str(source),'exec')
            dest=Path(importlib.util.cache_from_source(str(source)));dest.parent.mkdir()
            dest.write_bytes(importlib._bootstrap_external._code_to_timestamp_pyc(compiled,int(source.stat().st_mtime),source.stat().st_size))
            (root/'scripts/image.py').write_text('import helper,os\nassert helper.value == "fresh source", helper.value\nassert os.environ["CCACHE_DISABLE"] == "1"\nprint("fresh imports")\n')
            fake_id=root/'bin/id';fake_id.write_text('#!/bin/sh\necho 0\n');fake_id.chmod(0o755)
            result=subprocess.run(['bash',str(root/'build.sh')],env={**os.environ,'PATH':str(root/'bin')+':'+os.environ['PATH'],'TMPDIR':str(root)},capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('fresh imports',result.stdout)
            self.assertFalse(list(root.glob('chatbox-imports-*')))
