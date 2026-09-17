# -*- coding: utf-8 -*-
"""Preparation must reuse unchanged initial-state lines after a local edit."""
import unittest
from unittest.mock import patch
import morphology,corrector,analysis_worker
from vocabulary import VocabularyStore

class PrepareReuseTests(unittest.TestCase):
    def runtime(self):
        runtime=analysis_worker.Runtime()
        runtime.store=VocabularyStore()
        runtime.tokenize=corrector.make_tokenizer(runtime.store)
        return runtime
    def test_one_line_edit_reuses_context_and_content_words(self):
        runtime=self.runtime()
        lines=['確認用の資料です。'+str(i) for i in range(40)]
        with patch.object(morphology,'tokenize',wraps=morphology.tokenize) as native, \
                patch.object(runtime,'tokenize',wraps=runtime.tokenize) as content:
            first=runtime.prepare(lines)
            native.reset_mock();content.reset_mock()
            edited=lines[:];edited[20]=edited[20]+'追記。'
            second=runtime.prepare(edited)
            self.assertLessEqual(native.call_count,2,('Full preparation repeated',native.call_count))
            self.assertEqual(content.call_count,1,'Unchanged content words retokenized')
        fresh=self.runtime().prepare(edited)
        self.assertEqual(second,fresh,'Incremental preparation differs from fresh initial-state result')
        self.assertEqual(first['words'][lines[0]],second['words'][lines[0]])

if __name__=='__main__':unittest.main()