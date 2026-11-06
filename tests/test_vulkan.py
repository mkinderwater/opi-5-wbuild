"""Compile the real diagnostic and verify a missing ICD cannot report success."""
from pathlib import Path
import os
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
class VulkanDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        headers=Path(os.environ.get('CHATBOX_TEST_VULKAN_HEADERS','/usr/include'))
        compiler=os.environ.get('CHATBOX_TEST_GLSLANG','glslangValidator')
        if not shutil.which(compiler) or not (headers/'vulkan/vulkan.h').exists():
            raise unittest.SkipTest('Set Vulkan header and glslang paths to run native diagnostic checks')
        cls.temp=tempfile.TemporaryDirectory();directory=Path(cls.temp.name)
        spv=directory/'shader.spv'
        subprocess.run([compiler,'-V','--target-env','vulkan1.0',ROOT/'scripts/gpu-shader.comp','-o',spv],check=True,capture_output=True)
        data=spv.read_bytes();words=struct.unpack('<'+'I'*(len(data)//4),data)
        (directory/'gpu-shader.h').write_text('static const uint32_t shader_words[]={'+','.join(hex(w) for w in words)+'};\n')
        cls.program=directory/'probe'
        subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror','-I'+str(headers),'-I'+str(directory),ROOT/'scripts/vulkan-check.c','-l:libvulkan.so.1','-o',cls.program],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_missing_driver_is_not_success(self):
        r=subprocess.run([self.program],env={**os.environ,'VK_DRIVER_FILES':'/nonexistent/chatbox-icd.json'},capture_output=True,text=True,timeout=15)
        self.assertNotEqual(r.returncode,0)
        self.assertNotIn('PASS:',r.stdout)
    def test_software_device_is_not_success(self):
        candidates=list(Path('/usr/share/vulkan/icd.d').glob('*lvp*.json'))
        if not candidates:self.skipTest('No host software Vulkan ICD to test rejection')
        r=subprocess.run([self.program],env={**os.environ,'VK_DRIVER_FILES':str(candidates[0])},capture_output=True,text=True,timeout=15)
        self.assertNotEqual(r.returncode,0)
        self.assertNotIn('PASS:',r.stdout)
