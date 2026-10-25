"""ローマ字入力で、かな・漢字に付いて残った英字に少なくとも紫を付ける（2026-10-23・例文は作った文）"""
import unittest
from tests_analysis_async import initial
from correction_entry import correct_line
import last_keystroke


class LeftoverLetterTests(unittest.TestCase):
    def test_runs_found(self):
        self.assertEqual(last_keystroke._leftover_letter_runs('机のうえにかいgを置いた'), [(7, 8)])
        self.assertEqual(last_keystroke._leftover_letter_runs('昼から仕事g続いた'), [(5, 6)])
        # IME が全角で確定した英字も同じ
        self.assertEqual(last_keystroke._leftover_letter_runs('机のうえにかいｇを置いた'), [(7, 8)])

    def test_english_and_acronyms_are_words(self):
        for line in ('webで調べた', 'urlを貼る', 'PCを使う', '10gbのファイル', '写真.jpgを開く', 'emailを送る',
                     'ｗｅｂで調べた', 'ＰＣを使う', '１０ｇｂのファイル'):
            self.assertEqual(last_keystroke._leftover_letter_runs(line), [], line)

    def test_unfixed_letters_get_purple(self):
        st = initial()
        line = '机のうえにかいgを置いた'
        res = correct_line(line, st.store, context_vocab={}, input_method='romaji', dict_index=st.dict_index,
                           decisions=st.decisions, context_vec=st.context_vec)
        if res['corrected'] == line:
            self.assertTrue(any(a <= 7 < b for a, b in (tuple(x[:2]) for x in res['odd_spans'])))


if __name__ == '__main__':
    unittest.main()
