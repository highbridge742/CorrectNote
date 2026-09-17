# -*- coding: utf-8 -*-
"""A companion takes と, independently from a food/object accusative."""
import unittest
import morphology as M
import reading_segments as R
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('家族'),'requires native dictionary')
class ComitativeActivityTests(unittest.TestCase):
    def test_native_to_label_alone_does_not_decide_its_role(self):
        source='かぞくとたべます'
        boundary=R.native_nominal_case_boundary(source,M.tokenize(source),3,'と',('家族',))
        self.assertEqual(boundary,('家族',True))
        for text in ('かぞくとたべます','ともだちとあるきます','ともだちとべんきょうします'):
            with self.subTest(text=text):self.assertTrue(R.completed_native_reading_clause(text,require_object_fit=True))
        for text in ('いすとたべます','かぞくをたべます','かぞくとほんです'):
            with self.subTest(text=text):self.assertFalse(R.completed_native_reading_clause(text,require_object_fit=True))
        self.assertEqual(R.native_nominal_case_boundary('家族と友達',M.tokenize('家族と友達'),2,'と',('家族',)),None)
        self.assertIn('person',S.native_verb_roles('たべ','連用形','たべ',case='と'))
        self.assertNotIn('person',S.native_verb_roles('たべ','連用形','たべ'))

    def test_companion_and_content_object_share_the_same_action(self):
        for text in ('ともだちとごはんをたべます','かぞくとりんごをたべます',
                     'くらすのともだちとごはんをたべます','ともだちとほんをよみます'):
            with self.subTest(text=text):
                self.assertTrue(R.completed_native_reading_clause(text,
                    require_nominal=True,require_object_fit=True))
        for text in ('いすとごはんをたべます','ともだちといすをたべます',
                     'ともだちとぷねらをたべます','ぷねらとごはんをたべます',
                     'ともだちとごはんをたべ','ともだちとごはんをたべるひと'):
            with self.subTest(text=text):
                self.assertFalse(R.completed_native_reading_clause(text,
                    require_nominal=True,require_object_fit=True))

    def test_original_natural_companions_and_quoted_speech_are_retained(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('りょうりをつくってかぞくとたべました。','ともだちとあるきます。',
                     '家族と友達を招待します。','「はい」と言いました。',
                     'ともだちとごはんをたべます。','くらすのともだちとごはんをたべます。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)


if __name__=='__main__':unittest.main()
