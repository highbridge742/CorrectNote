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
**ローマ字の隣り合う2打の入れ替わり（英字が残らない形）**を、打鍵の単位で戻す（2026-10-23・ローマ字入力だけ）。

asakara を saakara と打つと さあから になり、英字は残らない。かなの1字の戻しでは届かず、語彙の読みを見る
romaji_window_match は初期状態の語彙（約400読み）に日常の語が無いので働かない。ここでは打った読みを
ローマ字の打鍵に戻し（ヘボン式・訓令式の両方、ん は n と nn の両方）、隣り合う2打を入れ替えた読みのうち、
かなの並びとして自然になるもの（読みの3連・辞書の語の並び）を候補にする。
"""
from cache_limits import size as _cache_size   # 控えの上限は cache_limits で1か所に（2026-10-24）
from functools import lru_cache

_BASE = {
    'あ': 'a', 'い': 'i', 'う': 'u', 'え': 'e', 'お': 'o',
    'か': 'ka', 'き': 'ki', 'く': 'ku', 'け': 'ke', 'こ': 'ko', 'が': 'ga', 'ぎ': 'gi', 'ぐ': 'gu', 'げ': 'ge', 'ご': 'go',
    'さ': 'sa', 'し': ('shi', 'si'), 'す': 'su', 'せ': 'se', 'そ': 'so', 'ざ': 'za', 'じ': ('ji', 'zi'), 'ず': 'zu',
    'ぜ': 'ze', 'ぞ': 'zo', 'た': 'ta', 'ち': ('chi', 'ti'), 'つ': ('tsu', 'tu'), 'て': 'te', 'と': 'to',
    'だ': 'da', 'ぢ': 'di', 'づ': 'du', 'で': 'de', 'ど': 'do', 'な': 'na', 'に': 'ni', 'ぬ': 'nu', 'ね': 'ne', 'の': 'no',
    'は': 'ha', 'ひ': 'hi', 'ふ': ('fu', 'hu'), 'へ': 'he', 'ほ': 'ho', 'ば': 'ba', 'び': 'bi', 'ぶ': 'bu', 'べ': 'be',
    'ぼ': 'bo', 'ぱ': 'pa', 'ぴ': 'pi', 'ぷ': 'pu', 'ぺ': 'pe', 'ぽ': 'po', 'ま': 'ma', 'み': 'mi', 'む': 'mu',
    'め': 'me', 'も': 'mo', 'や': 'ya', 'ゆ': 'yu', 'よ': 'yo', 'ら': 'ra', 'り': 'ri', 'る': 'ru', 'れ': 're', 'ろ': 'ro',
    'わ': 'wa', 'を': 'wo', 'ー': '-',
}
_YOON = {'ゃ': 'a', 'ゅ': 'u', 'ょ': 'o'}
_YOON_HEAD = {'き': 'ky', 'ぎ': 'gy', 'し': ('sh', 'sy'), 'じ': ('j', 'zy'), 'ち': ('ch', 'ty'), 'に': 'ny', 'ひ': 'hy',
              'び': 'by', 'ぴ': 'py', 'み': 'my', 'り': 'ry'}


def _alts(v):
    return v if isinstance(v, tuple) else (v,)


def _units(kana):
    """かな → 打鍵の単位の並び（各単位はヘボン式・訓令式の綴りの組）。読めない字があれば None。"""
    out = []
    i = 0
    while i < len(kana):
        c = kana[i]
        n = kana[i + 1] if i + 1 < len(kana) else ''
        if n in _YOON and c in _YOON_HEAD:
            out.append(tuple(h + _YOON[n] for h in _alts(_YOON_HEAD[c])))
            i += 2
            continue
        if c == 'っ':
            out.append(('*',))       # 次の子音を重ねる
            i += 1
            continue
        if c == 'ん':
            out.append(('n', 'nn'))
            i += 1
            continue
        if c not in _BASE:
            return None
        out.append(_alts(_BASE[c]))
        i += 1
    return out


def _spellings(kana, limit=8):
    """かな → ローマ字の綴り（ヘボン式だけ・訓令式だけ・ん の n／nn）。"""
    units = _units(kana)
    if units is None:
        return []
    out = []
    for style in (0, 1):
        for nn in (0, 1):
            s = ''
            for k, u in enumerate(units):
                if u == ('*',):
                    nxt = units[k + 1] if k + 1 < len(units) else None
                    if not nxt or nxt == ('*',) or nxt[0][0] in 'aiueon-':
                        return out
                    s += (nxt[min(style, len(nxt) - 1)])[0]
                    continue
                if u == ('n', 'nn'):
                    # n と nn の両方（入れ替わりで n が母音の前に動くと ni→in のように ん が出来る）
                    s += 'nn' if nn else 'n'
                    continue
                s += u[min(style, len(u) - 1)]
            if s not in out:
                out.append(s)
    return out[:limit]


_KEYS_BY_LEN = None


def _to_kana(romaji):
    """halfwidth.romaji_to_kana と同じ読み方（同じ子音2つは っ・長い綴りから）。表を字の数ごとの辞書にして引く
    （元の関数は位置ごとに表の全部を順に照らすので、何千もの戻しを読むと打った直後の補正が遅くなる）。"""
    global _KEYS_BY_LEN
    import halfwidth
    if _KEYS_BY_LEN is None:
        table = halfwidth.ROMAJI_TO_KANA
        _KEYS_BY_LEN = (table, sorted({len(k) for k in table}, reverse=True))
    table, lens = _KEYS_BY_LEN
    s = romaji.lower()
    out = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch in ' \t\n':
            out.append(ch)
            i += 1
            continue
        if i + 1 < n and ch == s[i + 1] and ch.isalpha() and ch not in 'aiueon':
            out.append('っ')
            i += 1
            continue
        for k in lens:
            key = s[i:i + k]
            if len(key) == k and key in table:
                out.append(table[key])
                i += k
                break
        else:
            out.append(ch)
            i += 1
    return ''.join(out)


def _to_kanas(romaji):
    """ローマ字 → かな。nn＋母音 は ん＋母音 と ん＋な行（n＋n母音: ennni の打ち方）の両方に読む。"""
    out = {_to_kana(romaji)}
    i = romaji.find('nn')
    while i >= 0:
        if i + 2 < len(romaji) and romaji[i + 2] in 'aiueo':
            # 1つ目の n を ん、2つ目を な行の子音として読む（'n' 'n'+母音: 単独の n を ん にするため、間に ' を入れる）
            out.add(_to_kana(romaji[:i] + "n'" + romaji[i + 1:]).replace("'", ''))
        i = romaji.find('nn', i + 1)
    return out


@lru_cache(maxsize=_cache_size(4096))
def swap_readings(kana):
    """打った読み → 隣り合う2打を入れ替えて戻した読みの集合（英字の残らないものだけ）。"""
    out = set()
    for sp in _spellings(kana):
        for i in range(len(sp) - 1):
            if sp[i] == sp[i + 1]:
                continue
            t = sp[:i] + sp[i + 1] + sp[i] + sp[i + 2:]
            for k in _to_kanas(t):
                if k and k != kana and all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in k):
                    out.add(k)
    return frozenset(out)


_LETTERS = 'aiueoknstmhyrwgzdbpjcf'


@lru_cache(maxsize=_cache_size(4096))
def rival_readings(kana):
    """打った読み → 入れ替わりでない1打の打ち違い（1打多い・1打抜け）を戻した読みの集合。入れ替わりの戻しと
    比べるためのもの（せえんたく は e の2度押しで、入れ替えると え選択 のような別の並びになる）。"""
    out = set()
    for sp in _spellings(kana):
        for i in range(len(sp)):
            for t in (sp[:i] + sp[i + 1:],) + tuple(sp[:i] + c + sp[i:] for c in _LETTERS):
                for k in _to_kanas(t):
                    if k and k != kana and all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in k):
                        out.add(k)
        for c in _LETTERS:
            for k in _to_kanas(sp + c):
                if k and k != kana and all('ぁ' <= ch <= 'ゖ' or ch == 'ー' for ch in k):
                    out.add(k)
    return frozenset(out)


def _kana(c):
    return 'ぁ' <= c <= 'ゖ' or c == 'ー'


def _regions(line, toks, odd, dict_index):
    """紫の範囲ごとに、戻しを試す所 (始まり, 終わり, 打った読み)。IME の確定の文節か、かなの並び。"""
    from last_keystroke import _ime_clauses
    clauses = [(s, e, r) for s, e, r, _f in _ime_clauses(line, toks, dict_index)]
    out = []
    for a, b in odd:
        cover = [c for c in clauses if c[0] < b and a < c[1]]
        # 文節ごとに先に試し、文節をつないだ形は後に（つなぐと、打ち違いの無い文節 弟の まで読みに戻ってしまう）
        for c in sorted(cover, key=lambda c: (c[1] - c[0], c[0])):
            out.append(c)
        if len(cover) > 1:
            s = min(c[0] for c in cover)
            e = max(c[1] for c in cover)
            # 文節が連なっていなければ使わない（間にかなの切れ端があれば、かなのまま足す）
            typed = ''
            pos = s
            for c in sorted(cover):
                if c[0] < pos:
                    continue
                gap = line[pos:c[0]]
                if not all(_kana(ch) for ch in gap):
                    typed = None
                    break
                typed += gap + c[2]
                pos = c[1]
            if typed:
                out.append((s, e, typed))
            continue
        s, e = a, b
        while s > 0 and _kana(line[s - 1]):
            s -= 1
        while e < len(line) and _kana(line[e]):
            e += 1
        if e > s and all(_kana(ch) for ch in line[s:e]):
            out.append((s, e, line[s:e]))
    return out


def _explained(text, s, e):
    """戻した読みの所が語として読めるか: 読みの無い字句・打ち違いの跡の印（1字のかなの自立語・名詞に付いた
    動詞の付属 など: last_keystroke._suspect_tokens）が掛からないこと。"""
    import morphology
    from last_keystroke import _suspect_tokens
    toks = list(morphology.tokenize(text))
    spots = _suspect_tokens(toks)
    for i, t in enumerate(toks):
        if t.end <= s or t.start >= e:
            continue
        if not t.has_reading or i in spots:
            return False
    return True


def _rough_line(line, s, e, cand, store, dict_index):
    if store is None or dict_index is None:
        return None
    try:
        from last_keystroke import _rough_convert
        return line[:s] + _rough_convert(cand, store, dict_index) + line[e:]
    except Exception:
        return None


def _min_cost(*texts):
    costs = [c for c in (_cost(t) for t in texts if t) if c is not None]
    return min(costs) if costs else None


def _cost(text):
    import morphology
    return morphology.path_cost(text)


def _rough_is_whole_words(line, s, e, rough):
    """粗い変換の漢字が、行の上でも語の切れ目に収まるか（確認＋下 のように、付属の し を漢字の語 下 にしていないか）。
    漢字を含む字句が、読みを持ち、かなの付属を漢字にした1字の語でないこと。"""
    import morphology
    text = line[:s] + rough + line[e:]
    end = s + len(rough)
    for t in morphology.tokenize(text):
        if t.end <= s or t.start >= end or not any('一' <= c <= '鿿' for c in t.surface):
            continue
        if not t.has_reading or t.start < s or t.end > end:
            return False
    if any('ァ' <= c <= 'ヶ' for c in rough):
        # かなの読みを片仮名の語（ノイズ）にした形は使わない
        return False
    for t in morphology.tokenize(text):
        if t.end <= s or t.start >= end or not any('一' <= c <= '鿿' for c in t.surface):
            continue
        if len(t.surface) == 1 and t.pos != '動詞' and t.pos != '形容詞':
            # 1字の漢字の名詞（下・都）は、かなの付属や切れ端を粗く漢字にした形がほとんど
            return False
        if all('一' <= c <= '鿿' for c in t.surface):
            # 漢字だけの語は身近の表にある語だけを置く（かよう → 歌謡 のような身近でない語はかなのまま）
            import kango_tier
            if kango_tier.known_usage_tier(t.surface) != 1:
                return False
    return True


def _rival_wins(line, s, e, r, y0, c0, best_y, best_c, store, dict_index):
    import yomigram
    t = line[:s] + r + line[e:]
    gy = yomigram.logp_parts(t)[0] - y0
    if gy <= 0:
        return False
    if gy < best_y:
        c = _cost(t)
        if c is None or c0 - c < best_c:
            c = _min_cost(t, _rough_line(line, s, e, r, store, dict_index))
            if c is None or c0 - c < best_c:
                return False
    return _explained(t, s, s + len(r))


def find(line, odd, store=None, dict_index=None):
    """ローマ字の入れ替わりの戻し → [(始まり, 終わり, 置く字, 理由)]。紫の範囲の中だけを見る。"""
    import morphology
    import yomigram
    toks = list(morphology.tokenize(line))
    out = []
    done = []
    for s, e, typed in _regions(line, toks, odd, dict_index):
        if len(typed) < 2 or any(a < e and s < b for a, b in done):
            continue
        if any(a < e and s < b and any('一' <= ch <= '鿿' for ch in line[a:max(a, s)] + line[min(b, e):b])
               for a, b in odd):
            # 掛かる紫の範囲が、この所の外の漢字まで及ぶなら戻さない。打ち違いの跡がその漢字の側にもある
            # （強い舞った の 強い だけを 医師 にする・簿湯院 の 院 だけを に にする）。外がかな（助詞 の など）だけならよい
            continue
        base_line = line[:s] + typed + line[e:]
        y0 = yomigram.logp_parts(base_line)[0]
        # 語の並びの費用は、元の行（IME の顔）とかなに戻した行の安い方と比べる。かなだけの並びは辞書が細かく
        # 切って高く見える（じゆうけんきゅう → じ＋ゆう＋けん…）ので、戻した側も粗く漢字にした形と安い方で比べる
        c0 = _min_cost(line, base_line)
        if c0 is None:
            continue
        rows = []
        for cand in swap_readings(typed):
            t = line[:s] + cand + line[e:]
            c = _min_cost(t, _rough_line(line, s, e, cand, store, dict_index))
            if c is None:
                continue
            gy, gc = yomigram.logp_parts(t)[0] - y0, c0 - c
            if gy > 0 and gc > 0 and _explained(t, s, s + len(cand)):
                rows.append((gy, gc, cand))
        if not rows:
            continue
        # 読みの並びも語の並びも良くなる戻しのうち、両方で一番のものに決める。両方で一番が別なら決めない（紫のまま）
        by_y = max(rows, key=lambda r: (r[0], r[1]))
        by_c = max(rows, key=lambda r: (r[1], r[0]))
        if by_y[2] != by_c[2]:
            continue
        cand = by_y[2]
        # 1打多い・1打抜けの戻しのほうが、読みの並びか語の並びで同じか良いなら、入れ替わりとは決めない
        best_y, best_c = by_y[0], by_y[1]
        rivals = rival_readings(typed) - swap_readings(typed)
        if any(_rival_wins(line, s, e, r, y0, c0, best_y, best_c, store, dict_index) for r in rivals):
            continue
        face = cand
        if store is not None and dict_index is not None:
            try:
                from last_keystroke import _rough_convert
                rough = _rough_convert(cand, store, dict_index)
                cr, ck = _cost(line[:s] + rough + line[e:]), _cost(line[:s] + cand + line[e:])
                if (rough != cand and cr is not None and ck is not None and cr < ck
                        and _rough_is_whole_words(line, s, e, rough)):
                    face = rough
            except Exception:
                pass
        out.append((s, e, face, 'ローマ字の隣り合う2打の入れ替わり（%s → %s）' % (typed, cand)))
        done.append((s, e))
    return out


def apply(line, result, input_method='kana', store=None, dict_index=None, decisions=None):
    """ローマ字入力の行で、紫の範囲の入れ替わりを戻した直しを足す。前の直しが無い行だけ。"""
    if input_method != 'romaji' or not line or (result.get('corrected') or line) != line:
        return result
    odd = [tuple(x[:2]) for x in (result.get('odd_spans') or ())]
    if not odd:
        return result
    try:
        from last_keystroke import _protected
        guard = _protected(line, decisions)
    except Exception:
        guard = ()
    try:
        found = [f for f in find(line, odd, store, dict_index)
                 if not any(a < f[1] and f[0] < b for a, b in guard)]
    except Exception:
        return result
    if not found:
        return result
    text = line
    for s, e, face, _r in sorted(found, reverse=True):
        text = text[:s] + face + text[e:]
    details, spans, original_spans = [], [], []
    shift = 0
    for s, e, face, _r in sorted(found):
        details.append([line[s:e], face, 'ローマ字の入れ替わり'])
        spans.append([s + shift, s + shift + len(face)])
        original_spans.append([s, e])
        shift += len(face) - (e - s)
    merged = dict(result)
    merged.update(corrected=text, changed=True, details=details, spans=spans, original_spans=original_spans,
                  odd_spans=[x for x in (result.get('odd_spans') or ())
                             if not any(s < x[1] and x[0] < e for s, e, _f, _r in found)],
                  odd_reasons=[x for x in (result.get('odd_reasons') or ())
                               if not any(s < x[1] and x[0] < e for s, e, _f, _r in found)])
    return merged
