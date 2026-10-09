# -*- coding: utf-8 -*-
"""A native quotation marker is distinct from a second argument case."""
import unittest
import morphology as M
import oddness as O
import reading_segments as R

@unittest.skipUnless(M.HAS_JANOME,'requires native dictionary')
class QuotedCaseParticleTests(unittest.TestCase):
    def test_native_quoted_cases_share_the_same_pair_proof(self):
        for source in ('君にと思っています。','友達にと買いました。',
                       'これをと選びました。','自分でと決めました。','君にと。'):
            parts=M.tokenize(source)
            pairs=[(a,b) for a,b in zip(parts,parts[1:]) if a.pos==b.pos=='助詞']
            self.assertEqual(len(pairs),1,source)
            a,b=pairs[0]
            with self.subTest(source=source):
                self.assertEqual(b.pos_sub,'格助詞:引用')
                self.assertFalse(O.case_particle_mismatch(a.surface,a.pos+':'+a.pos_sub,b.surface,b.pos+':'+b.pos_sub))
                self.assertFalse(O.object_particle_mismatch(a.surface,a.pos+':'+a.pos_sub,b.surface,b.pos+':'+b.pos_sub))
                self.assertTrue(R._written_nominal_case_chain_allowed(parts,a.start))

    def test_general_case_errors_and_existing_extensions_remain(self):
        pos='助詞:格助詞:一般'
        for left,right in (('を','に'),('に','を'),('が','を'),('と','に')):
            self.assertTrue(O.case_particle_mismatch(left,pos,right,pos),(left,right))
        self.assertTrue(O.object_particle_mismatch('を',pos,'に',pos))
        self.assertTrue(O.object_particle_mismatch('を',pos,'と',pos))
        for source in ('資料をに入れます。','箱にを入れます。'):
            parts=M.tokenize(source);case=next(t for t in parts if t.pos=='助詞')
            self.assertFalse(R._written_nominal_case_chain_allowed(parts,case.start),source)
        for left,right in (('へ','と'),('から','が')):
            self.assertFalse(O.case_particle_mismatch(left,pos,right,pos))

    def test_quote_does_not_release_an_original_temporal_word(self):
        self.assertTrue(M.preserves_native_adverbial_word('きょうにと思っています。','今日にと思っています。'))
        self.assertFalse(M.preserves_native_adverbial_word('きょうにと思っています。','京にと思っています。'))

    def test_initial_application_keeps_quoted_case_without_purple(self):
        from tests_analysis_async import initial
        from correction_entry import correct_line
        for source in ('君にと思っています。','友達にと買いました。','これをと選びました。','自分でと決めました。'):
            a=initial()
            with self.subTest(source=source):
                result=correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertEqual(result['corrected'],source)
                self.assertEqual(result.get('odd_spans'),[])
                self.assertEqual(result.get('analysis_status'),'complete')

if __name__=='__main__':unittest.main()
