"""常用漢字表の外の字を疑う段（kanji_doubt・2026-10-26）。例はすべて作ったもの。"""
import unittest

import morphology as M
import kanji_doubt as K


class JoyoTableTest(unittest.TestCase):
    def test_table_has_2136_chars(self):
        self.assertEqual(len(K.joyo()), 2136)
        self.assertFalse(K.outside('確認'))
        self.assertTrue(K.outside('撹乱'))


@unittest.skipUnless(M.HAS_JANOME, 'real native dictionary required')
class KanjiDoubtTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        cls.a = initial()

    def tearDown(self):
        from last_choice import set_active
        set_active(None)

    def propose(self, line):
        return K.propose(line, self.a.store, self.a.dict_index)

    def test_typo_that_became_a_rare_word_is_purple(self):
        # せんたく の1打違いが IME で 尖端 になった形（作り例）
        got = self.propose('雨の日は尖端物が乾かない。')
        self.assertTrue(got)
        self.assertEqual(got[0][:2], (4, 6))

    def test_names_and_everyday_rare_kanji_are_left_alone(self):
        for line in ('李さんに会った。', '持参した鞄に入れた。', 'デザートに蜜柑を食べた。',
                     '魚屋で鯵を買った。', '朝から咳が止まらない。'):
            self.assertEqual(self.propose(line), [], line)


if __name__ == '__main__':
    unittest.main()
