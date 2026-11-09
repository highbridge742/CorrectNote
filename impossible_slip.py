# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""
起こらない品詞のつながりの所のかな1字の打ち違い（impossible_slip・補正担当・2026-10-30）。

pos_grammar._impossible_connection_spans が「いまの文では起こらないつながり」と見た所（名詞＋文語の り・
名詞＋て・かな1字の名詞…）は、そこのかな1字が打ち違っている。そのつながりの中のかなを1字ずつ、
入力方式の配列で近いキー（隣・濁点・小書き）に替えてみて、
  - 行のどこにも起こらないつながりが残らず、
  - その辺りの語が全部読みを持つ
ものを行の費用（morphology.path_cost）で並べる。元の行より重くなる形は外す。一番が二番より MARGIN 以上軽ければ置き、並べば紫のまま。
ほかの理由で紫になった所と、漢字の後の説明の付かないかなの並び（報告｜しのす）も、より強い差があるときだけ
同じように見る（ODD_GAIN・ODD_MARGIN・かな入力だけ）。印の無い短いかなの並びも、さらに大きな差のときだけ見る
（SCAN_GAIN・SCAN_MARGIN）。
前の段が1か所直した行は、その所を元の行の1打違いの形と比べ直す（second_opinion）。
起こらないつながりも紫も無い行（正しい文）には何もしない。語を名指しした表は持たない。
"""
from functools import lru_cache
import difflib
import re

MARGIN = 1000
# ほかの理由の紫（つながりは起こり得る）の所は、根拠が弱いので、元の行より大きく軽く・二番とも大きく離れたときだけ
ODD_GAIN = 2500
ODD_MARGIN = 2000
# 印の無い所（漢字・片仮名の後の短いかなの並び）は、正しい文でも1字替えで軽くなる形がある（正しい文 2,400行で最大
# 約6,000）。それより十分大きく軽く、二番とも大きく離れたときだけ
SCAN_GAIN = 8000
SCAN_MARGIN = 5000
SCAN_LEN = 4
# 前の段が直した所を、元の行の1打違いと比べ直す（second_opinion）。正しい文 2,400行で最大 約1,500
OVERRIDE_GAIN = 4000
OVERRIDE_MARGIN = 3000


def _hira(ch):
    return 'ぁ' <= ch <= 'ゖ'


def _loose_form(toks, near, before):
    """替えた形が別の崩れ方をしているか。
      - 元の行に無かった、かなだけの名詞（見直しの｜はた）: 打ち違いの切れ端が名詞に読まれただけ
      - 後ろに名詞の無い接頭詞（進まん｜す。）
      - 打ち消しの ん に接続助詞（進まん｜て）: いまの書き言葉では ずに・ないで
      - 文語の活用（体言接続特殊）・係助詞や格助詞に直に付く た
      - 終助詞の後に区切りなしで続く中身の語
    """
    for t in near:
        if t.pos == '名詞' and all(_hira(c) for c in t.surface) and (t.surface, t.pos) not in before:
            return True
        # 文語の活用（来｜く の体言接続特殊）に読まれた形
        if (t.infl_form or '').startswith('体言接続特殊'):
            return True
    for i, t in enumerate(toks):
        nx = toks[i + 1] if i + 1 < len(toks) else None
        if t not in near and (nx is None or nx not in near):
            continue
        if t.pos == '接頭詞' and (nx is None or nx.pos != '名詞'):
            return True
        # 文の終わりの助詞の後に、区切りなしで中身の語が続く（都市｜け｜かかる）
        if t.pos == '助詞' and (t.pos_sub or '').startswith('終助詞') and nx is not None \
                and nx.pos in ('名詞', '動詞', '形容詞', '副詞'):
            return True
        # 係助詞・格助詞に過去の た が直に付く（は｜た）
        if t.pos == '助詞' and (t.pos_sub or '').startswith(('係助詞', '格助詞')) and nx is not None \
                and nx.pos == '助動詞' and nx.base_form == 'た':
            return True
        if t.pos == '助動詞' and t.base_form in ('ん', 'ぬ') and nx is not None and nx.pos == '助詞' \
                and (nx.pos_sub or '').startswith('接続助詞'):
            return True
    return False


def _weak_new_word(toks, near, before):
    """ほかの理由の紫の所で、替えた形に元の行に無かった中身の語が、かなだけ（かいい・ゆう）か漢字1字だけ（縮｜に）で
    現れるか。読みの近い語に寄せただけで、文が良くなったとは言えない形。
    かなだけの用言でも、すぐ後ろに助動詞が付く（なっ｜た）なら活用が並びで確かめられるので外さない。"""
    for i, t in enumerate(toks):
        # かなで書いた名詞（へんじ｜へ）がその辺りに残る所は、読みのまま書かれた行。1字替えても直ったとは言えない
        if (t in near and t.pos == '名詞' and len(t.surface) >= 2 and all(_hira(c) for c in t.surface)
                and (t.pos_sub or '').startswith(('一般', 'サ変接続', '形容動詞語幹'))):
            return True
        # かなだけの動詞（へんじ｜へ・ほせ｜て）は、すぐ後ろに助動詞が付く（かかり｜ます）ときだけ活用が確かめられる
        if (t in near and t.pos == '動詞' and len(t.surface) >= 2 and all(_hira(c) for c in t.surface)
                and (t.pos_sub or '').startswith('自立')):
            nx = toks[i + 1] if i + 1 < len(toks) else None
            if nx is None or nx.pos != '助動詞' or nx.start != t.end:
                return True
        if t not in near or (t.surface, t.pos) in before or t.pos not in ('名詞', '動詞', '形容詞'):
            continue
        if (t.pos_sub or '').startswith(('非自立', '接尾')):
            continue
        if len(t.surface) == 1 and not _hira(t.surface):
            return True
        if all(_hira(c) for c in t.surface):
            nx = toks[i + 1] if i + 1 < len(toks) else None
            if t.pos in ('動詞', '形容詞') and nx is not None and nx.pos == '助動詞' and nx.start == t.end:
                continue
            return True
    return False


# 隣のキーの、シフトの面のかな（隣＋シフトの2打）。ほ の隣の わ のシフト面は を。打つときにシフトを押したまま
# 隣のキーに指が掛かる形。1打違いより遠いので距離を足すが、候補に入れないと、助詞の を が来る所で
# 隣の へ だけが残って決まってしまう（手紙ほ書いた → 手紙へ書いた）。
SHIFT_FACE_DIST = 0.3


def _with_shift_face(alts):
    from kana_layout import SHIFT_KANA_PAIR
    have = {a for a, _ in alts}
    out = list(alts)
    for alt, dist in alts:
        if dist < 1.0:
            continue
        other = SHIFT_KANA_PAIR.get(alt)
        if other and other not in have:
            have.add(other)
            out.append((other, dist + SHIFT_FACE_DIST))
    return out


PAIR_MIN = 2      # 名詞＋助詞＋述語の組がこれだけ例文に在る助詞が1つだけなら、それに決める
PAIR_COST_SLACK = 3000  # 一番の形からこれだけ重い形までを、助詞の替え方の並びとして見る


def _particle_at(cand, k):
    """cand の k の字が 名詞＋助詞1字＋述語 の助詞なら (助詞, 名詞, 述語の基本形)。"""
    import morphology
    import pair_choice
    toks = list(morphology.tokenize(cand))
    for i, t in enumerate(toks):
        if t.start == k and t.end == k + 1:
            if t.pos == '助詞' and 0 < i < len(toks) - 1 and pair_choice._noun(toks[i - 1]) \
                    and toks[i + 1].pos in ('動詞', '形容詞') and toks[i - 1].end == k and toks[i + 1].start == k + 1:
                return t.surface, toks[i - 1].surface, pair_choice._base(toks[i + 1])
            return None
    return None


def _pair_seen(cand, k):
    import pair_choice
    table = pair_choice._table()
    key = _particle_at(cand, k) if table else None
    return key is not None and table[0].get('\t'.join(key), 0) >= PAIR_MIN


def _particle_by_pairs(text, cands):
    """一番と、近い重さの形が、どれも同じ所の助詞1字の替え方（名詞＋助詞＋述語）のとき、例文の組の回数で1つに決める。
    組が PAIR_MIN 以上の形がちょうど1つで、ほかの形の組が例文に無ければ、その形 (cost, k, alt)。決まらなければ None。"""
    import pair_choice
    table = pair_choice._table()
    if not table or len(cands) < 2:
        return None
    pairs = table[0]
    top = cands[0][0]
    near = [c for c in cands if c[0] - top <= PAIR_COST_SLACK and c[1] == cands[0][1]]
    if len(near) < 2:
        return None
    counts = []
    for c in near:
        cand = text[:c[1]] + c[2] + text[c[1] + 1:]
        key = _particle_at(cand, c[1])
        if key is None:
            return None
        counts.append((pairs.get('\t'.join(key), 0), c))
    strong = [c for n, c in counts if n >= PAIR_MIN]
    if len(strong) == 1 and all(n == 0 for n, c in counts if c is not strong[0]):
        return strong[0]
    if strong:
        return None
    # 組そのものが例文に無いときは、助詞＋述語（どの名詞でも）と 名詞＋助詞（どの述語でも）の両方で見る。
    # 片方の助詞だけが両方に SIDE_MIN 以上在り、ほかの助詞はどちらかが例文に無ければ、それに決める
    sides = _pair_sides()
    scored = []
    for c in near:
        cand = text[:c[1]] + c[2] + text[c[1] + 1:]
        p, noun, verb = _particle_at(cand, c[1])
        scored.append((sides[0].get((p, verb), 0), sides[1].get((p, noun), 0), c))
    # 名詞が例文に出ない語（どの助詞とも組が無い）なら、述語の側だけで見る
    noun_seen = any(n for v, n, c in scored)
    good = [c for v, n, c in scored if v >= SIDE_MIN and (n >= SIDE_MIN or not noun_seen)]
    if len(good) == 1 and all(v == 0 or (noun_seen and n == 0) for v, n, c in scored if c is not good[0]):
        return good[0]
    return None


SIDE_MIN = 5


@lru_cache(maxsize=1)
def _pair_sides():
    """例文の組から (助詞, 述語) と (助詞, 名詞) の回数。"""
    import pair_choice
    table = pair_choice._table()
    by_verb, by_noun = {}, {}
    for key, n in (table[0].items() if table else ()):
        parts = key.split('\t')
        if len(parts) != 3 or len(parts[0]) != 1:
            continue
        p, noun, verb = parts
        by_verb[(p, verb)] = by_verb.get((p, verb), 0) + n
        by_noun[(p, noun)] = by_noun.get((p, noun), 0) + n
    return by_verb, by_noun


def _plural_after_noun(text, a, tail):
    """text[a:] の tail が、解析で名詞のすぐ後ろの接尾の1語（お前｜ら）か。"""
    try:
        import morphology
        toks = list(morphology.tokenize(text))
    except Exception:
        return False
    return any(t.start == a and t.surface == tail and t.pos == '名詞' and (t.pos_sub or '').startswith('接尾')
               and p.pos == '名詞' and p.end == a for p, t in zip(toks, toks[1:]))


def unexplained_runs(text):
    """漢字の直後から始まるかなの並び（送りがな＋機能語）のうち、かなの文法で説明の付かないもの（報告｜しのす）。
    並びの終わりの お・ご が漢字の前なら次の語の頭なので並びに入れない。"""
    import pos_grammar
    out = []
    for m in re.finditer('[ぁ-ゖ]+', text):
        a, b = m.span()
        if b < len(text) and _kanji(text[b]) and text[b - 1] in 'おご':
            b -= 1
        if a == 0 or not _kanji(text[a - 1]) or b <= a:
            continue
        stem = re.search('[一-鿿々]+$', text[:a]).group()
        if not pos_grammar.explain_kana_run(text[a:b], after_kanji=True, kanji_stem=stem):
            # 漢字＋人の複数の接尾（お前｜ら・私｜たち）で、残りが説明できるもの（2026-11-07）。CN_SLIP_SCAN_PLURAL=0
            run = text[a:b]
            tail = next((t for t in ('たち', 'ども', 'ら') if run.startswith(t)), None)
            if (tail and __import__('os').environ.get('CN_SLIP_SCAN_PLURAL') != '0'
                    and (pos_grammar._one_token(stem[-1:] + tail) or _plural_after_noun(text, a, tail))
                    and (len(run) == len(tail) or pos_grammar.explain_kana_run(run[len(tail):]))):
                continue
            out.append((a, b))
    return out


def scan_runs(text):
    """漢字・片仮名の直後から始まるかなの並びの頭 SCAN_LEN 字（送りがな・助詞の所）。印が無くても見る所。"""
    out = []
    for m in re.finditer('[ぁ-ゖ]+', text):
        a, b = m.span()
        if a > 0 and (_kanji(text[a - 1]) or 'ァ' <= text[a - 1] <= 'ヺ' or text[a - 1] == 'ー'):
            out.append((a, min(b, a + SCAN_LEN)))
    return out


def _kanji(ch):
    return '一' <= ch <= '鿿' or ch == '々'


def _still_odd(text, k, alt, lo, hi):
    """text[k] を alt に替えた行で、替えた辺り（lo-1〜hi+1）にまだ説明の付かないかなの並び（pos_grammar.odd_kana_spans）が残るか。"""
    import pos_grammar
    cand = text[:k] + alt + text[k + 1:]
    try:
        spans = pos_grammar.odd_kana_spans(cand)
    except Exception:
        return False
    return any(a < hi + 1 and lo - 1 < b for a, b in spans)


def propose(text, input_method='kana', odd_spans=(), scan=False):
    """[(開始, 終了, 置く文字列 or None)]（text の位置）。"""
    import pos_grammar
    import morphology
    from kana_layout import nearby_candidates
    spans = [(a, b, 'strong') for a, b in pos_grammar._impossible_connection_spans(text)]
    spans += [(a, b, 'weak') for a, b in odd_spans if not any(x < b and a < y for x, y, _ in spans)]
    if scan:
        spans += [(a, b, 'scan') for a, b in scan_runs(text) if not any(x < b and a < y for x, y, _ in spans)]
    out = []
    _orig_toks = list(morphology.tokenize(text))
    before = {(t.surface, t.pos) for t in _orig_toks}
    adverbial_particles = {k for t in _orig_toks if t.pos == '助詞' and (t.pos_sub or '').startswith('副助詞')
                           for k in range(t.start, t.end)}
    # 終助詞（待っててね・行くよ・そうだな）も、印の無い所では替えない。話し言葉の文末に多く、替えると 待っててる の
    # ような別の形が軽く出る（2026-11-05 うに「縮まった形が抜けていたなら同じようなパターンがあるかもしれない」）。
    # CN_SLIP_SCAN_FINAL=0 で前のまま
    if __import__('os').environ.get('CN_SLIP_SCAN_FINAL') != '0':
        adverbial_particles |= {k for t in _orig_toks if t.pos == '助詞' and (t.pos_sub or '').startswith('終助詞')
                                for k in range(t.start, t.end)}
    # 名詞のすぐ後ろの複数の接尾（お前｜ら・アイツ｜ら・私｜たち）も、印の無い所では替えない（お前ら→お前に: 例文
    # Tatoeba の正しい文で見つけた・2026-11-07）。CN_SLIP_SCAN_PLURAL=0 で前のまま
    if __import__('os').environ.get('CN_SLIP_SCAN_PLURAL') != '0':
        adverbial_particles |= {k for p, t in zip(_orig_toks, _orig_toks[1:])
                                if t.pos == '名詞' and (t.pos_sub or '').startswith('接尾') and t.surface in ('ら', 'たち', 'ども')
                                and p.pos == '名詞' and p.end == t.start for k in range(t.start, t.end)}
    base = morphology.path_cost(text)
    if base is None:
        return []
    for lo, hi, level in spans:
        strong = level == 'strong'
        cands = []
        for k in range(lo, hi):
            if not _hira(text[k]):
                continue
            # 印の無い所では、副助詞（何｜か・誰だ｜か）は替えない。不定の言い方として正しい文に多く、替えると軽く出る
            if level == 'scan' and k in adverbial_particles:
                continue
            try:
                alts = nearby_candidates(text[k], max_dist=1.0, include_phonetic=False, input_method=input_method)
            except Exception:
                alts = ()
            if input_method == 'kana':
                alts = _with_shift_face(alts)
            for alt, dist in alts:
                if alt == text[k] or not _hira(alt):
                    continue
                cand = text[:k] + alt + text[k + 1:]
                if level == 'scan':
                    # 印の無い所は先に費用だけ見る。決まるのは一番が SCAN_GAIN 以上・二番と SCAN_MARGIN 以上離れたときなので、
                    # その差より軽くならない形は答えに関わらない
                    cost = morphology.path_cost(cand)
                    if cost is None or base - cost < SCAN_GAIN - SCAN_MARGIN:
                        continue
                if pos_grammar._impossible_connection_spans(cand):
                    continue
                toks = list(morphology.tokenize(cand))
                near = [t for t in toks if t.end > lo - 1 and t.start < hi + 1]
                if not all(t.has_reading for t in near) or _loose_form(toks, near, before):
                    continue
                # 漢字1字の名詞が切り直しで現れても（本｜ほ → 本｜を）、名詞＋助詞＋述語の組が例文に在れば確かめられている
                if not strong and _weak_new_word(toks, near, before) and not _pair_seen(cand, k):
                    continue
                cost = morphology.path_cost(cand)
                # 元の行より自然になる形だけ（つながりを1つ直しても、ほかが崩れて重くなる形は答えではない）
                if cost is not None and cost < base:
                    cands.append((cost, k, alt))
        if not cands:
            continue
        cands.sort()
        if not strong and cands and _still_odd(text, cands[0][1], cands[0][2], lo, hi):
            # 置いた形のかなの並びがまだ説明の付かない並びなら、直しにならない（つらたん→つらてん: 元より崩れる）
            # 一番の形が直しにならないなら、二番以下を繰り上げずに見送る。紫は前の段に任せる（2026-10-31）
            continue
        gain = base - cands[0][0]
        gap = cands[1][0] - cands[0][0] if len(cands) > 1 else None
        picked = _particle_by_pairs(text, cands)
        if picked is not None:
            # 名詞と述語の間の助詞1字の替え方が並ぶ所は、例文の組（名詞＋助詞＋述語）で決まるならそれを置く
            out.append((picked[1], picked[1] + 1, picked[2]))
            _BY_PAIRS.add((text, picked[1], picked[2]))
            continue
        need = {'strong': (None, MARGIN), 'weak': (ODD_GAIN, ODD_MARGIN), 'scan': (SCAN_GAIN, SCAN_MARGIN)}[level]
        if (need[0] is None or gain >= need[0]) and (gap is None or gap >= need[1]):
            _, k, alt = cands[0]
            out.append((k, k + 1, alt))
        else:
            out.append((lo, hi, None))
    return out


def _to_original(line, done, s, e):
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, done, line, autojunk=False).get_opcodes():
        if tag == 'equal' and i1 <= s and e <= i2:
            return s - i1 + j1, e - i1 + j1
    return None


def second_opinion(line, done):
    """前の段が直した所が1か所のとき、その所（と両隣の1字）のかなを元の行で1打だけ近いキーに替えた形と、
    前の段の答えを行の費用で比べる。替えた形が OVERRIDE_GAIN 以上軽く、二番とも OVERRIDE_MARGIN 以上離れていれば、
    その形を返す（会議前 ではなく 開きます）。無ければ None。"""
    import pos_grammar
    import morphology
    from kana_layout import nearby_candidates
    ops = [o for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes() if o[0] != 'equal']
    if len(ops) != 1:
        return None
    _, i1, i2, j1, j2 = ops[0]
    base = morphology.path_cost(done)
    if base is None:
        return None
    before = {(t.surface, t.pos) for t in morphology.tokenize(line)}
    cands = []
    for k in range(max(0, i1 - 1), min(len(line), i2 + 1)):
        if not _hira(line[k]):
            continue
        for alt, dist in nearby_candidates(line[k], max_dist=1.0, include_phonetic=False, input_method='kana'):
            if alt == line[k] or not _hira(alt):
                continue
            seg = line[:k] + alt + line[k + 1:]
            a, b = min(i1, k), max(i2, k + 1)
            if any(c in '゛゜' for c in seg[a:b]):
                # 前の段の直しが単独の印を前の字に付けた所（は゛す→ばす）は、戻すと印が行に残る。比べる形にしない
                continue
            cand = done[:j1 - (i1 - a)] + seg[a:b] + done[j2 + (b - i2):]
            if pos_grammar._impossible_connection_spans(cand):
                continue
            toks = list(morphology.tokenize(cand))
            lo = j1 - (i1 - a)
            near = [t for t in toks if t.end > lo - 1 and t.start < lo + (b - a) + 1]
            if (not all(t.has_reading for t in near) or _loose_form(toks, near, before)
                    or _weak_new_word(toks, near, before)):
                continue
            cost = morphology.path_cost(cand)
            if cost is not None and cost < base:
                cands.append((cost, cand))
    if not cands:
        return None
    cands.sort()
    gap = cands[1][0] - cands[0][0] if len(cands) > 1 else None
    if base - cands[0][0] >= OVERRIDE_GAIN and (gap is None or gap >= OVERRIDE_MARGIN):
        return cands[0][1]
    return None


# 直す形が1つに決まっても置かず、紫だけにする（2026-11-01 手分けB: 打った読みの記録ありの作った1打違い1,466件で、
# この段が置いた答えは 直る5・別の誤り27。途中までの直し（漢字の語の中の打ち違いが残ったまま後ろのかなだけ替える）と
# 助詞の選び違いが多く、費用や1字あたりの費用では分けられなかった。決めきれない所は紫）
DECIDE = False
# 例文の組（名詞＋助詞＋述語）で助詞1字が決まった所は、紫にせず置く（propose が入れる (行, 位置, 字)）
PAIRS_DECIDE = True
_BY_PAIRS = set()
ROUGH_PER_CHAR = 1600   # 直した欄の並びの費用を字数で割った値がこれを超えれば、まだ崩れた文（途中までの直し）


def _rough_field(text, k):
    """text の k を含む欄（タブ・改行で切る）の並びの費用の1字あたりが ROUGH_PER_CHAR を超えるか。"""
    a = max(text.rfind('\t', 0, k), text.rfind('\n', 0, k)) + 1
    b = min([x for x in (text.find('\t', k), text.find('\n', k)) if x >= 0] or [len(text)])
    field = text[a:b].strip()
    if not field:
        return False
    try:
        import morphology
        c = morphology.path_cost(field)
    except Exception:
        return False
    return c is not None and c / len(field) > ROUGH_PER_CHAR


def repair_line(line, result, decided=(), input_method='kana'):
    if not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done != line and input_method == 'kana':
        try:
            other = second_opinion(line, done)
        except Exception:
            other = None
        if other is not None:
            ops = [o for o in difflib.SequenceMatcher(None, line, other, autojunk=False).get_opcodes() if o[0] != 'equal']
            if ops and not DECIDE and not any(x < o[2] and o[1] < y for o in ops for x, y in (decided or ())):
                # 前の段の答えより別の1打の形が自然でも、置かずに紫（前の段の答えはそのまま）
                out = dict(result)
                out['odd_spans'] = sorted(set(tuple(x[:2]) for x in (result.get('odd_spans') or ()))
                                          | {(o[1], max(o[2], o[1] + 1)) for o in ops})
                return out
            if ops and not any(x < o[2] and o[1] < y for o in ops for x, y in (decided or ())):
                out = dict(result)
                out.update({'original': line, 'corrected': other, 'changed': True,
                            'details': list(result.get('details') or []) + [[done, other, '1打違いと比べ直し']],
                            'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
                near = [(o[1] - 1, o[2] + 1) for o in ops]
                for key in ('odd_spans', 'unsure_spans'):
                    out[key] = [sp for sp in (result.get(key) or ()) if not any(a < sp[1] and sp[0] < b for a, b in near)]
                if 'odd_reasons' in result:
                    out['odd_reasons'] = [r for r in (result.get('odd_reasons') or ()) if not any(a < r[1] and r[0] < b for a, b in near)]
                return out
    try:
        # 紫は元の行の位置。まだ何も置いていない行だけ、その紫も見る（かな入力だけ。ローマ字の近いキーは紫の所では確かめていない）
        odd = [tuple(sp[:2]) for sp in (result.get('odd_spans') or ())] if done == line and input_method == 'kana' else []
        # 漢字の後の説明の付かないかなの並びも、紫と同じ強さで見る（かな入力だけ・置いた後の行の位置）
        if input_method == 'kana':
            odd += [sp for sp in unexplained_runs(done) if not any(x < sp[1] and sp[0] < y for x, y in odd)]
        _BY_PAIRS.clear()
        marks = [m for m in propose(done, input_method, odd, scan=input_method == 'kana') if m[2] is not None]
    except Exception:
        return result
    if not marks:
        return result
    changed = [(o[3], o[4]) for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
               if o[0] != 'equal']
    new, details, cleared, purple = done, [], [], []
    for s, e, rep in sorted(marks, reverse=True):
        if any(x <= e and s <= y for x, y in changed):
            continue
        org = _to_original(line, done, s, e)
        if org is None or any(x < org[1] and org[0] < y for x, y in (decided or ())):
            continue
        cand = new[:s] + rep + new[e:]
        # 例文で決まった助詞・置いた形の 名詞＋助詞＋述語 の組が例文に在る所は置く（手紙ほ書いた → を）
        by_pairs = PAIRS_DECIDE and ((done, s, rep) in _BY_PAIRS or (e - s == 1 and _pair_seen(cand, s)))
        if (not DECIDE and not by_pairs) or _rough_field(cand, s):
            # 戻した後も、その欄（タブまで）が1字あたりの並びの費用で崩れたまま（途中までの直し）なら、決めずに紫
            # （作った1打違い1,466件で、この段の直しは 正しい5（1字あたり 1,545 以下）・別の誤り78 だった・2026-11-01 補正担当）
            purple.append(org)
            continue
        new = cand
        details.append([done[s:e], rep, '起こらないつながり'])
        cleared.append(org)
    if new == done:
        if purple:
            out = dict(result)
            out['odd_spans'] = sorted(set(tuple(x[:2]) for x in (result.get('odd_spans') or ())) | set(purple))
            return out
        return result
    ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out = dict(result)
    out.update({'original': line, 'corrected': new, 'changed': True,
                'details': list(result.get('details') or []) + details,
                'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    # 置いた字に重なる紫・迷い（元の行の位置）と、その前後1字に接する紫（つながりの印）は外す
    near = [(a - 1, b + 1) for a, b in cleared]
    for key in ('odd_spans', 'unsure_spans'):
        out[key] = [sp for sp in (result.get(key) or ()) if not any(a < sp[1] and sp[0] < b for a, b in near)]
    if 'odd_reasons' in result:
        out['odd_reasons'] = [r for r in (result.get('odd_reasons') or ()) if not any(a < r[1] and r[0] < b for a, b in near)]
    if purple:
        out['odd_spans'] = sorted(set(tuple(x[:2]) for x in out['odd_spans']) | set(purple))
    return out
