# -*- coding: utf-8 -*-
"""Ordinary kana spellings of the same native action, after correction.

These are reading-level style judgments, not typo/answer pairs. An explicit
user choice still takes precedence. Native forms prove the same inflection.
"""
from functools import lru_cache

# Everyday note-writing defaults; the rare written forms remain valid words.
KANA_ACTION_READINGS=frozenset(('まとめる','ためらう','うなずく'))


@lru_cache(maxsize=1024)
def prefers_kana(face,reading):
    from morphology import dictionary_inflections,native_spelling_only
    if not face or not any('一'<=c<='鿿' for c in face):return False
    for pos,form,base,rd in dictionary_inflections(face) or ():
        if not pos.startswith('動詞,自立,') or rd!=reading:continue
        for base_reading in KANA_ACTION_READINGS:
            if not native_spelling_only(base_reading,base):continue
            if any(p.startswith('動詞,自立,') and f==form and r==reading
                   and native_spelling_only(base_reading,b)
                   for p,f,b,r in dictionary_inflections(reading) or ()):
                return True
    return False
