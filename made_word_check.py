# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""
前の段がかなを漢字の語に直してできた形が、まだ文として通らない所は、その直しを採らず元のかなに戻して紫にする段
（made_word_check・2026-11-01・うに 08:29Z「〜での が変なので、次へ送って脱字に到達できるよう」）。

見る形（品詞と分類語彙表の分類番号だけで見る。特定の語は名指ししない）:
  - 直してできた語が、感覚・感情・知る・気付くの動きの名詞（サ変接続で、分類番号が 1.3001〜1.3003・1.3062）で、すぐ後ろが
    格助詞の で＋連体の の（〜での）。〜での は場所・手段・場面を受ける形で、知覚・認識の動きは受けない
    （聞いてわかる形は 〜して・〜した）。
隣のキーの打ち違いで直した形が通らないときは、ほかの戻し（脱字＝字を足す戻し）が書くつもりの形のことが多いが、
元のかなに1字足した読みが、本人の語（単語帳・覚えた語）か辞書の1語（身近さの門を通る表記）になり、その表記が
1つに決まるならそれに直す（本人の語が在れば本人の語だけで決める。語は組み合わせでなく1語として引く・うに 11:30Z）。
決まらなければ直しを採らずに紫にして、書いた人に見せる（決めるか紫・うに 10-18）。
直した所だけを見る（本人がそのまま書いた語は見ない）。
"""
import difflib

# 感覚（1.3001）・感情の動き（1.3002）・眠り（1.3003）・知る・気付く（1.3062）。選ぶ・計算・調べる・判断・決める
# （1.3063〜1.3067: 計算での誤り・審査での指摘）は 〜での で受けるのが普通なので入れない
_MENTAL = ('1.3001', '1.3002', '1.3003', '1.3062')


def _mental_action(t):
    if t.pos != '名詞' or (t.pos_sub or '') != 'サ変接続':
        return False
    try:
        import semantic_class
        cs = semantic_class.codes(t.surface)
    except Exception:
        return False
    return bool(cs) and all(c.startswith(_MENTAL) for c in cs)


def _reading(text):
    try:
        from morphology import tokenize
        return ''.join(_hira(t.reading or t.surface) for t in tokenize(text))
    except Exception:
        return None


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


def _bad_spans(text):
    """[(start, end)] text の中の 知覚・認識の動きの名詞＋での の名詞の所。"""
    from morphology import tokenize
    toks = list(tokenize(text))
    out = []
    for i in range(len(toks) - 2):
        a, b, c = toks[i], toks[i + 1], toks[i + 2]
        if b.surface == 'で' and b.pos == '助詞' and c.surface == 'の' and c.pos == '助詞' and _mental_action(a):
            out.append((a.start, a.end))
    return out


_KANA = [chr(c) for c in range(ord('ぁ'), ord('ゖ') + 1)] + ['ー']


def _dropped_word(orig, store, dict_index):
    """orig（かな）に1字足すと1語になる表記。1つに決まれば (表記, 読み)、決まらなければ None。"""
    if store is None or len(orig) < 2:
        return None
    try:
        import last_keystroke as LK
        import kana_lattice_place as K
        import ime_reconvert
    except Exception:
        return None
    own, common = {}, {}
    for i in range(len(orig) + 1):
        for k in _KANA:
            r = orig[:i] + k + orig[i:]
            if r in own or r in common:
                continue
            try:
                faces, mine = K._everyday_faces(r, store, dict_index, LK)
            except Exception:
                continue
            mine = [f for f in faces if f in mine]
            if mine:
                own[r] = mine[0]
                continue
            usual = [f for f in faces if ime_reconvert._rank(f) <= K.COMMON_FACE]
            if len(usual) == 1:
                common[r] = usual[0]
    pick = own if own else common
    faces = set(pick.values())
    if len(faces) != 1:
        return None
    r, f = next(iter(pick.items()))
    return f, r


def repair_line(line, result, decided=(), store=None, dict_index=None):
    if not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done == line:
        return result
    try:
        bad = _bad_spans(done)
    except Exception:
        return result
    if not bad:
        return result
    ops = [o for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes() if o[0] != 'equal']
    new = done
    odd_add = []
    undo = []
    fixed_add = []
    for tag, i1, i2, j1, j2 in sorted(ops, key=lambda o: o[3], reverse=True):
        if not any(j1 < y and x < j2 for x, y in bad):
            continue
        orig = line[i1:i2]
        # かなを漢字の語にした直しだけ（本人の書いた漢字を替えた直しは見ない）
        if not orig or not all('ぁ' <= ch <= 'ゖ' or ch == 'ー' for ch in orig):
            continue
        if any(x < i2 and i1 < y for x, y in (decided or ())):
            continue
        # 読みを変えずに漢字にしただけの所（りかい → 理解）は打ち違いの直しではない。見ない
        if _reading(done[j1:j2]) == orig:
            continue
        dropped = _dropped_word(orig, store, dict_index)
        if dropped is not None:
            face = dropped[0]
            new = new[:j1] + face + new[j2:]
            undo.append((done[j1:j2], face))
            fixed_add.append([orig, face, '脱字'])
            continue
        new = new[:j1] + orig + new[j2:]
        undo.append((done[j1:j2], orig))
        odd_add.append((i1, i2))
    if new == done:
        return result
    out = dict(result)
    ops2 = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out.update({'corrected': new, 'changed': new != line,
                'details': [d for d in (result.get('details') or []) if not any(len(d) > 1 and d[1] == w for w, _o in undo)]
                + fixed_add,
                'spans': [[o[3], o[4]] for o in ops2], 'original_spans': [[o[1], o[2]] for o in ops2]})
    # 紫の所は元の行の位置（odd_spans は line の位置で持つ）。戻した所のほかの紫・迷いはそのまま
    if not odd_add:
        return out
    out['odd_spans'] = sorted(set(tuple(x[:2]) for x in (result.get('odd_spans') or ())) | set(odd_add))
    out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [
        (a, b, '直すと「〜での」の形が通らないので、直し先を決めていません（字が抜けたのかもしれません）') for a, b in odd_add]
    return out
