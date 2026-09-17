# -*- coding: utf-8 -*-
"""Existing native okurigana stems recover readings lost in IME conversion."""
import unittest
import morphology as M
import kanji_guess as K
import contextual_repair as CR
import corrector as C
import kana_layout


@unittest.skipUnless(M.dictionary_inflections('削除'),'requires native dictionary')
class ImeNativeStemTests(unittest.TestCase):
    def test_inverse_readings_reuse_native_data_without_relaxing_ordinary_words(self):
        for ch,stem in (('誘','さそ'),('誤','あやま'),('並','なら')):
            self.assertIn(stem,K.ime_reconstruction_readings_for_char(ch))
        choices=K.ime_reconstruction_readings_for_char('誤')
        self.assertNotIn('あやま',K._drop_okurigana_readings('誤学習',0,'誤',choices,''))
        choices=K.ime_reconstruction_readings_for_char('誘')
        self.assertNotIn('さそ',K._drop_okurigana_readings('誘導',0,'誘',choices,''))

    def test_target_readings_and_physical_operation_use_the_recorded_ime_reading(self):
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        text='古い設定を誘駆除して保存します。'
        targets=CR.targets_for_line(text,tokenize,a.store,a.dict_index)
        target=next(t for t in targets if t.text=='誘駆除')
        readings=CR.reading_evidence(target,tokenize,a.dict_index)
        self.assertIn('さそくじょ',[r.text for r in readings])
        self.assertTrue(kana_layout.single_key_drop_adjacency('さそくじょ','さくじょ'))
        # The inverse reading is evidence, not a claim that this unknown
        # compound is itself a native word or that it was typed this time.
        row=next(r for r in readings if r.text=='さそくじょ')
        self.assertNotEqual(row.source,'current_ime_occurrence')

    def test_application_uses_context_and_preserves_real_native_words(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        rows=[('古い設定を誘駆除して保存します。','古い設定を削除して保存します。')]
        rows.extend((text,text) for text in ('友達を誘います。','誤学習を防ぎます。',
            '彼を宥恕します。','本を並べます。','係員が誘導します。'))
        for text,expected in rows:
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result.get('odd_spans'),[])


if __name__=='__main__':unittest.main()
