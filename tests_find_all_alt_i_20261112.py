# -*- coding: utf-8 -*-
"""全タブ検索の4つ（2026-11-12 うにさん）。隔てた写し・作った文で、本物のキーはほかの窓へ送らない（イベントはアプリの
窓の中だけ）。クリップボードは触らない。

  1) 検索の窓で Alt+I: 半角（<Alt-i> の束縛）でも、IME が全角の時（ｉ・に の字を伴って検索欄のキーの束縛に届く）でも、
     検索欄の文字で全タブ検索する。前は全角の時に何もせずに捨てていた
  2) 本文を選んで Alt+I で全タブ検索した時は、結果の窓を前に出して一覧にフォーカスを移す
  3) 本体の横に余白が無く、左隣にモニターがあれば、結果の窓はそのモニターの作業領域の右端に出る（左隣が無ければ
     今の置き方のまま）。モニターは作った値（monitor_work_area・monitor_left_of を差し替える）
  4) 列の幅: タブの列＝行:桁の列、一致箇所の列＝その2倍。窓の横幅もそれに合わせて縮む
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import unittest


def child():
    import tkinter as tk
    from types import SimpleNamespace
    from unittest.mock import Mock, patch
    import app
    from session import new_tab
    here = Path.cwd().resolve()
    assert (here / '.ui-find-alt-i-test-isolated').is_file()
    tabs = [new_tab(text='資料の一行目。\n二行目にも資料。'), new_tab(text='別のタブの資料。')]
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=tabs), ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); root.withdraw(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))
    tk.Misc.clipboard_get = lambda self, **kw: ''
    tk.Misc.clipboard_clear = lambda self, **kw: None
    tk.Misc.clipboard_append = lambda self, s, **kw: None

    def pump(seconds, until=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            root.update(); time.sleep(0.005)
            if until is not None and until(): return True
        return False

    def done():
        text = a._all_tab_notice.cget('text') if getattr(a, '_all_tab_notice', None) is not None else ''
        return '件' in text and '中' not in text
    out = {}
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        a = app.CorrectNoteApp(root)
        root.geometry('900x500+40+40'); root.deiconify(); pump(1.5)
        # 2) 本文を選んで Alt+I（本体の束縛と同じ入口）
        a.editor.tag_add('sel', '1.0', '1.2')
        a._alt_i_find_all_tabs(SimpleNamespace(widget=a.editor))
        pump(3.0, done)
        d = a._all_tab_dialog
        out['editor_hits'] = len(a._all_tab_hits)
        out['editor_focus'] = d.focus_lastfor() is a._all_tab_tree
        out['editor_viewable'] = bool(d.winfo_viewable())
        # 4) 列の幅と窓の横幅
        tree = a._all_tab_tree
        out['cols'] = [int(tree.column(c, 'width')) for c in ('tab', 'line', 'text')]
        out['width'] = d.winfo_width()
        # 1) 検索の窓で Alt+I（半角: 窓の <Alt-i> の束縛）
        a._close_all_tab_results(); pump(0.2)
        a._find_query.set('一行目')
        a._find_entry.focus_force(); pump(0.2)
        a._find_entry.event_generate('<Alt-i>'); pump(3.0, done)
        out['find_half_hits'] = len(a._all_tab_hits)
        out['find_half_focus'] = a._all_tab_dialog.focus_lastfor() is a._all_tab_tree
        # 1) IME が全角の時: ｉ（かな入力なら に）の字を伴い、Alt の印つきで検索欄のキーの束縛に届く
        a._close_all_tab_results(); pump(0.2)
        a._all_tab_hits = {}                       # 前の検索の結果を数えないように
        a._find_query.set('二行目')
        got = a._on_ime_ascii_key(SimpleNamespace(widget=a._find_entry, char='ｉ', keysym='i', state=0x20000, keycode=73))
        pump(3.0, done)
        out['find_full_break'] = got == 'break'
        out['find_full_hits'] = len(a._all_tab_hits)
        out['find_full_query'] = a._find_query.get()
        # 3) 余白が無い時は左隣のモニターの右端へ（モニターは作った値）
        a._close_all_tab_results(); pump(0.2)
        here_area, left_area = (1000, 0, 2000, 1000), (0, 0, 1000, 960)
        root.geometry('1000x900+1000+0'); pump(0.5)
        with patch.object(app, 'monitor_work_area', lambda x, y: here_area), \
                patch.object(app, 'monitor_left_of', lambda x, y: left_area):
            a._find_query.set('資料')
            a._do_find_all_tabs(); pump(3.0, done)
            d = a._all_tab_dialog; pump(0.3)
            fw, fh = app.window_frame_size(root)
            out['left_right_edge'] = d.winfo_x() + d.winfo_width() + fw
            out['left_x'] = d.winfo_x()
        # 左隣が無い時は今の置き方のまま（本体のモニターの中）
        a._close_all_tab_results(); pump(0.2)
        with patch.object(app, 'monitor_work_area', lambda x, y: here_area), \
                patch.object(app, 'monitor_left_of', lambda x, y: None):
            a._do_find_all_tabs(); pump(3.0, done)
            pump(0.3)
            out['no_left_x'] = a._all_tab_dialog.winfo_x()
        assert not errors, errors
        print('ALTI', json.dumps(out, ensure_ascii=False), flush=True)
        a._on_close()


class FindAllAltI(unittest.TestCase):
    def test_alt_i_focus_left_monitor_and_columns(self):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-find-alt-i-') as directory:
            dest = Path(directory).resolve()
            for entry in source.iterdir():
                if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                    shutil.copy2(entry, dest / entry.name)
            (dest / '.ui-find-alt-i-test-isolated').touch()
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                                 cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding='utf-8', errors='replace', timeout=300)
            self.assertEqual(run.returncode, 0, run.stdout[-3000:])
            line = [l for l in run.stdout.splitlines() if l.startswith('ALTI ')]
            self.assertTrue(line, run.stdout[-3000:])
            got = json.loads(line[0][len('ALTI '):])
            print(got)
            self.assertEqual(got['editor_hits'], 3, got)                 # 「資料」は3か所
            self.assertTrue(got['editor_focus'] and got['editor_viewable'], got)
            self.assertEqual(got['cols'], [70, 70, 140], got)
            self.assertLess(got['width'], 500, got)
            self.assertEqual(got['find_half_hits'], 1, got)
            self.assertTrue(got['find_half_focus'], got)
            self.assertTrue(got['find_full_break'], got)
            self.assertEqual(got['find_full_hits'], 1, got)
            self.assertEqual(got['find_full_query'], '二行目', got)      # 字は検索欄に入らない
            self.assertLessEqual(abs(got['left_right_edge'] - 1000), 2, got)
            self.assertGreaterEqual(got['left_x'], 0, got)
            self.assertGreaterEqual(got['no_left_x'], 1000, got)


if __name__ == '__main__':
    if '--child' in sys.argv:
        child()
    else:
        unittest.main()
