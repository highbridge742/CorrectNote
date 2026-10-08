# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit selection transformations; these do not infer typo corrections."""
import unicodedata as U


def reading_text(text):
    """Read only kanji-bearing native tokens and preserve all other characters."""
    from morphology import tokenize
    parts = []
    end = 0
    for token in tokenize(text):
        parts.append(text[end:token.start])
        surface = text[token.start:token.end]
        has_kanji = any('\u3400' <= c <= '\u9fff' or c in '々〆' for c in surface)
        parts.append(token.reading if has_kanji and token.has_reading else surface)
        end = token.end
    parts.append(text[end:])
    return ''.join(parts)


def _full_kana(text):
    # Normalize kana width only, leaving mathematical/compatibility symbols intact.
    import re
    return re.sub('[\uff61-\uff9f]+', lambda m: U.normalize('NFKC', m[0]), text)


def _kana_marks(text):
    return ''.join(U.normalize('NFD', c) if 'ぁ' <= c <= 'ヺ' else c for c in text)


def transform_selection(text, kind):
    value = _full_kana(reading_text(text))
    hira = ''.join(chr(ord(c)-0x60) if 'ァ' <= c <= 'ヶ' else c for c in value)
    if kind == 'hiragana':
        return hira
    kata = ''.join(chr(ord(c)+0x60) if 'ぁ' <= c <= 'ゖ' else c for c in hira)
    if kind == 'katakana':
        return kata
    if kind == 'halfwidth':
        table = {U.normalize('NFKC', chr(n)): chr(n) for n in range(0xff61, 0xffa0)}
        table.update({'\u3099': 'ﾞ', '\u309a': 'ﾟ', '　': ' '})
        table.update({chr(n): chr(n-0xfee0) for n in range(0xff01, 0xff5f)})
        return ''.join(table.get(c, c) for c in _kana_marks(kata))
    if kind == 'keys':
        from halfwidth import HALFWIDTH_TO_KANA, SHIFT_TO_KANA
        table = {}
        for key, kana in list(HALFWIDTH_TO_KANA.items()) + list(SHIFT_TO_KANA.items()):
            table.setdefault(kana, key)
        table.update({'\u3099': '@', '\u309a': '[', 'ー': '|', '　': ' '})
        table.update({chr(n): chr(n-0xfee0) for n in range(0xff01, 0xff5f)})
        return ''.join(table.get(c, c) for c in _kana_marks(hira))
    raise ValueError(kind)


def selected_brackets(widget, start, end, pairs):
    """Return one matching pair included in, or immediately outside, a selection."""
    text = widget.get(start, end)
    pairs = tuple(pairs) + (('(', ')'),)
    for opening, closing in pairs:
        if len(text) >= 2 and text.startswith(opening) and text.endswith(closing):
            return start, end, text[1:-1], opening, closing
    if widget.compare(start, '>', '1.0'):
        opening = widget.get(f'{start}-1c', start)
        closing = widget.get(end, f'{end}+1c')
        if (opening, closing) in pairs:
            return f'{start}-1c', f'{end}+1c', text, opening, closing
    return None
