"""読みで直した述語の、触っていない頭の語は元の漢字のまま（2026-10-30・補正担当。例文は作った文）"""
import unittest
import contextual_repair as CR


class KeepWrittenEdgesTests(unittest.TestCase):
    def test_head_word_kept(self):
        self.assertEqual(CR._keep_written_edges('簡単にまとるました', 'かんたんにまとめました'), '簡単にまとめました')

    def test_kana_only_unchanged(self):
        self.assertEqual(CR._keep_written_edges('まとる', 'まとめ'), 'まとめ')

    def test_same_reading_respelling_unchanged(self):
        self.assertEqual(CR._keep_written_edges('簡単', 'かんたん'), 'かんたん')


if __name__ == '__main__':
    unittest.main()
