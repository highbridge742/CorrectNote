# -*- coding: utf-8 -*-
"""rollin_word（巻き込みの1打で崩れた名詞の句）と ime_reconvert の活用する語への戻し（2026-11-08）。例は作った文。"""
import os
import unittest

import rollin_word as W


class RollinWord(unittest.TestCase):
    def test_kana_fragments(self):
        self.assertIn((0, 6, '電気代'), W.propose('でんなきだいの請求が'))

    def test_ime_rare_kanji(self):
        self.assertIn((0, 5, '電気代'), W.propose('でん鳴き代の請求が先月より高かった。'))
        self.assertIn((0, 5, '電気代'), W.propose('でんな稀代の請求が。'))

    def test_correct_lines_untouched(self):
        for s in ('電気代の請求が来た。', 'その男は駅で待っていた。', 'もういやだ。', 'おかわりはいかがですか？',
                  'そんな事をするとは思わなかった。', 'たまに人を傷つける。'):
            self.assertEqual(W.propose(s), [], s)

    def test_switch(self):
        os.environ['CN_ROLLIN_WORD'] = '0'
        try:
            self.assertEqual(W.propose('でんなきだいの請求が'), [])
        finally:
            del os.environ['CN_ROLLIN_WORD']


class ReconvertInflected(unittest.TestCase):
    def test_key_slip_to_verb(self):
        import kanji_guess
        import ime_reconvert as R
        rec = {'田桁': ['でんけた'], '週末': ['しゅうまつ'], '家族': ['かぞく']}
        kanji_guess.set_ime_readings_provider(lambda f: rec.get(f, []))
        try:
            self.assertEqual(R.propose('週末は家族で田桁。', 'kana', None), [(6, 8, '週末は家族で出かけた。')])
        finally:
            kanji_guess.set_ime_readings_provider(None)

    def test_keep_object_particle(self):
        # 打った読みで読めない表記（給田 を たべた）は動詞に替えてよい、を は残す（2026-11-08 PC）
        import kanji_guess
        import ime_reconvert as R
        rec = {'給田': ['たべた'], '外国': ['がいこく'], '料理': ['りょうり']}
        kanji_guess.set_ime_readings_provider(lambda f: rec.get(f, []))
        try:
            self.assertEqual(R.propose('外国の料理を給田。', 'kana', None), [(6, 8, '外国の料理を食べた。')])
        finally:
            kanji_guess.set_ime_readings_provider(None)


if __name__ == '__main__':
    unittest.main()
