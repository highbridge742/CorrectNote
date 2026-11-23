# -*- coding: utf-8 -*-
"""分割表示の時は、外見の装飾を右の補正欄だけに出し、左のメモ欄は無地（2026-11-20 うにさん「分割モード時、外見装飾は、
右の補正欄だけにして、メモ欄の装飾を消す」）。統合表示は今のまま。切り替えでその場で付け替える。
CN_SPLIT_DECOR_RIGHT_ONLY=0 で前の形。アプリを試しの写し（プログラムと同梱の物だけ・作った例文）で子として起こす。"""
import json
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import unittest


def child():
    import tkinter as tk
    from unittest.mock import Mock, patch
    import app
    from session import new_tab
    here = Path.cwd().resolve()
    assert (here / '.ui-split-decor-test-isolated').is_file()
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False,
                                                        decor='wamon', decor_strength='light')), encoding='utf-8')
    body = '\n'.join('%d 行目の作り物の文です。' % i for i in range(1, 200))
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=body)]),
                                                  ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))

    def pump(s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            root.update(); time.sleep(0.005)
    out = {}
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        a = app.CorrectNoteApp(root)
        root.geometry('1000x600+40+40')
        pump(1.5)

        def look():
            return dict(left=a.editor._correctnote_paper.decor, right=a.result_view._correctnote_paper.decor,
                        left_gutter=getattr(a.editor_gutter.backdrop, 'decor', None),
                        right_gutter=getattr(a.result_gutter.backdrop, 'decor', None))
        out['split'] = look()
        a._on_wheel_units(5); pump(0.4)                       # スクロールしても右の絵は外さない
        out['split_scrolled'] = look()
        a.settings.set('layout', 'unified'); a._apply_layout(); pump(0.4)
        out['unified'] = look()
        a.settings.set('layout', 'split'); a._apply_layout(); pump(0.4)
        out['split_again'] = look()
        assert not errors, errors
        print('SPLIT_DECOR', json.dumps(out), flush=True)
        a._on_close()


def run_child(test, env=None):
    from bundle_manifest import NAMES
    source = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='correctnote-split-decor-') as directory:
        dest = Path(directory).resolve()
        for entry in source.iterdir():
            if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                shutil.copy2(entry, dest / entry.name)
        (dest / '.ui-split-decor-test-isolated').touch()
        environ = dict(os.environ)
        environ.update(env or {})
        run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                             cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environ,
                             encoding='utf-8', errors='replace', timeout=240)
        test.assertEqual(run.returncode, 0, run.stdout[-3000:])
        line = [l for l in run.stdout.splitlines() if l.startswith('SPLIT_DECOR ')]
        test.assertTrue(line, run.stdout[-3000:])
        return json.loads(line[0][len('SPLIT_DECOR '):])


class SplitDecor(unittest.TestCase):
    def test_left_is_plain_in_split_and_follows_the_layout(self):
        got = run_child(self)
        plain_left = dict(left=None, right='wamon', left_gutter=None, right_gutter='wamon')
        self.assertEqual(got['split'], plain_left, got)
        self.assertEqual(got['split_scrolled'], plain_left, got)
        self.assertEqual(got['unified'], dict(left='wamon', right='wamon', left_gutter='wamon', right_gutter='wamon'), got)
        self.assertEqual(got['split_again'], plain_left, got)

    def test_switch_back(self):
        got = run_child(self, {'CN_SPLIT_DECOR_RIGHT_ONLY': '0'})
        self.assertEqual(got['split'], dict(left='wamon', right='wamon', left_gutter='wamon', right_gutter='wamon'), got)


if __name__ == '__main__':
    if '--child' in sys.argv: child()
    else: unittest.main()
