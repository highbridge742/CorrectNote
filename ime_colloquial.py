# -*- coding: utf-8 -*-
"""Source-local IME evidence for an otherwise unrecognized ra-row verb.

Only the original line receives an alternative grammatical tokenization.
IME output does not authorize a correction or add a global dictionary entry.
"""


def _source_tokens(source, tokenize):
    from morphology import HAS_JANOME, allows_bare_clause_object, dictionary_paradigms
    if (not HAS_JANOME or getattr(tokenize,'analysis_backend',None)!='janome'
            or len(source) < 4 or '\t' in source
            or any(ord(char)>0xffff for char in source)):
        return None
    actual = tokenize(source)
    if not actual:
        return None
    # Only a noun-like kana fragment near a ra-row ending can be the
    # otherwise missing verb. This cheap preflight is not an anomaly proof.
    if not any(t[1].startswith('名詞') and len(t[0])>=2
            and all('ぁ'<=char<='ゖ' or 'ァ'<=char<='ヶ' or char=='ー'
                    for char in t[0])
            and any(char in 'らりるれろっ' for char in source[t[4]:t[4]+3])
            for t in actual):
        return None
    from ime_language import JapaneseIME
    with JapaneseIME() as ime:
        if not ime.available:
            return None
        reverse = ime.reverse_words(source)
        if not reverse or not reverse[1]:
            return None
        reading, words = reverse
        possible=[]
        source_words=[]
        for row in words:
            a,z,c,d,pos,flags=row
            if (flags & 16 or not 0<=a<z<=len(source)
                    or not 0<=c<d<=len(reading)):
                continue
            stem=source[a:z]
            if (not all('ぁ'<=char<='ゖ' or 'ァ'<=char<='ヶ' for char in stem)
                    or any(t[3]==a and t[1].startswith('動詞:自立') for t in actual)):
                continue
            if pos!=208:
                if pos not in (100,101):
                    continue
                from seed_japanese import is_unit
                from morphology import katakana_to_hiragana
                from corrector import _KANA_TO_ROMAJI
                # The seed attests the lemma but stores no conjugation class.
                # An i/e stem can be ichidan (オチる/カケる), so it does not
                # independently license a godan inflection.
                last=_KANA_TO_ROMAJI.get(katakana_to_hiragana(stem[-1]), '')
                if (is_unit(stem+'る') is not True
                        or not last or last[-1] not in 'auo'):
                    continue
            # The whole-line dictionary may fuse adjacent unknown verbs
            # into one noun. Each split will still need its own proof.
            source_words.append((a,z,c,d,stem,reading[c:d],(),pos))
            prefix=tuple(t for t in actual if t[4]<=a)
            if ''.join(t[0] for t in prefix)!=source[:a]:
                continue
            possible.append((a,z,c,d,stem,reading[c:d],prefix,pos))
        if len(source_words)>1:
            return _composed_source_tokens(source, tokenize, source_words)
        if len(possible)!=1:
            return None
        a,z,c,d,stem,reading_stem,prefix_tokens,wdd_pos=possible[0]
        lemma, lemma_reading = stem + 'る', reading_stem + 'る'
        back = ime.reverse_words(lemma)
        if (not back or back[0] != lemma_reading or len(back[1])!=2
                or back[1][0][:5] != (0,len(stem),0,len(reading_stem),wdd_pos)
                or back[1][0][5] & 16
                or back[1][1][:5] != (len(stem),len(lemma),
                                      len(reading_stem),len(lemma_reading),0)):
            return None
        if wdd_pos==208:
            forward = ime.convert_words(lemma_reading)
            if not forward or forward[0] != lemma or len(forward[1]) != 2:
                return None
            first, second = forward[1]
            if (first[:5] != back[1][0][:5] or first[5] & 16
                    or second[:5] != back[1][1][:5]):
                return None

    from pos_grammar import _GODAN_ROW
    ending = _GODAN_ROW['る']
    forms = (("る", "基本形"), (ending[0], "未然形"),
             (ending[1], "連用形"), (ending[2], "仮定形"),
             (ending[3], "未然ウ接続"), (ending[4], "連用タ接続"))
    tail = source[z:]
    witnesses = []
    for carrier in ('走る', '登る'):
        phrase = carrier[:-1] + tail
        pieces = tokenize(phrase)
        if not pieces or pieces[0][3] != 0 or pieces[0][4] <= 0:
            return None
        form = pieces[0][6]
        observed = next((part for part, name in forms
                         if name == form and pieces[0][0] == carrier[:-1] + part), None)
        if (observed is None or pieces[0][0] != carrier[:-1] + observed
                or not pieces[0][1].startswith('動詞:自立')):
            return None
        if not any(pos.startswith('動詞,自立,') and base == carrier
                   and form_name == form and rd == pieces[0][2]
                   for pos, kind, form_name, base, rd
                   in dictionary_paradigms(pieces[0][0]) or ()):
            return None
        head_end = pieces[0][4]
        suffix = tuple((s, p, r, a-head_end, b-head_end, known, f)
                       for s, p, r, a, b, known, f in pieces[1:])
        witnesses.append((observed, form, suffix))
    if witnesses[0] != witnesses[1]:
        return None
    observed, form, suffix = witnesses[0]
    word = stem + observed
    if not source[a:].startswith(word):
        return None
    written_reading = reading_stem + observed
    if any(row[4] == written_reading for row in dictionary_paradigms(word) or ()):
        return None
    result = list(prefix_tokens)
    result.append((word, '動詞:自立', written_reading, a, a+len(word), True, form))
    result += [(s, p, r, start+a+len(word), end+a+len(word), known, f)
               for s, p, r, start, end, known, f in suffix]
    after = result[len(prefix_tokens)+1:]
    if ''.join(t[0] for t in result) != source:
        return None
    if after and after[0][1].startswith(('助動詞','助詞')):
        from pos_grammar import _PIECES, continuation_state
        state=continuation_state(form) or ('TSU' if form=='連用タ接続' else None)
        remaining=source[a+len(word):]
        if not state or not any(remaining.startswith(piece)
                                for piece,next_state in _PIECES[state]):
            return None
    # A source-only verb reading must not certify a malformed polite clause.
    # A finite polite suffix cannot directly modify a noun, while a plain
    # godan form can (メモる資料). A conjunctive particle or punctuation starts
    # a new clause and ends this local check.
    if after and form=='基本形' and after[0][0] in ('です','でした'):
        return None
    if after and after[0][0].startswith(('ます','まし','ませ')):
        for token in after[1:]:
            if token[1].startswith(('記号','助詞:接続助詞')):
                break
            if token[1].startswith('名詞'):
                return None
    # The IME lemma proves the head only. A separate, unexplained suffix
    # must keep its ordinary anomaly mark instead of borrowing that proof.
    if not all(t[5] or t[1].startswith('記号') for t in after):
        return None
    # Ra-row sokuon is unvoiced. A noun-like parse of っで may escape the
    # ordinary anomaly detector; IME verb evidence must not certify it.
    if form == '連用タ接続' and (not after
            or after[0][0] not in ('て', 'た', 'たら', 'たり')):
        return None
    if (after and form == '基本形' and after[0][0] == 'を'
            and after[0][1].startswith('助詞')
            and not allows_bare_clause_object(source[after[0][4]:])):
        return None
    import oddness
    if any(oddness.polite_aux_mismatch(a, b)
           or oddness.past_auxiliary_mismatch(a, b, include_finite_verbs=True)
           or oddness.auxiliary_connection_mismatch(a, b, result[i-1] if i else None)
           for i, (a, b) in enumerate(zip(result, result[1:]))):
        return None
    return result



def _composed_source_tokens(source, tokenize, possible):
    # Each WDD word must independently prove its own lemma and inflection.
    # Splitting at the next source word keeps the IME evidence local; a
    # malformed sibling never inherits the proof of a valid one.
    if len(possible)>3:
        return None
    starts=[row[0] for row in possible]
    if starts!=sorted(set(starts)):
        return None
    result=[]
    for i,(a,z,c,d,stem,reading_stem,prefix,wdd_pos) in enumerate(possible):
        start=0 if i==0 else a
        end=starts[i+1] if i+1<len(starts) else len(source)
        if not start<=a<z<=end:
            return None
        part=_source_tokens(source[start:end], tokenize)
        if (part is None
                or not any(t[3]+start==a and t[0].startswith(stem)
                           and t[1].startswith('動詞:自立') for t in part)):
            return None
        if i+1<len(possible):
            trailing=[t for t in part if t[3]+start>=z]
            linked=any(t[1].startswith('助詞:接続助詞')
                       or t[0] in ('、','。','！','？','!','?')
                       for t in trailing)
            linked=linked or any(left[0]=='ず' and right[0]=='に'
                                 for left,right in zip(trailing,trailing[1:]))
            if not linked:
                return None
        result.extend((s,p,r,left+start,right+start,known,form)
                      for s,p,r,left,right,known,form in part)
    if ''.join(t[0] for t in result)!=source:
        return None
    import oddness
    if any(oddness.polite_aux_mismatch(a,b)
           or oddness.past_auxiliary_mismatch(a,b,include_finite_verbs=True)
           or oddness.auxiliary_connection_mismatch(a,b,result[i-1] if i else None)
           for i,(a,b) in enumerate(zip(result,result[1:]))):
        return None
    return result


def source_tokenizer(source, tokenize):
    """Return original tokenizer unless this one source has independent proof."""
    try:
        proven = _source_tokens(source, tokenize)
    except (ImportError, OSError, AttributeError):
        return tokenize
    if proven is None:
        return tokenize

    # The inverse-reading gate checks a field without its final punctuation.
    # Use the same source evidence there; never apply it to a trial candidate.
    field = source[:-1] if source[-1] in '。！？!?' else source
    field_tokens = [t for t in proven if t[4] <= len(field)]
    if ''.join(t[0] for t in field_tokens) != field:
        field_tokens = None

    def scoped(text):
        if text == source:
            return list(proven)
        if field_tokens is not None and text == field:
            return list(field_tokens)
        return tokenize(text)

    scoped.analysis_backend = getattr(tokenize, 'analysis_backend', None)
    return scoped
