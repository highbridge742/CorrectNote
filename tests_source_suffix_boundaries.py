# -*- coding: utf-8 -*-
from tests_spelling_reference import assert_reviewed_source_spelling
from tests_spelling_reference import assert_repaired_spelling
import unittest
import morphology as M
import app,corrector as C,contextual_repair as Q,reading_segments as R
from tests_analysis_async import initial

@unittest.skipUnless(M.HAS_JANOME,'requires native Janome dictionary')
class SourceSuffixBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=initial();cls.tok=staticmethod(C.make_tokenizer(cls.a.store))
    def test_marked_basic_verb_keeps_the_original_suru_connective(self):
        source='本を貸すして戻ります。'
        targets=Q.targets_for_line(source,self.tok,self.a.store,self.a.dict_index)
        wide=[t for t in targets if (t.start,t.end,t.text)==(2,5,'貸すし')]
        self.assertEqual(len(wide),1)
        self.assertFalse(any((t.start,t.end)==(2,4) for t in targets))
        self.assertEqual(wide[0].following,'て戻ります')
        self.assertTrue(any(a==2 and b==5 for _,_,a,b in wide[0].anomalies))
        for source in ('本を貸して戻ります。','本を貸すし、話もします。',
                       '本を貸す。して戻ります。','本を貸す\tして戻ります。'):
            with self.subTest(source=source):
                targets=Q.targets_for_line(source,self.tok,self.a.store,self.a.dict_index)
                self.assertFalse(any(t.text=='貸すし' for t in targets))

    def test_replaced_basic_verb_scope_is_not_consumed_by_finite_tail_again(self):
        for source,expected in (('本を貸すしてみました。','本を貸してみました。'),
                                ('本を貸すしています。','本を貸しています。')):
            with self.subTest(source=source):
                a=initial();tok=C.make_tokenizer(a.store)
                targets=Q.targets_for_line(source,tok,a.store,a.dict_index)
                self.assertEqual(len([t for t in targets if (t.start,t.end)==(2,5)]),1)
                self.assertFalse(any((t.start,t.end)==(2,4) for t in targets))
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result['odd_spans'],[])
                self.assertEqual(result['analysis_status'],'complete')

    def test_marked_basic_verb_link_finishes_through_shared_checks(self):
        from unittest.mock import patch
        for source,expected in (('本を貸すして戻ります。','本を貸して戻ります。'),
                                ('本を貸すして帰ります。','本を貸して帰ります。')):
            with self.subTest(source=source):
                a=initial()
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result['odd_spans'],[])
                self.assertEqual(result['analysis_status'],'complete')
        a=initial();source='本を貸すして戻ります。'
        with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                decisions=a.decisions,context_vec=None)
        self.assertEqual(result['corrected'],source)
        self.assertTrue(result['odd_spans'])

    def test_marked_basic_verb_link_retains_keys_meaning_and_quotes(self):
        rows=(('資料を出すして戻ります。','資料を出して戻ります。'),
              ('税を課すして戻ります。','税を課して戻ります。'),
              ('辞書を貸すして戻ります。','辞書を貸して戻ります。'))
        for source,forbidden in rows:
            with self.subTest(source=source):
                a=initial()
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None)
                self.assertNotEqual(result['corrected'],forbidden)
        for source in ('本を貸して戻ります。','本を貸すし、話もします。',
                       '「本を貸すして戻ります」と入力しました。'):
            with self.subTest(source=source):
                a=initial()
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None)
                self.assertEqual(result['corrected'],source)

    def test_source_suru_link_requires_a_later_clause_not_a_trailing_particle(self):
        for source in ('宇佐したら','宇佐したら。','宇佐したらば','宇佐しましたら',
                       '宇佐して','宇佐しても','宇佐すれば'):
            with self.subTest(source=source):
                target=next(t for t in Q.targets_for_line(source,self.tok,self.a.store,self.a.dict_index)
                            if t.text=='宇佐')
                self.assertFalse(Q._source_marked_nominal_suru_omission(target,'うさ'))
        for source in ('宇佐したら戻ります。','宇佐したらば戻ります。',
                       '宇佐してから戻ります。','宇佐してぽねます。'):
            target=next(t for t in Q.targets_for_line(source,self.tok,self.a.store,self.a.dict_index)
                        if t.text=='宇佐')
            self.assertTrue(Q._source_marked_nominal_suru_omission(target,'うさ'))

    def test_source_unfinished_suru_link_retains_body_and_anomaly(self):
        for source in ('宇佐したら','宇佐しましたら','宇佐したらば'):
            with self.subTest(source=source):
                a=initial()
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None)
                self.assertEqual(result['corrected'],source)
                self.assertTrue(result['odd_spans'])
                self.assertEqual(result['analysis_status'],'complete')

    def test_original_conditional_auxiliary_keeps_its_actual_verb_scope(self):
        for source,start,prefix in (
                ('宇佐したら戻ります。',2,'したら'),
                ('宇佐しましたら戻ります。',2,'しましたら'),
                ('本を読んだら返します。',2,'読んだら'),
                ('書いたら戻ります。',0,'書いたら')):
            with self.subTest(source=source):
                self.assertIn(start+len(prefix),R.native_predicate_link_boundaries(source,start))
        for source,start in (('宇佐しだら戻ります。',2),('宇佐し\tたら戻ります。',2),
                             ('書いだら戻ります。',0),('読んたら戻ります。',0),
                             ('宇佐したら戻ります。',3)):
            self.assertFalse(R.native_predicate_link_boundaries(source,start),source)
        source='宇佐したら戻ります。'
        target=next(t for t in Q.targets_for_line(source,self.tok,self.a.store,self.a.dict_index)
                    if t.text=='宇佐')
        self.assertTrue(Q._source_marked_nominal_suru_omission(target,'うさ'))

    def test_original_conditional_suru_omission_keeps_shared_validation(self):
        from unittest.mock import patch
        for source,expected in (('宇佐したら戻ります。','操作したら戻ります。'),
                                ('あとで宇佐したら戻ります。','あとで操作したら戻ります。')):
            with self.subTest(source=source):
                a=initial()
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result['odd_spans'])
                self.assertEqual(result['analysis_status'],'complete')
        for source in ('操作したら戻ります。','宇佐に着いたら戻ります。',
                       '「宇佐したら戻ります」と入力します。','宇佐し\tたら戻ります。'):
            a=initial()
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                decisions=a.decisions,context_vec=None)
            self.assertEqual(result['corrected'],source)
        a=initial()
        with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')):
            result=app.correct_line('宇佐したら戻ります。',a.store,input_method='kana',dict_index=a.dict_index,
                decisions=a.decisions,context_vec=None)
        self.assertNotEqual(result['corrected'],'操作したら戻ります。')
        self.assertTrue(result['odd_spans'])

    def test_source_suru_link_owns_omission_without_later_predicate_proof(self):
        for source in ('宇佐してから戻ります。','宇佐して帰ります。','宇佐すれば戻ります。',
                       '宇佐してぽねます。'):
            with self.subTest(source=source):
                target=next(t for t in Q.targets_for_line(source,self.tok,self.a.store,self.a.dict_index)
                            if t.text=='宇佐')
                self.assertTrue(Q._source_marked_nominal_suru_omission(target,'うさ'))
        for source in ('宇佐しで戻ります。','宇佐し\tて戻ります。','宇佐し'):
            target=next(t for t in Q.targets_for_line(source,self.tok,self.a.store,self.a.dict_index)
                        if t.text=='宇佐')
            self.assertFalse(Q._source_marked_nominal_suru_omission(target,'うさ'),source)

    def test_source_suru_link_finishes_only_through_the_shared_candidate_gate(self):
        from unittest.mock import patch
        for source,expected in (
                ('宇佐してから戻ります。','操作してから戻ります。'),
                ('宇佐して帰ります。','操作して帰ります。'),
                ('宇佐すれば戻ります。','操作すれば戻ります。')):
            with self.subTest(source=source):
                a=initial()
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result['odd_spans'])
                self.assertEqual(result['analysis_status'],'complete')
        for source in ('宇佐に行ってから戻ります。','操作してから戻ります。',
                       '「宇佐してから戻ります」と入力します。','宇佐し\tて戻ります。'):
            a=initial()
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                decisions=a.decisions,context_vec=None)
            self.assertEqual(result['corrected'],source)
        a=initial()
        result=app.correct_line('宇佐してぽねます。',a.store,input_method='kana',dict_index=a.dict_index,
            decisions=a.decisions,context_vec=None)
        self.assertTrue(result['odd_spans'])
        self.assertTrue(result['corrected'].endswith('ぽねます。'))
        a=initial()
        with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')):
            result=app.correct_line('宇佐してから戻ります。',a.store,input_method='kana',dict_index=a.dict_index,
                decisions=a.decisions,context_vec=None)
        self.assertNotEqual(result['corrected'],'操作してから戻ります。')
        self.assertTrue(result['odd_spans'])

    def test_marked_nominal_suru_shares_original_omission_scope(self):
        from dataclasses import replace
        source='宇佐します。'
        target=next(t for t in Q.targets_for_line(source,self.tok,self.a.store,self.a.dict_index)
                    if t.text=='宇佐')
        self.assertTrue(Q._source_marked_nominal_suru_omission(target,'うさ'))
        self.assertFalse(Q._source_marked_nominal_suru_omission(target,'そうさ'))
        self.assertFalse(Q._source_marked_nominal_suru_omission(replace(target,anomalies=()),'うさ'))
        self.assertFalse(Q._source_marked_nominal_suru_omission(replace(target,end=1),'うさ'))
        for source in ('宇佐し','宇佐です。','宇佐\tします。','保存します。','ぽねします。'):
            for target in Q.targets_for_line(source,self.tok,self.a.store,self.a.dict_index):
                self.assertFalse(Q._source_marked_nominal_suru_omission(target,'うさ'),source)
        target=next(t for t in Q.targets_for_line('宇佐します。',self.tok,self.a.store,self.a.dict_index)
                    if t.text=='宇佐')
        selected,report=Q.resolve(target,C,self.tok,self.a.store,self.a.dict_index,self.a.decisions)
        rows=[row for row in report['candidates'] if row['surface']=='操作']
        self.assertTrue(rows)
        self.assertTrue(any(row['repair']['operation']=='omission'
                            and row['repair']['reading']=='そうさ' for row in rows))

    def test_nominal_suru_omission_keeps_the_shared_gate_and_written_names(self):
        from unittest.mock import patch
        for source in ('宇佐です。','宇佐に行きます。','宇佐は町です。',
                       '「宇佐します」と入力します。','保存します。','操作します。'):
            a=initial()
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                decisions=a.decisions,context_vec=None)
            self.assertEqual(result['corrected'],source)
            self.assertEqual(result['analysis_status'],'complete')
        a=initial()
        with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')):
            result=app.correct_line('宇佐します。',a.store,input_method='kana',dict_index=a.dict_index,
                decisions=a.decisions,context_vec=None)
        self.assertNotEqual(result['corrected'],'操作します。')
        self.assertTrue(result['odd_spans'])

    def test_marked_lexical_head_reuses_written_suru_only_with_source_arguments(self):
        rows=(
            ('メモの内容を別のファイルに宇佐します。',
             'メモの内容を別のファイルに移します。',False),
            ('メモの内容を別のファイルに宇冊します。',
             'メモの内容を別のファイルに移します。',False),
            ('絵を紙に宇佐します。','絵を紙に写します。',False),
            ('病気を人に宇佐します。','病気を人に移します。',False),
            ('メモの内容を別のファイルに宇佐し',
             'メモの内容を別のファイルに宇佐し',True),
            ('宇佐します。','操作します。',False),
            ('それを宇佐します。','それを宇佐します。',True),
            ('絵を紙に写してから宇佐します。',
             '絵を紙に写してから操作します。',False),
            ('メモの内容を別のファイルに保存します。',
             'メモの内容を別のファイルに保存します。',False),
            ('文書をメールに添付します。','文書をメールに添付します。',False),
            ('資料を出すしました。','資料を出すしました。',True),
            ('税を課すしました。','税を課すしました。',True),
            ('本を貸すしました。','本を貸しました。',False),
            ('読んだ本を友人に課すしました。',
             '読んだ本を友人に貸しました。',False),
            ('資料を出しました。','資料を出しました。',False),
            ('税を課しました。','税を課しました。',False),
            ('本を貸しました。','本を貸しました。',False),
        )
        complete_verb='読んだ本を友人に課すしました。'
        targets=Q.targets_for_line(complete_verb,self.tok,self.a.store,self.a.dict_index)
        self.assertFalse(any(t.text=='課すし' and t.boundary_kind=='auxiliary_connection'
                             for t in targets))
        for source,expected,purple in rows:
            with self.subTest(source=source):
                result=app.correct_line(source,self.a.store,input_method='kana',
                    dict_index=self.a.dict_index,context_vec=None,decisions=self.a.decisions)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(bool(result.get('odd_spans')),purple)

    def test_continuative_quantity_keeps_the_original_verb_in_both_initial_stages(self):
        from janome_import import import_from_janome
        a=initial()
        for phase in ('seed','fresh'):
            if phase=='fresh':import_from_janome(a.store)
            for text in ('たべふたことで','朝食をたべふたことで説明しました。',
                         '資料をよみふたことで説明しました。','席にすわりふたことで説明しました。'):
                with self.subTest(phase=phase,text=text):
                    result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                        context_vec=a.context_vec if phase=='fresh' else None,decisions=a.decisions)
                    # An actual adjacent ふ can now be removed without changing the verb.
                    expected='食べたことで' if text=='たべふたことで' else text
                    self.assertEqual(result['corrected'],expected)
                    self.assertEqual(bool(result.get('odd_spans')),expected==text)
        self.assertFalse(Q._kana_grammar_boundary(self.tok('たべふたことで'),0,4))

    def test_native_noun_alternatives_do_not_become_verb_errors(self):
        from janome_import import import_from_janome
        a=initial()
        # An arbitrary following noun is not the prefix boundary that this
        # kana-source proof owns. Existing whole-word repairs keep that scope.
        for text in ('ひどりぐらし','こりくつ','まげゆ','あけさげ'):
            self.assertEqual(R.native_nominal_verb_prefix_ranges(text),())
        for phase in ('seed','fresh'):
            if phase=='fresh':import_from_janome(a.store)
            for text in ('こたえふたことでおわります。','おしえふたことでかわる。',
                         'つたえふたことで','きめふたことで'):
                with self.subTest(phase=phase,text=text):
                    self.assertFalse(Q._kana_nominal_boundary_spans(self.tok(text)))
                    head=next(iter(M.tokenize(text)))
                    self.assertIn((0,head.end),R.native_context_ranges(text))
                    self.assertFalse(R.preserves_native_nominal_verb_prefix(text,'別語'+text[head.end:]))
                    r=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                        context_vec=a.context_vec if phase=='fresh' else None,decisions=a.decisions)
                    expected={'つたえふたことで':'伝えたことで','きめふたことで':'決めたことで'}.get(text,text)
                    self.assertEqual(r['corrected'],expected)
                    # Longer unresolved clauses retain their original purple.
                    if expected!=text:self.assertFalse(r.get('odd_spans'))

    def test_native_auxiliary_fragments_do_not_preempt_whole_word_repair(self):
        rows=(('すげるつぉを確認しました。','すけるつぉを確認しました。',False),
              ('へんそゅう','編集',False),
              ('ゆしつゅがありました。','輸出がありました。',False),
              ('くわかたむしに行きます。','くわがたむしに行きます。',False),
              ('まこつなを確認しました。','小松菜を確認しました。',False),
              ('うこほうに行きます。','うこほうに行きます。',True),
              ('これはしんつせです。','これはしんつせです。',True),
              ('もじりつ','文字列',False),
              ('ゆしつがありました。','輸出がありました。',False))
        from janome_import import import_from_janome
        for phase in ('seed','fresh'):
            a=initial()
            if phase=='fresh':import_from_janome(a.store)
            for text,expected,purple in rows:
                with self.subTest(phase=phase,text=text):
                    # These rare words require the initial native-dictionary import.
                    # Do not borrow a previous test's mutable store or count seed gaps as successes.
                    if phase=='seed' and text=='すげるつぉを確認しました。':
                        expected=text;purple=True
                    r=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                                       context_vec=None,decisions=a.decisions)
                    assert_repaired_spelling(self, r, expected)
                    self.assertEqual(bool(r.get('odd_spans')),purple)

    def test_revised_adjacency_does_not_restore_excluded_old_targets(self):
        from kana_layout import kana_key_distance,single_key_drop_adjacency
        from janome_import import import_from_janome
        for left,right in (('つ','し'),('ら','れ'),('す','し'),('そ','し')):
            self.assertGreater(kana_key_distance(left,right),1.0)
        for left,right in (('は','し'),('り','れ')):
            self.assertEqual(kana_key_distance(left,right),1.0)
        self.assertFalse(single_key_drop_adjacency('だすしました','だしました'))
        # The old edit targets require keys excluded by the user's new policy.
        # A different candidate still needs its own physical and lexical proof;
        # do not assert that an ambiguous misspelling must mean 編集.
        a=initial()
        for phase in ('seed','fresh'):
            if phase=='fresh':import_from_janome(a.store)
            for source,excluded in (('へんつゅう','編集'),('もじらつ','文字列')):
                with self.subTest(phase=phase,source=source):
                    r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                        context_vec=None,decisions=a.decisions)
                    self.assertNotEqual(r['corrected'],excluded)
                    self.assertEqual(r.get('analysis_status'),'complete')
                    if source=='もじらつ':
                        self.assertEqual(r['corrected'],source);self.assertTrue(r.get('odd_spans'))

    def test_native_mixed_noun_proof_does_not_take_an_unknown_suffix(self):
        for text in ('モーシょんの確認','モーシょんです','モーシょんでした'):
            self.assertIn((0,len(text)),R.native_mixed_kana_word_ranges(text),text)
        for text in ('モーシろょんです','プネろょんです','モーシょんプネラ','モーシょんなるこ'):
            self.assertEqual(R.native_mixed_kana_word_ranges(text),(),text)
    def test_initial_stages_keep_source_text_and_physical_intrusion_contract(self):
        from janome_import import import_from_janome
        a=initial()
        for phase in ('seed','fresh'):
            if phase=='fresh':import_from_janome(a.store)
            rows=[('モーシろょん'+tail,'モーション'+tail) for tail in
                     ('と入力します。','を作ります。','の確認','です。','でした。','だった。')]
            rows += [(t,t) for t in ('つたえることで','つたえたことで','つたえかたで','ことづけで',
                     'ひとことで','ふたことで','よろこぶことで','かくことで','するために',
                     '伝え、二言で説明する。','つたえ、ふたことでせつめいする。',
                     '「つたえふたことで」と入力します。','「つたえふたことで」という文字列',
                     'モーシょんと入力します。','モーシょんの確認','モーシょんです。')]
            for text,expected in rows:
                with self.subTest(phase=phase,text=text):
                    r=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                        context_vec=a.context_vec if phase=='fresh' else None,decisions=a.decisions)
                    assert_reviewed_source_spelling(self, r['corrected'], expected);self.assertEqual(r.get('odd_spans'),[])
            for text in ('つたえむたことで','プネろょんです。'):
                with self.subTest(phase=phase,text=text):
                    r=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                        context_vec=a.context_vec if phase=='fresh' else None,decisions=a.decisions)
                    self.assertEqual(r['corrected'],text);self.assertTrue(r.get('odd_spans'))
if __name__=='__main__':unittest.main()
