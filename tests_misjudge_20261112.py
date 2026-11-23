# -*- coding: utf-8 -*-
"""正しい文を書き換えない（うに 2026-11-12「誤判定を対応する」）。例は作った文。"""
import os
import unittest
from unittest import mock

import keyslip_window as KW
import no_particle_slip as NPS
import semantic_fit as SF
from morphology import tokenize


class _Env:
    def __init__(self, **kw):
        self.kw = kw

    def __enter__(self):
        self.old = {k: os.environ.get(k) for k in self.kw}
        os.environ.update(self.kw)

    def __exit__(self, *a):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class VerbRareReading(unittest.TestCase):
    def test_iru_not_to_hairu(self):
        # 入る を いる と読むのは稀な読み。居る を 入る にしない
        self.assertEqual(SF.propose('部屋に居る'), [])

    def test_switch_off_keeps_old(self):
        with _Env(CN_SF_ALT_MAIN_READING='0'):
            self.assertNotEqual(SF.propose('部屋に居る'), [])


class AdverbialNi(unittest.TestCase):
    def _args(self):
        toks = list(tokenize('適度に乾かす'))
        return [(p.surface, n.surface) for p, n in SF._verb_args(toks, len(toks) - 1)]

    def test_adverbial_ni_is_not_an_argument(self):
        self.assertEqual(self._args(), [])

    def test_switch_off_keeps_old(self):
        with _Env(CN_SF_ADVERBIAL_NI='0'):
            self.assertEqual(self._args(), [('に', '適度')])


class KeyCandidatesWeak(unittest.TestCase):
    def test_weak_one_key_candidates_no_purple(self):
        self.assertEqual(SF.propose('音素が落ちたり'), [])

    def test_switch_off_keeps_old(self):
        with _Env(CN_SF_KEY_WEAK='0', CN_SF_ABSENCE_NEEDS_SIZE='0'):
            self.assertNotEqual(SF.propose('音素が落ちたり'), [])


class AdjectiveAfterNo(unittest.TestCase):
    def test_attributive_adjective(self):
        self.assertEqual(NPS.propose('三人ほどの若い'), [])

    def test_switch_off_keeps_old(self):
        with _Env(CN_NPS_ADJ_ATTR='0'):
            self.assertNotEqual(NPS.propose('三人ほどの若い'), [])


class PrefixAndPlace(unittest.TestCase):
    def _lone(self, s):
        t = list(tokenize(s))
        return [KW._lone_kanji(x, t, k) for k, x in enumerate(t)]

    def test_prefix_noun(self):
        self.assertEqual(self._lone('新校舎'), [False, False])

    def test_place_noun(self):
        self.assertEqual(self._lone('本棚奥'), [False, False])

    def test_switch_off_keeps_old(self):
        with _Env(CN_KEYSLIP_PREFIX_PLACE='0'):
            self.assertIn(True, self._lone('新校舎'))
            self.assertIn(True, self._lone('本棚奥'))


class EverydayOutsideChar(unittest.TestCase):
    def test_everyday_outside_char_not_doubted(self):
        import kanji_doubt as KD
        # 噂 は常用外だが、ふだんの文でよく使う字。鵜 は稀な字なので疑う
        self.assertTrue(KD._everyday_outside('噂'))
        self.assertFalse(KD._everyday_outside('鵜'))


class EverydayExtraTable(unittest.TestCase):
    def test_extra_table_loaded(self):
        import kanji_doubt as KD
        self.assertTrue(KD.everyday_extra())
        self.assertFalse(KD.outside('嬉しい'))

    def test_switch_off_keeps_old(self):
        import kanji_doubt as KD
        with _Env(CN_KD_EXTRA_KANJI='0'):
            self.assertTrue(KD.outside('嬉しい'))


class Design33NoNumberOnly(unittest.TestCase):
    """学習の「直さない」に、数字・記号だけの組を自動で入れない（うに 2026-11-13）。app は tk を読むので関数だけ取り出す"""
    def _classify(self):
        import ast
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, 'app.py'), encoding='utf-8') as f:
            tree = ast.parse(f.read())
        ns = {}
        for n in tree.body:
            if isinstance(n, ast.FunctionDef) and n.name in ('design33_classify', '_d33_has_word'):
                exec(compile(ast.Module([n], []), 'app.py', 'exec'), ns)
        return ns['design33_classify']

    def test_number_only_pair_not_learned(self):
        f = self._classify()
        self.assertEqual(f('合計は46です', [(3, 5, 'fixed', '80-34')], '合計はです'), [])

    def test_word_pair_still_learned(self):
        f = self._classify()
        self.assertEqual(f('明日は会議です', [(3, 5, 'fixed', '開議')], '明日はです'), [('開議', '会議', False)])


class HeadNoCommonNoun(unittest.TestCase):
    def test_head_no_with_common_noun(self):
        # 上の行から続く文を見る前の形の守り（2026-11-21 から既定は上の行を見ない: CN_PREV_LINE_OFF）
        with _Env(CN_PREV_LINE_OFF='0'):
            self.assertEqual(KW._stacked_no(list(tokenize('の本は'))), [])

    def test_switch_off_keeps_old(self):
        with _Env(CN_KEYSLIP_HEAD_NO_COMMON='0'):
            self.assertEqual(KW._stacked_no(list(tokenize('の本は'))), [0])


class HeadParticleKeep(unittest.TestCase):
    def _res(self, line, got):
        return {'original': line, 'corrected': got, 'changed': True, 'details': [['に', '人', 'x']],
                'spans': [[0, 1]], 'original_spans': [[0, 1]], 'odd_spans': []}

    def test_head_particle_not_absorbed(self):
        import head_particle_keep as H
        out = H.keep_head('に別の道具がある', self._res('に別の道具がある', '人別の道具がある'))
        self.assertEqual(out['corrected'], 'に別の道具がある')
        self.assertEqual(out['details'], [])

    def test_switch_off_keeps_old(self):
        import head_particle_keep as H
        with _Env(CN_HEAD_PARTICLE_KEEP='0'):
            out = H.keep_head('に別の道具がある', self._res('に別の道具がある', '人別の道具がある'))
        self.assertEqual(out['corrected'], '人別の道具がある')


class CommonWordPurple(unittest.TestCase):
    """決め手の無い紫が、身近な1語・身近な2語の続きに掛かるなら外す（2026-11-13）。例は作った文"""
    def _res(self, line, a, b, why=''):
        return {'original': line, 'corrected': line, 'changed': False, 'details': [],
                'odd_spans': [[a, b]], 'odd_reasons': [[a, b, why]]}

    def test_two_common_words(self):
        import common_word_purple as C
        self.assertTrue(C.common_text('月末締め'))
        out = C.drop_common('請求は月末締めです', self._res('請求は月末締めです', 3, 7))
        self.assertEqual(out['odd_spans'], [])

    def test_reasoned_purple_kept(self):
        import common_word_purple as C
        out = C.drop_common('請求は月末締めです', self._res('請求は月末締めです', 3, 7, '打ち違いの跡'))
        self.assertEqual(out['odd_spans'], [[3, 7]])

    def test_switch_off_keeps_old(self):
        import common_word_purple as C
        with _Env(CN_COMMON_WORD_PURPLE='0'):
            out = C.drop_common('請求は月末締めです', self._res('請求は月末締めです', 3, 7))
        self.assertEqual(out['odd_spans'], [[3, 7]])


class WholeWordNotBroken(unittest.TestCase):
    def test_whole_word_switch(self):
        import broken_shape as BS
        self.assertTrue(BS._whole_word('補助輪'))
        with _Env(CN_BROKEN_WHOLE_WORD='0'):
            self.assertFalse(BS._whole_word('補助輪'))


class LoneBesideFix(unittest.TestCase):
    """直した所の前に浮いた1字が残るなら紫（2026-11-13）。例は作った文"""
    def test_lone_kanji_left(self):
        import lone_beside_fix as L
        self.assertEqual(L.lone_spans('請求書の金額が口枷っていました', '請求書の金額が口変わっていました'), [(7, 8)])

    def test_normal_noun_with_particle(self):
        import lone_beside_fix as L
        self.assertEqual(L.lone_spans('席を立って手お洗った', '席を立って手を洗った'), [])

    def test_switch_off_keeps_old(self):
        import lone_beside_fix as L
        res = {'corrected': '請求書の金額が口変わっていました', 'odd_spans': [], 'odd_reasons': []}
        with _Env(CN_LONE_BESIDE_FIX='0'):
            self.assertEqual(L.mark('請求書の金額が口枷っていました', res)['odd_spans'], [])


class DanglingKanaRun(unittest.TestCase):
    """抜けた1字の直しが、崩れたかなの並びの中に別のかなの語（けっく）を作るだけなら置かずに紫（2026-11-13）。"""

    def test_kana_word_inside_run_is_purple(self):
        import dangling_verb as D
        self.assertEqual([m[2] for m in D.propose('大阪の友人がけっみなするらしい')], [None])

    def test_before_kanji_still_fixed(self):
        import dangling_verb as D
        self.assertEqual([m[2] for m in D.propose('昨日はずっ家で寝てた')], ['ずっと'])

    def test_switch_off_keeps_old(self):
        import dangling_verb as D
        with _Env(CN_DANGLING_KANA_RUN='0'):
            self.assertEqual([m[2] for m in D.propose('大阪の友人がけっみなするらしい')], ['けっく'])


class ImeClassLetters(unittest.TestCase):
    """IME が落ちた種類で返した記号の1字（行頭の箇条書きの「・」）には紫を付けない（2026-11-13）。"""

    def test_bullet_not_marked(self):
        import ime_class_mark as M
        self.assertEqual(M.fallen_spans('・明日', [(0, 1, 0, 1, 900, 0), (1, 3, 1, 3, 100, 0)]), [])

    def test_kanji_still_marked(self):
        import ime_class_mark as M
        self.assertEqual(M.fallen_spans('積森', [(0, 1, 0, 1, 800, 0), (1, 2, 1, 2, 800, 0)]), [(0, 1), (1, 2)])


class FixedStillOddContext(unittest.TestCase):
    """直した語のほかに比べる内容語の無い行には、費用が高くても紫を足さない（2026-11-13）。"""

    def test_only_fixed_word(self):
        import fixed_still_odd as F
        self.assertFalse(F._has_context('歳で以下', '最大化'))
        self.assertFalse(F._has_context('・歳で以下する', '・最大化する'))
        self.assertFalse(F._has_context('歳で以下', '最大化'))
        self.assertFalse(F._has_context('与悪者', '予約者'))

    def test_with_context(self):
        import fixed_still_odd as F
        self.assertTrue(F._has_context('会員と梅木の手続き', '会員と天気の手続き'))

    def test_switch_off_keeps_old(self):
        import fixed_still_odd as F
        with _Env(CN_FIXED_STILL_ODD_CONTEXT='0'):
            self.assertTrue(F._has_context('歳で以下', '最大化'))


class RespellUndoOverlap(unittest.TestCase):
    """紫の所に前の段の書き換えが掛かって位置を写せない時は、その書き換えだけ元に戻して読み直す（2026-11-13）。"""

    def test_undo_only_overlap(self):
        import odd_respell as O
        self.assertEqual(O._undo_overlap('あいうえおかきく', 'あいXえおかYく', 2, 4), 'あいうえおかYく')

    def test_nothing_to_undo(self):
        import odd_respell as O
        self.assertIsNone(O._undo_overlap('あいうえ', 'あいうえ', 0, 2))


class PrefixAndElongation(unittest.TestCase):
    """誤＋サ変の名詞は古い動詞と見ない・長い並びの頭の直しは伸ばしの直しと見ない・拗音の後ろの小書きの跡（2026-11-13）。"""

    def test_prefix_not_classical(self):
        import correction_entry as ce
        self.assertEqual(ce._classical_verbs('誤入力したキー', 'ごにゅぅりょくしたきー'), [])

    def test_prefix_switch_off(self):
        import correction_entry as ce
        with _Env(CN_FIX_CLASSICAL_PREFIX='0'):
            self.assertEqual(ce._classical_verbs('誤入力したキー', 'ごにゅぅりょくしたきー'), [(0, 1)])

    def test_yoon_small_vowel_inside_word(self):
        import purple_narrow as P
        self.assertTrue(P.bad_small('ごにゅぅりょく', 3))
        self.assertFalse(P.bad_small('ぎゅぅっと', 2))
        self.assertFalse(P.bad_small('にゃぁ', 2))

    def test_unknown_kana_left(self):
        import purple_narrow as P
        self.assertTrue(P._unknown_kana_left('ぎにゅうりょくしたきー', 0))
        self.assertFalse(P._unknown_kana_left('ご入力したきー', 0))


class FixedStillOddFields(unittest.TestCase):
    """タブで区切った欄は欄ごとに見る。直しの無い欄の費用で紫を付けない（2026-11-13）。"""

    def test_unchanged_field_not_marked(self):
        import fixed_still_odd as F
        got = F._still_odd_fields('誤入下キー\tごにゅうりょくしたきー', '誤入下キー\t誤入力したキー')
        self.assertTrue(got is None or got[0] >= 6)

    def test_switch_off_keeps_old(self):
        import fixed_still_odd as F
        with _Env(CN_FIXED_STILL_ODD_FIELDS='0'):
            self.assertEqual(F._still_odd_fields('a\tb', '誤入下キー\t誤入力したキー'), F.still_odd('誤入下キー\t誤入力したキー'))


class KeyslipSwap(unittest.TestCase):
    """隣り合う2字の打つ順の入れ替えも1打の戻しと同じ重さで並べる（2026-11-13）。"""

    def test_swap_variant(self):
        import keyslip_window as K
        self.assertIn('はるから', K._variants('はるらか'))

    def test_switch_off(self):
        import keyslip_window as K
        with _Env(CN_KSW_SWAP='0'):
            self.assertNotIn('はるから', K._variants('はるらか'))


class FarReadingAlign(unittest.TestCase):
    """読みの遠い直しの守りは、直した側の語も元の語の端まで広げ、辞書のほかの読みも比べる（日本→二本、2026-11-14）。"""

    def test_same_reading_kept(self):
        import correction_entry as ce
        res = {'corrected': '二本の線を引く', 'changed': True, 'odd_spans': []}
        self.assertEqual(ce._far_reading_guard('日本の線を引く', res, None)['corrected'], '二本の線を引く')

    def test_switch_off_keeps_old(self):
        import correction_entry as ce
        res = {'corrected': '二本の線を引く', 'changed': True, 'odd_spans': []}
        with _Env(CN_FAR_ALIGN_NEW='0', CN_FAR_DICT_READINGS='0'):
            self.assertEqual(ce._far_reading_guard('日本の線を引く', res, None)['corrected'], '日本の線を引く')



class SuruEndAndGloss(unittest.TestCase):
    """2026-11-14 全体評価の fix1（ime_class_mark・chunk_alone）。例は作った文。"""

    def test_suru_class_is_not_odd(self):
        # 文末の「する」（〜にする・〜をする）の IME の種類は、落ちた字の種類ではない
        import ime_class_mark as M
        self.assertEqual(M.ODD_VERB, frozenset())

    def test_small_kana_fragment_not_picked(self):
        import ime_class_mark as M
        self.assertTrue(M._small_only('ぇ'))
        self.assertFalse(M._small_only('でぇ'))

    def test_reading_gloss_in_brackets_kept(self):
        # 語のすぐ後ろの括弧の中のかなは読みがなの書き添え。単体で見直さない
        import chunk_alone as C
        line = '秋は紅葉（もみじ）を見た'
        got = [(line[s:e], C._gloss(line, s, e)) for s, e, _q in C.chunks(line)]
        self.assertIn(('もみじ', True), got)

    def test_quoted_word_still_reviewed(self):
        # かぎ括弧で前に語の無い所は書き添えではない（単体で見直す）
        import chunk_alone as C
        line = '「かいき゛しつ」を予約した'
        self.assertFalse(any(C._gloss(line, s, e) for s, e, _q in C.chunks(line)))


class NoteShapes(unittest.TestCase):
    """2026-11-14 全体評価の方針 v1 の1・2・5（メモの書き方は文の形でなくても正しい）。例は作った文。"""

    def test_end_noun_familiar_no_purple(self):
        import pos_seq_odd as P
        self.assertFalse(any('で文が終わります' in w for _a, _b, w in P.spots('3都市間を走る列車')))

    def test_end_noun_switch_off(self):
        import pos_seq_odd as P
        with _Env(CN_POS_SEQ_END_FAMILIAR='0'):
            self.assertTrue(any('で文が終わります' in w for _a, _b, w in P.spots('3都市間を走る列車')))

    def test_symbol_between_words_no_purple(self):
        import broken_shape as B
        self.assertFalse(any('記号' in w for _a, _b, w in B.spans('泳ぐ＝運動')))

    def test_symbol_inside_word_purple(self):
        import broken_shape as B
        self.assertTrue(any('記号' in w for _a, _b, w in B.spans('あり＝がとう')))

    def test_reading_gloss_kept(self):
        import reading_gloss as G
        line = '生物（なまもの）と生物（せいぶつ）'
        r = {'corrected': '生物（なまもの）と生物（生物）', 'details': [['せいぶつ', '生物', '読みの区切り']],
             'odd_spans': [[12, 16]], 'spans': [[12, 14]]}
        got = G.keep(line, r)
        self.assertEqual(got['corrected'], line)
        self.assertEqual(got['odd_spans'], [])
        self.assertEqual(got['details'], [])

    def test_reading_gloss_needs_kanji_before(self):
        import reading_gloss as G
        self.assertEqual(G.glosses('「かいき゛しつ」を予約した'), [])

    def test_reading_gloss_same_kana(self):
        import reading_gloss as G
        self.assertEqual(G.glosses('みち（みち）をあるく'), [(3, 5)])
        self.assertEqual(G.lift('みち（みち）をあるく'), ('みちをあるく', [(2, '（みち）')]))
        self.assertEqual(G.glosses('ねこ（いぬ）がいる'), [])
        with _Env(CN_READING_GLOSS_SAME='0'):
            self.assertEqual(G.glosses('みち（みち）をあるく'), [])

    def test_reading_gloss_put_back_original(self):
        import reading_gloss as G
        line = '生物（せいぶつ）を見た'
        bare, cuts = G.lift(line)
        r = {'original': bare, 'corrected': bare, 'odd_spans': []}
        self.assertEqual(G.put_back(line, bare, cuts, r)['original'], line)

    def test_reading_gloss_switch_off(self):
        import reading_gloss as G
        r = {'corrected': '生物（生物）'}
        with _Env(CN_READING_GLOSS='0'):
            self.assertEqual(G.keep('生物（せいぶつ）', r)['corrected'], '生物（生物）')


class KataOneAndSymbolJoin(unittest.TestCase):
    """2026-11-14 全体評価の方針 v1 の3・v2 の A。例は作った文。"""

    def test_kata_one_suffix_kanji_no_purple(self):
        import broken_shape as B
        self.assertEqual([x for x in B.spans('音がオ段で終わる') if '片仮名' in x[2]], [])

    def test_kata_one_before_word_still_purple(self):
        import broken_shape as B
        self.assertTrue(any('片仮名' in x[2] for x in B.spans('会議をチ時間ずらす')))

    def test_kata_one_switch_off(self):
        import broken_shape as B
        # オ段 は表の1語でもあるので、CN_KATA_ONE_KNOWN（2026-11-22）も切って前の形を見る
        with _Env(CN_KATA_ONE_COMPOUND='0', CN_KATA_ONE_KNOWN='0'):
            self.assertTrue(any('片仮名' in x[2] for x in B.spans('音がオ段で終わる')))
        with _Env(CN_KATA_ONE_COMPOUND='0'):
            self.assertEqual([x for x in B.spans('音がオ段で終わる') if '片仮名' in x[2]], [])

    def test_symbol_join_not_merged(self):
        import symbol_join_keep as K
        got = K.keep('買う＝かう', {'corrected': '解放買う', 'details': [['買う＝', '解放', 'かな入力']],
                                  'odd_spans': [[0, 1]], 'odd_reasons': [[0, 1, '直し先を決められない']]})
        self.assertEqual((got['corrected'], got['odd_spans']), ('買う＝かう', []))

    def test_symbol_inside_word_left_to_others(self):
        import symbol_join_keep as K
        self.assertEqual(K.joining_symbols('あり＝がとう'), [])

    def test_symbol_join_switch_off(self):
        import symbol_join_keep as K
        with _Env(CN_SYMBOL_JOIN_KEEP='0'):
            self.assertEqual(K.keep('買う＝かう', {'corrected': '解放買う'})['corrected'], '解放買う')


class EndNounDictionary(unittest.TestCase):
    """2026-11-14 全体評価の方針 v2 の I。例は作った文。"""

    def test_dictionary_noun_not_marked(self):
        import pos_seq_odd as P
        self.assertFalse(any('で文が終わります' in w for _a, _b, w in P.spots('遠くに見える山脈')))

    def test_switch_off_uses_familiar_table_only(self):
        import pos_seq_odd as P
        with _Env(CN_POS_SEQ_END_DICT='0'):
            self.assertTrue(any('で文が終わります' in w for _a, _b, w in P.spots('遠くに見える山脈')))


class ReasonlessPurple(unittest.TestCase):
    """2026-11-14 全体評価の方針 v2 の K・L・M。例は作った文。"""

    def test_suru_form_dropped(self):
        import odd_reason_fill as F
        got = F.fill('カレーを煮込みする', {'corrected': 'カレーを煮込みする', 'odd_spans': [[4, 9]], 'odd_reasons': []})
        self.assertEqual(got['odd_spans'], [])

    def test_list_item_dropped(self):
        import odd_reason_fill as F
        got = F.fill('りんご・みかん・バナナ', {'corrected': 'りんご・みかん・バナナ', 'odd_spans': [[4, 7]], 'odd_reasons': []})
        self.assertEqual(got['odd_spans'], [])

    def test_other_reasonless_gets_reason(self):
        import odd_reason_fill as F
        got = F.fill('あしたはれる', {'corrected': 'あしたはれる', 'odd_spans': [[3, 6]], 'odd_reasons': []})
        self.assertEqual((got['odd_spans'], got['odd_reasons']), ([[3, 6]], [(3, 6, F.GENERIC)]))

    def test_switch_off(self):
        import odd_reason_fill as F
        r = {'corrected': 'カレーを煮込みする', 'odd_spans': [[4, 9]], 'odd_reasons': []}
        with _Env(CN_ODD_REASON_FILL='0'):
            self.assertIs(F.fill('カレーを煮込みする', r), r)

    def test_attr_end_noun_not_extra(self):
        import broken_shape as B
        self.assertFalse(any('言い終わりの後ろ' in x[2] for x in B.spans('母が描いた画')))

    def test_suffix_then_noun_still_purple(self):
        import odd_reason_fill as F
        line = '棚の中の流布委書類'
        got = F.fill(line, {'corrected': line, 'odd_spans': [[4, 6]], 'odd_reasons': []})
        self.assertEqual(got['odd_spans'], [[4, 6]])


class DictWordKeep(unittest.TestCase):
    """2026-11-14 全体評価の方針 v2 の N・O。例は作った文。"""

    def test_weak_rewrite_of_dictionary_word_undone(self):
        import dict_word_keep as K
        got = K.keep('読書に充てている', {'corrected': '読書に当てている', 'details': [['充て', '当て', '意味の分類']],
                                       'odd_spans': []})
        self.assertEqual(got['corrected'], '読書に充てている')

    def test_other_stage_rewrite_kept(self):
        import dict_word_keep as K
        got = K.keep('読書に充てている', {'corrected': '読書に当てている', 'details': [['充て', '当て', 'かな入力']]})
        self.assertEqual(got['corrected'], '読書に当てている')

    def test_switch_off(self):
        import dict_word_keep as K
        with _Env(CN_DICT_WORD_KEEP='0'):
            got = K.keep('読書に充てている', {'corrected': '読書に当てている', 'details': [['充て', '当て', '意味の分類']]})
            self.assertEqual(got['corrected'], '読書に当てている')

    def test_same_reading_pair_kept(self):
        # Batch620: 語の組の直しで同じ読みの表記の選び違い（作った例: 会議の死霊）は戻さない
        import dict_word_keep as K
        got = K.keep('会議の死霊を配る', {'corrected': '会議の資料を配る', 'details': [['死霊', '資料', '語の組']],
                                       'odd_spans': []})
        self.assertEqual(got['corrected'], '会議の資料を配る')
        with _Env(CN_DICT_WORD_KEEP_SAME_READING='0'):
            got = K.keep('会議の死霊を配る', {'corrected': '会議の資料を配る', 'details': [['死霊', '資料', '語の組']],
                                           'odd_spans': []})
            self.assertEqual(got['corrected'], '会議の死霊を配る')

    def test_prefix_noun_parts_not_rare(self):
        # Batch621: 接頭詞1字＋名詞1字に分けて読める2字の語（作った例: 毎行）は稀の紫にしない
        import last_keystroke as L
        self.assertTrue(L._prefix_noun_parts('毎行'))
        self.assertFalse(L._prefix_noun_parts('選択'))
        with _Env(CN_RARE_PREFIX_PARTS='0'):
            self.assertFalse(L._prefix_noun_parts('毎行'))

    def test_head_keyslip_rest_broken(self):
        # Batch622: 前の行から続きうる行でも、頭の助詞を外した残りが読めない1キーの直しは通す（作った例）
        import head_particle_keep as H
        d = [['の日っています', '残っています', 'かな入力の1キーの打ち違い']]
        got = H.keep_head('の日っています', {'corrected': '残っています', 'details': d, 'odd_spans': []}, '本の下')
        self.assertEqual(got['corrected'], '残っています')
        with _Env(CN_HEAD_KEYSLIP_COST='0', CN_PREV_LINE_OFF='0'):
            got = H.keep_head('の日っています', {'corrected': '残っています', 'details': d, 'odd_spans': []}, '本の下')
            self.assertEqual(got['corrected'], 'の日っています')

    def test_keyslip_head_te_aux(self):
        # Batch622: 名詞＋って＋補助の動詞（作った例: 行の頭の の日っています）は崩れた跡
        import keyslip_window as W
        from morphology import tokenize
        toks = list(tokenize('の日っています'))
        self.assertTrue(W._te_aux_after_noun(toks, 1))
        toks = list(tokenize('の日って楽しい'))
        self.assertFalse(W._te_aux_after_noun(toks, 1))

    def test_te_aux_bad_de(self):
        # Batch623: く の動詞のイ音便＋で（作った例: 書いでいる）は て＋補助の動詞の守りに入れない
        import guess_back as G
        self.assertEqual(G._te_aux_spots('書いでいる'), [])
        self.assertEqual(G._te_aux_spots('泳いでいる'), [(2, 3)])
        with _Env(CN_GUESS_BACK_TE_AUX_DE='0'):
            self.assertEqual(G._te_aux_spots('書いでいる'), [(2, 3)])

    def test_respell_off_mark(self):
        # Batch624: 紫の所に掛からない読み直しは採らない（作った例の位置で見る）
        import odd_respell as O
        self.assertTrue(O._off_mark('察して返事', 'そっと返事', 3, 5))
        self.assertFalse(O._off_mark('察して変字', '察して返事', 3, 5))
        with _Env(CN_RESPELL_OFF_MARK='0'):
            self.assertFalse(O._off_mark('察して返事', 'そっと返事', 3, 5))

    def test_tail_drop_mark(self):
        # Batch625: 行の終わりの1字を余計な1打として落とした直しで、その字のキーの隣に助詞があれば紫（作った例）
        import guess_back as G
        r = G.tail_drop_mark('てがみほ', {'corrected': '手紙', 'details': [('てがみほ', '手紙', 'かな入力')], 'odd_spans': []})
        self.assertEqual(r['corrected'], '手紙を')
        self.assertEqual(r['odd_spans'], [])
        with _Env(CN_GUESS_BACK_TAIL_WO='0'):
            r = G.tail_drop_mark('てがみほ', {'corrected': '手紙', 'details': [('てがみほ', '手紙', 'かな入力')],
                                            'odd_spans': []})
            self.assertEqual([tuple(x) for x in r['odd_spans']], [(0, 4)])
        with _Env(CN_GUESS_BACK_TAIL_DROP='0'):
            r = G.tail_drop_mark('てがみほ', {'corrected': '手紙', 'details': [('てがみほ', '手紙', 'かな入力')],
                                            'odd_spans': []})
            self.assertEqual(r['odd_spans'], [])

    def test_batch627_guards(self):
        # Batch627: 半角英字を消さない・身近な語だけ替えて珍しい語を残す読み直しを採らない・頼みの形の語の組（作った例）
        import odd_respell as O
        import dict_word_keep as K
        self.assertTrue(O._ascii_letter_dropped('n回目を見る', '回目を見る'))
        self.assertFalse(O._ascii_letter_dropped('さm歩に行く', '散歩に行く'))
        self.assertFalse(O._ascii_letter_dropped('隣のｌ席', '隣の席'))
        self.assertTrue(O._common_changed_rare_left('値総尺', '当てそうしゃく', 0, 3))
        self.assertTrue(K._request_frame('確認お願いします', 2))
        self.assertFalse(K._request_frame('確認します', 2))

    def test_derived_verb_not_rare(self):
        import ime_reconvert as I
        import morphology as M
        toks = list(M.tokenize('読みかけの本'))
        if not I._freq():
            self.skipTest('語の表が無い')
        self.assertLess(I._token_rarity(toks[0], toks), I.DOUBT)


class LabelKeigoCodePlace(unittest.TestCase):
    """2026-11-14 全体評価の方針 v2 の F・G・P・R・S・T。例は作った文。"""

    def _fill(self, line, a, b, why=''):
        import odd_reason_fill as F
        return F.fill(line, {'corrected': line, 'odd_spans': [[a, b]], 'odd_reasons': [(a, b, why)] if why else []})

    def test_label_line_dropped(self):
        self.assertEqual(self._fill('事務用品', 2, 4, '「用品」はあまり使わない語です。')['odd_spans'], [])

    def test_keigo_dropped(self):
        self.assertEqual(self._fill('ご用件をお申しつけください', 6, 13, '品詞として識別できない')['odd_spans'], [])

    def test_place_dropped(self):
        self.assertEqual(self._fill('福岡県福岡市', 0, 6, '異様だと見たが、直し先を決められなかった')['odd_spans'], [])

    def test_code_run(self):
        import odd_reason_fill as F
        self.assertEqual(F.code_runs('型番はUD-27Kです'), [(3, 9)])

    def test_code_rewrite_undone(self):
        import dict_word_keep as K
        got = K.keep('型番はUD-27Kです', {'corrected': '型番はID-27Kです', 'details': [['UD', 'ID', '英語']]})
        self.assertEqual(got['corrected'], '型番はUD-27Kです')

    def test_label_with_particle_kept(self):
        got = self._fill('会議の死霊', 3, 5, '「死霊」はあまり使わない語です。')
        self.assertEqual(got['odd_spans'], [[3, 5]])

    def test_label_switch_off(self):
        with _Env(CN_ODD_REASON_LABEL='0'):
            self.assertEqual(self._fill('事務用品', 2, 4, '組が少ない')['odd_spans'], [[2, 4]])

    def test_specific_reason_kept_on_label_line(self):
        got = self._fill('メモ＊リスト', 2, 3, '片仮名の語のあいだの＊は、並べる＊かもしれません')
        self.assertEqual(got['odd_spans'], [[2, 3]])

    def test_specific_reason_kept_with_particle(self):
        got = self._fill('リンゴをバナナ', 3, 4, '「を」は、かな入力で隣のキーを打ったか、一緒に押したかもしれません')
        self.assertEqual(got['odd_spans'], [[3, 4]])


class RewriteDoubt(unittest.TestCase):
    """書き換えは採るが崩れが残る所に紫（rewrite_doubt・2026-11-14）"""

    def test_clash_left_gets_purple(self):
        import rewrite_doubt as D
        line = '出るをがナッタ'
        got = D.mark(line, None, {'corrected': 'モデルをがなった', 'changed': True, 'odd_spans': [],
                                  'odd_reasons': [(2, 4, '「を」と「が」は続けて置けない')]})
        self.assertIn((2, 4), [tuple(x[:2]) for x in got['odd_spans']])
        self.assertEqual(got['corrected'], 'モデルをがなった')

    def test_clean_fix_no_purple(self):
        import rewrite_doubt as D
        got = D.mark('かいぎはじゅうじだ', None, {'corrected': '会議は十時だ', 'changed': True, 'odd_spans': []})
        self.assertEqual(got['odd_spans'], [])

    def test_same_reading_not_checked(self):
        import rewrite_doubt as D
        with _Env(CN_REWRITE_DOUBT_FRAME='1'):
            got = D.mark('手をきれいに洗う', None, {'corrected': '手を綺麗に洗う', 'changed': True, 'odd_spans': []})
        self.assertEqual(got['odd_spans'], [])

    def test_switch_off(self):
        import rewrite_doubt as D
        with _Env(CN_REWRITE_DOUBT='0'):
            r = {'corrected': 'モデルをがなった', 'odd_spans': [], 'odd_reasons': [(2, 4, '「を」と「が」は続けて置けない')]}
            self.assertIs(D.mark('出るをがナッタ', None, r), r)


class DanglingAdj(unittest.TestCase):
    def test_no_dangling_adjective(self):
        import dangling_verb as V
        self.assertTrue(V._dangling_adj('手伝ってよくっさい', 4, 7))
        self.assertFalse(V._dangling_adj('よくって', 0, 3))
        got = V.propose('手伝ってくっさい')
        self.assertNotEqual(got[0][2], 'よくっ')


class KeyslipRelNoun(unittest.TestCase):
    def test_lone_before_relational_noun(self):
        import keyslip_window as K
        from morphology import tokenize
        run = [t for t in tokenize('夏以降') ]
        self.assertFalse(K._plain_lone(run))

    def test_lone_head_after_sahen_noun(self):
        import keyslip_window as K
        from morphology import tokenize
        self.assertFalse(K._plain_lone(list(tokenize('洗濯籠'))))
        with _Env(CN_KEYSLIP_UNSURE_SAHEN_HEAD='0'):
            self.assertTrue(K._plain_lone(list(tokenize('洗濯籠'))))



class KanaLineVerbAndPurple(unittest.TestCase):
    def test_same_reading_rewrite_gets_no_still_odd(self):
        # 既定は見る（前のまま）。=1 の試しで、かなに戻した語（水→みず）だけが費用を上げている行を外す
        import fixed_still_odd as F
        self.assertFalse(F._only_same_reading('みずをのむ。', 'みずを飲む。'))
        with _Env(CN_FIXED_STILL_ODD_SAME_READING='1'):
            self.assertTrue(F._only_same_reading('みずをのむ。', 'みずを飲む。'))
            self.assertFalse(F._only_same_reading('てがみをかくた。', 'てがみを書いた。'))
            got = F._mark('みずをのむ。', {'corrected': 'みずを飲む。', 'odd_spans': [],
                                          '_kana_kept': ('水をのむ。', [(0, 2)])})
            self.assertFalse(got.get('odd_spans'))
            got = F._mark('みずをのむ。', {'corrected': 'みずを飲む。', 'odd_spans': []})
            self.assertTrue(got.get('odd_spans'))

    def test_sentence_final_noun_after_wo_read_as_verb(self):
        import wago_verb as W
        r = {'corrected': 'てがみをかく。', 'changed': False}
        self.assertEqual(W.repair_line('てがみをかく。', r)['corrected'], 'てがみを書く。')
        with _Env(CN_WAGO_VERB_END_NOUN='0'):
            self.assertEqual(W.repair_line('てがみをかく。', dict(r))['corrected'], 'てがみをかく。')



class KeyslipNumberSpace(unittest.TestCase):
    def test_counter_after_number_and_space(self):
        import keyslip_window as K
        self.assertTrue(K._after_number_counter('20 日後', 3, 5))
        self.assertFalse(K._after_number_counter('20日後', 2, 4))
        self.assertFalse(K._after_number_counter('あの 日後', 3, 5))


class KataAfterPrefix(unittest.TestCase):
    def test_prefix_and_loanword(self):
        import broken_shape
        why = [x[2] for x in broken_shape.spans('新タブ表示ウィンドウが') or ()]
        self.assertNotIn('片仮名が混じっています', why)
        with _Env(CN_KATA_AFTER_PREFIX='0'):
            why = [x[2] for x in broken_shape.spans('新タブ表示ウィンドウが') or ()]
            self.assertIn('片仮名が混じっています', why)


class ParallelPair(unittest.TestCase):
    def test_parallel_compound_weak_purple_dropped(self):
        import odd_reason_fill as F
        line = '食前食後の薬'
        r = {'corrected': line, 'odd_spans': [(2, 4)],
             'odd_reasons': [(2, 4, '「食後」はあまり使わない語です。同じ読みか1打違いの読みで変換し直すと、より自然な文になります')]}
        self.assertFalse(F.fill(line, r)['odd_spans'])
        with _Env(CN_ODD_REASON_PARALLEL='0'):
            self.assertTrue(F.fill(line, r)['odd_spans'])


class LoneKanaHead(unittest.TestCase):
    def test_one_kana_noun_sentence_kept(self):
        import lone_kana_head as L
        self.assertEqual(L.spans('きをうえる。'), [(0, 5)])
        self.assertEqual(L.spans('わたしは、てをふる。'), [(5, 9)])
        self.assertEqual(L.spans('おとうとがえきまでくる'), [])      # お は おとうと の頭
        self.assertEqual(L.spans('辺（あた）りを見回す'), [])         # 閉じ括弧の後ろは語の途中
        r = {'corrected': 'きょうえる。', 'changed': True, 'odd_spans': [], 'odd_reasons': []}
        self.assertEqual(L.keep('きをうえる。', r)['corrected'], 'きをうえる。')
        r = {'corrected': 'てをふる。', 'changed': False, 'odd_spans': [(2, 3)], 'odd_reasons': [(2, 3, 'x')]}
        self.assertFalse(L.keep('てをふる。', r)['odd_spans'])
        with _Env(CN_LONE_KANA_HEAD='0'):
            self.assertIs(L.keep('てをふる。', r), r)


class KeyslipLoneAfterNo(unittest.TestCase):
    def test_common_lone_noun_after_no_not_unsure(self):
        import keyslip_window as K
        from morphology import tokenize
        t = list(tokenize('山の木を見る'))
        self.assertTrue(K._lone_after_no(t, 2, 3))
        self.assertFalse(K._lone_after_no(t, 0, 1))      # 頭の字は「の」の後ろでない
        with _Env(CN_KEYSLIP_UNSURE_AFTER_NO='0'):
            self.assertFalse(K._lone_after_no(t, 2, 3))


class PurpleHomophone(unittest.TestCase):
    def test_one_clean_same_reading_face_taken(self):
        import purple_homophone as P
        from morphology import tokenize
        t = [x for x in tokenize('続きを離す') if x.surface == '離す'][0]
        self.assertIn('話す', P._candidates(t))
        res = {'corrected': '続きを離す', 'changed': False, 'odd_spans': [(3, 4)], 'odd_reasons': [(3, 4, 'x')]}
        clean = lambda new: {'corrected': new, 'odd_spans': [] if '話す' in new else [(3, 4)]}
        with _Env(CN_PURPLE_HOMOPHONE='1'):
            got = P.respell('続きを離す', res, clean)
            self.assertEqual(got['corrected'], '続きを話す')
            self.assertFalse(got['odd_spans'])
            both = lambda new: {'corrected': new, 'odd_spans': []}      # 2つ通るなら採らない
            keep = P._candidates
            P._candidates = lambda tok: ['話す', '放す']
            try:
                self.assertIs(P.respell('続きを離す', res, both), res)
            finally:
                P._candidates = keep
        self.assertEqual(P.respell('続きを離す', res, clean)['corrected'], '続きを話す')   # 既定はオン
        with _Env(CN_PURPLE_HOMOPHONE='0'):
            self.assertIs(P.respell('続きを離す', res, clean), res)


class Batch548(unittest.TestCase):
    def test_suffix_kanji_with_kun_reading_read_as_on(self):
        import keyslip_window as K
        from morphology import tokenize
        t = list(tokenize('表示行'))
        self.assertTrue(K._suffix_after_common(t, 0, 2))
        with _Env(CN_KEYSLIP_SUFFIX_ON_ANY='0'):
            self.assertFalse(K._suffix_after_common(t, 0, 2))

    def test_guess_rewrite_with_purple_goes_back(self):
        import guess_back as G
        r = {'corrected': '机れる', 'details': [('本', '', 'かな入力')], 'odd_spans': [(0, 1)], 'odd_reasons': [(0, 1, 'x')]}
        got = G.back('机本れる', r)
        self.assertEqual(got['corrected'], '机本れる')
        self.assertIn((1, 2), got['odd_spans'])
        with _Env(CN_GUESS_BACK='0'):
            self.assertIs(G.back('机本れる', r), r)

    def test_respell_does_not_break_earlier_fix(self):
        import correction_entry as ce
        before = {'corrected': 'テーブルを', 'details': [('てーぶる', 'テーブル', '外来語')]}
        broke = {'corrected': 'てーふるを', 'details': [('てーぶる', 'テーブル', '外来語'), ['ぶ', 'ふ', '紫の所の打ち違い']]}
        redo = {'corrected': 'てーぶるを', 'details': [('てーぶる', 'テーブル', '外来語'), ['テーブル', 'てーぶる', 'x']]}
        self.assertTrue(ce._respell_breaks_fix(before, broke))
        self.assertFalse(ce._respell_breaks_fix(before, redo))
        with _Env(CN_RESPELL_KEEP_FIX='0'):
            self.assertFalse(ce._respell_breaks_fix(before, broke))


class Batch549(unittest.TestCase):
    def test_common_loanword_inside_sahen_compound(self):
        import broken_shape as B
        self.assertEqual(B.spans('検索キー入力'), [])
        with _Env(CN_KATA_IN_COMPOUND='0', CN_KATA_KNOWN_NOUN='0'):
            self.assertTrue(B.spans('検索キー入力'))

    def test_te_not_added_inside_kana_noun(self):
        import te_dropped as T
        self.assertEqual(T.propose('ぜんぶひらがなであり'), [])
        with _Env(CN_TE_KANA_NOUN_SPLIT='0', CN_TE_NOUN_ARU='0'):
            self.assertTrue(T.propose('ぜんぶひらがなであり'))

    def test_kana_dictionary_entry_generic_purple_dropped(self):
        import odd_reason_fill as F
        line = '雨がふるいっぽうで、'
        r = {'corrected': line, 'odd_spans': [[4, 9]], 'odd_reasons': [(4, 9, F.GENERIC)]}
        self.assertFalse(F.fill(line, r)['odd_spans'])
        with _Env(CN_ODD_REASON_KANA_ENTRY='0'):
            self.assertTrue(F.fill(line, r)['odd_spans'])


class Batch550(unittest.TestCase):
    def test_double_case_particle_around_nado(self):
        import particle_dup as P
        line = '本をなどを読んだ'
        r = {'corrected': line, 'odd_spans': [(1, 4)], 'odd_reasons': [(1, 4, 'x')]}
        got = P.fix(line, r)
        self.assertEqual(got['corrected'], '本などを読んだ')
        self.assertFalse(got['odd_spans'])
        plain = {'corrected': line, 'odd_spans': []}
        self.assertIs(P.fix(line, plain), plain)                 # 紫の無い所は見ない
        with _Env(CN_PARTICLE_DUP='0'):
            self.assertIs(P.fix(line, r), r)

    def test_stale_still_odd_purple_dropped(self):
        import guess_back as G, fixed_still_odd as F
        r = {'corrected': 'あいう', 'odd_spans': [(0, 2)], 'odd_reasons': [(0, 2, F.REASON)]}
        self.assertTrue(G.back('あいう', r)['odd_spans'])            # 既定はオフ
        with _Env(CN_GUESS_BACK_STALE='1'):
            self.assertFalse(G.back('あいう', r)['odd_spans'])



class Batch551HeadGuardPrev(unittest.TestCase):
    """行の頭の助詞の守りは、1行前が文の途中で終わる行のときだけ（空の行・文の終わりの次の行では守らない）。"""

    def _res(self):
        return {'original': 'に別の道具がある', 'corrected': '人別の道具がある', 'changed': True,
                'details': [['に', '人', 'x']], 'spans': [[0, 1]], 'original_spans': [[0, 1]], 'odd_spans': []}

    def setUp(self):
        # 上の行を見る前の形の試験（2026-11-21 から既定は上の行を見ない: CN_PREV_LINE_OFF）
        self._env = _Env(CN_PREV_LINE_OFF='0')
        self._env.__enter__()

    def tearDown(self):
        self._env.__exit__(None, None, None)

    def test_may_continue(self):
        import correction_entry as ce
        self.assertTrue(ce.head_may_continue())
        self.assertTrue(ce.head_may_continue('ほかの道具のほか'))
        self.assertFalse(ce.head_may_continue(None))
        self.assertFalse(ce.head_may_continue(''))
        self.assertFalse(ce.head_may_continue('今日は休みです。'))

    def test_keep_head_with_previous(self):
        import head_particle_keep as H
        self.assertEqual(H.keep_head('に別の道具がある', self._res(), 'ほかの道具のほか')['corrected'], 'に別の道具がある')
        got = H.keep_head('に別の道具がある', self._res(), None)
        self.assertEqual(got['corrected'], 'に別の道具がある')          # 前から続かない行: 戻して紫
        self.assertEqual([tuple(x[:2]) for x in got['odd_spans']], [(0, 1)])
        ks = self._res()
        ks['details'] = [['に', '人', H.KEYSLIP_REASON]]
        self.assertEqual(H.keep_head('に別の道具がある', ks, None)['corrected'], '人別の道具がある')  # 1キーの窓の直しは通す

    def test_switch_off_keeps_guard(self):
        import head_particle_keep as H
        with _Env(CN_HEAD_GUARD_PREV='0'):
            self.assertEqual(H.keep_head('に別の道具がある', self._res(), None)['corrected'], 'に別の道具がある')


class Batch551StaleWithDetails(unittest.TestCase):
    def test_stale_dropped_when_reverted_fix_left_details(self):
        import guess_back as G, fixed_still_odd as F
        r = {'corrected': 'あいう', 'odd_spans': [(0, 2)], 'odd_reasons': [(0, 2, F.REASON)], 'details': [['あ', 'い', 'x']]}
        self.assertFalse(G.back('あいう', r)['odd_spans'])
        with _Env(CN_GUESS_BACK_STALE_DET='0'):
            self.assertTrue(G.back('あいう', r)['odd_spans'])


class Batch553FewestPhysical(unittest.TestCase):
    def test_physical_one(self):
        import odd_respell as O
        self.assertTrue(O._physical_one('はしい', 'はし'))       # 抜いた い は し の隣のキー（巻き込み）
        self.assertFalse(O._physical_one('はうし', 'はし'))      # う は隣のキーではない
        self.assertTrue(O._physical_one('はし', 'はと'))         # し と と は隣のキー
        self.assertFalse(O._physical_one('はし', 'はき'))


class Batch554(unittest.TestCase):
    def test_broad_predicate_not_purple(self):
        import pair_choice as P
        self.assertFalse(P._pred_marks(list(tokenize('家の鍵を閉める')), P._table()[0]))
        with _Env(CN_PAIR_PRED_BROAD='0'):
            self.assertTrue(P._pred_marks(list(tokenize('家の鍵を閉める')), P._table()[0]))

    def test_verb_then_noun(self):
        import odd_reason_fill as O
        toks = list(tokenize('後で守る決まり'))
        self.assertTrue(O._verb_then_noun(toks, 2, 7))
        self.assertFalse(O._verb_then_noun(list(tokenize('本を読む')), 2, 4))


class Batch555(unittest.TestCase):
    def test_interj_tte(self):
        import odd_reason_fill as O
        self.assertTrue(O._interj_tte(list(tokenize('ねえってばー')), 0, 6))
        self.assertFalse(O._interj_tte(list(tokenize('本を読む')), 0, 4))
    def test_split_kana_verb(self):
        import odd_reason_fill as O
        self.assertTrue(O._split_kana_verb(list(tokenize('車をよける')), 1, 3))
        self.assertFalse(O._split_kana_verb(list(tokenize('本を読む')), 1, 2))
    def test_lone_kanji_joins_unit(self):
        import broken_shape as B
        self.assertFalse(B.spans('毎日同じ所で採水し、測った'))
        with _Env(CN_BROKEN_LONE_JOIN='0'):
            self.assertTrue(B.spans('毎日同じ所で採水し、測った'))


class Batch558VarCount(unittest.TestCase):
    def test_spots(self):
        import var_count as V
        self.assertEqual(V.spots('n個めを見る'), [0])
        self.assertEqual(V.spots('k番目の要素'), [0])
        self.assertEqual(V.spots('abc個'), [])
        self.assertEqual(V.spots('本を読む'), [])
        self.assertEqual(V.spots('駅b二極へ行く'), [])
        self.assertEqual(V.spots('駅まで車ｄ目へ'), [])
        self.assertEqual(V.spots('リストのn番目'), [4])

    def test_unmask(self):
        import var_count as V
        r = V._unmask('n回目の試行', '1回目の試行', {'corrected': '1回目の試行', 'changed': False}, [0])
        self.assertEqual(r['corrected'], 'n回目の試行')
        self.assertIsNone(V._unmask('n回目', '1回目', {'corrected': '回目'}, [0]))


class Batch560SahenTail(unittest.TestCase):
    def test_noun_then_sahen(self):
        import keyslip_window as K
        self.assertEqual(K.propose('列追加する'), [])
        with _Env(CN_KEYSLIP_UNSURE_SAHEN_TAIL='0', CN_KEYSLIP_UNSURE_AFFIX='0'):
            self.assertTrue(K.propose('列追加する'))


class Batch565(unittest.TestCase):
    def test_label_cell(self):
        import odd_reason_fill as O
        line = '名詞\t物の名前を表す'
        r = {'corrected': line, 'odd_spans': [(0, 2)], 'odd_reasons': [(0, 2, '「名詞」はあまり使わない語です')]}
        self.assertFalse(O.fill(line, r)['odd_spans'])
        with _Env(CN_ODD_REASON_LABEL_CELL='0'):
            self.assertTrue(O.fill(line, r)['odd_spans'])

    def test_kata_sahen_tail(self):
        import keyslip_window as K
        self.assertEqual(K.propose('楽器、耳コピー'), [])


class Batch566ImeField(unittest.TestCase):
    def test_narrow(self):
        import odd_reason_fill as O
        line = '簡易入力の再入力'
        r = {'corrected': line, 'odd_spans': [(0, 8)], 'odd_reasons': [(0, 8, O.IME_FIELD)]}
        self.assertFalse(O.narrow_ime_field(line, r)['odd_spans'])
        line = 'あしたはかいぎにさんかすろ'
        r = {'corrected': line, 'odd_spans': [(0, 13)], 'odd_reasons': [(0, 13, O.IME_FIELD)]}
        self.assertEqual(O.narrow_ime_field(line, r)['odd_spans'], [(6, 13)])
        with _Env(CN_ODD_REASON_IME_FIELD='0'):
            self.assertEqual(O.narrow_ime_field(line, r)['odd_spans'], [(0, 13)])


class Batch584(unittest.TestCase):
    """2026-11-16 うに: 句点のない長い文の全体に紫。例は作った文。"""

    def test_ime_field_with_inner_reason_narrows(self):
        import odd_reason_fill as F
        line = '新しい機能を追加したので使い方を説明書に書いておいて明日の会議で皆さんに紹介する予定です'
        n = len(line)
        r = {'corrected': line, 'odd_spans': [(0, n)], 'odd_reasons': [(0, n, F.IME_FIELD), (18, 20, 'x')]}
        out = F.narrow_ime_field(line, r)
        self.assertEqual(out['odd_spans'], [(18, 20)])
        self.assertEqual(out['odd_reasons'], [(18, 20, 'x')])
        with _Env(CN_ODD_REASON_IME_FIELD_MIXED='0'):
            self.assertEqual(F.narrow_ime_field(line, r)['odd_spans'], [(0, n)])


class Batch583(unittest.TestCase):
    """2026-11-15 v1.19.0 の CI: 混ぜ書きの外来語に IME の読めなかった印を付けない。IME の答えは作った並び。"""

    def test_ime_class_skips_mixed_loan(self):
        import ime_class_mark as M
        words = [(0, 1, 0, 1, 900, 3), (1, 5, 1, 5, 103, 11), (5, 6, 5, 6, 0, 10), (6, 9, 6, 9, 211, 3),
                 (9, 10, 9, 10, 0, 2), (10, 11, 10, 11, 907, 3)]
        M.set_words_provider(lambda t: words)
        self.addCleanup(M.set_words_provider, None)
        r = {'corrected': 'スくりーんをください。', 'odd_spans': []}
        self.assertEqual(M._mark('スくりーんをくたせさい。', r).get('odd_spans'), [])
        with _Env(CN_IME_CLASS_MIXED_LOAN='0'):
            self.assertEqual(M._mark('スくりーんをくたせさい。', r).get('odd_spans'), [(0, 1)])


class Batch580(unittest.TestCase):
    """2026-11-15 全体評価の方針: IME の欄の紫を狭める時の珍しさ・浮いたかな。例は作った語。"""

    def test_familiar_parts(self):
        import odd_reason_fill as F
        import ime_reconvert as R
        self.assertFalse(F._familiar_parts('置詞', R))
        with _Env(CN_ODD_REASON_IME_FIELD_PARTS='0'):
            self.assertFalse(F._familiar_parts('総尺', R))

    def test_inflected_one(self):
        import odd_reason_fill as F
        from morphology import tokenize
        t = [x for x in tokenize('線を下にしてください') if x.surface == 'し'][0]
        self.assertTrue(F._inflected_one(t))
        with _Env(CN_ODD_REASON_IME_FIELD_INFLECT='0'):
            self.assertFalse(F._inflected_one(t))


class Batch579(unittest.TestCase):
    """2026-11-15 全体評価の方針: 身近な語をつないだ複合語だけの行。例は作った語。"""

    def test_compound_line(self):
        import odd_reason_fill as F
        self.assertEqual(F._compound_line('学校'), (0, 2))
        self.assertIsNone(F._compound_line('学校へ行く'))
        r = {'corrected': '学校', 'odd_spans': [(0, 2)], 'odd_reasons': [(0, 2, 'x')]}
        self.assertEqual(F.drop_compound_line('学校', r)['odd_spans'], [])
        with _Env(CN_ODD_REASON_COMPOUND_LINE='0'):
            self.assertEqual(F.drop_compound_line('学校', r)['odd_spans'], [(0, 2)])


class Batch578(unittest.TestCase):
    """2026-11-15 うにの画面の戻り。例は作った文。"""

    def test_var_count_original_is_line(self):
        import var_count as V
        line = 'n個めの行を見る'
        at = V.spots(line)
        masked = V.mask(line, at)
        got = V._unmask(line, masked, {'original': masked, 'corrected': masked}, at)
        self.assertEqual(got['original'], line)

    def test_keep_known_katakana(self):
        import last_keystroke as L
        import corrector
        from unittest import mock
        known = mock.patch.object(corrector, '_katakana_known_or_compound', lambda k, d=None: k == 'オン')
        known.start()
        self.addCleanup(known.stop)
        line = '設定はオンで、'
        found = ('設定はんで、', {'corrected': '設定はんで、'}, (3, 5, 'ん'))
        self.assertTrue(L._breaks_known_katakana(line, found, None, {}))
        self.assertFalse(L._breaks_known_katakana(line, found, None, {'odd_spans': [(3, 5)]}))
        with _Env(CN_KEEP_KNOWN_KATAKANA='0'):
            self.assertFalse(L._breaks_known_katakana(line, found, None, {}))

    def test_fixed_still_odd_kanji_respell_back(self):
        import fixed_still_odd as F
        self.assertTrue(F._kanji_respell_only([['値', '当て', '紫の所の打ち違い']]))
        self.assertFalse(F._kanji_respell_only([['あ', 'い', '紫の所の打ち違い']]))
        with _Env(CN_FSO_RESPELL_BACK='0'):
            self.assertFalse(F._kanji_respell_only([['値', '当て', '紫の所の打ち違い']]))


class Batch576(unittest.TestCase):
    def test_filler_inside_word(self):
        import odd_reason_fill as O
        line = 'まどをあけた'
        r = {'corrected': line, 'odd_spans': [(0, 2)], 'odd_reasons': [(0, 2, O.FILLER_ONE)]}
        self.assertFalse(O.drop_filler_in_word(line, r)['odd_spans'])
        r = {'corrected': line, 'odd_spans': [(0, 2)], 'odd_reasons': [(0, 2, O.GENERIC)]}
        self.assertTrue(O.drop_filler_in_word(line, r)['odd_spans'])
        with _Env(CN_ODD_REASON_FILLER_WORD='0'):
            r = {'corrected': line, 'odd_spans': [(0, 2)], 'odd_reasons': [(0, 2, O.FILLER_ONE)]}
            self.assertTrue(O.drop_filler_in_word(line, r)['odd_spans'])


class Batch570(unittest.TestCase):
    def test_ime_field_glued_kata(self):
        import odd_reason_fill as O
        line = '昨日の会議で青カン上'
        r = {'corrected': line, 'odd_spans': [(0, 10)], 'odd_reasons': [(0, 10, O.IME_FIELD)]}
        self.assertEqual(O.narrow_ime_field(line, r)['odd_spans'], [(6, 10)])
        line = '赤ワインを飲んだ'
        r = {'corrected': line, 'odd_spans': [(0, 8)], 'odd_reasons': [(0, 8, O.IME_FIELD)]}
        self.assertFalse(O.narrow_ime_field(line, r)['odd_spans'])


class Batch568(unittest.TestCase):
    def test_ime_first_keep(self):
        import ime_first_keep as K
        import odd_reason_fill as F
        fake = {'だけん': '打鍵', 'しりょう': '資料'}
        with _Env(CN_IME_FIRST_KEEP='1'):
            line = '打鍵の順番'
            r = {'corrected': line, 'odd_spans': [(0, 2)], 'odd_reasons': []}
            self.assertFalse(K.keep(line, r, ask=fake.get)['odd_spans'])
            r = {'corrected': line, 'odd_spans': [(0, 2)], 'odd_reasons': [(0, 2, F.GENERIC)]}
            self.assertTrue(K.keep(line, r, ask=fake.get)['odd_spans'])
            line = '会議の死霊を配る'
            r = {'corrected': line, 'odd_spans': [(3, 5)], 'odd_reasons': []}
            self.assertTrue(K.keep(line, r, ask=fake.get)['odd_spans'])
        line = '打鍵の順番'
        r = {'corrected': line, 'odd_spans': [(0, 2)], 'odd_reasons': [(0, 2, F.GENERIC)]}
        self.assertTrue(K.keep(line, r, ask=fake.get)['odd_spans'])

    def test_verb_wo_sahen_suru(self):
        import pos_seq_odd as P
        toks = list(tokenize('取り込むを参照してください'))
        self.assertTrue(P._names_command(toks, 1))
        self.assertFalse(P._names_command(list(tokenize('行くを出した')), 1))


class Batch585(unittest.TestCase):
    def test_verb_tail_noun_suru(self):
        import odd_reason_fill as F
        line = '下見しました'
        r = {'corrected': line, 'odd_spans': [(0, 3)], 'odd_reasons': [(0, 3, '「下見」と「し」は続けて置けない')]}
        self.assertFalse(F.fill(line, r)['odd_spans'])
        self.assertFalse(F._verb_tail_noun('資料'))

    def test_action_status_compound(self):
        import odd_reason_fill as F
        line = '設定は変更可能'
        r = {'corrected': line, 'odd_spans': [(5, 7)], 'odd_reasons': [(5, 7, F.GENERIC)]}
        self.assertFalse(F.fill(line, r)['odd_spans'])
        line = '会議の死霊を配る'
        r = {'corrected': line, 'odd_spans': [(3, 5)], 'odd_reasons': [(3, 5, F.GENERIC)]}
        self.assertTrue(F.fill(line, r)['odd_spans'])

    def test_head_particle_pair_purple(self):
        import head_particle_keep as H
        line = 'を確認した'
        r = {'corrected': line, 'odd_spans': [(0, 3)], 'odd_reasons': [(0, 3, '「を」と「確認」は続けて置けない')]}
        self.assertFalse(H.keep_head(line, r)['odd_spans'])
        with _Env(CN_HEAD_PARTICLE_PAIR='0'):
            self.assertTrue(H.keep_head(line, r)['odd_spans'])

    def test_te_known_katakana_end(self):
        import broken_shape as B
        self.assertFalse(B.spans('入力してテキスト'))
        self.assertFalse(B.spans('返信をお願いいただけますか'))


class Batch587(unittest.TestCase):
    def test_noun_pair(self):
        import odd_reason_fill as F
        line = '入力欄を見る'
        r = {'corrected': line, 'odd_spans': [(0, 3)], 'odd_reasons': [(0, 3, '「入力」と「欄」は続けて置けない')]}
        # 2026-11-20: 名詞＋端の漢字1字の複合語は B1（CN_ODD_REASON_AFFIX_COMPOUND）でも外れる
        self.assertFalse(F.fill(line, r)['odd_spans'])
        with _Env(CN_ODD_REASON_AFFIX_COMPOUND='0'):
            self.assertTrue(F.fill(line, r)['odd_spans'])
        with _Env(CN_ODD_REASON_NOUN_PAIR='1', CN_ODD_REASON_AFFIX_COMPOUND='0'):
            self.assertFalse(F.fill(line, r)['odd_spans'])

    def test_noun_renyo(self):
        import odd_reason_fill as F
        line = '数字を右詰めにする'
        r = {'corrected': line, 'odd_spans': [(3, 6)], 'odd_reasons': [(3, 6, '「右詰め」' + F.KEYSLIP_TAIL)]}
        self.assertFalse(F.fill(line, r)['odd_spans'])

    def test_te_aux_back(self):
        import guess_back as G
        line = '雨が降ってきた'
        r = {'corrected': '雨が降来た', 'odd_spans': [], 'details': [['ってき', '来', '紫の所の打ち違い']]}
        self.assertEqual(G.te_aux_back(line, r)['corrected'], line)
        with _Env(CN_GUESS_BACK_TE_AUX='0'):
            self.assertEqual(G.te_aux_back(line, r)['corrected'], '雨が降来た')


class Batch588(unittest.TestCase):
    def test_head_small_toggle(self):
        import head_particle_keep as H
        self.assertTrue(H._small_toggle('に有力を使う', '入力を使う', 2, 0, 1))
        self.assertFalse(H._small_toggle('も他をうたう', 'モチをうたう', 2, 0, 2))


class Batch591(unittest.TestCase):
    def test_numeral_same_reading(self):
        import correction_entry as ce
        self.assertTrue(ce._numeral_same_reading('二階', 'に貝'))
        self.assertFalse(ce._numeral_same_reading('二本', 'に本'))
        self.assertFalse(ce._numeral_same_reading('五人', '誤認'))
        self.assertFalse(ce._numeral_same_reading('三十五度', '三十度'))

    def test_unknown_word_guard_switch(self):
        import os
        self.assertNotEqual(os.environ.get('CN_UNKNOWN_WORD_SUFFIX'), '0')

class Batch592(unittest.TestCase):
    def test_frame_unique(self):
        import odd_respell as O
        self.assertTrue(O._frame_unique('元に戻る', 0, 1))

    def test_head_intrusion_drop_negative(self):
        import head_particle_keep as H
        self.assertFalse(H._intrusion_drop('も他をうたう', 'モチをうたう', 2, 0, 2))

    def test_ime_class_attached(self):
        import ime_class_mark as M
        self.assertTrue(M._attached_here('温度計の精度', 2, 3))
        self.assertTrue(M._attached_here('行かねばならぬ', 2, 3))
        self.assertFalse(M._attached_here('積み森を', 2, 3))


class Batch596(unittest.TestCase):
    def test_dict_word_not_rare(self):
        import ime_reconvert as R
        from morphology import tokenize
        t = [x for x in tokenize('週明けに会う') if x.surface == '週明け'][0]
        self.assertEqual(R._rank('週明け'), 800)
        self.assertLess(R._token_rarity(t), R.DOUBT)
        self.assertFalse(R._seed_top('風位', 'ふうい'))
        self.assertTrue(R._seed_top('週明け', 'しゅうあけ'))

    def test_kana_piece_end(self):
        import dict_word_keep as K
        from morphology import tokenize
        toks = list(tokenize('あすへほ'))
        last = toks[-1]
        self.assertTrue(K._kana_piece_end('あすへほ', last))
        self.assertFalse(K._kana_piece_end('あすへほか', last))


class Batch597(unittest.TestCase):
    def test_sahen_tail(self):
        import odd_reason_fill as F
        from morphology import tokenize
        toks = list(tokenize('会議で反証を示す'))
        self.assertTrue(F._sahen_tail_ok(toks, [t for t in toks if t.surface == '反証'][0]))
        toks = list(tokenize('案を検討せれる'))
        self.assertFalse(F._sahen_tail_ok(toks, [t for t in toks if t.surface == '検討'][0]))


class Batch599(unittest.TestCase):
    def test_reading_drop_one_key(self):
        import broken_shape as B
        import kana_layout
        # じ は し＋゛ の2打なので、抜く1打の形にはならない。か は ん の隣のキー
        self.assertFalse(kana_layout.single_key_drop_adjacency('へんかじを', 'へんかを'))
        self.assertTrue(kana_layout.single_key_drop_adjacency('へんかじを', 'へんじを'))
        import morphology
        d = '友達に変化字を書く'
        self.assertEqual(B._reading_drop(d, list(morphology.tokenize(d)), 3, 6), '返事')


class Batch600(unittest.TestCase):
    def test_kata_whole(self):
        import kana_lattice_place as K
        self.assertEqual(K._kata_whole('ぱそこんを'), (4, 'パソコン'))
        self.assertIsNone(K._kata_whole('ねこが'))


class Batch601(unittest.TestCase):
    def test_sahen_rare_neighbor(self):
        import odd_reason_fill as F
        from morphology import tokenize
        t = list(tokenize('会議で反証を示す'))
        x = [u for u in t if u.surface == '反証'][0]
        self.assertTrue(F._sahen_word(t, x.start, x.end))


class Batch602(unittest.TestCase):
    def test_head_drop_spot(self):
        import broken_shape as B
        import morphology
        d = '宿題に手取り掛かった'
        t = list(morphology.tokenize(d))
        self.assertTrue(B._head_drop_spots(t))
        self.assertEqual(B._head_drop_spots(list(morphology.tokenize('宿題に取り掛かった'))), [])

    def test_kata_verb(self):
        import kana_lattice_place as K
        self.assertEqual(K._kata_verb('さぼったら'), (2, 'サボ'))
        self.assertIsNone(K._kata_verb('はしったら'))

    def test_loan_run(self):
        import kana_keep as K
        self.assertEqual(K._loan_runs('ぐぐったら', 'ググったら'), [(0, 2)])


class Batch603(unittest.TestCase):
    def test_lone_voicing_mark_keeps_purple_when_ime_field_narrows(self):
        # 行全体の IME の欄の紫を狭める時、濁点だけの語（゜）は残す（作った例）
        import odd_reason_fill as F
        from unittest import mock
        line = 'カ゜）本を'
        r = {'corrected': line, 'odd_spans': [(0, len(line))], 'odd_reasons': [(0, len(line), F.IME_FIELD)]}
        with mock.patch.object(F, '_rare_token', lambda t, toks: False), mock.patch.object(F, '_wide_weak', lambda *a: True):
            got = F.narrow_ime_field(line, r)
        self.assertIn((1, 2), [tuple(x[:2]) for x in got['odd_spans']])
        with mock.patch.dict('os.environ', {'CN_ODD_REASON_IME_FIELD_MARK': '0'}), \
                mock.patch.object(F, '_rare_token', lambda t, toks: False), mock.patch.object(F, '_wide_weak', lambda *a: True):
            got = F.narrow_ime_field(line, r)
        self.assertNotIn((1, 2), [tuple(x[:2]) for x in got['odd_spans']])


class Batch604(unittest.TestCase):
    def test_wide_reasonless_purple_keeps_clear_slips(self):
        # 行全体の理由の無い紫を外す時、濁点だけの語と読みの無い1字は残す（作った例）
        import odd_reason_fill as F
        from unittest import mock
        line = 'ヅ゜）本の番号を'
        r = {'corrected': line, 'odd_spans': [(0, len(line))], 'odd_reasons': []}
        with mock.patch.object(F, '_wide_weak', lambda *a: True):
            got = [tuple(x[:2]) for x in F.fill(line, r)['odd_spans']]
        self.assertIn((1, 2), got)
        self.assertNotIn((0, len(line)), got)
        with mock.patch.dict('os.environ', {'CN_ODD_REASON_WIDE_SLIP': '0'}), mock.patch.object(F, '_wide_weak', lambda *a: True):
            self.assertEqual(F.fill(line, r)['odd_spans'], [])

    def test_wide_reasonless_purple_on_plain_line_still_goes(self):
        import odd_reason_fill as F
        from unittest import mock
        line = '明日の会議の資料を作る'
        r = {'corrected': line, 'odd_spans': [(0, len(line))], 'odd_reasons': []}
        with mock.patch.object(F, '_wide_weak', lambda *a: True):
            self.assertEqual(F.fill(line, r)['odd_spans'], [])


class Batch605(unittest.TestCase):
    def test_mark_replaced_reads_symbol_as_its_key(self):
        # 付く先の無い ゜ と、ょ のキーの ） の交じる所（作った例）。印を抜いただけの直しは印を替えた答えではない
        import odd_respell as O
        self.assertFalse(O._mark_replaced('ギ゜）鵜番号を', '行番号を'))
        self.assertTrue(O._mark_replaced('あ゛', 'あせ'))
        with mock.patch.dict('os.environ', {'CN_MARK_REPLACED_SURFACE': '0'}):
            self.assertTrue(O._mark_replaced('ギ゜）鵜番号を', '行番号を'))

    def test_far_kana_respell_reads_symbol_and_table_word(self):
        import correction_entry as ce
        l = 'ギ゜）鵜番号を見る。'
        out = {'corrected': '行番号を見る。'}
        self.assertFalse(ce._far_kana_respell(l, {'corrected': l}, out, 'kana'))
        with mock.patch.dict('os.environ', {'CN_RESPELL_KANA_FAR_SURFACE': '0'}):
            self.assertTrue(ce._far_kana_respell(l, {'corrected': l}, out, 'kana'))
        # 記号の無い行は今のまま（読むう→消す は3打）
        self.assertTrue(ce._far_kana_respell('本を読むう', {'corrected': '本を読むう'}, {'corrected': '本を消す'}, 'kana'))

    def test_table_compound_kept_over_two_slip_form(self):
        import odd_respell as O
        self.assertEqual(O._kanji_run_at('行番号を', 0, 1), '行番号')
        self.assertTrue(O._table_word('行番号'))
        self.assertFalse(O._table_word('牛番号'))


class Batch606(unittest.TestCase):
    def test_open_line_is_not_measured_as_a_whole_sentence(self):
        # 行は文の途中で切れることがある（作った例: 格助詞で終わる行・助詞で始まる行）
        import fixed_still_odd as F
        from morphology import tokenize
        self.assertTrue(F._open_line(list(tokenize('会議の資料を'))))
        self.assertTrue(F._open_line(list(tokenize('を見てください。'))))
        self.assertFalse(F._open_line(list(tokenize('しかし雨が降った。'))))
        self.assertFalse(F._open_line(list(tokenize('雨が降ったよ'))))
        with mock.patch.dict('os.environ', {'CN_FIXED_STILL_ODD_OPEN': '0'}):
            self.assertFalse(F._open_line(list(tokenize('会議の資料を'))))


class Batch607(unittest.TestCase):
    def test_compound_line_keeps_shape_reason(self):
        # 身近な名詞をつないだだけの行でも、形の見立て（片仮名の語のあいだの 化）の紫は残す（作った例）
        import odd_reason_fill as F
        line = 'コピー化ペースト'
        why = '片仮名の語のあいだの「化」は、並べる「か」かもしれません'
        r = {'corrected': line, 'odd_spans': [(3, 4)], 'odd_reasons': [(3, 4, why)]}
        with mock.patch.object(F, '_compound_line', lambda l: (0, len(l))):
            self.assertEqual([tuple(x[:2]) for x in F.drop_compound_line(line, r)['odd_spans']], [(3, 4)])
            r2 = {'corrected': line, 'odd_spans': [(3, 4)], 'odd_reasons': [(3, 4, F.GENERIC)]}
            self.assertEqual(F.drop_compound_line(line, r2)['odd_spans'], [])
            with mock.patch.dict('os.environ', {'CN_ODD_REASON_COMPOUND_STRONG': '0'}):
                self.assertEqual(F.drop_compound_line(line, r)['odd_spans'], [])


class Batch608(unittest.TestCase):
    def test_noun_ending_line_is_open(self):
        import fixed_still_odd as F
        from morphology import tokenize
        self.assertTrue(F._open_line(list(tokenize('会議の資料'))))
        self.assertFalse(F._open_line(list(tokenize('会議の資料。'))))
        with mock.patch.dict('os.environ', {'CN_FIXED_STILL_ODD_OPEN_NOUN': '0'}):
            self.assertFalse(F._open_line(list(tokenize('会議の資料'))))


class Batch609(unittest.TestCase):
    def test_kango_plus_particle_stays_kanji(self):
        # かなの打ち違いを直して 漢語＋助詞 になった所は、助詞の字で和語と見てかなに戻さない（作った例）
        import kana_keep as K
        self.assertEqual(K.wago_kana_respell('会議のでんわほ', '会議の電話を'), '会議の電話を')
        with mock.patch.dict('os.environ', {'CN_RESPELL_WAGO_KANA_TOKENS': '0'}):
            self.assertEqual(K.wago_kana_respell('会議のでんわほ', '会議の電話を'), '会議のでんわを')
        # 和語は今のまま
        self.assertEqual(K.wago_kana_respell('くたせさい', '下さい'), 'ください')

    def test_stray_top_near_switch(self):
        import odd_respell as O
        import inspect
        self.assertIn('CN_STRAY_TOP_NEAR', inspect.getsource(O._stray_mark_repair))


class Batch610(unittest.TestCase):
    def test_mark_key_replaced_by_other_kana_goes_back_to_purple(self):
        # 付く先の無い ゛ のキーを別のかなにした直しは戻して紫（作った例）
        import correction_entry as ce
        line = '会議でて゛んわを'
        r = {'corrected': '会議でてけんわを', 'changed': True, 'details': [['て゛', 'てけ', 'かな入力']],
             'spans': [[3, 5]], 'original_spans': [[3, 5]], 'odd_spans': []}
        with mock.patch('odd_respell._mark_replaced', lambda a, b: True):
            got = ce._mark_replaced_back(line, r, 'kana')
        self.assertEqual(got['corrected'], line)
        self.assertTrue(got['odd_spans'])
        self.assertIs(ce._mark_replaced_back(line, r, 'romaji'), r)
        with mock.patch.dict('os.environ', {'CN_MARK_REPLACED_BACK': '0'}):
            self.assertIs(ce._mark_replaced_back(line, r, 'kana'), r)


class Batch611(unittest.TestCase):
    def test_both_hands_shift_restored(self):
        # 両手が揃って左へ1つずれた打ち方を戻す（作った例: ほうこく を わあひき と打った）
        import hand_shift_wide as H
        self.assertNotIn('ほうこく', H.shifted_readings('わあひき'))   # ふだんの候補には混ぜない
        H.BOTH[0] = True
        self.addCleanup(H.BOTH.__setitem__, 0, False)
        self.assertIn('ほうこく', H.shifted_readings('わあひき'))
        with mock.patch.dict('os.environ', {'CN_HAND_SHIFT_BOTH': '0'}):
            self.assertNotIn('ほうこく', H.shifted_readings('わあひき'))

    def test_tie_purple_switch_exists(self):
        import odd_respell
        src = __import__('pathlib').Path(odd_respell.__file__).read_text(encoding='utf-8')
        self.assertIn("CN_SHIFT_TIE_PURPLE", src)
        self.assertIn("tie_spans", src)


class Batch612(unittest.TestCase):
    def test_noun_end_open_only_when_end_kept(self):
        # 直しが行の終わりを名詞に替えた行は、開いた行と見ない（作った例）
        import fixed_still_odd as F
        from morphology import tokenize
        toks = list(tokenize('机の上に本棚'))
        F._ORIG[0] = '机の上に本棚'
        try:
            self.assertTrue(F._open_line(toks))
            F._ORIG[0] = '机の上に置く'
            self.assertFalse(F._open_line(toks))
            with mock.patch.dict('os.environ', {'CN_FIXED_STILL_ODD_OPEN_NOUN_KEPT': '0'}):
                self.assertTrue(F._open_line(toks))
        finally:
            F._ORIG[0] = None


class Batch613(unittest.TestCase):
    def test_head_drop_skips_sahen_honorific(self):
        # 動作の名詞＋敬語の動詞（作った例: 項目を追加いただけ）に、頭の1字が混じった紫を付けない
        import broken_shape as B
        import morphology
        toks = list(morphology.tokenize('項目を追加いただけますか'))
        self.assertEqual(B._head_drop_spots(toks), [])
        with mock.patch.dict('os.environ', {'CN_HEAD_DROP_SAHEN_HONOR': '0', 'CN_HEAD_DROP_COMMON': '0'}):
            self.assertTrue(B._head_drop_spots(toks))


class Batch614(unittest.TestCase):
    def test_head_drop_skips_sahen_noun_before_verb(self):
        # 動作の名詞の後ろに を を省いて動詞（作った例: 【変更見ます】）
        import broken_shape as B
        import morphology
        toks = list(morphology.tokenize('【変更見ます】'))
        self.assertEqual(B._head_drop_spots(toks), [])

    def test_kana_nominal_renyou_with_de(self):
        # かなの連用形が名詞の表記を持つなら、で は格助詞として続く（作った例: うちあわせで）
        import correction_entry as ce
        self.assertTrue(ce._kana_nominal('うちあわせ'))
        self.assertFalse(ce._kana_nominal('癒え'))
        with mock.patch.dict('os.environ', {'CN_FIX_RENYOU_NOMINAL': '0'}):
            self.assertFalse(ce._kana_nominal('うちあわせ'))

    def test_variant_cap_raised(self):
        import correction_entry as ce
        self.assertGreaterEqual(ce.REOPEN_VARIANT_CAP, 4000)

    def test_tie_check_does_not_spend_budget(self):
        import odd_respell
        src = __import__('pathlib').Path(odd_respell.__file__).read_text(encoding='utf-8')
        self.assertIn("_rb._COUNT['passes'] = _p0", src)


class Batch615(unittest.TestCase):
    def test_joined_word_with_kana_spelling(self):
        # 2つの名詞の読みをつないだ語が、片方をかなで書いた表記で表に在る（作った例: 鍵括弧 ← カギ括弧）
        import odd_reason_fill as F
        import morphology
        t = list(morphology.tokenize('鍵括弧を使う'))
        self.assertTrue(F._joined_word(t, 0, 3))
        t2 = list(morphology.tokenize('期間車を見る'))
        self.assertFalse(F._joined_word(t2, 0, 3))

    def test_ime_class_attached_and_own_word(self):
        # 作った例: 使う方・各人 は IME が読めなくても紫にしない
        import ime_class_mark as I
        self.assertTrue(I._attached_here('使う方を選ぶ', 2, 3))
        self.assertTrue(I._own_word('各人の意見', 0, 2))
        self.assertFalse(I._own_word('積み森の', 0, 3))
        with mock.patch.dict('os.environ', {'CN_IME_CLASS_ATTR_VERB': '0', 'CN_IME_CLASS_OWN_WORD': '0'}):
            self.assertFalse(I._attached_here('使う方を選ぶ', 2, 3))
            self.assertFalse(I._own_word('各人の意見', 0, 2))


class Batch617(unittest.TestCase):
    def test_same_reading_gain_switch(self):
        import ime_reconvert as R
        src = __import__('pathlib').Path(R.__file__).read_text(encoding='utf-8')
        self.assertIn('CN_RECONVERT_SAME_READING_GAIN', src)
        self.assertLessEqual(R.KEY_GAIN, 3000)

    def test_selection_fix_keeps_reading(self):
        # 作った例: 読みの替わる直し（たかはし → かはし）は選び違いとして直さない
        import ime_reconvert as R
        self.assertFalse(R._same_reading_swap('高橋号を見る', '可橋号を見る'))
        self.assertTrue(R._same_reading_swap('会議の死霊を配る', '会議の資料を配る'))
        src = __import__('pathlib').Path(R.__file__).read_text(encoding='utf-8')
        self.assertIn('CN_RECONVERT_KEY_PROPER_MARK', src)


class Batch616(unittest.TestCase):
    def test_renyou_one_kanji_tail_at_line_end(self):
        # 連用形＋漢字1字の名詞で終わる行（作った例: 書き方）は切れ端と見ない
        import oddness
        a = ('書き', '動詞:自立', '', 0, 2, '', '連用形')
        b = ('方', '名詞:一般', '', 2, 3, '', '')
        self.assertFalse(oddness.renyou_stray_noun_mismatch(a, b, True))
        with mock.patch.dict('os.environ', {'CN_RENYOU_ONE_KANJI_TAIL': '0'}):
            with mock.patch('seed_japanese.is_unit', lambda w: False):
                self.assertTrue(oddness.renyou_stray_noun_mismatch(a, b, True))


class Batch628(unittest.TestCase):
    def test_no_after_close_bracket_is_not_stacked(self):
        # 作った例: 閉じ括弧の後ろの の（「え」の文字）は崩れた跡とみない
        import keyslip_window as K
        from morphology import tokenize
        toks = list(tokenize('「え」の文字に変えてから、'))
        self.assertEqual(K._stacked_no(toks), [])
        with mock.patch.dict('os.environ', {'CN_KEYSLIP_CLOSE_BRACKET_NO': '0'}):
            self.assertTrue(K._stacked_no(toks))

    def test_reduplicated_kana_not_respelled(self):
        # 作った例: くり返しの擬音（ころころ）は読み直さない
        import odd_respell as O
        self.assertTrue(O._reduplicated('犬がころころ転ぶ', 3, 4))
        self.assertFalse(O._reduplicated('犬がころがる', 3, 4))
        with mock.patch.dict('os.environ', {'CN_RESPELL_KEEP_REDUP': '0'}):
            self.assertFalse(O._reduplicated('犬がころころ転ぶ', 3, 4))

    def test_homophone_keeps_rare_chosen_word(self):
        # とても珍しい語は書き手が選んだ表記とみて同じ読みの語に替えない
        import purple_homophone as P
        import ime_reconvert as R

        class T:
            surface = '某語'
        with mock.patch.object(R, '_rank', lambda w: R.DOUBT_KEY + 1):
            self.assertTrue(P._chosen_rare(T()))
            with mock.patch.dict('os.environ', {'CN_PURPLE_HOMOPHONE_RARE_KEEP': '0'}):
                self.assertFalse(P._chosen_rare(T()))

    def test_ime_field_clause_and_nominalizer(self):
        # 作った例: 読点の後ろの節の全体に掛かる IME の欄の紫は、節の中身全部として狭める。準体の の は疑わない
        import odd_reason_fill as F
        from morphology import tokenize
        line = '雨でしたが、本を読んでいるのは、'
        toks = list(tokenize(line))
        self.assertTrue(F._wide_weak(line, toks, 6, 15))
        with mock.patch.dict('os.environ', {'CN_ODD_REASON_IME_FIELD_CLAUSE': '0'}):
            self.assertFalse(F._wide_weak(line, toks, 6, 15))
        no = [t for t in toks if t.surface == 'の' and str(t.pos_sub or '').startswith('非自立')]
        self.assertTrue(no and F._nominalizer(no[0]))

    def test_lone_tsu_inside_kana_word(self):
        # 作った例: かなの語の中の っ（ぽっぷ）は音便の動詞と見ない
        import dangling_verb as D
        self.assertTrue(D._lone_tsu('ぽっぷ', 1, 2))
        self.assertFalse(D._lone_tsu('待っ', 1, 2))
        with mock.patch.dict('os.environ', {'CN_DANGLING_LONE_TSU': '0'}):
            self.assertFalse(D._lone_tsu('ぽっぷ', 1, 2))

    def test_ime_class_redup_kana(self):
        # 作った例: くり返しの擬音（ころコロ）の切れ端は紫にしない
        import ime_class_mark as M
        self.assertTrue(M._redup('ころコロ！', 0, 1))
        self.assertFalse(M._redup('ころがる', 0, 1))
        with mock.patch.dict('os.environ', {'CN_IME_CLASS_REDUP': '0'}):
            self.assertFalse(M._redup('ころコロ！', 0, 1))

    def test_reconvert_okuri_omitted(self):
        # 作った例: 送り仮名を省いた表記（受付）は、同じ読みの辞書の語（受け付け）の省いた形として疑わない
        import ime_reconvert as R
        import reading_lattice as lat
        lat.load()
        words = ((0, 1, 0, 2, 100, 3), (1, 2, 2, 4, 100, 3), (2, 3, 4, 5, 0, 2))
        self.assertTrue(R._okuri_omitted('受付で', 'うけつけで', words, 0, 2))
        with mock.patch.dict('os.environ', {'CN_RECONVERT_OKURI_OMIT': '0'}):
            self.assertFalse(R._okuri_omitted('受付で', 'うけつけで', words, 0, 2))

    def test_ime_field_name_of_common_chars(self):
        # 作った例: 解析が姓と読んだ身近な字の並び（大中）は珍しい語と数えない
        import odd_reason_fill as F
        import ime_reconvert as R

        class T:
            surface = '大中'
            pos_sub = '固有名詞:人名:姓'
        self.assertTrue(F._name_of_common_chars(T(), R))
        with mock.patch.dict('os.environ', {'CN_ODD_REASON_IME_FIELD_NAME_CHARS': '0'}):
            self.assertFalse(F._name_of_common_chars(T(), R))
        src = __import__('pathlib').Path(F.__file__).read_text(encoding='utf-8')
        self.assertIn('CN_ODD_REASON_IME_FIELD_PART', src)


class Batch629(unittest.TestCase):
    def test_body_ignores_marks(self):
        # 作った例: 矢印・箇条書きの印は行の中身の字に数えない
        import odd_reason_fill as F
        self.assertTrue(F._mark_char('→'))
        self.assertFalse(F._mark_char('あ'))
        with mock.patch.dict('os.environ', {'CN_ODD_REASON_BODY_SYMBOLS': '0'}):
            self.assertFalse(F._mark_char('→'))

    def test_wago_verb_intransitive_without_object(self):
        # を の組がほとんど無い動詞（が の組だけ）は、目的語の無い使い方の表記として選ぶ
        import wago_verb as W
        with mock.patch.object(W, '_PARTS', [{'作る自': [10, 0], '作る他': [10, 9]}]):
            self.assertTrue(W._intransitive('作る自'))
            self.assertFalse(W._intransitive('作る他'))
        src = __import__('pathlib').Path(W.__file__).read_text(encoding='utf-8')
        self.assertIn('CN_WAGO_VERB_INTRANSITIVE', src)

    def test_respell_keeps_kata_common_pair(self):
        # 作った例: 身近な片仮名の語＋漢字の語（ペン先）の所を別の語に替える読み直しは採らない
        import odd_respell as O
        self.assertTrue(O._kata_common_pair('左のペン先', '左の変'))
        with mock.patch.dict('os.environ', {'CN_RESPELL_KATA_PAIR': '0'}):
            self.assertFalse(O._kata_common_pair('左のペン先', '左の変'))


if __name__ == '__main__':
    unittest.main()
