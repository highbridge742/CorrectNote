"""形容詞の語幹・接頭詞（漢字）＋動詞の連用形の複合語（固＋茹で）の後ろの名詞に紫を付けない（2026-10-31・補正担当。例文は作った文）"""
import unittest
import oddness


class _Fn:
    def __call__(self, text):
        import morphology
        return [(t.surface, t.pos + ':' + (t.pos_sub or ''), t.reading, t.start, t.end, True, t.infl_form or '')
                for t in morphology.tokenize(text)]


class AdjectiveRenyouCompoundTests(unittest.TestCase):
    def test_adjective_stem_compound_not_marked(self):
        self.assertEqual(oddness.renyou_stray_noun_spans('固茹でエッグ', _Fn()), [])

    def test_prefix_compound_not_marked(self):
        self.assertEqual(oddness.renyou_stray_noun_spans('高跳びマット', _Fn()), [])

    def test_bare_verb_with_stray_noun_still_marked(self):
        self.assertTrue(oddness.renyou_stray_noun_spans('寝クス', _Fn()))


if __name__ == '__main__':
    unittest.main()
