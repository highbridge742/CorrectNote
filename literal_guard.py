"""明示した引用例・ユーザーが守った語の字を、補正の全部の段の後でも変えない（2026-11-17）。

corrector の _with_literal_examples は corrector の中の直しだけを包む。その外の段（紫の所の読み直し odd_respell など）は
守った所を知らずに書き換え・紫にしていた（「ぽね」という表記です → ホール、守った がぞせう → 画像）。
一番外で、守った所に掛かる書き換えを原文に戻し、守った所の中の紫を外す。守った所の外の直しはそのまま。
CN_LITERAL_GUARD=0 で前のまま。
"""
import difflib
import functools
import os

_orig = {}


def _on():
    return os.environ.get('CN_LITERAL_GUARD') != '0'


def ranges_of(line, decisions=None):
    from literal_examples import protected_ranges
    ranges = list(protected_ranges(line))
    protected = getattr(decisions, 'protected_list', None)
    if callable(protected):
        for entry in protected() or ():
            word = entry.get('word', '') if isinstance(entry, dict) else ''
            if not isinstance(word, str) or len(word) < 2:
                continue
            pos = line.find(word)
            while pos >= 0:
                ranges.append((pos, pos + len(word)))
                pos = line.find(word, pos + 1)
    return sorted(ranges)


def _hits(a, b, ranges):
    if a == b:
        return any(lo < a < hi for lo, hi in ranges)
    return any(a < hi and lo < b for lo, hi in ranges)


def guard(line, result, decisions=None):
    if not _on() or not isinstance(line, str) or not isinstance(result, dict):
        return result
    ranges = ranges_of(line, decisions)
    if not ranges:
        return result
    text = result.get('corrected')
    out = dict(result)
    if isinstance(text, str) and text != line:
        ops = difflib.SequenceMatcher(None, line, text, autojunk=False).get_opcodes()
        if any(tag != 'equal' and _hits(i1, i2, ranges) for tag, i1, i2, j1, j2 in ops):
            new = ''.join(line[i1:i2] if (tag == 'equal' or _hits(i1, i2, ranges)) else text[j1:j2]
                          for tag, i1, i2, j1, j2 in ops)
            ops2 = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
            out.update({'corrected': new, 'changed': bool(ops2), 'spans': [[o[3], o[4]] for o in ops2],
                        'original_spans': [[o[1], o[2]] for o in ops2],
                        'details': [d for d in result.get('details') or ()
                                    if not (isinstance(d, (list, tuple)) and len(d) >= 2 and isinstance(d[1], str)
                                            and d[1] and d[1] not in new)]})
    for key in ('odd_spans', 'unsure_spans', 'odd_reasons'):
        if key in result:
            out[key] = [x for x in result.get(key) or ()
                        if not (len(x) >= 2 and isinstance(x[0], int) and isinstance(x[1], int)
                                and any(lo <= x[0] and x[1] <= hi for lo, hi in ranges))]
    return out


def correct_line(line, *args, **kwargs):
    result = _orig['correct_line'](line, *args, **kwargs)
    try:
        decisions = kwargs.get('decisions', args[2] if len(args) > 2 else None)
        return guard(line, result, decisions)
    except Exception:
        return result


def install():
    import correction_entry as ce
    if 'correct_line' in _orig:
        return
    _orig['correct_line'] = ce.correct_line
    functools.update_wrapper(correct_line, ce.correct_line)
    ce.correct_line = correct_line
