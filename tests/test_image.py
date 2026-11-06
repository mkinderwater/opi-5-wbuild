import gzip
import importlib.util
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import image

class LayoutTests(unittest.TestCase):
    def test_partition_geometry_and_partuuid(self):
        m=image.make_mbr(0x12345678, 1000000)
        self.assertEqual(m[510:], b'\x55\xaa')
        self.assertEqual(struct.unpack_from('<I',m,440)[0],0x12345678)
        entries=[struct.unpack_from('<B3sB3sII',m,446+16*i) for i in range(4)]
        self.assertEqual(entries[0][2],12)
        self.assertEqual(entries[0][4:],(2048,131072))
        self.assertEqual(entries[1][2],131)
        self.assertEqual(entries[1][4:],(133120,1000000))
        self.assertEqual(entries[0][4]+entries[0][5],entries[1][4])
        self.assertEqual(entries[2][5],0)
        self.assertEqual(entries[3][5],0)
        with self.assertRaises(ValueError):image.make_mbr(1,2**32)

    def test_hash_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'input';p.write_bytes(b'test')
            with self.assertRaises(ValueError):image.verify(p,'0'*64)
            self.assertEqual(image.verify(p,image.sha256(p)),image.sha256(p))


class ConfigTests(unittest.TestCase):
    def parse(self,text):
        d=tempfile.TemporaryDirectory();self.addCleanup(d.cleanup)
        p=Path(d.name);(p/'in').write_bytes(text.encode());(p/'out').mkdir()
        r=subprocess.run(['perl',str(ROOT/'overlay/usr/local/sbin/chatbox-config'),str(p/'in'),str(p/'out')],capture_output=True,text=True)
        return r,p/'out'

    def test_windows_line_endings(self):
        r,p=self.parse('ROOT_PASSWORD=abcdefghijkl!\r\nTIMEZONE=America/Edmonton\r\nHOSTNAME=pip\r\n')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual((p/'chpasswd').read_text(),'root:abcdefghijkl!\n')
        self.assertFalse((p/'settings').exists())
        self.assertEqual((p/'chpasswd').stat().st_mode & 0o777,0o600)

    def test_no_password_length_policy_and_colons_are_literal(self):
        for password in ['x','1234567890','a'*200,'literal:password','café']:
            with self.subTest(length=len(password)):
                r,p=self.parse('ROOT_PASSWORD='+password+'\n')
                self.assertEqual(r.returncode,0,r.stderr)
                self.assertEqual((p/'chpasswd').read_text(),'root:'+password+'\n')

    def test_config_is_literal_not_shell(self):
        r,p=self.parse('ROOT_PASSWORD=$(touch /tmp/never-execute)\n')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual((p/'chpasswd').read_text(),'root:$(touch /tmp/never-execute)\n')

    def test_invalid_inputs_never_write_credentials(self):
        cases=['ROOT_PASSWORD=\n',
               'ROOT_PASSWORD=abc\x00def\n',
               'ROOT_PASSWORD=abcdefghijkl\nROOT_PASSWORD=mnopqrstuvwx\n',
               'ROOT_PASSWORD=abcdefghijkl\nTIMEZONE=../../etc/passwd\n',
               'ROOT_PASSWORD=abcdefghijkl\nBUTTON_ENABLED=maybe\n',
               'ROOT_PASSWORD=abcdefghijkl\nHOSTNAME=$(id)\n',
               'ROOT_PASSWORD=abcdefghijkl\nBOGUS=yes\n']
        for case in cases:
            with self.subTest(case=case):
                r,p=self.parse(case)
                self.assertNotEqual(r.returncode,0)
                self.assertFalse((p/'chpasswd').exists())


class ExpansionTests(unittest.TestCase):
    def run_resize(self, mbr, total, start=133120, identity='12345678'):
        d=tempfile.TemporaryDirectory();self.addCleanup(d.cleanup)
        p=Path(d.name)/'disk';p.write_bytes(mbr)
        r=subprocess.run(['perl',str(ROOT/'overlay/usr/local/lib/chatbox/grow-mbr.pl'),str(p),str(total),str(start),identity],capture_output=True,text=True)
        return r,p.read_bytes()

    def test_growth_preserves_partition_start_identity_and_config(self):
        original=image.make_mbr(0x12345678,1000000)
        r,changed=self.run_resize(original,2000000)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(struct.unpack_from('<I',changed,474)[0],2000000-133120)
        self.assertEqual(original[:474],changed[:474])
        self.assertEqual(original[478:],changed[478:])
        r,again=self.run_resize(changed,2000000)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(changed,again)

    def test_wrong_disk_or_extra_partition_never_changes_bytes(self):
        original=image.make_mbr(0x12345678,1000000)
        extra=bytearray(original);extra[482]=0x83
        for m,total,start,identity in [(original,2000000,133120,'deadbeef'),
                                       (original,2000000,133121,'12345678'),
                                       (original,100000,133120,'12345678'),
                                       (extra,2000000,133120,'12345678'),
                                       (original,2**33,133120,'12345678')]:
            with self.subTest(total=total,start=start,identity=identity):
                r,changed=self.run_resize(m,total,start,identity)
                self.assertNotEqual(r.returncode,0)
                self.assertEqual(changed,m)

@unittest.skipUnless(shutil.which('mke2fs') and shutil.which('debugfs'),'e2fsprogs required')
class FilesystemTests(unittest.TestCase):
    def test_injected_files_and_permissions_and_account_lock(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);stage=p/'source';(stage/'etc/ssh').mkdir(parents=True)
            (stage/'var/lib/dbus').mkdir(parents=True)
            (stage/'root/.ssh').mkdir(parents=True)
            (stage/'home').mkdir()
            for name,text in {
                'passwd':'root:x:0:0:root:/root:/bin/bash\nold:x:1000:1000:Old:/home/old:/bin/bash\n',
                'shadow':'root:inherited:1:0:99999:7:::\nold:inherited:1:0:99999:7:::\n',
                'group':'root:x:0:\nold:x:1000:\nsudo:x:27:old\n',
                'gshadow':'root:*::\nold:!::\nsudo:*::old\n'}.items():
                (stage/'etc'/name).write_text(text)
            (stage/'etc/ssh/ssh_host_ed25519_key').write_text('inherited secret')
            (stage/'root/.ssh/authorized_keys').write_text('inherited authorization')
            f=p/'root.ext4'
            image.run(['mke2fs','-q','-t','ext4','-d',stage,f,'32768'])
            fs=image.Ext4(f,p)
            image.sanitize_accounts(fs,p)
            self.assertTrue(fs.text('/etc/shadow').startswith('root:!:'))
            self.assertNotIn('old:',fs.text('/etc/passwd'))
            self.assertNotIn('old',fs.text('/etc/group'))
            self.assertFalse(fs.exists('/etc/ssh/ssh_host_ed25519_key'))
            self.assertFalse(fs.exists('/root/.ssh/authorized_keys'))
            self.assertEqual(fs.text('/etc/machine-id'),'')
            self.assertIn('/dev/null',fs.command('stat /etc/systemd/system/ssh.socket'))
            fs.write('/usr/local/sbin/example','#!/bin/sh\nexit 0\n',0o755)
            self.assertIn('Mode:  0755',fs.command('stat /usr/local/sbin/example'))
            fs.write('/usr/local/sbin/example','replacement',0o700)
            self.assertEqual(fs.text('/usr/local/sbin/example'),'replacement')
            self.assertIn('Mode:  0700',fs.command('stat /usr/local/sbin/example'))
            second=image.Ext4(f,p)
            with self.assertRaises(ValueError):second.read('/missing-file')
            self.assertTrue(second.text('/etc/shadow').startswith('root:!:'))
            image.run(['e2fsck','-fn',f])

if __name__=='__main__':unittest.main()
