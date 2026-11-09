# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""
かなで書いた和語を、そのまま漢字に変えない段（kana_keep・補正担当・2026-11-01）。

うにさん 11-01 02:46Z: ひらがな・おもちゃ・あたりに・あたり・ずれ・ちいさい・おしえる・むすめ・ものさし・ひとつ は
「ひらがなのまま漢字にしなくてよいもの」。10-31 03:06Z「かなだけの行も、漢字にするべき部分は漢字に」の対象は
しょくじけん・変換ちゅう・でんわばんごう のような漢語。

決め手は語の成り立ち（語種）: 漢字の表記の字がどれも音読み（kanji_onkun.is_on_reading）で読める語（漢語:
電話・番号・食事・変換中）は漢字にする。訓読み・熟字訓・送り仮名の付く語（和語: 平仮名・玩具（おもちゃ）・辺り・
小さい・教える・娘・物差し・一つ）と、平仮名の和語を片仮名にしただけの形（ずれ→ズレ）は、かなで書いても自然なので、打ち違いを直したのではなく読みをそのまま漢字に
変えただけの所は、元のかなに戻す。打ち違いを直した所（読みが替わった所）は触らない。特定の語は名指ししない。
"""
import difflib
import os


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s or '')


def _is_hira(s):
    return bool(s) and all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in s)


def _kanji(c):
    return '一' <= c <= '鿿' or c == '々'


_VOICE = str.maketrans('かきくけこさしすせそたちつてとはひふへほ', 'がぎぐげござじずぜぞだぢづでどばびぶべぼ')
_HALF = str.maketrans('はひふへほ', 'ぱぴぷぺぽ')


def _kata(c):
    return 'ァ' <= c <= 'ヶ' or c == 'ー'


def native_katakana(face, reading):
    """片仮名だけの表記で、読みが和語（活用する語の形: ずれる の ずれ）か。外来語（てれび・こんぴゅーた）は False。"""
    if not face or not all(_kata(c) for c in face):
        return False
    try:
        import reading_lattice
        reading_lattice.load()
        rows = reading_lattice._table.get(reading, ())
    except Exception:
        return False
    # 片仮名の表記がよく使われ、同じ読みの漢字の表記（名詞の 御簾・動詞の 見す）はどれもめったに使わない語（ミス）は
    # 外来語（2026-11-04・にゅうりょくみす が 入力みす に戻っていた）
    if os.environ.get('CN_KANA_KEEP_LOAN_RANK') != '0':
        try:
            import ime_reconvert as _R
            kf = [row[0] for row in rows if row and row[0] and any(_kanji(c) for c in row[0])]
            if 0 < _R._rank(face) <= 470 and (not kf or min(_R._rank(f) for f in kf) > 650):
                return False
        except Exception:
            pass
    # 同じ読みに動詞・形容詞（活用する語＝和語）の行が在るもの（ずれる の ずれ）。名詞だけの読み（てれび・ぱそこん）は外来語
    if any(len(row) > 4 and row[4] in ('動詞', '形容詞') for row in rows):
        return True
    # 同じ読みの名詞に、平仮名の表記と漢字だけの表記が両方在るもの（うどん・饂飩、たばこ・煙草）は、平仮名で書くのが
    # 普通の語。片仮名にしない（2026-11-03 うに 未解決タブ「補正しなくてよい」）。漢字の表記の無い名詞（てれび・ぱそこん）は外来語
    if os.environ.get('CN_KANA_KEEP_KANJI_FACE') != '0':
        names = [row for row in rows if len(row) > 4 and row[4] == '名詞']
        kanji_faces = [row[0] for row in names if row[0] and all(_kanji(c) for c in row[0])]
        if any(row[0] == reading for row in names) and kanji_faces:
            return True
    return False


def _variants(r):
    """音読みの連濁・半濁・促音の形（番→ばん・ぱん、一→いっ）。"""
    out = {r}
    if r:
        out.add(r[0].translate(_VOICE) + r[1:])
        out.add(r[0].translate(_HALF) + r[1:])
        if r[-1] in 'つちくき':
            out.add(r[:-1] + 'っ')
    return out


def is_kango(face, reading):
    """表記の漢字がどれも音読みで、かなの字はそのままで、読みをちょうど言い切れるか。漢字の無い表記は False。"""
    import kanji_onkun as K
    if not face or not reading or not any(_kanji(c) for c in face):
        return False
    if any(not _kanji(c) for c in face):
        return False      # 送り仮名・かなの混ざる表記（小さい・物差し）は和語
    memo = {}

    def go(i, j):
        if i == len(face):
            return j == len(reading)
        key = (i, j)
        if key in memo:
            return memo[key]
        ok = False
        ch = face[i]
        cands = set()
        for r in K.readings_of(ch):
            if K.is_on_reading(ch, r):
                cands |= _variants(r)
        for r in cands:
            if r and reading.startswith(r, j) and go(i + 1, j + len(r)):
                ok = True
                break
        memo[key] = ok
        return ok
    return go(0, 0)


_SAHEN_TAIL = tuple('しじせぜすずさざ')


def is_kango_sahen(face, reading):
    """漢字1字の音読み＋サ変の活用の字（察し・適し・感じ: 察する・適する・感じる）か。字は音読みで、かなは活用の字
    だけなので漢語（漢字に）。音読みは2字の読み（さっ・てき・かん）だけ（1字の け は 消す の語幹と同じ形）。
    CN_KANA_KEEP_SAHEN=0 で前のまま（2026-11-08 手分けA）。"""
    if os.environ.get('CN_KANA_KEEP_SAHEN') == '0':
        return False
    if not face or len(face) < 2 or not _kanji(face[0]) or any(_kanji(c) for c in face[1:]):
        return False
    tail = face[1:]
    if tail[0] not in _SAHEN_TAIL or not reading.endswith(tail) or len(reading) - len(tail) < 2:
        return False
    return is_kango(face[0], reading[:-len(tail)])


def _reading(text):
    from morphology import tokenize
    out = []
    for t in tokenize(text):
        if _is_hira(t.surface):
            out.append(t.surface)
        elif t.has_reading and t.reading:
            out.append(_hira(t.reading))
        else:
            return ''
    return ''.join(out)


def _conversions(line, fixed):
    """[(元の開始, 元の終わり, 直した開始, 直した終わり)]: かなの並びを、読みを替えずに漢字の語にしただけの所。
    語の区切り（解析の語）まで広げる（あたり→辺り は あた｜り の り が同じ字として残る）。"""
    from morphology import tokenize
    toks = list(tokenize(fixed))
    out = []
    ops = difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes()
    # 送り仮名を挟んで1語の中で替わった所（とりたて → 取り立て: と→取・た→立 の2つの替え）は1つにまとめて見る。
    # 分けて見ると語の区切りまで広げた所が元の行と合わず、和語の名詞が漢字のまま残っていた（2026-11-09 うにの未解決タブ）。
    # CN_KANA_KEEP_JOIN_OKURI=0 で前のまま
    if os.environ.get('CN_KANA_KEEP_JOIN_OKURI') != '0':
        joined = []
        for o in ops:
            if o[0] == 'equal':
                joined.append(o)
                continue
            if (len(joined) >= 2 and joined[-1][0] == 'equal' and joined[-2][0] == 'replace' and o[0] == 'replace'
                    and _is_hira(line[joined[-1][1]:joined[-1][2]])
                    and any(t.start < joined[-2][4] and joined[-2][3] < t.end and t.start < o[4] and o[3] < t.end
                            for t in toks)):
                p = joined[-2]
                joined[-2:] = [('replace', p[1], o[2], p[3], o[4])]
                continue
            joined.append(o)
        ops = joined
    for tag, i1, i2, j1, j2 in ops:
        if tag != 'replace' or not any(_kanji(c) or _kata(c) for c in fixed[j1:j2]):
            continue
        cover = [t for t in toks if t.end > j1 and t.start < j2]
        if not cover:
            continue
        s, e = min(t.start for t in cover), max(t.end for t in cover)
        # 広げた分は元の行と同じ字（equal の所）でなければならない
        if line[i1 - (j1 - s):i1] != fixed[s:j1] or line[i2:i2 + (e - j2)] != fixed[j2:e]:
            continue
        a, b = i1 - (j1 - s), i2 + (e - j2)
        if a < 0 or not _is_hira(line[a:b]):
            continue
        if _reading(fixed[s:e]) != line[a:b]:
            continue          # 読みが替わった所＝打ち違いの直し。触らない
        # 漢字の語と片仮名の語が続けて置かれた所（にゅうりょくみす → 入力ミス）は語ごとに見る。まとめて見ると
        # 漢語＋外来語の並びが漢語にならず、漢語の所までかなに戻っていた（2026-11-04）
        if len(cover) > 1 and os.environ.get('CN_KANA_KEEP_PER_WORD') != '0':
            parts, at, ok = [], a, True
            for t in cover:
                rd = _reading(t.surface) if any(_kanji(c) or _kata(c) for c in t.surface) else t.surface
                if not rd or line[at:at + len(rd)] != rd:
                    ok = False
                    break
                if rd != t.surface:
                    parts.append((at, at + len(rd), t.start, t.end))
                at += len(rd)
            if ok and at == b and parts and any(all(_kata(c) for c in fixed[x:y]) for _p, _q, x, y in parts):
                out.extend(parts)
                continue
        out.append((a, b, s, e))
    return out


def wago_kana_respell(line, fixed):
    """かなで打った所を打ち違いとして読みごと直したとき（くたせさい→下さい）、直した語が和語なら漢字にせずかなで書く
    （くださいと打つ人は ください と書く・かなのままでよいのは和語 2026-11-01 うに）。漢語（電話）は漢字のまま。"""
    import os
    if os.environ.get('CN_RESPELL_WAGO_KANA') == '0' or not fixed or fixed == line:
        return fixed
    from morphology import tokenize
    toks = list(tokenize(fixed))
    new = fixed
    for tag, i1, i2, j1, j2 in sorted(difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes(),
                                      key=lambda o: o[3], reverse=True):
        if tag != 'replace' or not _is_hira(line[i1:i2]) or not any(_kanji(c) for c in fixed[j1:j2]):
            continue
        cover = [t for t in toks if t.end > j1 and t.start < j2]
        if not cover:
            continue
        s, e = min(t.start for t in cover), max(t.end for t in cover)
        if line[i1 - (j1 - s):i1] != fixed[s:j1] or line[i2:i2 + (e - j2)] != fixed[j2:e]:
            continue
        a, b = i1 - (j1 - s), i2 + (e - j2)
        if a < 0 or not _is_hira(line[a:b]):
            continue
        rd = _reading(fixed[s:e])
        if not rd or rd == line[a:b]:
            continue          # 読みを替えない漢字化は repair_line の受け持ち
        try:
            if is_kango(fixed[s:e], rd):
                continue
        except Exception:
            continue
        new = new[:s] + rd + new[e:]
    return new


def repair_line(line, result, decided=()):
    if not isinstance(result, dict):
        return result
    fixed = result.get('corrected') or line
    if fixed == line:
        return result
    try:
        convs = _conversions(line, fixed)
    except Exception:
        return result
    back = []
    for a, b, s, e in convs:
        if any(x < b and a < y for x, y in (decided or ())):
            continue
        try:
            face = fixed[s:e]
            if all(_kata(c) for c in face):
                if not native_katakana(face, line[a:b]):
                    continue
            elif is_kango(face, line[a:b]) or is_kango_sahen(face, line[a:b]):
                continue
        except Exception:
            continue
        back.append((a, b, s, e))
    if not back:
        return result
    new = fixed
    for a, b, s, e in sorted(back, key=lambda x: x[2], reverse=True):
        new = new[:s] + line[a:b] + new[e:]
    out = dict(result)
    out['corrected'] = new
    ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out['changed'] = bool(ops)
    out['spans'] = [[o[3], o[4]] for o in ops]
    out['original_spans'] = [[o[1], o[2]] for o in ops]
    # 戻したかなの語の位置（戻した後の行の位置）と戻す前の行。後ろの段（文の形の守り）が、戻したかなの和語の名詞
    # （ひるごはん）を説明の付かない並びと見て直しを丸ごと戻さないよう渡す（2026-11-06）
    try:
        pos, off = [], 0
        for a, b, s, e in sorted(back, key=lambda x: x[2]):
            pos.append((s + off, s + off + (b - a)))
            off += (b - a) - (e - s)
        out['_kana_kept'] = (fixed, pos)
    except Exception:
        pass
    kept = {fixed[s:e] for _a, _b, s, e in back}
    out['details'] = [d for d in (result.get('details') or []) if not (len(d) > 1 and d[1] in kept)]
    return out
