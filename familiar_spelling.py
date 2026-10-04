# -*- coding: utf-8 -*-
"""Ordinary kana spellings of the same native action, after correction.

These are reading-level style judgments, not typo/answer pairs. An explicit
user choice still takes precedence. Native forms prove the same inflection.
"""
from functools import lru_cache

# Everyday note-writing defaults; the rare written forms remain valid words.
KANA_ACTION_READINGS=frozenset(('まとめる','ためらう','うなずく'))


@lru_cache(maxsize=1024)
def prefers_kana(face,reading,before="",following=""):
    from morphology import dictionary_inflections,native_spelling_only
    if not face or not any('一'<=c<='鿿' for c in face):return False
    # User's default for these independent/dependent nominal readings.
    # A compound containing the same kana is not a standalone nominal.
    if reading in ('もの','こと'):
        return not (reading=='もの' and face=='者'
                    and person_reference(before,following))
    for pos,form,base,rd in dictionary_inflections(face) or ():
        if not pos.startswith('動詞,自立,') or rd!=reading:continue
        for base_reading in KANA_ACTION_READINGS:
            if not native_spelling_only(base_reading,base):continue
            if any(p.startswith('動詞,自立,') and f==form and r==reading
                   and native_spelling_only(base_reading,b)
                   for p,f,b,r in dictionary_inflections(reading) or ()):
                return True
    return False


@lru_cache(maxsize=1024)
def person_reference(before,following):
    """Positive person meaning in the same explicit case or copular slot."""
    from morphology import tokenize
    from semantic_roles import nominal_roles,_subject_predicate_roles,candidate_object_evidence
    parts=tokenize(following)
    if not parts or parts[0].pos!='助詞':return False
    case=parts[0]
    tail=following[case.end:]
    if case.surface in ('が','は'):
        # An explicit nominal identity is stronger than an inferred actor.
        for token in parts[1:]:
            if token.pos=='助動詞' and token.base_form in ('だ','です'):
                return nominal_roles(following[case.end:token.start])==frozenset(('person',))
            if token.pos not in ('名詞','接頭詞'):break
        if case.surface=='が':
            head,roles=_subject_predicate_roles(tail,'')
            return bool(head and roles==frozenset(('person',)))
    if case.surface=='を':
        proof=candidate_object_evidence('人',following,before)
        return bool(proof and set(proof.get('predicate_roles',()))=={'person'})
    return False
