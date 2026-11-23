# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""打った平仮名を別の読みに書き換えた所に、同じくらい語として切れる別の直し方があれば、書き換えを採らずに紫にする。

なぜ
----
間違った書き換えは紫より悪い（うにの決まり）。2026-11-21 補正担当の作り例（150 文・1948 行と新しい 40 文・600 行）で、
打ち違いの文節を別の「実在する語」に替える書き換え（ひにと → ひなと・えこまで → えごまで・へおから → ほおから）が
間違った書き換えの多くを占めた。替えた先も語なので「語で切れるか」では止まらない。Fable 5.2 の意見: 元の文節に別の種類の
直し（隣の2字の入れ替え・隣のキー1字）を当て、採った形がはっきり勝っていなければ迷ったら紫。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む（かな入力の行だけ）。
1. 答えの読み（解析の読み）を打った行と比べ、読みの替わった所（隣り合う違いは1つにまとめる）ごとに、
   採った形（打った行のその所だけ替えた行）の格子（reading_lattice.best）の費用を出す。
2. 同じ所（前後1字を含む）に、隣の2字の入れ替え・隣のキー1字（距離 1.05 以内）の直しを1つ当てた行を作り、格子で
   切れるもの（浮いた ゛゜ の残る形は除く）の一番軽い費用と比べる。打ったままの形（その所を替えない形）も比べる
   （打った所がそのまま語で切れるなら書き換えない。CN_RIVAL_TYPED=0 で外す）。
3. 採った形が格子で切れないか、別の直し方の方が軽い所が1つでもあれば、打った行に戻し、その所と他の書き換えの所を紫にする。
切り替え: CN_RIVAL_EXIT_GUARD=0 で前のまま。MARGIN は採った形が勝つべき差。特定の語や文字列には合わせない。
"""
import difflib
import functools
import os

MARGIN = -3000  # 別の形が採った形よりこれだけ軽い時だけ迷いと見る（2026-11-22: うにの画面で -500 は正しい直し（タブ・奥行固定・最大化ほか）を戻した。-3000 は作り例で直った行を失わず、誤りの止めは 41行中8・98行中30）
_orig = {}
_KT = {c: c - 0x60 for c in range(0x30A1, 0x30F7)}
_WHY = '別の直し方とも読めるので、書き換えずに残しました。打ち違いかもしれません'


def _hira(c):
    return 'ぁ' <= c <= 'ゖ' or c == 'ー'


def _reading(text):
    from morphology import tokenize
    return ''.join((t.reading if t.has_reading else t.surface) for t in tokenize(text)).translate(_KT)


def _cost(text, memo):
    if text not in memo:
        import reading_lattice as lat
        r = lat.best(text)
        memo[text] = None if r is None or not r.words else r.cost
    return memo[text]


def _particle_at(text, p):
    """格子がその並びの p の字を1字の助詞と読むか"""
    import reading_lattice as lat
    r = lat.best(text)
    if r is None or not r.words:
        return False
    at = 0
    for _face, rd, pos, _ed in r.words:
        if at == p and len(rd) == 1:
            return pos == '助詞'
        at += len(rd)
        if at > p:
            return False
    return False


def _particle_swap(chosen, t):
    """採った形と別の形の違いが、同じ所の1字の助詞どうし（を と へ）だけか。行の切れ目の前など前後の語が少ない所では
    格子は助詞の違いを決められないので、補正の選びに任せる（返事を を 返事へ と比べて戻さない）"""
    if len(chosen) != len(t):
        return False
    diff = [i for i in range(len(t)) if chosen[i] != t[i]]
    return len(diff) == 1 and _particle_at(chosen, diff[0]) and _particle_at(t, diff[0])


def _rivals(line, a, b):
    import kana_layout as KL
    out = set()
    for i in range(max(0, a - 1), min(len(line) - 1, b + 1)):
        if _hira(line[i]) and _hira(line[i + 1]) and line[i] != line[i + 1]:
            out.add(line[:i] + line[i + 1] + line[i] + line[i + 2:])
    for i in range(max(0, a - 1), min(len(line), b + 1)):
        if not _hira(line[i]):
            continue
        for ch, _d in KL.nearby_candidates(line[i], max_dist=1.05, include_phonetic=False):
            if ch != line[i]:
                out.add(line[:i] + ch + line[i + 1:])
    return out


def regions(line, rd):
    ops = [o for o in difflib.SequenceMatcher(None, line, rd, autojunk=False).get_opcodes() if o[0] != 'equal']
    mg = []
    for tg, a, b, c, d in ops:
        if mg and a - mg[-1][1] <= 1 and c - mg[-1][3] <= 1:
            mg[-1] = (mg[-1][0], b, mg[-1][2], d)
        else:
            mg.append((a, b, c, d))
    return mg


def _toks(text):
    """[(読みの始め, 終わり, 表記)] 答えの語ごとの、読みの上の所"""
    from morphology import tokenize
    out, at = [], 0
    for t in tokenize(text):
        r = (t.reading if t.has_reading else t.surface).translate(_KT)
        out.append((at, at + len(r), t.surface))
        at += len(r)
    return out


def _misread(line, a, b, c, d, toks):
    """読みの違いが、答えの漢字の語を解析が別の読みで読んだだけ（洗濯物の 物 を ぶつ）か。その語の所の打ったかなを
    読みの表で引き、同じ表記があれば読み違い（1字の漢字は字の読みの表でも引く。CN_RIVAL_KANJI_READING=0 で外す）"""
    if toks is None:
        return False
    import reading_lattice as lat
    for s, e, face in toks:
        if s <= c and d <= e and e > s and any('一' <= ch <= '鿿' for ch in face):
            lo, hi = a - (c - s), b + (e - d)
            if lo < 0 or hi > len(line):
                return False
            lat.load()
            if any(row[0] == face for row in lat._table.get(line[lo:hi], ())):
                return True
            # 1字の漢字は字の読みの表でも引く（誤 を あやま と読んだ時の ご。格子の表に1字の音読みが無いことがある）
            if len(face) == 1 and os.environ.get('CN_RIVAL_KANJI_READING') != '0':
                import kanji_readings
                return line[lo:hi] in (kanji_readings.readings_of(face) or ())
            return False
    return False


def doubtful(line, rd, memo=None, out_text=None):
    """[(a, b)] 打った行の、別の直し方に負ける（または格子で切れない）書き換えの所"""
    memo = {} if memo is None else memo
    out = []
    toks = _toks(out_text) if out_text else None
    for a, b, c, d in regions(line, rd):
        if _misread(line, a, b, c, d, toks):
            continue
        # 打った行の漢字・片仮名など（IME が置いた表記）の所は読みの比べが当てにならないので見ない
        if any(not (_hira(ch) or ch in '゛゜') for ch in line[max(a - 1, 0):b + 1]):
            continue
        # 費用は答えの読み全体（漢字の所は解析の読み）で測る。別の直し方は、打った行のその所（前後1字を含む）だけを
        # 替えて答えの読みに差し込む。IME が置いた漢字の混じる行も、かなの並びとして前後のつながりで比べられる
        pa, pb = max(a - 1, 0), min(b + 1, len(line))
        qa, qb = c - (a - pa), d + (pb - b)
        if qa < 0 or qb > len(rd) or rd[qa:c] != line[pa:a] or rd[d:qb] != line[b:pb]:
            continue
        chosen = rd
        c0 = _cost(chosen, memo)
        if c0 is None:
            out.append((a, max(b, a + 1)))
            continue
        # 打ったままの形も競う形に入れる（打った所がそのまま語で切れるなら書き換えない）。助詞どうしの除外はしない
        if os.environ.get('CN_RIVAL_TYPED') != '0' and not any(q in line[pa:pb] for q in '゛゜'):
            t = rd[:qa] + line[pa:pb] + rd[qb:]
            ct = _cost(t, memo)
            if t != chosen and ct is not None and ct < c0 + MARGIN:
                out.append((a, max(b, a + 1)))
                continue
        for t in _rivals(line, a, b):
            if any(q in t[max(0, a - 2):b + 2] for q in '゛゜'):
                continue
            t = rd[:qa] + t[pa:pb] + rd[qb:]
            if t == chosen or (os.environ.get('CN_RIVAL_PARTICLE_SWAP') != '0' and _particle_swap(chosen, t)):
                continue
            ct = _cost(t, memo)
            if ct is not None and ct < c0 + MARGIN:
                out.append((a, max(b, a + 1)))
                break
    return out


def _map_spans(out_text, line, spans):
    """答えの上の所を打った行の上の所へ（字の並べで。揃わない所はその塊の端へ）"""
    ops = difflib.SequenceMatcher(None, out_text, line, autojunk=False).get_opcodes()

    def pos(p, end):
        for tg, a, b, c, d in ops:
            if a <= p < b or (end and a < p <= b):
                if tg == 'equal':
                    return c + (p - a)
                return d if end else c
        return len(line) if end else 0
    res = []
    for x in spans or ():
        s, e = pos(x[0], False), pos(x[1], True)
        if s < e:
            res.append((s, e) + tuple(x[2:]))
    return res


def guard(line, result):
    if os.environ.get('CN_RIVAL_EXIT_GUARD') == '0' or not isinstance(result, dict):
        return result
    out = result.get('corrected') or line
    if out == line or not any(_hira(c) for c in line):
        return result
    try:
        rd = _reading(out)
        if rd == line:
            return result
        bad = doubtful(line, rd, out_text=out)
        if not bad:
            return result
        allr = [(a, max(b, a + 1)) for a, b, _c, _d in regions(line, rd)
                if all(_hira(ch) or ch in '゛゜' for ch in line[a:b])]
        kept = [x for x in _map_spans(out, line, result.get('odd_spans'))
                if not any(x[0] < e and s < x[1] for s, e in allr)]
        kwhy = [x for x in _map_spans(out, line, result.get('odd_reasons'))
                if not any(x[0] < e and s < x[1] for s, e in allr)]
    except Exception:
        return result
    back = dict(result)
    back.update({'corrected': line, 'changed': False, 'spans': [], 'original_spans': [], 'details': []})
    back.pop('unsure_spans', None)
    odd = [tuple(x[:2]) for x in kept]
    why = [tuple(x) for x in kwhy]
    for s, e in allr:
        odd.append((s, e))
        why.append((s, e, _WHY if (s, e) in bad else '直し先を決められず元の語に戻しました。打ち違いかもしれません'))
    back['odd_spans'] = sorted(set(odd))
    back['odd_reasons'] = why
    return back


def correct_line(line, store, *a, **k):
    r = _orig['correct_line'](line, store, *a, **k)
    if os.environ.get('CN_RIVAL_EXIT_GUARD') == '0' or not isinstance(line, str):
        return r
    im = k.get('input_method', a[2] if len(a) > 2 else 'kana')
    if im != 'kana':
        return r
    return guard(line, r)


def install():
    if _orig or os.environ.get('CN_RIVAL_EXIT_GUARD') == '0':
        return bool(_orig)
    import correction_entry
    _orig['correct_line'] = correction_entry.correct_line
    functools.update_wrapper(correct_line, _orig['correct_line'])
    correction_entry.correct_line = correct_line
    return True


def uninstall():
    if not _orig:
        return
    import correction_entry
    correction_entry.correct_line = _orig.pop('correct_line')
