# -*- coding: utf-8 -*-
"""覚えた語がかなの欄の紫を消した所を見直す段（learned_gate・手分けA・2026-11-01）。

かな入力の行で、初めの状態なら読みの通らない所として紫になるかなの欄が、本人の語彙で立った語（同梱の語彙では
立っていない語）があるために、同じ読みのまま漢字の語に変換されて紫が消えることがある。覚えた語が正しい語でも、
その欄の打つつもりの語とは限らない（学習で補正を悪くしない・うに 10-22）。

次が全部そろうときだけ、その欄の変換を採らずに打ったかなに戻して紫にする（後ろの段が紫の所の打ち違いとして見る）:
  - 前の段（素の補正）がかなの欄を、読みを替えずに漢字の語へ変換した（打ったかなと変換した形の読みが同じ）。
  - その中の名詞が覚えた語（語彙で立っていて、同梱の語彙 base_vocab では立っていない）。
  - その語と隣の名詞の組（覚えた語＋隣の名詞・隣の名詞＋覚えた語）が、同梱の辞書（seed_japanese・SudachiDict の見出し）の
    1語でも、一般の文での使われやすさの表（ja_wordfreq）の語でもない。
  - 覚えた語の読みに1打違いの別の読みがあり、それが同梱の語彙で立った語の読み（一般によく使う語として通る）。
組が辞書の1語として在る所（覚えた語＋隣の名詞で1つの複合語）は通す。覚えた語の行をまるごと紫にはしない。
特定の語や文字列には合わせない。かな入力だけ。
"""
import difflib

_BASE = None


def _base():
    """同梱の語彙で立っている (読み, 表記) と、立っている語の読み。"""
    global _BASE
    if _BASE is None:
        try:
            import vocabulary
            rows = vocabulary.load_base_rows()
        except Exception:
            rows = []
        pairs = {(r[0], r[1]) for r in rows if len(r) > 4 and r[4]}
        _BASE = (pairs, {p[0] for p in pairs})
    return _BASE


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s or '')


def _is_hira(s):
    return bool(s) and all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in s)


def _kanji_word(s):
    return bool(s) and all('一' <= c <= '鿿' or c == '々' for c in s)


def _reading(text):
    from morphology import tokenize
    out = []
    for t in tokenize(text):
        if not t.has_reading and not _is_hira(t.surface):
            return None
        out.append(_hira(t.reading or t.surface))
    return ''.join(out)


def _learned(store, reading, surface):
    pairs, _ = _base()
    if (reading, surface) in pairs:
        return False
    try:
        ents = store.lookup(reading) or ()
    except Exception:
        return False
    return any(e.get('surface') == surface and e.get('solid') for e in ents)


def _known_compound(face):
    import seed_japanese
    import ime_reconvert
    unit = seed_japanese.is_unit(face)
    if unit is None:
        return True       # 辞書が無ければ意見なし（通す）
    return bool(unit) or ime_reconvert._rank(face) < 800


def _other_common_reading(reading, before, after):
    from contextual_repair import key_repairs
    _, readings = _base()
    for r in key_repairs(reading, before, after):
        r = getattr(r, 'reading', r)
        if r and r != reading and r in readings:
            return r
    return None


def _split(toks, typed, store):
    """変換した欄の語を、打ったかなの読みに割り当てる [(語, 読み)]。語の読みは解析の読みと語彙の読み。合わなければ None。"""
    def cands(t):
        out = []
        for r in (_hira(t.reading) if t.has_reading else '', _hira(t.surface) if _is_hira(t.surface) else ''):
            if r and r not in out:
                out.append(r)
        try:
            r = store.reading_of(t.surface)
        except Exception:
            r = None
        if r and r not in out:
            out.append(r)
        return out

    def go(k, pos):
        if k == len(toks):
            return [] if pos == len(typed) else None
        for r in cands(toks[k]):
            if typed.startswith(r, pos):
                rest = go(k + 1, pos + len(r))
                if rest is not None:
                    return [(toks[k], r)] + rest
        return None
    return go(0, 0)


def propose(line, done, store):
    """[(done の開始, 終了, 戻すかな)]。"""
    from morphology import tokenize
    if not done or line == done:
        return []
    out = []
    alltoks = list(tokenize(done))
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes():
        if tag != 'replace':
            continue
        typed = line[i1:i2]
        if not _is_hira(typed):
            continue
        toks = [t for t in alltoks if j1 <= t.start and t.end <= j2]
        if not toks or toks[0].start != j1 or toks[-1].end != j2:
            continue
        parts = _split(toks, typed, store)
        if parts is None:
            continue      # 読みを替えた直しは見ない（読みを替えずに変換しただけの欄）
        for k, (t, rd) in enumerate(parts):
            if t.pos != '名詞' or not _kanji_word(t.surface):
                continue
            if not _learned(store, rd, t.surface):
                continue
            nbrs = [parts[x][0] for x in (k - 1, k + 1) if 0 <= x < len(parts)]
            nbrs = [m for m in nbrs if m.pos == '名詞' and _kanji_word(m.surface)]
            if not nbrs:
                continue
            faces = [(m.surface + t.surface) if m.end <= t.start else (t.surface + m.surface) for m in nbrs]
            if any(_known_compound(f) for f in faces):
                continue
            if not _other_common_reading(rd, line[:i1][-1:], line[i2:][:1]):
                continue
            out.append((j1, j2, typed))
            break
    return out


def _moved(spans, marks):
    """前の紫の位置を、戻した欄の長さの差だけずらす（戻した欄に掛かる紫は戻した欄の紫にまとめる）。"""
    out = []
    for a, b in spans:
        if any(a < e and s < b for s, e, _k in marks):
            continue
        d = sum(len(k) - (e - s) for s, e, k in marks if e <= a)
        out.append((a + d, b + d))
    return out


def repair_line(line, result, store, decided=(), input_method='kana'):
    if not isinstance(result, dict) or input_method != 'kana' or store is None:
        return result
    done = result.get('corrected') or line
    try:
        marks = propose(line, done, store)
    except Exception:
        return result
    if not marks:
        return result
    new = done
    for s, e, kana in sorted(marks, reverse=True):
        new = new[:s] + kana + new[e:]
    ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    if any(x < o[2] and o[1] < y for o in ops for x, y in (decided or ())):
        return result
    # 戻した欄を紫に（new の上の位置）
    odd = []
    shift = 0
    for s, e, kana in sorted(marks):
        odd.append((s + shift, s + shift + len(kana)))
        shift += len(kana) - (e - s)
    gone = {done[s:e] for s, e, _k in marks}
    out = dict(result)
    out.update({'corrected': new, 'changed': new != line,
                'details': [d for d in (result.get('details') or []) if not (len(d) > 1 and d[1] in gone)],
                'odd_spans': sorted(set(_moved(result.get('odd_spans') or (), marks)) | set(odd)),
                'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    return out
