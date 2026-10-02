# -*- coding: utf-8 -*-
"""Explicitly rare nouns compete with familiar senses fitting the same action."""
from functools import lru_cache

@lru_cache(maxsize=1)
def families():
    from public_nominal_cache import load
    cached=load()
    if cached is not None:return cached['families']
    import kango_tier as K
    from morphology import dictionary_inflections
    from reading_segments import _native_nominal_reading_faces
    K._load();out={}
    for word,tier in K._USAGE.items():
        if tier!=3:continue
        for pos,form,base,rd in dictionary_inflections(word) or ():
            if base!=word or not pos.startswith(('名詞,一般,','名詞,サ変接続,')):continue
            ordinary=tuple(face for face in _native_nominal_reading_faces(rd)
                           if K.known_usage_tier(face) in (1,2))
            if ordinary:
                group=out.setdefault(rd,{'restricted':set(),'ordinary':set()})
                group['restricted'].add(word);group['ordinary'].update(ordinary)
    return {rd:{k:tuple(sorted(v)) for k,v in group.items()} for rd,group in out.items()}

def roles(frame,face):
    family=families().get(frame['reading'],{})
    if face in frame['ordinary_faces']:return frozenset(('ordinary_spelling',))
    if face in family.get('restricted',()) or frame.get('proper_default') and face==frame['surface']:
        return frozenset(('restricted_spelling',))
    return frozenset()

def frames(source):
    groups=families()
    from morphology import tokenize
    from contextual_repair import _source_clause_bounds
    from semantic_roles import candidate_nominal_spelling_evidence,object_before,candidate_evidence
    from literal_examples import protected_ranges,overlaps
    from last_choice import surface_for_reading
    parts=tokenize(source)
    out=list(_proper_name_frames(source,parts));protected=None
    legacy=[(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,t.has_reading,t.infl_form) for t in parts]
    for part in parts:
        if part.pos!='名詞' or not part.has_reading:continue
        group=groups.get(part.reading)
        if not group or part.surface not in group['restricted']+group['ordinary']:continue
        if surface_for_reading(part.reading)==part.surface:continue
        lo,hi=_source_clause_bounds(source,part.start,part.end)
        before=source[lo:part.start];following=source[part.end:hi]
        ordinary=[];activity_fits=False
        obj=object_before(source,part.start,lambda _:legacy) if part.pos_sub=='サ変接続' else None
        original_action=(candidate_evidence(obj,part.surface,following,before) if obj else None)
        if (part.surface in group['restricted'] and original_action
            and original_action['shared_roles']):continue
        for face in group['ordinary']:
            evidence=candidate_nominal_spelling_evidence(before,face,following)
            # Merely doing/ending an activity does not distinguish a rare
            # native action noun from another activity with the same reading.
            if (evidence and part.pos_sub=='サ変接続'
                and set(evidence['predicate_roles']) & {'event','process'}):
                activity_fits=True
            if evidence and set(evidence['shared_roles'])-{'event','process','attribute'}:
                ordinary.append(face)
            if obj:
                action=candidate_evidence(obj,face,following,before)
                if action and action['shared_roles']:ordinary.append(face)
        # A native action noun fits an action-taking predicate directly.
        # That concrete sense can select the less common spelling.
        if activity_fits or not ordinary:continue
        if protected is None:protected=protected_ranges(source)
        if overlaps(part.start,part.end,protected):continue
        out.append(dict(kind='familiar_nominal',start=part.start,end=part.end,
            surface=part.surface,reading=part.reading,ordinary_faces=tuple(dict.fromkeys(ordinary)),
            evidence_start=lo,evidence_end=hi,expected_role='ordinary_spelling',
            reason='明示的に稀な語より、同じ読みで後続の動作の対象に合う一般的な語義を選びます'))
    return tuple(out)


def conditional_reference_frames(source):
    """Prefer an ordinary situational reference over a rare bare nominal.

    Copular conditions followed by a degree comparison establish a manner
    reference. Native noun ownership/modification, quotations and an explicit
    spelling choice can instead establish the less common nominal sense.
    """
    from morphology import tokenize,dictionary_inflections
    from kango_tier import is_restricted
    from literal_examples import protected_ranges,overlaps
    from last_choice import surface_for_reading
    from contextual_repair import _source_clause_bounds
    parts=tokenize(source);out=[];protected=None
    for i,t in enumerate(parts):
        if not (t.pos=='名詞' and t.pos_sub=='一般' and t.has_reading
            and is_restricted(t.surface) and t.reading in ('こう','そう','ああ')):continue
        if not any(pos.startswith('副詞,助詞類接続,') and rd==t.reading
            for pos,form,base,rd in dictionary_inflections(t.reading) or ()):continue
        previous=parts[i-1] if i else None
        if previous and previous.end==t.start and (previous.pos in ('名詞','連体詞','接頭詞')
            or previous.pos=='助詞' and previous.pos_sub=='連体化'
            or previous.pos=='助動詞' and previous.infl_form=='体言接続'):continue
        after=parts[i+1:]
        if not after or after[0].start!=t.end:continue
        copula=after[0]
        if not (copula.has_reading and copula.pos=='助動詞' and copula.base_form=='だ'):continue
        cut=1
        if copula.infl_form!='仮定形':
            if not (len(after)>=2 and copula.infl_form=='連用タ接続'
                and after[1].has_reading and after[1].pos=='助動詞'
                and after[1].base_form=='た' and after[1].infl_form=='仮定形'
                and after[1].start==copula.end):continue
            cut=2
        if len(after)<=cut:continue
        degree=after[cut]
        if not (degree.start==after[cut-1].end and degree.has_reading
            and degree.pos=='副詞' and degree.surface in ('もっと','さらに','より','一層')):continue
        lo,hi=_source_clause_bounds(source,t.start,degree.end)
        if degree.end>hi:continue
        tail=source[t.end:degree.end]
        if (surface_for_reading(t.reading)==t.surface
            or surface_for_reading(t.reading+tail)==t.surface+tail):continue
        if protected is None:protected=protected_ranges(source)
        if overlaps(t.start,degree.end,protected):continue
        out.append(dict(start=t.start,end=t.end,reading=t.reading,candidates=(t.reading,),
            evidence_end=degree.end,reason='所有や修飾で指定されない稀な名詞より、条件と程度比較をつなぐ一般的な状況指示を選びます'))
    return tuple(out)


def _ordinary_nominal_modifier_fits(parts,index,lo,face):
    """A modifier can establish the common noun through its actual の relation."""
    part=parts[index];previous=parts[index-1] if index else None
    if not (previous and previous.end==part.start and previous.start>=lo):return True
    if previous.pos=='助詞' and previous.pos_sub=='連体化':
        if index<2:return False
        left=parts[index-2]
        if not (left.end==previous.start and left.start>=lo
                and left.has_reading and left.pos=='名詞'):return False
        from semantic_roles import genitive_nominal_support
        return genitive_nominal_support(left.surface,face)
    return previous.pos not in ('名詞','連体詞','接頭詞')


def _proper_name_frames(source,parts=None):
    """Compare an unsupported bare name with an ordinary same-reading argument.

    Native proper-name POS is not a reason to stop. A positively classified
    common sense fitting the actual case and predicate wins by default;
    a name's own established relation, modifier, explicit choice or quotation
    supplies the contrary evidence. No misspelling/answer pair is stored.
    """
    from morphology import tokenize,dictionary_inflections
    from reading_segments import _native_nominal_reading_faces
    from semantic_roles import candidate_nominal_spelling_evidence,CASE_VERB_ROLES
    cases=('を',)+tuple(CASE_VERB_ROLES)
    if not any(case in source for case in cases):return ()
    from contextual_repair import _source_clause_bounds
    from literal_examples import protected_ranges,overlaps
    from last_choice import active,surface_for_reading
    from kango_tier import known_usage_tier
    if parts is None:parts=tokenize(source)
    out=[];protected=None;choices=active()
    for i,part in enumerate(parts):
        if (part.pos!='名詞' or not part.pos_sub.startswith('固有名詞') or not part.has_reading
                or not any('一'<=c<='鿿' for c in part.surface)
                or known_usage_tier(part.surface) in (1,2)):
            continue
        if any(pos.startswith(('名詞,一般,','名詞,サ変接続,')) and rd==part.reading
               for pos,form,base,rd in dictionary_inflections(part.surface) or ()):continue
        if surface_for_reading(part.reading)==part.surface:continue
        lo,hi=_source_clause_bounds(source,part.start,part.end)
        before=source[lo:part.start];following=source[part.end:hi]
        if not following.startswith(cases):continue
        original=candidate_nominal_spelling_evidence(before,part.surface,following)
        if original and original['shared_roles']:continue
        ordinary=[]
        for face in _native_nominal_reading_faces(part.reading):
            if face==part.surface:continue
            if not _ordinary_nominal_modifier_fits(parts,i,lo,face):continue
            evidence=candidate_nominal_spelling_evidence(before,face,following)
            if evidence and evidence['shared_roles']:ordinary.append(face)
        if not ordinary:continue
        if choices is not None and any(choices.lookup(face)==part.surface for face in ordinary):continue
        if protected is None:protected=protected_ranges(source)
        if overlaps(part.start,hi,protected):continue
        out.append(dict(kind='familiar_nominal',proper_default=True,
            start=part.start,end=part.end,surface=part.surface,reading=part.reading,
            ordinary_faces=tuple(ordinary),evidence_start=lo,evidence_end=hi,
            expected_role='ordinary_spelling',
            reason='人名・地名としての根拠がない名詞を、同じ読みで動作に合う一般語と比較します'))
    return tuple(out)


def proper_replacement_fits(frame,changed,start,end,surface):
    """Recheck the same nominal/case relation after the common replacement."""
    from contextual_repair import _source_clause_bounds
    from semantic_roles import candidate_nominal_spelling_evidence
    from morphology import dictionary_inflections
    if surface not in frame['ordinary_faces']:return False
    if not any(pos.startswith('名詞,') and '固有名詞' not in pos and rd==frame['reading']
               for pos,form,base,rd in dictionary_inflections(surface) or ()):return False
    lo,hi=_source_clause_bounds(changed,start,end)
    from morphology import tokenize
    parts=tokenize(changed)
    index=next((i for i,t in enumerate(parts) if t.start==start and t.end==end),None)
    if index is None or not _ordinary_nominal_modifier_fits(parts,index,lo,surface):return False
    evidence=candidate_nominal_spelling_evidence(changed[lo:start],surface,changed[end:hi])
    return bool(evidence and evidence['shared_roles'])
