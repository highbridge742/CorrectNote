# -*- coding: utf-8 -*-
"""Source sahen grammar does not imply a candidate's semantic fitness."""
import unittest
import reading_segments as R
from tests_analysis_async import initial

class SourceSahenPredicateTests(unittest.TestCase):
    def test_attested_sahen_and_full_tail_preserve_original_reading(self):
        for text in ('データをほかんします','項目をさくじょしました',
                     '機器をてんけんします','ほかんしました'):
            with self.subTest(text=text):
                self.assertTrue(R.native_source_predicate_ranges(text))

    def test_source_grammar_does_not_supply_missing_candidate_meaning(self):
        for text,cut,faces in (('データをほかんします',4,('データ',)),
                               ('項目をさくじょしました',3,('項目',))):
            with self.subTest(text=text):
                self.assertTrue(R.native_source_predicate_ranges(text))
                self.assertFalse(R.native_object_predicate_proof(text,cut,faces))

    def test_unknown_head_wrong_attachment_and_extra_tail_are_not_proofs(self):
        for text in ('データをぽねします','データをほかんまし',
                     'データをほかんしますです','データをほかんすりました',
                     'ぽねをほかんします','画像をきをうじしました'):
            with self.subTest(text=text):
                self.assertFalse(R.native_source_predicate_ranges(text))

    def test_actual_source_analysis_has_no_false_repair_or_mark(self):
        import app
        # 機器をてんけんしました。→ 機器を点検しました。 は読みの格子の手（kana_lattice_place・2026-10-25）の働きで、
        # うにさん 10-25 11:58Z「直すのが正」。漢字が1つも無い行（データをほかんします）はかなで書いた行として触らない
        for source,expected in (('データをほかんします。',None),('データをほかんしました。',None),
                                ('項目をさくじょします。',None),('機器をてんけんしました。','機器を点検しました。')):
            with self.subTest(source=source):
                a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions)
                self.assertEqual(r['corrected'],expected or source)
                self.assertEqual(r['odd_spans'],[])
                self.assertEqual(r['analysis_status'],'complete')

    def test_separate_typo_keeps_its_independent_source_anomaly(self):
        import app
        a=initial();r=app.correct_line('データをほかんします。皿をやさねます。',a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions)
        self.assertEqual(r['corrected'],'データをほかんします。皿を重ねます。')
        self.assertEqual(r['odd_spans'],[])

if __name__=='__main__':unittest.main()
