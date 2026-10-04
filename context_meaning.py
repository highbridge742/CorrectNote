# -*- coding: utf-8 -*-
"""Source role contrasts for qualities and physical amounts.

The semantic classes are reviewed ordinary senses in semantic_roles. IME
supplies same-reading spellings only after a source relationship is suspect.
The selected spelling must fit that relationship after all edits are joined.
"""

_EXPECTED={'addressed_venue':'reservable_place','use_action':'general_use_action','familiar_nominal':'ordinary_spelling','familiar_action':'ordinary_spelling','return_action':'homecoming','attainment_action':'attain_result','duty_action':'fulfill_role','repair_action':'structural_repair','placement_action':'object_placement','measurement_action':'dimension_measure','text_edit_action':'text_edit_activity','photographic_action':'image_capture','counted_object':'object','reserved_place':'reservable_place','assessment_quality':'quality_measure','motion_extent':'physical_motion',
           'ui_case':'screen_location','geometric_count':'linear_quantity',
           'deliberative_arrival':'epistemic_result'}
_CONFLICT={'addressed_venue':'open_environment','use_action':'private_use_action','familiar_nominal':'restricted_spelling','familiar_action':'restricted_spelling','return_action':'natural_cycle','attainment_action':'pay_due','duty_action':'employment','repair_action':'healing','placement_action':'auxiliary_preparation','measurement_action':'planned_achievement','text_edit_action':'fixation_state','photographic_action':'acquisition','counted_object':'','reserved_place':'open_environment','assessment_quality':'social_institution','motion_extent':'opening_event',
           'ui_case':'eating_tool','geometric_count':'country',
           'deliberative_arrival':'political_arena'}
_REASONS={'addressed_venue':'住所に対応する施設と自然環境の同読みが競合しています','reserved_place':'予約・借用する施設と自然環境の同読みが競合しています','assessment_quality':'測定・判断の品質に制度・組織の同読みが競合しています',
          'motion_extent':'回る物の動きに開業・開閉の同読みが競合しています',
          'ui_case':'画面上の標識の位置に食器の語義が使われています',
          'geometric_count':'幾何学的な線には国名より同読みの数量が一般的です'}

def contexts(source):
    """Reuse source meaning only during this correction, never in user history."""
    from ime_inverse_gate import _CORRECTION_CACHE
    cache=_CORRECTION_CACHE.get();key=('source_meaning_contexts',source)
    if cache is not None and key in cache:return cache[key]
    result=_contexts(source)
    if cache is not None:cache[key]=result
    return result


def _contexts(source,owner_spelling=True):
    out=list(_quality_contexts(source))
    if any(x in source for x in ('ぐらいの','くらいの','ほどの')):
        import morphology as M
        from semantic_roles import nominal_roles
        from literal_examples import protected_ranges,overlaps
        parts=M.tokenize(source);protected=None
        for i,t in enumerate(parts):
            if i<5 or t.pos!='名詞' or not t.has_reading:continue
            control,case,verb,degree,genitive=parts[i-5:i]
            if ('rotating_control' in nominal_roles(control.surface)
                and case.surface in ('で','が','を') and case.pos=='助詞'
                and verb.pos=='動詞' and verb.base_form in ('動く','動かす','回る','回す')
                and verb.infl_form=='基本形' and degree.surface in ('ぐらい','くらい','ほど')
                and degree.pos=='助詞' and genitive.surface=='の' and genitive.pos=='助詞'
                and all(a.end==b.start for a,b in zip(parts[i-5:i],parts[i-4:i+1]))):
                if protected is None:protected=protected_ranges(source)
                if not overlaps(control.start,t.end,protected):
                    out.append(dict(start=t.start,end=t.end,reading=t.reading,kind='motion_extent',
                        surface=t.surface,evidence_start=control.start,evidence_end=t.end,
                        reason=_REASONS['motion_extent']))
    out.extend(_local_contexts(source))
    from measurement_meaning import frames as measurement_frames
    out.extend(measurement_frames(source))
    from familiar_meaning import frames as familiar_frames
    out.extend(familiar_frames(source))
    from familiar_nominal import frames as familiar_nominal_frames
    out.extend(familiar_nominal_frames(source))
    from use_meaning import frames as use_frames
    out.extend(use_frames(source))
    out.extend(_placement_contexts(source))
    from return_meaning import frames as return_frames
    out.extend(return_frames(source))
    result=_coordinated_expectations(source,tuple(out))
    if owner_spelling:
        from semantic_owner_spelling import frames
        result+=frames(source)
    return result


def _quality_contexts(source):
    """A measured/estimated process owns its quality; concrete actions may choose a system."""
    from semantic_roles import QUALITY_ASSESSMENTS
    if not any(act in source for act in QUALITY_ASSESSMENTS):return ()
    import morphology as M
    from literal_examples import protected_ranges,overlaps
    parts=M.tokenize(source);out=[];protected=None
    for i,(act,link,noun) in enumerate(zip(parts,parts[1:],parts[2:])):
        if not (act.surface in QUALITY_ASSESSMENTS and act.pos=='名詞'
                and act.pos_sub=='サ変接続' and noun.pos=='名詞'
                and all(t.has_reading for t in (act,link,noun))
                and act.end==link.start and link.end==noun.start):continue
        genitive=link.surface=='の' and link.pos=='助詞'
        relative=(link.pos=='動詞' and link.base_form=='する' and link.infl_form=='基本形')
        if not genitive and not relative:continue
        expected,end,quality_action=_quality_role(parts,act.surface,noun.end)
        if relative and end==noun.end:continue
        if protected is None:protected=protected_ranges(source)
        if overlaps(act.start,end,protected):continue
        frame=dict(start=noun.start,end=noun.end,surface=noun.surface,reading=noun.reading,
            kind='assessment_quality',expected_role=expected,
            evidence_start=act.start,evidence_end=end,reason=_REASONS['assessment_quality'])
        out.append(frame)
        if genitive:
            out.extend(_reading_frames(source,frame,protected,
                lambda end:_quality_role(parts,act.surface,end)[:2]))
    return tuple(out)


def _quality_role(parts,act,end):
    # Evaluation also commonly denotes an institutional procedure. A direct
    # quality action can choose its measurement sense, in either spelling.
    expected='social_institution' if act=='評価' else 'quality_measure'
    pair=next(((case,action) for case,action in zip(parts,parts[1:])
        if case.start==end and case.end==action.start and case.surface=='を'
        and case.pos=='助詞' and action.has_reading),None)
    if pair is None:return expected,end,False
    case,action=pair
    if (action.pos=='名詞' and action.pos_sub=='サ変接続'
            and action.surface in ('制定','改正','廃止','導入','改革','創設','施行')):
        return 'social_institution',action.end,False
    if ((action.pos=='動詞' and action.base_form in ('上げる','高める','下げる'))
        or (action.pos=='名詞' and action.pos_sub=='サ変接続'
            and action.surface in ('向上','改善'))):
        return 'quality_measure',action.end,True
    return expected,end,False


def _reading_frames(source,frame,protected,role_for_end=None):
    """The same source relationship can select an unconverted native noun."""
    from literal_examples import overlaps
    start=frame['start'];out=[]
    if not ('ぁ'<=source[start:start+1]<='ゖ'):return ()
    for end in range(start+1,min(len(source),start+18)+1):
        raw=source[start:end]
        if not all('ぁ'<=c<='ゖ' or c=='ー' for c in raw):break
        nextchar=source[end:end+1]
        if nextchar and nextchar not in 'をがはのにでとも、。！？!?\t\r\n ⇒→':continue
        if overlaps(start,end,protected):continue
        expected,evidence_end=(role_for_end(end) if role_for_end else
                              (_expected_role(frame),max(end,frame['evidence_end'])))
        candidate=dict(frame,end=end,surface=raw,reading=raw,reading_spelling=True,
                       expected_role=expected,evidence_end=evidence_end)
        if candidates(candidate):out.append(candidate)
    return tuple(out)


def anomalous_frames(source):
    from semantic_roles import nominal_roles
    return tuple(f for f in contexts(source)
                 if (f.get('reading_spelling') or f['kind']=='counted_object' or bool(set(f.get('conflict_roles',(f.get('conflict_role',_CONFLICT[f['kind']]),))) & _meaning_roles(f)))
                 and _expected_role(f) not in _meaning_roles(f)
                 # Country + line is ambiguous, not intrinsically malformed.
                 # Prefer quantity only with an attested same-reading quantity.
                 and (f['kind'] not in ('geometric_count','deliberative_arrival','counted_object','photographic_action') or bool(candidates(f))))

def candidates(frame):
    if frame['kind']=='familiar_nominal':return frame['ordinary_faces']
    if frame.get('owner_spelling'):
        owner=frame['owner_spelling']
        return tuple(owner['prefix']+face for face in candidates(owner['core']))
    from morphology import dictionary_inflections,native_spelling_only
    from semantic_roles import nominal_roles
    from ime_candidates import SearchCandidates
    from ime_inverse_gate import _CORRECTION_CACHE
    if 'inflection' in frame:return _action_candidates(frame)
    role=_expected_role(frame)
    cache=_CORRECTION_CACHE.get();key=('meaning_candidates',frame['kind'],role,frame['reading'])
    if cache is not None and key in cache:return cache[key]
    with SearchCandidates() as search:
        if not search.available:return ()
        generated=search.candidates(frame['reading'])
    result=tuple(s for s in dict.fromkeys(generated)
        if role in nominal_roles(s) and
        (native_spelling_only(frame['reading'],s) if frame['kind']=='geometric_count' else
         any(pos.startswith('名詞,') and rd==frame['reading']
             for pos,form,base,rd in dictionary_inflections(s) or ())))
    if cache is not None:cache[key]=result
    return result


def supports_replacement(target,changed,local_start,local_end,surface):
    return supports_span(target.source,changed,target.start,target.end,local_start,local_end,surface)


def supports_span(source,changed,start,end,local_start,local_end,surface):
    source_frames=[f for f in anomalous_frames(source)
                   if (f['start'],f['end'])==(start,end)]
    changed_frames=contexts(changed)
    for frame in source_frames:
        head_start=local_start;face=surface
        if frame.get('owner_spelling'):
            prefix=frame['owner_spelling']['prefix']
            if not surface.startswith(prefix):continue
            head_start+=len(prefix);face=surface[len(prefix):]
        if _expected_role(frame) not in _meaning_roles(frame,surface):continue
        if frame.get('proper_default'):
            from familiar_nominal import proper_replacement_fits
            if proper_replacement_fits(frame,changed,head_start,local_end,face):return True
        if any(frame['kind']==g['kind'] and g['start']==head_start and g['end']==local_end
               and g['surface']==face and _expected_role(g)==_expected_role(frame)
               for g in changed_frames):return True
    return False


def preserves_argument_relation(source,start,end,changed,local_start,local_end,established=False):
    """A wider repair retains a proved meaning from its unchanged argument.

    Anomalous source heads supply the normal constraint. A caller preserving
    a written predicate can also retain its already established meaning.
    The argument lies outside the replacement and must remain identical.
    A later predicate or another field cannot explain the repaired head.
    """
    if source[:start]!=changed[:local_start]:return True
    source_frames=contexts(source) if established else anomalous_frames(source)
    frames=[frame for frame in source_frames
            if frame['start']==start and frame['end']<=end
            and frame.get('evidence_start',start)<start]
    if not frames:return True
    candidates=[frame for frame in contexts(changed)
                if frame['start']==local_start and frame['end']<=local_end]
    def fits(candidate,expected):
        if expected in _meaning_roles(candidate):return True
        # A literal native verb retains the same independently attested
        # inflection/readings as its written spelling. Do not require that
        # its first parse chose a particular homophone's kanji.
        if candidate.get('reading_spelling') and candidate.get('inflection'):
            from semantic_roles import ACTION_MEANINGS,_native_lexeme_forms
            return any(_native_lexeme_forms(lemma,candidate['inflection'],candidate['reading'])
                       for lemma in ACTION_MEANINGS.get(expected,()))
        return False
    return all(any(frame['kind']==candidate['kind']
                   and _expected_role(frame)==_expected_role(candidate)
                   and fits(candidate,_expected_role(frame))
                   for candidate in candidates) for frame in frames)


def _local_contexts(source):
    """Case/quantity relations, bounded to the original tab/arrow field."""
    arrival=_arrival_contexts(source)+_object_contexts(source)+_owned_motion_contexts(source)+_counted_object_contexts(source)+_cursor_destination_contexts(source)+_photographic_action_contexts(source)+_text_edit_contexts(source)
    if 'で' not in source and 'の' not in source:return arrival
    import morphology as M
    from semantic_roles import nominal_roles
    from reading_segments import native_counted_nominal_evidence
    from literal_examples import protected_ranges,overlaps
    parts=M.tokenize(source);out=list(arrival);protected=None
    out.extend(_reading_head_contexts(source,parts))
    for index,(head,case,noun) in enumerate(zip(parts,parts[1:],parts[2:])):
        if (not all(t.has_reading for t in (head,case,noun))
                or head.end!=case.start or case.end!=noun.start or head.pos!='名詞'):
            continue
        kind=None
        if case.surface=='の' and case.pos=='助詞' and noun.surface in ('住所','所在地'):
            kind='addressed_venue'
        if case.surface=='で' and case.pos=='助詞' and 'screen_marker' in nominal_roles(noun.surface):
            kind='ui_case'
        if case.surface=='の' and case.pos=='助詞' and 'geometric_line' in nominal_roles(noun.surface):
            kind='geometric_count'
        if not kind:continue
        start=head.start;face=head.surface;reading=head.reading
        if index and parts[index-1].end==head.start:
            combined=source[parts[index-1].start:head.end]
            if native_counted_nominal_evidence(combined):
                start=parts[index-1].start;face=combined
                reading=parts[index-1].reading+head.reading
        if 'country' in nominal_roles(face):
            from ime_language import JapaneseIME
            with JapaneseIME() as ime:
                inverse=ime.reverse_words(face) if ime.available else None
            if inverse:reading=inverse[0]
        if protected is None:protected=protected_ranges(source)
        if overlaps(start,noun.end,protected):continue
        out.append(dict(start=start,end=head.end,surface=face,reading=reading,kind=kind,
                        evidence_start=start,evidence_end=noun.end,reason=_REASONS[kind]))
    return tuple(out)


def _meaning_roles(frame,surface=None):
    face=frame['surface'] if surface is None else surface
    if frame.get('owner_spelling'):
        owner=frame['owner_spelling'];prefix=owner['prefix']
        # The original owner was already proved by its exact native reading.
        # Only a replacement must supply the coordinated written prefix.
        if surface is None:return _meaning_roles(owner['core'])
        return _meaning_roles(owner['core'],face[len(prefix):]) if face.startswith(prefix) else frozenset()
    if frame['kind']=='familiar_nominal':
        from familiar_nominal import roles
        return roles(frame,face)
    if frame['kind']=='familiar_action':
        from familiar_meaning import roles
        return roles(frame,face)
    if 'inflection' not in frame:
        from semantic_roles import nominal_roles
        return nominal_roles(face)
    from morphology import dictionary_inflections
    from semantic_roles import ACTION_MEANINGS
    lemmas={base for pos,form,base,rd in dictionary_inflections(face) or ()
            if pos.startswith('動詞,') and form==frame['inflection']}
    if face and all('ぁ'<=c<='ゖ' for c in face):
        # A native inflected reading already carries its possible action
        # meanings. Its kanji spelling is not a new structural repair.
        from semantic_roles import _native_lexeme_forms
        lemmas.update(lemma for words in ACTION_MEANINGS.values() for lemma in words
                      if _native_lexeme_forms(lemma,frame['inflection'],face))
    return frozenset(role for role,words in ACTION_MEANINGS.items() if words & lemmas)


def _action_candidates(frame):
    if frame['kind']=='familiar_action':
        from familiar_meaning import candidates
        return candidates(frame)
    from ime_candidates import SearchCandidates
    from morphology import dictionary_inflections
    from ime_inverse_gate import _CORRECTION_CACHE
    role=_expected_role(frame);tail=frame['query_tail']
    key=('meaning_action_candidates',role,frame['reading'],frame['inflection'],tail,frame['tail_reading'])
    cache=_CORRECTION_CACHE.get()
    if cache is not None and key in cache:return cache[key]
    with SearchCandidates() as search:
        generated=search.candidates(frame['reading']+frame['tail_reading']) if search.available else ()
    out=[]
    for result in generated:
        if tail and not result.endswith(tail):continue
        face=result[:-len(tail)] if tail else result
        if (role in _meaning_roles(frame,face) and any(pos.startswith('動詞,')
            and form==frame['inflection'] and rd==frame['reading']
            for pos,form,base,rd in dictionary_inflections(face) or ())):out.append(face)
    # An unchanged kana result is not a completed spelling search. Reuse
    # every independently attested inflection for this same action meaning.
    from semantic_roles import ACTION_MEANINGS,_native_lexeme_forms
    out.extend(face for word in ACTION_MEANINGS[role]
               for face in _native_lexeme_forms(word,frame['inflection'],frame['reading']))
    result=tuple(dict.fromkeys(out))
    # A literal kana form can share this lemma and meaning with its written
    # inflection. It is an unfinished spelling, not a competing lexical sense.
    # Retain all distinct written forms; their ambiguity is still compared.
    written=tuple(face for face in result if any('一'<=c<='鿿' or 'ァ'<=c<='ヺ' for c in face))
    if written:result=written
    if cache is not None:cache[key]=result
    return result


def _photographic_action_contexts(source):
    """Default to capture, with a same-object physical continuation as evidence."""
    from semantic_roles import NOUN_GROUPS
    if 'を' not in source or not any(x in source for x in NOUN_GROUPS['photographic_media']):return ()
    import morphology as M
    from literal_examples import protected_ranges,overlaps
    parts=M.tokenize(source);out=[];protected=None
    for i,noun in enumerate(parts[:-2]):
        if noun.surface not in NOUN_GROUPS['photographic_media'] or noun.pos!='名詞':continue
        frame=action_frame(source,parts,i+1,noun.start,'photographic_action','image_capture',
            ('image_capture','acquisition'),
            '画像を作る撮影と、物を手に取る動作の同読みを比較しています')
        if frame is None:continue
        if frame['query_tail'].startswith(('て','で')):
            tail=parts[i+3]
            following=[t for t in parts[i+4:] if t.start-tail.end<=16]
            nextverb=next((t for t in following if t.pos=='動詞' and t.pos_sub=='自立'),None)
            handling=('置く','並べる','渡す','しまう','破る','捨てる','返す','重ねる')
            from semantic_owner_spelling import placement_continuation
            placement=placement_continuation(source,tail.end,min(len(source),tail.end+20),handling)
            if placement:
                frame['expected_role']='image_capture' if placement['digital'] else 'acquisition'
                frame['evidence_end']=placement['end']
            elif nextverb and nextverb.base_form in handling:
                between=source[tail.end:nextverb.start]
                if (not any(t.surface=='を' for t in following if t.start<nextverb.start)
                        and not any(c in between for c in '。！？!?\t\r\n⇒→')):
                    frame['expected_role']='acquisition';frame['evidence_end']=nextverb.end
        if protected is None:protected=protected_ranges(source)
        if not overlaps(noun.start,frame['evidence_end'],protected):out.append(frame)
    return tuple(out)


def _cursor_destination_contexts(source):
    """Position an actual screen marker at its native destination phrase."""
    if 'を' not in source or not ('に' in source or 'へ' in source):return ()
    import morphology as M
    from semantic_roles import nominal_roles
    from literal_examples import protected_ranges,overlaps
    parts=M.tokenize(source);out=[];protected=None
    def positioning(action):
        return (action.has_reading and
            (action.pos=='動詞' and action.base_form in ('移す','動かす','寄せる','置く','合わせる','戻す')
             or action.pos=='名詞' and action.pos_sub=='サ変接続'
             and action.surface in ('移動','配置','固定','表示')))
    def add(start,end,lo,hi):
        nonlocal protected
        if not start<end:return
        if protected is None:protected=protected_ranges(source)
        if overlaps(lo,hi,protected):return
        face=source[start:end]
        raw=all('ぁ'<=c<='ゖ' or c=='ー' for c in face)
        nominal=[t for t in parts if t.start==start and t.end==end and t.pos=='名詞' and t.has_reading]
        if not raw and not nominal:return
        frame=dict(start=start,end=end,surface=face,reading=face if raw else nominal[0].reading,
            kind='ui_case',evidence_start=lo,evidence_end=hi,
            reason='画面の標識を配置する位置と食器の同読みが競合しています')
        if raw:
            frame['reading_spelling']=True
            if not candidates(frame):return
        out.append(frame)
    for i,case in enumerate(parts):
        if case.surface!='を' or case.pos!='助詞':continue
        # The reviewed screen-marker name can span tokenizer fragments (キャレット).
        # Only the unchanged exact name is used, never an arbitrary unknown prefix.
        starts=[t.start for t in parts[max(0,i-4):i]
                if 'screen_marker' in nominal_roles(source[t.start:case.start])]
        if not starts:continue
        marker_start=min(starts)
        for j in range(i+1,min(len(parts)-1,i+6)):
            destination,action=parts[j:j+2]
            if destination.start-case.end>12:break
            if (destination.surface in ('に','へ') and destination.pos=='助詞'
                and destination.end==action.start and positioning(action)):
                add(case.end,destination.start,marker_start,action.end)
        # Reverse argument order retains the same actual destination and action.
        destination=next((t for t in parts if t.end==marker_start),None)
        if destination and i+1<len(parts):
            action=parts[i+1]
            if (destination.surface in ('に','へ') and destination.pos=='助詞'
                and case.end==action.start and positioning(action)):
                starts=[t.start for t in parts if destination.start-12<=t.start<destination.start]
                for start in reversed(starts):
                    face=source[start:destination.start]
                    if any(c in face for c in '\t\r\n⇒→'):break
                    add(start,destination.start,start,action.end)
    return tuple(out)


def _counted_object_contexts(source):
    """An exact native quantity owns its noun, even if のき is parsed as 軒."""
    if 'の' not in source:return ()
    import morphology as M
    from reading_segments import native_counted_nominal_evidence
    from literal_examples import protected_ranges,overlaps
    parts=M.tokenize(source);out=[];protected=None;roles={'枚':'sheet_object','台':'device'}
    for case in (i for i,c in enumerate(source) if c=='の'):
        start=case+1
        if start>=len(source):continue
        reading_head='ぁ'<=source[start]<='ゖ'
        noun=next((t for t in parts if t.start==start),None)
        if not reading_head and (noun is None or noun.pos!='名詞' or not noun.has_reading):continue
        if not reading_head:
            following=next((t for t in parts if t.start==noun.end),None)
            if following and (following.surface=='の' or following.pos=='名詞'):continue
        for before in reversed([t for t in parts if case-12<=t.start<case]):
            quantity=source[before.start:case]
            proof=native_counted_nominal_evidence(quantity)
            units={unit for unit,ordinal in proof or () if not ordinal}
            if len(units)!=1 or not units<=roles.keys():continue
            if protected is None:protected=protected_ranges(source)
            end=start+1 if reading_head else noun.end
            if overlaps(before.start,end,protected):continue
            frame=dict(start=start,end=end,surface=source[start:end],
                reading=source[start:end] if reading_head else noun.reading,
                kind='counted_object',expected_role=roles[next(iter(units))],
                evidence_start=before.start,evidence_end=end,
                reason='助数詞が数える物と同じ読みの名詞の意味を比較しています')
            if not reading_head:out.append(frame)
            out.extend(f for f in _reading_frames(source,frame,protected)
                       if source[f['end']:f['end']+1]!='の')
            break
    return tuple(out)


def _owned_motion_contexts(source):
    """A rotating mechanism owns motion, independently of a degree phrase."""
    if 'の' not in source:return ()
    import morphology as M
    from semantic_roles import nominal_roles
    from literal_examples import protected_ranges,overlaps
    out=[];protected=None;parts=M.tokenize(source)
    for owner,link,noun in zip(parts,parts[1:],parts[2:]):
        if not ('rotating_control' in nominal_roles(owner.surface)
                and owner.pos=='名詞' and link.pos=='助詞' and link.surface=='の'
                and noun.pos=='名詞' and all(t.has_reading for t in (owner,link,noun))
                and owner.end==link.start and link.end==noun.start):continue
        if protected is None:protected=protected_ranges(source)
        if overlaps(owner.start,noun.end,protected):continue
        frame=dict(start=noun.start,end=noun.end,surface=noun.surface,reading=noun.reading,
            kind='motion_extent',evidence_start=owner.start,evidence_end=noun.end,
            reason=_REASONS['motion_extent'])
        out.append(frame);out.extend(_reading_frames(source,frame,protected))
    return tuple(out)


def _object_contexts(source):
    """An explicitly adjacent object and reservation/borrowing predicate."""
    if 'を' not in source:return ()
    import morphology as M
    from literal_examples import protected_ranges,overlaps
    parts=M.tokenize(source);out=[];protected=None
    for i,(noun,case,action) in enumerate(zip(parts,parts[1:],parts[2:])):
        if not (noun.pos=='名詞' and case.pos=='助詞' and case.surface=='を'
                and noun.end==case.start and case.end==action.start
                and all(t.has_reading for t in (noun,case,action))):continue
        end=action.end
        if action.pos=='動詞':
            if action.base_form not in ('借りる','貸す','貸し切る'):continue
        elif action.pos=='名詞' and action.pos_sub=='サ変接続':
            if action.surface not in ('予約','確保','借用','賃借','貸切'):continue
            tail=parts[i+3] if i+3<len(parts) else None
            if tail is not None and tail.start==action.end and tail.pos!='記号':
                if not (tail.pos=='動詞' and tail.has_reading and tail.base_form=='する'):continue
                end=tail.end
        else:continue
        if protected is None:protected=protected_ranges(source)
        if overlaps(noun.start,end,protected):continue
        out.append(dict(start=noun.start,end=noun.end,surface=noun.surface,reading=noun.reading,
            kind='reserved_place',evidence_start=noun.start,evidence_end=end,
            reason=_REASONS['reserved_place']))
    return tuple(out)


def _arrival_contexts(source):
    if '辿' not in source and 'たど' not in source:return ()
    import morphology as M
    import semantic_roles as S
    from literal_examples import protected_ranges,overlaps
    out=[];parts=M.tokenize(source)
    protected=None
    for noun,case,verb,tail in zip(parts,parts[1:],parts[2:],parts[3:]):
        if (noun.pos!='名詞' or case.surface!='に' or case.pos!='助詞'
            or verb.base_form not in ('辿る','たどる') or verb.infl_form!='連用形'
            or tail.base_form not in ('着く','つく') or tail.pos!='動詞'
            or not all(t.has_reading for t in (noun,case,verb,tail))
            or not all(a.end==b.start for a,b in zip((noun,case,verb),(case,verb,tail)))):continue
        sep=list(M.COLUMN_SEPARATOR.finditer(source))
        lo=next((m.end() for m in reversed(sep) if m.end()<=noun.start),0)
        hi=next((m.start() for m in sep if m.start()>=tail.end),len(source))
        if any('political_context' in S.nominal_roles(t.surface)
               for t in parts if lo<=t.start and t.end<=hi and t.start!=noun.start):continue
        # A country's explicitly modified arena is a concrete political destination.
        index=parts.index(noun)
        if (index>=2 and parts[index-1].surface=='の'
                and parts[index-1].end==noun.start and parts[index-2].end==parts[index-1].start
                and 'country' in S.nominal_roles(parts[index-2].surface)):continue
        if protected is None:protected=protected_ranges(source)
        if overlaps(noun.start,tail.end,protected):continue
        out.append(dict(start=noun.start,end=noun.end,surface=noun.surface,reading=noun.reading,
                        kind='deliberative_arrival',evidence_start=noun.start,evidence_end=tail.end,
                        reason='政治の文脈がなく到達した結論の同読みと競合しています'))
    return tuple(out)


def _reading_head_contexts(source,parts):
    """A kana spelling can hide the same native noun/case boundary."""
    if 'の' not in source and 'で' not in source:return ()
    from literal_examples import protected_ranges,overlaps
    from semantic_roles import nominal_roles
    out=[];protected=None
    for noun in parts:
        if noun.pos!='名詞' or not noun.has_reading or not noun.start:continue
        case=source[noun.start-1];roles=nominal_roles(noun.surface)
        kind=('geometric_count' if case=='の' and 'geometric_line' in roles else
              'ui_case' if case=='で' and 'screen_marker' in roles else None)
        if not kind:continue
        end=noun.start-1;left=end
        while left and ('ぁ'<=source[left-1]<='ゖ' or source[left-1]=='ー'):left-=1
        for start in (t.start for t in parts if left<=t.start<end):
            raw=source[start:end]
            if not raw or not all('ぁ'<=ch<='ゖ' or ch=='ー' for ch in raw):continue
            frame=dict(start=start,end=end,surface=raw,reading=raw,kind=kind,
                evidence_start=start,evidence_end=noun.end,reading_spelling=True,
                reason='後続名詞の意味関係で、かなの読みを表記する')
            if not candidates(frame):continue
            if protected is None:protected=protected_ranges(source)
            if overlaps(start,noun.end,protected):continue
            out.append(frame)
    return tuple(out)


def _expected_role(frame):
    return frame.get('expected_role',_EXPECTED[frame['kind']])


def _coordinated_expectations(source,frames):
    """Same-head noun phrases in a real と/や coordination share their role.

    A nearby place name alone is not evidence. The peer must independently
    denote a country and have no competing same-reading quantity. This also
    chooses the country spelling for a kana head in that original relation.
    """
    from semantic_roles import nominal_roles
    groups={}
    for f in frames:
        if f['kind']=='geometric_count':groups.setdefault(f['start'],[]).append(f)
    def country_peer(peer):
        if 'country' not in nominal_roles(peer['surface']):return False
        bare=dict(peer);bare.pop('expected_role',None)
        return not candidates(bare)
    for lefts in groups.values():
        for a in lefts:
            join=a['evidence_end']
            if source[join:join+1] not in ('と','や'):continue
            for b in groups.get(join+1,()):
                head=source[a['end']+1:a['evidence_end']]
                if head!=source[b['end']+1:b['evidence_end']]:continue
                for target,peer in ((a,b),(b,a)):
                    if not country_peer(peer):continue
                    target['expected_role']='country'
                    target['parallel_evidence']=(peer['start'],peer['end'],peer['surface'])
                    target['reason']='同じ線を所有する国名が、の句どうしで並列している'
    return tuple(frames)


def _text_edit_contexts(source):
    """Actual editable content as the object of a same-reading activity."""
    if 'を' not in source:return ()
    import morphology as M
    from semantic_roles import nominal_roles
    from literal_examples import protected_ranges,overlaps
    parts=M.tokenize(source);out=[];protected=None
    for i,(noun,case) in enumerate(zip(parts,parts[1:])):
        if not (noun.pos=='名詞' and noun.has_reading and case.pos=='助詞'
                and case.surface=='を' and noun.end==case.start
                and nominal_roles(noun.surface)&{'text','sound','photographic_media'}):continue
        start=case.end
        action=parts[i+2] if i+2<len(parts) else None
        if action is None or action.start!=start:continue
        spans=[]
        if action.pos=='名詞' and action.has_reading:
            spans.append((action.end,action.reading,False))
        if 'ぁ'<=source[start:start+1]<='ゖ':
            for end in range(start+1,min(len(source),start+18)+1):
                raw=source[start:end]
                if not all('ぁ'<=c<='ゖ' or c=='ー' for c in raw):break
                spans.append((end,raw,True))
        for end,reading,kana in spans:
            tail=M.tokenize(source[end:])
            if not tail or tail[0].pos!='動詞' or tail[0].base_form!='する':continue
            finish=end+tail[0].end
            if protected is None:protected=protected_ranges(source)
            if overlaps(noun.start,finish,protected):continue
            frame=dict(start=start,end=end,surface=source[start:end],reading=reading,
                kind='text_edit_action',evidence_start=noun.start,evidence_end=finish,
                reading_spelling=kana,
                reason='文章・映像等を編集する動作と、執着の状態の同読みを比較しています')
            if not kana or candidates(frame):out.append(frame)
    return tuple(out)


def candidate_evidence(source,start,end,surface):
    """Original semantic relations rank every candidate, regardless of route."""
    if source[start:end]==surface:return None
    from numeric_mark_repair import candidate_evidence as numeric_unit_evidence
    unit=numeric_unit_evidence(source,start,end,surface)
    if unit:return unit
    for frame in anomalous_frames(source):
        if (frame['start'],frame['end'])!=(start,end):continue
        if _expected_role(frame) not in _meaning_roles(frame,surface):continue
        changed=source[:start]+surface+source[end:]
        if not supports_span(source,changed,start,end,start,start+len(surface),surface):continue
        return dict(kind=frame['kind'],expected_role=_expected_role(frame),
                    evidence_start=frame['evidence_start'],evidence_end=frame['evidence_end'])
    return None


def action_frame(source,parts,index,object_start,kind,expected,conflicts,reason,case_surface='を'):
    """Retain the exact native verb and its functional tail for meaning choice."""
    case,verb=parts[index:index+2]
    if not (case.surface==case_surface and case.pos=='助詞'
            and case.has_reading and case.end==verb.start):return None
    return action_verb_frame(source,parts,index+1,object_start,kind,expected,conflicts,reason)


def action_verb_frame(source,parts,index,evidence_start,kind,expected,conflicts,reason,lexemes=None):
    """The same exact verb frame serves case and original-usage relations."""
    from semantic_roles import ACTION_MEANINGS
    verb=parts[index]
    if verb.pos!='動詞' or not verb.has_reading:return None
    raw=all('ぁ'<=c<='ゖ' for c in verb.surface)
    lemmas=(frozenset(lexemes) if lexemes is not None else
            frozenset().union(*(ACTION_MEANINGS[r] for r in conflicts)))
    in_family=verb.base_form in lemmas
    if raw:
        from semantic_roles import _native_lexeme_forms
        in_family=any(_native_lexeme_forms(lemma,verb.infl_form,verb.reading) for lemma in lemmas)
    if not in_family:return None
    tail=[];cursor=verb.end
    for part in parts[index+1:index+5]:
        if (part.start!=cursor or not part.has_reading or not
            (part.pos=='助動詞' or part.pos=='助詞' and part.pos_sub=='接続助詞'
             or part.pos=='動詞' and part.pos_sub.startswith('非自立'))):break
        tail.append(part);cursor=part.end
    return dict(start=verb.start,end=verb.end,surface=verb.surface,reading=verb.reading,
        kind=kind,expected_role=expected,inflection=verb.infl_form,conflict_roles=tuple(conflicts),
        query_tail=''.join(t.surface for t in tail),tail_reading=''.join(t.reading for t in tail),
        evidence_start=evidence_start,evidence_end=cursor,reading_spelling=raw,reason=reason)


def _placement_contexts(source):
    """An explicit destination makes おく the independent placement verb."""
    if not any(x in source for x in ('にお','へお','に置','へ置')):return ()
    from semantic_owner_spelling import placement_continuation
    from morphology import tokenize,Token
    from literal_examples import protected_ranges,overlaps
    out=[];protected=None
    for case,c in enumerate(source):
        if c not in ('に','へ'):continue
        begin=max([0]+[i+1 for i,ch in enumerate(source[:case]) if ch in 'を。！？!?\t\r\n⇒→'])
        placement=placement_continuation(source,begin,min(len(source),case+16),('置く',))
        if not placement or placement['case']!=case:continue
        # A native compound case can locate an event (school-ni-oite).
        # Place membership alone does not prove an object was placed there.
        # A support/container or an explicit original object supplies the
        # missing relation; the spelling candidate itself supplies neither.
        whole=tokenize(source)
        compound=next((t for t in whole if t.start==case and t.has_reading
                       and t.pos=='助詞' and t.pos_sub=='格助詞:連語'),None)
        if compound:
            from semantic_roles import nominal_roles,object_before
            physical={'support_surface','container','writing_surface','object'}
            supported=any(physical & nominal_roles(noun) for noun in placement['nouns'])
            def original_tokens(value):
                return [(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                         t.start,t.end,t.has_reading,t.infl_form) for t in tokenize(value)]
            if not supported and not object_before(source,case+1,original_tokens):continue
        # The destination already proves this case boundary. Parsing におき
        # together must not swallow the case into a different best-path word.
        parts=list(tokenize(c))
        parts.extend(Token(t.surface,t.pos,t.base_form,t.reading,t.start+1,t.end+1,
                           t.has_reading,t.pos_sub,t.infl_form) for t in tokenize(source[case+1:]))
        if len(parts)<2:continue
        frame=action_frame(source,parts,0,0,'placement_action','object_placement',
            ('object_placement',),'明示の配置先に続く動作なので補助動詞でなく置くとして表記します',case_surface=c)
        if frame is None:continue
        frame['start']+=case;frame['end']+=case;frame['evidence_end']+=case
        frame['evidence_start']=placement['start']
        if protected is None:protected=protected_ranges(source)
        if not overlaps(frame['evidence_start'],frame['evidence_end'],protected):out.append(frame)
    return tuple(out)


def photographic_candidate_relation(before,surface,following):
    """Rank an admitted action under the same unchanged photo/object sense.

    This supplies no source anomaly. A mistyped action need not already be a
    native とる form to inherit its original object's ordinary relationship.
    """
    text=before+surface+following
    for frame in _photographic_action_contexts(text):
        if (frame['start']==len(before) and frame['end']<=len(before)+len(surface)
                and frame['evidence_start']<len(before)
                and _expected_role(frame) in _meaning_roles(frame)):
            return 'photographic_action/'+_expected_role(frame)
    return None
