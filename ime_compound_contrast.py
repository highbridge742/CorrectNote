# -*- coding: utf-8 -*-
"""Compare a suffix-only unknown compound with a lexical action noun."""


def _field_frames(source):
    import morphology as M
    from ime_language import JapaneseIME
    parts = M.tokenize(source)
    spans = []
    for lead, left, right in zip(parts, parts[1:], parts[2:]):
        if ((lead.pos == '動詞' and lead.infl_form == '連用形'
                or lead.pos == '名詞' and any(
                    pos.startswith('動詞,') and form == '連用形' and reading == lead.reading
                    for pos, form, base, reading in M.dictionary_inflections(lead.surface) or ()))
                and left.pos == right.pos == '名詞'
                and right.pos_sub.startswith('接尾')
                and all(t.has_reading and len(t.surface) == 1
                        and '一' <= t.surface <= '鿿' for t in (left, right))
                and lead.end == left.start and left.end == right.start
                and not M.dictionary_inflections(source[left.start:right.end])):
            spans.append((left.start, right.end))
    if not spans:
        return ()
    out = []
    with JapaneseIME() as ime:
        if not ime.available:
            return ()
        back = ime.reverse_words(source)
        if not back:
            return ()
        # The source anomaly does not depend on a successful forward proposal.
        for a, b in spans:
            units = [u for u in back[1] if a <= u[0] and u[1] <= b]
            if (not units or units[0][0] != a or units[-1][1] != b
                    or any(u[4] not in (800, 801, 802, 803) for u in units)
                    or any(x[1] != y[0] or x[3] != y[2]
                           for x, y in zip(units, units[1:]))):
                continue
            reading = back[0][units[0][2]:units[-1][3]]
            frame = dict(start=a, end=b, reading=reading, candidates=())
            out.append(frame)
            first = ime.convert_words(back[0])
            if not first or first[0] == source:
                continue
            candidate = first[0]
            inverse = ime.reverse_words(candidate)
            if not inverse or inverse[0] != back[0]:
                continue
            if not candidate.startswith(source[:a]) or not candidate.endswith(source[b:]):
                continue
            z = len(candidate) - len(source[b:])
            face = candidate[a:z]
            if not any(p.startswith('名詞,サ変接続,') and rd == reading
                       for p, f, base, rd in M.dictionary_inflections(face) or ()):
                continue
            if any(u[:4] == (a, z, units[0][2], units[-1][3])
                   and u[4] == 101 for u in first[1]):
                frame['candidates'] = (face,)
    return tuple(out)


def frames(source):
    from morphology import COLUMN_SEPARATOR
    from literal_examples import protected_ranges, overlaps
    from ime_inverse_gate import _CORRECTION_CACHE
    cache = _CORRECTION_CACHE.get()
    key = ('suffix_compound_contrast', source)
    if cache is not None and key in cache:
        return cache[key]
    out = []
    lo = 0
    protected = protected_ranges(source)
    for hi, end in [(m.start(), m.end()) for m in COLUMN_SEPARATOR.finditer(source)] + [(len(source), len(source))]:
        for frame in _field_frames(source[lo:hi]):
            a, b = lo + frame['start'], lo + frame['end']
            if not overlaps(a, b, protected):
                out.append(dict(frame, start=a, end=b))
        lo = end
    result = tuple(out)
    if cache is not None:
        cache[key] = result
    return result
