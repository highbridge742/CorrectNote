"""複合動詞の連用形＋名詞で終わる行（書き込み処理）に、切れ端の紫を付けない（2026-10-30・補正担当。例文は作った文）"""
import unittest
import oddness
import morphology


def _spans(text):
    return oddness.renyou_stray_noun_spans(text, lambda t: [
        (x.surface, f'{x.pos}:{x.pos_sub}', x.reading, x.start, x.end, x.base_form, x.infl_form)
        for x in morphology.tokenize(t)])


class CompoundRenyouNounTests(unittest.TestCase):
    def test_compound_verb_head_makes_compound_noun(self):
        self.assertEqual(_spans('表の並べ替え処理'), [])
        self.assertEqual(_spans('音の聞き取り練習'), [])

    def test_simple_stem_still_marked(self):
        self.assertTrue(_spans('朝から寝麻酔'))


if __name__ == '__main__':
    unittest.main()
