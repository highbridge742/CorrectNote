# -*- coding: utf-8 -*-
"""2026-11-08 補正担当: 小さい母音の Shift の押し違い（CN_SMALL_VOWEL_SLIP）・長い紫の頭を外した読み直し
（CN_RESPELL_SHRINK）・頼みの言い切り（CN_FIX_HONORIFIC_IMPERATIVE）・どんな物でも取る動詞の組（CN_FRAME_GUARD_BROAD）。"""
import os
import tempfile
import unittest

from tests_analysis_async import initial
import vocabulary
import correction_entry as CE


class SmallSlip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = initial()
        cls.st.store = vocabulary.open_vocabulary(os.path.join(tempfile.mkdtemp(), 'vocabulary.json'))

    def fix(self, line):
        st = self.st
        return CE.correct_line(line, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                               decisions=st.decisions, context_vec=st.context_vec)

    def test_small_vowel_slip(self):
        self.assertEqual(self.fix('か゛いこくのりよぅりをたべた。')['corrected'][:6], '外国の料理を')

    def test_honorific_imperative_alone(self):
        self.assertEqual(self.fix('くたせさい')['corrected'], 'ください')

    def test_long_purple_shrink(self):
        self.assertEqual(self.fix('自動で直るようにしてくたせさい。')['corrected'], '自動で直るようにしてください。')

    def test_broad_verb_frame(self):
        self.assertEqual(self.fix('かーそねを持って行った')['corrected'], 'カーソルを持って行った')

    def test_head_merged_not_joined(self):
        st = self.st
        g = CE.correct_line('がいとうあのはんいを', st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                            decisions=st.decisions, context_vec=st.context_vec, previous_line='この番号を')
        self.assertEqual(g['corrected'], '該当の範囲を')

    def test_switches_off(self):
        os.environ['CN_SMALL_VOWEL_SLIP'] = '0'
        try:
            self.assertNotEqual(self.fix('か゛いこくのりよぅりをたべた。')['corrected'][:6], '外国の料理を')
        finally:
            os.environ.pop('CN_SMALL_VOWEL_SLIP')


if __name__ == '__main__':
    unittest.main()
