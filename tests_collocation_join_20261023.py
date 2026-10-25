"""IME が打ち違いの読みを幾つもの語に切った名詞を、読みをつないで1打戻した組で見る（確かなら直し・迷えば紫）（collocation_repair・2026-10-23・例文は作った文）"""
import unittest
from tests_analysis_async import initial
from correction_entry import correct_line
import collocation_repair as C


class CollocationJoinTests(unittest.TestCase):
    def run_ime(self, face, pairs):
        st = initial()
        for sf, rd in pairs:
            st.ime_readings.remember(sf, rd)
        return correct_line(face, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                            decisions=st.decisions, context_vec=st.context_vec)

    def test_split_noun_is_fixed(self):
        # ともだち の と の後に隣のキーの し を打ち、IME が 都市＋も＋立ち に切った形: つなぐと としもだち → ともだち を待つ
        # 候補は1つ（友達）で、左が確かな区切り（改札＋で）なので直す
        r = self.run_ime('改札で都市も立ちを待った。', [('都市', 'とし'), ('立ち', 'だち')])
        self.assertEqual(r['corrected'], '改札で友達を待った。')

    def test_unclear_left_is_purple_only(self):
        # 左が確かな区切りでない（これから＋書き題）なら紫だけ
        found = C.find('これから書き題を始める。', 'kana')
        self.assertTrue(found and not any(f[3] for f in found))

    def test_kana_words_and_substrings_are_kept(self):
        # かなで書いた語・読みの一部を取り出すだけの語（えほん → ほん）には付けない
        for line in ('こどもにえほんを読んであげた。', 'かいたぶんしょうを確認した。'):
            self.assertFalse([f for f in C.find(line, 'romaji') if not f[3]])

    def test_correct_lines_are_kept(self):
        for line in ('駅前で友達を待った。', '部屋の掃除をした。', '雨が止んだら散歩に行こう。'):
            r = self.run_ime(line, [])
            self.assertEqual(r['corrected'], line)
            self.assertFalse(r['odd_spans'])


if __name__ == '__main__':
    unittest.main()
