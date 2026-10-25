# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""読める塊・読める文節を、学習した語や脱字の戻しで別の語に替えない（2026-10-24・うにさんの誤判定・例文は作った文）"""
import unittest
from tests_analysis_async import initial
from correction_entry import correct_line


def run_line(text, vocab=(), ime=()):
    st = initial()
    for rd, sf, n in vocab:
        for _ in range(n):
            st.store.add(rd, sf)
    for sf, rd in ime:
        st.ime_readings.remember(sf, rd)
    return correct_line(text, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                        decisions=st.decisions, context_vec=st.context_vec)


class ReadableRespellTests(unittest.TestCase):
    def test_faithful_chunk_not_respelled_to_learned_word(self):
        # 言った（いった）を、学習した 一致（いっち）へ1打で戻さない
        r = run_line('彼がそう言った', [('いっち', '一致', 2)], [('言った', 'いった')])
        self.assertEqual(r['corrected'], '彼がそう言った')

    def test_readable_clause_not_reread(self):
        # 読める文節（見して）を、1打・脱字の戻しで別の語（燃して・乱して）にしない
        r = run_line('写真を見して', [], [('見して', 'みして')])
        self.assertEqual(r['corrected'], '写真を見して')

    def test_dropped_letter_against_substitution_not_decided(self):
        # 組み立てでは脱字の戻し（ください）が勝つのに、読みの並びで置き換え（くだす）に決めない
        r = run_line('名前を書いてくだい。')
        self.assertNotIn('くだす', r['corrected'])

    def test_part_of_kanji_run_not_respelled(self):
        # 漢字の並びの片方（側｜線）だけを、学習した語（我が）へ1打で替えない
        r = run_line('内側線を歩く', [('わが', '我が', 2)], [('側', 'がわ')])
        self.assertNotIn('我が', r['corrected'])


    def test_faithful_chunk_respelled_to_same_class_word(self):
        # 打ったとおりに読める塊（取れかかる）でも、同じ品詞の覚えた語（取り掛かる）へは今までどおり戻す
        r = run_line('明日から仕事に取れかかる。', [('とりかかる', '取り掛かる', 2)], [('取れかかる', 'とれかかる')])
        self.assertEqual(r['corrected'], '明日から仕事に取り掛かる。')

    def test_noun_then_verb_clause_is_not_readable(self):
        # 名詞のすぐ後に動詞が続く文節（取柄かかる）は読める文節として扱わず、巻き込みを戻す（取り掛かる）
        r = run_line('明日から仕事に取柄かかる。', [('とりかかる', '取り掛かる', 2)], [('取柄かかる', 'とりえかかる')])
        self.assertEqual(r['corrected'], '明日から仕事に取り掛かる。')

if __name__ == '__main__':
    unittest.main()
