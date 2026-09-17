# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""SR-D: deterministic, finite comparison of jointly validated source edits."""


def _touch(a,b):
    if a[0]==a[1]:return a==b or b[0]<=a[0]<b[1]
    if b[0]==b[1]:return a[0]<=b[0]<a[1]
    return a[0]<b[1] and b[0]<a[1]


def groups(options):
    """Edits sharing evidence or grammatical dependencies belong together."""
    out=[]
    for option in sorted(options,key=lambda o:(o['start'],o['end'],o['rank'],o['surface'])):
        connected=[g for g in out if any(
            _touch((option['start'],option['end']),(old['start'],old['end']))
            or bool(set(option['anomalies']) & set(old['anomalies']))
            or _touch(option['context'],old['context']) for old in g)]
        for group in connected:out.remove(group)
        out.append([option]+[old for group in connected for old in group])
    return out


def choose(options,validate,budget):
    """Choose among observed valid sets; report unexplored branches at the cap.

    Budget counts full combinations, not the number of candidates. A separate
    derived bound on visited prefix states prevents a conflict-heavy tree from
    spending unbounded time before reaching a complete set.
    """
    if budget<1:raise ValueError('budget must be positive')
    by_range={}
    for option in options:
        by_range.setdefault((option['start'],option['end']),[]).append(option)
    choices=[sorted(rows,key=lambda row:(row['rank'],row['surface']))
             for key,rows in sorted(by_range.items())]
    best=[];best_key=(0,(),())
    examined=0;visited=0
    stack=[(0,[],frozenset())]
    prefix_limit=budget*(len(choices)+1)
    while stack and examined<budget and visited<prefix_limit:
        index,selected,solved=stack.pop();visited+=1
        if index==len(choices):
            examined+=1
            key=(-len(solved),tuple(sorted((row['rank'] for row in selected),reverse=True)),
                 tuple((row['start'],row['end'],row['surface']) for row in selected))
            if key<best_key and validate(selected):best=selected;best_key=key
            continue
        # Skip is a real possibility, but visit compatible corrections first.
        stack.append((index+1,selected,solved))
        for option in reversed(choices[index]):
            if set(option['anomalies']) & solved:continue
            if any(_touch((option['start'],option['end']),(old['start'],old['end'])) for old in selected):continue
            stack.append((index+1,selected+[option],solved|frozenset(option['anomalies'])))
    return best,dict(limit=budget,examined=examined,prefix_states=visited,
                     unexplored=bool(stack),state='truncated' if stack else 'complete',
                     resolved=len(set(a for row in best for a in row['anomalies'])))
