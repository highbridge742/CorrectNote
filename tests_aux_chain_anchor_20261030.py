"""助動詞の連なり（し｜まし｜だ）の前の漢字を支えに、起こらないつながりを見る（2026-10-30・補正担当。例文は作った文）"""
import unittest
import pos_grammar as P


class AuxChainAnchorTests(unittest.TestCase):
    def test_marked(self):
        self.assertTrue(P._impossible_connection_spans('週末は友人と食事をしましだ。'))

    def test_correct_not_marked(self):
        for line in ('週末は友人と食事をしました。', 'みんなで食事をしましょう。', '昨日は雨でした。'):
            self.assertEqual(P._impossible_connection_spans(line), (), line)


if __name__ == '__main__':
    unittest.main()
