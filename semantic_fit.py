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

"""名詞と述語の**意味の分類が噛み合うか**で、同じ読み（または1打違いの読み）の名詞を選ぶ段（2026-11-07）。

流れ（うにさん 2026-11-07 14:44Z）:
1. 行の「名詞＋格助詞＋述語」を見る。例文（Tatoeba の語の組・pair_choice の表）でその (助詞, 述語) と組になった名詞の
   分類番号（分類語彙表・semantic_class.codes）を集め、その組の「意味の仲間」とする（回数で重みを付ける）。
2. 行の名詞の分類番号が仲間に無い（噛み合わない）とき、その名詞をかなの読みに開く。
3. 読みから候補を出す: 同じ読みの名詞（IME の選び違い）と、かな入力なら1打だけ戻した読みの名詞（打ち違い）。
4. 候補のうち、分類が仲間に在るものを選ぶ。1つに決まれば直す。0か2つ以上なら紫。
IME は使わない（雲と PC で同じ答え）。表が無い・名詞が分類に無い・組の例が少ない所は何もしない。
特定の語や文字列には合わせない。CN_SEMANTIC_FIT=0 で止まる。
"""

import difflib
import os
from collections import Counter
from functools import lru_cache

PROFILE_NOUNS = 3     # (助詞, 述語) の仲間を信じるのは、例文で組になった名詞がこれだけ（種類）在るとき
PROFILE_COUNT = 6     # …そして組の回数の合計がこれだけ在るとき
CAND_WEIGHT = 2       # 候補の分類が仲間でこれだけの回数（重み）を持つこと
FIX_WEIGHT = 4        # これ以上で候補が1つなら直す
PURPLE_DEPTH = 4      # 紫だけにするのは番号の頭 4 桁（1.16）でも仲間に無いとき
MISS_DEPTH = 5        # 噛み合わないとみる比べの桁（1.161 まで）
RANK_MARGIN = 50      # 候補の一般の文での稀さ（ime_reconvert._rank・大きいほど稀）が元の語をこれ以上超えないこと
KEY_RARE = 500        # 1打違いの読みの候補を見るのは、元の語の稀さ（_rank）がこれ以上のとき
FIX_RANK_GAP = 30     # 直し先は一般の文で元の語よりこれだけよく使う語（自己→事故・辺り→当たり は差が20未満）
FIX_PAIR = 2          # …または、直し先の組そのものが例文にこれだけ在る（機械を逃した→機会: どちらもよく使う語）
# で・から は手段・場所・時・起点の添えの語にも付き、述語が選ぶ名詞と限らないので見ない（粘土で作った→年度 にしていた）
GEN_RARE = 530        # 名詞＋の＋名詞の組だけで紫にするのは、元の語の稀さ（_rank）がこれ以上のとき
CASES = ('を', 'に', 'が', 'へ', 'と')
CASES_SEEN = CASES + ('で', 'から')   # 組そのもので見る段（_case_marks）の格助詞
_FORMAL = {'ん', 'の', 'よう', 'こと', 'もの', 'ところ', 'わけ', 'はず', 'ため', 'とき', 'そう', 'ほう'}
_LIGHT = {'ある', 'いる', 'なる', 'する', 'できる', 'やる', 'いう', '言う', 'おく', 'くる', 'みる', 'しまう'}


def enabled():
    return os.environ.get('CN_SEMANTIC_FIT') != '0'


@lru_cache(maxsize=1)
def _sahen_pairs():
    """名詞＋格助詞＋サ変の名詞（する）の組と回数（tatoeba_sahen.json.gz・Tatoeba の例文から数えた・2026-11-07）。
    pair_choice の表は述語が動詞の組だけなので、問題を検討する・部屋を掃除する の組はこちら。無ければ空。
    CN_SEMANTIC_FIT_SAHEN=0 で使わない。"""
    if os.environ.get('CN_SEMANTIC_FIT_SAHEN') == '0':
        return {}
    try:
        import gzip
        import json
        with gzip.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tatoeba_sahen.json.gz'),
                       'rt', encoding='utf-8') as f:
            return json.load(f).get('pairs') or {}
    except Exception:
        return {}


@lru_cache(maxsize=1)
def _by_sahen():
    """{(助詞, サ変の名詞): ((名詞, 回数), …)}。述語の側の選び違い（_pred_marks）だけで使う。名詞の側の仲間に混ぜると、
    例の少ないサ変の述語で同じ分類の述語から借りられなくなり、帰納を追加→機能 などを見落とした。"""
    out = {}
    for key, n in _sahen_pairs().items():
        parts = key.split('\t')
        if len(parts) == 3 and parts[0] in CASES:
            out.setdefault((parts[0], parts[2]), []).append((parts[1], n))
    return {k: tuple(v) for k, v in out.items()}


@lru_cache(maxsize=4096)
def sahen_profile(p, v):
    nouns = [(w, n) for w, n in _by_sahen().get((p, v), ()) if _codes(w)]
    if not _enough(nouns):
        return None
    c = Counter()
    for w, n in nouns:
        for code in _codes(w):
            c[code] += n
    return c


@lru_cache(maxsize=1)
def _by_pred():
    """{(助詞, 述語): ((名詞, 回数), …)}。pair_choice の表（Tatoeba の語の組）から。"""
    try:
        import pair_choice
        tab = pair_choice._table()
    except Exception:
        tab = None
    if not tab:
        return {}
    out = {}
    gen = os.environ.get('CN_SEMANTIC_FIT_GEN') != '0'
    for key, n in tab[0].items():
        parts = key.split('\t')
        if len(parts) != 3:
            continue
        if parts[0] in CASES:
            out.setdefault((parts[0], parts[2]), []).append((parts[1], n))
        elif gen and parts[0] == 'の':
            # 名詞＋の＋名詞: 右の名詞から見た左の名詞の仲間（'の>', 右）と、左から見た右の仲間（'<の', 左）
            out.setdefault(('の>', parts[2]), []).append((parts[1], n))
            out.setdefault(('<の', parts[1]), []).append((parts[2], n))
        elif gen and parts[0] == '連体':
            out.setdefault(('連体', parts[1]), []).append((parts[2], n))
    return {k: tuple(v) for k, v in out.items()}


def _pair_count(p, noun, v):
    """その組そのものが例文に在る回数。p は格助詞か 'の>'（noun の v）・'<の'（v の noun）・'連体'（v noun）。"""
    key = {'の>': ('の', noun, v), '<の': ('の', v, noun), '連体': ('連体', v, noun)}.get(p, (p, noun, v))
    try:
        import pair_choice
        k = '\t'.join(key)
        return pair_choice._table()[0].get(k, 0) + _sahen_pairs().get(k, 0)
    except Exception:
        return 0


def _codes(word):
    try:
        import semantic_class
        return semantic_class.codes(word)
    except Exception:
        return frozenset()


@lru_cache(maxsize=1)
def _preds_by_code():
    """述語の分類番号（分類語彙表の「用」）→ 例文の表に在る述語の並び。"""
    try:
        import semantic_class
    except Exception:
        return {}
    out = {}
    for _p, v in _by_pred():
        for code in semantic_class.verb_codes(v if v.endswith(('る', 'う', 'く', 'ぐ', 'す', 'つ', 'ぬ', 'ぶ', 'む')) else v + 'する'):
            out.setdefault(code, set()).add(v)
    return out


def _verb_codes(v):
    try:
        import semantic_class
        got = semantic_class.verb_codes(v)
        return got or semantic_class.verb_codes(v + 'する')
    except Exception:
        return frozenset()


@lru_cache(maxsize=4096)
def profile(p, v):
    """(助詞, 述語) と組になる名詞の分類番号 → 重み（組の回数）。例が少なければ None。
    その述語の例が少ないときは、同じ分類番号（「用」）の述語の例を借りる（察する→推測する・作成する→作る）。"""
    nouns = list(_by_pred().get((p, v), ()))
    if not _enough(nouns) and os.environ.get('CN_SEMANTIC_FIT_BORROW') != '0':
        by = _preds_by_code()
        for code in _verb_codes(v):
            for w in by.get(code, ()):
                # かなだけの述語（みる・はかる）と、ほかの意味の分類も持つ述語（買う＝値打ちを認める／品を買う）は借りない
                if w != v and w not in _LIGHT and any(_is_kanji(c) for c in w) and _verb_codes(w) <= _verb_codes(v):
                    nouns += _by_pred().get((p, w), ())
    known = [(w, n) for w, n in nouns if _codes(w)]
    if len(known) < PROFILE_NOUNS or sum(n for _w, n in known) < PROFILE_COUNT:
        return None
    c = Counter()
    for w, n in known:
        for code in _codes(w):
            c[code] += n
    return c


def _enough(nouns):
    known = [(w, n) for w, n in nouns if _codes(w)]
    return len(known) >= PROFILE_NOUNS and sum(n for _w, n in known) >= PROFILE_COUNT


def fit(word, prof, depth=None):
    """語の分類番号が仲間で持つ重み。depth を渡すと番号の頭だけで比べる（1.1611 → 1.161）。"""
    if not depth:
        return max((prof.get(code, 0) for code in _codes(word)), default=0)
    heads = {c[:depth] for c in _codes(word)}
    return sum(n for code, n in prof.items() if code[:depth] in heads)


def _rank(word):
    try:
        import ime_reconvert
        return ime_reconvert._rank(word)
    except Exception:
        return 0


def _is_kanji(c):
    return '一' <= c <= '鿿' or c == '々'


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


def _sub(t):
    """品詞の細分の頭（'非自立:一般' → '非自立'）。"""
    return (getattr(t, 'pos_sub', '') or '').split(':')[0]


def _noun(t):
    return (t.pos == '名詞' and _sub(t) not in ('非自立', '代名詞', '数', '接尾', '固有名詞')
            and t.surface not in _FORMAL and getattr(t, 'has_reading', True) and any(_is_kanji(c) for c in t.surface))


def _verb_at(toks, j):
    """j の語が述語なら基本形（動詞・サ変の名詞＋する）。そうでなければ None。"""
    if j >= len(toks):
        return None
    v = toks[j]
    if v.pos == '名詞' and _sub(v) == 'サ変接続' and j + 1 < len(toks) \
            and (getattr(toks[j + 1], 'base_form', '') or toks[j + 1].surface) == 'する' and toks[j + 1].start == v.end:
        return v.surface   # 資料を作成した: 述語は サ変の名詞＋する
    if v.pos != '動詞' or _sub(v) == '非自立':
        return None
    return getattr(v, 'base_form', '') or v.surface


def _inverted_pred(toks, i):
    """倒置（見たよ、あの映画を。）: 名詞＋格助詞が行か文の終わりにあり、前の 、 のすぐ前の句が述語で終わるなら、
    その述語の基本形。名詞の前は連体詞・「名詞＋の」まで。CN_SEMANTIC_FIT_INVERTED=0 で見ない。"""
    if os.environ.get('CN_SEMANTIC_FIT_INVERTED') == '0':
        return None
    k = i + 2
    if k < len(toks) and not (toks[k].pos == '記号' and toks[k].surface in ('。', '！', '？', '!', '?', '…')):
        return None
    j = i - 1
    while j >= 1 and (toks[j].pos == '連体詞' or (toks[j].surface == 'の' and toks[j - 1].pos in ('名詞', '副詞'))):
        j -= 2 if toks[j].surface == 'の' else 1
    if j < 1 or toks[j].surface not in ('、', '，', ','):
        return None
    j -= 1
    while j >= 0 and (toks[j].pos in ('助動詞',) or (toks[j].pos == '名詞' and _sub(toks[j]) == '非自立') or (toks[j].pos == '助詞' and _sub(toks[j]) in ('終助詞', '接続助詞'))
                      or (toks[j].pos == '動詞' and _sub(toks[j]) == '非自立')):
        j -= 1
    if j < 0:
        return None
    if toks[j].pos == '動詞' and _sub(toks[j]) != '非自立':
        return getattr(toks[j], 'base_form', '') or toks[j].surface
    if j >= 1 and toks[j].surface in ('し', 'する', 'した') and toks[j - 1].pos == '名詞' and _sub(toks[j - 1]) == 'サ変接続':
        return toks[j - 1].surface
    return None


SKIP_CHUNKS = 2   # 名詞＋格助詞と述語の間に挟まってよい「名詞＋助詞」「副詞」のかたまりの数（設定に時間が掛かった）


def _pred(toks, i, cases=CASES):
    """i の名詞の直後が格助詞1つで、その後ろ（間に別の名詞＋助詞・副詞が SKIP_CHUNKS まで）が述語なら
    (助詞, 述語の基本形)。cases は見る格助詞（組そのもので見る段は で・から も）。"""
    if i + 2 >= len(toks):
        return None
    p = toks[i + 1]
    if p.pos != '助詞' or p.surface not in cases or p.start != toks[i].end:
        return None
    # 前の名詞と続く複合語（〜の機械）の頭だけを見ないよう、名詞が前の名詞に続いていれば見ない
    if i >= 1 and toks[i - 1].pos == '名詞' and toks[i - 1].end == toks[i].start:
        return None
    inv = _inverted_pred(toks, i)
    if inv:
        return (p.surface, inv) if inv not in _LIGHT else None
    j, chunks = i + 2, 0
    limit = SKIP_CHUNKS if os.environ.get('CN_SEMANTIC_FIT_SKIP') != '0' else 0
    while j < len(toks):
        base = _verb_at(toks, j)
        if base:
            if base in _LIGHT:
                return None
            return p.surface, base
        if chunks >= limit:
            return None
        t = toks[j]
        if t.pos == '副詞':
            j += 1
        elif t.pos == '名詞' and j + 1 < len(toks) and toks[j + 1].pos == '助詞' \
                and toks[j + 1].surface in CASES + ('は', 'も', 'で', 'から') and toks[j + 1].surface != p.surface:
            j += 2
        else:
            return None
        chunks += 1
    return None


def _alternatives(noun, reading, input_method):
    import pair_choice
    same = set(pair_choice._alternatives(noun, reading))
    key = set()
    if input_method == 'kana':
        try:
            key = set(pair_choice._key_alternatives(noun, reading)) - same
        except Exception:
            key = set()
    return same, key


def _contexts(toks, i):
    """i の名詞の組の文脈 [(種類, 相手)]。述語との組（格助詞, 述語）を先に、名詞＋の＋名詞・連体の語との組を後に。"""
    out = []
    pv = _pred(toks, i)
    if pv:
        out.append(pv)
    if os.environ.get('CN_SEMANTIC_FIT_GEN') != '0':
        if i + 2 < len(toks) and toks[i + 1].surface == 'の' and toks[i + 1].start == toks[i].end \
                and _noun(toks[i + 2]) and toks[i + 2].start == toks[i + 1].end:
            out.append(('の>', toks[i + 2].surface))
        if i >= 2 and toks[i - 1].surface == 'の' and _noun(toks[i - 2]) and toks[i - 1].end == toks[i].start:
            out.append(('<の', toks[i - 2].surface))
        if i >= 1 and toks[i - 1].pos in ('形容詞', '連体詞') and toks[i - 1].end == toks[i].start:
            out.append(('連体', getattr(toks[i - 1], 'base_form', '') or toks[i - 1].surface))
    return out


def _rel_clause_verb(toks, i):
    """i の名詞を連体で修める動詞の基本形（選ん｜だ｜漢字・食べる｜物）。無ければ None。"""
    j = i - 1
    if j >= 0 and toks[j].pos == '助動詞' and toks[j].surface in ('た', 'だ') and toks[j].end == toks[i].start:
        j -= 1
        if j < 0 or toks[j].end != toks[j + 1].start:
            return None
    elif j < 0 or toks[j].end != toks[i].start or not (toks[j].infl_form or '').startswith(('基本', '連体')):
        return None
    if toks[j].pos != '動詞':
        return None
    return getattr(toks[j], 'base_form', '') or toks[j].surface


def _rel_clause_fits(toks, i):
    v = _rel_clause_verb(toks, i)
    if not v:
        return False
    for p in ('を', 'が', 'に'):
        pr = profile(p, v)
        if pr and (fit(toks[i].surface, pr, MISS_DEPTH) or _pair_count(p, toks[i].surface, v)):
            return True
    return False


FIX_KNOWN = 600   # これより使われる語は、直し先の組が例文に無ければ分類の重みだけでは直さない
FIX_KNOWN_GAP = 150   # ただし直し先がこれだけ以上よく使われる語（次官 → 時間）なら直す


def propose(text, input_method='kana'):
    """[(始め, 終わり, 直し先 or None)]。"""
    if not enabled() or not _by_pred():
        return []
    from morphology import tokenize
    toks = list(tokenize(text))
    _TEXT[0] = text
    out = []
    for i, t in enumerate(toks):
        if not _noun(t) or not _codes(t.surface):
            continue
        ctxs = [(c, profile(*c)) for c in _contexts(toks, i)]
        ctxs = [(c, pr) for c, pr in ctxs if pr]
        if not ctxs:
            continue
        # 噛み合わないとみるのは、どの組でも分類番号の頭（MISS_DEPTH 桁）が仲間に無く、組そのものも例文に無いとき
        if any(fit(t.surface, pr, MISS_DEPTH) or _pair_count(c[0], t.surface, c[1]) for c, pr in ctxs):
            continue
        # 前に連体の動詞（選んだ｜漢字）が在り、元の語がその動詞の格の仲間に入るなら、述語との組が合わないことだけでは
        # 書き違いの証にしない（選んだ漢字が違う → 感じ にしていた・2026-11-08 未解決タブの誤判定）。CN_SF_REL_CLAUSE=0
        if os.environ.get('CN_SF_REL_CLAUSE') != '0' and _rel_clause_fits(toks, i):
            continue
        here = _rank(t.surface)

        def weight(a):
            return max(fit(a, pr) for _c, pr in ctxs)

        def ok(a):
            # 候補は一般の文で元の語よりはっきり稀ではないこと（野菜→油彩 のような稀な語へは替えない）
            return weight(a) >= CAND_WEIGHT and _rank(a) <= here + RANK_MARGIN

        same, key = _alternatives(t.surface, _hira(t.reading), input_method)
        best = [(weight(a), a) for a in same if ok(a)]
        by_key = False
        # 1打違いの読みの候補は、元の語が2字以上で一般の文で稀なときだけ（肩・隅 のような1字の語や よく使う語は
        # 1打違いの語がいくらでも在るので、噛み合わないことの証にならない）
        if not best and len(t.surface) >= 2 and here >= KEY_RARE:
            best = [(weight(a), a) for a in key if ok(a)]
            by_key = True
        if not best:
            continue
        best.sort(reverse=True)
        cand = best[0][1]
        # 直すのは、同じ読みの候補が1つで、元の語も直し先も2字以上で、直し先が一般の文で元の語よりよく使う語か、
        # 直し先の組そのものが例文に在るとき（1字の語・1打違いの読みは根拠が弱いので紫だけ）
        sure = (len(best) == 1 and best[0][0] >= FIX_WEIGHT and not by_key and len(t.surface) >= 2
                and len(cand) >= 2
                and (_rank(cand) <= here - FIX_RANK_GAP
                     or any(_pair_count(c[0], cand, c[1]) >= FIX_PAIR for c, _pr in ctxs)))
        # 直し先の組が例文に無く、元の語が語として知られている（FIX_KNOWN 未満: 蒸気）なら、分類の重みだけでは直さず紫
        # （直し先がはっきりよく使われる語なら直す: 次官 → 時間。水を蒸気に変える → 上記 にしていた・2026-11-09 補正担当の正しい文の試し）。CN_SF_FIX_COMMON_PAIR=0 で前のまま
        if (sure and here < FIX_KNOWN and _rank(cand) > here - FIX_KNOWN_GAP
                and os.environ.get('CN_SF_FIX_COMMON_PAIR') != '0'
                and not any(_pair_count(c[0], cand, c[1]) >= FIX_PAIR for c, _pr in ctxs)):
            sure = False
        if not sure and any(fit(t.surface, pr, PURPLE_DEPTH) for _c, pr in ctxs):
            continue   # 紫だけにするのは、どの組でも中項目（1.16）まで仲間に無いとき
        # 弱い組（述語の例が少なく同じ分類の述語から借りた・名詞＋の＋名詞や連体の語との組だけ）と1字の名詞
        # （死・雪・文: 同じ読みの語が多い）は、合う候補が1つだけで重みが FIX_WEIGHT 以上のときだけ見る
        # （肩を縫い合わせる・隅に積み重ねる のような正しい文に紫を付けていた）
        strong_ctx = ctxs[0][0][0] in CASES and _enough(list(_by_pred().get(ctxs[0][0], ())))
        if ctxs[0][0][0] not in CASES:
            # 名詞＋の＋名詞・連体の語との組だけのとき: 名詞どうしの「の」は関係が広いので、
            # 1字の名詞は疑わない（次の版で→紫）、直すのは直し先の組そのものが例文に在るときだけ（人々の習慣→週間 にしていた）、
            # 紫だけにするのは元の語が一般の文で稀なときだけ（火事の方向・本物の医師 に紫を付けていた）
            if len(t.surface) == 1:
                continue
            sure = sure and any(_pair_count(c[0], cand, c[1]) >= FIX_PAIR for c, _pr in ctxs)
            if not sure and here < GEN_RARE:
                continue
        if (not strong_ctx or len(t.surface) == 1) and not (len(best) == 1 and best[0][0] >= FIX_WEIGHT):
            continue
        # 1字の名詞は、合う候補の組そのものが例文に1つも無ければ疑わない（班を決める: 分類だけ合う 反 を決める は
        # 例文に無い。同じ読みの1字の語は多く、分類が合うだけでは書き違いの証にならない）。CN_SF_ONE_PAIR=0 で前のまま
        if (len(t.surface) == 1 and os.environ.get('CN_SF_ONE_PAIR') != '0'
                and not any(_pair_count(c[0], cand, c[1]) for c, _pr in ctxs)):
            continue
        out.append((t.start, t.end, cand if sure else None))
    if os.environ.get('CN_SEMANTIC_FIT_COMPOUND') != '0':
        done = {(a, b) for a, b, _r in out}
        out += [m for m in _compound_marks(toks) if not any(a < m[1] and m[0] < b for a, b in done)]
    if os.environ.get('CN_SEMANTIC_FIT_VERB') != '0':
        done = {(a, b) for a, b, _r in out}
        out += [m for m in _verb_marks(toks) if not any(a < m[1] and m[0] < b for a, b in done)]
    if os.environ.get('CN_SEMANTIC_FIT_PRED') != '0':
        done = {(a, b) for a, b, _r in out}
        out += [m for m in _pred_marks(toks) if (m[0], m[1]) not in done]
    if os.environ.get('CN_SEMANTIC_FIT_NO') != '0':
        done = {(a, b) for a, b, _r in out}
        out += [m for m in _gen_marks(toks, input_method) if not any(a < m[1] and m[0] < b for a, b in done)]
    if os.environ.get('CN_SEMANTIC_FIT_CASE') != '0':
        done = {(a, b) for a, b, _r in out}
        out += [m for m in _case_marks(toks, input_method) if not any(a < m[1] and m[0] < b for a, b in done)]
    return out


@lru_cache(maxsize=1)
def _case_pairs():
    """名詞＋格助詞＋述語 の組のうち pair_choice の表に無いもの（1回だけの組も）と回数（tatoeba_case.json.gz・
    Tatoeba の例文から数えた・2026-11-07）。キーは '格助詞\t名詞\t述語の基本形'。無ければ空。"""
    try:
        import gzip
        import json
        with gzip.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tatoeba_case.json.gz'),
                       'rt', encoding='utf-8') as f:
            return json.load(f).get('pairs') or {}
    except Exception:
        return {}


def _seen(p, noun, v):
    """その組が例文に1回でも在るか（pair_choice の表・サ変の表・1回の組の表）。"""
    return _pair_count(p, noun, v) or _case_pairs().get('\t'.join((p, noun, v)), 0)


_TEXT = ['']


def _reading(t):
    """語の読み。打った記録が在ればそれ（瘡 は解析の読み くさ だが打ったのは かさ）、無ければ解析の読み。"""
    try:
        import ime_reconvert
        text = _TEXT[0]
        if text and text[t.start:t.end] == t.surface:
            got = ime_reconvert._record_reading(text, t.start, t.end, ime_reconvert._active_record())
            if got:
                return _hira(got)
    except Exception:
        pass
    return _hira(t.reading)


def _case_marks(toks, input_method):
    """名詞＋格助詞＋述語 の選び違いを、分類ではなく組そのもので: 元の組は例文に無く、元の語（名詞か述語）が一般の文で
    稀（_rank が GEN_RARE 以上）で、同じ読みの候補のうち1つだけの組が例文に在り、その候補がはっきりよく使う語なら直す
    （紫にはしない）。CN_SEMANTIC_FIT_CASE=0 で見ない。"""
    if not _case_pairs():
        return []
    out = []
    for i, t in enumerate(toks):
        if not _noun(t):
            continue
        pv = _pred(toks, i, CASES_SEEN)
        if not pv or _seen(pv[0], t.surface, pv[1]):
            continue
        here = _rank(t.surface)
        if here < GEN_RARE:
            continue
        same, _key = _alternatives(t.surface, _reading(t), input_method)
        # 1字の語（瘡を持つ→傘）は同じ読みの語が多いので、候補の組が FIX_PAIR 回以上在るときだけ
        need = 1 if len(t.surface) >= 2 else FIX_PAIR
        hit = [a for a in same if (len(a) >= 2 or len(t.surface) == 1) and a != t.surface
               and _seen(pv[0], a, pv[1]) >= need and _rank(a) <= here - FIX_RANK_GAP]
        if len(hit) == 1:
            out.append((t.start, t.end, hit[0]))
    for j, v in enumerate(toks):
        if v.pos == '名詞' and len(v.surface) >= 2 and _verb_at(toks, j) == v.surface and _rank(v.surface) >= GEN_RARE:
            # サ変の名詞＋する（出展を健闘する→検討）: 候補は同じ読みのサ変の名詞
            here = _rank(v.surface)
            same, _key = _alternatives(v.surface, _reading(v), input_method)
            for p, n in _verb_args(toks, j):
                if _seen(p.surface, n.surface, v.surface):
                    break
                hit = [a for a in same if len(a) >= 2 and a != v.surface and _seen(p.surface, n.surface, a)
                       and _rank(a) <= here - FIX_RANK_GAP]
                if len(hit) == 1:
                    out.append((v.start, v.end, hit[0]))
                    break
            continue
        if v.pos not in ('動詞', '形容詞') or _sub(v) != '自立' or not _is_kanji(v.surface[0]):
            continue
        base = getattr(v, 'base_form', '') or v.surface
        here = _rank(base)
        if here < GEN_RARE:
            continue
        alts = _verb_alternatives(v, v.pos)
        for p, n in _verb_args(toks, j):
            if _seen(p.surface, n.surface, base):
                break
            hit = {alt: face for face, alt in alts.items()
                   if alt != base and [c for c in alt if _is_kanji(c)] != [c for c in base if _is_kanji(c)]
                   and _seen(p.surface, n.surface, alt) and _rank(alt) <= here - FIX_RANK_GAP}
            if len(hit) == 1:
                out.append((v.start, v.end, next(iter(hit.values()))))
                break
    return out


@lru_cache(maxsize=1)
def _no_pairs():
    """名詞＋の＋名詞 の組と回数（tatoeba_no.json.gz・Tatoeba の例文から数えた・1回の組も・2026-11-07）。
    'A\tB' は「A の B」。前後の名詞が続くとき（契約書・更新書類）はつないだ形も数えてある。無ければ空。"""
    try:
        import gzip
        import json
        with gzip.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tatoeba_no.json.gz'),
                       'rt', encoding='utf-8') as f:
            return json.load(f).get('pairs') or {}
    except Exception:
        return {}


def _gen_neighbours(toks, i):
    """i の名詞の「の」の相手 [(向き, 相手)]。向き '<' は 相手の名詞、'>' は 名詞の相手。相手は続く名詞をつないだ形も。"""
    def nounish(t):
        return t.pos == '名詞' and _sub(t) not in ('非自立', '代名詞', '数')
    out = []
    if i >= 2 and toks[i - 1].surface == 'の' and toks[i - 1].end == toks[i].start and nounish(toks[i - 2]):
        a = toks[i - 2].surface
        out.append(('<', a))
        if i >= 3 and nounish(toks[i - 3]) and toks[i - 3].end == toks[i - 2].start:
            out.append(('<', toks[i - 3].surface + a))
    if i + 2 < len(toks) and toks[i + 1].surface == 'の' and toks[i + 1].start == toks[i].end \
            and nounish(toks[i + 2]) and _sub(toks[i + 2]) != '接尾':
        b = toks[i + 2].surface
        out.append(('>', b))
        if i + 3 < len(toks) and nounish(toks[i + 3]) and toks[i + 3].start == toks[i + 2].end:
            out.append(('>', b + toks[i + 3].surface))
    return out


def _gen_marks(toks, input_method):
    """名詞＋の＋名詞 の選び違い（会議の資料・来週の土曜）: 元の語の組は例文に無く、同じ読みの候補のうち1つだけの組が
    例文に在り、その候補が一般の文で元の語よりはっきりよく使う語のとき直す（紫にはしない）。分類語彙表の仲間では
    決まらない組（ビジネスの語）を、組そのもので見る。CN_SEMANTIC_FIT_NO=0 で見ない。"""
    tab = _no_pairs()
    if not tab:
        return []
    out = []
    for i, t in enumerate(toks):
        if not _noun(t):
            continue
        nb = _gen_neighbours(toks, i)
        if not nb:
            continue
        def cnt(w):
            return sum(tab.get(x + '\t' + w if d == '<' else w + '\t' + x, 0) for d, x in nb)
        if cnt(t.surface):
            continue
        here = _rank(t.surface)
        if here < GEN_RARE:
            continue  # 元の語が一般の文でよく使う語（回りの人・周りの人）は表記の好みなので見ない
        same, _key = _alternatives(t.surface, _reading(t), input_method)
        need = 1 if len(t.surface) >= 2 else FIX_PAIR
        hit = [a for a in same if (len(a) >= 2 or len(t.surface) == 1) and a != t.surface and cnt(a) >= need
               and _rank(a) <= here - FIX_RANK_GAP]
        if len(hit) == 1:
            out.append((t.start, t.end, hit[0]))
    return out


def _pred_marks(toks):
    """述語の側の選び違い（環境を以降する→移行・出展を健闘する→検討）: 名詞＋格助詞＋サ変の名詞＋する で、
    名詞がそのサ変の名詞の仲間に無く（頭 MISS_DEPTH 桁でも）、同じ読みの別のサ変の名詞の仲間には在るとき。
    名詞は分類に在り、どちらの述語の仲間も例文の組で十分に在ること（借りた仲間では見ない）。"""
    out = []
    for j in range(2, len(toks)):
        v = toks[j]
        # 名詞＋する（サ変の名詞でなくてもよい: 選び違いの語は 生理・以降 のようにサ変でないことが多い）
        if not (v.pos == '名詞' and len(v.surface) >= 2 and j + 1 < len(toks) and toks[j + 1].start == v.end
                and (getattr(toks[j + 1], 'base_form', '') or toks[j + 1].surface) == 'する'
                and any(_is_kanji(c) for c in v.surface)):
            continue
        k = j - 1
        if toks[k].pos == '副詞' and k >= 2:
            k -= 1   # 趣旨をもう一度生理する
        p, n = toks[k], toks[k - 1]
        if p.pos != '助詞' or p.surface not in CASES or n.end != p.start or not _noun(n):
            continue
        if not _codes(n.surface) or _pair_count(p.surface, n.surface, v.surface):
            continue
        own = list(_by_sahen().get((p.surface, v.surface), ()))
        if _enough(own):
            prof = sahen_profile(p.surface, v.surface)
            if fit(n.surface, prof, MISS_DEPTH):
                continue
            depth = None
        elif not own:
            # そのサ変の名詞が この格助詞で例文に一度も出ない（環境を以降する・出展を健闘する）: 候補の仲間は
            # 中項目（PURPLE_DEPTH 桁）で比べる（例文の組が少なく細かい番号まで揃わないため）
            prof, depth = None, PURPLE_DEPTH
        else:
            continue
        here = _rank(v.surface)
        best = []
        for alt in _alternatives(v.surface, _hira(v.reading), 'romaji')[0]:
            if not _enough(list(_by_sahen().get((p.surface, alt), ()))):
                continue
            pa = sahen_profile(p.surface, alt)
            w = fit(n.surface, pa, depth) if pa else 0
            if w >= (1 if depth else CAND_WEIGHT) and _rank(alt) <= here + RANK_MARGIN:
                best.append((w, alt))
        if not best:
            continue
        best.sort(reverse=True)
        alt = best[0][1]
        sure = (len(best) == 1 and best[0][0] >= FIX_WEIGHT
                and (_rank(alt) <= here - FIX_RANK_GAP or _pair_count(p.surface, n.surface, alt) >= FIX_PAIR))
        if prof is not None and not sure and (fit(n.surface, prof, PURPLE_DEPTH) or best[0][0] < _VPURPLE):
            continue
        if prof is None:
            # 元の述語に例が無いときは、候補が1つで一般の文で元よりはっきりよく使う語なら直し、そうでなければ紫
            sure = len(best) == 1 and _rank(alt) <= here - FIX_RANK_GAP
        out.append((v.start, v.end, alt if sure else None))
    return out


def repair_line(line, result, decided=(), input_method='kana'):
    if not isinstance(result, dict) or not enabled():
        return result
    done = result.get('corrected') or line
    try:
        marks = propose(done, input_method)
    except Exception:
        return result
    if not marks:
        return result
    changed = [(o[3], o[4]) for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
               if o[0] != 'equal']
    odd_now = [tuple(x[:2]) for x in list(result.get('odd_spans') or ()) + list(result.get('unsure_spans') or ())]
    new = done
    odd_add, details, fixed_at = [], [], []
    for s, e, rep in sorted(marks, reverse=True):
        if any(x < e and s < y for x, y in changed):
            continue
        org = None
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, done, line, autojunk=False).get_opcodes():
            if tag == 'equal' and i1 <= s and e <= i2:
                org = (s - i1 + j1, e - i1 + j1)
        if org is None or any(x < org[1] and org[0] < y for x, y in list(decided or ())):
            continue
        if rep:
            new = new[:s] + rep + new[e:]
            details.append([done[s:e], rep, '意味の分類'])
            if len(rep) == e - s:
                fixed_at.append(org)
        elif not any(x < org[1] and org[0] < y for x, y in odd_now):
            odd_add.append(org)
    if not odd_add and new == done:
        return result
    out = dict(result)
    if fixed_at and os.environ.get('CN_SF_FIX_CLEARS_ODD') != '0':
        # 直した所に前の段の紫（入口の直しを戻した印）が残ると、直したのに紫も付いた形になる。同じ長さの直しだけ外す
        # （2026-11-09 手分けA）。CN_SF_FIX_CLEARS_ODD=0 で前のまま
        hit = lambda x: any(a < x[1] and x[0] < b for a, b in fixed_at)
        for key in ('odd_spans', 'unsure_spans'):
            if out.get(key):
                out[key] = [x for x in out[key] if not hit(x)]
        if out.get('odd_reasons'):
            out['odd_reasons'] = [r for r in out['odd_reasons'] if not hit(r)]
        odd_now = [x for x in odd_now if not hit(x)]
    if odd_add:
        out['odd_spans'] = sorted(set(odd_now) | set(odd_add))
        out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [
            (a, b, f'「{line[a:b]}」は後ろの述語と意味の分類が噛み合いません。同じ読みの別の語か、1打違いの別の語かもしれません')
            for a, b in odd_add]
    if new != done:
        ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
        out.update({'original': line, 'corrected': new, 'changed': True,
                    'details': list(result.get('details') or []) + details,
                    'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    return out


def _unit(word):
    try:
        import seed_japanese
        return bool(seed_japanese.is_unit(word))
    except Exception:
        return False


@lru_cache(maxsize=4096)
def _same_reading_parts(part, reading):
    """同じ読みの漢字だけの表記（語の部品として・品詞は問わない）。"""
    import reading_lattice
    reading_lattice.load()
    return tuple(sorted({s for s, _l, _r, _c, _pos in reading_lattice._table.get(reading, ())
                         if s != part and s and all(_is_kanji(c) for c in s)}))


def _compound_marks(toks):
    """漢字の語の続き（保証機関・私用量・再機動・点字会）が1語として辞書に無く、部品の1つを同じ読みの別の表記に
    替えると1語として在る（保証期間・使用量・再起動・展示会）とき。替え先が1つなら直し、2つ以上なら紫。
    部品は名詞・接頭詞・接尾の漢字の語。1語として在る続きは見ない。"""
    out = []
    i = 0
    while i < len(toks):
        j = i
        while j < len(toks) and toks[j].pos in ('名詞', '接頭詞') and toks[j].surface \
                and all(_is_kanji(c) for c in toks[j].surface) and _sub(toks[j]) not in ('数', '固有名詞') \
                and (j == i or toks[j].start == toks[j - 1].end):
            j += 1
        run = toks[i:j]
        if len(run) >= 2:
            whole = ''.join(t.surface for t in run)
            # 〜的 はどの名詞にも付いて辞書に載らない語を作る（野性的 は正しいのに 野生的 に替えていた）ので見ない
            if not _unit(whole) and len(whole) >= 3 and run[-1].surface != '的':
                cands = set()
                for k, t in enumerate(run):
                    # 1字の部品の替え（仕事上→仕事場・後利益→御利益・交換氏→交換子）は正しい続きも崩すので見ない。
                    # 替え先は一般の文で元の部品より稀でないこと（当時町→東寺町 にしていた）
                    if len(t.surface) < 2:
                        continue
                    # サ変の名詞＋時の接尾（操作｜中・作業｜後: 接尾の副詞可能）は、どのサ変の名詞にも付いて「〜している間・
                    # 〜の後」と正しく読める続きなので、辞書に1語として無くても名詞を替えない（2026-11-09 手分けA: 正しい文の
                    # 操作中 を 捜査中 にしていた）。物・会・量 など一般の接尾（選択物→洗濯物）は前のまま。
                    # CN_SF_COMPOUND_TIME_SUFFIX=0 で前のまま
                    if (k + 1 < len(run) and _sub(t) == 'サ変接続'
                            and (getattr(run[k + 1], 'pos_sub', '') or '') == '接尾:副詞可能'
                            and os.environ.get('CN_SF_COMPOUND_TIME_SUFFIX') != '0'):
                        continue
                    for alt in _same_reading_parts(t.surface, _hira(t.reading)):
                        if len(alt) < 2 or _rank(alt) > _rank(t.surface) + RANK_MARGIN:
                            continue
                        new = ''.join(alt if m == k else u.surface for m, u in enumerate(run))
                        if _unit(new):
                            cands.add(new)
                if cands:
                    rep = next(iter(cands)) if len(cands) == 1 else None
                    out.append((run[0].start, run[-1].end, rep))
        i = max(j, i + 1)
    return out


_ARGS = os.environ.get('CN_SF_VERB_ARGS', '1') != '0'
_ADJ = os.environ.get('CN_SEMANTIC_FIT_ADJ', '1') != '0'
_NOOWN = os.environ.get('CN_SF_VERB_NOOWN', '1') != '0'
_VPURPLE = int(os.environ.get('CN_SF_VERB_PURPLE', str(FIX_WEIGHT)) or 0)


def _verb_alternatives(t, pos='動詞'):
    """同じ読み・同じ活用形の、漢字の違う動詞（pos='形容詞' なら形容詞）の表記 → 基本形。"""
    import reading_lattice
    from morphology import dictionary_inflections
    reading_lattice.load()
    form = getattr(t, 'infl_form', '') or ''
    out = {}
    want = pos
    readings = [_hira(t.reading)]
    if os.environ.get('CN_SF_VERB_ALL_READINGS') != '0':
        # 打った読みの記録が無い行では、解析の読み（描く=えがく・放す=ほかす）だけでなく、その表記が持つ
        # ほかの読み（かく・はなす）でも同じ読みの別の表記を探す（2026-11-09 手分けA: 文章を描く→書く）
        base = getattr(t, 'base_form', '') or t.surface
        for row in dictionary_inflections(base) or ():
            if row[0].startswith(want + ',自立,') and row[1] == form and row[2] == t.surface and row[3] not in readings:
                readings.append(row[3])
    for rd in readings:
        for face, _l, _r, _c, pos in reading_lattice._table.get(rd, ()):
            if pos != want or face == t.surface or face in out or not any(_is_kanji(c) for c in face):
                continue
            if [c for c in face if not _is_kanji(c)] != [c for c in t.surface if not _is_kanji(c)]:
                continue  # かなの部分が違う候補は区切りの違い（停｜まる→止ま）
            for row in dictionary_inflections(face) or ():
                if row[0].startswith(want + ',自立,') and row[1] == form and row[3] == rd:
                    out[face] = row[2]
    return out


def _kata_noun(t):
    """片仮名だけの2字以上の名詞（メモ・ノート）。動詞の選び違いを見る組の名詞に入れる（メモを描く→書く）。
    CN_SF_KATA_ARG=0 で前のまま（漢字を含む名詞だけ）。2026-11-09 手分けA"""
    return (os.environ.get('CN_SF_KATA_ARG') != '0' and t.pos == '名詞' and len(t.surface) >= 2
            and _sub(t) not in ('非自立', '代名詞', '数', '接尾', '固有名詞')
            and all('ァ' <= c <= 'ヺ' or c == 'ー' for c in t.surface))


def _verb_args(toks, j):
    """動詞 j の前の、同じ節の 名詞＋格助詞 を近い順に（最大3つ）。副詞・「分かり＋やすく」・ほかの格の組は越える。"""
    out = []
    k = j - 1
    while k >= 1 and len(out) < 3:
        t = toks[k]
        if t.pos == '副詞' or (t.pos == '形容詞' and _sub(t) == '非自立'):
            k -= 1
            continue
        if t.pos == '動詞' and k + 1 < j and toks[k + 1].pos == '形容詞' and _sub(toks[k + 1]) == '非自立':
            k -= 1
            continue
        if t.pos != '助詞' or t.surface not in CASES + ('で', 'から', 'まで', 'より'):
            break
        n = toks[k - 1]
        if n.end != t.start:
            break
        # 助詞が動詞などに付いている（戻す｜が 効かない: 接続助詞）なら、その前の組（元に）は別の述語のもの。
        # そこで止める（2026-11-08 未解決タブの誤判定 効かない→聞かない）。CN_SF_ARGS_STOP=0 で前のまま
        # 動詞の連用形＋に（見に｜行く: 目的）は動詞 j の組の一部なので越える
        purpose = t.surface == 'に' and n.pos == '動詞' and (getattr(n, 'infl_form', '') or '').startswith('連用')
        if (((n.pos in ('動詞', '形容詞', '助動詞')) and not purpose) or (t.pos_sub or '').startswith('接続助詞')) \
                and os.environ.get('CN_SF_ARGS_STOP') != '0':
            break
        if t.surface in CASES and (_noun(n) or _kata_noun(n)) and _codes(n.surface):
            out.append((t, n))
        # 名詞の前の 数・接頭・接尾・の を越えて、さらに前の組へ
        k -= 2
        while k >= 1 and toks[k].pos == '名詞' and _sub(toks[k]) in ('数', '接尾', '一般', 'サ変接続') and toks[k].end == toks[k + 1].start:
            k -= 1
    return out


def _verb_marks(toks):
    """動詞の選び違い（コートを堕しておいた→出し・条件を捜す→探す）: 名詞＋格助詞＋動詞 で、名詞がその動詞の仲間に
    無く（頭 MISS_DEPTH 桁でも）、同じ読み・同じ活用形の別の漢字の動詞の仲間には在るとき。どちらの動詞も例文の組が
    十分に在ること（借りた仲間では見ない）。同じ節の 名詞＋格助詞 を近い順に見て、最初に決まった組で決める。"""
    out = []
    for j in range(2, len(toks)):
        v = toks[j]
        if v.pos != '動詞' or _sub(v) != '自立' or not _is_kanji(v.surface[0]):
            continue
        args = _verb_args(toks, j) if _ARGS else _verb_args(toks, j)[:1]
        for p, n in args:
            m = _verb_mark_one(v, p, n)
            if m is not None:
                if m != 'skip':
                    out.append(m)
                break
    if _ADJ:
        out += _adj_marks(toks)
    return out


class _Rel:
    surface = '連体'


def _adj_marks(toks):
    """形容詞の選び違い（篤いコート→厚い・旧い時計→古い・走るのが早い→速い）: 形容詞＋名詞（連体の組）と
    名詞＋格助詞＋形容詞 で、動詞と同じに比べる。CN_SEMANTIC_FIT_ADJ=0 で見ない。"""
    out = []
    for j in range(len(toks)):
        a = toks[j]
        if a.pos != '形容詞' or _sub(a) != '自立' or not _is_kanji(a.surface[0]):
            continue
        args = []
        nx = toks[j + 1] if j + 1 < len(toks) else None
        if nx is not None and getattr(a, 'infl_form', '') == '基本形' and nx.start == a.end and nx.pos == '名詞' \
                and _sub(nx) not in ('非自立', '代名詞', '数', '接尾') and _codes(nx.surface):
            args.append((_Rel, nx))
        args += _verb_args(toks, j)
        base = getattr(a, 'base_form', '') or a.surface
        here = _rank(base)
        alts = _verb_alternatives(a, '形容詞')
        for p, n in args:
            if _pair_count(p.surface, n.surface, base):
                break
            # 形容詞の例文の組は少ないので、分類ではなく組そのもの（旧い時計→古い時計）が在る候補だけで直す
            hit = {alt: face for face, alt in alts.items()
                   if alt != base and [c for c in alt if _is_kanji(c)] != [c for c in base if _is_kanji(c)]
                   and _pair_count(p.surface, n.surface, alt) >= 1 and _rank(alt) <= here + RANK_MARGIN}
            if len(hit) == 1:
                out.append((a.start, a.end, next(iter(hit.values()))))
                break
    return out


PAIR_OUTWEIGH = 5      # 同じ読みの別の動詞の組が、元の動詞の組のこれだけ倍以上例文に在り
PAIR_OUTWEIGH_MIN = 20 # …その組がこれだけ在るなら選び違いとして直す（絵を書く 10 回・絵を描く 80 回）


def _pair_outweighed(v, p, n, base, have):
    """元の組も例文に在るが、同じ読みの別の動詞の組がはるかに多い（絵を書く→描く）なら直す。候補は1つだけ。
    CN_SF_PAIR_OUTWEIGH=0 で前のまま（組が在れば見ない）。2026-11-09 手分けA"""
    if os.environ.get('CN_SF_PAIR_OUTWEIGH') == '0':
        return 'skip'
    here = _rank(base)
    hit = {}
    for face, alt in _verb_alternatives(v).items():
        if alt == base or [c for c in alt if _is_kanji(c)] == [c for c in base if _is_kanji(c)]:
            continue
        c = _pair_count(p.surface, n.surface, alt)
        if c >= max(PAIR_OUTWEIGH_MIN, have * PAIR_OUTWEIGH) and _rank(alt) <= here + RANK_MARGIN:
            hit[alt] = face
    if len(hit) == 1:
        return (v.start, v.end, next(iter(hit.values())))
    return 'skip'


FIT_OUTWEIGH = 3       # 元の動詞の仲間にも在るが、同じ読みの別の動詞の仲間でこれだけ倍以上の重みなら紫


SWAP_SUPPORT = 30      # 同じ読みの動詞の入れ替えを、組が例文に無くても意味の分類で支える重み


def verb_swap_supported(p, noun, old, new):
    """名詞＋助詞＋動詞 の動詞を同じ読みの別の動詞（old→new）に替えた組を、意味の分類で支えられるか。名詞の分類が new の
    仲間で SWAP_SUPPORT 以上、かつ old の仲間の FIT_OUTWEIGH 倍以上（メモを描く→書く: 0／110・文字: 12／36）。
    correction_entry._frame_guard が、例文に組の無い直しを戻す前に見る（2026-11-09 手分けA）。CN_SF_SWAP_SUPPORT=0 で使わない"""
    if os.environ.get('CN_SF_SWAP_SUPPORT') == '0' or not _codes(noun):
        return False
    pn = profile(p, new)
    if not pn or not _enough(list(_by_pred().get((p, new), ()))):
        return False
    po = profile(p, old)
    w_new = fit(noun, pn, MISS_DEPTH)
    w_old = fit(noun, po, MISS_DEPTH) if po else 0
    return w_new >= SWAP_SUPPORT and w_new >= FIT_OUTWEIGH * w_old


def _fit_outweighed(v, p, n, base, mine):
    """名詞が元の動詞の仲間にも在る（噛み合う）が、同じ読みの別の動詞の仲間ではるかに重い（文字を描く: 描く 12・
    書く 36）なら、迷う所として紫にする（直さない）。CN_SF_FIT_OUTWEIGH=0 で前のまま。2026-11-09 手分けA"""
    if os.environ.get('CN_SF_FIT_OUTWEIGH') == '0':
        return 'skip'
    if len(n.surface) == 1 and os.environ.get('CN_SF_FIT_OUTWEIGH_ONE') != '0':
        # 名詞が元の動詞の仲間に在る（元の表記で正しく読める）とき、1字の名詞（間: ま・あいだ・かん）は分類番号が多く
        # どの動詞の仲間にも重く入りやすいので、重みの比べだけでは替えない（2026-11-09 手分けA: 正しい文の 間を空ける →
        # 開ける にしていた）。CN_SF_FIT_OUTWEIGH_ONE=0 で前のまま
        return 'skip'
    here = _rank(base)
    for face, alt in _verb_alternatives(v).items():
        if alt == base or [c for c in alt if _is_kanji(c)] == [c for c in base if _is_kanji(c)]:
            continue
        if not _enough(list(_by_pred().get((p.surface, alt), ()))) or _rank(alt) > here + RANK_MARGIN:
            continue
        pa = profile(p.surface, alt)
        if pa and fit(n.surface, pa, MISS_DEPTH) >= mine * FIT_OUTWEIGH and fit(n.surface, pa) >= FIX_WEIGHT:
            # 候補が一般の文でも元の動詞より身近で、分類の重みが十分なら直す（文字を描く→書く）。ほかは紫
            sure = (os.environ.get('CN_SF_FIT_OUTWEIGH_FIX') != '0' and _rank(alt) <= here
                    and fit(n.surface, pa, MISS_DEPTH) >= SWAP_SUPPORT)
            return (v.start, v.end, face if sure else None)
    return 'skip'


STRONG_FIT = 50        # 元の動詞の仲間に（頭 MISS_DEPTH 桁でも）無く、候補の仲間でこれだけの重みなら直す


def _strong_fit(n, p, alt, prof):
    """名詞が元の動詞の仲間に無く、同じ読みの別の動詞の仲間ではっきり重い（メモを描く: 描く 0・書く 110）。
    CN_SF_STRONG_FIT=0 で前のまま。2026-11-09 手分けA"""
    if os.environ.get('CN_SF_STRONG_FIT') == '0' or prof is None or fit(n.surface, prof, MISS_DEPTH):
        return False
    pa = profile(p.surface, alt)
    return bool(pa) and fit(n.surface, pa, MISS_DEPTH) >= STRONG_FIT


def _verb_mark_one(v, p, n, pos='動詞'):
    """1つの 名詞＋格助詞 で動詞 v を見る。印 (start, end, 直し or None)、この組で元の動詞が合うなら 'skip'、
    この組では決まらないなら None。"""
    base = getattr(v, 'base_form', '') or v.surface
    have = _pair_count(p.surface, n.surface, base)
    if have:
        return _pair_outweighed(v, p, n, base, have)
    own = list(_by_pred().get((p.surface, base), ()))
    if _enough(own):
        prof, depth = profile(p.surface, base), None
        mine = fit(n.surface, prof, MISS_DEPTH)
        if mine:
            return _fit_outweighed(v, p, n, base, mine)
    elif _NOOWN and sum(c for _w, c in own) <= 1:
        # その動詞がこの格助詞で例文にほとんど出ない（コートを堕す・条件を捜す）: 候補の仲間は中項目で比べる
        prof, depth = None, PURPLE_DEPTH
    else:
        return None
    here = _rank(base)
    alts = _verb_alternatives(v, pos)
    best = []
    for face, alt in alts.items():
        if alt == base or not _enough(list(_by_pred().get((p.surface, alt), ()))):
            continue
        if [c for c in alt if _is_kanji(c)] == [c for c in base if _is_kanji(c)]:
            continue  # 送り仮名の違いだけ（現われる・現れる）は表記の揺れ
        pa = profile(p.surface, alt)
        w = fit(n.surface, pa, depth) if pa else 0
        if w >= (1 if depth else CAND_WEIGHT) and _rank(alt) <= here + RANK_MARGIN:
            best.append((w, face))
    if not best:
        return None
    best.sort(reverse=True)
    face = best[0][1]
    alt = alts[face]
    one = len({alts[f] for _w, f in best}) == 1
    sure = (one and best[0][0] >= FIX_WEIGHT
            and (_rank(alt) <= here - FIX_RANK_GAP or _pair_count(p.surface, n.surface, alt) >= FIX_PAIR
                 or _strong_fit(n, p, alt, prof)))
    if prof is not None and not sure and (fit(n.surface, prof, PURPLE_DEPTH) or best[0][0] < _VPURPLE):
        return 'skip'
    if prof is None:
        # 元の動詞に例が無いときは、候補の基本形が1つで一般の文で元よりはっきりよく使う語なら直す
        sure = one and _rank(alt) <= here - FIX_RANK_GAP
        if not sure:
            return None  # 根拠が候補の側だけのときは紫にしない（議題に上る・送れる）
    return (v.start, v.end, face if sure else None)
