# -*- coding: utf-8 -*-
"""Read-only first-conversion spelling evidence for a closed kana field.

The IME supplies word boundaries and a conventional spelling. Each word is
checked against its original reading, source syntax and the common spelling
validator. No result is committed to the IME or to a personal dictionary.
"""


def _crosses_negative_attachment(text,start,end):
    """Keep a proved verb + negative auxiliary + dependent noun in source."""
    from morphology import tokenize as native_tokenize
    # A complete source noun with its actual object case and positive
    # predicate meaning owns the whole range. A best parse's internal
    # nai + dependent noun cannot invent a negative attachment there.
    from reading_segments import native_independent_object_reading
    if native_independent_object_reading(text,start,end):return False
    # A whole final noun may instead occupy the preceding completed
    # relative predicate's open object slot. Every native nominal reading
    # must carry its own positive meaning proof; dictionary presence or a
    # candidate spelling alone does not undo an original negative chain.
    if 0<start<end<len(text):
        from reading_segments import native_written_action_nominal_parts
        proof=native_written_action_nominal_parts(text[:end])
        if proof and proof[0]==start:
            # The same whole relative noun may end at an actual source
            # nominal case instead of the field end. Preserve the real
            # particle and its exact original spelling/reading/position.
            from morphology import dictionary_inflections
            case=next((t for t in native_tokenize(text) if t.start==end),None)
            if (case and case.has_reading and case.pos=='助詞'
                and case.pos_sub.startswith(('格助詞','係助詞'))
                and case.end==end+len(case.surface) and text[end:case.end]==case.surface
                and any(pos.startswith(('助詞,格助詞,','助詞,係助詞,'))
                        and rd==case.reading and base==case.base_form
                        and (form if form!='*' else '')==case.infl_form
                        for pos,form,base,rd in dictionary_inflections(case.surface) or ())):return False
    if 0<start<end==len(text):
        from reading_segments import native_nominal_phrase_faces
        from kana_spelling import _relative_object_spelling_evidence
        faces=native_nominal_phrase_faces(text[start:end])
        if faces and all(_relative_object_spelling_evidence(text[:start],face)
                         for face in faces):return False
    for begin in range(start,-1,-1):
        fragment=text[begin:end]
        parts=native_tokenize(fragment)
        if len(parts)>=2:
            negative,noun=parts[-2:]
            if (negative.has_reading and negative.pos=='形容詞'
                    and negative.base_form in ('ない','無い') and negative.infl_form=='基本形'
                    and noun.has_reading and noun.pos=='名詞'
                    and noun.pos_sub.startswith('非自立') and negative.end==noun.start
                    and start<begin+noun.start<end):
                return True
        if len(parts)<3:continue
        verb,negative,noun=parts[-3:]
        if (verb.pos=='動詞' and verb.pos_sub=='自立'
                and verb.infl_form.startswith('未然')
                and negative.pos=='助動詞'
                and negative.base_form in ('ない','ぬ','ん','まい')
                and noun.pos=='名詞' and noun.pos_sub.startswith('非自立')
                and noun.end==len(fragment)
                and begin+negative.start<end and start<begin+noun.end):
            return True
    return False

def _reinterprets_function_attachment(text,start,end,face=None,nominal_context=None):
    """Keep source grammatical roles from becoming homographic lexical words.

    The whole malformed field can have an unknown best parse. A source suffix
    ending at the IME word can still prove an attached auxiliary or particle.
    """
    from morphology import tokenize as native_tokenize, FUNCTION_WORDS, dictionary_inflections
    source=text[start:end]
    if _crosses_negative_attachment(text,start,end):return True
    # A spelling cannot detach only the head of an original function word.
    # Recovering a larger nominal from a bad parse is handled separately.
    if any(t.has_reading and t.start==start and end<t.end
           and t.pos in ('連体詞','副詞','感動詞','接続詞')
           for t in native_tokenize(text)):
        return True
    # A same-reading first IME candidate does not itself turn a response,
    # reference, connector or modifier into a lexical noun/verb. Compare the
    # source word's native role before any whole-field fallback can bypass it.
    token=next((part for part in native_tokenize(text)
                if part.start==start and part.end==end and part.has_reading),None)
    if token and token.pos=='動詞':
        following=next((p for p in native_tokenize(text) if p.start==end),None)
        if following and following.surface in ('て','で') and following.pos=='助詞' and following.pos_sub=='接続助詞':
            from contextual_repair import _modern_te_allowed
            if _modern_te_allowed(token.surface,token.reading,following.surface) is True:
                forms=dictionary_inflections(face) if face else ()
                if not any(pos.startswith('動詞,') and rd==source and form==token.infl_form
                           for pos,form,base,rd in forms or ()):return True
        from morphology import native_potential_auxiliary
        from semantic_roles import native_te_auxiliary_forms
        from last_choice import surface_for_reading
        preceding=next((p for p in native_tokenize(text) if p.end==start),None)
        if (preceding and preceding.pos=='助詞' and preceding.pos_sub=='接続助詞'
                and preceding.surface in ('て','で') and surface_for_reading(source)!=face
                and (native_potential_auxiliary(token.surface,token.infl_form,token.reading)
                     or native_te_auxiliary_forms(token.surface,token.infl_form,token.reading))):
            return True
    if token and (token.pos in ('感動詞','フィラー','接続詞','連体詞','副詞')
                  or token.pos=='名詞' and token.pos_sub.startswith('代名詞')):
        role=token.pos+','+(token.pos_sub.replace(':',',')+',' if token.pos_sub else '')
        same_role=face and any(pos.startswith(role) and rd==source
                              for pos,form,base,rd in dictionary_inflections(face) or ())
        if face and not same_role:
            # Share the exact whole source word's independently attested
            # finite interpretation, including the candidate's own subject
            # and whole-noun meanings and the original outer finite clause.
            if token.pos=='副詞':
                from kana_spelling import _dictionary_relative_spelling_evidence
                if _dictionary_relative_spelling_evidence(text,start,end,face):return False
            from reading_segments import native_honorific_stem_parts
            for a,b,forms in native_honorific_stem_parts(text):
                if (a==start and b==end and any(p==q and f==g and r==s
                        for p,f,base,r in forms
                        for q,g,lemma,s in dictionary_inflections(face) or ())):return False
            from last_choice import surface_for_reading
            if surface_for_reading(source)==face:return False
            from semantic_roles import candidate_nominal_spelling_evidence
            # A concrete nominal relation may instead identify a homophone,
            # e.g. an organ as a medical object. The IME order is not proof.
            if candidate_nominal_spelling_evidence(text[:start],face,text[end:]):return False
            if nominal_context is not None:
                before,following=nominal_context
                if candidate_nominal_spelling_evidence(before,face,following):return False
            from corrector import _trace
            _trace('IME表記', f'{source!r} → {face!r}: 原文の{role}を別の語へ置き換える根拠がない')
            return True
    if source not in FUNCTION_WORDS:
        return False
    for begin in range(start-1,-1,-1):
        fragment=text[begin:end]
        parts=native_tokenize(fragment)
        if len(parts)<2 or parts[-1].start!=start-begin:
            continue
        tail=parts[-1]
        if tail.end!=len(fragment) or tail.pos not in ('助詞','助動詞'):
            continue
        previous=parts[-2]
        if previous.end==tail.start and previous.pos in ('動詞','形容詞','助動詞'):
            return True
    return False

def cuts_attested_source_word(parts,start,end):
    """A first-IME word cannot consume only part of a known source word."""
    return any(t.has_reading and t.start<end and start<t.end
               and (t.start<start<t.end or t.start<end<t.end)
               for t in parts)


def touches_unattested_ime_word(parts,start,end):
    """An unknown neighboring IME fragment supplies no lexical boundary."""
    return any(not t.has_reading and t.pos!='記号'
               and (t.end==start or t.start==end) for t in parts)


def native_spelling_boundaries(text,parts):
    """Align native words when IME bunsetsu split their okurigana differently.

    Every native word's unchanged reading must cover the complete source.
    This is word-boundary evidence, not a new reading or candidate spelling.
    """
    if not parts or not all(t.has_reading for t in parts):return {}
    if ''.join(t.reading for t in parts)!=text:return {}
    boundaries={};offset=0
    for part in parts:
        boundaries[part.start,part.end]=(offset,offset+len(part.reading))
        offset+=len(part.reading)
    return boundaries


def source_first_words(text, ime):
    """Align a first conversion to source text without changing written words.

    IME conversion takes a reading, not mixed text. Written native tokens
    contribute only their attested reading and two boundary positions; kana
    keeps every original position. No boundary inside a written token is
    invented by a later conversion.
    """
    from morphology import tokenize, native_spelling_only
    if text and all('ぁ'<=c<='ゖ' or c=='ー' for c in text):
        first=ime.convert_words(text)
        return (*first,text,{i:i for i in range(len(text)+1)}) if first else None
    pieces=tokenize(text)
    if not pieces or ''.join(t.surface for t in pieces)!=text:return None
    reading=[];offsets={0:0};edge=0
    for token in pieces:
        kana=all('ぁ'<=c<='ゖ' or c=='ー' for c in token.surface)
        if kana:
            value=token.surface
            offsets.update((edge+i,token.start+i) for i in range(len(value)+1))
        else:
            if not token.has_reading:return None
            value=token.reading
            if not value or not all('ぁ'<=c<='ゖ' or c=='ー' for c in value):return None
            offsets[edge]=token.start;offsets[edge+len(value)]=token.end
        reading.append(value);edge+=len(value)
    reading=''.join(reading)
    first=ime.convert_words(reading)
    if not first or not native_spelling_only(text,first[0]):return None
    descriptors=tuple((a,b,offsets[c],offsets[d],pos,flags)
        for a,b,c,d,pos,flags in first[1] if c in offsets and d in offsets)
    return first[0],descriptors,reading,offsets


def project_first_words(text, store, dictionary, decisions, tokenize):
    import corrector as engine
    import morphology as native
    from semantic_roles import object_before, case_argument_before, candidate_evidence
    try:
        from ime_language import JapaneseIME
    except (ImportError,OSError,AttributeError):
        return None

    if not text:return None
    mixed=any(not ('ぁ'<=c<='ゖ' or c=='ー') for c in text)
    with JapaneseIME() as ime:
        if not ime.available:
            return None
        conversion=source_first_words(text,ime)
        if not conversion:return None
        first,descriptors,source_reading,offsets=conversion
        inverse=ime.reverse_words(first)
        inverse_matches=bool(inverse and inverse[0]==source_reading)
        parts=native.tokenize(first)
        source_parts=native.tokenize(text)
        # An omitted small-kana Shift can make the IME split one intended
        # noun into unrelated adjacent nouns. An isolated word from that
        # parse is not evidence for a completed field either.
        if any(a.pos=='名詞' and b.pos=='名詞' and a.end==b.start
               for a,b in zip(parts,parts[1:])):
            from reading_segments import native_nominal_compound_spelling
            from reading_segments import native_case_adnominal_parts
            compound=inverse_matches and (native_nominal_compound_spelling(text,first)
                or native_case_adnominal_parts(first))
            if mixed or not compound:return None
            # The whole nominal interpretation owns the original range.
            # An accidental name split in raw kana cannot veto only half of
            # it; actual key changes and proper-name candidates remain out.
            accepted,reason=engine._check_replacement(text,
                (0,len(text),first,'かな入力'),store,tokenize,dictionary,decisions,
                conv_taken=((0,len(text)),),spelling=True,ime_first_proof=True)
            if (accepted is None or tuple(accepted[:3])!=(0,len(text),first)
                    or engine._odd_spans_for_line(first,tokenize,[],store,dictionary,include_pending=False)):
                return None
            bounds=native_spelling_boundaries(text,parts)
            edits=tuple((a,b,token.surface) for token in parts
                        for a,b in (bounds.get((token.start,token.end)),)
                        if text[a:b]!=token.surface) if bounds else ((0,len(text),first),)
            return first,edits,True
        current=text;edits=[];delta=0;semantic_positive=False
        native_bounds={span:(offsets[a],offsets[b])
            for span,(a,b) in native_spelling_boundaries(source_reading,parts).items()
            if a in offsets and b in offsets}

        for token in parts:
            if not (token.pos=='名詞' and not token.pos_sub.startswith(('固有名詞','非自立'))
                    or token.pos in ('動詞','形容詞') and token.pos_sub=='自立'):
                continue
            units=[unit for unit in descriptors
                   if token.start<=unit[0] and unit[1]<=token.end]
            if (not units or units[0][0]!=token.start
                    or units[-1][1]!=token.end
                    or any(left[1]!=right[0] or left[3]!=right[2]
                           for left,right in zip(units,units[1:]))):
                aligned=native_bounds.get((token.start,token.end))
                if aligned is None:continue
                start,end=aligned
            else:start,end=units[0][2],units[-1][3]
            if not 0<=start<end<=len(text):
                continue
            # A complete source word such as the person name ちよ cannot
            # donate only ち to an IME first word 血. Unknown long tokens
            # do not certify their guessed boundaries.
            if (cuts_attested_source_word(source_parts,start,end)
                    or touches_unattested_ime_word(parts,token.start,token.end)):
                continue
            reading=text[start:end]
            if any(not ('ぁ'<=c<='ゖ' or c=='ー') for c in reading):continue
            face=first[token.start:token.end]
            if face==reading or not native.native_spelling_only(reading,face):
                continue
            if (_crosses_negative_attachment(text,start,end)
                    or _reinterprets_function_attachment(text,start,end,face,
                        (first[:token.start],first[token.end:]) if native_bounds else None)):
                return None
            forms=native.dictionary_inflections(face) or ()
            if not any(rd==reading and pos.startswith(('名詞,','動詞,自立,','形容詞,自立,'))
                       for pos,form,base,rd in forms):
                continue
            here,end_here=start+delta,end+delta
            if current[here:end_here]!=reading:
                continue
            predicate=(token.pos in ('動詞','形容詞')
                       or token.pos=='名詞' and token.pos_sub.startswith('サ変接続')
                       and current[end_here:].startswith(('し','す')))
            if predicate:
                preceding=next((part for part in source_parts
                    if part.end==start and part.pos=='助詞'
                    and part.pos_sub.startswith('格助詞')),None)
                if preceding and preceding.start==0:
                    continue
                obj=object_before(current,here,tokenize)
                arg=case_argument_before(current,here,tokenize)
                proofs=[]
                if obj:
                    proofs.append(candidate_evidence(obj,face,current[end_here:],
                                                     before=current[:here]))
                if arg:
                    proofs.append(candidate_evidence(arg[0],face,current[end_here:],
                                                     before=current[:here],case=arg[1]))
                positive=any(p and p['shared_roles'] for p in proofs)
                if (obj or arg) and not positive:
                    continue
            accepted,reason=engine._check_replacement(current,
                (here,end_here,face,'かな入力'),store,tokenize,dictionary,decisions,
                conv_taken=((here,end_here),),spelling=True)
            if accepted is None or tuple(accepted[:3])!=(here,end_here,face):
                continue
            current=current[:here]+face+current[end_here:]
            edits.append((start,end,face));delta+=len(face)-(end-start)
            if predicate and positive:semantic_positive=True
        if not mixed and not semantic_positive and current!=text:
            from ime_homophone import positive_predicate_alternatives
            alternatives=positive_predicate_alternatives(current,first,text,tokenize,ime)
            if len(alternatives)==1:
                alternate=alternatives[0][0]
                alternative_words=ime.reverse_words(alternate)
                verbs=[part for part in native.tokenize(alternate)
                       if part.pos=='動詞' and part.pos_sub=='自立']
                if alternative_words and alternative_words[0]==text and verbs:
                    verb=verbs[-1]
                    units=[unit for unit in alternative_words[1]
                           if verb.start<=unit[0] and unit[1]<=verb.end]
                    if (units and units[0][0]==verb.start and units[-1][1]==verb.end):
                        start,end=units[0][2],units[-1][3]
                        here,end_here=start+delta,end+delta
                        face=alternate[verb.start:verb.end]
                        if (current[here:end_here]==text[start:end]
                                and native.native_spelling_only(text[start:end],face)):
                            accepted,reason=engine._check_replacement(current,
                                (here,end_here,face,'かな入力'),store,tokenize,
                                dictionary,decisions,conv_taken=((here,end_here),),
                                spelling=True)
                            if accepted is not None and tuple(accepted[:3])==(here,end_here,face):
                                current=current[:here]+face+current[end_here:]
                                edits.append((start,end,face));semantic_positive=True
        # Direct input alignment resolves reading ambiguity, not meaning.
        # A newly admitted multireading conversion needs independent positive
        # evidence from the original argument and predicate before adoption.
        if not inverse_matches and not semantic_positive:
            return None
        if not edits or engine._odd_spans_for_line(current,tokenize,[],store,dictionary,include_pending=False):
            return None
        return current,tuple(edits),semantic_positive
