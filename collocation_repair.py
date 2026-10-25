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
    """上下・斜めのキーに替えた読み（かな入力）。置き換えは同じ段の左右だけ直す決まりなので、紫だけに使う。"""
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
        if r and kind and (kind != 'same' or _distinct_spelling(n.surface, cand)):
            out.append((n.start, n.end, cand, kind, cand))
    return out


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
        if not any(_kanji(c) for c in face):
            # かなで書いた語（ぶんしょう・えほん）は書いたとおり。IME が漢字の語に切った形だけを見る
            continue
        typed = ''.join(_typed_reading(t.surface, t.reading) for t in span)
        near = _one_key(typed, input_method)
        for cand in cands:
            r = _word_reading(cand)
            # 読みの一部をそのまま取り出しただけの語（えほん → ほん）は戻しでない
            if r and r in near and r not in typed and cand != face:
                out.append((span[0].start, span[-1].end, cand, 'near', j))
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


def find(line, input_method='kana', guard=()):
    """行の中の、語の組で見た打ち違い → [(始まり, 終わり, 置く字, 確か, 理由)]。"""
    if input_method not in ('kana', 'romaji') or not line:
        return []
    import morphology
    triples, _by_pv, _by_np, words = table()
    toks = list(morphology.tokenize(line))
    sem = _semantic()
    out = []
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
        verbs = [] if nouns or fits else _verb_options(line, toks, i, p, v, k, input_method)
        opts = nouns or verbs
        if sem and not opts and not fits and not _joined_noun_options(line, toks, i, p, v, input_method, words):
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
                sure = len(joined) == 1 and _clean_left(toks, joined[0][4], words)
                out.append((s, e, joined[0][2], sure, '「%s%s%s」より %s がよく使う組です' % (line[s:e], p, v, alts)))
            continue
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
        elif not known and (verbs or _familiar(n.surface)) and not (nouns and foreign):
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
        else:
            sure = False
        if nouns:
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
            out.append((s, e, None, False, reason))
            continue
        if not sure:
            # 確かでない組（紙を切る／髪を切る・気をつける／火をつける・友達を持つ／待つ）の紫は、表に無い正しい組に
            # 多く当たる（2026-10-23 試験一式で 道を入る・予定を書く・糸を張る など）ので、表が広がるまで付けない
            continue
        out.append((s, e, new, sure, reason))
        if sure and i >= 2 and toks[i - 1].pos == '助詞' and toks[i - 1].surface in ('に', 'で'):
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
    if edits:
        # 直しの後ろの紫は位置がずれるので、直しより前の紫だけ残す
        first = min(s1 for s1, _e1, _n, _r in edits)
        marks = [m for m in marks if m[1] <= first]
    if marks:
        pairs = sorted(zip(result.get('spans') or (), result.get('original_spans') or ())) if done != line else []

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
