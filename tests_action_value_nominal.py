# -*- coding: utf-8 -*-
import unittest
import app,corrector as C,reading_segments as R,morphology as M
from tests_analysis_async import initial

@unittest.skipUnless(M.HAS_JANOME,'requires native Janome dictionary')
class ActionValueNominalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=initial()
    def test_dictionary_continuative_is_required_before_the_nominal_suffix(self):
        for source in ('およぎがい','泳ぎ甲斐','かきがい','書きがい','はなしがい','いきがい','やりがい'):
            self.assertEqual(R.native_action_value_nominal_faces(source),(source,),source)
        for source in ('まとがい','ぷねらがい','およぐがい','泳ぐ甲斐','がい','甲斐','はなしがいプネラ'):
            self.assertFalse(R.native_action_value_nominal_faces(source),source)
    def test_initial_stages_keep_the_derived_noun_and_reject_the_wrong_inflection(self):
        from janome_import import import_from_janome
        a=self.a
        for phase in ('seed','fresh'):
            if phase=='fresh':import_from_janome(a.store)
            for source in ('およぎがい','およぎがいがある','およぎがいがあります。',
                           '泳ぎ甲斐','泳ぎ甲斐がある。','かきがい','はなしがいのある相手',
                           'いきがい','やりがい','間違い','まちがい'):
                with self.subTest(phase=phase,source=source):
                    r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                        context_vec=a.context_vec if phase=='fresh' else None,decisions=a.decisions)
                    self.assertEqual(r['corrected'],source);self.assertEqual(r.get('odd_spans'),[])
            r=app.correct_line('まとがい',a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=a.context_vec if phase=='fresh' else None,decisions=a.decisions)
            self.assertEqual(r['corrected'],'間違い');self.assertEqual(r.get('odd_spans'),[])
if __name__=='__main__':unittest.main()
