# -*- coding: utf-8 -*-
"""Read-only homophone evidence for a repaired IME first conversion.

The first conversion explains a possible typo.  A TSF search result may
offer a different spelling for its predicate; neither list is a verdict.
Only unchanged source arguments with positive semantic evidence can open
that alternative, and the caller still runs the common final validator.
"""


def positive_predicate_alternatives(source, first, reading, tokenize, ime):
    """Return (whole surface, original object, positive role proof) tuples."""
    from morphology import native_spelling_only, tokenize as native_tokenize
    from semantic_roles import object_before, case_argument_before, candidate_evidence

    reverse=ime.reverse_words(first)
    if not reverse or reverse[0]!=reading:
        return ()
    verbs=[token for token in native_tokenize(first)
           if token.pos=='動詞' and token.pos_sub=='自立' and token.start>0]
    if not verbs:
        return ()
    verb=verbs[-1]
    # The argument must be present in the original, not introduced by the
    # hypothetical conversion.  A changed prefix cannot lend its semantics.
    if source[:verb.start]!=first[:verb.start]:
        return ()
    word=next((item for item in reverse[1] if item[0]==verb.start),None)
    if word is None:
        return ()
    suffix_reading=reading[word[2]:]
    if not suffix_reading:
        return ()
    object_word=object_before(source,verb.start,tokenize)
    case_argument=case_argument_before(source,verb.start,tokenize)
    if not object_word and not case_argument:
        return ()

    def original_role_proof(suffix):
        proofs=[]
        before=source[:verb.start]
        if object_word:
            proofs.append(candidate_evidence(object_word,suffix,'',before=before))
        if case_argument:
            proofs.append(candidate_evidence(case_argument[0],suffix,'',
                                             before=before,case=case_argument[1]))
        return tuple(proof for proof in proofs if proof and proof['shared_roles'])

    # A known fit for the first conversion is not an invitation to rewrite
    # its spelling from the search interface's independently ranked results.
    if original_role_proof(first[verb.start:]):
        return ()
    try:
        from ime_candidates import SearchCandidates
        with SearchCandidates() as search:
            if not search.available:
                return ()
            hits=search.candidates(suffix_reading)
    except (ImportError,OSError,AttributeError):
        return ()
    if not hits:
        return ()
    alternatives=[]
    for suffix in dict.fromkeys(hits):
        if suffix==first[verb.start:]:
            continue
        proof=original_role_proof(suffix)
        if not proof:
            continue
        surface=first[:verb.start]+suffix
        if (not native_spelling_only(reading,surface)
                or ime.phonetic(surface)!=reading):
            continue
        alternatives.append((surface,object_word,proof[0]))
    return tuple(alternatives)
