# -*- coding: utf-8 -*-
"""Shared native particle frames and physically justified one-key deletions.

48-AGK / GPT-6 Astra / 2026-09-15. Source evidence precedes key search;
explicit menus may offer hypotheses without automatically accepting them.
"""
import re

def _is_hiragana(ch):
    return bool(ch) and all('ぁ' <= c <= 'ゖ' for c in ch)

def particle_frames(source, start, end, dict_index=None, native_alternatives=False):
    """Native noun/case/glyph/topic boundaries, before any key hypothesis."""
    if not 0 <= start < end <= len(source):
        return []
    from morphology import tokenize, dictionary_inflections
    from reading_segments import native_nominal_phrase_faces, native_common_noun_reading
    # Menu lookup only needs the nearby nominal head, even on a long line.
    window_start = max(0, start - 28)
    tokens = tokenize(source[window_start:min(len(source), end + 4)])
    out = []
    # A topic may be swallowed by the next word's best native parse. The
    # explicit choice also considers its exact dictionary entry at that edge.
    topics = ((extra, finish, source[extra+1:finish])
              for extra in range(max(2, start), min(end, len(source)-1))
              for finish in range(extra+2, min(len(source), extra+4)+1))
    for extra, finish, topic_text in topics:
        if not any(pos.startswith('助詞,係助詞,') and rd == topic_text
                   for pos, form, base, rd in dictionary_inflections(topic_text) or ()):
            continue
        glyph = source[extra]
        readings = ((glyph,) if _is_hiragana(glyph) else tuple(dict.fromkeys(
            rd for pos, form, base, rd in dictionary_inflections(glyph) or ()
            if pos.startswith('名詞,') and '固有名詞' not in pos)))
        for case_start in range(max(1, extra - 3), extra):
            case_text = source[case_start:extra]
            if not any(pos.startswith('助詞,格助詞,') and rd == case_text
                       for pos, form, base, rd in dictionary_inflections(case_text) or ()):
                continue
            # The preceding noun must be real at this boundary. Kana can have
            # a different native segmentation; it retains its exact spelling.
            head = next((t.start + window_start for t in reversed(tokens)
                if t.end + window_start == case_start and t.has_reading and t.pos == '名詞'
                and not any(x in t.pos_sub for x in ('固有名詞','非自立','接尾'))), None)
            if head == window_start and window_start:
                head = None  # A clipped word is not native boundary evidence.
            faces = (source[head:case_start],) if head is not None else ()
            head_reading=next((t.reading for t in tokens if t.start+window_start==head and t.end+window_start==case_start),'')
            for begin in range(max(0, case_start - 24), case_start):
                reading = source[begin:case_start]
                if not reading or not all(_is_hiragana(ch) or ch == 'ー' for ch in reading):
                    continue
                if dict_index is None or native_alternatives:
                    proven = native_nominal_phrase_faces(reading)
                else:
                    # The menus already have this index. Reuse it instead of
                    # constructing the full world-reading table on first F2.
                    options = dict_index.surfaces_for_reading(reading)
                    proven = tuple(face for face in (reading, *options)
                                   if native_common_noun_reading(face, reading))
                if proven:
                    head = begin
                    faces = tuple(proven)
                    head_reading=reading
                    break
            if head is None:
                continue
            row = dict(start=head, end=finish, case_start=case_start, extra=extra,
                       case=case_text, topic=topic_text, glyph=glyph,
                       readings=readings, head_faces=faces, head_reading=head_reading)
            if row not in out:
                out.append(row)
    return out


def drop_candidate(source, frame):
    """Delete only an original neighbor key; preserve every other glyph."""
    from kana_layout import single_key_drop_adjacency, single_key_drop_is_duplicate
    from oddness import object_particle_mismatch
    case, topic = frame['case'], frame['topic']
    if case == 'が' or object_particle_mismatch(case, '助詞:格助詞', topic, '助詞:係助詞'):
        return None
    restored = case + topic
    typed = next((case + rd + topic for rd in frame['readings']
                  if single_key_drop_adjacency(case + rd + topic, restored) is True
                  and not single_key_drop_is_duplicate(case + rd + topic, restored)), None)
    if typed is None:
        return None
    start, end, extra = frame['start'], frame['end'], frame['extra']
    return dict(surface=source[start:extra]+source[extra+1:end], reading=None,
                kind='typo', span=(start,end), base=source[start:end])


def interrupted_topic_frames(source, dictionary=None):
    """Recognize the original semantic frame without searching for a repair."""
    from semantic_roles import interrupted_topic_evidence
    out=[]
    # Lexical prefilter only. Native noun/particle readings and the original
    # continuation establish the judgment; adjacency is tested later.
    for match in re.finditer(r'に[気き]は', source):
        extra=match.start()+1
        for frame in particle_frames(source,extra,extra+1,dictionary,native_alternatives=True):
            proof=interrupted_topic_evidence(source,frame)
            if proof:
                out.append(dict(frame,evidence=proof))
    return out


def native_final_particle_sequence(parts):
    """Positive completion uses native particles and the existing END grammar.

    A native compound particle such as かい is independently attested even
    when the finite-state table cannot split it. Separate final particles
    cannot turn an unexplained ん into an explanatory nominalizer.
    """
    if not parts:return True
    if not all(t.has_reading and t.pos=='助詞' and '終助詞' in t.pos_sub for t in parts):return False
    from pos_grammar import explain_kana_run
    # Restored casual spelling has the same proved native particle
    # reading; the source glyph is retained for display, not reinterpreted
    # here as an unknown word after tokenization already proved its role.
    tail=''.join(t.reading for t in parts)
    if explain_kana_run(tail,no_words=True,initial_state='END',before_kanji=False):return True
    from morphology import dictionary_inflections
    return (len(parts)==1 and len(tail)>1 and any(
        p.startswith('助詞,終助詞,') and rd==tail
        for p,f,b,rd in dictionary_inflections(tail) or ()))


def reversed_explanatory_particles(parts):
    """Explanatory ん cannot follow the final question particle か."""
    return any(a.surface=='か' and a.pos=='助詞' and '終助詞' in a.pos_sub
               and b.surface=='ん' and b.pos in ('助詞','助動詞')
               for a,b in zip(parts,parts[1:]))


def nominalized_existential_case_frames(source):
    """A nominalized finite clause needs a case before existential aru.

    JF grammar 2011-12 (nominalizing koto), TUFS grammar 005 (N ga aru).
    https://www.jpf.go.jp/j/project/japanese/teach/tsushin/grammar/201112.html
    https://www.coelang.tufs.ac.jp/mt/ja/gmod/contents/explanation/005.html
    A question/coordination ka directly between those native units supplies
    no case. Indefinite pronouns, quotations, alternatives, and open tails
    are different structures. This records grammar, never a repair answer.
    """
    if not any(piece in source for piece in ('こと','の')):return ()
    from morphology import tokenize,dictionary_inflections
    from literal_examples import protected_ranges,overlaps
    parts=tokenize(source);protected=protected_ranges(source);out=[]
    for i in range(1,len(parts)-2):
        previous,nominal,particle,existential=parts[i-1:i+3]
        if not (all(t.has_reading for t in (previous,nominal,particle,existential))
                and previous.end==nominal.start and nominal.end==particle.start
                and particle.end==existential.start
                and previous.pos in ('動詞','助動詞','形容詞')
                and previous.infl_form=='基本形'
                and nominal.pos=='名詞' and nominal.pos_sub.startswith('非自立')
                and nominal.surface in ('こと','の')
                and existential.pos=='動詞' and existential.base_form=='ある'):continue
        question=(particle.surface=='か' and particle.pos=='助詞' and '終助詞' in particle.pos_sub)
        if not question:
            # A confirmed IME commit can expose a converted question key in
            # this same grammatical slot. A native written particle already
            # supplies its own role and cannot be overridden by raw keys.
            from analysis_work import occurrence_readings
            from kanji_readings import readings_of
            if particle.pos!='名詞':continue
            # The same independently malformed case slot can contain a
            # single kanji with an attested on-reading. A noun elsewhere
            # has no such grammatical evidence and is not reopened here.
            if ('か' not in occurrence_readings(source,particle.start,particle.end)
                    and not (len(particle.surface)==1 and 'か' in readings_of(particle.surface))):continue
        if not any(p.startswith('動詞,自立,') and base=='ある' and form==existential.infl_form
                   and rd==existential.reading
                   for p,form,base,rd in dictionary_inflections(existential.surface) or ()):continue
        chain=[existential]
        for token in parts[i+3:]:
            if token.start!=chain[-1].end or not token.has_reading or token.pos!='助動詞':break
            chain.append(token)
        if chain[-1].infl_form!='基本形':continue
        start,end=previous.start,chain[-1].end
        if overlaps(start,end,protected):continue
        out.append(dict(start=start,end=end,case_start=particle.start,case_end=particle.end,
                        nominal_start=nominal.start,predicate_start=existential.start))
    return tuple(out)


def nominalized_subject_particle(source,frame,reading):
    """Restore the explicit nominative case of the same nominalized subject.

    This frame supplies no evidence for introducing a new contrast/topic.
    The physical key search chooses among native particles; ordinary source
    topic/focus forms remain valid and never enter the anomalous frame.
    """
    from morphology import dictionary_inflections,tokenize
    if not any(pos.startswith('助詞,格助詞,一般,') and base=='が' and rd==reading
               for pos,form,base,rd in dictionary_inflections(reading) or ()):return None
    a,z=frame['case_start'],frame['case_end']
    changed=source[:a]+reading+source[z:]
    particle=next((t for t in tokenize(changed) if t.start==a and t.end==a+len(reading)),None)
    if not (particle and particle.has_reading and particle.pos=='助詞'
            and particle.pos_sub=='格助詞:一般' and particle.reading==reading):return None
    return reading


def closed_question_frames(source):
    """48-AGO: an unlicensed lexical tail after a native polite ending.

    A line/column ending or sentence punctuation closes this frame; quoted mentions,
    functional/relative nouns, native final particles and punctuation-separated
    inverted phrases do not establish this source anomaly.
    """
    from morphology import HAS_JANOME, tokenize, dictionary_inflections
    if not HAS_JANOME:return []
    from literal_examples import protected_ranges, overlaps
    out=[];protected=protected_ranges(source)
    for match in re.finditer(r'[^。！？!?\t\r\n;；⇒→]+',source):
        start=match.start();clause=match.group().rstrip()
        terminal=source[match.end():match.end()+1]
        terminal=terminal if terminal in ('。','！','？','!','?') else ''
        parts=[t for t in tokenize(clause+terminal) if t.end<=len(clause)]
        if not any(t.pos=='助動詞' and t.base_form in ('ます','です') for t in parts):
            # An unknown kana token can swallow the entire subject/predicate.
            # A separately completed native reading proves this original seam.
            from reading_segments import completed_native_reading_clause
            from copy import copy
            for boundary in re.finditer('ます|です',clause):
                edge=boundary.end();head=clause[:edge]
                if not (0<len(clause)-edge<=3 and _is_hiragana(head)
                        and completed_native_reading_clause(head,require_object_fit=True)):continue
                prefix=tokenize(head)
                if not prefix or prefix[-1].pos!='助動詞':continue
                rest=[]
                for original in tokenize(clause[edge:]+terminal):
                    if original.end>len(clause)-edge:continue
                    token=copy(original);token.start+=edge;token.end+=edge;rest.append(token)
                parts=prefix+rest
                break
        for index,aux in enumerate(parts[:-1]):
            if (aux.pos!='助動詞' or aux.base_form not in ('ます','です')
                    or aux.infl_form!='基本形' or not aux.has_reading):continue
            tail=parts[index+1:]
            text=clause[aux.end:]
            kanji_tail=len(text)==1 and '一'<=text<='鿿'
            if (not tail or tail[0].start!=aux.end or tail[-1].end!=len(clause)
                    or (not kanji_tail and not all(t.has_reading for t in tail)) or len(clause)-aux.end>3):continue
            # The best parse may select a surname or an incomplete verb stem
            # for the same glyph. Neither is a license after a finite clause.
            functional=any(t.pos=='名詞' and t.pos_sub.startswith(('非自立','副詞可能')) for t in tail)
            nominal=(kanji_tail and not functional) or all(t.pos=='名詞' and t.pos_sub=='一般' for t in tail)
            # A contiguous greeting can address a following native personal name.
            # An interjection elsewhere does not license a detached noun.
            from semantic_roles import finite_clause_addressee
            if (any(t.pos_sub.startswith('固有名詞:人名') for t in tail)
                    and finite_clause_addressee(parts,index)):continue
            # Explanatory ん precedes a question particle; attaching it after
            # か does not complete the polite question. Keep かね/かい/etc.
            reversed_explanation=(len(tail)==2 and reversed_explanatory_particles(tail))
            if not (nominal or reversed_explanation):continue
            forms=dictionary_inflections(text) or ()
            from semantic_roles import finite_clause_suffix, nominal_host_suffix
            if finite_clause_suffix(text):continue
            original_reading=''.join(t.reading for t in tail)
            # A classified nominal host is not a finite-clause license. For
            # other native suffix uses keep the pre-existing protection;
            # lacking a role classification is not evidence of an error.
            if any(pos.startswith('助詞,') or
                   (pos.startswith('名詞,接尾,一般,') and rd==original_reading
                    and not nominal_host_suffix(text))
                   for pos,form,base,rd in forms):continue
            if not index:continue
            previous=parts[index-1]
            if previous.end!=aux.start or not previous.has_reading:continue
            if aux.base_form=='ます':
                if previous.pos not in ('動詞','助動詞') or not previous.infl_form.startswith('連用'):continue
            elif previous.pos not in ('名詞','形容詞'):continue
            a,b=start+aux.start,start+tail[-1].end
            if overlaps(a,b,protected):continue
            out.append(dict(start=a,end=b,aux=aux.surface,aux_reading=aux.reading,
                extra=start+aux.end,tail=text,context_end=match.end()+len(terminal)))
    return out


def closed_question_particle(source,frame,reading):
    """Validate an unchanged polite auxiliary plus a native final particle."""
    from morphology import dictionary_inflections
    from pos_grammar import explain_kana_run
    prefix=frame['aux_reading']
    if not reading.startswith(prefix):return None
    particle=reading[len(prefix):]
    if not particle or not any(pos.startswith('助詞,') and '終助詞' in pos and rd==particle
                              for pos,form,base,rd in dictionary_inflections(particle) or ()):return None
    if not explain_kana_run(particle,no_words=True,initial_state='END',before_kanji=False):return None
    return frame['aux']+particle


def adnominal_topic_frames(source):
    """A native adnominal copula needs a noun before topic + predicate.

    Positive original boundaries only: a native adjectival/auxiliary stem,
    da's adnominal form, a topic particle, then an actual finite verb.
    Bare unfinished text and a following nominal head remain undecided.
    Grammar review: GPT-6 Astra / 2026-09-15.
    """
    if not re.search(r'な[もは]',source):return []
    from morphology import tokenize,dictionary_inflections
    from contextual_repair import _productive_predicate,_allows_grammatical_tail,_completed_predicate_token
    parts=tokenize(source);out=[]
    for i in range(1,len(parts)-2):
        head,copula,topic,verb=parts[i-1:i+3]
        if not (head.end==copula.start and copula.end==topic.start and topic.end==verb.start
                and all(t.has_reading for t in (head,copula,topic,verb))
                and head.pos=='名詞' and head.pos_sub in ('形容動詞語幹','非自立:助動詞語幹')
                and copula.pos=='助動詞' and copula.base_form=='だ' and copula.infl_form=='体言接続'
                and topic.pos=='助詞' and topic.pos_sub=='係助詞'
                and verb.pos=='動詞'):continue
        tail=re.split(r'[。！？.!?、,;；\t\r\n]',source[verb.start:],maxsplit=1)[0]
        endparts=tokenize(tail)
        if not endparts or not all(t.has_reading for t in endparts):continue
        last=endparts[-1]
        if not _completed_predicate_token((last.surface,last.pos+':'+last.pos_sub,last.reading,
                last.start,last.end,last.has_reading,last.infl_form)):continue
        forms=tuple(r for r in dictionary_inflections(verb.surface) or ()
                    if r[0].startswith('動詞,') and r[1]==verb.infl_form and r[3]==verb.reading)
        if not (_allows_grammatical_tail(forms,tail[len(verb.surface):],verb.reading,verb.surface)
                and _productive_predicate(tail,verb.surface)):continue
        out.append(dict(start=copula.start,end=topic.end,topic=topic.surface))
    return out


def adverbial_topic_candidate(source,frame,reading):
    """A native adverbial particle attaches that same original topic."""
    from morphology import dictionary_inflections
    topic=frame['topic'];particle=reading[:-len(topic)] if reading.endswith(topic) else ''
    if not particle:return None
    if any(pos.startswith('助詞,副詞化,') and rd==particle
           for pos,form,base,rd in dictionary_inflections(particle) or ()):
        return particle+topic
    return None


def interrupted_comparison_frames(source):
    """An attested comparison's original case and predicate enclose a filler.

    No key search or repaired word supplies the source judgment. A spoken
    pause written with punctuation and quoted examples remain separate.
    """
    from morphology import tokenize,dictionary_inflections
    from literal_examples import protected_ranges,overlaps
    from reading_segments import (_native_source_clauses,native_surface_nominal_heads,
        native_nominal_comparison_head,completed_native_nominal_predicate)
    protected=protected_ranges(source);out=[]
    for offset,clause in _native_source_clauses(source):
        if 'と' not in clause:continue
        parts=tokenize(clause)
        for match in re.finditer('と([ぁ-ゖ])',clause):
            case_start=match.start();extra=case_start+1
            case=next((t for t in parts if t.start==case_start and t.end==extra),None)
            filler=next((t for t in parts if t.start==extra and t.end==extra+1),None)
            faces=native_surface_nominal_heads(clause[:case_start])
            if not faces:continue
            actual_case=bool(case and case.has_reading and case.pos=='助詞')
            if not actual_case:
                # A complete kana noun phrase can be split as an interjection
                # and a nonfinite adjective that absorbs と. The original
                # nominal heads and the same native case supply its boundary.
                if not _is_hiragana(clause[:case_start]):continue
                if not any(any(t.start==len(face) and t.surface=='と' and t.has_reading
                               and t.pos=='助詞'
                               for t in tokenize(face+'と')) for face in faces):continue
            if not (filler and filler.has_reading and filler.pos in ('フィラー','感動詞')):continue
            if not any(pos.startswith('助詞,格助詞,') and rd=='と'
                       for pos,form,base,rd in dictionary_inflections('と') or ()):continue
            right=clause[extra+1:];head=native_nominal_comparison_head(right)
            if head is None:continue
            if right[head.end:] and not completed_native_nominal_predicate(
                    right,allow_topic=False,allow_written=True):continue
            end=extra+1+head.end
            if overlaps(offset+case_start,offset+end,protected):continue
            out.append(dict(start=offset+case_start,end=offset+end,
                case_start=offset+case_start,extra=offset+extra,case='と',
                topic=head.reading,glyph=filler.surface,readings=(filler.reading,),
                head_faces=faces,head_reading='',reason='比較の格と述語に挟まったフィラー'))
    return out


def interrupted_particle_frames(source,dictionary=None):
    return interrupted_topic_frames(source,dictionary)+interrupted_comparison_frames(source)


from functools import lru_cache

@lru_cache(maxsize=512)
def _native_action_noun(surface,reading):
    from morphology import dictionary_inflections
    if any(p.startswith('名詞,サ変接続,') and rd==reading
           for p,f,b,rd in dictionary_inflections(surface) or ()):return True
    try:
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            if not ime.available:return False
            native=ime.reverse_words(surface+'する')
            return bool(native and native[0]==reading+'する' and native[1]
                and native[1][0][:5]==(0,len(surface),0,len(reading),101))
    except (ImportError,OSError,AttributeError,ValueError):return False

def converted_suru_connection_frames(source):
    """An action noun and a connective expose a lexical homophone of shi.

    Source action POS, exact reading and the unchanged connective establish
    the anomaly. Candidate suru inflection is verified independently.
    """
    from morphology import tokenize,dictionary_inflections
    from literal_examples import protected_ranges,overlaps
    if not any(x in source for x in ('ながら','つつ','て','た')):return ()
    parts=tokenize(source);out=[];protected=None
    for head,noun,link in zip(parts,parts[1:],parts[2:]):
        if (not all(t.has_reading for t in (head,noun,link))
                or head.end!=noun.start or noun.end!=link.start
                or head.pos!='名詞' or '固有名詞' in head.pos_sub
                or noun.pos!='名詞' or len(noun.surface)!=1
                or not '一'<=noun.surface<='鿿' or noun.reading!='し'
                or not (link.pos=='助詞' and link.pos_sub=='接続助詞'
                        and link.surface in ('ながら','つつ','て')
                    or link.pos=='助動詞' and link.base_form=='た')):continue
        if not _native_action_noun(head.surface,head.reading):continue
        changed=head.surface+'し'+link.surface
        pieces=tokenize(changed)
        verb=next((t for t in pieces if t.start==len(head.surface)),None)
        if (not verb or verb.surface!='し' or verb.pos!='動詞'
                or verb.base_form!='する' or verb.infl_form!='連用形'):continue
        if not any(p.startswith('動詞,自立,') and b=='する' and f=='連用形' and rd=='し'
                   for p,f,b,rd in dictionary_inflections('し') or ()):continue
        if protected is None:protected=protected_ranges(source)
        if overlaps(head.start,link.end,protected):continue
        out.append(dict(start=head.start,end=link.end,verb_start=noun.start,verb_end=noun.end,
                        surface='し',reading='し'))
    return tuple(out)



def interrogative_extent_frames(source):
    from morphology import tokenize,dictionary_inflections
    from literal_examples import protected_ranges,overlaps
    from semantic_roles import nominal_roles,COGNITIVE_PREDICATES
    parts=tokenize(source);out=[];protected=None
    for finite,noun,case,verb in zip(parts,parts[1:],parts[2:],parts[3:]):
        if (not all(t.has_reading for t in (finite,noun,case,verb))
            or not all(a.end==b.start for a,b in zip((finite,noun,case),(noun,case,verb)))
            or finite.pos not in ('動詞','形容詞','助動詞') or finite.infl_form not in ('基本形','連体形')
            or noun.pos!='名詞' or case.pos!='助詞' or not case.pos_sub.startswith('格助詞')
            or verb.pos!='動詞' or verb.base_form not in COGNITIVE_PREDICATES
            or 'cooking_cutting_tool' not in nominal_roles(noun.surface)):continue
        reading=noun.reading+case.reading
        pieces=tokenize(reading)
        if (len(pieces)!=2 or pieces[0].surface!='か' or pieces[1].surface!='まで'
            or not all(t.has_reading and t.pos=='助詞' for t in pieces)):continue
        if not all(any(p.startswith('助詞,') and rd==t.reading
                       for p,f,b,rd in dictionary_inflections(t.surface) or ()) for t in pieces):continue
        if protected is None:protected=protected_ranges(source)
        if overlaps(finite.start,verb.end,protected):continue
        out.append(dict(start=noun.start,end=case.end,surface=reading,reading=reading))
    return tuple(out)

@lru_cache(maxsize=2048)
def converted_connective_nominal_frames(source):
    """A finite verb exposes an unbacked noun join with a connective reading."""
    from morphology import tokenize,dictionary_inflections
    from semantic_roles import nominal_compound_support
    from literal_examples import protected_ranges,overlaps
    if not any('一'<=c<='鿿' for c in source):return ()
    parts=tokenize(source);out=[];protected=None
    for verb,noun,tail in zip(parts,parts[1:],parts[2:]):
        nominal_tail=(verb.infl_form=='基本形' and tail.pos=='名詞'
                      and tail.pos_sub in ('一般','サ変接続'))
        imperative=(verb.infl_form.startswith('命令') and tail.surface=='から'
                    and tail.pos=='助詞' and tail.pos_sub.startswith('格助詞'))
        if (not all(t.has_reading for t in (verb,noun,tail))
                or verb.end!=noun.start or noun.end!=tail.start
                or verb.pos!='動詞' or verb.pos_sub!='自立'
                or not (nominal_tail or imperative)
                or noun.pos!='名詞' or noun.pos_sub!='一般'
                or not any('一'<=c<='鿿' for c in noun.surface)
                or noun.reading not in ('て','で')):
            continue
        if imperative:
            from semantic_roles import object_before,_independent_accusative_clause
            legacy=[(p.surface,p.pos+':'+p.pos_sub,p.reading,p.start,p.end,
                     p.has_reading,p.infl_form) for p in parts]
            if (not object_before(source,verb.start,lambda _:legacy)
                    or not _independent_accusative_clause(source[tail.end:])):
                continue
        elif (dictionary_inflections(noun.surface+tail.surface)
                or nominal_compound_support(noun.surface,tail.surface)):
            continue
        if not any(p.startswith('助詞,接続助詞,') and rd==noun.reading
                   for p,f,b,rd in dictionary_inflections(noun.reading) or ()):
            continue
        if protected is None:protected=protected_ranges(source)
        if overlaps(verb.start,tail.end,protected):continue
        out.append(dict(start=verb.start,end=noun.end if imperative else tail.end,
                        head=verb.surface,nominal=noun.surface,reading=noun.reading,
                        tail=tail.surface,imperative=imperative))
    return tuple(out)


def broken_nominal_te_frames(source):
    """A noun + quotative て does not establish the expected verbal link.

    Use original native token boundaries. A real verb's te form, a whole
    lexical adverb, quoted text, and the ordinary quotation って differ.
    The rare quotation sense is attested (Daijisen / Nikkoku):
    https://kotobank.jp/word/て-573101 . This is an everyday-context
    suspicion, not rejection of every nominal quotation.
    No repaired word or expected answer supplies this source judgment.
    """
    if 'を' not in source or 'て' not in source:return ()
    from morphology import tokenize
    from literal_examples import protected_ranges,overlaps
    parts=tokenize(source);out=[];protected=None
    for i,(case,noun,link,verb) in enumerate(zip(parts,parts[1:],parts[2:],parts[3:])):
        if (case.surface!='を' or case.pos!='助詞' or not case.pos_sub.startswith('格助詞')
                or noun.pos!='名詞' or not (noun.pos_sub in ('一般','サ変接続') or noun.pos_sub.startswith('固有名詞'))
                or not noun.has_reading
                or link.surface!='て' or link.pos!='助詞' or link.pos_sub not in ('格助詞:連語','接続助詞')
                or not all(a.end==b.start for a,b in ((case,noun),(noun,link),(link,verb)))):continue
        # Written names remain names in ordinary naming/quoting clauses.
        # A real following movement (possibly with its destination) proves
        # the missing action at this accusative, independently of a repair.
        ordinary_kana=(_is_hiragana(noun.surface) and noun.pos_sub in ('一般','サ変接続')
                       and verb.pos=='動詞' and verb.pos_sub=='自立' and verb.has_reading)
        # A real non-independent verb needs the preceding action's te
        # connection too. Requests/aspects cannot make a bare noun a verb.
        from morphology import dictionary_inflections
        auxiliary=(link.pos_sub=='接続助詞' and verb.pos=='動詞'
            and verb.pos_sub=='非自立' and verb.has_reading
            and any(pos.startswith('動詞,非自立,') and form==verb.infl_form and rd==verb.reading
                    for pos,form,base,rd in dictionary_inflections(verb.surface) or ()))
        if not (ordinary_kana or auxiliary or _following_native_motion(source[link.end:])):continue
        # The actual accusative needs its independently written/read noun;
        # a stray を at the beginning cannot create this interpretation.
        if i==0 or parts[i-1].end!=case.start or parts[i-1].pos!='名詞' or not parts[i-1].has_reading:continue
        from reading_segments import completed_native_reading_link
        if completed_native_reading_link(source[noun.start:link.end],allow_unclassified=True):continue
        if protected is None:protected=protected_ranges(source)
        if overlaps(noun.start,link.end,protected):continue
        out.append(dict(start=noun.start,end=link.end,noun=noun.surface,link=link.surface))
    return tuple(out)


@lru_cache(maxsize=2048)
def broken_accusative_adverb_frames(source):
    """An actual object is stranded before particles/adverbs and a return verb.

    Movement through a place, a genuine intervening verb, punctuation and
    a following relative clause do not establish this source anomaly.
    """
    if 'を' not in source or 'て' not in source:return ()
    from morphology import tokenize,native_spelling_only
    from semantic_roles import nominal_roles,RETURN_MOTION_ACTIONS,_terminal_predicate_tail
    from literal_examples import protected_ranges,overlaps
    parts=tokenize(source);out=[];protected=None;legacy=None
    for i,case in enumerate(parts):
        if i==0 or case.surface!='を' or case.pos!='助詞' or not case.pos_sub.startswith('格助詞'):continue
        noun=parts[i-1]
        if noun.pos!='名詞' or not noun.has_reading or noun.end!=case.start:continue
        roles=nominal_roles(noun.surface)
        if roles & {'place','origin'} or not roles & {'object','device','food','text','information'}:continue
        if not native_spelling_only(noun.reading,noun.surface):continue
        j=i+1;cursor=case.end;modifiers=[]
        while j<len(parts):
            t=parts[j]
            if (t.start!=cursor or not t.has_reading or not _is_hiragana(t.surface)
                    or t.pos not in ('副詞','接続詞','助詞')):break
            modifiers.append(t);cursor=t.end;j+=1
        if (not modifiers or not any(t.pos in ('副詞','接続詞') for t in modifiers)
                or not source[case.end:cursor].endswith('て') or j>=len(parts)):continue
        verb=parts[j]
        if verb.start!=cursor:continue
        simple_return=False
        if (verb.pos=='動詞' and verb.pos_sub=='自立' and verb.has_reading
                and verb.base_form in RETURN_MOTION_ACTIONS):
            if legacy is None:
                legacy=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,t.start,t.end,t.has_reading,t.infl_form) for t in parts]
            simple_return=_terminal_predicate_tail(source,legacy,verb.end,verb.infl_form)
        if not simple_return and not _following_native_motion(source[cursor:]):continue
        if protected is None:protected=protected_ranges(source)
        if overlaps(noun.start,verb.end,protected):continue
        out.append(dict(start=case.end,end=cursor,object=noun.surface,verb=verb.surface))
    return tuple(out)


def unlinked_written_suru_frames(source):
    """An actual written terminal verb directly precedes another finite する.

    The first native verb fixes the editing head. Connectives, nominal
    modifiers, explicit literals and a merely guessed source verb do not qualify.
    Pure kana predicates retain their existing repair route.
    """
    if not ('し' in source or 'する' in source):return ()
    from ime_inverse_gate import _CORRECTION_CACHE
    cache=_CORRECTION_CACHE.get();key=('source_written_suru',source)
    if cache is not None and key in cache:return cache[key]
    from morphology import tokenize
    from contextual_repair import _finite_written_predicate,_source_clause_bounds
    from literal_examples import protected_ranges,overlaps
    parts=tokenize(source);out=[];protected=None
    for head,verb in zip(parts,parts[1:]):
        if (not all(t.has_reading for t in (head,verb)) or head.end!=verb.start
                or head.pos!='動詞' or head.pos_sub!='自立' or head.infl_form!='基本形'
                or not any('一'<=c<='鿿' for c in head.surface)
                or verb.pos!='動詞' or verb.pos_sub!='自立' or verb.base_form!='する'):
            continue
        if not _finite_written_predicate(head.surface):continue
        lo,hi=_source_clause_bounds(source,head.start,verb.end)
        tail=source[verb.start:hi].rstrip(' 。！？!?')
        if not _finite_written_predicate(tail):continue
        if protected is None:protected=protected_ranges(source)
        end=verb.start+len(tail)
        if overlaps(head.start,end,protected):continue
        out.append(dict(start=head.start,end=end,first_end=head.end,lemma=head.base_form))
    result=tuple(out)
    if cache is not None:cache[key]=result
    return result


def changed_written_suru_allowed(source,start,end,surface):
    """Repairing this seam preserves the actual first verb's native paradigm."""
    frames=unlinked_written_suru_frames(source)
    if not frames:return True
    from difflib import SequenceMatcher
    from morphology import tokenize
    from semantic_roles import _native_lexeme_forms
    from contextual_repair import _finite_written_predicate
    changed=source[:start]+surface+source[end:]
    codes=SequenceMatcher(None,source,changed,autojunk=False).get_opcodes()
    edits=[(a,b) for tag,a,b,c,d in codes if tag!='equal']
    def boundary(position):
        for tag,a,b,c,d in codes:
            if a<=position<=b:
                if tag=='equal':return c+position-a
                if position==a:return c
                if position==b:return d
        return None
    for frame in frames:
        a,b=frame['start'],frame['end']
        if not any(lo<b and a<hi or lo==hi and a<=lo<b for lo,hi in edits):continue
        begin,finish=boundary(a),boundary(b)
        if begin is None or finish is None:return False
        predicate=changed[begin:finish]
        if not _finite_written_predicate(predicate):return False
        first=tokenize(predicate)[0]
        if first.pos!='動詞' or first.pos_sub!='自立':return False
        forms=_native_lexeme_forms(frame['lemma'],first.infl_form,first.reading)
        if forms:
            if first.surface in forms or first.surface==first.reading:continue
            # Native homophones keep the source inflection/reading. Existing
            # source meanings choose their spelling; a written lemma alone
            # must not suppress a contextually supported alternative.
            from context_meaning import preserves_argument_relation
            if source[:a]!=changed[:begin]:return False
            if not preserves_argument_relation(source,a,b,changed,begin,finish,
                                               established=True):return False
            continue
        # A positively proved source meaning conflict can change its lemma,
        # using that same untouched argument and expected native meaning.
        from context_meaning import anomalous_frames,preserves_argument_relation
        conflicts=[f for f in anomalous_frames(source)
                   if f['start']==a and f['end']==frame['first_end']
                   and f.get('evidence_start',a)<a]
        if (not conflicts or source[:a]!=changed[:begin]
                or not preserves_argument_relation(source,a,b,changed,begin,finish)):
            return False
    return True


@lru_cache(maxsize=2048)
def unlinked_past_predicate_frames(source):
    """An actual completed past predicate cannot directly modify a finite verb.

    A native noun after the past ending, punctuation, and adjective/desire
    continuations are different original constructions. No next-word guess
    or repaired connective supplies this anomaly.
    """
    if not any(c in source for c in ('た','だ')):return ()
    from morphology import tokenize
    from contextual_repair import _finite_written_predicate,_source_clause_bounds
    from literal_examples import protected_ranges,overlaps
    parts=tokenize(source);out=[];protected=None
    for i,(past,verb) in enumerate(zip(parts,parts[1:])):
        if (i==0 or not all(t.has_reading for t in (past,verb)) or past.end!=verb.start
                or past.pos!='助動詞' or past.base_form not in ('た','だ') or past.infl_form!='基本形'
                or verb.pos!='動詞' or verb.pos_sub!='自立'):continue
        j=i-1;cursor=past.start
        while j>=0:
            t=parts[j]
            if t.end!=cursor or not t.has_reading:break
            if t.pos=='動詞' and t.pos_sub=='自立':break
            if not (t.pos=='助動詞' or t.pos=='動詞' and t.pos_sub=='非自立'
                    or t.pos=='助詞' and t.pos_sub=='接続助詞'):break
            cursor=t.start;j-=1
        if j<0:continue
        head=parts[j]
        if head.pos!='動詞' or head.pos_sub!='自立' or head.end!=cursor:continue
        if not _finite_written_predicate(source[head.start:past.end]):continue
        lo,hi=_source_clause_bounds(source,head.start,verb.end)
        tail=source[verb.start:hi].rstrip(' 。！？!?')
        if not _finite_written_predicate(tail):continue
        # Repeating the same completed utterance is ordinary emphasis or
        # acknowledgement. Its actual trailing final particles stay valid.
        first=source[head.start:past.end]
        if tail.startswith(first) and native_final_particle_sequence(tokenize(tail[len(first):])):continue
        if protected is None:protected=protected_ranges(source)
        if overlaps(head.start,hi,protected):continue
        out.append(dict(start=head.start,end=past.end,following_end=verb.start+len(tail)))
    return tuple(out)


def changed_past_link_allowed(source,start,end,surface):
    """Every route repairing this seam must reconnect its two actual verbs."""
    frames=unlinked_past_predicate_frames(source)
    if not frames:return True
    from difflib import SequenceMatcher
    from reading_segments import native_predicate_link_boundaries
    from contextual_repair import _finite_written_predicate
    changed=source[:start]+surface+source[end:]
    opcodes=SequenceMatcher(None,source,changed,autojunk=False).get_opcodes()
    edits=[(a,b) for tag,a,b,c,d in opcodes if tag!='equal']
    def boundary(position):
        for tag,a,b,c,d in opcodes:
            if a<=position<=b:
                if tag=='equal':return c+position-a
                if position==a:return c
                if position==b:return d
        return None
    for frame in frames:
        a,b=frame['start'],frame['end']
        if not any(lo<b and a<hi or lo==hi and a<=lo<b for lo,hi in edits):continue
        begin,join,finish=(boundary(frame[key]) for key in ('start','end','following_end'))
        if begin is None or join is None or finish is None:return False
        if join-begin not in native_predicate_link_boundaries(changed[begin:finish],0):
            return False
        if not _finite_written_predicate(changed[join:finish]):return False
    return True


@lru_cache(maxsize=1024)
def _following_native_motion(text):
    """An unchanged finite movement, optionally with its native destination."""
    from morphology import tokenize
    from semantic_roles import native_verb_lexemes,native_verb_roles,nominal_roles,_PATH_MOTION_ACTIONS
    from reading_segments import _native_written_nominal_faces
    from contextual_repair import _finite_written_predicate,_source_clause_bounds
    # Only this source clause owns the motion. A later table field or
    # sentence cannot make its finite predicate look unfinished.
    _,end=_source_clause_bounds(text,0,0)
    text=text[:end].rstrip(' 。！？!?')
    parts=tokenize(text)
    if not parts or not all(p.has_reading for p in parts):return False
    for i,verb in enumerate(parts):
        if verb.pos!='動詞' or verb.pos_sub!='自立':continue
        lexemes=native_verb_lexemes(verb.surface,verb.infl_form,verb.reading)
        if not lexemes or not lexemes<=(_PATH_MOTION_ACTIONS|{'向かう'}):return False
        if not _finite_written_predicate(text[verb.start:]):return False
        if i==0:return verb.start==0
        case=parts[i-1]
        if (case.surface not in ('に','へ') or case.pos!='助詞'
                or not case.pos_sub.startswith('格助詞') or case.end!=verb.start):return False
        faces=_native_written_nominal_faces(text[:case.start])
        roles=native_verb_roles(verb.surface,verb.infl_form,verb.reading,case=case.surface)
        return any(nominal_roles(face)&roles for face in faces)
    return False
