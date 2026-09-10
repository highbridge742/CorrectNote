# -*- coding: utf-8 -*-
import unittest,json
from unittest.mock import patch
import corrector as C
import analysis_cache as A


class ResultStateTests(unittest.TestCase):
    def test_malformed_evidence_is_incomplete_without_losing_valid_ranges(self):
        r=self.result('😀あいう',odd_spans=[(0,2),None,(2,),('2',3),(True,2)],
                      odd_reasons=[(2,4,'rule'),(0,)],original_spans=[(0,1),(3,9)])
        out=C._line_result_contract(r['original'],r,None)
        self.assertEqual(out['analysis_status'],'incomplete')
        self.assertEqual(out['stop_reason'],'invalid_source_ranges')
        self.assertEqual(out['diagnosis']['detected_odd_spans'],[[0,4]])
        self.assertEqual(out['diagnosis']['unreplaced_odd_spans'],[[1,4]])
        self.assertEqual(len(out['diagnosis']['range_errors']),6)
        self.assertEqual(r['odd_spans'][1],None)

    def test_bad_container_does_not_claim_normal_or_overwrite_stop_reason(self):
        r=self.result(odd_reasons='broken',original_spans=12,stop_reason='cycle')
        out=C._line_result_contract('文章',r,None)
        self.assertEqual(out['analysis_status'],'incomplete')
        self.assertEqual(out['stop_reason'],'cycle')
        self.assertEqual(out['diagnosis']['judgement'],'undetermined')
        self.assertEqual([e['field'] for e in out['diagnosis']['range_errors']],
                         ['odd_reasons','original_spans'])

    def test_bad_ranges_are_not_clamped_into_valid_evidence(self):
        out=C._line_result_contract('文章',self.result(odd_spans=[(-1,1),(0,3),(1,1),(2,1)]),None)
        self.assertEqual(out['diagnosis']['detected_odd_spans'],[])
        self.assertEqual(out['diagnosis']['judgement'],'undetermined')

    def test_insertions_are_valid_source_points(self):
        for point in (0,1,2):
            r=self.result('文章',changed=True,original_spans=[(point,point)])
            out=C._line_result_contract('文章',r,None)
            self.assertEqual(out['analysis_status'],'complete')
            self.assertEqual(out['diagnosis']['range_errors'],[])

    def test_swap_diff_does_not_report_incomplete_analysis(self):
        r=self.result('確認しらた',corrected='確認したら',changed=True,
                      original_spans=[(3,3),(4,5)])
        out=C._line_result_contract(r['original'],r,None)
        self.assertEqual(out['analysis_status'],'complete')
        self.assertNotIn('stop_reason',out)

    def test_insertion_point_does_not_claim_anomaly_span_resolved(self):
        r=self.result('文章',changed=True,odd_spans=[(0,2)],original_spans=[(1,1)])
        d=C._line_result_contract('文章',r,None)['diagnosis']
        self.assertEqual(d['replaced_odd_spans'],[])
        self.assertEqual(d['unreplaced_odd_spans'],[[0,2]])

    def test_outside_insertion_point_is_still_invalid(self):
        r=self.result('文章',changed=True,original_spans=[(3,3)])
        out=C._line_result_contract('文章',r,None)
        self.assertEqual(out['analysis_status'],'incomplete')
        self.assertEqual(len(out['diagnosis']['range_errors']),1)

    def result(self,line='文章',**changes):
        result=dict(original=line,corrected=line,changed=False,details=[],spans=[],
                    original_spans=[],odd_spans=[],odd_reasons=[],unsure_spans=[])
        result.update(changes)
        return result

    def test_no_mark_does_not_claim_grammatical_proof(self):
        out=C._line_result_contract('文章',self.result(),None)
        self.assertEqual(out['analysis_status'],'complete')
        self.assertEqual(out['diagnosis']['judgement'],'no_anomaly_reported')
        self.assertEqual(out['diagnosis']['analyzer'],'external')

    def test_missing_analyzer_is_limited_not_zero_candidates(self):
        def tok(line):return []
        tok.analysis_backend='fallback'
        out=C._line_result_contract('文章',self.result(),tok)
        self.assertEqual(out['analysis_status'],'limited')
        self.assertEqual(out['diagnosis']['missing_resources'],['janome'])
        self.assertEqual(out['diagnosis']['judgement'],'undetermined')

    def test_partial_resolution_uses_original_codepoints(self):
        line='😀あいう漢字'
        r=self.result(line,odd_reasons=[(1,6,'rule')],original_spans=[(2,4)],changed=True)
        d=C._line_result_contract(line,r,None)['diagnosis']
        self.assertEqual(d['detected_odd_spans'],[[1,6]])
        self.assertEqual(d['replaced_odd_spans'],[[2,4]])
        self.assertEqual(d['unreplaced_odd_spans'],[[1,2],[4,6]])
        self.assertEqual(r['odd_reasons'],[(1,6,'rule')])

    def test_multiple_corrections_and_overlapping_evidence(self):
        r=self.result('あいうえおか',odd_spans=[(0,4),(2,6)],original_spans=[(0,2),(4,6)])
        d=C._line_result_contract(r['original'],r,None)['diagnosis']
        self.assertEqual(d['detected_odd_spans'],[[0,6]])
        self.assertEqual(d['unreplaced_odd_spans'],[[2,4]])
        self.assertEqual(d['replaced_odd_spans'],[[0,2],[4,6]])

    def test_interruption_reason_survives_cache_roundtrip(self):
        r=C._line_result_contract('文章',self.result(analysis_status='incomplete',
                    stop_reason='depth_limit',diagnostic_limit=32),None)
        packed=A._pack(r)
        out=A._unpack(json.loads(json.dumps(packed)))
        self.assertEqual(out,r)
        out['diagnosis']['missing_resources'].append('test')
        self.assertEqual(r['diagnosis']['missing_resources'],[])

    def test_old_cache_record_is_readable_without_fabricating_status(self):
        r=A._unpack({'o':'文章','c':'文章'})
        self.assertNotIn('analysis_status',r)
        self.assertNotIn('diagnosis',r)

    def test_backend_participates_in_fingerprint(self):
        with patch.object(A,'_morphology_backend',return_value='fallback'):
            a=A.build_fingerprint('.', '1.7.0', 'kana', ())
        with patch.object(A,'_morphology_backend',return_value='janome'):
            b=A.build_fingerprint('.', '1.7.0', 'kana', ())
        self.assertNotEqual(a,b)

    def test_incomplete_tabs_are_not_reused_from_disk(self):
        import tempfile,os
        with tempfile.TemporaryDirectory() as folder:
            path=os.path.join(folder,'cache.json')
            completed=self.result('完了',analysis_status='complete')
            incomplete=self.result('途中',analysis_status='incomplete')
            self.assertTrue(A.save(path, {'engine':'test'}, {'完了':[completed], '途中':[incomplete]}))
            self.assertEqual(set(A.load(path, {'engine':'test'})), {'完了'})
            # 他の版や手動編集で保存された未完了結果も読む側で拒む。
            data={'fingerprint':{'engine':'test'},'tabs':[{'text':'途中','results':[A._pack(incomplete)]}]}
            with open(path,'w',encoding='utf-8') as f:json.dump(data,f)
            self.assertEqual(A.load(path,{'engine':'test'}),{})

    def test_general_semantic_rules_participate_in_startup_fingerprint(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            rule=Path(folder)/'semantic_roles.py'
            rule.write_text('first',encoding='utf8')
            with patch.object(A,'_ENGINE_SOURCES_SEEN',None):
                old=A._engine_source_stamp(folder)
                rule.write_text('changed rules',encoding='utf8')
                self.assertEqual(old,A._engine_source_stamp(folder))
            with patch.object(A,'_ENGINE_SOURCES_SEEN',None):
                self.assertNotEqual(old,A._engine_source_stamp(folder))

if __name__ == '__main__':
    unittest.main()
