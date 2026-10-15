# -*- coding: utf-8 -*-
"""右の二度押し（縮小モード）を、たまった知らせに左右されずに見分ける（2026-10-15）。

うにさん「表示準備中のとき、縮小モードにならない」「しばらく待ったあとも、縮小が
できたりできなかったりする」。Tk の `<Double-Button-3>` は最後の 30 個の知らせに
1回目の押し下げが残っているかで見るので、解析の結果を当てている間（絵文字の色の札を
置き直す）や候補一覧を開いた直後は、0.15 秒の二度押しでも二度押しにならなかった。
"""
import tkinter as tk
import unittest
from types import SimpleNamespace

import app


class RightDoubleTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('300x200+40+40')
        self.text = tk.Text(self.root)
        self.text.pack(fill='both', expand=True)
        self.root.update()
        a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root
        a.editor = self.text
        self.doubles = []
        a._on_right_double = lambda e, w: self.doubles.append(w)
        a._close_dropdown = lambda *x, **k: None
        a._drag_press = lambda *x, **k: None
        self.a = a
        self.msg = [None]
        self._saved_msg = app._input_message_time
        app._input_message_time = lambda: self.msg[0]

    def tearDown(self):
        app._input_message_time = self._saved_msg
        self.root.destroy()

    def press(self, t, x=50, y=50, widget=None):
        e = SimpleNamespace(time=t, x=x, y=y, x_root=x + 100, y_root=y + 100, num=3)
        return self.a._on_editor_right_press(e)

    def test_two_presses_make_a_double_whatever_came_between(self):
        self.text.bind('<ButtonPress-3>', self.a._on_editor_right_press)
        self.text.bind('<Double-Button-3>', lambda e: self.doubles.append('tk'))
        T = 7000000
        self.text.event_generate('<ButtonPress-3>', x=20, y=20, rootx=120, rooty=120, time=T)
        self.text.event_generate('<ButtonRelease-3>', x=20, y=20, time=T + 50)
        # what the colour labels do while analysis results are laid on: Tk loses the first press
        labels = [tk.Label(self.text, text='x') for _ in range(20)]
        for i, label in enumerate(labels):
            label.place(x=i * 3, y=40)
        self.root.update()
        self.text.event_generate('<ButtonPress-3>', x=20, y=20, rootx=120, rooty=120, time=T + 150)
        self.assertEqual(self.doubles, [self.text])

    def test_a_slow_second_press_or_another_place_is_not_a_double(self):
        self.press(1000)
        self.press(1600)             # 0.6 s later
        self.press(1700, x=60)       # 10 px away
        self.assertEqual(self.doubles, [])
        self.press(1800, x=61)
        self.assertEqual(self.doubles, [self.text])
        self.press(1900, x=61)       # a third press starts over
        self.assertEqual(self.doubles, [self.text])

    def test_a_slow_second_press_after_a_long_release_is_not_a_double(self):
        # Opening the candidates can take a while; a second press made after it
        # finished (3 s later by both clocks) is a new click, not a double.
        self.msg[0] = 70000
        self.press(1000)
        self.msg[0] = 73000
        self.press(4000)
        self.assertEqual(self.doubles, [])

    def test_a_press_handled_late_counts_by_the_time_windows_gave_it(self):
        self.msg[0] = 50000
        self.press(1000)
        self.msg[0] = 50140                 # pressed 0.14 s after the first...
        self.press(1000 + 900)              # ...but handled 0.9 s later (analysis)
        self.assertEqual(self.doubles, [self.text])
        self.msg[0] = 60000
        self.press(5000)
        self.msg[0] = 60700                 # really pressed 0.7 s later
        self.press(5100)                    # handled soon: Tk's time says double
        self.assertEqual(self.doubles, [self.text, self.text])

    def stalled_pair(self, pressed_after_ms):
        """1回目を離したあと候補一覧を開くのに 0.6 秒かかる（その間 Tk は止まる）。
        Tk の time は処理した時刻なので、2回目の time は止まりのぶん遅れる。
        Windows の押下時刻（GetMessageTime）は本当に押した時刻。"""
        import time as _time
        self.msg[0] = 90000
        self.press(5000)                                  # 1回目（押した時刻＝処理した時刻）
        self.a._on_editor_right_click = lambda e: _time.sleep(0.6)
        _time.sleep(0.6)                                  # 離しで候補一覧を開く（止まり）
        handled = 5000 + max(pressed_after_ms, 650)       # 止まりが明けてから処理される
        self.msg[0] = 90000 + pressed_after_ms
        self.press(handled)

    def test_a_second_press_held_up_by_opening_the_candidates_is_a_double(self):
        # うにさん「解析中に縮小しない」の原因3: 0.3 秒後に押したが、処理は 0.65 秒後
        self.stalled_pair(300)
        self.assertEqual(self.doubles, [self.text])

    def test_the_same_stall_with_a_slow_second_press_is_not(self):
        self.stalled_pair(1500)
        self.assertEqual(self.doubles, [])

    def test_the_result_pane_too(self):
        a = self.a
        a.result_view = tk.Text(self.root)
        a._drag = None
        a._scroll_cursor_restore = lambda: None
        a._sync_cursor_line = lambda *x, **k: None
        e = lambda t: SimpleNamespace(time=t, x=5, y=5, x_root=105, y_root=105, num=3)
        a._on_result_press(e(1000))
        self.assertEqual(a._on_result_press(e(1200)), 'break')
        self.assertEqual(self.doubles, [a.result_view])


class MaskForwardTests(RightDoubleTests):
    """行へ移ったときの中央寄せの余白の覆い（_forward_from_mask）の上で押したとき。"""

    def mask_press(self, t):
        self.text.bind('<ButtonPress-3>', self.a._on_editor_right_press)
        # 本体と同じく、Tk が二度押しと見た時も同じ入口へ（どちらでも縮小に入る）
        self.text.bind('<Double-Button-3>', lambda e: self.a._on_right_double(e, self.text))
        e = SimpleNamespace(x_root=self.text.winfo_rootx() + 30, y_root=self.text.winfo_rooty() + 30,
                            state=0, num=3, time=t)
        self.a._forward_from_mask(self.text, e, '<ButtonPress>')
        self.a._forward_from_mask(self.text, e, '<ButtonRelease>')

    def test_a_double_press_on_the_mask_enters_the_overview(self):
        self.mask_press(5000000)
        self.mask_press(5000000 + 180)
        self.assertEqual(self.doubles, [self.text])

    def test_two_presses_three_seconds_apart_do_not(self):
        self.mask_press(6000000)
        self.mask_press(6000000 + 3000)
        self.assertEqual(self.doubles, [])

    # the inherited tests are already run by RightDoubleTests
    test_two_presses_make_a_double_whatever_came_between = None
    test_a_slow_second_press_or_another_place_is_not_a_double = None
    test_a_slow_second_press_after_a_long_release_is_not_a_double = None
    test_a_press_handled_late_counts_by_the_time_windows_gave_it = None
    test_the_result_pane_too = None
    test_a_second_press_held_up_by_opening_the_candidates_is_a_double = None
    test_the_same_stall_with_a_slow_second_press_is_not = None


class ForwardKeepsTimeTests(unittest.TestCase):
    def test_a_press_on_a_colour_label_reaches_the_pane_with_its_time(self):
        import emoji_color
        root = tk.Tk()
        try:
            text = tk.Text(root)
            text.pack()
            root.update()
            seen = []
            text.bind('<ButtonPress-3>', lambda e: seen.append(int(e.time)))
            overlay = emoji_color.EmojiOverlay.__new__(emoji_color.EmojiOverlay)
            overlay.w = text
            overlay._forward(SimpleNamespace(x_root=text.winfo_rootx() + 5, y_root=text.winfo_rooty() + 5,
                                             state=0, num=3, time=123456), '<ButtonPress>')
            self.assertEqual(seen, [123456])
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
