# -*- coding: utf-8 -*-
"""付けられない字の後ろの小書きの ゃゅょ（ね＋ょ・な＋ゅ）を、前の字を替えずに片付けた直しは採らず紫（2026-11-01 B）。

かな入力で ゃゅょ が付けられない字（イ段でない字）の後ろに来るのは、前の字のキーを隣と打ち違えた跡が多い
（り を ね・に を な と打った: しねょう ← しりょう）。前の字を隣のイ段のキーに替えれば拗音として読める所で、
ほかの段が 小書きを大きくする・抜く・別の語にまとめる（死ねよう・失う）形で片付けた直しは、どちらの打ち違いか
決め手が無い。直しを外して元の行に戻し、そこに紫を付ける（迷うなら紫）。
直した所の読みに、イ段の字＋同じ小書き（りょ・にゅ）が残る直し（補給 ← きほゅう の きゅ）はそのまま。
語や文字列を名指しした表は持たない（キーの並びと読みだけで見る）。
"""
import difflib

_I_ROW = 'きぎしじちぢにひびぴみりい'
_SMALL = 'ゃゅょ'


def _hira(ch):
    return 'ぁ' <= ch <= 'ゖ'


def _irow_neighbor(ch):
    try:
        from kana_layout import nearby_candidates
        return any(a in _I_ROW for a, d in nearby_candidates(ch, max_dist=1.05, include_phonetic=False,
                                                              input_method='kana') if d >= 1.0)
    except Exception:
        return False


def _reading(text):
    try:
        import odd_respell
        return odd_respell._line_reading(text) or text
    except Exception:
        return text


def spots(line):
    """付けられない字（イ段でない平仮名）の後ろの ゃゅょ の所（line の位置）。
    日本語の綴りに無い並びなので、隣のイ段のキーが在るかに関わらず打ち違いの印として扱う。"""
    return [k for k, c in enumerate(line) if c in _SMALL and k > 0 and _hira(line[k - 1])
            and line[k - 1] not in _I_ROW]


def repair_line(line, result, decided=(), input_method='kana'):
    if input_method != 'kana' or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done == line:
        return result
    ks = spots(line)
    if not ks:
        return result
    ops = [o for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes() if o[0] != 'equal']
    new = done
    undo, odd_add = [], []
    for tag, i1, i2, j1, j2 in sorted(ops, key=lambda o: o[3], reverse=True):
        hit = [k for k in ks if i1 <= k < i2 or i1 <= k - 1 < i2 or (i1 == i2 and k - 1 <= i1 <= k + 1)]
        if not hit:
            continue
        if any(x < max(i2, i1 + 1) and i1 < y for x, y in (decided or ())):
            continue
        rd = _reading(done[max(0, j1 - 1):j2 + 1])
        if all(any(rd[x] in _I_ROW and rd[x + 1] == line[k] for x in range(len(rd) - 1)) for k in hit):
            continue
        new = new[:j1] + line[i1:i2] + new[j2:]
        undo.append(done[j1:j2])
        a, b = min(hit) - 1, max(hit) + 1
        odd_add.append((min(a, i1), max(b, i2)))
    if new == done:
        return result
    out = dict(result)
    ops2 = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out.update({'corrected': new, 'changed': new != line,
                'details': [d for d in (result.get('details') or []) if not (len(d) > 1 and d[1] in undo)],
                'spans': [[o[3], o[4]] for o in ops2], 'original_spans': [[o[1], o[2]] for o in ops2]})
    out['odd_spans'] = sorted(set(tuple(x[:2]) for x in (result.get('odd_spans') or ())) | set(odd_add))
    out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [
        (a, b, '小さい ゃゅょ が付けられない字の後ろにあります。前の字の打ち違いかもしれないので、直し先を決めていません')
        for a, b in odd_add]
    return out
