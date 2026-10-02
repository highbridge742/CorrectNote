# -*- coding: utf-8 -*-
"""One physically justified intrusion plus one missing key in a relative verb."""
from functools import lru_cache


def _frames(source):
    import morphology as M
    from semantic_roles import nominal_roles
    from reading_segments import native_common_noun_faces
    from literal_examples import protected_ranges, overlaps
    fields = []
    lo = 0
    protected = None
    for hi, end in [(m.start(), m.end()) for m in M.COLUMN_SEPARATOR.finditer(source)] + [(len(source), len(source))]:
        field = source[lo:hi]
        original = M.tokenize(field)
        if not original or original[0].pos != '助詞' or not original[0].pos_sub.startswith('格助詞'):
            lo = end
            continue
        for cut in range(1, len(field)):
            tail = field[cut:]
            heads = (tail,) if 'method' in nominal_roles(tail) else (
                tuple(face for face in native_common_noun_faces(tail)
                      if 'method' in nominal_roles(face))
                if all('ぁ' <= ch <= 'ゖ' or ch == 'ー' for ch in tail) else ())
            if not heads:
                continue
            tokens = M.tokenize(field[:cut])
            if (len(tokens) != 2 or tokens[0].pos != '助詞'
                    or not tokens[0].pos_sub.startswith('格助詞')
                    or tokens[1].pos != '動詞' or tokens[1].infl_form != '基本形'):
                continue
            if not all(t.has_reading for t in tokens):
                continue
            if protected is None:
                protected = protected_ranges(source)
            if overlaps(lo, hi, protected):
                continue
            fields.append(dict(start=lo, end=lo+cut, tail=tail, heads=heads,
                               reading=''.join(t.reading for t in tokens)))
        lo = end
    return tuple(fields)


@lru_cache(maxsize=2048)
def _finite_faces(reading, heads):
    import morphology as M
    from reading_segments import native_lexical_reading_faces
    from semantic_roles import candidate_evidence
    found = []
    for face in native_lexical_reading_faces(reading):
        parts = M.tokenize(face)
        if len(parts) != 1 or parts[0].pos != '動詞' or parts[0].infl_form != '基本形':
            continue
        if any((candidate_evidence(head, face, '') or {}).get('shared_roles') for head in heads):
            found.append(face)
    return tuple(found)


def options(target, reading, before, after):
    import contextual_repair as C
    import kana_layout as K
    match = next((f for f in frames(target.source)
                  if (f['start'], f['end']) == (target.start, target.end)), None)
    if not match or reading.text != match['reading']:
        return
    missing = tuple(k for k in K.KANA_POSITIONS if k not in K._SHIFT_KANA and k not in '゛゜')
    seen = set()
    for first in C.key_repairs(reading.text, before, after):
        if first.operation != 'adjacent_intrusion' or not C._original_intrusion_allowed(reading.text, first, before, after):
            continue
        keys = tuple(k for ch in first.reading for k in K.keystrokes(ch))
        def variants():
            yield first.reading, first
            for pos in range(len(keys)+1):
                for key in missing:
                    if not C._search_step('relative_key_proposals', 512):
                        return
                    rd = C._render(keys[:pos]+(key,)+keys[pos:])
                    if not C._is_reading(rd):
                        continue
                    original_pos = pos + (pos >= first.position)
                    second = C.KeyRepair(rd, 'omission', original_pos, '', key, K.MISSING_KEY_COST)
                    yield rd, C.ClauseKeyRepair(rd, 'intrusion_and_omission', first.position,
                        first.pressed, key, first.cost+second.cost, (first, second))
        for rd, repair in variants():
            for face in _finite_faces(rd, tuple(match['heads'])):
                if (rd, face) in seen:
                    continue
                seen.add((rd, face))
                yield reading, repair, ('ime_clause', (face,))


def supports_replacement(target, surface):
    import morphology as M
    from semantic_roles import candidate_evidence
    match = next((f for f in frames(target.source)
                  if (f['start'], f['end']) == (target.start, target.end)), None)
    parts = M.tokenize(surface)
    return bool(match and len(parts) == 1 and parts[0].pos == '動詞'
                and parts[0].infl_form == '基本形'
                and any((candidate_evidence(head, surface, '') or {}).get('shared_roles')
                        for head in match['heads']))


def frames(source):
    from ime_inverse_gate import _CORRECTION_CACHE
    cache=_CORRECTION_CACHE.get();key=('relative_orphan_case',source)
    if cache is not None and key in cache:return cache[key]
    result=_frames(source)
    if cache is not None:cache[key]=result
    return result
