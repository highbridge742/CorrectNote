# -*- coding: utf-8 -*-
"""Combine an existing key repair with its original object's same-reading sense."""
from dataclasses import replace
from copy import deepcopy


def extend(targets,diagnostics,engine,tokenize,store,dictionary,decisions):
    from contextual_repair import validate,rank_candidates
    from semantic_roles import object_before,nominal_roles,candidate_evidence
    from morphology import tokenize as native_tokens,native_spelling_only
    from reading_segments import _native_nominal_reading_faces
    from context_meaning import anomalous_frames,candidates
    from literal_examples import protected_ranges,overlaps
    from last_choice import surface_for_reading
    extra={};protected=None
    for target,diagnostic in zip(targets,diagnostics):
        rows=diagnostic.get('candidates',())
        if not rows or not target.structural or not target.anomalies:continue
        obj=object_before(target.context,target.start-target.context_start,tokenize)
        if not obj or not target.source[:target.start].endswith(obj+'を'):continue
        start=target.start-len(obj)-1;end=target.start-1
        if start<target.context_start:continue
        prefix=target.source[start:target.start];parts=native_tokens(prefix)
        if (not parts or not all(t.has_reading for t in parts)
            or parts[-1].surface!='を' or parts[-1].pos!='助詞'
            or not all(t.pos=='名詞' and not t.pos_sub.startswith('固有名詞') for t in parts[:-1])):continue
        rd=''.join(t.reading for t in parts[:-1]);prefix_rd=rd+parts[-1].reading
        if surface_for_reading(rd)==obj:continue
        if not any(face!=obj and nominal_roles(face) for face in _native_nominal_reading_faces(rd)):continue
        if protected is None:protected=protected_ranges(target.source)
        if overlaps(start,end,protected):continue
        for row in rows:
            # The existing resolver already proved this reading, physical edit,
            # and action in the original clause. Its object spelling is still open.
            projected=target.substitute(row['surface'])
            for frame in anomalous_frames(projected):
                if ((frame['start'],frame['end'])!=(start-target.context_start,end-target.context_start)
                    or frame['surface']!=obj or frame['reading']!=rd
                    or frame['evidence_end']<=target.start-target.context_start):continue
                for noun in candidates(frame):
                    if noun==obj or not native_spelling_only(rd,noun):continue
                    surface=noun+'を'+row['surface']
                    changed_reading=prefix_rd+row['repair']['reading']
                    wide=replace(target,start=start,boundary_kind='lexical',preserved_head='',
                                 spelling=(),candidate_surface='',candidate_reading='')
                    ok,reason=validate(wide,surface,engine,tokenize,store,dictionary,decisions,changed_reading)
                    if not ok:continue
                    extended=deepcopy(row)
                    extended['surface']=surface
                    extended['reading']['text']=prefix_rd+row['reading']['text']
                    extended['reading']['source']='joint_source_argument'
                    extended['also_from_legacy']=False
                    segments=tuple((a+len(prefix),b+len(prefix),reading,kind)
                                   for a,b,reading,kind in row['reading']['segments'])
                    extended['reading']['segments']=tuple((p.start,p.end,p.reading,'analyzed_word') for p in parts)+segments
                    extended['reading']['provenance']=(('joint_original_argument',obj,rd,row['reading']),)
                    extended['repair']['reading']=changed_reading
                    if extended['repair']['position']>=0:extended['repair']['position']+=len(prefix_rd)
                    for step in extended['repair'].get('steps',()):
                        if step['position']>=0:step['position']+=len(prefix_rd)
                    e=extended['rank_evidence'];e['start']=start
                    e['source_relation']=min(e.get('source_relation',0),-1)
                    e['meaning']=min(e['meaning'],-2)
                    # A different nominal spelling cannot inherit parse/reading
                    # costs measured on the old whole clause. Missing evidence
                    # stays neutral in the common cohort ranker.
                    for key in ('cost','local_reading','parse_cost','continuation'):e[key]=None
                    extended['local_prediction']=None
                    extended['argument_evidence']=candidate_evidence(noun,row['surface'],target.following,
                        target.source[target.context_start:start]+noun+'を')
                    extended['argument_fit']=bool(extended['argument_evidence'] and extended['argument_evidence']['shared_roles'])
                    extended['object_word']=noun
                    extended['source_meaning']=dict(kind=frame['kind'],original_argument=obj,
                        argument=noun,argument_reading=rd,original_action=target.text,
                        action=row['surface'],source_start=start,source_end=target.end,
                        physical_repair=deepcopy(row['repair']))
                    extended['support']=[dict(reading=extended['reading'],repair=extended['repair'])]
                    key=(start,target.end,target.context_start,target.context_end,target.anomalies)
                    if key not in extra:
                        extra[key]=(wide,dict(start=start,end=target.end,text=wide.text,
                            boundary_kind='lexical',preserved_head='',context_start=wide.context_start,
                            context_end=wide.context_end,anomalies=wide.anomalies,structural=True,
                            readings=[],candidates=[],rejected={},status='joint_original_meaning'))
                    extra[key][1]['candidates'].append(extended)
    for wide,diagnostic in extra.values():
        diagnostic['candidates']=rank_candidates(diagnostic['candidates'])
        diagnostic['readings']=[row['reading'] for row in diagnostic['candidates']]
        targets.append(wide);diagnostics.append(diagnostic)
    return targets,diagnostics
