# -*- coding: utf-8 -*-
"""Native same-reading spelling in source and repairs; source offsets survive."""
import re
from morphology import COLUMN_SEPARATOR

def _native_inflected_identity(face,reading):
    """Native okurigana variants share kanji, lemma reading and actual form.

    Readings alone never identify a sense. Every written alternative and
    its lemma must already exist in the dictionary; no form is invented.
    """
    import morphology as M
    def stem(word):
        if not all('ぁ'<=c<='ゖ' or '一'<=c<='鿿' for c in word):return ''
        return ''.join(c for c in word if '一'<=c<='鿿')
    if not stem(face):return None
    identities=set()
    for pos,form,base,rd in M.dictionary_inflections(face) or ():
        if rd!=reading or not pos.startswith(('動詞,自立,','形容詞,自立,')):continue
        if not stem(base):continue
        for p,f,b,r in M.dictionary_inflections(base) or ():
            if p==pos and f=='基本形' and b==base:
                identities.add((pos,form,r,stem(base),stem(face)))
    return next(iter(identities)) if len(identities)==1 else None


def _relative_object_spelling_evidence(head,noun):
    """Share an actual open object slot of a completed relative predicate."""
    from reading_segments import native_relative_action,native_written_relative_action
    from semantic_roles import candidate_evidence
    relative=(native_relative_action(head)
        if head and all('ぁ'<=c<='ゖ' or c=='ー' for c in head)
        else native_written_relative_action(head))
    if not relative or 'を' in relative[1]:return None
    if relative[1]:
        from reading_segments import native_argument_relative_object_evidence
        proof=native_argument_relative_object_evidence(head,noun)
        if proof:return proof
    proof=candidate_evidence(noun,relative[0],'')
    if proof and proof.get('shared_roles'):return proof
    # A nominal action's canonical head alone omits its real suru tail.
    # Recheck the complete original predicate, binding the resulting meaning
    # to the same head; a different homophone cannot lend its object roles.
    proof=candidate_evidence(noun,head,'')
    if (proof and proof.get('shared_roles')
            and proof.get('predicate')==relative[0]):return proof
    from reading_segments import native_adverbial_reading_cuts
    for cut in native_adverbial_reading_cuts(head):
        suffix=head[cut:]
        original=(native_relative_action(suffix)
            if all('ぁ'<=c<='ゖ' or c=='ー' for c in suffix)
            else native_written_relative_action(suffix))
        if original!=relative:continue
        proof=candidate_evidence(noun,suffix,'')
        if (proof and proof.get('shared_roles')
                and proof.get('predicate')==relative[0]):return proof
    return None


def _sahen_relative_spelling_evidence(text,start,end,face):
    """Bind an emitted action's meaning to its original whole relative noun.

    Grammar establishes the unchanged reading/tail boundary independently.
    Each candidate then proves its own open object relation; the grammar's
    first homophone never receives another predicate's semantic evidence.
    """
    import morphology as M
    from reading_segments import (native_nominal_phrase_faces,_native_written_nominal_faces,
        native_attributive_predicate_end,completed_sahen_reading)
    kana=lambda value:bool(value) and all('ぁ'<=c<='ゖ' or c=='ー' for c in value)
    if start:
        from reading_segments import native_adverbial_sahen_relative_parts
        original=native_adverbial_sahen_relative_parts(text)
        if original and original[:2]==(start,end):
            proof=_sahen_relative_spelling_evidence(text[start:],0,end-start,face)
            return dict(proof,noun_start=proof['noun_start']+start) if proof else None
        scope=_argument_relative_nominal_scope(text)
        if not scope:return None
        noun_start,noun_end,nouns=scope
        from reading_segments import native_subject_sahen_action
        original=native_subject_sahen_action(text[:noun_start])
        if not original or original[:2]!=(start,end):return None
        if not any(pos.startswith('名詞,サ変接続,') and base==face and rd==text[start:end]
                   for pos,form,base,rd in M.dictionary_inflections(face) or ()):return None
        from semantic_roles import subject_candidate_evidence
        subjects=[subject_candidate_evidence(subject,face,text[end:noun_start]) for subject in original[3]]
        if not any(p and p.get('predicate')==face and p.get('shared_roles') for p in subjects):return None
        proofs=[_relative_object_spelling_evidence(face+text[end:noun_start],noun) for noun in nouns]
        if not all(p and p.get('predicate')==face and p.get('case')=='を'
                   and p.get('shared_roles') for p in proofs):return None
        return dict(predicate=face,noun_start=noun_start,noun_faces=tuple(nouns),
                    shared_roles=tuple(tuple(p['shared_roles']) for p in proofs))
    if not 2<=end<len(text)<=80 or not kana(text[:end]):return None
    rd=text[:end]
    def same_native_head(word):
        return any(pos.startswith('名詞,サ変接続,') and base==word and reading==rd
                   for pos,form,base,reading in M.dictionary_inflections(word) or ())
    if not same_native_head(face):return None
    for cut in range(end+1,len(text)):
        if not kana(text[:cut]):continue
        tail=text[cut:]
        nouns=native_nominal_phrase_faces(tail) if kana(tail) else _native_written_nominal_faces(tail)
        if not nouns or not native_attributive_predicate_end(text[:cut]):continue
        source_head=completed_sahen_reading(text[:cut],allow_nonpolite=True,
                                          return_action=True,finite_only=True)
        if not source_head or not same_native_head(source_head):continue
        # A helper argument reconstructs this face's unchanged suru tail;
        # it is not an additional generated or accepted output candidate.
        proofs=[_relative_object_spelling_evidence(face+text[end:cut],noun)
                for noun in nouns]
        if all(proof and proof.get('predicate')==face and proof.get('case')=='を'
               and proof.get('shared_roles') for proof in proofs):
            return dict(predicate=face,noun_start=cut,noun_faces=tuple(nouns),
                        shared_roles=tuple(tuple(p['shared_roles']) for p in proofs))
    return None


def _argument_relative_nominal_scope(text,nominal_parts=None):
    """The same completed source relative noun, bare or an outer object."""
    import morphology as M
    from reading_segments import native_argument_relative_nominal_parts,native_written_relative_action
    nominal_parts=nominal_parts or native_argument_relative_nominal_parts
    original=nominal_parts(text);noun_end=len(text)
    if not original:
        # An embedded relative noun keeps the same inner subject relation.
        # Its actual outer object case and complete following predicate must
        # independently fit every whole noun; do not truncate at a guessed
        # character or lend the outer predicate's role to the subject.
        from reading_segments import native_object_predicate_proof
        from semantic_roles import candidate_nominal_spelling_evidence
        if len(text)>80 or COLUMN_SEPARATOR.search(text) or any(c in text for c in '\r\n'):return None
        from reading_segments import native_case_positions,native_nominal_case_boundary
        original_parts=M.tokenize(text)
        for cut in native_case_positions(text,original_parts,('を',)):
            case_end=cut+1
            if not 0<cut<case_end<len(text):continue
            case=next((t for t in original_parts if t.start==cut and t.end==case_end),None)
            if case is not None:
                if not (case.surface=='を' and case.has_reading and case.reading=='を'
                        and case.pos=='助詞' and case.pos_sub.startswith('格助詞')
                        and any(pos.startswith('助詞,格助詞,') and reading==case.reading
                            and base==case.base_form and (form if form!='*' else '')==case.infl_form
                            for pos,form,base,reading in M.dictionary_inflections(case.surface) or ())):continue
            else:
                # A literal case inside an unknown source token needs its
                # own dictionary entry and the entire proved nominal.
                # This never splits a known word or changes a reading.
                if not any(pos.startswith('助詞,格助詞,') and reading==base=='を' and form=='*'
                           for pos,form,base,reading in M.dictionary_inflections('を') or ()):continue
            inner=nominal_parts(text[:cut])
            if not inner or inner[0]<=0:continue
            if native_nominal_case_boundary(text,original_parts,cut,'を',inner[1]) is None:continue
            # The shared object proof can also describe a connective tail.
            # This additional path requires the unchanged outer action to
            # be finite; a trailing te/de is not a completed sentence.
            tail=text[case_end:]
            if tail[-1:] in '。！？.!?':tail=tail[:-1]
            from reading_segments import completed_native_verb_reading,completed_sahen_reading
            finite=(completed_native_verb_reading(tail,True,require_roles=False,finite_only=True)
                or completed_sahen_reading(tail,allow_nonpolite=True,finite_only=True)
                if all('ぁ'<=c<='ゖ' or c=='ー' for c in tail)
                else native_written_relative_action(tail,allow_finite=True))
            if not finite:continue
            fits=True
            for noun in inner[1]:
                action=native_object_predicate_proof(text,case_end,(noun,),return_action=True)
                proof=candidate_nominal_spelling_evidence('',noun,text[cut:])
                if not (action and proof and proof.get('predicate')==action
                        and proof.get('case')=='を' and proof.get('shared_roles')):
                    fits=False;break
            if fits and inner[1]:
                original=inner;noun_end=cut;break
    return (original[0],noun_end,original[1]) if original else ()


def _subject_verb_relative_boundaries(text):
    """Share only coordinates of the same original verb and its whole noun.

    A single native lexeme must prove both the whole subject and every
    nominal face. This source proof neither emits nor picks a spelling.
    The existing outer-object scope retains its actual case and predicate.
    """
    import morphology as M
    from reading_segments import (native_nominal_phrase_faces,_native_written_nominal_faces,
        native_written_relative_action,native_relative_action,native_attributive_predicate_end,
        _native_subject_kana_verb_nominal,native_relative_nominal_cuts)
    if not text or len(text)>80 or COLUMN_SEPARATOR.search(text) or any(c in text for c in '\r\n'):return ()
    kana=lambda value:bool(value) and all('ぁ'<=c<='ゖ' or c=='ー' for c in value)
    spans={}
    def nominal_parts(source):
        from reading_segments import native_bound_relative_nominal_parts,native_progressive_bound_relative_nominal_parts,native_dictionary_relative_nominal_parts
        bound=native_bound_relative_nominal_parts(source) or native_progressive_bound_relative_nominal_parts(source) or native_dictionary_relative_nominal_parts(source)
        if bound:
            cut,nouns,start,end,prefix=bound
            spans[cut]=(start,end)
            return cut,nouns
        parts=M.tokenize(source)
        for cut in native_relative_nominal_cuts(source,parts):
            if any(t.start==cut and t.end==len(source) and t.has_reading
                   and t.pos in ('助詞','助動詞') for t in parts):continue
            tail=source[cut:]
            nouns=native_nominal_phrase_faces(tail) if kana(tail) else _native_written_nominal_faces(tail)
            if not nouns:continue
            head=source[:cut]
            relative=native_relative_action(head) if kana(head) else native_written_relative_action(head)
            if not relative or not native_attributive_predicate_end(head):continue
            if not _native_subject_kana_verb_nominal(head,relative,nouns):continue
            # The proof above validates this exact original suffix token,
            # including its dictionary reading, form, base and coordinates.
            start=len(head)-len(relative[0])
            token=next((t for t in M.tokenize(head) if t.start==start
                        and t.pos=='動詞' and t.pos_sub=='自立' and t.has_reading
                        and kana(t.surface) and t.reading==t.surface
                        and t.end==t.start+len(t.surface) and head[t.start:t.end]==t.surface),None)
            if token is None:continue
            spans[cut]=(token.start,token.end)
            return cut,tuple(nouns)
        return ()
    scope=_argument_relative_nominal_scope(text,nominal_parts=nominal_parts)
    if not scope or scope[0] not in spans:return ()
    start,end=spans[scope[0]]
    return start,end,scope[0],scope[1]


def _relative_subject_spelling_evidence(text,start,end,face):
    """A spelling's own positive subject meaning in the same source clause.

    The original whole noun, actual ga and independently completed relative
    clause own their seam. No homophone is selected by that boundary proof;
    every emitted spelling must keep its own existing nominative meaning.
    """
    import morphology as M
    from reading_segments import (native_argument_relative_nominal_parts,
        native_nominal_phrase_faces,native_relative_action,native_written_relative_action)
    if start!=0 or not 2<=end<len(text) or text[end:end+1]!='が':return None
    rd=text[:end]
    if not all('ぁ'<=c<='ゖ' or c=='ー' for c in rd):return None
    scope=_argument_relative_nominal_scope(text)
    original=(scope[0],scope[2]) if scope else ()
    if not original or original[0]<=end+1:
        from reading_segments import native_dictionary_subject_spelling
        return native_dictionary_subject_spelling(text,start,end,face)
    head=text[:original[0]]
    relative=(native_relative_action(head)
        if all('ぁ'<=c<='ゖ' or c=='ー' for c in head)
        else native_written_relative_action(head))
    if not relative or 'が' not in relative[1]:return None
    case=next((t for t in M.tokenize(text) if t.start==end and t.end==end+1),None)
    if not (case and case.has_reading and case.surface=='が' and case.reading=='が'
            and case.pos=='助詞' and case.pos_sub.startswith('格助詞')
            and any(pos.startswith('助詞,格助詞,') and reading==case.reading
                    and base==case.base_form and (form if form!='*' else '')==case.infl_form
                    for pos,form,base,reading in M.dictionary_inflections(case.surface) or ())):return None
    if face not in native_nominal_phrase_faces(rd):return None
    if not any(pos.startswith('名詞,') and reading==rd and base==face
               and not any(kind in pos for kind in ('固有名詞','接尾','非自立'))
               for pos,form,base,reading in M.dictionary_inflections(face) or ()):return None
    from semantic_roles import proved_action_case_support,nominal_roles,SUBJECT_VERB_ROLES
    if not proved_action_case_support(face,'が',relative[0],context=head):return None
    shared=nominal_roles(face) & frozenset(SUBJECT_VERB_ROLES.get(relative[0],()))
    if not shared:return None
    return dict(source='original_relative_subject',subject=face,case='が',
                predicate=relative[0],shared_roles=sorted(shared))


def _lexical_units(text,parts,nominal_members=None,action_links=None,inflected_members=None):
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
    def add_nominal_phrase(start,end,compound=False):
        # A phrase's semantic head does not make the whole phrase one word.
        # Reuse the same native boundaries for reopened and parsed cases.
        from reading_segments import native_coordinated_nominal_parts
        rd=text[start:end]
        from reading_segments import native_focused_nominal_parts
        focused=native_focused_nominal_parts(rd)
        if focused:
            # Focus belongs to grammar, not to the lexical spelling span.
            # Reuse the source noun proof and preserve the original suffix.
            add_nominal_phrase(start,start+focused[0],compound)
            return
        members=native_coordinated_nominal_parts(rd)
        if members:
            position=start
            for member in members:
                span=(position,position+len(member));units.append(span)
                if nominal_members is not None:nominal_members.add(span)
                position+=len(member)+1
            return
        modified=native_adnominal_reading_parts(rd,allow_predicative=True)
        if modified and ''.join(part[4] for part in modified)==rd:
            position=start
            for face,pos,form,base,reading in modified:
                part_end=position+len(reading)
                if pos.startswith(('名詞,','動詞,','形容詞,')):
                    units.append((position,part_end))
                    if nominal_members is not None and pos.startswith('名詞,'):
                        nominal_members.add((position,part_end))
                position=part_end
        else:
            span=(start,end);units.append(span)
            if compound:compound_units.append(span)
            if nominal_members is not None:nominal_members.add(span)
    # Reuse the original written action and complete noun reading even
    # when a guessed lexical unit crosses its actual suru/auxiliary seam.
    # This supplies ranges only; noun senses and final checks remain below.
    from reading_segments import native_written_sahen_nominal_parts
    written_nominals=native_written_sahen_nominal_parts(text)
    written_edges=tuple(edge for head,edge,faces in written_nominals)
    for head,edge,faces in written_nominals:
        add_nominal_phrase(edge,len(text))
    # A native prefix/sahen action can leave its spelling unresolved while
    # its original suru tail still proves the following whole noun boundary.
    # Share only that seam. Every noun sense and source replacement check
    # remains in project; no preceding homophone is selected here.
    from reading_segments import native_prefix_sahen_relative_parts
    prefix_nominals=native_prefix_sahen_relative_parts(text)
    prefix_edges=tuple(end for head,end,stem,faces in prefix_nominals)
    for head,end,stem,faces in prefix_nominals:
        add_nominal_phrase(end,len(text))
    # Only the complete original adjunct/relative proof can reopen these
    # seams. A bare adverb boundary does not certify a following phrase.
    from reading_segments import native_adverbial_sahen_relative_parts
    adverbial=native_adverbial_sahen_relative_parts(text)
    adverbial_edges=()
    if adverbial:
        start,end,noun_start,original_parts=adverbial
        span=(start,end);units.append(span)
        add_nominal_phrase(noun_start,len(text))
        if action_links is not None:action_links[span]=noun_start
        adverbial_edges=(start,end,noun_start)
    # A positively proved original subject/case seam cannot be swallowed
    # by a longer lexical homophone. This removes crossing units only;
    # project still generates and validates each nominal spelling itself.
    subject_edges=()
    for case in parts:
        if not (case.surface=='が' and case.pos=='助詞' and case.start>=2):continue
        if any(_relative_subject_spelling_evidence(text,0,case.start,face)
               for face in native_nominal_phrase_faces(text[:case.start])):
            add_nominal_phrase(0,case.start)
            subject_edges=(case.start,case.end);break
    # The whole subject and relative noun jointly prove the same original
    # completed sahen boundary. Neither the seam nor its grammar head picks
    # a spelling; project checks each emitted face through the common gate.
    argument_edges=()
    scope=_argument_relative_nominal_scope(text)
    if scope:
        from reading_segments import native_subject_sahen_action
        noun_start,noun_end,nouns=scope
        original=native_subject_sahen_action(text[:noun_start])
        if original:
            start,end,head,subjects=original
            span=(start,end);units.append(span)
            add_nominal_phrase(noun_start,noun_end)
            if action_links is not None:action_links[span]=noun_start
            argument_edges=(start,end,noun_start,noun_end)
    # Preserve only the same positively proved ordinary verb/noun seams.
    # All generated forms still pass their own meaning and common checks.
    verb_edges=_subject_verb_relative_boundaries(text)
    if verb_edges:
        start,end,noun_start,noun_end=verb_edges
        units.append((start,end))
        add_nominal_phrase(noun_start,noun_end)
    relative_edges=()
    relative=native_adnominal_reading_parts(text,allow_predicative=True)
    if relative:
        noun_start=len(text)-len(relative[-1][4]);head=text[:noun_start]
        action=native_relative_action(head)
        if action:
            # The independently proved finite verb and its semantically
            # fitting native noun own this boundary too. A best parse's
            # internal particle cannot split the same full nominal reading.
            add_nominal_phrase(noun_start,len(text))
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
    # A written finite predicate supplies the same boundary. Preserve its
    # actual identity/occupied cases and require an independent ordinary
    # noun with positive relative-role support; unknown suffixes and bare
    # word concatenations supply no proof. This records ranges, not faces.
    if len(text)<=80:
        from reading_segments import native_written_relative_action
        from semantic_roles import relative_action_support
        from kango_tier import usage_tier_for_reading
        for part in parts:
            cut=part.end;rd=text[cut:]
            if (cut<2 or not rd or not all('ぁ'<=c<='ゖ' or c=='ー' for c in rd)
                    or not any('一'<=c<='鿿' for c in text[:cut])):continue
            relative=native_written_relative_action(text[:cut])
            if relative and any(usage_tier_for_reading(face,rd) in (1,2)
                    and relative_action_support(face,*relative,source_head=True)
                    for face in native_nominal_phrase_faces(rd)):
                add_nominal_phrase(cut,len(text))
    # Numeric words have the same native counter evidence used by source
    # grammar. A counter ending cannot become the start of a different verb.
    starts={0}|{t.end for t in parts if t.pos=='助詞' and t.pos_sub.startswith('格助詞')}
    from reading_segments import native_predicate_link_boundaries,native_object_predicate_contexts
    # The source case can be swallowed by an unknown best-parse token.
    # Reuse the full nominal/case proof, without certifying its predicate.
    starts.update(cut for begin,cut,faces in native_object_predicate_contexts(text,True))
    # A positively proved subject-position frame owns the following whole
    # object start too. An arbitrary topic/focus particle does not.
    from reading_segments import native_preposed_object_parts
    starts.update(edge for edge,case,heads,cut,faces in native_preposed_object_parts(text,True)
        if case in ('が','は','も'))
    predicate_starts=starts|{t.start for t in parts if t.has_reading and t.pos=='動詞'}
    # Honorific grammar proves the lexical stem independently of a
    # homographic pronoun in the best parse (お + continuative + いたす).
    from reading_segments import native_honorific_stem_parts
    honorific_units=[]
    for start,end,forms in native_honorific_stem_parts(text):
        span=(start,end);units.append(span);honorific_units.append(span)
        if inflected_members is not None:inflected_members[span]=forms
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
    from reading_segments import completed_native_reading_link
    focused_starts=set()
    for edge in tuple(linked_starts):
        if text[edge:edge+1] not in ('は','も'):continue
        for origin in predicate_starts:
            if origin>=edge:continue
            original=M.tokenize(text[origin:edge+1])
            rd=''.join(p.surface if all('ぁ'<=c<='ゖ' for c in p.surface) else p.reading for p in original)
            if (all(p.has_reading for p in original) and completed_native_reading_link(rd)):
                linked_starts.add(edge+1);focused_starts.add(edge+1);break
    starts.update(linked_starts)
    # Reparse at a source-proved start, case or connective boundary.
    # A kana noun can also make the best parse mislabel its following case.
    from reading_segments import native_nominal_case_boundary
    from semantic_roles import candidate_nominal_spelling_evidence
    for start in sorted(starts):
        suffix=text[start:];native=M.tokenize(suffix)
        for cut in range(2,min(19,len(suffix))):
            if suffix[cut] not in 'がをにへでとはも':continue
            rd=suffix[:cut];faces=native_nominal_phrase_faces(rd)
            # A native verb's actual de-link is not new nominal-case
            # evidence. Retain both readings for the existing lexical and
            # meaning checks instead of marking the verb head noun-only.
            from reading_segments import completed_native_verb_reading
            if (suffix[cut]=='で' and completed_native_verb_reading(rd+'で',
                    allow_nonpolite=True,require_roles=False)):continue
            faces=tuple(face for face in faces if M.native_spelling_only(rd,face))
            boundary=native_nominal_case_boundary(suffix,native,cut,suffix[cut],faces,
                allow_known_noun=True) if faces else None
            if boundary is None:continue
            # Reopening a copula/unknown parse requires the noun's positive
            # role with the unchanged predicate, as in source case analysis.
            if boundary[1] and not any(
                    (candidate_nominal_spelling_evidence(text[:start],face,suffix[cut:]) or {})
                    .get('shared_roles') for face in faces):continue
            add_nominal_phrase(start,start+cut)
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
                if native_coordinated_nominal_parts(rd) or native_nominal_phrase_faces(rd):
                    add_nominal_phrase(start,boundary.start,compound=True)
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
    # The longest-word scan owns its cursor. A preceding grammar loop's
    # connective position must not suppress every earlier lexical unit.
    edge=0
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
            if not any(a<lo<b or a<hi<b for lo,hi in honorific_units)
            and not any(lo<a<hi<b for lo,hi in compound_units)
            # A source-proved adnominal no is not the beginning of a
            # lexical homophone crossing into its same native noun.
            and not any(a<start<b for start,end,heads in te_nominals)
            and not any(a<edge<b for edge in tuple(relative_edges)+tuple(focused_starts)+written_edges+prefix_edges+adverbial_edges+subject_edges+argument_edges+verb_edges)]


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


def _partial_relative_nominal_preserved(text,start,end,face):
    """A source normal range cannot lend its relative noun to another word.

    Only an independently proved original relative noun owns these seams.
    Check the generated spelling itself against that same whole nominal;
    unknown tails supply neither permission nor a blanket rejection.
    The source grammar remains valid and is never removed from normality.
    """
    if not 0<=start<end<=len(text) or len(text)>80:return True
    import morphology as M
    from reading_segments import (native_object_predicate_contexts,
        native_nominal_case_boundary,native_written_action_nominal_parts,
        native_nominal_phrase_faces,_native_written_nominal_faces)
    for begin,case_end,nouns in native_object_predicate_contexts(text,allow_written_predicate=True):
        case=case_end-1
        if not (start<case and begin<end):continue
        prefix=text[begin:case]
        original=native_written_action_nominal_parts(prefix)
        if not original:continue
        boundary=native_nominal_case_boundary(text[begin:],M.tokenize(text[begin:]),
            case-begin,'を',nouns)
        if boundary is None or boundary[1]:continue
        cut=begin+original[0]
        # A word spelling must not consume an independently proved noun
        # seam or use a piece outside that original constituent as support.
        if not begin<=start<end<=case or start<cut<end:return False
        candidate=text[begin:start]+face+text[end:case]
        if end<=cut:
            own=native_written_action_nominal_parts(candidate)
            mapped_cut=original[0]+len(face)-(end-start)
            if not own or own[0]!=mapped_cut or set(own[1])!=set(original[1]):return False
        else:
            nominal=candidate[original[0]:]
            if not M.native_spelling_only(text[cut:case],nominal):return False
            faces=(native_nominal_phrase_faces(nominal)
                if all('ぁ'<=ch<='ゖ' or ch=='ー' for ch in nominal)
                else _native_written_nominal_faces(nominal))
            # The unchanged head already proved each of these exact nouns.
            # Another homophone cannot borrow that noun's positive meaning.
            if not faces or any(noun not in original[1] for noun in faces):return False
    return True


def _relative_outer_spelling_proved(text,start,end,face):
    """A protected original relative noun is not a completed outer action.

    For edits inside that proved constituent, require the same actual case
    and finite outer frame, and then the candidate's own mapped whole frame.
    Unproved originals and outside edits receive no additional veto here.
    This does not revoke source normality or classify unknown words as bad.
    """
    if not 0<=start<end<=len(text) or len(text)>80:return True
    import morphology as M
    from reading_segments import (native_object_predicate_contexts,
        native_nominal_case_boundary,native_written_action_nominal_parts,
        native_nominal_phrase_faces,_native_written_nominal_faces,native_object_predicate_proof)
    from semantic_roles import candidate_nominal_spelling_evidence
    for begin,case_end,nouns in native_object_predicate_contexts(text,allow_written_predicate=True):
        case=case_end-1
        if not (start<case and begin<end):continue
        original=native_written_action_nominal_parts(text[begin:case])
        if not original:continue
        boundary=native_nominal_case_boundary(text[begin:],M.tokenize(text[begin:]),
            case-begin,'を',nouns)
        if boundary is None or boundary[1]:continue
        if not _partial_relative_nominal_preserved(text,start,end,face):return False
        scope=_argument_relative_nominal_scope(text[begin:],nominal_parts=native_written_action_nominal_parts)
        if not scope or scope!=(original[0],case-begin,original[1]):return False
        delta=len(face)-(end-start);mapped_case=case-begin+delta
        candidate=text[begin:start]+face+text[end:]
        cut=begin+original[0]
        if end<=cut:
            candidate_nouns=original[1]
        else:
            nominal=candidate[original[0]:mapped_case]
            candidate_nouns=(native_nominal_phrase_faces(nominal)
                if all('ぁ'<=ch<='ゖ' or ch=='ー' for ch in nominal)
                else _native_written_nominal_faces(nominal))
        if not candidate_nouns or any(n not in original[1] for n in candidate_nouns):return False
        source_tail=M.tokenize(text[case:]);parts=M.tokenize(candidate)
        own_tail=[t for t in parts if t.start>=mapped_case]
        if (candidate[mapped_case:]!=text[case:] or len(own_tail)!=len(source_tail)
                or not source_tail or source_tail[0].start!=0
                or any(a.start!=b.start-mapped_case or a.end!=b.end-mapped_case
                    or any(getattr(a,k)!=getattr(b,k) for k in
                        ('surface','reading','has_reading','pos','pos_sub','base_form','infl_form'))
                    for a,b in zip(source_tail,own_tail))):return False
        own_boundary=native_nominal_case_boundary(candidate,parts,mapped_case,'を',candidate_nouns)
        if own_boundary is None or own_boundary[1]:return False
        for noun in candidate_nouns:
            action=native_object_predicate_proof(candidate,mapped_case+1,(noun,),return_action=True)
            proof=candidate_nominal_spelling_evidence('',noun,candidate[mapped_case:])
            if not (action and proof and proof.get('predicate')==action
                    and proof.get('case')=='を' and proof.get('shared_roles')):return False
    return True


def _relative_source_parts(text,parts):
    """Use a proved original segmentation, retaining its literal auxiliary.

    This is not a repaired-reading parse. The source prefix, whole noun,
    case and outer finite action all keep their own positive evidence.
    Candidate spellings still undergo their own inflection and C checks.
    """
    import morphology as M
    from reading_segments import native_bound_relative_nominal_parts,native_progressive_bound_relative_nominal_parts,native_dictionary_relative_nominal_parts
    proofs={}
    def nominal_parts(source):
        proof=native_bound_relative_nominal_parts(source) or native_progressive_bound_relative_nominal_parts(source) or native_dictionary_relative_nominal_parts(source)
        if proof:proofs[proof[0]]=proof;return proof[:2]
        return ()
    scope=_argument_relative_nominal_scope(text,nominal_parts=nominal_parts)
    if not scope or scope[0] not in proofs:return parts,()
    cut,nouns,start,end,prefix=proofs[scope[0]]
    suffix=M.tokenize(text[cut:])
    if not (suffix and suffix[0].start==0 and suffix[-1].end==len(text)-cut
            and all(t.has_reading and text[cut+t.start:cut+t.end]==t.surface for t in suffix)
            and all(a.end==b.start for a,b in zip(suffix,suffix[1:]))):return parts,()
    rebuilt=list(prefix)+[M.Token(t.surface,t.pos,t.base_form,t.reading,t.start+cut,t.end+cut,
        t.has_reading,t.pos_sub,t.infl_form) for t in suffix]
    return rebuilt,(start,end,cut,scope[1])


def _dictionary_relative_spelling_evidence(text,start,end,face):
    """A candidate must own the source word's proved finite alternative."""
    import morphology as M
    from reading_segments import (native_nominal_phrase_faces,_native_written_nominal_faces,
        _native_subject_kana_verb_nominal)
    parts,edges=_relative_source_parts(text,M.tokenize(text))
    if not edges or edges[:3]!=(start,end,end):return False
    verb=next((t for t in parts if t.start==start and t.end==end),None)
    if not (verb and verb.pos=='動詞' and verb.pos_sub=='自立'
            and verb.infl_form=='基本形'):return False
    noun=text[end:edges[3]]
    nouns=(native_nominal_phrase_faces(noun)
        if all('ぁ'<=c<='ゖ' or c=='ー' for c in noun)
        else _native_written_nominal_faces(noun))
    return _native_subject_kana_verb_nominal(text[:end],(text[start:end],('が',)),nouns,
        source_parts=[t for t in parts if t.end<=end],candidate_face=face)


def project(text,store,index,decisions=None,partial=False):
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

    # Keep independently proved original noun boundaries after spelling
    # an earlier modifier. A mixed-script best parse cannot erase that proof.
    source_nominals=set()
    _lexical_units(text,M.tokenize(text),source_nominals)
    # Each accepted step consumes at least one complete kana lexical unit.
    # Written units cannot be rewritten on a subsequent step.
    for _ in range(len(text)//2):
        parts,rebound_edges=_relative_source_parts(current,M.tokenize(current))
        options=[];nominal_members=set();action_context={};argument_support={}
        argument_context={}
        action_links={};inflected_members={}
        units=_lexical_units(current,parts,nominal_members,action_links,inflected_members)
        from reading_segments import native_prefix_sahen_relative_parts
        prefix_relatives=native_prefix_sahen_relative_parts(current)
        mapped={original_offset(pos):pos for pos in range(len(current)+1)}
        for lo,hi in source_nominals:
            if lo in mapped and hi in mapped:
                span=(mapped[lo],mapped[hi])
                if span[0]<span[1]:units.append(span);nominal_members.add(span)
        grammatical_links=[]
        from contextual_repair import _allows_grammatical_tail,_native_te_auxiliary_tail
        for i,head in enumerate(parts):
            if not (head.has_reading and head.pos in ('動詞','形容詞')):continue
            edge=head.end;auxiliary_edge=None
            for tail in parts[i+1:]:
                if not (tail.start==edge and tail.has_reading and (tail.pos=='助動詞'
                        or tail.pos=='助詞' and tail.pos_sub.startswith('接続助詞')
                        or tail.pos=='動詞' and tail.pos_sub=='非自立')):break
                if tail.pos=='動詞' and auxiliary_edge is None:auxiliary_edge=edge
                edge=tail.end
            if edge==head.end:continue
            forms=tuple(row for row in M.dictionary_inflections(head.surface) or ()
                if row[0].startswith(head.pos+',') and row[1]==head.infl_form and row[3]==head.reading)
            # Only the same native te/de chain may extend the old seam.
            # If it is unproved, keep the original auxiliary/particle prefix.
            if auxiliary_edge is not None and not _native_te_auxiliary_tail(
                    forms,current[head.end:edge],head.reading,head.surface):
                edge=auxiliary_edge
            from reading_segments import _native_open_predicate
            if forms and (_allows_grammatical_tail(forms,current[head.end:edge],head.reading,head.surface)
                    or edge==len(current) and _native_open_predicate(
                        current[head.start:edge],head.surface,current[:head.start])):
                grammatical_links.append((head.start,head.end,edge))
        # An actual sahen noun plus its native suru/auxiliary connection
        # owns the same seam as an inflected verb. A generated prefix+noun
        # cannot absorb suru while leaving the proved auxiliary stranded.
        sahen_links=[]
        for lo,begin in units:
            actions=native_bare_action_faces(current[lo:begin])
            if not actions:continue
            # A whole native action establishes its own following suru
            # boundary. The best kana parse may absorb that suru into a
            # different verb; it cannot be the sole source of this seam.
            suffix_parts=M.tokenize(current[begin:])
            if not suffix_parts:continue
            head=suffix_parts[0]
            if not (head.start==0 and head.has_reading and head.pos=='動詞'
                    and head.base_form=='する'):continue
            edge=head.end
            for tail in suffix_parts[1:]:
                if not (tail.start==edge and tail.has_reading and (tail.pos=='助動詞'
                        or tail.pos=='助詞' and tail.pos_sub.startswith('接続助詞'))):break
                edge=tail.end
            if edge==head.end:continue
            edge+=begin
            if completed_sahen_reading(current[lo:edge],allow_nonpolite=True,
                    allow_open_tail=True,return_action=True) not in actions:continue
            sahen_links.append((lo,begin,edge))
            grammatical_links.append((begin,begin+head.end,edge))
        # A longer nominal lookup cannot absorb only part of an attested
        # verb's auxiliary. The actual native head and complete connection
        # own this seam; a complete independent word remains intact.
        units=[(lo,hi) for lo,hi in units if (lo,hi) in nominal_members or not (
            any(lo==begin and head_end<hi<=edge for begin,head_end,edge in grammatical_links)
            or any(lo==start and begin<hi<edge for start,begin,edge in sahen_links))]
        from reading_segments import native_genitive_nominal_splits
        # Whole native auxiliaries own their interior, even if an alternate
        # nominal parser finds a familiar word starting at the last kana.
        # A token boundary can still be reconsidered by the existing full-word
        # grammar; an interior is never an independent spelling boundary.
        auxiliary_interiors=tuple((t.start,t.end) for t in parts
            if t.has_reading and t.pos=='助動詞' and t.end-t.start>1
            and any(lo<=t.start and t.end<=hi for lo,head_end,hi in grammatical_links))
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
                    # Only the independently proved full relative noun can
                    # disambiguate an adverb spanning its literal auxiliary.
                    if rebound_edges and a<rebound_edges[2]<z:continue
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
            # The anomaly detector already recognizes intentional colloquial
            # spellings. A partial homophone must not undo that source fact.
            expressive=E._colloquial_adjective_ending(match.group())
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
                    if expressive and (start!=match.start() or end!=match.end()):continue
                    if any(lo<start<hi or lo<end<hi for lo,hi in auxiliary_interiors):continue
                    rd=current[start:end];remembered=remembered_surface(rd)
                    if any(start<hi and lo<end and not (start==lo and end==head_end)
                           and not (start<lo and (start,end) in units)
                           for lo,head_end,hi in grammatical_links):
                        boundary=next((t for t in parts if t.start==end),None)
                        nominal_slot=bool(boundary and boundary.has_reading and boundary.pos=='助詞'
                            and boundary.surface!='と' and (boundary.pos_sub.startswith('格助詞')
                                or boundary.pos_sub=='連体化' or boundary.pos_sub=='係助詞' and boundary.surface in ('は','も')))
                        if not ((start,end) in units and (nominal_slot or (start,end) in nominal_members or (start,end) in action_links
                                or end==len(current) and (native_written_sahen_relative(current[:start])
                                    or start in native_predicate_link_boundaries(current,0)))
                                and native_nominal_phrase_faces(rd)):continue
                    # A single source-proved action owns its して seam, even
                    # when a longer accidental token overlaps that head.
                    unique_head_face=None
                    if (start==0 and current.startswith(rd+'して')
                            and action_links.get((start,end))==end+2
                            and text.startswith(rd+'して')):
                        from reading_segments import _native_action_note_heads,native_source_action_heads
                        faces=tuple(native_bare_action_faces(rd))
                        proved_heads=_native_action_note_heads(text,allow_predicate=True)
                        following_heads=(native_bare_action_faces(text[end+2:])
                            or native_source_action_heads(text[end+2:]))
                        if (len(proved_heads)==1 and proved_heads[0] in faces
                                and (len(faces)==1 or len(following_heads)==1)):
                            unique_head_face=proved_heads[0]
                    # A restored whole action and its literal suru stem
                    # own this seam, even when a guessed internal noun
                    # crosses it. The following complete noun is proved too.
                    prefix_faces={face for head,edge,stem,faces in prefix_relatives
                        if start==0 and end==head for face in faces}
                    prefix_stems={stem for head,edge,stem,faces in prefix_relatives
                        if start==0 and end==head}
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
                        if not proved and prefix_faces:
                            proved=all(start<lo<end and hi-end in prefix_stems
                                       for lo,hi in overlaps)
                        if not proved:continue
                    protected_hits=[(lo,hi) for lo,hi in protected
                        if start<hi and lo<end]
                    native_link=False
                    if protected_hits and (start,end) in units and all(
                            lo<start<hi for lo,hi in protected_hits) and (native_bare_action_faces(rd)
                            or any(p.startswith('動詞,自立,') and r==rd
                                for p,f,b,r in M.dictionary_inflections(rd) or ())):
                        from reading_segments import native_predicate_link_boundaries
                        link_origins={0}|{p.end for p in parts if p.pos=='助詞'
                            and p.pos_sub.startswith('格助詞')}
                        native_link=any(start in native_predicate_link_boundaries(current,origin)
                            for origin in link_origins)
                    # The same source proof outranks an internal adverb
                    # or bad exact POS parse.
                    note_head=bool(unique_head_face and protected_hits
                        and all(start<=lo<hi<=end+2 for lo,hi in protected_hits))
                    prefix_head=bool(prefix_faces and protected_hits
                        and all(start<lo<end and hi-end in prefix_stems
                                for lo,hi in protected_hits))
                    # The original complete suru tail and following whole noun
                    # own their common seam even if a best-parse adverb crosses
                    # it. A protected word inside the noun retains its meaning
                    # check; the preceding action spelling is not selected here.
                    prefix_noun=bool(protected_hits and (start,end) in nominal_members
                        and end==len(current) and any(edge==start and all(
                            head<=lo<start<hi<=end for lo,hi in protected_hits)
                            for head,edge,stem,faces in prefix_relatives))
                    # A guessed functional suffix cannot absorb an existing
                    # independent finite verb with its own object meaning.
                    # The same narrow proof is checked again for each face.
                    local_verb=False
                    if protected_hits and (start,end) in units:
                        from contextual_repair import independently_spelled_object_verb
                        local_verb=any(independently_spelled_object_verb(current,start,end,sf)
                            for sf in native_lexical_reading_faces(rd))
                    # A whole source adverb may have a separately attested
                    # finite verb parse. Its full subject/noun/outer-case proof
                    # owns only this exact span; each face is rechecked below.
                    source_verb=bool(rebound_edges and rebound_edges[:3]==(start,end,end)
                        and (start,end) in units and protected_hits
                        and all((lo,hi)==(start,end) for lo,hi in protected_hits))
                    if (protected_hits
                            and not (note_head or prefix_head or prefix_noun or local_verb or source_verb or (start,end) in units and
                                (native_written_sahen_relative(current[:start]) or native_link))):
                        from semantic_roles import candidate_nominal_spelling_evidence
                        if not ((start,end) in units and any(
                                candidate_nominal_spelling_evidence(current[:start],face,current[end:])
                                or (start,end) in nominal_members and end==len(current)
                                    and _relative_object_spelling_evidence(current[:start],face)
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
                    nominal=tuple(dict.fromkeys(native_nominal_spelling_faces(rd) or native_nominal_phrase_faces(rd))) if noun_slot else ()
                    next_token=next((t for t in parts if t.start==end),None)
                    explicit_nominal=bool(nominal and ((start,end) in nominal_members or next_token and next_token.pos=='助詞'
                        and (next_token.pos_sub.startswith('格助詞') or next_token.pos_sub=='連体化'))
                        and not ((start,end) not in nominal_members and finite and len(hit)==1 and hit[0].has_reading
                            and hit[0].start==start and hit[0].end==end
                            and hit[0].pos=='名詞' and hit[0].pos_sub.startswith('非自立')))
                    # A kana noun homograph before de can also be the
                    # native euphonic verb/link (e.g. an omitted argument).
                    # Its independent inflection proof survives a nominal
                    # best parse; spelling alone cannot choose the noun sense.
                    from reading_segments import completed_native_verb_reading
                    ambiguous_link=bool(next_token and next_token.surface in ('て','で')
                        and next_token.has_reading and next_token.pos=='助詞'
                        and completed_native_verb_reading(rd+next_token.surface,
                            allow_nonpolite=True,require_roles=False))
                    if ambiguous_link and explicit_nominal and not remembered:continue
                    action_note=bool((not after or after.startswith('して')) and
                        (start==0 or current[:start].endswith('して')))
                    # An actual open polite auxiliary can establish its
                    # unchanged sahen head; a bare unfinished suru cannot.
                    from reading_segments import native_polite_auxiliary_chains
                    actions=tuple(native_bare_action_faces(rd))
                    action_unit=bool(actions and (
                        (start,end) in action_links
                        or completed_sahen_reading(rd+after,allow_nonpolite=True,return_action=True) in actions
                        or any(a>=end and b==len(current) for a,b,sig in
                            native_polite_auxiliary_chains(current,include_open=True))
                        and completed_sahen_reading(rd+after,allow_nonpolite=True,
                            return_action=True,allow_open_tail=True) in actions
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
                    # Missing meaning data is not negative evidence against
                    # another ordinary native noun with the same reading.
                    # A known role for just one of them cannot choose the sense.
                    native_nominals={f for f in (*nominal,*native_lexical_reading_faces(rd))
                        if any(E.is_kanji(c) for c in f) and K.usage_tier_for_reading(f,rd)!=3
                        and any(p.startswith(('名詞,一般,','名詞,サ変接続,')) and r==rd
                                for p,frm,b,r in M.dictionary_inflections(f) or ())}
                    best_nominal_tier=min((K.usage_tier_for_reading(f,rd) or 3 for f in native_nominals),default=3)
                    ordinary_nominals={f for f in native_nominals
                        if (K.usage_tier_for_reading(f,rd) or 3)==best_nominal_tier}
                    unknown_sense=(explicit_nominal and not action_unit and len(ordinary_nominals)>1
                                   and any(not nominal_roles(f) for f in ordinary_nominals))
                    # A focus particle supplies a noun boundary, not a sense.
                    # Reopening that boundary must retain the short reading's
                    # real dictionary alternatives before familiarity omits
                    # unassessed spellings. Use the unchanged following case
                    # and predicate for positive context, never the focus alone.
                    from reading_segments import native_focused_nominal_parts
                    focused_tail=None
                    if explicit_nominal and not action_unit and 2<=len(rd)<=3:
                        for edge in range(1,min(5,len(after))+1):
                            focused=native_focused_nominal_parts(rd+after[:edge])
                            if focused and focused[0]==len(rd):
                                focused_tail=after[edge:]
                                break
                    unresolved_focus=(focused_tail is not None and len(native_nominals)>1
                        and not any(candidate_nominal_spelling_evidence(current[:start],f,focused_tail)
                                    for f in native_nominals))
                    # A known common spelling is not evidence that an
                    # unclassified same-reading adjective sense is rare.
                    # Keep kana unless an explicit choice resolves the sense.
                    adjective_senses={base for alternative in faces
                        for pos,form,base,reading in M.dictionary_inflections(alternative) or ()
                        if pos.startswith('形容詞,自立,') and reading==rd
                        # The unchanged kana spelling is not another sense.
                        and any(E.is_kanji(c) for c in base)
                        and K.usage_tier_for_reading(base,rd)!=3}
                    # Explicitly evaluated alternatives may differ in ordinary
                    # use. Unknown alternatives remain unknown and block this
                    # shortcut; absence from the roster never means rare.
                    adjective_tiers={base:K.usage_tier_for_reading(base,rd) for base in adjective_senses}
                    if adjective_tiers and all(tier is not None for tier in adjective_tiers.values()):
                        best_adjective_tier=min(adjective_tiers.values())
                        adjective_senses={base for base,tier in adjective_tiers.items() if tier==best_adjective_tier}
                    for face in dict.fromkeys(faces):
                        if source_verb and not _dictionary_relative_spelling_evidence(current,start,end,face):continue
                        if prefix_head and face not in prefix_faces:continue
                        if (unknown_sense or unresolved_focus) and face!=remembered:continue
                        if face==rd or not any(E.is_kanji(c) or E.is_katakana(c) for c in face):continue
                        from familiar_spelling import prefers_kana
                        if face!=remembered and prefers_kana(face,rd,current[:start],after):continue
                        if decisions is not None and decisions.blocks(rd,face):continue
                        from general_words import sourced_common_noun_evidence
                        forms=tuple(M.dictionary_inflections(face) or ())+tuple(
                            (entry['pos'],'*',face,entry['reading'])
                            for entry in sourced_common_noun_evidence(face,rd))
                        # Reuse the exact restored compound's native sahen
                        # proof, without adding a synthetic dictionary row.
                        compound_reading=M.native_sahen_compound_reading(face)
                        if compound_reading==rd:
                            forms+= (('名詞,サ変接続,*,*','*',face,compound_reading),)
                        viable=[];frame_bases=set();frame_support=set();argument_proofs=set()
                        for pos,form,base,reading in forms:
                            proved_arguments=frozenset()
                            if reading!=rd or '固有名詞' in pos:continue
                            if '非自立' in pos:
                                from familiar_spelling import person_reference
                                if not (rd=='もの' and face=='者' and person_reference(current[:start],after)):continue
                            inflected=inflected_members.get((start,end))
                            if inflected and not any(pos==p and form==f and reading==r
                                    for p,f,b,r in inflected):continue
                            # A native adverbial noun can denote time/order as well
                            # as an object; a merely homophonic concrete noun loses it.
                            if (any(p.startswith('名詞,副詞可能,') and r==rd for p,f,b,r in M.dictionary_inflections(rd) or ())
                                    and not any(p.startswith('名詞,副詞可能,') and r==rd for p,f,b,r in forms)
                                    and not (explicit_nominal and nominal_roles(rd) & nominal_roles(face)
                                        and candidate_nominal_spelling_evidence(current[:start],face,after))):continue
                            if not pos.startswith(('名詞,','動詞,自立,','形容詞,自立,','連体詞,')):continue
                            if explicit_nominal and pos.startswith(('動詞,','形容詞,')):continue
                            if pos.startswith('形容詞,'):
                                if (len(adjective_senses)>1 or adjective_senses and base not in adjective_senses) and face!=remembered:continue
                                # A bare adjectival stem cannot become a finished
                                # written word merely because its lemma is common.
                                if form=='ガル接続' and not (next_token and next_token.has_reading
                                        and (next_token.pos=='名詞' and next_token.pos_sub.startswith('接尾')
                                             and next_token.surface in ('さ','み','げ')
                                             or next_token.pos=='動詞' and next_token.base_form=='がる')):continue
                            deverbal=face in native_deverbal_nominal_faces(rd) and face in whole and hit[0].pos=='動詞' and hit[0].infl_form=='連用形'
                            counter=bool(start and current[start-1].isdigit() and pos.startswith('名詞,接尾,助数詞,'))
                            # A dictionary token inside an unexplained kana chain
                            # does not prove a noun phrase. Require a grammatical
                            # edge or the independently attested complete nominal.
                            nominal_edge=start==0 or bool(preceding and preceding.pos=='助詞') or genitive or finite
                            nominal_tail=not after or case
                            if pos.startswith('名詞,') and not (counter or face in whole or nominal_edge and nominal_tail):
                                from reading_segments import native_adverbial_stem_spelling
                                if not (pos.startswith('名詞,形容動詞語幹,')
                                        and native_adverbial_stem_spelling(current,start,end,face)):continue
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
                                and (hit[0].infl_form=='基本形' or (start,end) in nominal_members
                                     and candidate_nominal_spelling_evidence(current[:start],face,after)) and next_token
                                and next_token.pos=='助詞'
                                and (next_token.surface=='を' and next_token.pos_sub.startswith('格助詞')
                                    or next_token.surface=='と' and (start,end) in nominal_members
                                    and candidate_nominal_spelling_evidence(current[:start],face,after)))
                            genitive_noun_slot=bool(exact and hit[0].pos=='動詞'
                                and hit[0].infl_form=='連用形' and next_token
                                and next_token.surface=='の' and next_token.pos=='助詞'
                                and next_token.pos_sub=='連体化')
                            # Independently completed sahen morphology owns
                            # the source noun even if the best kana split is
                            # a homographic verb. Keep its literal suru tail.
                            if exact and not inflected and not deverbal and not (action_unit and face in actions) and not (explicit_nominal and face in whole
                                    and (hit[0].pos=='名詞'
                                        and (not hit[0].pos_sub.startswith(('非自立','代名詞')) or (start,end) in nominal_members)
                                        or object_noun_slot or genitive_noun_slot)):
                                t=hit[0]
                                if not counter and not pos.startswith(t.pos+','+(t.pos_sub.replace(':',',')+',' if t.pos_sub else '')) and face!=unique_head_face:continue
                                if t.pos in ('動詞','形容詞') and form!=t.infl_form and face!=unique_head_face:continue
                                if t.pos=='連体詞' and not any(p.startswith(('名詞,','形容詞,')) for p,f,b,r in forms):continue
                            original_roles=nominal_roles(rd)
                            # The actual human-only argument selects the person
                            # sense of mono, not its generic object dictionary role.
                            from familiar_spelling import person_reference
                            if rd=='もの' and person_reference(current[:start],after):
                                original_roles=frozenset(('person',))
                            if original_roles and not inflected and not original_roles & nominal_roles(face):continue
                            tier=(K.native_inflection_usage_tier(face,pos,form,base,rd)
                                if pos.startswith(('動詞,自立,','形容詞,自立,'))
                                else K.usage_tier_for_reading(base,rd))
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
                                    if not (obj or arg or sub):
                                        from semantic_roles import following_shared_object
                                        obj=following_shared_object(current,start,end)
                                else:obj=arg=sub=None
                                # A newly admitted single-kana stem cannot treat
                                # an unrecognized explicit argument as no argument.
                                if (end==start+1 and face!=remembered and preceding
                                        and preceding.pos=='助詞'
                                        and preceding.pos_sub.startswith('格助詞')
                                        and not (obj or arg or sub)):continue
                                neutral_time=False
                                from contextual_repair import independently_spelled_object_verb
                                local_proof=(independently_spelled_object_verb(current,start,end,face)
                                    if not (obj or arg or sub) else None)
                                if not (obj or arg or sub or local_proof) and (end,len(current)) in nominal_members:
                                    from reading_segments import _native_written_nominal_faces
                                    # The already written whole noun supplies its
                                    # own object sense. Do not choose a kana noun
                                    # homophone merely to justify this verb face.
                                    if _native_written_nominal_faces(after)==(after,):
                                        local_proof=_relative_object_spelling_evidence(current[:start]+face,after)
                                if obj or arg or sub or local_proof:
                                    scoped=[]
                                    if local_proof:scoped.append((('relative',start,end),local_proof))
                                    if obj:scoped.append((('object',obj,'を'),candidate_evidence(obj,face,after,current[:start])))
                                    if arg:scoped.append((('case',arg[0],arg[1]),candidate_evidence(arg[0],face,after,current[:start],case=arg[1])))
                                    if sub:scoped.append((('subject',sub,'が'),subject_candidate_evidence(sub,face,after)))
                                    proof=[p for _,p in scoped]
                                    proved_arguments=frozenset(scope for scope,p in scoped if p and p.get('shared_roles'))
                                    if not any(p and p.get('shared_roles') for p in proof):continue
                                    # An unspelled kana noun may still denote multiple
                                    # written senses. One sense cannot lend its argument
                                    # role to an incompatible or unclassified homophone.
                                    if obj and all('ぁ'<=c<='ゖ' or c=='ー' for c in obj):
                                        # The literal kana noun can have its own
                                        # classified sense (e.g. generic もの).
                                        # A reverse-spelled homophone must not
                                        # erase that independent source proof.
                                        source_roles=nominal_roles(obj)
                                        direct_support=source_roles & set((proof[0] or {}).get('predicate_roles',()))
                                        if not direct_support:
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
                                if (not (obj or arg or sub or local_proof) or neutral_time) and face!=remembered:
                                    from contextual_repair import _modern_euphonic_link,_modern_te_allowed
                                    link=(_modern_euphonic_link(next_token.surface,
                                        next_token.pos+':'+next_token.pos_sub,next_token.infl_form)
                                        if neutral_time and next_token and next_token.start==end else None)
                                    # Origin usage makes an attested potential
                                    # form usable, but does not choose that new
                                    # lemma over a different unclassified homophone
                                    # without an argument or relative relation.
                                    # Only a judgment of the actual lemma resolves
                                    # this source-neutral ambiguity. Inflections of
                                    # that same lemma keep their direct judgment;
                                    # positive context and explicit choice are above.
                                    senses={(b,K.usage_tier_for_reading(b,r))
                                        # Use the same actual inflected forms as
                                        # candidate generation. A short reading's
                                        # nominal lookup may omit every written verb.
                                        for f in (*native_lexical_reading_faces(rd),
                                            *index.inflected_surfaces_for_reading(rd))
                                        for p,frm,b,r in M.dictionary_inflections(f) or ()
                                        if p.startswith('動詞,自立,') and frm==form and r==rd
                                        and any(E.is_kanji(c) for c in b)
                                        and (link is None or _modern_te_allowed(f,r,link) is not False)}
                                    # A source-neutral inflection retains the same
                                    # explicit ordinary-use evidence as repair
                                    # ranking. An unjudged rival cannot erase that
                                    # positive fact; it remains unjudged, not rare.
                                    # Equal positive senses (or no positive usage)
                                    # still stay ambiguous. Argument/choice proof
                                    # is handled above and is never overridden here.
                                    positive=[tier for b,tier in senses if tier in (1,2)]
                                    best=min(positive) if positive else None
                                    bases={''.join(c for c in b if E.is_kanji(c))
                                           for b,tier in senses if best is None or tier==best}
                                    if (len(bases)>1 or ''.join(c for c in base if E.is_kanji(c)) not in bases):continue
                            if ordinary:
                                viable.append(tier or 3)
                                if proved_arguments:argument_proofs.add(proved_arguments)
                        if not viable and not (face in whole and not forms and not exact):continue
                        if not viable and face in whole:
                            # A proved nominal compound retains the same
                            # explicit familiarity of each native component.
                            tier=K.candidate_usage_tier(face,rd)
                            if tier is not None:viable.append(tier)
                        proposed=current[:start]+face+after
                        if not M.native_spelling_only(current,proposed):continue
                        emitted=M.tokenize(face)
                        usual=''.join(t.reading for t in emitted if t.has_reading)
                        if (face!=remembered and all(t.has_reading for t in emitted)
                                and not E._adj_ok_one_char(rd,usual,'kana')):continue
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
                            if (face in whole and face in nominal or any(pos.startswith('名詞,') and reading==rd for pos,form,base,reading in forms)) else None)
                        if not nominal_support and explicit_nominal:
                            nominal_support=_relative_subject_spelling_evidence(current,start,end,face)
                        # A productive count is not the only native sense
                        # when this exact reading also names a country.
                        # The ordinary noun inventory omits proper nouns;
                        # that omission cannot choose the quantity. Keep
                        # a concrete original relation or explicit choice,
                        # otherwise preserve the unresolved kana reading.
                        if face!=remembered and not nominal_support:
                            from reading_segments import native_counted_nominal_evidence
                            if native_counted_nominal_evidence(face):
                                from context_meaning import _native_country_readings,nominal_spelling_context_evidence as source_meaning_evidence
                                countries=_native_country_readings().get(rd,())
                                if (any(M.native_spelling_only(rd,country) for country in countries)
                                        and not source_meaning_evidence(current,start,end,face)):continue
                        # Rejecting a familiar noun's context must not leave
                        # an unjudged homophone as an automatic spelling winner.
                        # An explicit choice or a positive sense relation can
                        # still establish that alternative; otherwise keep kana.
                        if (explicit_nominal and not action_unit and face!=remembered
                                and ordinary_nominals and face not in ordinary_nominals
                                and K.candidate_usage_tier(face,rd) is None
                                and not nominal_support):continue
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
                        if action_unit and face in actions and action_links.get((start,end))==end+2:
                            from semantic_roles import object_before,candidate_evidence
                            if start not in argument_context:
                                argument_context[start]=(object_before(current,start,tok),None,None)
                            obj=argument_context[start][0]
                            if obj:
                                proof=candidate_evidence(obj,face,after,current[:start])
                                action_role=bool(proof and proof.get('shared_roles'))
                        if action_unit and face in actions and not action_role:
                            action_role=bool(_sahen_relative_spelling_evidence(current,start,end,face))
                        if (overlaps and not action_role and face!=remembered
                                and face!=unique_head_face and face not in prefix_faces):continue
                        if argument_proofs:argument_support[start,end,face]=frozenset(argument_proofs)
                        options.append(((-(end-start),int(face!=remembered),-bool(nominal_support),
                            -bool(nominal_support and nominal_support.get('coordinated_shared_roles')),
                            -action_role,min(viable or [3]),M.path_cost(proposed),face),
                                        (start,end,face),
                                        (frozenset(frame_bases),frozenset(frame_support)) if frame_support else None))
        # The source can already express the proved meaning in kana.
        # Complete its spelling here without declaring a structural error.
        from context_meaning import contexts,candidates,_expected_role,_meaning_roles
        from literal_examples import protected_ranges,overlaps as overlaps_literal
        literal=protected_ranges(current)
        for frame in contexts(current):
            if not frame.get('reading_spelling') or _expected_role(frame) not in _meaning_roles(frame):continue
            start,end=frame['start'],frame['end'];rd=current[start:end]
            if overlaps_literal(start,end,literal):continue
            remembered=remembered_surface(rd)
            for face in candidates(frame):
                if face==rd or not any(E.is_kanji(c) or E.is_katakana(c) for c in face):continue
                if remembered and face!=remembered:continue
                from familiar_spelling import prefers_kana
                if not remembered and prefers_kana(face,rd,current[:start],current[end:]):continue
                proposed=current[:start]+face+current[end:]
                if not M.native_spelling_only(current,proposed):continue
                from ime_spelling import _reinterprets_function_attachment
                if _reinterprets_function_attachment(current,start,end,face):continue
                accepted,_=E._check_replacement(current,(start,end,face,'かな入力'),store,tok,index,decisions,
                    conv_taken=((start,end),),spelling=True)
                if accepted is None or tuple(accepted[:3])!=(start,end,face):continue
                import oddness
                if oddness.structural_anomaly_in_range(proposed,start,start+len(face),tok,store,index):continue
                options.append(((-(end-start),int(face!=remembered),-1,0,0,
                    K.candidate_usage_tier(face) or 3,M.path_cost(proposed),face),(start,end,face),None))
        # Different ordinary senses with equal source/meaning evidence
        # remain an unresolved reading. Cost or the first IME result cannot
        # make that spelling decision on an otherwise unchanged lexical unit.
        # A remembered choice or a stronger concrete relation still wins.
        # A normal source noun/case is not proof of the candidate's outer
        # action. Apply its own completed frame before either spelling mode.
        outer_proved=[]
        for item in options:
            a,b,face=item[1];lo,hi=original_offset(a),original_offset(b)
            if lo is None or hi is None:continue
            if _relative_outer_spelling_proved(text,lo,hi,face):outer_proved.append(item)
        options=outer_proved
        if partial:
            from reading_segments import (native_context_ranges,native_dictionary_subject_spelling,
                native_dictionary_relative_retention)
            from contextual_repair import independently_spelled_object_verb,_legacy_source_changes
            normal=native_context_ranges(text)
            original_changes=_legacy_source_changes(text,result,E,trim_context=False)
            retained=[]
            for item in options:
                a,b,face=item[1];lo,hi=original_offset(a),original_offset(b)
                if lo is None or hi is None:continue
                if not _partial_relative_nominal_preserved(text,lo,hi,face):continue
                if (any(x<=lo<hi<=y for x,y in normal)
                        or independently_spelled_object_verb(text,lo,hi,face)
                        or native_dictionary_subject_spelling(text,lo,hi,face)
                        or native_dictionary_relative_retention(text,original_changes,lo,hi,face)):
                    retained.append(item)
            options=retained
        # A positive relation between both source actions distinguishes
        # homophones before unresolved equal-evidence senses are discarded.
        # The same evidence used for final ranking must also reach this gate.
        options=[(key[:4]+(-action_context.get(change,0),)+key[4:],change,proof)
                 for key,change,proof in options]
        grouped={}
        for item in options:grouped.setdefault(item[1][:2],[]).append(item)
        # Keep separately proved source arguments, not just their union of
        # role labels. With the same stronger source/choice evidence, a face
        # supported by both original cases dominates one supported by only
        # a subset. Unknown roles stay unknown; incomparable proofs, or a
        # candidate without a competing fuller proof, are not rejected.
        # Never combine different dictionary analyses into one proof.
        dominated=set()
        for group in grouped.values():
            for key,change,_ in group:
                own=argument_support.get(change,())
                if not own:continue
                for other_key,other_change,_ in group:
                    if other_change==change or key[1:4]!=other_key[1:4]:continue
                    other=argument_support.get(other_change,())
                    if other and all(any(a<b for b in other) for a in own):
                        dominated.add(change);break
        options=[item for item in options if item[1] not in dominated]
        grouped={}
        for item in options:grouped.setdefault(item[1][:2],[]).append(item)
        # A restored prefix compound must not hide its independently
        # judged lexical head. Compare only already accepted faces with
        # identical stronger source/choice/meaning evidence and the same
        # native prefix. No whole-compound tier is manufactured, and an
        # unknown head or a direct whole judgment keeps the usual ranking.
        usage_dominated=set()
        for (start,end),group in grouped.items():
            peers={}
            for item in group:peers.setdefault(item[0][:6],[]).append(item)
            for same_context in peers.values():
                faces={item[1][2] for item in same_context}
                if any(K.candidate_usage_tier(face,current[start:end]) is not None
                       for face in faces):continue
                tiers=K.shared_prefixed_sahen_usage(faces,current[start:end])
                if tiers:
                    best=min(tiers.values())
                    usage_dominated.update(item[1] for item in same_context
                                           if tiers[item[1][2]]>best)
        options=[item for item in options if item[1] not in usage_dominated]
        grouped={}
        for item in options:grouped.setdefault(item[1][:2],[]).append(item)
        ambiguous=[];equivalent={}
        for (start,end),group in grouped.items():
            proof=min(item[0][:7] for item in group)
            tied=[item for item in group if item[0][:7]==proof]
            tied_senses={item[1][2] for item in tied}
            if len(tied_senses)>1:
                identities={_native_inflected_identity(face,current[start:end])
                            for face in tied_senses}
                if None not in identities and len(identities)==1:
                    # Prefer the attested full okurigana spelling within the
                    # same lexeme. Different kanji/lemmas remain ambiguous.
                    equivalent[start,end]=min(tied,key=lambda item:(
                        -len(item[1][2]),item[0]))[1][2]
                else:ambiguous.append((start,end))
        options=[item for item in options if not any(
            a<item[1][1] and item[1][0]<b for a,b in ambiguous)
            and (item[1][:2] not in equivalent
                 or item[1][2]==equivalent[item[1][:2]])]
        if not options:break
        # A remembered spelling and concrete role support rank first.
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
        preverified=None;partial_spelling=False
        if (missing_shift is None and odd_field
                and len(fields)==len(original_fields)
                and line[original_fields[number][0]:original_fields[number][1]]==text
                and any(c in 'ぁぃぅぇぉ' for c in text)):
            from ime_full_field import additional_first_words
            preverified=additional_first_words(text,None,store,dictionary,decisions,tokenize)
        if (missing_shift is None and preverified is None and odd_field
                and len(fields)==len(original_fields)
                and line[slice(*original_fields[number])]==text):
            # Only independently proved original words may be spelled in
            # an unfinished field. Its unknown part retains the same text
            # and anomaly; this is also valid for an all-kana source.
            native=project(text,store,dictionary,decisions,partial=True)
            if native and native[1]:
                preverified=native;partial_spelling=True
        repaired=None
        if (missing_shift is None and result.get('corrected',line)!=line
                and len(fields)==len(original_fields)):
            from ime_shift_finish import project_repaired_field
            a,b=original_fields[number]
            repaired=project_repaired_field(line[a:b],text,store,dictionary,decisions,tokenize)
        native_projected=False
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
                native_projected=True
                if first_words and (proposal is None or (
                        {(a,b) for a,b,_ in proposal[1]}.issubset(
                            {(a,b) for a,b,_ in first_words[1]})
                        and len(first_words[1])>len(proposal[1]))):
                    proposal=first_words[:2];native_projected=False
        if not odd_field and re.search(r'[\t\r\n⇒→]',line):
            from ime_full_field import additional_first_words
            complete=additional_first_words(text,proposal,store,dictionary,
                                            decisions,tokenize)
            if complete is not None:
                proposal=complete;native_projected=False
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
                        face=desired;native_projected=False
        # An IME/repaired-field proposal may establish a written lexical
        # boundary that was opaque in kana. Finish its ordinary spelling
        # through the same native projector before exposing the result;
        # otherwise merely analyzing it again changes the visible text.
        # This performs spelling only, not another typo-correction search.
        if not partial_spelling and not native_projected:
            native=project(face,store,dictionary,decisions)
            if native:
                intermediate=_compose_result(text,dict(original=text,corrected=text),
                    edits,engine,decisions)
                if intermediate.get('corrected')==face:
                    finished=_compose_result(text,intermediate,native[1],engine,decisions)
                    if finished.get('corrected')==native[0]:
                        from contextual_repair import _legacy_source_changes
                        face=native[0]
                        edits=tuple(_legacy_source_changes(text,finished,engine,trim_context=False))
        # A spelling that introduces an unexplained boundary on the next
        # analysis is not a completed result. Reuse the common mark evidence
        # once for the proposed field; do not run correction recursively.
        remaining=engine._odd_spans_for_line(face,tokenize,[],store,dictionary,include_pending=False)
        if remaining:
            if not partial_spelling:continue
            # A surviving original anomaly is allowed; newly anomalous
            # text is not. Map the final field back to its unchanged source.
            from difflib import SequenceMatcher
            blocks=SequenceMatcher(None,text,face,autojunk=False).get_opcodes()
            source_start=original_fields[number][0]
            mapped=[]
            for a,b in remaining:
                for tag,x,y,lo,hi in blocks:
                    if a>=hi or b<=lo:continue
                    mapped.append((source_start+x+max(0,a-lo),source_start+x+min(b,hi)-lo)
                        if tag=='equal' else (source_start+x,source_start+y))
            if not mapped or not all(any(lo<=a<=b<=hi for lo,hi in odd) for a,b in mapped):continue
        if odd_field and not remaining:resolved_fields.append(original_fields[number])
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
