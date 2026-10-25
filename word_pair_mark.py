# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""
語の組の印（補正担当・2026-10-25。うにさん 11:58Z「語の組の印」）。

IME が別の語を選んだ型（待ち外の補正・鳥のこされない）は、1語ずつ見ると辞書にある語なので、ほかの補正は通す。
ここでは隣り合う語の「組」を見る。
  (A) 漢字の名詞＋漢字の接尾（待ち＋外・変＋場）が、つないだ形では辞書（分類語彙表・同梱辞書・身近さの表）の
      どこにも無い造語で、つないだ読みが身近な1語（間違い・返上）になる。
  (B) 漢字の名詞＋格助詞＋かな1〜2字の動詞（鳥＋の＋こさ）の読みをつなぐと、辞書の動詞の活用形
      （取り残さ）になる。
置くのは、候補が1つに決まるときだけ。書き方の違い（子供向け↔子ども向け: 元の漢字が候補に順に全部在る）は組ではない
ので触らない。置いた所は紫（迷うなら紫・2026-10-18）。特定の語を名指ししない。
ほかの補正が触った所と、本人が「直さない」と決めた所には触らない。
"""
import difflib

MAX_VERB_KANA = 2      # (B) の動詞のかなの長さ
FAMILIAR_TIER = 2      # 置く語の身近さ（kango_tier.known_usage_tier）の上限

_H = {chr(c): chr(c - 0x60) for c in range(0x30A1, 0x30F7)}


def _hira(s):
    return s.translate(str.maketrans(_H))


def _kanji_any(s):
    return any('一' <= c <= '鿿' or c == '々' for c in s)


def _kana_all(s):
    return bool(s) and all('ぁ' <= c <= 'ゖ' for c in s)


def _variant(surf, face):
    """元の漢字が候補に順に全部在る（見積書↔見積もり書）＝同じ語の書き方の違い。"""
    it = iter(face)
    return all(any(c == k for k in it) for c in surf if _kanji_any(c))


def _tier_ok(face):
    try:
        import kango_tier as K
        t = K.known_usage_tier(face)
    except Exception:
        return True
    return (t or 3) <= FAMILIAR_TIER


def _faces_a(surf, rd, dict_index):
    import semantic_class as S
    pool = []
    for fn in (dict_index.surfaces_for_reading, dict_index.inflected_surfaces_for_reading, S.words_read):
        try:
            pool += list(fn(rd) or ())
        except Exception:
            pass
    return sorted({f for f in pool if f != surf and _kanji_any(f) and S.codes(f)
                   and not _variant(surf, f) and _tier_ok(f)})


def _faces_b(surf, rd, dict_index):
    try:
        pool = dict_index.inflected_surfaces_for_reading(rd) or ()
    except Exception:
        return []
    return sorted({f for f in pool if f != surf and _kanji_any(f) and not _variant(surf, f)})


def propose(text, dict_index):
    """[(start, end, 候補の並び)]。候補が複数の所も返す（置くかは呼ぶ側）。"""
    if dict_index is None:
        return []
    try:
        import morphology
        import semantic_class as S
        import kango_tier as K
        toks = list(morphology.tokenize(text))
    except Exception:
        return []
    out = []
    for i in range(len(toks) - 1):
        a, b = toks[i], toks[i + 1]
        if not (a.has_reading and b.has_reading and a.end == b.start and a.pos == '名詞'):
            continue
        if (a.pos_sub or '').startswith(('数', '副詞可能')) or (b.pos_sub or '').startswith('数'):
            continue
        if not _kanji_any(a.surface):
            continue
        if b.pos == '名詞' and (b.pos_sub or '').startswith('接尾') and _kanji_any(b.surface):
            surf = a.surface + b.surface
            if S.codes(surf) or K.known_usage_tier(surf) is not None:
                continue
            faces = _faces_a(surf, _hira(a.reading + b.reading), dict_index)
            if faces:
                out.append((a.start, b.end, faces))
        elif b.pos == '助詞' and (b.pos_sub or '').startswith('格助詞') and i + 2 < len(toks):
            c = toks[i + 2]
            if not (c.has_reading and c.pos == '動詞' and c.start == b.end and _kana_all(c.surface)
                    and len(c.surface) <= MAX_VERB_KANA):
                continue
            surf = a.surface + b.surface + c.surface
            faces = _faces_b(surf, _hira(a.reading + b.reading + c.reading), dict_index)
            if faces:
                out.append((a.start, c.end, faces))
    return out


def _to_original(line, done, s, e):
    """done の [s, e) を line の位置に戻す（その範囲はほかの補正が触っていない所）。"""
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, done, line, autojunk=False).get_opcodes():
        if tag == 'equal' and i1 <= s and e <= i2:
            return s - i1 + j1, e - i1 + j1
    return None


def repair_line(line, result, store, dict_index, decided=()):
    """result: ほかの補正の答え。ほかの補正が触っていない所の語の組だけ見る。候補1つなら置いて紫、複数なら紫だけ。"""
    if not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    try:
        marks = propose(done, dict_index)
    except Exception:
        return result
    if not marks:
        return result
    changed = [(o[3], o[4]) for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
               if o[0] != 'equal']
    odd_now = [tuple(x[:2]) for x in list(result.get('odd_spans') or ()) + list(result.get('unsure_spans') or ())]
    new = done
    odd_add, details = [], []
    for s, e, faces in sorted(marks, reverse=True):
        if any(x < e and s < y for x, y in changed):
            continue
        org = _to_original(line, done, s, e)
        if org is None or any(x < org[1] and org[0] < y for x, y in list(odd_now) + list(decided or ())):
            continue
        if len(faces) == 1:
            new = new[:s] + faces[0] + new[e:]
            details.append([done[s:e], faces[0], '語の組'])
        odd_add.append(org)
    if not odd_add:
        return result
    out = dict(result)
    out['odd_spans'] = sorted(set(odd_now) | set(odd_add))
    out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [
        (a, b, f'「{line[a:b]}」は隣の語とつなぐと別の語の読みです') for a, b in odd_add]
    if new != done:
        ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
        out.update({'original': line, 'corrected': new, 'changed': True,
                    'details': list(result.get('details') or []) + details,
                    'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    return out
