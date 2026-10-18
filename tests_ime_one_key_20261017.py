# -*- coding: utf-8 -*-
"""打った読みそのものに1打の誤りがあるときの設計30（2026-10-17）。

うにさんの報告「切磋名はどこ が 説明はどこ に直らなかった。隣接キー
巻き込み」。打った読み せつさめい（つ の隣の さ を巻き込んだ）を IME が
切磋名 に変えた。1打を戻した読みが1つだけ語彙の語に届き、いまの表記を
語に分けた読みが打った読みにならないときだけ直す。
"""
import unittest
from unittest import mock

import morphology as M


@unittest.skipUnless(M.HAS_JANOME, 'real native dictionary required')
class IMEOneKeyRespellTests(unittest.TestCase):
    def correct(self, line, pairs=(), input_method='kana'):
        import app
        from tests_analysis_async import initial
        from last_choice import set_active
        a = initial()
        self.addCleanup(set_active, None)
        for surface, reading in pairs:
            a.ime_readings.remember(surface, reading)
        return app.correct_line(line, a.store, input_method=input_method,
                                dict_index=a.dict_index, decisions=a.decisions,
                                context_vec=a.context_vec)

    def test_rolled_in_key_under_an_ime_guess_is_repaired(self):
        for line, want in (('切磋名はどこ', '説明はどこ'),
                           ('切磋名を見ます。', '説明を見ます。')):
            with self.subTest(line=line):
                result = self.correct(line, [('切磋名', 'せつさめい')])
                self.assertEqual(result['corrected'], want)

    def test_clause_pair_supplies_the_word_reading(self):
        # IME の対は文節（語＋助詞）や行ごとに保存される。塊そのものの対が
        # 無くても、前後の語の読みを外して塊の読みを取り出す
        for pair in (('切磋名は', 'せつさめいは'), ('切磋名はどこ', 'せつさめいはどこ')):
            with self.subTest(pair=pair):
                self.assertEqual(self.correct('切磋名はどこ', [pair])['corrected'], '説明はどこ')
        # 今回の確定（出現）だけでも同じ
        import app
        from tests_analysis_async import initial
        from analysis_work import Occurrence
        a = initial()
        result = app.correct_line('切磋名はどこ', a.store, input_method='kana',
                                  dict_index=a.dict_index, decisions=a.decisions,
                                  context_vec=a.context_vec,
                                  occurrence_readings=(Occurrence(0, 4, '切磋名は', 'せつさめいは'),))
        self.assertEqual(result['corrected'], '説明はどこ')

    def test_pair_readings_are_cut_at_word_boundaries(self):
        import corrector as C
        import kanji_guess
        pairs = {'切磋名は': ['せつさめいは'], 'この切磋名を': ['このせつさめいを']}
        kanji_guess.set_ime_readings_provider(lambda t: pairs.get(t, []))
        self.addCleanup(kanji_guess.set_ime_readings_provider, None)
        self.assertEqual(C._ime_pair_readings('切磋名', '切磋名はどこ', 0, 3), ['せつさめい'])
        self.assertEqual(C._ime_pair_readings('切磋名', 'この切磋名を見る', 2, 5), ['せつさめい'])
        # 対の表記が塊の途中で切れていれば使わない
        pairs = {'磋名は': ['さめいは']}
        self.assertEqual(C._ime_pair_readings('切磋名', '切磋名はどこ', 0, 3), [])

    def test_faithful_conversion_is_left(self):
        # 打ったとおりに読める表記は、本人の書きたい語かもしれない
        for line, pair in (('写真化します。', ('写真化', 'しゃしんか')),
                           ('切磋名はどこ', ('切磋名', 'せっさめい'))):
            with self.subTest(line=line):
                self.assertEqual(self.correct(line, [pair])['corrected'], line)
        # IME の対が無ければ、打った読みは分からない
        self.assertEqual(self.correct('切磋名はどこ')['corrected'], '切磋名はどこ')

    def test_romaji_input_does_not_use_kana_keys(self):
        result = self.correct('切磋名はどこ', [('切磋名', 'せつさめい')],
                              input_method='romaji')
        self.assertEqual(result['corrected'], '切磋名はどこ')

    def test_common_final_check_still_applies(self):
        import corrector
        with mock.patch.object(corrector, '_check_replacement',
                               return_value=(None, 'test_common_gate')):
            result = self.correct('切磋名はどこ', [('切磋名', 'せつさめい')])
        self.assertEqual(result['corrected'], '切磋名はどこ')

    def test_reads_as_typed(self):
        import corrector as C
        from tests_analysis_async import initial
        a = initial()
        tk = C.make_tokenizer(a.store)
        self.assertTrue(C._reads_as_typed('写真化', 'しゃしんか', tk, a.dict_index))
        self.assertTrue(C._reads_as_typed('切磋名', 'せっさめい', tk, a.dict_index))
        self.assertFalse(C._reads_as_typed('切磋名', 'せつさめい', tk, a.dict_index))


if __name__ == '__main__':
    unittest.main()
