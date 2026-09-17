# -*- coding: utf-8 -*-
import unittest
from types import SimpleNamespace
import corrector as C


class ResolvedDiagnosticTests(unittest.TestCase):
    def report(self,line,corrected,applied,detected,remaining,**kwargs):
        result=dict(corrected=corrected,changed=line!=corrected,original_spans=applied,
                    odd_reasons=[(a,b,'source anomaly') for a,b in detected])
        if remaining is not None:result['odd_spans']=remaining
        result.update(kwargs)
        return C._line_result_contract(line,result,None)

    def test_single_deleted_character_can_resolve_a_larger_connection(self):
        r=self.report('資料を調べいて','資料を調べて',[(5,6)],[(3,6)],[])
        self.assertEqual(r['diagnosis']['replaced_odd_spans'],[[3,6]])
        self.assertEqual(r['diagnosis']['unreplaced_odd_spans'],[])

    def test_unrelated_anomaly_remains_after_a_successful_edit(self):
        r=self.report('甲゜乙丙゛丁','甲乙丙゛丁',[(1,2)],[(0,2),(3,5)],[(3,5)])
        self.assertEqual(r['diagnosis']['replaced_odd_spans'],[[0,2]])
        self.assertEqual(r['diagnosis']['unreplaced_odd_spans'],[[3,5]])

    def test_adjacent_ranges_are_split_by_the_final_unresolved_evidence(self):
        r=self.report('甲゜乙丙','甲乙丙',[(1,2)],[(0,2),(2,4)],[(2,4)])
        self.assertEqual(r['diagnosis']['replaced_odd_spans'],[[0,2]])
        self.assertEqual(r['diagnosis']['unreplaced_odd_spans'],[[2,4]])

    def test_explicit_remaining_range_is_not_cleared_by_a_nearby_edit(self):
        r=self.report('甲゜乙丙','甲乙丙',[(1,2)],[(0,4)],[(2,4)])
        self.assertEqual(r['diagnosis']['unreplaced_odd_spans'],[[2,4]])

    def test_changed_text_is_not_itself_evidence_that_an_anomaly_was_resolved(self):
        r=self.report('甲゜乙丙','甲乙丙',[(1,2)],[(0,4)],[(0,4)])
        self.assertEqual(r['diagnosis']['replaced_odd_spans'],[])
        self.assertEqual(r['diagnosis']['unreplaced_odd_spans'],[[0,4]])

    def test_absent_final_ranges_and_unmodified_results_are_not_proof_of_resolution(self):
        r=self.report('甲゜乙','甲乙',[(1,2)],[(0,2)],None)
        self.assertEqual(r['diagnosis']['unreplaced_odd_spans'],[[0,1]])
        r=self.report('甲゜乙','甲゜乙',[],[(0,2)],[])
        self.assertEqual(r['diagnosis']['unreplaced_odd_spans'],[[0,2]])

    def test_insertion_can_resolve_an_existing_connection(self):
        for position in (0,1,2):
            r=self.report('甲乙','甲と乙',[(position,position)],[(0,2)],[])
            self.assertEqual(r['diagnosis']['unreplaced_odd_spans'],[])

    def test_failed_analysis_does_not_infer_whole_relation_resolution(self):
        for status in ('limited','incomplete'):
            r=self.report('甲゜乙','甲乙',[(1,2)],[(0,2)],[],analysis_status=status)
            self.assertEqual(r['diagnosis']['unreplaced_odd_spans'],[[0,1]])

    def test_invalid_ranges_are_still_reported_as_incomplete(self):
        r=self.report('甲゜乙','甲乙',[(1,2)],[(0,20)],[])
        self.assertEqual(r['analysis_status'],'incomplete')
        self.assertTrue(r['diagnosis']['range_errors'])


if __name__=='__main__':unittest.main()
