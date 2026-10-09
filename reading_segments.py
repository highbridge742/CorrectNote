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



@lru_cache(maxsize=4096)
def native_nominal_units(text):
    """Exact written noun units, including a proved adjective + nominal sa.

    Return original ranges; no new word, spelling or dictionary row is made.
    Relations between units belong to the shared semantic compound check.
    """
    from morphology import tokenize,dictionary_inflections
    from general_words import general_katakana_noun_reading,sourced_common_noun_evidence
    parts=tokenize(text)
    if (not parts or parts[0].start!=0 or parts[-1].end!=len(text)
            or any(a.end!=b.start for a,b in zip(parts,parts[1:]))):return ()
    legacy=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
             t.start,t.end,t.has_reading,t.infl_form) for t in parts]
    units=[];i=0
    while i<len(parts):
        token=parts[i]
        if (token.has_reading and token.pos=='名詞'
                and not token.pos_sub.startswith(('固有名詞','非自立','接尾'))
                and (any(pos.startswith('名詞,') and rd==token.reading
                        for pos,form,base,rd in dictionary_inflections(token.surface) or ())
                     or general_katakana_noun_reading(token.surface,token.reading)
                     or sourced_common_noun_evidence(token.surface,token.reading))):
            units.append((token.start,token.end,token.surface));i+=1;continue
        if token.has_reading and token.pos=='名詞' and token.pos_sub=='接尾:一般' and units:
            from semantic_roles import deverbal_nominal_support
            if deverbal_nominal_support(text[:token.start],token.surface,token.reading):
                units.append((token.start,token.end,token.surface));i+=1;continue
        if (i+1<len(parts) and parts[i+1].surface=='さ'
                and nominalized_adjective_context(text,token.start,parts[i+1].end,lambda _:legacy)):
            end=parts[i+1].end;units.append((token.start,end,text[token.start:end]));i+=2;continue
        return ()
    return tuple(units)


@lru_cache(maxsize=4096)
def native_case_adnominal_parts(text,allow_unknown_left=False):
    """Native N + case/no + N; retain both nouns and the actual particles."""
    if not text or 'の' not in text or len(text)>80:return ()
    from morphology import tokenize
    from semantic_roles import nominal_compound_support
    def faces(value):
        if not value:return ()
        if all('ぁ'<=c<='ゖ' or c=='ー' for c in value):
            return native_nominal_phrase_faces(value)
        direct=_native_written_nominal_faces(value)
        if direct:return direct
        units=native_nominal_units(value)
        if units and all(nominal_compound_support(value[:a],word) for a,b,word in units[1:]):
            return (value,)
        return ()
    parts=tokenize(text);out=[]
    for case,link in zip(parts,parts[1:]):
        if (not case.has_reading or not link.has_reading or case.end!=link.start
                or case.pos!='助詞' or not case.pos_sub.startswith('格助詞')
                or case.surface not in ('で','へ','と','から','まで')
                or link.surface!='の' or link.pos!='助詞' or link.pos_sub!='連体化'):
            continue
        left=faces(text[:case.start]);right=faces(text[link.end:])
        if right and (left or allow_unknown_left):
            out.append((case.start,link.end,tuple(left),tuple(right)))
    return tuple(out)


def native_lexical_phrase(text, tokenize):
    """A native whole noun with its particle, or an interjection being quoted.

    GPT-6 / 2026-09-11 / 48-YT. This is evidence about the actual spelling,
    not about any homophonic word in a reading table. Unknown pieces and
    incomplete predicates provide no such evidence.
    """
    if not text or tokenize is None:
        return False
    if native_case_adnominal_parts(text):return True
    if native_written_adnominal_parts(text):return True
    if native_prefix_sahen_relative_parts(text):return True
    if native_written_sahen_nominal_parts(text):return True
    if native_argument_relative_nominal_parts(text):return True
    if native_written_action_nominal_parts(text):return True
    # The same attested written noun is valid with or without a particle.
    # This requires the whole word, not just the last head of a noun chain.
    if _native_written_nominal_faces(text)==(text,):return True
    tokens=list(tokenize(text) or ())
    if (not tokens or any(len(t)<6 or not t[5] for t in tokens)
            or tokens[0][3]!=0 or tokens[-1][4]!=len(text)
            or ''.join(t[0] for t in tokens)!=text
            or any(a[4]!=b[3] for a,b in zip(tokens,tokens[1:]))):
        return False
    from morphology import dictionary_inflections
    def ordinary_noun(pos):
        return pos.startswith('名詞') and not any(x in pos for x in ('固有名詞','接尾','非自立'))
    from general_words import general_katakana_noun_reading,sourced_common_noun_evidence
    def native_noun(token):
        return ordinary_noun(token[1]) and (any(ordinary_noun(pos) and rd==token[2]
            for pos,form,base,rd in dictionary_inflections(token[0]) or ())
            or general_katakana_noun_reading(token[0],token[2])
            or sourced_common_noun_evidence(token[0],token[2]))
    def unbound_nominal_parts(parts):
        if not parts:return False
        if len(parts)==1:return native_noun(parts[0])
        face=''.join(t[0] for t in parts);reading=''.join(t[2] for t in parts)
        # The existing reviewed whole word owns its original boundaries,
        # even when IPAdic splits a newer loanword into several nouns.
        if all(ordinary_noun(t[1]) for t in parts) and (
                general_katakana_noun_reading(face,reading)
                or sourced_common_noun_evidence(face,reading)):return True
        units=native_nominal_units(face)
        if not units:return False
        from semantic_roles import nominal_compound_support
        return all(nominal_compound_support(face[:a],word) for a,b,word in units[1:])
    def nominal_parts(parts):
        if unbound_nominal_parts(parts):return True
        if len(parts)<2:return False
        if parts[0][1]=='接頭詞:名詞接続':
            if ''.join(t[2] for t in parts) in native_attested_prefix_noun_readings(
                    ''.join(t[0] for t in parts)):return True
            # A productive nominal prefix attaches to the unchanged whole
            # noun. The combination need not itself be a dictionary entry;
            # both the actual prefix POS/reading and the host are attested.
            if (any(pos.startswith('接頭詞,名詞接続,') and rd==parts[0][2]
                    for pos,form,base,rd in dictionary_inflections(parts[0][0]) or ())
                    and unbound_nominal_parts(parts[1:])):return True
        tail=parts[-1]
        # NINJAL basic-use dictionary: 以上/以下 are comparative suffixes.
        # Keep the exact native head; other dependent nouns need their own link.
        # https://mmsrv.ninjal.ac.jp/kamus/data/item1081.html (and item1082)
        return bool(tail[0] in ('以上','以下') and tail[1].startswith('名詞')
            and unbound_nominal_parts(parts[:-1])
            and any(pos.startswith('名詞,非自立,副詞可能,') and rd==tail[2]
                    for pos,form,base,rd in dictionary_inflections(tail[0]) or ()))
    # Whole attested nouns or positively related nominal parts preserve
    # the source; unknown relations do not declare a word anomalous.
    if nominal_parts(tokens):return True
    if native_coordinated_nominal_heads(text):return True
    if native_written_nominal_coordination(text):return True
    if len(tokens)<2:
        head=tokens[0]
        return head[1].startswith('感動詞') and any(pos.startswith('感動詞,') and rd==head[2]
            for pos,form,base,rd in dictionary_inflections(head[0]) or ())
    tail=tokens[-1];heads=tokens[:-1];head=heads[0]
    entries=dictionary_inflections(head[0]) or ()
    nominal=nominal_parts(heads)
    nominal_particle=tail[1].startswith(('助詞:格助詞','助詞:係助詞','助詞:副助詞','助詞:連体化'))
    if not nominal and nominal_particle and not head[1].startswith("感動詞"):
        # A homophonous noun does not replace the original interjection POS.
        nominal=bool(native_surface_nominal_heads(text[:tail[3]]))
    interjection=len(heads)==1 and head[1].startswith('感動詞') and any(
        pos.startswith('感動詞,') and reading==head[2] for pos,form,base,reading in entries)
    if not nominal and not interjection:
        return False
    # A noun takes nominal case/topic/attributive particles. A connective
    # following a predicate cannot be justified by a nominal homograph.
    from pos_grammar import is_quotative_particle
    # A native na-adjective also has the adnominal copula な. Do not
    # treat its stem-final repetition as two unrelated particles.
    na_adnominal=(nominal and len(heads)==1 and '形容動詞語幹' in head[1] and tail[0]=='な'
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
    return any(pos.startswith('動詞,非自立,') and base in ('くださる','下さる')
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
            or not last.infl_form.startswith(('連用','未然','仮定'))):return False
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
        projected=[t for t in tokenize(before+finite) if t.start>=len(before)]
        # Source-only proof: complete the actual last inflection, preserving
        # every earlier token. Candidate completion remains strict; an open
        # source does not need to masquerade as a finite candidate.
        identity=lambda t:(t.surface,t.pos,t.pos_sub,t.reading,t.infl_form,t.start,t.end)
        if (len(projected)!=len(parts) or not projected[-1].has_reading
                or projected[-1].pos!=last.pos or projected[-1].surface!=lemma
                or [identity(t) for t in projected[:-1]]!=[identity(t) for t in parts[:-1]]):continue
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
                                    content_case_argument=None, allow_open_tail=False, source_prefix="", strict_subject_fit=True):
    """Original particles, optionally followed by a completed basic predicate.

    48-ZD / GPT-6 / 2026-09-11. Reuse the existing functional vocabulary
    and native inflection validation. A content noun, filler or unfinished
    verb is not another spelling of a functional phrase.
    """
    from semantic_roles import nominal_role_matches
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
        basic=direct_request or any(nominal_role_matches(face,roles) for face in content_object_faces)
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
        # A source-established basic construction (Nがある/いる, etc.)
        # keeps its previous proof unless this boundary explicitly requires
        # classified subject fit. Added content meanings supplement that
        # functional grammar; they do not remove its existing evidence.
        basic=(basic and not strict_subject_fit) or any(
            nominal_role_matches(face,roles) for face in content_subject_faces)
    if content_case_argument is not None:
        from semantic_roles import native_verb_roles,nominal_roles
        case,faces=content_case_argument
        roles=native_verb_roles(head[0],head[6],head[2],case=case,tail=suffix,before=before,allow_open_tail=allow_open_tail)
        basic=any(nominal_role_matches(face,roles) for face in faces)
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
def native_lexical_core_boundary_allowed(text,start,end):
    """48-AMS: preserve a native particle/auxiliary across lexical cuts.

    This validates the proposed word scope, not the source's correctness.
    Whole functional tokens may be repaired; their partial spelling cannot
    be borrowed to attest an unrelated lexical word across the boundary.
    """
    from morphology import tokenize,dictionary_inflections
    # An attested verb + te/de + focus remains a grammatical connection.
    # A lexical noun must not absorb its complete te/de token either.
    from contextual_repair import _native_focused_te_edges
    parts=tokenize(text)
    focused=set(_native_focused_te_edges(text))
    if any(token.has_reading and token.pos=='助詞' and token.pos_sub=='係助詞'
           and token.surface in ('は','も') and token.end in focused
           and start<token.start-1 and token.start<=end for token in parts):
        return False
    adjunct_starts=None
    for token in parts:
        if not (token.has_reading and token.pos in ('助詞','助動詞')
                and (token.start<start<token.end or token.start<end<token.end)):continue
        # 48-ANR: an independently attested original adjunct can own
        # a swallowed case edge (じぶんで + しゃしま, parsed as でし).
        # Share precisely the same boundary used by object targets and
        # their final frame proof; do not open the far end of a function.
        if token.start<start<token.end<=end:
            # A complete written sahen relative clause ends before this
            # independently attested noun, even if Janome absorbs its first
            # kana into the past auxiliary (したきー -> し/たき/ー).
            if (native_written_sahen_relative(text[:start])
                    and native_nominal_phrase_faces(text[start:end])):
                continue
            if adjunct_starts is None:
                adjunct_starts={offset+cut for offset,clause in _native_source_clauses(text)
                    for cut in native_adverbial_reading_cuts(clause)}
            if start in adjunct_starts:continue
        if any(pos.startswith(token.pos+',') and rd==token.reading
                and base==token.base_form and (token.pos!='助動詞' or form==token.infl_form)
                for pos,form,base,rd in dictionary_inflections(token.surface) or ()):
            return False
    return True


@lru_cache(maxsize=4096)
def native_candidate_continuation_allowed(source,source_end,changed,changed_end):
    """A new cut inside an unknown source word cannot leave an attributive stem.

    This checks candidate completion only. Existing source boundaries and
    unfinished source input are not reclassified as anomalies. Native finite
    and imperative alternatives keep their own POS and reading evidence.
    """
    from morphology import tokenize,dictionary_inflections
    # A wider replacement may repeat the unchanged suffix verbatim. Its
    # effective right edge must have the same proof as a narrow replacement.
    while (source_end and changed_end
           and source[source_end-1]==changed[changed_end-1]):
        source_end-=1;changed_end-=1
    if not any(t.start<source_end<t.end and not t.has_reading
               for t in tokenize(source)):
        return True
    clause=next(((offset,text) for offset,text in _native_source_clauses(changed)
                 if offset<changed_end<offset+len(text)),None)
    if clause is None:return True
    offset,text=clause;edge=changed_end-offset
    parts=[t for t in tokenize(text) if t.start>=edge]
    if (not parts or parts[0].start!=edge or parts[0].pos!='助詞'
            or not parts[0].pos_sub.startswith(('格助詞:一般','係助詞'))
            or not all(t.has_reading for t in parts)
            or any(t.pos not in ('助詞','動詞','助動詞','形容詞') for t in parts)):
        return True
    last=parts[-1]
    if (last.pos not in ('動詞','助動詞','形容詞')
            or not last.infl_form.startswith('体言接続')):
        return True
    native_pos=last.pos+','+(last.pos_sub.replace(':',',')+',' if last.pos_sub else '')
    forms=tuple(row for row in dictionary_inflections(last.surface) or ()
                if row[0].startswith(native_pos) and row[3]==last.reading)
    if not any(form==last.infl_form and base==last.base_form
               for pos,form,base,reading in forms):return True
    from contextual_repair import _completed_predicate_token,_native_imperative_completion
    for pos,form,base,reading in forms:
        token=(last.surface,last.pos+':'+last.pos_sub,reading,last.start,last.end,True,form)
        if _completed_predicate_token(token):return True
    first=next(i for i,t in enumerate(parts) if t.pos!='助詞')
    return _native_imperative_completion(parts[first:])


def native_lexical_core_edit_allowed(text,start,end,surface):
    """The same scope proof at final application, only for lexical words.

    An auxiliary's own spelling/inflection repair is not a lexical core.
    Missing lexical evidence gives no new source anomaly or blanket ban.
    """
    if native_lexical_core_boundary_allowed(text,start,end):return True
    from morphology import dictionary_inflections,tokenize
    # A first-roundtripped source word can start inside a misparsed
    # auxiliary. Prove the untouched attributive predicate and the actual
    # nominal replacement before accepting that independently supplied edge.
    from ime_inverse_gate import cached_context_neighbors
    if (cached_context_neighbors(text,start,end) is not None
            and any(pos.startswith('名詞,') and not any(kind in pos.split(',')
                    for kind in ('接尾','非自立'))
                    for pos,form,base,rd in dictionary_inflections(surface) or ())
            and native_attributive_predicate_end(text[:start])):
        prefix=tokenize(text[:start])
        head=next((t for t in reversed(prefix) if t.has_reading
                   and t.pos=='動詞' and t.pos_sub=='自立'),None)
        if (head and _completed_native_verb_surface(text[head.start:start],
                allow_nonpolite=True,require_roles=False,finite_only=True)):
            return True
    # An edit wholly inside the function itself is not a cross-word core.
    if any(t.has_reading and t.pos in ('助詞','助動詞')
            and t.start<=start<=end<=t.end for t in tokenize(text)):return True
    lexical=any(pos.startswith(('名詞,','動詞,','形容詞,','副詞,','連体詞,'))
                and not any(kind in pos.split(',') for kind in ('接尾','非自立'))
                for pos,form,base,rd in dictionary_inflections(surface) or ())
    if lexical:return False
    return not native_lexical_reading_faces(surface)


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
    from public_nominal_cache import load
    cached=load()
    if cached is not None:return cached['seed']
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
COUNTER_READING_VERSION = '2026-09-20als'


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
def _small_number_surface_aliases():
    return {''.join(_native_small_number_words(n)):
            (str(n),str(n).translate(str.maketrans('0123456789','０１２３４５６７８９')))
            for n in range(1,100)}


@lru_cache(maxsize=4096)
def _native_counter_spelling_variants(face):
    """48-ALM: numeral spellings of an already attested complete count."""
    import re
    match=re.match(r'([一二三四五六七八九十]+)(.+)$',face)
    if not match:return (face,)
    aliases=_small_number_surface_aliases().get(match.group(1),())
    return (face,)+tuple(number+match.group(2) for number in aliases)


@lru_cache(maxsize=1)
def native_counted_surface_readings():
    """The same native counter/ordinal paradigm in kana, kanji and digits."""
    found={}
    for table in (native_counter_readings(),native_ordinal_readings()):
        for reading,faces in table.items():
            found.setdefault(reading,set()).add(reading)
            for face in faces:
                for surface in _native_counter_spelling_variants(face):
                    found.setdefault(surface,set()).add(reading)
    return {surface:tuple(sorted(readings,key=lambda rd:(len(rd),rd)))
            for surface,readings in found.items()}


@lru_cache(maxsize=1)
def native_counted_surface_prefixes():
    return frozenset(word[:cut] for word in native_counted_surface_readings()
                     for cut in range(1,len(word)+1))


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
                for text in (reading,*_native_counter_spelling_variants(face)):
                    index.setdefault(text,set()).add((unit,ordinal))
    return {text:tuple(sorted(evidence)) for text,evidence in index.items()}


@lru_cache(maxsize=1)
def _numeric_counted_spelling_pattern():
    import re
    # 48-ALP: grouping is three digits; the decimal point has digits on
    # both sides. Malformed notation cannot lend a valid suffix its scope.
    digit=r'[0-9０-９]'
    number=rf'(?:{digit}{{1,3}}(?:[,，]{digit}{{3}})+|{digit}+)(?:[.．]{digit}+)?'
    return re.compile(rf'(?<![0-9０-９.,，．])({number})([個枚冊本台人])(目?)')


def native_numeric_quantity_spans(text):
    """Written numeric counters, preserving source coordinates and value."""
    return tuple(match.span() for match in _numeric_counted_spelling_pattern().finditer(text)
                 if native_counted_nominal_evidence(match.group()))


@lru_cache(maxsize=2048)
def _native_kanji_number_spelling(text):
    """48-ALS: written integer structure, with native numeric characters.

    No pronunciation is constructed. Small units descend 千/百/十 and
    large groups descend 兆/億/万; repeated or reversed units are not proof.
    """
    import re
    from morphology import dictionary_inflections
    digits='一二三四五六七八九'
    if not text or any(ch not in digits+'〇零十百千万億兆' for ch in text):return False
    if not all(any(pos.startswith('名詞,数,') and base==ch
                   for pos,form,base,reading in dictionary_inflections(ch) or ()) for ch in set(text)):
        return False
    if all(ch in digits+'〇零' for ch in text):return True
    small=rf'(?:[{digits}]?千)?(?:[{digits}]?百)?(?:[{digits}]?十)?[{digits}]?'
    valid_small=lambda word:bool(word and re.fullmatch(small,word))
    start=0;previous=-1;large=False
    for position,ch in enumerate(text):
        if ch not in '兆億万':continue
        order='兆億万'.index(ch)
        if order<=previous or not valid_small(text[start:position]):return False
        previous=order;start=position+1;large=True
    tail=text[start:]
    return valid_small(tail) or large and not tail


def native_counted_nominal_evidence(surface):
    """Exact native count, or numeric spelling with an attested counter.

    48-ALO: digit quantities keep their written value. Their unit supplies
    meaning without inventing a Japanese pronunciation for large numbers.
    """
    found=_counted_nominal_index().get(surface,())
    if found:return found
    match=_numeric_counted_spelling_pattern().fullmatch(surface)
    if match:
        number,unit,ordinal=match.groups()
        if ordinal and any(c in '.．' for c in number):return ()
    else:
        import re
        match=re.fullmatch(r'([〇零一二三四五六七八九十百千万億兆]+)([個枚冊本台人])(目?)',surface)
        if not match:return ()
        number,unit,ordinal=match.groups()
        if not _native_kanji_number_spelling(number):return ()
    # Reuse the native paradigm's evidence for this suffix and ordinal.
    return _counted_nominal_index().get('二'+unit+ordinal,())


@lru_cache(maxsize=1)
def _katakana_nominal_inventory():
    """Membership only: keep the public roster's original ordering intact."""
    from seed_katakana import KATAKANA_WORDS
    return frozenset(KATAKANA_WORDS)


@lru_cache(maxsize=8192)
def native_katakana_nominal_face(reading):
    """An unchanged loanword needs native or reviewed ordinary-noun evidence.

    The shipped loanword roster locates the face; native lexical identity
    and its exact reading prove the word. A cost-table spelling alone does not.
    """
    if not reading or not all('ぁ'<=c<='ゖ' or c=='ー' for c in reading):return None
    face=''.join(chr(ord(c)+0x60) if 'ぁ'<=c<='ゖ' else c for c in reading)
    from general_words import general_katakana_noun_reading,sourced_common_noun_evidence
    if general_katakana_noun_reading(face,reading) or sourced_common_noun_evidence(face,reading):return face
    if face not in _katakana_nominal_inventory():return None
    from morphology import dictionary_inflections
    if any(pos.startswith(('名詞,一般,','名詞,サ変接続,')) and base==face and rd==reading
           for pos,form,base,rd in dictionary_inflections(face) or ()):return face
    return None


@lru_cache(maxsize=1)
def _classified_nominal_readings():
    """48-ALA/AMI: attested whole readings of classified ordinary nouns.

    External common-noun evidence retains its source in general_words;
    morphology.dictionary_inflections remains native-only. Whole common
    entries and contiguous compounds share one role inventory. 48-AMP:
    exact one-kana nouns use the same evidence and callers prove the case;
    proper, dependent and suffix entries cannot supply a new whole noun.
    """
    from public_nominal_cache import load
    cached=load()
    if cached is not None:return cached['classified']
    from semantic_roles import NOUN_ROLES,VERB_ROLES
    from morphology import tokenize,dictionary_inflections,native_sahen_compound_reading
    from general_words import sourced_common_noun_evidence
    found={}
    for face in sorted(NOUN_ROLES.keys() | VERB_ROLES.keys()):
        action_reading=native_sahen_compound_reading(face)
        if action_reading:found.setdefault(action_reading,set()).add(face)
        for entry in sourced_common_noun_evidence(face):
            found.setdefault(entry['reading'],set()).add(face)
        for pos,form,base,reading in dictionary_inflections(face) or ():
            if (base==face and reading
                    and pos.startswith(('名詞,一般,','名詞,サ変接続,','名詞,副詞可能,','名詞,代名詞,'))
                    and all('ぁ'<=c<='ゖ' or c=='ー' for c in reading)):
                found.setdefault(reading,set()).add(face)
        parts=tokenize(face)
        if (len(parts)<2 or ''.join(t.surface for t in parts)!=face
                or any(a.end!=b.start for a,b in zip(parts,parts[1:]))):continue
        ordinary=[any(pos.startswith('名詞,') and base==part.surface and rd==part.reading
                and not any(kind in pos for kind in ('固有名詞','接尾','非自立'))
                for pos,form,base,rd in dictionary_inflections(part.surface) or ()) for part in parts]
        if all(ordinary):
            reading=''.join(part.reading for part in parts)
            if reading and all('ぁ'<=c<='ゖ' or c=='ー' for c in reading):
                found.setdefault(reading,set()).add(face)
        elif (all(ordinary[:-1]) and parts[-1].has_reading
                and parts[-1].pos=='名詞' and parts[-1].pos_sub=='接尾:一般'):
            # GPT-6 Astra / 2026-09-21: the independently classified whole
            # noun supplies word/meaning evidence. The table only attests its
            # whole reading, matched to the same native noun and suffix rows.
            # Do not invent a word from an arbitrary host/suffix combination.
            from corrector import _table_readings_for_surface
            whole_readings=set(_table_readings_for_surface(face))
            prefix=''.join(part.reading for part in parts[:-1])
            for pos,form,base,rd in dictionary_inflections(parts[-1].surface) or ():
                reading=prefix+rd
                if (pos.startswith('名詞,接尾,一般,') and base==parts[-1].surface
                        and reading in whole_readings
                        and all('ぁ'<=c<='ゖ' or c=='ー' for c in reading)):
                    found.setdefault(reading,set()).add(face)
    return {rd:tuple(sorted(faces)) for rd,faces in found.items()}


@lru_cache(maxsize=8192)
def native_lexical_reading_faces(reading):
    """48-AJA: exact whole-word evidence, not mere cost-table keys.

    The cost table locates candidate spellings. Only their own dictionary
    reading and independent lexical category attest the word. Inflected
    verbs remain lexical words; particles and dependent suffixes do not.
    Lack of this evidence never declares an original spelling anomalous.
    """
    if not reading or not all('ぁ'<=c<='ゖ' or c=='ー' for c in reading):return ()
    from morphology import dictionary_inflections
    from general_words import general_katakana_noun_reading,sourced_common_noun_evidence
    from corrector import table_surfaces_for_reading
    katakana=''.join(chr(ord(c)+0x60) if 'ぁ'<=c<='ゖ' else c for c in reading)
    faces={reading,katakana,*table_surfaces_for_reading(reading,limit=12)}
    return tuple(sorted(face for face in faces if general_katakana_noun_reading(face,reading)
        or sourced_common_noun_evidence(face,reading) or any(
        rd==reading and pos.startswith(('名詞,','動詞,','形容詞,','副詞,','連体詞,','感動詞,','接続詞,'))
        and not any(part in pos.split(',') for part in ('接尾','非自立'))
        for pos,form,base,rd in dictionary_inflections(face) or ())))


@lru_cache(maxsize=4096)
def native_continuative_reading_faces(reading):
    """An unchanged reading may use another attested reading of one verb.

    Lexical identity and conjugation come from the native dictionary. The
    reading table must attest both the same written stem and its own lemma
    with the same inflectional change. A cost-table noun alone proves none
    of these facts. This returns evidence, not a proposed spelling.
    """
    if not reading or not all('ぁ'<=c<='ゖ' or c=='ー' for c in reading):return ()
    from morphology import dictionary_paradigms
    from corrector import table_surfaces_for_reading
    faces=tuple(dict.fromkeys((reading,*table_surfaces_for_reading(reading,limit=12))))
    out=[]
    for face in faces:
        for pos,kind,form,base,rd in dictionary_paradigms(face) or ():
            if not pos.startswith('動詞,自立,') or form!='連用形':continue
            if rd==reading:
                out.append(face);break
            for bp,bk,bf,bb,br in dictionary_paradigms(base) or ():
                if (bp!=pos or bk!=kind or bf!='基本形' or bb!=base):continue
                common=0
                while common<min(len(rd),len(br)) and rd[common]==br[common]:common+=1
                # Keep the lexical stem; only the native inflectional tail
                # can differ between the source reading and its lemma.
                if common==0:continue
                ending=rd[common:]
                if ending and not reading.endswith(ending):continue
                root=reading[:-len(ending)] if ending else reading
                if not root:continue
                base_reading=root+br[common:]
                if base in table_surfaces_for_reading(base_reading,limit=12):
                    out.append(face);break
    return tuple(dict.fromkeys(out))


@lru_cache(maxsize=4096)
def native_continuative_prefix_cuts(reading):
    """Visit the same possible stems through the native and reading indices.

    Exact form/reading and full-tail validation still follow. No lexical
    length limit or hand-selected auxiliary alphabet is introduced.
    """
    from morphology import dictionary_prefix_paradigms
    from corrector import table_reading_prefix_lengths
    native=dictionary_prefix_paradigms(reading)
    if native is None:return tuple(range(1,len(reading)))
    cuts={len(surface) for surface,pos,kind,form,base,rd in native
          if pos.startswith('動詞,自立,') and form=='連用形'}
    cuts.update(table_reading_prefix_lengths(reading))
    return tuple(sorted(cut for cut in cuts if 0<cut<len(reading)))


@lru_cache(maxsize=4096)
def native_source_finite_verb(reading):
    """The unchanged finite verb's grammar, without a positive meaning claim.

    Only source preservation uses this evidence. Candidate acceptance still
    requires its own argument/meaning proof. Alternate readings retain the
    same native continuative inflection and the entire original finite tail.
    """
    if not reading or not all('ぁ'<=c<='ゖ' or c=='ー' for c in reading):return False
    from morphology import tokenize,dictionary_inflections
    from contextual_repair import _allows_grammatical_tail
    def complete(surface):
        if not _completed_native_verb_surface(surface,True,False,True):return False
        head=tokenize(surface)[0]
        forms=tuple(row for row in dictionary_inflections(head.surface) or ()
                    if row[0].startswith('動詞,自立,')
                    and row[1]==head.infl_form and row[3]==head.reading)
        return bool(forms and (head.end==len(surface)
            or _allows_grammatical_tail(forms,surface[head.end:],head.reading,head.surface)))
    # Source grammar must not license the same invalid polite/copula chain
    # rejected by candidate validation. This direct seam check does not
    # consult source ranges and therefore cannot validate itself recursively.
    from oddness import finite_copula_aux_mismatch
    parts=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
            t.start,t.end,t.has_reading,t.infl_form) for t in tokenize(reading)]
    if any(finite_copula_aux_mismatch(a,b,parts[i-1] if i else None)
           for i,(a,b) in enumerate(zip(parts,parts[1:]))):return False
    if complete(reading):return True
    for cut in native_continuative_prefix_cuts(reading):
        for face in native_continuative_reading_faces(reading[:cut]):
            tail=reading[cut:]
            if complete(face+tail):return True
            # A kana stem may be tokenized as a filler or particle. Its
            # exact native verb entry still supplies the original inflection;
            # prove the entire unchanged tail, including finite completion.
            forms=tuple(row for row in dictionary_inflections(face) or ()
                if row[0].startswith('動詞,自立,') and row[1]=='連用形'
                and row[3]==reading[:cut])
            if not forms:continue
            suffix=tokenize(tail)
            if not suffix or not all(t.has_reading for t in suffix):continue
            # A suffix grammar cannot certify another independent action.
            # Such a sequence needs its own original argument/clause proof.
            if any(t.pos=='動詞' and t.pos_sub=='自立' for t in suffix):continue
            from contextual_repair import _completed_predicate_token
            core=native_predicate_finite_core([
                (t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                 t.start,t.end,t.has_reading,t.infl_form) for t in suffix])
            if (core and _completed_predicate_token(core[-1])
                    and _allows_grammatical_tail(forms,tail,reading[:cut],face)):
                return True
    return False


@lru_cache(maxsize=4096)
def native_source_predicate_ranges(text):
    """Source grammar is not disproved by an unclassified meaning label.

    The original noun/case and whole finite predicate supply the range.
    Independently demonstrated source conflicts remain anomalies. Neither
    another word's meaning nor a proposed correction supplies this evidence.
    """
    # A native sahen noun and its complete suru tail have the same
    # source grammar as a lexical verb. A proved te/de connection also
    # retains the original text without completing a candidate. Missing semantic labels
    # do not turn that unchanged reading into evidence of a typing error.
    # Candidate acceptance continues to require its own argument proof.
    def complete(predicate):
        return (native_source_finite_verb(predicate)
            or completed_sahen_reading(predicate,allow_nonpolite=True)
            or predicate.endswith(('て','で')) and completed_native_verb_reading(
                predicate,allow_nonpolite=True,require_roles=False))
    out=[]
    for start,clause in _native_source_clauses(text):
        if _native_written_predicate_conflicts(clause):continue
        if complete(clause):
            out.append((start,start+len(clause)));continue
        # Source preservation can use the existing case/written frame
        # locator. Its actual noun/case and complete kana verb are still
        # required; this does not widen candidate-generation boundaries.
        contexts=tuple(dict.fromkeys(native_argument_predicate_contexts(clause)+tuple(
            (0,cut,faces) for cut,faces in native_object_predicate_frames(clause,True))))
        preposed=native_preposed_object_parts(clause,allow_written_predicate=True)
        for begin,cut,faces in contexts:
            if complete(clause[cut:]):
                # This whole-range proof owns an explicit earlier case too.
                # A complete final verb alone cannot certify that case.
                # Missing evidence withholds this proof; it creates no mark.
                if (any(begin<edge and owned_cut==cut for edge,case,receiver,owned_cut,objects in preposed)
                        and not native_object_predicate_proof(clause[begin:],cut-begin,faces)):
                    continue
                out.append((start+begin,start+len(clause)))
    return tuple(dict.fromkeys(out))


def native_common_noun_reading(surface, reading):
    """Attested common-noun identity, shared by sources and choices.

    Historical API name; the classified index may also hold separately
    sourced common-noun readings. Native dictionary rows stay unchanged.
    """
    from morphology import dictionary_inflections
    from general_words import general_katakana_noun_reading,sourced_common_noun_evidence
    return (general_katakana_noun_reading(surface,reading)
            or bool(sourced_common_noun_evidence(surface,reading))
            or any(pos.startswith('名詞,') and rd == reading
               and not any(x in pos for x in ('固有名詞', '接尾', '非自立'))
               for pos, form, base, rd in dictionary_inflections(surface) or ())
            or surface in _classified_nominal_readings().get(reading,()))


@lru_cache(maxsize=4096)
def native_common_noun_faces(reading):
    """Exact ordinary-noun alternatives, without usage-tier or repair guesses."""
    return tuple(face for face in native_lexical_reading_faces(reading)
                 if native_common_noun_reading(face,reading))


@lru_cache(maxsize=4096)
def native_deverbal_nominal_faces(reading):
    """A native continuative verb also listed as the very same common noun.

    The noun entry supplies nominal use; a verb ending alone does not.
    Exact surface/reading agreement excludes unrelated homophones.
    """
    from morphology import dictionary_inflections
    found=[]
    for face in native_lexical_reading_faces(reading):
        forms=dictionary_inflections(face) or ()
        if (any(pos.startswith('名詞,一般,') and base==face and rd==reading
                for pos,form,base,rd in forms)
                and any(pos.startswith('動詞,自立,') and form=='連用形' and rd==reading
                        for pos,form,base,rd in forms)):
            found.append(face)
    return tuple(found)


@lru_cache(maxsize=16384)
def _native_nominal_reading_faces(reading):
    """Attested common-noun spellings with this exact complete reading.

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
    attested=tuple(attested)+_classified_nominal_readings().get(reading,())
    # External whole-noun facts prove identity even without a semantic role.
    # Reuse their exact reading; absence from the role table is not oddness.
    from general_words import SOURCED_COMMON_NOUNS,sourced_common_noun_evidence
    attested+=tuple(face for face in SOURCED_COMMON_NOUNS
                    if sourced_common_noun_evidence(face,reading))
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
    # The actual prefix check below already requires these two literals.
    # Do it before tokenizing every non-honorific suffix of a long clause.
    if not text or len(text)<2 or text[0] not in ('お','ご'):return ()
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
    suffix=next((s for s in ('たち','達') if text.endswith(s)),None)
    if not suffix or len(text)<=len(suffix):return ()
    from morphology import tokenize,dictionary_inflections
    from semantic_roles import nominal_roles
    if not any(pos.startswith('名詞,接尾,一般,') and rd=='たち'
               for pos,form,base,rd in dictionary_inflections(suffix) or ()):return ()
    head=text[:-len(suffix)]
    faces=_native_nominal_reading_faces(head) if all('ぁ'<=c<='ゖ' for c in head) else (head,)
    if any(pos.startswith('名詞,代名詞,') and base==head and rd==head
           for pos,form,base,rd in dictionary_inflections(head) or ()):
        faces=tuple(faces)+(head,)
    found=[]
    for face in faces:
        tokens=tokenize(face+suffix)
        if (len(tokens)!=2 or tokens[0].surface!=face or tokens[0].pos!='名詞'
                or tokens[1].surface!=suffix or tokens[1].pos!='名詞'
                or tokens[1].pos_sub!='接尾:一般' or not all(t.has_reading for t in tokens)):continue
        if 'person' in nominal_roles(face) or tokens[0].pos_sub.startswith('代名詞'):
            found.append(face)
    return tuple(sorted(set(found)))


@lru_cache(maxsize=4096)
def native_deverbal_compound_parts(reading):
    """Exact nominal readings plus the verb-derived head's object meaning."""
    if not reading or not all('ぁ'<=c<='ゖ' or c=='ー' for c in reading):return ()
    from semantic_roles import deverbal_nominal_support
    out=[]
    for cut in range(2,len(reading)-1):
        objects=_native_nominal_reading_faces(reading[:cut])
        if not objects:continue
        for action in native_lexical_reading_faces(reading[cut:]):
            for obj in objects:
                if deverbal_nominal_support(obj,action,reading[cut:]):out.append((cut,obj,action))
    return tuple(out)


@lru_cache(maxsize=4096)
def native_relational_compound_heads(reading):
    """Attested written noun compounds retain an independently fitting head.

    A frequency-table spelling only locates a possible compound. Both
    native nouns, their full readings and the existing compound relation
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
        prefix=reading[:cut]
        objects=(_native_nominal_reading_faces(prefix) or
                 (native_nominal_phrase_faces(prefix) if prefix.endswith('さ') else ()))
        for action in actions:
            if any(support(obj,action) for obj in objects):heads.add(action)
    # A continuative used as an attested nominal suffix has the same
    # object relation, but only inside this native noun compound.
    heads.update(action for cut,obj,action in native_deverbal_compound_parts(reading))
    # 48-AMA: a field can qualify an actual reference/teaching head
    # productively. Each half still owns its full native common-noun reading;
    # a proper-name-only dictionary entry cannot invent the common reading.
    from semantic_roles import nominal_roles,field_nominal_support,document_purpose_support
    for cut in range(2,len(reading)-1):
        qualified=tuple(face for face in _native_nominal_reading_faces(reading[cut:])
                        if nominal_roles(face) & {'reference','teaching','text'})
        if not qualified:continue
        fields=_native_nominal_reading_faces(reading[:cut])
        for head in qualified:
            if any(field_nominal_support(field,head) or document_purpose_support(field,head)
                   for field in fields):heads.add(head)
    # A literal katakana spelling is another locator, not word evidence.
    # Both actual nouns, exact readings and the independent relation below
    # still have to agree (including an attested loanword compound).
    katakana=''.join(chr(ord(c)+0x60) if 'ぁ'<=c<='ゖ' else c for c in reading)
    for face in dict.fromkeys((*table_surfaces_for_reading(reading,limit=12),katakana)):
        # The ordinary-word tier itself requires a single dictionary token,
        # so it cannot establish a two-token compound. The native readings
        # and semantic composition below provide the independent word proof.
        parts=tokenize(face)
        if (len(parts)!=2 or ''.join(t.surface for t in parts)!=face
                or parts[0].pos not in ('名詞','接頭詞') or parts[1].pos!='名詞'
                or any(not t.has_reading
                       or any(kind in t.pos_sub for kind in ('固有名詞','非自立')) for t in parts)):continue
        # A parser's first reading is not the noun's only native reading.
        # Keep the actual word and POS, and consider every dictionary reading
        # of that same entry (suffix 物 has both ぶつ and もの).
        from morphology import dictionary_inflections
        options=[{rd for pos,form,base,rd in dictionary_inflections(t.surface) or ()
                  if pos.startswith(t.pos+','+t.pos_sub.replace(':',',')+',')}
                 for t in parts]
        matching=tuple((a,b) for a in options[0] for b in options[1] if a+b==reading)
        if not matching:continue
        first,head=parts
        if first.pos=='接頭詞':
            # 48-ALZ: a registered whole noun can have a native property
            # prefix (青 + りんご). The same prefix reading must also be
            # an actual i-adjective stem. Negating/privative prefixes do
            # not acquire the noun's positive meaning from mere attachment.
            from seed_japanese import is_unit
            if (first.pos_sub=='名詞接続' and not head.pos_sub.startswith('接尾')
                    and is_unit(face) is True and any(
                        pos.startswith('形容詞,') and form=='基本形' and base==first.surface+'い'
                        and rd==a+'い' for a,b in matching
                        for pos,form,base,rd in dictionary_inflections(first.surface+'い') or ())):
                heads.add(head.surface)
            continue
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
        from semantic_roles import relational_nominal_support
        if relational_nominal_support(first.surface,head.surface):heads.add(head.surface)
    return tuple(sorted(heads))


@lru_cache(maxsize=4096)
def native_coordinated_nominal_parts(text):
    """Native N と N, retaining every original spelling and complete reading."""
    if 'と' not in text or not 3<=len(text)<=24:return ()
    from morphology import tokenize,dictionary_inflections
    if not any(p.startswith('助詞,並立助詞,') and rd=='と'
               for p,f,b,rd in dictionary_inflections('と') or ()):return ()
    parts=tokenize(text)
    if (len(parts)>=3 and len(parts)%2==1 and parts[0].start==0
            and parts[-1].end==len(text)
            and all(a.end==b.start for a,b in zip(parts,parts[1:]))):
        for index,part in enumerate(parts):
            if not part.has_reading:break
            if index%2:
                if part.surface!='と' or part.pos!='助詞' or part.pos_sub!='並立助詞':break
            elif (part.pos!='名詞' or any(x in part.pos_sub for x in ('固有名詞','非自立','接尾'))
                    or not any(p.startswith('名詞,') and rd==part.reading
                               and not any(x in p.split(',')[1:4] for x in ('固有名詞','非自立','接尾'))
                               for p,f,b,rd in dictionary_inflections(part.surface) or ())):break
        else:return tuple(part.surface for part in parts[::2])
    # 48-AKP: kana can be split as auxiliaries or verbs even though every
    # complete noun reading is attested. Reuse those lexical proofs; a known
    # whole word/name/form and ambiguous nominal boundaries are not reopened.
    if (not all('ぁ'<=c<='ゖ' or 'ァ'<=c<='ヶ' or '一'<=c<='鿿' or c=='ー' for c in text)
            or dictionary_inflections(text) or _native_nominal_reading_faces(text)):
        return ()
    # 48-AMK / GPT-6 Astra / 2026-09-20: a dictionary reading may
    # belong to a bound/alternate use of a written noun. An inferred
    # coordinate needs the same reading in the independent noun itself.
    # Keep exact sourced common-noun senses separate from the native
    # tokenizer's preferred proper-name parse. No source is made odd merely
    # because this additional positive boundary proof is unavailable.
    from general_words import sourced_common_noun_evidence
    @lru_cache(maxsize=None)
    def independent_member(reading):
        if not all('ぁ'<=c<='ゖ' or c=='ー' for c in reading):
            # Partial ordinary spelling retains the same independent noun;
            # no reading of a different written homophone supplies this proof.
            return bool(sourced_common_noun_evidence(reading) or any(
                p.startswith('名詞,') and base==reading and not any(
                    kind in p.split(',')[1:4] for kind in ('固有名詞','非自立','接尾'))
                for p,form,base,rd in dictionary_inflections(reading) or ()))
        for face in _native_nominal_reading_faces(reading):
            if sourced_common_noun_evidence(face,reading):return True
            word=tokenize(face)
            if (word and ''.join(t.surface for t in word)==face
                    and ''.join(t.reading for t in word)==reading
                    and all(t.has_reading and t.pos=='名詞'
                        and not any(kind in t.pos_sub for kind in ('固有名詞','非自立','接尾'))
                        for t in word)):
                return True
        return False
    @lru_cache(maxsize=None)
    def suffixes(start):
        found=[]
        rest=text[start:]
        if independent_member(rest):return ((rest,),)
        for cut in range(start+1,len(text)-1):
            if text[cut]!='と':continue
            head=text[start:cut]
            if not independent_member(head):continue
            for tail in suffixes(cut+1):
                found.append((head,)+tail)
                if len(found)>1:return tuple(found)
        return tuple(found)
    interpretations=suffixes(0)
    return interpretations[0] if len(interpretations)==1 else ()


@lru_cache(maxsize=4096)
def native_container_nominal_heads(text):
    """48-AMF: actual noun + classified container suffix, including rendaku.

    The same native spelling, boundaries and readings prove kana and written
    sources. A container retains its own role; its contents are not inherited.
    """
    from morphology import tokenize,dictionary_inflections
    from semantic_roles import NOUN_GROUPS,nominal_host_suffix,genitive_nominal_support
    if not text or len(text)>24:return ()
    heads=set()
    def consider(left,head,reading):
        kind=nominal_host_suffix(head)
        if not kind or kind['role']!='container':return
        parts=tokenize(left+head)
        if (len(parts)!=2 or tuple(t.surface for t in parts)!=(left,head)
                or parts[0].start!=0 or parts[0].end!=parts[1].start
                or parts[1].end!=len(left+head) or not all(t.has_reading for t in parts)
                or parts[0].pos!='名詞'
                or any(x in parts[0].pos_sub for x in ('固有名詞','非自立','接尾'))
                or parts[1].pos!='名詞' or not parts[1].pos_sub.startswith('接尾:一般')
                or ''.join(t.reading for t in parts)!=reading):return
        if genitive_nominal_support(left,head):heads.add(head)
    if all('ぁ'<=c<='ゖ' or c=='ー' for c in text):
        for head in NOUN_GROUPS['container']:
            kind=nominal_host_suffix(head)
            if not kind or kind['role']!='container':continue
            endings={rd for pos,form,base,rd in dictionary_inflections(head) or ()
                     if pos.startswith('名詞,接尾,一般,') and base==head and rd}
            for ending in endings:
                if not text.endswith(ending) or len(text)<=len(ending):continue
                for left in _native_nominal_reading_faces(text[:-len(ending)]):
                    consider(left,head,text)
    else:
        parts=tokenize(text)
        if len(parts)==2 and ''.join(t.surface for t in parts)==text:
            consider(parts[0].surface,parts[1].surface,''.join(t.reading for t in parts))
    return tuple(sorted(heads))


@lru_cache(maxsize=4096)
def _native_suffix_nominal_pairs(text,suffix,rd,sub):
    """One exact native noun and suffix, with their unchanged readings."""
    if not text or not 2<=len(text)<=24:return ()
    # Native noun merging can hide an attested suffix (e.g. 承認待ち).
    # Use the existing locked native parse before contextual restoration.
    from morphology import _tokenize_janome as tokenize,dictionary_inflections
    kana=all('ぁ'<=c<='ゖ' or c=='ー' for c in text)
    ending=rd if kana or text.endswith(rd) else suffix
    if not text.endswith(ending) or len(text)<=len(ending):return ()
    if not any(pos.startswith('名詞,'+sub.replace(':',',')+',')
               and base==suffix and native_rd==rd
               for pos,form,base,native_rd in dictionary_inflections(suffix) or ()):return ()
    reading=text[:-len(ending)] if kana else None
    hosts=_native_nominal_reading_faces(reading) if kana else (text[:-len(ending)],)
    found=[]
    for host in hosts:
        # External whole-word evidence retains the same actual suffix fact
        # when IPAdic splits its absent head into unrelated verb fragments.
        from general_words import sourced_common_noun_evidence
        external=sourced_common_noun_evidence(host,reading)
        if external:
            found.extend((host,row['pos'].split(',')[1]) for row in external)
            continue
        parts=tokenize(host+suffix)
        if not (len(parts)>=2 and parts[-1].surface==suffix
                and parts[0].start==0 and parts[-1].start==len(host)
                and parts[-1].end==len(host)+len(suffix) and all(t.has_reading for t in parts)
                and all(a.end==b.start for a,b in zip(parts,parts[1:]))
                and ''.join(t.surface for t in parts[:-1])==host
                and all(t.pos=='名詞' for t in parts[:-1])
                and parts[-1].pos=='名詞' and parts[-1].pos_sub==sub
                and parts[-1].reading==rd):continue
        host_reading=''.join(t.reading for t in parts[:-1])
        # 48-ANX: the host can be an already classified native compound
        # such as 看護 + 師. Reuse its whole ordinary-noun reading; a
        # series of unclassified nouns/suffixes is not a new lexical host.
        # A parser's preferred suffix reading is not the only attested
        # reading of the same whole noun. Kana must match its exact source
        # reading; written input can retain another proved native reading.
        proved=native_common_noun_reading(host,reading if reading is not None else host_reading)
        if not proved and reading is None:
            from corrector import _table_readings_for_surface
            proved=any(native_common_noun_reading(host,rd)
                       for rd in _table_readings_for_surface(host))
        if not proved:continue
        found.append((host,parts[-2].pos_sub))
    return tuple(sorted(set(found)))


@lru_cache(maxsize=4096)
def native_written_derived_nominal_faces(text):
    """An unchanged ordinary noun and an actual written nominal suffix.

    The complete host and the native suffix reading/POS are both required.
    Pure kana よう/か can instead be functional endings; do not invent
    a derived noun from those endings. The host's action roles are not
    inherited by a purpose/transformation noun. NINJAL BCCWJ manual 5,
    appendix 5-E attests 化 as a nominal suffix; IPAdic supplies its POS.
    """
    for suffix,reading,kind in (('用','よう','接尾:一般'),('化','か','接尾:サ変接続'),
                                ('製','せい','接尾:一般'),('外','がい','接尾:一般'),
                                ('度','ど','接尾:一般'),('付き','つき','接尾:一般')):
        if text.endswith(suffix):
            return tuple(host+suffix for host,host_kind in
                         _native_suffix_nominal_pairs(text,suffix,reading,kind)
                         if suffix!='度' or host_kind in ('サ変接続','形容動詞語幹'))
    # A separately attested whole word can retain another native suffix.
    # The word inventory supplies identity, never familiarity or an action
    # role. Both the full host and the suffix still need their own native
    # reading/POS, and the composed reading must belong to the whole word.
    from seed_japanese import is_unit
    if not any('一'<=c<='鿿' for c in text) or is_unit(text) is not True:return ()
    from morphology import _tokenize_janome
    parts=_tokenize_janome(text)
    if (len(parts)<2 or parts[0].start!=0 or parts[-1].end!=len(text)
            or any(a.end!=b.start for a,b in zip(parts,parts[1:]))
            or any(not t.has_reading for t in parts)
            or parts[-1].pos!='名詞' or parts[-1].pos_sub!='接尾:一般'):return ()
    from corrector import _table_readings_for_surface
    reading=''.join(t.reading for t in parts)
    if reading not in _table_readings_for_surface(text):return ()
    suffix=parts[-1]
    if _native_suffix_nominal_pairs(text,suffix.surface,suffix.reading,suffix.pos_sub):return (text,)
    return ()


@lru_cache(maxsize=4096)
def native_temporal_nominal_faces(text,include_ongoing=True):
    """Native action + phase noun, keeping its whole temporal identity.

    48-AMR/ANH / GPT-6 Astra / 2026-09-20: 中 needs a classified ongoing
    activity; 前/後 also attach to native instantaneous sahen events. Exact
    dictionary nouns, readings and boundaries are shared with written input.
    No spatial/food/object role leaks from the phase or its original host.
    Source: 福沢将樹「時間を表す接尾語について」p.73,
    https://aichi-pu.repo.nii.ac.jp/record/2968/files/8_13.pdf .
    """
    from semantic_roles import ongoing_nominal_support
    found=[]
    for suffix,rd,sub in (('中','ちゅう','接尾:副詞可能'),
                          ('前','まえ','副詞可能'),('後','ご','接尾:副詞可能')):
        if suffix=='中' and not include_ongoing:continue
        for host,kind in _native_suffix_nominal_pairs(text,suffix,rd,sub):
            if (ongoing_nominal_support(host) if suffix=='中' else kind=='サ変接続'):
                found.append(host+suffix)
    return tuple(sorted(set(found)))


@lru_cache(maxsize=4096)
def native_waiting_nominal_faces(text):
    """48-ANK / GPT-6 Astra / 2026-09-20: a native action awaiting its turn.

    A sahen event or classified person and the actual nominal suffix
    待ち prove a whole state noun. Neither a temporal adjunct nor the
    host's argument role is inherited. Other referents remain unclassified.
    Source: NICT EDR technical dictionary, chapter 11 p.22, job queue:
    https://www2.nict.go.jp/ipp/EDR/JPN/TG/Doc/EDR_J11a.pdf .
    """
    # 48-ANW: a person can be the awaited referent of the same suffix.
    # Native ordinary-noun identity and the shared person role are required;
    # a state noun does not itself inherit the awaited person's role.
    # Nikkoku 人待: https://kotobank.jp/word/人待-2077946
    from semantic_roles import nominal_roles
    return tuple(host+'待ち' for host,kind in
                 _native_suffix_nominal_pairs(text,'待ち','まち','接尾:一般')
                 if kind=='サ変接続' or 'person' in nominal_roles(host))


@lru_cache(maxsize=4096)
def native_inchoative_nominal_faces(text):
    """48-ANU: V-continuative + kake is a derived incomplete-action noun.

    GPT-6 Astra / 2026-09-20. Native forms and the same continuative
    attachment prove the whole noun. Neither its action's argument roles
    nor the unrelated lexical senses of kakeru become nominal meanings.
    NINJAL basic-verb handbook, 掛ける, compound nouns; also:
    https://www2.ninjal.ac.jp/vvlexicon/about.html
    """
    if not text or not 3<=len(text)<=24:return ()
    from morphology import dictionary_inflections,Token
    from contextual_repair import _native_continuative_attachment
    for ending in ('かけ','掛け'):
        if not text.endswith(ending) or len(text)<=len(ending):continue
        head=text[:-len(ending)]
        kana=all('ぁ'<=c<='ゖ' or c=='ー' for c in head)
        # Isolated kana かき can select the noun 柿. Native verb forms
        # still prove the same whole continuative compound without changing
        # tokenizer rows or giving the nominal homograph a verbal role.
        for hp,hf,hb,hr in dictionary_inflections(head) or ():
            if not (hp.startswith('動詞,自立,') and hf=='連用形'
                    and (not kana or hr==head)):continue
            first=Token(head,'動詞',hb,hr,0,len(head),True,'自立',hf)
            for pos,form,base,rd in dictionary_inflections(ending) or ():
                if not (pos.startswith('動詞,') and form=='連用形'
                        and base in ('かける','掛ける') and rd=='かけ'):continue
                suffix=Token(ending,'動詞',base,rd,len(head),len(text),True,
                             pos.split(',')[1],form)
                if _native_continuative_attachment(first,suffix):return (text,)
    return ()


@lru_cache(maxsize=4096)
def native_action_value_nominal_faces(text):
    """A native continuative plus gai is a nominal value of that action.

    GPT-6 Astra / 2026-09-22. The original spelling and exact native
    continuative are required; no vocabulary list of eligible verbs.
    NINJAL Corpus Japanese Workshop 2 (2012), kai/gai nominalizing suffix:
    https://repository.ninjal.ac.jp/record/3438/files/JCLWorkshop2012_2_web.pdf
    """
    if not text or not 3<=len(text)<=24:return ()
    from morphology import dictionary_inflections
    ending=next((tail for tail in ('がい','甲斐') if text.endswith(tail)),None)
    if ending is None:return ()
    if not any(pos.startswith('名詞,接尾,一般,') and rd=='がい'
               for pos,form,base,rd in dictionary_inflections('がい') or ()):
        return ()
    if ending=='甲斐' and not any(pos.startswith('名詞,一般,') and rd=='かい'
                for pos,form,base,rd in dictionary_inflections(ending) or ()):
        return ()
    head=text[:-len(ending)]
    kana=all('ぁ'<=c<='ゖ' for c in head)
    if any(pos.startswith('動詞,自立,') and form=='連用形' and (not kana or rd==head)
           for pos,form,base,rd in dictionary_inflections(head) or ()):
        return (text,)
    return ()


@lru_cache(maxsize=4096)
def native_attested_prefix_noun_readings(face):
    """A shipped whole noun with a native prefix and native noun head.

    The shipped unit proves wordhood. Native prefix/head entries or the
    existing on-reading cost-table evidence prove its full pronunciation.
    """
    if not face or len(face)<2 or not ('一'<=face[0]<='龯'):
        return ()
    from seed_japanese import is_unit
    from corrector import _table_readings_for_surface
    from morphology import dictionary_inflections
    from kanji_onkun import readings_of,kind_of
    # A native nominal prefix and the unchanged whole native host already
    # attest the reading; an extra cost-table row is not needed for that
    # exact written lexical unit. Raw tokens avoid restoration recursion.
    from morphology import _tokenize_janome
    parts=_tokenize_janome(face)
    first=parts[0] if parts else None
    native=()
    if (first and first.start==0 and first.end<len(face) and first.has_reading
            and first.pos=='接頭詞' and first.pos_sub=='名詞接続'
            and any(pos.startswith('接頭詞,名詞接続,') and rd==first.reading
                    for pos,form,base,rd in dictionary_inflections(first.surface) or ())):
        host=face[first.end:]
        native=tuple(sorted({first.reading+rd
            for pos,form,base,rd in dictionary_inflections(host) or ()
            if pos.startswith(('名詞,一般,','名詞,サ変接続,')) and base==host and rd}))
    if not is_unit(face):return native
    head=face[1:]
    nouns={rd for pos,form,base,rd in dictionary_inflections(head) or ()
           if pos.startswith(('名詞,一般,','名詞,サ変接続,'))
           and base==head and rd}
    attested=set(_table_readings_for_surface(face))
    return tuple(sorted(set(native) | {rd+tail for rd in readings_of(face[0])
                        if kind_of(face[0],rd)=='on' for tail in nouns
                        if rd+tail in attested}))


@lru_cache(maxsize=4096)
def native_attested_prefix_noun_faces(reading):
    if not reading or not all('ぁ'<=c<='ゖ' or c=='ー' for c in reading):return ()
    from corrector import table_surfaces_for_reading
    from morphology import dictionary_inflections
    faces={face for face in table_surfaces_for_reading(reading,limit=32)
           if reading in native_attested_prefix_noun_readings(face)}
    # A productive native prefix does not require the whole combination
    # to have a separate frequency-table row. Both components still need
    # their exact native POS/reading, and the whole reading is rechecked.
    for cut in range(1,len(reading)):
        prefixes=[face for face in table_surfaces_for_reading(reading[:cut],limit=32)
            if any(pos.startswith('接頭詞,名詞接続,') and rd==reading[:cut]
                   for pos,form,base,rd in dictionary_inflections(face) or ())]
        if not prefixes:continue
        for head in native_lexical_reading_faces(reading[cut:]):
            if not any(pos.startswith(('名詞,一般,','名詞,サ変接続,')) and base==head
                       and rd==reading[cut:] for pos,form,base,rd
                       in dictionary_inflections(head) or ()):continue
            for prefix in prefixes:
                face=prefix+head
                if reading in native_attested_prefix_noun_readings(face):faces.add(face)
    return tuple(sorted(faces))


@lru_cache(maxsize=4096)
def native_written_sahen_relative(text):
    """A complete written sahen relative clause, using native inflection."""
    if not text or len(text)<3 or not native_attributive_predicate_end(text):return False
    from morphology import dictionary_inflections,tokenize
    for cut in range(1,len(text)-1):
        stem,tail=text[:cut],text[cut:]
        noun=any(pos.startswith('名詞,サ変接続,') and base==stem
                 for pos,form,base,rd in dictionary_inflections(stem) or ())
        if not noun and not native_attested_prefix_noun_readings(stem):continue
        parts=tokenize(tail)
        if (not parts or parts[0].start!=0 or parts[-1].end!=len(tail)
                or any(a.end!=b.start for a,b in zip(parts,parts[1:]))
                or not all(t.has_reading for t in parts)):continue
        first=parts[0]
        if not (first.pos=='動詞' and first.pos_sub=='自立'
                and first.base_form=='する'):continue
        if all(t.pos in ('助詞','助動詞') or t.pos=='動詞' and t.pos_sub=='非自立'
               for t in parts[1:]):return True
    return False


@lru_cache(maxsize=2048)
def native_written_sahen_nominal_parts(text):
    """An unchanged written action, literal suru chain and full noun reading.

    This proves the source seam, never the sense or spelling of that noun.
    Both the complete original action and the entire remaining noun must
    exist independently; an internal noun or a broken auxiliary is no proof.
    """
    if not text or not 5<=len(text)<=80:return ()
    from morphology import dictionary_inflections,tokenize,native_sahen_compound_reading
    from contextual_repair import _allows_grammatical_tail
    original_parts=tokenize(text)
    out=[]
    for head_end in range(1,min(18,len(text)-3)+1):
        stem=text[:head_end]
        if not any('一'<=c<='鿿' for c in stem):continue
        if not (any(pos.startswith('名詞,サ変接続,') and base==stem
                    for pos,form,base,rd in dictionary_inflections(stem) or ())
                or native_sahen_compound_reading(stem)):continue
        for noun_start in range(head_end+2,min(head_end+8,len(text)-1)+1):
            # A whole native function token keeps its own attachment.
            # A homophonic noun cannot certify that same complete token;
            # a longer noun spanning several original pieces is separate.
            if any(t.has_reading and t.start==noun_start and t.end==len(text)
                   and t.pos in ('助詞','助動詞') for t in original_parts):continue
            tail=text[head_end:noun_start];parts=tokenize(tail)
            if not parts:continue
            first=parts[0]
            if not (first.start==0 and first.has_reading and first.pos=='動詞'
                    and first.pos_sub=='自立' and first.base_form=='する'):continue
            forms=tuple(row for row in dictionary_inflections(first.surface) or ()
                        if row[0].startswith('動詞,自立,') and row[1]==first.infl_form
                        and row[2]=='する' and row[3]==first.reading)
            if not _allows_grammatical_tail(forms,tail[first.end:],first.reading,first.surface):continue
            if not native_written_sahen_relative(text[:noun_start]):continue
            faces=_native_nominal_reading_faces(text[noun_start:])
            if faces:out.append((head_end,noun_start,faces))
    return tuple(out)


@lru_cache(maxsize=2048)
def native_prefix_sahen_relative_parts(text):
    """The original full prefix noun, actual suru tail and complete noun.

    These are lexical/inflection boundaries, not a homophone decision.
    Unknown following text cannot complete the relative clause's noun.
    """
    if not text or not 7<=len(text)<=60:return ()
    from morphology import native_sahen_compound_reading,tokenize,native_suru_form
    out=[]
    for head_end in range(3,min(18,len(text)-3)+1):
        reading=text[:head_end]
        if not all('ぁ'<=c<='ゖ' or c=='ー' for c in reading):continue
        faces=tuple(face for face in native_attested_prefix_noun_faces(reading)
                    if native_sahen_compound_reading(face)==reading)
        if not faces:continue
        for end in range(head_end+2,min(head_end+8,len(text)-1)+1):
            tail=text[head_end:end];parts=tokenize(tail)
            if not parts:continue
            first=parts[0]
            if not (first.has_reading and first.start==0
                    and first.pos=='動詞' and first.pos_sub=='自立'
                    and first.base_form=='する'
                    and native_suru_form(first.surface,first.infl_form,first.reading,False)):
                continue
            from morphology import dictionary_inflections
            from contextual_repair import _allows_grammatical_tail
            forms=tuple(row for row in dictionary_inflections(first.surface) or ()
                        if row[0].startswith('動詞,自立,') and row[1]==first.infl_form
                        and row[2]=='する' and row[3]==first.reading)
            if not _allows_grammatical_tail(forms,tail[first.end:],first.reading,first.surface):continue
            if not native_nominal_phrase_faces(text[end:]):continue
            proved=tuple(face for face in faces if native_written_sahen_relative(face+tail))
            if proved:out.append((head_end,end,first.end,proved))
    return tuple(out)


@lru_cache(maxsize=4096)
def native_te_nominal_parts(text,allow_following=False):
    """A proved native te clause modifying an actual action noun with no.

    Shared clause/case and action-role evidence applies to the original
    words. This neither drops no nor creates a corrected reading.
    HUSCAP 10.14943/rjgshhs.24.l183, section 2: te-no nominal phrases.
    https://eprints.lib.hokudai.ac.jp/repo/huscap/all/94035/
    """
    if not text or 'の' not in text or not 5<=len(text)<=80:return ()
    from morphology import tokenize
    from semantic_roles import action_note_support
    parts=tokenize(text);out=[]
    for te,no in zip(parts,parts[1:]):
        if not (te.has_reading and no.has_reading and te.end==no.start
                and te.pos==no.pos=='助詞' and te.surface in ('て','で')
                and te.pos_sub=='接続助詞' and no.surface=='の'
                and no.pos_sub=='連体化'):continue
        left=text[:te.end]
        kana=lambda value:all('ぁ'<=ch<='ゖ' or ch=='ー' for ch in value)
        if kana(left):
            action=completed_native_reading_clause(left,allow_nonpolite=True,
                require_object_fit=True,return_action=True)
        else:
            proof=native_written_relative_action(left,allow_link=True)
            action=proof[0] if proof else None
        if not action:continue
        # A spelling unit may end at an actual following case/topic. This
        # proves the same source noun, never the unfinished outer predicate.
        ends={len(text)}
        if allow_following:
            ends.update(t.start for t in parts if t.start>no.end and t.has_reading
                and t.pos=='助詞' and (t.pos_sub.startswith('格助詞:一般')
                    or t.pos_sub=='係助詞' and t.surface in ('は','も')))
        for end in sorted(ends):
            right=text[no.end:end]
            if not right:continue
            if kana(right):heads=native_bare_action_faces(right)
            else:
                tail=tokenize(right)
                heads=((right,) if len(tail)==1 and tail[0].has_reading
                    and native_action_noun_reading(right,tail[0].reading) else ())
            supported=tuple(head for head in heads if action_note_support(action,head))
            if supported:out.append((no.end,end,supported))
    return tuple(dict.fromkeys(out))


@lru_cache(maxsize=4096)
def native_te_nominal_heads(text):
    return tuple(dict.fromkeys(head for start,end,heads in native_te_nominal_parts(text)
                               for head in heads))


@lru_cache(maxsize=4096)
def native_nominal_phrase_faces(text):
    """Return native nominal heads; never produce a replacement spelling."""
    if not text or not 1<=len(text)<=24 or not all('ぁ'<=c<='ゖ' or c=='ー' for c in text):
        return ()
    direct=_native_nominal_reading_faces(text) or native_deverbal_nominal_faces(text)
    if direct:return direct
    te_nominal=native_te_nominal_heads(text)
    if te_nominal:return te_nominal
    linked=native_case_adnominal_parts(text)
    if linked:return tuple(dict.fromkeys(face for a,b,left,right in linked for face in right))
    containers=native_container_nominal_heads(text)
    if containers:return containers
    phased=(native_temporal_nominal_faces(text) or native_waiting_nominal_faces(text)
            or native_inchoative_nominal_faces(text) or native_action_value_nominal_faces(text))
    if phased:return phased
    # 48-AJH: the native adjective + nominalizing さ already used by
    # written-object semantics also proves the unchanged kana noun.
    # Return the literal reading; this selects no alternate kanji spelling.
    if text.endswith('さ'):
        from morphology import tokenize
        def original_parts(value):
            return [(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                     t.start,t.end,t.has_reading,t.infl_form) for t in tokenize(value)]
        if nominalized_adjective_context(text,0,len(text),original_parts):return (text,)
    if native_coordinated_nominal_parts(text):return (text,)
    compound=native_relational_compound_heads(text)
    if compound:return compound
    # A native nominal focus particle preserves its noun's argument roles.
    # しか is deliberately separate: it requires a negative predicate.
    from morphology import tokenize,dictionary_inflections
    focused=native_focused_nominal_parts(text)
    if focused:return focused[1]
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
        else:
            # 48-ALK: a relative action constrains each exact homophone;
            # it does not select the first spelling from the cost table.
            noun=modified[-1][4]
            relative=native_relative_action(text[:-len(noun)])
            if relative:heads+=native_relative_nominal_faces(noun,*relative)
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
    for cut,left,right in native_genitive_nominal_splits(text):
        return right
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
                            subject_faces=None, case_argument=None, allow_open_tail=False, relative_faces=None, finite_only=False):
    """48-ZJ/ZN: a native action reading with an unchanged finite polite tail.

    GPT-6 / 2026-09-11. This proves an inflection without choosing among
    homophonic kanji. The reading table only locates native dictionary
    entries; their exact reading and grammatical form supply the proof.
    It does not treat arbitrary noun pairs as completed predicates.
    """
    if finite_only:allow_open_tail=False
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
        # Frequency is not the source's grammatical POS. Native common
        # nouns retain their exact sahen entry and full suru connection;
        # candidate argument/meaning requirements below remain unchanged.
        for face in dict.fromkeys((*_native_nominal_reading_faces(reading),
                                  *native_common_noun_faces(reading),
                                  *native_bare_action_faces(reading))):
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
                    # The shared attachment check accepts this independently
                    # attested action use without fabricating native POS.
                    forms=[row for row in dictionary_inflections(face) or ()
                           if row[0].startswith('名詞,一般,') and row[3]==reading]
            from morphology import native_sahen_compound_reading
            from general_words import sourced_sahen_noun
            if (not forms and native_sahen_compound_reading(face)!=reading
                    and not sourced_sahen_noun(face,reading)):
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
            if finite_only:
                # The exact native action/tail was just proved. Reuse this
                # lexical reconstruction instead of re-parsing the original
                # all-kana spelling into an unknown terminal token.
                core=native_predicate_finite_core([(t.surface,
                    t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                    t.start,t.end,t.has_reading,t.infl_form) for t in parts])
                if not core or not _completed_predicate_token(core[-1]):continue
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
                        allow_open_tail=allow_open_tail,relative_faces=relative_faces,finite_only=finite_only)
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
                        # The full productive suru chain was checked above;
                        # its native finite aspect verb also completes it.
                        or (last.pos=='動詞' and last.pos_sub.startswith('非自立')
                            and any(pos.startswith('動詞,非自立,') and form==last.infl_form
                                    and base==last.base_form and rd==last.reading
                                    for pos,form,base,rd in dictionary_inflections(last.surface) or ()))
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
    # Bare suru actions have the same native finite/attributive ending as
    # other verbs. Keep their independently attested action identity when
    # the relative clause omits its object (保存した画像), not just when
    # it already contains an explicit case (資料を保存した...).
    verb_head=((completed_native_verb_reading(head,True)
        or completed_sahen_reading(head,allow_nonpolite=True,return_action=True,finite_only=True))
        if attributive else False)
    occupied_cases=()
    if attributive and not verb_head:
        native_parts=tokenize(head)
        # Reuse the source case positions, including cases swallowed
        # by an unknown token. Occupied objects/subjects must remain
        # occupied when the relative head is checked below.
        markers=('を','が','は','も','に','へ','で','から')
        occupied=list((cut,marker)
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
                    occupied.append((cut,marker))
        occupied_cases=tuple(dict.fromkeys(marker for cut,marker in occupied))
        if occupied_cases:
            action=completed_native_reading_clause(head,allow_nonpolite=True,
                require_nominal=True,require_object_fit=True,return_action=True)
            if action:
                verb_head=action
                # Candidate case positions inside an unknown token are not
                # all occupied arguments. The independently proved action
                # owns its complete suffix (including に in かくにん).
                suffix=_native_completed_action_suffix(head,action)
                if suffix:
                    edge=len(head)-len(suffix)
                    occupied_cases=tuple(dict.fromkeys(marker for cut,marker in occupied if cut<edge))
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
                    # A content verb needs its finite inflection for meaning;
                    # a suru action already has its proved canonical noun.
                    # Replacing 保存 with an unknown parse of ほぞんした
                    # would erase that same event's temporal relation.
                    if finite and completed_native_verb_reading(finite,True,False):
                        verb_head=finite
    if not verb_head:
        # Keep the same independently proved adjunct boundary and relative
        # predicate. The adjunct supplies neither the verb nor its case fit.
        for cut in native_adverbial_reading_cuts(head):
            relative=native_relative_action(head[cut:])
            if relative:return relative
    return (verb_head,occupied_cases) if verb_head else ()


def native_adverbial_sahen_relative_parts(text):
    """Share an original adjunct seam only with its complete relative proof.

    The suffix supplies its own whole noun, completed suru and positive
    relation. Returned positions are original boundaries, never spellings
    chosen for output or evidence borrowed between homonymous predicates.
    """
    if not text or not 5<=len(text)<=48:return ()
    from morphology import tokenize,dictionary_inflections
    from semantic_roles import relative_action_support
    kana=lambda value:bool(value) and all('ぁ'<=c<='ゖ' or c=='ー' for c in value)
    for start in native_adverbial_reading_cuts(text):
        suffix=text[start:]
        written=not kana(suffix)
        proof=(native_written_adnominal_parts(suffix) if written else
               native_adnominal_reading_parts(suffix,allow_predicative=True))
        if not proof:continue
        nominal=proof[-1][0] if written else proof[-1][4]
        if not suffix.endswith(nominal):continue
        edge=len(suffix)-len(nominal);head=suffix[:edge]
        if not kana(head) or not native_attributive_predicate_end(head):continue
        nouns=(_native_written_nominal_faces(nominal) if written else
               native_nominal_phrase_faces(nominal))
        relative=native_relative_action(head)
        if not nouns or not relative or relative[1]:continue
        action=completed_sahen_reading(head,allow_nonpolite=True,
            return_action=True,relative_faces=nouns,finite_only=True)
        if not action or not all(relative_action_support(n,action) for n in nouns):continue
        for pos,form,base,reading in dictionary_inflections(action) or ():
            if not (pos.startswith('名詞,サ変接続,') and base==action and reading
                    and head.startswith(reading) and len(reading)<len(head)):continue
            prefix=tuple((t.surface,t.pos+','+t.pos_sub.replace(':',','),
                t.infl_form,t.base_form,t.reading) for t in tokenize(text[:start]))
            if not prefix or ''.join(p[4] for p in prefix)!=text[:start]:continue
            return start,start+len(reading),start+edge,prefix+proof
    return ()


@lru_cache(maxsize=2048)
def native_written_adnominal_parts(text):
    """Same native adjective/adnominal proof with its unchanged written noun.

    Project only the final noun's actual dictionary reading. The returned
    nominal face must equal that original word, not another homophone.
    Unknown nouns, noun fragments and finite predicate tails cannot qualify.
    """
    if not text or not 3<=len(text)<=48 or not any('一'<=c<='鿿' for c in text):return ()
    adverbial=native_adverbial_sahen_relative_parts(text)
    if adverbial:return adverbial[3]
    from morphology import tokenize,dictionary_inflections
    parts=tokenize(text)
    if not parts:return ()
    noun=parts[-1];head=text[:noun.start]
    if (not noun.has_reading or noun.pos!='名詞' or noun.end!=len(text)
            or noun.start<2
            or not any(pos.startswith('名詞,') and rd==noun.reading
                       and not any(kind in pos for kind in ('固有名詞','接尾','非自立'))
                       for pos,form,base,rd in dictionary_inflections(noun.surface) or ())):return ()
    # The same exact modifier proof already protects source ranges. Its
    # original spelling need not be kana, and the written noun supplies its
    # own full lexical boundary without a synthetic kana segmentation.
    # This establishes syntax only, not a new meaning or commonness tier.
    modifier=native_adnominal_modifier_parts(head,allow_written=True)
    nouns=[(noun.surface,pos,form,base,rd)
           for pos,form,base,rd in dictionary_inflections(noun.surface) or ()
           if pos.startswith('名詞,') and rd==noun.reading
           and not any(kind in pos for kind in ('固有名詞','接尾','非自立'))]
    if modifier and nouns:return modifier+(nouns[0],)
    if (nouns and all('ぁ'<=c<='ゖ' or c=='ー' for c in head)
            and native_attributive_predicate_end(head)):
        relative=native_relative_action(head)
        if relative and not relative[1]:
            # The exact written noun constrains the original completed
            # sahen reading. Its spelling and open object stay the same.
            # These dictionary parts prove source grammar, not output text.
            from semantic_roles import relative_action_support
            faces=tuple(dict.fromkeys(row[0] for row in nouns))
            action=completed_sahen_reading(head,allow_nonpolite=True,
                return_action=True,relative_faces=faces,finite_only=True)
            if action and all(relative_action_support(face,action) for face in faces):
                return tuple((t.surface,t.pos+','+t.pos_sub.replace(':',','),
                    t.infl_form,t.base_form,t.reading) for t in tokenize(head))+(nouns[0],)
    # The written noun already supplies its own boundary. A synthetic
    # all-kana parse must not swallow its first syllable into an adverb.
    # Keep this actual basic adjective and the exact ordinary noun entry.
    if (len(parts)==2 and parts[0].start==0 and parts[0].end==noun.start
            and parts[0].has_reading and parts[0].pos=='形容詞'
            and parts[0].pos_sub=='自立' and parts[0].infl_form=='基本形'):
        from morphology import native_independent_adjective
        modifiers=[(head,pos,form,base,rd) for pos,form,base,rd in dictionary_inflections(head) or ()
                   if rd==head and native_independent_adjective(pos,form,base)]
        nouns=[(noun.surface,pos,form,base,rd) for pos,form,base,rd in dictionary_inflections(noun.surface) or ()
               if pos.startswith('名詞,') and rd==noun.reading
               and not any(kind in pos for kind in ('固有名詞','接尾','非自立'))]
        if modifiers and nouns:return (modifiers[0],nouns[0])
    proof=native_adnominal_reading_parts(head+noun.reading)
    if (proof and proof[-1][0]==noun.surface and proof[-1][4]==noun.reading
            and ''.join(row[4] for row in proof[:-1])==head):return proof
    return ()


@lru_cache(maxsize=4096)
def native_adnominal_reading_parts(text, allow_predicative=False):
    """48-ZQ: native adjective/adnominal + ordinary noun in the same reading.

    GPT-6 / 2026-09-11. Returned spellings only carry dictionary evidence;
    they are never chosen as output text. A case or a finite tail cannot be
    reinterpreted as a modifier. Unknown readings supply no positive proof.
    """
    if not text or len(text)<3 or not all('ぁ'<=c<='ゖ' or c=='ー' for c in text):
        return ()
    if allow_predicative:
        adverbial=native_adverbial_sahen_relative_parts(text)
        if adverbial:return adverbial[3]
    from corrector import table_surfaces_for_reading
    from morphology import dictionary_inflections, native_independent_adjective, tokenize
    def entries(reading):
        # A proved modifier is grammatical context for the existing short
        # ordinary-noun reading index. Do not export one-kana readings to
        # free lexical search or infer a new noun from the modifier alone.
        from semantic_roles import short_role_noun_faces
        for face in dict.fromkeys((reading,*table_surfaces_for_reading(reading,limit=12),
                                   *short_role_noun_faces(reading))):
            for pos,form,lemma,rd in dictionary_inflections(face) or ():
                if rd==reading:
                    yield face,pos,form,lemma,rd
    for cut in range(2,len(text)):
        head,noun=text[:cut],text[cut:]
        # Both adjective and relative-clause paths require the same
        # native noun suffix. Reject absent suffixes before parsing all
        # possible relative clauses in the prefix.
        from kango_tier import usage_tier_for_reading
        nouns=[row for row in entries(noun) if row[1].startswith('名詞,')
               and usage_tier_for_reading(row[0],row[4]) in (1,2)
               and not any(kind in row[1] for kind in ('固有名詞','接尾','非自立'))]
        polite=native_polite_nominal_parts(noun) if not nouns else ()
        if not nouns and not polite:continue
        modifier=native_adnominal_modifier_parts(head,allow_predicative)
        modifiers=[modifier] if modifier else []
        relative=native_relative_action(head) if allow_predicative and nouns and not modifiers else ()
        verb_head,occupied_cases=relative if relative else (False,())
        verb_parts=tokenize(head) if verb_head else []
        if not modifiers and not verb_head:
            continue
        result=modifiers[0]+((nouns[0],) if nouns else polite[0]) if modifiers and (nouns or polite) else ()
        if not result and verb_head:
            from semantic_roles import relative_action_support
            verb_nouns=[row for row in nouns if relative_action_support(row[0],verb_head,occupied_cases)]
            if not verb_nouns and not occupied_cases:
                # The first grammatical homophone is not a semantic choice.
                # Reuse the native complete suru proof conditioned on the
                # original noun readings, binding their positive relation
                # to that same proved action. This returns source grammar,
                # not the selected kanji spelling of the predicate.
                action=completed_sahen_reading(head,allow_nonpolite=True,
                    return_action=True,relative_faces=tuple(row[0] for row in nouns),
                    finite_only=True)
                if action and all(relative_action_support(row[0],action)
                                  for row in nouns):verb_nouns=nouns
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



def _native_nominal_copula_tail(face,tail,connective='',conditional=False):
    """Validate a copula after an independently proved original nominal head.

    The caller owns the noun evidence. Source-only honorifics can therefore
    reuse the exact native auxiliary proof without becoming candidate nouns.
    """
    from morphology import tokenize
    from pos_grammar import _NOUN_PRED
    from contextual_repair import _completed_predicate_token
    finite={piece for piece,state in _NOUN_PRED if state in ('END','TA')}
    if connective=='ので':finite=(finite-{'だ'})|{'な'}
    if conditional:finite={'なら'}
    parts=[t for t in tokenize(face+tail+connective) if t.start>=len(face)]
    if connective:
        if (not parts or parts[-1].surface!=connective or not parts[-1].has_reading
                or parts[-1].pos!='助詞' or parts[-1].pos_sub!='接続助詞'
                or parts[-1].start!=len(face)+len(tail)):return False
        parts.pop()
    if (not parts or parts[0].start!=len(face)
            or not all(t.has_reading for t in parts)
            or ''.join(t.surface for t in parts)!=tail):return False
    from particle_frames import native_final_particle_sequence
    final=[]
    while not connective and parts and parts[-1].pos=='助詞' and '終助詞' in parts[-1].pos_sub:
        final.insert(0,parts.pop())
    if not native_final_particle_sequence(final):return False
    # GPT-6 Astra / 2026-09-21: native Nな/だった + の/ん + copula.
    # https://www.kyozai.jpf.go.jp/kyozai/material/BTS00120/ja/render.do
    # https://www.jpf.go.jp/j/project/japanese/teach/tsushin/grammar/201006.html
    if not connective and not conditional:
        for i,marker in enumerate(parts):
            if not (marker.surface in ('の','ん') and marker.pos=='名詞'
                    and marker.pos_sub.startswith('非自立')):continue
            left=parts[:i];plain=''.join(t.surface for t in left)
            present=(len(left)==1 and plain=='な' and left[0].base_form=='だ'
                     and left[0].infl_form=='体言接続')
            past=(plain in {piece for piece,state in _NOUN_PRED if state=='TA'}
                  and all(t.pos=='助動詞' for t in left)
                  and left[-1].base_form=='た' and left[-1].infl_form=='基本形')
            if present or past:parts=parts[i+1:]
            break
    if (not parts or ''.join(t.surface for t in parts) not in finite
            or not all(t.pos=='助動詞' for t in parts)):return False
    last=parts[-1]
    if connective=='ので' and tail=='な':
        return (len(parts)==1 and last.surface=='な' and last.base_form=='だ'
                and last.infl_form=='体言接続')
    if conditional:
        return len(parts)==1 and last.base_form=='だ' and last.infl_form=='仮定形'
    legacy=(last.surface,last.pos,last.reading,last.start,last.end,last.has_reading,last.infl_form)
    return _completed_predicate_token(legacy)


@lru_cache(maxsize=2048)
def native_nominal_comparison_head(text):
    """The same attested irregular comparison head, without changing its text."""
    from morphology import tokenize
    parts=tokenize(text)
    head=parts[0] if parts else None
    if (head and head.start==0 and head.has_reading
            and head.base_form in ('同じ','おなじ') and head.reading=='おなじ'
            and (head.pos=='連体詞' or head.pos=='名詞' and head.pos_sub in ('一般','形容動詞語幹'))):
        return head
    return None


@lru_cache(maxsize=4096)
def completed_native_nominal_predicate(text, allow_topic=True, connective='', conditional=False, allow_written=False, nominal_end=None):
    """An exact native noun and copula in its actual connective context.

    48-AMU / GPT-6 Astra / 2026-09-20: Nなので uses the same nominal
    head as the finite predicate, with native だ/体言接続. This mode is
    connective evidence, not a completed standalone candidate.
    https://www.coelang.tufs.ac.jp/mt/ja/gmod/courses/c01/lesson21/step1/explanation/081.html
    """
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    if not bare or not 2<=len(bare)<=40:return False
    if not allow_written and not all('ぁ'<=c<='ゖ' or c=='ー' for c in bare):return False
    noun_faces=native_surface_nominal_heads if allow_written else native_nominal_phrase_faces
    from morphology import tokenize
    from pos_grammar import _NOUN_PRED
    finite={piece for piece,state in _NOUN_PRED if state in ('END','TA')}
    if connective=='ので':finite=(finite-{'だ'})|{'な'}
    if conditional:finite={'なら'}
    if allow_topic and nominal_end is None:
        for particle in tokenize(bare):
            nominative=(particle.surface=='が' and particle.pos_sub.startswith('格助詞'))
            topic=(particle.surface in ('は','も') and particle.pos_sub.startswith('係助詞'))
            # GPT-6 Astra / 2026-09-21: Nと同じ compares an attested
            # nominal argument with the same native nominal predicate.
            # The dictionary's irregular adnominal/na-adjective keeps its
            # actual reading and full finite tail; no word or repair is made.
            # https://www.coelang.tufs.ac.jp/mt/ja/gmod/contents/explanation/053.html
            # General/quotative と has the same native particle boundary.
            # The attested noun plus 同じ and its finite tail prove this use.
            comparison=(particle.surface=='と' and particle.pos_sub.startswith('格助詞'))
            if comparison:
                comparison=bool(native_nominal_comparison_head(bare[particle.end:]))
            if (particle.pos=='助詞' and particle.has_reading and (nominative or topic or comparison)
                    and noun_faces(bare[:particle.start])
                    and completed_native_nominal_predicate(bare[particle.end:],allow_topic=False,connective=connective,conditional=conditional,allow_written=allow_written)):
                return True
    for cut in ((nominal_end,) if nominal_end is not None else range(1,len(bare))):
        if not 0<cut<len(bare):continue
        tail=bare[cut:]
        if not (any(tail.startswith(piece) for piece in finite)
                or not connective and not conditional and tail.startswith('な')):continue
        faces=noun_faces(bare[:cut])
        if not faces and allow_written:
            comparison_head=native_nominal_comparison_head(bare[:cut])
            if comparison_head is not None and comparison_head.end==cut:
                faces=(comparison_head.surface,)
        if not faces:
            modifier=native_adnominal_reading_parts(bare[:cut],allow_predicative=True)
            if modifier:faces=(''.join(part[0] for part in modifier),)
        for face in faces:
            if _native_nominal_copula_tail(face,tail,connective,conditional):return True
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
    return bool(bare in _seed_nominal_readings() or native_te_nominal_heads(bare)
                or native_relational_compound_heads(bare)
                or native_katakana_nominal_face(bare)
                or native_adnominal_reading_parts(bare) or completed_native_nominal_predicate(text)
                or completed_native_reading_clause(text)
                # 48-ANM / GPT-6 Astra / 2026-09-20: a finite native
                # content verb uses the same attachment and meaning proof
                # here as inside a clause. An open te/de link is separate.
                or completed_native_verb_reading(bare,allow_nonpolite=True,finite_only=True)
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


@lru_cache(maxsize=4096)
def native_nominal_case_reading(particle):
    """The same native case/topic entry used by full boundary validation."""
    from morphology import dictionary_inflections
    return any(pos.startswith(('助詞,格助詞,一般,','助詞,係助詞,')) and rd==particle
               for pos,form,base,rd in dictionary_inflections(particle) or ())


def native_nominal_case_boundary(source,original,cut,particle,faces,allow_known_noun=False,
                                 allow_compound_case=False):
    """Shared actual/unknown-source case proof; never use a changed reading.

    Return the projected native noun, if one was needed, and the existing
    special nominative reopening flag. None means no affirmative boundary.
    """
    from morphology import tokenize,dictionary_inflections
    size=len(particle)
    from morphology import kana_syllable_boundary
    if (not kana_syllable_boundary(source,cut)
            or not kana_syllable_boundary(source,cut+size)):return None
    if not native_nominal_case_reading(particle):return None
    if any(t.start==cut and t.end==cut+size and t.has_reading and t.pos=='助詞'
           and t.pos_sub.startswith(('格助詞:一般','係助詞')) for t in original):
        return None,False
    if allow_compound_case and particle in ('に','へ') and faces and any(
            t.start==cut and t.has_reading and t.pos=='助詞' and t.pos_sub.startswith('格助詞')
            and t.surface.startswith(particle) and len(t.surface)>size for t in original):
        # The complete source object/action and this noun's case role must
        # independently support reopening にて as に + てがみ, etc.
        return faces[0],True
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
    # An actual compound connective can absorb a known noun's final
    # kana (じし / んで). A whole original noun and projected case are
    # required, and callers must retain their positive case-role proof.
    if allow_compound_case and any(t.has_reading and t.pos=='助詞'
            and t.pos_sub=='接続助詞' and t.start<cut<t.end
            and t.end==cut+size and t.surface.endswith(particle) for t in original):
        strict_case_fit=True
    if allow_known_noun and particle=='に' and faces and any(
            t.has_reading and t.start==cut and t.end==cut+size and t.pos=='助詞'
            and t.pos_sub=='副詞化' for t in original):
        # 48-ALF: a whole noun reading can also be an adverb (あに).
        # Reproject the unchanged native noun + に below; the caller must
        # prove the same completed action's positive recipient/location role.
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
    # 2026-09-20 / GPT-6 Astra: an exact cardinal person count + で
    # denotes the participating group. A prefix-only best parse can label
    # this で as copular; neither that parse nor a following し removes
    # the attested counter/particle relation. Keep strict action checking.
    # Native counting paradigm; usage: https://www.irodori.jpf.go.jp/faq.html
    if particle=='で' and ('人',False) in native_counted_nominal_evidence(source[:cut]):
        for face in faces:
            if ('人',False) in native_counted_nominal_evidence(face):
                return face,True
    if not swallowed and not strict_case_fit:return None
    for face in faces:
        prefix=tokenize(face+particle)
        if (prefix and prefix[-1].start==len(face) and prefix[-1].end==len(face)+size
                and prefix[-1].has_reading and prefix[-1].pos=='助詞'
                and prefix[-1].pos_sub.startswith(('格助詞:一般','係助詞'))):
            return face,strict_case_fit
    return None


@lru_cache(maxsize=4096)
def _native_honorific_action_heads(text,allow_open=False,humble=False):
    """Shared お + continuative / ご + sahen with an attested honorific tail.

    The prefix and lexical head do not change between a request and a
    humble action. Each tail supplies its own native completion proof.
    """
    if (not text or not 3<=len(text)<=24 or text[0] not in 'おご'
            or not all('ぁ'<=c<='ゖ' or c=='ー' for c in text)):return ()
    from morphology import tokenize,dictionary_inflections
    prefix=text[0]
    if not any(pos.startswith('接頭詞,名詞接続,') and rd==prefix
               for pos,form,base,rd in dictionary_inflections(prefix) or ()):return ()
    body=text[1:];heads=[]
    for cut in range(1,len(body)+1):
        stem,tail=body[:cut],body[cut:]
        if humble:
            if not _native_humble_tail(tail):continue
        elif not tail:
            if not allow_open:continue
        else:
            parts=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                    t.start,t.end,t.has_reading,t.infl_form) for t in tokenize(tail)]
            if not _native_request_tail(native_predicate_finite_core(parts)):continue
        if prefix=='お':
            if any(pos.startswith('動詞,自立,') and form=='連用形' and rd==stem
                   for pos,form,base,rd in dictionary_inflections(stem) or ()):
                heads.append(stem)
        else:
            heads.extend(native_bare_action_faces(stem))
    return tuple(dict.fromkeys(heads))



@lru_cache(maxsize=2048)
def native_honorific_stem_parts(text):
    """Original honorific grammar owns its stem despite a pronoun best parse."""
    from morphology import tokenize,dictionary_inflections
    starts={0}|{p.end for p in tokenize(text) if p.has_reading and p.pos=='助詞'
        and p.pos_sub.startswith('格助詞')}
    found=[]
    for start in sorted(starts):
        suffix=text[start:]
        if not suffix.startswith('お'):continue
        for head in native_humble_action_heads(suffix)+native_honorific_request_heads(suffix):
            if not suffix[1:].startswith(head):continue
            forms=tuple(row for row in dictionary_inflections(head) or ()
                if row[0].startswith('動詞,自立,') and row[1]=='連用形' and row[3]==head)
            if forms:found.append((start+1,start+1+len(head),forms))
    return tuple(found)


def native_honorific_request_heads(text,allow_open=False):
    return _native_honorific_action_heads(text,allow_open=allow_open)


def native_humble_action_heads(text):
    return _native_honorific_action_heads(text,humble=True)


@lru_cache(maxsize=2048)
def _native_humble_tail(text):
    """An exact native いたす inflection with a complete unchanged tail.

    GPT-6 Astra / 2026-09-24, Bunkacho: お(ご)…いたす.
    https://www.bunka.go.jp/seisaku/kokugo_nihongo/kokugo_shisaku/keigo/chapter4/detail.html
    Written projection only resolves the adjective homograph いたし;
    it supplies neither a new reading nor a changed output spelling.
    """
    if not text or not text.startswith('いた'):return False
    from morphology import dictionary_inflections
    for cut in range(2,min(len(text),5)+1):
        reading=text[:cut]
        for face in dict.fromkeys((reading,*native_lexical_reading_faces(reading))):
            if not any(pos.startswith('動詞,') and base in ('いたす','致す') and rd==reading
                       and not form.startswith('命令')
                       for pos,form,base,rd in dictionary_inflections(face) or ()):continue
            if _completed_native_verb_surface(face+text[cut:],True,False,True):return True
    return False


@lru_cache(maxsize=4096)
def completed_native_verb_reading(text, allow_nonpolite=False, require_roles=True, finite_only=False):
    """Return a known content-verb head with the actual unchanged native tail.

    The same modern inflection and positive semantic roles used by nominal
    clauses apply to ordinary verbs, including a finite relative modifier.
    This does not infer grammar from the last kana or an unknown dictionary row.
    """
    if not text or not all('ぁ'<=c<='ゖ' or c=='ー' for c in text):return False
    from morphology import tokenize,dictionary_inflections
    from semantic_roles import native_verb_roles,VERB_ROLES
    for request in (native_humble_action_heads(text)
            + (() if finite_only else native_honorific_request_heads(text))):
        if (not require_roles or request in VERB_ROLES
                or native_verb_roles(request,'連用形',request)
                or native_verb_roles(request,'連用形',request,subject=True)):
            return request
    if allow_nonpolite and not require_roles and not finite_only and text.endswith(('て','で')):
        # Source-only bare links can have a native noun homograph (貝で /
        # 嗅いで). Exact verb inflection and modern euphony establish the
        # unedited reading without selecting a kanji or inventing context.
        stem=text[:-1]
        if any(pos.startswith('動詞,自立,') and rd==stem
               and form.startswith('連用')
               for pos,form,base,rd in dictionary_inflections(stem) or ()):
            from contextual_repair import _modern_te_allowed
            if _modern_te_allowed(stem,stem,text[-1]) is True:return text
    if _completed_native_verb_surface(text,allow_nonpolite,require_roles,finite_only):
        return text
    # 48-ANP / GPT-6 Astra / 2026-09-20: kana のみきる can be parsed
    # as a particle plus an unrelated verb. Project only an independently
    # attested verb head with the exact original reading. The whole native
    # tail, inflection and semantic-role proof are shared with the direct
    # path. No spelling is proposed and no unknown stem gains a reading.
    original=tokenize(text)
    for cut in range(1,len(text)):
        reading=text[:cut]
        for face in native_lexical_reading_faces(reading):
            if face==reading:continue
            forms=tuple((form,base) for pos,form,base,rd in dictionary_inflections(face) or ()
                        if pos.startswith('動詞,自立,') and rd==reading)
            if not forms:continue
            projected=face+text[cut:]
            parts=tokenize(projected)
            if (not parts or parts[0].surface!=face or parts[0].reading!=reading
                    or (parts[0].infl_form,parts[0].base_form) not in forms):continue
            # Recover a swallowed/fragmented head, not a different native
            # inflection of an already intact original verb at this edge.
            if (original and original[0].has_reading and original[0].pos=='動詞'
                    and original[0].pos_sub=='自立' and original[0].end==cut
                    and parts[0].infl_form!=original[0].infl_form):continue
            if _completed_native_verb_surface(projected,allow_nonpolite,require_roles,finite_only):
                return text
    return False


def _completed_native_verb_surface(text,allow_nonpolite,require_roles,finite_only):
    """Exact native predicate proof shared by literal and attested spelling."""
    from morphology import tokenize
    from contextual_repair import (_productive_predicate,_completed_predicate_token,
        _native_imperative_completion)
    from semantic_roles import native_verb_roles
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
    finite=bool(core and (_completed_predicate_token(core[-1])
        or allow_nonpolite and _native_imperative_completion(parts[:len(core)])))
    if finite_only and not finite:return False
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
    from semantic_roles import nominal_role_matches
    if not text or not 4<=len(text)<=30 or not all('ぁ'<=c<='ゖ' for c in text):return False
    from morphology import tokenize,dictionary_inflections
    from semantic_roles import resultative_adjective_roles
    for cut in range(2,min(15,len(text)-1)):
        adjective,predicate=text[:cut],text[cut:]
        if not any(nominal_role_matches(face,resultative_adjective_roles(adjective)) for face in object_faces):continue
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
    from semantic_roles import nominal_role_matches
    source=text
    if text and text[-1] in '。！？.!?':
        text=text[:-1]
    if not text or not all('ぁ'<=c<='ゖ' or c=='ー' for c in text):
        return False
    if not require_nominal:
        action=completed_sahen_reading(text,allow_nonpolite=allow_nonpolite,
            return_action=return_action,action_note_following=action_note_following,
            allow_open_tail=allow_open_tail)
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
        # Test the already-required case inventory before building noun
        # interpretations for every prefix. Keep the three existing
        # boundary-recovery branches even if native case lookup fails.
        particles=tuple(text[cut:cut+size] for size in range(1,min(4,len(text)-cut)+1)
            if text[cut:cut+size] not in seen_cases and (
                text[cut:cut+size] in ('に','へ','と')
                or native_nominal_case_reading(text[cut:cut+size])))
        if not particles:continue
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
        for particle in particles:
            size=len(particle)
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
                if (particle in ('に','へ') and native_nominal_case_boundary(source,
                        original,cut,particle,faces,allow_compound_case=True) is not None):
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
                        if any(nominal_role_matches(face,roles) for face in faces):
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
            from semantic_roles import proved_action_case_support
            for request in (native_honorific_request_heads(text[cut+size:],allow_open=allow_open_tail)
                    + native_humble_action_heads(text[cut+size:])):
                if any(proved_action_case_support(face,particle,request) for face in object_faces):
                    return request if return_action else True
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
                adverb_faces=tuple(object_faces)
                if particle=='を' and needs_case_fit:
                    # Keep a typed original quantity attached to this noun,
                    # even when the following request accepts any object.
                    from semantic_roles import counted_object_roles
                    quantity_roles=counted_object_roles(remainder[:adverb_end])
                    if quantity_roles is not None:
                        # 48-ALR: the same noun sense must satisfy both the
                        # counter and the verb; two homophones cannot split
                        # these roles (資料/飼料 before 冊 + 食べる).
                        adverb_faces=tuple(face for face in object_faces
                                          if nominal_role_matches(face,quantity_roles))
                        if not adverb_faces:continue
                action=completed_native_reading_clause(text[:cut+size]+remainder[adverb_end:],
                    allow_nonpolite=allow_nonpolite,require_nominal=True,
                    require_object_fit=True,modifier_reading=modifier_reading,
                    return_action=return_action,action_note_following=action_note_following,
                    nominal_constraint=(reading,adverb_faces),modifier_constraint=modifier_constraint,
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
            # reading-established nominal head. The proved nominative also
            # supplies the exact boundary for native one-kana い + ます;
            # no bare one-kana word is added to BASIC_VERB_FORMS. Require
            # the actual source case plus a complete basic verb/auxiliaries;
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
                            explicit_nominal_case=(particle in ('を','が')),
                            content_object_faces=object_faces if particle=='を' else None,
                            content_subject_faces=object_faces if needs_case_fit and particle=='が' else None,
                            strict_subject_fit=strict_case_fit,
                            content_case_argument=(particle,object_faces) if particle in ('に','へ','で','と','から') else None,
                            allow_connective=allow_nonpolite,allow_open_tail=allow_open_tail,
                            source_prefix=case_face if case_face is not None else text[:cut]):
                        return tail[1].surface if return_action else True
    return False


@lru_cache(maxsize=4096)
def completed_native_link_clause(text, allow_unclassified=False,
                                 require_nominal=False, nominal_constraint=None):
    """A complete linked clause, retaining any original nominal constraint.

    An independently proved suru action can have an unknown best parse.
    Its exact native reading supplies the finite tail; a te/de connective
    remains an open link even when the whole clause has positive meanings.
    """
    if not text or len(text)>80:return False
    from morphology import tokenize
    from contextual_repair import _completed_predicate_token,_native_imperative_completion
    action=completed_native_reading_clause(text,allow_nonpolite=True,
        require_nominal=bool(require_nominal or nominal_constraint is not None),
        require_object_fit=True,nominal_constraint=nominal_constraint,return_action=True)
    tail=_native_completed_action_suffix(text,action) if action else ''
    parts=tokenize(tail or text)
    legacy=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
             t.start,t.end,t.has_reading,t.infl_form) for t in parts]
    core=native_predicate_finite_core(legacy)
    finite=bool(core and (_completed_predicate_token(core[-1])
        or _native_imperative_completion(parts[:len(core)])))
    if action and (finite or tail and completed_sahen_reading(tail,
            allow_nonpolite=True,return_action=True,finite_only=True)==action):return True
    if require_nominal or nominal_constraint is not None:return False
    return bool(completed_native_nominal_predicate(text)
                or native_adverbial_predicate_reading(text,allow_open_tail=False,finite_only=True)
                or allow_unclassified and completed_native_verb_reading(text,True,
                    require_roles=False,finite_only=True))


@lru_cache(maxsize=4096)
def native_ba_finite_forms(text):
    """Exact native hypothetical form + ba, projected only for clause proof.

    GPT-6 Astra / 2026-09-21. TUFS Japanese Grammar 083:
    https://www.coelang.tufs.ac.jp/mt/ja/gmod/contents/explanation/083.html
    No literal suffix rewrite, changed reading, or guessed word is supplied.
    """
    if not 3<=len(text)<=80 or not text.endswith('ば'):return ()
    from morphology import tokenize,dictionary_inflections
    if not any(pos.startswith('助詞,接続助詞,') and rd=='ば'
               for pos,form,base,rd in dictionary_inflections('ば') or ()):
        return ()
    parts=tokenize(text);end=len(text)-1
    if any(t.has_reading and t.start<end<t.end for t in parts):return ()
    out=[]
    for start in range(end):
        if any(t.has_reading and t.start<start<t.end for t in parts):continue
        stem=text[start:end]
        literal=all('ぁ'<=c<='ゖ' or c=='ー' for c in stem)
        for pos,form,base,reading in dictionary_inflections(stem) or ():
            if (form!='仮定形' or not pos.startswith(('動詞,自立,','助動詞,'))
                    or literal and reading!=stem):continue
            for root_pos,root_form,root_base,root_reading in dictionary_inflections(base) or ():
                if (root_form!='基本形' or root_base!=base or root_pos!=pos):continue
                finite=text[:start]+(root_reading if literal else base)
                # The finite form proves this original verb, not a new word
                # formed by merging its prefix (あ + おう must not become 会おう).
                if any(t.has_reading and t.start<start<t.end for t in tokenize(finite)):continue
                if finite not in out:out.append(finite)
    return tuple(out)


@lru_cache(maxsize=4096)
def completed_native_reading_link(text, require_nominal=False, nominal_constraint=None,
                                  allow_unclassified=False):
    """A complete native clause plus its written connective, with no edits.

    Shared by sequence protection and the source boundaries of later-clause
    candidates. Proving a later object never certifies a malformed first clause.
    """
    # The same completed finite clause proves its native ba connection;
    # its original object constraint is retained through the projection.
    for finite in native_ba_finite_forms(text):
        if (completed_native_reading_clause(finite,allow_nonpolite=True,
                require_object_fit=True,require_nominal=require_nominal,
                nominal_constraint=nominal_constraint)
                or not require_nominal and nominal_constraint is None
                and completed_native_link_clause(finite,allow_unclassified)):
            return True
    # 48-AND / GPT-6 Astra / 2026-09-20: native conditional auxiliaries
    # already supply a clause connection. Prove the unchanged stem and its
    # arguments using the corresponding finite inflection; no output is built.
    # TUFS Japanese Grammar 083 (conditions), 094 (connective particles).
    if text.endswith(('たら','だら','なら','たらば','だらば','ならば')):
        # 48-ANL: a whole noun's kana can swallow なら in the best parse.
        # Reuse the exact noun+copula proof, including the actual optional
        # connective ば; ordinary finite candidates never use this mode.
        if (text.endswith(('なら','ならば')) and not require_nominal and nominal_constraint is None
                and completed_native_nominal_predicate(text[:-1] if text.endswith('ならば') else text,
                    connective='ば' if text.endswith('ならば') else '',conditional=True)):
            return True
        from morphology import tokenize
        from contextual_repair import _self_contained_conditional,_modern_euphonic_link
        parts=tokenize(text)
        last=parts[-1] if parts else None
        end=len(text)
        # 48-ANE: native conditional + optional 接続助詞ば is one link.
        # Shogakukan Daijisen/Nikkoku たら/だ: https://kotobank.jp/word/たら-563172
        # and https://kotobank.jp/word/だ-556047 . A lexical ばね is not
        # removed: both the unchanged conditional and next clause need proof.
        if (last and last.has_reading and last.surface=='ば' and last.pos=='助詞'
                and last.pos_sub=='接続助詞' and len(parts)>1):
            end=last.start;last=parts[-2]
        elif (last and not last.has_reading and text.endswith(('たらば','だらば','ならば'))
                and not any(t.has_reading and t.start<end-1<t.end for t in parts)):
            from morphology import dictionary_inflections
            if any(pos.startswith('助詞,接続助詞,') and rd=='ば'
                   for pos,form,base,rd in dictionary_inflections('ば') or ()):
                end-=1;last=None
        if (last is None or not last.has_reading) and end>2:
            # An unknown parse may swallow the actual conditional auxiliary.
            # Reuse its exact native form and the existing finite-clause
            # reconstruction below. Never split a known word at either edge.
            begin=end-2;surface=text[begin:end]
            if not any(t.has_reading and (t.start<begin<t.end or t.start<end<t.end) for t in parts):
                from morphology import dictionary_inflections,Token
                for pos,form,base,rd in dictionary_inflections(surface) or ():
                    if rd!=surface:continue
                    native=(surface,pos.split(',')[0],rd,begin,end,True,form)
                    if _self_contained_conditional(native):
                        last=Token(surface,pos.split(',')[0],base,rd,begin,end,True,'',form)
                        break
        if last and last.start>0 and last.end==end:
            actual=(last.surface,last.pos+(':'+last.pos_sub if last.pos_sub else ''),
                    last.reading,last.start,last.end,last.has_reading,last.infl_form)
            if _self_contained_conditional(actual):
                prefix=text[:last.start]
                past=_modern_euphonic_link(last.surface,actual[1],last.infl_form)
                finite=(prefix+past,) if past else ()
                if not past and last.base_form=='だ':
                    # Nominal なら corresponds to Nだ, while Vなら keeps the
                    # original finite V. Never certify V+だ by that projection.
                    prior=tokenize(prefix)
                    plain_copula=bool(prior and prior[-1].pos=='助動詞'
                        and prior[-1].base_form=='だ' and prior[-1].infl_form=='基本形'
                        and completed_native_nominal_predicate(prefix))
                    if not plain_copula and native_attributive_predicate_end(prefix):finite=(prefix,)
                for clause in finite:
                    if (completed_native_reading_clause(clause,allow_nonpolite=True,
                            require_object_fit=True,require_nominal=require_nominal,
                            nominal_constraint=nominal_constraint)
                            or not require_nominal and nominal_constraint is None
                            and completed_native_link_clause(clause,allow_unclassified)):
                        return True
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
        from morphology import dictionary_inflections
        if link=='ので' and not require_nominal and nominal_constraint is None:
            # Plain copular だ is attributive な before ので; polite and
            # past finite copulas retain their actual forms. Native POS
            # alone would also parse the invalid Nだので as auxiliaries.
            if (completed_native_nominal_predicate(predicate,connective='ので')
                    and any(p.startswith('助詞,接続助詞,') and rd==link
                            for p,f,b,rd in dictionary_inflections(link) or ())
                    and not any(t.has_reading and t.start<len(predicate)<t.end for t in actual)):
                return True
            if predicate.endswith('だ') and completed_native_nominal_predicate(predicate):
                return False
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
        proved_finite=completed_native_link_clause(predicate,allow_unclassified,
            require_nominal=require_nominal,nominal_constraint=nominal_constraint)
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
def _native_completed_action_suffix(text, action, native_surface=False, allow_open_tail=False):
    """An already proved source action retains its complete literal tail."""
    if not isinstance(action,str) or not action:return ''
    start=text.rfind(action)
    if start>=0:
        suffix=text[start:]
        if completed_native_verb_reading(suffix,True,False):return suffix
        if allow_open_tail:
            from morphology import tokenize
            parts=tokenize(suffix)
            if parts and _native_open_predicate(suffix,parts[0].surface):return suffix
    # A completed suru clause returns its attested nominal action spelling.
    # Locate that same word's native reading in the literal kana source,
    # then re-prove the unchanged suffix with the same action identity.
    # No missing reading, homophone or invented conjugation supplies a seam.
    if not all('ぁ'<=c<='ゖ' or c=='ー' for c in text):return ''
    from morphology import dictionary_inflections,native_sahen_compound_reading
    readings={rd for pos,form,base,rd in dictionary_inflections(action) or ()
              if pos.startswith('名詞,') and base==action and rd}
    compound=native_sahen_compound_reading(action)
    if compound:readings.add(compound)
    for reading in sorted(readings):
        start=text.rfind(reading)
        if start<0:continue
        suffix=text[start:]
        if completed_sahen_reading(suffix,allow_nonpolite=True,return_action=True,
                                   allow_open_tail=allow_open_tail)==action:
            return action+suffix[len(reading):] if native_surface else suffix
    return ''


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
        # A native verb's volitional ending completes an utterance, but
        # does not by itself prove direct modification of the next noun.
        # Keep conjectural copulas (だろう), lexical verbs ending in う,
        # and the separate literary attributive forms on their own paths.
        # Izumiya, Constraints on Noun Modification (2007), sec. 2.2-2.3:
        # https://www.jstage.jst.go.jp/article/kyoyobukiyo/37/0/37_KJ00006122619/_pdf
        previous=parts[-2] if len(parts)>=2 else None
        if (actual and last.has_reading and last.base_form in ('う','よう')
                and last.infl_form=='基本形' and previous is not None
                and previous.has_reading and previous.pos=='動詞'
                and previous.end==last.start
                and previous.infl_form in ('未然ウ接続','未然形')
                and any(row[0].startswith('動詞,') and row[2]==previous.infl_form
                        and row[3]==previous.base_form and row[4]==previous.reading
                        for row in dictionary_paradigms(previous.surface) or ())):
            return False
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
def native_linked_reading_boundaries(text,nominal_constraint=None,allow_unclassified=False,
                                    allow_open_tail=False):
    """Both unchanged clauses prove the exact seam of their native link.

    Shared with sequence protection and source-final auxiliary evidence.
    A lexical ばね cannot itself provide a seam; the conditional and the
    remaining independent verb must each satisfy the same complete proof.
    Source-only allow_open_tail reuses the native unfinished predicate proof;
    candidate callers retain the default complete-tail requirement.
    """
    if not text or len(text)>80:return ()
    from morphology import tokenize,dictionary_inflections
    parts=tokenize(text)
    # A completed native polite past owns its auxiliary stem. Splitting
    # でした inside でし would invent a second clause such as 下です.
    # An actual で + しつれい clause has no following native past た here.
    closed_auxiliaries=tuple((a.start,a.end) for a,b in zip(parts,parts[1:])
        if a.has_reading and b.has_reading and a.end==b.start
        and a.pos==b.pos=='助動詞' and a.infl_form=='連用形'
        and b.base_form=='た' and b.infl_form=='基本形'
        and any(pos.startswith('助動詞,') and base in ('ます','です')
                and form==a.infl_form and rd==a.reading
                for pos,form,base,rd in dictionary_inflections(a.surface) or ())
        and any(pos.startswith('助動詞,') and base=='た' and form==b.infl_form and rd==b.reading
                for pos,form,base,rd in dictionary_inflections(b.surface) or ()))
    boundaries=set()
    for cut in range(2,len(text)-1):
        if any(start<cut<end for start,end in closed_auxiliaries):continue
        left,right=text[:cut],text[cut:]
        if (completed_native_reading_link(left,require_nominal=bool(nominal_constraint),
                nominal_constraint=nominal_constraint,allow_unclassified=allow_unclassified)
                and (completed_native_link_clause(right,allow_unclassified)
                     or completed_native_reading_sequence(right,allow_unclassified=allow_unclassified)
                     or allow_open_tail and (
                         completed_native_reading_clause(right,allow_nonpolite=True,
                             require_object_fit=True,allow_open_tail=True)
                         or native_adverbial_predicate_reading(right)
                         or native_incomplete_polite_reading(right)
                         or native_linked_reading_boundaries(right,
                             allow_unclassified=allow_unclassified,allow_open_tail=True)))):
            boundaries.add(cut)
            boundaries.update(cut+later for later in native_linked_reading_boundaries(
                right,allow_unclassified=allow_unclassified,allow_open_tail=allow_open_tail))
    return tuple(sorted(boundaries))


def _native_attributive_end_positions(text):
    """Necessary native suffix positions, never a complete clause proof.

    Both finite and literary attributive endings require a native terminal
    entry. Unknown-token recovery recurses on a shorter literal suffix,
    retaining that same final entry. Query the existing dictionary trie;
    unavailable data leaves the original exhaustive checks in place.
    """
    from morphology import dictionary_prefix_paradigms
    ends=set()
    for start in range(len(text)):
        tail=text[start:]
        forms=dictionary_prefix_paradigms(tail)
        if forms is None:return None
        for surface,pos,kind,form,base,reading in forms:
            if (surface and tail.startswith(surface)
                    and pos.startswith(('動詞,','形容詞,','助動詞,'))
                    and form in ('基本形','連体形','体言接続')):
                ends.add(start+len(surface))
    return frozenset(ends)


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
    if not bare or len(bare)>80 or not all('ぁ'<=c<='ゖ' or c=='ー' for c in bare):
        return False
    # Native short verbs can form either complete clause (見たら寝る).
    # Their dictionary inflection and connection provide the proof;
    # a four-kana minimum is not a grammatical boundary.
    if native_linked_reading_boundaries(bare,nominal_constraint,allow_unclassified):return True
    possible_ends=_native_attributive_end_positions(bare)
    for cut in range(2,len(bare)-1):
        if possible_ends is not None and cut not in possible_ends:continue
        left,right=bare[:cut],bare[cut:]
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
    return tuple(face for face in dict.fromkeys((*_native_nominal_reading_faces(text),
                    *native_attested_prefix_noun_faces(text)))
                 if native_action_noun_reading(face,text))


@lru_cache(maxsize=4096)
def native_action_noun_reading(surface,reading):
    """Shared exact action-noun evidence for complete and omitted suru tails."""
    from morphology import dictionary_inflections,native_sahen_compound_reading
    from general_words import sourced_sahen_noun
    return (native_sahen_compound_reading(surface)==reading
            or sourced_sahen_noun(surface,reading)
            or any(pos.startswith('名詞,サ変接続,') and rd==reading
                   for pos,form,base,rd in dictionary_inflections(surface) or ()))


@lru_cache(maxsize=2048)
def native_reading_polite_mismatches(text):
    """Apply the existing noun/masu seam to its unchanged native reading.

    No inserted suru or repair supplies the source boundary. Whole native
    nominal/predicate alternatives still precede the malformed attachment.
    """
    from morphology import tokenize
    from oddness import polite_aux_mismatch
    from contextual_repair import _native_sahen_reading_heads
    out=[]
    for start,clause in _native_source_clauses(text):
        if (not clause or 'ま' not in clause
                or not all('ぁ'<=c<='ゖ' or c=='ー' for c in clause)):
            continue
        marks=[]
        for cut,reading,heads in _native_sahen_reading_heads(clause):
            tail=clause[cut:]
            for head in heads:
                spelled=head+tail;original=tokenize(spelled)
                if (len(original)<2 or original[0].surface!=head
                        or original[0].reading!=reading):continue
                chain=next((end for begin,end,sig in native_polite_auxiliary_chains(spelled)
                            if begin==len(head) and sig[0][1]=='ます'),None)
                if chain is None:continue
                pair=[(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,
                       t.has_reading,t.infl_form) for t in original[:2]]
                if polite_aux_mismatch(*pair):
                    marks.append((start,start+cut+chain-len(head)))
                    break
        if marks and not (completed_native_reading(clause)
                          or native_source_finite_verb(clause)
                          or native_nominal_phrase_faces(clause)):
            from literal_examples import protected_ranges,overlaps
            literal=protected_ranges(text)
            out.extend((a,b) for a,b in marks if not overlaps(a,b,literal))
    return tuple(dict.fromkeys(out))


@lru_cache(maxsize=2048)
def native_written_action_attachment_heads(text):
    """Written native action nouns before their malformed polite attachment."""
    from morphology import tokenize,dictionary_inflections
    from oddness import polite_aux_mismatch
    parts=tokenize(text);out=[]
    for left,right in zip(parts,parts[1:]):
        if (not left.has_reading or left.pos!='名詞' or left.pos_sub!='サ変接続'
                or not any('一'<=c<='鿿' for c in left.surface)):
            continue
        if not any(pos.startswith('名詞,サ変接続,') and rd==left.reading
                   for pos,form,base,rd in dictionary_inflections(left.surface) or ()):continue
        pair=[(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,t.has_reading,t.infl_form)
              for t in (left,right)]
        if polite_aux_mismatch(*pair):out.append((left.start,left.end))
    return tuple(out)


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
def native_source_action_heads(text):
    """Same-reading action heads with their actual finite/open polite tails.

    Keep every grammatical homophone available to the caller's meaning
    comparison. This is source evidence, not a completed-candidate test.
    """
    if not text or not 2<=len(text)<=80:return ()
    if not all('ぁ'<=c<='ゖ' or c=='ー' for c in text):
        proof=native_written_relative_action(text,allow_finite=True,allow_open_polite=True)
        return (proof[0],) if proof else ()
    from morphology import native_spelling_only
    out=[]
    for cut in range(2,min(12,len(text)-1)+1):
        for face in native_bare_action_faces(text[:cut]):
            written=face+text[cut:]
            if not native_spelling_only(text,written):continue
            proof=native_written_relative_action(written,allow_finite=True,allow_open_polite=True)
            if proof and proof[0]==face:out.append(face)
    return tuple(dict.fromkeys(out))


@lru_cache(maxsize=4096)
def _native_action_note_heads(text,require_link=True,allow_predicate=False):
    """Use the same clause proof and its exact action; never re-guess its boundary."""
    for cut in range(4,len(text)-1):
        left,right=text[:cut],text[cut:]
        if not left.endswith('して'):
            continue
        right_heads=native_bare_action_faces(right) or _native_action_note_heads(right,require_link,allow_predicate)
        if not right_heads and allow_predicate:
            right_heads=native_source_action_heads(right)
        if not right_heads:
            continue
        head=completed_native_reading_clause(left,allow_nonpolite=True,
            require_object_fit=True,return_action=True,
            action_note_following=right_heads if require_link else None)
        if head:return (head,)
    return ()


# 48-ACE: closed discourse/question modifiers of an abbreviated action.
# Actual native token boundaries and POS are still required; these written
# words are grammatical roles, not correction answers.
ACTION_NOTE_INTRODUCERS=frozenset('そして それから まず なぜ どうして なんで'.split())


@lru_cache(maxsize=4096)
def native_action_note_introduction(text):
    if (not text or not 4<=len(text)<=80
            or not all('ぁ'<=c<='ゖ' for c in text)):return False
    from morphology import tokenize,dictionary_inflections
    parts=tokenize(text)
    if not parts:return False
    first=parts[0]
    # A real source conjunction introduces the same abbreviated action
    # without needing a separate surface whitelist. Other modifiers keep
    # the existing discourse/question scope.
    return bool(first.start==0 and first.has_reading
        and first.pos in ('接続詞','副詞')
        and (first.surface in ACTION_NOTE_INTRODUCERS
             or first.pos=='接続詞' and any(pos.startswith('接続詞,')
                 and rd==first.reading==first.surface
                 for pos,form,base,rd in dictionary_inflections(first.surface) or ()))
        and native_bare_action_faces(text[first.end:]))


@lru_cache(maxsize=4096)
def completed_native_action_note(text,require_link=True):
    """48-ABY: a linked instruction such as confirm-and-save may end in a noun.

    The existing grammatical evidence proves each unchanged clause. Shared
    semantic roles additionally prove a plausible action sequence. Missing
    linkage is no negative judgment; existing anomaly detection still applies.
    Source preservation may omit the cross-action link: different tasks
    can be listed in temporal order. Each original clause and its own case
    still require evidence. Candidate validation keeps require_link=True.
    This never selects a kanji spelling for the user's kana text.
    """
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    if native_action_note_introduction(bare):return True
    return bool(bare and 8<=len(bare)<=80 and all('ぁ'<=c<='ゖ' for c in bare)
                and _native_action_note_heads(bare,require_link))


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
    return tuple((rd,phase) for face,phase in (('前','nonpast'),('後','past'),('時','relative'))
                 for pos,form,base,rd in dictionary_inflections(face) or ()
                 if pos.startswith('名詞,') and rd in ('まえ','あと','のち','とき'))


@lru_cache(maxsize=4096)
def _native_temporal_modifier(left,phase,nominal_constraint=None):
    """The unchanged action and native inflection select 前/後/時 together."""
    from morphology import tokenize
    action=(nominal_constraint is None and (
                completed_sahen_reading(left,allow_nonpolite=True,return_action=True)
                or completed_native_verb_reading(left,True,require_roles=False))
            or completed_native_reading_clause(left,allow_nonpolite=True,
                require_nominal=True,require_object_fit=True,return_action=True,
                nominal_constraint=nominal_constraint))
    if not action:return False
    parts=tokenize(left);last=parts[-1] if parts else None
    if not last or not last.has_reading:
        # The known noun/case may have forced the whole kana clause
        # into one unknown token. Reuse the same proved predicate,
        # without borrowing the ending of a different suffix word.
        suffix=_native_completed_action_suffix(left,action)
        parts=tokenize(suffix) if suffix else []
        last=parts[-1] if parts else None
    if not last:return False
    if phase=='relative':
        ending=native_attributive_predicate_end(left)
    elif phase=='nonpast':
        ending=last.pos=='動詞' and last.infl_form=='基本形'
    else:
        ending=last.pos=='助動詞' and last.base_form=='た' and last.infl_form=='基本形'
        if (not ending and last.pos=='助動詞' and last.base_form=='だ'
                and last.infl_form=='基本形' and len(parts)>1):
            from contextual_repair import _modern_te_allowed
            previous=parts[-2]
            ending=(previous.pos=='動詞' and previous.has_reading
                and _modern_te_allowed(previous.surface,previous.reading,'だ') is True)
    return bool(ending)


@lru_cache(maxsize=4096)
def native_temporal_nominal_reading(text):
    """Source-only completed time phrase, also valid without a next predicate.

    GPT-6 Astra / 2026-09-22: a native finite action modifies the same
    temporal heads used in whole clauses. Do not propose a replacement.
    """
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    if not 3<=len(bare)<=48 or not all('ぁ'<=c<='ゖ' or c=='ー' for c in bare):return False
    for head,phase in _native_temporal_heads():
        for case in ('','に','で'):
            ending=head+case
            if bare.endswith(ending) and len(bare)>len(ending):
                if _native_temporal_modifier(bare[:-len(ending)],phase):return True
    return False


@lru_cache(maxsize=2048)
def native_mixed_kana_word_ranges(text):
    """The unchanged native noun and its attested functional tail survive mixing."""
    import re
    from morphology import dictionary_inflections,tokenize
    from pos_grammar import explain_kana_run
    out=[]
    # The written prefix and full native noun attest a partly kana spelling.
    # A parser's alternative verb reading cannot erase that written prefix.
    for m in re.finditer('[一-鿿]+[ぁ-ゖー]+',text):
        if m.start():
            from morphology import COLUMN_SEPARATOR
            left=next((t for t in tokenize(text) if t.end==m.start()),None)
            # An explicit source field boundary has no lexical reading.
            # It still starts the same nominal proof as the first field;
            # an unknown word or a single internal space does not.
            if not (left and (left.pos=='記号' and COLUMN_SEPARATOR.fullmatch(left.surface)
                    or left.has_reading and (left.pos in ('助詞','接続詞','記号')
                    or left.pos=='助動詞' and left.infl_form=='基本形'
                    or left.pos in ('動詞','形容詞')
                    and native_attributive_predicate_end(text[:m.start()])))):continue
        word=m.group();cut=next(i for i,c in enumerate(word) if 'ぁ'<=c<='ゖ' or c=='ー')
        prefix=word[:cut]
        readings={rd for pos,form,base,rd in dictionary_inflections(prefix) or ()
            if pos.startswith('名詞,') and not any(x in pos for x in ('固有名詞','非自立','接尾'))}
        for end in range(min(len(word),18),cut,-1):
            faces=[face for reading in readings for face in native_lexical_reading_faces(reading+word[cut:end])
                if face.startswith(prefix) and any(pos.startswith('名詞,') and rd==reading+word[cut:end]
                    and not any(x in pos for x in ('固有名詞','接尾','非自立'))
                    for pos,form,base,rd in dictionary_inflections(face) or ())]
            tail=word[end:];attested=False
            for face in faces:
                if not tail or _native_nominal_copula_tail(face,tail):attested=True;break
                following=[t for t in tokenize(face+tail) if t.start>=len(face)]
                if (following and following[0].start==len(face) and following[-1].end==len(face+tail)
                        and all(t.has_reading and t.pos=='助詞' for t in following)
                        and explain_kana_run(tail,no_words=True,initial_state='Bw')):attested=True;break
            if attested:out.append((m.start(),m.start()+end));break
    for m in re.finditer('[ぁ-ゖァ-ヶー]+',text):
        word=m.group()
        if not (2<=len(word)<=40 and any('ァ'<=c<='ヶ' for c in word)
                and any('ぁ'<=c<='ゖ' for c in word)):continue
        for cut in range(len(word),1,-1):
            head,tail=word[:cut],word[cut:]
            if not (any('ァ'<=c<='ヶ' for c in head) and any('ぁ'<=c<='ゖ' for c in head)):
                continue
            if tail and not all('ぁ'<=c<='ゖ' for c in tail):continue
            katakana=''.join(chr(ord(c)+0x60) if 'ぁ'<=c<='ゖ' else c for c in head)
            reading=''.join(chr(ord(c)-0x60) if 'ァ'<=c<='ヶ' else c for c in head)
            if not any(pos.startswith('名詞,') and rd==reading
                       for pos,form,base,rd in dictionary_inflections(katakana) or ()):
                continue
            if not tail or _native_nominal_copula_tail(katakana,tail):
                out.append(m.span());break
            projected=tokenize(katakana+tail)
            after=[t for t in projected if t.start>=cut]
            if not (after and after[0].start==cut and after[-1].end==len(word)
                    and all(t.has_reading and t.pos=='助詞' for t in after)
                    and explain_kana_run(tail,no_words=True,initial_state='Bw')):
                continue
            out.append(m.span())
            if tail=='の' and after[0].pos_sub=='連体化':
                # The same original N-no-N phrase, with its literal right
                # noun, explains a parser's accidental unknown-token join.
                suffix=tokenize(text[m.end():]);right=[];edge=0
                for t in suffix:
                    if t.start!=edge or t.end>24 or not t.has_reading or t.pos!='名詞':break
                    right.append(t);edge=t.end
                if right:
                    surface=''.join(t.surface for t in right)
                    yomi=''.join(t.reading for t in right)
                    if (_native_written_nominal_faces(surface)
                            and native_nominal_phrase_faces(reading+tail+yomi)):
                        out.append((m.start(),m.end()+len(surface)))
            break
    return tuple(dict.fromkeys(out))


def preserves_native_mixed_kana_words(original,changed):
    return _preserves_source_ranges(original,changed,native_mixed_kana_word_ranges(original))


@lru_cache(maxsize=2048)
def native_temporal_nominal_ranges(text):
    return tuple((start,start+len(clause)) for start,clause in _native_source_clauses(text)
                 if native_temporal_nominal_reading(clause))


def preserves_native_temporal_nominal(original,changed):
    return _preserves_source_ranges(original,changed,native_temporal_nominal_ranges(original))


@lru_cache(maxsize=4096)
def native_temporal_reading_edges(text,nominal_constraint=None):
    """Native 前/後/時 + に joins independently proved unchanged clauses.

    GPT-6 Astra / 2026-09-21: 時 takes the shared attributive predicate
    proof. An original written object constrains the same preceding action,
    while the following independent clause keeps its own arguments.
    """
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    if not 8<=len(bare)<=80 or not all('ぁ'<=c<='ゖ' or c=='ー' for c in bare):return ()
    from morphology import tokenize
    edges=[]
    markers=((head+case,phase) for head,phase in _native_temporal_heads()
             for case in (('に','で') if phase=='past' else ('に',)))
    for marker,phase in markers:
        for cut in range(2,len(bare)-len(marker)-2):
            if not bare.startswith(marker,cut):continue
            left,right=bare[:cut],bare[cut+len(marker):]
            if not _native_temporal_modifier(left,phase,nominal_constraint):continue
            if (completed_native_reading_clause(right,require_object_fit=True)
                    or completed_native_reading_sequence(right)
                    or completed_native_adjunct_clause(right)
                    or completed_native_temporal_clause(right)):
                edges.append(cut+len(marker))
    return tuple(sorted(set(edges)))


@lru_cache(maxsize=4096)
def completed_native_temporal_clause(text,nominal_constraint=None):
    return bool(native_temporal_reading_edges(text,nominal_constraint))


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
    text=text.rstrip('。！？.!?')
    if (not text or 'の' not in text or not any(p in text for p in particles) or not 8<=len(text)<=80
            or not all('ぁ'<=c<='ゖ' or c=='ー' for c in text)):return ()
    from morphology import tokenize
    from contextual_repair import _completed_predicate_token
    parts=tokenize(text);out=[]
    adjuncts=native_adverbial_reading_cuts(text)
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
        # A bare time noun immediately before の is this modifier's
        # owner, not a completed adjunct before a different nominal.
        begin=max([edge for edge in begins if edge<=genitive_start]
                  +[edge for edge in adjuncts if edge<genitive_start])
        if not native_nominal_phrase_faces(text[begin:genitive_start]):continue
        for case in cases:
            if not 2<=case-genitive_end<=12:continue
            # An independently proved adjunct closes its own genitive
            # phrase. It cannot also modify the following unknown object.
            if any(genitive_end<edge<=case for edge in adjuncts):continue
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
def native_genitive_nominal_splits(text, allow_unknown_left=False, original_context=None):
    """48-AKR: the original adnominal の and a complete nominal suffix.

    Normal proof requires both nouns. A repair range may leave its left
    noun unproved, but supplies no anomaly or candidate evidence thereby.
    A known whole word or a known token across の owns that spelling.
    """
    if not text or 'の' not in text or not 3<=len(text)<=24:return ()
    from morphology import tokenize,dictionary_inflections
    kana=lambda value:all('ぁ'<=c<='ゖ' or c=='ー' for c in value)
    def faces(value):
        return (native_nominal_phrase_faces(value) if kana(value) else
                _native_written_nominal_faces(value) or _native_written_compound_nominal_heads(value))
    direct=_native_nominal_reading_faces(text) if kana(text) else _native_written_nominal_faces(text)
    if direct:return ()
    if original_context is not None and not original_context.startswith(text):return ()
    # Prefix-only tokenization may change the source word across the next
    # particle. A caller owning the original context supplies that same
    # unchanged text, never a repaired reading or a neighboring clause.
    original=tokenize(original_context if original_context is not None else text);out=[]
    for cut,char in enumerate(text):
        if char!='の' or not 1<=cut<len(text)-1:continue
        right=faces(text[cut+1:])
        if not right:continue
        left=faces(text[:cut])
        if not left and not kana(text[:cut]):
            # A written native name may modify a noun without becoming a
            # common-noun candidate itself. Keep its exact original spelling.
            head=next((t for t in original if t.start==0 and t.end==cut),None)
            if (head and head.has_reading and head.pos=='名詞'
                    and head.pos_sub.startswith('固有名詞')
                    and any(p.startswith('名詞,固有名詞,') and b==head.surface and rd==head.reading
                            for p,f,b,rd in dictionary_inflections(head.surface) or ())):
                left=(head.surface,)
        if not left:
            # A native quantity is a modifier without being an independent
            # common noun. Reuse its typed counter and the actual head;
            # an ordinal or unknown referent supplies no new evidence.
            from semantic_roles import counted_object_roles,nominal_role_matches,nominal_roles
            roles=counted_object_roles(text[:cut])
            if not roles:
                # Share only the existing quantity-no-noun context meaning;
                # generic quantity/ordinal roles remain unchanged.
                from semantic_roles import counted_genitive_roles
                roles=counted_genitive_roles(text[:cut])
            # A typed linear quantity also modifies an already classified
            # geometric line. This does not classify every hon-counted
            # object as a line; the actual following noun supplies that sense.
            linear='linear_quantity' in nominal_roles(text[:cut])
            counted=tuple(face for face in right if nominal_role_matches(face,roles or ())
                or linear and 'geometric_line' in nominal_roles(face))
            if counted:left,right=(text[:cut],),counted
        if not left and not allow_unknown_left:continue
        particle=any(t.start==cut and t.end==cut+1 and t.surface=='の'
            and t.pos=='助詞' and t.has_reading and t.pos_sub=='連体化' for t in original)
        # An inferred head lying wholly inside an original known word
        # cannot create its own genitive boundary. A token overlapping
        # only part of an independently proved full noun is not that
        # proof: the native best parse may itself split either noun.
        # Use the same original context to retain complete-word ownership,
        # while both whole nouns and their projected particle still have
        # to be established independently below.
        if not particle and any(t.has_reading and t.start<=cut
                and cut+1<t.end and len(text)<=t.end for t in original):continue
        projected=any(any(t.start==len(a) and t.end==len(a)+1 and t.surface=='の'
            and t.pos=='助詞' and t.has_reading and t.pos_sub=='連体化'
            for t in tokenize(a+'の'+z)) for a in left for z in right)
        unknown=(allow_unknown_left and not left
            and any(not t.has_reading and t.start<=cut<t.end for t in original)
            and any(pos.startswith('助詞,連体化,') and rd=='の'
                for pos,form,base,rd in dictionary_inflections('の') or ()))
        if particle or projected or unknown:out.append((cut,tuple(left),tuple(right)))
    return tuple(out)


@lru_cache(maxsize=4096)
def native_relative_nominal_faces(text, action, occupied_cases):
    """A relative action may modify the noun before an unchanged genitive.

    In a borrowed book's page, book fits borrowing and page is the final
    head. Both are independently attested; a written noun stays itself.
    """
    from semantic_roles import relative_action_support
    kana=all('ぁ'<=c<='ゖ' or c=='ー' for c in text)
    faces=native_nominal_phrase_faces(text) if kana else _native_written_nominal_faces(text)
    if kana and len(text)==1:
        # The same proved relative action supplies context for the existing
        # short noun evidence; no one-kana entry enters free lexical search.
        from semantic_roles import short_role_noun_faces
        faces=tuple(dict.fromkeys((*faces,*short_role_noun_faces(text))))
    splits=native_genitive_nominal_splits(text)
    if not splits:
        return tuple(face for face in faces if relative_action_support(face,action,occupied_cases))
    # The altered left noun must fit the original relative action itself.
    # The suffix's role cannot justify an unrelated lexical replacement.
    fitting=[]
    for cut,left,right in splits:
        if any(relative_action_support(face,action,occupied_cases) for face in left):
            fitting.extend(right)
    return tuple(dict.fromkeys(fitting))


@lru_cache(maxsize=4096)
def native_modified_argument_slots(text):
    """48-AKD: source modifiers and the same case/predicate repair boundary.

    The last field carries the relative action and occupied cases, or None
    for an N-no modifier. The head supplies neither a noun nor an anomaly.
    """
    genitives=tuple((*slot,None) for slot in native_genitive_argument_slots(text))
    if not text or not 6<=len(text)<=80:return genitives
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
            if begin+3>case:continue
            for head in range(max(begin+2,case-12),case):
                # A finite-looking prefix inside an attested original noun
                # does not create a relative clause (including kana nouns).
                if (any(t.has_reading and t.pos=='名詞' and t.start<head<t.end
                        for t in parts) and native_nominal_phrase_faces(text[begin:case])):
                    continue
                # A short best-path noun may swallow the real past ending.
                # Only the complete original nominal, not that internal token,
                # can overrule the independent native relative-clause proof.
                # An attested lexical modifier before the source no owns
                # its whole word. A short finite-looking prefix inside that
                # noun does not create a competing relative clause.
                if any(gbegin==begin and begin<head<ghead-1 and gcase==case
                        and _native_nominal_reading_faces(text[begin:ghead-1])
                        for gbegin,ghead,gcase,gfinish,_ in genitives):continue
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
    if not text or not 6<=len(text)<=80:return ()
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
                if not head<=start<start+size<=case:continue
                # A written noun may precede の + another nominal head.
                # Convert coordinates only; the literal written noun below
                # still has to prove its own relation to the source action.
                finish-=size-(stop-start);case-=size-(stop-start)
            else:
                faces=native_nominal_phrase_faces(text[head:case])
            if relative:faces=native_relative_nominal_faces(text[head:case],*relative)
            if not faces:continue
            if native_object_predicate_proof(text[begin:finish],case-begin+1,faces,allow_link=True):
                out.append((begin,head,case,finish,tuple(faces)))
    return tuple(dict.fromkeys(out))


def native_genitive_object_slots(text):
    """The accusative subset of the same original genitive/case evidence."""
    return native_genitive_argument_slots(text,('を',))


@lru_cache(maxsize=2048)
def native_coordinated_nominal_heads(text):
    """An actual adjective/て coordinates with an attested noun modifier.

    Both modifiers belong to the same written nominal phrase. A bare noun
    after て or an unexplained suffix does not establish this structure.
    """
    if not any(c in text for c in ('て','と','や')):return ()
    from morphology import tokenize
    parts=tokenize(text)
    # Each actual parallel noun retains its own complete nominal head.
    # Slices are strictly shorter, so nested genitives share the ordinary
    # noun proof without a full-clause or candidate-search recursion.
    for link in parts:
        if (link.has_reading and link.pos=='助詞' and link.pos_sub=='並立助詞'
                and link.surface in ('と','や') and 0<link.start<link.end<len(text)):
            left=native_surface_nominal_heads(text[:link.start])
            right=native_surface_nominal_heads(text[link.end:])
            if left and right:return tuple(dict.fromkeys(left+right))
    if len(parts)<4:return ()
    adjective,link=parts[:2]
    if not (adjective.start==0 and adjective.has_reading and adjective.pos=='形容詞'
            and link.surface=='て' and link.pos=='助詞' and link.pos_sub=='接続助詞'
            and link.has_reading and adjective.end==link.start
            and native_adjective_adverbial_prefix(text,adjective.end)):return ()
    tail=text[link.end:];rest=parts[2:]
    if not (rest[-1].has_reading and rest[-1].pos=='名詞'
            and any(t.has_reading and (t.pos in ('形容詞','連体詞')
                or t.surface=='の' and t.pos=='助詞' and t.pos_sub=='連体化')
                for t in rest[:-1])):return ()
    return native_surface_nominal_heads(tail)


def native_subject_sahen_action(text):
    """The original whole subject, actual ga and unchanged complete sahen.

    This is a source boundary proof, not a selected output spelling. Keep
    the subject case even when its written face precedes a kana predicate.
    Every use still checks its own candidate and relative-noun meanings.
    """
    from morphology import tokenize,dictionary_inflections,COLUMN_SEPARATOR
    if (not text or not 5<=len(text)<=80 or COLUMN_SEPARATOR.search(text)
            or any(c in text for c in '\r\n')):return ()
    kana=lambda value:bool(value) and all('ぁ'<=c<='ゖ' or c=='ー' for c in value)
    for case in tokenize(text):
        if not (case.start>=2 and case.end==case.start+1 and case.end<len(text)
                and text[case.start:case.end]==case.surface=='が'
                and case.has_reading and case.reading=='が' and case.pos=='助詞'
                and case.pos_sub.startswith('格助詞')
                and any(pos.startswith('助詞,格助詞,') and rd==case.reading
                    and base==case.base_form and (form if form!='*' else '')==case.infl_form
                    for pos,form,base,rd in dictionary_inflections(case.surface) or ())):continue
        subject=text[:case.start];tail=text[case.end:]
        subjects=native_nominal_phrase_faces(subject) if kana(subject) else _native_written_nominal_faces(subject)
        if not subjects or not kana(tail):continue
        # The original adjunct owns only its boundary. Keep the source ga,
        # whole subject and the following predicate's independent finite
        # and semantic proof; an arbitrary removed prefix supplies none.
        for cut in (0,)+native_adverbial_reading_cuts(tail):
            predicate=tail[cut:]
            if not native_attributive_predicate_end(predicate):continue
            action=completed_sahen_reading(predicate,allow_nonpolite=True,subject_faces=subjects,
                                          return_action=True,finite_only=True)
            if not action:continue
            from semantic_roles import subject_candidate_evidence
            for pos,form,base,reading in dictionary_inflections(action) or ():
                if (pos.startswith('名詞,サ変接続,') and base==action and reading
                        and predicate.startswith(reading) and len(reading)<len(predicate)):
                    meanings=[subject_candidate_evidence(subject,action,predicate[len(reading):]) for subject in subjects]
                    if any(p and p.get('predicate')==action and p.get('shared_roles') for p in meanings):
                        return case.end+cut,case.end+cut+len(reading),action,tuple(subjects)
    return ()


def native_unknown_relative_object_action(text,parts):
    """An original whole relative noun followed by its own finite action.

    Only a case swallowed by an unknown native token is reopened. The
    unchanged relative head proves every inner argument before the whole
    noun is checked against the same actual outer predicate. No string is
    repaired and no inner subject is lent to that outer action.
    """
    from morphology import COLUMN_SEPARATOR,dictionary_inflections
    from contextual_repair import _finite_written_predicate
    from semantic_roles import candidate_nominal_spelling_evidence
    if (not text or not 6<=len(text)<=80 or COLUMN_SEPARATOR.search(text)
            or any(c in text for c in '\r\n')):return ()
    for cut in native_case_positions(text,parts,('を',)):
        if not any(not t.has_reading and t.start<cut and cut+1<=t.end for t in parts):continue
        if not any(pos.startswith('助詞,格助詞,') and base==rd=='を' and form=='*'
                   for pos,form,base,rd in dictionary_inflections('を') or ()):continue
        nominal=native_written_action_nominal_parts(text[:cut])
        if not nominal or native_nominal_case_boundary(text,parts,cut,'を',nominal[1]) is None:continue
        tail=text[cut+1:]
        # This new path is finite only, even when its caller also allows
        # note forms. Keep links and unfinished polite forms separate.
        if not _finite_written_predicate(tail):continue
        original_tail=[t for t in parts if t.start>=cut+1]
        if (not original_tail or original_tail[0].start!=cut+1
                or ''.join(t.surface for t in original_tail)!=tail
                or not all(t.has_reading for t in original_tail)):continue
        action=native_written_relative_action(tail,allow_finite=True)
        if not action or action[1]:continue
        proofs=[candidate_nominal_spelling_evidence('',face,text[cut:]) for face in nominal[1]]
        if all(proof and proof.get('predicate')==action[0] and proof.get('case')=='を'
               and proof.get('shared_roles') for proof in proofs):return action[0],('を',)
    return ()


@lru_cache(maxsize=4096)
def native_written_relative_action(text,allow_link=False,allow_finite=False,allow_note=False,allow_open_polite=False):
    """Actual written predicate and all its unchanged nominal arguments.

    GPT-6 / 2026-09-29. Keep the native lemma, inflection and occupied cases.
    A different homophone, a malformed auxiliary or an unknown argument
    cannot supply source proof. This helper chooses no replacement text.
    """
    if not text or not 2<=len(text)<=80 or all('ぁ'<=c<='ゖ' or c=='ー' for c in text):return ()
    from morphology import tokenize
    from contextual_repair import _productive_predicate,_finite_written_predicate
    from semantic_roles import (classified_nominal_action,native_verb_roles,
        predicate_roles,nominal_role_matches)
    parts=tokenize(text)
    if allow_finite and not (allow_link or allow_open_polite) and any(not t.has_reading for t in parts):
        original=native_unknown_relative_object_action(text,parts)
        if original:return original
    if (not parts or parts[0].start!=0 or parts[-1].end!=len(text)
            or not all(t.has_reading for t in parts)
            or not all(a.end==b.start for a,b in zip(parts,parts[1:]))):return ()
    for i,head in enumerate(parts):
        verb=head.pos=='動詞' and head.pos_sub=='自立'
        action=head.pos=='名詞' and classified_nominal_action(head.surface,head.reading)
        if not (verb or action):continue
        before=text[:head.start];tail=text[head.start:]
        linked=(allow_link and parts[-1].surface in ('て','で')
                and parts[-1].pos=='助詞' and parts[-1].pos_sub=='接続助詞')
        # Source spelling may reuse an actual unfinished polite chain.
        # This option does not certify it as a completed relative clause.
        open_polite=bool(allow_open_polite and any(end==len(tail)
            for start,end,signature in native_polite_auxiliary_chains(tail,include_open=True))
            and _native_open_predicate(tail,head.surface,before=before))
        if not (open_polite or (native_attributive_predicate_end(tail) or linked
                or allow_note and action and tail==head.surface
                or allow_finite and _finite_written_predicate(tail))
                and _productive_predicate(tail,head.surface,before=before)):continue
        if any(t.pos=='動詞' and t.pos_sub.startswith('接尾')
               and t.base_form in ('れる','られる','せる','させる') for t in parts[i+1:]):continue
        occupied=[];begin=0;valid=True
        # Share the original whole-noun/case chain when a kana best parse
        # splits an ordinary argument into internal functional tokens.
        literal=native_literal_argument_chain(before)
        if literal:
            from semantic_roles import proved_action_case_support
            if all(proved_action_case_support(noun,case,head.surface,context=text)
                   for noun,case,a,b in literal):
                return (head.surface if action else tail,tuple(case for noun,case,a,b in literal))
            continue
        for case in parts[:i]:
            if not (case.pos=='助詞' and case.has_reading
                    and case.surface in ('が','は','も','を','に','へ','で','と','から')):continue
            faces=native_surface_nominal_heads(text[begin:case.start])
            nominal_case=case.pos_sub.startswith(('格助詞','係助詞'))
            if (not nominal_case and case.surface=='に' and faces
                    and native_nominal_case_boundary(text,parts,case.start,'に',faces,
                        allow_known_noun=True,allow_compound_case=True) is not None):
                nominal_case=True
            if not nominal_case:continue
            if not faces or case.surface in occupied:valid=False;break
            if action:
                roles=predicate_roles(head.surface,case=None if case.surface=='を' else case.surface)
                if case.surface in ('が','は','も'):
                    from semantic_roles import SUBJECT_VERB_ROLES
                    roles=frozenset(SUBJECT_VERB_ROLES.get(head.surface,())) | (
                        predicate_roles(head.surface) if case.surface in ('は','も') else frozenset())
            else:
                kwargs=dict(tail=tail[len(head.surface):],before=before)
                roles=native_verb_roles(head.surface,head.infl_form,head.reading,
                    subject=case.surface in ('が','は','も'),
                    case=None if case.surface in ('を','が','は','も') else case.surface,**kwargs)
                if case.surface in ('は','も'):
                    roles |= native_verb_roles(head.surface,head.infl_form,head.reading,**kwargs)
            supported=any(nominal_role_matches(face,roles) for face in faces)
            if not supported and action:
                # The completed/open native predicate was proved above.
                # Reuse the same literal argument/action relation as the
                # source-chain path, retaining this case's original scope.
                from semantic_roles import proved_action_case_support
                supported=any(proved_action_case_support(face,case.surface,head.surface,
                    context=text[begin:]) for face in faces)
            if not supported:valid=False;break
            occupied.append(case.surface);begin=case.end
        if not valid:continue
        if begin!=head.start:
            # An unchanged internal adjunct can separate a proved argument
            # from this same actual predicate. It consumes no case slot.
            # Do not broaden open/link/note/finite-only modes here.
            if (allow_link or allow_finite or allow_note or allow_open_polite
                    or head.start-begin not in native_adverbial_reading_cuts(text[begin:])):continue
        return (head.surface if action else tail,tuple(occupied))
    # An independently attested leading adjunct is not an occupied case.
    # Reuse the completed written predicate's own identity and arguments;
    # open, linked and note-only modes retain their existing contracts.
    if not (allow_link or allow_finite or allow_note or allow_open_polite):
        subject=native_subject_sahen_action(text)
        if subject:return subject[2],('が',)
        for cut in native_adverbial_reading_cuts(text):
            relative=native_written_relative_action(text[cut:])
            if relative:return relative
    return ()


@lru_cache(maxsize=4096)
def native_written_preference_nominal_heads(text):
    """The actual N-ga-NA-na-N frame, keeping both original noun meanings."""
    if not any(stem in text for stem in ('好き','嫌い')):return ()
    from morphology import tokenize,dictionary_inflections
    from semantic_roles import native_preference_relative_support
    parts=tokenize(text)
    if (len(parts)<5 or not all(t.has_reading for t in parts)
            or parts[0].start!=0 or parts[-1].end!=len(text)
            or not all(a.end==b.start for a,b in zip(parts,parts[1:]))):return ()
    out=[]
    for i in range(2,len(parts)-2):
        case,stem,copula=parts[i-1:i+2]
        if not (case.surface=='が' and case.pos=='助詞' and case.pos_sub.startswith('格助詞')
                and stem.pos=='名詞' and stem.pos_sub=='形容動詞語幹'
                and copula.surface=='な' and copula.pos=='助動詞'
                and copula.base_form=='だ' and copula.infl_form=='体言接続'):continue
        if not any(pos.startswith('助動詞,') and base=='だ' and form=='体言接続' and rd=='な'
                   for pos,form,base,rd in dictionary_inflections(copula.surface) or ()):continue
        left=native_surface_nominal_heads(text[:case.start])
        right=_native_written_nominal_faces(text[copula.end:])
        out.extend(head for head in right if any(native_preference_relative_support(
            argument,head,stem.surface,stem.reading) for argument in left))
    return tuple(dict.fromkeys(out))


def native_argument_relative_object_evidence(head,noun):
    """Retain a proved clause's cases while using its own complete action tail.

    The full original clause proves every occupied argument first. Only an
    open object slot may reuse the same sahen head and unchanged finite tail;
    the stripped tail never replaces the original clause's occupied cases.
    Returned semantic evidence is not an emitted spelling candidate.
    """
    if not head or not noun or len(head)>80:return None
    kana=all('ぁ'<=c<='ゖ' or c=='ー' for c in head)
    relative=native_relative_action(head) if kana else native_written_relative_action(head)
    if not relative or not relative[1] or 'を' in relative[1]:return None
    action=relative[0]
    from morphology import tokenize,dictionary_inflections
    entries=dictionary_inflections(action) or ()
    if not any(pos.startswith('名詞,サ変接続,') and base==action
               for pos,form,base,rd in entries):return None
    suffix=''
    if kana:
        literal=_native_completed_action_suffix(head,action)
        if literal and len(literal)<len(head):
            suffix=_native_completed_action_suffix(head,action,native_surface=True)
    else:
        for token in tokenize(head):
            if not (token.start>0 and token.has_reading and token.surface==action
                    and token.end==token.start+len(token.surface)
                    and head[token.start:token.end]==token.surface
                    and token.pos=='名詞' and token.pos_sub=='サ変接続'
                    and token.base_form==action and any(rd==token.reading
                        and pos.startswith('名詞,サ変接続,') and base==action
                        for pos,form,base,rd in entries)):continue
            tail=head[token.start:]
            if native_written_relative_action(tail)==(action,()):
                suffix=tail;break
    if not suffix and not kana:
        original=native_subject_sahen_action(head)
        if original and relative==(original[2],('が',)):
            # Only this source-proved head and its literal tail are used as
            # a semantic-helper argument; the original ga remains occupied.
            suffix=action+head[original[1]:]
    if not suffix or not native_attributive_predicate_end(suffix):return None
    from semantic_roles import candidate_evidence
    proof=candidate_evidence(noun,suffix,'')
    if (proof and proof.get('predicate')==action and proof.get('case')=='を'
            and proof.get('shared_roles')):return proof
    return None


def native_argument_relative_nominal_parts(text):
    """Original argument-bearing relative clause and its entire final noun.

    Each nominal face must fit the same original open object slot. This
    proves a source grammar range only, never the chosen spelling of its
    subject, predicate or noun and never a partial-replacement exemption.
    """
    if not text or not 5<=len(text)<=80:return ()
    from morphology import tokenize,COLUMN_SEPARATOR
    if COLUMN_SEPARATOR.search(text) or any(c in text for c in '\r\n'):return ()
    parts=tokenize(text)
    if not any(t.has_reading and t.pos=='助詞'
               and t.pos_sub.startswith(('格助詞','係助詞')) for t in parts):return ()
    for cut in sorted({t.end for t in parts if 2<t.end<len(text)}):
        nominal=text[cut:]
        faces=(native_nominal_phrase_faces(nominal)
            if all('ぁ'<=c<='ゖ' or c=='ー' for c in nominal)
            else _native_written_nominal_faces(nominal))
        if faces and all(native_argument_relative_object_evidence(text[:cut],face)
                         for face in faces):return cut,tuple(faces)
    return ()


def _native_genitive_subject_heads(head,end,parts):
    """Bind a whole unchanged genitive subject to its own nominal heads.

    Each original token and the actual adnominal particle retain their
    dictionary identity and coordinates. Both complete nouns are proved
    by the existing genitive relation; no suffix or projected parse alone
    certifies the subject. Its predicate meaning is checked by the caller.
    """
    from morphology import tokenize,dictionary_inflections,COLUMN_SEPARATOR
    if not (0<end<=len(head)) or COLUMN_SEPARATOR.search(head) or any(c in head for c in '\r\n'):return ()
    subject=head[:end]
    if 'の' not in subject:return ()
    original=[t for t in parts if t.start<end]
    actual=[t for t in tokenize(head) if t.start<end]
    fields=('surface','reading','has_reading','pos','pos_sub','base_form','infl_form','start','end')
    if (not original or original[0].start!=0 or original[-1].end!=end
            or any(a.end!=b.start for a,b in zip(original,original[1:]))
            or len(actual)!=len(original)
            or any(any(getattr(a,k)!=getattr(b,k) for k in fields) for a,b in zip(original,actual))):return ()
    for t in original:
        if not (t.has_reading and t.end==t.start+len(t.surface) and subject[t.start:t.end]==t.surface
                and (t.pos=='名詞' or t.pos=='助詞' and t.pos_sub=='連体化' and t.surface==t.reading=='の')
                and any(pos.startswith(t.pos+','+(t.pos_sub.replace(':',',')+',' if t.pos_sub else ''))
                    and base==t.base_form and rd==t.reading and (form if form!='*' else '')==t.infl_form
                    for pos,form,base,rd in dictionary_inflections(t.surface) or ())):return ()
    heads=[]
    for cut,left,right in native_genitive_nominal_splits(subject,original_context=head):
        if (left and right and any(t.start==cut and t.end==cut+1 and t.surface=='の'
                and t.pos=='助詞' and t.pos_sub=='連体化' for t in original)):
            heads.extend(right)
    return tuple(dict.fromkeys(heads))


def _native_coordinated_subject_heads(head,end,parts):
    """Keep every original member of a native coordinated nominal subject.

    Whole token identity and the actual parallel particle bind the existing
    nominal proof to this clause. Each member still needs its own positive
    relation to the very same predicate; no member lends another its role.
    """
    from morphology import tokenize,dictionary_inflections,COLUMN_SEPARATOR
    if not (0<end<=len(head)) or COLUMN_SEPARATOR.search(head) or any(c in head for c in '\r\n'):return ()
    subject=head[:end]
    if 'と' not in subject:return ()
    original=[t for t in parts if t.start<end]
    actual=[t for t in tokenize(head) if t.start<end]
    fields=('surface','reading','has_reading','pos','pos_sub','base_form','infl_form','start','end')
    if (len(original)<3 or len(original)%2!=1 or original[0].start!=0 or original[-1].end!=end
            or any(a.end!=b.start for a,b in zip(original,original[1:]))
            or len(actual)!=len(original)
            or any(any(getattr(a,k)!=getattr(b,k) for k in fields) for a,b in zip(original,actual))):return ()
    for index,t in enumerate(original):
        if (not t.has_reading or t.end!=t.start+len(t.surface) or subject[t.start:t.end]!=t.surface
                or not any(pos.startswith(t.pos+','+(t.pos_sub.replace(':',',')+',' if t.pos_sub else ''))
                    and base==t.base_form and rd==t.reading and (form if form!='*' else '')==t.infl_form
                    for pos,form,base,rd in dictionary_inflections(t.surface) or ())):return ()
        if index%2:
            if not (t.surface==t.reading=='と' and t.pos=='助詞' and t.pos_sub=='並立助詞'):return ()
        elif t.pos!='名詞' or any(kind in t.pos_sub for kind in ('固有名詞','接尾','非自立')):return ()
    members=native_coordinated_nominal_parts(subject)
    return members if members==tuple(t.surface for t in original[::2]) else ()


def _native_plural_subject_heads(head,end,parts):
    """Bind a productive plural's existing core to the whole source subject.

    The original noun and suffix must retain their exact native identities
    in both the clause and the plural proof. The core still has to support
    the same predicate as every object; the suffix supplies no new meaning.
    """
    from morphology import tokenize,dictionary_inflections,COLUMN_SEPARATOR
    if not (0<end<=len(head)) or COLUMN_SEPARATOR.search(head) or any(c in head for c in '\r\n'):return ()
    subject=head[:end]
    original=[t for t in parts if t.start<end]
    actual=[t for t in tokenize(head) if t.start<end]
    fields=('surface','reading','has_reading','pos','pos_sub','base_form','infl_form','start','end')
    if (len(original)!=2 or original[0].start!=0 or original[-1].end!=end
            or original[0].end!=original[1].start):return ()
    for parsed in (actual,tokenize(subject)):
        if (len(parsed)!=len(original)
                or any(any(getattr(a,k)!=getattr(b,k) for k in fields) for a,b in zip(original,parsed))):return ()
    noun,suffix=original
    if (noun.pos!='名詞' or any(kind in noun.pos_sub for kind in ('固有名詞','接尾','非自立'))
            or suffix.pos!='名詞' or suffix.pos_sub!='接尾:一般' or suffix.reading!='たち'):return ()
    for t in original:
        if (not t.has_reading or t.end!=t.start+len(t.surface) or subject[t.start:t.end]!=t.surface
                or not any(pos.startswith(t.pos+','+(t.pos_sub.replace(':',',')+',' if t.pos_sub else ''))
                    and base==t.base_form and rd==t.reading and (form if form!='*' else '')==t.infl_form
                    for pos,form,base,rd in dictionary_inflections(t.surface) or ())):return ()
    members=native_plural_nominal_heads(subject)
    return members if members==(noun.surface,) else ()


def _native_subject_kana_verb_nominal(head,relative,nouns,source_parts=None,candidate_face=None,subject_face=None,allow_written=False):
    """One source inflection and one native lexeme prove both arguments.

    A kana parse may expose several homophones. Their role unions cannot
    certify this frame. Dictionary forms below are semantic arguments only;
    no replacement is emitted and every coordinate belongs to the source.
    An explicitly enabled written token proves only its own literal form;
    another homophone may not lend its subject or object meaning.
    """
    if not relative or relative[1]!=('が',) or not nouns:return False
    from morphology import tokenize,dictionary_inflections,COLUMN_SEPARATOR
    from semantic_roles import (native_verb_lexemes,_native_lexeme_forms,
        subject_candidate_evidence,candidate_evidence)
    if COLUMN_SEPARATOR.search(head) or any(c in head for c in '\r\n'):return False
    kana=lambda value:bool(value) and all('ぁ'<=c<='ゖ' or c=='ー' for c in value)
    parts=tokenize(head) if source_parts is None else source_parts
    for token in parts:
        if not (token.has_reading and token.pos=='動詞' and token.pos_sub=='自立'
                and (kana(token.surface) and token.reading==token.surface
                    or allow_written and any('一'<=c<='鿿' for c in token.surface))
                and token.end==token.start+len(token.surface)
                and head[token.start:token.end]==token.surface
                and head[token.start:]==relative[0]
                and any(pos.startswith('動詞,自立,') and base==token.base_form
                    and form==token.infl_form and rd==token.reading
                    for pos,form,base,rd in dictionary_inflections(token.surface) or ())):continue
        for case in parts:
            if not (0<case.start<case.end<=token.start and case.end==case.start+1
                    and head[case.start:case.end]==case.surface=='が'
                    and case.has_reading and case.reading=='が' and case.pos=='助詞'
                    and case.pos_sub.startswith('格助詞')
                    and any(pos.startswith('助詞,格助詞,') and rd==case.reading
                        and base==case.base_form and (form if form!='*' else '')==case.infl_form
                        for pos,form,base,rd in dictionary_inflections(case.surface) or ())):continue
            source_subject=head[:case.start]
            subjects=(native_nominal_phrase_faces(source_subject) if kana(source_subject)
                      else _native_written_nominal_faces(source_subject))
            if not subjects:
                subjects=_native_genitive_subject_heads(head,case.start,parts)
            if not subjects:
                subjects=_native_coordinated_subject_heads(head,case.start,parts)
            if not subjects:
                subjects=_native_plural_subject_heads(head,case.start,parts)
            if not subjects:continue
            if subject_face is not None:
                # This conditional proof belongs to one emitted subject,
                # never to all the unselected homophones of the source.
                if not (kana(source_subject) and subject_face in subjects
                        and any(pos.startswith('名詞,') and rd==source_subject and base==subject_face
                            and not any(kind in pos for kind in ('固有名詞','接尾','非自立'))
                            for pos,form,base,rd in dictionary_inflections(subject_face) or ())):continue
                subjects=(subject_face,)
            if (case.end!=token.start and token.start-case.end not in
                    native_adverbial_reading_cuts(head[case.end:])):continue
            tail=head[token.end:]
            for lemma in native_verb_lexemes(token.surface,token.infl_form,token.reading):
                for face in _native_lexeme_forms(lemma,token.infl_form,token.reading):
                    if not kana(token.surface) and face!=token.surface:continue
                    if candidate_face is not None and face!=candidate_face:continue
                    if not any('一'<=c<='鿿' for c in face):continue
                    bases={base for pos,form,base,rd in dictionary_inflections(face) or ()
                           if pos.startswith('動詞,自立,') and form==token.infl_form and rd==token.reading}
                    if bases!={lemma} or native_verb_lexemes(face,token.infl_form,token.reading)!={lemma}:continue
                    if not _completed_native_verb_surface(face+tail,True,True,True):continue
                    subjects_proof=[subject_candidate_evidence(noun,face,tail) for noun in subjects]
                    objects_proof=[candidate_evidence(noun,face,tail) for noun in nouns]
                    if (all(p and p.get('predicate')==face and p.get('shared_roles') for p in subjects_proof)
                            and all(p and p.get('predicate')==face and p.get('case')=='を'
                                    and p.get('shared_roles') for p in objects_proof)):return True
    return False


def native_relative_nominal_cuts(text,parts):
    """Propose unchanged cuts without splitting a known lexical token.

    Unknown-token interiors are only boundary proposals. Each caller still
    proves the full original relative head, finite inflection, occupied
    cases and every whole noun's own meaning before returning evidence.
    No repaired reading or replacement text is parsed here.
    """
    from morphology import kana_syllable_boundary
    cuts={t.end for t in parts if 2<t.end<len(text)}
    for token in parts:
        if token.has_reading:continue
        cuts.update(cut for cut in range(max(3,token.start+1),min(token.end,len(text)))
                    if kana_syllable_boundary(text,cut))
    return tuple(sorted(cuts))


def native_bound_relative_nominal_parts(text):
    """An unchanged complete inflection can disambiguate a lexical overlap.

    The best full parse and the independently completed prefix may have
    different inflections. Preserve both dictionary checks: a familiar
    adverb or a following noun alone cannot certify this alternative.
    Returned tokens contain only the unedited original prefix, no spelling.
    A written independent verb is checked against its own single lexeme;
    the kana and written inputs never borrow each other's parsed tokens.
    """
    from morphology import tokenize,dictionary_inflections,kana_syllable_boundary,COLUMN_SEPARATOR
    if (not text or not 4<=len(text)<=80 or COLUMN_SEPARATOR.search(text)
            or any(c in text for c in '\r\n')):return ()
    parts=tokenize(text)
    def attested(token):
        return (token.has_reading and token.end==token.start+len(token.surface)
            and text[token.start:token.end]==token.surface
            and any(pos.startswith(token.pos+','+(token.pos_sub.replace(':',',')+',' if token.pos_sub else ''))
                and base==token.base_form and (form if form!='*' else '')==token.infl_form
                and rd==token.reading for pos,form,base,rd in dictionary_inflections(token.surface) or ()))
    for index,owner in enumerate(parts):
        if not (index and owner.pos=='副詞' and attested(owner)):continue
        # Literal source auxiliaries may separate the verb from the
        # overlapping adverb. Keep every intervening token's identity;
        # this cannot step across another lexical word or a gap.
        stem_index=index-1;edge=owner.start
        while stem_index>=0:
            previous=parts[stem_index]
            if not (previous.pos=='助動詞' and previous.end==edge and attested(previous)):break
            edge=previous.start;stem_index-=1
        if stem_index<0:continue
        stem=parts[stem_index]
        # A whole attested final particle may have a distinct verb entry.
        # The completed unedited prefix must independently prove that verb;
        # neither the particle's existence nor its reading chooses a spelling.
        if not (stem.end==edge and (stem.pos=='動詞' and stem.pos_sub=='自立'
                    or stem.pos=='助詞' and stem.pos_sub=='終助詞')
                and attested(stem)):continue
        kana_stem=(stem.surface==stem.reading
            and all('ぁ'<=ch<='ゖ' or ch=='ー' for ch in stem.surface))
        written_stem=(stem.pos=='動詞' and stem.pos_sub=='自立'
            and any('一'<=ch<='鿿' for ch in stem.surface))
        if not (kana_stem or written_stem):continue
        for cut in range(owner.start+1,owner.end):
            if not kana_syllable_boundary(text,cut):continue
            tail=text[cut:]
            if not all('ぁ'<=ch<='ゖ' or ch=='ー' for ch in tail):continue
            nouns=native_nominal_phrase_faces(tail)
            if not nouns:continue
            head=text[:cut];relative=native_written_relative_action(head)
            if not (relative and relative[1]==('が',) and head[stem.start:]==relative[0]
                    and native_attributive_predicate_end(head)
                    and _native_subject_kana_verb_nominal(head,relative,nouns,allow_written=written_stem)):continue
            prefix=tokenize(head)
            verb=next((t for t in prefix if t.start==stem.start and t.end==stem.end
                and t.surface==stem.surface and t.reading==stem.reading
                and t.pos=='動詞' and t.pos_sub=='自立' and attested(t)),None)
            if verb is None:continue
            # All preceding source words retain their exact original identity.
            fields=('surface','reading','pos','pos_sub','base_form','infl_form','start','end','has_reading')
            before=lambda seq:[tuple(getattr(t,k) for k in fields) for t in seq if t.end<=stem.start]
            if before(prefix)!=before(parts):continue
            original_auxiliaries=parts[stem_index+1:index]
            unchanged_auxiliaries=[t for t in prefix if stem.end<=t.start and t.end<=owner.start]
            identity=lambda seq:[tuple(getattr(t,k) for k in fields) for t in seq]
            if identity(unchanged_auxiliaries)!=identity(original_auxiliaries):continue
            auxiliaries=[t for t in prefix if t.start>=stem.end]
            if not (auxiliaries and auxiliaries[0].start==stem.end and auxiliaries[-1].end==cut
                    and all(a.end==b.start for a,b in zip(auxiliaries,auxiliaries[1:]))
                    and all(attested(t) and (t.pos=='助動詞' or t.pos=='助詞'
                        and t.pos_sub.startswith('接続助詞')) for t in auxiliaries)):continue
            return cut,tuple(nouns),stem.start,stem.end,tuple(prefix)
    return ()


def native_progressive_bound_relative_nominal_parts(text):
    """Verify an original whole reading against its complete te-auxiliary.

    An attested noun may overlap a literal verb/link/bound-verb sequence.
    Both analyses keep their own dictionary entries; the original whole
    surface and reading must be preserved. Only the same completed clause
    and each of its positively supported whole nouns certify the seam.
    """
    from morphology import tokenize,dictionary_inflections,kana_syllable_boundary,COLUMN_SEPARATOR
    from contextual_repair import _native_te_auxiliary_tail
    from semantic_roles import native_te_auxiliary_forms,candidate_evidence
    if (not text or not 4<=len(text)<=80 or COLUMN_SEPARATOR.search(text)
            or any(c in text for c in '\r\n')):return ()
    parts=tokenize(text)
    fields=('surface','reading','pos','pos_sub','base_form','infl_form','start','end','has_reading')
    identity=lambda seq:[tuple(getattr(t,k) for k in fields) for t in seq]
    kana=lambda value:bool(value) and all('ぁ'<=c<='ゖ' or c=='ー' for c in value)
    def attested(token):
        return (token.has_reading and token.end==token.start+len(token.surface)
            and text[token.start:token.end]==token.surface
            and any(pos.startswith(token.pos+','+(token.pos_sub.replace(':',',')+',' if token.pos_sub else ''))
                and base==token.base_form and (form if form!='*' else '')==token.infl_form
                and rd==token.reading for pos,form,base,rd in dictionary_inflections(token.surface) or ()))
    for owner in parts:
        if not (owner.pos=='副詞' and attested(owner)):continue
        for cut in range(owner.start+1,owner.end):
            if not kana_syllable_boundary(text,cut) or not kana(text[cut:]):continue
            nouns=native_nominal_phrase_faces(text[cut:])
            if not nouns:continue
            head=text[:cut];relative=native_written_relative_action(head)
            if not (relative and relative[1]==('が',) and native_attributive_predicate_end(head)):continue
            start=len(head)-len(relative[0]);prefix=tokenize(head)
            chain=[t for t in prefix if t.start>=start]
            if not (len(chain)>=4 and chain[0].start==start and chain[-1].end==cut
                    and all(a.end==b.start for a,b in zip(chain,chain[1:]))
                    and all(attested(t) for t in chain)):continue
            verb,link,aux=chain[:3]
            if not (verb.pos=='動詞' and verb.pos_sub=='自立'
                    and link.pos=='助詞' and link.pos_sub.startswith('接続助詞')
                    and aux.pos=='動詞' and aux.pos_sub.startswith('非自立')
                    and aux.end==owner.start and all(t.pos=='助動詞' for t in chain[3:])):continue
            forms=tuple(row for row in dictionary_inflections(verb.surface) or ()
                if row[0].startswith('動詞,自立,') and row[1]==verb.infl_form
                and row[2]==verb.base_form and row[3]==verb.reading)
            if not (forms and native_te_auxiliary_forms(aux.surface,aux.infl_form,aux.reading)
                    and _native_te_auxiliary_tail(forms,head[verb.end:],verb.reading,verb.surface)):continue
            original=[t for t in parts if start<=t.start and t.end<=owner.start]
            if not original or original[0].start!=start or original[-1].end!=owner.start:continue
            if not all(attested(t) for t in original):continue
            if identity(original)!=identity(chain[:3]):
                if not (len(original)==1 and original[0].pos=='名詞'
                        and not any(x in original[0].pos_sub for x in ('固有名詞','非自立','接尾'))
                        and kana(original[0].surface) and original[0].surface==original[0].reading
                        and ''.join(t.surface for t in chain[:3])==original[0].surface
                        and ''.join(t.reading for t in chain[:3])==original[0].reading):continue
            if identity([t for t in parts if t.end<=start])!=identity([t for t in prefix if t.end<=start]):continue
            if kana(verb.surface):
                if not _native_subject_kana_verb_nominal(head,relative,nouns):continue
            else:
                if not any('一'<=ch<='鿿' for ch in verb.surface):continue
                proofs=[candidate_evidence(noun,relative[0],'') for noun in nouns]
                if not all(proof and proof.get('predicate')==relative[0] and proof.get('case')=='を'
                        and proof.get('shared_roles') for proof in proofs):continue
            return cut,tuple(nouns),verb.start,verb.end,tuple(prefix)
    return ()


def _native_unknown_relative_prefix(text,original,cut,prefix):
    """Bind unchanged prefix tokens to one original unknown owner.

    A known token remains whole. The only changed known-token boundary is
    an entire native nominal prefix absorbed into its attested full adverb;
    the remainder must belong to the adjacent original unknown token.
    """
    from morphology import dictionary_inflections
    if not prefix or prefix[0].start!=0 or prefix[-1].end!=cut:return False
    if not all(a.end==b.start for a,b in zip(prefix,prefix[1:])):return False
    fields=('surface','reading','pos','pos_sub','base_form','infl_form','start','end','has_reading')
    identity=lambda t:tuple(getattr(t,k) for k in fields)
    def attested(t):
        return (t.has_reading and t.end==t.start+len(t.surface)
            and text[t.start:t.end]==t.surface
            and any(pos.startswith(t.pos+','+t.pos_sub.replace(':',',')+',')
                and base==t.base_form and (form if form!='*' else '')==t.infl_form
                and rd==t.reading for pos,form,base,rd in dictionary_inflections(t.surface) or ()))
    if not all(attested(t) for t in prefix):return False
    verb=prefix[-1]
    if not (verb.pos=='動詞' and verb.pos_sub=='自立' and verb.infl_form=='基本形'
            and verb.surface==verb.reading==verb.base_form
            and all('ぁ'<=c<='ゖ' or c=='ー' for c in verb.surface)):return False
    owners=[t for t in original if not t.has_reading and t.start<=verb.start<cut<t.end]
    if len(owners)!=1:return False
    owner=owners[0]
    if not (0<=owner.start<owner.end<=len(text)
            and owner.end==owner.start+len(owner.surface)
            and text[owner.start:owner.end]==owner.surface
            and owner.base_form==owner.surface==owner.reading
            and all('ぁ'<=c<='ゖ' or c=='ー' for c in owner.surface)):return False
    before=[t for t in original if t.end<=owner.start]
    if (not before or before[0].start!=0 or before[-1].end!=owner.start
            or not all(a.end==b.start for a,b in zip(before,before[1:]))):return False
    for old in before:
        if any(identity(old)==identity(t) for t in prefix):continue
        if not (old.end==owner.start and old.pos=='接頭詞' and old.pos_sub=='名詞接続'
                and attested(old) and any(t.start==old.start<owner.start<t.end<=verb.start
                    and t.pos=='副詞' and t.surface==t.reading
                    and t.surface.startswith(old.surface) for t in prefix)):return False
    for token in prefix:
        if token.start>=owner.start:continue
        if any(identity(token)==identity(t) for t in before):continue
        if not (token.pos=='副詞' and token.start==before[-1].start
                and token.start<owner.start<token.end<=verb.start):return False
    return True


def native_dictionary_relative_nominal_parts(text,subject_face=None):
    """Prove a whole source word's finite alternative without repairing it.

    The best parse and the alternative keep separate dictionary identities.
    An already attested independent basic verb retains its original token.
    Only the same literal reading, occupied subject and every whole noun's
    positive one-lexeme relation can support a different grammatical role.
    Returned tokens contain original text, never a selected output spelling.
    """
    from morphology import tokenize,dictionary_inflections,Token,COLUMN_SEPARATOR
    if (not text or not 4<=len(text)<=80 or COLUMN_SEPARATOR.search(text)
            or any(c in text for c in '\r\n')):return ()
    kana=lambda value:bool(value) and all('ぁ'<=c<='ゖ' or c=='ー' for c in value)
    parts=tokenize(text)
    for owner in parts:
        finite_owner=(owner.pos=='動詞' and owner.pos_sub=='自立'
                      and owner.infl_form=='基本形' and owner.base_form==owner.surface)
        if not ((owner.pos=='副詞' or finite_owner)
                and owner.has_reading and kana(owner.surface)
                and owner.surface==owner.reading and 0<owner.start<owner.end<len(text)
                and owner.end==owner.start+len(owner.surface)
                and text[owner.start:owner.end]==owner.surface):continue
        entries=dictionary_inflections(owner.surface) or ()
        if not any(pos.startswith(owner.pos+','+owner.pos_sub.replace(':',',')+',')
                and base==owner.base_form and (form if form!='*' else '')==owner.infl_form
                and rd==owner.reading for pos,form,base,rd in entries):continue
        finite=tuple((pos,form,base,rd) for pos,form,base,rd in entries
            if pos.startswith('動詞,自立,') and form=='基本形'
            and base==owner.surface and rd==owner.reading)
        if not finite:continue
        cut=owner.end;tail=text[cut:]
        if any(t.start==cut and t.end==len(text) and t.has_reading
               and t.pos in ('助詞','助動詞') for t in parts):continue
        nouns=native_nominal_phrase_faces(tail) if kana(tail) else _native_written_nominal_faces(tail)
        if not nouns:continue
        before=[t for t in parts if t.end<=owner.start]
        if not (before and before[0].start==0 and before[-1].end==owner.start
                and all(t.has_reading and text[t.start:t.end]==t.surface for t in before)
                and all(a.end==b.start for a,b in zip(before,before[1:]))):continue
        # A finite dictionary form certifies this unchanged suffix, while
        # the existing helper proves the actual ga/adverb and both meanings.
        for pos,form,base,rd in finite:
            verb=owner if finite_owner else Token(owner.surface,'動詞',base,rd,owner.start,owner.end,True,'自立',form)
            prefix=tuple(before+[verb]);head=text[:cut]
            if _native_subject_kana_verb_nominal(head,(owner.surface,('が',)),nouns,source_parts=prefix,subject_face=subject_face):
                return cut,tuple(nouns),owner.start,owner.end,prefix
    # A separate parse of an unchanged completed prefix may expose the
    # verb inside an original unknown owner. Every known token stays whole,
    # and this remains conditional on one subject and one verb meaning.
    for cut in native_relative_nominal_cuts(text,parts):
        if not any(not t.has_reading and t.start<cut<t.end for t in parts):continue
        tail=text[cut:]
        nouns=native_nominal_phrase_faces(tail) if kana(tail) else _native_written_nominal_faces(tail)
        if not nouns:continue
        head=text[:cut];prefix=tuple(tokenize(head))
        if not _native_unknown_relative_prefix(text,parts,cut,prefix):continue
        verb=prefix[-1]
        if _native_subject_kana_verb_nominal(head,(verb.surface,('が',)),nouns,
                source_parts=prefix,subject_face=subject_face):
            return cut,tuple(nouns),verb.start,verb.end,prefix
    return ()


def native_dictionary_subject_spelling(text,start,end,face):
    """A subject spelling conditionally proves the same complete source frame.

    Each unchanged source token and both predicates keep their own evidence.
    The subject's own inner meaning cannot certify another homophone or a
    global normal range. Candidate parsing is checked separately, never
    substituted for original positions, readings or the actual outer case.
    """
    from morphology import tokenize,dictionary_inflections,COLUMN_SEPARATOR,Token
    from contextual_repair import _finite_written_predicate
    from semantic_roles import candidate_nominal_spelling_evidence
    if (start!=0 or not 2<=end<len(text)<=80 or text[end:end+1]!='が'
            or COLUMN_SEPARATOR.search(text) or any(c in text for c in '\r\n')):return None
    if not all('ぁ'<=c<='ゖ' or c=='ー' for c in text[:end]):return None
    parts=tokenize(text)
    subject=next((t for t in parts if t.start==0 and t.end==end),None)
    if not (subject and subject.has_reading and subject.surface==subject.reading==text[:end]
            and subject.pos=='名詞' and not any(k in subject.pos_sub for k in ('固有名詞','接尾','非自立'))
            and any(pos.startswith('名詞,'+subject.pos_sub.replace(':',',')+',')
                and base==subject.base_form and (form if form!='*' else '')==subject.infl_form
                and rd==subject.reading for pos,form,base,rd in dictionary_inflections(subject.surface) or ())):return None
    fields=('surface','reading','pos','pos_sub','base_form','infl_form','start','end','has_reading')
    def identity(tokens,offset=0):
        return [tuple(getattr(t,k)+offset if k in ('start','end') else getattr(t,k) for k in fields) for t in tokens]
    for cut in native_case_positions(text,parts,('を',)):
        if not end<cut<cut+1<len(text):continue
        case=next((t for t in parts if t.start==cut and t.end==cut+1),None)
        unknown_case=case is None
        if unknown_case:
            # The projected case keeps a literal source position inside
            # one unknown owner; it is not an actual whole-text token.
            if not any(not t.has_reading and t.start<cut and t.end==cut+1 for t in parts):continue
            if text[cut:cut+1]!='を' or not any(pos.startswith('助詞,格助詞,')
                    and rd==base=='を' and form=='*'
                    for pos,form,base,rd in dictionary_inflections('を') or ()):continue
            case=Token('を','助詞','を','を',cut,cut+1,True,'格助詞:一般','')
        elif not (text[case.start:case.end]==case.surface=='を'
                and case.has_reading and case.reading=='を' and case.pos=='助詞' and case.pos_sub.startswith('格助詞')
                and any(pos.startswith('助詞,格助詞,') and rd==case.reading and base==case.base_form
                    and (form if form!='*' else '')==case.infl_form
                    for pos,form,base,rd in dictionary_inflections(case.surface) or ())):continue
        inner=native_dictionary_relative_nominal_parts(text[:case.start],subject_face=face)
        if not inner or not end+1<inner[2]<inner[3]==inner[0]<case.start:continue
        # Independent prefix analysis must preserve every preceding source
        # token; only the attested whole adverb/verb has a separate identity.
        unknown_prefix=_native_unknown_relative_prefix(text,parts,inner[0],inner[4])
        if not unknown_prefix:
            if identity([t for t in parts if t.end<=inner[2]])!=identity(inner[4][:-1]):continue
            owner=next((t for t in parts if t.start==inner[2] and t.end==inner[3]),None)
            if owner is None or owner.surface!=text[inner[2]:inner[3]]:continue
            original_inner=tokenize(text[:case.start])
            original_owner=next((t for t in original_inner if t.start==inner[2] and t.end==inner[3]),None)
            if original_owner is None or identity([owner])!=identity([original_owner]):continue
        if unknown_case and not unknown_prefix:continue
        if native_nominal_case_boundary(text,parts,case.start,'を',inner[1]) is None:continue
        tail=text[case.end:];core=tail[:-1] if tail[-1:] in '。！？.!?' else tail
        if not core or not _finite_written_predicate(core):continue
        if identity([t for t in parts if t.start>=case.end])!=identity(tokenize(tail),case.end):continue
        action=native_written_relative_action(core,allow_finite=True)
        if not action or action[1]:continue
        proofs=[candidate_nominal_spelling_evidence('',noun,text[case.start:]) for noun in inner[1]]
        if not all(p and p.get('predicate')==action[0] and p.get('case')=='を'
                   and p.get('shared_roles') for p in proofs):continue
        # This is an additional candidate-side check of the entire frame,
        # not a replacement of the conditional original evidence above.
        changed=face+text[end:];delta=len(face)-end
        if not all(native_object_predicate_proof(changed,case.end+delta,(noun,),return_action=True)==action[0]
                   for noun in inner[1]):continue
        return dict(source='conditional_original_relative_subject',subject=face,case='が',
            source_span=(start,end),verb_span=inner[2:4],noun_span=(inner[0],case.start),
            noun_faces=inner[1],outer_case=(case.start,case.end),outer_predicate=action[0])
    return None


def native_adverbial_stem_spelling(text,start,end,face):
    """The same whole na-stem in an attested original modifier sequence.

    This proves a modifier boundary, not a noun argument or normal clause.
    Each spelling owns its dictionary and token evidence; the common usage,
    candidate checks and original partial-frame retention still apply.
    """
    from morphology import tokenize,dictionary_inflections,COLUMN_SEPARATOR,native_spelling_only
    if (not 0<start<end<len(text)<=80 or COLUMN_SEPARATOR.search(text)
            or any(c in text for c in '\r\n') or not face):return False
    parts=tokenize(text)
    stem=next((t for t in parts if t.start==start and t.end==end),None)
    particle=next((t for t in parts if t.start==end),None)
    def attested(t,line):
        return bool(t and t.has_reading and t.end==t.start+len(t.surface)
            and line[t.start:t.end]==t.surface
            and any(pos.startswith(t.pos+',')
                and ':'.join(p for p in pos.split(',')[1:] if p!='*')==t.pos_sub
                and base==t.base_form and (form if form!='*' else '')==t.infl_form
                and rd==t.reading for pos,form,base,rd in dictionary_inflections(t.surface) or ()))
    def manner(stem,particle,line):
        return bool(attested(stem,line) and stem.pos=='名詞' and stem.pos_sub=='形容動詞語幹'
            and attested(particle,line) and particle.start==stem.end and particle.surface=='に'
            and (particle.pos=='助詞' and particle.pos_sub=='副詞化'
                or particle.pos=='助動詞' and particle.base_form=='だ' and particle.infl_form=='連用形'))
    if not manner(stem,particle,text):return False
    changed=text[:start]+face+text[end:];delta=len(face)-(end-start)
    if not native_spelling_only(text,changed):return False
    own=tokenize(changed)
    written=next((t for t in own if t.start==start and t.end==start+len(face)),None)
    following=next((t for t in own if t.start==start+len(face)),None)
    if not manner(written,following,changed) or written.reading!=stem.reading:return False
    fields=('surface','reading','has_reading','pos','pos_sub','base_form','infl_form','start','end')
    def identities(tokens,offset=0):
        return [tuple(getattr(t,k)+offset if k in ('start','end') else getattr(t,k) for k in fields) for t in tokens]
    if identities([t for t in parts if t.end<=start])!=identities([t for t in own if t.end<=start]):return False
    if identities([t for t in parts if t.start>=end],delta)!=identities([t for t in own if t.start>=start+len(face)]):return False
    # Use a real original subject-case edge, never a guessed noun start.
    # Every intervening modifier and the candidate's own cumulative edge
    # must be proved independently by the shared whole-token grammar.
    for case in parts:
        if not (case.end<start and case.surface=='が' and case.pos=='助詞'
                and case.pos_sub.startswith('格助詞') and attested(case,text)):continue
        if (particle.end-case.end in native_adverbial_reading_cuts(text[case.end:])
                and following.end-case.end in native_adverbial_reading_cuts(changed[case.end:])):return True
    return False


def native_dictionary_relative_retention(text,changes,start,end,face):
    """Recheck each later spelling under an already accepted subject choice.

    The original conditional frame is never added to normal ranges. All
    changes retain its exact source spans/readings, one verb sense and both
    cases. Candidate parsing checks only the candidate's own outer frame.
    """
    from morphology import native_spelling_only
    from contextual_repair import _apply
    if not changes:return False
    chosen={(a,b):word for a,b,word in changes}
    if len(chosen)!=len(changes) or (start,end) in chosen:return False
    subjects=[(a,b,word) for a,b,word in changes if a==0]
    if len(subjects)!=1:return False
    lo,subject_end,subject=subjects[0]
    proof=native_dictionary_subject_spelling(text,lo,subject_end,subject)
    if not proof:return False
    verb_span=proof['verb_span'];noun_span=proof['noun_span']
    from morphology import tokenize
    modifiers={(t.start,t.end) for t in tokenize(text)
        if t.pos=='名詞' and t.pos_sub=='形容動詞語幹' and subject_end<t.start<t.end<=verb_span[0]}
    if (start,end) not in {verb_span,noun_span}|modifiers:return False
    chosen[start,end]=face
    allowed={(0,subject_end),verb_span,noun_span}|modifiers
    if any(not native_adverbial_stem_spelling(text,a,b,word)
           for (a,b),word in chosen.items() if (a,b) in modifiers):return False
    if any(span not in allowed or not native_spelling_only(text[span[0]:span[1]],word)
           for span,word in chosen.items()):return False
    noun=chosen.get(noun_span)
    if noun is not None and noun not in proof['noun_faces']:return False
    inner=native_dictionary_relative_nominal_parts(text[:proof['outer_case'][0]],subject_face=subject)
    if not inner or inner[2:4]!=verb_span or inner[0]!=noun_span[0]:return False
    verb=chosen.get(verb_span)
    nouns=(noun,) if noun is not None else inner[1]
    if not _native_subject_kana_verb_nominal(text[:inner[0]],
            (text[verb_span[0]:verb_span[1]],('が',)),inner[1],
            source_parts=inner[4],candidate_face=verb,subject_face=subject):return False
    edits=sorted((a,b,word) for (a,b),word in chosen.items())
    if any(a[1]>b[0] for a,b in zip(edits,edits[1:])):return False
    changed=_apply(text,edits)
    case_end=proof['outer_case'][1]+sum(len(word)-(b-a) for a,b,word in edits)
    return all(native_object_predicate_proof(changed,case_end,(n,),return_action=True)
               ==proof['outer_predicate'] for n in nouns)


def native_written_action_nominal_parts(text):
    """Keep an actual completed action and its entire kana nominal tail.

    Native token ends expose possible seams, never output spellings. Every
    whole noun must fit the same written predicate's still-open object slot;
    neither a grammatical suffix nor another homophone supplies its meaning.
    """
    if (not text or not 4<=len(text)<=80 or not any('一'<=c<='鿿' for c in text)
            or any(c in text for c in '\r\n')):return ()
    from morphology import tokenize,dictionary_inflections,COLUMN_SEPARATOR
    if COLUMN_SEPARATOR.search(text):return ()
    from semantic_roles import candidate_evidence
    parts=tokenize(text)
    for cut in native_relative_nominal_cuts(text,parts):
        nominal=text[cut:]
        if not all('ぁ'<=c<='ゖ' or c=='ー' for c in nominal):continue
        # A whole original auxiliary/particle keeps its functional identity.
        # Whole-noun evidence may explain an internal seam, not rename
        # a single unchanged function word as a different lexical noun.
        if any(t.start==cut and t.end==len(text) and t.has_reading
               and t.pos in ('助詞','助動詞') for t in parts):continue
        faces=native_nominal_phrase_faces(nominal)
        if not faces:continue
        head=text[:cut];relative=native_written_relative_action(head)
        if not relative or 'を' in relative[1] or not native_attributive_predicate_end(head):continue
        action=relative[0]
        sahen=any(t.has_reading and t.pos=='名詞' and t.pos_sub=='サ変接続'
            and t.surface==t.base_form==action and t.end==t.start+len(action)
            and text[t.start:t.end]==action and t.end<cut
            and any(pos.startswith('名詞,サ変接続,') and base==action and rd==t.reading
                    for pos,form,base,rd in dictionary_inflections(action) or ())
            for t in parts)
        # A written ordinary verb retains its actual inflection and entire
        # relative tail. The whole head above already proved each occupied
        # case; a stripped tail cannot supply a missing subject relation.
        verb=any(t.has_reading and t.pos=='動詞' and t.pos_sub=='自立'
            and any('一'<=ch<='鿿' for ch in t.surface)
            and t.end==t.start+len(t.surface) and text[t.start:t.end]==t.surface
            and t.end<=cut and head[t.start:]==action
            and any(pos.startswith('動詞,自立,') and base==t.base_form
                    and form==t.infl_form and rd==t.reading
                    for pos,form,base,rd in dictionary_inflections(t.surface) or ())
            for t in parts)
        if not (sahen or verb):
            if _native_subject_kana_verb_nominal(head,relative,faces):return cut,tuple(faces)
            continue
        proofs=[candidate_evidence(face,action,'') if verb else
                native_argument_relative_object_evidence(head,face) if relative[1]
                else candidate_evidence(face,head,'') for face in faces]
        if all(proof and proof.get('predicate')==action and proof.get('case')=='を'
               and proof.get('shared_roles') for proof in proofs):return cut,tuple(faces)
    bound=native_bound_relative_nominal_parts(text) or native_progressive_bound_relative_nominal_parts(text) or native_dictionary_relative_nominal_parts(text)
    return bound[:2] if bound else ()


@lru_cache(maxsize=4096)
def native_written_relative_nominal_heads(text):
    """Native relative clause plus its exact, semantically fitting head."""
    if not text or not 4<=len(text)<=80 or all('ぁ'<=c<='ゖ' or c=='ー' for c in text):return ()
    from morphology import tokenize
    from semantic_roles import relative_action_support
    preference=native_written_preference_nominal_heads(text)
    if preference:return preference
    nominal=native_written_action_nominal_parts(text)
    if nominal:return nominal[1]
    # Reuse the same original occupied case, completed predicate and
    # every whole nominal face; this supplies grammar, not output spelling.
    argument_nominal=native_argument_relative_nominal_parts(text)
    if argument_nominal:return argument_nominal[1]
    out=[]
    for noun in tokenize(text):
        if noun.start<2 or noun.pos!='名詞' or not noun.has_reading:continue
        heads=_native_written_nominal_faces(text[noun.start:])
        relative=native_written_relative_action(text[:noun.start])
        if (relative and noun.end==len(text) and noun.pos_sub=='非自立:一般'
                and noun.surface in ('もの','こと')):
            # Native nominalizers denote the thing/event of their actual
            # finite clause. They do not guess a more specific noun sense.
            out.append(noun.surface)
        if relative and heads:
            out.extend(face for face in heads if relative_action_support(face,*relative,source_head=True))
    return tuple(dict.fromkeys(out))


@lru_cache(maxsize=4096)
def native_mixed_nominal_heads(text):
    """The same noun-compound relation with exact written/kana halves.

    Keep the written half's identity. Only the literal kana half may use
    its attested native nominal readings. Neither a different written
    homophone nor an unknown word can supply the other half's meaning.
    This supplies argument proof and chooses no output spelling.
    """
    kana=lambda value:bool(value) and all('ぁ'<=c<='ゖ' or c=='ー' for c in value)
    if not text or not 3<=len(text)<=32 or kana(text):return ()
    from morphology import tokenize
    from semantic_roles import nominal_compound_support
    parts=tokenize(text);out=[]
    for cut in range(1,len(text)):
        a,b=text[:cut],text[cut:]
        if kana(a)==kana(b):continue
        # Do not reopen an actual native lexical word at a proposed split.
        if any(t.has_reading and t.start<cut<t.end for t in parts):continue
        if kana(b):
            right_start=next((t for t in parts if t.start==cut),None)
            from morphology import dictionary_inflections,native_suru_form
            if (right_start and right_start.pos=='動詞' and right_start.base_form=='する'
                    and native_suru_form(right_start.surface,right_start.infl_form,right_start.reading,False)
                    and any(pos.startswith('名詞,サ変接続,') and base==a
                            for pos,form,base,rd in dictionary_inflections(a) or ())):continue
        left=native_nominal_phrase_faces(a) if kana(a) else _native_written_nominal_faces(a)
        if not left:continue
        right=native_nominal_phrase_faces(b) if kana(b) else _native_written_nominal_faces(b)
        out.extend(head for head in right if any(nominal_compound_support(prefix,head) for prefix in left))
    return tuple(dict.fromkeys(out))


@lru_cache(maxsize=4096)
def native_focused_nominal_parts(text):
    """Original noun/focus boundary with the same complete nominal proof."""
    from morphology import tokenize,dictionary_inflections
    for focus in ('だけ','ばかり','など'):
        if not text.endswith(focus) or len(text)<=len(focus):continue
        if not any(pos.startswith('助詞,副助詞,') and rd==focus
                   for pos,form,base,rd in dictionary_inflections(focus) or ()):continue
        boundary=len(text)-len(focus)
        faces=native_nominal_phrase_faces(text[:boundary])
        for face in faces:
            parts=tokenize(face+focus)
            if (parts and parts[-1].start==len(face) and parts[-1].has_reading
                    and parts[-1].surface==focus and parts[-1].pos=='助詞'
                    and parts[-1].pos_sub=='副助詞'):return (boundary,faces)
    return None


def _native_written_compound_nominal_heads(text):
    """The existing whole compound proof, shared without genitive recursion."""
    from morphology import tokenize,dictionary_inflections
    from semantic_roles import nominal_compound_support,nominal_roles
    parts=tokenize(text)
    def nominal(part):
        return (part.has_reading and not any(x in part.pos_sub for x in ('固有名詞','非自立'))
            and (part.pos=='名詞' or any(p.startswith('名詞,一般,')
                and base==part.surface and rd==part.reading
                for p,form,base,rd in dictionary_inflections(part.surface) or ())))
    if (2<=len(parts)<=4 and parts[0].start==0 and parts[-1].end==len(text)
            and all(nominal(t) for t in parts)):
        for tail in parts[1:]:
            left,right=text[:tail.start],text[tail.start:]
            if (not tail.pos_sub.startswith('接尾') and (nominal_roles(left) or _native_written_nominal_faces(left))
                    and _native_written_nominal_faces(right) and nominal_compound_support(left,right)):
                return (text,)
    return ()


@lru_cache(maxsize=4096)
def native_surface_nominal_heads(text, original_context=None):
    """48-ALT: the same nominal head in kana, written, or mixed genitives.

    Keep the exact written noun's meaning. Native の and both established
    nouns supply a phrase boundary; no reading of a different kanji is used.
    """
    if not text:return ()
    if original_context is not None and not original_context.startswith(text):return ()
    if all('ぁ'<=c<='ゖ' or c=='ー' for c in text):
        return native_nominal_phrase_faces(text)
    direct=_native_written_nominal_faces(text)
    if direct:return direct
    modified=native_written_adnominal_parts(text)
    if modified:return (modified[-1][0],)
    # A written personal plural retains the same nominal boundary as kana.
    if native_plural_nominal_heads(text):return (text,)
    linked=native_coordinated_nominal_heads(text)
    if linked:return linked
    te_nominal=native_te_nominal_heads(text)
    if te_nominal:return te_nominal
    mixed=native_mixed_nominal_heads(text)
    if mixed:return mixed
    relative=native_written_relative_nominal_heads(text)
    if relative:return relative
    compound=_native_written_compound_nominal_heads(text)
    if compound:return compound
    return tuple(dict.fromkeys(face for cut,left,right in native_genitive_nominal_splits(
        text,original_context=original_context) for face in right))


@lru_cache(maxsize=4096)
def native_preposed_object_parts(text,allow_written_predicate=False,*,object_start=None):
    """48-AKW: retain an earlier nominal case with the same content object.

    These are source ranges, not anomaly or action evidence. The final
    proof must fit both unchanged nouns to the very same finite action.
    A supplied object_start must follow an independently proved native
    adjunct; the returned first edge stays the original case-marker end.
    """
    if text and text[-1:] in '。！？.!?':text=text[:-1]
    # Both nominal arguments may each be one written character. Their
    # actual case markers and the same predicate proof own the boundary;
    # kana spelling length is not grammatical evidence.
    minimum=(2 if allow_written_predicate else 3)+4
    if not text or 'を' not in text or not minimum<=len(text)<=80:return ()
    from morphology import tokenize
    parts=tokenize(text);out=[]
    for case in (i for i in range(1,len(text)) if text[i] in 'がにへでとはも'):
        edge=case+1
        # A topic with a separate accusative object may fill the subject
        # role only with its own full predicate proof below. Do not infer
        # a topic boundary inside a longer native word such as momo.
        if text[case] in ('は','も') and not any(t.start==case and t.end==edge
                and t.surface==text[case] and t.reading==text[case]
                and t.has_reading and t.pos=='助詞' and t.pos_sub=='係助詞'
                for t in parts):continue
        prefix=text[:case]
        if (not prefix or native_nominal_temporal_prefix(text[:edge])
                or native_reflexive_manner_prefix(text[:edge])
                or native_counted_agent_prefix(text[:edge])):continue
        faces=native_surface_nominal_heads(prefix)
        if not faces or native_nominal_case_boundary(text,parts,case,text[case],faces,
                allow_known_noun=True,allow_compound_case=True) is None:continue
        begin=edge
        if object_start is not None:
            if not edge<object_start<len(text):continue
            from semantic_roles import _argument_prefix
            legacy=[(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,
                     t.has_reading,t.infl_form) for t in parts]
            if _argument_prefix(text,object_start,lambda _:legacy)[1]!=edge:continue
            begin=object_start
        for cut,objects in native_object_predicate_frames(text[begin:],allow_written_predicate):
            # A fully proved modified noun already owns an earlier case
            # (library-de borrowed-book). Do not attach that case again
            # to the main verb just because its kana can be sliced there.
            if native_nominal_phrase_faces(text[:begin+cut-1]):continue
            # A nominative clause is not itself an object nominal. Only
            # its positively proved full predicate and both arguments can
            # supply this new whole-clause scope to boundary-only callers.
            # Missing meaning does not create an error in the source.
            if text[case] in ('が','は','も'):
                from semantic_roles import proved_action_case_support
                action=native_object_predicate_proof(text[begin:],cut,objects,return_action=True)
                if not action or not any(proved_action_case_support(noun,'が',action,
                        context=text[begin:]) for noun in faces):continue
            out.append((edge,text[case],tuple(faces),begin+cut,objects))
    return tuple(out)


@lru_cache(maxsize=4096)
def native_object_predicate_frames(text,allow_written_predicate=False):
    """Unchanged native object/case evidence shared by source and repair."""
    return _native_nominal_predicate_frames(text,'を',allow_written_predicate)


@lru_cache(maxsize=2048)
def _native_nominal_predicate_frames(text,case_particle,allow_written_predicate=False):
    """One unchanged noun/case boundary with its complete predicate scope."""
    # A written finite verb can be two characters (見る / 読む). Its
    # native grammar and object meaning, not kana length, prove the source.
    predicate_minimum=2 if allow_written_predicate else 3
    # One attested noun character + one actual case + the same predicate
    # minimum. Written noun length does not change the grammatical frame.
    minimum=predicate_minimum+2
    if not text or not minimum<=len(text)<=80:
        return ()
    if case_particle not in text:
        return ()
    from morphology import tokenize
    original=tokenize(text)
    cuts=[]
    for cut in range(1,len(text)-predicate_minimum):
        if text[cut]!=case_particle or not predicate_minimum<=len(text)-cut-1<=18:continue
        remainder=text[cut+1:]
        kana=lambda value:all('ぁ'<=c<='ゖ' or c=='ー' for c in value)
        # 48-ALH: an unchanged written quantity uses the same exact
        # native counter as its kana reading; the remaining predicate
        # must still be literal kana. Ordinals are not quantities.
        adjuncts=()
        if not kana(remainder):
            native=tokenize(remainder)
            adjuncts=_native_counter_prefixes(remainder,native)
            from semantic_roles import _argument_prefix
            legacy=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                     t.start,t.end,t.has_reading,t.infl_form) for t in native]
            adjuncts=tuple(adjuncts)+tuple(t.start for t in native if t.start>0
                and kana(remainder[t.start:])
                and _argument_prefix(remainder,t.start,lambda _:legacy)[1]==0)
        if not kana(remainder) and not any(size<len(remainder) and kana(remainder[size:])
                for size in adjuncts):
            # 48-ALN: source preservation may inspect an unchanged written
            # predicate. Candidate target discovery keeps its existing scope.
            written=tokenize(remainder) if allow_written_predicate or remainder.endswith('下さい') else ()
            # A written request auxiliary keeps exactly the same kana
            # action slot. Its kanji spelling does not remove that boundary.
            legacy=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                     t.start,t.end,t.has_reading,t.infl_form) for t in written]
            request=bool(written and kana(remainder[:written[-1].start])
                         and _native_request_tail(legacy))
            if not allow_written_predicate and not request:written=()
            if allow_written_predicate:
                counts=_native_counter_prefixes(remainder,tokenize(remainder))
                if counts:written=tokenize(remainder[max(counts):])
            if not written or not all(part.has_reading for part in written):continue
        # This target proves a single object/predicate, not a later clause
        # or an additional argument. Actual native noun/case tokens establish
        # that boundary; accidental に inside an unknown reading does not.
        tail=[part for part in original if part.start>cut]
        # A native conditional auxiliary starts a following clause even
        # when its kana noun (えき) is missegmented as filler/auxiliaries.
        # This routine proves one predicate and must not consume that clause.
        # An auxiliary at the object edge has no earlier predicate to attest.
        if any(part.has_reading and part.pos=='助動詞' and part.infl_form=='仮定形'
               and cut+1<part.start and part.end<len(text) for part in tail):
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
        faces=native_surface_nominal_heads(text[:cut])
        if not faces:
            # The same unchanged adjective/relative-clause proof used for
            # source intactness also supplies the object head for repair.
            # A malformed modifier cannot borrow its corrected noun's fit.
            nominal=native_adnominal_reading_parts(text[:cut],allow_predicative=True)
            if nominal:faces=(nominal[-1][0],)
        if not faces and native_coordinated_nominal_parts(text[:cut]):
            # The unchanged written coordination keeps every member's role.
            # Reading and final case validation share the same source range.
            faces=(text[:cut],)
        if not faces and any(not ('ぁ'<=c<='ゖ' or c=='ー') for c in text[:cut]):
            # A single actual common noun retains its written meaning. The
            # candidate proof must not borrow a different homophone's roles.
            noun=next((t for t in original if t.start==0 and t.end==cut),None)
            if (noun and noun.has_reading and noun.pos=='名詞'
                    and not any(kind in noun.pos_sub for kind in ('固有名詞','接尾','非自立'))):
                faces=(noun.surface,)
        if faces and native_nominal_case_boundary(text,original,cut,case_particle,faces) is not None:
            cuts.append((cut+1,faces))
    if not cuts and case_particle=='を':
        cuts.extend((cut,faces) for edge,case,receiver,cut,faces in native_preposed_object_parts(text,allow_written_predicate))
    return tuple(cuts)


@lru_cache(maxsize=2048)
def native_nominal_connective_boundaries(text):
    """Exact source noun/copula/link proof survives a swallowed best parse.

    Only the already attested nominal predicate supplies a boundary. The
    following text is not certified, and no anomaly is invented by a cut.
    """
    if not text or len(text)>80:return ()
    import re
    matches=list(re.finditer('ので|から',text))
    if not matches:return ()
    if completed_native_nominal_predicate(text,allow_written=True):return ()
    from morphology import tokenize
    parts=tokenize(text);out=[]
    for m in matches:
        if m.end()>=len(text):continue
        actual=[part for part in parts if part.start<m.end() and m.start()<part.end]
        # Nなのです/なのでしょう uses the nominalizer の and a copula.
        # A known actual parse cannot be split into the causal connector.
        # An unknown token may still hide the independently proved boundary.
        if (actual and all(part.has_reading for part in actual)
                and not (len(actual)==1 and actual[0].start==m.start()
                    and actual[0].end==m.end() and actual[0].pos=='助詞'
                    and actual[0].pos_sub=='接続助詞')):continue
        if completed_native_nominal_predicate(text[:m.start()],
                connective=m.group(),allow_written=True):out.append(m.end())
    return tuple(out)



@lru_cache(maxsize=4096)
def native_object_clause_edges(text):
    """Grammatical object/link edges for replacement scope, not intactness.

    Missing semantic labels cannot turn an earlier clause into part of the
    next noun. This proof supplies only a boundary; meaning conflicts and
    the original replacement checks still apply independently.
    """
    if not text or len(text)>80 or 'を' not in text:return ()
    from morphology import tokenize
    from contextual_repair import _self_contained_conditional,_productive_predicate,_modern_te_allowed
    parts=tokenize(text);edges=[]
    for last in parts:
        conditional=_self_contained_conditional((last.surface,last.pos+(':'+last.pos_sub if last.pos_sub else ''),
            last.reading,last.start,last.end,last.has_reading,last.infl_form))
        linked=last.has_reading and last.pos=='助詞' and last.pos_sub=='接続助詞' and last.surface in ('て','で')
        if not (conditional or linked):continue
        # A bare native action also ends at its own actual te/de. This is
        # scope evidence only, never proof of the whole source's meaning.
        prefix=text[:last.end];native=tokenize(prefix)
        if (linked and len(native)>=2 and native[0].pos=='動詞'
                and all(t.has_reading for t in native)
                and _productive_predicate(prefix,native[0].surface)
                and _modern_te_allowed(native[-2].surface,native[-2].reading,last.surface) is True):
            edges.append(last.end);continue
        for begin in reversed([0]+edges):
            prefix=text[begin:last.end]
            for cut,faces in native_object_predicate_frames(prefix,True):
                predicate=prefix[cut:];native=tokenize(predicate)
                if (not native or not all(t.has_reading for t in native)
                        or native[0].pos not in ('動詞','名詞')
                        or not _productive_predicate(predicate,native[0].surface)):
                    continue
                if linked and (len(native)<2 or _modern_te_allowed(native[-2].surface,
                        native[-2].reading,last.surface) is not True):continue
                # This is not positive semantic evidence. Explicit conflicts
                # nevertheless cannot supply an unchanged completed edge.
                if _native_written_predicate_conflicts(prefix):continue
                edges.append(last.end);break
            if edges and edges[-1]==last.end:break
    return tuple(dict.fromkeys(edges))


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
    boundaries=list(native_nominal_connective_boundaries(text))
    parts=tokenize(text)
    # A conditional auxiliary or a connective swallowed by the best-path
    # kana split still ends its own independently proved original clause.
    # Project written lexical readings only when their identities survive.
    from contextual_repair import _self_contained_conditional
    for last in parts:
        conditional=_self_contained_conditional((last.surface,last.pos+(':'+last.pos_sub if last.pos_sub else ''),
            last.reading,last.start,last.end,last.has_reading,last.infl_form))
        if (not last.has_reading or last.end>=len(text)
                or not (conditional or last.pos=='助詞' and last.pos_sub=='接続助詞'
                        or last.pos=='接続詞' and last.surface.endswith(('て','で')))):
            continue
        prefix=text[:last.end];native=[t for t in parts if t.end<=last.end]
        if not native or native[0].start:continue
        if any(not t.has_reading and not all('ぁ'<=c<='ゖ' or c=='ー' for c in t.surface) for t in native):continue
        reading=''.join(t.surface if all('ぁ'<=c<='ゖ' or c=='ー' for c in t.surface) else t.reading for t in native)
        if not _written_predicate_reading_preserved(native,0,reading):continue
        constraints=[]
        for case in native:
            if not (case.surface=='を' and case.pos=='助詞' and case.pos_sub.startswith('格助詞')):continue
            faces=native_surface_nominal_heads(prefix[:case.start])
            noun_reading=''.join(t.surface if all('ぁ'<=c<='ゖ' or c=='ー' for c in t.surface) else t.reading
                                for t in native if t.end<=case.start)
            if faces:constraints.append((noun_reading,faces))
        if constraints:
            valid=any(completed_native_reading_link(reading,require_nominal=True,nominal_constraint=c)
                      for c in constraints)
        else:
            # A source subject keeps its own written sense too.
            from semantic_roles import subject_candidate_evidence
            subjects=[t for i,t in enumerate(native[:-1]) if native[i+1].surface=='が'
                      and native[i+1].pos=='助詞' and native[i+1].pos_sub.startswith('格助詞')]
            valid=(all('ぁ'<=c<='ゖ' or c=='ー' for c in prefix)
                   and completed_native_reading_link(reading,require_nominal=True))
            if len(subjects)==1:
                subject=subjects[0];after=next(t for t in native if t.start==subject.end)
                proof=subject_candidate_evidence(subject.surface,prefix[after.end:],'')
                valid=bool(proof and proof.get('shared_roles')
                           and completed_native_reading_link(reading,require_nominal=True))
        if valid:boundaries.append(last.end)
    for t in parts:
        if not (t.has_reading and t.pos=='助詞' and t.surface in ('て','で','から','ので','が')):continue
        if t.surface=='が' and t.pos_sub!='接続助詞':continue
        left,right=text[:t.end],text[t.end:]
        if completed_native_reading_link(left,require_nominal=True):
            boundaries.append(t.end)
        elif (any('一'<=c<='鿿' for c in left)
                and any(native_object_predicate_proof(left,cut,faces,allow_link=True)
                        for cut,faces in native_object_predicate_frames(left,True))):
            # The same unchanged written object, verb and native connective
            # terminate this clause even when the following clause is bad.
            # Its object must not become the next predicate's argument.
            boundaries.append(t.end)
        elif (native_object_predicate_frames(right)
                and (completed_native_reading_link(left)
                     or left.endswith(('て','で'))
                     and completed_native_verb_reading(left,True,require_roles=False))):
            # A short clause may omit its object while the next clause
            # has its own attested noun/case. Keep that native first
            # predicate; an unexplained bare tail alone supplies no seam.
            boundaries.append(t.end)
        elif (_completed_native_verb_surface(left,True,False,False)
                and any(part.has_reading and part.pos=='助詞' and part.surface=='を'
                        and part.pos_sub.startswith('格助詞')
                        and native_surface_nominal_heads(right[:part.start])
                        for part in tokenize(right))):
            # A bare written verb/link also ends before an independently
            # attested next object. Its malformed predicate need not already
            # pass the whole kana object/predicate parser to retain this edge.
            boundaries.append(t.end)
    # A truncated te/de prefix can hide a conflict that is explicit only
    # with its following independent clause. Keep that original full-context
    # anomaly authoritative before treating the prefix as completed source.
    conflicts=(_native_written_predicate_conflicts(text) if boundaries
        and any('一'<=ch<='龯' for ch in text) else ())
    # The full parse may read te+nai as an auxiliary although the
    # unchanged prefix has a complete object and connective predicate.
    # Reparse that source prefix; a candidate spelling supplies no seam.
    for case in parts:
        if not (case.has_reading and case.surface=='を' and case.pos=='助詞'
                and case.pos_sub.startswith('格助詞')):continue
        for edge in native_predicate_link_boundaries(text,case.end):
            if edge>=len(text):continue
            prefix=text[:edge]
            for cut,faces in native_object_predicate_frames(prefix,True):
                if cut==case.end and native_object_predicate_proof(prefix,cut,faces,allow_link=True):
                    boundaries.append(edge)
    return tuple(sorted(edge for edge in set(boundaries)
                        if not any(start<edge for noun,lemma,start,end in conflicts)))



@lru_cache(maxsize=4096)
def _native_adverbial_faces(reading):
    from corrector import table_surfaces_for_reading
    from morphology import dictionary_inflections
    from semantic_roles import adverbial_reading_needs_host
    # The classified whole nouns already carry their exact native readings.
    # Reuse them when a cost-filtered face list omits a common adverbial noun;
    # the actual adverbial POS and dependent-host check still decide entry.
    lexical=tuple(face for face in dict.fromkeys((reading,*table_surfaces_for_reading(reading,limit=8),
                  *_classified_nominal_readings().get(reading,())))
                  if not adverbial_reading_needs_host(face,reading)
                 and any(rd==reading and pos.startswith(('副詞,','名詞,副詞可能,'))
                         for pos,form,base,rd in dictionary_inflections(face) or ()))
    # 48-AMW/ANH: the proved activity + phase has native 副詞可能.
    # This licenses a temporal adjunct, not a generic time object or the
    # spatial/food meaning of its suffix/head. Keep the same whole noun.
    return tuple(dict.fromkeys(lexical+native_temporal_nominal_faces(reading)))


@lru_cache(maxsize=4096)
def _native_time_nominal_faces(reading,include_relative=False,include_ongoing=True):
    """Time nouns before an explicit particle, distinct from bare adverbs.

    48-ANC: a noun need not have native 副詞可能 when its actual に or
    までに supplies the adjunct relation. Bare adverb projection keeps its
    existing POS proof; ordinary places or an unknown noun gain nothing.
    """
    from semantic_roles import nominal_roles
    compounds=native_temporal_nominal_faces(reading,include_ongoing)
    kinds={'time','relative_time'} if include_relative else {'time'}
    faces=dict.fromkeys(_native_adverbial_faces(reading)+native_nominal_phrase_faces(reading))
    return tuple(face for face in faces if face in compounds or nominal_roles(face)&kinds)


def _native_counter_prefixes(text, original):
    # A whole unchanged lexical word owns its prefix. The native counter
    # table can otherwise recover a numeral split as particles or verbs.
    evidence={cut:native_counted_nominal_evidence(text[:cut])
              for cut in range(2,min(17,len(text)+1))}
    ordinals=[cut for cut,rows in evidence.items() if any(ordinal for unit,ordinal in rows)]
    return tuple(cut for cut,rows in evidence.items()
        if rows and any(not ordinal for unit,ordinal in rows)
        and not any(cut<end for end in ordinals)
        and not any(t.start==0 and t.has_reading and cut<t.end
            and t.pos in ('名詞','動詞','形容詞','副詞') for t in original))


@lru_cache(maxsize=4096)
def native_nominal_temporal_prefix(text):
    """48-AIU: an unchanged native N-no-mae/ato-ni supplies an adjunct edge.

    Reuse the temporal heads and an exact native nominal reading. The
    projected spelling only proves the original の + noun + に grammar;
    it neither changes the kana text nor certifies the following clause.
    """
    if not text.endswith('に') or not 3<=len(text)<=24:return False
    from morphology import tokenize,dictionary_inflections
    # 48-AKU: native adverbial time nouns also retain their explicit に.
    # An arbitrary noun or a location is not a temporal adjunct; the
    # following predicate and nominal frame still need their own proof.
    from semantic_roles import nominal_roles
    temporal=_native_time_nominal_faces(text[:-1])
    for face in temporal:
        # As with までに below, the unchanged whole time noun owns this
        # explicit case even when kana is segmented as another adverb.
        if native_nominal_case_boundary(face+'に',tokenize(face+'に'),len(face),'に',(face,)) is not None:
            return True
    # 48-ALX: the native limit particle plus に keeps an independently
    # attested time noun outside the later object. It is only an adjunct
    # boundary; no unknown object or unfinished predicate becomes normal.
    if text.endswith('までに'):
        for face in _native_time_nominal_faces(text[:-3],include_relative=True,include_ongoing=False):
            parts=tokenize(face+'までに');edge=len(face)
            if all(any(t.start==start and t.end==start+len(surface) and t.surface==surface
                    and t.has_reading and t.pos=='助詞' and t.pos_sub.startswith(sub) for t in parts)
                    for start,surface,sub in ((edge,'まで','副助詞'),(edge+2,'に','格助詞'))):
                return True
    if len(text)<5:return False
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
    # A written adjective supplies its own attested reading at the same
    # complete boundary; a split kana stem still uses the original kana.
    reading=first.reading if first.end==cut else text[:cut]
    return any(pos.startswith('形容詞,') and form=='連用テ接続'
               and base==first.base_form and rd==reading
               for pos,form,base,rd in dictionary_inflections(text[:cut]) or ())


@lru_cache(maxsize=1024)
def native_reflexive_manner_prefix(text):
    """48-ALD: an actual reflexive noun plus de is an unchanged adjunct.

    This boundary certifies neither a following action nor its arguments.
    It does not turn arbitrary person-de phrases into grammatical modifiers.
    """
    if not text.endswith('で') or not 3<=len(text)<=12:return False
    from semantic_roles import nominal_roles
    from morphology import tokenize
    prefix=text[:-1]
    kana=all('ぁ'<=c<='ゖ' or c=='ー' for c in prefix)
    faces=native_nominal_phrase_faces(prefix) if kana else _native_written_nominal_faces(prefix)
    reflexive=tuple(face for face in faces if 'reflexive_agent' in nominal_roles(face))
    return bool(reflexive and native_nominal_case_boundary(text,tokenize(text),
        len(text)-1,'で',reflexive,allow_compound_case=True) is not None)


@lru_cache(maxsize=1024)
def native_counted_agent_prefix(text):
    """An unchanged cardinal person count + de marks the acting group.

    The group's boundary supplies no proof of the following noun/action.
    Ordinals, non-person counters and arbitrary person nouns gain nothing.
    """
    if not text.endswith('で') or not 3<=len(text)<=20:return False
    prefix=text[:-1]
    if ('人',False) not in native_counted_nominal_evidence(prefix):return False
    from morphology import tokenize
    kana=all('ぁ'<=c<='ゖ' or c=='ー' for c in prefix)
    faces=native_counter_readings().get(prefix,()) if kana else (prefix,)
    return bool(faces and native_nominal_case_boundary(
        text,tokenize(text),len(prefix),'で',faces) is not None)


@lru_cache(maxsize=4096)
def native_adverbial_reading_cuts(text):
    """Unedited native adverbs, shared by source proof and argument ranges.

    The cut neither proves the following clause nor its anomaly. A known
    lexical word spanning the cut is not divided into an adverb and a noun.
    """
    if not text or not 4<=len(text)<=80:return ()
    from corrector import table_surfaces_for_reading
    from morphology import dictionary_inflections,tokenize
    original=tokenize(text);cuts=[];blocked_adverb=False
    # The same actual action noun/polite mismatch used by repair scopes
    # retains its lexical boundary before an alternative adverb parse.
    # A short homophonic adverb cannot erase a longer proved action head.
    action_ends=native_polite_action_prefixes(text)
    counter_cuts=_native_counter_prefixes(text,original)
    # Adjacent actual modifiers keep their own dictionary identities.
    # Their cumulative edge proves no clause or candidate spelling.
    def attested_modifier_token(token):
        return (token.has_reading and token.end==token.start+len(token.surface)
            and text[token.start:token.end]==token.surface
            and (token.surface==token.reading
                or token.pos=='名詞' and token.pos_sub=='形容動詞語幹')
            and all('ぁ'<=c<='ゖ' or c=='ー' for c in token.reading)
            and any(pos.startswith(token.pos+',')
                and ':'.join(p for p in pos.split(',')[1:] if p!='*')==token.pos_sub
                and base==token.base_form and (form if form!='*' else '')==token.infl_form
                and rd==token.reading for pos,form,base,rd in dictionary_inflections(token.surface) or ()))
    sequence_cuts=set();edge=0;members=0;index=0
    while index<len(original):
        token=original[index]
        if token.start!=edge or not attested_modifier_token(token):break
        count=1;end=token.end
        if token.pos=='副詞':
            if token.surface not in _native_adverbial_faces(token.reading):break
        elif token.pos=='形容詞':
            if not (token.infl_form=='連用テ接続' and token.surface.endswith('く')):break
            # The existing manner proof uses an unchanged suffix. Bind its
            # first token back to this whole original adjective explicitly.
            suffix=text[token.start:];parts=tokenize(suffix)
            if not (parts and parts[0].start==0 and parts[0].end==len(token.surface)
                    and all(getattr(parts[0],k)==getattr(token,k) for k in
                            ('surface','reading','has_reading','pos','pos_sub','base_form','infl_form'))
                    and native_adjective_adverbial_prefix(suffix,len(token.surface))):break
        elif token.pos=='名詞' and token.pos_sub=='形容動詞語幹' and index+1<len(original):
            # Keep the entire original na-stem and its real adverbial ni.
            # A same-reading general noun or case particle owns no such edge.
            particle=original[index+1]
            if not (particle.start==token.end and particle.surface=='に'
                    and attested_modifier_token(particle)
                    and (particle.pos=='助詞' and particle.pos_sub=='副詞化'
                        or particle.pos=='助動詞' and particle.base_form=='だ'
                            and particle.infl_form=='連用形')):break
            count=2;end=particle.end
        else:break
        edge=end;members+=1;index+=count
        if members>=2:sequence_cuts.add(edge)
    # A single attested na-stem plus adverbial ni owns a whole modifier
    # boundary too. Keep the existing cumulative cuts when more modifiers
    # follow; do not add a new intermediate written-stem cut to that chain.
    if members==1 and index==2:sequence_cuts.add(edge)
    # A written bound particle/auxiliary cannot become a free adverb
    # through a homophonic kanji entry (ほど / 程 before 貸します).
    # Unknown segmentation still has the existing dictionary fallback.
    if original and original[0].start==0 and original[0].has_reading:
        first=original[0]
        if (first.surface not in native_counter_readings()
                and (first.pos in ('助詞','助動詞') or first.pos in ('動詞','形容詞')
                     and not first.infl_form.startswith('連用'))):
            blocked_adverb=True
    # A complete native predicate can be two kana (見た / 寝る).
    # The caller still proves that whole suffix, not just its length.
    for cut in range(2,min(17,len(text)-1)):
        if any(cut<end for end in action_ends):continue
        if any(t.start==0 and t.has_reading and cut<t.end
               and t.pos in ('名詞','動詞','形容詞','副詞') for t in original):continue
        reading=text[:cut]
        # 48-ANR: the unchanged adverb can precede a written noun.
        # Its own prefix still needs exact kana-reading evidence; the
        # following script neither proves nor disqualifies this boundary.
        # A written na-stem has its own full dictionary reading/POS.
        # Reuse only the attested whole sequence, never a kana projection
        # or another spelling's token evidence. Other paths stay kana-only.
        if cut in sequence_cuts:
            cuts.append(cut);continue
        if not all('ぁ'<=c<='ゖ' or c=='ー' for c in reading):continue
        # An attested native counter may quantify an independently proved
        # object/predicate, using the same unchanged adverbial projection.
        # 48-AHD: the whole unchanged numeral/counter can be split as
        # a particle or a finite verb by the best parse (e.g. ni + satsu).
        # It has its own native counting proof. Keep the original ban for
        # other adverbs; a counter cut does not certify the following verb.
        # JPF, Bunpoo setsumei, pp.46-47: N + case + numeral/counter.
        if cut in counter_cuts:
            cuts.append(cut);continue
        if (native_nominal_temporal_prefix(reading) or native_reflexive_manner_prefix(reading)
                or native_counted_agent_prefix(reading)):
            cuts.append(cut);continue
        # The same exact time noun can span a swallowed は/も. Reuse
        # the native case proof instead of inventing a nominal boundary.
        if reading[-1] in ('は','も'):
            temporal=_native_time_nominal_faces(reading[:-1],include_relative=True)
            if temporal and native_nominal_case_boundary(text,original,cut-1,reading[-1],temporal) is not None:
                cuts.append(cut);continue
        if reading.endswith('に') and any(
                pos.startswith('名詞,形容動詞語幹,') and rd==reading[:-1]
                for face in native_nominal_phrase_faces(reading[:-1])
                for pos,form,base,rd in dictionary_inflections(face) or ()):
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
        # An attested compound adverb remains a word when following
        # kana makes the best parse fuse its particle with an auxiliary.
        heads=_native_adverbial_faces(reading[:-1])
        if any(pos.startswith('副詞,') and rd==reading for face in heads
               for pos,form,base,rd in dictionary_inflections(face+reading[-1]) or ()):
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
    return tuple(cuts)


@lru_cache(maxsize=4096)
def native_predicate_link_boundaries(text,predicate_start):
    """A known verb's connective ends its argument scope, not source meaning.

    An unclassified or conflicting earlier object cannot be borrowed by a
    later independent predicate. Only the unchanged native verb and link
    are proved here; this evidence does not mark that whole source intact.
    """
    from morphology import tokenize
    boundaries=[]
    # A native sahen head owns its actual して connection even when the
    # full best parse swallows し into a longer noun. This proves a seam,
    # not the whole clause's meaning or one of the head's homophones.
    for end in range(predicate_start+2,min(len(text)-1,predicate_start+18)+1):
        if text[end:end+2]!='して':continue
        heads=native_bare_action_faces(text[predicate_start:end])
        if heads and completed_sahen_reading(text[predicate_start:end+2],
                allow_nonpolite=True,return_action=True) in heads:
            boundaries.append(end+2)
    source_parts=tokenize(text)
    for link in source_parts:
        if not (link.has_reading and predicate_start<link.end):continue
        # A conditional auxiliary already closes this verb's own scope.
        # Keep the original verb/auxiliary parse: cutting the string can
        # turn the actual suru into an unrelated lexical head. This is
        # grammatical boundary evidence, not a proof of either clause's
        # arguments or meaning. Every intervening token must be a native
        # auxiliary in the same contiguous source range.
        from contextual_repair import _self_contained_conditional,_allows_grammatical_tail
        conditional=_self_contained_conditional((link.surface,
            link.pos+(':'+link.pos_sub if link.pos_sub else ''),link.reading,
            link.start,link.end,link.has_reading,link.infl_form))
        if conditional:
            native=[part for part in source_parts
                    if predicate_start<=part.start and part.end<=link.end]
            if (len(native)>=2 and native[0].start==predicate_start
                    and native[0].pos=='動詞' and native[0].pos_sub=='自立'
                    and native[-1].end==link.end
                    and all(part.has_reading for part in native)
                    and all(part.pos=='助動詞' for part in native[1:])
                    and ''.join(part.surface for part in native)==text[predicate_start:link.end]):
                from morphology import dictionary_inflections
                head=native[0]
                forms=tuple(row for row in dictionary_inflections(head.surface) or ()
                    if row[0].startswith('動詞,自立,') and row[1]==head.infl_form
                    and row[2]==head.base_form and row[3]==head.reading)
                if forms and _allows_grammatical_tail(forms,text[head.end:link.end],
                                                      head.reading,head.surface):
                    boundaries.append(link.end)
            continue
        parts=tokenize(text[predicate_start:link.end]);readings=[]
        original_link=link.pos=='助詞' and link.pos_sub=='接続助詞'
        # A following noun can absorb the past/aspect kana in the full parse.
        # The unchanged prefix must independently end in the same te/de link.
        recovered_link=bool(link.surface in ('て','で') and parts
            and parts[-1].surface==link.surface and parts[-1].has_reading
            and parts[-1].pos=='助詞' and parts[-1].pos_sub=='接続助詞')
        if not (original_link or recovered_link):continue
        for part in parts:
            if all('ぁ'<=c<='ゖ' or c=='ー' for c in part.surface):readings.append(part.surface)
            elif part.has_reading:readings.append(part.reading)
            else:break
        else:
            reading=''.join(readings)
            if (_written_predicate_reading_preserved(parts,0,reading)
                    and (completed_native_reading_link(reading,allow_unclassified=True)
                         or link.surface in ('て','で')
                         and native_adverbial_predicate_reading(reading,allow_open_tail=False))):
                boundaries.append(link.end)
    return tuple(boundaries)


@lru_cache(maxsize=4096)
def native_object_predicate_contexts(text,allow_written_predicate=False,include_written_mismatch=True):
    """Return (clause start, predicate start, faces) in the original text.

    Later boundaries require an independently completed preceding clause.
    Source intactness continues to prove the entire input separately.
    """
    if any(mark in text for mark in '、,;；'):
        clauses=list(_native_source_clauses(text))
        if len(clauses)>1:
            # The shared source splitter retains decimal quantities. A
            # later explicit object owns its clause even when the earlier
            # clause ends in an open continuative before a comma.
            return tuple((offset+begin,offset+cut,faces) for offset,clause in clauses
                for begin,cut,faces in native_object_predicate_contexts(clause,
                    allow_written_predicate,include_written_mismatch))
    result=[(0,cut,faces) for cut,faces in native_object_predicate_frames(text,allow_written_predicate)]
    if not text or 'を' not in text or not 6<=len(text)<=80:
        return tuple(result)
    if not allow_written_predicate and include_written_mismatch:
        # An existing written noun/polite mismatch shares the actual
        # object's validation even across a receiver or modifier. A proved
        # completed clause ends that ownership; its object never carries
        # into an unrelated later malformed predicate.
        from morphology import tokenize
        from oddness import polite_aux_mismatch
        parts=tokenize(text)
        legacy=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                 t.start,t.end,t.has_reading,t.infl_form) for t in parts]
        broken={a[3] for a,b in zip(legacy,legacy[1:])
                if a[4]==b[3] and a[5] and b[5]
                and a[1].startswith('名詞') and '固有名詞' not in a[1]
                and any('一'<=c<='鿿' for c in a[0]) and polite_aux_mismatch(a,b)}
        # The same owned native past mismatch must retain its written
        # object at final validation, not only at source discovery.
        from oddness import source_past_attachment_mismatch
        broken.update(a[3] for a,b in zip(legacy,legacy[1:])
                      if source_past_attachment_mismatch(text,tuple(a),tuple(b)))
        direct={a[3] for left,a in zip(legacy,legacy[1:]) if a[3] in broken
                and left[0]=='を' and left[1].startswith('助詞:格助詞') and left[5]
                and left[4]==a[3]}
        if broken:
            seams=native_completed_clause_boundaries(text)
            result.extend(row for row in native_object_predicate_contexts(text,True)
                          if any(row[1]<=edge and not any(row[1]<seam<=edge
                                 for seam in tuple(seams)+native_predicate_link_boundaries(text,row[1]))
                                 for edge in broken) and row not in result)
            # A literal new object after a real source particle owns its
            # own predicate even when the earlier written clause is outside
            # the kana clause recognizer. Reuse the same whole-noun proof;
            # never cut an unknown/compound noun down to a convenient head.
            for i,head in enumerate(parts):
                if head.start not in direct or i<2 or any(cut==head.start for _,cut,_ in result):continue
                noun=i-2;left=parts[i-1]
                if parts[noun].end!=left.start or parts[noun].pos!='名詞':continue
                begin=noun
                while (begin>0 and parts[begin-1].end==parts[begin].start
                       and (parts[begin-1].pos=='名詞' or parts[begin-1].pos=='接頭詞'
                            and parts[begin-1].pos_sub=='名詞接続')):begin-=1
                if (not all(p.has_reading for p in parts[begin:noun+1])
                        or begin==0 or not parts[begin-1].has_reading
                        or parts[begin-1].end!=parts[begin].start
                        or parts[begin-1].pos!='助詞'):continue
                start=parts[begin].start;fragment=text[start:]
                faces=native_surface_nominal_heads(text[start:left.start])
                if (faces and native_nominal_case_boundary(fragment,tokenize(fragment),
                        left.start-start,'を',faces) is not None):
                    result.append((start,head.start,faces))
    edges=set(native_completed_clause_boundaries(text)) | set(native_adverbial_reading_cuts(text))
    if allow_written_predicate:
        # Candidate validation shares grammatical seams; it does not need
        # an earlier clause's semantic label to locate a later object.
        edges.update(native_object_clause_edges(text))
        from morphology import tokenize
        for part in tokenize(text):
            if (part.has_reading and part.surface=='は' and part.pos=='助詞'
                    and part.pos_sub=='係助詞'
                    and native_surface_nominal_heads(text[:part.start])):
                edges.add(part.end)
    for edge in sorted(edges):
        # An already attested whole object reading owns its noun boundary.
        # Do not split that same noun into an adverb and a second object
        # merely because the malformed tail changed native segmentation.
        if any(begin<edge<cut for begin,cut,faces in result):continue
        frames=native_object_predicate_frames(text[edge:],allow_written_predicate)
        result.extend((edge,edge+cut,faces) for cut,faces in frames)
    return tuple(result)


@lru_cache(maxsize=4096)
def native_adverbial_predicate_reading(text, allow_open_tail=True, finite_only=False):
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
        if (completed_sahen_reading(predicate,allow_nonpolite=True,
                    allow_open_tail=allow_open_tail,finite_only=finite_only)
                or completed_native_verb_reading(predicate,allow_nonpolite=True,
                    require_roles=False,finite_only=finite_only)
                or (not native_adjective_adverbial_prefix(bare,cut) and (
                    completed_native_nominal_predicate(predicate)
                    or (completed_native_link_clause(predicate,require_nominal=True) if finite_only
                        else completed_native_reading_clause(predicate,require_nominal=True,
                            require_object_fit=True,allow_open_tail=allow_open_tail))))):
            return True
    return False


def _native_genitive_nominal_neighbor(text,parts,index,before=False):
    """An original adnominal particle and an unchanged whole native noun.

    The neighboring noun supplies only its own boundary, never meaning
    for the anomalous compound on the other side of the particle.
    """
    from morphology import dictionary_inflections
    link=parts[index]
    if (not link.has_reading or link.surface!='の' or link.reading!='の'
            or link.pos!='助詞' or link.pos_sub!='連体化'
            or link.end!=link.start+1 or text[link.start:link.end]!='の'
            or not any(pos.startswith('助詞,連体化,') and rd==link.reading
                       for pos,form,base,rd in dictionary_inflections(link.surface) or ())):return False
    if before:
        nouns=parts[:index]
        if not nouns or nouns[0].start!=0 or nouns[-1].end!=link.start:return False
    else:
        end=index+1
        while end<len(parts) and parts[end].pos=='名詞':end+=1
        nouns=parts[index+1:end]
        if not nouns or nouns[0].start!=link.end:return False
        if end<len(parts):
            tail=parts[end]
            if (not tail.has_reading or tail.start!=nouns[-1].end
                    or not (tail.pos=='助詞' and tail.pos_sub.startswith(('格助詞:','係助詞'))
                            or tail.pos=='助動詞' and tail.base_form in ('だ','です')
                            or tail.pos=='記号' and tail.surface in '。！？.!?')):return False
    if (any(a.end!=b.start for a,b in zip(nouns,nouns[1:]))
            or any(not t.has_reading or t.pos!='名詞'
                   or any(kind in t.pos_sub for kind in ('固有名詞','非自立'))
                   or text[t.start:t.end]!=t.surface
                   or not any(pos.startswith('名詞,')
                       and ':'.join(x for x in pos.split(',')[1:] if x!='*')==t.pos_sub
                       and base==t.base_form and rd==t.reading
                       and (form or '*')==(t.infl_form or '*')
                       for pos,form,base,rd in dictionary_inflections(t.surface) or ())
                   for t in nouns)):return False
    raw=text[nouns[0].start:nouns[-1].end]
    return bool(raw and native_surface_nominal_heads(raw))


def native_nominal_verb_prefix_ranges(text):
    """Keep a native continuative before an actual nominal-prefix boundary.

    A clause edge or the original case particle owns the verb onset.
    This protects only that verb, not the following noun or whole clause.
    """
    from morphology import tokenize,dictionary_inflections,native_suru_form
    out=[]
    for offset,clause in _native_source_clauses(text):
        parts=tokenize(clause)
        for index,head in enumerate(parts[:-2]):
            if head.start:
                previous=parts[index-1] if index else None
                case=(previous and previous.end==head.start and previous.has_reading
                      and previous.pos=='助詞' and previous.pos_sub.startswith('格助詞:'))
                genitive=(previous and previous.end==head.start and previous.surface=='の'
                          and head.surface in native_deverbal_nominal_faces(head.reading)
                          and _native_genitive_nominal_neighbor(clause,parts,index-1,True))
                if not (case or genitive):continue
            following=parts[index+1:]
            if (not head.has_reading or head.pos!='動詞' or head.pos_sub!='自立'
                    or head.infl_form!='連用形' or not 2<=len(head.surface)<=8
                    or not (any('一'<=c<='鿿' for c in head.surface)
                            or (following[0].has_reading and following[0].pos=='接頭詞'
                                and following[0].pos_sub=='名詞接続'))):continue
            if not any(pos.startswith('動詞,自立,') and form==head.infl_form and rd==head.reading
                       for pos,form,base,rd in dictionary_inflections(head.surface) or ()):continue
            end=head.end;nominal=False
            for position,token in enumerate(following,index+1):
                if token.start!=end:break
                if token.pos=='名詞' or token.pos=='接頭詞' and token.pos_sub=='名詞接続':
                    nominal=nominal or token.pos=='名詞';end=token.end;continue
                case=(token.has_reading and token.pos=='助詞'
                      and token.pos_sub.startswith(('格助詞:一般','係助詞')))
                action=(token.has_reading and token.pos=='動詞' and token.base_form=='する'
                        and native_suru_form(token.surface,token.infl_form,token.reading,False))
                copula=(token.has_reading and token.pos=='助動詞'
                        and token.base_form in ('だ','です'))
                genitive=(token.surface=='の' and head.surface in native_deverbal_nominal_faces(head.reading)
                          and _native_genitive_nominal_neighbor(clause,parts,position))
                if nominal and (case or action or copula or genitive):
                    out.append((offset+head.start,offset+head.end))
                break
            else:
                if nominal:out.append((offset+head.start,offset+head.end))
    return tuple(out)


@lru_cache(maxsize=4096)
def native_waiting_source_ranges(text):
    """The original waiting-state noun owns its head before a copular tail."""
    import re
    from morphology import tokenize
    found=[]
    for offset,clause in _native_source_clauses(text):
        parts=tokenize(clause)
        for match in re.finditer(r'(?:まち|待ち)(?=[だでな])',clause):
            end=match.end()
            if any(t.has_reading and t.start<end<t.end for t in parts):continue
            if native_waiting_nominal_faces(clause[:end]):found.append((offset,offset+end))
    return tuple(found)


def preserves_native_waiting_source(original,changed):
    spans=native_waiting_source_ranges(original)
    if not spans:return True
    from difflib import SequenceMatcher
    diffs=[(a,b,c,d) for tag,a,b,c,d in SequenceMatcher(None,original,changed,autojunk=False).get_opcodes() if tag!='equal']
    for start,end in spans:
        if any(a<end<b or a<start<b for a,b,c,d in diffs):return False
        lo=start+sum((d-c)-(b-a) for a,b,c,d in diffs if b<=start)
        hi=end+sum((d-c)-(b-a) for a,b,c,d in diffs if b<=end)
        face=changed[lo:hi]
        if face==original[start:end]:continue
        if not set(native_waiting_nominal_faces(original[start:end])) & set(native_waiting_nominal_faces(face)):return False
    return True


def preserves_native_nominal_verb_prefix(original,changed):
    """48-ALJ: unrelated noun repair cannot rewrite a native written head."""
    spans=native_nominal_verb_prefix_ranges(original)
    if not spans:return True
    from difflib import SequenceMatcher
    blocks=SequenceMatcher(None,original,changed,autojunk=False).get_matching_blocks()
    return all(any(block.a<=start and end<=block.a+block.size for block in blocks)
               for start,end in spans)



@lru_cache(maxsize=4096)
def native_pronoun_case_ranges(text):
    """An actual pronoun owns its native case/topic, despite an unknown tail.

    This is original grammatical evidence, not a guess about the next noun.
    In particular a malformed initial small kana cannot lend the preceding
    pronoun's particle to a different lexical reading.
    """
    from morphology import tokenize,dictionary_inflections
    parts=tokenize(text);out=[]
    for noun in parts:
        if not (noun.has_reading and noun.pos=='名詞' and noun.pos_sub.startswith('代名詞')):continue
        if not any(pos.startswith('名詞,代名詞,') and reading==noun.reading
                   for pos,form,base,reading in dictionary_inflections(noun.surface) or ()):continue
        # The next malformed onset can make the best parse swallow the
        # particle into a noun. The unchanged pronoun and native particle
        # entries establish the same source boundary independently.
        for end in range(noun.end+1,min(len(text),noun.end+3)+1):
            raw=text[noun.end:end]
            if any(pos.startswith(('助詞,格助詞,一般,','助詞,係助詞,','助詞,連体化,'))
                   and reading==raw for pos,form,base,reading in dictionary_inflections(raw) or ()):
                out.append((noun.end,end))
    return tuple(out)


def preserves_native_pronoun_case(original,changed):
    spans=native_pronoun_case_ranges(original)
    if not spans:return True
    from difflib import SequenceMatcher
    # A missing next onset may be inserted at the right edge. Preserve the
    # actual particle; do not freeze either neighbor or its written spelling.
    return not any(a<end and start<b or a==b and start<a<end
        for tag,a,b,c,d in SequenceMatcher(None,original,changed,autojunk=False).get_opcodes()
        if tag!='equal' for start,end in spans)


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


def _native_written_modifier_nominal_heads(text,parts):
    """Retain an actual modifier and the following noun's own whole proof.

    The modifier supplies no nominal meaning. Its original tokens must
    match the same dictionary forms before the existing nominal/compound
    proof is applied to the strictly shorter, unchanged remainder.
    """
    if (len(parts)<3 or parts[0].start!=0 or parts[-1].end!=len(text)
            or not all(t.has_reading for t in parts)
            or any(a.end!=b.start for a,b in zip(parts,parts[1:]))):return ()
    from semantic_roles import nominal_roles
    for index in range(1,len(parts)-1):
        cut=parts[index].start;prefix=text[:cut]
        if not any('一'<=c<='鿿' for c in prefix):continue
        proof=native_adnominal_modifier_parts(prefix,allow_written=True)
        original=parts[:index]
        if (not proof or len(proof)!=len(original)
                or ''.join(t.surface for t in original)!=prefix
                or any(row[0]!=t.surface or row[4]!=t.reading
                       or row[1].split(',')[0]!=t.pos or row[3]!=t.base_form
                       or (row[2] or '*')!=(t.infl_form or '*')
                       for row,t in zip(proof,original))):continue
        heads=native_surface_nominal_heads(text[cut:])
        supported=tuple(face for face in heads if nominal_roles(face))
        if supported:return supported
    return ()


@lru_cache(maxsize=4096)
def _native_written_nominal_faces(text):
    """An attested nominal head, retaining the written word's own senses.

    Sourced ordinary senses are alternatives, not tokenizer replacements.
    Proper-name readings and literal/source protections remain available.
    """
    from morphology import tokenize,dictionary_inflections,native_independent_adjective
    from general_words import sourced_common_noun_evidence
    def nominal(surface):
        from morphology import katakana_to_hiragana
        from general_words import general_katakana_noun_reading
        if (sourced_common_noun_evidence(surface)
                or general_katakana_noun_reading(surface,katakana_to_hiragana(surface))
                or any(p.startswith(('名詞,一般,','名詞,サ変接続,','名詞,代名詞,','名詞,副詞可能,'))
                       and base==surface for p,form,base,rd in dictionary_inflections(surface) or ())):
            return True
        # The same classified whole-noun evidence already serves kana.
        # A native compound is not lost only because it has multiple tokens.
        parts=tokenize(surface)
        return bool(parts and ''.join(t.surface for t in parts)==surface
            and all(t.has_reading and t.pos=='名詞' for t in parts)
            and all(a.end==b.start for a,b in zip(parts,parts[1:]))
            and native_common_noun_reading(surface,''.join(t.reading for t in parts)))
    if nominal(text):return (text,)
    if text.endswith('さ'):
        def legacy(value):
            return [(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,
                     t.has_reading,t.infl_form) for t in tokenize(value)]
        if nominalized_adjective_context(text,0,len(text),legacy):return (text,)
    containers=native_container_nominal_heads(text)
    if containers:return containers
    phased=(native_temporal_nominal_faces(text) or native_waiting_nominal_faces(text)
            or native_inchoative_nominal_faces(text) or native_action_value_nominal_faces(text))
    if phased:return phased
    derived=native_written_derived_nominal_faces(text)
    if derived:return derived
    parts=tokenize(text)
    # A literal kana modifier carries the same native adjective/copula
    # evidence before a written noun. The noun retains its own identity;
    # neither an unknown suffix nor a changed spelling proves this slot.
    for cut in range(2,len(text)):
        modifier=text[:cut]
        if not all('ぁ'<=c<='ゖ' or c=='ー' for c in modifier):break
        if not native_adnominal_modifier_parts(modifier):continue
        if any(t.has_reading and t.start==0 and cut<t.end for t in parts):continue
        from semantic_roles import nominal_roles
        heads=native_surface_nominal_heads(text[cut:])
        supported=tuple(face for face in heads if nominal_roles(face))
        if supported:return supported
    modified=_native_written_modifier_nominal_heads(text,parts)
    if modified:return modified
    if (len(parts)==2 and parts[0].start==0 and parts[0].end==parts[1].start
            and parts[1].end==len(text) and all(t.has_reading for t in parts)
            and parts[0].pos in ('連体詞','接頭詞') and nominal(parts[1].surface)):
        return (parts[1].surface,)
    # 48-APT: an unchanged independent adjective modifies an actual written
    # common noun. Its head supplies only the original noun's meaning; the
    # adjective neither proves an anomaly nor a corrected spelling.
    if (len(parts)==2 and parts[0].start==0 and parts[0].end==parts[1].start
            and parts[1].end==len(text) and all(t.has_reading for t in parts)
            and parts[0].pos=='形容詞' and parts[0].pos_sub=='自立'
            and parts[0].infl_form=='基本形' and parts[0].base_form==parts[0].surface
            and parts[1].pos=='名詞' and parts[1].pos_sub in ('一般','サ変接続')
            and any(native_independent_adjective(pos,form,base)
                    and base==parts[0].surface and rd==parts[0].reading
                    for pos,form,base,rd in dictionary_inflections(parts[0].surface) or ())
            and any(pos.startswith(('名詞,一般,','名詞,サ変接続,')) and base==parts[1].surface
                    and rd==parts[1].reading for pos,form,base,rd
                    in dictionary_inflections(parts[1].surface) or ())):
        from semantic_roles import nominal_roles
        if nominal_roles(parts[1].surface):return (parts[1].surface,)
    # A native na-adjective keeps the same actual nominal head too.
    # Its attributive copula cannot become a finite or case particle.
    if (len(parts)>=3 and parts[0].start==0 and parts[-1].end==len(text)
            and all(t.has_reading for t in parts)
            and all(a.end==b.start for a,b in zip(parts,parts[1:]))
            and parts[0].pos=='名詞' and parts[0].pos_sub=='形容動詞語幹'
            and parts[1].surface=='な' and parts[1].pos=='助動詞'
            and parts[1].base_form=='だ' and parts[1].infl_form=='体言接続'
            and any(pos.startswith('名詞,形容動詞語幹,')
                    and base==parts[0].base_form and rd==parts[0].reading
                    for pos,form,base,rd in dictionary_inflections(parts[0].surface) or ())
            and any(pos.startswith('助動詞,') and base=='だ' and form=='体言接続' and rd=='な'
                    for pos,form,base,rd in dictionary_inflections(parts[1].surface) or ())):
        from semantic_roles import nominal_roles
        heads=native_surface_nominal_heads(text[parts[1].end:])
        supported=tuple(face for face in heads if nominal_roles(face))
        if supported:return supported
    if (len(parts)==2 and parts[0].start==0 and parts[0].end==parts[1].start
            and parts[1].end==len(text) and all(t.has_reading and t.pos=='名詞'
                and (not any(x in t.pos_sub for x in ('固有名詞','接尾','非自立'))
                     or bool(sourced_common_noun_evidence(t.surface))) for t in parts)):
        from semantic_roles import relational_nominal_support
        if relational_nominal_support(parts[0].surface,parts[1].surface):
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
    import re
    quantities=native_numeric_quantity_spans(text) if re.search('[0-9０-９]',text) else ()
    masked=''.join('x' if ch in '.,' and any(a<=i<b for a,b in quantities) else ch
                   for i,ch in enumerate(text)) if quantities else text
    # Keep numeric punctuation inside quantities, but never borrow a later
    # column or an arrow's opposite side as this phrase's grammar context.
    from morphology import COLUMN_SEPARATOR,detached_symbol_separators
    separators=list(detached_symbol_separators(text))
    separators.extend(match.span() for match in re.finditer(
        COLUMN_SEPARATOR.pattern + r'|[。！？.!?、,;；「」『』“”"（）()]',masked))
    start=0
    for end,following in sorted(separators)+[(len(text),len(text))]:
        if start<end:
            raw=text[start:end];clause=raw.strip()
            if clause:yield start+len(raw)-len(raw.lstrip()),clause
        start=max(start,following)


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


@lru_cache(maxsize=2048)
def native_prolonged_adverb_ranges(text):
    """Share the original expressive adverb proof, not the following clause."""
    if not any(c in text for c in 'ぁぃぅぇぉ'):return ()
    from morphology import tokenize,native_prolonged_adverb_token_ranges
    return native_prolonged_adverb_token_ranges(tokenize(text))


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
        or native_adverbial_predicate_reading(ordinary,allow_open_tail=False,finite_only=True)
        or completed_native_reading_clause(ordinary,require_nominal=True,require_object_fit=True)
        or completed_native_reading_sequence(ordinary))


@lru_cache(maxsize=4096)
def native_continuative_source_boundaries(text):
    """Two original nominal-case clauses may join at an exact continuative.

    GPT-6 Astra / 2026-09-24: a written continuative is a clause link,
    not a missing te. Each clause retains its own original case and meaning;
    only an attested plain continuative verb ends the first one. Unfinished
    auxiliaries and te-onbin stems do not establish this source-only seam.
    """
    if not text or not 8<=len(text)<=80 or not all('ぁ'<=c<='ゖ' or c=='ー' for c in text):
        return ()
    from morphology import dictionary_inflections,tokenize
    boundaries=[]
    for cut in range(4,len(text)-3):
        left,right=text[:cut],text[cut:]
        # A complete right clause with its own explicit nominal argument
        # prevents a word-internal reading from masquerading as a boundary.
        if not completed_native_reading_clause(right,allow_nonpolite=True,
                require_nominal=True,require_object_fit=True):continue
        action=completed_native_reading_clause(left,allow_nonpolite=True,
            require_nominal=True,require_object_fit=True,allow_open_tail=True,return_action=True)
        if not isinstance(action,str) or not action:continue
        ending=_native_completed_action_suffix(left,action,native_surface=True,allow_open_tail=True)
        parts=tokenize(ending) if ending else ()
        last=parts[-1] if parts else None
        if (last and last.end==len(ending) and last.has_reading
                and last.pos=='動詞' and last.infl_form=='連用形'
                and any(pos.startswith('動詞,') and form=='連用形'
                        and base==last.base_form and rd==last.reading
                        for pos,form,base,rd in dictionary_inflections(last.surface) or ())):
            boundaries.append(cut)
    return tuple(boundaries)


@lru_cache(maxsize=4096)
def completed_native_source_sequence(text):
    """48-AIA: retain a complete source sequence inside its actual clause.

    Native adverb boundaries and a retained finite connective may surround
    the same proved sequence. No arbitrary substring or changed spelling
    supplies proof, and a following unproved clause remains outside it.
    """
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    if not bare or len(bare)>80 or not all('ぁ'<=c<='ゖ' or c=='ー' for c in bare):return False
    if native_continuative_source_boundaries(bare):return True
    if not any(link in bare for link in ('て','で','ら','が')):return False
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


@lru_cache(maxsize=4096)
def native_incomplete_polite_reading(text):
    """Source-only prefix of an attested polite ending; never completion.

    48-AMO / GPT-6 Astra / 2026-09-20: keep an unfinished native verb
    and its original arguments literal. The existing inflection table and
    full native predicate proof establish a prefix without guessing an edit.
    A completed ending, unknown stem or malformed attachment adds no proof.
    """
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    if (not bare or not 3<=len(bare)<=80 or 'ま' not in bare
            or not all('ぁ'<=c<='ゖ' or c=='ー' for c in bare)):return False
    from pos_grammar import _PIECES
    from morphology import tokenize,dictionary_inflections
    endings={tail for tail,state in _PIECES['R']
             if tail.startswith('ま') and state in ('END','TA')}
    for size in range(1,min(max(map(len,endings)),len(bare))):
        suffix=bare[-size:]
        # An attested open auxiliary may share a finite spelling. The
        # longer native ending and actual original seam still need proof.
        if suffix in endings and not any(pos.startswith('助動詞,')
                and base=='ます' and rd==suffix
                and form.startswith(('未然','連用'))
                for pos,form,base,rd in dictionary_inflections(suffix) or ()):continue
        for tail in sorted(endings,key=lambda value:(len(value),value)):
            if not len(suffix)<len(tail) or not tail.startswith(suffix):continue
            whole=bare+tail[len(suffix):]
            # 48-ANG: the same incomplete source can contain a proved
            # adverb or prior linked clause. Require their complete native
            # composition too; a bare noun/unknown prefix supplies no proof.
            if not (completed_native_reading_clause(whole,require_nominal=True,require_object_fit=True)
                    or completed_native_verb_reading(whole,require_roles=False)
                    or completed_sahen_reading(whole,allow_nonpolite=True,finite_only=True)
                    or native_adverbial_predicate_reading(whole,allow_open_tail=False)
                    or completed_native_source_sequence(whole)):continue
            # The best whole parse may swallow ます into one unknown token.
            # Only proved source adverbs, clause connections or an object case
            # may expose the same predicate and exact auxiliary offset.
            starts={0};pending=[0]
            while pending:
                begin=pending.pop();clause=whole[begin:]
                edges={*native_adverbial_reading_cuts(clause),*native_completed_clause_boundaries(clause),
                       *native_linked_reading_boundaries(clause,allow_unclassified=True)}
                edges.update(edge for left,edge,faces in native_object_predicate_contexts(clause))
                for edge in edges:
                    if 0<edge<len(clause) and begin+edge not in starts:
                        starts.add(begin+edge);pending.append(begin+edge)
            # 48-ANJ: lexical 増す can prove an adverb+verb while the
            # best parse calls the same ます an auxiliary. Its actual left
            # token must also supply the native polite attachment; the two
            # readings cannot lend each other half of the evidence.
            from oddness import polite_aux_mismatch
            for start in starts:
                predicate=whole[start:]
                sources=[(predicate,0)]
                # The kana parse can split the same sahen noun and call
                # its suru host an unrelated verb. Reuse the proved native
                # spelling with its literal tail and adjust only offsets.
                action=completed_sahen_reading(predicate,allow_nonpolite=True,
                    finite_only=True,return_action=True)
                written=_native_completed_action_suffix(predicate,action,native_surface=True)
                if written:sources.append((written,len(predicate)-len(written)))
                for surface,offset in sources:
                    parts=tokenize(surface)
                    for a,t in zip(parts,parts[1:]):
                        if not (start+offset+t.start==len(bare)-size and t.has_reading
                                and t.pos=='助動詞' and t.base_form=='ます'
                                and a.has_reading and a.pos in ('動詞','助動詞')
                                and a.end==t.start):continue
                        pair=[(x.surface,x.pos+(':'+x.pos_sub if x.pos_sub else ''),
                               x.reading,x.start,x.end,x.has_reading,x.infl_form) for x in (a,t)]
                        if not polite_aux_mismatch(*pair):return True
    return False


@lru_cache(maxsize=4096)
def native_incomplete_nominal_reading(text):
    """48-AMY: an unchanged source-final noun and its actual case/focus.

    This is an unfinished input, not a completed predicate or candidate.
    48-ANA: the whole attested noun may compete with a native verb/adjective
    parse. Its literal case is proved with that same noun; a source-final
    fragment has no following predicate whose meaning could be required.
    Interior fragments still obtain protection only from the actual source.
    """
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    if not bare or not 2<=len(bare)<=28:return False
    from morphology import tokenize
    for particle in ('から','より','を','が','に','へ','で','と','は','も'):
        if not bare.endswith(particle) or len(bare)<=len(particle):continue
        noun=bare[:-len(particle)]
        kana=all('ぁ'<=c<='ゖ' or c=='ー' for c in noun)
        faces=native_nominal_phrase_faces(noun) if kana else _native_written_nominal_faces(noun)
        if not faces:continue
        for face in faces:
            source=face+particle
            proof=native_nominal_case_boundary(source,tokenize(source),len(face),particle,(face,))
            if proof is not None and not proof[1]:return True
    return False


@lru_cache(maxsize=4096)
def native_incomplete_linked_reading(text):
    """Keep an unchanged native link followed by an attested open predicate.

    A complete first clause does not certify an unknown or malformed second
    one. Both sides use the existing native proof; this is source retention
    only and never supplies a completed generated candidate.
    """
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    if (not bare or len(bare)>80 or not all('ぁ'<=c<='ゖ' or c=='ー' for c in bare)
            or not any(link in bare for link in ('て','で','ら','が'))):return False
    # allow_open_tail also accepts completed tails. Prefer the existing
    # complete proof before classifying this whole source as unfinished.
    if native_linked_reading_boundaries(bare,allow_unclassified=True):return False
    return bool(native_linked_reading_boundaries(bare,
        allow_unclassified=True,allow_open_tail=True))


@lru_cache(maxsize=2048)
def native_incomplete_subject_predicate(text):
    """Retain an original noun + actual nominative + open continuative.

    This proves an unfinished source boundary, not the subject's meaning
    or a completed generated predicate. Every original token and native
    inflection stays unchanged; unknown tails and reopened cases add none.
    """
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    if not bare or not 3<=len(bare)<=80 or 'が' not in bare:return False
    from morphology import tokenize,dictionary_inflections
    parts=tokenize(bare)
    if len(parts)<3:return False
    case,verb=parts[-2:]
    if (not verb.has_reading or verb.pos!='動詞' or verb.pos_sub!='自立'
            or verb.infl_form!='連用形' or verb.end!=len(bare)
            or not case.has_reading or case.surface!=case.reading or case.surface!='が'
            or case.pos!='助詞' or case.pos_sub!='格助詞:一般'
            or case.end!=verb.start or case.end!=case.start+1
            or parts[0].start or any(a.end!=b.start for a,b in zip(parts,parts[1:]))
            or any(bare[t.start:t.end]!=t.surface for t in parts)):return False
    if not any(pos.startswith('動詞,自立,') and form==verb.infl_form
               and base==verb.base_form and rd==verb.reading
               for pos,form,base,rd in dictionary_inflections(verb.surface) or ()):return False
    if not any(pos.startswith('助詞,格助詞,一般,') and base==case.surface and rd==case.reading
               for pos,form,base,rd in dictionary_inflections(case.surface) or ()):return False
    noun=bare[:case.start]
    faces=native_surface_nominal_heads(noun,original_context=bare)
    if not faces or native_nominal_case_boundary(bare,parts,case.start,'が',faces) is None:
        return False
    # The harmless polite-tail grammar probe must retain this exact host;
    # a different token split after adding the auxiliary proves nothing.
    formed=tokenize(bare+'ます')
    if not any(t.start==verb.start and t.end==verb.end and t.surface==verb.surface
               and t.has_reading and t.reading==verb.reading and t.pos==verb.pos
               and t.pos_sub==verb.pos_sub and t.infl_form==verb.infl_form
               and t.base_form==verb.base_form for t in formed):return False
    return _native_continuative_verb_end(bare)


@lru_cache(maxsize=2048)
def native_incomplete_source_ranges(text):
    out=[]
    for start,clause in _native_source_clauses(text):
        if (native_incomplete_polite_reading(clause)
                or native_incomplete_nominal_reading(clause)
                or native_incomplete_linked_reading(clause)):
            out.append((start,start+len(clause)));continue
        if _native_written_predicate_conflicts(clause):continue
        if native_incomplete_subject_predicate(clause):
            out.append((start,start+len(clause)));continue
        # Use the same attested source noun/case seams as complete verbs.
        # This proves only an original unfinished suffix, never a candidate.
        contexts=tuple(dict.fromkeys(native_object_predicate_contexts(clause)+tuple(
            (0,cut,faces) for cut,faces in native_object_predicate_frames(clause,True))))
        for begin,cut,faces in contexts:
            if native_incomplete_polite_reading(clause[cut:]):
                out.append((start+begin,start+len(clause)))
    return tuple(dict.fromkeys(out))


def _preserves_source_ranges(original,changed,spans):
    if not spans:return True
    from difflib import SequenceMatcher
    return not any(a<end and start<b or a==b and start<=a<=end
                   for tag,a,b,c,d in SequenceMatcher(None,original,changed,autojunk=False).get_opcodes()
                   if tag!='equal' for start,end in spans)


def preserves_native_incomplete_source(original,changed):
    return _preserves_source_ranges(original,changed,native_incomplete_source_ranges(original))


def _native_continuative_verb_end(stem):
    from morphology import tokenize,dictionary_inflections
    from contextual_repair import _allows_grammatical_tail,_productive_predicate
    parts=tokenize(stem+'ます')
    auxiliary=next((t for t in parts if t.start==len(stem) and t.has_reading
        and t.pos=='助動詞' and t.base_form=='ます'),None)
    host=next((t for t in parts if t.end==len(stem)),None)
    if (auxiliary is None or host is None or not host.has_reading
            or host.pos!='動詞' or host.infl_form!='連用形'):return False
    forms=tuple((pos,form,lemma,rd) for pos,form,lemma,rd
        in dictionary_inflections(host.surface) or ()
        if pos.startswith('動詞,') and form=='連用形'
        and lemma==host.base_form and rd==host.reading)
    return bool(forms and _allows_grammatical_tail(forms,'ます',host.reading,host.surface)
        and _productive_predicate(host.surface+'ます',host.surface,before=stem[:host.start]))


@lru_cache(maxsize=2048)
def attested_historical_auxiliary_ranges(text):
    """Retain an attested source spelling of auxiliary 申す, never propose it.

    GPT-6 Astra / 2026-09-21: Daijisen/Nikkoku 申す attests historical
    まうす/まをす and the auxiliary's continuative-verb attachment.
    https://kotobank.jp/word/%E7%94%B3%E3%81%99-633322
    The existing polite predicate proves that unchanged host; ます is only
    grammatical evidence, never an output or a claimed native old spelling.
    An unproved earlier argument cannot erase a proved auxiliary's style.
    """
    if not any(form in text for form in ('まうす','まをす')):return ()
    from morphology import tokenize,dictionary_inflections
    from particle_frames import native_final_particle_sequence
    import re
    out=[]
    for start,clause in _native_source_clauses(text):
        if not 4<=len(clause)<=80:continue
        for match in re.finditer('まうす|まをす',clause):
            stem=clause[:match.start()];tail=clause[match.end():]
            parts=tokenize(tail)
            if not stem or ''.join(t.surface for t in parts)!=tail or not native_final_particle_sequence(parts):continue
            canonical=stem+'ます'+tail
            direct_host=_native_continuative_verb_end(stem)
            if not direct_host:
                # Recover the same attested action if the whole parse
                # swallowed its host. Every reconstruction still requires
                # the actual verb immediately before ます; contracted てます
                # therefore cannot prove historical 申す attachment.
                contexts=[canonical]
                contexts.extend(canonical[begin:] for begin,cut,faces
                    in native_object_predicate_contexts(canonical,allow_written_predicate=True))
                contexts.extend(canonical[edge:] for edge in native_completed_clause_boundaries(canonical))
                for context in contexts:
                    action=completed_native_reading_clause(context,require_object_fit=True,return_action=True)
                    native=_native_completed_action_suffix(context,action,native_surface=True)
                    if native and native.endswith('ます'+tail) and _native_continuative_verb_end(native[:-2-len(tail)]):
                        direct_host=True;break
                if not direct_host:continue
            if (completed_native_reading_clause(canonical,require_object_fit=True)
                    or completed_native_source_sequence(canonical)
                    or completed_written_object_clause(canonical)
                    or completed_native_verb_reading(canonical,True,False)
                    or completed_sahen_reading(canonical,finite_only=True)):
                out.append((start,start+len(clause)));continue
            # A written or linked earlier clause may be outside the same
            # whole-kana proof. Its actual object/predicate retains the same
            # existing native meaning and source coordinates.
            proved=False
            for begin,cut,faces in native_object_predicate_contexts(canonical,allow_written_predicate=True):
                if native_object_predicate_proof(canonical[begin:],cut-begin,faces):
                    out.append((start+begin,start+len(clause)));proved=True
            if proved:continue
            # Keep only the actual auxiliary when earlier meaning/grammar
            # is unproved. A native independent continuative verb is needed;
            # do not infer a host from an arbitrary known suffix in unknowns.
            if direct_host:
                out.append((start+match.start(),start+match.end()))
    return tuple(sorted(set(out)))


@lru_cache(maxsize=2048)
def native_polite_auxiliary_chains(text, include_open=False):
    """Native polite tails; optionally include a proved open continuative."""
    from morphology import tokenize
    parts=tokenize(text);out=[]
    for i,part in enumerate(parts):
        if not (part.has_reading and part.pos=='助動詞'
                and part.base_form in ('ます','です')):continue
        if i and parts[i-1].end==part.start and parts[i-1].pos=='助動詞' and parts[i-1].base_form in ('ます','です'):continue
        chain=[part]
        for following in parts[i+1:]:
            if following.start!=chain[-1].end or not following.has_reading or following.pos!='助動詞':break
            chain.append(following)
        edge=next((start+len(value) for start,value in _native_source_clauses(text)
                   if start<=part.start<start+len(value)),len(text))
        if chain[-1].infl_form not in ('基本形','体言接続','体言接続特殊'):
            from morphology import dictionary_inflections
            previous=parts[i-1] if i else None
            host=bool(previous and previous.has_reading and previous.end==part.start
                and (previous.pos in ('動詞','形容詞','名詞','助動詞')
                     or previous.pos=='助詞' and previous.surface in ('て','で')))
            if (include_open and host and len(chain)==1 and part.end==edge
                    and any(pos.startswith('助動詞,') and form=='連用形'
                            and base==part.base_form and rd==part.reading
                            for pos,form,base,rd in dictionary_inflections(part.surface) or ())):
                out.append((part.start,part.end,((part.surface,part.base_form),)))
            continue
        if len(chain)>1:
            # Native auxiliary tokens alone do not prove their attachment
            # (finite masu + volitional u / past ki). Reuse the same full
            # inflection check as candidate construction, without requiring
            # the possibly damaged host before this polite auxiliary.
            from contextual_repair import _productive_predicate
            if not _productive_predicate(text[part.start:chain[-1].end],
                    part.surface,before=text[:part.start]):continue
        # A finite-looking auxiliary inside a malformed lexical field does
        # not establish its own endpoint. Verify its following continuation
        # independently from the possibly damaged host before the auxiliary.
        from particle_frames import native_final_particle_sequence
        tail=[t for t in parts if chain[-1].end<=t.start<edge]
        if tail and not native_final_particle_sequence(tail):
            from contextual_repair import _FINITE_CONNECTIVES
            from pos_grammar import is_quotative_particle
            link=tail[0]
            if not (link.has_reading and link.pos=='助詞' and (
                    link.pos_sub=='接続助詞' and link.surface in _FINITE_CONNECTIVES
                    or is_quotative_particle(link.surface,'助詞:'+link.pos_sub))):continue
            if len(tail)>1 and not all(t.has_reading for t in tail[1:]):continue
        out.append((part.start,chain[-1].end,tuple((t.surface,t.base_form) for t in chain)))
    # An attested original object/case boundary remains available when
    # the full best parse absorbs a malformed predicate into an unknown
    # kana token. Reparse only that same source predicate; no corrected
    # spelling or candidate supplies the auxiliary's existence.
    if any(not t.has_reading for t in parts):
        for offset,clause in _native_source_clauses(text):
            bare=clause.rstrip('。！？.!?')
            for cut,faces in native_object_predicate_frames(bare):
                suffix=bare[cut:];native=tokenize(suffix)
                if not native or not native[0].has_reading or native[0].pos!='動詞':continue
                out.extend((offset+cut+a,offset+cut+b,sig)
                    for a,b,sig in native_polite_auxiliary_chains(suffix,include_open))
    return tuple(dict.fromkeys(out))


@lru_cache(maxsize=2048)
def native_independent_object_reading(text,start,end):
    """A complete source noun owns its actual case and fitting predicate."""
    if text[end:end+1]!='を':return False
    if start not in (0,)+native_completed_clause_boundaries(text):
        # A proved earlier argument supplies the same original object seam.
        # Both complete nouns must fit that one action, not another sense
        # or a nominal guessed from only the ending of the source reading.
        from semantic_roles import proved_action_case_support
        for edge,case,nouns,predicate,objects in native_preposed_object_parts(text,True):
            if edge!=start or predicate!=end+1:continue
            action=native_object_predicate_proof(text[edge:],predicate-edge,objects,
                return_action=True)
            if action and any(proved_action_case_support(noun,case,action,
                    context=text[edge:]) for noun in nouns):break
        else:return False
    from morphology import tokenize
    original=text[start:];cut=end-start;faces=native_surface_nominal_heads(original[:cut])
    return bool(faces and native_nominal_case_boundary(original,tokenize(original),cut,'を',faces) is not None
        and native_object_predicate_proof(original,cut+1,faces,allow_link=True))


@lru_cache(maxsize=4096)
def native_negative_auxiliary_chains(text):
    """Actual negative auxiliary after an attested irrealis host."""
    from morphology import tokenize,dictionary_inflections
    parts=tokenize(text);out=[]
    for index,(host,aux) in enumerate(zip(parts,parts[1:])):
        if (not host.has_reading or not aux.has_reading or host.end!=aux.start
                or host.pos!='動詞' or not host.infl_form.startswith('未然')
                or aux.pos!='助動詞' or aux.base_form not in ('ない','ぬ','ん','まい')):continue
        # The volitional irrealis attaches u, not a negative auxiliary.
        # A best-path split of a complete loanword does not change that form.
        if host.infl_form=='未然ウ接続':continue
        if not any(p.startswith('動詞,') and f==host.infl_form and b==host.base_form
                   and r==host.reading for p,f,b,r in dictionary_inflections(host.surface) or ()):continue
        # A real irrealis/negative pair still needs its original host
        # attachment. Share the same native te/de-auxiliary mismatch used
        # in source grammar and candidate completion. An impossible bound
        # verb connection cannot turn a following noun reading into a
        # protected negation. Actual te/de links and dictionary compounds
        # retain their own proof; no candidate supplies this decision.
        if index:
            from morphology import native_te_auxiliary_attachment_mismatch
            if native_te_auxiliary_attachment_mismatch(parts[index-1],host):continue
        # An explicitly reviewed rare kana lemma alone cannot establish a
        # normal negative phrase against an independent source anomaly.
        # Unknown usage is not rare. A written host or an actual preceding
        # argument still establishes this negative construction locally.
        from kango_tier import is_restricted
        from morphology import source_column_bounds
        field=source_column_bounds(text,host.start,aux.end)
        if (is_restricted(host.base_form) and all('ぁ'<=c<='ゖ' for c in host.surface)
                and not any(field is not None and field[0]<=t.start and t.end<=host.start
                    and t.has_reading and t.pos=='助詞' and t.pos_sub.startswith('格助詞')
                    for t in parts[:index])):continue
        # A best-path irrealis + n may be the inside of one attested noun.
        # Its unchanged complete reading and following nominal case own
        # the boundary; the lexical ending is not a negative auxiliary.
        # A proved original te/de + auxiliary + negative chain owns its
        # ending even before a case-like connective. A homophonous noun
        # reading of only the auxiliary/negative pair cannot erase that
        # actual connection. Reuse the native tail proof from completion;
        # unrelated preceding text supplies no bound-verb evidence.
        linked_negative=False
        if index>=2 and host.pos_sub.startswith('非自立'):
            verb,link=parts[index-2:index]
            if (verb.has_reading and verb.pos=='動詞' and verb.end==link.start
                    and link.has_reading and link.pos=='助詞' and link.pos_sub=='接続助詞'
                    and link.surface in ('て','で') and link.end==host.start):
                from contextual_repair import _native_te_auxiliary_tail
                linked_negative=_native_te_auxiliary_tail(
                    dictionary_inflections(verb.surface) or (),text[verb.end:aux.end],
                    verb.reading,verb.surface)
        # A complete original noun after its actual written relative
        # action owns its internal nasal too. Share the same whole-word
        # boundary used by spelling, without borrowing a candidate face.
        if (not linked_negative and any(edge<=host.start and aux.end<=len(text)
                for head,edge,faces in native_written_sahen_nominal_parts(text))):continue
        following=parts[index+2] if index+2<len(parts) else None
        if (not linked_negative and following is not None and following.start==aux.end and following.has_reading
                and following.pos=='助詞' and following.pos_sub.startswith('格助詞')
                and _native_nominal_reading_faces(text[host.start:aux.end])):continue
        # The same completed native action-noun reading can contain a
        # short irrealis-looking prefix. Its independently attested finite
        # suru ending proves a word, not a negative auxiliary inside it.
        if completed_sahen_reading(text[host.start:].rstrip('。！？.!?'),
                allow_nonpolite=True,finite_only=True):continue
        # A complete native sahen connective also owns the lexical head
        # when a later independent clause/note follows it.
        if any(text[edge:edge+2]=='して' and aux.end<=edge
                and native_bare_action_faces(text[host.start:edge])
                and completed_sahen_reading(text[host.start:edge+2],allow_nonpolite=True)
                for edge in range(aux.end,min(len(text)-1,host.start+18))):continue
        # A source noun after a completed clause can begin with nai.
        # Share its full nominal/case/meaning proof; a prefix-only noun
        # lookup cannot erase a real original negative auxiliary.
        if any(case.has_reading and case.surface=='を' and aux.end<case.start
                and case.pos=='助詞' and case.pos_sub.startswith('格助詞')
                and native_independent_object_reading(text,aux.start,case.start)
                for case in parts[index+2:]):continue
        # An independently proved N-no-unknown-case-action slot owns the
        # genitive key even when the best parse calls no+... an irrealis.
        # The unknown noun itself supplies no positive normality evidence.
        if (host.surface.startswith('の') and len(host.surface)>1
                and any(host.start<head<=host.end and aux.end<=case
                        for begin,head,case,finish in native_genitive_argument_slots(text))):
            continue
        out.append((aux.start,aux.end,aux.surface,aux.base_form))
    return tuple(out)


def preserves_native_negative_auxiliary(original,changed):
    chains=native_negative_auxiliary_chains(original)
    if not chains:return True
    from difflib import SequenceMatcher
    candidates=native_negative_auxiliary_chains(changed)
    blocks=SequenceMatcher(None,original,changed,autojunk=False).get_matching_blocks()
    # An independent edit may change the best parse of untouched text.
    # The identical host and negative tail remain their own evidence,
    # just as for the existing polite-auxiliary preservation contract.
    candidates=tuple(candidates)+tuple((block.b+a,block.b+b,word,base)
        for block in blocks if block.size
        for a,b,word,base in native_negative_auxiliary_chains(
            changed[block.b:block.b+block.size]))
    for start,end,word,base in chains:
        if not any(block.a<=start and end<=block.a+block.size
                   and (block.b+start-block.a,block.b+end-block.a,word,base) in candidates
                   for block in blocks):return False
    return True


def preserves_native_polite_auxiliary(original,changed):
    """Keep finite polite meaning, or complete the same open auxiliary."""
    # Existing spelling facts preserve this same auxiliary (しましょぅ
    # and しましょう). Compare their confirmed normal form without forcing
    # other pending spelling repairs to happen in the same replacement.
    from morphology import original_spelling_facts
    def canonical(text):
        for fact in reversed(original_spelling_facts(text)):
            if fact.rule=='SP-AUX-U':text=text[:fact.start]+fact.normal+text[fact.end:]
        return text
    original=canonical(original);changed=canonical(changed)
    finite=frozenset(native_polite_auxiliary_chains(original))
    chains=native_polite_auxiliary_chains(original,include_open=True)
    if not chains:return True
    from difflib import SequenceMatcher
    candidates=native_polite_auxiliary_chains(changed,include_open=True)
    blocks=SequenceMatcher(None,original,changed,autojunk=False).get_matching_blocks()
    # An earlier pending spelling edit can swallow an unchanged native host
    # into an unknown token. The identical block can independently attest
    # that same host/tail; never infer an auxiliary from arbitrary substrings.
    candidates=tuple(candidates)+tuple((block.b+c,block.b+d,sig)
        for block in blocks if block.size
        for c,d,sig in native_polite_auxiliary_chains(changed[block.b:block.b+block.size],include_open=True))
    for start,end,signature in chains:
        if (start,end,signature) not in finite:
            # An open continuative is already polite, but its inflection
            # is unfinished. Keep the actual auxiliary family at the same
            # source anchor while allowing its ending to be completed.
            if not any(a<=start<a+size
                       and any(c==b+start-a and sig[0][1]==signature[0][1]
                               for c,d,sig in candidates) for a,b,size in blocks):return False
            continue
        if not any(a<=start and end<=a+size
                   and any(c<=b+start-a and b+end-a<=d and signature==sig for c,d,sig in candidates)
                   for a,b,size in blocks):return False
    return True


def preserves_attested_historical_auxiliary(original,changed):
    return _preserves_source_ranges(original,changed,attested_historical_auxiliary_ranges(original))


def _written_nominal_case_chain_allowed(parts,end):
    """An independently broken actual case chain cannot prove a derived noun.

    A kana-only reparse can borrow copular で and falsely accept でから.
    Reuse the anomaly check's actual native particle relationship instead.
    Only the immediately attached functional chain is inspected.
    """
    from oddness import case_particle_mismatch,object_particle_mismatch
    chain=[]
    for token in parts:
        if token.start<end:continue
        if token.start!=end or token.pos!='助詞':break
        chain.append(token);end=token.end
    for left,right in zip(chain,chain[1:]):
        lp=left.pos+':'+left.pos_sub;rp=right.pos+':'+right.pos_sub
        if (case_particle_mismatch(left.surface,lp,right.surface,rp)
                or object_particle_mismatch(left.surface,lp,right.surface,rp)):
            return False
    return True


@lru_cache(maxsize=2048)
def native_written_nominal_ranges(text):
    """48-ANX: preserve a whole written noun run, not its following grammar.

    The maximal original nominal run includes unknown tokens, so a known
    suffix cannot hide an unexplained preceding noun. Common-noun identity
    and compound/suffix readings come from the same written nominal proof.
    """
    if not any('一'<=c<='鿿' for c in text):return ()
    from morphology import tokenize,native_suru_form,dictionary_inflections
    parts=tokenize(text);groups=[];current=[]
    for part in parts:
        # The original nominal prefix is part of the same maximal run.
        # Proving only its following noun cannot freeze that fragment while
        # hiding an unproved attachment on the left. The whole run must
        # still have the ordinary complete nominal evidence below.
        nominal=(part.pos=='名詞' or part.pos=='接頭詞' and part.pos_sub=='名詞接続')
        if nominal and (not current or current[-1].end==part.start):
            current.append(part);continue
        if current:groups.append(current);current=[]
        if nominal:current=[part]
    if current:groups.append(current)
    # A native sahen noun followed by suru is the lexical head of a
    # predicate here. Bare noun identity alone cannot certify its argument
    # relation (e.g. 原因を絶命する). Keep that whole predicate with the
    # existing source grammar/meaning proof, including causatives/modifiers.
    verbal_starts={t.start for t in parts if t.has_reading and t.pos=='動詞'
        and t.base_form=='する'
        and native_suru_form(t.surface,t.infl_form,t.reading,False)}
    return tuple((group[0].start,group[-1].end) for group in groups
                 if all(t.has_reading for t in group)
                 and any('一'<=char<='鿿' for char in text[group[0].start:group[-1].end])
                 and group[-1].end not in verbal_starts
                 and _native_written_nominal_faces(text[group[0].start:group[-1].end])
                 and (not native_written_derived_nominal_faces(text[group[0].start:group[-1].end])
                      or _written_nominal_case_chain_allowed(parts,group[-1].end)))


def preserves_native_written_derivation(original,changed):
    """Retain only the proved maximal derived noun, not adjacent grammar."""
    spans=tuple((start,end) for start,end in native_written_nominal_ranges(original)
                if native_written_derived_nominal_faces(original[start:end]))
    return _preserves_source_ranges(original,changed,spans)


@lru_cache(maxsize=4096)
def source_honorific_name(text):
    """Share the existing source-only name/honorific grammar with anomaly checks.

    Unknown personal spelling remains undecided. This proof generates no
    name spelling and supplies no common-noun or person argument role.
    """
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    if not bare or not all('ぁ'<=c<='ゖ' or c=='ー' for c in bare):return False
    from pos_grammar import _HONORIFICS,explain_kana_run
    from morphology import dictionary_inflections
    suffixes=tuple(suffix for suffix in _HONORIFICS
        if bare.endswith(suffix) and len(bare)>len(suffix)
        and any(p.startswith('名詞,接尾,人名,') and rd==suffix
                for p,f,b,rd in dictionary_inflections(suffix) or ()))
    if not suffixes:return False
    if explain_kana_run(bare,no_words=True):return True
    # A native kana name can attest its exact original reading even when
    # the best parse splits it (ワタナベ -> わ + た + なべ). This is a
    # direct dictionary lookup, not a new name roster or spelling proposal.
    from loanword import hiragana_to_katakana
    for suffix in suffixes:
        name=bare[:-len(suffix)]
        for face in (name,hiragana_to_katakana(name)):
            if any(p.startswith('名詞,固有名詞,人名,') and rd==name
                   for p,f,b,rd in dictionary_inflections(face) or ()):return True
    return False


@lru_cache(maxsize=2048)
def source_honorific_name_ranges(text,case_only=False):
    from pos_grammar import _HONORIFICS
    out=[]
    for start,clause in _native_source_clauses(text):
        for suffix in _HONORIFICS:
            cut=clause.find(suffix)
            while cut>=0:
                end=cut+len(suffix)
                if source_honorific_name(clause[:end]):
                    if not case_only:out.append((start,start+end))
                    # Only this unchanged name and its actual grammatical
                    # ending are retained. The following predicate still
                    # has its own anomaly/meaning check and repair target.
                    from morphology import tokenize
                    parts=tokenize(clause)
                    particle=next((t for t in parts if t.start==end),None)
                    particle_end=particle.end if particle is not None else None
                    if (particle is None and end<len(clause) and any(not t.has_reading
                            and t.start<=end<end+1<=t.end for t in parts)):
                        # The already proved name may absorb its particle as
                        # one unknown token. Reparse its unchanged native
                        # honorific suffix; no spelling or person role is added.
                        projected=tokenize(suffix+clause[end:])
                        particle=next((t for t in projected if t.start==len(suffix)),None)
                        particle_end=end+particle.end-len(suffix) if particle is not None else None
                    if (particle is not None and particle.has_reading
                            and particle.pos=='助詞'
                            and particle.pos_sub.startswith(('格助詞','係助詞','連体化','並立助詞'))):
                        out.append((start,start+particle_end))
                        # A source name + genitive の modifies the same
                        # independently attested noun. This whole nominal
                        # proof is not a case edge or a generated noun face.
                        if (not case_only and particle.surface=='の'
                                and particle.pos_sub=='連体化'
                                and native_surface_nominal_heads(clause[particle_end:])):
                            out.append((start,start+len(clause)))
                    if not case_only and (_native_nominal_copula_tail(clause[:end],clause[end:])
                            or _native_nominal_copula_tail(suffix,clause[end:])):
                        # An unknown name may swallow its whole ending in the
                        # best parse. Its actual attested honorific supplies
                        # the already proved nominal edge, not a new noun.
                        out.append((start,start+len(clause)))
                cut=clause.find(suffix,cut+1)
    return tuple(sorted(set(out)))


@lru_cache(maxsize=4096)
def _opaque_source_nominal(noun):
    """The unchanged opaque source shape, shared by its actual case slots."""
    if not noun or not all('ぁ'<=c<='ゖ' or c=='ー' for c in noun):return False
    from corrector import _SMALL_KANA_HEADS,_MORA_TAIL_KANA
    if noun[0] in _SMALL_KANA_HEADS or any(
            c in _MORA_TAIL_KANA-{'ー'} and noun[i-1] in _SMALL_KANA_HEADS
            for i,c in enumerate(noun) if i):return False
    from morphology import tokenize
    nominal=tokenize(noun)
    return bool(len(nominal)==1 and not nominal[0].has_reading and nominal[0].surface==noun)


@lru_cache(maxsize=1)
def _opaque_case_markers():
    """Share the existing single-character case-role inventory."""
    from semantic_roles import CASE_VERB_ROLES
    return ('を','が')+tuple(sorted(case for case in CASE_VERB_ROLES if len(case)==1 and case not in ('を','が')))


@lru_cache(maxsize=4096)
def _opaque_predicate_roles(surface,following='',before='',case='を',normalized_action=None):
    """Use the same finite predicate's attested case, without naming its noun."""
    from semantic_roles import predicate_roles,_subject_predicate_roles
    if case!='が':
        return predicate_roles(normalized_action or surface,following,before,
            case=None if case=='を' else case)
    # Keep the whole finite predicate: isolated 眠り / よみ can be nouns.
    roles=_subject_predicate_roles(surface+following,'')[1]
    if roles:return roles
    tail=surface+following
    action=normalized_action or completed_sahen_reading(tail,allow_nonpolite=True,
        return_action=True,finite_only=True)
    if not action:return frozenset()
    from morphology import dictionary_inflections
    # Reuse the completed sahen's same native face and literal reading.
    # Its actual suffix remains present, including voice-changing forms
    # which the shared subject-role proof does not certify.
    roles=set()
    for pos,form,base,reading in dictionary_inflections(action) or ():
        if pos.startswith('名詞,') and reading and tail.startswith(reading):
            roles.update(_subject_predicate_roles(action+tail[len(reading):],'')[1])
    return frozenset(roles)


@lru_cache(maxsize=4096)
def _opaque_source_case_edges(clause,cases):
    """A literal case may be swallowed or independently tokenized exactly."""
    import morphology as M
    if M.original_spelling_facts(clause):return ()
    parts=M.tokenize(clause)
    if not parts or parts[0].has_reading or parts[0].start!=0:return ()
    out=[]
    for cut in range(3,min(parts[0].end+2,len(clause))):
        case=clause[cut-1]
        if case not in cases or not _opaque_source_nominal(clause[:cut-1]):continue
        # Do not take the first letter from a known following word. When
        # the unknown token ends before the case, require its actual token.
        kind='係助詞' if case=='は' else '格助詞'
        if cut>parts[0].end and not any(t.start==cut-1 and t.end==cut and t.has_reading
                and t.pos=='助詞' and t.pos_sub.startswith(kind) for t in parts):continue
        if any(pos.startswith('助詞,'+kind+',') and rd==case
               for pos,form,base,rd in M.dictionary_inflections(case) or ()):
            out.append((cut,case))
    return tuple(out)


@lru_cache(maxsize=4096)
def _opaque_simple_object_ranges(text):
    """Unchanged unknown nominal + actual case + complete native predicate.

    This only withholds source anomaly: it proves no noun or meaning,
    supplies no reading, and cannot certify a generated candidate.
    48-AOL / GPT-6 Astra / 2026-09-21; source scope, not a name list.
    """
    import morphology as M
    import contextual_repair as Q
    if not any(case in text for case in _opaque_case_markers()):
        return ()
    ranges = []
    for begin, clause in _native_source_clauses(text):
        if not 6<=len(clause)<=80 or clause.count('を')>1:continue
        for cut,case in _opaque_source_case_edges(clause,_opaque_case_markers()):
            tail = clause[cut:]
            # A following object owns its own meaning and predicate proof;
            # the shared preposed-object path validates that larger frame.
            if 'を' in tail:continue
            # Reuse the same finite native sahen reading, without giving
            # the unknown object a spelling or semantic classification.
            action=completed_sahen_reading(tail,allow_nonpolite=True,
                return_action=True,finite_only=True)
            if action and _opaque_predicate_roles(tail,case=case,normalized_action=action):
                ranges.append((begin,begin+cut,begin+len(clause)))
                continue
            parsed = M.tokenize(case + tail)
            # The source edge already attests the literal case lexeme.
            # Isolated で + sahen can be tagged as a conjunction, while
            # retaining the exact boundary and the same finite predicate.
            if (not parsed or parsed[0].surface!=case or parsed[0].start!=0
                    or parsed[0].end!=len(case) or not parsed[0].has_reading):
                continue
            parts = parsed[1:]
            if not parts or parts[0].start != 1 or not parts[0].has_reading:
                continue
            if not (parts[0].pos == '動詞' and parts[0].pos_sub == '自立'
                    or parts[0].pos == '名詞' and parts[0].pos_sub.startswith('サ変接続')):
                continue
            last = parts[-1]
            legacy = (last.surface, last.pos + ':' + last.pos_sub,
                      last.reading, last.start, last.end, last.has_reading, last.infl_form)
            if not (Q._completed_predicate_token(legacy) or Q._native_imperative_completion(parts)):
                continue
            if not Q._productive_predicate(tail, parts[0].surface, before=case):
                continue
            # A finite form alone does not establish the written case.
            # Existing verb roles attest that case, not this unknown noun's meaning.
            if not _opaque_predicate_roles(parts[0].surface,tail[len(parts[0].surface):],before=case,case=case):
                continue
            ranges.append((begin, begin+cut, begin+len(clause)))
    return tuple(ranges)


@lru_cache(maxsize=4096)
def _opaque_preposed_object_ranges(text):
    """An opaque case/genitive head before the same known object/action.

    GPT-6 Astra / 2026-09-21. Existing native_object_predicate_proof and
    predicate_roles attest the unchanged action and its actual case. A
    native genitive modifies only that known object. The opaque head
    acquires neither a word, a reading nor a semantic role.
    """
    if 'を' not in text:return ()
    from morphology import original_spelling_facts
    ranges=[]
    for begin,clause in _native_source_clauses(text):
        if not 8<=len(clause)<=80 or clause.count('を')!=1:continue
        if original_spelling_facts(clause):continue
        edges=list(_opaque_source_case_edges(clause,_opaque_case_markers()[1:]+('は',)))
        nominal=clause[:clause.index('を')]
        for cut,left,right in native_genitive_nominal_splits(nominal,allow_unknown_left=True):
            if not left and _opaque_source_nominal(nominal[:cut]):edges.append((cut+1,'の'))
        for cut,case in edges:
            remainder=clause[cut:]
            for start,edge,heads in native_object_predicate_contexts(remainder,allow_written_predicate=True):
                if start!=0:continue
                action=native_object_predicate_proof(remainder,edge,heads,return_action=True)
                if not action:continue
                # A genitive qualifies the proved noun, not the verb.
                # Other cases still belong to that same finite predicate;
                # its continuative can be a noun in isolation (わたし).
                # GPT-6 Astra / 2026-09-21: an unchanged topic may
                # occupy the subject slot of this same known object/action.
                # Keep literal は at the source edge; it grants the unknown
                # head no lexical meaning and no generated candidate proof.
                # https://www.coelang.tufs.ac.jp/mt/ja/gmod/contents/explanation/002.html
                role_case='が' if case=='は' else case
                if case!='の' and not (
                        _opaque_predicate_roles(remainder[edge:],before='を',case=role_case)
                        or role_case!='が' and _opaque_predicate_roles(action,case=role_case)):continue
                ranges.append((begin,begin+cut+edge,begin+len(clause)))
                break
    return tuple(dict.fromkeys(ranges))


@lru_cache(maxsize=4096)
def _known_subject_opaque_object_ranges(text):
    """The same native nominative subject and opaque accusative object.

    GPT-6 Astra / 2026-09-21: reuse exact nominal faces and the finite
    predicate's existing roles. This gives the unknown object no meaning.
    """
    if 'が' not in text or 'を' not in text:return ()
    from morphology import tokenize,original_spelling_facts
    from semantic_roles import nominal_role_matches
    out=[]
    for begin,clause in _native_source_clauses(text):
        if not 8<=len(clause)<=80 or original_spelling_facts(clause):continue
        for case in tokenize(clause):
            if not (case.surface=='が' and case.has_reading and case.pos=='助詞'
                    and case.pos_sub.startswith('格助詞') and case.start>0):continue
            noun=clause[:case.start];suffix=clause[case.end:]
            faces=(native_nominal_phrase_faces(noun) if all('ぁ'<=c<='ゖ' for c in noun)
                   else _native_written_nominal_faces(noun))
            if not faces:continue
            for start,edge,end in _opaque_simple_object_ranges(suffix):
                if start or end!=len(suffix) or suffix[edge-1]!='を':continue
                roles=_opaque_predicate_roles(suffix[edge:],case='が')
                if any(nominal_role_matches(face,roles) for face in faces):
                    out.append((begin,begin+case.end+edge,begin+len(clause)))
    return tuple(dict.fromkeys(out))


@lru_cache(maxsize=4096)
def source_opaque_object_ranges(text):
    """Keep an unchanged native prefix and opaque object as separate proofs."""
    ranges=list(_opaque_simple_object_ranges(text))
    ranges.extend(_opaque_preposed_object_ranges(text))
    ranges.extend(_known_subject_opaque_object_ranges(text))
    if not any(case in text for case in _opaque_case_markers()):return tuple(ranges)
    from morphology import tokenize
    for begin,clause in _native_source_clauses(text):
        if (not 9<=len(clause)<=80 or not any(case in clause for case in _opaque_case_markers())
                or any(a==begin and end==begin+len(clause) for a,cut,end in ranges)):
            continue
        parts=tokenize(clause)
        if not any(not t.has_reading for t in parts):continue
        adverbial=native_adverbial_reading_cuts(clause)
        for cut in range(2,len(clause)-5):
            # A shorter adverb cannot hide the rest of an already proved
            # longer prefix inside the opaque noun (しゅっ / 出発前に).
            if any(cut<edge for edge in adverbial):continue
            if any(t.has_reading and t.start<cut<t.end for t in parts):continue
            if (cut not in adverbial and not completed_native_reading_link(clause[:cut])):
                continue
            suffix=clause[cut:]
            for start,edge,end in (*_opaque_simple_object_ranges(suffix),
                                    *_opaque_preposed_object_ranges(suffix),
                                    *_known_subject_opaque_object_ranges(suffix)):
                if start==0 and end==len(suffix):
                    ranges.append((begin,begin+cut+edge,begin+len(clause)))
    return tuple(dict.fromkeys(ranges))


def preserves_opaque_source_object(original, changed):
    return _preserves_source_ranges(original,changed,
        tuple((start,end) for start,cut,end in source_opaque_object_ranges(original)))


@lru_cache(maxsize=4096)
def attested_source_expression(text):
    """Whole attested source expression/name or native adjective stem + tan.

    Shen (2019), Proceedings of the Pragmatics Society of Japan 14,
    distinguishes adjective-stem + tan from its other sentence-final uses:
    https://pragmatics.gr.jp/content/files/proceedings/Proceedings_14_2019.pdf
    Only the attested adjective-stem construction is implemented here.
    """
    from general_words import SOURCED_EXPRESSIONS,attested_noun
    if text in SOURCED_EXPRESSIONS:return True
    # An independently attested written kana name has the same exact
    # hiragana reading. This retains the source, never nominates a name
    # as a repair or extends the ordinary-noun roster.
    from morphology import katakana_to_hiragana,tokenize
    from pos_grammar import explain_kana_run
    for end in range(2,min(len(text),24)+1):
        head,tail=text[:end],text[end:]
        if not all('ぁ'<=ch<='ゖ' or 'ァ'<=ch<='ヶ' or ch=='ー' for ch in head):break
        reading=katakana_to_hiragana(head)
        face=''.join(chr(ord(ch)+0x60) if 'ぁ'<=ch<='ゖ' else ch for ch in head)
        entry=attested_noun(face,reading)
        # An attested expression can itself be the topic or the nominal
        # predicate of the source. The same native tail proof applies;
        # neither fact creates a dictionary row or a repair candidate.
        if not (head in SOURCED_EXPRESSIONS
                or entry and entry[1].startswith('固有名詞:')):continue
        if not tail or _native_nominal_copula_tail(face,tail):return True
        # Reuse the native noun-tail grammar with this independent source
        # name fact. No name enters lexical replacement candidates.
        after=[t for t in tokenize(face+tail) if t.start>=len(face)]
        if (after and after[0].start==len(face) and after[-1].end==len(face+tail)
                and all(t.has_reading and t.pos=='助詞' and t.pos_sub!='連体化' for t in after)
                and explain_kana_run(tail,no_words=True,initial_state='Bw')):return True
        # An adnominal の requires its unchanged complete right noun.
        if tail.startswith('の') and any(cut==end and right for cut,left,right
                in native_genitive_nominal_splits(text,allow_unknown_left=True)):return True
    if not 3<=len(text)<=24 or not all('ぁ'<=ch<='ゖ' for ch in text):return False
    from morphology import dictionary_inflections,tokenize
    from particle_frames import native_final_particle_sequence
    for end in range(len(text),2,-1):
        word,tail=text[:end],text[end:]
        if not word.endswith('たん') or not native_final_particle_sequence(tokenize(tail)):continue
        stem=word[:-2]
        if any(pos.startswith('形容詞,自立,') and form=='ガル接続' and rd==stem
               for pos,form,base,rd in dictionary_inflections(stem) or ()):
            return True
    return False


@lru_cache(maxsize=2048)
def attested_source_expression_ranges(text):
    return tuple((start,start+len(clause)) for start,clause in _native_source_clauses(text)
                 if attested_source_expression(clause))


@lru_cache(maxsize=4096)
def native_adnominal_modifier_parts(reading, allow_predicative=False, allow_written=False):
    """Exact modifier proof, independent of the identity of its right noun.

    Only the modifier is certified. An unknown following token stays unknown;
    it cannot turn a complete source word into an erroneous verb inflection.
    """
    written=allow_written and any('一'<=ch<='龥' for ch in reading)
    if not reading or not all('ぁ'<=ch<='ゖ' or ch=='ー'
            or written and '一'<=ch<='龥' for ch in reading):return ()
    from corrector import table_surfaces_for_reading
    from morphology import dictionary_inflections,native_independent_adjective
    def entries(value):
        for face in dict.fromkeys((value,*table_surfaces_for_reading(value,limit=12))):
            for pos,form,base,rd in dictionary_inflections(face) or ():
                if rd==value or written and face==value:yield face,pos,form,base,rd
    rows=tuple(entries(reading))
    finite=any(row[1].startswith(('動詞,','助動詞,')) and row[2]=='基本形' for row in rows)
    for row in rows:
        if (row[1].startswith('連体詞,') and (allow_predicative or not finite)
                or native_independent_adjective(row[1],row[2],row[3])):return (row,)
    if reading.endswith('な') and len(reading)>2:
        copulas=[('な',pos,form,base,rd) for pos,form,base,rd in dictionary_inflections('な') or ()
                 if pos.startswith('助動詞,') and form=='体言接続' and base=='だ' and rd=='な']
        for row in entries(reading[:-1]):
            if row[1].startswith('名詞,形容動詞語幹,') and copulas:return (row,copulas[0])
    # An actual inflected copula (e.g. plain past) is the same modifier
    # proof as な. Its native attachment belongs to this lexical stem,
    # independently of whether the following noun is in the dictionary.
    from morphology import tokenize
    for cut in range(2,len(reading)):
        tail=reading[cut:]
        for row in entries(reading[:cut]):
            if (not row[1].startswith('名詞,形容動詞語幹,')
                    or not _native_nominal_copula_tail(row[0],tail)
                    or not native_attributive_predicate_end(row[0]+tail)):continue
            parts=[t for t in tokenize(row[0]+tail) if t.start>=len(row[0])]
            return (row,)+tuple((t.surface,t.pos+','+t.pos_sub.replace(':',','),
                t.infl_form,t.base_form,t.reading) for t in parts)
    return ()


@lru_cache(maxsize=2048)
def _native_non_nominal_modifier_tail(text):
    """Positive source evidence that the remainder supplies no nominal host.

    Unknown continuations stay eligible. A verified finite verb, or an
    all-functional native tail ending in an auxiliary, is a different role.
    This removes only a modifier proof; it never declares the source wrong.
    """
    if _completed_native_verb_surface(text,True,False,True):return True
    from morphology import tokenize,dictionary_inflections
    from contextual_repair import _completed_predicate_token
    parts=tokenize(text)
    from morphology import DAKUTEN_MARKS,HANDAKUTEN_MARKS
    mark_end=0
    while mark_end<len(text) and text[mark_end] in DAKUTEN_MARKS+HANDAKUTEN_MARKS:
        mark_end+=1
    if mark_end:
        tail=tokenize(text[mark_end:])
        # A mark cluster followed immediately by a native case/auxiliary
        # supplies no noun host. An unknown noun remains eligible as before.
        if not tail or tail[0].has_reading and (tail[0].pos=='助動詞'
                or tail[0].pos=='助詞' and tail[0].pos_sub.startswith('格助詞')):
            return True
    # A native te/de + imperative request has no nominal host for a
    # preceding apparent adjective. Unknown noun continuations still give
    # no negative evidence and keep the modifier's original protection.
    if (len(parts)>=2 and parts[0].has_reading and parts[0].surface in ('て','で')
            and parts[0].pos=='助詞' and parts[0].pos_sub=='接続助詞'):
        request=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                  t.start,t.end,t.has_reading,t.infl_form) for t in parts[1:]]
        if _native_request_tail(native_predicate_finite_core(request)):return True
    if not parts or any(not t.has_reading or t.pos not in ('助詞','助動詞')
            or not any(pos.split(',')[0]==t.pos and rd==t.reading
                       and (not t.infl_form or form==t.infl_form)
                       for pos,form,base,rd in dictionary_inflections(t.surface) or ()) for t in parts):return False
    legacy=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
             t.start,t.end,t.has_reading,t.infl_form) for t in parts]
    # A native final-particle-only remainder is a question/utterance,
    # not the nominal host of an adnominal modifier. Unknown nouns still
    # supply no such negative evidence and keep the modifier proof.
    if all(t.pos=='助詞' and '終助詞' in t.pos_sub for t in parts):return True
    core=native_predicate_finite_core(legacy)
    return bool(core and core[-1][1].startswith('助動詞') and _completed_predicate_token(core[-1]))


@lru_cache(maxsize=2048)
def native_adnominal_modifier_ranges(text):
    from morphology import tokenize
    from pos_grammar import native_object_functional_tail_frames
    predicate_heads=native_object_functional_tail_frames(text)
    out=[]
    for offset,clause in _native_source_clauses(text):
        tokens=tokenize(clause)
        # A written adjective keeps its own native connective boundary even
        # when the next modifier or noun has no whole-word classification.
        # Only that proved prefix is retained, never the unknown remainder.
        from morphology import dictionary_inflections
        for i,(adjective,link) in enumerate(zip(tokens,tokens[1:])):
            if (adjective.has_reading and adjective.pos=='形容詞'
                    and adjective.pos_sub=='自立' and adjective.infl_form=='連用テ接続'
                    and adjective.end==link.start and link.has_reading
                    and link.surface=='て' and link.pos=='助詞' and link.pos_sub=='接続助詞'
                    and (i==0 or tokens[i-1].has_reading and tokens[i-1].pos in ('助詞','記号'))
                    and any(pos.startswith('形容詞,自立,') and form=='連用テ接続'
                            and base==adjective.base_form and rd==adjective.reading
                            for pos,form,base,rd in dictionary_inflections(adjective.surface) or ())):
                out.append((offset+adjective.start,offset+link.end))
        # An attested numeral/counter owns its whole lexical boundary just
        # as a dictionary word does. Its internal kana is not a modifier.
        nominal_starts={0}|{t.end for t in tokens if t.has_reading and t.pos=='助詞'
                            and t.pos_sub.startswith(('格助詞','並立助詞'))}
        quantities=[(begin,begin+cut) for begin in nominal_starts
                    for cut in _native_counter_prefixes(clause[begin:],tokenize(clause[begin:]))]
        starts={0}|{t.start for t in tokens}
        for start in sorted(starts):
            if any(begin<start<end for begin,end in quantities):continue
            # A previously attested source modifier owns its whole prefix.
            # A best-path fragment beginning inside it cannot start a second
            # overlapping modifier and freeze a key in the following noun.
            if any(begin<offset+start<finish for begin,finish in out):continue
            for end in range(start+2,len(clause)):
                head=clause[start:end]
                if not all('ぁ'<=ch<='ゖ' or ch=='ー' or '一'<=ch<='龥' for ch in head):break
                # Use the same exact native modifier proof as candidate
                # boundaries, including the original written spelling.
                # Only its range is retained; the right noun stays unknown.
                if not native_adnominal_modifier_parts(head,allow_written=True):continue
                # An exact original continuative owns this same range when
                # its object and actual functional prefix establish a verb.
                if any(a==offset+start and cut==offset+end
                       for a,b,cut,reading in predicate_heads):continue
                if _native_non_nominal_modifier_tail(clause[end:]):continue
                # Do not split a longer original dictionary token. Parser
                # fragments within a proved modifier are not new word edges.
                if any(t.has_reading and t.start<=start<t.end and t.start<start
                       or t.has_reading and t.start==start and end<t.end for t in tokens):continue
                out.append((offset+start,offset+end))
    return tuple(sorted(set(out)))


def preserves_native_adnominal_modifier(source,start,end,surface):
    from morphology import native_spelling_only
    for lo,hi in native_adnominal_modifier_ranges(source):
        if start>=hi or end<=lo:continue
        if lo<=start and end<=hi:
            changed=source[lo:start]+surface+source[end:hi]
            if changed!=source[lo:hi] and not native_spelling_only(source[lo:hi],changed):return False
        elif not (start<=lo and hi<=end and (source[lo:hi] in surface
                or native_spelling_only(source[start:end],surface))):
            return False
    return True


@lru_cache(maxsize=2048)
def native_lexical_phrase_ranges(text):
    """Original fields and modifier+noun prefixes sharing nominal proof."""
    from morphology import tokenize
    def original_parts(value):
        return [(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                 t.start,t.end,t.has_reading,t.infl_form) for t in tokenize(value)]
    out=[]
    for start,clause in _native_source_clauses(text):
        if native_lexical_phrase(clause,original_parts):
            out.append((start,start+len(clause)));continue
        # A proved modifier + written noun keeps only its own original
        # range before a case/copula. The remaining clause is not certified.
        for token in tokenize(clause):
            if (token.pos=='名詞' and token.end<len(clause)
                    and native_written_adnominal_parts(clause[:token.end])):
                out.append((start,start+token.end))
    return tuple(dict.fromkeys(out))


@lru_cache(maxsize=2048)
def native_paused_nominal_ranges(text):
    """Retain a native nominal/case plus an explicit comma-delimited pause.

    NINJAL CSJ transcription treats fillers as spoken expressions, not typos:
    https://clrd.ninjal.ac.jp/csj/manu-f/transcription.pdf
    The original comma and native lexical entries supply the proof. An
    uninterrupted filler inside a comparison still has its separate gate.
    """
    if not any(c in text for c in '、,'):return ()
    from morphology import tokenize,dictionary_inflections
    out=[]
    for start,clause in _native_source_clauses(text):
        end=start+len(clause)
        if text[end:end+1] not in ('、',','):continue
        parts=tokenize(clause)
        if len(parts)<3:continue
        cut=len(parts)
        while cut>2 and any(pos.startswith(('フィラー,','感動詞,')) and rd==parts[cut-1].reading
                for pos,form,base,rd in dictionary_inflections(parts[cut-1].surface) or ()):
            cut-=1
            case=parts[cut-1]
            if (case.end!=parts[cut].start or parts[-1].end!=len(clause)
                    or case.pos!='助詞' or not case.has_reading):continue
            if not any(pos.startswith(('助詞,格助詞,','助詞,係助詞,','助詞,副助詞,','助詞,並立助詞,'))
                       and rd==case.reading
                       for pos,form,base,rd in dictionary_inflections(case.surface) or ()):continue
            if native_surface_nominal_heads(clause[:case.start]):
                out.append((start,end));break
    return tuple(out)


@lru_cache(maxsize=2048)
def native_open_nominal_fragment(text):
    """A clipped case + native noun + adnominal ending remains an open note.

    Both missing hosts are outside this fragment. Their absence is not a
    malformed connection inside the written noun; no completed sentence,
    unproved compound or unknown host is certified.
    """
    from morphology import tokenize,dictionary_inflections
    parts=tokenize(text)
    if (len(parts)<3 or parts[0].start!=0 or parts[-1].end!=len(text)
            or any(a.end!=b.start for a,b in zip(parts,parts[1:]))
            or not all(t.has_reading for t in parts)):return False
    first,last=parts[0],parts[-1]
    if not (first.pos=='助詞' and first.pos_sub.startswith('格助詞')
            and last.pos=='助詞' and last.pos_sub=='連体化'):
        return False
    if not all(any(':'.join(x for x in pos.split(',') if x!='*')==part.pos+':'+part.pos_sub
                   and rd==part.reading
                   for pos,form,base,rd in dictionary_inflections(part.surface) or ())
               for part in (first,last)):return False
    return bool(native_surface_nominal_heads(text[first.end:last.start]))


@lru_cache(maxsize=2048)
def native_context_ranges(text):
    """48-AHB: retain proved source grammar, even beside a malformed tail.

    Completed sequences, degree clauses and original noun/case frames feed
    the same entry and anomaly checks. A noun/counter proof stops at its own end: it does not
    certify the predicate, erase unrelated marks, or use a repaired reading.
    """
    out=list(native_mixed_kana_word_ranges(text))
    out.extend(native_likeness_predicate_ranges(text))
    out.extend(native_source_predicate_ranges(text))
    if native_open_nominal_fragment(text):out.append((0,len(text)))
    out.extend(native_lexical_phrase_ranges(text))
    out.extend(attested_source_expression_ranges(text))
    out.extend(native_paused_nominal_ranges(text))
    out.extend(native_prolonged_adverb_ranges(text))
    out.extend(native_temporal_nominal_ranges(text))
    out.extend(native_degree_context_ranges(text))
    out.extend(source_honorific_name_ranges(text))
    out.extend(native_incomplete_source_ranges(text))
    out.extend(attested_historical_auxiliary_ranges(text))
    out.extend(native_predicate_modifier_ranges(text))
    out.extend(native_adnominal_modifier_ranges(text))
    out.extend(native_written_nominal_ranges(text))
    out.extend(native_nominal_verb_prefix_ranges(text))
    from semantic_roles import unadorned_nominal_prefix_ranges
    out.extend(unadorned_nominal_prefix_ranges(text))
    if not any('ぁ'<=c<='ゖ' for c in text):
        return tuple(out)
    from morphology import tokenize
    for start,clause in _native_source_clauses(text):
        # The unchanged action sequence has the same lexical boundaries
        # before and after same-reading spelling. An actual open polite
        # tail supplies source evidence, never completed-candidate evidence.
        # As with a bare action note below, separate valid actions may occur
        # in temporal order. Meaning-based spelling selection stays stricter.
        if (8<=len(clause)<=80
                and _native_action_note_heads(clause,require_link=False,allow_predicate=True)):
            out.append((start,start+len(clause)))
        if native_case_adnominal_parts(clause) or native_te_nominal_heads(clause):
            out.append((start,start+len(clause)))
        # Share the unchanged adjunct itself, without declaring the following
        # noun/action correct or merging independently proved source ranges.
        out.extend((start,start+cut) for cut in native_adverbial_reading_cuts(clause))
        out.extend((start,start+cut) for cut in native_nominal_connective_boundaries(clause))
        if any(not ('ぁ'<=c<='ゖ' or c=='ー') for c in clause):
            out.extend((start+begin,start+finish)
                for begin,head,case,finish,faces in native_modified_nominal_contexts(clause))
            # An object and its completed connective predicate supply
            # their own source range even when the full best parse swallows
            # that connective into an unknown token. The next clause gets
            # no normality evidence from this prefix.
            # A written first object may precede two independently
            # completed native clauses. Prove its own connective clause,
            # then the whole remaining source; a noun range is insufficient.
            for edge in native_completed_clause_boundaries(clause):
                first,last=clause[:edge],clause[edge:]
                if not any(native_object_predicate_proof(first,cut,faces,allow_link=True)
                           for cut,faces in native_object_predicate_frames(first,True)):
                    continue
                out.append((start,start+edge))
                from contextual_repair import _completed_predicate_token,_native_imperative_completion
                tail=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                       t.start,t.end,t.has_reading,t.infl_form) for t in tokenize(last)]
                finite=native_predicate_finite_core(tail)
                if not (finite and (_completed_predicate_token(finite[-1])
                                    or _native_imperative_completion(tokenize(last)[:len(finite)]))):
                    continue
                if (completed_native_reading(last)
                        or completed_native_source_sequence(last)
                        or any(native_object_predicate_proof(last,cut,faces)
                               for cut,faces in native_object_predicate_frames(last,True))):
                    out.append((start,start+len(clause)))
            # 48-ALG: a written recipient/object keeps its own native
            # meaning. Share the full positive object/action proof with
            # source intactness before a partial kana run is explored.
            for begin,cut,faces in native_object_predicate_contexts(clause,allow_written_predicate=True):
                if native_object_predicate_proof(clause[begin:],cut-begin,faces):
                    out.append((start+begin,start+len(clause)))
        if (completed_native_reading(clause)
                or completed_native_action_note(clause,require_link=False)
                or completed_native_source_sequence(clause)
                or completed_native_nominal_predicate(clause,allow_written=True)
                or completed_native_reading_link(clause,allow_unclassified=True)):
            out.append((start,start+len(clause)))
        if native_prolonged_clause(clause) or attested_nominal_polite_variant(clause):
            out.append((start,start+len(clause)))
        if 'を' not in clause:continue
        if not 6<=len(clause)<=80:continue
        written=any(not ('ぁ'<=c<='ゖ' or c=='ー') for c in clause)
        # The same unchanged noun/case also precedes a native written verb.
        # Keep only that object range; its predicate still needs its own proof.
        for begin,end,faces in native_object_predicate_contexts(clause,allow_written_predicate=written):
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


@lru_cache(maxsize=2048)
def attested_nominal_polite_variant(text):
    """Preserve an attested original copular style; never generate that style.

    GPT-6 Astra / 2026-09-21: Shogakukan Daijisen/Nikkoku おす attests
    copular で + polite auxiliary おす. The unchanged native noun and
    exact dictionary forms are required; unknown prefixes are not certified.
    https://kotobank.jp/word/%E3%81%8A%E3%81%99-452578
    """
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    if not bare or not 4<=len(bare)<=40 or 'でおす' not in bare:return False
    from morphology import tokenize,dictionary_inflections
    if not any(p.startswith('助動詞,') and f=='連用形' and b=='だ' and r=='で'
               for p,f,b,r in dictionary_inflections('で') or ()):return False
    if not any(p.startswith('動詞,') and f=='基本形' and b=='おす' and r=='おす'
               for p,f,b,r in dictionary_inflections('おす') or ()):return False
    import re
    for marker in re.finditer('でおす',bare):
        if not native_surface_nominal_heads(bare[:marker.start()]):continue
        tail=bare[marker.end():];parts=tokenize(tail)
        from particle_frames import native_final_particle_sequence
        if ''.join(t.surface for t in parts)==tail and native_final_particle_sequence(parts):
            return True
    return False


@lru_cache(maxsize=4096)
def native_kahen_derivational_source(text):
    """Prove an original kana KAHEN stem and its completed native suffix.

    A full tokenizer can prefer a different homograph. Only the same written
    source, its dictionary paradigms and ordinary finite tail protect it.
    """
    if (not 4<=len(text)<=36 or not all('ぁ'<=ch<='ゖ' for ch in text)
            or not any(suffix in text for suffix in ('させ','られ'))):
        return False
    from morphology import HAS_JANOME,dictionary_paradigms
    if not HAS_JANOME:return False
    from oddness import _derivational_connection
    from pos_grammar import explain_kana_run,_load_tables
    if not _load_tables()[0]:return False
    for cut in range(1,min(4,len(text)-2)):
        left=[row for row in dictionary_paradigms(text[:cut]) or ()
              if row[0].startswith('動詞,自立,') and row[1].startswith('カ変')
              and row[2]=='未然形' and row[4]==text[:cut]]
        if not left:continue
        for end in range(cut+1,min(cut+5,len(text))):
            right=[row for row in dictionary_paradigms(text[cut:end]) or ()
                   if row[0].startswith('動詞,接尾,')
                   and row[3] in ('させる','られる') and row[4]==text[cut:end]
                   and row[2] in ('未然形','連用形')]
            for suffix in right:
                kind='causative' if suffix[3]=='させる' else 'passive'
                if (_derivational_connection(left,(suffix,),kind) is True
                        and explain_kana_run(text[end:],no_words=True,initial_state='E')
                        and completed_native_verb_reading(text,allow_nonpolite=True,
                            require_roles=False,finite_only=True)):
                    return True
    return False


@lru_cache(maxsize=4096)
def intact_native_reading(text,allow_incomplete=True):
    """Known source grammar, including a native open or sequential tail.

    This protects the input and suppresses a false anomaly. Generated
    single-predicate candidates still need completed_native_reading_clause.
    An extracted interior fragment cannot borrow a missing clause ending;
    its incomplete proof must instead come from native_context_ranges(source).
    """
    bare=text[:-1] if text and text[-1] in '。！？.!?' else text
    # 48-AMJ / GPT-6 Astra / 2026-09-20: a complete original noun
    # phrase needs no predicate. Reuse its exact reading and nominal-head
    # proof; do not accept a noun prefix plus an unexplained/invalid tail.
    # This source proof neither changes spelling nor validates candidates.
    if attested_source_expression(bare):return True
    if (native_written_adnominal_parts(bare) or native_nominal_phrase_faces(bare)
            or any('一'<=c<='鿿' for c in bare) and _native_written_nominal_faces(bare)):
        return True
    if allow_incomplete and (native_incomplete_polite_reading(text)
                             or native_incomplete_nominal_reading(text)
                             or native_incomplete_linked_reading(text)):return True
    if (any(begin==0 and end==len(bare) for begin,end in source_honorific_name_ranges(bare))
            or native_degree_subject_clause(text) or completed_written_object_clause(text)
            or attested_nominal_polite_variant(text) or native_temporal_nominal_reading(text)
            or (0,len(bare)) in attested_historical_auxiliary_ranges(bare)
            or completed_native_reading(text)
            or completed_native_source_sequence(text)
            or completed_native_reading_link(text,allow_unclassified=True)
            or native_adverbial_predicate_reading(text)
            or native_degree_expression(text)
            or native_prolonged_clause(text)
            or completed_native_reading_clause(text,require_nominal=True,
                require_object_fit=True,allow_open_tail=True)):
        return True
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
    return (native_kahen_derivational_source(bare)
            or completed_sahen_reading(bare,allow_nonpolite=True,allow_open_tail=True)
            or any(completed_sahen_reading(bare[cut:],allow_nonpolite=True,object_faces=faces,allow_open_tail=True)
                   for cut,faces in native_object_predicate_frames(bare)))



def _written_predicate_reading_preserved(parts,predicate_start,reading):
    """A written content verb cannot borrow a homophone's auxiliary role.

    GPT-6 / 2026-09-14. This constrains positive candidate proof only. Native
    auxiliary variants remain available when this exact spelling/form/reading
    has the projected grammatical role in the same native dictionary.
    """
    from morphology import tokenize,dictionary_inflections
    from oddness import polite_aux_mismatch,auxiliary_connection_mismatch
    # Reading projection must not erase a written noun's already invalid
    # polite attachment (歌詞+ます cannot borrow the verb 貸す). Use the
    # same original-form mismatch that owns the correction target.
    legacy=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
             t.start,t.end,t.has_reading,t.infl_form) for t in parts]
    # Keep the same written native attachment through kana projection;
    # an impossible perfective/auxiliary chain cannot borrow a whole verb
    # that happens to share its combined reading (売 + つ -> うつ).
    if any(a[3]>=predicate_start and any('一'<=c<='鿿' for c in a[0])
           and (polite_aux_mismatch(a,b) or
                auxiliary_connection_mismatch(a,b,legacy[i-1] if i else None))
           for i,(a,b) in enumerate(zip(legacy,legacy[1:]))):return False
    # 48-AMB: a written proper name cannot disappear into a different
    # common predicate merely by joining its reading to the next kana.
    # A separately cased name remains eligible for the full grammar proof;
    # an unproved join is not positive evidence, nor a new anomaly rule.
    for index,part in enumerate(parts):
        if (part.start<predicate_start or part.pos!='名詞'
                or not part.pos_sub.startswith('固有名詞')
                or all('ぁ'<=c<='ゖ' or c=='ー' for c in part.surface)):
            continue
        following=parts[index+1] if index+1<len(parts) else None
        if not (following and following.pos=='助詞'
                and following.pos_sub.startswith('格助詞')
                and following.surface in ('が','を','に','へ','と','から','より','で')):
            return False
    # A written action noun owns its original spelling before suru.
    # Joining unrelated native nouns into a reading cannot certify the
    # source by silently using another written action with that reading.
    from morphology import native_suru_form
    from semantic_roles import classified_nominal_action
    for index,part in enumerate(parts):
        if not (part.start>=predicate_start and part.has_reading and part.pos=='動詞'
                and part.base_form=='する'
                and native_suru_form(part.surface,part.infl_form,part.reading,False)):continue
        begin=index
        while (begin>0 and parts[begin-1].end==parts[begin].start
                and parts[begin-1].start>=predicate_start
                and parts[begin-1].pos in ('名詞','接頭詞')):begin-=1
        nouns=parts[begin:index]
        if not nouns or not any(any('一'<=c<='鿿' for c in t.surface) for t in nouns):continue
        face=''.join(t.surface for t in nouns);rd=''.join(t.reading for t in nouns)
        if not (all(t.has_reading for t in nouns)
                and (native_action_noun_reading(face,rd)
                     or classified_nominal_action(face,rd)
                     or rd in native_attested_prefix_noun_readings(face))):return False
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


def _written_case_meanings_preserved(text,predicate_start,parts,faces):
    """Bind an intervening case to the actual written verb, before projection.

    Object grammar retains its existing proof. A recipient/place meaning
    cannot be borrowed from another written verb with the same reading.
    Native benefactive auxiliaries keep their own case evidence as well.
    Missing proof does not classify the source as anomalous.
    """
    from semantic_roles import (case_argument_before,native_verb_roles,_argument_prefix,
                               native_benefactive_case_roles,nominal_role_matches)
    legacy=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
             t.start,t.end,t.has_reading,t.infl_form) for t in parts]
    temporal_edges=None;readings=()
    def temporal_boundaries():
        nonlocal temporal_edges,readings
        if temporal_edges is None:
            readings=tuple(t.surface if all('ぁ'<=c<='ゖ' or c=='ー' for c in t.surface)
                else t.reading if t.has_reading else '' for t in parts)
            nominal=''.join(rd for t,rd in zip(parts,readings) if t.end<=predicate_start-1)
            constraint=((nominal,tuple(faces)) if any(not ('ぁ'<=c<='ゖ' or c=='ー')
                for c in text[:predicate_start-1]) else None)
            temporal_edges=(native_temporal_reading_edges(''.join(readings),constraint)
                            if all(readings) else ())
        return temporal_edges
    for head in parts:
        if (head.start<predicate_start or not head.has_reading or head.pos!='動詞'
                or head.pos_sub!='自立' or all('ぁ'<=c<='ゖ' or c=='ー' for c in head.surface)):
            continue
        # The original accusative also owns the written verb's exact sense.
        # A kana projection must not borrow a fitting homophone's roles.
        if text[predicate_start-1:predicate_start]=='を':
            _,edge=_argument_prefix(text,head.start,lambda _:legacy)
            bound=edge==predicate_start
            if not bound and head.start>predicate_start:
                from morphology import tokenize
                remainder=text[predicate_start:]
                bound=head.start-predicate_start in _native_counter_prefixes(remainder,tokenize(remainder))
            if bound:
                object_roles=native_verb_roles(head.surface,head.infl_form,head.reading,
                    tail=text[head.end:].rstrip('。！？.!?'),before=text[:head.start])
                # Positive clause proof needs this actual written verb's
                # object role. An empty role set cannot borrow a fitting
                # homophone after projection to kana; it is not oddness.
                if not object_roles:
                    # An independently connected next action is not part of
                    # this verb's auxiliary tail. Its actual native link
                    # proves the shorter inflection; whole-clause validation
                    # still checks the following action separately.
                    for edge in native_predicate_link_boundaries(text,head.start):
                        object_roles=native_verb_roles(head.surface,head.infl_form,head.reading,
                            tail=text[head.end:edge],before=text[:head.start])
                        if object_roles:break
                if not object_roles:
                    # A proved temporal nominal closes this written action.
                    # Its following clause is not part of the verb's auxiliary
                    # tail. Keep the original noun sense and the same source
                    # temporal proof used by the ni case below.
                    ends=temporal_boundaries()
                    for time,case in zip(parts,parts[1:]):
                        if (time.start<head.end or not time.has_reading or time.pos!='名詞'
                                or time.reading not in {rd for rd,phase in _native_temporal_heads()}
                                or case.surface not in ('に','で') or case.pos!='助詞' or time.end!=case.start):continue
                        edge=sum(len(rd) for t,rd in zip(parts,readings) if t.end<=case.end)
                        if edge not in ends:continue
                        object_roles=native_verb_roles(head.surface,head.infl_form,head.reading,
                            tail=text[head.end:time.start],before=text[:head.start])
                        if object_roles:break
                if not any(nominal_role_matches(face,object_roles) for face in faces):
                    return False
        argument=case_argument_before(text,head.start,lambda _:legacy,through_object=True)
        if not argument:continue
        noun,particle=argument
        if particle in ('に','で'):
            actual=next((t for t in reversed(parts) if t.end<=head.start
                         and t.surface==particle and t.pos=='助詞'),None)
            if actual:
                temporal_boundaries()
                edge=sum(len(rd) for t,rd in zip(parts,readings) if t.end<=actual.end)
                # Only this original に belongs to the independently proved
                # temporal clause. A recipient/location elsewhere still
                # needs the actual written verb's own case meaning.
                if edge in temporal_edges:continue
        arguments=native_surface_nominal_heads(noun)
        roles=native_verb_roles(head.surface,head.infl_form,head.reading,case=particle)
        roles=roles | native_benefactive_case_roles(head.surface,head.infl_form,head.reading,
            text[head.end:].rstrip('。！？.!?'),particle,text[:head.start])
        if not any(nominal_role_matches(face,roles) for face in arguments):return False
    return True


@lru_cache(maxsize=4096)
def _native_written_predicate_conflicts(text):
    """Original full-context anomalies shared by projection and source seams."""
    from morphology import tokenize
    from semantic_roles import subject_only_predicate_spans,conflicting_object_predicates,unadorned_action_conflicts
    original=[(part.surface,part.pos+':'+part.pos_sub,part.reading,part.start,part.end,
               part.has_reading,part.infl_form) for part in tokenize(text)]
    conflicts=subject_only_predicate_spans(text,original)+conflicting_object_predicates(text,original)+list(unadorned_action_conflicts(text,original))
    if 'てい' in text or 'てと' in text:
        from pos_grammar import _orphaned_key_before_direct_action_windows
        conflicts.extend((verb[0],'orphaned_action_key',te[3],extra[4])
            for verb,te,extra,aux in _orphaned_key_before_direct_action_windows(original))
    if 'てし' in text or 'んし' in text or 'かし' in text:
        from pos_grammar import _orphaned_particle_before_sahen_action_windows
        conflicts.extend((head[0],'orphaned_particle',extra[3],extra[4])
            for head,extra,aux in _orphaned_particle_before_sahen_action_windows(original,text))
    if 'をん' in text or 'をし' in text:
        from oddness import orphan_case_leading_mismatch
        conflicts.extend((a[0],'orphaned_case_prefix',a[3],b[4])
            for previous,a,b in zip(original,original[1:],original[2:])
            if orphan_case_leading_mismatch(a,b,previous))
    if 'から' in text:
        from particle_frames import converted_connective_nominal_frames
        conflicts.extend((frame['head'],'imperative_nominal',frame['start'],frame['end'])
            for frame in converted_connective_nominal_frames(text) if frame.get('imperative'))
    return tuple(conflicts)


@lru_cache(maxsize=4096)
def _native_partitive_object_projections(text,predicate_start,faces):
    """An explicit genitive subset retains its own unchanged nominal source.

    This transfers no roles to a bare partitive noun. Both original
    particles, both whole noun readings and the existing genitive relation
    are required before the same predicate can use that noun's meaning.
    """
    if not faces or text[predicate_start-1:predicate_start]!='を':return ()
    prefix=text[:predicate_start-1]
    if 'の' not in prefix:return ()
    from morphology import tokenize
    from semantic_roles import nominal_roles,genitive_nominal_support
    if not all('partitive' in nominal_roles(face) for face in faces):return ()
    parts=tokenize(text)
    if not any(t.start==predicate_start-1 and t.end==predicate_start
               and t.has_reading and t.surface==t.reading=='を' and t.pos=='助詞'
               and t.pos_sub=='格助詞:一般' for t in parts):return ()
    out=[]
    for cut,left,right in native_genitive_nominal_splits(prefix,original_context=text):
        if not (set(faces)<=set(right) and any(t.start==cut and t.end==cut+1
                and t.has_reading and t.surface==t.reading=='の' and t.pos=='助詞'
                and t.pos_sub=='連体化' for t in parts)):continue
        owned=tuple(noun for noun in left if all(genitive_nominal_support(noun,face) for face in faces))
        if owned:
            # Only the proved nominal modifier changes in this proof view;
            # the actual case, written action and entire tail stay original.
            out.append((prefix[:cut]+text[predicate_start-1:],cut+1,owned))
    return tuple(out)


@lru_cache(maxsize=4096)
def native_object_predicate_proof(text, predicate_start, faces, allow_link=False, return_action=False):
    """Shared nominal/case proof, retaining a written argument's own meaning.

    Kana remain literal even when unknown. A kanji spelling must have an
    actual native reading, and cannot borrow another homophone's object role.
    This positive proof neither invents an anomaly nor chooses a spelling.
    """
    from semantic_roles import nominal_role_matches
    if not 1<predicate_start<len(text):return False
    partitive=_native_partitive_object_projections(text,predicate_start,faces)
    if partitive:
        for projected,cut,objects in partitive:
            proof=native_object_predicate_proof(projected,cut,objects,
                allow_link=allow_link,return_action=return_action)
            if proof:return proof
        # Missing inherited fit is not a conflict. The head may also own
        # an independently proved sense; keep its normal validation below.
    from morphology import tokenize,dictionary_inflections
    # A finite path motion cannot inherit this non-path object. Close the
    # first te/de action with the same source ownership proof, then validate
    # that first action's own object and grammar, including its actual link.
    from semantic_roles import _motion_tail_cannot_take_object
    source_parts=tokenize(text)
    for index,link in enumerate(source_parts):
        if not (link.start>predicate_start and link.pos=='助詞'
                and link.pos_sub=='接続助詞' and link.surface in ('て','で')):continue
        ends=[link.end]
        # A temporal te/de + kara belongs to this same native action.
        # Retain the full original tokens and prove the complete link;
        # the following motion lends neither its object nor its meaning.
        following=source_parts[index+1] if index+1<len(source_parts) else None
        if (link.has_reading and following and following.has_reading
                and following.start==link.end and following.pos=='助詞'
                and following.surface==following.reading=='から'):
            native=[part for part in source_parts
                    if predicate_start<=part.start and part.end<=following.end]
            if (native and native[0].start==predicate_start
                    and all(part.has_reading for part in native)
                    and all(a.end==b.start for a,b in zip(native,native[1:]))
                    and ''.join(part.surface for part in native)==text[predicate_start:following.end]):
                reading=''.join(part.surface if all('ぁ'<=c<='ゖ' or c=='ー' for c in part.surface)
                                else part.reading for part in native)
                if (_written_predicate_reading_preserved(native,predicate_start,reading)
                        and completed_native_reading_link(reading,allow_unclassified=True)):
                    ends.append(following.end)
        if faces and any(all(_motion_tail_cannot_take_object(text[end:],face)
                             for face in faces) for end in ends):
            action=native_object_predicate_proof(text[:link.end],predicate_start,faces,
                                                 allow_link=True,return_action=True)
            if action:return action if return_action else True
    # Native continuative V followed by an independently finite sahen
    # action shares the explicit object with that following action. The
    # preceding written verb is retained by source-preservation checks;
    # it is not an auxiliary of the newly repaired action noun.
    sequence=tokenize(text[predicate_start:].rstrip('。！？.!?'))
    if len(sequence)>=3:
        first,second=sequence[:2]
        if (first.has_reading and first.end==second.start
                and any(p.startswith('動詞,自立,') and form=='連用形' and rd==first.reading
                    for p,form,base,rd in dictionary_inflections(first.surface) or ())
                and second.has_reading and second.pos=='名詞' and second.pos_sub=='サ変接続'
                and native_action_noun_reading(second.surface,second.reading)):
            from semantic_roles import native_verb_roles
            roles=native_verb_roles(first.surface,'連用形',first.reading,
                tail='',before=text[:predicate_start],allow_open_tail=True)
            if roles and not any(nominal_role_matches(face,roles) for face in faces):return False
            tail=text[predicate_start+second.start:]
            action=native_object_predicate_proof(text[:predicate_start]+tail,predicate_start,faces,
                                                 allow_link=allow_link,return_action=True)
            if action:return action if return_action else True
    # 48-ALQ: a kana projection must not turn a proved conflict in the
    # original written predicate into its fitting homophone. Reuse the
    # same explicit native object/case anomaly used by all repair routes.
    if any('一'<=ch<='龯' for ch in text[predicate_start:]):
        native_parts=tokenize(text)
        if not _written_case_meanings_preserved(text,predicate_start,native_parts,faces):return False
        if _native_written_predicate_conflicts(text):return False
    preposed=[part for part in native_preposed_object_parts(text,allow_written_predicate=True)
              if part[3]==predicate_start and tuple(part[4])==tuple(faces)]
    if preposed:
        from semantic_roles import proved_action_case_support
        for edge,case,receiver,cut,objects in preposed:
            action=native_object_predicate_proof(text[edge:],cut-edge,objects,
                allow_link=allow_link,return_action=True)
            if action and any(proved_action_case_support(noun,case,action,context=text[edge:])
                              for noun in receiver):
                return action if return_action else True
        return False
    # 48-ALO/ALS: an unchanged written count is an adverbial quantity, not a
    # guessed reading. Prove its actual object/case, retain only the noun
    # meanings that fit this unit, and validate the same complete predicate.
    # A following case belongs to the quantity itself and cannot be removed.
    quantity_faces=None
    remainder=text[predicate_start:]
    if text[predicate_start-1]=='を' and any(not ('ぁ'<=ch<='ゖ' or ch=='ー') for ch in remainder):
        parts=tokenize(text)
        for size in _native_counter_prefixes(remainder,tokenize(remainder)):
            if all('ぁ'<=ch<='ゖ' or ch=='ー' for ch in remainder[:size]):continue
            tail=tokenize(remainder[size:])
            if (not tail or tail[0].pos not in ('動詞','副詞') or not tail[0].has_reading
                    or native_nominal_case_boundary(text,parts,predicate_start-1,'を',faces) is None):
                continue
            from semantic_roles import counted_object_roles
            roles=counted_object_roles(remainder[:size])
            supported=tuple(face for face in faces if roles is None or nominal_role_matches(face,roles))
            if not supported:return False
            quantity_faces=supported;faces=supported
            text=text[:predicate_start]+remainder[size:]
            break
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
            if any(nominal_role_matches(face,roles) for face in faces):return head if return_action else True
            from morphology import native_suru_form
            if base=='する' and native_suru_form(head,form,rd,False) and any(any(p.startswith('名詞,サ変接続,') and b==face
                    for p,f,b,r in dictionary_inflections(face) or ()) for face in faces):return head if return_action else True
    readings=[];nominal=[]
    parts=tokenize(text)
    # Keep the actual written arguments when a kana best parse picks a
    # different noun reading. This existing proof validates every case,
    # native action, and finite tail without borrowing a homophone's role.
    bare=text[:-1] if text[-1:] in '。！？.!?' else text
    written=native_written_relative_action(bare,allow_finite=True,allow_note=True)
    if (written and text[predicate_start-1:predicate_start]=='を'
            and set(faces)&set(native_surface_nominal_heads(text[:predicate_start-1]))):
        return written[0] if return_action else True
    # The same argument/action may close as an attributive clause plus a
    # native noun and copula. Prove the shorter action with these exact
    # object meanings; the nominal ending cannot license a different verb.
    for noun in parts:
        if (noun.start<=predicate_start or noun.pos!='名詞' or not noun.has_reading
                or not native_attributive_predicate_end(text[:noun.start])
                or not _native_nominal_copula_tail(noun.surface,
                    text[noun.end:-1] if text[-1:] in '。！？.!?' else text[noun.end:])):continue
        action=native_object_predicate_proof(text[:noun.start],predicate_start,faces,
                                            return_action=True)
        if action:return action if return_action else True
    for part in parts:
        if all('ぁ'<=c<='ゖ' or c=='ー' for c in part.surface):rd=part.surface
        elif part.has_reading:rd=part.reading
        else:return False
        readings.append(rd)
        if part.end<=predicate_start-1:nominal.append(rd)
    prefix=text[:predicate_start-1]
    constraint=((''.join(nominal),tuple(faces))
        if quantity_faces is not None or any(not ('ぁ'<=c<='ゖ' or c=='ー') for c in prefix) else None)
    reading=''.join(readings)
    if not _written_predicate_reading_preserved(parts,predicate_start,reading):return False
    action=completed_native_reading_clause(reading,require_nominal=True,
                    require_object_fit=True,nominal_constraint=constraint,return_action=return_action)
    if not action and text[predicate_start-1:predicate_start]=='を':
        # The written predicate already has its own native inflection.
        # Its kana best parse may split that same reading into auxiliaries;
        # verify the original tokens with the shared argument/tail grammar.
        head=next((t for t in parts if t.start==predicate_start),None)
        if (head and head.has_reading and head.pos=='動詞' and head.pos_sub=='自立'
                and any('一'<=c<='鿿' for c in head.surface)
                and native_nominal_case_boundary(text,parts,predicate_start-1,'を',faces) is not None):
            tail=[t for t in parts if t.start>=predicate_start-1]
            legacy=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                     t.start,t.end,t.has_reading,t.infl_form) for t in tail]
            from semantic_roles import _terminal_predicate_tail
            closed_request=_terminal_predicate_tail(text,legacy,head.end,head.infl_form)
            if _native_nominal_functional_tail(legacy,explicit_nominal_case=True,
                    content_object_faces=faces,source_prefix=text[:predicate_start-1],
                    allow_connective=closed_request):
                action=head.surface if return_action else True
    if return_action:return action
    return bool(action or completed_native_reading_sequence(reading,nominal_constraint=constraint)
                or completed_native_temporal_clause(reading,nominal_constraint=constraint)
                or constraint is None and completed_native_action_note(reading)
                or allow_link and completed_native_reading_link(reading,require_nominal=True,
                    nominal_constraint=constraint))


@lru_cache(maxsize=4096)
def native_argument_predicate_contexts(text,include_written_mismatch=True):
    """Share native noun/case boundaries without inventing source errors.

    Accusative/preposed scopes keep their existing evidence. Other cases
    require an actual single-key native case token in the unchanged source;
    they do not reopen a copula, topic, quote, or swallowed unknown boundary.
    The proposed predicate still needs the same positive full-clause proof.
    """
    out=list(native_object_predicate_contexts(text,
        include_written_mismatch=include_written_mismatch))
    from morphology import tokenize
    cases=tuple(dict.fromkeys((t.end,t.surface) for t in tokenize(text)
        if t.has_reading and t.pos=='助詞' and t.pos_sub=='格助詞:一般'
        and len(t.surface)==1 and t.surface!='を'))
    for particle in dict.fromkeys(case for end,case in cases):
        out.extend((0,cut,faces) for cut,faces in
                   _native_nominal_predicate_frames(text,particle)
                   if (cut,particle) in cases)
    return tuple(dict.fromkeys(out))


@lru_cache(maxsize=4096)
def native_argument_predicate_cuts(text):
    """The same anomaly search boundary for each attested source case."""
    return tuple(dict.fromkeys(cut for start,cut,faces in
        native_argument_predicate_contexts(text,include_written_mismatch=False)
        if not intact_native_reading(text[start:])
        and not native_object_predicate_proof(text[start:],cut-start,faces)))


@lru_cache(maxsize=4096)
def native_object_predicate_cuts(text):
    """Repair boundaries only; no anomaly or output is inferred here."""
    # Written noun/auxiliary mismatches share source argument validation,
    # but retain their existing auxiliary target. They do not open the
    # broader kana-predicate search or change the written noun's identity.
    return tuple(dict.fromkeys(cut for start,cut,faces in native_object_predicate_contexts(
                    text,include_written_mismatch=False)
                 if not intact_native_reading(text[start:])
                 and not native_object_predicate_proof(text[start:],cut-start,faces)))


@lru_cache(maxsize=4096)
def native_nominal_spelling_faces(reading):
    """Full written noun spellings, excluding a merely grammatical kana phrase."""
    from morphology import native_spelling_only
    faces=native_nominal_phrase_faces(reading)
    # Native adjective + nominalizing sa is a complete nominal even when
    # the whole surface is not a dictionary entry. Derive its written
    # spelling from that same stem and suffix, never a noun-answer table.
    if reading.endswith('さ'):
        from morphology import tokenize,dictionary_inflections
        parts=tokenize(reading)
        legacy=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                 t.start,t.end,t.has_reading,t.infl_form) for t in parts]
        if len(parts)==2 and nominalized_adjective_context(reading,0,len(reading),lambda _:legacy):
            stem,suffix=parts
            stem_faces=set(native_lexical_reading_faces(stem.reading))
            # The compact reading index can omit a short inflected stem.
            # Recover it through the same native lemma and actual form.
            for pos,form,base,rd in dictionary_inflections(stem.surface) or ():
                if not (pos.startswith('形容詞,自立,') and form=='ガル接続' and rd==stem.reading):continue
                for p,f,b,lemma_reading in dictionary_inflections(base) or ():
                    if not (p.startswith('形容詞,自立,') and f=='基本形' and b==base):continue
                    for lemma in native_lexical_reading_faces(lemma_reading):
                        possible={lemma[:i]+rd[j:] for i in range(len(lemma)+1)
                                  for j in range(len(rd)+1)}
                        stem_faces.update(face for face in possible if any(
                            p.startswith('形容詞,自立,') and f==form and b==lemma and r==rd
                            for p,f,b,r in dictionary_inflections(face) or ()))
            for face in sorted(stem_faces):
                if any(rd==stem.reading and (
                        pos.startswith('形容詞,自立,') and form=='ガル接続'
                        or pos.startswith('名詞,形容動詞語幹,'))
                        for pos,form,base,rd in dictionary_inflections(face) or ()):
                    proposal=face+suffix.surface
                    if native_spelling_only(reading,proposal):faces+=(proposal,)
    # The ordinary written personal plural uses the native 達 suffix.
    # This is a productive suffix spelling, not a whole phrase replacement.
    plural=native_plural_nominal_heads(reading)
    if plural:
        written=tuple(face+'達' for face in plural if any('一'<=c<='鿿' for c in face)
            and native_plural_nominal_heads(face+'達') and native_spelling_only(reading,face+'達'))
        if written:return written
    # Existing source noun identities and positive compound relations also
    # establish productive spellings absent from the whole-word dictionary.
    faces+=native_nominal_tail_spellings(reading,native_nominal_tail_heads(reading))
    return tuple(dict.fromkeys(face for face in faces
                 if face!=reading and native_spelling_only(reading,face)))


@lru_cache(maxsize=2048)
def native_nominal_compound_spelling(reading,surface):
    """A complete, same-reading nominal compound with each relation proved."""
    from morphology import native_spelling_only
    from semantic_roles import nominal_compound_support
    units=native_nominal_units(surface)
    return bool(len(units)>1 and native_spelling_only(reading,surface)
        and all(nominal_compound_support(surface[:a],face) for a,b,face in units[1:]))


@lru_cache(maxsize=2048)
def native_nominal_tail_heads(text):
    """Existing ordinary noun heads; neither an anomaly nor a repair answer."""
    from morphology import tokenize
    from semantic_roles import nominal_roles
    kana=bool(text and all('ぁ'<=char<='ゖ' or char=='ー' for char in text))
    out=[]
    if kana:
        for cut in range(2,len(text)):
            for face in _native_nominal_reading_faces(text[cut:]):
                if nominal_roles(face):out.append((cut,face,text[cut:]))
    else:
        parts=tokenize(text)
        if parts and all(t.has_reading and t.pos=='名詞' and not t.pos_sub.startswith(('固有名詞','非自立','接尾')) for t in parts):
            last=parts[-1]
            if last.start>=2 and nominal_roles(last.surface):out.append((last.start,last.surface,last.reading))
    return tuple(out)


@lru_cache(maxsize=4096)
def native_nominal_tail_spellings(reading,heads):
    """Join exact native noun readings with the unchanged source noun head."""
    out=[]
    for cut,head,tail in heads:
        if not reading.endswith(tail) or len(reading)<=len(tail):continue
        for prefix in native_nominal_phrase_faces(reading[:-len(tail)]):
            surface=prefix+head
            if native_nominal_compound_spelling(reading,surface) and surface not in out:out.append(surface)
    return tuple(out)


@lru_cache(maxsize=4096)
def native_written_nominal_coordination(text):
    """Actual noun/genitive members joined by native coordinating particles.

    Proper names keep their actual native reading. This proves only the
    written syntax; independent semantic contrasts still select the sense.
    """
    if not any(c in text for c in ('と','や')) or not any('一'<=c<='鿿' for c in text):return ()
    from morphology import tokenize,dictionary_inflections
    parts=tokenize(text)
    if not parts or any(not t.has_reading for t in parts):return ()
    if (parts[0].start!=0 or parts[-1].end!=len(text)
            or any(a.end!=b.start for a,b in zip(parts,parts[1:]))):return ()
    groups=[];start=0
    for i,t in enumerate(parts):
        if t.pos=='助詞' and t.pos_sub=='並立助詞' and t.surface in ('と','や'):
            groups.append(parts[start:i]);start=i+1
    if not groups:return ()
    groups.append(parts[start:])
    def native_noun(units):
        if not units or any(t.pos!='名詞' for t in units):return False
        face=''.join(t.surface for t in units)
        if len(units)>1:return bool(_native_written_nominal_faces(face))
        t=units[0]
        return bool(any(p.startswith('名詞,') and b==face and rd==t.reading
            and not any(x in p.split(',')[1:4] for x in ('接尾','非自立'))
            for p,f,b,rd in dictionary_inflections(face) or ()))
    for group in groups:
        start=0
        for i,t in enumerate(group):
            if t.surface=='の' and t.pos=='助詞' and t.pos_sub=='連体化':
                if not native_noun(group[start:i]):return ()
                start=i+1
            elif t.pos!='名詞':return ()
        if not native_noun(group[start:]):return ()
    return tuple(''.join(t.surface for t in group) for group in groups)


def native_interrogative_nominal(text,tokenize_fn):
    """A native interrogative fills the open slot of a nominal category."""
    if tokenize_fn is None or not text.startswith(("何","なに","なん")):return False
    parts=list(tokenize_fn(text))
    if (len(parts)!=2 or parts[0][3]!=0 or parts[1][4]!=len(text)
        or parts[0][4]!=parts[1][3] or not all(t[5] for t in parts)
        or '代名詞' not in parts[0][1] or not parts[1][1].startswith('名詞')
        or '固有名詞' in parts[1][1]):return False
    from semantic_roles import interrogative_nominal_support
    return interrogative_nominal_support(parts[0][0],parts[1][0])


@lru_cache(maxsize=2048)
def native_likeness_predicate_ranges(text):
    """Finite native predicate + auxiliary you + its actual copular form.

    This is an original grammatical range, not a license to repair the
    predicate, certify an unknown noun or choose a homophone of you.
    """
    from morphology import tokenize,dictionary_inflections
    from contextual_repair import _allows_grammatical_tail,_productive_predicate
    parts=tokenize(text);out=[]
    for i in range(1,len(parts)-1):
        prior,you,copula=parts[i-1:i+2]
        if not (you.has_reading and you.pos=='名詞' and you.pos_sub=='非自立:助動詞語幹'
                and you.base_form=='よう' and prior.end==you.start and you.end==copula.start
                and prior.has_reading and prior.pos in ('動詞','助動詞','形容詞')
                and prior.infl_form=='基本形' and prior.base_form not in ('ます','です')
                and copula.has_reading and copula.pos=='助動詞' and copula.base_form in ('だ','です')
                and any(p.startswith('名詞,非自立,助動詞語幹,') and b=='よう' and r==you.reading
                    for p,f,b,r in dictionary_inflections(you.surface) or ())):continue
        head=next((t for t in reversed(parts[:i]) if t.pos in ('動詞','形容詞') and t.pos_sub=='自立'),None)
        if head is None:continue
        core=text[head.start:you.start]
        forms=tuple(row for row in dictionary_inflections(head.surface) or ()
            if row[0].startswith(head.pos+',') and row[1]==head.infl_form and row[3]==head.reading)
        if (forms and _allows_grammatical_tail(forms,core[len(head.surface):],head.reading,head.surface)
                and _productive_predicate(core,head.surface,before=text[:head.start])):
            out.append((head.start,copula.end))
    return tuple(out)
