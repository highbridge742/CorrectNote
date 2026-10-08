# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""原文の異様範囲・文脈・読み・打鍵を保った補正。

辞書や誤字の正解表を持たない。既存の異様判定を先に受け取り、
原文座標を動かさず候補を検算する。候補を見つけたことは異様の根拠にしない。
"""
from dataclasses import dataclass, asdict, replace
from functools import lru_cache
import re
import unicodedata
from oddness import auxiliary_connection_mismatch as _auxiliary_connection_mismatch


from morphology import COLUMN_SEPARATOR
_SEPARATOR = re.compile(COLUMN_SEPARATOR.pattern + r'|[。！？!?;；]')


def _source_separator_ranges(line):
    """Share existing detached-symbol boundaries without changing source positions."""
    from morphology import detached_symbol_separators
    ranges=sorted([m.span() for m in _SEPARATOR.finditer(line)]
                  +list(detached_symbol_separators(line)))
    merged=[]
    for lo,hi in ranges:
        if merged and lo<=merged[-1][1]:
            merged[-1]=(merged[-1][0],max(merged[-1][1],hi))
        else:merged.append((lo,hi))
    return tuple(merged)


@dataclass(frozen=True)
class RepairTarget:
    source: str
    start: int
    end: int
    context_start: int
    context_end: int
    anomalies: tuple
    structural: bool
    following: str
    boundary_kind: str = 'lexical'
    preserved_head: str = ''
    spelling: tuple = ()
    candidate_surface: str = ''
    candidate_reading: str = ''
    require_ime_first_roundtrip: bool = False
    semantic_conflict: bool = False
    object_slot: bool = False

    @property
    def text(self):
        return self.source[self.start:self.end]

    @property
    def context(self):
        return self.source[self.context_start:self.context_end]

    def substitute(self, surface):
        return (self.source[self.context_start:self.start] + surface
                + self.source[self.end:self.context_end])


@dataclass(frozen=True)
class Reading:
    text: str
    source: str
    rank: int
    segments: tuple = ()
    provenance: tuple = ()


@dataclass(frozen=True)
class KeyRepair:
    reading: str
    operation: str
    position: int
    pressed: str
    intended: str
    cost: float


@dataclass(frozen=True)
class ClauseKeyRepair(KeyRepair):
    # Each component position refers to the original target's key sequence.
    steps: tuple = ()


def _kana(text):
    return ''.join(chr(ord(c)-0x60) if 'ァ' <= c <= 'ヶ' else c for c in text)


def _is_reading(text):
    return bool(text) and all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in text)


def _input_kana(text):
    """Keep the originally pressed mark keys even when not valid phonetic kana."""
    return _kana(text).translate(str.maketrans({'\u3099':'゛','\u309a':'゜','\uff9e':'゛','\uff9f':'゜'}))


def _is_input_reading(text):
    # Candidate readings still use _is_reading: a malformed mark is only source evidence.
    return bool(text) and all('ぁ'<=c<='ゖ' or c in 'ー゛゜' for c in text)


def _case_boundary(t):
    return t[1].startswith(('助詞:格助詞', '助詞:係助詞', '助詞:連体化'))


def _literal_boundary(t):
    return any(c.isascii() and (c.isalnum() or c in '+_') for c in t[0])


def _completed_predicate_token(token):
    """A native finite form is context before the next anomalous word."""
    if (len(token)<7 or not token[5] or token[6] not in ('基本形','連体形')
            or not token[1].startswith(('動詞','形容詞','助動詞'))):
        return False
    from morphology import dictionary_inflections
    return any(pos.split(',')[0]==token[1].split(':')[0]
        and form==token[6] and reading==token[2]
        for pos,form,base,reading in dictionary_inflections(token[0]) or ())


def _preserves_completed_auxiliary_end(source_parts,parts):
    """A source finite auxiliary cannot become a new unfinished ending."""
    if (not source_parts or not source_parts[-1][1].startswith('助動詞')
            or not _completed_predicate_token(source_parts[-1])):
        return True
    # A finite-looking past token attached to an incompatible original
    # word is not a completed source ending. Use the same native connection
    # evidence as anomaly detection before protecting that ending.
    if len(source_parts)>1:
        from oddness import past_auxiliary_mismatch,noun_past_aux_mismatch
        source=' '*source_parts[0][3]+''.join(t[0] for t in source_parts)
        if (past_auxiliary_mismatch(source_parts[-2],source_parts[-1],
                include_finite_verbs=True,include_adjective_forms=True)
                or noun_past_aux_mismatch(source_parts[-2],source_parts[-1],source)):
            return True
    # Native sentence punctuation follows the finite lexical ending.
    # It cannot complete an unfinished stem or dangling connective itself.
    edge=len(parts)
    while (edge and parts[edge-1][1].startswith('記号') and parts[edge-1][0]
           and all(c in '。！？.!?' for c in parts[edge-1][0])):
        edge-=1
    return bool(edge and _completed_predicate_token(parts[edge-1]))


def _native_imperative_completion(parts):
    """48-ANT: an exact native imperative closes its unchanged verb chain.

    GPT-6 Astra / 2026-09-20. The best kana parse can choose an open
    potential form instead. Only an actual same-reading imperative with
    the same native POS can close it. Compound verbs reuse their native
    continuative attachment; a finite preceding verb is not a stem.
    """
    if not parts:return False
    last=parts[-1]
    if not last.has_reading or last.pos!='動詞':return False
    from morphology import dictionary_inflections,Token
    native_pos='動詞,'+last.pos_sub.replace(':',',')+','
    for pos,form,base,rd in dictionary_inflections(last.surface) or ():
        if not (pos.startswith(native_pos) and form.startswith('命令')
                and rd==last.reading):continue
        if len(parts)==1:
            if last.pos_sub=='自立':return True
            continue
        alternative=Token(last.surface,last.pos,base,rd,last.start,last.end,
                          True,last.pos_sub,form)
        if _native_continuative_attachment(parts[-2],alternative):return True
    return False


def _kana_nominal_boundary_spans(parts):
    """かなの語の断片と、辞書活用で確定できる接続不一致を分ける。

    語の内部の読み探索は既存経路に残す。語をまたぐ活用の不一致は
    漢字表記と同じ原文範囲で検査する。異様判定そのものは共有する。
    """
    import oddness
    out=[]
    for i in range(1, len(parts)):
        a, b = parts[i-1], parts[i]
        # A native non-finite verb cannot attach this dependent noun.
        # Keep that existing source anomaly when both tokens are in kana;
        # the whole range may be one misspelled noun, not a request verb.
        if (a[5] and b[5] and a[4]==b[3] and b[1].startswith('名詞:非自立')
                and oddness.infl_mismatch(a,b,parts[i-2] if i>1 else None)):
            out.append((a[3],b[4]));continue
    return tuple(dict.fromkeys(out))


def _kana_grammar_boundary_spans(parts):
    import oddness
    out=[]
    for i in range(1,len(parts)):
        a,b=parts[i-1],parts[i]
        if (oddness.polite_aux_mismatch(a, b, parts[:i-1]) or oddness.excess_aux_mismatch(a,b) or oddness.mai_aux_mismatch(a,b)
                or oddness.repeated_polite_aux_mismatch(parts[i-2] if i>1 else None,a,b)):
            out.append((a[3],b[4]));continue
        if not _auxiliary_connection_mismatch(a,b,parts[i-2] if i>1 else None):
            continue
        # かなは語中も動詞・助動詞へ割れやすい。接尾の一字を見ただけで
        # 語内探索から奪わず、述語としての明示的な語尾まである範囲を移す。
        if _completed_predicate_token(b):
            out.append((a[3],b[4]));continue
        if i+1 < len(parts):
            c=parts[i+1]
            if c[3]!=b[4] or not c[5]:
                continue
            if c[1].startswith('助詞:接続助詞') and c[0] in ('て','で','つつ','ながら'):
                out.append((a[3],b[4]));continue
            if c[1].startswith('助動詞'):
                from morphology import dictionary_inflections
                if any(p.startswith('助動詞,') and base in ('ます','た','ない','たい','ぬ','ん','う')
                       for p,form,base,rd in dictionary_inflections(c[0]) or ()):
                    out.append((a[3],b[4]));continue
    return tuple(dict.fromkeys(out))


def _kana_grammar_boundary(parts,begin,finish):
    return (any(start<finish and begin<end
                for start,end in _kana_grammar_boundary_spans(parts))
            or any(begin<=start and end==finish
                   for start,end in _kana_nominal_boundary_spans(parts)))


@lru_cache(maxsize=2048)
def _orphan_case_finite_predicate(text):
    """The source has a native case particle without its left argument.

    Used only after an existing whole-range anomaly. A correctly parsed
    finite tail marks the source slot; candidate existence is not evidence.
    """
    if not _is_input_reading(text):return False
    from morphology import tokenize as native_tokenize
    from reading_segments import completed_native_verb_reading
    parts=native_tokenize(text)
    if len(parts)<3:return False
    first,head=parts[:2]
    if not (first.start==0 and first.has_reading and first.pos=='助詞'
            and first.pos_sub.startswith('格助詞') and first.end==head.start
            and head.has_reading and head.pos=='動詞' and head.pos_sub=='自立'):
        return False
    return bool(not completed_native_verb_reading(text,require_roles=False,finite_only=True)
        and completed_native_verb_reading(text[first.end:],require_roles=False,finite_only=True))


def _native_unattached_masu_tail(text):
    """A closed kana masu field with no earlier native case argument."""
    if not _is_input_reading(text):return False
    from morphology import tokenize
    from reading_segments import native_polite_auxiliary_chains
    parts=tokenize(text)
    if any(p.has_reading and p.pos=='助詞' and p.pos_sub.startswith('格助詞') for p in parts):
        return False
    return any(start>=2 and end==len(text) and signature[0][1]=='ます'
               for start,end,signature in native_polite_auxiliary_chains(text))


def _unexplained_kana_request_targets(line, lo, hi, tokenize, store, dictionary, source_anomalies=(), grammar_spans=None):
    """48-AGL: reuse source kana oddness for a native request-word repair.

    No requested spelling is guessed here. The clause edge or a native
    te/de link supplies the original left boundary.
    Object/case predicates already have their own source-proof route.
    Candidate requests still pass the ordinary physical and final checks.
    """
    from morphology import HAS_JANOME,source_yoon_spans
    if not HAS_JANOME:return []
    import pos_grammar
    clause=line[lo:hi]
    if not re.search(r'[ぁ-ゖー゛゜]{4,}$',clause):return []
    odd=pos_grammar.odd_kana_spans(clause,dictionary,store) if grammar_spans is None else grammar_spans
    # 48-AJV: reuse the native POS anomaly already shown in this clause.
    # It extends only the nominal slot, not the broad request route.
    slot_odd=tuple(dict.fromkeys(list(odd)+[(a,b) for _,_,a,b in source_anomalies]))
    if not slot_odd:return []
    starts={0}
    # Display grouping may swallow the connective together with an odd tail.
    # The grammar boundary uses actual native tokens, as candidate proof does.
    from morphology import tokenize as native_tokenize
    from reading_segments import native_predicate_link_boundaries
    completed_links=native_predicate_link_boundaries(clause,0)
    parts=native_tokenize(clause)
    for previous,link in zip(parts,parts[1:]):
        if (previous.has_reading and link.has_reading and previous.end==link.start
                and link.surface in ('て','で') and link.pos=='助詞'
                and link.pos_sub.startswith('接続助詞') and previous.pos=='動詞'
                and _modern_te_allowed(previous.surface,previous.reading,link.surface) is True
                and link.end in completed_links):
            starts.add(link.end)
    result=[]
    # 48-AJF: the same already marked kana clause may instead contain a
    # noun slot bounded by an actual genitive and case. A filler-like
    # parse inside that malformed noun cannot erase the surrounding frame.
    from reading_segments import native_modified_argument_slots,native_nominal_phrase_faces
    for begin,head_start,case_start,finish,relative in native_modified_argument_slots(clause):
        if native_nominal_phrase_faces(clause[head_start:case_start]):continue
        head_end=case_start
        if relative:
            from reading_segments import native_genitive_nominal_splits
            splits=native_genitive_nominal_splits(clause[head_start:case_start],True)
            if len(splits)==1 and not splits[0][1]:head_end=head_start+splits[0][0]
        anomalies=tuple(('品詞文法','未説明の修飾名詞',lo+a,lo+b)
                        for a,b in slot_odd if a<head_end and head_start<b)
        if anomalies:
            result.append(RepairTarget(line,lo+head_start,lo+head_end,lo,hi,
                anomalies,True,clause[head_end:],'lexical'))
    for start in (max(starts),):
        tail=clause[start:]
        if (not 4<=len(tail)<=18 or not _is_input_reading(tail)
                or not any(a<=start and b>=len(clause) for a,b in odd)):
            continue
        # A broad kana run may include a normally spelled voice/interjection.
        # Reuse the source fragment's own grammar before assigning its anomaly.
        from corrector import _kana_run_is_odd_by_grammar
        if (not _kana_run_is_odd_by_grammar(tail,dictionary,store)
                or any(t.has_reading and t.pos in ('感動詞','フィラー')
                       for t in native_tokenize(tail))):continue
        result.append(RepairTarget(line,lo+start,hi,lo,hi,
            tuple(('品詞文法','未説明のかな語尾',lo+a,lo+b) for a,b in odd
                  if a<len(clause) and start<b),True,'',
                  'lexical' if source_yoon_spans(tail)
                  else 'auxiliary_connection' if start==0 and (
                      _orphan_case_finite_predicate(tail) or _native_unattached_masu_tail(tail))
                  else 'kana_request'))
    return result


def _unexplained_nominal_source_targets(line,lo,hi,start,anomalies):
    """48-ALI/ALU/ANR: a marked object owns its unchanged native context."""
    if not anomalies:return []
    from reading_segments import (native_nominal_phrase_faces,completed_native_link_clause,
                                  native_adverbial_reading_cuts)
    context=line[lo:hi];out=[]
    # An already anomalous closed noun/topic field owns its whole noun slot.
    # The actual native topic remains outside the key repair; it cannot be
    # consumed by a merely homographic noun or a request-word candidate.
    from morphology import dictionary_inflections
    if (hi<len(line) and line[hi] in '\t\r\n⇒→。！？!?'
            and context[-1:] in ('は','も')
            and any(pos.startswith('助詞,係助詞,') and rd==context[-1]
                    for pos,form,base,rd in dictionary_inflections(context[-1]) or ())):
        end=hi-1;noun=line[start:end]
        if (2<=len(noun)<=18 and _is_input_reading(noun)
                and not native_nominal_phrase_faces(noun)
                and any(a<end and start<b for _,_,a,b in anomalies)):
            out.append(RepairTarget(line,start,end,lo,hi,anomalies,True,
                                    line[end:hi],'nominal_topic'))
    # Reuse only original, independently attested adjunct boundaries.
    # The following noun still needs the existing anomaly and actual object
    # slot. Retain the broad interpretation, and never certify a new word
    # merely because its repaired spelling would complete the sentence.
    from reading_segments import native_object_clause_edges
    starts=sorted({start}|{start+cut for cut in native_adverbial_reading_cuts(line[start:hi])}
                  |{lo+edge for edge in native_object_clause_edges(context) if lo+edge>=start})
    for cut,sizes in _original_counted_object_slots(context,include_unexplained=True):
        end=lo+cut-1
        # A plain slot attests the actual source verb and full tail. A
        # quantity keeps its existing independent completion requirement.
        if sizes!=(0,) and not any(completed_native_link_clause(context[cut+size:]) for size in sizes):continue
        for begin in starts:
            noun=line[begin:end]
            if (not 2<=len(noun)<=12 or not _is_input_reading(noun)
                    or native_nominal_phrase_faces(noun)
                    or not any(a<end and begin<b for _,_,a,b in anomalies)):continue
            # A rare native whole word remains classified independently
            # of common-usage/meaning coverage and generated alternatives.
            if sizes==(0,):
                from reading_segments import native_lexical_reading_faces
                if native_lexical_reading_faces(noun):continue
            kind='nominal_object' if sizes==(0,) else 'lexical'
            out.append(RepairTarget(line,begin,end,lo,hi,anomalies,True,line[end:hi],kind))
    return out


def _unexplained_nominal_targets(targets):
    """Retain a broad interpretation while sharing its marked object slot."""
    targets=list(targets)
    for target in tuple(targets):
        if (target.boundary_kind!='kana_request' or not target.structural
                or not target.anomalies or target.spelling or target.preserved_head):continue
        for candidate in _unexplained_nominal_source_targets(target.source,target.context_start,
                target.context_end,target.start,target.anomalies):
            if candidate not in targets:targets.append(candidate)
    return targets


def _marked_case_leading_intrusion_targets(line, lo, hi, parts, odd, existing):
    """Reuse a marked extra key before an attested written or kana verb."""
    if not odd or any(len(part)<7 for part in parts):
        return []
    from morphology import dictionary_inflections
    from kana_layout import single_key_drop_adjacency
    targets=[]
    for i in range(1,len(parts)-3):
        noun,case,extra,verb,following=parts[i-1:i+4]
        if (not noun[5] or not noun[1].startswith('名詞')
                or noun[4]!=case[3]
                or case[0]!='を' or not case[1].startswith('助詞:格助詞')
                or case[4]!=extra[3] or len(extra[0])!=1
                or not _is_input_reading(extra[0])
                or extra[4]!=verb[3]
                or not verb[5] or not verb[1].startswith('動詞:自立')
                or verb[6] not in ('連用形','連用タ接続')
                or verb[4]!=following[3]):
            continue
        written=any('一'<=c<='鿿' for c in verb[0])
        from oddness import orphan_case_leading_mismatch
        source_prefix=orphan_case_leading_mismatch(extra,verb,case)
        native_connective=(written and source_prefix
            and following[0]=='て' and following[5]
            and following[1].startswith('助詞:接続助詞'))
        if native_connective:
            pass
        elif written:
            if (verb[6]!='連用形' or not following[5] or not following[1].startswith('助動詞')
                    or following[0] not in ('ます','まし')):
                continue
            if following[0]=='まし' and not (
                    i+4<len(parts) and parts[i+4][0]=='た'
                    and parts[i+4][1].startswith('助動詞')
                    and parts[i+4][3]==following[4]):
                continue
        else:
            if (verb[6]!='連用形' or not _is_input_reading(verb[0])
                    or not extra[1].startswith('助詞:')
                    or following[0]!='て'
                    or not following[1].startswith('助詞:接続助詞')
                    or not following[5]):
                continue
            # A different sentence or quoted tail cannot close this verb.
            tail=[]
            for part in parts[i+4:]:
                if part[1].startswith('記号:'):
                    if part[0] in '。！？!?」』”':
                        break
                    continue
                tail.append(part)
            if (len(tail)<2 or tail[-1][0]!='ます'
                    or not tail[-1][1].startswith('助動詞')
                    or not tail[-2][1].startswith('動詞:自立')
                    or tail[-2][6]!='連用形'
                    or tail[-2][4]!=tail[-1][3]):
                continue
        marks=tuple((left,right,lo+a,lo+b) for left,right,a,b in odd
                    if (a==case[3] and b==extra[4])
                    or (source_prefix and a==extra[3] and b==verb[4]))
        if (not marks or verb[4]-extra[3]>12
                or any(t.start<=lo+extra[3]<t.end for t in existing)):
            continue
        if not any(pos.startswith('動詞,自立,') and form==verb[6]
                   and reading==verb[2]
                   for pos,form,base,reading in dictionary_inflections(verb[0]) or ()):
            continue
        if single_key_drop_adjacency(extra[0]+verb[2],verb[2]) is not True:
            continue
        targets.append(RepairTarget(line,lo+extra[3],lo+verb[4],lo,hi,
            marks,True,line[lo+verb[4]:hi],'case_leading_intrusion'))
    return targets




def _marked_case_leading_suru_intrusion_targets(line, lo, hi, parts, odd, existing):
    """Share a marked extra kana key before a native suru action."""
    if not odd:
        return []
    from ime_inverse_gate import exact_context_reading
    from kana_layout import single_key_drop_adjacency
    from literal_examples import protected_ranges,overlaps
    from morphology import dictionary_inflections,native_suru_form

    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    sequences=[(a,b,c,d,e,f,None) for a,b,c,d,e,f in zip(
        parts,parts[1:],parts[2:],parts[3:],parts[4:],parts[5:])]
    sequences.extend((parts[i],parts[i+2],parts[i+3],parts[i+4],
                      parts[i+5],parts[i+6],parts[i+1])
                     for i in range(len(parts)-6)
                     if parts[i+1][0]=='だけ' and parts[i+1][5]
                     and parts[i+1][1].startswith('助詞:副助詞')
                     and parts[i][4]==parts[i+1][3]
                     and parts[i+1][4]==parts[i+2][3])
    for head,case,extra,action,suru,link,focus in sequences:
        converted=(extra[5] and extra[1].startswith('名詞')
                   and len(extra[0])==1 and '一'<=extra[0]<='鿿'
                   and len(extra[2])==1 and _is_input_reading(extra[2]))
        if (not head[5] or not head[1].startswith('名詞')
                or case[0]!='を' or not case[1].startswith('助詞:格助詞')
                or not (converted or extra[1].startswith('助詞:')
                        and len(extra[0])==1 and _is_input_reading(extra[0]))
                or not action[5] or not action[1].startswith('名詞:サ変接続')
                or suru[0]!='し' or not suru[5]
                or not suru[1].startswith('動詞:自立') or suru[6]!='連用形'
                or link[0] not in ('て','で') or not link[5]
                or not link[1].startswith('助詞:接続助詞')
                or (head[4]!=case[3] if focus is None else not converted)
                or any(a[4]!=b[3] for a,b in
                       ((case,extra),(extra,action),(action,suru),(suru,link)))
                or overlaps(lo+extra[3],lo+action[4],protected)
                or any(t.start<=lo+extra[3]<t.end and (not converted or t.boundary_kind!='ime_scope') for t in existing)):
            continue
        if converted:
            marks=tuple((left,right,lo+a,lo+b) for left,right,a,b in odd
                        if left=='IME逆読み' and a<=extra[3] and b>=action[4])
        else:
            marks=tuple((left,right,lo+a,lo+b) for left,right,a,b in odd
                        if a==case[3] and b==extra[4])
        if not marks:
            continue
        if not (any(pos.startswith('名詞,サ変接続,') and rd==action[2]
                    for pos,form,base,rd in dictionary_inflections(action[0]) or ())
                and native_suru_form(suru[0],suru[6],suru[2],False)):
            continue
        if converted:
            first=exact_context_reading(clause,extra[3],extra[4])
            second=exact_context_reading(clause,action[3],action[4])
            if (not first or not second or first[0]!=extra[2]
                    or second[0]!=action[2]):
                continue
            reading=first[0]+second[0]
        else:
            exact=exact_context_reading(clause,extra[3],action[4])
            if not exact:
                continue
            reading,segments=exact
            if (len(segments)!=2 or segments[0][:3]!=(0,1,extra[2])
                    or segments[1][:3]!=(1,1+len(action[0]),action[2])
                    or reading!=extra[2]+action[2]):
                continue
        if single_key_drop_adjacency(reading,action[2]) is not True:
            continue
        targets.append(RepairTarget(line,lo+extra[3],lo+action[4],lo,hi,
            marks,True,line[lo+action[4]:hi],'case_leading_intrusion'))
    return targets




def _marked_case_numeric_suru_targets(line, lo, hi, parts, odd):
    """Scope a marked one-kana particle with a native numeral and して."""
    if not odd:
        return []
    from literal_examples import protected_ranges,overlaps
    from morphology import dictionary_inflections,native_suru_form

    protected=protected_ranges(line)
    targets=[]
    for head,case,kana,numeral,suru,link in zip(
            parts,parts[1:],parts[2:],parts[3:],parts[4:],parts[5:]):
        if (not head[5] or not head[1].startswith('名詞')
                or case[0]!='を' or not case[1].startswith('助詞:格助詞')
                or not kana[1].startswith('助詞:') or len(kana[0])!=1
                or not _is_input_reading(kana[0])
                or not numeral[5] or not numeral[1].startswith('名詞:数')
                or suru[0]!='し' or not suru[5]
                or not suru[1].startswith('動詞:自立') or suru[6]!='連用形'
                or link[0] not in ('て','で') or not link[5]
                or not link[1].startswith('助詞:接続助詞')
                or any(a[4]!=b[3] for a,b in
                       ((head,case),(case,kana),(kana,numeral),(numeral,suru),(suru,link)))
                or overlaps(lo+kana[3],lo+suru[4],protected)):
            continue
        marks=tuple((left,right,lo+a,lo+b) for left,right,a,b in odd
                    if a==case[3] and b==kana[4])
        if not marks:
            continue
        if not (any(pos.startswith('名詞,数,') and rd==numeral[2]
                    for pos,form,base,rd in dictionary_inflections(numeral[0]) or ())
                and native_suru_form(suru[0],suru[6],suru[2],False)):
            continue
        targets.append(RepairTarget(line,lo+kana[3],lo+suru[4],lo,hi,
            marks,True,line[lo+suru[4]:hi],'lexical'))
    return targets




def _marked_case_auxiliary_mark_shift_targets(line, lo, hi, parts, odd):
    """Scope a marked case/auxiliary seam through its real verb stem."""
    if not odd or any(len(part)<7 for part in parts):
        return []
    from morphology import dictionary_inflections
    targets=[]
    for i in range(1,len(parts)-4):
        noun,case,particle,aux,verb,following=parts[i-1:i+5]
        if (not noun[5] or not noun[1].startswith('名詞')
                or noun[4]!=case[3] or case[0]!='を'
                or not case[1].startswith('助詞:格助詞')
                or case[4]!=particle[3] or particle[0]!='か'
                or not particle[1].startswith('助詞:')
                or particle[4]!=aux[3] or aux[0]!='だ'
                or not aux[1].startswith('助動詞')
                or aux[4]!=verb[3] or not verb[5]
                or not verb[1].startswith('動詞:自立')
                or verb[6]!='連用形' or verb[4]!=following[3]
                or following[0]!='ます'
                or not following[1].startswith('助動詞')):
            continue
        marks=tuple((left,right,lo+a,lo+b) for left,right,a,b in odd
                    if a==case[3] and b==particle[4])
        if not marks or verb[4]-particle[3]>12:
            continue
        if not any(pos.startswith('動詞,自立,') and form==verb[6]
                   and reading==verb[2]
                   for pos,form,base,reading in dictionary_inflections(verb[0]) or ()):
            continue
        source_reading=particle[2]+aux[2]+verb[2]
        if not any(row.operation=='transposition' and '゛' in row.pressed
                   for row in key_repairs(source_reading)):
            continue
        targets.append(RepairTarget(line,lo+particle[3],lo+verb[4],lo,hi,
            marks,True,line[lo+verb[4]:hi],'lexical'))
    return targets



def _marked_imperative_connective_targets(line, lo, hi, parts, grammar_spans):
    """A source-marked imperative plus て may contain an adjacent extra key."""
    if not grammar_spans:
        return []
    from morphology import dictionary_inflections
    from kana_layout import single_key_drop_adjacency
    targets=[]
    for verb, connective in zip(parts, parts[1:]):
        if (len(verb)<7 or len(connective)<7 or not verb[5]
                or not verb[1].startswith('動詞:自立')
                or not verb[6].startswith('命令')
                or not verb[0].endswith('ろ') or not verb[2].endswith('ろ')
                or connective[0]!='て' or connective[2]!='て'
                or not connective[1].startswith('助詞:接続助詞')
                or verb[4]!=connective[3]):
            continue
        marks=tuple(('品詞文法','原文の命令形と接続助詞',lo+verb[3],lo+connective[4])
                    for a,b in grammar_spans
                    if a<=verb[3] and connective[4]<=b)
        if not marks:
            continue
        imperative=tuple((pos,base) for pos,form,base,reading
                         in dictionary_inflections(verb[0]) or ()
                         if pos.startswith('動詞,自立,') and form==verb[6]
                         and reading==verb[2])
        continuative=tuple((pos,base) for pos,form,base,reading
                           in dictionary_inflections(verb[0][:-1]) or ()
                           if pos.startswith('動詞,自立,') and form=='連用形'
                           and reading==verb[2][:-1])
        if not set(imperative).intersection(continuative):
            continue
        original=verb[2]+connective[2]
        repaired=verb[2][:-1]+connective[2]
        if single_key_drop_adjacency(original,repaired) is not True:
            continue
        targets.append(RepairTarget(line,lo+verb[3],lo+connective[4],lo,hi,
            marks,True,line[lo+connective[4]:hi],'lexical'))
    return targets




def _marked_nonfinite_connective_intrusion_targets(line, lo, hi, parts, grammar_spans):
    """Keep a real て-stem when a marked kana tail hides its connective."""
    if not grammar_spans:
        return []
    from morphology import dictionary_inflections
    from kana_layout import single_key_drop_adjacency
    targets=[]
    for verb, tail in zip(parts, parts[1:]):
        if (len(verb)<7 or len(tail)<7 or not verb[5]
                or not verb[1].startswith('動詞:自立')
                or verb[6]!='連用タ接続'
                or not tail[5] or tail[4]!=verb[4]+len(tail[0])
                or verb[4]!=tail[3]
                or len(tail[0])!=2 or tail[0]!=tail[2]
                or not all('ぁ'<=c<='ゖ' for c in tail[0])
                or tail[0][1]!='て'
                or tail[1].startswith('助詞:接続助詞')):
            continue
        marks=tuple(('品詞文法','原文の動詞と未説明の接続',lo+verb[3],lo+tail[4])
                    for a,b in grammar_spans
                    if a<=verb[3] and tail[4]<=b)
        if not marks:
            continue
        if not any(pos.startswith('動詞,自立,') and form==verb[6]
                   and reading==verb[2]
                   for pos,form,base,reading in dictionary_inflections(verb[0]) or ()):
            continue
        original=verb[2]+tail[2]
        repaired=verb[2]+tail[2][1:]
        if single_key_drop_adjacency(original,repaired) is not True:
            continue
        targets.append(RepairTarget(line,lo+verb[3],lo+tail[4],lo,hi,
            marks,True,line[lo+tail[4]:hi],'lexical'))
    return targets




def _marked_ime_prefix_native_verb_targets(line, parts, inverse_marks):
    """Repair a source-proved extra IME word before a native verb + te/de."""
    if not inverse_marks:
        return []
    from ime_inverse_gate import exact_context_reading
    from kana_layout import single_key_drop_adjacency
    from literal_examples import protected_ranges,overlaps
    from morphology import tokenize as native_tokenize,dictionary_inflections
    protected=protected_ranges(line)
    targets=[]
    for part in parts:
        surface,pos,reading,start,part_end=part[:5]
        if (len(part)<7 or part[5] or not pos.startswith('名詞:一般')
                or len(surface)<2 or not all('一'<=c<='鿿' for c in surface)
                or not any(previous[0]=='を' and previous[1].startswith('助詞:格助詞')
                           and previous[4]==start and previous[5] for previous in parts)):
            continue
        lo,hi=_source_clause_bounds(line,start,part_end)
        clause=line[lo:hi]
        for end in range(part_end+1,min(start+8,hi)+1):
            body=line[start:end]
            if body[-1] not in ('て','で') or overlaps(start,end,protected):
                continue
            if not any(a<=start and end<=b for _,_,a,b in inverse_marks):
                continue
            suffix=body[1:]
            native=native_tokenize(suffix)
            if (len(native)!=2 or native[0].start!=0
                    or native[-1].end!=len(suffix)
                    or native[0].end!=native[1].start
                    or not native[0].has_reading or native[0].pos!='動詞'
                    or native[0].pos_sub!='自立'
                    or native[0].infl_form!='連用形'
                    or not native[1].has_reading or native[1].pos!='助詞'
                    or not native[1].pos_sub.startswith('接続助詞')
                    or native[1].surface not in ('て','で')
                    or not any(pos.startswith('動詞,自立,')
                               and form==native[0].infl_form and rd==native[0].reading
                               for pos,form,base,rd in dictionary_inflections(native[0].surface) or ())
                    or _modern_te_allowed(native[0].surface,native[0].reading,
                                          native[1].surface) is not True):
                continue
            exact=exact_context_reading(clause,start-lo,end-lo)
            if not exact:
                continue
            source_reading,segments=exact
            if (len(segments)<2 or segments[0][:2]!=(0,1)
                    or ''.join(segment[2] for segment in segments[1:])
                       !=native[0].reading+native[1].reading
                    or source_reading!=segments[0][2]+native[0].reading+native[1].reading
                    or single_key_drop_adjacency(
                        source_reading,native[0].reading+native[1].reading) is not True):
                continue
            targets.append(RepairTarget(line,start,end,lo,hi,
                (('IME逆読み','実動詞の前に余分なIME語頭',start,end),),
                True,line[end:hi],'lexical'))
    return targets




def _marked_detached_mark_action_targets(line, parts, source_odd):
    """Keep the original case; scope its marked detached key with the action."""
    if not source_odd:
        return []
    from literal_examples import protected_ranges,overlaps
    from morphology import dictionary_inflections
    protected=protected_ranges(line)
    targets=[]
    for case,mark,particle,verb,aux in zip(parts,parts[1:],parts[2:],parts[3:],parts[4:]):
        if (case[0]!='を' or not case[1].startswith('助詞:格助詞')
                or mark[0] not in ('゛','゜') or not mark[1].startswith('記号')
                or particle[0]!='ん' or not particle[1].startswith('助詞')
                or not verb[5] or not verb[1].startswith('動詞:自立')
                or verb[6]!='連用形' or aux[0]!='ます'
                or not aux[5] or not aux[1].startswith('助動詞')
                or any(a[4]!=b[3] for a,b in
                       ((case,mark),(mark,particle),(particle,verb),(verb,aux)))
                or overlaps(mark[3],verb[4],protected)):
            continue
        marks=tuple(row for row in source_odd if row[2]==case[3]
                    and row[3]==mark[4] and row[0]==case[0] and row[1]==mark[0])
        if not marks:
            continue
        if not any(pos.startswith('動詞,自立,') and form==verb[6]
                   and rd==verb[2]
                   for pos,form,base,rd in dictionary_inflections(verb[0]) or ()):
            continue
        lo,hi=_source_clause_bounds(line,mark[3],verb[4])
        targets.append(RepairTarget(line,mark[3],verb[4],lo,hi,
            marks,True,line[verb[4]:hi],'lexical'))
    return targets




def _marked_suru_pair_targets(line, lo, hi, parts, odd):
    """Keep a marked converted noun seam inside an object + suru action."""
    if not odd:
        return []
    from ime_inverse_gate import exact_context_reading
    from literal_examples import protected_ranges,overlaps
    from morphology import dictionary_inflections,native_suru_form
    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    for case,first,action,suru,link in zip(
            parts,parts[1:],parts[2:],parts[3:],parts[4:]):
        if (case[0]!='を' or not case[1].startswith('助詞:格助詞')
                or not first[5] or not first[1].startswith('名詞:一般')
                or not action[5] or not action[1].startswith('名詞:サ変接続')
                or suru[0]!='し' or not suru[5]
                or not suru[1].startswith('動詞:自立')
                or suru[6]!='連用形'
                or link[0] not in ('て','で') or not link[5]
                or not link[1].startswith('助詞:接続助詞')
                or any(a[4]!=b[3] for a,b in
                       ((case,first),(first,action),(action,suru),(suru,link)))
                or overlaps(lo+first[3],lo+action[4],protected)):
            continue
        marks=tuple((left,right,lo+a,lo+b) for left,right,a,b in odd
                    if a==first[3] and b==action[4])
        if not marks:
            continue
        if not (any(pos.startswith('名詞,一般,') and rd==first[2]
                    for pos,form,base,rd in dictionary_inflections(first[0]) or ())
                and any(pos.startswith('名詞,サ変接続,') and rd==action[2]
                        for pos,form,base,rd in dictionary_inflections(action[0]) or ())
                and native_suru_form(suru[0],suru[6],suru[2],False)):
            continue
        if not exact_context_reading(clause,first[3],action[4]):
            continue
        targets.append(RepairTarget(line,lo+first[3],lo+action[4],lo,hi,
            marks,True,line[lo+action[4]:hi],'lexical'))
    return targets




def _marked_suru_extra_noun_targets(line, lo, hi, parts, odd):
    """Include native し when a marked one-key noun splits a suru action."""
    if not odd:
        return []
    from kana_layout import single_key_drop_adjacency
    from literal_examples import protected_ranges,overlaps
    from morphology import dictionary_inflections,native_suru_form

    protected=protected_ranges(line)
    targets=[]
    for case,action,extra,suru,link in zip(
            parts,parts[1:],parts[2:],parts[3:],parts[4:]):
        if (case[0]!='を' or not case[1].startswith('助詞:格助詞')
                or not action[5] or not action[1].startswith('名詞:サ変接続')
                or len(action[0])<2
                or not extra[5] or not extra[1].startswith('名詞:一般')
                or len(extra[0])!=1 or len(extra[2])!=1
                or suru[0]!='し' or not suru[5]
                or not suru[1].startswith('動詞:自立') or suru[6]!='連用形'
                or link[0] not in ('て','で') or not link[5]
                or not link[1].startswith('助詞:接続助詞')
                or any(a[4]!=b[3] for a,b in
                       ((case,action),(action,extra),(extra,suru),(suru,link)))
                or overlaps(lo+action[3],lo+suru[4],protected)):
            continue
        marks=tuple((left,right,lo+a,lo+b) for left,right,a,b in odd
                    if a==extra[3] and b==suru[4])
        if not marks:
            continue
        if not (any(pos.startswith('名詞,サ変接続,') and rd==action[2]
                    for pos,form,base,rd in dictionary_inflections(action[0]) or ())
                and any(pos.startswith('名詞,一般,') and rd==extra[2]
                        for pos,form,base,rd in dictionary_inflections(extra[0]) or ())
                and native_suru_form(suru[0],suru[6],suru[2],False)):
            continue
        if single_key_drop_adjacency(
                action[2]+extra[2]+suru[2],action[2]+suru[2]) is not True:
            continue
        targets.append(RepairTarget(line,lo+action[3],lo+suru[4],lo,hi,
            marks,True,line[lo+suru[4]:hi],'lexical'))
    return targets




def _marked_leading_mark_noun_targets(line, parts, source_odd):
    """Use a source first-conversion reading for a marked initial key."""
    if not source_odd:
        return []
    from ime_native_reading import source_roundtrips
    from literal_examples import protected_ranges,overlaps
    protected=protected_ranges(line)
    targets=[]
    for mark,particle,noun in zip(parts,parts[1:],parts[2:]):
        if (mark[0] not in ('゛','゜') or not mark[1].startswith('記号')
                or particle[0]!='ん' or not particle[1].startswith('助詞')
                or not noun[5] or not noun[1].startswith('名詞')
                or mark[4]!=particle[3] or particle[4]!=noun[3]
                or overlaps(mark[3],noun[4],protected)):
            continue
        lo,hi=_source_clause_bounds(line,mark[3],noun[4])
        if mark[3]!=lo:
            continue
        marks=tuple(row for row in source_odd
                    if row[0]==particle[0] and row[1]==noun[0]
                    and row[2]==particle[3] and row[3]==noun[4])
        if not marks:
            continue
        text=line[mark[3]:noun[4]]
        local=[(t[0],t[1],t[2],t[3]-mark[3],t[4]-mark[3],*t[5:])
               for t in (mark,particle,noun)]
        if not source_roundtrips(text,local):
            continue
        targets.append(RepairTarget(line,mark[3],noun[4],lo,hi,
            marks,True,line[noun[4]:hi],'lexical'))
    return targets




def _marked_basic_verb_suru_targets(line, lo, hi, parts, odd):
    """Scope an anomalous basic verb before an attested polite し tail."""
    if not odd:
        return []
    from ime_inverse_gate import exact_context_reading
    from kana_layout import single_key_drop_adjacency
    from literal_examples import protected_ranges,overlaps
    from morphology import dictionary_inflections,native_suru_form
    from semantic_roles import nominal_roles

    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    for obj,objcase,recipient,recase,verb,suru,aux,past in zip(
            parts,parts[1:],parts[2:],parts[3:],
            parts[4:],parts[5:],parts[6:],parts[7:]):
        if (not obj[5] or not obj[1].startswith('名詞')
                or not ({'text','object'} & nominal_roles(obj[0]))
                or objcase[0]!='を' or not objcase[1].startswith('助詞:格助詞')
                or not recipient[5] or not recipient[1].startswith('名詞')
                or 'person' not in nominal_roles(recipient[0])
                or recase[0]!='に' or not recase[1].startswith('助詞:格助詞')
                or not verb[5] or not verb[1].startswith('動詞:自立')
                or verb[6]!='基本形' or len(verb[2])<2
                or not any('一'<=c<='鿿' for c in verb[0])
                or suru[0]!='し' or not suru[5]
                or not suru[1].startswith('動詞:自立') or suru[6]!='連用形'
                or aux[0]!='まし' or not aux[5]
                or not aux[1].startswith('助動詞') or aux[6]!='連用形'
                or past[0]!='た' or not past[5]
                or not past[1].startswith('助動詞')
                or any(a[4]!=b[3] for a,b in
                       ((obj,objcase),(objcase,recipient),(recipient,recase),
                        (recase,verb),(verb,suru),(suru,aux),(aux,past)))
                or overlaps(lo+verb[3],lo+suru[4],protected)):
            continue
        marks=tuple((left,right,lo+a,lo+b) for left,right,a,b in odd
                    if a==verb[3] and b==suru[4])
        if not marks:
            continue
        if not (any(pos.startswith('動詞,自立,') and form=='基本形'
                    and rd==verb[2]
                    for pos,form,base,rd in dictionary_inflections(verb[0]) or ())
                and native_suru_form(suru[0],suru[6],suru[2],False)):
            continue
        exact=exact_context_reading(clause,verb[3],suru[4])
        if not exact:
            continue
        reading,segments=exact
        shorter=verb[2][:-1]+suru[2]
        if (reading!=verb[2]+suru[2] or len(segments)<2
                or single_key_drop_adjacency(reading,shorter) is not True):
            continue
        targets.append(RepairTarget(line,lo+verb[3],lo+suru[4],lo,hi,
            marks,True,line[lo+suru[4]:hi],'marked_written_verb'))
    return targets




def _marked_attributive_verb_noun_object_targets(line, lo, hi, parts, odd):
    """Scope a marked converted verb/noun object before a native action."""
    if not odd:
        return []
    from ime_inverse_gate import exact_context_reading
    from literal_examples import protected_ranges,overlaps
    from morphology import dictionary_inflections

    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    for first,noun,case,action,link in zip(
            parts,parts[1:],parts[2:],parts[3:],parts[4:]):
        if (not first[5] or not first[1].startswith('動詞:自立')
                or first[6] not in ('体言接続特殊２','連用形') or len(first[0])!=1
                or not noun[5] or not noun[1].startswith('名詞:一般')
                or len(noun[0])!=1
                or case[0]!='を' or not case[1].startswith('助詞:格助詞')
                or not action[5] or not action[1].startswith('動詞:自立')
                or action[6]!='連用タ接続'
                or link[0] not in ('て','で') or not link[5]
                or not link[1].startswith('助詞:接続助詞')
                or any(a[4]!=b[3] for a,b in
                       ((first,noun),(noun,case),(case,action),(action,link)))
                or overlaps(lo+first[3],lo+noun[4],protected)):
            continue
        marks=tuple((left,right,lo+a,lo+b) for left,right,a,b in odd
                    if a==first[3] and b==noun[4])
        if not marks:
            continue
        if not (any(pos.startswith('動詞,自立,') and form==first[6]
                    and rd==first[2]
                    for pos,form,base,rd in dictionary_inflections(first[0]) or ())
                and any(pos.startswith('名詞,一般,') and rd==noun[2]
                        for pos,form,base,rd in dictionary_inflections(noun[0]) or ())):
            continue
        exact=exact_context_reading(clause,first[3],noun[4])
        if not exact:
            continue
        reading,segments=exact
        if (reading!=first[2]+noun[2] or len(segments)!=2
                or segments[0][:3]!=(0,1,first[2])
                or segments[1][:3]!=(1,2,noun[2])):
            continue
        targets.append(RepairTarget(line,lo+first[3],lo+noun[4],lo,hi,
            marks,True,line[lo+noun[4]:hi],'lexical',object_slot=True))
    return targets




def _marked_kana_past_action_after_object_targets(line,lo,hi,parts,grammar_spans):
    """Scope a broken kana action and its native written past tail."""
    if not grammar_spans:
        return []
    from morphology import dictionary_inflections
    from literal_examples import protected_ranges,overlaps

    protected=protected_ranges(line)
    targets=[]
    for i in range(len(parts)-5):
        head,case=parts[i:i+2]
        if (not head[5] or not head[1].startswith('名詞')
                or case[0]!='を' or not case[5]
                or not case[1].startswith('助詞:格助詞')
                or head[4]!=case[3]):
            continue
        for width in range(2,5):
            if i+width+3>=len(parts):
                continue
            kana=parts[i+2:i+2+width]
            verb,past=parts[i+2+width:i+4+width]
            if (not kana[0][1].startswith('名詞:非自立')
                    or not kana[-1][1].startswith('助詞:終助詞')
                    or not all(t[5] and _is_input_reading(_input_kana(t[0])) for t in kana)
                    or not verb[5] or not verb[1].startswith('動詞:自立')
                    or len(verb)<7 or verb[6]!='連用形' or not any('一'<=c<='鿿' for c in verb[0])
                    or not past[5] or past[0]!='た'
                    or not past[1].startswith('助動詞')
                    or any(a[4]!=b[3] for a,b in zip((case,)+tuple(kana)+(verb,),
                                                       tuple(kana)+(verb,past)))
                    or past[4]-kana[0][3]>8
                    or overlaps(lo+kana[0][3],lo+past[4],protected)):
                continue
            if not any(pos.startswith('動詞,自立,') and form==verb[6]
                       and reading==verb[2]
                       for pos,form,base,reading in dictionary_inflections(verb[0]) or ()):
                continue
            marks=tuple(('品詞文法','元のかな動作と過去形',lo+a,lo+b)
                        for a,b in grammar_spans
                        if a<=case[3] and b>=kana[-1][4])
            if not marks:
                continue
            targets.append(RepairTarget(line,lo+kana[0][3],lo+past[4],lo,hi,
                marks,True,line[lo+past[4]:hi],'lexical'))
    return targets



def _marked_terminal_ime_tail_targets(line,lo,hi,parts,odd):
    """Test a one-key terminal noun after an already complete polite verb."""
    if not odd:
        return []
    from ime_inverse_gate import exact_context_reading
    from kana_layout import single_key_drop_adjacency
    from literal_examples import protected_ranges,overlaps
    from morphology import dictionary_inflections

    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    for verb,aux,tail in zip(parts,parts[1:],parts[2:]):
        if (not verb[5] or not verb[1].startswith('動詞:自立')
                or len(verb)<7 or verb[6]!='連用形'
                or not aux[5] or aux[0]!='ます'
                or not aux[1].startswith('助動詞')
                or not tail[5] or not tail[1].startswith('名詞')
                or len(tail[0])!=1 or tail[4]!=len(clause)
                or verb[4]!=aux[3] or aux[4]!=tail[3]
                or overlaps(lo+verb[3],lo+tail[4],protected)):
            continue
        marks=tuple((left,right,lo+a,lo+b) for left,right,a,b in odd
                    if left=='IME逆読み' and a<=tail[3] and b>=tail[4])
        if not marks:
            continue
        if not any(pos.startswith('動詞,自立,') and form==verb[6]
                   and reading==verb[2]
                   for pos,form,base,reading in dictionary_inflections(verb[0]) or ()):
            continue
        exact=exact_context_reading(clause,tail[3],tail[4])
        if (not exact or len(exact[0])!=1 or exact[0]==tail[2]
                or single_key_drop_adjacency(verb[2]+aux[2]+exact[0],
                                             verb[2]+aux[2]) is not True):
            continue
        targets.append(RepairTarget(line,lo+verb[3],lo+tail[4],lo,hi,
            marks,True,'','lexical'))
    return targets




def _source_nominal_sahen_intrusion_targets(line,lo,hi,parts):
    """Try an unsupported one-key noun before a native sahen action."""
    if 'を' not in line[lo:hi] or ('して' not in line[lo:hi] and 'します' not in line[lo:hi]):
        return []
    from ime_inverse_gate import exact_context_reading,attested_context_reading
    from literal_examples import protected_ranges,overlaps
    from morphology import dictionary_inflections
    from semantic_roles import nominal_compound_support

    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    for i in range(len(parts)-5):
        obj,case,lead,head,suru,te=parts[i:i+6]
        connective=(te[0]=='て' and te[5]
            and te[1].startswith('助詞:接続助詞'))
        polite=(te[0]=='ます' and te[5] and te[1].startswith('助動詞')
            and len(lead[2])==1 and 'ァ'<=lead[0]<='ヿ')
        suffix='します' if polite else 'して'
        if (not obj[5] or not obj[1].startswith('名詞')
                or case[0]!='を' or not case[5]
                or not case[1].startswith('助詞:格助詞')
                or not lead[5] or not lead[1].startswith('名詞')
                or len(lead[0])!=1
                or not head[5] or not head[1].startswith('名詞:サ変接続')
                or suru[0]!='し' or not suru[5]
                or not suru[1].startswith('動詞:自立')
                or suru[6]!='連用形'
                or not (connective or polite)
                or any(a[4]!=b[3] for a,b in
                       ((obj,case),(case,lead),(lead,head),(head,suru),(suru,te)))
                or overlaps(lo+lead[3],lo+te[4],protected)
                or dictionary_inflections(lead[0]+head[0])
                or nominal_compound_support(lead[0],head[0])):
            continue
        exact=(exact_context_reading(clause,lead[3],te[4])
               or attested_context_reading(clause,lead[3],te[4]))
        if (not exact or len(exact[1])<3
                or exact[1][0][:2]!=(0,1)
                or len(exact[1][0][2])!=1
                or exact[1][1][:2]!=(1,1+len(head[0]))
                or exact[1][1][2]!=head[2]
                or not exact[0].endswith(suffix)
                or not any(r.operation=='adjacent_intrusion'
                           and (not polite or (r.reading==head[2]+suffix
                               and r.pressed==lead[2] and r.position==0))
                           for r in key_repairs(exact[0]))):
            continue
        marks=(('品詞文法','元の名詞とサ変動作の接続',
                lo+lead[3],lo+head[4]),)
        targets.append(RepairTarget(line,lo+lead[3],lo+te[4],lo,hi,
            marks,True,line[lo+te[4]:hi],'lexical'))
    return targets



def _marked_nominal_particle_before_kara_targets(line,lo,hi,parts,odd):
    """Resolve a marked noun + compound particle as an action before から."""
    if not odd:
        return []
    from ime_inverse_gate import exact_context_reading
    from literal_examples import protected_ranges,overlaps

    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    for obj,case,noun,link,kara,following in zip(
            parts,parts[1:],parts[2:],parts[3:],parts[4:],parts[5:]):
        if (not obj[5] or not obj[1].startswith('名詞')
                or case[0]!='を' or not case[5]
                or not case[1].startswith('助詞:格助詞')
                or not noun[5] or not noun[1].startswith('名詞')
                or not link[5] or not link[1].startswith('助詞:格助詞:連語')
                or not link[0].startswith('に') or not link[0].endswith('して')
                or kara[0]!='から' or not kara[5]
                or not kara[1].startswith('助詞:格助詞')
                or not following[5]
                or not following[1].startswith(('動詞:自立','名詞:サ変接続'))
                or any(a[4]!=b[3] for a,b in
                       ((obj,case),(case,noun),(noun,link),(link,kara),(kara,following)))
                or overlaps(lo+noun[3],lo+link[4],protected)):
            continue
        marks=tuple((left,right,lo+a,lo+b) for left,right,a,b in odd
                    if a<=link[3] and b>=kara[4])
        if not marks:
            continue
        exact=exact_context_reading(clause,noun[3],link[4])
        if (not exact or not exact[0].startswith(noun[2])
                or not exact[0].endswith('して')
                or not exact[1] or exact[1][0][:2]!=(0,len(noun[0]))
                or not any(r.operation=='adjacent_intrusion'
                           and len(noun[2])<=r.position<len(exact[0])-2
                           and r.reading.endswith('して')
                           for r in key_repairs(exact[0]))):
            continue
        targets.append(RepairTarget(line,lo+noun[3],lo+link[4],lo,hi,
            marks,True,line[lo+link[4]:hi],'lexical'))
    return targets



def _source_sahen_connective_intrusion_targets(line,lo,hi,parts):
    """Use a native sahen action and から to scope one extra IME key."""
    clause=line[lo:hi]
    if 'を' not in clause or 'から' not in clause:
        return []
    from ime_inverse_gate import exact_context_reading
    from literal_examples import protected_ranges,overlaps

    protected=protected_ranges(line)
    targets=[]
    for i in range(len(parts)-2):
        case,head=parts[i:i+2]
        obj=parts[i-1] if i else None
        if (not obj or not obj[5] or not obj[1].startswith('名詞')
                or case[0]!='を' or not case[5]
                or not case[1].startswith('助詞:格助詞')
                or not head[5] or not head[1].startswith('名詞:サ変接続')
                or obj[4]!=case[3] or case[4]!=head[3]):
            continue
        for j in range(i+3,min(i+7,len(parts)-1)):
            kara,following=parts[j:j+2]
            if (kara[0]!='から' or not kara[5]
                    or not kara[1].startswith('助詞:格助詞')
                    or not following[5]
                    or not following[1].startswith(('名詞:サ変接続','動詞:自立'))
                    or kara[4]!=following[3]
                    or any(a[4]!=b[3] for a,b in
                           zip(parts[i+1:j],parts[i+2:j+1]))
                    or 'た' in clause[head[3]:kara[3]]
                    or overlaps(lo+head[3],lo+kara[3],protected)):
                continue
            if 'し' not in clause[head[4]:kara[3]]:
                continue
            exact=exact_context_reading(clause,head[3],kara[3])
            native=head[2]+'して'
            if (not exact or not exact[0].startswith(head[2])
                    or not exact[1] or exact[1][0][:2]!=(0,len(head[0]))
                    or exact[1][0][2]!=head[2]
                    or not any(r.reading==native
                               and r.operation=='adjacent_intrusion'
                               and r.position>=len(head[2])
                               for r in key_repairs(exact[0]))):
                continue
            marks=(('品詞文法','元のサ変動作の接続',
                    lo+head[3],lo+kara[3]),)
            targets.append(RepairTarget(line,lo+head[3],lo+kara[3],
                lo,hi,marks,True,line[lo+kara[3]:hi],'auxiliary_connection'))
    return targets


def _marked_pre_suru_action_targets(line,lo,hi,parts,odd,grammar_spans):
    """Scope a marked source action through real し and a finite polite tail."""
    if not odd and not grammar_spans:
        return []
    from literal_examples import protected_ranges,overlaps
    from ime_inverse_gate import exact_context_reading

    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    for i in range(len(parts)-1):
        obj,case=parts[i:i+2]
        if (not obj[5] or not obj[1].startswith('名詞')
                or case[0]!='を' or not case[5]
                or not case[1].startswith('助詞:格助詞')
                or obj[4]!=case[3]):
            continue
        start=case[4]
        for j in range(i+3,min(i+8,len(parts)-1)):
            suru,aux=parts[j:j+2]
            present=(aux[0]=='ます' and aux[5]
                     and aux[1].startswith('助動詞') and aux[6]=='基本形')
            past=parts[j+2] if j+2<len(parts) else None
            polite_past=(aux[0]=='まし' and aux[5]
                         and aux[1].startswith('助動詞')
                         and past is not None and past[0]=='た' and past[5]
                         and past[1].startswith('助動詞') and aux[4]==past[3])
            tail_end=aux[4] if present else past[4] if polite_past else aux[4]
            inner=parts[i+2:j]
            if (not inner or inner[0][3]!=start
                    or inner[-1][4]!=suru[3]
                    or any(a[4]!=b[3] for a,b in zip(inner,inner[1:]))
                    or suru[0]!='し' or not suru[5]
                    or not suru[1].startswith('動詞:自立') or suru[6]!='連用形'
                    or not (present or polite_past)
                    or suru[4]!=aux[3]
                    or not 3<=suru[4]-start<=8
                    or overlaps(lo+start,lo+suru[4],protected)):
                continue
            # A complete native action reading is positive source evidence.
            # A split kana parse must not reopen an already correct action.
            from reading_segments import completed_sahen_reading
            if completed_sahen_reading(clause[start:tail_end],allow_nonpolite=True):
                continue
            source_ime=tuple((left,right,lo+a,lo+b) for left,right,a,b in odd
                             if left=='IME逆読み' and a<=start and b>=tail_end)
            if not all(t[5] for t in inner):
                exact=exact_context_reading(clause,start,suru[4]) if source_ime else None
                if not exact:
                    continue
            marks=tuple((left,right,lo+a,lo+b) for left,right,a,b in odd
                        if start<=a<b<=suru[4])
            if not all(t[5] for t in inner) and source_ime:
                marks+=(('IME逆読み','元のサ変動作',
                         lo+start,lo+suru[4]),)
            marks+=tuple(('品詞文法','元の動作と助動詞',lo+a,lo+b)
                         for a,b in grammar_spans
                         if start<=a<suru[4] and b>=suru[3])
            if not marks:
                continue
            targets.append(RepairTarget(line,lo+start,lo+suru[4],lo,hi,
                marks,True,line[lo+suru[4]:hi],'lexical'))
    return targets




def _marked_nonindependent_sahen_past_targets(line, lo, hi, parts, grammar_spans):
    """Resolve one source-key intrusion across native し + い + ました."""
    if not grammar_spans:
        return []
    from ime_inverse_gate import exact_context_reading
    from literal_examples import protected_ranges, overlaps

    clause = line[lo:hi]
    protected = protected_ranges(line)
    targets = []
    for i in range(len(parts)-6):
        obj, case, head, suru, extra, aux, past = parts[i:i+7]
        if (not obj[5] or not obj[1].startswith('名詞')
                or case[0] != 'を' or not case[5]
                or not case[1].startswith('助詞:格助詞')
                or not head[5] or not head[1].startswith('名詞:サ変接続')
                or suru[0] != 'し' or not suru[5]
                or not suru[1].startswith('動詞:自立') or suru[6] != '連用形'
                or extra[0] != 'い' or not extra[5]
                or not extra[1].startswith('動詞:非自立')
                or aux[0] != 'まし' or not aux[5]
                or not aux[1].startswith('助動詞')
                or past[0] != 'た' or not past[5]
                or not past[1].startswith('助動詞')
                or any(a[4] != b[3] for a, b in
                       ((obj, case), (case, head), (head, suru),
                        (suru, extra), (extra, aux), (aux, past)))
                or overlaps(lo + head[3], lo + past[4], protected)
                or not any(a <= suru[3] and extra[4] <= b
                           for a, b in grammar_spans)):
            continue
        exact = exact_context_reading(clause, head[3], past[4])
        if not exact or exact[0] != head[2] + 'しいました':
            continue
        corrected = head[2] + 'しました'
        if not any(r.reading == corrected
                   and r.operation == 'adjacent_intrusion'
                   and r.position == len(head[2]) + 1
                   and r.pressed == 'い'
                   for r in key_repairs(exact[0])):
            continue
        marks = (('品詞文法', '元のサ変動作接続',
                  lo + suru[3], lo + extra[4]),)
        targets.append(RepairTarget(line, lo + head[3], lo + past[4],
            lo, hi, marks, True, line[lo + past[4]:hi], 'lexical'))
    return targets


def _marked_terminal_noun_after_polite_past_targets(line,lo,hi,parts,grammar_spans):
    """Remove only a source-key intrusion after a native completed action."""
    if not grammar_spans:
        return []
    from ime_inverse_gate import exact_context_reading
    from literal_examples import protected_ranges, overlaps

    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    for i in range(len(parts)-6):
        obj,case,head,suru,aux,past,extra=parts[i:i+7]
        if (not obj[5] or not obj[1].startswith('名詞')
                or case[0]!='を' or not case[5]
                or not case[1].startswith('助詞:格助詞')
                or not head[5] or not head[1].startswith('名詞:サ変接続')
                or suru[0]!='し' or not suru[5]
                or not suru[1].startswith('動詞:自立') or suru[6]!='連用形'
                or aux[0]!='まし' or not aux[5]
                or not aux[1].startswith('助動詞')
                or past[0]!='た' or not past[5]
                or not past[1].startswith('助動詞')
                or len(extra[0])!=1 or not extra[5]
                or not extra[1].startswith('名詞') or len(extra[2])!=1
                or extra[4]!=len(clause)
                or any(a[4]!=b[3] for a,b in
                       ((obj,case),(case,head),(head,suru),(suru,aux),
                        (aux,past),(past,extra)))
                or overlaps(lo+head[3],lo+extra[4],protected)
                or not any(a<=past[3] and extra[4]<=b for a,b in grammar_spans)):
            continue
        exact=exact_context_reading(clause,head[3],extra[4])
        if not exact or exact[0]!=head[2]+'しました'+extra[2]:
            continue
        corrected=head[2]+'しました'
        if not any(r.reading==corrected
                   and r.operation=='adjacent_intrusion'
                   and r.position==len(corrected)
                   and r.pressed==extra[2]
                   for r in key_repairs(exact[0])):
            continue
        marks=(('品詞文法','丁寧過去の後の遊離名詞',
                lo+past[3],lo+extra[4]),)
        targets.append(RepairTarget(line,lo+head[3],lo+extra[4],lo,hi,
            marks,True,'','lexical'))
    return targets


def _marked_past_before_sahen_targets(line,lo,hi,parts,grammar_spans):
    """Read a marked contracted past through any native finite next action."""
    if not grammar_spans:return []
    from morphology import dictionary_inflections
    from literal_examples import protected_ranges,overlaps
    clause=line[lo:hi];protected=protected_ranges(line);targets=[]
    for i in range(len(parts)-5):
        obj,case,verb,te,past=parts[i:i+5]
        if (not obj[5] or not obj[1].startswith('名詞')
                or case[0]!='を' or not case[5] or not case[1].startswith('助詞:格助詞')
                or not verb[5] or not verb[1].startswith('動詞:自立')
                or verb[6] not in ('連用形','連用タ接続')
                or te[0] not in ('て','で') or not te[5] or not te[1].startswith('動詞:非自立')
                or past[0]!='た' or not past[5] or not past[1].startswith('助動詞')
                or any(a[4]!=b[3] for a,b in ((obj,case),(case,verb),(verb,te),(te,past)))
                or overlaps(lo+verb[3],hi,protected)
                or not any(a<=te[3] and past[4]<=b for a,b in grammar_spans)
                or _modern_te_allowed(verb[0],verb[2],te[0]) is not True
                or not _finite_written_predicate(clause[past[4]:])):continue
        # The original written verb already has an exact native form and
        # reading. A first-choice IME round trip is not a second prerequisite.
        if not any(p.startswith('動詞,自立,') and f==verb[6] and rd==verb[2]
                   for p,f,base,rd in dictionary_inflections(verb[0]) or ()):continue
        reading=verb[2]+te[2]
        if not any(r.reading==reading and r.operation=='adjacent_intrusion'
                   and r.pressed==past[2] for r in key_repairs(reading+past[2])):continue
        marks=(('品詞文法','元の過去形と次の動作の接続',lo+te[3],lo+past[4]),)
        targets.append(RepairTarget(line,lo+verb[3],lo+past[4],lo,hi,
            marks,True,line[lo+past[4]:hi],'lexical'))
    return targets


def _marked_double_native_polite_tail_targets(line,lo,hi,parts,grammar_spans):
    """Read a native まし verb as source keystrokes, then resolve the action."""
    if not grammar_spans:
        return []
    from ime_inverse_gate import exact_context_reading
    from literal_examples import protected_ranges, overlaps

    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    for i in range(len(parts)-6):
        obj,case,head,suru,second,te,past=parts[i:i+7]
        if (not obj[5] or not obj[1].startswith('名詞')
                or case[0]!='を' or not case[5]
                or not case[1].startswith('助詞:格助詞')
                or not head[5] or not head[1].startswith('名詞:サ変接続')
                or suru[0]!='し' or not suru[5]
                or not suru[1].startswith('動詞:自立') or suru[6]!='連用形'
                or not second[5] or second[2]!='まし'
                or not second[1].startswith('動詞:自立') or second[6]!='連用形'
                or te[0]!='て' or not te[5]
                or not te[1].startswith('動詞:非自立')
                or past[0]!='た' or not past[5]
                or not past[1].startswith('助動詞')
                or any(a[4]!=b[3] for a,b in
                       ((obj,case),(case,head),(head,suru),(suru,second),
                        (second,te),(te,past)))
                or overlaps(lo+head[3],lo+past[4],protected)
                or not any(a<=suru[3] and te[4]<=b for a,b in grammar_spans)):
            continue
        exact=exact_context_reading(clause,head[3],past[4])
        if not exact or exact[0]!=head[2]+'し'+second[2]+'てた':
            continue
        corrected=head[2]+'しました'
        if not any(r.reading==corrected
                   and r.operation=='adjacent_intrusion'
                   and r.pressed=='て'
                   for r in key_repairs(exact[0])):
            continue
        marks=(('品詞文法','原文の二重動詞と語尾',
                lo+suru[3],lo+te[4]),)
        targets.append(RepairTarget(line,lo+head[3],lo+past[4],lo,hi,
            marks,True,line[lo+past[4]:hi],'lexical'))
    return targets


def _marked_terminal_polite_connective_targets(line,lo,hi,parts,grammar_spans):
    """Resolve a native polite connective only at a full-stop boundary."""
    if not grammar_spans or not line.endswith('しまして。'):
        return []
    from ime_inverse_gate import exact_context_reading
    from literal_examples import protected_ranges, overlaps

    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    for i in range(len(parts)-5):
        obj,case,head,suru,aux,te=parts[i:i+6]
        if (not obj[5] or not obj[1].startswith('名詞')
                or case[0]!='を' or not case[5]
                or not case[1].startswith('助詞:格助詞')
                or not head[5] or not head[1].startswith('名詞:サ変接続')
                or suru[0]!='し' or not suru[5]
                or not suru[1].startswith('動詞:自立') or suru[6]!='連用形'
                or aux[0]!='まし' or not aux[5]
                or not aux[1].startswith('助動詞')
                or te[0]!='て' or not te[5]
                or not te[1].startswith('助詞:接続助詞')
                or te[4]!=len(clause)
                or any(a[4]!=b[3] for a,b in
                       ((obj,case),(case,head),(head,suru),
                        (suru,aux),(aux,te)))
                or overlaps(lo+head[3],lo+te[4],protected)
                or not any(a<=aux[3] and te[4]<=b for a,b in grammar_spans)):
            continue
        exact=exact_context_reading(clause,head[3],te[4])
        if not exact or exact[0]!=head[2]+'しまして':
            continue
        corrected=head[2]+'しました'
        if not any(r.reading==corrected
                   and r.operation=='adjacent_substitution'
                   and r.pressed=='て' and r.intended=='た'
                   for r in key_repairs(exact[0])):
            continue
        marks=(('品詞文法','文末の丁寧な接続助詞',
                lo+aux[3],lo+te[4]),)
        targets.append(RepairTarget(line,lo+head[3],lo+te[4],lo,hi,
            marks,True,'','lexical'))
    return targets


def _source_one_key_before_adverbial_targets(line,lo,hi,parts,grammar_spans):
    """Give a source-proven extra noun to the ordinary adjective resolver."""
    if not grammar_spans:
        return []
    from morphology import dictionary_inflections
    from ime_inverse_gate import exact_context_reading
    from literal_examples import protected_ranges, overlaps

    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    for i in range(len(parts)-4):
        obj,case,extra,adverb,action=parts[i:i+5]
        if (not obj[5] or not obj[1].startswith('名詞')
                or case[0]!='を' or not case[5]
                or not case[1].startswith('助詞:格助詞')
                or not extra[5] or not extra[1].startswith('名詞:一般')
                or len(extra[0])!=1 or len(extra[2])!=1
                or not adverb[5] or not adverb[1].startswith('形容詞:自立')
                or not adverb[6].startswith('連用')
                or not action[5] or not action[1].startswith(('動詞:自立','名詞:サ変接続'))
                or any(a[4]!=b[3] for a,b in ((obj,case),(case,extra),
                       (extra,adverb),(adverb,action)))
                or dictionary_inflections(extra[0]+adverb[0])
                or overlaps(lo+extra[3],lo+adverb[4],protected)
                or not any(a<=extra[3] and extra[4]<=b for a,b in grammar_spans)):
            continue
        exact=exact_context_reading(clause,extra[3],adverb[4])
        if (not exact or exact[0]!=extra[2]+adverb[2]
                or not any(r.reading==adverb[2] and r.operation=='adjacent_intrusion'
                           and r.pressed==extra[2] for r in key_repairs(exact[0]))):
            continue
        marks=(('品詞文法','実副詞の前の一打',lo+extra[3],lo+extra[4]),)
        targets.append(RepairTarget(line,lo+extra[3],lo+adverb[4],lo,hi,
            marks,True,line[lo+adverb[4]:hi],'lexical'))
    return targets


def _source_adnominal_particle_targets(line,lo,hi,parts,grammar_spans,store):
    """Remove a proved extra は while retaining native modifier and noun."""
    if not grammar_spans:
        return []
    from corrector import make_tokenizer
    from ime_inverse_gate import exact_context_reading
    from literal_examples import protected_ranges, overlaps

    clause=line[lo:hi]
    protected=protected_ranges(line)
    tokenize=make_tokenizer(store)
    targets=[]
    for i in range(len(parts)-5):
        left,link,extra,noun,case,action=parts[i:i+6]
        genitive=(left[5] and left[1].startswith('名詞') and link[0]=='の'
                  and link[5] and link[1].startswith(('名詞:非自立','助詞:連体化')))
        adnominal=(left[5] and left[1].startswith('名詞:形容動詞語幹')
                   and link[0]=='な' and link[5]
                   and link[1].startswith('助動詞') and link[6]=='体言接続')
        if (not (genitive or adnominal)
                or extra[0]!='は' or not extra[5]
                or not extra[1].startswith('助詞:係助詞')
                or not noun[5] or not noun[1].startswith('名詞')
                or case[0]!='を' or not case[5]
                or not case[1].startswith('助詞:格助詞')
                or not action[5] or not action[1].startswith(('動詞:自立','名詞:サ変接続'))
                or any(a[4]!=b[3] for a,b in ((left,link),(link,extra),
                       (extra,noun),(noun,case),(case,action)))
                or overlaps(lo+link[3],lo+noun[4],protected)
                or not any(a<=extra[3] and extra[4]<=b for a,b in grammar_spans)):
            continue
        exact=exact_context_reading(clause,link[3],noun[4])
        intended=link[2]+noun[2]
        if (not exact or exact[0]!=link[2]+'は'+noun[2]
                or not any(r.reading==intended and r.operation=='adjacent_intrusion'
                           and r.pressed=='は' for r in key_repairs(exact[0]))):
            continue
        trial=clause[:extra[3]]+clause[extra[4]:]
        trial_parts=list(tokenize(trial))
        matched=False
        for j in range(len(trial_parts)-3):
            a,b,c,d=trial_parts[j:j+4]
            if (a[3]==left[3] and a[0]==left[0]
                    and b[0]==link[0] and c[0]==noun[0] and d[0]=='を'
                    and all(x[4]==y[3] for x,y in ((a,b),(b,c),(c,d)))
                    and (b[1].startswith('助詞:連体化') if genitive
                         else b[1].startswith('助動詞') and b[6]=='体言接続')
                    and c[1].startswith('名詞') and d[1].startswith('助詞:格助詞')):
                matched=True
                break
        if not matched:continue
        marks=(('品詞文法','連体形と名詞の間の遊離は',lo+extra[3],lo+extra[4]),)
        targets.append(RepairTarget(line,lo+link[3],lo+noun[4],lo,hi,
            marks,True,line[lo+noun[4]:hi],'source_adnominal_intrusion',
            candidate_surface=link[0]+noun[0],candidate_reading=intended))
    return targets


def _source_destination_connective_targets(line,lo,hi,parts,grammar_spans):
    """Use original verb reading and destination syntax to repair と to て."""
    if not grammar_spans:
        return []
    from morphology import dictionary_inflections
    from semantic_roles import nominal_roles
    from ime_inverse_gate import exact_context_reading
    from literal_examples import protected_ranges, overlaps

    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    for i in range(len(parts)-7):
        obj,case,head,link,destination,destcase,action,aux=parts[i:i+8]
        if (not obj[5] or not obj[1].startswith('名詞')
                or case[0]!='を' or not case[5]
                or not case[1].startswith('助詞:格助詞')
                or not head[5] or not head[1].startswith(('名詞:一般','動詞:自立'))
                or link[0]!='と' or not link[5]
                or not link[1].startswith(('助詞:並立助詞','助詞:格助詞:引用'))
                or not destination[5] or not destination[1].startswith('名詞')
                or 'place' not in nominal_roles(destination[0])
                or destcase[0]!='へ' or not destcase[5]
                or not destcase[1].startswith('助詞:格助詞')
                or not action[5] or not action[1].startswith('動詞:自立')
                or action[6]!='連用形'
                or aux[0]!='ます' or not aux[5]
                or not aux[1].startswith('助動詞')
                or any(a[4]!=b[3] for a,b in ((obj,case),(case,head),(head,link),
                       (link,destination),(destination,destcase),(destcase,action),(action,aux)))
                or not any(p.startswith('動詞,自立,') and f=='連用形' and rd==head[2]
                           for p,f,b,rd in dictionary_inflections(head[0]) or ())
                or overlaps(lo+head[3],lo+aux[4],protected)
                or not any(a<=link[3] and link[4]<=b for a,b in grammar_spans)):
            continue
        exact=exact_context_reading(clause,head[3],link[4])
        intended=head[2]+'て'
        if (not exact or exact[0]!=head[2]+'と'
                or not any(r.reading==intended and r.operation=='adjacent_substitution'
                           and r.pressed=='と' and r.intended=='て'
                           for r in key_repairs(exact[0]))):
            continue
        candidate=head[0]+'て'
        marks=(('品詞文法','目的地動作前の接続助詞',lo+link[3],lo+link[4]),)
        targets.append(RepairTarget(line,lo+head[3],lo+link[4],lo,hi,
            marks,True,line[lo+link[4]:hi],'source_destination_connective',
            candidate_surface=candidate,candidate_reading=intended))
    return targets


def _source_one_key_object_tail_targets(line,lo,hi,parts,grammar_spans):
    """Resolve an unsupported one-key suffix on the original object noun."""
    if not grammar_spans:
        return []
    from morphology import dictionary_inflections
    from semantic_roles import nominal_roles, nominal_compound_support
    from ime_inverse_gate import exact_context_reading
    from literal_examples import protected_ranges, overlaps

    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    for i in range(len(parts)-3):
        head,tail,case,action=parts[i:i+4]
        if (not head[5] or not head[1].startswith('名詞:一般')
                or not nominal_roles(head[0])
                or not tail[5] or not tail[1].startswith('名詞:接尾')
                or len(tail[0])!=1
                or tail[1].startswith('名詞:接尾:サ変接続')
                or case[0]!='を' or not case[5]
                or not case[1].startswith('助詞:格助詞')
                or not (action[5] and action[1].startswith(('動詞:自立','名詞:サ変接続'))
                        or (action[5] and action[1].startswith('名詞')
                            and nominal_roles(action[0]) & {'container','place'}
                            and i+5<len(parts) and parts[i+4][5]
                            and parts[i+4][0] in ('に','へ')
                            and parts[i+4][1].startswith('助詞:格助詞')
                            and parts[i+5][5]
                            and parts[i+5][1].startswith('動詞:自立')
                            and action[4]==parts[i+4][3]
                            and parts[i+4][4]==parts[i+5][3]))
                or any(a[4]!=b[3] for a,b in ((head,tail),(tail,case),(case,action)))
                or dictionary_inflections(head[0]+tail[0])
                or nominal_compound_support(head[0],tail[0])
                or overlaps(lo+head[3],lo+tail[4],protected)
                or not any(a<=tail[3] and tail[4]<=b for a,b in grammar_spans)):
            continue
        exact=exact_context_reading(clause,head[3],tail[4])
        if (not exact or len(exact[1])!=2
                or exact[1][0][:2]!=(0,len(head[0]))
                or exact[1][0][2]!=head[2]
                or exact[1][1][:2]!=(len(head[0]),len(head[0])+len(tail[0]))
                or len(exact[1][1][2])!=1
                or exact[0]!=head[2]+exact[1][1][2]
                or not any(r.reading==head[2]
                           and r.operation=='adjacent_intrusion'
                           and r.pressed==exact[1][1][2]
                           for r in key_repairs(exact[0]))):
            continue
        marks=(('品詞文法','元の名詞句末尾の一打',lo+tail[3],lo+tail[4]),)
        targets.append(RepairTarget(line,lo+head[3],lo+tail[4],lo,hi,
            marks,True,line[lo+tail[4]:hi],'lexical'))
    return targets


def _marked_single_key_between_sahen_actions_targets(line,lo,hi,parts,grammar_spans):
    """Read an extra source key after して before another finite action."""
    if not grammar_spans:
        return []
    from ime_inverse_gate import exact_context_reading
    from literal_examples import protected_ranges, overlaps
    from kana_layout import intrusion_key_distance

    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    for i in range(len(parts)-8):
        obj,case,head,suru,te,extra,nexthead,nextsuru,aux=parts[i:i+9]
        if (not obj[5] or not obj[1].startswith('名詞')
                or case[0]!='を' or not case[5]
                or not case[1].startswith('助詞:格助詞')
                or not head[5] or not head[1].startswith('名詞:サ変接続')
                or suru[0]!='し' or not suru[5]
                or not suru[1].startswith('動詞:自立') or suru[6]!='連用形'
                or te[0]!='て' or not te[5]
                or not te[1].startswith('助詞:接続助詞')
                or not extra[5] or len(extra[0])!=1
                or not ((extra[0]=='と' and extra[1].startswith('助詞:格助詞:引用'))
                        or (len(extra[2])==1 and nexthead[2]
                            and (extra[1].startswith('助詞:副助詞')
                                 or extra[1].startswith('動詞:非自立') and extra[6]=='基本形')
                            and intrusion_key_distance(extra[2],nexthead[2][0])<=1.0))
                or not nexthead[5] or not nexthead[1].startswith('名詞:サ変接続')
                or nextsuru[0]!='し' or not nextsuru[5]
                or not nextsuru[1].startswith('動詞:自立')
                or aux[0]!='ます' or not aux[5]
                or not aux[1].startswith('助動詞')
                or any(a[4]!=b[3] for a,b in
                       ((obj,case),(case,head),(head,suru),(suru,te),
                        (te,extra),(extra,nexthead),(nexthead,nextsuru),(nextsuru,aux)))
                or overlaps(lo+head[3],lo+nextsuru[4],protected)
                or not any(a<=te[3] and extra[4]<=b for a,b in grammar_spans)):
            continue
        exact=exact_context_reading(clause,head[3],extra[4])
        if not exact or exact[0]!=head[2]+'して'+extra[2]:
            continue
        corrected=head[2]+'して'
        if not any(r.reading==corrected
                   and r.operation=='adjacent_intrusion'
                   and r.pressed==extra[2]
                   for r in key_repairs(exact[0],after=nexthead[2])):
            continue
        marks=(('品詞文法','次の動作前の遊離一打',
                lo+te[3],lo+extra[4]),)
        targets.append(RepairTarget(line,lo+head[3],lo+extra[4],lo,hi,
            marks,True,line[lo+extra[4]:hi],'source_sahen_action_bridge',
            candidate_surface=head[0]+'して',candidate_reading=corrected))
    if 'てし' in clause or 'んし' in clause or 'かし' in clause:
        from pos_grammar import _orphaned_particle_before_sahen_action_windows
        for head,extra,aux in _orphaned_particle_before_sahen_action_windows(parts,clause):
            if (overlaps(lo+head[3],lo+aux[4],protected)
                    or not any(a<=extra[3] and extra[4]<=b for a,b in grammar_spans)):
                continue
            exact=exact_context_reading(clause,head[3],aux[4])
            suffix='し'+aux[2]
            if (not exact or exact[0]!=head[2]+extra[2]+suffix
                    or not any(r.reading==head[2]+suffix
                               and r.operation=='adjacent_intrusion'
                               and r.pressed==extra[2]
                               for r in key_repairs(exact[0]))):
                continue
            marks=(('品詞文法','実サ変動作前の遊離助詞',lo+extra[3],lo+extra[4]),)
            targets.append(RepairTarget(line,lo+head[3],lo+aux[4],lo,hi,
                marks,True,line[lo+aux[4]:hi],'auxiliary_connection'))
    return targets


def _marked_stray_key_before_next_object_targets(line,lo,hi,parts,grammar_spans):
    """Read an orphaned source key after て before another action."""
    if not grammar_spans:
        return []
    from ime_inverse_gate import exact_context_reading
    from literal_examples import protected_ranges, overlaps

    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    for i in range(len(parts)-8):
        obj,case,verb,te,extra,nextnoun,nextcase,nextverb,aux=parts[i:i+9]
        after=parts[i+9] if i+9<len(parts) else None
        simple_action=(nextverb[5] and nextverb[1].startswith('動詞:自立')
            and nextverb[6]=='連用形' and aux[0]=='ます' and aux[5]
            and aux[1].startswith('助動詞'))
        sahen_action=(nextcase[0]=='を' and nextverb[5]
            and nextverb[1].startswith('名詞:サ変接続')
            and aux[0]=='し' and aux[5]
            and aux[1].startswith('動詞:自立') and aux[6]=='連用形'
            and after is not None and after[0]=='ます' and after[5]
            and after[1].startswith('助動詞'))
        last=after if sahen_action else aux
        if (not obj[5] or not obj[1].startswith('名詞')
                or case[0]!='を' or not case[5]
                or not case[1].startswith('助詞:格助詞')
                or not verb[5] or not verb[1].startswith('動詞:自立')
                or verb[6] not in ('連用形','連用タ接続')
                or te[0]!='て' or not te[5]
                or not te[1].startswith('助詞:接続助詞')
                or not extra[5]
                or not ((extra[0]=='と' and extra[1].startswith('助詞:格助詞:引用'))
                        or (extra[0]=='い' and extra[1].startswith('動詞:非自立')
                            and extra[6]=='連用形'))
                or not nextnoun[5] or not nextnoun[1].startswith('名詞')
                or nextcase[0] not in ('を','へ','に') or not nextcase[5]
                or not nextcase[1].startswith('助詞:格助詞')
                or not (simple_action or sahen_action)
                or any(a[4]!=b[3] for a,b in
                       ((obj,case),(case,verb),(verb,te),(te,extra),
                        (extra,nextnoun),(nextnoun,nextcase),
                        (nextcase,nextverb),(nextverb,aux)))
                or (sahen_action and aux[4]!=last[3])
                or overlaps(lo+verb[3],lo+last[4],protected)
                or not any(a<=te[3] and extra[4]<=b for a,b in grammar_spans)):
            continue
        exact=exact_context_reading(clause,verb[3],extra[4])
        if not exact or exact[0]!=verb[2]+'て'+extra[2]:
            continue
        corrected=verb[2]+'て'
        if not any(r.reading==corrected
                   and r.operation=='adjacent_intrusion'
                   and r.pressed==extra[2]
                   for r in key_repairs(exact[0])):
            continue
        marks=(('品詞文法','次の目的語前の遊離一打',
                lo+te[3],lo+extra[4]),)
        targets.append(RepairTarget(line,lo+verb[3],lo+extra[4],lo,hi,
            marks,True,line[lo+extra[4]:hi],'auxiliary_connection'))
    if 'てい' in clause or 'てと' in clause:
        from pos_grammar import _orphaned_key_before_direct_action_windows
        for verb,te,extra,aux in _orphaned_key_before_direct_action_windows(parts):
            if (overlaps(lo+verb[3],lo+aux[4],protected)
                    or not any(a<=te[3] and extra[4]<=b for a,b in grammar_spans)):
                continue
            exact=exact_context_reading(clause,verb[3],extra[4])
            raw=verb[2]+te[2]+extra[2]
            if exact:
                if exact[0]!=raw:
                    continue
            elif extra[0]=='と':
                from morphology import dictionary_inflections
                if not any(pos.startswith('動詞,自立,') and form==verb[6]
                           and reading==verb[2]
                           for pos,form,base,reading in dictionary_inflections(verb[0]) or ()):
                    continue
            else:
                continue
            if not any(r.reading==verb[2]+te[2]
                       and r.operation=='adjacent_intrusion' and r.pressed==extra[2]
                       for r in key_repairs(raw)):
                continue
            marks=(('品詞文法','実動作間の遊離一打',lo+te[3],lo+extra[4]),)
            targets.append(RepairTarget(line,lo+verb[3],lo+extra[4],lo,hi,
                marks,True,line[lo+extra[4]:hi],'auxiliary_connection'))
    return targets


def _marked_stray_to_before_sahen_past_targets(line,lo,hi,parts,grammar_spans):
    """Resolve extra と across a source-proven simple verb and sahen past."""
    if not grammar_spans:
        return []
    from ime_inverse_gate import exact_context_reading
    from literal_examples import protected_ranges, overlaps

    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    for i in range(len(parts)-8):
        obj,case,verb,te,extra,nexthead,nextsuru,aux,past=parts[i:i+9]
        if (not obj[5] or not obj[1].startswith('名詞')
                or case[0]!='を' or not case[5]
                or not case[1].startswith('助詞:格助詞')
                or not verb[5] or not verb[1].startswith('動詞:自立')
                or verb[6]!='連用形'
                or te[0]!='て' or not te[5]
                or not te[1].startswith('助詞:接続助詞')
                or extra[0]!='と' or not extra[5]
                or not extra[1].startswith('助詞:格助詞:引用')
                or not nexthead[5] or not nexthead[1].startswith('名詞:サ変接続')
                or nextsuru[0]!='し' or not nextsuru[5]
                or not nextsuru[1].startswith('動詞:自立') or nextsuru[6]!='連用形'
                or aux[0]!='まし' or not aux[5]
                or not aux[1].startswith('助動詞')
                or past[0]!='た' or not past[5]
                or not past[1].startswith('助動詞')
                or any(a[4]!=b[3] for a,b in
                       ((obj,case),(case,verb),(verb,te),(te,extra),
                        (extra,nexthead),(nexthead,nextsuru),
                        (nextsuru,aux),(aux,past)))
                or overlaps(lo+verb[3],lo+past[4],protected)
                or not any(a<=te[3] and extra[4]<=b for a,b in grammar_spans)):
            continue
        exact=exact_context_reading(clause,verb[3],extra[4])
        if not exact or exact[0]!=verb[2]+'てと':
            continue
        corrected=verb[2]+'て'
        if not any(r.reading==corrected
                   and r.operation=='adjacent_intrusion'
                   and r.pressed=='と'
                   for r in key_repairs(exact[0])):
            continue
        marks=(('品詞文法','次のサ変過去前の遊離と',
                lo+te[3],lo+extra[4]),)
        targets.append(RepairTarget(line,lo+verb[3],lo+extra[4],lo,hi,
            marks,True,line[lo+extra[4]:hi],'auxiliary_connection'))
    return targets


def _marked_interrupted_polite_action_targets(line, lo, hi, parts, odd):
    """Read a marked polite action across an intruding native て."""
    if not odd:
        return []
    from ime_inverse_gate import exact_context_reading
    from literal_examples import protected_ranges, overlaps

    clause = line[lo:hi]
    protected = protected_ranges(line)
    targets = []
    for i in range(len(parts)-6):
        obj, case, verb, connective, noun, aux, past = parts[i:i+7]
        if (not obj[5] or not obj[1].startswith('名詞')
                or case[0] != 'を' or not case[5]
                or not case[1].startswith('助詞:格助詞')
                or not verb[5] or not verb[1].startswith('動詞:自立')
                or verb[6] != '基本形'
                or connective[0] != 'て' or not connective[5]
                or not connective[1].startswith('助詞:接続助詞')
                or not noun[5] or not noun[1].startswith('名詞')
                or aux[0] != 'まし' or not aux[5]
                or not aux[1].startswith('助動詞')
                or past[0] != 'た' or not past[5]
                or not past[1].startswith('助動詞')
                or any(a[4] != b[3] for a,b in
                       ((obj,case),(case,verb),(verb,connective),
                        (connective,noun),(noun,aux),(aux,past)))
                or overlaps(lo+verb[3],lo+past[4],protected)):
            continue
        marks = tuple((left,right,lo+a,lo+b) for left,right,a,b in odd
                      if a <= noun[3] and b >= aux[4])
        if not marks:
            continue
        exact = exact_context_reading(clause,verb[3],past[4])
        if (not exact or not exact[0].startswith(verb[2]+'て')
                or not exact[0].endswith('ました')):
            continue
        repaired = exact[0][:len(verb[2])] + exact[0][len(verb[2])+1:]
        if (not repaired.endswith('しました')
                or not any(r.reading == repaired
                           and r.operation == 'adjacent_intrusion'
                           and r.position == len(verb[2])
                           and r.pressed == 'て'
                           for r in key_repairs(exact[0]))):
            continue
        targets.append(RepairTarget(line,lo+verb[3],lo+past[4],lo,hi,
            marks,True,line[lo+past[4]:hi],'lexical'))
    return targets


def _marked_unsplit_polite_action_after_case_targets(line,lo,hi,parts,odd):
    """Resolve a source-marked action when its polite past stayed unsplit."""
    if not odd:
        return []
    from ime_inverse_gate import exact_context_reading
    from literal_examples import protected_ranges,overlaps

    clause=line[lo:hi]
    if not clause.endswith('しました'):
        return []
    end=len(clause)-3
    if any(p[0]=='まし' and p[3]==end and p[5] for p in parts):
        return []
    protected=protected_ranges(line)
    targets=[]
    for head,case in zip(parts,parts[1:]):
        if (not head[5] or not head[1].startswith('名詞:副詞可能')
                or case[0]!='に' or not case[5]
                or not case[1].startswith('助詞:格助詞')
                or head[4]!=case[3]):
            continue
        start=case[4]
        body=clause[start:end]
        if (not 4<=len(body)<=8 or not body.endswith('し')
                or overlaps(lo+start,lo+end,protected)):
            continue
        marks=tuple((left,right,lo+a,lo+b) for left,right,a,b in odd
                    if left!='IME逆読み' and start<=a<b<=end)
        if not marks:
            continue
        exact=exact_context_reading(clause,start,end)
        if not exact or not exact[0].endswith('し'):
            continue
        targets.append(RepairTarget(line,lo+start,lo+end,lo,hi,
            marks,True,line[lo+end:hi],'lexical'))
    return targets


def _marked_converted_sahen_past_targets(line,lo,hi,parts,odd):
    """Use an unchanged native sahen head and one-key polite-past reading."""
    if not odd:
        return []
    from ime_inverse_gate import exact_context_reading
    from literal_examples import protected_ranges,overlaps
    from morphology import dictionary_inflections

    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    for head in parts:
        if (not head[5] or not head[1].startswith('名詞:サ変接続')
                or not 2<=len(clause)-head[4]<=4
                or not any(pos.startswith('名詞,サ変接続,')
                           and base==head[0] and reading==head[2]
                           for pos,form,base,reading in dictionary_inflections(head[0]) or ())
                or overlaps(lo+head[3],hi,protected)):
            continue
        marks=tuple((left,right,lo+a,lo+b) for left,right,a,b in odd
                    if left=='IME逆読み' and a<=head[3] and b>=len(clause))
        if not marks:
            continue
        exact=exact_context_reading(clause,head[3],len(clause))
        intended=head[2]+'しました'
        if (not exact or not exact[0].startswith(head[2])
                or len(exact[1])<2 or exact[1][0][0]!=0
                or exact[1][0][1]!=len(head[0])
                or exact[1][0][2]!=head[2]
                or not any(repair.reading==intended
                           and repair.operation=='adjacent_substitution'
                           for repair in key_repairs(exact[0]))):
            continue
        candidate=head[0]+'しました'
        targets.append(RepairTarget(line,lo+head[3],hi,lo,hi,
            marks,True,'','source_sahen_polite_tail',
            candidate_surface=candidate,candidate_reading=intended))
    return targets


def _marked_projected_polite_past_targets(line,lo,hi,parts,odd,tokenize):
    """Keep two native arguments for a short converted polite predicate."""
    if not odd:
        return []
    from ime_inverse_gate import exact_context_reading
    from literal_examples import protected_ranges,overlaps
    from semantic_roles import object_before,case_argument_before

    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    for i,first in enumerate(parts):
        start=first[3]
        body=clause[start:]
        if (not 2<=len(body)<=5 or not all(p[5] and p[1].startswith('名詞')
                                              for p in parts[i:])
                or overlaps(lo+start,hi,protected)):
            continue
        marks=tuple((left,right,lo+a,lo+b) for left,right,a,b in odd
                    if left=='IME逆読み' and a<=start and b>=len(clause))
        if not marks:
            continue
        obj=object_before(clause,start,tokenize)
        arg=case_argument_before(clause,start,tokenize)
        if not obj or not arg or arg[1]!='に':
            continue
        exact=exact_context_reading(clause,start,len(clause))
        if not exact:
            continue
        for repair in key_repairs(exact[0]):
            if (repair.operation!='adjacent_substitution'
                    and not (repair.operation=='adjacent_intrusion'
                             and repair.position==len(exact[0])-1)
                    or not repair.reading.endswith('ました')
                    or len(repair.reading)<5):
                continue
            targets.append(RepairTarget(line,lo+start,hi,lo,hi,
                marks,True,'','source_projected_polite_tail',
                candidate_reading=repair.reading))
    return targets


def _marked_nominal_de_before_kara_targets(line,lo,hi,parts,odd):
    """Keep a source-marked de/kara seam and resolve its preceding action."""
    if not odd:
        return []
    from ime_inverse_gate import exact_context_reading
    from literal_examples import protected_ranges,overlaps

    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    for i in range(len(parts)-1):
        head,case=parts[i:i+2]
        if (not head[5] or not head[1].startswith('名詞')
                or case[0]!='を' or not case[5]
                or not case[1].startswith('助詞:格助詞')
                or head[4]!=case[3]):
            continue
        for j in range(i+3,min(i+7,len(parts)-3)):
            de,kara,action,aux=parts[j:j+4]
            middle=parts[i+2:j]
            if (not middle or not all(t[5] and t[1].startswith('名詞') for t in middle)
                    or middle[0][3]!=case[4] or middle[-1][4]!=de[3]
                    or any(a[4]!=b[3] for a,b in zip(middle,middle[1:]))
                    or de[0]!='で' or not de[5]
                    or not de[1].startswith('助詞:格助詞')
                    or kara[0]!='から' or not kara[5]
                    or not kara[1].startswith('助詞:格助詞')
                    or de[4]!=kara[3] or kara[4]!=action[3]
                    or de[4]-case[4]>6
                    or overlaps(lo+case[4],lo+de[4],protected)):
                continue
            marks=tuple((left,right,lo+a,lo+b) for left,right,a,b in odd
                        if left=='で' and right=='から'
                        and a==de[3] and b==kara[4])
            if not marks:
                continue
            direct=(action[5] and action[1].startswith('動詞:自立')
                    and action[6]=='連用形' and aux[0]=='ます' and aux[5]
                    and aux[1].startswith('助動詞') and action[4]==aux[3])
            if not direct:
                # An independently proved following noun/case/predicate
                # owns its whole original range. It locates this seam,
                # without supplying meaning to the damaged earlier action.
                tail=clause[kara[4]:].rstrip('。！？.!?')
                finish=kara[4]+len(tail)
                owned=[t for t in parts[j+2:] if t[4]<=finish]
                if (not owned or not owned[0][1].startswith('名詞')
                        or owned[0][3]!=kara[4] or owned[-1][4]!=finish
                        or not all(t[5] for t in owned)
                        or any(a[4]!=b[3] for a,b in zip(owned,owned[1:]))
                        or ''.join(t[0] for t in owned)!=tail):continue
                from reading_segments import native_written_relative_action
                proof=native_written_relative_action(tail,allow_finite=True)
                if not proof or not proof[1] or not _finite_written_predicate(proof[0]):continue
            exact=exact_context_reading(clause,case[4],de[4])
            # Original native words can establish this same marked range
            # without an IME first-conversion round trip. Each member keeps
            # its actual POS, reading and coordinate; this does not attest
            # the nominal run as a whole word or make its reading typed input.
            from morphology import dictionary_inflections
            native=all(clause[t[3]:t[4]]==t[0] and _is_reading(t[2])
                and any(pos.split(',')[:len(t[1].split(':'))]==t[1].split(':')
                        and rd==t[2] and (form if form!='*' else '')==t[6]
                        for pos,form,base,rd in dictionary_inflections(t[0]) or ())
                for t in middle)
            native=native and clause[de[3]:de[4]]==de[0]==de[2]
            if not (exact and exact[0].endswith('で') or native):
                continue
            targets.append(RepairTarget(line,lo+case[4],lo+de[4],lo,hi,
                marks,True,line[lo+de[4]:hi],'lexical'))
    return targets



def _te_suffix_before_motion_targets(line,lo,hi,parts):
    """Use the source IME reading when a 手 noun suffix masks a te action."""
    from ime_inverse_gate import exact_context_reading,attested_context_reading
    from literal_examples import protected_ranges,overlaps
    from particle_frames import _following_native_motion
    from semantic_roles import nominal_roles

    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    for i in range(len(parts)-1):
        head,case=parts[i:i+2]
        if (not head[5] or not head[1].startswith('名詞')
                or case[0]!='を' or not case[5]
                or not case[1].startswith('助詞:格助詞')
                or head[4]!=case[3]):
            continue
        start=case[4]
        for j in range(i+3,min(i+9,len(parts)-3)):
            suffix=parts[j-1]
            destination,destcase,action,aux=parts[j:j+4]
            end=destination[3]
            body=clause[start:end]
            if (suffix[0]!='手' or not suffix[5]
                    or not suffix[1].startswith('名詞:接尾') or suffix[2]=='て'
                    or suffix[4]!=end
                    or not destination[5] or not destination[1].startswith('名詞')
                    or 'place' not in nominal_roles(destination[0])
                    or destcase[0]!='へ' or not destcase[5]
                    or not destcase[1].startswith('助詞:格助詞')
                    or not action[5] or not action[1].startswith('動詞:自立')
                    or action[6]!='連用形'
                    or aux[0]!='ます' or not aux[5]
                    or not aux[1].startswith('助動詞')
                    or any(a[4]!=b[3] for a,b in
                           ((destination,destcase),(destcase,action),(action,aux)))
                    or not _following_native_motion(clause[end:])
                    or not 4<=len(body)<=7 or not body.endswith('手')
                    or not all('ぁ'<=c<='ゖ' or 'ァ'<=c<='ヶ' or '一'<=c<='鿿'
                               for c in body)
                    or overlaps(lo+start,lo+end,protected)):
                continue
            exact=(exact_context_reading(clause,start,end)
                   or attested_context_reading(clause,start,end))
            if (not exact or not exact[0].endswith('て')
                    or not exact[1] or exact[1][-1][:3]!=(len(body)-1,len(body),'て')):
                continue
            marks=(('品詞文法','元の手接尾語と移動句の境界',lo+suffix[3],lo+end),)
            targets.append(RepairTarget(line,lo+start,lo+end,lo,hi,
                marks,True,line[lo+end:hi],'lexical'))
    return targets



def _marked_object_tail_before_noun_targets(line, lo, hi, parts, odd, grammar_spans):
    """Scope a source-marked te/手 action at its next object or field edge."""
    if not odd and not grammar_spans:
        return []
    from ime_inverse_gate import exact_context_reading,exact_mark_context_reading
    from literal_examples import protected_ranges,overlaps
    from morphology import DAKUTEN_MARKS,HANDAKUTEN_MARKS

    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    def hand_tail_marks(start,end,case_start):
        body=clause[start:end]
        if (not 4<=len(body)<=7 or not body.endswith('手')
                or not all('ぁ'<=c<='ゖ' or 'ァ'<=c<='ヶ' or '一'<=c<='鿿'
                           or c in DAKUTEN_MARKS+HANDAKUTEN_MARKS for c in body)
                or overlaps(lo+start,lo+end,protected)):return ()
        marks=tuple((left,right,lo+x,lo+y) for left,right,x,y in odd
                    if case_start<=x<end and start<y<=end)+tuple(
                    ('品詞文法','元の目的語と語尾の接続',lo+x,lo+y)
                    for x,y in grammar_spans if case_start<=x<end and start<y<=end)
        if not marks:return ()
        exact=exact_context_reading(clause,start,end)
        if not exact and any(c in '゛゜' for c in body):
            exact=exact_mark_context_reading(clause,start,end)
        return marks if exact and exact[0].endswith('て') else ()

    for i in range(len(parts)-1):
        head,case=parts[i:i+2]
        if (not head[5] or not head[1].startswith('名詞')
                or case[0]!='を' or not case[1].startswith('助詞:格助詞')
                or head[4]!=case[3]):
            continue
        start=case[4]
        # A literal marked action can end this field without borrowing
        # the next field as an object or a model answer. The same whole-source
        # reading and actual accusative prove its scope; candidates must still
        # supply a native te predicate fitting that unchanged object.
        if clause.endswith('手') and any(c in '゛゜' for c in clause[start:]):
            marks=hand_tail_marks(start,len(clause),case[3])
            if marks:
                targets.append(RepairTarget(line,lo+start,hi,lo,hi,marks,True,'','lexical'))
        for j in range(i+3,min(i+9,len(parts)-3)):
            nextnoun,nextcase,action,aux=parts[j:j+4]
            end=nextnoun[3]
            body=clause[start:end]
            if (not nextnoun[5] or not nextnoun[1].startswith('名詞')
                    or nextcase[0]!='を' or not nextcase[1].startswith('助詞:格助詞')
                    or not 4<=len(body)<=7 or body[-1] not in '手て'
                    or not all('ぁ'<=c<='ゖ' or 'ァ'<=c<='ヶ' or '一'<=c<='鿿'
                               or c in DAKUTEN_MARKS+HANDAKUTEN_MARKS for c in body)
                    or overlaps(lo+start,lo+end,protected)):
                continue
            simple=(action[5] and action[1].startswith('動詞:自立')
                and action[6]=='連用形' and aux[0]=='ます' and aux[5]
                and aux[1].startswith('助動詞')
                and all(a[4]==b[3] for a,b in
                        ((nextnoun,nextcase),(nextcase,action),(action,aux))))
            if not simple:
                if not body.endswith('て') or j+5>len(parts):
                    continue
                action,verb,aux=parts[j+2:j+5]
                if (not action[5] or not action[1].startswith('名詞:サ変接続')
                        or verb[0]!='し' or not verb[5]
                        or not verb[1].startswith('動詞:自立')
                        or verb[6]!='連用形'
                        or aux[0]!='ます' or not aux[5]
                        or not aux[1].startswith('助動詞')
                        or any(a[4]!=b[3] for a,b in
                               ((nextnoun,nextcase),(nextcase,action),
                                (action,verb),(verb,aux)))):
                    continue
            local_marks=tuple((left,right,lo+a,lo+b) for left,right,a,b in odd
                              if case[3]<=a<end and start<b<=end)
            if body.endswith('手'):
                marks=hand_tail_marks(start,end,case[3])
                if not marks:continue
            else:
                literal_keys=(local_marks and any(c in '゛゜' for c in body)
                    and all('ぁ'<=c<='ゖ' or c in '゛゜' for c in body))
                if (not literal_keys and (parts[j-1][0]!='て'
                        or not parts[j-1][1].startswith('助詞:接続助詞'))):
                    continue
                marks=local_marks+tuple(
                    ('品詞文法','元の目的語とかな動作',lo+a,lo+b)
                    for a,b in grammar_spans
                    if case[3]<=a<end and start<b<=end)
                if not marks:
                    inverse=tuple((left,right,lo+a,lo+b)
                                  for left,right,a,b in odd
                                  if left=='IME逆読み' and a<=start and b>=end)
                    exact=exact_context_reading(clause,start,end)
                    if not inverse or not exact or not exact[0].endswith('て'):
                        continue
                    marks=inverse
            targets.append(RepairTarget(line,lo+start,lo+end,lo,hi,
                marks,True,line[lo+end:hi],'lexical'))
    return targets




def _marked_base_verb_noun_te_targets(line, lo, hi, parts, grammar_spans):
    """Scope a source-marked basic verb plus kana noun before native て."""
    if not grammar_spans:
        return []
    from ime_inverse_gate import exact_context_reading
    from kana_layout import single_key_drop_adjacency
    from literal_examples import protected_ranges,overlaps
    from morphology import dictionary_inflections

    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    for head,case,verb,noun,link in zip(
            parts,parts[1:],parts[2:],parts[3:],parts[4:]):
        if (not head[5] or not head[1].startswith('名詞')
                or case[0]!='を' or not case[1].startswith('助詞:格助詞')
                or not verb[5] or not verb[1].startswith('動詞:自立')
                or verb[6]!='基本形' or len(verb[2])<2
                or not any('一'<=c<='鿿' for c in verb[0])
                or not noun[5] or not noun[1].startswith('名詞:一般')
                or len(noun[0])!=1 or not _is_input_reading(noun[0])
                or link[0] not in ('て','で') or not link[5]
                or not link[1].startswith('助詞:接続助詞')
                or any(a[4]!=b[3] for a,b in
                       ((head,case),(case,verb),(verb,noun),(noun,link)))
                or overlaps(lo+verb[3],lo+link[4],protected)):
            continue
        marks=tuple(('品詞文法','原文の基本形と接続',lo+a,lo+b)
                    for a,b in grammar_spans
                    if a==verb[4]-1 and b>=link[4])
        if not marks:
            continue
        if not any(pos.startswith('動詞,自立,') and form=='基本形'
                   and rd==verb[2]
                   for pos,form,base,rd in dictionary_inflections(verb[0]) or ()):
            continue
        exact=exact_context_reading(clause,verb[3],link[4])
        if not exact:
            continue
        reading,segments=exact
        source_reading=verb[2]+noun[2]+link[2]
        shorter=verb[2][:-1]+noun[2]+link[2]
        if (reading!=source_reading or len(segments)<3
                or single_key_drop_adjacency(reading,shorter) is not True):
            continue
        targets.append(RepairTarget(line,lo+verb[3],lo+link[4],lo,hi,
            marks,True,line[lo+link[4]:hi],'lexical'))
    return targets




def _marked_unknown_prefix_intrusion_targets(line, parts, inverse_marks, dictionary):
    """Scope an extra IME word before a native noun only from source proof."""
    if dictionary is None or not inverse_marks:
        return []
    from ime_inverse_gate import exact_context_reading
    from kana_layout import single_key_drop_adjacency
    from literal_examples import protected_ranges,overlaps
    protected=protected_ranges(line)
    targets=[]
    for part in parts:
        surface,pos,reading,start,end=part[:5]
        if (len(part)<7 or part[5] or not pos.startswith('名詞:一般')
                or len(surface)<3 or not all('一'<=c<='鿿' for c in surface)
                or overlaps(start,end,protected)
                or not any(a<=start and end<=b for _,_,a,b in inverse_marks)):
            continue
        suffix=surface[1:]
        suffix_readings=dictionary.readings_for_surface(suffix)
        if (not suffix_readings or dictionary.readings_for_surface(surface)):
            continue
        lo,hi=_source_clause_bounds(line,start,end)
        exact=exact_context_reading(line[lo:hi],start-lo,end-lo)
        if not exact:
            continue
        source_reading,segments=exact
        if (len(segments)!=2 or segments[0][:2]!=(0,1)
                or segments[1][:2]!=(1,len(surface))
                or segments[1][2] not in suffix_readings
                or source_reading!=segments[0][2]+segments[1][2]
                or single_key_drop_adjacency(source_reading,segments[1][2]) is not True):
            continue
        targets.append(RepairTarget(line,start,end,lo,hi,
            (('IME逆読み','原文の複合語先頭に余分な打鍵',start,end),),
            True,line[end:hi],'lexical'))
    return targets




def _marked_native_verb_kana_tail_targets(line, lo, hi, parts, odd):
    """Scope a proved て-stem with its marked one-kana broken link."""
    if not odd or any(len(part)<7 for part in parts):
        return []
    from morphology import dictionary_inflections
    targets=[]
    for verb,tail,nextverb,aux in zip(parts,parts[1:],parts[2:],parts[3:]):
        if (not verb[5] or not verb[1].startswith('動詞:自立')
                or verb[6]!='連用タ接続' or verb[4]!=tail[3]
                or not tail[5] or len(tail[0])!=1
                or not _is_input_reading(tail[0])
                or not tail[1].startswith('動詞:非自立')
                or tail[4]!=nextverb[3]
                or not nextverb[5] or not nextverb[1].startswith('動詞:自立')
                or nextverb[6]!='連用形' or nextverb[4]!=aux[3]
                or aux[0]!='ます' or not aux[1].startswith('助動詞')):
            continue
        marks=tuple((left,right,lo+a,lo+b) for left,right,a,b in odd
                    if a==verb[3] and b==tail[4])
        if not marks:
            continue
        if not any(pos.startswith('動詞,自立,') and form==verb[6]
                   and reading==verb[2]
                   for pos,form,base,reading in dictionary_inflections(verb[0]) or ()):
            continue
        reading=verb[2]+tail[2]
        if not any(row.operation=='adjacent_substitution'
                   and row.reading in (verb[2]+'て',verb[2]+'で')
                   for row in key_repairs(reading)):
            continue
        targets.append(RepairTarget(line,lo+verb[3],lo+tail[4],lo,hi,
            marks,True,line[lo+tail[4]:hi],'lexical'))
    return targets




def _marked_past_kana_object_targets(line, lo, hi, parts, odd):
    """Keep a native past modifier and repair its missegmented kana object."""
    if not odd:
        return []
    from ime_inverse_gate import exact_context_reading
    from literal_examples import protected_ranges,overlaps
    from morphology import dictionary_inflections

    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    for verb,aux in zip(parts,parts[1:]):
        if (not verb[5] or not verb[1].startswith('動詞:自立')
                or len(verb)<7 or len(aux)<7
                or verb[6]!='連用タ接続' or verb[4]!=aux[3]
                or aux[0]!='た' or not aux[5]
                or not aux[1].startswith('助動詞') or aux[6]!='基本形'):
            continue
        if not (any(pos.startswith('動詞,自立,') and form==verb[6]
                    and rd==verb[2]
                    for pos,form,base,rd in dictionary_inflections(verb[0]) or ())
                and any(pos.startswith('助動詞,') and form==aux[6]
                        and rd==aux[2]
                        for pos,form,base,rd in dictionary_inflections(aux[0]) or ())):
            continue
        start=aux[4]
        end=clause.find('を',start)
        if (end<0 or not 3<=end-start<=9 or end+1>=len(clause)
                or not all('ぁ'<=c<='ゖ' for c in clause[start:end])
                or overlaps(lo+start,lo+end,protected)):
            continue
        if not (any(not part[5] and part[3]<end and part[4]==end+1
                    for part in parts)
                and any(part[5] and part[1].startswith('名詞')
                        and part[3]==end+1 for part in parts)):
            continue
        marks=tuple((left,right,lo+a,lo+b) for left,right,a,b in odd
                    if start<=a<end and end+1<=b)
        if not marks or not exact_context_reading(clause,start,end):
            continue
        targets.append(RepairTarget(line,lo+start,lo+end,lo,hi,
            marks,True,line[lo+end:hi],'lexical'))
    return targets




def _attested_written_nominal_tail(text,parts):
    """A literal input prefix plus one actual written noun, not a whole word proof."""
    if not parts:return None
    tail=parts[-1]
    if (len(tail)<6 or not tail[5] or not tail[1].startswith('名詞')
            or tail[4]!=len(text) or not 0<tail[3]<tail[4]
            or not any('一'<=c<='鿿' for c in tail[0])
            or not _is_input_reading(_input_kana(text[:tail[3]]))):return None
    from morphology import dictionary_inflections
    if not any(pos.startswith(('名詞,一般,','名詞,サ変接続,'))
               and base==tail[0] and rd==tail[2]
               for pos,form,base,rd in dictionary_inflections(tail[0]) or ()):return None
    return tail


def _marked_adnominal_kana_object_targets(line, lo, hi, parts, odd, grammar_spans=()):
    """Keep the attested modifier and case; repair their marked noun reading."""
    if not odd and not grammar_spans:
        return []
    from literal_examples import protected_ranges,overlaps
    from reading_segments import native_adnominal_modifier_ranges
    clause=line[lo:hi]
    protected=protected_ranges(line)
    targets=[]
    # The same attested modifier boundary applies to an adjective,
    # an adnominal, or a nominal adjective with its actual copula.
    # It certifies only the unchanged prefix. The following noun still
    # needs an independent source anomaly and attested source reading.
    for _begin,start in native_adnominal_modifier_ranges(clause):
        end=clause.find('を',start)
        body=clause[start:end]
        if (end<0 or not 3<=len(body)<=8 or end+1>=len(clause)
                or overlaps(lo+start,lo+end,protected)):
            continue
        kana=all('ぁ'<=c<='ゖ' for c in body)
        mixed=(not kana and any('一'<=c<='鿿' or 'ァ'<=c<='ヶ' for c in body)
               and all('ぁ'<=c<='ゖ' or 'ァ'<=c<='ヶ'
                       or '一'<=c<='鿿' for c in body))
        if not (kana or mixed):
            continue
        marks=tuple((left,right,lo+a,lo+b) for left,right,a,b in odd
                    if a<end and start<b and (mixed or end+1<=b))
        if mixed:
            marks+=tuple(('品詞文法','元の連体名詞',lo+a,lo+b)
                         for a,b in grammar_spans if a<end and start<b)
        if not marks:
            continue
        if mixed:
            from ime_inverse_gate import exact_context_reading,attested_context_reading
            body_parts=[(*t[:3],t[3]-start,t[4]-start,*t[5:])
                        for t in parts if start<=t[3]<t[4]<=end]
            tail=_attested_written_nominal_tail(body,body_parts)
            # Missing source IME data does not erase a literal kana input
            # prefix or the dictionary reading of its unchanged written noun.
            # The independent original anomaly must belong to that prefix.
            native_tail=(tail is not None and all(
                lo+start<=a<b<=lo+start+tail[3] for _,_,a,b in marks))
            if not (exact_context_reading(clause,start,end)
                    or attested_context_reading(clause,start,end) or native_tail):
                continue
            # Native particles delimit phrases. Only a final particle
            # already inside the source anomaly can be an internal key;
            # genitives/cases and unmarked spoken boundaries remain intact.
            if any(t[1].startswith('助詞') and not (
                       '終助詞' in t[1] and len(t[0])==1
                       and any(a<=lo+t[3] and lo+t[4]<=b for _,_,a,b in marks))
                   for t in parts if start<=t[3] and t[4]<=end):
                continue
        targets.append(RepairTarget(line,lo+start,lo+end,lo,hi,
            marks,True,line[lo+end:hi],'lexical'))
    return targets



def _marked_written_verb_tail_targets(line, lo, hi, parts, grammar_spans):
    """Keep an attested written verb stem with its marked broken polite tail.

    The source grammar mark is the gate. Native dictionary inflection proves
    the unchanged stem; the common resolver proves the key and whole clause.
    """
    if not grammar_spans or any(len(part)<7 for part in parts):
        return []
    from morphology import dictionary_inflections
    targets=[]
    for i,head in enumerate(parts):
        if (not head[5] or not head[1].startswith('動詞:自立')
                or head[6]!='連用形'
                or not any('一'<=c<='鿿' for c in head[0])):
            continue
        if not any(pos.startswith('動詞,自立,') and form==head[6]
                   and reading==head[2]
                   for pos,form,base,reading in dictionary_inflections(head[0]) or ()):
            continue
        for j in range(i+2,min(i+5,len(parts))):
            auxiliary=parts[j]
            if (auxiliary[0]!='ます' or not auxiliary[5]
                    or not auxiliary[1].startswith('助動詞')):
                continue
            middle=parts[i+1:j]
            if (auxiliary[3]!=middle[-1][4]
                    or head[4]!=middle[0][3]
                    or any(a[4]!=b[3] for a,b in zip(middle,middle[1:]))
                    or not all(_is_input_reading(_input_kana(t[0]))
                               and not t[1].startswith(('助詞','記号','接続詞'))
                               for t in middle)):
                continue
            marks=tuple(('品詞文法','原文の活用語尾',lo+a,lo+b)
                        for a,b in grammar_spans
                        if a<=head[4] and b>=auxiliary[3])
            if not marks or auxiliary[3]-head[3]>12:
                continue
            target=RepairTarget(line,lo+head[3],lo+auxiliary[3],lo,hi,
                marks,True,line[lo+auxiliary[3]:hi],
                'auxiliary_connection',head[0])
            if target not in targets:
                targets.append(target)
            # The source object can also justify reconsidering the first
            # verb, if the marked whole action has its own exact IME reading.
            from semantic_roles import object_before
            from ime_inverse_gate import exact_context_reading
            clause=line[lo:hi]
            if (object_before(clause,head[3],lambda _:parts)
                    and exact_context_reading(clause,head[3],auxiliary[3])):
                whole=RepairTarget(line,lo+head[3],lo+auxiliary[3],lo,hi,
                    marks,True,line[lo+auxiliary[3]:hi],'lexical')
                if whole not in targets:
                    targets.append(whole)
            break
    return targets


def _native_action_tail_targets(targets):
    """Reuse a marked kana tail with an unchanged native action/verb head."""
    from reading_segments import native_polite_action_prefixes
    targets=list(targets)
    for target in tuple(targets):
        if (target.boundary_kind!='kana_request' or not target.structural or not target.anomalies
                or target.spelling or target.preserved_head):continue
        cuts=list(native_polite_action_prefixes(target.text))
        from morphology import tokenize,dictionary_inflections,FUNCTION_WORDS
        parts=tokenize(target.text)
        if len(parts)>1:
            first,last=parts[0],parts[-1]
            if (first.start==0 and first.has_reading and first.pos=='動詞' and first.pos_sub=='自立'
                    and first.infl_form=='連用形' and first.base_form not in FUNCTION_WORDS
                    and not any(t.pos=='助詞' and t.pos_sub.startswith('格助詞')
                                or t.pos=='動詞' and t.pos_sub=='自立' and t.base_form not in FUNCTION_WORDS
                                for t in parts[1:])
                    and last.end==len(target.text) and last.has_reading and last.pos=='助動詞'
                    and any(pos.startswith('動詞,自立,') and form=='連用形' and rd==first.reading
                            for pos,form,base,rd in dictionary_inflections(first.surface) or ())):
                cuts.append(first.end)
        for cut in dict.fromkeys(cuts):
            if not any(target.start+cut<b and a<target.end for _,_,a,b in target.anomalies):continue
            wide=replace(target,boundary_kind='auxiliary_connection',preserved_head=target.text[:cut])
            if wide not in targets:targets.append(wide)
    return targets


def _marked_lexical_suru_targets(targets):
    """Keep the original し when a marked lexical head may be a verb stem.

    Two unchanged native case arguments make the source action specific enough
    to test the wider reading. The normal candidate and final checks still
    decide its spelling; a bare or unfinished action supplies no new target.
    """
    from morphology import tokenize as native_tokenize,dictionary_inflections
    from reading_segments import (completed_native_verb_reading,
                                  native_completed_clause_boundaries)
    targets=list(targets)
    for target in tuple(targets):
        # A source basic verb can be marked together with the immediately
        # following native suru continuative. Keep both original readings
        # in the search scope before an actual te connection; otherwise
        # the unchanged shi falsely forces every candidate to be a noun.
        if (target.boundary_kind=='lexical' and target.structural
                and target.anomalies and not target.spelling
                and not target.preserved_head and target.following.startswith('して')
                and any(a<=target.start and target.end+1<=b
                        for _,_,a,b in target.anomalies)):
            head=native_tokenize(target.text)
            if (len(head)==1 and head[0].start==0
                    and head[0].end==len(target.text) and head[0].has_reading
                    and head[0].pos=='動詞' and head[0].pos_sub=='自立'
                    and head[0].infl_form=='基本形'
                    and any('一'<=c<='鿿' for c in head[0].surface)
                    and any(pos.startswith('動詞,自立,') and form=='基本形'
                            and rd==head[0].reading and base==head[0].base_form
                            for pos,form,base,rd in
                            dictionary_inflections(head[0].surface) or ())):
                boundary=target.end-target.context_start
                tail=[part for part in native_tokenize(target.context)
                      if part.start>=boundary]
                from morphology import native_suru_form
                if (len(tail)>=2 and tail[0].start==boundary
                        and tail[0].surface=='し' and tail[0].has_reading
                        and tail[0].pos=='動詞' and tail[0].base_form=='する'
                        and native_suru_form(tail[0].surface,tail[0].infl_form,
                                             tail[0].reading,False)
                        and tail[1].start==tail[0].end and tail[1].surface=='て'
                        and tail[1].has_reading and tail[1].pos=='助詞'
                        and tail[1].pos_sub=='接続助詞'):
                    wide=replace(target,end=target.end+1,
                                 following=target.following[1:])
                    # This source anomaly straddles the native verb and
                    # suru. Its truncated prefix is not an independent
                    # completed word that can settle the wider search.
                    targets.remove(target)
                    if wide not in targets:targets.append(wide)
                    continue
        # A proved continuative verb plus a marked noun and source し/て
        # can instead be one inflected compound verb. Keep the actual し
        # in the editable reading; candidates still need a physical key
        # repair and the ordinary native and context validation.
        if (target.boundary_kind == 'lexical' and target.structural
                and target.anomalies and not target.spelling
                and not target.preserved_head and target.following.startswith('して')
                and any(a < target.end and target.end + 1 <= b
                        for _, _, a, b in target.anomalies)):
            head = native_tokenize(target.text)
            if (len(head) == 2 and head[0].has_reading
                    and head[0].pos == '動詞' and head[0].pos_sub == '自立'
                    and head[0].infl_form == '連用形'
                    and any(pos.startswith('動詞,自立,') and form == '連用形'
                            and rd == head[0].reading
                            for pos, form, base, rd in
                            dictionary_inflections(head[0].surface) or ())
                    and head[1].has_reading and head[1].pos == '名詞'
                    and head[1].pos_sub == '一般'
                    and head[0].end == head[1].start
                    and head[1].end == len(target.text)):
                boundary = target.end - target.context_start
                tail = [part for part in native_tokenize(target.context)
                        if part.start >= boundary]
                if (len(tail) >= 2 and tail[0].start == boundary
                        and tail[0].surface == 'し' and tail[0].has_reading
                        and tail[0].pos == '動詞' and tail[0].base_form == 'する'
                        and tail[1].start == tail[0].end
                        and tail[1].surface == 'て' and tail[1].pos == '助詞'
                        and tail[1].pos_sub == '接続助詞'):
                    wide = replace(target, end=target.end + 1,
                                   following=target.following[1:], boundary_kind='compound_verb')
                    if wide not in targets: targets.append(wide)
        # A marked noun plus native suffix followed by し/ます may instead
        # be one inflected verb. Keep the actual し in the editable source.
        if (target.boundary_kind=='lexical' and target.structural
                and target.anomalies and not target.spelling
                and not target.preserved_head and target.following.startswith('します')
                and any(a<target.end and target.end+1<=b
                        for _,_,a,b in target.anomalies)):
            head=native_tokenize(target.text)
            if (len(head)==2 and all(t.has_reading and t.pos=='名詞' for t in head)
                    and head[0].pos_sub=='一般'
                    and head[1].pos_sub.startswith('接尾')
                    and head[0].end==head[1].start
                    and head[1].end==len(target.text)
                    and not dictionary_inflections(target.text)):
                boundary=target.end-target.context_start
                tail=[part for part in native_tokenize(target.context)
                      if part.start>=boundary]
                if (len(tail)>=2 and tail[0].start==boundary
                        and tail[0].surface=='し' and tail[0].has_reading
                        and tail[0].pos=='動詞' and tail[0].base_form=='する'
                        and tail[0].infl_form=='連用形'
                        and tail[1].start==tail[0].end
                        and tail[1].surface=='ます' and tail[1].pos=='助動詞'):
                    wide=replace(target,end=target.end+1,
                                 following=target.following[1:])
                    if wide not in targets:targets.append(wide)
        # An anomalous lexical head can have its last reading key parsed
        # as a connective before the actual suru predicate. Retain this
        # original continuation as another lexical range, using the same
        # source anomaly and final candidate/argument validation.
        if (target.boundary_kind=='lexical' and target.anomalies
                and not target.spelling and not target.preserved_head):
            boundary=target.end-target.context_start
            tail=[part for part in native_tokenize(target.context) if part.start>=boundary]
            if (tail and tail[0].start==boundary and tail[0].surface in ('て','で')
                    and tail[0].pos=='助詞' and tail[0].pos_sub=='接続助詞'):
                cursor=tail[0].end
                for part in tail[1:]:
                    if part.start!=cursor or not part.has_reading:break
                    if part.pos=='動詞' and part.pos_sub=='自立' and part.base_form=='する':
                        wide=replace(target,end=target.context_start+cursor,following=target.context[cursor:])
                        if wide not in targets:targets.append(wide)
                        break
                    if part.pos=='動詞' and part.pos_sub=='非自立' and part.base_form=='いる':
                        cursor=part.end
                    else:break
        if (target.boundary_kind!='lexical' or not target.structural or target.spelling
                or target.preserved_head or not target.following.startswith('し')
                or not any(a<=target.start<target.end<b
                           for _,_,a,b in target.anomalies)
                or not completed_native_verb_reading(target.following,
                        allow_nonpolite=True,require_roles=False)):
            continue
        # A complete original verb must not be re-read as an unrelated stem.
        # Even two source arguments may leave distinct one-key actions plausible.
        head=native_tokenize(target.text)
        if (len(head)==1 and head[0].start==0 and head[0].end==len(target.text)
                and head[0].has_reading and head[0].pos=='動詞'
                and head[0].pos_sub=='自立' and head[0].infl_form=='基本形'):
            from morphology import dictionary_inflections
            if any(pos.startswith('動詞,自立,') and form=='基本形'
                   and base==target.text and reading==head[0].reading
                   for pos,form,base,reading in dictionary_inflections(target.text) or ()):
                # A complete source verb cannot justify a different suru noun.
                # Without independent action evidence, keep the marked source.
                targets.remove(target)
                continue
        prior=target.context[:target.start-target.context_start]
        seam=max(native_completed_clause_boundaries(prior),default=0)
        parts=native_tokenize(prior[seam:])
        cases=[]
        for i,particle in enumerate(parts):
            if (i==0 or not particle.has_reading or particle.pos!='助詞'
                    or not particle.pos_sub.startswith('格助詞')
                    or particle.surface not in ('を','に','へ')):
                continue
            noun=parts[i-1]
            if (noun.end!=particle.start or not noun.has_reading or noun.pos!='名詞'
                    or any(kind in noun.pos_sub for kind in
                           ('代名詞','固有名詞','非自立','接尾'))):
                continue
            cases.append(particle.surface)
        if not any(left=='を' and right in ('に','へ')
                   for i,left in enumerate(cases) for right in cases[i+1:]):
            continue
        wide=replace(target,end=target.end+1,following=target.following[1:],
                     boundary_kind='auxiliary_connection')
        if wide not in targets:targets.append(wide)
    return targets


@lru_cache(maxsize=2048)
def _source_actions_before_owned_objects(clause):
    """A complete following object clause bounds the earlier marked action.

    The later noun supplies only its own boundary. Its role cannot prove the
    earlier action, which retains its original object and all final checks.
    """
    from morphology import tokenize
    from reading_segments import (native_surface_nominal_heads,
        native_object_predicate_contexts,native_object_predicate_proof,
        native_completed_clause_boundaries)
    parts=tokenize(clause);out=[]
    seams=native_completed_clause_boundaries(clause)
    for noun,case in zip(parts,parts[1:]):
        if (not noun.has_reading or noun.pos!='名詞'
                or any(k in noun.pos_sub for k in ('代名詞','固有名詞','非自立','接尾'))
                or noun.end!=case.start or not case.has_reading
                or case.surface!='を' or case.pos!='助詞'
                or not case.pos_sub.startswith('格助詞')
                or not native_surface_nominal_heads(noun.surface)):continue
        edge=noun.start;following=clause[edge:]
        if not any(begin==0 and native_object_predicate_proof(following,cut,faces)
                for begin,cut,faces in native_object_predicate_contexts(following,True)):continue
        frames=list(native_object_predicate_contexts(clause[:edge],True))
        # A malformed predicate may have been parsed as an auxiliary. Its
        # actual prior noun and accusative still independently own its start.
        for prior in parts:
            if (prior.end>=edge or not prior.has_reading or prior.surface!='を'
                    or prior.pos!='助詞' or not prior.pos_sub.startswith('格助詞')):continue
            # An independently proved earlier source clause owns its own
            # arguments. Start this noun after that existing boundary, and
            # retain the exact source suffix for the whole-noun proof. The
            # earlier action supplies no meaning to this marked predicate.
            begin=max((seam for seam in seams if seam<=prior.start),default=0)
            faces=native_surface_nominal_heads(clause[begin:prior.start],
                                               original_context=clause[begin:])
            if faces and (begin,prior.end,faces) not in frames:
                frames.append((begin,prior.end,faces))
        for begin,cut,faces in frames:
            if not 2<=edge-cut<=18:continue
            if native_object_predicate_proof(clause[begin:edge],cut-begin,faces,allow_link=True):continue
            row=(begin,cut,edge,faces)
            if row not in out:out.append(row)
    return tuple(out)


def _source_owned_action_contexts(target):
    """Keep the original object when its final connective is unchanged.

    The following clause proves only its own noun/case and boundary.
    This supplies an obligation to the same object validation below,
    never a positive meaning for the marked earlier action.
    """
    from morphology import tokenize,dictionary_inflections
    start=target.start-target.context_start;end=target.end-target.context_start
    parts=None;out=[]
    for begin,cut,edge,faces in _source_actions_before_owned_objects(target.context):
        if cut!=start:continue
        if edge!=end:
            if (target.boundary_kind!='lexical' or not target.structural
                    or not target.anomalies or target.spelling or not end<edge):continue
            if parts is None:parts=tokenize(target.context)
            link=next((t for t in parts if t.start==end and t.end==edge),None)
            if link is None:
                # The same exact unedited temporal particle sequence owns
                # this first object's obligation; the next object does not.
                from particle_frames import _native_te_kara_end
                first=next((t for t in parts if t.start==end),None)
                if first is not None and _native_te_kara_end(target.context,first,parts)==edge:
                    row=(begin,cut,faces)
                    if row not in out:out.append(row)
                continue
            if (not link or not link.has_reading or link.pos!='助詞'
                    or link.pos_sub!='接続助詞' or link.surface not in ('て','で')
                    or link.surface!=link.reading
                    or target.context[end:edge]!=link.surface
                    or not any(pos.startswith('助詞,接続助詞,') and rd==link.reading
                               and base==link.base_form
                               and ('' if form=='*' else form)==link.infl_form
                               for pos,form,base,rd in dictionary_inflections(link.surface) or ())):continue
        row=(begin,cut,faces)
        if row not in out:out.append(row)
    return tuple(out)


def _marked_action_before_owned_object_targets(line,lo,hi,odd,grammar_spans):
    """Source marks and independently proved clauses share exact boundaries."""
    from literal_examples import protected_ranges,overlaps
    marks=tuple(odd)+tuple(('品詞文法','未説明の原文接続',a,b) for a,b in grammar_spans)
    if not marks:return []
    out=[];clause=line[lo:hi]
    for begin,cut,edge,faces in _source_actions_before_owned_objects(clause):
        relevant=tuple((a,b,lo+start,lo+end) for a,b,start,end in marks
                       if start<edge and cut<end)
        if not relevant or overlaps(lo+cut,lo+edge,protected_ranges(line)):continue
        editable_end=edge
        # The source's native open action can independently bind te/de +
        # kara to the later clause. The broader object-owned path must use
        # that same original action edge, not reopen its temporal particles.
        # No candidate spelling, reading repair or rank decides this bound.
        from morphology import tokenize as native_tokenize
        from oddness import native_final_particle_inside_link
        from particle_frames import _native_te_kara_end
        native=native_tokenize(clause)
        original=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                   t.start,t.end,t.has_reading,t.infl_form) for t in native]
        for i,(head,terminal,link,after) in enumerate(zip(native,native[1:],native[2:],native[3:])):
            if head.start!=cut or after.end!=edge:continue
            if (_native_te_kara_end(clause,link,native)==edge
                    and native_final_particle_inside_link(*original[i:i+3],
                        original[i-1] if i else None,text=clause,parts=original)):
                editable_end=link.start
                break
        target=RepairTarget(line,lo+cut,lo+editable_end,lo,hi,relevant,True,
            clause[editable_end:],'lexical')
        if target not in out:out.append(target)
    return out



def _native_owned_predicate_targets(targets,tokenize):
    """A proved original object owns the unresolved action before its mark.

    A tentative connective token does not prove a complete prior action.
    Retain the shared frame as an alternative to the local malformed word;
    real clauses, new cases, literals and source protection keep their edges.
    """
    from reading_segments import native_predicate_link_boundaries
    from literal_examples import protected_ranges,overlaps
    targets=list(targets)
    for target in tuple(targets):
        if (target.boundary_kind!='lexical' or not target.structural
                or not target.anomalies or target.spelling or target.preserved_head):continue
        frame=_source_object_predicate_frame(target.source,target.start,target.end)
        if frame is None:continue
        lo,hi,begin,cut,faces=frame;start=lo+cut
        if not (target.context_start==lo and start<target.start
                and target.end-start<=18):continue
        prefix=[t for t in tokenize(target.source[lo:hi])
                if cut<=t[3] and t[4]<=target.start-lo]
        if (not prefix or prefix[0][3]!=cut or prefix[-1][4]!=target.start-lo
                or any(_case_boundary(t) or _literal_boundary(t) or t[1].startswith('記号')
                       for t in prefix)):continue
        if any(cut<edge<=target.start-lo
               for edge in native_predicate_link_boundaries(target.source[lo:hi],cut)):continue
        if overlaps(start,target.end,protected_ranges(target.source)):continue
        wide=replace(target,start=start)
        if wide not in targets:targets.append(wide)
    return targets


def _native_verb_prefix_targets(targets):
    # 48-AHQ: a native, unmarked continuative verb may precede the
    # anomalous lexical head (巻き込み + 乳力). Retain its exact source
    # token as another candidate boundary; the full target also competes.
    # This is not proof that the preceding clause is complete or natural.
    # The following native suru form distinguishes a nominal action from
    # an unproved compound verb. Every candidate keeps the full context.
    from morphology import tokenize as native_tokenize, dictionary_inflections
    targets=list(targets)
    for target in tuple(targets):
        if target.boundary_kind!='lexical' or target.spelling or target.preserved_head:continue
        local=target.start-target.context_start
        parts=native_tokenize(target.context)
        following=next((t for t in parts if t.start==target.end-target.context_start),None)
        first=next((t for t in parts if t.start==local),None)
        neighbor=next((t for t in parts if first and t.start==first.end),None)
        # A same-reading dictionary noun and its original nominal slot
        # independently own this written head. Share exactly the join mark
        # which used that proof, retaining the whole target as a competitor.
        if first and neighbor and target.context_start+first.end<target.end:
            edge=target.context_start+first.end
            mark=(first.surface,neighbor.surface,target.context_start+first.start,
                  target.context_start+neighbor.end)
            if (mark in target.anomalies
                    and not any(row!=mark and row[2]<edge for row in target.anomalies)):
                import oddness
                def native_row(t):
                    return (t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),
                            t.reading,t.start,t.end,t.has_reading,t.infl_form)
                if oddness._native_nominal_prefix_join_mismatch(
                        target.context,native_row(first),native_row(neighbor)):
                    narrow=replace(target,start=edge)
                    if narrow not in targets:targets.append(narrow)
        if not (following and following.has_reading and following.pos=='動詞'
                and following.base_form=='する' and any(
                    _sahen_verb_form(pos,base,following.surface,form,rd) and form==following.infl_form and rd==following.reading
                    for pos,form,base,rd in dictionary_inflections(following.surface) or ())):continue
        first=next((t for t in parts if t.start==local),None)
        if not (first and first.has_reading and first.pos=='動詞' and first.pos_sub=='自立'
                and first.infl_form=='連用形' and target.context_start+first.end<target.end):continue
        edge=target.context_start+first.end
        if not target.anomalies or any(a<edge for _,_,a,b in target.anomalies):continue
        if not any(pos.startswith('動詞,自立,') and form=='連用形' and rd==first.reading
                   for pos,form,base,rd in dictionary_inflections(first.surface) or ()):continue
        narrow=replace(target,start=edge)
        if narrow not in targets:targets.append(narrow)
    return targets


def _native_modified_nominal_prefix_targets(targets):
    """The original modifier and known noun retain a marked join's head.

    Only an existing exact noun/noun join anomaly supplies this tail scope.
    The complete native modifier and the unchanged head's own dictionary
    reading prove its boundary, independently of any proposed repair.
    """
    from morphology import tokenize,dictionary_inflections
    from reading_segments import native_adnominal_modifier_parts
    targets=list(targets)
    for target in tuple(targets):
        if (target.boundary_kind!='lexical'
                or not target.anomalies or target.spelling or target.preserved_head):continue
        parts=tokenize(target.context);offset=target.context_start
        for head,tail in zip(parts,parts[1:]):
            mark=(head.surface,tail.surface,offset+head.start,offset+tail.end)
            edge=offset+head.end
            if (mark not in target.anomalies or not target.start<offset+head.start<edge<target.end
                    or head.end!=tail.start or not head.has_reading or not tail.has_reading
                    or head.pos!='名詞' or tail.pos!='名詞'
                    or any(x in head.pos_sub for x in ('固有名詞','接尾','非自立'))
                    or target.source[offset+head.start:edge]!=head.surface
                    or any(row!=mark and row[2]<edge for row in target.anomalies)):continue
            prefix=target.context[target.start-offset:head.start]
            if not native_adnominal_modifier_parts(prefix,allow_written=True):continue
            if not any(pos.startswith('名詞,') and base==head.surface and rd==head.reading
                       and not any(x in pos for x in ('固有名詞','接尾','非自立'))
                       for pos,form,base,rd in dictionary_inflections(head.surface) or ()):continue
            narrow=replace(target,start=edge)
            if narrow not in targets:targets.append(narrow)
    return targets


def _native_focused_prefix_targets(targets):
    # 48-AHR: a native focus can be swallowed by the malformed following word.
    # Keep the original wider interpretation and the same anomaly/context.
    targets=list(targets)
    for target in tuple(targets):
        if (target.boundary_kind not in ('lexical','auxiliary_connection')
                or target.spelling or target.preserved_head or not target.anomalies):continue
        for local in _native_focused_te_edges(target.context):
            edge=target.context_start+local
            if target.start!=edge-1 or edge>=target.end:continue
            if any(a<edge for _,_,a,b in target.anomalies):continue
            narrow=replace(target,start=edge)
            if narrow not in targets:targets.append(narrow)
    return targets


def _unexplained_nominal_copula_targets(line,lo,hi,odd,grammar_spans):
    """A marked original noun may keep its spelling while its copula is repaired.

    The same native noun proof supplies only the source boundary. Candidate
    copulas must complete that exact noun span through the common validator.
    Unknown nouns and source clauses without an existing mark supply no target.
    """
    clause=line[lo:hi]
    marks=tuple(dict.fromkeys(list(grammar_spans)+[(a,b) for _,_,a,b in odd]))
    if not marks or not _is_input_reading(clause):return []
    from reading_segments import native_nominal_phrase_faces,completed_native_nominal_predicate
    if completed_native_nominal_predicate(clause):return []
    from pos_grammar import _NOUN_PRED,_FINAL_PARTICLES,_EXTRA_PARTICLES
    # One attested finite copula, a final particle and one extra key.
    width=max(len(word) for word,state in _NOUN_PRED if state in ('END','TA'))
    width+=max(map(len,_FINAL_PARTICLES|_EXTRA_PARTICLES))+1
    from morphology import tokenize as native_tokenize
    parts=native_tokenize(clause)
    result=[]
    for cut in range(max(1,len(clause)-width),len(clause)-1):
        # The nominal proof cannot cut an actual known word in half.
        if any(t.has_reading and t.start<cut<t.end for t in parts):continue
        if not native_nominal_phrase_faces(clause[:cut]):continue
        anomalies=tuple(('品詞文法','原文の名詞述語の範囲',lo+a,lo+b)
                        for a,b in marks if a<len(clause) and cut<b)
        if anomalies:
            result.append(RepairTarget(line,lo+cut,hi,lo,hi,anomalies,True,'','kana_copula'))
    return result


def _native_kana_targets(line,lo,hi,tokenize,store,dictionary,odd,grammar_spans=None):
    """One source reading/argument proof shared by full and comma scopes."""
    clause=line[lo:hi]
    if grammar_spans is None:
        import pos_grammar
        grammar_spans=pos_grammar.odd_kana_spans(clause,dictionary,store)
    result=list(_unexplained_kana_request_targets(line,lo,hi,tokenize,store,dictionary,
                                                source_anomalies=odd,grammar_spans=grammar_spans))
    result.extend(_unexplained_nominal_copula_targets(line,lo,hi,odd,grammar_spans))
    from reading_segments import native_case_adnominal_parts
    for head_end,link_end,heads,following_heads in native_case_adnominal_parts(clause,True):
        if heads or head_end<2:continue
        marks=tuple(('品詞文法','未説明の連体名詞',lo+a,lo+b)
            for a,b in dict.fromkeys(list(grammar_spans)+[(a,b) for _,_,a,b in odd])
            if a<head_end and 0<b)
        if marks:result.append(RepairTarget(line,lo,lo+head_end,lo,hi,marks,True,
                                           clause[head_end:],'lexical'))
    # Keep the native action head with its already anomalous functional
    # tail. The original dictionary boundary, not a repaired answer,
    # establishes this scope when tokenization has split the head itself.
    if (odd or grammar_spans) and _is_input_reading(clause):
        from morphology import dictionary_inflections
        from reading_segments import completed_native_reading,native_adnominal_modifier_ranges
        if not completed_native_reading(clause):
            modifiers=native_adnominal_modifier_ranges(clause)
            for cut,prefix,heads in _native_sahen_reading_heads(clause):
                # A source-proved modifier owns its native copula as well
                # as its head. A homophonic action noun cannot reopen that
                # boundary merely because the following noun is unknown.
                if any(begin==0 and cut<end for begin,end in modifiers):continue
                # An independently proved longer nominal head owns its
                # copula; its inner sahen noun cannot steal that ending.
                if any(t.boundary_kind=='kana_copula' and lo+cut<t.start
                       and t.end==hi for t in result):continue
                marks=[(a,b) for a,b in grammar_spans if cut<b]
                marks.extend((a,b) for _,_,a,b in odd if cut<b)
                if not marks:continue
                if any(_allows_grammatical_tail(dictionary_inflections(head) or (),clause[cut:],prefix,head)
                       and _productive_predicate(head+clause[cut:],head) for head in heads):continue
                result.append(RepairTarget(line,lo,hi,lo,hi,
                    tuple(('品詞文法','原文のサ変接続',lo+a,lo+b) for a,b in dict.fromkeys(marks)),True,'','sahen_tail',prefix))
                result.append(RepairTarget(line,lo,hi,lo,hi,
                    tuple(('品詞文法','原文のサ変接続',lo+a,lo+b) for a,b in dict.fromkeys(marks)),True,'','lexical'))
                break
    # 48-ALI/ANY: a marked nominal slot does not require a broad
    # request-word target. A proved source adjunct can include kana parsed
    # as an interjection (さ + ...), which correctly blocks that broad
    # search but does not erase the independent noun/case/predicate proof.
    # Existing request targets derive these same slots once downstream.
    if not any(t.boundary_kind=='kana_request' for t in result):
        # Keep the original reason, so the same native object reached
        # below is the same target rather than a relabelled second search.
        marked={(a,b) for _,_,a,b in odd}
        anomalies=tuple((left,right,lo+a,lo+b) for left,right,a,b in odd)
        anomalies+=tuple(('品詞文法','未説明の目的語',lo+a,lo+b)
                         for a,b in dict.fromkeys(grammar_spans) if (a,b) not in marked)
        result.extend(_unexplained_nominal_source_targets(line,lo,hi,lo,anomalies))
    # 48-ACQ: a kana grammar anomaly is already a judgment even when
    # the tokenizer swallowed a whole predicate as one unknown token.
    # Keep its unchanged noun/case in context; edit only the predicate.
    from reading_segments import (native_object_predicate_cuts,
        native_argument_predicate_cuts,completed_native_reading)
    kana_cuts=native_argument_predicate_cuts(clause)
    if kana_cuts and not completed_native_reading(clause):
        import pos_grammar
        kana_odd=grammar_spans
        kana_odd=list(dict.fromkeys(list(kana_odd)+[(a,b) for _,_,a,b in odd]))
        for cut in kana_cuts:
            relevant=[(s,e) for s,e in kana_odd if s<len(clause) and cut<e]
            if not relevant:
                # The untouched noun/case already fixed this predicate's
                # boundary. Reuse the existing kana grammar judgment on
                # that original span when a leading を hides it in the run.
                from corrector import _kana_run_is_odd_by_grammar
                if _kana_run_is_odd_by_grammar(clause[cut:],dictionary,store):
                    relevant=[(cut,len(clause))]
            if relevant:
                result.append(RepairTarget(line,lo+cut,hi,lo,hi,
                    tuple(('品詞文法','未説明のかな述語',lo+s,lo+e) for s,e in relevant),
                    True,'','kana_predicate'))
    # A proved following movement leaves this marked action as its own
    # original object/predicate scope. The full multi-clause text cannot
    # be passed to the single-predicate kana frame, but its first part can.
    marks=tuple(dict.fromkeys(list(grammar_spans)+[(a,b) for _,_,a,b in odd]))
    if marks:
        from morphology import tokenize as native_tokenize
        from particle_frames import _following_native_motion
        for link in native_tokenize(clause):
            if (link.surface not in ('て','で') or link.pos!='助詞'
                    or link.pos_sub!='接続助詞' or not link.has_reading
                    or not _following_native_motion(clause[link.end:])):continue
            for cut in native_object_predicate_cuts(clause[:link.end]):
                if not _is_input_reading(clause[cut:link.start]):continue
                relevant=tuple(('品詞文法','未説明のかな述語',lo+a,lo+b)
                    for a,b in marks if a<link.start and cut<b)
                if relevant:
                    result.append(RepairTarget(line,lo+cut,lo+link.start,lo,hi,
                        relevant,True,clause[link.start:],'lexical'))
    return result


def _comma_native_kana_targets(line,lo,hi,tokenize,store,dictionary,odd,grammar_spans):
    """48-AKI: preserve existing anomalies in independently framed clauses.

    A comma alone supplies no word, grammar or anomaly. Only a native
    nominal/case/predicate frame can reuse a smaller proof scope; ordinary
    whole-sentence targets still retain relations spanning the comma.
    """
    clause=line[lo:hi]
    if not re.search('[、,]',clause):return []
    # The same full-source kana judgment already supplies the visible purple.
    # Native token oddness alone can be empty even for that marked grammar.
    odd=tuple(dict.fromkeys(list(odd)+[
        ('品詞文法','未説明のかな接続',a,b) for a,b in grammar_spans]))
    if not odd:return []
    result=[]
    for match in re.finditer('[^、,]+',clause):
        body=match.group()
        if not _is_input_reading(body):continue
        begin,end=match.span()
        marks=tuple((left,right,max(a,begin)-begin,min(b,end)-begin)
                    for left,right,a,b in odd if a<end and begin<b)
        if not marks:continue
        for target in _native_kana_targets(line,lo+begin,lo+end,tokenize,store,dictionary,marks):
            # Request-only tails and arbitrary fragment guesses cannot
            # acquire a new independent scope merely from punctuation.
            if target.boundary_kind not in ('lexical','kana_predicate'):continue
            source_marks=tuple((left,right,lo+a,lo+b) for left,right,a,b in odd
                              if lo+a<target.end and target.start<lo+b)
            if source_marks:result.append(replace(target,anomalies=source_marks))
    return result


@lru_cache(maxsize=2048)
def _native_marked_prefix_edges(context):
    """The actual source prefix owns its end before a malformed onset.

    A yoon anomaly includes the previous character. An independently
    attested full modifier or noun plus native particle can own that
    character without proving any reading or meaning for the next word.
    """
    from morphology import source_yoon_spans,dictionary_inflections
    from reading_segments import native_surface_nominal_heads,native_adnominal_modifier_parts
    from morphology import tokenize as native_tokenize
    edges=set()
    onsets={end-1 for begin,end in source_yoon_spans(context)}
    # A native particle can accidentally form a legal yoon with the next
    # malformed noun. Its unknown small-kana token still has an original
    # onset; the whole left noun and actual particle must prove the cut.
    onsets.update(part.start for part in native_tokenize(context)
        if part.pos=='名詞' and not part.has_reading and part.surface[:1] in ('ゃ','ゅ','ょ'))
    for edge in sorted(onsets):
        if edge<=0 or context[edge:edge+1] not in ('ゃ','ゅ','ょ'):continue
        prefix=context[:edge]
        # A complete modifier is its own source unit, not a new nominal
        # sense obtained by splitting its final particle-shaped character.
        if native_adnominal_modifier_parts(prefix,allow_written=True):
            edges.add(edge);continue
        for cut in range(max(1,edge-3),edge):
            particle=context[cut:edge]
            if not any(pos.startswith(('助詞,格助詞,一般,','助詞,係助詞,','助詞,連体化,'))
                       and rd==particle for pos,form,base,rd in dictionary_inflections(particle) or ()):continue
            if native_surface_nominal_heads(context[:cut],original_context=context):
                edges.add(edge);break
    return tuple(sorted(edges))


def _native_marked_word_prefix_targets(targets):
    """An unchanged native modifier remains context for a marked word.

    Only the original small-kana anomaly triggers these alternate scopes.
    The adjective/adverb's actual reading and inflection, or an unchanged
    native noun/topic, establish the cut; no repaired word supplies it.
    The wider interpretation remains available.
    """
    from morphology import source_yoon_spans,tokenize as native_tokenize,dictionary_inflections
    from reading_segments import (native_adverbial_reading_cuts,native_adjective_adverbial_prefix,
                                  native_surface_nominal_heads,native_adnominal_modifier_parts,
                                  native_nominal_phrase_faces)
    targets=list(targets)
    for target in tuple(targets):
        if (target.boundary_kind not in ('lexical','ime_scope') or not target.anomalies
                or target.preserved_head or target.spelling):continue
        context=target.context;offset=target.context_start
        marks=[(a,b) for a,b in source_yoon_spans(context)
               if target.start<=offset+a and offset+b<=target.end]
        # Reuse an anomaly already attached to the original target. A
        # source boundary alone cannot mark a normal syllable as erroneous.
        prefix_edges=set(_native_marked_prefix_edges(context))
        marks.extend((a-offset,a-offset+1) for _,_,a,b in target.anomalies
            if target.start<=a<b<=target.end and a-offset in prefix_edges
            and target.source[a:a+1] in ('ゃ','ゅ','ょ'))
        if not marks:continue
        first=min(a for a,b in marks)
        onset=min(b-1 for a,b in marks)
        source_edges={edge for edge in _native_marked_prefix_edges(context) if edge<=onset}
        previous=next((part for part in native_tokenize(context)
            if part.end==target.start-offset and part.has_reading
            and part.pos in ('動詞','形容詞','名詞')),None)
        scope_start=target.start-offset
        if previous and target.end-offset-previous.start<=18:
            # A malformed original syllable can be the tail of the same
            # IME-split word. Keep the full readable native word as a
            # competing scope; physical and grammatical checks are shared.
            scope_start=previous.start
            wide=replace(target,start=offset+scope_start,boundary_kind='lexical')
            if wide not in targets:targets.append(wide)
        edges=set(native_adverbial_reading_cuts(context))
        # The next malformed syllable can swallow an actual modifier tail
        # into the preceding best-parse token. Certify the unchanged native
        # head and copula independently, then share that original boundary.
        for part in native_tokenize(context):
            if part.start>scope_start:break
            for edge in range(max(scope_start+1,part.start+2),first+1):
                if native_adnominal_modifier_parts(context[part.start:edge],allow_written=True):
                    edges.add(edge)
        for part in native_tokenize(context):
            if part.end>first:break
            if (part.pos=='形容詞' and part.has_reading
                    and native_adjective_adverbial_prefix(context[part.start:],part.end-part.start)):
                edge=part.end
                # The shared adjective proof is the same lemma's exact
                # native 連用テ接続. The verb-only te/ta helper cannot
                # certify it. Keep its original て with that modifier,
                # including when the following typo made IPADIC join てつ.
                if context[edge:edge+1]=='て':
                    edges.discard(edge)
                    edge+=1
                edges.add(edge)
        # A source genitive owns its left noun independently of the marked
        # right word. The next unknown onset can be parsed as a functional
        # token, so it need not be one of the native lexical parts above.
        owned_edges=set()
        for cut in range(1,first):
            if context[cut]!='の':continue
            # The best parse may absorb の and the unknown noun onset into
            # one token. Prove the unchanged whole left noun and actual
            # adnominal particle separately; the marked right word remains
            # unresolved and must still pass the shared replacement checks.
            head=context[:cut]
            if (native_nominal_phrase_faces(head) or native_surface_nominal_heads(head)):
                if any(pos.startswith('助詞,連体化,') and base=='の' and rd=='の'
                       for pos,form,base,rd in dictionary_inflections('の') or ()):
                    owned_edges.add(cut+1)
        from reading_segments import native_pronoun_case_ranges
        owned_edges.update(end for begin,end in native_pronoun_case_ranges(context) if end<=first)
        owned_edges.update(source_edges)
        edges.update(owned_edges)
        # The unchanged whole noun and native topic particle supply the
        # same nominal context even if the next malformed syllable made
        # the best parse absorb は/も into a noun. The existing spelling
        # anomaly must start immediately after that particle.
        cut=first-1
        if (cut>0 and context[cut] in ('は','も')
                and native_surface_nominal_heads(context[:cut])
                and any(pos.startswith('助詞,係助詞,') and rd==context[cut]
                        for pos,form,base,rd in dictionary_inflections(context[cut]) or ())):
            edges.add(first)
        for edge in sorted(edges):
            if ((edge<=first or edge in source_edges) and offset+edge<target.end
                    and (scope_start<edge or edge in owned_edges
                         and target.end-offset-edge<=18)):
                narrow=replace(target,start=offset+edge,boundary_kind='lexical')
                if narrow not in targets:targets.append(narrow)
    return targets



def _native_marked_nominal_member_targets(targets):
    """An intact right member owns its original coordinating boundary.

    The marked left member remains unknown. This supplies only its source
    range, never the missing reading, meaning, or permission to replace it.
    """
    from morphology import tokenize as native_tokenize
    from reading_segments import native_surface_nominal_heads
    targets=list(targets)
    for target in tuple(targets):
        if (target.boundary_kind not in ('lexical','ime_scope') or not target.structural
                or not target.anomalies or target.preserved_head or target.spelling
                or target.text[:1] not in ('ゃ','ゅ','ょ')):continue
        offset=target.context_start
        for link in native_tokenize(target.context):
            cut=offset+link.start
            if (link.pos!='助詞' or link.pos_sub!='並立助詞' or not link.has_reading
                    or not target.start+1<cut<target.end):continue
            # Keep the original written tail with the anomalous onset.
            if not all('一'<=c<='鿿' for c in target.source[target.start+1:cut]):continue
            if not any(a==target.start and a<b<=cut for _,_,a,b in target.anomalies):continue
            right=target.source[offset+link.end:target.end]
            if not native_surface_nominal_heads(right):continue
            narrow=replace(target,end=cut,boundary_kind='lexical',
                following=target.source[cut:target.context_end])
            if narrow not in targets:targets.append(narrow)
    return targets


def targets_for_line(line, tokenize, store, dictionary, _keep_completed=True,
                     input_method='kana'):
    """候補生成前に、異様を含む文節と、その接続を判断する文脈を固定する。"""
    import oddness
    from morphology import original_spelling_facts
    source_spelling=original_spelling_facts(line)
    targets = []
    for f in source_spelling:
        lo=0;hi=len(line)
        for sep in _SEPARATOR.finditer(line):
            if sep.end()<=f.start:lo=sep.end()
            elif sep.start()>=f.end:
                hi=sep.start();break
        targets.append(RepairTarget(line,f.start,f.end,lo,hi,
            ((f.original[:-1],f.original[-1],f.change_start,f.change_start+1),),
            True,line[f.end:hi],'spelling','',(f,)))
    if '素' in line:
        from semantic_roles import unadorned_action_conflicts
        for left,right,start,end in unadorned_action_conflicts(line,list(tokenize(line))):
            lo,hi=_source_clause_bounds(line,start,end)
            targets.append(RepairTarget(line,start,end,lo,hi,
                ((left,right,start,end),),True,line[end:hi],'lexical'))
    from numeric_mark_repair import frames as numeric_mark_frames
    for frame in numeric_mark_frames(line):
        targets.append(RepairTarget(line,frame['start'],frame['end'],frame['lo'],frame['hi'],
            (('意味接続','数値に続く未成立の助数詞表記',frame['start'],frame['end']),),
            True,'','numeric_mark_counter',candidate_surface=frame['surface'],
            candidate_reading=frame['reading'],semantic_conflict=True))
    from particle_frames import broken_accusative_adverb_frames
    for frame in broken_accusative_adverb_frames(line):
        start,end=frame['start'],frame['end']
        lo,hi=_source_clause_bounds(line,start,end)
        targets.append(RepairTarget(line,start,end-1,lo,hi,
            (('品詞文法','物の目的語に動作がない',start,end),),
            True,line[end-1:hi],'lexical'))
    from particle_frames import unlinked_written_suru_frames
    for frame in unlinked_written_suru_frames(line):
        start,end=frame['start'],frame['end']
        lo,hi=_source_clause_bounds(line,start,end)
        targets.append(RepairTarget(line,start,end,lo,hi,
            (('品詞文法','終止動詞とする述語の直結',start,end),),
            True,line[end:hi],'lexical'))
    from particle_frames import unlinked_past_predicate_frames
    for frame in unlinked_past_predicate_frames(line):
        start,end=frame['start'],frame['end']
        lo,hi=_source_clause_bounds(line,start,end)
        targets.append(RepairTarget(line,start,end,lo,hi,
            (('品詞文法','過去形と終止述語の直結',start,end),),
            True,line[end:hi],'lexical'))
    from particle_frames import broken_nominal_te_frames
    for frame in broken_nominal_te_frames(line):
        start,end=frame['start'],frame['end']
        lo,hi=_source_clause_bounds(line,start,end)
        # Keep the actual following て as context, exactly as for a
        # malformed written inflection. The prior source frame owns it.
        targets.append(RepairTarget(line,start,end-1,lo,hi,
            (('品詞文法','原文の名詞とての接続',start,end),),
            True,line[end-1:hi],'lexical'))
    from particle_frames import closed_question_frames
    for frame in closed_question_frames(line):
        lo=next((m.end() for m in reversed(list(_SEPARATOR.finditer(line[:frame['start']])))),0)
        hi=frame['context_end']
        targets.append(RepairTarget(line,frame['start'],frame['end'],lo,hi,
            (('助詞接続','疑問文末の名詞',frame['start'],frame['end']),),
            True,'','question_particle',frame['aux']))
    from particle_frames import adnominal_topic_frames
    for frame in adnominal_topic_frames(line):
        start,end=frame['start'],frame['end']
        lo=next((m.end() for m in reversed(list(_SEPARATOR.finditer(line[:start])))),0)
        hi=next((m.start() for m in _SEPARATOR.finditer(line) if m.start()>=end),len(line))
        targets.append(RepairTarget(line,start,end,lo,hi,
            (('助詞接続','連体形に名詞がない',start,end),),True,line[end:hi],'particle_adverbial'))
    # 48-AMV: punctuation affects native tokenization. Determine the
    # original marks once, as the visible purple does, then translate
    # contained facts into each editing scope. Re-parsing a stripped
    # clause must not erase an already established source anomaly.
    from ime_nominal_head import frames as nominal_head_frames
    for frame in nominal_head_frames(line):
        lo,hi=_source_clause_bounds(line,frame['start'],frame['end'])
        for surface in frame['candidates']:
            targets.append(RepairTarget(line,frame['start'],frame['end'],lo,hi,
                (('品詞文法','受け先のない格と連体詞',frame['start'],frame['evidence_end']),),
                True,line[frame['end']:hi],'nominal_resegmentation',
                candidate_surface=surface,candidate_reading=frame['reading']))
    from ime_nominal_head import split_question_noun_frames
    for frame in split_question_noun_frames(line):
        lo,hi=_source_clause_bounds(line,frame['start'],frame['end'])
        for surface in frame['candidates']:
            targets.append(RepairTarget(line,frame['start'],frame['end'],lo,hi,
                (('品詞文法','疑問と名詞内部のかなの区切り',frame['start'],frame['evidence_end']),),
                True,line[frame['end']:hi],'nominal_resegmentation',
                candidate_surface=surface,candidate_reading=frame['reading']))
    from familiar_nominal import conditional_reference_frames
    for frame in conditional_reference_frames(line):
        lo,hi=_source_clause_bounds(line,frame['start'],frame['end'])
        for surface in frame['candidates']:
            targets.append(RepairTarget(line,frame['start'],frame['end'],lo,hi,
                (('意味接続','条件と程度比較の状況指示',frame['start'],frame['evidence_end']),),
                True,line[frame['end']:hi],'nominal_resegmentation',
                candidate_surface=surface,candidate_reading=frame['reading']))
    from context_meaning import anomalous_frames,candidates as meaning_candidates
    for frame in anomalous_frames(line):
        lo,hi=_source_clause_bounds(line,frame['start'],frame['end'])
        for surface in meaning_candidates(frame):
            targets.append(RepairTarget(line,frame['start'],frame['end'],lo,hi,
                (('意味接続',frame['kind'],frame['evidence_start'],frame['evidence_end']),),
                True,line[frame['end']:hi],'meaning_context',
                candidate_surface=surface,candidate_reading=frame['reading']))
    from ime_compound_contrast import frames as compound_frames
    for frame in compound_frames(line):
        lo,hi=_source_clause_bounds(line,frame['start'],frame['end'])
        for surface in frame['candidates']:
            targets.append(RepairTarget(line,frame['start'],frame['end'],lo,hi,
                (('IME逆読み','接尾語だけの未登録複合',frame['start'],frame['end']),),
                True,line[frame['end']:hi],'nominal_resegmentation',
                candidate_surface=surface,candidate_reading=frame['reading']))
    from relative_key_repair import frames as relative_frames
    for frame in relative_frames(line):
        lo,hi=_source_clause_bounds(line,frame['start'],frame['end'])
        targets.append(RepairTarget(line,frame['start'],frame['end'],lo,hi,
            (('品詞文法','名詞を修飾する述語の前に受け先のない格',frame['start'],frame['end']),),
            True,line[frame['end']:hi],'relative_predicate'))
    from process_familiarity import frames as familiarity_frames
    for frame in familiarity_frames(line):
        lo=frame.get('evidence_start',frame['start']);hi=frame.get('evidence_end',frame['end'])
        targets.append(RepairTarget(line,frame['start'],frame['end'],lo,hi,
            (('意味接続',frame.get('reason','反復する自然変化と一般的な程度変化の比較'),frame['start'],frame['end']),),
            True,line[frame['end']:hi],'unfamiliar_process'))
    source_parts=list(tokenize(line))
    if input_method == 'kana' and dictionary is not None:
        from ime_question_contrast import bare_question_candidate
        from ime_lexical_contrast import split_colloquial_candidate
        from ime_postevent_contrast import symbolic_result_candidate
        # Each tab/arrow field is independent. Never make a candidate for an
        # earlier field from the answer or key text in a later one.
        fields=[];lo=0
        for separator in COLUMN_SEPARATOR.finditer(line):
            if lo<separator.start():fields.append((lo,separator.start()))
            lo=separator.end()
        if lo<len(line):fields.append((lo,len(line)))
        for lo,hi in fields:
            field=line[lo:hi]
            parts=[t[:3]+(t[3]-lo,t[4]-lo)+t[5:] for t in source_parts
                   if lo<=t[3] and t[4]<=hi]
            event=symbolic_result_candidate(field,parts)
            if event:
                end,surface,reading=event
                targets.append(RepairTarget(line,lo,lo+end,lo,hi,
                    (('意味接続','返す動作と記号表記の結果',lo,lo+end),),
                    True,line[lo+end:hi],'ime_postevent',
                    candidate_surface=surface,candidate_reading=reading))
            question=bare_question_candidate(field,parts)
            if question:
                offset,surface,reading=question
                start=lo+offset
                targets.append(RepairTarget(line,start,start+1,lo,hi,
                    (('品詞文法','疑問主語の後に未完の名詞化',start,start+1),),
                    True,line[start+1:hi],'ime_question',
                    candidate_surface=surface[offset:offset+1],
                    candidate_reading=reading[-1:]))
            proposal=split_colloquial_candidate(field,parts)
            if proposal:
                end,surface,reading,anomaly_end=proposal
                targets.append(RepairTarget(line,lo,lo+end,lo,lo+end,
                    (('品詞文法','独立動詞の直結',lo,lo+anomaly_end),),
                    True,'','ime_colloquial',candidate_surface=surface,
                    candidate_reading=reading))
    from particle_frames import interrogative_extent_frames
    for frame in interrogative_extent_frames(line):
        lo,hi=_source_clause_bounds(line,frame['start'],frame['end'])
        targets.append(RepairTarget(line,frame['start'],frame['end'],lo,hi,
            (('意味接続','思考する内容と具体物の道具格',frame['start'],frame['end']),),True,
            line[frame['end']:hi],'interrogative_extent',
            candidate_surface=frame['surface'],candidate_reading=frame['reading']))
    from particle_frames import converted_suru_connection_frames
    for frame in converted_suru_connection_frames(line):
        a,b=frame['verb_start'],frame['verb_end']
        lo,hi=_source_clause_bounds(line,a,b)
        targets.append(RepairTarget(line,a,b,lo,hi,
            (('品詞文法','動作名詞と接続語の間の同音名詞',a,frame['end']),),
            True,line[b:hi],'suru_connection',
            candidate_surface=frame['surface'],candidate_reading=frame['reading']))
    source_odd=oddness.is_odd_run(line,tokenize,with_spans=True,
        store=store,dict_index=dictionary,complete_line=True, preserve_unknown_source=True)
    targets.extend(_marked_detached_mark_action_targets(
        line,source_parts,source_odd))
    targets.extend(_marked_leading_mark_noun_targets(
        line,source_parts,source_odd))
    source_strong=oddness.is_odd_run(line,tokenize,with_spans=True,
        store=store,dict_index=dictionary,skip_join=True,complete_line=True, preserve_unknown_source=True) if source_odd else ()
    # A recorded whole commit already proves which reading produced this
    # source. Its independently anomalous field may be repaired as a whole,
    # preserving the other word readings and allowing their contextual kanji.
    # Actual commit evidence is not a requirement to repeat today's IME query.
    from analysis_work import occurrence_readings
    for lo,hi in dict.fromkeys(_source_clause_bounds(line,a,b) for _,_,a,b in source_odd):
        readings=occurrence_readings(line,lo,hi)
        if not readings:continue
        facts=tuple(row for row in source_odd if lo<=row[2]<row[3]<=hi)
        if facts:targets.append(RepairTarget(line,lo,hi,lo,hi,facts,True,'','ime_scope'))
    inverse_marks=tuple(row for row in source_odd if row[0]=='IME逆読み')
    targets.extend(_marked_unknown_prefix_intrusion_targets(
        line,source_parts,inverse_marks,dictionary))
    targets.extend(_marked_ime_prefix_native_verb_targets(
        line,source_parts,inverse_marks))
    # A whole-field inverse clue does not independently mark every word.
    for _left,_right,start,end in inverse_marks:
        lo,hi=_source_clause_bounds(line,start,end)
        # The IME clue identifies the edit span, while untouched source
        # arguments to its left still constrain candidate meaning.
        target=RepairTarget(line,start,end,lo,hi,((_left,_right,start,end),),
                            True,line[end:hi],'ime_scope')
        if target not in targets:targets.append(target)
    import pos_grammar
    source_grammar=pos_grammar.odd_kana_spans(line,dictionary,store)
    for start,end in pos_grammar.closed_subject_topic_spans(line):
        targets.append(RepairTarget(line,start,end-1,start,end,
            (('品詞文法','閉じた主語と話題に述語がない',start,end),),True,
            line[end-1:end],'nominal_topic'))
    for start,end,cut,reading in pos_grammar.unexplained_shifted_predicate_tails(line):
        lo,hi=_source_clause_bounds(line,start,end)
        targets.append(RepairTarget(line,start,end,lo,hi,
            (('品詞文法','未説明の小文字語尾',cut,end),),True,line[end:hi],
            'auxiliary_connection',line[start:cut]))
    # A completed field's source grammar mark belongs to its original whole
    # reading. Keep that field together when the one bad key has changed IME
    # segmentation in several words. No candidate or answer creates the mark.
    for start,end in pos_grammar._completed_kana_attachment_spans(line):
        facts=tuple(row for row in source_odd if row[2]<=start and end<=row[3])
        if facts:
            target=RepairTarget(line,start,end,start,end,facts,True,'','lexical')
            if target not in targets:targets.append(target)
    for start,end in pos_grammar._completed_orphan_attachment_spans(line):
        facts=tuple(row for row in source_odd if row[2]<=start and end<=row[3])
        if facts:
            target=RepairTarget(line,start,end,start,end,facts,True,'','lexical')
            if target not in targets:targets.append(target)
    from particle_frames import nominalized_existential_case_frames
    for frame in nominalized_existential_case_frames(line):
        a,b=frame['case_start'],frame['case_end'];lo,hi=_source_clause_bounds(line,a,b)
        targets.append(RepairTarget(line,a,b,lo,hi,
            (('名詞化の接続','存在述語の格',frame['start'],frame['end']),),True,
            line[b:hi],'nominalized_subject'))
    completed_boundaries = set()
    boundaries = [0]
    for left,right in _source_separator_ranges(line):
        boundaries.extend((left,right))
    boundaries.append(len(line))
    for lo, hi in zip(boundaries[::2], boundaries[1::2]):
        # Arrow/column padding belongs to the separator, not the phrase proof.
        while lo < hi and line[lo].isspace():lo += 1
        while lo < hi and line[hi-1].isspace():hi -= 1
        clause = line[lo:hi]
        if not clause:
            continue
        from particle_frames import interrupted_particle_frames
        for frame in interrupted_particle_frames(clause,dictionary):
            start,end=lo+frame['start'],lo+frame['end']
            targets.append(RepairTarget(line,start,end,lo,hi,
                (('助詞接続',frame.get('reason','話題に挟まった注意名詞'),start,end),),
                True,line[end:hi],'particle_intrusion',clause[frame['start']:frame['case_start']]))
        parts=[(t[0],t[1],t[2],t[3]-lo,t[4]-lo,*t[5:]) for t in source_parts
               if lo<=t[3]<t[4]<=hi]
        field_odd=[(a,b,start-lo,end-lo) for a,b,start,end in source_odd if lo<=start<end<=hi]
        odd=[row for row in field_odd if row[0]!='IME逆読み']
        # Existing local evidence owns its lexical scopes. When the inverse
        # is the only source anomaly, preserve the established lexical
        # projections as alternatives to its full-field candidate.
        inverse_only=not odd
        if inverse_only:odd=field_odd
        grammar_spans=[(start-lo,end-lo) for start,end in source_grammar if lo<=start<end<=hi]
        # A native inflection boundary qualifies the same pre-existing
        # kana grammar mark for ordinary lexical/auxiliary repair as well.
        # Unknown words and mere incomplete readings supply no such gate.
        # Share the actual native boundary, not the whole purple kana run.
        # A broader mark must not swallow an already proved preceding clause.
        grammar_anomalies=[('品詞文法','原文の活用境界',start,end)
            for start,end in _kana_nominal_boundary_spans(parts)
            if any(a<=start and end<=b for a,b in grammar_spans)
            and not any(a<=start and end<=b for _,_,a,b in odd)]
        odd.extend(grammar_anomalies)
        # An already marked compound retains its attested nominal head.
        # Kana tokenization may have mistaken the preceding noun for a verb;
        # a known suffix alone never declares that source anomalous.
        if odd:
            from reading_segments import native_nominal_tail_heads,native_nominal_tail_spellings
            heads=native_nominal_tail_heads(clause)
            if _is_input_reading(clause) and native_nominal_tail_spellings(clause,heads):heads=()
            facts=tuple((a,b,lo+start,lo+end) for a,b,start,end in odd
                        if any(start<cut for cut,face,reading in heads))
            if facts:
                targets.append(RepairTarget(line,lo,hi,lo,hi,facts,True,'','nominal_field'))
        targets.extend(_native_kana_targets(line,lo,hi,tokenize,store,dictionary,odd,grammar_spans))
        targets.extend(_comma_native_kana_targets(line,lo,hi,tokenize,store,dictionary,odd,grammar_spans))
        targets.extend(_marked_case_leading_intrusion_targets(
            line,lo,hi,parts,odd,targets))
        targets.extend(_marked_case_leading_suru_intrusion_targets(
            line,lo,hi,parts,odd,targets))
        targets.extend(_marked_case_numeric_suru_targets(
            line,lo,hi,parts,odd))
        targets.extend(_marked_case_auxiliary_mark_shift_targets(
            line,lo,hi,parts,odd))
        targets.extend(_marked_suru_pair_targets(
            line,lo,hi,parts,odd))
        targets.extend(_marked_suru_extra_noun_targets(
            line,lo,hi,parts,odd))
        targets.extend(_marked_native_verb_kana_tail_targets(
            line,lo,hi,parts,odd))
        targets.extend(_marked_base_verb_noun_te_targets(
            line,lo,hi,parts,grammar_spans))
        targets.extend(_marked_object_tail_before_noun_targets(
            line,lo,hi,parts,odd,grammar_spans))
        targets.extend(_te_suffix_before_motion_targets(
            line,lo,hi,parts))
        targets.extend(_marked_nominal_de_before_kara_targets(
            line,lo,hi,parts,odd))
        targets.extend(_marked_nominal_particle_before_kara_targets(
            line,lo,hi,parts,odd))
        targets.extend(_source_sahen_connective_intrusion_targets(
            line,lo,hi,parts))
        targets.extend(_marked_pre_suru_action_targets(
            line,lo,hi,parts,odd,grammar_spans))
        targets.extend(_source_nominal_sahen_intrusion_targets(
            line,lo,hi,parts))
        targets.extend(_marked_nonindependent_sahen_past_targets(
            line,lo,hi,parts,grammar_spans))
        targets.extend(_marked_terminal_noun_after_polite_past_targets(
            line,lo,hi,parts,grammar_spans))
        targets.extend(_marked_past_before_sahen_targets(
            line,lo,hi,parts,tuple(dict.fromkeys(grammar_spans+[
                (a,b) for kind,reason,a,b in odd if kind=='品詞文法']))))
        targets.extend(_marked_double_native_polite_tail_targets(
            line,lo,hi,parts,grammar_spans))
        targets.extend(_marked_terminal_polite_connective_targets(
            line,lo,hi,parts,grammar_spans))
        targets.extend(_source_adnominal_particle_targets(
            line,lo,hi,parts,grammar_spans,store))
        targets.extend(_source_one_key_before_adverbial_targets(
            line,lo,hi,parts,grammar_spans))
        targets.extend(_source_destination_connective_targets(
            line,lo,hi,parts,grammar_spans))
        targets.extend(_source_one_key_object_tail_targets(
            line,lo,hi,parts,grammar_spans))
        targets.extend(_marked_single_key_between_sahen_actions_targets(
            line,lo,hi,parts,grammar_spans))
        targets.extend(_marked_stray_key_before_next_object_targets(
            line,lo,hi,parts,grammar_spans))
        targets.extend(_marked_stray_to_before_sahen_past_targets(
            line,lo,hi,parts,grammar_spans))
        targets.extend(_marked_interrupted_polite_action_targets(
            line,lo,hi,parts,odd))
        targets.extend(_marked_converted_sahen_past_targets(
            line,lo,hi,parts,odd))
        targets.extend(_marked_projected_polite_past_targets(
            line,lo,hi,parts,odd,tokenize))
        targets.extend(_marked_unsplit_polite_action_after_case_targets(
            line,lo,hi,parts,odd))
        targets.extend(_marked_action_before_owned_object_targets(
            line,lo,hi,odd,grammar_spans))
        targets.extend(_marked_terminal_ime_tail_targets(
            line,lo,hi,parts,odd))
        targets.extend(_marked_kana_past_action_after_object_targets(
            line,lo,hi,parts,grammar_spans))
        targets.extend(_marked_attributive_verb_noun_object_targets(
            line,lo,hi,parts,odd))
        targets.extend(_marked_basic_verb_suru_targets(
            line,lo,hi,parts,odd))
        targets.extend(_marked_adnominal_kana_object_targets(
            line,lo,hi,parts,odd,grammar_spans))
        targets.extend(_marked_past_kana_object_targets(
            line,lo,hi,parts,odd))
        if not odd:
            targets.extend(_marked_written_verb_tail_targets(
                line,lo,hi,parts,grammar_spans))
            targets.extend(_marked_imperative_connective_targets(
                line,lo,hi,parts,grammar_spans))
        # Keep the original inflection and grammar proof local. A separate
        # anomaly can coexist with this additional projection only when the
        # original complete noun/object boundary independently owns it.
        # Otherwise the existing wider search keeps its original scope.
        for target in _marked_nonfinite_connective_intrusion_targets(
                line,lo,hi,parts,grammar_spans):
            if any(lo+a<target.end and target.start<lo+b
                   for _,_,a,b in odd):
                continue
            if odd:
                from reading_segments import native_object_predicate_contexts
                if not any(faces and lo+cut==target.start
                           for begin,cut,faces in native_object_predicate_contexts(
                               clause,allow_written_predicate=True)):
                    continue
            targets.append(target)
        from mark_usage import unattached_positions,transposed_mark_readings,transposed_mark_connection
        mark_positions=frozenset(unattached_positions(clause))
        from morphology import HAS_JANOME
        for position in sorted(mark_positions) if HAS_JANOME else ():
            if any(transposed_mark_connection(clause,position,position+2,reading)
                   for reading in transposed_mark_readings(clause,position)):
                targets.append(RepairTarget(line,lo+position,lo+position+2,lo,hi,
                    (('記号','原文で結合できない濁点・半濁点',lo+position,lo+position+1),),
                    True,clause[position+2:],'mark_transposition'))
        def separator(token):
            from pos_grammar import is_functional_noun
            # A one-kana particle cannot sever the onset of the following
            # small kana inside this already anomalous lexical range.
            if (len(token[0])==1 and _is_reading(_input_kana(token[0]))
                    and token[4]<len(clause) and clause[token[4]] in 'ゃゅょ'):
                return False
            if token[1].startswith('助詞:接続助詞') or is_functional_noun(token,dictionary_alternative=True):
                return True
            return (token[1].startswith('記号') and not (
                token[3]<token[4] and all(i in mark_positions for i in range(token[3],token[4]))))
        # 48-ACC: the kana grammar has already produced the purple mark.
        # Reuse that same judgment; a native action seam only limits the
        # repair span and does not itself declare the source anomalous.
        if 'して' in clause:
            from reading_segments import native_action_note_seams
            seams=native_action_note_seams(clause,parts)
            if seams:
                from corrector import _kana_run_is_odd_by_grammar
                if _kana_run_is_odd_by_grammar(clause,dictionary,store):
                    for cut in seams:
                        targets.append(RepairTarget(line,lo,lo+cut,lo,hi,
                            (('品詞文法','未説明のかな操作メモ',lo,hi),),
                            True,clause[cut:],'kana_action_note'))
        if not odd:
            continue
        strong={(a,b,start-lo,end-lo) for a,b,start,end in source_strong if lo<=start<end<=hi}
        strong.update(grammar_anomalies)
        if inverse_only:strong.update(row for row in field_odd if row[0]=='IME逆読み')
        from semantic_roles import conflicting_nominal_compounds
        meaning_boundaries={row[2] for row in conflicting_nominal_compounds(clause,parts)}
        from semantic_roles import conflicting_object_predicates,subject_only_predicate_spans
        predicate_frames=list(dict.fromkeys(conflicting_object_predicates(clause,parts)
            +subject_only_predicate_spans(clause,parts)))
        predicate_boundaries={row[2] for row in predicate_frames}
        # A source semantic conflict owns the native action word itself.
        # Its intact suru/relative tail remains context even before a noun.
        # The wider lexical interpretation below remains a competing option.
        for noun,predicate,a,b in predicate_frames:
            targets.append(RepairTarget(line,lo+a,lo+b,lo,hi,
                ((noun,predicate,lo+a,lo+b),),True,clause[b:],'lexical',
                semantic_conflict=True))
        # A marked nominal split can make an internal kana look like a
        # topic particle. Keep the whole original reading as an alternative
        # only when its written noun + auxiliary is itself invalid.
        for index in range(len(parts)-3):
            head,case,noun,aux=parts[index:index+4]
            if (not head[1].startswith('名詞:一般')
                    or not case[1].startswith('助詞:係助詞')
                    or not noun[1].startswith('名詞:一般')
                    or any(parts[j][4]!=parts[j+1][3] for j in range(index,index+3))
                    or not oddness.volitional_auxiliary_mismatch(noun,aux)
                    or not any(start<=head[3] and noun[4]<=end
                               for _,_,start,end in strong)):
                continue
            begin,finish=head[3],aux[4]
            facts=tuple((a,b,lo+start,lo+end) for a,b,start,end in odd
                        if start<finish and begin<end)
            full=RepairTarget(line,lo+begin,lo+finish,lo,hi,facts,
                              True,clause[finish:],'lexical',
                              require_ime_first_roundtrip=True)
            if full not in targets:targets.append(full)
        for a, b, start, end in odd:
            hit = [i for i, t in enumerate(parts) if t[3] < end and start < t[4]]
            if not hit:
                continue
            first, last = hit[0], hit[-1]
            # 異様な格助詞の連続では、先の助詞は文節境界、後の助詞は
            # 誤って分割された語頭かもしれない。正しい「には」等は odd にない。
            if (first < last and _case_boundary(parts[first])
                    and _case_boundary(parts[first+1])
                    and any(x[2] == parts[first][3] and x[3] == parts[first+1][4]
                            for x in strong)):
                first += 1
            while (first and not _case_boundary(parts[first-1])
                   and not _literal_boundary(parts[first-1])
                   and not separator(parts[first-1])):
                if parts[first-1][4] != parts[first][3]:
                    break
                # The shared meaning judgment identifies the preceding noun
                # as context; reopening it would discard that very evidence.
                if parts[first][3] in meaning_boundaries or parts[first][3] in predicate_boundaries:
                    break
                # A completed modifier before the anomaly remains in context.
                # Do not retreat across it and then trim at an earlier auxiliary,
                # which would discard the anomalous noun entirely.
                if (_keep_completed and parts[first-1][4]<=start
                        and not (parts[first][1].startswith('助詞:終助詞')
                            and not any(parts[first][3]<=j<=parts[first][4] for j in mark_positions))
                        and _completed_predicate_token(parts[first-1])):
                    completed_boundaries.add(lo+parts[first-1][4])
                    break
                first -= 1
            # 接続助詞/格助詞より前の語は途中の文字種境界で切らない。
            while last+1 < len(parts):
                nxt = parts[last+1]
                if (parts[last][4] != nxt[3] or _case_boundary(nxt) or _literal_boundary(nxt)
                        or separator(nxt)):
                    break
                last += 1
            # 隣の異様な接続を、別の短い対象を作ることで切り捨てない。
            if (first >= 2 and _case_boundary(parts[first-1])
                    and _case_boundary(parts[first-2])
                    and any(x[2] == parts[first-2][3] and x[3] == parts[first-1][4]
                            for x in strong)):
                first -= 1
            begin, finish = parts[first][3], parts[last][4]
            # 読む範囲と検査する範囲を分ける。するの活用は原文のまま検査に残す。
            for i in range(first+1, last+1):
                t = parts[i]
                if (t[0] in ('し', 'する', 'すれ', 'せよ') and t[1].startswith('動詞')
                        and t[3] >= start and (i == last or
                            parts[i+1][1].startswith(('助詞', '助動詞')))):
                    finish = t[3]
                    break
                # A malformed auxiliary before masu is part of the repair,
                # not a sound boundary that can discard the source anomaly.
                if (t[1].startswith('助動詞')
                        and not (i<last and oddness.polite_aux_mismatch(t,parts[i+1]))
                        and (parts[i-1][1].startswith(('動詞', '形容詞'))
                         or t[0] in ('ます', 'まし', 'ませ', 'ましょ', 'です', 'でし', 'でしょ'))):
                    finish = t[3]
                    break
            # 異様の印が接続の両側を含んでも、読む本文は格助詞を越えない。
            for i in range(first+1, last+1):
                if _case_boundary(parts[i]) or separator(parts[i]):
                    finish = min(finish, parts[i][3])
                    break
            if (_case_boundary(parts[first]) and first < last
                    and parts[first+1][5] and parts[first+1][1].startswith('動詞')
                    and parts[first+1][6].startswith('連用') and first+2 < len(parts)
                    and parts[first+2][1].startswith('助動詞')):
                finish = min(finish, parts[first][4])
            # 未知のかな語が格助詞まで一語に飲み込まれても、その後ろの
            # 既知の述語は読み直す本文ではなく検査の文脈に残す。
            for i in range(first, last):
                t, nxt = parts[i], parts[i+1]
                if (not t[5] and _is_input_reading(_input_kana(t[0])) and len(t[0]) >= 2
                        and t[0][-1] in ('を', 'に', 'へ', 'が', 'と')
                        and nxt[5] and (nxt[1].startswith(('動詞', '形容詞')) or
                            (nxt[1].startswith('名詞:サ変接続') and i+2 < len(parts)
                             and parts[i+2][0] in ('し', 'する', 'すれ')
                             and parts[i+2][1].startswith('動詞')))):
                    finish = min(finish, t[4]-1)
            # The malformed spelling can swallow a genitive or copula.
            # Keep only a boundary inside an unknown token, following the
            # already established spelling mark. The normal suffix remains
            # in context and every candidate still passes validate().
            from morphology import source_yoon_spans
            spelling_edges=source_yoon_spans(clause)
            if spelling_edges:
                from pos_grammar import _NOUN_PRED
                copulas={piece for piece,state in _NOUN_PRED if state in ('END','TA')}
                for i in range(first,last+1):
                    t=parts[i]
                    if t[5]:continue
                    if (i+1<len(parts) and t[0].endswith('の') and parts[i+1][5]
                            and parts[i+1][1].startswith('名詞') and t[4]==parts[i+1][3]
                            and any(begin<=a<b<=t[4]-1 for a,b in spelling_edges)):
                        finish=min(finish,t[4]-1)
                    for tail in copulas:
                        cut=t[4]-len(tail)
                        if (t[0].endswith(tail) and t[3]<cut
                                and any(begin<=a<b<=cut for a,b in spelling_edges)):
                            finish=min(finish,cut)
            # 48-AAR: the original all-kana action may be split into
            # a short noun and a connective by the analyzer. Preserve its
            # exact ordinary reading and modern ending before the bad mark;
            # candidate generation still starts from the remaining anomaly.
            local_marks=[p for p in mark_positions if begin<p<finish]
            if _keep_completed and local_marks:
                from reading_segments import completed_sahen_reading
                edges=[t[4] for t in parts if begin<t[4]<min(local_marks)]
                for edge in sorted(edges,reverse=True):
                    if completed_sahen_reading(clause[begin:edge],allow_nonpolite=True):
                        completed_boundaries.add(lo+edge)
                        begin=edge
                        break
            untrimmed_begin = begin
            # 文頭の時点・数量等の副詞的名詞は後続の未知語と一語にしない。
            if (first < last and parts[first][1].startswith('名詞:副詞可能')
                    and parts[first][5]):
                begin = parts[first+1][3]
            # 引用記号自体は候補の綴りに含めず、原文のまま外へ残す。
            while begin < finish and clause[begin] in "`\"'「『（(【[":
                begin += 1
            while begin < finish and clause[finish-1] in "`\"'」』）)】]":
                finish -= 1
            structural = any(x[2] < finish and begin < x[3] for x in strong)
            # 原文で活用接続が異様なら、漢字2字の語も調べる。
            # 読みの長さと漢字の文字数を取り違えて入口を落とさない。
            single_polite=(finish-begin==1 and structural and any(
                parts[i-1][3]==begin and parts[i][3]==finish
                and (oddness.polite_aux_mismatch(parts[i-1],parts[i])
                     or oddness.completed_tsu_aux_mismatch(parts[i-1],parts[i]))
                for i in range(1,len(parts))))
            if (not (1 <= finish-begin <= 18) or finish <= start
                    or (finish-begin==1 and not single_polite)
                    or (finish-begin==2 and not structural)):
                continue
            text = clause[begin:finish]
            anomalies = tuple((x, y, lo+s, lo+e) for x, y, s, e in odd
                              if s < finish and begin < e)
            # 48-AMN / GPT-6 Astra / 2026-09-20: an already anomalous
            # kana word can occupy the same plain object slot as a broken
            # request tail. Share the optional nominal interpretation before
            # the old inflection-only gate discards that source range.
            # The original anomaly, native unchanged predicate, intact check
            # and positive candidate fit all remain the existing contracts.
            if _is_input_reading(text):
                for nominal in _unexplained_nominal_source_targets(line,lo,hi,lo+begin,anomalies):
                    if nominal not in targets:targets.append(nominal)
            # 全かなでも、活用の接続が崩れた範囲は同じ検査へ通す。
            # 語の途中で切れたという印だけで従来の語内探索を置き換えない。
            if (not any('一' <= c <= '鿿' or 'ァ' <= c <= 'ヶ' for c in text)
                    and not _kana_grammar_boundary(parts, begin, finish)
                    # An actual accusative owns the following broken action.
                    # A collision elsewhere (e.g. a connective tail) does
                    # not establish that same lexical action boundary.
                    and not (first>0 and parts[first-1][0]=='を'
                        and parts[first-1][1].startswith('助詞:格助詞')
                        and _case_boundary(parts[first]) and parts[first][3]==begin
                        and any(a==parts[first-1][3] and b==parts[first][4]
                                for _,_,a,b in strong))
                    and not any(begin<=i<finish for i in mark_positions)
                    and not any(begin<=a<b<=finish for a,b in spelling_edges)):
                continue
            # 見慣れない普通名詞の連接だけなら、従来の証拠を持つ経路に委ねる。
            relevant = [t for t in parts if t[3] < finish and begin < t[4]]
            if not structural and all(t[5] and t[1].startswith('名詞') for t in relevant):
                continue
            following = clause[finish:]
            target = RepairTarget(line, lo+begin, lo+finish, lo, hi,
                                  anomalies, structural, following,
                                  'nominal_meaning' if begin in meaning_boundaries else 'lexical',
                                  semantic_conflict=any(begin==a and finish>=b
                                      for _,_,a,b in predicate_frames))
            # A one-key-late Shift window can leave the yoon key large
            # and the following vowel small. Its original i-row onset and
            # native prefix own the same competing scope as a small yoon;
            # both actual Shift events still need ordinary final proof.
            shifted_yoon=(structural and len(text)>=2
                and text[0] in 'やゆよ' and text[1] in 'ぁぃぅぇぉ')
            if shifted_yoon:
                from semantic_roles import case_argument_before
                # A positively proved original noun/case owns that seam.
                # A late Shift window alone cannot swallow its case key.
                shifted_yoon=not case_argument_before(clause,begin,tokenize)
            joined_yoon=((text[:1] in ('ゃ','ゅ','ょ') or shifted_yoon) and first
                and parts[first-1][4]==begin
                and parts[first-1][0][-1:] in 'きぎしじちぢにひびぴみり')
            if not joined_yoon and target not in targets:
                targets.append(target)
            # A small yoon at this edge cannot start a word. IME may have
            # mislabeled its preceding base as a particle; preserve both the
            # original range and the joined range for the common validator.
            if joined_yoon:
                starts=[parts[first-1][3]]
                if (first>=2 and parts[first-2][4]==starts[0]
                        and parts[first-2][1].startswith('接頭詞')
                        and _is_input_reading(_input_kana(parts[first-2][0]))):
                    starts.append(parts[first-2][3])
                for wide_begin in starts:
                    wide=RepairTarget(line,lo+wide_begin,lo+finish,lo,hi,
                        anomalies,structural,following)
                    if wide not in targets:targets.append(wide)
            # A kana word after a completed modifier can have its first kana
            # mistaken for a particle (e.g. an uncomposable mark breaks the word).
            # Keep both original boundaries; the wider candidate must pass the
            # same reading, physical-key and nominal-slot checks in full context.
            if (first>=2 and begin==parts[first][3]
                    and any(begin<=i<finish for i in mark_positions)
                    and parts[first-1][1].startswith('助詞')
                    and _is_reading(parts[first-1][0]) and len(parts[first-1][0])==1
                    and parts[first-2][4]==parts[first-1][3]
                    and parts[first-1][4]==begin
                    and _completed_predicate_token(parts[first-2])):
                wide_begin=parts[first-1][3]
                if finish-wide_begin<=18:
                    wide=RepairTarget(line,lo+wide_begin,lo+finish,lo,hi,anomalies,
                        structural,following)
                    if wide not in targets:targets.append(wide)
            # 副詞可能という最上位の解析だけで、語頭を捨てない。
            # 誤変換で副詞的名詞になった場合に備え、元の広い範囲を先に
            # 検査する。成立する候補が無ければ、時点等を文脈に残す範囲へ。
            if untrimmed_begin < begin and finish-untrimmed_begin <= 18:
                full = RepairTarget(line,lo+untrimmed_begin,lo+finish,lo,hi,
                    tuple((x,y,lo+s,lo+e) for x,y,s,e in odd
                          if s<finish and untrimmed_begin<e),
                    structural,following)
                if full not in targets:
                    targets.append(full)
            # 正しい助動詞は検査文脈へ残す。一方、原文で接続できない
            # 助動詞はそれ自身の誤打もあり得るため、語尾まで含む別範囲を
            # 控える。接続全体を先に比較し、語尾の誤打を見落とさない。
            for i in range(1,len(parts)):
                b=parts[i]
                if b[3]!=finish or not (oddness.polite_aux_mismatch(parts[i-1],b)
                        or oddness.completed_tsu_aux_mismatch(parts[i-1],b)
                        or oddness.desiderative_source_mismatch(clause,parts[i-1],b)):
                    continue
                extended=b[4]
                for c in parts[i+1:]:
                    if c[3]!=extended or not c[1].startswith(('助動詞','助詞:接続助詞')):
                        break
                    extended=c[4]
                if extended-begin>18:
                    break
                a=parts[i-1]
                from reading_segments import native_written_action_attachment_heads
                head=(a[0] if a[3]==begin and a[1].startswith('名詞:サ変接続') and (
                    _is_reading(a[0]) or (a[3],a[4]) in native_written_action_attachment_heads(clause)) else '')
                extra=RepairTarget(line,lo+begin,lo+extended,lo,hi,anomalies,
                                   structural,clause[extended:],'auxiliary_connection',head)
                if extra not in targets:
                    targets.append(extra)
                # 助動詞の前が短い名詞へ誤変換されると、直前の「へ/に」も
                # 語中のかなを切り取った境界になり得る。元の助動詞接続が
                # 明らかに崩れた場合だけ、前の名詞一語と境界まで検算する。
                if (a[3]==begin and len(a[0])<=2 and i>=3
                        and _case_boundary(parts[i-2]) and parts[i-2][0] in ('へ','に')
                        and parts[i-3][5] and parts[i-3][1].startswith('名詞')
                        and len(parts[i-3][0])>=2
                        and parts[i-3][4]==parts[i-2][3] and parts[i-2][4]==begin):
                    wide_begin=parts[i-3][3]
                    if extended-wide_begin<=18:
                        wide=RepairTarget(line,lo+wide_begin,lo+extended,lo,hi,anomalies,
                            structural,clause[extended:],'auxiliary_connection')
                        if wide not in targets:
                            targets.append(wide)
                break
            # 補助動詞の直結では、語尾との境界をまたいだ順序違いも
            # あり得る。本文側だけを交換して、接続助詞を取り残さない。
            for i in range(1,len(parts)):
                a,b=parts[i-1],parts[i]
                if not (begin<=a[3]<finish and b[3]<finish):
                    continue
                if not _auxiliary_connection_mismatch(a,b,parts[i-2] if i>1 else None):
                    continue
                extended=finish
                for t in parts:
                    if t[3]<extended:
                        continue
                    if t[3]!=extended or not t[5] or not t[1].startswith((
                            '助動詞','助詞:接続助詞','動詞:非自立','動詞:接尾')):
                        break
                    extended=t[4]
                if finish<extended and extended-begin<=18:
                    extra=RepairTarget(line,lo+begin,lo+extended,lo,hi,anomalies,
                                       structural,clause[extended:],'auxiliary_connection')
                    if extra not in targets:
                        targets.append(extra)
                break
            # 未然形＋「って」が既に異様なら、引用助詞という誤分割を
            # 固定せず、音便の「っ＋て」まで含む範囲も同じ打鍵で探す。
            for i in range(1,len(parts)):
                a,b=parts[i-1],parts[i]
                if (structural and begin<=a[3]<finish and b[3]==finish
                        and a[4]==b[3] and a[5] and a[1].startswith('動詞')
                        and a[6].startswith(('未然','仮定')) and b[0]=='って'
                        and b[1].startswith('助詞:格助詞') and b[4]-begin<=18):
                    extra=RepairTarget(line,lo+begin,lo+b[4],lo,hi,anomalies,
                        True,clause[b[4]:],'auxiliary_connection')
                    if extra not in targets:targets.append(extra)
                    break
    # An already anomalous predicate can have its first kana misparsed as
    # a one-character topic particle after the original case. Retain both
    # ranges so an adjacent intrusion inside that head can be removed, with
    # the same original-context validation and physical-key contract.
    for target in tuple(targets):
        if (not target.structural or target.preserved_head or target.spelling
                or target.boundary_kind not in ('lexical','auxiliary_connection')):
            continue
        prefix=[p for p in tokenize(target.context)
                if p[4]<=target.start-target.context_start]
        if len(prefix)<2:continue
        case,topic=prefix[-2:]
        if (case[5] and case[1].startswith('助詞:格助詞')
                and topic[5] and topic[1].startswith('助詞:係助詞')
                and _is_reading(topic[0]) and len(topic[0])==1
                and case[4]==topic[3] and topic[4]==target.start-target.context_start
                and target.end-target.context_start-topic[3]<=18):
            wide=replace(target,start=target.context_start+topic[3])
            if wide not in targets:targets.append(wide)
    # The object/predicate route already owns its complete source frame.
    # Do not reopen that same kana phrase as a second request-word search.
    targets=[t for t in targets if t.boundary_kind!='kana_request' or not any(
        other.boundary_kind=='kana_predicate' and t.context_start==other.context_start
        and t.start<=other.start and t.end==other.end for other in targets)]
    # Preserve the proven stem; lexical guesses cannot take responsibility for
    # the same spelling fact by expanding its range over a normal neighbor.
    targets=[t for t in targets if t.spelling or not any(
        t.start<f.end and f.start<t.end for f in source_spelling)]
    # A malformed next word must not consume a completed native link.
    # Keep the same original anomaly and context; only its editable range narrows.
    from reading_segments import native_completed_clause_boundaries
    from particle_frames import unlinked_past_predicate_frames
    broken_past=unlinked_past_predicate_frames(line)
    bounded=[]
    for target in targets:
        edges=[target.context_start+edge for edge in native_completed_clause_boundaries(target.context)
               if target.start<target.context_start+edge<target.end
               and not any(frame['start']<target.context_start+edge<frame['end']
                           for frame in broken_past)]
        if edges and target.boundary_kind in ('lexical','ime_scope') and not target.preserved_head and not target.spelling:
            target=replace(target,start=max(edges))
        if target not in bounded:bounded.append(target)
    targets=bounded
    targets=_unexplained_nominal_targets(targets)
    targets=_native_action_tail_targets(targets)
    targets=_native_owned_predicate_targets(targets,tokenize)
    targets=_native_verb_prefix_targets(targets)
    targets=_native_focused_prefix_targets(targets)
    # Include the original base key of a malformed syllable before using
    # native modifier boundaries; a target starting at small kana alone
    # otherwise conceals both the marked pair and the preceding word.
    targets=_native_marked_word_prefix_targets([
        replace(t,start=_lexical_syllable_start(t)) for t in targets])
    targets=_native_marked_nominal_member_targets(targets)
    # An actual limit case and a separately proved following object clause
    # delimit the earlier marked nominal. Do not search both as one word.
    from morphology import tokenize as native_tokens
    from reading_segments import native_object_predicate_contexts,native_object_predicate_proof
    for target in tuple(targets):
        if not target.structural or not target.anomalies or target.spelling:continue
        parts=native_tokens(target.context)
        for limit,case in zip(parts,parts[1:]):
            if (limit.surface!='まで' or limit.pos!='助詞' or not limit.has_reading
                    or case.surface!='に' or case.pos!='助詞' or not case.has_reading
                    or limit.end!=case.start):continue
            cut=target.context_start+limit.start
            if not target.start<cut<target.end:continue
            if not any(target.start<=a<b<=cut for _,_,a,b in target.anomalies):continue
            following=target.context[case.end:]
            if not any(begin==0 and native_object_predicate_proof(following,edge,faces)
                       for begin,edge,faces in native_object_predicate_contexts(following)):continue
            narrow=replace(target,end=cut,boundary_kind='lexical',
                following=target.source[cut:target.context_end])
            if narrow not in targets:targets.append(narrow)
    ordered=sorted(targets, key=lambda t: (t.start, not bool(t.preserved_head),
                                         t.boundary_kind=='lexical', -(t.end-t.start)))
    if _keep_completed and completed_boundaries:
        # Prefer preserving a plausible completed modifier. If that narrower
        # reading produces no valid candidate, its finite form may itself be an
        # IME misconversion. Reuse the same range construction without that cut.
        # The resolver skips these fallbacks once an overlapping narrow repair wins.
        for target in targets_for_line(line,tokenize,store,dictionary,False):
            if (target not in ordered and any(target.start<edge<target.end
                                             for edge in completed_boundaries)):
                ordered.append(target)
    # A complete modifier may keep the broad anomalous reading only as a
    # fallback above. Share its same proved noun boundary after that merge;
    # the retained head and modifier still enter ordinary final validation.
    ordered=sorted(_native_modified_nominal_prefix_targets(ordered),
                   key=lambda t:(t.start,not bool(t.preserved_head),
                                 t.boundary_kind=='lexical',-(t.end-t.start)))
    return _marked_lexical_suru_targets([replace(t,start=_lexical_syllable_start(t)) for t in ordered])


def _source_clause_bounds(line,start,end):
    lo,hi=0,len(line)
    for left,right in _source_separator_ranges(line):
        if right<=start:lo=right
        elif left>=end:hi=left;break
    return lo,hi


def _source_object_predicate_frame(line,start,end):
    """Share the original clause's proved object with validation and ranking."""
    from reading_segments import native_object_predicate_contexts
    lo,hi=_source_clause_bounds(line,start,end)
    original=line[lo:hi]
    from reading_segments import native_completed_clause_boundaries
    from reading_segments import _native_source_clauses
    punctuation=tuple(offset for offset,clause in _native_source_clauses(original) if offset<=start-lo)
    seams=tuple(edge for edge in native_completed_clause_boundaries(original) if edge<=start-lo)+punctuation
    frames=[f for f in native_object_predicate_contexts(original) if f[1]<=start-lo
            and not any(f[1]<edge for edge in seams)]
    for begin,cut,stop,faces in _source_actions_before_owned_objects(original):
        if cut==start-lo and stop==end-lo and not any(cut<edge for edge in seams):
            row=(begin,cut,faces)
            if row not in frames:frames.append(row)
    # An independently completed earlier clause owns its object. A mark
    # in the next clause must not bind that object to an unrelated predicate;
    # an explicit object of the later clause still supplies its own frame.
    if not frames:return None
    clause,cut,faces=max(frames,key=lambda f:(f[0],f[1]))
    return lo,hi,clause,cut,faces


@lru_cache(maxsize=4096)
def _original_counted_object_slots(text,include_unexplained=False):
    """Literal accusative/counter slots, including an unreadable kana token.

    A known lexical word is never split to invent を. The unchanged native
    counter attests its own boundary; no noun or anomaly is inferred here.
    """
    from morphology import tokenize
    from reading_segments import (_native_counter_prefixes,native_case_positions,
                                  native_nominal_phrase_faces,completed_native_link_clause)
    parts=tokenize(text);slots=[]
    for position in native_case_positions(text,parts):
        tail=text[position+1:]
        sizes=_native_counter_prefixes(tail,tokenize(tail))
        if sizes:slots.append((position+1,sizes))
        elif (include_unexplained and position>0
                and not native_nominal_phrase_faces(text[:position])):
            complete=completed_native_link_clause(tail)
            if not complete:
                # Keep the actual case context: isolated にます can parse
                # に as a particle, while the source を + 煮ます attests a
                # native independent verb and its complete auxiliary tail.
                from semantic_roles import _terminal_predicate_tail
                head=next((t for t in parts if t.start==position+1 and t.has_reading
                           and (t.pos=='動詞' and t.pos_sub=='自立'
                                or t.pos=='名詞' and t.pos_sub=='サ変接続')),None)
                finite_head=head
                if head and head.pos=='名詞':
                    from morphology import dictionary_inflections,native_suru_form
                    following=next((t for t in parts if t.start==head.end),None)
                    noun=any(pos.startswith('名詞,サ変接続,') and base==head.surface
                             and rd==head.reading for pos,form,base,rd
                             in dictionary_inflections(head.surface) or ())
                    finite_head=(following if noun and following and following.has_reading
                        and following.pos=='動詞'
                        and native_suru_form(following.surface,following.infl_form,following.reading,False)
                        and any(pos.startswith('動詞,') and base=='する'
                            and form==following.infl_form and rd==following.reading
                            for pos,form,base,rd in dictionary_inflections(following.surface) or ())
                        else None)
                if head and finite_head:
                    legacy=[(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,
                             t.has_reading,t.infl_form) for t in parts]
                    complete=(_terminal_predicate_tail(text,legacy,finite_head.end,finite_head.infl_form)
                              and _productive_predicate(tail,head.surface,before=text[:position+1]))
            # 48-ALT: zero means no quantity. The native case and whole
            # completed predicate supply only a candidate-validation slot;
            # they do not declare the unknown original noun anomalous.
            if complete:slots.append((position+1,(0,)))
    return tuple(slots)


def _source_te_edges(text):
    """Actual native continuative + te/de boundaries, before any repair."""
    from morphology import tokenize
    parts=tokenize(text)
    return tuple(link.end for verb,link in zip(parts,parts[1:])
        if verb.has_reading and verb.pos=='動詞' and verb.end==link.start
        and link.has_reading and link.pos=='助詞' and link.pos_sub=='接続助詞'
        and link.surface in ('て','で')
        and _modern_te_allowed(verb.surface,verb.reading,link.surface) is True)


def _retained_action_before_owned_object(target,surface,source_reading,expected_reading):
    """Keep an original owned action separate from the next owned object.

    The unchanged literal link is bound to the original reading segments.
    Its native candidate connection and its own original object's positive
    meaning are both required; the later clause lends neither permission.
    """
    if (target.boundary_kind!='lexical' or not target.structural or not target.anomalies
            or target.spelling or not source_reading or not expected_reading
            or not target.text or target.text[-1] not in ('て','で')):return False
    segments=source_reading.segments;cursor=0
    for a,b,rd,kind in segments:
        if a!=cursor or not a<b<=len(target.text) or not rd:return False
        cursor=b
    if (cursor!=len(target.text) or ''.join(s[2] for s in segments)!=source_reading.text):
        return False
    a,b,rd,kind=segments[-1]
    if (kind!='literal_kana' or rd!=target.text[a:b]
            or not surface.endswith(target.text[-1])
            or not expected_reading.endswith(target.text[-1])):return False
    from morphology import native_spelling_only
    from reading_segments import native_object_predicate_proof
    if (len(surface) not in _source_te_edges(surface)
            or not native_spelling_only(expected_reading,surface)):return False
    lo,hi=_source_clause_bounds(target.source,target.start,target.end)
    clause=target.source[lo:hi]
    if any(c in clause for c in '\t\r\n'):return False
    start,end=target.start-lo,target.end-lo
    return any(cut==start and edge==end
        and native_object_predicate_proof(clause[begin:cut]+surface,
                                         cut-begin,faces,allow_link=True)
        for begin,cut,edge,faces in _source_actions_before_owned_objects(clause))


def _source_linked_companion_owns_object(target,frame,companions,surface=None):
    """Prove a prior action's own object through an unchanged original link.

    Companions retain their original edit coordinates and are independently
    checked by resolution and joint validation. This supplies no reading or
    typing evidence for the later candidate.
    """
    begin,cut,faces=frame
    if not faces:return False
    from semantic_roles import _motion_tail_cannot_take_object
    from reading_segments import native_object_predicate_proof
    from morphology import tokenize as native_tokens
    local=target.start-target.context_start
    if not all(_motion_tail_cannot_take_object(target.context[local:],face) for face in faces):return False
    if surface is not None:
        # Original motion does not lend its case behavior to a different
        # proposed predicate. The same finite non-object proof is required
        # of the actual candidate as well, before detaching this object.
        proposed=surface+target.context[target.end-target.context_start:]
        if not all(_motion_tail_cannot_take_object(proposed,face) for face in faces):return False
    for a,b,surface in companions:
        if (a!=target.context_start+cut or not a<b<target.start
                or not target.context_start<=a or not surface):continue
        link=target.source[b:target.start]
        if link not in ('て','で'):continue
        from morphology import dictionary_inflections
        # The original particle can be parsed as a collocation after the
        # malformed noun. Its same-face/same-reading native link entry and
        # the repaired action's actual connection are independent evidence.
        if not any(pos.startswith('助詞,接続助詞') and base==link and rd==link
                   for pos,form,base,rd in dictionary_inflections(link) or ()):continue
        parts=native_tokens(target.context)
        if not any(t.start==b-target.context_start and t.end==local
                   and t.surface==link and t.reading==link and t.has_reading
                   and t.pos=='助詞' for t in parts):continue
        action=surface+link
        if len(action) not in _source_te_edges(action):continue
        prefix=target.context[begin:cut]+action
        if native_object_predicate_proof(prefix,cut-begin,faces,allow_link=True):return True
    return False


def _retained_nonfinite_intrusion_link(target,surface,source_reading,expected_reading,
                                       tokenize,store,dictionary):
    """Bind the existing source intrusion proof to its unchanged link.

    This supplies a boundary only. The caller still proves the candidate's
    own original object and native connection; the later clause lends no
    meaning. No corrected sentence is used as original typing evidence.
    """
    if (target.boundary_kind!='lexical' or not target.structural or not target.anomalies
            or target.spelling or not source_reading or not expected_reading
            or not target.text.endswith('て')):return False
    lo,hi=_source_clause_bounds(target.source,target.start,target.end)
    clause=target.source[lo:hi]
    if any(c in clause for c in '\t\r\n'):return False
    parts=list(tokenize(clause))
    import pos_grammar
    grammar=pos_grammar.odd_kana_spans(clause,dictionary,store)
    frames=_marked_nonfinite_connective_intrusion_targets(target.source,lo,hi,parts,grammar)
    if not any((frame.start,frame.end)==(target.start,target.end)
               and all(mark in target.anomalies for mark in frame.anomalies)
               for frame in frames):return False
    original=[t for t in parts if target.start-lo<=t[3]<t[4]<=target.end-lo]
    if len(original)!=2:return False
    recorded=tuple((a,b,rd) for a,b,rd,kind in source_reading.segments)
    actual=tuple((lo+t[3]-target.start,lo+t[4]-target.start,t[2]) for t in original)
    if (recorded!=actual or source_reading.text!=''.join(t[2] for t in original)
            or expected_reading!=original[0][2]+original[1][2][1:]):return False
    from morphology import native_spelling_only
    return (len(surface) in _source_te_edges(surface)
            and native_spelling_only(expected_reading,surface))


def _retained_nominal_prefix_relation(text,start,end,surface,reading):
    """Positive compound evidence from the unchanged original noun prefix.

    This proves only the candidate's relation to that same written noun.
    A later predicate contributes no meaning to the repaired word.
    """
    if not 0<start<end<=len(text) or not reading:return False
    from morphology import tokenize,dictionary_inflections
    from reading_segments import native_nominal_verb_prefix_ranges,native_deverbal_nominal_faces
    from semantic_roles import nominal_compound_support
    parts=tokenize(text)
    head=next((p for p in parts if p.end==start),None)
    if not head or not head.has_reading:return False
    if head.start:
        previous=next((p for p in parts if p.end==head.start),None)
        if not (previous and previous.has_reading and previous.pos=='助詞'
                and previous.pos_sub.startswith('格助詞:')):return False
    nominal=(head.pos=='名詞' and not any(x in head.pos_sub
             for x in ('固有名詞','接尾','非自立')))
    if not nominal:
        nominal=((head.start,head.end) in native_nominal_verb_prefix_ranges(text)
            and head.surface in native_deverbal_nominal_faces(head.reading))
    if not nominal:return False
    def noun(word,rd):
        return any(pos.startswith('名詞,') and base==word and native==rd
                   and not any(x in pos for x in ('固有名詞','接尾','非自立'))
                   for pos,form,base,native in dictionary_inflections(word) or ())
    return bool(noun(head.surface,head.reading) and noun(surface,reading)
                and nominal_compound_support(head.surface,surface))


def _source_other_case_object_positions(text,start,end):
    """An original non-accusative case separates a later proved object.

    Return only the literal accusatives owned by that unchanged complete
    noun/predicate. This assigns no meaning to the earlier edited word and
    supplies no candidate permission; its ordinary checks still apply.
    """
    if not 0<=start<end<len(text) or any(c in text for c in '\t\r\n'):return ()
    from morphology import tokenize,dictionary_inflections
    from reading_segments import native_object_predicate_contexts,native_object_predicate_proof
    parts=tokenize(text)
    left=next((p for p in parts if p.end==end and start<=p.start),None)
    case=next((p for p in parts if p.start==end),None)
    if not (left and left.has_reading and left.pos=='名詞'
            and case and case.has_reading and case.pos=='助詞'
            and case.pos_sub=='格助詞:一般' and case.surface!='を'
            and any(pos.startswith('助詞,格助詞,一般,') and base==case.surface and rd==case.reading
                    for pos,form,base,rd in dictionary_inflections(case.surface) or ())):return ()
    following=text[case.end:];tail=tokenize(following);found=[]
    for begin,cut,faces in native_object_predicate_contexts(following,allow_written_predicate=True):
        if begin!=0 or not native_object_predicate_proof(following,cut,faces):continue
        original=[p for p in parts if case.end<=p.start and p.end<=case.end+cut]
        local=[p for p in tail if p.end<=cut]
        def identity(p,offset):
            return (p.surface,p.reading,p.pos,p.pos_sub,p.infl_form,p.start-offset,p.end-offset,p.has_reading)
        if (not original or not all(p.has_reading for p in original)
                or [identity(p,case.end) for p in original]!=[identity(p,0) for p in local]):continue
        owned=original[-1]
        if (owned.end==case.end+cut and owned.surface=='を' and owned.pos=='助詞'
                and owned.pos_sub=='格助詞:一般'):
            found.append(owned.start)
    return tuple(dict.fromkeys(found))


def _changed_object_slot_allowed(line,start,end,surface,require_positive_plain=False):
    """48-AIG/ALT: a changed object owns its unchanged case and predicate.

    Match the actual source case/counter through equal text, independently
    of the proposed replacement's outer boundary. A wider candidate cannot
    evade the same proof, and an edit in a separate clause does not invoke it.
    No source anomaly is inferred from a missing noun/meaning classification.
    """
    if 'を' not in line:return not require_positive_plain
    proved_plain=False
    from reading_segments import (native_object_predicate_contexts,native_object_predicate_proof,
                                  _native_source_clauses)
    from difflib import SequenceMatcher
    lo,hi=_source_clause_bounds(line,start,end)
    original=line[lo:hi]
    changed=line[lo:start]+surface+line[end:hi]
    clauses=list(_native_source_clauses(changed))
    frames=[(offset+begin,offset+cut,nouns,offset+len(clause))
            for offset,clause in clauses
            for begin,cut,nouns in native_object_predicate_contexts(clause,allow_written_predicate=True)]
    matcher=SequenceMatcher(None,original,changed,autojunk=False)
    edits=[(a,b,c,d) for tag,a,b,c,d in matcher.get_opcodes() if tag!='equal']
    # A newly repaired noun cannot introduce an explicit conflict with its
    # own unchanged predicate. Missing meaning stays unknown; a separate
    # later clause cannot veto this object edit.
    from reading_segments import _native_written_predicate_conflicts,native_predicate_link_boundaries
    for begin,cut,nouns,finish in frames:
        if not any(begin<=c<cut-1 and c<d<=cut-1 for a,b,c,d in edits):continue
        fragment=changed[begin:finish];head=cut-begin
        edge=min(native_predicate_link_boundaries(fragment,head) or (len(fragment),))
        if any(head<=a<edge for _,_,a,b in _native_written_predicate_conflicts(fragment)):
            return False
        # Complete native grammar and the same object's positive meaning
        # outrank an accidental short kana verb in the best tokenization.
        if (native_object_predicate_proof(fragment,head,nouns)
                or native_object_predicate_proof(fragment,head,nouns,allow_link=True)):
            continue
        from morphology import tokenize as native_tokenize
        from semantic_roles import nominal_roles,nominal_role_matches,native_verb_roles
        native=native_tokenize(fragment);verb=next((p for p in native if p.start==head),None)
        from morphology import dictionary_inflections
        forms=tuple(row for row in dictionary_inflections(verb.surface) or ()
            if row[0].startswith('動詞,自立,') and row[1]==verb.infl_form and row[3]==verb.reading) if verb else ()
        native_head=bool(verb and verb.has_reading and forms and
            (verb.end==edge or _allows_grammatical_tail(forms,fragment[verb.end:edge],verb.reading,verb.surface)))
        roles=native_verb_roles(verb.surface,verb.infl_form,verb.reading) if native_head else ()
        # Only a proposed replacement is checked here. An unknown role
        # remains unknown and cannot mark normal source text as erroneous.
        if (roles and nouns and all(nominal_roles(noun) for noun in nouns)
                and not any(nominal_role_matches(noun,roles) for noun in nouns)):
            return False
    if require_positive_plain:
        # A malformed written noun may end in a spurious auxiliary, so
        # nominal source discovery cannot yet recognize it. The literal
        # accusative particle and entire unchanged predicate still bound
        # the candidate's own positive meaning check.
        from morphology import tokenize
        for part in tokenize(original):
            if not (part.has_reading and part.surface=='を' and part.pos=='助詞'
                    and part.pos_sub.startswith('格助詞') and end-lo<=part.start):continue
            cut=next((block.b+part.end-block.a for block in matcher.get_matching_blocks()
                if block.a<=part.start and len(original)<=block.a+block.size),None)
            if cut is None:continue
            for begin,edge,nouns,finish in frames:
                if edge!=cut or not all(begin<=c<=d<=cut-1 for a,b,c,d in edits):continue
                if native_object_predicate_proof(changed[begin:finish],cut-begin,nouns):
                    proved_plain=True
    for predicate_start,quantities in _original_counted_object_slots(original,include_unexplained=True):
        if quantities==(0,) and not any(block.a<=predicate_start-1
                and len(original)<=block.a+block.size for block in matcher.get_matching_blocks()):
            continue
        cuts={block.b+predicate_start-block.a for block in matcher.get_matching_blocks()
              if block.a<predicate_start and any(predicate_start+size<=block.a+block.size for size in quantities)}
        for cut in cuts:
            if quantities==(0,) and not require_positive_plain:
                # A repaired whole lexical item may itself be mentioned
                # as an object (including an adverb/onomatopoeia). This
                # boundary check does not infer meaning or require a noun
                # role merely because the spelling precedes を.
                from reading_segments import native_surface_nominal_heads,native_lexical_reading_faces
                prefix=changed[:cut-1]
                if native_surface_nominal_heads(prefix) or native_lexical_reading_faces(prefix):
                    continue
                from reading_segments import native_modified_nominal_contexts
                if any(case+1==cut for begin,head,case,finish,faces
                       in native_modified_nominal_contexts(changed)):
                    # The same relative/genitive modifier and unchanged
                    # predicate already prove this exact repaired object.
                    continue
                # The legacy two-word composer already proves these exact
                # native nouns through the shared compound relation. This is
                # boundary evidence only; it assigns no new object meaning.
                from morphology import tokenize
                from semantic_roles import nominal_compound_support
                parts=tokenize(prefix)
                if (len(parts)==2 and parts[0].start==0 and parts[0].end==parts[1].start
                        and parts[1].end==len(prefix) and all(t.has_reading and t.pos=='名詞'
                            and not any(x in t.pos_sub for x in ('固有名詞','接尾','非自立')) for t in parts)
                        and nominal_compound_support(parts[0].surface,parts[1].surface)):
                    continue
            # A malformed verb/unknown sequence has no nominal frame. Its
            # absence cannot certify the proposed object. Keep independent
            # completed clauses outside the affected object region.
            if not any(edge==cut for begin,edge,nouns,finish in frames):
                from morphology import tokenize
                from reading_segments import (native_completed_clause_boundaries,
                                              native_object_clause_edges,completed_native_link_clause)
                for offset,clause in clauses:
                    if not offset<cut<=offset+len(clause):continue
                    prefix=clause[:cut-offset-1]
                    boundaries=list(native_completed_clause_boundaries(clause))+list(native_object_clause_edges(clause))+list(native_predicate_link_boundaries(clause,0))
                    for part in tokenize(prefix):
                        if not (part.has_reading and part.pos=='助詞'
                                and part.pos_sub=='接続助詞'):continue
                        left=prefix[:part.end]
                        link=_unchanged_finite_connective(left,left)
                        if link and completed_native_link_clause(left[:-len(link)],allow_unclassified=True):
                            boundaries.append(part.end)
                    begin=offset+max([0]+[edge for edge in boundaries if edge<cut-offset-1])
                    if any(c<cut-1 and begin<d or c==d and begin<=c<=cut-1
                           for a,b,c,d in edits):return False
            affected=[(begin,nouns,finish) for begin,edge,nouns,finish in frames if edge==cut
                and any(c<cut-1 and begin<d or c==d and begin<=c<=cut-1
                        for a,b,c,d in edits)]
            if affected and (quantities!=(0,) or require_positive_plain):
                proved=any(native_object_predicate_proof(changed[begin:finish],cut-begin,nouns)
                           for begin,nouns,finish in affected)
                if not proved:return False
                if quantities==(0,):proved_plain=True
    return not require_positive_plain or proved_plain


def _changed_genitive_object_allowed(line,start,end,surface):
    """The original genitive argument keeps its case and first native action.

    Map the unchanged boundary text, so a wider legacy replacement cannot
    evade the same nominal/semantic proof. Later clauses supply no evidence
    for this object's action. No missing source classification is an anomaly.
    """
    from reading_segments import (native_modified_argument_slots,native_object_predicate_proof,
                                  native_nominal_phrase_faces,native_common_noun_reading)
    from difflib import SequenceMatcher
    lo,hi=_source_clause_bounds(line,start,end);old=line[lo:hi]
    slots=native_modified_argument_slots(old)
    if not slots:return True
    new=line[lo:start]+surface+line[end:hi]
    matcher=SequenceMatcher(None,old,new,autojunk=False);blocks=matcher.get_matching_blocks()
    def mapped(a,b):
        return next(((block.b+a-block.a,block.b+b-block.a) for block in blocks
                     if block.a<=a and b<=block.a+block.size),None)
    edits=[(a,b) for tag,a,b,c,d in matcher.get_opcodes() if tag!='equal']
    for begin,head,case,finish,relative in slots:
        if not any(a<case and head<b or a==b and head<=a<case for a,b in edits):continue
        prefix=mapped(begin,head);marker=mapped(case,case+1);ending=mapped(finish-1,finish)
        if prefix is None and begin==start-lo and old[head-1:head]=='の':
            # A kana modifier may acquire its own native spelling while the
            # genitive boundary and the object/predicate proof stay in place.
            genitive=mapped(head-1,head)
            if genitive is not None:
                from morphology import native_spelling_only
                new_prefix=new[begin:genitive[1]]
                if native_spelling_only(old[begin:head],new_prefix):
                    prefix=(begin,genitive[1])
        if prefix is None:return False
        if marker is None or ending is None:return False
        new_begin,new_head=prefix;new_case=marker[0];new_finish=ending[1]
        if not new_head<new_case<new_finish:return False
        fragment=new[new_begin:new_finish]
        head_text=new[new_head:new_case]
        faces=native_nominal_phrase_faces(head_text)
        if not faces and not _is_reading(head_text):
            from morphology import tokenize
            head_parts=tokenize(head_text)
            if head_parts and all(part.has_reading for part in head_parts):
                head_reading=''.join(part.reading for part in head_parts)
                if native_common_noun_reading(head_text,head_reading):faces=(head_text,)
        if not faces and not relative:return False
        if relative:
            from reading_segments import native_relative_nominal_faces,native_genitive_nominal_splits
            splits=native_genitive_nominal_splits(old[head:case],True)
            if len(splits)==1 and not splits[0][1] and mapped(head+splits[0][0],case) is None:
                return False
            faces=native_relative_nominal_faces(head_text,*relative)
            if not faces:return False
        if not native_object_predicate_proof(fragment,new_case-new_begin+1,faces,allow_link=True):
            return False
    return True


def _same_reading_open_object_spelling(src,dst,cut,faces,new_cut=None):
    """An actual unfinished polite predicate keeps its reading and object.

    Source prefix evidence does not certify the proposed meaning. The
    written clause must separately prove every original argument, the
    actual native action/inflection and the unchanged polite auxiliary.
    """
    from morphology import native_spelling_only
    from reading_segments import (native_incomplete_polite_reading,
        native_polite_auxiliary_chains,native_written_relative_action,
        native_surface_nominal_heads)
    if new_cut is None:new_cut=cut
    if (not 1<cut<len(src) or not 1<new_cut<len(dst)
            or src[cut-1:cut]!='を' or dst[new_cut-1:new_cut]!='を'
            or not native_spelling_only(src,dst)
            or not native_incomplete_polite_reading(src[cut:])):return False
    original=src[cut:];tail=dst[new_cut:]
    chains=native_polite_auxiliary_chains(tail,include_open=True)
    if not any(b==len(tail) and original.endswith(tail[a:b])
               for a,b,signature in chains):return False
    written=native_written_relative_action(dst,allow_open_polite=True)
    if not written or 'を' not in written[1]:return False
    actual=set(native_surface_nominal_heads(dst[:new_cut-1]))
    from semantic_roles import candidate_evidence
    for face in faces:
        if face not in actual:continue
        evidence=candidate_evidence(face,written[0],tail[len(written[0]):],dst[:new_cut])
        if evidence and evidence.get('shared_roles'):return evidence
    return False


def _object_predicate_candidate_fits(src,dst,cut,faces,new_cut=None,spelling=False):
    """One source prefix and the same final clause proof for every edit width."""
    from reading_segments import native_object_predicate_proof
    if new_cut is None:new_cut=cut
    if src[:cut]!=dst[:new_cut]:
        from morphology import native_spelling_only
        if (src[cut-1:cut]!='を' or dst[new_cut-1:new_cut]!='を'
                or not native_spelling_only(src[:cut],dst[:new_cut])):return False
        # Pin the proposed written object's own meaning; do not borrow the
        # other homophones previously possible in the original kana.
        faces=(dst[:new_cut-1],)
    if spelling and _same_reading_open_object_spelling(src,dst,cut,faces,new_cut):return True
    cut=new_cut
    if native_object_predicate_proof(dst,cut,faces):return True
    retained=_unchanged_finite_connective(src,dst)
    return bool(retained and dst.endswith(retained)
                and native_object_predicate_proof(dst[:-len(retained)],cut,faces))


def _wide_object_predicate_allowed(line,start,end,surface,spelling=False):
    """48-AKW: actual predicate edits retain their original argument frames.

    Equal source spans map independently of the proposal's outer boundary.
    An unchanged bad predicate in another clause supplies no restriction.
    """
    from difflib import SequenceMatcher
    from reading_segments import native_object_predicate_contexts,_native_source_clauses
    changed=line[:start]+surface+line[end:]
    matcher=SequenceMatcher(None,line,changed,autojunk=False)
    opcodes=matcher.get_opcodes();blocks=matcher.get_matching_blocks()
    edits=[(a,b) for tag,a,b,c,d in opcodes if tag!='equal']
    def boundary(position):
        for tag,a,b,c,d in opcodes:
            if a<=position<=b:
                if tag=='equal':return c+position-a
                if position==a:return c
                if position==b:return d
        return None
    from reading_segments import native_completed_clause_boundaries
    for offset,clause in _native_source_clauses(line):
        finish=offset+len(clause)
        seams=native_completed_clause_boundaries(clause)
        for begin,cut,faces in native_object_predicate_contexts(clause):
            # An already completed earlier clause owns its own object in
            # narrow and wide proposals alike. Inspect edits before its seam.
            relevant=[(a,b) for a,b in edits
                if (a<finish and offset+cut<b or a==b and offset+cut<=a<finish)
                and not any(cut<edge<=a-offset for edge in seams)]
            if not relevant:continue
            prefix_start=offset+begin;prefix_end=offset+cut
            block=next((block for block in blocks
                if block.a<=prefix_start and prefix_end<=block.a+block.size),None)
            mapped_begin=(block.b+prefix_start-block.a if block is not None else boundary(prefix_start))
            mapped_cut=boundary(prefix_end);mapped_finish=boundary(finish)
            if mapped_begin is None or mapped_cut is None or mapped_finish is None:return False
            if not _object_predicate_candidate_fits(clause[begin:],
                    changed[mapped_begin:mapped_finish],cut-begin,faces,
                    new_cut=mapped_cut-mapped_begin,spelling=spelling):return False
    return True


def _native_kara_note_preserve(line,legacy,store,tokenize,dictionary,decisions,engine,
                               protected_mode=False):
    """Keep a proved source action note when another route invents a reading."""
    finite=(re.fullmatch(
        r'([一-鿿]{1,12})を([ぁ-ゖ]{2,12})してから([ぁ-ゖ]{2,12})(します|しました)([。！？.!?]?)',
        line) if protected_mode else None)
    match=finite or re.fullmatch(
        r'([一-鿿]{1,12})を([ぁ-ゖ]{2,12})してから([ぁ-ゖ]{2,12})',line)
    if not match or legacy.get('analysis_status') in ('incomplete','limited'):return None
    from reading_segments import (native_bare_action_faces,native_object_predicate_proof,
                                  completed_native_reading_clause)
    from last_choice import surface_for_reading
    noun,first,second=match.groups()[:3]
    if any(surface_for_reading(reading) is not None for reading in (line,first,second)):
        return None
    second_faces=tuple(native_bare_action_faces(second))
    if not second_faces or (not finite and len(second_faces)!=1):return None
    first_faces=tuple(native_bare_action_faces(first))
    if not first_faces:return None
    first_clause=noun+'を'+first+'して'
    action=native_object_predicate_proof(first_clause,len(noun)+1,(noun,),
                                         allow_link=True,return_action=True)
    if action not in first_faces:return None
    if finite:
        final_action=native_object_predicate_proof(noun+'を'+second+finite.group(4),
            len(noun)+1,(noun,),allow_link=True,return_action=True)
        if final_action not in second_faces:return None
    else:
        completed=completed_native_reading_clause(first+'して',allow_nonpolite=True,
            require_object_fit=True,return_action=True,action_note_following=second_faces)
        if completed!=action:return None
    original_odd=engine._odd_spans_for_line(line,tokenize,[],store,dictionary,
                                            include_pending=False)
    if not finite:
        tail_start=len(line)-len(second)
        if not any(a<=len(noun)+1 and b>=tail_start for a,b in original_odd):
            return None
    if finite and action!=first:
        from kana_spelling import _compose_result
        start=len(noun)+1;end=start+len(first)
        candidate=line[:start]+action+line[end:]
        checked,reason=engine._check_replacement(line,(start,end,action,'かな入力'),
            store,tokenize,dictionary,decisions,conv_taken=((start,end),),spelling=True)
        if (checked is not None and tuple(checked[:3])==(start,end,action)
                and not engine._odd_spans_for_line(candidate,tokenize,[],store,dictionary,
                                                   include_pending=False)):
            base=dict(legacy,corrected=line,changed=False,details=[],spans=[],
                      original_spans=[],odd_spans=[],odd_reasons=[],unsure_spans=[])
            composed=_compose_result(line,base,((start,end,action),),engine,decisions)
            if composed.get('corrected')==candidate:
                return engine._line_result_contract(line,composed,tokenize,dictionary)
    held=dict(legacy,corrected=line,changed=False,details=[],spans=[],
              original_spans=[],odd_spans=original_odd,odd_reasons=[],unsure_spans=[])
    return engine._line_result_contract(line,held,tokenize,dictionary)


def _native_relative_source_spelling(line,store,tokenize,dictionary,decisions,engine):
    """Project only a complete relative action, fitted noun and final action."""
    match=re.fullmatch(
        r'([ぁ-ゖ]{2,12})(した|する)([ぁ-ゖ]{2,12})を([ぁ-ゖ]{2,12})(します|しました)([。！？.!?]?)',line)
    if not match:return None
    from reading_segments import (native_relative_action,native_relative_nominal_faces,
        native_object_predicate_proof,completed_native_reading_clause)
    from morphology import native_spelling_only
    from last_choice import surface_for_reading
    head,link,noun,predicate,finite,punctuation=match.groups()
    relative=native_relative_action(head+link)
    if not relative or not isinstance(relative[0],str):return None
    action=relative[0]
    noun_faces=tuple(native_relative_nominal_faces(noun,*relative))
    if len(noun_faces)!=1:return None
    written_noun=noun_faces[0]
    suffix=noun+'を'+predicate+finite
    if not native_object_predicate_proof(suffix,len(noun)+1,(written_noun,),allow_link=True):
        return None
    final_action=completed_native_reading_clause(suffix,require_nominal=True,
        require_object_fit=True,return_action=True)
    if not isinstance(final_action,str):return None
    changes=[(0,len(head),action),
        (len(head)+len(link),len(head)+len(link)+len(noun),written_noun),
        (len(head)+len(link)+len(noun)+1,
         len(head)+len(link)+len(noun)+1+len(predicate),final_action)]
    if any(not any('一'<=c<='鿿' or 'ァ'<=c<='ヶ' for c in face)
           or surface_for_reading(line[a:b]) not in (None,face)
           for a,b,face in changes):return None
    candidate=_apply(line,changes)
    if (surface_for_reading(line) not in (None,candidate)
            or not native_spelling_only(line,candidate)
            or engine._user_blocks_replacement(decisions,line,candidate)):
        return None
    for a,b,face in changes:
        checked,reason=engine._check_replacement(line,(a,b,face,'かな入力'),
            store,tokenize,dictionary,decisions,conv_taken=((a,b),),spelling=True)
        if checked is None or tuple(checked[:3])!=(a,b,face):return None
    if engine._odd_spans_for_line(candidate,tokenize,[],store,dictionary,
                                  include_pending=False):return None
    return candidate,tuple(changes)


def _mixed_action_note_first_spelling(line,start,end,surface):
    """A written を-object can license only its native first kana action.

    The unchanged source tail must independently prove the whole linked
    action note. The proposed head must be the very first action in that
    proof and have a positive role with the original written object.
    """
    from morphology import tokenize,native_spelling_only
    from reading_segments import _native_action_note_heads,native_bare_action_faces
    from semantic_roles import candidate_evidence
    if (not 2<=start<end<=len(line) or not re.fullmatch(
            r'[一-鿿]+を[ぁ-ゖ]{8,}',line) or line[start-1]!='を'):
        return False
    frame=_source_object_predicate_frame(line,start,end)
    if not frame or frame[0]!=0 or frame[2]!=0 or frame[3]!=start:
        return False
    object_text=line[:start-1]
    parts=tokenize(line[:start])
    if (len(parts)!=2 or parts[0].surface!=object_text
            or parts[0].pos!='名詞' or not parts[0].has_reading
            or not any('一'<=ch<='鿿' for ch in object_text)
            or parts[1].surface!='を' or parts[1].start!=start-1):
        return False
    tail=line[start:]
    if not tail or not all('ぁ'<=ch<='ゖ' for ch in tail):return False
    heads=_native_action_note_heads(tail)
    if not heads or surface not in heads:return False
    head=line[start:end]
    if (not head or tail[len(head):len(head)+2]!='して'
            or surface not in native_bare_action_faces(head)
            or not native_spelling_only(line,line[:start]+surface+line[end:])):
        return False
    evidence=candidate_evidence(object_text,surface,line[end:],line[:start])
    return bool(evidence and evidence.get('shared_roles'))


def _written_object_native_finite_action(line):
    """An unchanged written object owns a fully native finite action chain."""
    match=re.fullmatch(
        r'([一-鿿]+)を([ぁ-ゖ]{2,}して[一-鿿ぁ-ゖ]{2,}(?:ます|ました))[。！？.!?]?',line)
    if not match:return False
    from morphology import tokenize
    from reading_segments import native_object_predicate_proof
    object_text=match.group(1);cut=len(object_text)+1
    parts=tokenize(line[:cut])
    if (len(parts)!=2 or parts[0].surface!=object_text
            or parts[0].pos!='名詞' or not parts[0].has_reading
            or parts[1].surface!='を' or parts[1].start!=cut-1):return False
    return bool(native_object_predicate_proof(match.group(1)+'を'+match.group(2),
                                               cut,(object_text,),allow_link=True))


def _later_object_scope(line,start,end,surface):
    """Locate a later actual object without requiring a semantic label."""
    from reading_segments import native_object_clause_edges,native_object_predicate_frames
    edges=sorted(set(_source_te_edges(line[:start]))|set(native_object_clause_edges(line[:start])))
    for edge in reversed(edges):
        original=line[edge:];changed=line[edge:start]+surface+line[end:]
        # The new actual noun/case owns its unchanged predicate. Absence of
        # a role label is not evidence that this ordinary noun is invalid.
        if (native_object_predicate_frames(changed.rstrip('。！？.!?'),True)
                and _changed_object_slot_allowed(original,start-edge,end-edge,surface)
                and _wide_object_predicate_allowed(original,start-edge,end-edge,surface)):
            return edge
    return None



def independently_spelled_object_verb(line,start,end,surface):
    """Spell an existing predicate using its own tail and object meaning.

    The literal head, inflection and full tail must be unchanged. Its sense
    needs a positively fitting original object in the same argument scope.
    This proves only the spelling; it never clears the unknown phrase.
    """
    from morphology import tokenize,dictionary_inflections,native_spelling_only
    if not native_spelling_only(line[start:end],surface):return False
    frame=_source_object_predicate_frame(line,start,end)
    if frame is not None:
        lo,hi,clause,cut,faces=frame
        original=line[lo+clause:hi]
        changed=line[lo+clause:start]+surface+line[end:hi]
        proof=_same_reading_open_object_spelling(original,changed,cut-clause,faces)
        if proof:return proof
    parts=tokenize(line)
    head=next((t for t in parts if t.start==start and t.end==end
        and t.has_reading and t.pos=='動詞' and t.pos_sub=='自立'),None)
    if head is None:return False
    tail=line[end:].rstrip('。！？.!?')
    forms=tuple(row for row in dictionary_inflections(surface) or ()
        if row[0].startswith('動詞,自立,') and row[1]==head.infl_form and row[3]==head.reading)
    if (not forms or not _allows_grammatical_tail(forms,tail,head.reading,surface)
            or not _productive_predicate(surface+tail,surface)):
        return False
    ending=tokenize(surface+tail)
    if not ending:return False
    last=ending[-1]
    if not _completed_predicate_token((last.surface,last.pos+':'+last.pos_sub,
            last.reading,last.start,last.end,last.has_reading,last.infl_form)):
        return False
    from reading_segments import native_object_predicate_contexts,native_predicate_link_boundaries
    from semantic_roles import candidate_evidence
    for begin,cut,faces in native_object_predicate_contexts(line,True):
        if cut>start or any(cut<edge<=start for edge in native_predicate_link_boundaries(line,cut)):
            continue
        for face in faces:
            proof=candidate_evidence(face,surface,tail,line[:start])
            if proof and proof.get('shared_roles'):return proof
    return False


def object_predicate_candidate_allowed(line,start,end,surface,spelling=False):
    """A proposed edit completes the same independently proved object clause."""
    if not _changed_genitive_object_allowed(line,start,end,surface):return False
    if spelling and independently_spelled_object_verb(line,start,end,surface):return True
    if _later_object_scope(line,start,end,surface) is not None:return True
    frame=_source_object_predicate_frame(line,start,end)
    if frame is None:
        return (_changed_object_slot_allowed(line,start,end,surface)
                and _wide_object_predicate_allowed(line,start,end,surface,spelling=spelling))
    lo,hi,clause,cut,faces=frame
    original=line[lo:hi];changed=line[lo:start]+surface+line[end:hi]
    src,dst=original[clause:],changed[clause:]
    return (_object_predicate_candidate_fits(src,dst,cut-clause,faces,spelling=spelling)
            or spelling and _mixed_action_note_first_spelling(line,start,end,surface))


def _finite_written_predicate(candidate):
    from morphology import tokenize
    parts=tokenize(candidate)
    if not parts or parts[0].start or parts[-1].end!=len(candidate):return False
    # Sentence particles attach to an already completed predicate. Their
    # exact native reading proof also covers supported casual spellings.
    end=len(parts)
    while end and parts[end-1].pos=='助詞' and '終助詞' in parts[end-1].pos_sub:end-=1
    if end<len(parts):
        from particle_frames import native_final_particle_sequence
        if not end or not native_final_particle_sequence(parts[end:]):return False
    core=parts[:end];last=core[-1]
    if not _productive_predicate(candidate[:last.end],core[0].surface):return False
    return _completed_predicate_token((last.surface,last.pos+':'+last.pos_sub,last.reading,
        last.start,last.end,last.has_reading,last.infl_form))


def _changed_shifted_predicate_tail_allowed(line,start,end,surface):
    from pos_grammar import unexplained_shifted_predicate_tails
    frames=unexplained_shifted_predicate_tails(line)
    if not frames:return True
    from difflib import SequenceMatcher
    changed=line[:start]+surface+line[end:]
    matcher=SequenceMatcher(None,line,changed,autojunk=False)
    edits=[(a,b,c,d) for tag,a,b,c,d in matcher.get_opcodes() if tag!='equal']
    blocks=matcher.get_matching_blocks()
    for begin,finish,cut,reading in frames:
        if not any(a<finish and begin<b or a==b and begin<=a<finish for a,b,c,d in edits):continue
        head=next((block for block in blocks if block.a<=begin and cut<=block.a+block.size),None)
        if head is None:return False
        mapped_begin=head.b+begin-head.a
        mapped_finish=next((block.b+finish-block.a for block in blocks
                            if block.a<=finish<=block.a+block.size),None)
        if mapped_finish is None:
            mapped_finish=next((d for a,b,c,d in edits if b==finish),None)
        if mapped_finish is None or not _finite_written_predicate(changed[mapped_begin:mapped_finish]):return False
    return True


def _changed_adjective_excess_allowed(line,start,end,surface):
    """An actual adjective/excess connection keeps its own native head.

    The best parse of a proposal can introduce a conjunction between them;
    that does not repair the original bound degree expression. Other native
    clauses, including an original conjunction, provide no such constraint.
    """
    from morphology import tokenize,native_spelling_only,native_excess_head
    from difflib import SequenceMatcher
    source=tokenize(line)
    frames=[(head,tail) for head,tail in zip(source,source[1:])
        if head.has_reading and head.pos=='形容詞' and head.pos_sub=='自立'
        and head.end==tail.start and tail.has_reading and tail.pos=='動詞'
        and tail.pos_sub=='非自立' and tail.base_form in ('すぎる','過ぎる')
        and head.start<end and start<=tail.end]
    if not frames:return True
    changed=line[:start]+surface+line[end:]
    if changed==line:return True
    blocks=SequenceMatcher(None,line,changed,autojunk=False).get_matching_blocks()
    parts=tokenize(changed)
    for head,tail in frames:
        mapped=next((b.b+tail.end-b.a for b in blocks
                     if b.a<tail.end<=b.a+b.size),None)
        if mapped is None:return False
        adjacent=[(a,b) for a,b in zip(parts,parts[1:]) if b.end==mapped
            and b.has_reading and b.pos=='動詞' and b.base_form in ('すぎる','過ぎる')
            and a.has_reading and a.end==b.start and a.pos=='形容詞'
            and native_spelling_only(head.base_form,a.base_form)
            and native_excess_head(a.surface,a.reading) is True]
        if not adjacent:return False
    return True


def changed_native_action_attachment_allowed(line,start,end,surface):
    """A narrow/wide edit cannot leave an unchanged action head unattached.

    The same source prefix evidence constructs the wider repair target.
    It does not compel a repair or supply a new anomaly. Known grammatical
    clauses and nominal compounds retain their full shared native proof.
    """
    from particle_frames import changed_past_link_allowed,changed_written_suru_allowed
    if not changed_past_link_allowed(line,start,end,surface):return False
    if not changed_written_suru_allowed(line,start,end,surface):return False
    if not _changed_shifted_predicate_tail_allowed(line,start,end,surface):return False
    if not _changed_adjective_excess_allowed(line,start,end,surface):return False
    from reading_segments import native_written_action_attachment_heads
    written=native_written_action_attachment_heads(line)
    if written:
        from difflib import SequenceMatcher
        changed=line[:start]+surface+line[end:]
        blocks=SequenceMatcher(None,line,changed,autojunk=False).get_matching_blocks()
        if any(not any(block.a<=a and z<=block.a+block.size for block in blocks)
               for a,z in written if a<end and start<z):return False
    from reading_segments import (native_completed_clause_boundaries,native_polite_action_prefixes,
                                  completed_native_reading,completed_native_source_sequence)
    lo,hi=_source_clause_bounds(line,start,end)
    original=line[lo:hi];changed=line[lo:start]+surface+line[end:hi]
    begins=[0]+[edge for edge in native_completed_clause_boundaries(original) if edge<=start-lo]
    # A best-path clause edge inside the proved action noun cannot remove
    # that noun from the common check of a narrower competing repair.
    owners=[begin for begin in begins for cut in native_polite_action_prefixes(original[begin:])
            if begin<=start-lo<begin+cut]
    begin=min(owners) if owners else max(begins)
    old=original[begin:];new=changed[begin:]
    if not old or not new or not all('ぁ'<=c<='ゖ' for c in old):return True
    for cut in native_polite_action_prefixes(old):
        if old==new:continue
        from morphology import tokenize
        from reading_segments import _written_predicate_reading_preserved
        parts=tokenize(new);readings=[]
        for part in parts:
            if all('ぁ'<=c<='ゖ' for c in part.surface):readings.append(part.surface)
            elif part.has_reading:readings.append(part.reading)
            else:return False
        reading=''.join(readings)
        if not reading.startswith(old[:cut]):return False
        if (not _written_predicate_reading_preserved(parts,0,reading)
                or not (completed_native_reading(reading) or completed_native_source_sequence(reading))):
            return False
        from reading_segments import completed_sahen_reading,native_bare_action_faces
        action=completed_sahen_reading(reading,allow_nonpolite=True,return_action=True)
        if (action and old[:cut]==new[:cut] and action in native_bare_action_faces(old[:cut])
                and not _is_reading(new[cut:])):
            # Reading も+します may be valid, while written 燃します is
            # a content verb. Reconstruct only the unchanged action noun;
            # its actual written tail still passes the shared POS proof.
            if not _productive_predicate(action+new[cut:],action):return False
    return True


def _completed_verb_spelling_preserved(original,changed,edge):
    """A proven object licenses only its own verb's same-reading spelling."""
    from difflib import SequenceMatcher
    from morphology import tokenize,native_spelling_only
    from reading_segments import native_literal_argument_chain
    from semantic_roles import candidate_evidence
    matcher=SequenceMatcher(None,original,changed,autojunk=False)
    mapped=next((block.b+edge-block.a for block in matcher.get_matching_blocks()
                 if block.a<edge<=block.a+block.size),None)
    if mapped is None:return False
    old=original[:edge];new=changed[:mapped]
    literal_projection=native_spelling_only(old,new)
    old_verbs=[t for t in tokenize(old) if t.pos=='動詞' and t.pos_sub=='自立'
               and t.has_reading and t.end<edge]
    new_verbs=[t for t in tokenize(new) if t.pos=='動詞' and t.pos_sub=='自立'
               and t.has_reading and t.end<mapped]
    if not old_verbs or not new_verbs:return False
    source=old_verbs[-1];target=new_verbs[-1]
    prefix_projected=old[:source.start]!=new[:target.start]
    if (source.surface==target.surface and not prefix_projected or source.reading!=target.reading
            or source.infl_form!=target.infl_form
            or prefix_projected and not literal_projection
            or old[source.end:]!=new[target.end:]
            or not native_spelling_only(source.reading,source.surface)
            or not native_spelling_only(source.reading,target.surface)):
        return False
    # Written homophones may change only when the same explicit source
    # meaning relationship has selected that exact verb boundary. This does
    # not reopen an otherwise natural earlier clause because a later one is odd.
    if not literal_projection:
        from context_meaning import supports_span
        if not supports_span(original,changed,source.start,source.end,
                             target.start,target.end,target.surface):return False
    before=new[:target.start] if prefix_projected else old[:source.start]
    objects=[noun for noun,case,a,b in native_literal_argument_chain(before) if case=='を']
    if len(objects)!=1:
        from semantic_roles import object_before
        def legacy(text):
            return [(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                     t.start,t.end,t.has_reading,t.infl_form) for t in tokenize(text)]
        noun=object_before(changed,target.start,legacy) if prefix_projected else object_before(original,source.start,legacy)
        if not noun:return False
        objects=[noun]
    proof=candidate_evidence(objects[0],target.surface,changed[target.end:],before)
    return bool(proof and proof['shared_roles'])


def _completed_meaning_spelling_preserved(original,changed,edge):
    """A native completed clause also admits its proved same-reading meaning.

    The evidence must name the changed source word itself. Neither another
    faulty clause nor generic lexical existence can reopen this prefix.
    """
    from context_meaning import anomalous_frames,supports_span
    frames=[f for f in anomalous_frames(original) if f['end']<=edge]
    if not frames:return False
    from morphology import native_spelling_only
    from reading_segments import native_completed_clause_boundaries
    for frame in frames:
        a,b=frame['start'],frame['end']
        if original[:a]!=changed[:a]:continue
        # Only the source word changes: all following characters retain
        # their exact order through the end of this completed clause.
        suffix=original[b:]
        if suffix and not changed.endswith(suffix):continue
        end=len(changed)-len(suffix) if suffix else len(changed)
        if end<=a:continue
        face=changed[a:end]
        mapped=edge+end-b
        if (native_spelling_only(frame['reading'],face)
            and mapped in native_completed_clause_boundaries(changed)
            and supports_span(original,changed,a,b,a,end,face)):
            return True
    return False


def preserves_completed_reading_link(line,start,end,surface):
    """Shared final contract: a candidate retains a proved source clause/link."""
    from reading_segments import native_completed_clause_boundaries,native_nominal_topic_prefix
    lo,hi=_source_clause_bounds(line,start,end)
    original=line[lo:hi]
    changed=line[lo:start]+surface+line[end:hi]
    topic=native_nominal_topic_prefix(original)
    if topic and start-lo<topic and changed[:topic]!=original[:topic]:return False
    return all(start-lo>=edge or changed[:edge]==original[:edge]
               or _completed_verb_spelling_preserved(original,changed,edge)
               or _completed_meaning_spelling_preserved(original,changed,edge)
               for edge in native_completed_clause_boundaries(original))


def _reading_strength(reading):
    direct=(reading.source in ('current_ime_occurrence','original_spelling','literal_kana')
            or (reading.segments and all(s[3] in ('literal_kana','current_ime_occurrence') for s in reading.segments)))
    native=bool(reading.source=='native_nominal_completion' or reading.segments and all(s[3] in ('literal_kana','current_ime_occurrence','analyzed_word') for s in reading.segments))
    saved=reading.source=='saved_ime_pair'
    context_roundtrip=(reading.source=='ime_context_roundtrip' and reading.rank==0
        and bool(reading.segments) and reading.segments[0][0]==0
        and all(a<b and kind=='ime_context_word' for a,b,rd,kind in reading.segments)
        and all(left[1]==right[0] for left,right in zip(reading.segments,reading.segments[1:]))
        and ''.join(segment[2] for segment in reading.segments)==reading.text)
    first=reading.source=='ime_first_roundtrip' or context_roundtrip
    # A dictionary analysis is stronger than a speculative reverse reading,
    # but it is not the person's committed IME reading or a proved roundtrip.
    return (0 if direct else 1 if first else 2 if saved else 3 if native
            else 4 if reading.source=='ime_source_candidate' else 5,
            reading.rank, reading.text,
            reading.segments, reading.source)


def merge_readings(readings):
    """SR-C: evidence belongs to a reading, not the path that arrived first."""
    merged={}
    for reading in readings:
        old=merged.get(reading.text)
        evidence=set(reading.provenance or ((reading.source,reading.rank,reading.segments),))
        if old:
            evidence.update(old.provenance)
            reading=min((old,reading),key=_reading_strength)
        merged[reading.text]=replace(reading,provenance=tuple(sorted(evidence)))
    return sorted(merged.values(),key=_reading_strength)


def needs_ime_context_projection(reading):
    """A whole IME reading retains its spelling route after native attestation.

    Individually known words do not prove that their malformed combination
    is complete. Observed/saved direct input keeps its existing source route.
    """
    evidence=reading.provenance or ((reading.source,reading.rank,reading.segments),)
    return (any(source in ('ime_context_roundtrip','ime_first_roundtrip','ime_source_candidate')
                for source,rank,segments in evidence)
            and not any(source in ('current_ime_occurrence','saved_ime_pair','original_spelling')
                        for source,rank,segments in evidence))


def needs_source_argument_proof(reading):
    """Only guessed source readings need extra positive argument evidence.

    Evidence is merged by reading, so a native attestation cannot become
    weaker just because another route guessed the same reading first.
    This governs new candidates, never the validity of an unknown original.
    """
    evidence=reading.provenance or ((reading.source,reading.rank,reading.segments),)
    direct={'current_ime_occurrence','saved_ime_pair','ime_first_roundtrip','original_spelling'}
    native={'literal_kana','literal_mark_key','analyzed_word','dictionary_word',
            'current_ime_occurrence','saved_ime_segment'}
    for source,rank,segments in evidence:
        if source in direct:return False
        if (source in ('token_sequence','contextual_token_sequence') and segments
                and all(segment[3] in native for segment in segments)):return False
    return any(source in ('ime_reverse','ime_context_roundtrip','ime_source_candidate','character_guess',
                           'kanji_guess','token_sequence','contextual_token_sequence')
               or any(segment[3] in ('character_guess','unrecognized_ime_sequence','compound_voicing','source_nominal_voicing')
                      for segment in segments)
               for source,rank,segments in evidence)



from contextvars import ContextVar
_SEARCH=ContextVar('correctnote_contextual_search',default=None)
_SKIP_MIXED_REOPEN=ContextVar('correctnote_skip_mixed_reopen',default=None)


def _bounded(rows,limit,kind):
    rows=list(rows)
    search=_SEARCH.get()
    if search is not None:
        count=search.setdefault(kind,dict(limit=limit,observed=0,examined=0,unexplored=False))
        count['observed']+=len(rows)
        count['examined']+=min(len(rows),limit)
        count['unexplored']|=len(rows)>limit
    return rows[:limit]


def _with_search_report(fn):
    from functools import wraps
    @wraps(fn)
    def wrapped(*args,**kwargs):
        search={};token=_SEARCH.set(search)
        try:
            surface,diagnostic=fn(*args,**kwargs)
            limited=any(row['unexplored'] for row in search.values())
            diagnostic['search']={'state':'truncated' if limited else 'complete',
                                  'scope':'contextual_candidates','limits':search}
            if not surface and diagnostic.get('status')=='no_candidate' and limited:
                diagnostic['status']='unexplored_no_valid_candidate'
            return surface,diagnostic
        finally:_SEARCH.reset(token)
    return wrapped



from morphology import compound_voiced_reading as _compound_voiced_reading


def _keeps_native_inflection_readings(reading,parts):
    """Weak reverse guesses keep the original word's attested inflection."""
    evidence=reading.provenance or ((reading.source,reading.rank,reading.segments),)
    if any(source in ('current_ime_occurrence','saved_ime_pair','original_spelling',
            'ime_first_roundtrip','ime_context_roundtrip','ime_source_candidate')
            for source,rank,segments in evidence):return True
    from morphology import dictionary_inflections
    constraints=[]
    for i,token in enumerate(parts):
        if not (token[5] and token[1].startswith(('動詞:自立','形容詞:自立'))
                and any('一'<=c<='鿿' for c in token[0])
                and any('ぁ'<=c<='ゖ' for c in token[0])):continue
        readings={rd for pos,form,base,rd in dictionary_inflections(token[0]) or ()
            if pos.startswith(token[1].split(':')[0]+',自立,')
            and form==token[6]}
        # A nominal compound can contain a continuative verb (e.g. 色付け).
        # Its voiced member keeps the same native form and source word edge.
        # Generation must already attest nominal use; an arbitrary reverse
        # guess cannot borrow this alternative for a real finite verb.
        voiced=set()
        if (i and token[1].startswith('動詞:自立') and token[6].startswith('連用')
                and parts[i-1][1].startswith('名詞') and parts[i-1][4]==token[3]
                and '一'<=parts[i-1][0][-1]<='鿿' and '一'<=token[0][0]<='鿿'):
            voiced={rd for rd in map(_compound_voiced_reading,readings) if rd}
        if token[2] in readings:constraints.append((token[3],token[4],readings,voiced))
    if not constraints:return True
    for source,rank,segments in evidence:
        compatible=True
        for start,end,readings,voiced in constraints:
            hit=[(a,b,rd) for a,b,rd,kind in segments if start<=a<b<=end]
            compound=any(a==start and b==end and rd in voiced and kind=='compound_voicing'
                         for a,b,rd,kind in segments)
            if not (compound or hit and hit[0][0]==start and hit[-1][1]==end
                    and all(left[1]==right[0] for left,right in zip(hit,hit[1:]))
                    and ''.join(rd for a,b,rd in hit) in readings):
                compatible=False;break
        if compatible:return True
    return False


def _readings_with_native_inflections(rows,parts):
    """Validate each source proof before merging equal readings.

    A valid weak branch does not validate a different, incompatible native
    provenance merely because both happen to spell the same kana sequence.
    """
    supported=[]
    for reading in rows:
        for source,rank,segments in (reading.provenance or
                ((reading.source,reading.rank,reading.segments),)):
            proof=Reading(reading.text,source,rank,segments)
            if _keeps_native_inflection_readings(proof,parts):
                supported.append(proof)
    return merge_readings(supported)


def _marked_single_kanji_nominal_run(target, parts, index):
    """Only the original anomalous, unlexicalized run can hide okurigana.

    A best-parse noun is not evidence against a native inflection stem when
    the same source run is already malformed. Whole dictionary words and
    all ordinary source tokens retain their original reading restrictions.
    """
    def single(part):
        return len(part[0])==1 and '一'<=part[0]<='鿿' and part[1].startswith('名詞')
    if (target.boundary_kind!='lexical' or not target.structural
            or not target.anomalies or not single(parts[index])):return False
    left=right=index
    while left and single(parts[left-1]) and parts[left-1][4]==parts[left][3]:left-=1
    while right+1<len(parts) and single(parts[right+1]) and parts[right][4]==parts[right+1][3]:right+=1
    if left==right:return False
    start=target.start+parts[left][3];end=target.start+parts[right][4]
    if not any(a<end and start<b for _,_,a,b in target.anomalies):return False
    from morphology import dictionary_inflections
    whole=''.join(part[0] for part in parts[left:right+1])
    return not any(pos.startswith('名詞,') for pos,form,base,rd in dictionary_inflections(whole) or ())


def _complete_native_stem_family_limits(token_options, limit, existing_readings=0):
    """Share only unused space of two complete, source-attested families.

    Count every provenance-bearing branch before enumerating either beam.
    The original combined allowance remains twice limit; direct/saved/IME
    readings reserve ordinary space first. No candidate or preferred stem
    supplies capacity. Overflow retains the original all-option beam and
    source-bound route, including their truthful unexplored state.
    """
    ordinary=1;stems=0;ordinary_peak=1;stem_peak=0
    for token,options,hidden in token_options:
        all_options=set(options);hidden_options=set(hidden)
        stems=stems*len(all_options)+ordinary*len(hidden_options)
        ordinary*=len(all_options-hidden_options)
        ordinary_peak=max(ordinary_peak,ordinary)
        stem_peak=max(stem_peak,stems)
        if ordinary_peak+existing_readings+stem_peak>2*limit:return None
    if not stems:return None
    # Keep the original equal quotas when both fit; otherwise transfer
    # only space that the other complete family demonstrably cannot use.
    ordinary_limit=max(ordinary_peak+existing_readings,min(limit,2*limit-stem_peak))
    return ordinary_limit,2*limit-ordinary_limit


def reading_evidence(target, tokenize, dictionary, limit=32):
    """IME対応→辞書の語/活用→未知部分の一字推測。語の読みを壊さない。"""
    import kanji_guess
    from inflected_lexicon import dictionary_readings
    if target.boundary_kind=='numeric_mark_counter':
        from analysis_work import occurrence_readings
        from numeric_mark_repair import counter_faces
        rows=[Reading(target.candidate_reading,'native_mark_normalization',0)]
        for source,values in (
                ('current_ime_occurrence',occurrence_readings(target.source,target.start,target.end)),
                ('saved_ime_pair',kanji_guess.ime_readings_for(target.text))):
            rows.extend(Reading(rd,source,rank) for rank,rd in enumerate(values)
                        if rd==target.candidate_reading or counter_faces(rd))
        return merge_readings(rows)
    if target.spelling:
        f=target.spelling[0]
        # Keep the actually written small vowel in the reading to be repaired.
        return (Reading(f.reading[:-1]+f.original[-1], 'original_spelling', 0),)
    text = target.text
    out = {}
    def add(reading):
        if _is_input_reading(reading.text):
            out[reading.text]=merge_readings([out[reading.text],reading] if reading.text in out else [reading])[0]
    from analysis_work import occurrence_readings
    for rd in occurrence_readings(target.source,target.start,target.end):
        add(Reading(rd,'current_ime_occurrence',0))
    for rank, rd in enumerate(kanji_guess.ime_readings_for(text)):
        add(Reading(rd, 'saved_ime_pair', rank))
    # A written IME error can split lexical words at the wrong boundaries.
    # Query the IME's reverse reading only for such source-side evidence,
    # then check whether normal first conversion reproduces this exact text.
    # A different first output still leaves the reading as a weaker clue.
    confirmed_first=False
    inverse_failed=False
    allow_weak_reverse=(target.structural and
        (any(mark[0]=='IME逆読み' for mark in target.anomalies)
         or target.boundary_kind=='lexical' and bool(target.anomalies)
            and any('一'<=c<='鿿' for c in text)
         or any(c in 'ぁぃぅぇぉ' for c in text)
            and any('一'<=c<='鿿' for c in text)))
    exact_lexical=(not target.structural and target.boundary_kind=='lexical'
        and bool(target.anomalies) and any('一'<=c<='鿿' for c in text))
    if allow_weak_reverse or exact_lexical:
        try:
            from ime_inverse_gate import _CORRECTION_CACHE
            cache=_CORRECTION_CACHE.get()
            cached=cache is not None and ('phonetic',text) in cache
            if cached:
                inferred=cache['phonetic',text]
                morph=cache.get(('morph',text))
                first_match=cache.get(('first_match',text),False)
            else:
                from ime_language import JapaneseIME
                with JapaneseIME() as ime:
                    morph=ime.reverse_words(text) if ime.available else None
                    inferred=(morph[0] if morph else
                              ime.phonetic(text) if ime.available else None)
                    first_match=bool(inferred and ime.convert(inferred)==text)
            inverse_failed=bool(morph and not first_match)
            if (inferred and _is_input_reading(inferred)
                    and (first_match or allow_weak_reverse)):
                segments=tuple((a,b,inferred[c:d],'ime_reverse_word')
                    for a,b,c,d,pos,flags in morph[1]) if morph else ()
                add(Reading(inferred,
                    'ime_first_roundtrip' if first_match else 'ime_reverse',
                    0,segments))
                confirmed_first=first_match
            # Keep the source hypothesis already verified by the inverse gate.
            # Search membership is weaker than exact first conversion and
            # retains the original argument and final replacement checks.
            if cache is not None:
                for rank,(rd,attested_first) in enumerate(cache.get(('source_readings',text),())):
                    if _is_input_reading(rd):
                        add(Reading(rd,'ime_first_roundtrip' if attested_first
                                    else 'ime_source_candidate',rank))
                        confirmed_first=confirmed_first or attested_first
        except (ImportError,OSError,AttributeError):
            pass
    normalized_input_possible=(confirmed_first and any(
        any(c in 'じぢずづ' for c in row.text) for row in out.values()))
    if ((not confirmed_first or normalized_input_possible)
            and target.context!=text and target.anomalies
            and any('一'<=c<='鿿' for c in text)):
        from ime_inverse_gate import exact_context_reading
        exact=exact_context_reading(target.context,target.start-target.context_start,
                                   target.end-target.context_start)
        if not exact:
            from ime_inverse_gate import attested_context_reading
            native=attested_context_reading(target.context,target.start-target.context_start,
                                            target.end-target.context_start)
            if native:add(Reading(native[0],'contextual_token_sequence',0,native[1]))
        if exact:
            add(Reading(exact[0],'ime_context_roundtrip',0,exact[1]))
            from ime_inverse_gate import native_context_readings
            for rank,variant in enumerate(native_context_readings(target.context,
                    target.start-target.context_start,target.end-target.context_start)):
                add(Reading(variant[0],'ime_context_roundtrip',rank+1,variant[1]))
            # Exact original context and word edges attest this sequence too.
            # Keep native readings without inventing a character beam.
            confirmed_first=True
    if (inverse_failed and allow_weak_reverse and target.anomalies
            and target.boundary_kind in ('lexical','ime_scope') and target.structural
            and any('一'<=c<='鿿' for c in text)):
        from ime_inverse_gate import inverse_context_input_aliases
        for rank,alias in enumerate(inverse_context_input_aliases(target.context,
                target.start-target.context_start,target.end-target.context_start)):
            add(Reading(alias[0],'ime_context_roundtrip',rank+1,alias[1]))
            confirmed_first=True
    if target.anomalies and any(c in '゛゜' for c in text):
        from ime_inverse_gate import exact_mark_context_reading
        exact=exact_mark_context_reading(target.context,target.start-target.context_start,
                                        target.end-target.context_start)
        if exact:
            add(Reading(exact[0],'ime_context_roundtrip',0,exact[1]))
            from ime_inverse_gate import native_context_readings
            for rank,variant in enumerate(native_context_readings(target.context,
                    target.start-target.context_start,target.end-target.context_start,mark_keys=True)):
                add(Reading(variant[0],'ime_context_roundtrip',rank+1,variant[1]))
            # The exact parent round trip also proves this complete
            # word-aligned range. Retain native readings, but do not invent
            # character guesses for an already attested source sequence.
            confirmed_first=True
    # The IME's exact first-conversion round trip is a direct source
    # hypothesis for an already proved anomaly, including lexical errors.
    # A failed round trip remains a weaker source hypothesis only for
    # the independently anomalous ranges admitted above.
    # An exact first conversion is one source hypothesis. It must not
    # erase independently attested native readings of the original text.
    # Once this whole reading exists, no speculative character beam is
    # needed merely to manufacture more alternatives.
    beam = [('', 0, ())]
    # Preserve the original all-option search unless both source families
    # can be fully expanded inside their existing combined allowance.
    # Sharing only unused space cannot create a third resource allowance
    # beside the original source-bound nominal-tail route.
    hidden_stem_beam=[]
    token_options=[]
    local_start=target.start-target.context_start
    local_end=target.end-target.context_start
    contextual=[t for t in tokenize(target.context) if local_start<=t[3] and t[4]<=local_end]
    use_context=bool(contextual and contextual[0][3]==local_start
        and contextual[-1][4]==local_end and ''.join(t[0] for t in contextual)==text)
    # 切り出す前に判定できていた活用と読みを、単独解析で名詞へ戻さない。
    # 原文境界とぴったり合う語だけを使い、語の途中の読みを捏造しない。
    parts=([tuple(t[:3])+(t[3]-local_start,t[4]-local_start)+tuple(t[5:]) for t in contextual]
           if use_context else list(tokenize(text)))
    if ''.join(t[0] for t in parts) != text:
        parts = []
    # A separate, already attested source frame needs its own bounded
    # lattice: native stem alternatives and the unchanged whole nominal
    # tail. It does not replace generic readings, increase their cap, or
    # promote weak stems to directly observed IME input.
    nominal_parts=_marked_native_stem_nominal_parts(target)
    stem_choices=()
    if (nominal_parts and len(parts)==len(nominal_parts)
            and all((p.surface,p.start,p.end,p.reading)==(t[0],t[3],t[4],t[2])
                    for p,t in zip(nominal_parts,parts))):
        from okurigana import NEEDS_OKURIGANA
        stem_choices=NEEDS_OKURIGANA.get(nominal_parts[0].surface,())
    stem_beam=[('',0,())] if stem_choices else []
    # A one-token native alternative may reproduce the original IME text
    # even when reverse conversion returns a different personal-name reading.
    # Keep every verified first-conversion hypothesis; the ordinary final
    # candidate ranking still decides what the writer most likely meant.
    if target.boundary_kind=='lexical' and target.anomalies:
        from ime_native_reading import source_roundtrips
        for rank,(rd,segments) in enumerate(source_roundtrips(text,parts)):
            add(Reading(rd,'ime_first_roundtrip',rank,segments))
            confirmed_first=True
    for token_number, t in enumerate(parts):
        options = []
        hidden_stem_options=[]
        literal = _input_kana(t[0])
        if _is_input_reading(literal):
            options.append((literal, 0, 'literal_mark_key' if any(c in '゛゜' for c in literal) else 'literal_kana'))
        elif t[0] in ('～','〜'):
            # The Japanese IME can render a pressed long-vowel key as a wave
            # dash. Retain the physical へ-key interpretation as an alternative.
            options.extend((('ー',0,'ime_long_vowel'),('へ',2,'physical_unshift')))
        elif t[5] and _is_reading(t[2]):
            options.append((t[2], 0, 'analyzed_word'))
        for rd in occurrence_readings(target.source,target.start+t[3],target.start+t[4]):
            options.insert(0,(rd,0,'current_ime_occurrence'))
        for rd in kanji_guess.ime_readings_for(t[0]):
            if _is_reading(rd):
                options.insert(0, (rd, 0, 'saved_ime_segment'))
        if not _is_input_reading(literal):
            # Keep native inflections and independent nominal readings.
            # A malformed noun can have the wrong subtype in the best parse;
            # one IME attestation does not make that subtype authoritative.
            native_context=None
            from morphology import dictionary_inflections
            forms=dictionary_inflections(t[0]) or ()
            # An ordinary source token does not acquire every surname
            # reading sharing its kanji. Actual IME occurrence/reverse,
            # saved readings and a native proper-name parse remain their
            # own evidence. This removes unsupported lexical senses before
            # building a Cartesian beam, not after a search limit is hit.
            proper={rd for pos,form,base,rd in forms if pos.startswith('名詞,固有名詞,')}
            ordinary={rd for pos,form,base,rd in forms if not pos.startswith('名詞,固有名詞,')}
            unsupported_names=proper-ordinary if '固有名詞' not in t[1] else set()
            if confirmed_first:
                wanted=t[1].split(':')
                native_context={rd for pos,form,base,rd in forms
                    if (pos.split(',')[:len(wanted)]==wanted
                        or target.structural and wanted[0]=='名詞' and pos.startswith('名詞,'))
                    and (not t[6] or form==t[6])}
            for rank, rd in enumerate(dictionary_readings(t[0])):
                if rd in unsupported_names:
                    from last_choice import surface_for_reading
                    if surface_for_reading(rd)!=t[0]:continue
                if native_context is not None and rd not in native_context:
                    continue
                if _is_reading(rd) and rd not in [r for r, _, _ in options]:
                    options.append((rd, rank+1, 'dictionary_word'))
        # 複合語の後項の連濁は読みの変種。未入力の濁点を補う打鍵とは区別する。
        nominal_use = (t[1].startswith('名詞') or (t[1].startswith('動詞')
                       and t[6].startswith('連用') and target.following[:1] in ('を','が','に','へ','の')))
        if (token_number and nominal_use and '一' <= t[0][0] <= '鿿'
                and parts[token_number-1][1].startswith('名詞')
                and '一' <= parts[token_number-1][0][-1] <= '鿿'):
            for rd, rank, origin in tuple(options):
                voiced=_compound_voiced_reading(rd)
                if voiced:
                    options.append((voiced, rank+1, 'compound_voicing'))
        # A damaged kana first member can hide the same compound seam as
        # a written first noun. Offer voicing only for the final attested
        # written noun. Validation must retain this exact written tail in
        # a dictionary-attested whole nominal reading; it cannot become a
        # different homophone or a free missing dakuten key.
        if (not confirmed_first and target.structural and target.anomalies
                and token_number==len(parts)-1 and token_number
                and _attested_written_nominal_tail(text,parts) is not None):
            for rd,rank,origin in tuple(options):
                if origin not in ('analyzed_word','dictionary_word'):continue
                voiced=_compound_voiced_reading(rd)
                if voiced:options.append((voiced,rank+1,'source_nominal_voicing'))
        if not options and not confirmed_first:
            options = [(r['reading'], r['rank']+2, 'character_guess') for r in
                       _bounded(kanji_guess.reading_combos_with_evidence(t[0], dictionary, max_combos=limit+1),limit,'word_readings')]
            # IMEで出来た未知の漢字列には、送り仮名が別の字に化けた訓も
            # 残す。正常な漢字語の読み制限を、この誤変換の逆算へ流用しない。
            raw = [('', 0)]
            for i, char in enumerate(t[0]):
                choices = kanji_guess._trim_okurigana_from_readings(
                    t[0], i, kanji_guess.ime_reconstruction_readings_for_char(char, dictionary), None)
                raw = sorted((prefix+rd, score+j) for prefix, score in raw
                             for j, rd in enumerate(choices))
                raw.sort(key=lambda item: (item[1], item[0]))
                raw = _bounded(raw,limit,'character_readings')
            have = {r for r, _, _ in options}
            options.extend((rd, score+4, 'unrecognized_ime_sequence')
                           for rd, score in raw if rd not in have)
        elif ((not confirmed_first or target.boundary_kind=='question_particle')
                and len(t[0]) == 1 and '一' <= t[0] <= '鿿'
                and (t[1].startswith('名詞') or target.boundary_kind=='question_particle')):
            # 一字の誤変換には、最良解析の品詞以外の音訓もあり得る。
            # 終止した丁寧節の異様な末尾も、名詞だけでなく同じ読み根拠で扱う。
            # 多字の既知語や送り仮名を持つ活用形は一字読みへ分解しない。
            existing = {r for r, _, _ in options}
            options.extend((r['reading'], r['rank']+4, 'character_guess') for r in
                           _bounded(kanji_guess.reading_combos_with_evidence(t[0], dictionary, max_combos=9),8,'single_character_readings')
                           if r['reading'] not in existing)
        # A malformed source noun run may have hidden a verb's written
        # okurigana in another IME character. Share only the existing native
        # stem table, with the same weak provenance and final source checks
        # as inverse reconstruction. No candidate supplies a source reading.
        if not confirmed_first and _marked_single_kanji_nominal_run(target,parts,token_number):
            from okurigana import NEEDS_OKURIGANA
            existing={rd for rd,_,_ in options}
            hidden_stem_options=[(rd,rank+4,'unrecognized_ime_sequence')
                for rank,rd in enumerate(NEEDS_OKURIGANA.get(t[0],()))
                if _is_reading(rd) and rd not in existing]
            options.extend(hidden_stem_options)
        # A parsed single-kanji verb can have no grammatical connection
        # to the next verb. The shared source anomaly proves that this
        # parse does not own the whole reading; reuse existing native stems
        # as weak reconstruction evidence, with the normal candidate gates.
        if (not confirmed_first and target.structural and target.anomalies
                and len(t[0])==1 and '一'<=t[0]<='鿿'
                and token_number+1<len(parts)
                and any(a<target.start+t[4] and target.start+t[3]<b
                        for _,_,a,b in target.anomalies)):
            from oddness import noncontinuative_independent_verb_mismatch
            if noncontinuative_independent_verb_mismatch(t,parts[token_number+1]):
                existing={rd for rd,_,_ in options}
                choices=kanji_guess.ime_reconstruction_readings_for_char(t[0],dictionary)
                options.extend((rd,rank+4,'unrecognized_ime_sequence')
                    for rank,rd in enumerate(_bounded(choices,8,'single_character_readings'))
                    if rd not in existing)
        token_options.append((t,options,hidden_stem_options))
    # Direct/saved/round-trip readings already occupy the ordinary cap.
    # Count them conservatively too, so source-bound readings cannot
    # recover an evicted ordinary branch as an unintended third family.
    family_limits=_complete_native_stem_family_limits(token_options,limit,len(out))
    split_stems=family_limits is not None
    ordinary_limit,hidden_limit=family_limits if split_stems else (limit,limit)
    for token_number,(t,options,hidden_stem_options) in enumerate(token_options):
        if not split_stems:hidden_stem_options=[]
        original_options=[row for row in options if row not in hidden_stem_options]
        hidden=[(prefix+rd,cost+rank,segments+((t[3],t[4],rd,origin),))
                for prefix,cost,segments in hidden_stem_beam
                for rd,rank,origin in options]
        hidden.extend((prefix+rd,cost+rank,segments+((t[3],t[4],rd,origin),))
                for prefix,cost,segments in beam
                for rd,rank,origin in hidden_stem_options)
        hidden_stem_beam=_bounded(sorted(set(hidden),key=lambda item:(item[1],item[0],item[2])),
                                 hidden_limit,'hidden_stem_token_readings')
        combined = [(prefix+rd, cost+rank, segments+((t[3], t[4], rd, origin),))
                    for prefix, cost, segments in beam for rd, rank, origin in original_options]
        # 先着で切らず、各段階で全ての枝を比較してから上限を適用する。
        beam = _bounded(sorted(set(combined), key=lambda item: (item[1], item[0],item[2])),ordinary_limit,'token_readings')
        if stem_beam:
            scoped_options=[(rd,rank,origin) for rd,rank,origin in options
                if (token_number!=0 or rd in stem_choices)
                and (token_number!=len(parts)-1 or rd==nominal_parts[-1].reading)]
            scoped=[(prefix+rd,cost+rank,segments+((t[3],t[4],rd,origin),))
                for prefix,cost,segments in stem_beam for rd,rank,origin in scoped_options]
            stem_beam=_bounded(sorted(set(scoped),key=lambda item:(item[1],item[0],item[2])),
                               limit,'source_stem_token_readings')
    for rd, rank, segments in beam if parts else ():
        add(Reading(rd, 'contextual_token_sequence' if use_context else 'token_sequence', rank, segments))
    # 語単位の読みが得られない残りを救う。既知の活用を一字推測へ置き換えない。
    if not out:
        for r in _bounded(kanji_guess.reading_combos_with_evidence(text, dictionary, max_combos=limit+1),limit,'fallback_readings'):
            add(Reading(r['reading'], r['source'], r['rank']))
    ordinary=_bounded(_readings_with_native_inflections(out.values(),parts),ordinary_limit,'readings')
    source_stems=[]
    for rd,rank,segments in stem_beam:
        row=Reading(rd,'contextual_token_sequence' if use_context else 'token_sequence',rank,segments)
        if _marked_native_stem_nominal_tail(target,row) is not None:
            source_stems.extend(_readings_with_native_inflections((row,),parts))
    hidden_rows=[Reading(rd,'contextual_token_sequence' if use_context else 'token_sequence',rank,segments)
                 for rd,rank,segments in hidden_stem_beam]
    hidden_rows=_readings_with_native_inflections(hidden_rows,parts)
    return merge_readings(ordinary+_bounded(hidden_rows,hidden_limit,'hidden_stem_readings')
                          +_bounded(source_stems,limit,'source_stem_readings'))


def _render(keys):
    out = ''
    for c in keys:
        if c in ('゛', '゜') and out:
            combined = unicodedata.normalize('NFC', out[-1] + ('\u3099' if c == '゛' else '\u309a'))
            if len(combined) == 1:
                out = out[:-1] + combined
                continue
        out += c
    return out


@lru_cache(maxsize=128)
def _key_neighbors(key):
    import kana_layout as k
    return tuple((other, k.kana_key_distance(key, other)) for other in k.KANA_POSITIONS
                 if not k.same_physical_key(key, other)
                 and 0 < k.kana_key_distance(key, other) <= 1.05)


def key_repairs(reading, before='', after=''):
    """かなを実際の打鍵に開いた一手。濁点も同じ置換/巻き込みの規則で扱う。"""
    import kana_layout as k
    from vocabulary import dup_repair_enabled
    keys = tuple(key for c in reading for key in k.keystrokes(c))
    left_key = k.keystrokes(before[-1])[-1] if before else None
    right_key = k.keystrokes(after[0])[0] if after else None
    out = ({reading: KeyRepair(reading, 'same_reading', -1, '', '', 0.0)}
           if _is_reading(reading) else {})
    def add(changed, kind, position, pressed, intended, cost):
        rd = _render(changed)
        if rd == reading or not _is_reading(rd):
            return
        row = KeyRepair(rd, kind, position, pressed, intended, cost)
        old = out.get(rd)
        if old is None or (row.cost, row.operation, row.position) < (old.cost, old.operation, old.position):
            out[rd] = row
    for i, key in enumerate(keys):
        for other, distance in _key_neighbors(key):
            if (key in '゛゜' or other in '゛゜') and not k.mark_slip_enabled():
                continue
            add(keys[:i]+(other,)+keys[i+1:], 'adjacent_substitution', i, key, other, 1.0)
        adjacent = [keys[j] for j in (i-1, i+1) if 0 <= j < len(keys)]
        # 語を切り出しても、直前・直後に実際に打たれたキーを失わない。
        # 範囲外の文字は変更せず、端の1打を巻き込んだ根拠にだけ使う。
        if i==0 and left_key is not None:
            adjacent.append(left_key)
        if i==len(keys)-1 and right_key is not None:
            adjacent.append(right_key)
        if not any(k.same_physical_key(key,neighbor) for neighbor in adjacent) and any(0 < k.intrusion_key_distance(key, neighbor) <= 1.0 for neighbor in adjacent):
            add(keys[:i]+keys[i+1:], 'adjacent_intrusion', i, key, '', 1.0)
        if any(k.same_physical_key(key,neighbor) for neighbor in adjacent) and dup_repair_enabled():
            add(keys[:i]+keys[i+1:], 'duplicate', i, key, '', 1.0)
        if i+1 < len(keys) and key != keys[i+1]:
            add(keys[:i]+(keys[i+1], key)+keys[i+2:], 'transposition', i,
                key+keys[i+1], keys[i+1]+key, 1.0)
        # A missed voicing key is one physical insertion, not an adjacent
        # replacement of the base kana or an invented Shift press.
        if k.mark_slip_enabled() and key not in '゛゜' and (i+1==len(keys) or keys[i+1] not in '゛゜'):
            for mark in '゛゜':
                if len(_render((key,mark)))==1:
                    add(keys[:i+1]+(mark,)+keys[i+1:],'omission',i+1,'',mark,k.MISSING_KEY_COST)
        if key in k.SHIFT_KANA_PAIR:
            other = k.SHIFT_KANA_PAIR[key]
            add(keys[:i]+(other,)+keys[i+1:], 'shift', i, key, other, 0.4)
    return tuple(sorted(out.values(), key=lambda row: (row.cost, row.reading)))



def nonadjacent_key_repairs(reading):
    """One bounded source-key substitution from the existing layout model.

    These finite distances already distinguish two-key-width slips from FAR.
    Do not invent an intermediate key, combine this slip with another edit,
    or reinterpret a changed Shift state as a single physical substitution.
    """
    import kana_layout as k
    keys=tuple(key for char in reading for key in k.keystrokes(char))
    for position,key in enumerate(keys):
        for other in k.KANA_POSITIONS:
            if (key in '゛゜' or other in '゛゜') and not k.mark_slip_enabled():continue
            distance=k.kana_key_distance(key,other)
            if not 1.05<distance<k.FAR:continue
            restored=_render(keys[:position]+(other,)+keys[position+1:])
            if restored!=reading and _is_reading(restored):
                yield KeyRepair(restored,'nonadjacent_substitution',position,key,other,distance)

def adjacent_shift_key_repairs(reading):
    """One-key-late Shift window at an original i-row yoon onset.

    Both adjacent events retain their physical base keys and actual costs.
    Anomaly detection, native clause proof and final validation stay shared.
    """
    import kana_layout as k
    keys=tuple(key for char in reading for key in k.keystrokes(char))
    from morphology import _YOON_BASES
    for index,(left,right) in enumerate(zip(keys,keys[1:])):
        if left not in 'やゆよ' or right not in 'ぁぃぅぇぉ':continue
        before=_render(keys[:index])
        if not before or before[-1] not in _YOON_BASES:continue
        a,b=k.SHIFT_KANA_PAIR[left],k.SHIFT_KANA_PAIR[right]
        intermediate=_render(keys[:index]+(a,)+keys[index+1:])
        restored=_render(keys[:index]+(a,b)+keys[index+2:])
        if restored==reading or not _is_reading(restored):continue
        steps=(KeyRepair(intermediate,'shift',index,left,a,0.4),
               KeyRepair(restored,'shift',index+1,right,b,0.4))
        yield ClauseKeyRepair(restored,'adjacent_shift_pair',index,left+right,a+b,0.8,steps)


def held_shift_key_repairs(reading):
    """Consecutive presses of one shifted vowel retain every base key.

    The visible run identifies a held Shift state, not a repeated-key
    deletion. Each event keeps its original position and ordinary cost.
    """
    import kana_layout as k
    keys=tuple(key for char in reading for key in k.keystrokes(char))
    for run in re.finditer(r'([ぁぃぅぇぉ])\1+', ''.join(keys)):
        changed=list(keys);steps=[]
        for position in range(run.start(),run.end()):
            pressed=keys[position];intended=k.SHIFT_KANA_PAIR[pressed]
            changed[position]=intended
            steps.append(KeyRepair(_render(changed),'shift',position,pressed,intended,0.4))
        restored=steps[-1].reading
        if _is_reading(restored):
            yield ClauseKeyRepair(restored,'held_shift_run',run.start(),run.group(),
                ''.join(changed[run.start():run.end()]),sum(step.cost for step in steps),tuple(steps))


def neighbor_shift_key_repairs(reading):
    """A different base key cannot also change its Shift state.

    User policy 2026-10-05: a small ゅ cannot become a large よ.
    Do not recreate this excluded substitution by composing two events
    at one position. A distant を supplies no Shift evidence for it.
    Same-key Shift and disjoint-key repairs retain their own contracts.
    """
    return ()


def _source_marked_nominal_suru_omission(target, reading):
    """A source noun and actual complete suru tail share the existing anomaly.

    This permits lexical generation only. The nominal candidate must still
    satisfy the same suru slot, original keys and final context validation.
    Neither an unknown noun nor a detached or unfinished tail supplies proof.
    """
    if (target.boundary_kind!='lexical' or not target.structural
            or not target.anomalies or target.spelling or target.preserved_head):
        return False
    from morphology import tokenize,dictionary_inflections,native_suru_form
    parts=tokenize(target.context)
    lo=target.start-target.context_start;hi=target.end-target.context_start
    heads=[part for part in parts if lo<=part.start and part.end<=hi]
    if (not heads or heads[0].start!=lo or heads[-1].end!=hi
            or ''.join(part.surface for part in heads)!=target.text
            or any(a.end!=b.start for a,b in zip(heads,heads[1:]))):return False
    for part in heads:
        if not part.has_reading or part.pos!='名詞':return False
        forms=tuple(row for row in dictionary_inflections(part.surface) or ()
                    if row[0].startswith('名詞,') and row[3]==part.reading)
        if not forms:return False
    if len(heads)==1:
        if heads[0].reading!=reading or any(row[0].startswith('名詞,サ変接続,') for row in forms):
            return False
    else:
        # The source may have split an unlexicalized noun run into real
        # one-kanji nouns. Its final noun owns the same malformed suru
        # connection; none of its readings becomes an observed key history.
        legacy=[(part.surface,part.pos+':'+part.pos_sub,part.reading,
                 part.start-lo,part.end-lo,part.has_reading,part.infl_form) for part in heads]
        if (not all(len(part.surface)==1 for part in heads)
                or not _marked_single_kanji_nominal_run(target,legacy,0)):return False
    head=heads[-1]
    tail=[part for part in parts if part.start>=hi]
    if not tail:return False
    action=tail[0]
    if (action.start!=hi or not action.has_reading or action.pos!='動詞'
            or action.base_form!='する'
            or not native_suru_form(action.surface,action.infl_form,action.reading,False)
            or not any(a<=target.context_start+head.start and target.context_start+action.end<=b
                       for _,_,a,b in target.anomalies)
            or ''.join(part.surface for part in tail)!=target.following
            or any(a.end!=b.start for a,b in zip(tail,tail[1:]))):return False
    action_forms=tuple(row for row in dictionary_inflections(action.surface) or ()
                       if row[0].startswith('動詞,自立,') and row[1]==action.infl_form
                       and row[2]=='する' and row[3]==action.reading)
    if not action_forms:return False
    last=tail[-1]
    if (_completed_predicate_token((last.surface,last.pos+':'+last.pos_sub,
            last.reading,last.start,last.end,last.has_reading,last.infl_form))
            and _allows_grammatical_tail(action_forms,
                target.following[len(action.surface):],action.reading,action.surface)):
        return True
    # An actual source connective can close this predicate before another
    # clause. Prove only the unchanged suru and its own grammatical tail;
    # a later action/argument supplies neither lexical nor semantic support.
    from reading_segments import native_predicate_link_boundaries
    return any(action.end<edge<len(target.context)
        # A connective alone is not a finished tail. There must actually
        # be following lexical material in this same source clause/column;
        # extra particles or punctuation do not supply a later clause.
        # This proves presence only, not that material's meaning/grammar.
        and any(part.start>=edge and part.pos in
                ('名詞','動詞','形容詞','副詞','連体詞','接頭詞') for part in tail)
        and _allows_grammatical_tail(action_forms,target.context[action.end:edge],
                                    action.reading,action.surface)
        for edge in native_predicate_link_boundaries(target.context,hi))


def lexical_omission_repairs(reading,dictionary,include_shift=False,nominal_compound=False,native_tails=()):
    """One missing physical key, restricted to existing lexical candidates."""
    import kana_layout as k
    from reading_segments import native_deverbal_compound_parts
    if dictionary is None or not _is_reading(reading):return ()
    keys=tuple(key for char in reading for key in k.keystrokes(char))
    insertions=tuple(key for key in k.KANA_POSITIONS
                     if (include_shift or key not in k._SHIFT_KANA) and
                     (key not in '゛゜' or k.mark_slip_enabled()))
    found={}
    for position in range(len(keys)+1):
        for key in insertions:
            restored=_render(keys[:position]+(key,)+keys[position:])
            if not _is_reading(restored) or restored==reading:continue
            if not (dictionary.surfaces_for_reading(restored,limit=1,band=True)
                    or dictionary.inflected_surfaces_for_reading(restored)
                    or nominal_compound and native_deverbal_compound_parts(restored)
                    or any(restored.endswith(tail_reading) and face.endswith(tail)
                           for tail,tail_reading in native_tails
                           for face in _native_written_nominal_readings().get(restored,()))):continue
            if key in k._SHIFT_KANA:
                base=k.SHIFT_KANA_PAIR[key]
                middle=_render(keys[:position]+(base,)+keys[position:])
                steps=(KeyRepair(middle,'omission',position,'',base,k.MISSING_KEY_COST),
                       KeyRepair(restored,'shift',position,base,key,0.4))
                row=ClauseKeyRepair(restored,'omission_and_shift',position,'',key,
                                    k.MISSING_KEY_COST+0.4,steps)
            else:row=KeyRepair(restored,'omission',position,'',key,k.MISSING_KEY_COST)
            found.setdefault(restored,row)
    return tuple(found[key] for key in sorted(found))



@lru_cache(maxsize=2048)
def _native_sahen_reading_heads(reading):
    from reading_segments import _native_nominal_reading_faces,native_bare_action_faces
    out=[]
    # A longer original noun before an actual nominal particle owns its
    # internal syllables, even when that noun has no semantic label yet.
    # A shorter homophone cannot claim the rest of the clause as its tail.
    nominal_edges=[edge for edge in range(2,len(reading))
        if reading[edge] in 'をがにへでもはと' and _native_nominal_reading_faces(reading[:edge])]
    for cut in range(2,len(reading)):
        prefix=reading[:cut]
        if any(cut<=edge for edge in nominal_edges):continue
        heads=native_bare_action_faces(prefix)
        if heads:out.append((cut,prefix,heads))
    # Prefer the longest independently attested original action head.
    # Its internal homophones cannot claim a longer functional tail.
    return tuple(sorted(out,reverse=True))


@lru_cache(maxsize=2048)
def sahen_omission_repairs(reading,following=''):
    """One omitted physical key in a native action's functional tail.

    Existing source oddness owns the call. The unchanged prefix must have
    an exact native sahen reading; the tail must prove the actual suru
    paradigm and all its auxiliaries. No arbitrary word-stem insertion or
    assumed Shift is added. The common original-context checks still apply.
    """
    import kana_layout as k
    from morphology import dictionary_inflections
    keys=tuple(char for char in k.KANA_POSITIONS
               if char not in k._SHIFT_KANA and (char not in '゛゜' or k.mark_slip_enabled()))
    found={}
    for cut,prefix,heads in _native_sahen_reading_heads(reading):
        tail=reading[cut:]
        tail_keys=tuple(key for char in tail for key in k.keystrokes(char))
        offset=sum(len(k.keystrokes(char)) for char in prefix)
        for head in heads:
            forms=dictionary_inflections(head) or ()
            if (_allows_grammatical_tail(forms,tail+following,prefix,head)
                    and _productive_predicate(head+tail+following,head)):continue
            for index in range(len(tail_keys)+1):
                for key in keys:
                    changed=_render(tail_keys[:index]+(key,)+tail_keys[index:])
                    if not changed or not _is_reading(changed):continue
                    if not (_allows_grammatical_tail(forms,changed+following,prefix,head)
                            and _productive_predicate(head+changed+following,head)):continue
                    text=prefix+changed
                    found.setdefault(text,KeyRepair(text,'omission',offset+index,'',key,k.MISSING_KEY_COST))
    return tuple(found[key] for key in sorted(found))


def sahen_open_omission_repairs(reading, before='', following=''):
    """One missing suru key before the same unfinished polite auxiliary.

    The unchanged source must already contain a native open ます chain. The
    candidate's whole kana clause must pass the existing incomplete-polite
    proof; this does not complete its ending or authorize a spelling.
    """
    if not _is_reading(reading):return ()
    from reading_segments import (native_incomplete_polite_reading,
                                   native_polite_auxiliary_chains)
    import kana_layout as k
    original=before+reading+following
    chains=native_polite_auxiliary_chains(original,include_open=True)
    found=[]
    for cut,prefix,heads in _native_sahen_reading_heads(reading):
        tail=reading[cut:]
        if (not heads or not tail.startswith('ま')
                or not any(start==len(before)+cut and sig[0][1]=='ます'
                           for start,end,sig in chains)):
            continue
        repaired=prefix+'し'+tail
        if not native_incomplete_polite_reading(before+repaired+following):
            continue
        position=sum(len(k.keystrokes(c)) for c in prefix)
        found.append(KeyRepair(repaired,'omission',position,'','し',k.MISSING_KEY_COST))
    return tuple(dict((row.reading,row) for row in found).values())


def _completed_shifted_predicate(target,reading):
    """A finite completion keeps the independently proved written stem."""
    from reading_segments import completed_native_verb_reading
    if completed_native_verb_reading(reading,finite_only=True):return True
    from pos_grammar import unexplained_shifted_predicate_tails
    for start,end,cut,original in unexplained_shifted_predicate_tails(target.text):
        if start or end!=len(target.text):continue
        size=len(original)-(end-cut)
        if not reading.startswith(original[:size]):continue
        candidate=target.text[:cut]+reading[size:]
        if _finite_written_predicate(candidate):return True
    return False


def request_shift_key_repairs(target, reading, before='', after=''):
    """Release an explicit small-vowel Shift plus one physical key slip.

    Separate keys retain the native request contract. A neighboring base
    key may not be combined with a Shift-state change at that same source
    position, even when the result happens to be a finite predicate.
    """
    from pos_grammar import unexplained_shifted_predicate_tails
    written=(target.boundary_kind=='auxiliary_connection' and any(
        start==0 and end==len(target.text) and native==reading
        for start,end,cut,native in unexplained_shifted_predicate_tails(target.text)))
    if not written and (target.boundary_kind not in ('kana_request','kana_predicate') or reading!=target.text):return
    from morphology import dictionary_inflections
    seen=set()
    for first in key_repairs(reading,before,after):
        if first.operation!='shift' or first.pressed not in 'ぁぃぅぇぉ':continue
        for second in key_repairs(first.reading,before,after):
            if second.operation not in ('adjacent_substitution','adjacent_intrusion'):continue
            if not _original_intrusion_allowed(reading,second,before,after):continue
            if second.position==first.position:continue
            elif written:continue
            elif not any(pos.startswith('動詞,') and form=='命令ｉ' and rd==second.reading
                         for pos,form,base,rd in dictionary_inflections(second.reading) or ()):continue
            if second.reading in seen:continue
            seen.add(second.reading)
            yield ClauseKeyRepair(second.reading,'shift_and_key',first.position,
                first.pressed+second.pressed,first.intended+second.intended,
                first.cost+second.cost,(first,second))


def _original_intrusion_allowed(reading, repair, before='', after='', removed=()):
    """Check every dropped key against the original neighbors, including Shift."""
    if repair.operation!='adjacent_intrusion':return True
    import kana_layout as k
    keys=tuple(key for c in reading for key in k.keystrokes(c))
    i=repair.position
    if not 0<=i<len(keys) or keys[i]!=repair.pressed:return False
    adjacent=[keys[j] for j in (i-1,i+1) if 0<=j<len(keys) and j not in removed]
    if i==0 and before:adjacent.append(k.keystrokes(before[-1])[-1])
    if i==len(keys)-1 and after:adjacent.append(k.keystrokes(after[0])[0])
    return (not any(k.same_physical_key(keys[i],other) for other in adjacent)
            and any(0<k.intrusion_key_distance(keys[i],other)<=1.0 for other in adjacent))


def _search_step(kind, limit):
    """A lazy grammar search records a cutoff without exhausting its iterator."""
    from analysis_context import check_current_request
    check_current_request()
    search=_SEARCH.get()
    if search is None:return True
    count=search.setdefault(kind,dict(limit=limit,observed=0,examined=0,unexplored=False))
    count['observed']+=1
    if count['examined']>=limit:
        count['unexplored']=True
        return False
    count['examined']+=1
    return True


def independent_key_pair_repairs(reading,dictionary,before='',after=''):
    """Two disjoint original key events, independent of a sentence template.

    This combines the existing primitive slips, never two substitutions of
    one key to pretend that a distant key was pressed twice. Deletion witnesses
    are the original neighbors. Lexical filtering is only a proposal index;
    original oddness, native grammar, meaning and final checks still apply.
    """
    if dictionary is None or not _is_reading(reading):return
    import kana_layout as k
    keys=tuple(key for c in reading for key in k.keystrokes(c))
    atoms=tuple(row for row in key_repairs(reading,before,after)
                if row.operation!='same_reading'
                and _original_intrusion_allowed(reading,row,before,after))
    found={}
    lexical_cache={}
    def lexical(value):
        if value not in lexical_cache:
            lexical_cache[value]=bool(dictionary.surfaces_for_reading(value,limit=1,band=True)
                or dictionary.inflected_surfaces_for_reading(value))
        return lexical_cache[value]
    def proposed(value):
        if lexical(value):return True
        # The inflected index contains one-kana native verb stems too.
        # Their actual forms must license the whole auxiliary tail; a
        # one-character noun alone is never a predicate proposal.
        from morphology import dictionary_inflections
        for face in dictionary.inflected_surfaces_for_reading(value[:1]):
            forms=tuple(row for row in dictionary_inflections(face) or ()
                if row[0].startswith('動詞,自立,') and row[3]==value[:1])
            if forms and _allows_grammatical_tail(forms,value[1:],value[:1],face):
                return True
        return any(lexical(value[:cut]) and any(_grammatical_suffix(value[cut:],state)
                    for state in ('N','R','Bw','IST','END'))
                   for cut in range(2,len(value)))
    for first in atoms:
        a=first.position;az=a+len(first.pressed)
        for second in atoms:
            b=second.position;bz=b+len(second.pressed)
            if not a<b or az>b:continue
            # Two deleted keys cannot serve as each other's only physical
            # witness. An intrusion still needs an original neighbor which
            # survives this pair; reconstructed or inserted neighbors do not count.
            removed={i for row in (first,second) if row.operation=='adjacent_intrusion'
                       for i in range(row.position,row.position+len(row.pressed))}
            if not all(_original_intrusion_allowed(reading,row,before,after,removed)
                       for row in (first,second)):continue
            if not _search_step('independent_key_pairs',16384):return
            changed=keys[:a]+tuple(first.intended)+keys[az:b]+tuple(second.intended)+keys[bz:]
            restored=_render(changed)
            cost=first.cost+second.cost
            if restored==reading or found.get(restored,float('inf'))<=cost or not _is_reading(restored):continue
            found[restored]=cost
            if not proposed(restored):continue
            last=replace(second,reading=restored)
            yield ClauseKeyRepair(restored,'independent_key_pair',a,
                first.pressed+second.pressed,first.intended+second.intended,
                first.cost+second.cost,(first,last))
    # An omitted ordinary key is not in key_repairs' substitution atoms.
    # Reuse lexical omission proposals after one independent adjacent slip;
    # keep the actual grammatical tail and the original key coordinates.
    for first in atoms:
        if first.operation!='adjacent_substitution':continue
        for cut in range(2,len(first.reading)+1):
            tail=first.reading[cut:]
            if tail and not any(_grammatical_suffix(tail,state)
                                for state in ('N','R','Bw','IST','END')):continue
            if not _search_step('independent_omission_prefixes',16384):return
            for missing in lexical_omission_repairs(first.reading[:cut],dictionary):
                gap=missing.position
                # Equal positions do not prove two independent source events.
                if gap==first.position or missing.intended in '゛゜':continue
                restored=missing.reading+tail
                cost=first.cost+missing.cost
                if (restored==reading or not _is_reading(restored)
                        or found.get(restored,float('inf'))<=cost):continue
                found[restored]=cost
                if gap<first.position:
                    intermediate=_render(keys[:gap]+tuple(missing.intended)+keys[gap:])
                    steps=(replace(missing,reading=intermediate),replace(first,reading=restored))
                else:
                    steps=(first,replace(missing,reading=restored))
                yield ClauseKeyRepair(restored,'independent_key_pair',steps[0].position,
                    steps[0].pressed+steps[1].pressed,
                    steps[0].intended+steps[1].intended,cost,steps)


def clause_key_repairs(target, reading, before='', after=''):
    """Two separate key slips around an unchanged, positively proved clause seam.

    Used only after the single-step candidates fail. This produces readings;
    the ordinary source guard, validation and ranking still decide adoption.
    The connective and every deletion witness remain in original coordinates.
    """
    if (target.boundary_kind!='kana_predicate' or reading!=target.text
            or not 10<=len(reading)<=40):return
    from reading_segments import completed_native_reading_link, completed_native_reading_clause
    import kana_layout as k
    prefix=target.source[target.context_start:target.start]
    seen=set();prefix_count=0;tail_count=0
    for marker in re.finditer('てから|でから|ので|て|で',reading):
        cut=marker.end();ending=marker.group()
        if cut<3 or len(reading)-cut<4:continue
        left,right=reading[:cut],reading[cut:]
        # A proved original half has no second slip to explore. In particular,
        # do not generate hundreds of changes to an already complete clause
        # merely because a separate half has no accepted single-step repair.
        if (completed_native_reading_link(prefix+left,require_nominal=True)
                or completed_native_reading_clause(right+target.following,require_object_fit=True)):
            continue
        offset=sum(len(k.keystrokes(c)) for c in left)
        right_options=None
        for first in key_repairs(left,before,right):
            if (first.reading==left or not first.reading.endswith(ending)
                    or not _original_intrusion_allowed(left,first,before,right)):continue
            prefix_count+=1
            if not _search_step('clause_key_prefixes',128) or prefix_count>128:return
            if not completed_native_reading_link(prefix+first.reading,require_nominal=True):continue
            if right_options is None:
                right_options=[]
                for second in key_repairs(right,left,after):
                    if (second.reading==right
                            or not _original_intrusion_allowed(right,second,left,after)):continue
                    tail_count+=1
                    if not _search_step('clause_key_tails',256) or tail_count>256:return
                    if completed_native_reading_clause(second.reading+target.following,require_object_fit=True):
                        right_options.append(second)
            for second in right_options:
                changed=first.reading+second.reading
                if changed in seen:continue
                seen.add(changed)
                yield ClauseKeyRepair(changed,'clause_key_pair',first.position,
                    first.pressed+second.pressed,first.intended+second.intended,
                    first.cost+second.cost,(first,replace(second,position=offset+second.position)))


def _self_contained_conditional(token):
    """Native たら/だら/なら already supply the conditional connection."""
    if (len(token)<7 or not token[5] or token[1]!='助動詞'
            or token[6]!='仮定形'):
        return False
    from morphology import dictionary_inflections
    return any(pos.startswith('助動詞,') and form=='仮定形'
               and base in ('た','だ') and reading==token[2]
               for pos,form,base,reading in dictionary_inflections(token[0]) or ())


# GPT-6 / 2026-09-14: finite forms and continuative/conditional forms
# have different native connective attachments. Positive evidence only;
# particles outside this class are not thereby anomalous.
# https://www.coelang.tufs.ac.jp/mt/ja/gmod/courses/c02/lesson27/step3/explanation/094.html
# https://www.coelang.tufs.ac.jp/mt/ja/gmod/courses/c01/lesson21/step2/explanation/082.html
_FINITE_CONNECTIVES=frozenset(('が','けれども','けれど','けど','けども','し','から','と'))


@lru_cache(maxsize=4096)
def _unchanged_finite_connective(original, changed):
    """Return a native connective retained after the same finite source tail.

    This licenses proving the preceding clause, not generating an open ending.
    Both original and replacement must retain the actual final particle and a
    finite predecessor; a homographic case particle or て/ば cannot supply it.
    """
    from morphology import tokenize
    endings=[]
    for text in dict.fromkeys((original,changed)):
        parts=list(tokenize(text))
        if parts and parts[-1].surface in ('。','！','？','.','!','?'):parts.pop()
        if len(parts)<2:return None
        last,prev=parts[-1],parts[-2]
        if (not last.has_reading or last.pos!='助詞' or last.pos_sub!='接続助詞'
                or last.surface not in _FINITE_CONNECTIVES
                or not prev.has_reading or prev.end!=last.start):return None
        native=(prev.surface,prev.pos+(':'+prev.pos_sub if prev.pos_sub else ''),
                prev.reading,prev.start,prev.end,prev.has_reading,prev.infl_form)
        if not _completed_predicate_token(native):return None
        endings.append(last.surface)
    return endings[0] if endings[0]==endings[-1] else None


def _same_context_reading(tokens,reading):
    """Other dictionary readings must retain every contextual POS and form."""
    from morphology import dictionary_inflections
    # The same complete nominal pronunciation used by original-key
    # validation also applies across contiguous nominal tokenizer seams.
    # Keep the actual contextual boundaries/POS; a particle or verb cannot
    # acquire the reading of a different nominal interpretation.
    if (tokens and all(len(t)>=7 and t[5] and not t[6]
            and t[1].startswith(('名詞','接頭詞')) for t in tokens)
            and all(a[4]==b[3] for a,b in zip(tokens,tokens[1:]))):
        from reading_segments import native_attested_prefix_noun_readings
        if reading in native_attested_prefix_noun_readings(''.join(t[0] for t in tokens)):
            return True
    positions={0}
    for token in tokens:
        if len(token)<7 or not token[5]:return False
        wanted=token[1].split(':');form=token[6]
        choices={rd for pos,inflection,base,rd in dictionary_inflections(token[0]) or ()
                 if pos.split(',')[:len(wanted)]==wanted and (not form or inflection==form)}
        following={at+len(rd) for at in positions for rd in choices if reading.startswith(rd,at)}
        if not following:return False
        positions=following
    return len(reading) in positions


def _lexical_syllable_start(target):
    """Retain the original IME word containing a malformed small kana."""
    start=target.start
    if target.boundary_kind!='lexical' or len(target.text)<2 or target.text[0] not in 'ゃゅょ':
        return start
    from reading_segments import native_pronoun_case_ranges
    if (start-target.context_start in _native_marked_prefix_edges(target.context)
            or any(end==start-target.context_start for begin,end in native_pronoun_case_ranges(target.context))):
        return start
    from ime_inverse_gate import _CORRECTION_CACHE
    cache=_CORRECTION_CACHE.get()
    morph=cache.get(('morph',target.context)) if cache is not None else None
    if morph:
        for a,b,c,d,pos,flags in morph[1]:
            if a<=start-target.context_start<b:
                return target.context_start+a
    if (start>target.context_start
            and ('ぁ'<=target.source[start-1]<='ゖ' or 'ァ'<=target.source[start-1]<='ヶ')):
        return start-1
    return start


def _late_shift_candidate_complete(target,surface,reading):
    """A printed late Shift window cannot become another loose token chain.

    This is shared source-range proof for every candidate route, including
    a legacy alternative after a better candidate was explicitly blocked.
    """
    if not (target.structural and re.search(
            '[きぎしじちぢにひびぴみり][やゆよ][ぁぃぅぇぉ]',target.text)):
        return True
    from morphology import dictionary_inflections,tokenize as native_tokenize
    from reading_segments import completed_native_reading_clause,native_written_sahen_relative
    def noun(face):
        return any(pos.startswith(('名詞,一般,','名詞,サ変接続,','名詞,形容動詞語幹,'))
                   and base==face for pos,form,base,rd in dictionary_inflections(face) or ())
    if noun(surface):return True
    # An actual adjectival-noun manner + native bare action is also a
    # complete instruction memo. Its explicit 副詞化 particle and whole
    # sahen tail distinguish it from a loose N-ga-N token sequence.
    parts=native_tokenize(surface)
    if len(parts)>=3:
        head,particle=parts[:2]
        tail=surface[particle.end:]
        if (head.start==0 and head.end==particle.start
                and head.has_reading and head.pos=='名詞' and head.pos_sub=='形容動詞語幹'
                and particle.surface=='に' and particle.has_reading
                and particle.pos=='助詞' and particle.pos_sub=='副詞化'
                and any(pos.startswith('名詞,形容動詞語幹,') and base==head.base_form
                        and rd==head.reading for pos,form,base,rd in dictionary_inflections(head.surface) or ())
                and any(pos.startswith('名詞,サ変接続,') and base==tail
                        for pos,form,base,rd in dictionary_inflections(tail) or ())):return True
    if reading is None:
        if parts and all(part.has_reading for part in parts):
            reading=''.join(part.reading for part in parts)
    if reading and completed_native_reading_clause(reading,allow_nonpolite=True,
            require_object_fit=True):return True
    return any(noun(surface[cut:]) and native_written_sahen_relative(surface[:cut])
               for cut in range(1,len(surface)))


def validate(target, surface, engine, tokenize, store, dictionary, decisions=None,
             expected_reading=None, companions=(), source_reading=None):
    """同じ原文範囲への候補。直接再構築・通常置換のいずれからも呼ぶ。"""
    import oddness
    if surface is None or surface == target.text:
        return False, 'unchanged'
    if not surface:
        # An empty replacement can be a proved deletion, not an unchanged
        # candidate. Share the original mark/key/seam validator used by
        # normalization; no lexical word is licensed to disappear here.
        from mark_usage import normalized_intrusions
        from morphology import DAKUTEN_MARKS,HANDAKUTEN_MARKS
        marks=DAKUTEN_MARKS+HANDAKUTEN_MARKS
        if target.text and all(c in marks for c in target.text):
            changed=target.source[:target.start]+target.source[target.end:]
            proved=normalized_intrusions(target.source,changed,
                list(range(target.start,target.end)),tokenize,store,dictionary,decisions)
            return (True,'proved_mark_deletion') if proved else (False,'unproven_mark_deletion')
        return False,'empty_lexical_replacement'
    # 辞書にある動作名詞は、その直後の誤打だけで接続を戻せる候補を先に
    # 調べる。無ければ語本体を読む別範囲へ進み、そこで全候補を順位付けする。
    if _lexical_syllable_start(target)!=target.start:
        return False,'source_syllable_boundary'
    if target.spelling and surface!=target.spelling[0].normal:
        return False, 'spelling_stem_changed'
    if target.preserved_head and not surface.startswith(target.preserved_head):
        # A preserved kana head may gain only its exact native spelling.
        # Align complete candidate tokens; do not cut inside written words
        # or compare an IME-guessed reading to the source's lexical head.
        from morphology import tokenize as native_tokenize,native_spelling_only
        kept=False;reading=''
        if _is_input_reading(target.preserved_head):
            for token in native_tokenize(surface):
                if not token.has_reading:break
                reading+=token.reading
                if len(reading)>=len(target.preserved_head):
                    kept=(reading==target.preserved_head and native_spelling_only(
                        target.preserved_head,surface[:token.end]));break
        if not kept:return False, 'known_action_changed'
    if target.boundary_kind=='case_leading_intrusion' and surface!=target.text[1:]:
        return False, 'source_verb_changed'
    if source_reading is not None:
        if _omission_changes_unedited_nominal_tail(target.text,surface,source_reading,expected_reading):
            return False,'unedited_written_nominal_tail'
        if source_reading.source=='native_nominal_completion':
            if not any(rd.text==source_reading.text and repair.reading==expected_reading and face==surface
                    for rd,repair,face in _whole_written_nominal_omissions(target.text)):
                return False,'unproven_whole_nominal_completion'
        voiced_tails=[(a,b,rd) for a,b,rd,kind in source_reading.segments
                      if kind=='source_nominal_voicing']
        if voiced_tails:
            from morphology import dictionary_inflections
            if (not expected_reading or not all(b==len(target.text)
                    and surface.endswith(target.text[a:b]) and expected_reading.endswith(rd)
                    for a,b,rd in voiced_tails)
                    or not any(pos.startswith('名詞,') and base==surface and rd==expected_reading
                        and not any(kind in pos for kind in ('固有名詞','接尾','非自立'))
                        for pos,form,base,rd in dictionary_inflections(surface) or ())):
                return False,'unproven_source_nominal_voicing'
    accepted, reason = engine._check_replacement(target.source,
        (target.start, target.end, surface, 'かな入力'), store, tokenize, dictionary, decisions,
        conv_taken=((target.start, target.end),))
    if accepted is None:
        return False, reason
    if tuple(accepted[:2]) != (target.start, target.end):
        return False, 'changed_source_boundary'
    from mark_usage import proved_cluster_normalization
    normalized=proved_cluster_normalization(target.source,tokenize,store,dictionary,decisions)
    if normalized and _apply(target.source,[(target.start,target.end,surface)])==normalized[0]:
        return True,'proved_mark_normalization'
    if not _late_shift_candidate_complete(target,surface,expected_reading):
        return False,'unproven_late_shift_clause'
    # 48-ALU: a newly isolated plain object is a possible interpretation.
    # It may propose a repair only with positive fit to the same unchanged
    # predicate. Missing proof does not invalidate an older whole-word path.
    if target.boundary_kind=='nominal_object' and not _changed_object_slot_allowed(
            target.source,target.start,target.end,surface,require_positive_plain=True):
        return False,'unproven_plain_object_interpretation'

    # A guessed source reading is not independently attested just because
    # the proposed spelling is a real noun. Share the existing positive
    # argument proof for objects, as for guessed predicates. Bind it to
    # the unchanged source accusative/predicate in this same clause.
    # Native/committed readings keep their own stronger evidence; no
    # original noun is marked anomalous by a missing semantic class.
    if source_reading is not None and needs_source_argument_proof(source_reading):
        lo,hi=_source_clause_bounds(target.source,target.start,target.end)
        source_parts=list(tokenize(target.source[lo:hi]))
        # An actual unchanged te/de connection closes the earlier action.
        # A later clause's accusative cannot turn that action into its noun.
        # This source boundary supplies no candidate meaning or permission.
        action_edges=_source_te_edges(target.source[lo:hi])
        # The source tokenizer may swallow its literal link in an unknown
        # word. Reuse the independently owned source scopes only after the
        # same action has passed its own positive meaning and native link.
        if _retained_action_before_owned_object(target,surface,source_reading,expected_reading):
            action_edges=action_edges+(target.end-lo,)
        other_objects=_source_other_case_object_positions(
            target.source[lo:hi],target.start-lo,target.end-lo)
        # Separating another object's scope cannot erase the weak source
        # reading's own positive context requirement. Reuse the existing
        # nominal relation to the unchanged prefix; unknown stays unproved.
        if other_objects and not _retained_nominal_prefix_relation(
                target.source[lo:hi],target.start-lo,target.end-lo,surface,expected_reading):
            other_objects=()
        if any(t[5] and t[0]=='を' and t[1].startswith('助詞:格助詞')
                and target.end-lo<=t[3] and t[3] not in other_objects
                and not any(target.start-lo<edge<=t[3] for edge in action_edges)
                for t in source_parts):
            if not _changed_object_slot_allowed(target.source,target.start,target.end,surface,
                                                require_positive_plain=True):
                return False,'unproven_guessed_object_argument'

    local_start = target.start-target.context_start
    siblings = [(a-target.context_start, b-target.context_start, text)
                for a, b, text in companions
                if target.context_start <= a <= b <= target.context_end
                and not _overlaps(a, b, target.start, target.end)]
    changed = _apply(target.context, siblings+[(local_start, target.end-target.context_start, surface)])
    local_start += sum(len(text)-(b-a) for a, b, text in siblings if b <= local_start)
    local_end = local_start+len(surface)
    # 表記を差し替えても、隣の助詞・活用との接続を必ず同じ文脈で検査する。
    from literal_examples import masked_case_view
    with masked_case_view(target.source,target.context_start,target.context_end):
        anomalous=oddness.structural_anomaly_in_range(changed,local_start,local_end,
                                                     tokenize,store,dictionary)
    if anomalous:
        return False, 'context_still_anomalous'
    # Preserve a dictionary-form source verb with a proved fitting object
    # while repairing its polite attachment. Original nominal/case seams
    # remain evidence even when the full parse swallowed the predicate.
    from semantic_roles import object_before,native_verb_roles,nominal_role_matches
    from reading_segments import native_nominal_phrase_faces,native_object_predicate_frames
    from morphology import dictionary_inflections,native_potential_origins
    original_parts=list(tokenize(target.context))
    source_segments=[(0,original_parts,())]
    if (any(not t[5] for t in original_parts)
            or any(oddness.polite_aux_mismatch(a,b) for a,b in zip(original_parts,original_parts[1:]))):
        for cut,faces in native_object_predicate_frames(target.context.rstrip('。！？.!?')):
            source_segments.append((cut,list(tokenize(target.context[cut:])),faces))
    proved=set()
    for offset,segment,object_faces in source_segments:
        for original,aux in zip(segment,segment[1:]):
            begin,end=offset+original[3],offset+original[4]
            if (not original[5] or original[1]!='動詞:自立' or original[6]!='基本形'
                    or not _is_reading(original[0]) or original[4]!=aux[3]
                    or not oddness.polite_aux_mismatch(original,aux)
                    or not (begin<target.end-target.context_start
                            and target.start-target.context_start<end)):continue
            if not any(p.startswith('動詞,自立,') and f==original[6] and r==original[2]
                    for p,f,b,r in dictionary_inflections(original[0]) or ()):continue
            obj=object_before(target.context,begin,tokenize)
            faces=object_faces or (native_nominal_phrase_faces(obj) if _is_reading(obj) else (obj,))
            roles=native_verb_roles(original[0],original[6],original[2])
            if any(nominal_role_matches(face,roles) for face in faces):proved.add(('reading',original[2]))
    if proved:
        actual=set(_candidate_verb_bases(changed,tokenize))
        for token in tokenize(changed):
            if token[5] and token[1].startswith('動詞'):
                actual.update(('reading',rd) for base,rd in
                    native_potential_origins(token[0],token[6],token[2]))
        if not proved & actual:return False,'original_object_verb_reading'
    if target.boundary_kind=='relative_predicate':
        from relative_key_repair import supports_replacement
        if not supports_replacement(target,surface):return False,'relative_head_meaning'
    from process_familiarity import frames as familiarity_frames,supports_replacement
    # The same source comparison also constrains a lexical duplicate of
    # this range. A different route cannot discard its positive evidence.
    if (target.boundary_kind=='unfamiliar_process' or any(
            (frame['start'],frame['end'])==(target.start,target.end)
            for frame in familiarity_frames(target.source))):
        if not supports_replacement(target,surface,expected_reading):return False,'process_familiarity'
    if target.boundary_kind=='interrogative_extent':
        from particle_frames import interrogative_extent_frames
        frames=[f for f in interrogative_extent_frames(target.source)
                if (f['start'],f['end'])==(target.start,target.end) and f['surface']==surface]
        context_parts=list(tokenize(changed))
        actual=[t for t in context_parts if local_start<=t[3] and t[4]<=local_end]
        from semantic_roles import COGNITIVE_PREDICATES
        from morphology import tokenize as native_tokens
        following=[t for t in native_tokens(changed) if t.start>=local_end]
        if (not frames or len(actual)!=2 or ''.join(t[0] for t in actual)!='かまで'
                or not all(t[1].startswith('助詞:') for t in actual)
                or not following or following[0].base_form not in COGNITIVE_PREDICATES):
            return False,'unproven_question_extent'
    if target.boundary_kind=='meaning_context':
        from context_meaning import supports_replacement
        if not supports_replacement(target,changed,local_start,local_end,surface):
            return False,'unproven_context_meaning'
    if target.boundary_kind=='mark_transposition':
        from mark_usage import transposed_mark_connection
        proved=(expected_reading==surface and transposed_mark_connection(target.context,
            target.start-target.context_start,target.end-target.context_start,surface))
        return (True,'native_mark_transposition') if proved else (False,'unproven_mark_connection')
    if target.boundary_kind=='kana_copula':
        from reading_segments import completed_native_nominal_predicate
        if (expected_reading is not None and surface!=expected_reading
                or not _is_reading(surface) or target.following):
            return False,'copula_spelling_or_tail'
        proved=completed_native_nominal_predicate(changed,nominal_end=local_start)
        return (True,'native_nominal_copula') if proved else (False,'unproven_nominal_copula')
    if target.boundary_kind=='question_particle':
        from particle_frames import closed_question_frames,closed_question_particle
        for frame in closed_question_frames(target.source):
            if frame['start']==target.start and frame['end']==target.end:
                reading=expected_reading or frame['aux_reading']+surface[len(frame['aux']):]
                if closed_question_particle(target.source,frame,reading)==surface:
                    return True,'native_question_particle'
        return False,'unproven_question_particle'
    if target.boundary_kind=='particle_adverbial':
        from particle_frames import adnominal_topic_frames,adverbial_topic_candidate
        for frame in adnominal_topic_frames(target.source):
            if (frame['start']==target.start and frame['end']==target.end
                    and (expected_reading is None or expected_reading==surface)
                    and adverbial_topic_candidate(target.source,frame,surface)==surface):
                return True,'native_adverbial_topic'
        return False,'unproven_adverbial_topic'
    if target.boundary_kind=='particle_intrusion':
        from particle_frames import interrupted_particle_frames, drop_candidate
        for frame in interrupted_particle_frames(target.context,dictionary):
            if (frame['start']==target.start-target.context_start
                    and frame['end']==target.end-target.context_start
                    and (expected_reading is None or expected_reading==frame['head_reading']+frame['case']+frame['topic'])
                    and (drop_candidate(target.context,frame) or {}).get('surface')==surface):
                return True,'native_particle_connection'
        return False,'unproven_particle_connection'
    if target.boundary_kind=='nominalized_subject':
        from particle_frames import nominalized_existential_case_frames,nominalized_subject_particle
        for frame in nominalized_existential_case_frames(target.source):
            if (frame['case_start']==target.start and frame['case_end']==target.end
                    and nominalized_subject_particle(target.source,frame,surface)==surface):
                return True,'native_nominalized_case'
        return False,'unproven_nominalized_case'
    if target.boundary_kind=='nominal_meaning':
        # 48-ACM: changing one nonsensical compound to another is not a
        # completed repair. Reuse ordinary role evidence for the exact
        # original context that established the source anomaly.
        from semantic_roles import conflicting_nominal_compounds,support
        relations=[row for row in conflicting_nominal_compounds(target.context,
                    list(tokenize(target.context)))
                   if row[2]==target.start-target.context_start]
        if not relations or not all(support(left,_surface_score_head(surface))
                                    for left,right,a,b in relations):
            return False,'unproven_nominal_meaning'
    if any(mark[1]=='未説明の小文字語尾' for mark in target.anomalies):
        if not expected_reading or not _completed_shifted_predicate(target,expected_reading):
            return False,'unproven_shifted_predicate_tail'
    if target.boundary_kind in ('kana_request','nominal_topic') and expected_reading is not None:
        from reading_segments import _native_request_tail
        if (target.boundary_kind=='nominal_topic' or surface!=expected_reading
                or not _is_reading(surface) or not _native_request_tail(list(tokenize(surface)))):
            from reading_segments import native_nominal_spelling_faces
            if surface not in native_nominal_spelling_faces(expected_reading):
                return False,'unproven_native_request'
    from reading_segments import native_object_predicate_contexts,native_argument_predicate_contexts
    # This complete-predicate scope already requires positive source-argument
    # meaning. Extend its cases without imposing a new meaning prerequisite
    # on every pre-existing lexical repair in the application.
    source_contexts=(native_argument_predicate_contexts if target.boundary_kind=='kana_predicate'
                     else native_object_predicate_contexts)
    frames=source_contexts(target.context)
    if target.boundary_kind!='kana_predicate' and not frames:
        # An unchanged written continuation does not detach a malformed
        # kana predicate from its original object. Keep discovery separate:
        # this check only validates an already discovered candidate.
        from reading_segments import native_completed_clause_boundaries,native_object_clause_edges
        local=target.start-target.context_start
        scopes=tuple(native_completed_clause_boundaries(target.context))+tuple(native_object_clause_edges(target.context))
        frames=tuple(row for row in native_object_predicate_contexts(target.context,True)
            if row[1]<=local and not any(row[1]<edge<=local for edge in scopes))
    # The next complete object clause bounds this marked action, but its
    # argument cannot license it. Use the same original owner at validation.
    owned=_source_owned_action_contexts(target)
    frames=tuple(dict.fromkeys(tuple(frames)+owned))
    from reading_segments import _native_source_clauses
    own_clause=max((offset for offset,clause in _native_source_clauses(target.context)
        if offset<=target.start-target.context_start<offset+len(clause)),default=0)
    source_frames=[(start,cut,faces) for start,cut,faces in frames
                   if own_clause<=start and cut<=target.start-target.context_start
                   and target.end<=target.context_end]
    # A separately written finite path motion owns no earlier non-path
    # object when another actual verb already intervenes. Its lexical sense
    # and auxiliary chain are still checked at the unchanged source span.
    from semantic_roles import _motion_tail_cannot_take_object
    from morphology import tokenize as native_tokenize
    local=target.start-target.context_start
    if source_frames:
        native=native_tokenize(target.context)
        source_frames=[row for row in source_frames if not (row[2]
            and all(_motion_tail_cannot_take_object(target.context[local:],face) for face in row[2])
            and any(row[1]<=part.start<part.end<=local and part.has_reading
            and part.pos=='動詞' and part.pos_sub=='自立' for part in native))
            and not _source_linked_companion_owns_object(target,row,companions,surface)]
    # A later noun/case owns its predicate. Share the same scope as the
    # common replacement check; absent meaning labels cannot revive an
    # earlier clause's object as the argument of this different action.
    edge=_later_object_scope(target.context,target.start-target.context_start,
                             target.end-target.context_start,surface)
    if edge is not None:source_frames=[row for row in source_frames if row[0]>=edge]
    if target.boundary_kind=='kana_predicate' or source_frames:
        proof_start=max((start for start,cut,faces in source_frames),default=0)
        changed_start=proof_start+sum(len(text)-(b-a) for a,b,text in siblings if b<=proof_start)
        source_predicate_context=target.context[proof_start:]
        changed_predicate_context=changed[changed_start:]
        from reading_segments import native_object_predicate_proof
        from morphology import tokenize as native_tokenize
        if not source_frames:return False,'missing_object_frame'
        _,source_cut,source_faces=max(source_frames,key=lambda f:(f[0],f[1]))
        local_cut=source_cut-proof_start
        if source_predicate_context[:local_cut]!=changed_predicate_context[:local_cut]:
            return False,'changed_object_frame'
        if expected_reading is not None:
            actual=''.join(p.surface if _is_reading(p.surface) else p.reading
                for p in native_tokenize(surface) if _is_reading(p.surface) or p.has_reading)
            if actual!=expected_reading:
                from morphology import native_spelling_only
                if not native_spelling_only(expected_reading,surface):return False,'predicate_reading'
        completed=native_object_predicate_proof(changed_predicate_context,local_cut,source_faces)
        if not completed:
            retained=_unchanged_finite_connective(source_predicate_context,changed_predicate_context)
            bare=changed_predicate_context[:-1] if changed_predicate_context[-1:] in '。！？.!?' else changed_predicate_context
            if retained and bare.endswith(retained):
                completed=native_object_predicate_proof(bare[:-len(retained)],local_cut,source_faces)
        if not completed:
            # Validate this predicate up to an unchanged native link. A
            # second malformed clause must not invalidate the first repair.
            from difflib import SequenceMatcher
            blocks=SequenceMatcher(None,source_predicate_context,
                                   changed_predicate_context,autojunk=False).get_matching_blocks()
            source_edit_end=target.end-target.context_start-proof_start
            source_edges=_source_te_edges(source_predicate_context)
            if _retained_nonfinite_intrusion_link(target,surface,source_reading,
                    expected_reading,tokenize,store,dictionary):
                source_edges=source_edges+(source_edit_end,)
            for edge in source_edges:
                if edge<source_edit_end:continue
                mapped=next((block.b+edge-block.a for block in blocks
                             if block.a<=edge-1 and edge<=block.a+block.size),None)
                if mapped is None or mapped<local_end-changed_start:continue
                if native_object_predicate_proof(changed_predicate_context[:mapped],
                                                 local_cut,source_faces,allow_link=True):
                    completed=True
                    source_predicate_context=source_predicate_context[:edge]
                    changed_predicate_context=changed_predicate_context[:mapped]
                    break
        if not completed:return False,'unproven_object_predicate'
        if expected_reading is not None:
            # The isolated spelling and its full-context parse can select
            # different native readings. The object proof must also hold
            # for the reading reached by the actual proposed key repair.
            begin=local_start-changed_start;finish=begin+len(surface)
            written=[p for p in native_tokenize(changed_predicate_context)
                     if begin<=p.start and p.end<=finish]
            contextual=''.join(p.surface if _is_reading(p.surface) else p.reading
                              for p in written if _is_reading(p.surface) or p.has_reading)
            if contextual!=expected_reading:
                literal=(changed_predicate_context[:begin]+expected_reading
                         +changed_predicate_context[finish:])
                from morphology import dictionary_inflections
                from semantic_roles import native_case_support
                from context_meaning import supports_span
                # A written argument can have several attested native readings.
                # Keep its already proved word/case meaning instead of requiring
                # a fresh kana parse to rediscover that same nominal boundary.
                nominal_reading=(len(written)==1 and written[0].pos=='名詞'
                    and written[0].start==begin and written[0].end==finish
                    and any(pos.startswith('名詞,') and base==written[0].base_form
                            and rd==expected_reading for pos,form,base,rd
                            in dictionary_inflections(surface) or ())
                    and (any((a,b)==(begin,finish) for a,b,case
                            in native_case_support(changed_predicate_context))
                        or supports_span(
                            source_predicate_context,changed_predicate_context,
                            target.start-target.context_start-proof_start,
                            target.end-target.context_start-proof_start,
                            begin,finish,surface)))
                if not nominal_reading and not _object_predicate_candidate_fits(
                        source_predicate_context,literal,local_cut,source_faces):
                    return False,'unproven_candidate_reading_object'
        # A wider auxiliary window observes the same source-proved meaning
        # as its lexical head. It cannot replace that relation with an
        # unrelated action merely because a preferred spelling was blocked.
        from context_meaning import preserves_argument_relation
        if not preserves_argument_relation(source_predicate_context,
                target.start-target.context_start-proof_start,
                target.end-target.context_start-proof_start,
                changed_predicate_context,local_start-changed_start,
                local_end-changed_start):
            return False,'source_argument_meaning'
        if target.boundary_kind=='kana_predicate':return True,'native_object_predicate'
        # A lexical/auxiliary route cannot evade the unchanged object frame.
        # Continue its own reading and POS validation after the common proof.
    if target.boundary_kind=='kana_action_note':
        from reading_segments import completed_native_action_note
        # Keep the source's kana spelling style and prove the whole new
        # clause with the same unedited native reading/meaning contract.
        if surface!=expected_reading or not _is_reading(surface):
            return False,'action_note_spelling'
        return ((True,'native_action_note') if completed_native_action_note(changed)
                else (False,'unproven_action_note'))
    if not oddness.preserves_completed_modifier(target.context,target.start-target.context_start,
                                                changed,local_start,local_end,tokenize):
        return False,'completed_modifier_slot'
    if not oddness.preserves_bound_verb(target.context,target.end-target.context_start,
                                        changed,local_end,tokenize):
        return False,'bound_verb_slot'
    # A source action-head scope promises to repair its grammatical
    # attachment. The existence of each token is insufficient: use the
    # same complete suru/note proof for readable and unknown parses.
    if target.boundary_kind=='sahen_tail' and target.preserved_head:
        from reading_segments import completed_sahen_reading,completed_native_action_note
        from morphology import tokenize as native_tokenize
        reading=expected_reading or ''.join(t.reading for t in native_tokenize(surface) if t.has_reading)
        if not (completed_sahen_reading(reading,allow_nonpolite=True)
                or completed_native_action_note(reading)):
            return False,'unproven_sahen_attachment'
    parts = list(tokenize(surface))
    if not parts or not all(t[5] for t in parts):
        # A whole kana action can remain unknown in the best parse even
        # when its exact nominal head and complete suru tail are attested.
        # Keep that head literally; share the ordinary finite-clause proof
        # after all source/context checks above, without inventing tokens.
        if (target.boundary_kind=='sahen_tail' and target.preserved_head
                and surface==expected_reading and _is_reading(surface)
                and target.start==target.context_start
                and target.end==target.context_end and not target.following):
            from reading_segments import completed_sahen_reading,native_action_noun_reading
            action=completed_sahen_reading(surface,allow_nonpolite=True,
                                           return_action=True,finite_only=True)
            if action and native_action_noun_reading(action,target.preserved_head):
                return True,'native_sahen_tail'
        return False, 'unreadable_candidate'
    lexical_parts = parts
    lexical_tail = parts[-1]
    # 機能語を欠いたまま別の品詞を置かない。格助詞を受ける名詞句と、
    # 接続助詞を受ける連用形を、表記の頻度より先に検査する。
    in_context = list(tokenize(changed))
    inserted = [t for t in in_context if t[3] < local_end and local_start < t[4]]
    if expected_reading is not None:
        if (not inserted or inserted[0][3] != local_start or inserted[-1][4] != local_end
                or (''.join(t[2] for t in inserted) != expected_reading
                    and not _same_context_reading(inserted,expected_reading))):
            # The same fully proved nominal boundary can be swallowed by
            # an unknown best-parse token. Keep literal kana and require
            # the exact head, unchanged case and both original predicates.
            from reading_segments import native_modified_nominal_contexts
            from morphology import native_spelling_only,dictionary_inflections
            literal_nominal=(surface==expected_reading and _is_reading(surface)
                and any(head==local_start and case==local_end
                    for begin,head,case,finish,faces in native_modified_nominal_contexts(changed)))
            # The best parse can split an independently attested compound at
            # its first kanji. A proved kana-to-written projection has the
            # requested reading; keep all following source-context checks.
            # A proved source meaning frame can select a native nominal reading
            # across nominal subtypes (端/はし vs 端/はした). Keep the exact
            # contextual boundary and coarse noun role; other POS do not inherit it.
            meaning_nominal=(target.boundary_kind=='meaning_context' and inserted
                and inserted[0][3]==local_start and inserted[-1][4]==local_end
                and all(t[5] and t[1].startswith('名詞') for t in inserted)
                and any(pos.startswith('名詞,') and rd==expected_reading
                    for pos,form,base,rd in dictionary_inflections(surface) or ()))
            source_projection=(meaning_nominal or any(mark[0] in ('IME逆読み','完成節の接続')
                                   for mark in target.anomalies)
                or any(c in target.text for c in 'ぁぃぅぇぉ'))
            if not (literal_nominal or source_projection
                    and native_spelling_only(expected_reading,surface)):
                return False, 'reading_changed_in_context'
            inserted=[(t[0],t[1],t[2],local_start+t[3],local_start+t[4],t[5],t[6]) for t in parts]
    if inserted and inserted[0][3] == local_start and inserted[-1][4] == local_end:
        parts = inserted
    following = [t for t in in_context if t[3] >= local_end]
    original_following = [t for t in tokenize(target.context)
                          if t[3] >= target.end-target.context_start]
    # A generated word may be grammatical alone yet fail when an original
    # auxiliary changes its internal analysis. Prove the whole joined native
    # predicate, retaining only contiguous functional pieces from the source.
    from morphology import tokenize as native_tokenize
    native_inserted=[t for t in native_tokenize(changed)
                     if local_start<=t.start and t.end<=local_end]
    native_head=next((t for t in native_inserted if t.start==local_start),None)
    # 48-AGI: a nominal object can precede the verb inside the replacement.
    # Prove the actual verb plus unchanged auxiliaries, retaining the nominal
    # prefix as its original context. Suru still belongs to its action noun.
    if native_head and native_head.pos=='名詞':
        for part in native_inserted[1:]:
            if not part.has_reading:break
            if part.pos=='動詞' and part.pos_sub.startswith('自立') and part.base_form!='する':
                native_head=part;break
            if part.pos!='名詞':break
    if native_head and (native_head.pos in ('動詞','形容詞') or
            (native_head.pos=='名詞' and native_head.pos_sub.startswith('サ変接続'))):
        suffix=[]
        cursor=target.end-target.context_start
        for part in original_following:
            # An actually attested noun after a finite adjective owns its
            # whole reading; an old kana split inside it is not an auxiliary.
            if not suffix and native_head.pos=='形容詞' and native_head.infl_form=='基本形':
                from reading_segments import native_adnominal_reading_parts
                nominal_edge=any(changed[noun_end] in 'をにでがへとのはも'
                    and native_adnominal_reading_parts(native_head.reading+changed[local_end:noun_end])
                    for noun_end in range(local_end+len(part[0])+1,min(len(changed),local_end+16)))
                if nominal_edge:break
            if (part[3]!=cursor or not part[5] or not part[1].startswith(
                    ('助動詞','動詞:非自立','動詞:接尾','助詞:接続助詞','助詞:終助詞'))):
                break
            suffix.append(part[0]);cursor=part[4]
        head_offset=native_head.start-local_start
        # 48-AHI: auxiliaries wholly inside the candidate need the same
        # native chain proof as unchanged auxiliaries outside its boundary.
        # A closed verbal chain cannot borrow a kana homophone's parse.
        internal=[t for t in native_inserted if t.start>=native_head.start]
        closed_internal=(native_head.pos in ('動詞','形容詞')
            and any(t.pos=='助動詞' for t in internal)
            and all(t.pos in ('動詞','形容詞','助動詞') for t in internal))
        if (suffix or closed_internal) and not _productive_predicate(
                surface[head_offset:]+''.join(suffix),native_head.surface,
                before=changed[:native_head.start]):
            from reading_segments import (native_incomplete_polite_reading,
                preserves_native_polite_auxiliary)
            open_polite=(not suffix and closed_internal
                and native_incomplete_polite_reading(changed)
                and preserves_native_polite_auxiliary(target.context,changed))
            if not open_polite:
                return False,('unproven_original_auxiliary_chain' if suffix
                              else 'unproven_candidate_auxiliary_chain')
    # 48-ZW / GPT-6 / 2026-09-11: a functional ending left outside the
    # replacement keeps its original grammatical role. The analyzer must
    # not turn an original connective into a nominal case after a new noun.
    # Use the same modern inflection check as composed candidates, including
    # the seam between the candidate and the unchanged suffix.
    for suffix_parts in (original_following,following):
        if not suffix_parts:
            continue
        suffix=suffix_parts[0]
        link=_modern_euphonic_link(suffix[0],suffix[1],suffix[6])
        if link is None:
            continue
        # 48-AAA: nominal/verbal homographs such as 調べ and 片付け
        # take their role from the actual changed clause. The unchanged
        # suffix still retains its original role; native euphony is shared.
        seam_tail=parts[-1]
        if seam_tail[1].startswith('動詞'):
            if _modern_te_allowed(seam_tail[0],seam_tail[2],link) is False:
                return False,'euphonic_following_slot'
        elif suffix[1].startswith('助詞:接続助詞') and suffix[0] in ('て','で'):
            if (not seam_tail[1].startswith(('形容詞','助動詞'))
                    or not seam_tail[6].startswith('連用')):
                return False,'continuative_following_slot'
    # The original suru suffix does not become a free conjunction merely
    # because an inserted predicate makes the analyzer relabel it.
    suru_surface = next((ts[0][0] for ts in (original_following,following)
        if ts and ts[0][0] in ('し','する','すれ','せよ')
        and ts[0][1].startswith('動詞')),None)
    if suru_surface is not None and not lexical_tail[1].startswith('名詞:サ変接続'):
        return False,'suru_slot'
    # 48-ACK: preserve the original auxiliary even if a noun candidate
    # makes the tokenizer relabel it as the count suffix 枚.
    if any(ts and ts[0][0]=='まい' and ts[0][1].startswith('助動詞')
           for ts in (original_following,following)):
        if _native_mai_connection(parts[-1][0],parts[-1][2],parts[-1][1].split(':')[0]) is not True:
            return False,'negative_volition_following_slot'
    if any(ts and ts[0][0]=='つ' and ts[0][1].startswith('助動詞')
           for ts in (original_following,following)):
        if oddness.native_tsu_connection(parts[-1]) is not True:
            return False,'perfective_auxiliary_slot'
    polite_surface = next((ts[0][0] for ts in (original_following,following)
        if ts and ts[0][1].startswith('助動詞')
        and ts[0][0] in ('ます','まし','ませ','ましょ')),None)
    # 差し替え後に助動詞が同形の副詞や自立動詞へ再分類されても、
    # 原文で受け取った丁寧語の接続条件を落とさない。
    if polite_surface is not None:
        tail=parts[-1]
        b=(polite_surface,'助動詞',polite_surface,tail[4],tail[4]+len(polite_surface),True,'')
        if (not tail[1].startswith(('動詞','助動詞'))
                or tail[6]!='連用形' or oddness.polite_aux_mismatch(tail,b)):
            return False,'polite_auxiliary_slot'
    # 「てい」は「いる」の途中。語尾を入れ替えた候補が、入力に無い
    # 続きを要求したまま終わるのを採用しない。名詞に再分類されても
    # 単独の候補で得た補助動詞の役割を失わない。
    if (lexical_tail[0]=='い' and lexical_tail[1].startswith('動詞:非自立')
            and len(lexical_parts)>=2
            and lexical_parts[-2][0] in ('て','で')):
        next_part=following[0] if following else None
        continuation=bool(next_part and (
            next_part[1].startswith('助動詞') or
            (next_part[1].startswith('助詞:接続助詞') and next_part[0] in ('て','で','ながら','つつ'))))
        if not continuation:
            return False,'unfinished_aspect_auxiliary'
    source_parts = list(tokenize(target.text))
    preserved={base for kind,base in _source_preserved_verb_bases(target,tokenize) if kind=='surface'}
    if preserved:
        from morphology import native_potential_origins
        actual={base for kind,base in _candidate_verb_bases(changed,tokenize) if kind=='surface'}
        for token in tokenize(changed):
            if token[5] and token[1].startswith('動詞'):
                actual.update(base for base,rd in native_potential_origins(token[0],token[6],token[2]))
        if not preserved & actual:return False,'original_written_predicate'
    # 48-ZZ / GPT-6 / 2026-09-11: repairing a native predicate's broken
    # auxiliary connection must not invent an interjection at its head.
    # あかげます can be split into filler あ + verb かげ + ます; that
    # analysis does not connect the original predicate to its auxiliary.
    # Existing interjections and non-predicate inputs keep their own roles.
    original_head=next((t for t in tokenize(target.context)
                        if t[3]==target.start-target.context_start),None)
    candidate_head=inserted[0] if inserted and inserted[0][3]==local_start else None
    if (target.boundary_kind=='auxiliary_connection' and original_head and candidate_head
            and original_head[5]
            and original_head[1].startswith(('動詞','形容詞'))
            and candidate_head[1].startswith(('フィラー','感動詞'))):
        from morphology import dictionary_inflections
        head=original_head
        if any(pos.split(',')[0]==head[1].split(':')[0] and rd==head[2]
               and form==head[6]
               for pos,form,base,rd in dictionary_inflections(head[0]) or ()):
            return False,'predicate_replaced_with_interjection'
    # 格助詞を受ける丁寧な述語の修復で、語尾ごと名詞へ置き換えない。
    # 全かなの単語や見出しにはこの条件を課さず、明示的な文の役割を使う。
    before=[t for t in tokenize(target.context) if t[4]<=target.start-target.context_start]
    if (target.boundary_kind=='auxiliary_connection' and before
            and before[-1][4]==target.start-target.context_start
            and before[-1][1].startswith('助詞:格助詞')
            and any(oddness.polite_aux_mismatch(a,b) for a,b in zip(source_parts,source_parts[1:]))
            and not any(t[1].startswith(('動詞','形容詞')) for t in lexical_parts)):
        return False,'predicate_replaced_with_noun'
    # A completed source auxiliary at this clause edge fixes a finite
    # predicate slot. A repair cannot replace it with an unfinished verb
    # stem or a newly dangling connective merely because all tokens exist.
    if (target.boundary_kind=='auxiliary_connection' and not target.following
            and not _preserves_completed_auxiliary_end(source_parts,parts)):
        return False,'incomplete_repaired_predicate'
    original_pairs={(a[0],b[0]) for a,b in zip(source_parts,source_parts[1:])}
    for a,b in zip(lexical_parts,lexical_parts[1:]):
        if (b[0]=='まい' and b[1].startswith('助動詞')
                and _native_mai_connection(a[0],a[2],a[1].split(':')[0]) is False):
            return False,'negative_volition_inflection'
        if ((a[0],b[0]) not in original_pairs and (oddness.aspect_auxiliary_needs_te(a,b)
                or oddness.excess_aux_mismatch(a,b))):
            return False,'aspect_auxiliary_slot'
        link=_modern_euphonic_link(b[0],b[1],b[6] if len(b)>6 else '')
        if (a[1].startswith('動詞') and link is not None
                and (a[0],b[0]) not in original_pairs
                and _modern_te_allowed(a[0],a[2],link) is False):
            return False,'euphonic_auxiliary_slot'
    from pos_grammar import unexplained_shifted_predicate_tails
    if (target.boundary_kind not in ('ime_question','source_sahen_polite_tail','source_projected_polite_tail') and not target.following and source_parts
            and all(t[1].startswith('名詞') for t in source_parts)
            and not unexplained_shifted_predicate_tails(target.text)
            and not parts[-1][1].startswith('名詞')):
        # Actual forward word boundaries can prove that an all-noun IME
        # segmentation hides a finite source reading. Only a changed input
        # reading retaining an original closed masu tail and a complete predicate
        # fitting original arguments may
        # replace it; nominal notes and speculative readings keep this guard.
        evidence=(source_reading.provenance or
                  ((source_reading.source,source_reading.rank,source_reading.segments),)) if source_reading else ()
        attested=any(origin=='ime_context_roundtrip' and segments
                     and all(segment[3]=='ime_context_word' for segment in segments)
                     for origin,rank,segments in evidence)
        from semantic_roles import object_before,case_argument_before
        local=target.start-target.context_start
        obj=object_before(target.context,local,tokenize)
        case=case_argument_before(target.context,local,tokenize)
        proved=bool(target.boundary_kind=='ime_scope' and target.structural
            and any(mark[0]=='IME逆読み' for mark in target.anomalies)
            and attested and expected_reading and expected_reading!=source_reading.text
            and _native_unattached_masu_tail(source_reading.text)
            and _native_unattached_masu_tail(expected_reading)
            and (obj or case) and _ime_predicate_candidate(target,surface,obj,case))
        if not proved:return False, 'nominal_phrase'
    if following:
        first = following[0]
        if (first[1].startswith('助詞:格助詞') and lexical_parts
                and lexical_parts[-1][1].startswith('助詞:終助詞')):
            # The joined parser can turn a final particle into the end of a
            # newly invented noun. An actual whole nominal reading may
            # override that parse; a speculative relative-clause head may not.
            from reading_segments import native_nominal_spelling_faces
            reading=expected_reading or ''.join(t[2] for t in lexical_parts if t[5])
            if not native_nominal_spelling_faces(reading):
                return False,'final_particle_before_nominal_case'
        if (first[0]=='まい' and first[1].startswith('助動詞')
                and _native_mai_connection(parts[-1][0],parts[-1][2],parts[-1][1].split(':')[0]) is False):
            return False,'negative_volition_following_slot'
        # 活用形を短い名詞へ誤分割した文中解析を、成立の証拠にしない。
        # 同じ表記に本物の名詞項がある場合は、その解釈を残す。
        if (_case_boundary(first) and lexical_tail[6].startswith(('未然', '仮定', '命令'))):
            from inflected_lexicon import has_nominal_entry
            if not has_nominal_entry(lexical_tail[0]):
                return False, 'incomplete_inflection_before_nominal_particle'
        if (parts[-1][1].startswith('動詞:接尾') and first[1].startswith('助動詞')
                and first[0] in ('だ', 'で', 'だっ', 'です', 'なら')):
            return False, 'copula_after_verbal_suffix'
        if (parts[-1][6].startswith('仮定') and first[0] not in ('ば', 'ど', 'ども')
                and not _self_contained_conditional(parts[-1])):
            return False, 'conditional_slot'
        if first[1].startswith('助詞:格助詞') and not parts[-1][1].startswith('名詞'):
            # Quoted と also takes a completed predicate, unlike nominal cases.
            # The actual native form supplies completion, not surface frequency.
            from pos_grammar import is_quotative_particle
            quoted_predicate=(is_quotative_particle(first[0],first[1])
                              and (_completed_predicate_token(parts[-1])
                                   or (parts[-1][1].startswith('感動詞') and parts[-1][5])))
            # Native V-te/de + kara orders two actions. The dictionary
            # label of kara as a case particle does not require a noun here.
            temporal_sequence=(first[0]=='から' and len(parts)>=2
                and parts[-1][0] in ('て','で')
                and parts[-1][1].startswith('助詞:接続助詞')
                and _modern_te_allowed(parts[-2][0],parts[-2][2],parts[-1][0]) is True)
            if not quoted_predicate and not temporal_sequence:
                return False, 'nominal_slot'
        if first[0] in ('て', 'で') and first[1].startswith('助詞:接続助詞'):
            if not parts[-1][1].startswith(('動詞', '形容詞')) or not parts[-1][6].startswith('連用'):
                return False, 'continuative_slot'
    return True, 'accepted'


@lru_cache(maxsize=1)
def _seed_context():
    # 同梱の一般的な話題の関係だけを読む。使用回数も履歴も作らない。
    from context_vec import ContextVectorStore
    context = ContextVectorStore()
    context.ensure_seeded()
    return context


def _marked_native_stem_nominal_parts(target):
    """Original anomalous stem run and an independent, unchanged whole noun."""
    from morphology import tokenize,dictionary_inflections
    parts=tokenize(target.text)
    if len(parts)<3:return ()
    first,last=parts[0],parts[-1]
    if (first.start!=0 or last.end!=len(target.text) or len(last.surface)<2
            or not last.has_reading or last.pos!='名詞'
            or last.pos_sub not in ('一般','サ変接続')
            or len(last.reading)<2 or any(a.end!=b.start for a,b in zip(parts,parts[1:]))):return ()
    legacy=[(p.surface,p.pos+':'+p.pos_sub,p.reading,p.start,p.end,p.has_reading,p.infl_form)
            for p in parts[:-1]]
    if (not all(len(p.surface)==1 and p.pos=='名詞' for p in parts[:-1])
            or not _marked_single_kanji_nominal_run(target,legacy,0)):return ()
    if not any(pos.startswith('名詞,') and rd==last.reading
               for pos,form,base,rd in dictionary_inflections(last.surface) or ()):return ()
    return tuple(parts)


def _marked_native_stem_nominal_tail(target, reading):
    """Bind a weak original stem hypothesis to the unchanged attested noun."""
    from okurigana import NEEDS_OKURIGANA
    parts=_marked_native_stem_nominal_parts(target)
    if not parts:return None
    first,last=parts[0],parts[-1];segments=reading.segments
    if (len(segments)!=len(parts) or ''.join(seg[2] for seg in segments)!=reading.text
            or any((seg[0],seg[1])!=(p.start,p.end) for seg,p in zip(segments,parts))
            or segments[0][2] not in NEEDS_OKURIGANA.get(first.surface,())
            or segments[-1][2]!=last.reading):return None
    return last


def _source_predicate_nominal_tail(original):
    """An attested source verb followed by an unchanged ordinary final noun."""
    if not original:return None
    from morphology import tokenize as native_tokenize
    parts=native_tokenize(original)
    if len(parts)<2:return None
    first,last=parts[0],parts[-1]
    if (first.start==0 and first.has_reading and first.pos=='動詞'
            and first.pos_sub=='自立' and last.has_reading
            and last.end==len(original) and last.start>=2
            and last.pos=='名詞' and last.pos_sub in ('一般','サ変接続')
            and len(last.reading)>=2):
        return last
    return None



@lru_cache(maxsize=8192)
def _native_written_reading_matches(surface,reading):
    """Locate a reading boundary using existing word/character evidence.

    Whole-word existence alone cannot assign an arbitrary reading suffix
    to one printed glyph. Each side of the retained source boundary must
    also have an independently attested reading.
    """
    from morphology import dictionary_inflections
    from kanji_onkun import readings_of
    if not surface or not reading:return False
    if any(rd==reading for pos,form,base,rd in dictionary_inflections(surface) or ()):
        return True
    edges={0}
    for char in surface:
        next_edges=set()
        for edge in edges:
            for rd in readings_of(char):
                if rd and reading.startswith(rd,edge):next_edges.add(edge+len(rd))
        edges=next_edges
        if not edges:return False
    return len(reading) in edges


def _whole_written_nominal_omissions(original):
    import kana_layout as K
    return _cached_whole_written_nominal_omissions(original,K.mark_slip_enabled())


@lru_cache(maxsize=2048)
def _cached_whole_written_nominal_omissions(original,allow_mark):
    """Coupled whole-word reading and missing-key hypotheses for a source tail.

    A compound dictionary reading is not a reading of its isolated last
    glyph. Keep this evidence bound to the complete candidate that supplied
    it, with the original kana keys and written tail unchanged.
    """
    import kana_layout as K
    from morphology import source_yoon_spans
    cut=next((i for i,c in enumerate(original) if '一'<=c<='鿿'),len(original))
    prefix,tail=original[:cut],original[cut:]
    if (not prefix or not tail or not _is_input_reading(prefix)
            or not all('一'<=c<='鿿' for c in tail)
            or not (prefix[:1] in 'ゃゅょ' or source_yoon_spans(prefix))):return ()
    literal=_input_kana(prefix)
    keys=tuple(k for c in literal for k in K.keystrokes(c))
    inserted=[(key,) for key in K.KANA_POSITIONS if key not in K._SHIFT_KANA and key not in '゛゜']
    if allow_mark:
        # A missing voiced kana has two physical presses. Both are absent
        # at one source gap; no existing key is substituted or shifted.
        # Keep the two-key meaning check in resolve, even with a real noun.
        inserted.extend(strokes for char in K.MARK_OF
            for strokes in (K.keystrokes(char),)
            if len(strokes)==2 and strokes[0] not in K._SHIFT_KANA and strokes[1] in '゛゜')
    restored={}
    for position in range(len(keys)+1):
        for strokes in inserted:
            fixed=_render(keys[:position]+strokes+keys[position:])
            if not _is_reading(fixed) or fixed[:1] in 'ゃゅょ' or source_yoon_spans(fixed):continue
            restored.setdefault(fixed,[]).append((position,strokes))
    rows=[]
    for face,rd in _native_nominal_words_by_last_glyph().get(tail[-1],()):
        if face==tail or not face.endswith(tail):continue
        for fixed,operations in restored.items():
            if not rd.startswith(fixed) or len(rd)<=len(fixed):continue
            suffix=rd[len(fixed):]
            if not (_native_written_reading_matches(face[:-len(tail)],fixed)
                    and _native_written_reading_matches(tail,suffix)):continue
            reading=Reading(literal+suffix,'native_nominal_completion',0,
                ((0,cut,literal,'literal_kana'),(cut,len(original),suffix,'native_compound_tail')))
            for position,strokes in operations:
                if len(strokes)==1:
                    repair=KeyRepair(rd,'omission',position,'',strokes[0],K.MISSING_KEY_COST)
                else:
                    steps=tuple(KeyRepair(_render(keys[:position]+strokes[:count]+keys[position:])+suffix,
                        'omission',position,'',key,K.MISSING_KEY_COST)
                        for count,key in enumerate(strokes,1))
                    repair=ClauseKeyRepair(rd,'marked_omission',position,'',''.join(strokes),
                        len(strokes)*K.MISSING_KEY_COST,steps)
                rows.append((reading,repair,face))
    return tuple(dict.fromkeys(rows))


@lru_cache(maxsize=1)
def _native_nominal_words_by_last_glyph():
    by_last={}
    for rd,faces in _native_written_nominal_readings().items():
        for face in faces:by_last.setdefault(face[-1],[]).append((face,rd))
    return {last:tuple(words) for last,words in by_last.items()}


@lru_cache(maxsize=2048)
def _source_written_nominal_tails(original,reading):
    """An actual printed noun tail attests its own spelling and reading.

    This supplies an unpruned lexical lookup for a missing earlier key,
    not a new source anomaly, a usage judgment or a semantic role.
    """
    from morphology import tokenize,dictionary_inflections
    parts=tokenize(original);tail=parts[-1] if parts else None
    if not (tail and tail.has_reading and tail.pos=='名詞'
            and not tail.pos_sub.startswith(('固有名詞','非自立'))
            and tail.end==len(original) and tail.start>0
            and _is_input_reading(original[:tail.start])
            and any('一'<=c<='鿿' for c in tail.surface)):return ()
    return tuple((tail.surface,rd) for pos,form,base,rd in dictionary_inflections(tail.surface) or ()
                 if pos.startswith('名詞,') and reading.endswith(rd)
                 and reading[:-len(rd)]==_input_kana(original[:tail.start]))


def _omission_changes_unedited_nominal_tail(original,surface,reading,expected):
    """An omitted prefix key is not evidence to respell a separate noun.

    Use the source's actual native noun and exact remaining key sequence,
    not an imagined full word or a missing semantic classification.
    A repair which changes the tail reading needs its own normal checks.
    """
    if not expected:return False
    import kana_layout as K
    from morphology import source_yoon_spans
    for tail,rd in _source_written_nominal_tails(original,reading.text):
        prefix=original[:-len(tail)]
        if not (prefix[:1] in 'ゃゅょ' or source_yoon_spans(prefix)):continue
        if not expected.endswith(rd) or surface.endswith(tail):continue
        before=tuple(k for c in _input_kana(prefix) for k in K.keystrokes(c))
        after=tuple(k for c in expected[:-len(rd)] for k in K.keystrokes(c))
        added=len(after)-len(before)
        if added not in (1,2):continue
        for gap in range(len(before)+1):
            if after[:gap]!=before[:gap] or after[gap+added:]!=before[gap:]:continue
            keys=after[gap:gap+added]
            ordinary=(added==1 and keys[0] not in K._SHIFT_KANA and keys[0] not in '゛゜')
            marked=(added==2 and K.mark_slip_enabled() and len(_render(keys))==1
                and _render(keys) in K.MARK_OF and K.keystrokes(_render(keys))==keys)
            if ordinary or marked:return True
    return False


def _retained_written_nominal_tail(target,surface,reading,repair):
    """An omitted earlier key can preserve an actual written noun head.

    The complete candidate and the unchanged tail share exact native
    readings. This is original spelling evidence for ranking candidates
    which already passed all checks, not a new meaning or a veto on rivals.
    """
    if repair.operation not in ('omission','marked_omission'):return False
    if reading.source=='native_nominal_completion':
        return (reading,repair,surface) in _whole_written_nominal_omissions(target.text)
    from morphology import dictionary_inflections
    from kana_layout import keystrokes
    forms=dictionary_inflections(surface) or ()
    from reading_segments import native_attested_prefix_noun_readings
    if not (any(pos.startswith('名詞,') and base==surface and rd==repair.reading
                for pos,form,base,rd in forms)
            or repair.reading in native_attested_prefix_noun_readings(surface)):return False
    for tail,rd in _source_written_nominal_tails(target.text,reading.text):
        prefix=reading.text[:-len(rd)]
        edge=sum(len(keystrokes(c)) for c in prefix)
        if (repair.position<=edge and surface.endswith(tail)
                and repair.reading.endswith(rd)):
            return True
    return False


def _source_written_adnominal_surface(reading,original):
    """A repaired kana modifier keeps the source's actual written noun."""
    if not original:return None
    from morphology import tokenize as native_tokenize
    from reading_segments import native_written_adnominal_parts
    parts=native_tokenize(original);noun=parts[-1] if parts else None
    if (noun and noun.has_reading and noun.pos=='名詞'
            and noun.pos_sub in ('一般','サ変接続') and noun.end==len(original)
            and noun.start>=2 and _is_input_reading(original[:noun.start])
            and any('一'<=c<='鿿' for c in noun.surface)
            and len(noun.reading)>=2 and reading.endswith(noun.reading)
            and len(reading)>len(noun.reading)+1):
        candidate=reading[:-len(noun.reading)]+noun.surface
        if native_written_adnominal_parts(candidate):return candidate
    return None


@lru_cache(maxsize=1)
def _native_written_nominal_readings():
    """Unpruned dictionary words for an already attested written noun tail.

    This index supplies spellings, never source anomalies, usage judgments
    or new semantic roles. Callers constrain both the exact reading and
    retained original tail before the common contextual validation.
    """
    from janome_import import iter_janome_entries
    result={}
    for face,reading,pos,sub,sub2,cost in iter_janome_entries(
            min_len=2,max_len=18,pos_prefix='名詞,'):
        if sub not in ('一般','サ変接続') or not face or not '一'<=face[-1]<='鿿':continue
        result.setdefault(reading,set()).add(face)
    return {rd:tuple(sorted(faces)) for rd,faces in result.items()}


def _surfaces(reading, store, dictionary, compose=False, following="", before="", preserved_bases=(), original="", source_nominal_tail=None):
    # 本人語彙には同梱の初期語彙も含まれる。索引から落ちた普通の語を
    # 捨てない一方、使用回数や最終使用時刻は順位に使わない。
    # 48-AIE: an attested ordinary noun may be absent from the broad
    # index (especially a single kanji). Share the exact native noun/usage
    # evidence already used to retain sources; do not add an answer roster.
    from reading_segments import (_native_nominal_reading_faces,native_polite_nominal_parts,
        native_temporal_nominal_faces,native_waiting_nominal_faces,native_inchoative_nominal_faces,
        native_lexical_reading_faces)
    from reading_segments import native_deverbal_compound_parts
    # Derived compounds need a readable source span. An unknown kanji run can
    # acquire a guessed reading and fabricate an unrelated object/action noun.
    compounds=[obj+action for cut,obj,action in native_deverbal_compound_parts(reading)] if compose and _is_reading(original) else []
    # A malformed mixed syllable may restore an exact native loanword even
    # when the broad cost index omits it. The shared word/reading evidence
    # supplies candidates; it never establishes the original anomaly.
    from morphology import source_yoon_spans
    mixed=[face for face in native_lexical_reading_faces(reading)
           if all("ァ"<=c<="ヶ" or c=="ー" for c in face)] if source_yoon_spans(original) else []
    derived=(list(native_temporal_nominal_faces(reading))+list(native_waiting_nominal_faces(reading))
             +list(native_inchoative_nominal_faces(reading))) if compose else []
    # 48-ALW: an unchanged original お/ご can keep its actual native
    # nominal prefix while repairing the following noun. The existing
    # source proof supplies both entries and readings; no new prefix is added.
    polite=[]
    for proof in native_polite_nominal_parts(reading) if compose and original[:1] in ('お','ご') else ():
        prefix=proof[0][0]
        if original.startswith(prefix):polite.append(prefix+proof[-1][0])
    return list(dict.fromkeys(
        _bounded(dictionary.surfaces_for_reading(reading, limit=13, band=True),12,'dictionary_surfaces')
        + list(_native_nominal_reading_faces(reading)) + polite + derived + mixed + compounds
        + [entry['surface'] for entry in store.lookup(reading) if entry.get('surface')]
        + list(dictionary.inflected_surfaces_for_reading(reading))
        + (_composed_surfaces(reading,store,dictionary,following,before,preserved_bases,original,source_nominal_tail) if compose or _source_predicate_nominal_tail(original) else [])))



@lru_cache(maxsize=4096)
def _grammatical_suffix(suffix, state):
    from pos_grammar import explain_kana_run
    return explain_kana_run(suffix,no_words=True,initial_state=state,before_kanji=False)


def _sahen_verb_form(pos, base, surface, form, reading):
    """Share the native conjugation kind for suru and its potential form."""
    from morphology import native_suru_form
    return (pos.split(',')[:2]==['動詞','自立'] and base in ('する','できる','出来る')
            and native_suru_form(surface,form,reading))


@lru_cache(maxsize=4096)
def _native_mai_connection(surface, reading, part_of_speech=None):
    """48-ACK: modern negative volition depends on the native conjugation.

    Godan uses the finite form; ichidan/kuru/suru also use the negative stem.
    A stem may be tagged continuative in isolation, so check every native
    paradigm for this exact written form and reading. None is unknown.
    Source: Mitsumura, Reiwa 7 Kokugo transition supplement, auxiliary table.
    https://assets.mitsumura-tosho.co.jp/3417/4218/8941/07c-kokugo-ikou-k-h.pdf
    """
    from morphology import dictionary_paradigms
    results=[]
    for pos,kind,form,base,rd in dictionary_paradigms(surface) or ():
        if rd!=reading:continue
        # 48-ACL: the source auxiliary ん is not the homographic verb る.
        # Preserve the actual native coarse POS when a caller has it.
        if part_of_speech and pos.split(',')[0]!=part_of_speech:continue
        if pos.startswith('助動詞,') and base in ('ます','た','だ','です'):
            # 48-ACP: the modern negative-volitional auxiliary attaches to
            # finite ます, not past た or a copula. Known past/copula
            # attachment is negative evidence; other auxiliaries stay unknown.
            results.append(base=='ます' and form=='基本形')
        elif pos.startswith('助動詞,') and base=='ある' and kind=='五段・ラ行アル':
            results.append(form=='基本形')
        elif pos.startswith('動詞,'):
            if kind.startswith('五段'):
                results.append(form=='基本形')
            elif kind.startswith(('一段','カ変','サ変')):
                results.append(form in ('基本形','未然形','未然ヌ接続')
                    or (kind.startswith('サ変') and base=='する' and surface=='す'
                        and form=='文語基本形')
                    or (kind.startswith('カ変') and base in ('くる','来る') and rd=='く'
                        and form=='体言接続特殊２'))
    return any(results) if results else None


# NINJAL, syntactic compounds: continuative V + onset/continuation/completion/repetition.
# https://www2.ninjal.ac.jp/vvlexicon/about.html
# GPT-6 Astra / 2026-09-14. Native POS and exact lemma, not a typo answer list.
_PHASE_VERB_BASES=frozenset(('始める','はじめる','続ける','つづける',
                            '終える','おえる','終わる','おわる','直す','なおす',
                            '掛ける','かける'))


def _native_continuative_attachment(previous, following):
    """Same native continuative compound, including a self-standing parse."""
    if not (previous.has_reading and following.has_reading
            and previous.end==following.start and previous.pos==following.pos=='動詞'
            and previous.infl_form=='連用形'
            and following.base_form in (_PHASE_VERB_BASES | _CONTINUATIVE_BOUND_VERBS)):
        return False
    from morphology import dictionary_inflections
    return any(pos.startswith('動詞,') and form==following.infl_form
               and base==following.base_form and rd==following.reading
               for pos,form,base,rd in dictionary_inflections(following.surface) or ())


@lru_cache(maxsize=4096)
def _native_manner_predicate(surface,head,before=''):
    """48-AGP: native finite V + auxiliary you-ni + independently valid suru.

    The same construction serves source evidence and candidate validation.
    Both predicates keep their actual inflections; a noun suffix called you
    and a finite polite ending do not establish this boundary.
    Source: https://www.kyozai.jpf.go.jp/kyozai/material/BTS00105/ja/render.do
    Grammar review/counterexamples: GPT-6 Astra / 2026-09-15.
    """
    if 'ように' not in surface:return False
    from morphology import tokenize,dictionary_inflections
    parts=[t for t in tokenize(before+surface) if t.start>=len(before)]
    if (len(parts)<4 or parts[0].surface!=head or parts[0].pos!='動詞'
            or not all(t.has_reading for t in parts)
            or ''.join(t.surface for t in parts)!=surface
            or any(a.end!=b.start for a,b in zip(parts,parts[1:]))):return False
    for i in range(1,len(parts)-2):
        you,ni,action=parts[i:i+3];previous=parts[i-1]
        from morphology import native_suru_form
        if (you.surface!='よう' or you.pos!='名詞' or you.pos_sub!='非自立:助動詞語幹'
                or ni.surface!='に' or ni.pos!='助詞' or ni.pos_sub!='格助詞:一般'
                or action.pos!='動詞' or action.base_form!='する'
                or not native_suru_form(action.surface,action.infl_form,action.reading,False)
                or previous.pos not in ('動詞','助動詞') or previous.infl_form!='基本形'
                or previous.base_form in ('ます','です')):continue
        if not any(p.startswith('名詞,非自立,助動詞語幹,') and rd==you.reading
                   for p,f,base,rd in dictionary_inflections(you.surface) or ()):continue
        prefix=surface[:you.start-len(before)];suffix=surface[action.start-len(before):]
        native=lambda t:tuple(row for row in dictionary_inflections(t.surface) or ()
            if row[0].startswith('動詞,') and row[1]==t.infl_form and row[3]==t.reading)
        last=parts[-1]
        finite=_completed_predicate_token((last.surface,last.pos+':'+last.pos_sub,
            last.reading,last.start,last.end,last.has_reading,last.infl_form))
        if (finite and _allows_grammatical_tail(native(parts[0]),prefix[len(head):],parts[0].reading,head)
                and _productive_predicate(prefix,head,before=before)
                and _allows_grammatical_tail(native(action),suffix[len(action.surface):],action.reading,action.surface)
                and _productive_predicate(suffix,action.surface)):
            return True
    return False


def _native_te_auxiliary_tail(forms,tail,head_reading,head_surface):
    """48-AKZ: bind an actual te/de auxiliary to the same native head form."""
    if not head_surface or not tail.startswith(('て','で')):return False
    from morphology import tokenize,dictionary_inflections
    parts=tokenize(head_surface+tail)
    if len(parts)<3:return False
    head,link,aux=parts[:3]
    if (head.surface!=head_surface or head.start!=0 or not head.has_reading
            or head.pos!='動詞' or head.end!=link.start or link.end!=aux.start
            or link.pos!='助詞' or link.pos_sub!='接続助詞'
            or link.surface not in ('て','で') or not link.has_reading
            or aux.pos!='動詞' or not aux.has_reading):return False
    if not any(p.startswith('動詞,') and f==head.infl_form and b==head.base_form
               and rd==head.reading and (head_reading is None or rd==head_reading)
               for p,f,b,rd in forms):return False
    if _modern_te_allowed(head.surface,head.reading,link.surface) is not True:return False
    from semantic_roles import native_te_auxiliary_forms
    aux_forms=tuple(row for row in native_te_auxiliary_forms(
        aux.surface,aux.infl_form,aux.reading) if row[2]==aux.base_form)
    if not aux_forms:return False
    return _allows_grammatical_tail(aux_forms,(head_surface+tail)[aux.end:],
                                    aux.reading,aux.surface)


def _sahen_grammatical_tail(tail):
    """The same actual suru paradigm serves simple and compound nominals."""
    from morphology import dictionary_inflections
    from pos_grammar import continuation_state
    for n in range(1,min(3,len(tail))+1):
        for tp,tf,tb,tr in dictionary_inflections(tail[:n]) or ():
            state=continuation_state(tf)
            if not (_sahen_verb_form(tp,tb,tail[:n],tf,tr) and tr==tail[:n]):continue
            if tail[n:].startswith('まい'):
                if _native_mai_connection(tail[:n],tr,tp.split(',')[0]) is not True:continue
                if state is None:state='END'
            if _native_te_auxiliary_tail(((tp,tf,tb,tr),),tail[n:],tr,tail[:n]):return True
            if state and _grammatical_suffix(tail[n:],state):return True
    return False


def _allows_grammatical_tail(forms, tail, head_reading=None, head_surface=None):
    """辞書の活用形と既存の文法による接続。生成と順位で共有する。"""
    from morphology import dictionary_inflections
    from pos_grammar import continuation_state
    from semantic_roles import classified_nominal_action
    from morphology import native_sahen_compound_reading
    if head_surface and head_reading:
        from general_words import sourced_sahen_noun
        if (native_sahen_compound_reading(head_surface)==head_reading
                or sourced_sahen_noun(head_surface,head_reading)):
            return _sahen_grammatical_tail(tail)
    if _native_te_auxiliary_tail(forms,tail,head_reading,head_surface):return True
    # 48-AGW: the same native focused te/de construction supplies tail
    # attachment as well as whole-predicate proof. The original head keeps
    # its actual dictionary POS, form and reading; no glyph is edited.
    if head_surface:
        from morphology import tokenize
        for reduced in _native_focused_te_forms(head_surface+tail,head_surface):
            first=tokenize(reduced)[0]
            matching=tuple(row for row in forms if row[0].split(',')[0]==first.pos
                and (row[1] if row[1]!='*' else '')==first.infl_form and row[3]==first.reading
                and (head_reading is None or row[3]==head_reading))
            if matching and _allows_grammatical_tail(matching,reduced[len(head_surface):],
                    head_reading,head_surface):return True
    if head_surface and _native_manner_predicate(head_surface+tail,head_surface):
        # Do not lend this construction to an unrelated homograph's form.
        from morphology import tokenize
        first=tokenize(head_surface+tail)[0]
        if any(p.startswith('動詞,') and f==first.infl_form and rd==first.reading
               and (head_reading is None or rd==head_reading) for p,f,b,rd in forms):return True
    for pos,form,base,rd in forms:
        if head_reading is not None and rd!=head_reading:
            continue
        if pos.startswith('動詞,'):
            # The generic continuative state cannot override the native
            # modern te/ta connection. Share the same paradigm check used
            # by candidate validation; unclassified/classical forms stay
            # unclassified rather than becoming negative source evidence.
            if head_surface and tail:
                from morphology import tokenize
                first=tokenize(tail)
                if first:
                    token=first[0]
                    link=_modern_euphonic_link(token.surface,
                        token.pos+(':'+token.pos_sub if token.pos_sub else ''),token.infl_form)
                    if link and _modern_te_allowed(head_surface,rd,link) is False:
                        continue
            if tail.startswith('まい') and _native_mai_connection(head_surface,rd,pos.split(',')[0]) is not True:
                continue
            if form=='連用形' and tail:
                from morphology import tokenize
                phase=tokenize(tail)
                if (phase and phase[0].start==0 and phase[0].has_reading
                        and phase[0].pos=='動詞' and phase[0].base_form in _PHASE_VERB_BASES
                        and (phase[0].end==len(tail) or _allows_grammatical_tail(
                            dictionary_inflections(phase[0].surface) or (),tail[phase[0].end:],
                            phase[0].reading,phase[0].surface))):
                    return True
            # A recognized bound phase verb cannot borrow a segmentation
            # into unrelated functional syllables (読む + な + お + します).
            if tail and form!='連用形':
                from morphology import tokenize
                phase=tokenize(tail)
                if (phase and phase[0].start==0 and phase[0].has_reading
                        and phase[0].pos=='動詞' and phase[0].pos_sub.startswith('非自立')
                        and phase[0].base_form in _PHASE_VERB_BASES):continue
            state=continuation_state(form)
            # A native ichidan stem has られ/させ as well as the ordinary
            # continuative/negative endings. The form name alone loses
            # its conjugation class; ask the same native paradigm.
            if form=='未然形' and head_surface:
                from morphology import dictionary_paradigms
                if any(p.startswith('動詞,') and kind.startswith('一段')
                       and f==form and r==rd for p,kind,f,b,r
                       in dictionary_paradigms(head_surface) or ()):
                    state='E'
            if state is None and form=='連用タ接続' and head_surface:
                # 読み末尾「い」だけでは書いて/泳いでを区別できない。
                # 生成後の検算と同じ辞書活用の根拠で、音便の接続を渡す。
                # Exact kana homographs can attest both (書いて / 嗅いで).
                # Consider every native link; dictionary order cannot discard
                # the voiced paradigm. Written kanji keep their own paradigm.
                if any(_modern_te_allowed(head_surface,rd,link) is True
                       and _grammatical_suffix(tail,link_state)
                       for link,link_state in (('て','TSU'),('で','N'))):
                    return True
            if state and _grammatical_suffix(tail,state):
                return True
        elif pos.startswith('形容詞,') and form=='基本形':
            # The full native adjective is already finite; share the
            # existing END grammar for polite and final-particle tails.
            if _grammatical_suffix(tail,'END'):return True
        elif pos.startswith('形容詞,') and form=='連用タ接続':
            # An actual adjective's past stem takes unvoiced ta. Reuse
            # the existing completed-past grammar for what follows it.
            if tail.startswith('た') and _grammatical_suffix(tail[1:],'TA'):return True
        elif pos.startswith('形容詞,') and form=='ガル接続':
            # 48-AGQ: exact native adjective stems use the existing
            # adjective grammar, including the ichidan tail of excess.
            # A whole basic adjective cannot borrow this stem form.
            if _grammatical_suffix(tail,'IST'):return True
        elif (pos.startswith('名詞,サ変接続,') or
              pos.startswith('名詞,一般,') and base==head_surface
              and classified_nominal_action(head_surface,rd)):
            if _sahen_grammatical_tail(tail):return True
    return False


def _modern_euphonic_link(surface, pos, form=''):
    """The modern past conditional has the same onset as た/だ.

    GPT-6 / 2026-09-11 / 48-YW. Use the actual grammatical role; the
    noun たら and the classical auxiliary たり do not prove this link.
    """
    if pos.startswith('助詞:接続助詞') and surface in ('て','で'):
        return surface
    if pos.startswith('助動詞'):
        if surface in ('た','だ'):
            return surface
        if surface in ('たら','だら') and form=='仮定形':
            return surface[0]
    if pos.startswith('助詞:並立助詞') and surface in ('たり','だり'):
        return surface[0]
    # The native contracted auxiliary てる/でる contains the connective
    # even when it is tokenized as a non-independent verb (て + ます).
    # Its own onset still requires the preceding verb's modern euphony.
    if pos.startswith('動詞:非自立'):
        from morphology import dictionary_inflections
        for native_pos,native_form,base,reading in dictionary_inflections(surface) or ():
            if (native_pos.startswith('動詞,非自立,') and native_form==form
                    and base in ('てる','でる') and surface.startswith(base[0])):
                return base[0]
    return None


@lru_cache(maxsize=8192)
def _modern_te_allowed(surface, reading, particle):
    """生成する現代語のて/た接続。辞書の活用型と音便を共有して検算する。

    文語等は未判定。同じ表記の別の読みを接続の証拠に混ぜない。
    原文の文語を異様と決める規則ではない。設計/反証: GPT-6, 2026-09-11。
    """
    from morphology import dictionary_paradigms
    known=False
    unclassified=False
    for pos,kind,form,base,rd in dictionary_paradigms(surface) or ():
        if not pos.startswith('動詞,') or rd!=reading:
            continue
        if kind.startswith('五段'):
            known=True
            voiced=kind.startswith(('五段・ガ行','五段・ナ行','五段・バ行','五段・マ行'))
            if ((particle in ('で','だ'))!=voiced):
                continue
            if form=='連用タ接続' or (kind=='五段・サ行' and form=='連用形'):
                return True
        elif kind.startswith(('一段','カ変','サ変')):
            known=True
            # サ変の「し」は未然と連用が同形で、辞書の一部に片方だけある。
            continuative=(form=='連用形' or (kind.startswith('サ変')
                          and base.endswith('する') and surface==base[:-2]+'し'))
            if continuative and particle in ('て','た'):
                return True
        else:
            # 48-ZT: an unclassified/classical homograph is not a negative
            # answer, but must not hide a later native modern proof either.
            # Inspect every matching form; dictionary iteration order must
            # not choose between True and None for the same inflection.
            unclassified=True
    return None if unclassified else (False if known else None)


# 2026-09-14 / GPT-6 Astra: bound potential/completive verbs attach
# to a verb's continuative form. Independent lexical uses keep their POS.
_CONTINUATIVE_BOUND_VERBS=frozenset(('える','得る','うる','きる','切る'))


@lru_cache(maxsize=4096)
def _native_focused_te_edges(surface,before=""):
    """Attested native verb + te/de + focus edges in unchanged source."""
    if not any(piece in surface for piece in ('ては','ても','では','でも')):return ()
    found=[]
    from morphology import tokenize,dictionary_inflections
    parts=tokenize(before+surface)
    for i,link in enumerate(parts):
        if (i==0 or link.start<len(before) or not link.has_reading or link.pos!='助詞'
                or link.pos_sub!='接続助詞' or link.surface not in ('て','で')):continue
        previous=parts[i-1]
        if (not previous.has_reading or previous.pos!='動詞' or previous.end!=link.start
                or not any(p.startswith('動詞,') and f==previous.infl_form and rd==previous.reading
                           for p,f,b,rd in dictionary_inflections(previous.surface) or ())
                or _modern_te_allowed(previous.surface,previous.reading,link.surface) is not True):continue
        edge=link.end-len(before)
        focus=surface[edge:edge+1]
        if focus not in ('は','も'):continue
        if not any(pos.startswith('助詞,係助詞,') and rd==focus
                   for pos,form,base,rd in dictionary_inflections(focus) or ()):continue
        found.append(edge+1)
    return tuple(dict.fromkeys(found))


def _native_focused_te_forms(surface,head,before=""):
    """The focused auxiliary shares source edges; input is never shortened."""
    from morphology import tokenize
    found=[]
    for focus_end in _native_focused_te_edges(surface,before):
        edge=focus_end-1
        reduced=surface[:edge]+surface[edge+1:]
        following=next((t for t in tokenize(before+reduced) if t.start==len(before)+edge),None)
        if (following and following.has_reading and following.pos=='動詞'
                and following.pos_sub.startswith('非自立')
                and _productive_predicate(reduced,head,before=before)):
            found.append(reduced)
    return tuple(dict.fromkeys(found))


def _native_focused_te_predicate(surface,head,before=""):
    return bool(_native_focused_te_forms(surface,head,before))


@lru_cache(maxsize=4096)
def _native_negative_degree_predicate(surface,head):
    """Native irrealis + negative stem (with written sa) + excess.

    The analyzer can read nasa as another verb's irrealis. Native source
    inflections and the unchanged grammatical suffix prove this chain;
    no altered letters or assumed dictionary word are supplied.
    """
    if not head or not surface.startswith(head):return False
    tail=surface[len(head):]
    negative=next((x for x in ('なさ','な') if tail.startswith((x+'すぎ',x+'過ぎ'))),None)
    if negative is None:return False
    from morphology import dictionary_inflections,tokenize
    forms=tuple(r for r in dictionary_inflections(head) or ()
                if (r[0].startswith('動詞,') and r[1]=='未然形')
                or (r[0].startswith('形容詞,') and r[1]=='連用テ接続'))
    # 48-AGT / GPT-6 Astra: the negative of a na-adjective follows
    # its attested copular continuative, optionally focused with は.
    # The unchanged source form supplies evidence; no noun is invented.
    if not forms:
        copula=next((ending for ending in ('では','じゃ','で') if head.endswith(ending)),'')
        nominal=head[:-len(copula)] if copula else ''
        if (nominal and any(p.startswith('名詞,形容動詞語幹,')
                for p,f,b,r in dictionary_inflections(nominal) or ())
                and any(p.startswith('助動詞,') and b=='だ' and f=='連用形' and r=='で'
                for p,f,b,r in dictionary_inflections('で') or ())
                and (copula=='で' or copula=='じゃ' and any(p.startswith('助詞,副助詞,') and r=='じゃ'
                for p,f,b,r in dictionary_inflections('じゃ') or ())
                or copula=='では' and any(p.startswith('助詞,係助詞,') and r=='は'
                for p,f,b,r in dictionary_inflections('は') or ()))):
            forms=True
    if not forms:return False
    degree=tail[len(negative):];parts=tokenize(degree)
    if (not parts or not all(t.has_reading for t in parts)
            or parts[0].pos!='動詞' or parts[0].base_form not in ('すぎる','過ぎる')):return False
    # Only the actual native excess verb supplies this written reading.
    grammar_tail=negative+'すぎ'+degree[2:] if degree.startswith('過ぎ') else tail
    if not _grammatical_suffix(grammar_tail,'MZ'):return False
    last=parts[-1]
    return _productive_predicate(degree,parts[0].surface) and _completed_predicate_token((last.surface,last.pos+':'+last.pos_sub,last.reading,
        last.start,last.end,last.has_reading,last.infl_form))


@lru_cache(maxsize=8192)
def _productive_predicate(surface, head, before=""):
    """候補を作る語尾は、保護用の緩い説明だけで正当化しない。"""
    from morphology import tokenize
    # The actual case on the left can distinguish a verb such as しめて
    # from its isolated adverb homograph. Preserve that original context.
    parts=[t for t in tokenize(before+surface) if t.start>=len(before)]
    # Share the native finite-auxiliary seam with the final replacement
    # check, including candidates whose first token is a particle.
    import oddness
    legacy=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
             t.start,t.end,t.has_reading,t.infl_form) for t in parts]
    if any(oddness.finite_copula_aux_mismatch(a,b,legacy[i-1] if i else None)
           for i,(a,b) in enumerate(zip(legacy,legacy[1:]))):
        return False
    if _native_focused_te_predicate(surface,head,before=before):return True
    if _native_manner_predicate(surface,head,before=before):return True
    if _native_negative_degree_predicate(surface,head):return True
    if (not parts or not all(t.has_reading for t in parts)
            or parts[0].start!=len(before) or parts[-1].end!=len(before)+len(surface)
            or ''.join(t.surface for t in parts)!=surface or parts[0].surface!=head):
        return False
    from semantic_roles import classified_nominal_action
    action_head=(parts[0].pos=='名詞' and (parts[0].pos_sub.startswith('サ変接続')
        or parts[0].pos_sub=='一般' and classified_nominal_action(head,parts[0].reading)))
    if len(parts)>1 and action_head:
        # Candidate completion needs a real suru chain or a proved nominal
        # copula. Functional POS coverage alone admits unattached auxiliaries.
        from morphology import dictionary_inflections
        from reading_segments import _native_nominal_copula_tail
        tail=surface[len(head):]
        if not (_allows_grammatical_tail(dictionary_inflections(head) or (),
                tail,parts[0].reading,head) or _native_nominal_copula_tail(head,tail)):
            return False
    # 48-ACS: candidate completion shares the native attachment checks
    # used for the source. Functional POS coverage alone accepts しせます.
    # 48-ANI / GPT-6 Astra / 2026-09-20: a source-complete bare verb
    # still needs the same native bound-verb attachment as a repair target.
    # Share it here instead of duplicating only some auxiliary checks.
    if any(oddness.aspect_auxiliary_needs_te(a,b) or oddness.excess_aux_mismatch(a,b) or oddness.mai_aux_mismatch(a,b)
           or _auxiliary_connection_mismatch(a,b,legacy[i-1] if i else None)
           or oddness.polite_aux_mismatch(a,b,legacy[:i])
           or oddness.past_auxiliary_mismatch(a,b,include_finite_verbs=True,include_adjective_forms=True) or oddness.volitional_auxiliary_mismatch(a,b)
           or oddness.negative_aux_mismatch(a,b) or oddness.modern_ba_mismatch(a,b)
           for i,(a,b) in enumerate(zip(legacy,legacy[1:]))):
        return False
    if any(oddness.repeated_polite_aux_mismatch(a,b,c)
           for a,b,c in zip(legacy,legacy[1:],legacy[2:])):
        return False
    # A source auxiliary may be unclassified, but that absence of a negative
    # judgment is not positive proof for a newly generated ...n-mai chain.
    if any(b[0]=='まい' and b[1].startswith('助動詞')
           and _native_mai_connection(a[0],a[2],a[1].split(':')[0]) is not True
           for a,b in zip(legacy,legacy[1:])):
        return False
    from morphology import TE_AUXILIARY_BASES,dictionary_inflections
    for a,b in zip(parts,parts[1:]):
        # A native te/de auxiliary cannot attach directly to an arbitrary
        # verb merely because the parser labels it non-independent. An
        # independently attested compound retains its own lexical grammar.
        from morphology import native_te_auxiliary_attachment_mismatch
        if native_te_auxiliary_attachment_mismatch(a,b):return False
        if (b.pos=='動詞' and b.pos_sub.startswith('非自立')
                and b.base_form in (_CONTINUATIVE_BOUND_VERBS | _PHASE_VERB_BASES)
                and (a.pos!='動詞' or a.infl_form!='連用形')):
            return False
        link=_modern_euphonic_link(b.surface,b.pos+(':'+b.pos_sub if b.pos_sub else ''),b.infl_form)
        if (a.pos=='動詞' and link is not None
                and _modern_te_allowed(a.surface,a.reading,link) is False):
            return False
    # A native -ku adjective modifies the following independent verb;
    # it is not the head of that verb's auxiliary chain. Both retain the
    # shared inflection checks, and callers still validate the source object.
    if (len(parts)>1 and parts[0].pos=='形容詞'
            and parts[1].pos=='動詞' and parts[1].pos_sub=='自立'):
        from reading_segments import native_adjective_adverbial_prefix
        if native_adjective_adverbial_prefix(surface,len(head)):
            if parts[1].base_form=='する':
                from semantic_roles import resultative_adjective_roles
                if not resultative_adjective_roles(parts[0].reading):return False
            return _productive_predicate(surface[len(head):],parts[1].surface,before=before+head)
    for i,t in enumerate(parts[1:],1):
        if t.pos=='助動詞' or (t.pos=='助詞' and t.pos_sub.startswith('接続助詞')):
            continue
        if t.pos=='動詞' and ((t.pos_sub.startswith(('非自立','接尾'))
                and not (parts[i-1].pos=='助詞' and parts[i-1].surface in ('て','で')))
                or _native_continuative_attachment(parts[i-1],t)):
            continue
        if (t.pos=='動詞' and parts[i-1].pos=='助詞'
                and parts[i-1].pos_sub=='接続助詞' and parts[i-1].surface in ('て','で')):
            from morphology import native_potential_auxiliary
            from semantic_roles import native_te_auxiliary_forms
            if (native_potential_auxiliary(t.surface,t.infl_form,t.reading)
                    or native_te_auxiliary_forms(t.surface,t.infl_form,t.reading)):continue
        if (t.pos=='助詞' and '終助詞' in t.pos_sub
                and all(q.pos=='助詞' and '終助詞' in q.pos_sub for q in parts[i:])):
            from morphology import dictionary_inflections
            # 48-ANO / GPT-6 Astra / 2026-09-20: the preceding
            # native chain has already passed the shared attachment checks.
            # A finite bound verb can take the same attested final particles
            # as a simple verb; do not reclassify its whole tail as a stem.
            if ((_completed_predicate_token(legacy[i-1]) or _native_imperative_completion(parts[:i])) and all(
                    any(pos.startswith('助詞,終助詞,') and rd==q.reading
                        for pos,form,base,rd in dictionary_inflections(q.surface) or ())
                    for q in parts[i:])):
                continue
            if _allows_grammatical_tail(dictionary_inflections(head) or (),
                    surface[len(head):],parts[0].reading,head):
                continue
        # Native auxiliary stems (様態/伝聞そう) and the に belonging to
        # negative ずに are functional pieces even when IPAdic calls
        # them a noun/case. Require the whole existing grammatical tail
        # plus their actual native role; arbitrary nouns remain excluded.
        auxiliary_stem=t.pos=='名詞' and t.pos_sub in ('接尾:助動詞語幹','特殊:助動詞語幹')
        negative_ni=(t.surface=='に' and t.pos=='助詞' and t.pos_sub=='格助詞:一般'
                     and parts[i-1].pos=='助動詞' and parts[i-1].surface=='ず' and parts[i-1].base_form=='ぬ'
                     and parts[i-1].infl_form=='連用ニ接続')
        if auxiliary_stem or negative_ni:
            from morphology import dictionary_inflections
            native_role=t.pos+','+t.pos_sub.replace(':',',')+','
            if (any(p.startswith(native_role) and rd==t.reading
                    for p,f,b,rd in dictionary_inflections(t.surface) or ())
                    and _allows_grammatical_tail(dictionary_inflections(head) or (),
                        surface[len(head):],parts[0].reading,head)):
                continue
        if (i==1 and action_head
                and _sahen_verb_form(t.pos+','+t.pos_sub.replace(':',','),t.base_form,t.surface,t.infl_form,t.reading)):
            continue
        return False
    return True


def _composed_surfaces(reading,store,dictionary,following="",before="",preserved_bases=(),original="",source_nominal_tail=None):
    """原文の異様な接続を含む範囲で、語と文法的な語尾を組み合わせる。"""
    from morphology import dictionary_inflections
    out=[]
    for cut in range(1,len(reading)):
        head,tail=reading[:cut],reading[cut:]
        if len(tail)>10:
            continue
        heads=_surfaces(head,store,dictionary)
        # An attested source adjective may have a one-character written
        # stem excluded by the general inflection index's length floor.
        # Keep only the actual native lemma and matching stem reading.
        for kind,base in preserved_bases:
            if kind!='surface' or not base.endswith('い'):continue
            stem=base[:-1]
            if any(p.startswith('形容詞,') and f=='ガル接続' and b==base and rd==head
                   for p,f,b,rd in dictionary_inflections(stem) or ()):heads.append(stem)
        for surface in dict.fromkeys(heads):
            # A completed connective can end this predicate before another
            # clause. Following text supplies an optional native continuation;
            # full original-context validation still follows candidate creation.
            if any(_allows_grammatical_tail(dictionary_inflections(surface) or (),tail+rest,head,surface)
                   and _productive_predicate(surface+tail+rest,surface,before=before)
                   for rest in dict.fromkeys(('',following))):
                out.append(surface+tail)
    # A source's final ordinary noun may belong to the next clause.
    # Restore the preceding native connective without asking the dictionary
    # to contain the entire verb+next-noun phrase as one lexical entry.
    if original:
        from morphology import tokenize as native_tokenize
        last=source_nominal_tail or _source_predicate_nominal_tail(original)
        if (last and last.has_reading and last.end==len(original) and last.start>=2
                and last.pos=='名詞' and last.pos_sub in ('一般','サ変接続')
                and len(last.reading)>=2 and reading.endswith(last.reading)
                and len(reading)>len(last.reading)+1):
            prefix_reading=reading[:-len(last.reading)]
            for prefix in _surfaces(prefix_reading,store,dictionary,compose=True,
                    following=last.surface+following,before=before,preserved_bases=preserved_bases):
                parts=native_tokenize(prefix)
                if not (parts and parts[-1].pos=='助詞' and parts[-1].pos_sub=='接続助詞'
                        and parts[-1].surface in ('て','で')):continue
                if _productive_predicate(prefix,parts[0].surface,before=before):
                    out.append(prefix+last.surface)
    return list(dict.fromkeys(out))


@lru_cache(maxsize=8192)
def _surface_score_head(surface,following="",before=""):
    """文法的な語尾を足した表記を、語本体と同じ一般性で比べる。

    『並べました』全体が単語費用表に無いことを、『並べ』という語が
    珍しいことにしない。語尾は候補全体の読み・接続で別に評価される。
    """
    from morphology import dictionary_inflections
    for cut in range(len(surface)-1,0,-1):
        head,tail=surface[:cut],surface[cut:]
        if not _is_reading(tail) or len(tail)>10:
            continue
        if any(_allows_grammatical_tail(dictionary_inflections(head) or (),tail+rest,head_surface=head)
               and _productive_predicate(surface+rest,head,before=before)
               for rest in dict.fromkeys(('',following))):
            return head
    return surface




def _candidate_usage_tier(surface,head,following='',before='',reading=None):
    """A kana predicate cannot borrow familiarity from an unrelated noun."""
    from kango_tier import candidate_usage_tier,known_reading_usage_tier
    if _is_reading(head):
        from morphology import dictionary_inflections
        forms=tuple(row for row in dictionary_inflections(head) or ()
            if row[0].startswith(('動詞,自立,','形容詞,自立,')) and row[3]==head)
        tail=surface[len(head):] if surface.startswith(head) else ''
        if forms and any((suffix or any(row[1]=='基本形' for row in forms))
                and _allows_grammatical_tail(forms,suffix,head,head)
                and _productive_predicate(head+suffix,head,before=before)
                for suffix in (tail if tail else following,)):
            # Keep an unclassified verb unclassified; うて as a verb is not
            # the independently judged noun 右手 just because it reads alike.
            return candidate_usage_tier(head,reading=head)
        return known_reading_usage_tier(head)
    # Only the entire candidate owns the repaired reading here. A shortened
    # scoring head cannot borrow the whole phrase's reading or a guessed cut.
    return candidate_usage_tier(head,reading=reading if head==surface else None)


def _ime_predicate_nominal_prefix(target):
    """A retained initial object/case belongs to a clause, not one predicate.

    This excludes only the single-predicate IME projection. Other whole
    clause and lexical candidates remain available through their own gates.
    """
    if 'を' not in target.text:return ''
    from morphology import tokenize
    from reading_segments import native_surface_nominal_heads,native_nominal_case_boundary
    parts=tokenize(target.text)
    for i,case in enumerate(parts):
        if case.surface!='を' or case.pos!='助詞' or not case.pos_sub.startswith('格助詞'):continue
        if not i or not all(p.has_reading for p in parts[:i+1]):return ''
        faces=native_surface_nominal_heads(target.text[:case.start])
        if faces and native_nominal_case_boundary(target.text,parts,case.start,'を',faces) is not None:
            return ''.join(p.reading for p in parts[:i+1])
        return ''
    return ''


def _ime_predicate_candidate(target,surface,object_word="",case_argument=None):
    """A newly projected IME phrase needs a complete native predicate chain.

    First-word dictionary membership cannot certify a string such as a verb
    stem followed by unrelated nouns. An unchanged trailing source noun may
    follow a proved te/de clause, while its original attachment still goes
    through validate(). No new compound noun is invented by this projection.
    """
    from morphology import tokenize
    before=target.context[:target.start-target.context_start]
    full=surface+target.following
    original_parts=tokenize(target.context)
    left=next((p for p in original_parts if p.end==len(before)),None)
    if left and left.has_reading and left.pos in ('動詞','形容詞','助動詞'):
        # A newly generated predicate cannot silently attach to an earlier
        # finite verb. Prove their full native chain with the same grammar
        # used to build composed candidates (including continuative forms).
        if not _productive_predicate(left.surface+full,left.surface,before=before[:left.start]):
            return False
    parts=[p for p in tokenize(before+full) if p.start>=len(before)]
    if not parts or parts[0].start!=len(before) or not parts[0].has_reading:return False
    head=parts[0].surface
    if (parts[0].pos not in ('動詞','形容詞') and not
            (parts[0].pos=='名詞' and parts[0].pos_sub.startswith('サ変接続'))):return False
    def arguments_fit():
        from semantic_roles import candidate_evidence,CASE_VERB_ROLES
        # Use the already proved source arguments, never a candidate noun.
        # A native adjective manner modifies the first independent action.
        action=parts[1] if parts[0].pos=='形容詞' and len(parts)>1 else parts[0]
        action_before=before+full[:action.start-len(before)]
        action_after=full[action.end-len(before):]
        if left and left.pos=='助詞' and left.pos_sub.startswith('格助詞'):
            if left.surface in CASE_VERB_ROLES and case_argument is None:return False
        arguments=([(object_word,None)] if object_word else [])
        if case_argument:arguments.append(case_argument)
        return all((candidate_evidence(noun,action.surface,action_after,
                        before=action_before,case=case) or {}).get('shared_roles')
                   for noun,case in arguments)
    if _productive_predicate(full,head,before=before):return arguments_fit()
    for left_part,right in zip(parts,parts[1:]):
        cut=left_part.end-len(before)
        if (not 0<cut<len(full) or left_part.surface not in ('て','で')
                or left_part.pos!='助詞' or not left_part.pos_sub.startswith('接続助詞')):continue
        # A source suffix beyond the replacement can contain another clause
        # or a connector (for example te + kara). Do not parse that unchanged
        # clause as if it belonged to this predicate's auxiliary chain.
        # Within the replacement, only the original nominal tail is retained.
        if cut<len(surface) and right.pos!='名詞':continue
        suffix=full[cut:]
        if not (target.text+target.following).endswith(suffix):continue
        original_cut=target.end-target.context_start+len(target.following)-len(suffix)
        if not any(p.start==original_cut and p.has_reading and p.pos==right.pos
                   for p in original_parts):continue
        if _productive_predicate(full[:cut],head,before=before):return arguments_fit()
    return False


def context_material(target, tokenize):
    """対象に近い内容語から渡す。得点関数の距離減衰と順序を一致させる。"""
    start = target.start-target.context_start
    end = target.end-target.context_start
    parts = [t for t in tokenize(target.context)
             if (t[4] <= start or t[3] >= end)
             and t[1].startswith(('名詞', '動詞', '形容詞')) and len(t[0]) > 1]
    parts.sort(key=lambda t: (start-t[4] if t[4] <= start else t[3]-end, t[3]))
    return tuple(t[0] for t in parts)


def _native_sahen_heads(parts, linked_only=False):
    """Native action nouns own their actual suru form, not a guessed noun."""
    from reading_segments import native_action_noun_reading
    from morphology import dictionary_inflections
    for index,(noun,verb) in enumerate(zip(parts,parts[1:])):
        if (not noun[5] or not verb[5] or not noun[1].startswith('名詞:サ変接続')
                or noun[4]!=verb[3] or not verb[1].startswith('動詞')
                or not native_action_noun_reading(noun[0],noun[2])):continue
        if not any(_sahen_verb_form(pos,base,verb[0],form,reading)
                and form==verb[6] and reading==verb[2]
                for pos,form,base,reading in dictionary_inflections(verb[0]) or ()):continue
        if linked_only:
            link=parts[index+2] if index+2<len(parts) else None
            if (not link or not link[5] or verb[4]!=link[3]
                    or verb[6]!='連用形'
                    or not link[1].startswith('助詞:接続助詞')
                    or link[0] not in ('て','で')
                    or _modern_te_allowed(verb[0],verb[2],link[0]) is not True):continue
        yield noun


def _source_preserved_verb_bases(target, tokenize):
    """Preserve native predicate lemmas at a proved malformed attachment."""
    from morphology import dictionary_inflections
    import oddness
    # Every overlapping candidate observes the same original polite attachment.
    parts=list(tokenize(target.context))
    bases=set()
    # A completed written action + native connective belongs to the source.
    # A separate malformed request after it cannot replace that action.
    from semantic_roles import object_before,nominal_roles,support,native_verb_roles
    from context_meaning import anomalous_frames
    from process_familiarity import frames as familiarity_frames
    # A source-proved meaning comparison owns the same lexical range in
    # every route. A written sahen form does not erase that evidence merely
    # because its suru/te attachment is grammatical. Other source actions
    # still retain their own lemmas; candidate validation keeps the same
    # positive meaning, key and explicit-choice requirements.
    source_meaning_frames=list(anomalous_frames(target.context))
    # Use the same closed object/predicate conflict that created the target.
    # A grammatical suru suffix cannot restore the rejected lexical sense.
    from semantic_roles import conflicting_object_predicates,subject_only_predicate_spans
    source_meaning_frames.extend(dict(start=a,end=b) for noun,predicate,a,b in
        conflicting_object_predicates(target.context,parts)+subject_only_predicate_spans(target.context,parts))
    source_meaning_frames.extend(dict(start=f['start']-target.context_start,
        end=f['end']-target.context_start) for f in familiarity_frames(target.source)
        if target.context_start<=f['start']<f['end']<=target.context_end)
    for noun in _native_sahen_heads(parts,linked_only=True):
        if (not any('一'<=c<='鿿' for c in noun[0])
                or not (noun[3]<target.end-target.context_start
                        and target.start-target.context_start<noun[4])):continue
        if any(f['start']<=noun[3] and noun[4]<=f['end']
               for f in source_meaning_frames):continue
        obj=object_before(target.context,noun[3],tokenize)
        if (obj and nominal_roles(obj) and native_verb_roles(noun[0],'',noun[2])
                and not support(obj,noun[0])):continue
        bases.add(('surface',noun[0]))
    for a,b in zip(parts,parts[1:]):
        if (a[5] and a[1].startswith(('動詞:自立','形容詞:自立')) and a[6]=='基本形'
                and a[3]<target.end-target.context_start
                and target.start-target.context_start<a[4]
                and (oddness.polite_aux_mismatch(a,b) or oddness.excess_aux_mismatch(a,b))):
            for pos,form,base,rd in dictionary_inflections(a[0]) or ():
                if pos.split(',')[0]==a[1].split(':')[0] and form=='基本形' and rd==a[2]:
                    # かな表記の原形は同じ読みの漢字活用でも保持できる。
                    # 漢字で書かれた原形は、その語の表記を保つ根拠にする。
                    bases.add(('reading',rd) if _is_reading(a[0]) else ('surface',base))
    # A native written continuative followed directly by an aspect auxiliary
    # has a proved missing te/de seam. Keep that actual source lemma just
    # as for a malformed polite attachment, across every overlapping scope.
    for a,b in zip(parts,parts[1:]):
        if (a[5] and a[1].startswith('動詞:自立') and a[6]=='連用形'
                and any('一'<=c<='鿿' for c in a[0])
                and a[3]<target.end-target.context_start
                and target.start-target.context_start<a[4]
                and oddness.aspect_auxiliary_needs_te(a,b)):
            bases.update(('surface',base) for pos,form,base,rd in dictionary_inflections(a[0]) or ()
                         if pos.startswith('動詞,自立,') and form==a[6] and rd==a[2])
    # A written native verb with an independently matching source object
    # and grammatical attachment keeps its actual lemma too. Merely having
    # kanji in a malformed token (タフ背, も水戸) supplies no preservation.
    from semantic_roles import object_before,candidate_evidence
    obj=object_before(target.context,target.start-target.context_start,tokenize)
    if obj:
        for a,b in zip(parts,parts[1:]):
            if (not a[5] or not b[5] or not a[1].startswith('動詞:自立')
                    or not any('一'<=c<='鿿' for c in a[0]) or a[4]!=b[3]
                    or not (a[3]<target.end-target.context_start
                            and target.start-target.context_start<a[4])):continue
            if not b[1].startswith(('助詞:接続助詞','助動詞')):continue
            # A noncontinuative stem before perfective tsu is an invalid
            # source attachment, not proof of this written verb's identity.
            if oddness.completed_tsu_aux_mismatch(a,b):continue
            if (b[0] in ('て','で') and b[1].startswith('助詞:接続助詞')
                    and _modern_te_allowed(a[0],a[2],b[0]) is not True):continue
            # An anomalous isolated small kana before this written token
            # belongs to the broken head. The token alone does not prove
            # an intact verb, even when its object would fit that verb.
            head_start=target.context_start+a[3]
            if (head_start and target.source[head_start-1] in 'ぁぃぅぇぉっゃゅょゎ'
                    and any(lo<head_start and a[4]+target.context_start<=hi
                            for _,_,lo,hi in target.anomalies)):continue
            if (head_start>target.start and any(
                    left[4]==right[3] and target.start<=right[3]+target.context_start<head_start
                    and oddness.object_particle_mismatch(left[0],left[1],right[0],right[1])
                    for left,right in zip(parts,parts[1:]))):continue
            previous=next((p for p in parts if p[4]==a[3]),None)
            if (previous and previous[5] and
                    oddness.can_join(previous[0],previous[1],a[0],a[1],previous[2]) is False
                    and any(lo<=target.context_start+previous[3]
                        and target.context_start+a[4]<=hi for _,_,lo,hi in target.anomalies)):
                # The unchanged object cannot certify an isolated verb inside
                # a source-marked, independently invalid lexical attachment.
                continue
            if (previous and previous[5] and previous[1].startswith('動詞')
                    and previous[6].startswith('体言接続')
                    and any(lo<=target.context_start+previous[3]
                        and target.context_start+a[4]<=hi for _,_,lo,hi in target.anomalies)):
                # A marked attributive stem cannot directly attach this
                # second verb. Its convenient isolated object role does not
                # certify the malformed cluster's original lexical head.
                continue
            forms=tuple(row for row in dictionary_inflections(a[0]) or ()
                        if row[0].startswith('動詞,') and row[1]==a[6] and row[3]==a[2])
            from semantic_roles import native_verb_roles,nominal_role_matches
            # The broken auxiliary is what is being repaired. The unchanged
            # written stem and its source object prove the lexical identity
            # independently of that malformed tail.
            roles=native_verb_roles(a[0],a[6],a[2])
            if forms and nominal_role_matches(obj,roles):
                # A broad object category cannot override a more specific
                # source relation that already proves this same verb wrong.
                # Candidate meaning is still checked by the common validator.
                from context_meaning import anomalous_frames
                if any(f['start']<=a[3] and a[4]<=f['end']
                       for f in source_meaning_frames):continue
                bases.update(('surface',base) for pos,form,base,rd in forms)
    return frozenset(bases)


def _candidate_verb_bases(surface, tokenize):
    from morphology import dictionary_inflections
    from inflected_lexicon import dictionary_readings
    parts=list(tokenize(surface))
    bases={('surface',noun[0]) for noun in _native_sahen_heads(parts)}
    for t in parts:
        if not t[5] or not t[1].startswith(('動詞','形容詞')):
            continue
        for pos,form,base,rd in dictionary_inflections(t[0]) or ():
            # 「読め」の命令形と「読める」の連用形は表記が同じ。
            # 候補の解析と違う活用の原形まで保存したことにしない。
            if pos.split(',')[0]!=t[1].split(':')[0] or form!=t[6] or rd!=t[2]:
                continue
            bases.add(('surface',base))
            for base_reading in dictionary_readings(base):
                bases.add(('reading',base_reading))
    return frozenset(bases)


def _terminal_auxiliary_fragment(surface, following, tokenize):
    """語尾がまだ続く形は、同じ打鍵で得た完成語より後で比較する。"""
    parts=list(tokenize(surface))
    if (len(parts)<3 or not parts[-1][1].startswith('動詞:非自立')
            or parts[-1][6]!='連用形' or parts[-2][0] not in ('て','で')):
        return False
    after=list(tokenize(following)) if following else []
    if after and (after[0][1].startswith('助動詞')
                  or after[0][1].startswith('助詞:接続助詞')
                  or after[0][0] in ('、',',')):
        return False
    return True


def _source_predicate_context(target,tokenize):
    """An actual auxiliary or te/de connective marks this predicate slot.

    A lexical subwindow ending immediately before て/で observes the same
    original boundary as a wider auxiliary window. A later clause's polite
    auxiliary does not supply evidence for either window.
    """
    # 48-AHK: a proved original noun/case fixes this predicate even if
    # the malformed tail contains no correctly parsed auxiliary. All routes
    # use that same source frame for script preservation and validation.
    if _source_object_predicate_frame(target.source,target.start,target.end) is not None:
        return True
    if (target.structural and target.anomalies and not target.following
            and target.start==target.context_start and target.end==target.context_end
            and (_orphan_case_finite_predicate(target.text)
                 or target.boundary_kind=='auxiliary_connection'
                    and _native_unattached_masu_tail(target.text))):
        return True
    from morphology import dictionary_inflections
    parts=list(tokenize(target.context))
    head=next((t for t in parts if t[3]==target.start-target.context_start),None)
    # 48-AHM: a particle/auxiliary accidentally found later inside a loan
    # reading cannot certify that the whole window is a kana predicate.
    # Preserve an actual native head, or the proved original object above.
    if (head is None or not head[5] or not head[1].startswith(
            ('動詞','形容詞','助動詞','名詞:サ変接続'))
            or not any(pos.split(',')[0]==head[1].split(':')[0] and rd==head[2]
                       and (form if form!='*' else '')==head[6]
                       for pos,form,base,rd in dictionary_inflections(head[0]) or ())):
        return False
    from pos_grammar import is_functional_noun
    if any(t[3]==target.end-target.context_start
           and is_functional_noun(t,dictionary_alternative=True) for t in parts):
        return True
    return any(t[5] and target.start-target.context_start<=t[3]<=target.end-target.context_start
        and ((t[1]=='助動詞' and any(pos.startswith('助動詞,') and rd==t[2] and form==t[6]
              for pos,form,base,rd in dictionary_inflections(t[0]) or ()))
             or (t[0] in ('て','で') and t[1].startswith('助詞:接続助詞')
                 and any(pos.startswith('助詞,接続助詞,') and rd==t[2]
                         for pos,form,base,rd in dictionary_inflections(t[0]) or ())))
        for t in parts)


_SHIFT_INPUT_KANA = frozenset('ぁぃぅぇぉっゃゅょを')


def _source_shift_free(target, readings):
    """Use the source's own keys, or an exact first-IME source reading."""
    field = _input_kana(target.context)
    if not field:
        return False
    if all(_is_input_reading(c) or c in '。、！？・ ' for c in field):
        return not any(c in _SHIFT_INPUT_KANA for c in field)
    if target.start == target.context_start and target.end == target.context_end:
        exact = [r.text for r in readings if r.source == 'ime_first_roundtrip']
        return bool(exact) and all(not any(c in _SHIFT_INPUT_KANA for c in rd)
                                   for rd in exact)
    return False


def _repair_uses_shift(repair):
    return repair.operation == 'shift' or any(
        step.operation == 'shift' for step in getattr(repair, 'steps', ()))


def _native_candidate_clause_rank(target,reading):
    """Full original kana context, with its native polite tail unchanged."""
    from reading_segments import (native_polite_auxiliary_chains,
        completed_native_reading_clause,completed_native_source_sequence,
        native_incomplete_polite_reading,native_degree_expression)
    original=target.context.rstrip('。！？!?')
    if (not _is_reading(original)
            or not native_polite_auxiliary_chains(target.context,include_open=True)):
        return 0
    changed=target.substitute(reading).rstrip('。！？!?')
    return int(not (completed_native_reading_clause(changed)
        or completed_native_source_sequence(changed)
        or native_incomplete_polite_reading(changed)
        or (any(word in changed for word in ('すぎ','過ぎ','スギ'))
            and native_degree_expression(changed))))


def _native_written_te_action(surface,reading,tokenize):
    """An exact self-contained verb and its real connective, not two verbs."""
    from morphology import dictionary_inflections
    parts=list(tokenize(surface))
    if (len(parts)!=2 or parts[0][3]!=0 or parts[0][4]!=parts[1][3]
            or parts[1][4]!=len(surface) or parts[1][0]!='て'
            or not parts[1][1].startswith('助詞:接続助詞')
            or not parts[0][5] or not parts[0][1].startswith('動詞:自立')
            or parts[0][2]+parts[1][2]!=reading
            or not any('一'<=c<='鿿' for c in parts[0][0])):
        return False
    return any(pos.startswith('動詞,自立,') and form==parts[0][6]
               and rd==parts[0][2]
               for pos,form,base,rd in dictionary_inflections(parts[0][0]) or ())


def _native_phase_repair_evidence(target,surface,tokenize):
    """A marked noun+auxiliary seam retains its native activity host."""
    if not (target.structural and target.anomalies):return False
    from reading_segments import native_temporal_nominal_faces,native_bare_action_faces
    from morphology import native_spelling_only
    if surface in native_temporal_nominal_faces(surface):
        # Overlapping lexical/request scopes share the original action-noun
        # boundary already used to create a sahen-tail scope. A scope label
        # must not erase that unchanged host when comparing a phase noun.
        prefixes=((target.preserved_head,) if target.preserved_head else
            tuple(prefix for cut,prefix,heads in _native_sahen_reading_heads(target.text))
            if _is_input_reading(target.text) else ())
        for prefix in prefixes:
            for head in native_bare_action_faces(prefix):
                if surface.startswith(head) and native_spelling_only(prefix,head):return True
    import oddness
    parts=list(tokenize(target.text))
    if len(parts)<3:return False
    noun,aux=parts[-2:]
    if (noun[3]<=0 or not oddness.volitional_auxiliary_mismatch(noun,aux)
            or not any(start<=target.start+noun[3]
                and target.start+aux[4]<=end
                for _,_,start,end in target.anomalies)):
        return False
    host=target.text[:noun[3]]
    from reading_segments import native_temporal_nominal_faces
    return surface.startswith(host) and surface in native_temporal_nominal_faces(surface)


def _retained_source_kana_nominal_head(target,surface,repair,dictionary):
    """Rank an already valid compound that keeps its attested kana noun head."""
    if (target.boundary_kind!='kana_request' or not target.structural
            or target.start!=target.context_start or target.end!=target.context_end
            or len(target.text)<6 or repair.operation!='adjacent_substitution'
            or not all('ぁ'<=c<='ゖ' or c=='ー' for c in target.text)
            or not surface.startswith(target.text[:2])
            or not any(mark[0]=='品詞文法' for mark in target.anomalies)):
        return False
    from reading_segments import known_reading_prefix
    source=known_reading_prefix(target.text,dictionary,allow_short=True)
    if not source or source[2]!='名詞':return False
    head=source[0]
    if not (surface.startswith(head) and repair.reading.startswith(head)):
        return False
    from morphology import tokenize
    from semantic_roles import nominal_compound_support
    parts=tokenize(surface)
    return bool(len(parts)==2 and parts[0].surface==head
        and parts[0].pos=='名詞' and parts[0].reading==head
        and parts[1].surface==surface[len(head):] and parts[1].pos=='名詞'
        and parts[1].has_reading and parts[1].reading==repair.reading[len(head):]
        and nominal_compound_support(head,parts[1].surface))


def _retained_auxiliary_stem(target,surface):
    """A real continuative before a malformed auxiliary is positive evidence.

    A dictionary terminal such as おく in おくます supplies no such stem.
    This does not generate candidates or replace their grammar/key checks.
    """
    if target.boundary_kind!='auxiliary_connection':return 0
    from morphology import tokenize,dictionary_inflections,native_spelling_only
    original=tokenize(target.text);proposed=tokenize(surface)
    for head in original:
        if not (head.has_reading and head.pos=='動詞' and head.pos_sub=='自立'
                and head.infl_form.startswith('連用') and head.end<len(target.text)):
            continue
        following=next((t for t in original if t.start==head.end),None)
        if following is None or following.pos!='助動詞':continue
        untouched_tail=target.text[following.end:]
        if not untouched_tail:continue
        if not any(p.startswith('動詞,自立,') and f==head.infl_form
                and base==head.base_form and rd==head.reading
                for p,f,base,rd in dictionary_inflections(head.surface) or ()):
            continue
        for candidate in proposed:
            if not (candidate.start==head.start and candidate.has_reading
                    and candidate.pos=='動詞' and candidate.pos_sub=='自立'
                    and candidate.reading==head.reading
                    and target.text[:head.start]==surface[:candidate.start]):
                continue
            if not any(p.startswith('動詞,自立,') and f==head.infl_form
                    and base==candidate.base_form and rd==head.reading
                    for p,f,base,rd in dictionary_inflections(candidate.surface) or ()):
                continue
            # Removing the anomalous auxiliary retains the actual later
            # auxiliary series. A newly added potential changes that series.
            if surface[candidate.end:]!=untouched_tail:continue
            if not native_spelling_only(head.base_form,candidate.base_form):continue
            return 2 if any('一'<=c<='鿿' for c in head.surface) and head.base_form==candidate.base_form else 1
    return 0


def _native_semantic_homophone(target,surface,reading,repair,argument_fit):
    """A fitted homophone retains the native source head and auxiliary tail.

    An established source meaning conflict owns the head; matching its
    exact reading and inflection does not invent a second key error in an
    unchanged auxiliary. Semantic fit is still evaluated before this proof.
    """
    if not (target.semantic_conflict and argument_fit
            and repair.operation=='same_reading'):
        return False
    from morphology import tokenize,dictionary_inflections
    before=target.source[target.context_start:target.start]
    def head(text):
        parts=[t for t in tokenize(before+text+target.following) if t.start>=len(before)]
        if not parts or parts[0].start!=len(before):return None
        t=parts[0]
        if (t.end>len(before)+len(text) or not t.has_reading
                or not any('一'<=c<='鿿' for c in t.surface)
                or not (t.pos=='動詞' and t.pos_sub=='自立'
                    or t.pos=='名詞' and t.pos_sub=='サ変接続')):return None
        forms={(pos,form,rd) for pos,form,base,rd in dictionary_inflections(t.surface) or ()
               if pos.startswith(('動詞,自立,','名詞,サ変接続,'))
               and form==(t.infl_form or '*') and rd==t.reading}
        return (t,forms) if forms else None
    old,new=head(target.text),head(surface)
    if not old or not new or not old[1]&new[1]:return False
    return target.text[old[0].end-len(before):]==surface[new[0].end-len(before):]


def rank_candidates(rows):
    """SR-D total order, with group-wide treatment of optional numeric gaps.

    Intact-source protection and native base preservation precede ranking.
    Do not additionally reward the exact inflected token strings from an
    already anomalous parse: that would favor おくまい over おきます just
    for keeping おく from the malformed おくます.
    """
    rows=list(rows)
    # Native parser cost measures segmentation, not human semantic naturalness.
    # Keep it as a late comparable signal; positive meaning and usage decide
    # ahead of tiny dictionary-cost differences between unrelated words.
    # Only candidates tied on mandatory source/key/meaning evidence can
    # affect optional coverage. A weaker interpretation with no judgment
    # must not erase a stronger group's available usage evidence.
    # A proved source contrast distinguishes specific senses. Broad case
    # compatibility alone cannot tie that relation through double counting.
    core=('native_predicate','source_relation','written_boundary','meaning','written_native','native_inflection','method_spelling','bases','script',
          'proper','terminal','guesses','restricted_usage','common_usage','general_usage','nonadjacent_key')
    cohorts={}
    for row in rows:
        # Once source, meaning and known usage tie, an unexplained distant
        # key cannot outrank a physical neighbor only through parse/n-gram
        # frequency. Multi-step Shift repairs keep their actual operations.
        operations=(row['repair'],)+tuple(row['repair'].get('steps',()))
        row['rank_evidence']['nonadjacent_key']=int(any(
            step.get('operation')=='nonadjacent_substitution' for step in operations))
        # Explicitly judged restricted use remains negative evidence even
        # beside an unjudged word. Unknown usage is still not everyday proof.
        row['rank_evidence']['restricted_usage']=int(row['rank_evidence'].get('usage')==3)
        # Explicit everyday-use evidence is positive even beside an unjudged
        # candidate. Missing usage stays unknown; it does not erase what is
        # already known about the competing, more ordinary interpretation.
        row['rank_evidence']['common_usage']=-int(row['rank_evidence'].get('usage')==1)
        # An explicit general-use judgment is also positive evidence. A
        # rival's missing judgment must not erase it and let dictionary
        # parsing cost stand in for familiarity. Unknown remains unknown,
        # and all source/meaning evidence above still takes precedence.
        row['rank_evidence']['general_usage']=-int(row['rank_evidence'].get('usage')==2)
        # A short raw-kana suffix is not stronger source evidence than a
        # complete native reading of the containing anomalous word. Keep
        # actual committed input first, and speculative readings last.
        key=(-row['rank_evidence'].get('input_reading',0),
             int(row['rank_evidence']['direct']>3))+tuple(
            row['rank_evidence'].get(name,0) if name in ('native_predicate','source_relation','written_boundary','native_inflection')
            else row['rank_evidence'][name] for name in core)
        cohorts.setdefault(key,[]).append(row)
    for prefix,cohort in cohorts.items():
        # A local edit can include only a stem or its whole inflection.
        # Compare reading costs early only when their reconstructed context
        # is the same scope and has the same positively evidenced length.
        scopes={(row.get('context_scope'),row.get('context_reading_length')) for row in cohort}
        comparable=(len(scopes)==1 and all(part is not None for part in next(iter(scopes))))
        # When every alternative inflects the same independently attested
        # local verb, parse cost compares its grammar, not unrelated lexical
        # meanings. Character n-grams alone must not decide that inflection.
        verbs={row.get('local_verb_bases',()) for row in cohort}
        same_verb=len(verbs)==1 and bool(next(iter(verbs)))
        tail=(('context','cost','local_reading','parse_cost','continuation') if comparable and not same_verb
              else ('context','cost','parse_cost','local_reading','continuation'))
        optional=('usage',)+tail
        available={key for key in optional if all(row['rank_evidence'].get(key) is not None
                                                   for row in cohort)}
        for row in cohort:
            e=row['rank_evidence'];op=row['repair']
            # Fixed slots compare across cohorts; omitted values are equal
            # inside their own mandatory prefix, never guessed evidence.
            row['rank']=prefix+(e['usage'] if 'usage' in available else 0,)+tuple(
                e[key] if key in available else 0 for key in tail)+(
                e.get('ime_support',0),e['direct'],e['edits'],e['added'],e['physical'],e.get('shift_avoid',0),e['start'],e['end'],op['reading'],row['surface'],
                op['position'],op['operation'],op['pressed'],op['intended'])
            row['omitted_numeric_evidence']=tuple(key for key in optional if key not in available)
    ordered=sorted(rows,key=lambda row:row['rank'])
    # One final spelling is one choice. Preserve every supporting reading/operation
    # in diagnostics, without granting a vote to repeated generation paths.
    chosen={}
    for row in ordered:
        first=chosen.setdefault((row['rank_evidence']['start'],row['rank_evidence']['end'],row['surface']),dict(row,support=[]))
        support=dict(reading=row['reading'],repair=row['repair'])
        if support not in first['support']:first['support'].append(support)
    return list(chosen.values())


@_with_search_report
def resolve(target, engine, tokenize, store, dictionary, decisions=None, legacy_surface=None, companions=()):
    """同じ文脈で成立した全候補を比較し、最優先の一つと診断を返す。"""
    from ngram_yomi import continuation_cost
    from kango_tier import candidate_usage_tier,known_reading_usage_tier
    from reading_likelihood import edit_cost, adjacent_readings, evidence,context_reading_length
    collect_reading_diagnostic = (engine.TRACE is not None
        or getattr(engine._trace, '_diagnostic_observer', None) is not None)
    from morphology import path_cost,dictionary_inflections
    from semantic_roles import object_before, candidate_evidence as role_evidence, candidate_object_evidence
    from semantic_roles import subject_before, subject_candidate_evidence, modifier_candidate_evidence
    diagnostic = dict(start=target.start, end=target.end, text=target.text,
                      boundary_kind=target.boundary_kind, preserved_head=target.preserved_head,
                      context_start=target.context_start, context_end=target.context_end,
                      anomalies=target.anomalies, structural=target.structural,
                      readings=[], candidates=[], rejected={})
    if (target.boundary_kind!='ime_postevent'
            and engine._chunk_is_intact(
            target.text, tokenize, repair_context=target)):
        diagnostic['status'] = 'intact'
        return None, diagnostic
    readings = reading_evidence(target, tokenize, dictionary)
    if target.require_ime_first_roundtrip:
        readings=tuple(row for row in readings if row.source=='ime_first_roundtrip')
        if not readings:
            diagnostic['status']='source_not_roundtrip'
            return None,diagnostic
    source_shift_free = _source_shift_free(target, readings)
    whole_kana_grammar=(target.start==target.context_start
        and target.end==target.context_end and _is_input_reading(target.text)
        and any(mark[0]=='品詞文法' for mark in target.anomalies))
    reading_grammar_cache={}
    reading_cost_cache={}
    diagnostic['readings']=[asdict(r) for r in readings]
    surrounding_readings = (
        adjacent_readings(target.context, list(tokenize(target.context)),
            target.start-target.context_start, target.end-target.context_start))
    if collect_reading_diagnostic:
        diagnostic['reading_likelihood'] = [dict(row,
            source_start=row['source_start']+target.context_start,
            source_end=row['source_end']+target.context_start)
            for row in evidence(target.context, list(tokenize(target.context)),
                                dictionary_alternatives=False)]
    candidates = []
    ime_evidence = {}
    homophone_positive = {}
    compose = target.structural or target.boundary_kind=='auxiliary_connection'
    from morphology import native_spelling_only
    preserve_kana=_is_input_reading(target.text) and _source_predicate_context(target,tokenize)
    unattached_masu=(preserve_kana and target.boundary_kind=='auxiliary_connection'
        and target.start==target.context_start and target.end==target.context_end
        and not target.following and _native_unattached_masu_tail(target.text))
    grammar_rank = (target.boundary_kind=='auxiliary_connection'
                    or _kana_grammar_boundary(list(tokenize(target.text)),0,len(target.text)))
    complete_verbs = _source_preserved_verb_bases(target,tokenize)
    # 他の列や正解の見本を材料にしない。この対象を除いた同じ文の内容語。
    material = context_material(target, tokenize)
    object_word=(None if target.object_slot else
        object_before(target.context,target.start-target.context_start,tokenize))
    object_frame=(_source_object_predicate_frame(target.source,target.start,target.end)
                  if not object_word or target.boundary_kind=='kana_predicate' and target.structural else None)
    proved_objects=object_frame[-1] if object_frame else ()
    subject_word=subject_before(target.context,target.start-target.context_start,tokenize)
    from semantic_roles import case_argument_before
    case_argument=(None if target.object_slot else
        case_argument_before(target.context,target.start-target.context_start,tokenize))
    ranking_case_argument=(None if target.object_slot else
        case_argument_before(target.context,target.start-target.context_start,tokenize,through_object=True))
    semantic = _seed_context()
    legacy_parts = list(tokenize(legacy_surface)) if legacy_surface else []
    legacy_reading = (''.join(t[2] for t in legacy_parts)
                      if legacy_parts and all(t[5] for t in legacy_parts) else None)
    particle_pair=None;particle_surface=None
    if target.boundary_kind=='particle_intrusion':
        from particle_frames import interrupted_particle_frames, drop_candidate
        local_start=target.start-target.context_start
        for frame in interrupted_particle_frames(target.context,dictionary):
            if frame['start']==local_start and frame['end']==target.end-target.context_start:
                candidate=drop_candidate(target.context,frame)
                if candidate is not None:
                    particle_pair=frame['head_reading']+frame['case']+frame['topic']
                    particle_surface=candidate['surface']
    context_predicate_cache={}
    def context_predicate(surface):
        if surface not in context_predicate_cache:
            context_predicate_cache[surface]=_ime_predicate_candidate(target,surface,object_word,case_argument)
        return context_predicate_cache[surface]
    following_parts=list(tokenize(target.following)) if target.following else []
    nominal_following=bool(following_parts and _case_boundary(following_parts[0]))
    context_surface_cache={}
    nominal_projection_prefix=_ime_predicate_nominal_prefix(target)
    def context_surface(reading):
        if reading not in context_surface_cache:
            if nominal_projection_prefix and reading.startswith(nominal_projection_prefix):
                context_surface_cache[reading]=None
                return None
            # Native predicate projection cannot explain a malformed
            # syllable still present in the proposed reading. Reuse the
            # same source spelling judgment before querying the IME.
            from morphology import source_yoon_spans
            if source_yoon_spans(reading):
                context_surface_cache[reading]=None
                return None
            from ime_language import JapaneseIME
            with JapaneseIME() as ime:
                native=ime.convert_words(reading) if ime.available else None
            context_surface_cache[reading]=native[0] if native else None
        return context_surface_cache[reading]
    key_repair_cache={}
    def cached_key_repairs(reading):
        if reading.text not in key_repair_cache:
            key_repair_cache[reading.text]=tuple(key_repairs(
                reading.text,*surrounding_readings))
        return key_repair_cache[reading.text]
    def ime_project_repairs():
        # Search candidates explain a possible source reading; they are not
        # the first result of normal conversion. Query only after the source
        # has its own anomaly, never as an oddness test or negative evidence.
        if (not target.structural or target.spelling
                or not any(mark[0] in ('IME逆読み','完成節の接続') for mark in target.anomalies)):
            return
        try:
            from ime_candidates import SearchCandidates
            with SearchCandidates() as ime:
                if not ime.available:
                    return
                explained=[]
                for reading in readings:
                    hits=ime.candidates(reading.text)
                    if hits and target.text in hits:
                        explained.append(reading)
                for reading in explained:
                    for repair in cached_key_repairs(reading):
                        if repair.operation=='same_reading':
                            continue
                        hits=ime.candidates(repair.reading)
                        ime_evidence[repair.reading]=hits
                        if hits and any(any('一'<=c<='鿿' or 'ァ'<=c<='ヶ'
                                            for c in hit) for hit in hits):
                            yield reading,repair,('ime_project',hits)
        except (ImportError,OSError,AttributeError):
            return

    def repair_options():
        if target.boundary_kind=='numeric_mark_counter':
            from numeric_mark_repair import frames
            for frame in frames(target.source):
                if ((frame['start'],frame['end'],frame['surface'])
                        == (target.start,target.end,target.candidate_surface)):
                    from numeric_mark_repair import counter_faces
                    for reading in readings:
                        if reading.text==frame['reading']:
                            yield reading,frame['repair'],('ime_clause',(frame['surface'],))
                        elif reading.source in ('current_ime_occurrence','saved_ime_pair'):
                            faces=counter_faces(reading.text)
                            if faces:
                                yield reading,KeyRepair(reading.text,'same_reading',-1,'','',0.0),('ime_clause',faces)
            return
        if target.boundary_kind=='relative_predicate':
            from relative_key_repair import options
            for reading in readings:
                yield from options(target,reading,*surrounding_readings)
            return
        if target.boundary_kind=='unfamiliar_process':
            from process_familiarity import options
            for reading in readings:yield from options(target,reading)
            return
        if target.boundary_kind=='source_projected_polite_tail':
            from ime_spelling import project_first_words
            from semantic_roles import object_before,case_argument_before,candidate_evidence
            projected=project_first_words(target.candidate_reading,
                store,dictionary,decisions,tokenize)
            if not projected:
                return
            surface=projected[0]
            before=target.context[:target.start-target.context_start]
            obj=object_before(target.context,target.start-target.context_start,tokenize)
            arg=case_argument_before(target.context,target.start-target.context_start,tokenize)
            object_fit=candidate_evidence(obj,surface,'',before=before) if obj else None
            case_fit=(candidate_evidence(arg[0],surface,'',before=before,case=arg[1])
                      if arg else None)
            if not (object_fit and object_fit['shared_roles']
                    and case_fit and case_fit['shared_roles']):
                return
            for reading in readings:
                for repair in cached_key_repairs(reading):
                    if (repair.reading==target.candidate_reading
                            and repair.operation in ('adjacent_substitution','adjacent_intrusion')):
                        yield reading,repair,('ime_clause',(surface,))
            return
        if target.boundary_kind=='source_sahen_action_bridge':
            for reading in readings:
                for repair in cached_key_repairs(reading):
                    if (repair.reading==target.candidate_reading
                            and repair.operation=='adjacent_intrusion'
                            and repair.pressed==target.text[-1]):
                        yield reading,repair,('ime_clause',(target.candidate_surface,))
            return
        if target.boundary_kind=='source_adnominal_intrusion':
            for reading in readings:
                for repair in cached_key_repairs(reading):
                    if (repair.reading==target.candidate_reading
                            and repair.operation=='adjacent_intrusion'
                            and repair.pressed=='は'):
                        yield reading,repair,('ime_clause',(target.candidate_surface,))
            return
        if target.boundary_kind=='source_destination_connective':
            for reading in readings:
                for repair in cached_key_repairs(reading):
                    if (repair.reading==target.candidate_reading
                            and repair.operation=='adjacent_substitution'
                            and repair.pressed=='と' and repair.intended=='て'):
                        yield reading,repair,('ime_clause',(target.candidate_surface,))
            return
        if target.boundary_kind=='source_sahen_polite_tail':
            for reading in readings:
                for repair in cached_key_repairs(reading):
                    if (repair.reading==target.candidate_reading
                            and repair.operation=='adjacent_substitution'):
                        yield reading,repair,('ime_clause',(target.candidate_surface,))
            return
        if target.candidate_surface and target.candidate_reading:
            # Exact source reading and an independently proved candidate.
            # The ordinary candidate ranker and joint validation own adoption.
            for reading in readings:
                if reading.text != target.candidate_reading:
                    continue
                for repair in cached_key_repairs(reading):
                    if repair.operation == 'same_reading':
                        yield reading, repair, ('ime_clause', (target.candidate_surface,))
            return
        if target.boundary_kind=='case_leading_intrusion':
            for reading in readings:
                for repair in cached_key_repairs(reading):
                    if (repair.operation=='adjacent_intrusion' and repair.position==0
                            and repair.reading==reading.text[1:]):
                        yield reading,repair,False
            return
        if target.boundary_kind=='nominalized_subject':
            for reading in readings:
                for repair in cached_key_repairs(reading):
                    if repair.operation!='same_reading':yield reading,repair,False
            return
        if target.boundary_kind=='sahen_tail':
            # This interpretation proves an unchanged native action head.
            # Share ordinary physical repairs at the same unchanged action
            # boundary; the special omission rule is not the only tail error.
            for reading in readings:
                repairs=tuple(sahen_omission_repairs(reading.text,target.following))+cached_key_repairs(reading)
                for repair in dict.fromkeys(repairs):
                    if (repair.operation!='same_reading' and repair.position>=len(target.preserved_head)
                            and repair.reading.startswith(target.preserved_head)):
                        yield reading,repair,False
            return
        if target.boundary_kind=='particle_intrusion':
            for reading in readings:
                for repair in cached_key_repairs(reading):
                    if repair.operation=='adjacent_intrusion' and repair.reading==particle_pair:
                        yield reading,repair,False
            return
        # A visible small vowel gives a physically grounded projection, but
        # it does not prove that every other candidate is worse. Rank all
        # validated surfaces together instead of stopping at the first phase.
        prioritize=(target.structural and not target.spelling and not _is_input_reading(target.text)
                    and any(c in target.text for c in 'ぁぃぅぇぉ'))
        if prioritize:
            for reading in readings:
                for repair in cached_key_repairs(reading):
                    if (repair.operation=='shift' and repair.pressed in 'ぁぃぅぇぉ'
                            and repair.pressed in target.text):
                        yield reading,repair,True
        yield from ime_project_repairs()
        inverse=any(mark[0] in ('IME逆読み','完成節の接続') for mark in target.anomalies)
        for reading in readings:
            for repair in cached_key_repairs(reading):
                # This mark proves that the source reading itself is malformed.
                # Changing only its kanji cannot repair that reading.
                if inverse and repair.operation=='same_reading':continue
                if (prioritize and repair.operation=='shift'
                        and repair.pressed in 'ぁぃぅぇぉ'
                        and repair.pressed in target.text):continue
                yield reading,repair,False
        if target.structural and target.boundary_kind in ('lexical','kana_predicate','auxiliary_connection'):
            for reading in readings:
                if not needs_source_argument_proof(reading):
                    for repair in held_shift_key_repairs(reading.text):
                        if repair.pressed in target.text:
                            yield reading,repair,prioritize
                # Only an actually printed late Shift window owns this
                # two-event option; a speculative reverse reading cannot.
                from semantic_roles import case_argument_before
                windows=re.finditer('[きぎしじちぢにひびぴみり][やゆよ][ぁぃぅぇぉ]',target.text)
                # Two physical events cannot also assume an unproved
                # character reading or compound voicing. Reuse merged SR-C
                # evidence, including native and directly attested readings.
                if (not needs_source_argument_proof(reading) and
                        any(not case_argument_before(target.context,
                            target.start-target.context_start+match.start()+1,tokenize)
                            for match in windows)):
                    for repair in adjacent_shift_key_repairs(reading.text):
                        # Reuse the visible small-vowel clause projection.
                        yield reading,repair,prioritize
        if target.structural and target.boundary_kind=='lexical':
            from semantic_roles import conflicting_object_predicates
            from reading_segments import native_case_adnominal_parts
            nominal_omission=any(target.start==target.context_start and
                target.end==target.context_start+head_end and not heads
                for head_end,link_end,heads,right in native_case_adnominal_parts(target.context,True))
            semantic_omission=any(a<target.end-target.context_start and
                target.start-target.context_start<b for obj,verb,a,b in
                conflicting_object_predicates(target.context,list(tokenize(target.context))))
            # A source-proved inflection error can be a missing lexical
            # key just as well as a neighboring key. The unchanged native
            # connector supplies that evidence before any candidate search.
            native_parts=list(tokenize(target.text))
            malformed_link=bool(target.following[:1] in ('て','で') and native_parts
                and native_parts[-1][5] and native_parts[-1][1].startswith('動詞:自立')
                and _modern_te_allowed(native_parts[-1][0],native_parts[-1][2],target.following[0]) is False)
            # The complete native word can attest a tail reading absent
            # from the isolated glyph dictionary. Do not lend this reading
            # to unrelated spelling/key proposals; validation binds both.
            for reading,repair,face in _whole_written_nominal_omissions(target.text):
                diagnostic['readings'].append(asdict(reading))
                yield reading,repair,('native_completion',(face,))
            for reading in readings:
                if not (semantic_omission or nominal_omission or malformed_link
                        or _source_marked_nominal_suru_omission(target,reading.text)
                        or reading.text[:1] in 'ゃゅょ') and reading.source not in ('ime_reverse','ime_first_roundtrip','ime_context_roundtrip','ime_source_candidate'):continue
                for repair in lexical_omission_repairs(reading.text,dictionary,include_shift=semantic_omission,nominal_compound=nominal_omission,
                        native_tails=_source_written_nominal_tails(target.text,reading.text)):
                    yield reading,repair,False
        if not candidates:
            for reading in readings:
                for repair in request_shift_key_repairs(target,reading.text,*surrounding_readings):
                    yield reading,repair,False
        if not target.spelling:
            before=target.source[target.context_start:target.start]
            for reading in readings:
                for repair in sahen_omission_repairs(reading.text,target.following):
                    yield reading,repair,False
                for repair in sahen_open_omission_repairs(reading.text,before,target.following):
                    yield reading,repair,False
        parts=list(tokenize(target.text)) if target.boundary_kind=='ime_scope' else []
        source_object=(parts[0][0] if len(parts)>=2 and parts[0][3]==0 and parts[0][5]
            and parts[0][1].startswith(('名詞:一般','名詞:サ変接続')) and parts[1][0]=='を'
            and parts[1][1].startswith('助詞:格助詞') and parts[0][4]==parts[1][3] else '')
        if (not candidates and source_object and target.boundary_kind=='ime_scope'
                and target.start==target.context_start and target.end==target.context_end):
            # A whole malformed IME reading can contain the unchanged case
            # and a noun whose spelling depends on the repaired action.
            # Prove that native clause first, then reuse ordinary spelling;
            # the original text and physical keys still own final validation.
            from reading_segments import completed_native_reading_clause
            from kana_spelling import project
            from morphology import native_spelling_only,dictionary_inflections,source_yoon_spans
            prefixes=tuple(rd+'を' for pos,form,base,rd in dictionary_inflections(source_object) or ()
                           if base==source_object and pos.startswith(('名詞,一般,','名詞,サ変接続,')))
            for reading in readings:
                unchanged=tuple(prefix for prefix in prefixes if reading.text.startswith(prefix))
                if not unchanged:continue
                for repair in cached_key_repairs(reading):
                    if not any(repair.reading.startswith(prefix) for prefix in unchanged):continue
                    # The same invalid small-kana attachment already
                    # blocks native projection and final spelling proof.
                    # Check it before building every nominal clause parse.
                    if (repair.operation=='same_reading' or source_yoon_spans(repair.reading) or not
                            completed_native_reading_clause(repair.reading,
                                require_nominal=True,require_object_fit=True)):continue
                    projected=project(repair.reading,store,dictionary,decisions)
                    if projected and projected[1] and native_spelling_only(repair.reading,projected[0]):
                        yield reading,repair,('ime_clause',(projected[0],))
        if not candidates:
            for reading in readings:
                for repair in clause_key_repairs(target,reading.text,*surrounding_readings):
                    yield reading,repair,False
        # A lexical parse alone must not stop the independent two-key
        # search. Existing positive context/meaning keeps the bounded
        # fallback closed; an unproved first candidate does not.
        if (target.structural and not target.spelling and not any(
                any(candidate.get('rank_evidence',{}).get(key,0)<0
                    for key in ('meaning','native_predicate','source_relation'))
                for candidate in candidates)):
            for reading in readings:
                if needs_source_argument_proof(reading):continue
                for repair in nonadjacent_key_repairs(reading.text):
                    yield reading,repair,False
                for repair in independent_key_pair_repairs(reading.text,dictionary,*surrounding_readings):
                    yield reading,repair,False
    nominal_heads=()
    if target.boundary_kind=='nominal_field':
        from reading_segments import native_nominal_tail_heads
        nominal_heads=native_nominal_tail_heads(target.text)
    # A repaired clause is not a dictionary word. Preserve the actual
    # leading noun and its printed case before projecting the verb;
    # a swallowed source case is not itself an error declaration.
    clause_projection_head=None
    if (target.structural and not target.spelling
            and target.start==target.context_start and target.end==target.context_end):
        source_parts=list(tokenize(target.text))
        head=source_parts[0] if source_parts else None
        if (head and head[3]==0 and head[5]
                and head[1].startswith(('名詞:一般','名詞:サ変接続'))
                and head[4]<len(target.text)
                and target.text[head[4]] in 'がをにでへと'):
            clause_projection_head=(head[0],head[4]+1,head[2]+target.text[head[4]])
    unresolved_predicates={}
    unresolved_adjacent=set()
    for reading,repair,priority in repair_options():
        if unattached_masu:
            from reading_segments import completed_native_verb_reading
            if not completed_native_verb_reading(repair.reading,require_roles=False,finite_only=True):continue
        if nominal_heads and not any(reading.text.endswith(rd) and repair.reading.endswith(rd)
                and reading.text[:-len(rd)]!=repair.reading[:-len(rd)] for cut,face,rd in nominal_heads):continue
        if (target.boundary_kind=='marked_written_verb'
                and repair.operation!='adjacent_intrusion'):continue
        if target.boundary_kind=='mark_transposition' and not (
                repair.operation=='transposition' and repair.position==0):continue
        question_surface=None
        if target.boundary_kind=='question_particle':
            from particle_frames import closed_question_frames,closed_question_particle
            if repair.operation!='adjacent_intrusion':continue
            for frame in closed_question_frames(target.source):
                if frame['start']==target.start and frame['end']==target.end:
                    question_surface=closed_question_particle(target.source,frame,repair.reading)
            if not question_surface:continue
        if target.boundary_kind=='kana_copula':
            from reading_segments import completed_native_nominal_predicate
            start=target.start-target.context_start
            if not completed_native_nominal_predicate(target.context[:start]+repair.reading,
                    nominal_end=start):continue
        nominal_tail=[]
        if target.boundary_kind in ('kana_request','nominal_topic'):
            from morphology import dictionary_inflections
            from reading_segments import _native_request_tail,native_nominal_spelling_faces
            # An independently proved written noun may be lexical or derived.
            # A grammatical kana phrase alone does not supply a noun spelling.
            request=any(pos.startswith('動詞,') and form=='命令ｉ' and rd==repair.reading
                       for pos,form,base,rd in dictionary_inflections(repair.reading) or ())
            request=target.boundary_kind=='kana_request' and request and _native_request_tail(list(tokenize(repair.reading)))
            if not request:
                nominal_tail=list(native_nominal_spelling_faces(repair.reading))
                if not nominal_tail:continue
        if target.spelling:
            fact=target.spelling[0]
            if repair.reading!=fact.reading or repair.operation!='shift':
                continue
        if dictionary is None:
            priority=False
        if isinstance(priority,tuple) and priority[0] in ('ime_clause','native_completion'):
            surfaces=list(priority[1])
        elif isinstance(priority,tuple) and priority[0]=='ime_project':
            from kana_spelling import project
            projected=project(repair.reading,store,dictionary,decisions)
            surfaces=[projected[0]] if projected and projected[0] in priority[1] else []
        elif priority:
            from kana_spelling import project
            projected=project(repair.reading,store,dictionary,decisions)
            surfaces=[projected[0]] if projected and projected[1] else []
            if (target.start==target.context_start and target.end==target.context_end
                    and any(mark[0]=='IME逆読み' for mark in target.anomalies)):
                try:
                    from ime_language import JapaneseIME
                    with JapaneseIME() as ime:
                        first=ime.convert(repair.reading) if ime.available else None
                        if first:
                            if first not in surfaces:surfaces.insert(0,first)
                            from ime_homophone import positive_predicate_alternatives
                            for alternate,source_object,proof in positive_predicate_alternatives(
                                    target.text,first,repair.reading,tokenize,ime):
                                if alternate not in surfaces:surfaces.append(alternate)
                                homophone_positive[alternate]=(source_object,proof)
                except (ImportError,OSError,AttributeError):pass
        else:
            surfaces = (nominal_tail if nominal_tail else
                         [question_surface] if target.boundary_kind=='question_particle' else
                         [particle_surface] if target.boundary_kind=='particle_intrusion' else
                         [target.spelling[0].normal] if target.spelling else
                         [repair.reading] if unattached_masu or target.boundary_kind in ('kana_action_note','kana_predicate','kana_request','kana_copula','particle_adverbial','mark_transposition','nominalized_subject')
                         else _surfaces(repair.reading,store,dictionary,
                             # A native action-tail omission already proves
                             # this composition, even when the source anomaly
                             # came from a mixed-script lexical boundary.
                             compose=compose or (repair.operation=='omission' and
                                 repair in sahen_omission_repairs(reading.text,target.following)),
                             following=target.following,before=target.context[:target.start-target.context_start],
                             preserved_bases=complete_verbs,original=target.text,
                             source_nominal_tail=_marked_native_stem_nominal_tail(target,reading)))
            # A repaired kana predicate may retain an earlier completed
            # object/verb clause. Its ordinary spelling needs the same
            # positive argument proof at the common final gate.
            if (target.boundary_kind=='kana_predicate' and target.structural
                    and repair.operation!='same_reading'):
                # A repaired predicate needs the same actual inflected
                # spellings as other lexical targets. Kana projection alone
                # may omit a whole attested verb; every spelling still passes
                # the original-context, key and meaning checks below.
                surfaces.extend(_surfaces(repair.reading,store,dictionary,
                    compose=True,following=target.following,
                    before=target.context[:target.start-target.context_start],
                    preserved_bases=complete_verbs,original=target.text))
                from reading_segments import native_completed_clause_boundaries
                from kana_spelling import project
                from morphology import native_spelling_only
                if (_source_object_predicate_frame(target.source,target.start,target.end)
                        or any(target.start-target.context_start<edge<target.end-target.context_start
                               for edge in native_completed_clause_boundaries(target.context))):
                    projected=project(repair.reading,store,dictionary,decisions)
                    if (projected and projected[1]
                            and native_spelling_only(repair.reading,projected[0])):
                        surfaces.append(projected[0])
            # Fall back to all same-reading spellings only when the proved
            # Shift-first path found no acceptable candidate.
            if (target.structural and repair.operation=='shift'
                    and repair.pressed in 'ぁぃぅぇぉ' and repair.pressed in target.text
                    and not _is_input_reading(target.text)):
                from kana_spelling import project
                projected=project(repair.reading,store,dictionary,decisions)
                if projected and projected[1]:surfaces.append(projected[0])
        if not surfaces and clause_projection_head and repair.operation!='same_reading':
            head,cut,prefix=clause_projection_head
            if reading.text.startswith(prefix) and repair.reading.startswith(prefix):
                from reading_segments import native_object_predicate_proof
                if native_object_predicate_proof(repair.reading,len(prefix),(head,)):
                    from kana_spelling import project
                    from morphology import native_spelling_only
                    projected=project(target.text[:cut]+repair.reading[len(prefix):],
                        store,dictionary,decisions)
                    if (projected and projected[1]
                            and native_spelling_only(repair.reading,projected[0])):
                        surfaces.append(projected[0])
        if repair.operation=='omission' and _is_reading(repair.reading):
            from reading_segments import native_incomplete_polite_reading
            if native_incomplete_polite_reading(target.substitute(repair.reading)):
                surfaces.append(repair.reading)
        # Exact original-context IME words attest the source reading. The
        # repaired first spelling is just another candidate: it must retain
        # that reading and pass the same original-context/meaning checks.
        if (needs_ime_context_projection(reading)
                and repair.operation!='same_reading'):
            projected=context_surface(repair.reading)
            if projected and context_predicate(projected):
                surfaces.append(projected)
        if (not target.spelling and target.boundary_kind not in ('kana_action_note','kana_predicate') and repair.reading.endswith('し')
                and target.following.startswith(('て','た','ま','な'))):
            # 「名詞＋し」が別の名詞の一部へ誤分割されても、入力された
            # しを残してサ変活用の境界を戻す。追加打鍵は仮定しない。
            surfaces.extend(sf+'し' for sf in _surfaces(repair.reading[:-1], store, dictionary)
                if any(t[1].startswith('名詞:サ変接続') for t in list(tokenize(sf))[-1:]))
        # 48-AJC: an attested kana action prefix keeps its spelling while
        # the ordinary key search repairs its tail. The common final check
        # still proves the whole attachment, including narrower contenders.
        if target.preserved_head and _is_reading(target.text) and _is_reading(target.preserved_head):
            surfaces.append(repair.reading)
            # The exact source head can be a native prefixed action absent
            # from the single-word table. Reuse its morphology for candidate
            # spelling as well as for the finite-reading proof.
            if target.boundary_kind=='sahen_tail' and repair.reading.startswith(target.preserved_head):
                from reading_segments import native_bare_action_faces
                surfaces.extend(face+repair.reading[len(target.preserved_head):]
                    for face in native_bare_action_faces(target.preserved_head))
        # 既存経路の先頭候補も、同じ読みに同じ一手で届くなら同列で比較。
        # 新設の経路であること自体を、優先する理由にしない。
        if not target.spelling and legacy_reading == repair.reading and target.boundary_kind not in ('kana_action_note','particle_intrusion','kana_request'):
            surfaces.append(legacy_surface)
        # This original noun boundary also belongs to IME-priority routes.
        # Candidate ranking and the common source/key checks remain unchanged.
        if repair.operation=='omission':
            # The reading-side lookup must reach the same exact native
            # spelling here; a frequency-band omission is not absence from
            # the dictionary. All candidates still pass normal validation.
            tails=_source_written_nominal_tails(target.text,reading.text)
            surfaces.extend(face for face in _native_written_nominal_readings().get(repair.reading,())
                if any(repair.reading.endswith(rd) and face.endswith(tail) for tail,rd in tails))
            # An independently attested whole word may be absent from the
            # single-row native dictionary. Share its existing prefix/head
            # pronunciation proof, still tied to the unchanged source noun.
            from reading_segments import native_attested_prefix_noun_faces
            if tails:
                surfaces.extend(face for face in native_attested_prefix_noun_faces(repair.reading)
                    if any(repair.reading.endswith(rd) and face.endswith(tail) for tail,rd in tails))
        if repair.reading!=reading.text:
            written_nominal=_source_written_adnominal_surface(repair.reading,target.text)
            if written_nominal:surfaces.append(written_nominal)
        if nominal_heads:
            from reading_segments import native_nominal_compound_spelling,native_nominal_tail_spellings
            surfaces.extend(native_nominal_tail_spellings(repair.reading,nominal_heads))
            surfaces=[surface for surface in surfaces
                if any(surface.endswith(face) for cut,face,rd in nominal_heads)
                and native_nominal_compound_spelling(repair.reading,surface)]
        voiced_tails=[target.text[a:b] for a,b,rd,kind in reading.segments
            if kind=='source_nominal_voicing' and b==len(target.text)
            and repair.reading.endswith(rd)]
        if voiced_tails:
            # A whole native compound can be missing from the old frequency
            # band although its original written tail is attested. Do not
            # turn a lost spelling index entry into a missing candidate.
            surfaces.extend(face for face in _native_written_nominal_readings().get(repair.reading,())
                            if all(face.endswith(tail) for tail in voiced_tails))
        for surface in dict.fromkeys(surfaces):
            if (needs_source_argument_proof(reading)
                    and (object_word or case_argument) and not nominal_following
                    and not context_predicate(surface)):
                reason='unproven_source_argument'
                diagnostic['rejected'][reason]=diagnostic['rejected'].get(reason,0)+1
                continue
            valid, reason = validate(target, surface, engine, tokenize, store, dictionary, decisions, repair.reading,companions,source_reading=reading)
            if not valid:
                diagnostic['rejected'][reason] = diagnostic['rejected'].get(reason, 0)+1
                # Unknown lexical meaning is not negative evidence against
                # another attested reading of the same damaged predicate.
                if (reason=='unproven_original_object_predicate'
                        and not getattr(repair,'steps',())
                        and target.boundary_kind=='kana_predicate' and object_frame
                        and target.start==object_frame[0]+object_frame[3]):
                    from reading_segments import completed_native_verb_reading
                    from semantic_roles import candidate_evidence
                    if completed_native_verb_reading(repair.reading,require_roles=False,finite_only=True):
                        proofs=[candidate_evidence(face,surface,target.following,
                            target.context[:target.start-target.context_start]) for face in proved_objects]
                        if not any(p and p.get('object_roles') and p.get('predicate_roles') for p in proofs):
                            unresolved_predicates[repair.reading]=min(repair.cost,
                                unresolved_predicates.get(repair.reading,float('inf')))
                            if repair.operation=='adjacent_substitution':unresolved_adjacent.add(repair.reading)
                continue
            if whole_kana_grammar:
                if repair.reading not in reading_grammar_cache:
                    from pos_grammar import odd_kana_spans
                    reading_grammar_cache[repair.reading]=bool(odd_kana_spans(
                        repair.reading+'\t',dictionary,store))
                if reading_grammar_cache[repair.reading]:
                    reason='repaired_reading_still_anomalous'
                    diagnostic['rejected'][reason]=diagnostic['rejected'].get(reason,0)+1
                    continue
            if (repair.operation=='shift' and any(c in 'ぁぃぅぇぉ' for c in target.text)
                    and any(mark[0]=='IME逆読み' for mark in target.anomalies)):
                from ime_inverse_gate import first_roundtrip
                roundtrip=first_roundtrip(target.substitute(surface))
                if roundtrip is False and surface not in homophone_positive:
                    diagnostic['rejected']['ime_first_mismatch']=diagnostic['rejected'].get('ime_first_mismatch',0)+1
                    continue
            # 実観測、意味・文脈・一般性を比較し、推定読みと物理操作を後に置く。
            # 漢語の一般性は既存表を、目的語と動作の意味的な役割は版付きの
            # 一般語分類を使う。未知の意味を不適合と決めない。
            score_head = (_surface_score_head(surface,target.following,target.context[:target.start-target.context_start])
                if compose else surface)
            if target.boundary_kind=='kana_action_note':
                # 48-ACH: validation already proved the unchanged kana
                # action boundaries. Score that actual native action,
                # not accidental short tokens from parsing it alone.
                from reading_segments import _native_action_note_heads
                action_heads=_native_action_note_heads(target.substitute(surface))
                if action_heads:score_head=action_heads[0]
            # A partial lexical head's corpus cost is not the cost of a
            # newly composed action/phrase. Missing whole-surface evidence
            # is omitted across the cohort, then full-context parse cost
            # remains comparable for both a whole word and a composition.
            cost = engine._table_cost(surface if score_head!=surface else score_head)
            # A shared spelling cost cannot identify which native lexical
            # base a composed predicate used (ふい: ふう / ふく). Missing
            # evidence is omitted across its comparison group, never zero.
            from morphology import dictionary_inflections
            if score_head!=surface and len({base
                for pos,form,base,rd in dictionary_inflections(score_head) or ()
                if pos.startswith('動詞,')})>1:
                cost=None
            continuation = continuation_cost(repair.reading)
            context_cost = path_cost(target.substitute(surface))
            context_length=context_reading_length(target.substitute(surface),list(tokenize(target.substitute(surface))))
            reading_cost_key=(reading.text,repair.reading)
            if reading_cost_key not in reading_cost_cache:
                reading_cost_cache[reading_cost_key]=edit_cost(reading.text,repair.reading,*surrounding_readings)
            local_prediction=reading_cost_cache[reading_cost_key]
            argument_evidence=(role_evidence(object_word,surface,target.following,
                before=target.context[:target.start-target.context_start]) if object_word else None)
            if not (argument_evidence and argument_evidence["shared_roles"]) and surface in homophone_positive:
                argument_evidence=homophone_positive[surface][1]
            if not (argument_evidence and argument_evidence['shared_roles']) and proved_objects:
                # A raw kana parse may lose the object that validation has
                # independently proved. Reuse those original noun heads;
                # do not derive an object or its meaning from a candidate.
                for face in proved_objects:
                    proof=role_evidence(face,surface,target.following,before=face+'を')
                    if proof and proof['shared_roles']:
                        # Validation retained the actual original context.
                        # Its proved noun spelling also prevents that same
                        # unknown parse from hiding the candidate verb here.
                        argument_evidence=dict(proof,source='original_object_frame');break
            if case_argument and not (argument_evidence and argument_evidence['shared_roles']):
                case_evidence=role_evidence(case_argument[0],surface,target.following,
                    before=target.context[:target.start-target.context_start],case=case_argument[1])
                if case_evidence and case_evidence['shared_roles']:
                    argument_evidence=case_evidence
            if not (argument_evidence and argument_evidence['shared_roles']):
                from semantic_roles import candidate_internal_argument_evidence
                internal=candidate_internal_argument_evidence(surface,target.following,
                    before=target.context[:target.start-target.context_start])
                if internal:argument_evidence=internal
            argument_fit=bool(argument_evidence and argument_evidence['shared_roles'])
            additional_case_evidence=(role_evidence(ranking_case_argument[0],surface,target.following,
                before=target.context[:target.start-target.context_start],case=ranking_case_argument[1])
                if argument_fit and ranking_case_argument else None)
            additional_case_fit=bool(additional_case_evidence and additional_case_evidence['shared_roles'])
            from semantic_roles import candidate_return_sequence_evidence
            # The following action is independent positive evidence, even
            # when the original dictionary noun has no semantic class yet.
            # With an explicit case, use this default only if that same
            # candidate also positively explains the case/argument.
            sequence_evidence=(candidate_return_sequence_evidence(target.text,surface,
                target.following,target.context[:target.start-target.context_start])
                if (argument_fit or object_word and argument_evidence is None)
                and (not ranking_case_argument or additional_case_fit) else None)

            from semantic_roles import candidate_origin_return_evidence
            origin_return=candidate_origin_return_evidence(surface,target.following)
            subject_evidence=subject_candidate_evidence(subject_word,surface,target.following) if subject_word else None
            subject_fit=bool(subject_evidence and subject_evidence['shared_roles'])
            modifier_evidence=modifier_candidate_evidence(target.context,
                target.start-target.context_start,surface,tokenize)
            modifier_fit=bool(modifier_evidence and modifier_evidence['shared_roles'])
            object_candidate_evidence=candidate_object_evidence(surface,target.following,
                before=target.context[:target.start-target.context_start])
            object_candidate_fit=bool(object_candidate_evidence and object_candidate_evidence['shared_roles'])
            from semantic_roles import retained_nominal_head_support
            retained_nominal=retained_nominal_head_support(target.text,surface)
            from process_familiarity import meaning_evidence as process_meaning
            process_evidence=process_meaning(target,surface)
            from semantic_roles import relative_method_evidence
            relative_evidence=relative_method_evidence(surface,target.following)
            from context_meaning import candidate_evidence as source_meaning
            source_evidence=source_meaning(target.source,target.start,target.end,surface)
            from semantic_roles import request_action_evidence,nominal_input_method_evidence
            request_evidence=request_action_evidence(target.source,target.start,target.end,surface)
            method_evidence=nominal_input_method_evidence(
                target.context,target.start-target.context_start,
                target.end-target.context_start,surface,repair.reading)
            method_spelling=False
            if method_evidence:
                from ime_spelling import project_first_words
                projected=project_first_words(repair.reading,store,dictionary,decisions,tokenize)
                method_spelling=bool(projected and projected[2] and projected[0]==surface)
            from ime_nominal_head import split_nominal_evidence
            nominal_boundary=split_nominal_evidence(target.source,target.start,target.end,surface)

            # SR-D: required validation has passed. Every candidate now uses
            # the same semantic/physical/preservation key; missing optional
            # numeric evidence is removed for the whole comparison group.
            candidate_bases=_candidate_verb_bases(target.substitute(surface),tokenize)
            if preserve_kana and target.boundary_kind in ('kana_predicate','auxiliary_connection'):
                # This whole predicate already passed native grammar and
                # original-context validation. Kana outside its proved edge
                # may make the full parser swallow it as one unknown noun;
                # that parse cannot erase the same verb's native base here.
                candidate_bases |= _candidate_verb_bases(surface,tokenize)
            # A full native reading clause outranks an accidental sequence
            # of known words only at an already anomalous auxiliary seam.
            # This uses the same source grammar and never supplies a spelling.
            native_predicate=_native_candidate_clause_rank(target,repair.reading)
            from reading_segments import completed_sahen_reading,native_bare_action_faces
            retained_action=(target.boundary_kind=='sahen_tail' and target.preserved_head
                and repair.reading.startswith(target.preserved_head)
                and _sahen_grammatical_tail(repair.reading[len(target.preserved_head):])
                and completed_sahen_reading(repair.reading,allow_nonpolite=True,return_action=True)
                    in native_bare_action_faces(target.preserved_head))
            phase_nominal=_native_phase_repair_evidence(target,surface,tokenize)
            native_te=(target.boundary_kind=='lexical' and target.text.endswith('て')
                and any(kind=='品詞文法' for kind,reason,a,b in target.anomalies)
                and argument_fit and _native_written_te_action(
                    surface,repair.reading,tokenize))
            retained_stem=_retained_auxiliary_stem(target,surface)
            written_boundary=_retained_written_nominal_tail(target,surface,reading,repair)
            rank_evidence=dict(
                direct=_reading_strength(reading)[0],
                input_reading=int(reading.source=='current_ime_occurrence' or
                    any(segment[3]=='current_ime_occurrence' for segment in reading.segments)),
                native_predicate=native_predicate,
                # In this source-proved compound-verb window, an exact native
                # continuative form has stronger spelling evidence than an
                # unlisted mixed-kana face of the same repaired reading.
                native_inflection=-int(native_te or retained_stem or retained_action or target.boundary_kind=='compound_verb' and any(
                    pos.startswith('動詞,自立,') and form=='連用形'
                    and rd==repair.reading
                    for pos,form,base,rd in dictionary_inflections(surface) or ())),
                source_relation=-int(bool(source_evidence or request_evidence or nominal_boundary or
                    target.boundary_kind=='interrogative_extent' and surface==target.candidate_surface or
                    argument_evidence and argument_evidence.get('preferred_relation'))),
                # An earlier omitted key leaves this source-attested noun
                # and its exact reading unchanged. A broad object-role match
                # must not erase that boundary. Specific source relations
                # still precede it, and every candidate has passed validation.
                written_boundary=-int(written_boundary),
                added=max(0,len(repair.intended)-len(repair.pressed)),
                method_spelling=-int(method_spelling),
                meaning=-max(2 if source_evidence or request_evidence else 0,
                    (2 if argument_fit and argument_evidence.get('preferred_relation') else
                     int(argument_fit or subject_fit or modifier_fit or object_candidate_fit
                         or retained_nominal or phase_nominal or bool(process_evidence) or bool(relative_evidence)
                         or bool(method_evidence)))
                    +int(additional_case_fit)+int(bool(sequence_evidence))
                    +int(bool(origin_return))),
                written_native=-int(_native_semantic_homophone(target,surface,reading,repair,argument_fit)
                    or written_boundary
                    or retained_stem==2 or _retained_source_kana_nominal_head(target,surface,repair,dictionary)
                    or target.boundary_kind=='marked_written_verb'
                    and any('一'<=c<='鿿' for c in surface)
                    and any(pos.startswith('動詞,自立,') and form=='連用形'
                            and rd==repair.reading
                            for pos,form,base,rd in dictionary_inflections(surface) or ())),
                edits=len(getattr(repair,'steps',())) or int(repair.operation!='same_reading'),
                shift_avoid=int(source_shift_free and _repair_uses_shift(repair)),
                physical=(max(repair.cost,1.0) if source_shift_free
                          and _repair_uses_shift(repair) else repair.cost),
                bases=len(complete_verbs-candidate_bases),
                script=int((any('ァ'<=c<='ヶ' for c in target.text)
                            and not any('ァ'<=c<='ヶ' for c in surface))
                           or (preserve_kana and not _is_reading(surface)
                               and not (target.boundary_kind=='sahen_tail'
                                   and target.preserved_head
                                   and native_spelling_only(repair.reading,surface)))),
                proper=int(engine._is_whole_proper_noun(surface,tokenize)),
                terminal=int(_terminal_auxiliary_fragment(surface,target.following,tokenize))
                         if grammar_rank else 0,
                guesses=sum(segment[3] in ('character_guess','unrecognized_ime_sequence','compound_voicing','source_nominal_voicing')
                            for segment in reading.segments),
                usage=_candidate_usage_tier(surface,score_head,target.following,
                    target.context[:target.start-target.context_start],reading=repair.reading),
                context=-semantic.context_score(score_head,material),
                cost=cost,local_reading=local_prediction,continuation=continuation,parse_cost=context_cost,
                start=target.start,end=target.end)
            # Wider key searches need positive meaning in the unchanged
            # source context. A standalone unknown label is not evidence for
            # replacing it with a familiar word reached by a wider search.
            if repair.operation in ('independent_key_pair','marked_omission','nonadjacent_substitution') and rank_evidence['meaning']>=0:
                reason=('unproven_two_key_context' if repair.operation in ('independent_key_pair','marked_omission')
                        else 'unproven_nonadjacent_key_context')
                diagnostic['rejected'][reason]=diagnostic['rejected'].get(reason,0)+1
                continue
            local_parts=list(tokenize(surface))
            local_verb_bases=tuple(sorted(_candidate_verb_bases(surface,tokenize))) if (
                local_parts and local_parts[0][5] and local_parts[0][3]==0
                and local_parts[0][1].startswith('動詞:自立')) else ()
            rank=()
            row = dict(surface=surface, rank=rank, rank_evidence=rank_evidence, score_head=score_head, local_prediction=local_prediction,
                       local_verb_bases=local_verb_bases,
                       context_scope=(target.context_start,target.context_end),context_reading_length=context_length,
                       object_word=object_word or homophone_positive.get(surface,("",))[0],
                       argument_fit=argument_fit, argument_evidence=argument_evidence,
                       sequence_evidence=sequence_evidence, additional_case_evidence=additional_case_evidence,
                       subject_word=subject_word, subject_fit=subject_fit, subject_evidence=subject_evidence,
                       modifier_evidence=modifier_evidence,modifier_fit=modifier_fit,
                       object_candidate_evidence=object_candidate_evidence,object_candidate_fit=object_candidate_fit,
                       retained_nominal_head=retained_nominal,
                       process_meaning=process_evidence, relative_meaning=relative_evidence, source_meaning=source_evidence,
                       request_meaning=request_evidence, method_meaning=method_evidence,
                       nominal_boundary_evidence=nominal_boundary,
                       reading=asdict(reading), repair=asdict(repair),
                       also_from_legacy=surface == legacy_surface)
            candidates.append(row)
    # The search list is not the normal conversion order. An exact spelling
    # appearing there is positive homophone evidence only, after every face
    # has passed the same source, key, grammar and final-text validation.
    spelling_groups={}
    for row in candidates:
        spelling_groups.setdefault(row['repair']['reading'],set()).add(row['surface'])
    ime_source=(target.boundary_kind=='nominal_field'
        or any(mark[0] in ('IME逆読み','完成節の接続') for mark in target.anomalies)
        or any(needs_ime_context_projection(reading)
               for reading in readings))
    unresolved=[rd for rd,faces in spelling_groups.items()
                if ime_source and len(faces)>1 and rd not in ime_evidence]
    if unresolved:
        try:
            from ime_candidates import SearchCandidates
            with SearchCandidates() as ime:
                if ime.available:
                    for rd in unresolved:
                        ime_evidence[rd]=ime.candidates(rd)
        except (ImportError,OSError,AttributeError):
            pass
    first_spelling={}
    if ime_source:
        ambiguous=[rd for rd,faces in spelling_groups.items() if len(faces)>1]
        if ambiguous:
            try:
                from ime_language import JapaneseIME
                with JapaneseIME() as ime:
                    if ime.available:
                        first_spelling={rd:ime.convert(rd) for rd in ambiguous}
            except (ImportError,OSError,AttributeError):
                pass
    for row in candidates:
        rd=row['repair']['reading']
        hits=ime_evidence.get(rd) or ()
        row['rank_evidence']['ime_support']=(
            -2 if ime_source and first_spelling.get(rd)==row['surface'] else
            -1 if ime_source and row['surface'] in hits else 0)
    ordered = rank_candidates(candidates)
    diagnostic['candidates'] = ordered
    diagnostic['status'] = 'selected' if ordered else 'no_candidate'
    if ordered and unresolved_predicates and proved_objects:
        best=ordered[0]
        from semantic_roles import candidate_evidence
        proofs=[candidate_evidence(face,best['surface'],target.following,
            target.context[:target.start-target.context_start]) for face in proved_objects]
        shared={role for p in proofs if p for role in p.get('shared_roles',())}
        # The generic object class cannot distinguish actions. Retain the
        # source when an equally close native verb has unclassified meaning;
        # a closer single adjacent-key candidate also stays unresolved.
        # Missing meaning cannot justify preferring extra physical events.
        if any(rd!=best['repair']['reading'] and (
                shared=={'object'} and cost<=best['repair']['cost']
                or rd in unresolved_adjacent and cost<best['repair']['cost'])
                for rd,cost in unresolved_predicates.items()):
            diagnostic['status']='unresolved_semantic_competitor'
            return None,diagnostic
    return (ordered[0]['surface'] if ordered else None), diagnostic


def _overlaps(a, b, start, end):
    return start <= a <= end if a == b else a < end and start < b


def _anomaly_spans(target):
    # Semantic context explains an edit; it is not itself the damaged span.
    return tuple((target.start,target.end) if kind=='意味接続' else (a,b)
                 for kind,reason,a,b in target.anomalies)


def _repair_coverage(target):
    """Retain coupled grammar edits, without discarding semantic context spelling."""
    spans=_anomaly_spans(target)
    return (min([target.start]+[a for a,b in spans]),
            max([target.end]+[b for a,b in spans]))


def _legacy_source_changes(source, result, engine, trim_context=True):
    """Retain the source intervals already checked by the earlier path.

    Character display diffs can split one transposition into an insertion
    and a deletion. Those pieces are not independent correction choices.
    Accept interval metadata only when its unchanged gaps and all edits
    reconstruct this exact result; older results fall back to their diff.
    """
    corrected=result.get('corrected',source)
    originals=result.get('original_spans',())
    outputs=result.get('spans',())
    if originals and len(originals)==len(outputs):
        changes=[];left=right=0
        for before,after in zip(originals,outputs):
            if len(before)!=2 or len(after)!=2:break
            a,b=before;c,d=after
            if (not all(isinstance(x,int) for x in (a,b,c,d))
                    or not left<=a<=b<=len(source)
                    or not right<=c<=d<=len(corrected)
                    or source[left:a]!=corrected[right:c]):break
            # Trim only identical outer context. Keep every interior edit
            # as one operation: a transposition is never an insert/delete
            # pair, and an unchanged auxiliary is not a new wider candidate.
            x,y=a,b;u,v=c,d
            while trim_context and x<y and u<v and source[x]==corrected[u]:x+=1;u+=1
            while trim_context and x<y and u<v and source[y-1]==corrected[v-1]:y-=1;v-=1
            if x<y or u<v:changes.append((x,y,corrected[u:v]))
            left=b;right=d
        else:
            if source[left:]==corrected[right:]:return changes
    return [(a,b,corrected[c:d]) for a,b,c,d in engine._diff_spans(source,corrected)]



def _resolved_adjacent_connectives(source,selected,odd,tokenize):
    """A changed native verb can explain unchanged particles at its right edge.

    Prove the entire actual connective reading. Mere disappearance from an
    anomaly list is insufficient, and a separate clause is never covered.
    """
    from morphology import tokenize as native_tokens
    from reading_segments import (native_predicate_link_boundaries,
        completed_native_reading_link,_written_predicate_reading_preserved)
    out=[];source_parts=None
    for a,b in odd:
        owners=[(x,y,face) for x,y,face in selected if y==a]
        if not owners:continue
        if source_parts is None:source_parts=list(tokenize(source))
        tail=[t for t in source_parts if a<=t[3] and t[4]<=b]
        if (len(tail)<2 or tail[0][3]!=a or tail[-1][4]!=b
            or not all(t[5] and t[1].startswith('助詞') for t in tail)
            or not all(x[4]==y[3] for x,y in zip(tail,tail[1:]))):continue
        for x,y,face in owners:
            fragment=face+source[a:b];parts=native_tokens(fragment)
            if (not parts or parts[0].pos!='動詞' or parts[0].pos_sub!='自立'
                or not all(t.has_reading for t in parts)):continue
            reading=''.join(t.reading for t in parts)
            if (any(len(face)<cut<=len(fragment)
                    for cut in native_predicate_link_boundaries(fragment,0))
                and _written_predicate_reading_preserved(parts,0,reading)
                and completed_native_reading_link(reading,allow_unclassified=True)):
                out.append((a,b));break
    return out

def _retain_independent_changes(old_changes, selected, targets, diagnostics=()):
    # A semantic abstention is an adoption decision, not a failed lexical
    # validation. Rechecking the old proposal alone cannot resolve the
    # competing source interpretation. Drop its whole original operation,
    # while retaining independent edits outside the abstained source span.
    held=[(target.start,target.end) for target,diagnostic in zip(targets,diagnostics)
          if diagnostic.get('status')=='unresolved_semantic_competitor']
    old_changes=[change for change in old_changes if not any(
        _overlaps(change[0],change[1],a,b) for a,b in held)]
    coverages=[_repair_coverage(t) for t in targets
               if any((t.start,t.end)==(a,b) for a,b,_ in selected)]
    # The unchanged native object/case is already positive source evidence.
    # Keep it when no predicate candidate survives too: its mere kanji
    # conversion cannot resolve (or hide) the following grammar anomaly.
    coverages.extend((t.context_start,t.start) for t in targets
                     if t.boundary_kind=='kana_predicate')
    retained=[change for change in old_changes if not any(
        _overlaps(change[0],change[1],a,b) for a,b in coverages)]
    # A selected lexical repair may already carry the native voiced host
    # from a prior mark composition. Retain only the consumed mark tail;
    # reapplying the old host would duplicate it, dropping all would strand it.
    from morphology import DAKUTEN_MARKS,HANDAKUTEN_MARKS,normalize_marks,katakana_to_hiragana
    source=targets[0].source if targets else ''
    marks=DAKUTEN_MARKS+HANDAKUTEN_MARKS
    for a,b,face in selected:
        if not face:continue
        for x,y,composed in old_changes:
            if (x!=b-1 or not a<=x<b<y or len(composed)!=1
                    or not all(c in marks for c in source[b:y])):continue
            if (normalize_marks(source[x:y])==composed
                    and katakana_to_hiragana(face[-1])==katakana_to_hiragana(composed)):
                tail=(b,y,'')
                if tail not in retained:retained.append(tail)
    return retained


def _apply(source, changes):
    out = []; cursor = 0
    for a, b, surface in sorted(changes):
        if a < cursor:
            raise ValueError('overlapping source edits')
        out.extend((source[cursor:a], surface)); cursor = b
    out.append(source[cursor:])
    return ''.join(out)


def _candidate_source_kwargs(candidate):
    evidence=candidate.get('reading')
    return {'source_reading':Reading(**evidence)} if evidence else {}


def _validate_joint_choices(selected, retained, targets, diagnostics, engine,
                            tokenize, store, dictionary, decisions, provenance=None):
    """長さの異なる複数補正を合成した状態でも、同じ候補を再検査する。"""
    if provenance is None:
        provenance={(t.start,t.end,c['surface']):(t,d) for t,d in zip(targets,diagnostics)
                    for c in d.get('candidates',())}
    rejected = {}
    # 不成立になった候補へ戻らないため、候補数の合計以内に必ず終わる。
    budget = sum(len(d.get('candidates',())) for d in diagnostics)+len(selected)
    for _ in range(budget):
        changed = False
        for a, b, surface in tuple(selected):
            # Same coordinates can come from different reading/grammar
            # targets. Revalidate the actual selected candidate's owner.
            target,diagnostic = provenance[a,b,surface]
            row = next(c for c in diagnostic['candidates'] if c['surface'] == surface)
            companions = retained+[c for c in selected if c[:2] != (a, b)]
            valid, reason = validate(target, surface, engine, tokenize, store, dictionary,
                                     decisions, row['repair']['reading'], companions,
                                     **_candidate_source_kwargs(row))
            if valid:
                continue
            changed = True
            excluded = rejected.setdefault((a, b), set())
            excluded.add(surface)
            diagnostic.setdefault('joint_rejected', []).append(dict(surface=surface, reason=reason))
            selected.remove((a, b, surface))
            for candidate in diagnostic['candidates']:
                sf = candidate['surface']
                if sf in excluded:
                    continue
                valid, _ = validate(target, sf, engine, tokenize, store, dictionary,
                                    decisions, candidate['repair']['reading'], companions,
                                    **_candidate_source_kwargs(candidate))
                if valid:
                    selected.append((a, b, sf))
                    provenance[a,b,sf]=(target,diagnostic)
                    diagnostic['status'] = 'selected_after_joint_validation'
                    break
                excluded.add(sf)
            else:
                diagnostic['status'] = 'no_joint_candidate'
        if not changed:
            break
    return selected


# SR-D: measured in tools_local/implement_sp_sr_20260913/check/fresh/joint_profile.json.
# Eight initial-state examples: at most 31 mutually compatible single choices;
# warmed mandatory validation 0.10–0.24 ms per candidate. Keep a bounded reserve
# for simultaneous errors, and report a cutoff instead of declaring completion.
MAX_JOINT_COMBINATIONS=256


def _choose_joint_candidates(targets,diagnostics,old_changes,engine,
                             tokenize,store,dictionary,decisions,provenance=None):
    from joint_candidates import groups,choose
    options=[];spans=set()
    for target in targets:
        spans.update(_anomaly_spans(target))
    atoms={span for span in spans if not any(span!=other and span[0]<=other[0]
                                           and other[1]<=span[1] for other in spans)}
    for target,diagnostic in zip(targets,diagnostics):
        if diagnostic.get('status')=='unresolved_semantic_competitor':continue
        # A completed field is one grammatical fact. A shorter word
        # cannot claim to resolve the rest of that source anomaly.
        if any(mark[0]=='完成節の接続' and not
               (target.start<=mark[2] and mark[3]<=target.end)
               for mark in target.anomalies):
            continue
        facts=tuple(sorted(atom for atom in atoms if any(a<=atom[0] and atom[1]<=b
                              for a,b in _anomaly_spans(target))))
        if not facts:continue
        # A word repair can also resolve an overlapping source fact whose
        # diagnostic starts at the preceding case particle. Count its actual
        # resolution, not how many marks happened to enter this search scope.
        extra=[(a,b) for a,b in atoms if (a,b) not in facts
               and target.context_start<=a<b<=target.context_end
               and _overlaps(a,b,target.start,target.end)]
        for row in diagnostic.get('candidates',()):
            resolved=list(facts)
            if extra:
                projected=target.substitute(row['surface'])
                fresh=engine._odd_spans_for_line(projected,tokenize,[],store,dictionary,include_pending=False)
                delta=len(row['surface'])-(target.end-target.start)
                for a,b in extra:
                    left=(a if a<=target.start else target.start)-target.context_start
                    right=(b+delta if b>=target.end else target.start+len(row['surface']))-target.context_start
                    if not any(_overlaps(left,right,x,y) for x,y in fresh):resolved.append((a,b))
            options.append(dict(start=target.start,end=target.end,surface=row['surface'],
                rank=row['rank'],anomalies=tuple(sorted(resolved)),context=(target.context_start,target.context_end),
                target=target,candidate=row,diagnostic=diagnostic))
    selected=[];reports=[]
    for group in groups(options):
        rank_candidates([option['candidate'] for option in group])
        for option in group:option['rank']=option['candidate']['rank']
        def valid(rows):
            changes=[(row['start'],row['end'],row['surface']) for row in rows]
            companions=_retain_independent_changes(old_changes,changes,targets,diagnostics)
            for row,change in zip(rows,changes):
                ok,_=validate(row['target'],row['surface'],engine,tokenize,store,dictionary,
                    decisions,row['candidate']['repair']['reading'],
                    companions+[other for other in changes if other is not change],
                    **_candidate_source_kwargs(row['candidate']))
                if not ok:return False
            return True
        choices,report=choose(group,valid,MAX_JOINT_COMBINATIONS)
        selected.extend((row['start'],row['end'],row['surface']) for row in choices)
        if provenance is not None:
            provenance.update({(row['start'],row['end'],row['surface']):(row['target'],row['diagnostic']) for row in choices})
        reports.append(dict(start=min(row['start'] for row in group),
            end=max(row['end'] for row in group),scope='joint_combinations',**report))
    return selected,reports


def _trace_diagnostic(engine, stage, diagnostic):
    # 通常の画面解析で、全候補の巨大な診断文字列を作らない。
    if engine.TRACE is not None or getattr(engine._trace, '_diagnostic_observer', None):
        engine._trace(stage, repr(diagnostic))


def _legacy_resolves_anomaly(target, changes, engine, tokenize, store, dictionary, decisions, punctuation_changes=()):
    """語本体を保ったまま、同じ原文の異様が隣の修正で解消したか。

    異様の範囲は語尾の接続まで含むが、読む範囲は語本体だけの場合がある。
    その語尾が既に直っていれば、元から正しい語まで重ねて変えない。
    既存出力を無条件には信用せず、広い元の範囲を同じ検算に通す。
    """
    if not target.anomalies:return False
    inside=[row for row in changes if _overlaps(row[0],row[1],target.start,target.end)]
    if inside:
        from mark_usage import proved_cluster_normalization
        normalized=proved_cluster_normalization(target.source,tokenize,store,dictionary,decisions)
        if normalized and all(row in normalized[1] for row in inside):
            from oddness import structural_anomaly_in_range
            projected=_apply(target.source,inside)
            shift=sum(len(face)-(b-a) for a,b,face in inside if b<=target.end)
            if not structural_anomaly_in_range(projected,max(0,target.start-1),
                    min(len(projected),target.end+shift+1),tokenize,store,dictionary):return True
        # A checked same-key terminator resolves the original ending while
        # leaving its lexical body intact. The whole original anomaly still
        # enters the common validator below, including narrower tail targets.
        if not all(row in punctuation_changes and row[1]==target.context_end
                   for row in inside):return False
    start=min([target.start]+[a for _,_,a,b in target.anomalies])
    end=max([target.end]+[b for _,_,a,b in target.anomalies])
    relevant=[c for c in changes if _overlaps(c[0],c[1],start,end)]
    if not relevant:
        # A removed mark cluster may finish a conditional whose last kana
        # starts the next target. Its source intervals touch rather than overlap.
        # The target's own letters stay unchanged; prove its original anomaly
        # has disappeared at the same native seam before reopening those letters.
        from morphology import DAKUTEN_MARKS,HANDAKUTEN_MARKS
        from mark_usage import normalization_seam_is_complete
        from oddness import structural_anomaly_in_range
        marks=DAKUTEN_MARKS+HANDAKUTEN_MARKS
        adjacent=[c for c in changes if c[1]==target.start and not c[2]
                  and c[0]<c[1] and all(x in marks for x in target.source[c[0]:c[1]])]
        if not adjacent:return False
        start=target.context_start;end=target.context_end
        surface=_apply(target.context,[(a-start,b-start,face) for a,b,face in adjacent])
        shift=sum(len(face)-(b-a) for a,b,face in adjacent)
        seam=target.start-start+shift
        if not normalization_seam_is_complete(surface,seam,tokenize):return False
        if structural_anomaly_in_range(surface,max(0,seam-1),
                target.end-start+shift,tokenize,store,dictionary):return False
        proposal=(start,end,surface,'かな入力')
        accepted,reason=engine._check_replacement(target.source,proposal,store,
                                                tokenize,dictionary,decisions)
        return accepted==proposal
    # Keep a prior lexical operation whole even when only its final letter
    # touches the anomaly. Validate the enlarged original context, never a
    # deletion inferred from half of a previously checked transposition.
    start=min([start]+[a for a,b,_ in relevant])
    end=max([end]+[b for a,b,_ in relevant])
    if not target.context_start<=start<end<=target.context_end:return False
    wide=RepairTarget(target.source,start,end,target.context_start,target.context_end,
                      target.anomalies,target.structural,target.source[end:target.context_end])
    surface=_apply(wide.text,[(a-start,b-start,text) for a,b,text in relevant])
    valid,_=validate(wide,surface,engine,tokenize,store,dictionary,decisions)
    return valid


def _legacy_covering_targets(targets,changes):
    """48-AHM: compare a wider prior candidate under the same source facts.

    An earlier lexical replacement can cover a narrower later target. Its
    source interval must enter ordinary reading, physical-key, final-context
    validation and joint ranking instead of being discarded just by width.
    Existing spelling ownership is never enlarged by this projection.
    """
    out=list(targets)
    for start,end,surface in changes:
        # A copula interpretation owns its exact original noun boundary;
        # widening it into a lexical target would discard that very proof.
        covered=[t for t in targets if t.boundary_kind!='kana_copula'
                 and start<=t.start and t.end<=end
                 and (start<t.start or t.end<end)
                 and t.context_start<=start<end<=t.context_end]
        if not covered or any((t.spelling or t.preserved_head) and _overlaps(start,end,t.start,t.end)
                              for t in targets):continue
        contexts={(t.context_start,t.context_end) for t in covered}
        if len(contexts)!=1:continue
        facts=tuple(dict.fromkeys(f for t in covered for f in t.anomalies))
        if not facts:continue
        target=replace(covered[0],start=start,end=end,anomalies=facts,
            structural=any(t.structural for t in covered),
            boundary_kind=('nominal_object' if all(t.boundary_kind=='nominal_object' for t in covered) else 'lexical'),
            following=covered[0].source[end:covered[0].context_end])
        if target not in out:out.append(target)
    return out


def _contained_scope_resolution(target, completed, engine, tokenize, store, dictionary, decisions,
                                source_changes=(), companion_proof=None):
    """Reuse a completed native-word repair after rechecking its whole clause.

    A coarse overlapping search is a fallback, not a second typing event.
    If the local repair is later rejected during joint selection, that search
    is reopened. No candidate, unresolved mark or search cutoff is concealed.
    """
    if (target.boundary_kind not in ('lexical','ime_scope','kana_predicate') or target.spelling
            or target.preserved_head or target.semantic_conflict):return None
    for owner,surface,diagnostic in completed:
        if (not owner.structural or not surface or owner.spelling
                or owner.context_start!=target.context_start or owner.context_end!=target.context_end
                or not (target.start<=owner.start<owner.end<=target.end)
                or (owner.start,owner.end)==(target.start,target.end)
                or diagnostic.get('search',{}).get('state')!='complete'):continue
        if target.boundary_kind not in ('ime_scope','kana_predicate') and any(
                not any(c<=a and b<=d for _,_,c,d in owner.anomalies)
                for _,_,a,b in target.anomalies):continue
        if owner.start>target.start:
            from reading_segments import native_completed_clause_boundaries,native_object_clause_edges
            from morphology import tokenize as native_tokenize
            local=owner.start-owner.context_start
            edges=set(native_completed_clause_boundaries(owner.context))|set(native_object_clause_edges(owner.context))
            edges.update(p.end for p in native_tokenize(owner.context) if p.has_reading
                and p.pos=='助詞' and p.pos_sub.startswith('格助詞'))
            # A merely plausible word prefix is not an independently closed
            # source field. Search the competing whole word before reusing
            # a tail repair; a fresh absence of purple alone proves no boundary.
            if local not in edges:
                from reading_segments import native_attributive_predicate_end
                from morphology import dictionary_inflections
                prefix=owner.context[:local];parts=native_tokenize(prefix)
                adnominal=(len(parts)>=2 and parts[-1].surface=='な'
                    and parts[-1].base_form=='だ' and parts[-1].infl_form=='体言接続'
                    and parts[-2].end==parts[-1].start and parts[-2].has_reading
                    and any(pos.startswith('名詞,形容動詞語幹,') and rd==parts[-2].reading
                            for pos,form,base,rd in dictionary_inflections(parts[-2].surface) or ()))
                from reading_segments import native_surface_nominal_heads
                genitive=(parts and parts[-1].surface=='の' and parts[-1].pos=='助詞'
                    and parts[-1].end==len(prefix)
                    and native_surface_nominal_heads(prefix[:parts[-1].start]))
                # A bare written verb before a malformed tail can itself
                # belong to the damaged word. A real original argument
                # distinguishes a relative clause from that guess.
                relative=(native_attributive_predicate_end(prefix) and any(
                    part.has_reading and part.pos=='助詞' and part.pos_sub.startswith('格助詞')
                    for part in parts[:-1]))
                # A source-proved action noun already supplies the original
                # head boundary for a suru-connection repair. Its homographic
                # tail need not reopen the unchanged head as a new key error.
                from particle_frames import converted_suru_connection_frames
                action_head=(owner.boundary_kind=='suru_connection' and any(
                    frame['start']==target.start and frame['verb_start']==owner.start
                    and frame['verb_end']==owner.end
                    for frame in converted_suru_connection_frames(owner.source)))
                if not (adnominal or genitive or relative or action_head):continue
        candidate=next((c for c in diagnostic.get('candidates',()) if c['surface']==surface),None)
        if candidate is None:continue
        valid,_=validate(owner,surface,engine,tokenize,store,dictionary,decisions,
                         candidate['repair']['reading'],**_candidate_source_kwargs(candidate))
        if not valid:continue
        projected=owner.substitute(surface)
        # Pending marks are in original coordinates. Only fresh structural
        # checks apply to this projected clause; original diagnostics remain.
        companions=()
        if engine._odd_spans_for_line(projected,tokenize,[],store,dictionary,include_pending=False):
            # A separately proved source mark normalization must not reopen
            # this already repaired word as a different typing event. Use
            # only the exact original-coordinate edit still supplied by the
            # legacy plan; never read keys from the normalized sentence.
            from mark_usage import proved_cluster_normalization
            normalized=proved_cluster_normalization(owner.source,tokenize,store,dictionary,decisions)
            if not normalized:continue
            companions=tuple(change for change in normalized[1] if change in source_changes
                and owner.context_start<=change[0]<change[1]<=owner.context_end
                and not _overlaps(change[0],change[1],target.start,target.end))
            if not companions:continue
            valid,_=validate(owner,surface,engine,tokenize,store,dictionary,decisions,
                candidate['repair']['reading'],companions,**_candidate_source_kwargs(candidate))
            if not valid:continue
            projected=_apply(owner.context,[(owner.start-owner.context_start,
                owner.end-owner.context_start,surface)]+[(a-owner.context_start,b-owner.context_start,face)
                    for a,b,face in companions])
            if engine._odd_spans_for_line(projected,tokenize,[],store,dictionary,include_pending=False):continue
        if companion_proof is not None:companion_proof.extend(companions)
        # validate above already applies the common final validator to this
        # exact source edit in its full original context. Recasting it as one
        # sentence-sized word makes the word length_delta guard reject a
        # valid contained edit; it adds no new grammatical evidence.
        return (owner.start,owner.end,surface)
    return None


def _prepare_reopen_choices(line,targets,engine,tokenize,store,dictionary,decisions):
    """Share completed same-reading repairs within this one original line.

    This supplies an already validated alternative to the legacy enumerator.
    Competing projections, remaining source anomalies and incomplete searches
    still use ordinary enumeration. Joint choice/validation remains unchanged.
    """
    prepared={};proposals={}
    for target in targets:
        if not (target.structural and target.candidate_surface and target.candidate_reading):continue
        surface,diagnostic=resolve(target,engine,tokenize,store,dictionary,decisions,None)
        prepared[target]=(surface,diagnostic)
        winner=next((c for c in diagnostic.get('candidates',()) if c['surface']==surface),None)
        if not (surface and winner and winner['repair']['operation']=='same_reading'
                and diagnostic.get('search',{}).get('state')=='complete'):continue
        projected=target.substitute(surface)
        if engine._odd_spans_for_line(projected,tokenize,[],store,dictionary,include_pending=False):continue
        proposals.setdefault(target.context,set()).add(projected)
    from ime_inverse_gate import _CORRECTION_CACHE
    cache=_CORRECTION_CACHE.get()
    if cache is not None:
        for original,choices in proposals.items():
            if len(choices)==1:cache['validated_reopen',line,original]=next(iter(choices))
    return prepared


def _remaining_unchanged_meaning(source, result, engine):
    """Keep a diagnostic when a repaired action exposes an unchanged bad sense.

    This does not feed the output through correction again. Only a shared
    semantic frame connected to an actual edit is evaluated, and an unchanged
    word maps back through an exact matching source interval.
    """
    changed=result.get('corrected',source)
    if changed==source:return result
    from difflib import SequenceMatcher
    from context_meaning import anomalous_frames
    blocks=SequenceMatcher(None,source,changed,autojunk=False).get_matching_blocks()
    edits=list(engine._diff_spans(source,changed))
    residual=[]
    for frame in anomalous_frames(changed):
        x,y=frame['start'],frame['end']
        if not any((frame['evidence_start']<d and c<frame['evidence_end'])
                   or c==d and frame['evidence_start']<=c<frame['evidence_end']
                   for a,b,c,d in edits):continue
        block=next((b for b in blocks if b.b<=x<y<=b.b+b.size),None)
        if block is None:continue
        a=block.a+x-block.b;b=a+y-x
        if any(_overlaps(a,b,c,d) for c,d in result.get('odd_spans',())):continue
        residual.append((a,b,frame['reason']))
    if residual:
        result['odd_spans']=sorted(set(tuple(x) for x in result.get('odd_spans',()))|{(a,b) for a,b,_ in residual})
        result['odd_reasons']=list(result.get('odd_reasons',()))+residual
        result.pop('diagnosis',None)
        for a,b,reason in residual:
            engine._trace('補正後の意味残件',str(dict(start=a,end=b,text=source[a:b],reason=reason)))
    return result


def _extend_linked_source_motion_candidates(targets,diagnostics,engine,tokenize,store,dictionary,decisions):
    """Retry an original rejected motion with separately proved source actions.

    Every candidate is generated again from its unchanged target and reading.
    The common joint chooser must retain a valid preceding action; validating
    the later choice alone still fails. Original options/ranks are unchanged.
    """
    from reading_segments import native_object_predicate_contexts
    extra=[];seen=set();original=list(zip(targets,diagnostics))
    for target,diagnostic in original:
        if diagnostic.get('candidates') or not diagnostic.get('rejected',{}).get('unproven_object_predicate'):continue
        frames=native_object_predicate_contexts(target.context,allow_written_predicate=True)
        if not frames:continue
        for owner,proved in original:
            if (owner.source!=target.source or owner.end>=target.start
                    or owner.context_start!=target.context_start
                    or owner.context_end!=target.context_end):continue
            for row in proved.get('candidates',()):
                change=(owner.start,owner.end,row['surface'])
                key=(target,change)
                if key in seen:continue
                seen.add(key)
                if not any(_source_linked_companion_owns_object(target,frame,(change,)) for frame in frames):continue
                _,retry=resolve(target,engine,tokenize,store,dictionary,decisions,companions=(change,))
                if not retry.get('candidates'):continue
                retry['joint_source_dependency']=change
                extra.append((target,retry))
    for target,diagnostic in extra:
        targets.append(target);diagnostics.append(diagnostic)
    return targets,diagnostics


def _manual_choice_rows(line, targets, diagnostics, changes, engine,
                        tokenize, store, dictionary, decisions):
    """Reuse completed source checks for optional, explicitly chosen repairs.

    Neither missing meaning evidence nor a joint-only hypothesis becomes a
    manual choice here. Each row must work on its original range alone and
    with the independent changes in the final displayed line.
    """
    out=[];seen=set()
    for target,diagnostic in zip(targets,diagnostics):
        for row in diagnostic.get('candidates',()):
            surface=row['surface'];key=(target.start,target.end,surface)
            if key in seen:continue
            seen.add(key)
            if line[target.start:target.end]!=target.text:continue
            reading=row['repair']['reading']
            arguments=_candidate_source_kwargs(row)
            valid,_=validate(target,surface,engine,tokenize,store,dictionary,
                             decisions,reading,**arguments)
            if not valid:continue
            companions=[c for c in changes if not _overlaps(
                c[0],c[1],target.start,target.end)]
            if companions:
                valid,_=validate(target,surface,engine,tokenize,store,dictionary,
                                 decisions,reading,companions,**arguments)
                if not valid:continue
            out.append(dict(start=target.start,end=target.end,base=target.text,
                            surface=surface,reading=reading))
    return out


def with_contextual_repair(fn):
    """通常の置換/途中の再構築/再解析を、最後に同じ原文範囲で検算する。

    既存処理の内部は段階的に移行する。新しく確定した候補はこの返却点で
    合成し、文脈を捨てた別の再解析へ再投入しない。
    """
    from functools import wraps
    import os
    import sys
    @wraps(fn)
    def wrapped(line, *args, **kwargs):
        engine = sys.modules[fn.__module__]
        def argument(name, position, default=None):
            return kwargs.get(name, args[position] if len(args) > position else default)
        store = argument('store', 0)
        tokenize = argument('tokenize_fn', 1)
        dictionary = argument('dict_index', 8)
        method = argument('input_method', 6, 'kana')
        decisions = argument('decisions', 5)
        if (tokenize is None or store is None
                or len(engine._CORRECTION_PATH.get()) != 1
                or os.environ.get('CN_CONTEXTUAL_REPAIR') == '0'):
            return fn(line, *args, **kwargs)
        targets = targets_for_line(line, tokenize, store, dictionary,
                                   input_method=method)
        if method!='kana' or dictionary is None:
            # Written Japanese marks in a native numeric unit are spelling
            # evidence even when the current IME input mode is romaji.
            from morphology import DAKUTEN_MARKS,HANDAKUTEN_MARKS
            marks=DAKUTEN_MARKS+HANDAKUTEN_MARKS
            targets=[t for t in targets if t.spelling or (
                t.boundary_kind=='numeric_mark_counter' and any(c in marks for c in t.text))]
        if not targets:
            legacy=fn(line,*args,**kwargs)
            if method=='kana' and dictionary is not None:
                preserved=_native_kara_note_preserve(
                    line,legacy,store,tokenize,dictionary,decisions,engine)
                if preserved:return preserved
            if (method=='kana' and dictionary is not None
                    and legacy.get('analysis_status') not in ('incomplete','limited')):
                relative=_native_relative_source_spelling(
                    line,store,tokenize,dictionary,decisions,engine)
                if relative:
                    from kana_spelling import _compose_result
                    base=dict(legacy,corrected=line,changed=False,details=[],
                              spans=[],original_spans=[],odd_spans=[],odd_reasons=[],
                              unsure_spans=[])
                    composed=_compose_result(line,base,relative[1],engine,decisions)
                    if composed.get('corrected')==relative[0]:
                        return engine._line_result_contract(line,composed,
                                                            tokenize,dictionary)
            return legacy
        # The source IME's ordinary first conversion can exactly reproduce
        # this malformed field. If the same-key Shift repair already passes
        # the shared original-context validator, the old mixed-run enumerator
        # only repeats work. Keep every other legacy route and final check.
        prepared=_prepare_reopen_choices(line,targets,engine,tokenize,store,dictionary,decisions)
        fast_target=None;fast_resolution=None
        field=line.rstrip('\t\r\n')
        if (method=='kana' and dictionary is not None and field
                and any(c in 'ぁぃぅぇぉ' for c in field)
                and any('一'<=c<='鿿' for c in field)):
            for target in targets:
                if (target.start!=0 or target.end!=len(field)
                        or not target.structural or target.spelling
                        or any(t.structural and target.start<=t.start<t.end<=target.end
                               and (t.start,t.end)!=(target.start,target.end) for t in targets)):
                    continue
                surface,diagnostic=resolve(target,engine,tokenize,store,
                                           dictionary,decisions,None)
                winner=next((row for row in diagnostic.get('candidates',())
                             if row['surface']==surface),None)
                if (surface and diagnostic.get('search',{}).get('state')=='complete'
                        and winner and winner['reading']['source']=='ime_first_roundtrip'
                        and winner['repair']['operation'] in ('shift','adjacent_shift_pair')
                        and any(c in 'ぁぃぅぇぉ' for c in winner['repair']['pressed'])
                        and winner['repair']['pressed'] in field):
                    fast_target=target;fast_resolution=(surface,diagnostic)
                    break
        if fast_target is not None:
            token=_SKIP_MIXED_REOPEN.set(line)
            try:
                legacy=fn(line,*args,**kwargs)
            finally:
                _SKIP_MIXED_REOPEN.reset(token)
            engine._trace('探索省略','初回IME再現と検算済みShift補正に重なる旧混在文字探索')
        else:
            legacy=fn(line,*args,**kwargs)
        if legacy.get('analysis_status')=='incomplete':return legacy
        if method=='kana' and dictionary is not None:
            preserved=_native_kara_note_preserve(
                line,legacy,store,tokenize,dictionary,decisions,engine)
            if preserved:return preserved
        if (method=='kana' and dictionary is not None
                and legacy.get('analysis_status') not in ('incomplete','limited')):
            relative=_native_relative_source_spelling(
                line,store,tokenize,dictionary,decisions,engine)
            if relative:
                from kana_spelling import _compose_result
                base=dict(legacy,corrected=line,changed=False,details=[],
                          spans=[],original_spans=[],odd_spans=[],odd_reasons=[],
                          unsure_spans=[])
                composed=_compose_result(line,base,relative[1],engine,decisions)
                if composed.get('corrected')==relative[0]:
                    return engine._line_result_contract(line,composed,
                                                        tokenize,dictionary)
        # A written object and unchanged linked kana actions can already
        # support same-reading spelling before a bad-parse key alternative.
        if method=='kana' and dictionary is not None and len(line)<=80:
            from reading_segments import _native_action_note_heads
            note=False
            if re.fullmatch(r'[一-鿿]+を[ぁ-ゖ]{8,}',line):
                start=line.index('を')+1;tail=line[start:]
                heads=_native_action_note_heads(tail)
                if heads and 'して' in tail:
                    note=_mixed_action_note_first_spelling(
                        line,start,start+tail.index('して'),heads[0])
            finite=_written_object_native_finite_action(line)
            if note or finite:
                from kana_spelling import project,_compose_result
                proposal=project(line,store,dictionary,decisions)
                # A rejected completed source spelling must not be retried
                # as a partial spelling by the later finish pass. Keep only
                # this already checked source range, not unrelated edits.
                if proposal and engine._user_blocks_replacement(decisions,line,proposal[0]):
                    legacy=dict(legacy,_spelling_keep=[(0,len(line))])
                if (proposal and proposal[1]
                        and (finite or _mixed_action_note_first_spelling(
                            line,*proposal[1][0]))
                        and not engine._user_blocks_replacement(
                            decisions,line,proposal[0])
                        and not engine._odd_spans_for_line(proposal[0],tokenize,[],
                                                           store,dictionary,include_pending=False)):
                    base=dict(legacy,corrected=line,changed=False,details=[],
                              spans=[],original_spans=[],odd_spans=[],odd_reasons=[],
                              unsure_spans=[])
                    composed=_compose_result(line,base,proposal[1],engine,decisions)
                    if composed.get('corrected')==proposal[0]:
                        return engine._line_result_contract(line,composed,
                                                            tokenize,dictionary)
                # The original action chain has positive source grammar.
                # A blocked or unproved spelling cannot license a new key slip.
                if legacy.get('corrected',line)==line:return legacy
                original_odd=engine._odd_spans_for_line(line,tokenize,[],
                    store,dictionary,include_pending=False)
                held=dict(legacy,corrected=line,changed=False,details=[],
                          spans=[],original_spans=[],odd_spans=original_odd,
                          odd_reasons=[],unsure_spans=[])
                return engine._line_result_contract(line,held,tokenize,dictionary)
        old = legacy.get('corrected', line)
        old_changes = _legacy_source_changes(line,legacy,engine)
        punctuation_changes=set()
        for span,detail in zip(legacy.get('original_spans',()),legacy.get('details',())):
            if len(span)!=2 or len(detail)<3 or detail[2]!='記号':continue
            a,b=span;face=detail[1]
            if (a<b and len(face)==b-a and line[a:b]==detail[0]
                    and all(engine._SAMEKEY_PUNCT.get(c)==p for c,p in zip(line[a:b],face))):
                punctuation_changes.add((a,b,face))
        targets=_legacy_covering_targets(targets,old_changes)
        # Resolve contained source-word ranges before their coarse fallbacks.
        # Stable ordering is retained for unrelated and equal-sized ranges.
        targets=sorted(targets,key=lambda t:-sum(
            other.start<=t.start<t.end<=other.end and (t.start,t.end)!=(other.start,other.end)
            for other in targets))
        selected = []; diagnostics = []; completed=[]; deferred={}
        for target in targets:
            companion_proof=[]
            covered=_contained_scope_resolution(target,completed,engine,tokenize,store,dictionary,decisions,
                                                old_changes,companion_proof)
            if covered is not None:
                deferred[len(diagnostics)]=(covered,tuple(companion_proof))
                diagnostics.append(dict(start=target.start,end=target.end,text=target.text,
                    status='resolved_by_contained_change',resolved_by=covered))
                continue
            if _legacy_resolves_anomaly(target,old_changes,engine,tokenize,store,dictionary,decisions,punctuation_changes):
                diagnostic=dict(start=target.start,end=target.end,text=target.text,
                                status='resolved_by_existing_change')
                diagnostics.append(diagnostic)
                _trace_diagnostic(engine,'文脈補正',diagnostic)
                continue
            changes = [change for change in old_changes if _overlaps(
                change[0], change[1], target.start, target.end)]
            legacy_surface = None
            if changes and all(target.start <= a <= b <= target.end for a,b,_ in changes):
                legacy_surface = _apply(target.text, [(a-target.start,b-target.start,text)
                                                      for a,b,text in changes])
            reused=(fast_resolution if target==fast_target else prepared.get(target))
            # The exact prior winner supplies no additional candidate. Preserve
            # the legacy provenance flag while avoiding the same search twice.
            if reused and legacy_surface in (None,reused[0]):
                surface,diagnostic=reused
                if legacy_surface is not None:
                    for candidate in diagnostic.get('candidates',()):
                        candidate['also_from_legacy']=candidate['surface']==legacy_surface
            else:
                surface,diagnostic=resolve(target,engine,tokenize,store,dictionary,decisions,legacy_surface)
            if method!='kana' and target.spelling:
                for candidate in diagnostic['candidates']:
                    candidate['repair']['operation']='small_kana_spelling'
                    candidate['repair']['pressed']=''
                    candidate['repair']['intended']=''
                    candidate['repair']['position']=-1
                    candidate['repair']['source_position']=target.spelling[0].change_start
                    for support in candidate.get('support',()):
                        support['repair']=dict(candidate['repair'])
            diagnostics.append(diagnostic)
            _trace_diagnostic(engine, '文脈補正', diagnostic)
            if surface is not None:
                selected.append((target.start, target.end, surface))
                completed.append((target,surface,diagnostic))
        from joint_meaning import extend as extend_joint_meaning
        targets,diagnostics=extend_joint_meaning(targets,diagnostics,engine,tokenize,store,dictionary,decisions)
        targets,diagnostics=_extend_linked_source_motion_candidates(
            targets,diagnostics,engine,tokenize,store,dictionary,decisions)
        provenance={}
        selected,joint_reports=_choose_joint_candidates(targets,diagnostics,old_changes,engine,
            tokenize,store,dictionary,decisions,provenance)
        # Joint selection can reject the local proposal. Reopen exactly
        # those deferred scopes before accepting the combined result.
        reopened=False
        retained_dependencies=_retain_independent_changes(old_changes,selected,targets,diagnostics)
        for index,(dependency,companions) in deferred.items():
            # If joint selection removes either source edit, its broader
            # search is no longer covered and must run normally.
            if dependency in selected and all(c in retained_dependencies+selected for c in companions):continue
            target=targets[index]
            surface,diagnostics[index]=resolve(target,engine,tokenize,store,dictionary,decisions,None)
            reopened=True
        if reopened:
            provenance={}
            selected,joint_reports=_choose_joint_candidates(targets,diagnostics,old_changes,engine,
                tokenize,store,dictionary,decisions,provenance)
        # 語本体を直す新候補へ、同じ接続の語尾を直す旧候補を重ねない。
        # どちらも単独では成立しても、合成すると別の文になるため。
        retained = _retain_independent_changes(old_changes, selected, targets, diagnostics)
        # 新しい候補がない場合も、古い経路が部分だけを直して不整合を残すのを防ぐ。
        for target in targets:
            # An optional request/copula/object interpretation owns only a
            # repair it proves. Missing proof cannot revoke a lexical edit.
            if target.boundary_kind in ('kana_request','kana_copula','question_particle','nominal_object','ime_scope','sahen_tail'):continue
            if any(_overlaps(target.start, target.end, a, b) for a, b, _ in selected):
                continue
            overlapping = [change for change in retained if _overlaps(
                change[0], change[1], target.start, target.end)]
            if not overlapping:
                continue
            if all(target.start <= a <= b <= target.end for a, b, _ in overlapping):
                surface = _apply(target.text, [(a-target.start, b-target.start, text)
                                               for a, b, text in overlapping])
                valid, reason = validate(target, surface, engine, tokenize, store, dictionary, decisions)
            else:
                # 既存経路がより広い範囲を直す場合はこの狭い対象から判断しない。
                continue
            if not valid:
                retained = [change for change in retained if change not in overlapping]
                engine._trace('文脈最終検査', f'{target.text!r} → {surface!r} を除外: {reason}')
                diagnostics.append(dict(start=target.start, end=target.end,
                                        status='legacy_rejected', surface=surface, reason=reason))
        selected = _validate_joint_choices(selected, retained, targets, diagnostics, engine,
                                            tokenize, store, dictionary, decisions, provenance)
        corrected = _apply(line, retained+selected)
        final_choices = {(a,b):surface for a,b,surface in selected}
        for diagnostic in diagnostics:
            bounds=(diagnostic['start'],diagnostic['end']);surface=final_choices.get(bounds)
            owner=provenance.get(bounds+(surface,))
            diagnostic['selected'] = surface if owner and owner[1] is diagnostic else None
            _trace_diagnostic(engine, '文脈補正確定', diagnostic)
        result = dict(legacy)
        manual=_manual_choice_rows(line,targets,diagnostics,retained+selected,
            engine,tokenize,store,dictionary,decisions)
        if manual:
            result['contextual_choices']=dict(version=1,source=line,input_method=method,candidates=manual)
        result['search_reports']=[dict(start=d['start'],end=d['end'],**d['search']) for d in diagnostics if 'search' in d]+joint_reports
        if any(d['state']=='truncated' for d in result['search_reports']):
            result['analysis_status']='limited'
            result['stop_reason']='search_limit'
        if engine.TRACE is not None:
            result['contextual_diagnostics'] = diagnostics
        # Every selected candidate passed the original-context seam check.
        # Its lexical boundary may be wider than the actual character diff:
        # 乳力 -> 入力 also resolves the old 力/し split on unchanged letters.
        resolved_ranges=[(a,b) for a,b,surface in selected]
        from repaired_spelling import retained_frames
        result['_repair_surfaces']=retained_frames(line,legacy,retained,selected,engine)
        result['_repair_surfaces'] += [(a,b,surface,provenance[(a,b,surface)][0].boundary_kind
            if (a,b,surface) in provenance else '') for a,b,surface in selected]
        from repaired_spelling import display_frames
        result['_grammatical_display_frames']=display_frames(line,corrected,targets,diagnostics,engine,tokenize)
        stale_mark=any(_overlaps(a,b,x,y) or a==y for a,b in result.get('odd_spans',())
                       for x,y in resolved_ranges)
        if corrected == old and not stale_mark:
            return _remaining_unchanged_meaning(line,result,engine)
        original_spans = []; spans = []; details = []
        display_changes=list(engine._diff_spans(line, corrected))
        # Deletions and multi-part request repairs need one nonempty rejection
        # pair. Keep the proved original frame so menu actions stop the actual
        # candidate, rather than trying to record an empty character deletion.
        for a,b,surface in selected:
            owner=provenance.get((a,b,surface))
            if not owner:continue
            kind=owner[0].boundary_kind
            request=(kind in ('kana_request','kana_copula'))
            if kind=='kana_predicate':
                from reading_segments import _native_request_tail
                request=_native_request_tail(list(tokenize(surface)))
            if kind not in ('particle_intrusion','question_particle') and not request:continue
            c=a+sum(len(text)-(y-x) for x,y,text in retained+selected if y<=a)
            display_changes=[row for row in display_changes if not (a<=row[0] and row[1]<=b)]
            display_changes.append((a,b,c,c+len(surface)))
        for a, b, c, d in sorted(display_changes):
            original_spans.append((a, b)); spans.append((c, d))
            details.append((line[a:b], corrected[c:d], '表記補正' if method!='kana' else 'かな入力'))
        reasons = []
        # Display diffs describe actual edits; resolved ranges describe proven grammar.
        odd = engine._odd_spans_for_line(line, tokenize, original_spans+resolved_ranges,
                                         store, dictionary, reasons_out=reasons)
        adjacent=_resolved_adjacent_connectives(line,selected,odd,tokenize)
        if adjacent:
            resolved_ranges+=adjacent
            odd=[span for span in odd if span not in adjacent]
        # An unchanged opaque recipient may become grammatical when its
        # predicate is repaired. Reuse the same final-source proof used for
        # typing that result directly; absence of a mark alone proves nothing.
        if odd and selected and corrected!=line:
            from reading_segments import source_opaque_object_ranges
            from difflib import SequenceMatcher
            proved=source_opaque_object_ranges(corrected)
            if proved:
                blocks=SequenceMatcher(None,line,corrected,autojunk=False).get_matching_blocks()
                edits=list(engine._diff_spans(line,corrected))
                fresh=engine._odd_spans_for_line(corrected,tokenize,[],store,dictionary,include_pending=False)
                cleared=[]
                for a,b in odd:
                    mapped=next(((block.b+a-block.a,block.b+b-block.a) for block in blocks
                                 if block.a<=a<b<=block.a+block.size),None)
                    if not mapped:continue
                    x,y=mapped
                    if any(x<z and c<y for c,z in fresh):continue
                    if any(lo<=x<y<=hi and any(lo<=c<d<=hi for aa,bb,c,d in edits)
                           for lo,cut,hi in proved):cleared.append((a,b))
                resolved_ranges+=cleared
                odd=[span for span in odd if span not in cleared]
        unsure = [span for span in result.get('unsure_spans', []) if not any(
                  _overlaps(span[0], span[1], a, b) for a, b in original_spans)]
        result.update(original=line, corrected=corrected, changed=corrected != line,
                      details=details, original_spans=original_spans, spans=spans,
                      odd_spans=odd, odd_reasons=reasons, unsure_spans=unsure)
        if resolved_ranges:
            # Display diffs can leave unchanged characters inside a proved
            # replacement. Carry the accepted source interval separately.
            result['_validated_repair_ranges']=resolved_ranges
            result['_validated_corrected']=corrected
        result.pop('diagnosis', None)
        return _remaining_unchanged_meaning(line,result,engine)
    return wrapped
