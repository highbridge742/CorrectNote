# -*- coding: utf-8 -*-
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
            ('宇佐します。','宇佐します。',True),
            ('それを宇佐します。','それを宇佐します。',True),
            ('絵を紙に写してから宇佐します。',
             '絵を紙に写してから宇佐します。',True),
            ('メモの内容を別のファイルに保存します。',
             'メモの内容を別のファイルに保存します。',False),
            ('文書をメールに添付します。','文書をメールに添付します。',False),
            ('資料を出すしました。','資料を出すしました。',True),
            ('税を課すしました。','税を課すしました。',True),
            ('本を貸すしました。','本を貸すしました。',True),
            ('読んだ本を友人に課すしました。',
             '読んだ本を友人に課すしました。',True),
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
              ('へんつゅう','編集',False),
              ('ゆしつゅがありました。','輸出がありました。',False),
              ('くわかたむしに行きます。','くわがたむしに行きます。',False),
              ('まこつなを確認しました。','こまつなを確認しました。',False),
              ('うこほうに行きます。','うこほうに行きます。',True),
              ('これはしんつせです。','これはしんつせです。',True),
              ('もじらつ','文字列',False),
              ('ゆしつがありました。','輸出がありました。',False))
        from janome_import import import_from_janome
        for phase in ('seed','fresh'):
            a=initial()
            if phase=='fresh':import_from_janome(a.store)
            for text,expected,purple in rows:
                with self.subTest(phase=phase,text=text):
                    # These rare words require the initial native-dictionary import.
                    # Do not borrow a previous test's mutable store or count seed gaps as successes.
                    if phase=='seed' and text in ('すげるつぉを確認しました。','まこつなを確認しました。'):
                        expected=text;purple=True
                    r=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                                       context_vec=None,decisions=a.decisions)
                    assert_repaired_spelling(self, r, expected)
                    self.assertEqual(bool(r.get('odd_spans')),purple)

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
                    self.assertEqual(r['corrected'],expected);self.assertEqual(r.get('odd_spans'),[])
            for text in ('つたえむたことで','プネろょんです。'):
                with self.subTest(phase=phase,text=text):
                    r=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                        context_vec=a.context_vec if phase=='fresh' else None,decisions=a.decisions)
                    self.assertEqual(r['corrected'],text);self.assertTrue(r.get('odd_spans'))
if __name__=='__main__':unittest.main()
