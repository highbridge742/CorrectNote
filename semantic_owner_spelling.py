# -*- coding: utf-8 -*-
"""Use native readings of semantic owners through the existing noun relationships."""
from functools import lru_cache


@lru_cache(maxsize=3)
def _owner_readings(case):
    from semantic_roles import QUALITY_ASSESSMENTS,NOUN_GROUPS
    from morphology import dictionary_inflections,native_spelling_only
    if case=='の':
        words=QUALITY_ASSESSMENTS | frozenset(NOUN_GROUPS['rotating_control'])
    elif case=='に':
        words=frozenset().union(*(NOUN_GROUPS[name] for name in ('place','object','container','writing_surface','support_surface','employer','effort_goal')))
    else:
        from measurement_meaning import OBJECTS
        words=frozenset().union(*(NOUN_GROUPS[name] for name in ('text','sound','photographic_media',*OBJECTS)))
    out={}
    for word in sorted(words):
        for pos,form,base,reading in dictionary_inflections(word) or ():
            if pos.startswith('名詞,') and base==word and native_spelling_only(reading,word):
                out.setdefault(reading,set()).add(word)
        # Derived nominal names can span native adjective/suffix or noun/suffix tokens.
        from morphology import tokenize
        parts=tokenize(word)
        if parts and parts[-1].pos=='名詞' and all(t.has_reading for t in parts):
            reading=''.join(t.reading for t in parts)
            if native_spelling_only(reading,word):out.setdefault(reading,set()).add(word)
    return {rd:tuple(sorted(faces)) for rd,faces in out.items()}


def _owners(reading,case):
    from reading_segments import native_counted_nominal_evidence
    out=list(_owner_readings(case).get(reading,()))
    if case!='の':return tuple(out)
    proof=native_counted_nominal_evidence(reading)
    units={unit for unit,ordinal in proof or () if not ordinal}
    if units and units<={'台','枚'}:
        from ime_candidates import SearchCandidates
        from morphology import native_spelling_only
        with SearchCandidates() as search:
            faces=search.candidates(reading) if search.available else ()
        out.extend(face for face in faces if face!=reading
                   and native_counted_nominal_evidence(face)==proof
                   and native_spelling_only(reading,face))
    return tuple(dict.fromkeys(out))



def _owner_boundary(source,start,case,owner):
    """An owner is a whole source nominal, never a suffix of an unknown run."""
    from morphology import tokenize
    from reading_segments import native_predicate_link_boundaries,native_surface_nominal_heads
    parts=tokenize(source)
    origins={0}|{p.end for p in parts if p.has_reading and p.pos=='助詞'
        and p.pos_sub.startswith('格助詞') and p.end<=start}
    beginnings=set(origins)
    beginnings.update(edge for origin in origins
        for edge in native_predicate_link_boundaries(source,origin) if edge<=start)
    return any(owner in native_surface_nominal_heads(source[begin:case])
        for begin in beginnings if begin<=start)


def frames(source):
    if not any(c in source for c in ('の','を','に')):return ()
    from morphology import tokenize
    from literal_examples import protected_ranges,overlaps
    import context_meaning as K
    out=[];parts=tokenize(source);protected=None
    for case in (i for i,c in enumerate(source) if c in ('の','を','に')):
        link=source[case]
        left=case
        while left and case-left<18 and ('ぁ'<=source[left-1]<='ゖ' or source[left-1]=='ー'):
            left-=1
        for start in sorted({left}|{t.start for t in parts if left<=t.start<case}):
            raw=source[start:case]
            if not raw:continue
            from semantic_roles import candidate_origin_return_evidence
            source_origin=candidate_origin_return_evidence(raw,source[case:])
            for owner in _owners(raw,link):
                if not _owner_boundary(source,start,case,owner):continue
                if source_origin and not candidate_origin_return_evidence(owner,source[case:]):
                    continue
                projected=source[:start]+owner+source[case:]
                delta=len(owner)-len(raw);core_start=start+len(owner)+1
                # The original native owner reading supplies meaning; the
                # projected spelling only lets the existing relationship read it.
                for core in K._contexts(projected,owner_spelling=False):
                    if (core['evidence_start']!=start or core['start']!=core_start
                        or core.get('owner_spelling')):
                        continue
                    if not K.candidates(core):continue
                    end=core['end']-delta;evidence_end=core['evidence_end']-delta
                    if protected is None:protected=protected_ranges(source)
                    if overlaps(start,max(end,evidence_end),protected):continue
                    out.append(dict(core,start=start,end=end,surface=source[start:end],
                        reading=raw+link+core['reading'],evidence_end=evidence_end,
                        reading_spelling=True,owner_spelling=dict(prefix=owner+link,core=core),
                        reason='元のかなの名詞と、後続の名詞・動作との意味関係を同じ表記へまとめています'))
    return tuple(out)


def placement_continuation(source,start,finish,verbs):
    """Read an explicit destination and the same native following action."""
    from morphology import tokenize,dictionary_inflections,native_spelling_only
    from semantic_roles import NOUN_GROUPS
    words=frozenset().union(*(NOUN_GROUPS[name] for name in ('place','object','container','writing_surface','support_surface')))
    for case in range(start,min(finish,len(source))):
        if source[case] not in ('に','へ'):continue
        before=source[start:case]
        if any(c in before for c in 'を。！？!?\t\r\n⇒→'):continue
        boundaries={0}|{t.start for t in tokenize(before)}
        nouns=set();noun_starts=[]
        for edge in boundaries:
            face=before[edge:]
            if face in words and _owner_boundary(source,start+edge,case,face):nouns.add(face);noun_starts.append(start+edge)
            if face and all('ぁ'<=c<='ゖ' or c=='ー' for c in face):
                known=tuple(owner for owner in _owner_readings('に').get(face,())
                    if _owner_boundary(source,start+edge,case,owner))
                if known:nouns.update(known);noun_starts.append(start+edge)
        if not nouns:continue
        tail=tokenize(source[case+1:finish])
        if not tail or tail[0].pos!='動詞' or not tail[0].has_reading:continue
        verb=tail[0]
        actual=any(pos.startswith('動詞,') and form==verb.infl_form and base in verbs
                   and rd==verb.reading for pos,form,base,rd in dictionary_inflections(verb.surface) or ())
        if not actual and all('ぁ'<=c<='ゖ' for c in verb.surface):
            from semantic_roles import _native_lexeme_forms
            actual=any(native_spelling_only(verb.surface,face) for word in verbs
                       for face in _native_lexeme_forms(word,verb.infl_form,verb.reading))
        if not actual:continue
        return dict(start=min(noun_starts),case=case,end=case+1+verb.end,nouns=tuple(sorted(nouns)),
                    digital=bool(nouns & set(NOUN_GROUPS.get('digital_destination',()))))
    return None
