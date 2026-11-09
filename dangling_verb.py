# -*- coding: utf-8 -*-
"""後ろに て・た の続かない音便形の動詞（くだい・置い）を、抜けたかな1字を足して直す（2026-10-26・未解決 くだい）。

    提案してみてくだい。 → 提案してみてください。

動詞の連用タ接続（イ音便・撥音便・促音便: 砕い・休ん・待っ）は、後ろに て／で／た／だ（たり・たら・ても…）が続いて
初めて文になる。続かないなら、どこかの1字が抜けている（打ち落とし）。その動詞の中か直後に、かな1字を足した形のうち、
足した後に同じ形が残らず、その辺りの語が全部読みを持つものを行の費用（morphology.path_cost）で並べる。
一番が二番より MARGIN 以上軽ければそれに置き、並べば紫（迷うなら紫）。語を名指しした表は持たない。
"""
import difflib
import os

MARGIN = 1000
_FOLLOW = ('て', 'で', 'た', 'だ', 'たり', 'だり', 'ちゃ', 'じゃ', 'たら', 'だら', 'ても', 'でも')
# 〜ておく の縮まった形（やっとく・置いといて・読んどいた・見とかない・書いときます・しとけ・やっとこう）も音便の後ろの形
# （2026-11-05 うに「縮まった形が抜けていたなら同じようなパターンがあるかもしれない」）。CN_DANGLING_TOKU=0 で前のまま
_TOKU = tuple(h + t for h in 'とど' for t in 'くいかきけこ')
if __import__('os').environ.get('CN_DANGLING_TOKU') != '0':
    _FOLLOW = _FOLLOW + _TOKU
_KANA = tuple(chr(c) for c in range(0x3041, 0x3094) if chr(c) not in 'ぁぃぅぇぉゎゐゑ')


def dangling(text):
    from morphology import tokenize
    return [(t.start, t.end) for t in tokenize(text)
            if t.pos == '動詞' and t.infl_form == '連用タ接続' and not text[t.end:].startswith(_FOLLOW)
            and not _inside_kana_word(text, t.start, t.end) and not _exclaim_tsu(text, t.start, t.end)]


def _exclaim_tsu(text, s, e):
    """かなだけの語の終わりの っ のすぐ後ろが文の終わり（！？。・行末）なら、言い切りを強める っ（あいたっ！・
    みじけっ。・うわっ！）で、抜けた字は無い（2026-11-08 補正担当: 正しい文 あいたっ！ → あいたあっ）。
    漢字の動詞（待っ！）は前のまま見る。CN_DANGLING_EXCLAIM=0 で前のまま。"""
    if os.environ.get('CN_DANGLING_EXCLAIM') == '0' or not text[s:e].endswith('っ'):
        return False
    if not all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in text[s:e]):
        return False
    nxt = text[e:e + 1]
    return nxt == '' or nxt in '！!？?。…～〜'


def _inside_kana_word(text, s, e):
    """かなの音便形（ほっ）が、後ろのかなとつないで辞書の名詞の読み（ほっかいどう）の頭になっているか。かなだけの行を
    解析が 動詞＋… と切っただけで、抜けた字は無い（2026-11-06 脱字の試しのスレッド: ほっかいどう→ほっとかいどう）。
    CN_DANGLING_KANA_WORD=0 で前のまま。"""
    import os
    if os.environ.get('CN_DANGLING_KANA_WORD') == '0':
        return False
    if not all('ぁ' <= c <= 'ゖ' for c in text[s:e]):
        return False
    try:
        import reading_lattice
        reading_lattice.load()
    except Exception:
        return False
    j = e
    while j < len(text) and 'ぁ' <= text[j] <= 'ゖ':
        j += 1
    for jj in range(j, e, -1):
        if any(pos == '名詞' and len(text[s:jj]) >= 3 for _s, _l, _r, _c, pos in reading_lattice._table.get(text[s:jj], ())):
            return True
    return False


def _noun_join(text, s):
    """動詞と読まれた所の頭の漢字を名詞の読みで読み、後ろのかなとつなぐと辞書の名詞の1語になる形（空＋いろ → そらいろ
    → 空色）→ (開始, 終了, 語, '読みのつなぎ') か None。IME が読みの途中までを漢字にした跡で、字を足さずに説明が付く。
    つないだ語が一般の文章に在る語（ime_reconvert の表）で、1つに決まるときだけ。2026-10-31"""
    try:
        import reading_lattice
        import ime_reconvert
        from morphology import tokenize
        reading_lattice.load()
    except Exception:
        return None
    def kanji(ch):
        return '一' <= ch <= '鿿' or ch == '々'
    k = s
    while k < len(text) and kanji(text[k]):
        k += 1
    if k == s:
        # 動詞の前の漢字の名詞（役＋いん → やくいん → 役員）
        while s > 0 and kanji(text[s - 1]):
            s -= 1
    head = text[s:k]
    if not head:
        return None
    toks = list(tokenize(head))
    if len(toks) != 1 or toks[0].pos != '名詞' or not toks[0].reading:
        return None
    r0 = ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in toks[0].reading)
    j = k
    while j < len(text) and 'ぁ' <= text[j] <= 'ゖ':
        j += 1
    found = set()
    end = None
    for jj in range(j, k, -1):
        faces = {surf for surf, _l, _r, _c, pos in reading_lattice._table.get(r0 + text[k:jj], ())
                 if pos == '名詞' and surf.startswith(head) and ime_reconvert._rank(surf) < 800}
        if faces:
            found, end = faces, jj
            break
    if len(found) != 1:
        return None
    return (s, end, found.pop(), '読みのつなぎ')


def propose(text):
    """[(開始, 終了, 置く文字列 or None)]（text の位置）。"""
    from morphology import tokenize, path_cost
    found = dangling(text)
    if not found:
        return []
    out = []
    s, e = found[0]
    if text[s] == 'っ' and os.environ.get('CN_DANGLING_SOKUON') != '0':
        # 語の頭の っ（行頭・記号や漢字の後ろ）は、前に字を足しても説明にならない（っ注文した→まっ注文した は5件とも誤り、
        # 2026-11-06 ローマ字の試しのスレッド）。字は足さず紫。CN_DANGLING_SOKUON=0 で前のまま
        return [(s, e, None)]
    joined = _noun_join(text, s)
    if joined is not None:
        return [joined]
    cands = []
    for p in range(s, e + 1):
        for h in _KANA:
            t = text[:p] + h + text[p:]
            if dangling(t):
                continue
            if not all(x.has_reading for x in tokenize(t) if x.end > s and x.start < e + 1):
                continue
            c = path_cost(t)
            if c is not None:
                cands.append((c, t))
    cands.sort()
    if cands and (len(cands) == 1 or cands[1][0] - cands[0][0] >= MARGIN):
        out.append((s, e, cands[0][1][s:e + 1]))
    else:
        out.append((s, e, None))
    return out


def repair_line(line, result, decided=()):
    if not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    try:
        marks = propose(done)
    except Exception:
        return result
    if not marks:
        return result
    changed = [(o[3], o[4]) for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
               if o[0] != 'equal']
    odd_now = [tuple(x[:2]) for x in list(result.get('odd_spans') or ()) + list(result.get('unsure_spans') or ())]
    s, e, rep = marks[0][:3]
    label = marks[0][3] if len(marks[0]) > 3 else '抜けた1字'
    if any(x < e and s < y for x, y in changed):
        return result
    org = None
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, done, line, autojunk=False).get_opcodes():
        if tag == 'equal' and i1 <= s and e <= i2:
            org = (s - i1 + j1, e - i1 + j1)
    if org is None or any(x < org[1] and org[0] < y for x, y in list(odd_now) + list(decided or ())):
        return result
    out = dict(result)
    if rep is None:
        out['odd_spans'] = sorted(set(odd_now) | {org})
        out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [
            (org[0], org[1], f'「{line[org[0]:org[1]]}」の後ろに続くはずの て・た がありません')]
        return out
    new = done[:s] + rep + done[e:]
    ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out.update({'original': line, 'corrected': new, 'changed': True,
                'details': list(result.get('details') or []) + [[done[s:e], rep, label]],
                'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    return out
