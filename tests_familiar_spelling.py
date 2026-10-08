# -*- coding: utf-8 -*-
from tests_spelling_reference import assert_reviewed_source_spelling
import unittest
from unittest.mock import patch


from morphology import HAS_JANOME

@unittest.skipUnless(HAS_JANOME, "Requires real Janome; run with the native integration suite")
class FamiliarSpellingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        cls.state=initial()

    def test_ordinary_word_fixture_retains_excluded_source_key_evidence(self):
        import contextual_repair as Q,corrector as C
        a=self.state;tk=C.make_tokenizer(a.store);source='いゅうせい'
        targets=[t for t in Q.targets_for_line(source,tk,a.store,a.dict_index)
                 if (t.start,t.end)==(0,len(source))]
        self.assertTrue(targets)
        for target in targets:
            readings=Q.reading_evidence(target,tk,a.dict_index)
            self.assertEqual({r.text for r in readings},{source})
            for reading in readings:
                for generator in (Q.key_repairs,Q.nonadjacent_key_repairs,
                                  Q.adjacent_shift_key_repairs,Q.neighbor_shift_key_repairs):
                    self.assertNotIn('しゅうせい',{r.reading for r in generator(reading.text)})
        for generator in (Q.key_repairs,Q.nonadjacent_key_repairs,
                          Q.adjacent_shift_key_repairs,Q.neighbor_shift_key_repairs):
            self.assertNotIn('し',{r.reading for r in generator('い')})
        proof=next(r for r in Q.key_repairs('とゅうせい') if r.reading=='しゅうせい')
        self.assertEqual((proof.operation,proof.position,proof.pressed,proof.intended,proof.cost),
                         ('adjacent_substitution',0,'と','し',1.0))

    def test_ordinary_word_horizontal_fixture_still_requires_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        source='とゅうせい';a=initial()
        try:
            with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')) as gate:
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None)
            self.assertTrue(any(call.args[1][:3]==(0,5,'修正') for call in gate.call_args_list))
            self.assertEqual(result['corrected'],source)
            self.assertTrue(result['odd_spans'])
            self.assertEqual(result['analysis_status'],'complete')
        finally:set_active(None)

    def test_core_repair_fixtures_keep_original_cross_row_keys(self):
        import contextual_repair as Q,corrector as C,kana_layout as L
        a=self.state;tk=C.make_tokenizer(a.store)
        rows=(('とうろくしたたんごをいちらんあ゛かくにんできます。','あ゛かく','でかく'),
              ('このぶんしょうをよんでいただけますき。','いただけますき','いただけますか'),
              ('つくえのうえをかたづめておきます。','かたづめ','かたづけ'))
        for source,span,wanted in rows:
            with self.subTest(source=source):
                targets=[t for t in Q.targets_for_line(source,tk,a.store,a.dict_index) if t.text==span]
                self.assertTrue(targets)
                for target in targets:
                    readings=Q.reading_evidence(target,tk,a.dict_index)
                    self.assertEqual({r.text for r in readings},{span})
                    for generator in (Q.key_repairs,Q.nonadjacent_key_repairs,
                                      Q.adjacent_shift_key_repairs,Q.neighbor_shift_key_repairs):
                        self.assertNotIn(wanted,{r.reading for r in generator(span)})
        # Old cross-row substitutions stay excluded; observed held outputs
        # are not completion expectations. The new inputs use real neighbors.
        for source,wanted,pressed,intended in (('い゛','で','い','て'),('す','か','す','か'),('れ','け','れ','け')):
            proof=next(r for r in Q.key_repairs(source) if r.reading==wanted)
            self.assertEqual((proof.operation,proof.position,proof.pressed,proof.intended),
                             ('adjacent_substitution',0,pressed,intended))

    def test_horizontal_core_fixture_candidates_still_use_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        for source in ('とうろくしたたんごをいちらんい゛かくにんできます。',
                       'このぶんしょうをよんでいただけますす。',
                       'つくえのうえをかたづれておきます。'):
            with self.subTest(source=source):
                a=initial()
                try:
                    with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):
                        result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                            decisions=a.decisions,context_vec=None)
                    self.assertEqual(result['corrected'],source)
                    self.assertTrue(result['odd_spans'])
                    self.assertEqual(result['analysis_status'],'complete')
                finally:set_active(None)

    def test_linked_source_action_keeps_its_object_and_later_original_reading(self):
        import contextual_repair as Q,corrector as C,reading_segments as R
        a=self.state;tk=C.make_tokenizer(a.store);source='メモをとっさて還ります。'
        targets=Q.targets_for_line(source,tk,a.store,a.dict_index)
        owner=next(t for t in targets if (t.start,t.end)==(3,6))
        target=next(t for t in targets if t.boundary_kind=='meaning_context' and (t.start,t.end)==(7,9))
        first,diag=Q.resolve(owner,C,tk,a.store,a.dict_index,a.decisions)
        self.assertEqual(first,'取っ')
        original=next(r for r in Q.reading_evidence(target,tk,a.dict_index) if r.text=='かえり')
        frames=R.native_object_predicate_contexts(target.context,allow_written_predicate=True)
        frame=next(f for f in frames if f[1]==3 and f[2]==('メモ',))
        self.assertTrue(Q._source_linked_companion_owns_object(target,frame,((3,6,'取っ'),)))
        for changes in ((),((2,6,'取っ'),),((3,7,'取っ'),),((3,6,'食っ'),),((3,6,'ぽね'),)):
            self.assertFalse(Q._source_linked_companion_owns_object(target,frame,changes))
        with patch.object(R,'native_object_predicate_proof',return_value=False):
            self.assertFalse(Q._source_linked_companion_owns_object(target,frame,((3,6,'取っ'),)))
        self.assertTrue(Q._source_linked_companion_owns_object(target,frame,((3,6,'取っ'),),'帰り'))
        self.assertFalse(Q._source_linked_companion_owns_object(target,frame,((3,6,'取っ'),),'買えれ'))
        accepted,reason=Q.validate(target,'買えれ',C,tk,a.store,a.dict_index,a.decisions,
            'かえれ',((3,6,'取っ'),),source_reading=original)
        self.assertFalse(accepted)
        self.assertEqual(Q.validate(target,'帰り',C,tk,a.store,a.dict_index,a.decisions,
            'かえり',source_reading=original),(False,'unproven_object_predicate'))
        self.assertEqual(Q.validate(target,'帰り',C,tk,a.store,a.dict_index,a.decisions,
            'かえり',((3,6,'取っ'),),source_reading=original),(True,'accepted'))
        extended,diagnostics=Q._extend_linked_source_motion_candidates(
            [owner,target],[diag,dict(candidates=[],rejected={'unproven_object_predicate':1})],
            C,tk,a.store,a.dict_index,a.decisions)
        self.assertGreater(len(extended),2)
        for t,d in zip(extended[2:],diagnostics[2:]):
            self.assertEqual(t,target);self.assertEqual(d['joint_source_dependency'][:2],(3,6))
            for row in d['candidates']:
                self.assertEqual(row['reading']['text'],'かえり')
                self.assertEqual(tuple(row['reading']['segments']),tuple(original.segments))

    def test_linked_source_motion_needs_both_original_candidates_in_joint_validation(self):
        import app,corrector as C,contextual_repair as Q
        from tests_analysis_async import initial
        from last_choice import set_active
        def run(source):
            a=initial();return app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                                decisions=a.decisions,context_vec=None)
        try:
            source='メモをとっさて還ります。'
            result=run(source)
            self.assertEqual(result['corrected'],'メモを取って帰ります。')
            self.assertFalse(result['odd_spans']);self.assertEqual(result['analysis_status'],'complete')
            with patch.object(Q,'_source_linked_companion_owns_object',return_value=False):result=run(source)
            self.assertEqual(result['corrected'],'メモを取って還ります。')
            with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):result=run(source)
            self.assertEqual(result['corrected'],source);self.assertTrue(result['odd_spans'])
            validate=Q.validate;saw=[]
            def reject(target,face,*args,**kw):
                companions=kw.get('companions',args[6] if len(args)>6 else ())
                if target.source==source and (target.start,target.end)==(7,9) and any(c[:2]==(3,6) for c in companions):
                    saw.append(companions);return False,'forced_source_companion_gate'
                return validate(target,face,*args,**kw)
            with patch.object(Q,'validate',side_effect=reject):result=run(source)
            self.assertTrue(saw);self.assertEqual(result['corrected'],'メモを取って還ります。')
            for source in ('メモを取って帰ります。','土に還ります。',
                           '「メモをとっさて還ります。」と入力します。','とっさてという文字列です。'):
                result=run(source);self.assertEqual(result['corrected'],source)
                self.assertFalse(result['odd_spans']);self.assertEqual(result['analysis_status'],'complete')
        finally:set_active(None)

    def test_nonfinite_link_retains_original_members_and_candidate_connection(self):
        import contextual_repair as Q,corrector as C,reading_segments as R
        from dataclasses import replace
        a=self.state;tk=C.make_tokenizer(a.store)
        source='荷物をもっさて自宅へ還ります。'
        target=next(t for t in Q.targets_for_line(source,tk,a.store,a.dict_index) if (t.start,t.end)==(3,7))
        reading=next(r for r in Q.reading_evidence(target,tk,a.dict_index) if r.text=='もっさて')
        def check(t=target,face='持って',r=reading,expected='もって'):
            return Q._retained_nonfinite_intrusion_link(t,face,r,expected,tk,a.store,a.dict_index)
        self.assertTrue(check())
        self.assertFalse(Q._source_te_edges(source))
        self.assertTrue(R.native_object_predicate_proof('荷物を持って',3,('荷物',),allow_link=True))
        for face,rd in (('持って','もっさて'),('持って','もっで'),('持っ','もって'),
                        ('持つ','もって'),('食って','くって'),('勝手','かって')):
            with self.subTest(face=face,reading=rd):self.assertFalse(check(face=face,expected=rd))
        for r in (replace(reading,text='もつさて'),
                  replace(reading,segments=((0,1,'もっ','literal_kana'),(1,4,'さて','literal_kana'))),
                  replace(reading,segments=((0,2,'もつ','literal_kana'),(2,4,'さて','literal_kana'))),
                  replace(reading,segments=reading.segments[:-1])):
            self.assertFalse(check(r=r))
        self.assertFalse(check(t=replace(target,anomalies=())))
        self.assertFalse(check(t=replace(target,end=target.end+1)))
        with patch.object(Q,'_marked_nonfinite_connective_intrusion_targets',return_value=[]):self.assertFalse(check())
        with patch('pos_grammar.odd_kana_spans',return_value=[]):self.assertFalse(check())
        # The original boundary is no permission to omit its own meaning.
        with patch.object(R,'native_object_predicate_proof',return_value=False):
            valid,reason=Q.validate(target,'持って',C,tk,a.store,a.dict_index,a.decisions,
                                    'もって',source_reading=reading)
        self.assertFalse(valid);self.assertEqual(reason,'unproven_object_predicate')

    def test_nonfinite_link_keeps_first_object_and_joint_original_validation(self):
        import app,corrector as C,contextual_repair as Q
        from tests_analysis_async import initial
        from last_choice import set_active
        def run(source):
            a=initial();return app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                                decisions=a.decisions,context_vec=None)
        try:
            source='荷物をもっさて自宅へ還ります。';expected='荷物を持って自宅へ帰ります。'
            result=run(source)
            with self.subTest(check='body'):self.assertEqual(result['corrected'],expected)
            with self.subTest(check='purple'):self.assertFalse(result['odd_spans'])
            self.assertEqual(result['analysis_status'],'complete')
            with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):result=run(source)
            self.assertEqual(result['corrected'],source);self.assertTrue(result['odd_spans'])
            with patch.object(Q,'_retained_nonfinite_intrusion_link',return_value=False):result=run(source)
            self.assertEqual(result['corrected'],'荷物をもっさて自宅へ帰ります。')
            self.assertTrue(result['odd_spans'])
            for source in ('荷物を持って自宅へ帰ります。','「荷物をもっさて自宅へ還ります。」と入力します。',
                           'もっさてという文字列です。'):
                with self.subTest(control=source):
                    result=run(source);self.assertEqual(result['corrected'],source)
                    self.assertFalse(result['odd_spans']);self.assertEqual(result['analysis_status'],'complete')
        finally:set_active(None)

    def test_retained_nonfinite_link_does_not_lend_later_argument_meaning(self):
        import contextual_repair as Q,corrector as C,reading_segments as R
        a=self.state;tk=C.make_tokenizer(a.store)
        source='荷物をくっさて自宅へ還ります。'
        target=next(t for t in Q.targets_for_line(source,tk,a.store,a.dict_index) if (t.start,t.end)==(3,7))
        reading=next(r for r in Q.reading_evidence(target,tk,a.dict_index) if r.text=='くっさて')
        # The source connection is attested; its own object still rejects eating.
        self.assertTrue(Q._retained_nonfinite_intrusion_link(target,'食って',reading,'くって',tk,a.store,a.dict_index))
        self.assertFalse(R.native_object_predicate_proof('荷物を食って',3,('荷物',),allow_link=True))
        accepted,reason=Q.validate(target,'食って',C,tk,a.store,a.dict_index,a.decisions,
                                   'くって',source_reading=reading)
        self.assertFalse(accepted);self.assertEqual(reason,'unproven_object_predicate')

    def test_independent_oddness_keeps_original_nonfinite_connection_scope(self):
        import contextual_repair as Q,corrector as C,pos_grammar
        a=self.state;tk=C.make_tokenizer(a.store)
        source='料理の材料をかっさて還ります。'
        def targets():return Q.targets_for_line(source,tk,a.store,a.dict_index)
        found=targets();ranges={(t.start,t.end) for t in found}
        self.assertIn((6,10),ranges);self.assertIn((6,12),ranges);self.assertIn((10,12),ranges)
        target=next(t for t in found if (t.start,t.end)==(6,10))
        self.assertEqual(target.source,source);self.assertEqual(target.text,'かっさて')
        self.assertEqual(target.anomalies,(('品詞文法','原文の動詞と未説明の接続',6,10),))
        self.assertIn('かっさて',{r.text for r in Q.reading_evidence(target,tk,a.dict_index)})
        proof=next(r for r in Q.key_repairs('かっさて') if r.reading=='かって')
        self.assertEqual((proof.operation,proof.position,proof.pressed,proof.intended),
                         ('adjacent_intrusion',2,'さ',''))
        with patch.object(Q,'_marked_nonfinite_connective_intrusion_targets',return_value=[]):
            self.assertNotIn((6,10),{(t.start,t.end) for t in targets()})
        with patch('reading_segments.native_object_predicate_contexts',return_value=()):
            self.assertNotIn((6,10),{(t.start,t.end) for t in targets()})
        unknown='ぽねをかっさて還ります。'
        unknown_targets=Q.targets_for_line(unknown,tk,a.store,a.dict_index)
        self.assertNotIn((3,7),{(t.start,t.end) for t in unknown_targets})
        self.assertIn((3,9),{(t.start,t.end) for t in unknown_targets})
        parts=tk(source);grammar=pos_grammar.odd_kana_spans(source,a.dict_index,a.store)
        self.assertFalse(Q._marked_nonfinite_connective_intrusion_targets(source,0,len(source),parts,()))
        for k,value in ((2,'かい'),(5,False),(6,'基本形')):
            changed=list(parts);index=next(i for i,t in enumerate(parts) if t[0]=='かっ')
            token=list(parts[index]);token[k]=value;changed[index]=tuple(token)
            with self.subTest(slot=k):
                self.assertFalse(Q._marked_nonfinite_connective_intrusion_targets(source,0,len(source),changed,grammar))
        changed=list(parts);index=next(i for i,t in enumerate(parts) if t[0]=='さて')
        token=list(parts[index]);token[3]+=1;changed[index]=tuple(token)
        self.assertFalse(Q._marked_nonfinite_connective_intrusion_targets(source,0,len(source),changed,grammar))
        for text in ('料理の材料をかっさて\t還ります。','前欄\t料理の材料をかっさて還ります。'):
            cut=text.index('\t')
            for t in Q.targets_for_line(text,tk,a.store,a.dict_index):
                self.assertFalse(t.start<=cut<t.end)

    def test_independent_nonfinite_repair_keeps_joint_validation_and_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        def run(source):
            a=initial();return app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                                decisions=a.decisions,context_vec=None)
        try:
            source='料理の材料をかっさて還ります。';result=run(source)
            with self.subTest(check='text'):self.assertEqual(result['corrected'],'料理の材料を買って帰ります。')
            with self.subTest(check='purple'):self.assertFalse(result['odd_spans'])
            self.assertEqual(result['analysis_status'],'complete')
            with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):result=run(source)
            self.assertEqual(result['corrected'],source);self.assertTrue(result['odd_spans'])
            # The separate return repair already exists; an unproved object
            # must not gain the new independent first-action projection.
            result=run('ぽねをかっさて還ります。')
            self.assertEqual(result['corrected'],'ぽねをかっさて帰ります。')
            self.assertEqual(result['odd_spans'],[(0,7)])
            self.assertEqual(result['analysis_status'],'complete')
            for source in ('料理の材料を買って帰ります。','「料理の材料をかっさて還ります。」と入力します。',
                           'かっさてという文字列です。'):
                with self.subTest(control=source):
                    result=run(source);self.assertEqual(result['corrected'],source)
                    self.assertFalse(result['odd_spans']);self.assertEqual(result['analysis_status'],'complete')
        finally:set_active(None)

    def test_independent_nonfinite_scope_requires_joint_companion_validation(self):
        import app,contextual_repair as Q
        from tests_analysis_async import initial
        from last_choice import set_active
        original=Q.validate;blocked=[]
        def checked(target,surface,*args,**kwargs):
            companions=kwargs.get('companions',args[6] if len(args)>6 else ())
            if ((target.start,target.end)==(6,10) and surface=='買って'
                    and (10,12,'帰り') in companions):
                blocked.append((target.source,tuple(companions)))
                return False,'forced_joint_companion'
            return original(target,surface,*args,**kwargs)
        source='料理の材料をかっさて還ります。'
        try:
            a=initial()
            with patch.object(Q,'validate',side_effect=checked):
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                        decisions=a.decisions,context_vec=None)
            self.assertTrue(blocked)
            self.assertTrue(all(text==source for text,companions in blocked))
            self.assertNotEqual(result['corrected'],'料理の材料を買って帰ります。')
        finally:set_active(None)

    def test_native_standalone_following_action_proves_grammar_not_new_meaning(self):
        import corrector as C,oddness as O,morphology as M,reading_segments as R
        from semantic_roles import classified_nominal_action,predicate_roles
        a=self.state;tok=C.make_tokenizer(a.store)
        source='場所を取らべて出発します。';parts=tok(source)
        i=next(i for i,t in enumerate(parts) if t[0]=='取ら');x,y,z=parts[i:i+3]
        def check(ts=parts):return O.native_final_particle_inside_link(x,y,z,parts[i-1],text=source,parts=ts)
        self.assertFalse(classified_nominal_action('出発','しゅっぱつ'))
        self.assertFalse(predicate_roles('出発'))
        self.assertFalse(R.native_written_relative_action('出発します',allow_finite=True))
        self.assertTrue(check())
        with patch.object(M,'native_suru_form',return_value=False):self.assertFalse(check())
        with patch('contextual_repair._allows_grammatical_tail',return_value=False):self.assertFalse(check())
        for k,value in ((2,'しゅうぱつ'),(3,parts[i+3][3]+1),(1,'名詞:一般'),(5,False)):
            changed=list(parts);t=list(changed[i+3]);t[k]=value;changed[i+3]=tuple(t)
            with self.subTest(slot=k):self.assertFalse(check(changed))
        for tail in ('出発したら','出発し','出発して','出発しで','出発しますです',
                     '駅します','ぽねします','資料を出発します','出発しますと話します',
                     'という文字列です','出発\tします'):
            source2='場所を取らべて'+tail;ts=tok(source2)
            i2=next(i for i,t in enumerate(ts) if t[0]=='取ら')
            with self.subTest(tail=tail):
                self.assertFalse(O.native_final_particle_inside_link(*ts[i2:i2+3],ts[i2-1],text=source2,parts=ts))

    def test_standalone_following_action_keeps_repair_and_common_gate_separate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        def run(source):
            a=initial();return app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                                decisions=a.decisions,context_vec=None)
        try:
            for source in ('場所を取らべて出発します。','時刻を取らべて休憩します。'):
                with self.subTest(source=source):
                    result=run(source);self.assertEqual(result['corrected'],source.replace('取らべて','調べて'))
                    self.assertFalse(result['odd_spans']);self.assertEqual(result['analysis_status'],'complete')
            source='場所を取らべて出発します。'
            with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):result=run(source)
            self.assertEqual(result['corrected'],source);self.assertTrue(result['odd_spans'])
            for source in ('場所を調べて出発します。','取らねえで出発します。','「取らべて」と入力します。'):
                with self.subTest(control=source):
                    result=run(source);self.assertEqual(result['corrected'],source)
                    self.assertFalse(result['odd_spans']);self.assertEqual(result['analysis_status'],'complete')
        finally:set_active(None)

    def test_terminal_particle_inside_link_uses_actual_source_inflection(self):
        import corrector as C,oddness as O
        a=self.state;tok=C.make_tokenizer(a.store)
        source='電車の時刻を取らべて駅へ向かいます。';parts=tok(source)
        i=next(i for i,t in enumerate(parts) if t[0]=='取ら');x,y,z=parts[i:i+3]
        def check(a,b,c,prev=None):
            return O.native_final_particle_inside_link(a,b,c,prev,text=source,parts=parts)
        self.assertTrue(check(x,y,z,parts[i-1]))
        with patch('reading_segments.native_written_relative_action',return_value=()):
            self.assertFalse(check(x,y,z,parts[i-1]))
        self.assertFalse(O.infl_mismatch(x,y,parts[i-1]))
        self.assertFalse(check(x,y,None))
        for k,value in ((2,'とり'),(3,x[3]+1),(5,False),(6,'連用形')):
            changed=list(x);changed[k]=value
            with self.subTest(slot=k):self.assertFalse(check(tuple(changed),y,z))
        changed=list(z);changed[3]+=1
        self.assertFalse(check(x,y,tuple(changed)))
        for text in ('時刻を調べて駅へ向かいます。','虎べて駅へ向かいます。',
                     '行くべ。','取らねえで待ってください。','知らねって言いました。',
                     '取ら\tべて駅へ向かいます。','取らべ','取らべてという文字列です。',
                     '取らべてぽねます。','取らべて駅へ向かい','取らべて駅へ向かいますです。'):
            ts=tok(text)
            with self.subTest(text=text):
                self.assertFalse(any(O.native_final_particle_inside_link(a,b,c,ts[n-1] if n else None,text=text,parts=ts)
                    for n,(a,b,c) in enumerate(zip(ts,ts[1:],ts[2:]))))

    def test_written_action_with_internal_final_particle_keeps_common_gate(self):
        import app,corrector as C
        from literal_examples import protected_ranges
        # Explicit written-data scope keeps the source and has no correction purple.
        self.assertEqual(protected_ranges('取らべてという文字列です。'),[(0,4)])
        from tests_analysis_async import initial
        from last_choice import set_active
        def run(source):
            a=initial();return app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                                decisions=a.decisions,context_vec=None)
        try:
            source='電車の時刻を取らべて駅へ向かいます。'
            result=run(source)
            with self.subTest(check='text'):self.assertEqual(result['corrected'],'電車の時刻を調べて駅へ向かいます。')
            with self.subTest(check='purple'):self.assertFalse(result['odd_spans'])
            self.assertEqual(result['analysis_status'],'complete')
            with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):
                result=run(source)
            self.assertEqual(result['corrected'],source);self.assertTrue(result['odd_spans'])
            for source,old_odd in (('時刻を調べて駅へ向かいます。',[]),('知らねって言いました。',[]),
                           ('取らねえで待ってください。',[]),('「取らべて」と入力します。',[]),
                           ('取らべてという文字列です。',[])):
                with self.subTest(control=source):
                    result=run(source);self.assertEqual(result['corrected'],source)
                    self.assertEqual(result['odd_spans'],old_odd);self.assertEqual(result['analysis_status'],'complete')
        finally:set_active(None)

    def test_owned_action_retains_its_literal_link_and_own_positive_argument(self):
        import contextual_repair as Q,corrector as C,reading_segments as R
        from dataclasses import replace
        s=self.state;tk=C.make_tokenizer(s.store)
        source='文章を乳りらょくして内容を確認します。'
        target=next(t for t in Q.targets_for_line(source,tk,s.store,s.dict_index)
                    if (t.start,t.end)==(3,10))
        reading=next(r for r in Q.reading_evidence(target,tk,s.dict_index)
                     if r.text=='にゅうりらょくして')
        self.assertTrue(Q.needs_source_argument_proof(reading))
        self.assertTrue(Q._retained_action_before_owned_object(target,'入力して',reading,'にゅうりょくして'))
        for face,rd in (('食べて','たべて'),('入力しで','にゅうりょくしで'),
                        ('入力し','にゅうりょくし'),('入力して','にゅうりょくしで')):
            with self.subTest(face=face,rd=rd):
                self.assertFalse(Q._retained_action_before_owned_object(target,face,reading,rd))
        for changed in (replace(reading,text=reading.text+'て'),
                replace(reading,segments=reading.segments[:-1]+((2,7,'ょくして','literal_kana'),)),
                replace(reading,segments=reading.segments[:-1]+((3,7,'ょくして','dictionary_word'),)),
                replace(reading,segments=reading.segments[:-1]+((3,7,'ょくしで','literal_kana'),))):
            self.assertFalse(Q._retained_action_before_owned_object(target,'入力して',changed,'にゅうりょくして'))
        self.assertFalse(Q._retained_action_before_owned_object(replace(target,anomalies=()),'入力して',reading,'にゅうりょくして'))
        with patch.object(Q,'_source_actions_before_owned_objects',return_value=()):
            self.assertFalse(Q._retained_action_before_owned_object(target,'入力して',reading,'にゅうりょくして'))
        with patch.object(R,'native_object_predicate_proof',return_value=False):
            self.assertFalse(Q._retained_action_before_owned_object(target,'入力して',reading,'にゅうりょくして'))
        for original in ('料理を乳りらょくして内容を確認します。',
                         '文章を乳りらょくして内容を飲みます。',
                         '文章を乳りらょくしてぽねを確認します。',
                         '文章を乳りらょくして\t内容を確認します。'):
            changed=replace(target,source=original,context_end=len(original)-1)
            with self.subTest(source=original):
                self.assertFalse(Q._retained_action_before_owned_object(changed,'入力して',reading,'にゅうりょくして'))

    def test_owned_action_before_later_object_keeps_common_gate_and_source_meaning(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        def run(source):
            state=initial()
            return app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                                    decisions=state.decisions,context_vec=None)
        try:
            source='文章を乳りらょくして内容を確認します。'
            r=run(source)
            self.assertEqual(r['corrected'],'文章を入力して内容を確認します。')
            self.assertFalse(r['odd_spans'])
            self.assertEqual(r['analysis_status'],'complete')
            with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):
                self.assertEqual(run(source)['corrected'],source)
            for source in ('文章を入力して内容を確認します。',
                    '文章を乳りらょくして内容を飲みます。','料理を乳りらょくして内容を確認します。',
                    '「文章を乳りらょくして内容を確認します。」という文字列です。'):
                with self.subTest(source=source):
                    r=run(source);self.assertEqual(r['corrected'],source)
                    self.assertEqual(r['analysis_status'],'complete')
        finally:set_active(None)

    def test_malformed_noun_run_retains_existing_native_hidden_stems(self):
        import contextual_repair as Q,corrector as C
        from dataclasses import replace
        s=self.state;tok=C.make_tokenizer(s.store)
        for source,wanted in [('原因を詰名します','つめい'),
                              ('聞いた話を纏路手文章にします。','まとろてぶんしょう')]:
            targets=Q.targets_for_line(source,tok,s.store,s.dict_index)
            target=next(t for t in targets if t.boundary_kind=='lexical'
                        and ((t.start,t.end)==(3,5) if source.startswith('原因') else (t.start,t.end)==(5,10)))
            readings=Q.reading_evidence(target,tok,s.dict_index)
            found=next(r for r in readings if r.text==wanted)
            self.assertTrue(any(seg[3]=='unrecognized_ime_sequence' for seg in found.segments))
            self.assertTrue(Q.needs_source_argument_proof(found))
            ordinary=Q.reading_evidence(replace(target,structural=False,anomalies=()),tok,s.dict_index)
            self.assertNotIn(wanted,{r.text for r in ordinary})

    def test_hidden_native_stems_keep_source_meaning_and_final_validation(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        try:
            for source,expected in [('原因を詰名します','原因を説明します'),
                                    ('聞いた話を纏路手文章にします。','聞いた話をまとめて文章にします。')]:
                with self.subTest(source=source):
                    a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                    self.assertEqual(r['corrected'],expected)
                    self.assertEqual(r['odd_spans'],[])
                    self.assertEqual(r['analysis_status'],'complete')
                    a=initial()
                    with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')):
                        r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                    self.assertEqual(r['corrected'],source)
            for source in ('話を纏めて文章にします。','書類を箱に詰めます。',
                           '「原因を詰名します」と入力します。',
                           '「聞いた話を纏路手文章にします」という文字列です。'):
                a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertEqual(r['corrected'],source)
                self.assertEqual(r['analysis_status'],'complete')
        finally:set_active(None)

    def test_hidden_stem_run_requires_its_actual_suru_tail(self):
        import contextual_repair as Q,corrector as C,app
        from tests_analysis_async import initial
        from last_choice import set_active
        s=self.state;tok=C.make_tokenizer(s.store)
        for source in ('原因を詰名したら','原因を詰名しで戻ります',
                       '原因を説明します','ぽねします'):
            targets=Q.targets_for_line(source,tok,s.store,s.dict_index)
            for target in targets:
                if target.text in ('詰名','説明','ぽね'):
                    self.assertFalse(Q._source_marked_nominal_suru_omission(target,'つめい'),source)
        try:
            source='料理を詰名します'
            a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
            self.assertEqual(r['corrected'],'料理を説明します')
            self.assertEqual(r['analysis_status'],'complete')
            source='原因を詰名したら'
            a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
            self.assertEqual(r['corrected'],source)
            self.assertEqual(r['analysis_status'],'complete')
        finally:set_active(None)

    def test_hidden_stem_composition_retains_original_whole_noun_and_reading(self):
        import contextual_repair as Q,corrector as C
        from dataclasses import replace
        a=self.state;tok=C.make_tokenizer(a.store)
        source='聞いた話を纏路手文章にします。'
        target=next(t for t in Q.targets_for_line(source,tok,a.store,a.dict_index) if (t.start,t.end)==(5,10))
        reading=next(r for r in Q.reading_evidence(target,tok,a.dict_index) if r.text=='まとろてぶんしょう')
        last=Q._marked_native_stem_nominal_tail(target,reading)
        self.assertIsNotNone(last)
        self.assertEqual((last.start,last.end,last.surface,last.reading),(3,5,'文章','ぶんしょう'))
        repair=next(r for r in Q.key_repairs(reading.text) if r.reading=='まとめてぶんしょう')
        self.assertEqual((repair.operation,repair.pressed,repair.intended),('adjacent_substitution','ろ','め'))
        forms=Q._surfaces(repair.reading,a.store,a.dict_index,compose=True,following=target.following,
             before='聞いた話を',original=target.text,source_nominal_tail=last)
        self.assertTrue({'まとめて文章','纏めて文章'} & set(forms))
        self.assertIsNone(Q._marked_native_stem_nominal_tail(replace(target,anomalies=()),reading))
        segments=reading.segments[:-1]+((2,5,'ぶんしょう','analyzed_word'),)
        self.assertIsNone(Q._marked_native_stem_nominal_tail(target,replace(reading,segments=segments)))
        self.assertIsNone(Q._marked_native_stem_nominal_tail(target,replace(reading,text='まとろてしりょう')))
        self.assertEqual(Q._surfaces('まとめてしりょう',a.store,a.dict_index,compose=True,
            following=target.following,original=target.text,source_nominal_tail=last),[])

    def test_hidden_stem_composition_still_requires_the_final_source_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        source='聞いた話を纏路手文章にします。'
        try:
            a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
            self.assertEqual(r['corrected'],'聞いた話をまとめて文章にします。')
            self.assertEqual(r['odd_spans'],[])
            with self.subTest(check='complete_search'):
                self.assertEqual(r['analysis_status'],'complete')
            a=initial()
            with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')):
                r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
            self.assertEqual(r['corrected'],source)
            for text in ('聞いた話をまとめて文章にします。','話を纏めて文章にします。',
                         '「聞いた話を纏路手文章にします」という文字列です。'):
                a=initial();r=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertEqual(r['corrected'],text)
                self.assertEqual(r['analysis_status'],'complete')
        finally:set_active(None)

    def test_bound_stem_readings_preserve_generic_hypotheses_and_weak_provenance(self):
        import contextual_repair as Q,corrector as C
        from dataclasses import replace
        a=self.state;tok=C.make_tokenizer(a.store);source='説明を纏路手資料にしました。'
        target=next(t for t in Q.targets_for_line(source,tok,a.store,a.dict_index) if t.text=='纏路手資料')
        with patch.object(Q,'_marked_native_stem_nominal_parts',return_value=()):
            ordinary=Q.reading_evidence(target,tok,a.dict_index)
        search={};token=Q._SEARCH.set(search)
        try:readings=Q.reading_evidence(target,tok,a.dict_index)
        finally:Q._SEARCH.reset(token)
        self.assertTrue({r.text for r in ordinary}<={r.text for r in readings})
        found=next(r for r in readings if r.text=='まとろてしりょう')
        self.assertTrue(Q.needs_source_argument_proof(found))
        self.assertEqual(found.segments[-1][2],'しりょう')
        self.assertIsNotNone(Q._marked_native_stem_nominal_tail(target,found))
        self.assertTrue(search['token_readings']['unexplored'])
        self.assertFalse(search['source_stem_token_readings']['unexplored'])
        self.assertEqual(search['source_stem_token_readings']['limit'],32)
        self.assertLessEqual(len(readings),64)
        unmarked=Q.reading_evidence(replace(target,structural=False,anomalies=()),tok,a.dict_index)
        self.assertNotIn('まとろてしりょう',{r.text for r in unmarked})

    def test_bound_stem_readings_keep_the_common_gate_and_search_limit_visible(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        source='説明を纏路手資料にしました。'
        try:
            a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
            self.assertEqual(r['corrected'],'説明をまとめて資料にしました。')
            self.assertEqual(r['odd_spans'],[])
            self.assertEqual(r['analysis_status'],'limited')
            self.assertTrue(any(x.get('state')=='truncated' for x in r.get('search_reports',())))
            a=initial()
            with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')):
                r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
            self.assertEqual(r['corrected'],source)
            for text in ('説明をまとめて資料にしました。','道路の資料を読みます。',
                         '「説明を纏路手資料にしました」という文字列です。'):
                a=initial();r=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertEqual(r['corrected'],text)
        finally:set_active(None)

    def test_contained_word_reuses_only_proved_original_mark_companions(self):
        import contextual_repair as Q,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();tok=C.make_tokenizer(a.store);source='飲んで゛゜から詰名します'
        try:
            targets=Q.targets_for_line(source,tok,a.store,a.dict_index)
            owner=next(t for t in targets if t.text=='詰名')
            wide=next(t for t in targets if t.text=='詰名し')
            surface,diagnostic=Q.resolve(owner,C,tok,a.store,a.dict_index,a.decisions)
            self.assertEqual(surface,'説明')
            complete=[(owner,surface,diagnostic)];proof=[]
            self.assertIsNone(Q._contained_scope_resolution(wide,complete,C,tok,a.store,a.dict_index,a.decisions))
            self.assertIsNone(Q._contained_scope_resolution(wide,complete,C,tok,a.store,a.dict_index,a.decisions,[(3,5,'で')]))
            result=Q._contained_scope_resolution(wide,complete,C,tok,a.store,a.dict_index,a.decisions,[(3,5,'')],proof)
            self.assertEqual(result,(7,9,'説明'));self.assertEqual(proof,[(3,5,'')])
            winner=next(row for row in diagnostic['candidates'] if row['surface']==surface)
            self.assertEqual(winner['reading']['segments'][0][3],'unrecognized_ime_sequence')
            with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')):
                self.assertIsNone(Q._contained_scope_resolution(wide,complete,C,tok,a.store,a.dict_index,a.decisions,[(3,5,'')]))
            with patch('mark_usage.proved_cluster_normalization',return_value=None):
                self.assertIsNone(Q._contained_scope_resolution(wide,complete,C,tok,a.store,a.dict_index,a.decisions,[(3,5,'')]))
        finally:set_active(None)

    def test_source_mark_companions_keep_final_word_and_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        source='飲んで゛゜から詰名します'
        try:
            a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
            self.assertEqual(r['corrected'],'飲んでから説明します')
            self.assertEqual(r['odd_spans'],[]);self.assertEqual(r['analysis_status'],'complete')
            a=initial()
            with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')):
                r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
            self.assertEqual(r['corrected'],source)
            for text in ('飲んでから説明します','書類を箱に詰めます',
                         '「飲んで゛゜から詰名します」という文字列です。','記号は゛゜です。'):
                a=initial();r=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertEqual(r['corrected'],text)
        finally:set_active(None)

    def test_accepted_natural_spelling_survives_finishing(self):
        import app
        s=self.state
        for source,expected in [('聞いた話を纏路手文章にします。','聞いた話をまとめて文章にします。'),
                                ('話を纏めて文章にします。','話を纏めて文章にします。'),
                                ('「纏路手」という文字列','「纏路手」という文字列')]:
            with self.subTest(source=source):
                r=app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,decisions=s.decisions,context_vec=None)
                self.assertEqual(expected,r['corrected'])
                self.assertFalse(r.get('odd_spans'))
                self.assertNotEqual('incomplete',r.get('analysis_status'))

    def test_same_native_inflection_and_explicit_choice(self):
        from familiar_spelling import prefers_kana
        from kana_spelling import project
        for face,reading in [('纏め','まとめ'),('躊躇う','ためらう'),('頷い','うなずい')]:
            with self.subTest(face=face):self.assertTrue(prefers_kana(face,reading))
        self.assertFalse(prefers_kana('微笑み','ほほえみ'))
        self.assertFalse(prefers_kana('頷い','うなづい'))
        s=self.state
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:'纏め' if rd=='まとめ' else None):
            result=project('話をまとめて文章にします',s.store,s.dict_index,s.decisions)
        self.assertIsNotNone(result)
        self.assertEqual('話を纏めて文章にします',result[0])

    def test_native_connective_keeps_source_noun_and_ordinary_spelling(self):
        import app,corrector
        from repaired_spelling import finish
        s=self.state
        for source,expected in [
                ('聞いた話をまとめる手文章にします。','聞いた話をまとめて文章にします。'),
                ('聞いた話をまとめる文章にします。','聞いた話をまとめる文章にします。'),
                ('聞いた話をまとめて文章にします。','聞いた話をまとめて文章にします。'),
                ('話を纏めて文章にします。','話を纏めて文章にします。')]:
            with self.subTest(source=source):
                r=app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,decisions=s.decisions,context_vec=None)
                self.assertEqual(expected,r['corrected'])
                self.assertFalse(r.get('odd_spans'))
                self.assertEqual('complete',r.get('analysis_status'))
        # A synthetic remembered spelling checks this finishing contract only;
        # it does not load or exercise the user's stopped learning pipeline.
        source='聞いた話をまとめる手文章にします。'
        proposed='聞いた話を纏めて文章にします。'
        result=dict(corrected=proposed,changed=True,analysis_status='complete',
                    _repair_surfaces=[(5,12,'纏めて文章','lexical')])
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:'纏めて' if rd=='まとめて' else None):
            kept=finish(source,result,s.store,corrector.make_tokenizer(s.store),s.dict_index,s.decisions)
        self.assertEqual(proposed,kept['corrected'])

    def test_source_connective_frame_overrides_unbacked_tail_frequency(self):
        import app
        s=self.state
        for source,expected in [
                ('説明をまとめる手資料にします。','説明をまとめて資料にします。'),
                ('話をまとめる手文章にする。','話をまとめて文章にする。'),
                ('契約をまとめる手腕が必要だ。','契約をまとめる手腕が必要だ。'),
                ('データを集める手作業を減らす。','データを集める手作業を減らす。'),
                ('紙を切る手が震える。','紙を切る手が震える。'),
                ('紙資料を読む。','紙資料を読む。'),
                ('音資料を集める。','音資料を集める。'),
                ('「説明をまとめる手資料」という文字列','「説明をまとめる手資料」という文字列')]:
            with self.subTest(source=source):
                r=app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,decisions=s.decisions,context_vec=None)
                self.assertEqual(expected,r['corrected'])
                self.assertFalse(r.get('odd_spans'))
                self.assertEqual('complete',r.get('analysis_status'))


    def test_general_action_and_explicit_role_choose_different_words(self):
        import app
        s=self.state
        for source,expected in [
                ('詰名します','説明します'),
                ('飲んで゛゜から詰名します','飲んでから説明します'),
                ('原因を詰名します','原因を説明します'),
                ('新しい機械を発明する','新しい機械を発明する'),
                ('事故で失明した','事故で失明した'),
                ('「詰名します」という文字列','「詰名します」という文字列')]:
            with self.subTest(source=source):
                r=app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,
                                   decisions=s.decisions,context_vec=None)
                self.assertEqual(expected,r['corrected'])
                self.assertFalse(r.get('odd_spans'))
                self.assertEqual('complete',r.get('analysis_status'))

    def test_explicit_person_role_keeps_horizontal_and_excludes_vertical_keys(self):
        import app,contextual_repair as Q
        s=self.state
        self.assertIn('しめいします',{r.reading for r in Q.key_repairs('しめすします')})
        for generator in (Q.key_repairs,Q.nonadjacent_key_repairs):
            self.assertNotIn('しめいします',{r.reading for r in generator('しめうします')})
        for prefix in ('担当者を','次の回答者を'):
            with self.subTest(prefix=prefix):
                r=app.correct_line(prefix+'しめすします',s.store,input_method='kana',dict_index=s.dict_index,
                    decisions=s.decisions,context_vec=None)
                self.assertEqual(r['corrected'],prefix+'指名します')
                self.assertFalse(r['odd_spans'])
                self.assertEqual(r['analysis_status'],'complete')
                r=app.correct_line(prefix+'しめうします',s.store,input_method='kana',dict_index=s.dict_index,
                    decisions=s.decisions,context_vec=None)
                self.assertEqual(r['corrected'],prefix+'しめうします')
                self.assertTrue(r['odd_spans'])
                self.assertEqual(r['analysis_status'],'complete')

    def test_native_written_variant_keeps_the_actual_verb_and_noun_readings(self):
        import app,corrector as C,contextual_repair as Q
        from tests_analysis_async import initial
        from last_choice import set_active
        try:
            source='予定を書く人しました。';a=initial();tok=C.make_tokenizer(a.store)
            target=next(t for t in Q.targets_for_line(source,tok,a.store,a.dict_index)
                        if t.text=='書く人')
            reading=next(r for r in Q.reading_evidence(target,tok,a.dict_index)
                         if r.text=='かくにん')
            self.assertEqual(tuple((x[0],x[1],x[2]) for x in reading.segments),
                             ((0,2,'かく'),(2,3,'にん')))
            self.assertNotIn(reading.source,('current_ime_occurrence','saved_ime_pair'))
            for source in ('予定を書く人がいます。','話を聞く人がいます。',
                           '頭を掻く人がいます。','「予定を書く人しました。」という文字列です。'):
                with self.subTest(source=source):
                    a=initial();r=app.correct_line(source,a.store,input_method='kana',
                        dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                    self.assertEqual(r['corrected'],source)
                    self.assertEqual(r['odd_spans'],[])
                    self.assertEqual(r['analysis_status'],'complete')
        finally:set_active(None)

    def test_excluded_hearing_key_keeps_original_source_and_common_gate(self):
        import app,corrector as C,contextual_repair as Q
        from tests_analysis_async import initial
        from last_choice import set_active
        for reading,expected in (('きくひと','かくにん'),('きくにん','かくにん'),
                                 ('きくじん','かくにん'),('きくひとし','かくにんし'),
                                 ('きくにんし','かくにんし'),('きくじんし','かくにんし')):
            for generator in (Q.key_repairs,Q.nonadjacent_key_repairs,
                              Q.adjacent_shift_key_repairs,Q.neighbor_shift_key_repairs):
                with self.subTest(reading=reading,generator=generator.__name__):
                    self.assertNotIn(expected,{r.reading for r in generator(reading)})
        try:
            source='予定を聞く人しました。';a=initial()
            r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                               decisions=a.decisions,context_vec=None)
            self.assertEqual(r['corrected'],source)
            self.assertTrue(r['odd_spans'])
            self.assertEqual(r['analysis_status'],'complete')
            a=initial();source='予定を書く人しました。'
            with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')):
                r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                   decisions=a.decisions,context_vec=None)
            self.assertEqual(r['corrected'],source)
            self.assertEqual(r['analysis_status'],'complete')
        finally:set_active(None)

    def test_ime_attestation_keeps_other_native_readings_and_spelling_candidates(self):
        import app
        s=self.state
        for source,expected in [
                ('予定を書く人しました。','予定を確認しました。'),
                ('文章を乳りらょくして内容を確認します。','文章を入力して内容を確認します。'),
                ('話を聞く人がいます。','話を聞く人がいます。')]:
            with self.subTest(source=source):
                r=app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,
                                   decisions=s.decisions,context_vec=None)
                self.assertEqual(expected,r['corrected'])
                self.assertFalse(r.get('odd_spans'))
                self.assertEqual('complete',r.get('analysis_status'))

    def test_excluded_material_key_keeps_original_past_boundary_and_common_gate(self):
        import app,corrector as C,contextual_repair as Q
        from tests_analysis_async import initial
        from last_choice import set_active
        for generator in (Q.key_repairs,Q.nonadjacent_key_repairs,
                          Q.adjacent_shift_key_repairs,Q.neighbor_shift_key_repairs):
            self.assertNotIn('しょくざい',{r.reading for r in generator('いょくざい')})
        for reading,pressed in (('とょくざい','と'),('はょくざい','は')):
            proof=next(r for r in Q.key_repairs(reading) if r.reading=='しょくざい')
            self.assertEqual((proof.operation,proof.position,proof.pressed,proof.intended),
                             ('adjacent_substitution',0,pressed,'し'))
        try:
            source='店で買ったいょく材を冷蔵庫に入れます。';a=initial();tk=C.make_tokenizer(a.store)
            target=next(t for t in Q.targets_for_line(source,tk,a.store,a.dict_index)
                        if t.text=='いょく材')
            self.assertEqual((target.start,target.end),(5,9))
            readings=Q.reading_evidence(target,tk,a.dict_index)
            self.assertIn('いょくざい',{r.text for r in readings})
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                    decisions=a.decisions,context_vec=None)
            self.assertEqual(result['corrected'],source)
            self.assertTrue(result['odd_spans'])
            self.assertEqual(result['analysis_status'],'complete')
            source='店で買ったとょく材を冷蔵庫に入れます。';a=initial()
            with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                        decisions=a.decisions,context_vec=None)
            self.assertEqual(result['corrected'],source)
            self.assertEqual(result['analysis_status'],'complete')
            for source in ('店で買った食材を冷蔵庫に入れます。',
                           '「店で買ったとょく材を冷蔵庫に入れます。」という文字列です。'):
                with self.subTest(source=source):
                    a=initial();result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                                      decisions=a.decisions,context_vec=None)
                    self.assertEqual(result['corrected'],source)
                    self.assertFalse(result['odd_spans'])
                    self.assertEqual(result['analysis_status'],'complete')
        finally:set_active(None)

    def test_original_ime_word_edges_retain_complete_neighbors(self):
        import app
        s=self.state
        for source,expected in [
                ('必要なしはょ類を送信しました。','必要な書類を送信しました。'),
                ('わたしはょ類を送信しました。','私は書類を送信しました。'),
                ('店で買ったとょく材を冷蔵庫に入れます。','店で買った食材を冷蔵庫に入れます。'),
                ('集めた資料をならぺ手内容を比べます。','集めた資料を並べて内容を比べます。'),
                ('集めて資料をならぺ手内容を比べます。','集めて資料を並べて内容を比べます。'),
                ('わたしは書類を送信しました。','わたしは書類を送信しました。'),
                ('食べたい料理を選びます。','食べたい料理を選びます。'),
                ('読みたい資料を選びます。','読みたい資料を選びます。')]:
            with self.subTest(source=source):
                r=app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,
                                   decisions=s.decisions,context_vec=None)
                assert_reviewed_source_spelling(self, r['corrected'], expected)
                self.assertFalse(r.get('odd_spans'))
                self.assertEqual('complete',r.get('analysis_status'))

    def test_marked_lexical_tail_is_read_in_original_suru_context(self):
        import app
        s=self.state
        for source,expected in [
                ('故障の原因を背詰めてしてから修理します。','故障の原因を説明してから修理します。'),
                ('故障の原因を背詰めていしてから修理します。','故障の原因を説明してから修理します。'),
                ('書類を箱に詰めて仕事をします。','書類を箱に詰めて仕事をします。'),
                ('よく考えてします。','よく考えてします。')]:
            with self.subTest(source=source):
                r=app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,
                                   decisions=s.decisions,context_vec=None)
                self.assertEqual(expected,r['corrected'])
                self.assertFalse(r.get('odd_spans'))
                self.assertEqual('complete',r.get('analysis_status'))

    def test_written_candidate_cannot_borrow_a_different_reading_object(self):
        import app
        state=self.state
        for source,expected in (
                ('詳しい説明をきういてください。','詳しい説明を聞いてください。'),
                ('説明を打ってください。','説明を打ってください。'),
                ('木を伐ってください。','木を伐ってください。'),
                ('紙を切ってください。','紙を切ってください。'),
                ('予定を書く人しました。','予定を確認しました。')):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')
        # These inputs still need a stronger key hypothesis for 聞いて.
        # Do not freeze today's unchanged output as a permanent protection.
        for source,bad in (
                ('詳しい説明をきっいてください。',('詳しい説明を切ってください。','詳しい説明を伐ってください。')),
                ('説明をきっいてください。',('説明を切ってください。','説明を伐ってください。'))):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertNotIn(result['corrected'],bad)
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_original_case_and_unchanged_return_choose_natural_action(self):
        import app
        state=self.state
        for source,expected in (
                ('店で本をかっさて帰ります。','店で本を買って帰ります。'),
                ('家族に本をかとて帰ります。','家族に本を貸して帰ります。'),
                ('棚に本を貸さて帰ります。','棚に本を重ねて帰ります。'),
                ('切手をかっさて帰ります。','切手を買って帰ります。'),
                ('道具をかっさて戻ります。','道具を買って戻ります。'),
                ('料理の材料をかっさて帰ります。','料理の材料を買って帰ります。'),
                ('道具を借りて戻ります。','道具を借りて戻ります。'),
                ('家族に本を貸して帰ります。','家族に本を貸して帰ります。'),
                ('道具をさて置いて帰ります。','道具をさて置いて帰ります。'),
                ('彼をばかって呼びます。','彼をばかって呼びます。'),
                ('「かさて」と書いてあります。','「かさて」と書いてあります。')):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                assert_reviewed_source_spelling(self, result['corrected'], expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_stamp_purchase_fixture_keeps_original_key_evidence_and_common_gate(self):
        import app,corrector as C,contextual_repair as Q
        old='切手を貸さて帰ります。'
        source='切手をかっさて帰ります。'
        a=self.state;tk=C.make_tokenizer(a.store)
        target=next(t for t in Q.targets_for_line(old,tk,a.store,a.dict_index)
                    if (t.start,t.end)==(3,5))
        self.assertEqual(target.text,'貸さ')
        readings=Q.reading_evidence(target,tk,a.dict_index)
        self.assertEqual({r.text for r in readings},{'かさ'})
        self.assertTrue(all(r.segments==((0,2,'かさ','analyzed_word'),) for r in readings))
        for generator in (Q.key_repairs,Q.nonadjacent_key_repairs,
                          Q.adjacent_shift_key_repairs,Q.neighbor_shift_key_repairs):
            for reading,wanted in (('かさ','かっ'),('かさて','かって')):
                with self.subTest(generator=generator.__name__,reading=reading):
                    self.assertNotIn(wanted,{r.reading for r in generator(reading)})
        proof=next(r for r in Q.key_repairs('かっさて') if r.reading=='かって')
        self.assertEqual((proof.operation,proof.position,proof.pressed,proof.intended),
                         ('adjacent_intrusion',2,'さ',''))
        # The preceding whole method already checks this exact completed
        # purchase once. The excluded source keeps its own reading contract;
        # its observed 重ねて output is not a replacement expectation.
        with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                    decisions=a.decisions,context_vec=None)
        self.assertEqual(result['corrected'],source)
        self.assertTrue(result['odd_spans'])
        self.assertEqual(result['analysis_status'],'complete')
        for text in ('切手を買って帰ります。',
                     '「切手を貸さて帰ります。」という文字列です。',
                     '「切手をかっさて帰ります。」という文字列です。'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                                        decisions=a.decisions,context_vec=None)
                self.assertEqual(result['corrected'],text)
                self.assertFalse(result['odd_spans'])
                self.assertEqual(result['analysis_status'],'complete')

    def test_voiced_nominal_key_uses_same_row_and_original_whole_scope(self):
        import app,corrector as C,contextual_repair as Q
        from tests_analysis_async import initial
        from last_choice import set_active
        for generator in (Q.key_repairs,Q.nonadjacent_key_repairs,
                          Q.adjacent_shift_key_repairs,Q.neighbor_shift_key_repairs):
            for old,goal in (('がばう','がぞう'),('がばうをほぞんします','がぞうをほぞんします')):
                with self.subTest(generator=generator.__name__,reading=old):
                    self.assertNotIn(goal,{r.reading for r in generator(old)})
        proof=next(r for r in Q.key_repairs('がびう') if r.reading=='がぞう')
        self.assertEqual((proof.operation,proof.position,proof.pressed,proof.intended),
                         ('adjacent_substitution',2,'ひ','そ'))
        try:
            for source,expected in (('がばうをほぞんします。','がばうをほぞんします。'),
                                    ('がびうをほぞんします。','画像を保存します。')):
                with self.subTest(source=source):
                    a=initial();tk=C.make_tokenizer(a.store)
                    targets=Q.targets_for_line(source,tk,a.store,a.dict_index)
                    self.assertTrue(any((t.start,t.end,t.text)==(0,10,source[:-1]) for t in targets))
                    target=next(t for t in targets if (t.start,t.end)==(0,3))
                    self.assertEqual({r.text for r in Q.reading_evidence(target,tk,a.dict_index)},{source[:3]})
                    result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                            decisions=a.decisions,context_vec=None)
                    self.assertEqual(result['corrected'],expected)
                    self.assertEqual(result['odd_spans'],[(0,10)] if source.startswith('がばう') else [])
                    self.assertEqual(result['analysis_status'],'complete')
            source='がびうをほぞんします。';a=initial()
            with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                        decisions=a.decisions,context_vec=None)
            self.assertEqual(result['corrected'],source)
            self.assertEqual(result['analysis_status'],'complete')
            for source in ('画像を保存します。','「がびうをほぞんします。」という文字列です。'):
                with self.subTest(source=source):
                    a=initial();result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                                      decisions=a.decisions,context_vec=None)
                    self.assertEqual(result['corrected'],source)
                    self.assertFalse(result['odd_spans'])
                    self.assertEqual(result['analysis_status'],'complete')
        finally:set_active(None)

    def test_excluded_loan_keys_keep_written_native_inflection_and_source(self):
        import app,corrector as C,contextual_repair as Q
        from tests_analysis_async import initial
        from last_choice import set_active
        for generator in (Q.key_repairs,Q.nonadjacent_key_repairs,
                          Q.adjacent_shift_key_repairs,Q.neighbor_shift_key_repairs):
            for source,goals in (('かさ',('かっ','かし')),('かさて',('かって','かして'))):
                with self.subTest(generator=generator.__name__,source=source):
                    readings={r.reading for r in generator(source)}
                    for goal in goals:self.assertNotIn(goal,readings)
        try:
            for source,original in (('店で本を貸さて帰ります。','貸さ'),
                                    ('家族に本を貸さて帰ります。','貸さ'),
                                    ('道具をかさて戻ります。','かさ'),
                                    ('料理の材料をかさて帰ります。','かさ')):
                with self.subTest(source=source):
                    a=initial();tk=C.make_tokenizer(a.store)
                    target=next(t for t in Q.targets_for_line(source,tk,a.store,a.dict_index)
                                if t.text==original)
                    start=source.index(original)
                    self.assertEqual((target.start,target.end),(start,start+len(original)))
                    self.assertEqual({r.text for r in Q.reading_evidence(target,tk,a.dict_index)},{'かさ'})
                    result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                            decisions=a.decisions,context_vec=None)
                    self.assertEqual(result['corrected'],source)
                    self.assertTrue(result['odd_spans'])
                    self.assertEqual(result['analysis_status'],'complete')
        finally:set_active(None)

    def test_purchase_intrusion_and_lending_left_right_keep_common_gate(self):
        import app,corrector as C,contextual_repair as Q
        from tests_analysis_async import initial
        from last_choice import set_active
        for source,goal,expected in (
                ('かっさて','かって',('adjacent_intrusion',2,'さ','')),
                ('かとて','かして',('adjacent_substitution',1,'と','し'))):
            proof=next(r for r in Q.key_repairs(source) if r.reading==goal)
            self.assertEqual((proof.operation,proof.position,proof.pressed,proof.intended),expected)
        try:
            for source in ('店で本をかっさて帰ります。','家族に本をかとて帰ります。'):
                with self.subTest(source=source):
                    a=initial()
                    with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):
                        result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                                decisions=a.decisions,context_vec=None)
                    self.assertEqual(result['corrected'],source)
                    self.assertEqual(result['analysis_status'],'complete')
            for source in ('店で本を買って帰ります。','家族に本を貸して帰ります。',
                           '「店で本をかっさて帰ります。」という文字列です。',
                           '「家族に本をかとて帰ります。」という文字列です。'):
                with self.subTest(source=source):
                    a=initial();result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                                      decisions=a.decisions,context_vec=None)
                    self.assertEqual(result['corrected'],source)
                    self.assertFalse(result['odd_spans'])
                    self.assertEqual(result['analysis_status'],'complete')
        finally:set_active(None)

    def test_two_physical_events_and_the_same_yoon_anomaly(self):
        import app,kana_layout as K
        from contextual_repair import key_repairs,neighbor_shift_key_repairs
        self.assertNotIn('かっ',{r.reading for r in neighbor_shift_key_repairs('かさ')})
        self.assertNotIn('かっ',{r.reading for r in key_repairs('かさ')})
        self.assertIn('かつ',{r.reading for r in key_repairs('かさ')})
        self.assertIn('かっ',{r.reading for r in key_repairs('かつ')})
        self.assertEqual(K.kana_key_distance('さ','っ'),K.FAR)
        state=self.state
        for source,expected in (
                ('古い設定をさくじゅして保存します。','古い設定を削除して保存します。'),
                ('りゅうり','料理'),
                ('つょい','強い'),('風がつょい','風がつよい'),
                ('つよい','つよい'),('だょね','だょね')):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertIn(result['corrected'],(expected,'風が強い') if expected=='風がつよい' else (expected,))
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_distant_shifted_particle_does_not_authorize_neighbor_case_change(self):
        import app
        state=self.state
        for source,forbidden in (('ゅみを聞きます。','読みを聞きます。'),
                ('ゅ役を演じます。','予約を演じます。'),
                ('彼女のゅ味を聞きます。','彼女の読みを聞きます。'),
                ('彼はゅ役を演じます。','彼は予約を演じます。')):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',
                    dict_index=state.dict_index,decisions=state.decisions,context_vec=None)
                self.assertNotEqual(result['corrected'],forbidden)
                self.assertEqual(result['analysis_status'],'complete')

    def test_written_nominal_after_modifier_keeps_its_exact_boundary(self):
        import app,reading_segments as R,contextual_repair as Q,corrector as C
        state=self.state
        for modifier in ('静かな','しずかな','安全な','あんぜんな'):
            with self.subTest(modifier=modifier):
                source=modifier+'しはゃ両を選びます。';start=len(modifier)
                self.assertEqual(R.native_surface_nominal_heads(modifier+'車両'),('車両',))
                self.assertTrue(Q.object_predicate_candidate_allowed(source,start,start+4,'車両'))
        source='静かなしはゃ両を選びます。'
        result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
            decisions=state.decisions,context_vec=None)
        self.assertEqual(result['corrected'],'静かな車両を選びます。')
        self.assertFalse(result['odd_spans']);self.assertEqual(result['analysis_status'],'complete')
        with patch.object(C,'_check_replacement',return_value=(None,'test_shared_gate')):
            blocked=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                decisions=state.decisions,context_vec=None)
        self.assertNotEqual(blocked['corrected'],'静かな車両を選びます。')
        for text in ('静かなし車両','静かなぷねら','静かな走ります','ぷねらな車両'):
            with self.subTest(unproved=text):self.assertFalse(R.native_written_adnominal_parts(text))
        for text in ('静かな車両を選びます。','安全な車両を選びます。',
                     '「静かなしはゃ両を選びます」と入力します。'):
            with self.subTest(preserved=text):
                result=app.correct_line(text,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],text)

    def test_written_modifier_is_kept_before_an_unknown_noun(self):
        import app,reading_segments as R,corrector as C
        state=self.state
        for source,head in (('静かなぽねです。','静かな'),('貴重なぷねらです。','貴重な')):
            with self.subTest(source=source):
                self.assertIn((0,len(head)),R.native_adnominal_modifier_ranges(source))
                self.assertFalse(R.preserves_native_adnominal_modifier(source,0,len(head),head[:-1]+'ん'))
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],source)
                self.assertEqual(result['analysis_status'],'complete')
        for source in ('必要なしです。','貴重な資料を保存します。','「静かんぽね」と入力します。'):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],source)
        self.assertFalse(R.native_adnominal_modifier_parts('ぷねらな',allow_written=True))

    def test_genitive_projection_keeps_the_original_complete_token(self):
        import reading_segments as R,contextual_repair as Q
        source='会議のしはょ類を送信します。'
        self.assertEqual(R.native_genitive_nominal_splits('会議のし',original_context=source),())
        self.assertEqual(R.native_surface_nominal_heads('会議のし',original_context=source),())
        self.assertEqual(R.native_surface_nominal_heads('会議のし',original_context='資料の本'),())
        self.assertNotIn(5,Q._native_marked_prefix_edges('会議のしはょ類を送信します。'))
        for source in ('会議の詩','資料の表','本の栞'):
            self.assertTrue(R.native_surface_nominal_heads(source),source)
        for source in ('ものさし','いのしし','きのこ'):
            self.assertEqual(R.native_genitive_nominal_splits(source),(),source)

    def test_genitive_left_noun_survives_the_next_malformed_parse(self):
        import app,corrector as C,contextual_repair as Q,reading_segments as R
        from unittest.mock import patch
        state=self.state;tok=C.make_tokenizer(state.store)
        source='会議のしはょ類を送信します。'
        targets=Q.targets_for_line(source,tok,state.store,state.dict_index)
        self.assertTrue(any(t.text=='しはょ類' and (t.start,t.end)==(3,7) for t in targets))
        for source in ('会議の書類を送信します。','仕事の種類を確認します。',
                       '「会議のしはょ類を送信します。」と入力します。'):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],source)
                self.assertFalse(result['odd_spans'])
        self.assertFalse(R.native_surface_nominal_heads('ぷねら'))
        source='会議のしはょ類を送信します。'
        with patch.object(C,'_check_replacement',return_value=(None,'forced_reject')):
            result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                decisions=state.decisions,context_vec=None)
        self.assertEqual(result['corrected'],source)
        self.assertTrue(result['odd_spans'])

    def test_native_modifier_and_marked_syllable_share_original_boundaries(self):
        import app,reading_segments as R,contextual_repair as Q,corrector as C
        from unittest.mock import patch
        state=self.state;tok=C.make_tokenizer(state.store)
        for head in ('必要な','大切な','新しい','かんたんな'):
            self.assertTrue(R.native_adnominal_modifier_parts(head,allow_written=True),head)
        for head in ('必要なし','大切なし','ぷねらな','必要ます','新しいた'):
            self.assertFalse(R.native_adnominal_modifier_parts(head,allow_written=True),head)
        source='必要なしはょ類を送信しました。'
        targets=Q.targets_for_line(source,tok,state.store,state.dict_index)
        self.assertTrue(any((t.start,t.end)==(3,7) and t.text=='しはょ類' for t in targets))
        for source,expected in ((source,'必要な書類を送信しました。'),
                ('大切なしはょ類を保管します。','大切な書類を保管します。')):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result['odd_spans'])
                self.assertEqual(result['analysis_status'],'complete')
        for source in ('必要なしです。','大切なぷねらです。','かんたんなぽねです。',
                       '「必要なしはょ類を送信しました。」と入力します。'):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],source)
        source='必要なしはょ類を送信しました。'
        with patch.object(C,'_check_replacement',return_value=(None,'forced_reject')):
            result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                decisions=state.decisions,context_vec=None)
        self.assertEqual(result['corrected'],source)
        self.assertTrue(result['odd_spans'])

    def test_original_modifiers_leave_the_same_marked_word_for_repair(self):
        import app
        state=self.state
        for source,expected in (
                ('すごくつょいです','すごく強いです'),
                ('小さくてつょい','小さくて強い'),
                ('とってもつょい','とっても強い'),
                ('もっともつょい','もっとも強い'),
                ('この道具はつょい','この道具は強い'),
                ('これもつょい','これも強い'),
                ('母の声はつょい','母の声は強い'),
                ('この道具は小さくてつょい','この道具は小さくて強い'),
                ('明日のしばゅんびを済ませて早く寝ます。','明日の準備を済ませて早く寝ます。')):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_native_final_particle_reading_is_shared_without_changing_intent(self):
        import app,morphology as M
        state=self.state
        for source in ('行くょ！','あるょね','それだょね','あるょねえ',
                       '食事をするょ','作業をするょね','しょくじをするよ'):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                assert_reviewed_source_spelling(self, result['corrected'], source)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')
        self.assertEqual(M.colloquial_particle_normal_form('とってもつょい'),'とってもつょい')
        self.assertEqual(M.colloquial_particle_normal_form('すふょ'),'すふょ')
        self.assertEqual(M.colloquial_particle_normal_form('行くょね'),'行くよね')

    def test_coordinated_noun_and_unadorned_process_use_source_meaning(self):
        import app
        state=self.state
        for source,expected in (
                ('小さくて鉄製の箱','小さくて鉄製の箱'),
                ('大きくて木製の机','大きくて木製の机'),
                ('軽くて金属製の道具','軽くて金属製の道具'),
                ('古い設定を素削除して保存します。','古い設定を削除して保存します。'),
                ('設定を素削除します。','設定を削除します。'),
                ('素画像を表示します。','素画像を表示します。'),
                ('素通りします。','素通りします。'),
                ('図を素描します。','図を素描します。'),
                ('書類を素読みします。','書類を素読みします。')):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_return_fixture_keeps_original_reading_and_intrusion_contract(self):
        import app,contextual_repair as Q,corrector as C
        old='料理の材料を貸さて還ります。'
        source='料理の材料をかっさて還ります。'
        a=self.state;tk=C.make_tokenizer(a.store)
        targets=Q.targets_for_line(old,tk,a.store,a.dict_index)
        target=next(t for t in targets if (t.start,t.end)==(6,8))
        self.assertEqual(old[target.start:target.end],'貸さ')
        readings=Q.reading_evidence(target,tk,a.dict_index)
        self.assertEqual({r.text for r in readings},{'かさ'})
        self.assertTrue(all(r.segments==((0,2,'かさ','analyzed_word'),) for r in readings))
        for generator in (Q.key_repairs,Q.nonadjacent_key_repairs,
                          Q.adjacent_shift_key_repairs,Q.neighbor_shift_key_repairs):
            for reading,wanted in (('かさ','かっ'),('かさて','かって')):
                with self.subTest(generator=generator.__name__,reading=reading):
                    self.assertNotIn(wanted,{r.reading for r in generator(reading)})
        proof=next(r for r in Q.key_repairs('かっさて') if r.reading=='かって')
        self.assertEqual((proof.operation,proof.position,proof.pressed,proof.intended),
                         ('adjacent_intrusion',2,'さ',''))
        # Do not make the old 重ねて output a new positive expectation.
        # The return test below keeps the original completed sentence.
        with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                    decisions=a.decisions,context_vec=None)
        self.assertEqual(result['corrected'],source)
        self.assertTrue(result['odd_spans'])
        self.assertEqual(result['analysis_status'],'complete')
        for text in ('料理の材料を買って帰ります。',
                     '「料理の材料を貸さて還ります。」という文字列です。',
                     '「料理の材料をかっさて還ります。」という文字列です。'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                                        decisions=a.decisions,context_vec=None)
                self.assertEqual(result['corrected'],text)
                self.assertFalse(result['odd_spans'])
                self.assertEqual(result['analysis_status'],'complete')

    def test_return_spelling_uses_ordinary_meaning_and_actual_destination(self):
        import app
        state=self.state
        for source,expected in (
                ('料理の材料をかっさて還ります。', '料理の材料を買って帰ります。'),
                ('家に還ります。', '家に帰ります。'),
                ('自宅へ還る。', '自宅へ帰る。'),
                ('国へ還る。', '国へ帰る。'),
                ('正気にかえる。', '正気に返る。'),
                ('我に帰った。', '我に返った。'),
                ('土に帰る。', '土に還る。'),
                ('自然に還る。', '自然に還る。'),
                ('本を返します。', '本を返します。'),
                ('新しい設定に変えます。', '新しい設定に変えます。'),
                ('「還る」という表記を使う。', '「還る」という表記を使う。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_native_coordination_retains_context_without_erasing_default_sense(self):
        import app
        state=self.state
        for source,expected in (('日本の線と中国の線', '日本の線と中国の線'), ('日本の線や中国の線', '日本の線や中国の線'), ('日本の線', '二本の線'), ('にほんの線', '二本の線'), ('机の脚と椅子の背', '机の脚と椅子の背')):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_stranded_object_leaves_the_return_verb_as_context(self):
        import app
        state=self.state
        for source,expected in (
                ('荷物をもっさて帰ります。', '荷物を持って帰ります。'),
                ('メモをとっさて帰ります。', 'メモを取って帰ります。'),
                ('荷物をもっさて帰った。', '荷物を持って帰った。'),
                ('荷物をもって帰ります。', '荷物をもって帰ります。'),
                ('荷物を持ち、さて帰ります。', '荷物を持ち、さて帰ります。'),
                ('仕事をさておいて休みます。', '仕事をさておいて休みます。'),
                ('彼は「荷物をもさて帰る」と誤入力した。', '彼は「荷物をもさて帰る」と誤入力した。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_final_particle_needs_a_real_text_boundary(self):
        import app
        state=self.state
        for source,expected in (('必要なしはょ類を送信しました。', '必要な書類を送信しました。'), ('会議のしはょ類を送信します。', '会議の書類を送信します。'), ('するょ、またね。', 'するょ、またね。'), ('「あるょ」と返事する。', '「あるょ」と返事する。')):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_completed_past_requires_a_real_action_link(self):
        import app
        state=self.state
        for source,expected in (
                ('料理の材料を買った帰りますよ。', '料理の材料を買って帰りますよ。'),
                ('料理の材料を買ってた帰ります。', '料理の材料を買って帰ります。'),
                ('本を読んだ戻りますね。', '本を読んで戻りますね。'),
                ('料理を食べた寝ます。', '料理を食べて寝ます。'),
                ('本を買っていた帰りますよ。', '本を買っていて帰りますよ。'),
                ('料理の材料を買った還ります。', '料理の材料を買って帰ります。'),
                ('本を買った帰り道ですよ。', '本を買った帰り道ですよ。'),
                ('本を買った。帰ります。', '本を買った。帰ります。'),
                ('料理を食べたくなりました。', '料理を食べたくなりました。'),
                ('「買った帰ります」と誤入力した。', '「買った帰ります」と誤入力した。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_repeated_completed_utterance_has_its_own_original_syntax(self):
        import app
        state=self.state
        for source,expected in (
                ('分かった分かった。', '分かった分かった。'),
                ('やったやった。', 'やったやった。'),
                ('読んだ読んだよ。', '読んだ読んだよ。'),
                ('見た見た見た。', '見た見た見た。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_photo_meaning_ranks_repaired_action_with_unchanged_context(self):
        import app
        state=self.state
        for source,expected in (
                ('写真をとっさて帰りますよ。', '写真を撮って帰りますよ。'),
                ('メモをとっさて帰ります。', 'メモを取って帰ります。'),
                ('写真を取って机に置く。', '写真を取って机に置く。'),
                ('写真を取ってファイルに保存します。', '写真を撮ってファイルに保存します。'),
                ('写真をは撮って帰ります。', '写真を貼って帰ります。'),
                ('写真を貼って帰ります。', '写真を貼って帰ります。'),
                ('糸を張って帰ります。', '糸を張って帰ります。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_later_motion_does_not_own_a_content_object(self):
        import app
        state=self.state
        for source,expected in (
                ('道を入って帰ります。', '道を入って帰ります。'),
                ('写真の中を歩きます。', '写真の中を歩きます。'),
                ('写真を入った箱に貼ります。', '写真を入った箱に貼ります。'),
                ('本を読んで帰ります。', '本を読んで帰ります。'),
                ('データを進めて確認します。', 'データを進めて確認します。'),
                ('感覚が冴えて帰ります。', '感覚が冴えて帰ります。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_rejects_intransitive_escape_without_claiming_a_complete_repair(self):
        import app
        for source,expected,unresolved in (('メモをとさえて帰ります。','メモをとさえて帰ります。',True),
                ('写真を走って帰ります。','写真を貼って帰ります。',False)):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(bool(result.get('odd_spans')),unresolved)

    def test_finite_predicate_shares_actual_final_particle_readings(self):
        from contextual_repair import _finite_written_predicate
        for text in ('帰りますよ','帰るょ','帰りたいよ','帰れないね','買ったよ','帰るよねえ'):
            self.assertTrue(_finite_written_predicate(text),text)
        for text in ('帰るには','帰りよ','買って位置帰ります','買った帰り道'):
            self.assertFalse(_finite_written_predicate(text),text)

    def test_marked_kana_onset_uses_same_semantics_as_written_onset(self):
        import app
        state=self.state
        for source,expected in (
                ('写真をはとって帰ります。', '写真を貼って帰ります。'),
                ('切手をはとって帰ります。', '切手を貼って帰ります。'),
                ('写真をとって帰ります。', '写真を撮って帰ります。'),
                ('切手をはって帰ります。', '切手をはって帰ります。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_written_usage_and_motion_keep_contextual_counterexamples(self):
        import app
        state=self.state
        for source,expected in (
                ('事情を聰って帰ります。', '事情を悟って帰ります。'),
                ('コンクリートをはつります。', 'コンクリートをはつります。'),
                ('床を這って進みます。', '床を這って進みます。'),
                ('苦労を厭わない。', '苦労を厭わない。'),
                ('その人を伊良部と呼びます。', 'その人を伊良部と呼びます。'),
                ('彼を太郎て呼びます。', '彼を太郎て呼びます。'),
                ('伊良部って誰ですか。', '伊良部って誰ですか。'),
                ('駅には行きます。', '駅には行きます。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_stranded_object_retains_destination_and_physical_type(self):
        import app
        state=self.state
        for source,expected in (
                ('荷物をもっさて駅へ向かいます。', '荷物を持って駅へ向かいます。'),
                ('写真をとっさて空港へ行きます。', '写真を撮って空港へ行きます。'),
                ('切手をもっさて帰ります。', '切手を持って帰ります。'),
                ('テープをもっさて駅へ向かいます。', 'テープを持って駅へ向かいます。'),
                ('荷物を持ち、さて駅へ向かいます。', '荷物を持ち、さて駅へ向かいます。'),
                ('仕事をさておいて休みます。', '仕事をさておいて休みます。'),
                ('ホームを歩いて帰ります。', 'ホームを歩いて帰ります。'),
                ('図面を入った入口に貼ります。', '図面を入った入口に貼ります。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_native_inflection_keeps_explicit_usage_without_borrowing_a_homophone(self):
        from kango_tier import candidate_usage_tier
        self.assertEqual(candidate_usage_tier('聰っ'),3)
        self.assertEqual(candidate_usage_tier('覚っ'),3)
        self.assertEqual(candidate_usage_tier('悟っ'),2)
        self.assertEqual(candidate_usage_tier('貼っ'),1)
        self.assertIsNone(candidate_usage_tier('分類していない綴り'))

    def test_movement_fixtures_keep_horizontal_keys_and_excluded_old_reading(self):
        import app,contextual_repair as Q,corrector as C
        from tests_analysis_async import initial
        from kana_layout import kana_key_distance
        self.assertEqual(kana_key_distance('と','し'),1.0)
        self.assertGreater(kana_key_distance('い','し'),1.0)
        for generator in (Q.key_repairs,Q.nonadjacent_key_repairs,
                          Q.adjacent_shift_key_repairs,Q.neighbor_shift_key_repairs):
            self.assertFalse(any(row.reading=='しらべて' for row in generator('いらべて')))
        self.assertTrue(any(row.reading=='しらべて' and row.operation=='adjacent_substitution'
                            for row in Q.key_repairs('とらべて')))
        for source in ('時刻をいらべて駅へ向かいます。','資料をいらべて帰ります。'):
            with self.subTest(source=source):
                a=initial()
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None)
                self.assertEqual(result['corrected'],source)
                self.assertTrue(result['odd_spans'])
                self.assertEqual(result['analysis_status'],'complete')
        source='「時刻をとらべて駅へ向かいます」と入力しました。';a=initial()
        result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
            decisions=a.decisions,context_vec=None)
        self.assertEqual(result['corrected'],source)
        source='時刻をとらべて駅へ向かいます。';a=initial()
        with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                decisions=a.decisions,context_vec=None)
        self.assertNotEqual(result['corrected'],'時刻を調べて駅へ向かいます。')
        self.assertTrue(result['odd_spans'])

    def test_marked_kana_action_retains_the_original_following_movement(self):
        import app
        for source,expected in (
                ('時刻をとらべて駅へ向かいます。','時刻を調べて駅へ向かいます。'),
                ('資料をとらべて帰ります。','資料を調べて帰ります。'),
                ('時刻をしらべて駅へ向かいます。','時刻をしらべて駅へ向かいます。'),
                ('時間をかけて駅へ向かいます。','時間をかけて駅へ向かいます。')):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',
                    dict_index=self.state.dict_index,decisions=self.state.decisions,context_vec=None)
                assert_reviewed_source_spelling(self, result['corrected'], expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')
        import contextual_repair as Q,corrector as C
        source='時刻をいらべて\t駅へ向かいます。'
        targets=Q.targets_for_line(source,C.make_tokenizer(self.state.store),self.state.store,self.state.dict_index)
        self.assertTrue(targets)
        self.assertTrue(all('\t' not in t.context for t in targets))

    def test_classified_following_clause_does_not_lend_its_meaning_to_the_first_action(self):
        import corrector as C,contextual_repair as Q,oddness as O
        a=self.state;source='経路を虎べて内容を確認します。';tok=C.make_tokenizer(a.store)
        self.assertTrue(O.native_original_following_clause(source,6,len(source),tok(source)))
        target=next(t for t in Q.targets_for_line(source,tok,a.store,a.dict_index) if (t.start,t.end,t.text)==(3,5,'虎べ'))
        self.assertEqual(Q._source_owned_action_contexts(target),((0,3,('経路',)),))
        from dataclasses import replace
        import morphology as M
        self.assertFalse(Q._source_owned_action_contexts(replace(target,end=target.end-1)))
        self.assertFalse(Q._source_owned_action_contexts(replace(target,start=target.start+1)))
        self.assertFalse(Q._source_owned_action_contexts(replace(target,structural=False)))
        native=M.tokenize;lexicon=M.dictionary_inflections
        def changed_tokens(text):
            tokens=native(text)
            for token in tokens:
                if text==target.context and token.start==target.end-target.context_start:token.reading='で'
            return tokens
        with patch.object(M,'tokenize',side_effect=changed_tokens):
            self.assertFalse(Q._source_owned_action_contexts(target))
        with patch.object(M,'dictionary_inflections',side_effect=lambda text:() if text=='て' else lexicon(text)):
            self.assertFalse(Q._source_owned_action_contexts(target))
        gate=C._check_replacement;validate=Q.validate;gates=[];checks=[]
        def checked(line,replacement,*args,**kwargs):
            result=gate(line,replacement,*args,**kwargs)
            if replacement[2]=='調べ':gates.append(result[0] is not None)
            return result
        def validated(t,surface,*args,**kwargs):
            result=validate(t,surface,*args,**kwargs)
            if surface=='調べ':checks.append(result)
            return result
        with patch.object(C,'_check_replacement',side_effect=checked),patch.object(Q,'validate',side_effect=validated):
            selected,diagnostic=Q.resolve(target,C,tok,a.store,a.dict_index,a.decisions)
        self.assertIsNone(selected);self.assertIn(True,gates)
        self.assertIn((False,'unproven_object_predicate'),checks)

    def test_irrealis_temporal_edge_is_shared_by_the_owned_action_target(self):
        import contextual_repair as Q,corrector as C,particle_frames as P,oddness as O
        a=self.state;source='時刻を取らべてから内容を確認します。';tk=C.make_tokenizer(a.store)
        targets=Q.targets_for_line(source,tk,a.store,a.dict_index)
        self.assertTrue(any((t.start,t.end)==(3,6) for t in targets))
        self.assertFalse(any((t.start,t.end)==(3,9) for t in targets))
        for t in targets:
            if (t.start,t.end)==(3,6):
                self.assertEqual(t.following,'てから内容を確認します')
                self.assertEqual(Q._source_owned_action_contexts(t),((0,3,('時刻',)),))
        for module,name,value in ((P,'_native_te_kara_end',None),(O,'native_final_particle_inside_link',False)):
            with patch.object(module,name,return_value=value):
                targets=Q.targets_for_line(source,tk,a.store,a.dict_index)
            with self.subTest(proof=name):self.assertTrue(any((t.start,t.end)==(3,9) for t in targets))
        # A causal past connection is an independent original relation.
        source='時刻を取らべたから内容を確認します。'
        self.assertFalse(any(t.following.startswith('てから') for t in Q.targets_for_line(source,tk,a.store,a.dict_index)))

    def test_irrealis_te_kara_link_binds_both_original_particle_views(self):
        import corrector as C,oddness as O,morphology as M,particle_frames as P
        source='時刻を取らべてから内容を確認します。'
        tk=C.make_tokenizer(self.state.store);parts=tk(source)
        i=next(i for i,t in enumerate(parts) if t[0]=='取ら');a,b,link,after=parts[i:i+4]
        def check(ts=parts,z=link):
            return O.native_final_particle_inside_link(a,b,z,parts[i-1],text=source,parts=ts)
        with patch.object(O,'native_original_following_clause',wraps=O.native_original_following_clause) as proof:
            self.assertTrue(check())
            self.assertEqual(proof.call_args.args,(source,after[4],M.source_column_bounds(source,a[3],after[4])[1],parts))
        with patch.object(P,'_native_te_kara_end',return_value=None):self.assertFalse(check())
        with patch.object(O,'native_original_following_clause',return_value=False):self.assertFalse(check())
        with patch.object(O,'infl_mismatch',return_value=False):self.assertFalse(check())
        for slot,value in ((0,'まで'),(1,'名詞:一般'),(2,'まで'),(3,after[3]+1),
                           (4,after[4]+1),(5,False),(6,'基本形')):
            changed=list(parts);token=list(after);token[slot]=value;changed[i+3]=tuple(token)
            with self.subTest(slot=slot):self.assertFalse(check(changed))
        self.assertFalse(check(parts[:i+3]+parts[i+4:]))
        changed=list(link);changed[2]='で';self.assertFalse(check(z=tuple(changed)))
        lexicon=M.dictionary_inflections
        with patch.object(M,'dictionary_inflections',side_effect=lambda text:() if text=='から' else lexicon(text)):
            self.assertFalse(check())
        for tail in ('ぽねを確認します。','水を保存します。','内容を確認して',
                     '内容を確認しますです。','から内容を確認します。','。','\t内容を確認します。'):
            text='時刻を取らべてから'+tail;ts=tk(text);j=next(j for j,t in enumerate(ts) if t[0]=='取ら')
            with self.subTest(tail=tail):
                self.assertFalse(O.native_final_particle_inside_link(*ts[j:j+3],ts[j-1],text=text,parts=ts))
        text='時刻を取らべてまで内容を確認します。';ts=tk(text);j=next(j for j,t in enumerate(ts) if t[0]=='取ら')
        self.assertFalse(O.native_final_particle_inside_link(*ts[j:j+3],ts[j-1],text=text,parts=ts))

    def test_irrealis_te_kara_repair_retains_shared_gate_and_original_controls(self):
        import app,corrector as C
        a=self.state
        def run(text):return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        for tail in ('内容を確認します。','駅へ向かいます。'):
            source='時刻を取らべてから'+tail
            with self.subTest(tail=tail):
                r=run(source);self.assertEqual(r['corrected'],'時刻を調べてから'+tail)
                self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
                with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):r=run(source)
                self.assertEqual(r['corrected'],source);self.assertTrue(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
        for text in ('時刻を調べてから内容を確認します。','荷物を取ってから駅へ向かいます。',
                     '取らねえで待ってください。','行くべ。','「時刻を取らべてから内容を確認します。」と入力します。',
                     '取らべてからという文字列です。'):
            with self.subTest(control=text):
                r=run(text);self.assertEqual(r['corrected'],text);self.assertFalse(r['odd_spans'])
                self.assertEqual(r['analysis_status'],'complete')

    def test_irrealis_te_kara_keeps_first_object_validation_after_common_gate(self):
        import contextual_repair as Q,corrector as C
        a=self.state;source='経路を取らべてから内容を確認します。';tk=C.make_tokenizer(a.store)
        target=next(t for t in Q.targets_for_line(source,tk,a.store,a.dict_index) if (t.start,t.end)==(3,6))
        self.assertEqual(Q._source_owned_action_contexts(target),((0,3,('経路',)),))
        gate=C._check_replacement;validate=Q.validate;gates=[];checks=[]
        def checked(line,replacement,*args,**kwargs):
            result=gate(line,replacement,*args,**kwargs)
            if replacement[2]=='調べ':gates.append(result[0] is not None)
            return result
        def validated(t,surface,*args,**kwargs):
            result=validate(t,surface,*args,**kwargs)
            if surface=='調べ':checks.append(result)
            return result
        with patch.object(C,'_check_replacement',side_effect=checked),patch.object(Q,'validate',side_effect=validated):
            selected,diagnostic=Q.resolve(target,C,tk,a.store,a.dict_index,a.decisions)
        self.assertIsNone(selected);self.assertIn(True,gates)
        self.assertIn((False,'unproven_object_predicate'),checks)

    def test_original_te_kara_boundary_keeps_exact_native_particles(self):
        import copy,morphology as M,particle_frames as P,oddness as O
        source='時刻を虎べてから内容を確認します。'
        parts=M.tokenize(source);link=next(t for t in parts if t.surface=='て')
        after=next(t for t in parts if t.start==link.end)
        self.assertEqual(P._native_te_kara_end(source,link,parts),8)
        self.assertEqual(P.broken_nominal_te_frames(source),(dict(start=3,end=6,noun='虎',link='て'),))
        original=O.native_original_following_clause
        with patch.object(O,'native_original_following_clause',wraps=original) as proof:
            self.assertTrue(P.broken_nominal_te_frames(source))
            self.assertEqual(proof.call_args.args[:3],(source,after.end,M.source_column_bounds(source,3,link.end)[1]))
            self.assertEqual(proof.call_args.args[3],[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),
                t.reading,t.start,t.end,t.has_reading,t.infl_form) for t in parts])
        with patch.object(O,'native_original_following_clause',return_value=False):
            self.assertFalse(P.broken_nominal_te_frames(source))
        for which,attr,value in ((0,'reading','で'),(0,'has_reading',False),(0,'pos_sub','格助詞:連語'),
                                 (1,'reading','まで'),(1,'base_form','まで'),(1,'start',7),
                                 (1,'pos','名詞'),(1,'infl_form','基本形')):
            tokens=[copy.copy(t) for t in parts]
            t=next(t for t in tokens if t.start==(link.start if which==0 else after.start));setattr(t,attr,value)
            changed_link=next(t for t in tokens if t.surface=='て')
            with self.subTest(which=which,attr=attr):
                self.assertIsNone(P._native_te_kara_end(source,changed_link,tokens))
        lexicon=M.dictionary_inflections
        with patch.object(M,'dictionary_inflections',side_effect=lambda text:() if text=='から' else lexicon(text)):
            self.assertIsNone(P._native_te_kara_end(source,link,parts))
        for text in ('時刻を虎べてからぽねを確認します。','時刻を虎べてから内容を確認して',
                     '時刻を虎べてから内容を確認しますです。','時刻を虎べてから水を保存します。',
                     '時刻を虎べてからから内容を確認します。','時刻を虎べてから。',
                     '時刻を虎べてから\t内容を確認します。','時刻を虎べてまで内容を確認します。',
                     '「時刻を虎べてから内容を確認します。」と入力します。',
                     '虎べてからという文字列です。','時刻を調べてから内容を確認します。'):
            with self.subTest(control=text):self.assertFalse(P.broken_nominal_te_frames(text))

    def test_original_te_kara_link_retains_repair_and_common_gate(self):
        import app,corrector as C
        a=self.state
        def run(text):return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        for tail in ('内容を確認します。','駅へ向かいます。'):
            source='時刻を虎べてから'+tail
            with self.subTest(tail=tail):
                result=run(source);self.assertEqual(result['corrected'],'時刻を調べてから'+tail)
                self.assertFalse(result['odd_spans']);self.assertEqual(result['analysis_status'],'complete')
                with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):result=run(source)
                self.assertEqual(result['corrected'],source);self.assertTrue(result['odd_spans'])
                self.assertEqual(result['analysis_status'],'complete')
        for text in ('時刻を調べてから内容を確認します。','「時刻を虎べてから内容を確認します。」と入力します。',
                     '虎べてからという文字列です。','虎だべ。'):
            with self.subTest(control=text):
                result=run(text);self.assertEqual(result['corrected'],text)
                self.assertFalse(result['odd_spans']);self.assertEqual(result['analysis_status'],'complete')

    def test_original_te_kara_link_keeps_first_object_obligation(self):
        from dataclasses import replace
        import morphology as M,contextual_repair as Q,corrector as C,particle_frames as P
        a=self.state;source='経路を虎べてから内容を確認します。';tk=C.make_tokenizer(a.store)
        target=next(t for t in Q.targets_for_line(source,tk,a.store,a.dict_index) if (t.start,t.end)==(3,5))
        self.assertEqual(Q._source_owned_action_contexts(target),((0,3,('経路',)),))
        with patch.object(P,'_native_te_kara_end',return_value=None):self.assertFalse(Q._source_owned_action_contexts(target))
        self.assertFalse(Q._source_owned_action_contexts(replace(target,structural=False)))
        self.assertFalse(Q._source_owned_action_contexts(replace(target,end=target.end-1)))
        gate=C._check_replacement;validate=Q.validate;gates=[];checks=[]
        def checked(line,replacement,*args,**kwargs):
            result=gate(line,replacement,*args,**kwargs)
            if replacement[2]=='調べ':gates.append(result[0] is not None)
            return result
        def validated(t,surface,*args,**kwargs):
            result=validate(t,surface,*args,**kwargs)
            if surface=='調べ':checks.append(result)
            return result
        with patch.object(C,'_check_replacement',side_effect=checked),patch.object(Q,'validate',side_effect=validated):
            selected,diagnostic=Q.resolve(target,C,tk,a.store,a.dict_index,a.decisions)
        self.assertIsNone(selected);self.assertIn(True,gates)
        self.assertIn((False,'unproven_object_predicate'),checks)

    def test_following_action_noun_keeps_its_own_finite_suffix_and_arguments(self):
        import corrector as C,oddness as O,reading_segments as R,particle_frames as P
        source='時刻を虎べて内容を確認します。';parts=C.make_tokenizer(self.state.store)(source)
        def proof(ts=parts):return O.native_original_following_clause(source,6,len(source),ts)
        self.assertEqual(R.native_written_relative_action('内容を確認します',allow_finite=True),('確認',('を',)))
        self.assertTrue(proof())
        self.assertEqual(P.broken_nominal_te_frames(source),(dict(start=3,end=6,noun='虎',link='て'),))
        with patch.object(R,'native_written_relative_action',return_value=()):self.assertFalse(proof())
        with patch.object(R,'native_written_relative_action',return_value=('保存',('を',))):self.assertFalse(proof())
        with patch('contextual_repair._finite_written_predicate',return_value=False):self.assertFalse(proof())
        i=next(i for i,t in enumerate(parts) if t[0]=='確認')
        for slot,value in ((0,'保存'),(2,'ほぞん'),(3,10),(1,'名詞:一般'),(5,False)):
            altered=list(parts);token=list(altered[i]);token[slot]=value;altered[i]=tuple(token)
            with self.subTest(slot=slot):self.assertFalse(proof(altered))
        for tail in ('ぽねを確認します','水を保存します','内容を確認して','内容を確認したら',
                     '内容を確認しますです','という文字列です','資料を出発します'):
            text='時刻を虎べて'+tail;tokens=C.make_tokenizer(self.state.store)(text)
            with self.subTest(tail=tail):
                self.assertFalse(O.native_original_following_clause(text,6,len(text),tokens))
                self.assertFalse(P.broken_nominal_te_frames(text))
        for text in ('時刻を虎べて\t内容を確認します。','時刻を虎べて内容を\t確認します。',
                     '「時刻を虎べて内容を確認します。」と入力します。',
                     '時刻を調べて内容を確認します。','虎べてという文字列です。'):
            with self.subTest(control=text):self.assertFalse(P.broken_nominal_te_frames(text))

    def test_nominal_and_irrealis_links_keep_later_objects_out_of_the_first_action(self):
        import app,corrector as C,oddness as O
        a=self.state
        def run(text):return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        for source in ('時刻を虎べて内容を確認します。','時刻を取らべて内容を確認します。'):
            with self.subTest(source=source):
                result=run(source)
                self.assertEqual(result['corrected'],'時刻を調べて内容を確認します。')
                self.assertFalse(result['odd_spans']);self.assertEqual(result['analysis_status'],'complete')
                with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):result=run(source)
                self.assertEqual(result['corrected'],source);self.assertTrue(result['odd_spans'])
                self.assertEqual(result['analysis_status'],'complete')
        with patch.object(O,'native_original_following_clause',return_value=False):
            self.assertEqual(run('時刻を虎べて内容を確認します。')['corrected'],'時刻を虎べて内容を確認します。')
        for text in ('時刻を調べて内容を確認します。','「時刻を虎べて内容を確認します。」と入力します。',
                     '虎べてという文字列です。','虎だべ。'):
            with self.subTest(control=text):
                result=run(text);self.assertEqual(result['corrected'],text)
                self.assertFalse(result['odd_spans']);self.assertEqual(result['analysis_status'],'complete')

    def test_nominal_terminal_following_sahen_uses_exact_source_grammar(self):
        import corrector as C,oddness as O,morphology as M,particle_frames as P
        source='場所を虎べて出発します。';a=self.state;parts=C.make_tokenizer(a.store)(source)
        start=6
        def proof(ts=parts):return O.native_original_following_clause(
            source,start,len(source),ts,standalone_only=True)
        self.assertTrue(proof())
        self.assertEqual(P.broken_nominal_te_frames(source),(dict(start=3,end=6,noun='虎',link='て'),))
        with patch.object(M,'native_suru_form',return_value=False):self.assertFalse(proof())
        with patch('contextual_repair._allows_grammatical_tail',return_value=False):self.assertFalse(proof())
        i=next(i for i,t in enumerate(parts) if t[0]=='出発')
        for slot,value in ((2,'しゅうぱつ'),(3,start+1),(1,'名詞:一般'),(5,False)):
            changed=list(parts);member=list(changed[i]);member[slot]=value;changed[i]=tuple(member)
            with self.subTest(slot=slot):self.assertFalse(proof(changed))
        for tail in ('出発したら','出発して','出発し','出発しで','出発しますです',
                     'ぽねします','駅します','資料を出発します','出発しますと話します'):
            with self.subTest(tail=tail):self.assertFalse(P.broken_nominal_te_frames('場所を虎べて'+tail))
        for text in ('場所を虎べて\t出発します。','場所を虎べて出発\tします。',
                     '場所を虎べてという文字列です。','「場所を虎べて出発します。」と入力します。',
                     '場所を調べて出発します。','虎だべ。'):
            with self.subTest(control=text):self.assertFalse(P.broken_nominal_te_frames(text))

    def test_nominal_terminal_sahen_keeps_repair_and_common_gate(self):
        import app,corrector as C,oddness as O
        a=self.state
        def run(text):
            return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                                    decisions=a.decisions,context_vec=None)
        source='場所を虎べて出発します。'
        result=run(source)
        self.assertEqual(result['corrected'],'場所を調べて出発します。')
        self.assertFalse(result['odd_spans']);self.assertEqual(result['analysis_status'],'complete')
        with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):result=run(source)
        self.assertEqual(result['corrected'],source);self.assertTrue(result['odd_spans'])
        self.assertEqual(result['analysis_status'],'complete')
        with patch.object(O,'native_original_following_clause',return_value=False):result=run(source)
        self.assertEqual(result['corrected'],source)
        for text in ('場所を調べて出発します。','「場所を虎べて出発します。」と入力します。',
                     '虎べてという文字列です。','虎だべ。'):
            with self.subTest(control=text):
                result=run(text);self.assertEqual(result['corrected'],text)
                self.assertFalse(result['odd_spans']);self.assertEqual(result['analysis_status'],'complete')

    def test_written_nominal_terminal_link_keeps_exact_original_members(self):
        import copy,morphology as M,particle_frames as P
        source='電車の時刻を虎べて駅へ向かいます。'
        parts=M.tokenize(source)
        i=next(i for i,t in enumerate(parts) if t.surface=='虎')
        noun,terminal,link=parts[i:i+3]
        self.assertTrue(P._native_nominal_terminal_te(source,noun,terminal,link))
        self.assertEqual(P.broken_nominal_te_frames(source),(
            dict(start=6,end=9,noun='虎',link='て'),))
        for index,attr,value in ((0,'reading','こ'),(0,'start',7),(0,'has_reading',False),
                                  (0,'pos','動詞'),(0,'base_form','虎子'),
                                  (1,'reading','ね'),(1,'pos_sub','係助詞'),
                                  (2,'start',7),(2,'pos_sub','格助詞:連語')):
            changed=[copy.copy(t) for t in (noun,terminal,link)]
            setattr(changed[index],attr,value)
            with self.subTest(index=index,attr=attr):
                self.assertFalse(P._native_nominal_terminal_te(source,*changed))
        # Denial must remove both independent original-clause proofs.
        # The general proof also reads this unchanged native movement;
        # a denied provider is not a denial of the actual original clause.
        import oddness as O,reading_segments as R
        original=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                   t.start,t.end,t.has_reading,t.infl_form) for t in parts]
        field=M.source_column_bounds(source,noun.start,link.end)
        expected=(dict(start=6,end=9,noun='虎',link='て'),)
        self.assertTrue(P._following_native_motion(source[link.end:]))
        self.assertTrue(O.native_original_following_clause(source,link.end,field[1],original))
        self.assertFalse(O.native_original_following_clause(source,link.end,field[1],original,standalone_only=True))
        with patch.object(P,'_following_native_motion',return_value=False):
            with patch.object(O,'native_original_following_clause',wraps=O.native_original_following_clause) as following:
                self.assertEqual(P.broken_nominal_te_frames(source),expected)
                following.assert_called_once_with(source,link.end,field[1],original)
            with patch.object(R,'native_written_relative_action',return_value=()):
                self.assertFalse(P.broken_nominal_te_frames(source))
            with patch.object(O,'native_original_following_clause',return_value=False):
                self.assertFalse(P.broken_nominal_te_frames(source))
        with patch.object(O,'native_original_following_clause',return_value=False):
            self.assertEqual(P.broken_nominal_te_frames(source),expected)
        for text in ('電車の時刻を調べて駅へ向かいます。','その人を虎と呼びます。',
                     '虎だべ。','時刻をぽねべて駅へ向かいます。',
                     '時刻を虎べて','時刻を虎べて駅へ向かい',
                     '時刻を虎べて駅へ向かいますです。','時刻を虎べてぽねへ向かいます。',
                     '時刻を虎べてという文字列です。','「時刻を虎べて駅へ向かいます。」と入力します。',
                     '時刻を虎べて\t駅へ向かいます。'):
            with self.subTest(text=text):self.assertFalse(P.broken_nominal_te_frames(text))

    def test_written_nominal_terminal_link_retains_physical_meaning_and_common_gate(self):
        import app,contextual_repair as Q,corrector as C
        source='電車の時刻を虎べて駅へ向かいます。'
        a=self.state;tk=C.make_tokenizer(a.store)
        target=next(t for t in Q.targets_for_line(source,tk,a.store,a.dict_index)
                    if (t.start,t.end,t.text)==(6,8,'虎べ'))
        readings=Q.reading_evidence(target,tk,a.dict_index)
        self.assertIn('とらべ',{r.text for r in readings})
        route=next(r for r in Q.key_repairs('とらべ') if r.reading=='しらべ')
        self.assertEqual((route.operation,route.position,route.pressed,route.intended),
                         ('adjacent_substitution',0,'と','し'))
        result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                decisions=a.decisions,context_vec=None)
        self.assertEqual(result['corrected'],'電車の時刻を調べて駅へ向かいます。')
        self.assertFalse(result['odd_spans']);self.assertEqual(result['analysis_status'],'complete')
        with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                    decisions=a.decisions,context_vec=None)
        self.assertEqual(result['corrected'],source);self.assertTrue(result['odd_spans'])
        self.assertEqual(result['analysis_status'],'complete')
        for text in ('電車の時刻を調べて駅へ向かいます。','その人を虎と呼びます。',
                     '「電車の時刻を虎べて駅へ向かいます。」と入力します。',
                     '虎べてという文字列です。'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                                        decisions=a.decisions,context_vec=None)
                self.assertEqual(result['corrected'],text)
                self.assertFalse(result['odd_spans']);self.assertEqual(result['analysis_status'],'complete')

    def test_written_nominal_link_recovers_an_exact_ime_source_reading(self):
        import app
        source='電車の時刻を伊良部て駅へ向かいます。'
        result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
            decisions=self.state.decisions,context_vec=None)
        self.assertEqual(result['corrected'],'電車の時刻を調べて駅へ向かいます。')
        self.assertFalse(result.get('odd_spans'))

    def test_motion_relation_is_independent_of_neighboring_fields(self):
        import app
        for source,expected in (
                ('荷物をもっさて駅へ向かいます。\t別の欄です。', '荷物を持って駅へ向かいます。\t別の欄です。'),
                ('別の欄です。\t荷物をもっさて駅へ向かいます。', '別の欄です。\t荷物を持って駅へ向かいます。'),
                ('荷物をもっさて駅へ向かいます。\t荷物を捨てて駅へ向かいます。', '荷物を持って駅へ向かいます。\t荷物を捨てて駅へ向かいます。'),
                ('荷物をもっさて駅へ向かいます。⇒荷物を捨てて駅へ向かいます。', '荷物を持って駅へ向かいます。⇒荷物を捨てて駅へ向かいます。'),
                ('荷物をもっさて駅へ向かいます。次の文です。', '荷物を持って駅へ向かいます。次の文です。'),
                ('写真を走って帰ります。\t別の欄です。', '写真を貼って帰ります。\t別の欄です。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_original_rare_action_compares_same_native_reading_and_inflection(self):
        import app
        for source,expected in (
                ('事情を聰って帰ります。', '事情を悟って帰ります。'),
                ('事情を覚って帰ります。', '事情を悟って帰ります。'),
                ('彼は真実を聰った。', '彼は真実を悟った。'),
                ('事情を聰りません。', '事情を悟りません。'),
                ('すべてを覚れば分かる。', 'すべてを悟れば分かる。'),
                ('彼は真実をさとった。', '彼は真実を悟った。'),
                ('コンクリートをはつります。', 'コンクリートをはつります。'),
                ('本の内容を覚える。', '本の内容を覚える。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_spelling_report_names_the_exact_rare_spelling(self):
        import app
        for source,expected in (
                ('「聰って」と表記する。', '「聰って」と表記する。'),
                ('「覚る」と表記しました。', '「覚る」と表記しました。'),
                ('「聰る」と表記しない。', '「聰る」と表記しない。'),
                ('「聰って」と言った。', '「悟って」と言った。'),
                ('事情を聰って帰ります。\t「聰って」と表記する。', '事情を悟って帰ります。\t「聰って」と表記する。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_accusative_onset_does_not_reinterpret_other_particle_collisions(self):
        import app
        for source,expected in (
                ('かくにんしてた', '確認してた'),
                ('写真をはとって帰ります。', '写真を貼って帰ります。'),
                ('切手をはとって帰ります。', '切手を貼って帰ります。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                assert_reviewed_source_spelling(self, result['corrected'], expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_exact_explicit_spelling_precedes_general_familiarity(self):
        import app
        for reading,face,source in (('さとっ','聰っ','事情を聰って帰ります。'),
                ('さとって','聰って','事情を聰って帰ります。')):
            with self.subTest(reading=reading), patch('last_choice.surface_for_reading',
                    side_effect=lambda rd:face if rd==reading else None):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],source)
                self.assertFalse(result.get('odd_spans'))

    def test_rare_nominal_sense_uses_ordinary_action_argument(self):
        import app
        for source,expected in (
                ('思料を印刷します。', '資料を印刷します。'),
                ('必要な思量を送ります。', '必要な資料を送ります。'),
                ('会議の思料を配布します。', '会議の資料を配布します。'),
                ('会議の思料を印刷して帰ります。', '会議の資料を印刷して帰ります。'),
                ('そのように思料します。', 'そのように思料します。'),
                ('慎重に思量する。', '慎重に思量する。'),
                ('深い思量を重ねます。', '深い思量を重ねます。'),
                ('彼の思料を説明します。', '彼の思料を説明します。'),
                ('資料を印刷します。', '資料を印刷します。'),
                ('飼料を購入します。', '飼料を購入します。'),
                ('「思料」と表記し、思料を印刷します。', '「思料」と表記し、資料を印刷します。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_rare_action_defaults_to_fitting_sense_and_keeps_geographic_patrol(self):
        import app
        for source,expected in (
                ('友人を哨戒します。', '友人を紹介します。'),
                ('新しい道具を哨戒します。', '新しい道具を紹介します。'),
                ('お客様に友人を哨戒します。', 'お客様に友人を紹介します。'),
                ('資料を哨戒して帰ります。', '資料を紹介して帰ります。'),
                ('友人を哨戒した後で帰ります。', '友人を紹介した後で帰ります。'),
                ('海上を哨戒します。', '海上を哨戒します。'),
                ('近海を哨戒して帰ります。', '近海を哨戒して帰ります。'),
                ('海域を巡回します。', '海域を巡回します。'),
                ('制度の内容を照会します。', '制度の内容を照会します。'),
                ('「哨戒」と表記する。', '「哨戒」と表記する。'),
                ('資料を哨戒して帰ります。\t海上を哨戒して帰ります。', '資料を紹介して帰ります。\t海上を哨戒して帰ります。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_marked_case_seam_keeps_the_following_clauses_own_cases(self):
        import contextual_repair as Q,corrector as C
        a=self.state;tok=C.make_tokenizer(a.store)
        for source in ('荷物を箱館でから駅へ向かいます。','道具を箱館でから家に帰ります。'):
            with self.subTest(source=source):
                targets=Q.targets_for_line(source,tok,a.store,a.dict_index)
                found=[t for t in targets if t.text=='箱館で']
                self.assertEqual(len(found),1)
                self.assertEqual((found[0].start,found[0].end),(3,6))
                readings=Q.reading_evidence(found[0],tok,a.dict_index)
                self.assertTrue(any(r.text=='はこかんで' for r in readings))
        source='荷物を箱館でから駅へ向かいます。'
        parts=list(tok(source));marks=(('で','から',5,8),)
        with patch('reading_segments.native_written_relative_action',return_value=()):
            self.assertFalse(Q._marked_nominal_de_before_kara_targets(source,0,len(source),parts,marks))
        self.assertFalse(Q._marked_nominal_de_before_kara_targets(source,0,len(source),parts,()))
        for source in ('荷物を箱館でから資料へ戻ります。','荷物を箱館でからぽねに帰ります。',
                '荷物を箱館でから駅へ向かいますです。','荷物を箱館でから駅へ向かいま',
                '荷物を箱館でから駅へ\t向かいます。','箱館でから駅へ向かいます。',
                '荷物を箱館から駅へ向かいます。','「荷物を箱館でから駅へ向かいます」という文字列です。'):
            with self.subTest(source=source):
                self.assertFalse(any(t.text=='箱館で' for t in Q.targets_for_line(source,tok,a.store,a.dict_index)))

    def test_following_case_repair_keeps_final_meaning_and_common_gate(self):
        import app,corrector as C,reading_segments as R
        from tests_analysis_async import initial
        from last_choice import set_active
        def run(source):
            a=initial()
            return app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                    decisions=a.decisions,context_vec=None)
        try:
            for source in ('荷物を箱館でから駅へ向かいます。','道具を箱館でから家に帰ります。'):
                with self.subTest(source=source):
                    r=run(source)
                    self.assertEqual(r['corrected'],source.replace('箱館で','運んで'))
                    self.assertEqual(r['odd_spans'],[])
                    self.assertEqual(r['analysis_status'],'complete')
            self.assertFalse(R.native_object_predicate_proof('資料を食べてから駅へ戻ります',3,('資料',)))
            source='荷物を箱館でから駅へ向かいます。'
            with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')):
                self.assertEqual(run(source)['corrected'],source)
            for source in ('荷物を運んでから駅へ向かいます。','箱館から駅へ向かいます。',
                    '荷物を箱館でから駅へ\t向かいます。',
                    '「荷物を箱館でから駅へ向かいます」という文字列です。'):
                self.assertEqual(run(source)['corrected'],source)
        finally:set_active(None)

    def test_marked_nominal_case_seam_uses_original_native_readings(self):
        import contextual_repair as Q,corrector as C
        state=self.state;tok=C.make_tokenizer(state.store)
        source='荷物を箱館でから休みます。'
        found=[t for t in Q.targets_for_line(source,tok,state.store,state.dict_index)
               if (t.start,t.end)==(3,6)]
        self.assertEqual(len(found),1)
        target=found[0]
        self.assertEqual(target.text,'箱館で')
        self.assertTrue(target.following.startswith('から'))
        readings=Q.reading_evidence(target,tok,state.dict_index)
        original=next(r for r in readings if r.text=='はこかんで')
        self.assertFalse(any(origin.startswith('ime_') or origin=='current_ime_occurrence'
            for origin,rank,segments in original.provenance))
        self.assertTrue(any(r.reading=='はこんで' and r.operation=='adjacent_intrusion'
                            for r in Q.key_repairs(original.text)))
        parts=list(tok(source));marks=(('で','から',5,8),)
        with patch('ime_inverse_gate.exact_context_reading',return_value=None):
            self.assertTrue(Q._marked_nominal_de_before_kara_targets(source,0,len(source),parts,marks))
            self.assertFalse(Q._marked_nominal_de_before_kara_targets(source,0,len(source),parts,()))
            for index,field,value in ((2,2,'ぽね'),(3,3,3),(3,1,'名詞:サ変接続')):
                changed=list(parts);token=list(changed[index]);token[field]=value;changed[index]=tuple(token)
                with self.subTest(index=index,field=field):
                    self.assertFalse(Q._marked_nominal_de_before_kara_targets(source,0,len(source),changed,marks))
        for text in ('荷物を箱館で受け取ります。','箱館でから休みます。',
                     '荷物をぽねでから休みます。','荷物を箱館でから',
                     '荷物を箱館で\tから休みます。',
                     '「荷物を箱館でから休みます」という文字列です。'):
            with self.subTest(text=text):
                self.assertFalse(any(t.text=='箱館で' for t in Q.targets_for_line(text,tok,state.store,state.dict_index)))

    def test_native_nominal_case_seam_keeps_final_gate_and_source_context(self):
        import app,corrector as C
        state=self.state;source='荷物を箱館でから休みます。'
        result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
            decisions=state.decisions,context_vec=None)
        self.assertEqual(result['corrected'],'荷物を運んでから休みます。')
        self.assertFalse(result['odd_spans'])
        self.assertEqual(result['analysis_status'],'complete')
        with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')):
            rejected=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                decisions=state.decisions,context_vec=None)
        self.assertEqual(rejected['corrected'],source)
        for text in ('荷物を運んでから休みます。','箱館で休みます。',
                     '「荷物を箱館でから休みます」という文字列です。'):
            with self.subTest(text=text):
                result=app.correct_line(text,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],text)
                self.assertFalse(result['odd_spans'])
                self.assertEqual(result['analysis_status'],'complete')

    def test_repaired_action_clears_only_proved_adjacent_connectives(self):
        import app
        for source,expected in (
                ('荷物をは今夏でから休みます。', '荷物を運んでから休みます。'),
                ('荷物をはコンクでから休みます。', '荷物を運んでから休みます。'),
                ('荷物を運んでから休みます。', '荷物を運んでから休みます。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_adjacent_proof_does_not_cover_another_field_or_invalid_particles(self):
        import app
        for source,expected,odd in (
                ('荷物を箱館でから休みます。','荷物を運んでから休みます。',[]),
                ('荷物をはコンクでから休みます。\t時刻を伊良部て駅へ向かいます。',
                 '荷物を運んでから休みます。\t時刻を調べて駅へ向かいます。',[]),
                ('時刻を伊良部て駅へ向かいます。\t荷物をはコンクでから休みます。',
                 '時刻を調べて駅へ向かいます。\t荷物を運んでから休みます。',[]),
                ('荷物をはコンクでには休みます。','荷物を運んでには休みます。',[(7,9)])):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual([tuple(x) for x in result.get('odd_spans',[])],odd)

    def test_completed_meaning_requires_its_own_same_reading_source_proof(self):
        from contextual_repair import preserves_completed_reading_link
        for source,old,new,accepted in (
                ('資料を哨戒して帰ります。','哨戒','紹介',True),
                ('海上を哨戒して帰ります。','哨戒','紹介',False),
                ('資料を保存して話ました。','保存','説明',False),
                ('資料を保存して話ました。','話','話し',True)):
            a=source.index(old)
            self.assertEqual(preserves_completed_reading_link(source,a,a+len(old),new),accepted,source)

    def test_rare_nominal_explicit_choice_is_stronger_than_default_usage(self):
        import app
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:'思料' if rd=='しりょう' else None):
            source='思料を印刷します。'
            result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                decisions=self.state.decisions,context_vec=None)
            self.assertEqual(result['corrected'],source)
            self.assertFalse(result.get('odd_spans'))

    def test_translation_uses_content_and_native_auxiliary_connection(self):
        import app
        for source,expected in (
                ('会場を和訳します。', '会場を予約します。'),
                ('明日の会場を和訳しておきます。', '明日の会場を予約しておきます。'),
                ('会議室を和訳しています。', '会議室を予約しています。'),
                ('会場を和訳してしまいました。', '会場を予約してしまいました。'),
                ('会場を和訳しておいてください。', '会場を予約しておいてください。'),
                ('会場を和訳して人数を伝えておきます。', '会場を予約して人数を伝えておきます。'),
                ('会議室を和訳して資料を読んでいます。', '会議室を予約して資料を読んでいます。'),
                ('資料を和訳しておきます。', '資料を和訳しておきます。'),
                ('英文を和訳しています。', '英文を和訳しています。'),
                ('会場を和訳している人に貸します。', '会場を和訳している人に貸します。'),
                ('「会場」を和訳しておきます。', '「会場」を和訳しておきます。'),
                ('海上を哨戒しています。', '海上を哨戒しています。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_ordinary_use_and_concrete_private_purpose(self):
        import app
        for source,expected in (
                ('私用した道具を片付けます。', '使用した道具を片付けます。'),
                ('私用する資料を準備します。', '使用する資料を準備します。'),
                ('道具を私用します。', '道具を使用します。'),
                ('資料を私用して内容を説明します。', '資料を使用して内容を説明します。'),
                ('会社の道具を私用します。', '会社の道具を私用します。'),
                ('社用車を私用します。', '社用車を私用します。'),
                ('公用車を私用しておきます。', '公用車を私用しておきます。'),
                ('私的に私用した道具を片付けます。', '私的に私用した道具を片付けます。'),
                ('会社の会議で私用した道具を片付けます。', '会社の会議で使用した道具を片付けます。'),
                ('私用した道具を個人的に買います。', '使用した道具を個人的に買います。'),
                ('会社の道具を使用します。', '会社の道具を使用します。'),
                ('私用のため休みます。', '私用のため休みます。'),
                ('「私用」と表記し、私用した道具を片付けます。', '「私用」と表記し、使用した道具を片付けます。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_independent_next_object_stops_at_its_source_field(self):
        import app
        for source,expected in (
                ('会場を和訳して人数を伝えます。\t海上を哨戒します。', '会場を予約して人数を伝えます。\t海上を哨戒します。'),
                ('海上を哨戒します。\t会場を和訳して人数を伝えておきます。', '海上を哨戒します。\t会場を予約して人数を伝えておきます。'),
                ('会場を和訳して人数を伝えます。説明を英訳します。', '会場を予約して人数を伝えます。説明を英訳します。'),
                ('私用した道具を片付けます。\t会社の道具を私用します。', '使用した道具を片付けます。\t会社の道具を私用します。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_partial_semantic_repair_keeps_the_unchanged_source_remainder(self):
        import app
        # A deliberate same-reading choice keeps the argument while the action repairs.
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:'海上' if rd=='かいじょう' else None):
            for source,expected,odd in (
                    ('海上を和訳して人数を伝えます。','海上を予約して人数を伝えます。',[(0,2)]),
                    ('海上を和訳して人数を伝えます。\t会場を予約します。','海上を予約して人数を伝えます。\t会場を予約します。',[(0,2)]),
                    ('海上を和訳して人数を伝えます。 ⇒海上を和訳します。','海上を予約して人数を伝えます。 ⇒海上を予約します。',[(0,2),(17,19)])):
                with self.subTest(source=source):
                    result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                        decisions=self.state.decisions,context_vec=None)
                    self.assertEqual(result['corrected'],expected)
                    self.assertEqual([tuple(x) for x in result.get('odd_spans',[])],odd)
                    diagnosis=result['diagnosis']
                    self.assertEqual(diagnosis['language_state'],'anomaly_unrepaired')
                    self.assertFalse(diagnosis['range_errors'])
                    for x in odd:self.assertIn(list(x),diagnosis['unreplaced_odd_spans'])

    def test_auxiliary_is_one_action_and_relative_head_keeps_its_object_slot(self):
        from semantic_roles import _independent_accusative_clause
        for source in ('本を読んでいます。','本を読んでおきます。','本を読んでしまいました。',
                       '人数を伝えておきます。\t未完成の別欄'):
            self.assertTrue(_independent_accusative_clause(source),source)
        for source in ('本を読んでいる人に渡します。','本を読んで位置ます。','本を読むには'):
            self.assertFalse(_independent_accusative_clause(source),source)

    def test_explicit_private_use_choice_overrides_ordinary_default(self):
        import app
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:'私用' if rd=='しよう' else None):
            source='私用した道具を片付けます。'
            result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                decisions=self.state.decisions,context_vec=None)
            self.assertEqual(result['corrected'],source)
            self.assertFalse(result.get('odd_spans'))

    def test_joint_object_and_action_meaning_uses_one_original_key_proof(self):
        import app
        for source,expected in (
                ('海上を和訳して人数を伝えます。', '会場を予約して人数を伝えます。'),
                ('海上を読奥して人数を伝えます。', '会場を予約して人数を伝えます。'),
                ('海上を和訳しておきます。', '会場を予約しておきます。'),
                ('人数を確認し、海上を和訳しておきます。', '人数を確認し、会場を予約しておきます。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')
                self.assertFalse(result['diagnosis']['range_errors'])

    def test_joint_argument_meaning_is_local_to_its_original_field(self):
        import app
        for source,expected in (
                ('海上を和訳して人数を伝えます。\t会場を予約します。', '会場を予約して人数を伝えます。\t会場を予約します。'),
                ('海上を和訳して人数を伝えます。 ⇒海上を和訳します。', '会場を予約して人数を伝えます。 ⇒会場を予約します。'),
                ('海上を和訳します。\t海上を哨戒します。', '会場を予約します。\t海上を哨戒します。'),
                ('会議室を和訳します。\t海上を和訳します。', '会議室を予約します。\t会場を予約します。'),
                ('海上を哨戒して人数を伝えておきます。', '海上を哨戒して人数を伝えておきます。'),
                ('海上を和訳している人に貸します。', '海上を和訳している人に貸します。'),
                ('「海上」を和訳しておきます。', '「海上」を和訳しておきます。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')
                self.assertFalse(result['diagnosis']['range_errors'])

    def test_joint_meaning_keeps_physical_key_positions_and_reading_sources(self):
        import app,corrector
        source='海上を和訳して人数を伝えます。'
        corrector.trace_on()
        try:
            result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                decisions=self.state.decisions,context_vec=None)
        finally:corrector.trace_off()
        selected=next(d for d in result['contextual_diagnostics'] if d.get('selected')=='会場を予約')
        row=next(c for c in selected['candidates'] if c['surface']=='会場を予約')
        self.assertEqual(row['reading']['source'],'joint_source_argument')
        self.assertEqual(row['reading']['text'],'かいじょうをわやく')
        self.assertEqual(row['repair']['reading'],'かいじょうをよやく')
        self.assertEqual(row['reading']['text'][row['repair']['position']],row['repair']['pressed'])
        self.assertEqual(row['repair']['intended'],'よ')
        self.assertFalse(row['also_from_legacy'])
        self.assertEqual(row['source_meaning']['original_argument'],'海上')

    def test_joint_reading_provenance_preserves_weak_and_native_evidence(self):
        from dataclasses import asdict
        from types import SimpleNamespace
        import contextual_repair as Q
        from joint_meaning import _prepend_source_reading
        parts=(SimpleNamespace(start=0,end=2,reading='かいじょう'),
               SimpleNamespace(start=2,end=3,reading='を'))
        weak=Q.Reading('わやく','ime_reverse',2,((0,2,'わやく','character_guess'),))
        native=Q.Reading('わやく','token_sequence',0,((0,2,'わやく','dictionary_word'),))
        for original in (weak,native,*[Q.merge_readings(rows)[0] for rows in ((weak,native),(native,weak))]):
            with self.subTest(source=original.source,provenance=original.provenance):
                source=asdict(original)
                widened=Q.Reading(**_prepend_source_reading(source,parts,3))
                self.assertEqual(source,asdict(original))
                self.assertEqual(widened.text,'かいじょうをわやく')
                self.assertEqual(widened.segments[-1][:3],(3,5,'わやく'))
                self.assertEqual(Q.needs_source_argument_proof(widened),Q.needs_source_argument_proof(original))
                self.assertEqual(Q.needs_ime_context_projection(widened),Q.needs_ime_context_projection(original))
                for origin,rank,segments in widened.provenance:
                    self.assertEqual(segments[:2],((0,2,'かいじょう','analyzed_word'),(2,3,'を','analyzed_word')))
                    self.assertEqual(segments[-1][:3],(3,5,'わやく'))

    def test_joint_correct_text_does_not_hide_existing_search_limit(self):
        import app
        source='海上を読湯訳して人数を伝えます。'
        import contextual_repair as Q
        original_readings=Q.reading_evidence
        def measured_limit(*args,**kwargs):
            # Exercise a real truncated search report, independent of how
            # many lexical candidates this particular dictionary returns.
            Q._bounded((0,1),1,'controlled_test_bound')
            return original_readings(*args,**kwargs)
        with patch.object(Q,'reading_evidence',side_effect=measured_limit) as measured:
            result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                decisions=self.state.decisions,context_vec=None)
        self.assertTrue(measured.called)
        self.assertEqual(result['corrected'],'会場を予約して人数を伝えます。')
        self.assertFalse(result.get('odd_spans'))
        self.assertEqual(result.get('analysis_status'),'limited')
        self.assertEqual(result.get('stop_reason'),'search_limit')

    def test_native_nominal_copula_closes_the_same_action_object(self):
        import app
        for source,expected in (
                ('会場を和訳しておく予定です。', '会場を予約しておく予定です。'),
                ('会場を和訳する予定です。', '会場を予約する予定です。'),
                ('会場を和訳する人です。', '会場を予約する人です。'),
                ('会場を和訳した人でした。', '会場を予約した人でした。'),
                ('会場を和訳していた人です。', '会場を予約していた人です。'),
                ('会場を和訳するつもりです。', '会場を予約するつもりです。'),
                ('海上を和訳する予定です。', '会場を予約する予定です。'),
                ('資料を私用する予定です。', '資料を使用する予定です。'),
                ('会場を和訳する予定の人に貸します。', '会場を和訳する予定の人に貸します。'),
                ('会場を和訳する人だと聞きました。', '会場を和訳する人だと聞きました。'),
                ('資料を和訳する予定です。', '資料を和訳する予定です。'),
                ('英文を和訳する人です。', '英文を和訳する人です。'),
                ('本を読んだ人でした。', '本を読んだ人でした。'),
                ('海上を哨戒する予定です。', '海上を哨戒する予定です。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_following_nominal_clause_uses_the_same_completed_object_proof(self):
        import app
        for source,expected in (
                ('会場を和訳して人数を伝える予定です。', '会場を予約して人数を伝える予定です。'),
                ('海上を和訳して人数を伝える予定です。', '会場を予約して人数を伝える予定です。'),
                ('会場を和訳して本を読むつもりです。', '会場を予約して本を読むつもりです。'),
                ('会場を和訳して人数を伝えておく予定です。', '会場を予約して人数を伝えておく予定です。'),
                ('会場を和訳して人数を伝える予定です。\t海上を哨戒します。', '会場を予約して人数を伝える予定です。\t海上を哨戒します。'),
                ('会場を和訳して人数を伝える予定の人に貸します。', '会場を和訳して人数を伝える予定の人に貸します。'),
                ('海上を哨戒して人数を伝える予定です。', '海上を哨戒して人数を伝える予定です。'),
                ('資料を和訳して人数を伝える予定です。', '資料を和訳して人数を伝える予定です。'),
                ('会社の道具を私用する予定です。', '会社の道具を私用する予定です。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_nominal_completion_requires_the_native_components(self):
        from semantic_roles import _independent_accusative_clause
        for source in ('人数を伝える予定です。','人数を伝えておく予定です。','本を読むつもりです。','本を読んだ人です。'):
            self.assertTrue(_independent_accusative_clause(source),source)
        for source in ('人数を伝えます予定です。','人数を伝える予定の人に貸します。',
                       '人数を伝える予定だと聞きます。','本を読むには','本を読み予定です。'):
            self.assertFalse(_independent_accusative_clause(source),source)

    def test_contract_past_seam_is_shared_but_real_past_stays(self):
        import app
        for source,expected in (
            ('手紙を書いてた寝ます。','手紙を書いて寝ます。'),
            ('本を読んでた頃です。','本を読んでた頃です。'),
            ('材料を買った。帰ります。','材料を買った。帰ります。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',
                    dict_index=self.state.dict_index,decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result.get('odd_spans'),[])
