# -*- coding: utf-8 -*-
"""Finish broken kana fields from attested same-key Shift readings."""

_SHIFTED_TO_FULL=str.maketrans(dict(zip('ぁぃぅぇぉっゃゅょ','あいうえおつやゆよ')))
_SHIFTED=frozenset('ぁぃぅぇぉっゃゅょを')


def _known_shift_reading(source, dictionary, ime, native):
    """Replace disjoint source spans only when a dictionary reading is unique."""
    world=getattr(dictionary,'_world',None)
    if not world:
        return None
    by_keys={}
    for reading in world:
        if len(reading)<2:
            continue
        keys=reading.translate(_SHIFTED_TO_FULL)
        if keys!=reading:
            by_keys.setdefault(keys,set()).add(reading)
    proved={}
    def whole_word(reading):
        if reading not in proved:
            face=ime.convert(reading)
            reverse=ime.reverse_words(face) if face else None
            tokens=native.tokenize(face) if face else ()
            proved[reading]=bool(reverse and reverse[0]==reading
                and len(tokens)==1 and tokens[0].start==0
                and tokens[0].end==len(face) and tokens[0].has_reading
                and tokens[0].pos in ('名詞','動詞','形容詞','副詞','感動詞'))
        return proved[reading]
    out=[];index=0;changed=False
    while index<len(source):
        found=None
        for end in range(len(source),index+1,-1):
            keys=source[index:end]
            variants=by_keys.get(keys,())
            if not variants or dictionary.is_world_reading(keys):
                continue
            attested=[reading for reading in variants if whole_word(reading)]
            if not attested:
                continue
            if len(attested)!=1:
                return None
            found=(end,attested[0])
            break
        if found:
            end,reading=found
            out.append(reading);index=end;changed=True
        else:
            out.append(source[index]);index+=1
    return ''.join(out) if changed else None


_FULL_TO_SMALL=dict(zip('あいうえおつやゆよ','ぁぃぅぇぉっゃゅょ'))


def _keeps_finite_auxiliary(source, parts):
    """A repaired key must not turn the existing polite tail into a noun."""
    tail=source.rstrip('。！？!?.,，．\t \r\n')
    lexical=[part for part in parts if part.pos!='記号']
    last=lexical[-1] if lexical else None
    return all(not tail.endswith(aux) or
               bool(last and last.surface==aux and last.pos=='助動詞')
               for aux in ('ます','です'))


def _trial_missing_shift(source,ime,engine,store,dictionary,decisions,tokenize,native,source_anomalous=False):
    """Try every one-key Shift omission, keeping only a unique full word."""
    accepted={}
    for position,pressed in enumerate(source):
        intended=_FULL_TO_SMALL.get(pressed)
        if intended is None:
            continue
        reading=source[:position]+intended+source[position+1:]
        first=ime.convert(reading)
        reverse=ime.reverse_words(first) if first else None
        if not reverse or reverse[0]!=reading:
            continue
        parts=native.tokenize(first)
        if not _keeps_finite_auxiliary(source,parts):
            continue
        if (any(not part.has_reading for part in parts if part.pos!='記号')
                or any(a.pos=='名詞' and b.pos=='名詞' and a.end==b.start
                       for a,b in zip(parts,parts[1:]))):
            continue
        units=[unit for unit in reverse[1] if unit[2]<=position<unit[3]]
        if len(units)!=1:
            continue
        unit=units[0]
        if not any(part.start==unit[0] and part.end==unit[1]
                   and part.has_reading and part.pos in ('名詞','動詞','形容詞','副詞')
                   and part.reading==reading[unit[2]:unit[3]] for part in parts):
            continue
        if engine._odd_spans_for_line(first,tokenize,[],store,dictionary,include_pending=False):
            continue
        checked,reason=engine._check_replacement(source,
            (0,len(source),first,'かな入力'),store,tokenize,dictionary,
            decisions,conv_taken=((0,len(source)),),
            ime_shift_proof=source_anomalous)
        if checked is not None and tuple(checked[:3])==(0,len(source),first):
            accepted[first]=reading
    return next(iter(accepted)) if len(accepted)==1 else None



def _written_mid_final_quote(source, tokenize):
    """Native source has a bare noun, medial final/quote seam, then a verb."""
    if any(c in source for c in '「」『』"'):
        return False
    parts = list(tokenize(source))
    if not parts or ''.join(part[0] for part in parts) != source:
        return False
    return any(i and i + 1 < len(parts) - 1
        and part[1].startswith('助詞:終助詞')
        and parts[i-1][1].startswith('名詞')
        and parts[i+1][1].startswith('助詞:格助詞:引用')
        and any(t[1].startswith('動詞') for t in parts[i+2:])
        for i, part in enumerate(parts))


def _written_multi_noun_case(source, tokenize):
    """The source IME split has adjacent nouns before an explicit case."""
    from morphology import tokenize as native_tokenize
    from reading_segments import native_lexical_phrase
    parts=list(native_tokenize(source))
    for i,case in enumerate(parts):
        if (case.surface not in ('を','に') or case.pos!='助詞'
                or not case.pos_sub.startswith('格助詞') or i<2):
            continue
        start=i-1
        while (start>=0 and parts[start].pos=='名詞'
                and parts[start].has_reading and parts[start].end==parts[start+1].start):
            start-=1
        if i-start-1>=2 and any(part.pos=='動詞' for part in parts[i+1:]):
            # Written nominal proof also owns the Shift fallback's boundary.
            # Re-reading a valid group in kana supplies no missing-key evidence.
            nominal=source[parts[start+1].start:case.start]
            from morphology import dictionary_inflections
            # Multiple ordinary written nouns alone do not establish a
            # missing Shift. This is only a limit of this fallback; ordinary
            # anomaly/meaning analysis still examines the whole compound.
            ordinary=all(any(pos.startswith(('名詞,一般,','名詞,サ変接続,'))
                and base==t.surface and rd==t.reading
                for pos,form,base,rd in dictionary_inflections(t.surface) or ())
                for t in parts[start+1:i])
            if native_lexical_phrase(nominal,tokenize) or ordinary:continue
            return True
    return False


def _symbolic_first_reading(source, ime):
    """Accept only a unique phonetic whose first IME result is the source."""
    if (len(source)<3 or source[0] not in '=+-*/#'
            or not '\u3400'<=source[1]<='\u9fff'):
        return None
    phonetic=ime.phonetic(source)
    if not phonetic or any(not ('ぁ'<=c<='ゖ' or c=='ー') for c in phonetic):
        return None
    from kana_layout import DAKUTEN_BASE
    trials={phonetic}
    trials.update(phonetic[:i]+DAKUTEN_BASE[c]+phonetic[i+1:]
        for i,c in enumerate(phonetic) if c in DAKUTEN_BASE)
    matched={reading for reading in trials if ime.convert(reading)==source}
    return next(iter(matched)) if len(matched)==1 else None


def complete_written_field(source, approved, store, dictionary, decisions, tokenize):
    """A source-side broken quotative allows one whole-field Shift trial."""
    if not source or source != approved or dictionary is None:
        return None
    symbolic=bool(len(source)>=3 and source[0] in '=+-*/#'
                  and '\u3400'<=source[1]<='\u9fff')
    if not (symbolic or _written_mid_final_quote(source, tokenize)
            or _written_multi_noun_case(source, tokenize)):
        return None
    import corrector as engine
    import morphology as native
    from ime_language import JapaneseIME
    from pos_grammar import odd_kana_spans
    with JapaneseIME() as ime:
        if not ime.available:
            return None
        if symbolic:
            reading=_symbolic_first_reading(source,ime)
        else:
            morph=ime.reverse_words(source)
            reading=morph[0] if morph and ime.convert(morph[0])==source else None
        if not reading or (not symbolic and not odd_kana_spans(
                reading + '\t', dictionary, store)):
            return None
        first = _trial_missing_shift(reading, ime, engine, store, dictionary,
                                     decisions, tokenize, native)
        if not first or first == source:
            return None
        checked, reason = engine._check_replacement(source,
            (0, len(source), first, 'かな入力'), store, tokenize, dictionary,
            decisions, conv_taken=((0, len(source)),))
        return first if checked is not None and tuple(checked[:3]) == (
            0, len(source), first) else None


def _word_edits(source, approved, first, ime):
    """Use IME word boundaries even after an earlier partial repair."""
    fallback=((0,len(approved),first),)
    reverse=ime.reverse_words(first)
    if not reverse or len(reverse)!=2:
        return fallback
    reading,units=reverse
    if approved!=source:
        from difflib import SequenceMatcher
        proposed=[]
        for tag,lo,hi,start,end in SequenceMatcher(
                None,approved,first,autojunk=False).get_opcodes():
            if tag=='equal':
                continue
            covered=[unit for unit in units if unit[0]<end and start<unit[1]]
            if (not covered or covered[0][0]!=start
                    or covered[-1][1]!=end
                    or any(a[1]!=b[0] or a[3]!=b[2]
                           for a,b in zip(covered,covered[1:]))
                    or not lo<hi):
                proposed=[]
                break
            # The old text and final IME word must still have the same
            # reading; only its written form is new at this stage.
            expected=reading[covered[0][2]:covered[-1][3]]
            if ime.phonetic(approved[lo:hi])!=expected:
                proposed=[]
                break
            proposed.append((lo,hi,first[start:end]))
        if proposed:
            rebuilt=[];edge=0
            for lo,hi,face in proposed:
                rebuilt.extend((approved[edge:lo],face));edge=hi
            rebuilt.append(approved[edge:])
            if ''.join(rebuilt)==first:
                return tuple(proposed)
    if len(reading)!=len(approved):
        return fallback
    different=[(old,new) for old,new in zip(approved,reading) if old!=new]
    if len(different)>1 or any(_FULL_TO_SMALL.get(old)!=new
                              and _FULL_TO_SMALL.get(new)!=old for old,new in different):
        return fallback
    read_edge=face_edge=0
    edits=[]
    for unit in units:
        if len(unit)<4:
            return fallback
        start,end,lo,hi=unit[:4]
        if (start!=face_edge or lo!=read_edge or not start<end<=len(first)
                or not lo<hi<=len(reading)):
            return fallback
        face=first[start:end]
        if approved[lo:hi]!=face:
            edits.append((lo,hi,face))
        read_edge=hi;face_edge=end
    if read_edge!=len(reading) or face_edge!=len(first) or not edits:
        return fallback
    rebuilt=[];edge=0
    for lo,hi,face in edits:
        rebuilt.extend((approved[edge:lo],face));edge=hi
    rebuilt.append(approved[edge:])
    return tuple(edits) if ''.join(rebuilt)==first else fallback


def _prefer_source_reading(source, shifted, plain, reverse, engine, store,
                           dictionary, decisions, tokenize, native):
    """Compare an existing Shift repair with a proved unchanged reading."""
    if (not shifted or shifted==plain or any(c in _SHIFTED for c in source)
            or not plain or not reverse or reverse[0]!=source):return shifted
    parts=native.tokenize(plain)
    if (not _keeps_finite_auxiliary(source,parts)
            or any(not p.has_reading for p in parts if p.pos!='記号')
            or any(a.end==b.start and (a.pos==b.pos=='名詞'
                    or a.pos==b.pos=='助詞' and a.surface in 'がをにへでと'
                       and b.surface in 'がをにへでと') for a,b in zip(parts,parts[1:]))):
        return shifted
    from semantic_roles import native_case_support
    if len(native_case_support(shifted))>len(native_case_support(plain)):
        return shifted
    if engine._odd_spans_for_line(plain,tokenize,[],store,dictionary,include_pending=False):return shifted
    checked,_=engine._check_replacement(source,(0,len(source),plain,'かな入力'),
        store,tokenize,dictionary,decisions,conv_taken=((0,len(source)),))
    return plain if checked is not None and tuple(checked[:3])==(0,len(source),plain) else shifted


def complete_field(source, approved, store, dictionary, decisions, tokenize):
    """Use source anomalies and read-only IME trials to finish a Shift slip.

    A first-conversion mismatch or source grammar anomaly is established
    before any Shift candidate exists. The answer is never supplied to the
    generator, and every candidate uses the ordinary final validator.
    """
    import corrector as engine
    import morphology as native
    from pos_grammar import odd_kana_spans
    from ime_language import JapaneseIME

    if (not source or not approved or not dictionary
            or any(not ('ぁ'<=c<='ゖ' or c=='ー') for c in source)):
        return None
    source_odd=odd_kana_spans(source+'\t',dictionary,store)
    with JapaneseIME() as ime:
        if not ime.available:
            return None
        source_first=ime.convert(source)
        source_reverse=ime.reverse_words(source_first) if source_first else None
        source_mismatch=bool(source_first and
            (not source_reverse or source_reverse[0]!=source))
        # The ordinary source mark can expose an impossible particle seam
        # that kana-only parsing misses. Ask only after the cheap source
        # evidence failed, still before generating any Shift candidate.
        source_marked=False
        if not source_odd and not source_mismatch:
            source_marked=bool(engine._odd_spans_for_line(
                source,tokenize,[],store,dictionary))
            if not source_marked and source_first and source_reverse and source_reverse[0]==source:
                # The source's first IME conversion can expose a broken
                # native seam hidden by its fragmented kana tokenization.
                # No Shift trial or proposed correction exists at this point.
                source_marked=bool(engine._odd_spans_for_line(
                    source_first,tokenize,[],store,dictionary,include_pending=False))
            if not source_marked:
                return None
        if engine._chunk_is_intact(source,tokenize):
            return None
        def choose(shifted):
            return _prefer_source_reading(source,shifted,source_first,source_reverse,
                engine,store,dictionary,decisions,tokenize,native)
        reading=_known_shift_reading(source,dictionary,ime,native)
        if reading and not odd_kana_spans(reading+'\t',dictionary,store):
            first=ime.convert(reading)
            reverse=ime.reverse_words(first) if first else None
            if reverse and reverse[0]==reading:
                parts=native.tokenize(first)
                if (_keeps_finite_auxiliary(source,parts)
                        and not any(a.pos=='名詞' and b.pos=='名詞' and a.end==b.start
                            for a,b in zip(parts,parts[1:]))
                        and not engine._odd_spans_for_line(first,tokenize,[],store,dictionary,include_pending=False)):
                    checked,reason=engine._check_replacement(source,
                        (0,len(source),first,'かな入力'),store,tokenize,dictionary,
                        decisions,conv_taken=((0,len(source)),))
                    if checked is not None and tuple(checked[:3])==(0,len(source),first):
                        first=choose(first)
                        return (first,_word_edits(source,approved,first,ime)) if first and first!=approved else None
        first=_trial_missing_shift(source,ime,engine,store,dictionary,
                                   decisions,tokenize,native,
                                   source_anomalous=bool(source_odd or source_marked))
        first=choose(first)
        return (first,_word_edits(source,approved,first,ime)) if first and first!=approved else None
