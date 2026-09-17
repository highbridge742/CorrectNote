# -*- coding: utf-8 -*-
"""Focus particles retain the original request and its argument reading."""
import unittest
import morphology as M
import contextual_repair as C
import reading_segments as R
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('する'),'requires native dictionary')
class FocusedRequestContextTests(unittest.TestCase):
    def test_native_focus_attachment_and_imperative_share_one_proof(self):
        for text,head in (('してもください','し'),('書いてもください','書い'),
                          ('読んではください','読ん'),('保存してもください','保存')):
            with self.subTest(text=text):
                first=M.tokenize(text)[0]
                self.assertTrue(C._native_focused_te_forms(text,head))
                self.assertTrue(C._allows_grammatical_tail(M.dictionary_inflections(head),text[len(head):],first.reading,head))
                self.assertTrue(C._productive_predicate(text,head))
                parts=[(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,t.has_reading,t.infl_form) for t in M.tokenize(text)]
                self.assertTrue(R._native_request_tail(parts))
        for text,head in (('読むてもください','読む'),('書いでもください','書い'),
                          ('飲みでもください','飲み'),('してももください','し'),
                          ('してはもください','し'),('未知てもください','未知')):
            with self.subTest(text=text):self.assertFalse(C._native_focused_te_forms(text,head))

    def test_auxiliary_word_is_not_misread_as_an_intervening_particle(self):
        self.assertEqual(C._native_focused_te_forms('読んでもらいます','読ん'),())
        self.assertTrue(C._productive_predicate('読んでもらいます','読ん'))
        self.assertEqual(C._native_focused_te_forms('読んでもう一度考えます','読ん'),())
        self.assertEqual(C._native_focused_te_forms('読んでも','読ん'),())

    def test_response_words_have_native_readings_without_selecting_a_homophone(self):
        self.assertIn('感想',R._native_nominal_reading_faces('かんそう'))
        self.assertIn('乾燥',R._native_nominal_reading_faces('かんそう'))
        self.assertIn('完走',R._native_nominal_reading_faces('かんそう'))
        for word in ('感想','見解','批評','論評','レビュー'):
            with self.subTest(word=word):self.assertTrue(S.support(word,'書く'))
        self.assertFalse(S.support('乾燥','書く'))
        self.assertFalse(S.support('完走','飲む'))

    def test_application_keeps_focus_and_normal_homophone_meanings(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        normal=('あたらしいせっていをほぞんしてもください。',
                'このほんをよんでもください。','ふぁいるをほぞんしてはください。',
                'かんそうをかいてもください。','感想を書きます。',
                '本を読んではいます。','文字を入力してもらいます。',
                'しりょうをよんでもらいました。','衣服を乾燥します。',
                'マラソンを完走します。','私は「してもください」と書きました。')
        for text in normal:
            with self.subTest(text=text):
                r=app.correct_line(text,a.store,dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions,input_method='kana')
                self.assertEqual(r['corrected'],text)
                self.assertEqual(r['odd_spans'],[])


if __name__=='__main__':unittest.main()
