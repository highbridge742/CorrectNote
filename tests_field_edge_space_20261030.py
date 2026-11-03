"""欄の頭の空白（字下げ）があっても、かなの行の表記は空白の無い行と同じに置く（2026-10-30・補正担当。例文は作った文）"""
import unittest
import kana_spelling as K
import tests_last_keystroke_20261016 as _T


class FieldEdgeSpaceTests(unittest.TestCase):
    setUpClass = _T.LastKeystrokeLineTests.__dict__['setUpClass']
    setUp = _T.LastKeystrokeLineTests.setUp
    run_line = _T.LastKeystrokeLineTests.run_line

    def test_fields_skip_edge_spaces(self):
        self.assertEqual(list(K._fields(' あいう')), [(1, 4)])
        self.assertEqual(list(K._fields('　あいう　')), [(1, 4)])
        self.assertEqual(list(K._fields('あいう\t\tえお')), [(0, 3), (5, 7)])

    def test_indented_kana_line_same_as_plain(self):
        plain = self.run_line('あめがふったばあい')['corrected']
        self.assertEqual(self.run_line(' あめがふったばあい')['corrected'], ' ' + plain)


if __name__ == '__main__':
    unittest.main()
