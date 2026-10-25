"""かなで書いた名詞が、頭の1字の感動詞＋切れ端に割れた形を1語に戻す（2026-10-23・うにさんの報告「おてほん」）"""
import unittest
from tests_analysis_async import initial
from morphology import tokenize


class KanaNounHeadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initial()

    def test_split_kana_noun_is_one_noun(self):
        toks = tokenize('おてほんを見る')
        self.assertEqual([(t.surface, t.pos) for t in toks[:2]], [('おてほん', '名詞'), ('を', '助詞')])

    def test_real_interjection_is_kept(self):
        toks = tokenize('えっと、それは')
        self.assertEqual(toks[0].pos, '感動詞')


if __name__ == '__main__':
    unittest.main()
