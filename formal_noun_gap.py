# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""
形式名詞（こと・もの・ところ など、品詞の細かい分けが 非自立）のすぐ後ろに、助詞を挟まず漢字の一般の名詞が来て、
その名詞のすぐ後ろに用言（動詞・形容詞）が続く所に紫を付ける段（formal_noun_gap・2026-11-01）。

形式名詞は の・が・は・を などの助詞か、断定（だ・です）で受けるのが普通で、名詞が直に続いて用言に掛かる形
（〜こと＋名詞＋あります）は、助詞が脱字のまま IME が別の語に変換した所のことが多い。直し先は決まらないので紫。
やること一覧・することリスト（名詞のまま終わる・片仮名の語）と、副詞のように働く形式名詞（非自立:副詞可能）は見ない。特定の語や文字列には合わせない。
"""


def _kanji(c):
    return '一' <= c <= '鿿' or c == '々'


def spans(text):
    from morphology import tokenize
    toks = list(tokenize(text))
    out = []
    for i in range(len(toks) - 2):
        a, b, c = toks[i], toks[i + 1], toks[i + 2]
        # 副詞のように働く形式名詞（品詞の細かい分けが 非自立:副詞可能: 〜限り・〜とおり・〜ため）は、後ろに
        # 名詞＋用言が直に続くのが普通の形（できる限り＋努力＋する）。助詞で受ける形式名詞だけを見る
        if not (a.pos == '名詞' and (a.pos_sub or '') == '非自立:一般'):
            continue
        if not (b.pos == '名詞' and (b.pos_sub or '') in ('一般', 'サ変接続') and b.surface
                and all(_kanji(ch) for ch in b.surface)):
            continue
        if c.pos not in ('動詞', '形容詞'):
            continue
        out.append((b.start, b.end))
    return out


def repair_line(line, result, decided=()):
    if not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done != line:
        return result
    try:
        found = spans(done)
    except Exception:
        return result
    odd_now = [tuple(x[:2]) for x in list(result.get('odd_spans') or ()) + list(result.get('unsure_spans') or ())]
    add = [sp for sp in found if not any(x < sp[1] and sp[0] < y for x, y in odd_now + list(decided or ()))]
    if not add:
        return result
    out = dict(result)
    out['odd_spans'] = sorted(set(tuple(x[:2]) for x in (result.get('odd_spans') or ())) | set(add))
    out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [
        (a, b, '「こと・もの」などのすぐ後ろに名詞が続いています（助詞が抜けたかもしれません）') for a, b in add]
    return out
