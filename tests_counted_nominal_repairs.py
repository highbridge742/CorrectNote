# -*- coding: utf-8 -*-
"""Existing anomalies can isolate a noun using its unchanged count and verb."""
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
            result=R._counted_nominal_targets((target,))
            derived=[t for t in result if t!=target]
            self.assertEqual(len(derived),1)
            noun=derived[0]
            self.assertEqual((noun.start,noun.end,noun.text),
                (len(prefix),len(prefix)+3,'ほきん'))
            self.assertEqual(noun.following,'をにさつかいます')
            self.assertEqual(noun.anomalies,target.anomalies)
            self.assertEqual(noun.context,target.context)
            self.assertEqual(R._counted_nominal_targets(result),result)

    def test_quantity_or_unknown_noun_alone_does_not_create_an_anomaly(self):
        target=self.target()
        for source in ('ほんをにさつかいます','ほきんをにさつかいなす',
                       'ほきんをにさつしらゆほます','ほきんをさつかいます'):
            item=self.target(source)
            with self.subTest(source=source):
                self.assertEqual(R._counted_nominal_targets((item,)),[item])
        for item in (replace(target,anomalies=()),replace(target,structural=False),
                     replace(target,anomalies=(('品詞文法','後ろだけ',7,11),)),
                     replace(target,boundary_kind='auxiliary_connection')):
            self.assertEqual(R._counted_nominal_targets((item,)),[item])

    def test_initial_application_recovers_adjacent_intrusions_and_substitutions(self):
        import app
        from kana_layout import single_key_drop_adjacency
        from tests_analysis_async import initial
        a=initial()
        self.assertIs(single_key_drop_adjacency('ほきん','ほん'),True)
        self.assertIs(single_key_drop_adjacency('しりょにう','しりょう'),True)
        for source,expected in (
                ('ほきんをにさつかいます。','ほんをにさつかいます。'),
                ('ほんゃをにさつかいます。','ほんをにさつかいます。'),
                ('にんごをみっつかいます。','リンゴをみっつかいます。'),
                ('しりょにうをにまいよみます。','資料をにまいよみます。')):
            with self.subTest(source=source):
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result.get('odd_spans'),[])

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
