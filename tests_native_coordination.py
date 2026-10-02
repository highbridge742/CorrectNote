# -*- coding: utf-8 -*-
"""Native coordination retains every member and their shared argument roles."""
from tests_spelling_reference import assert_repaired_spelling
import unittest
import morphology as M
import reading_segments as R
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('玉葱'),'requires native dictionary')
class NativeCoordinationTests(unittest.TestCase):
    def test_actual_ordinary_nouns_and_coordinating_particle(self):
        for text,parts in (
            ('たまねぎとにんじん',('たまねぎ','にんじん')),
            ('玉葱と人参',('玉葱','人参')),
            ('野菜と果物と肉',('野菜','果物','肉')),
        ):
            self.assertEqual(R.native_coordinated_nominal_parts(text),parts)
        for text in ('おとうと','いと','たまねぎと','とにんじん',
                     'たまねぎやにんじん','たまねぎとぷねら','太郎と花子',
                     'たまねぎ とにんじん','「たまねぎ」とにんじん',
                     '読むと書く','たまねぎとにんじんを'):
            self.assertFalse(R.native_coordinated_nominal_parts(text),text)

    def test_each_member_must_support_the_argument_role(self):
        for text in ('たまねぎとにんじん','玉葱と人参','野菜と果物と肉'):
            self.assertIn('food',S.nominal_roles(text),text)
        self.assertNotIn('food',S.nominal_roles('野菜と精度'))
        self.assertNotIn('food',S.nominal_roles('精度と野菜'))
        self.assertNotIn('food',S.nominal_roles('野菜と果物と精度'))
        self.assertTrue(R.native_object_predicate_proof(
            'たまねぎとにんじんをこまかくきります',10,('たまねぎとにんじん',)))
        self.assertFalse(R.native_object_predicate_proof(
            '野菜と精度を食べます',6,('野菜と精度',)))

    def test_candidate_keeps_all_original_members(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for noun in ('たまねぎとにんじん','玉葱と人参','野菜と果物','布と紙','ぬのとかみ'):
            text=noun+'をこまかくきすります。'
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_repaired_spelling(self, result, noun+'をこまかくきります。')
            self.assertEqual(result.get('odd_spans'),[],text)

    def test_complete_kana_nouns_keep_their_original_ranges(self):
        for text,expected in (
            ('ぬのとかみ',('ぬの','かみ')),
            ('さとうとしお',('さとう','しお')),
            ('とまととにんじん',('とまと','にんじん')),
            ('いととぬの',('いと','ぬの'))):
            self.assertEqual(R.native_coordinated_nominal_parts(text),expected)
        for text in ('おとうと','いと','きょうと','さとし','かくとよむ',
                     'ぷねらとかみ','ぬのとぷねら','とぬの','ぬのと'):
            self.assertFalse(R.native_coordinated_nominal_parts(text),text)

    def test_different_roles_must_each_fit_the_same_action(self):
        for noun,verb in (('布と紙','切る'),('ぬのとかみ','切る'),
                          ('野菜と資料','送る')):
            self.assertTrue(S.support(noun,verb),(noun,verb))
        for noun,verb in (('野菜と精度','切る'),('紙と精度','切る'),
                          ('布と紙','食べる'),('紙と布','読む')):
            self.assertFalse(S.support(noun,verb),(noun,verb))
        evidence=S.candidate_evidence('布と紙','切り','ます')
        self.assertEqual(set(evidence['shared_roles']),{'object','writing_surface'})
        evidence=S.candidate_evidence('野菜と精度','食べ','ます')
        self.assertFalse(evidence and evidence['shared_roles'])
        self.assertTrue(R.native_object_predicate_proof('ぬのとかみをこまかくきります',6,('ぬのとかみ',)))
        self.assertFalse(R.native_object_predicate_proof('野菜と精度をこまかくきります',6,('野菜と精度',)))

    def test_normal_actions_and_explicit_examples_stay_literal(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('たまねぎとにんじんをこまかくきります。',
                     'たまねぎとにんじんをこまかくすります。',
                     '野菜と果物を買います。','弟と図書館に行きます。',
                     '糸と布を切ります。','友達と資料を読みます。',
                     '「たまねぎとにんじんをこまかくきすります」という誤入力例です。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            self.assertEqual(result.get('odd_spans'),[],text)


    def test_inferred_members_keep_independent_readings(self):
        # A one-kana noun is valid. The issue is independent lexical use,
        # not word length or an absent semantic category.
        for text,parts in (('きといし',('き','いし')),
                           ('まとかみ',('ま','かみ')),
                           ('かみとぬのとき',('かみ','ぬの','き')),
                           ('わえいとやくたい',('わえい','やくたい'))):
            self.assertEqual(R.native_coordinated_nominal_parts(text),parts,text)
        self.assertTrue(M.dictionary_inflections('外'))
        self.assertIn('外',R._native_nominal_reading_faces('がい'))
        for text in ('まとがい','しょとがい','ぬのとがい'):
            self.assertFalse(R.native_coordinated_nominal_parts(text),text)
            self.assertFalse(R.native_nominal_phrase_faces(text),text)
        # Written lexical choices keep their actual independent reading.
        self.assertEqual(R.native_coordinated_nominal_parts('魔と外'),('魔','外'))
        self.assertEqual(R.native_coordinated_nominal_parts('まとそと'),('ま','そと'))

    def test_partial_spellings_preserve_each_native_member(self):
        for text,parts in (('ぬのと紙',('ぬの','紙')),('布とかみ',('布','かみ')),
                           ('かみと布',('かみ','布')),('紙とぬの',('紙','ぬの'))):
            self.assertEqual(R.native_coordinated_nominal_parts(text),parts)
        for text in ('ぷねらと紙','布とぷねら','ぬのと太郎','布\tとかみ','布と「かみ」'):
            self.assertFalse(R.native_coordinated_nominal_parts(text),text)

    def test_spelling_keeps_original_argument_meaning_across_manner(self):
        from unittest.mock import patch
        import app,corrector as C
        from tests_analysis_async import initial
        a=initial();tok=C.make_tokenizer(a.store)
        text='布とかみをこまかくきります'
        with patch('last_choice.surface_for_reading',return_value=None):
            for face in ('紙','髪'):
                proof=S.candidate_nominal_spelling_evidence('布と',face,'をこまかくきります')
                self.assertTrue(proof and proof['shared_roles'])
                accepted,reason=C._check_replacement(text,(2,4,face,'かな入力'),a.store,tok,
                    a.dict_index,a.decisions,conv_taken=((2,4),),spelling=True)
                self.assertIsNotNone(accepted,(face,reason))
            self.assertIsNone(S.candidate_nominal_spelling_evidence('布と','神','をこまかくきります'))
            accepted,reason=C._check_replacement(text,(2,4,'神','かな入力'),a.store,tok,
                a.dict_index,a.decisions,conv_taken=((2,4),),spelling=True)
            self.assertIsNone(accepted)
            self.assertEqual(reason,'original_nominal_argument_meaning')
        # An explicit choice owns its spelling, even outside this role inventory.
        with patch('last_choice.surface_for_reading',return_value='神'):
            self.assertTrue(S.preserves_nominal_spelling_argument(text,2,4,'神'))
        for tail in ('を。切ります','を\t切ります','を「切ります」','を考え、紙を切ります'):
            self.assertIsNone(S.candidate_nominal_spelling_evidence('布と','紙',tail),tail)

    def test_spelling_finishes_both_orders_without_rewriting_normal_senses(self):
        import app
        from tests_analysis_async import initial
        a=initial();revision=a.store.revision()
        for text,expected in (
            ('ぬのとかみをこまかくきすります。','布と紙をこまかく切ります。'),
            ('かみとぬのをこまかくきすります。','紙と布をこまかく切ります。')):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],expected)
            self.assertFalse(result.get('odd_spans'))
        for text in ('布と髪を切ります。','髪と布を切ります。',
                     '神と仏を信じます。','ぬのとかみをこまかくきります。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            self.assertFalse(result.get('odd_spans'))
        self.assertEqual(a.store.revision(),revision)

if __name__=='__main__':unittest.main()
