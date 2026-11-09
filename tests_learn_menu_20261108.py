# -*- coding: utf-8 -*-
"""The learning menu without the learned history (2026-11-08 うにさん「学習メニューから、不要となる項目を外してください」):
「語彙を追加（日本語用）」「文章から学習」「辞書を取り込む」 add to the learned layer, which adds nothing now, and are
not shown; 「補正の判断」 and 「索引を作り直す」 stay. With CN_LEARNED_HISTORY=1 the menu is as before. An isolated copy."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


def child():
    import tkinter as tk
    from unittest.mock import Mock, patch
    import app
    from session import new_tab
    here = Path.cwd().resolve()
    assert (here / '.ui-learn-menu-test-isolated').is_file()
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text='資料')]), ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); root.withdraw()
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        a = app.CorrectNoteApp(root)
        root.update()

        def labels(menu):
            out = []
            for i in range(menu.index('end') + 1):
                if menu.type(i) in ('command', 'cascade', 'checkbutton', 'radiobutton'):
                    out.append(menu.entrycget(i, 'label'))
            return out
        learn, maint = a._menus[-2], a._menus[-1]
        print('MENU', json.dumps(dict(learn=labels(learn), maint=labels(maint)), ensure_ascii=False), flush=True)
        a._on_close()


class LearnMenu(unittest.TestCase):
    def run_child(self, history):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-learn-menu-') as directory:
            dest = Path(directory).resolve()
            for entry in source.iterdir():
                if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                    shutil.copy2(entry, dest / entry.name)
            (dest / '.ui-learn-menu-test-isolated').touch()
            env = {k: v for k, v in os.environ.items() if k != 'CN_LEARNED_HISTORY'}
            if history:
                env['CN_LEARNED_HISTORY'] = '1'
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                                 cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding='utf-8', errors='replace', timeout=200, env=env)
            self.assertEqual(run.returncode, 0, run.stdout[-3000:])
            line = [l for l in run.stdout.splitlines() if l.startswith('MENU ')]
            self.assertTrue(line, run.stdout[-3000:])
            return json.loads(line[0][len('MENU '):])

    def test_default_hides_the_learned_layer_items(self):
        got = self.run_child(False)
        self.assertIn('補正の判断…', got['learn'])
        self.assertIn('辞書と語彙の管理', got['learn'])
        self.assertEqual(got['maint'], ['索引を作り直す…'])

    def test_learned_history_on_shows_them_as_before(self):
        got = self.run_child(True)
        self.assertEqual(got['maint'], ['語彙を追加（日本語用）…', '文章から学習…', '辞書を取り込む…', '索引を作り直す…'])


if __name__ == '__main__':
    if '--child' in sys.argv: child()
    else: unittest.main()
