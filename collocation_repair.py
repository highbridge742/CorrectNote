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
**打ち間違えた読みがそのまま辞書の語になる形**を、語の組（collocation_table）で見る（2026-10-23）。

へんじ を ほんじ と打つと IME は 本字 を出し、行は「本字を書いて送った」になる。語は辞書に在り、
並びも費用も正しく見えるので、異様の印が立たない。決め手は語の意味の組:

  元の組（本字＋を＋書く）が表に無く、名詞か動詞の**打った読みを1打戻した読み**の語で組が表に在る
  （返事＋を＋書く）なら、それが打ち違いの跡。

- 名詞の側（本字→返事・社員→写真）: 元の語が身近な語（AI 判定の層1）でも、表の組でもないなら直す。
  元の語が身近な語なら、元の文も言えるので直さず紫（迷い）にして、理由に組を示す。
- 動詞の側（持つ→待つ・切った→買った）: 動詞はどれも身近なので直さず紫。
- 1打戻した語の組が2つ以上並べば、決め手が無いので紫。
- 表に無い組は「組でない」の証拠にしない（組が在る側が見つかったときだけ動く）。
- 本人の書いた文からは学ばない（表は同梱の固定のもの）。読みは IME の確定の読みを先に使う。
"""

from cache_limits import size as _cache_size   # 控えの上限は cache_limits で1か所に（2026-10-24）
from functools import lru_cache

PARTICLES = ('を', 'に', 'で', 'が', 'は')
# 助詞と動詞の間に挟まってよい語（写真を**たくさん**撮った・友達を**ずっと**待つ）
_GAP_POS = ('副詞',)
_NOUN_PARTNER = ('の', '連体', '続')  # 組の相手が述語でなく、左の名詞・形容詞か直後の語の行
_FOLLOWERS = ('いたす', '致す', 'する', '願う', 'です')
_GAP_SUB = ('副詞可能',)


@lru_cache(maxsize=1)
def table():
    """(名詞, 助詞, 動詞の基本形) の集合と、引くための索引。"""
    from collocation_table import GROUPS
    triples = set()
    for row in GROUPS.strip().splitlines():
        parts = row.split('\t')
        if len(parts) != 3:
            continue
        p, verbs, nouns = parts
        for v in verbs.split():
            for n in nouns.split():
                triples.add((n, p, v))
    by_pv, by_np = {}, {}
    words, verbs = set(), set()
    for n, p, v in triples:
        by_pv.setdefault((p, v), set()).add(n)
        by_np.setdefault((n, p), set()).add(v)
        words.add(n)
        verbs.add(v)
    return triples, by_pv, by_np, words | verbs


@lru_cache(maxsize=None)
def _row_rank(p, v):
    """表の (助詞, 動詞) の行で、名詞を書いた順（先に書いた語ほどよく使う）。"""
    from collocation_table import GROUPS
    rank = {}
    for row in GROUPS.strip().splitlines():
        parts = row.split('\t')
        if len(parts) == 3 and parts[0] == p and v in parts[1].split():
            for n in parts[2].split():
                rank.setdefault(n, len(rank))
    return rank


def _semantic():
    """意味の分類（semantic_class）。表が読めなければ None（いまと同じ答えになる）。"""
    try:
        import semantic_class
        return semantic_class if semantic_class.available() else None
    except Exception:
        return None


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


def _kanji(c):
    return '一' <= c <= '鿿' or c == '々'


@lru_cache(maxsize=_cache_size(4096))
def _word_reading(word):
    import morphology
    toks = list(morphology.tokenize(word))
    if not toks or not all(t.has_reading for t in toks) or ''.join(t.surface for t in toks) != word:
        return None
    return _hira(''.join(t.reading for t in toks))


@lru_cache(maxsize=_cache_size(4096))
def _one_key(reading, input_method):
    """読みを1打戻した読みの集合（last_keystroke.candidates と同じ打鍵の形）。"""
    from last_keystroke import candidates
    import kana_layout as kl
    # 1字の抜けの戻し（足す）は見ない（脱字は低い優先度・うに 10-19。き→あき＝気になる→秋になる・
    # みやげ→おみやげ のように、正しい語に字を足して別の組の語にしてしまう）
    # 上下のキーは _far_key（紫だけ）の受け持ち。ここで数えると 型を増やした（かた→かち）を 価値 に直した
    # （2026-10-24・うにさんの誤判定）
    token = kl.VERTICAL_OK.set(False)
    try:
        return frozenset(text for text, (op, _i) in candidates(reading, 0, len(reading), input_method).items()
                         if op != 'ins')
    finally:
        kl.VERTICAL_OK.reset(token)


@lru_cache(maxsize=_cache_size(4096))
def _far_key(reading, input_method):
    """上下・斜めのキーに替えた読み。置き換えは同じ段の左右だけ直す決まりなので、紫だけに使う。"""
    if input_method == 'romaji':
        return _far_key_romaji(reading)
    if input_method != 'kana':
        return frozenset()
    import kana_layout as kl
    from last_keystroke import _keys, KEY_DISTANCE
    out = set()
    for i, c in enumerate(reading):
        for ch in _keys():
            if ch != c and kl.kana_key_distance(c, ch, intrusion=True) <= KEY_DISTANCE:
                out.add(reading[:i] + ch + reading[i + 1:])
    return frozenset(out - _one_key(reading, input_method))


_QWERTY_ROWS = ('qwertyuiop', 'asdfghjkl', 'zxcvbnm')


def _rare(face):
    try:
        import ime_reconvert
        return ime_reconvert._rank(face) >= ime_reconvert.DOUBT
    except Exception:
        return False


WF_MARGIN = 150     # 元の語が候補より一般の文でこれだけ稀（wordfreq の段の差）なら、組の無さを打ち違いの証と見る


def _rarer_than_any(face, alts):
    """元の語 face が、候補 alts のどれかより一般の文ではっきり稀か（表に無い語は 800 で数える）。"""
    try:
        import ime_reconvert
        r = ime_reconvert._rank(face)
        return any(r - ime_reconvert._rank(a) >= WF_MARGIN for a in alts)
    except Exception:
        return True


def _common(face):
    try:
        import ime_reconvert
        return ime_reconvert._rank(face) <= 500     # 承知・了解 くらいまで
    except Exception:
        return False


def _qwerty_vertical(ch):
    """上下・斜めに隣り合うキー（下の段は半キーほど右にずれる: w の下は a と s）。"""
    for r, row in enumerate(_QWERTY_ROWS):
        c = row.find(ch)
        if c < 0:
            continue
        out = []
        if r > 0:
            out += [_QWERTY_ROWS[r - 1][x] for x in (c, c + 1) if 0 <= x < len(_QWERTY_ROWS[r - 1])]
        if r + 1 < len(_QWERTY_ROWS):
            out += [_QWERTY_ROWS[r + 1][x] for x in (c - 1, c) if 0 <= x < len(_QWERTY_ROWS[r + 1])]
        return out
    return []


def _far_key_romaji(reading):
    try:
        import romaji_swap_repair
        from halfwidth import romaji_to_kana
        spellings = romaji_swap_repair._spellings(reading, limit=2)
    except Exception:
        return frozenset()
    out = set()
    for typed in spellings:
        for i, ch in enumerate(typed):
            for other in _qwerty_vertical(ch):
                r = romaji_to_kana(typed[:i] + other + typed[i + 1:])[0]
                if r and r != reading and all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in r):
                    out.add(r)
    return frozenset(out - _one_key(reading, 'romaji'))


def _typed_reading(face, token_reading):
    """IME の確定の読み（打った読み）。無ければ辞書の読み。"""
    try:
        from kanji_guess import _IME_READINGS_PROVIDER as prov
        if prov is not None:
            for r in (prov(face) or ()):
                if r and isinstance(r, str) and r != face and all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in r):
                    return r
    except Exception:
        pass
    return _hira(token_reading)


_SURU_FORMS = ('する', 'した', 'して', 'しま', 'しな', 'しよ', 'すれ', 'され', 'させ', 'せず', 'しろ')


def _ime_suru_face(line, toks, k):
    """IME が確定した漢字の語＋する の形（賢治＋した: 辞書は 賢＋治し と読む）→ 漢字の語か None。"""
    a = toks[k].start
    b = a
    while b < len(line) and _kanji(line[b]):
        b += 1
    if b == a or not line[b:b + 2] in _SURU_FORMS:
        return None
    face = line[a:b]
    try:
        from kanji_guess import _IME_READINGS_PROVIDER as prov
        if prov is not None and any(r and isinstance(r, str) and r != face for r in (prov(face) or ())):
            return face
    except Exception:
        pass
    return None


def _predicate(toks, k, line=''):
    """toks[k] から始まる述語 → (基本形, 語の字句の番号) か None。サ変の名詞＋する は 掃除する。"""
    t = toks[k]
    if t.pos == '動詞' and t.pos_sub.split(':')[0] == '自立' and t.has_reading:
        u = toks[k + 1] if k + 1 < len(toks) else None
        if u is not None and u.pos == '動詞' and u.pos_sub.split(':')[0] == '自立' and u.start == t.end:
            # 複合動詞（書き＋間違える・持ち＋帰る）は前の動詞だけの組ではない
            return None
        return t.base_form, k
    # 名詞＋する（掃除する）。IME が同じ読みの別の語を出した形（けんじする→賢治する: 辞書は 賢＋治 に切る）も
    # 漢字の名詞の並び＋する として同じく見る
    j = k
    while (j < len(toks) and toks[j].pos in ('名詞', '接頭詞') and all(_kanji(c) for c in toks[j].surface)
           and toks[j].pos_sub.split(':')[0] not in ('代名詞', '非自立', '数')
           and (j == k or toks[j].start == toks[j - 1].end)):
        j += 1
    if (j > k and j < len(toks) and toks[j].pos == '動詞' and toks[j].base_form == 'する'
            and toks[j].start == toks[j - 1].end):
        return ''.join(x.surface for x in toks[k:j]) + 'する', k
    face = _ime_suru_face(line, toks, k) if line and toks[k].pos in ('名詞', '接頭詞') else None
    if face:
        return face + 'する', k
    return None


def _frames(toks, line=''):
    """(名詞の字句の番号, 助詞, 述語の基本形, 述語の字句の番号) の並び。"""
    out = []
    for i in range(len(toks) - 2):
        n, p = toks[i], toks[i + 1]
        if not (n.pos == '名詞' and n.has_reading and p.pos == '助詞' and p.surface in PARTICLES
                and n.pos_sub.split(':')[0] not in ('代名詞', '数', '非自立', '接尾')):
            continue
        k = i + 2
        while k < len(toks) and k < i + 4 and (toks[k].pos in _GAP_POS or toks[k].pos_sub in _GAP_SUB):
            k += 1
        if k >= len(toks):
            continue
        pred = _predicate(toks, k, line)
        if pred:
            out.append((i, p.surface, pred[0], pred[1]))
    # 名詞＋の＋名詞（添付の資料）と 形容詞＋名詞（新しい住所）: 右の名詞を組の名詞、左の語を組の相手として同じ表で見る
    # （表の行は「の」「連体」。相手の語は替えない）
    for i in range(1, len(toks)):
        n = toks[i]
        if not (n.pos == '名詞' and n.has_reading and n.pos_sub.split(':')[0] not in ('代名詞', '数', '非自立', '接尾')):
            continue
        if i + 1 < len(toks) and toks[i + 1].pos == '名詞' and toks[i + 1].start == n.end:
            # 名詞が続く（議事＋録）: 組の名詞は続いた語ぜんたいなので、1語では見ない
            continue
        q = toks[i - 1]
        if (q.surface == 'の' and q.pos == '助詞' and i >= 2 and toks[i - 2].pos == '名詞' and toks[i - 2].has_reading
                and toks[i - 2].pos_sub.split(':')[0] not in ('代名詞', '数', '非自立')):
            out.append((i, 'の', toks[i - 2].surface, i - 2))
        elif q.pos == '形容詞' and q.has_reading and q.end == n.start and q.surface == q.base_form:
            out.append((i, '連体', q.base_form, i - 1))
    # 名詞の直後の述語（承知いたします・幸いです・返信願います）: 左の名詞を組の名詞、直後の語を組の相手として見る
    for i in range(len(toks) - 1):
        n, q = toks[i], toks[i + 1]
        if not (n.pos == '名詞' and n.has_reading and q.start == n.end
                and n.pos_sub.split(':')[0] not in ('代名詞', '数', '非自立', '接尾')):
            continue
        if i > 0 and toks[i - 1].pos == '名詞' and toks[i - 1].end == n.start:
            continue
        if (q.pos in ('動詞', '助動詞') and q.base_form in _FOLLOWERS):
            out.append((i, '続', q.base_form, i + 1))
        elif (q.surface == 'お願い' and i + 2 < len(toks) and toks[i + 2].start == q.end
              and toks[i + 2].base_form in ('する', 'いたす', '致す')):
            # 名詞＋お願いします・お願いいたします（返信お願いします）
            out.append((i, '続', 'お願い', i + 1))
    # 漢字かカタカナで書いた副詞＋です（〜です の名詞が副詞に切れた形）: 紫だけ（下の find）
    for i in range(len(toks) - 1):
        n, q = toks[i], toks[i + 1]
        if (n.pos == '副詞' and n.has_reading and q.start == n.end and q.pos == '助動詞' and q.base_form == 'です'
                and any(_kanji(c) or 'ァ' <= c <= 'ヶ' for c in n.surface)
                and not (i > 0 and toks[i - 1].end == n.start and toks[i - 1].pos in ('名詞', '副詞'))):
            out.append((i, '続', 'です', i + 1))
    return out


def _noun_options(line, toks, i, p, v, input_method):
    triples, by_pv, _by_np, _words = table()
    n = toks[i]
    typed = _typed_reading(n.surface, n.reading)
    near, far = _one_key(typed, input_method), _far_key(typed, input_method)
    out = []
    for cand in sorted(by_pv.get((p, v), ())):
        if cand == n.surface:
            continue
        r = _word_reading(cand)
        kind = 'same' if r == typed else 'near' if r in near else 'far' if r in far else None
        if kind is None and r and p in _NOUN_PARTNER and _one_mora(typed, r):
            # 名詞どうし・〜します の組で、かなの1字だけ違う読み（キーが離れた打ち違い・抜け）: 紫だけ（find）
            kind = 'mora'
            if input_method == 'kana' and not (len(r) == len(typed) + 1
                                               and any(r[:k] + r[k + 1:] == typed for k in range(len(r)))):
                # かな入力では、隣のキーでも1字の抜けでもない1字違い（さいあい／さいわい）は打ち違いの形でないので、
                # 候補にせず紫も付けない（うに 10-30「隣接でも脱字でもないので紫も不要」）
                kind = None
        if r and kind and (kind != 'same' or _distinct_spelling(n.surface, cand)):
            out.append((n.start, n.end, cand, kind, cand))
    return out


def _hepburn_distance(a, b):
    """かなの読み2つの、ヘボン式のローマ字での打鍵の違いの数（入れ・抜け・置き換え）。綴れなければ大きな数。"""
    try:
        import romaji_swap_repair
        x = romaji_swap_repair._spellings(a, limit=1)
        y = romaji_swap_repair._spellings(b or '', limit=1)
    except Exception:
        return 99
    if not x or not y:
        return 99
    x, y = x[0], y[0]
    d = list(range(len(y) + 1))
    for i, cx in enumerate(x, 1):
        prev, d[0] = d[0], i
        for j, cy in enumerate(y, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (cx != cy))
    return d[-1]


def _one_mora(a, b):
    """かなの1字の置き換え・抜け・余り（拗音の小さい字は前の字と組で数えない）。短い読みは見ない。"""
    if min(len(a), len(b)) < 3 or a == b:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if abs(len(a) - len(b)) != 1:
        return False
    long, short = (a, b) if len(a) > len(b) else (b, a)
    return any(long[:i] + long[i + 1:] == short for i in range(len(long)))


def _class_noun_options(line, toks, i, p, v, input_method, sem):
    """表の名詞にも読みをつないだ形にも届かないとき、表の名詞と同じ意味の仲間の語（semantic_class）を候補にする。
    仲間が表の1語にしか出ない候補は確かでない（'weak'）。"""
    n = toks[i]
    typed = _typed_reading(n.surface, n.reading)
    near = _one_key(typed, input_method)
    out = []
    for cand in sorted(sem.candidates(p, v, {typed} | set(near), _familiar)):
        r = _word_reading(cand)
        kind = 'same' if r == typed else 'near' if r in near else None
        if cand != n.surface and r and kind and (kind != 'same' or _distinct_spelling(n.surface, cand)):
            out.append((n.start, n.end, cand, kind, None if sem.strong(cand, p, v) else 'weak'))
    return out


def _joined_noun_options(line, toks, i, p, v, input_method, words):
    """名詞とその左の1〜2語の読みをつないで1打戻すと、表の組の名詞になるもの（といもだち → ともだち を待つ・
    そえじ → そうじ をする）。元の名詞が表の語か身近な語なら、元の組も言えるので見ない。組の助詞（を・が・に…）は
    またがない（またぐと別の組になる）。"""
    n = toks[i]
    if p in _NOUN_PARTNER:
        return []
    if n.surface in words or _familiar(n.surface):
        return []
    _triples, by_pv, _by_np, _words = table()
    cands = sorted(by_pv.get((p, v), ()))
    out = []
    for j in (i - 1, i - 2):
        if j < 0:
            break
        span = toks[j:i + 1]
        if any(not t.has_reading for t in span) or any(a.end != b.start for a, b in zip(span, span[1:])):
            break
        if any(t.pos == '助詞' and t.surface in PARTICLES for t in span[:-1]) or any(t.pos == '記号' for t in span):
            break
        face = line[span[0].start:span[-1].end]
        kanji = any(_kanji(c) for c in face)
        if not kanji and not (len(span) >= 3 and any('ァ' <= c <= 'ヶ' for c in face)):
            # かなで書いた語（ぶんしょう・えほん）は書いたとおり。IME が漢字の語に切った形だけを見る。
            # カタカナの語が入った形は、表の2語をつないだ読み（下）だけを見る
            continue
        typed = ''.join(_typed_reading(t.surface, t.reading) for t in span)
        near = _one_key(typed, input_method)
        for cand in cands:
            r = _word_reading(cand)
            # 読みの一部をそのまま取り出しただけの語（えほん → ほん）は戻しでない
            if kanji and r and r in near and r not in typed and cand != face:
                out.append((span[0].start, span[-1].end, cand, 'near', j))
        if not out and len(span) >= 3:
            # 助詞をはさんで切れた形（〜と＋〜）: 表の組の2語をつないだ読みが、つないだ読みと同じか1打違い
            for a in cands:
                ra = _word_reading(a)
                if not ra or not typed.startswith(ra[:1]):
                    continue
                for b in cands:
                    rb = _word_reading(b)
                    if rb and a != b and (ra + rb == typed or ra + rb in near):
                        # 同じ読みは直せる。1打違いもからむときは紫だけ
                        out.append((span[0].start, span[-1].end, a + b, 'near' if ra + rb == typed else 'pair_near', j))
        if out:
            break
    return out


def _verb_options(line, toks, i, p, v, k, input_method):
    _triples, _by_pv, by_np, _words = table()
    import morphology
    t = toks[k]
    if v.endswith('する') and t.pos in ('名詞', '接頭詞'):
        # 名詞＋する の名詞の側だけを替える（賢治＋する → 堅持＋する）
        face = v[:-2]
        end = t.start + len(face)
        typed = _typed_reading(face, _word_reading(face) or '')
        if not typed:
            return []
        near, far = _one_key(typed, input_method), _far_key(typed, input_method)
        out = []
        for cand in sorted(by_np.get((toks[i].surface, p), ())):
            if cand == v or not cand.endswith('する') or len(cand) < 3:
                continue
            r = _word_reading(cand[:-2])
            kind = 'same' if r == typed else 'near' if r in near else 'far' if r in far else None
            if r and kind and (kind != 'same' or _distinct_spelling(face, cand[:-2])):
                out.append((t.start, end, cand[:-2], kind, cand))
        return out
    if t.pos != '動詞' or not t.surface or not _kanji(t.surface[0]):
        return []
    stem_len = 0
    while stem_len < len(t.surface) and _kanji(t.surface[stem_len]):
        stem_len += 1
    tail = t.surface[stem_len:]
    typed = _hira(t.reading)
    near, far = _one_key(typed, input_method), _far_key(typed, input_method)
    out = []
    for cand in sorted(by_np.get((toks[i].surface, p), ())):
        if cand == v or cand.endswith('する') or not _kanji(cand[0]):
            continue
        cstem = cand[:next((j for j, c in enumerate(cand) if not _kanji(c)), len(cand))]
        new = cstem + tail
        text = line[:t.start] + new + line[t.end:]
        u = next((x for x in morphology.tokenize(text) if x.start == t.start), None)
        if (u is None or u.end != t.start + len(new) or u.pos != '動詞' or u.base_form != cand
                or not u.has_reading):
            continue
        r = _hira(u.reading)
        kind = 'same' if r == typed else 'near' if r in near else 'far' if r in far else None
        if kind and (kind != 'same' or _distinct_spelling(cstem, t.surface[:stem_len])):
            out.append((t.start, t.end, new, kind, cand))
    return out


def _distinct_spelling(a, b):
    """同じ読みの2つの表記を替えてよいか: どちらも漢字だけ（賢治／堅持・介決／解決）。
    かなを含む形（子ども／子供・珈琲／コーヒー）は同じ語の書き分けなので替えない。"""
    return bool(a) and bool(b) and all(_kanji(c) for c in a) and all(_kanji(c) for c in b)


def _familiar(word):
    try:
        import kango_tier
        return kango_tier.known_usage_tier(word) == 1
    except Exception:
        return False


def _clean_left(toks, i, words):
    """名詞の左が確かな区切りか: 行頭・句読点、身近な語か表の語に付いた助詞、形容詞・動詞の連体の形。
    左に打ち違いの切れ端が残る形（変の＋字・屁か＋字・麻木＋範）では、打ち違いは名詞の外に在りうるので直さない。"""
    if i == 0:
        return True
    q = toks[i - 1]
    if q.pos == '記号' and q.surface and all(c in '。．.！？!?「『（(［[、，, 　\t' for c in q.surface):
        # 句読点・括弧（濁点のキー ゛゜ の打ち残しは区切りでない）
        return True
    if q.pos in ('形容詞', '動詞') and q.has_reading and q.end == toks[i].start:
        return True
    if q.pos == '助詞' and i >= 2:
        h = toks[i - 2]
        return h.pos == '名詞' and h.has_reading and (h.surface in words or _familiar(h.surface))
    return False


def _run_follower_options(line, toks, input_method, triples, guard):
    """名詞の並び＋直後の述語（層＋談＋します）: IME が打ち違いの読みを幾つもの語に切った形を、並びの読みを
    つないで1打戻し（同じ読みも）、表の「続」の組の名詞になるか見る。候補が1つなら直す、2つ以上なら紫。"""
    _t, by_pv, _n, _w = table()
    out = []
    i = 0
    while i < len(toks):
        j = i
        while (j < len(toks) and toks[j].pos == '名詞' and toks[j].has_reading
               and toks[j].pos_sub.split(':')[0] not in ('代名詞', '数', '非自立')
               and (j == i or toks[j].start == toks[j - 1].end)):
            j += 1
        if j - i >= 2 and j < len(toks) and toks[j].start == toks[j - 1].end and toks[j].pos in ('動詞', '助動詞') \
                and toks[j].base_form in _FOLLOWERS:
            s, e, v = toks[i].start, toks[j - 1].end, toks[j].base_form
            face = line[s:e]
            if (face, '続', v) not in triples and not any(a < e and s < b for a, b in guard):
                typed = _hira(''.join(t.reading for t in toks[i:j]))
                near = _one_key(typed, input_method)
                cands = sorted(c for c in by_pv.get(('続', v), ())
                               if c != face and (_word_reading(c) == typed or _word_reading(c) in near))
                if cands:
                    alts = '・'.join('「%s%s」' % (c, v) for c in cands)
                    reason = '「%s%s」より %s がよく使う組です' % (face, v, alts)
                    out.append((s, e, cands[0] if len(cands) == 1 else None, len(cands) == 1, reason))
            i = j
        elif (j - i >= 2 and _desu_swallowed(toks[j - 1], toks[j] if j < len(toks) else None)
              and _better_same_reading(toks[j - 2])):
            # 行末の名詞の並びの終わりのカタカナの語が、読みの終わりに「です」を抱えている（〜アンデス 型）:
            # 述語の です が語に取り込まれたかもしれない。表では決められないので紫だけ
            s, e = toks[j - 1].start, toks[j - 1].end
            if not any(a < e and s < b for a, b in guard):
                out.append((s, e, None, False, '「%s」は、終わりの「です」が語に取り込まれたかもしれません' % line[s:e]))
            i = j
        else:
            i = max(j, i + 1)
    return out


def _better_same_reading(t):
    """左の名詞にも、同じ読みでずっと身近な名詞が在る（IME の選び違いが続いた形）。"""
    try:
        import ime_reconvert
        import reading_lattice
        reading_lattice.load()
        own = ime_reconvert._rank(t.surface)
        return any(pos == '名詞' and surf != t.surface and ime_reconvert._rank(surf) <= own - 50
                   for surf, _l, _r, _c, pos in reading_lattice._table.get(_hira(t.reading or ''), ()))
    except Exception:
        return False


def _dropped_keys_te(line, toks, input_method, triples, guard):
    """ローマ字で2打までの抜けが、名詞＋助詞＋動詞の て形 をカタカナの語＋って に変えた形（お世話になって の w と n が
    抜けて おせあにあって）。抜けた打鍵を戻した読みが表の組（名詞・助詞・動詞）の て形になるものを探す。
    候補が1つなら直す、2つ以上なら紫。"""
    if input_method != 'romaji':
        return []
    out = []
    for i in range(len(toks) - 1):
        t, q = toks[i], toks[i + 1]
        if not (t.pos == '名詞' and t.has_reading and q.surface == 'って' and q.start == t.end
                and all('ァ' <= c <= 'ヶ' or c == 'ー' for c in t.surface) and _rare(t.surface)):
            continue
        # って の後が て形に付く語（おります・いただく…）のときだけ。「オセアニアって知ってる」は引用の って
        r = toks[i + 2] if i + 2 < len(toks) else None
        if not (r is not None and r.start == q.end and r.pos == '動詞'
                and (r.base_form in ('おる', 'いる', 'いただく', 'くださる', 'もらう', 'しまう', 'おく', 'ある')
                     or r.surface in ('おり', 'おりまし'))):     # 解析は って＋おり を 降りる と読むことがある
            continue
        if any(a < q.end and t.start < b for a, b in guard):
            continue
        typed_kana = _hira(t.reading) + 'って'
        try:
            import romaji_swap_repair
            typed = romaji_swap_repair._spellings(typed_kana, limit=2)
        except Exception:
            continue
        cands = set()
        for n, p, v in triples:
            if p not in ('に', 'を', 'が', 'と', 'で') or not v.endswith(('る', 'う', 'つ')) or len(v) < 2:
                continue
            rn, rv = _word_reading(n), _word_reading(v)
            if not rn or not rv:
                continue
            want = rn + p + rv[:-1] + 'って'
            if abs(len(want) - len(typed_kana)) > 2:
                continue
            for w in romaji_swap_repair._spellings(want, limit=2):
                if any(_dropped(w, x) for x in typed):
                    cands.add(n + p + v[:-1] + 'って')
                    break
        if cands:
            alts = '・'.join('「%s」' % c for c in sorted(cands))
            new = sorted(cands)[0] if len(cands) == 1 else None
            out.append((t.start, q.end, new, len(cands) == 1,
                        '「%s」は、打鍵が抜けた %s かもしれません' % (line[t.start:q.end], alts)))
    return out


def _dropped(full, typed, limit=2):
    """typed が full から limit 打までを抜いた形か（先頭の打鍵は同じ）。"""
    if not full or not typed or full[0] != typed[0] or not (0 < len(full) - len(typed) <= limit):
        return False
    it = iter(full)
    return all(c in it for c in typed)


# て形に付く語（ます形）。同じ頭の形が幾つもあるときは最初のもの（おります／おりました → おります）
_TE_FOLLOWERS = ('おります', 'います', 'いただきます', 'いただけますか', 'ください', 'くださいます', 'あります',
                 'おきます', 'しまいます', 'みます', 'くれます', 'もらえますか', 'もらいます', 'まいります')


def _te_then_rare_name(line, toks, guard):
    """動詞の「〜て・〜で」のすぐ後に、めったに使わない固有名詞が来て行（文）が終わる形（予測変換の選び違い:
    〜ております が 〜て＋地名 になる）。文の形が崩れているので紫だけ。"""
    out = []
    for i in range(1, len(toks)):
        t, q = toks[i], toks[i - 1]
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if not (q.pos == '助詞' and q.surface in ('て', 'で') and q.pos_sub.startswith('接続助詞')
                and t.pos == '名詞' and t.pos_sub.startswith('固有名詞') and t.start == q.end):
            continue
        if nxt is not None and not (nxt.pos == '記号' and nxt.surface in ('。', '．', '！', '？', '!', '?')):
            continue
        if not _rare(t.surface) or any(a < t.end and t.start < b for a, b in guard):
            continue
        # 打った読みの頭（予測変換の前に打った字）が、て形に付く語の頭と2字以上そろい、そろう語が1つなら
        # その語に直す（おり｜んぴあ → おります）
        r = _hira(t.reading or '')
        heads = {}
        for form in _TE_FOLLOWERS:
            k = 0
            while k < min(len(r), len(form)) and r[k] == form[k]:
                k += 1
            if k >= 2:
                heads.setdefault(form[:k], form)
        if len(heads) == 1 and q.end == t.start:
            new = next(iter(heads.values()))
            out.append((t.start, t.end, new, True,
                        '「%s%s」は、予測変換で「%s」の所を選び違えた形かもしれません' % (q.surface, t.surface, new)))
            continue
        out.append((t.start, t.end, None, False,
                    '「%s%s」で文が終わっています。「%s」は予測変換で選び違えた語かもしれません'
                    % (q.surface, t.surface, t.surface)))
    return out


_SMALL_VOWEL = {'ぁ': 'a', 'ぃ': 'i', 'ぅ': 'u', 'ぇ': 'e', 'ぉ': 'o'}
_FUNC_POS = ('助詞', '助動詞')


def _small_vowel_spellings(kana):
    """小さい母音（ぃ）の付いた読みのローマ字（しまつぃあ → shimatsia・simatia）。"""
    import romaji_swap_repair
    outs = ['']
    i = 0
    while i < len(kana):
        j = i
        while j < len(kana) and kana[j] not in _SMALL_VOWEL:
            j += 1
        part = kana[i:j]
        sp = romaji_swap_repair._spellings(part, limit=2) if part else ['']
        if not sp:
            return []
        if j < len(kana):
            # 小さい母音は前の字の母音を置き換える（つ＋ぃ → tsi）
            sp = [x[:-1] + _SMALL_VOWEL[kana[j]] for x in sp if x and x[-1] in 'aiueo']
            j += 1
        outs = [o + x for o in outs for x in sp][:8]
        i = j
    return outs


def _small_vowel_head(line, toks, input_method, guard):
    """ローマ字の打鍵の順番違いで、かなの頭に小さい母音が出た形（shimasita を shimatsia と打って しまつぃあ）。
    小さい母音で始まる語とその前の1〜2語の読みをローマ字に戻し、1打の入れ替え・2つ先への移り・1打の抜きを
    戻して、そこが付属の語（する・ます・た…）か身近な語だけになり行の費用が大きく下がるものを探す。
    いちばん安いものが2番目より十分安ければ直す、近ければ紫。"""
    if input_method != 'romaji':
        return []
    try:
        from halfwidth import romaji_to_kana
        import morphology
        import ime_reconvert
    except Exception:
        return []
    out = []
    for i, t in enumerate(toks):
        if not (t.surface and t.surface[0] in _SMALL_VOWEL) or i == 0:
            continue
        if any(a < t.end and toks[max(0, i - 2)].start < b for a, b in guard):
            continue
        here = morphology.path_cost(line)
        if here is None:
            continue
        best = {}
        for k in (1, 2):
            if i - k < 0:
                break
            win = toks[i - k:i + 1]
            if any(w.end != x.start for w, x in zip(win, win[1:])) or not all(w.has_reading for w in win[:-1]):
                continue
            a, b = win[0].start, t.end
            typed = ''.join(_hira(w.reading) for w in win[:-1]) + t.surface
            for sp in _small_vowel_spellings(typed):
                vs = set()
                for j in range(len(sp) - 1):
                    vs.add(sp[:j] + sp[j + 1] + sp[j] + sp[j + 2:])
                    if j + 2 < len(sp):
                        vs.add(sp[:j] + sp[j + 1:j + 3] + sp[j] + sp[j + 3:])
                        vs.add(sp[:j] + sp[j + 2] + sp[j:j + 2] + sp[j + 3:])
                for j in range(1, len(sp)):
                    vs.add(sp[:j] + sp[j + 1:])
                for v in vs:
                    kana = romaji_to_kana(v)[0]
                    if not kana or not all('ぁ' <= c <= 'ゖ' for c in kana):
                        continue
                    if any(c in _SMALL_VOWEL for c in kana):
                        continue
                    other = line[:a] + kana + line[b:]
                    new = [x for x in morphology.tokenize(other) if x.start < a + len(kana) and a < x.end]
                    if (not new or new[0].start != a or new[-1].end != a + len(kana)
                            or any(not x.has_reading for x in new)
                            or not all(x.pos in _FUNC_POS or x.pos == '動詞' for x in new)
                            or not any(x.pos == '動詞' for x in new)
                            or any(ime_reconvert._rank(x.base_form or x.surface) > 470 and x.pos == '動詞'
                                   and x.base_form not in ('する', 'いたす', 'くださる', 'おる', 'いる', 'ある', 'なる')
                                   for x in new)):
                        continue
                    if __import__('os').environ.get('CN_SMALL_VOWEL_TE') != '0':
                        # て・で の後ろに付く補助の動詞（いる・ある・おく・しまう…）が て・で の後ろでない形
                        # （えいふぁ → へ｜い｜あ）は語の並びになっていない（2026-11-06 挙動関連担当のアプリの道の試し）
                        allx = list(morphology.tokenize(other))
                        if any(x.pos == '動詞' and x.pos_sub.split(':')[0] == '非自立'
                               and x.base_form in ('いる', 'ある', 'おく', 'しまう', 'みる', 'いく', 'くる')
                               and not (k2 > 0 and allx[k2 - 1].surface in ('て', 'で'))
                               for k2, x in enumerate(allx) if x.start < a + len(kana) and a < x.end):
                            continue
                    c = morphology.path_cost(other)
                    if c is not None and here - c >= 3000:
                        best[other] = min(c, best.get(other, c))
        if best:
            ranked = sorted((c, o) for o, c in best.items())
            sure = len(ranked) == 1 or ranked[1][0] - ranked[0][0] >= 300
            # 直す所は、元の行と直した行で違う所
            import difflib
            ops = [o for o in difflib.SequenceMatcher(None, line, ranked[0][1], autojunk=False).get_opcodes() if o[0] != 'equal']
            s1, e1 = ops[0][1], ops[-1][2]
            new_s = ranked[0][1][ops[0][3]:ops[-1][4]]
            alts = '・'.join('「%s」' % o for _c, o in ranked[:3])
            out.append((s1, e1, new_s if sure else None, sure,
                        '「%s」はローマ字の打鍵の順番違いかもしれません（%s）' % (line[s1:e1], alts)))
    return out


def _desu_swallowed(t, nxt):
    if nxt is not None and not (nxt.pos == '記号' and nxt.surface in ('。', '．', '！', '？', '!', '?')):
        return False
    r = _hira(t.reading or '')
    if not (len(r) >= 4 and r.endswith('です') and all('ァ' <= c <= 'ヶ' or c == 'ー' for c in t.surface)):
        return False
    return _rare(t.surface)


def _dakuten_only(a, b):
    """読み a と b が、1字の濁点・半濁点の有無だけ違うか（へんし／へんじ）。"""
    import unicodedata
    if not a or not b or len(a) != len(b):
        return False
    diff = [(x, y) for x, y in zip(a, b) if x != y]
    if len(diff) != 1:
        return False
    strip = lambda c: unicodedata.normalize('NFD', c)[0]
    return strip(diff[0][0]) == strip(diff[0][1])


def find(line, input_method='kana', guard=()):
    """行の中の、語の組で見た打ち違い → [(始まり, 終わり, 置く字, 確か, 理由)]。"""
    if input_method not in ('kana', 'romaji') or not line:
        return []
    import morphology
    triples, _by_pv, _by_np, words = table()
    toks = list(morphology.tokenize(line))
    sem = _semantic()
    out = (_run_follower_options(line, toks, input_method, triples, guard) + _te_then_rare_name(line, toks, guard)
           + _dropped_keys_te(line, toks, input_method, triples, guard)
           + _small_vowel_head(line, toks, input_method, guard))
    for i, p, v, k in _frames(toks, line):
        n = toks[i]
        if (n.surface, p, v) in triples:
            continue
        if any(a < toks[k].end and n.start < b for a, b in guard):
            continue
        # 意味の仲間: 身近な語で組の仲間なら元の組も言える／分類に在って組の仲間でない名詞
        fits = bool(sem) and sem.fits(n.surface, p, v, _familiar)
        foreign = bool(sem) and sem.foreign(n.surface, p, v)
        nouns = [] if fits else _noun_options(line, toks, i, p, v, input_method)
        verbs = [] if nouns or fits or p in _NOUN_PARTNER else _verb_options(line, toks, i, p, v, k, input_method)
        opts = nouns or verbs
        if sem and p not in _NOUN_PARTNER and not opts and not fits and not _joined_noun_options(line, toks, i, p, v, input_method, words):
            nouns = opts = _class_noun_options(line, toks, i, p, v, input_method, sem)
        if not opts:
            # 名詞1語の読みでは届かないとき: IME が打ち違いの読みを幾つもの語に切った形（問いも＋立ち＝といもだち）を、
            # 左の語の読みとつないで見る。確かでない組の紫の門（下）とは別の判定で、紫だけを付ける
            joined = _joined_noun_options(line, toks, i, p, v, input_method, words)
            if joined:
                s, e = joined[0][0], joined[0][1]
                alts = '・'.join('「%s%s%s」' % (x[2], p, v) for x in joined)
                # 候補が1つで、つないだまとまりの左が確かな区切り（行頭・句読点・身近な語か表の語に付いた助詞）なら直す。
                # 左に切れ端が残る形や候補が2つ以上なら紫だけ
                sure = len(joined) == 1 and joined[0][3] != 'pair_near' and _clean_left(toks, joined[0][4], words)
                out.append((s, e, joined[0][2], sure, '「%s%s%s」より %s がよく使う組です' % (line[s:e], p, v, alts)))
            continue
        if nouns and len(opts) > 1 and p in _NOUN_PARTNER and input_method == 'romaji':
            # 候補が幾つかあるときは、ヘボン式で打った英字の違いが1打だけのもの（へんし／へんしん: n の抜け）が
            # 1つならそれに決める（へんじ は shi と ji で2打違う）
            one = [x for x in opts if _hepburn_distance(_typed_reading(n.surface, n.reading), _word_reading(x[2])) == 1]
            if len(one) == 1:
                nouns = opts = one
        if nouns and len(opts) > 1 and p in _NOUN_PARTNER and input_method == 'kana':
            # かな入力で候補が幾つかあるときは、かなキーの打ち違いの形（同じ読み・1打隣・濁点のキー）が1つなら
            # それに決める（へんし／へんじ: 濁点の抜け。へんしん は ん の抜けで、かなでは抜けを後に回す）。
            # 有力な候補が並んでも紫に留めない（うに 10-30）
            one = [x for x in opts if x[3] in ('same', 'near')]
            if len(one) == 1 and one[0][3] == 'near' and _dakuten_only(_word_reading(n.surface), _word_reading(one[0][2])):
                # 濁点のキー1打の違い（へんし→へんじ）と抜けの1打（へんし→へんしん）はどちらも1打。表の行で先に書いた
                # 語（よく使う方）が抜けの側なら、そちらに決める（うに 2026-11-02「変死は返信を優先したい」）
                rank = _row_rank(p, v)
                best = min(opts, key=lambda x: rank.get(x[2], 999))
                if best[3] == 'mora' and rank.get(best[2], 999) < rank.get(one[0][2], 999):
                    one = [best]
            if len(one) == 1:
                nouns = opts = one
        if nouns and len(opts) > 1 and p in _NOUN_PARTNER:
            # まだ並ぶときも紫に留めず、表の行で先に書いた語（よく使う方）に決める（うに 10-30「どちらかに補正する」）
            rank = _row_rank(p, v)
            kinds = ('same', 'near', 'far', 'mora')
            opts = sorted(opts, key=lambda x: (kinds.index(x[3]) if x[3] in kinds else 9, rank.get(x[2], 999)))
            nouns = opts = opts[:1]
        s, e, new, kind, _base = opts[0]
        old = line[s:e]
        # 同じ読みの別の語（賢治する→堅持する）: 打った読みは正しく、IME の表記の選びが文脈に合わない形
        homophone = len(opts) == 1 and kind == 'same'
        known = n.surface in words and (bool(nouns) or v in words)
        if verbs and homophone and n.surface in words and v not in words and v.endswith('する'):
            # 名詞＋する の同じ読み: 元の述語（賢治する）が表のどの組にも出ず、名詞（方針）が表の語。
            # 元の名詞が する の付く語（サ変の名詞）なら元の文も言えるので紫、付かない語（賢治: 人名）なら直す
            import morphology as _m
            head = list(_m.tokenize(old))
            sure = not (len(head) == 1 and head[0].pos_sub.startswith('サ変接続'))
        elif (not known and (verbs or _familiar(n.surface)) and not (nouns and foreign)
                and not (p in _NOUN_PARTNER and kind == 'same' and v != 'する')):
            # 表に無い組は「組でない」の証拠にしない。元の語が表の組に出てくる語（社員・持つ）のときだけ、
            # その組が表に無いことを打ち違いの手掛かりにする（餌を買う: 餌 は表に無いので見ない）
            continue
        elif verbs and kind == 'same':
            # 元の動詞も表の語（絵を書く／描く）: 同じ読みの書き分けは紫にもしない
            continue
        elif len(opts) == 1 and nouns and kind in ('same', 'near'):
            # 元の名詞が身近な語でも表の組の語でもない（本字・主審）なら直す。身近な語（社員）は元の文も言えるので紫
            sure = (not _familiar(old) and old not in words and any(_kanji(c) for c in old)
                    and _clean_left(toks, i, words))
            if p in _NOUN_PARTNER and kind != 'same':
                # 名詞どうし・形容詞＋名詞の組は述語の組より緩い（1打違いの元の組も言えることがある）。1打違いは
                # 元の語がめったに使わない語で、直し先が身近な語のときだけ直す。ほかは紫だけ
                sure = sure and _rare(old) and _common(new)
            if (not sure and p == '続' and v in ('願う', 'お願い') and kind == 'same' and old not in words
                    and _clean_left(toks, i, words)):
                # 〜願います・〜お願いします は頼みの形で、前の名詞は頼む事柄（返信・確認）。同じ読みの表の語が1つだけで、
                # 元の語が表の語でなければ IME の選び違いとして直す（元の語が身近な語でも: 変身→返信 の形）
                sure = True
            if p in _NOUN_PARTNER and not sure:
                # 元の組は表に無く、同じ読みか1打隣に表の組が在る: 決めずに紫（元の語が身近な語でも）
                foreign = True
        elif nouns and p in _NOUN_PARTNER and all(x[3] in ('far', 'mora') for x in opts):
            # 上下のキー・離れたキー・抜けの打ち違いは紫だけ。元の語がめったに使わない語（wordfreq の段）のときに限る
            # 候補が1つで、直し先が身近な語なら直す（2026-10-30 うにさんの画面: 紫止まりが多い）
            sure = len(opts) == 1 and _rare(old) and _common(opts[0][2]) and _clean_left(toks, i, words)
            foreign = _rare(old)
        else:
            sure = False
        if nouns and p in _NOUN_PARTNER:
            glue = 'の' if p == 'の' else ''
            if p == '続':
                alts = '・'.join('「%s%s」' % (x[2], v) for x in opts)
                reason = '「%s%s」より %s がよく使う組です' % (old, v, alts)
            else:
                alts = '・'.join('「%s%s%s」' % (v, glue, x[2]) for x in opts)
                reason = '「%s%s%s」より %s がよく使う組です' % (v, glue, old, alts)
        elif nouns:
            alts = '・'.join('「%s%s%s」' % (x[2], p, v) for x in opts)
            reason = '「%s%s%s」より %s がよく使う組です' % (old, p, v, alts)
        else:
            alts = '・'.join('「%s%s%s」' % (n.surface, p, x[4]) for x in opts)
            reason = '「%s%s%s」より %s がよく使う組です' % (n.surface, p, v, alts)
        if nouns and opts[0][4] == 'weak':
            # 意味の仲間だけで見つけた候補で、その仲間が表の名詞の1語にしか出ないもの: 決め手が弱いので紫
            sure = False
        if not sure and nouns and foreign:
            # 元の名詞が組の意味の仲間でないのに、1打隣か同じ読みに組の語が在る: 迷うなら紫（元の語が身近な語でも）
            if not _rarer_than_any(old, [x[2] for x in opts]):
                # ただし元の名詞が一般の文で候補と同じくらい使う語（表記／病気・位置／市）なら、表に組が無いのは
                # 表の狭さ（技術の語が少ない）で、打ち違いの証にならない。紫も付けない（説明書の正しい文に
                # 紫が立っていた。2026-10-30・補正担当）
                continue
            out.append((s, e, None, False, reason))
            continue
        if not sure:
            # 確かでない組（紙を切る／髪を切る・気をつける／火をつける・友達を持つ／待つ）の紫は、表に無い正しい組に
            # 多く当たる（2026-10-23 試験一式で 道を入る・予定を書く・糸を張る など）ので、表が広がるまで付けない
            continue
        out.append((s, e, new, sure, reason))
        if sure and p not in _NOUN_PARTNER and i >= 2 and toks[i - 1].pos == '助詞' and toks[i - 1].surface in ('に', 'で'):
            # 直した名詞の左の「語＋に・で」が述語との組を持たない（明日に＋天気を調べた: の→に の打ち違いが残る）
            # なら、直しは残してその残りに紫を付ける（迷うなら紫）。左の語が表の語（図書館で）なら付けない
            h = toks[i - 2]
            if (h.pos == '名詞' and h.surface not in words and (h.surface, toks[i - 1].surface, v) not in triples
                    and h.end == toks[i - 1].start):
                out.append((h.start, toks[i - 1].end, None, False,
                            '「%s%s」は「%s」とつながりにくい形です' % (h.surface, toks[i - 1].surface, v)))
    return out


def apply(line, result, input_method='kana', decisions=None):
    """補正の結果（直した行）に、語の組で見た直しと紫を足す。足した形の結果を返す。"""
    done = result.get('corrected') or line
    try:
        from last_keystroke import _protected
        guard = _protected(done, decisions)
    except Exception:
        guard = ()
    try:
        found = find(done, input_method, guard)
    except Exception:
        return result
    if not found:
        return result
    edits = [(s, e, new, reason) for s, e, new, sure, reason in found if sure]
    marks = [(s, e, reason) for s, e, new, sure, reason in found if not sure]
    text = done
    details, spans, original_spans = [], [], []
    for s, e, new, _reason in sorted(edits, reverse=True):
        text = text[:s] + new + text[e:]
    shift = 0
    for s, e, new, _reason in sorted(edits):
        details.append([done[s:e], new, '語の組'])
        spans.append([s + shift, s + shift + len(new)])
        original_spans.append([s, e])
        shift += len(new) - (e - s)
    second = {'original': done, 'corrected': text, 'changed': bool(edits),
              'details': details, 'spans': spans, 'original_spans': original_spans,
              'odd_spans': [], 'unsure_spans': [], 'odd_reasons': []}
    if edits and done == line:
        merged = dict(result)
        merged.update(corrected=text, changed=True, details=details, spans=spans, original_spans=original_spans)
    elif edits:
        from correction_entry import _merge_second_pass
        merged = _merge_second_pass(line, result, second)
    else:
        merged = dict(result)
    if edits and done == line:
        # 直した所に掛かっていた前の段の紫（直す前の語への印）は、直したので外す（変死→返信 の上に紫が残った・2026-11-02）
        hit = lambda a, b: any(a < e1 and s1 < b for s1, e1, _n, _r in edits)
        for key in ('odd_spans', 'unsure_spans'):
            if merged.get(key):
                merged[key] = [x for x in merged[key] if not hit(x[0], x[1])]
        if merged.get('odd_reasons'):
            merged['odd_reasons'] = [x for x in merged['odd_reasons'] if not hit(x[0], x[1])]
    if edits:
        # 直しの後ろの紫は位置がずれるので、直しより前の紫だけ残す
        first = min(s1 for s1, _e1, _n, _r in edits)
        marks = [m for m in marks if m[1] <= first]
    if marks:
        pairs = sorted((tuple(x[:2]), tuple(y[:2])) for x, y in zip(result.get('spans') or (), result.get('original_spans') or ())) if done != line else []

        def to_original(a, b):
            # 直した行の位置 → 元の行の位置（前の直しと重なれば None）
            delta = 0
            for (s1, e1), (os1, oe1) in pairs:
                if a < e1 and s1 < b:
                    return None
                if e1 <= a:
                    delta += (oe1 - os1) - (e1 - s1)
            return a + delta, b + delta
        # 後の段（correction_entry の紫）が odd_spans を並べ替えるので、型はそちらと同じ tuple にそろえる
        odd = [tuple(x) for x in (merged.get('odd_spans') or ())]
        reasons = [tuple(x) for x in (merged.get('odd_reasons') or ())]
        for s1, e1, reason in marks:
            o = to_original(s1, e1)
            if o is None or any(a < o[1] and o[0] < b for a, b in [tuple(x[:2]) for x in odd]):
                continue
            odd.append(tuple(o))
            reasons.append((o[0], o[1], reason))
        merged['odd_spans'], merged['odd_reasons'] = odd, reasons
    return merged
