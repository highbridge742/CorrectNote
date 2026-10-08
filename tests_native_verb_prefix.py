# -*- coding: utf-8 -*-
import unittest
from dataclasses import replace
import morphology as M
import contextual_repair as C


@unittest.skipUnless(M.dictionary_inflections('読み'),'requires native dictionary')
class NativeVerbPrefixTests(unittest.TestCase):
    def test_genitive_reuses_the_same_positive_compound_noun_proof(self):
        from unittest.mock import patch
        import reading_segments as R,semantic_roles as S
        self.assertEqual(R.native_surface_nominal_heads('読み入力'),('読み入力',))
        for source,expected in (('読み入力の設定',('設定',)),('文字の読み入力',('読み入力',))):
            with self.subTest(source=source):
                self.assertEqual(R.native_surface_nominal_heads(source),expected)
                self.assertTrue(R.native_genitive_nominal_splits(source))
        for source in ('読み処方の設定','文字の読み処方','読みぽねの設定','文字の読ま入力'):
            with self.subTest(control=source):self.assertFalse(R.native_surface_nominal_heads(source))
        try:
            with patch.object(S,'nominal_compound_support',return_value=False):
                R.native_surface_nominal_heads.cache_clear();R.native_genitive_nominal_splits.cache_clear()
                self.assertFalse(R.native_surface_nominal_heads('読み入力の設定'))
                self.assertFalse(R.native_surface_nominal_heads('文字の読み入力'))
        finally:
            R.native_surface_nominal_heads.cache_clear();R.native_genitive_nominal_splits.cache_clear()

    def test_original_genitive_noun_owns_the_continuative_nominal_boundary(self):
        from unittest.mock import patch
        import reading_segments as R,corrector as E,oddness as O
        from tests_analysis_async import initial
        from last_choice import set_active
        try:
            for source,span in (('読み乳力の設定を確認します。',(0,2)),
                                ('文字の読み乳力を確認します。',(3,5))):
                with self.subTest(source=source):
                    self.assertIn(span,R.native_nominal_verb_prefix_ranges(source))
                    a=initial();tk=E.make_tokenizer(a.store);rows=list(tk(source))
                    head=next(t for t in rows if t[3:5]==span);tail=next(t for t in rows if t[3]==span[1])
                    self.assertTrue(O._native_nominal_prefix_join_mismatch(source,head,tail))
                    with patch.object(O,'can_join',return_value=None):
                        self.assertFalse(O._native_nominal_prefix_join_mismatch(source,head,tail))
                    with patch.object(R,'_native_genitive_nominal_neighbor',return_value=False):
                        self.assertNotIn(span,R.native_nominal_verb_prefix_ranges(source))
                    parts=M.tokenize(source);idx=next(i for i,t in enumerate(parts) if t.surface=='の')
                    before=idx==1;owner=parts[0] if before else parts[idx+1]
                    for field,value in (('reading','ぽね'),('start',owner.start+1),('infl_form','未然形')):
                        altered=M.Token(**{**{k:getattr(owner,k) for k in owner.__slots__},field:value})
                        bad=[altered if t is owner else t for t in parts]
                        self.assertFalse(R._native_genitive_nominal_neighbor(source,bad,idx,before))
            for source in ('読み乳力のぽねを確認します。','ぽねの読み乳力を確認します。',
                    '文字の読ま乳力を確認します。','読むの設定','読み乳力の',
                    '読み乳力の\t設定を確認します。'):
                with self.subTest(control=source):self.assertFalse(R.native_nominal_verb_prefix_ranges(source))
            self.assertEqual(R.native_nominal_verb_prefix_ranges('文字の\t読み乳力を確認します。'),((4,6),))
        finally:set_active(None)

    def test_genitive_nominal_repair_keeps_source_meaning_and_common_gate(self):
        from unittest.mock import patch
        import app,corrector as E
        from tests_analysis_async import initial
        from last_choice import set_active
        def run(source):
            a=initial()
            return app.correct_line(source,a.store,dict_index=a.dict_index,decisions=a.decisions,
                                    context_vec=None,input_method='kana')
        try:
            for source in ('読み乳力の設定を確認します。','文字の読み乳力を確認します。'):
                result=run(source)
                with self.subTest(source=source):
                    self.assertEqual(result['corrected'],source.replace('乳力','入力'))
                    self.assertFalse(result['odd_spans'])
                    self.assertEqual(result['analysis_status'],'complete')
                with patch.object(E,'_check_replacement',return_value=(None,'forced_common_gate')):
                    self.assertEqual(run(source)['corrected'],source)
            for source in ('読み入力の設定を確認します。','文字の読み入力を確認します。',
                    '読み手の説明を聞きます。','「文字の読み乳力」と入力します。',
                    '読み乳力の\t設定を確認します。'):
                with self.subTest(control=source):self.assertEqual(run(source)['corrected'],source)
        finally:set_active(None)

    def test_original_modifier_and_nominal_join_own_the_same_tail(self):
        from unittest.mock import patch
        import reading_segments as R
        source='この読み乳力を確認します。'
        original=C.RepairTarget(source,0,6,0,len(source),(('読み','乳',2,5),),False,source[6:])
        narrow=replace(original,start=4)
        self.assertEqual(C._native_modified_nominal_prefix_targets([original]),[original,narrow])
        self.assertEqual(C._native_modified_nominal_prefix_targets([original,narrow]),[original,narrow])
        self.assertEqual(narrow.context,original.context)
        self.assertEqual(narrow.anomalies,original.anomalies)
        with patch.object(R,'native_adnominal_modifier_parts',return_value=()):
            self.assertEqual(C._native_modified_nominal_prefix_targets([original]),[original])
        with patch.object(M,'dictionary_inflections',return_value=()):
            self.assertEqual(C._native_modified_nominal_prefix_targets([original]),[original])
        for item in (replace(original,anomalies=(('読み','乳',1,5),)),
                replace(original,anomalies=(('読み','乳',2,5),('こ','の',0,2))),
                replace(original,spelling=('owned',)),replace(original,preserved_head='この'),
                replace(original,boundary_kind='kana_predicate')):
            with self.subTest(item=item):self.assertEqual(C._native_modified_nominal_prefix_targets([item]),[item])

    def test_completed_modifier_fallback_keeps_its_proved_nominal_tail(self):
        import corrector as E
        from tests_analysis_async import initial
        from last_choice import set_active
        try:
            a=initial();tk=E.make_tokenizer(a.store)
            for source,edge,end in (('新しい読み乳力を使います。',5,7),
                    ('この読み乳力を確認します。',4,6)):
                targets=C.targets_for_line(source,tk,a.store,a.dict_index)
                with self.subTest(source=source):
                    wide=next(t for t in targets if t.start==0 and t.end==end)
                    narrow=next(t for t in targets if (t.start,t.end)==(edge,end))
                    self.assertEqual(narrow.anomalies,wide.anomalies)
                    self.assertEqual(narrow.context,wide.context)
                    self.assertEqual(narrow.text,'乳力')
                    self.assertFalse(narrow.structural)
        finally:set_active(None)

    def test_modified_nominal_repair_keeps_the_original_head_and_common_gate(self):
        from unittest.mock import patch
        import app,corrector as E
        from tests_analysis_async import initial
        from last_choice import set_active
        def run(source):
            a=initial()
            return app.correct_line(source,a.store,dict_index=a.dict_index,decisions=a.decisions,
                                    context_vec=None,input_method='kana')
        try:
            for source in ('新しい読み乳力を使います。','この読み乳力を確認します。'):
                with self.subTest(source=source):
                    result=run(source)
                    self.assertEqual(result['corrected'],source.replace('乳力','入力'))
                    self.assertFalse(result['odd_spans'])
                    self.assertEqual(result['analysis_status'],'complete')
            source='この読み乳力を確認します。'
            with patch.object(E,'_check_replacement',return_value=(None,'forced_common_gate')):
                self.assertEqual(run(source)['corrected'],source)
            for source in ('この読み入力を確認します。','新しい読み手を紹介します。',
                    '「この読み乳力」と入力します。','読み\t乳力を確認します。'):
                with self.subTest(control=source):self.assertEqual(run(source)['corrected'],source)
        finally:set_active(None)

    def target(self,source='読み乳力します'):
        return C.RepairTarget(source,0,4,0,len(source),(('力','し',3,5),),True,source[4:])

    def test_same_source_facts_and_wide_candidate_are_retained(self):
        original=self.target()
        targets=C._native_verb_prefix_targets([original])
        self.assertIn(original,targets)
        self.assertEqual(len(targets),2)
        narrow=next(t for t in targets if t.start==2)
        self.assertEqual(narrow.text,'乳力')
        self.assertEqual(narrow.anomalies,original.anomalies)
        self.assertEqual(narrow.context,original.context)
        self.assertEqual(narrow.following,original.following)
        self.assertEqual(C._native_verb_prefix_targets(targets),targets)

    def test_changed_prefix_and_owned_spelling_do_not_supply_a_seam(self):
        from unittest.mock import patch
        import oddness as O
        original=self.target()
        # This exact join now has independent same-reading noun evidence.
        # It permits only the tail scope; the written head and all original
        # facts remain owned by the same source, and the wide scope remains.
        join=replace(original,anomalies=(('読み','乳',0,3),))
        targets=C._native_verb_prefix_targets([join])
        self.assertEqual(targets,[join,replace(join,start=2)])
        self.assertEqual(targets[1].text,'乳力')
        with patch.object(O,'_native_nominal_prefix_join_mismatch',return_value=False):
            self.assertEqual(C._native_verb_prefix_targets([join]),[join])
        for target in (replace(original,anomalies=(('読','み',0,2),)),
                       replace(original,anomalies=(('読み','乳',0,3),('読','み',0,2))),
                       replace(original,spelling=('source-fact',)),
                       replace(original,preserved_head='読み'),
                       replace(original,boundary_kind='kana_predicate'),
                       self.target('読む乳力します'),self.target('読み退見ます')):
            with self.subTest(target=target):
                self.assertEqual(C._native_verb_prefix_targets([target]),[target])

    def test_native_prefix_keeps_its_text_when_following_homophone_is_repaired(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for text,expected in (
            ('隣のキーを巻き込み乳力してしまいます。','隣のキーを巻き込み入力してしまいます。'),
            ('文字を読み乳力します。','文字を読み入力します。'),
            ('文章を選び乳力します。','文章を選び入力します。'),
            ('隣のキーを巻き込み入力してしまいます。','隣のキーを巻き込み入力してしまいます。'),
            ('文字を読み入力します。','文字を読み入力します。'),
            ('書類を読み入籍します。','書類を読み入籍します。'),
            ('乳牛の乳を搾ります。','乳牛の乳を搾ります。')):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None,input_method='kana')
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result['odd_spans'],[])
        text='雨が降る前に洗濯物を取り退見ます。'
        result=app.correct_line(text,a.store,dict_index=a.dict_index,
            decisions=a.decisions,context_vec=None,input_method='kana')
        # The exact source reading とりひみ now has adjacent ひ→こ proof.
        self.assertEqual(result['corrected'],'雨が降る前に洗濯物を取り込みます。')
        self.assertFalse(result['odd_spans'])
        result=app.correct_line('荷物を受け市取って住所を確かめます。',a.store,dict_index=a.dict_index,
            decisions=a.decisions,context_vec=None,input_method='kana')
        self.assertEqual(result['corrected'],'荷物を受け取って住所を確かめます。')
        self.assertEqual(result['odd_spans'],[])


if __name__=='__main__':unittest.main()
