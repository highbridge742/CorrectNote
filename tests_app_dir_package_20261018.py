# -*- coding: utf-8 -*-
"""Where the data files go (2026-10-18, MSIX for the Microsoft Store): inside an
MSIX package the install folder is read-only, so %LOCALAPPDATA%\\CorrectNote is
used; the one-file exe and the scripts keep their own folder."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import app


class AppDirTests(unittest.TestCase):
    def test_packaged_uses_the_real_package_folder_and_creates_it(self):
        # 2026-10-19: the path must be the real one, because it is handed to programs outside the
        # package (the browser for the manual, Explorer); %LOCALAPPDATA%\CorrectNote is only
        # redirected for the packaged process itself
        with tempfile.TemporaryDirectory() as d, \
                patch.dict(os.environ, {'LOCALAPPDATA': d}), \
                patch.object(app, 'running_as_package', return_value=True), \
                patch.object(app, 'package_family_name', return_value='5AA043A5.CorrectNote_8a3wpcepe66rc'):
            got = app.app_dir()
            self.assertEqual(got, os.path.join(d, 'Packages', '5AA043A5.CorrectNote_8a3wpcepe66rc',
                                               'LocalCache', 'Local', 'CorrectNote'))
            self.assertTrue(os.path.isdir(got))
            self.assertEqual(app.app_dir(), got)           # again: no error when it exists

    def test_packaged_without_a_family_name_falls_back_to_local_app_data(self):
        with tempfile.TemporaryDirectory() as d, \
                patch.dict(os.environ, {'LOCALAPPDATA': d}), \
                patch.object(app, 'running_as_package', return_value=True), \
                patch.object(app, 'package_family_name', return_value=None):
            got = app.app_dir()
            self.assertEqual(got, os.path.join(d, 'CorrectNote'))
            self.assertTrue(os.path.isdir(got))

    def test_package_family_name(self):
        if sys.platform != 'win32':
            self.assertIsNone(app.package_family_name())
            return
        import ctypes
        kernel32 = ctypes.windll.kernel32
        self.assertIsNone(app.package_family_name())      # this test process is not packaged

        def fake(length, buf):
            name = 'Pkg.Name_abc123'
            if buf is None:
                length._obj.value = len(name) + 1
                return 122
            buf.value = name
            return 0
        with patch.object(kernel32, 'GetCurrentPackageFamilyName', side_effect=fake):
            self.assertEqual(app.package_family_name(), 'Pkg.Name_abc123')
        with patch.object(kernel32, 'GetCurrentPackageFamilyName', side_effect=AttributeError):
            self.assertIsNone(app.package_family_name())

    def test_otherwise_the_folder_stays_as_before(self):
        with patch.object(app, 'running_as_package', return_value=False):
            self.assertEqual(app.app_dir(), os.path.dirname(os.path.abspath(app.__file__)))
            exe = os.path.join(tempfile.gettempdir(), 'portable', 'CorrectNote.exe')
            with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', exe):
                self.assertEqual(app.app_dir(), os.path.dirname(exe))

    def test_package_detection(self):
        if sys.platform != 'win32':
            self.assertFalse(app.running_as_package())
            return
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # This test process is not packaged (APPMODEL_ERROR_NO_PACKAGE)
        self.assertFalse(app.running_as_package())
        with patch.object(kernel32, 'GetCurrentPackageFullName', return_value=122):   # buffer too small: packaged
            self.assertTrue(app.running_as_package())
        with patch.object(kernel32, 'GetCurrentPackageFullName', side_effect=AttributeError):
            self.assertFalse(app.running_as_package())
        with patch.object(sys, 'platform', 'linux'):
            self.assertFalse(app.running_as_package())


if __name__ == '__main__':
    unittest.main()
