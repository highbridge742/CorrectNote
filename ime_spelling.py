# -*- coding: utf-8 -*-
"""Read-only first-conversion spelling evidence for a closed kana field.

The IME supplies word boundaries and a conventional spelling. Each word is
checked against its original reading, source syntax and the common spelling
validator. No result is committed to the IME or to a personal dictionary.
"""


import re

# Every eligible changed reading contains at least two adjacent kana.
# This is only a necessary character-range condition, not a word roster.
_FOCUSED_READING_PAIR=re.compile(r'[ぁ-ゖー]{2}')

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
    from morphology import native_dependent_noun_ending_possible
    if native_dependent_noun_ending_possible(text[:end]) is False:return False
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

def _crosses_genitive_attachment(text,start,end,face):
    """A nominal spelling cannot swallow the original noun's adnominal no.

    A best parse can join no to a following continuative verb. At a nominal
    boundary, independently attested nouns on both sides still establish
    the unchanged genitive reading. A finite verbal tail owns its own stem.
    """
    if not 0<start<end<=len(text) or text[start]!='の' or (face or '').startswith('の'):
        return False
    from morphology import tokenize,dictionary_inflections
    from reading_segments import native_nominal_phrase_faces,_native_written_nominal_faces
    parts=tokenize(text)
    previous=next((t for t in parts if t.end==start),None)
    if (previous is None or not previous.has_reading or previous.pos!='名詞'
            or previous.pos_sub.startswith(('非自立','接尾'))
            or text[previous.start:previous.end]!=previous.surface
            or not any(p.startswith('名詞,') and r==previous.reading and b==previous.base_form
                for p,f,b,r in dictionary_inflections(previous.surface) or ())):return False
    following=next((t for t in parts if t.start==end),None)
    nominal_end=(end==len(text) or text[end].isspace()
        or following is not None and following.has_reading and (
            following.pos=='記号' or following.pos=='助詞' and (
                following.pos_sub.startswith(('格助詞','係助詞','並立助詞')) or following.pos_sub=='連体化')))
    if not nominal_end and (following is None or following.pos!='助動詞'):return False
    # Retain complete source-word ownership. Only an actual genitive or
    # the ambiguous, complete continuative token can provide this seam.
    head=next((t for t in parts if t.start==start),None)
    if (head is None or not head.has_reading
            or not (head.surface=='の' and head.end==start+1 and head.pos=='助詞'
                    and head.pos_sub=='連体化'
                or head.end==end and head.pos=='動詞' and head.pos_sub=='自立'
                    and head.infl_form=='連用形')):return False
    suffix=text[start+1:end]
    faces=(native_nominal_phrase_faces(suffix)
        if suffix and all('ぁ'<=c<='ゖ' or c=='ー' for c in suffix)
        else _native_written_nominal_faces(suffix))
    if not nominal_end:
        # This proves only the noun's attachment, not completion of the
        # whole predicate. The actual nominal copula owns this boundary
        # even before an intervening wa in a negative or connective tail.
        # Verbal masu/tai/ta cannot supply this nominal attachment.
        if (not following.has_reading or following.base_form not in ('だ','です')
                or not any(p.startswith('助動詞,') and b==following.base_form
                    and r==following.reading and f==following.infl_form
                    for p,f,b,r in dictionary_inflections(following.surface) or ())):return False
    for noun in faces:
        evidence=tokenize(previous.surface+'の'+noun)
        cut=len(previous.surface)
        if any(t.start==cut and t.end==cut+1 and t.surface=='の' and t.has_reading
                and t.pos=='助詞' and t.pos_sub=='連体化' for t in evidence):return True
    return False


def _reinterprets_function_attachment(text,start,end,face=None,nominal_context=None):
    """Keep source grammar and ambiguous short-noun spelling choices.

    The whole malformed field can have an unknown best parse. A source suffix
    ending at the IME word can still prove an attached auxiliary or particle.
    A focused short noun also retains its native, unresolved sense boundary.
    """
    from morphology import tokenize as native_tokenize, FUNCTION_WORDS, dictionary_inflections
    source=text[start:end]
    source_parts=native_tokenize(text)
    def attested_auxiliary(part):
        return bool(part and part.has_reading and part.pos=='助動詞'
            and any(pos.startswith('助動詞,') and base==part.base_form
                    and form==part.infl_form and reading==part.reading
                    for pos,form,base,reading in dictionary_inflections(part.surface) or ()))
    def original_auxiliary_attachment(part):
        if not attested_auxiliary(part):return False
        previous=next((item for item in source_parts if item.end==part.start),None)
        return bool(previous and previous.has_reading
            and previous.pos in ('動詞','形容詞','助動詞')
            and text[previous.start:previous.end]==previous.surface
            and any(pos.startswith(previous.pos+',') and base==previous.base_form
                    and (form if form!='*' else '')==previous.infl_form
                    and reading==previous.reading
                    for pos,form,base,reading in dictionary_inflections(previous.surface) or ()))
    # Only positive evidence bypasses the older narrow-range checks.
    # An unproved source attachment still receives all original fallbacks.
    token=next((part for part in source_parts
                if part.start==start and part.end==end and part.has_reading),None)
    native_auxiliary=attested_auxiliary(token)
    if original_auxiliary_attachment(token):return True
    # A whole-field candidate owns the same original auxiliaries as a narrow
    # word candidate. Map only exact source boundaries: a replacement that
    # crosses them cannot provide this positive attachment proof.
    if face and source!=face:
        auxiliaries=[part for part in source_parts
            if part.pos=='助動詞' and part.has_reading
            and start<=part.start<part.end<=end
            and (start<part.start or part.end<end)]
        if auxiliaries:
            from difflib import SequenceMatcher
            from morphology import native_spelling_only
            blocks=SequenceMatcher(None,source,face,autojunk=False).get_opcodes()
            def boundary(offset):
                if any(tag=='insert' and a==offset for tag,a,b,c,d in blocks):return None
                for tag,a,b,c,d in blocks:
                    if a<=offset<=b:
                        if tag=='equal':return c+offset-a
                        if offset==a:return c
                        if offset==b:return d
                        return None
                return None
            for part in auxiliaries:
                left=boundary(part.start-start);right=boundary(part.end-start)
                if left is None or right is None or left>=right:continue
                written=face[left:right]
                # This new whole-range proof may use only the original
                # native attachment. If it is absent, continue the original
                # whole-range checks; do not launch a new substring search
                # at every unproved internal auxiliary.
                if (written!=part.surface and native_spelling_only(part.surface,written)
                        and original_auxiliary_attachment(part)):
                    return True
    # A first-conversion word owns a reading, not the short focused noun's
    # meaning. Use the native projector's same alternatives and actual tail
    # before either narrow or whole-field IME spelling reaches the common gate.
    if face and source!=face and _FOCUSED_READING_PAIR.search(source):
        from kana_spelling import _unresolved_focused_source_nominal
        from last_choice import surface_for_reading,active
        from morphology import native_spelling_only
        from difflib import SequenceMatcher
        # Map the actual changed noun even when a caller owns the whole field.
        # Equal outer words/particles cannot lend it another noun's evidence.
        for tag,a,b,c,d in SequenceMatcher(None,source,face,autojunk=False).get_opcodes():
            reading=source[a:b];written=face[c:d]
            if (tag=='equal' or not 2<=len(reading)<=3
                    or not all('ぁ'<=ch<='ゖ' or ch=='ー' for ch in reading)
                    or not native_spelling_only(reading,written)):continue
            remembered=surface_for_reading(reading)
            if not remembered:
                chosen=active().lookup(reading) if active() is not None else None
                if chosen and native_spelling_only(reading,chosen):remembered=chosen
            if (written!=remembered and _unresolved_focused_source_nominal(
                    text,start+a,start+b)):return True
    if _crosses_negative_attachment(text,start,end):return True
    if _crosses_genitive_attachment(text,start,end,face):return True
    # A spelling cannot detach only the head of an original function word.
    # Recovering a larger nominal from a bad parse is handled separately.
    if any(t.has_reading and t.start==start and end<t.end
           and t.pos in ('連体詞','副詞','感動詞','接続詞')
           for t in source_parts):
        return True
    # A same-reading first IME candidate does not itself turn a response,
    # reference, connector or modifier into a lexical noun/verb. Compare the
    # source word's native role before any whole-field fallback can bypass it.
    token=next((part for part in source_parts
                if part.start==start and part.end==end and part.has_reading),None)
    if token and token.pos=='動詞':
        following=next((p for p in source_parts if p.start==end),None)
        if following and following.surface in ('て','で') and following.pos=='助詞' and following.pos_sub=='接続助詞':
            from contextual_repair import _modern_te_allowed
            if _modern_te_allowed(token.surface,token.reading,following.surface) is True:
                forms=dictionary_inflections(face) if face else ()
                if not any(pos.startswith('動詞,') and rd==source and form==token.infl_form
                           for pos,form,base,rd in forms or ()):return True
        from morphology import native_potential_auxiliary
        from semantic_roles import native_te_auxiliary_forms
        from last_choice import surface_for_reading
        preceding=next((p for p in source_parts if p.end==start),None)
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
    # Keep the previous fallback when the exact original attachment above
    # is not proved. Missing proof is not a new permission to re-spell it.
    if source not in FUNCTION_WORDS and not native_auxiliary:
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


def _first_compound_arguments(text, first, parts, source_parts):
    """Locate attested whole nouns inside the same finite source clause.

    An IME split is not a new dictionary entry. Keep each actual noun's
    full native reading and the original case/finite-predicate relation.
    Unknown noun strings never gain proof merely by being adjacent.
    """
    from morphology import native_spelling_only
    from reading_segments import (native_common_noun_reading,
        native_nominal_case_boundary,native_source_finite_verb)
    from semantic_roles import candidate_evidence
    boundaries=native_spelling_boundaries(text,parts)
    if not boundaries:return None
    found={};index=0
    while index<len(parts):
        end=index+1
        if parts[index].pos=='名詞':
            while (end<len(parts) and parts[end].pos=='名詞'
                   and parts[end-1].end==parts[end].start):end+=1
        if end-index<2:index=end;continue
        group=parts[index:end]
        if any(not t.has_reading or t.pos_sub.startswith(('固有名詞','非自立')) for t in group):return None
        begin=boundaries[group[0].start,group[0].end][0]
        finish=boundaries[group[-1].start,group[-1].end][1]
        reading=text[begin:finish];face=first[group[0].start:group[-1].end]
        if (not native_common_noun_reading(face,reading)
                or not native_spelling_only(reading,face)
                or cuts_attested_source_word(source_parts,begin,finish)):return None
        if end+1>=len(parts):return None
        case,head=parts[end:end+2]
        if not (case.has_reading and case.pos=='助詞'
                and case.pos_sub=='格助詞:一般'
                and case.start==group[-1].end and head.start==case.end
                and head.has_reading and head.pos=='動詞' and head.pos_sub=='自立'):return None
        case_begin,case_end=boundaries[case.start,case.end]
        head_begin,head_end=boundaries[head.start,head.end]
        if (case_begin!=finish or case_end!=head_begin
                or text[case_begin:case_end]!=case.surface
                or native_nominal_case_boundary(text,source_parts,finish,case.surface,(face,)) is None
                or not native_source_finite_verb(text[head_begin:])):return None
        proof=candidate_evidence(face,text[head_begin:head_end],text[head_end:],
            before=text[:head_begin],case=case.surface)
        if not (proof and proof['shared_roles']):return None
        written_before=text[:begin]+face+text[finish:head_begin]
        written_proof=candidate_evidence(face,head.surface,text[head_end:],
            before=written_before,case=case.surface)
        if not (written_proof and written_proof['shared_roles']):return None
        found[group[0].start]=(begin,finish,face,group[-1].end)
        index=end
    return found or None



def _first_case_word_proposal(text,first,descriptors,parts,source_parts,native_bounds,decisions):
    """Compose proved words from one original native case/predicate frame.

    No intermediate replacement or common-C rejection supplies evidence.
    The exact source range, noun face, real case and actual written verb
    retain independent proof before a combined field candidate is built.
    """
    from analysis_context import check_current_request
    from morphology import native_spelling_only,dictionary_inflections,tokenize
    from reading_segments import (native_reopened_verb_case_frames,
        native_case_predicate_witness,native_reopened_verb_spelling_boundary)
    from semantic_roles import candidate_evidence
    from last_choice import surface_for_reading,active
    check_current_request()
    if not native_bounds:return None

    def source_span(token):
        units=[unit for unit in descriptors if token.start<=unit[0] and unit[1]<=token.end]
        aligned=native_bounds.get((token.start,token.end))
        if (units and units[0][0]==token.start and units[-1][1]==token.end
                and all(a[1]==b[0] and a[3]==b[2] for a,b in zip(units,units[1:]))):
            span=(units[0][2],units[-1][3])
            if aligned is not None and aligned!=span:return None
            return span
        return aligned

    frames=native_reopened_verb_case_frames(text)
    check_current_request()
    for offset,clause,a,b,case,source_faces in frames:
        # The caller owns one original field. Never borrow a frame through
        # a quotation, separator or another clause in the supplied text.
        if offset!=0 or clause!=text:continue
        start,end=offset+a,offset+b
        noun=next((part for part in parts if source_span(part)==(start,end)
            and part.has_reading and part.pos=='名詞'
            and not part.pos_sub.startswith(('固有名詞','非自立','接尾'))),None)
        if noun is None:continue
        particle=next((part for part in parts if part.start==noun.end
            and part.has_reading and part.pos=='助詞' and part.pos_sub=='格助詞:一般'
            and part.surface==case and source_span(part)==(end,end+len(case))),None)
        if particle is None or text[end:end+len(case)]!=case:continue
        head=next((part for part in parts if part.start==particle.end
            and part.has_reading and part.pos=='動詞' and part.pos_sub=='自立'),None)
        if head is None:continue
        head_span=source_span(head)
        if head_span is None:continue
        head_start,head_end=head_span
        if not end+len(case)==head_start<head_end<=len(text):continue
        noun_face=first[noun.start:noun.end];head_face=first[head.start:head.end]
        if noun_face not in source_faces:continue
        edits=((start,end,noun_face),(head_start,head_end,head_face))
        if any(text[lo:hi]==face for lo,hi,face in edits):continue
        proved=True
        for token,(lo,hi,face) in zip((noun,head),edits):
            reading=text[lo:hi]
            if (not all('ぁ'<=ch<='ゖ' or ch=='ー' for ch in reading)
                    or not native_spelling_only(reading,face,following=text[hi:])
                    or touches_unattested_ime_word(parts,token.start,token.end)
                    or cuts_attested_source_word(source_parts,lo,hi)
                    and not (token is head and native_reopened_verb_spelling_boundary(text,lo,hi,face))
                    or _crosses_negative_attachment(text,lo,hi)
                    or _reinterprets_function_attachment(text,lo,hi,face,
                        (first[:token.start],first[token.end:]))):
                proved=False;break
            forms=dictionary_inflections(face) or ()
            if not any(pos.startswith(token.pos+',') and rd==reading
                    and base==token.base_form and (form if form!='*' else '')==token.infl_form
                    for pos,form,base,rd in forms):
                proved=False;break
            chosen=surface_for_reading(reading)
            selected=active().lookup(reading) if active() is not None else None
            if (chosen and chosen!=face or selected and selected!=face
                    or decisions is not None and decisions.blocks(reading,face)):
                proved=False;break
            check_current_request()
        if not proved:continue
        source_predicate=text[head_start:]
        source_fit=native_case_predicate_witness(noun_face,case,source_predicate,finite_only=True)
        check_current_request()
        if not source_fit:continue
        actual_tail=text[head_end:]
        actual_predicate=head_face+actual_tail
        actual_parts=tokenize(actual_predicate)
        if not (actual_parts and actual_parts[0].surface==head_face
                and actual_parts[0].start==0 and actual_parts[0].end==len(head_face)
                and actual_parts[0].pos==head.pos and actual_parts[0].pos_sub==head.pos_sub
                and actual_parts[0].reading==text[head_start:head_end]
                and actual_parts[0].base_form==head.base_form
                and actual_parts[0].infl_form==head.infl_form):continue
        actual_before=text[:start]+noun_face+text[end:head_start]
        actual_fit=candidate_evidence(noun_face,head_face,actual_tail,before=actual_before,case=case)
        check_current_request()
        if not (actual_fit and actual_fit['shared_roles']):continue
        actual_finite=native_case_predicate_witness(noun_face,case,actual_predicate,finite_only=True)
        check_current_request()
        if not actual_finite:continue
        changed=text[:start]+noun_face+text[end:head_start]+head_face+actual_tail
        # Evidence keeps both coordinate systems and actual faces. It is
        # request-local construction data, never personal or public state.
        written_noun_end=start+len(noun_face)
        written_head_start=head_start+len(noun_face)-(end-start)
        evidence=dict(field=(offset,offset+len(clause)),noun_source=(start,end),
            noun_candidate=(start,written_noun_end),native_noun_span=(noun.start,noun.end),noun_face=noun_face,
            case_source=(end,head_start),case_candidate=(written_noun_end,written_head_start),
            native_case_span=(particle.start,particle.end),case=case,
            predicate_source=(head_start,head_end),
            predicate_candidate=(written_head_start,written_head_start+len(head_face)),
            native_predicate_span=(head.start,head.end),
            predicate_face=head_face,source_fit=source_fit,actual_fit=actual_fit)
        check_current_request()
        return changed,edits,evidence
    check_current_request()
    return None


def project_first_words(text, store, dictionary, decisions, tokenize, *, subject_completion=False):
    import corrector as engine
    import morphology as native
    from semantic_roles import (object_before, case_argument_before, candidate_evidence,
        subject_before, subject_candidate_evidence)
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
        compound_arguments={}
        if any(a.pos=='名詞' and b.pos=='名詞' and a.end==b.start
               for a,b in zip(parts,parts[1:])):
            from reading_segments import native_nominal_compound_spelling
            from reading_segments import native_case_adnominal_parts
            compound=inverse_matches and (native_nominal_compound_spelling(text,first)
                or native_case_adnominal_parts(first))
            if mixed:return None
            if not compound:
                compound_arguments=(_first_compound_arguments(text,first,parts,source_parts)
                                    if inverse_matches else None)
                if compound_arguments is None:return None
            else:
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
        current=text;edits=[];delta=0;semantic_positive=False;paired_edits=()
        native_bounds={span:(offsets[a],offsets[b])
            for span,(a,b) in native_spelling_boundaries(source_reading,parts).items()
            if a in offsets and b in offsets}

        # Prove a same-field noun and its actual predicate before the
        # sequential path tests a nominal-only intermediate sentence.
        # Unknown evidence or rejected combined C leaves that path intact.
        if inverse_matches and not compound_arguments:
            proposal=_first_case_word_proposal(text,first,descriptors,parts,source_parts,native_bounds,decisions)
            if proposal is not None:
                projected,combined_edits,evidence=proposal
                accepted,reason=engine._check_replacement(text,
                    (0,len(text),projected,'かな入力'),store,tokenize,dictionary,decisions,
                    conv_taken=((0,len(text)),),spelling=True)
                from analysis_context import check_current_request
                check_current_request()
                if (accepted is not None and tuple(accepted[:3])==(0,len(text),projected)
                        and not engine._odd_spans_for_line(projected,tokenize,[],store,dictionary,include_pending=False)):
                    check_current_request()
                    # The pair proves these original words, not every other
                    # first-conversion word in this field. Preserve the old
                    # independent word path for an earlier subject or noun.
                    current=projected;edits=list(combined_edits)
                    paired_edits=combined_edits;semantic_positive=True

        compound_end=-1
        for token in parts:
            if token.start<compound_end:continue
            if token.start in compound_arguments:
                start,end,face,compound_end=compound_arguments[token.start]
                source_delta=(sum(len(face)-(b-a) for a,b,face in edits if b<=start)
                              if paired_edits else delta)
                here,end_here=start+source_delta,end+source_delta
                if current[here:end_here]!=text[start:end]:return None
                accepted,reason=engine._check_replacement(current,
                    (here,end_here,face,'かな入力'),store,tokenize,dictionary,decisions,
                    conv_taken=((here,end_here),),spelling=True)
                if accepted is None or tuple(accepted[:3])!=(here,end_here,face):return None
                current=current[:here]+face+current[end_here:]
                edits.append((start,end,face));delta+=len(face)-(end-start)
                continue
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
            if any((start,end)==(a,b) for a,b,face in paired_edits):
                continue
            # A complete source word such as the person name ちよ cannot
            # donate only ち to an IME first word 血. Unknown long tokens
            # do not certify their guessed boundaries.
            if cuts_attested_source_word(source_parts,start,end):
                from reading_segments import native_reopened_topic_spelling,native_reopened_verb_spelling_boundary
                preserved=(subject_completion and token.pos=='名詞'
                    and native_reopened_topic_spelling(text,start,end,first[token.start:token.end]))
                if not preserved and token.pos=='動詞' and token.pos_sub=='自立':
                    preserved=native_reopened_verb_spelling_boundary(text,start,end,first[token.start:token.end])
                if not preserved:continue
            if touches_unattested_ime_word(parts,token.start,token.end):continue
            reading=text[start:end]
            if any(not ('ぁ'<=c<='ゖ' or c=='ー') for c in reading):continue
            face=first[token.start:token.end]
            if token.pos=='名詞':
                # The same original noun/case/predicate frame may already
                # identify its native nominal sense. Supply that spelling
                # before checking this candidate; a rejected IME word is
                # not evidence for a replacement. Ambiguous faces retain
                # the existing first-conversion ordering.
                from reading_segments import native_reopened_verb_case_frames
                from last_choice import surface_for_reading,active
                chosen=surface_for_reading(reading)
                if not chosen:
                    selected=active().lookup(reading) if active() is not None else None
                    if selected and native.native_spelling_only(reading,selected):chosen=selected
                if not chosen:
                    choices=tuple(dict.fromkeys(proved for offset,clause,a,b,case,faces
                        in native_reopened_verb_case_frames(text)
                        if (start,end)==(offset+a,offset+b) for proved in faces
                        if native.native_spelling_only(reading,proved)
                        and any(pos.startswith('名詞,') and rd==reading
                            for pos,form,base,rd in native.dictionary_inflections(proved) or ())))
                    if len(choices)==1:face=choices[0]
            if face==reading or not native.native_spelling_only(reading,face,following=text[end:]):
                continue
            if (_crosses_negative_attachment(text,start,end)
                    or _reinterprets_function_attachment(text,start,end,face,
                        (first[:token.start],first[token.end:]) if native_bounds else None)):
                return None
            forms=native.dictionary_inflections(face) or ()
            if not any(rd==reading and pos.startswith(('名詞,','動詞,自立,','形容詞,自立,'))
                       for pos,form,base,rd in forms):
                continue
            source_delta=(sum(len(face)-(b-a) for a,b,face in edits if b<=start)
                          if paired_edits else delta)
            here,end_here=start+source_delta,end+source_delta
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
                subject=(subject_before(current,here,tokenize,allow_direct_topic=True)
                         if subject_completion else '')
                # Carry only a positive relation already present in the
                # same original kana predicate. Unknown roles are not a veto.
                source_subject=(subject_candidate_evidence(subject,reading,text[end:])
                                if subject else None)
                if not (source_subject and source_subject['shared_roles']):subject=''
                proofs=[]
                subject_fit=subject_candidate_evidence(subject,face,current[end_here:]) if subject else None
                if subject and not (subject_fit and subject_fit['shared_roles']):continue
                if subject_fit:proofs.append(subject_fit)
                if obj:
                    proofs.append(candidate_evidence(obj,face,current[end_here:],
                                                     before=current[:here]))
                if arg:
                    proofs.append(candidate_evidence(arg[0],face,current[end_here:],
                                                     before=current[:here],case=arg[1]))
                positive=any(p and p['shared_roles'] for p in proofs)
                if (obj or arg or subject) and not positive:
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
            alternatives=positive_predicate_alternatives(current,first,text,tokenize,ime,
                subject_completion=subject_completion)
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
                        source_delta=(sum(len(face)-(b-a) for a,b,face in edits if b<=start)
                                      if paired_edits else delta)
                        here,end_here=start+source_delta,end+source_delta
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
        return current,tuple(sorted(edits) if paired_edits else edits),semantic_positive
