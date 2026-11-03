# -*- coding: utf-8 -*-
"""Small windows open by the main window, inside its monitor; the Language menu follows the theme (2026-11-03)."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

import app as app_module
from app import fit_in_area

App = app_module.CorrectNoteApp


class Fit(unittest.TestCase):
    AREA = (1920, 0, 3840, 1040)

    def test_inside_stays(self):
        self.assertEqual(fit_in_area(2000, 100, 400, 300, self.AREA), (2000, 100))

    def test_past_the_right_and_bottom(self):
        self.assertEqual(fit_in_area(3700, 900, 400, 300, self.AREA), (3440, 740))

    def test_past_the_left_and_top_of_a_second_monitor(self):
        self.assertEqual(fit_in_area(100, -50, 400, 300, self.AREA), (1920, 0))

    def test_a_monitor_on_the_left(self):
        self.assertEqual(fit_in_area(-300, 100, 400, 300, (-1920, 0, 0, 1040)), (-400, 100))

    def test_larger_than_the_area_keeps_its_head(self):
        self.assertEqual(fit_in_area(2000, 100, 3000, 2000, self.AREA), (1920, 0))

    def test_area_unknown(self):
        self.assertEqual(fit_in_area(5, 6, 400, 300, None), (5, 6))


class PlaceDialog(unittest.TestCase):
    def place(self, area, rootx=2000, rooty=50, width=1000, height=800, w=400, h=300, frame=(16, 40)):
        root = NS(winfo_rootx=lambda: rootx, winfo_rooty=lambda: rooty, winfo_width=lambda: width, winfo_height=lambda: height)
        dlg = mock.Mock()
        with mock.patch.object(app_module, 'monitor_work_area', return_value=area) as asked, \
                mock.patch.object(app_module, 'window_frame_size', return_value=frame):
            App._place_dialog(NS(root=root), dlg, w, h)
        return dlg.geometry.call_args[0][0], asked.call_args[0]

    def test_over_the_main_window(self):
        got, asked = self.place((1920, 0, 3840, 1040))
        self.assertEqual(got, '400x300+2300+216')
        self.assertEqual(asked, (2500, 450))        # the monitor of the main window, not the primary

    def test_a_small_main_window_near_the_bottom(self):
        got, _ = self.place((1920, 0, 3840, 1040), rooty=950, height=80, w=400, h=600)
        self.assertEqual(got, '400x600+2300+400')

    def test_maximized(self):
        got, _ = self.place((1920, 0, 3840, 1040), rootx=1920, rooty=0, width=1920, height=1040)
        self.assertEqual(got, '400x300+2680+246')


    def test_the_frame_is_counted_at_any_scale(self):
        common = dict(rooty=950, height=80, w=400, h=600)
        self.assertEqual(self.place((1920, 0, 3840, 1040), frame=(16, 40), **common)[0], '400x600+2300+400')
        self.assertEqual(self.place((1920, 0, 3840, 1040), frame=(24, 60), **common)[0], '400x600+2300+380')


class Frame(unittest.TestCase):
    def test_it_grows_with_the_scale(self):
        small = app_module.frame_size_for_dpi(96)
        if small is None:
            self.skipTest('Windows only')
        middle, large = app_module.frame_size_for_dpi(120), app_module.frame_size_for_dpi(144)
        self.assertGreater(small[1], small[0])          # the title bar
        self.assertGreater(middle[1], small[1])
        self.assertGreater(large[1], middle[1])
        self.assertGreater(large[0], small[0])

    def test_when_windows_cannot_say(self):
        root = NS(winfo_id=mock.Mock(side_effect=OSError))
        self.assertEqual(app_module.window_frame_size(root), app_module.FALLBACK_FRAME_SIZE)
        with mock.patch('ctypes.windll') as windll:
            windll.user32.GetParent.return_value = 1
            windll.user32.GetDpiForWindow.return_value = 0        # no answer for this window
            self.assertEqual(app_module.window_frame_size(NS(winfo_id=lambda: 5)), app_module.FALLBACK_FRAME_SIZE)
            windll.user32.GetDpiForWindow.return_value = 120
            with mock.patch.object(app_module, 'frame_size_for_dpi', return_value=(20, 49)) as asked:
                self.assertEqual(app_module.window_frame_size(NS(winfo_id=lambda: 5)), (20, 49))
            asked.assert_called_once_with(120)


class Source(unittest.TestCase):
    def test_every_menu_bar_menu_gets_the_theme(self):
        tree = ast.parse(Path(app_module.__file__).read_text(encoding='utf-8'))
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_build_menu_bar') \
            if any(isinstance(n, ast.FunctionDef) and n.name == '_build_menu_bar' for n in ast.walk(tree)) else tree
        made = set()
        listed = set()
        for node in ast.walk(method):
            if isinstance(node, ast.Assign):
                names = [t.elts[1] if isinstance(t, ast.Tuple) and len(t.elts) == 2 else t for t in node.targets]
                value = ast.unparse(node.value)
                if value.startswith('tk.Menu(') or value.startswith('_make_menubutton('):
                    for name in names:
                        made.add(ast.unparse(name))
                if any(ast.unparse(t) == 'self._menus' for t in node.targets) and isinstance(node.value, ast.List):
                    listed |= {ast.unparse(e) for e in node.value.elts}
        made = {name for name in made if name.startswith('m_') or name.endswith('_menu')}
        self.assertIn('m_lang', made)
        self.assertEqual(sorted(made - listed), [])


if __name__ == '__main__':
    unittest.main()
