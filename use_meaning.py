# -*- coding: utf-8 -*-
"""Prefer ordinary tool use unless this source supplies a private-purpose sense."""

def frames(source):
    from morphology import tokenize, native_suru_form
    from semantic_roles import nominal_roles, support, object_before, _closed_object_predicate_spans, _terminal_predicate_tail
    from contextual_repair import _source_clause_bounds
    from literal_examples import protected_ranges, overlaps
    from last_choice import surface_for_reading
    parts=tokenize(source)
    legacy=[(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,t.has_reading,t.infl_form) for t in parts]
    closed=None
    out=[];protected=None
    for i,word in enumerate(parts):
        if (word.pos!='名詞' or word.pos_sub!='サ変接続' or not word.has_reading
            or not nominal_roles(word.surface)&{'general_use_action','private_use_action'}):continue
        if surface_for_reading(word.reading)==word.surface:continue
        if i+1>=len(parts):continue
        action=parts[i+1]
        if (action.start!=word.end or action.pos!='動詞' or not action.has_reading
            or not native_suru_form(action.surface,action.infl_form,action.reading,False)):continue
        if closed is None:
            closed={a:(obj,b) for obj,act,a,b in _closed_object_predicate_spans(source,legacy)}
        lo,hi=_source_clause_bounds(source,word.start,word.end)
        obj=None;obj_start=None;end=action.end
        if word.start in closed:
            obj=closed[word.start][0]
            case=next((t for t in reversed(parts[:i]) if t.surface=='を' and t.pos=='助詞'),None)
            if case and source[max(lo,case.start-len(obj)):case.start]==obj:
                obj_start=case.start-len(obj)
        else:
            # A finite native suru/past chain immediately modifies its noun.
            # Do not jump over particles or a second independent verb.
            j=i+2
            while j<len(parts) and parts[j].pos=='助動詞' and parts[j].has_reading:j+=1
            if j>=len(parts):continue
            noun=parts[j]
            if (noun.pos!='名詞' or not noun.has_reading or noun.start!=parts[j-1].end
                or not _terminal_predicate_tail(source[:noun.start],legacy[:j],action.end,action.infl_form)):
                continue
            # An explicit inner object already fills this action's object slot.
            if object_before(source,word.start,lambda _:legacy):continue
            obj=noun.surface;obj_start=noun.start;end=noun.end
        if not obj or not support(obj,'使用'):continue
        if 'private_use_action' in nominal_roles(word.surface):
            # Private purpose or an organization's property concretely licenses
            # the narrower sense. It does not force that sense on ordinary use.
            context=source[lo:word.start]
            owner=next((a for a,b in zip(parts,parts[1:]) if b.end==obj_start
                and b.surface=='の' and b.pos=='助詞' and b.pos_sub=='連体化'
                and a.end==b.start and a.has_reading and a.pos=='名詞'),None)
            if (nominal_roles(obj)&{'organizational_property'}
                or owner and 'organization' in nominal_roles(owner.surface)
                or any(context.endswith(cue) for cue in ('私的に','個人的に','私的な目的で','個人の目的で','業務外で'))):
                continue
        if protected is None:protected=protected_ranges(source)
        if overlaps(word.start,end,protected):continue
        out.append(dict(kind='use_action',start=word.start,end=word.end,surface=word.surface,
            reading=word.reading,evidence_start=lo,evidence_end=end,
            reason='道具や情報を使う文では、私的な目的の根拠がなければ一般的な使用の意味を選びます'))
    return tuple(out)
