"""Saved reading changes invalidate only rows whose observed lookup changed."""
import correction_entry
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import analysis_context,analysis_worker,tab_analysis,analysis_work_app as work
from ime_readings import IMEReadings
from session import SessionStore,new_tab


class ReadingDependencyTests(unittest.TestCase):
    def setUp(self):
        self.a=SimpleNamespace(ime_readings=IMEReadings(),settings={'input_method':'kana'})
        self.before=analysis_worker.state_key(self.a)

    def row(self,reads=(),text='資料'):
        return dict(original=text,corrected=text,_ime_evidence=reads)

    def compatible(self,row):
        return analysis_worker.result_compatible(self.a,row,self.before)

    def test_unread_pair_keeps_result_but_changes_worker_state(self):
        self.a.ime_readings.remember('校閲','こうえつ')
        self.assertNotEqual(self.before,analysis_worker.state_key(self.a))
        self.assertTrue(self.compatible(self.row()))

    def test_previously_missing_pair_is_a_real_dependency(self):
        row=self.row((('資料',()),))
        self.a.ime_readings.remember('資料','しりょう')
        self.assertFalse(self.compatible(row))

    def test_reading_order_change_invalidates_but_same_pair_does_not(self):
        ime=self.a.ime_readings;ime.remember('行った','おこなった');ime.remember('行った','いった')
        self.before=analysis_worker.state_key(self.a)
        row=self.row((('行った',('いった','おこなった')),))
        self.assertFalse(ime.remember('行った','いった'))
        self.assertEqual(self.before,analysis_worker.state_key(self.a))
        ime.remember('行った','おこなった')
        self.assertFalse(self.compatible(row))

    def test_eviction_and_forget_are_dependency_changes(self):
        ime=self.a.ime_readings;ime.limit=1;ime.remember('資料','しりょう')
        self.before=analysis_worker.state_key(self.a);row=self.row((('資料',('しりょう',)),))
        ime.remember('校閲','こうえつ');self.assertFalse(self.compatible(row))
        self.before=analysis_worker.state_key(self.a);row=self.row((('校閲',('こうえつ',)),))
        ime.forget('校閲');self.assertFalse(self.compatible(row))

    def test_unknown_proof_and_model_changes_are_not_reused(self):
        self.a.ime_readings.remember('資料','しりょう')
        self.assertFalse(self.compatible(dict(original='資料',corrected='資料')))
        self.assertTrue(self.compatible(self.row(text='')))
        self.a._analysis_state_revision=1
        self.assertFalse(self.compatible(self.row()))

    def test_replacing_reading_store_does_not_reuse_old_proof(self):
        self.a.ime_readings=IMEReadings()
        self.assertFalse(self.compatible(self.row()))

    def test_worker_records_positive_negative_reads_and_clears_on_error(self):
        import kanji_guess,app,units
        runtime=analysis_worker.Runtime();runtime.ime=IMEReadings()
        runtime.store=object();runtime.decisions=None;runtime.context_vec=None;runtime.index=None
        runtime.tokenize=lambda text:[];runtime.choices=None
        runtime.ime.remember('資料','しりょう')
        original_provider=kanji_guess._IME_READINGS_PROVIDER
        kanji_guess.set_ime_readings_provider(runtime._read_ime)
        def correction(line,*args,**kwargs):
            kanji_guess.ime_readings_for('資料');kanji_guess.ime_readings_for('校閲')
            return dict(original=line,corrected=line)
        task=dict(kind='line',line='資料',context={},input_method='kana')
        try:
            with patch.object(correction_entry,'correct_line',side_effect=correction),patch.object(units,'build_line_units',return_value=('',[])),patch.object(units,'build_suspect_units',return_value=('',[])):
                result=analysis_context.completed(runtime.execute(task))
            self.assertEqual(dict(result['_ime_evidence']),{'資料':('しりょう',),'校閲':()})
            with patch.object(correction_entry,'correct_line',side_effect=ValueError('synthetic')):
                with self.assertRaises(ValueError):runtime.execute(task)
            self.assertIsNone(runtime._ime_queries)
        finally:kanji_guess.set_ime_readings_provider(original_provider)

    def tab(self):
        a=self.a;a.session=SessionStore();a.session.tabs=[new_tab(text='現在'),new_tab(text='資料\n末尾')]
        a.BG_PARKED_MAX=6;owner=work.owner_for_tab(a,a.session.tabs[1])
        rows=[self.row((('資料',()),)),self.row(text='末尾')]
        saved=dict(text='資料\n末尾',results=rows,prepared=dict(context={},words={},attested={}),
                   dependencies=self.before,readings=(),calculations=(),
                   units={(r['original'],r['corrected']):('',[]) for r in rows},
                   suspect={(r['original'],r['corrected'],False):('',[]) for r in rows})
        a._completed_tabs={owner:saved}
        return owner,saved

    def test_completed_unaffected_tab_stays_ready(self):
        owner,saved=self.tab();self.a.ime_readings.remember('校閲','こうえつ')
        self.assertIs(tab_analysis.completed(self.a,saved['text'],owner),saved)
        self.assertTrue(tab_analysis.display_ready(saved))
        self.assertEqual(saved['dependencies'],analysis_worker.state_key(self.a))

    def test_affected_tab_parks_only_changed_rows(self):
        owner,saved=self.tab();self.a.ime_readings.remember('資料','しりょう')
        self.assertIsNone(tab_analysis.completed(self.a,saved['text'],owner))
        pending=self.a._bg_parked[owner]
        self.assertIsNone(pending['results'][0]);self.assertEqual(pending['results'][1],saved['results'][1])
        self.assertEqual(pending['pos'],0)
        self.assertTrue(tab_analysis.background_compatible(self.a,pending))

    def test_background_invalidation_keeps_finished_unaffected_row(self):
        owner,saved=self.tab()
        state=dict(owner=owner,text=saved['text'],lines=saved['text'].split('\n'),
                   results=saved['results'],dependencies=self.before,readings=(),calculations=(),
                   units=saved['units'],suspect_units=saved['suspect'],pos=2)
        self.a.ime_readings.remember('資料','しりょう')
        self.assertTrue(tab_analysis.background_compatible(self.a,state))
        self.assertIsNone(state['results'][0]);self.assertEqual(state['results'][1]['original'],'末尾')
        self.assertEqual(state['pos'],0)

    def test_text_cache_cannot_reuse_changed_or_unknown_evidence(self):
        a=self.a;a._analysis_cache={'資料':[self.row((('資料',()),))]}
        a._analysis_cache_dependencies={'資料':self.before}
        a.ime_readings.remember('資料','しりょう')
        self.assertIsNone(tab_analysis.text_results(a,'資料'))


if __name__=='__main__':unittest.main()
