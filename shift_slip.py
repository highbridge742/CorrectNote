# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""
中身のないシフトで、小書き・「を」の抜けを直す（1.16 に入れる形・2026-10-24。かな入力だけ）。

うにさん 10-24 01:47Z「シフトの離しが早かっただけでシフトの打鍵はあるはず」・09:31Z「シフトキーの件も入れる」。
本物の記録（かな入力55文）: シフトの押し90回のうち、押している間に他のキーの無い「中身のないシフト」が5回、
5回とも近くの小書きが抜けていた（とまつた×2・ざつし・しりよう・しまつた）。小書きの抜けは全部この形。
記録の5つはどれも、シフトの押しが遅れて直前のキー（まだ押していた）が素の字になった形。

1. 打鍵（アプリ側・挙動関連担当）: `ShiftStrokeClock`（keystroke_doubt.StrokeClock と同じ使い方）。
   シフトの押し・離しは別に覚え、押しの組（keycode 229 の待ち）には触らない。Tk はシフトの押しを Shift_R、
   離しを Shift_L と別の名前で渡すことがあるので、keycode（16・160・161）で見る。
2. 印（`empty_shifts`）: シフトの押しから離しまでに押されたキーが無いもの。
3. 候補（`shift_candidates`）: 印の直前のキー（シフトを押したときまだ押していた、または 150ms 以内）と、
   離した直後のキー（150ms 以内）のうち、シフト付きの字のあるキー。重なっていた方を先に並べる。
4. 直すか（`repair_shift`）: 候補の字をシフト付きにした読みを作り、あり得ない所（kana_rules.bad_spots）が
   増えず、読みの3連（yomigram）が打った読みより良いものを採る。候補が2つとも良く、差が小さければ紫。
   打鍵の並びが確定の読みと合わないとき（打ち直しなど）は何もしない。特定の文字列を名指ししない。
"""
import kana_rules

SHIFT_KEYCODES = (16, 160, 161)
NEAR_MS = 150.0
CLOSE_LOGP = 1.0            # 2つの候補の差がこれ未満なら決めずに紫
MARK_KEYS = ('@', '[')       # ゛ ゜ のキー（JIS かな配列）
# JIS かな配列でシフト付きの字のあるキー（素の字 → シフト付き）
SHIFTED = {'3': ('あ', 'ぁ'), '4': ('う', 'ぅ'), '5': ('え', 'ぇ'), '6': ('お', 'ぉ'),
           '7': ('や', 'ゃ'), '8': ('ゆ', 'ゅ'), '9': ('よ', 'ょ'), '0': ('わ', 'を'),
           'e': ('い', 'ぃ'), 'z': ('つ', 'っ')}

try:
    from keystroke_doubt import StrokeClock
except Exception:          # 単体の試験用
    StrokeClock = object


class ShiftStrokeClock(StrokeClock):
    """StrokeClock に、シフトの押し・離しの時刻を足したもの。take() は (strokes, shifts) を返す。"""

    def __init__(self, key_of_keycode):
        super().__init__(key_of_keycode)
        self._shift_down = None
        self.shifts = []

    def press(self, keycode, now_ms=None):
        if keycode in SHIFT_KEYCODES:
            import time
            now_ms = time.perf_counter() * 1000.0 if now_ms is None else now_ms
            if self._shift_down is None: self._shift_down = now_ms
            return
        super().press(keycode, now_ms)

    def release(self, keycode, now_ms=None):
        if keycode in SHIFT_KEYCODES:            # 押しの組（229 の待ち）を減らさない
            import time
            now_ms = time.perf_counter() * 1000.0 if now_ms is None else now_ms
            if self._shift_down is not None:
                self.shifts.append((self._shift_down, now_ms))
                self._shift_down = None
            return
        super().release(keycode, now_ms)

    def take(self):
        strokes = super().take()
        shifts, self.shifts = self.shifts, []
        return strokes, shifts


def empty_shifts(strokes, shifts):
    """strokes: [(キー, 押した ms)]（押した順）。shifts: [(押し ms, 離し ms)]。中身のないシフトを返す。"""
    return [(a, b) for a, b in shifts if not any(a <= t <= b for k, t in strokes if k)]


def shift_candidates(strokes, shift, release_of=None):
    """中身のないシフト1つについて、シフト付きにしたかったかもしれない打鍵の番号を、確からしい順に返す。
    release_of(i): その打鍵を離した ms（分からなければ None）。"""
    a, b = shift
    out = []
    prev = [i for i, (k, t) in enumerate(strokes) if k and t < a]
    nxt = [i for i, (k, t) in enumerate(strokes) if k and t > b]
    if prev:
        i = prev[-1]
        held = release_of is not None and release_of(i) is not None and release_of(i) > a
        if strokes[i][0] in SHIFTED and (held or a - strokes[i][1] <= NEAR_MS):
            out.append((0 if held else 1, i))
    if nxt:
        i = nxt[0]
        if strokes[i][0] in SHIFTED and strokes[i][1] - b <= NEAR_MS:
            out.append((1, i))
    return [i for _, i in sorted(out)]


def _char_index(strokes, reading):
    """打鍵の番号 → 読みの字の番号。打鍵から作った読みが確定の読みと合わなければ None。"""
    idx, chars = {}, []
    last = len(strokes)
    while last and not strokes[last - 1][0]: last -= 1     # 確定の Enter など、終わりの字でないキーは除く
    for i, (k, _) in enumerate(strokes[:last]):
        if not k: return None                     # 字でないキー（BS など）があれば合わせない
        if k in MARK_KEYS:
            if not chars: return None
            continue
        idx[i] = len(chars)
        chars.append(SHIFTED[k][0] if k in SHIFTED else None)
    if len(chars) != len(reading): return None
    big = {small: plain for plain, small in SHIFTED.values()}
    for c, r in zip(chars, reading):
        if c is not None and c != big.get(r, r): return None   # 素の字（またはそのシフト付き）でなければ合わせない   # 素の字のはずの所が違えば合わせない
    return idx


def repair_shift(reading, strokes, shifts, yomi_logp, release_of=None):
    """reading: 確定のかなの読み。返り値: (読み, 'fix' | 'purple' | None, 紫の位置 or None)。"""
    idx = _char_index(strokes, reading)
    if idx is None: return reading, None, None
    status, where = None, None
    for sh in empty_shifts(strokes, shifts):
        base_bad = len(kana_rules.bad_spots(reading))
        base_lp = yomi_logp(reading)
        cands = []
        for i in shift_candidates(strokes, sh, release_of):
            p = idx[i]
            plain, small = SHIFTED[strokes[i][0]]
            if reading[p] != plain: continue
            alt = reading[:p] + small + reading[p + 1:]
            bad = len(kana_rules.bad_spots(alt))
            if bad > base_bad: continue
            lp = yomi_logp(alt)
            if bad < base_bad or lp > base_lp: cands.append((bad, -lp, alt, p))
        if not cands: continue
        cands.sort()
        if len(cands) > 1 and cands[0][0] == cands[1][0] and cands[1][1] - cands[0][1] < CLOSE_LOGP:
            if status is None: status, where = 'purple', cands[0][3]
            continue
        reading, status, where = cands[0][2], 'fix', cands[0][3]
    return reading, status, where


# --- 補正の入口から使う形（補正担当・2026-10-24）---
# correction_entry.correct_line(..., occurrence_strokes=[(start, end, surface, reading, strokes, shifts), ...])
# の6つ目（ShiftStrokeClock.take() の shifts）があるとき、かな入力だけ。

def repair_line(line, base, occurrences, input_method, run, convert=None):
    """
    中身のないシフトの直しを確定ごとに当てる。'fix' は直した読みを（IME の1つ目の変換で）行に戻して補正し直す。
    'purple' はその確定の範囲に紫だけを足す（迷うなら紫）。返り値: 結果（dict）。直しも紫も無ければ base のまま。
    """
    if input_method != 'kana': return base
    import yomigram
    yomi = lambda rd: yomigram.logp_parts(rd)[0]
    hira = str.maketrans({chr(c): chr(c - 0x60) for c in range(0x30A1, 0x30F7)})
    done = base.get('corrected') or line
    for occ in occurrences or ():
        if len(occ) < 6 or not occ[5]: continue
        start, end, surface, reading, strokes, shifts = occ[:6]
        if line[start:end] != surface or not reading: continue
        rd = reading.translate(hira)
        try:
            new, status, _ = repair_shift(rd, strokes, shifts, yomi)
        except Exception:
            continue
        if status == 'fix' and new != rd:
            # 印なしの補正が確定の外を直した行は混ぜない
            if done != line and (done[:start] != line[:start] or done[len(done) - (len(line) - end):] != line[end:]): continue
            face = None
            if convert is not None:
                try: face = convert(new)
                except Exception: face = None
            alt = line[:start] + (face or new) + line[end:]
            got = run(alt)
            text = got.get('corrected') or alt
            if got.get('odd_spans'): text = alt   # 直した後に紫が残るなら、補正し直しの分は採らない
            import difflib
            ops = [o for o in difflib.SequenceMatcher(None, line, text, autojunk=False).get_opcodes() if o[0] != 'equal']
            if not ops: continue
            a, b, c, d = ops[0][1], ops[-1][2], ops[0][3], ops[-1][4]
            return {'original': line, 'corrected': text, 'changed': True,
                    'details': [[line[a:b], text[c:d], 'シフトの抜け']], 'spans': [[c, d]], 'original_spans': [[a, b]],
                    'odd_spans': [], 'unsure_spans': [], 'odd_reasons': []}
        if status == 'purple' and done == line:
            out = dict(base)
            if any(s < end and start < e for s, e, *_ in out.get('odd_spans') or ()): continue
            out['odd_spans'] = sorted(list(out.get('odd_spans') or ()) + [(start, end)])
            out['odd_reasons'] = list(out.get('odd_reasons') or ()) + [
                (start, end, f'「{surface}」はシフトだけの打鍵の近くで、小書きが抜けたかもしれません')]
            return out
    return base
