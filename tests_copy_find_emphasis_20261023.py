# -*- coding: utf-8 -*-
"""The copied range and the search hits shown larger (2026-10-23 うにさん).

コピー範囲が行の一部だけなら、その範囲のフォントを 1.3 倍（2026-10-23 に 1.2 から）（行全体を含む行があるコピーでは掛けない。
タブ移動・スクロール・新しいコピーで戻す）。検索の窓が出ている間、見つかった文字を 1.3 倍（窓を閉じたら
戻す）。倍率はデバッグメニューの【表示】。each piece keeps its own font (the size per part of
speech) times the factor. Withdrawn root; Tk's own copy is stopped, so the clipboard is not used."""
import unittest
from types import SimpleNamespace
from tkinter import font as tkfont
import tkinter as tk

import app, emphasis_font


def size_at(widget, index):
    for tag in reversed(widget.tag_names(index)):
        spec = widget.tag_cget(tag, 'font')
        if spec:
            return tkfont.Font(root=widget, font=spec).actual()['size']
    return tkfont.Font(root=widget, font=widget.cget('font')).actual()['size']


class EmphasisTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()
        self.text = tk.Text(self.root, font=('Yu Gothic', 10)); self.text.pack()
        self.text.insert('1.0', '前の行です\n名詞と動詞の行\n後の行')
        self.text.tag_configure('pos_font_0', font=('Yu Gothic', 11))
        self.text.tag_add('pos_font_0', '2.0', '2.2')                # 名詞 is drawn at 11
        self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        self.a.root = self.root; self.a.editor = self.text
        self.a.result_view = tk.Text(self.root)

    def tearDown(self):
        self.root.update()
        self.root.destroy()

    def test_each_piece_keeps_its_own_size_times_the_factor(self):
        self.assertEqual(emphasis_font.apply(self.text, '2.0', '2.5', 1.2, 'emph_copy'), 2)
        self.assertEqual((size_at(self.text, '2.0'), size_at(self.text, '2.3'), size_at(self.text, '2.5')),
                         (13, 12, 10))
        emphasis_font.clear(self.text, 'emph_copy')
        self.assertEqual((size_at(self.text, '2.0'), size_at(self.text, '2.3')), (11, 10))

    def test_only_a_copy_without_a_whole_line_is_enlarged(self):
        partial = emphasis_font.partial_lines_only
        self.assertTrue(partial(self.text, '2.0', '2.2'))                 # part of a line
        self.assertTrue(partial(self.text, '1.2', '2.3'))                 # two parts, no whole line
        self.assertFalse(partial(self.text, '2.0', '2.end'))              # a whole line
        self.assertFalse(partial(self.text, '1.2', '3.1'))                # line 2 whole inside
        self.assertFalse(partial(self.text, '2.0', '3.0'))                # the line-number selection

    def test_copy_shows_the_range_until_a_new_copy_or_a_scroll(self):
        t = self.text
        self.assertTrue(self.a._show_copied(t, '2.3', '2.5'))
        self.assertEqual(size_at(t, '2.3'), 13)              # 1.3x (2026-10-23)
        self.assertFalse(self.a._show_copied(t, '1.0', '1.end'))         # whole line: none, old gone
        self.assertEqual(size_at(t, '2.3'), 10)
        self.a._show_copied(t, '2.3', '2.5')
        self.a._copy_emphasis = (t, '9.0')                               # the view has moved since
        self.a._copy_emphasis_scrolled(t)
        self.assertEqual(size_at(t, '2.3'), 10)
        self.a._show_copied(t, '2.3', '2.5')
        self.a.session = SimpleNamespace(tabs=[{}, {}], active=0)
        self.a._load_active_tab = lambda: None
        self.a._capture_session = self.a._schedule_session_save = self.a._forget_bracket_cycle = lambda: None
        self.a._switch_tab(1)                                            # another tab
        self.assertEqual(size_at(t, '2.3'), 10)

    def test_tk_copy_shows_the_range(self):
        t = self.text
        self.a._install_copied_range(t)
        self.root.tk.call('bind', 'StopCopy', '<<Copy>>', 'break')       # keep the clipboard untouched
        tags = t.bindtags(); t.bindtags((tags[0], 'StopCopy') + tags[1:])
        t.tag_add('sel', '1.0', '1.2')
        t.event_generate('<<Copy>>')
        self.assertEqual(size_at(t, '1.0'), 13)

    def test_search_hits_while_the_search_window_is_open(self):
        import search as searchlib
        t = self.text
        self.a._editor_text = lambda: t.get('1.0', 'end-1c')
        self.a._offset_to_index = lambda offset: t.index('1.0+%dc' % offset)
        spans = self.a._highlight_all(searchlib.build_pattern('の行', regex=False, match_case=False,
                                                              whole_word=False))
        self.assertEqual(len(spans), 3)
        self.assertEqual((size_at(t, '1.1'), size_at(t, '2.5'), size_at(t, '2.0')), (13, 13, 11))
        self.a._clear_find_marks()                                       # the window closed
        self.assertEqual((size_at(t, '1.1'), size_at(t, '2.5')), (10, 10))

    def test_a_white_frame_shrinks_into_place_around_the_copy(self):
        # 「コピー範囲の白い枠: 縮み始める大きさから本来の大きさへ縮む」（描き方は A＝細い線）。既定は
        # 2026-10-23 うにさんの値（218％・123ms・1px）
        import range_frame
        a = self.a
        self.assertEqual((a.COPY_FRAME_START_PERCENT, a.COPY_FRAME_MS, a.COPY_FRAME_WIDTH, a.QUOTE_TINT_PERCENT),
                         (218, 123, 1, 6))
        self.root.attributes('-alpha', 0); self.root.geometry('400x200+10000+10000'); self.root.deiconify()
        self.root.update()
        t = self.text
        a._show_copied(t, '2.3', '2.5')
        frame = a._copy_frame
        self.assertEqual(len(frame.lines), 4)                            # one display line: a plain box
        self.assertTrue(all(line.cget('bg') == '#ffffff' for line in frame.lines))
        start_width = frame.place_of()[0][2]
        self.settle()
        x0, y0, x1, y1 = range_frame.range_box(t, '2.3', '2.5')
        top = frame.place_of()[0]
        self.assertEqual(top[2], (x1 - x0) + 2 * 2 + 1)                  # the range, the margin, the line
        self.assertAlmostEqual(start_width, round((x1 - x0) * 2.18) + 2 * 2 + 1, delta=2)
        # Also for a whole line (the letters stay as they are there); gone on the next clearing
        self.assertFalse(a._show_copied(t, '1.0', '1.end'))
        self.assertEqual(len(frame.lines), 4)
        a._clear_copy_emphasis()
        self.assertEqual(frame.lines, [])

    def wrapped_text(self, **options):
        """A shown Text (off the screens) whose 2nd line wraps into 3 display lines, part of it larger."""
        self.root.attributes('-alpha', 0); self.root.geometry('320x320+10000+10000'); self.root.deiconify()
        self.text.pack_forget()                                   # only this one in the window
        settings = dict(font=('Yu Gothic', 10), wrap='char', width=24, height=12)
        settings.update(options)
        t = tk.Text(self.root, **settings)
        t.pack()
        t.insert('1.0', '前の行です\n' + '折り返す長い行の作り文です。' * 4 + '\n後の行')
        t.tag_configure('pos_font_big', font=('Yu Gothic', 16))
        t.tag_add('pos_font_big', '2.20', '2.24')                  # larger letters in the 2nd display line
        self.root.update()
        return t

    def settle(self, seconds=.5):
        import time
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.root.update(); time.sleep(.01)

    def screen_lines(self):
        """The frame's lines on the screen: [('h' or 'v', x0, y0, x1, y1)]."""
        out = []
        for line in self.a._copy_frame.lines:
            x, y, w, h = line.winfo_rootx(), line.winfo_rooty(), line.winfo_width(), line.winfo_height()
            out.append(('h' if w > h else 'v', x, y, x + w, y + h))
        return out

    def letters(self, t, start, end):
        """Screen boxes of the letters of [start, end) (newlines left out)."""
        out = []
        i = t.index(start)
        while t.compare(i, '<', end):
            b = t.bbox(i)
            if b is not None and t.get(i) != '\n':
                out.append((t.winfo_rootx() + b[0], t.winfo_rooty() + b[1],
                            t.winfo_rootx() + b[0] + b[2], t.winfo_rooty() + b[1] + b[3]))
            i = t.index(i + ' +1c')
        return out

    def check_outline(self, t, start, end):
        """Every letter is inside the outline (between a left and a right line at its own height, below the
        top and above the bottom), and no line is drawn over a letter."""
        lines = self.screen_lines()
        boxes = self.letters(t, start, end)
        self.assertTrue(boxes)
        top = min(l[2] for l in lines); bottom = max(l[4] for l in lines)
        for x0, y0, x1, y1 in boxes:
            self.assertTrue(top <= y0 and y1 <= bottom, (start, end, (x0, y0, x1, y1), top, bottom))
            mid = (y0 + y1) / 2.0
            sides = [l for l in lines if l[0] == 'v' and l[2] <= mid <= l[4]]
            self.assertTrue(any(l[1] <= x0 for l in sides) and any(l[3] >= x1 for l in sides),
                            (start, end, (x0, y0, x1, y1), sides))
            for l in lines:
                self.assertFalse(l[1] < x1 - 1 and x0 + 1 < l[3] and l[2] < y1 - 1 and y0 + 1 < l[4],
                                 (start, end, (x0, y0, x1, y1), l))
        return lines

    def test_the_frame_follows_a_wrapped_line_as_one_stepped_shape(self):
        # 2026-10-23 うにさん「折り返しの一部をコピー枠で包むと、行全体が囲まれる。…枠の始まりと終わりで分割し、
        # …中間の縦線が入らない形にする」: the 1st display line from the first letter, the last up to the last
        # letter, those between across; one outline, no line inside
        import range_frame
        t = self.wrapped_text(borderwidth=1, highlightthickness=0, padx=14, pady=12, spacing1=3, spacing3=3)
        self.assertGreaterEqual(t.count('2.0', '2.end', 'displaylines')[0], 3)
        second = t.index('2.0 +1 display lines display linestart')
        third = t.index(second + ' +1 display lines display linestart')
        cases = (('2.0', '2.end'),                                      # the whole wrapped line
                 ('2.5', t.index(second + ' +8c')),                     # overlapping steps
                 (t.index(second + ' -3c'), t.index(second + ' +2c')),  # two parts that do not overlap
                 ('2.5', t.index(third + ' +3c')),                      # first, middle across, last
                 ('2.3', '2.7'))                                         # one display line: a box
        for start, end in cases:
            self.a._show_copied(t, start, end)
            self.settle()
            lines = self.check_outline(t, start, end)
            if len(range_frame.range_rows(t, start, end)) == 1:
                self.assertEqual(len(lines), 4)
        # Two display lines whose parts overlap: 8 lines (top, bottom, 2 left, 2 right, 2 steps), and the step
        # lines between them leave out the shared part
        start, end = '2.5', t.index(second + ' +8c')
        self.a._show_copied(t, start, end); self.settle()
        lines = self.screen_lines()
        self.assertEqual(len(lines), 8, lines)
        rows = range_frame.range_rows(t, start, end)
        shared = (t.winfo_rootx() + rows[0][0] + 1, t.winfo_rootx() + rows[1][2] - 1)
        boundary = t.winfo_rooty() + rows[0][3]
        for kind, x0, y0, x1, y1 in lines:
            if kind == 'h' and abs(y0 - boundary) <= 3:
                self.assertFalse(x0 < shared[1] and shared[0] < x1, ((x0, x1), shared))

    def test_the_background_of_a_wrapped_line_stays_inside_the_frame(self):
        # 2026-10-23 うにさん「折り返し行を枠で包むと、折り返しのところの背景色が枠の外に出る」: Tk paints the
        # background of a display line the range goes on past up to the right edge of the text
        import range_frame
        t = self.wrapped_text(borderwidth=1, highlightthickness=0, padx=14, pady=12)
        right = t.winfo_rootx() + range_frame._text_right(t)
        self.a._show_copied(t, '2.0', '2.end')
        self.settle()
        lines = self.screen_lines()
        first = t.dlineinfo('2.0')
        mid = t.winfo_rooty() + first[1] + first[3] / 2.0
        sides = [l for l in lines if l[0] == 'v' and l[2] <= mid <= l[4]]
        self.assertGreaterEqual(max(l[1] for l in sides), right)           # the right line is past the edge

    def test_the_frame_follows_when_the_letters_change_size_after_the_copy(self):
        # The analysis gives the letters their part-of-speech sizes after the copy: the frame measures again
        t = self.wrapped_text()
        t.tag_remove('pos_font_big', '1.0', 'end')
        self.root.update()
        self.a._show_copied(t, '2.0', '2.end')
        frame = self.a._copy_frame
        self.settle(.35)
        before = max(l[4] for l in self.screen_lines())
        t.tag_add('pos_font_big', '2.0', '2.end')                 # retagged: taller, more display lines
        self.settle(.6)
        self.assertGreater(max(l[4] for l in self.screen_lines()), before)
        self.check_outline(t, '2.0', '2.end')
        self.a._clear_copy_emphasis()
        self.assertEqual(frame.lines, [])
        self.assertIsNone(frame.job)

    def test_the_frame_is_where_the_letters_are_on_the_screen(self):
        # 2026-10-23 うにさん「ずれています」: the frame was lower and right of the copy by the memo's padx/pady
        # (place counted from inside the Text's border). Compared on the screen: around the letters, a few px off
        t = self.wrapped_text(borderwidth=1, highlightthickness=0, padx=14, pady=12, spacing1=3, spacing3=3)
        t.tag_remove('pos_font_big', '1.0', 'end')
        self.root.update()
        for start, end in (('2.3', '2.7'), ('1.0', '1.end')):
            self.a._show_copied(t, start, end)
            self.settle()
            lines = self.check_outline(t, start, end)
            frame = (min(l[1] for l in lines), min(l[2] for l in lines), max(l[3] for l in lines), max(l[4] for l in lines))
            boxes = self.letters(t, start, end)
            letters = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
            self.assertTrue(all(abs(f - l) <= 10 for f, l in zip(frame, letters)), (start, frame, letters))

    def test_esc_clears_the_frame_and_the_letters_unless_converting(self):
        # 2026-10-23 うにさん「変換をしていない時にエスケープを押したら、白い枠は非表示にする。クリップボードは
        # そのまま」「エスケープを押して枠を解いたら、そのフォントサイズも元に戻す」
        t = self.wrapped_text()
        self.a._install_copied_range(t)
        self.a._show_copied(t, '2.3', '2.8')
        frame = self.a._copy_frame
        self.assertEqual(len(frame.lines), 4)
        self.assertEqual(size_at(t, '2.3'), 13)                    # 1.3x of 10
        self.a._composing = lambda widget: True                   # converting: Esc is the IME's, all stays
        t.focus_force(); t.event_generate('<Escape>'); self.root.update()
        self.assertEqual(len(frame.lines), 4)
        self.assertEqual(size_at(t, '2.3'), 13)
        self.a._composing = lambda widget: False
        t.event_generate('<Escape>'); self.root.update()
        self.assertEqual(frame.lines, [])
        self.assertEqual(size_at(t, '2.3'), 10)                    # the letters back too
        self.assertIsNone(self.a._copy_emphasis)
        self.a._on_copy_frame_escape(t._w)                         # nothing shown: nothing happens

    def test_factors_are_in_the_debug_menu(self):
        import debug_menu
        settings = SimpleNamespace(data={}, get=lambda k, d=None: settings.data.get(k, d),
                                   set=lambda k, v: settings.data.__setitem__(k, v), save=lambda: None)
        self.a.settings = settings
        self.assertEqual((debug_menu.default('copy_emphasis', self.a), debug_menu.default('find_emphasis', self.a)),
                         (130, 130))                     # 2026-10-23 うにさん: the copy +0.1 (1.2 → 1.3)
        debug_menu.set_value(self.a, 'copy_emphasis', 150, save=False)
        self.assertEqual(self.a.COPY_EMPHASIS_PERCENT, 150)
        self.a._show_copied(self.text, '2.3', '2.5')
        self.assertEqual(size_at(self.text, '2.3'), 15)
        debug_menu.apply(self.a, {})


if __name__ == '__main__':
    unittest.main()
