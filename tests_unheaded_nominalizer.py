# -*- coding: utf-8 -*-
"""Source nominalization evidence retains positive predicate validation."""
import copy,unittest
from unittest.mock import patch
import morphology as M
import particle_frames as F


@unittest.skipUnless(M.dictionary_inflections('読む'),'requires native dictionary')
class UnheadedNominalizerTests(unittest.TestCase):
    def test_native_source_frame_is_independent_of_expected_word(self):
        for text in ('処理がじゃのになっている。','作業がしかしのになっています。',
                     '結果がそしてのに見えます。'):
            with self.subTest(text=text):
                frames=F.unheaded_nominalizer_frames(text)
                self.assertEqual(len(frames),1)
                frame=frames[0]
                self.assertEqual(text[frame['end']:frame['case_end']],'に')
                self.assertNotIn('candidate',frame)
                self.assertNotIn('reading',frame)

    def test_native_attributes_and_original_coordinates_are_required(self):
        source='処理がじゃのになっている。';parts=M.tokenize(source)
        self.assertEqual(len(F.unheaded_nominalizer_frames(source)),1)
        for index in range(5):
            for field,value in (('has_reading',False),('reading','べつ'),('start',parts[index].start+1)):
                changed=list(parts);changed[index]=copy.copy(parts[index]);setattr(changed[index],field,value)
                with self.subTest(index=index,field=field),patch('morphology.tokenize',return_value=changed):
                    self.assertFalse(F.unheaded_nominalizer_frames(source))
        original=M.dictionary_inflections
        with patch('morphology.dictionary_inflections',side_effect=lambda text:() if text=='じゃ' else original(text)):
            self.assertFalse(F.unheaded_nominalizer_frames(source))

    def test_valid_nominalizers_and_literal_boundaries_are_preserved(self):
        for source in ('処理が邪魔になっていないだろうか\t','処理がじゃまになっている。',
                       '本文が読めるのになりました。','名前がただの文字になった。',
                       'それが前のになる。','処理が「じゃの」になっている。',
                       '「処理がじゃのになっている」と入力します。',
                       '「処理がじゃのになっている」という文字列です。',
                       '結果がつまりのに見えます。','処理は続く。しかし終わる。',
                       '処理が終わるので、しかし次を読みます。',
                       '処理が\tじゃのになっている。','処理が、じゃのになっている。',
                       '処理が じゃのになっている。','じゃのになっている。'):
            with self.subTest(source=source):self.assertFalse(F.unheaded_nominalizer_frames(source))

    def test_search_keeps_unchanged_finite_tail_and_common_meaning_gate(self):
        import corrector as C,contextual_repair as R
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();tok=C.make_tokenizer(a.store)
        source='処理がじゃのになっていないだろうか\t'
        try:
            targets=R.targets_for_line(source,tok,a.store,a.dict_index)
            self.assertEqual([(t.start,t.end,t.boundary_kind) for t in targets],[(3,6,'kana_predicate')])
            target=targets[0]
            self.assertEqual(target.following,'になっていないだろうか')
            self.assertFalse(C._chunk_is_intact(target.text,tok,repair_context=target))
            for surface,reading in (('蛇','じゃ'),('邪魔','じゃま')):
                allowed,reason=R.validate(target,surface,C,tok,a.store,a.dict_index,a.decisions,expected_reading=reading)
                self.assertFalse(allowed,surface)
                self.assertEqual(reason,'unproven_object_predicate')
            with patch.object(C,'_check_replacement',return_value=(None,'forced_source_rejection')):
                self.assertEqual(R.validate(target,'邪魔',C,tok,a.store,a.dict_index,a.decisions),
                                 (False,'forced_source_rejection'))
            for open_tail in ('なって','なりまふ'):
                text='処理がじゃのに'+open_tail+'\t'
                frames=R.targets_for_line(text,tok,a.store,a.dict_index)
                self.assertTrue(any(t.boundary_kind=='kana_predicate' and t.end>6 for t in frames))
        finally:set_active(None)

    def test_neighbor_fields_do_not_supply_meaning_or_block_unrelated_edits(self):
        import corrector as C,contextual_repair as R,oddness as O
        from tests_analysis_async import initial
        from last_choice import set_active
        malformed='処理がじゃのになっていないだろうか'
        expected='処理が邪魔になっていないだろうか'
        a=initial();tok=C.make_tokenizer(a.store)
        try:
            for text,offset in ((malformed+'\t'+expected,0),(expected+'\t'+malformed,len(expected)+1)):
                targets=R.targets_for_line(text,tok,a.store,a.dict_index)
                own=[t for t in targets if t.start==offset+3]
                self.assertEqual(len(own),1)
                target=own[0]
                self.assertEqual((target.start,target.end,target.boundary_kind),(offset+3,offset+6,'kana_predicate'))
                self.assertEqual(R.validate(target,'邪魔',C,tok,a.store,a.dict_index,a.decisions,expected_reading='じゃま'),
                                 (False,'unproven_object_predicate'))
            for text in ('処理がじゃのになっている。\t資料を読みます。',
                         '処理がじゃのになっている。資料を読みます。',
                         '資料を読みます。\t処理がじゃのになっている。'):
                start=text.index('読み');changed=text[:start]+'書き'+text[start+2:]
                self.assertTrue(O.changed_auxiliary_chain_allowed(changed,start,start+2,text))
        finally:set_active(None)

    def test_final_auxiliary_gate_rejects_new_unheaded_nominalization(self):
        import oddness as O
        original='処理が邪魔になっている。'
        changed=original.replace('邪魔','じゃの')
        self.assertFalse(O.changed_auxiliary_chain_allowed(changed,3,6,original))
        self.assertTrue(O.changed_auxiliary_chain_allowed(original,3,5,changed))

    def test_runtime_reports_anomaly_without_unproved_substitution(self):
        import analysis_worker
        from tests_analysis_async import initial
        from last_choice import set_active
        from janome_import import import_from_janome
        source='処理がじゃのになっていないだろうか\t'
        try:
            for fresh in (False,True):
                a=initial()
                if fresh:import_from_janome(a.store)
                before=a.store.revision()
                runtime=analysis_worker.Runtime();runtime.set_state(analysis_worker.snapshot(a))
                context=runtime.execute(dict(kind='prepare',lines=[source]))
                result=runtime.execute(dict(kind='line',line=source,input_method='kana',
                    context=context['context'],attested=context['attested']))['result']
                self.assertEqual(result['corrected'],source)
                self.assertEqual(result['analysis_status'],'complete')
                self.assertEqual(result['odd_spans'],[(3,6)])
                self.assertEqual(result['diagnosis']['language_state'],'anomaly_unrepaired')
                self.assertTrue(result['search_reports'])
                self.assertTrue(all(r['state']=='complete' for r in result['search_reports']))
                self.assertEqual(a.store.revision(),before)
        finally:set_active(None)


if __name__=='__main__':unittest.main()
