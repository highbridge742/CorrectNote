# -*- coding: utf-8 -*-
"""選択してF3で検索（f3_search・2026-10-31 うにさん）。選んでいなければ F3 は Enter のまま。選んでいれば
既定のブラウザで Google 検索（オプション・既定オン）。その前の確かめ（オプション・既定オン）は F3・Enter で
開き、Esc・枠の外のクリック（焦点が外れる）で取りやめる。ブラウザは開かない（開く口を差し替える）。"""
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import f3_search
import settings as settings_module


class FakeSettings(dict):
    def get(self, key, default=None):
        return dict.get(self, key, default)


class F3SearchTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.text = tk.Text(self.root)
        self.text.pack()
        self.text.insert('1.0', '浅煎り ブレンド\n二行目')
        self.opened = []
        self.app = SimpleNamespace(settings=FakeSettings(f3_search=True, f3_search_confirm=False),
                                   status=SimpleNamespace(config=lambda **kw: None))

    def tearDown(self):
        self.root.destroy()

    def _handle(self):
        with patch.object(f3_search, 'open_search', lambda text, opener=None: self.opened.append(text) or True):
            return f3_search.handle(self.app, self.text)

    def test_the_defaults_are_on(self):
        self.assertTrue(settings_module.DEFAULTS['f3_search'])
        self.assertTrue(settings_module.DEFAULTS['f3_search_confirm'])

    def test_without_a_selection_f3_stays_enter(self):
        self.assertFalse(self._handle())
        self.assertEqual(self.opened, [])

    def test_a_selection_is_searched(self):
        self.text.tag_add('sel', '1.0', '2.2')
        self.assertTrue(self._handle())
        self.assertEqual(self.opened, ['浅煎り ブレンド 二行'])

    def test_the_option_off_keeps_enter(self):
        self.app.settings['f3_search'] = False
        self.text.tag_add('sel', '1.0', '1.3')
        self.assertFalse(self._handle())

    def test_a_given_word_is_searched(self):
        # 再変換の候補一覧で項目を選んでいないときの F3（選んでいる語・2026-11-01）
        with patch.object(f3_search, 'open_search', lambda text, opener=None: self.opened.append(text) or True):
            self.assertTrue(f3_search.handle_text(self.app, self.text, ' 資料 '))
            self.assertFalse(f3_search.handle_text(self.app, self.text, ''))
        self.assertEqual(self.opened, ['資料'])

    def test_the_url_is_a_google_search(self):
        self.assertEqual(f3_search.search_url('浅煎り ブレンド&'),
                         'https://www.google.com/search?q=%E6%B5%85%E7%85%8E%E3%82%8A+%E3%83%96%E3%83%AC%E3%83%B3%E3%83%89%26')
        got = []
        self.assertTrue(f3_search.open_search('あ', opener=lambda url: got.append(url) or True))
        self.assertEqual(got, [f3_search.search_url('あ')])

    def test_the_confirmation_runs_with_f3_or_enter_and_cancels_with_escape(self):
        self.app.settings['f3_search_confirm'] = True
        self.text.tag_add('sel', '1.0', '1.3')
        for key, expected in (('F3', ['浅煎り']), ('Return', ['浅煎り']), ('Escape', [])):
            self.opened.clear()
            self.assertTrue(self._handle())
            confirm = self.app._f3_confirm
            self.assertEqual(self.opened, [])          # まだ開かない
            labels = [w.cget('text') for w in confirm.body.winfo_children()]
            self.assertEqual(labels, [f3_search.QUESTION, f3_search.HINT])
            with patch.object(f3_search, 'open_search', lambda text, opener=None: self.opened.append(text) or True):
                handler = {'F3': confirm._accept, 'Return': confirm._accept, 'Escape': confirm._cancel}[key]
                handler()
            self.assertEqual(self.opened, expected, key)
            self.assertTrue(confirm.done)
            self.assertFalse(confirm.top.winfo_exists())

    def test_the_text_answers_for_the_box_and_restores_itself(self):
        self.app.settings['f3_search_confirm'] = True
        self.text.tag_add('sel', '1.0', '1.3')
        tags = self.text.bindtags()
        self._handle()
        confirm = self.app._f3_confirm
        self.assertEqual(self.text.bindtags()[0], f3_search.Confirm.TAG)     # 枠は焦点を取らず、欄が受ける
        # 枠が出ている間の F3 は実行（2つ目の枠を出さない）
        self.assertTrue(self._handle())
        self.assertEqual(self.opened, ['浅煎り'])
        self.assertTrue(confirm.done)
        self.assertEqual(self.text.bindtags(), tags)
        self.assertEqual(self.root.tk.call('bind', 'all', '<ButtonPress>'), '')

    def test_a_click_outside_cancels_and_inside_does_not(self):
        self.app.settings['f3_search_confirm'] = True
        self.text.tag_add('sel', '1.0', '1.3')
        self._handle()
        confirm = self.app._f3_confirm
        confirm._pressed(str(confirm.body))
        self.assertFalse(confirm.done)
        confirm._pressed(str(self.text))
        self.assertTrue(confirm.done)
        confirm._accept()                          # 閉じたあとは何もしない
        self.assertEqual(self.opened, [])

if __name__ == '__main__':
    unittest.main()
