# -*- coding: utf-8 -*-
"""Cursor navigation across logical blocks and text-segment boundaries."""


def block_edge(lines, row, direction):
    """Return a zero-based row; whitespace-only lines separate text blocks.

    Within a filled run, stop at its edge. At its edge or in blank space,
    stop at the next filled line. If none remains, stop at the document edge.
    """
    if not lines:
        return 0
    step = 1 if direction > 0 else -1
    row = max(0, min(row, len(lines) - 1))
    adjacent = row + step
    if not 0 <= adjacent < len(lines):
        return row
    filled = lambda index: bool(lines[index].strip())
    if filled(row) and filled(adjacent):
        while 0 <= adjacent < len(lines) and filled(adjacent):
            row = adjacent
            adjacent += step
        return row
    while 0 <= adjacent < len(lines):
        row = adjacent
        if filled(row):
            return row
        adjacent += step
    return row


_AFTER_PUNCTUATION = frozenset('、。，．,.！？!?…‥')
_BRACKETS = dict(zip('「『（(［[｛{【〔〈《＜<｢', '」』）)］]｝}】〕〉》＞>｣'))
_CLOSING_BRACKETS = frozenset(_BRACKETS.values())


def text_edge(text, column, direction, tokens=()):
    """Return the next strict boundary within one logical line.

    Punctuation runs and closing brackets belong to the preceding segment.
    A contiguous whitespace run has two edges, regardless of its length.
    """
    column = max(0, min(column, len(text)))
    boundaries = {0, len(text)}
    for token in tokens:
        if token[1].split(':')[0] in ('接続詞', '助詞'):
            end = token[4]
            # Keep following punctuation with the word; its run ends below.
            if end == len(text) or text[end] not in _AFTER_PUNCTUATION:
                boundaries.add(end)
    for i, char in enumerate(text):
        if char in _AFTER_PUNCTUATION and (
                i + 1 == len(text) or text[i + 1] not in _AFTER_PUNCTUATION):
            boundaries.add(i + 1)
        if char in _CLOSING_BRACKETS:
            boundaries.add(i + 1)
        if char in _BRACKETS:
            end = i + 1
            while end < len(text) and text[end].isspace():
                end += 1
            if end == len(text) or text[end] != _BRACKETS[char]:
                boundaries.add(i)
        if char.isspace():
            if i == 0 or not text[i - 1].isspace():
                boundaries.add(i)
            if i + 1 == len(text) or not text[i + 1].isspace():
                boundaries.add(i + 1)
    if direction > 0:
        return min((i for i in boundaries if i > column), default=len(text))
    return max((i for i in boundaries if i < column), default=0)
