"""上下の行の語と読みが隣のキーの1打だけ違う漢字の語を、その語に置く（2026-10-30・補正担当。例文は作った文）"""
import unittest
import nearby_one_key as N


class NearbyOneKeyTests(unittest.TestCase):
    def test_one_key_word_from_nearby(self):
        # ほんじ（本字）と へんじ（返事）: ほ と へ は隣のキー
        got = N.repair_line('友達のメールに本字を書く', {'corrected': '友達のメールに本字を書く'}, ['返事', '友達'])
        self.assertEqual(got['corrected'], '友達のメールに返事を書く')

    def test_word_written_nearby_is_kept(self):
        line = '友達のメールに本字を書く'
        got = N.repair_line(line, {'corrected': line}, ['返事', '本字'])
        self.assertEqual(got.get('corrected'), line)

    def test_no_nearby_word_no_change(self):
        line = '雨の日は傘を持っていく。'
        self.assertEqual(N.repair_line(line, {'corrected': line}, ['雨', '天気'])['corrected'], line)

    def test_common_word_not_replaced_by_nearby_common_word(self):
        # しんせい（申請）と じんせい（人生）: どちらもよく使う語。近くの行に 人生 が在っても、正しく書いた 申請 は替えず紫も付けない
        line = '役所に申請を出した'
        got = N.repair_line(line, {'corrected': line}, ['人生', '役所'])
        self.assertEqual(got.get('corrected'), line)
        self.assertFalse(got.get('odd_spans'))

    def test_romaji_input_untouched(self):
        line = '友達のメールに本字を書く'
        self.assertEqual(N.repair_line(line, {'corrected': line}, ['返事'], 'romaji')['corrected'], line)

    def test_wired_after_pair_choice(self):
        import inspect, correction_entry as C
        self.assertIn('_nearby_one_key(line, result, nearby_words, input_method, decisions)',
                      inspect.getsource(C._line_stages_now))


if __name__ == '__main__':
    unittest.main()
