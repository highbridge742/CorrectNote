# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
**候補欄に出す説明**（項目48-MD・うにさんの指定・2026-08-31）。

    「メニューに『補正候補に品詞の判定を表示する』を追加し、
      デフォルトオフ。オンにすると、候補欄の一番下に
      『－ 品詞判定 －』の項目が増え、選択範囲の単語が何の品詞に
      判定されたか（名詞や動詞など。活用変化しているものはその形で
      書く。イ形容詞やナ形容詞など）を書く。」

    「メニューのさらにそのひとつ下に『補正候補に根拠を表示する』を
      追加し、デフォルトオフ。『－ 品詞判定 －』の下に
      『－ 補正根拠 －』を増やし、3行の内容を入れる。」

    「上2件は、**なかなか進まない開発を分析するために役立てる**ので、
      優先して取り組みます。」

**ここは画面に出す言葉を作るだけ。補正の答えには一切触らない。**
`corrector` からも `candidates` からも呼ばない——呼ぶのは `app.py`
の候補一覧の組み立てだけ。だから janome の有無で言葉が変わっても
補正の数字は動かない（`ENGINE_STAMP` を上げる必要がない）。

**なぜ「根拠」を後から測り直すのか**
--------------------------------------
`correct_line` は 3,225行の1関数で、置き換えを積む場所が **46か所**
ある。そこ全部に「どの手で直したか」を持たせて回すのは、補正の道
そのものを触ることになる（学び22——片方だけに置くと、そちらを
迂回して素通りする）。**画面に出すだけの説明のために、補正の道を
46か所触るのは割に合わない。**

代わりに、**打った文字と直した文字の対**（`details` が既に持って
いる）から**観測できる形**を言葉にする。「隣接キーへ補正」と書く
のは、実際に**隣のキーで説明が付く**ときだけ——エンジンが内部で
何を考えたかの申告ではなく、**結果として何が起きたか**の記述で
ある。読み違えないよう、決められないときは黙って落とす
（「補正の形を言い当てられません」と書く）。

**違和感の正体**（1行目）は逆に、**判定そのものをもう一度回す**
（`pos_grammar.odd_kana_spans` と `oddness.is_odd_run`）。紫を
立てているのと同じ道具なので、ここは申告ではなく本物。
"""

import difflib

# ------------------------------------------------------------
# 品詞の言葉（うにさんの挙げた呼び方に合わせる）
# ------------------------------------------------------------
#
#   「名詞、代名詞、副詞、連体詞、接続詞、感動詞、助詞は
#     文の形が変わりません」（2026-08-29）
#   「イ形容詞やナ形容詞など」（2026-08-31）
#
# janome（IPAdic）の呼び方は「形容詞」＝イ形容詞、
# 「名詞,形容動詞語幹」＝ナ形容詞の語幹。**学校文法の名前のまま
# 出すと、うにさんの言う名前と食い違う**ので、ここで言い換える。

# 大分類そのままでよいもの
_MAJOR = {
    '名詞': '名詞',
    '動詞': '動詞',
    '副詞': '副詞',
    '連体詞': '連体詞',
    '接続詞': '接続詞',
    '感動詞': '感動詞',
    '助詞': '助詞',
    '助動詞': '助動詞',
    '接頭詞': '接頭辞',
    '記号': '記号',
    'フィラー': 'フィラー',
    'その他': 'その他',
}

# 名詞の細分類（先頭の1段だけ見る）
_NOUN_SUB = {
    '代名詞': '代名詞',
    '数': '数詞',
    'サ変接続': '名詞（サ変）',
    '形容動詞語幹': 'ナ形容詞の語幹',
    'ナイ形容詞語幹': 'イ形容詞の語幹',
    '副詞可能': '名詞（副詞にもなる）',
    '接尾': '接尾辞',
    '非自立': '名詞（非自立）',
    '動詞非自立的': '名詞（非自立）',
    '特殊': '名詞（特殊）',
    '接続詞的': '名詞（接続詞的）',
    '引用文字列': '名詞（引用）',
}

# 固有名詞の下の段（姓と名を分けて出す。項目48-JL で運んでいる）
_PROPER = {
    '人名': '人名',
    '組織': '組織名',
    '地域': '地名',
    '一般': '固有名詞',
}
_PROPER_3 = {'姓': '姓', '名': '名', '一般': '', '国': '国名'}

# 助詞の細分類
_PARTICLE_SUB = {
    '格助詞': '格助詞', '係助詞': '係助詞', '副助詞': '副助詞',
    '接続助詞': '接続助詞', '終助詞': '終助詞', '並立助詞': '並立助詞',
    '連体化': '連体化（の）', '副詞化': '副詞化',
    '副助詞／並立助詞／終助詞': '副助詞',
    '特殊': '特殊',
}

# 活用形（janome の名前 → うにさんに見せる名前）。
# **janome の名前をそのまま出さない**——「連用タ接続」「命令ｅ」の
# ような内部の呼び方は、読む人の役に立たない。
_INFL = {
    '基本形': '終止形',
    '音便基本形': '終止形（音便）',
    '未然形': '未然形',
    '未然ウ接続': '未然形（う接続）',
    '未然ヌ接続': '未然形（ぬ接続）',
    '未然レル接続': '未然形（れる接続）',
    '未然特殊': '未然形',
    '連用形': '連用形',
    '連用タ接続': '連用形（た接続）',
    '連用テ接続': '連用形（て接続）',
    '連用デ接続': '連用形（で接続）',
    '連用ゴザイ接続': '連用形（ございます接続）',
    '仮定形': '仮定形',
    '仮定縮約１': '仮定形（縮約）',
    '仮定縮約２': '仮定形（縮約）',
    '体言接続': '連体形',
    '体言接続特殊': '連体形',
    '体言接続特殊２': '連体形',
    '命令ｅ': '命令形',
    '命令ｉ': '命令形',
    '命令ｒｏ': '命令形',
    '命令ｙｏ': '命令形',
    'ガル接続': '語幹（がる接続）',
    '文語基本形': '終止形（文語）',
    '現代基本形': '終止形',
    'ダ列基本連体形': '連体形',
    'ダ列特殊連体形': '連体形',
}

# 品詞が立たなかったときの言葉
UNKNOWN_POS = '判定できません'


def _major_and_sub(pos):
    """
    `名詞:固有名詞:人名:姓` / `名詞` のどちらの形でも
    (大分類, [細分類…]) に割る。
    """
    if not pos:
        return '', []
    parts = [p for p in str(pos).replace(',', ':').split(':') if p and p != '*']
    if not parts:
        return '', []
    return parts[0], parts[1:]


def pos_name(pos, surface='', infl_form='', base_form='',
             has_reading=True):
    """
    形態素1つ分の品詞を、**うにさんの呼び方**で1行にする。

    pos: `名詞:固有名詞:人名:姓` の形（`corrector.make_tokenizer` が
         渡してくる形）でも `名詞` だけでもよい。
    infl_form: janome の活用形（`morphology.Token.infl_form`）。
         無ければ活用の話は書かない。
    """
    major, subs = _major_and_sub(pos)
    if not major:
        return UNKNOWN_POS

    sub1 = subs[0] if subs else ''
    label = _MAJOR.get(major, major)

    if major == '名詞':
        if sub1 == '固有名詞':
            kind = _PROPER.get(subs[1] if len(subs) > 1 else '', '固有名詞')
            deep = _PROPER_3.get(subs[2] if len(subs) > 2 else '', '')
            label = f'固有名詞（{kind}・{deep}）' if deep \
                else f'固有名詞（{kind}）' if kind != '固有名詞' else '固有名詞'
        else:
            label = _NOUN_SUB.get(sub1, '名詞')
    elif major == '形容詞':
        # **イ形容詞**（うにさんの呼び方）。janome は「形容詞」。
        label = 'イ形容詞'
    elif major == '動詞':
        if sub1 in ('非自立', '接尾'):
            label = '動詞（補助動詞）' if sub1 == '非自立' else '動詞（接尾）'
    elif major == '助詞':
        got = _PARTICLE_SUB.get(sub1)
        label = f'助詞（{got}）' if got else '助詞'
    elif major == '接頭詞':
        label = '接頭辞'

    # 活用している形は、その形で書く（うにさんの指定）。
    if infl_form:
        form = _INFL.get(infl_form, infl_form)
        if form:
            label = f'{label}・{form}'
    # 原形は、活用して形が変わっているときだけ添える
    # （`走っ` を見て `走る` だと分かるように）。
    if base_form and base_form != surface:
        label = f'{label}／原形 {base_form}'

    # **辞書に読みが無い語**は、そこが分析のいちばんの手がかり。
    # janome は知らない塊も「名詞,一般」と推測するので、
    # 推測だったことを必ず添える（48-JG の「大分類だけを頼ると
    # 本物の異様まで黙る」と同じ用心）。
    if not has_reading:
        label = f'{label}（辞書に無い語）'
    return label


# 同じ塊を何度も割り直さない（`_f2_peek` は左右の行き先を先読みする
# たびにここへ来る）。janome の分割は入力の文字列だけで決まるので、
# 控えても言葉は1文字も変わらない（項目48-BO と同じ理由）。
_TOK_CACHE = {}
_TOK_CACHE_LIMIT = 2000


def _tokens_for(text, tokenize_fn=None):
    """
    `text` を形態素に割る。

    janome があれば `morphology.tokenize`（**活用形まで取れる**）、
    無ければ呼び出し側の `tokenize_fn`（エンジンが見ているのと
    同じ割り方）。どちらも駄目なら []。

    戻り値: [(表記, 品詞, 活用形, 原形, 読みが取れたか), ...]
    """
    got = _TOK_CACHE.get(text)
    if got is not None:
        return got

    try:
        from morphology import tokenize as _mtok, HAS_JANOME
    except Exception:
        _mtok, HAS_JANOME = None, False

    if HAS_JANOME and _mtok is not None:
        try:
            out = []
            for t in _mtok(text):
                pos = t.pos
                sub = getattr(t, 'pos_sub', '')
                if sub:
                    pos = f'{pos}:{sub}'
                out.append((t.surface, pos,
                            getattr(t, 'infl_form', '') or '',
                            t.base_form or '', bool(t.has_reading)))
            # **複合辞は1語にして見せる**（項目48-NV・学び22）。
            # ここは `morphology.tokenize` を**直に呼んでいる**ので、
            # 補正の道（`corrector.make_tokenizer`）だけに繋ぎを
            # 掛けると、**画面の「－ 品詞判定 －」だけ と／は／いえ
            # のまま**になる。うにさんが問題を見つけたのは
            # まさにこの欄（2026-09-01）。
            # **表とどこを繋ぐかの判定は corrector に1本だけ**（48-GN）。
            # 活用形（3つ目）は**必ず空**——`命令ｅ` を残すと
            # `pos_name` が「接続詞・命令形」と出す。
            try:
                from corrector import (compound_ranges,
                                       COMPOUND_FUNCTION_WORDS as _CFW)
                for _a, _b, _w in reversed(
                        compound_ranges([t[0] for t in out])):
                    _part = out[_a:_b + 1]
                    out[_a:_b + 1] = [(_w, _CFW[_w], '', _w,
                                       all(bool(t[4]) for t in _part))]
            except Exception:
                pass
            if out:
                return _remember(text, out)
        except Exception:
            pass

    if tokenize_fn is not None:
        try:
            # 語彙の育ちで答えが変わる道（janome 無しの簡易分割は
            # `store.lookup` を見る）なので、**控えない**。
            return [(t[0], t[1] or '', '', '', bool(t[5]))
                    for t in tokenize_fn(text)]
        except Exception:
            pass
    return []


def _remember(text, tokens):
    if len(_TOK_CACHE) > _TOK_CACHE_LIMIT:
        _TOK_CACHE.clear()
    _TOK_CACHE[text] = tokens
    return tokens


def pos_lines(text, tokenize_fn=None):
    """
    **選んだ範囲の品詞**（「－ 品詞判定 －」の中身）を行の一覧で返す。

    語が2つ以上に割れたときは**1語ずつ1行**にする。**割れたこと
    自体が分析の材料**なので、代表の1つに丸めない
    （`にゅうりょくみす` が `に｜ゅうりょくみす` に割れているのは、
    紫が立たない理由そのもの）。1行にまとめないのは、候補一覧の
    幅がその1行の長さで決まるから（`_make_dropdown`）。
    """
    text = text or ''
    if not text.strip():
        return [UNKNOWN_POS]
    toks = _tokens_for(text, tokenize_fn)
    if not toks:
        return [UNKNOWN_POS]
    if len(toks) == 1:
        surface, pos, infl, base, has_reading = toks[0]
        return [pos_name(pos, surface, infl, base, has_reading)]
    return [f'{surface} ＝ {pos_name(pos, surface, infl, base, hr)}'
            for surface, pos, infl, base, hr in toks]


def pos_label(text, tokenize_fn=None):
    """`pos_lines` を1行に繋いだもの（検品と道具のため）。"""
    return '＋'.join(pos_lines(text, tokenize_fn))


# ============================================================
# 補正の根拠（「－ 補正根拠 －」の3行）
# ============================================================

# 1行目に出す「違和感の正体」。**判定をもう一度回して**書く。
NO_ODD_REASON = '異様だという判定は立っていない'

#: 初期語彙が付ける使用回数の上限（`seed_vocabulary.load_seed` は 2 を
#: 入れ、同じ語が種の表に2度出ていると 3 になる）。これ以下を
#: 「学習した」と書かない（項目48-MD）。
SEED_COUNT_MAX = 3


def odd_reason(text, line='', start=None, end=None, tokenize_fn=None,
               dict_index=None, store=None, recorded=None):
    """
    **なぜ異様だと見たのか**（「－ 補正根拠 －」の1行目）。

    `recorded` は、その行を直したときにエンジンが控えた理由
    （`correct_line` の戻り値の `odd_reasons`。項目48-MD）。
    **在るならそれが本物**——判定を立てた当人の言葉なので、
    ここで測り直さない（48-GN「同じ判定をもう一度書くと、
    いつか食い違う」）。**測り直すのは控えが無いときだけ**
    （古い解析の控えから戻した行・道具から直に呼んだとき）。

    測り直す側も、紫を立てているのと同じ道具を回す:

      ・`pos_grammar.odd_kana_spans` —— かなの連続が
        「語＋機能語＋活用」で説明できない（＝**品詞として
        識別できない**）
      ・`oddness.is_odd_run` —— その順ではくっつけない語の並び

    どちらも立たなければ、そう書く（**でっち上げない**）。
    """
    text = text or ''
    if not text:
        return NO_ODD_REASON

    # ① かなの連続の説明が付かない（項目48-KS）
    src = line if line else text
    if start is None or end is None:
        s0, e0 = 0, len(src)
        if line:
            p = line.find(text)
            if p >= 0:
                s0, e0 = p, p + len(text)
    else:
        s0, e0 = start, end

    # ⓪ エンジンが控えた理由（在れば、それが本物）
    if recorded:
        best = None
        for got in recorded:
            try:
                a, b, why = got[0], got[1], got[2]
            except Exception:
                continue
            if e0 <= a or s0 >= b:
                continue
            # いちばん狭い範囲の理由を採る（広い範囲の印は、
            # 隣の語まで巻き込んでいることがある）
            if best is None or (b - a) < best[0]:
                best = (b - a, why)
        if best is not None:
            return best[1]

    try:
        import pos_grammar as _pg
        for a, b in _pg.odd_kana_spans(src, dict_index, store):
            if not (e0 <= a or s0 >= b):
                return '品詞として識別できない（かなの並びに説明が付かない）'
    except Exception:
        pass

    # ② その順ではくっつけない語の並び（項目48-HO ほか）。
    # **行の上で測る**——塊だけを渡すと、`に｜有力` のように
    # 境目をまたぐ並びが見えない（判定は行を見て立っている）。
    if tokenize_fn is not None:
        try:
            import oddness as _odd
            for a, b, s1, e1 in _odd.is_odd_run(src, tokenize_fn,
                                                with_spans=True):
                if not (e0 <= s1 or s0 >= e1):
                    return f'「{a}」と「{b}」は続けて置けない'
            if src is not text:
                for pair in _odd.is_odd_run(text, tokenize_fn):
                    return f'「{pair[0]}」と「{pair[1]}」は続けて置けない'
        except Exception:
            pass

    # ③ 解析が読みを引けなかった（辞書に無い塊）
    toks = _tokens_for(text, tokenize_fn)
    dead = [t[0] for t in toks if not t[4] and t[0].strip()]
    if dead:
        return f'辞書に無い語がある（{"・".join(dead[:3])}）'

    return NO_ODD_REASON


# --- 打った文字と直した文字の差を、打鍵の型で言い当てる ---------

_ADJ_LABEL = '隣接キーへ補正'
_ROLL_LABEL = '隣接キーの巻き込みを補正'
_SWAP_LABEL = '文字の順序を補正'
_DROP_LABEL = '脱字を補正'
_DUP_LABEL = '重複した打鍵を補正'
_EXTRA_LABEL = '余分な文字を削って補正'
_SHIFT_LABEL = 'Shift の押し忘れ（小書き）を補正'
_MARK_LABEL = '濁点・半濁点を補正'
_VOWEL_LABEL = '母音の取り違えを補正'
_CONSONANT_LABEL = '子音の取り違えを補正'
_KANJI_LABEL = '漢字に変換'
_HOMO_LABEL = '同じ読みの別の語へ変換'
_REBUILD_LABEL = '読みから語を組み直して補正'
NO_HAND_REASON = '補正の形を言い当てられない'


def _is_kana(ch):
    return 'ぁ' <= ch <= 'ゖ' or ch == 'ー'


def _all_kana(s):
    return bool(s) and all(_is_kana(c) for c in s)


def _has_kanji(s):
    return any('一' <= c <= '鿿' for c in s or '')


def _adjacent(a, b, input_method):
    """その1文字の違いが、隣のキーで説明が付くか。"""
    try:
        from kana_layout import kana_key_distance
    except Exception:
        return False
    if input_method == 'romaji':
        try:
            from corrector import _KANA_TO_ROMAJI, _qwerty_adjacent
        except Exception:
            return False
        ra, rb = _KANA_TO_ROMAJI.get(a), _KANA_TO_ROMAJI.get(b)
        if ra and rb and len(ra) == len(rb):
            diff = [(x, y) for x, y in zip(ra, rb) if x != y]
            return len(diff) == 1 and _qwerty_adjacent(diff[0][0], diff[0][1])
        return False
    try:
        return kana_key_distance(a, b) <= 1.6
    except Exception:
        return False


def _romaji_drop(a, b):
    """ローマ字で打つと1打の押し忘れで説明が付くか（項目48-FY）。"""
    try:
        from corrector import _KANA_TO_ROMAJI
    except Exception:
        return False
    ra, rb = _KANA_TO_ROMAJI.get(a), _KANA_TO_ROMAJI.get(b)
    if not ra or not rb or abs(len(ra) - len(rb)) != 1:
        return False
    short, long_ = (ra, rb) if len(ra) < len(rb) else (rb, ra)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


def _small_pair(a, b):
    try:
        from kana_layout import SMALL_KANA_PAIR
    except Exception:
        return False
    return SMALL_KANA_PAIR.get(a) == b


def _mark_pair(a, b):
    try:
        from kana_layout import DAKUTEN_BASE
    except Exception:
        return False
    return a != b and DAKUTEN_BASE.get(a, a) == DAKUTEN_BASE.get(b, b)


def _phonetic_label(a, b):
    """
    同じ子音で母音だけ違う／同じ母音で子音だけ違う（`kana_layout` の
    `phonetic_candidates` が見ているのと同じ型）。

    `さいでいか ⇒ さいだいか` の で→だ は、ローマ字では
    `de`→`da`＝**母音の取り違え**。「1文字を置き換えた」より
    ずっと役に立つ言い方になる。
    """
    try:
        from corrector import _KANA_TO_ROMAJI
    except Exception:
        return None
    ra, rb = _KANA_TO_ROMAJI.get(a), _KANA_TO_ROMAJI.get(b)
    if not ra or not rb or ra == rb:
        return None
    if ra[-1] != rb[-1] and ra[:-1] == rb[:-1]:
        return _VOWEL_LABEL
    if ra[-1] == rb[-1] and ra[:-1] != rb[:-1]:
        return _CONSONANT_LABEL
    return None


def _one_char_label(a, b, input_method):
    """1文字の置き換え a→b を、打鍵の型の言葉にする。"""
    if _small_pair(a, b):
        return _SHIFT_LABEL
    if _mark_pair(a, b):
        return _MARK_LABEL
    if _adjacent(a, b, input_method):
        return _ADJ_LABEL
    if input_method == 'romaji' and _romaji_drop(a, b):
        return _DROP_LABEL
    return _phonetic_label(a, b)


def _dl_ops(a, b):
    """
    `a` を `b` にする**最小の手数**を、手の種類ごとに並べる。

    素の編集距離ではなく **入れ替え（となりどうしの2字が逆）を
    1手と数える**（Damerau）。うにさんの言う「文字の順序」は
    打鍵として1回の誤りなので、置き換え2回と数えると型が読めない
    （`そももそ ⇒ そもそも` が「脱字＋余分」に見えていた）。

    戻り値: [('sub', i, j) / ('ins', i, j) / ('del', i, j) /
             ('swap', i, j), ...]（`a` の左から順）
    """
    n, m = len(a), len(b)
    inf = 1 << 30
    d = [[inf] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            best = min(d[i - 1][j] + 1, d[i][j - 1] + 1,
                       d[i - 1][j - 1] + (0 if a[i - 1] == b[j - 1] else 1))
            if (i > 1 and j > 1 and a[i - 1] == b[j - 2]
                    and a[i - 2] == b[j - 1]):
                best = min(best, d[i - 2][j - 2] + 1)
            d[i][j] = best

    ops = []
    i, j = n, m
    while i > 0 or j > 0:
        if (i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]
                and d[i][j] == d[i - 2][j - 2] + 1):
            ops.append(('swap', i - 2, j - 2))
            i, j = i - 2, j - 2
            continue
        if i > 0 and j > 0 and a[i - 1] == b[j - 1]                 and d[i][j] == d[i - 1][j - 1]:
            i, j = i - 1, j - 1
            continue
        if i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + 1:
            ops.append(('sub', i - 1, j - 1))
            i, j = i - 1, j - 1
            continue
        if i > 0 and d[i][j] == d[i - 1][j] + 1:
            ops.append(('del', i - 1, j))
            i -= 1
            continue
        ops.append(('ins', i, j - 1))
        j -= 1
    ops.reverse()
    return ops


# 手が多すぎるときは、型を並べても読めない。数だけ言う。
MAX_HANDS = 3
_MANY_LABEL = '読みを組み直して補正'
_OTHER_LABEL = '1文字を置き換えて補正'


def hand_labels(typed, fixed, input_method='kana'):
    """
    **打った並びと直した並びの差**を、打鍵の型の言葉の一覧にする。

    両方とも「読み」（かなの並び）で渡すこと。表記のまま渡すと
    漢字の分だけ差が膨らんで、型が読めなくなる。

    戻り値: ['隣接キーへ補正', '脱字を補正', ...]（順は出た順・重複無し）
    """
    typed, fixed = typed or '', fixed or ''
    if not typed or not fixed or typed == fixed:
        return []
    ops = _dl_ops(typed, fixed)
    if not ops:
        return []
    if len(ops) > MAX_HANDS:
        return [f'{_MANY_LABEL}（{len(ops)}か所）']

    out = []

    def push(label):
        if label and label not in out:
            out.append(label)

    for kind, i, j in ops:
        if kind == 'swap':
            push(_SWAP_LABEL)
        elif kind == 'sub':
            push(_one_char_label(typed[i], fixed[j], input_method)
                 or _OTHER_LABEL)
        elif kind == 'del':
            ch = typed[i]
            before = typed[i - 1] if i > 0 else ''
            after = typed[i + 1] if i + 1 < len(typed) else ''
            if ch == before or ch == after:
                push(_DUP_LABEL)
            elif ((before and _adjacent(ch, before, input_method))
                    or (after and _adjacent(ch, after, input_method))):
                push(_ROLL_LABEL)
            else:
                push(_EXTRA_LABEL)
        else:
            push(_DROP_LABEL)
    return out


def _reading_of(text, store=None, tokenize_fn=None, dict_index=None,
                target=''):
    """
    その表記の読みを取る（言い当てるための材料。**当たらなくてよい**）。

    ① かなだけならそのまま
    ② 語彙が読みを知っていれば、それ
    ③ 解析の読みを繋いだもの
    ④ `target`（もう片方の読み）が渡っていれば、漢字の読みの
       組み合わせのうち **target にいちばん近いもの**。
       `貸す九人`（解析は かすきゅうにん）を かすくにん と読んで
       いた、という**エンジン側の見立て**を拾うため。
    """
    text = text or ''
    if not text:
        return ''
    if _all_kana(text):
        return text

    got = ''
    if store is not None:
        try:
            got = store.reading_of(text) or ''
        except Exception:
            got = ''
    if not got and tokenize_fn is not None:
        try:
            parts = [t[2] or '' for t in tokenize_fn(text)]
            if all(parts):
                got = ''.join(parts)
        except Exception:
            got = ''

    if target and _has_kanji(text):
        best, best_d = got, (_distance(got, target) if got else 1 << 30)
        try:
            import kanji_guess as _kg
            for reading, _rank in _kg.reading_combos_with_rank(
                    text, dict_index, max_combos=200)[:200]:
                d = _distance(reading, target)
                if d < best_d:
                    best, best_d = reading, d
        except Exception:
            pass
        if best:
            return best
    return got


def _distance(a, b):
    """素の編集距離（読みの近さを較べるだけ）。"""
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def hand_reason(typed, fixed, input_method='kana', store=None,
                tokenize_fn=None, dict_index=None):
    """
    **何をして直したのか**（「－ 補正根拠 －」の2行目）。

    打った文字と直した文字を**読みに開いてから**較べる
    （CLAUDE.md ★★ の②「平仮名に開く」と同じ順）。
    """
    typed, fixed = typed or '', fixed or ''
    if not typed or not fixed or typed == fixed:
        return NO_HAND_REASON

    r_fixed = _reading_of(fixed, store, tokenize_fn, dict_index)
    r_typed = _reading_of(typed, store, tokenize_fn, dict_index,
                          target=r_fixed)

    labels = []
    if r_typed and r_fixed:
        if r_typed == r_fixed:
            # 読みは同じ＝打鍵ではなく変換の選び方の話
            if _all_kana(typed) and _has_kanji(fixed):
                return _KANJI_LABEL
            return _HOMO_LABEL
        labels = hand_labels(r_typed, r_fixed, input_method)
    if not labels and _all_kana(typed) and _all_kana(fixed):
        labels = hand_labels(typed, fixed, input_method)

    if not labels:
        if _all_kana(typed) and _has_kanji(fixed):
            return _REBUILD_LABEL
        return NO_HAND_REASON
    return '＋'.join(labels)


def learn_reason(typed, fixed, unit=None, choices=None, store=None):
    """
    **学習履歴が効いたか**（「－ 補正根拠 －」の3行目）。

    効いていなければ **None**（呼び出し側はこの行を出さない）。

      ・「補正の判断」の選び直し（`choices`）で決まった
        → 「学習による選び直し」（うにさんの指定の言葉のまま）
      ・直し先が**本人が実際に使った語**
        → 何回使った語かを添える（これも学習履歴）

    **実績の敷居は 4 回**（項目48-MD）。初期語彙は投入の時点で
    **count=2**、同じ語が種の表に2度出ていると 3 になる（実測:
    初期状態の分布は 1:16,689 / 2:284 / 3:117 で、**3 が上限**）。
    3 以下を「学習した」と書くと、**まだ何も学習していない初期状態で
    この行が出てしまう**——うにさんの問い「学習履歴が影響したか」に
    嘘を返すことになる。4 以上なら、本人が少なくとも1回は使っている。
    """
    typed, fixed = typed or '', fixed or ''

    # ① 選び直しの記憶
    if choices is not None and typed:
        prev = next_ = ''
        if isinstance(unit, dict):
            prev, next_ = unit.get('prev') or '', unit.get('next') or ''
        for base in (typed, (unit or {}).get('base') if isinstance(unit, dict)
                     else None):
            if not base:
                continue
            try:
                got = choices.lookup(base, prev, next_)
            except Exception:
                got = None
            if got and got == fixed:
                return '学習による選び直し'
        if isinstance(unit, dict) and unit.get('kind') in ('chosen',
                                                           'chosen_hint'):
            return '学習による選び直し'

    # ② 直し先が本人の使った語（初期語彙の上限 3 より上）
    if store is not None and fixed:
        try:
            from morphology import katakana_to_hiragana as _k2h
            reading = store.reading_of(fixed) or ''
            best = 0
            for e in store.lookup(_k2h(reading)) if reading else []:
                if e.get('surface') == fixed:
                    best = max(best, int(e.get('count', 0) or 0))
            if best >= SEED_COUNT_MAX + 1:
                return f'学習した語彙が効いた（「{fixed}」・{best}回）'
        except Exception:
            pass
    return None


def reason_lines(typed, fixed, unit=None, line='', start=None, end=None,
                 input_method='kana', tokenize_fn=None, store=None,
                 dict_index=None, choices=None, recorded=None):
    """
    「－ 補正根拠 －」に並べる**3行**（学習が効いていなければ2行）。

        上   なぜ異様だと見たのか
        中   何をして直したのか
        下   学習履歴が効いたか（効いていなければ**この行は出さない**）
    """
    changed = bool(fixed and typed and fixed != typed)
    why = odd_reason(typed, line, start, end, tokenize_fn,
                     dict_index, store, recorded)
    if changed and why == NO_ODD_REASON:
        # **直したのに、異様だという判定は立っていない。**
        # ここを黙って「判定なし」で済ませると、うにさんの言う
        # 「補正が動くのは異様な文字列だけ」を満たしていない箇所が
        # 見えなくなる。**分析のための窓なので、はっきり書く。**
        why = '異様だという判定は立っていない（補正は別の道から届いた）'
    out = [why]
    if changed:
        out.append(hand_reason(typed, fixed, input_method, store,
                               tokenize_fn, dict_index))
    else:
        out.append('補正はしていない（印だけ）')
    got = learn_reason(typed, fixed, unit, choices, store)
    if got:
        out.append(got)
    return out
