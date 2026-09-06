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
    # **`ナイ形容詞語幹` は「ない と続く名詞」**（項目48-QD・2026-09-04）。
    # IPAdic のこの札は `問題ない`・`間違いない`・`仕方ない` のように
    # **ない を伴ってイ形容詞のふるまいをする名詞**に付く。
    # `問題` そのものは**名詞**であって、イ形容詞の語幹ではない
    # （`問題い` とは言えない。`赤い` の `赤` とは別物）。
    # 実機メモでは 問題×24・間違い×7・違い・まちがい・仕方 の
    # 35 か所が「イ形容詞の語幹」と出ていた。
    'ナイ形容詞語幹': '名詞（「ない」に続く）',
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

# 接尾辞の下の段（項目48-QD・2026-09-04）。実機メモに出るのはこの9つ。
# `本`（助数詞）と `書`（一般）と `的`（ナ形容詞を作る）は付き方が
# 違う——48-PQ（`スクロール語 → 後`）のような判断を読むときに、
# ここが分かれていないと追えない。
_SUFFIX_SUB = {
    '一般': '接尾辞',
    '助数詞': '接尾辞（助数詞）',
    '副詞可能': '接尾辞（副詞にもなる）',
    '形容動詞語幹': '接尾辞（ナ形容詞を作る）',
    'サ変接続': '接尾辞（サ変）',
    '人名': '接尾辞（人名に付く）',
    '地域': '接尾辞（地名に付く）',
    '助動詞語幹': '接尾辞（助動詞の語幹）',
    '特殊': '接尾辞（特殊）',
}

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

# **基底のかな ＋ 小書きのかな で「1拍」になる組**（項目48-QE・
# 2026-09-04）。解析がこの2字の**あいだ**で切ったなら、その切り方は
# 拍の内側を割っている——**日本語の音として成り立たない**ので、
# そこから引いた品詞はどれも当て推量になる。
#
#   しゅるい  → `し ＝ 動詞・連用形／原形 する ／ ゅるい ＝ 断片`
#               `し` を「する の連用形」と**言い切っている**が、
#               `しゅ` は1拍で、`し` はその半分でしかない
#
# **`っ`（促音）は入れない。** `って`・`っけ`・`っす` は辞書に在る語で、
# **小書きで始まってよい唯一の例外**（入れると `直しませんでしたっけ`
# の `っけ ＝ 助詞（終助詞）`・`往って` の `って ＝ 助詞（格助詞）` を
# 壊す・実測）。**`ヵ`／`ヶ` も入れない**（`ヶ月` は接尾辞）。
def _mora_pairs():
    out = set()
    for b in 'きぎしじちぢにひびぴみりふゔてで':
        for s in 'ゃゅょ':
            out.add(b + s)
    out |= {
        'ふぁ', 'ふぃ', 'ふぇ', 'ふぉ',
        'うぃ', 'うぇ', 'うぉ',
        'ゔぁ', 'ゔぃ', 'ゔぇ', 'ゔぉ',
        'てぃ', 'でぃ', 'とぅ', 'どぅ',
        'つぁ', 'つぃ', 'つぇ', 'つぉ',
        'しぇ', 'じぇ', 'ちぇ',
        'くぁ', 'くぃ', 'くぇ', 'くぉ', 'ぐぁ',
        'すぃ', 'ずぃ', 'いぇ',
        'くゎ', 'ぐゎ',
    }
    return frozenset(out)


_MORA_PAIR = _mora_pairs()

#: 語の頭に立てない小書き（`っ`・`ヵ`・`ヶ` は**わざと外してある**）
_SMALL_NOT_HEAD = 'ぁぃぅぇぉゃゅょゎァィゥェォャュョヮ'


def _to_hira(c):
    """カタカナ1字をひらがなに落とす（それ以外はそのまま）。"""
    return chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' and c != 'ー' else c


def _mora_cut(toks):
    """
    **語の切れ目が、1拍の内側に入っているか**（項目48-QE）。

    入っていれば (添字, その1拍) を返す。無ければ None。
    """
    for k in range(1, len(toks)):
        head = toks[k][0]
        prev = toks[k - 1][0]
        if not head or not prev or head[0] not in _SMALL_NOT_HEAD:
            continue
        pair = _to_hira(prev[-1]) + _to_hira(head[0])
        if pair in _MORA_PAIR:
            return k, prev[-1] + head[0]
    return None



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


def _no_word_chars(s):
    """かな・漢字・英字を1つも含まない（＝数字と記号だけ）か。"""
    for c in s:
        if ('ぁ' <= c <= 'ゖ' or 'ァ' <= c <= 'ヺ' or c == 'ー'
                or '一' <= c <= '鿿'
                or 'a' <= c <= 'z' or 'A' <= c <= 'Z'
                or 'ａ' <= c <= 'ｚ' or 'Ａ' <= c <= 'Ｚ'):
            return False
    return True


def pos_name(pos, surface='', infl_form='', base_form='',
             has_reading=True):
    """
    形態素1つ分の品詞を、**うにさんの呼び方**で1行にする。

    pos: `名詞:固有名詞:人名:姓` の形（`corrector.make_tokenizer` が
         渡してくる形）でも `名詞` だけでもよい。
    infl_form: janome の活用形（`morphology.Token.infl_form`）。
         無ければ活用の話は書かない。
    """
    # **長音記号は品詞ではない**（項目48-PW・2026-09-04・うにさんの
    # 報告「`かー` の判定も変」——janome は独立した `ー` を
    # `名詞:固有名詞` と当て推量する。前の字と合わせて1拍の記号で
    # あって、固有名詞と呼ぶのは判定ではない）。
    if surface and all(c == 'ー' for c in surface):
        return '長音（前の字と合わせて1拍）'
    # **小書きで始まる語は無い**（同・「頭に小文字が来るのも変」）。
    # 解析がそう切ったなら、それは**語の途中で切れた断片**（48-OI と
    # 同じ根拠）。janome の当て推量（名詞:一般）を名乗らせない。
    if (surface and surface[0] in 'ぁぃぅぇぉゃゅょっゎァィゥェォャュョッヮ'
            and not has_reading):
        return f'断片（小書き `{surface[0]}` で始まる——語の頭に立たない）'
    # **英字の並びを「組織名」と名乗らない**（項目48-QD・2026-09-04）。
    # janome は知らないアルファベットの並びを**片端から
    # `名詞:固有名詞:組織`** と当て推量する。実機メモでは 742 か所が
    # これで、中身は `ja`・`F`・`s`・`the`・`Ctrl`・`Shift`・`https`・
    # `py`・`and`・`to` ——**組織名は1つも無い**。
    # 読みが取れていない（＝解析が知らない）英字の並びに限って、
    # 当て推量の札を名乗らせず、**分かっている事実だけ**を言う。
    # 読みが取れている英字（辞書に在る語）は今までどおり。
    if (surface and not has_reading
            and all('a' <= c <= 'z' or 'A' <= c <= 'Z' for c in surface)):
        return '英字（解析は品詞を言えない）'
    # **数字と記号は「読みが無い」を根拠にしない**（項目48-QD）。
    # 読みが取れないのは当たり前で、「辞書に無い語」の証拠ではない。
    # `://` や `.` のような**記号だけの並び**を janome は
    # `名詞:サ変接続` と当て推量する——記号は記号と言う。
    if surface and _no_word_chars(surface):
        if not has_reading and not any(c.isdigit() for c in surface):
            return '記号'
        has_reading = True      # 数字に「辞書に無い語」とは書かない

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
        elif sub1 == '接尾':
            # **どんな接尾辞かまで言う**（項目48-QD・2026-09-04）
            label = _SUFFIX_SUB.get(subs[1] if len(subs) > 1 else '',
                                    '接尾辞')
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

    戻り値: [(表記, 品詞, 活用形, 原形, 読みが取れたか, **読み**), ...]

    6つ目の**読み**は 48-RN で足した（固有名詞を信用してよいかの
    判定に要る）。**既存の添字は1つも動かしていない**ので、
    5つで受けている場所は `t[:5]` で受け直すだけでよい。
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
                            t.base_form or '', bool(t.has_reading),
                            getattr(t, 'reading', '') or ''))
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
                                       all(bool(t[4]) for t in _part),
                                       '')]
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
            # **活用形（7つ目・48-NT）は落とさない**（項目48-PW——
            # 落とすと「動詞の終止形＋名詞」の注記がこの道でだけ
            # 黙る・学び22）。
            return [(t[0], t[1] or '',
                     (t[6] if len(t) > 6 else '') or '', '', bool(t[5]),
                     (t[2] if len(t) > 2 else '') or '')
                    for t in tokenize_fn(text)]
        except Exception:
            pass
    return []


def _remember(text, tokens):
    if len(_TOK_CACHE) > _TOK_CACHE_LIMIT:
        _TOK_CACHE.clear()
    _TOK_CACHE[text] = tokens
    return tokens


def _is_kana_char(c):
    """かな（ひらがな・カタカナ・長音）か。"""
    return bool(c) and ('ぁ' <= c <= 'ゖ' or 'ァ' <= c <= 'ヺ' or c == 'ー')


def _proper_noun_note(toks, i, store, dict_index):
    """
    **その固有名詞の札を、そのまま名乗ってよいか**（項目48-RN・
    2026-09-05・うにさんの報告「`右田でブルクリック`——以前も
    言ったが、**地名と人名判定の優先度を下げなければいけない**」）。

    48-OR は①（異様か）で「解析の言う固有名詞を特別扱いしない」と
    決めた。**同じ判定を、表示が知らなかった**——エンジンが
    「信用しない」と決めた札を、品詞判定の欄が**そのまま名乗って**
    いた（`右田 ＝ 固有名詞（地名）`）。

    ★★ **判定は借りるだけ。新しい判定は作らない**（48-GN）——
    `oddness._proper_noun_downgradable`（そもそも落としてよい形か）と
    `oddness._proper_noun_is_trusted`（信用してよいか）の2本を、
    ①が見ているのと**同じ材料**で呼ぶ。

    戻り値: 言い換えの字（`当て推量（地名）——…`）か、空。
    """
    if store is None and dict_index is None:
        return ''
    try:
        import oddness as _odd
        if not _odd._proper_noun_downgradable(toks, i):
            return ''
        t = toks[i]
        # `_proper_noun_is_trusted` は (表記, 品詞, 読み) を見る
        _t3 = (t[0], t[1], (t[5] if len(t) > 5 else ''))
        if _odd._proper_noun_is_trusted(_t3, store, dict_index):
            return ''
    except Exception:
        return ''
    pos = (toks[i][1] or '')
    if '人名' in pos:
        what = '人名'
    elif '地域' in pos or '地名' in pos:
        what = '地名'
    elif '組織' in pos:
        what = '組織名'
    else:
        what = '固有名詞'
    return f'当て推量（{what}）——固有名詞として信用しない'


def _unknown_katakana_note(t):
    """
    **janome が知らないカタカナを「組織名」と名乗らない**
    （項目48-RN／D6(b)・2026-09-05・うにさんの報告
    「`解析課背中セク、`——セクが組織名である判定が変」）。

    48-QD が英字でやったのと**同じ根拠**をカタカナに広げる——
    辞書に無い綴りに janome が当てる `名詞:固有名詞:組織` は、
    札ではなく**当て推量**。「知らない」と言うほうが正しい。
    """
    surf = t[0] or ''
    if not surf or not all('ァ' <= c <= 'ヶ' or c == 'ー' for c in surf):
        return ''
    pos = (t[1] or '')
    if '固有名詞' not in pos:
        return ''
    if len(t) > 4 and t[4]:
        return ''               # 読みが取れている＝辞書に在る
    return 'カタカナ（辞書に無い語）'


def _kana_only(text):
    """かな（と長音）だけの範囲か。"""
    return bool(text) and all(_is_kana_char(c) for c in text)


def _verb_noun_cut(toks):
    """
    鎖のどこかで**動詞の終止形に名詞が直付き**になっているか
    （項目48-RL）。なっていれば (添字, 動詞の字, 名詞の字)。

    判定そのものは `corrector._verb_noun_pair` の**1本**を借りる
    （48-GN——同じ文法をもう一度書かない）。
    """
    try:
        from corrector import _verb_noun_pair as _vnp
    except Exception:
        return None
    for k in range(1, len(toks)):
        try:
            if _vnp(toks[k - 1][1], toks[k - 1][2], toks[k][1]):
                return k, toks[k - 1][0], toks[k][0]
        except Exception:
            continue
    return None


def _run_neighbour_note(text, prev_text, next_text):
    """
    **隣とひとつづきである事実**（項目48-RG・2026-09-05・うにさんの指定
    「**判定できないなら、できる範囲で判定するべきです**」）。

    48-QE は「1拍の内側で切れた割り方から品詞を言わない」と決めた——
    これは正しいので**動かさない**。だが「判定できません」だけで
    終わると、**分かっていることまで黙る**ことになる。

    `かんいりゅうりょく` は解析が `かん｜いりゅうりょく` に切るので、
    F2 で後ろを見ると `いりゅうりょく` になる。**品詞は言えない**が、
    「**前の『かん』とひとつづきのかな連続**」は**見れば分かる事実**で、
    当て推量ではない。それを添える。

    **品詞は言わない**（言えないから）。両隣ともかなで繋がるときは
    両方を言う。繋がらない側は黙る。
    """
    if not text:
        return ''
    sides = []
    if prev_text and _is_kana_char(prev_text[-1]) \
            and _is_kana_char(text[0]):
        sides.append('前の「%s」' % prev_text[-6:])
    if next_text and _is_kana_char(next_text[0]) \
            and _is_kana_char(text[-1]):
        sides.append('後ろの「%s」' % next_text[:6])
    if not sides:
        return ''
    return '。%sとひとつづきのかな連続' % '・'.join(sides)


def candidate_pos_line(surface, tokenize_fn):
    """
    **候補の品詞を1行で**（項目48-RH・2026-09-05・うにさんの指定
    「**判定できないなら、できる範囲で判定するべきです**」）。

    打った字が「1拍の内側で切れた割り方」で品詞を言えないとき
    （48-QE）、**一覧に既に並んでいる筆頭候補**を借りて
    「その候補ならこう」と言い添える材料。

        `いりゅうりょく` → 判定できません（…）
                           候補「入力」なら 名詞（サ変）

    ★★ **新しい判定は作らない**（48-GN）——janome に聞くだけ。
    **1語に割れないなら何も言わない**（割れた鎖に品詞を言い切るのは
    48-QE がやめたこと。候補の側でも同じ）。

    戻り値: `名詞（サ変）` のような字。言えなければ空。
    """
    if not surface or tokenize_fn is None:
        return ''
    try:
        toks = tokenize_fn(surface)
    except Exception:
        return ''
    if not toks or len(toks) != 1:
        return ''                    # 1語で割れないなら言わない
    t = toks[0]
    if (t[0] or '') != surface:
        return ''
    try:
        name = pos_name(t[1], t[0], (t[6] if len(t) > 6 else ''),
                        '', bool(t[5]) if len(t) > 5 else True)
    except Exception:
        return ''
    if not name or name == UNKNOWN_POS:
        return ''
    return name


def pos_lines(text, tokenize_fn=None, store=None, pos_hint=None,
              infl_hint='', atomic_hint=False, known_hint=True,
              prev_text='', next_text='', dict_index=None):
    """
    **選んだ範囲の品詞**（「－ 品詞判定 －」の中身）を行の一覧で返す。

    語が2つ以上に割れたときは**1語ずつ1行**にする。**割れたこと
    自体が分析の材料**なので、代表の1つに丸めない
    （`にゅうりょくみす` が `に｜ゅうりょくみす` に割れているのは、
    紫が立たない理由そのもの）。1行にまとめないのは、候補一覧の
    幅がその1行の長さで決まるから（`_make_dropdown`）。

    `prev_text` / `next_text` を渡すと、**1拍の内側で切れた割り方**の
    ときに「隣とひとつづきのかな連続」という**事実だけ**を添える
    （項目48-RG。**品詞は言わない**——言えないから）。

    **判定が変なときは、変だと言う**（項目48-PW・2026-09-04・
    うにさんの指定「品詞の判定を見れば見るほど変なので、品詞判定を
    よく見て、細かく見て修正をしていってください」）:
      ・かなの範囲がまるごと**カタカナ語のかな書き**なら、バラバラの
        当て推量の鎖（`か＝助詞／ー＝固有名詞／そる＝動詞`）ではなく
        その1行で言い切る（判定は `loanword.katakana_for_hiragana`
        ただ1つ・48-GN。store が要るので、渡されたときだけ）
      ・**動詞の終止形に名詞が直付き**（`たぶ＝動詞・終止形／
        い＝名詞`）なら、48-PL と同じ述語で「つながりが異様」と
        書き添える——分析の鎖を見せたうえで、正しい並びではないと
        伝える（★★「異様であると認識しているのかが重要」の表示版）
    """
    text = text or ''
    if not text.strip():
        return [UNKNOWN_POS]
    # **1字の助詞は、行の文脈の品詞で言う**（項目48-PW・2026-09-04）。
    # この関数は範囲の文字列だけを解析し直すので、`が`・`で` を単独で
    # 掛けると janome は文頭の「接続詞」（だが・それで の類）と
    # 当て推量する。単位は行を解析したときの品詞（`pos`）を持って
    # いるので、**1字のときはそちらが正しい**（呼び手が渡したとき）。
    if pos_hint and len(text) == 1:
        return [pos_name(pos_hint, text, infl_hint or '',
                         has_reading=known_hint)]
    # **行の解析が「1語」と見た範囲は、その品詞を名乗る**（項目48-QC・
    # 2026-09-04）。上の1字の門と同じ理由を、**長さではなく事実**で
    # 言い直したもの——この関数は範囲の文字列**だけ**を割り直すので、
    # 文の中では起きなかった分かれ方を画面に出していた:
    #
    #     日間   行では 名詞:接尾:助数詞（7日間 の 日間）
    #            画面は `日 ＝ 固有名詞（地名・国名） ／ 間 ＝ 接尾辞`
    #     かな   行では 名詞:一般（31 か所）
    #            画面は `か ＝ 助詞（副助詞） ／ な ＝ 助詞（終助詞）`
    #     ない   行では 助動詞（できない の ない・53 か所）
    #            画面は `イ形容詞・終止形`
    #     よう   行では 名詞:非自立:助動詞語幹（36 か所）
    #            画面は `感動詞`
    #
    # **文脈のある側が正しい。** 単独で割り直したほうは当て推量。
    # `atomic_hint` は「行の解析が**手を加えずに**1語と見た」——
    # まとめた単位（`のよう`＝の＋よう・`します`＝し＋ます）や、
    # 前処理が作った語（`きゃー`＋`っ`）では False になるので、
    # 鎖の表示はそのまま残る（あれは本当に鎖）。
    # `known_hint` は「解析がその語の読みを言えた」——言えない塊
    # （`にゅうりょくみす`）は、当て推量の品詞を名乗るより、
    # 割り直した鎖のほうが分析の材料になるので今までどおり。
    #
    # 実測（実機メモの単位 5,471 種）: **1,117 種・4,555 か所**の
    # 判定が変わり、**悪くなったものは1つも無い**
    # （`tools_local/probe_pos_survey.py` の全種突き合わせ）。
    if pos_hint and atomic_hint and known_hint:
        # **原形は落とさない**（`押し` を見て `押す` だと分かるように）。
        # 単位は原形を持っていないので、割り直した側から借りる——
        # ただし**割り直しても1語で、大分類が一致するとき**だけ
        # （`押し` が行では 名詞 のとき、単独の解析が言う 原形 押す を
        #   添えると、名詞に動詞の原形が付いて食い違う）。
        _base = ''
        _one = _tokens_for(text, tokenize_fn)
        if (len(_one) == 1 and _one[0][0] == text
                and _major_and_sub(_one[0][1])[0]
                == _major_and_sub(pos_hint)[0]):
            _base = _one[0][3] or ''
        return [pos_name(pos_hint, text, infl_hint or '', _base,
                         has_reading=known_hint)]
    toks = _tokens_for(text, tokenize_fn)
    if not toks:
        return [UNKNOWN_POS]
    if (store is not None and len(toks) >= 2 and len(text) >= 4
            and all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in text)):
        try:
            from loanword import katakana_for_hiragana as _k4h
            kata = _k4h(text, store, min_length=4)
        except Exception:
            kata = None
        if kata:
            return [f'カタカナ語（{kata}）のかな書き']
    if len(toks) == 1:
        # **1語のときも同じ判定を通す**（学び22——片方だけに置くと
        # そちらを迂回する。`セク` 単独はこの道）
        _n1 = (_unknown_katakana_note(toks[0])
               or _proper_noun_note(toks, 0, store, dict_index))
        if _n1:
            return [_n1]
        surface, pos, infl, base, has_reading = toks[0][:5]
        return [pos_name(pos, surface, infl, base, has_reading)]
    lines = [f'{surface} ＝ {pos_name(pos, surface, infl, base, hr)}'
             for surface, pos, infl, base, hr in (t[:5] for t in toks)]
    # **固有名詞の当て推量は、そう言う**（項目48-RN）。
    # ①（`oddness`）が「信用しない」と決めた札を、ここだけ
    # そのまま名乗るのはおかしい（学び22——同じ判定を全部の道に）
    for _i, _t in enumerate(toks):
        _note2 = (_unknown_katakana_note(_t)
                  or _proper_noun_note(toks, _i, store, dict_index))
        if _note2:
            lines[_i] = f'{_t[0]} ＝ {_note2}'
    # **1拍の内側で切れた割り方からは、品詞を言わない**（項目48-QE・
    # 2026-09-04・うにさんの指定「頭に小文字が来るのも変」の根っこ）。
    #
    # 48-PW は**切られた側**（`ゅるい`）に「断片」と書くところまで
    # 進めた。だが**切った側**（`し`）は「動詞・連用形／原形 する」と
    # 言い切ったままだった——`しゅ` は1拍で、`し` はその半分でしかない。
    # **半分の音に品詞は無い。** 切れ目が拍の内側にあると分かった時点で、
    # その割り方から引いた品詞は**全部**当て推量になる。
    #
    #     しゅるい  旧 `し ＝ 動詞・連用形／原形 する ／ ゅるい ＝ 断片`
    #               新 `判定できません（`しゅ` は1拍——語の途中で
    #                   切れています）`
    #
    # かなだけの範囲は1行に言い直す。漢字や記号を含む範囲は**取り
    # 過ぎない**——割れた2語ぶんだけを繋いで言い直し、ほかの語の行は
    # そのまま残す（`外しょつする` の `する` は正しい判定なので消さない）。
    _mc = _mora_cut(toks)
    if _mc is not None:
        _k, _mora = _mc
        # **言える事実を添える**（項目48-RG）——品詞は言えないが、
        # 「隣とひとつづきのかな連続だ」は見れば分かる
        _side = _run_neighbour_note(text, prev_text, next_text)
        _note = (f'{UNKNOWN_POS}（`{_mora}` は1拍——語の途中で'
                 f'切れています{_side}）')
        if all('ぁ' <= c <= 'ゖ' or 'ァ' <= c <= 'ヺ' or c == 'ー'
               for c in text):
            lines = [_note]
        else:
            _joined = toks[_k - 1][0] + toks[_k][0]
            lines = (lines[:_k - 1] + [f'{_joined} ＝ {_note}']
                     + lines[_k + 1:])
    elif _kana_only(text):
        # ★★ **かなだけの範囲で「動詞の終止形＋名詞の直付き」が
        # 要る割り方は、割り方ごと当て推量**（項目48-RL・2026-09-05・
        # うにさんの報告「`たぶいごうして`——動詞終止形から名詞と
        # 繋がる**誤判定**。この文法は変ですよね」）。
        #
        #   いま  たぶ ＝ 動詞・終止形 ／ い ＝ 名詞 ／ … ／
        #         ※ 品詞のつながりが異様
        #   新    判定できません（「たぶ」を動詞と読むと、終止形に
        #         名詞「い」が直付きになる——成り立たない割り方。…）
        #
        # 48-QE（1拍の内側で切れた割り方から品詞を言わない）と
        # **同じ性質**——解析が壊れたかなに当てた割り方は、
        # 割り方ごと当て推量。48-PW は鎖を見せて ※ を足したが、
        # うにさんは**鎖そのもの**を誤判定だと言っている。
        #
        # **漢字を含む範囲（`解す咳`）は今までどおり**鎖＋※——
        # うにさん自身がその言い方で報告した形（48-PL）。
        # 判定は `corrector._verb_noun_pair` の**1本のまま**（48-GN）。
        _vn = _verb_noun_cut(toks)
        if _vn is not None:
            _kk, _vw, _nw = _vn
            _side2 = _run_neighbour_note(text, prev_text, next_text)
            lines = [f'{UNKNOWN_POS}（「{_vw}」を動詞と読むと、'
                     f'終止形に名詞「{_nw}」が直付きになる'
                     f'——成り立たない割り方{_side2}）']
            _mc = True          # ※ を足さない（下の try が見る）
    try:
        if _mc is not None:
            raise ValueError        # 成り立たない割り方に注記は付けない
        from corrector import _verb_noun_pair as _vnp
        for k in range(1, len(toks)):
            if _vnp(toks[k - 1][1], toks[k - 1][2], toks[k][1]):
                lines.append('※ 品詞のつながりが異様'
                             '（動詞の終止形に名詞が直付き）')
                break
    except Exception:
        pass
    # **まるごとで語彙に在る読みなら、そう言い添える**（項目48-PW）。
    # `かいせき` を単独で解析すると `かいせ＝動詞・未然形／き＝助動詞`
    # のような当て推量の鎖になるが、本人の語彙は `かいせき` を
    # 1つの読み（解析）として持っている。鎖だけ見せると「聞かない
    # 分かれ方」が判定に見えてしまう（うにさんの「見れば見るほど変」）。
    # **動詞・助動詞を含む鎖には出さない**——`される`（さ＋れる）・
    # `かいせき`（かいせ＋き）は形のうえでは正しい活用の鎖なので、
    # 「当て推量」と言い切れない（`される` に付けて検品で出た→
    # 受け止めた）。出すのは**名詞・助詞だけの鎖**（`こてい`＝こ＋てい・
    # `かだい`＝か＋だい・`かくにん`＝かく＋に＋ん）——活用しない
    # 品詞だけの並びが、たまたま1語の読みと同じ長さで割れている形。
    if (store is not None and len(text) >= 3
            and all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in text)
            and not any((p or '').split(':')[0] in ('動詞', '助動詞')
                        for _s, p, _i, _b, _h in (t[:5]
                                                  for t in toks))):
        try:
            if store.has_reading(text):
                lines.append('※ まるごとでは語彙に在る読み'
                             '（上の分かれ方は解析の当て推量）')
        except Exception:
            pass
    return lines


def pos_label(text, tokenize_fn=None):
    """`pos_lines` を1行に繋いだもの（検品と道具のため）。"""
    return '＋'.join(pos_lines(text, tokenize_fn))


# ============================================================
# 補正の根拠（「－ 補正根拠 －」の3行）
# ============================================================

# 1行目に出す「違和感の正体」。**判定をもう一度回して**書く。
NO_ODD_REASON = '異様だという判定は立っていない'

#: **撤去した**（項目48-QJ・2026-09-05）。初期語彙の使用回数の上限
#: （3）を見て「学習した」と書くかを決めていたが、**回数そのものを
#: 記録しなくなった**（うにさんの指定）。名前だけ残すと、いつか
#: 「回数がある」前提のコードがまた生える。`learn_reason` を参照。


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
    **本人の選択が効いたか**（「－ 補正根拠 －」の3行目）。

    効いていなければ **None**（呼び出し側はこの行を出さない）。

      ・語の枠（選び直し）で決まった
        → 「学習による選び直し」（うにさんの指定の言葉のまま）
      ・読みの枠（同音異義語で最後に選んだ表記）で決まった
        → 「前回この読みで選んだ表記に合わせた」

    ★★ **「何回使った語か」はもう書かない**（項目48-QJ・2026-09-05）。
    うにさんの指定「変換の根拠に、**履歴に何回あったという表示**が
    ありました。**履歴として記録されることをユーザは望みません**」。
    回数そのものを記録しなくなったので、書きようがない
    （旧: `学習した語彙が効いた（「X」・N回）`／`SEED_COUNT_MAX`）。
    """
    typed, fixed = typed or '', fixed or ''

    # ① 語の枠（選び直しの記憶）
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

    # ② 読みの枠（同音異義語で最後に選んだ表記・項目48-QH）
    #
    # ★★ **両方の読みで照らす**（項目48-QT）。`unit['reading']` は
    # 道によって中身が違う——`build_line_units`（補正結果の欄）は
    # **直した語の読み**、`build_suspect_units`（メモ欄・F2）は
    # **打った語の読み**を入れる（`units.py`）。片方だけ見ると、
    # **同じ1件が補正結果欄では出て、メモ欄では出ない**
    # （学び22——門が片方の道にしか掛かっていない形）。
    # 落ちるのは**読みが変わる直し**（誤字を直した読みで引き当て、
    # 枠の並べ替えが効いた場合）。`store.reading_of` を第一候補に
    # 「する」のではなく**足す**——`fixed` が語彙に立っていないとき、
    # いま出ている②を消してしまう（★★ 壊さない ＞ 直る）。
    if choices is not None and fixed:
        try:
            _rds = []
            if isinstance(unit, dict) and unit.get('reading'):
                _rds.append(unit['reading'])
            if store is not None:
                from morphology import katakana_to_hiragana as _k2h
                _got = _k2h(store.reading_of(fixed) or '')
                if _got and _got not in _rds:
                    _rds.append(_got)
            for reading in _rds:
                if choices.surface_for_reading(reading) == fixed:
                    return '前回この読みで選んだ表記に合わせた'
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
