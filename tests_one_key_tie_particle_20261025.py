# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""打った読みの1打の戻し（_ime_one_key_respell）の2つの広げ（2026-10-25・未解決 相手の意図を察して返事を）:
1. 1打を戻した読みが2つ並ぶ（へんじ・ほんば）とき、身近さの表（everyday_faces）に在る読みが1つだけならそれに決める。
2. 戻した読みの末尾が助詞1字で手前が世の中の語（へんじょ→へんじを）なら、語＋助詞（返事を）を直し先にする
   （を を打つつもりで隣の ょ を押した／巻き込んだのを IME が助詞ごと変換した形）。塊の直後にかなが続くなら見ない。
例は作ったもの。"""
import unittest

import morphology as M


@unittest.skipUnless(M.HAS_JANOME, 'real native dictionary required')
class OneKeyTieAndParticleTests(unittest.TestCase):
    def correct(self, line, pairs=(), input_method='kana'):
        import app
        from tests_analysis_async import initial
        from last_choice import set_active
        a = initial()
        self.addCleanup(set_active, None)
        # 直し先は本人の語彙の語だけなので、同梱の語として足す（実機では seed に在る）
        for reading, surface in (('へんじ', '返事'), ('ほんば', '本場')):
            if not a.store.lookup(reading):
                a.store.add(reading, surface, solid=True)
        for surface, reading in pairs:
            a.ime_readings.remember(surface, reading)
        return app.correct_line(line, a.store, input_method=input_method,
                                dict_index=a.dict_index, decisions=a.decisions,
                                context_vec=a.context_vec)

    def test_tie_is_broken_by_everyday_faces(self):
        # へんば → へんじ（返事・表に在る）／ほんば（本場・表に無い）: 返事 に決める
        result = self.correct('友人の気持ちを察して変場を', [('変場を', 'へんばを')])
        self.assertEqual(result['corrected'], '友人の気持ちを察して返事を')

    def test_swallowed_particle_is_restored_with_the_word(self):
        # へんじょ（を の隣の ょ）→ へんじを → 返事を
        result = self.correct('友人の気持ちを察して変所', [('変所', 'へんじょ')])
        self.assertEqual(result['corrected'], '友人の気持ちを察して返事を')

    def test_intruded_key_before_particle(self):
        # へんじょを（を の前に ょ を巻き込んだ）→ へんじを → 返事を
        result = self.correct('友人の気持ちを察して変所を', [('変所を', 'へんじょを')])
        self.assertEqual(result['corrected'], '友人の気持ちを察して返事を')

    def test_correct_lines_untouched(self):
        for line in ('本場の味を楽しむ', '返事を書く', '友人の気持ちを察して返事を書く'):
            with self.subTest(line=line):
                self.assertEqual(self.correct(line)['corrected'], line)


if __name__ == '__main__':
    unittest.main()
