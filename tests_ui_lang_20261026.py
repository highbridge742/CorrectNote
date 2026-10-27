"""
画面の表示言語（ui_lang.py・Language メニュー・2026-10-26）の試験。

- 英語にすると、作るウィジェット・メニューの文字が訳される。
- 読み返す（cget / entrycget）と元の日本語が返る（アプリの比べる所を守る）。
- 日本語へ戻すと、開いている窓の文字が元に戻る。
- 本人の語（ui_lang.raw）は訳さない。
- 日本の IME 用の設定は、字下げして末尾に (Japanese IME setting)。
"""

import tkinter as tk
import unittest

import ui_lang


class UiLangTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        ui_lang.install()

    def setUp(self):
        ui_lang.set_language('ja')
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        ui_lang.set_language('ja')
        self.root.destroy()

    def _raw_text(self, w):
        return w.tk.call(w._w, 'cget', '-text')

    def test_japanese_is_untouched(self):
        lab = tk.Label(self.root, text='保存')
        self.assertEqual(self._raw_text(lab), '保存')
        self.assertEqual(ui_lang.tr('保存'), '保存')

    def test_widget_and_menu_translate_and_read_back(self):
        ui_lang.set_language('en', self.root)
        lab = tk.Label(self.root, text='保存')
        self.assertEqual(self._raw_text(lab), 'Save')
        self.assertEqual(lab.cget('text'), '保存')
        self.assertEqual(lab['text'], '保存')
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label='名前を付けて保存…')
        shown = menu.tk.call(menu._w, 'entrycget', 0, '-label')
        self.assertNotEqual(shown, '名前を付けて保存…')
        self.assertFalse(ui_lang._JA.search(shown))
        self.assertEqual(menu.entrycget(0, 'label'), '名前を付けて保存…')

    def test_switch_back_and_forth(self):
        lab = tk.Label(self.root, text='保存')
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label='保存', accelerator='Ctrl+S')
        self.root.title('無題')
        ui_lang.set_language('en', self.root)
        self.assertEqual(self._raw_text(lab), 'Save')
        self.assertEqual(menu.tk.call(menu._w, 'entrycget', 0, '-label'), 'Save')
        self.assertEqual(self.root.tk.call('wm', 'title', self.root._w), 'Untitled')
        self.assertEqual(self.root.title(), '無題')
        ui_lang.set_language('ja', self.root)
        self.assertEqual(self._raw_text(lab), '保存')
        self.assertEqual(menu.tk.call(menu._w, 'entrycget', 0, '-label'), '保存')
        self.assertEqual(self.root.tk.call('wm', 'title', self.root._w), '無題')

    def test_raw_text_is_kept(self):
        ui_lang.set_language('en', self.root)
        b = tk.Button(self.root, text=ui_lang.raw('保存'))
        self.assertEqual(self._raw_text(b), '保存')
        b.configure(text='保存')         # 同じ欄に後から入れても本人の語のまま
        self.assertEqual(self._raw_text(b), '保存')
        ui_lang.set_language('ja', self.root)
        ui_lang.set_language('en', self.root)
        self.assertEqual(self._raw_text(b), '保存')

    def test_status_progress_keeps_japanese_start(self):
        ui_lang.set_language('en', self.root)
        lab = tk.Label(self.root)
        lab.config(text='解析中… 3/10 行')
        self.assertFalse(ui_lang._JA.search(self._raw_text(lab)))
        self.assertTrue(lab.cget('text').startswith('解析中'))

    def test_ime_only_items_are_indented_and_noted(self):
        ui_lang.set_language('en', self.root)
        s = ui_lang.tr('かなの配列（かな入力）')
        self.assertTrue(s.startswith(ui_lang.IME_INDENT))
        self.assertTrue(s.endswith('(Japanese IME setting)'))
        self.assertTrue(ui_lang.tr('親指シフト（NICOLA）').endswith('(Japanese IME setting)'))
        # 英字の配列は日本の IME 用ではない
        self.assertFalse(ui_lang.tr('英字の配列（ローマ字入力・英語）').endswith('(Japanese IME setting)'))

    def test_unknown_text_stays(self):
        ui_lang.set_language('en', self.root)
        self.assertEqual(ui_lang.tr('きょうはいい天気です'), 'きょうはいい天気です')
        self.assertEqual(ui_lang.tr('Hello'), 'Hello')

    def test_empty_setting_follows_system_language(self):
        orig = ui_lang.system_language
        try:
            ui_lang.system_language = lambda: 'en'
            ui_lang.set_language('', self.root)
            self.assertEqual(ui_lang.language(), 'en')
            ui_lang.set_language('ja', self.root)
            ui_lang.system_language = lambda: 'ja'
            ui_lang.set_language('', self.root)
            self.assertEqual(ui_lang.language(), 'ja')
        finally:
            ui_lang.system_language = orig

    def test_analysis_lines_translate_by_terms(self):
        ui_lang.set_language('en', self.root)
        s = ui_lang.tr('  名詞（サ変）・連用形（辞書に無い語）')
        self.assertTrue(s.startswith('  '))
        self.assertFalse(ui_lang._JA.search(s), s)
        # 「」の中の本人の文字は残す
        s = ui_lang.tr('  「たべる」と「を」は続けて置けない')
        self.assertIn('たべる', s)
        self.assertFalse(ui_lang._JA.search(s.replace('たべる', '').replace('を', '')), s)


if __name__ == '__main__':
    unittest.main()
