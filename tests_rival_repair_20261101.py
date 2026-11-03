# -*- coding: utf-8 -*-
"""前の段が1打で直した語を、ほかの1打の戻しと例文の組で比べ直す（rival_repair・2026-11-01）。作った文だけ。"""
import unittest
from tests_analysis_async import initial
import rival_repair as R
import correction_entry as CE


class RivalRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = initial()

    def test_neighbour_key_beats_dropped_mark(self):
        # じゅう｜だん（た を隣のキーに打った＋゛）: ゛を抜く（じゅうたん）より、隣のキーを戻した 充電 が例文の組（〜する）に多い
        self.assertEqual(R.propose('じゅうだんした', 'じゅうたんした'), [(0, 5, '充電')])
        self.assertEqual(R.propose('昨日そうでんした', '昨日そうてんした'), [(2, 6, '相談')])

    def test_converted_answer_is_also_compared(self):
        # 前の段が漢字まで置いた答えでも、打った読みから比べ直す
        got = R.repair_line('じゅうだんした', {'corrected': 'じゅうたんした', 'odd_spans': []})
        self.assertEqual(got['corrected'], '充電した')

    def test_unchanged_typed_word_is_not_touched(self):
        # 前の段が読みを替えていない語（打ったままの語に漢字を置いただけ）は見ない
        self.assertEqual(R.propose('しっこうされた', '失効された'), [])
        self.assertEqual(R.propose('会議を開いた', '会議を開いた'), [])

    def test_mid_word_split_is_not_replaced(self):
        # 行頭のかな1字を助詞と見誤った区切り（て＋いそ）の語の途中は替えない
        self.assertEqual(R.propose('ていぞした', 'ていそした'), [])

    def test_only_kana_input(self):
        res = {'corrected': 'じゅうたんした', 'odd_spans': []}
        self.assertIs(R.repair_line('じゅうだんした', res, input_method='romaji'), res)

    def test_correct_lines_untouched(self):
        st = self.st
        for line in ['充電した', '相談した', '絨毯を敷いた', '展示された', '会議を開いた']:
            r = CE.correct_line(line, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                                decisions=st.decisions, context_vec=st.context_vec)
            self.assertEqual(r['corrected'], line, line)


if __name__ == '__main__':
    unittest.main()
