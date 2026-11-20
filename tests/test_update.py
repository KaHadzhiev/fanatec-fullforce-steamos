# SPDX-License-Identifier: GPL-2.0-or-later
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location('updater',Path(__file__).resolve().parents[1]/'fullforce_update.py')
u=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(u)

class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.prefix=self.root/'Steam Library/steamapps/compatdata/3058630/pfx'
        (self.prefix/'drive_c/windows/system32/drivers').mkdir(parents=True)
        (self.prefix/'system.reg').write_text('original registry')
        (self.prefix/'user.reg').write_text('original user')
        self.state_dir=self.prefix.parent/'fanatec-fullforce'; self.state_dir.mkdir()
    def tearDown(self): self.tmp.cleanup()

class DiscoveryTests(Fixture):
    def test_secondary_library_with_spaces(self):
        home=self.root/'home'; steam=home/'.local/share/Steam/steamapps'; steam.mkdir(parents=True)
        (steam/'libraryfolders.vdf').write_text('"libraryfolders" { "1" { "path" "'+str(self.root/'Steam Library')+'" "apps" { "3058630" "999" } } }')
        self.assertEqual(u.discover(home),[self.prefix])
    def test_aliases_are_deduplicated(self):
        home=self.root/'home'; (home/'.local/share').mkdir(parents=True); (home/'.steam').mkdir()
        (home/'.local/share/Steam').symlink_to(self.root/'Steam Library',target_is_directory=True)
        (home/'.steam/steam').symlink_to(self.root/'Steam Library',target_is_directory=True)
        self.assertEqual(u.discover(home),[self.prefix])
    def test_wrong_game_rejected(self):
        wrong=self.prefix.parent.parent/'805550/pfx'; wrong.mkdir(parents=True)
        with self.assertRaises(u.Stop): u.validate_prefix(wrong)
    def test_driver_path_escape_rejected(self):
        drivers=self.prefix/'drive_c/windows/system32/drivers'; drivers.rmdir()
        drivers.symlink_to(self.root)
        with self.assertRaises(u.Stop): u.validate_prefix(self.prefix)
    def test_malformed_vdf(self):
        with self.assertRaises(u.Stop): u.parse_vdf('"libraryfolders" { "1" "abc"')
    def test_quoted_path(self):
        self.assertEqual(u.parse_vdf(r'"path" "a\"b\\c"')['path'],'a"b\\c')

class BackupTests(Fixture):
    def test_restore_preserves_new_prefix_and_does_not_follow_links(self):
        external=self.root/'outside'; external.write_text('external data')
        (self.prefix/'external').symlink_to(external)
        backup,fp=u.backup_prefix(self.prefix,self.state_dir)
        self.assertTrue((backup/'external').is_symlink())
        (self.prefix/'system.reg').write_text('changed')
        (self.prefix/'new-save').write_text('progress')
        state={'backup':backup.name,'fingerprint':fp,'status':'installed'}
        u.restore_prefix(self.prefix,self.state_dir,state)
        self.assertEqual((self.prefix/'system.reg').read_text(),'original registry')
        self.assertEqual((Path(state['retained'])/'new-save').read_text(),'progress')
        self.assertEqual(external.read_text(),'external data')
    def test_tampered_backup_refused(self):
        backup,fp=u.backup_prefix(self.prefix,self.state_dir)
        (backup/'system.reg').write_text('tampered')
        with self.assertRaises(u.Stop): u.restore_prefix(self.prefix,self.state_dir,{'backup':backup.name,'fingerprint':fp})
        self.assertEqual((self.prefix/'system.reg').read_text(),'original registry')
    def test_low_space_refused(self):
        with patch.object(u.shutil,'disk_usage',return_value=type('Space',(),{'free':0})()):
            with self.assertRaises(u.Stop): u.backup_prefix(self.prefix,self.state_dir)
    def test_transaction_success_and_undo(self):
        class PT:
            def command(inner,command):
                self.assertIn('wine reg query' if command.startswith('wine') else '--apply',command)
            def stop(inner): pass
        u.transaction(self.prefix,self.state_dir,PT())
        state=json.loads((self.state_dir/'state.json').read_text())
        self.assertEqual(state['status'],'installed')
        self.assertTrue((self.prefix/'drive_c/windows/system32/drivers/fwfilterusb.sys').is_file())
        u.restore_prefix(self.prefix,self.state_dir,state)
        self.assertFalse((self.prefix/'drive_c/windows/system32/drivers/fwfilterusb.sys').exists())
    def test_failed_registry_import_rolls_back(self):
        class PT:
            def command(inner,command):
                (self.prefix/'system.reg').write_text('partial mutation')
                raise u.Stop('simulated registry import failure')
            def stop(inner): pass
        with patch.object(u,'require_idle'),self.assertRaises(u.Stop):
            u.transaction(self.prefix,self.state_dir,PT())
        self.assertEqual((self.prefix/'system.reg').read_text(),'original registry')
        self.assertEqual(json.loads((self.state_dir/'state.json').read_text())['status'],'restored')
    def test_failed_shutdown_keeps_backup_for_manual_undo(self):
        class PT:
            def command(inner,command): raise u.Stop('import failure')
            def stop(inner): raise u.Stop('cannot stop Wine')
        with self.assertRaises(u.Stop): u.transaction(self.prefix,self.state_dir,PT())
        state=json.loads((self.state_dir/'state.json').read_text())
        self.assertEqual(state['status'],'prepared')
        self.assertTrue((self.state_dir/state['backup']/'system.reg').is_file())

class HardwareTests(Fixture):
    def test_correct_family(self):
        d=self.root/'sys/module/hid_fanatec/drivers/hid:fanatec/0003:0EB7:0020.1234'; d.mkdir(parents=True)
        (d/'wheel_type').write_text('17\n'); (d/'rim_id').write_text('16\n')
        u.check_hardware(self.root/'sys')
    def test_missing_driver(self):
        with self.assertRaises(u.Stop): u.check_hardware(self.root/'sys')
    def test_wrong_family(self):
        d=self.root/'sys/module/hid_fanatec/drivers/hid:fanatec/0003:0EB7:0020.1234'; d.mkdir(parents=True)
        (d/'wheel_type').write_text('99'); (d/'rim_id').write_text('16')
        with self.assertRaises(u.Stop): u.check_hardware(self.root/'sys')

if __name__=='__main__': unittest.main()
