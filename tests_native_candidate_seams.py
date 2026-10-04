"""Original unknown-token cuts may not create a dangling attributive stem."""
import unittest
import corrector as C
import contextual_repair as Q
from tests_analysis_async import initial


class NativeCandidateSeamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = initial()
        cls.tok = staticmethod(C.make_tokenizer(cls.a.store))

    def check(self, source, part, surface):
        start = source.index(part)
        end = start + len(part)
        return C._check_replacement(source, (start, end, surface, 'かな入力'),
            self.a.store, self.tok, self.a.dict_index, conv_taken=((start, end),))

    def test_partial_candidate_cannot_expose_unfinished_native_stem(self):
        for source, part, surface in (
            ('もじにゅうりをく', 'もじにゅうり', '文字に有利'),
            ('もじにゅうりをく', 'もじにゅうりをく', '文字に有利をく'),
            ('子どもにじりょうをくば', 'じりょう', '資料'),
            ('子どもにじりょうをくば', 'じりょうをくば', '資料をくば'),
        ):
            with self.subTest(source=source):
                result, reason = self.check(source, part, surface)
                self.assertIsNone(result)
                self.assertEqual(reason, 'unproven_native_continuation')

    def test_completed_and_original_unfinished_context_keep_existing_permission(self):
        for source, part, surface in (
            ('もじにゅうりをく', 'もじにゅうりをく', '文字入力'),
            ('子どもにじりょうをくばる', 'じりょう', '資料'),
            ('子どもにじりょうを', 'じりょう', '資料'),
            ('じりょうを読み', 'じりょう', '資料'),
            ('じりょうをよんで', 'じりょう', '資料'),
            ('じりょうをよめ', 'じりょう', '資料'),
            ('じりょうをよみまし', 'じりょう', '資料'),
            ('じりょうを確認します。あんじんしました。', 'じりょう', '資料'),
        ):
            with self.subTest(source=source):
                result, reason = self.check(source, part, surface)
                self.assertIsNotNone(result, reason)

    def test_contextual_entry_uses_the_same_final_proof(self):
        source = 'もじにゅうりをく'
        target = Q.RepairTarget(source, 0, 6, 0, len(source), (), False, source[6:])
        self.assertEqual(Q.validate(target, '文字に有利', C, self.tok, self.a.store,
            self.a.dict_index), (False, 'unproven_native_continuation'))


    def test_separate_object_does_not_require_an_earlier_meaning_label(self):
        import app
        for source,expected in (
            ('数をかぞえおたら資料を保存します。','数を数えたら資料を保存します。'),
            ('答えをおしえおたら資料を保存します。','答えを教えたら資料を保存します。'),
            # A marked adjacent intrusion in the later noun, after an independent te-clause.
            ('準備を済ませてほなんを読みます。','準備を済ませて本を読みます。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.a.store,input_method='kana',dict_index=self.a.dict_index)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result['odd_spans'],[])

    def test_grammatical_edge_is_not_a_source_intactness_claim(self):
        from reading_segments import native_object_clause_edges
        for text in ('数を数えたら資料を保存します。','準備を済ませて学生を呼びます。'):
            self.assertTrue(native_object_clause_edges(text),text)
        for text in ('数を数えんたら資料を保存します。','準備を済ませで学生を呼びます。',
                     '資料を煮て学生を呼びます。'):
            self.assertFalse(native_object_clause_edges(text),text)

    def test_kana_verb_homograph_is_not_forced_to_a_noun(self):
        import app
        result=app.correct_line('かいでちしきをえます。',self.a.store,
            input_method='kana',dict_index=self.a.dict_index)
        self.assertTrue(result['corrected'].startswith('かいで'),result)
        self.assertEqual(result['odd_spans'],[])


if __name__ == '__main__':
    unittest.main()
