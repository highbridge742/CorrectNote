"""一般によく使う語には稀の紫を付けない／お＋名詞＋ください を接尾辞＋用言の紫にしない（2026-10-30・補正担当。例文は作った文）"""
import unittest
import last_keystroke as L
import oddness


def _spans(line):
    import morphology
    return [(t.start, t.end, (t.surface, t.pos + ':' + (t.pos_sub or ''))) for t in morphology.tokenize(line)]


class CommonRestrictedTests(unittest.TestCase):
    def test_common_word_not_rare(self):
        self.assertTrue(L._general_common('事前'))

    def test_rare_word_still_rare(self):
        self.assertFalse(L._general_common('稀代'))
        self.assertFalse(L._general_common('現官'))

    def test_gate_wired(self):
        import inspect
        self.assertIn('not _general_common(t.surface)', inspect.getsource(L._mark_rare_clauses))


class HonorificRequestTests(unittest.TestCase):
    def test_prefix_noun_kudasai(self):
        sp = [(0, 1, ('お', '接頭詞:名詞接続')), (1, 2, ('声', '名詞:一般')), (2, 4, ('がけ', '名詞:接尾:一般')),
              (4, 8, ('ください', '動詞:自立'))]
        self.assertFalse(oddness.suffix_then_yougen(sp, 2))

    def test_suffix_then_verb_still_odd(self):
        sp = [(0, 2, ('田中', '名詞:固有名詞')), (2, 4, ('さん', '名詞:接尾:人名')), (4, 6, ('行く', '動詞:自立'))]
        self.assertTrue(oddness.suffix_then_yougen(sp, 1))


if __name__ == '__main__':
    unittest.main()
