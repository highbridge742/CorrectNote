"""タブの左の欄で終わる文も、欄の終わりを文の終わりとして見る（2026-10-30・補正担当。例文は作った文）"""
import unittest
import tests_last_keystroke_20261016 as _T


class TabFieldEndTests(unittest.TestCase):
    setUpClass = _T.LastKeystrokeLineTests.__dict__['setUpClass']
    setUp = _T.LastKeystrokeLineTests.setUp
    run_line = _T.LastKeystrokeLineTests.run_line

    def test_degree_adverb_before_tab(self):
        got = self.run_line('この石はとても思い\t\t庭の話')
        self.assertTrue(got['corrected'].startswith('この石はとても重い\t'), got['corrected'])

    def test_plain_line_still_fixed(self):
        self.assertTrue(self.run_line('この石はとても思い。')['corrected'].startswith('この石はとても重い'))

    def test_correct_field_kept(self):
        line = 'この石はとても重い\t\t庭の話'
        self.assertEqual(self.run_line(line)['corrected'], line)


if __name__ == '__main__':
    unittest.main()
