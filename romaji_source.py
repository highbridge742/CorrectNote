# -*- coding: utf-8 -*-
"""Physical evidence from original ASCII keys, using the existing decoder.

This module proves a path; it does not generate vocabulary or choose meanings.
An exhausted state budget is unknown, never a completed negative result.
"""
from cache_limits import size as _cache_size   # 控えの上限は cache_limits で1か所に（2026-10-24）
from dataclasses import dataclass
from functools import lru_cache
import heapq
from contextvars import ContextVar

_LIMITS=ContextVar('correctnote_romaji_source_limits',default=None)


@dataclass(frozen=True)
class KeyEvidence:
    state:str
    proved:bool
    edits:int
    chosen:str
    operations:tuple
    visited:int


@lru_cache(maxsize=_cache_size(2048))
def _feed(pending,chunk,final=False):
    from halfwidth import ROMAJI_TO_KANA,_ROMAJI_KEYS
    pending+=chunk;out=[]
    while pending:
        ch=pending[0]
        if len(pending)==1 and ch.isalpha() and ch not in 'aiueon' and not final:
            break
        if len(pending)>1 and ch==pending[1] and ch.isalpha() and ch not in 'aiueon':
            out.append('っ');pending=pending[1:];continue
        if not final and any(k.startswith(pending) and len(k)>len(pending) for k in _ROMAJI_KEYS):
            break
        key=next((k for k in _ROMAJI_KEYS if pending.startswith(k)),None)
        if key is None:return None
        out.append(ROMAJI_TO_KANA[key]);pending=pending[len(key):]
    return ''.join(out),pending


def source_keys(typed,reading,*,max_edits=3,state_limit=20000,input_limit=128,
                missing_keys=True,duplicate_keys=False):
    """Find a physical path without enumerating all romanizations.

    The state retains original source position, emitted reading position and
    the decoder's pending letters. Intrusions are checked against the original
    adjacent keys, never a neighbor created by an earlier deletion.
    """
    from halfwidth import ROMAJI_TO_KANA,romaji_to_kana
    from corrector import _qwerty_adjacent,_qwerty_intrusion_adjacent
    from analysis_context import check_current_request
    check_current_request()
    if len(typed)>input_limit or len(reading)>input_limit:
        return KeyEvidence('input_limit',False,-1,'',(),0)
    if not typed or not reading or any(c not in 'abcdefghijklmnopqrstuvwxyz-' for c in typed):
        return KeyEvidence('not_applicable',False,-1,'',(),0)
    if any(not ('ぁ'<=c<='ゖ' or c in 'ーヴ') for c in reading):
        return KeyEvidence('not_applicable',False,-1,'',(),0)
    alphabet=tuple(sorted(set(''.join(ROMAJI_TO_KANA))))
    start=(0,0,'');best={start:0};previous={};heap=[(0,start)];visited=0
    def push(state,cost,parent,chunk,operation):
        if cost>max_edits or cost>=best.get(state,max_edits+1):return
        best[state]=cost;previous[state]=(parent,chunk,operation);heapq.heappush(heap,(cost,state))
    def advance(state,consume,chunk,cost,operation):
        i,j,pending=state;got=_feed(pending,chunk)
        if got is None:return
        emitted,wait=got
        if not reading.startswith(emitted,j):return
        push((i+consume,j+len(emitted),wait),cost,state,chunk,operation)
    while heap:
        cost,state=heapq.heappop(heap)
        if cost!=best[state]:continue
        if visited>=state_limit:return KeyEvidence('state_limit',False,-1,'',(),visited)
        visited+=1;i,j,pending=state
        if visited%64==0:check_current_request(frequent=True)
        if i==len(typed):
            got=_feed(pending,'',True)
            if got is not None and reading[j:]==got[0] and not got[1]:
                chunks=[];operations=[];node=state
                while node!=start:
                    node,chunk,operation=previous[node];chunks.append(chunk)
                    if operation is not None:operations.append(operation)
                chosen=''.join(reversed(chunks))
                assert romaji_to_kana(chosen)[0]==reading
                return KeyEvidence('proved',True,cost,chosen,tuple(reversed(operations)),visited)
        if i<len(typed):
            advance(state,1,typed[i],cost,None)
        if cost==max_edits:continue
        if i<len(typed):
            for ch in alphabet:
                if ch!=typed[i] and _qwerty_adjacent(typed[i],ch):
                    advance(state,1,ch,cost+1,('adjacent_substitution',i,typed[i],ch))
            neighbors=typed[max(0,i-1):i]+typed[i+1:i+2]
            duplicate=typed[i] in neighbors
            if duplicate and duplicate_keys:
                push((i+1,j,pending),cost+1,state,'',('duplicate_deletion',i,typed[i],''))
            elif not duplicate and any(_qwerty_intrusion_adjacent(typed[i],n) for n in neighbors):
                push((i+1,j,pending),cost+1,state,'',('adjacent_intrusion',i,typed[i],''))
            if i+1<len(typed) and typed[i]!=typed[i+1]:
                advance(state,2,typed[i+1]+typed[i],cost+1,('transposition',i,typed[i:i+2],typed[i+1]+typed[i]))
        if missing_keys:
            for ch in alphabet:
                advance(state,0,ch,cost+1,('missing_key',i,'',ch))
    return KeyEvidence('complete',False,-1,'',(),visited)


def checked_source_keys(typed,reading,*,source=None,start=0,end=None,**kwargs):
    """Keep unfinished physical searches visible to the outer correction call."""
    from vocabulary import dup_repair_enabled
    evidence=source_keys(typed.lower(),reading,duplicate_keys=dup_repair_enabled(),**kwargs)
    if evidence.state in ('state_limit','input_limit'):
        reports=_LIMITS.get()
        if reports is not None:
            item=(source if source is not None else typed,start,len(typed) if end is None else end,
                  evidence.state,evidence.visited)
            if item not in reports:reports.append(item)
    return evidence


def finish_limits(line,result):
    pending=_LIMITS.get()
    if not pending:return result
    reports=list(result.get('search_reports',()))
    for source,start,end,state,visited in pending:
        # A nested generator may not own full original coordinates. In that
        # case report the containing root row, never a fabricated small span.
        if source!=line:start,end=0,len(line)
        item=dict(start=start,end=end,scope='romaji_source_keys',state='truncated',
                  reason=state,examined=visited,unexplored=True)
        if item not in reports:reports.append(item)
    result=dict(result,search_reports=reports)
    if result.get('analysis_status')!='incomplete':
        result.update(analysis_status='limited',stop_reason='search_limit')
    return result


def candidate_evidence(line,start,end,replacement,tokenize_fn):
    """Recheck a candidate against exactly mapped original ASCII ranges.

    No printed kanji is converted back to invented original keys. The source
    must itself contain the ASCII spelling, possibly in a prior recursion.
    """
    import re
    from corrector import _candidate_source_ranges,_CORRECTION_INPUT_METHOD
    from halfwidth import zenkaku_to_hankaku,romaji_to_kana
    from morphology import katakana_to_hiragana,native_spelling_only
    if _CORRECTION_INPUT_METHOD.get()!='romaji':return None
    reading=None
    for source,a,b in _candidate_source_ranges(line,start,end):
        original=source[a:b];changed=replacement
        left=0
        while left<min(len(original),len(changed)) and original[left]==changed[left]:left+=1
        right=0
        while right<min(len(original)-left,len(changed)-left) and original[-right-1]==changed[-right-1]:right+=1
        typed=zenkaku_to_hankaku(original[left:len(original)-right])
        surface=changed[left:len(changed)-right]
        lo,hi=a+left,b-right
        if not re.fullmatch('[A-Za-z-]{4,}',typed):continue
        # A narrow written edit cannot claim only a fragment of the raw key
        # sequence. The whole source run is the unit of this physical proof.
        if re.match('[A-Za-zＡ-Ｚａ-ｚ-]',source[max(0,lo-1):lo] or '') or re.match('[A-Za-zＡ-Ｚａ-ｚ-]',source[hi:hi+1]):continue
        if not surface or not any('ぁ'<=c<='ゖ' or 'ァ'<=c<='ヺ' or '一'<=c<='鿿' for c in surface):continue
        restored=romaji_to_kana(typed)[0]
        if restored==katakana_to_hiragana(surface) or native_spelling_only(restored,surface):continue
        literal=katakana_to_hiragana(surface)
        if all('ぁ'<=c<='ゖ' or c=='ー' for c in literal):reading=literal
        elif tokenize_fn is not None:
            parts=list(tokenize_fn(surface))
            if not parts or ''.join(t[0] for t in parts)!=surface or not all(t[5] for t in parts):
                return KeyEvidence('reading_unavailable',False,-1,'',(),0)
            reading=''.join(t[2] for t in parts)
        else:return KeyEvidence('reading_unavailable',False,-1,'',(),0)
        evidence=checked_source_keys(typed,reading,source=source,start=lo,end=hi)
        if not evidence.proved:return evidence
    return None
