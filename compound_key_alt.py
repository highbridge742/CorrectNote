# -*- coding: utf-8 -*-
"""漢字の名詞の組が辞書の1語でも身近な組でもない所（野外｜文章）を、読み（やがいぶんしょう）に戻して、かなの行と同じ
1打違いの置き直し（kana_lattice_place._key_alt: ながい文章）に掛ける（2026-11-09 手分けA）。

IME が1打違いの読みをそのまま漢字の名詞2つに変換した形は、行の珍しい語の門（ime_reconvert）に掛からない（どの語も
身近）。かなの行では同じ読みが _key_alt で直るので、漢字の行でも読みに戻して同じ決まりで見る。
- 見る所: 漢字だけの名詞（一般・サ変接続・形容動詞語幹）が2つ以上続く所。固有名詞・数・接尾は見ない。
- 読み: 打った記録、無ければ辞書の読み（ime_reconvert.typed_reverse）。
- 置き直しが元の組と違う表記になり、元の読みと違う（打ち直した）ときだけ直す。決まりは _key_alt のまま
  （名詞で終わる句・行の費用が 1000 以上よい・二番とも 1000 以上離れる）。
特定の語には合わせない。CN_COMPOUND_KEY_ALT=0 で見ない。
"""
import difflib
import os


def _on():
    return os.environ.get('CN_COMPOUND_KEY_ALT') != '0'


def _kanji(c):
    return '一' <= c <= '鿿' or c == '々'


_NOUN_SUB = ('一般', 'サ変接続', '形容動詞語幹')


def _runs(tokens):
    out, cur = [], []
    for t in tokens:
        ok = (t.pos == '名詞' and (t.pos_sub or '').split(':')[0] in _NOUN_SUB
              and t.surface and all(_kanji(c) for c in t.surface))
        if ok and (not cur or cur[-1].end == t.start):
            cur.append(t)
            continue
        if len(cur) >= 2:
            out.append(cur)
        cur = [t] if ok else []
    if len(cur) >= 2:
        out.append(cur)
    return out


def propose(text):
    if not _on() or not text:
        return []
    try:
        from morphology import tokenize
        import ime_reconvert as R
        import kana_lattice_place as K
        import learned_gate
    except Exception:
        return []
    tokens = list(tokenize(text))
    runs = _runs(tokens)
    if not runs:
        return []
    rw = R.typed_reverse(text, tokens, None)
    if not rw:
        return []
    phon, words = rw
    out = []
    for run in runs:
        s, e = run[0].start, run[-1].end
        if any(learned_gate._known_compound(p.surface + q.surface) for p, q in zip(run, run[1:])):
            continue
        ws = [w for w in words if w[0] < e and s < w[1]]
        if not ws or ws[0][0] != s or ws[-1][1] != e:
            continue
        reading = R._hira(phon[ws[0][2]:ws[-1][3]])
        if not reading or not all('ぁ' <= c <= 'ゖ' for c in reading):
            continue
        alt = text[:s] + reading + text[e:]
        try:
            places, _doubts = K.propose(alt, None, None)
        except Exception:
            continue
        mine = sorted(p for p in places if s <= p[0] and p[1] <= s + len(reading))
        if not mine or mine[0][0] != s or mine[-1][1] != s + len(reading):
            continue
        face = reading
        for a0, b0, f0 in reversed(mine):
            face = face[:a0 - s] + f0 + face[b0 - s:]
        if face == text[s:e] or not any(_kanji(c) for c in face):
            continue
        # 置き直しの表記の読みが元の読みと同じなら（同じ読みの別の表記）、打ち違いの直しではない
        try:
            rr = R.typed_reverse(face, None, None)
        except Exception:
            rr = None
        if rr and R._hira(rr[0]) == reading:
            continue
        # 元の行は IME が変換した漢字の行なので、打ち直した読みは IME の代わり（dict_ime: 辞書の表記）で変換し直す
        # （かなの行の置き方は和語の用言をかなのまま残す: ながい文章 → 長い文章）。変換し直しの語の数・切れ目が
        # 置き直しと同じときだけ
        if rr and os.environ.get('CN_COMPOUND_KEY_ALT_IME') != '0':
            try:
                import dict_ime
                conv = dict_ime._convert(R._hira(rr[0]))
            except Exception:
                conv = None
            if conv and conv[0] != face and len(conv[1]) == len(rr[1]) \
                    and all(a[3] == b[3] for a, b in zip(conv[1], rr[1])):
                face = conv[0]
        # 置き直しは 修飾の語＋名詞 の句（ながい｜文章）のときだけ。名詞の組のまま表記だけ替わる形（感想｜卵）は、
        # 打ち直しではなくかなの置き方の表記の揺れ
        try:
            ft = [t for t in tokenize(text[:s] + face + text[e:]) if s <= t.start and t.end <= s + len(face)]
        except Exception:
            ft = []
        if not ft or ft[0].pos not in ('形容詞', '動詞', '連体詞') or ft[-1].pos != '名詞':
            continue
        out.append((s, e, text[:s] + face + text[e:]))
    return out


def repair_line(line, result, decided=()):
    if not _on() or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    try:
        marks = propose(done)
    except Exception:
        return result
    if not marks:
        return result
    ops = difflib.SequenceMatcher(None, done, line, autojunk=False).get_opcodes()
    changed = [(o[1], o[2]) for o in ops if o[0] != 'equal']

    def overlaps(a, b, spans):
        return any(x < b and a < y for x, y in spans)
    for s, e, other in marks:
        if overlaps(s, e, changed):
            continue
        org = None
        for tag, i1, i2, j1, j2 in ops:
            if tag == 'equal' and i1 <= s and e <= i2:
                org = (s - i1 + j1, e - i1 + j1)
        if org is None or overlaps(org[0], org[1], list(decided or ())):
            continue
        sops = [o for o in difflib.SequenceMatcher(None, done, other, autojunk=False).get_opcodes() if o[0] != 'equal']
        new = done[:sops[0][1]] + other[sops[0][3]:sops[-1][4]] + done[sops[-1][2]:]
        out = dict(result)
        d = len(new) - len(done)
        for key in ('odd_spans', 'unsure_spans'):
            if out.get(key):
                out[key] = [((x[0] + d, x[1] + d) if x[0] >= e else (x[0], x[1])) + tuple(x[2:])
                            for x in out[key] if not (x[0] < e and s < x[1])]
        if out.get('odd_reasons'):
            out['odd_reasons'] = [((r[0] + d, r[1] + d) if r[0] >= e else (r[0], r[1])) + tuple(r[2:])
                                  for r in out['odd_reasons'] if not (r[0] < e and s < r[1])]
        lops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
        out.update({'original': line, 'corrected': new, 'changed': True,
                    'details': list(result.get('details') or []) + [
                        [done[sops[0][1]:sops[-1][2]], other[sops[0][3]:sops[-1][4]], '打ち違い']],
                    'spans': [[o[3], o[4]] for o in lops], 'original_spans': [[o[1], o[2]] for o in lops]})
        return out
    return result
