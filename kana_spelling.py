# -*- coding: utf-8 -*-
"""Native same-reading spelling in source and repairs; source offsets survive."""
import re
from morphology import COLUMN_SEPARATOR

def _lexical_units(text,parts,nominal_members=None,action_links=None):
    """Keep the longest dictionary word at each original lexical boundary.

    These are boundaries, not output choices. A short homophone inside an
    attested longer word cannot become a spelling candidate of its own.
    """
    import morphology as M
    from general_words import sourced_common_noun_evidence
    from reading_segments import native_lexical_reading_faces,native_action_value_nominal_faces,_native_counter_prefixes,native_counted_nominal_evidence,native_nominal_phrase_faces,native_inchoative_nominal_faces,native_attested_prefix_noun_faces,native_written_sahen_relative
    units=[];edge=0;compound_units=[]
    from reading_segments import native_action_note_introduction
    if native_action_note_introduction(text):
        # The existing source-note proof owns the entire bare action noun,
        # including after a real conjunction or discourse modifier.
        span=(parts[0].end,len(text));units.append(span)
        if nominal_members is not None:nominal_members.add(span)
    # The source-proved te/no noun owns its whole original range, even
    # when its kana best parse invents internal particles. Share the
    # grammatical boundary; normal choice and replacement checks still run.
    from reading_segments import native_te_nominal_parts
    te_nominals=native_te_nominal_parts(text,allow_following=True)
    for start,end,heads in te_nominals:
        units.append((start,end))
        if nominal_members is not None:nominal_members.add((start,end))
    # Reuse the completed relative clause's own sahen reading and noun
    # boundary when the full-text best parse crosses either seam.
    from reading_segments import native_adnominal_reading_parts,native_relative_action,completed_sahen_reading
    relative_edges=()
    relative=native_adnominal_reading_parts(text,allow_predicative=True)
    if relative:
        noun_start=len(text)-len(relative[-1][4]);head=text[:noun_start]
        action=native_relative_action(head)
        if action and completed_sahen_reading(head,allow_nonpolite=True,
                return_action=True,finite_only=True)==action[0]:
            for pos,form,base,reading in M.dictionary_inflections(action[0]) or ():
                if not (pos.startswith('名詞,サ変接続,') and base==action[0]
                        and reading and head.startswith(reading) and len(reading)<len(head)):continue
                span=(0,len(reading));units.extend((span,(noun_start,len(text))))
                if action_links is not None:action_links[span]=noun_start
                if nominal_members is not None:nominal_members.add((noun_start,len(text)))
                relative_edges=(len(reading),noun_start)
                break
    # Numeric words have the same native counter evidence used by source
    # grammar. A counter ending cannot become the start of a different verb.
    starts={0}|{t.end for t in parts if t.pos=='助詞' and t.pos_sub.startswith('格助詞')}
    from reading_segments import native_predicate_link_boundaries
    predicate_starts=starts|{t.start for t in parts if t.has_reading and t.pos=='動詞'}
    linked_starts={edge for start in predicate_starts
        for edge in native_predicate_link_boundaries(text,start)}
    # A native conjunction also starts an independent nominal slot.
    # This proves only its following noun, not the preceding clause.
    linked_starts.update(t.end for t in parts if t.has_reading and t.pos=='接続詞')
    # A following noun can swallow the connective's final kana in the best
    # parse. Prove the native whole action and actual する link separately;
    # the following nominal still needs its own dictionary boundary.
    from reading_segments import completed_sahen_reading,native_bare_action_faces
    for start in predicate_starts:
        for end in range(start+2,min(len(text)-1,start+18)+1):
            if text[end:end+2]!='して':continue
            heads=native_bare_action_faces(text[start:end])
            if not heads or completed_sahen_reading(text[start:end+2],allow_nonpolite=True,
                    return_action=True) not in heads:continue
            units.append((start,end));linked_starts.add(end+2)
            if action_links is not None:action_links[(start,end)]=end+2
    starts.update(linked_starts)
    # A completed native nominal predicate owns its head before the actual
    # copula, just as a nominal argument owns its head before a case marker.
    # The existing proof retains the whole original reading and finite tail.
    from reading_segments import completed_native_nominal_predicate
    nominal_starts=starts|{t.end for t in parts if t.has_reading and t.pos=='助詞'
        and t.pos_sub=='係助詞' and t.surface in ('は','も')}
    for start in sorted(nominal_starts):
        for copula in parts:
            if not (start<copula.start and copula.has_reading and copula.pos=='助動詞'
                    and copula.base_form in ('だ','です')):continue
            span=(start,copula.start)
            if (native_nominal_phrase_faces(text[start:copula.start])
                    and completed_native_nominal_predicate(text[start:],allow_topic=False,
                        nominal_end=copula.start-start)):
                units.append(span)
                if nominal_members is not None:nominal_members.add(span)
    # An independently native sahen head remains a whole word even when
    # the following native する continuative is still unfinished.
    # This proves its lexical range, not completion of the source clause.
    for token in parts:
        if not (token.end==len(text) and token.has_reading and any(pos.startswith('動詞,')
                and base=='する' and form=='連用形' and rd==token.reading
                for pos,form,base,rd in M.dictionary_inflections(token.surface) or ())):
            continue
        for start in (t.start for t in parts if 2<=token.start-t.start<=18):
            if native_bare_action_faces(text[start:token.start]):
                units.append((start,token.start))
    starts.update(i for i in range(2,len(text)-1) if native_written_sahen_relative(text[:i]))
    for start in sorted(starts):
        suffix=text[start:];original=M.tokenize(suffix)
        cuts=list(_native_counter_prefixes(suffix,original))
        cuts.extend(cut for cut in range(2,min(17,len(suffix)+1))
                    if any(ordinal for unit,ordinal in native_counted_nominal_evidence(suffix[:cut]))
                    and not any(t.start==0 and t.has_reading and cut<t.end and t.pos in ('名詞','動詞','形容詞','副詞') for t in original))
        if cuts:units.append((start,start+max(cuts)))
    # The existing nominal parser can prove a whole relational compound
    # even when the best parse inserts a spurious particle inside it.
    for start in sorted(starts):
        for boundary in parts:
            if (boundary.start<=start or boundary.pos!='助詞'
                    or not (boundary.pos_sub.startswith('格助詞')
                            or boundary.pos_sub=='係助詞' and boundary.surface in ('は','も'))):continue
            if not M.kana_syllable_boundary(text,boundary.end):continue
            rd=text[start:boundary.start]
            if 2<=len(rd)<=18:
                from reading_segments import native_coordinated_nominal_parts
                members=native_coordinated_nominal_parts(rd)
                if members:
                    position=start
                    for member in members:
                        span=(position,position+len(member));units.append(span)
                        if nominal_members is not None:nominal_members.add(span)
                        position+=len(member)+1
                elif native_nominal_phrase_faces(rd):
                    span=(start,boundary.start);units.append(span)
                    compound_units.append(span)
                    if nominal_members is not None:
                        nominal_members.add(span)
    # Janome can absorb the first kana of a relative noun into the past
    # auxiliary (したきー -> し / たき / ー). The completed clause is the
    # actual boundary, provided that the following noun is independently real.
    for start in sorted(starts):
        if not native_written_sahen_relative(text[:start]):continue
        for end in range(min(len(text),start+18),start+1,-1):
            reading=text[start:end]
            if not all('ぁ'<=c<='ゖ' or c=='ー' for c in reading):continue
            if native_nominal_phrase_faces(reading):
                units.append((start,end));break
    # A proved whole compound outranks an accidental short homophone.
    for start in sorted(starts):
        for end in range(min(len(text),start+18),start+1,-1):
            if native_attested_prefix_noun_faces(text[start:end]):
                units.append((start,end));break
    for token in parts:
        start=token.start
        previous=next((t for t in parts if t.end==start),None)
        nominal_edge=start in linked_starts or start==0 or previous and (previous.pos=='助詞' and (previous.pos_sub.startswith('格助詞') or previous.pos_sub=='連体化') or previous.surface=='の' and native_nominal_phrase_faces(text[:previous.start]))
        if start<edge or token.pos=='記号' or not nominal_edge and (token.pos in ('助詞','助動詞') or token.pos=='名詞' and token.pos_sub.startswith('非自立')):continue
        for end in range(min(len(text),start+18),start+1,-1):
            rd=text[start:end]
            if not all('ぁ'<=c<='ゖ' or c=='ー' for c in rd):continue
            faces=native_lexical_reading_faces(rd)
            if (native_action_value_nominal_faces(rd) or native_inchoative_nominal_faces(rd)
                    or any(sourced_common_noun_evidence(face,rd) for face in faces)
                    or any(any(r==rd and p.startswith(('名詞,一般,','名詞,サ変接続,','名詞,副詞可能,','動詞,自立,','形容詞,自立,'))
                       for p,f,b,r in M.dictionary_inflections(face) or ()) for face in faces)):
                units.append((start,end));edge=end;break
    # A proved whole nominal owns its internal boundary. An accidental
    # particle parse cannot start a second word across its retained tail.
    return [(a,b) for a,b in units
            if not any(lo<a<hi<b for lo,hi in compound_units)
            # A source-proved adnominal no is not the beginning of a
            # lexical homophone crossing into its same native noun.
            and not any(a<start<b for start,end,heads in te_nominals)
            and not any(a<edge<b for edge in relative_edges)]


def _ambiguous_short_kana(text):
    """An unchanged short reading needs context or a valid explicit choice."""
    if not (2<=len(text)<=3 and all('ぁ'<=c<='ゖ' for c in text)):return False
    import corrector as E,morphology as M
    from reading_segments import native_lexical_reading_faces
    from last_choice import surface_for_reading,active
    if surface_for_reading(text):return False
    chosen=active().lookup(text) if active() is not None else None
    if chosen and M.native_spelling_only(text,chosen):return False
    faces={f for f in native_lexical_reading_faces(text) if any(E.is_kanji(c) for c in f)}
    return len(faces)>1


def project(text,store,index,decisions=None):
    """Convert complete lexical units, retaining original grammatical tokens."""
    # No candidate loop can run without this same kana span pattern.
    if not re.search(r'[ぁ-ゖー]{2,}',text):return None
    import corrector as E,morphology as M,kango_tier as K
    if not M.HAS_JANOME or index is None:return None
    from contextual_repair import _surfaces,_completed_predicate_token
    from reading_segments import native_nominal_phrase_faces,native_bare_action_faces,native_lexical_reading_faces,native_katakana_nominal_face,completed_sahen_reading,native_deverbal_nominal_faces,native_attested_prefix_noun_faces,native_written_sahen_relative,native_nominal_spelling_faces,native_predicate_link_boundaries
    from semantic_roles import native_verb_roles,CASE_VERB_ROLES,nominal_roles,candidate_nominal_spelling_evidence
    from last_choice import surface_for_reading,active
    def remembered_surface(reading):
        face=surface_for_reading(reading)
        if face:return face
        chosen=active().lookup(reading) if active() is not None else None
        return chosen if chosen and M.native_spelling_only(reading,chosen) else None
    if remembered_surface(text)==text:return None
    if _ambiguous_short_kana(text):return None
    tok=E.make_tokenizer(store);current=text;result=dict(original=text,corrected=text)
    preferred=None;preferred_words=();preferred_checked=False
    def original_offset(offset):
        from contextual_repair import _legacy_source_changes
        delta=0
        for a,b,face in _legacy_source_changes(text,result,E,trim_context=False):
            lo=a+delta;hi=lo+len(face)
            if offset<=lo:return offset-delta
            if offset<hi:return None
            if offset==hi:return b
            delta+=len(face)-(b-a)
        return offset-delta
    def matches_preferred(a,b,face):
        if not preferred:return False
        start,end=original_offset(a),original_offset(b)
        if start is None or end is None:return False
        hit=[unit for unit in preferred_words if start<=unit[2]<unit[3]<=end]
        return bool(hit and hit[0][2]==start and hit[-1][3]==end
            and all(left[1]==right[0] and left[3]==right[2]
                    for left,right in zip(hit,hit[1:]))
            and preferred[hit[0][0]:hit[-1][1]]==face)

    # Each accepted step consumes at least one complete kana lexical unit.
    # Written units cannot be rewritten on a subsequent step.
    for _ in range(len(text)//2):
        parts=M.tokenize(current);options=[];nominal_members=set();action_context={}
        argument_context={}
        action_links={}
        units=_lexical_units(current,parts,nominal_members,action_links)
        grammatical_links=[]
        from contextual_repair import _allows_grammatical_tail
        for i,head in enumerate(parts):
            if not (head.has_reading and head.pos in ('動詞','形容詞')):continue
            edge=head.end
            for tail in parts[i+1:]:
                if not (tail.start==edge and tail.has_reading and (tail.pos=='助動詞'
                        or tail.pos=='助詞' and tail.pos_sub.startswith('接続助詞'))):break
                edge=tail.end
            if edge==head.end:continue
            forms=tuple(row for row in M.dictionary_inflections(head.surface) or ()
                if row[0].startswith(head.pos+',') and row[1]==head.infl_form and row[3]==head.reading)
            if forms and _allows_grammatical_tail(forms,current[head.end:edge],head.reading,head.surface):
                grammatical_links.append((head.start,head.end,edge))
        # A longer nominal lookup cannot absorb only part of an attested
        # verb's auxiliary. The actual native head and complete connection
        # own this seam; a complete independent word remains intact.
        units=[(lo,hi) for lo,hi in units if not any(
            lo==begin and head_end<hi<edge for begin,head_end,edge in grammatical_links)]
        from reading_segments import native_genitive_nominal_splits
        protected=[(cut,cut+1) for cut,left,right in native_genitive_nominal_splits(current)]
        # The best parse may split a real written imperative inside its
        # emphatic final vowel. Check the source's whole native word first.
        if current.endswith(('い','ぃ')):
            for token in parts:
                word=current[token.start:-1]
                if (word and not M.dictionary_inflections(current[token.start:])
                        and not native_lexical_reading_faces(current[token.start:])
                        and any(pos.startswith('動詞,自立,') and form.startswith('命令')
                                for pos,form,base,rd in M.dictionary_inflections(word) or ())):
                    protected.append((len(current)-1,len(current)))
                    break
        # Native final particles belong to the completed predicate even when
        # the best dictionary split selects a homographic noun (e.g. kana).
        from pos_grammar import explain_kana_run
        for token in parts:
            if not token.has_reading or not _completed_predicate_token((token.surface,
                    token.pos+':'+token.pos_sub,token.reading,token.start,token.end,True,token.infl_form)):continue
            tail=current[token.end:]
            if (tail and explain_kana_run(tail,no_words=True,initial_state='END',before_kanji=False)):
                protected.append((token.end,len(current)))
        from reading_segments import completed_native_reading_link
        # A proved te/de + focus link retains its grammatical connector;
        # a same-reading noun cannot absorb that connector.
        for link in re.finditer('[てで][はも]',current):
            if completed_native_reading_link(current[:link.end()]):
                protected.append((link.start(),link.end()))
        for run in re.finditer(r'[ぁ-ゖー]{2,}',current):
            for a in (a for a in range(run.start(),run.end()-1) if any(t.start==a for t in parts)):
                for z in range(a+2,min(run.end(),a+16)+1):
                    word=current[a:z]
                    if any(lo<=a and z<=hi and z-a<hi-lo for lo,hi in units):continue
                    # A native conjunction split inside an attested action
                    # head may include that head's actual completed する link.
                    # A conjunction beginning at the head boundary stays literal.
                    if (any(pos.startswith('接続詞,') and rd==word
                            for pos,form,base,rd in M.dictionary_inflections(word) or ())
                            and any(lo<a<hi<z and completed_sahen_reading(current[lo:z],
                                    allow_nonpolite=True,return_action=True)
                                    in native_bare_action_faces(current[lo:hi])
                                for lo,hi in units)):
                        continue
                    if (any(pos.startswith(('副詞,','感動詞,','接続詞,')) and rd==word for pos,form,base,rd in M.dictionary_inflections(word) or ())
                            or any(pos.startswith('連体詞,') and rd==word for pos,form,base,rd in M.dictionary_inflections(word) or ()) and not any(pos.startswith('名詞,') and rd==word for pos,form,base,rd in M.dictionary_inflections(word) or ())
                            or len(word)>=4 and len(word)%2==0 and word[:len(word)//2]==word[len(word)//2:]):
                        if not (word.endswith('の') and len(word)>2 and native_nominal_phrase_faces(word[:-1])):
                            protected.append((a,z))
        for match in re.finditer(r'[ぁ-ゖー]{2,}',current):
            for start in range(match.start(),match.end()-1):
                for end in range(min(match.end(),start+18),start,-1):
                    # A one-kana native verb stem has the same actual
                    # lexical boundary and auxiliary connection as a long
                    # stem. This does not admit one-kana noun guesses.
                    if end==start+1 and not any(
                            t.start==start and t.end==end and t.has_reading
                            and t.pos=='動詞' and t.pos_sub=='自立'
                            and any(lo==start and head_end==end for lo,head_end,edge in grammatical_links)
                            for t in parts):continue
                    rd=current[start:end];remembered=remembered_surface(rd)
                    if any(start<hi and lo<end and not (start==lo and end==head_end)
                           and not (start<lo and (start,end) in units)
                           for lo,head_end,hi in grammatical_links):
                        boundary=next((t for t in parts if t.start==end),None)
                        nominal_slot=bool(boundary and boundary.has_reading and boundary.pos=='助詞'
                            and boundary.surface!='と' and (boundary.pos_sub.startswith('格助詞')
                                or boundary.pos_sub=='連体化' or boundary.pos_sub=='係助詞' and boundary.surface in ('は','も')))
                        if not ((start,end) in units and (nominal_slot or (start,end) in action_links
                                or end==len(current) and (native_written_sahen_relative(current[:start])
                                    or start in native_predicate_link_boundaries(current,0)))
                                and native_nominal_phrase_faces(rd)):continue
                    # A single source-proved action owns its して seam, even
                    # when a longer accidental token overlaps that head.
                    unique_head_face=None
                    if (start==0 and current.startswith(rd+'して')
                            and action_links.get((start,end))==end+2
                            and text.startswith(rd+'して')):
                        from reading_segments import _native_action_note_heads
                        faces=tuple(native_bare_action_faces(rd))
                        if len(faces)==1 and _native_action_note_heads(text)==faces:
                            unique_head_face=faces[0]
                    overlaps=[(lo,hi) for lo,hi in units
                        if start<hi and lo<end and not (start<=lo and hi<=end)]
                    if overlaps:
                        # A unique complete native note may own its し seam.
                        # Otherwise an actual を argument must give positive
                        # meaning evidence for one action spelling.
                        proved=bool(unique_head_face and all(
                            lo==start and hi==end+1 for lo,hi in overlaps))
                        if (not proved and all(lo==start and hi==end+1 for lo,hi in overlaps)
                                and action_links.get((start,end))==end+2
                                and current[end:end+2]=='して'):
                            from semantic_roles import object_before,candidate_evidence
                            obj=object_before(current,start,tok)
                            if obj:
                                proved=any((candidate_evidence(obj,face,current[end:],current[:start]) or {})
                                    .get('shared_roles') for face in native_bare_action_faces(rd))
                        if not proved:continue
                    protected_hits=[(lo,hi) for lo,hi in protected
                        if start<hi and lo<end]
                    native_link=False
                    if protected_hits and (start,end) in units and all(
                            lo<start<hi for lo,hi in protected_hits) and native_bare_action_faces(rd):
                        from reading_segments import native_predicate_link_boundaries
                        link_origins={0}|{p.end for p in parts if p.pos=='助詞'
                            and p.pos_sub.startswith('格助詞')}
                        native_link=any(start in native_predicate_link_boundaries(current,origin)
                            for origin in link_origins)
                    # The same source proof outranks an internal adverb
                    # or bad exact POS parse.
                    note_head=bool(unique_head_face and protected_hits
                        and all(start<=lo<hi<=end+2 for lo,hi in protected_hits))
                    if (protected_hits
                            and not (note_head or (start,end) in units and
                                (native_written_sahen_relative(current[:start]) or native_link))):
                        from semantic_roles import candidate_nominal_spelling_evidence
                        if not ((start,end) in units and any(
                                candidate_nominal_spelling_evidence(current[:start],face,current[end:])
                                for face in native_nominal_phrase_faces(rd))):continue
                    if remembered==rd:continue
                    hit=[t for t in parts if t.start<end and start<t.end]
                    if not hit:continue
                    preceding=next((t for t in parts if t.end==start),None)
                    after=current[end:]
                    case=(after[:1] in ('が','を','に','へ','で','と','は','も','の')
                          and M.kana_syllable_boundary(current,end+1))
                    finite=bool(native_written_sahen_relative(current[:start]) or
                        preceding and preceding.has_reading and _completed_predicate_token((
                        preceding.surface,preceding.pos+':'+preceding.pos_sub,preceding.reading,
                        preceding.start,preceding.end,True,preceding.infl_form)))
                    genitive=bool(preceding and preceding.has_reading and preceding.surface=='の'
                                  and preceding.pos=='助詞' and preceding.pos_sub=='連体化')
                    noun_slot=((start,end) in nominal_members or start==0 and (not after or case) or (finite or genitive) and (not after or case))
                    nominal=tuple(dict.fromkeys(native_nominal_spelling_faces(rd)+native_nominal_phrase_faces(rd))) if noun_slot else ()
                    next_token=next((t for t in parts if t.start==end),None)
                    explicit_nominal=bool(nominal and ((start,end) in nominal_members or next_token and next_token.pos=='助詞'
                        and (next_token.pos_sub.startswith('格助詞') or next_token.pos_sub=='連体化'))
                        and not (finite and len(hit)==1 and hit[0].has_reading
                            and hit[0].start==start and hit[0].end==end
                            and hit[0].pos=='名詞' and hit[0].pos_sub.startswith('非自立')))
                    action_note=bool((not after or after.startswith('して')) and
                        (start==0 or current[:start].endswith('して')))
                    actions=tuple(native_bare_action_faces(rd))
                    action_unit=bool(actions and (
                        (start,end) in action_links
                        or completed_sahen_reading(rd+after,allow_nonpolite=True,return_action=True) in actions
                        or any(completed_sahen_reading(rd+current[end:t.end],
                            allow_nonpolite=True,return_action=True) in actions
                            for t in parts if start<t.start and end<t.end<=end+10 and t.has_reading
                            and (t.pos=='接続詞' and t.start<end
                                or end<=t.start and (t.pos=='助詞' and t.pos_sub=='接続助詞'
                                    or _completed_predicate_token((t.surface,t.pos+':'+t.pos_sub,
                                        t.reading,t.start,t.end,True,t.infl_form)))))))
                    if not (action_note or action_unit):actions=()
                    # A shipped compound with a proved on-reading prefix may
                    # act as its native sahen head before a completed する form.
                    # The whole word and the inflection are independent facts.
                    compound_action=[]
                    for face in native_attested_prefix_noun_faces(rd):
                        head=face[1:]
                        for pos,form,base,head_reading in M.dictionary_inflections(head) or ():
                            if not (pos.startswith('名詞,サ変接続,') and rd.endswith(head_reading)):
                                continue
                            if any(native_written_sahen_relative(face+after[:cut])
                                   for cut in range(2,min(8,len(after))+1)):
                                compound_action.append(face);break
                    # A stronger, independently attested whole lexical unit
                    # can recover a bad kana split without trusting its pieces.
                    whole=tuple(face for face in (nominal or actions or compound_action)
                                if M.native_spelling_only(rd,face))
                    known=[t for t in hit if t.has_reading]
                    if any(t.pos=='名詞' and t.pos_sub.startswith('非自立') or t.base_form in M.FUNCTION_WORDS or t.surface in M.FUNCTION_WORDS
                           for t in known) and not (whole and (action_unit or native_katakana_nominal_face(rd) in whole
                           or native_attested_prefix_noun_faces(rd)
                           or explicit_nominal and (start,end) in nominal_members
                           or native_written_sahen_relative(current[:start]) and (start,end) in units)):continue
                    if any(t.start<start or end<t.end for t in known) and (start,end) not in units:continue
                    if any(any(E.is_kanji(c) or E.is_katakana(c) for c in t.surface)
                           and (t.start<start or end<t.end) for t in hit):continue
                    if any(t.pos in ('助詞','助動詞','接頭詞','副詞','感動詞','記号')
                           or t.pos=='名詞' and t.pos_sub.startswith('非自立')
                           or t.pos=='動詞' and (t.pos_sub.startswith('非自立') or t.base_form in M.FUNCTION_WORDS)
                           for t in known) and not whole:continue
                    faces=([remembered] if remembered else [])+list(whole)+_surfaces(rd,store,index)+list(index.surfaces_for_reading(rd,limit=32,band=True))+list(index.inflected_surfaces_for_reading(rd))+list(native_lexical_reading_faces(rd))
                    exact=(len(hit)==1 and hit[0].has_reading and hit[0].start==start and hit[0].end==end)
                    for face in dict.fromkeys(faces):
                        if face==rd or not any(E.is_kanji(c) or E.is_katakana(c) for c in face):continue
                        from familiar_spelling import prefers_kana
                        if face!=remembered and prefers_kana(face,rd):continue
                        if decisions is not None and decisions.blocks(rd,face):continue
                        from general_words import sourced_common_noun_evidence
                        forms=tuple(M.dictionary_inflections(face) or ())+tuple(
                            (entry['pos'],'*',face,entry['reading'])
                            for entry in sourced_common_noun_evidence(face,rd))
                        viable=[];frame_bases=set();frame_support=set()
                        for pos,form,base,reading in forms:
                            if reading!=rd or any(x in pos for x in ('固有名詞','非自立')):continue
                            # A native adverbial noun can denote time/order as well
                            # as an object; a merely homophonic concrete noun loses it.
                            if (any(p.startswith('名詞,副詞可能,') and r==rd for p,f,b,r in M.dictionary_inflections(rd) or ())
                                    and not any(p.startswith('名詞,副詞可能,') and r==rd for p,f,b,r in forms)
                                    and not (explicit_nominal and nominal_roles(rd) & nominal_roles(face)
                                        and candidate_nominal_spelling_evidence(current[:start],face,after))):continue
                            if not pos.startswith(('名詞,','動詞,自立,','形容詞,自立,','連体詞,')):continue
                            if explicit_nominal and pos.startswith(('動詞,','形容詞,')):continue
                            deverbal=face in native_deverbal_nominal_faces(rd) and face in whole and hit[0].pos=='動詞' and hit[0].infl_form=='連用形'
                            counter=bool(start and current[start-1].isdigit() and pos.startswith('名詞,接尾,助数詞,'))
                            # A dictionary token inside an unexplained kana chain
                            # does not prove a noun phrase. Require a grammatical
                            # edge or the independently attested complete nominal.
                            nominal_edge=start==0 or bool(preceding and preceding.pos=='助詞') or genitive or finite
                            nominal_tail=not after or case
                            if pos.startswith('名詞,') and not (counter or face in whole or nominal_edge and nominal_tail):continue
                            if pos.startswith('動詞,') and after:
                                following=next((t for t in parts if t.start==end),None)
                                if following and following.has_reading:
                                    from contextual_repair import _modern_euphonic_link,_modern_te_allowed
                                    link=_modern_euphonic_link(following.surface,following.pos+':'+following.pos_sub,following.infl_form)
                                    if link and _modern_te_allowed(face,rd,link) is not True:continue
                                    if form=='連用タ接続' and not link:continue
                            # An alternative nominal spelling cannot override
                            # an attested pronoun, dependent noun or inflected
                            # source predicate merely by supplying a whole noun.
                            object_noun_slot=bool(exact and hit[0].pos in ('動詞','形容詞')
                                and hit[0].infl_form=='基本形' and next_token
                                and next_token.surface=='を' and next_token.pos=='助詞'
                                and next_token.pos_sub.startswith('格助詞'))
                            genitive_noun_slot=bool(exact and hit[0].pos=='動詞'
                                and hit[0].infl_form=='連用形' and next_token
                                and next_token.surface=='の' and next_token.pos=='助詞'
                                and next_token.pos_sub=='連体化')
                            # Independently completed sahen morphology owns
                            # the source noun even if the best kana split is
                            # a homographic verb. Keep its literal suru tail.
                            if exact and not deverbal and not (action_unit and face in actions) and not (explicit_nominal and face in whole
                                    and (hit[0].pos=='名詞'
                                        and not hit[0].pos_sub.startswith(('非自立','代名詞'))
                                        or object_noun_slot or genitive_noun_slot)):
                                t=hit[0]
                                if not counter and not pos.startswith(t.pos+','+(t.pos_sub.replace(':',',')+',' if t.pos_sub else '')) and face!=unique_head_face:continue
                                if t.pos in ('動詞','形容詞') and form!=t.infl_form and face!=unique_head_face:continue
                                if t.pos=='連体詞' and not any(p.startswith(('名詞,','形容詞,')) for p,f,b,r in forms):continue
                            original_roles=nominal_roles(rd)
                            if original_roles and not original_roles & nominal_roles(face):continue
                            tier=K.usage_tier_for_reading(base,rd)
                            if tier==3 and face!=remembered:continue
                            ordinary=face==remembered or tier in (1,2) or face in whole
                            if exact and pos.startswith('名詞,') and (counter or face==''.join(chr(ord(c)+0x60) if 'ぁ'<=c<='ゖ' else c for c in rd)):ordinary=True
                            if pos.startswith('動詞,'):
                                ordinary=ordinary or any(native_verb_roles(face,form,rd,subject=s,case=c)
                                    for s,c in [(False,None),(True,None)]+[(False,c) for c in CASE_VERB_ROLES])
                            if ordinary and pos.startswith('動詞,'):
                                # A case particle at the start of this field has no
                                # argument. A remembered spelling cannot supply one.
                                if (preceding and preceding.pos=='助詞'
                                        and preceding.pos_sub.startswith('格助詞')
                                        and preceding.start==0):continue
                                # An explicit case constrains a homophone choice. A
                                # known reading alone cannot supply the argument meaning.
                                # One generated candidate does not prove that the
                                # omitted homophones have the same meaning.
                                if face!=remembered:
                                    from semantic_roles import object_before,case_argument_before,subject_before,candidate_evidence,subject_candidate_evidence
                                    if start not in argument_context:
                                        argument_context[start]=(object_before(current,start,tok),
                                            case_argument_before(current,start,tok),subject_before(current,start,tok))
                                    obj,arg,sub=argument_context[start]
                                else:obj=arg=sub=None
                                # A newly admitted single-kana stem cannot treat
                                # an unrecognized explicit argument as no argument.
                                if (end==start+1 and face!=remembered and preceding
                                        and preceding.pos=='助詞'
                                        and preceding.pos_sub.startswith('格助詞')
                                        and not (obj or arg or sub)):continue
                                neutral_time=False
                                if obj or arg or sub:
                                    proof=[]
                                    if obj:proof.append(candidate_evidence(obj,face,after,current[:start]))
                                    if arg:proof.append(candidate_evidence(arg[0],face,after,current[:start],case=arg[1]))
                                    if sub:proof.append(subject_candidate_evidence(sub,face,after))
                                    if not any(p and p.get('shared_roles') for p in proof):continue
                                    # An unspelled kana noun may still denote multiple
                                    # written senses. One sense cannot lend its argument
                                    # role to an incompatible or unclassified homophone.
                                    if obj and all('ぁ'<=c<='ゖ' or c=='ー' for c in obj):
                                        noun_faces=[f for f in native_nominal_phrase_faces(obj)
                                            if any(E.is_kanji(c) or E.is_katakana(c) for c in f)]
                                        if len(noun_faces)>1 and any(not (candidate_evidence(f,face,after,current[:start]) or {}).get('shared_roles') for f in noun_faces):continue
                                    supported={role for p in proof if p for role in p.get('shared_roles',())}
                                    # Temporal ni places any event in time; it does
                                    # not choose among different lexical actions.
                                    neutral_time=bool(arg and arg[1]=='に' and not (obj or sub)
                                                      and supported=={'time'})
                                    frame_bases.add(base)
                                    frame_support.update(supported)
                                if (not (obj or arg or sub) or neutral_time) and face!=remembered:
                                    from contextual_repair import _modern_euphonic_link,_modern_te_allowed
                                    link=(_modern_euphonic_link(next_token.surface,
                                        next_token.pos+':'+next_token.pos_sub,next_token.infl_form)
                                        if neutral_time and next_token and next_token.start==end else None)
                                    bases={''.join(c for c in b if E.is_kanji(c))
                                        # Use the same actual inflected forms as
                                        # candidate generation. A short reading's
                                        # nominal lookup may omit every written verb.
                                        for f in (*native_lexical_reading_faces(rd),
                                            *index.inflected_surfaces_for_reading(rd))
                                        for p,frm,b,r in M.dictionary_inflections(f) or ()
                                        if p.startswith('動詞,自立,') and frm==form and r==rd
                                        and any(E.is_kanji(c) for c in b)
                                        and (link is None or _modern_te_allowed(f,r,link) is not False)}
                                    if len(bases)>1:continue
                            if ordinary:viable.append(tier or 3)
                        if not viable and not (face in whole and not forms and not exact):continue
                        proposed=current[:start]+face+after
                        if not M.native_spelling_only(current,proposed):continue
                        from ime_spelling import _reinterprets_function_attachment
                        if _reinterprets_function_attachment(current,start,end,face):continue
                        accepted,reason=E._check_replacement(current,(start,end,face,'かな入力'),store,tok,index,decisions,
                            conv_taken=((start,end),),spelling=True)
                        if accepted is None or tuple(accepted[:3])!=(start,end,face):continue
                        import oddness
                        if oddness.structural_anomaly_in_range(proposed,start,start+len(face),tok,store,index):continue
                        # Ordinary noun spellings share the same actual
                        # argument meaning as repaired nouns and verbs.
                        from semantic_roles import candidate_nominal_spelling_evidence
                        nominal_support=(candidate_nominal_spelling_evidence(current[:start],face,after)
                            if any(pos.startswith('名詞,') and reading==rd for pos,form,base,reading in forms) else None)
                        # Only independently complete native actions supply
                        # positive shared activity meaning for a closed note.
                        if action_note and after.startswith('して') and face in actions:
                            shared=set()
                            next_note=after[2:]
                            next_actions=list(native_bare_action_faces(next_note))
                            if any(pos.startswith('名詞,サ変接続,') and base==next_note
                                   for pos,form,base,rd in M.dictionary_inflections(next_note) or ()):
                                next_actions.append(next_note)
                            for following_action in next_actions:
                                shared.update(nominal_roles(face) & nominal_roles(following_action))
                            action_context[(start,end,face)]=len(shared)
                        action_role=0
                        if overlaps and action_unit and face in actions and action_links.get((start,end))==end+2:
                            from semantic_roles import object_before,candidate_evidence
                            if start not in argument_context:
                                argument_context[start]=(object_before(current,start,tok),None,None)
                            obj=argument_context[start][0]
                            if obj:
                                proof=candidate_evidence(obj,face,after,current[:start])
                                action_role=bool(proof and proof.get('shared_roles'))
                        if overlaps and not action_role and face!=remembered and face!=unique_head_face:continue
                        options.append(((-(end-start),int(face!=remembered),-bool(nominal_support),
                            -bool(nominal_support and nominal_support.get('coordinated_shared_roles')),
                            -action_role,min(viable or [3]),M.path_cost(proposed),face),
                                        (start,end,face),
                                        (frozenset(frame_bases),frozenset(frame_support)) if frame_support else None))
        if not options:break
        # Choose the ordinary reading when several already validated senses
        # remain. A remembered spelling and concrete role support rank first.
        prefix=min(item[0][:-2] for item in options)
        tied=[item for item in options if item[0][:-2]==prefix]
        if len(tied)>1:
            if not preferred_checked:
                from ime_language import JapaneseIME
                with JapaneseIME() as ime:
                    from ime_spelling import source_first_words
                    first=source_first_words(text,ime) if ime.available else None
                    if first and M.native_spelling_only(text,first[0]):
                        preferred,preferred_words=first[:2]
                preferred_checked=True
            if preferred:
                # The IME may also spell later words. Compare only this
                # proved lexical range, aligned back to its original reading.
                options=[(key[:-2]+(int(not matches_preferred(a,b,face)),)+key[-2:],
                          (a,b,face),proof) for key,(a,b,face),proof in options]
        selected=min(options,key=lambda item:item[0])
        # Preserve the chosen source span. Semantic evidence selects its
        # homophone; it must not reorder spelling of independent later words.
        same_span=[item for item in options if item[1][:2]==selected[1][:2]
            and item[0][1:4]==selected[0][1:4]]
        change=min(same_span,key=lambda item:(-action_context.get(item[1],0),item[0]))[1]
        composed=_compose_result(text,result,[change],E,decisions)
        if composed.get('corrected')==current:break
        result=composed;current=result['corrected']
    if current==text:return None
    from contextual_repair import _legacy_source_changes
    return current,tuple(_legacy_source_changes(text,result,E,trim_context=False))


_FIELD_END=re.compile(COLUMN_SEPARATOR.pattern+r'|[、,。！？!?;；]')

def _fields(text):
    from morphology import detached_symbol_separators
    separators=list(detached_symbol_separators(text))
    separators.extend(match.span() for match in _FIELD_END.finditer(text))
    start=0
    for end,following in sorted(separators)+[(len(text),len(text))]:
        if start<end:yield start,end
        start=max(start,following)


def _compose_result(line,result,spelling,engine,decisions=None,source_frames=()):
    from contextual_repair import _legacy_source_changes,_apply
    approved=result.get('corrected',line)
    # Existing highlight coordinates are part of the correction contract.
    # A diff fallback cannot repair corrupt provenance for a further edit.
    if approved!=line or result.get('original_spans') or result.get('spans'):
        source_ranges=result.get('original_spans') or []
        result_ranges=result.get('spans') or []
        if len(source_ranges)!=len(result_ranges) or not source_ranges:return result
        source_edge=result_edge=0;recorded=[]
        for (a,z),(lo,hi) in zip(source_ranges,result_ranges):
            if not (source_edge<=a<=z<=len(line) and result_edge<=lo<=hi<=len(approved)):return result
            recorded.append((a,z,approved[lo:hi]));source_edge=z;result_edge=hi
        if _apply(line,recorded)!=approved:return result
    old=sorted(source_frames) if source_frames else _legacy_source_changes(
        line,result,engine,trim_context=False)
    if any(not 0<=a<=b<=len(line) for a,b,_ in old):return result
    if any(left[1]>right[0] for left,right in zip(old,old[1:])):return result
    if _apply(line,old)!=approved:return result
    # Some older key routes report the whole field for one physical Shift
    # change. Preserve its actual key coordinate before combining IME words.
    from ime_missing_shift import _FULL_TO_SMALL
    narrow=[]
    for start,end,face in old:
        source=line[start:end]
        differences=[i for i,(a,b) in enumerate(zip(source,face)) if a!=b]
        if (len(source)==len(face) and len(differences)==1
                and _FULL_TO_SMALL.get(face[differences[0]])==source[differences[0]]):
            i=differences[0]
            narrow.append((start+i,start+i+1,face[i]))
        else:narrow.append((start,end,face))
    old=narrow
    projected=[];delta=0
    for start,end,face in old:
        lo=start+delta;hi=lo+len(face)
        projected.append((lo,hi,start,end));delta+=len(face)-(end-start)
    deletion_seams={}
    for lo,hi,a,z in projected:
        if lo==hi:
            old=deletion_seams.get(lo,(a,z))
            deletion_seams[lo]=(min(a,old[0]),max(z,old[1]))
    intervals=[(lo,hi) for lo,hi,_,_ in projected]+[(a,b) for a,b,_ in spelling]
    groups=[]
    for lo,hi in sorted(intervals):
        if groups and (lo<groups[-1][1] or lo==groups[-1][1] and lo in deletion_seams):
            groups[-1]=(groups[-1][0],max(groups[-1][1],hi))
        else:groups.append((lo,hi))
    def source_offset(offset,right=False):
        if offset in deletion_seams:return deletion_seams[offset][int(right)]
        delta=0
        for lo,hi,a,b in projected:
            if offset<lo:break
            if offset==lo:return a
            if offset<hi:return b if right else a
            if offset==hi:return b
            delta+=(hi-lo)-(b-a)
        return offset-delta
    changes=[];accepted_spelling=list(spelling)
    for lo,hi in groups:
        edits=[(a-lo,b-lo,face) for a,b,face in spelling if lo<=a<=b<=hi]
        face=_apply(approved[lo:hi],edits)
        start,end=source_offset(lo),source_offset(hi,True)
        # Preserve the already checked repair when a later word spelling
        # would recreate an exact rejected original-to-finished pair.
        # These coordinates also retain any unchanged functional tail.
        if edits and engine._user_blocks_replacement(decisions,line[start:end],face):
            face=approved[lo:hi]
            accepted_spelling=[row for row in accepted_spelling
                               if not lo<=row[0]<=row[1]<=hi]
        if line[start:end]!=face:changes.append((start,end,face))
    if not accepted_spelling:return result
    corrected=_apply(line,changes)
    if corrected!=_apply(approved,accepted_spelling):
        engine._trace('表記の範囲','原文座標へ戻せないため表記変更を見送る')
        return result
    spans=[];source_spans=[];details=[];delta=0
    for start,end,face in changes:
        lo=start+delta;spans.append((lo,lo+len(face)));source_spans.append((start,end))
        details.append((line[start:end],face,'かな入力'));delta+=len(face)-(end-start)
    return dict(result,corrected=corrected,changed=corrected!=line,spans=spans,
                original_spans=source_spans,details=details)


def _restore_unresolved_shift_fields(line,result,store,dictionary):
    """An unfinished physical edit cannot clear the original odd field."""
    if not re.search(r'[\t\r\n⇒→]',line):
        return result
    approved=result.get('corrected',line)
    if approved==line:
        return result
    original_fields=list(_fields(line));current_fields=list(_fields(approved))
    if len(original_fields)!=len(current_fields):
        return result
    from pos_grammar import odd_kana_spans
    bad=[];marks=[]
    for (a,b),(lo,hi) in zip(original_fields,current_fields):
        source=line[a:b];current=approved[lo:hi]
        if (source==current or not source
                or any(not ('ぁ'<=c<='ゖ' or c=='ー') for c in source)
                or any(c in 'ぁぃぅぇぉっゃゅょを' for c in source)
                or any(not ('ぁ'<=c<='ゖ' or c=='ー') for c in current)):
            continue
        if not odd_kana_spans(current+'\t',dictionary,store):
            continue
        source_odd=odd_kana_spans(source+'\t',dictionary,store)
        if source_odd:
            bad.append((a,b))
            marks.extend((a+x,a+y) for x,y in source_odd)
    if not bad:
        return result
    import corrector as engine
    from contextual_repair import _legacy_source_changes,_apply
    changes=_legacy_source_changes(line,result,engine,trim_context=False)
    retained=[change for change in changes if not any(a<hi and lo<b
                          for lo,hi in bad for a,b,_ in (change,))]
    corrected=_apply(line,retained)
    categories={(a,b):detail[2] for (a,b),detail in zip(
        result.get('original_spans',()),result.get('details',())) if len(detail)>2}
    spans=[];source_spans=[];details=[];delta=0
    for a,b,face in retained:
        lo=a+delta;spans.append((lo,lo+len(face)));source_spans.append((a,b))
        details.append((line[a:b],face,categories.get((a,b),'かな入力')))
        delta+=len(face)-(b-a)
    odd=[tuple(span) for span in result.get('odd_spans',())]
    odd.extend(marks)
    odd=sorted(set(odd))
    out=dict(result,original=line,corrected=corrected,changed=corrected!=line,
             spans=spans,original_spans=source_spans,details=details,odd_spans=odd)
    out['odd_reasons']=[reason for reason in out.get('odd_reasons',())
        if not (isinstance(reason,(tuple,list)) and len(reason)>=2
                and isinstance(reason[0],int) and isinstance(reason[1],int)
                and any(lo<reason[1] and reason[0]<hi for lo,hi in bad))]
    out['_repair_surfaces']=[frame for frame in out.get('_repair_surfaces',())
        if not any(lo<frame[1] and frame[0]<hi for lo,hi in bad)]
    out.pop('_validated_corrected',None)
    out.pop('_validated_repair_ranges',None)
    out.pop('diagnosis',None)
    return out


def finish(line,result,store,tokenize,dictionary,decisions=None):
    """Choose written forms after key correction, without borrowing another field."""
    spelling_keep=result.pop('_spelling_keep',())
    source_frames=result.pop('_spelling_repair_frames',())
    if not store or not dictionary or not tokenize or result.get('analysis_status')=='incomplete':return result
    # Same-reading spelling also applies to an untouched kana source.
    # Word boundaries, meaning, explicit choices and final source validation
    # remain the projector's requirements; spelling supplies no anomaly.
    explicitly_closed=bool(re.search(r'[\t\r\n⇒→]',line))
    from literal_examples import protected_ranges,overlaps
    import corrector as engine
    approved=result.get('corrected',line);protected=protected_ranges(approved);changes=[];resolved_fields=[]
    fields=list(_fields(approved));original_fields=list(_fields(line))
    odd=result.get('odd_spans') or ()
    listed_nominals=line.count('、')+line.count(',')>=2
    for number,(start,end) in enumerate(fields):
        odd_field=bool(odd and (len(fields)!=len(original_fields)
            or overlaps(*original_fields[number],odd)))
        text=approved[start:end]
        if not 2<=len(text)<=80 or not any('ぁ'<=c<='ゖ' for c in text):continue
        if overlaps(start,end,protected):continue
        # A column terminator or blank protection mask supplies no meaning
        # for an unchanged short reading. Share the native projector's
        # ambiguity contract before any first-IME spelling fallback.
        if (len(fields)==len(original_fields)
                and line[slice(*original_fields[number])]==text
                and _ambiguous_short_kana(text)):
            continue
        # An intact noun in a written enumeration already has a legitimate
        # source spelling. A homophone or script change needs its own edit
        # or a remembered choice; neighboring list members give no such proof.
        if (listed_nominals and len(fields)==len(original_fields) and not odd_field
                and line[slice(*original_fields[number])]==text):
            from morphology import tokenize as native_tokens
            from last_choice import surface_for_reading
            words=native_tokens(text)
            if (len(words)==1 and words[0].has_reading and words[0].pos=='名詞'
                    and words[0].surface==text
                    and surface_for_reading(text) in (None,text)):
                continue
        missing_shift=None
        if len(fields)==len(original_fields):
            from ime_missing_shift import complete_field,complete_written_field
            a,b=original_fields[number]
            from ime_closed_frame import complete_field as complete_closed_frame
            missing_shift=complete_closed_frame(line[a:b],text,store,dictionary,decisions,tokenize)
            if missing_shift is None:
                written_shift=complete_written_field(line[a:b],text,store,dictionary,decisions,tokenize)
                missing_shift=(written_shift,((0,len(text),written_shift),)) if written_shift is not None else None
            # A sentence-final mark closes the original kana source.
            # An earlier partial repair can already have cleared its purple,
            # so the source-side Shift gate itself decides whether to try.
            sentence_closed=bool(b<len(line) and line[b] in '。！？!?')
            # The written finite auxiliary is another source-side closure.
            # The shift repair still needs its own pre-candidate oddness gate.
            finite_source=bool(b==len(line) and
                line[a:b].endswith(('ます','ました','ません','です','でした')))
            if missing_shift is None and (
                    explicitly_closed or sentence_closed or finite_source):
                missing_shift=complete_field(line[a:b],text,store,dictionary,decisions,tokenize)
        preverified=None
        if (missing_shift is None and odd_field
                and len(fields)==len(original_fields)
                and line[original_fields[number][0]:original_fields[number][1]]==text
                and any(c in 'ぁぃぅぇぉ' for c in text)):
            from ime_full_field import additional_first_words
            preverified=additional_first_words(text,None,store,dictionary,decisions,tokenize)
        if (missing_shift is None and preverified is None and odd_field
                and len(fields)==len(original_fields)
                and line[slice(*original_fields[number])]==text
                and any(not ('ぁ'<=c<='ゖ' or c=='ー') for c in text)):
            # First-IME spelling accepts all-kana fields only. For mixed
            # source text, share independently proved source word ranges;
            # an unchanged unknown tail cannot borrow that proof.
            from reading_segments import native_context_ranges
            normal=native_context_ranges(text)
            native=project(text,store,dictionary,decisions) if normal else None
            if native and native[1] and all(any(lo<=a<b<=hi for lo,hi in normal)
                                           for a,b,face in native[1]):
                preverified=native
        repaired=None
        if (missing_shift is None and result.get('corrected',line)!=line
                and len(fields)==len(original_fields)):
            from ime_shift_finish import project_repaired_field
            a,b=original_fields[number]
            repaired=project_repaired_field(line[a:b],text,store,dictionary,decisions,tokenize)
        if missing_shift is not None:
            proposal=missing_shift
        elif repaired:
            proposal=repaired
        elif preverified is not None:
            proposal=preverified
        else:
            if odd_field:
                # The IME can spell individual words in a malformed kana
                # clause. Same-reading spelling cannot repair the original
                # connection; leave its mark until a proved key edit does.
                from pos_grammar import odd_kana_spans
                if odd_kana_spans(text+'\t',dictionary,store):
                    continue
            from ime_spelling import project_first_words
            # The native projector can spell an untouched source. The
            # first-IME fallback retains its closed/repaired field contract.
            first_words=(project_first_words(text,store,dictionary,decisions,tokenize)
                if odd_field or approved!=line or explicitly_closed else None)
            if odd_field:
                # Only a complete same-reading spelling with a positive source
                # argument can resolve a malformed kana segmentation.
                if not first_words or not first_words[2]:continue
                proposal=first_words[:2]
            else:
                proposal=project(text,store,dictionary,decisions)
                if first_words and (proposal is None or (
                        {(a,b) for a,b,_ in proposal[1]}.issubset(
                            {(a,b) for a,b,_ in first_words[1]})
                        and len(first_words[1])>len(proposal[1]))):
                    proposal=first_words[:2]
        if not odd_field and re.search(r'[\t\r\n⇒→]',line):
            from ime_full_field import additional_first_words
            complete=additional_first_words(text,proposal,store,dictionary,
                                            decisions,tokenize)
            if complete is not None:
                proposal=complete
        if proposal is None:continue
        face,edits=proposal
        if result.get('corrected',line)!=line and len(fields)==len(original_fields):
            from ime_shift_finish import project_repaired_polite_tail
            a,b=original_fields[number]
            tail_spelling=project_repaired_polite_tail(
                line[a:b],face,store,dictionary,decisions,tokenize)
            if tail_spelling:
                desired,tail_edits=tail_spelling
                if len(tail_edits)==1:
                    tail_start,tail_end,tail_face=tail_edits[0]
                    old_tail=face[tail_start:tail_end]
                    approved_start=len(text)-len(old_tail)
                    if (tail_end==len(face) and text.endswith(old_tail)
                            and all(end<=approved_start for start,end,_ in edits)):
                        edits=tuple(edits)+((approved_start,len(text),tail_face),)
                        face=desired
        # A spelling that introduces an unexplained boundary on the next
        # analysis is not a completed result. Reuse the common mark evidence
        # once for the proposed field; do not run correction recursively.
        if engine._odd_spans_for_line(face,tokenize,[],store,dictionary,include_pending=False):continue
        if odd_field:resolved_fields.append(original_fields[number])
        changes.extend((start+a,start+b,sf) for a,b,sf in edits
            if text[a:b]!=sf and not any(start+a<hi and lo<start+b
                for lo,hi in spelling_keep))
    if not changes:
        return _restore_unresolved_shift_fields(line,result,store,dictionary)
    completed=_compose_result(line,result,changes,engine,decisions,source_frames)
    if resolved_fields and completed is not result:
        completed['odd_spans']=[(a,b) for a,b in completed.get('odd_spans',())
            if not any(a<hi and lo<b for lo,hi in resolved_fields)]
        completed=engine._line_result_contract(line,completed,tokenize,dictionary)
    return _restore_unresolved_shift_fields(line,completed,store,dictionary)
