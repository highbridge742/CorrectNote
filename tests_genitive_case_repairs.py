# -*- coding: utf-8 -*-
"""Genitive nouns retain their actual case and independently proved action."""
import unittest
import morphology as M
import reading_segments as R
import contextual_repair as CR
import corrector as C
import kana_layout as K


@unittest.skipUnless(M.dictionary_inflections('会議'),'requires native dictionary')
class GenitiveCaseRepairTests(unittest.TestCase):
    def test_source_case_slot_uses_unchanged_later_object_and_action(self):
        text='あしたのかえぎでしりょうをくばります'
        self.assertEqual(R.native_genitive_argument_slots(text),((0,4,7,len(text)),))
        self.assertFalse(R.native_genitive_object_slots(text))
        # An unknown following object cannot prove the event's で slot.
        # A wider unproved noun before を remains only a lexical target;
        # it does not certify a で boundary inside either unknown reading.
        self.assertFalse(any(case==7 for begin,head,case,finish in
            R.native_genitive_argument_slots('あしたのかえぎでしるょうをくばります')))
        self.assertFalse(R.native_genitive_argument_slots('ぷねらのかえぎでしりょうをくばります'))
        self.assertFalse(R.native_genitive_argument_slots('あしたのかえぎでしりょうをたべます'))

    def test_swallowed_case_needs_the_unchanged_complete_object_clause(self):
        text='へやのいこにほんをいれます'
        self.assertEqual(R.native_genitive_argument_slots(text),((0,3,5,len(text)),))
        self.assertNotIn(5,R.native_case_positions(text,particles=('に',)))
        for tail in ('にぷねらをいれます','にほんをたべます','にほんをいれ'):
            self.assertFalse(any(case==5 for begin,head,case,end in
                R.native_genitive_argument_slots('へやのいこ'+tail)))
        self.assertTrue(CR._changed_genitive_object_allowed(text,3,5,'箱'))
        self.assertFalse(CR._changed_genitive_object_allowed(text,3,5,'猫'))

    def test_candidate_must_fit_the_original_case_not_just_exist(self):
        text='あしたのかえぎでしりょうをくばります'
        for good in ('かいぎ','会議'):
            self.assertTrue(CR._changed_genitive_object_allowed(text,4,7,good),good)
        for bad in ('懐疑','かえ','楓'):
            self.assertFalse(CR._changed_genitive_object_allowed(text,4,7,bad),bad)
        self.assertFalse(CR._changed_genitive_object_allowed(text,0,len(text),text.replace('かえぎ','懐疑')))

    def test_existing_anomaly_and_shared_application_repair(self):
        import app
        from tests_analysis_async import initial
        a=initial();source='あしたのかえぎでしりょうをくばります。'
        self.assertEqual(K.kana_key_distance('え','い'),1.0)
        result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        self.assertIn(result['corrected'],('あしたのかいぎでしりょうをくばります。',
                                          'あしたの会議でしりょうをくばります。'))
        self.assertEqual(result.get('odd_spans'),[])
        source='へやのいこにほんをいれます。'
        result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        self.assertIn(result['corrected'],('へやのはこにほんをいれます。','へやの箱にほんをいれます。'))
        self.assertEqual(result.get('odd_spans'),[])
        for text in ('へやのはこにほんをいれます。','あしたのかいぎでしりょうをくばります。',
                     '会議で資料を配ります。','あしたの会議で資料を配ります。',
                     '会議で食料を配ります。','会議を開きます。'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],text)
                self.assertEqual(result.get('odd_spans'),[])


if __name__=='__main__':unittest.main()
