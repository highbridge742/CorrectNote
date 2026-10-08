# -*- coding: utf-8 -*-
"""Only source-required Shift can witness deletion of its adjacent key."""
import unittest
from unittest.mock import patch
import kana_layout as K,contextual_repair as Q,corrector as C
class SourceShiftIntrusionTests(unittest.TestCase):
    def test_user_physical_neighbours_and_input_method_are_distinct(self):
        for kana,keys in (('ん',set('おやかな く'.replace(' ',''))),('く',set('んきまこみ'))):
            bases={key[2] for key in K._JIS_KEYS}
            self.assertEqual({x for x in bases if x!=kana and K.intrusion_key_distance(kana,x)<=1.0},keys)
        self.assertEqual({x for x in C._QWERTY_POS if C._qwerty_intrusion_adjacent('y',x)},set('67tuh'))
        self.assertEqual({x for x in C._QWERTY_POS if C._qwerty_intrusion_adjacent('h',x)},set('ygjbn'))
        for a,b in (('ん','え'),('ん','ま'),('ん','き'),('く','な'),('れ','ろ')):
            self.assertGreater(K.kana_key_distance(a,b),1.05)
            self.assertGreater(K.kana_key_distance(b,a),1.05)
        self.assertFalse(K.single_key_drop_adjacency('しろれいたな','しろいたな'))
        self.assertFalse(C.adjacent_slip('ご','ほ','kana'))
        self.assertTrue(C.adjacent_slip('ご','ほ','romaji'))

    def test_horizontal_substitution_is_separate_from_unchanged_intrusion(self):
        import loanword as L,explain as E
        for key,expected in (('ん',set('かな')),('く',set('きま'))):
            self.assertEqual({x[2] for x in K._JIS_KEYS if x[2]!=key
                and K.kana_key_distance(key,x[2])<=1.0},expected)
        for key,expected in (('y',set('tu')),('h',set('gj'))):
            self.assertEqual({x for x in C._QWERTY_POS if C._qwerty_adjacent(key,x)},expected)
        for a,b in (('ん','く'),('ん','や'),('く','み'),('く','こ')):
            self.assertGreaterEqual(K.kana_key_distance(a,b),K.FAR)
            self.assertLessEqual(K.intrusion_key_distance(a,b),1.0)
            self.assertFalse(any(r.reading==b and r.operation=='adjacent_substitution'
                for r in Q.key_repairs(a)))
            self.assertFalse(any(r.reading==b for r in Q.nonadjacent_key_repairs(a)))
            self.assertTrue(any(r.reading==b and r.operation=='adjacent_intrusion'
                for r in Q.key_repairs(a+b)))
            self.assertTrue(K.single_key_drop_adjacency(a+b,b))
            self.assertFalse(E._adjacent(a,b,'kana'))
            self.assertTrue(E._adjacent(a,b,'kana',intrusion=True))
        self.assertTrue(C.adjacent_slip('ん','な','kana'))
        self.assertTrue(C.adjacent_slip('ご','ほ','romaji'))
        self.assertFalse(C.adjacent_slip('ゆ','ふ','romaji'))
        self.assertTrue(C.adjacent_slip('ゆ','ふ','romaji',intrusion=True))
        self.assertFalse(L._qwerty_near('y','h'))
        self.assertTrue(L._qwerty_intrusion_near('y','h'))
        self.assertEqual(K.kana_key_distance('ゃ','や'),0.3)
        self.assertEqual(K.kana_key_distance('か','が'),0.4)
        self.assertFalse(any(r for r in K.mark_slip_candidates('さ','へ')))
        self.assertTrue(any(face=='ざ' for face,cost in K.mark_slip_candidates('さ','せ')))

    def test_katakana_seed_gate_retains_vertical_intrusion_only(self):
        import loanword as L
        for a,b in (('ん','く'),('ん','や'),('く','み'),('く','こ')):
            with self.subTest(typed=a,intended=b):
                self.assertFalse(L.typo_explains_seed_word('にゅうりょ'+a,'にゅうりょ'+b))
                self.assertTrue(L.typo_explains_seed_word('にゅうりょ'+a+b,'にゅうりょ'+b))
        self.assertTrue(L.typo_explains_seed_word('にゅうりょま','にゅうりょく'))

    def test_source_small_kana_supplies_its_real_modifier(self):
        for before,after in (('もーしろょん','もーしょん'),('もーしょろん','もーしょん'),('りつゅう','りゅう'),('りろゅう','りゅう')):
            with self.subTest(before=before):
                self.assertTrue(K.single_key_drop_adjacency(before,after))
                self.assertFalse(K.single_key_drop_is_duplicate(before,after))
                self.assertIn(after,C._typo_repairs_intruded(before))
                rows=[r for r in Q.key_repairs(before) if r.reading==after]
                self.assertTrue(rows)
                self.assertEqual(rows[0].operation,'adjacent_intrusion')
                self.assertTrue(Q._original_intrusion_allowed(before,rows[0]))
    def test_deletion_keeps_original_shift_while_adjacent_printed_keys_can_differ(self):
        self.assertGreater(K.kana_key_distance('よ','ゅ'),1.0)
        self.assertEqual(K.intrusion_key_distance('よ','ゅ'),1.0)
        self.assertTrue(K.single_key_drop_adjacency('ちよゅう','ちゅう'))
        self.assertIn('ちゅう',C._typo_repairs_intruded('ちよゅう'))
        self.assertTrue(any(r.reading=='ちゅう' and r.operation=='adjacent_intrusion'
                            for r in Q.key_repairs('ちよゅう')))

    def test_ordinary_and_nonadjacent_source_does_not_invent_shift(self):
        for before,after in (('もーしろよん','もーしよん'),('りろゆう','りゆう'),('もんじにゅうりょく','もじにゅうりょく'),('りこゅう','りゅう')):
            with self.subTest(before=before):
                self.assertFalse(K.single_key_drop_adjacency(before,after))
                self.assertNotIn(after,C._typo_repairs_intruded(before))
                self.assertFalse(any(r.reading==after for r in Q.key_repairs(before)))
        invented=Q.KeyRepair('もーしょん','adjacent_intrusion',3,'ろ','',1.0)
        self.assertFalse(Q._original_intrusion_allowed('もーしろよん',invented))
        self.assertGreater(K.kana_key_distance('ろ','ょ'),1.0)
        self.assertGreater(K.intrusion_key_distance('ょ','ろ'),1.0)
    def test_legacy_generator_does_not_infer_a_kana_shift_in_romaji_mode(self):
        token=C._CORRECTION_INPUT_METHOD.set('romaji')
        try:
            self.assertNotIn('もーしょん',C._typo_repairs_intruded('もーしろょん'))
            self.assertIn('がぞう',C._typo_repairs_intruded('がすぞう'))
        finally:C._CORRECTION_INPUT_METHOD.reset(token)
        self.assertIn('もーしょん',C._typo_repairs_intruded('もーしろょん'))

    def test_attested_whole_nominal_reading_reaches_original_shift_check(self):
        from tests_analysis_async import initial
        from last_choice import set_active
        import reading_segments as R
        a=initial();tok=C.make_tokenizer(a.store)
        try:
            self.assertEqual(R.native_attested_prefix_noun_readings('手稿'),('しゅこう',))
            self.assertEqual(''.join(t[2] for t in tok('手稿')),'てこう')
            for source,face in (('ゅ稿','手稿'),('私はゅ稿を整理します。','私は手稿を整理します。')):
                self.assertFalse(C._changes_neighbor_and_shift_in_source(source,0,len(source),face,tok),(source,face))
            with patch.object(R,'native_attested_prefix_noun_readings',return_value=()):
                self.assertTrue(C._changes_neighbor_and_shift_in_source('ゅ稿',0,2,'手稿',tok))
            for source,face in (('ゅ味','読み'),('ゅ役','予約'),('りゆうり','料理')):
                self.assertTrue(C._changes_neighbor_and_shift_in_source(source,0,len(source),face,tok),(source,face))
            token=C._CORRECTION_PATH.set(('彼女のゅ味','彼女のゆ味'))
            try:
                self.assertTrue(C._changes_neighbor_and_shift_in_source('彼女のゆ味',3,5,'読み',tok))
            finally:C._CORRECTION_PATH.reset(token)
        finally:set_active(None)

    def test_attested_whole_context_reading_keeps_pos_and_contiguity(self):
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();tok=C.make_tokenizer(a.store)
        try:
            parts=list(tok('手稿'))
            self.assertTrue(Q._same_context_reading(parts,'しゅこう'))
            self.assertFalse(Q._same_context_reading(parts,'しょこう'))
            changed=list(parts);t=changed[0]
            changed[0]=(t[0],'動詞:自立',t[2],t[3],t[4],t[5],'連用形')
            self.assertFalse(Q._same_context_reading(changed,'しゅこう'))
            changed=list(parts);t=changed[-1]
            changed[-1]=(t[0],t[1],t[2],t[3]+1,t[4]+1,t[5],t[6])
            self.assertFalse(Q._same_context_reading(changed,'しゅこう'))
            with patch('reading_segments.native_attested_prefix_noun_readings',return_value=()):
                self.assertFalse(Q._same_context_reading(parts,'しゅこう'))
        finally:set_active(None)

    def test_attested_whole_nominal_restoration_keeps_shared_candidate_gate(self):
        import app
        from tests_analysis_async import initial
        from last_choice import set_active
        source='私はゅ稿を整理します。'
        try:
            a=initial()
            r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
            self.assertEqual(r['corrected'],'私は手稿を整理します。')
            self.assertEqual(r['odd_spans'],[])
            self.assertEqual(r['analysis_status'],'complete')
            a=initial()
            with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
            self.assertEqual(r['corrected'],source)
            self.assertTrue(r['odd_spans'])
        finally:set_active(None)

    def test_original_shift_check_uses_compound_reading_before_trimming_glyphs(self):
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();tok=C.make_tokenizer(a.store)
        try:
            for source,face in (('ゅ芸','手芸'),('ゅ役','主役'),('ゅ味','趣味')):
                self.assertFalse(C._changes_neighbor_and_shift_in_source(source,0,len(source),face,tok),(source,face))
            for source,face in (('ゅ味','読み'),('ゅ役','予約'),('りゆうり','料理')):
                self.assertTrue(C._changes_neighbor_and_shift_in_source(source,0,len(source),face,tok),(source,face))
            token=C._CORRECTION_PATH.set(('彼女のゅ味','彼女のゆ味'))
            try:
                self.assertTrue(C._changes_neighbor_and_shift_in_source('彼女のゆ味',3,5,'読み',tok))
            finally:C._CORRECTION_PATH.reset(token)
        finally:set_active(None)

    def test_valid_missing_onset_survives_original_shift_check_with_actual_reading(self):
        import app,ime_language,ime_candidates
        from unittest.mock import patch
        from tests_analysis_async import initial
        from last_choice import set_active
        source='僕はゅ芸を習います。'
        try:
            with patch.object(ime_language,'_factory',None),patch.object(ime_candidates.SearchCandidates,'__enter__',lambda self:self):
                a=initial()
                r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertEqual(r['corrected'],'僕は手芸を習います。')
                self.assertEqual(r['odd_spans'],[])
                self.assertEqual(r['analysis_status'],'complete')
                a=initial()
                with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                    r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertEqual(r['corrected'],source)
                self.assertTrue(r['odd_spans'])
        finally:set_active(None)

    def test_neighbor_substitution_cannot_change_shift_at_the_same_position(self):
        from types import SimpleNamespace
        dictionary=SimpleNamespace(surfaces_for_reading=lambda *a,**k:('index-entry',),
                                   inflected_surfaces_for_reading=lambda *a:())
        for source,forbidden in (('ゅみ','よみ'),('ゅやく','よやく'),
                                 ('りゆうり','りょうり'),('かさ','かっ'),
                                 ('もさて','もって'),('とさて','とって'),('かさて','かって')):
            for before,after in (('',''),('資料を渡して','を確認する'),
                                 ('を長く離して','話を聞く')):
                with self.subTest(source=source,before=before,after=after):
                    rows=list(Q.key_repairs(source,before,after))
                    rows+=list(Q.nonadjacent_key_repairs(source))
                    rows+=list(Q.neighbor_shift_key_repairs(source))
                    rows+=list(Q.independent_key_pair_repairs(source,dictionary,before,after))
                    self.assertNotIn(forbidden,{row.reading for row in rows})
        for source in ('よみまぃ','なおしまぃ','よみまぇ'):
            target=SimpleNamespace(boundary_kind='kana_predicate',text=source)
            for before,after in (('',''),('本を長く','を調べる')):
                self.assertNotIn(source[:-1]+'す',{r.reading for r in
                    Q.request_shift_key_repairs(target,source,before,after)})
        # The source already owns small tsu. Its adjacent extra key can be
        # removed without inventing Shift at the replaced source position.
        for source,intended in (('もっさて','もって'),('とっさて','とって'),('かっさて','かって')):
            self.assertTrue(K.single_key_drop_adjacency(source,intended))
            self.assertTrue(any(r.reading==intended and r.operation=='adjacent_intrusion'
                                for r in Q.key_repairs(source)))
        self.assertIn('りょうり',{r.reading for r in Q.key_repairs('りゅうり')})
        self.assertIn('ゆみ',{r.reading for r in Q.key_repairs('ゅみ')})
        self.assertEqual(K.kana_key_distance('ゅ','よ'),K.FAR)
        self.assertEqual(K.kana_key_distance('よ','ゅ'),K.FAR)
        self.assertLessEqual(K.kana_key_distance('ゅ','ょ'),1.0)

    def test_recursive_neighbor_slip_keeps_original_shift_and_coordinate(self):
        from types import SimpleNamespace
        def tokenize(text):
            if text=='料理':return [('料理','名詞:サ変接続','りょうり',0,2,True,'')]
            return [(text,'名詞:一般',text,0,len(text),True,'')]
        token=C._CORRECTION_PATH.set(('本を渡してりゆうり','本を渡してりゅうり'))
        try:
            self.assertTrue(C._changes_neighbor_and_shift_in_source(
                '本を渡してりゅうり',5,9,'料理',tokenize))
            self.assertFalse(C._changes_neighbor_and_shift_in_source(
                '本を渡してりゅうり',5,9,'りゅうり',tokenize))
        finally:C._CORRECTION_PATH.reset(token)
        self.assertFalse(C._changes_neighbor_and_shift_in_source('りゅうり',0,4,'料理',tokenize))
        self.assertFalse(C._changes_neighbor_and_shift_in_source('ゅみ',0,2,'ゆみ',tokenize))
        method=C._CORRECTION_INPUT_METHOD.set('romaji')
        try:self.assertFalse(C._changes_neighbor_and_shift_in_source('ゅみ',0,2,'よみ',tokenize))
        finally:C._CORRECTION_INPUT_METHOD.reset(method)

    def test_window_boundary_and_duplicate_policy_use_original_keys(self):
        repair=Q.KeyRepair('','adjacent_intrusion',0,'ろ','',1.0)
        self.assertTrue(Q._original_intrusion_allowed('ろ',repair,after='ょん'))
        self.assertFalse(Q._original_intrusion_allowed('ろ',repair,after='よん'))
        with patch('vocabulary.dup_repair_enabled',return_value=False):
            self.assertFalse(any(r.reading=='ちょう' for r in Q.key_repairs('ちょょう')))
if __name__=='__main__':unittest.main()
