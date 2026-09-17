# -*- coding: utf-8 -*-
"""A productive nominal prefix is not an extra adjacent key by itself."""
import unittest
import morphology as M
import semantic_roles as S
import corrector as C
import oddness as O


@unittest.skipUnless(M.dictionary_inflections('画像'),'requires native dictionary')
class UnadornedPrefixTests(unittest.TestCase):
    def test_prefix_grammar_uses_native_common_hosts_without_word_pairs(self):
        for text in ('素画像','素写真','素文章','素データ','素うどん','素顔'):
            with self.subTest(text=text):self.assertTrue(S.unadorned_nominal_prefix_parts(text))
        for text in ('素','素帰任','素しらゆほ','素読む','素東京','素画像で','素 画像'):
            with self.subTest(text=text):self.assertIsNone(S.unadorned_nominal_prefix_parts(text))
        self.assertTrue(O.can_join('素','名詞:一般','画像','名詞:一般'))

    def test_same_evidence_reaches_intact_and_shared_final_check(self):
        from tests_analysis_async import initial
        a=initial();tk=C.make_tokenizer(a.store)
        self.assertTrue(C._chunk_is_intact('素画像',tk))
        for start,end,candidate in ((0,1,''),(0,3,'画像'),(0,10,'画像を保存します。')):
            with self.subTest(start=start,end=end):
                accepted,reason=C._check_replacement('素画像を保存します。',
                    (start,end,candidate,'かな入力'),a.store,tk,a.dict_index,a.decisions)
                self.assertIsNone(accepted)
                self.assertEqual(reason,'completed_nominal_prefix')

    def test_a_following_typo_remains_editable(self):
        self.assertTrue(S.preserves_unadorned_nominal_prefix('素画像を保存しなす。','素画像を保存します。'))
        self.assertFalse(S.preserves_unadorned_nominal_prefix('素画像を保存しなす。','画像を保存します。'))
        self.assertEqual(S.unadorned_nominal_prefix_ranges('まず素画像を保存します。'),((2,5),))

    def test_internal_prefix_fragment_does_not_block_a_whole_word_repair(self):
        for text in ('イン素刷してください。','剣素柵結果を見ます。'):
            with self.subTest(text=text):self.assertEqual(S.unadorned_nominal_prefix_ranges(text),())
        for old,new in (('イン素刷してください。','印刷してください。'),
                        ('剣素柵結果を見ます。','検索結果を見ます。')):
            with self.subTest(text=old):self.assertTrue(S.preserves_unadorned_nominal_prefix(old,new))
        for prefix in ('この','新しい','処理前の','まず','「'):
            with self.subTest(prefix=prefix):
                self.assertTrue(S.unadorned_nominal_prefix_ranges(prefix+'素画像を保存します。'))

    def test_initial_application_keeps_text_and_does_not_leave_false_purple(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('素画像を保存します。','素画像を処理します。','素写真を見ます。',
                     '素データを保存します。','素うどんを食べます。','素顔を見せます。'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],text)
                self.assertEqual(result.get('odd_spans'),[])


if __name__=='__main__':unittest.main()
