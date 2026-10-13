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


def _is_decimal_point(text, index):
    """A period between decimal digits belongs to the number, not a stop."""
    return (text[index] in '.．' and index > 0 and index + 1 < len(text)
            and text[index - 1].isdecimal()
            and text[index + 1].isdecimal())


# Forms of ある・おく that the tokenizer tags as independent verbs after て.
_HELPER_VERBS = frozenset(('ある', 'あっ', 'あり', 'あれ', 'あろ',
                           'おく', 'おい', 'おき', 'おけ', 'おこ'))


def text_boundaries(text, tokens=()):
    """The single source of the actual Ctrl-left/right stops."""
    boundaries = {0, len(text)}
    tokens = tuple(tokens)
    particle_starts = {token[3] for token in tokens
                       if token[1].split(':')[0] == '助詞'}
    # て/で followed by a helping verb (している・食べてみる・書いてある) is one
    # predicate; Ctrl-left/right passes through it.
    helper_starts = {token[3] for token in tokens
                     if token[1].startswith('動詞:非自立')
                     or token[1].startswith('動詞') and token[0] in _HELPER_VERBS}
    for token in tokens:
        if token[1].split(':')[0] in ('接続詞', '助詞'):
            end = token[4]
            # Particles in a row (にも・では・からは) stop once, after the last.
            if end in particle_starts:
                continue
            if (token[0] in ('て', 'で') and token[1].startswith('助詞:接続助詞')
                    and end in helper_starts):
                continue
            # Keep following punctuation with the word; its run ends below.
            if end == len(text) or text[end] not in _AFTER_PUNCTUATION:
                boundaries.add(end)
    for i, char in enumerate(text):
        if char in _AFTER_PUNCTUATION and not _is_decimal_point(text, i) and (
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
    return tuple(sorted(boundaries))


def text_edge(text, column, direction, tokens=()):
    """Return the next strict boundary within one logical line."""
    column = max(0, min(column, len(text)))
    boundaries = text_boundaries(text, tokens)
    if direction > 0:
        return min((i for i in boundaries if i > column), default=len(text))
    return max((i for i in boundaries if i < column), default=0)


def boundary_spans(text, tokens=()):
    """Color the POS unit before each stop, including its trailing symbols.

    Empty brackets never borrow a word from outside. A whitespace-only row
    supplies no colored unit. Native compound function words remain whole.
    """
    import unicodedata
    tokens = tuple(tokens)
    # Each character and token is visited once. Long symbol/closing-bracket
    # runs must not walk back through the same prefix at every stop.
    lexical_end = [0]
    for i,char in enumerate(text):
        if char in _BRACKETS:
            lexical_end.append(0)
        elif char.isspace() or unicodedata.category(char)[0] in ('P', 'S'):
            lexical_end.append(lexical_end[-1])
        else:
            lexical_end.append(i+1)
    owning = {}
    for part in tokens:
        if part[1].split(':')[0] != '記号':
            for end in range(max(0,part[3])+1,min(len(text),part[4])+1):
                owning[end] = part
    spans = {}
    for stop in text_boundaries(text, tokens):
        part = owning.get(lexical_end[stop])
        if part is not None and part[4] <= stop:
            spans[part[3]] = max(stop, spans.get(part[3], 0))
    return tuple(sorted(spans.items()))


def plans(texts, tokenize):
    """Compute presentation-only navigation spans without importing Tk."""
    from literal_lines import literal_only
    from analysis_context import check_current_request
    out={}
    for text in dict.fromkeys(texts):
        check_current_request()
        if literal_only(text):continue
        parts=tokenize(text)
        from pos_font import spans as pos_font_spans
        # Legacy POS-wide highlight spans are not needed for the short boundary
        # marker. Keep the tuple slot for existing worker/cache consumers.
        out[text]=(text_boundaries(text,parts),(),
                   pos_font_spans(text,parts))
    check_current_request()
    return out
