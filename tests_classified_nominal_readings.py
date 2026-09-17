# -*- coding: utf-8 -*-
"""Existing semantic units need their own native readings, including compounds."""
import unittest
import morphology as M
import reading_segments as R
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('日光'),'requires native dictionary')
class ClassifiedNominalReadingTests(unittest.TestCase):
    def test_exact_native_common_sense_survives_best_parse_proper_name(self):
        self.assertIn('直射日光',R._native_nominal_reading_faces('ちょくしゃにっこう'))
        self.assertTrue(R.native_common_noun_reading('直射日光','ちょくしゃにっこう'))
        self.assertFalse(R.native_common_noun_reading('直射日光','ちょくしゃひかり'))
        self.assertFalse(R.native_common_noun_reading('直射日光','ちょくしゃにこう'))
        self.assertNotIn('資料日光',R._native_nominal_reading_faces('しりょうにっこう'))
        self.assertNotIn('読んで日光',R._native_nominal_reading_faces('よんでにっこう'))

    def test_classified_single_nouns_share_the_existing_usage_index(self):
        from kango_tier import _explicit_reading_faces
        for word,reading in (('蓼','たで'),('筆','ふで'),('湿気','しっけ')):
            with self.subTest(word=word):
                self.assertIn(word,_explicit_reading_faces().get(reading,()))
                self.assertIn(word,R.native_nominal_phrase_faces(reading))

    def test_physical_plant_sense_does_not_invent_edibility_or_a_verb_role(self):
        for word in ('植物','草','葉','茎','根','枝','苗','蓼'):
            with self.subTest(word=word):
                self.assertTrue(S.support(word,'洗う'))
                self.assertTrue(S.support(word,'並べる'))
                self.assertFalse(S.support(word,'食べる'))
                self.assertFalse(S.support(word,'読む'))
        self.assertFalse(S.support('たでる','洗う'))

    def test_initial_application_keeps_real_alternative_nouns_and_compounds(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('たでをにほんあらいます。','はをにまいあらいます。',
                     'くきをさんぼんあらいます。','なえをならべます。',
                     'ちょくしゃにっこうをさけます。',
                     'ちょくしゃにっこうをさけてほかんします。'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],text)
                self.assertEqual(result.get('odd_spans'),[])


if __name__=='__main__':unittest.main()
