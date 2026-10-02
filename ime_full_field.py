# -*- coding: utf-8 -*-
"""Conservative whole-field first-conversion evidence for closed kana input."""

def additional_first_words(text, proposal, store, dictionary, decisions, tokenize):
    """Return only an attested first conversion that extends existing edits."""
    import corrector as engine
    import morphology as native
    from ime_language import JapaneseIME
    from pos_grammar import odd_kana_spans
    from semantic_roles import CASE_VERB_ROLES
    if not text or any(not ('ぁ'<=c<='ゖ' or c=='ー') for c in text):
        return None
    with JapaneseIME() as ime:
        if not ime.available:
            return None
        conversion=ime.convert_words(text)
        reverse=ime.reverse_words(conversion[0]) if conversion else None
    if not conversion or conversion[0]==text or not reverse or reverse[0]!=text:
        return None
    first,descriptors=conversion
    parts=native.tokenize(first)
    source_parts=native.tokenize(text)
    from ime_spelling import cuts_attested_source_word,native_spelling_boundaries
    native_bounds=native_spelling_boundaries(text,parts)
    # A first conversion can split a missed small-kana key into two ordinary
    # nouns. Their separate dictionary entries do not attest the compound.
    if any(a.pos=='名詞' and b.pos=='名詞' and a.end==b.start
           for a,b in zip(parts,parts[1:])):
        return None
    edits=[]
    for index,token in enumerate(parts):
        units=[unit for unit in descriptors
               if token.start<=unit[0] and unit[1]<=token.end]
        if (not units or units[0][0]!=token.start or units[-1][1]!=token.end
                or any(a[1]!=b[0] or a[3]!=b[2] for a,b in zip(units,units[1:]))):
            aligned=native_bounds.get((token.start,token.end))
            if aligned is None:
                if token.pos!='記号':return None
                continue
            start,end=aligned
        else:start,end=units[0][2],units[-1][3]
        if not 0<=start<end<=len(text):
            return None
        if cuts_attested_source_word(source_parts,start,end):
            return None
        face=first[token.start:token.end]
        reading=text[start:end]
        if face==reading:
            continue
        if token.pos not in ('名詞','動詞','形容詞'):
            return None
        if not native.native_spelling_only(reading,face):
            return None
        if token.pos_sub.startswith('固有名詞'):
            if not token.pos_sub.startswith('固有名詞:地域'):
                return None
            case=text[end:end+1]
            particle=parts[index+1] if index+1<len(parts) else None
            following=parts[index+2] if index+2<len(parts) else None
            if (case not in ('に','へ') or particle is None
                    or particle.surface!=case or particle.pos!='助詞'
                    or following is None or following.pos!='動詞'
                    or 'place' not in CASE_VERB_ROLES.get(case,{}).get(
                        following.base_form,())):
                return None
        from ime_spelling import (_crosses_negative_attachment,
                                  _reinterprets_function_attachment)
        if (_crosses_negative_attachment(text,start,end)
                or _reinterprets_function_attachment(text,start,end,face,
                    (first[:token.start],first[token.end:]) if native_bounds else None)):
            return None
        edits.append((start,end,face))
    if not edits or (proposal and len(edits)<=len(proposal[1])):
        return None
    if proposal and not set(proposal[1]).issubset(set(edits)):
        return None
    # Same-reading spelling alone cannot make a broken kana connection sound.
    source_odd=odd_kana_spans(text+'\t',dictionary,store)
    if source_odd and not any(a<=i<b for a,b in source_odd
                              for i,c in enumerate(text) if c in 'ぁぃぅぇぉ'):
        return None
    accepted,reason=engine._check_replacement(text,
        (0,len(text),first,'かな入力'),store,tokenize,dictionary,decisions,
        conv_taken=((0,len(text)),),spelling=True,ime_first_proof=True)
    if accepted is None or tuple(accepted[:3])!=(0,len(text),first):
        return None
    if engine._odd_spans_for_line(first,tokenize,[],store,dictionary,include_pending=False):
        return None
    return first,tuple(edits)
