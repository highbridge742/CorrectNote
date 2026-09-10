# -*- coding: utf-8 -*-
import json
import tempfile
import unittest
import ast
from types import SimpleNamespace
from pathlib import Path
from ime_readings import IMEReadings


class IMERemovalTests(unittest.TestCase):
    def test_dialog_removes_selected_pair_and_refreshes_analysis(self):
        created = []
        class Var:
            def __init__(self, **kw): self.value = ''
            def get(self): return self.value
            def set(self, value): self.value = value
            def trace_add(self, *args): pass
        class Widget:
            def __init__(self, *args, **kw):
                self.kw = kw
                self.rows = {}
                self.selected = ()
                created.append(self)
            def __getattr__(self, name): return lambda *a, **k: None
            def get_children(self): return list(self.rows)
            def insert(self, *a, **kw):
                item = str(len(self.rows))
                self.rows[item] = kw['values']
                return item
            def delete(self, item): del self.rows[item]
            def selection(self): return self.selected
        ui = SimpleNamespace(**{name: Widget for name in
             ('Toplevel', 'Label', 'Entry', 'Frame', 'Button', 'Treeview', 'Scrollbar')})
        ui.StringVar = Var
        module = ast.parse(Path(__file__).with_name('app.py').read_text(encoding='utf-8'))
        cls = next(n for n in module.body if isinstance(n, ast.ClassDef)
                   and n.name == 'CorrectNoteApp')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef)
                      and n.name == 'open_ime_readings_dialog')
        ns = {'tk': ui, 'ttk': ui, 'BG': '', 'INK': ''}
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'app.py', 'exec'), ns)
        ir = IMEReadings()
        ir.remember('行った', 'いった')
        ir.remember('行った', 'おこなった')
        calls = []
        app = SimpleNamespace(root=None, ime_readings=ir, _ime_pairs_dirty=False,
                              _place_dialog=lambda *args: None,
                              _reanalyze_all=lambda: calls.append('reanalyze'))
        ns['open_ime_readings_dialog'](app)
        tree = next(w for w in created if w.rows)
        tree.selected = (next(i for i, values in tree.rows.items()
                              if values[1] == 'おこなった'),)
        button = next(w for w in created if w.kw.get('text') == '選択した読みを削除')
        button.kw['command']()
        self.assertEqual(ir.readings_for('行った'), ['いった'])
        self.assertEqual(calls, ['reanalyze'])
        self.assertEqual(list(tree.rows.values()), [('行った', 'いった')])

    def test_remove_only_selected_reading_persist_and_reload(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'pairs.json')
            ir = IMEReadings(path)
            ir.remember('行った', 'いった')
            ir.remember('行った', 'おこなった')
            ir.remember('読む', 'よむ')
            ir.save()
            before = ir.stamp()
            self.assertEqual(ir.forget('行った', 'ｵｺﾅｯﾀ'), 1)
            self.assertNotEqual(before, ir.stamp())
            self.assertTrue(ir.save())
            loaded = IMEReadings(path).load()
            self.assertEqual(loaded.readings_for('行った'), ['いった'])
            self.assertEqual(loaded.readings_for('読む'), ['よむ'])
            self.assertEqual(set(json.loads(Path(path).read_text(encoding='utf-8'))),
                             {'version', 'pairs'})

    def test_missing_pair_does_not_change_stamp_or_dirty(self):
        ir = IMEReadings()
        ir.remember('行った', 'いった')
        ir._dirty = False
        before = ir.stamp()
        self.assertEqual(ir.forget('行った', 'おこなった'), 0)
        self.assertEqual(ir.forget('不在'), 0)
        self.assertEqual(ir.stamp(), before)
        self.assertFalse(ir._dirty)

    def test_whole_surface_and_reentry(self):
        ir = IMEReadings()
        ir.remember('行った', 'いった')
        ir.remember('行った', 'おこなった')
        self.assertEqual(ir.forget('行った'), 2)
        self.assertEqual(ir.readings_for('行った'), [])
        self.assertTrue(ir.remember('行った', 'いった'))
        self.assertEqual(ir.readings_for('行った'), ['いった'])


if __name__ == '__main__':
    unittest.main()
