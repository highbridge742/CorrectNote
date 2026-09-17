# -*- coding: utf-8 -*-
import unittest
import morphology as M
import semantic_roles as S
import reading_segments as R


@unittest.skipUnless(M.dictionary_inflections('処理'),'requires native dictionary')
class ProcessingRoleTests(unittest.TestCase):
    def test_processing_uses_content_roles_without_an_answer_roster(self):
        for noun in ('画像','写真','文章','資料','情報','データ'):
            with self.subTest(noun=noun):
                self.assertTrue(S.support(noun,'処理'))
                self.assertTrue(R.native_object_predicate_proof(noun+'を処理します',len(noun)+1,(noun,)))
        self.assertFalse(S.support('しらゆほ','処理'))

    def test_native_action_compounds_share_the_process_confirmation_role(self):
        for noun in ('作業','処理','会議','画面反映','描画面反映','表示面反映','プレビュー反映','資料保存','画像処理'):
            with self.subTest(noun=noun):self.assertTrue(S.support(noun,'確認'))
        self.assertFalse(S.support('画面繁栄','確認'))
        self.assertTrue(S.changed_nominal_object_allowed('画面繁栄を確認します。','画面反映を確認します。'))
        self.assertFalse(S.changed_nominal_object_allowed('あとで良けれをおくります。','あとで池をおくります。'))

    def test_repaired_compound_keeps_an_independent_quoted_example(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text,expected in (
                ('「画面繁栄」は自然だが、画面繁栄を確認します。','「画面繁栄」は自然だが、画面反映を確認します。'),
                ('描画面繁栄を確認します。','描画面反映を確認します。'),
                ('画像を処理します。','画像を処理します。'),
                ('作業を確認します。','作業を確認します。')):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result.get('odd_spans'),[])


if __name__=='__main__':unittest.main()
