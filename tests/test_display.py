from pathlib import Path
import subprocess
import re
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))

class ReadinessTests(unittest.TestCase):
    def parse(self,text):
        script='source "$1"; parse_ipv4'
        p=subprocess.run(['bash','-c',script,'bash',str(ROOT/'overlay/usr/local/lib/chatbox/network.sh')],input=text,text=True,capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr)
        return p.stdout.strip()

    def test_ipv4_first(self):
        self.assertEqual(self.parse(' Address: 192.168.24.134\n Gateway: 192.168.24.1\n'),'192.168.24.134')

    def test_ipv6_first_then_ipv4(self):
        self.assertEqual(self.parse(' Address: fd12::1\n          fe80::a\n          192.168.24.134/24\n Gateway: 192.168.24.1\n'),'192.168.24.134')

    def test_link_local_and_unrelated_fields_rejected(self):
        for text in [' Address: 169.254.1.2\n Gateway: 192.168.24.1\n',
                     ' Address: 127.0.0.1\n DNS: 192.168.24.1\n',
                     ' Address: 999.1.2.3\n',' Address: fd12::1\n Gateway: 192.168.24.1\n']:
            with self.subTest(text=text):self.assertEqual(self.parse(text),'')

class BootMenuTests(unittest.TestCase):
    def render(self,choice,abi='6.1.172-chatbox4-arm64',root='12345678-02'):
        p=subprocess.run(['bash','-c','source "$1"; render_boot_menu "$2" "$3" "$4"','bash',
             str(ROOT/'overlay/usr/local/lib/chatbox/boot-menu.sh'),choice,abi,root],capture_output=True,text=True)
        return p

    def test_display_and_recovery_use_matched_paths(self):
        for choice in ['display','recovery']:
            with self.subTest(choice=choice):
                p=self.render(choice);self.assertEqual(p.returncode,0,p.stderr)
                self.assertTrue(p.stdout.startswith('DEFAULT '+choice+'\n'))
                blocks={part.splitlines()[0]:part for part in re.split(r'^LABEL ',p.stdout,flags=re.M)[1:] if part.splitlines()[0] in ['display','recovery']}
                self.assertIn('console=ttyFIQ0,1500000n8',blocks['display'])
                self.assertIn('console=ttyS2,1500000n8',blocks['recovery'])
                self.assertIn('vmlinuz-6.1.172-chatbox4-arm64',blocks['display'])
                self.assertIn('initrd.img-6.1.172-chatbox4-arm64',blocks['display'])
                self.assertIn('/boot/chatbox-orangepi-5.dtb',blocks['display'])
                self.assertIn('vmlinuz-6.12.113+deb13-arm64',blocks['recovery'])
                self.assertIn('/boot/chatbox-recovery.dtb',blocks['recovery'])
                self.assertEqual(p.stdout.count('root=PARTUUID=12345678-02'),2)

    def test_bad_identifiers_produce_no_menu(self):
        for args in [('bogus',),('display','bad;command'),('display','6.1.172-chatbox4-arm64','bad')]:
            p=self.render(*args);self.assertNotEqual(p.returncode,0);self.assertEqual(p.stdout,'')

class ConfigScopeTests(unittest.TestCase):
    def test_template_has_only_current_values(self):
        lines=(ROOT/'CONFIG.TXT').read_text().splitlines()
        self.assertEqual(lines,['ROOT_PASSWORD=','TIMEZONE=America/Edmonton','HOSTNAME='])

if __name__=='__main__':unittest.main()
