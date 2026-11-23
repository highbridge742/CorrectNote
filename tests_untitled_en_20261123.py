# -*- coding: utf-8 -*-
"""英語の画面では、名前もファイルも無いタブ（既定の「無題」）の見出しを Untitled と見せる（2026-11-23 説明書の担当「英語の
画面でもタブの見出しが『無題』のまま」）。表示だけで、タブの控え（session）の中身は変えない。名前の付いたタブ・タイトルの
あるタブは名前のまま。CN_UNTITLED_EN=0 で前の形。Tk の窓は出さない（作った値だけ）。"""
import os
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import app
import ui_lang


def fake(active_tab, current_file=None):
    return NS(session=NS(current=lambda: active_tab), current_file=current_file, _title_toc=None,
              _untitled_label=app.CorrectNoteApp._untitled_label)


def full(a, tab, active=None):
    return app.CorrectNoteApp._tab_full_name(a, tab, active)


class Untitled(unittest.TestCase):
    def setUp(self):
        self.addCleanup(lambda: setattr(ui_lang, '_lang', 'ja') or ui_lang._cache.clear())

    def english(self):
        ui_lang._lang = 'en'
        ui_lang._cache.clear()

    def test_japanese_is_unchanged(self):
        tab = {'text': 'x', 'path': None}
        a = fake(tab)
        self.assertEqual(full(a, tab, True), '無題')
        self.assertEqual(full(a, {'text': 'y'}, False), '無題')

    def test_english_shows_untitled(self):
        self.english()
        tab = {'text': 'x', 'path': None}
        a = fake(tab)
        self.assertEqual(full(a, tab, True), 'Untitled')                    # 選んでいるタブ
        other = {'text': 'y', 'path': None}
        self.assertEqual(full(a, other, False), 'Untitled')                 # ほかのタブ
        self.assertNotIn('title', other)                                    # 控えの中身は変えない
        self.assertEqual(full(a, {'text': 'z', 'path': r'C:\\x\\memo.txt'}, False), 'memo')    # ファイル名はそのまま

    def test_named_tabs_keep_their_name(self):
        self.english()
        a = fake({})
        self.assertEqual(full(a, {'text': 'y', 'title': '無題'}, False), '無題')        # 自分で「無題」と名付けたタブ
        self.assertEqual(full(a, {'text': 'y', 'doc_title': '無題'}, False), '無題')    # タイトル欄に「無題」と書いたタブ

    def test_switch_back(self):
        self.english()
        with mock.patch.dict(os.environ, {'CN_UNTITLED_EN': '0'}):
            self.assertEqual(full(fake({}), {'text': 'y'}, False), '無題')


if __name__ == '__main__':
    unittest.main()
