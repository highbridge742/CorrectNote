# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""1回の確定の打鍵を、文節ごとに分ける（2026-11-06 補正の担当「文節ごとに分けて入れる」）。

IME は1回の確定を文節（春が／来た）に分けて知らせ、打鍵の記録（stroke_keys）は1回の確定ぶんまとめて取れる。
これまでは文節が2つ以上あると、どの打鍵がどの文節か分からないので、打鍵なしで渡していた。
ぴったり合う時だけ分ける（合わなければ None を返し、呼び手は今までどおり打鍵なしで渡す）:
  かな入力  キー1つがかな1字（シフトの間は小書き）、゛゜のキーは前の字に付く。打鍵から組んだかなが文節の読みを
           つないだものと同じ時だけ、文節の読みの字数で切る。
  ローマ字  打った字の並びをかなに戻し（halfwidth.romaji_to_kana）、文節の切れ目でちょうど読みに一致する切り方が
           ただ1つの時だけ切る。, . - のキーは 、 。 ー に1字ずつ読み替える（2026-11-06 補正の担当）。
打鍵の途中に字でないキー（BackSpace・矢印など）があれば分けない（変換の空白・確定の Enter は後ろに付くだけなので、
最後の文節に付ける）。配列が既定（JIS かな・QWERTY）でない時も分けない。"""
import unicodedata

# JIS かな配列: stroke_keys.key_of_keycode の字 → かな（シフトなし／あり）
_PLAIN = dict(zip('1234567890-^¥', 'ぬふあうえおやゆよわほへー'))
_PLAIN.update(zip('qwertyuiop@[', 'たていすかんなにらせ゛゜'))
_PLAIN.update(zip('asdfghjkl;:]', 'ちとしはきくまのりれけむ'))
_PLAIN.update(zip('zxcvbnm,./\\', 'つさそひこみもねるめろ'))
_SHIFTED = dict(zip('34567890ze', 'ぁぅぇぉゃゅょをっぃ'))
_SHIFTED.update({',': '、', '.': '。', '/': '・', '[': '「', ']': '」', '¥': 'ー'})


def _hira(text):
    try:
        from ime_readings import reading_to_hiragana
        return reading_to_hiragana(text)
    except Exception:
        return text


def _body(strokes):
    """字のキーの並び（番号つき）と、後ろに付く字でないキー。途中に字でないキーがあれば None。"""
    keys = list(strokes)
    lead = 0
    while lead < len(keys) and not keys[lead][0]:
        lead += 1
    end = len(keys)
    while end > lead and not keys[end - 1][0]:
        end -= 1
    body = keys[lead:end]
    if not body or any(not k for k, _ms in body):
        return None
    return lead, end


def _shifted(ms, shifts):
    return any(down <= ms <= up for down, up in shifts or ())


def _kana_units(strokes, shifts, lead, end):
    """[(かな1字, その字の打鍵の番号の並び)]。組めないキーがあれば None。"""
    units = []
    for i in range(lead, end):
        key, ms = strokes[i]
        ch = (_SHIFTED if _shifted(ms, shifts) else _PLAIN).get(key)
        if ch is None:
            return None
        if ch in '゛゜':
            if not units:
                return None
            joined = unicodedata.normalize('NFC', units[-1][0] + ('゙' if ch == '゛' else '゚'))
            if len(joined) != 1:
                return None
            units[-1] = (joined, units[-1][1] + [i])
        else:
            units.append((ch, [i]))
    return units


def _pack(strokes, shifts, index_groups, lead, end):
    out = []
    for n, group in enumerate(index_groups):
        idx = list(group)
        if n == 0:
            idx = list(range(0, lead)) + idx
        if n == len(index_groups) - 1:
            idx = idx + list(range(end, len(strokes)))
        keys = tuple(strokes[i] for i in idx)
        times = [ms for _k, ms in keys]
        lo, hi = (min(times), max(times)) if times else (0, -1)
        out.append((keys, tuple(s for s in (shifts or ()) if s[0] <= hi and s[1] >= lo)))
    return out


def split_kana(strokes, shifts, readings):
    span = _body(strokes)
    if span is None:
        return None
    lead, end = span
    units = _kana_units(strokes, shifts, lead, end)
    want = [_hira(r) for r in readings]
    if units is None or ''.join(u for u, _i in units) != ''.join(want):
        return None
    groups, at = [], 0
    for r in want:
        groups.append([i for _u, idx in units[at:at + len(r)] for i in idx])
        at += len(r)
    if any(not g for g in groups):
        return None
    return _pack(strokes, shifts, groups, lead, end)


_ROMAJI_MARKS = {',': '、', '.': '。', '-': 'ー'}


def split_romaji(strokes, shifts, readings):
    span = _body(strokes)
    if span is None:
        return None
    lead, end = span
    letters = ''.join(k for k, _ms in strokes[lead:end])
    if not all((c.isascii() and c.isalpha()) or c in _ROMAJI_MARKS for c in letters):
        return None
    # キー1つが1字のまま（切れ目の番号がキーの番号と同じ）
    letters = ''.join(_ROMAJI_MARKS.get(c, c) for c in letters)
    from halfwidth import romaji_to_kana
    want = [_hira(r) for r in readings]
    if romaji_to_kana(letters)[0] != ''.join(want):
        return None
    cuts, start, done = [], 0, ''
    for n, r in enumerate(want[:-1]):
        done += r
        found = [j for j in range(start + 1, len(letters)) if romaji_to_kana(letters[:j])[0] == done
                 and romaji_to_kana(letters[j:])[0] == ''.join(want[n + 1:])]
        if len(found) != 1:
            return None          # 切れ目が決まらない（ん の n・っ の重ね など）
        cuts.append(found[0]); start = found[0]
    bounds = [0] + cuts + [len(letters)]
    groups = [list(range(lead + bounds[k], lead + bounds[k + 1])) for k in range(len(want))]
    if any(not g for g in groups):
        return None
    return _pack(strokes, shifts, groups, lead, end)


def split(strokes, shifts, readings, input_method, spec=None):
    """[(strokes, shifts)] を文節ごとに。分けられなければ None。"""
    if not readings or not strokes:
        return None
    if spec is not None:
        try:
            layout, _shape, _custom, kana = (tuple(spec) + (None,) * 4)[:4]
            if layout not in (None, '', 'qwerty_jis') or (input_method == 'kana' and kana not in (None, '', 'jis')):
                return None
        except Exception:
            return None
    try:
        if input_method == 'kana':
            return split_kana(strokes, shifts, readings)
        if input_method == 'romaji':
            return split_romaji(strokes, shifts, readings)
    except Exception:
        return None
    return None
