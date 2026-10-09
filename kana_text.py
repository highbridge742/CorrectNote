# -*- coding: utf-8 -*-
"""Mechanical fullwidth katakana conversion; no normalization or reading inference."""

_HIRAGANA_TRANSLATION = {code: code - 0x60 for code in range(0x30a1, 0x30f7)}


def katakana_to_hiragana(text):
    # Exact str values use the same scalar mapping in the standard library.
    # Other iterables and str subclasses retain the previous iteration/errors.
    if type(text) is str:
        return text.translate(_HIRAGANA_TRANSLATION)
    out = []
    for ch in text:
        if '\u30a1' <= ch <= '\u30f6':
            out.append(chr(ord(ch) - 0x60))
        else:
            out.append(ch)
    return ''.join(out)
