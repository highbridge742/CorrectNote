# -*- coding: utf-8 -*-
"""Native negative degree expressions retain source form and argument meaning."""
import unittest
import morphology as M
import reading_segments as R
import contextual_repair as C


@unittest.skipUnless(M.dictionary_inflections('する'), 'requires native dictionary')
class NegativeDegreeContextTests(unittest.TestCase):
    def test_exact_negative_inflections_and_copular_connection(self):
        for text in ('のまなすぎます','しなさすぎます','面白くなさすぎます',
                     '静かでなさすぎます','しずかじゃなさすぎます',
                     '元気ではなさすぎました','読まなさ過ぎます'):
            with self.subTest(text=text): self.assertTrue(R.native_degree_expression(text))
        for text in ('読むなさすぎます','高いなさすぎます','静かななさすぎます',
                     '未知っぽいでなさすぎます','しなさすぎ','しなさすぎますです',
                     'しなさすぎまいです','面白くなさすぎますです'):
            with self.subTest(text=text): self.assertFalse(R.native_degree_expression(text))

    def test_object_proof_uses_original_meaning_and_native_action_noun(self):
        for text in ('おちゃをのまなすぎます','このおちゃをのまなすぎます',
                     'しごとをしなさすぎます','仕事をしなすぎます',
                     'この本を読まなさすぎます'):
            with self.subTest(text=text):self.assertTrue(R.completed_written_object_clause(text))
        for text in ('お茶を読まなさすぎます','ほんをのまなさすぎます',
                     'はこをしなさすぎます','みずしなさすぎます',
                     '未知のをしなさすぎます','しごとをしなさすぎますです'):
            with self.subTest(text=text):self.assertFalse(R.completed_written_object_clause(text))

    def test_source_ranges_do_not_cover_other_clauses_or_invalid_suffixes(self):
        text='今日は、おちゃをのまなすぎます。未知っぽいなさすぎます。'
        self.assertEqual(R.native_degree_context_ranges(text),((4,15),))
        self.assertEqual(R.native_degree_context_ranges('しごとをしなさすぎますです'),())
        self.assertFalse(C._productive_predicate('すぎまいです','すぎ'))
        self.assertTrue(C._productive_predicate('すぎますまい','すぎ'))

    def test_application_keeps_normal_text_without_purple_and_keeps_stop_contract(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for text in ('おちゃをのまなすぎます。','仕事をしなさすぎます。',
                     '高くなさすぎます。','しずかじゃなさすぎます。',
                     '今日は、おちゃをのまなすぎます。',
                     'ほんをよまなさすぎますが、時間はあります。'):
            with self.subTest(text=text):
                r=app.correct_line(text,a.store,dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions,input_method='kana')
                self.assertEqual(r['corrected'],text)
                self.assertEqual(r['odd_spans'],[])
        for text in ('もんじにゅうりょく','もじにゅうりょくく'):
            r=app.correct_line(text,a.store,dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions,input_method='kana')
            self.assertEqual(r['corrected'],text)


if __name__=='__main__': unittest.main()
