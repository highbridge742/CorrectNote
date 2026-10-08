# -*- coding: utf-8 -*-
import unittest
import app
from tests_analysis_async import initial

from morphology import HAS_JANOME

@unittest.skipUnless(HAS_JANOME, "Requires real Janome; run with the native integration suite")
class NaturalDefaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.state=initial()
    def check(self,source,expected):
        s=self.state
        r=app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,
                           decisions=s.decisions,context_vec=None)
        self.assertIn(r['corrected'],expected if isinstance(expected,tuple) else (expected,),source)
        self.assertFalse(r.get('odd_spans'),source)
        self.assertEqual('complete',r.get('analysis_status'),source)

    def test_independent_key_and_written_fields(self):
        for source in ('と照る手段','とてるしゅだん','とれるしゅだん'):
            with self.subTest(source=source):self.check(source+'\t','取れる手段\t')

    def test_familiar_process_keeps_original_semantic_category(self):
        for source in ('再退化','さいたいか','さいだいか'):
            with self.subTest(source=source):self.check(source+'\t','最大化\t')

    def test_parser_cost_is_not_semantic_naturalness(self):
        for a,b in [('約束の時間に土地宇着しました。','約束の時間に到着しました。'),
                    ('海上を世や菊して人数を伝えます。','会場を予約して人数を伝えます。'),
                    ('結果を機論して資料を閉じます。',('結果を記録して資料を閉じます。','結果を議論して資料を閉じます。')),
                    ('必要な部分だけを点刷してください。','必要な部分だけを印刷してください。')]:
            with self.subTest(source=a):self.check(a,b)

    def test_native_processes_and_relative_actions(self):
        for source in ('再構成','再変換','再初期化','再評価','器官が再退化する',
                       '取る手段','取れる手段','採る手段','使える方法'):
            with self.subTest(source=source):self.check(source,source)


    def test_native_inflection_keeps_its_source_reading_and_own_usage(self):
        for source,expected in (
                ('キーボードで文字を売ちます。','キーボードで文字を打ちます。'),
                ('キーボードで文字を打ちます。','キーボードで文字を打ちます。'),
                ('キーボードで文字を打てます。','キーボードで文字を打てます。')):
            with self.subTest(source=source):self.check(source,expected)

    def test_inverse_scope_keeps_proved_nominal_prefix_and_real_limits(self):
        import corrector,ime_inverse_gate
        s=self.state;tok=corrector.make_tokenizer(s.store)
        for source,expected in (
                ('必要な部分だけを点刷してください。','必要な部分だけを印刷してください。'),
                ('重要な資料を点刷します。','重要な資料を印刷します。')):
            with self.subTest(source=source):
                result=app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,
                    decisions=s.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result['odd_spans'])
                self.assertEqual(result['analysis_status'],'complete')
                self.assertTrue(result.get('search_reports'))
                edge=source.index('を')+1
                self.assertTrue(all(report['start']>=edge for report in result['search_reports']))
                self.assertTrue(all(not v.get('unexplored') for report in result['search_reports']
                                    for v in report.get('limits',{}).values()))
        for source in ('未知語ぽねを点刷します','必要で部分を点刷します','を点刷します',
                       '必要な部分だけ','資料を'):
            with self.subTest(source=source):self.assertEqual(ime_inverse_gate._native_argument_prefix(source,tok),0)

    def test_complete_stem_family_keeps_unfinished_and_invalid_source_states(self):
        state=self.state
        for source,expected,spans in (
                ('未知語ぽねを点刷します。','未知語ぽねを印刷します。',()),
                ('資料を点刷したら','資料を点刷したら',((3,6),)),
                ('資料を点刷しますです。','資料を点刷しますです。',((3,6),))):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                                        decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(tuple(map(tuple,result['odd_spans'])),spans)
                self.assertEqual(result['analysis_status'],'complete')

    def test_native_stem_extra_capacity_requires_complete_source_families(self):
        import contextual_repair as Q,corrector as C
        # Count provenance-bearing branches, not only duplicate text. No
        # answer, inflection, or downstream acceptance can grant capacity.
        native=('あ',0,'analyzed_word');stem=('い',1,'unrecognized_ime_sequence')
        token=('字','名詞:一般','あ',0,1,True,'')
        rows=[(token,[native,stem],[stem])]
        self.assertTrue(Q._complete_native_stem_family_limits(rows,1))
        self.assertFalse(Q._complete_native_stem_family_limits(rows,1,existing_readings=1))
        self.assertTrue(Q._complete_native_stem_family_limits(rows,2,existing_readings=1))
        self.assertTrue(Q._complete_native_stem_family_limits([(token,[native,native,stem,stem],[stem,stem])],1))
        distinct=('あ',1,'dictionary_word')
        self.assertFalse(Q._complete_native_stem_family_limits([(token,[native,distinct,stem],[stem])],1))
        self.assertEqual(Q._complete_native_stem_family_limits(rows*2,2),(1,3))
        self.assertTrue(Q._complete_native_stem_family_limits(rows*2,3))
        self.assertFalse(Q._complete_native_stem_family_limits([(token,[native],[])],32))
        state=self.state;tk=C.make_tokenizer(state.store)
        for source,expected_count,limited in (('聞いた話を纏路手文章にします。',60,False),
                                              ('説明を纏路手資料にしました。',52,True)):
            target=next(t for t in Q.targets_for_line(source,tk,state.store,state.dict_index)
                        if t.text in ('纏路手文章','纏路手資料'))
            search={};report=Q._SEARCH.set(search)
            try:readings=Q.reading_evidence(target,tk,state.dict_index)
            finally:Q._SEARCH.reset(report)
            with self.subTest(source=source):
                self.assertEqual(len(readings),expected_count)
                self.assertEqual(search['token_readings']['unexplored'],limited)
                self.assertEqual(search['hidden_stem_readings']['examined'],0 if limited else 24)
                self.assertEqual(search['readings']['limit']+search['hidden_stem_readings']['limit'],64)
                self.assertLessEqual(len(readings),64)

    def test_native_stem_pool_reserves_original_evidence_without_single_family_expansion(self):
        import contextual_repair as Q
        token=('字','名詞:一般','あ',0,1,True,'')
        ordinary=[('あ'+str(n),n,'dictionary_word') for n in range(36)]
        hidden=[('い'+str(n),n,'unrecognized_ime_sequence') for n in range(24)]
        rows=[(token,ordinary+hidden,hidden)]
        self.assertEqual(Q._complete_native_stem_family_limits(rows,32),(36,28))
        self.assertEqual(Q._complete_native_stem_family_limits(rows,32,4),(40,24))
        self.assertIsNone(Q._complete_native_stem_family_limits(rows,32,5))
        self.assertEqual(Q._complete_native_stem_family_limits([(token,hidden+ordinary,ordinary)],32),(28,36))
        self.assertIsNone(Q._complete_native_stem_family_limits([(token,ordinary,[])],32))
        self.assertIsNone(Q._complete_native_stem_family_limits(rows*2,32))
        # Text equality does not erase distinct original provenance.
        other=(ordinary[0][0],0,'analyzed_word')
        self.assertIsNone(Q._complete_native_stem_family_limits([(token,ordinary+[other]+hidden,hidden)],32,4))

    def test_native_stem_lattice_keeps_original_provenance_and_real_bounds(self):
        import contextual_repair as Q,corrector as C
        from dataclasses import asdict
        from unittest.mock import patch
        state=self.state;tk=C.make_tokenizer(state.store)
        source='必要な部分だけを点刷してください。'
        target=next(t for t in Q.targets_for_line(source,tk,state.store,state.dict_index) if t.text=='点刷')
        search={};token=Q._SEARCH.set(search)
        try:rows=Q.reading_evidence(target,tk,state.dict_index)
        finally:Q._SEARCH.reset(token)
        self.assertEqual(len(rows),35)
        self.assertTrue({'つざつ','たさっ','つさっ'}<={r.text for r in rows})
        self.assertFalse(any(row['unexplored'] for row in search.values()))
        self.assertTrue(all(search[k]['limit']==32 for k in ('token_readings','readings','hidden_stem_token_readings','hidden_stem_readings')))
        for row in rows:
            self.assertEqual(tuple((a,b) for a,b,rd,kind in row.segments),((0,1),(1,2)))
            if row.text.startswith(('さ','た','つ')):
                self.assertTrue(Q.needs_source_argument_proof(row))
        # Removing the independent source proof restores only the original
        # family; it does not attest a hidden stem or promote its source.
        with patch.object(Q,'_marked_single_kanji_nominal_run',return_value=False):
            original=Q.reading_evidence(target,tk,state.dict_index)
        self.assertEqual(len(original),14)
        by_text={row.text:row for row in rows}
        for row in original:
            self.assertTrue(set(row.provenance)<=set(by_text[row.text].provenance))
        search={};token=Q._SEARCH.set(search)
        try:Q.reading_evidence(target,tk,state.dict_index,limit=2)
        finally:Q._SEARCH.reset(token)
        self.assertTrue(any(row['unexplored'] for row in search.values()))
        self.assertTrue(all(search[k]['limit']==2 for k in ('token_readings','readings','hidden_stem_token_readings','hidden_stem_readings')))

    def test_native_stem_lattice_still_uses_the_common_gate_and_preserves_limits(self):
        import contextual_repair as Q,corrector as C
        from unittest.mock import patch
        state=self.state;tk=C.make_tokenizer(state.store)
        source='重要な資料を点刷します。'
        with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):
            result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                                    decisions=state.decisions,context_vec=None)
        self.assertEqual(result['corrected'],source)
        self.assertTrue(result['odd_spans'])
        self.assertEqual(result['analysis_status'],'complete')
        for source in ('資料を印刷します。','「点刷します」と入力します。'):
            with self.subTest(source=source):self.check(source,source)
        source='説明を纏路手資料にしました。'
        target=next(t for t in Q.targets_for_line(source,tk,state.store,state.dict_index) if t.text=='纏路手資料')
        search={};token=Q._SEARCH.set(search)
        try:rows=Q.reading_evidence(target,tk,state.dict_index)
        finally:Q._SEARCH.reset(token)
        # These original72 + stem48 branches exceed the combined64.
        # Preserve fallback and the real unexplored state on overflow.
        self.assertTrue(search['token_readings']['unexplored'])
        self.assertFalse(search['hidden_stem_token_readings']['unexplored'])
        self.assertGreater(len(rows),32)
        self.assertTrue(all(search[k]['limit']==32 for k in ('token_readings','readings','hidden_stem_token_readings','hidden_stem_readings')))

    def test_source_provenances_pass_inflection_separately_before_merge(self):
        import contextual_repair as Q,corrector as C
        tok=C.make_tokenizer(self.state.store);parts=tok('的買い')
        weak=Q.Reading('まとがい','contextual_token_sequence',3,
            ((0,1,'まと','dictionary_word'),(1,3,'がい','compound_voicing')))
        incompatible=Q.Reading('まとがい','contextual_token_sequence',4,
            ((0,1,'まと','dictionary_word'),(1,3,'がい','dictionary_word')))
        self.assertTrue(Q._keeps_native_inflection_readings(weak,parts))
        self.assertFalse(Q._keeps_native_inflection_readings(incompatible,parts))
        merged=Q.merge_readings((weak,incompatible))
        checked=Q._readings_with_native_inflections(merged,parts)
        self.assertEqual(len(checked),1)
        self.assertEqual(checked[0].text,'まとがい')
        self.assertTrue(Q.needs_source_argument_proof(checked[0]))
        self.assertTrue(all(Q._keeps_native_inflection_readings(Q.Reading(checked[0].text,source,rank,segments),parts)
                            for source,rank,segments in checked[0].provenance))
        self.assertEqual(Q._readings_with_native_inflections((incompatible,),parts),[])
        native=Q.Reading('てきかい','contextual_token_sequence',0,
            ((0,1,'てき','analyzed_word'),(1,3,'かい','analyzed_word')))
        rows=Q._readings_with_native_inflections((native,*merged),parts)
        self.assertEqual({r.text for r in rows},{'てきかい','まとがい'})
        self.assertFalse(Q.needs_source_argument_proof(next(r for r in rows if r.text=='てきかい')))
        for source in ('current_ime_occurrence','saved_ime_pair','ime_first_roundtrip'):
            direct=Q.Reading('まとがい',source,0)
            rows=Q._readings_with_native_inflections((*merged,direct),parts)
            self.assertEqual(len(rows),1)
            self.assertFalse(Q.needs_source_argument_proof(rows[0]))
            self.assertTrue(any(item[0]==source for item in rows[0].provenance))

    def test_source_provenance_merge_keeps_original_member_coordinates(self):
        import contextual_repair as Q
        # Original member coordinates remain part of each reading proof.
        parts=[('的','名詞:一般','まと',0,1,True,''),
               ('買い','動詞:自立','かい',1,3,True,'連用形')]
        native=Q.Reading('まとかい','contextual_token_sequence',0,
                         ((0,1,'まと','dictionary_word'),(1,3,'かい','analyzed_word')))
        voiced=Q.Reading('まとがい','contextual_token_sequence',1,
                         ((0,1,'まと','dictionary_word'),(1,3,'がい','compound_voicing')))
        wrong_edge=Q.Reading('まとがい','contextual_token_sequence',0,
                         ((0,1,'まと','dictionary_word'),(1,2,'がい','compound_voicing')))
        rows=Q._readings_with_native_inflections(Q.merge_readings((native,voiced,wrong_edge)),parts)
        self.assertEqual({r.text for r in rows},{'まとかい','まとがい'})
        retained=next(r for r in rows if r.text=='まとがい')
        self.assertTrue(Q.needs_source_argument_proof(retained))
        self.assertTrue(all(segments[-1][0:2]==(1,3) for origin,rank,segments in retained.provenance))

    def test_weak_inverse_reading_keeps_attested_inflection(self):
        import corrector,contextual_repair as Q
        tok=corrector.make_tokenizer(self.state.store)
        parts=tok('悪けれ')
        weak=Q.Reading('あくけれ','ime_reverse',0,((0,1,'あく','ime_reverse_word'),
            (1,2,'け','ime_reverse_word'),(2,3,'れ','ime_reverse_word')))
        self.assertFalse(Q._keeps_native_inflection_readings(weak,parts))
        native=Q.Reading('わるけれ','token_sequence',0,((0,3,'わるけれ','analyzed_word'),))
        self.assertTrue(Q._keeps_native_inflection_readings(native,parts))
        self.assertTrue(Q._keeps_native_inflection_readings(Q.Reading('あくけれ','current_ime_occurrence',0),parts))
        self.assertTrue(Q._keeps_native_inflection_readings(Q.Reading('あくけれ','ime_first_roundtrip',0),parts))
        for source in ('悪けれではないでしょうか。','高けれではないでしょうか。'):
            result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                decisions=self.state.decisions,context_vec=None)
            with self.subTest(source=source):
                self.assertEqual(result['corrected'],source)
                # The malformed connection stays unresolved; no invented success.
                self.assertTrue(result['odd_spans'])

    def test_nominal_compound_voicing_keeps_form_and_source_edges(self):
        import contextual_repair as Q
        from unittest.mock import patch
        parts=[('色','名詞:一般','いろ',0,1,True,''),
               ('付け','動詞:自立','つけ',1,3,True,'連用形')]
        def reading(rd,kind='compound_voicing',span=(1,3)):
            return Q.Reading('いろ'+rd,'token_sequence',1,
                ((0,1,'いろ','analyzed_word'),(*span,rd,kind)))
        with patch('morphology.dictionary_inflections',return_value=(
                ('動詞,自立,*,*','連用形','付ける','つけ'),)):
            self.assertTrue(Q._keeps_native_inflection_readings(reading('づけ'),parts))
            self.assertTrue(Q.needs_source_argument_proof(reading('づけ')))
            self.assertFalse(Q._keeps_native_inflection_readings(reading('づけ','ime_reverse_word'),parts))
            self.assertFalse(Q._keeps_native_inflection_readings(reading('づけ',span=(1,2)),parts))
            self.assertFalse(Q._keeps_native_inflection_readings(reading('づく'),parts))
            separated=[('色を','助詞:格助詞','いろを',0,1,True,''),parts[1]]
            self.assertFalse(Q._keeps_native_inflection_readings(reading('づけ'),separated))
        for form in ('基本形','仮定形'):
            other=[parts[0],parts[1][:6]+(form,)]
            with patch('morphology.dictionary_inflections',return_value=(
                    ('動詞,自立,*,*',form,'付ける','つけ'),)):
                self.assertFalse(Q._keeps_native_inflection_readings(reading('づけ'),other))

    def test_damaged_kana_member_keeps_attested_written_nominal_voicing(self):
        import corrector as C,contextual_repair as Q
        from unittest.mock import patch
        from dataclasses import replace
        state=self.state;tok=C.make_tokenizer(state.store)
        source='透明なしはょ棚を片付けます。'
        target=next(t for t in Q.targets_for_line(source,tok,state.store,state.dict_index)
                    if (t.start,t.end)==(3,7))
        reading=next(r for r in Q.reading_evidence(target,tok,state.dict_index)
                     if r.text=='しはょだな')
        self.assertIn('source_nominal_voicing',{s[3] for s in reading.segments})
        self.assertTrue(Q.needs_source_argument_proof(reading))
        ok,why=Q.validate(target,'書棚',C,tok,state.store,state.dict_index,state.decisions,
            expected_reading='しょだな',source_reading=reading)
        self.assertTrue(ok,why)
        for face,rd in (('処方','しょほう'),('初棚','しょだな'),('書棚','しょたな')):
            with self.subTest(face=face,reading=rd):
                self.assertEqual(Q.validate(target,face,C,tok,state.store,state.dict_index,
                    state.decisions,expected_reading=rd,source_reading=reading),
                    (False,'unproven_source_nominal_voicing'))
        normal=replace(target,structural=False,anomalies=())
        self.assertFalse(any(s[3]=='source_nominal_voicing'
            for r in Q.reading_evidence(normal,tok,state.dict_index) for s in r.segments))
        result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
            decisions=state.decisions,context_vec=None)
        self.assertEqual(result['corrected'],'透明な書棚を片付けます。')
        self.assertFalse(result['odd_spans'])
        with patch.object(C,'_check_replacement',return_value=(None,'test_shared_gate')):
            blocked=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                decisions=state.decisions,context_vec=None)
        self.assertNotEqual(blocked['corrected'],'透明な書棚を片付けます。')

    def test_missing_ime_still_generates_and_validates_voiced_nominal(self):
        import corrector as C
        from vocabulary import find_known_readings_flex
        from unittest.mock import patch
        s=self.state;tok=C.make_tokenizer(s.store)
        with patch('ime_language._factory',None):
            for source,expected in (
                    ('画添えウを保存します。','画像を保存します。'),
                    ('画像を保存します。','画像を保存します。'),
                    ('各層を保存します。','各層を保存します。'),
                    ('花を添えます。','花を添えます。')):
                with self.subTest(source=source):
                    trace=C.trace_on()
                    try:
                        result=C.correct_line(source,s.store,tok,find_known_readings_flex,
                            input_method='kana',dict_index=s.dict_index)
                    finally:C.trace_off()
                    self.assertEqual(result['corrected'],expected)
                    self.assertFalse(result['odd_spans'])
                    self.assertEqual(result['analysis_status'],'complete')
                    if source.startswith('画添'):
                        rows=[row for diagnostic in result['contextual_diagnostics']
                              for row in diagnostic.get('candidates',()) if row['surface']=='画像']
                        self.assertTrue(rows)
                        self.assertTrue(rows[0]['object_candidate_fit'])
                        self.assertEqual(rows[0]['repair']['operation'],'adjacent_intrusion')


    def test_marked_single_kanji_inflection_opens_existing_stem_reading(self):
        import corrector as C,contextual_repair as Q
        from unittest.mock import patch
        state=self.state;tok=C.make_tokenizer(state.store)
        with patch('ime_language._factory',None):
            source='雨が降る前に洗濯物を取り退見ます。'
            target=next(t for t in Q.targets_for_line(source,tok,state.store,state.dict_index)
                        if t.text=='取り退見' and t.boundary_kind=='lexical')
            readings=Q.reading_evidence(target,tok,state.dict_index)
            repaired=next(r for r in readings if r.text=='とりひみ')
            self.assertTrue(Q.needs_source_argument_proof(repaired))
            self.check(source,'雨が降る前に洗濯物を取り込みます。')
            for source in ('川を退く。','退路を確認します。','資料を取り出します。',
                           '本を読み書きします。','「取り退見ます」と入力しました。'):
                with self.subTest(source=source):self.check(source,source)



if __name__=='__main__':unittest.main()
