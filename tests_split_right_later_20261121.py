# -*- coding: utf-8 -*-
"""分割の表示でタブを切り替えた時、右の補正欄は後から描く（2026-11-21 うにさん「描く順は、右の補正欄は遅れてよい。
品詞ごとのフォントは遅らせない」）。CN_SPLIT_RIGHT_LATER=0 で前の形。自分の Tk の窓だけ（画面の外）・作った例文。"""
import json
import os
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

import split_right_later as S


class FakeApp:
    def __init__(self, root, unified=False):
        self.root = root
        self.unified = unified
        self.rendered = 0
        self._closing = False

    def _layout_is_unified(self):
        return self.unified

    def _render_corrected(self):
        if S.take(self):
            return
        self.rendered += 1


class Unit(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def pump(self, s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            self.root.update()
            time.sleep(0.005)

    def test_armed_render_goes_later(self):
        app = FakeApp(self.root)
        S.arm(app)
        app._render_corrected()
        self.assertEqual(app.rendered, 0)                  # 切り替えの中では描かない
        self.assertTrue(S.pending(app))
        S.disarm(app)
        with mock.patch.object(S, 'input_waiting', return_value=False):
            self.pump(0.1)
        self.assertEqual(app.rendered, 1)                  # 次の一瞬に1回
        self.assertFalse(S.pending(app))

    def test_other_render_overtakes_and_cancels(self):
        app = FakeApp(self.root)
        S.arm(app)
        app._render_corrected()
        S.disarm(app)
        app._render_corrected()                            # 解析の答えなど、別の道の作り直し
        self.assertEqual(app.rendered, 1)
        self.assertFalse(S.pending(app))
        self.pump(0.1)
        self.assertEqual(app.rendered, 1)                  # 二重には描かない

    def test_waits_for_waiting_input_but_not_forever(self):
        app = FakeApp(self.root)
        S.arm(app)
        app._render_corrected()
        S.disarm(app)
        with mock.patch.object(S, 'input_waiting', return_value=True), mock.patch.object(S, 'MAX_WAIT_S', 0.25):
            self.pump(0.12)
            self.assertEqual(app.rendered, 0)              # 打った字を先に通す
            self.pump(0.4)
        self.assertEqual(app.rendered, 1)                  # 待つのは最長 MAX_WAIT_S

    def test_unified_and_switch_off_render_at_once(self):
        app = FakeApp(self.root, unified=True)
        S.arm(app)
        app._render_corrected()
        self.assertEqual(app.rendered, 1)
        with mock.patch.dict(os.environ, {'CN_SPLIT_RIGHT_LATER': '0'}):
            app = FakeApp(self.root)
            S.arm(app)
            app._render_corrected()
            self.assertEqual(app.rendered, 1)

    def test_closing_does_not_render(self):
        app = FakeApp(self.root)
        S.arm(app)
        app._render_corrected()
        S.disarm(app)
        app._closing = True
        self.pump(0.1)
        self.assertEqual(app.rendered, 0)


CHILD = r'''
import json, os, sys, time, traceback
from pathlib import Path
def main():
    here = Path.cwd().resolve()
    assert not (here / 'vocabulary.json').exists()
    import tkinter as tk
    from unittest.mock import Mock, patch
    import app
    from session import new_tab
    from pos_font import POS_FONT_TAGS
    big = chr(10).join('%d行目の本文です。会議の資料を作る' % i for i in range(1, 31))
    small = chr(10).join('小さいタブの%d行目' % i for i in range(1, 6))
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=big), new_tab(text=small)]), ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); out = {}
    def pump(s, until=None):
        end = time.monotonic() + s
        while time.monotonic() < end:
            root.update(); time.sleep(0.005)
            if until is not None and until():
                return True
        return False
    tags = set(POS_FONT_TAGS.values())
    def pos(w):
        return sum(1 for t in w.tag_names() if t in tags and w.tag_ranges(t))
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        import offscreen_window; offscreen_window.hold(root)      # 作る間も見えない所に（画面の置き方に依らない）
        a = app.CorrectNoteApp(root)
        import offscreen_window; offscreen_window.hold(root, '1000x600')
        pump(60, lambda: not a._foreground_analysis_pending() and all(r and not r.get('pending') for r in a.line_results[:30]))
        pump(1)
        a._switch_tab(1); pump(2)
        aligned = []
        real = a._align_pane_rows
        def counting():
            aligned.append(getattr(a, '_right_later_job', None) is not None)
            return real()
        a._align_pane_rows = counting
        a._switch_tab(0)
        out['right_after_call'] = a.result_view.get('1.0', '1.end')
        out['pending_after_call'] = getattr(a, '_right_later_job', None) is not None
        root.update_idletasks()
        boards = getattr(a, '_right_later_covers', None) or []
        out['covered'] = [bool(b.winfo_ismapped()) for _w, b in boards]
        out['cover_bg_same'] = [str(b.cget('bg')) == str(w.cget('bg')) for w, b in boards]
        out['left_pos_drawn'] = pos(a.editor)
        out['left_text'] = a.editor.get('1.0', '1.end')
        pump(3)
        out['pending_later'] = getattr(a, '_right_later_job', None) is not None
        out['covered_later'] = [bool(b.winfo_ismapped()) for _w, b in boards]
        out['right_later'] = a.result_view.get('1.0', '1.end')
        out['left_pos_final'] = pos(a.editor)
        out['right_pos_final'] = pos(a.result_view)
        out['aligned_while_pending'] = aligned.count(True)
        out['aligned_after'] = aligned.count(False)
        import offscreen_window; out['on_screen'] = offscreen_window.on_a_screen(root)
        open('child_out.json', 'w', encoding='utf-8').write(json.dumps(out, ensure_ascii=False))
        os._exit(0)
if __name__ == '__main__':
    try:
        main()
    except Exception:
        open('child_out.json', 'w', encoding='utf-8').write(json.dumps({'error': traceback.format_exc()}))
        os._exit(1)
'''


def run_child(case, env_extra=None):
    here = Path(__file__).resolve().parent
    if here == Path(r'C:\CorrectNote') or (here / 'vocabulary.json').exists():
        case.skipTest('写しの中で回す')
    d = Path(tempfile.mkdtemp(prefix='cn-srl-'))
    import shutil
    for e in here.iterdir():
        if e.is_file() and e.suffix == '.py':
            shutil.copy2(e, d / e.name)
        elif e.is_file() and e.suffix in ('.json', '.txt', '.tsv', '.gz', '.bin', '.dic', '.csv') and e.name not in (
                'settings.json', 'session.json', 'vocabulary.json', 'last_choice.json'):
            shutil.copy2(e, d / e.name)
    (d / 'zz_child.py').write_text(CHILD, encoding='utf-8')
    env = dict(os.environ); env.pop('PYTHONPATH', None); env.update(env_extra or {})
    subprocess.run([sys.executable, '-B', '-X', 'utf8', 'zz_child.py'], cwd=d, env=env, timeout=240,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    got = json.loads((d / 'child_out.json').read_text(encoding='utf-8'))
    shutil.rmtree(d, ignore_errors=True)
    case.assertNotIn('error', got, got.get('error'))
    return got


class InTheApp(unittest.TestCase):
    def test_left_first_right_later_same_end(self):
        got = run_child(self)
        self.assertTrue(got['pending_after_call'], got)                 # 切り替えの中では右を作り直さない
        self.assertTrue(got['right_after_call'].startswith('小さいタブ'), got)
        self.assertTrue(got['left_text'].startswith('1行目'), got)      # 左はその場で新しいタブ
        self.assertGreater(got['left_pos_drawn'], 0, got)               # 左の品詞のフォントは遅らせない
        self.assertEqual(got['left_pos_drawn'], got['left_pos_final'], got)
        self.assertFalse(got['pending_later'], got)
        self.assertTrue(got['right_later'].startswith('1行目'), got)    # 右も後から新しいタブ
        self.assertGreater(got['right_pos_final'], 0, got)
        self.assertGreater(got['aligned_after'], 0, got)                # 右を作り直した時にいつもの道でそろえる
        self.assertEqual(got['covered'], [True, True], got)              # 待つ間は右と行番号を空に（地の色の板）
        self.assertEqual(got['cover_bg_same'], [True, True], got)
        self.assertEqual(got['covered_later'], [False, False], got)      # 作り直したら外す
        self.assertFalse(got['on_screen'], got)                          # 試しの窓は画面に出ない

    def test_no_blank_switch(self):
        got = run_child(self, {'CN_SPLIT_RIGHT_BLANK': '0'})
        self.assertTrue(got['pending_after_call'], got)
        self.assertEqual(got['covered'], [], got)

    def test_switch_back(self):
        got = run_child(self, {'CN_SPLIT_RIGHT_LATER': '0'})
        self.assertFalse(got['pending_after_call'], got)
        self.assertTrue(got['right_after_call'].startswith('1行目'), got)


if __name__ == '__main__':
    unittest.main()
