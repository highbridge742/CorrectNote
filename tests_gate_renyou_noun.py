"""ime_inverse_gate._written_nominal_group: 動詞の連用形がそのまま名詞になった語は書いたとおりの名詞として読める（作った例）。"""
import os
import unittest

import ime_inverse_gate as G
from morphology import tokenize


def _parts(text):
    return [(t.surface, t.pos + (':' + t.pos_sub if t.pos_sub else ''), t.reading,
             t.start, t.end, t.has_reading, t.infl_form) for t in tokenize(text)]


class GateRenyouNounTest(unittest.TestCase):
    def _group(self, text, word):
        return [p for p in _parts(text) if p[0] == word]

    def test_renyou_noun_is_nominal(self):
        text = '色付きで残す'
        self.assertTrue(G._written_nominal_group(text, self._group(text, '色付き'), _parts))

    def test_switch_off(self):
        text = '色付きで残す'
        os.environ['CN_GATE_RENYOU_NOUN'] = '0'
        try:
            self.assertFalse(G._written_nominal_group(text, self._group(text, '色付き'), _parts))
        finally:
            del os.environ['CN_GATE_RENYOU_NOUN']


if __name__ == '__main__':
    unittest.main()
