# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""Reuse only still-live completed Quick rows. No text history or disk cache."""
from copy import deepcopy
from tab_context import tab_has_kana


def _continues(previous,line):
    # 1行上で答えが変わるのは、行頭の付属語が前の行から続く時だけ（correction_entry の previous_line）
    from correction_entry import _continuation_prefix
    return _continuation_prefix(previous,line)


def _kana_matters(task,index):
    # 文書にかながあるかで変わるのは、半角のまま打った部分の補正だけ（tab_context）。その字の無い行は見ない
    if not any(ord(c)<0x100 or 0xFF61<=ord(c)<=0xFF9F for c in task['lines'][index]):return None
    return any(tab_has_kana(line) for line in task['lines'])


def row_key(task,index):
    # メモ欄と同じ入口は、1行上の行と文書にかながあるかも見る
    return (task['lines'][index],_continues(task['lines'][index-1],task['lines'][index]) if index else None,
            _kana_matters(task,index),
            task['input_method'],task.get('keyboard'),
            tuple(task.get('readings',{}).get(index,())),
            tuple(task.get('calculations',{}).get(index,())))


def completed_row(value,line):
    return (isinstance(value,dict) and value.get('original')==line
            and value.get('analysis_status')=='complete'
            and not value.get('pending') and not value.get('analysis_error')
            and not value.get('deferred_stages'))     # 重い段を後回しにした答えは本当の答えではない


def remember(app,scope,task,value):
    """Keep one current displayed result set, before automatic text projection."""
    rows={}
    for i,(result,units,corrected) in enumerate(zip(
            value['results'],value['units'],value['corrected_units'])):
        if i<len(task['lines']) and completed_row(result,task['lines'][i]):
            rows[i]=(row_key(task,i),deepcopy((result,units,corrected)))
    app._quick_row_reuse=(scope.owner,scope.dependencies,
                         frozenset(task.get('attested',())),rows)


def select(app,scope,task):
    kept=getattr(app,'_quick_row_reuse',None)
    if not kept:return {}
    owner,dependencies,attested,rows=kept
    if (owner is not scope.owner or dependencies!=scope.dependencies
            or attested!=frozenset(task.get('attested',()))):
        app._quick_row_reuse=None
        return {}
    return {i:deepcopy(entry) for i,entry in rows.items()
            if i<len(task['lines']) and entry[0]==row_key(task,i)}


def invalidate(app,before,after,discard=False,edit=None):
    """Drop changed rows on every edit, including an A→B→A before dispatch."""
    kept=getattr(app,'_quick_row_reuse',None)
    if not kept:return
    if discard or before==after:
        app._quick_row_reuse=None
        return
    if edit is not None:
        lo,old=edit;new=old+len(after)-len(before)
        if not (0<=lo<=old<=len(before) and lo<=new<=len(after)
                and before[:lo]==after[:lo] and before[old:]==after[new:]):
            app._quick_row_reuse=None
            return
    else:
        lo=0
        while lo<min(len(before),len(after)) and before[lo]==after[lo]:lo+=1
        old,new=len(before),len(after)
        while old>lo and new>lo and before[old-1]==after[new-1]:old-=1;new-=1
    first=before.count('\n',0,lo)
    old_last=before.count('\n',0,old);new_last=after.count('\n',0,new)
    rows=kept[3]
    # Row-number shifts need no alignment guesses. Recompute from this row;
    # an edit without added/deleted newlines keeps the other exact row slots.
    for row in tuple(rows):
        if first<=row and (old_last!=new_last or row<=old_last):rows.pop(row)


def restored(task,index):
    entry=task.get('reuse',{}).get(index)
    if not entry or len(entry)!=2 or entry[0]!=row_key(task,index):return None
    values=entry[1]
    if len(values)!=3 or not completed_row(values[0],task['lines'][index]):return None
    return values
