# -*- coding: utf-8 -*-
"""Identical base spelling does not mean identical native conjugation."""
from tests_spelling_reference import assert_reviewed_source_spelling
import unittest
import morphology as M
import reading_segments as R
import contextual_repair as C


@unittest.skipUnless(M.dictionary_paradigms('する'),'requires native dictionary')
class SuruParadigmTests(unittest.TestCase):
    def test_sahen_and_potential_forms_retain_their_actual_paradigms(self):
        for surface,form,reading in (('し','連用形','し'),('する','基本形','する'),
                                     ('すれ','仮定形','すれ'),('でき','連用形','でき'),
                                     ('出来る','基本形','できる')):
            with self.subTest(surface=surface):self.assertTrue(M.native_suru_form(surface,form,reading))
        for surface,form,reading in (('すり','連用形','すり'),('すら','未然形','すら'),
                                     ('刷り','連用形','すり'),('摺り','連用形','すり'),
                                     ('し','基本形','し'),('し','連用形','すり')):
            with self.subTest(surface=surface):self.assertFalse(M.native_suru_form(surface,form,reading))
        self.assertFalse(M.native_suru_form('でき','連用形','でき',False))

    def test_action_object_and_sahen_attachment_share_the_same_form(self):
        for text in ('さぎょうをすりました','さぎょうをすらない','さぎょうすりました'):
            with self.subTest(text=text):
                self.assertFalse(R.completed_native_reading_clause(text,True,True,True))
                self.assertFalse(R.completed_sahen_reading(text,True))
        for text in ('さぎょうをしました','さぎょうをします','さぎょうをしない'):
            with self.subTest(text=text):self.assertTrue(R.completed_native_reading_clause(text,True,True,True))
        self.assertFalse(R.native_resultative_reading('ちいさくすります',('音',),True))
        self.assertTrue(R.native_resultative_reading('ちいさくします',('音',),True))
        self.assertFalse(C._native_manner_predicate('よむようにすります','よむ'))
        self.assertTrue(C._native_manner_predicate('よむようにします','よむ'))

    def test_bare_sahen_head_cannot_borrow_a_bound_verb_or_connector(self):
        for tail in ('れています','れて','れば','きました','てました','すました','れました'):
            with self.subTest(tail=tail):self.assertFalse(C._productive_predicate('確認'+tail,'確認'))
        for tail in ('されて','すれば','しました','です','だ','しない','せず','できる'):
            with self.subTest(tail=tail):self.assertTrue(C._productive_predicate('確認'+tail,'確認'))

    def test_godan_rubbing_and_printing_are_still_native_verbs(self):
        for text in ('すります','すりました','刷りました','擦りました'):
            with self.subTest(text=text):self.assertTrue(C._productive_predicate(text,M.tokenize(text)[0].surface))

    def test_te_auxiliary_needs_its_actual_attachment_and_origin(self):
        import semantic_roles as S
        for surface in ('保存してたれない','保存してでない'):
            self.assertFalse(C._productive_predicate(surface,'保存'),surface)
        for surface in ('保存しておけない','保存してみせます','保存していただきます',
                        '保存してくださいます','保存していない','保存してた'):
            self.assertTrue(C._productive_predicate(surface,'保存'),surface)
        self.assertNotIn('process',S.native_verb_roles('すれ','連用形','すれ',tail='ました'))
        self.assertIn('text',S.native_verb_roles('読め','連用形','よめ',tail='ます'))

    def test_application_does_not_use_the_godan_homograph_as_suru(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        text='さぎょうをありました。'
        result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        assert_reviewed_source_spelling(self, result['corrected'], text)
        self.assertTrue(result.get('odd_spans'))
        for text in ('作業をしました。','ごまをすりました。','版画を刷りました。'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],text)
                self.assertEqual(result.get('odd_spans'),[])


if __name__=='__main__':unittest.main()
