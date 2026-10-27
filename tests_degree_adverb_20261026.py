"""程度の副詞が、受ける述語の無い名詞にかかる所（degree_adverb・2026-10-26）。例はすべて作ったもの。

うに 2026-10-26「とてもおもいで、とても思い、とても想いが変なのは、なぜだと思いますか」→ 程度の副詞は様子や度合いの語に
かかり、名詞にはかからない。名詞のあとに受ける述語が無ければ、同じ読みの形容詞へ（1つに決まらなければ紫）。
"""
import unittest

import morphology as M
import degree_adverb as D


class DegreeWordsTest(unittest.TestCase):
    def test_table_comes_from_the_degree_class(self):
        words = D.degree_words()
        for w in ('とても', 'かなり', 'やや', '非常'):
            self.assertIn(w, words)
        self.assertNotIn('机', words)


@unittest.skipUnless(M.HAS_JANOME, 'real native dictionary required')
class DegreeAdverbLineTest(unittest.TestCase):
    def correct(self, line):
        import app
        from tests_analysis_async import initial
        from last_choice import set_active
        a = initial()
        self.addCleanup(set_active, None)
        return app.correct_line(line, a.store, input_method='kana', dict_index=a.dict_index,
                                decisions=a.decisions, context_vec=a.context_vec)

    def test_noun_after_degree_adverb_becomes_same_reading_adjective(self):
        for line, want in (('箱はとても想い。', '箱はとても重い。'),
                           ('この鞄は非常に思いです', 'この鞄は非常に重いです')):
            self.assertEqual(self.correct(line)['corrected'], want, line)

    def test_noun_with_its_own_predicate_is_left_alone(self):
        for line in ('彼はとても思いが強い。', 'ちょっと前に着いた。', 'かなり昔の写真だ。',
                     '計画にはおおむね賛成だ。', '机はとても重い。', 'とてもおもい'):
            r = self.correct(line)
            self.assertEqual(r['corrected'], line, line)
            self.assertFalse(r.get('odd_spans'), line)

    def test_noun_without_an_adjective_reading_is_purple(self):
        r = self.correct('今朝はとても機嫌')
        self.assertEqual(r['corrected'], '今朝はとても機嫌')
        self.assertIn((6, 8), [tuple(x[:2]) for x in r.get('odd_spans') or ()])


if __name__ == '__main__':
    unittest.main()
