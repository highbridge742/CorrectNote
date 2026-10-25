"""打ち間違えた読みがそのまま辞書の語になる形を語の組で見る（collocation_repair・2026-10-23・例文は作った文）"""
import unittest
from tests_analysis_async import initial
from correction_entry import correct_line


class CollocationRepairTests(unittest.TestCase):
    def run_ime(self, face, pairs):
        st = initial()
        for sf, rd in pairs:
            st.ime_readings.remember(sf, rd)
        return correct_line(face, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                            decisions=st.decisions, context_vec=st.context_vec)

    def test_unfamiliar_noun_becomes_collocation(self):
        # へんじ の へ が隣の ほ に替わり、IME が 本字 にした。返事を書く は組、本字を書く は組でない
        r = self.run_ime('友人に本字を書いた。', [('本字', 'ほんじ')])
        self.assertEqual(r['corrected'], '友人に返事を書いた。')

    def test_familiar_noun_is_not_replaced(self):
        # しゃしん→しゃいん（上下のキー）: 社員 は身近な語で、元の文も言えるので直さない
        r = self.run_ime('旅先で社員を撮った。', [('社員', 'しゃいん')])
        self.assertEqual(r['corrected'], '旅先で社員を撮った。')

    def test_correct_pairs_missing_from_table_are_not_purple(self):
        # 表に無い正しい組（紙を切る・気をつける・友達を持つ）に組の紫を付けない
        for line in ('紙を切ってください。', 'ミスらないように気をつける。', '改札の前で友達を持つ。', '予定を書く人がいます。'):
            r = self.run_ime(line, [])
            self.assertEqual(r['corrected'], line)
            self.assertFalse(any('よく使う組' in x[2] for x in r.get('odd_reasons') or ()), line)

    def test_homophone_suru_noun(self):
        # けんじする を IME が 賢治＋した にした。方針を堅持する は組、賢治 は する の付かない語
        r = self.run_ime('会社の方針を賢治した。', [('賢治', 'けんじ')])
        self.assertEqual(r['corrected'], '会社の方針を堅持した。')

    def test_spelling_variants_are_kept(self):
        # 同じ語の書き分け（子ども／子供・珈琲／コーヒー・上る／登る）は替えない
        for line in ('二人目の子どもが生まれた。', '朝は珈琲を飲む。', '階段を上って部屋に入った。'):
            r = self.run_ime(line, [])
            self.assertEqual(r['corrected'], line)

    def test_rest_of_half_fix_is_purple(self):
        # 名詞は直るが、左の 日曜に（の→に の打ち違い）が残る: 直しは残して残りに紫
        r = self.run_ime('日曜に転機を調べた。', [('転機', 'てんき')])
        self.assertEqual(r['corrected'], '日曜に天気を調べた。')
        self.assertTrue(any(a == 0 for a, b in [tuple(x[:2]) for x in r['odd_spans']]))

    def test_homophone_suru_noun(self):
        # けんじする を IME が 賢治＋した にした。方針を堅持する は組、賢治 は する の付かない語
        r = self.run_ime('会社の方針を賢治した。', [('賢治', 'けんじ')])
        self.assertEqual(r['corrected'], '会社の方針を堅持した。')

    def test_spelling_variants_are_kept(self):
        # 同じ語の書き分け（子ども／子供・珈琲／コーヒー・上る／登る）は替えない
        for line in ('二人目の子どもが生まれた。', '朝は珈琲を飲む。', '階段を上って部屋に入った。'):
            r = self.run_ime(line, [])
            self.assertEqual(r['corrected'], line)

    def test_rest_of_half_fix_is_purple(self):
        # 名詞は直るが、左の 日曜に（の→に の打ち違い）が残る: 直しは残して残りに紫
        r = self.run_ime('日曜に転機を調べた。', [('転機', 'てんき')])
        self.assertEqual(r['corrected'], '日曜に天気を調べた。')
        self.assertTrue(any(a == 0 for a, b in [tuple(x[:2]) for x in r['odd_spans']]))

    def test_correct_lines_are_kept(self):
        for line in ('鳥の餌を買いに行った。', '電話番号を書き間違えた。', '走る車の音が気になって眠れない。',
                     '旅行のお土産を渡した。', '駅で友達を待つ。'):
            r = self.run_ime(line, [])
            self.assertEqual(r['corrected'], line)
            self.assertFalse(any('よく使う組' in x[2] for x in r.get('odd_reasons') or ()), line)


if __name__ == '__main__':
    unittest.main()
