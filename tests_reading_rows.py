# -*- coding: utf-8 -*-
"""The indexed row view must match the original range filter, including Unicode."""
import random
import unittest
from analysis_work import Document,Occurrence
from analysis_async import _background_readings

class ReadingRowsTests(unittest.TestCase):
    def assert_rows(self,doc):
        at=0
        for index,line in enumerate(doc.text.split('\n')):
            self.assertEqual(doc.row_readings(index,line),doc.line_readings(at,line))
            at+=len(line)+1

    def test_generated_ranges_match_original_filter(self):
        rng=random.Random(915)
        for _ in range(100):
            text='\n'.join(''.join(rng.choice('資料あ😀') for _ in range(rng.randrange(12))) for _ in range(12))
            doc=Document(1,text);items=[]
            for _ in range(60):
                start=rng.randrange(len(text)+1);end=min(len(text),start+rng.randrange(1,5))
                items.append(Occurrence(start,end,text[start:end],'しりょう'))
            # Keep the old order even for manually supplied, overlapping ranges.
            doc.occurrences=tuple(items);self.assert_rows(doc)

    def test_current_text_and_occurrence_replacement_invalidate_index(self):
        doc=Document(1,'資料です。\n資料です。');doc.remember(0,2,'資料','しりょう')
        first=doc.row_readings(0,'資料です。');cache=doc._reading_rows
        self.assertIs(doc.row_readings(0,'資料です。'),first)
        self.assertIs(doc._reading_rows,cache)
        doc.remember(0,2,'資料','しりお');self.assertEqual(doc.row_readings(0,'資料です。')[0].reading,'しりお')
        self.assertIsNot(doc._reading_rows,cache)
        doc.update('注釈\n'+doc.text);self.assertIsNone(doc._reading_rows);self.assert_rows(doc)
        self.assertEqual(doc.row_readings(0,'注釈'),())
        doc.update(doc.text,discard_readings=True);self.assertEqual(doc.row_readings(1,'資料です。'),())

    def test_direct_replacement_does_not_depend_on_generation(self):
        doc=Document(1,'資料');doc.occurrences=(Occurrence(0,2,'資料','しりょう'),)
        self.assertEqual(doc.row_readings(0,'資料')[0].reading,'しりょう')
        doc.occurrences=(Occurrence(0,2,'資料','しりお'),)
        self.assertEqual(doc.row_readings(0,'資料')[0].reading,'しりお')
        doc.text='別の資料';doc.occurrences=(Occurrence(2,4,'資料','しりょう'),)
        self.assert_rows(doc)

    def test_wrong_line_and_outside_row_are_rejected(self):
        doc=Document(1,'資料\n');doc.remember(0,2,'資料','しりょう')
        for index,line in ((0,'別の資料'),(1,'資料'),(-1,'資料'),(5,'')):
            self.assertEqual(doc.row_readings(index,line),())

    def test_background_reuses_one_current_document(self):
        state=dict(owner=1,text='資料\n資料',lines=['資料','資料'],readings=(Occurrence(0,2,'資料','しりょう'),))
        self.assertTrue(_background_readings(state,0));doc=state['_reading_document'];cache=doc._reading_rows
        self.assertEqual(_background_readings(state,1),());self.assertIs(state['_reading_document'],doc)
        self.assertIs(doc._reading_rows,cache)
        state.update(text='注釈\n資料',lines=['注釈','資料'],readings=(Occurrence(3,5,'資料','しりょう'),))
        self.assertTrue(_background_readings(state,1));self.assertIsNot(state['_reading_document'],doc)

if __name__=='__main__':unittest.main()
