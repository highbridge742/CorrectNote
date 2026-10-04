# -*- coding: utf-8 -*-
"""Choose written forms only after a reading repair is already accepted."""

def retained_frames(source,legacy,retained,selected,engine):
    """Keep a proved lexical frame only while every edit inside survives."""
    from contextual_repair import _legacy_source_changes,_apply,_overlaps
    frames=list(retained)
    for start,end,face in _legacy_source_changes(source,legacy,engine,trim_context=False):
        if any(_overlaps(a,b,start,end) for a,b,_ in selected):continue
        inside=[row for row in frames if _overlaps(row[0],row[1],start,end)]
        if (not inside or any(not start<=a<=b<=end for a,b,_ in inside)
                or _apply(source[start:end],[(a-start,b-start,sf) for a,b,sf in inside])!=face):continue
        frames=[row for row in frames if row not in inside]+[(start,end,face)]
    return [(a,b,face,'') for a,b,face in sorted(frames)]


def _functional_tail(parts,edge):
    from contextual_repair import _sahen_verb_form
    tail=[]
    for token in parts:
        if token.start<edge:continue
        if token.start!=edge or not token.has_reading:break
        if not (token.pos=='助動詞'
                or token.pos=='助詞' and token.pos_sub=='接続助詞'
                or token.pos=='動詞' and (token.pos_sub.startswith('非自立')
                    or _sahen_verb_form(token.pos+','+token.pos_sub.replace(':',','),
                        token.base_form,token.surface,token.infl_form,token.reading))):break
        tail.append(token.surface);edge=token.end
    return ''.join(tail)


def finish(line,result,store,tokenize,dictionary,decisions=None):
    import corrector as engine
    from contextual_repair import _legacy_source_changes,_surfaces,_surface_score_head
    from morphology import dictionary_inflections,tokenize as native_tokens,path_cost
    from kango_tier import known_usage_tier
    from last_choice import surface_for_reading
    from semantic_roles import candidate_nominal_spelling_evidence,nominal_roles
    frames=result.pop('_repair_surfaces',None)
    if (not store or not dictionary or not tokenize or result.get('corrected',line)==line
            or result.get('analysis_status')=='incomplete'):return result
    changes=frames if frames is not None else [(*row,'') for row in _legacy_source_changes(line,result,engine,trim_context=False)]
    from contextual_repair import _apply
    if _apply(line,[row[:3] for row in changes])!=result.get('corrected',line):return result
    approved_parts=list(native_tokens(result['corrected']))
    finished=[];changed=False
    for start,end,reading,kind in changes:
        chosen=reading
        approved_start=start+sum(len(sf)-(b-a) for a,b,sf,_ in changes if b<=start)
        preserve=(kind=='case_leading_intrusion' and line[start+1:end]==reading
            and bool(reading) and all(engine.is_hiragana(c) for c in reading))
        if (not preserve and kind=='ime_scope' and start>0 and line[start-1]=='を'
                and line[start+1:end]==reading and len(reading)>1
                and all(engine.is_hiragana(c) for c in reading)):
            from kana_layout import single_key_drop_adjacency
            if single_key_drop_adjacency(line[start:end],reading) is True:
                preserve=any(t.start==approved_start and t.pos=='動詞'
                    and t.infl_form.startswith('連用')
                    and any(n.start==t.end and n.surface=='て'
                            for n in approved_parts)
                    for t in approved_parts)
        if preserve:
            result.setdefault('_spelling_keep',[]).append(
                (approved_start,approved_start+len(reading)))
        # Keep the grammatical role already proved by the repaired reading:
        # 読んであげる must not acquire the independent action 揚げる.
        from reading_segments import _native_request_tail
        bound=any(t.start==approved_start and t.has_reading and (
                    t.pos_sub.startswith('非自立') or _native_request_tail([
                        (t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),
                         t.reading,t.start,t.end,t.has_reading,t.infl_form)]))
                  for t in approved_parts)
        # An older display range beginning inside a kana run supplies no
        # left lexical boundary. Contextual targets carry their own proof.
        legacy_fragment=not kind and approved_start>0 and engine.is_hiragana(result['corrected'][approved_start-1])
        tail=_functional_tail(approved_parts,approved_start+len(reading))
        # A one-kana character repair does not prove an independent word.
        if (not bound and not legacy_fragment and not preserve and len(reading)>1 and all(engine.is_hiragana(c) or c=='ー' for c in reading)
                and kind not in ('kana_request','kana_copula','particle_adverbial','particle_intrusion')):
            remembered=surface_for_reading(reading)
            if not (remembered and remembered==reading):
                approved=result['corrected']
                # Both coordinate systems keep their own field boundary:
                # earlier accepted edits may have changed source lengths.
                before,_,following=engine._source_column_context(
                    approved,approved_start,approved_start+len(reading))
                source_before,_,source_after=engine._source_column_context(line,start,end)
                source_roles=nominal_roles(reading)
                source_argument=(candidate_nominal_spelling_evidence(before,reading,following)
                    if source_roles else None)
                candidates=_surfaces(reading,store,dictionary,compose=True,
                    before=source_before,following=source_after)
                candidates+=list(dictionary.surfaces_for_reading(reading,limit=32,band=False))
                candidates+=engine.table_surfaces_for_reading(reading,limit=16)
                converted=engine._convert_odd_kana_run(reading,store,dictionary)
                if converted:candidates.append(converted[0])
                ranked=[]
                for face in dict.fromkeys(candidates):
                    if not any(engine.is_kanji(c) for c in face):continue
                    parts=list(native_tokens(face))
                    actual=''.join(t.surface if all(engine.is_hiragana(c) or c=='ー' for c in t.surface)
                                   else t.reading if t.has_reading else '' for t in parts)
                    if actual!=reading:continue
                    from familiar_spelling import prefers_kana
                    if face!=remembered and prefers_kana(face,reading,before,following):continue
                    if source_argument and (not source_roles & nominal_roles(face)
                            or not candidate_nominal_spelling_evidence(before,face,following)):continue
                    head=_surface_score_head(face,following=source_after,before=source_before)
                    forms=dictionary_inflections(head) or ()
                    # Validate the untouched auxiliaries too, not only the
                    # replacement's interior (辞書+う / 自署+しう).
                    from contextual_repair import _productive_predicate,_allows_grammatical_tail,_grammatical_suffix
                    if tail:
                        suffix=face[len(head):]+tail
                        grammar=(_allows_grammatical_tail(forms,suffix,head_surface=head)
                            or any(pos.startswith('名詞,') for pos,_,_,_ in forms)
                            and _grammatical_suffix(suffix,'END'))
                        if not grammar or not _productive_predicate(face+tail,head,
                                before=before):continue
                    from semantic_roles import native_verb_roles,CASE_VERB_ROLES
                    ordinary=[]
                    for pos,form,lemma,rd in forms:
                        if pos.startswith(('名詞,一般,','名詞,サ変接続,','動詞,自立,','形容詞,自立,')):
                            tier=known_usage_tier(lemma)
                            if tier in (1,2):ordinary.append(tier)
                        if pos.startswith('動詞,自立,') and any(
                            native_verb_roles(head,form,rd,subject=subject,case=case)
                            for subject,case in [(False,None),(True,None)]+[(False,c) for c in CASE_VERB_ROLES]):
                            ordinary.append(2)
                        # A native counter's reading is licensed by this numeric boundary.
                        if (start and line[start-1].isdigit()
                                and pos.startswith('名詞,接尾,助数詞,') and rd==reading):
                            ordinary.append(2)
                    if not ordinary:continue
                    accepted,reason=engine._check_replacement(line,(start,end,face,'かな入力'),
                        store,tokenize,dictionary,decisions,conv_taken=((start,end),))
                    if accepted is None or accepted[:3]!=(start,end,face):continue
                    import oddness
                    after=line[:start]+face+line[end:]
                    if oddness.structural_anomaly_in_range(after,start,start+len(face),tokenize,store,dictionary):continue
                    ranked.append(((int(face!=remembered),min(ordinary),path_cost(source_before+face+source_after),face),face))
                if ranked:chosen=min(ranked)[1]
        # A selected repair may already be written in a rare kanji form.
        # Apply the same ordinary-kana policy after meaning selection, only
        # to native verb tokens touched by this repair. Keep explicit choices.
        if not preserve and any(engine.is_kanji(c) for c in chosen):
            from familiar_spelling import prefers_kana
            pieces=list(native_tokens(chosen))
            edits=engine._diff_spans(line[start:end],chosen)
            kana=[]
            for part in pieces:
                if not (part.has_reading and prefers_kana(part.surface,part.reading,line[:start]+chosen[:part.start],chosen[part.end:]+line[end:])
                        and any(part.start<j2 and j1<part.end for i1,i2,j1,j2 in edits)):
                    continue
                suffix=_functional_tail(pieces,part.end)
                remembered_word=surface_for_reading(part.reading+suffix)
                if (remembered_word==part.surface+suffix
                        or surface_for_reading(part.reading)==part.surface):
                    continue
                kana.append((part.start,part.end,part.reading))
            if kana:
                projected=_apply(chosen,kana)
                proposal=(start,end,projected,'かな入力')
                accepted,reason=engine._check_replacement(line,proposal,store,
                    tokenize,dictionary,decisions,conv_taken=((start,end),))
                if accepted==proposal:chosen=projected
        changed |= chosen!=reading
        finished.append((start,end,chosen))
    # Retain the actual checked lexical ranges for the next spelling pass;
    # display diffs can be smaller than the original rejection pair.
    finished.sort()
    result['_spelling_repair_frames']=tuple(finished)
    if not changed:return result
    parts=[];details=[];source_spans=[];spans=[];cursor=0;length=0
    for start,end,face in finished:
        if start<cursor:return result
        prefix=line[cursor:start];parts.append(prefix);length+=len(prefix)
        parts.append(face);source_spans.append((start,end));spans.append((length,length+len(face)))
        details.append((line[start:end],face,'かな入力'));length+=len(face);cursor=end
    parts.append(line[cursor:]);corrected=''.join(parts)
    engine._trace('補正後の表記',repr(result.get('corrected'))+' → '+repr(corrected))
    return dict(result,corrected=corrected,changed=corrected!=line,details=details,
                original_spans=source_spans,spans=spans)


def _mapped_frame(source,corrected,start,end,engine):
    diffs=list(engine._diff_spans(source,corrected))
    inside=[row for row in diffs if row[0]<end and start<row[1]
            or row[0]==row[1] and start<row[0]<end]
    if not inside or any(not start<=a<=b<=end for a,b,c,d in inside):return None
    lo=start+sum((d-c)-(b-a) for a,b,c,d in diffs if b<=start)
    hi=end+sum((d-c)-(b-a) for a,b,c,d in diffs if b<=end)
    return lo,hi,corrected[lo:hi]


def display_frames(source,corrected,targets,diagnostics,engine,tokenize):
    """A proved grammatical frame survives another route selecting the same edit."""
    frames=[]
    from reading_segments import _native_request_tail
    for target,diagnostic in zip(targets,diagnostics):
        kind=target.boundary_kind
        if kind not in ('kana_request','kana_copula','particle_intrusion','question_particle','kana_predicate'):continue
        mapped=_mapped_frame(source,corrected,target.start,target.end,engine)
        if mapped is None:continue
        lo,hi,face=mapped
        if not any(c['surface']==face for c in diagnostic.get('candidates',())):continue
        if kind=='kana_predicate' and not _native_request_tail(list(tokenize(face))):continue
        frames.append((target.start,target.end,face))
    return tuple(dict.fromkeys(frames))


def restore_display_frames(source,result,engine):
    frames=result.pop('_grammatical_display_frames',())
    if not frames:return result
    corrected=result.get('corrected',source)
    if corrected==source:return result
    from morphology import native_spelling_only
    grouped=[]
    for a,b,approved in sorted(frames,key=lambda row:(row[1]-row[0],row[0])):
        if any(a<y and x<b for x,y,c,d in grouped):continue
        mapped=_mapped_frame(source,corrected,a,b,engine)
        if mapped is None:continue
        c,d,face=mapped
        if not face or not (face==approved or native_spelling_only(approved,face)):continue
        grouped.append((a,b,c,d))
    if not grouped:return result
    diffs=[row for row in engine._diff_spans(source,corrected)
           if not any(a<=row[0]<=row[1]<=b for a,b,c,d in grouped)]
    diffs=sorted(diffs+grouped)
    return dict(result,original_spans=[(a,b) for a,b,c,d in diffs],
        spans=[(c,d) for a,b,c,d in diffs],
        details=[(source[a:b],corrected[c:d],'かな入力') for a,b,c,d in diffs])
