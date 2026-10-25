# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""芯の再構築（項目48-NF）: かなの窓の直後にカタカナが切れ目なく続く（しとゅう**ガク**旅行）ときは、
かなだけを漢字に固めない（補正担当・2026-10-25。本人の語彙に 刺繍 が立つと 刺繍ガク旅行 になっていた）。例文は作ったもの。"""
import unittest

import app as C
from vocabulary import VocabularyStore
from seed_vocabulary import load_seed


class KanaBeforeKatakanaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dict_index import DictIndex
        cls.store = VocabularyStore()
        load_seed(cls.store)
        # 本人の語彙に 刺繍 が立った状態（試験の行を打ち続けると起きる）を作る
        for _ in range(3):
            cls.store.add('ししゅう', '刺繍')
        cls.index = DictIndex()
        cls.index.ensure_built()

    def test_kana_run_glued_to_katakana_is_not_hardened_to_a_learned_kanji_word(self):
        res = C.correct_line('しとゅうガク旅行の班を決めるのに時間がかかった。', self.store,
                             input_method='kana', dict_index=self.index)
        self.assertNotIn('刺繍', res['corrected'])

    def test_kana_run_before_a_particle_is_still_hardened(self):
        # 窓の直後がカタカナでない（助詞）なら、今までどおり漢字に固める道は閉じない
        res = C.correct_line('しとゅうの本を読む。', self.store, input_method='kana', dict_index=self.index)
        self.assertIn('刺繍', res['corrected'])


if __name__ == '__main__':
    unittest.main()
