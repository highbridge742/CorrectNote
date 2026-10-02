# -*- coding: utf-8 -*-
"""Native noun spellings for a kana head split into orphan function words."""


def frames(source):
    import morphology as M
    from ime_inverse_gate import _CORRECTION_CACHE
    from ime_language import JapaneseIME
    from literal_examples import protected_ranges, overlaps
    cache = _CORRECTION_CACHE.get()
    key = ('orphan_genitive_spelling', source)
    if cache is not None and key in cache:
        return cache[key]
    out = []
    lo = 0
    protected = protected_ranges(source)
    for hi, end in [(m.start(), m.end()) for m in M.COLUMN_SEPARATOR.finditer(source)] + [(len(source), len(source))]:
        field = source[lo:hi]
        parts = M.tokenize(field)
        for i, (case, modifier, noun) in enumerate(zip(parts, parts[1:], parts[2:])):
            if not (case.pos == '助詞' and case.pos_sub.startswith('格助詞')
                    and (i == 0 or parts[i - 1].pos == '助詞')
                    and modifier.pos == '連体詞' and modifier.surface.endswith('の')
                    and noun.pos == '名詞' and noun.has_reading
                    and case.end == modifier.start and modifier.end == noun.start):
                continue
            reading = field[case.start:modifier.end - 1]
            if not reading or not all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in reading):
                continue
            if overlaps(lo + case.start, lo + noun.end, protected):
                continue
            # The original orphan case and following noun establish the
            # scope before asking for a spelling of the unchanged reading.
            frame = dict(start=lo + case.start, end=lo + noun.end,
                         evidence_end=lo + noun.end, reading=reading + 'の' + noun.reading, candidates=())
            out.append(frame)
            with JapaneseIME() as ime:
                phrase = ime.convert(reading + 'の' + noun.reading) if ime.available else None
            tail = 'の' + noun.surface
            if not phrase or not phrase.endswith(tail):
                continue
            face = phrase[:-len(tail)]
            if face == reading or not M.native_spelling_only(reading, face):
                continue
            tokens = M.tokenize(face)
            if tokens and all(t.pos == '名詞' and t.has_reading for t in tokens):
                frame['candidates'] = (phrase,)
        lo = end
    result = tuple(out)
    if cache is not None:
        cache[key] = result
    return result


def _split_question_noun_frames(source):
    """A bare noun/ka/case can be a split lexical reading, not a question.

    Preserve native interrogatives, explicit alternatives and a clause with
    its own subject. Compare exact native noun spellings only after locating
    the doubtful source boundary; no typed/answer pair or key edit is used.
    """
    if 'か' not in source:return ()
    from morphology import tokenize
    from oddness import _QUESTION_PRONOUNS
    from contextual_repair import _source_clause_bounds
    from literal_examples import protected_ranges,overlaps
    from reading_segments import _native_nominal_reading_faces
    from kango_tier import known_usage_tier
    parts=tokenize(source);out=[];protected=None
    for i,(noun,question,case) in enumerate(zip(parts,parts[1:],parts[2:])):
        if not (noun.pos=='名詞' and not noun.pos_sub.startswith(('固有名詞','代名詞'))
                and question.surface=='か' and question.pos=='助詞'
                and case.pos=='助詞' and case.pos_sub.startswith('格助詞')
                and noun.end==question.start and question.end==case.start
                and all(t.has_reading for t in (noun,question,case))):continue
        lo,hi=_source_clause_bounds(source,noun.start,case.end)
        preceding=[t for t in parts[:i] if lo<=t.start]
        nominal=[noun]
        for t in reversed(preceding):
            if t.end!=nominal[0].start or t.pos not in ('名詞','接頭詞'):break
            nominal.insert(0,t)
        # A non-independent nominal needs an actual modifier. Its bare
        # attachment to a noun can instead be an unconverted compound
        # head, but only a positive relation to that head may justify it.
        dependent=noun.pos_sub.startswith('非自立')
        if dependent and len(nominal)<2:continue
        # Native question expressions and alternatives keep their scope.
        if any(t.surface in _QUESTION_PRONOUNS for t in nominal):continue
        if any(t.surface=='か' and t.pos=='助詞' for t in preceding):continue
        previous=next((t for t in reversed(preceding) if t.end==nominal[0].start),None)
        if previous and (previous.pos in ('動詞','形容詞','助動詞')
            or previous.pos=='助詞' and previous.pos_sub.startswith(('格助詞','係助詞'))):continue
        if any(not t.has_reading or t.pos_sub.startswith('固有名詞') for t in nominal):continue
        a,b=nominal[0].start,question.end
        if protected is None:protected=protected_ranges(source)
        if overlaps(a,b,protected):continue
        # The compound's unchanged head remains context. Requiring a
        # dictionary entry for the entire productive compound hides its
        # independently attested final noun. A shared positive nominal
        # relation must justify that retained head; unknown is not enough.
        from semantic_roles import nominal_compound_support
        for offset in range(len(nominal)):
            start=nominal[offset].start
            reading=''.join(t.reading for t in nominal[offset:])+question.reading
            prefix=source[a:start]
            if dependent and not prefix:continue
            faces=tuple(face for face in _native_nominal_reading_faces(reading)
                if face!=source[start:b] and known_usage_tier(face) in (1,2)
                and (not prefix or nominal_compound_support(prefix,face)))
            if not faces:continue
            out.append(dict(start=start,end=b,evidence_end=case.end,reading=reading,candidates=faces,
                reason='名詞と格の間のかが独立した疑問を作らず、同じ読みの日常的な一語の区切りと競合しています'))
    return tuple(out)


def split_nominal_evidence(source,start,end,surface):
    """The same native lexical reading repairs an independently split head.

    All overlapping candidate paths see the same original-boundary proof.
    This supports a spelling/segmentation interpretation, rather than making
    a cheaper unrelated word win merely through its dictionary cost.
    """
    for frame in split_question_noun_frames(source):
        if (frame['start']==start and frame['end']==end
                and surface in frame['candidates']):
            return dict(kind='native_nominal_boundary',reading=frame['reading'],
                start=start,end=end,surface=surface,reason=frame['reason'])
    return None


def split_question_noun_frames(source):
    from ime_inverse_gate import _CORRECTION_CACHE
    cache=_CORRECTION_CACHE.get();key=('native_nominal_question_boundary',source)
    if cache is not None and key in cache:return cache[key]
    result=_split_question_noun_frames(source)
    if cache is not None:cache[key]=result
    return result
