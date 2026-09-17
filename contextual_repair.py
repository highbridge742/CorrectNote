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


_SEPARATOR = re.compile(r'[\t\r\n。！？!?;；⇒→]|\s{2,}')


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
    return _kana(text).translate(str.maketrans({'\u3099':'゛','\u309a':'゜'}))


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


def _auxiliary_connection_mismatch(a,b,previous=None):
    """Reuse native grammar for both target ownership and its complete tail."""
    import oddness
    return bool(oddness.causative_aux_mismatch(a,b)
        or oddness.passive_aux_mismatch(a,b)
        or oddness.auxiliary_te_mismatch(a,b)
        or oddness.completed_tsu_aux_mismatch(a,b)
        or oddness.orphan_sokuon_mismatch(a,b,previous)
        or (a[5] and b[5] and a[1].startswith('動詞')
            and b[1].startswith('動詞:非自立')
            and oddness.infl_mismatch(a,b,previous)))


def _kana_grammar_boundary(parts, begin, finish):
    """かなの語の断片と、辞書活用で確定できる接続不一致を分ける。

    語の内部の読み探索は既存経路に残す。語をまたぐ活用の不一致は
    漢字表記と同じ原文範囲で検査する。異様判定そのものは共有する。
    """
    import oddness
    for i in range(1, len(parts)):
        a, b = parts[i-1], parts[i]
        if a[3] >= finish or b[4] <= begin:
            continue
        if (oddness.polite_aux_mismatch(a, b) or oddness.excess_aux_mismatch(a,b) or oddness.mai_aux_mismatch(a,b)
                or oddness.repeated_polite_aux_mismatch(parts[i-2] if i>1 else None,a,b)):
            return True
        if not _auxiliary_connection_mismatch(a,b,parts[i-2] if i>1 else None):
            continue
        # かなは語中も動詞・助動詞へ割れやすい。接尾の一字を見ただけで
        # 語内探索から奪わず、述語としての明示的な語尾まである範囲を移す。
        if _completed_predicate_token(b):
            return True
        if i+1 < len(parts):
            c=parts[i+1]
            if c[3]!=b[4] or not c[5]:
                continue
            if c[1].startswith('助詞:接続助詞') and c[0] in ('て','で','つつ','ながら'):
                return True
            if c[1].startswith('助動詞'):
                from morphology import dictionary_inflections
                if any(p.startswith('助動詞,') and base in ('ます','た','ない','たい','ぬ','ん','う')
                       for p,form,base,rd in dictionary_inflections(c[0]) or ()):
                    return True
    return False


def _unexplained_kana_request_targets(line, lo, hi, tokenize, store, dictionary, source_anomalies=(), grammar_spans=None):
    """48-AGL: reuse source kana oddness for a native request-word repair.

    No requested spelling is guessed here. The clause edge or a native
    te/de link supplies the original left boundary.
    Object/case predicates already have their own source-proof route.
    Candidate requests still pass the ordinary physical and final checks.
    """
    from morphology import HAS_JANOME
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
    parts=native_tokenize(clause)
    for previous,link in zip(parts,parts[1:]):
        if (previous.has_reading and link.has_reading and previous.end==link.start
                and link.surface in ('て','で') and link.pos=='助詞'
                and link.pos_sub.startswith('接続助詞') and previous.pos=='動詞'
                and _modern_te_allowed(previous.surface,previous.reading,link.surface) is True):
            starts.add(link.end)
    result=[]
    # 48-AJF: the same already marked kana clause may instead contain a
    # noun slot bounded by an actual genitive and case. A filler-like
    # parse inside that malformed noun cannot erase the surrounding frame.
    from reading_segments import native_modified_argument_slots,native_nominal_phrase_faces
    for begin,head_start,case_start,finish,relative in native_modified_argument_slots(clause):
        if native_nominal_phrase_faces(clause[head_start:case_start]):continue
        anomalies=tuple(('品詞文法','未説明の修飾名詞',lo+a,lo+b)
                        for a,b in slot_odd if a<case_start and head_start<b)
        if anomalies:
            result.append(RepairTarget(line,lo+head_start,lo+case_start,lo,hi,
                anomalies,True,clause[case_start:],'lexical'))
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
                  if a<len(clause) and start<b),True,'','kana_request'))
    return result


def _counted_nominal_targets(targets):
    """48-AID: reuse an existing anomaly for the noun before a native count.

    A complete unchanged counter and finite predicate isolate the noun.
    Known native noun readings stay intact; absence alone creates no target.
    New candidates use ordinary lexical reading/key/meaning/final checks.
    """
    from reading_segments import native_nominal_phrase_faces,completed_native_link_clause
    targets=list(targets)
    for target in tuple(targets):
        if (target.boundary_kind!='kana_request' or not target.structural
                or not target.anomalies or target.spelling or target.preserved_head):continue
        for cut,sizes in _original_counted_object_slots(target.context):
            end=target.context_start+cut-1
            noun=target.source[target.start:end]
            if (not 2<=len(noun)<=12 or not _is_input_reading(noun)
                    or native_nominal_phrase_faces(noun)
                    or not any(a<end and target.start<b for _,_,a,b in target.anomalies)):
                continue
            if not any(completed_native_link_clause(target.context[cut+size:]) for size in sizes):continue
            candidate=replace(target,end=end,boundary_kind='lexical',
                following=target.source[end:target.context_end])
            if candidate not in targets:targets.append(candidate)
    return targets


def _native_action_tail_targets(targets):
    """Reuse a marked kana tail with an unchanged native action head."""
    from reading_segments import native_polite_action_prefixes
    targets=list(targets)
    for target in tuple(targets):
        if (target.boundary_kind!='kana_request' or not target.structural or not target.anomalies
                or target.spelling or target.preserved_head):continue
        for cut in native_polite_action_prefixes(target.text):
            if not any(target.start+cut<b and a<target.end for _,_,a,b in target.anomalies):continue
            wide=replace(target,boundary_kind='auxiliary_connection',preserved_head=target.text[:cut])
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


def _native_kana_targets(line,lo,hi,tokenize,store,dictionary,odd,grammar_spans=None):
    """One source reading/argument proof shared by full and comma scopes."""
    clause=line[lo:hi]
    if grammar_spans is None:
        import pos_grammar
        grammar_spans=pos_grammar.odd_kana_spans(clause,dictionary,store)
    result=list(_unexplained_kana_request_targets(line,lo,hi,tokenize,store,dictionary,
                                                source_anomalies=odd,grammar_spans=grammar_spans))
    # 48-ACQ: a kana grammar anomaly is already a judgment even when
    # the tokenizer swallowed a whole predicate as one unknown token.
    # Keep its unchanged noun/case in context; edit only the predicate.
    from reading_segments import native_object_predicate_cuts, completed_native_reading
    kana_cuts=native_object_predicate_cuts(clause)
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


def targets_for_line(line, tokenize, store, dictionary, _keep_completed=True):
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
    completed_boundaries = set()
    boundaries = [0]
    for m in _SEPARATOR.finditer(line):
        boundaries.extend((m.start(), m.end()))
    boundaries.append(len(line))
    for lo, hi in zip(boundaries[::2], boundaries[1::2]):
        clause = line[lo:hi]
        if not clause:
            continue
        from particle_frames import interrupted_topic_frames
        for frame in interrupted_topic_frames(clause,dictionary):
            start,end=lo+frame['start'],lo+frame['end']
            targets.append(RepairTarget(line,start,end,lo,hi,
                (('助詞接続','話題に挟まった注意名詞',start,end),),
                True,line[end:hi],'particle_intrusion',clause[frame['start']:frame['case_start']]))
        parts = list(tokenize(clause))
        odd = oddness.is_odd_run(clause, tokenize, with_spans=True,
                                store=store, dict_index=dictionary, complete_line=True)
        import pos_grammar
        grammar_spans=pos_grammar.odd_kana_spans(clause,dictionary,store)
        targets.extend(_native_kana_targets(line,lo,hi,tokenize,store,dictionary,odd,grammar_spans))
        targets.extend(_comma_native_kana_targets(line,lo,hi,tokenize,store,dictionary,odd,grammar_spans))
        from mark_usage import unattached_positions
        mark_positions=frozenset(unattached_positions(clause))
        def separator(token):
            from pos_grammar import is_functional_noun
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
        strong = set(tuple(p) for p in oddness.is_odd_run(
            clause, tokenize, with_spans=True, store=store, dict_index=dictionary,
            skip_join=True, complete_line=True))
        from semantic_roles import conflicting_nominal_compounds
        meaning_boundaries={row[2] for row in conflicting_nominal_compounds(clause,parts)}
        from semantic_roles import conflicting_object_predicates
        predicate_boundaries={row[2] for row in conflicting_object_predicates(clause,parts)}
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
                if (t[1].startswith('助動詞') and
                        (parts[i-1][1].startswith(('動詞', '形容詞'))
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
                        and t[0][-1] in ('を', 'に', 'へ', 'が')
                        and nxt[5] and (nxt[1].startswith(('動詞', '形容詞')) or
                            (nxt[1].startswith('名詞:サ変接続') and i+2 < len(parts)
                             and parts[i+2][0] in ('し', 'する', 'すれ')
                             and parts[i+2][1].startswith('動詞')))):
                    finish = min(finish, t[4]-1)
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
            # 全かなでも、活用の接続が崩れた範囲は同じ検査へ通す。
            # 語の途中で切れたという印だけで従来の語内探索を置き換えない。
            if (not any('一' <= c <= '鿿' or 'ァ' <= c <= 'ヶ' for c in text)
                    and not _kana_grammar_boundary(parts, begin, finish)
                    and not any(begin<=i<finish for i in mark_positions)):
                continue
            # 見慣れない普通名詞の連接だけなら、従来の証拠を持つ経路に委ねる。
            relevant = [t for t in parts if t[3] < finish and begin < t[4]]
            if not structural and all(t[5] and t[1].startswith('名詞') for t in relevant):
                continue
            anomalies = tuple((x, y, lo+s, lo+e) for x, y, s, e in odd
                              if s < finish and begin < e)
            following = clause[finish:]
            target = RepairTarget(line, lo+begin, lo+finish, lo, hi,
                                  anomalies, structural, following,
                                  'nominal_meaning' if begin in meaning_boundaries else 'lexical')
            if target not in targets:
                targets.append(target)
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
                        or oddness.completed_tsu_aux_mismatch(parts[i-1],b)):
                    continue
                extended=b[4]
                for c in parts[i+1:]:
                    if c[3]!=extended or not c[1].startswith(('助動詞','助詞:接続助詞')):
                        break
                    extended=c[4]
                if extended-begin>18:
                    break
                a=parts[i-1]
                head=(a[0] if a[3]==begin and a[1].startswith('名詞:サ変接続') else '')
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
    bounded=[]
    for target in targets:
        edges=[target.context_start+edge for edge in native_completed_clause_boundaries(target.context)
               if target.start<target.context_start+edge<target.end]
        if edges and target.boundary_kind=='lexical' and not target.preserved_head and not target.spelling:
            target=replace(target,start=max(edges))
        if target not in bounded:bounded.append(target)
    targets=bounded
    targets=_counted_nominal_targets(targets)
    targets=_native_action_tail_targets(targets)
    targets=_native_verb_prefix_targets(targets)
    targets=_native_focused_prefix_targets(targets)
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
    return ordered


def _source_clause_bounds(line,start,end):
    lo,hi=0,len(line)
    for sep in _SEPARATOR.finditer(line):
        if sep.end()<=start:lo=sep.end()
        elif sep.start()>=end:hi=sep.start();break
    return lo,hi


def _source_object_predicate_frame(line,start,end):
    """Share the original clause's proved object with validation and ranking."""
    from reading_segments import native_object_predicate_contexts
    lo,hi=_source_clause_bounds(line,start,end)
    original=line[lo:hi]
    from reading_segments import native_completed_clause_boundaries
    seams=tuple(edge for edge in native_completed_clause_boundaries(original) if edge<=start-lo)
    frames=[f for f in native_object_predicate_contexts(original) if f[1]<=start-lo
            and not any(f[1]<edge for edge in seams)]
    # An independently completed earlier clause owns its object. A mark
    # in the next clause must not bind that object to an unrelated predicate;
    # an explicit object of the later clause still supplies its own frame.
    if not frames:return None
    clause,cut,faces=max(frames,key=lambda f:(f[0],f[1]))
    return lo,hi,clause,cut,faces


@lru_cache(maxsize=4096)
def _original_counted_object_slots(text):
    """Literal accusative/counter slots, including an unreadable kana token.

    A known lexical word is never split to invent を. The unchanged native
    counter attests its own boundary; no noun or anomaly is inferred here.
    """
    from morphology import tokenize
    from reading_segments import _native_counter_prefixes,native_case_positions
    parts=tokenize(text);slots=[]
    for position in native_case_positions(text,parts):
        tail=text[position+1:]
        sizes=_native_counter_prefixes(tail,tokenize(tail))
        if sizes:slots.append((position+1,sizes))
    return tuple(slots)


def _changed_quantity_object_allowed(line,start,end,surface):
    """48-AIG: a changed object still owns its unchanged case and quantity.

    Match the actual source case/counter through equal text, independently
    of the proposed replacement's outer boundary. A wider candidate cannot
    evade the same proof, and an edit in a separate clause does not invoke it.
    No source anomaly is inferred from a missing noun/meaning classification.
    """
    if 'を' not in line:return True
    from reading_segments import (native_object_predicate_contexts,native_object_predicate_proof,
                                  _native_source_clauses)
    from difflib import SequenceMatcher
    lo,hi=_source_clause_bounds(line,start,end)
    original=line[lo:hi]
    changed=line[lo:start]+surface+line[end:hi]
    clauses=list(_native_source_clauses(changed))
    frames=[(offset+begin,offset+cut,nouns,offset+len(clause))
            for offset,clause in clauses
            for begin,cut,nouns in native_object_predicate_contexts(clause)]
    matcher=SequenceMatcher(None,original,changed,autojunk=False)
    edits=[(a,b,c,d) for tag,a,b,c,d in matcher.get_opcodes() if tag!='equal']
    for predicate_start,quantities in _original_counted_object_slots(original):
        cuts={block.b+predicate_start-block.a for block in matcher.get_matching_blocks()
              if block.a<predicate_start and any(predicate_start+size<=block.a+block.size for size in quantities)}
        for cut in cuts:
            # A malformed verb/unknown sequence has no nominal frame. Its
            # absence cannot certify the proposed object. Keep independent
            # completed clauses outside the affected object region.
            if not any(edge==cut for begin,edge,nouns,finish in frames):
                from morphology import tokenize
                from reading_segments import (native_completed_clause_boundaries,
                                              completed_native_link_clause)
                for offset,clause in clauses:
                    if not offset<cut<=offset+len(clause):continue
                    prefix=clause[:cut-offset-1]
                    boundaries=list(native_completed_clause_boundaries(clause))
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
            if affected and not any(native_object_predicate_proof(changed[begin:finish],cut-begin,nouns)
                                    for begin,nouns,finish in affected):return False
    return True


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
        if not faces:return False
        if relative:
            from semantic_roles import relative_action_support
            action,occupied=relative
            if not any(relative_action_support(face,action,occupied) for face in faces):
                return False
        if not native_object_predicate_proof(fragment,new_case-new_begin+1,faces,allow_link=True):
            return False
    return True


def object_predicate_candidate_allowed(line,start,end,surface):
    """A proposed edit completes the same independently proved object clause."""
    from reading_segments import native_object_predicate_proof
    if not _changed_genitive_object_allowed(line,start,end,surface):return False
    frame=_source_object_predicate_frame(line,start,end)
    if frame is None:
        return _changed_quantity_object_allowed(line,start,end,surface)
    lo,hi,clause,cut,faces=frame
    original=line[lo:hi];changed=line[lo:start]+surface+line[end:hi]
    src,dst=original[clause:],changed[clause:]
    if src[:cut-clause]!=dst[:cut-clause]:return False
    if native_object_predicate_proof(dst,cut-clause,faces):return True
    retained=_unchanged_finite_connective(src,dst)
    return bool(retained and dst.endswith(retained)
                and native_object_predicate_proof(dst[:-len(retained)],cut-clause,faces))


def changed_native_action_attachment_allowed(line,start,end,surface):
    """A narrow/wide edit cannot leave an unchanged action head unattached.

    The same source prefix evidence constructs the wider repair target.
    It does not compel a repair or supply a new anomaly. Known grammatical
    clauses and nominal compounds retain their full shared native proof.
    """
    from reading_segments import (native_completed_clause_boundaries,native_polite_action_prefixes,
                                  completed_native_reading,completed_native_source_sequence)
    lo,hi=_source_clause_bounds(line,start,end)
    original=line[lo:hi];changed=line[lo:start]+surface+line[end:hi]
    begins=[0]+[edge for edge in native_completed_clause_boundaries(original) if edge<=start-lo]
    begin=max(begins);old=original[begin:];new=changed[begin:]
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


def preserves_completed_reading_link(line,start,end,surface):
    """Shared final contract: a candidate retains a proved source clause/link."""
    from reading_segments import native_completed_clause_boundaries,native_nominal_topic_prefix
    lo,hi=_source_clause_bounds(line,start,end)
    original=line[lo:hi]
    changed=line[lo:start]+surface+line[end:hi]
    topic=native_nominal_topic_prefix(original)
    if topic and start-lo<topic and changed[:topic]!=original[:topic]:return False
    return all(start-lo>=edge or changed[:edge]==original[:edge]
               for edge in native_completed_clause_boundaries(original))


def _reading_strength(reading):
    direct=(reading.source in ('current_ime_occurrence','original_spelling','literal_kana')
            or (reading.segments and all(s[3] in ('literal_kana','current_ime_occurrence') for s in reading.segments)))
    saved=reading.source=='saved_ime_pair'
    return (0 if direct else 1 if saved else 2, reading.rank, reading.text,
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


from contextvars import ContextVar
_SEARCH=ContextVar('correctnote_contextual_search',default=None)


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


def reading_evidence(target, tokenize, dictionary, limit=32):
    """IME対応→辞書の語/活用→未知部分の一字推測。語の読みを壊さない。"""
    import kanji_guess
    from inflected_lexicon import dictionary_readings
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
    beam = [('', 0, ())]
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
    for token_number, t in enumerate(parts):
        options = []
        literal = _input_kana(t[0])
        if _is_input_reading(literal):
            options.append((literal, 0, 'literal_mark_key' if any(c in '゛゜' for c in literal) else 'literal_kana'))
        elif t[5] and _is_reading(t[2]):
            options.append((t[2], 0, 'analyzed_word'))
        for rd in occurrence_readings(target.source,target.start+t[3],target.start+t[4]):
            options.insert(0,(rd,0,'current_ime_occurrence'))
        for rd in kanji_guess.ime_readings_for(t[0]):
            if _is_reading(rd):
                options.insert(0, (rd, 0, 'saved_ime_segment'))
        if not _is_input_reading(literal):
            for rank, rd in enumerate(dictionary_readings(t[0])):
                if _is_reading(rd) and rd not in [r for r, _, _ in options]:
                    options.append((rd, rank+1, 'dictionary_word'))
        # 複合語の後項の連濁は読みの変種。未入力の濁点を補う打鍵とは区別する。
        nominal_use = (t[1].startswith('名詞') or (t[1].startswith('動詞')
                       and t[6].startswith('連用') and target.following[:1] in ('を','が','に','へ','の')))
        if (token_number and nominal_use and '一' <= t[0][0] <= '鿿'
                and parts[token_number-1][1].startswith('名詞')
                and '一' <= parts[token_number-1][0][-1] <= '鿿'):
            voiced = dict(zip('かきくけこさしすせそたちつてとはひふへほ',
                              'がぎぐげござじずぜぞだぢづでどばびぶべぼ'))
            for rd, rank, origin in tuple(options):
                if rd and rd[0] in voiced:
                    options.append((voiced[rd[0]]+rd[1:], rank+1, 'compound_voicing'))
        if not options:
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
        elif (len(t[0]) == 1 and '一' <= t[0] <= '鿿'
                and (t[1].startswith('名詞') or target.boundary_kind=='question_particle')):
            # 一字の誤変換には、最良解析の品詞以外の音訓もあり得る。
            # 終止した丁寧節の異様な末尾も、名詞だけでなく同じ読み根拠で扱う。
            # 多字の既知語や送り仮名を持つ活用形は一字読みへ分解しない。
            existing = {r for r, _, _ in options}
            options.extend((r['reading'], r['rank']+4, 'character_guess') for r in
                           _bounded(kanji_guess.reading_combos_with_evidence(t[0], dictionary, max_combos=9),8,'single_character_readings')
                           if r['reading'] not in existing)
        combined = [(prefix+rd, cost+rank, segments+((t[3], t[4], rd, origin),))
                    for prefix, cost, segments in beam for rd, rank, origin in options]
        # 先着で切らず、各段階で全ての枝を比較してから上限を適用する。
        beam = _bounded(sorted(set(combined), key=lambda item: (item[1], item[0],item[2])),limit,'token_readings')
    for rd, rank, segments in beam if parts else ():
        add(Reading(rd, 'contextual_token_sequence' if use_context else 'token_sequence', rank, segments))
    # 語単位の読みが得られない残りを救う。既知の活用を一字推測へ置き換えない。
    if not out:
        for r in _bounded(kanji_guess.reading_combos_with_evidence(text, dictionary, max_combos=limit+1),limit,'fallback_readings'):
            add(Reading(r['reading'], r['source'], r['rank']))
    return _bounded(merge_readings(out.values()),limit,'readings')


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
    return tuple((other, k._base_distance(key, other)) for other in k.KANA_POSITIONS
                 if other != key and 0 < k._base_distance(key, other) <= 1.05)


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
        if not any(k.same_physical_key(key,neighbor) for neighbor in adjacent) and any(0 < k._base_distance(key, neighbor) <= 1.05 for neighbor in adjacent):
            add(keys[:i]+keys[i+1:], 'adjacent_intrusion', i, key, '', 1.0)
        if any(k.same_physical_key(key,neighbor) for neighbor in adjacent) and dup_repair_enabled():
            add(keys[:i]+keys[i+1:], 'duplicate', i, key, '', 1.0)
        if i+1 < len(keys) and key != keys[i+1]:
            add(keys[:i]+(keys[i+1], key)+keys[i+2:], 'transposition', i,
                key+keys[i+1], keys[i+1]+key, 1.0)
        if key in k.SMALL_KANA_PAIR:
            other = k.SMALL_KANA_PAIR[key]
            add(keys[:i]+(other,)+keys[i+1:], 'shift', i, key, other, 0.4)
    return tuple(sorted(out.values(), key=lambda row: (row.cost, row.reading)))


def request_shift_key_repairs(target, reading, before='', after=''):
    """One Shift slip plus a separate physical slip in an anomalous request.

    This fallback supplies only native request inflections. Both operations
    keep original key coordinates, and deletions use original neighbors.
    """
    if target.boundary_kind not in ('kana_request','kana_predicate') or reading!=target.text:return
    from morphology import dictionary_inflections
    seen=set()
    for first in key_repairs(reading,before,after):
        if first.operation!='shift' or first.pressed not in 'ぁぃぅぇぉ':continue
        for second in key_repairs(first.reading,before,after):
            if second.operation not in ('adjacent_substitution','adjacent_intrusion'):continue
            if second.position==first.position or not _original_intrusion_allowed(reading,second,before,after):continue
            if not any(pos.startswith('動詞,') and form=='命令ｉ' and rd==second.reading
                       for pos,form,base,rd in dictionary_inflections(second.reading) or ()):continue
            if second.reading in seen:continue
            seen.add(second.reading)
            yield ClauseKeyRepair(second.reading,'shift_and_key',first.position,
                first.pressed+second.pressed,first.intended+second.intended,
                first.cost+second.cost,(first,second))


def _original_intrusion_allowed(reading, repair, before='', after=''):
    """Check every dropped key against the original neighbors, including Shift."""
    if repair.operation!='adjacent_intrusion':return True
    import kana_layout as k
    keys=tuple(key for c in reading for key in k.keystrokes(c))
    i=repair.position
    if not 0<=i<len(keys) or keys[i]!=repair.pressed:return False
    adjacent=[keys[j] for j in (i-1,i+1) if 0<=j<len(keys)]
    if i==0 and before:adjacent.append(k.keystrokes(before[-1])[-1])
    if i==len(keys)-1 and after:adjacent.append(k.keystrokes(after[0])[0])
    return (not any(k.same_physical_key(keys[i],other) for other in adjacent)
            and any(0<k._base_distance(keys[i],other)<=1.0 for other in adjacent))


def _search_step(kind, limit):
    """A lazy grammar search records a cutoff without exhausting its iterator."""
    search=_SEARCH.get()
    if search is None:return True
    count=search.setdefault(kind,dict(limit=limit,observed=0,examined=0,unexplored=False))
    count['observed']+=1
    if count['examined']>=limit:
        count['unexplored']=True
        return False
    count['examined']+=1
    return True


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


def validate(target, surface, engine, tokenize, store, dictionary, decisions=None,
             expected_reading=None, companions=()):
    """同じ原文範囲への候補。直接再構築・通常置換のいずれからも呼ぶ。"""
    import oddness
    if not surface or surface == target.text:
        return False, 'unchanged'
    # 辞書にある動作名詞は、その直後の誤打だけで接続を戻せる候補を先に
    # 調べる。無ければ語本体を読む別範囲へ進み、そこで全候補を順位付けする。
    if target.spelling and surface!=target.spelling[0].normal:
        return False, 'spelling_stem_changed'
    if target.preserved_head and not surface.startswith(target.preserved_head):
        return False, 'known_action_changed'
    accepted, reason = engine._check_replacement(target.source,
        (target.start, target.end, surface, 'かな入力'), store, tokenize, dictionary, decisions,
        conv_taken=((target.start, target.end),))
    if accepted is None:
        return False, reason
    if tuple(accepted[:2]) != (target.start, target.end):
        return False, 'changed_source_boundary'
    local_start = target.start-target.context_start
    siblings = [(a-target.context_start, b-target.context_start, text)
                for a, b, text in companions
                if target.context_start <= a <= b <= target.context_end
                and not _overlaps(a, b, target.start, target.end)]
    changed = _apply(target.context, siblings+[(local_start, target.end-target.context_start, surface)])
    local_start += sum(len(text)-(b-a) for a, b, text in siblings if b <= local_start)
    local_end = local_start+len(surface)
    # 表記を差し替えても、隣の助詞・活用との接続を必ず同じ文脈で検査する。
    if oddness.structural_anomaly_in_range(changed,local_start,local_end,
                                          tokenize,store,dictionary):
        return False, 'context_still_anomalous'
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
        from particle_frames import interrupted_topic_frames, drop_candidate
        for frame in interrupted_topic_frames(target.context,dictionary):
            if (frame['start']==target.start-target.context_start
                    and frame['end']==target.end-target.context_start
                    and (expected_reading is None or expected_reading==frame['head_reading']+frame['case']+frame['topic'])
                    and (drop_candidate(target.context,frame) or {}).get('surface')==surface):
                return True,'native_particle_connection'
        return False,'unproven_particle_connection'
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
    if target.boundary_kind=='kana_request' and expected_reading is not None:
        from reading_segments import _native_request_tail
        if (surface!=expected_reading or not _is_reading(surface)
                or not _native_request_tail(list(tokenize(surface)))):
            return False,'unproven_native_request'
    from reading_segments import native_object_predicate_contexts
    source_frames=[(start,cut,faces) for start,cut,faces in native_object_predicate_contexts(target.context)
                   if cut<=target.start-target.context_start and target.end<=target.context_end]
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
            if actual!=expected_reading:return False,'predicate_reading'
        completed=native_object_predicate_proof(changed_predicate_context,local_cut,source_faces)
        if not completed:
            retained=_unchanged_finite_connective(source_predicate_context,changed_predicate_context)
            bare=changed_predicate_context[:-1] if changed_predicate_context[-1:] in '。！？.!?' else changed_predicate_context
            if retained and bare.endswith(retained):
                completed=native_object_predicate_proof(bare[:-len(retained)],local_cut,source_faces)
        if not completed:return False,'unproven_object_predicate'
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
    parts = list(tokenize(surface))
    if not parts or not all(t[5] for t in parts):
        return False, 'unreadable_candidate'
    lexical_parts = parts
    lexical_tail = parts[-1]
    # 機能語を欠いたまま別の品詞を置かない。格助詞を受ける名詞句と、
    # 接続助詞を受ける連用形を、表記の頻度より先に検査する。
    in_context = list(tokenize(changed))
    inserted = [t for t in in_context if t[3] < local_end and local_start < t[4]]
    if expected_reading is not None:
        if (not inserted or inserted[0][3] != local_start or inserted[-1][4] != local_end
                or ''.join(t[2] for t in inserted) != expected_reading):
            # The same fully proved nominal boundary can be swallowed by
            # an unknown best-parse token. Keep literal kana and require
            # the exact head, unchanged case and both original predicates.
            from reading_segments import native_modified_nominal_contexts
            if not (surface==expected_reading and _is_reading(surface)
                    and any(head==local_start and case==local_end
                        for begin,head,case,finish,faces in native_modified_nominal_contexts(changed))):
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
            and source_parts and source_parts[-1][1].startswith('助動詞')
            and _completed_predicate_token(source_parts[-1])):
        if not parts or not _completed_predicate_token(parts[-1]):
            return False,'incomplete_repaired_predicate'
    original_pairs={(a[0],b[0]) for a,b in zip(source_parts,source_parts[1:])}
    for a,b in zip(lexical_parts,lexical_parts[1:]):
        if (b[0]=='まい' and b[1].startswith('助動詞')
                and _native_mai_connection(a[0],a[2],a[1].split(':')[0]) is False):
            return False,'negative_volition_inflection'
        if ((a[0],b[0]) not in original_pairs and (oddness.aspect_auxiliary_needs_te(a,b)
                or oddness.excess_aux_mismatch(a,b))):
            return False,'aspect_auxiliary_slot'
        link=_modern_euphonic_link(b[0],b[1],b[6])
        if (a[1].startswith('動詞') and link is not None
                and (a[0],b[0]) not in original_pairs
                and _modern_te_allowed(a[0],a[2],link) is False):
            return False,'euphonic_auxiliary_slot'
    if (not target.following and source_parts and all(t[1].startswith('名詞') for t in source_parts)
            and not parts[-1][1].startswith('名詞')):
        return False, 'nominal_phrase'
    if following:
        first = following[0]
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
            if not quoted_predicate:
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


def _surfaces(reading, store, dictionary, compose=False, following="", before="", preserved_bases=()):
    # 本人語彙には同梱の初期語彙も含まれる。索引から落ちた普通の語を
    # 捨てない一方、使用回数や最終使用時刻は順位に使わない。
    # 48-AIE: an attested ordinary noun may be absent from the broad
    # index (especially a single kanji). Share the exact native noun/usage
    # evidence already used to retain sources; do not add an answer roster.
    from reading_segments import _native_nominal_reading_faces
    return list(dict.fromkeys(
        _bounded(dictionary.surfaces_for_reading(reading, limit=13, band=True),12,'dictionary_surfaces')
        + list(_native_nominal_reading_faces(reading))
        + [entry['surface'] for entry in store.lookup(reading) if entry.get('surface')]
        + list(dictionary.inflected_surfaces_for_reading(reading))
        + (_composed_surfaces(reading,store,dictionary,following,before,preserved_bases) if compose else [])))



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
                            '終える','おえる','終わる','おわる','直す','なおす'))


def _native_phase_attachment(previous, following):
    return bool(previous.has_reading and following.has_reading
        and previous.end==following.start and previous.pos==following.pos=='動詞'
        and previous.infl_form=='連用形' and following.base_form in _PHASE_VERB_BASES)


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


def _allows_grammatical_tail(forms, tail, head_reading=None, head_surface=None):
    """辞書の活用形と既存の文法による接続。生成と順位で共有する。"""
    from morphology import dictionary_inflections
    from pos_grammar import continuation_state
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
        elif pos.startswith('形容詞,') and form=='ガル接続':
            # 48-AGQ: exact native adjective stems use the existing
            # adjective grammar, including the ichidan tail of excess.
            # A whole basic adjective cannot borrow this stem form.
            if _grammatical_suffix(tail,'IST'):return True
        elif pos.startswith('名詞,サ変接続,'):
            for n in range(1,min(3,len(tail))+1):
                for tp,tf,tb,tr in dictionary_inflections(tail[:n]) or ():
                    state=continuation_state(tf)
                    if not (_sahen_verb_form(tp,tb,tail[:n],tf,tr) and tr==tail[:n]):continue
                    if tail[n:].startswith('まい'):
                        if _native_mai_connection(tail[:n],tr,tp.split(',')[0]) is not True:continue
                        if state is None:state='END'
                    if state and _grammatical_suffix(tail[n:],state):return True
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
    if any(oddness.finite_copula_aux_mismatch(a,b) for a,b in zip(legacy,legacy[1:])):
        return False
    if _native_focused_te_predicate(surface,head,before=before):return True
    if _native_manner_predicate(surface,head,before=before):return True
    if _native_negative_degree_predicate(surface,head):return True
    if (not parts or not all(t.has_reading for t in parts)
            or parts[0].start!=len(before) or parts[-1].end!=len(before)+len(surface)
            or ''.join(t.surface for t in parts)!=surface or parts[0].surface!=head):
        return False
    # 48-ACS: candidate completion shares the native attachment checks
    # used for the source. Functional POS coverage alone accepts しせます.
    if any(oddness.aspect_auxiliary_needs_te(a,b) or oddness.excess_aux_mismatch(a,b) or oddness.mai_aux_mismatch(a,b)
           or oddness.causative_aux_mismatch(a,b) or oddness.passive_aux_mismatch(a,b)
           or oddness.polite_aux_mismatch(a,b) or oddness.completed_tsu_aux_mismatch(a,b)
           or oddness.past_auxiliary_mismatch(a,b) or oddness.volitional_auxiliary_mismatch(a,b)
           for a,b in zip(legacy,legacy[1:])):
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
    for a,b in zip(parts,parts[1:]):
        if (b.pos=='動詞' and b.pos_sub.startswith('非自立')
                and b.base_form in (_CONTINUATIVE_BOUND_VERBS | _PHASE_VERB_BASES)
                and (a.pos!='動詞' or a.infl_form!='連用形')):
            return False
        link=_modern_euphonic_link(b.surface,b.pos+(':'+b.pos_sub if b.pos_sub else ''),b.infl_form)
        if (a.pos=='動詞' and link is not None
                and _modern_te_allowed(a.surface,a.reading,link) is False):
            return False
    for i,t in enumerate(parts[1:],1):
        if t.pos=='助動詞' or (t.pos=='助詞' and t.pos_sub.startswith('接続助詞')):
            continue
        if t.pos=='動詞' and (t.pos_sub.startswith(('非自立','接尾'))
                               or _native_phase_attachment(parts[i-1],t)):
            continue
        if (t.pos=='動詞' and parts[i-1].pos=='助詞'
                and parts[i-1].pos_sub=='接続助詞' and parts[i-1].surface in ('て','で')):
            from morphology import native_potential_auxiliary
            if native_potential_auxiliary(t.surface,t.infl_form,t.reading):continue
        if (t.pos=='助詞' and '終助詞' in t.pos_sub
                and all(q.pos=='助詞' and '終助詞' in q.pos_sub for q in parts[i:])):
            from morphology import dictionary_inflections
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
        if (i==1 and parts[0].pos=='名詞' and parts[0].pos_sub.startswith('サ変接続')
                and _sahen_verb_form(t.pos+','+t.pos_sub.replace(':',','),t.base_form,t.surface,t.infl_form,t.reading)):
            continue
        return False
    return True


def _composed_surfaces(reading,store,dictionary,following="",before="",preserved_bases=()):
    """原文の異様な接続を含む範囲で、語と文法的な語尾を組み合わせる。"""
    from morphology import dictionary_inflections
    out=[]
    for cut in range(2,len(reading)):
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


def context_material(target, tokenize):
    """対象に近い内容語から渡す。得点関数の距離減衰と順序を一致させる。"""
    start = target.start-target.context_start
    end = target.end-target.context_start
    parts = [t for t in tokenize(target.context)
             if (t[4] <= start or t[3] >= end)
             and t[1].startswith(('名詞', '動詞', '形容詞')) and len(t[0]) > 1]
    parts.sort(key=lambda t: (start-t[4] if t[4] <= start else t[3]-end, t[3]))
    return tuple(t[0] for t in parts)


def _source_preserved_verb_bases(target, tokenize):
    """Preserve native predicate lemmas at a proved malformed attachment."""
    from morphology import dictionary_inflections
    import oddness
    # Every overlapping candidate observes the same original polite attachment.
    parts=list(tokenize(target.context))
    bases=set()
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
            forms=tuple(row for row in dictionary_inflections(a[0]) or ()
                        if row[0].startswith('動詞,') and row[1]==a[6] and row[3]==a[2])
            if not _allows_grammatical_tail(forms,b[0],a[2],a[0]):continue
            evidence=candidate_evidence(obj,a[0],b[0])
            if evidence and evidence['shared_roles']:
                bases.update(('surface',base) for pos,form,base,rd in forms)
    return frozenset(bases)


def _candidate_verb_bases(surface, tokenize):
    from morphology import dictionary_inflections
    from inflected_lexicon import dictionary_readings
    bases=set()
    for t in tokenize(surface):
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
    return any(t[5] and target.start-target.context_start<=t[3]<=target.end-target.context_start
        and ((t[1]=='助動詞' and any(pos.startswith('助動詞,') and rd==t[2] and form==t[6]
              for pos,form,base,rd in dictionary_inflections(t[0]) or ()))
             or (t[0] in ('て','で') and t[1].startswith('助詞:接続助詞')
                 and any(pos.startswith('助詞,接続助詞,') and rd==t[2]
                         for pos,form,base,rd in dictionary_inflections(t[0]) or ())))
        for t in parts)


def rank_candidates(rows):
    """SR-D total order, with group-wide treatment of optional numeric gaps.

    Intact-source protection and native base preservation precede ranking.
    Do not additionally reward the exact inflected token strings from an
    already anomalous parse: that would favor おくまい over おきます just
    for keeping おく from the malformed おくます.
    """
    rows=list(rows)
    optional=('context','cost','parse_cost','continuation')
    available={key for key in optional if all(row['rank_evidence'].get(key) is not None
                                               for row in rows)}
    for row in rows:
        e=row['rank_evidence'];op=row['repair']
        row['rank']=(e['direct'],e['added'],e['meaning'],e['edits'],e['physical'],
            e['bases'],e['script'],e['proper'],e['terminal'],
            e['guesses'],e['usage'])+tuple(e[key] for key in optional if key in available)+( 
            e['start'],e['end'],op['reading'],row['surface'],
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
def resolve(target, engine, tokenize, store, dictionary, decisions=None, legacy_surface=None):
    """同じ文脈で成立した全候補を比較し、最優先の一つと診断を返す。"""
    from ngram_yomi import continuation_cost
    from reading_likelihood import edit_cost, adjacent_readings, evidence
    collect_reading_diagnostic = (engine.TRACE is not None
        or getattr(engine._trace, '_diagnostic_observer', None) is not None)
    from morphology import path_cost
    from semantic_roles import object_before, candidate_evidence as role_evidence, candidate_object_evidence
    from semantic_roles import subject_before, subject_candidate_evidence, modifier_candidate_evidence
    diagnostic = dict(start=target.start, end=target.end, text=target.text,
                      boundary_kind=target.boundary_kind, preserved_head=target.preserved_head,
                      context_start=target.context_start, context_end=target.context_end,
                      anomalies=target.anomalies, structural=target.structural,
                      readings=[], candidates=[], rejected={})
    if engine._chunk_is_intact(target.text, tokenize, repair_context=target):
        diagnostic['status'] = 'intact'
        return None, diagnostic
    readings = reading_evidence(target, tokenize, dictionary)
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
    compose = target.structural or target.boundary_kind=='auxiliary_connection'
    preserve_kana=_is_input_reading(target.text) and _source_predicate_context(target,tokenize)
    grammar_rank = (target.boundary_kind=='auxiliary_connection'
                    or _kana_grammar_boundary(list(tokenize(target.text)),0,len(target.text)))
    complete_verbs = _source_preserved_verb_bases(target,tokenize)
    # 他の列や正解の見本を材料にしない。この対象を除いた同じ文の内容語。
    material = context_material(target, tokenize)
    object_word=object_before(target.context,target.start-target.context_start,tokenize)
    object_frame=(_source_object_predicate_frame(target.source,target.start,target.end)
                  if not object_word else None)
    proved_objects=object_frame[-1] if object_frame else ()
    subject_word=subject_before(target.context,target.start-target.context_start,tokenize)
    from semantic_roles import case_argument_before
    case_argument=case_argument_before(target.context,target.start-target.context_start,tokenize)
    semantic = _seed_context()
    legacy_parts = list(tokenize(legacy_surface)) if legacy_surface else []
    legacy_reading = (''.join(t[2] for t in legacy_parts)
                      if legacy_parts and all(t[5] for t in legacy_parts) else None)
    particle_pair=None;particle_surface=None
    if target.boundary_kind=='particle_intrusion':
        from particle_frames import interrupted_topic_frames, drop_candidate
        local_start=target.start-target.context_start
        for frame in interrupted_topic_frames(target.context,dictionary):
            if frame['start']==local_start and frame['end']==target.end-target.context_start:
                candidate=drop_candidate(target.context,frame)
                if candidate is not None:
                    particle_pair=frame['head_reading']+frame['case']+frame['topic']
                    particle_surface=candidate['surface']
    def repair_options():
        if target.boundary_kind=='particle_intrusion':
            for reading in readings:
                for repair in key_repairs(reading.text,*surrounding_readings):
                    if repair.operation=='adjacent_intrusion' and repair.reading==particle_pair:
                        yield reading,repair
            return
        for reading in readings:
            for repair in key_repairs(reading.text,*surrounding_readings):
                yield reading,repair
        if not candidates:
            for reading in readings:
                for repair in request_shift_key_repairs(target,reading.text,*surrounding_readings):
                    yield reading,repair
        if not candidates:
            for reading in readings:
                for repair in clause_key_repairs(target,reading.text,*surrounding_readings):
                    yield reading,repair
    for reading,repair in repair_options():
        question_surface=None
        if target.boundary_kind=='question_particle':
            from particle_frames import closed_question_frames,closed_question_particle
            if repair.operation!='adjacent_intrusion':continue
            for frame in closed_question_frames(target.source):
                if frame['start']==target.start and frame['end']==target.end:
                    question_surface=closed_question_particle(target.source,frame,repair.reading)
            if not question_surface:continue
        if target.boundary_kind=='kana_request':
            from morphology import dictionary_inflections
            from reading_segments import _native_request_tail
            # Exact inflection lookup avoids parsing every non-word key variant.
            if not any(pos.startswith('動詞,') and form=='命令ｉ' and rd==repair.reading
                       for pos,form,base,rd in dictionary_inflections(repair.reading) or ()):continue
            if not _native_request_tail(list(tokenize(repair.reading))):continue
        if target.spelling:
            fact=target.spelling[0]
            if repair.reading!=fact.reading or repair.operation!='shift':
                continue
        surfaces = ([question_surface] if target.boundary_kind=='question_particle' else
                    [particle_surface] if target.boundary_kind=='particle_intrusion' else
                    [target.spelling[0].normal] if target.spelling else
                    [repair.reading] if target.boundary_kind in ('kana_action_note','kana_predicate','kana_request','particle_adverbial') 
                    else _surfaces(repair.reading,store,dictionary,compose=compose,
                        following=target.following,before=target.context[:target.start-target.context_start],
                        preserved_bases=complete_verbs))
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
        # 既存経路の先頭候補も、同じ読みに同じ一手で届くなら同列で比較。
        # 新設の経路であること自体を、優先する理由にしない。
        if not target.spelling and legacy_reading == repair.reading and target.boundary_kind not in ('kana_action_note','particle_intrusion','kana_request'):
            surfaces.append(legacy_surface)
        for surface in dict.fromkeys(surfaces):
            valid, reason = validate(target, surface, engine, tokenize, store, dictionary, decisions, repair.reading)
            if not valid:
                diagnostic['rejected'][reason] = diagnostic['rejected'].get(reason, 0)+1
                continue
            # IME情報を先にし、物理操作、元の文字種、文脈、一般性を比較。
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
            cost = engine._table_cost(score_head)
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
            local_prediction = (edit_cost(reading.text, repair.reading, *surrounding_readings)
                                if collect_reading_diagnostic else None)
            argument_evidence=(role_evidence(object_word,surface,target.following,
                before=target.context[:target.start-target.context_start]) if object_word else None)
            if not argument_evidence and proved_objects:
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
            argument_fit=bool(argument_evidence and argument_evidence['shared_roles'])
            subject_evidence=subject_candidate_evidence(subject_word,surface,target.following) if subject_word else None
            subject_fit=bool(subject_evidence and subject_evidence['shared_roles'])
            modifier_evidence=modifier_candidate_evidence(target.context,
                target.start-target.context_start,surface,tokenize)
            modifier_fit=bool(modifier_evidence and modifier_evidence['shared_roles'])
            object_candidate_evidence=candidate_object_evidence(surface,target.following,
                before=target.context[:target.start-target.context_start])
            object_candidate_fit=bool(object_candidate_evidence and object_candidate_evidence['shared_roles'])
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
            rank_evidence=dict(
                direct=_reading_strength(reading)[0],
                added=max(0,len(repair.intended)-len(repair.pressed)),
                meaning=-int(argument_fit or subject_fit or modifier_fit or object_candidate_fit),
                edits=len(getattr(repair,'steps',())) or int(repair.operation!='same_reading'),physical=repair.cost,
                bases=len(complete_verbs-candidate_bases),
                script=int((any('ァ'<=c<='ヶ' for c in target.text)
                            and not any('ァ'<=c<='ヶ' for c in surface))
                           or (preserve_kana and not _is_reading(surface))),
                proper=int(engine._is_whole_proper_noun(surface,tokenize)),
                terminal=int(_terminal_auxiliary_fragment(surface,target.following,tokenize))
                         if grammar_rank else 0,
                guesses=sum(segment[3] in ('character_guess','unrecognized_ime_sequence')
                            for segment in reading.segments),
                usage=engine._kango_tier_of(score_head),
                context=-semantic.context_score(score_head,material),
                cost=cost,continuation=continuation,parse_cost=context_cost,
                start=target.start,end=target.end)
            rank=()
            row = dict(surface=surface, rank=rank, rank_evidence=rank_evidence, score_head=score_head, local_prediction=local_prediction,
                       object_word=object_word, argument_fit=argument_fit, argument_evidence=argument_evidence,
                       subject_word=subject_word, subject_fit=subject_fit, subject_evidence=subject_evidence,
                       modifier_evidence=modifier_evidence,modifier_fit=modifier_fit,
                       object_candidate_evidence=object_candidate_evidence,object_candidate_fit=object_candidate_fit,
                       reading=asdict(reading), repair=asdict(repair),
                       also_from_legacy=surface == legacy_surface)
            candidates.append(row)
    ordered = rank_candidates(candidates)
    diagnostic['candidates'] = ordered
    diagnostic['status'] = 'selected' if ordered else 'no_candidate'
    return (ordered[0]['surface'] if ordered else None), diagnostic


def _overlaps(a, b, start, end):
    return start <= a <= end if a == b else a < end and start < b


def _repair_coverage(target):
    """同じ異様な接続の両側は、独立した二つの編集として合成しない。"""
    return (min([target.start]+[s for _,_,s,e in target.anomalies]),
            max([target.end]+[e for _,_,s,e in target.anomalies]))


def _retain_independent_changes(old_changes, selected, targets):
    coverages=[_repair_coverage(t) for t in targets
               if any((t.start,t.end)==(a,b) for a,b,_ in selected)]
    # The unchanged native object/case is already positive source evidence.
    # Keep it when no predicate candidate survives too: its mere kanji
    # conversion cannot resolve (or hide) the following grammar anomaly.
    coverages.extend((t.context_start,t.start) for t in targets
                     if t.boundary_kind=='kana_predicate')
    return [change for change in old_changes if not any(
        _overlaps(change[0],change[1],a,b) for a,b in coverages)]


def _apply(source, changes):
    out = []; cursor = 0
    for a, b, surface in sorted(changes):
        if a < cursor:
            raise ValueError('overlapping source edits')
        out.extend((source[cursor:a], surface)); cursor = b
    out.append(source[cursor:])
    return ''.join(out)


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
                                     decisions, row['repair']['reading'], companions)
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
                                    decisions, candidate['repair']['reading'], companions)
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
        spans.update((a,b) for _,_,a,b in target.anomalies)
    atoms={span for span in spans if not any(span!=other and span[0]<=other[0]
                                           and other[1]<=span[1] for other in spans)}
    for target,diagnostic in zip(targets,diagnostics):
        facts=tuple(sorted(atom for atom in atoms if any(a<=atom[0] and atom[1]<=b
                              for _,_,a,b in target.anomalies)))
        if not facts:continue
        for row in diagnostic.get('candidates',()):
            options.append(dict(start=target.start,end=target.end,surface=row['surface'],
                rank=row['rank'],anomalies=facts,context=(target.context_start,target.context_end),
                target=target,candidate=row,diagnostic=diagnostic))
    selected=[];reports=[]
    for group in groups(options):
        rank_candidates([option['candidate'] for option in group])
        for option in group:option['rank']=option['candidate']['rank']
        def valid(rows):
            changes=[(row['start'],row['end'],row['surface']) for row in rows]
            companions=_retain_independent_changes(old_changes,changes,targets)
            for row,change in zip(rows,changes):
                ok,_=validate(row['target'],row['surface'],engine,tokenize,store,dictionary,
                    decisions,row['candidate']['repair']['reading'],
                    companions+[other for other in changes if other is not change])
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


def _legacy_resolves_anomaly(target, changes, engine, tokenize, store, dictionary, decisions):
    """語本体を保ったまま、同じ原文の異様が隣の修正で解消したか。

    異様の範囲は語尾の接続まで含むが、読む範囲は語本体だけの場合がある。
    その語尾が既に直っていれば、元から正しい語まで重ねて変えない。
    既存出力を無条件には信用せず、広い元の範囲を同じ検算に通す。
    """
    if not target.anomalies or any(_overlaps(a,b,target.start,target.end) for a,b,_ in changes):
        return False
    start=min([target.start]+[a for _,_,a,b in target.anomalies])
    end=max([target.end]+[b for _,_,a,b in target.anomalies])
    relevant=[c for c in changes if _overlaps(c[0],c[1],start,end)]
    if not relevant or not all(start<=a<=b<=end for a,b,_ in relevant):
        return False
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
        covered=[t for t in targets if start<=t.start and t.end<=end
                 and (start<t.start or t.end<end)
                 and t.context_start<=start<end<=t.context_end]
        if not covered or any((t.spelling or t.preserved_head) and _overlaps(start,end,t.start,t.end)
                              for t in targets):continue
        contexts={(t.context_start,t.context_end) for t in covered}
        if len(contexts)!=1:continue
        facts=tuple(dict.fromkeys(f for t in covered for f in t.anomalies))
        if not facts:continue
        target=replace(covered[0],start=start,end=end,anomalies=facts,
            structural=any(t.structural for t in covered),boundary_kind='lexical',
            following=covered[0].source[end:covered[0].context_end])
        if target not in out:out.append(target)
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
        targets = targets_for_line(line, tokenize, store, dictionary)
        if method!='kana' or dictionary is None:
            targets=[t for t in targets if t.spelling]
        if not targets:
            return fn(line, *args, **kwargs)
        legacy = fn(line, *args, **kwargs)
        if legacy.get('analysis_status')=='incomplete':return legacy
        old = legacy.get('corrected', line)
        old_changes = [(a, b, old[c:d]) for a, b, c, d in engine._diff_spans(line, old)]
        targets=_legacy_covering_targets(targets,old_changes)
        selected = []; diagnostics = []
        for target in targets:
            if _legacy_resolves_anomaly(target,old_changes,engine,tokenize,store,dictionary,decisions):
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
            surface, diagnostic = resolve(target, engine, tokenize, store, dictionary, decisions, legacy_surface)
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
        provenance={}
        selected,joint_reports=_choose_joint_candidates(targets,diagnostics,old_changes,engine,
            tokenize,store,dictionary,decisions,provenance)
        # 語本体を直す新候補へ、同じ接続の語尾を直す旧候補を重ねない。
        # どちらも単独では成立しても、合成すると別の文になるため。
        retained = _retain_independent_changes(old_changes, selected, targets)
        # 新しい候補がない場合も、古い経路が部分だけを直して不整合を残すのを防ぐ。
        for target in targets:
            # A request-word fallback owns only a request it actually supplies.
            # Its absent candidate cannot revoke an independent lexical repair.
            if target.boundary_kind in ('kana_request','question_particle'):continue
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
        stale_mark=any(_overlaps(a,b,x,y) for a,b in result.get('odd_spans',())
                       for x,y in resolved_ranges)
        if corrected == old and not stale_mark:
            return result
        original_spans = []; spans = []; details = []
        display_changes=list(engine._diff_spans(line, corrected))
        # Deletions and multi-part request repairs need one nonempty rejection
        # pair. Keep the proved original frame so menu actions stop the actual
        # candidate, rather than trying to record an empty character deletion.
        for a,b,surface in selected:
            owner=provenance.get((a,b,surface))
            if not owner:continue
            kind=owner[0].boundary_kind
            request=(kind=='kana_request')
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
        unsure = [span for span in result.get('unsure_spans', []) if not any(
                  _overlaps(span[0], span[1], a, b) for a, b in original_spans)]
        result.update(original=line, corrected=corrected, changed=corrected != line,
                      details=details, original_spans=original_spans, spans=spans,
                      odd_spans=odd, odd_reasons=reasons, unsure_spans=unsure)
        result.pop('diagnosis', None)
        return result
    return wrapped
