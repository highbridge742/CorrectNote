"""英字の名前と16進の ID を「かな入力のまま打った字」と取り違えない（2026-10-15）。

実機で、貼り付けた英文の中の利用者名（数字＋英単語）と ID（16進の
長い並び）が、かな配列の読み替えでかな・漢字に化けた。IME が手元に
あると、かなに戻した列が漢字に化けて読めてしまうので、意味の判定の前に
形で止める（`halfwidth.looks_like_halfwidth_input`）。

ここの例はすべて作った並び（実際の文は使わない）。
"""
import unittest
from unittest.mock import patch

import halfwidth as H


# 作った例: 数字＋同梱の英語辞書に載る6字以上の語 / 16進の ID / GUID
_NAMES = ('k9shadows', 'q7windows', 'r2settings', 'Zed4players')
_HEX_IDS = ('5f3a9c0e7b21d4c8a6e0', 'SessionKey:2048:9b1e77c4d02af3e5',
            'trace=7c1e0b9a44d2f6e3', '3f2504e0-4f89-11d3-9a0c-0305e82c3301')
# うにさんが挙げた、かな入力のまま打った実例（halfwidth.py の説明から）
_KANA_TYPED = ('md@i(4l)h', 'qyb@kzut@l', '^ytyx;ue', 'c4w@r,', 'bkzg@f',
               'i(4l)hoy', 'fythkjji(4l)h', 'hd(4r.bsw@', 'md[ki)4l)h',
               'b@^ytyg)94w@gjr', 'up@uo<5eqyb@t@b@^ytyx;wm')


class HalfwidthIdentifierTest(unittest.TestCase):
    def test_names_with_an_english_word_are_not_kana_typing(self):
        for text in _NAMES:
            self.assertFalse(H.looks_like_halfwidth_input(text), text)

    def test_hex_identifiers_are_not_kana_typing(self):
        for text in _HEX_IDS:
            self.assertFalse(H.looks_like_halfwidth_input(text), text)
            self.assertTrue(H._has_hex_identifier(text), text)

    def test_kana_typing_examples_still_open(self):
        for text in _KANA_TYPED:
            self.assertTrue(H.looks_like_halfwidth_input(text), text)
            self.assertFalse(H._has_hex_identifier(text), text)

    def test_short_or_unmixed_runs_are_not_hex_ids(self):
        # 短い並び・数字だけ・英字だけは、この判定では止めない
        for text in ('3e45', '4ea5c0', '0123456789012', 'deadbeefcafe', 'a1b2c3d4e5f'):
            self.assertFalse(H._has_hex_identifier(text), text)

    def test_shape_stops_before_any_reading_judgement(self):
        # 日本語として読めると判定されても（IME がある PC の状況）、
        # 形で止めた並びはかなに戻さない。
        with patch.object(H, 'makes_sense_as_japanese', return_value=True):
            for text in _NAMES + _HEX_IDS:
                self.assertIsNone(H.correct_halfwidth(
                    text, None, lambda *a, **k: [], judge=lambda c: []), text)

    def test_whole_line_is_left_as_written(self):
        import corrector as C
        from vocabulary import VocabularyStore, find_known_readings_flex
        from seed_vocabulary import load_seed
        store = VocabularyStore()
        load_seed(store)
        tok = C.make_tokenizer(store)
        for method in ('kana', 'romaji'):
            for line in ('k9shadows の投稿8月29日',
                         'Error SessionKey:2048:9b1e77c4d02af3e5 failed'):
                result = C.correct_line(line, store, tok, find_known_readings_flex,
                                        input_method=method)
                self.assertEqual(result['corrected'], line, (method, line))


if __name__ == '__main__':
    unittest.main()
