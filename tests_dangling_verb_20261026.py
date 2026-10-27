"""後ろに て・た の続かない音便形の動詞に、抜けた1字を足す（dangling_verb・2026-10-26）。例はすべて作ったもの。"""
import unittest

import morphology as M


@unittest.skipUnless(M.HAS_JANOME, 'real native dictionary required')
class DanglingVerbTest(unittest.TestCase):
    def test_detects_only_unfollowed_onbin_forms(self):
        import dangling_verb as D
        self.assertTrue(D.dangling('窓を開けてくだい。'))
        for ok in ('窓を開けてください。', '本を置いた。', '少し休んで帰った。', '手紙を書いて送る。'):
            self.assertEqual(D.dangling(ok), [], ok)

    def correct(self, line):
        import app
        from tests_analysis_async import initial
        from last_choice import set_active
        a = initial()
        self.addCleanup(set_active, None)
        return app.correct_line(line, a.store, input_method='kana', dict_index=a.dict_index,
                                decisions=a.decisions, context_vec=a.context_vec)

    def test_dropped_kana_is_restored(self):
        self.assertEqual(self.correct('窓を開けてくだい。')['corrected'], '窓を開けてください。')

    def test_correct_lines_are_unchanged(self):
        for line in ('窓を開けてください。', '本を机に置いた。', '少し休んで帰った。'):
            r = self.correct(line)
            self.assertEqual(r['corrected'], line, line)


if __name__ == '__main__':
    unittest.main()
