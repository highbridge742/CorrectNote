# -*- coding: utf-8 -*-
"""Shared person semantics and source-only honorific grammar keep their own scope."""
import unittest
import morphology as M

@unittest.skipUnless(M.HAS_JANOME,'requires native Janome dictionary')
class NominalSourcePeopleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        cls.a=initial()

    def correct(self,text):
        import app
        from decisions import DecisionStore
        return app.correct_line(text,self.a.store,dict_index=self.a.dict_index,
            decisions=DecisionStore(),input_method='kana',context_vec=None)

    def test_person_roles_do_not_leak_to_homophones_or_waiting_states(self):
        import semantic_roles as S,reading_segments as R
        for face in ('患者','病人','怪我人','負傷者'):
            self.assertIn('person',S.nominal_roles(face),face)
        for face in ('病気','病院','奸邪','寒邪','患者待ち','病人待ち'):
            self.assertNotIn('person',S.nominal_roles(face),face)
        self.assertIn('患者待ち',R.native_waiting_nominal_faces('かんじゃまち'))
        self.assertIn('病人待ち',R.native_waiting_nominal_faces('びょうにんまち'))
        # 病気 is already a native sahen event and can enter the old
        # waiting-event proof. It must not gain a person role (checked above).
        for face in ('奸邪待ち','寒邪待ち','病院待ち'):
            self.assertFalse(R.native_waiting_nominal_faces(face),face)
        for head in ('かんじゃまち','びょうにんまち'):
            for tail in ('。','です。','なのでほんをよみます。'):
                text=head+tail;result=self.correct(text)
                self.assertEqual(result['corrected'],text)
                self.assertFalse(result['odd_spans'])
        result=self.correct('かんじゃまちなのでほんをよみまうす。')
        self.assertEqual(result['corrected'],'かんじゃまちなのでほんをよみまうす。')
        self.assertFalse(result['odd_spans'])

    def test_honorific_evidence_is_source_protection_not_a_common_noun(self):
        import reading_segments as R,semantic_roles as S
        for text in ('かずひでさん','かずひでくん','かずひでちゃん','ぷねらさん'):
            self.assertTrue(R.source_honorific_name(text),text)
            self.assertTrue(R.intact_native_reading(text),text)
            self.assertFalse(R.native_nominal_phrase_faces(text),text)
            self.assertFalse(S.nominal_roles(text),text)
            result=self.correct(text+'。')
            self.assertEqual(result['corrected'],text+'。')
            self.assertFalse(result['odd_spans'])
        for text in ('せくん','ほんをよみまうすさん','かずひで','ぷねら'):
            self.assertFalse(R.source_honorific_name(text),text)
        text='かずひでさん、ほんをよみまうす。'
        ranges=R.source_honorific_name_ranges(text)
        self.assertEqual(ranges,((0,6),))
        result=self.correct(text)
        self.assertEqual(result['corrected'],text)
        self.assertFalse(result['odd_spans'])

    def test_classified_suffix_readings_keep_the_native_rows_and_exact_word(self):
        import reading_segments as R
        for face,reading in (('怪我人','けがにん'),('負傷者','ふしょうしゃ'),
                             ('担当者','たんとうしゃ'),('交通費','こうつうひ'),
                             ('帆立','ほたて')):
            self.assertTrue(R.native_common_noun_reading(face,reading),(face,reading))
        for face,reading in (('怪我人','けがじん'),('負傷者','ふしょうもの'),
                             ('帆立','ほりつ'),('ぷねら費','ぷねらひ')):
            self.assertFalse(R.native_common_noun_reading(face,reading),(face,reading))
        self.assertEqual(M.tokenize('怪我人')[-1].reading,'じん')
        for kana,written in (('けがにん','怪我人'),('ふしょうしゃ','負傷者'),
                             ('りようしゃ','利用者'),('たんとうしゃ','担当者')):
            self.assertIn(written+'待ち',R.native_waiting_nominal_faces(kana+'まち'))
            self.assertIn(written+'待ち',R.native_waiting_nominal_faces(written+'待ち'))
            text=kana+'まちです。';result=self.correct(text)
            self.assertEqual(result['corrected'],text)
            self.assertFalse(result['odd_spans'])
        for text in ('けがじんまち','ふしょうものまち','ぷねらしゃまち'):
            self.assertFalse(R.native_waiting_nominal_faces(text),text)
        text='けがにんまちなのでしりょうをほぞんしまうす。'
        result=self.correct(text)
        self.assertEqual(result['corrected'],text)
        self.assertFalse(result['odd_spans'])

    def test_honorific_copula_and_case_protect_only_the_original_nominal(self):
        import reading_segments as R
        for head in ('かずひでさん','ぷねらさん','ひろしちゃん'):
            for tail in ('です。','でした。','なのです。','だったんです。',
                         'に資料を渡します。','と話します。','の本。','は来ます。','を待ちます。'):
                text=head+tail;result=self.correct(text)
                self.assertEqual(result['corrected'],text)
                self.assertFalse(result['odd_spans'],text)
            for tail in ('に','と','は'):
                result=self.correct(head+tail+'。')
                self.assertEqual(result['corrected'],head+tail+'。')
                self.assertFalse(result['odd_spans'])
        for text in ('かずひでさんでうす','かずひでさんでます','かずひでさんですん'):
            self.assertFalse(R.intact_native_reading(text),text)
            self.assertFalse(any(begin==0 and end==len(text)
                for begin,end in R.source_honorific_name_ranges(text)),text)
        text='ぷねらさんに資料を食べます'
        self.assertEqual(R.source_honorific_name_ranges(text,case_only=True),((0,6),))
        self.assertFalse(R.intact_native_reading(text))
        self.assertFalse(R.native_nominal_phrase_faces('ぷねらさん'))
        self.assertFalse(R.completed_native_nominal_predicate('ぷねらさんです'))
        # The copied source suffix supplies no spelling and no semantic
        # approval of a following action. Its unresolved meaning stays open.
        text='かずひでさんにに資料を渡します。';result=self.correct(text)
        self.assertEqual(result['corrected'],text)
        self.assertTrue(result['odd_spans'])

    def test_native_kana_name_keeps_its_source_spelling_without_new_noun_faces(self):
        import reading_segments as R
        for head in ('わたなべさん','たかはしくん','よしおちゃん'):
            self.assertTrue(R.source_honorific_name(head),head)
            self.assertFalse(R.native_nominal_phrase_faces(head),head)
            for tail in ('。','です。','に資料を渡します。','の本。'):
                text=head+tail;result=self.correct(text)
                self.assertEqual(result['corrected'],text)
                self.assertFalse(result['odd_spans'],text)
        # Unknown/long spellings gain no invented native entry; the source
        # name evidence still differs from an ordinary lexical candidate.
        for text in ('せくん','ぷねらたろうさん','ほんをよみまうすさん'):
            self.assertFalse(R.source_honorific_name(text),text)

if __name__=='__main__':unittest.main()
