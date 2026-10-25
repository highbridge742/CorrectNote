# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""
打鍵の間隔で巻き込みを疑う（1.16 に入れる形・2026-10-24。うにさん 09:01Z「ぜんぶ1.16に入れる」）。

1. 打鍵の時刻（アプリ側・挙動関連担当）: `StrokeClock`。Windows の Tk は IME の変換中 KeyPress を
   keycode 229 で、KeyRelease を本当のキーで渡すので、押しと離しを古い順に組む（1秒より古い押しは捨てる）。
   時刻は time.perf_counter（Tk の %t は 15.6ms 刻みで使えない）。全体のフック・Win32 の呼び出しは無し。
2. 印（`doubt_pairs`）: 巻き込みの隣（かな: kana_layout.physical_intrusion_keys_adjacent、
   ローマ字: keyboard_layout の英字の巻き込みの隣）で、押した時刻の差が 30ms 未満の2打。
   左右の手が別（中央の列を除く）なら印にしない（うにさん 10-23 23:15Z）。
3. どちらを抜くか（`choose_drop`）: うにさん 10-24 00:33Z「前後の繋がりと、前の文字から続きやすい文字の確率」・
   01:05Z「表は以前からある」・01:44Z「文頭文末などのあり得ない並び」。
   (1) あり得ない所（kana_rules.bad_spots）の少ない方 (2) 同じなら 読みの3連（yomigram.logp_parts の合計）
   ＋ 自然さ（morphology.path_cost）×0.5/1000 の高い方。
4. 採るか（`repair_with_doubts`）: 選んだ抜き方の行そのものと、その補正の結果を候補にし、印の文節の外を
   変えるものと紫が残るものは捨てる。自然さが印なしの結果より margin（2000）以上低いときだけ採る。
   打った行にあり得ない所があり、抜いた形で消えるときは margin を外す（必ず誤りの印）。
   採らないときは印なしの結果（今まで通りの補正・紫）のまま。特定の文字列を名指ししない。
"""
import difflib, time
import kana_rules

DEFAULT_THRESHOLD_MS = 30.0
DEFAULT_MARGIN = 2000.0
PATH_WEIGHT = 0.5
_STALE_MS = 1000.0            # 離しの来ない押しは 1 秒で捨てる（組がずれないように）


class StrokeClock:
    """KeyPress / KeyRelease から、打鍵ごとの (キーの字, 押した時刻 ms) を作る。"""

    def __init__(self, key_of_keycode):
        self._key_of = key_of_keycode          # 仮想キー → 配列の字（q, @, ...）。字でなければ None
        self._pending = []
        self.strokes = []

    def press(self, keycode, now_ms=None):
        now_ms = time.perf_counter() * 1000.0 if now_ms is None else now_ms
        if keycode == 229:
            self._pending.append(now_ms)
        else:
            key = self._key_of(keycode)
            if key: self.strokes.append((key, now_ms))

    def release(self, keycode, now_ms=None):
        now_ms = time.perf_counter() * 1000.0 if now_ms is None else now_ms
        while self._pending and self._pending[0] < now_ms - _STALE_MS:
            self._pending.pop(0)
        if not self._pending:
            return
        down = self._pending.pop(0)
        key = self._key_of(keycode)
        self.strokes.append((key or '', down))  # 字でないキー（空白・Enter・BS）も並びを切るために残す

    def take(self):
        """確定したら呼ぶ。押した順の打鍵を返して空にする。"""
        out = sorted(self.strokes, key=lambda x: x[1])
        self.strokes = []
        return out


def _hand(pos):
    if pos is None: return '?'
    return 'L' if pos[1] <= 3 else ('R' if pos[1] >= 6 else 'C')


def doubt_pairs(strokes, positions, adjacent, threshold_ms=DEFAULT_THRESHOLD_MS):
    """strokes: [(キーの字, 押した ms)]。positions: 字 → (段, 列)。adjacent(p1, p2): 巻き込みの隣か。
    返り値: 印の付いた (i, i+1) の並び（strokes の番号）。"""
    out = []
    for i in range(len(strokes) - 1):
        (a, ta), (b, tb) = strokes[i], strokes[i + 1]
        if not a or not b or a == b: continue
        pa, pb = positions.get(a), positions.get(b)
        if pa is None or pb is None or not adjacent(pa, pb): continue
        ha, hb = _hand(pa), _hand(pb)
        if 'C' not in (ha, hb) and ha != hb: continue      # 左右の手が別
        if tb - ta < threshold_ms: out.append((i, i + 1))
    return out


def _region(a, b):
    ops = [o for o in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if o[0] != 'equal']
    return (ops[0][1], ops[-1][2]) if ops else None


def _local(line, cand_line, got, slack=2):
    r = _region(line, cand_line)
    if r is None: return True
    return all(o[0] == 'equal' or (o[1] >= r[0] - slack and o[2] <= r[1] + slack)
               for o in difflib.SequenceMatcher(None, line, got, autojunk=False).get_opcodes())


def choose_drop(alternatives, reading_of, yomi_logp, path_cost):
    """alternatives: 印の2打のどちらかを抜いた行（2つ）。返り値: (選んだ行, あり得ない所で決めたか)。"""
    def key(alt):
        rd = reading_of(alt)
        pc = path_cost(alt)
        return (len(kana_rules.bad_spots(rd)), -(yomi_logp(rd) - PATH_WEIGHT * (pc or 0) / 1000.0))
    ks = [key(a) for a in alternatives]
    best = min(range(len(alternatives)), key=lambda i: ks[i])
    by_rule = len({k[0] for k in ks}) > 1
    return alternatives[best], by_rule


def repair_with_doubts(line, base, alternatives, run, path_cost, reading_of, yomi_logp, margin=DEFAULT_MARGIN):
    """
    line: 打った行。base: 印なしの補正の結果。alternatives: 印の2打のどちらかを抜いた行（2つ）。
    run(text) -> (補正した行, 紫が残ったか)。yomi_logp(読み) -> 対数確率（yomigram.logp_parts(読み)[0]）。
    返り値: (行, 'fix' | None)。
    """
    alt, _ = choose_drop(alternatives, reading_of, yomi_logp, path_cost)
    sure = len(kana_rules.bad_spots(reading_of(line))) > len(kana_rules.bad_spots(reading_of(alt)))
    got, odd = run(alt)
    cands = []
    for g, o in ((alt, False), (got, odd)):
        if not o and _local(line, alt, g):
            c = path_cost(g)
            if c is not None: cands.append((c, g))
    if not cands: return base, None
    cands.sort()
    bc = path_cost(base)
    if bc is None or cands[0][0] >= bc - (0.0 if sure else margin): return base, None
    return cands[0][1], 'fix'


# --- 補正の入口から使う形（補正担当・2026-10-24）---
# アプリは確定ごとに take() の打鍵を、その確定（行の中の位置・表記・読み）と一緒に渡す:
#   correction_entry.correct_line(..., occurrence_strokes=[(start, end, surface, reading, strokes), ...])
# 6つ目にシフトの押し・離し（shift_slip.ShiftStrokeClock の shifts）があってもよい（シフトは shift_slip が見る）。
# 打鍵と読みの並びが1打ずつ合うときだけ使う（BS で直した確定・並びの合わない確定は見ない）。

_HIRA = {chr(c): chr(c - 0x60) for c in range(0x30A1, 0x30F7)}


def _kana_key_reading(reading):
    """読み → 打鍵の並び（かな入力。濁点・半濁点のキーも1打）。"""
    import kana_layout
    out = []
    for ch in reading:
        out.extend(kana_layout.keystrokes(ch))
    return out


def _compose_kana(keys):
    """打鍵の並び（かな・゛・゜）→ 読み。付く先の無い ゛゜ はそのまま残す（kana_rules があり得ない所と見る）。"""
    import kana_layout
    voiced = {}
    for ch in [chr(c) for c in range(0x3041, 0x3097)]:
        ks = kana_layout.keystrokes(ch)
        if len(ks) == 2: voiced[ks] = ch
    out = []
    for k in keys:
        if k in '゛゜' and out and (out[-1], k) in voiced:
            out[-1] = voiced[(out[-1], k)]
        else:
            out.append(k)
    return ''.join(out)


def _setup(input_method):
    """(位置の表, 隣の決まり)。かな: kana_layout の巻き込みの隣。ローマ字: keyboard_layout の英字の巻き込みの隣。"""
    import keyboard_layout
    positions = keyboard_layout.positions()
    if input_method == 'romaji':
        letter_at = {p: k for k, p in keyboard_layout.letter_positions().items()}
        pairs = keyboard_layout.letter_intrusion_pairs()
        def adjacent(p, q):
            a, b = letter_at.get(p), letter_at.get(q)
            return bool(a and b) and ((a, b) in pairs or (b, a) in pairs)
        return keyboard_layout.letter_positions(), adjacent
    import kana_layout
    return positions, kana_layout.physical_intrusion_keys_adjacent


def occurrence_alternatives(reading, strokes, input_method):
    """1つの確定の読みと打鍵から、印の2打のどちらかを抜いた読みの組を返す: [(読み1, 読み2), ...]。"""
    if not strokes or any(not k for k, _ in strokes): return []
    rd = reading.translate(str.maketrans(_HIRA))
    positions, adjacent = _setup(input_method)
    keys = [k for k, _ in strokes]
    if input_method == 'romaji':
        import halfwidth
        if halfwidth.romaji_to_kana(''.join(keys))[0] != rd: return []
        make = lambda d: halfwidth.romaji_to_kana(''.join(keys[:d] + keys[d + 1:]))[0]
    else:
        import kana_layout
        typed = _kana_key_reading(rd)
        if len(typed) != len(keys): return []
        if any(kana_layout.KANA_POSITIONS.get(t) != positions.get(k) for t, k in zip(typed, keys)): return []
        make = lambda d: _compose_kana(typed[:d] + typed[d + 1:])
    out = []
    for i, j in doubt_pairs(strokes, positions, adjacent):
        a, b = make(i), make(j)
        if a and b and a != b: out.append((a, b))
    return out


def repair_line(line, base, occurrences, input_method, run, convert=None):
    """
    line: 打った行。base: 印なしの補正の結果（dict）。occurrences: [(start, end, surface, reading, strokes)]。
    run(text) -> 印なしの補正の結果（dict）。convert(読み) -> IME の1つ目の変換（無ければ読みのまま入れる）。
    採ったときは、印の文節を直した結果（dict）を返す。採らないときは base のまま。
    """
    import morphology, yomigram
    KT = str.maketrans(_HIRA)
    def reading_of(text):
        return ''.join((t.reading if t.has_reading else t.surface).translate(KT) for t in morphology.tokenize(text))
    def yomi(rd):
        return yomigram.logp_parts(rd)[0]
    done = base.get('corrected') or line
    runs = {}
    def run2(text):
        if text not in runs: runs[text] = run(text)
        r = runs[text]
        return r.get('corrected') or text, bool(r.get('odd_spans'))
    for occ in occurrences or ():
        try:
            start, end, surface, reading, strokes = occ[:5]
        except (TypeError, ValueError):
            continue
        if line[start:end] != surface or not reading: continue
        # 印なしの補正が文節の外を直した行は混ぜない（どちらの直しも崩さないため、印なしのまま）
        if done != line and not _local(line, line[:start] + '\0' + line[end:], done, slack=0): continue
        for ra, rb in occurrence_alternatives(reading, strokes, input_method):
            alts = []
            for r in (ra, rb):
                face = None
                if convert is not None:
                    try: face = convert(r)
                    except Exception: face = None
                alts.append(line[:start] + (face or r) + line[end:])
            got, how = repair_with_doubts(line, done, alts, run2, morphology.path_cost, reading_of, yomi)
            if how != 'fix' or got == done: continue
            ops = [o for o in difflib.SequenceMatcher(None, line, got, autojunk=False).get_opcodes() if o[0] != 'equal']
            a, b, c, d = ops[0][1], ops[-1][2], ops[0][3], ops[-1][4]
            return {'original': line, 'corrected': got, 'changed': True,
                    'details': [[line[a:b], got[c:d], '打鍵の間隔']], 'spans': [[c, d]], 'original_spans': [[a, b]],
                    'odd_spans': [], 'unsure_spans': [], 'odd_reasons': []}
    return base
