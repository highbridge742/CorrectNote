"""辞書の語のまま読める行の語を、使われやすさの差や例文の組の少なさだけで別の語に置き換えない（2026-11-14 補正担当・
全体評価の方針 v2 の N）。

なぜ
----
正しい行の正しい語が、「あまり使わない語」の紫や組の少なさを入口に、1打違い・同音のより使われる語へ置き換わっていた
（作った例: 読書に充てている → 当てている・広報担当 → 高等担当）。元の語は辞書の語で、行はそのまま読める。
使われやすさの差と、組が例文に無いことは、打ち違いの跡ではない。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む（答えが出た後に見る）。
答えの直しのうち、根拠が使われやすさ・組の段（紫の所の打ち違い・意味の分類・IMEの選び違い）だけのものについて:
1. 元の行の、書き換えた所に掛かる語がどれも辞書の語（読みのある語で、漢字1字の名詞の切れ端でない）で、
2. 元の行の並びが文法で切れていない（broken_shape・pos_seq_odd がその所の近くに何も出さない）なら、
その書き換えを採らず元の字に戻し、そこに掛かる紫も外す（決められないので紫も付けない）。
ほかの段の直し（打ち違いの跡のある所）はそのまま。特定の語や文字列には合わせない。

切り替え: CN_DICT_WORD_KEEP=0 で前のまま。
"""
import difflib
import functools
import os

_orig = {}

WEAK = ('紫の所の打ち違い', '意味の分類', 'IMEの選び違い', '語の組')


# 広げる試し（2026-11-14 全体評価の頼み）: かな入力・脱字 の直しにも同じ考えを当てる。既定は当てない
WIDE = ('かな入力', '脱字')


def _weak():
    return WEAK + WIDE if os.environ.get('CN_DICT_WORD_KEEP_WIDE') == '1' else WEAK


def _on():
    return os.environ.get('CN_DICT_WORD_KEEP') != '0'


def _kanji(s):
    return bool(s) and all('一' <= c <= '鿿' or c == '々' for c in s)


def _latin(s):
    return any(c.isascii() and c.isalpha() or 'ａ' <= c <= 'ｚ' or 'Ａ' <= c <= 'Ｚ' for c in s)


def _dict_word(t):
    if not getattr(t, 'has_reading', True) or _latin(t.surface):
        return False
    if t.pos in ('助詞', '助動詞'):
        return True
    # 記号・感動詞（ああ・わあ: 文の中の感動詞は打ち違いの跡のことが多い）・人名や地名（辞書の語でも行の中で浮く）は見ない
    if t.pos in ('記号', '感動詞', 'フィラー', 'その他') or str(t.pos_sub or '').startswith('固有名詞'):
        return False
    if t.pos == '名詞' and len(t.surface) == 1 and _kanji(t.surface):
        return False
    try:
        from morphology import dictionary_inflections
        return bool(dictionary_inflections(t.surface))
    except Exception:
        return False


def _verb_run(seq):
    """言い切りの動詞のすぐ後ろに自立の動詞（向く｜なっ）: 文法で切れた並び"""
    for x, y in zip(seq, seq[1:]):
        if (x.pos == '動詞' and (x.infl_form or '') == '基本形' and y.pos == '動詞'
                and str(y.pos_sub or '') == '自立' and x.end == y.start):
            return True
    return False


def _breaks(line, a, b):
    """元の行の a..b の近く（前後1字）に、文法の切れ目の印（崩れた形・品詞の並びの変な所）が在るか"""
    found = []
    try:
        import broken_shape
        found += [x[:2] for x in broken_shape.spans(line) or ()]
    except Exception:
        pass
    try:
        import pos_seq_odd
        found += [x[:2] for x in pos_seq_odd.spots(line) or ()]
    except Exception:
        pass
    return any(s < b + 1 and a - 1 < e for s, e in found)


def _code_any(line):
    try:
        import odd_reason_fill as F
        return bool(F.code_runs(line))
    except Exception:
        return False


def _in_code(line, i1, i2):
    try:
        import odd_reason_fill as F
        return any(a <= i1 and max(i2, i1 + 1) <= b for a, b in F.code_runs(line))
    except Exception:
        return False


def _covers(line, src, i1, i2):
    p = line.find(src)
    while p >= 0:
        if p <= i1 and max(i2, i1 + 1) <= p + len(src):
            return True
        p = line.find(src, p + 1)
    return False


def keep(line, result):
    if not _on() or not isinstance(line, str) or not isinstance(result, dict):
        return result
    text = result.get('corrected')
    details = [d for d in result.get('details') or () if isinstance(d, (list, tuple)) and len(d) >= 3]
    if not isinstance(text, str) or text == line or not details:
        return result
    weak_src = {d[0] for d in details if d[2] in _weak() and isinstance(d[0], str) and d[0]}
    if not weak_src and not (os.environ.get('CN_DICT_WORD_KEEP_CODE') != '0' and any(c.isdigit() for c in line)
                             and _code_any(line)):
        return result
    try:
        from morphology import tokenize
        toks = list(tokenize(line))
    except Exception:
        return result
    ops = difflib.SequenceMatcher(None, line, text, autojunk=False).get_opcodes()
    undo = []
    for tag, i1, i2, j1, j2 in ops:
        if tag == 'equal':
            continue
        # S: 型番・略号（英大文字・数字・ハイフンだけの並び: UD-27K）の中の書き換えは、どの段でも採らない。CN_DICT_WORD_KEEP_CODE=0
        if os.environ.get('CN_DICT_WORD_KEEP_CODE') != '0' and _in_code(line, i1, i2):
            undo.append((i1, i2, j1, j2, i1, max(i2, i1 + 1)))
            continue
        # この書き換えが弱い根拠の直しの所か（直しの元の字が、書き換えた所を含む）
        mine = [d for d in details if d[2] in _weak() and isinstance(d[0], str) and d[0] and _covers(line, d[0], i1, i2)]
        if not mine:
            continue
        others = [d for d in details if d[2] not in _weak() and d[0] and d[0] in line[max(0, i1 - 2):i2 + 2]]
        if others:
            continue
        hit = [t for t in toks if t.start < max(i2, i1 + 1) and i1 < t.end]
        if not hit or not all(_dict_word(t) for t in hit):
            continue
        # 前後の1語も、英字・感動詞・記号でない（打ち違いの跡が隣に在る行は見ない）
        n0, n1 = toks.index(hit[0]), toks.index(hit[-1])
        side = toks[max(0, n0 - 1):n0] + toks[n1 + 1:n1 + 2]
        if any(_latin(t.surface) or t.pos in ('感動詞', 'フィラー', 'その他') or not getattr(t, 'has_reading', True)
               for t in side):
            continue
        if _verb_run(toks[max(0, n0 - 1):n1 + 2]):
            continue
        # 文の途中の終助詞（すずし｜いす｜ぜ｜が の ぜ）は、かなの並びの切り方が崩れた印。辞書の語の並びとは見ない
        # （2026-11-14 補正担当: かなのまま打った誤字の束で、すぜ→かぜ・はすん→はん の直しを戻していた）。
        # CN_DICT_WORD_KEEP_MID_FINAL=0 で前のまま
        if os.environ.get('CN_DICT_WORD_KEEP_MID_FINAL') != '0' and any(
                t.pos == '助詞' and str(t.pos_sub or '').startswith('終助詞') and k + 1 < len(toks)
                and toks[k + 1].pos != '記号'
                for k, t in enumerate(toks[max(0, n0 - 1):n1 + 2], max(0, n0 - 1))):
            continue
        a, b = hit[0].start, hit[-1].end
        if _breaks(line, a, b):
            continue
        undo.append((i1, i2, j1, j2, a, b))
    if not undo:
        return result
    parts = []
    for tag, i1, i2, j1, j2 in ops:
        if tag != 'equal' and any(u[0] == i1 and u[1] == i2 and u[2] == j1 for u in undo):
            parts.append(line[i1:i2])
        else:
            parts.append(text[j1:j2] if tag != 'equal' else line[i1:i2])
    new = ''.join(parts)
    out = dict(result)
    ops2 = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out.update({'corrected': new, 'changed': bool(ops2), 'spans': [[o[3], o[4]] for o in ops2],
                'original_spans': [[o[1], o[2]] for o in ops2],
                'details': [d for d in result.get('details') or ()
                            if not (isinstance(d, (list, tuple)) and len(d) >= 3 and d[2] in _weak()
                                    and isinstance(d[1], str) and d[1] and d[1] not in new)]})
    near = [(u[4], u[5]) for u in undo]

    def far(x):
        return not (len(x) >= 2 and isinstance(x[0], int) and any(x[0] < e and s < x[1] for s, e in near))
    for key in ('odd_spans', 'unsure_spans', 'odd_reasons'):
        if key in result:
            out[key] = [x for x in result.get(key) or () if far(x)]
    return out


def correct_line(line, *args, **kwargs):
    result = _orig['correct_line'](line, *args, **kwargs)
    try:
        return keep(line, result)
    except Exception:
        return result


def install():
    import correction_entry as ce
    if 'correct_line' in _orig:
        return
    _orig['correct_line'] = ce.correct_line
    functools.update_wrapper(correct_line, ce.correct_line)
    ce.correct_line = correct_line


def uninstall():
    import correction_entry as ce
    fn = _orig.pop('correct_line', None)
    if fn is not None and ce.correct_line is correct_line:
        ce.correct_line = fn
    correct_line.__dict__.pop('__wrapped__', None)
