import unittest
from unittest.mock import patch
import morphology as M

@unittest.skipUnless(M.HAS_JANOME,'native dictionary required')
class ReopenedNominalSpellingTests(unittest.TestCase):
    def setUp(self):
        from tests_analysis_async import initial
        from last_choice import set_active
        self.state=initial();self.addCleanup(set_active,None)

    def run_source(self,source):
        from correction_entry import correct_line
        return correct_line(source,self.state.store,context_vocab={},input_method='romaji',
            dict_index=self.state.dict_index,decisions=self.state.decisions,context_vec=self.state.context_vec)

    def test_original_positive_noun_reaches_local_and_original_ascii_gates(self):
        import corrector as C
        original=C._check_replacement;calls=[]
        def record(*args,**kwargs):
            calls.append((args[0],args[1]));return original(*args,**kwargs)
        source='gakuseigakouendearukimasu'
        with patch.object(C,'_check_replacement',record):result=self.run_source(source)
        self.assertEqual(result['corrected'],'学生が公園で歩きます')
        self.assertFalse(result['odd_spans']);self.assertEqual(result['analysis_status'],'complete')
        self.assertIn(('学生がこうえんであるきます',(3,7,'公園','かな入力')),calls)
        self.assertTrue(any(text==source and proposal[2]==result['corrected'] for text,proposal in calls))

    def test_local_nominal_rejection_does_not_silently_adopt_the_other_face(self):
        import corrector as C
        original=C._check_replacement
        def reject(*args,**kwargs):
            return (None,'forced_nominal') if args[1][2]=='公園' else original(*args,**kwargs)
        with patch.object(C,'_check_replacement',reject):
            result=self.run_source('gakuseigakouendearukimasu')
        self.assertEqual(result['corrected'],'学生がこうえんで歩きます')
        self.assertNotIn('講演',result['corrected'])

    def test_explicit_last_choice_is_not_overwritten_by_generated_nominal(self):
        import corrector as C
        original=C._check_replacement;calls=[]
        def record(*args,**kwargs):
            calls.append(args[1]);return original(*args,**kwargs)
        with patch('last_choice.surface_for_reading',side_effect=lambda reading:'講演' if reading=='こうえん' else None),patch.object(C,'_check_replacement',record):
            self.run_source('gakuseigakouendearukimasu')
        self.assertTrue(any(proposal[2]=='講演' for proposal in calls))
        self.assertFalse(any(proposal[2]=='公園' for proposal in calls))

    def test_original_partial_key_block_owns_only_its_field(self):
        source='kouendearukimasu\tgakuseigakouendearukimasu'
        self.state.decisions.protect('gakuseigakouen')
        result=self.run_source(source)
        self.assertEqual(result['corrected'],'公園で歩きます\tgakuseigakouendearukimasu')
        self.assertFalse(result['odd_spans']);self.assertEqual(result['analysis_status'],'complete')

if __name__=='__main__':unittest.main()
