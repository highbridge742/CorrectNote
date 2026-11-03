# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""
紫の所の読みに、一般の打ち違いの戻しを当てて、行がはっきり自然になる形を1つ選ぶ段（odd_respell・補正担当・
2026-11-01。うにさん 11-01 00:38Z「理由2に取り掛かって」: 紫は付くが直し先が1つに決まらない行）。

前の段は「おかしい所」は見つけて紫にするが、直し先を探すのが1打の置き換えだけの段や、漢字の語の中の打ち違いを
見ない段が多い。ここでは紫の所（語の区切りまで広げる）の読みを打鍵に開き、contextual_repair.key_repairs の一手
（隣のキーへの置き換え・巻き込みの抜き・抜けの足し・二度押し・入れ替わり）を当てる。戻した読みに漢字を置き
（last_keystroke._place_kanji）、行の並びの費用（morphology.path_cost）の安い順に TOP だけ、行の補正をし直して
（run: 後段を通さない補正）紫も迷いも残らないかを見る。

置くのは次がそろうときだけ:
  - 一番の形は、補正し直しても紫も迷いも残らない。
  - 一番の形は、元の行より GAIN 以上軽い（短い行は元の行の費用の GAIN_SHARE でよい）。
  - 二番の形（紫が残る形も含む）より MARGIN 以上軽い。並べば紫のまま。
かな入力だけ（key_repairs はかなの配列の打鍵）。特定の語や文字列には合わせない。
"""
import difflib
from functools import lru_cache

GAIN = 5000
MARGIN = 2500
TOP = 6
MAX_READ = 12
SCREEN = GAIN      # 補正し直す前の見送り（重さを減らす・答えの決め手ではない）
COMMON_NEW = 520   # 直した所に出る漢字の名詞は、一般の文章の使われやすさの順位がこれ以下（ime_reconvert._rank）
SECOND_FROM = 6    # 2打の戻しは、1打の戻しの費用の安い順にこれだけから広げる
SECOND_TOP = 3     # 2打の戻しで補正し直して見る数
MAX_READINGS = 4   # 紫の所の読みの候補（打った読み・解析の読みの組み合わせ）
ALIGN_PLACE = 40   # 変わらない語の表記を残した形のうち、漢字を置いてみる数
GAIN_SHARE = 0.25  # 短い行では並びの費用そのものが小さく、GAIN（一定の差）に届かない（作った例で 約9,800→5,500）。
                   # 元の行の費用のこの割合だけ軽くなれば足りる（GAIN を超えては求めない・2026-11-01）
WIDEN = 4          # 付く先の無い ゛゜ の前へ広げて読み直す字数（打った読みの記録で戻せなかったとき）


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s or '')


def _is_hira(s):
    return bool(s) and all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in s)


def _token_readings(t, dict_index):
    """語の読みの候補（確からしい順）。打った読みの記録（kanji_guess.ime_readings_for・PC の IME で確定した読み）を
    先に、次に解析の読み（解析の読みは打った読みと違うことがある: 1字の漢字の訓読み）。字の読みを総当たりで足すと
    でたらめな読みの並びが候補に混ざって選び違えたので足さない（2026-11-01）。"""
    out = []
    if _is_hira(t.surface):
        return [t.surface]
    try:
        from kanji_guess import ime_readings_for
        out.extend(_hira(r) for r in ime_readings_for(t.surface))
    except Exception:
        pass
    if t.has_reading:
        out.append(_hira(t.reading))
    out.extend(_one_kanji_readings(t.surface))
    seen = []
    for r in out:
        if _is_hira(r) and r not in seen:
            seen.append(r)
    return seen[:3]


ONE_KANJI_ALT = 2   # 1字の漢字の語の、解析の読みのほかに見る読みの数


@lru_cache(maxsize=512)
def _one_kanji_readings(surface):
    """1字の漢字の語の、辞書にその字1字の語として載っている読み（費用の安い順に ONE_KANJI_ALT まで）。解析は1字の漢字を
    前後の語に引かれて別の読みで読むことがある（上 を接頭の かみ と読む形・字の音と訓の取り違え）。字の読みを総当たりで足すとでたらめな
    読みの並びが混ざったので、その字1字の語として辞書に在る読みだけを見る（2026-11-01・短い行）。"""
    if len(surface) != 1 or not _kanji(surface):
        return ()
    try:
        import reading_lattice
        reading_lattice.load()
        table = reading_lattice._table
        onkun = _onkun()
    except Exception:
        return ()
    got = []
    for r in onkun.get(surface, ()):
        costs = [c for s, _l, _r, c, _p in table.get(r, ()) if s == surface]
        if costs:
            got.append((min(costs), r))
    got.sort()
    return tuple(r for _c, r in got[:ONE_KANJI_ALT])


@lru_cache(maxsize=1)
def _onkun():
    import json
    import os
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kanji_onkun.json'), encoding='utf-8') as f:
        d = json.load(f)
    return d.get('readings') or {}


def _with_surface(done, x, y, typed):
    """打った読みの記録 typed に、表記から読み直した読み（_surface_readings）を足す。記録が付く先の無い ゛゜ や記号の
    まじる所（IME が記号まじりに変換した所）の記録は、別の打鍵（打ち直す前の打鍵など）の読みのことがあり、記録の読み
    だけでは書くつもりの読みに届かない（2026-11-01 C・補正担当の調べ）。記録の読みを先に、表記の読みを後ろに並べる。"""
    run = done[x:y]
    if not any(c in '゛゜' or not (c.isalnum() or c.isspace()) for c in run):
        return typed[:MAX_READINGS]
    try:
        sr = [r for r in (_surface_readings(run) or ()) if r not in typed]
    except Exception:
        sr = []
    if not sr:
        return typed[:MAX_READINGS]
    keep = max(1, MAX_READINGS - min(2, len(sr)))
    return typed[:keep] + sr[:MAX_READINGS - min(keep, len(typed))]


def _typed_run(done, a, b):
    """紫の所を含む、平仮名と句読点・空白を含まない並び（IME が1度に変換した所: デ゜ン和番号）に、PC で打った読みの
    記録（kanji_guess.ime_readings_for）が在れば (開始, 終了, [打った読み])。記号を含む所も、打った読みからなら
    戻せる（て゛゜んわ… は ゜ を巻き込んで デ゜ン和 と変換される・うにさん 11-01 03:58Z）。無ければ None。"""
    try:
        from kanji_guess import ime_readings_for
    except Exception:
        return None

    def inside(c):
        return not (_is_hira(c) or c.isspace() or c in '。、，．,.！？!?「」『』')

    def lookup(x, y):
        # 句読点まで1度に確定した記録（〜て。）も引く。読みの終わりの句読点は外す（2026-11-01 B）
        got = list(ime_readings_for(done[x:y]) or ())
        if y < len(done) and done[y] in '。、':
            got += [r[:-1] for r in (ime_readings_for(done[x:y + 1]) or ()) if r and r[-1:] in '。、']
        return got
    s, e = a, b
    while s > 0 and inside(done[s - 1]):
        s -= 1
    while e < len(done) and inside(done[e]):
        e += 1
    if s >= e:
        return None
    out = []
    # 1回の確定は後ろのかな（助詞）まで含むことがある（デ゜ン和番号を）。後ろの平仮名まで広げた形も引く
    tail = e
    while tail < len(done) and _is_hira(done[tail]):
        tail += 1
    # 前の平仮名（平仮名の語＋の＋漢字の語）や前の文節（名詞＋が＋次の語）も1回の確定に入ることがある。打ち違いが前の平仮名に在ると、漢字の所だけの読みでは
    # 戻せない。前の平仮名まで広げた形は、広げない形の後で引く（2026-11-01・短い行）
    head = s
    while head > 0 and (_is_hira(done[head - 1]) or inside(done[head - 1])):
        head -= 1
    end = tail
    while end < len(done) and (_is_hira(done[end]) or inside(done[end])):
        end += 1
    tries = [(s, e)] + [(s, t) for t in range(e + 1, end + 1)]
    tries += [(h, t) for h in range(s - 1, head - 1, -1) for t in range(e, end + 1)]
    tries += [(a, b)]
    for x, y in tries:
        try:
            got = lookup(x, y)
        except Exception:
            got = []
        for r in got:
            r = _hira(r)
            if r and len(r) <= MAX_READ + 2 and all('ぁ' <= c <= 'ゖ' or c in 'ー゛゜' for c in r) and r not in out:
                out.append(r)
        if out:
            return x, y, _with_surface(done, x, y, out)
    # 1回の確定が前の字から始まることもある（かなの付いた語の後ろの漢字だけに紫が付き、打った読みの記録はかなの字からの表記に在る形）。
    # 句読点・空白の手前まで、前へ1字ずつ広げた形も引く（記録に在る表記＝その字から1度に確定した所・2026-11-01 B）
    lead = s
    while lead > 0 and e - lead < MAX_READ and not (done[lead - 1].isspace() or done[lead - 1] in '。、，．,.！？!?「」『』'):
        lead -= 1
    for x in range(s - 1, lead - 1, -1):
        for y in range(e, tail + 1):
            try:
                got = lookup(x, y)
            except Exception:
                got = []
            for r in got:
                r = _hira(r)
                if r and len(r) <= MAX_READ + 2 and all('ぁ' <= c <= 'ゖ' or c in 'ー゛゜' for c in r) and r not in out:
                    out.append(r)
            if out:
                return x, y, _with_surface(done, x, y, out)
    if any(c in '゛゜' for c in done[s:e]):
        got = _surface_readings(done[s:e])
        if got:
            return s, e, got
    return None


# JIS 配列でシフトを押した記号 → 同じキーの字（かな入力では、そのキーのかな・小書きのかな）
_JIS_SHIFT_SYMBOL = {'!': '1', '"': '2', '#': '3', '$': '4', '%': '5', '&': '6', "'": '7', '(': '8', ')': '9',
                     '=': '-', '~': '^', '|': '¥', '`': '@', '{': '[', '+': ';', '*': ':', '}': ']', '<': ',',
                     '>': '.', '?': '/', '_': '\\'}


def _key_kana(ch):
    """記号1字 → 同じ物理キーのかな（シフトの記号ならシフトのかなを先に）。無ければ []。"""
    import unicodedata
    try:
        import keyboard_layout, kana_layout
    except Exception:
        return []
    c = unicodedata.normalize('NFKC', ch)
    key, shifted = (_JIS_SHIFT_SYMBOL[c], True) if c in _JIS_SHIFT_SYMBOL else (c, False)
    pos = keyboard_layout.positions().get(key)
    if pos is None:
        return []
    kana = [k for k, p in kana_layout.KANA_POSITIONS.items() if p == pos and 'ぁ' <= k <= 'ゖ']
    small = [k for k in kana if k in 'ぁぃぅぇぉっゃゅょゎ' or k == 'を']
    big = [k for k in kana if k not in small]
    return (small + big) if shifted else (big + small)


def _surface_readings(run):
    """打った読みの記録が無いとき、付く先の無い ゛゜ を含む IME の1文節（ゲ゜）亜 のような形）を、表記から読み直す。
    かなはそのまま、漢字の語は解析の読み、記号は同じキーのかな（かな入力でシフトや ゜ のあとに記号へ化けた字）。
    ゛゜ は残す（後で key_repairs が抜く形を試す）。"""
    import itertools
    from morphology import tokenize
    opts = []
    for t in tokenize(run):
        sf = t.surface
        if all(c in '゛゜' for c in sf):
            opts.append([sf])
        elif all(_is_hira(c) or c in '゛゜' or 'ァ' <= c <= 'ヶ' for c in sf):
            opts.append([_hira(sf)])
        elif t.pos == '記号' or not any(_kanji(c) for c in sf):
            per = []
            for c in sf:
                if c in '゛゜':
                    per.append([c])
                elif _is_hira(_hira(c)):
                    per.append([_hira(c)])
                else:
                    k = _key_kana(c)
                    if not k:
                        return []
                    per.append(k[:2])
            opts.append([''.join(x) for x in itertools.islice(itertools.product(*per), 4)])
        else:
            rs = _token_readings(t, None)
            if not rs:
                return []
            opts.append(rs)
    out = []
    for combo in itertools.islice(itertools.product(*opts), 16):
        rd = ''.join(combo)
        if rd and len(rd) <= MAX_READ and rd not in out:
            out.append(rd)
        if len(out) >= MAX_READINGS:
            break
    return out


def _span_reading(done, a, b, dict_index=None):
    """紫の所を語の区切りまで広げた (開始, 終了, [読み])。読めない語・記号を含めば None。"""
    import itertools
    from morphology import tokenize
    typed = _typed_run(done, a, b)
    if typed:
        return typed
    toks = [t for t in tokenize(done) if t.end > a and t.start < b]
    if not toks:
        return None
    opts = []
    for t in toks:
        if t.pos == '記号':
            return None
        rs = _token_readings(t, dict_index)
        if not rs:
            return None
        opts.append(rs)
    rds = []
    # 紫の所まるごとに打った読みの記録が在れば、それを先に（IME の1文節を打った読み）
    try:
        from kanji_guess import ime_readings_for
        whole = done[toks[0].start:toks[-1].end]
        for r in ime_readings_for(whole):
            r = _hira(r)
            if _is_hira(r) and len(r) <= MAX_READ and r not in rds:
                rds.append(r)
    except Exception:
        pass
    recorded = False
    # 紫の所の中の、漢字を含む語から始まる並び（IME で1度に確定した文節）に打った読みの記録が在れば、その並びは記録の
    # 読みに、ほかの語は解析の読みにした形も先に（紫が欄全体に付き、記録は中の文節だけに在る形・手分けA）
    try:
        from kanji_guess import ime_readings_for
        for i, t in enumerate(toks):
            if not any(_kanji(c) for c in t.surface):
                continue
            for j in range(len(toks) - 1, i - 1, -1):
                if i == 0 and j == len(toks) - 1:
                    continue
                got = [_hira(r) for r in ime_readings_for(done[t.start:toks[j].end])]
                got = [r for r in got if _is_hira(r)]
                if not got:
                    continue
                for r in got[:2]:
                    head = ''.join(o[0] for o in opts[:i])
                    tail = ''.join(o[0] for o in opts[j + 1:])
                    rd = head + r + tail
                    if len(rd) <= MAX_READ and rd not in rds:
                        rds.append(rd)
                        recorded = True
                break
    except Exception:
        pass
    if recorded:
        # 打った読みの記録は打った事実なので、記録の在る文節を解析の読みで読んだ形（打っていない読み）は並べない
        return toks[0].start, toks[-1].end, rds[:MAX_READINGS]
    for combo in itertools.islice(itertools.product(*opts), 16):
        rd = ''.join(combo)
        if rd and len(rd) <= MAX_READ and rd not in rds:
            rds.append(rd)
        if len(rds) >= MAX_READINGS:
            break
    if not rds:
        return None
    return toks[0].start, toks[-1].end, rds


def _widened_mark_spans(done, i):
    """付く先の無い ゛゜（done[i]）を含む所を、左へ1字ずつ広げて表記から読み直した [(開始, 終了, [読み])]（短い順）。
    ゛゜ の前の字と並べ違えると（し・へ・ら・゛・る と打つ: ら を へ と ゛ の間に打った）、IME は ゛ を前の字に付けられず、
    ゛゜ と後ろの字だけの所の読みでは元の打鍵に届かない。前のかな・漢字まで読みに入れて key_repairs の入れ替わりを
    当てる（2026-11-01）。句読点・空白・漢字の並びの途中では切らない。"""
    stop = '。、，．,.！？!?「」『』（）()・'
    e = i + 1
    while e < len(done) and not (_is_hira(done[e]) or done[e].isspace() or done[e] in stop):
        e += 1
    out = []
    s = i
    while s > 0 and i - s < WIDEN:
        s -= 1
        c = done[s]
        if c.isspace() or c in stop or c in '゛゜':
            break
        if s > 0 and _kanji(done[s - 1]) and _kanji(c):
            continue
        try:
            rds = _surface_readings(done[s:e])
        except Exception:
            rds = []
        if rds:
            out.append((s, e, rds))
    return out


def _merge_region(line, done0, fixed, s, e):
    """line[s:e] を直した形 fixed（line 全体の直し）の所に、前の段の答え done0 のうち、その所に触れない直し
    （所の外で、端にも接しない）だけを重ねる。所に触れる前の段の直し（゛ の後ろの字を ね に替えた等）は捨てる。"""
    tail = len(line) - e
    if tail < 0 or len(fixed) < s + tail or fixed[:s] != line[:s] or fixed[len(fixed) - tail:] != line[e:]:
        return None
    mid = fixed[s:len(fixed) - tail]
    pieces = []
    pos = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, line, done0, autojunk=False).get_opcodes():
        if tag == 'equal' or (i1 <= e and i2 >= s):
            continue
        pieces.append((i1, i2, done0[j1:j2]))
    out = []
    for i1, i2, rep in sorted(pieces):
        if i1 < pos:
            return None
        if pos <= s <= i1:
            out.append(line[pos:s] + mid)
            pos = e
        out.append(line[pos:i1] + rep)
        pos = i2
    if pos <= s:
        out.append(line[pos:s] + mid)
        pos = e
    out.append(line[pos:])
    return ''.join(out)


def _voice_mark(line, i):
    """line[i] の ゛゜ が声の表記（あ゛ー・え゛っ: 濁れない字に付けて、後ろが ー・っ・記号・行の終わり）なら True。
    濁れない字でも後ろにかなが続く所（ら゛る）は打ち違いとして見る（2026-11-01 補正担当）。"""
    import unicodedata
    if i == 0:
        return False
    prev = line[i - 1]
    if not ('ぁ' <= prev <= 'ゖ' or 'ァ' <= prev <= 'ヺ'):
        return False
    if len(unicodedata.normalize('NFD', prev)) != 1:
        return False      # ギ゜ のように、もう印の付いた字の後ろは打ち違い
    comb = '\u3099' if line[i] == '゛' else '\u309a'
    if len(unicodedata.normalize('NFC', prev + comb)) == 1:
        return False      # 付けられる字（か゛）は声の表記ではない
    j = i + 1
    while j < len(line) and line[j] in '゛゜':
        j += 1
    return j >= len(line) or line[j] in 'ーっッ〜～…' or not (line[j].isalnum())


def _bare_reading(text):
    """行の読みから ゛゜ と濁点・半濁点を除いた形（印の付け違いを数えずに、打った字が残っているかを比べる）。"""
    import unicodedata
    r = _line_reading(text)
    if r is None:
        return None
    r = unicodedata.normalize('NFD', r)
    return ''.join(c for c in r if c not in '\u3099\u309a゛゜')


def _edit_count(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def _base_keeps_more(line, base, new_text, i, out):
    """前の段がもう ゛゜ を片付けて（紫を残さず）、打った字をより多く残した形なら True。
    （印だけを除けば読める行を、印の後ろの字まで替えた別の語にしない・手分けB）"""
    if base == line:
        return False
    m = _to_done(line, base, max(0, i - 2), min(len(line), i + 3))
    if any(c in '゛゜' for c in base):
        return False
    for sp in (out.get('odd_spans') or ()):
        if m is None or (sp[0] < m[1] + 2 and m[0] - 2 < sp[1]):
            return False
    r0, rb, rn = _bare_reading(line), _bare_reading(base), _bare_reading(new_text)
    if None in (r0, rb, rn):
        return False
    return _edit_count(r0, rb) < _edit_count(r0, rn)


def _stray_mark_repair(line, result, run, store, dict_index, context_vec, decided):
    """付く先の無い ゛゜ の所を、元の行（前の段が ゛゜ を別の字に直していても、その前の打った形）から左へ広げて
    読み直し、はっきり自然になる形を1つ選ぶ。前の段の答えより MARGIN 以上軽いときだけ替える。"""
    import morphology
    done0 = result.get('corrected') or line
    marks = [i for i, c in enumerate(line) if c in '゛゜' and not _voice_mark(line, i)]
    if not marks:
        return result
    cur_cost = morphology.path_cost(done0)
    out = result
    for i in reversed(marks):
        # 広げ方ごとに一番の形を出し、いちばん軽い形を採る（゛ と後ろの字だけの短い所の直しより、
        # 前の字まで入れた入れ替わりの直し（しへら゛る → 調べる）が軽いことがある）
        import morphology as _m
        from contextual_repair import key_repairs
        base_line = _m.path_cost(line)
        if base_line is None:
            continue
        # 広げ方ごとの戻しに漢字を置き、全部の中で安い順に TOP だけ補正し直す（広げ方ごとに補正し直すと遅い）
        pool = {}
        for s, e, rds in _widened_mark_spans(line, i):
            if any(x < e and s < y for x, y in (decided or ())):
                break
            tried = set(rds)
            reps = []
            for rd in rds:
                for r in key_repairs(rd, line[:s][-1:], line[e:][:1]):
                    r = getattr(r, 'reading', r)
                    if r and r not in tried:
                        tried.add(r)
                        reps.append(r)
            try:
                placed = _placed(line, s, e, reps, store, dict_index, context_vec)
            except Exception:
                placed = []
            for c, text, _r in placed:
                if text not in pool or c < pool[text][0]:
                    pool[text] = (c, s, e)
        ranked = sorted(pool.items(), key=lambda x: x[1][0])
        if not ranked or base_line - ranked[0][1][0] < SCREEN:
            continue
        seen = {}
        where = {}
        for text, (c, s, e) in ranked[:TOP]:
            for fx, v in _judge(line, s, e, [text], run, (), True).items():
                if fx not in seen or v[0] < seen[fx][0]:
                    seen[fx] = v
                    where[fx] = (s, e)
        got = _pick(seen)
        if got is None or base_line - got[1] < GAIN:
            continue
        fixed = got[0]
        if _mark_replaced(line, fixed):
            continue
        s, e = where[fixed]
        base = out.get('corrected') or line
        new_text = _merge_region(line, base, fixed, s, e)
        if new_text is None or new_text == base:
            continue
        c_new = morphology.path_cost(new_text)
        c_old = morphology.path_cost(base) if base != done0 else cur_cost
        if c_new is None or (c_old is not None and c_new + MARGIN > c_old):
            continue
        if _base_keeps_more(line, base, new_text, i, out):
            continue
        ops = [o for o in difflib.SequenceMatcher(None, line, new_text, autojunk=False).get_opcodes()
               if o[0] != 'equal']
        new = dict(out)
        gone = line[s:e]
        new.update({'original': line, 'corrected': new_text, 'changed': True,
                    'details': [d for d in (out.get('details') or [])
                                if not (d and isinstance(d[0], str) and d[0] and d[0] in gone)]
                    + [_detail(base, new_text)],
                    'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
        # 前の段の紫・迷いは done の位置。広げた所に掛かるものは消す（位置は直した形の側で見る）
        for key in ('odd_spans', 'unsure_spans'):
            keep = []
            for sp in (out.get(key) or ()):
                m = _to_done(base, new_text, sp[0], sp[1])
                if m is None:
                    continue
                keep.append(type(sp)((m[0], m[1]) + tuple(sp[2:])) if isinstance(sp, tuple) else [m[0], m[1]] + list(sp[2:]))
            new[key] = keep
        if 'odd_reasons' in out:
            new['odd_reasons'] = [r for r in (out.get('odd_reasons') or ())
                                  if _to_done(base, new_text, r[0], r[1]) is not None]
        out = new
    return out


def _to_done(line, done, a, b):
    if line == done:
        return a, b
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes():
        if tag == 'equal' and i1 <= a and b <= i2:
            return a - i1 + j1, b - i1 + j1
    return None


def _kanji(c):
    return '一' <= c <= '鿿' or c == '々'


def _splits_kanji_run(done, fixed, a=None, b=None):
    """漢字の並び（IME が1つの読みから変換した所）の一部の漢字だけを別の漢字に替え、残りの漢字をそのまま残す形か。
    その並びはそのまま打った読み（誤変換 は ごへんかん）から出たもので、1打違いの読み（こへんかん）からなら IME は
    並びごと別の表記にしていた。一部だけ替える戻しは採らない（誤変換→小変換 の形・2026-11-01）。"""
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, done, fixed, autojunk=False).get_opcodes():
        if tag == 'equal':
            continue
        if not any(_kanji(c) for c in fixed[j1:j2]) or not any(_kanji(c) for c in done[i1:i2]):
            continue
        left = i1 > 0 and _kanji(done[i1 - 1]) and _kanji(done[i1]) if i1 < len(done) else False
        right = i2 < len(done) and i2 > 0 and _kanji(done[i2]) and _kanji(done[i2 - 1])
        if a is not None:
            # 打った読みの記録から1文節ごと戻すとき（デ゜ン和番号）は、その文節の中に残る漢字も読み直した形
            left = left and not (a <= i1 - 1 < b)
            right = right and not (a <= i2 < b)
        if left or right:
            return True
    return False


def _lattice(alt, a, e, store, dict_index):
    """_place_kanji が置けなかった読み（ぎょうばんごう）に、読みの格子の置き方（kana_lattice_place）で漢字を置く。"""
    try:
        import kana_lattice_place
        places, _ = kana_lattice_place.propose(alt, store, dict_index)
    except Exception:
        return alt
    for s0, e0, f in sorted(places, reverse=True):
        if a <= s0 and e0 <= e:
            alt = alt[:s0] + f + alt[e0:]
    return alt


@lru_cache(maxsize=64)
def _surface_tokens(done, a=0, b=None):
    """done[a:b] の (語の並び, 語ごとの読み or None)。区切りは行全体の解析で見る（所だけを解析すると がせ＋るい の
    ように区切りが変わる）。行の区切りが a・b に合わなければ所だけで解析する。区切れなければ None。"""
    from morphology import tokenize
    b = len(done) if b is None else b
    face = done[a:b]
    toks = tuple(t for t in tokenize(done) if a <= t.start and t.end <= b)
    if not toks or ''.join(t.surface for t in toks) != face:
        toks = tuple(tokenize(face))
    if not toks or ''.join(t.surface for t in toks) != face:
        return None
    rds = []
    for t in toks:
        if _is_hira(t.surface):
            rds.append(t.surface)
        elif t.has_reading and _is_hira(_hira(t.reading)):
            rds.append(_hira(t.reading))
        else:
            rds.append(None)
    return toks, tuple(rds)


def _kept_edges(done, a, b, typed, r):
    """done[a:b] の語のうち、打った読み typed と戻した読み r の前と後ろで読みの合う語の表記 (前, 後ろ)。"""
    got = _surface_tokens(done, a, b)
    if not got:
        return '', ''
    toks, rds = got
    # 接尾・非自立の1語（ーい｜時 の 時）は、前の語の打ち違いで区切られただけの語。読みが合っても残す表記にしない
    # （残すと、読み全体に置いた漢字の語が「時が替わった形」として外れていた・2026-11-01 B）
    weak = lambda t: (getattr(t, 'pos_sub', '') or '').startswith(('接尾', '非自立'))
    i, at = 0, 0
    while (i < len(toks) and rds[i] and not weak(toks[i]) and typed.startswith(rds[i], at)
           and r.startswith(rds[i], at)):
        at += len(rds[i])
        i += 1
    j, back = len(toks), 0
    while (j > i and rds[j - 1] and not weak(toks[j - 1]) and typed.endswith(rds[j - 1], 0, len(typed) - back)
           and r.endswith(rds[j - 1], 0, len(r) - back) and len(typed) - back - len(rds[j - 1]) >= at
           and len(r) - back - len(rds[j - 1]) >= at):
        back += len(rds[j - 1])
        j -= 1
    return ''.join(t.surface for t in toks[:i]), ''.join(t.surface for t in toks[j:])


def _aligned(done, a, b, typed, r):
    """IME で変換した所（done[a:b]・打った読み typed）の読みを r に戻したとき、読みの変わらない前後の語は変換した表記の
    まま残し、変わった所（とその隣の語まで広げた形）だけかなにした [(行, 置き直す所の開始, 終了, 読み)]。読み全体に漢字を
    置き直すと、長い読みでは置けずにかなのまま残っていた（ほかのしたばあい → ほかにしたばあい・2026-11-01）。"""
    got = _surface_tokens(done, a, b)
    if not got:
        return []
    toks, rds = got
    # 前から読みの合う語・後ろから読みの合う語（打った読みとも戻した読みとも合う所）
    i, at = 0, 0
    while i < len(toks) and rds[i] and typed.startswith(rds[i], at) and r.startswith(rds[i], at):
        at += len(rds[i])
        i += 1
    j, back = len(toks), 0
    while (j > i and rds[j - 1] and typed.endswith(rds[j - 1], 0, len(typed) - back)
           and r.endswith(rds[j - 1], 0, len(r) - back) and len(typed) - back - len(rds[j - 1]) >= at
           and len(r) - back - len(rds[j - 1]) >= at):
        back += len(rds[j - 1])
        j -= 1
    out = []
    for wi in (0, 1):
        for wj in (0, 1):
            x, y = max(0, i - wi), min(len(toks), j + wj)
            if x >= y:
                continue
            pa = sum(len(rds[k]) for k in range(x)) if all(rds[k] for k in range(x)) else None
            pb = sum(len(rds[k]) for k in range(y, len(toks))) if all(rds[k] for k in range(y, len(toks))) else None
            if pa is None or pb is None or pa + pb > len(r):
                continue
            mid = r[pa:len(r) - pb]
            if not mid:
                continue
            left = done[:a] + ''.join(t.surface for t in toks[:x])
            right = ''.join(t.surface for t in toks[y:]) + done[b:]
            out.append((left + mid + right, len(left), len(left) + len(mid), mid))
    return list(dict.fromkeys(out))


_MISREAD = set()   # 読みの違う漢字が置かれた行（_placed が足し、_judge が further に入れる）
_PARTICLE_KANA = ('で', 'に', 'を', 'は', 'が', 'と', 'へ', 'も', 'の')


def _place_trim(LK, alt, x, y, mid, store, dict_index, context_vec):
    """_place_kanji で [x, y) に漢字を置く。置けなければ、頭の助詞のかな1字（打った読みの記録が助詞から始まる確定:
    で＋でかけた）を外した所に置く（2026-11-01 B）。"""
    for k in range(0, 2 if len(mid) > 2 else 1):
        if k and mid[:k] not in _PARTICLE_KANA:
            continue
        try:
            got = LK._place_kanji(alt, x + k, y, mid[k:], mid[k:], store, dict_index, context_vec, ())
        except Exception:
            got = None
        if got and not (len(got) > 2 and got[2]) and got[0] != alt:
            return got
    return None


def _line_reading(text):
    from morphology import tokenize
    out = []
    for t in tokenize(text):
        if _is_hira(_hira(t.surface)) or not any(_kanji(c) for c in t.surface):
            out.append(_hira(t.surface))
        elif t.has_reading:
            out.append(_hira(t.reading))
        else:
            return None
    return ''.join(out)


def _stray_mark_extra(field):
    """欄に付く先の無い ゛゜ が在れば 1（その印を抜くのは打ち違いの戻しの1打目で、もう1打の戻しと合わせて2打になる:
    2026-11-03 うに 優先の行・挙動関連担当の切り分け）。無ければ 0。"""
    import os
    if os.environ.get('CN_TYPED_STRAY_MARK') == '0':
        return 0
    try:
        return 1 if _drop_stray_marks(field) != field else 0
    except Exception:
        return 0


def _drop_stray_marks(text):
    """付く先の無い ゛゜（前の字と合わせて1字にならない）を抜いた形。"""
    import unicodedata
    out = []
    for c in text:
        if c in '゛゜':
            prev = out[-1] if out else ''
            comb = unicodedata.normalize('NFC', prev + ('\u3099' if c == '゛' else '\u309a')) if prev else ''
            if len(comb) == 1 and comb != prev:
                out.append(c)
            continue
        out.append(c)
    return ''.join(out)


def _line_reading_alts(text, cap=32):
    """_line_reading の読みの候補。1字の漢字の語は、解析の読み（行 → くだり）のほかにその字の読み（ぎょう・こう）も
    候補にする（2026-11-03 うに 優先の行: 直した 行番号 を くだりばんごう と読んで、打った読みから遠いとして捨てていた）。"""
    from morphology import tokenize
    outs = ['']
    for t in tokenize(text):
        if _is_hira(_hira(t.surface)) or not any(_kanji(c) for c in t.surface):
            opts = [_hira(t.surface)]
        elif t.has_reading:
            opts = [_hira(t.reading)]
            if len(t.surface) == 1:
                try:
                    from kanji_onkun import readings_of
                    opts += [r for r in readings_of(t.surface) if r and r not in opts]
                except Exception:
                    pass
        else:
            return []
        outs = [o + r for o in outs for r in opts][:cap]
    return outs


def _reads_as(seg, r, allowed=()):
    """漢字を置いた所が、戻した読み（か、ほかの戻しの読み）のとおりに読めるか（戻した読みと違う読みの漢字が置かれると
    （読みの一部が別の読みの漢字に置かれる形）、読みの違う候補が並んで、正しい直しが二番と離れずに紫のまま残っていた・
    2026-11-01 B）。置き方が二度押しの字を1つにまとめた形（同じかなが3つ続く読みから1つ落とした語）は通す。
    読めない字が在れば確かめられないので通す。"""
    try:
        got = _line_reading(seg)
    except Exception:
        return True
    if got is None:
        return True
    if got == r or got in allowed:
        return True
    if any(r[i] == r[i + 1] and r[:i] + r[i + 1:] == got for i in range(len(r) - 1)):
        return True
    # 解析が読み違える置き方（まが に置いた 曲が を 曲＋が と切って きょくが と読む）: 読みの表にその読みの表記として
    # そのまま在れば通す（読みの違う候補を外すと、並ぶはずの形が消えて、決められない行を決めてしまった・2026-11-01 B）
    try:
        import reading_lattice
        reading_lattice.load()
        return any(row[0] == seg for row in reading_lattice._table.get(r, ()))
    except Exception:
        return False


def _placed(done, a, b, readings, store, dict_index, context_vec, src=None, allowed=()):
    """[(並びの費用, 漢字を置いた行, 読み)]（安い順）。src: 戻した読み → 元の読み（打った読み・解析の読み）。在れば、
    読みの変わらない語の表記を残した形も比べる。"""
    import morphology
    import last_keystroke as LK
    if len(_MISREAD) > 2000:
        _MISREAD.clear()
    pre = []
    kana = []
    for r in readings:
        alt = done[:a] + r + done[b:]
        got = _place_trim(LK, alt, a, a + len(r), r, store, dict_index, context_vec)
        text = got[0] if got and not (len(got) > 2 and got[2]) else alt
        from_lattice = False
        if text == alt:
            text = _lattice(alt, a, a + len(r), store, dict_index)
            from_lattice = text != alt
        # 読みの違う漢字が置かれた形は採らない（下の、読みの変わらない語を残して置き直す形は見る・2026-11-01 B）。
        # 格子の置き方は読みの区切りごとにその読みの表記を置くので確かめない（解析は1字の漢字を別の音で
        # 読むことがあり、格子が正しい読みの区切りに置いた形まで外していた・2026-11-01 C）
        bad = text != alt and not from_lattice and not _reads_as(text[a:len(text) - (len(done) - b)], r, allowed)
        # 読みの変わらない前後の語の表記を、読み全体に置き直した形が別の漢字に替えていれば（見せ→魅せ）、その形は採らず
        # 表記を残した形で比べる（手分けA）
        moved = False
        # ゛゜・記号まじりの1文節（IME が付く先の無い印や記号のまま変換した所）は、中の漢字も読み違えて置かれたもので、
        # 格子で読み全体に置き直した形を、前後の漢字を替えたとして外さない（2026-11-01 C）
        garbled = from_lattice and any(ch in '゛゜' or not ch.isalnum() for ch in done[a:b])
        if text != alt and not bad and not garbled and src and r in src:
            left, right = _kept_edges(done, a, b, src[r], r)
            moved = ((any(_kanji(c) for c in left) and text[a:a + len(left)] != left)
                     or (any(_kanji(c) for c in right) and not text.endswith(right + done[b:])))
        # 漢字を置いた形でも、元の変換した所より漢字が増えない（頭の語にだけ置けて後ろがかなのまま: 見て＋へんしんを）ときも、
        # 読みの変わらない語を残して変わった所に置き直す形を比べる（2026-11-01 B）
        lost = (text != alt and not bad and not moved
                and sum(1 for c in text if _kanji(c)) <= sum(1 for c in done if _kanji(c)))
        if not moved and not bad:
            c = morphology.path_cost(text)
            if c is not None:
                pre.append((c, text, r))
        # 置けたのが読みの一部だけで、かなが残った（頭のかなの語が置けず後ろの語だけ漢字になった形）ときは、
        # 読みの格子の置き方（読み全体の区切りで置く）も競わせる（2026-11-01 C）
        if text != alt and any(_is_hira(ch) for ch in text[a:len(text) - (len(done) - b)]):
            lat = _lattice(alt, a, a + len(r), store, dict_index)
            # 格子は読みの区切りごとにその読みの表記を置くので、読みの確かめ（解析の読み: 行＝こう）は掛けない
            if lat not in (alt, text):
                c = morphology.path_cost(lat)
                if c is not None:
                    pre.append((c, lat, r))
        # 読み全体に漢字を置けずかなのまま残ったときだけ、読みの変わらない語の表記を残した形も比べる
        # （置けた読みに足すと、同じ語の置き違い（田和番号）が二番に並んで決められなくなった）
        if (text == alt or moved or bad or lost) and src and r in src:
            for alt2, x, y, mid in _aligned(done, a, b, src[r], r):
                c2 = morphology.path_cost(alt2)
                if c2 is not None:
                    kana.append((c2, alt2, x, y, mid, r))
    # 置き直す所に漢字を置くのは、かなのままの並びの費用の安い順に ALIGN_PLACE だけ（全部に置くと1か所 数秒掛かった）
    kana.sort(key=lambda k: k[0])
    for n, (c, alt, x, y, mid, r) in enumerate(kana):
        pre.append((c, alt, r))
        if n >= ALIGN_PLACE:
            continue
        got = _place_trim(LK, alt, x, y, mid, store, dict_index, context_vec)
        if got and not (len(got) > 2 and got[2]) and got[0] != alt:
            c2 = morphology.path_cost(got[0])
            if c2 is not None:
                pre.append((c2, got[0], r))
                if not _reads_as(got[0][x:len(got[0]) - (len(alt) - y)], mid, allowed):
                    # 読みの違う漢字が置かれた形（だん に 弾 を置いて はじけた と読む形）: 一番より安いときだけ並ぶ形として
                    # 数える（_pick の further と同じ。2026-11-01 B）
                    _MISREAD.add(got[0])
    pre.sort()
    seen = set()
    return [x for x in pre if not (x[1] in seen or seen.add(x[1]))]


def _judge(done, a, b, texts, run, other_odd, typed=False):
    """{直した行: (費用, 紫が残らないか)}。"""
    import morphology
    import time
    seen = _Seen()
    deferred = DEFER_TWO.get()
    t0 = time.monotonic()
    for n, text in enumerate(texts):
        # 打鍵中の行（defer_heavy）で、行全体の補正し直し1回が重い（長い行で数秒〜）なら、残りは手が止まってから
        # （答えは変えない: 後回しにした印を付け、呼び手が defer_heavy=False で解き直す・挙動関連担当の測り 2026-11-02）
        if deferred is not None and n and time.monotonic() - t0 > JUDGE_DEFER_SEC:
            deferred.append('odd_respell_judge')
            return _Seen()
        try:
            g = run(text)
        except Exception:
            continue
        if not isinstance(g, dict):
            continue
        fixed = g.get('corrected') or text
        if _splits_kanji_run(done, fixed, *((a, b) if typed else ())):
            continue
        cost = morphology.path_cost(fixed)
        if cost is None or fixed == done:
            continue
        # 戻した所の外に残る紫が、もとから在ったほかの紫と同じ所なら、この所の直しとしては紫が残らない
        shift = len(text) - len(done)
        tail = len(text) - (len(done) - b)
        ok = True
        for sp in list(g.get('odd_spans') or ()) + list(g.get('unsure_spans') or ()):
            x, y = sp[0], sp[1]
            if y <= a and (x, y) in other_odd:
                continue
            if x >= tail and (x - shift, y - shift) in other_odd:
                continue
            ok = False
            break
        if not ok and fixed != text and not any(
                not ((sp[1] <= a and tuple(sp[:2]) in other_odd)) for sp in (g.get('odd_spans') or ())):
            # 迷い（直し先の決まらない所）だけが残り、補正し直しが替えた形（かなに漢字を置いた行）をもう1度通すと
            # 紫も迷いも残らず変わらないなら、その迷いは置き方の迷いで、戻した形は落ち着いている（2026-11-01・かなの行）
            try:
                g2 = run(fixed)
            except Exception:
                g2 = None
            if (isinstance(g2, dict) and (g2.get('corrected') or fixed) == fixed
                    and not g2.get('odd_spans') and not g2.get('unsure_spans')):
                ok = True
        if ok and _rare_new_noun(done, fixed):
            ok = False        # 競う形としては残す
        if fixed not in seen or cost < seen[fixed][0]:
            seen[fixed] = (cost, ok)
            if text in _MISREAD or (fixed != text and not _same_reading(fixed, text)):
                # 補正し直しが読みを替えずに漢字を置いただけ（ばあい→場合）なら、もう1か所の直しではない（手分けA）
                seen.further.add(fixed)
                seen.source[fixed] = text
            else:
                seen.further.discard(fixed)
        elif text not in _MISREAD and (fixed == text or _same_reading(fixed, text)) and ok == seen[fixed][1]:
            # 同じ行に戻しだけで届く形が在れば、重ねた直しの形とは見ない（ぬ を足して抜いた形と、ふ を抜いた形が同じ行・手分けA）
            seen.further.discard(fixed)
            seen.source.pop(fixed, None)
    return seen


def _rare_new_noun(done, fixed):
    """直した所に、一般の文章でめったに使わない漢字の名詞が出るか（短いかなの行が稀な漢字の語に替わる形: 短い行では並びの費用が
    稀な語を好む・2026-11-01）。"""
    try:
        import ime_reconvert
        from morphology import tokenize
    except Exception:
        return False
    spans = [(j1, j2) for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, done, fixed, autojunk=False).get_opcodes()
             if tag != 'equal']
    for t in tokenize(fixed):
        if t.pos != '名詞' or not any(_kanji(c) for c in t.surface):
            continue
        if not any(x < t.end and t.start < max(y, x + 1) for x, y in spans):
            continue
        if ime_reconvert._rank(t.surface) > COMMON_NEW:
            return True
    return False


def _same_reading(x, y):
    """2つの行が同じ読みか（漢字を置いただけの違いか）。読めなければ違うと見る。"""
    try:
        rx, ry = _line_reading(x), _line_reading(y)
    except Exception:
        return False
    return rx is not None and rx == ry


class _Seen(dict):
    """_judge の答え。further: 補正し直しでさらに替わった行（1打の戻しの上に、もう1か所の直しが重なった形）。"""
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.further = set()
        self.source = {}     # further の行 → 補正し直す前の行（戻しを当てただけの行）


def _stacked_inside(done, a, b, seen, best, rds=()):
    """一番の形が、戻しを当てた行に補正し直しがもう1か所の読みの直しを重ねた形で、その重ねた直しが紫の所の中にあるか。
    同じ所に別々の段の直しが2つ重なった形は、2打の戻しを1つの段が選んだのと同じで根拠が弱い（作った形: 1打を抜いた読みに、
    補正し直しが同じ所の別の1字を重ねて替え、2打替えた語になった・手分けA）。決めずに紫に残す。"""
    if best not in getattr(seen, 'further', ()):
        return False
    text = getattr(seen, 'source', {}).get(best)
    if not text:
        return False
    end = b + (len(text) - len(done))       # 戻しを当てた行での紫の所の終わり
    try:
        rt, rb = _line_reading(text), _line_reading(best)
    except Exception:
        return False
    if not rt or not rb or rt == rb:
        return False
    # 一番の行の読みが、紫の所の読みの1打の戻しで届く読みなら、重ねた形ではない（別の道で同じ行になっただけ）
    try:
        from contextual_repair import key_repairs
        head, tail = _line_reading(done[:a]) if a else '', _line_reading(done[b:]) if b < len(done) else ''
        if head is not None and tail is not None:
            for rd in rds or ():
                for r in key_repairs(rd, done[:a][-1:], done[b:][:1]):
                    if head + getattr(r, 'reading', r) + tail == rb:
                        return False
    except Exception:
        pass
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, text, best, autojunk=False).get_opcodes():
        if tag == 'equal':
            continue
        if not _same_reading(text[i1:i2] or ' ', best[j1:j2] or ' ') and i1 < end and a < max(i2, i1 + 1):
            return True
    return False


def _pick(seen, margin=MARGIN):
    """一番が紫なしで、二番と margin 以上離れていれば (行, 費用)。
    一番が戻しのまま（補正し直しで替わらない）なら、補正し直しでさらに替わった形（戻しの上にもう1か所の直しが重なる）
    は、一番より軽いときだけ並ぶ形として数える（2か所を替えたかなの形が1か所の形と費用で並んで、正しい1打の直しが
    紫に残っていた・2026-11-01 B）。"""
    if not seen:
        return None
    further = getattr(seen, 'further', ())
    ranked = sorted(seen.items(), key=lambda x: x[1][0])
    best, (cost, ok) = ranked[0]
    if not ok:
        return None
    rivals = [x for x in ranked[1:] if not (best not in further and x[0] in further)]
    # 一番と読みが同じで書き方だけ違う形（漢字を置いた形とかなのままの形）は、並ぶ形ではなく同じ答え
    # （一番に漢字を置いた形、二番が同じ読みのかなのままで、離れずに紫に残っていた・2026-11-01 B）
    if rivals:
        try:
            want = _line_reading(best)
            same = [x for x in rivals if want is not None and x[1][1] and _line_reading(x[0]) == want]
            rivals = [x for x in rivals if x not in same]
            # 同じ読みの形のうち、漢字を置いた形を採る（かなのままのほうが費用が安くても、IME で変換した所は漢字。
            # かなで書いた和語は後の kana_keep がかなに戻す）
            kanji = lambda t: sum(1 for c in t if _kanji(c))
            for x in same:
                if kanji(x[0]) > kanji(best):
                    best, cost = x[0], x[1][0]
        except Exception:
            pass
    if rivals and rivals[0][1][0] - cost < margin:
        # 一番と二番が同じ所の助詞1字だけの違い（会は・会と: どちらも1打違い）なら、例文の組で決める
        win = _particle_rival(best, rivals[0][0]) if rivals[0][1][1] else None
        if win is None:
            return None
        k = next(i for i, (c, d) in enumerate(zip(best, rivals[0][0])) if c != d)
        if win != best:
            best, cost = win, rivals[0][1][0]
        # 同じ所の字を抜いた形（会を・会へ に対する 会）は、打った字が在る所なので、助詞の組で決めた形と並べない
        rest = [x for x in rivals[1:] if x[0] != best and x[0] != best[:k] + best[k + 1:]]
        if rest and rest[0][1][0] - cost < margin:
            return None
    return best, cost


PARTICLE_SIDE_MIN = 5   # 決める助詞の組（名詞＋助詞・助詞＋述語）がこれだけ例文に在ること
PARTICLE_RATIO = 4      # もう片方の助詞の組の回数のこれだけ倍


def _particle_at_line(text, k):
    """text の k の字が 名詞の直後の助詞1字なら (助詞, 名詞, 後ろの最初の述語の基本形 or None)。"""
    import morphology
    import pair_choice
    toks = list(morphology.tokenize(text))
    for i, t in enumerate(toks):
        if t.start == k:
            if not (t.end == k + 1 and t.pos == '助詞' and i > 0 and pair_choice._noun(toks[i - 1])
                    and toks[i - 1].end == k):
                return None
            verb = next((pair_choice._base(u) for u in toks[i + 1:] if u.pos in ('動詞', '形容詞')
                         and (u.pos_sub or '').startswith('自立')), None)
            return t.surface, toks[i - 1].surface, verb
    return None


def _particle_rival(x, y):
    """x と y が同じ所の助詞1字だけ違うとき、例文の組（名詞＋助詞・助詞＋後ろの述語）がはっきり多いほう。決まらなければ None。"""
    if len(x) != len(y):
        return None
    diff = [i for i, (c, d) in enumerate(zip(x, y)) if c != d]
    if len(diff) != 1:
        return None
    k = diff[0]
    try:
        import impossible_slip
        by_verb, by_noun = impossible_slip._pair_sides()
    except Exception:
        return None
    score = []
    for t in (x, y):
        got = _particle_at_line(t, k)
        if got is None:
            return None
        p, noun, verb = got
        score.append(by_noun.get((p, noun), 0) + (by_verb.get((p, verb), 0) if verb else 0))
    if score[0] >= PARTICLE_SIDE_MIN and score[0] >= PARTICLE_RATIO * max(score[1], 1):
        return x
    if score[1] >= PARTICLE_SIDE_MIN and score[1] >= PARTICLE_RATIO * max(score[0], 1):
        return y
    return None


def _shift_face_repairs(rd):
    """読みの1字を、隣のキーのシフト面のかなに替えた読み（ほ → を: ほ の隣の わ のシフト面）。key_repairs の1打違いに
    入らない、隣＋シフトの2打（impossible_slip._with_shift_face と同じ形・2026-11-01 B）。"""
    try:
        from kana_layout import nearby_candidates, SHIFT_KANA_PAIR
    except Exception:
        return []
    out = []
    for k, ch in enumerate(rd):
        try:
            alts = nearby_candidates(ch, max_dist=1.0, include_phonetic=False, input_method='kana')
        except Exception:
            continue
        have = {x for x, _ in alts}
        for alt, dist in alts:
            other = SHIFT_KANA_PAIR.get(alt) if dist >= 1.0 else None
            # 小書きのかな（や の隣の ゅ 等）は入れない。並びの費用が同じ形がいくつも並び、比べる候補の枠（TOP）を
            # 埋めて正しい形が落ちた（2026-11-01 B）。シフト面の全角のかな（を）だけ
            if other and other not in have and other != ch and other not in 'ぁぃぅぇぉっゃゅょゎ':
                out.append(rd[:k] + other + rd[k + 1:])
    return out


COMPOUND_REACH = 8   # 紫の所から前後に広げて見るかなの字数


def _noun_faces(reading):
    import reading_lattice
    reading_lattice.load()
    # 2字以上の漢字の名詞だけ（1字の名詞の組 炎＋天 は1語の読みと変わらず、複合語の決め手にならない）
    return {f for f, _l, _r, _c, pos in reading_lattice._table.get(reading, ())
            if pos == '名詞' and len(f) >= 2 and all(_kanji(c) for c in f)}


def _dict_compound_kana(done, a, b):
    """紫の所を含む平仮名の並びが、打った読みのまま辞書の複合語（名詞＋名詞で、合わせた表記が SudachiDict の
    見出し・固有名詞を除く狭い側）として読めるか。読めるなら、その所は正しく打った複合語のことがあり、1打違いの
    別の語に替えない（紫のまま・手分けA）。"""
    try:
        import seed_japanese
    except Exception:
        return False
    if not (0 <= a < b <= len(done)) or not _is_hira(done[a:b]):
        return False
    s0 = a
    while s0 > 0 and a - s0 < COMPOUND_REACH and _is_hira(done[s0 - 1]):
        s0 -= 1
    e0 = b
    while e0 < len(done) and e0 - b < COMPOUND_REACH and _is_hira(done[e0]):
        e0 += 1
    for x in range(s0, a + 1):
        for y in range(e0, b - 1, -1):
            seg = done[x:y]
            for k in range(2, len(seg) - 1):
                left = _noun_faces(seg[:k])
                if not left:
                    continue
                right = _noun_faces(seg[k:])
                for f1 in left:
                    for f2 in right:
                        if seed_japanese.is_common_unit(f1 + f2):
                            return True
    return False


LEFTOVER_ONE = 490   # 直していない1字の語はこれより珍しいときだけ崩れた変換の残りと見る
LEFTOVER_RARE = 520   # 直した所に接する語がこれより珍しい（ime_reconvert._token_rarity）なら途中までの直し


def _deconverted(done, fixed):
    """直しが、漢字の所をその漢字の読み（字ごとの読みをつないだもの）の平仮名に戻しただけか（彷徨う → ほうこう）。
    打ち違いを戻したのではなく、変換を外しただけで、行は自然にならない（漢語の読みのかなは漢字で書く語）。
    （2026-11-03 うに 優先の行: 漢字の紫を音読みのかなに替えていた）"""
    import difflib
    import os
    if os.environ.get('CN_DECONVERT_GUARD') == '0':
        return False
    try:
        from kanji_onkun import readings_of
    except Exception:
        return False
    if done == fixed:
        return False
    # 変わった所は1か所に見る（前後の同じ字を除いた所。difflib は かなの う を前後に割って並べることがある）
    p = 0
    while p < len(done) and p < len(fixed) and done[p] == fixed[p]:
        p += 1
    q = 0
    while q < len(done) - p and q < len(fixed) - p and done[-1 - q] == fixed[-1 - q]:
        q += 1
    # 漢字の所の後ろの送りがなは、置いた平仮名の側に含める（彷徨う → ほうこう: う が共通の尻尾に入る）
    while q > 0 and _is_hira(done[len(done) - q]) and p < len(done) - q and _kanji(done[len(done) - q - 1]):
        q -= 1
    for i1, i2, j1, j2 in ((p, len(done) - q, p, len(fixed) - q),):
        src, new = done[i1:i2], fixed[j1:j2]
        while src and _is_hira(src[-1]):
            src = src[:-1]
        if not src or not any(_kanji(c) for c in src) or not all(_kanji(c) for c in src):
            return False
        if not new or not all(_is_hira(c) for c in new):
            return False
        # 後ろに続く平仮名（送りがな）も読みの一部に入れて見る
        k = j2
        while k < len(fixed) and _is_hira(fixed[k]):
            k += 1
        tail = fixed[j2:k]
        reads = ['']
        for c in src:
            reads = [r + x for r in reads for x in (readings_of(c) or [])][:64]
        if not any(new == r or (new + tail).startswith(r) and len(r) >= len(new) for r in reads):
            return False
    return True


def _new_common_one(done, ops, t):
    """1字の語 t（直した後の行の語）が、直しが新しく置いた字か: t の字が置き換えた所（直しの新しい字）の中に在り、
    その所の元の字には無く、よく使う語（ime_reconvert の段が LEFTOVER_ONE 未満）。"""
    try:
        import ime_reconvert
    except Exception:
        return False
    for tag, i1, i2, j1, j2 in ops:
        if tag in ('replace', 'insert') and j1 <= t.start and t.end <= j2:
            return t.surface not in done[i1:i2] and ime_reconvert._rank(t.surface) < LEFTOVER_ONE
    return False


def _leftover_piece(done, fixed, a=0, b=None):
    """直した所に接する語（直した字を含む語・すぐ隣の語）に、平仮名でない1字だけの語（漢字・片仮名1字）か、
    珍しい語が残るか（直した字を含まない隣の語は、元の紫の所 [a, b) の中に在った語だけ）。紫の所の一部だけを1打で戻して、崩れた変換の残り（1字の漢字・稀な語）が直した字に付いたまま
    になった形は、途中までの直し。決めずに紫に残す（隣のキー1打の作り文 1,466件で、正しく直った 64件には無く、
    別の誤りに替えた形にだけ在った・手分けA 2026-11-01）。"""
    import difflib
    try:
        import ime_reconvert
        from morphology import tokenize
    except Exception:
        return False
    ops = [o for o in difflib.SequenceMatcher(None, done, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']
    if not ops:
        return False
    lo, hi = min(o[3] for o in ops), max(o[4] for o in ops)
    b = len(done) if b is None else b
    shift = len(fixed) - len(done)
    for t in tokenize(fixed):
        if t.end < lo or t.start > hi:
            continue
        if not (t.start < hi and lo < t.end) and lo < hi:
            # 直した字を含まない隣の語は、元の紫の所の中に在った語（崩れた変換の残り）だけ見る
            s0, e0 = (t.start, t.end) if t.end <= lo else (t.start - shift, t.end - shift)
            if not (a <= s0 and e0 <= b):
                continue
        if len(t.surface) == 1 and not _is_hira(t.surface) and t.pos != '記号':
            # 直しが新しく置いた1字の語（崩れた所 ギ゜）鵜 を丸ごと 行 に替え、後ろの 番号 とつながる）は、崩れた変換の
            # 残りではない。直した所の元の字に無い字で、よく使う語なら残りと見ない（2026-11-03 うに 優先の行: 正しい
            # 答えをこの検査が止めていた）
            if (t.start < hi and lo < t.end) and _new_common_one(done, ops, t) \
                    and __import__('os').environ.get('CN_LEFTOVER_NEW_ONE') != '0':
                continue
            # 直した字を含まない1字の語は、よく使う1字の名詞（雨・靴・駅）なら正しく残った語のことが多い
            if (t.start < hi and lo < t.end) or ime_reconvert._rank(t.surface) >= LEFTOVER_ONE:
                return True
        # 珍しさは直した字を含まない語（紫の所に残った語）だけで見る。直した字を含む語は、珍しくても1打で戻した
        # 実在の語のことがある（取り掛かる・出掛ける）
        if not (t.start < hi and lo < t.end) and ime_reconvert._token_rarity(t) > LEFTOVER_RARE:
            return True
    return False


def _drop_candidate(done, a, b, rds):
    """紫の所の読みが1字で、そのキーが前か後ろのかなのキーの隣なら、その1字を余分に打った形（所ごと抜いた行）を
    (費用, 行, '') で返す。1字の所は戻しの読みが空になるので key_repairs の巻き込みでは出ず、隣のキーへの替え
    （…た地 → …たと）だけが並んでいた（手分けB）。"""
    import morphology
    import kana_layout as k
    one = [rd for rd in rds if len(rd) == 1 and 'ぁ' <= rd <= 'ゖ']
    if not one or b - a > 2:
        return None
    sides = [(c, end) for c, end in ((done[a - 1:a], -1), (done[b:b + 1], 0)) if c and 'ぁ' <= c <= 'ゖ']
    if not sides:
        return None
    try:
        near = any(0 < k.intrusion_key_distance(k.keystrokes(rd)[0], k.keystrokes(c)[end]) <= 1.0
                   for rd in one for c, end in sides)
    except Exception:
        return None
    if not near:
        return None
    text = done[:a] + done[b:]
    if not text.strip():
        return None
    cost = morphology.path_cost(text)
    return None if cost is None else (cost, text, '')


def _bad_join(done, fixed):
    """直した所に、活用の形・助詞の合わないつながりができたか: 終止形（基本形）の動詞・形容詞のすぐ後ろの ば
    （仮定の ば は仮定形に付く: 来れば・よければ）・続かない格助詞の並び（がの・をが）・行の終わりの終止形の動詞＋形容詞。1打の戻しが語の切れ目をずらしてできる形（手分けA 2026-11-01）。"""
    import difflib
    try:
        from morphology import tokenize
    except Exception:
        return False
    ops = [o for o in difflib.SequenceMatcher(None, done, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']
    if not ops:
        return False
    lo, hi = min(o[3] for o in ops), max(o[4] for o in ops)
    toks = list(tokenize(fixed))
    for x, y in zip(toks, toks[1:]):
        if y.end < lo or x.start > hi:
            continue
        if (x.pos in ('動詞', '形容詞') and (getattr(x, 'infl_form', '') or '') == '基本形'
                and y.surface == 'ば' and y.pos == '助詞'):
            return True
        # 格助詞の が・を のすぐ後ろの格助詞（がの・をが・がを）、に のすぐ後ろの が・を は続かない
        if (x.pos == '助詞' and y.pos == '助詞' and (x.pos_sub or '').startswith('格助詞')
                and ((x.surface in ('が', 'を') and y.surface in ('の', 'が', 'を', 'に'))
                     or (x.surface == 'に' and y.surface in ('が', 'を')))):
            return True
    # 行の終わりの「終止形の動詞＋形容詞」（降る良い）: 動詞の終止形は形容詞に続かない
    if len(toks) >= 2:
        tail = [t for t in toks if t.pos != '記号']
        if len(tail) >= 2:
            x, y = tail[-2], tail[-1]
            if (x.pos == '動詞' and (getattr(x, 'infl_form', '') or '') == '基本形' and y.pos == '形容詞'
                    and (y.pos_sub or '') == '自立' and y.end >= lo and x.start <= hi):
                return True
    return False


_TWO_USED = [False]   # 直前の _choose の答えが2打の戻し（_two_only）から来たか


def _keys(s):
    """読みを打鍵の並びに（かな入力: 濁点・半濁点は別のキー）。"""
    import unicodedata
    return unicodedata.normalize('NFD', s or '').replace('\u3099', '゛').replace('\u309a', '゜')


def _key_distance(x, y):
    d = list(range(len(y) + 1))
    for i, cx in enumerate(x, 1):
        p, d[0] = d[0], i
        for j, cy in enumerate(y, 1):
            p, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, p + (cx != cy))
    return d[-1]


def _typed_field_reading(text):
    """欄の、打った読み（平仮名はそのまま、変換した所は PC で打った読みの記録）。記録の無い変換した所が在れば None。"""
    parts = _typed_field_parts(text)
    if parts is None:
        return None
    return ''.join(p[0] for p in parts)


def _typed_field_parts(text):
    """_typed_field_reading の、所ごとの読みの候補の並び（先頭が記録の最初の読み）。記録の無い変換した所が在れば None。
    1字の漢字だけで確定した所は、記録の読み（その字を前に単独で打ったときの読み）がこの所の読みとは限らない
    （時＝とき／じ）ので、その字の読みも候補に足す（2026-11-03 記録のある行: 打った読みを「とき」と取って、1打の直しが
    3打離れたとして捨てられていた）。"""
    try:
        from kanji_guess import ime_readings_for
    except Exception:
        return None
    out = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if _is_hira(c) or c in 'ー゛゜' or c.isspace() or c in '。、，．,.！？!?「」『』':
            out.append((c if (_is_hira(c) or c in 'ー゛゜') else '',))
            i += 1
            continue
        j = i
        while j < n and not (_is_hira(text[j]) or text[j].isspace() or text[j] in '。、，．,.！？!?「」『』'):
            j += 1
        # 1回の確定は後ろの送り仮名・助詞や次の漢字まで含むことがある（開け手下さい）。句読点・空白までの長い方から引く
        got = None
        k = j
        while k < n and not (text[k].isspace() or text[k] in '。、，．,.！？!?「」『』'):
            k += 1
        for y in range(k, j - 1, -1):
            try:
                rs = [_hira(r) for r in (ime_readings_for(text[i:y]) or ())]
            except Exception:
                rs = []
            rs = [r for r in rs if r and all('ぁ' <= ch <= 'ゖ' or ch in 'ー゛゜' for ch in r)]
            if rs:
                got = (y, rs)
                break
        if got is None:
            return None
        y, rs = got
        opts = list(dict.fromkeys(rs))
        if y - i == 1 and not _is_hira(c) and not ('ァ' <= c <= 'ヶ'):
            try:
                from kanji_onkun import readings_of
                opts += [r for r in readings_of(c) if r and r not in opts]
            except Exception:
                pass
        out.append(tuple(opts))
        i = y
    return out


def _typed_field_readings(text, cap=32):
    """打った読みの候補（所ごとの候補の組み合わせ、cap 通りまで）。記録が無ければ []。"""
    parts = _typed_field_parts(text)
    if parts is None:
        return []
    outs = ['']
    for opts in parts:
        outs = [o + r for o in outs for r in opts][:cap]
    return outs


def _far_from_typed(done, fixed, limit=1):
    """PC で打った読みの記録が欄に在るとき、直した欄の読みが打った読みから limit 打より離れていれば True。
    1打（2打）の戻しで直したはずの答えが、補正し直しや漢字の置き方で打った読みからさらに離れた形
    （隣のキー1打の作り文 1,466件・記録ありで、正しく直った行はどれも打った読みから1打、別の誤りの半分ほどは2打以上だった・
    手分けA 2026-11-01）。記録が無ければ見ない。"""
    typed = _typed_field_reading(done)
    if not typed or typed == done:
        return False
    got = _line_reading(fixed)
    if not got:
        return False
    # 打った読み（_typed_field_reading）は句読点・空白を落としているので、直した読みからも落として比べる（。の1字が
    # 1打に数えられ、1打の直しがどれも「2打離れた」として捨てられていた: 2026-11-03 記録のある行）
    got = ''.join(c for c in got if not (c.isspace() or c in '。、，．,.！？!?「」『』'))
    alts = _typed_field_readings(done) if os.environ.get('CN_TYPED_ONE_KANJI') != '0' else [typed]
    if os.environ.get('CN_TYPED_STRAY_MARK') != '0':
        # 付く先の無い ゛゜（濁った字の後ろの ゜ など）は、抜くのが打ち違いの戻しの1つ目。打った読みからも抜いた形を
        # 候補にする（2026-11-03 うに 優先の行: 付く先の無い印と別の1打を戻した正しい答えが、2打離れたとして捨てられていた）
        alts = list(alts or [typed])
        alts += [x for x in (_drop_stray_marks(t) for t in list(alts)) if x and x not in alts]
    gots = [got]
    if os.environ.get('CN_FIXED_ONE_KANJI') != '0':
        strip = lambda x: ''.join(c for c in x if not (c.isspace() or c in '。、，．,.！？!?「」『』'))
        gots += [strip(x) for x in _line_reading_alts(fixed) if strip(x) != got]
    return min(_key_distance(_keys(t), _keys(g)) for t in (alts or [typed]) for g in gots) > limit


def _mark_replaced(done, fixed):
    """欄に打った ゛゜ のキーを、直しが別のかなに替えたか（あ゛ → あせ・お゛ → おけ）。付く先の無い ゛゜ は、
    前の字を隣の濁れる字に戻す（か゛＝が）か印を抜くのが1打の戻しで、印のキーを別のかなにした答えは
    打ち違いの戻しとして通らない形が多かった（隣のキー1打の作り文・記録あり: 正しく直った行は印を残すか抜いていた・
    手分けA 2026-11-01）。打った読みが分からなければ見ない。"""
    import difflib
    typed = _typed_field_reading(done)
    if typed and typed != done:
        got = _line_reading(fixed)
        got = ''.join(c for c in (got or '') if not (c.isspace() or c in '。、，．,.！？!?「」『』'))
    else:
        # 記録が無ければ、直した所ごとに、元の側（平仮名と印はそのまま、漢字の所は解析の読み）と直した側の読みで比べる
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, done, fixed, autojunk=False).get_opcodes():
            if tag != 'replace' or not any(c in '゛゜' for c in done[i1:i2]):
                continue
            src = done[i1:i2]
            parts = []
            k = 0
            while k < len(src):
                if _is_hira(src[k]) or src[k] in 'ー゛゜':
                    parts.append(src[k])
                    k += 1
                    continue
                m = k
                while m < len(src) and not (_is_hira(src[m]) or src[m] in 'ー゛゜'):
                    m += 1
                rd = _line_reading(src[k:m])
                if not rd:
                    parts = None
                    break
                parts.append(rd)
                k = m
            got = _line_reading(fixed[j1:j2]) if j2 > j1 else ''
            if parts is None or got is None:
                continue
            if _mark_swapped(_keys(''.join(parts)), _keys(got)):
                return True
        return False
    if not typed or not any(c in '゛゜' for c in typed) or not got:
        return False
    return _mark_swapped(_keys(typed), _keys(got))


def _mark_swapped(tk, gk):
    import difflib
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, tk, gk, autojunk=False).get_opcodes():
        if tag == 'replace' and any(c in '゛゜' for c in tk[i1:i2]) and not any(c in '゛゜' for c in gk[j1:j2]):
            return True
    return False


@lru_cache(maxsize=512)
def _ime_phonetic_cached(text):
    try:
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            if not ime.available:
                return ()
            got = ime.phonetic(text)
    except Exception:
        return ()
    got = _hira(got or '')
    return (got,) if got and all(_is_hira(c) or c == 'ー' for c in got) else ()


def _ime_phonetic(text):
    """PC の IME がその字の並びを読む読み（平仮名）の並び。IME が無い（雲）・読めなければ []。"""
    import os
    if not text or os.environ.get('CN_RESEGMENT_IME') == '0':
        return []
    return list(_ime_phonetic_cached(text))


def _choice_overlaps(line, fixed):
    """直した所に掛かる元の行のかなの並びのどこかが、本人の選び直しの元の表記として覚えてあるか。"""
    try:
        import last_choice
        ch = last_choice.active()
    except Exception:
        return False
    if ch is None or not getattr(ch, '_units', None):
        return False
    kana = lambda c: 'ぁ' <= c <= 'ゖ' or c == 'ー'
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes():
        if tag == 'equal':
            continue
        rs, re_ = i1, max(i2, i1 + 1)
        while rs > 0 and kana(line[rs - 1]) and i1 - rs < 8:
            rs -= 1
        while re_ < len(line) and kana(line[re_]) and re_ - i2 < 8:
            re_ += 1
        for x in range(rs, i1 + 1):
            for y in range(max(i2, x + 2), re_ + 1):
                try:
                    if ch.has(line[x:y]):
                        return True
                except Exception:
                    return False
    return False


def _resegment_suffix(done, a, b, rds, run, other_odd=()):
    """紫の所 [a, b) の読みを、すぐ前の漢字の名詞の読みとつないで区切り直し、「前の名詞を伸ばした名詞＋接尾の名詞1字」
    （おきゃく｜さまよう → お客様｜用）に置いた行が、元の行より GAIN 以上軽く、紫が残らず、そう置ける形が1つだけなら
    その行。IME が名詞の後ろの読みを別の語（動詞）に切って変換した形を、読みは変えずに戻す（2026-11-03 うに 優先の行）。
    名詞＋接尾は解析がそう切る（接尾の語と読む）ときだけ。"""
    import morphology
    try:
        import reading_lattice
        reading_lattice.load()
        table = reading_lattice._table
    except Exception:
        return None
    toks = list(morphology.tokenize(done))
    prev = [t for t in toks if t.end == a and t.pos == '名詞' and any(_kanji(c) for c in t.surface)
            and t.has_reading and t.reading]
    inside = False
    if not prev:
        # 紫の所が名詞から始まる（前の名詞ごと1度に確定した記録で、紫の所が名詞まで広がった）ときは、その名詞を前の名詞に
        head_t = [t for t in toks if t.start == a and t.end < b and t.pos == '名詞' and any(_kanji(c) for c in t.surface)
                  and t.has_reading and t.reading]
        if not head_t:
            return None
        prev, inside = head_t, True
    t = prev[0]
    pr = _hira(t.reading)
    base = morphology.path_cost(done)
    if base is None:
        return None
    # 紫の後ろの送りがな（彷徨｜う）も読みに入れる。どこまでが送りがなかは分からないので、後ろのかなの各長さで見る。
    # 読みは PC で打った読みの記録を先に
    hi = b
    while hi < len(done) and _is_hira(done[hi]):
        hi += 1
    try:
        from kanji_guess import ime_readings_for
    except Exception:
        ime_readings_for = None
    found = {}
    for b2 in range(b, hi + 1):
        tail_kana = done[b:b2]
        cands = []
        wholes = []
        if ime_readings_for is not None:
            try:
                for key, extra in ((done[a:b2], ''), (done[a:b], tail_kana)):
                    cands += [_hira(r) + extra for r in (ime_readings_for(key) or ())]
                # 前の名詞から送りがなまでを1回で確定した記録（おきゃくさまよう を1度に変換した）
                wholes += [_hira(r) for r in (ime_readings_for(done[t.start:b2]) or ())]
            except Exception:
                pass
        cands += [r + tail_kana for r in rds if r]
        wholes += [rd for rd in cands if rd] if inside else [pr + rd for rd in cands if rd]
        # 打った読みの記録が無ければ、PC の IME の読み（彷徨う → さまよう。解析の辞書に無い表記）も見る
        wholes += _ime_phonetic(done[t.start:b2])
        for whole in dict.fromkeys(wholes):
            if not whole or not all(_is_hira(c) or c == 'ー' for c in whole) or not whole.startswith(pr[:1]):
                continue
            for k in range(len(pr) + 1, len(whole)):
                head, tail = whole[:k], whole[k:]
                hf = [r[0] for r in table.get(head, ()) if len(r) > 4 and r[4] == '名詞' and r[0].startswith(t.surface)
                      and r[0] != t.surface]
                tf = [r[0] for r in table.get(tail, ()) if len(r) > 4 and r[4] == '名詞' and len(r[0]) == 1
                      and _kanji(r[0])]
                for h in dict.fromkeys(hf):
                    for x in dict.fromkeys(tf):
                        if h.endswith(x):
                            continue      # 同じ接尾の字を重ねる形（お客様｜様）は置かない
                        face = h + x
                        tt = list(morphology.tokenize(face))
                        if len(tt) != 2 or tt[0].surface != h or '接尾' not in (tt[1].pos_sub or ''):
                            continue
                        line = done[:t.start] + face + done[b2:]
                        c = morphology.path_cost(line)
                        if c is not None:
                            found[line] = c
    if not found:
        return None
    ranked = sorted(found.items(), key=lambda x: x[1])
    line, c = ranked[0]
    # 置ける形が2つ以上なら、一番が二番より MARGIN 以上軽いときだけ（お客様｜用 と お客様｜様）
    if len(ranked) > 1 and ranked[1][1] - c < MARGIN:
        return None
    if base - c < min(GAIN, GAIN_SHARE * base):
        return None
    try:
        got = run(line)
    except Exception:
        return None
    if not isinstance(got, dict) or (got.get('corrected') or line) != line or got.get('odd_spans'):
        return None
    return line


def _choose(done, a, b, rds, run, store, dict_index, context_vec, other_odd=(), typed=False):
    """(直した行) か None。other_odd: 同じ行のほかの紫（done の位置）。そこに残る紫は数えない。

    1打の戻しで一番が決まっても、2打の戻し（2か所の打ち違い: 1打だけ戻すと途中までの直しになる）の形がそれより
    MARGIN 以上自然なら、1打の答えは途中までの直し。2打の一番も二番と離れていればそれを採り、並べば紫のまま。"""
    import morphology
    from contextual_repair import key_repairs
    base = morphology.path_cost(done)
    if base is None:
        return None
    if _dict_compound_kana(done, a, b):
        return None
    tried = set(rds)
    reps = []
    src = {}      # 戻した読み → 元の読み（変わらない語の表記を残す形に使う）
    for rd in rds:
        for r in list(key_repairs(rd, done[:a][-1:], done[b:][:1])) + _shift_face_repairs(rd):
            r = getattr(r, 'reading', r)
            if r and r not in tried:
                tried.add(r)
                reps.append(r)
                src[r] = rd
    pre = _placed(done, a, b, reps, store, dict_index, context_vec, src, tried)
    drop = _drop_candidate(done, a, b, rds)
    if drop is not None:
        pre = sorted(pre + [drop])
    # 漢字を置いた時点で一番軽い形でも元の行より SCREEN（＝GAIN）軽くならなければ、補正し直しても直す形にはまず
    # ならない（雲の紫の行 65 か所で、直った所はどれも置いた時点で 9,000 以上軽かった）。補正し直しの前に見送る
    need = min(GAIN, GAIN_SHARE * base)
    if not pre:
        return None
    if base - pre[0][0] < min(SCREEN, need):
        return _two_only(done, a, b, pre, tried, base, run, store, dict_index, context_vec, other_odd, typed)
    # 同じ行になった候補は1度だけ補正し直す（PC で紫1か所 6回×約3秒 掛かった・2026-11-01）
    texts = list(dict.fromkeys(t for _c, t, _r in pre[:TOP]))
    # 二番との差は短い行でも MARGIN のまま（割合にすると、かなの行で並んだ二番を越えて稀な漢字の語を選んだ）
    margin = MARGIN
    seen1 = _judge(done, a, b, texts, run, other_odd, typed)
    got = _pick(seen1, margin)
    if got is None or base - got[1] < need:
        return None
    best, cost = got
    if _stacked_inside(done, a, b, seen1, best, rds):
        return None
    reps2 = []
    for _c, _t, r1 in pre[:SECOND_FROM]:
        for r in key_repairs(r1, done[:a][-1:], done[b:][:1]):
            r = getattr(r, 'reading', r)
            if r and r not in tried:
                tried.add(r)
                reps2.append(r)
                src[r] = src.get(r1, r1)
    pre2 = [x for x in _placed(done, a, b, reps2, store, dict_index, context_vec, src, tried) if x[0] < cost - margin]
    if not pre2:
        return best
    seen2 = _judge(done, a, b, list(dict.fromkeys(t for _c, t, _r in pre2[:SECOND_TOP])), run, other_odd, typed)
    if not any(ok and c < cost - margin for c, ok in seen2.values()):
        return best
    seen2[best] = (cost, True)
    got2 = _pick(seen2, margin)
    return got2[0] if got2 else None


_DROP_KANA = ('あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん'
              'がぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽっゃゅょー')


def _choose_dropped(done, a, b, rds, run, store, dict_index, context_vec, other_odd=(), typed=False):
    """紫の所の読みに1字を足した形（かな入力の脱字: ならんで → なんで）だけで見る。決め方は1打と同じ
    （GAIN・MARGIN・紫が残らない）。うに 2026-11-02 の画面（脱字の行が直らず紫のまま）。"""
    import morphology
    base = morphology.path_cost(done)
    if base is None or _dict_compound_kana(done, a, b):
        return None
    tried = set(rds)
    reps, src = [], {}
    for rd in rds:
        if not rd or len(rd) > 8:
            continue
        for k in range(len(rd) + 1):
            for ch in _DROP_KANA:
                r = rd[:k] + ch + rd[k:]
                if r not in tried:
                    tried.add(r)
                    reps.append(r)
                    src[r] = rd
    pre = _placed(done, a, b, reps, store, dict_index, context_vec, src, tried)
    need = min(GAIN, GAIN_SHARE * base)
    if not pre or base - pre[0][0] < min(SCREEN, need):
        return None
    texts = list(dict.fromkeys(t for _c, t, _r in pre[:TOP]))
    seen = _judge(done, a, b, texts, run, other_odd, typed)
    # 抜けの戻しは候補が多く、費用だけでは別の語に化けやすい（onekey3 で誤りが増えた）。左の 名詞＋助詞 との組が
    # 例文か組の表に在る形が1つだけのときだけ採る
    got = _pick_by_frame(done, a, b, seen, MARGIN)
    if got is None or base - got[1] < need:
        return None
    return got[0]


def _pick_by_frame(done, a, b, seen, margin):
    """一番と並ぶ形（MARGIN の内）のうち、紫の所の述語が左の 名詞＋助詞 と語の組の表（collocation_table）の組に
    なる形が1つだけなら、それ（列に＋並ぶ・学ぶ／舞う が並んだ時の 並ぶ）。決まらなければ None。"""
    try:
        import morphology
        import collocation_repair as C
        triples = C.table()[0]
    except Exception:
        return None
    try:
        import pair_choice
        pairs = (pair_choice._table() or ({}, {}))[0]
    except Exception:
        pairs = {}
    ranked = sorted(((c, t) for t, (c, ok) in seen.items() if ok), key=lambda x: x[0])
    if not ranked:
        return None
    close = [(c, t) for c, t in ranked if c - ranked[0][0] < margin]
    hits = []
    for c, t in close:
        toks = list(morphology.tokenize(t))
        shift = len(t) - len(done)
        e2 = b + shift
        for i, p, v, k in C._frames(toks, t):
            # 組の表か、例文（Tatoeba）の 名詞＋助詞＋述語 の組に3回以上在る
            if toks[k].start < e2 and a < toks[k].end and (
                    (toks[i].surface, p, v) in triples or pairs.get('\t'.join((p, toks[i].surface, v)), 0) >= 3):
                hits.append((t, c))
                break
    if len(hits) != 1:
        return None
    return hits[0]


import os
import contextvars as _cv
# 打鍵中の行は2打の戻しを後回しにする（挙動関連担当 2026-11-02: 1字目に約10秒・_two_only の補正し直し）。
# 後回しにした行は答えに deferred_stages が付き、呼び手が手の止まった時に後回しなしで解析し直す。答えはそこで同じになる
JUDGE_DEFER_SEC = 1.0   # 打鍵中の行で、_judge の補正し直しがこの秒を超えたら残りを後回しにする
DEFER_TWO = _cv.ContextVar('odd_respell_defer_two', default=None)   # None: 後回しにしない／list: 後回しにした印を足す


def _defer(name):
    """打鍵中の行（DEFER_TWO が list）なら name を後回しの印に足して False（その段は手が止まってから）。"""
    deferred = DEFER_TWO.get()
    if deferred is None:
        return True
    if name not in deferred:
        deferred.append(name)
    return False


def _two_only(done, a, b, pre, tried, base, run, store, dict_index, context_vec, other_odd, typed):
    deferred = DEFER_TWO.get()
    if deferred is not None:
        deferred.append('odd_respell_two')
        return None
    return _two_only_now(done, a, b, pre, tried, base, run, store, dict_index, context_vec, other_odd, typed)


def _two_only_now(done, a, b, pre, tried, base, run, store, dict_index, context_vec, other_odd, typed):
    """1打の戻しではどれも軽くならないとき、2打の戻し（小書きと隣のキーの2か所の打ち違い）だけで見る。
    行のほかの所がもう正しいと、1打の形がどれも SCREEN に届かず、2打の形を見ないまま紫に残っていた（ほかの所に
    打ち違いが残っている間だけ直っていた・2026-11-01 B）。決め方は1打と同じ（GAIN・MARGIN・紫が残らない）。"""
    from contextual_repair import key_repairs
    reps2 = []
    for _c, _t, r1 in pre[:SECOND_FROM]:
        for r in key_repairs(r1, done[:a][-1:], done[b:][:1]):
            r = getattr(r, 'reading', r)
            if r and r not in tried:
                tried.add(r)
                reps2.append(r)
    pre2 = _placed(done, a, b, reps2, store, dict_index, context_vec, None, tried)
    need = min(GAIN, GAIN_SHARE * base)
    if not pre2 or base - pre2[0][0] < min(SCREEN, need):
        return None
    seen = _judge(done, a, b, list(dict.fromkeys(t for _c, t, _r in pre2[:SECOND_TOP])), run, other_odd, typed)
    got = _pick(seen, MARGIN)
    if got is None or base - got[1] < need:
        return None
    _TWO_USED[0] = True
    return got[0]


def _detail(cur, fixed):
    p = 0
    while p < min(len(cur), len(fixed)) and cur[p] == fixed[p]:
        p += 1
    q = 0
    while q < min(len(cur), len(fixed)) - p and cur[len(cur) - 1 - q] == fixed[len(fixed) - 1 - q]:
        q += 1
    return [cur[p:len(cur) - q], fixed[p:len(fixed) - q], '紫の所の打ち違い']


def _stray_long_marks(line):
    """助詞のすぐ後ろで1語に切れた ー（かな入力で ー の隣のキーのかなを打つつもりが ー になり、IME が後ろを記号まじりに
    変換した形）から、次の助詞・記号の手前まで。紫が無くても見る（決め方はほかの紫と同じ GAIN・MARGIN なので、
    戻しがはっきり自然なときだけ直る・2026-11-01 B）。"""
    try:
        from morphology import tokenize
        toks = list(tokenize(line))
    except Exception:
        return []
    out = []
    for i, t in enumerate(toks):
        if t.surface != 'ー' or i == 0 or toks[i - 1].pos != '助詞' or toks[i - 1].end != t.start:
            continue
        j = i
        while (j + 1 < len(toks) and toks[j + 1].start == toks[j].end and toks[j + 1].pos not in ('助詞', '記号', '助動詞')
               and toks[j + 1].end - t.start <= MAX_READ):
            j += 1
        out.append((t.start, toks[j].end))
    return out


_ALT_MARK = {'\u3099': '゛', '\u309a': '゜', '\uff9e': '゛', '\uff9f': '゜'}


def _spacing_marks(text):
    """付く先の無い結合用・半角の濁点・半濁点（ギ＋結合の半濁点、空白＋結合の半濁点 など。IME・貼り付け・NFKC で
    来る形）を ゛゜ 1字にした文字列。合成できる所（か＋結合の濁点＝が）と、半角カタカナに付く半角の濁点は変えない。"""
    import unicodedata
    out = []
    i = 0
    while i < len(text):
        c = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ''
        if c == ' ' and nxt in '\u3099\u309a':
            out.append(_ALT_MARK[nxt])
            i += 2
            continue
        if c in _ALT_MARK:
            prev = text[i - 1] if i else ''
            keep = (c in '\uff9e\uff9f' and prev and '\uff66' <= prev <= '\uff9d') or \
                   (c in '\u3099\u309a' and prev and len(unicodedata.normalize('NFC', prev + c)) == 1)
            out.append(c if keep else _ALT_MARK[c])
        else:
            out.append(c)
        i += 1
    return ''.join(out)


def _map_spans(src, dst, spans):
    """src の上の [(開始, 終了)] を dst の上に写す（変わった所に掛かる端は、その所の端まで広げる）。"""
    ops = difflib.SequenceMatcher(None, src, dst, autojunk=False).get_opcodes()

    def pos(p, end):
        for tag, i1, i2, j1, j2 in ops:
            if tag == 'equal' and i1 <= p <= i2:
                return j1 + (p - i1)
            if i1 <= p < i2 or (end and i1 < p <= i2):
                return j2 if end else j1
        return len(dst) if end else 0
    out = []
    for sp in spans or ():
        x, y = pos(sp[0], False), pos(sp[1], True)
        if x < y:
            out.append((x, y))
    return out


def _field(text, a, b):
    """text の a の所を含む欄（タブで区切った所）の (開始, 終了)。タブが無ければ行全体。"""
    fs = text.rfind('\t', 0, a) + 1
    fe = text.find('\t', a)
    return fs, (len(text) if fe < 0 else fe)


def repair_line(line, result, run, store, dict_index, context_vec=None, decided=(), input_method='kana'):
    """結合用・半角・空白＋結合の ゛゜ を ゛゜ 1字にしてから見る。直さなかった所の字は元のまま返す。"""
    norm = _spacing_marks(line) if isinstance(line, str) else line
    if norm == line or not isinstance(result, dict) or (result.get('corrected') or line) != line:
        return _repair_line(line, result, run, store, dict_index, context_vec, decided, input_method)
    res = dict(result)
    res['corrected'] = norm
    for key in ('odd_spans', 'face_doubt_spans'):
        if result.get(key):
            res[key] = _map_spans(line, norm, [tuple(x[:2]) for x in result[key]])
    dec = _map_spans(line, norm, decided)
    out = _repair_line(norm, res, run, store, dict_index, context_vec, dec, input_method)
    if out is res or (out.get('corrected') or norm) == norm:
        return result
    fixed = out.get('corrected')
    back = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, norm, fixed, autojunk=False).get_opcodes():
        if tag == 'equal':
            # 直さなかった所は元の行の字（結合用の印もそのまま）
            o = _map_spans(norm, line, [(i1, i2)])
            back.append(line[o[0][0]:o[0][1]] if o and (o[0][1] - o[0][0]) >= (i2 - i1) else fixed[j1:j2])
        else:
            back.append(fixed[j1:j2])
    fixed = ''.join(back)
    out = dict(out)
    out['corrected'] = fixed
    ops = [o for o in difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']
    out['changed'] = bool(ops)
    out['spans'] = [[o[3], o[4]] for o in ops]
    out['original_spans'] = [[o[1], o[2]] for o in ops]
    out['odd_spans'] = _map_spans(norm, line, out.get('odd_spans'))
    return out


def _repair_line(line, result, run, store, dict_index, context_vec=None, decided=(), input_method='kana'):
    """result: 行のほかの補正の答え。run(text): 後段を通さない補正。直せなければ result のまま。"""
    if isinstance(result, dict) and input_method == 'romaji' and os.environ.get('CN_ROMAJI_RESPELL') != '0' \
            and _defer('odd_respell_romaji'):
        return _romaji_repair(line, result, run, store, dict_index, context_vec, decided)
    if not isinstance(result, dict) or input_method != 'kana':
        return result
    odd = []
    face_doubt = {tuple(sp[:2]) for sp in (result.get('face_doubt_spans') or ())}
    spans = [tuple(sp[:2]) for sp in (result.get('odd_spans') or ()) if tuple(sp[:2]) not in face_doubt]
    # 付く先の無い ゛゜（かなに付けば1字に合成される。単独で残るのは打ち違い）は、紫が無くても見る
    # （ぎ に ゜ を重ねて打つと IME が記号まじりに変換し、紫の付かない行がある・うにさん 11-01）
    done0 = result.get('corrected') or line
    if done0 == line:
        spans += [(i, i + 1) for i, c in enumerate(line) if c in '゛゜' and not _voice_mark(line, i)
                  and not any(x <= i < y for x, y in spans)]
    spans += [sp for sp in _stray_long_marks(line) if not any(x < sp[1] and sp[0] < y for x, y in spans)]
    # 重なる紫はひとつの所として見る（内側の小さな紫だけを直すと、外側の迷いが残ったまま決めてしまう）
    for x, y in sorted(spans):
        if odd and x < odd[-1][1]:
            odd[-1] = (odd[-1][0], max(odd[-1][1], y))
        else:
            odd.append((x, y))
    if not odd:
        return _stray_mark_repair(line, result, run, store, dict_index, context_vec, decided)
    # 紫の中の付く先の無い ゛゜ も、左へ広げた読み直し（入れ替わり: 明日マテに゛ → 明日までに）を先に見る。
    # 紫の所だけの読みでは ゛ を打った字に届かない（新しい試験 2026-11-02）
    if os.environ.get('CN_STRAY_IN_PURPLE') != '0' and any(
            c in '゛゜' and not _voice_mark(line, i) and any(x <= i < y for x, y in odd) for i, c in enumerate(line)
    ) and _defer('odd_respell_stray'):
        r2 = _stray_mark_repair(line, result, run, store, dict_index, context_vec, decided)
        done2 = r2.get('corrected') or line
        if done2 != (result.get('corrected') or line):
            result = r2
            odd = [sp for sp in odd if _to_done(line, done2, *sp) is not None]
            if not odd:
                return result
    done = result.get('corrected') or line
    out = result
    for a0, b0 in sorted(odd, reverse=True):
        if any(x < b0 and a0 < y for x, y in (decided or ())):
            continue
        # 声の表記（あ゛ー）を含む所・接する所（後ろの ー だけの紫）は打ち違いとして読み直さない
        if any(line[k] in '゛゜' and _voice_mark(line, k) for k in range(max(0, a0 - 2), min(b0 + 1, len(line)))):
            continue
        cur = out.get('corrected') or line
        at = _to_done(line, cur, a0, b0)
        if at is None:
            continue
        # タブは欄の終わり（打った行＋タブ＋メモ の行で、紫の所の読み・行の費用・補正し直しにメモまで入れない・手分けA）
        fs, fe = _field(cur, *at)
        field = cur[fs:fe]
        fa, fb = at[0] - fs, min(at[1], fe) - fs
        if fa >= fb:
            continue
        span = _span_reading(field, fa, fb, dict_index=dict_index)
        if span is None:
            continue
        a, b, rds = span
        try:
            others = set()
            for x0, y0 in odd:
                if (x0, y0) != (a0, b0):
                    m = _to_done(line, cur, x0, y0)
                    if m and fs <= m[0] and m[1] <= fe:
                        others.add((m[0] - fs, m[1] - fs))
            _TWO_USED[0] = False
            fixed = _choose(field, a, b, rds, run, store, dict_index, context_vec, others,
                            _typed_run(field, fa, fb) is not None)
            if fixed is None and os.environ.get('CN_DROPPED_KANA') != '0' and _defer('odd_respell_dropped'):
                # 1打の戻しで決まらない紫は、最後に1字の抜け（脱字）を戻す形を見る（低い優先度: 打ち違いの形が先）
                fixed = _choose_dropped(field, a, b, rds, run, store, dict_index, context_vec, others,
                                        _typed_run(field, fa, fb) is not None)
        except Exception:
            fixed = None
        if fixed and (_leftover_piece(field, fixed, a, b) or _bad_join(field, fixed) or _deconverted(field, fixed)
                      or _far_from_typed(field, fixed, (2 if _TWO_USED[0] else 1) + _stray_mark_extra(field)) or _mark_replaced(field, fixed)):
            fixed = None
        if not fixed and os.environ.get('CN_RESEGMENT_SUFFIX') != '0':
            # 打ち違いの戻しで決まらない紫は、前の名詞と読みをつないで区切り直す形（名詞＋接尾の語）を見る
            try:
                fixed = _resegment_suffix(field, a, b, rds, run)
            except Exception:
                fixed = None
        if not fixed:
            continue
        fixed = cur[:fs] + fixed + cur[fe:]
        try:
            import kana_keep as _kk
            fixed = _kk.wago_kana_respell(line, fixed)
        except Exception:
            pass
        if os.environ.get('CN_RESPELL_CHOICE') != '0' and _choice_overlaps(line, fixed):
            # 本人が選び直した元の表記（くたせさい→下さい と選んだ）に掛かる読み直しは採らない。選び直しは表示で効く
            # （2026-11-03 tests_mixed_choice_scope）
            continue
        if os.environ.get('CN_RESPELL_MIXED_KATA') != '1':
            # 混ぜ書きの片仮名の名詞（スくりーん）は書いたままの語（tests_mixed_nominal_argument の決まり）。
            # その中を書き換える読み直しは採らない（2026-11-03）
            try:
                import broken_shape as _bs
                mixed = _bs.mixed_katakana_spans(line)
                if mixed and any(o[0] != 'equal' and any(ms < max(o[2], o[1] + 1) and o[1] < me for ms, me in mixed)
                                 for o in difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes()):
                    continue
            except Exception:
                pass
        ops = [o for o in difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']
        if not ops or any(x < o[2] and o[1] < y for o in ops for x, y in (decided or ())):
            continue
        near = [(o[1], o[2]) for o in ops]
        new = dict(out)
        new.update({'original': line, 'corrected': fixed, 'changed': True,
                    'details': list(out.get('details') or []) + [_detail(cur, fixed)],
                    'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
        for key in ('odd_spans', 'unsure_spans'):
            new[key] = [sp for sp in (out.get(key) or ()) if not any(x < sp[1] and sp[0] < y for x, y in near)
                        and not (a0 <= sp[0] and sp[1] <= b0)]
        if 'odd_reasons' in out:
            new['odd_reasons'] = [r for r in (out.get('odd_reasons') or ())
                                  if not any(x < r[1] and r[0] < y for x, y in near + [(a0, b0)])]
        out = new
    if out is result:
        out = _stray_mark_repair(line, result, run, store, dict_index, context_vec, decided)
    return out


# ------------------------------------------------------------
# ローマ字入力で英字が残った紫（打鍵順の入れ替わり・隣のキーの打ち違い・巻き込みの余分な1打）
# 新しい試験（2026-11-02・作った30文の打鍵順入れ替え／ローマ字の隣キー）で、英字の残る行は紫は付くがほとんど
# 直らなかった（入れ替え 241件で直る11）。英字は IME が音にできなかった打鍵。打った読み（かな＋英字）を打鍵に戻し、
# 隣り合う2打の入れ替え・隣のキーへの置き換え・1打の抜きで英字の残らない読みにして、かなの1打の戻しと同じ決め方
# （漢字を置く→補正し直し→二番と離れていれば採る）で選ぶ。
# ------------------------------------------------------------
_ROMAJI_WIDEN = 2      # 紫の語から左右へ広げる語の数（IME の文節を跨いだ入れ替わり: 能ｈｃい合わせ）
_HALF = str.maketrans({chr(0xFF41 + i): chr(0x61 + i) for i in range(26)} | {chr(0xFF21 + i): chr(0x61 + i) for i in range(26)})
_FULL_LETTERS = frozenset(chr(0xFF41 + i) for i in range(26)) | frozenset(chr(0xFF21 + i) for i in range(26))


def _romaji_units(rd):
    """かな＋英字の読み → 打鍵の綴りの組の並び（英字は1打）。読めない字があれば None。"""
    import romaji_swap_repair as R
    out = []
    i = 0
    while i < len(rd):
        c = rd[i]
        if 'a' <= c <= 'z':
            out.append((c,))
            i += 1
            continue
        j = i
        while j < len(rd) and not ('a' <= rd[j] <= 'z'):
            j += 1
        u = R._units(rd[i:j])
        if u is None:
            return None
        out.extend(u)
        i = j
    return out


def _romaji_spellings(rd, limit=4):
    units = _romaji_units(rd)
    if units is None:
        return []
    out = []
    for style in (0, 1):
        s = ''
        for k, u in enumerate(units):
            if u == ('*',):
                nxt = units[k + 1] if k + 1 < len(units) else None
                if not nxt or nxt == ('*',) or nxt[0][0] in 'aiueon-':
                    s = None
                    break
                s += nxt[min(style, len(nxt) - 1)][0]
                continue
            if u == ('n', 'nn'):
                nxt = units[k + 1] if k + 1 < len(units) else None
                s += 'nn' if nxt is None or nxt[0][0] in 'aiueoyn' else 'n'
                continue
            s += u[min(style, len(u) - 1)]
        if s and s not in out:
            out.append(s)
    return out[:limit]


def _romaji_key_repairs(rd, drop_only=None):
    """英字の残る打った読み → 1打の戻し（入れ替え・隣のキー・抜き）で英字の残らない読み。"""
    import romaji_swap_repair as R
    import keyboard_layout as KB
    near = {}
    for x, y in KB.letter_intrusion_pairs():
        near.setdefault(x, set()).add(y)
        near.setdefault(y, set()).add(x)
    out = []
    seen = set()
    for sp in _romaji_spellings(rd):
        tries = []
        for i in range(len(sp)):
            if i + 1 < len(sp) and sp[i] != sp[i + 1]:
                tries.append((sp[:i] + sp[i + 1] + sp[i] + sp[i + 2:], False))
            for y in near.get(sp[i], ()):
                tries.append((sp[:i] + y + sp[i + 1:], False))
            # 1打の抜きは、隣のキーと一緒に押した余分な1打（巻き込み）だけ: 前か後ろの打鍵が隣のキー
            # （英字を抜くだけの戻しは別の語を作りやすい: 台所ｄへ→台所へ）
            if (i and sp[i - 1] in near.get(sp[i], ())) or (i + 1 < len(sp) and sp[i + 1] in near.get(sp[i], ())):
                tries.append((sp[:i] + sp[i + 1:], True))
        for t, drop in tries:
            for k in R._to_kanas(t):
                if not k or not _is_hira(k):
                    continue
                if drop_only is not None:
                    drop_only[k] = drop_only.get(k, True) and drop
                if k not in seen:
                    seen.add(k)
                    out.append(k)
    return out


def _romaji_spans(done, a, b, letters=True, widen=_ROMAJI_WIDEN):
    """紫の所を語の区切りまで広げ、左右へ _ROMAJI_WIDEN 語まで広げた [(開始, 終了, [打った読み])]（英字を含む読みだけ）。"""
    from morphology import tokenize
    toks = list(tokenize(done))
    idx = [k for k, t in enumerate(toks) if t.end > a and t.start < b]
    if not idx:
        return []
    try:
        from kanji_guess import ime_readings_for
    except Exception:
        return []
    out = []
    for dl in range(widen + 1):
        for dr in range(widen + 1):
            i, j = idx[0] - dl, idx[-1] + dr
            if i < 0 or j >= len(toks):
                continue
            s, e = toks[i].start, toks[j].end
            if any(c in '。、，．,.！？!?「」『』（）() 　\t' for c in done[s:e]):
                continue
            rds = []
            for r in ime_readings_for(done[s:e]) or ():
                r = _hira(r.translate(_HALF)).lower()
                if (not letters or any('a' <= c <= 'z' for c in r)) and r not in rds and len(r) <= MAX_READ + 4 \
                        and (letters or _is_hira(r)):
                    rds.append(r)
            if not rds:
                # 打った読みの記録が無ければ、語ごとの読み（英字はそのまま1打・漢字は語の読み）を並べる
                rds = [r for r in _romaji_token_readings(toks[i:j + 1], need_letters=letters) if len(r) <= MAX_READ + 4]
            if rds:
                out.append((s, e, rds))
    return out


def _leftover_letters(line, x, y):
    """紫の所の英字が、IME が音にできずに残した打鍵に見えるか: 英字の並びがどれも3字以下・大文字なし（全角は可）で、
    かなか漢字に接している（英語の語・略語は見ない）。"""
    import re
    lo = x
    while lo > 0 and (line[lo - 1] in _FULL_LETTERS or 'a' <= line[lo - 1].lower() <= 'z'):
        lo -= 1
    hi = y
    while hi < len(line) and (line[hi] in _FULL_LETTERS or 'a' <= line[hi].lower() <= 'z'):
        hi += 1
    runs = list(re.finditer('[a-zA-Zａ-ｚＡ-Ｚ]+', line[lo:hi]))
    if not runs:
        return False
    jp = lambda c: _is_hira(c) or _kanji(c) or 'ァ' <= c <= 'ヶ' or c == 'ー'
    for m in runs:
        a, b = lo + m.start(), lo + m.end()
        t = m.group()
        if len(t) > 3 or any('A' <= c <= 'Z' for c in t):
            return False
        if not ((a > 0 and jp(line[a - 1])) or (b < len(line) and jp(line[b]))):
            return False
    return True


def _garbled_neighbour(fixed, changed):
    """直した所のすぐ隣に片仮名の切れ端が残るか（のhノン→のんノン・のhスッ長→のんスッ長: IME が英字の周りを崩して
    片仮名にした所）。漢字の並びは見ない（契約ｚ書→契約書 のように正しく直った所も2語に分かれる）。"""
    kata = lambda c: 'ァ' <= c <= 'ヶ' or c == 'ー'
    for j1, j2 in changed:
        for k in ([j1 - 1] if j1 > 0 else []) + ([j2] if j2 < len(fixed) else []):
            if kata(fixed[k]) and not any(kata(c) for c in fixed[j1:j2]):
                return True
    return False


def _romaji_token_readings(toks, limit=4, need_letters=True):
    import itertools
    opts = []
    for t in toks:
        sf = t.surface.translate(_HALF)
        if all('a' <= c.lower() <= 'z' for c in sf):
            opts.append([sf.lower()])
            continue
        if any('a' <= c.lower() <= 'z' for c in sf):
            per = []
            for c in sf:
                if 'a' <= c.lower() <= 'z':
                    per.append(c.lower())
                elif _is_hira(_hira(c)):
                    per.append(_hira(c))
                else:
                    return []
            opts.append([''.join(per)])
            continue
        rs = _token_readings(t, None)
        if not rs and all('ァ' <= c <= 'ヶ' or c == 'ー' for c in sf) and _is_hira(_hira(sf)):
            # IME が片仮名にした打鍵（a→ア）は、その音のまま
            rs = [_hira(sf)]
        if not rs:
            return []
        opts.append(rs[:2])
    out = [''.join(x) for x in itertools.islice(itertools.product(*opts), limit)]
    return [r for r in out if not need_letters or any('a' <= c <= 'z' for c in r)]


ROMAJI_ROUNDS = 3   # 1行の中の打ち違いを1か所ずつ直す回数（前半と後半に1つずつの行: うにさん 11-03 のメール例）


def _romaji_repair(line, result, run, store, dict_index, context_vec=None, decided=()):
    """紫ごとに、打鍵の1打の戻し（入れ替え・隣のキー・巻き込みの1打）で直す形を1つずつ選ぶ。1か所直したら、残りの
    紫をその上でもう一度見る（2か所の打ち違いで、1か所目を直さないと費用が下がり切らない）。決まらなければ result のまま。"""
    if not isinstance(result, dict):
        return result
    out = result
    for _ in range(ROMAJI_ROUNDS):
        new = _romaji_repair_once(line, out, run, store, dict_index, context_vec, decided)
        if new is out:
            break
        out = new
    return out


def _has_letters(text):
    return any(c in _FULL_LETTERS or 'a' <= c.lower() <= 'z' for c in text)


def _romaji_repair_once(line, result, run, store, dict_index, context_vec=None, decided=()):
    import morphology
    cur = result.get('corrected') or line
    spans = []
    for x0, y0 in sorted({tuple(sp[:2]) for sp in (result.get('odd_spans') or ())}):
        if any(x < y0 and x0 < y for x, y in (decided or ())):
            continue
        m = _to_done(line, cur, x0, y0)
        if m is None:
            continue
        x, y = m
        if _has_letters(cur[x:y]):
            if _leftover_letters(cur, x, y):
                spans.append((x, y, True, _ROMAJI_WIDEN))
        elif os.environ.get('CN_ROMAJI_PLAIN') != '0' and any(not _is_hira(c) for c in cur[x:y]):
            # 英字の残らない打ち違い（かけよう を kakeyuo と打って 出かけ湯尾）も、紫の所の打った読みを打鍵に戻して見る
            spans.append((x, y, False, _ROMAJI_WIDEN))
        elif os.environ.get('CN_ROMAJI_PLAIN') != '0' and any(_kanji(c) for c in cur):
            # ひらがなだけの紫（がいにおで: IME が仮名のまま残した打ち違い）は、行のどこかを漢字に変換した行で、
            # 紫の語だけを見る（左右へ広げると重い: 挙動関連担当の測り 11-03 で止まった後に33秒。かなだけの行は見ない）
            spans.append((x, y, False, 0))
    if not spans:
        return result
    base = morphology.path_cost(cur)
    if base is None:
        return result
    need = min(GAIN, GAIN_SHARE * base)
    # 紫ごとに別々に決める（1行に打ち違いが2つあると、片方の紫で一番と二番が並んでも、もう片方ははっきり決まる。
    # まとめて並べると、並んだほうに引きずられて両方とも紫のままだった・うにさん 11-03 のメール例）
    groups = []
    for a0, b0, letters, widen in spans:
        pool = {}
        drop_only = {}
        keep = set()
        for s, e, rds in _romaji_spans(cur, a0, b0, letters, widen):
            reps, src, tried = [], {}, set(rds)
            for rd in rds:
                for r in _romaji_key_repairs(rd, drop_only):
                    if r not in tried:
                        tried.add(r)
                        reps.append(r)
                        src[r] = rd
            try:
                placed = _placed(cur, s, e, reps, store, dict_index, context_vec, src, tried)
            except Exception:
                placed = []
            for c, text, r in placed:
                if text not in pool or c < pool[text][0]:
                    pool[text] = (c, s, e, drop_only.get(r, False))
            if not letters and os.environ.get('CN_ROMAJI_PLAIN_RIVAL') != '0':
                # 英字の無い紫では、打った読みのまま置き直した形（打ち違いが無いとした形）も並べる。打ち違いの戻しは、
                # これよりはっきり軽いときだけ（かなのままの正しい行 しゅうまつはかぞく を 週末が家族 にしていた）
                try:
                    same = _placed(cur, s, e, list(rds), store, dict_index,
                                   context_vec, None, set(rds))
                except Exception:
                    same = []
                for c, text, r in same:
                    if text != cur and (text not in pool or c < pool[text][0]):
                        pool[text] = (c, s, e, False)
                        keep.add(text)
        ranked = sorted(pool.items(), key=lambda x: x[1][0])
        if ranked and base - ranked[0][1][0] >= min(SCREEN, need):
            groups.append((ranked[0][1][0], a0, b0, ranked, keep))
    for _c0, a0, b0, ranked, keep in sorted(groups, key=lambda g: g[:3]):
        # ほかの紫（もう1つの打ち違い）が直した形に残っても、この所の直しとしては紫が残らない
        other = {(x, y) for x, y, _l, _w in spans if not (x < b0 and a0 < y)}
        seen = _Seen()
        drops = set()
        for text, (c, s, e, drop) in ranked[:TOP]:
            want = _line_reading(text) if os.environ.get('CN_ROMAJI_SAME_READING') != '0' else None
            for fx, v in _judge(cur, s, e, [text], run, other, True).items():
                # 補正し直しで読みまで替わった形（1打の戻しの上に別の直しが重なった: あたrさひい→おもねっらしい）は見ない
                if want is not None and fx != text and _line_reading(fx) != want:
                    continue
                if fx not in seen or v[0] < seen[fx][0]:
                    seen[fx] = v
                    (drops.add if drop else drops.discard)(fx)
                    if text in keep:
                        keep.add(fx)
        got = _pick(seen, MARGIN)
        if got is None and drops and os.environ.get('CN_ROMAJI_DROP_RIVAL') != '0':
            # 一番が打鍵の入れ替え・隣のキーの戻しで、並ぶ二番が1打を抜いたときだけの形（ゆお→よう と よ）なら、
            # 二番は数えない（抜きは余分な1打を仮に置いた弱い見立て。一番のほうが軽いときだけ）
            best = min(seen.items(), key=lambda x: x[1][0])[0]
            if best not in drops:
                kept = _Seen({k: v for k, v in seen.items() if k not in drops})
                kept.further = {k for k in seen.further if k in kept}
                kept.source = {k: v for k, v in seen.source.items() if k in kept}
                got = _pick(kept, MARGIN)
        if got is None or base - got[1] < need or got[0] in keep:
            continue
        fixed = got[0]
        if _romaji_fix_ok(cur, fixed, [sp[:3] for sp in spans if sp[0] < b0 and a0 < sp[1]]):
            break
    else:
        return result
    lops = [o for o in difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']
    if not lops or any(x < o[2] and o[1] < y for o in lops for x, y in (decided or ())):
        return result
    near = [(o[1], o[2]) for o in lops]
    new = dict(result)
    new.update({'original': line, 'corrected': fixed, 'changed': True,
                'details': list(result.get('details') or []) + [_detail(cur, fixed)],
                'spans': [[o[3], o[4]] for o in lops], 'original_spans': [[o[1], o[2]] for o in lops]})
    for key in ('odd_spans', 'unsure_spans'):
        new[key] = [sp for sp in (result.get(key) or ()) if not any(x < sp[1] and sp[0] < y for x, y in near)]
    if 'odd_reasons' in result:
        new['odd_reasons'] = [r for r in (result.get('odd_reasons') or ())
                              if not any(x < r[1] and r[0] < y for x, y in near)]
    return new


def _romaji_fix_ok(cur, fixed, spans):
    allops = difflib.SequenceMatcher(None, cur, fixed, autojunk=False).get_opcodes()
    ops = [o for o in allops if o[0] != 'equal']
    if not ops:
        return False
    # 英字を戻した所に英字が残る形、直した紫の所に IME が崩した漢字・片仮名がそのまま残る形（のhノン→のんノン）は、
    # 途中までの直し。紫の所で残ってよいのはひらがなだけ
    for x, y, letters in spans:
        if not any(x < o[2] + (o[1] == o[2]) and o[1] < y + (o[1] == o[2]) for o in ops):
            continue
        if letters and _has_letters(fixed[_cur_to_fixed(allops, x):_cur_to_fixed(allops, y)]):
            return False
        for tag, i1, i2, j1, j2 in allops:
            if tag == 'equal' and any(x <= k < y and not _is_hira(cur[k]) for k in range(i1, i2)) and letters:
                return False
    return not _garbled_neighbour(fixed, [(o[3], o[4]) for o in ops])


def _cur_to_fixed(allops, k):
    for tag, i1, i2, j1, j2 in allops:
        if i1 <= k < i2 or (k == i2 and tag == 'equal'):
            return j1 + (k - i1 if tag == 'equal' else 0)
    return allops[-1][4] if allops else k
