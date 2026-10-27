"""正しい文を崩す誤判定の直し（2026-10-26）。例はすべて作ったもの。"""
import os
import tempfile
import unittest

import morphology as M


@unittest.skipUnless(M.HAS_JANOME, 'real native dictionary required')
class FalsePositiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from vocabulary import open_vocabulary
        from dict_index import DictIndex
        from context_vec import ContextVectorStore
        from decisions import DecisionStore
        cls.tmp = tempfile.mkdtemp()
        cls.store = open_vocabulary(os.path.join(cls.tmp, 'vocabulary.json'))
        cls.store.load()
        cls.index = DictIndex(); cls.index.ensure_built()
        cls.cv = ContextVectorStore(); cls.cv.ensure_seeded()
        cls.dec = DecisionStore()

    def correct(self, text):
        import app
        return app.correct_line(text, self.store, input_method='kana', dict_index=self.index,
                                decisions=self.dec, context_vec=self.cv)['corrected']

    def test_counter_suffix_is_not_a_word_pair(self):
        for text in ('3行後の段落を見る', '5行分の余白', '4点間を結ぶ線'):
            self.assertEqual(self.correct(text), text)

    def test_kana_predicate_is_not_spelled_as_noun(self):
        for text in ('全体にしないという方針', '細かい調整をしないというのは同じ'):
            self.assertEqual(self.correct(text), text)

    def test_unseen_pair_does_not_drop_a_whole_noun(self):
        self.assertEqual(self.correct('行間幅を広げる'), '行間幅を広げる')

    def test_unknown_kanji_compound_before_suru_is_a_noun(self):
        for text in ('自走できる', '自走して止まる'):
            self.assertEqual(self.correct(text), text)

    def test_real_repairs_still_work(self):
        self.assertEqual(self.correct('引き月資料を送る'), '引き継ぎ資料を送る')


if __name__ == '__main__':
    unittest.main()
