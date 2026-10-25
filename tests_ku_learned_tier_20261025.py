# -*- coding: utf-8 -*-
"""48-KU の守り（本人の立っている語幹）は、語幹が身近さの表で遠く（層3以上か判定なし・everyday_faces にも無い）なら外す
（2026-10-25・うに「初期で直る、使うと直らない判定の見直し」）。作った語だけ。"""
import unittest
import corrector
from vocabulary import VocabularyStore
from seed_vocabulary import load_seed


class _Store(object):
    def __init__(self, table):
        self.table = table
    def lookup(self, reading):
        return self.table.get(reading, [])


class KuLearnedTierTests(unittest.TestCase):
    def test_far_learned_stem_does_not_block_everyday_restore(self):
        # 層3の語幹（学んだ）・層1の戻し先が1つ → 守りを外す
        store = _Store({'こうこ': [{'surface': '一世', 'count': 2}],
                        'こうこう': [{'surface': '高校', 'count': 3}, {'surface': '一世', 'count': 2}]})
        import kango_tier
        if kango_tier.known_usage_tier('高校') != 1 or (kango_tier.known_usage_tier('一世') or 9) <= 2:
            self.skipTest('身近さの表の判定が前提と違う')
        self.assertTrue(corrector._ku_learned_outranks_everyday('一世', 'こうこ', store))

    def test_everyday_learned_stem_keeps_protection(self):
        # 層1〜2の語幹は今までどおり守る（補正→方正 の型）
        store = _Store({'ほせい': [{'surface': '補正', 'count': 5}],
                        'ほうせい': [{'surface': '方正', 'count': 2}]})
        self.assertFalse(corrector._ku_learned_outranks_everyday('補正', 'ほせい', store))

    def test_far_stem_without_restore_target_is_still_not_protected(self):
        # 戻し先が無くても層3の学んだ語幹は守りにしない（初期と同じ道＝紫へ）
        store = _Store({'こうこ': [{'surface': '一世', 'count': 2}]})
        self.assertTrue(corrector._ku_learned_outranks_everyday('一世', 'こうこ', store))


if __name__ == '__main__':
    unittest.main()
