# -*- coding: utf-8 -*-
"""Genitive nouns retain their actual case and independently proved action."""
from tests_spelling_reference import assert_repaired_spelling
import unittest
import morphology as M
import reading_segments as R
import contextual_repair as CR
import corrector as C
import kana_layout as K


@unittest.skipUnless(M.dictionary_inflections('会議'),'requires native dictionary')
class GenitiveCaseRepairTests(unittest.TestCase):
    def test_source_case_slot_uses_unchanged_later_object_and_action(self):
        text='あしたのかうぎでしりょうをくばります'
        self.assertEqual(R.native_genitive_argument_slots(text),((0,4,7,len(text)),))
        self.assertFalse(R.native_genitive_object_slots(text))
        # An unknown following object cannot prove the event's で slot.
        # A wider unproved noun before を remains only a lexical target;
        # it does not certify a で boundary inside either unknown reading.
        self.assertFalse(any(case==7 for begin,head,case,finish in
            R.native_genitive_argument_slots('あしたのかうぎでしるょうをくばります')))
        self.assertFalse(R.native_genitive_argument_slots('ぷねらのかうぎでしりょうをくばります'))
        # 48-ALB: しりょう can mean 飼料. The earlier negative assumed
        # 資料 without a written spelling; use unambiguous 書類 instead.
        self.assertTrue(R.native_genitive_argument_slots('あしたのかうぎでしりょうをたべます'))
        self.assertFalse(R.native_genitive_argument_slots('あしたのかうぎでしょるいをたべます'))

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
        text='あしたのかうぎでしりょうをくばります'
        for good in ('かいぎ','会議'):
            self.assertTrue(CR._changed_genitive_object_allowed(text,4,7,good),good)
        for bad in ('懐疑','かえ','楓'):
            self.assertFalse(CR._changed_genitive_object_allowed(text,4,7,bad),bad)
        self.assertFalse(CR._changed_genitive_object_allowed(text,0,len(text),text.replace('かうぎ','懐疑')))

    def test_existing_anomaly_and_shared_application_repair(self):
        import app
        from tests_analysis_async import initial
        a=initial();source='あしたのかてぎでしりょうをくばります。'
        self.assertEqual(K.kana_key_distance('て','い'),1.0)
        result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        assert_repaired_spelling(self, result, ('あしたのかいぎでしりょうをくばります。',
                                          'あしたの会議でしりょうをくばります。'))
        self.assertEqual(result.get('odd_spans'),[])
        self.assertEqual(K.kana_key_distance('き','は'),1.0)
        source='へやのきこにほんをいれます。'
        result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        assert_repaired_spelling(self, result, ('へやのはこにほんをいれます。','へやの箱にほんをいれます。'))
        self.assertEqual(result.get('odd_spans'),[])
        # Former vertical/diagonal substitutions are negative controls.
        # Keep positive case/meaning checks above on same-row slips.
        for pressed,intended in (('う','い'),('い','は')):
            self.assertEqual(K.kana_key_distance(pressed,intended),99.0)
        for source in ('あしたのかうぎでしりょうをくばります。','へやのいこにほんをいれます。'):
            with self.subTest(excluded=source):
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],source)
                self.assertTrue(result['odd_spans'])
        # Initial-state 199 already selects these native same-reading
        # spellings. Preserve the grammatical source, not one IME surface.
        observed_spellings={
            'へやのはこにほんをいれます。':('へやのはこに本をいれます。','へやのはこに本を入れます。','部屋の箱に本を入れます。'),
            'あしたのかいぎでしりょうをくばります。':('明日の会議でしりょうをくばります。','明日の会議で資料を配ります。'),
            'あしたの会議で資料を配ります。':('明日の会議で資料を配ります。',),
        }
        for text in ('へやのはこにほんをいれます。','あしたのかいぎでしりょうをくばります。',
                     '会議で資料を配ります。','あしたの会議で資料を配ります。',
                     '会議で食料を配ります。','会議を開きます。'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertIn(result['corrected'],(text,)+observed_spellings.get(text,()))
                self.assertEqual(result.get('odd_spans'),[])


if __name__=='__main__':unittest.main()
