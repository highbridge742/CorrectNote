import unittest
from unittest.mock import patch
import corrector as C
import ime_inverse_gate as I
from tests_analysis_async import initial


class StackedFinalParticleTests(unittest.TestCase):
    """文末の終助詞が重なる文（〜かな・〜よね）も、書かれた文として通る。

    逆読みが「かなの並びが異様」と見ても、原文の述語が成り立っていれば
    IME に読みを聞かない（2026-10-20・文字列→文字連れ の誤判定）。
    """
    @classmethod
    def setUpClass(cls):
        cls.state=initial()
        cls.tokenize=staticmethod(C.make_tokenizer(cls.state.store))

    def test_finite_predicate_with_stacked_final_particles_is_intact(self):
        for source in ('文字列一致は特に気にしないかな','行番号表示は特に要らないよね',
                       '画面表示はもう少し大きくしたいかな'):
            with self.subTest(source=source),patch('ime_language.JapaneseIME') as ime,patch('ime_candidates.SearchCandidates') as search:
                self.assertEqual(I.anomalous_source_fields(source,self.tokenize,self.state.store,self.state.dict_index),())
                ime.assert_not_called();search.assert_not_called()

    def test_a_single_final_particle_still_counts(self):
        with patch('ime_language.JapaneseIME') as ime,patch('ime_candidates.SearchCandidates') as search:
            self.assertEqual(I.anomalous_source_fields('明日は駅前の本屋に寄るか',self.tokenize,self.state.store,self.state.dict_index),())
            ime.assert_not_called();search.assert_not_called()

    def test_an_independent_source_mark_still_opens_the_field(self):
        with patch('ime_language.JapaneseIME') as ime,patch('ime_candidates.SearchCandidates') as search:
            ime.return_value.__enter__.return_value.available=False
            search.return_value.__enter__.return_value.available=False
            I.anomalous_source_fields('駅前の本屋に寄るかな',self.tokenize,self.state.store,
                                     self.state.dict_index,source_marks=((0,2),))
            ime.assert_called_once()


if __name__=='__main__':
    unittest.main()
