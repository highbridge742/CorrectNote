# -*- coding: utf-8 -*-
"""Data URL rows are literal data, while surrounding prose still reaches NLP."""
import unittest
from unittest.mock import Mock,patch
import literal_lines as L

DATA_ROWS=(
    'data:image/png;base64,QUJDRA==',
    'DATA:IMAGE/SVG+XML;CHARSET=UTF-8;BASE64,PHN2Zy8+',
    'data:,A%20brief%20note',
    'data:;charset=UTF-8,%E6%96%87',
    'data:application/vnd.example+json;name=sample,%7B%22a%22%3A1%7D',
    'data:,',
    ' \t「data:text/plain,hello%20world」　',
    '"data:application/octet-stream;base64,AA=="',
    'data:image/png;base64,'+'QUJD'*9010,
)

class DataUriLiteralTests(unittest.TestCase):
    def test_data_url_shapes_are_literal_without_size_or_image_type_rules(self):
        for text in DATA_ROWS:
            with self.subTest(length=len(text)):
                self.assertTrue(L.literal_only(text))
        for text in ('data:','data:image/png;base64','data:image/png;base64x,AAAA',
                     'data:image/png;broken,AAAA','data:plain,hello','data:text/plain,hello world',
                     '説明 data:image/png;base64,AAAA','data:image/png;base64,AAAA を保存',
                     'data:image/png;base64,AAAA。','data:,one\ntwo','普通の文章です。'*100):
            with self.subTest(length=len(text)):
                self.assertFalse(L.literal_only(text))

    def test_unfinished_data_payload_is_not_reclassified_as_language(self):
        # The framing is explicit even when percent escapes or base64 are
        # still being typed. NLP cannot repair the data's encoding.
        for text in ('data:,foo%', 'data:,%ZZ', 'data:text/plain,%A',
                     'data:image/png;base64,QUJ'):
            with self.subTest(text=text):self.assertTrue(L.literal_only(text))
        for text in ('data:foo%', 'data:%ZZ', 'data:,foo% を確認する',
                     'データは data:,%ZZ です。'):
            with self.subTest(text=text):self.assertFalse(L.literal_only(text))

    def test_entry_and_worker_paths_do_not_initialize_or_call_nlp(self):
        import correction_entry as E,units
        from analysis_worker import Runtime
        r=Runtime();r.prepare_tables=Mock(side_effect=AssertionError('tables loaded'))
        r.store=r.decisions=r.context_vec=r.choices=None
        r.tokenize=Mock(side_effect=AssertionError('literal row tokenized'))
        with patch.object(E.corrector,'make_tokenizer',side_effect=AssertionError('tokenizer created')):
            for text in DATA_ROWS:
                result=E.correct_line(text,None)
                self.assertEqual(result['corrected'],text)
                self.assertEqual(result['analysis_status'],'complete')
                self.assertFalse(result['odd_spans'])
                self.assertEqual(units.build_line_units(result,r.tokenize,None,None),(text,[]))
                self.assertEqual(units.build_suspect_units(result,r.tokenize,None,None),(text,[]))
            self.assertEqual(r.execute(dict(kind='prepare',lines=list(DATA_ROWS))),L.prepared(DATA_ROWS))
            text=DATA_ROWS[-1]
            value=r.execute(dict(kind='line',line=text,context={},input_method='kana',attested=()))
            self.assertEqual(value['result']['corrected'],text)
            self.assertEqual(value['corrected_units'],(text,[]))
            quick=r.quick(dict(lines=[text],attested=(),input_method='kana',calculations={}))
            self.assertEqual(quick['results'][0]['corrected'],text)
        r.tokenize.assert_not_called();r.prepare_tables.assert_not_called()

    def test_mixed_document_retains_ordinary_row_context(self):
        from analysis_worker import Runtime
        r=Runtime();r.store=object();r.tokenize=Mock()
        def build(lines,store,cache,attested_out,tokenize_fn):
            self.assertEqual(lines,['普通の文章です。']);return {'preserved':True}
        with patch('vocabulary.build_context_vocab_cached',side_effect=build),patch('context_vec.extract_content_words',return_value=['文章']) as words:
            result=r.prepare([DATA_ROWS[-1],'普通の文章です。'])
            words.assert_called_once_with(r.tokenize,'普通の文章です。')
            self.assertEqual(result['context'],{'preserved':True})
            self.assertEqual(result['words'][DATA_ROWS[-1]],[])

if __name__=='__main__':unittest.main()
