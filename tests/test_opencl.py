from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import vendor

class ProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        headers=Path(os.environ.get('CHATBOX_TEST_OPENCL_HEADERS','/usr/include'))
        if not shutil.which('gcc') or not (headers/'CL/cl.h').is_file():
            raise unittest.SkipTest('Set CHATBOX_TEST_OPENCL_HEADERS to verified OpenCL include directory')
        cls.temp=tempfile.TemporaryDirectory();cls.program=Path(cls.temp.name)/'probe'
        subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-I'+str(headers),str(ROOT/'scripts/opencl-check.c'),str(ROOT/'tests/opencl-stub.c'),'-o',str(cls.program)],check=True,capture_output=True,text=True)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_gpu_probe_requires_execution_and_correct_numbers(self):
        for mode in ['good','no-platform','cpu-only','wrong-gpu','compile-failure','wrong-result','nan']:
            with self.subTest(mode=mode):
                p=subprocess.run([str(self.program)],env={**os.environ,'CL_TEST_MODE':mode},capture_output=True,text=True)
                self.assertEqual(p.returncode,0 if mode=='good' else 1,p.stdout+p.stderr)
                self.assertEqual('PASS:' in p.stdout,mode=='good')

class HardwareConfigTests(unittest.TestCase):
    def test_opencl_requires_panthor_and_exclusive_driver(self):
        config=(ROOT/'inputs/kernel.fragment').read_text();vendor.check_config(config)
        with self.assertRaises(ValueError):vendor.check_config(config.replace('CONFIG_DRM_PANTHOR=m','# CONFIG_DRM_PANTHOR is not set'))
        for setting in ('y','m'):
            with self.assertRaises(ValueError):vendor.check_config(config+'\nCONFIG_MALI_VALHALL='+setting+'\n')
