# -*- coding: utf-8 -*-
"""漢字の名詞のすぐ後ろにかなのまま残った接尾の語に漢字を置く（noun_suffix・2026-10-31）。作った文だけ。"""
import unittest
from tests_analysis_async import initial
import noun_suffix as N
import correction_entry as CE


class NounSuffixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = initial()

    def places(self, line):
        return N._places(line, self.st.store, self.st.dict_index)

    def test_suffix_after_noun_gets_kanji(self):
        self.assertEqual(self.places('いま会議ちゅうです。'), [(4, 7, '中')])
        self.assertEqual(self.places('計画てきに進める。'), [(2, 4, '的')])
        self.assertEqual(self.places('会議ちゅうなので後で。'), [(2, 5, '中')])

    def test_suffix_usually_written_in_kana_is_left(self):
        # かなで書くのが普通の接尾は、漢字にすると行の自然さが下がる
        for line in ['学生たちが来た。', '来週ごろに行く。', '三日ほど休む。', '世界じゅうで人気がある。',
                     '先生がたが集まった。', '人ごとに決める。']:
            self.assertEqual(self.places(line), [], line)

    def test_typo_of_particle_or_verb_ending_is_not_a_suffix(self):
        # 1字の読み（雨か・精算き）や、動詞の後ろの形（利用てきません）は接尾の語ではない
        for line in ['朝から雨か降っていた。', '出張の精算き経理に出す。', '明日は利用てきません。']:
            self.assertEqual(self.places(line), [], line)

    def test_char_joining_noun_into_dictionary_word(self):
        # 名詞の読みとつなぐと辞書の1語になる字（乗車＋けん → 乗車券）
        self.assertEqual(self.places('駅で乗車けんを買う。'), [(4, 6, '券')])

    def test_whole_line(self):
        st = self.st
        r = CE.correct_line('作業ちゅうに電話が来た。', st.store, context_vocab={}, input_method='kana',
                            dict_index=st.dict_index, decisions=st.decisions, context_vec=st.context_vec)
        self.assertEqual(r['corrected'], '作業中に電話が来た。')
        self.assertEqual(r['original'], '作業ちゅうに電話が来た。')


if __name__ == '__main__':
    unittest.main()
