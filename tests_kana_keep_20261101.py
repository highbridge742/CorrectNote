# -*- coding: utf-8 -*-
"""かなで書いた和語は読みをそのまま漢字にしない・漢語は漢字に（kana_keep・2026-11-01）。作った文。"""
import unittest
from tests_analysis_async import initial
import kana_keep as K
import correction_entry as CE


class KanaKeepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = initial()

    def run_line(self, line):
        st = self.st
        return CE.correct_line(line, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                               decisions=st.decisions, context_vec=st.context_vec)['corrected']

    def test_word_kind(self):
        for face, rd in (('電話', 'でんわ'), ('番号', 'ばんごう'), ('連絡', 'れんらく'), ('一番', 'いちばん')):
            self.assertTrue(K.is_kango(face, rd), face)
        for face, rd in (('玩具', 'おもちゃ'), ('小さい', 'ちいさい'), ('娘', 'むすめ'), ('一つ', 'ひとつ'), ('部屋', 'へや')):
            self.assertFalse(K.is_kango(face, rd), face)

    def test_native_words_stay_kana(self):
        for line in ('おもちゃをかう。', 'ちいさいいえ。', 'ずれがある。'):
            self.assertEqual(self.run_line(line), line, line)

    def test_sino_words_and_loanwords_still_convert(self):
        self.assertEqual(self.run_line('またれんらくします。'), 'また連絡します。')
        self.assertEqual(self.run_line('てれびをみる。'), 'テレビをみる。')


if __name__ == '__main__':
    unittest.main()
