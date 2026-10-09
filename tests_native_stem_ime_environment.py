# -*- coding: utf-8 -*-
"""Application correction retains its common gate with or without live IME."""
import unittest
from unittest.mock import patch

from morphology import HAS_JANOME
from tests_analysis_async import initial


@unittest.skipUnless(HAS_JANOME,'Requires real Janome')
class NativeStemIMEEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.state=initial()

    def tearDown(self):
        from last_choice import set_active
        set_active(None)

    def check_application_and_common_gate(self):
        import app,corrector as C
        state=self.state
        def correct(source):
            return app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                                    decisions=state.decisions,context_vec=None)
        source='必要な部分だけを点刷してください。'
        with patch.object(C,'_check_replacement',wraps=C._check_replacement) as gate:
            result=correct(source)
        self.assertEqual(result['corrected'],'必要な部分だけを印刷してください。')
        self.assertFalse(result['odd_spans'])
        self.assertEqual(result['analysis_status'],'complete')
        self.assertGreater(gate.call_count,0)
        for normal in ('必要な部分だけを印刷してください。','「点刷します」と入力します。'):
            with self.subTest(source=normal):
                result=correct(normal)
                self.assertEqual(result['corrected'],normal)
                self.assertFalse(result['odd_spans'])
                self.assertEqual(result['analysis_status'],'complete')
        with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')) as gate:
            result=correct(source)
        self.assertGreater(gate.call_count,0)
        self.assertEqual(result['corrected'],source)
        self.assertTrue(result['odd_spans'])
        self.assertEqual(result['analysis_status'],'complete')

    def test_application_with_live_ime_keeps_output_and_common_gate(self):
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            if not ime.available:self.skipTest('Requires available native IFELanguage')
        self.check_application_and_common_gate()

    def test_application_without_ime_keeps_output_and_common_gate(self):
        with patch('ime_language.JapaneseIME') as ime:
            ime.return_value.__enter__.return_value.available=False
            self.check_application_and_common_gate()


if __name__=='__main__':unittest.main()
