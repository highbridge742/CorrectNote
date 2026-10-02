# -*- coding: utf-8 -*-
"""Existing anomalies can isolate a noun using its unchanged count and verb."""
from tests_spelling_reference import assert_repaired_spelling
import unittest
from dataclasses import replace
import morphology as M
import contextual_repair as R


@unittest.skipUnless(M.dictionary_inflections('買う'),'requires native dictionary')
class CountedNominalRepairTests(unittest.TestCase):
    def target(self,text='ほきんをにさつかいます',prefix=''):
        start=len(prefix)
        return R.RepairTarget(prefix+text,start,start+len(text),start,start+len(text),
            (('品詞文法','未説明のかな',start,start+3),),True,'','kana_request')

    def test_only_the_affected_noun_is_added_in_original_coordinates(self):
        for prefix in ('','前の文。'):
            target=self.target(prefix=prefix)
            result=R._unexplained_nominal_targets((target,))
            derived=[t for t in result if t!=target]
            self.assertEqual(len(derived),1)
            noun=derived[0]
            self.assertEqual((noun.start,noun.end,noun.text),
                (len(prefix),len(prefix)+3,'ほきん'))
            self.assertEqual(noun.following,'をにさつかいます')
            self.assertEqual(noun.anomalies,target.anomalies)
            self.assertEqual(noun.context,target.context)
            self.assertEqual(R._unexplained_nominal_targets(result),result)

    def test_quantity_or_unknown_noun_alone_does_not_create_an_anomaly(self):
        target=self.target()
        for source in ('ほんをにさつかいます','ほきんをにさつかいなす',
                       'ほきんをにさつしらゆほます','ほきんをさつかいます'):
            item=self.target(source)
            with self.subTest(source=source):
                self.assertEqual(R._unexplained_nominal_targets((item,)),[item])
        for item in (replace(target,anomalies=()),replace(target,structural=False),
                     replace(target,anomalies=(('品詞文法','後ろだけ',7,11),)),
                     replace(target,boundary_kind='auxiliary_connection')):
            self.assertEqual(R._unexplained_nominal_targets((item,)),[item])

    def test_initial_application_recovers_adjacent_intrusions_and_substitutions(self):
        import app
        from kana_layout import single_key_drop_adjacency
        from tests_analysis_async import initial
        a=initial()
        self.assertIs(single_key_drop_adjacency('ほきん','ほん'),True)
        self.assertIs(single_key_drop_adjacency('しりょにう','しりょう'),True)
        for source,expected in (
                ('ほきんをにさつかいます。','本をにさつかいます。'),
                ('ほんゃをにさつかいます。','本をにさつかいます。'),
                ('にんごをみっつかいます。','リンゴをみっつかいます。'),
                ('しりょにうをにまいよみます。','資料をにまいよみます。')):
            with self.subTest(source=source):
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                assert_repaired_spelling(self, result, expected)
                self.assertEqual(result.get('odd_spans'),[])

    def test_written_counter_reuses_the_existing_mark_and_narrow_scope(self):
        import app,corrector as C
        from tests_analysis_async import initial
        a=initial();tk=C.make_tokenizer(a.store)
        source='ほきんを二冊ください'
        self.assertFalse(R._unexplained_nominal_source_targets(source,0,len(source),0,()))
        for text in ('ほきんを二冊ください。','ほきんを二冊かいます。',
                     'ほんゃを二冊よみます。','ほきんを2冊ください。','ほきんを２冊かいます。'):
            targets=R.targets_for_line(text,tk,a.store,a.dict_index)
            self.assertTrue(any(t.text==text[:3] and t.following.startswith(('を二冊','を2冊','を２冊'))
                                and t.anomalies for t in targets),text)
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_repaired_spelling(self, result, '本'+text[3:])
            self.assertEqual(result.get('odd_spans'),[])
        for text in ('ほきんを二冊','ほきんを二冊かいなす','ほきんを二冊しらゆほます'):
            marked=(('品詞文法','元の印',0,3),)
            self.assertFalse(R._unexplained_nominal_source_targets(text,0,len(text),0,marked),text)
        for text in ('「ほきんを二冊ください」を入力しました。','ぷねらを二冊ください。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)

    def test_existing_anomaly_can_isolate_an_unexplained_plain_object(self):
        for text in ('きようりをきります','かぼちんをにます','ぶろっこりへをゆでます'):
            target=self.target(text)
            result=R._unexplained_nominal_targets((target,))
            derived=[t for t in result if t!=target]
            self.assertEqual(len(derived),1,text)
            self.assertEqual(derived[0].text,text[:text.index('を')])
            self.assertEqual(derived[0].anomalies,target.anomalies)
            self.assertEqual(derived[0].context,target.context)
        for text in ('かぼちゃをにます','かぼちんをにま','かぼちんをしらゆほます',
                     'かぼちんを','はふをみます','てはずをかくにんします'):
            target=self.target(text)
            self.assertEqual(R._unexplained_nominal_targets((target,)),[target],text)
        target=replace(self.target('かぼちんをにます'),anomalies=())
        self.assertEqual(R._unexplained_nominal_targets((target,)),[target])

    def test_plain_object_target_does_not_absorb_the_prior_receiver(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        source='おきやくさまにおちゃをだします。'
        result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        assert_repaired_spelling(self, result, 'おきゃくさまにおちゃをだします。')
        self.assertFalse(result['odd_spans'])

    def test_repaired_polite_noun_keeps_its_original_prefix_and_meaning(self):
        import app
        import semantic_roles as S
        from tests_analysis_async import initial
        a=initial()
        surfaces=R._surfaces('おこめ',a.store,a.dict_index,compose=True,original='おごめ')
        self.assertIn('お米',surfaces)
        # Ordinary nominal heads are not returned without their prefix.
        self.assertNotIn('米',surfaces)
        plain=R._surfaces('おこめ',a.store,a.dict_index,compose=True,original='こめ')
        self.assertNotIn('お米',plain)
        evidence=S.candidate_object_evidence('お米','をかいます')
        self.assertTrue(evidence and evidence['shared_roles'])
        self.assertFalse(S.candidate_object_evidence('お米','をよみます')['shared_roles'])
        result=app.correct_line('おみこめをかいます。',a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        self.assertIn(result['corrected'],('お米をかいます。','おこめをかいます。'))
        self.assertFalse(result['odd_spans'])

    def test_unproved_narrow_object_does_not_invent_a_noun_or_revoke_legacy(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        # 42's old おごめ -> おこめ gold required nonadjacent dakuten deletion.
        # Keep that prohibited path absent and the unknown original unchanged.
        self.assertFalse(any(row.reading=='おこめ' for row in R.key_repairs('おごめ',after='を')))
        # 43's Ru expectation came only from prototype39. Its object role
        # remains unclassified; the verified root34 also retains this source.
        for source,expected in (('おごめをかいます。','おごめをかいます。'),
                ('はふをみます。','はふをみます。'),
                ('ごしこしをみます。','ごしごしをみます。'),
                ('おきやくさまにおちゃをだします。','おきゃくさまにおちゃをだします。'),
                ('のてにうむをみます。','のてにうむをみます。')):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_repaired_spelling(self, result, expected, source)

    def test_plain_boundary_reuses_genitive_and_two_word_evidence(self):
        from reading_segments import native_surface_nominal_heads
        for text in ('へやの窓','部屋のまど','部屋の窓'):
            self.assertIn('窓',native_surface_nominal_heads(text),text)
        for text in ('へやのぷねら','ぷねらの窓','ブロッコリーへ'):
            self.assertFalse(native_surface_nominal_heads(text),text)
        for original,changed in (
                ('へやのまとづをあけます','へやの窓をあけます'),
                ('あしたのかえぎでしりょうをくばります','あしたの会議でしりょうをくばります'),
                ('きょじえかくらんを調べます','挙動確認を調べます')):
            self.assertTrue(R._changed_object_slot_allowed(original,0,len(original),changed),original)
        self.assertFalse(R._changed_object_slot_allowed('ぶろっこりへをゆでます',
            0,len('ぶろっこりへ'),'ブロッコリーへ'))

    def test_normal_counted_objects_and_forbidden_deletion_are_retained(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('ほんをにさつかいます。','りんごをみっつかいます。',
                     'しりょうをにまいよみます。','もんじにゅうりょく。'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],text)
                self.assertEqual(result.get('odd_spans'),[])


if __name__=='__main__':unittest.main()
