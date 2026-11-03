# -*- coding: utf-8 -*-
"""The second window takes the running app's colours, is shown at its size, and stays on the monitor."""
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

import doc_window


class Module(unittest.TestCase):
    def test_the_running_apps_module_not_a_second_copy(self):
        running = types.ModuleType('running_app_for_test')
        running.LineNumberGutter = object
        running.LINE_NUM_BG = '#1c1a17'
        App = type('App', (), {'__module__': 'running_app_for_test'})
        sys.modules['running_app_for_test'] = running
        try:
            self.assertIs(doc_window._app_module(App()), running)
        finally:
            del sys.modules['running_app_for_test']


class Place(unittest.TestCase):
    def window(self, last=None, area=(0, 0, 1920, 1040)):
        module = types.ModuleType('place_app_for_test')
        module.LineNumberGutter = object
        module.monitor_work_area = lambda x, y: area
        module.window_frame_size = lambda root: (16, 39)
        module.fit_in_area = lambda x, y, w, h, a: (min(x, a[2] - w), min(y, a[3] - h))
        App = type('App', (), {'__module__': 'place_app_for_test'})
        sys.modules['place_app_for_test'] = module
        self.addCleanup(sys.modules.pop, 'place_app_for_test', None)
        app = App()
        app.root = MagicMock()
        app.root.winfo_rootx.return_value = 100
        app.root.winfo_rooty.return_value = 50
        app.root.winfo_width.return_value = 1200
        app.root.winfo_height.return_value = 800
        if last:
            app._doc_window_last = last
        w = doc_window.DocumentWindow.__new__(doc_window.DocumentWindow)
        w.app = app
        w.window = MagicMock()
        return w

    def test_first_by_the_main_window(self):
        w = self.window()
        w._place_window()
        w.window.geometry.assert_called_once_with('600x720+140+90')

    def test_again_at_the_last_place(self):
        w = self.window(last=(700, 500, 300, 200))
        w._place_window()
        w.window.geometry.assert_called_once_with('700x500+300+200')

    def test_last_place_kept_inside_the_area(self):
        w = self.window(last=(700, 500, 1800, 900))
        w._place_window()
        w.window.geometry.assert_called_once_with('700x500+1204+501')

    def test_remembered_only_when_shown(self):
        w = self.window()
        w.window.winfo_ismapped.return_value = 0
        w._remember_place()
        self.assertFalse(hasattr(w.app, '_doc_window_last'))
        w.window.winfo_ismapped.return_value = 1
        w.window.winfo_width.return_value = 640
        w.window.winfo_height.return_value = 480
        w.window.winfo_x.return_value = 10
        w.window.winfo_y.return_value = 20
        w._remember_place()
        self.assertEqual(w.app._doc_window_last, (640, 480, 10, 20))


if __name__ == '__main__':
    unittest.main()
