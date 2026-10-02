"""Whole native question/genitive readings disambiguate source kana splits."""
def _closed_structure(reading,surface,descriptors):
    import morphology as M
    from semantic_roles import nominal_roles
    from ime_question_contrast import _QUESTION_SUBJECTS
    from ime_postevent_contrast import _CONTENT_TRANSFORMATIONS
    if not reading or any(not ('ぁ'<=c<='ゖ' or c=='ー') for c in reading):return None
    parts=M.tokenize(surface)
    if len(parts)!=4 or not all(t.has_reading for t in parts):return None
    if any(a.end!=b.start for a,b in zip(parts,parts[1:])):return None
    a,b,c,d=parts
    question=(a.surface in _QUESTION_SUBJECTS and a.pos=='名詞' and a.pos_sub.startswith('代名詞')
              and b.surface=='が' and b.pos=='助詞' and b.pos_sub.startswith('格助詞')
              and c.pos=='名詞' and not c.pos_sub.startswith(('固有名詞','接尾','非自立'))
              and d.surface=='か' and d.pos=='助詞' and '終助詞' in d.pos_sub)
    postevent=(a.surface in _CONTENT_TRANSFORMATIONS and a.pos=='名詞' and a.pos_sub=='サ変接続'
               and b.surface=='後' and b.pos=='名詞' and b.pos_sub.startswith('接尾')
               and c.surface=='の' and c.pos=='助詞' and c.pos_sub=='連体化'
               and d.pos=='名詞' and {'text','shape'}<=nominal_roles(d.surface))
    if not (question or postevent):return None
    # Dictionary-attested lexical readings are checked separately from IME
    # boundaries. A kana token split is not stronger than the complete word.
    for t in parts:
        if not any(rd==t.reading and pos.split(',')[0]==t.pos
                   for pos,form,base,rd in M.dictionary_inflections(t.surface) or ()):return None
    # The complete IME reading must cover the field once, without gaps.
    if (not descriptors or descriptors[0][0]!=0 or descriptors[0][2]!=0
        or descriptors[-1][1]!=len(surface) or descriptors[-1][3]!=len(reading)
        or any(x[1]!=y[0] or x[3]!=y[2] for x,y in zip(descriptors,descriptors[1:]))):return None
    for t in parts:
        if t.pos!='助詞':continue
        unit=next((x for x in descriptors if x[0]==t.start and x[1]==t.end),None)
        if not unit or reading[unit[2]:unit[3]]!=t.surface:return None
    return 'nominal_question' if question else 'symbolic_postevent'

def complete_field(text,current,store,dictionary,decisions,tokenize):
    import corrector as engine
    from ime_language import JapaneseIME
    if not text or any(not ('ぁ'<=c<='ゖ' or c=='ー') for c in text):return None
    if len(text)>80 or not ('が' in text and text.endswith('か') or 'ごの' in text):return None
    with JapaneseIME() as ime:
        if not ime.available:return None
        first=ime.convert_words(text)
        if not first or first[0]==text or not _closed_structure(text,*first):return None
        back=ime.reverse_words(first[0])
        if not back or back[0]!=text:return None
    accepted,reason=engine._check_replacement(text,(0,len(text),first[0],'かな入力'),store,tokenize,dictionary,decisions,
        conv_taken=((0,len(text)),),spelling=True,ime_first_proof=True)
    if accepted is None or tuple(accepted[:3])!=(0,len(text),first[0]):return None
    if first[0]==current:return None
    return first[0],((0,len(current),first[0]),)
