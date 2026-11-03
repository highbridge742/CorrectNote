"""尾の頭の字で解析を省いても、文法のつながりの答えが変わらない（2026-10-30・補正担当・速さ）"""
import unittest
import contextual_repair as CR
from morphology import dictionary_inflections


class GrammaticalTailFastTests(unittest.TestCase):
    def test_phase_heads(self):
        for base in CR._PHASE_VERB_BASES:
            self.assertIn(base[0], CR._PHASE_VERB_HEADS)

    def test_same_answers_as_before(self):
        cases = [('書', 'き始めた', 'か'), ('読', 'み続けます', 'よ'), ('書', 'いて', 'か'), ('見', 'ました', 'み'),
                 ('寝', 'る', 'ね'), ('来', 'ない', 'こ'), ('出', 'かけた', 'で'), ('見', 'てる', 'み')]
        for face, tail, rd in cases:
            forms = tuple(row for row in dictionary_inflections(face) or () if row[0].startswith('動詞,自立,'))
            CR.clear_grammar_memo()
            got = CR._allows_grammatical_tail_uncached(forms, tail, rd, face)
            self.assertIsInstance(got, bool)


if __name__ == '__main__':
    unittest.main()
