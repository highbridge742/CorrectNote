# -*- coding: utf-8 -*-
"""Read-only evidence that an odd reading can produce the written source.

The IME's own reverse reading and first conversion provide the primary clue.
TSF search candidates can corroborate a source produced by a different IME
choice. Absence from either interface does not prove that the source is sound.
"""
import re

from itertools import chain
from contextvars import ContextVar

_CORRECTION_CACHE = ContextVar("ime_inverse_correction_cache", default=None)


_FIELD_END = re.compile(r'[\t\r\n⇒→、,。！？!?;；]')


def _kana_reading(text):
    text=''.join(chr(ord(c)-0x60) if 'ァ'<=c<='ヶ' else c for c in text)
    return text if re.fullmatch(r'[ぁ-ゖー]+',text) else None



def _native_argument_prefix(field,tokenize):
    """Leave original dictionary nouns and their actual case chain unchanged."""
    from reading_segments import native_lexical_phrase,native_genitive_nominal_splits,native_surface_nominal_heads
    from morphology import dictionary_inflections
    parts=list(tokenize(field))
    if not parts or ''.join(t[0] for t in parts)!=field:return 0
    begin=0;edge=0;last_case=''
    for index,case in enumerate(parts):
        if not case[1].startswith('助詞:格助詞'):continue
        chunk=parts[begin:index]
        if (not chunk or not case[5] or not all(t[5] for t in chunk)
                or chunk[-1][4]!=case[3]):break
        # Focus particles qualify the same original noun; they do not
        # change its boundary or prove the following malformed predicate.
        nominal_end=case[3]
        while chunk and chunk[-1][1].startswith('助詞:副助詞'):
            focus=chunk[-1]
            if not any(pos.startswith('助詞,副助詞,') and rd==focus[2]
                       for pos,form,base,rd in dictionary_inflections(focus[0]) or ()):break
            nominal_end=focus[3];chunk=chunk[:-1]
        if not chunk:break
        nominal=field[chunk[0][3]:nominal_end]
        if not (native_lexical_phrase(nominal,tokenize)
                or native_genitive_nominal_splits(nominal)
                or native_surface_nominal_heads(nominal)):break
        edge=case[4];last_case=case[0];begin=index+1
    remaining=parts[begin:]
    return edge if (last_case=='を' and edge<len(field) and remaining
                    and remaining[0][3]==edge) else 0


def _source_readings(surface, tokenize):
    """Native token readings plus one independent lexical alternative.

    This is positive evidence, not proof that absent IME hits make the source
    normal. One alternative accounts for a misread lexical token without a
    length, score or first-N cutoff over a combinatorial character beam.
    """
    from inflected_lexicon import dictionary_readings
    parts=list(tokenize(surface))
    if not parts or ''.join(t[0] for t in parts)!=surface:
        return
    choices=[]
    for token in parts:
        face=token[0]
        if face in ('～','〜'):
            readings=['ー','へ']
        elif all('ぁ'<=c<='ゖ' or 'ァ'<=c<='ヶ' or c=='ー' for c in face):
            readings=[_kana_reading(face)]
        elif token[5]:
            readings=[_kana_reading(token[2])]
            readings.extend(_kana_reading(value)
                            for value in dictionary_readings(face))
        else:
            return
        readings=list(dict.fromkeys(reading for reading in readings if reading))
        if not readings:return
        choices.append(readings)
    native=[row[0] for row in choices]
    first=''.join(native)
    seen={first}
    yield first
    for index,options in enumerate(choices):
        for alternative in options[1:]:
            variant=''.join(native[:index]+[alternative]+native[index+1:])
            if variant not in seen:
                seen.add(variant)
                yield variant


def _written_nominal_group(field, group, tokenize):
    """A whole native nominal or an attested productive action modifier."""
    from reading_segments import native_lexical_phrase
    from morphology import dictionary_inflections
    if not group:return False
    prefixed=(group[0][1]=='接頭詞:名詞接続'
              and all(t[1].startswith('名詞') for t in group[1:]))
    if not (prefixed or all(t[1].startswith('名詞') for t in group)):return False
    face=field[group[0][3]:group[-1][4]]
    first=group[0]
    if (first[1].startswith('名詞:接尾') and not any(
            pos.startswith(('名詞,一般,','名詞,サ変接続,','名詞,副詞可能,'))
            and rd==first[2] and base==first[0]
            for pos,form,base,rd in dictionary_inflections(first[0]) or ())):
        # A different reading of this glyph may be a noun. It cannot supply
        # a missing host to the suffix in this actual source segmentation.
        return False
    if native_lexical_phrase(face,tokenize):return True
    if prefixed:return False
    # The original anomaly judge already accepts this productive noun
    # composition. Preserve that same written syntax before an inverse
    # kana parse; it supplies neither a lexical unit nor a candidate sense.
    from oddness import ordinary_nominal_composition
    if (len(group)>1 and all(native_lexical_phrase(t[0],tokenize) for t in group)
            and all(ordinary_nominal_composition(a[0],a[1],b[0],b[1])
                    for a,b in zip(group,group[1:]))):return True
    # A written native name (optionally with its native name suffix) can
    # own a nominal case. This proves the original group, not an arbitrary
    # name/ordinary-noun compound or a kana spelling candidate.
    name_end=(2 if len(group)>1 and group[0][1]=='名詞:固有名詞:人名:姓'
              and group[1][1]=='名詞:固有名詞:人名:名' else 1)
    if (group[0][1].startswith('名詞:固有名詞')
            and all(t[1].startswith(('名詞:接尾:人名','名詞:接尾:地域'))
                    for t in group[name_end:])
            and all(t[5] and any(':'.join(x for x in pos.split(',') if x!='*')==t[1]
                                and rd==t[2] for pos,form,base,rd
                                in dictionary_inflections(t[0]) or ()) for t in group)):
        return True
    if len(group)==1:
        head=group[0]
        return bool(head[1].startswith('名詞:非自立:副詞可能')
            and any(pos.startswith('名詞,非自立,副詞可能,') and rd==head[2]
                for pos,form,base,rd in dictionary_inflections(head[0]) or ()))
    head=group[0]
    if ((head[1].startswith('名詞:サ変接続')
             or head[1]=='名詞:一般'
             and all(t[1]=='名詞:接尾:一般' for t in group[1:])
             and head[3]>0
             and _written_attributive_end(field[:head[3]],tokenize(field[:head[3]])))
            and native_lexical_phrase(head[0],tokenize)
            and all(t[1].startswith('名詞:接尾') and any(
                pos.startswith('名詞,接尾,') and rd==t[2]
                for pos,form,base,rd in dictionary_inflections(t[0]) or ())
                for t in group[1:])):return True
    return bool(head[1].startswith('名詞:副詞可能')
        and group[-1][1].startswith('名詞:サ変接続')
        and native_lexical_phrase(field[group[1][3]:group[-1][4]],tokenize))


def _written_nominal_note(field, parts, tokenize):
    """Attested nominal groups and their actual particles form an open note."""
    from morphology import dictionary_inflections
    # A written connective/adverb may introduce an ordinary nominal note.
    # Verify its original dictionary POS; dependent adverbs still need a host.
    from semantic_roles import adverbial_reading_needs_host
    leading=False
    while parts and parts[0][1].split(':')[0] in ('接続詞','副詞'):
        t=parts[0]
        if (adverbial_reading_needs_host(t[0],t[2]) or not any(
                ':'.join(x for x in pos.split(',') if x!='*')==t[1] and rd==t[2]
                for pos,form,base,rd in dictionary_inflections(t[0]) or ())):return False
        parts=parts[1:];leading=True
    if not parts:return False
    begin=0;links=0
    for i,t in enumerate(parts):
        if t[1].startswith('名詞') or t[1]=='接頭詞:名詞接続':continue
        if not (t[1].startswith(('助詞:格助詞','助詞:係助詞','助詞:連体化','助詞:並立助詞'))
                and _written_nominal_group(field,parts[begin:i],tokenize) and any(
                    ':'.join(x for x in pos.split(',') if x!='*')==t[1] and rd==t[2]
                    for pos,form,base,rd in dictionary_inflections(t[0]) or ())):return False
        begin=i+1;links+=1
    return bool((links or leading)
        and (begin==len(parts) or _written_nominal_group(field,parts[begin:],tokenize)))


def _written_attributive_end(field, parts):
    """The existing native relative ending, including its polite auxiliary chain."""
    from reading_segments import native_attributive_predicate_end
    from morphology import dictionary_paradigms,tokenize as native_tokens
    if not native_attributive_predicate_end(field):return False
    native=native_tokens(field)
    # だ has both copular and voiced-past dictionary entries. Only the
    # actual preceding verb's licensed attachment proves the latter.
    if (native and native[-1].pos=='助動詞' and native[-1].base_form=='だ'
            and native[-1].infl_form=='基本形'):
        from morphology import dictionary_inflections
        from contextual_repair import _allows_grammatical_tail
        head=native[-2] if len(native)>1 else None
        forms=tuple(row for row in dictionary_inflections(head.surface) or ()
                    if row[3]==head.reading and row[1]==head.infl_form) if head else ()
        if not (head and head.pos in ('動詞','助動詞') and forms
                and _allows_grammatical_tail(forms,native[-1].surface,
                                            head.reading,head.surface)):return False
    for token in reversed(parts):
        if not token[1].startswith('助動詞'):break
        if any(pos.startswith('助動詞,') and kind in ('特殊・マス','特殊・デス')
                and form==token[6] and reading==token[2]
                for pos,kind,form,base,reading in dictionary_paradigms(token[0]) or ()):
            return False
    return True


def _written_relative_note(field, parts, tokenize):
    """A native attributive clause keeps its noun and optional case/action note."""
    if not parts or not all(t[5] for t in parts):return False
    end=len(parts)
    if (end>=2 and parts[-1][1].startswith('名詞:サ変接続')
            and parts[-2][1].startswith(('助詞:格助詞','助詞:係助詞'))
            and _written_nominal_group(field,parts[-1:],tokenize)):
        end-=1
    while end and parts[end-1][1].startswith(('助詞:格助詞','助詞:係助詞','助詞:副助詞','助詞:連体化')):
        end-=1
    start=end
    while start and (parts[start-1][1].startswith('名詞')
                     or parts[start-1][1]=='接頭詞:名詞接続'):start-=1
    if not start or start==end:return False
    return bool(_written_nominal_group(field,parts[start:end],tokenize)
        and _written_attributive_end(field[:parts[start][3]],parts[:start]))


def anomalous_source_fields(line, tokenize, store, dictionary, source_marks=(), display_ranges_out=None):
    """Yield original field ranges with an independently odd inverse reading."""
    if not line or dictionary is None:
        return ()
    # One correction can ask the source gate several times while validating
    # the same original. Keep positive and negative evidence only for that
    # correction; a later input starts with fresh IME state.
    cache=_CORRECTION_CACHE.get()
    marks=tuple(sorted(set((a,b) for a,b in source_marks if 0<=a<b<=len(line))))
    key=('marked_source_fields',line,marks) if marks else line
    if cache is not None and key in cache:
        if display_ranges_out is not None:
            display_ranges_out.update(cache.get(('source_alias_display',key),{}))
        return cache[key]
    import kanji_guess
    from analysis_work import occurrence_readings
    from ime_candidates import SearchCandidates
    from ime_language import JapaneseIME
    from pos_grammar import odd_kana_spans,prolonged_quotative

    fields = []
    start = 0
    for separator in _FIELD_END.finditer(line):
        if start < separator.start():
            closed = separator.group() in '\t\r\n⇒→。！？!?'
            fields.append((start, separator.start(), closed))
        start = separator.end()
    if start < len(line):
        fields.append((start, len(line), False))
    # Pure kana has its own source grammar, and a one-word dictionary surface
    # has no surrounding segmentation for IME to have changed.
    from kango_tier import is_restricted
    fields = [(a, b, closed) for a, b, closed in fields
              if any('一' <= c <= '鿿' for c in line[a:b])
              and (any('ぁ'<=c<='ゖ' or 'ァ'<=c<='ヶ' for c in line[a:b])
                   or any(t[5] and is_restricted(t[0]) for t in tokenize(line[a:b])))]
    # A prolonged expressive sound before quotative と is an attested
    # adverbial shape, even when a kana-only reparse dislikes the clause.
    fields=[(a,b,closed) for a,b,closed in fields
            if not prolonged_quotative(line[a:b])]
    from reading_segments import native_paused_nominal_ranges
    pauses=native_paused_nominal_ranges(line)
    fields=[(a,b,closed) for a,b,closed in fields
            if not any(lo<=a and b<=hi for lo,hi in pauses)]
    # A complete native predicate is positive source evidence. Kana-only
    # grammar can fail on a rare noun plus an ordinary auxiliary and cannot
    # override the written clause's intact native analysis.
    marked_finite_fields=set()
    def intact_predicate(field, closed, marked=False):
        # 48-APE: a written native noun with its attested particle
        # already passes the shared source proof. A kana reparse must not
        # manufacture a structural override for that completed source.
        from reading_segments import native_lexical_phrase,native_mixed_kana_word_ranges
        if ((0,len(field)) in native_mixed_kana_word_ranges(field)
                or native_lexical_phrase(field,tokenize)):return True
        from reading_segments import native_open_nominal_fragment
        if not closed and native_open_nominal_fragment(field):return True
        parts=list(tokenize(field))
        known=bool(parts and ''.join(t[0] for t in parts)==field
                   and all(t[5] for t in parts))
        # A sequence of independently read native nouns is a possible
        # compound. An odd kana reparse cannot mark it wrong by itself.
        if not known:return False
        # A final finite form cannot dismiss an already independent source mark.
        # The whole native word and other positive syntax checks remain above.
        finite=(not marked and parts[-1][1].startswith(('助動詞','動詞','形容詞'))
            and parts[-1][6]=='基本形')
        if finite:return True
        if not marked and _written_nominal_note(field,parts,tokenize):return True
        # A note can end at an object plus verbal noun, and an
        # imperative can take a final particle. Both are positive
        # native analyses even if their all-kana reparse looks odd.
        # Multiple known kanji pieces are not themselves an attested word.
        # Whole native words/meaningful compounds already returned above;
        # investigate an unproved all-kanji segmentation using the same
        # exact IME membership and independently odd reading as mixed text.
        noun_phrase=(all(t[1].startswith('名詞') for t in parts)
            and not (len(parts)>1 and all('一'<=c<='鿿' for c in field)))
        genitive_phrase=(parts[-1][1].startswith('名詞')
            and any(t[0]=='の' and t[1]=='助詞:連体化' for t in parts)
            and all(t[1].startswith('名詞')
                or t[0]=='の' and t[1]=='助詞:連体化' for t in parts))
        object_note=(len(parts)>=2 and parts[-1][1].startswith('名詞')
            and parts[-2][0]=='を' and parts[-2][1].startswith('助詞:格助詞'))
        imperative=(len(parts)>=2 and parts[-1][1].startswith('助詞:終助詞')
            and parts[-2][1].startswith('動詞')
            and parts[-2][6].startswith('命令'))
        direct_imperative=False
        if (parts[-1][1].startswith('動詞:自立')
                and parts[-1][6].startswith('命令')):
            from morphology import tokenize as native_tokens
            from contextual_repair import _native_imperative_completion
            native=list(native_tokens(field))
            direct_imperative=bool(native and native[-1].surface==parts[-1][0]
                and native[-1].start==parts[-1][3]
                and native[-1].reading==parts[-1][2]
                and native[-1].infl_form==parts[-1][6]
                and _native_imperative_completion(native[-1:]))
        question=(len(parts)>=2 and parts[-1][1].startswith('助詞:終助詞')
            and parts[-2][1].startswith(('助動詞','動詞','形容詞'))
            and parts[-2][6]=='基本形')
        # A native sahen noun plus the literary finite する is complete.
        # Kana grammar may misread its short ending as an odd Shift result.
        literary_sahen=(len(parts)>=2
            and parts[-2][1].startswith('名詞:サ変接続')
            and parts[-1][1].startswith('動詞:自立')
            and parts[-1][6]=='文語基本形'
            and parts[-2][4]==parts[-1][3])
        # A complete comparison has an attested nominal before the case
        # particle and a native comparative determiner after it. The IME
        # may reverse a polyphonic noun to a different, awkward reading.
        comparison=(len(parts)>=3 and parts[-1][1]=='連体詞'
            and parts[-2][0]=='と' and parts[-2][1].startswith('助詞:格助詞')
            and any(t[1].startswith('名詞') for t in parts[:-2])
            and not any(t[1].startswith('フィラー') for t in parts))
        # A nominalized verb clause ending in negative conjunctive なく
        # remains a valid clause before a comma. Its phonetic spelling may
        # look odd when the IME chooses homophones inside the long clause.
        # A plain past predicate can modify a following native noun. The
        # polite past auxiliary ました is finite here and is not a noun modifier.
        relative_noun=(len(parts)>=3 and parts[-1][1].startswith('名詞')
            and parts[-2][1].startswith('助動詞') and parts[-2][0] in ('た','だ')
            and parts[-3][1].startswith('動詞')
            and (parts[-3][6]=='連用タ接続'
                 or parts[-3][6]=='連用形' and parts[-3][0]=='し'
                 and any(t[1].startswith('名詞:サ変接続') for t in parts[:-3])))
        # The unchanged native verb may directly modify a noun. Confirm its
        # actual dictionary form and the noun's existing lexical proof before
        # an all-kana IME reparse is allowed to mark the source anomalous.
        from morphology import dictionary_paradigms
        simple_relative=(len(parts)==2 and parts[0][1].startswith('動詞:自立')
            and parts[0][6]=='基本形' and parts[1][1].startswith('名詞')
            and native_lexical_phrase(parts[1][0],tokenize)
            and any(pos.startswith('動詞,自立,') and form=='基本形'
                    and base==parts[0][0] and reading==parts[0][2]
                    for pos,kind,form,base,reading
                    in dictionary_paradigms(parts[0][0]) or ()))
        negative_link=(len(parts)>=4 and parts[-1][1].startswith('助動詞')
            and parts[-1][6]=='連用テ接続'
            and parts[-2][1].startswith('助詞:係助詞')
            and parts[-3][1].startswith('名詞:非自立')
            and any(t[1].startswith('動詞') for t in parts[:-3]))
        # Native inflection can prove a sound continuation even when an
        # all-kana reparse labels an unfinished fragment odd. A tab or an
        # explicit example boundary still lets the inverse gate investigate.
        previous = parts[-2] if len(parts) > 1 else None
        open_tail = not closed and (
            len(parts) >= 2
            and parts[-1][1].startswith('名詞:接尾')
            and parts[-2][1].startswith('助動詞')
            and parts[-2][6] == '基本形'
            or parts[-1][1].startswith('形容詞:自立')
            and parts[-1][6] in ('連用形', '連用テ接続')
            or previous is not None
            and parts[-1][1].startswith('助詞:接続助詞')
            and (parts[-1][0] in ('て', 'で')
                 and previous[1].startswith(('動詞:', '助動詞'))
                 and previous[6] in ('連用形', '連用タ接続', '連用テ接続')
                 or parts[-1][0] == 'が'
                 and previous[1].startswith(('動詞:', '助動詞', '形容詞:'))
                 and previous[6] == '基本形')
            or len(parts) >= 3
            and parts[-1][1].startswith('名詞')
            and parts[-2][0] in ('て', 'で')
            and parts[-2][1].startswith('助詞:接続助詞')
            and parts[-3][1].startswith('動詞:自立')
            and parts[-3][6] in ('連用形', '連用タ接続'))
        # The actual written word boundaries also establish ordinary
        # connective clauses. Re-parsing their all-kana reading must not
        # turn a native noun into an unrelated homophone.
        def nominal_head(items):
            return bool(items and items[0][1].startswith('名詞')
                and items[-1][1].startswith('名詞')
                and all(t[1].startswith('名詞')
                    or t[0]=='の' and t[1]=='助詞:連体化' for t in items))
        # A finite predicate can be nominalized and take a case, including
        # native compound particles such as に対し. These written boundaries
        # establish the connection without an all-kana IME interpretation.
        nominalized_case=(len(parts)>=3
            and parts[-1][1].startswith('助詞:格助詞')
            and parts[-2][1].startswith('名詞:非自立')
            and parts[-3][1].startswith(('動詞:','形容詞:','助動詞'))
            and parts[-3][6]=='基本形')
        case_topic=(len(parts)>=3 and nominal_head(parts[:-2])
            and parts[-2][1].startswith('助詞:格助詞')
            and parts[-1][1].startswith('助詞:係助詞'))
        negative_nominal=False
        # で/では/でも/じゃ + the actual negative continuative なく.
        # This is a copular connection, not a list of protected source words.
        from morphology import dictionary_inflections
        for i,t in enumerate(parts):
            if not nominal_head(parts[:i]):continue
            tail=parts[i:]
            if tail[-1][0]=='て' and tail[-1][1]=='助詞:接続助詞':tail=tail[:-1]
            if not tail:continue
            negative=tail[-1]
            if not any(pos.startswith(('助動詞,','形容詞,')) and base=='ない'
                       and form in ('連用形','連用テ接続') and rd==negative[2]
                       for pos,form,base,rd in dictionary_inflections(negative[0]) or ()):continue
            link=tail[:-1]
            if link and link[0][0]=='で':
                copula=any(pos.startswith('助動詞,') and base=='だ' and form=='連用形'
                           for pos,form,base,rd in dictionary_inflections('で') or ())
                valid=bool(copula and (len(link)==1 or len(link)==2
                    and link[1][0] in ('は','も') and link[1][1].startswith('助詞:係助詞')))
            else:
                valid=bool(len(link)==1 and link[0][0]=='じゃ'
                           and link[0][1].startswith('助詞:副助詞'))
            if valid:negative_nominal=True;break
        written_te=False
        if parts[-1][0] in ('て','で') and parts[-1][1]=='助詞:接続助詞':
            from contextual_repair import _productive_predicate,_allows_grammatical_tail
            # Begin at the first real predicate, including its sahen noun.
            # A later valid して cannot certify a malformed 読むして prefix.
            first=next((i for i,t in enumerate(parts) if t[1].startswith(('動詞:','形容詞:','助動詞'))),None)
            if first is not None:
                if first and parts[first-1][1].startswith('名詞:サ変接続'):first-=1
                head=parts[first];before=field[:head[3]];surface=field[head[3]:]
                forms=tuple(row for row in dictionary_inflections(head[0]) or ()
                            if row[3]==head[2] and (row[1] if row[1]!='*' else '')==head[6])
                written_te=bool(forms and _allows_grammatical_tail(forms,field[head[4]:],head[2],head[0])
                    and _productive_predicate(surface,head[0],before=before))
        # The written case and exact native inflection prove an unfinished
        # continuation or relative clause. An all-kana reparse cannot replace
        # its auxiliary with another word. Independent source marks still win.
        written_predicate=False
        # A good final verb does not attest the earlier nominal groups.
        # Confirm each actual noun phrase; bound grammatical stems are
        # checked by the shared predicate attachment proof below.
        source_nominals=True;group_start=0
        while group_start<len(parts):
            if not parts[group_start][1].startswith('名詞'):
                group_start+=1;continue
            group_end=group_start+1
            while group_end<len(parts) and parts[group_end][1].startswith('名詞'):
                group_end+=1
            group=parts[group_start:group_end]
            nominal=_written_nominal_group(field,group,tokenize)
            previous=parts[group_start-1] if group_start else None
            functional=bool(previous and previous[1].startswith(('動詞','形容詞','助動詞'))
                and all(t[1].startswith('名詞:非自立') or
                    t[1].startswith(('名詞:接尾:助動詞語幹','名詞:特殊:助動詞語幹')) for t in group))
            if not (nominal or functional):source_nominals=False;break
            group_start=group_end
        if not marked and source_nominals:
            if _written_relative_note(field,parts,tokenize):return True
            from contextual_repair import _productive_predicate,_allows_grammatical_tail
            from reading_segments import _native_open_predicate
            end=len(parts)
            # An indirect question retains its finite predicate before
            # the native question particle. Validate the unchanged suffix
            # using only functional grammar, not candidate word guesses.
            from pos_grammar import explain_kana_run
            for i in range(1,end):
                question_part=parts[i];prior=parts[i-1];tail=parts[i:]
                if (question_part[0]!='か' or not question_part[1].startswith('助詞:')
                        or '終助詞' not in question_part[1]
                        or prior[6]!='基本形'
                        or not prior[1].startswith(('動詞','形容詞','助動詞'))):continue
                if (all(t[1].startswith(('助詞:','副詞:')) and any(
                        ':'.join(x for x in pos.split(',') if x!='*')==t[1]
                        and rd==t[2] for pos,form,base,rd
                        in dictionary_inflections(t[0]) or ()) for t in tail)
                        and explain_kana_run(field[question_part[3]:],no_words=True,
                            initial_state='END',before_kanji=False)):
                    end=i;break
            # A conditional clause can precede a bare action in a note.
            # Keep both original spans: the final nominal was proved above,
            # and the predicate below must attest the actual conditional
            # attachment. A finite past alone supplies no such boundary.
            from contextual_repair import _self_contained_conditional
            if (end>=3 and parts[-1][1].startswith('名詞:サ変接続')
                    and _self_contained_conditional(parts[-2])):
                end-=1
            nominal_end=end
            while nominal_end and parts[nominal_end-1][1].startswith((
                    '助詞:格助詞','助詞:係助詞','助詞:副助詞','助詞:連体化')):
                nominal_end-=1
            if (nominal_end>=2 and parts[nominal_end-1][1].startswith('名詞')
                    and parts[nominal_end-2][1].startswith(('動詞','助動詞'))
                    and parts[nominal_end-2][6]=='基本形'
                    and native_lexical_phrase(field[parts[nominal_end-1][3]:],tokenize)
                    and _written_attributive_end(field[:parts[nominal_end-1][3]],parts[:nominal_end-1])):
                end=nominal_end-1
            # A quoted finite statement can end in a bare action noun in
            # a note. The actual quotation particle retains its boundary.
            if (end>=3 and parts[end-1][1].startswith('名詞:サ変接続')
                    and parts[end-2][1].startswith('助詞:格助詞:引用')
                    and native_lexical_phrase(parts[end-1][0],tokenize)):
                end-=2
            last_case=max((i for i,t in enumerate(parts[:end])
                if t[0] in ('を','に','が','へ','から','で')
                and t[1].startswith('助詞:格助詞')),default=-1)
            first=next((i for i in range(last_case+1,end)
                if parts[i][1].startswith(('動詞:自立','形容詞:自立')) or
                parts[i][1].startswith('名詞:サ変接続') and i+1<end
                and parts[i+1][1].startswith('動詞')),None)
            if first is not None:
                head=parts[first];surface=field[head[3]:parts[end-1][4]]
                forms=tuple(row for row in dictionary_inflections(head[0]) or ()
                    if row[0].split(',')[0]==head[1].split(':')[0]
                    and row[3]==head[2] and (row[1] if row[1]!='*' else '')==head[6])
                from reading_segments import native_likeness_predicate_ranges
                written_predicate=(0,len(surface)) in native_likeness_predicate_ranges(surface)
                written_predicate=written_predicate or bool(forms and (
                    _allows_grammatical_tail(forms,surface[len(head[0]):],head[2],head[0])
                    and _productive_predicate(surface,head[0],before=field[:head[3]])
                    or _native_open_predicate(surface,head[0],before=field[:head[3]])))
        intact=(noun_phrase or genitive_phrase or object_note or imperative
                or direct_imperative
                or literary_sahen or question or comparison or relative_noun
                or simple_relative or negative_link or open_tail
                or nominalized_case or case_topic or negative_nominal or written_te
                or written_predicate)
        if (not intact and marked
                and parts[-1][1].startswith(('助動詞','動詞','形容詞'))
                and parts[-1][6]=='基本形'):
            marked_finite_fields.add(field)
        return intact
    fields=[(a,b,closed) for a,b,closed in fields
            if not intact_predicate(line[a:b],closed,
                                    any(a<=lo<hi<=b for lo,hi in marks))]
    if not fields:
        if cache is not None:cache[key]=()
        return ()

    def completed_source_prefix(field):
        """Retain an attested native predicate and following nominal argument.

        A malformed IME tail can make the entire phonetic sentence look odd.
        The last explicit case after an attested verb+past+noun phrase is an
        existing boundary, so the IME clue may only open the following tail.
        """
        from contextual_repair import _productive_predicate
        parts=list(tokenize(field))
        for i in range(1,len(parts)-1):
            if ((parts[i][1].startswith('助動詞') and parts[i][6]=='基本形'
                     or parts[i][1].startswith('助詞:接続助詞') and parts[i][0] in ('て','で'))
                    and parts[i-1][1].startswith('動詞')
                    and (parts[i-1][6]=='連用タ接続'
                         or parts[i-1][6]=='連用形'
                         and _productive_predicate(field[parts[i-1][3]:parts[i][4]],
                             parts[i-1][0],before=field[:parts[i-1][3]]))
                    and parts[i+1][1].startswith('名詞')
                    and all(t[5] for t in parts[:i+2])):
                # The modifier does not certify an arbitrary later noun or
                # every later case particle. Only its own proved nominal
                # phrase can move this boundary past a case.
                from reading_segments import native_lexical_phrase
                for j in range(i+2,len(parts)):
                    t=parts[j]
                    if t[1].startswith('助詞:格助詞'):
                        nominal=field[parts[i+1][3]:t[3]]
                        if not native_lexical_phrase(nominal,tokenize):break
                        edge=t[4];following=j+1
                        # Further unchanged native arguments can belong to
                        # this same clause. Extend only through each proved
                        # noun/case pair, never across an unexplained word.
                        while following<len(parts):
                            first=following
                            while (following<len(parts) and parts[following][5]
                                   and parts[following][1].startswith('名詞')):following+=1
                            if following==first or following>=len(parts):break
                            case=parts[following]
                            if not case[1].startswith('助詞:格助詞'):break
                            noun=field[parts[first][3]:case[3]]
                            if not native_lexical_phrase(noun,tokenize):break
                            edge=case[4];following+=1
                        return edge
                    if not t[1].startswith('名詞') or not t[5]:break
        return 0

    found = []
    display_ranges={}
    aliases_complete=True
    from contextlib import ExitStack
    with ExitStack() as owned:
        first=owned.enter_context(JapaneseIME())
        search=None
        def search_provider():
            nonlocal search
            from analysis_context import check_current_request
            check_current_request()
            # TSF activation can be expensive even when no candidate is used.
            # Keep the same fallback, opening it only when it is needed.
            if search is None:search=owned.enter_context(SearchCandidates())
            return search
        if not first.available and not search_provider().available:
            return ()
        for start, end, closed in fields:
            surface = line[start:end]
            morph=first.reverse_words(surface) if first.available else None
            native_reading=(morph[0] if morph else
                            first.phonetic(surface) if first.available else None)
            if cache is not None:
                cache['phonetic',surface]=native_reading
                cache['morph',surface]=morph
            # An unproved all-kanji compound has no anomalous kana seam.
            # Only the current occurrence or IME's actual inverse reading
            # can open it; alternate dictionary readings cannot manufacture
            # an error in a correctly read native compound.
            direct=chain((native_reading,),occurrence_readings(line,start,end))
            # Input aliases are hypotheses until the complete original and
            # forward word edges agree; they are never a typed-key deletion.
            alias_scopes={}
            def marked_input_aliases():
                nonlocal aliases_complete
                field_marks=tuple((lo,hi) for lo,hi in marks if start<=lo<hi<=end)
                if not field_marks or not morph:return
                for a,b,c,d,_,_ in morph[1]:
                    if not any(start+a<hi and lo<start+b for lo,hi in field_marks):continue
                    aliases=inverse_context_input_aliases(surface,a,b)
                    if cache is not None and ('inverse_context_input_aliases',surface,a,b) not in cache:
                        aliases_complete=False
                    for alias,segments in aliases:
                        whole=morph[0][:c]+alias+morph[0][d:]
                        lo,hi=a,b
                        while True:
                            overlapping=[(x-start,y-start) for x,y in field_marks
                                         if start+lo<y and x<start+hi]
                            expanded=(min([lo]+[x for x,y in overlapping]),
                                      max([hi]+[y for x,y in overlapping]))
                            if expanded==(lo,hi):break
                            lo,hi=expanded
                        alias_scopes[whole]=(lo,hi)
                        yield whole
            # An intact finite ending was excluded before the marked-word
            # extension. Only its original marked word's proven input alias
            # may open that scope; an odd whole-sentence kana reparse cannot.
            hypotheses=(marked_input_aliases() if surface in marked_finite_fields else
                direct if all('一'<=c<='鿿' for c in surface) else
                chain(direct,kanji_guess.ime_readings_for(surface),
                      _source_readings(surface,tokenize),marked_input_aliases()))
            tried=set()
            for raw in hypotheses:
                reading=_kana_reading(raw) if isinstance(raw,str) else None
                if not reading or reading in tried:continue
                tried.add(reading)
                source_match=first.convert(reading)==surface if first.available else False
                first_match=source_match
                if cache is not None and reading==native_reading:
                    cache['first_match',surface]=source_match
                if not source_match and search_provider().available:
                    try:hits=search.candidates(reading)
                    except Exception:hits=None
                    source_match=bool(hits and surface in hits)
                if not source_match:continue
                # Exact IME conversion or TSF membership is positive evidence.
                if odd_kana_spans(reading+'\t',dictionary,store):
                    if cache is not None:
                        cache['source_readings',surface]=((reading,first_match),)
                    edge=completed_source_prefix(surface)
                    if not edge:edge=_native_argument_prefix(surface,tokenize)
                    # Trimming an independently proved original prefix changes
                    # the scope being accused by this inverse-reading clue.
                    # Judge that actual suffix again; a whole-line bad reparse
                    # cannot override its own intact native word or grammar.
                    if edge and intact_predicate(surface[edge:],closed,
                            any(start+edge<=lo<hi<=end for lo,hi in marks)):
                        break
                    found.append((start+edge,end,reading))
                    if reading in alias_scopes:
                        lo,hi=alias_scopes[reading]
                        display_ranges[start+edge,end]=(start+lo,start+hi)
                    break
    result=tuple(found)
    if cache is not None and aliases_complete:
        cache[key]=result
        if display_ranges:cache['source_alias_display',key]=display_ranges
    if display_ranges_out is not None:display_ranges_out.update(display_ranges)
    return result

def first_roundtrip(surface):
    """Whether the IME's own reading first-converts to this finished surface.

    None means the read-only interface supplied no evidence. A False result
    constrains only repairs whose source was opened by the IME inverse gate.
    """
    if not surface:return None
    cache=_CORRECTION_CACHE.get();key=('candidate_first_roundtrip',surface)
    if cache is not None and key in cache:return cache[key]
    from ime_language import JapaneseIME
    with JapaneseIME() as ime:
        if not ime.available:return None
        reading=ime.phonetic(surface)
        converted=ime.convert(reading) if reading else None
        result=(converted==surface) if converted is not None else None
    if cache is not None:cache[key]=result
    return result

def exact_context_reading(surface,start,end):
    """Slice source IME words only when the complete original first-roundtrips.

    A fragment can choose different kanji out of context. Whole-field proof
    retains the original surroundings; exact word boundaries prevent guessing
    how a kanji's reading should be split. No candidate/answer is consulted.
    """
    if not 0<=start<end<=len(surface):return None
    return _slice_context_reading(_exact_context_morph(surface),start,end)


def _exact_context_morph(surface):
    cache=_CORRECTION_CACHE.get()
    key=('exact_context_morph',surface)
    if cache is not None and key in cache:
        morph=cache[key]
    else:
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            morph=(cache.get(('morph',surface)) if cache is not None else None)
            if morph is None and ime.available:
                morph=ime.reverse_words(surface)
                if cache is not None:cache['morph',surface]=morph
            confirmed=cache.get(('first_match',surface)) if cache is not None else None
            if confirmed is None and morph and ime.available:
                confirmed=ime.convert(morph[0])==surface
                if cache is not None:cache['first_match',surface]=confirmed
            if not confirmed:morph=None
        if cache is not None:cache[key]=morph
    return morph


def attested_context_reading(surface,start,end):
    """Aligned native source words can attest a reading without first choice.

    First conversion may change a written kana variant or choose another
    homophone. Its failure supplies no evidence against the independently
    attested source words. This is dictionary evidence, not an IME round trip.
    """
    if not 0<=start<end<=len(surface):return None
    cache=_CORRECTION_CACHE.get();key=('attested_context_reading',surface,start,end)
    if cache is not None and key in cache:return cache[key]
    from ime_language import JapaneseIME
    from morphology import dictionary_inflections
    result=None
    with JapaneseIME() as ime:
        morph=cache.get(('morph',surface)) if cache is not None else None
        if morph is None and ime.available:morph=ime.reverse_words(surface)
    sliced=_slice_context_reading(morph,start,end)
    if sliced:
        reading,segments=sliced
        attested=[]
        for a,b,rd,origin in segments:
            face=surface[start+a:start+b]
            if _kana_reading(face)==rd:
                kind='literal_kana'
            elif any(value==rd for pos,form,base,value in dictionary_inflections(face) or ()):
                kind='dictionary_word'
            else:break
            attested.append((a,b,rd,kind))
        else:
            if (attested and all(a[1]==b[0] for a,b in zip(attested,attested[1:]))):
                result=reading,tuple(attested)
    if cache is not None:cache[key]=result
    return result


def native_context_readings(surface,start,end,*,mark_keys=False):
    """Attest native word alternatives against the complete original field.

    Marked source keys also retain literal hiragana/katakana equivalents;
    unmarked words and normalized input aliases keep their own edge proof.
    """
    morph=(_exact_mark_context_morph(surface) if mark_keys else _exact_context_morph(surface))
    base=_slice_context_reading(morph,start,end,mark_keys=mark_keys,
                                literal_source=surface if mark_keys else None)
    if not base:return ()
    cache=_CORRECTION_CACHE.get();key=('native_context_readings',surface,start,end)
    if mark_keys:key+=('mark_keys',)
    if cache is not None and key in cache:return cache[key]
    from morphology import dictionary_inflections
    from ime_language import JapaneseIME
    from contextual_repair import _search_step
    reading,words=morph;variants={}
    for a,b,c,d,_,_ in words:
        if not start<=a<b<=end or not any('一'<=ch<='鿿' for ch in surface[a:b]):continue
        native=tuple(dict.fromkeys(rd for pos,form,lemma,rd in dictionary_inflections(surface[a:b]) or ()
                         if _kana_reading(rd) and not pos.startswith('名詞,固有名詞,')))
        aliases=[]
        # The IME can normalize じ/ぢ and ず/づ while reversing a word.
        # These are input hypotheses, never equivalent physical keys.
        # Every alias must reproduce this whole field and its real word edges.
        if reading[c:d] in native:
            for i,ch in enumerate(reading[c:d]):
                other={'じ':'ぢ','ぢ':'じ','ず':'づ','づ':'ず'}.get(ch)
                if other:aliases.append(reading[c:c+i]+other+reading[c+i+1:d])
        for rd in dict.fromkeys(native+tuple(aliases)):
            if rd==reading[c:d]:continue
            whole=reading[:c]+rd+reading[d:]
            segments=tuple((lo,hi,rd if (lo,hi)==(a-start,b-start) else piece,origin)
                           for lo,hi,piece,origin in base[1])
            if not any((lo,hi)==(a-start,b-start) for lo,hi,_,_ in base[1]):continue
            variants.setdefault(whole,(segments,rd not in native))
    found=[];complete=True
    if variants:
        with JapaneseIME() as ime:
            if ime.available:
                for whole,(segments,needs_forward) in variants.items():
                    if not _search_step('native_context_word_checks',64):complete=False;break
                    converted=ime.convert(whole)
                    if not (_literal_kana_surface_matches(surface,converted) if mark_keys
                            else converted==surface):continue
                    if needs_forward:
                        forward=ime.convert_words(whole)
                        if not forward or not (_literal_kana_surface_matches(surface,forward[0])
                            if mark_keys else forward[0]==surface):continue
                        sliced=_slice_context_reading((whole,forward[1]),start,end,mark_keys=mark_keys,
                                                      literal_source=surface if mark_keys else None)
                        if not sliced or sliced[1]!=segments:continue
                    found.append((''.join(piece for _,_,piece,_ in segments),segments))
    result=tuple(found)
    if cache is not None and complete:cache[key]=result
    return result


def inverse_context_input_aliases(surface,start,end):
    """A normalized inverse word may differ from a first-converting input.

    Only the original field and its real forward word boundaries attest an
    alias. This is source-reading evidence, not deletion of a typed key.
    """
    if not 0<=start<end<=len(surface):return ()
    cache=_CORRECTION_CACHE.get();key=('inverse_context_input_aliases',surface,start,end)
    if cache is not None and key in cache:return cache[key]
    from ime_language import JapaneseIME
    from contextual_repair import _search_step
    found=[];complete=True
    with JapaneseIME() as ime:
        if not ime.available:return ()
        morph=cache.get(('morph',surface)) if cache is not None else None
        if morph is None:morph=ime.reverse_words(surface)
        if not morph:return ()
        reading,words=morph
        for a,b,c,d,pos,flags in words:
            if not start<=a<b<=end or not any('一'<=ch<='鿿' for ch in surface[a:b]):continue
            piece=reading[c:d]
            for index,char in enumerate(piece):
                if not 'ぁ'<=char<='ゖ' or len(piece)<2:continue
                alias=piece[:index]+piece[index+1:]
                whole=reading[:c]+alias+reading[d:]
                if not _search_step('native_word_forward_checks',64):complete=False;break
                if ime.convert(whole)!=surface:continue
                forward=ime.convert_words(whole)
                if not forward or forward[0]!=surface:continue
                sliced=_slice_context_reading((whole,forward[1]),start,end)
                if sliced and sliced not in found:found.append(sliced)
            if not complete:break
    result=tuple(found)
    if cache is not None and complete:cache[key]=result
    return result


def _slice_context_reading(morph,start,end,mark_keys=False,literal_source=None):
    if not morph:return None
    reading,words=morph
    own=[]
    for a,b,c,d,pos,flags in words:
        if b<=start or end<=a:continue
        lo,hi=max(a,start),min(b,end)
        if (lo,hi)!=(a,b):
            # A literal kana auxiliary can span the repair edge in IME
            # segmentation. Its written characters already prove each key;
            # never split a kanji reading or a normalized/nonliteral word.
            if (literal_source is None or literal_source[a:b]!=reading[c:d]
                    or not re.fullmatch(r'[ぁ-ゖー゛゜]+',reading[c:d])):return None
            c+=lo-a;d=c+hi-lo;a,b=lo,hi
        own.append((a,b,c,d,pos,flags))
    if not own or own[0][0]!=start or own[-1][1]!=end:return None
    rd=reading[own[0][2]:own[-1][3]]
    if not (_kana_reading(rd) or mark_keys and re.fullmatch(r'[ぁ-ゖー゛゜]+',rd)):return None
    return rd,tuple((a-start,b-start,reading[c:d],'ime_context_word')
                    for a,b,c,d,pos,flags in own)


def exact_mark_context_reading(surface,start,end):
    """Keep written mark keys when the whole source first-converts back.

    The reverse IME can pronounce a raw ゜ as まる. Only those literal
    source words replace their spoken reading; every other IME word keeps
    its original reading and aligned boundaries. Literal kana script alone
    may differ in that conversion; kanji and mark positions must agree.
    This supplies source key
    evidence after an anomaly, never a new anomaly or chosen repair.
    """
    if not 0<=start<end<=len(surface) or not any(c in '゛゜' for c in surface[start:end]):return None
    return _slice_context_reading(_exact_mark_context_morph(surface),start,end,mark_keys=True,
                                  literal_source=surface)


def _literal_kana_surface_matches(source,converted):
    """A source key is unchanged by hiragana/katakana display alone.

    Preserve every kanji, literal mark, separator and character position.
    Voicing, small kana, long vowels and homophones are not interchangeable.
    This supplies marked source readings only, never a repaired output.
    """
    return (isinstance(converted,str) and len(source)==len(converted)
            and all(a==b or _kana_reading(a) is not None
                    and _kana_reading(a)==_kana_reading(b)
                    for a,b in zip(source,converted)))


def _exact_mark_context_morph(surface):
    """Return the same whole-source proof for slicing and native variants."""
    cache=_CORRECTION_CACHE.get();key=('exact_mark_context_morph',surface)
    if cache is not None and key in cache:
        morph=cache[key]
    else:
        from ime_language import JapaneseIME
        morph=None
        with JapaneseIME() as ime:
            reverse=cache.get(('morph',surface)) if cache is not None else None
            if reverse is None and ime.available:reverse=ime.reverse_words(surface)
            if reverse:
                reading,words=reverse
                pieces=[];aligned=[];source_edge=0;read_edge=0;changed=False
                for a,b,c,d,pos,flags in words:
                    if a!=source_edge or not a<b or not 0<=c<d<=len(reading):break
                    face=surface[a:b]
                    literal=face and all(ch in '゛゜' for ch in face)
                    rd=face if literal else reading[c:d]
                    changed=changed or literal and rd!=reading[c:d]
                    pieces.append(rd);aligned.append((a,b,read_edge,read_edge+len(rd),pos,flags))
                    source_edge=b;read_edge+=len(rd)
                else:
                    rebuilt=''.join(pieces)
                    if (changed and source_edge==len(surface)
                            and _literal_kana_surface_matches(surface,ime.convert(rebuilt))):
                        morph=(rebuilt,tuple(aligned))
        if cache is not None:cache[key]=morph
    return morph


def cached_context_neighbors(source,start,end):
    """Use a previously confirmed original IME field at exact word edges.

    No new IME query is made by a physical-key check. Only the full original
    first-roundtrip already established by the source gate is available;
    no candidate spelling or neighboring example field supplies keys.
    """
    cache=_CORRECTION_CACHE.get()
    if cache is None or not 0<=start<end<=len(source):return None
    lo=0;hi=len(source)
    for sep in _FIELD_END.finditer(source):
        if sep.end()<=start:lo=sep.end()
        elif sep.start()>=end:hi=sep.start();break
        else:return None
    field=source[lo:hi]
    if not cache.get(('first_match',field)):return None
    morph=cache.get(('morph',field))
    if not morph:return None
    reading,words=morph
    starts={a:c for a,b,c,d,pos,flags in words};ends={b:d for a,b,c,d,pos,flags in words}
    left=ends.get(start-lo) if start>lo else 0
    right=starts.get(end-lo) if end<hi else len(reading)
    if left is None or right is None:return None
    before=reading[:left];after=reading[right:]
    if (before and not _kana_reading(before)) or (after and not _kana_reading(after)):return None
    return before,after
