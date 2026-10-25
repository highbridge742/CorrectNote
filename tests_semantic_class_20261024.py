"""語の組の表を意味の分類（分類語彙表）で広げる（collocation_repair・semantic_class・2026-10-24・例文は作った文）"""
import unittest
from tests_analysis_async import initial
from correction_entry import correct_line


class WlspClassTests(unittest.TestCase):
    def run_ime(self, face, pairs):
        st = initial()
        for sf, rd in pairs:
            st.ime_readings.remember(sf, rd)
        return correct_line(face, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                            decisions=st.decisions, context_vec=st.context_vec)

    def purple(self, r, text):
        return any(text in x[2] for x in r.get('odd_reasons') or ())

    def test_codes_are_loaded(self):
        import semantic_class as wlsp_classes
        self.assertIn('1.3122', wlsp_classes.codes('返事'))
        self.assertIn('天気', wlsp_classes.words_read('てんき'))

    def test_class_member_outside_table_is_candidate(self):
        # しょうめい を打ち違えて IME が 襲名 にした。照明 は表に無いが、表の 電気・明かり と同じ仲間（消す）
        r = self.run_ime('部屋の襲名を消した。', [('襲名', 'しゅうめい')])
        self.assertEqual(r['corrected'], '部屋の照明を消した。')

    def test_familiar_out_of_class_noun_is_purple(self):
        # しゃしん→しゃいん: 社員 は身近な語なので替えないが、撮る の組の仲間でないので紫
        r = self.run_ime('旅先で社員を撮った。', [('社員', 'しゃいん')])
        self.assertEqual(r['corrected'], '旅先で社員を撮った。')
        self.assertTrue(self.purple(r, 'よく使う組'))

    def test_correct_class_members_are_left_alone(self):
        # 表に無い正しい組でも、組の意味の仲間なら何も付けない
        for line in ('電車の時刻を調べた。', '冷たい麦茶を飲んだ。', '花壇に球根を植えた。', '旅先で景色を撮った。'):
            r = self.run_ime(line, [])
            self.assertEqual(r['corrected'], line)
            self.assertFalse(self.purple(r, 'よく使う組'), line)


if __name__ == '__main__':
    unittest.main()
