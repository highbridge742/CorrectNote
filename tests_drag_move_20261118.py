# -*- coding: utf-8 -*-
"""長押しで語を選ぶ・選んだ範囲をドラッグで移す（2026-11-18 うにさん・drag_move）。自分の Tk の窓だけ・作った例文。
マウスの知らせは、欄の上の字の位置（bbox）から作った作り物で、束縛の手続きを直に呼ぶ。"""
import os
import time
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import drag_move as D

TEXT = 'alpha beta gamma delta'


class FakeApp:
    def __init__(self):
        self.frames = []
        self.cleared = 0
        self.changed = 0
        self._title_toc = None

    def _show_copy_frame(self, widget, start, end):
        self.frames.append((str(widget.index(start)), str(widget.index(end))))

    def _clear_copy_emphasis(self):
        self.cleared += 1

    def _on_change(self, *a):
        self.changed += 1


class DragMoveTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('600x200+40+40')
        self.w = tk.Text(self.root, undo=True, autoseparators=True, font=('Courier New', 12))
        self.w.pack(fill='both', expand=True)
        self.w.insert('1.0', TEXT)
        self.w.edit_reset()
        self.app = FakeApp()
        self.d = D.install(self.app, self.w)
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    def at(self, index):
        x, y, w, h = self.w.bbox(index)
        return x + 2, y + h // 2

    def ev(self, index, state=0, dx=0):
        x, y = self.at(index)
        return NS(x=x + dx, y=y, state=state)

    def pump(self, sec):
        end = time.monotonic() + sec
        while time.monotonic() < end:
            self.root.update()
            time.sleep(0.005)

    def select(self, a, b):
        self.w.tag_add('sel', a, b)

    def test_bindtag_is_in_front_of_text(self):
        tags = self.w.bindtags()
        self.assertLess(tags.index(D.TAG), tags.index('Text'))

    def test_long_press_selects_the_word(self):
        with mock.patch.object(D, 'LONGPRESS_MS', 30):
            self.assertIsNone(self.d.press(self.ev('1.7')))          # beta の中
            self.pump(0.15)
        self.assertEqual(self.w.get('sel.first', 'sel.last').strip(), 'beta')

    def test_long_press_selects_only_the_word_in_japanese(self):
        # 2026-11-18 うにさん「長押しで、今は行全体が選択されています。ダブルクリックの選択範囲は単語だけです」:
        # Tk の語は空白で区切るので、空白の無い日本語の行は行の全部になっていた。ダブルクリックと同じ手続きで選ぶ
        import mouse_words
        line = '今日は駅前の本屋で新しい本を買いました。'
        self.w.delete('1.0', 'end')
        self.w.insert('1.0', line)
        self.root.update()
        col = line.index('本屋')
        with mock.patch.object(D, 'LONGPRESS_MS', 30):
            self.d.press(self.ev('1.%d' % col))
            self.pump(0.15)
        got = self.w.get('sel.first', 'sel.last')
        a, z = mouse_words.word_at(line, col)
        self.assertEqual(got, line[a:z])                      # ダブルクリックと同じ範囲
        self.assertNotEqual(got, line)                         # 行の全部ではない
        self.assertLess(len(got), 4)

    def test_defaults_220_and_up_to_1000(self):
        # 2026-11-18 うにさん「長押しの時間はデフォルト220で、上限は1000まで」（初めは 500・上限 2000）
        self.assertEqual((D.LONGPRESS_MS, D.LONGPRESS_MS_MAX), (220, 1000))

    def test_drag_caret_is_coloured_and_steady_then_restored(self):
        import editor_guides
        self.w.configure(insertbackground='#123456', insertofftime=300)
        self.select('1.6', '1.11')
        self.d.press(self.ev('1.8'))
        self.d.motion(self.ev('1.8', dx=30))
        self.assertEqual(str(self.w.cget('insertbackground')), editor_guides.FLASH_COLOR)
        self.assertEqual(int(self.w.cget('insertofftime')), 0)        # 点滅しない
        self.d.release(self.ev('1.22'))
        self.assertEqual(str(self.w.cget('insertbackground')), '#123456')
        self.assertEqual(int(self.w.cget('insertofftime')), 300)

    def test_moving_while_pressed_cancels_the_long_press(self):
        with mock.patch.object(D, 'LONGPRESS_MS', 60):
            self.d.press(self.ev('1.7'))
            self.d.motion(self.ev('1.7', dx=20))
            self.pump(0.2)
        self.assertFalse(self.w.tag_ranges('sel'))

    def test_drag_moves_and_one_undo_restores(self):
        self.select('1.6', '1.11')                                   # 'beta '
        self.assertEqual(self.d.press(self.ev('1.8')), 'break')
        self.d.motion(self.ev('1.8', dx=30))
        self.assertTrue(self.app.frames)                             # 白い枠で包む
        self.assertEqual(self.d.release(self.ev('1.22')), 'break')   # 行末へ
        self.assertEqual(self.w.get('1.0', 'end-1c'), 'alpha gamma deltabeta ')
        # 2026-11-23 うにさん「ドラッグ移動で運んだあとは、選択範囲解除する」: 落とした後は選択を外し、カーソルは落とした範囲の
        # 終わり（前は落とした範囲を選んだまま・CN_DRAG_DROP_DESELECT=0）
        self.assertFalse(self.w.tag_ranges('sel'))
        self.assertEqual(self.w.index('insert'), '1.22')
        self.assertTrue(self.app.cleared and self.app.changed)
        self.w.edit_undo()
        self.assertEqual(self.w.get('1.0', 'end-1c'), TEXT)

    def test_ctrl_drop_duplicates(self):
        self.select('1.6', '1.11')
        self.d.press(self.ev('1.8'))
        self.d.motion(self.ev('1.8', dx=30))
        self.d.release(self.ev('1.0', state=0x0004))
        self.assertEqual(self.w.get('1.0', 'end-1c'), 'beta alpha beta gamma delta')
        self.w.edit_undo()
        self.assertEqual(self.w.get('1.0', 'end-1c'), TEXT)

    # 2026-11-20 うにさん「長押しで単語を選択して、クリックを離してまたクリックし、ドラッグしたが単語を移動できなかった。
    # 2文字の単語だったが」: 端は字ではなく、範囲の始まり・終わりの線から数 px だけ（仕様の変更。前は最初と最後の字が端）
    def at_px(self, index, frac):
        x, y, w, h = self.w.bbox(index)
        return NS(x=x + int(w * frac), y=y + h // 2, state=0)

    def test_edges_keep_the_old_click(self):
        self.select('1.6', '1.11')
        x, y, w, h = self.w.bbox('1.6')
        self.assertIsNone(self.d.press(NS(x=x, y=y + h // 2, state=0)))            # 始まりの線の上
        self.d._cancel_timer()
        x, y, w, h = self.w.bbox('1.10')
        self.assertIsNone(self.d.press(NS(x=x + w - 1, y=y + h // 2, state=0)))    # 終わりの線の上
        self.d._cancel_timer()

    def drag_move_of(self, a, b, grab, to='1.22'):
        self.select(a, b)
        word = self.w.get(a, b)
        self.assertEqual(self.d.press(grab), 'break', word)
        self.d.motion(NS(x=grab.x + 30, y=grab.y, state=0))
        self.d.release(self.ev(to))
        return word

    def test_one_and_two_letter_ranges_can_be_grabbed(self):
        word = self.drag_move_of('1.6', '1.8', self.at_px('1.7', 0.5))             # 2字（'be'）の真ん中
        self.assertTrue(self.w.get('1.0', 'end-1c').endswith(word))
        self.w.edit_undo()
        self.assertEqual(self.w.get('1.0', 'end-1c'), TEXT)
        word = self.drag_move_of('1.6', '1.7', self.at_px('1.6', 0.5))             # 1字の真ん中
        self.assertTrue(self.w.get('1.0', 'end-1c').endswith(word))

    def test_long_word_middle_and_old_switch(self):
        word = self.drag_move_of('1.0', '1.5', self.at_px('1.0', 0.5))             # 長い語の最初の字の真ん中も掴める
        self.assertTrue(self.w.get('1.0', 'end-1c').endswith(word))
        self.w.edit_undo()
        with mock.patch.dict(os.environ, {'CN_DRAG_EDGE_PX': '0'}):
            self.select('1.6', '1.8')
            self.assertIsNone(self.d.press(self.at_px('1.7', 0.5)))                # 前の形: 2字は掴めない
            self.d._cancel_timer()

    def test_double_press_inside_the_selection_goes_to_the_drag(self):
        # 長押しの離しのすぐ後の押しは二度押し（<Double-Button-1>）になり、mouse_words が先に受けて語を選び直していた
        import mouse_words
        self.select('1.6', '1.8')
        grab = self.at_px('1.7', 0.5)
        app = NS(_word_drag=None)
        got = mouse_words._double(app, NS(widget=self.w, x=grab.x, y=grab.y, state=0))
        self.assertEqual(got, 'break')
        self.assertEqual(self.d.state, 'armed')                                 # 移す側が受けた
        self.assertEqual(self.w.get('sel.first', 'sel.last'), 'be')             # 選び直していない
        self.d.state = None
        with mock.patch.dict(os.environ, {'CN_DRAG_AFTER_DOUBLE': '0'}):
            mouse_words._double(app, NS(widget=self.w, x=grab.x, y=grab.y, state=0))
        self.assertIsNone(self.d.state)                                         # 前の形: 語を選び直す

    def test_long_press_release_then_press_and_drag(self):
        # 長押しで選ぶ → 離す → もう一度押して動かす（うにさんの順）。状態が残って掴めない、が無いこと
        with mock.patch.object(D, 'LONGPRESS_MS', 30):
            self.d.press(self.ev('1.7'))
            self.pump(0.12)
        self.assertEqual(self.w.get('sel.first', 'sel.last'), 'beta')
        self.d.release(self.ev('1.7'))
        self.assertIsNone(self.d.state)
        first = self.w.index('sel.first')
        grab = self.at_px('%s +1c' % first, 0.5)
        self.assertEqual(self.d.press(grab), 'break')
        self.d.motion(NS(x=grab.x + 30, y=grab.y, state=0))
        self.assertEqual(self.d.state, 'dragging')
        self.d.release(self.ev('1.22'))
        self.assertTrue(self.w.get('1.0', 'end-1c').endswith('beta'))

    def test_click_inside_without_moving_places_the_cursor(self):
        self.select('1.6', '1.11')
        self.d.press(self.ev('1.8'))
        self.d.release(self.ev('1.8'))
        self.assertFalse(self.w.tag_ranges('sel'))
        self.assertEqual(self.w.get('1.0', 'end-1c'), TEXT)

    def test_escape_and_drop_inside_cancel(self):
        self.select('1.6', '1.11')
        self.d.press(self.ev('1.8'))
        self.d.motion(self.ev('1.8', dx=30))
        self.assertEqual(self.d.escape(NS()), 'break')
        self.assertIsNone(self.d.release(self.ev('1.20')))
        self.assertEqual(self.w.get('1.0', 'end-1c'), TEXT)
        self.select('1.6', '1.11')
        self.d.press(self.ev('1.8'))
        self.d.motion(self.ev('1.8', dx=10))
        self.d.release(self.ev('1.9'))                               # 範囲の中へ: 取りやめ
        self.assertEqual(self.w.get('1.0', 'end-1c'), TEXT)

    def test_switches(self):
        with mock.patch.dict(os.environ, {'CN_DRAG_MOVE': '0', 'CN_LONGPRESS_SELECT': '0'}):
            self.select('1.6', '1.11')
            self.assertIsNone(self.d.press(self.ev('1.8')))
            self.assertIsNone(self.d.timer)


class AutoScroll(unittest.TestCase):
    """ドラッグで移す間、欄の上端・下端の帯で送り続ける（2026-11-20 うにさん「ドラッグ移動で、上下スクロールの端までカーソルが
    来たらスクロールさせる」）。CN_DRAG_AUTOSCROLL=0 で前の形。"""
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('500x200+40+40')
        self.w = tk.Text(self.root, undo=True, font=('Courier New', 12))
        self.w.pack(fill='both', expand=True)
        self.w.insert('1.0', '\n'.join('%d 行目 alpha beta' % i for i in range(1, 201)))
        self.w.yview('50.0')
        self.root.update()
        self.app = FakeApp()
        self.app._overview = None
        self.d = D.install(self.app, self.w)
        top = int(self.w.index('@0,0').split('.')[0])
        row = top + 3
        self.w.tag_add('sel', '%d.4' % row, '%d.11' % row)
        x, y, bw, bh = self.w.bbox('%d.6' % row)
        self.d.press(NS(x=x + bw // 2, y=y + bh // 2, state=0))
        self.d.motion(self.ev(x + 40, y + bh // 2))
        self.assertEqual(self.d.state, 'dragging')
        self.x = x + 40

    def tearDown(self):
        self.root.destroy()

    def ev(self, x, y):
        return NS(x=x, y=y, state=0, x_root=self.w.winfo_rootx() + x, y_root=self.w.winfo_rooty() + y)

    def top(self):
        return int(self.w.index('@0,0').split('.')[0])

    def pump(self, sec):
        end = time.monotonic() + sec
        while time.monotonic() < end:
            self.root.update()
            time.sleep(0.005)

    def test_bottom_edge_scrolls_while_held_and_caret_follows(self):
        h = self.w.winfo_height()
        before = self.top()
        with mock.patch('drag_out.drag_text_out') as out:
            self.d.motion(self.ev(self.x, h - 2))           # 下端の帯（止めたまま）
            self.pump(0.4)
        out.assert_not_called()                              # 帯の中は外へ出たとみなさない
        moved = self.top()
        self.assertGreater(moved, before)
        caret = int(self.w.index('insert').split('.')[0])
        self.assertGreaterEqual(caret, moved)                # 落とす先のカーソルも付いていく
        self.d.motion(self.ev(self.x, h // 2))              # 帯から出たら止まる
        stop = self.top()
        self.pump(0.3)
        self.assertEqual(self.top(), stop)

    def test_top_edge_scrolls_up_and_release_stops(self):
        before = self.top()
        self.d.motion(self.ev(self.x, 1))
        self.pump(0.3)
        self.assertLess(self.top(), before)
        self.d.release(self.ev(self.x, 1))
        self.assertIsNone(self.d.scroll_job)
        stop = self.top()
        self.pump(0.2)
        self.assertEqual(self.top(), stop)

    def test_deeper_is_faster(self):
        h = self.w.winfo_height()
        self.d.motion(self.ev(self.x, h - 2))
        self.d._stop_scroll()
        self.d.scroll_at = (self.x, h - 2)
        a = self.top(); self.d._scroll_tick(); deep = self.top() - a
        self.d._stop_scroll()
        band = self.d._band()
        self.d.scroll_at = (self.x, h - band + 1)
        a = self.top(); self.d._scroll_tick(); shallow = self.top() - a
        self.d._stop_scroll()
        self.assertGreater(deep, shallow)

    def test_overview_and_switch_do_not_scroll(self):
        h = self.w.winfo_height()
        self.app._overview = {'fast': True}
        before = self.top()
        self.d.motion(self.ev(self.x, h - 2))
        self.pump(0.2)
        self.assertEqual(self.top(), before)
        self.app._overview = None
        with mock.patch.dict(os.environ, {'CN_DRAG_AUTOSCROLL': '0'}):
            self.d.motion(self.ev(self.x, h - 2))
            self.pump(0.2)
        self.assertEqual(self.top(), before)


if __name__ == '__main__':
    unittest.main()
