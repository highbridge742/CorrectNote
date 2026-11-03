"""辞書に無い可能動詞（沿え|る）を つながりの紫にしない／かな書きの副詞（しばらく）を窓にしない（2026-10-30・補正担当。例文は作った文）"""
import unittest
import corrector
import oddness
import pos_grammar


class PotentialVerbTests(unittest.TestCase):
    def test_potential_verb_not_impossible_connection(self):
        self.assertEqual(pos_grammar._impossible_connection_spans('ご期待に沿えるよう準備します。'), ())

    def test_classical_ri_typo_still_marked(self):
        self.assertTrue(pos_grammar._impossible_connection_spans('仕事を始めりました。'))

    def test_potential_aux_heads(self):
        self.assertIn('る', oddness._POTENTIAL_AUX_HEADS)
        self.assertIn('れ', oddness._POTENTIAL_AUX_HEADS)


class KanaAdverbTests(unittest.TestCase):
    def test_kana_dictionary_adverb(self):
        self.assertTrue(corrector._kana_dictionary_adverb('しばらく'))
        self.assertTrue(corrector._kana_dictionary_adverb('ほとんど'))
        self.assertFalse(corrector._kana_dictionary_adverb('らくお'))

    def test_adverb_not_window(self):
        class Empty:
            def lookup(self, frag):
                return []
        self.assertEqual(corrector.explain_cores('までしばらくは', Empty()), [])


if __name__ == '__main__':
    unittest.main()
