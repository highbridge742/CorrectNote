"""2026-11-20: 正しい文に付いていた紫・間違った書き換えを止める決まり（作った例）。判断 POLICY.md の A〜K。"""
import os
import unittest
from unittest import mock

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


class NumCounter(unittest.TestCase):
    def test_number_and_counter_not_lone(self):
        import keyslip_window as W
        t = list(tokenize('一例を挙げる'))
        self.assertTrue(W._num_counter(t[0], t, 0))
        self.assertTrue(W._num_counter(t[1], t, 1))
        self.assertFalse(W._num_counter(t[2], t, 2))


class AffixForm(unittest.TestCase):
    def _run(self, s, a, b):
        import affix_form
        return affix_form.affix_run(list(tokenize(s)), a, b)

    def test_compound_with_number(self):
        self.assertTrue(self._run('設定画面5つ', 0, 4))

    def test_noun_and_known_katakana(self):
        self.assertTrue(self._run('入力ミス', 0, 4))

    def test_two_single_kanji_stay(self):
        self.assertFalse(self._run('赤トン下', 0, 3))

    def test_switch_off(self):
        with _Env(CN_AFFIX_FORM='0'):
            self.assertFalse(self._run('設定画面5つ', 0, 4))


class OddReasonFill(unittest.TestCase):
    def _fill(self, line, odd, reasons=()):
        import odd_reason_fill as F
        return F.fill(line, {'corrected': line, 'odd_spans': list(odd), 'odd_reasons': list(reasons)}).get('odd_spans')

    def test_affix_compound_dropped(self):
        self.assertEqual(self._fill('入力ミスを減らす', [(0, 4)]), [])
        with _Env(CN_ODD_REASON_AFFIX_COMPOUND='0'):
            self.assertEqual(self._fill('入力ミスを減らす', [(0, 4)]), [(0, 4)])

    def test_rengo_case(self):
        line = '天気についてを書く'
        rs = [(2, 7, '「について」と「を」は続けて置けない')]
        self.assertEqual(self._fill(line, [(2, 7)], rs), [])
        with _Env(CN_ODD_REASON_RENGO_CASE='0'):
            self.assertEqual(self._fill(line, [(2, 7)], rs), [(2, 7)])

    def test_reading_beside(self):
        line = 'あさかつ—朝活の話'
        self.assertEqual(self._fill(line, [(5, 7)]), [])

    def test_spoken_words(self):
        import odd_reason_fill as F
        self.assertEqual(F._spoken_kana_words('すげぇ話'), [(0, 3)])
        self.assertEqual(F._spoken_kana_words('もふもふだ'), [(0, 4)])
        self.assertEqual(F._spoken_kana_words('かきかけ'), [])
        self.assertEqual(F._spoken_kana_words('ははは'), [])

    def test_ime_field_with_affix_compound(self):
        import odd_reason_fill as F
        line = '行間幅を、'
        r = {'corrected': line, 'odd_spans': [(0, 4)],
             'odd_reasons': [(0, 3, '「行間」と「幅」は続けて置けない'), (0, 4, F.IME_FIELD)]}
        self.assertEqual(F.narrow_ime_field(line, r)['odd_spans'], [])

    def test_specific_reason_kept(self):
        line = '入力ミスを減らす'
        rs = [(0, 4, '「ミス」は「ミル」の打ち違いかもしれません')]
        self.assertEqual(self._fill(line, [(0, 4)], rs), [(0, 4)])


class ImeNounPair(unittest.TestCase):
    line = '今日の残件を見る'

    def _fill(self, words):
        import ime_class_mark as M
        import odd_reason_fill as F
        M.set_words_provider(lambda t: words)
        try:
            r = {'corrected': self.line, 'odd_spans': [(3, 5)], 'odd_reasons': [(3, 5, '「残」と「件」は続けて置けない')]}
            return F.fill(self.line, r)['odd_spans']
        finally:
            M.set_words_provider(None)

    def test_ime_reads_one_noun(self):
        self.assertEqual(self._fill([(0, 2, 0, 3, 100, 3), (2, 3, 3, 4, 0, 2), (3, 5, 4, 8, 100, 3)]), [])

    def test_ime_splits_stays(self):
        self.assertEqual(self._fill([(0, 2, 0, 3, 100, 3), (2, 3, 3, 4, 0, 2), (3, 4, 4, 6, 100, 3),
                                     (4, 5, 6, 8, 100, 3)]), [(3, 5)])


class BrokenShape(unittest.TestCase):
    def _why(self, s):
        import broken_shape as BS
        return [x[2] for x in BS.spans(s)]

    def test_known_katakana_noun_at_end(self):
        self.assertNotIn('片仮名が混じっています', self._why('効果ゼロでした'))
        with _Env(CN_KATA_KNOWN_NOUN='0'):
            self.assertIn('片仮名が混じっています', self._why('効果ゼロでした'))

    def test_paired_symbols(self):
        self.assertEqual(self._why('もし**強くしたい**なら'), [])
        with _Env(CN_STRAY_SYMBOL_PAIRED='0'):
            self.assertIn('文の途中に記号が混じっています', self._why('もし**強くしたい**なら'))

    def test_sahen_shi_renyo(self):
        self.assertNotIn('動詞のつながりが変です', self._why('運動し走る'))
        with _Env(CN_BROKEN_SHI_RENYO='0'):
            self.assertIn('動詞のつながりが変です', self._why('運動し走る'))


class KanjiDoubt(unittest.TestCase):
    def test_dict_one_word(self):
        import kanji_doubt as KD
        self.assertTrue(KD._dict_one_word('二重罫線', 2, 4))
        self.assertFalse(KD._dict_one_word('佑から', 0, 1))


class SplitCompound(unittest.TestCase):
    def test_split_compound_purple(self):
        import correction_entry as CE
        line = '急いで自走し始める'
        r = CE._split_compound_purple(line, {'corrected': line, 'odd_spans': [(4, 5)], 'odd_reasons': [(4, 5, 'x')]})
        self.assertEqual(r['odd_spans'], [])
        with _Env(CN_SPLIT_COMPOUND_PURPLE='0'):
            r = CE._split_compound_purple(line, {'corrected': line, 'odd_spans': [(4, 5)]})
            self.assertEqual(r['odd_spans'], [(4, 5)])


class KeepRestore(unittest.TestCase):
    def test_restored_purple_on_one_kanji(self):
        import dict_word_keep as K
        line = '山田号して進む'
        r = K.keep(line, {'corrected': '山田号と進む', 'details': [['して', 'と', '紫の所の打ち違い']]})
        self.assertEqual(r['corrected'], line)
        self.assertEqual(r['odd_spans'], [(2, 5)])
        with _Env(CN_DICT_WORD_KEEP_RESTORE='0'):
            r = K.keep(line, {'corrected': '山田号と進む', 'details': [['して', 'と', '紫の所の打ち違い']]})
            self.assertFalse(r.get('odd_spans'))


class LiteralKanaPair(unittest.TestCase):
    def test_two_quoted_spellings(self):
        import literal_examples as LE
        self.assertEqual(LE.protected_ranges('「かきく」と「かぎく」の違い'), [(1, 4), (7, 10)])


class TeSuffix(unittest.TestCase):
    """て の後ろの接尾だけの名詞（pos_seq_odd の (q)）。紫は て の前の動詞から、読み直しは当てない。"""
    def test_marks_suffix_after_te(self):
        import pos_seq_odd as Q
        self.assertEqual([x[:2] for x in Q.spots('窓が閉めてて系が鳴ってる')], [(2, 7)])
        r = Q.mark_line('窓が閉めてて系が鳴ってる', {'corrected': '窓が閉めてて系が鳴ってる'})
        self.assertEqual(r['odd_spans'], [(2, 7)])
        self.assertEqual(r['face_doubt_spans'], [(2, 7)])

    def test_standalone_nouns_after_te_kept(self):
        import pos_seq_odd as Q
        for s in ('急いで用を足す', '言って側に置く', 'おいしくて後を引く', '窓が閉まってて時計が鳴ってる'):
            self.assertEqual(Q.spots(s), [], s)

    def test_switch(self):
        import pos_seq_odd as Q
        with _Env(CN_POS_SEQ_TE_SUFFIX='0'):
            self.assertEqual(Q.spots('窓が閉めてて系が鳴ってる'), [])


class ImeShortSuffix(unittest.TestCase):
    """名詞のすぐ後ろの漢字1字で、IME の読みが1字なのに接尾の読みが2字以上（ime_class_mark）。"""
    def test_short_reading_marked(self):
        import ime_class_mark as M
        w = [[0, 3, 0, 4, 100, 3], [3, 4, 4, 5, 100, 3], [4, 5, 5, 6, 0, 2]]
        self.assertEqual(M._short_suffix_spans('見出し名も', w), [(3, 4)])
        with _Env(CN_IME_CLASS_SHORT_SUFFIX='0'):
            self.assertEqual(M._short_suffix_spans('見出し名も', w), [])

    def test_suffix_reading_kept(self):
        import ime_class_mark as M
        # 都 は接尾で と と読む（1字）ので、IME の1字の読みは普通の付き方
        w = [[0, 2, 0, 4, 100, 3], [2, 3, 4, 5, 100, 3], [3, 4, 5, 6, 0, 2]]
        self.assertEqual(M._short_suffix_spans('東京都に', w), [])
        # IME の読みが2字（めい）なら普通の付き方
        w2 = [[0, 3, 0, 4, 100, 3], [3, 4, 4, 6, 100, 3], [4, 5, 6, 7, 0, 2]]
        self.assertEqual(M._short_suffix_spans('見出し名も', w2), [])


class ImeSinglePair(unittest.TestCase):
    """IME が漢字1字の名詞2つに分けた所で、2字が辞書の普通の語でない所（ime_class_mark）。"""
    def test_pair_marked(self):
        import ime_class_mark as M
        w = [[0, 2, 0, 4, 100, 3], [2, 3, 4, 5, 0, 2], [3, 4, 5, 6, 100, 3], [4, 5, 6, 7, 100, 3], [5, 6, 7, 8, 0, 2]]
        self.assertEqual(M._single_pair_spans('明日は手目が', w), [(3, 5)])
        with _Env(CN_IME_CLASS_SINGLE_PAIR='0'):
            self.assertEqual(M._single_pair_spans('明日は手目が', w), [])

    def test_dictionary_word_kept(self):
        import ime_class_mark as M
        # 左右 は辞書の語
        w = [[0, 1, 0, 2, 100, 3], [1, 2, 2, 3, 100, 3], [2, 3, 3, 4, 0, 2]]
        self.assertEqual(M._single_pair_spans('左右を', w), [])

    def test_bare_pair_at_line_end(self):
        import ime_class_mark as M
        # 後ろに助詞の無い行末の2字（用語を並べた行）は紫にしない
        w = [[0, 1, 0, 1, 100, 3], [1, 2, 1, 2, 100, 3]]
        self.assertEqual(M._single_pair_spans('手目', w), [])
        with _Env(CN_IME_CLASS_SINGLE_PAIR_BARE='1'):
            self.assertEqual(M._single_pair_spans('手目', w), [(0, 2)])


class CleanSentences1120(unittest.TestCase):
    """例文の正しい文に付いていた紫・書き換えを止める決まり（2026-11-20 午後・作った例）。"""
    def test_keyslip_not_to_rarer(self):
        import keyslip_window as W
        self.assertTrue(W._to_rarer('今ケン', '否ケン'))
        self.assertFalse(W._to_rarer('否', '今'))
        with _Env(CN_KEYSLIP_NO_RARER='0'):
            self.assertFalse(W._to_rarer('今ケン', '否ケン'))

    def test_drop_inside_kana_word_is_weak(self):
        import dict_word_keep as K
        line = '三十分かそこらで着く'
        self.assertEqual(K._drop_weak(line, ('ら', '', 'かな入力'))[2], K.DROP_TAG)
        self.assertEqual(K._drop_weak('あいうう', ('う', '', 'かな入力'))[2], 'かな入力')
        with _Env(CN_DICT_WORD_KEEP_DROP='0'):
            self.assertEqual(K._drop_weak(line, ('ら', '', 'かな入力'))[2], 'かな入力')

    def test_broad_predicate_no_purple(self):
        import semantic_fit as F
        self.assertEqual([m for m in F.propose('市場全体の動向を知る。') if m[2] is None], [])
        with _Env(CN_SF_BROAD_PRED='0'):
            self.assertTrue(any(m[2] is None for m in F.propose('市場全体の動向を知る。')))

    def test_question_with_joined_ka(self):
        import question_ka as Q
        self.assertEqual(Q.unanswered_question_spans('いつそれができるかお返事はできません。'), [])
        self.assertTrue(Q.unanswered_question_spans('どこに行きます。'))

    def test_adverb_not_placed_as_noun(self):
        import kana_lattice_place as L
        self.assertTrue(L._not_noun_word('ちょうど私の番だ', 0, 4))
        self.assertFalse(L._not_noun_word('こうえんに行く', 0, 4))

    def test_indefinite_mo_ga(self):
        import broken_shape as B
        self.assertFalse(any(w == '助詞の並びが変です' for *_x, w in B.spans('町の人は誰もがよく笑う。')))

    def test_time_noun_before_verb(self):
        import broken_shape as B
        self.assertFalse(any('語の前に1字' in w for *_x, w in B.spans('彼は明日来ないそうだ。')))


class WagoVerbKanaUsual(unittest.TestCase):
    """意味で分かれる漢字の表記（止める・辞める）で、かなの基本形の方が例文に多い動詞はかなのまま（wago_verb）。"""
    def test_split_meaning_stays_kana(self):
        import wago_verb as W
        self.assertIsNone(W.choose('やめ'))
        self.assertEqual(W.choose('わかり'), '分かり')
        with _Env(CN_WAGO_VERB_KANA_USUAL='0'):
            self.assertIsNotNone(W.choose('やめ'))


class HeadDropCommonNoun(unittest.TestCase):
    def test_common_noun_before_verb(self):
        import broken_shape as B
        import morphology
        toks = list(morphology.tokenize('ここに名前書いておいて'))
        self.assertEqual(B._head_drop_spots(toks), [])


class TypedWordsGuard(unittest.TestCase):
    """読み直しが、身近な漢字の語と助詞だけの所を別の語に替える直しは採らない（odd_respell._typed_words_guard）。"""
    def test_common_kanji_words_kept(self):
        import odd_respell as O
        line = '昨日彼の本を読んだ。'
        res = {'corrected': line}
        out = {'corrected': '昨日これの本を読んだ。'}
        self.assertIs(O._typed_words_guard(res, out, line), res)
        with _Env(CN_RESPELL_TYPED_WORDS='0'):
            self.assertIs(O._typed_words_guard(res, out, line), out)

    def test_line_head_particle_not_kept(self):
        import odd_respell as O
        line = 'も箱に入れます'
        res = {'corrected': line}
        out = {'corrected': '元に入れます'}
        self.assertIs(O._typed_words_guard(res, out, line), out)

    def test_broken_kana_piece_still_fixed(self):
        import odd_respell as O
        line = '札ん港に着いた'
        res = {'corrected': line}
        out = {'corrected': '桟橋に着いた'}
        self.assertIs(O._typed_words_guard(res, out, line), out)


class HomophoneNaSuru(unittest.TestCase):
    """形容動詞の語幹（好調）は する の前に置かない（purple_homophone._na_before_suru）。"""
    def test_na_stem_before_suru(self):
        import purple_homophone as H
        text = '顔が高潮した'
        tok = [t for t in tokenize(text) if t.surface == '高潮'][0]
        self.assertTrue(H._na_before_suru(text, tok, '好調'))
        self.assertFalse(H._na_before_suru(text, tok, '校長'))
        with _Env(CN_PURPLE_HOMOPHONE_NA_SURU='0'):
            self.assertFalse(H._na_before_suru(text, tok, '好調'))


class PairDemonstrative(unittest.TestCase):
    """この・その＋名詞 の組だけでは同じ読みの名詞に替えない（pair_choice）。"""
    def test_demonstrative_only_pair(self):
        import pair_choice as P
        if not P._table():
            self.skipTest('組の表が無い')
        line = 'その士気を落とすな。'
        self.assertEqual(P.propose(line), [])
        with _Env(CN_PAIR_DEMONSTRATIVE='0'):
            self.assertTrue(P.propose(line))


class Mazegaki(unittest.TestCase):
    """交ぜ書き（ひっ越し）は別の語に書き換えず辞書の語にする（dict_word_keep._mazegaki）。"""
    def test_mazegaki_to_dict_face(self):
        import dict_word_keep as D
        out = D._mazegaki('来週ひっ越しする。', {'corrected': '来週筆記する。'})
        self.assertEqual(out['corrected'], '来週引っ越しする。')
        with _Env(CN_DICT_WORD_KEEP_MAZEGAKI='0'):
            self.assertIsNone(D._mazegaki('来週ひっ越しする。', {'corrected': '来週筆記する。'}))


class TimeHeadNoun(unittest.TestCase):
    """時の名詞＋名詞（昔｜写真を）の決め手の無い紫は外す（common_word_purple.time_head_text）。"""
    def test_time_noun_then_noun(self):
        import common_word_purple as C
        self.assertTrue(C.time_head_text('昔写真', 'を'))
        self.assertFalse(C.time_head_text('昔写真', '、'))
        with _Env(CN_COMMON_WORD_TIME_HEAD='0'):
            self.assertFalse(C.time_head_text('昔写真', 'を'))


class LatticeLeadWord(unittest.TestCase):
    """名詞でない語で始まる かな の紫（もう｜そこ）は名詞の表記の迷いにしない（kana_lattice_place._not_noun_word）。"""
    def test_adverb_then_pronoun(self):
        import kana_lattice_place as L
        line = 'もうそこに着いた。'
        self.assertTrue(L._not_noun_word(line, 0, 4))
        with _Env(CN_LATTICE_DOUBT_LEAD_WORD='0'):
            self.assertFalse(L._not_noun_word(line, 0, 4))


class FillerAdnominal(unittest.TestCase):
    """あの・その が名詞の前なら連体詞（broken_shape のフィラーの紫にしない）。"""
    def test_ano_before_noun(self):
        import broken_shape as B
        line = '晴れたらあの店に行こう。'
        self.assertFalse(any('1字が混じって' in w for *_x, w in B.spans(line)))


class AspectAux(unittest.TestCase):
    """身近な動詞＋終える・始める は打ち違いの述語と見ない（predicate_slip._aspect_pair）。"""
    def test_read_finish(self):
        import predicate_slip as P
        toks = list(tokenize('本を読み終えた。'))
        v = [k for k, t in enumerate(toks) if t.surface == '読み'][0]
        self.assertTrue(P._aspect_pair(toks[v], toks[v + 1]))
        with _Env(CN_PS_ASPECT_AUX='0'):
            self.assertFalse(P._aspect_pair(toks[v], toks[v + 1]))


class FormalGapSahen(unittest.TestCase):
    """こと＋サ変の名詞＋する は を の省き（formal_noun_gap）。"""
    def test_koto_sahen_suru(self):
        import formal_noun_gap as F
        self.assertEqual(F.spans('言ったこと心配してる。'), [])
        with _Env(CN_FORMAL_GAP_SAHEN='0'):
            self.assertTrue(F.spans('言ったこと心配してる。'))


class QuestionNumMo(unittest.TestCase):
    """何＋助数詞＋も（何日もの）は疑問ではない（question_ka）。"""
    def test_nan_counter_mo(self):
        import question_ka as Q
        self.assertEqual(Q.unanswered_question_spans('何日もの間、海辺で過ごしました。'), [])
        self.assertTrue(Q.unanswered_question_spans('何日前に着きました。'))


class DanglingParticleAdverb(unittest.TestCase):
    """少し｜もじっ｜と の切り違い（dangling_verb）・待っている｜間｜少しも（broken_shape）。"""
    def test_mo_jitto(self):
        import dangling_verb as D
        self.assertEqual(D.dangling('話す間ちょっともじっとしない。'), [])

    def test_attr_noun_then_adverb(self):
        import broken_shape as B
        self.assertFalse(any('浮いて' in w for *_x, w in B.spans('彼が寝ている間少しも音を立てなかった。')))


class HeadSuffixPronoun(unittest.TestCase):
    """読点の後ろの 君（代名詞）は付く先の無い接尾にしない（ime_reconvert._also_free_noun）・
    時の名詞＋名詞 は隣のキーの紫にしない（keyslip_window._time_head）。"""
    def test_kimi_after_comma(self):
        import ime_reconvert as R
        self.assertTrue(R._also_free_noun('君'))
        self.assertFalse(R._also_free_noun('的'))

    def test_keyslip_time_head(self):
        import keyslip_window as K
        line = '長い間お手数をかけました。'
        self.assertTrue(K._time_head(line, 2, 6))
        with _Env(CN_KEYSLIP_TIME_HEAD='0'):
            self.assertFalse(K._time_head(line, 2, 6))


class LatticeCutWord(unittest.TestCase):
    """副詞・連体詞の途中で切れる所に名詞を置かない（kana_lattice_place._cuts_word）。"""
    def test_cut_adverb(self):
        import kana_lattice_place as L
        line = 'しかと見届けた。'
        self.assertTrue(L._cuts_word(line, 0, 2))
        with _Env(CN_LATTICE_CUT_WORD='0'):
            self.assertFalse(L._cuts_word(line, 0, 2))


class KeyslipKanaNoun(unittest.TestCase):
    def test_whole_kana_noun_kept(self):
        import keyslip_window as K
        self.assertTrue(K._whole_kana_noun('一かけら', '初めから毛'))
        self.assertFalse(K._whole_kana_noun('一かけら', '一かけらの'))


class SuruPieces(unittest.TestCase):
    """漢字1字の名詞2つ以上に切れた並び＋する は名詞＋する の形と見ない（odd_reason_fill._suru_form）。
    片仮名の語＋って の続けて置けない紫は外す（common_word_purple.drop_kata_te）。"""
    def test_pieces_before_suru(self):
        import odd_reason_fill as O
        line = '書類乳力します。'
        toks = list(tokenize(line))
        self.assertFalse(O._suru_form(line, toks, 0, 5))
        with _Env(CN_ODD_REASON_SURU_PIECES='0'):
            self.assertTrue(O._suru_form(line, toks, 0, 5))

    def test_kata_te(self):
        import common_word_purple as C
        r = {'odd_spans': [(2, 6)], 'odd_reasons': [(2, 6, '「って」と「から」は続けて置けない')]}
        self.assertEqual(C.drop_kata_te('ハモってから歌う。', r)['odd_spans'], [])


class HonorProhibitPronoun(unittest.TestCase):
    """お＋連用形＋いただく（te_dropped）・言い切り＋な＋と（common_word_purple）・いつ＋な＋の（kana_lattice_place）。"""
    def test_o_itadaku(self):
        import te_dropped as T
        self.assertEqual(T.propose('お越しいただき感謝します。'), [])

    def test_prohibit_quote(self):
        import common_word_purple as C
        line = '弟に触るなと言った。'
        r = {'corrected': line, 'odd_spans': [(2, 6)], 'odd_reasons': [(2, 6, '前後の語とのつながりが辞書で確かめられません')]}
        self.assertEqual(C.drop_prohibit_quote(line, r)['odd_spans'], [])

    def test_pronoun_aux(self):
        import kana_lattice_place as L
        self.assertTrue(L._not_noun_word('出発はいつなの？', 3, 6))


class HomophoneNearRank(unittest.TestCase):
    def test_near_rank(self):
        import purple_homophone as H
        self.assertTrue(H._near_rank('発送', '発想'))
        self.assertFalse(H._near_rank('飼料', '資料'))


class TeNounAru(unittest.TestCase):
    def test_chigai_aru(self):
        import te_dropped as T
        self.assertEqual(T.propose('来たのにちがいありません。'), [])
        with _Env(CN_TE_NOUN_ARU='0'):
            self.assertTrue(T.propose('来たのにちがいありません。'))


class PrefixSuffixHonor(unittest.TestCase):
    """ご＋名詞（rollin_word）・名詞＋ら（keyslip_window）・おこし＋ください（te_dropped）。"""
    def test_go_noun(self):
        import rollin_word as R
        self.assertTrue(R._prefix_noun('ご意見を伺う。', 0, 3))

    def test_kana_suffix(self):
        import keyslip_window as K
        self.assertTrue(K._kana_suffix('学生ら', '学生に'))
        self.assertFalse(K._kana_suffix('学生ら', '学生らに'))

    def test_o_joined_kudasai(self):
        import te_dropped as T
        self.assertEqual(T.propose('ぜひおこしください。'), [])


class RespellKanaGuards(unittest.TestCase):
    """読み直しは辞書の1語の中の字を消すだけの直しはしない（odd_respell._inner_delete_guard）。"""
    def test_inner_delete(self):
        import odd_respell as O
        line = 'それじゃ、おやすみ。'
        res = {'corrected': line}
        out = {'corrected': 'それじゃ、やすみ。'}
        self.assertIs(O._inner_delete_guard(res, out, line), res)
        with _Env(CN_RESPELL_INNER_DELETE='0'):
            self.assertIs(O._inner_delete_guard(res, out, line), out)


class HeadDropOneKanji(unittest.TestCase):
    """1字の漢字の名詞＋動詞（を を省いた話し言葉）は頭の1打の足しと見ない（broken_shape._head_drop_spots）。"""
    def test_one_kanji_noun_verb(self):
        import broken_shape as BS
        line = '箱に鍵かけた？'
        self.assertFalse(any(w == '語の前に1字が混じっています' for _a, _b, w in BS.spans(line)))


class DanglingMimetic(unittest.TestCase):
    """平仮名の 〜ん＋と（擬態語）は て・た の抜けた動詞と見ない（dangling_verb._mimetic_n_to）。"""
    def test_mimetic(self):
        import dangling_verb as D
        self.assertEqual(D.propose('しっぽはくるんとしてる。'), [])
        with _Env(CN_DANGLING_MIMETIC='0'):
            self.assertNotEqual(D.propose('しっぽはくるんとしてる。'), [])


class KataRuVerb(unittest.TestCase):
    """片仮名の名詞＋る の話し言葉の動詞（サボった）の片仮名の中の紫は外す（common_word_purple.drop_kata_ru）。"""
    def test_kata_ru(self):
        import common_word_purple as C
        line = '昨日は授業をサボった。'
        res = {'corrected': line, 'odd_spans': [(6, 7)], 'odd_reasons': [(6, 7, '語になりません')]}
        self.assertEqual(C.drop_kata_ru(line, res)['odd_spans'], [])
        with _Env(CN_COMMON_WORD_KATA_RU='0'):
            self.assertEqual(C.drop_kata_ru(line, res)['odd_spans'], [(6, 7)])


class FillerParticle(unittest.TestCase):
    """助詞の後ろの なんか は副助詞（broken_shape: CN_BROKEN_FILLER_PARTICLE）。"""
    def test_nanka(self):
        import broken_shape as BS
        line = '僕になんか興味もないよ。'
        self.assertFalse(any('文の途中' in w for _a, _b, w in BS.spans(line)))


class KeyslipSuffixCompound(unittest.TestCase):
    """接尾の名詞で作る語（冬中・2年半）には打ち違いの紫を足さない（keyslip_window._suffix_compound）。"""
    def test_suffix_compound(self):
        import keyslip_window as K
        self.assertTrue(K._suffix_compound('その冬中寒かった', 2, 4))
        self.assertFalse(K._suffix_compound('その冬は寒かった', 2, 4))
        with _Env(CN_KEYSLIP_SUFFIX_COMPOUND='0'):
            self.assertFalse(K._suffix_compound('その冬中寒かった', 2, 4))


class DoubleHonorAux(unittest.TestCase):
    """お＋連用の名詞＋いただく の い の並びは余りと見ない（last_keystroke: CN_DOUBLE_HONOR_AUX）。"""
    def test_honor_aux(self):
        import last_keystroke as L
        from morphology import tokenize
        line = 'こちらの棚をお使いいただけます。'
        self.assertFalse(any('余って' in str(x) for x in L._impossible_kana_spans(line, list(tokenize(line)))))
        with _Env(CN_DOUBLE_HONOR_AUX='0'):
            self.assertTrue(any('余って' in str(x) for x in L._impossible_kana_spans(line, list(tokenize(line)))))


class PrefixRow(unittest.TestCase):
    """形容詞に付く接頭詞（超）＋形容詞は崩れた形と見ない（broken_shape: CN_BROKEN_PREFIX_ROW）。"""
    def test_cho_adj(self):
        import broken_shape as BS
        line = 'この店は超おいしい。'
        self.assertFalse(any('前に付く字' in w for _a, _b, w in BS.spans(line)))
        with _Env(CN_BROKEN_PREFIX_ROW='0'):
            self.assertTrue(any('前に付く字' in w for _a, _b, w in BS.spans(line)))


class HomophoneVariant(unittest.TestCase):
    """同じ語の別の書き方（奇麗→綺麗）には替えず紫を外す（purple_homophone._variant）。"""
    def test_variant(self):
        import purple_homophone as H
        from morphology import tokenize
        tok = [x for x in tokenize('机が奇麗だ') if x.surface == '奇麗'][0]
        self.assertTrue(H._variant(tok, '綺麗'))
        self.assertFalse(H._variant(tok, '帰来'))
        with _Env(CN_PURPLE_HOMOPHONE_VARIANT='0'):
            self.assertFalse(H._variant(tok, '綺麗'))


class KataCounter(unittest.TestCase):
    """数＋片仮名の助数詞（５千ドル）は混じった片仮名と見ない（broken_shape: CN_KATA_COUNTER）。"""
    def test_counter(self):
        import broken_shape as BS
        line = '彼は５千ドル払った。'
        self.assertFalse(any('片仮名' in w for _a, _b, w in BS.spans(line)))
        with _Env(CN_KATA_COUNTER='0'):
            self.assertTrue(any('片仮名' in w for _a, _b, w in BS.spans(line)))


class MazegakiOneWord(unittest.TestCase):
    """1語の かな の送り（思い）は交ぜ書きと見て漢字に替えない（dict_word_keep._mazegaki）。"""
    def test_one_word(self):
        import dict_word_keep as W
        line = '鞄が思い'
        self.assertIsNone(W._mazegaki(line, {'corrected': '鞄が重い'}))


class PairOutweighRare(unittest.TestCase):
    """例文の組がはるかに多い同じ読みの動詞（描く）は、稀な読みでも直す（semantic_fit・dict_word_keep）。"""
    def test_pair_outweighs(self):
        import dict_word_keep as W
        self.assertTrue(W._pair_outweighs('壁に絵を書く', '壁に絵を描く', 4, 4, 5))
        with _Env(CN_DICT_WORD_KEEP_PAIR_OUTWEIGH='0'):
            self.assertFalse(W._pair_outweighs('壁に絵を書く', '壁に絵を描く', 4, 4, 5))


class MazegakiRareFace(unittest.TestCase):
    """交ぜ書きの先が表の珍しい語なら置かない（dict_word_keep._mazegaki）。"""
    def test_rare_face(self):
        import dict_word_keep as W
        self.assertIsNone(W._mazegaki('作業茶う', {'corrected': '作業中'}))


class LatticeAdverbBeforeCase(unittest.TestCase):
    """副詞としてしか辞書に無い かな でも、すぐ後ろが格助詞なら名詞の置き場所（kana_lattice_place._not_noun_word）。"""
    def test_adverb_before_case(self):
        import kana_lattice_place as K
        self.assertFalse(K._not_noun_word('いとをくんで', 0, 2))
        self.assertTrue(K._not_noun_word('ちょうどよい', 0, 4))


class LatticeLeadWordPieces(unittest.TestCase):
    """1字の かな に切れる並びは名詞でない語の並びと見ない（kana_lattice_place._not_noun_word）。"""
    def test_pieces(self):
        import kana_lattice_place as K
        self.assertFalse(K._not_noun_word('ぎょうばんごうを', 0, 7))
        # 付属の1字（接頭詞・助動詞）に切れるだけの並びは語の並びのまま（作り例）
        self.assertTrue(K._not_noun_word('もうこりごりです', 0, 6))


class WideDoubtDropWord(unittest.TestCase):
    """広い迷いの行でも、余分な1字を抜くと辞書の名詞の読みが現れる戻しは止めない（作り例）。"""

    def test_drop_makes_word(self):
        import last_keystroke as K
        self.assertTrue(K._drop_makes_word('ていさあんをみた', 'ていあんをみた'))

    def test_substitution_not(self):
        import last_keystroke as K
        self.assertFalse(K._drop_makes_word('そのえいがは', 'そのえいがぱ'))
        self.assertFalse(K._drop_makes_word('いえでねてた', 'いえでもてた'))


class KanaKeepPerKango(unittest.TestCase):
    """漢語の名詞と動詞が続けて置かれた所は語ごとに見て、漢語の名詞と動詞を戻さない（作り例）。"""

    def test_split(self):
        import kana_keep as K
        r = K.repair_line('せつめいかいています', {'corrected': '説明書いています'})
        self.assertEqual(r.get('corrected'), '説明書いています')

    def test_lone_verb_same(self):
        import kana_keep as K
        r = K.repair_line('ほんをみています', {'corrected': '本を見ています'})
        self.assertEqual(r.get('corrected'), '本をみています')


class RespellRankLines(unittest.TestCase):
    """候補の何回目の集計: 同じ行は1つにまとめ、候補の種類を残す（作り例）。"""

    def test_kind(self):
        import odd_respell as O
        self.assertEqual(O.candidate_kind('てえあんです', 'ていあんです'), '1字置き換え')
        self.assertEqual(O.candidate_kind('かいすせき', 'かいせき'), '1字抜き')
        self.assertEqual(O.candidate_kind('あいう', 'いあう'), '入れ替え')

    def test_same_line_once(self):
        import respell_stats as RS
        RS.clear()
        one = {'lines': {'てえあんです': [1, 3, '提案です', ['1字置き換え', '2字以上', '2字以上']]}}
        RS.merge(one)
        RS.merge(one)
        snap = RS.snapshot()
        self.assertEqual(len(snap['lines']), 1)
        self.assertIn('1字置き換え', RS.text())
        RS.clear()


class ReasonFillEvening(unittest.TestCase):
    """紫の外し: 読みの書き添えの かな の側・数を表す英字1字・身近な名詞1語（作り例）。"""

    def _toks(self, line):
        from morphology import tokenize
        return list(tokenize(line))

    def test_kana_reading_beside(self):
        import odd_reason_fill as O
        line = '・あさかつ（朝活）'
        self.assertTrue(O._kana_reading_of_beside(line, self._toks(line), 1, 5))
        line = '・あさかつ'
        self.assertFalse(O._kana_reading_of_beside(line, self._toks(line), 1, 5))

    def test_letter_counter(self):
        import odd_reason_fill as O
        line = 'そのk番目の字'
        self.assertTrue(O._letter_counter(line, self._toks(line), 0, 3))
        line = 'あいうえk'
        self.assertFalse(O._letter_counter(line, self._toks(line), 0, 5))

    def test_common_noun_slot(self):
        import odd_reason_fill as O
        line = '会議の時間'
        self.assertTrue(O._common_noun_slot(line, self._toks(line), 0, 2))
        line = '会議した'
        self.assertTrue(O._common_noun_slot(line, self._toks(line), 0, 2))
        line = '会議ね'
        self.assertFalse(O._common_noun_slot(line, self._toks(line), 0, 2))


class EveningKanaShiftAndGloss(unittest.TestCase):
    """かなの並びの濁点のずれ・読みを書き添えた語の単体見直し（作り例）。"""

    def test_kana_dakuten_shift(self):
        import dakuten_shift as D
        self.assertEqual(D.propose_kana('だたしいこたえ', [(0, 4)]), [(0, 4, '正しい')])

    def test_glossed_chunk(self):
        import chunk_alone as C
        self.assertTrue(C._changes_glossed('朝活／朝の時間', '悪活／朝の時間', {'あさかつ'}))
        self.assertFalse(C._changes_glossed('朝活／朝の時間', '朝活／朝の時間', {'あさかつ'}))


class CleanRewriteGuards(unittest.TestCase):
    """正しい文の書き換え止め（作り例）。"""

    def test_function_words_only(self):
        import kana_spelling as K
        self.assertTrue(K._function_words_only('走るからだ。', 2, 5))
        self.assertFalse(K._function_words_only('からだがいたい', 0, 3))

    def test_adverb_function_tail(self):
        import kana_spelling as K
        self.assertTrue(K._adverb_function_tail('へえ、そうなんだ。', 3, 7))
        self.assertFalse(K._adverb_function_tail('へえ、そうなんだ。', 3, 5))

    def test_extra_before_adverbial_noun(self):
        import broken_shape as B
        self.assertEqual(B.extra_chars('私は県全体を見た。'), [])


class LexicalPairPurple(unittest.TestCase):
    """名詞＋形容詞の連用形が表の1語の読み（うんわるく）のとき「続けて置けない」の紫を外す（作り例）。"""

    def test_drop(self):
        import correction_entry as ce
        r = {'corrected': '運悪く雨だ。', 'odd_spans': [(0, 3)], 'odd_reasons': [(0, 3, '「運」と「悪く」は続けて置けない')]}
        self.assertEqual(ce._lexical_pair_ok('運悪く雨だ。', r)['odd_spans'], [])

    def test_keep_unknown(self):
        import correction_entry as ce
        r = {'corrected': '運早く着いた。', 'odd_spans': [(0, 3)], 'odd_reasons': [(0, 3, '「運」と「早く」は続けて置けない')]}
        self.assertEqual(ce._lexical_pair_ok('運早く着いた。', r)['odd_spans'], [(0, 3)])


class SahenShiTe(unittest.TestCase):
    """…する の し＋て の「続けて置けない」の紫を外す（作り例）。"""

    def test_drop(self):
        import correction_entry as ce
        line = '毎日の仕事にあきあきしている。'
        k = line.index('あきあき')
        r = {'corrected': line, 'odd_spans': [(k, k + 6)], 'odd_reasons': [(k, k + 6, '「あきあきし」と「て」は続けて置けない')]}
        self.assertEqual(ce._sahen_shi_te_ok(line, r)['odd_spans'], [])


class LonePronoun(unittest.TestCase):
    """漢字1字の代名詞は 1字だけ浮いて の紫にしない（作り例）。"""

    def test_pronoun(self):
        import broken_shape as B
        self.assertFalse([x for x in B.spans('なんで俺そんなこと言うの？') if '浮いて' in x[2]])

    def test_kata_whole_word(self):
        import broken_shape as B
        self.assertFalse([x for x in B.spans('もう腹ペコだよ。') if '片仮名' in x[2]])

    def test_attr_noun_comma(self):
        import broken_shape as B
        self.assertFalse([x for x in B.spans('母が描いた絵、見ていい？') if '言い終わり' in x[2]])

    def test_lone_exist(self):
        import broken_shape as B
        self.assertFalse([x for x in B.spans('もう通す気ないよ。') if '浮いて' in x[2]])

    def test_join_next(self):
        import broken_shape as B
        self.assertFalse([x for x in B.spans('もう先延ばしはしない。') if '浮いて' in x[2]])


class NumSuffixBetween(unittest.TestCase):
    """数＋接尾1字＋間 の「続けて置けない」の紫を外す（作り例）。"""

    def test_drop(self):
        import correction_entry as ce
        line = '３者間の話し合いが続いた。'
        r = {'corrected': line, 'odd_spans': [(1, 3)], 'odd_reasons': [(1, 3, '「者」と「間」は続けて置けない')]}
        self.assertEqual(ce._num_suffix_between_ok(line, r)['odd_spans'], [])


class QuoteAfterParticle(unittest.TestCase):
    """助詞＋引用の って の「続けて置けない」の紫を外す（作り例）。"""

    def test_drop(self):
        import correction_entry as ce
        line = '答えは明日でって、言われた。'
        r = {'corrected': line, 'odd_spans': [(5, 8)], 'odd_reasons': [(5, 8, '「で」と「って」は続けて置けない')]}
        self.assertEqual(ce._quote_after_particle_ok(line, r)['odd_spans'], [])


class KanaRunAdverbHead(unittest.TestCase):
    """副詞だけの語のあとの形容詞・じゃぁ の縮まった形を、かなの並びとして説明する（作り例）。"""

    def test_adverb_then_adjective(self):
        import pos_grammar as PG
        self.assertTrue(PG.explain_kana_run('はずいぶんよくなった', after_kanji=True))

    def test_interjection_head(self):
        import pos_grammar as PG
        self.assertTrue(PG.explain_kana_run('さあいこう'))
        self.assertTrue(PG.explain_kana_run('さあこい'))

    def test_te_yo(self):
        import pos_grammar as PG
        self.assertTrue(PG.explain_kana_run('まってよ'))

    def test_te_sa(self):
        import pos_grammar as PG
        self.assertTrue(PG.explain_kana_run('たべてさ'))

    def test_noun_ne(self):
        import pos_grammar as PG
        self.assertTrue(PG.explain_kana_run('わせね', after_kanji=True, kanji_stem='打ち合'))

    def test_kanji_noun_yo(self):
        import pos_grammar as PG
        self.assertTrue(PG.explain_kana_run('よ', after_kanji=True, kanji_stem='先生'))

    def test_jaa_small(self):
        import pos_grammar as PG
        self.assertTrue(PG.explain_kana_run('はうまくいくんじゃぁないかな', after_kanji=True))

    def test_mizen_nu(self):
        import pos_grammar as PG
        self.assertTrue(PG.explain_kana_run('をとらぬように', after_kanji=True))

    def test_written_verb_not_broken_polite(self):
        import pos_grammar as PG
        class _Empty:
            def __getattr__(self, name):
                return lambda *a, **k: ()
        self.assertEqual(PG._broken_polite_end_spans('大雨が町に被害をもたらした。', _Empty()), ())


class DegreeDigitHead(unittest.TestCase):
    """程度の副詞＋数字で始まる語は量として見る（作り例）。"""

    def test_digit(self):
        import degree_adverb as D
        self.assertEqual(D.propose('来たのはせいぜい３０人だ。', None), [])


class VerbListing(unittest.TestCase):
    """動詞を2つ並べて名詞に掛ける形の「続けて置けない」の紫を外す（作り例）。"""

    def test_drop(self):
        import correction_entry as ce
        line = '押す引くの騒ぎになった。'
        r = {'corrected': line, 'odd_spans': [(0, 4)], 'odd_reasons': [(0, 4, '「押す」と「引く」は続けて置けない')]}
        self.assertEqual(ce._verb_listing_ok(line, r)['odd_spans'], [])


class GaruPurple(unittest.TestCase):
    """形容詞の語幹＋がる の「続けて置けない」の紫を外す（作り例）。"""

    def test_drop(self):
        import correction_entry as ce
        line = '猫を面白がって見ていた。'
        r = {'corrected': line, 'odd_spans': [(4, 7)], 'odd_reasons': [(4, 7, '「が」と「って」は続けて置けない')]}
        self.assertEqual(ce._garu_ok(line, r)['odd_spans'], [])


class CollocClassSahen(unittest.TestCase):
    """サ変の名詞＋を＋する を意味の仲間の語に替えない（作り例）。"""

    def test_sahen(self):
        import collocation_repair as C
        self.assertFalse([x for x in C.find('机の整頓をしなさい。') if x[2] == '精神'])


class KanaVerbGuardLatin(unittest.TestCase):
    """かなの用言を守る段が、英字の残った紫まで外さない（作り例）。"""

    def test_keep_latin_purple(self):
        import odd_respell as O
        line = '父にrたのまれて店へ行った'
        res = {'corrected': line, 'odd_spans': [(1, 8)], 'odd_reasons': [(1, 8, 'x')]}
        out = {'corrected': '父に頼まれて店へ行った', 'odd_spans': []}
        orig = O._common_kana_verbs
        O._common_kana_verbs = lambda text: [(4, 7)]
        try:
            got = O._kana_verb_guard(res, out, line)
        finally:
            O._common_kana_verbs = orig
        self.assertEqual(got['odd_spans'], [(1, 8)])


class ConnectiveNoun(unittest.TestCase):
    """名詞＋対＋名詞 の「続けて置けない」の紫を外す（作り例）。"""

    def test_drop(self):
        import correction_entry as ce
        line = '日本対中国の試合だ。'
        r = {'corrected': line, 'odd_spans': [(0, 5)],
             'odd_reasons': [(0, 3, '「日本」と「対」は続けて置けない'), (0, 5, '前後の語とのつながりが辞書で確かめられません')]}
        self.assertEqual(ce._connective_noun_ok(line, r)['odd_spans'], [])


class StemSuruVerb(unittest.TestCase):
    """漢字＋する の動詞の し＋て（恋して）を形容詞の語幹＋て の印にしない（作り例）。"""

    def test_koi_shite(self):
        import last_keystroke as L, morphology
        toks = list(morphology.tokenize('恋してしまった。'))
        self.assertEqual(L._conjugation_mismatch(toks), set())

    def test_adj_te_still_marked(self):
        import last_keystroke as L, morphology
        toks = list(morphology.tokenize('新しい靴だ。'))
        self.assertEqual(L._conjugation_mismatch(toks), set())


class PronounSplitWord(unittest.TestCase):
    """代名詞＋辞書が割った1語の名詞（聞き上手）の紫を外す（作り例）。"""

    def test_drop(self):
        import correction_entry as ce
        line = '私聞き上手なの。'
        r = {'corrected': line, 'odd_spans': [(0, 5)],
             'odd_reasons': [(0, 3, '「私」と「聞き」は続けて置けない'), (1, 5, '「聞き」と「上手」は続けて置けない'),
                             (0, 5, '前後の語とのつながりが辞書で確かめられません')]}
        self.assertEqual(ce._pronoun_split_word_ok(line, r)['odd_spans'], [])

    def test_keep_not_word(self):
        import correction_entry as ce
        line = '私開き上手なの。'
        r = {'corrected': line, 'odd_spans': [(0, 5)],
             'odd_reasons': [(0, 3, '「私」と「開き」は続けて置けない'), (1, 5, '「開き」と「上手」は続けて置けない')]}
        self.assertEqual(ce._pronoun_split_word_ok(line, r)['odd_spans'], [(0, 5)])


class AttrVerbKata(unittest.TestCase):
    """形容動詞の語幹＋な＋動詞の連用形＋方 の理由の無い紫を外す（作り例）。"""

    def test_drop(self):
        import odd_reason_fill as F
        line = '楽な死に方だ。'
        r = F.fill(line, {'corrected': line, 'odd_spans': [(0, 4)], 'odd_reasons': []})
        self.assertEqual(list(r.get('odd_spans') or ()), [])


class LkMismatchExceptions(unittest.TestCase):
    """お＋連用形＋ください・形容詞＋連用形の名詞＋格助詞 を活用の合わない印にしない（作り例）。"""

    def test_honor_o(self):
        import last_keystroke as L, morphology
        self.assertEqual(L._conjugation_mismatch(list(morphology.tokenize('あちらへおこしください。'))), set())

    def test_adj_renyou_noun(self):
        import last_keystroke as L, morphology
        self.assertEqual(L._conjugation_mismatch(list(morphology.tokenize('正しいこたえを書く。'))), set())

    def test_adj_verb_still_marked(self):
        import last_keystroke as L, morphology
        self.assertTrue(L._conjugation_mismatch(list(morphology.tokenize('高いなった。'))))


class CleanRewriteGuardsF(unittest.TestCase):
    """例文の正しい文の書き換えを止める決まり（作り例）。"""

    def test_adverb_suru(self):
        import kana_spelling as K
        self.assertTrue(K._adverb_function_tail('ああ、どうしよう。', 3, 8))

    def test_extra_before_noun(self):
        import broken_shape as B
        self.assertEqual(B.extra_chars('町は市北部にある。'), [])

    def test_te_particle_place(self):
        import kana_lattice_place as K
        self.assertEqual(K._fix_places('ここで寝てはいかん。', [(5, 9, '配管')]), [])

    def test_prefix_word_place(self):
        import kana_lattice_place as K
        self.assertEqual(K._fix_places('みんな、ごきげんいかが。', [(5, 8, '期限')]), [(5, 8, '機嫌')])

    def test_long_mark_word(self):
        import odd_respell as O
        line = 'ばーちゃんが来た。'
        r = {'corrected': line}
        self.assertIs(O._long_mark_word_guard(r, {'corrected': 'バー茶なが来た。'}, line), r)

    def test_kana_word_reading(self):
        import odd_respell as O
        line = '庭のもくせいの花だ。'
        r = {'corrected': line}
        self.assertIs(O._kana_word_reading_guard(r, {'corrected': '庭のみくらいの花だ。'}, line), r)

    def test_n_contraction(self):
        import correction_entry as ce
        line = 'そんなこと気にすんな。'
        r = ce._explained_kana_revert(line, {'corrected': 'そんなこと気にすな。', 'changed': True})
        self.assertEqual(r['corrected'], line)


class QuestionDatte(unittest.TestCase):
    """疑問の語＋だって は疑問ではない（作り例）。"""

    def test_datte(self):
        import question_ka as Q
        self.assertEqual(Q.unanswered_question_spans('どこにだって行けます。'), [])


class HumbleShi(unittest.TestCase):
    """お＋連用形＋し の言いさし（作り例）。"""

    def test_humble_shi(self):
        import pos_grammar as PG
        self.assertTrue(PG.explain_kana_run('をおまちし', after_kanji=True))


class PrevLineOff(unittest.TestCase):
    """補正は1行の中だけで決まる（うに 11-21 00:03Z「止める」・作り例）。"""

    def test_no_previous_tail(self):
        import correction_entry as ce
        self.assertEqual(ce._continuation_prefix('今日の会議の資料', 'をまとめておく。'), 'それ')
        # 行の頭の1字は続きとして読まず、その行だけで直す（うに 11-21 02:48Z「直す方向で」）
        self.assertFalse(ce.head_may_continue('今日は休みです。'))
        with _Env(CN_HEAD_ALONE_FIX='0'):
            self.assertTrue(ce.head_may_continue('今日は休みです。'))

    def test_keep_head_fix(self):
        import correction_entry as ce
        res = {'original': 'に別の道具', 'corrected': '人別の道具', 'changed': True, 'details': [['に', '人', 'x']],
               'spans': [[0, 1]], 'original_spans': [[0, 1]], 'odd_spans': []}
        res['details'] = [['に別', '入力', 'x']]; res['spans'] = [[0, 2]]; res['original_spans'] = [[0, 2]]; res['corrected'] = '入力の道具'
        self.assertIs(ce._clear_head(res, {'corrected': 'に別の道具'}, 'に別の道具', 1), res)

    def test_head_alone_natural(self):
        # 行の頭の助詞＋身近な語がふつうに読める行は崩さず、行の頭の字を捨てるだけの直しもしない（作り例の読み）
        import head_particle_keep as H, keyslip_window as KW
        from morphology import tokenize
        self.assertEqual(KW._stacked_no(list(tokenize('の本は'))), [])
        self.assertTrue(H._rest_reads('に後ろから抱きついた。', '人後ろから抱きついた。'))
        with _Env(CN_HEAD_ALONE_NATURAL='0'):
            self.assertFalse(H._rest_reads('に後ろから抱きついた。', '人後ろから抱きついた。'))

    def test_no_other_line_words(self):
        import inspect, correction_entry as ce
        self.assertIn('CN_NEARBY_WORDS_OFF', inspect.getsource(ce.correct_line))


class AttrNounBracket(unittest.TestCase):
    """連体の形＋2拍以上の1字の名詞＋開き括弧は正しい形（作り例）。"""

    def test_attr_noun_bracket(self):
        import broken_shape as BS
        text = '待っている間（長い）本を読んだ。'
        self.assertEqual([x for x in BS.spans(text) if '言い終わり' in x[2]], [])
        with _Env(CN_BROKEN_ATTR_BRACKET='0'):
            self.assertNotEqual([x for x in BS.spans(text) if '言い終わり' in x[2]], [])


class NumSpace(unittest.TestCase):
    """数字の前後の空白1つは抜いた行で読み、答えを元の位置へ戻す（作り例）。"""

    def test_squeeze_and_rebuild(self):
        import num_space as N
        sq, pos, gone = N._squeeze('最大 3 日間')
        self.assertEqual(sq, '最大3日間')
        self.assertEqual(gone, (2, 4))
        self.assertEqual(N._rebuild('あい 2 うえ', 'あい2うえ', 'あい2うXえ', *N._squeeze('あい 2 うえ')[1:])[0], 'あい 2 うXえ')
        self.assertIsNone(N._squeeze('ver 2.0 OK')[1])

    def test_installed(self):
        import correction_entry as ce, inspect
        self.assertIn('num_space', inspect.getsource(ce))


class BorrowedVerbFit(unittest.TestCase):
    """元の動詞の例が少ない時は借りた仲間で見て、別の動詞の組が例文に在れば直す（作り例の読み）。"""

    def test_borrowed_mark(self):
        import semantic_fit as S
        toks = list(tokenize('英語の言葉を離した'))
        k = next(i for i, t in enumerate(toks) if t.surface.startswith('離'))
        self.assertEqual(S._borrowed_mark(toks[k], toks[k - 1], toks[k - 2], '離す')[2], '話し')
        with _Env(CN_SF_BORROW_OWN='0'):
            self.assertIsNone(S._borrowed_mark(toks[k], toks[k - 1], toks[k - 2], '離す'))

    def test_variant_kept(self):
        import semantic_fit as S
        toks = list(tokenize('子供から目を離した'))
        k = next(i for i, t in enumerate(toks) if t.surface.startswith('離'))
        self.assertIsNone(S._borrowed_mark(toks[k], toks[k - 1], toks[k - 2], '離す'))


class ImeRareSameClass(unittest.TestCase):
    """同じ仲間の語を並べた行の語は、珍しいというだけで紫にしない（作り例）。"""

    def test_same_class(self):
        import ime_reconvert as R
        line = '名詞と動詞と副詞の表'
        self.assertTrue(R._same_class_in_line(line, (6, 8)))
        self.assertFalse(R._same_class_in_line('福祉の仕事をする', (0, 2)))
        with _Env(CN_IME_RARE_SAME_CLASS='0'):
            self.assertFalse(R._same_class_in_line(line, (6, 8)))


class KanaKeepCompound(unittest.TestCase):
    """漢字のまま残る漢語と続く和語の名詞は、かなに戻さず複合語のまま漢字にする（作り例）。"""

    def test_compound(self):
        import kana_keep as K
        self.assertEqual(K.repair_line('うりあげかんり', {'corrected': '売り上げ管理'})['corrected'], '売り上げ管理')
        self.assertEqual(K.repair_line('よこはばせってい', {'corrected': '横幅設定'})['corrected'], '横幅設定')
        with _Env(CN_KANA_KEEP_COMPOUND='0'):
            self.assertEqual(K.repair_line('うりあげかんり', {'corrected': '売り上げ管理'})['corrected'], 'うりあげ管理')

    def test_alone_still_back(self):
        import kana_keep as K
        self.assertTrue(K.repair_line('うりあげがのびた', {'corrected': '売り上げが伸びた'})['corrected'].startswith('うりあげが'))


class FrameGuardLightVerb(unittest.TestCase):
    """「名詞を＋やる・する」の名詞の打ち違いは、軽い動詞の組の数が少なくても直す（作り例）。"""

    def test_switch_in_source(self):
        import correction_entry as ce, inspect
        self.assertIn('CN_FRAME_GUARD_LIGHT_KANA', inspect.getsource(ce))


class TeAuxRenyo(unittest.TestCase):
    """未然形＋て（こ｜て｜い）は て＋補助の動詞の形と見ない（作り例）。"""

    def test_spots(self):
        import guess_back as G
        self.assertEqual(G._te_aux_spots('あるくこてい'), [])
        self.assertEqual(G._te_aux_spots('みている'), [(1, 2)])
        with _Env(CN_TE_AUX_RENYO='0'):
            self.assertEqual(G._te_aux_spots('あるくこてい'), [(4, 5)])


class KnownWordGuard(unittest.TestCase):  # noqa
    """打ったかなの中の、格子がふだんの漢字の名詞と切る語を別の読みに書き換えた行は採らない（作り例）。"""

    def test_guard(self):
        import known_word_guard as G
        from tests_analysis_async import initial
        st = initial()
        line = 'きのうはとしょかんでほんをかりた'
        bad = line.replace('としょかん', 'とひょかん')
        with _Env(CN_KNOWN_WORD_GUARD='1'):
            r = G.guard(line, {'corrected': bad, 'odd_spans': []}, st.store, st.dict_index)
        self.assertEqual(r['corrected'], line)
        self.assertEqual(r['odd_spans'], [(4, 9)])
        # 1 でなければ止めている（既定。rival_exit_guard が同じ誤りを紫にする）
        with _Env(CN_KNOWN_WORD_GUARD='0'):
            r = G.guard(line, {'corrected': bad, 'odd_spans': []}, st.store, st.dict_index)
            self.assertEqual(r['corrected'], bad)

    def test_installed(self):
        import correction_entry as ce, inspect
        self.assertIn('known_word_guard', inspect.getsource(ce))
        self.assertIn('purple_restore', inspect.getsource(ce))


class PurpleRestore(unittest.TestCase):
    def test_restore(self):
        import purple_restore as P, kana_lattice_place as K
        if not P._orig:
            self.skipTest('not installed')
        self.assertTrue(hasattr(K, '_CLEARED'))



class StrayMarkGuard(unittest.TestCase):
    """前の字に付けられない ゛゜ は、消す・2つ前の字に付ける・次の字に付けるの3つの形を比べる（作り例）。"""

    def test_candidates(self):
        import stray_mark_guard as G
        self.assertEqual(G.stray_at('はしが゛おおきい'), 3)
        self.assertIsNone(G.stray_at('かき゛'))
        cs = G.candidates('かぜ゛かつよい', 2)
        self.assertEqual(cs['drop'], 'かぜかつよい')
        self.assertEqual(cs['fwd'], 'かぜがつよい')
        self.assertEqual(G.candidates('はしが゛おおきい', 3)['back'], 'はじがおおきい')
        self.assertNotIn('fwd', G.candidates('はしが゛おおきい', 3))
        # 前の2字の打つ順も入れ替わった形
        self.assertEqual(G.candidates('たこま゛を', 3)['swap2'], 'たまごを')

    def test_installed(self):
        import correction_entry as ce, inspect
        self.assertIn('stray_mark_guard', inspect.getsource(ce))


class RivalExitGuard(unittest.TestCase):
    """打ったかなを別の読みに替えた所に、同じくらい語で切れる別の直し方があれば紫（作り例）。"""

    def test_doubtful(self):
        import rival_exit_guard as G
        typed = 'となりのへおからたのしそうなこえがきこえる'
        m0 = G.MARGIN
        try:
            G.MARGIN = -500     # 差の小さい別の直し方は、線を緩めると迷いになる
            self.assertTrue(G.doubtful(typed, typed.replace('へお', 'ほお')))
        finally:
            G.MARGIN = m0
        # 既定の線（-3000）では、この程度の差では採った書き換えを戻さない
        self.assertEqual(G.doubtful(typed, typed.replace('へお', 'ほお')), [])
        typed = 'ふゆになるとなべりうょりをつくる'
        self.assertEqual(G.doubtful(typed, typed.replace('りうょり', 'りょうり')), [])
        # 1字の助詞どうしの違い（を と へ）は格子では決めない
        self.assertTrue(G._particle_swap('しゃしんを', 'しゃしんへ'))
        self.assertFalse(G._particle_swap('しゃしんを', 'しゃしんせ'))

    def test_guard(self):
        import rival_exit_guard as G
        typed = 'となりのへおからたのしそうなこえがきこえる'
        self.addCleanup(setattr, G, 'MARGIN', G.MARGIN)
        G.MARGIN = -500
        r = G.guard(typed, {'corrected': typed.replace('へお', 'ほお'), 'odd_spans': []})
        self.assertEqual(r['corrected'], typed)
        self.assertTrue(any(a <= 4 < b for a, b in r['odd_spans']))
        with _Env(CN_RIVAL_EXIT_GUARD='0'):
            r = G.guard(typed, {'corrected': typed.replace('へお', 'ほお'), 'odd_spans': []})
            self.assertNotEqual(r['corrected'], typed)

    def test_kanji_reading_misread(self):
        # 答えの 誤 を解析が あやま と読んでも、打った ご は 誤 の字の読みなので書き換えと見ない（作り例）
        import rival_exit_guard as G
        toks = [(0, 3, '誤'), (3, 8, '変換')]
        self.assertTrue(G._misread('ごへんかん', 0, 1, 0, 3, toks))
        self.assertFalse(G._misread('がへんかん', 0, 1, 0, 3, toks))
        with _Env(CN_RIVAL_KANJI_READING='0'):
            self.assertFalse(G._misread('ごへんかん', 0, 1, 0, 3, toks))

    def test_installed(self):
        import correction_entry as ce, inspect
        self.assertIn('rival_exit_guard', inspect.getsource(ce))


class DanglingQuoted(unittest.TestCase):
    """括弧の中がその語だけの音便形（「いっ」）は字を足さない（作り例）。"""

    def test_quoted(self):
        import dangling_verb as D
        self.assertEqual(D.dangling('画面に「待っ」と出た。'), [])
        self.assertTrue(D.dangling('画面に待っと出た。'))
        with _Env(CN_DANGLING_QUOTED='0'):
            self.assertTrue(D.dangling('画面に「待っ」と出た。'))

class KeyslipWordCompound(unittest.TestCase):
    """隣のキーの紫は、辞書の語でできた複合語（2字以上の語を挟む）には足さない。1字の漢字が続く所は今まで通り（作り例）。"""

    def test_word_compound(self):
        import keyslip_window as K
        self.assertTrue(K._word_compound('黒背景色の', 0, 4))
        self.assertFalse(K._word_compound('寺木升が', 0, 3))
        with _Env(CN_KEYSLIP_WORD_COMPOUND='0'):
            self.assertFalse(K._word_compound('黒背景色の', 0, 4))


class NounCompoundPurple(unittest.TestCase):
    """辞書の2字以上の名詞2つの継ぎ目の「続けて置けない」の紫は外す。1字の漢字の切れ端は外さない（作り例）。"""

    def test_filter(self):
        import noun_compound_purple as N
        r = {'corrected': '東京電力株式会社の', 'odd_spans': [(0, 8)],
             'odd_reasons': [(0, 8, '「東京電力」と「株式会社」は続けて置けない')]}
        self.assertEqual(N.filter_result('東京電力株式会社の', r)['odd_spans'], [])
        r = {'corrected': '寺木升が', 'odd_spans': [(0, 2)], 'odd_reasons': [(0, 2, '「寺」と「木」は続けて置けない')]}
        self.assertEqual(N.filter_result('寺木升が', r)['odd_spans'], [(0, 2)])
        r = {'corrected': '東京電力株式会社の', 'odd_spans': [(0, 8)],
             'odd_reasons': [(0, 8, '「東京電力」と「株式会社」は続けて置けない'), (0, 8, '前後の語とのつながりが辞書で確かめられません')]}
        self.assertEqual(N.filter_result('東京電力株式会社の', r)['odd_spans'], [(0, 8)])
        with _Env(CN_NOUN_COMPOUND_PURPLE='0'):
            r = {'corrected': '東京電力株式会社の', 'odd_spans': [(0, 8)],
                 'odd_reasons': [(0, 8, '「東京電力」と「株式会社」は続けて置けない')]}
            self.assertEqual(N.filter_result('東京電力株式会社の', r)['odd_spans'], [(0, 8)])

    def test_object_drop(self):
        # を を省いた話し言葉（本棚し・作り例）の名詞＋動詞は外す。動詞の形が後ろへつながらない打ち違いの跡は残す
        import noun_compound_purple as N
        r = {'corrected': '宿題しないでよ', 'odd_spans': [(0, 3)], 'odd_reasons': [(0, 3, '「宿題」と「し」は続けて置けない')]}
        self.assertEqual(N.filter_result('宿題しないでよ', r)['odd_spans'], [])
        r = {'corrected': '机の手せ価格を', 'odd_spans': [(2, 4)], 'odd_reasons': [(2, 4, '「手」と「せ」は続けて置けない')]}
        self.assertEqual(N.filter_result('机の手せ価格を', r)['odd_spans'], [(2, 4)])
        with _Env(CN_NOUN_VERB_PURPLE='0'):
            r = {'corrected': '宿題しないでよ', 'odd_spans': [(0, 3)], 'odd_reasons': [(0, 3, '「宿題」と「し」は続けて置けない')]}
            self.assertEqual(N.filter_result('宿題しないでよ', r)['odd_spans'], [(0, 3)])

    def test_installed(self):
        import correction_entry as ce, inspect
        self.assertIn('noun_compound_purple', inspect.getsource(ce))



class StaleWordPurple(unittest.TestCase):
    """「X」はあまり使わない語です の紫は、答えで X が長い語の一部になったら外す（作り例）。"""

    def test_filter(self):
        import stale_word_purple as W
        r = {'corrected': '画面の上', 'odd_spans': [(2, 3)],
             'odd_reasons': [(2, 3, '「面」はあまり使わない語です。同じ読みか1打違いの読みで変換し直すと、より自然な文になります')]}
        self.assertEqual(W.filter_result('が゛面の上', r)['odd_spans'], [])
        # 答えが打った行のままなら外さない
        r = {'corrected': '尾の上', 'odd_spans': [(0, 1)],
             'odd_reasons': [(0, 1, '「尾」はあまり使わない語です。同じ読みか1打違いの読みで変換し直すと、より自然な文になります')]}
        self.assertEqual(W.filter_result('尾の上', r)['odd_spans'], [(0, 1)])
        with _Env(CN_STALE_WORD_PURPLE='0'):
            r = {'corrected': '画面の上', 'odd_spans': [(2, 3)],
                 'odd_reasons': [(2, 3, '「面」はあまり使わない語です。同じ読みか1打違いの読みで変換し直すと、より自然な文になります')]}
            self.assertEqual(W.filter_result('が゛面の上', r)['odd_spans'], [(2, 3)])


class KanaKeepWordSpan(unittest.TestCase):
    """一覧の語を解析が1語に切れない時も、語の切れ目どうしに当たる所の弱い紫を外す（作った語 わっほー）"""

    def setUp(self):
        import tempfile, kana_keep_list
        self.tmp = tempfile.TemporaryDirectory()
        kana_keep_list.set_user_dir(self.tmp.name)
        kana_keep_list.add_word('わっほー')

    def tearDown(self):
        import kana_keep_list
        kana_keep_list.set_user_dir(None)
        self.tmp.cleanup()

    def _res(self, why):
        return {'corrected': 'わっほーと言った', 'odd_spans': [(0, 3)], 'odd_reasons': [(0, 3, why)]}

    def test_weak_dropped(self):
        import kana_keep_list as K
        line = 'わっほーと言った'
        self.assertEqual(K.drop_weak(line, self._res('「わっ」と「ほ」は続けて置けない'))['odd_spans'], [])
        self.assertEqual(K.drop_weak(line, self._res('「わ」は直すと文の形に説明が付かない'))['odd_spans'], [])

    def test_strong_kept_and_switch(self):
        import kana_keep_list as K
        line = 'わっほーと言った'
        self.assertEqual(K.drop_weak(line, self._res('「わ」は隣のキーを打ったかもしれません'))['odd_spans'], [(0, 3)])
        with mock.patch.dict(os.environ, {'CN_KANA_KEEP_WORD_SPAN': '0'}):
            self.assertEqual(K.drop_weak(line, self._res('「わっ」と「ほ」は続けて置けない'))['odd_spans'], [(0, 3)])

    def test_not_from_mid_word(self):
        import kana_keep_list as K
        # 語の途中から始まる並び（っほー）は一覧の語として見ない
        K.add_word('っほー')
        line = 'わっほーと言った'
        r = {'corrected': line, 'odd_spans': [(1, 3)], 'odd_reasons': [(1, 3, '「わっ」と「ほ」は続けて置けない')]}
        K.remove_word('わっほー')
        self.assertEqual(K.drop_weak(line, r)['odd_spans'], [(1, 3)])


class HalfwidthDictWords(unittest.TestCase):
    """半角のまま打った所を戻したかなが、語彙に無い身近な語で全部読める時は読めるとする（作った例）"""

    def test_common_word(self):
        import halfwidth as H
        self.assertEqual(H._common_dictionary_face('かいぎ'), '会議')
        self.assertIsNone(H._common_dictionary_face('くいり'))
        with mock.patch.dict(os.environ, {'CN_HALFWIDTH_DICT_WORDS': '0'}):
            self.assertIsNone(H._common_dictionary_face('かいぎ'))

    def test_needs_full_cover(self):
        import halfwidth as H

        class Empty:
            def lookup(self, s):
                return []
        self.assertTrue(H.makes_sense_as_japanese('ていあんする', Empty(), dict_words=True))
        self.assertFalse(H.makes_sense_as_japanese('ていあんする', Empty()))
        # 一部だけ語に当たる並びは通さない
        self.assertFalse(H.makes_sense_as_japanese('くいていあんり', Empty(), dict_words=True))


class KataOneKnown(unittest.TestCase):
    """表の1語の中の片仮名1字は、混じった片仮名の紫にしない（作った例: 写メを送る）"""

    def test_switch(self):
        import broken_shape as BS
        self.assertEqual(BS.spans('写メを送る'), [])
        with _Env(CN_KATA_ONE_KNOWN='0'):
            self.assertEqual([x[:2] for x in BS.spans('写メを送る')], [(1, 2)])


class ProperPairNation(unittest.TestCase):
    """1字の固有名詞2つの並びは、国の略称どうしか辞書の1語の時だけ実在の並びとして守る"""

    def test_pairs(self):
        import kanji_guess as G
        self.assertTrue(G._proper_pair_ok([('日', '名詞:固有名詞:地域:国'), ('中', '名詞:固有名詞:地域:国')], 0))
        self.assertTrue(G._proper_pair_ok([('米', '名詞:固有名詞:地域:国'), ('英', '名詞:固有名詞:地域:国')], 0))
        with _Env(CN_REAL_WORD_PAIR_NATION='0'):
            self.assertTrue(G._proper_pair_ok([('集', 'x'), ('亜', 'y')], 0))


class OddReasonDecimal(unittest.TestCase):
    """名詞と数だけの行の小数（4.5）は数の一部として見る（作った例）"""

    def test_label_line(self):
        import odd_reason_fill as O
        self.assertTrue(O._label_line(list(tokenize('身長中3.5'))))
        with _Env(CN_ODD_REASON_DECIMAL='0'):
            self.assertFalse(O._label_line(list(tokenize('身長中3.5'))))


class NounCount(unittest.TestCase):
    """辞書の名詞＋数の語の並びは数え方（作った例: 林檎二つ）"""

    def test_noun_count(self):
        import odd_reason_fill as O
        t = list(tokenize('林檎二つの箱'))
        self.assertTrue(O._noun_count(t, 0, 4))
        t = list(tokenize('林檎がある'))
        self.assertFalse(O._noun_count(t, 0, 3))


class BadJoinTsutsu(unittest.TestCase):
    """つつ は連用形に付く: 形容詞の言い切り＋つつ を作る直しは採らない（作った例）"""

    def test_bad_join(self):
        import odd_respell as R
        self.assertTrue(R._bad_join('赤五つ', '赤いつつ'))
        self.assertFalse(R._bad_join('書きつづ', '書きつつ'))
        with _Env(CN_BAD_JOIN_TSUTSU='0'):
            self.assertFalse(R._bad_join('赤五つ', '赤いつつ'))


class LoneJoinOkuri(unittest.TestCase):
    """前の漢字1字と送り仮名をつないで表の1語になる1字は浮いた字ではない（作った例）"""

    def test_okuri(self):
        import broken_shape as BS
        self.assertEqual(BS.spans('規則違反と見做して扱う'), [])
        with _Env(CN_BROKEN_LONE_JOIN_OKURI='0'):
            self.assertNotEqual(BS.spans('規則違反と見做して扱う'), [])


class StretchPair(unittest.TestCase):
    """伸ばす音で解析が切り違えた「続けて置けない」の紫（作った例: 班分けしよー）"""

    def test_stretch(self):
        import odd_reason_fill as O
        self.assertEqual(O._unstretch('班分けしよー'), '班分けしよう')
        self.assertIsNone(O._unstretch('班分けしよう'))
        tx = ['「分け」と「し」は続けて置けない']
        self.assertTrue(O._stretch_pair('班分けしよー', 1, 4, tx))
        self.assertFalse(O._stretch_pair('班分けしよう', 1, 4, tx))


class UnitSuffix(unittest.TestCase):
    """表の1語に続く接尾の漢字だけの紫（作った例。表の語は差し替え）"""

    def test_unit_suffix(self):
        import odd_reason_fill as O
        import seed_japanese
        t = list(tokenize('ガン科医に頼む'))
        with mock.patch.object(seed_japanese, 'is_unit', lambda w: True if w == 'ガン科' else False):
            self.assertTrue(O._unit_suffix(t, 2, 4))
        with mock.patch.object(seed_japanese, 'is_unit', lambda w: False):
            self.assertFalse(O._unit_suffix(t, 2, 4))


class MasuQuote(unittest.TestCase):
    """〜ますの「…」は言い方を名前に挙げる書き方（作った例）"""

    def test_masu_quote(self):
        import pos_seq_odd as P
        self.assertEqual(P.spots('書きますの「す」は、'), [])
        self.assertNotEqual(P.spots('書きますの。'), [])
        with _Env(CN_POS_SEQ_MASU_QUOTE='0'):
            self.assertNotEqual(P.spots('書きますの「す」は、'), [])


class WaQuote(unittest.TestCase):
    """は＋引用の と＋思う・言う・なる は、言いかけの文を引いた形（作った例）"""

    def test_wa_quote(self):
        import odd_reason_fill as O
        t = list(tokenize('それは何だこれはと思った。'))
        self.assertTrue(O._wa_quote(t, 7, 9))
        t = list(tokenize('これはと走った。'))
        self.assertFalse(O._wa_quote(t, 2, 4))


class KanaKeepTypedInside(unittest.TestCase):
    """一覧の語の中の字だけを書き換えた直しは打った語へ戻す（作った語 ほげふが）"""

    def test_back(self):
        import kana_keep_list as K
        with mock.patch.object(K, 'words', lambda: ['ほげふが']):
            r = {'corrected': 'あとほげ不可', 'odd_spans': [(3, 6)], 'odd_reasons': [(3, 6, 'x')]}
            got = K.keep_typed_inside('あとほげふが', r)
            self.assertEqual(got['corrected'], 'あとほげふが')
            self.assertEqual(got['odd_spans'], [(3, 6)])
            # 語の外へはみ出す直しは触らない
            r = {'corrected': 'あ問ほげ不可', 'odd_spans': []}
            self.assertEqual(K.keep_typed_inside('あとほげふが', r)['corrected'], 'あ問ほげ不可')
            with _Env(CN_KANA_KEEP_TYPED_INSIDE='0'):
                r = {'corrected': 'あとほげ不可', 'odd_spans': []}
                self.assertEqual(K.keep_typed_inside('あとほげふが', r)['corrected'], 'あとほげ不可')


class KanaListRun(unittest.TestCase):
    """一覧の語を含む読めないかなの語は、並びが語に切り分けられれば紫にしない（作った語 ぬるぴよ）"""

    def test_run(self):
        import odd_reason_fill as O
        import kana_keep_list as K
        line = 'すすぎとぬるぴよは水で'
        toks = list(tokenize(line))
        bad = [t for t in toks if not getattr(t, 'has_reading', True)]
        self.assertTrue(bad)
        with mock.patch.object(K, 'words', lambda: ['ぬるぴよ']):
            self.assertTrue(O._kana_list_run(line, toks, bad[0].start, bad[0].end))
        with mock.patch.object(K, 'words', lambda: []):
            self.assertFalse(O._kana_list_run(line, toks, bad[0].start, bad[0].end))


class DakutenShiftReasons(unittest.TestCase):
    """濁点の付け違いを直した所の紫の理由も外し、残りは直した後の位置へ（作った例）"""

    def test_reasons(self):
        import dakuten_shift as D
        r = {'corrected': 'これはだたしい答えです', 'odd_spans': [[3, 7]],
             'odd_reasons': [[3, 7, 'x'], [8, 10, 'y']]}
        got = D.repair_line('これはだたしい答えです', r)
        self.assertEqual(got['corrected'], 'これは正しい答えです')
        self.assertEqual(got['odd_spans'], [])
        self.assertEqual([x[2] for x in got['odd_reasons']], ['y'])


class ParticleInsertRival(unittest.TestCase):
    """助詞を1字足しただけの直しと、隣のキーの打ち違いで届く身近な語を比べる（作った例）"""

    def test_parts(self):
        import particle_insert_rival as P
        self.assertEqual(P._inserted('静か歩く', '静かに歩く'), 2)
        self.assertIsNone(P._inserted('静か歩く', '静か歩く'))
        self.assertEqual(P._chunk('酢木任して', 2), (0, 3))
        self.assertIn('すき', P._variants('かく'))

    def test_fix(self):
        import particle_insert_rival as P
        import kanji_guess

        class Store:
            def lookup(self, r):
                return [{'surface': '確認', 'solid': True, 'count': 5}] if r == 'かくにん' else []
        r = {'corrected': '酢木に任して', 'details': [['', 'に', 'かな入力']]}
        with mock.patch.object(kanji_guess, 'reading_combos', lambda *a, **k: ['すきにん']):
            got = P.fix('酢木任して', r, Store())
            self.assertEqual(got['corrected'], '確認して')
            with _Env(CN_PARTICLE_INSERT_RIVAL='0'):
                self.assertEqual(P.fix('酢木任して', r, Store())['corrected'], '酢木に任して')

        class Empty:
            def lookup(self, r):
                return []
        with mock.patch.object(kanji_guess, 'reading_combos', lambda *a, **k: ['すきにん']):
            self.assertEqual(P.fix('酢木任して', r, Empty())['corrected'], '酢木に任して')


class KanaRunProbe(unittest.TestCase):
    """文の中の、短い語の切れ端にしか読めないかなの並びを、並びだけで補正に通して比べる（作った例）"""

    def test_spots(self):
        import kana_run_probe as K
        self.assertEqual(K.spots('めいでかいを押す'), [(0, 5)])
        self.assertEqual(K.spots('これはいすの代わりです'), [])
        self.assertEqual(K.spots('きのうはいかをたべた'), [])

    def test_probe(self):
        import kana_run_probe as K
        r = {'corrected': 'めいでかいを押す', 'odd_spans': []}
        call = lambda t: {'corrected': '名大会' if t == 'めいでかい' else t, 'odd_spans': []}
        got = K.probe('めいでかいを押す', r, call)
        self.assertEqual(got['corrected'], '名大会を押す')
        self.assertEqual(K.probe('めいでかいを押す', r, lambda t: {'corrected': t, 'odd_spans': []})['corrected'],
                         'めいでかいを押す')
        with _Env(CN_KANA_RUN_PROBE='0'):
            self.assertEqual(K.probe('めいでかいを押す', r, call)['corrected'], 'めいでかいを押す')

    def test_probe_keeps_far_purple(self):
        import kana_run_probe as K
        r = {'corrected': 'めいでかいを押すと元の文', 'odd_spans': [[10, 12]], 'odd_reasons': [[10, 12, 'x']]}
        call = lambda t: {'corrected': '名大会' if t == 'めいでかい' else t, 'odd_spans': []}
        got = K.probe('めいでかいを押すと元の文', r, call)
        self.assertEqual((got['corrected'], got['odd_spans']), ('名大会を押すと元の文', [[8, 10]]))
        # 並びに掛かる紫が在れば見ない
        r = {'corrected': 'めいでかいを押す', 'odd_spans': [[0, 2]]}
        self.assertEqual(K.probe('めいでかいを押す', r, call)['corrected'], 'めいでかいを押す')

    def test_remark_after_fix(self):
        import kana_run_probe as K
        import fixed_still_odd as F
        line = 'めいでかいを括弧から外して単体で行に置くと、正しく補正される。なぜ元の文だと補正されない？'
        r = {'corrected': line, 'odd_spans': [[33, 36]], 'odd_reasons': [[33, 36, F.REASON]]}
        call = lambda t: {'corrected': '名大会' if t == 'めいでかい' else t, 'odd_spans': []}
        self.assertEqual(K.probe(line, r, call)['odd_spans'], [])
        with _Env(CN_KANA_RUN_PROBE_REMARK='0'):
            self.assertEqual(K.probe(line, r, call)['odd_spans'], [[31, 34]])

    def test_stale_reason_dropped(self):
        import kana_run_probe as K
        import fixed_still_odd as F
        r = {'corrected': 'めいでかいを押すと元の文', 'odd_spans': [[10, 12]], 'odd_reasons': [[10, 12, F.REASON]]}
        call = lambda t: {'corrected': t, 'odd_spans': []}
        # 既定オフ（本当の打ち違いの所の紫も同じ理由で付くため）
        self.assertEqual(K.probe('めいでかいを押すと元の文', r, call)['odd_spans'], [[10, 12]])
        with _Env(CN_KANA_RUN_PROBE_STALE='1'):
            self.assertEqual(K.probe('めいでかいを押すと元の文', r, call)['odd_spans'], [])


class MazegakiFragment(unittest.TestCase):
    def test_mazegaki_kept(self):
        import ime_class_mark as M
        self.assertTrue(M._mazegaki('破たんした', 1, 3))
        self.assertTrue(M._mazegaki('補てんする', 1, 3))
        self.assertFalse(M._mazegaki('手フを置く', 1, 2))
        self.assertFalse(M._mazegaki('写メを送る', 1, 2))
        with _Env(CN_IME_CLASS_MAZEGAKI='0'):
            self.assertFalse(M._mazegaki('破たんした', 1, 3))


class MeasureKeep(unittest.TestCase):
    def test_family_swap_reverted(self):
        import measure_keep as K
        line = '秒数を量って書く'
        r = {'corrected': '秒数を計って書く', 'changed': True, 'details': [['量', '計', 'かな入力']],
             'odd_spans': [], 'odd_reasons': [[3, 5, 'x']]}
        got = K.keep(line, r)
        self.assertEqual((got['corrected'], got['odd_reasons']), (line, []))
        # 族の外の字からの直しは残す
        r2 = {'corrected': '改善を図る', 'details': [['測', '図', 'かな入力']]}
        self.assertEqual(K.keep('改善を測る', r2)['corrected'], '改善を図る')
        with _Env(CN_MEASURE_KEEP='0'):
            self.assertEqual(K.keep(line, r)['corrected'], '秒数を計って書く')

    def test_fso_purple_dropped_on_revert(self):
        import measure_keep as K
        import fixed_still_odd as F
        line = '入口に通し直して秒数を量って書く'
        r = {'corrected': '入口に通し直して秒数を計って書く', 'details': [['量', '計', 'かな入力']],
             'odd_spans': [[3, 6]], 'odd_reasons': [[3, 6, F.REASON]]}
        got = K.keep(line, r)
        self.assertEqual((got['corrected'], got['odd_spans']), (line, []))


class EatsParticle(unittest.TestCase):
    def test_respell_eating_particle(self):
        import fixed_still_odd as F
        det = [['をっ', 'よん', F.RESPELL[0]]]
        self.assertTrue(F._eats_particle('設定をっ変更する。', '設定よん変更する。', det))
        self.assertFalse(F._eats_particle('設定をっ変更する。', '設定を変更する。', det))
        with _Env(CN_FSO_EATS_PARTICLE='0'):
            self.assertFalse(F._eats_particle('設定をっ変更する。', '設定よん変更する。', det))


if __name__ == '__main__':
    unittest.main()
