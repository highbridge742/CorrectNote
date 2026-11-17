# -*- coding: utf-8 -*-
"""ファイルタブの名前（2026-11-16 うにさん）: タイトルがあればタイトル・空ならファイル名（.txt は拡張子を出さない）・
未保存は今のまま・タイトルを打てば付け直す・全部が窓に収まらない時だけ字数で切る。自分の Tk の窓だけ・作った例。"""
import os
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import tab_label as L


class Names(unittest.TestCase):
    def test_title_when_there_is_one(self):                                   # 1
        self.assertEqual(L.display_name(r'C:\memo\note.md', '旅の計画', 'note.md', {}), '旅の計画')

    def test_file_name_when_the_title_is_empty(self):                         # 2
        self.assertEqual(L.display_name(r'C:\memo\note.md', '', 'note.md', {}), 'note.md')
        self.assertEqual(L.display_name(r'C:\memo\note.md', '   ', 'note.md', {}), 'note.md')

    def test_file_name_when_the_title_is_the_stem(self):                      # 3
        self.assertEqual(L.display_name(r'C:\memo\note.md', 'note', 'note.md', {}), 'note.md')

    def test_txt_hides_its_extension(self):                                   # 4
        self.assertEqual(L.display_name(r'C:\memo\note.txt', '', 'note.txt', {}), 'note')
        self.assertEqual(L.display_name(r'C:\memo\NOTE.TXT', 'NOTE', 'NOTE.TXT', {}), 'NOTE')
        self.assertEqual(L.display_name(r'C:\memo\note.txt', '旅', 'note.txt', {}), '旅')

    def test_unsaved_tab_keeps_its_name(self):                                # 5
        self.assertEqual(L.display_name(None, '旅の計画', '無題', {}), '無題')
        self.assertEqual(L.display_name('', '旅の計画', 'メモ', {}), 'メモ')

    def test_switch_back_to_the_old_name(self):
        self.assertEqual(L.display_name(r'C:\memo\note.txt', '旅の計画', 'note.txt', {'CN_TAB_LABEL_TITLE': '0'}),
                         'note.txt')


class Fit(unittest.TestCase):                                                  # 7
    """2026-11-16 うにさん「末尾は...にしないでよい。文字数の下限は全角6文字、半角のみなら12文字。デバッグパラメータに」:
    字の幅（全角＝2・半角＝1）で切る・末尾に「…」は付けない・下限は幅 12。"""
    def width(self, shown):
        return sum(8 * L.text_width(s) + 30 for s in shown)

    def test_no_cut_when_everything_fits(self):
        self.assertIsNone(L.fit_limit(['一二三四五', 'あいう'], self.width, 1000))

    def test_cut_only_as_far_as_needed(self):
        names = ['一二三四五六七八九十', 'あいうえおかきくけこ']
        limit = L.fit_limit(names, self.width, 260)
        self.assertLessEqual(self.width([L.shorten(n, limit) for n in names]), 260)
        self.assertGreater(self.width([L.shorten(n, limit + 1) for n in names]), 260)

    def test_never_below_six_wide_or_twelve_narrow_characters(self):
        self.assertEqual(L.MIN_WIDTH, 12)
        limit = L.fit_limit(['一二三四五六七八九十'] * 20, self.width, 50)
        self.assertEqual(limit, 12)
        self.assertEqual(L.shorten('一二三四五六七八九十', limit), '一二三四五六')          # 全角6字
        self.assertEqual(L.shorten('abcdefghijklmnop', limit), 'abcdefghijkl')            # 半角12字
        self.assertEqual(L.shorten('旅ab旅cd旅efgh', limit), '旅ab旅cd旅ef')                  # 混ざれば幅12まで

    def test_no_ellipsis(self):
        self.assertEqual(L.shorten('一二三四五', 6), '一二三')
        self.assertEqual(L.shorten('一二三', 6), '一二三')
        self.assertEqual(L.shorten('一二三四五', None), '一二三四五')
        self.assertNotIn('…', L.shorten('一二三四五六七八九十', 12))

    def test_the_minimum_is_a_debug_parameter(self):
        import debug_menu
        self.assertIn('tab_name_min', debug_menu.KEYS)
        self.assertEqual(debug_menu.default('tab_name_min'), 12)
        self.assertEqual(debug_menu.maximum('tab_name_min'), L.MIN_WIDTH_MAX)
        with mock.patch.object(L, 'MIN_WIDTH', 4):                                      # パラメータで変えると効く
            self.assertEqual(L.fit_limit(['一二三四五六七八九十'] * 20, self.width, 50), 4)


class InTheApp(unittest.TestCase):
    """app の札の字・切る上限の見直し・タイトルを打った時の付け直し（app の関数を作り物の app で呼ぶ）。"""
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        import app
        self.app_cls = app.CorrectNoteApp

    def fake(self, tabs, width):
        viewport = tk.Canvas(self.root, width=width, height=20, highlightthickness=0)
        viewport.pack()
        viewport.winfo_width = lambda w=width: w       # 窓は出さない（隠したままの窓は幅が 1 になる）
        widgets = []
        for _ in tabs:
            f = tk.Frame(viewport)
            widgets.append(dict(frame=f, label=tk.Label(f, font=('Yu Gothic UI', 9), padx=10),
                                close=tk.Label(f, text='✕', font=('Yu Gothic UI', 8), padx=6)))
        session = NS(tabs=tabs, active=0, current=lambda: tabs[0])
        fake = NS(session=session, current_file=tabs[0].get('path'), _dirty=False, _title_toc=None,
                  _tab_widgets=widgets, _tab_viewport=viewport, _tab_plus=tk.Label(viewport, text='＋'),
                  _tab_char_limit=None, TAB_TITLE_MAX=14, _refresh_tab_bar=mock.Mock())
        cls = self.app_cls
        fake._tab_full_name = lambda tab, active=None: cls._tab_full_name(fake, tab, active)
        self.root.update()
        return fake

    def test_label_uses_the_title_and_keeps_the_unsaved_mark(self):           # 1・6
        tabs = [dict(path=r'C:\m\a.txt', doc_title='旅の計画', saved=True),
                dict(path=r'C:\m\b.md', doc_title='', saved=False)]
        fake = self.fake(tabs, 2000)
        self.assertEqual(self.app_cls._tab_label_text(fake, tabs[0], True), '旅の計画')
        self.assertEqual(self.app_cls._tab_label_text(fake, tabs[1], False), '● b.md')
        fake._title_toc = NS(get_title=lambda: '打ち替えた題')                 # 選んでいるタブは打っている題から
        self.assertEqual(self.app_cls._tab_label_text(fake, tabs[0], True), '打ち替えた題')

    def test_fit_cuts_only_when_the_bar_is_too_narrow(self):                  # 7
        tabs = [dict(path=r'C:\m\%d.txt' % i, doc_title='とても長いタイトルの文書その%d' % i) for i in range(6)]
        wide = self.fake(tabs, 4000)
        with mock.patch.dict(os.environ, {'CN_TAB_LABEL_TITLE': '1'}):
            self.app_cls._fit_tab_labels(wide)
        self.assertIsNone(wide._tab_char_limit)
        wide._refresh_tab_bar.assert_not_called()
        narrow = self.fake(tabs, 500)
        with mock.patch.dict(os.environ, {'CN_TAB_LABEL_TITLE': '1'}):
            self.app_cls._fit_tab_labels(narrow)
        self.assertIsNotNone(narrow._tab_char_limit)
        self.assertGreaterEqual(narrow._tab_char_limit, L.MIN_WIDTH)
        narrow._refresh_tab_bar.assert_called_once_with()
        label = self.app_cls._tab_label_text(narrow, tabs[1], False)
        self.assertNotIn('…', label)                                             # 末尾に「…」は付けない
        self.assertTrue('とても長いタイトルの文書その1'.startswith(label) and len(label) < 15)
        self.assertEqual(self.app_cls._tab_full_name(narrow, tabs[1], False), 'とても長いタイトルの文書その1')

    def test_typing_the_title_queues_one_rename(self):                       # 6
        calls = []
        fake = NS(root=self.root, _tab_names_job=None, _refresh_tab_bar=lambda: calls.append(1),
                  TAB_NAMES_DELAY_MS=self.app_cls.TAB_NAMES_DELAY_MS)
        fake._apply_tab_names = lambda: self.app_cls._apply_tab_names(fake)
        for _ in range(5):
            self.app_cls._queue_tab_names(fake)
        self.assertIsNotNone(fake._tab_names_job)
        self.root.after(self.app_cls.TAB_NAMES_DELAY_MS + 100, self.root.quit)
        self.root.mainloop()
        self.assertEqual(calls, [1])                                         # 打つたびではなく1回

    def test_title_edit_asks_the_app_for_new_tab_names(self):
        import title_toc as T
        queued = []
        app = NS(_queue_tab_names=lambda: queued.append(1))
        toc = NS(title=tk.Text(self.root), _title_text='前', _loading=False, app=app,
                 paint_pos=lambda: None, undo=NS(record=lambda *a: None), _save_soon=lambda: None)
        toc.title.insert('1.0', '新しい題')
        toc.title.edit_modified(True)
        T.TitleToc._modified(toc)
        self.assertEqual(queued, [1])


if __name__ == '__main__':
    unittest.main()
