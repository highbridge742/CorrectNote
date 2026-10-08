# -*- coding: utf-8 -*-
"""Short native genitives and locative nouns retain their own readings."""
from tests_spelling_reference import assert_reviewed_source_spelling
from tests_spelling_reference import assert_repaired_spelling
import unittest
import morphology as M
import reading_segments as R
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('する'),'requires native dictionary')
class SpatialNominalContextTests(unittest.TestCase):
    def test_one_kana_native_noun_uses_the_same_genitive_connection(self):
        for text,head in (('きのはこ','箱'),('めのいろ','色'),('てのかたち','形')):
            with self.subTest(text=text):self.assertIn(head,R.native_nominal_phrase_faces(text))
        for text in ('しらゆほのはこ','きのしらゆほ','きののはこ'):
            with self.subTest(text=text):self.assertFalse(R.native_nominal_phrase_faces(text))

    def test_projected_genitive_keeps_both_whole_nouns_and_source_word_ownership(self):
        for phrase,head,tail in (('きのはこ','箱','を置きます。'),
                                 ('まどのちかく','近く','に置きます。'),
                                 ('まどのそと','外','を見ます。'),
                                 ('えきまえのみせ','店','で買います。'),
                                 ('昨日のせれくしょん','セレクション','を見ました。')):
            for context in (None,phrase+tail):
                with self.subTest(phrase=phrase,context=context):
                    splits=R.native_genitive_nominal_splits(phrase,original_context=context)
                    self.assertTrue(any(head in right for cut,left,right in splits))
                    self.assertTrue(all(left and right for cut,left,right in splits))
        source='会議のしはょ類を送信します。'
        self.assertEqual(R.native_genitive_nominal_splits('会議のし',original_context=source),())
        self.assertEqual(R.native_surface_nominal_heads('会議のし',original_context=source),())
        for phrase in ('きのこ','ものさし','いのしし','ぷねらのはこ','きのぷねら'):
            self.assertFalse(R.native_genitive_nominal_splits(phrase),phrase)
        self.assertFalse(R.native_genitive_nominal_splits('会議のし',original_context='資料の本'))

    def test_locative_readings_do_not_lend_their_role_to_a_written_homophone(self):
        self.assertIn('近く',R._native_nominal_reading_faces('ちかく'))
        for word in ('近く','付近','近所','辺り','そば','脇'):
            with self.subTest(word=word):self.assertIn('place',S.nominal_roles(word))
        for word in ('地殻','知覚','蕎麦'):
            with self.subTest(word=word):self.assertNotIn('place',S.nominal_roles(word))

    def test_original_normal_clauses_and_adjacent_intrusion(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        def correct(text):return app.correct_line(text,a.store,dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions,input_method='kana')
        for text in ('きのはこをそこにおきます。','きのはこをまどのちかくにおきます。',
                     'このはこをまどのちかくにおきます。','めのいろをみます。',
                     'てのかたちをかきます。','はのかたちをかきます。',
                     '地殻を調べます。','知覚を調べます。','そばをたべます。'):
            with self.subTest(text=text):
                r=correct(text)
                assert_reviewed_source_spelling(self, r['corrected'], text);self.assertEqual(r['odd_spans'],[])
        source='きのはこをまどのちかくにおきまくす。'
        expected='きのはこをまどのちかくにおきます。'
        from kana_layout import single_key_drop_adjacency,single_key_drop_is_duplicate
        self.assertTrue(single_key_drop_adjacency(source,expected))
        self.assertFalse(single_key_drop_is_duplicate(source,expected))
        result=correct(source)
        assert_repaired_spelling(self, result, expected);self.assertEqual(result['odd_spans'],[])


if __name__=='__main__':unittest.main()
