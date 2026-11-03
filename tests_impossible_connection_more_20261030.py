"""いまの文では起こらない品詞のつながりの印を足す（名詞＋て・な＋用言・名詞＋き・名詞＋ば・名詞＋ま＋名詞・ます＋だ・助詞＋たい）
（2026-10-30・補正担当。例文は作った文）"""
import unittest
import pos_grammar as P


class ImpossibleConnectionMoreTests(unittest.TestCase):
    def test_marked(self):
        for line in ('本日の作業は難しい状況てす。', '今日は一覧なまとめました。', '旅費の精算き経理に出す。',
                     '落とし物ば受付で預かる。', '提出物ま締め切りを守る。', '朝ご飯を食べましだ。', '検索はたい言葉を入れる。'):
            self.assertTrue(P._impossible_connection_spans(line), line)

    def test_correct_not_marked(self):
        for line in ('綺麗なのです。', 'それならば行きます。', '静かな海を見た。', '会議室で待ちます。',
                     '本を読みたい。', 'えーと、これは本です。', '資料として配ります。'):
            self.assertEqual(P._impossible_connection_spans(line), (), line)


if __name__ == '__main__':
    unittest.main()
