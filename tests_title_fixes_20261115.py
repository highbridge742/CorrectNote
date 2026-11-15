# -*- coding: utf-8 -*-
"""タイトルと目次の直し12件（2026-11-15 うにさんの指摘）。自分で作った Tk の窓の中だけで確かめる（本物のキー送り・
クリップボードは使わない）。作った例文。

ホイール・右ドラッグを本文へ渡す／F2・括弧はタイトルへ／ルーラーは何もしない／Undo を本文と1つの列に／1行目の番号／
目次の字の大きさ・区切りの線／タブの切り替えでその場で作り直す／重さ（余白・位置の掛け直し）／タイトルを上端へ／
再入力変換の Home・End。"""
import os
import time
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import title_toc as T


def _root():
    try:
        root = tk.Tk()
    except tk.TclError:
        raise unittest.SkipTest('no display')
    return root


class Fixture(unittest.TestCase):
    """左右の欄・本文の Text・偽の app（title_toc が使う所だけ）。"""
    def setUp(self):
        os.environ.pop('CN_TITLE_TOC', None)
        self.root = _root()
        self.root.geometry('900x500+40+40')
        body = tk.Frame(self.root)
        body.pack(fill='both', expand=True)
        body.grid_columnconfigure(0, weight=1, uniform='pane')
        body.grid_columnconfigure(1, weight=1, uniform='pane')
        body.grid_rowconfigure(0, weight=1)
        left, right = tk.Frame(body), tk.Frame(body)
        left.grid(row=0, column=0, sticky='nsew')
        right.grid(row=0, column=1, sticky='nsew')
        self.font = ('Yu Gothic UI', 12)
        self.editor = tk.Text(left, undo=True, wrap='word', font=self.font, padx=14, pady=12, width=1)
        self.result = tk.Text(right, wrap='word', font=self.font, padx=14, pady=12, width=1)
        self.editor.pack(fill='both', expand=True)
        self.result.pack(fill='both', expand=True)
        text = '\n'.join('%d行目の文です。' % i for i in range(1, 61))
        self.editor.insert('1.0', text)
        self.result.insert('1.0', text)
        self.bookmarks = {3, 10}
        self.drags = []
        self.app = NS(_body=body, editor=self.editor, result_view=self.result, _editor_wrap=left, _result_wrap=right,
                      bookmarks=self.bookmarks, settings={'dark_mode': False},
                      editor_source_text=lambda: self.editor.get('1.0', 'end-1c'),
                      _goto_line=lambda row: None, _layout_is_unified=lambda: False,
                      _editor_font=lambda: self.font, store=NS(_tokenize_fn=lambda line: []),
                      _show_copy_frame=mock.Mock(), _schedule_session_save=mock.Mock(),
                      _drag_press=lambda ev, w, always: self.drags.append(('press', ev.x, ev.y, w)),
                      _drag_motion=lambda ev, w: self.drags.append(('motion', ev.x, ev.y, w)),
                      _drag_release=lambda ev, w: self.drags.append(('release', ev.x, ev.y, w)))
        self.toc = T.TitleToc(self.app)
        self.root.update()
        self.toc.refresh_toc(force=True)
        self.root.update()
        self.addCleanup(self.root.destroy)


class Scroll(Fixture):
    def test_wheel_on_a_toc_link_scrolls_the_text(self):
        """1. 目次（リンクの字も）の上のホイールは本文を送る。"""
        link = self.toc.links[0]
        before = self.editor.yview()[0]
        link.event_generate('<MouseWheel>', delta=-120, x=5, y=5)
        self.root.update()
        self.assertGreater(self.editor.yview()[0], before)

    def test_wheel_on_the_title_scrolls_the_text(self):
        before = self.editor.yview()[0]
        self.toc.title.event_generate('<MouseWheel>', delta=-120, x=5, y=5)
        self.root.update()
        self.assertGreater(self.editor.yview()[0], before)

    def test_right_drag_on_the_title_and_toc_goes_to_the_text(self):
        """2. タイトル・目次・その余白の上の右ドラッグは、本文の右ドラッグ（座標は本文の欄の中）。"""
        for widget in (self.toc.title, self.toc.links[0], self.toc.frame):
            del self.drags[:]
            widget.event_generate('<ButtonPress-3>', x=20, y=5)
            widget.event_generate('<B3-Motion>', x=20, y=40)
            widget.event_generate('<ButtonRelease-3>', x=20, y=40)
            self.root.update()
            self.assertEqual([d[0] for d in self.drags], ['press', 'motion', 'release'], widget)
            self.assertTrue(all(d[3] is self.editor for d in self.drags))
            dy = widget.winfo_rooty() - self.editor.winfo_rooty()
            self.assertEqual(self.drags[0][2], 5 + dy)
            self.assertEqual(self.drags[1][2], 40 + dy)


class Look(Fixture):
    def test_toc_font_is_a_little_smaller_than_the_text(self):
        """7. 目次の字は本文の 0.85 倍＋1pt（9〜12・2026-11-15 うにさん「目次のフォントサイズを1増やす」で +1）。"""
        size = abs(int(self.toc._link_font.cget('size')))
        self.assertEqual(size, 11)
        self.font = ('Yu Gothic UI', 20)
        self.assertEqual(self.toc._toc_size(), 12)
        self.font = ('Yu Gothic UI', 6)
        self.assertEqual(self.toc._toc_size(), 9)

    def test_a_rule_under_the_toc_only_when_there_is_a_toc(self):
        """11. 目次の下に区切りの線（目次が無い時は無し）。色はテーマの線の色。"""
        self.root.update()
        self.assertTrue(self.toc.rule.winfo_ismapped())
        self.assertEqual(int(self.toc.rule.cget('height')), 1)
        self.bookmarks.clear()
        self.toc.refresh_toc()
        self.root.update()
        self.assertFalse(self.toc.rule.winfo_ismapped())
        self.assertFalse(self.toc.toc.winfo_ismapped())
        # 目次がまた出来たら、目次 → 線 の順に戻る（外していた線の前へ詰めて落ちていた）
        self.bookmarks.update({5})
        self.toc.refresh_toc()
        self.root.update()
        self.assertTrue(self.toc.rule.winfo_ismapped())
        self.assertGreater(self.toc.rule.winfo_y(), self.toc.toc.winfo_y())

    def test_title_sits_at_the_top_of_the_text(self):
        """12. タイトルは本文の欄の上端から 2px。1行目の字は欄の下。"""
        self.toc.layout(); self.root.update()
        gap = self.toc.clip.winfo_rooty() - self.editor.winfo_rooty()
        self.assertEqual(gap, T.TOP_GAP)
        info = self.editor.dlineinfo('1.0')
        text_top = self.editor.winfo_rooty() + info[1] + info[4] - int(
            self.editor.tk.call('font', 'metrics', self.editor.cget('font'), '-ascent'))
        self.assertGreaterEqual(text_top, self.toc.clip.winfo_rooty() + self.toc._height)


class Light(Fixture):
    def test_scrolling_does_not_set_the_pad_again(self):
        """10. スクロールでは余白の spacing を掛け直さず、同じ位置なら置き直さない。"""
        self.toc.layout(); self.root.update()
        with mock.patch.object(self.editor, 'tag_configure', wraps=self.editor.tag_configure) as conf, \
                mock.patch.object(self.toc.clip, 'place', wraps=self.toc.clip.place) as place:
            for _ in range(5):
                self.toc.ensure_pad()
                self.toc.position()
            self.assertEqual(conf.call_count, 0)
            self.assertEqual(place.call_count, 0)

    def test_typing_that_keeps_the_toc_does_not_measure_again(self):
        self.toc.layout(); self.root.update()
        with mock.patch.object(self.toc, 'layout') as layout:
            self.editor.insert('5.end', 'あ')
            self.toc._changed_now()
        layout.assert_not_called()

    def test_tab_switch_rebuilds_the_toc_at_once(self):
        """8. タブを替えたら、待たずに目次を作り直す（打鍵の待ちが残っていても）。"""
        self.toc.changed()            # 打鍵の待ちが残っている
        self.editor.delete('1.0', 'end')
        self.editor.insert('1.0', '一\n二\n三\n四')
        self.bookmarks.clear(); self.bookmarks.update({2, 4})
        self.toc.switched('別の題')
        self.assertEqual([l.cget('text') for l in self.toc.links], ['二', '四'])
        self.assertEqual(self.toc.get_title(), '別の題')
        self.assertIsNone(getattr(self.toc, '_after', None))


class Overlap(Fixture):
    """目次と本文が重なって見えた件（2026-11-15）: 高さはその場で測り、絵のあるテーマでは欄も透過の窓に。"""
    def test_measured_height_is_the_packed_height(self):
        for marks, title in (({3, 10}, ''), ({3, 10, 20, 30}, '長いタイトル'), (set(), '題')):
            self.bookmarks.clear(); self.bookmarks.update(marks)
            self.toc.set_title(title)
            self.toc.refresh_toc(force=True)
            self.root.update()
            self.assertEqual(self.toc._measure(), self.toc.frame.winfo_reqheight(), (marks, title))

    def test_tab_switch_sets_pad_and_frame_in_the_same_turn(self):
        self.toc.layout(); self.root.update()
        self.editor.delete('1.0', 'end')
        self.editor.insert('1.0', chr(10).join('行%d' % i for i in range(1, 40)))
        self.bookmarks.clear(); self.bookmarks.update({1, 5, 9, 13, 17})
        self.toc.switched('題')
        # 描き直しを待たずに、余白と欄の高さが今の目次に合っている
        self.assertEqual(self.toc._height, self.toc._measure())
        pad = int(float(self.editor.tag_cget(T.PAD_TAG, 'spacing1')))
        self.assertGreaterEqual(pad, self.toc._height - self.toc._shift())
        self.root.update()
        self.assertEqual(self.toc._height, self.toc.frame.winfo_reqheight())

    def _layered(self, widget):
        import ctypes
        return bool(ctypes.windll.user32.GetWindowLongPtrW(widget.winfo_id(), -20) & 0x00080000)

    def test_frame_is_a_child_of_the_text_and_stays_inside_it(self):
        """黒い帯・字が透けた件（2026-11-15）: 欄は本文の欄（Text）の子の窓で、本文の欄の内側だけに置く。"""
        self.assertIs(self.toc.clip.master, self.editor)
        self.toc.layout(); self.root.update()
        border = self.toc._border(self.editor)
        for step in (0, 15, 15, 30, 40, 60, -200):
            if step:
                self.editor.yview_scroll(step, 'pixels')
            self.toc.position(); self.root.update()
            if not self.toc.clip.winfo_ismapped():
                continue
            y, h = self.toc.clip.winfo_y(), self.toc.clip.winfo_height()
            self.assertGreaterEqual(y, border, step)
            self.assertLessEqual(y + h, self.editor.winfo_height() - border, step)
            self.assertLessEqual(self.toc.clip.winfo_x() + self.toc.clip.winfo_width(),
                                 self.editor.winfo_width() - border)

    def test_partly_scrolled_frame_moves_with_the_text(self):
        """画素で送ると、欄も同じだけ上へ（上へ見切れた分を切り取る）。"""
        self.toc.layout(); self.root.update()
        top0 = self.toc.clip.winfo_rooty() + self.toc.frame.winfo_y()     # 欄の中身の頭（画面の上の位置）
        self.editor.yview_scroll(20, 'pixels')
        self.toc.position(); self.root.update()
        top1 = self.toc.clip.winfo_rooty() + self.toc.frame.winfo_y()
        self.assertEqual(top1, top0 - 20)                                  # 本文と同じだけ上へ
        self.assertLess(self.toc.frame.winfo_y(), 0)                       # 上へ見切れた分は切り取る

    @unittest.skipUnless(os.name == 'nt', 'Windows only')
    def test_frame_is_not_a_layered_window_in_the_picture_theme(self):
        """絵のあるテーマ（本文の欄が透過の窓）でも、欄は透過の窓にしない（黒い地が出ない）。"""
        import paper_window as PW
        hwnd = self.editor.winfo_id()
        if not PW.show_through(hwnd, PW.colorref(self.editor.winfo_rgb(self.editor.cget('bg')))):
            self.skipTest('no layered child windows here')
        try:
            self.toc._placed = None
            self.toc.position(); self.root.update()
            self.assertTrue(self.toc.clip.winfo_ismapped())
            self.assertFalse(self._layered(self.toc.clip))
            self.assertIs(self.toc.clip.master, self.editor)
        finally:
            PW.stop_showing_through(hwnd)

    def test_scroll_cursor_hides_over_the_frame_too(self):
        """タイトル・目次から始めた右ドラッグでもカーソルを隠す（app._scroll_panes に欄の部品が入る）。"""
        import app
        a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.editor, a.result_view, a.root = self.editor, self.result, self.root
        a._title_toc = self.toc
        panes = a._scroll_panes()
        for w in (self.toc.title, self.toc.frame, self.toc.clip, self.toc.links[0]):
            self.assertIn(w, panes)


class PadPixels(Fixture):
    """タイトル・目次からの右ドラッグ（2026-11-15）: 1行目が見えている間は画素で送る（行で送ると欄の高さぶんが1回で消えた）。"""
    def make_app(self):
        import app
        a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.editor, a.result_view, a.root = self.editor, self.result, self.root
        a._title_toc = self.toc
        a._syncing = False
        a._overview = None
        a._release_navigation_padding = lambda: None
        a._layout_is_unified = lambda: True
        return a

    def test_drag_in_the_title_space_moves_by_pixels(self):
        a = self.make_app()
        self.toc.layout(); self.root.update()
        y0 = self.editor.dlineinfo('1.0')[1]
        self.assertTrue(a._title_pad_scroll(12))
        self.root.update()
        self.assertEqual(self.editor.dlineinfo('1.0')[1], y0 - 12)
        self.assertTrue(a._title_pad_scroll(-12))
        self.root.update()
        self.assertEqual(self.editor.dlineinfo('1.0')[1], y0)

    def test_moves_before_a_redraw_are_sent_at_once(self):
        """続けて来た動きは、描き直しの前（idle）に1回でまとめて送る（2026-11-15 うにさん「右クリックのスクロールが効きが
        悪い・全く動かないこともある」: 動き1つごとに送って描き直し、知らせが溜まっていた）。"""
        a = self.make_app()
        a.root = self.root
        self.toc.layout(); self.root.update()
        y0 = self.editor.dlineinfo('1.0')[1]
        with mock.patch.object(self.editor, 'yview_scroll', wraps=self.editor.yview_scroll) as scroll:
            for _ in range(5):
                self.assertTrue(a._title_pad_scroll(3))
            self.assertEqual(scroll.call_count, 0)          # まだ送らない
            self.root.update()
            self.assertEqual(scroll.call_count, 1)          # 1回で
            scroll.assert_called_with(15, 'pixels')
        self.assertEqual(self.editor.dlineinfo('1.0')[1], y0 - 15)

    def test_lines_below_go_by_lines_as_before(self):
        a = self.make_app()
        self.toc.layout(); self.root.update()
        self.editor.yview_scroll(5, 'units'); self.root.update()
        self.assertFalse(a._title_pad_scroll(12))
        with mock.patch.dict(os.environ, {'CN_TITLE_PAD_PIXELS': '0'}):
            self.editor.yview_moveto(0); self.root.update()
            self.assertFalse(a._title_pad_scroll(12))


class SplitMirror(Fixture):
    """分割の右の欄も1つの欄に（2026-11-15 最初の仕様「分割モードでも、左右繋がった欄として表示する」）: 右の Text の子の窓に
    写しを置き、左の欄の幅＋仕切りの分だけずらして、仕切りをまたいで続いた1枚に見せる。"""
    def settle(self):
        self.toc.layout(); self.root.update()
        self.toc.position(); self.root.update()

    def origins(self):
        """左の中身の頭と、右の写しの中身の頭（画面の x）。"""
        m = self.toc.mirror
        return (self.toc.frame.winfo_rootx(), m.frame.winfo_rootx())

    def test_the_right_pane_shows_the_continuation(self):
        self.settle()
        m = self.toc.mirror
        self.assertIsNotNone(m)
        self.assertIs(m.clip.master, self.result)
        self.assertTrue(m.clip.winfo_ismapped())
        left, right = self.origins()
        self.assertEqual(left, right)                      # 同じ所から続く1枚
        self.assertEqual(m.frame.winfo_width(), self.toc.frame.winfo_width())
        self.assertEqual(m.frame.winfo_rooty(), self.toc.frame.winfo_rooty())
        # 中身は左右を合わせた幅（左の欄より広い）
        self.assertGreater(self.toc.frame.winfo_width(), self.editor.winfo_width())

    def test_it_stays_continuous_when_the_split_moves(self):
        self.settle()
        self.root.geometry('700x500'); self.root.update()
        self.toc.position(); self.root.update()
        left, right = self.origins()
        self.assertEqual(left, right)

    def test_title_text_and_caret_are_copied(self):
        self.settle()
        self.toc.set_title('とても長いタイトルの字')
        self.toc.title.focus_force(); self.toc.title.mark_set('insert', '1.3')
        self.toc._mirror_call('sync_caret'); self.root.update()
        m = self.toc.mirror
        self.assertEqual(m.title.get('1.0', 'end-1c'), 'とても長いタイトルの字')
        self.assertTrue(m.caret.winfo_ismapped())
        self.assertEqual(m.caret.winfo_x(), m.title.bbox('1.3')[0])

    def test_click_on_the_copy_puts_the_cursor_in_the_real_title(self):
        self.settle()
        self.toc.set_title('左から右へ続くタイトル')
        self.root.update()
        m = self.toc.mirror
        box = m.title.bbox('1.4')
        m.title.event_generate('<Button-1>', x=box[0] + 1, y=box[1] + 2)
        self.root.update()
        # 焦点の移りは窓が前に出ている時だけ見える（試験の窓は前に出ないことがある）ので、カーソルの所だけ見る
        self.assertEqual(self.toc.title.index('insert'), '1.4')

    def test_toc_links_on_the_right_do_not_jump(self):
        """2026-11-15 うにさん「目次の補正欄側をクリックするとジャンプする。反応しないようにする」で仕様を変えた（前は右からも
        飛んだ）。右の写しの目次の行は字だけ見せ、クリックしても飛ばず、手のカーソルも出さない。左は今まで通り飛ぶ。"""
        jumps = []
        self.app._goto_line = lambda row: jumps.append(row)
        self.settle()
        m = self.toc.mirror
        self.assertEqual([l.cget('text') for l in m.links], [l.cget('text') for l in self.toc.links])
        m.links[1].event_generate('<Button-1>', x=2, y=2); self.root.update()
        self.assertEqual(jumps, [])
        self.assertNotEqual(m.links[1].cget('cursor'), 'hand2')
        self.toc.links[1].event_generate('<Button-1>', x=2, y=2); self.root.update()
        self.assertEqual(jumps, [10])

    def test_wheel_and_drag_from_the_right_go_to_the_text(self):
        self.settle()
        m = self.toc.mirror
        before = self.editor.yview()[0]
        m.links[0].event_generate('<MouseWheel>', delta=-120, x=2, y=2); self.root.update()
        self.assertGreater(self.editor.yview()[0], before)
        del self.drags[:]
        m.title.event_generate('<ButtonPress-3>', x=5, y=5)
        m.title.event_generate('<B3-Motion>', x=5, y=30)
        self.assertEqual([d[0] for d in self.drags], ['press', 'motion'])
        self.assertTrue(all(d[3] is self.editor for d in self.drags))

    def test_unified_layout_has_no_copy(self):
        self.app._layout_is_unified = lambda: True
        self.toc._placed = None
        self.settle()
        self.assertTrue(self.toc.mirror is None or not self.toc.mirror.clip.winfo_ismapped())

    def test_only_what_shows_on_the_right_is_covered(self):
        """右の欄に字が出ない（目次の行・タイトルが左の欄の中で終わる）時は、写しは下の線の所だけを覆う（大きい窓を補正欄の
        上で動かさない・2026-11-15 右ドラッグを軽く）。線は左とつながって見える。"""
        self.toc.set_title('短')
        self.settle()
        m = self.toc.mirror
        self.assertTrue(m.clip.winfo_ismapped())
        self.assertLessEqual(m.clip.winfo_height(), 2)
        self.assertEqual(m.rule.winfo_rooty(), self.toc.rule.winfo_rooty())       # 線は左と同じ高さ
        # 長い題なら、タイトルの所も覆う
        self.toc.set_title('長いタイトル' * 12)
        self.toc._placed = None; m._placed = None
        self.settle()
        self.assertGreater(m.clip.winfo_height(), 20)
        self.assertEqual(m.frame.winfo_rooty(), self.toc.frame.winfo_rooty())

    def test_the_copy_is_inside_the_right_text(self):
        self.settle()
        m = self.toc.mirror
        border = self.toc._border(self.result)
        self.assertGreaterEqual(m.clip.winfo_y(), border)
        self.assertLessEqual(m.clip.winfo_x() + m.clip.winfo_width(), self.result.winfo_width() - border)


class FastScroll(Fixture):
    """速いスクロールで黒い帯・空の瞬間・ずれた目次の行（2026-11-15）: 欄を置き直すたびに、その場で描き直しを積む。
    行番号の列の余白の所は地の色の板で覆う。画面は撮れないので、描き直しの積み方と板の位置を見る。"""
    def test_every_move_asks_for_a_redraw(self):
        self.toc.layout(); self.root.update()
        with mock.patch.object(self.toc, '_repaint', wraps=self.toc._repaint) as repaint:
            moves = 0
            for step in (5, 5, 5, 5, -20, 7, 7):
                self.editor.yview_scroll(step, 'pixels')
                before = self.toc._placed
                self.toc.position()
                if self.toc._placed is not None and self.toc._placed != before:
                    moves += 1
            self.assertGreater(moves, 0)
            self.assertEqual(repaint.call_count, moves)

    def test_redraw_keeps_the_colors(self):
        self.toc.layout(); self.root.update()
        before = [w.cget('bg') for w in (self.toc.clip, self.toc.frame, self.toc.title, self.toc.rule)]
        self.toc._repaint()
        self.assertEqual([w.cget('bg') for w in (self.toc.clip, self.toc.frame, self.toc.title, self.toc.rule)], before)

    def test_line_number_column_is_covered_beside_the_title(self):
        """行番号の列の、タイトルと目次の高さの所は、列の地の色で塗る（絵の点を透かさない）。2026-11-15 から列が自分の
        描き直しの中で塗る（前は列の上に板の窓を置いていたが、スクロールのたびに窓を動かして右ドラッグが重くなった）。"""
        import app
        gutter = app.LineNumberGutter(self.editor.master, self.editor, bg='#123456')
        gutter.pack(side='left', fill='y', before=self.editor)
        self.toc._placed = None
        self.toc.layout(); self.root.update()
        gutter.redraw(); self.root.update()
        covers = gutter.find_withtag('title_cover')
        self.assertEqual(len(covers), 1)
        self.assertEqual(gutter.itemcget(covers[0], 'fill'), '#123456')
        x0, y0, x1, y1 = gutter.coords(covers[0])
        info = self.editor.dlineinfo('1.0')
        ascent = int(self.editor.tk.call('font', 'metrics', self.editor.cget('font'), '-ascent'))
        self.assertEqual(y0, 0)
        self.assertEqual(y1, info[1] + info[4] - ascent)                 # 1行目の字の頭まで（番号は覆わない）
        self.assertFalse(getattr(self.toc, '_covers', None))              # 板の窓は作らない
        # 1行目が見えなくなったら塗らない
        self.editor.yview_scroll(10, 'units'); self.root.update()
        gutter.redraw(); self.root.update()
        self.assertEqual(gutter.find_withtag('title_cover'), ())


class TitleClick(Fixture):
    """タイトルの字より右の空いた所のクリックで、タイトルの末尾へ（2026-11-15 うにさん）。左の余白なら頭。"""
    def settle(self):
        self.toc.set_title('短い題')
        self.toc.layout(); self.root.update()
        self.toc.position(); self.root.update()
        self.toc.title.mark_set('insert', '1.1')

    def click(self, widget, x_root, y_root):
        widget.event_generate('<Button-1>', x=x_root - widget.winfo_rootx(), y=y_root - widget.winfo_rooty(),
                              rootx=x_root, rooty=y_root)
        self.root.update()

    def title_mid_y(self):
        return self.toc.title.winfo_rooty() + self.toc.title.winfo_height() // 2

    def test_right_of_the_title_text_goes_to_the_end(self):
        self.settle()
        t = self.toc.title
        self.click(t, t.winfo_rootx() + t.winfo_width() - 30, self.title_mid_y())
        self.assertEqual(t.index('insert'), t.index('end-1c'))

    def test_the_frame_beside_the_title_goes_to_the_end(self):
        """タイトルの Text の外（欄の箱）の、タイトルの行の高さの所。"""
        self.settle()
        t = self.toc.title
        got = self.toc.click_title_band(NS(x_root=t.winfo_rootx() + t.winfo_width() - 5,
                                           y_root=t.winfo_rooty() + t.winfo_height() + 2))
        self.assertEqual(got, 'break')
        self.assertEqual(t.index('insert'), t.index('end-1c'))
        self.assertTrue(self.toc._title_last)

    def test_left_margin_goes_to_the_head(self):
        self.settle()
        t = self.toc.title
        t.mark_set('insert', 'end-1c')
        got = self.toc.click_title_band(NS(x_root=t.winfo_rootx() + 2, y_root=self.title_mid_y()))
        self.assertEqual(got, 'break')
        self.assertEqual(t.index('insert'), '1.0')

    def test_the_right_pane_copy_goes_to_the_end(self):
        self.settle()
        m = self.toc.mirror
        self.click(m.title, m.title.winfo_rootx() + m.title.winfo_width() - 10, self.title_mid_y())
        self.assertEqual(self.toc.title.index('insert'), self.toc.title.index('end-1c'))

    def test_clicks_below_the_title_are_left_alone(self):
        """目次の行・その下のクリックはそのまま（目次のジャンプは今まで通り）。"""
        self.settle()
        link = self.toc.links[0]
        got = self.toc.click_title_band(NS(x_root=link.winfo_rootx() + 300, y_root=link.winfo_rooty() + 3))
        self.assertIsNone(got)
        self.assertEqual(self.toc.title.index('insert'), '1.1')


class Cursor(Fixture):
    def test_has_cursor_follows_the_last_focus(self):
        self.toc.title.focus_force(); self.root.update()
        self.assertTrue(self.toc.has_cursor())
        self.editor.focus_force(); self.root.update()
        self.assertFalse(self.toc.has_cursor())


class UndoTogether(unittest.TestCase):
    """5. 元に戻す・やり直しをタイトルと本文で1つの列に（本物の undo_feedback・tab_undo）。"""
    def setUp(self):
        os.environ.pop('CN_TITLE_TOC', None)
        self.root = _root()
        self.root.geometry('700x400+40+40')
        body = tk.Frame(self.root); body.pack(fill='both', expand=True)
        self.editor = tk.Text(body, undo=True, autoseparators=True, padx=14, pady=12, width=1)
        self.editor.pack(fill='both', expand=True)
        from undo_feedback import install
        feedback = install(self.editor, lambda: '#ffeecc')
        self.tab = {'text': ''}
        self.app = NS(_body=body, editor=self.editor, result_view=None, _editor_wrap=body, bookmarks=set(),
                      settings={}, editor_source_text=lambda: self.editor.get('1.0', 'end-1c'),
                      _goto_line=lambda r: None, _layout_is_unified=lambda: True, _editor_font=lambda: ('Yu Gothic UI', 12),
                      store=NS(_tokenize_fn=lambda line: []), _schedule_session_save=mock.Mock(),
                      session=NS(tabs=[self.tab]), root=self.root, _closing=False)
        from tab_undo import TabUndo
        self.app._tab_undo = TabUndo(self.app, feedback)
        self.app._tab_undo.owner = self.tab
        self.toc = T.TitleToc(self.app)
        self.root.update()
        self.addCleanup(self.root.destroy)

    def body(self, text):
        self.editor.edit_separator()
        self.editor.insert('end-1c', text)
        self.editor.edit_separator()
        self.root.update()

    def title(self, text):
        self.toc.title.insert('end-1c', text)
        self.root.update()
        self.toc.undo.history[-1]['t'] -= 10      # 次の打鍵とまとめない

    def state(self):
        return self.editor.get('1.0', 'end-1c'), self.toc.get_title()

    def test_steps_go_back_in_the_order_they_were_made(self):
        self.body('本文1')
        self.title('題')
        self.body('本文2')
        self.title('名')
        self.assertEqual(self.state(), ('本文1本文2', '題名'))
        steps = []
        for _ in range(4):
            self.editor.edit_undo(); self.root.update()
            steps.append(self.state())
        self.assertEqual(steps, [('本文1本文2', '題'), ('本文1', '題'), ('本文1', ''), ('', '')])
        for _ in range(4):
            self.editor.edit_redo(); self.root.update()
        self.assertEqual(self.state(), ('本文1本文2', '題名'))

    def test_ctrl_z_in_the_title_takes_the_body_step_too(self):
        self.title('題')
        self.body('本文')
        self.toc.title.focus_force(); self.root.update()
        self.toc.title.event_generate('<<Undo>>'); self.root.update()
        self.assertEqual(self.state(), ('', '題'))
        self.assertIs(self.root.focus_get(), self.editor)     # 戻した所（本文）へ
        self.toc.title.event_generate('<<Undo>>'); self.root.update()
        self.assertEqual(self.state(), ('', ''))

    def test_title_undo_moves_the_cursor_to_the_title(self):
        self.body('本文')
        self.title('題')
        self.editor.focus_force(); self.root.update()
        self.editor.edit_undo(); self.root.update()
        self.assertEqual(self.state(), ('本文', ''))
        self.assertIs(self.root.focus_get(), self.toc.title)

    def test_typing_runs_are_one_step(self):
        self.toc.title.insert('end-1c', 'あ'); self.root.update()
        self.toc.title.insert('end-1c', 'い'); self.root.update()
        self.assertEqual(len(self.toc.undo.history), 1)
        self.editor.edit_undo(); self.root.update()
        self.assertEqual(self.toc.get_title(), '')

    def test_loading_a_title_is_not_a_step(self):
        self.toc.set_title('読んだ題')
        self.assertEqual(self.toc.undo.history, [])


class Gutter(unittest.TestCase):
    """6. 1行目の番号は、上の余白ではなく1行目の字の高さに。"""
    def test_number_of_row_one_is_drawn_beside_its_text(self):
        import app
        root = _root()
        self.addCleanup(root.destroy)
        root.geometry('500x300+40+40')
        frame = tk.Frame(root); frame.pack(fill='both', expand=True)
        text = tk.Text(frame, font=('Yu Gothic UI', 12), padx=14, pady=12)
        gutter = app.LineNumberGutter(frame, text)
        gutter.pack(side='left', fill='y'); text.pack(side='left', fill='both', expand=True)
        text.insert('1.0', '一行目\n二行目')
        text.tag_configure(T.PAD_TAG, spacing1=120)
        text.tag_add(T.PAD_TAG, '1.0', '1.0+1c')
        root.update()
        gutter.redraw(); root.update()
        ys = [gutter.coords(i)[1] for i in gutter.find_withtag('num') if gutter.itemcget(i, 'text') == '1']
        self.assertEqual(len(ys), 1)
        info = text.dlineinfo('1.0')
        self.assertGreater(ys[0], info[1] + 120)          # 余白の下（字の高さ）
        self.assertLess(ys[0], info[1] + info[3])


class Brackets(unittest.TestCase):
    """3. タイトルにカーソルがある時の F2・括弧はタイトルの字に。4. ルーラーは何もしない。"""
    def setUp(self):
        import app
        self.root = _root(); self.root.withdraw()
        self.editor = tk.Text(self.root, undo=True); self.editor.pack()
        self.title = tk.Text(self.root, undo=False); self.title.pack()
        self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        self.a.root = self.root; self.a.editor = self.editor
        self.tab = {}; self.a.session = NS(current=lambda: self.tab)
        self.a._work_epoch = 0; self.a._f2_focus_target = None
        self.a._on_change = lambda *args: None
        self.a._close_dropdown = lambda: None; self.a._clear_f2_target = lambda: None
        self.cursor_in_title = True
        self.a._title_toc = NS(has_cursor=lambda: self.cursor_in_title, title=self.title)
        self.editor.insert('1.0', '本文'); self.editor.mark_set('insert', '1.1')
        self.title.insert('1.0', '題名'); self.title.mark_set('insert', '1.1')
        self.errors = []
        self.root.report_callback_exception = lambda *exc: self.errors.append(exc)

    def tearDown(self):
        self.root.update()
        for job in self.root.tk.call('after', 'info'):
            self.root.after_cancel(job)
        self.root.destroy()
        self.assertFalse(self.errors)

    def test_f2_in_the_title_wraps_the_title(self):
        import ime_watch
        with mock.patch.object(ime_watch, 'composition_active', return_value=False):
            self.a._on_f5_brackets(NS(widget=self.title, keysym='F2', char='', state=0))
        self.assertEqual(self.title.get('1.0', 'end-1c'), '題（）名')
        self.assertEqual(self.editor.get('1.0', 'end-1c'), '本文')

    def test_the_bracket_menu_goes_to_the_title(self):
        import ime_watch
        self.title.tag_add('sel', '1.0', '1.2')
        with mock.patch.object(ime_watch, 'composition_active', return_value=False):
            self.a._cycle_brackets()
        self.assertEqual(self.title.get('1.0', 'end-1c'), '（題名）')
        self.assertEqual(self.editor.get('1.0', 'end-1c'), '本文')

    def test_the_body_still_gets_brackets_when_the_cursor_is_there(self):
        import ime_watch
        self.cursor_in_title = False
        with mock.patch.object(ime_watch, 'composition_active', return_value=False):
            self.a._cycle_brackets()
        self.assertEqual(self.editor.get('1.0', 'end-1c'), '本（）文')
        self.assertEqual(self.title.get('1.0', 'end-1c'), '題名')

    def test_ruler_does_nothing_from_the_title(self):
        self.a._install_editor_guides = mock.Mock()
        self.a._sync_ruler_button = mock.Mock()
        self.assertFalse(self.a._toggle_ruler())
        self.a._install_editor_guides.assert_not_called()


class ReinputHomeEnd(unittest.TestCase):
    """9. 再入力変換の範囲を開いている間の Home・End は範囲の先頭・末尾へ。Shift なら範囲の中で選ぶ。"""
    def setUp(self):
        import reinput as R
        self.R = R
        self.root = _root(); self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.w = tk.Text(self.root); self.w.pack()
        self.w.insert('1.0', '前の字ひらがな後の字')
        app = NS(_composing=lambda w: False, _cursor_hider=None, session=NS(current=lambda: None))
        self.r = R.ReInput(app, self.w)
        self.w.mark_set(R.START, '1.3'); self.w.mark_gravity(R.START, 'left')
        self.w.mark_set(R.END, '1.7'); self.w.mark_gravity(R.END, 'right')
        self.r.state = dict(original='ひらがな', shown='ひらがな')
        self.w.mark_set('insert', '1.5')

    def key(self, keysym, state=0):
        return self.r.on_press(NS(keysym=keysym, state=state, keycode=36, char=''))

    def test_home_and_end_stay_in_the_range(self):
        self.assertEqual(self.key('Home'), 'break')
        self.assertEqual(self.w.index('insert'), '1.3')
        self.assertEqual(self.key('End'), 'break')
        self.assertEqual(self.w.index('insert'), '1.7')

    def test_shift_selects_inside_the_range(self):
        self.key('End', state=1)
        self.assertEqual((self.w.index('sel.first'), self.w.index('sel.last')), ('1.5', '1.7'))
        self.key('Home', state=1)
        self.assertEqual((self.w.index('sel.first'), self.w.index('sel.last')), ('1.3', '1.5'))

    def test_ctrl_home_and_no_range_are_as_before(self):
        self.assertIsNone(self.key('Home', state=4))
        self.r.state = None
        self.assertIsNone(self.key('Home'))

    def test_switch_off_keeps_the_old_way(self):
        with mock.patch.dict(os.environ, {'CN_REINPUT_HOME_END': '0'}):
            self.assertIsNone(self.key('Home'))


if __name__ == '__main__':
    unittest.main()
