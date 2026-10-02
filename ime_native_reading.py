# -*- coding: utf-8 -*-
"""Attested native word readings verified against the original IME spelling.

A malformed conversion can hide an okurigana-bearing continuative form or
an alternative word-final reading. Reconstruct one native token at a time,
then require ordinary
first conversion to reproduce the complete original text. This is a source
hypothesis, not observed key history or a table of desired corrections.
"""
from functools import lru_cache


@lru_cache(maxsize=4096)
def _native_alternatives(character):
    from morphology import dictionary_inflections
    from okurigana import NEEDS_OKURIGANA
    readings={rd for pos,form,base,rd in dictionary_inflections(character) or ()}
    readings.update(NEEDS_OKURIGANA.get(character,()))
    # Only actual native continuative entries contribute a hidden one-kana
    # ending. No pronunciation is made by appending kana to a guessed reading.
    for kana in map(chr,range(0x3041,0x3097)):
        for pos,form,base,reading in dictionary_inflections(character+kana) or ():
            if pos.startswith(('動詞,','形容詞,')) and form.startswith('連用'):
                readings.add(reading)
    return tuple(sorted(rd for rd in readings if rd and all('ぁ'<=c<='ゖ' or c=='ー' for c in rd)))


def source_roundtrips(text,parts):
    import contextual_repair as C
    from ime_language import JapaneseIME
    from ime_inverse_gate import _CORRECTION_CACHE
    if not parts or not all(t[5] and C._is_input_reading(t[2]) for t in parts):return ()
    if ''.join(t[0] for t in parts)!=text:return ()
    key=('native_word_source_readings',text,tuple(t[2] for t in parts))
    cache=_CORRECTION_CACHE.get()
    if cache is not None and key in cache:return cache[key]
    variants={}
    for i,token in enumerate(parts):
        surface=token[0]
        if not surface or any(not '一'<=c<='鿿' for c in surface):continue
        if len(surface)==1:
            alternatives=_native_alternatives(surface)
        elif token[1].startswith('名詞'):
            # Reverse IME readings can select only one surname pronunciation.
            # Keep the known word prefix; vary its final character using the
            # existing character readings, then require exact first conversion.
            # This is a verified source hypothesis, never observed keystrokes.
            from kanji_guess import readings_for_char
            tails=readings_for_char(surface[-1])
            alternatives=sorted({token[2][:-len(old)]+new
                for old in tails if len(old)<len(token[2]) and token[2].endswith(old)
                for new in tails if new!=old})
        else:
            continue
        for reading in alternatives:
            if reading==token[2]:continue
            whole=''.join(reading if j==i else p[2] for j,p in enumerate(parts))
            segments=tuple((p[3],p[4],reading if j==i else p[2],
                'native_word_forward' if j==i else 'analyzed_word') for j,p in enumerate(parts))
            variants.setdefault(whole,segments)
    found=[];complete=True
    if variants:
        with JapaneseIME() as ime:
            if ime.available:
                for reading,segments in variants.items():
                    if not C._search_step('native_word_forward_checks',64):
                        complete=False;break
                    if ime.convert(reading)==text:found.append((reading,segments))
    result=tuple(found)
    # A truncated query must report its unfinished search again if requested
    # from another target; never cache it as a completed negative result.
    if cache is not None and complete:cache[key]=result
    return result
