# -*- coding: utf-8 -*-
"""起動の「アプリを更新しました」の問いの文（2026-11-15）。「辞書を取り込む…」は 2026-11-08 から「設定」には無く、
学習 → 辞書と語彙の管理 の中（学習を残さない形＝既定では出ない）。文はメニューに在る時だけ、その場所を添える。"""
import io
import unittest

import ui_lang_en

BASE = ('アプリを更新しました。\n辞書と索引を新しい版で作り直しますか？\n\n'
        '・覚えた語や手で足した語は消えません（足すだけです）\n・数十秒かかることがあります')
FULL = BASE + '\n・あとで「学習 → 辞書と語彙の管理 → 辞書を取り込む…」からもできます'


def _tables():
    return [v for v in vars(ui_lang_en).values() if isinstance(v, dict)]


class UpdateMessage(unittest.TestCase):
    def setUp(self):
        with io.open('app.py', encoding='utf-8') as f:
            self.src = f.read()

    def test_no_old_menu_path(self):
        self.assertNotIn('設定 → 辞書を取り込む', self.src)

    def test_sentence_only_when_the_menu_item_shows(self):
        i = self.src.find("'・数十秒かかることがあります')")
        self.assertGreater(i, 0)
        block = self.src[i:i + 400]
        self.assertIn("if not getattr(_vocabulary, 'LEARNED_OFF', False):", block)
        self.assertIn('学習 → 辞書と語彙の管理 → 辞書を取り込む…', block)

    def test_english_has_both(self):
        tables = _tables()
        for key in (BASE, FULL):
            hits = [t[key] for t in tables if key in t]
            self.assertTrue(hits, key[-30:])
        with open('ui_lang_en.py', encoding='utf-8') as f:
            self.assertNotIn('Settings → Import dictionary', f.read())
        self.assertTrue(any('Learning → Dictionary and vocabulary → Import dictionary…' in t.get(FULL, '') for t in tables))

    def test_menu_labels_match(self):
        # 文に書いた場所が、本当のメニューの名前と同じ
        for label in ("'学習'", "'辞書と語彙の管理'", "'辞書を取り込む…'"):
            self.assertIn(label, self.src)


if __name__ == '__main__':
    unittest.main()
