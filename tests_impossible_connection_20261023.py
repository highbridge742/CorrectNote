"""いまの日本語では起こらない品詞のつながりに紫（補正C・2026-10-23・例文は作った文）"""
import unittest
import morphology
from pos_grammar import _impossible_connection_spans


@unittest.skipUnless(morphology.HAS_JANOME, '解析器が無い')
class ImpossibleConnectionTests(unittest.TestCase):
    def test_broken_kana_is_marked(self):
        # かなが1打崩れて、文語や名詞＋受け身に切られた形
        for line in ('明日は駅まで歩きり。', '机の整理れをした。', 'お茶を飲みまなした。'):
            self.assertTrue(_impossible_connection_spans(line), line)

    def test_correct_lines_are_not_marked(self):
        for line in ('明日は駅まで歩く。', '机の整理をした。', 'お茶を飲みました。', '選択なしで進める。',
                     '会議の資料を作られた。', '雨が降りそうだ。'):
            self.assertEqual(_impossible_connection_spans(line), (), line)


    def test_particles_and_auxiliaries_that_cannot_stack(self):
        # 格助詞の重なり・並べる と の後の格助詞・は の後の で・た の後の ぬ・連用形＋らしい・補助の い＋用言・
        # 言い切りの後の は で終わる文
        for line in ('パンへを焼いた。', '本とを読んだ。', '公園はで遊ぶ。', '手紙を出したぬ', '風が吹きらしい',
                     '絵を描いてい見せた', '明日は早く起きますは'):
            self.assertTrue(_impossible_connection_spans(line), line)

    def test_correct_stacks_are_not_marked(self):
        for line in ('パンと牛乳とを買った。', '東京へは来月行く。', 'ここでは靴を脱ぐ。', '雨が降ったらしい。',
                     '見ていられない。', 'それはね、秘密だよ。', 'ありますは、ありますけど。', '選択ではなく移動になる。',
                     'JISかな配列にする。', '駅での待ち合わせ。', '学校へと向かった。', '器用と不器用とに分けます。',
                     '必要なほんね資料を渡します。', '買いまうす。', 'たまねぎとにんじんをこまかくきります。',
                     'かんりょうごにしりょうをほぞんします。', 'つくえのまえにほんをならべます。', 'ほんをよみまをす。'):
            self.assertEqual(_impossible_connection_spans(line), (), line)


if __name__ == '__main__':
    unittest.main()
