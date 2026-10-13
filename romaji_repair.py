# -*- coding: utf-8 -*-
"""One observed-key repair after an independent source-reading anomaly."""
from contextvars import ContextVar
from dataclasses import dataclass
import re

_DIAGNOSTICS=ContextVar('correctnote_romaji_repair_diagnostics',default=None)
# Pure complete enumerations live only in the current correction request.
_READINGS=ContextVar('correctnote_romaji_key_readings',default=None)

@dataclass(frozen=True)
class ReadingSearch:
    state:str
    examined:int
    candidates:tuple


def one_key_readings(typed,*,state_limit=4096,input_limit=96):
    from halfwidth import ROMAJI_TO_KANA,romaji_to_kana
    from corrector import (_qwerty_adjacent,_qwerty_intrusion_adjacent,
                           _ROM_SUB_NEAR,_ROM_GAP,_ROM_SWAP)
    from analysis_context import check_current_request
    check_current_request()
    if len(typed)>input_limit:return ReadingSearch('input_limit',0,())
    if not re.fullmatch('[a-z-]+',typed):return ReadingSearch('not_applicable',0,())
    pool=_READINGS.get();cache_key=(typed,state_limit,input_limit)
    if pool is not None and cache_key in pool:
        check_current_request(frequent=True)
        return pool[cache_key]
    alphabet=tuple(sorted(set(''.join(ROMAJI_TO_KANA))))
    original=romaji_to_kana(typed)[0];seen=set();readings={};examined=0
    def attempts():
        for i,ch in enumerate(typed):
            for other in alphabet:
                if other!=ch and _qwerty_adjacent(ch,other):
                    yield typed[:i]+other+typed[i+1:],_ROM_SUB_NEAR,('adjacent_substitution',i,ch,other)
            neighbors=typed[max(0,i-1):i]+typed[i+1:i+2]
            if ch not in neighbors and any(_qwerty_intrusion_adjacent(ch,n) for n in neighbors):
                yield typed[:i]+typed[i+1:],_ROM_GAP,('adjacent_intrusion',i,ch,'')
            if i+1<len(typed) and ch!=typed[i+1]:
                yield typed[:i]+typed[i+1]+ch+typed[i+2:],_ROM_SWAP,('transposition',i,typed[i:i+2],typed[i+1]+ch)
        for i in range(len(typed)+1):
            for ch in alphabet:
                yield typed[:i]+ch+typed[i:],_ROM_GAP,('missing_key',i,'',ch)
    def rows():
        return tuple(sorted(readings.values(),key=lambda row:(row[3][0]=='missing_key',row[1],row[0])))
    for changed,cost,operation in attempts():
        if changed in seen:continue
        if examined>=state_limit:return ReadingSearch('state_limit',examined,rows())
        examined+=1;seen.add(changed)
        if examined%64==0:check_current_request(frequent=True)
        reading,_,_=romaji_to_kana(changed)
        if (reading==original or len(reading)<4
                or not all('ぁ'<=ch<='ゖ' or ch=='ー' for ch in reading)):continue
        row=(reading,cost,changed,operation)
        prior=readings.get(reading)
        key=lambda value:(value[3][0]=='missing_key',value[1])
        if prior is None or key(row)<key(prior):readings[reading]=row
    result=ReadingSearch('complete',examined,rows())
    check_current_request()
    if pool is not None:
        # Keep bounded transient work, never a cross-request text history.
        if len(pool)>=8:pool.pop(next(iter(pool)))
        pool[cache_key]=result
    return result


def _whole_field(line,start,end):
    lo,hi=0,len(line)
    for boundary in re.finditer('[\t\r\n⇒→。！？]',line):
        if boundary.end()<=start:lo=boundary.end()
        elif boundary.start()>=end:hi=boundary.start();break
        else:return False
    raw=line[lo:hi];typed=line[start:end]
    if raw.strip()==typed:return True
    # Detached symbol runs are established source separators. Remove only
    # those separators from this equality test; every ordinary character,
    # ASCII connector and the untouched original coordinates remain owned.
    from morphology import detached_symbol_separators
    pieces=[];edge=0
    for a,b in detached_symbol_separators(raw):
        pieces.extend((raw[edge:max(edge,a)],' '));edge=max(edge,b)
    pieces.append(raw[edge:])
    return ''.join(pieces).strip()==typed


def propose(line,start,end,store,tokenize_fn,judge,accept,max_dist=1.6):
    """Reuse source anomaly, physical policy and unchanged-field completion."""
    import corrector as C
    from halfwidth import romaji_to_kana,_is_dictionary_english,makes_sense_as_japanese
    typed=line[start:end]
    if (C._CORRECTION_INPUT_METHOD.get()!='romaji'
            or not re.fullmatch('[a-z-]{4,}',typed) or not _whole_field(line,start,end)
            or _is_dictionary_english(typed)):return None
    root=C._CORRECTION_SOURCE.get()
    origin=next(((a,b) for source,a,b in C._candidate_source_ranges(line,start,end)
                 if source==root and source[a:b]==typed and _whole_field(source,a,b)),None)
    if origin is None:return None
    reading=romaji_to_kana(typed)[0]
    if (len(reading)<6 or not all('ぁ'<=ch<='ゖ' or ch=='ー' for ch in reading)
            or judge is None or not judge(reading)
            or C._chunk_is_intact(reading,tokenize_fn)):return None
    diagnostics=_DIAGNOSTICS.get()
    item=dict(start=origin[0],end=origin[1],state='pending',examined=0)
    if diagnostics is not None:diagnostics.append(item)
    search=one_key_readings(typed)
    item.update(state=search.state,examined=search.examined,generated=len(search.candidates))
    # Partial enumeration is not a completed set of candidates.
    if search.state!='complete':return None
    from romaji_source import checked_source_keys
    for candidate,cost,keys,operation in search.candidates:
        if cost>max_dist:continue
        if not makes_sense_as_japanese(candidate,store,min_ratio=1.0):continue
        if not checked_source_keys(typed,candidate,source=root,start=origin[0],end=origin[1]).proved:continue
        # Pass the reading, not a prematurely selected spelling. The shared
        # callback completes it in the original field and rechecks raw offsets.
        fixed=accept(candidate)
        if fixed is not None:return fixed
    return None


def finish(result):
    diagnostics=_DIAGNOSTICS.get()
    if not diagnostics:return result
    result=dict(result);odd=list(result.get('odd_spans',()));reasons=list(result.get('odd_reasons',()))
    reports=list(result.get('search_reports',()))
    applied=result.get('original_spans',())
    for item in diagnostics:
        a,b=item['start'],item['end']
        reason=(a,b,'ローマ字をそのまま読んだ語句に、既存の文法・意味の不整合があります')
        if reason not in reasons:reasons.append(reason)
        if not any(x<=a and b<=y for x,y in applied) and (a,b) not in odd:odd.append((a,b))
        if item['state'] in ('state_limit','input_limit'):
            report=dict(start=a,end=b,scope='romaji_key_candidates',state='truncated',
                        reason=item['state'],examined=item['examined'],unexplored=True)
            if report not in reports:reports.append(report)
            if result.get('analysis_status')!='incomplete':
                result.update(analysis_status='limited',stop_reason='search_limit')
    result.update(odd_spans=sorted(odd),odd_reasons=sorted(reasons))
    if reports:result['search_reports']=reports
    return result
