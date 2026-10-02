# -*- coding: utf-8 -*-
"""Commit positions require the same composition's actual editor mutations."""
import unittest
from ime_commit_ranges import CommitRanges

class IMECommitRangeTests(unittest.TestCase):
    def setUp(self):
        self.r=CommitRanges();self.r.set_owner('tab1');self.r.begin()
    def edit(self,start,old,new):self.r.edited('tab1',(start,old),(start,new))
    def test_result_before_or_after_actual_characters(self):
        for before in (True,False):
            self.setUp()
            if before:self.r.result('資料','しりょう')
            self.edit(2,2,3);self.edit(3,3,4)
            if not before:self.r.result('資料','しりょう')
            self.r.finish()
            self.assertEqual(self.r.take('tab1','前文資料'),((2,4,'資料','しりょう'),))
    def test_no_insert_does_not_borrow_identical_old_text(self):
        self.r.result('資料','しりょう');self.r.finish()
        self.assertEqual(self.r.take('tab1','資料'),())
    def test_partial_results_keep_equal_spellings_and_different_readings(self):
        self.r.result('行った','いった');self.edit(0,0,3)
        self.r.result('行った','おこなった');self.edit(3,3,6);self.r.finish()
        self.assertEqual(self.r.take('tab1','行った行った'),
            ((0,3,'行った','いった'),(3,6,'行った','おこなった')))
    def test_multiple_compositions_between_polls_are_separate(self):
        self.r.result('橋','はし');self.edit(0,0,1);self.r.finish();self.r.begin()
        self.edit(1,1,2);self.r.result('端','はし');self.r.finish()
        self.assertEqual(self.r.take('tab1','橋端'),((0,1,'橋','はし'),(1,2,'端','はし')))
    def test_edits_before_pending_closed_range_rebase_it(self):
        self.r.result('橋','はし');self.edit(2,2,3);self.r.finish()
        self.edit(0,0,2)
        self.assertEqual(self.r.take('tab1','追加前文橋'),((4,5,'橋','はし'),))
    def test_overlap_undo_or_tab_switch_invalidates_position(self):
        for invalid in ('overlap','undo','tab'):
            self.setUp();self.r.result('資料','しりょう');self.edit(0,0,2);self.r.finish()
            if invalid=='overlap':self.edit(0,2,2)
            elif invalid=='undo':self.r.edited('tab1',None,None,True)
            else:self.r.set_owner('tab2')
            self.assertEqual(self.r.take('tab1','資料'),())
    def test_unrelated_edit_during_composition_does_not_expand_its_range(self):
        self.edit(3,3,4);self.edit(0,0,1);self.r.result('資料','しりょう')
        self.assertEqual(self.r.take('tab1','資料前文'),())
    def test_cancel_never_promotes_composition_text_to_a_result(self):
        self.edit(0,0,2);self.r.finish()
        self.assertEqual(self.r.take('tab1','資料'),())
    def test_poll_during_composition_can_wait_for_actual_insert(self):
        self.r.result('橋','はし');self.assertEqual(self.r.take('tab1','橋'),())
        self.edit(1,1,2);self.assertEqual(self.r.take('tab1','橋橋'),((1,2,'橋','はし'),))
        self.r.result('端','はし');self.edit(2,2,3)
        self.assertEqual(self.r.take('tab1','橋橋端'),((2,3,'端','はし'),))
    def test_duplicate_result_without_duplicate_insert_does_not_bind(self):
        self.r.result('橋','はし');self.r.result('橋','はし');self.edit(0,0,1)
        self.assertEqual(self.r.take('tab1','橋'),())
    def test_missing_start_or_wrong_owner_supplies_no_position(self):
        self.r.clear();self.r.result('橋','はし');self.edit(0,0,1)
        self.assertEqual(self.r.take('tab1','橋'),())
        self.r.begin();self.r.result('橋','はし');self.r.edited('tab2',(0,0),(0,1))
        self.assertEqual(self.r.take('tab1','橋'),())
    def test_unicode_offsets_remain_python_character_offsets(self):
        self.r.result('𠮷野','よしの');self.edit(1,1,3)
        self.assertEqual(self.r.take('tab1','😀𠮷野'),((1,3,'𠮷野','よしの'),))

class AdjacentActualReadingTests(unittest.TestCase):
    def test_actual_clauses_keep_exact_and_whole_readings_without_native_guess(self):
        from analysis_work import Document,current_input,occurrence_readings
        doc=Document('tab','架理経過図')
        self.assertTrue(doc.remember(0,2,'架理','ｶｸﾆﾝ'))
        self.assertTrue(doc.remember(2,5,'経過図','ｼﾏｼﾀ'))
        with current_input(doc.text,doc.occurrences):
            self.assertEqual(occurrence_readings(doc.text,0,2),('かくにん',))
            self.assertEqual(occurrence_readings(doc.text,2,5),('しました',))
            self.assertEqual(occurrence_readings(doc.text,0,5),('かくにんしました',))
            self.assertFalse(occurrence_readings('別本文',0,3))
        doc.update('前架理経過図',edited=True,edit=(0,0))
        with current_input(doc.text,doc.occurrences):
            self.assertEqual(occurrence_readings(doc.text,1,6),('かくにんしました',))
            self.assertFalse(occurrence_readings(doc.text,0,6))

    def test_gaps_overlaps_and_changed_surface_do_not_compose(self):
        from analysis_work import Occurrence,current_input,occurrence_readings
        examples=(('資料／確認',(Occurrence(0,2,'資料','しりょう'),Occurrence(3,5,'確認','かくにん'))),
                  ('資料確認',(Occurrence(0,3,'資料確','しりょうかく'),Occurrence(2,4,'確認','かくにん'))),
                  ('資料確認',(Occurrence(0,2,'別字','しりょう'),Occurrence(2,4,'確認','かくにん'))))
        for source,records in examples:
            with current_input(source,records):
                self.assertFalse(occurrence_readings(source,0,len(source)))
        records=(Occurrence(0,4,'資料確認','じっさいのよみ'),Occurrence(0,2,'資料','しりょう'),Occurrence(2,4,'確認','かくにん'))
        with current_input('資料確認',records):
            self.assertEqual(occurrence_readings('資料確認',0,4),('じっさいのよみ',))


class LiteralActualReadingTests(unittest.TestCase):
    def test_literal_edges_keep_exact_insertion_coordinates(self):
        from analysis_work import Document,current_input,occurrence_readings
        cases=(('確認。','ｶｸﾆﾝ｡','確認','かくにん',0),
               ('「確認」。','｢ｶｸﾆﾝ｣｡','確認','かくにん',1),
               ('「確認」','ｶｸﾆﾝ｣','「確認','かくにん',0),
               ('　確認　',' ｶｸﾆﾝ ','確認','かくにん',1),
               ('【𠮷野】！','【ﾖｼﾉ】!','𠮷野','よしの',1),
               ('(資料)','(ｼﾘｮｳ)','資料','しりょう',1))
        for surface,reading,face,yomi,offset in cases:
            with self.subTest(surface=surface):
                doc=Document('tab','😀'+surface+'後')
                self.assertTrue(doc.remember(1,1+len(surface),surface,reading))
                record,=doc.occurrences
                self.assertEqual((record.start,record.end,record.surface,record.reading),
                                 (1+offset,1+offset+len(face),face,yomi))
                with current_input(doc.text,doc.occurrences):
                    self.assertEqual(occurrence_readings(doc.text,record.start,record.end),(yomi,))
                    self.assertFalse(occurrence_readings(doc.text,1,1+len(surface)))
                doc.update('追記'+doc.text,edited=True,edit=(0,0))
                self.assertEqual(doc.occurrences[0].start,3+offset)

    def test_unmatched_internal_and_nonphonetic_parts_still_supply_no_reading(self):
        from analysis_work import Document
        cases=(('確認。','ｶｸﾆﾝ､'),('「確認」','｢ｶｸﾆﾝ〕'),
               ('確認、資料','ｶｸﾆﾝ､ｼﾘｮｳ'),('A確認。','Aｶｸﾆﾝ｡'),
               ('確認1。','ｶｸﾆﾝ1｡'),('確認。','ｶｸﾆﾝ｡X'),
               ('確認。','ｶｸﾆﾝ｡\n'),('。','｡'),('　',' '),
               ('確認。','ｶｸﾆﾝ!'),('確認。','ｶｸﾆﾝ｡｡'))
        for surface,reading in cases:
            with self.subTest(surface=surface,reading=reading):
                doc=Document('tab',surface)
                self.assertFalse(doc.remember(0,len(surface),surface,reading))
                self.assertFalse(doc.occurrences)
        doc=Document('tab','別字。')
        self.assertFalse(doc.remember(0,3,'確認。','ｶｸﾆﾝ｡'))

    def test_plain_reading_and_persistent_pair_contract_remain_strict(self):
        from analysis_work import Document
        from ime_readings import IMEReadings
        doc=Document('tab','確認。')
        self.assertTrue(doc.remember(0,3,'確認。','ｶｸﾆﾝ'))
        self.assertEqual(doc.occurrences[0].surface,'確認。')
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            pairs=IMEReadings(Path(folder)/'ime_readings.json')
            self.assertFalse(pairs.remember('確認。','ｶｸﾆﾝ｡'))
            self.assertFalse(pairs.readings_for('確認'))


if __name__=='__main__':unittest.main()
