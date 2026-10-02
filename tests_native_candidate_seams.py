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


if __name__ == '__main__':
    unittest.main()
