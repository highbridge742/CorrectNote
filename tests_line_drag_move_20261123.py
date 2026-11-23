# -*- coding: utf-8 -*-
"""行で選んだ範囲を行頭へドラッグで移すと、行として移す（2026-11-23 うにさん「行番号をクリックして、またはShift+スペースで
行を選択した場合、その範囲をドラッグ移動して行頭に持って行った場合は後ろの改行も移動する。移す前の場所に空白行は残らず、
移したあとは後ろに改行を加える」）。
・行番号で選んだ形（行頭〜次の行頭）・Shift+Space の形（行頭〜行末）のどちらも
・上へ・下へ・最終行（前の改行を消す）・複数行。元の場所に空行は残らない。Undo 1回で戻る
・行の途中へ落とす時・選択を手で変えた後は今までどおり
・アプリの中でも、行番号のクリックと Shift+Space で選んだ範囲が行として移る
CN_LINE_DRAG_MOVE=0 で前の形。作った文だけ。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

import drag_move

TEXT = '1行目\n2行目\n3行目\n4行目\n5行目'


class LineDrop(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.w = tk.Text(self.root, undo=True, autoseparators=True)
        self.w.pack()
        self.w.insert('1.0', TEXT)
        self.w.edit_reset()
        self.d = drag_move.DragMove(NS(), self.w, on_change=None, body=False)

    def select(self, first, last, lines=True):
        self.w.tag_remove('sel', '1.0', 'end')
        self.w.tag_add('sel', first, last)
        if lines:
            drag_move.mark_lines(self.w)
        self.d.sel = (str(self.w.index(first)), str(self.w.index(last)))

    def text(self):
        return self.w.get('1.0', 'end-1c')

    def test_gutter_row_down(self):
        self.select('2.0', '3.0')                          # 行番号で2行目
        self.assertTrue(self.d.drop('5.0'))
        self.assertEqual(self.text(), '1行目\n3行目\n4行目\n2行目\n5行目')
        self.assertFalse(self.w.tag_ranges('sel'))                   # 落とした後は選択を外す（CN_DRAG_DROP_DESELECT）
        self.assertEqual(self.w.index('insert'), '5.0')               # 移した行の次の行頭

    def test_shift_space_row_up(self):
        self.select('4.0', '4.end')                        # Shift+Space で4行目
        self.assertTrue(self.d.drop('1.0'))
        self.assertEqual(self.text(), '4行目\n1行目\n2行目\n3行目\n5行目')

    def test_last_row(self):
        self.select('5.0', '5.end')
        self.assertTrue(self.d.drop('2.0'))
        self.assertEqual(self.text(), '1行目\n5行目\n2行目\n3行目\n4行目')   # 後ろに空行を残さない

    def test_many_rows(self):
        self.select('2.0', '4.0')                          # 行番号のドラッグで2〜3行目
        self.assertTrue(self.d.drop('1.0'))
        self.assertEqual(self.text(), '2行目\n3行目\n1行目\n4行目\n5行目')
        self.select('1.0', '2.end')                        # Shift+Space で広げた形
        self.assertTrue(self.d.drop('5.0'))
        self.assertEqual(self.text(), '1行目\n4行目\n2行目\n3行目\n5行目')

    def test_undo_once(self):
        self.select('2.0', '3.0')
        self.d.drop('5.0')
        self.w.edit_undo()
        self.assertEqual(self.text(), TEXT)

    def test_middle_of_a_row_is_as_before(self):
        self.select('2.0', '3.0')
        self.assertTrue(self.d.drop('4.1'))
        self.assertEqual(self.text(), '1行目\n3行目\n4' + '2行目\n' + '行目\n5行目')

    def test_selection_changed_by_hand_is_as_before(self):
        self.select('2.0', '3.0')
        self.select('2.0', '2.2', lines=False)            # 手で選び直した（印と違う）
        self.assertTrue(self.d.drop('5.0'))
        self.assertEqual(self.text(), '1行目\n目\n3行目\n4行目\n2行5行目')

    def test_same_place_is_not_moved(self):
        self.select('2.0', '3.0')
        self.assertFalse(self.d.drop('3.0'))
        self.assertEqual(self.text(), TEXT)

    def test_switch_back(self):
        with mock.patch.dict(os.environ, {'CN_LINE_DRAG_MOVE': '0'}):
            self.select('4.0', '4.end')
            self.assertTrue(self.d.drop('1.0'))
        self.assertEqual(self.text(), '4行目1行目\n2行目\n3行目\n\n5行目')   # 前の形: 改行は動かず空行が残る


CHILD = r'''
import json, os, sys, time, traceback
from pathlib import Path
def main():
    here = Path.cwd().resolve()
    assert not (here / 'vocabulary.json').exists()
    import tkinter as tk
    from types import SimpleNamespace as NS
    from unittest.mock import Mock, patch
    import app
    from session import new_tab
    text = chr(10).join('%d行目は会議の資料を確認するための作った文です。' % i for i in range(1, 9))
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=text)]), ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e))[-500:])
    def pump(s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            root.update(); time.sleep(0.003)
    out = {}
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        a = app.CorrectNoteApp(root)
        root.geometry('1200x800+40+40')
        pump(3)
        ed = a.editor
        d = ed._cn_drag_move
        def rows():
            return [ed.get('%d.0' % r, '%d.end' % r)[:2] for r in range(1, 10)]     # 後ろの空行（新しい文書の余白）は9行目だけ見る
        # 行番号のクリック（3行目）→ 6行目の行頭へ
        a.editor_gutter._select_lines(3, 3)
        d.sel = (str(ed.index('sel.first')), str(ed.index('sel.last')))
        out['gutter_moved'] = d.drop('6.0')
        out['after_gutter'] = rows()
        ed.edit_undo()
        out['after_undo'] = rows()
        # Shift+Space（5行目）→ 1行目の行頭へ
        ed.tag_remove('sel', '1.0', 'end')
        ed.mark_set('insert', '5.3')
        a._on_select_line_text(NS(widget=ed))
        d.sel = (str(ed.index('sel.first')), str(ed.index('sel.last')))
        out['space_moved'] = d.drop('1.0')
        out['after_space'] = rows()
        ed.edit_undo(); pump(0.3)
        # 本当のイベント: 行番号（4行目）を押して離す → 本文の選んだ行の中を押して、7行目の行頭へ引いて離す
        ed.tag_remove('sel', '1.0', 'end')
        g = a.editor_gutter
        t = int(time.monotonic() * 1000)
        d4 = ed.dlineinfo('4.0')
        gy = d4[1] + d4[3] // 2
        g.event_generate('<ButtonPress-1>', x=10, y=gy, time=t)
        g.event_generate('<ButtonRelease-1>', x=10, y=gy, time=t + 60)
        pump(0.5)
        out['real_sel'] = [str(i) for i in ed.tag_ranges('sel')]
        out['real_mark'] = list(getattr(ed, '_cn_line_sel', None) or ())
        bb = ed.bbox('4.3')
        d7 = ed.dlineinfo('7.0')
        x0, y0 = bb[0] + 2, bb[1] + bb[3] // 2
        x1, y1 = d7[0] + 1, d7[1] + d7[3] // 2
        ed.focus_force(); pump(0.2)
        ed.event_generate('<ButtonPress-1>', x=x0, y=y0, time=t + 2000)
        pump(0.05)
        for k in range(1, 8):
            ed.event_generate('<B1-Motion>', x=x0 + (x1 - x0) * k // 7, y=y0 + (y1 - y0) * k // 7, state=0x100, time=t + 2000 + 30 * k)
            pump(0.03)
        out['before_release_sel'] = [str(i) for i in ed.tag_ranges('sel')]
        out['before_release_mark'] = list(getattr(ed, '_cn_line_sel', None) or ())
        ed.event_generate('<ButtonRelease-1>', x=x1, y=y1, state=0x100, time=t + 2400)
        pump(0.5)
        out['after_real'] = rows()
        pump(0.5)
        out['errors'] = errors
        open('child_out.json', 'w', encoding='utf-8').write(json.dumps(out, ensure_ascii=False))
        os._exit(0)
if __name__ == '__main__':
    try:
        main()
    except Exception:
        open('child_out.json', 'w', encoding='utf-8').write(json.dumps({'error': traceback.format_exc()}))
        os._exit(1)
'''


def run_child(case):
    here = Path(__file__).resolve().parent
    if here == Path(r'C:\CorrectNote') or (here / 'vocabulary.json').exists():
        case.skipTest('写しの中で回す')
    d = Path(tempfile.mkdtemp(prefix='cn-linedrag-'))
    for e in here.iterdir():
        if e.is_file() and e.name not in ('settings.json', 'session.json', 'vocabulary.json', 'last_choice.json'):
            shutil.copy2(e, d / e.name)
    (d / 'zz_child.py').write_text(CHILD, encoding='utf-8')
    env = dict(os.environ); env.pop('PYTHONPATH', None)
    subprocess.run([sys.executable, '-B', '-X', 'utf8', 'zz_child.py'], cwd=d, env=env, timeout=200,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    got = json.loads((d / 'child_out.json').read_text(encoding='utf-8'))
    shutil.rmtree(d, ignore_errors=True)
    case.assertNotIn('error', got, got.get('error'))
    return got


class InTheApp(unittest.TestCase):
    def test_gutter_click_and_shift_space(self):
        got = run_child(self)
        self.assertEqual(got['errors'], [], got)
        self.assertTrue(got['gutter_moved'], got)
        self.assertEqual(got['after_gutter'], ['1行', '2行', '4行', '5行', '3行', '6行', '7行', '8行', ''], got)
        self.assertEqual(got['after_undo'], ['%d行' % i for i in range(1, 9)] + [''], got)
        self.assertTrue(got['space_moved'], got)
        self.assertEqual(got['after_space'], ['5行', '1行', '2行', '3行', '4行', '6行', '7行', '8行', ''], got)
        # 本当のイベントで、行番号のクリック → 本文で引いて行頭へ落とす
        self.assertEqual(got['after_real'], ['1行', '2行', '3行', '5行', '6行', '4行', '7行', '8行', ''], got)


if __name__ == '__main__':
    unittest.main()
