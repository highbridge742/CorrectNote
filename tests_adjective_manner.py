# -*- coding: utf-8 -*-
"""A native manner form keeps its verb and object independently accountable."""
from tests_spelling_reference import assert_reviewed_source_spelling
from tests_spelling_reference import assert_repaired_spelling
import unittest
import morphology as M
import reading_segments as R
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('薄く'),'requires native dictionary')
class AdjectiveMannerTests(unittest.TestCase):
    def test_adverbial_edge_requires_exact_native_continuative(self):
        for text,cut in (('うすくきります',3),('ながくきります',3),
                         ('こまかくきります',4),('はやくあるきます',3),
                         ('うすくくきります',3)):
            with self.subTest(text=text):self.assertIn(cut,R.native_adverbial_reading_cuts(text))
        for text,cut in (('うすいきります',3),('うすけれきります',4),
                         ('うすからきります',4),('ぷねらくきります',4)):
            with self.subTest(text=text):self.assertNotIn(cut,R.native_adverbial_reading_cuts(text))

    def test_written_modifier_protects_only_its_own_unknown_host_prefix(self):
        import reading_segments as R
        for text,edge in (('古くてぷねらの道具',3),('かるくてぽねです',4)):
            spans=R.native_adnominal_modifier_ranges(text)
            self.assertIn((0,edge),spans)
            self.assertFalse(any(a<edge<b for a,b in spans))
        import ime_missing_shift as I,corrector as C
        from tests_analysis_async import initial
        a=initial();tk=C.make_tokenizer(a.store)
        self.assertFalse(I._written_multi_noun_case('列平均を計算する',tk))
        self.assertFalse(R.native_written_nominal_ranges('画面繁栄'))

    def test_original_manner_does_not_split_into_internal_function_words(self):
        import pos_grammar as P
        for text in ('ながくきくります','ぬのをながくきくります','こまかくきくります'):
            self.assertFalse(P.explain_kana_run(text,bare_head=True),text)
        for text in ('ながくきります','ぬのをながくきります','うすくすります'):
            self.assertTrue(P.explain_kana_run(text,bare_head=True),text)

    def test_vegetable_and_cutting_roles_are_shared_but_not_homophones(self):
        for noun in ('玉葱','たまねぎ','人参','大根','キャベツ'):
            with self.subTest(noun=noun):
                self.assertTrue(S.nominal_roles(noun)&{'food','ingredient'})
                self.assertTrue(S.candidate_support(noun,'切ります',''))
        self.assertFalse(S.candidate_support('玉葱','着ます',''))
        self.assertFalse(S.candidate_support('お茶','切ります',''))

    def test_completed_predicate_and_original_object_are_still_required(self):
        for text,cut,faces in (('たまねぎをうすくきります',5,('玉葱',)),
                               ('ぬのをながくきります',3,('布',)),
                               ('かみをこまかくきります',3,('紙',))):
            with self.subTest(text=text):self.assertTrue(R.native_object_predicate_proof(text,cut,faces))
        for text,cut,faces in (('おちゃをうすくきります',4,('お茶',)),
                               ('たまねぎをうすいきります',5,('玉葱',)),
                               ('たまねぎをうすくきるよみます',5,('玉葱',)),
                               ('たまねぎをうすくぷねらます',5,('玉葱',))):
            with self.subTest(text=text):self.assertFalse(R.native_object_predicate_proof(text,cut,faces))

    def test_intrusion_is_removed_with_original_manner_and_object_intact(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for old,new in (('たまねぎをうすくきくります。','たまねぎをうすくきります。'),
                        ('ぬのをながくきくります。','ぬのをながくきります。')):
            with self.subTest(text=old):
                result=app.correct_line(old,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                assert_repaired_spelling(self, result, new)
                self.assertEqual(result.get('odd_spans'),[])

    def test_correct_source_and_ambiguous_native_actions_are_preserved(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('たまねぎをうすくきります。','たまねぎをうすくすります。',
                     'たまねぎをうすくかります。','かみをこまかくきります。',
                     'ぬのをながくきります。'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                assert_reviewed_source_spelling(self, result['corrected'], text)
                self.assertEqual(result.get('odd_spans'),[])


@unittest.skipUnless(M.dictionary_inflections('薄く'),'requires native dictionary')
class AdjectiveHostBoundaryTests(unittest.TestCase):

    def test_geminated_continuative_needs_its_actual_connective(self):
        for text,cut in (('おぞくったべます',4),('うすくっきります',4),
                         ('はやくっあるきます',4)):
            self.assertFalse(R.native_adjective_adverbial_prefix(text,cut))
            self.assertNotIn(cut,R.native_adverbial_reading_cuts(text))
        self.assertTrue(R.native_adjective_adverbial_prefix('おぞくたべます',3))
        import app
        from tests_analysis_async import initial
        a=initial()
        text='りょうりをつくっておぞくとたべました。'
        result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        # AJE also supplies the original frame's comitative person role.
        assert_repaired_spelling(self, result, 'りょうりをつくってかぞくとたべました。')
        self.assertEqual(result.get('odd_spans'),[])


    def test_manner_does_not_certify_an_unrelated_nominal_clause(self):
        self.assertFalse(R.native_adverbial_predicate_reading('こくつりがありました'))
        self.assertFalse(R.native_adverbial_predicate_reading('うすくほんです'))
        self.assertTrue(R.native_adverbial_predicate_reading('こくいれます'))
        self.assertTrue(R.native_adverbial_predicate_reading('うすくきります'))
        self.assertTrue(R.native_adverbial_predicate_reading('ゆっくりほんをよみます'))

    def test_preexisting_typo_and_native_word_are_both_retained(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text,expected in (('こくつりがありました。','国立がありました。'),
                ('こくいれます。','こくいれます。'),
                ('はやくうちにかえります。','はやくうちにかえります。'),
                ('うすくおちゃをいれます。','うすくおちゃをいれます。')):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], expected)


if __name__=='__main__':unittest.main()
