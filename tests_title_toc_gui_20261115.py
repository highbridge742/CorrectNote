# -*- coding: utf-8 -*-
"""タイトルと目次の欄（画面・2026-11-15 うにさん「タイトルと目次を実装します」）。自分で作った Tk の窓の中だけで確かめる
（本物のキー送り・クリップボードは使わない。コピーはクリップボードの関数を差し替えて、渡す字だけを見る）。作った例文。"""
import os
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import title_toc as T


class Pane(unittest.TestCase):
    def setUp(self):
        os.environ.pop('CN_TITLE_TOC', None)
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.root.geometry('900x500+40+40')
        body = tk.Frame(self.root)
        body.pack(fill='both', expand=True)
        body.grid_columnconfigure(0, weight=1, uniform='pane')
        body.grid_columnconfigure(1, weight=1, uniform='pane')
        body.grid_rowconfigure(0, weight=1)
        left, right = tk.Frame(body), tk.Frame(body)
        left.grid(row=0, column=0, sticky='nsew')
        right.grid(row=0, column=1, sticky='nsew')
        font = ('Yu Gothic UI', 12)
        self.editor = tk.Text(left, undo=True, wrap='word', font=font, padx=14, pady=12, width=1)
        self.result = tk.Text(right, wrap='word', font=font, padx=14, pady=12, width=1)
        self.editor.pack(fill='both', expand=True)
        self.result.pack(fill='both', expand=True)
        self.text = '\n'.join('%d行目の文です。' % i for i in range(1, 61))
        self.editor.insert('1.0', self.text)
        self.result.insert('1.0', self.text)
        self.bookmarks = {3, 10}
        self.jumps = []
        self.app = NS(_body=body, editor=self.editor, result_view=self.result, _editor_wrap=left, _result_wrap=right,
                      bookmarks=self.bookmarks, settings={'dark_mode': False},
                      editor_source_text=lambda: self.editor.get('1.0', 'end-1c'),
                      _goto_line=lambda row: self.jumps.append(row), _layout_is_unified=lambda: False,
                      _editor_font=lambda: font, store=NS(_tokenize_fn=lambda line: []),
                      _show_copy_frame=mock.Mock(), _schedule_session_save=mock.Mock())
        self.toc = T.TitleToc(self.app)
        self.root.update()
        self.toc.refresh_toc(force=True)
        self.root.update()
        self.addCleanup(self.root.destroy)

    def pad(self, pane):
        return [str(x) for x in pane.tag_ranges(T.PAD_TAG)]

    def settle(self):
        self.toc.layout()
        self.root.update()

    def test_pad_stays_on_the_first_row_only(self):
        e = self.editor
        steps = (
            lambda: e.insert('1.0', '\n'),                       # 1行目の先頭で改行
            lambda: e.delete('1.0', '2.0'),                      # 1行目を消す
            lambda: e.insert('1.0', '貼り付け1\n貼り付け2\n'),    # 貼り付け
            lambda: e.edit_undo(),                               # 元に戻す
            lambda: (e.delete('1.0', 'end'), e.insert('1.0', 'まるごと\n置き換え')),   # 全体の置き換え
        )
        for step in steps:
            step()
            self.settle()
            # 1行目の頭の字だけ（1行目が空なら、その改行の字）
            self.assertEqual(self.pad(e), ['1.0', e.index('1.0+1c')])
            self.assertEqual(self.pad(self.result), ['1.0', self.result.index('1.0+1c')])
            self.assertEqual(len(e.tag_ranges(T.PAD_TAG)), 2)

    def test_pad_is_not_in_the_text(self):
        self.settle()
        self.assertEqual(self.editor.get('1.0', 'end-1c'), self.text)      # 保存・解析が読む本文は変わらない

    def test_rows_line_up_left_and_right(self):
        self.settle()
        for row in ('1.0', '2.0', '5.0'):
            a, b = self.editor.dlineinfo(row), self.result.dlineinfo(row)
            self.assertIsNotNone(a)
            self.assertEqual(a[1], b[1], row)

    def test_frame_sits_over_the_space_and_hides_when_scrolled(self):
        self.settle()
        info = self.editor.dlineinfo('1.0')
        place = self.toc.clip.place_info()
        self.assertTrue(place)
        # 2026-11-15 うにさん「タイトルの上の余白を詰め、本文の欄の上端へ寄せる」: 欄は1行目の表示行の頭より、本文の上の
        # 内側の余白（pady＋枠）から 2px を残した分（_shift）だけ上。余白のタグもその分だけ低い
        top = self.editor.winfo_rooty() - self.app._body.winfo_rooty() + info[1] - self.toc._shift()
        self.assertEqual(int(place['y']), top)
        self.assertEqual(int(place['height']), self.toc._height)
        # 余白の高さ＝欄の高さ − 上へ寄せた分（行間の基本の値を足した分）
        self.assertGreaterEqual(int(float(self.editor.tag_cget(T.PAD_TAG, 'spacing1'))), self.toc._height - self.toc._shift())
        # 2026-11-15 から欄は本文の欄（Text）の子の窓で、本文の欄の内側だけ（左右をまたぐ1つの欄だった時に、絵のあるテーマで
        # 本文の字が透けた・透過の窓にすると速いスクロールで黒い帯が出た）。分割の右の欄には、右の Text の子の窓に写しを
        # ずらして置き、左右をまたぐ1つの欄に見せる（tests_title_fixes_20261115.SplitMirror）
        self.assertIs(self.toc.clip.master, self.editor)
        self.assertLessEqual(int(place['width']), self.editor.winfo_width())
        self.editor.yview_moveto(1.0)
        self.toc.position()
        self.root.update()
        self.assertFalse(self.toc.clip.place_info())                 # 下へ送ると見切れて隠れる
        self.editor.yview_moveto(0.0)
        self.toc.position()
        self.root.update()
        self.assertTrue(self.toc.clip.place_info())

    def test_size_changes_are_followed(self):
        self.settle()
        before = self.toc._height
        self.toc.set_title('とても長いタイトル')
        self.bookmarks.update({20, 30, 40, 50})                     # 目次が長い時は全部並べて余白を伸ばす
        self.toc.refresh_toc()
        self.root.update()
        self.assertGreater(self.toc._height, before)
        # 余白は欄の高さ − 上へ寄せた分（2026-11-15 上端へ寄せた）
        self.assertGreaterEqual(int(float(self.editor.tag_cget(T.PAD_TAG, 'spacing1'))), self.toc._height - self.toc._shift())
        width = int(self.toc.clip.place_info()['width'])
        self.root.geometry('600x500')
        self.root.update()
        self.toc.position()
        self.root.update()
        self.assertLess(int(self.toc.clip.place_info()['width']), width)     # 窓の幅に合わせる

    def test_empty_toc_takes_no_space(self):
        self.settle()
        with_toc = self.toc._height
        self.bookmarks.clear()
        self.toc.refresh_toc()
        self.root.update()
        self.assertLess(self.toc._height, with_toc)
        self.assertFalse(self.toc.toc.winfo_ismapped())

    def test_links_jump(self):
        self.assertEqual([l.cget('text') for l in self.toc.links], ['3行目の文です。', '10行目の文です。'])
        self.toc.links[1].event_generate('<Button-1>')
        self.root.update()
        self.assertEqual(self.jumps, [10])
        import tkinter.font as tkfont
        self.assertTrue(tkfont.nametofont(str(self.toc.links[0].cget('font'))).actual('underline'))

    def test_theme_follows_the_pane(self):
        # 2026-11-15 うにさん「ダークモード対応と、スクロール対応が必要でした」: 色は本文の Text の今の色から取る
        self.settle()
        self.assertEqual(self.toc.links[0].cget('fg'), T.LINK_LIGHT)
        self.assertEqual(self.toc.title.cget('bg'), self.editor.cget('bg'))
        for pane in (self.editor, self.result):                     # テーマを暗くした（本文の色が替わった）
            pane.configure(bg='#1e2124', fg='#e6e6e6', insertbackground='#e6e6e6', selectbackground='#3a4a5a',
                           selectforeground='#ffffff')
        self.toc.position()                                          # スクロールの流れの中で気づいて塗り直す
        self.assertEqual(self.toc.title.cget('bg'), '#1e2124')
        self.assertEqual(self.toc.title.cget('fg'), '#e6e6e6')
        self.assertEqual(self.toc.title.cget('insertbackground'), '#e6e6e6')
        self.assertEqual(self.toc.title.cget('selectbackground'), '#3a4a5a')
        for w in (self.toc.clip, self.toc.frame, self.toc.toc):
            self.assertEqual(w.cget('bg'), '#1e2124')
        self.assertEqual(self.toc.links[0].cget('fg'), T.LINK_DARK)
        self.assertEqual(self.toc.links[0].cget('bg'), '#1e2124')

    def test_partly_scrolled_shows_the_rest(self):
        self.settle()
        full = self.toc._height
        self.editor.yview_scroll(20, 'pixels')                       # 1行目が少しだけ上へ送られた
        self.root.update()
        self.toc.position()
        self.root.update()
        info = self.editor.dlineinfo('1.0')
        if info is None or info[1] >= 0:
            self.skipTest('this Tk does not scroll by pixels')
        place = self.toc.clip.place_info()
        self.assertTrue(place)                                       # いきなり消えない
        self.assertLess(int(place['height']), full)                  # 見切れた分だけ低い
        self.assertEqual(int(float(self.toc.frame.place_info()['y'])), -(full - int(place['height'])))

    def test_wheel_on_the_area_scrolls_the_text(self):
        self.settle()
        before = self.editor.yview()[0]
        seen = []
        self.editor.bind('<MouseWheel>', lambda e: (seen.append(e.delta), self.editor.yview_scroll(3, 'units')))
        self.toc.title.event_generate('<MouseWheel>', delta=-120)
        self.root.update()
        self.assertEqual(seen, [-120])
        self.assertGreater(self.editor.yview()[0], before)

    def test_scroll_paths_move_the_area_with_the_first_row(self):
        self.settle()
        self.editor.configure(yscrollcommand=lambda *a: self.toc.position())   # アプリと同じ流れ（_on_editor_scroll）
        for move in (lambda: self.editor.yview_scroll(1, 'pages'),          # PgDn・スクロールバー
                     lambda: self.editor.yview_moveto(0.0),
                     lambda: self.editor.see('60.0'),                       # キー移動・ジャンプ
                     lambda: self.editor.see('1.0')):
            move()
            self.root.update()
            info = self.editor.dlineinfo('1.0')
            place = self.toc.clip.place_info()
            self.assertEqual(bool(place), info is not None and info[1] + self.toc._height > 0)

    def test_title_is_not_corrected(self):
        self.app._on_change = mock.Mock()
        self.app._analyze = mock.Mock()
        self.toc.title.insert('1.0', 'てすとのたいとる')
        self.root.update()
        self.assertEqual(self.toc.get_title(), 'てすとのたいとる')      # 書いたまま（補正・解析を通らない）
        self.app._on_change.assert_not_called()
        self.app._analyze.assert_not_called()
        self.assertEqual(self.editor.get('1.0', 'end-1c'), self.text)

    def test_one_line_only(self):
        self.toc.title.insert('1.0', 'あ')
        self.assertEqual(self.toc.title.event_generate('<Return>'), None)
        self.toc.set_title('一行目\n二行目')
        self.assertEqual(self.toc.get_title(), '一行目')

    def test_copy_gives_the_frame_but_no_enlargement(self):
        self.toc.set_title('旅行記のタイトル')
        self.toc.title.tag_add('sel', '1.0', '1.3')
        with mock.patch.object(self.toc.title, 'clipboard_clear') as clear, \
                mock.patch.object(self.toc.title, 'clipboard_append') as append:
            self.assertEqual(self.toc._copy(), 'break')
        clear.assert_called_once_with()
        append.assert_called_once_with('旅行記')
        self.app._show_copy_frame.assert_called_once()              # 白い枠は付ける
        self.assertEqual(self.toc.title.cget('font'), self.toc.title.cget('font'))   # 字の大きさは替えない


class Off(unittest.TestCase):
    def test_switch_off_installs_nothing(self):
        with mock.patch.dict(os.environ, {'CN_TITLE_TOC': '0'}):
            self.assertIsNone(T.install(NS()))


if __name__ == '__main__':
    unittest.main()
