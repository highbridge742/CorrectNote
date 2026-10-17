"""引用した表記が別の表記になったと報告する文（2026-10-16・`literal_examples`）。

「誤字の例」が「直った形」になった、と書いた文では、両方の引用が表記
そのものを指す。引用の中を補正しない。裸の引用や、ふつうの変化を言う
文は今までどおり補正できる。

ここの例はすべて作った文。
"""
import unittest

import morphology as M
from literal_examples import protected_ranges


def _protected(line):
    return [line[a:b] for a, b in protected_ranges(line)]


class ChangeReportTests(unittest.TestCase):
    def test_reported_wrong_correction_keeps_both_spellings(self):
        line = '「見本の誤字」が「見本の正字」へ誤補正される例があります。'
        self.assertEqual(_protected(line), ['見本の誤字', '見本の正字'])
        line = '「見本の誤字」が「見本の正字」になる例や「別の誤字」が「別の正字」になる例があります。'
        self.assertEqual(_protected(line), ['見本の誤字', '見本の正字', '別の誤字', '別の正字'])
        line = '「見本の誤字」は「見本の正字」に変換されました。'
        self.assertEqual(_protected(line), ['見本の誤字', '見本の正字'])

    def test_ordinary_quotes_stay_correctable(self):
        for line in ('「しんごう」が「あお」になるまでまつ。',
                     '「見本の誤字」→「見本の正字」へ移動します。',
                     '「見本の誤字」が「見本の正字」になった。'):
            with self.subTest(line=line):
                self.assertEqual(protected_ranges(line), [])


@unittest.skipUnless(M.HAS_JANOME, 'real native dictionary required')
class ChangeReportLineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        cls.state = initial()

    def setUp(self):
        from last_choice import set_active
        self.addCleanup(set_active, None)

    def run_line(self, line):
        from correction_entry import correct_line
        a = self.state
        return correct_line(line, a.store, context_vocab={}, input_method='kana',
                            dict_index=a.dict_index, decisions=a.decisions,
                            context_vec=a.context_vec)

    def test_quoted_typo_examples_are_not_corrected(self):
        line = '補正では「にもつがとどはました」が「荷物が届きました」になる例が残っています。'
        self.assertEqual(self.run_line(line)['corrected'], line)
        line = '「しりょうをよんでおいてくらはい」が「資料を読んでおいて下さい」へ誤補正される例があります。'
        result = self.run_line(line)
        self.assertEqual(result['corrected'], line)
        self.assertEqual(result['odd_spans'], [])


if __name__ == '__main__':
    unittest.main()
