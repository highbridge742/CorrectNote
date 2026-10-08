import unittest
import corrector as C
from literal_examples import protected_ranges, subtract_ranges, masked_case_ranges

class LiteralExampleTests(unittest.TestCase):

    def test_input_output_value_reports_keep_only_the_asserted_quote(self):
        for before in ('入力は','出力が','今回の入力は','前の文。出力は'):
            for after in ('です。','でした。','だった。','ではありません。','である。'):
                source=before+'「変更するない」'+after+'変更するない。'
                with self.subTest(source=source):
                    self.assertEqual([source[a:b] for a,b in protected_ranges(source)],['変更するない'])
                    self.assertEqual(protected_ranges(source),[(source.index('「')+1,source.index('」'))])
        source='入力は「😀あ『い』う」です。'
        self.assertEqual([source[a:b] for a,b in protected_ranges(source)],['😀あ『い』う'])

    def test_input_output_value_reports_require_original_subject_and_copula(self):
        import literal_examples as L,morphology as M
        from unittest.mock import patch
        from copy import copy
        for source in ('入力を「変更するない」です。','入力は「変更するない」と話します。',
                       '入力は「変更するない」ですます。','入力は「変更するない」では',
                       '入力は\t「変更するない」です。','入力は「変更するない」\tです。',
                       '入力は「変更するない。','入力は「変更するない』です。',
                       '入力を確認します。「変更するない」です。','「変更するない」です。'):
            self.assertEqual(protected_ranges(source),[],source)
        source='入力は「変更するない」です。';prefix=source[:3]
        tokens=M.tokenize(prefix);tokenize=M.tokenize
        for index,field,value in ((0,'reading','でりょく'),(0,'pos','動詞'),(0,'base_form','出力'),(0,'end',1),
                                  (1,'reading','が'),(1,'pos','名詞'),(1,'base_form','が'),(1,'infl_form','未然形'),(1,'has_reading',False)):
            changed=[copy(t) for t in tokens];setattr(changed[index],field,value)
            with patch.object(M,'tokenize',side_effect=lambda text:changed if text==prefix else tokenize(text)):
                self.assertFalse(L._input_output_value_report(source,3,10),(index,field))
        actual=M.dictionary_inflections
        for missing in ('入力','は'):
            with patch.object(M,'dictionary_inflections',side_effect=lambda face:() if face==missing else actual(face)):
                self.assertFalse(L._input_output_value_report(source,3,10),missing)

    def test_input_value_mask_preserves_outside_marks_and_codepoint_offsets(self):
        source='入力は「😀変更するない」です。外';seen=[]
        def engine(line):
            seen.append(line)
            return dict(original=line,corrected=line,changed=False,odd_spans=[(0,len(line))],odd_reasons=[(0,len(line),'rule')],unsure_spans=[])
        result=C._with_literal_examples(engine)(source)
        lo=source.index('「')+1;hi=source.index('」')
        self.assertEqual(len(seen),1);self.assertEqual(len(seen[0]),len(source))
        self.assertNotIn('😀変更するない',seen[0])
        self.assertEqual(result['corrected'],source)
        self.assertEqual(result['odd_spans'],[(0,lo),(hi,len(source))])

    def test_input_value_application_retains_literal_and_validates_outside_change(self):
        import app
        from tests_analysis_async import initial
        from last_choice import set_active
        from unittest.mock import patch
        state=initial()
        def result(source):
            return app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,decisions=state.decisions,context_vec=None)
        source='入力は「変更するない」です。'
        try:
            r=result(source);self.assertEqual(r['corrected'],source)
            self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
            bare=result('変更するない');self.assertEqual(bare['corrected'],'変更するない')
            self.assertTrue(bare['odd_spans']);self.assertEqual(bare['analysis_status'],'complete')
            source+='話を纏路手文章にします。'
            r=result(source);self.assertEqual(r['corrected'],'入力は「変更するない」です。話をまとめて文章にします。')
            self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
            self.assertTrue(r['original_spans'])
            self.assertTrue(all(a>=source.index('話') for a,b in r['original_spans']))
            with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                r=result(source);self.assertEqual(r['corrected'],source)
                self.assertEqual(r['analysis_status'],'complete')
        finally:set_active(None)


    def test_unquoted_spelling_labels_keep_the_original_bounded_text(self):
        for label in ('表記','綴り','文字列','文字'):
            for link in ('という','といった'):
                source='前の文。纏路手'+link+label+'です。後の文。'
                with self.subTest(source=source):
                    self.assertEqual(protected_ranges(source),[(4,7)])
        for source,wanted in (
                ('ぽねという文字列です。',[(0,2)]),
                ('纏路手という文字列を確認します。',[(0,3)]),
                ('纏路手\tぽねという文字列です。',[(4,6)]),
                ('纏路手⇒ぽねという文字列です。',[(4,6)]),
                ('纏路手という文字列です。\tぽね',[(0,3)])):
            with self.subTest(source=source):self.assertEqual(protected_ranges(source),wanted)
        for source in ('纏路手と話します。','文字列を調べて纏路手と書きます。',
                       '纏路手という文字列挙を確認します。','「纏路手という文字列です。',
                       '（纏路手）という文字列です。','纏路手\tという文字列です。',
                       '纏路手\nという文字列です。','纏路手という\t文字列です。'):
            with self.subTest(source=source):self.assertEqual(protected_ranges(source),[])

    def test_unquoted_spelling_data_preserves_other_field_repairs(self):
        import app
        from tests_analysis_async import initial
        from last_choice import set_active
        try:
            for source,expected in (
                    ('纏路手という文字列です。','纏路手という文字列です。'),
                    ('ぽねという表記です。','ぽねという表記です。'),
                    ('纏路手という文字列です。\t話を纏路手文章にします。',
                     '纏路手という文字列です。\t話をまとめて文章にします。')):
                with self.subTest(source=source):
                    state=initial()
                    result=app.correct_line(source,state.store,input_method='kana',
                        dict_index=state.dict_index,decisions=state.decisions,context_vec=None)
                    self.assertEqual(result['corrected'],expected)
                    self.assertEqual(result['odd_spans'],[])
                    self.assertEqual(result['analysis_status'],'complete')
        finally:set_active(None)

    def test_literal_copy_and_search_objects_keep_exact_characters(self):
        for operation in ('コピー','コピーします。','コピーしない','検索','検索する'):
            line='「ぬるかった゛゜」を'+operation
            self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['ぬるかった゛゜'])
        for line in ('「ぬるかった゛゜」と話す','「ぬるかった゛゜」をコピー機で印刷する'):
            self.assertEqual(protected_ranges(line),[])

    def test_written_form_labels_identify_the_same_quote_on_either_side(self):
        from literal_examples import protected_ranges
        for label in ('表記','綴り','文字列','文字'):
            for text in (label+'「モーシろょん ⇒ 注」を確認します。',
                         '「モーシろょん ⇒ 注」という'+label+'です。',
                         '「モーシろょん ⇒ 注」は'+label+'です。'):
                with self.subTest(text=text):
                    lo=text.index('「')+1;hi=text.index('」')
                    self.assertIn((lo,hi),protected_ranges(text))
        for text in ('「モーシろょん ⇒ 注」と書きます。',
                     '文章「モーシろょん ⇒ 注」を校正します。',
                     '文字列を調べて「モーシろょん ⇒ 注」と書きます。',
                     '文字列「モーシろょん ⇒ 注',
                     '文字列「モーシろょん ⇒ 注』'):
            self.assertEqual(protected_ranges(text),[],text)

    def test_explicit_input_output_spelling_examples_are_literal_data(self):
        for line in ('「あいう」は入力例です。','「あいう」が出力の例でした。',
                     '「あいう」も表記例ではありません。','入力例：「あいう」',
                     '出力の例として「あいう」を示します。','「あいう」という入力例を説明します。',
                     'あいうという表記の例です。'):
            with self.subTest(line=line):
                self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['あいう'])

    def test_example_action_longer_noun_and_unclosed_quote_remain_outside_label(self):
        for line in ('「あいう」は入力例を作ります。','「あいう」は入力例題です。',
                     '「あいう」という出力例外','入力例を調べます。「あいう」を確認します。',
                     '入力例ではない「あいう」','「あいうは入力例です。'):
            with self.subTest(line=line):self.assertEqual(protected_ranges(line),[])
        line='「あいう」は入力例です。「えお」を確認します。'
        self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['あいう'])

    def test_explicit_error_examples_only(self):
        for line in ('「あいう」という誤入力', '誤入力例：「あいう」', '入力ミスの例『あいう』', '“あいう”といった誤字を直す'):
            with self.subTest(line=line):
                ranges=protected_ranges(line)
                self.assertEqual([line[a:b] for a,b in ranges],['あいう'])
        for line in ('「あいう」', '（あいう）という誤字', '「あいう」という言葉', '「あいう」という誤入力装置', '誤入力例ではない「あいう」', '「あいう', '「あいう』という誤字'):
            with self.subTest(line=line):self.assertEqual(protected_ranges(line),[])

    def test_unquoted_error_example_has_a_sentence_boundary(self):
        line='保存が官僚しました。糸を汲むという誤変換の例です。'
        self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['糸を汲む'])
        for text in ('「糸を汲むという誤変換の例です。','（糸を汲む）という誤変換',
                     '糸を汲むという誤変換装置'):
            with self.subTest(text=text):self.assertEqual(protected_ranges(text),[])

    def test_explicit_example_case_marker_stays_literal(self):
        for prefix in ('誤変換の例として','タイプミスの例としては','誤字の例としての'):
            line=prefix+'「保存が官僚した」を示します。'
            with self.subTest(prefix=prefix):
                self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['保存が官僚した'])
        self.assertEqual(protected_ranges('事例として「保存が官僚した」を話しました。'),[])

    def test_quoted_keystrokes_are_text_being_reported(self):
        for tail in ('と入力しました。','と入力したら','とタイプします。','と打った。','と打っても','と打鍵する。','とキー入力した。','を入力しました。',
                     'をキー入力した。','をタイプする。','を打鍵したら'):
            line='「あいう」'+tail
            with self.subTest(tail=tail):
                self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['あいう'])
        for tail in ('と書きました。','と入力仕様を比較した。','とタイプライター','という言葉','を入力欄で直します。',
                     'を入力ミスと呼びます。','を打ち消しました。','を直します。'):
            self.assertEqual(protected_ranges('「あいう」'+tail),[])

    def test_partial_repair_keeps_a_reading_with_multiple_written_forms(self):
        line='きせいせん（規制線、紀勢線、棋聖戦）'
        tk=lambda s:[(s,'名詞','きせいせんきせいせんきせいせん',0,len(s),True,'')]
        self.assertTrue(C._reading_spelled_in_bracket(line,0,3,tk))
        self.assertTrue(C._reading_spelled_in_bracket(line,3,5,tk))
        self.assertFalse(C._reading_spelled_in_bracket('あいう（注釈）',0,3,tk))
        self.assertFalse(C._reading_spelled_in_bracket('あいう（注釈',0,3,tk))

    def test_label_boundary_uses_actual_text_not_truncated_slice(self):
        for count in range(80):
            prefix='「あいう」'+' '*count
            self.assertEqual(protected_ranges(prefix+'という誤入力装置'),[])
            self.assertEqual(protected_ranges(prefix+'という誤入力'),[(1,4)])

    def test_nested_and_multiple_quotes(self):
        line='「あ『い』う」という誤字と「😀え」という誤入力'
        self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['あ『い』う','😀え'])

    def test_escaped_ascii_quote(self):
        line='"a\\"b"という誤入力'
        self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['a\\"b'])

    def test_evidence_is_split_with_reason(self):
        self.assertEqual(subtract_ranges([(0,10,'reason')],[(2,4),(6,8)]),[(0,2,'reason'),(4,6,'reason'),(8,10,'reason')])

    def test_engine_receives_no_literal_characters(self):
        source='前「😀誤字」という誤入力、後'
        seen=[]
        def engine(line):
            seen.append(line)
            return dict(original=line,corrected=line,changed=False,odd_spans=[(0,len(line))],odd_reasons=[(0,len(line),'rule')],unsure_spans=[])
        result=C._with_literal_examples(engine)(source)
        self.assertNotIn('😀誤字',seen[0])
        self.assertEqual(len(seen[0]),len(source))
        self.assertEqual(result['corrected'],source)
        self.assertEqual(result['odd_spans'],[(0,2),(5,len(source))])

    def test_outside_edits_and_offsets_survive(self):
        source='甲「😀誤字」という誤入力、乙'
        def engine(line):
            return dict(original=line,corrected=line.replace('甲','甲甲').replace('乙','丙'),changed=True,original_spans=[],details=[],odd_spans=[],odd_reasons=[],unsure_spans=[])
        result=C._with_literal_examples(engine)(source)
        self.assertEqual(result['corrected'],'甲甲「😀誤字」という誤入力、丙')
        for (a,b),(old,new,_) in zip(result['original_spans'],result['details']):self.assertEqual(source[a:b],old)
        for (a,b),(_,new,_) in zip(result['spans'],result['details']):self.assertEqual(result['corrected'][a:b],new)

    def test_insertions_at_boundaries_do_not_insert_inside_the_protected_text(self):
        from literal_examples import overlaps
        self.assertFalse(overlaps(2,2,[(2,5)]))
        self.assertFalse(overlaps(5,5,[(2,5)]))
        self.assertTrue(overlaps(3,3,[(2,5)]))
        self.assertTrue(overlaps(1,3,[(2,5)]))
        self.assertTrue(overlaps(4,6,[(2,5)]))

    def test_normalizer_cannot_remove_literal(self):
        source='「あいう」という誤入力'
        def engine(line):return dict(corrected=line.replace(' ',''),odd_spans=[],odd_reasons=[],unsure_spans=[])
        self.assertEqual(C._with_literal_examples(engine)(source)['corrected'],source)

    def test_unlabelled_quote_goes_through_unchanged(self):
        seen=[]
        def engine(line):seen.append(line);return {'corrected':line+'!'}
        self.assertEqual(C._with_literal_examples(engine)('「あいう」')['corrected'],'「あいう」!')
        self.assertEqual(seen,['「あいう」'])


    def test_explicit_copular_error_classification_preserves_the_quoted_spelling(self):
        for case in ('は','が','も'):
            for tail in ('誤入力です。','誤字だった。','入力ミスではない。',
                         '誤変換の例でした。','誤記ではありません。'):
                line='「あいう」'+case+tail
                self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['あいう'],line)

    def test_error_action_or_longer_word_is_not_a_copular_example_label(self):
        for tail in ('は誤字を検出します。','が誤入力装置です。',
                     'という誤字装置','は誤字の原因です。'):
            line='「あいう」'+tail
            self.assertEqual(protected_ranges(line),[],line)

    def test_linguistic_assertion_preserves_the_expression_under_discussion(self):
        for tail in ('は成立している。','は、成立しているが説明が必要です。',
                     'は日本語として成立していない。','が自然です。',
                     'は不自然だった。','は正しいですか。','はおかしいでしょう。'):
            line='「見本の誤字」'+tail
            self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['見本の誤字'],line)
        for tail in ('は自然に消えます。','は正しく表示します。','は自然数です。',
                     'は成立条件を満たします。','と書きました。'):
            self.assertEqual(protected_ranges('「見本の誤字」'+tail),[],tail)

    def test_expression_judgment_does_not_freeze_another_occurrence(self):
        line='「見本の誤字」は自然だが、見本の誤字を確認します。'
        self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['見本の誤字'])
        self.assertEqual(protected_ranges('「見本の誤字は自然だ。'),[])


    def test_literal_error_label_and_demonstration_preserve_exact_occurrence(self):
        for before,after in (
            ('誤変換の例は','です。'),
            ('誤りを示すために','と記しました。'),
            ('修正前の表記は','です。'),
        ):
            line=before+'「見本の誤字」'+after+'見本の誤字を直します。'
            self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['見本の誤字'],line)
        for line in ('誤字を直して「見本の誤字」と書きました。',
                     '誤変換の例を直して「見本の誤字」と書きます。',
                     '誤りを説明したあとで「見本の誤字」と話しました。'):
            self.assertEqual(protected_ranges(line),[],line)

    def test_explicit_wrong_right_comparison_preserves_both_spellings(self):
        line='×「見本の誤字」→○「見本の正字」と比較します。'
        self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['見本の誤字','見本の正字'])
        for line in ('「見本の誤字」→「見本の正字」へ移動します。',
                     '×「見本の誤字」を選んで「見本の正字」を描きます。',
                     '×「見本の誤字」→○「見本の正字'):
            self.assertEqual(protected_ranges(line),[],line)


class MaskedCaseTests(unittest.TestCase):
    def test_masked_case_source_head_and_candidate_suffix_are_separate(self):
        import literal_examples as L,oddness as O
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        source='がぞせうを保存したます。';masked='    を保存したます。'
        bound=L.masked_case_ranges(source,[(0,4)]);self.assertEqual(bound,[(4,5)])
        def rows(text):return O.is_odd_run(text,tokenize,with_spans=True,store=a.store,dict_index=a.dict_index)
        self.assertIn(('を','保存',4,7),rows(masked))
        with L.masked_case_scope(source,[(0,4)],masked,bound):
            self.assertNotIn(('を','保存',4,7),rows(masked))
            self.assertIn(('た','ます',8,11),rows(masked))
            self.assertFalse(rows('    を保存してます。'))
            self.assertFalse(L.masked_case_head_bound('    が保存してます。',4,5,7))
            self.assertFalse(L.masked_case_head_bound('    を説明してます。',4,5,7))
            self.assertFalse(L.masked_case_head_bound('    を保存してます。',4,5,6))
            self.assertFalse(L.masked_case_head_bound('を保存してます',0,1,3))
        self.assertIn(('を','保存',4,7),rows(masked))

    def test_masked_case_source_views_require_original_prefix_and_reset(self):
        import literal_examples as L
        source='がぞせうを保存したます。';masked='    を保存したます。'
        bound=L.masked_case_ranges(source,[(0,4)])
        with L.masked_case_scope(source,[(0,4)],masked,bound):
            with L.masked_case_view(masked,4,11):
                self.assertTrue(L.masked_case_head_bound('を保存してます',0,1,3))
                self.assertFalse(L.masked_case_head_bound('を説明してます',0,1,3))
            self.assertTrue(L.masked_case_head_bound(masked,4,5,7))
            with L.masked_case_view('xxxxを保存したます。',4,11):
                self.assertFalse(L.masked_case_head_bound('を保存してます',0,1,3))
            with L.masked_case_view(masked,5,11):
                self.assertFalse(L.masked_case_head_bound('保存してます',0,1,2))
            with self.assertRaises(RuntimeError):
                with L.masked_case_scope(source,[(0,4)],masked,[]):raise RuntimeError()
            self.assertTrue(L.masked_case_head_bound(masked,4,5,7))
        self.assertFalse(L.masked_case_head_bound(masked,4,5,7))

    def test_masked_case_source_missing_proof_and_tab_do_not_bind(self):
        import literal_examples as L
        for source,ranges,masked in (
                ('がぞせうをぷねらします。',[(0,4)],'    をぷねらします。'),
                ('がぞせう\tを保存します。',[(0,4)],'    \tを保存します。'),
                ('本を保存します。',[(0,2)],'  保存します。')):
            with self.subTest(source=source):
                bound=L.masked_case_ranges(source,ranges);self.assertFalse(bound)
                with L.masked_case_scope(source,ranges,masked,bound):
                    self.assertFalse(L.masked_case_head_bound(masked,4,5,7))
        source='がぞせうを保存したます。'
        with L.masked_case_scope(source,[(0,4)],'    を説明したます。',[(4,5)]):
            self.assertFalse(L.masked_case_head_bound('    を説明してます。',4,5,7))

    def test_masked_case_source_tail_still_uses_common_gate(self):
        import app,literal_examples as L
        from tests_analysis_async import initial
        from unittest.mock import patch
        source='がぞせうを保存したます。';a=initial();a.decisions.protect('がぞせう')
        check=C._check_replacement;seen=[]
        def refuse(line,replacement,*args,**kwargs):
            result=check(line,replacement,*args,**kwargs)
            seen.append((line,replacement,result[0] is not None))
            return None,'forced_common_gate_rejection'
        with patch.object(C,'_check_replacement',side_effect=refuse):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        self.assertEqual(result['corrected'],source);self.assertEqual(result['analysis_status'],'complete')
        self.assertTrue(any(ok and '保存して' in replacement[2] for line,replacement,ok in seen))
        self.assertTrue(any(lo<=8 and hi>=11 for lo,hi in result['odd_spans']))
        self.assertTrue(all(lo>=4 for lo,hi in result['odd_spans']))
        self.assertFalse(L.masked_case_head_bound('    を保存してます。',4,5,7))

    def test_declared_edges_require_a_native_case_and_its_original_head_role(self):
        for source,bound in (('がぞせうを保存します。',(4,5)),('がぞせうが届きました。',(4,5)),
                ('未知ぷねらを保存します。',(5,6)),('がぞせうの資料を保存します。',(4,5)),
                ('「がぞせう」を保存します。',(6,7))):
            a=1 if source.startswith('「') else 0
            # The explicit protected lexical atom fixes the original edge.
            b=5 if a else bound[0]
            with self.subTest(source=source):self.assertIn(bound,masked_case_ranges(source,[(a,b)]))
        for source in ('がぞせうをです。','がぞせうをぷねらします。','がぞせうのです。'):
            with self.subTest(source=source):self.assertFalse(masked_case_ranges(source,[(0,4)]))
        # A substring protection does not split an actual known native word.
        self.assertFalse(masked_case_ranges('本を保存します。',[(0,2)]))

    def test_mask_boundary_is_not_a_deletion_reason_and_other_edits_survive(self):
        from decisions import DecisionStore
        source='がぞせうを保存したます。';d=DecisionStore();d.protect('がぞせう')
        def fake_engine(line,**kwargs):
            return dict(corrected=line.replace('を','').replace('たます','てます'),original_spans=[],details=[],odd_spans=[(4,5),(8,10)],odd_reasons=[(4,5,'masked initial case')],unsure_spans=[])
        r=C._with_literal_examples(fake_engine)(source,decisions=d)
        self.assertEqual(r['corrected'],'がぞせうを保存してます。')
        self.assertEqual(r['odd_spans'],[(8,10)])
        self.assertFalse(r['odd_reasons'])

    def test_a_case_substitution_is_not_turned_into_a_protected_range(self):
        from decisions import DecisionStore
        source='がぞせうを保存します。';d=DecisionStore();d.protect('がぞせう')
        def fake_engine(line,**kwargs):return dict(corrected=line.replace('を','が'),odd_spans=[],odd_reasons=[],unsure_spans=[])
        self.assertEqual(C._with_literal_examples(fake_engine)(source,decisions=d)['corrected'],'がぞせうが保存します。')

    def test_actual_initial_state_keeps_declared_word_case_and_repairs_only_bad_tail(self):
        import app
        from tests_analysis_async import initial
        from decisions import DecisionStore
        for source,word,expected in (('がぞせうを保存します。','がぞせう','がぞせうを保存します。'),
                ('がぞせうを保存したます。','がぞせう','がぞせうを保存してます。'),
                ('未知ぷねらを保存します。','未知ぷねら','未知ぷねらを保存します。')):
            a=initial();d=DecisionStore();d.protect(word)
            r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=d,context_vec=None)
            self.assertEqual(r['corrected'],expected);self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')

if __name__=='__main__':unittest.main()

