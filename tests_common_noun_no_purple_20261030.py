"""一般の文でよく使う名詞（表記）に、語の組の表に組が無いだけで紫を付けない／略語の表の BOM（2026-10-30・補正担当。例文は作った文）"""
import unittest
import collocation_repair as CR
import loanword


class CommonNounNoPurpleTests(unittest.TestCase):
    def test_common_noun_not_rarer_than_candidate(self):
        self.assertFalse(CR._rarer_than_any('表記', ['病気']))

    def test_rare_noun_still_doubted(self):
        self.assertTrue(CR._rarer_than_any('変心', ['返信']))

    def test_purple_gate_wired(self):
        import inspect
        self.assertIn("_rarer_than_any(old, [x[2] for x in opts])", inspect.getsource(CR))

    def test_bom_is_known_acronym(self):
        self.assertIn('BOM', loanword._ACRONYM_SEED)
        self.assertEqual(loanword.find_miskeyed_acronym('BOM付きで保存する', None), [])


if __name__ == '__main__':
    unittest.main()
