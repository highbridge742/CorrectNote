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

    def test_proved_modifier_does_not_spawn_an_overlapping_lexical_head(self):
        import reading_segments as R,app
        from tests_analysis_async import initial
        for head in ('大きな','小さな'):
            for noun in ('きはゃく室','きぷねら','きれいな部屋'):
                text=head+noun+'を見ます。'
                spans=R.native_adnominal_modifier_ranges(text)
                self.assertIn((0,len(head)),spans)
                self.assertFalse(any(0<a<len(head)<b for a,b in spans),spans)
        self.assertIn((0,2),R.native_adnominal_modifier_ranges('なき人を思います。'))
        source='小さなきはゃく室を掃除します。';expected='小さな客室を掃除します。'
        state=initial()
        result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
            decisions=state.decisions,context_vec=None)
        self.assertEqual(result['corrected'],expected)
        self.assertFalse(result['odd_spans'])
        self.assertEqual(result['analysis_status'],'complete')
        for text in ('小さなきぷねらを見ます。','高くて小さな部屋を見ます。',
                '「小さなきはゃく室」という文字列です。'):
            result=app.correct_line(text,state.store,input_method='kana',dict_index=state.dict_index,
                decisions=state.decisions,context_vec=None)
            self.assertEqual(result['corrected'],text)

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
        text='りょうりをつくってんぞくとたべました。'
        result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        # AJE also supplies the original frame's comitative person role.
        assert_repaired_spelling(self, result, 'りょうりをつくってかぞくとたべました。')
        self.assertEqual(result.get('odd_spans'),[])


    def test_comitative_fixture_retains_old_direction_and_common_gate(self):
        import app,corrector as C,contextual_repair as Q
        from unittest.mock import patch
        from tests_analysis_async import initial
        from last_choice import set_active
        for generator in (Q.key_repairs,Q.nonadjacent_key_repairs,
                          Q.adjacent_shift_key_repairs,Q.neighbor_shift_key_repairs):
            self.assertNotIn('かぞく',{r.reading for r in generator('おぞく')})
        self.assertTrue(any(r.reading=='かぞく' and r.operation=='adjacent_substitution'
                            for r in Q.key_repairs('んぞく')))
        try:
            old='りょうりをつくっておぞくとたべました。';a=initial()
            r=app.correct_line(old,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(r['corrected'],'料理をつくっておぞくとたべました。')
            self.assertTrue(r['odd_spans'])
            self.assertEqual(r['analysis_status'],'complete')
            text='りょうりをつくってんぞくとたべました。'
            for source in ('「'+text+'」と入力します。','料理を作って家族と食べました。'):
                a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(r['corrected'],source)
                self.assertEqual(r['odd_spans'],[])
                self.assertEqual(r['analysis_status'],'complete')
            a=initial()
            with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')):
                r=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
            self.assertEqual(r['corrected'],text)
            self.assertTrue(r['odd_spans'])
        finally:set_active(None)

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
