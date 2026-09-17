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
            reversed_explanation=(len(tail)==2 and tail[0].surface=='か'
                and tail[0].pos=='助詞' and '終助詞' in tail[0].pos_sub
                and tail[1].surface=='ん' and tail[1].pos in ('助詞','助動詞'))
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
