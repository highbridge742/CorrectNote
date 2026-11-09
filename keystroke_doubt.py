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
5. 巻き込みを基本疑う（うにさん 11-01 04:11Z「キーの打鍵間隔が閾値を下回るときは、隣接の巻き込みを基本疑って
   ください」）: しきい値より短い隣の2打は巻き込みと見て、抜いた形が紫を残さず文節の外を変えず、自然さが印なしの
   結果より PRESUME_TOLERANCE（1000）を超えて悪くならなければ採る（前の「margin 以上良くなるときだけ」をやめた）。
   どちらを抜くかは抜いた所の前後だけの自然さで比べ、2つの差が CHOOSE_GAP より小さければ決めない。
   採れなかった印は、その文節を紫にする（決めるか紫か）。
"""
import difflib, os, time
import kana_rules

DEFAULT_THRESHOLD_MS = 30.0
DEFAULT_MARGIN = 2000.0       # 前の門（今は使わない。測りの比べのために残す）
CHOOSE_GAP = 1.0              # 2つの抜き方の点の差がこれより小さければ決めずに紫
PRESUME_TOLERANCE = 1000.0    # 抜いた形が印なしの結果よりこれ以上悪いときだけ巻き込みとしない
PATH_WEIGHT = 0.5
LINE_PATH_WEIGHT = 2.0       # 基本疑う形で、どちらを抜くかを行全体の自然さで比べるときの重み
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


def _window(line, text, width=4):
    """text のうち line と違う所の前後 width 字だけ（長いかなの行は janome の自然さが行の終わりの方しか見ないので）。"""
    r = _region(line, text)
    if r is None: return text
    lo = max(0, r[0] - width)
    hi = min(len(line), r[1] + width)
    return text[lo:hi + len(text) - len(line)]


def choose_drop(alternatives, reading_of, yomi_logp, path_cost, line=None):
    """alternatives: 印の2打のどちらかを抜いた行（2つ）。返り値: (選んだ行, あり得ない所で決めたか)。
    line を渡すと、自然さは抜いた所の前後だけで比べる。"""
    return _choose(alternatives, reading_of, yomi_logp, path_cost, line)[:2]


def _choose(alternatives, reading_of, yomi_logp, path_cost, line=None):
    def key(alt):
        rd = reading_of(alt)
        if line is None or os.environ.get('CN_KD_LINE') == '0':
            pc, w = path_cost(alt if line is None else _window(line, alt)), PATH_WEIGHT
        else:
            # 行全体の自然さで比べ、重みを上げる（抜いた所の前後だけでは語の途中で切れ、短い形が軽く出た: 今日は吉が・
            # 会社も近くに。新しい試験の巻き込み 754件で 誤り34→16・決めない21→11・2026-11-02）
            pc, w = path_cost(alt), LINE_PATH_WEIGHT
        return (len(kana_rules.bad_spots(rd)), -(yomi_logp(rd) - w * (pc or 0) / 1000.0))
    ks = [key(a) for a in alternatives]
    best = min(range(len(alternatives)), key=lambda i: ks[i])
    by_rule = len({k[0] for k in ks}) > 1
    gap = min((abs(k[1] - ks[best][1]) for i, k in enumerate(ks) if i != best and k[0] == ks[best][0]), default=None)
    return alternatives[best], by_rule, gap


COMMON_RARE, COMMON_USUAL = 600, 450


def _diff_noun(text, other):
    """text の、other と違う所がちょうど名詞1語なら (表記, 珍しさ)。それ以外は None。"""
    try:
        from morphology import tokenize
        import ime_reconvert as _R
        ops = [o for o in difflib.SequenceMatcher(None, text, other, autojunk=False).get_opcodes() if o[0] != 'equal']
        if not ops:
            return None
        a, b = ops[0][1], max(ops[-1][2], ops[0][1] + 1)
        toks = list(tokenize(text))
        hit = [t for t in toks if t.start < b and a < t.end]
        if len(hit) != 1 or hit[0].pos != '名詞':
            return None
        return hit[0].surface, _R._token_rarity(hit[0], toks)
    except Exception:
        return None


def repair_with_doubts(line, base, alternatives, run, path_cost, reading_of, yomi_logp, margin=None, odd_spans=None):
    """
    line: 打った行。base: 印なしの補正の結果。alternatives: 印の2打のどちらかを抜いた行（2つ）。
    run(text) -> (補正した行, 紫が残ったか)。yomi_logp(読み) -> 対数確率（yomigram.logp_parts(読み)[0]）。
    margin: None なら巻き込みを基本疑う（抜いた形が PRESUME_TOLERANCE を超えて悪くなければ採る）。
    数を渡すと前の門（margin 以上良くなるときだけ採る）。
    返り値: (行, 'fix' | None)。
    """
    alt, by_rule, gap = _choose(alternatives, reading_of, yomi_logp, path_cost, line if margin is None else None)
    if margin is None and len(alternatives) == 2 and os.environ.get('CN_KD_COMMON') != '0':
        # 抜いた2つの形が名詞1つずつだけ違い、片方は漢字か片仮名だけの珍しい名詞（枷・コチ: 600 以上）、もう一方は
        # 身近な名詞（川・道: 450 以下）なら身近な方を採る。読みの確率と path_cost は短い珍しい名詞を軽く見ることがある
        # （為替で→枷で・小道に→コチに。2026-11-06 かな入力の担当。送り仮名の付く複合語 草取り 等は見ない）
        w = [_diff_noun(alternatives[0], alternatives[1]), _diff_noun(alternatives[1], alternatives[0])]
        if None not in w:
            (s0, r0), (s1, r1) = w
            rare, common = (0, 1) if r0 > r1 else (1, 0)
            rs = w[rare][0]
            if (w[rare][1] >= COMMON_RARE and w[common][1] <= COMMON_USUAL
                    and (all('一' <= c <= '鿿' for c in rs) or all('ァ' <= c <= 'ヶ' or c == 'ー' for c in rs))):
                pick = alternatives[common]
                # 読めない並び（ざゅう 等）の多い方には替えない
                if pick != alt and len(kana_rules.bad_spots(reading_of(pick))) <= len(kana_rules.bad_spots(reading_of(alt))):
                    alt, by_rule, gap = pick, True, None
    if margin is None and len(alternatives) == 2 and os.environ.get('CN_KD_CLEAN') != '0':
        # 抜いた2つの形を補正に通し、選んだ方だけ紫が残り、もう一方は紫なしに通るなら、もう一方を採る
        # （喪背で/店で・押す手/終えて の取り違え。抜いた形に紫が残るのは、その抜き方が誤りの印・2026-11-05 かな入力の担当）
        # 紫は抜いた所（2つの形の違う所）に掛かるものだけを見る（行の別の所の紫は抜き方の証にならない）
        other = alternatives[1] if alt == alternatives[0] else alternatives[0]
        def odd_here(text, against):
            ops = [o for o in difflib.SequenceMatcher(None, text, against, autojunk=False).get_opcodes() if o[0] != 'equal']
            if not ops: return False
            a, b = ops[0][1], max(ops[-1][2], ops[0][1] + 1)
            spans = odd_spans(text) if odd_spans is not None else None
            if spans is None: return run(text)[1]
            return any(x < b + 1 and a - 1 < y for x, y, *_ in spans)
        if run(alt)[1] and odd_here(alt, other) and not odd_here(other, alt):
            alt, by_rule, gap = other, True, None
    if margin is None and not by_rule and gap is not None and gap < CHOOSE_GAP:
        return base, None      # どちらが余分か決められない（紫にする）
    sure = len(kana_rules.bad_spots(reading_of(line))) > len(kana_rules.bad_spots(reading_of(alt)))
    got, odd = run(alt)
    cands = []
    for g, o in ((alt, False), (got, odd)):
        # 抜いた形の補正が読みを替えずに漢字にしただけなら、文節の外の変換も採る（かなの行も漢字にする所は漢字に）
        if not o and (_local(line, alt, g) or (g is got and reading_of(g) == reading_of(alt))):
            c = path_cost(g)
            if c is not None: cands.append((c, g))
    if not cands:
        if margin is None and os.environ.get('CN_KD_FIRST') != '0':
            # 抜いた形に紫が残っても、間隔の短い2打は先に1字減らす（うに 11-08 03:44Z「紫が付かなくても間隔が短ければ
            # どちらか1字を削ったほうがいい」）。紫はその文節に付け直す
            return alt, 'fix_odd'
        return base, None
    cands.sort()
    if margin is None:
        # 基本疑う形では、抜いた形を補正に通した結果（漢字にした行）を先に使う
        cands.sort(key=lambda x: x[1] != got)
    bc = path_cost(base)
    if bc is None: return base, None
    if margin is None:
        # 間隔が短すぎる2打は巻き込みとして先に字を減らす（うに 11-08 03:42Z「打鍵間隔は優先してチェック」）。
        # 抜いた形が印なしの補正より不自然でも採る。CN_KD_FIRST=0 で前のまま（PRESUME_TOLERANCE を超えて悪ければ採らない）
        if (not sure and os.environ.get('CN_KD_FIRST') == '0'
                and min(c for c, _ in cands) > bc + PRESUME_TOLERANCE): return base, None
    elif cands[0][0] >= bc - (0.0 if sure else margin): return base, None
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
        # 句読点のキーはキーの字（, . - / [ ]）で記録されるので、読みの側の字（、。ー・「」）に揃えて比べる
        # （2026-11-06 ローマ字の試しのスレッド: 句読点を含む確定で巻き込みの戻しが効いていなかった）。CN_KD_PUNCT=0
        punct = str.maketrans({',': '、', '.': '。', '-': 'ー', '/': '・', '[': '「', ']': '」'}) \
            if os.environ.get('CN_KD_PUNCT') != '0' else {}
        conv = lambda ks: (halfwidth.romaji_to_kana(''.join(ks))[0] or '').translate(punct)
        if conv(keys) != rd: return []
        make = lambda d: conv(keys[:d] + keys[d + 1:])
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
    if input_method != 'romaji' and os.environ.get('CN_KD_BETWEEN') != '0':
        # 1つのキーの両隣（す の両隣の い・か）を、しきい値より短い間隔で続けて押した2打は、間のキーを押すつもりで
        # 両隣に触れた形（でいか → です）。2打を間のキー1つにした読みを、ほかの形と比べず1つだけの候補にする
        # （うに 11-08 03:42Z「打鍵間隔の情報は？」）。CN_KD_BETWEEN=0 で見ない
        import kana_layout
        at = {}
        for k_, p_ in kana_layout.KANA_POSITIONS.items():
            if len(k_) == 1 and 'ぁ' <= k_ <= 'ゖ':
                at.setdefault(p_, k_)
        for i, j in between_pairs(strokes, positions, adjacent):
            mids = [m for p_, m in at.items() if adjacent(positions.get(keys[i]), p_) and adjacent(p_, positions.get(keys[j]))]
            if len(mids) != 1: continue
            r = _compose_kana(typed[:i] + [mids[0]] + typed[j + 1:])
            if r and r != rd: out.append((r,))
    return out


def between_pairs(strokes, positions, adjacent, threshold_ms=DEFAULT_THRESHOLD_MS):
    """隣どうしではないが、1つのキーを挟む両隣（同じ手）の2打で、押した時刻の差がしきい値未満の (i, i+1)。"""
    out = []
    for i in range(len(strokes) - 1):
        (a, ta), (b, tb) = strokes[i], strokes[i + 1]
        if not a or not b or a == b: continue
        pa, pb = positions.get(a), positions.get(b)
        if pa is None or pb is None or adjacent(pa, pb): continue
        if pa[0] != pb[0] or abs(pa[1] - pb[1]) != 2: continue       # 同じ段で1つ挟んだ2つ
        ha, hb = _hand(pa), _hand(pb)
        if 'C' not in (ha, hb) and ha != hb: continue
        if tb - ta < threshold_ms: out.append((i, i + 1))
    return out


def repair_line(line, base, occurrences, input_method, run, convert=None):
    """
    line: 打った行。base: 印なしの補正の結果（dict）。occurrences: [(start, end, surface, reading, strokes)]。
    run(text) -> 印なしの補正の結果（dict）。convert(読み) -> IME の1つ目の変換（無ければ読みのまま入れる）。
    採ったときは、印の文節を直した結果（dict）を返す。採れない印があれば、その文節を紫にした base を返す。
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
    doubted = []
    for occ in occurrences or ():
        try:
            start, end, surface, reading, strokes = occ[:5]
        except (TypeError, ValueError):
            continue
        if line[start:end] != surface or not reading: continue
        # 印なしの補正が文節の外を直した行は混ぜない（どちらの直しも崩さないため、印なしのまま）
        if (done != line and os.environ.get('CN_KD_FIRST') == '0'
                and not _local(line, line[:start] + '\0' + line[end:], done, slack=0)): continue
        known = {}

        def reading_of2(text, known=known):
            k = known.get(text)
            if k is None:
                return reading_of(text)
            return reading_of(k[0]) + k[1] + reading_of(k[2])
        for rs in occurrence_alternatives(reading, strokes, input_method):
            if (start, end) not in doubted: doubted.append((start, end))
            alts = []
            for r in rs:
                face = None
                if convert is not None:
                    try: face = convert(r)
                    except Exception: face = None
                alts.append(line[:start] + (face or r) + line[end:])
                if os.environ.get('CN_KD_TYPED_READING') != '0':
                    # 抜いた形の読みは打った読み（r）を使う。表記から読み直すと 毛 → もう のように打った読みと違う読みで
                    # 比べてしまう（けとは と けさは の比べが もうとは になった・2026-11-08）。CN_KD_TYPED_READING=0
                    known[alts[-1]] = (line[:start], r, line[end:])
            got, how = repair_with_doubts(line, done, alts, run2, morphology.path_cost, reading_of2, yomi,
                                          odd_spans=lambda t: [tuple(x[:2]) for x in (runs[t].get('odd_spans') or ())] if t in runs else None)
            if how not in ('fix', 'fix_odd') or got == done or got == line: continue
            ops = [o for o in difflib.SequenceMatcher(None, line, got, autojunk=False).get_opcodes() if o[0] != 'equal']
            a, b, c, d = ops[0][1], ops[-1][2], ops[0][3], ops[-1][4]
            out = {'original': line, 'corrected': got, 'changed': True,
                   'details': [[line[a:b], got[c:d], '打鍵の間隔']], 'spans': [[c, d]], 'original_spans': [[a, b]],
                   'odd_spans': [], 'unsure_spans': [], 'odd_reasons': []}
            if how == 'fix_odd':
                out['_stroke_odd'] = [(start, end)]
            return out
    return _mark_doubted(line, base, done, doubted)


def _mark_doubted(line, base, done, doubted):
    """採れなかった印の文節を紫にする（紫の位置は打った行のもの）。印なしの補正が既に直した・紫にした所は触らない。"""
    if not doubted or not isinstance(base, dict): return base
    odd = [tuple(x) for x in (base.get('odd_spans') or ())]
    taken = odd + [tuple(x) for x in (base.get('original_spans') or ())]
    add = [(a, b) for a, b in doubted if not any(x < b and a < y for x, y in [t[:2] for t in taken])]
    if not add: return base
    out = dict(base)
    out['odd_spans'] = odd + add
    out['odd_reasons'] = [tuple(x) for x in (base.get('odd_reasons') or ())] + [(a, b, '打鍵の間隔（巻き込み）') for a, b in add]
    return out
