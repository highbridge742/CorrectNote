# -*- coding: utf-8 -*-
"""Complete a proved Shift repair using the IME's read-only word alignment."""


_SMALL_TO_FULL=dict(zip('ぁぃぅぇぉ','あいうえお'))


def project_repaired_field(original, approved, store, dictionary, decisions, tokenize):
    """Return edits in approved coordinates, after a single physical Shift slip."""
    from difflib import SequenceMatcher
    import corrector as engine
    from ime_spelling import project_first_words
    try:
        from ime_language import JapaneseIME
    except (ImportError,OSError,AttributeError):
        return None
    if (not original or not any(c in _SMALL_TO_FULL for c in original)
            or not all('ぁ'<=c<='ゖ' or c=='ー' for c in original)):
        return None
    with JapaneseIME() as ime:
        if not ime.available:
            return None
        reading=ime.phonetic(approved)
    if not reading or len(reading)!=len(original):
        return None
    differences=[(old,new) for old,new in zip(original,reading) if old!=new]
    if len(differences)!=1 or _SMALL_TO_FULL.get(differences[0][0])!=differences[0][1]:
        return None
    projected=project_first_words(reading,store,dictionary,decisions,tokenize)
    if not projected or not projected[2] or projected[0]==approved:
        return None
    desired=projected[0]
    # Replay every proposed word against the actual mistyped source. An
    # intermediate spelling chosen by an older path is not user intent.
    current=original;delta=0
    for start,end,face in projected[1]:
        lo,hi=start+delta,end+delta
        accepted,reason=engine._check_replacement(current,
            (lo,hi,face,'かな入力'),store,tokenize,dictionary,decisions,
            conv_taken=((lo,hi),))
        if accepted is None or tuple(accepted[:3])!=(lo,hi,face):
            return None
        current=current[:lo]+face+current[hi:]
        delta+=len(face)-(end-start)
    if current!=desired or engine._odd_spans_for_line(desired,tokenize,[],store,dictionary,include_pending=False):
        return None
    changes=[(a,b,desired[c:d]) for tag,a,b,c,d in
             SequenceMatcher(None,approved,desired,autojunk=False).get_opcodes()
             if tag!='equal']
    if not changes or any(a==b or not face for a,b,face in changes):
        return None
    return desired,tuple(changes)


def project_repaired_polite_tail(original, approved, store, dictionary, decisions, tokenize):
    """Spell an approved one-key polite repair using two native arguments."""
    import corrector as engine
    from contextual_repair import key_repairs
    from ime_spelling import project_first_words
    from semantic_roles import object_before,case_argument_before,candidate_evidence
    from morphology import tokenize as native_tokenize
    try:
        from ime_language import JapaneseIME
    except (ImportError,OSError,AttributeError):
        return None

    if (not approved.endswith('ました') or not original
            or not all('ぁ'<=c<='ゖ' or c=='ー' for c in original)):
        return None
    parts=native_tokenize(approved)
    if len(parts)<3:
        return None
    verb,polite,past=parts[-3:]
    if (verb.pos!='動詞' or verb.pos_sub!='自立' or verb.infl_form!='連用形'
            or polite.surface!='まし' or polite.pos!='助動詞'
            or past.surface!='た' or past.pos!='助動詞'
            or verb.end!=polite.start or polite.end!=past.start
            or past.end!=len(approved)):
        return None
    start=verb.start
    tail=approved[start:]
    if not 5<=len(tail)<=9 or not all('ぁ'<=c<='ゖ' for c in tail):
        return None
    obj=object_before(approved,start,tokenize)
    arg=case_argument_before(approved,start,tokenize)
    if not obj or not arg or arg[1]!='に':
        return None
    with JapaneseIME() as ime:
        if not ime.available:
            return None
        reading=ime.phonetic(approved)
    if not reading or not reading.endswith(tail):
        return None
    prefix=reading[:-len(tail)]
    if not original.startswith(prefix):
        return None
    typed_tail=original[len(prefix):]
    if len(typed_tail)==len(tail):
        physical=any(repair.reading==tail
                     and repair.operation=='adjacent_substitution'
                     for repair in key_repairs(typed_tail))
    elif len(typed_tail)==len(tail)+1:
        physical=any(repair.reading==tail
                     and repair.operation=='adjacent_intrusion'
                     and repair.position==len(typed_tail)-1
                     for repair in key_repairs(typed_tail))
    else:
        physical=False
    if not physical:
        return None
    projected=project_first_words(tail,store,dictionary,decisions,tokenize)
    if not projected or projected[0]==tail:
        return None
    face=projected[0]
    before=approved[:start]
    object_fit=candidate_evidence(obj,face,'',before=before)
    case_fit=candidate_evidence(arg[0],face,'',before=before,case=arg[1])
    if not (object_fit and object_fit['shared_roles']
            and case_fit and case_fit['shared_roles']):
        return None
    accepted,reason=engine._check_replacement(approved,
        (start,len(approved),face,'かな入力'),store,tokenize,dictionary,decisions,
        conv_taken=((start,len(approved)),),spelling=True)
    if accepted is None or tuple(accepted[:3])!=(start,len(approved),face):
        return None
    desired=approved[:start]+face
    if engine._odd_spans_for_line(desired,tokenize,[],store,dictionary,include_pending=False):
        return None
    return desired,((start,len(approved),face),)
