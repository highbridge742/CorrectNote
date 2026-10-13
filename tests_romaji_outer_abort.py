# -*- coding: utf-8 -*-
"""Outer aborts retain independently proved anomaly in original coordinates."""
import unittest
from unittest.mock import patch
import corrector as C,romaji_repair as R
from romaji_source import _LIMITS
from correction_entry import correct_line
from tests_analysis_async import initial
from last_choice import set_active


class RomajiOuterAbortTests(unittest.TestCase):
    def setUp(self):
        self.a=initial();self.addCleanup(set_active,None)
    def run_line(self,source):
        a=self.a
        return correct_line(source,a.store,context_vocab={},input_method='romaji',
            decisions=a.decisions,dict_index=a.dict_index,context_vec=a.context_vec)
    def verify(self,exception,reason):
        raw='shiryouwohozinshimasu';prefix='mojinyuuryoku\t';source=prefix+raw
        proposal=R.propose;records=[];finish=R.finish
        def observe(result):
            records.extend(dict(x) for x in R._DIAGNOSTICS.get() or ())
            return finish(result)
        def abort_accept(*args,**kwargs):
            args=list(args)
            def stop(candidate):raise exception()
            args[6]=stop
            return proposal(*args,**kwargs)
        for phase in ('enumeration','completion'):
            records.clear()
            patcher=(patch.object(R,'one_key_readings',side_effect=exception)
                     if phase=='enumeration' else patch.object(R,'propose',side_effect=abort_accept))
            with self.subTest(phase=phase),patcher,patch.object(R,'finish',side_effect=observe):
                row=self.run_line(source)
                self.assertEqual(row['corrected'],source)
                self.assertFalse(row['changed'])
                self.assertEqual(row['original_spans'],[])
                self.assertEqual(row['spans'],[])
                self.assertEqual(row['analysis_status'],'incomplete')
                self.assertEqual(row['stop_reason'],reason)
                self.assertEqual(row['odd_spans'],[(len(prefix),len(source))])
                self.assertEqual(row['diagnosis']['unreplaced_odd_spans'],[[len(prefix),len(source)]])
                self.assertEqual(row['diagnosis']['detected_odd_spans'],[[len(prefix),len(source)]])
                self.assertEqual([(x['start'],x['end']) for x in records],[(len(prefix),len(source))])
                self.assertEqual(records[0]['state'],'pending' if phase=='enumeration' else 'complete')
                self.assertIsNone(R._DIAGNOSTICS.get())
                self.assertIsNone(_LIMITS.get())
                self.assertIsNone(C._CORRECTION_SOURCE.get())
                self.assertEqual(C._CORRECTION_PATH.get(),())
        row=self.run_line('普通の文章です。')
        self.assertEqual(row['corrected'],'普通の文章です。')
        self.assertEqual(row['analysis_status'],'complete')
        self.assertFalse(row.get('search_reports'))
        self.assertFalse(row['odd_spans'])
    def test_depth_limit_keeps_both_new_anomaly_states(self):
        self.verify(C._CorrectionLimit,'depth_limit')
    def test_cycle_keeps_both_new_anomaly_states(self):
        self.verify(C._CorrectionCycle,'cycle')


if __name__=='__main__':unittest.main()
