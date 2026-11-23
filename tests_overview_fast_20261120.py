# -*- coding: utf-8 -*-
"""俯瞰の速い形・試作（overview_fast・2026-11-20 うにさん「作りを変えて試す」）。本文の欄の字は変えずに、小さい字の
分身（peer）を重ねて見せ、離したら分身を隠して本文の欄をその上端の行へ置く。自分の Tk の窓だけ・作った例文。"""
import os
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import overview_fast as O
import title_inline as TI


class FakeApp:
    def __init__(self, root, editor):
        self.root = root
        self.editor = editor
        self.result_view = None
        self.settings = {'overview_fast': True}
        self._overview = None
        self.hidden = 0

    def _layout_is_unified(self):
        return True

    def _editor_font(self):
        return ('Meiryo', 12)

    def _scroll_cursor_hide(self, w):
        self.hidden += 1

    def _scroll_cursor_restore(self):
        self.hidden -= 1


class FastOverviewTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        __import__('offscreen_window').hold(self.root, '600x400')          # 画面の外（うにさんの画面を占めない・どの画面の置き方でも）
        self.frame = tk.Frame(self.root)
        self.frame.pack(fill='both', expand=True)
        self.w = tk.Text(self.frame, font=('Meiryo', 12), wrap='word')
        self.w.pack(fill='both', expand=True)
        TI.prepare(self.w)
        TI.style(self.w, 'Meiryo', 10, '#1f5fbf', '#888888')
        TI.write(self.w, '試しの題', [])
        self.w.insert('1.0', '\n'.join('%d行目の本文です。' % i for i in range(1, 400)))
        self.root.update()
        self.w.yview('100.0')
        self.root.update()
        self.app = FakeApp(self.root, self.w)
        self.ov = O.install(self.app)

    def tearDown(self):
        self.root.destroy()

    def ev(self, y):
        return NS(x=100, y=y, x_root=self.w.winfo_rootx() + 100, y_root=self.w.winfo_rooty() + y, widget=self.w, state=0)

    # 2026-11-20: Tk 8.6.9 では、同じ本文の分身が1つでも disabled だと本文の Undo が効かない。起動の4秒後に前もって
    # 作る分身（prepare）を disabled で作っていたので、それからは本文の Ctrl+Z が効かなかった
    # （tests_gui_shortcuts_menu の「括弧の巡回の後の Undo」で見つかった）
    def undo_works(self):
        self.w.configure(undo=True, autoseparators=True)
        self.w.edit_reset()
        self.w.insert('end', 'あ')
        self.w.edit_separator()
        self.w.insert('end', 'い')
        self.w.edit_undo()
        return self.w.get('end-2c', 'end-1c') == 'あ'

    def test_prepared_peer_keeps_the_body_undo(self):
        self.ov.prepare()
        self.assertTrue(self.ov.peers)
        self.assertTrue(self.undo_works())
        self.ov.enter(self.ev(100), self.w)                                # 俯瞰の間は分身に打てない
        name = self.ov.peers[self.w._w]
        self.assertEqual(str(self.w.tk.call(name, 'cget', '-state')), 'disabled')
        self.ov.exit()
        self.assertEqual(str(self.w.tk.call(name, 'cget', '-state')), 'normal')
        self.assertTrue(self.undo_works())                                  # 出た後も Undo が効く

    def undo_seen_by_the_pane(self):
        """Undo の字の戻しが本文の欄の命令を通ったか（欄の命令の実行に trace を掛けて数える）。"""
        seen = []
        cmd = self.w.register(lambda *a: seen.append(a[0] if a else ''))
        self.w.tk.call('trace', 'add', 'execution', self.w._w, 'enter', cmd)
        try:
            ok = self.undo_works()
        finally:
            self.w.tk.call('trace', 'remove', 'execution', self.w._w, 'enter', cmd)
        return ok, any(' delete ' in ' %s ' % s for s in seen)

    def test_undo_goes_through_the_pane_command(self):
        # Tk は Undo の一手をいちばん新しい分身の名前で呼び返す。分身の名前は欄の命令へ回す（_route_undo）
        self.ov.prepare()
        ok, through = self.undo_seen_by_the_pane()
        self.assertTrue(ok)
        self.assertTrue(through)                                            # 観察者（undo_feedback など）が見る
        name = self.ov.peers[self.w._w]
        self.assertTrue(int(self.w.tk.call('winfo', 'exists', name)))
        self.w.tk.call(name, 'yview', '1.0')                                # 分身の自分の命令は本物へ

    def test_route_switch_off_bypasses_the_pane(self):
        with mock.patch.dict(os.environ, {'CN_OVERVIEW_PEER_ROUTE': '0'}):
            self.ov.prepare()
            ok, through = self.undo_seen_by_the_pane()
        self.assertTrue(ok)
        self.assertFalse(through)                                           # 前の形: 欄の命令を素通り（原因の再現）

    def test_old_disabled_peer_stops_the_undo(self):
        with mock.patch.dict(os.environ, {'CN_OVERVIEW_PEER_NORMAL': '0', 'CN_OVERVIEW_PEER_ROUTE': '0'}):
            self.ov.prepare()
            self.assertFalse(self.undo_works())                             # 前の形（不具合の再現）

    def test_enter_shows_a_small_peer_without_changing_the_pane(self):
        before = str(self.w.cget('font'))
        self.ov.enter(self.ev(200), self.w)
        self.root.update()
        name = self.ov._left()
        self.assertTrue(int(self.root.tk.call('winfo', 'ismapped', name)))
        self.assertEqual(str(self.w.cget('font')), before)                   # 本文の欄の字は変えない
        self.assertIn('5', str(self.root.tk.call(name, 'cget', '-font')))
        self.assertEqual(self.app._overview.get('fast'), True)
        self.assertTrue(self.root.tk.call(self.w._cn_body_raw, 'tag', 'ranges', 'ov_dest'))   # 移る範囲の枠

    def test_drag_and_release_moves_the_pane_to_the_peer_top(self):
        self.ov.enter(self.ev(200), self.w)
        self.root.update()
        top0 = self.ov._top_raw()
        self.ov.motion(self.ev(80))                                          # 上へ掴んで動かす: 先の行へ
        self.root.update()
        top1 = self.ov._top_raw()
        self.assertGreater(top1, top0)
        self.ov.exit()
        self.root.update()
        name = self.w._w + O.SUFFIX
        self.assertFalse(int(self.root.tk.call('winfo', 'ismapped', name)))   # 分身を隠す
        self.assertIsNone(self.app._overview)
        self.assertEqual(int(self.w.index('@0,0').split('.')[0]), top1 - TI.head_rows(self.w))
        self.assertFalse(self.root.tk.call(self.w._cn_body_raw, 'tag', 'ranges', 'ov_dest'))
        self.assertEqual(self.app.hidden, 0)

    def test_peer_is_kept_and_follows_edits(self):
        self.ov.prepare()
        name = self.w._w + O.SUFFIX
        self.w.insert('1.0', '追加')
        self.assertEqual(str(self.root.tk.call(name, 'get', '%d.0' % (TI.head_rows(self.w) + 1),
                                               '%d.2' % (TI.head_rows(self.w) + 1))), '追加')
        self.ov.enter(self.ev(200), self.w)
        self.assertEqual(self.ov._left(), name)                             # 作り直さない
        self.ov.exit()

    def test_background_canvas_is_raised_and_lowered_back(self):
        cv = tk.Canvas(self.frame)
        cv._correctnote_paper_pane = self.w
        cv.place(in_=self.w, x=0, y=0, relwidth=1, relheight=1)
        self.root.tk.call('lower', cv._w, self.w._w)
        order = lambda: [str(c) for c in self.root.tk.splitlist(self.root.tk.call('winfo', 'children', self.frame._w))]
        self.ov.enter(self.ev(200), self.w)
        kids = order()
        self.assertGreater(kids.index(cv._w), kids.index(self.w._w))       # 絵を欄より前へ（欄の字が透けない）
        self.ov.exit()
        kids = order()
        self.assertLess(kids.index(cv._w), kids.index(self.w._w))          # 出たら欄の後ろへ戻す

    # 2026-11-20 うにさん「縮小時に、ブックマークがある行は、一回り大きく」「本文の行頭位置が左右に揺れるので、揺れないように」
    def test_bookmarked_rows_are_one_size_larger_while_shown(self):
        self.app.bookmarks = {105, 110}
        self.ov.enter(self.ev(200), self.w)
        got = self.w.tag_ranges(O.BOOKMARK_TAG)
        self.assertEqual([str(x) for x in got], ['105.0', '106.0', '110.0', '111.0'])
        self.assertIn(str(O.BOOKMARK_SIZE), str(self.w.tag_cget(O.BOOKMARK_TAG, 'font')))
        self.ov.exit()
        self.assertFalse(self.w.tag_ranges(O.BOOKMARK_TAG))
        with mock.patch.dict(os.environ, {'CN_OVERVIEW_BOOKMARK': '0'}):
            self.ov.enter(self.ev(200), self.w)
            self.assertFalse(self.w.tag_ranges(O.BOOKMARK_TAG))
            self.ov.exit()

    def text_x(self, path, window):
        """欄の上端の行の、本文の1字目の画面の x。"""
        tkapp = self.root.tk
        index = str(tkapp.call(path, 'index', '@0,0 linestart'))
        box = tkapp.call(path, 'bbox', index)
        return int(tkapp.call('winfo', 'rootx', window)) + int(tkapp.splitlist(box)[0])

    def test_text_start_does_not_move_sideways(self):
        before = self.text_x(self.w._cn_body_raw, self.w._w)
        self.ov.enter(self.ev(200), self.w)
        self.root.update()
        during = self.text_x(self.ov._left(), self.ov._left())
        self.ov.exit()
        self.root.update()
        after = self.text_x(self.w._cn_body_raw, self.w._w)
        self.assertEqual((before, during, after), (before, before, before))

    # 2026-11-20 うにさん「左と右を同時にダブルクリックしたら、右クリックを離しているのに縮小のままになった」:
    # 右の離しの知らせが、左の押しの掴み（分身など）へ行って届かない順を作り、ボタンの実際の状態で出ることを見る
    def wire_exit(self):
        def exit_():
            if O.active(self.app) is not None:
                self.ov.exit()
        self.app._overview_exit = exit_

    def test_right_released_without_the_event_still_exits(self):
        self.wire_exit()
        state = {'down': True}
        with mock.patch.object(O, 'right_button_down', lambda app=None: state['down']):
            self.ov.enter(self.ev(200), self.w)                # 右を押したまま入る（見張りが立つ）
            self.root.after(20, lambda: state.update(down=False))   # 左を押した掴みの間に右を離す（知らせは来ない）
            end = self.root.tk.call('clock', 'milliseconds') + 600
            while self.app._overview is not None and self.root.tk.call('clock', 'milliseconds') < end:
                self.root.update()
        self.assertIsNone(self.app._overview)
        self.assertIsNone(O.active(self.app))

    def test_still_held_stays(self):
        self.wire_exit()
        with mock.patch.object(O, 'right_button_down', lambda app=None: True):
            self.ov.enter(self.ev(200), self.w)
            end = self.root.tk.call('clock', 'milliseconds') + 300
            while self.root.tk.call('clock', 'milliseconds') < end:
                self.root.update()
            self.assertIsNotNone(O.active(self.app))           # 押している間は出ない
            self.ov.exit()

    def test_old_overview_waits_for_the_minimum_show(self):
        import time
        calls = []
        app = NS(_overview={'shown_at': time.monotonic()}, OVERVIEW_MIN_SHOW_S=0.25, root=self.root,
                 _overview_exit=lambda: (calls.append(time.monotonic()), setattr(app, '_overview', None)))
        start = time.monotonic()
        O.watch_right_button(app, down=lambda a: False)
        end = self.root.tk.call('clock', 'milliseconds') + 800
        while app._overview is not None and self.root.tk.call('clock', 'milliseconds') < end:
            self.root.update()
        self.assertTrue(calls)
        self.assertGreaterEqual(calls[0] - start, 0.2)              # 今の形の最短の時間は待つ

    def test_watch_switch(self):
        app = NS(_overview={'fast': True}, root=self.root)
        with mock.patch.dict(os.environ, {'CN_OVERVIEW_BUTTON_WATCH': '0'}):
            O.watch_right_button(app, down=lambda a: False)
        self.assertIsNone(getattr(app, '_ov_button_job', None))

    # 2026-11-20 16:28Z うにさん「縮小モードの範囲が白いです。範囲にしては縦に長いな」（ダーク・分割表示）。
    # (1) 枠の色を `import app`（py app.py では2つ目の写し＝最初のライトの配色）から読んでいた → 動いているアプリの
    #     モジュールから読む（app_module_of・CN_OVERVIEW_FAST_THEME=0 で前の形）
    # (2) 左右の行をそろえる隙間（paired_row_pad_）は分身と共有で、ふだんの字の隙間が小さい字に付いて縦に長かった
    #     → 俯瞰の間だけ 0、出たら戻す（squash_padding・CN_OVERVIEW_FAST_PAD=0 で前の形）
    def dark_app(self):
        import sys
        import types
        mod = types.ModuleType('cn_fake_running_app')
        mod.OVERVIEW_DEST_TAG = 'ov_dest'
        mod.OVERVIEW_DEST_BORDER = 1
        mod.OVERVIEW_FONT_SIZE = 5
        mod.HOVER_BG = '#3c464c'                     # ダークの HOVER_BG（app.DARK_PALETTE）
        sys.modules[mod.__name__] = mod
        self.addCleanup(sys.modules.pop, mod.__name__, None)
        cls = type('RunningApp', (FakeApp,), {'__module__': mod.__name__})
        app = cls(self.root, self.w)
        return app, O.install(app)

    def test_mark_takes_the_running_theme(self):
        app, ov = self.dark_app()
        ov.enter(self.ev(200), self.w)
        self.assertEqual(str(self.w.tag_cget('ov_dest', 'background')), '#3c464c')
        ov.exit()
        with mock.patch.dict(os.environ, {'CN_OVERVIEW_FAST_THEME': '0'}):
            import app as second_copy
            ov.enter(self.ev(200), self.w)
            self.assertEqual(str(self.w.tag_cget('ov_dest', 'background')), second_copy.HOVER_BG)   # 前の形（白い枠）
            ov.exit()
        self.assertEqual(O.app_module_of(app).HOVER_BG, '#3c464c')

    def pad_rows(self):
        self.w.tag_configure('paired_row_pad_30', spacing3=int(self.w.cget('spacing3')) + 30)
        self.w.tag_add('paired_row_pad_30', '90.0', '140.0')

    def mark_pixels(self, ov):
        name = ov._left()
        first, last = [str(x) for x in self.root.tk.splitlist(
            self.root.tk.call(self.w._cn_body_raw, 'tag', 'ranges', 'ov_dest'))[:2]]
        got = self.root.tk.call(name, 'count', '-update', '-ypixels', first, last)
        return int(got)

    def test_row_gaps_are_squashed_while_shown(self):
        app, ov = self.dark_app()
        self.pad_rows()
        ov.enter(self.ev(200), self.w)
        self.root.update()
        self.assertEqual(int(self.w.tag_cget('paired_row_pad_30', 'spacing3')), 0)
        squashed = self.mark_pixels(ov)
        ov.exit()
        self.assertEqual(int(self.w.tag_cget('paired_row_pad_30', 'spacing3')), int(self.w.cget('spacing3')) + 30)
        with mock.patch.dict(os.environ, {'CN_OVERVIEW_FAST_PAD': '0'}):
            ov.enter(self.ev(200), self.w)
            self.root.update()
            self.assertEqual(int(self.w.tag_cget('paired_row_pad_30', 'spacing3')), int(self.w.cget('spacing3')) + 30)
            padded = self.mark_pixels(ov)                                    # 前の形（縦に長い）
            ov.exit()
        self.assertLess(squashed * 2, padded)

    # (3) 品詞の字の大きさ（pos_font_*）などタグの字は分身と共有で、ふだんの大きさのままだった（本物のアプリの写しで
    #     行が 26px・枠が見えている 569px のうち 472px）→ 俯瞰の間だけ俯瞰の字との比で小さく、出たら戻す
    #     （shrink_tag_fonts・CN_OVERVIEW_FAST_TAGFONT=0 で前の形）。ブックマークの行の字は除く
    def tagged_raw_row(self, peer):
        first = str(self.root.tk.splitlist(self.root.tk.call(peer, 'tag', 'ranges', 'pos_font_2'))[2])   # 分身は生の行番号
        return first.split('.')[0] + '.0'

    def test_tag_fonts_shrink_while_shown(self):
        app, ov = self.dark_app()
        self.w.tag_configure('pos_font_2', font=('Meiryo', 14))
        self.w.tag_add('pos_font_2', '95.0', '95.3', '100.0', '100.3', '105.0', '105.3', '110.0', '110.3')
        app.bookmarks = {120}
        before = str(self.w.tag_cget('pos_font_2', 'font'))
        ov.enter(self.ev(200), self.w)
        self.root.update()
        self.assertIn('6', str(self.w.tag_cget('pos_font_2', 'font')))           # 14 × 5 / 12 → 6
        self.assertIn(str(O.BOOKMARK_SIZE), str(self.w.tag_cget(O.BOOKMARK_TAG, 'font')))   # ブックマークはそのまま
        name = ov._left()
        row = self.tagged_raw_row(name)
        small = int(self.root.tk.call(name, 'count', '-update', '-ypixels', row, row + ' +1 lines'))
        ov.exit()
        self.assertEqual(str(self.w.tag_cget('pos_font_2', 'font')), before)
        with mock.patch.dict(os.environ, {'CN_OVERVIEW_FAST_TAGFONT': '0'}):
            ov.enter(self.ev(200), self.w)
            self.root.update()
            self.assertEqual(str(self.w.tag_cget('pos_font_2', 'font')), before)
            big = int(self.root.tk.call(name, 'count', '-update', '-ypixels', row, row + ' +1 lines'))   # 前の形
            ov.exit()
        self.assertLess(small * 2, big)

    def test_tag_font_changed_while_shown_is_kept(self):
        app, ov = self.dark_app()
        self.w.tag_configure('pos_font_2', font=('Meiryo', 14))
        ov.enter(self.ev(200), self.w)
        self.w.tag_configure('pos_font_2', font=('Meiryo', 16))                  # 俯瞰の間に付け直された字
        ov.exit()
        self.assertIn('16', str(self.w.tag_cget('pos_font_2', 'font')))

    def test_align_skipped_in_overview_runs_after_exit(self):
        app, ov = self.dark_app()
        calls = []
        app._align_pane_rows = lambda: calls.append(1)
        ov.enter(self.ev(200), self.w)
        app._align_skipped_in_overview = True                               # 俯瞰の間に止めた（app._align_pane_rows）
        ov.exit()
        self.root.update()
        self.assertEqual(calls, [1])
        self.assertFalse(app._align_skipped_in_overview)

    def test_app_does_not_realign_while_fast_overview_is_shown(self):
        import app as A
        import text_layout
        fake = NS(result_view=self.w, editor=self.w, _syncing=False, _ov_right_font=None, _overview={'fast': True},
                  _layout_is_unified=lambda: False, _pane_row_partners=lambda: None)
        with mock.patch.object(text_layout, 'align_rows', side_effect=AssertionError('aligned during the overview')):
            A.CorrectNoteApp._align_pane_rows(fake)
        self.assertTrue(fake._align_skipped_in_overview)
        calls = []
        with mock.patch.dict(os.environ, {'CN_OVERVIEW_FAST_PAD': '0'}),                 mock.patch.object(text_layout, 'align_rows', lambda *a, **k: calls.append(1) or False):
            A.CorrectNoteApp._align_pane_rows(fake)                       # 前の形: そろえ直す
        self.assertEqual(calls, [1])

    # 2026-11-21 05:01Z うにさん「縮小モードのスクロールは、途中から下へ進まなくなる」「タイトルと目次のフォントサイズは
    # 元のままにする」「ブックマーク行のフォントサイズをより大きくする」
    def test_head_fonts_are_kept(self):
        app, ov = self.dark_app()
        heads = [t for t in self.w.tk.splitlist(self.w.tk.call(self.w._cn_body_raw, 'tag', 'names'))
                 if str(t).startswith('cn_head') and str(self.w.tk.call(self.w._cn_body_raw, 'tag', 'cget', t, '-font'))]
        self.assertTrue(heads)                                                   # タイトルの行の字（title_inline）
        font = lambda t: str(self.w.tk.call(self.w._cn_body_raw, 'tag', 'cget', t, '-font'))
        before = {t: font(t) for t in heads}
        ov.enter(self.ev(200), self.w)
        self.assertEqual({t: font(t) for t in heads}, before)                      # 小さくしない
        ov.exit()
        with mock.patch.dict(os.environ, {'CN_OVERVIEW_KEEP_HEAD': '0'}):
            ov.enter(self.ev(200), self.w)
            self.assertNotEqual({t: font(t) for t in heads}, before)               # 前の形
            ov.exit()
        self.assertEqual({t: font(t) for t in heads}, before)

    def test_bookmark_size_is_larger(self):
        self.assertGreaterEqual(O.BOOKMARK_SIZE, 11)

    def drag_down(self, ov, steps=400):
        y = 300
        for _ in range(steps):
            y -= 10
            ov.motion(self.ev(y))
        self.root.update()

    def test_peer_reaches_the_last_row(self):
        # 分身は最後の行が上端に来るまで送れる（文の終わりで止まらない）。枠も最後の行に届く
        app, ov = self.dark_app()
        self.w.yview('350.0')
        self.root.update()
        ov.enter(self.ev(300), self.w)
        self.drag_down(ov)
        raw = self.w._cn_body_raw
        last = int(str(self.root.tk.call(raw, 'index', 'end-1c')).split('.')[0])
        rng = [str(x) for x in self.root.tk.splitlist(self.root.tk.call(raw, 'tag', 'ranges', 'ov_dest'))]
        self.assertGreaterEqual(int(rng[-1].split('.')[0]), last, rng)
        ov.exit()

    def test_pointer_is_brought_back_from_the_screen_edge(self):
        app, ov = self.dark_app()
        warps = []
        app._warp_pointer = lambda w, x, y: (warps.append((x, y)), 'sync')[1]
        app.DRAG_WARP_EDGE = 64
        ov.enter(self.ev(300), self.w)
        edge = NS(x=100, y=0, x_root=self.w.winfo_rootx() + 100, y_root=2, widget=self.w, state=0)
        ov.motion(edge)                                                            # 画面の上の端
        self.assertTrue(warps)
        want = ov.active['warp_to']
        top = ov._top_raw()
        ov.motion(NS(x=100, y=0, x_root=edge.x_root, y_root=1, widget=self.w, state=0))   # 戻す前の報せ: 数えない
        self.assertEqual(ov._top_raw(), top)
        ov.motion(NS(x=100, y=0, x_root=edge.x_root, y_root=want, widget=self.w, state=0))
        self.assertNotIn('warp_to', ov.active)
        ov.exit()
        self.assertEqual(warps[-1], (100, 300))                                    # 離したら押した所へ戻す
        warps.clear()
        with mock.patch.dict(os.environ, {'CN_OVERVIEW_EDGE_WARP': '0'}):
            ov.enter(self.ev(300), self.w)
            ov.motion(edge)
            self.assertFalse(warps)
            ov.exit()

    # 2026-11-21 05:12Z うにさん「縮小で、やはり途中でスクロールが止まる」「タイトルと目次は縦に短くなるので、できれば見た目を
    # キープする」「行番号が縮小時に追従しないので、それが意図的なら番号を非表示にする」
    def test_drag_step_is_the_small_line_from_the_title(self):
        app, ov = self.dark_app()
        self.w.yview_moveto(0)
        self.root.update()
        ov.enter(self.ev(300), self.w)
        ov.motion(self.ev(290))
        self.assertLess(ov.active['line_h'], 20)                                 # 上端がタイトルの行でも、小さい字の1行
        new = ov.active['line_h']
        ov.exit()
        with mock.patch.dict(os.environ, {'CN_OVERVIEW_LINE_H_FONT': '0'}):
            self.w.yview_moveto(0)
            self.root.update()
            ov.enter(self.ev(300), self.w)
            ov.motion(self.ev(290))
            self.assertNotEqual(ov.active['line_h'], new)                        # 前の形（上端の表示の行の高さ）
            ov.exit()

    def test_head_rows_keep_their_spacing(self):
        app, ov = self.dark_app()
        raw = self.w._cn_body_raw
        ov.enter(self.ev(200), self.w)
        tags = [str(t) for t in self.root.tk.splitlist(self.root.tk.call(raw, 'tag', 'names', '1.0'))]
        self.assertTrue([t for t in tags if t.startswith(O.HEAD_SPACE_TAG)], tags)
        name = ov._left()
        self.assertEqual(int(self.root.tk.call(name, 'cget', '-pady')), int(self.w.cget('pady')))
        ov.exit()
        self.assertFalse(self.root.tk.call(raw, 'tag', 'ranges', O.HEAD_SPACE_TAG + '_0'))

    def test_gutter_numbers_are_covered_while_shown(self):
        app, ov = self.dark_app()
        g = tk.Canvas(self.frame, width=30, bg='#222222')
        g.pack(side='left', fill='y', before=self.w)
        app.editor_gutter = g
        self.root.update()
        ov.enter(self.ev(200), self.w)
        covers = ov.active['gutter_covers']
        self.assertEqual(len(covers), 1)
        self.assertTrue(covers[0].winfo_exists())
        ov.exit()
        self.assertFalse(covers[0].winfo_exists())
        with mock.patch.dict(os.environ, {'CN_OVERVIEW_HIDE_GUTTER': '0'}):
            ov.enter(self.ev(200), self.w)
            self.assertEqual(ov.active['gutter_covers'], [])
            ov.exit()

    def test_stuck_is_logged_once(self):
        import tempfile
        app, ov = self.dark_app()
        folder = tempfile.mkdtemp()
        app._scroll_trace_dir = folder
        ov.enter(self.ev(200), self.w)
        with mock.patch.object(O, 'app_module_of', lambda app: NS(redo_trace_on=lambda: True, data_dir=lambda: folder)):
            for _ in range(O.STUCK_LOG_AFTER + 5):
                ov._watch_stuck(ov.active, -1, 150, 150, self.ev(100))
        ov.exit()
        text = open(os.path.join(folder, 'overview_fast.log'), encoding='utf-8').read()
        self.assertEqual(text.count('stuck'), 1)

    # 2026-11-21 06:23Z うにさん「縮小のスクロールは、やはり一番下まで行きません。一番下の少し前から、そこより下に行けなく
    # なります」: 分身の Text は最後のページより下へ送れない。下端に着いた後は、範囲の枠だけを下へ滑らせ、最後の行まで
    # 選べる（離した本文の位置もその枠の上端）。分身が送れない形は、送りを止める作り物（_scroll）で作る
    def reach_the_end(self, rows, capped=True):
        import title_inline as TI2
        frame = tk.Frame(self.root)
        frame.pack(fill='both', expand=True)
        w = tk.Text(frame, font=('Meiryo', 12), wrap='word')
        w.pack(fill='both', expand=True)
        TI2.prepare(w)
        TI2.style(w, 'Meiryo', 10, '#1f5fbf', '#888888')
        TI2.write(w, '題', [])
        w.insert('1.0', '\n'.join('%d行目の本文です。' % i for i in range(1, rows + 1)))
        self.root.update()
        app, _ov = self.dark_app()
        app.editor = w
        ov = O.FastOverview(app)
        app._ovf = ov
        raw = w._cn_body_raw
        last = int(str(self.root.tk.call(raw, 'index', 'end-1c')).split('.')[0])
        real = O.FastOverview._scroll

        def capped_scroll(this, peer, units):
            real(this, peer, units)
            cap = max(1, last - 40)                            # 最後のページ（40行ぶん）より下へは送れない分身
            top = int(str(self.root.tk.call(peer, 'index', '@0,0')).split('.')[0])
            if top > cap:
                self.root.tk.call(peer, 'yview', '%d.0' % cap)
        ev = lambda y: NS(x=100, y=y, x_root=w.winfo_rootx() + 100, y_root=w.winfo_rooty() + y, widget=w, state=0)
        with mock.patch.object(O.FastOverview, '_scroll', capped_scroll if capped else real):
            ov.enter(ev(300), w)
            y = 300
            for _ in range(rows * 2 + 200):
                y -= 10
                ov.motion(ev(y))
            self.root.update()
            rng = [str(x) for x in self.root.tk.splitlist(self.root.tk.call(raw, 'tag', 'ranges', 'ov_dest'))]
            reached = int(rng[-1].split('.')[0]) >= last if rng else False
            aim = ov.active.get('aim', 0)
            top = ov._top_raw_of(ov.active)
            ov.exit()
            self.root.update()
        return reached, aim, top, last, w

    def test_reaches_the_last_row_for_any_length(self):
        for rows in (30, 300, 3000):
            reached, aim, top, last, w = self.reach_the_end(rows)
            self.assertTrue(reached, (rows, aim, top, last))                    # 枠が最後の行まで届く
            if rows > 60:
                self.assertGreater(aim, 0, rows)                                # 分身が止まった後は枠を滑らせた
            self.assertGreaterEqual(int(w.index('@0,0').split('.')[0]) + 40, last - 1, rows)   # 離すと最後の方

    def test_end_slide_switch(self):
        with mock.patch.dict(os.environ, {'CN_OVERVIEW_END_SLIDE': '0'}):
            reached, aim, top, last, w = self.reach_the_end(300)
        self.assertEqual(aim, 0)
        self.assertFalse(reached)                                               # 前の形（最後の手前で止まる）

    # 2026-11-21（軽量化）: 縮小に入るたびにタグごとに Font を作って問い合わせていた（入る時間の約2割）。同じ指定は控えから
    def test_font_actual_is_memoised(self):
        from tkinter import font as tkfont
        O._FONT_ACTUAL.clear()
        made = []
        real = tkfont.Font

        def counting(*a, **k):
            made.append(1)
            return real(*a, **k)
        with mock.patch.object(tkfont, 'Font', counting):
            first = O._font_size_of(self.w, ('Meiryo', 14))
            second = O._font_size_of(self.w, ('Meiryo', 14))
            self.assertEqual(first, second)
            self.assertEqual(len(made), 1)
            with mock.patch.dict(os.environ, {'CN_OVERVIEW_FONT_MEMO': '0'}):
                O._font_size_of(self.w, ('Meiryo', 14))
            self.assertEqual(len(made), 2)                                   # 前の形（毎回作る）

    def test_switches(self):
        self.assertTrue(O.enabled(self.app))
        self.assertFalse(O.enabled(self.app, {'CN_OVERVIEW_FAST': '0'}))
        # 2026-11-23: デバッグメニューの項目を外し、いつも速い形。前に切って保存した設定でも速い形
        self.app.settings['overview_fast'] = False
        self.assertTrue(O.enabled(self.app))


if __name__ == '__main__':
    unittest.main()
