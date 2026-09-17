# -*- coding: utf-8 -*-
"""Every core search must retain the evidence of the original whole word."""
import unittest
from unittest.mock import patch
import corrector as C
import reading_segments as R
from tests_native_phrase_context import tokens


class SourceFragmentEntryTests(unittest.TestCase):
    def test_original_mixed_script_word_protects_its_kana_fragment(self):
        source='これはどんでん返しです。'
        parts=tokens([('これ','名詞:代名詞:一般','これ'),('は','助詞:係助詞','は'),
                      ('どんでん返し','名詞:一般','どんでんがえし'),
                      ('です','助動詞','です','基本形'),('。','記号:句点','。')])
        token=C._CORRECTION_SOURCE.set(source)
        try:
            with patch('seed_japanese.is_unit',side_effect=lambda w:w=='どんでん返し'):
                self.assertTrue(C._chunk_is_intact('どんでん',lambda _:parts,context_only=True))
                # An unknown or shifted original token cannot supply this proof.
                bad=parts[:2]+[parts[2][:5]+(False,)+parts[2][6:]]+parts[3:]
                self.assertFalse(C._chunk_is_intact('どんでん',lambda _:bad,context_only=True))
        finally:
            C._CORRECTION_SOURCE.reset(token)

    def test_all_occurrences_must_have_the_same_original_word_evidence(self):
        source='どんでん返し、どんでん'
        parts=tokens([('どんでん返し','名詞:一般','どんでんがえし'),
                      ('、','記号:読点','、'),('どんでん','名詞:一般','どんでん','',False)])
        token=C._CORRECTION_SOURCE.set(source)
        try:
            with patch('seed_japanese.is_unit',side_effect=lambda w:w=='どんでん返し'):
                self.assertFalse(C._chunk_is_intact('どんでん',lambda _:parts,context_only=True))
        finally:
            C._CORRECTION_SOURCE.reset(token)

    def test_core_search_calls_shared_entry_after_removing_prefix(self):
        with patch.object(C,'window_cores',return_value=[(3,7)]), \
             patch.object(C,'_chunk_is_intact',return_value=True) as entry, \
             patch('vocabulary.find_similar_readings') as find:
            # Readability and vocabulary setup belong to the existing caller;
            # the actual core still needs the shared original completion entry.
            with patch.object(C,'_reading_intact',return_value=False), \
                 patch.object(C,'_kana_run_explained',return_value=False):
                C.rebuild_window_core('これはどんでん',None,lambda _:[])
            entry.assert_any_call('どんでん',unittest.mock.ANY,context_only=True)
            find.assert_not_called()

    def test_original_nominal_prefix_is_shared_with_the_fragment(self):
        source='これはどんでん返しです'
        parts=tokens([('これ','名詞:代名詞:一般','これ'),('は','助詞:係助詞','は'),
                      ('どんでん返し','名詞:一般','どんでんがえし'),
                      ('です','助動詞','です','基本形')])
        entries={'これ':(('名詞,代名詞,一般,*','*','これ','これ'),),
                 'は':(('助詞,係助詞,*,*','*','は','は'),)}
        with patch('seed_japanese.is_unit',side_effect=lambda w:w=='どんでん返し'), \
             patch('morphology.dictionary_inflections',side_effect=lambda w:entries.get(w,())):
            self.assertTrue(R.native_word_fragment_context(source,0,7,lambda _:parts))
            # The original topic particle, not a fresh parse of its text,
            # must prove the prefix. An unfinished verb is not that proof.
            bad=[parts[0],parts[1][:1]+('動詞:自立',)+parts[1][2:]]+parts[2:]
            self.assertFalse(R.native_word_fragment_context(source,0,7,lambda _:bad))
            self.assertFalse(R.native_word_fragment_context(source,1,7,lambda _:parts))

    def test_genitive_fragment_requires_its_original_nominal_attachment(self):
        source='説明のどんでん返し'
        parts=tokens([('説明','名詞:サ変接続','せつめい'),('の','助詞:連体化','の'),
                      ('どんでん返し','名詞:一般','どんでんがえし')])
        word=tokens([('どんでん返し','名詞:一般','どんでんがえし')])
        def tokenize(text):
            return parts if text==source else word
        entry=(('名詞,一般,*,*','*','どんでん返し','どんでんがえし'),)
        with patch('seed_japanese.is_unit',side_effect=lambda w:w=='どんでん返し'), \
             patch('morphology.dictionary_inflections',return_value=entry):
            self.assertTrue(R.native_word_fragment_context(source,2,7,tokenize))
            parts[0]=parts[0][:5]+(False,)+parts[0][6:]
            self.assertFalse(R.native_word_fragment_context(source,2,7,tokenize))

    def test_source_fragment_requires_both_native_and_bundled_word_proof(self):
        source='ひっくり返す'
        parts=tokens([('ひっくり返す','動詞:自立','ひっくりかえす','基本形')])
        with patch('seed_japanese.is_unit',return_value=False):
            self.assertFalse(R.native_word_fragment_context(source,0,4,lambda _:parts))
        with patch('seed_japanese.is_unit',return_value=True):
            self.assertFalse(R.native_word_fragment_context(source,0,6,lambda _:parts))
            self.assertTrue(R.native_word_fragment_context(source,0,4,lambda _:parts))


if __name__=='__main__':
    unittest.main()
