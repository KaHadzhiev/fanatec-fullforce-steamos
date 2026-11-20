# SPDX-License-Identifier: GPL-2.0-or-later
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from kernel_update import install, restore


class KernelUpdateTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.state = root / 'backup'
        self.state.mkdir()
        self.target = root / 'hid-fanatec.ko'
        self.target.write_bytes(b'working original')
        self.candidate = root / 'candidate.ko'
        self.candidate.write_bytes(b'async update')

    def test_install_and_restore(self):
        refresh = Mock()
        install(self.state, self.target, self.candidate, refresh)
        self.assertEqual(self.target.read_bytes(), b'async update')
        with self.assertRaisesRegex(RuntimeError, 'pending install'):
            install(self.state, self.target, self.candidate, refresh)
        restore(self.state, self.target, refresh)
        self.assertEqual(self.target.read_bytes(), b'working original')
        self.assertEqual(refresh.call_count, 2)

    def test_failed_depmod_restores_old_module(self):
        refresh = Mock(side_effect=[RuntimeError('depmod failed'), None])
        with self.assertRaisesRegex(RuntimeError, 'depmod failed'):
            install(self.state, self.target, self.candidate, refresh)
        self.assertEqual(self.target.read_bytes(), b'working original')
        self.assertEqual(refresh.call_count, 2)

    def test_refuses_modified_target(self):
        refresh = Mock()
        install(self.state, self.target, self.candidate, refresh)
        self.target.write_bytes(b'changed independently')
        with self.assertRaisesRegex(RuntimeError, 'changed independently'):
            restore(self.state, self.target, refresh)
        self.assertEqual(self.target.read_bytes(), b'changed independently')

    def test_refuses_corrupted_backup(self):
        refresh = Mock()
        install(self.state, self.target, self.candidate, refresh)
        (self.state / 'original-hid-fanatec.ko').write_bytes(b'corrupt')
        with self.assertRaisesRegex(RuntimeError, 'failed verification'):
            restore(self.state, self.target, refresh)
        self.assertEqual(self.target.read_bytes(), b'async update')
