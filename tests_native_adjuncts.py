"""Clock/source readings require independently native pieces and semantics."""
import unittest
from unittest.mock import patch
import reading_segments as R
import semantic_roles as S
import morphology as M


class NativeAdjunctTests(unittest.TestCase):
    def tearDown(self):
        R.native_clock_readings.cache_clear()
        R.completed_native_adjunct_clause.cache_clear()
        S._native_temporal_verb_readings.cache_clear()

    def clock_entries(self,word):
        ordinary={'零':'れい','一':'いち','二':'に','三':'さん','四':'よん',
                  '五':'ご','六':'ろく','七':'なな','八':'はち','九':'きゅう','十':'じゅう'}
        if word in ordinary:return (('名詞,数,*,*','*',word,ordinary[word]),)
        if word=='時':return (('名詞,接尾,助数詞,*','*','時','じ'),)
        if word=='半':return (('名詞,一般,*,*','*','半','はん'),)
        if word in ('午前','午後'):return (('名詞,副詞可能,*,*','*',word,{'午前':'ごぜん','午後':'ごご'}[word]),)
        return ()

    def test_clock_uses_numeric_and_counter_entries_with_ordinary_allomorphs(self):
        R.native_clock_readings.cache_clear()
        with patch.object(M,'dictionary_inflections',side_effect=self.clock_entries):
            readings=R.native_clock_readings()
            for rd in ('ごぜんじゅうじ','ごごよじ','ごごしちじ','ごぜんくじはん','にじゅうよじ'):
                self.assertIn(rd,readings)
            for rd in ('ごごにじゅうじ','ごぜんきゅうじゅうじ','じゅうち','ごぜんはん'):
                self.assertNotIn(rd,readings)

    def test_clock_cannot_be_invented_without_a_native_counter(self):
        R.native_clock_readings.cache_clear()
        with patch.object(M,'dictionary_inflections',return_value=()):
            self.assertFalse(R.native_clock_readings())

    def test_point_start_and_duration_cases_are_distinct(self):
        self.assertTrue(S.temporal_case_support('開始','から'))
        self.assertTrue(S.temporal_case_support('開始','までに'))
        self.assertFalse(S.temporal_case_support('開始','まで'))
        self.assertTrue(S.temporal_case_support('終了','に'))
        self.assertFalse(S.temporal_case_support('終了','から'))
        self.assertFalse(S.temporal_case_support('説明','から'))

    def test_native_verb_phase_requires_actual_inflection_and_reading(self):
        forms={'はじまり':(('動詞,自立,*,*','連用形','はじまる','はじまり'),),
               'はじまる':(('動詞,自立,*,*','基本形','はじまる','はじまる'),)}
        with patch.object(M,'dictionary_inflections',side_effect=lambda x:forms.get(x,())), \
             patch.object(S,'_native_temporal_verb_readings',return_value={'はじまる':frozenset(('から','に'))}):
            self.assertTrue(S.temporal_case_support('はじまり','から','連用形','はじまり'))
            self.assertFalse(S.temporal_case_support('はじまり','まで','連用形','はじまり'))
            self.assertFalse(S.temporal_case_support('はじまり','から','未然形','はじまり'))


if __name__=='__main__':unittest.main()
