# -*- coding: utf-8 -*-
"""読みが壊れていても辞書で裏付けられる区切りを返す。本文は補正しない。"""
def known_reading_prefix(text,dict_index,allow_short=False):
    if not text or not all('ぁ'<=c<='ゖ' or c=='ー' for c in text):
        return None
    from morphology import dictionary_base_pos
    # 完成した読みを細切れにしない。未知の残りを最低2字確保する。
    if dict_index.is_world_reading(text):
        return None
    for cut in range(len(text)-2,2,-1):
        if text[cut] in 'ぁぃぅぇぉゃゅょっー':
            continue
        head=text[:cut]
        surfaces=dict_index.surfaces_for_reading(head,limit=16,band=True)
        evidence=[]
        for surface in surfaces:
            positions=dictionary_base_pos(surface)
            if not positions:
                continue
            # 固有名詞・機能語・未知語を境界の確定根拠にしない。
            nouns=[p for p in positions if p.startswith('名詞,') and '固有名詞' not in p
                   and '接尾' not in p and '非自立' not in p]
            if nouns and len(nouns)==len(positions):
                evidence.append(surface)
        if evidence:
            return (head,text[cut:],'名詞',tuple(dict.fromkeys(evidence)))
    if allow_short and len(text)>=6 and text[2] not in 'ぁぃぅぇぉゃゅょっー':
        head=text[:2]
        positions=dictionary_base_pos(head) or ()
        if any(p.startswith('名詞,一般,') or p.startswith('名詞,サ変接続,') for p in positions):
            return (head,text[2:],'名詞',(head,))
    return None


def odd_partial_loanwords(line,dict_index,store,tokenize_fn):
    """既知名詞＋未知の長音終わりの読みを、既存の接続判定で検証。"""
    if dict_index is None or store is None or tokenize_fn is None:
        return []
    import re
    import corrector as C
    import loanword as L
    import oddness as O
    out=[]
    for match in re.finditer(r'[ぁ-ゖー]+',line):
        run=match.group()
        end=match.end()
        if not run.endswith('ー') and 'ー' in run:
            import pos_grammar as PG
            cut=run.rfind('ー')+1
            suffix=run[cut:]
            if PG.explain_kana_run(suffix,no_words=True):
                run=run[:cut];end=match.start()+cut
        if (match.start()>0 and end<len(line) and
                line[match.start()-1] in C._QUOTE_OPEN and line[end] in C._QUOTE_CLOSE):
            continue
        if not (7<=len(run)<=24 and run.endswith('ー')):
            continue
        if C._chunk_is_intact(run,tokenize_fn):
            continue
        evidence=known_reading_prefix(run,dict_index)
        if not evidence:
            continue
        head,tail,major,surfaces=evidence
        # 普通の伸ばし声を外来語と決めつけない。今回は2拍以上の
        # 小書き仮名＋長音を持つ未知語の接続だけを検証する。
        if len(tail)<4 or tail[-2] not in 'ゃゅょ':
            continue
        if L.katakana_for_hiragana(tail,store,min_length=3):
            continue
        # 既知の前半は読みを変更せず、候補探索前に接続を検査する。
        projected=surfaces[0]+L.hiragana_to_katakana(tail)
        if not O.is_odd_run(projected,tokenize_fn,store=store,dict_index=dict_index):
            continue
        out.append((match.start(),end,head,tail,surfaces[0]))
    return out


from functools import lru_cache


def _continuative_head(token):
    return (token.has_reading and token.pos == '動詞' and token.pos_sub == '自立'
            and token.infl_form == '連用形' and 2 <= len(token.surface) <= 8
            and token.reading == token.surface)


@lru_cache(maxsize=2048)
def continuative_reading_prefix(text):
    """辞書が原文のまま読める連用形。後半の修正候補から前半を逆算しない。"""
    if not text or not all('ぁ' <= c <= 'ゖ' for c in text):
        return None
    from morphology import _tokenize_janome
    raw = _tokenize_janome(text)
    if not raw or raw[0].start != 0 or not _continuative_head(raw[0]):
        return None
    size = len(raw[0].surface)
    # 連用形の名詞用法＋の＋既知名詞は、解析が「のく」等へ
    # 結合していても複合語の誤打としない。原文の読みだけで検証。
    tail = text[size:]
    if tail.startswith('の') and len(tail) > 1:
        from corrector import table_surfaces_for_reading
        from morphology import dictionary_base_pos
        if any(any(p.startswith('名詞,') for p in (dictionary_base_pos(face) or ()))
               for face in table_surfaces_for_reading(tail[1:], limit=6)):
            return None
    # 助詞で接続して読める後半を、複合語の誤打へ組み替えない。
    # に＋ゅ…のような未知境界は、この条件には当たらない。
    if (len(raw) > 1 and raw[1].pos in ('助詞', '助動詞')
            and all(t.has_reading for t in raw[1:])):
        return None
    if len(text) - size < 4 or text[size] in 'ぁぃぅぇぉゃゅょっー':
        return None
    return text[:size]


@lru_cache(maxsize=2048)
def short_nominal_reading(text):
    """普通名詞／連用形に続く名詞の読み。未知の拗音境界を戻すだけ。"""
    if not (6 <= len(text) <= 20 and all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in text)):
        return None
    from morphology import dictionary_base_pos, _tokenize_janome
    from corrector import table_surfaces_for_reading
    from pos_grammar import explain_kana_run
    # 前半は同音語ではなく原文の表記自体が名詞であることを確かめる。
    head = text[:2]
    # 読めている語を別の名詞2語へ組み替えない。未知語の先頭が
    # 拗音の途中で切れているときだけ、辞書の読みへ境界を戻す。
    raw = _tokenize_janome(text)
    if (not raw or not raw[0].has_reading
            or not any(not t.has_reading and t.surface[:1] in ('ゃ','ゅ','ょ')
                       for t in raw)):
        return None
    # 48-XN: 辞書が認める自立動詞の連用形も名詞を修飾できる。
    # 連体形・未然形や、語尾だけから推測した活用形には広げない。
    verbal = _continuative_head(raw[0])
    if verbal:
        head = raw[0].surface
    elif raw[0].surface != head or raw[0].pos != '名詞':
        return None
    def noun(surface):
        return any(p.startswith('名詞,一般,') or p.startswith('名詞,サ変接続,')
                   for p in (dictionary_base_pos(surface) or ()))
    size = len(head)
    if len(text) - size < 4 or (not verbal and not noun(head)) or text[size] in 'ぁぃぅぇぉゃゅょっー':
        return None
    for end in range(len(text), size + 3, -1):
        tail, suffix = text[size:end], text[end:]
        if suffix and not explain_kana_run(suffix, no_words=True, initial_state='Bw'):
            continue
        if suffix and suffix[0] in 'ぁぃぅぇぉゃゅょっー':
            continue
        for face in table_surfaces_for_reading(tail, limit=6):
            if noun(face):
                return (head, tail, suffix, face)
    return None


def native_lexical_phrase(text, tokenize):
    """A native whole noun with its particle, or an interjection being quoted.

    GPT-6 / 2026-09-11 / 48-YT. This is evidence about the actual spelling,
    not about any homophonic word in a reading table. Unknown pieces and
    incomplete predicates provide no such evidence.
    """
    if not text or tokenize is None:
        return False
    tokens=list(tokenize(text) or ())
    if (not 1<=len(tokens)<=2 or any(len(t)<6 or not t[5] for t in tokens)
            or tokens[0][3]!=0 or tokens[-1][4]!=len(text)
            or ''.join(t[0] for t in tokens)!=text
            or (len(tokens)==2 and tokens[0][4]!=tokens[1][3])):
        return False
    from morphology import dictionary_inflections
    head=tokens[0]
    entries=dictionary_inflections(head[0]) or ()
    def ordinary_noun(pos):
        return pos.startswith('名詞') and not any(x in pos for x in ('固有名詞','接尾','非自立'))
    nominal=ordinary_noun(head[1]) and any(
        ordinary_noun(pos) and reading==head[2] for pos,form,base,reading in entries)
    interjection=head[1].startswith('感動詞') and any(
        pos.startswith('感動詞,') and reading==head[2] for pos,form,base,reading in entries)
    if not nominal and not interjection:
        return False
    if len(tokens)==1:
        return True
    tail=tokens[1]
    # A noun takes nominal case/topic/attributive particles. A connective
    # following a predicate cannot be justified by a nominal homograph.
    nominal_particle=tail[1].startswith(('助詞:格助詞','助詞:係助詞','助詞:副助詞','助詞:連体化'))
    from pos_grammar import is_quotative_particle
    # A native na-adjective also has the adnominal copula な. Do not
    # treat its stem-final repetition as two unrelated particles.
    na_adnominal=(nominal and '形容動詞語幹' in head[1] and tail[0]=='な'
                  and tail[1].startswith('助動詞') and len(tail)>6
                  and any(pos.startswith('名詞,形容動詞語幹,') and reading==head[2]
                          for pos,form,base,reading in entries))
    if not ((nominal and nominal_particle) or na_adnominal
            or (interjection and is_quotative_particle(tail[0],tail[1]))):
        return False
    return any(':'.join(x for x in pos.split(',') if x!='*')==tail[1] and reading==tail[2]
               and (not na_adnominal or (base=='だ' and form==tail[6]))
               for pos,form,base,reading in dictionary_inflections(tail[0]) or ())


def nominalized_adjective_context(source, start, end, tokenize):
    """Recognize the original adjective stem + native nominalizing suffix さ.

    GPT-6 / 2026-09-11 / 48-YV. A kana window may start inside the stem;
    the full original word supplies the grammar, not the two repeated kana.
    """
    if not source or tokenize is None or not 0<=start<end<=len(source):
        return False
    tokens=list(tokenize(source) or ())
    from morphology import dictionary_inflections
    from pos_grammar import explain_kana_run
    for index,(head,suffix) in enumerate(zip(tokens,tokens[1:])):
        if (len(head)<7 or len(suffix)<7 or not head[5] or not suffix[5]
                or head[4]!=suffix[3] or suffix[0]!='さ'
                or not suffix[1].startswith('名詞:接尾:特殊')
                or not head[3]<=start<suffix[4]<=end):
            continue
        adjective=head[1].startswith('形容詞') and head[6]=='ガル接続'
        na_adjective=head[1].startswith('名詞:形容動詞語幹')
        if not adjective and not na_adjective:
            continue
        entries=dictionary_inflections(head[0]) or ()
        if not any(reading==head[2] and (
                (adjective and pos.startswith('形容詞,') and form=='ガル接続')
                or (na_adjective and pos.startswith('名詞,形容動詞語幹,')))
                for pos,form,base,reading in entries):
            continue
        if not any(pos.startswith('名詞,接尾,特殊,') and reading==suffix[2]
                   for pos,form,base,reading in dictionary_inflections(suffix[0]) or ()):
            continue
        if suffix[4]==end:
            return True
        following=[t for t in tokens[index+2:] if suffix[4]<=t[3] and t[4]<=end]
        if (not following or following[0][3]!=suffix[4] or following[-1][4]!=end
                or any(len(t)<6 or not t[5] for t in following)
                or not following[0][1].startswith(('助詞:格助詞','助詞:係助詞','助詞:副助詞','助詞:連体化'))
                or any(not t[1].startswith(('助詞','助動詞')) for t in following)
                or any(a[4]!=b[3] for a,b in zip(following,following[1:]))):
            continue
        if explain_kana_run(source[suffix[4]:end],no_words=True,initial_state='Bw'):
            return True
    return False


def native_genitive_context(source,start,end,tokenize):
    """A leading の in a kana window still belongs to its original preceding noun."""
    if not source or tokenize is None or not 0<start<end<=len(source) or source[start]!='の':
        return False
    tokens=list(tokenize(source) or ())
    for previous,particle in zip(tokens,tokens[1:]):
        if (len(previous)<6 or len(particle)<6 or not previous[5] or not particle[5]
                or previous[4]!=start or particle[3]!=start or particle[4]!=start+1
                or particle[0]!='の' or particle[1]!='助詞:連体化'
                or not previous[1].startswith('名詞')):
            continue
        return native_lexical_phrase(source[start+1:end],tokenize)
    return False


def _native_request_tail(parts):
    """Actual くださる imperative, standalone or after a native te/de link."""
    if len(parts)==1 and len(parts[0])>=7:
        last=parts[0]
        if (last[5] and last[1].startswith(('動詞:自立','動詞:非自立'))
                and last[6] in ('命令ｉ','連用形')):
            from morphology import dictionary_inflections
            return any(pos.startswith('動詞,自立,') and base in ('くださる','下さる')
                       and form=='命令ｉ' and reading==last[2]
                       for pos,form,base,reading in dictionary_inflections(last[0]) or ())
        return False
    if len(parts)<3 or any(len(t)<7 for t in parts[-2:]):
        return False
    # 48-AGW: keep a native intervening は/も in the written request.
    # Reuse the whole-predicate focus proof, then the same imperative
    # check on its evidence form. This does not normalize the source.
    from contextual_repair import _native_focused_te_forms
    text=''.join(t[0] for t in parts)
    if all(len(t)>=7 and t[5] for t in parts) and all(a[4]==b[3] for a,b in zip(parts,parts[1:])):
        for reduced in _native_focused_te_forms(text,parts[0][0]):
            from morphology import tokenize
            projected=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                        t.start,t.end,t.has_reading,t.infl_form) for t in tokenize(reduced)]
            if _native_request_tail(projected):return True
    previous,last=parts[-2:]
    if (not previous[5] or not last[5] or previous[4]!=last[3]
            or previous[0] not in ('て','で') or not previous[1].startswith('助詞:接続助詞')
            or not last[1].startswith('動詞:非自立') or last[6]!='命令ｉ'):
        return False
    from morphology import dictionary_inflections
    return any(pos.startswith('動詞,非自立,') and base=='くださる'
               and form==last[6] and reading==last[2]
               for pos,form,base,reading in dictionary_inflections(last[0]) or ())



@lru_cache(maxsize=4096)
def _native_open_predicate(surface,head,before=''):
    """Source-only native unfinished inflection; never candidate completion.

    GPT-6 / 2026-09-14. Every written piece keeps its actual reading and
    attachment. A final native inflection is checked against its own lemma
    to establish the preceding grammatical chain, without editing the input.
    """
    from morphology import tokenize,dictionary_inflections
    from contextual_repair import _productive_predicate,_allows_grammatical_tail
    parts=[t for t in tokenize(before+surface) if t.start>=len(before)]
    if (not parts or parts[0].surface!=head or not all(t.has_reading for t in parts)
            or ''.join(t.surface for t in parts)!=surface):return False
    first,last=parts[0],parts[-1]
    if (last.pos not in ('動詞','助動詞')
            or not last.infl_form.startswith(('連用','未然','仮定'))
            or not _productive_predicate(surface,head,before=before)):return False
    endings=[row for row in dictionary_inflections(last.surface) or ()
             if row[0].split(',')[0]==last.pos and row[1]==last.infl_form
             and row[3]==last.reading]
    if len(parts)==1:return bool(endings and first.pos=='動詞')
    forms=[row for row in dictionary_inflections(head) or ()
           if row[0].split(',')[0]==first.pos and row[3]==first.reading]
    for pos,form,lemma,rd in endings:
        if not any(p.split(',')[0]==last.pos and f=='基本形' and b==lemma
                   for p,f,b,r in dictionary_inflections(lemma) or ()):continue
        finite=surface[:-len(last.surface)]+lemma
        if (_allows_grammatical_tail(forms,finite[len(head):],first.reading,head)
                and _productive_predicate(finite,head,before=before)):
            return True
    return False


def native_predicate_finite_core(parts):
    """Keep actual sentence-final particles outside the finite predicate.

    The caller still verifies the entire unchanged grammatical tail. This
    identifies the finite token; it does not license removing a particle.
    """
    end=len(parts)
    while (end and parts[end-1][5] and parts[end-1][1].startswith('助詞:')
           and '終助詞' in parts[end-1][1]):
        end-=1
    return parts[:end]


def _native_nominal_functional_tail(parts,explicit_nominal_case=False,
                                    content_object_faces=None, content_subject_faces=None, allow_connective=False,
                                    content_case_argument=None, allow_open_tail=False, source_prefix=""):
    """Original particles, optionally followed by a completed basic predicate.

    48-ZD / GPT-6 / 2026-09-11. Reuse the existing functional vocabulary
    and native inflection validation. A content noun, filler or unfinished
    verb is not another spelling of a functional phrase.
    """
    if all(t[1].startswith('助詞') for t in parts):
        return True
    first=next((i for i,t in enumerate(parts) if not t[1].startswith('助詞')),len(parts))
    if first==0 or first==len(parts):
        return False
    if any(len(t)<7 for t in parts[first:]):
        return False
    head=parts[first]
    from corrector import BASIC_VERB_FORMS
    from contextual_repair import (_completed_predicate_token,
        _allows_grammatical_tail,_productive_predicate)
    from morphology import dictionary_inflections
    request=_native_request_tail(parts[first:])
    connective=(allow_connective and len(parts)>first+1 and parts[-1][0] in ('て','で')
                and parts[-1][1].startswith('助詞:接続助詞'))
    core=native_predicate_finite_core(parts)
    if len(core)<=first:return False
    ending=core[first+1:-1] if connective else core[first+1:]
    last=core[-1]
    open_tail=bool(allow_open_tail and len(core)==len(parts) and last[5] and last[1].startswith(('動詞','助動詞'))
                   and last[6].startswith(('連用','未然','仮定')))
    # Completion and attachment are separate. The shared full native tail
    # check below already handles auxiliaries, te/de aspect and phase verbs;
    # an auxiliary-only POS filter would reject the same valid grammar here.
    valid_tail=request or connective or _completed_predicate_token(last) or open_tail
    if not head[1].startswith('動詞') or not valid_tail:
        return False
    forms=tuple(x for x in dictionary_inflections(head[0]) or ()
                if x[0].startswith('動詞,') and x[1]==head[6] and x[3]==head[2])
    direct_request=bool(request and len(parts)==first+1)
    basic=head[0] in BASIC_VERB_FORMS or direct_request
    if explicit_nominal_case:
        # The established noun + actual case supplies a boundary that bare
        # fragments such as ほらい lack. Native み + ます can then complete
        # the already-known basic verb みる without adding み as a word.
        lemma_readings={rd for _,_,lemma,_ in forms
            for pos,form,base,rd in dictionary_inflections(lemma) or ()
            if pos.startswith('動詞,') and form=='基本形' and rd in BASIC_VERB_FORMS}
        basic=bool(lemma_readings) or direct_request
        if parts[0][0]=='を':
            from semantic_roles import ACCUSATIVE_BASIC_LEMMA_READINGS
            basic=bool(lemma_readings & ACCUSATIVE_BASIC_LEMMA_READINGS) or direct_request
    suffix=''.join(t[0] for t in parts[first+1:])
    before=source_prefix+''.join(t[0] for t in parts[:first])
    if explicit_nominal_case and content_object_faces and parts[0][0]=='を':
        from semantic_roles import native_verb_roles,nominal_roles
        roles=native_verb_roles(head[0],head[6],head[2],tail=suffix,before=before,allow_open_tail=allow_open_tail)
        # A direct native imperative request takes the already proved noun
        # itself (Nをください). Its role is not restricted to the small
        # content-word taxonomy used for ordinary lexical action senses.
        basic=direct_request or any(roles & nominal_roles(face) for face in content_object_faces)
        if not basic:
            # The native construction N(サ変)をする uses the action noun's
            # own meaning. A generic suru need not borrow an unrelated
            # lexical verb's object roles, and arbitrary nouns add no proof.
            from morphology import native_suru_form
            suru=tuple(row for row in forms if row[2]=='する'
                       and native_suru_form(head[0],row[1],row[3],False))
            action_noun=any(any(pos.startswith('名詞,サ変接続,') and base==face
                               for pos,form,base,rd in dictionary_inflections(face) or ())
                            for face in content_object_faces)
            basic=bool(suru and action_noun
                and _allows_grammatical_tail(suru,suffix,head[2],head[0])
                and _productive_predicate(head[0]+suffix,head[0],before=before))
    if content_subject_faces is not None:
        from semantic_roles import native_verb_roles,nominal_roles
        roles=native_verb_roles(head[0],head[6],head[2],subject=True,tail=suffix,before=before,allow_open_tail=allow_open_tail)
        basic=any(roles & nominal_roles(face) for face in content_subject_faces)
    if content_case_argument is not None:
        from semantic_roles import native_verb_roles,nominal_roles
        case,faces=content_case_argument
        roles=native_verb_roles(head[0],head[6],head[2],case=case,tail=suffix,before=before,allow_open_tail=allow_open_tail)
        basic=any(roles & nominal_roles(face) for face in faces)
    if not basic:
        return False
    # 48-ZT: positive completion needs an actual modern euphonic proof.
    # A classical/unknown homograph left unjudged by candidate validation
    # cannot certify an irregular-looking past form such as ありた.
    if parts[first+1:]:
        from contextual_repair import _modern_euphonic_link, _modern_te_allowed
        following=parts[first+1]
        link=_modern_euphonic_link(following[0],following[1],following[6])
        if link is not None and _modern_te_allowed(head[0],head[2],link) is not True:
            return False
    return bool(forms and (not suffix or (
        (_allows_grammatical_tail(forms,suffix,head[2],head[0])
         or allow_open_tail and _native_open_predicate(head[0]+suffix,head[0],before))
        and _productive_predicate(head[0]+suffix,head[0],before=before))))


@lru_cache(maxsize=4096)
def native_functional_case_cuts(text):
    """48-ABN: retain an actual case and completed basic predicate.

    This locates an existing grammatical suffix after an independently
    anomalous input; it neither proves the preceding word nor selects a
    replacement. It shares the original functional-tail validation.
    """
    from morphology import tokenize,dictionary_inflections
    out=[]
    for cut in range(3,min(25,len(text)-2)):
        if text[cut] not in 'がはをにで':continue
        parts=list(tokenize(text[cut:]))
        if (not parts or parts[0].start!=0 or parts[-1].end!=len(text)-cut
                or not all(t.has_reading for t in parts)
                or any(a.end!=b.start for a,b in zip(parts,parts[1:]))
                or parts[0].surface!=text[cut] or parts[0].pos!='助詞'
                or not parts[0].pos_sub.startswith(('格助詞:一般','係助詞'))
                or not any(t.pos=='動詞' for t in parts)):
            continue
        if not any(p.startswith(('助詞,格助詞,一般,','助詞,係助詞,')) and rd==text[cut]
                   for p,f,b,rd in dictionary_inflections(text[cut]) or ()):
            continue
        legacy=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                 t.start,t.end,t.has_reading,t.infl_form) for t in parts]
        if _native_nominal_functional_tail(legacy,explicit_nominal_case=True):
            out.append(cut)
    return tuple(out)


@lru_cache(maxsize=1)
def _seed_nominal_readings():
    """SR-A: attest whole readings from the shipped roster, without converting.

    A lexical unit and its native noun readings must both agree. User vocabulary
    and the mere existence of a kanji candidate are not normality evidence.
    """
    from seed_vocabulary import SEED_VOCABULARY
    from seed_japanese import is_unit
    from morphology import tokenize
    found={}
    for reading,face,category in SEED_VOCABULARY:
        if not is_unit(face):continue
        parts=tokenize(face)
        if (parts and all(t.has_reading and t.pos=='名詞'
                         and not any(x in t.pos_sub for x in ('固有名詞','接尾','非自立'))
                         for t in parts)
                and ''.join(t.reading for t in parts)==reading):
            found.setdefault(reading,set()).add(face)
    return {rd:tuple(sorted(faces)) for rd,faces in found.items()}


# Native decimal digits shared by clock and ordinary counter paradigms.
KANJI_DIGITS='零一二三四五六七八九'


def _native_small_number_words(number):
    """Decimal place value shared by counters and the existing clock proof."""
    if not 0 <= number < 100:
        return ()
    if number < 10:
        return (KANJI_DIGITS[number],)
    tens, units = divmod(number, 10)
    return (() if tens == 1 else (KANJI_DIGITS[tens],)) + ('十',) + (
        (KANJI_DIGITS[units],) if units else ())


# 48-AHA / 2026-09-16 / GPT-6 Astra: productive counter readings, not
# typo/output pairs. Native digits and exact counter POS establish identity;
# the conventional sound changes are independently reviewed against the
# Japan Foundation's 教科書を作ろう reference chart (PDF p.284) and まるごと
# starter wordbook (PDF p.81). Only the attested counting use is added.
# https://www.jpf.go.jp/j/urawa/j_rsorcs/textbook/dl/setsumei/setsumei_all.pdf
# https://marugoto.jpf.go.jp/assets/docs/download/starter_a/MarugotoStarterWordbook_CN.pdf
COUNTER_READING_VERSION = '2026-09-16ahd'


def _native_regular_counter_readings():
    from morphology import dictionary_inflections
    from itertools import product
    def exact(word, kind):
        return tuple(rd for pos, form, base, rd in dictionary_inflections(word) or ()
                     if base == word and pos.startswith(kind))
    digits = {number: exact(KANJI_DIGITS[number], '名詞,数,') for number in range(1, 10)}
    tens = exact('十', '名詞,数,')
    if not tens or not all(digits.values()):
        return {}
    counters = {face: reading for face, reading in (
        ('個', 'こ'), ('枚', 'まい'), ('冊', 'さつ'), ('本', 'ほん'), ('台', 'だい'), ('人', 'にん'))
        if reading in exact(face, '名詞,接尾,助数詞,')}
    result = {}
    for number in range(1, 100):
        words = _native_small_number_words(number)
        ending = number % 10
        last = digits[ending] if ending else tens
        prefixes = {''.join(row) for row in product(*(
            exact(word, '名詞,数,') for word in words[:-1]))}
        for counter, reading in counters.items():
            stems = last
            suffix = reading
            if counter in ('個', '本') and ending in (1, 6, 8, 0):
                stems = {1: ('いっ',), 6: ('ろっ',), 8: ('はっ',), 0: ('じゅっ', 'じっ')}[ending]
            elif counter == '冊' and ending in (1, 8, 0):
                stems = {1: ('いっ',), 8: ('はっ',), 0: ('じゅっ', 'じっ')}[ending]
            if counter == '本':
                suffix = 'ぼん' if ending == 3 else ('ぽん' if ending in (1, 6, 8, 0) else 'ほん')
            elif counter == '人':
                if number in (1, 2):
                    # The irregular one/two-person words apply only to those
                    # complete numbers; e.g. 21 uses いちにん, not ひとり.
                    complete = 'ひとり' if number == 1 else 'ふたり'
                    result.setdefault(complete, set()).add(''.join(words) + counter)
                    continue
                if ending == 4:
                    stems = ('よ',)
                elif ending == 7:
                    stems = ('なな', 'しち')
            for prefix in prefixes:
                for stem in stems:
                    result.setdefault(prefix + stem + suffix, set()).add(''.join(words) + counter)
    return result


@lru_cache(maxsize=1)
def native_counter_readings():
    """The attested native counting paradigm, not typo answers.

    2026-09-14 / GPT-6 Astra: actual dictionary noun/readings supply the
    complete forms, including native gemination. No arbitrary syllable
    concatenation or unrecorded reading is inferred.
    """
    from morphology import dictionary_inflections
    result={}
    for digit in KANJI_DIGITS[1:]:
        word=digit+'つ'
        for pos,form,base,reading in dictionary_inflections(word) or ():
            if pos.startswith('名詞,一般,') and base==word:
                result.setdefault(reading,set()).add(word)
    # Reading supplement v2026-09-14 / GPT-6 Astra, verified against
    # 文化庁「常用漢字表の音訓索引」十: とお. IPAdic's 十 entry
    # supplies nominal identity but does not list this counting reading.
    # https://www.bunka.go.jp/kokugo_nihongo/sisaku/joho/joho/kijun/naikaku/kanji/joyokanjisakuin/
    if any(pos.startswith('名詞,数,') and base=='十'
           for pos,form,base,reading in dictionary_inflections('十') or ()):
        result.setdefault('とお',set()).add('十')
    for reading, faces in _native_regular_counter_readings().items():
        result.setdefault(reading, set()).update(faces)
    # 48-AHD / GPT-6 Astra: native numeric 半 and suffix 半 attest
    # fractional quantities. Daijisen 半, senses 1 and 5:
    # https://kotobank.jp/word/%E5%8D%8A-605946
    half_forms=dictionary_inflections('半') or ()
    if any(pos.startswith('名詞,接尾,') and rd=='はん'
            for pos,form,base,rd in half_forms):
        for reading,faces in tuple(result.items()):
            result[reading+'はん']={face+'半' for face in faces}
    if any(pos.startswith('名詞,数,') and rd=='はん'
            for pos,form,base,rd in half_forms):
        # These counters retain their native consonants after half.
        # No unverified 本 allomorph or human fractional count is inferred.
        for counter in ('個','枚','冊','台'):
            for pos,form,base,reading in dictionary_inflections(counter) or ():
                if base==counter and pos.startswith('名詞,接尾,助数詞,'):
                    result.setdefault('はん'+reading,set()).add('半'+counter)
    return {reading:tuple(sorted(faces)) for reading,faces in result.items()}


@lru_cache(maxsize=1)
def native_ordinal_readings():
    """48-AHP: native integer/counter + ordinal 目; not a floating quantity.

    Kyoto University Samidori, lesson 7 counters; native suffix め.
    Fractions and bare 十/とお do not form this ordinal paradigm.
    """
    from morphology import dictionary_inflections
    if not any(pos.startswith('名詞,接尾,一般,') and base=='目' and rd=='め'
               for pos,form,base,rd in dictionary_inflections('目') or ()):
        return {}
    out={}
    for reading,faces in native_counter_readings().items():
        whole=tuple(face+'目' for face in faces if '半' not in face
                    and face.endswith(('個','枚','冊','本','台','人','つ')))
        if whole:out[reading+'め']=whole
    return out


@lru_cache(maxsize=1)
def _counted_nominal_index():
    index={}
    for ordinal,table in ((False,native_counter_readings()),(True,native_ordinal_readings())):
        for reading,faces in table.items():
            for face in faces:
                bare=face[:-1] if ordinal else face
                if bare.endswith('半'):bare=bare[:-1]
                unit=bare[-1:]
                if unit not in ('個','枚','冊','本','台','人','つ'):continue
                for text in (reading,face):index.setdefault(text,set()).add((unit,ordinal))
    return {text:tuple(sorted(evidence)) for text,evidence in index.items()}


def native_counted_nominal_evidence(surface):
    """Exact proven reading/spelling only; unit meaning lives in semantic_roles."""
    return _counted_nominal_index().get(surface,())


@lru_cache(maxsize=8192)
def native_katakana_nominal_face(reading):
    """An unchanged loanword reading needs an actual native noun.

    The shipped loanword roster locates the face; native lexical identity
    and its exact reading prove the word. A cost-table spelling alone does not.
    """
    if not reading or not all('ぁ'<=c<='ゖ' or c=='ー' for c in reading):return None
    from seed_katakana import KATAKANA_WORDS
    face=''.join(chr(ord(c)+0x60) if 'ぁ'<=c<='ゖ' else c for c in reading)
    if face not in KATAKANA_WORDS:return None
    from morphology import dictionary_inflections
    if any(pos.startswith(('名詞,一般,','名詞,サ変接続,')) and base==face and rd==reading
           for pos,form,base,rd in dictionary_inflections(face) or ()):return face
    return None


@lru_cache(maxsize=1)
def _classified_compound_nominal_readings():
    """48-AII: exact readings of already classified whole nominal units.

    The existing semantic roster proves the whole word, not arbitrary noun
    concatenation. Each contiguous part needs its actual native common-noun
    reading. A best-parse proper-name tag cannot hide that same common entry.
    No word or typo/answer roster is introduced here.
    """
    from semantic_roles import NOUN_ROLES
    from morphology import tokenize,dictionary_inflections
    found={}
    for face in sorted(NOUN_ROLES):
        parts=tokenize(face)
        if (len(parts)<2 or ''.join(t.surface for t in parts)!=face
                or any(a.end!=b.start for a,b in zip(parts,parts[1:]))):continue
        if not all(any(pos.startswith('名詞,') and base==part.surface and rd==part.reading
                and not any(kind in pos for kind in ('固有名詞','接尾','非自立'))
                for pos,form,base,rd in dictionary_inflections(part.surface) or ()) for part in parts):continue
        reading=''.join(part.reading for part in parts)
        if reading and all('ぁ'<=c<='ゖ' or c=='ー' for c in reading):
            found.setdefault(reading,set()).add(face)
    return {rd:tuple(sorted(faces)) for rd,faces in found.items()}


@lru_cache(maxsize=8192)
def native_lexical_reading_faces(reading):
    """48-AJA: exact native whole-word entries, not mere cost-table keys.

    The cost table locates candidate spellings. Only their own dictionary
    reading and independent lexical category attest the word. Inflected
    verbs remain lexical words; particles and dependent suffixes do not.
    Lack of this evidence never declares an original spelling anomalous.
    """
    if not reading or not all('ぁ'<=c<='ゖ' or c=='ー' for c in reading):return ()
    from morphology import dictionary_inflections
    from corrector import table_surfaces_for_reading
    katakana=''.join(chr(ord(c)+0x60) if 'ぁ'<=c<='ゖ' else c for c in reading)
    faces={reading,katakana,*table_surfaces_for_reading(reading,limit=12)}
    return tuple(sorted(face for face in faces if any(
        rd==reading and pos.startswith(('名詞,','動詞,','形容詞,','副詞,','連体詞,','感動詞,','接続詞,'))
        and not any(part in pos.split(',') for part in ('接尾','非自立'))
        for pos,form,base,rd in dictionary_inflections(face) or ())))


def native_common_noun_reading(surface, reading):
    """Native noun identity, shared by reading proofs and explicit choices."""
    from morphology import dictionary_inflections
    return (any(pos.startswith('名詞,') and rd == reading
               and not any(x in pos for x in ('固有名詞', '接尾', '非自立'))
               for pos, form, base, rd in dictionary_inflections(surface) or ())
            or surface in _classified_compound_nominal_readings().get(reading,()))


@lru_cache(maxsize=16384)
def _native_nominal_reading_faces(reading):
    """Native common-noun spellings with this exact complete reading.

    A one-kana noun uses the same native reading and usage evidence. Length
    alone does not invalidate a known noun; callers prove its actual case.
    """
    if not reading or not all('ぁ'<=c<='ゖ' or c=='ー' for c in reading):
        return ()
    from corrector import table_surfaces_for_reading
    from morphology import dictionary_inflections
    from kango_tier import usage_tier_for_reading, _explicit_reading_faces
    # 48-ABD: AI usage judgments have native dictionary readings even
    # when the old cost-filtered table omits the spelling (店 / みせ).
    # Use that same roster as evidence, not a second list of answer words.
    attested=_seed_nominal_readings().get(reading,())
    attested=tuple(attested)+_classified_compound_nominal_readings().get(reading,())
    attested=tuple(attested)+native_counter_readings().get(reading,())+native_ordinal_readings().get(reading,())
    loan=native_katakana_nominal_face(reading)
    if loan:attested=tuple(attested)+(loan,)
    # A literal kana dictionary noun is already an attested lexical unit.
    # Do not demand a kanji cost-table spelling for words such as fruit
    # names. Unknown, proper, dependent and suffix entries add no proof.
    if any(pos.startswith(('名詞,一般,','名詞,サ変接続,')) and base==reading and rd==reading
           for pos,form,base,rd in dictionary_inflections(reading) or ()):
        attested=tuple(attested)+(reading,)

    faces=set(table_surfaces_for_reading(reading,limit=12))
    faces.update(_explicit_reading_faces().get(reading,()))
    return tuple(sorted(set(attested).union(face for face in sorted(faces)
        if usage_tier_for_reading(face,reading) in (1,2)
        and native_common_noun_reading(face, reading))))


# 48-ACG: relational nouns keep their own meaning as the head of a
# compound. The modifier must be an attested native sahen action. This
# cannot arbitrarily combine all dictionary words into a completed reading.
ACTION_RESULT_NOUNS=frozenset('結果 記録 履歴 手順 方法 状態 条件 予定 計画'.split())


@lru_cache(maxsize=4096)
def native_polite_nominal_parts(text):
    """Native お/ご nominal prefix and an unchanged ordinary noun reading.

    GPT-6 Astra / 2026-09-14: grammatical prefix evidence only. Whole lexical
    words such as おなら/ごはん keep their own parse; no prefix is invented.
    """
    from morphology import tokenize,dictionary_inflections
    parts=tokenize(text)
    if not parts:
        return ()
    first=parts[0]
    if (first.start!=0 or first.surface not in ('お','ご') or not first.has_reading
            or first.pos!='接頭詞' or first.pos_sub!='名詞接続' or first.end>=len(text)):
        return ()
    prefixes=[(first.surface,pos,form,base,rd) for pos,form,base,rd in dictionary_inflections(first.surface) or ()
              if pos.startswith('接頭詞,名詞接続,') and rd==first.reading]
    if not prefixes:
        return ()
    reading=text[first.end:];proofs=[]
    for face in _native_nominal_reading_faces(reading):
        for pos,form,base,rd in dictionary_inflections(face) or ():
            if pos.startswith('名詞,') and rd==reading and not any(kind in pos for kind in ('固有名詞','接尾','非自立')):
                proofs.append((prefixes[0],(face,pos,form,base,rd)))
    return tuple(proofs)


@lru_cache(maxsize=4096)
def native_deictic_range(text):
    """An actual demonstrative location plus the native extent particle まで.

    This supplies the nominal range itself; no absent noun or spelling is
    inserted. Its possible argument roles remain in the shared meaning table.
    """
    if not text.endswith('まで') or len(text)<=2:return False
    from morphology import tokenize
    parts=tokenize(text)
    return bool(len(parts)==2 and all(t.has_reading for t in parts)
        and parts[0].pos=='名詞' and parts[0].pos_sub.startswith('代名詞')
        and parts[0].surface==parts[0].reading and parts[0].surface in ('ここ','そこ','あそこ','どこ')
        and parts[1].surface=='まで' and parts[1].pos=='助詞' and parts[1].pos_sub=='副助詞')


@lru_cache(maxsize=4096)
def native_plural_nominal_heads(text):
    """Native personal noun/pronoun + the attested plural suffix たち.

    GPT-6 Astra / 2026-09-14. A nominal head supplies personhood; the suffix
    supplies plurality. Neither an arbitrary word ending nor frequency does.
    """
    if not text.endswith('たち') or len(text)<=2:return ()
    from morphology import tokenize,dictionary_inflections
    from semantic_roles import nominal_roles
    if not any(pos.startswith('名詞,接尾,一般,') and base=='たち' and rd=='たち'
               for pos,form,base,rd in dictionary_inflections('たち') or ()):return ()
    head=text[:-2]
    faces=_native_nominal_reading_faces(head) if all('ぁ'<=c<='ゖ' for c in head) else (head,)
    if any(pos.startswith('名詞,代名詞,') and base==head and rd==head
           for pos,form,base,rd in dictionary_inflections(head) or ()):
        faces=tuple(faces)+(head,)
    found=[]
    for face in faces:
        tokens=tokenize(face+'たち')
        if (len(tokens)!=2 or tokens[0].surface!=face or tokens[0].pos!='名詞'
                or tokens[1].surface!='たち' or tokens[1].pos!='名詞'
                or tokens[1].pos_sub!='接尾:一般' or not all(t.has_reading for t in tokens)):continue
        if 'person' in nominal_roles(face) or tokens[0].pos_sub.startswith('代名詞'):
            found.append(face)
    return tuple(sorted(set(found)))


@lru_cache(maxsize=4096)
def native_relational_compound_heads(reading):
    """Attested written noun compounds retain an independently fitting head.

    A frequency-table spelling only locates a possible compound. Both
    native nouns, their full readings and the existing genitive relation
    must agree. This does not split every kana string into arbitrary nouns.
    """
    from corrector import table_surfaces_for_reading
    from morphology import tokenize
    from semantic_roles import genitive_nominal_support,classified_nominal_action,support
    heads=set()
    # 48-AGV / GPT-6 Astra: productive object/action nouns do not require
    # the cost table to contain their concatenation. Each unchanged half
    # needs an ordinary native noun reading, and the original object must
    # fit the independently classified action. Do not recursively combine
    # unknown pieces or infer the action merely from its sahen POS.
    for cut in range(2,len(reading)-1):
        actions=tuple(face for face in _native_nominal_reading_faces(reading[cut:])
                      if classified_nominal_action(face,reading[cut:]))
        if not actions:continue
        objects=_native_nominal_reading_faces(reading[:cut])
        for action in actions:
            if any(support(obj,action) for obj in objects):heads.add(action)
    for face in table_surfaces_for_reading(reading,limit=12):
        if not any('一'<=c<='鿿' for c in face):continue
        # The ordinary-word tier itself requires a single dictionary token,
        # so it cannot establish a two-token compound. The native readings
        # and semantic composition below provide the independent word proof.
        parts=tokenize(face)
        if (len(parts)!=2 or ''.join(t.surface for t in parts)!=face
                or any(not t.has_reading or t.pos!='名詞'
                       or any(kind in t.pos_sub for kind in ('固有名詞','非自立')) for t in parts)):continue
        # A parser's first reading is not the noun's only native reading.
        # Keep the actual word and POS, and consider every dictionary reading
        # of that same entry (suffix 物 has both ぶつ and もの).
        from morphology import dictionary_inflections
        options=[{rd for pos,form,base,rd in dictionary_inflections(t.surface) or ()
                  if pos.startswith(t.pos+','+t.pos_sub.replace(':',',')+',')}
                 for t in parts]
        if not any(a+b==reading for a in options[0] for b in options[1]):continue
        first,head=parts
        # A native action noun + the attested material suffix 物 names
        # its object only when that action already has the object role.
        # No arbitrary suffix, new reading or unclassified action is inferred.
        if (first.pos_sub=='サ変接続' and head.surface=='物' and reading.endswith('もの')
                and 'もの' in options[1]
                and head.pos_sub.startswith('接尾')):
            from semantic_roles import predicate_roles
            if 'object' in predicate_roles(first.surface):heads.add(head.surface)
            continue
        if any('接尾' in t.pos_sub for t in parts):continue
        from semantic_roles import classified_nominal_action,support
        if (genitive_nominal_support(first.surface,head.surface)
                or classified_nominal_action(head.surface,head.reading)
                and support(first.surface,head.surface)):heads.add(head.surface)
    return tuple(sorted(heads))


@lru_cache(maxsize=4096)
def native_nominal_phrase_faces(text):
    """Return native nominal heads; never produce a replacement spelling."""
    if not text or not 1<=len(text)<=24 or not all('ぁ'<=c<='ゖ' or c=='ー' for c in text):
        return ()
    direct=_native_nominal_reading_faces(text)
    if direct:return direct
    # 48-AJH: the native adjective + nominalizing さ already used by
    # written-object semantics also proves the unchanged kana noun.
    # Return the literal reading; this selects no alternate kanji spelling.
    if text.endswith('さ'):
        from morphology import tokenize
        def original_parts(value):
            return [(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                     t.start,t.end,t.has_reading,t.infl_form) for t in tokenize(value)]
        if nominalized_adjective_context(text,0,len(text),original_parts):return (text,)
    compound=native_relational_compound_heads(text)
    if compound:return compound
    # A native nominal focus particle preserves its noun's argument roles.
    # しか is deliberately separate: it requires a negative predicate.
    from morphology import tokenize,dictionary_inflections
    for focus in ('だけ','ばかり','など'):
        if not text.endswith(focus) or len(text)<=len(focus):continue
        if not any(pos.startswith('助詞,副助詞,') and rd==focus
                   for pos,form,base,rd in dictionary_inflections(focus) or ()):continue
        focused=native_nominal_phrase_faces(text[:-len(focus)])
        # Kana parsing can split だけ into copula だ + final け after an
        # attested modifier. The independently proved nominal head and
        # native focused spelling establish the same unchanged boundary.
        for face in focused:
            parts=tokenize(face+focus)
            if (parts and parts[-1].start==len(face) and parts[-1].has_reading
                    and parts[-1].surface==focus and parts[-1].pos=='助詞'
                    and parts[-1].pos_sub=='副助詞'):return focused
    if native_deictic_range(text):return (text,)
    plural=native_plural_nominal_heads(text)
    if plural:return tuple(face+'たち' for face in plural)
    # A proved attributive phrase retains its actual nominal head when
    # nested inside another noun phrase. Reuse its native inflection and
    # subject/object relation rather than re-parsing the kana fragments.
    modified=native_adnominal_reading_parts(text,allow_predicative=True)
    if modified:
        heads=(modified[-1][0],)
        # An unchanged adjective/demonstrative does not select the first
        # dictionary spelling of its noun. Preserve all exact native noun
        # readings; a relative verb still keeps its argument-constrained head.
        if modified[0][1].startswith(('連体詞,','形容詞,','名詞,形容動詞語幹,')):
            heads+=_native_nominal_reading_faces(modified[-1][4])
            for proof in native_polite_nominal_parts(modified[-1][4]):
                heads+=(proof[-1][0],)
                heads+=_native_nominal_reading_faces(proof[-1][4])
        return tuple(dict.fromkeys(heads))
    # Pronouns are a native grammatical nominal category; their exact
    # spelling does not require a content-word usage/frequency judgment.
    from morphology import dictionary_inflections
    if any(pos.startswith('名詞,代名詞,') and base==text and reading==text
           for pos,form,base,reading in dictionary_inflections(text) or ()):
        return (text,)
    # Counter + adnominal の + known noun retains the original readings.
    # The counter paradigm supplies the boundary even when native kana
    # segmentation mistakes the following noun for particles.
    for cut, char in enumerate(text):
        if char == 'の' and (text[:cut] in native_counter_readings() or text[:cut] in native_ordinal_readings()):
            right=native_nominal_phrase_faces(text[cut+1:])
            if right:return right
    polite=native_polite_nominal_parts(text)
    if polite:return tuple(sorted({proof[-1][0] for proof in polite}))
    from morphology import tokenize
    original=tokenize(text)
    # The original の must occupy its own native particle token. A case
    # homograph additionally needs positive reconstruction of the nouns.
    # An unknown chunk or a suffix inside a known word proves no boundary.
    for cut,char in enumerate(text):
        if char!='の' or not 1<=cut<len(text)-1:continue
        left=native_nominal_phrase_faces(text[:cut])
        right=native_nominal_phrase_faces(text[cut+1:])
        if not left or not right:continue
        particle=next((t for t in original if t.start==cut and t.end==cut+1
                       and t.surface=='の' and t.pos=='助詞' and t.has_reading
                       and t.pos_sub=='連体化'),None)
        # Both unchanged noun readings and a native adnominal connection
        # establish the boundary, even when 窓の became ま + どの in kana.
        # An existing whole lexical word was already handled above.
        if particle or any(any(q.start==len(a) and q.end==len(a)+1
                and q.surface=='の' and q.pos=='助詞' and q.pos_sub=='連体化'
                and q.has_reading for q in tokenize(a+'の'+b))
                for a in left for b in right):return right
    for cut in range(2,len(text)-1):
        right=_native_nominal_reading_faces(text[cut:])
        heads=tuple(face for face in right if face in ACTION_RESULT_NOUNS)
        if heads and native_bare_action_faces(text[:cut]):
            return heads
    return ()


def native_nominal_reading_context(source,start,end,tokenize,require_predicate=False):
    """48-AAB: an original common-noun reading and its actual nominal case.

    No candidate reading or edited spelling is used. A single actual case
    closes a noun phrase; a longer scope additionally needs the same native
    finite basic predicate proof. Unknown cases and cut lexical words do
    not supply a boundary. This evidence is shared by entry and purple.
    """
    if (tokenize is None or not 0<=start<end<=len(source)
            or not all('ぁ'<=c<='ゖ' or c=='ー' for c in source[start:end])):
        return False
    original=list(tokenize(source) or ())
    if any(t[5] and t[3]<start<t[4] for t in original):
        return False
    previous=next((t for t in reversed(original) if t[4]==start),None)
    if (previous and previous[1].startswith(('名詞','接頭詞'))
            and not previous[1].startswith('名詞:副詞可能')):
        return False
    from morphology import dictionary_inflections
    from pos_grammar import _CASE_PARTICLES, explain_kana_run
    # 48-AAJ: original の + a native following noun establishes an
    # adnominal boundary. A noun reading alone, a nominalizer の, or
    # an unknown following fragment does not. Share this proof with the
    # intact entry and purple; do not add a repair-path exception.
    if not require_predicate:
        for index,(particle,following) in enumerate(zip(original,original[1:])):
            if not (particle[0]=='の' and particle[1]=='助詞:連体化'
                    and particle[5] and start+2<=particle[3]
                    and following[3]==particle[4]):
                continue
            # The kana window can include an actual determiner before the
            # following written noun. Reuse its native role, never a
            # guessed split of a longer word.
            noun=following
            if (particle[4]<end and following[1]=='連体詞' and following[5]
                    and following[4]==end and index+2<len(original)
                    and any(pos.startswith('連体詞,') and rd==following[2]
                            for pos,form,lemma,rd in dictionary_inflections(following[0]) or ())):
                noun=original[index+2]
            elif particle[4]!=end:
                continue
            reading=source[start:particle[3]]
            if (noun[3]==end and noun[5] and noun[1].startswith('名詞')
                    and not any(kind in noun[1] for kind in ('非自立','接尾'))
                    and any(pos.startswith('名詞,') and rd==noun[2]
                            for pos,form,lemma,rd in dictionary_inflections(noun[0]) or ())
                    and (native_nominal_phrase_faces(reading)
                         or native_adnominal_reading_parts(reading,allow_predicative=True))):
                return True
    for case in original:
        if (not start+2<=case[3]<case[4]<=end or not case[5]
                or not case[1].startswith(('助詞:格助詞:一般','助詞:格助詞:連語','助詞:係助詞'))
                or not any(pos.startswith(('助詞,格助詞,一般,','助詞,格助詞,連語,','助詞,係助詞,'))
                           and rd==case[2]
                           for pos,form,base,rd in dictionary_inflections(case[0]) or ())):
            continue
        # A native entry for a dialectal one-character particle is not
        # positive evidence of a new boundary in an ordinary kana phrase.
        if len(case[0])==1 and case[0] not in _CASE_PARTICLES:
            continue
        reading=source[start:case[3]]
        if not (native_nominal_phrase_faces(reading)
                or native_adnominal_reading_parts(reading,allow_predicative=True)):
            continue
        if case[4]==end:
            if require_predicate:
                continue
            following=next((t for t in original if t[3]==end),None)
            if following and following[1].startswith('助詞'):
                if not explain_kana_run(case[0]+following[0],no_words=True,initial_state='Bw'):
                    continue
            return True
        if case[0] not in ('が','は','を'):
            continue
        tail=[t for t in original if case[3]<=t[3] and t[4]<=end]
        if (len(tail)>1 and tail[0]==case and tail[-1][4]==end
                and tail[1][1].startswith('動詞')
                and all(t[5] for t in tail)
                and all(a[4]==b[3] for a,b in zip(tail,tail[1:]))
                and _native_nominal_functional_tail(tail,explicit_nominal_case=True)):
            return True
    return False


def native_nominal_context(source, start, end, tokenize):
    """A native original noun followed only by existing functional grammar.

    GPT-6 / 2026-09-11 / 48-YY. The kana window may start inside an
    established mixed-script word, or at its preceding genitive の.
    The native spelling and reading prove the noun; the existing grammar
    proves the tail. A noun at the end of a larger compound is insufficient.
    """
    if not source or tokenize is None or not 0<=start<end<=len(source):
        return False
    if native_nominal_reading_context(source,start,end,tokenize):
        return True
    tokens=list(tokenize(source) or ())
    from morphology import dictionary_inflections
    from pos_grammar import explain_kana_run
    def ordinary(pos):
        return pos.startswith('名詞') and not any(x in pos for x in ('固有名詞','接尾','非自立'))
    word_start=start
    if source[start]=='の':
        for previous,particle in zip(tokens,tokens[1:]):
            if (len(previous)>=6 and len(particle)>=6 and previous[5] and particle[5]
                    and previous[1].startswith('名詞') and previous[4]==start
                    and particle[0]=='の' and particle[1]=='助詞:連体化'
                    and particle[3]==start and particle[4]==start+1):
                word_start=start+1
                break
    for index,head in enumerate(tokens):
        if (len(head)<6 or not head[5] or not ordinary(head[1])
                or not head[3]<=word_start<head[4]<=end
                or source[head[3]:head[4]]!=head[0]):
            continue
        if index and tokens[index-1][4]==head[3] and tokens[index-1][1].startswith(('名詞','接頭詞')):
            continue
        # 48-ZG: a terminal particle does not prove the next noun boundary
        # when it was itself attached to another case/topic particle.
        # This withholds positive word evidence; the existing anomaly rules
        # still decide whether and how to repair the original string.
        left=index-1
        while (left>=0 and tokens[left][1].startswith('助詞:終助詞')
               and tokens[left][4]==tokens[left+1][3]):
            left-=1
        if left<index-1 and (left<0 or (
                tokens[left][4]==tokens[left+1][3]
                and tokens[left][1].startswith(('助詞','連体詞')))):
            continue
        if not any(ordinary(pos) and reading==head[2]
                   for pos,form,lemma,reading in dictionary_inflections(head[0]) or ()):
            continue
        if head[4]==end:
            return True
        tail=[t for t in tokens[index+1:] if head[4]<=t[3] and t[4]<=end]
        if (not tail or tail[0][3]!=head[4] or tail[-1][4]!=end
                or any(len(t)<6 or not t[5] for t in tail)
                or not _native_nominal_functional_tail(tail)
                or not tail[0][1].startswith(('助詞:格助詞','助詞:係助詞','助詞:副助詞','助詞:連体化'))
                or any(a[4]!=b[3] for a,b in zip(tail,tail[1:]))):
            continue
        # 48-ZB: 「機能語の字で読める」は原文の品詞・接続を証明しない。
        # 名詞＋助詞の範囲に限り、既存の格接続の異様を同じ原文で確認。
        # 述語や別の内容語を機能語の別解へ逃がさない。
        from oddness import is_odd_run
        if any(a<end and head[3]<b for _,_,a,b in
               is_odd_run(source,lambda _:tokens,with_spans=True,skip_join=True)):
            continue
        if explain_kana_run(source[head[4]:end],no_words=True,initial_state='Bw'):
            return True
    return False


def native_word_fragment_context(source,start,end,tokenize):
    """A window ending inside an original word is not a complete reading.

    48-ZH / GPT-6 / 2026-09-11. Share the existing native+seed proof with
    both the correction entry and kana anomaly detection. A preceding
    original nominal case phrase or genitive may belong to the same window.
    """
    if not source or tokenize is None or not 0<=start<end<=len(source):
        return False
    from corrector import _span_inside_one_token
    tokens=list(tokenize(source) or ())
    if _span_inside_one_token(tokens,start,end):
        return True
    for head in tokens:
        if (not start<head[3]<end<head[4]
                or not _span_inside_one_token(tokens,head[3],end)):
            continue
        prefix=[t for t in tokens if start<=t[3] and t[4]<=head[3]]
        if (not prefix or prefix[0][3]!=start or prefix[-1][4]!=head[3]
                or any(a[4]!=b[3] for a,b in zip(prefix,prefix[1:]))):
            continue
        # Use the original prefix parse, not a new segmentation of its text.
        shifted=[t[:3]+(t[3]-start,t[4]-start)+t[5:] for t in prefix]
        if (prefix[-1][1].startswith('助詞')
                and native_lexical_phrase(source[start:head[3]],lambda _:shifted)):
            return True
        if (source[start:head[3]]=='の'
                and native_genitive_context(source,start,head[4],tokenize)):
            return True
    return False


@lru_cache(maxsize=4096)
def completed_sahen_reading(text, allow_nonpolite=False, object_faces=None,
                            return_action=False, action_note_following=None,
                            subject_faces=None, case_argument=None, allow_open_tail=False, relative_faces=None):
    """48-ZJ/ZN: a native action reading with an unchanged finite polite tail.

    GPT-6 / 2026-09-11. This proves an inflection without choosing among
    homophonic kanji. The reading table only locates native dictionary
    entries; their exact reading and grammatical form supply the proof.
    It does not treat arbitrary noun pairs as completed predicates.
    """
    if not text or not all('ぁ'<=c<='ゖ' or c=='ー' for c in text):
        return False
    from corrector import table_surfaces_for_reading
    from morphology import dictionary_inflections, tokenize
    from contextual_repair import _allows_grammatical_tail, _productive_predicate
    from contextual_repair import _completed_predicate_token, _sahen_verb_form
    for cut in range(2,len(text)):
        reading,tail=text[:cut],text[cut:]
        # A native topic/focus or result-case particle can intervene between
        # a nominal action and suru: 入力は/もする, 入力と/にする.
        # Prove that construction, then reuse the same verb-tail evidence.
        # The particle is preserved in the source, never deleted as a typo.
        predicate_tail=tail;intervening_particle=""
        for size in range(1,min(3,len(tail))):
            particle=tail[:size]
            if any(pos.startswith('助詞,係助詞,') or (particle in ('と','に')
                    and pos.startswith('助詞,格助詞,一般,'))
                    for pos,form,base,rd in dictionary_inflections(particle) or () if rd==particle):
                predicate_tail=tail[size:];intervening_particle=particle
                break
        # The suffix starts with a native suru or its potential form.
        if not any(_sahen_verb_form(p,b,predicate_tail[:n],f,r) and r==predicate_tail[:n]
                   for n in range(1,min(3,len(predicate_tail))+1)
                   for p,f,b,r in dictionary_inflections(predicate_tail[:n]) or ()):
            continue
        for face in _native_nominal_reading_faces(reading):
            if relative_faces is not None:
                from semantic_roles import relative_action_support
                if not any(relative_action_support(noun,face) for noun in relative_faces):
                    continue
            if action_note_following is not None:
                from semantic_roles import action_note_support
                if not any(action_note_support(face,next_action) for next_action in action_note_following):
                    continue
            if case_argument is not None:
                from semantic_roles import case_action_support
                particle,arguments=case_argument
                if not any(case_action_support(noun,particle,face) for noun in arguments):
                    continue
            if subject_faces is not None:
                from semantic_roles import subject_candidate_evidence
                subject_fit=[subject_candidate_evidence(subj,face,tail) for subj in subject_faces]
                if not any(evidence and evidence['shared_roles'] for evidence in subject_fit):
                    continue
            if object_faces is not None:
                from semantic_roles import support
                if not any(support(obj,face) for obj in object_faces):
                    continue
            forms=[row for row in dictionary_inflections(face) or ()
                   if row[0].startswith('名詞,サ変接続,') and row[3]==reading]
            if not forms:
                from semantic_roles import classified_nominal_action
                if classified_nominal_action(face,reading):
                    # Contextual action use of an attested ordinary noun;
                    # dictionary_inflections itself stays native-only.
                    forms=[('名詞,サ変接続,*,*','*',face,reading)]
            if not forms:
                continue
            # 48-AIX: a dictionary homograph of や/か as a kakari
            # particle cannot erase an actual coordination/question seam.
            # Verify the same particle after the reconstructed action noun,
            # before projecting it away for the common suru-tail proof.
            if intervening_particle:
                connected=tokenize(face+tail)
                actual=next((t for t in connected if t.start==len(face)
                             and t.end==len(face)+len(intervening_particle)),None)
                if not (actual and actual.has_reading and actual.pos=='助詞'
                        and actual.surface==intervening_particle
                        and (actual.pos_sub=='係助詞'
                             or actual.surface in ('と','に')
                             and actual.pos_sub.startswith('格助詞:一般'))):continue
            # Source-only: retain a native renyou suru followed by another
            # independent finite verb. A whole parse can swallow し寝ます as
            # 死ねます or label 見ます non-independent; the alternative uses
            # unchanged readings and native inflections on both boundaries.
            if allow_open_tail:
                for n in range(1,min(3,len(predicate_tail))):
                    if not any(pos.startswith('動詞,') and base=='する' and form=='連用形'
                               and rd==predicate_tail[:n]
                               for pos,form,base,rd in dictionary_inflections(predicate_tail[:n]) or ()):
                        continue
                    remainder=predicate_tail[n:];following=list(tokenize(remainder))
                    if not following or not all(part.has_reading for part in following):
                        continue
                    first,last=following[0],following[-1]
                    native=(last.surface,last.pos+(':'+last.pos_sub if last.pos_sub else ''),
                            last.reading,last.start,last.end,last.has_reading,last.infl_form)
                    if (first.pos=='動詞' and first.pos_sub.startswith('自立')
                            and _completed_predicate_token(native)
                            and _productive_predicate(remainder,first.surface)):
                        return face if return_action else True
            if allow_open_tail and _native_open_predicate(face+predicate_tail,face):
                return face if return_action else True
            if not _allows_grammatical_tail(forms,predicate_tail,reading,face):
                continue
            parts=list(tokenize(face+predicate_tail))
            if not _productive_predicate(face+predicate_tail,face):
                continue
            # Native full volition (しよ + う) shares the same exact
            # paradigm and productive-tail validation. Contracted しょう
            # still does not establish a new action-noun boundary.
            # 48-ZN: this positive reading reconstruction requires an
            # explicit native polite auxiliary. Bare dialectal/contracted
            # しん or しょう are not enough to establish a new word split.
            # Their actual original tokenization remains available to the
            # existing grammar; this is not a new negative judgment.
            if not parts:
                continue
            polite=any(t.pos=='助動詞' and t.base_form=='ます'
                       and t.has_reading for t in parts[1:])
            # 48-AAR: before an independently anomalous mark, explicit
            # modern して/した/する also establishes an unchanged boundary.
            # This optional proof never accepts contracted しん/しょう.
            last=parts[-1]
            # A native sentence-final particle follows the same finite
            # predicate. The full tail and its actual POS were proven above.
            # An open connective is source-only evidence, never a newly
            # completed candidate merely because its grammar is possible.
            if len(parts)>=3 and last.pos=='助詞' and (
                    last.pos_sub.startswith('終助詞') or allow_open_tail
                    and last.pos_sub.startswith('接続助詞')):
                previous=parts[-2]
                native=(previous.surface,previous.pos+(':'+previous.pos_sub if previous.pos_sub else ''),
                        previous.reading,previous.start,previous.end,previous.has_reading,previous.infl_form)
                if _completed_predicate_token(native):
                    # A final particle must not turn an unproved contracted
                    # predicate into a completed one. Reuse the same core
                    # proof, including modern nonpolite endings, before it.
                    completed=completed_sahen_reading(text[:-len(last.surface)],
                        allow_nonpolite=True,object_faces=object_faces,
                        return_action=return_action,action_note_following=action_note_following,
                        subject_faces=subject_faces,case_argument=case_argument,
                        allow_open_tail=allow_open_tail,relative_faces=relative_faces)
                    if completed:return completed
            # 48-ACS: native Vてください is a completed request. The
            # productive predicate above verifies the preceding inflection;
            # a bare imperative or an arbitrary noun is not this proof.
            request_parts=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),
                            t.reading,t.start,t.end,t.has_reading,t.infl_form) for t in parts]
            if _native_request_tail(request_parts):
                return face if return_action else True
            if (len(parts)>=3 and last.has_reading and last.pos=='助動詞'
                    and last.base_form in ('う','よう') and last.infl_form=='基本形'
                    and parts[-2].base_form=='する' and parts[-2].reading=='しよ'
                    and parts[-2].infl_form=='未然ウ接続'):
                # Full native suru volition is explicit completion even
                # without a polite auxiliary. Grammar was proved above.
                # The native dictionary also tags contracted しょ as this
                # form; only the full modern しよ proves a new word split.
                return face if return_action else True
            if not polite:
                if not allow_nonpolite:
                    continue
                if (last.pos=='助詞' and last.pos_sub.startswith('接続助詞')
                        and last.surface in ('て','で') and len(parts)>=3):
                    from contextual_repair import _modern_te_allowed
                    previous=parts[-2]
                    if _modern_te_allowed(previous.surface,previous.reading,last.surface) is True:
                        return face if return_action else True
                    continue
                if not (last.has_reading and last.infl_form=='基本形' and (
                        (_sahen_verb_form(last.pos+','+last.pos_sub.replace(':',','),last.base_form,last.surface,last.infl_form,last.reading))
                        or (last.pos=='助動詞' and (last.base_form in ('た','ない','まい')
                            or allow_open_tail and last.base_form in ('ぬ','ん'))))):
                    continue
            legacy=(last.surface,last.pos+(':'+last.pos_sub if last.pos_sub else ''),
                    last.reading,last.start,last.end,last.has_reading,last.infl_form)
            if _completed_predicate_token(legacy):
                return face if return_action else True
    return False



@lru_cache(maxsize=4096)
def native_relative_action(head):
    """The unchanged finite relative clause and its already occupied cases."""
    from morphology import tokenize
    attributive=native_attributive_predicate_end(head)
    verb_head=completed_native_verb_reading(head,True) if attributive else False
    occupied_cases=()
    if attributive and not verb_head:
        native_parts=tokenize(head)
        # Reuse the source case positions, including cases swallowed
        # by an unknown token. Occupied objects/subjects must remain
        # occupied when the relative head is checked below.
        markers=('を','が','は','も','に','へ','で','から')
        occupied=list(head[cut:cut+len(marker)]
            for cut in native_case_positions(head,native_parts,markers)
            for marker in markers if head.startswith(marker,cut))
        # 48-AKH: a proved genitive noun can precede copular-looking で.
        # Share the same original noun/case evidence as clause completion;
        # arbitrary copulas and changed readings supply no occupied case.
        for cut in range(1,len(head)-2):
            choices=tuple(marker for marker in markers if head.startswith(marker,cut))
            if not choices:continue
            faces=native_nominal_phrase_faces(head[:cut])
            if not faces:continue
            for marker in choices:
                if native_nominal_case_boundary(head,native_parts,cut,marker,faces) is not None:
                    occupied.append(marker)
        occupied_cases=tuple(dict.fromkeys(occupied))
        if occupied_cases:
            action=completed_native_reading_clause(head,allow_nonpolite=True,
                require_nominal=True,require_object_fit=True,return_action=True)
            if action:
                verb_head=action
                # The clause proved the original cases and predicate.
                # Keep a native verb's full finite tail for its meaning;
                # a bare continuative such as かい loses that evidence.
                for t in reversed(native_parts):
                    if t.pos=='動詞' and t.has_reading and t.surface==action:
                        finite=head[t.start:]
                        if completed_native_verb_reading(finite,True,False):
                            verb_head=finite;break
                else:
                    # The same proved action can be inside the
                    # unknown best-parse token. Keep its finite tail.
                    finite=_native_completed_action_suffix(head,action)
                    if finite:verb_head=finite
    return (verb_head,occupied_cases) if verb_head else ()


@lru_cache(maxsize=4096)
def native_adnominal_reading_parts(text, allow_predicative=False):
    """48-ZQ: native adjective/adnominal + ordinary noun in the same reading.

    GPT-6 / 2026-09-11. Returned spellings only carry dictionary evidence;
    they are never chosen as output text. A case or a finite tail cannot be
    reinterpreted as a modifier. Unknown readings supply no positive proof.
    """
    if not text or len(text)<4 or not all('ぁ'<=c<='ゖ' or c=='ー' for c in text):
        return ()
    from corrector import table_surfaces_for_reading
    from morphology import dictionary_inflections, native_independent_adjective, tokenize
    def entries(reading):
        for face in dict.fromkeys((reading,*table_surfaces_for_reading(reading,limit=12))):
            for pos,form,lemma,rd in dictionary_inflections(face) or ():
                if rd==reading:
                    yield face,pos,form,lemma,rd
    for cut in range(2,len(text)-1):
        head,noun=text[:cut],text[cut:]
        modifiers=[]
        head_entries=list(entries(head))
        # 48-ZV: use native grammatical ambiguity, not the entire class of
        # demonstratives. この/その are adnominals; ある also independently
        # ends a native verb clause. Its new nominal reading needs the
        # explicit case/predicate context supplied by the caller.
        finite_homograph=any(row[1].startswith(('動詞,','助動詞,')) and row[2]=='基本形'
                              for row in head_entries)
        for row in head_entries:
            if ((row[1].startswith('連体詞,') and (allow_predicative or not finite_homograph))
                    or native_independent_adjective(row[1],row[2],row[3])):
                modifiers.append((row,))
        if head.endswith('な') and len(head)>2:
            copulas=[('な',pos,form,lemma,rd) for pos,form,lemma,rd in dictionary_inflections('な') or ()
                     if pos.startswith('助動詞,') and form=='体言接続' and lemma=='だ' and rd=='な']
            for row in entries(head[:-1]):
                if row[1].startswith('名詞,形容動詞語幹,'):
                    modifiers.extend((row,copula) for copula in copulas)
        relative=native_relative_action(head) if allow_predicative else ()
        verb_head,occupied_cases=relative if relative else (False,())
        verb_parts=tokenize(head) if verb_head else []
        if not modifiers and not verb_head:
            continue
        from kango_tier import usage_tier_for_reading
        nouns=[row for row in entries(noun) if row[1].startswith('名詞,')
               and usage_tier_for_reading(row[0],row[4]) in (1,2)
               and not any(kind in row[1] for kind in ('固有名詞','接尾','非自立'))]
        polite=native_polite_nominal_parts(noun) if not nouns else ()
        result=modifiers[0]+((nouns[0],) if nouns else polite[0]) if modifiers and (nouns or polite) else ()
        if not result and verb_head:
            from semantic_roles import relative_action_support
            verb_nouns=[row for row in nouns if relative_action_support(row[0],verb_head,occupied_cases)]
            if verb_nouns:
                result=tuple((t.surface,t.pos+','+t.pos_sub.replace(':',','),
                              t.infl_form,t.base_form,t.reading) for t in verb_parts)+(verb_nouns[0],)
        if result:
            # Do not cut the original first known word (e.g. a
            # connective) into a shorter modifier. A later token may
            # instead be an accidental split of the newly proven whole
            # modifier, so it cannot independently establish this edge.
            if any(token.has_reading and token.start==0 and cut<token.end
                   for token in tokenize(text)):
                continue
            return result
    return ()



@lru_cache(maxsize=4096)
def completed_native_nominal_predicate(text, allow_topic=True):
    """An unchanged native noun reading with an existing finite copular tail."""
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    if not bare or not 2<=len(bare)<=40 or not all('ぁ'<=c<='ゖ' or c=='ー' for c in bare):return False
    from morphology import tokenize
    from pos_grammar import _NOUN_PRED
    from contextual_repair import _completed_predicate_token
    finite={piece for piece,state in _NOUN_PRED if state in ('END','TA')}
    if allow_topic:
        for particle in tokenize(bare):
            nominative=(particle.surface=='が' and particle.pos_sub.startswith('格助詞'))
            topic=(particle.surface in ('は','も') and particle.pos_sub.startswith('係助詞'))
            if (particle.pos=='助詞' and particle.has_reading and (nominative or topic)
                    and native_nominal_phrase_faces(bare[:particle.start])
                    and completed_native_nominal_predicate(bare[particle.end:],allow_topic=False)):
                return True
    for cut in range(1,len(bare)):
        tail=bare[cut:]
        if not any(tail.startswith(piece) for piece in finite):continue
        faces=native_nominal_phrase_faces(bare[:cut])
        if not faces:
            modifier=native_adnominal_reading_parts(bare[:cut],allow_predicative=True)
            if modifier:faces=(''.join(part[0] for part in modifier),)
        for face in faces:
            parts=[t for t in tokenize(face+tail) if t.start>=len(face)]
            if (not parts or parts[0].start!=len(face)
                    or not all(t.has_reading for t in parts)
                    or ''.join(t.surface for t in parts)!=tail):continue
            while parts and parts[-1].pos=='助詞' and '終助詞' in parts[-1].pos_sub:
                parts.pop()
            if (not parts or ''.join(t.surface for t in parts) not in finite
                    or not all(t.pos=='助動詞' for t in parts)):continue
            last=parts[-1]
            legacy=(last.surface,last.pos,last.reading,last.start,last.end,last.has_reading,last.infl_form)
            if _completed_predicate_token(legacy):return True
    return False


@lru_cache(maxsize=4096)
def completed_native_state_clause(text):
    """An unchanged Nのまま(で) adjunct followed by a proved native clause.

    GPT-6 Astra / 2026-09-14: grammatical composition, no output vocabulary.
    JF BMA00025 attests Nの + まま and the optional connective で.
    https://www.kyozai.jpf.go.jp/kyozai/material/BMA00025/ja/render.do
    """
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    if (not 7<=len(bare)<=80 or 'のまま' not in bare
            or not all('ぁ'<=c<='ゖ' or c=='ー' for c in bare)):return False
    import re
    from morphology import tokenize
    for marker in re.finditer('のまま',bare):
        faces=native_nominal_phrase_faces(bare[:marker.start()])
        if not faces:continue
        attested=False
        for face in faces:
            parts=[t for t in tokenize(face+'のまま') if t.start>=len(face)]
            if (len(parts)==2 and parts[0].surface=='の' and parts[0].pos=='助詞'
                    and parts[0].pos_sub=='連体化' and parts[1].surface=='まま'
                    and parts[1].pos=='名詞' and parts[1].pos_sub.startswith('非自立')
                    and all(t.has_reading for t in parts)):
                attested=True;break
        if not attested:continue
        right=bare[marker.end():]
        if right.startswith('で'):right=right[1:]
        if right and completed_native_reading(right):return True
    return False


@lru_cache(maxsize=4096)
def completed_native_prerequisite_sequence(text):
    """Native Vてから + negative condition + a proved negative consequence.

    GPT-6 Astra / 2026-09-14: positive composition of a prerequisite reading.
    A nonnegative consequence is unclassified here, not declared anomalous.
    """
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    if (not 12<=len(bare)<=80 or 'から' not in bare
            or not all('ぁ'<=c<='ゖ' or c=='ー' for c in bare)):return False
    import re
    from morphology import tokenize
    for match in re.finditer('[てで]から((?:で|じゃ)(?:ないと|なければ))',bare):
        edge=match.start(1)
        if not completed_native_reading_link(bare[:edge]):continue
        condition=[t for t in tokenize(bare[:match.end()]) if t.start>=edge]
        if (len(condition)!=3 or ''.join(t.surface for t in condition)!=match.group(1)
                or not all(t.has_reading for t in condition)):continue
        copula,negative,link=condition
        nominal_connection=((copula.surface=='で' and copula.pos=='助動詞'
                             and copula.base_form=='だ' and copula.infl_form=='連用形')
                            or copula.surface=='じゃ' and copula.pos=='助詞'
                            and copula.pos_sub=='副助詞')
        negative_connection=(negative.pos=='助動詞' and negative.base_form=='ない'
                             and link.pos=='助詞' and link.pos_sub=='接続助詞'
                             and (negative.infl_form,link.surface) in (('基本形','と'),('仮定形','ば')))
        if not nominal_connection or not negative_connection:continue
        right=bare[match.end():]
        if native_negative_predicate(right) and completed_native_link_clause(right):return True
    return False


@lru_cache(maxsize=4096)
def completed_native_reading(text):
    """Share native nominal phrases and completed clauses at every entry."""
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    return bool(bare in _seed_nominal_readings() or native_relational_compound_heads(bare)
                or native_katakana_nominal_face(bare)
                or native_adnominal_reading_parts(bare) or completed_native_nominal_predicate(text)
                or completed_native_reading_clause(text)
                or completed_native_reading_sequence(text) or completed_native_action_note(text)
                or completed_native_adjunct_clause(text) or completed_native_temporal_clause(text)
                or completed_native_state_clause(text) or completed_native_prerequisite_sequence(text))


def native_negative_predicate(text):
    """Native auxiliary polarity in this predicate; no distant clause search."""
    from morphology import tokenize, dictionary_inflections
    parts=tokenize(text)
    if not parts or any(not t.has_reading for t in parts):return False
    for t in parts:
        if t.pos=='助動詞' and any(pos.startswith('助動詞,')
                and base in ('ない','ぬ','ん','まい') and form==t.infl_form
                and rd==t.reading for pos,form,base,rd in dictionary_inflections(t.surface) or ()):
            return True
        if t.pos=='助詞' and t.pos_sub.startswith('接続助詞'):
            return False
    return False


def native_nominal_case_boundary(source,original,cut,particle,faces,allow_known_noun=False):
    """Shared actual/unknown-source case proof; never use a changed reading.

    Return the projected native noun, if one was needed, and the existing
    special nominative reopening flag. None means no affirmative boundary.
    """
    from morphology import tokenize,dictionary_inflections
    size=len(particle)
    if not any(pos.startswith(('助詞,格助詞,一般,','助詞,係助詞,')) and rd==particle
               for pos,form,base,rd in dictionary_inflections(particle) or ()):
        return None
    if any(t.start==cut and t.end==cut+size and t.has_reading and t.pos=='助詞'
           and t.pos_sub.startswith(('格助詞:一般','係助詞')) for t in original):
        return None,False
    # 48-AJE: IPADIC labels actual 家族と食べる / 友達と話す as
    # 格助詞:引用 too. A native nominal reading can supply the comitative
    # alternative, but every caller must prove its positive と-case role.
    # Quoted predicates and coordinating と do not establish this edge.
    if particle=='と' and faces and any(t.start==cut and t.end==cut+1
            and t.has_reading and t.pos=='助詞' and t.pos_sub=='格助詞:引用' for t in original):
        return faces[0],True
    swallowed=any(not t.has_reading and t.start<=cut and cut+size<=t.end for t in original)
    strict_case_fit=bool(particle=='が' and any(
        t.has_reading and t.pos=='名詞' and t.start<cut<t.end and t.end==cut+size for t in original))
    # 48-AJY: kana N + instrumental/location で can be parsed as
    # copular で/でし. Reproject only the unchanged complete noun;
    # its positive case role with the same completed action remains
    # mandatory. This does not establish a bare copula as a case.
    if particle=='で' and faces and any(t.start==cut and t.has_reading
            and t.pos=='助動詞' and t.base_form in ('だ','です')
            and t.surface.startswith('で') and t.infl_form=='連用形' for t in original):
        strict_case_fit=True
    if particle=='が':
        # A whole attested noun can have an accidental nonfinite verb parse.
        # Such a form cannot supply adversative が; reopening the nominal
        # case requires positive subject/predicate fit below.
        from contextual_repair import _completed_predicate_token
        connector=next((t for t in original if t.start==cut and t.end==cut+size),None)
        previous=next((t for t in reversed(original) if t.end==cut),None)
        if (connector and previous and connector.has_reading and connector.pos=='助詞'
                and connector.pos_sub=='接続助詞' and previous.has_reading
                and previous.pos=='動詞' and previous.infl_form.startswith('連用')
                and not _completed_predicate_token((previous.surface,
                    previous.pos+(':'+previous.pos_sub if previous.pos_sub else ''),previous.reading,
                    previous.start,previous.end,previous.has_reading,previous.infl_form))):
            strict_case_fit=True
    if allow_known_noun:
        swallowed=swallowed or any(t.has_reading and t.pos=='名詞'
            and t.start<cut<t.end and t.end==cut+size for t in original)
    # A full established noun reading may be split into an internal name
    # ending in を (ひらがなを -> ひ/ら/が/なを). The first source word
    # itself is never shortened. Reopening needs positive object/action fit.
    if particle=='を' and any(t.has_reading and t.pos=='名詞'
            and t.pos_sub.startswith('固有名詞') and 0<t.start<cut
            and t.end==cut+size for t in original):
        strict_case_fit=True
    if (particle in ('は','も') and native_plural_nominal_heads(source[:cut])
            and any(t.has_reading and t.pos=='名詞' and t.start==cut<t.end-size
                    for t in original)
            and completed_native_reading_clause(source[cut+size:],require_object_fit=True)):
        swallowed=True
    if not swallowed and not strict_case_fit:return None
    for face in faces:
        prefix=tokenize(face+particle)
        if (prefix and prefix[-1].start==len(face) and prefix[-1].end==len(face)+size
                and prefix[-1].has_reading and prefix[-1].pos=='助詞'
                and prefix[-1].pos_sub.startswith(('格助詞:一般','係助詞'))):
            return face,strict_case_fit
    return None


@lru_cache(maxsize=4096)
def completed_native_verb_reading(text, allow_nonpolite=False, require_roles=True):
    """Return a known content-verb head with the actual unchanged native tail.

    The same modern inflection and positive semantic roles used by nominal
    clauses apply to ordinary verbs, including a finite relative modifier.
    This does not infer grammar from the last kana or an unknown dictionary row.
    """
    if not text or not all('ぁ'<=c<='ゖ' or c=='ー' for c in text):return False
    from morphology import tokenize,dictionary_inflections
    from contextual_repair import _productive_predicate,_completed_predicate_token
    from semantic_roles import native_verb_roles
    if allow_nonpolite and not require_roles and text.endswith(('て','で')):
        # Source-only bare links can have a native noun homograph (貝で /
        # 嗅いで). Exact verb inflection and modern euphony establish the
        # unedited reading without selecting a kanji or inventing context.
        stem=text[:-1]
        if any(pos.startswith('動詞,自立,') and rd==stem
               and form.startswith('連用')
               for pos,form,base,rd in dictionary_inflections(stem) or ()):
            from contextual_repair import _modern_te_allowed
            if _modern_te_allowed(stem,stem,text[-1]) is True:return text
    parts=tokenize(text)
    if (not parts or not all(t.has_reading for t in parts)
            or parts[0].pos!='動詞' or not parts[0].pos_sub.startswith('自立')
            or require_roles and not (
                native_verb_roles(parts[0].surface,parts[0].infl_form,parts[0].reading)
                or native_verb_roles(parts[0].surface,parts[0].infl_form,parts[0].reading,subject=True))):
        return False
    legacy=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),
             t.reading,t.start,t.end,t.has_reading,t.infl_form) for t in parts]
    request=_native_request_tail(legacy)
    connective=(allow_nonpolite and len(parts)>1 and parts[-1].surface in ('て','で')
                and parts[-1].pos=='助詞' and parts[-1].pos_sub.startswith('接続助詞'))
    core=native_predicate_finite_core(legacy)
    finite=bool(core and _completed_predicate_token(core[-1]))
    polite=any(t.pos=='助動詞' and t.base_form=='ます' for t in parts[1:])
    if (not (request or connective or finite) or not (allow_nonpolite or polite or request)
            or not _productive_predicate(text,parts[0].surface)):
        return False
    if connective:
        from contextual_repair import _modern_te_allowed
        prev=parts[-2]
        if _modern_te_allowed(prev.surface,prev.reading,parts[-1].surface) is not True:return False
    return text



def _native_open_case_head(text,particle,faces):
    """Exact native unfinished verb plus independently proved source case."""
    if particle not in ('を','が','に','へ','で'):return False
    from morphology import dictionary_inflections
    from semantic_roles import native_verb_roles,NOUN_ROLES
    for pos,form,base,rd in dictionary_inflections(text) or ():
        if not (pos.startswith('動詞,自立,') and rd==text
                and form.startswith(('連用','未然','仮定'))):continue
        roles=native_verb_roles(text,form,rd,subject=particle=='が',
            case=particle if particle in ('に','へ','で') else None)
        if any(roles & NOUN_ROLES.get(face,set()) for face in faces):return text
    return False


@lru_cache(maxsize=4096)
def native_resultative_reading(text, object_faces, allow_nonpolite=False):
    """An unchanged adjective continuative + finite suru and its result object."""
    if not text or not 4<=len(text)<=30 or not all('ぁ'<=c<='ゖ' for c in text):return False
    from morphology import tokenize,dictionary_inflections
    from semantic_roles import resultative_adjective_roles,nominal_roles
    object_roles=set().union(*(nominal_roles(face) for face in object_faces))
    if not object_roles:return False
    for cut in range(2,min(15,len(text)-1)):
        adjective,predicate=text[:cut],text[cut:]
        if not resultative_adjective_roles(adjective)&object_roles:continue
        parts=tokenize(predicate)
        if not parts:continue
        head=parts[0]
        from morphology import native_suru_form
        if not (head.pos=='動詞' and head.base_form=='する' and head.reading==head.surface
                and native_suru_form(head.surface,head.infl_form,head.reading,False)
                and any(pos.startswith('動詞,自立,') and base=='する'
                        and form==head.infl_form and rd==head.reading
                        for pos,form,base,rd in dictionary_inflections(head.surface) or ())):continue
        if completed_native_verb_reading(predicate,allow_nonpolite,require_roles=False):return text
    return False


@lru_cache(maxsize=4096)
def completed_native_reading_clause(text, allow_nonpolite=False, require_nominal=False,
                                    require_object_fit=False, modifier_reading=None,
                                    return_action=False, action_note_following=None,
                                    nominal_constraint=None, modifier_constraint=None,
                                    seen_cases=(), allow_open_tail=False):
    """48-ZM: an unedited nominal case followed by a native finite action.

    GPT-6 / 2026-09-11. This is a grammatical reading of the actual kana,
    independent of the analyzer's accidental split of かくにん into に/ん.
    Unknown words, chained cases and unfinished predicates do not supply
    this positive evidence. No particular kanji spelling is selected.
    """
    source=text
    if text and text[-1] in '。！？.!?':
        text=text[:-1]
    if not text or not all('ぁ'<=c<='ゖ' or c=='ー' for c in text):
        return False
    if not require_nominal:
        action=completed_sahen_reading(text,allow_nonpolite=allow_nonpolite,
            return_action=return_action,action_note_following=action_note_following)
        if action:return action
        verb=completed_native_verb_reading(text,allow_nonpolite)
        if verb:return verb if return_action else True
    from morphology import tokenize as native_tokenize
    def original_tokens(value):
        return [(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                 t.start,t.end,t.has_reading,t.infl_form) for t in native_tokenize(value)]
    if (not require_object_fit and modifier_reading is None and not return_action
            and native_nominal_reading_context(source,0,len(text),original_tokens,require_predicate=True)):
        return True
    from corrector import table_surfaces_for_reading
    from morphology import dictionary_inflections, tokenize
    # The noun is established by its reading, but the nominal case must
    # be the actual original token. A dictionary homograph of の as a
    # nominative case cannot turn an adnominal の into a main-clause case.
    # 48-ZS: punctuation belongs to the source parse. Removing it before
    # tokenization may swallow an otherwise known case and predicate.
    original=[part for part in tokenize(source) if part.end<=len(text)]
    for cut in range(1,len(text)-2):
        reading=text[:cut]
        if nominal_constraint and reading!=nominal_constraint[0]:continue
        faces=list(nominal_constraint[1] if nominal_constraint else native_nominal_phrase_faces(reading))
        short_faces=()
        if not nominal_constraint and not faces and len(reading)==1:
            from semantic_roles import short_role_noun_faces
            short_faces=short_role_noun_faces(reading);faces=list(short_faces)
        composed_nominal=bool(not nominal_constraint and faces and not _native_nominal_reading_faces(reading))
        base_case_fit=require_object_fit or composed_nominal
        # 48-ZQ: a native modifier plus native noun is also a nominal
        # case head. Keep every kana; the compound spelling is used only
        # when an unknown token swallowed the following original case.
        nominal=() if nominal_constraint else native_adnominal_reading_parts(reading,allow_predicative=True)
        if nominal:
            faces.append(''.join(part[0] for part in nominal))
        if not faces:
            continue
        for size in range(1,min(4,len(text)-cut)+1):
            particle=text[cut:cut+size]
            needs_case_fit=base_case_fit
            if particle in seen_cases:continue
            boundary=native_nominal_case_boundary(source,original,cut,particle,faces)
            if boundary is None and particle in ('に','へ'):
                boundary=native_nominal_case_boundary(source,original,cut,particle,faces,allow_known_noun=True)
                if boundary is not None:needs_case_fit=True
            if (boundary is None and particle=='と'
                    and any(t.start==cut and t.end==cut+1 and t.has_reading
                            and t.pos=='助詞' and t.pos_sub in ('並立助詞','接続助詞')
                            for t in original)
                    and native_object_predicate_frames(text[cut+1:])):
                # 48-AJT: a companion can precede a separate content object.
                # The nested clause must prove its own object and the same
                # action's positive companion role; keep every source kana.
                boundary=(faces[0],True)
            if boundary is None:
                # 48-AJE: と + a complete action reading can be swallowed
                # by an unfinished verb token (とべん + きょうします).
                # The whole native sahen action and the companion's case
                # role must both be independently proved before reopening.
                owner=next((part for part in original if part.start==cut and part.end>cut+size),None)
                if (particle=='と' and owner and owner.has_reading and owner.pos=='動詞'
                        and owner.surface.startswith('と')):
                    action=completed_sahen_reading(text[cut+size:],allow_nonpolite=allow_nonpolite,
                        return_action=return_action,case_argument=('と',tuple(faces)),
                        allow_open_tail=allow_open_tail)
                    if action:return action
                # A compound case such as にて can absorb the first kana of
                # the next object. Prove the entire remaining object clause
                # and this recipient's role before using the shorter case.
                compound=next((part for part in original if part.start==cut),None)
                if (particle in ('に','へ') and compound and compound.has_reading
                        and compound.pos=='助詞' and compound.pos_sub.startswith('格助詞')
                        and compound.surface.startswith(particle) and len(compound.surface)>size
                        and any(pos.startswith('助詞,格助詞,') and rd==particle
                                for pos,form,base,rd in dictionary_inflections(particle) or ())):
                    # 48-AGQ: a native compound case may swallow the onset
                    # of a complete verb, not only a second nominal clause.
                    # Its unchanged inflection AND this noun's case role
                    # must agree before the shorter boundary supplies proof.
                    predicate=text[cut+size:]
                    if completed_native_verb_reading(predicate,allow_nonpolite,require_roles=False):
                        from semantic_roles import native_verb_roles,nominal_roles
                        head=tokenize(predicate)[0]
                        roles=native_verb_roles(head.surface,head.infl_form,head.reading,
                            case=particle,tail=predicate[head.end:])
                        if any(roles & nominal_roles(face) for face in faces):
                            return head.surface if return_action else True
                    if allow_open_tail and _native_open_case_head(text[cut+size:],particle,faces):
                        return text[cut+size:] if return_action else True
                    nested=completed_native_reading_clause(text[cut+size:],
                        allow_nonpolite=allow_nonpolite,require_nominal=True,
                        require_object_fit=True,return_action=True,seen_cases=seen_cases+(particle,),
                        allow_open_tail=allow_open_tail)
                    if nested:
                        from semantic_roles import proved_action_case_support
                        if any(proved_action_case_support(face,particle,nested,context=text[cut+size:]) for face in faces):
                            return nested if return_action else True
                continue
            case_face,strict_case_fit=boundary
            needs_case_fit=needs_case_fit or strict_case_fit
            # 48-ACF: しか requires a negative predicate, even when the
            # analyzer lists it as an ordinary topic particle. Its native
            # category alone cannot establish an affirmative clause.
            if particle=='しか' and not native_negative_predicate(text[cut+size:]):
                continue
            # 48-ABU: composing a new clause needs positive argument fit;
            # native noun/suru grammar alone also covers "内容を堪忍".
            object_faces=tuple(nominal_constraint[1] if nominal_constraint else short_faces or native_nominal_phrase_faces(reading))
            if nominal:
                object_faces+=(nominal[-1][0],)
            if modifier_reading is not None:
                if not native_attributive_predicate_end(modifier_reading):continue
                from semantic_roles import relative_action_support
                # Consider every native homophone against the actual noun;
                # the first dictionary face alone cannot disprove the reading.
                modifier=completed_sahen_reading(modifier_reading,allow_nonpolite=True,
                    return_action=True,relative_faces=object_faces)
                if not modifier:
                    modifier=completed_native_verb_reading(modifier_reading,allow_nonpolite=True)
                    if not modifier:
                        modifier=completed_native_reading_clause(modifier_reading,
                            allow_nonpolite=True,require_nominal=True,require_object_fit=True,
                            return_action=True,nominal_constraint=modifier_constraint)
                    if not modifier or not any(relative_action_support(noun,modifier) for noun in object_faces):
                        continue
            action=completed_sahen_reading(text[cut+size:],allow_nonpolite=allow_nonpolite,
                    object_faces=object_faces if needs_case_fit and particle=='を' else None,
                    return_action=return_action,action_note_following=action_note_following,
                    allow_open_tail=allow_open_tail,
                    subject_faces=object_faces if needs_case_fit and particle=='が' else None,
                    case_argument=(particle,object_faces) if needs_case_fit and particle not in ('を','が') else None)
            if not action and not allow_nonpolite:
                # 48-ACJ: a newly accepted plain predicate must have the
                # same positive case fit as a composed clause. Merely
                # recognizing its negative auxiliary is not sufficient.
                action=completed_sahen_reading(text[cut+size:],allow_nonpolite=True,
                    object_faces=object_faces if particle=='を' else None,
                    return_action=return_action,action_note_following=action_note_following,
                    allow_open_tail=allow_open_tail,
                    subject_faces=object_faces if particle=='が' else None,
                    case_argument=(particle,object_faces) if particle not in ('を','が') else None)
            if action:return action
            if particle=='を' and action_note_following is None:
                resultative=native_resultative_reading(text[cut+size:],tuple(object_faces),allow_nonpolite=True)
                if resultative:return resultative if return_action else True
            if allow_open_tail and _native_open_case_head(text[cut+size:],particle,object_faces):
                return text[cut+size:] if return_action else True
            # Native adverbs may occur between an argument and its verb.
            # Prove their unchanged readings independently, then verify the
            # same nominal/case and complete predicate with positive roles.
            # The projection is evidence only; it never edits source text.
            remainder=text[cut+size:]
            for adverb_end in native_adverbial_reading_cuts(remainder):
                action=completed_native_reading_clause(text[:cut+size]+remainder[adverb_end:],
                    allow_nonpolite=allow_nonpolite,require_nominal=True,
                    require_object_fit=True,modifier_reading=modifier_reading,
                    return_action=return_action,action_note_following=action_note_following,
                    nominal_constraint=(reading,object_faces),modifier_constraint=modifier_constraint,
                    seen_cases=seen_cases,allow_open_tail=allow_open_tail)
                if action:return action
            # A recipient can precede the unchanged content object. Both
            # arguments must independently fit the same proved predicate.
            if particle in ('を','に','へ','で','と','が','は','も') and action_note_following is None:
                nested=completed_native_reading_clause(text[cut+size:],
                    allow_nonpolite=allow_nonpolite,require_nominal=True,
                    require_object_fit=True,return_action=True,seen_cases=seen_cases+(particle,),
                        allow_open_tail=allow_open_tail)
                if nested:
                    from semantic_roles import proved_action_case_support
                    role_case=('が' if particle in ('は','も')
                               and native_object_predicate_frames(text[cut+size:]) else particle)
                    if any(proved_action_case_support(face,role_case,nested,context=text[cut+size:]) for face in object_faces):
                        return nested if return_action else True
            # 48-ZR / GPT-6 / 2026-09-11: the same native functional
            # predicate proof used by nominal_context also applies to a
            # reading-established nominal head. Require the actual source
            # nominative/topic plus one complete basic verb and auxiliaries;
            # do not claim an arbitrary object/case has an existential role.
            if (not return_action or action_note_following is None) and particle in ('が','は','を','に','へ','で','と','から'):
                tail=[part for part in original if cut<=part.start]
                if case_face is not None:
                    # The existing unknown-case fallback established this
                    # nominal reading. Keep the entire literal suffix and
                    # its native case/form, mapping positions back to source.
                    from morphology import Token
                    offset=cut-len(case_face)
                    projected=tokenize(case_face+text[cut:])
                    tail=[Token(part.surface,part.pos,part.base_form,part.reading,
                                part.start+offset,part.end+offset,part.has_reading,
                                part.pos_sub,part.infl_form)
                          for part in projected if len(case_face)<=part.start]
                if (tail and tail[0].start==cut and tail[0].end==cut+size
                        and tail[0].pos=='助詞'
                        and (tail[0].pos_sub.startswith(('格助詞:一般','係助詞'))
                             or particle=='と' and strict_case_fit and tail[0].pos_sub=='格助詞:引用')
                        and tail[-1].end==len(text)
                        and ''.join(part.surface for part in tail)==text[cut:]
                        and all(part.has_reading for part in tail)
                        and len(tail)>1 and tail[1].pos=='動詞'
                        and all(a.end==b.start for a,b in zip(tail,tail[1:]))):
                    legacy=[(part.surface,part.pos+(':'+part.pos_sub if part.pos_sub else ''),
                             part.reading,part.start,part.end,part.has_reading,part.infl_form)
                            for part in tail]
                    if _native_nominal_functional_tail(legacy,
                            explicit_nominal_case=(particle=='を'),
                            content_object_faces=object_faces if particle=='を' else None,
                            content_subject_faces=object_faces if strict_case_fit and particle=='が' else None,
                            content_case_argument=(particle,object_faces) if particle in ('に','へ','で','と','から') else None,
                            allow_connective=allow_nonpolite,allow_open_tail=allow_open_tail,
                            source_prefix=case_face if case_face is not None else text[:cut]):
                        return tail[1].surface if return_action else True
    return False


@lru_cache(maxsize=4096)
def completed_native_link_clause(text, allow_unclassified=False):
    """A finite clause for a connective, including adverb and nominal predicates.

    A bare noun or open auxiliary tail is not a completed linked clause.
    48-AHY / GPT-6 Astra / 2026-09-16: source-only callers may accept an
    unclassified bare verb whose complete native inflection is proved.
    Candidate object composition keeps the default semantic requirements.
    """
    return bool(completed_native_reading_clause(text,require_object_fit=True)
                or completed_native_nominal_predicate(text)
                or native_adverbial_predicate_reading(text,allow_open_tail=False)
                or allow_unclassified and completed_native_verb_reading(text,require_roles=False))


@lru_cache(maxsize=4096)
def completed_native_reading_link(text, require_nominal=False, nominal_constraint=None,
                                  allow_unclassified=False):
    """A complete native clause plus its written connective, with no edits.

    Shared by sequence protection and the source boundaries of later-clause
    candidates. Proving a later object never certifies a malformed first clause.
    """
    # 48-AHH: the same native te/de clause can precede focus は/も
    # and an independent following clause. The shortened string only
    # proves the source link; it never supplies replacement text.
    if text.endswith(('ては','ても','では','でも')):
        from morphology import dictionary_inflections
        if any(pos.startswith('助詞,係助詞,') and rd==text[-1]
               for pos,form,base,rd in dictionary_inflections(text[-1]) or ()):
            return completed_native_reading_link(text[:-1],
                require_nominal=require_nominal,nominal_constraint=nominal_constraint,
                allow_unclassified=allow_unclassified)
    if (text.endswith(('て','で'))
            and (completed_native_reading_clause(text,allow_nonpolite=True,require_object_fit=True,require_nominal=require_nominal,nominal_constraint=nominal_constraint)
                 or allow_unclassified and not require_nominal and nominal_constraint is None
                 and completed_native_verb_reading(text,True,require_roles=False))):
        return True
    for link in ('ので','から','が'):
        if not text.endswith(link):continue
        predicate=text[:-len(link)]
        if not predicate:return False
        from morphology import tokenize
        actual=tokenize(text);prior=tokenize(predicate)
        if prior and prior[-1].pos=='助詞' and '終助詞' in prior[-1].pos_sub:return False
        # An unknown kana token can hide a real sentence-final particle.
        # Its unchanged finite prefix and native particle entry establish
        # the boundary; a suffix spelling alone cannot do so.
        from pos_grammar import _FINAL_PARTICLES,_EXTRA_PARTICLES
        from morphology import dictionary_inflections
        for particle in _FINAL_PARTICLES|_EXTRA_PARTICLES:
            if (len(predicate)>len(particle) and predicate.endswith(particle)
                    and any(pos.startswith('助詞,') and '終助詞' in pos and rd==particle
                            for pos,form,base,rd in dictionary_inflections(particle) or ())
                    and completed_native_link_clause(predicate[:-len(particle)],allow_unclassified)):
                return False
        proved_finite=(not require_nominal and nominal_constraint is None
                       and completed_native_link_clause(predicate,allow_unclassified))
        if link=='が':
            from contextual_repair import _unchanged_finite_connective
            if _unchanged_finite_connective(text,text)!='が':
                # A positively proved nominal predicate can end inside an
                # unknown token. A real lexical word spanning the proposed
                # connective boundary remains indivisible.
                if (not proved_finite or any(t.has_reading and t.start<len(predicate)<t.end
                                             for t in actual)):return False
        # Temporal Vてから and an actual finite predicate share the same
        # full-clause proof; the latter also covers native 読んだ/終わる.
        if link=='から' and predicate.endswith(('て','で')):
            ending=True
        else:
            from morphology import tokenize
            from contextual_repair import _completed_predicate_token
            parts=tokenize(predicate)
            last=parts[-1] if parts else None
            ending=bool(last and _completed_predicate_token((last.surface,
                last.pos+(':'+last.pos_sub if last.pos_sub else ''),last.reading,
                last.start,last.end,last.has_reading,last.infl_form)))
        return bool((ending or proved_finite) and (completed_native_reading_clause(predicate,
            allow_nonpolite=True,require_object_fit=True,require_nominal=require_nominal,nominal_constraint=nominal_constraint)
            or not require_nominal and nominal_constraint is None
            and completed_native_link_clause(predicate,allow_unclassified)))
    return False


@lru_cache(maxsize=4096)
def _native_completed_action_suffix(text, action):
    """An already proved source action retains its complete literal tail."""
    start=text.rfind(action) if isinstance(action,str) and action else -1
    if start<0:return ''
    suffix=text[start:]
    return suffix if completed_native_verb_reading(suffix,True,False) else ''


@lru_cache(maxsize=4096)
def native_attributive_predicate_end(text):
    """A finite polite ending alone does not prove a new relative-clause seam."""
    from morphology import tokenize
    from contextual_repair import _completed_predicate_token
    parts=tokenize(text)
    last=parts[-1] if parts else None
    if not last or last.end!=len(text):return False
    if last.pos=='助動詞':
        if last.base_form in ('ます','です','まい'):return False
        # 48-AJG: literary auxiliaries distinguish finite and attributive
        # forms (き/し, けり/ける). Their native terminal form cannot
        # modify a following noun merely because it ends a sentence.
        from morphology import dictionary_paradigms
        actual=tuple(row for row in dictionary_paradigms(last.surface) or ()
                     if row[0].startswith('助動詞,') and row[2]==last.infl_form
                     and row[3]==last.base_form and row[4]==last.reading)
        if actual and all(row[1].startswith('文語・') for row in actual):
            return last.infl_form in ('体言接続','連体形')
    if _completed_predicate_token((last.surface,
        last.pos+(':'+last.pos_sub if last.pos_sub else ''),last.reading,
        last.start,last.end,last.has_reading,last.infl_form)):return True
    # 48-AKA: a full kana clause can end inside one unknown token.
    # Its unchanged nominal case and completed action must first be
    # proved together. Reuse the actual, shorter native finite suffix
    # to distinguish attributive from polite/literary terminal forms.
    if last.has_reading or not all('ぁ'<=c<='ゖ' or c=='ー' for c in text):return False
    action=completed_native_reading_clause(text,allow_nonpolite=True,
        require_nominal=True,require_object_fit=True,return_action=True)
    suffix=_native_completed_action_suffix(text,action)
    return bool(suffix and len(suffix)<len(text)
                and native_attributive_predicate_end(suffix))


@lru_cache(maxsize=4096)
def completed_native_reading_sequence(text, nominal_constraint=None, allow_unclassified=False):
    """48-ABU / GPT-6 / 2026-09-13: compose independently proved clauses.

    No kana is edited and no output spelling is chosen. A native modern
    connective joins two complete readings; a plain sahen predicate may
    modify an independently proved nominal-case clause. Arbitrary word
    coverage, adjacent finite predicates and incomplete tails prove nothing.
    Explicit objects and the modified noun require positive fit in the shared
    semantic-role table. Missing fit leaves the existing anomaly checks active;
    it is not a claim that an unlisted metaphor or object is incorrect.
    """
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    if not 8<=len(bare)<=80 or not all('ぁ'<=c<='ゖ' or c=='ー' for c in bare):
        return False
    # Native short verbs can form complete links (書いて / 見て).
    # Their dictionary inflection and the next clause provide the proof;
    # a four-kana minimum is not a grammatical boundary.
    for cut in range(2,len(bare)-3):
        left,right=bare[:cut],bare[cut:]
        if (completed_native_reading_link(left,require_nominal=bool(nominal_constraint),
                nominal_constraint=nominal_constraint,allow_unclassified=allow_unclassified)
                and (completed_native_link_clause(right,allow_unclassified)
                     or completed_native_reading_sequence(right,allow_unclassified=allow_unclassified))):
            return True
        if not native_attributive_predicate_end(left):
            continue
        # An adnominal predicate needs an actual nominal head on its right.
        # A second standalone action (e.g. ...した...します) is not a noun.
        modifier=(completed_sahen_reading(left,allow_nonpolite=True)
                  if left.endswith(('した','する')) else completed_native_verb_reading(left,True))
        if not modifier:
            # An attributive predicate may carry its own original object.
            # Prove that whole clause before relating it to the next noun.
            modifier=completed_native_reading_clause(left,allow_nonpolite=True,
                require_nominal=True,require_object_fit=True,return_action=True,
                nominal_constraint=nominal_constraint)
        if (modifier and not left.endswith(('て','で'))
                and completed_native_reading_clause(right,require_nominal=True,
                    require_object_fit=True,modifier_reading=left,modifier_constraint=nominal_constraint)):
            return True
    return False


@lru_cache(maxsize=4096)
def native_bare_action_faces(text):
    """Ordinary native sahen spellings with this exact unedited reading."""
    if not text or not 2<=len(text)<=12 or not all('ぁ'<=c<='ゖ' for c in text):
        return ()
    from morphology import dictionary_inflections
    return tuple(face for face in _native_nominal_reading_faces(text)
                 if any(pos.startswith('名詞,サ変接続,') and reading==text
                        for pos,form,base,reading in dictionary_inflections(face) or ()))


@lru_cache(maxsize=4096)
def native_polite_action_prefixes(text):
    """48-AJC: unchanged action nouns before a native polite predicate end.

    This establishes only a possible attachment, not the source's anomaly.
    The original finite auxiliary and exact ordinary sahen reading are
    required; no hypothetical repaired prefix supplies the evidence.
    """
    if not text or not 5<=len(text)<=24 or not all('ぁ'<=c<='ゖ' for c in text):return ()
    from morphology import tokenize,dictionary_inflections
    parts=tokenize(text)
    if not parts or parts[-1].end!=len(text):return ()
    last=parts[-1]
    if not (last.has_reading and last.pos=='助動詞' and last.infl_form=='基本形'):return ()
    polite=any(t.has_reading and t.pos=='助動詞' and t.base_form=='ます'
        and any(pos.startswith('助動詞,') and base=='ます' and form==t.infl_form and rd==t.reading
                for pos,form,base,rd in dictionary_inflections(t.surface) or ()) for t in parts[-3:])
    if not polite:return ()
    import oddness
    legacy=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
             t.start,t.end,t.has_reading,t.infl_form) for t in parts]
    broken=[a[4] for a,b in zip(legacy,legacy[1:]) if oddness.polite_aux_mismatch(a,b)]
    # Only the already malformed polite attachment licenses this action
    # scope. A normal N-ga-arimasu clause may happen to start with a sahen
    # reading; that overlap must not turn a noun repair into an action test.
    if not broken:return ()
    return tuple(cut for cut in range(2,len(text)-2) if cut<max(broken)
                 and native_bare_action_faces(text[:cut]))


@lru_cache(maxsize=4096)
def _native_action_note_heads(text):
    """Use the same clause proof and its exact action; never re-guess its boundary."""
    for cut in range(4,len(text)-1):
        left,right=text[:cut],text[cut:]
        if not left.endswith('して'):
            continue
        right_heads=native_bare_action_faces(right) or _native_action_note_heads(right)
        if not right_heads:
            continue
        head=completed_native_reading_clause(left,allow_nonpolite=True,
            require_object_fit=True,return_action=True,action_note_following=right_heads)
        if head:return (head,)
    return ()


# 48-ACE: closed discourse/question modifiers of an abbreviated action.
# Actual native token boundaries and POS are still required; these written
# words are grammatical roles, not correction answers.
ACTION_NOTE_INTRODUCERS=frozenset('そして それから まず なぜ どうして なんで'.split())


@lru_cache(maxsize=4096)
def native_action_note_introduction(text):
    if (not text or not 4<=len(text)<=80
            or not any(text.startswith(word) for word in ACTION_NOTE_INTRODUCERS)
            or not all('ぁ'<=c<='ゖ' for c in text)):return False
    from morphology import tokenize
    parts=tokenize(text)
    if not parts:return False
    first=parts[0]
    return bool(first.start==0 and first.has_reading
        and first.surface in ACTION_NOTE_INTRODUCERS
        and first.pos in ('接続詞','副詞')
        and native_bare_action_faces(text[first.end:]))


@lru_cache(maxsize=4096)
def completed_native_action_note(text):
    """48-ABY: a linked instruction such as confirm-and-save may end in a noun.

    The existing grammatical evidence proves each unchanged clause. Shared
    semantic roles additionally prove a plausible action sequence. Missing
    linkage is no negative judgment; existing anomaly detection still applies.
    This never selects a kanji spelling for the user's kana text.
    """
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    if native_action_note_introduction(bare):return True
    return bool(bare and 8<=len(bare)<=80 and all('ぁ'<=c<='ゖ' for c in bare)
                and _native_action_note_heads(bare))


def native_action_note_seams(text,tokens):
    """Return source noun/action boundaries, without declaring an anomaly.

    The original native し＋て attachment and unchanged following action
    provide the seam. A caller must separately have the existing whole-kana
    anomaly judgment before generating any repaired reading.
    """
    if not (8<=len(text)<=80 and all('ぁ'<=c<='ゖ' for c in text)):
        return ()
    out=[]
    for first,last in zip(tokens,tokens[1:]):
        cut=first[3]
        if (not 2<=cut<=18 or first[0]!='し' or last[0]!='て'
                or not first[5] or not last[5]
                or not first[1].startswith('動詞')
                or first[6]!='連用形' or not last[1].startswith('助詞:接続助詞')
                or first[4]!=last[3] or text[cut:last[4]]!='して'):
            continue
        from morphology import dictionary_inflections
        if not any(pos.startswith('動詞,') and form=='連用形' and base=='する' and rd=='し'
                   for pos,form,base,rd in dictionary_inflections('し') or ()):
            continue
        right=text[last[4]:]
        if native_bare_action_faces(right) or _native_action_note_heads(right):
            out.append(cut)
    return tuple(out)


# 48-ACI / GPT-6 / 2026-09-13: native number/counter paradigm plus
# conventional counter allomorphs (四時 よじ, 七時 しちじ, 九時 くじ).
# These are grammatical readings, not typo/correction pairs.
@lru_cache(maxsize=1)
def _native_temporal_heads():
    from morphology import dictionary_inflections
    return tuple((rd,phase) for face,phase in (('前','nonpast'),('後','past'))
                 for pos,form,base,rd in dictionary_inflections(face) or ()
                 if pos.startswith('名詞,') and rd in ('まえ','あと','のち'))


@lru_cache(maxsize=4096)
def completed_native_temporal_clause(text):
    """An unchanged Vる前に / Vた後に joins two positively proved clauses."""
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    if not 8<=len(bare)<=80 or not all('ぁ'<=c<='ゖ' or c=='ー' for c in bare):return False
    from morphology import tokenize
    for head,phase in _native_temporal_heads():
        marker=head+'に'
        for cut in range(2,len(bare)-len(marker)-2):
            if not bare.startswith(marker,cut):continue
            left,right=bare[:cut],bare[cut+len(marker):]
            action=(completed_sahen_reading(left,allow_nonpolite=True,return_action=True)
                    or completed_native_verb_reading(left,True,require_roles=False)
                    or completed_native_reading_clause(left,allow_nonpolite=True,
                        require_nominal=True,require_object_fit=True,return_action=True))
            if not action:continue
            parts=tokenize(left);last=parts[-1] if parts else None
            if not last or not last.has_reading:
                # The known noun/case may have forced the whole kana clause
                # into one unknown token. Reuse the same proved predicate,
                # without borrowing the ending of a different suffix word.
                last=None
                for begin in range(1,len(left)-1):
                    suffix=left[begin:]
                    tail_action=(completed_sahen_reading(suffix,allow_nonpolite=True,return_action=True)
                                 or completed_native_verb_reading(suffix,True,require_roles=False))
                    if tail_action!=action:continue
                    tail=tokenize(suffix)
                    if tail and tail[-1].has_reading:
                        parts=tail;last=tail[-1];break
            if not last:continue
            if phase=='nonpast':
                ending=last.pos=='動詞' and last.infl_form=='基本形'
            else:
                ending=last.pos=='助動詞' and last.base_form=='た' and last.infl_form=='基本形'
                if (not ending and last.pos=='助動詞' and last.base_form=='だ'
                        and last.infl_form=='基本形' and len(parts)>1):
                    from contextual_repair import _modern_te_allowed
                    previous=parts[-2]
                    ending=(previous.pos=='動詞' and previous.has_reading
                        and _modern_te_allowed(previous.surface,previous.reading,'だ') is True)
            if not ending:continue
            if (completed_native_reading_clause(right,require_object_fit=True)
                    or completed_native_reading_sequence(right)
                    or completed_native_adjunct_clause(right)
                    or completed_native_temporal_clause(right)):
                return True
    return False


@lru_cache(maxsize=1)
def native_clock_readings():
    from morphology import dictionary_inflections
    from itertools import product
    def exact(word,kind):
        return tuple(rd for pos,form,base,rd in dictionary_inflections(word) or ()
                     if pos.startswith(kind))
    digits=KANJI_DIGITS
    counter=exact('時','名詞,接尾,助数詞,')
    if 'じ' not in counter:return frozenset()
    readings=set()
    for number in range(25):
        words=_native_small_number_words(number)
        pieces=[exact(word,'名詞,数,') for word in words]
        if not all(pieces):continue
        variants={''.join(row) for row in product(*pieces)}
        last=number%10
        if last in (4,7,9):
            prefix=words[:-1]
            prefixes={''.join(row) for row in product(*(exact(word,'名詞,数,') for word in prefix))}
            variants.update(base+{4:'よ',7:'しち',9:'く'}[last] for base in prefixes)
        for number_reading in variants:
            stem=number_reading+'じ'
            readings.add(stem)
            if 'はん' in exact('半','名詞,'):readings.add(stem+'はん')
            if number<=12:
                for period in ('午前','午後'):
                    for rd in exact(period,'名詞,副詞可能,'):
                        readings.add(rd+stem)
                        if 'はん' in exact('半','名詞,'):readings.add(rd+stem+'はん')
    return frozenset(readings)


@lru_cache(maxsize=4096)
def completed_native_adjunct_clause(text):
    """An actual source/time argument preceding an independently proved clause.

    Keep every source character. A genitive/relational noun head supplies its
    semantic role, an exact native time supplies the clock argument, and the
    existing native predicate validator supplies inflection. Unknown pieces
    do not acquire evidence from a corrected candidate.
    """
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    if not bare or not 10<=len(bare)<=80 or not all('ぁ'<=c<='ゖ' or c=='ー' for c in bare):
        return False
    if 'から' not in bare and 'は' not in bare:return False
    from morphology import tokenize,dictionary_inflections
    from semantic_roles import NOUN_ROLES,native_verb_roles,temporal_case_support
    original=tokenize(bare)
    def legacy(parts,offset=0):
        return [(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                 t.start+offset,t.end+offset,t.has_reading,t.infl_form) for t in parts]
    # A source noun (e.g. a search result) can precede another complete
    # object/verb clause. It must be the literal original から boundary.
    for cut in range(2,len(bare)-6):
        if bare[cut:cut+2]!='から':continue
        heads=native_nominal_phrase_faces(bare[:cut])
        if not any(NOUN_ROLES.get(head,set()) & {'information','text'} for head in heads):continue
        if native_nominal_case_boundary(bare,original,cut,'から',heads) is None:continue
        right=bare[cut+2:]
        if not completed_native_reading_clause(right,require_object_fit=True):continue
        # A text-handling content verb already carries an exact native form
        # and reading. An unrelated action does not prove a source relation.
        tail=tokenize(right)
        if any(part.pos=='動詞' and part.has_reading and
               native_verb_roles(part.surface,part.infl_form,part.reading) & {'text','information'}
               for part in tail):return True
    # An event/process topic can begin or end at an explicit clock time.
    for cut in range(2,len(bare)-6):
        if bare[cut]!='は':continue
        heads=native_nominal_phrase_faces(bare[:cut])
        if not any(NOUN_ROLES.get(head,set()) & {'event','process'} for head in heads):continue
        actual_topic=any(t.start==cut and t.end==cut+1 and t.surface=='は'
                         and t.pos=='助詞' and t.pos_sub.startswith('係助詞')
                         and t.has_reading for t in original)
        swallowed=any(not t.has_reading and t.start<=cut<t.end for t in original)
        if not (actual_topic or swallowed):continue
        rest=bare[cut+1:]
        for end in range(2,len(rest)-3):
            clock=rest[:end]
            if clock not in native_clock_readings():continue
            for case in ('から','までに','まで','に'):
                if not rest[end:].startswith(case):continue
                predicate=rest[end+len(case):]
                action=completed_sahen_reading(predicate,allow_nonpolite=True,
                                               subject_faces=heads,return_action=True)
                if action and temporal_case_support(action,case):return True
                # Project only the independently established clock head;
                # the case and the entire original predicate are untouched.
                projected=tokenize('十時'+case+predicate)
                tail=[t for t in projected if t.start>=2]
                if not tail or tail[0].pos!='助詞':continue
                prefix=[]
                for part in tail:
                    if part.pos!='助詞':break
                    prefix.append(part.surface)
                if ''.join(prefix)!=case:continue
                verbs=[t for t in tail[len(prefix):] if t.pos=='動詞']
                if len(verbs)!=1:continue
                verb=verbs[0]
                if not temporal_case_support(verb.surface,case,verb.infl_form,verb.reading):continue
                roles=native_verb_roles(verb.surface,verb.infl_form,verb.reading,subject=True)
                if not any(roles & NOUN_ROLES.get(head,set()) for head in heads):continue
                if _native_nominal_functional_tail(legacy(tail),content_subject_faces=heads):
                    return True
    return False


def native_case_positions(text, parts=None, particles=('を',)):
    """Literal case/focus markers at actual particles or in unknown tokens.

    A known lexical word is not split. This supplies only source positions;
    callers independently prove the count, modifier or following predicate.
    """
    from morphology import tokenize
    original=tokenize(text) if parts is None else parts
    return tuple(position for position in range(len(text))
        if any(text.startswith(marker,position) and any(
            t.start<=position and position+len(marker)<=t.end and (not t.has_reading or
            t.start==position and t.end==position+len(marker) and t.pos=='助詞'
            and t.pos_sub.startswith(('格助詞','係助詞'))) for t in original)
            for marker in particles))


@lru_cache(maxsize=4096)
def _native_argument_predicate_end(text, case, require_clause=False):
    """First unchanged native finite/link predicate after a source case."""
    from morphology import tokenize
    from contextual_repair import _completed_predicate_token
    tail=text[case+1:]
    # An unknown token may swallow the unchanged case and verb.
    # Parse only that exact suffix, never a hypothetical repaired one.
    for last in tokenize(tail):
        if last.end>18:break
        native=(last.surface,last.pos+(':'+last.pos_sub if last.pos_sub else ''),
                last.reading,last.start,last.end,last.has_reading,last.infl_form)
        link=(last.has_reading and last.pos=='助詞' and last.pos_sub=='接続助詞'
              and last.surface in ('て','で'))
        if not link and not _completed_predicate_token(native):continue
        predicate=tail[:last.end]
        nominal_clause=(text[case]!='を' and completed_native_reading_clause(predicate,
            allow_nonpolite=True,require_nominal=True,require_object_fit=True))
        if require_clause and not nominal_clause:continue
        if (nominal_clause
                or completed_native_verb_reading(predicate,allow_nonpolite=True,require_roles=False)
                or completed_sahen_reading(predicate,allow_nonpolite=True)):
            return case+1+last.end
    return None


@lru_cache(maxsize=4096)
def native_genitive_argument_slots(text, particles=('を','に','へ','で','と')):
    """48-AJF/AJO: original N-no-?-case and an independently native action.

    Only the modifier, actual/unknown-token case position and finite/link
    predicate establish the slot. Unknown heads supply no word or anomaly.
    Return (clause start, head start, case start, predicate end).
    """
    if (not text or 'の' not in text or not any(p in text for p in particles) or not 8<=len(text)<=80
            or not all('ぁ'<=c<='ゖ' or c=='ー' for c in text)):return ()
    from morphology import tokenize
    from contextual_repair import _completed_predicate_token
    parts=tokenize(text);out=[]
    begins=(0,)+native_completed_clause_boundaries(text)
    cases=native_case_positions(text,parts,particles)
    # 48-AJV: a native noun such as にほん can contain the unchanged に
    # followed by a separately complete object clause. This only proposes
    # a repair slot; the unknown head supplies neither a word nor an anomaly.
    borrowed={t.start for t in parts if t.has_reading and t.pos=='名詞'
              and not any(kind in t.pos_sub for kind in ('固有名詞','接尾','非自立'))
              and len(t.surface)>1 and t.surface[0] in particles
              and t.surface[0] in 'にへでと'}
    cases=tuple(sorted(set(cases)|borrowed))
    other_cases=native_case_positions(text,parts,('を','に','で','へ','と','が','は','も'))
    genitives={(t.start,t.end) for t in parts if t.has_reading and t.surface=='の' and t.pos=='助詞'
               and t.pos_sub in ('連体化','格助詞:一般')}
    # 48-AKC: an original noun + の can be swallowed by a native irrealis
    # verb (へや + のま...). The unchanged preceding noun, following case
    # and completed predicate still have to prove this repair slot. A known
    # source head is excluded by the caller; no anomaly is invented here.
    for token in parts:
        if (token.has_reading and token.pos=='動詞' and token.infl_form.startswith('未然')
                and token.surface.startswith('の') and len(token.surface)>1):
            genitives.add((token.start,token.start+1))
    genitives=tuple(sorted(genitives))
    for genitive_start,genitive_end in genitives:
        begin=max(edge for edge in begins if edge<=genitive_start)
        if not native_nominal_phrase_faces(text[begin:genitive_start]):continue
        for case in cases:
            if not 2<=case-genitive_end<=12:continue
            if any(genitive_end<=start<case for start,stop in genitives):continue
            # A proved noun on either side of an intervening native case
            # closes a different argument (N-no-meeting-de document-wo).
            # Do not assign that first genitive to the later object. A
            # particle-like fragment inside an unproved typo is no boundary.
            if any(genitive_end<position<case
                   and (native_nominal_phrase_faces(text[genitive_end:position])
                        or native_nominal_phrase_faces(text[position+1:case]))
                   for position in other_cases):continue
            finish=_native_argument_predicate_end(text,case,case in borrowed)
            if finish is not None:out.append((begin,genitive_end,case,finish))
            if out and out[-1][1]==genitive_end:break
    return tuple(dict.fromkeys(out))



@lru_cache(maxsize=4096)
def native_modified_argument_slots(text):
    """48-AKD: source modifiers and the same case/predicate repair boundary.

    The last field carries the relative action and occupied cases, or None
    for an N-no modifier. The head supplies neither a noun nor an anomaly.
    """
    genitives=tuple((*slot,None) for slot in native_genitive_argument_slots(text))
    if not text or not 8<=len(text)<=80:return genitives
    # 48-AKI: original-coordinate frames also reach the common final check
    # for wide legacy edits. A different clause supplies no nominal meaning.
    if '、' in text or ',' in text:
        import re
        return tuple((match.start()+begin,match.start()+head,match.start()+case,
                      match.start()+finish,relative)
            for match in re.finditer('[^、,]+',text)
            for begin,head,case,finish,relative in native_modified_argument_slots(match.group()))
    if not all('ぁ'<=c<='ゖ' or c=='ー' for c in text):return genitives
    from morphology import tokenize
    parts=tokenize(text)
    cases=native_case_positions(text,parts,('を','に','へ','で','と'))
    other_cases=native_case_positions(text,parts,('を','に','で','へ','と','が','は','も'))
    # The same native adverb boundary already used by ordinary object
    # contexts can precede a relative clause without changing either text.
    begins=tuple(sorted({0,*native_completed_clause_boundaries(text),
                         *native_adverbial_reading_cuts(text)}))
    out=list(genitives)
    for case in cases:
        finish=_native_argument_predicate_end(text,case)
        if finish is None:continue
        for begin in begins:
            if begin+4>case:continue
            for head in range(max(begin+2,case-12),case-1):
                relative=native_relative_action(text[begin:head])
                if not relative:continue
                if any(head<position<case
                       and (native_nominal_phrase_faces(text[head:position])
                            or native_nominal_phrase_faces(text[position+1:case]))
                       for position in other_cases):continue
                out.append((begin,head,case,finish,relative))
    return tuple(dict.fromkeys(out))



@lru_cache(maxsize=4096)
def native_modified_nominal_contexts(text):
    """48-AKD: unchanged nominal heads fitting both sides of a modifier.

    A written noun retains its own meaning. Its attested reading supplies
    coordinates for the same kana grammar, never a different homophone.
    Return (begin, nominal start, case start, first predicate end, faces).
    """
    if not text or not 8<=len(text)<=80:return ()
    kana=lambda value:all('ぁ'<=c<='ゖ' or c=='ー' for c in value)
    from morphology import tokenize
    from semantic_roles import relative_action_support
    variants=[(text,None)] if kana(text) else []
    if not variants:
        for part in tokenize(text):
            if (part.has_reading and part.pos=='名詞' and not kana(part.surface)
                    and kana(text[:part.start]+text[part.end:])):
                faces=_native_written_nominal_faces(part.surface)
                if faces:
                    variants.append((text[:part.start]+part.reading+text[part.end:],
                        (part.start,part.end,len(part.reading),faces)))
    out=[]
    for reading,projection in variants:
        for begin,head,case,finish,relative in native_modified_argument_slots(reading):
            if projection:
                start,stop,size,faces=projection
                if head!=start or case!=start+size:continue
                finish-=size-(stop-start);case=stop
            else:
                faces=native_nominal_phrase_faces(text[head:case])
            if not faces:continue
            if relative and not any(relative_action_support(face,*relative) for face in faces):
                continue
            if native_object_predicate_proof(text[begin:finish],case-begin+1,faces,allow_link=True):
                out.append((begin,head,case,finish,tuple(faces)))
    return tuple(dict.fromkeys(out))


def native_genitive_object_slots(text):
    """The accusative subset of the same original genitive/case evidence."""
    return native_genitive_argument_slots(text,('を',))


@lru_cache(maxsize=4096)
def native_object_predicate_frames(text):
    """Unchanged native object/case evidence shared by source and repair."""
    if not text or not 6<=len(text)<=80:
        return ()
    if 'を' not in text:
        return ()
    from morphology import tokenize
    original=tokenize(text)
    cuts=[]
    for cut in range(1,len(text)-3):
        if (text[cut]!='を' or not 3<=len(text)-cut-1<=18
                or not all('ぁ'<=c<='ゖ' or c=='ー' for c in text[cut+1:])):
            continue
        # This target proves a single object/predicate, not a later clause
        # or an additional argument. Actual native noun/case tokens establish
        # that boundary; accidental に inside an unknown reading does not.
        tail=[part for part in original if part.start>cut]
        # A native conditional auxiliary starts a following clause even
        # when its kana noun (えき) is missegmented as filler/auxiliaries.
        # This routine proves one predicate and must not consume that clause.
        if any(part.has_reading and part.pos=='助動詞' and part.infl_form=='仮定形'
               and part.end<len(text) for part in tail):
            continue
        # A second native argument may follow Vてから, or use a
        # comitative と which the original parse labels as a parallel case.
        # Its unchanged nominal reading supplies the boundary even when
        # the kana is assigned another POS in the malformed whole sentence.
        subsequent=False
        for i,link in enumerate(tail):
            if link.pos!='助詞' or not link.pos_sub.startswith('接続助詞') or not link.has_reading:
                continue
            edges=[link.end]
            # A full parse may swallow から + the next noun into a verb.
            # Unedited て/で + から and a native noun/case are sufficient
            # to exclude a single-predicate range, not to certify normality.
            if link.surface in ('て','で') and text.startswith('から',link.end):
                edges.append(link.end+2)
            for edge in edges:
                # An independently attested bare predicate can contain kana
                # which the full parse labels as a case (e.g. 保存 -> ほぞ/ん).
                # Such a split cannot establish a second nominal argument.
                rest=text[edge:]
                if (completed_sahen_reading(rest,allow_nonpolite=True)
                        or completed_native_verb_reading(rest,True,require_roles=False)):
                    continue
                for particle in tail[i+1:]:
                    if (particle.start>edge and particle.has_reading and particle.pos=='助詞'
                            and (particle.pos_sub.startswith('格助詞') or
                                 particle.surface=='と' and particle.pos_sub.startswith('並立助詞'))
                            and (native_nominal_phrase_faces(text[edge:particle.start])
                                 or any(noun.start==edge and noun.end==particle.start
                                        and noun.has_reading and noun.pos=='名詞' for noun in tail))):
                        subsequent=True;break
                if subsequent:break
            if subsequent:break
        if subsequent:continue
        faces=native_nominal_phrase_faces(text[:cut])
        if not faces:
            # The same unchanged adjective/relative-clause proof used for
            # source intactness also supplies the object head for repair.
            # A malformed modifier cannot borrow its corrected noun's fit.
            nominal=native_adnominal_reading_parts(text[:cut],allow_predicative=True)
            if nominal:faces=(nominal[-1][0],)
        if not faces and any(not ('ぁ'<=c<='ゖ' or c=='ー') for c in text[:cut]):
            # A single actual common noun retains its written meaning. The
            # candidate proof must not borrow a different homophone's roles.
            noun=next((t for t in original if t.start==0 and t.end==cut),None)
            if (noun and noun.has_reading and noun.pos=='名詞'
                    and not any(kind in noun.pos_sub for kind in ('固有名詞','接尾','非自立'))):
                faces=(noun.surface,)
        if faces and native_nominal_case_boundary(text,original,cut,'を',faces) is not None:
            cuts.append((cut+1,faces))
    return tuple(cuts)


@lru_cache(maxsize=4096)
def native_completed_clause_boundaries(text):
    """Actual source particles terminating an independently proved clause.

    Native particle boundaries prevent a から inside the adjective からい
    from being treated as the temporal link. Kana outside the prefix may
    remain malformed and is not declared normal by this evidence. A bare
    action head alone cannot freeze a semantically anomalous action sequence;
    this source protection requires its own native noun/case argument.
    """
    if not text or not 5<=len(text)<=80:return ()
    from morphology import tokenize
    boundaries=[]
    for t in tokenize(text):
        if not (t.has_reading and t.pos=='助詞' and t.surface in ('て','で','から','ので')):continue
        left,right=text[:t.end],text[t.end:]
        if completed_native_reading_link(left,require_nominal=True):
            boundaries.append(t.end)
        elif (native_object_predicate_frames(right)
                and (completed_native_reading_link(left)
                     or left.endswith(('て','で'))
                     and completed_native_verb_reading(left,True,require_roles=False))):
            # A short clause may omit its object while the next clause
            # has its own attested noun/case. Keep that native first
            # predicate; an unexplained bare tail alone supplies no seam.
            boundaries.append(t.end)
    return tuple(boundaries)



@lru_cache(maxsize=4096)
def _native_adverbial_faces(reading):
    from corrector import table_surfaces_for_reading
    from morphology import dictionary_inflections
    from semantic_roles import adverbial_reading_needs_host
    return tuple(face for face in dict.fromkeys((reading,*table_surfaces_for_reading(reading,limit=8)))
                 if not adverbial_reading_needs_host(face,reading)
                 and any(rd==reading and pos.startswith(('副詞,','名詞,副詞可能,'))
                         for pos,form,base,rd in dictionary_inflections(face) or ()))


def _native_counter_prefixes(text, original):
    # A whole unchanged lexical word owns its prefix. The native counter
    # table can otherwise recover a numeral split as particles or verbs.
    return tuple(cut for cut in range(2,min(17,len(text)+1))
        if text[:cut] in native_counter_readings()
        and not any(t.start==0 and t.has_reading and cut<t.end
            and t.pos in ('名詞','動詞','形容詞','副詞') for t in original))


@lru_cache(maxsize=4096)
def native_nominal_temporal_prefix(text):
    """48-AIU: an unchanged native N-no-mae/ato-ni supplies an adjunct edge.

    Reuse the temporal heads and an exact native nominal reading. The
    projected spelling only proves the original の + noun + に grammar;
    it neither changes the kana text nor certifies the following clause.
    """
    if not text.endswith('に') or not 5<=len(text)<=24:return False
    from morphology import tokenize,dictionary_inflections
    for reading,phase in _native_temporal_heads():
        marker='の'+reading+'に'
        if not text.endswith(marker):continue
        noun=text[:-len(marker)]
        if not noun:continue
        head='前' if phase=='nonpast' else '後'
        for face in native_nominal_phrase_faces(noun):
            parts=tokenize(face+'の'+head+'に')
            expected=((len(face),'の','助詞','連体化'),
                      (len(face)+1,head,'名詞',None),
                      (len(face)+2,'に','助詞','格助詞'))
            if not all(any(t.start==start and t.end==start+len(surface)
                    and t.surface==surface and t.pos==pos and t.has_reading
                    and (sub is None or t.pos_sub.startswith(sub))
                    for t in parts) for start,surface,pos,sub in expected):continue
            # The best written parse may choose のち, while あと is also
            # the same native nominal head's exact attested reading.
            if any(pos.startswith('名詞,') and rd==reading
                   for pos,form,base,rd in dictionary_inflections(head) or ()):
                return True
    return False


@lru_cache(maxsize=4096)
def native_adjective_adverbial_prefix(text,cut):
    """The full continuative belongs to the same actual adjective lemma.

    A following intrusion can split 薄く as the same adjective's 薄 stem
    plus another token. It does not justify borrowing an unrelated lemma.
    """
    # 48-AJD: IPADIC also labels くっ as 連用テ接続. That
    # contracted allomorph needs following て; it is not a free manner
    # modifier before another lexical verb. Exact native -く is required.
    if not 1<cut<len(text) or not text[:cut].endswith('く'):return False
    from morphology import tokenize,dictionary_inflections
    parts=tokenize(text)
    if not parts:return False
    first=parts[0]
    if not (first.start==0 and first.end<=cut and first.has_reading
            and first.pos=='形容詞'):return False
    return any(pos.startswith('形容詞,') and form=='連用テ接続'
               and base==first.base_form and rd==text[:cut]
               for pos,form,base,rd in dictionary_inflections(text[:cut]) or ())


@lru_cache(maxsize=4096)
def native_adverbial_reading_cuts(text):
    """Unedited native adverbs, shared by source proof and argument ranges.

    The cut neither proves the following clause nor its anomaly. A known
    lexical word spanning the cut is not divided into an adverb and a noun.
    """
    if not text or not 5<=len(text)<=80 or not all('ぁ'<=c<='ゖ' or c=='ー' for c in text):return ()
    from corrector import table_surfaces_for_reading
    from morphology import dictionary_inflections,tokenize
    original=tokenize(text);cuts=[];blocked_adverb=False
    counter_cuts=_native_counter_prefixes(text,original)
    # A written bound particle/auxiliary cannot become a free adverb
    # through a homophonic kanji entry (ほど / 程 before 貸します).
    # Unknown segmentation still has the existing dictionary fallback.
    if original and original[0].start==0 and original[0].has_reading:
        first=original[0]
        if (first.surface not in native_counter_readings()
                and (first.pos in ('助詞','助動詞') or first.pos in ('動詞','形容詞')
                     and not first.infl_form.startswith('連用'))):
            blocked_adverb=True
    for cut in range(2,min(17,len(text)-2)):
        if any(t.start==0 and t.has_reading and cut<t.end
               and t.pos in ('名詞','動詞','形容詞','副詞') for t in original):continue
        reading=text[:cut]
        # An attested native counter may quantify an independently proved
        # object/predicate, using the same unchanged adverbial projection.
        # 48-AHD: the whole unchanged numeral/counter can be split as
        # a particle or a finite verb by the best parse (e.g. ni + satsu).
        # It has its own native counting proof. Keep the original ban for
        # other adverbs; a counter cut does not certify the following verb.
        # JPF, Bunpoo setsumei, pp.46-47: N + case + numeral/counter.
        if cut in counter_cuts:
            cuts.append(cut);continue
        if native_nominal_temporal_prefix(reading):
            cuts.append(cut);continue
        faces=_native_adverbial_faces(reading)
        # 48-AHO: a complete native lexical adverb can span the wrongly
        # isolated functional prefix (ねん + ... -> 年末). A lone bound
        # particle such as ほど still cannot borrow an adverb homograph.
        adjective=native_adjective_adverbial_prefix(text,cut)
        if blocked_adverb and not (faces and cut>original[0].end or adjective):continue
        # 48-AIW: native i-adjective continuatives also modify verbs
        # (薄く切る / 長く伸ばす). This edge proves neither the following
        # verb nor its object: callers still require the complete native
        # predicate and the unchanged case's positive semantic relation.
        if adjective:
            cuts.append(cut);continue
        if faces:
            cuts.append(cut);continue
        # An actual topic/focus particle can qualify the unchanged native
        # adverbial noun (今は / 以前も). It supplies no following action.
        particle=next((t for t in original if t.end==cut and t.has_reading
                       and t.pos=='助詞'),None)
        if particle is None or particle.start<2:continue
        heads=_native_adverbial_faces(reading[:particle.start])
        if not heads:continue
        if particle.surface in ('は','も') and particle.pos_sub=='係助詞':
            cuts.append(cut);continue
        # Some complete adverbs are spelled as a noun and particle in
        # kana (後で). Require the whole native adverb dictionary entry.
        if any(pos.startswith('副詞,') and rd==reading for face in heads
               for pos,form,base,rd in dictionary_inflections(face+particle.surface) or ()):
            cuts.append(cut)
    return tuple(cuts)


@lru_cache(maxsize=4096)
def native_object_predicate_contexts(text):
    """Return (clause start, predicate start, faces) in the original text.

    Later boundaries require an independently completed preceding clause.
    Source intactness continues to prove the entire input separately.
    """
    result=[(0,cut,faces) for cut,faces in native_object_predicate_frames(text)]
    if not text or 'を' not in text or not 6<=len(text)<=80 or not all('ぁ'<=c<='ゖ' or c=='ー' for c in text):
        return tuple(result)
    edges=set(native_completed_clause_boundaries(text)) | set(native_adverbial_reading_cuts(text))
    for edge in sorted(edges):
        # An already attested whole object reading owns its noun boundary.
        # Do not split that same noun into an adverb and a second object
        # merely because the malformed tail changed native segmentation.
        if any(begin<edge<cut for begin,cut,faces in result):continue
        frames=native_object_predicate_frames(text[edge:])
        result.extend((edge,edge+cut,faces) for cut,faces in frames)
    return tuple(result)


@lru_cache(maxsize=4096)
def native_adverbial_predicate_reading(text, allow_open_tail=True):
    """Source evidence: a complete native adverb reading plus an actual verb.

    Dictionary POS and exact readings attest the whole adverb, including
    nominal adverbs. A frequency entry alone cannot certify this boundary.
    The following verb retains its native inflection and completed tail.
    """
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    if not bare or not 5<=len(bare)<=40 or not all('ぁ'<=c<='ゖ' or c=='ー' for c in bare):
        return False
    for cut in native_adverbial_reading_cuts(bare):
        predicate=bare[cut:]
        # 48-AJB: adjective manner + a directly attested action is
        # positive evidence. A separate nominal clause (e.g. N-ga-aru)
        # does not establish the adjective's relation to that action.
        # Unclassified original modifiers are not thereby anomalous.
        if (completed_sahen_reading(predicate,allow_nonpolite=True,allow_open_tail=allow_open_tail)
                or completed_native_verb_reading(predicate,allow_nonpolite=True,require_roles=False)
                or (not native_adjective_adverbial_prefix(bare,cut) and (
                    completed_native_nominal_predicate(predicate)
                    or completed_native_reading_clause(predicate,require_nominal=True,
                        require_object_fit=True,allow_open_tail=allow_open_tail)))):
            return True
    return False


def preserves_native_word_onset(line,start,end,surface):
    """A native adverb or completed predicate keeps its original word onset.

    Source-only evidence for size changes: an anomaly elsewhere in the run
    does not make ゆっくり join the preceding し as a new contracted sound.
    Ordinary lexical repair is outside this small/large-kana contract.
    """
    if len(surface)!=end-start:return True
    positions={start+i for i,(old,new) in enumerate(zip(line[start:end],surface))
               if old in 'やゆよ' and ord(new)==ord(old)-1}
    if not positions:return True
    from morphology import tokenize
    for token in tokenize(line):
        if (token.start in positions and token.has_reading and token.pos in ('副詞','動詞')
                and len(token.surface)>1 and token.surface==token.reading):
            tail=line[token.start:]
            for mark in ('。','！','？','!','?','、',',','\n'):
                tail=tail.split(mark,1)[0]
            if (native_adverbial_predicate_reading(tail) if token.pos=='副詞'
                    else completed_native_verb_reading(tail,allow_nonpolite=True,require_roles=False)):
                return False
    return True


def native_nominal_topic_prefix(text):
    """48-AGK: exact ordinary kana noun + native に/は, still in source spelling.

    This proves only a nominal topic boundary; a following predicate remains
    available for its own analysis. It does not certify an arbitrary tail.
    """
    cut=text.find('には')
    if cut<=0:return 0
    faces=native_nominal_phrase_faces(text[:cut])
    if not faces:return 0
    from morphology import dictionary_inflections,tokenize
    if not any(pos.startswith('助詞,係助詞,') and rd=='は'
               for pos,form,base,rd in dictionary_inflections('は') or ()):
        return 0
    if native_nominal_case_boundary(text,tokenize(text),cut,'に',faces) is None:
        return 0
    return cut+2


@lru_cache(maxsize=4096)
def native_degree_expression(text):
    """Source-only degree expression with a verified head and native excess.

    This retains adjective stems and their written nominalizing sa even
    when Janome selects an unrelated verb's irrealis homograph. Unknown
    heads, case-bearing clauses and incomplete excess tails add no proof.
    """
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    if not bare or not 4<=len(bare)<=32:return False
    from morphology import tokenize,dictionary_inflections,native_excess_head
    from contextual_repair import _productive_predicate,_allows_grammatical_tail,_completed_predicate_token
    # 48-AGT: the best parse can swallow the actual excess boundary
    # into an unknown kana token. Exact native negative grammar can prove
    # that unchanged boundary independently of the selected tokenization.
    from contextual_repair import _native_negative_degree_predicate
    for cut in range(1,len(bare)):
        if bare.startswith(('なすぎ','なさすぎ','な過ぎ','なさ過ぎ'),cut):
            if _native_negative_degree_predicate(bare,bare[:cut]):return True
    for part in tokenize(bare):
        if not (part.start>0 and part.has_reading and part.pos=='動詞'
                and part.base_form in ('すぎる','過ぎる')):continue
        head=bare[:part.start]
        from contextual_repair import _native_negative_degree_predicate
        if any(head.endswith(ending) and _native_negative_degree_predicate(bare,head[:-len(ending)])
               for ending in ('なさ','な')):return True
        readings={rd for p,f,b,rd in dictionary_inflections(head) or ()}
        if all('ぁ'<=ch<='ゖ' for ch in head):readings.add(head)
        if not any(native_excess_head(head,rd) is True for rd in readings):continue
        tail=bare[part.start:];parts=tokenize(tail)
        if not parts or parts[0].surface!=part.surface or not all(t.has_reading for t in parts):continue
        last=parts[-1]
        if not _completed_predicate_token((last.surface,last.pos+':'+last.pos_sub,
                last.reading,last.start,last.end,last.has_reading,last.infl_form)):continue
        forms=tuple(row for row in dictionary_inflections(part.surface) or ()
            if row[0].startswith('動詞,') and row[1]==part.infl_form and row[3]==part.reading
            and row[2] in ('すぎる','過ぎる'))
        if (_allows_grammatical_tail(forms,tail[len(part.surface):],part.reading,part.surface)
                and _productive_predicate(tail,part.surface)):return True
    return False


@lru_cache(maxsize=4096)
def native_literal_argument_chain(prefix):
    """A unique independent-noun/case chain when kana segmentation loses a case.

    Return source spellings and positions, not alternate kanji meanings.
    Every whole noun has independent native evidence. At least one kana noun
    is required; ordinary written-noun parsing keeps its existing contract.
    """
    if not prefix or len(prefix)>80 or prefix[-1] not in 'をにでへと':return ()
    import re
    boundary=max((m.end() for m in re.finditer(r'[。！？.!?、,;；\t\r\n「」『』“”"（）()]',prefix)),default=0)
    text=prefix[boundary:]
    if not text or any(c.isspace() for c in text):return ()
    solutions=[]
    def visit(start,chain,kana):
        if len(solutions)>1:return
        if start==len(text):
            if kana:solutions.append(tuple(chain))
            return
        if len(chain)>=3:return
        for cut in range(start+1,min(len(text),start+25)):
            if text[cut] not in 'をにでへと':continue
            noun=text[start:cut]
            is_kana=all('ぁ'<=c<='ゖ' or c=='ー' for c in noun)
            # Semantic callers need the actual nominal head. A modifier
            # phrase's grammar does not make that whole phrase one noun.
            faces=_native_nominal_reading_faces(noun) if is_kana else _native_written_nominal_faces(noun)
            if not faces or not is_kana and noun not in faces:continue
            visit(cut+1,chain+[(noun,text[cut],boundary+start,boundary+cut+1)],kana or is_kana)
    visit(0,[],False)
    return solutions[0] if len(solutions)==1 else ()


@lru_cache(maxsize=4096)
def _native_written_nominal_faces(text):
    """An actual native nominal head, with its original simple modifier."""
    from morphology import tokenize,dictionary_inflections
    def nominal(surface):
        return any(p.startswith(('名詞,一般,','名詞,サ変接続,','名詞,代名詞,','名詞,副詞可能,'))
                   and base==surface for p,form,base,rd in dictionary_inflections(surface) or ())
    if nominal(text):return (text,)
    parts=tokenize(text)
    if (len(parts)==2 and parts[0].start==0 and parts[0].end==parts[1].start
            and parts[1].end==len(text) and all(t.has_reading for t in parts)
            and parts[0].pos in ('連体詞','接頭詞') and nominal(parts[1].surface)):
        return (parts[1].surface,)
    return ()


@lru_cache(maxsize=4096)
def native_degree_subject_clause(text):
    """A native noun subject and an unchanged degree predicate.

    Adjectival stems and native negative irrealis chains retain their source
    form. An arbitrary affirmative transitive verb gets no subject proof.
    """
    if not text or not 5<=len(text)<=80 or not any(x in text for x in 'がはも') or ('すぎ' not in text and '過ぎ' not in text):return False
    bare=text[:-1] if text[-1:] in '。！？.!?' else text
    from morphology import tokenize,dictionary_inflections
    for case in tokenize(bare):
        if not (case.has_reading and case.surface in ('が','は','も') and case.pos=='助詞'
                and case.pos_sub.startswith(('格助詞','係助詞')) and case.start>0):continue
        noun=bare[:case.start];predicate=bare[case.end:]
        if not (_native_written_nominal_faces(noun)
                or all('ぁ'<=c<='ゖ' for c in noun) and native_nominal_phrase_faces(noun)):continue
        if not native_degree_expression(predicate):continue
        from contextual_repair import _native_negative_degree_predicate
        for excess in tokenize(predicate):
            if excess.pos!='動詞' or excess.base_form not in ('すぎる','過ぎる') or not excess.start:continue
            stem=predicate[:excess.start]
            if any(stem.endswith(ending) and _native_negative_degree_predicate(predicate,stem[:-len(ending)])
                   for ending in ('なさ','な')):return True
            heads=(stem,stem[:-1]) if stem.endswith('さ') else (stem,)
            if any((p.startswith('形容詞,') and form=='ガル接続')
                   or p.startswith('名詞,形容動詞語幹,')
                   for head in heads for p,form,base,rd in dictionary_inflections(head) or ()):
                return True
    return False


@lru_cache(maxsize=4096)
def completed_written_object_clause(text):
    """An exact native written object and its original complete predicate.

    A kanji reading alone cannot switch the written object's meaning. Reuse
    the original-object proof already required of generated candidates.
    """
    if not text or not 5<=len(text)<=80 or 'を' not in text:return False
    bare=text[:-1] if text[-1:] in '。！？.!?' else text
    from morphology import tokenize
    boundaries=list(native_object_predicate_frames(bare))
    for part in tokenize(bare):
        if (part.surface=='を' and part.has_reading and part.pos=='助詞'
                and part.pos_sub.startswith('格助詞') and 0<part.start<part.end<len(bare)):
            faces=_native_written_nominal_faces(bare[:part.start])
            if faces:boundaries.append((part.end,faces))
    for cut,faces in boundaries:
        if (native_degree_expression(bare[cut:])
                and native_object_predicate_proof(bare,cut,faces)):return True
    return False


def _native_source_clauses(text):
    """Unchanged source slices; punctuation and explicit columns stay outside."""
    import re
    for match in re.finditer(r'[^。！？.!?、,;；\t\r\n「」『』“”"（）()]+',text):
        raw=match.group();clause=raw.strip()
        if clause:
            yield match.start()+len(raw)-len(raw.lstrip()),clause


@lru_cache(maxsize=2048)
def native_degree_context_ranges(text):
    """Source ranges with the same completed degree proof, across punctuation.

    A completed connective keeps its own finite prefix. Only the proved
    clause is retained; another sentence or an arbitrary quoted string is
    not certified by it. Coordinates stay in the original source.
    """
    if 'すぎ' not in text and '過ぎ' not in text:return ()
    import re
    from morphology import dictionary_inflections
    out=[]
    for start,clause in _native_source_clauses(text):
        variants=[clause]
        if (clause.endswith('が') and any(p.startswith('助詞,接続助詞,') and rd=='が'
                for p,f,b,rd in dictionary_inflections('が') or ())):variants.append(clause[:-1])
        for body in variants:
            if (native_degree_subject_clause(body) or completed_written_object_clause(body)
                    or native_degree_expression(body)):
                out.append((start,start+len(body)));break
    return tuple(out)


@lru_cache(maxsize=4096)
def native_prolonged_clause(text):
    """48-AHG: same-vowel small kana can spell an unchanged spoken clause.

    Reuse the existing vowel map. The compact form is evidence only:
    require a complete native verb or a whole clause with positive case
    fit. A small kana with another vowel, an unknown word or unfinished
    predicate supplies no evidence. No compact spelling is emitted.
    """
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    if (not bare or not 3<=len(bare)<=80 or not any(c in 'ぁぃぅぇぉ' for c in bare)
            or not all('ぁ'<=c<='ゖ' for c in bare)):
        return False
    from corrector import _VOWEL_OF
    compact=[]
    for char in bare:
        if (char in 'ぁぃぅぇぉ' and compact
                and _VOWEL_OF.get(compact[-1])==chr(ord(char)+1)):
            continue
        compact.append(char)
    ordinary=''.join(compact)
    if ordinary==bare:return False
    return bool(completed_native_verb_reading(ordinary,allow_nonpolite=True,require_roles=False)
        or completed_sahen_reading(ordinary,allow_nonpolite=True)
        or completed_native_reading_clause(ordinary,require_nominal=True,require_object_fit=True)
        or completed_native_reading_sequence(ordinary))


@lru_cache(maxsize=4096)
def completed_native_source_sequence(text):
    """48-AIA: retain a complete source sequence inside its actual clause.

    Native adverb boundaries and a retained finite connective may surround
    the same proved sequence. No arbitrary substring or changed spelling
    supplies proof, and a following unproved clause remains outside it.
    """
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    if (not 8<=len(bare)<=80 or not all('ぁ'<=c<='ゖ' or c=='ー' for c in bare)
            or not any(link in bare for link in ('て','で','から','が'))):return False
    from contextual_repair import _unchanged_finite_connective
    connector=_unchanged_finite_connective(bare,bare)
    variants=(bare,bare[:-len(connector)]) if connector else (bare,)
    for clause in variants:
        if completed_native_reading_sequence(clause,allow_unclassified=True):return True
        for cut in native_adverbial_reading_cuts(clause):
            if completed_native_reading_sequence(clause[cut:],allow_unclassified=True):return True
    return False


@lru_cache(maxsize=2048)
def native_predicate_modifier_ranges(text):
    """48-AIZ: retain an actual i-adjective after a proved source object.

    An unexplained verb does not make the preceding complete manner form
    anomalous. Exact native inflection, the original nominal/case edge and
    actual adjective token are required; no repaired reading supplies them.
    This does not claim that an unclassified adjective elsewhere is wrong.
    """
    if 'を' not in text:return ()
    from morphology import tokenize,dictionary_inflections
    out=[]
    for start,clause in _native_source_clauses(text):
        if not all('ぁ'<=c<='ゖ' or c=='ー' for c in clause):continue
        for begin,end,faces in native_object_predicate_contexts(clause):
            source=clause[begin:]
            boundary=native_nominal_case_boundary(source,tokenize(source),end-begin-1,'を',faces)
            if boundary is None or boundary[1]:continue
            remainder=clause[end:]
            for cut in native_adverbial_reading_cuts(remainder):
                if native_adjective_adverbial_prefix(remainder,cut):
                    out.append((start+end,start+end+cut))
    return tuple(sorted(set(out)))


def preserves_native_predicate_modifier(original,changed):
    spans=native_predicate_modifier_ranges(original)
    if not spans:return True
    from difflib import SequenceMatcher
    blocks=SequenceMatcher(None,original,changed,autojunk=False).get_matching_blocks()
    return all(any(block.a<=start and end<=block.a+block.size for block in blocks)
               for start,end in spans)


@lru_cache(maxsize=2048)
def native_context_ranges(text):
    """48-AHB: retain proved source grammar, even beside a malformed tail.

    Completed sequences, degree clauses and original noun/case frames feed
    the same entry and anomaly checks. A noun/counter proof stops at its own end: it does not
    certify the predicate, erase unrelated marks, or use a repaired reading.
    """
    out=list(native_degree_context_ranges(text))
    out.extend(native_predicate_modifier_ranges(text))
    from semantic_roles import unadorned_nominal_prefix_ranges
    out.extend(unadorned_nominal_prefix_ranges(text))
    if not any(c in text for c in 'をてでがぁぃぅぇぉ') and 'から' not in text:
        return tuple(out)
    from morphology import tokenize
    for start,clause in _native_source_clauses(text):
        if any(not ('ぁ'<=c<='ゖ' or c=='ー') for c in clause):
            out.extend((start+begin,start+finish)
                for begin,head,case,finish,faces in native_modified_nominal_contexts(clause))
        if completed_native_source_sequence(clause):
            out.append((start,start+len(clause)))
        if native_prolonged_clause(clause):
            out.append((start,start+len(clause)))
        if 'を' not in clause:continue
        if not 6<=len(clause)<=80 or not all('ぁ'<=c<='ゖ' or c=='ー' for c in clause):
            continue
        for begin,end,faces in native_object_predicate_contexts(clause):
            source=clause[begin:]
            boundary=native_nominal_case_boundary(source,tokenize(source),end-begin-1,'を',faces)
            # Reopening a known word/connector with a competing case still
            # requires predicate fit elsewhere; a bare nominal is not enough.
            if boundary is not None and not boundary[1]:
                out.append((start+begin,start+end))
                # 48-AHD: the untouched quantity belongs to this original
                # object frame. Stop at its last character, before any
                # unknown/unfinished predicate; do not borrow a correction.
                remainder=clause[end:]
                for cut in _native_counter_prefixes(remainder,tokenize(remainder)):
                    out.append((start+begin,start+end+cut))
    return tuple(sorted(set(out)))


@lru_cache(maxsize=4096)
def intact_native_reading(text):
    """Known source grammar, including a native open or sequential tail.

    This protects the input and suppresses a false anomaly. Generated
    single-predicate candidates still need completed_native_reading_clause.
    """
    if (native_degree_subject_clause(text) or completed_written_object_clause(text)
            or completed_native_reading(text)
            or completed_native_source_sequence(text)
            or native_adverbial_predicate_reading(text)
            or native_degree_expression(text)
            or native_prolonged_clause(text)
            or completed_native_reading_clause(text,require_nominal=True,
                require_object_fit=True,allow_open_tail=True)):
        return True
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    if any(begin==0 and finish==len(bare)
           for begin,head,case,finish,faces in native_modified_nominal_contexts(bare)):
        return True
    # 48-AGP: a terminal small vowel may spell the voice of a complete
    # native clause. Only its last glyph is read in ordinary size for this
    # source proof; the original spelling is retained, never proposed as an
    # edited candidate. An unexplained stem or invalid case still fails.
    if bare and bare[-1] in 'ぁぃぅぇぉ' and all('ぁ'<=c<='ゖ' for c in bare):
        ordinary=bare[:-1]+dict(zip('ぁぃぅぇぉ','あいうえお'))[bare[-1]]
        if completed_native_reading(ordinary):return True
    topic=native_nominal_topic_prefix(bare)
    if topic:
        tail=bare[topic:].lstrip('、, ')
        if not tail or completed_native_reading(tail):return True
    if bare and all('ぁ'<=c<='ゖ' or c=='ー' for c in bare):
        # Source-only: an attested bare verb can omit its object. The
        # next clause must have its own original noun/case and complete
        # predicate; an unclassified first verb is not itself an anomaly.
        for edge in native_completed_clause_boundaries(bare):
            if completed_native_reading(bare[edge:]):return True
        from contextual_repair import _unchanged_finite_connective
        retained=_unchanged_finite_connective(bare,bare)
        if retained and completed_native_reading(bare[:-len(retained)]):return True
    return (completed_sahen_reading(bare,allow_nonpolite=True,allow_open_tail=True)
            or any(completed_sahen_reading(bare[cut:],allow_nonpolite=True,object_faces=faces,allow_open_tail=True)
                   for cut,faces in native_object_predicate_frames(bare)))



def _written_predicate_reading_preserved(parts,predicate_start,reading):
    """A written content verb cannot borrow a homophone's auxiliary role.

    GPT-6 / 2026-09-14. This constrains positive candidate proof only. Native
    auxiliary variants remain available when this exact spelling/form/reading
    has the projected grammatical role in the same native dictionary.
    """
    from morphology import tokenize,dictionary_inflections
    projected=None;offset=0
    for part in parts:
        kana=all('ぁ'<=c<='ゖ' or c=='ー' for c in part.surface)
        rd=part.surface if kana else part.reading
        start,end=offset,offset+len(rd);offset=end
        if kana or part.start<predicate_start or part.pos!='動詞':continue
        if projected is None:projected=tokenize(reading)
        matches=[t for t in projected if start<=t.start and t.end<=end]
        if (not matches or matches[0].start!=start or matches[-1].end!=end
                or not all(t.has_reading for t in matches)):continue
        functional=lambda t:t.pos in ('助詞','助動詞') or (
            t.pos=='動詞' and t.pos_sub.startswith(('非自立','接尾')))
        if not all(functional(t) for t in matches):continue
        if not any(pos.startswith(('動詞,非自立,','動詞,接尾,'))
                   and form==part.infl_form and native_reading==rd
                   for pos,form,base,native_reading in dictionary_inflections(part.surface) or ()):
            return False
    return True


@lru_cache(maxsize=4096)
def native_object_predicate_proof(text, predicate_start, faces, allow_link=False):
    """Shared nominal/case proof, retaining a written argument's own meaning.

    Kana remain literal even when unknown. A kanji spelling must have an
    actual native reading, and cannot borrow another homophone's object role.
    This positive proof neither invents an anomaly nor chooses a spelling.
    """
    if not 1<predicate_start<len(text):return False
    from morphology import tokenize,dictionary_inflections
    # 48-AGT: source-only alternative segmentation of native negative
    # degree predicates, bound to the original object's exact meanings.
    # A one-kana irrealis such as し needs no standalone word registration.
    predicate=text[predicate_start:]
    if predicate[-1:] in '。！？.!?':predicate=predicate[:-1]
    from contextual_repair import _native_negative_degree_predicate
    from semantic_roles import native_verb_roles,nominal_roles
    for cut in range(1,len(predicate)) if text[predicate_start-1]=='を' else ():
        if not predicate.startswith(('なすぎ','なさすぎ','な過ぎ','なさ過ぎ'),cut):continue
        head=predicate[:cut];tail=predicate[cut:]
        if not _native_negative_degree_predicate(predicate,head):continue
        forms=tuple(row for row in dictionary_inflections(head) or ()
                    if row[0].startswith('動詞,自立,') and row[1]=='未然形')
        for pos,form,base,rd in forms:
            roles=native_verb_roles(head,form,rd,tail=tail)
            if any(roles & nominal_roles(face) for face in faces):return True
            from morphology import native_suru_form
            if base=='する' and native_suru_form(head,form,rd,False) and any(any(p.startswith('名詞,サ変接続,') and b==face
                    for p,f,b,r in dictionary_inflections(face) or ()) for face in faces):return True
    readings=[];nominal=[]
    parts=tokenize(text)
    for part in parts:
        if all('ぁ'<=c<='ゖ' or c=='ー' for c in part.surface):rd=part.surface
        elif part.has_reading:rd=part.reading
        else:return False
        readings.append(rd)
        if part.end<=predicate_start-1:nominal.append(rd)
    prefix=text[:predicate_start-1]
    constraint=((''.join(nominal),tuple(faces))
        if any(not ('ぁ'<=c<='ゖ' or c=='ー') for c in prefix) else None)
    reading=''.join(readings)
    if not _written_predicate_reading_preserved(parts,predicate_start,reading):return False
    return bool(completed_native_reading_clause(reading,require_nominal=True,
                    require_object_fit=True,nominal_constraint=constraint)
                or completed_native_reading_sequence(reading,nominal_constraint=constraint)
                or allow_link and completed_native_reading_link(reading,require_nominal=True,
                    nominal_constraint=constraint))


@lru_cache(maxsize=4096)
def native_object_predicate_cuts(text):
    """Repair boundaries only; no anomaly or output is inferred here."""
    return tuple(dict.fromkeys(cut for start,cut,faces in native_object_predicate_contexts(text)
                 if not intact_native_reading(text[start:])
                 and not native_object_predicate_proof(text[start:],cut-start,faces)))
