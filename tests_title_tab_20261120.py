# -*- coding: utf-8 -*-
"""タイトルの行の Tab は何もしない（2026-11-20: タイトルにタブの字が入り、焦点が補正欄へ飛んでいた）。Shift+Tab も焦点を
動かさない。Ctrl+Tab は文書のタブを替えるだけ。本文・簡易入力の Tab（タブの字）は今のまま。CN_TITLE_TAB=0 で前の形。
アプリを試しの写し（プログラムと同梱の物だけ・作った例文）で子として起こし、自分の窓の欄へだけキーの知らせを送る。"""
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
    assert (here / '.ui-title-tab-test-isolated').is_file()
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)),
                                        encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[
        new_tab(text='一行目の文。\n二行目。'), new_tab(text='別のタブ')]), ensure_ascii=False), encoding='utf-8')
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
        root.geometry('900x600+40+40')
        pump(1.5)
        ed = a.editor
        toc = a._title_toc
        out['inline'] = bool(toc is not None and getattr(toc, 'inline', False))

        def focus():
            f = root.focus_get()
            return str(f) if f is not None else None

        def press(sym, state=0):
            ed.event_generate('<KeyPress>', keysym=sym, state=state, when='now')
            ed.event_generate('<KeyRelease>', keysym=sym, state=state, when='now')
            pump(0.3)
        if out['inline']:
            for name, state in (('tab', 0), ('shift_tab', 1), ('ctrl_tab', 4)):
                ed.focus_force(); pump(0.1)
                toc.enter_title(0); pump(0.2)
                t0 = toc.title.get('1.0', 'end-1c')
                active0 = a.session.active
                press('Tab', state)
                out[name] = dict(tabs=toc.title.get('1.0', 'end-1c').count('\t') - t0.count('\t'),
                                 focus_on_editor=focus() == str(ed), in_title=bool(getattr(toc, '_active', False)),
                                 switched=a.session.active != active0)
                if out[name]['switched']:
                    a._next_tab(-1); pump(0.3)
            toc.leave_title(); pump(0.1)
        # 本文の Tab は今のまま（タブの字が入る）
        ed.focus_force(); pump(0.1)
        ed.mark_set('insert', 'end-1c')
        before = ed.get('1.0', 'end-1c').count('\t')
        press('Tab')
        out['body_tab'] = ed.get('1.0', 'end-1c').count('\t') - before
        assert not errors, errors
        print('TITLE_TAB', json.dumps(out), flush=True)
        a._on_close()


def run_child(test, env=None):
    from bundle_manifest import NAMES
    source = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='correctnote-title-tab-') as directory:
        dest = Path(directory).resolve()
        for entry in source.iterdir():
            if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                shutil.copy2(entry, dest / entry.name)
        (dest / '.ui-title-tab-test-isolated').touch()
        environ = dict(os.environ)
        environ.update(env or {})
        run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                             cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environ,
                             encoding='utf-8', errors='replace', timeout=240)
        test.assertEqual(run.returncode, 0, run.stdout[-3000:])
        line = [l for l in run.stdout.splitlines() if l.startswith('TITLE_TAB ')]
        test.assertTrue(line, run.stdout[-3000:])
        return json.loads(line[0][len('TITLE_TAB '):])


class TitleTab(unittest.TestCase):
    def test_tab_in_the_title_does_nothing(self):
        got = run_child(self)
        self.assertTrue(got['inline'], got)                                   # 既定は本文の中の見出しの形
        self.assertEqual(got['tab'], dict(tabs=0, focus_on_editor=True, in_title=True, switched=False), got)
        self.assertEqual(got['shift_tab'], dict(tabs=0, focus_on_editor=True, in_title=True, switched=False), got)
        self.assertEqual(got['ctrl_tab']['tabs'], 0, got)
        self.assertTrue(got['ctrl_tab']['switched'], got)                     # Ctrl+Tab は文書のタブを替える
        self.assertTrue(got['ctrl_tab']['focus_on_editor'], got)
        self.assertEqual(got['body_tab'], 1, got)                             # 本文の Tab は今のまま

    def test_switch_back(self):
        got = run_child(self, {'CN_TITLE_TAB': '0'})
        self.assertTrue(got['inline'], got)                                   # 既定は本文の中の見出しの形
        self.assertEqual(got['tab']['tabs'], 1, got)                          # 前の形: タイトルにタブの字
        self.assertFalse(got['tab']['focus_on_editor'], got)                  # 前の形: 焦点が飛ぶ


if __name__ == '__main__':
    if '--child' in sys.argv: child()
    else: unittest.main()
