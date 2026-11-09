"""正しい文の誤判定の守り（2026-11-08 補正担当）: 読みの大きく違う語への替え・窓の別読み・言い切りの っ。例は作り例。"""
import unittest

import correction_entry as CE
import dangling_verb as D
import keyslip_window as K
import last_keystroke as LK


class FarGuardTest(unittest.TestCase):
    def test_far_reading_reverted(self):
        line = 'この部屋変な音がする。'
        r = CE._far_reading_guard(line, {'corrected': 'この変化な音がする。', 'odd_spans': []}, {})
        self.assertEqual(r['corrected'], line)
        self.assertEqual(r['odd_spans'], [[2, 5]])

    def test_near_reading_kept(self):
        line = '資料を確認して変身します。'
        res = {'corrected': '資料を確認して返信します。', 'odd_spans': []}
        self.assertEqual(CE._far_reading_guard(line, res, {})['corrected'], res['corrected'])

    def test_keyslip_variant_reading(self):
        self.assertEqual(K.propose('この部屋変だ。'), [])

    def test_exclaim_tsu(self):
        self.assertEqual(D.propose('あいたっ！痛い！'), [])
        self.assertEqual(D.propose('うわっ。'), [])
        self.assertTrue(D.propose('ちょっと待っ！'))

    def test_stem_sa(self):
        self.assertEqual(K.propose('静かさと異様さが同時にあった。'), [])

    def test_bracket_particle(self):
        line = '「表の色」にします。'
        r = CE._bracket_particle_ok(line, {'corrected': line, 'odd_spans': [[5, 6]]})
        self.assertEqual(r['odd_spans'], [])

    def test_mark_key(self):
        self.assertEqual(K._compose([('は',), ('し',), ('゛',), ('め',), ('る',)]), 'はじめる')

    def test_suffix_noun_verb(self):
        line = '掃除機かけなきゃ。'
        r = CE._suffix_noun_verb_ok(line, {'corrected': line, 'odd_spans': [[2, 5]]})
        self.assertEqual(r['odd_spans'], [])
        line2 = '図書館で背借りた。'
        r2 = CE._suffix_noun_verb_ok(line2, {'corrected': line2, 'odd_spans': [[4, 7]]})
        self.assertEqual(r2['odd_spans'], [[4, 7]])

    def test_swap_guard_onkun(self):
        line = '明日から仕事を端攻める。'
        r = CE._kanji_swap_guard(line, {'corrected': '明日から仕事を始める。', 'odd_spans': []})
        self.assertEqual(r['corrected'], '明日から仕事を始める。')

    def test_double_in_word(self):
        import morphology
        t = '準備に手間がかかる場合がある。'
        spans = LK._impossible_kana_spans(t, list(morphology.tokenize(t)))
        self.assertFalse(any('余って' in str(x) for x in spans))

    def test_rarer_word_respell(self):
        line = '辞書のこの字をご覧。'
        self.assertTrue(CE._rarer_word_respell(line, {'corrected': line}, {'corrected': '辞書のこの字を五輪。'}))
        line2 = '会議の死霊を配る。'
        self.assertFalse(CE._rarer_word_respell(line2, {'corrected': line2}, {'corrected': '会議の資料を配る。'}))

    def test_kango_suru(self):
        t = '弟、爆睡してるよ。'
        r = CE._kango_suru_ok(t, {'corrected': t, 'odd_spans': [[2, 4]],
                                  'odd_reasons': [(2, 5, '「爆睡」と「し」は続けて置けない')]})
        self.assertEqual(r['odd_spans'], [])

    def test_kana_noun_verb(self):
        t = '今朝ひげ剃ったよ。'
        r = CE._kana_noun_verb_ok(t, {'corrected': t, 'odd_spans': [[3, 6]],
                                      'odd_reasons': [(3, 6, '「げ」と「剃っ」は続けて置けない')]})
        self.assertEqual(r['odd_spans'], [])
        t2 = '今朝からら剃ったよ。'
        r2 = CE._kana_noun_verb_ok(t2, {'corrected': t2, 'odd_spans': [[3, 6]],
                                        'odd_reasons': [(3, 6, '「ら」と「剃っ」は続けて置けない')]})
        self.assertEqual(r2['odd_spans'], [[3, 6]])

    def test_closed_kana_run(self):
        t = 'そういうことじゃなくて。'
        r = CE._closed_kana_run_ok(t, {'corrected': t, 'odd_spans': [[4, 11]],
                                       'odd_reasons': [(4, 11, '品詞として識別できない（かなの並びに説明が付かない）')]})
        self.assertEqual(r['odd_spans'], [])

    def test_degree_feeling(self):
        import degree_adverb as DA
        self.assertEqual(DA.propose('今回はとても不満です。', None), [])

    def test_noun_suru_over_fix(self):
        t = '有線して補正'
        r = CE._noun_suru(t, {'original': t, 'corrected': '有線と補正', 'changed': True, 'odd_spans': [],
                             'spans': [[2, 3]], 'original_spans': [[2, 4]], 'details': []})
        self.assertEqual(r['corrected'], '優先して補正')

    def test_swap_reading_worse(self):
        self.assertTrue(CE._swap_reading_worse('さしこみ゛て、', 4, '\u3099'))
        self.assertFalse(CE._swap_reading_worse('なへら゛てください', 3, '\u3099'))

    def test_lone_fill_swap_purple(self):
        import inspect
        self.assertIn('CN_LONE_FILL_SWAP', inspect.getsource(CE._lone_mark_fill))

    def test_verb_copula_made(self):
        self.assertTrue(CE._verb_copula_made('土地が肥沃である。', {'corrected': '土地が肥沃である。'},
                                             {'corrected': '土地が開くである。'}))
        self.assertFalse(CE._verb_copula_made('会議の死霊を配る。', {'corrected': '会議の死霊を配る。'},
                                              {'corrected': '会議の資料を配る。'}))

    def test_conj_also_noun(self):
        import pos_seq_odd as P
        self.assertTrue(P._also_common_noun('ただ'))
        self.assertFalse(P._also_common_noun('又'))

    def test_sf_fix_common_pair(self):
        import semantic_fit as F
        got = [r for r in F.propose('熱は水を蒸気に変える。') if r[2]]
        self.assertEqual(got, [])

    def test_unknown_word_guard(self):
        t = '近所で昨日火事が起こった。'
        r = CE._unknown_word_guard(t, {'corrected': '近所で昨日化時が起こった。', 'changed': True, 'odd_spans': []}, {})
        self.assertEqual(r['corrected'], t)


if __name__ == '__main__':
    unittest.main()
