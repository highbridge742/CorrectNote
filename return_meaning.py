# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""Ordinary return spellings selected by the source destination or action.

The place/state distinction follows the Agency for Cultural Affairs' 2014
異字同訓 examples (かえす・かえる). Cyclic origins are separate ordinary senses.
https://www.bunka.go.jp/seisaku/bunkashingikai/kokugo/hokoku/pdf/ijidokun_140221.pdf
"""
ROLES=('homecoming','restored_state','natural_cycle')

def frames(source):
    if not any(x in source for x in ('帰','返','還','かえ')):return ()
    from morphology import tokenize,native_spelling_only,dictionary_inflections
    from semantic_roles import nominal_roles,native_verb_lexemes,ACQUISITION_ACTIONS
    from context_meaning import action_verb_frame
    from literal_examples import protected_ranges,overlaps
    parts=tokenize(source);out=[];protected=None
    for v,verb in enumerate(parts):
        if verb.pos!='動詞' or verb.pos_sub!='自立' or not verb.has_reading:continue
        expected=None;begin=verb.start;explicit_unknown=False
        if v>=2:
            before,link=parts[v-2:v]
            adjacent=(before.end==link.start and link.end==verb.start and before.has_reading)
            if adjacent and link.pos=='助詞':
                if link.surface in ('に','へ') and any(p.startswith('助詞,格助詞,') and rd==link.reading
                        for p,f,b,rd in dictionary_inflections(link.surface) or ()):
                    explicit_unknown=True
                    for j in range(max(0,v-5),v-1):
                        units=parts[j:v-1];face=source[units[0].start:link.start]
                        if (not all(t.pos=='名詞' and t.has_reading for t in units)
                                or not native_spelling_only(''.join(t.reading for t in units),face)):continue
                        roles=nominal_roles(face)
                        if roles & {'cyclic_origin'}:expected='natural_cycle'
                        elif roles & {'return_state'}:expected='restored_state'
                        elif roles & {'origin'}:break
                        elif roles & {'place','country','home_destination'}:expected='homecoming'
                        if expected:begin=units[0].start;break
                elif (link.surface in ('て','で') and link.pos_sub=='接続助詞'
                        and before.pos=='動詞' and before.pos_sub=='自立'
                        and native_verb_lexemes(before.surface,before.infl_form,before.reading)&ACQUISITION_ACTIONS):
                    expected='homecoming';begin=before.start
                elif (link.surface=='が' and link.pos_sub.startswith('格助詞')
                        and nominal_roles(before.surface)&{'return_state'}):
                    expected='restored_state';begin=before.start
        # 還る is a literary spelling (かえる is outside the common-kanji
        # reading table). In ordinary prose use the usual homecoming spelling
        # when no explicit, unresolved destination supplies a different sense.
        # A normal 帰る retains this same relation for candidate validation.
        # Existing 返る or bare kana has no such familiarity anomaly by itself.
        if expected is None and not explicit_unknown and verb.base_form in ('還る','帰る'):
            expected='homecoming'
        if expected is None:continue
        frame=action_verb_frame(source,parts,v,begin,'return_action',expected,ROLES,
            '日常の帰路を既定とし、原文の行き先・状態・自然の循環で同読みの表記を選びます')
        if frame is None:continue
        if protected is None:protected=protected_ranges(source)
        if not overlaps(begin,frame['evidence_end'],protected):out.append(frame)
    return tuple(out)
