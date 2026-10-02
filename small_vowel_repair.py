"""Same-key small-vowel repair with independent lexical and clause proof."""

_FULL_VOWEL = dict(zip('ぁぃぅぇぉ', 'あいうえお'))


def proposed_keys(line, store, dictionary, decisions=None):
    """Offer a physical Shift edit only when its word and continuation exist."""
    if not dictionary or not any(c in _FULL_VOWEL for c in line):return ()
    from kana_layout import nearby_candidates
    from kana_spelling import _fields, project
    from reading_segments import (native_attested_prefix_noun_faces,
        native_written_sahen_relative,native_nominal_phrase_faces,
        native_nominal_spelling_faces)
    from pos_grammar import odd_kana_spans,prolonged_quotative
    from morphology import tokenize as native_tokenize
    import corrector as engine

    tokenize=engine.make_tokenizer(store)
    accepted=[]
    for field_start,field_end in _fields(line):
        source=line[field_start:field_end]
        if not source or not all('ぁ'<=c<='ゖ' or c=='ー' for c in source):continue
        # A drawn-out voice before quotative と is a positive source shape.
        if prolonged_quotative(source):continue
        source_odd=bool(odd_kana_spans(source+'\t',dictionary,store))
        choices=[]
        for offset,small in enumerate(source):
            if small not in _FULL_VOWEL:continue
            full=_FULL_VOWEL[small]
            if full not in (key for key,_distance in nearby_candidates(
                    small,max_dist=0.35,include_phonetic=False)):continue
            candidate=source[:offset]+full+source[offset+1:]
            projected=project(candidate,store,dictionary,decisions)
            if projected is None:continue
            projected_surface,edits=projected
            primary=next(((lo,hi,face) for lo,hi,face in edits
                if lo<=offset<hi and face in native_nominal_spelling_faces(candidate[lo:hi])),None)
            if primary is None:continue
            _,primary_end,primary_face=primary
            relative=False
            if primary_face in native_attested_prefix_noun_faces(candidate[primary[0]:primary_end]):
                tail=candidate[primary_end:]
                relative=(not tail or native_written_sahen_relative(primary_face+tail)
                    or any(lo>=primary_end and hi==len(candidate)
                        and native_written_sahen_relative(
                            primary_face+candidate[primary_end:lo])
                        and native_nominal_phrase_faces(candidate[lo:hi])
                        for lo,hi,face in edits))
            finite=False
            if source_odd:
                written=projected_surface
                try:
                    from ime_language import JapaneseIME
                    with JapaneseIME() as ime:
                        if ime.available:written=ime.convert(candidate) or written
                except (ImportError,OSError,AttributeError):pass
                parts=native_tokenize(written)
                finite=bool(parts and all(t.has_reading for t in parts)
                    and parts[-1].pos in ('助動詞','動詞','形容詞')
                    and parts[-1].infl_form=='基本形'
                    and not engine._odd_spans_for_line(written,tokenize,[],store,dictionary))
            if not relative and not finite:continue
            if relative and engine._odd_spans_for_line(
                    projected_surface,tokenize,[],store,dictionary):continue
            choices.append((field_start+offset,field_start+offset+1,full,'かな入力'))
        if len(choices)==1:accepted.append(choices[0])
    return tuple(accepted)