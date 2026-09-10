"""Bidirectional reading evidence, coordinates, ambiguity and data sparsity."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import reading_likelihood as L


def token(sf, rd, start=0, known=True):
    return (sf, '名詞:一般', rd, start, start+len(sf), known, '')


class ReadingLikelihoodTests(unittest.TestCase):
    def setUp(self):
        self.table = patch('ngram_yomi.TRIGRAMS', {
            'あいう':10, 'あいえ':30, 'かいう':90,
            'かきく':5000, 'あきけ':6000})
        self.table.start(); L._distributions.cache_clear()
        self.ime=patch('kanji_guess.ime_readings_for',return_value=[])
        self.ime.start()
        self.dic=patch('inflected_lexicon.dictionary_readings',return_value=())
        self.dic.start()

    def tearDown(self):
        self.dic.stop(); self.ime.stop(); self.table.stop()
        L._distributions.cache_clear()

    def test_forward_and_backward_use_different_denominators(self):
        w=L.windows('あいう')[0]
        self.assertEqual((w.count,w.forward_total,w.backward_total),(10,40,100))
        self.assertGreater(w.forward_probability,w.backward_probability)

    def test_character_is_checked_in_all_three_window_positions(self):
        self.assertEqual([w.gram for w in L.windows('あいうえお',2,3)],
                         ['あいう','いうえ','うえお'])
        self.assertEqual([w.gram for w in L.windows('あいうえお',0,1)],['あいう'])
        self.assertEqual([w.gram for w in L.windows('あいうえお',4,5)],['うえお'])

    def test_unseen_context_is_missing_evidence_not_zero_probability(self):
        w=L.windows('わをん')[0]
        self.assertIsNone(w.forward_probability);self.assertIsNone(w.backward_probability)
        self.assertFalse(w.unlikely);self.assertIsNone(L.local_cost('わをん'))

    def test_either_direction_can_supply_evidence_when_other_is_sparse(self):
        self.assertTrue(L.windows('かきけ')[0].unlikely)
        self.assertTrue(L.windows('かきお')[0].unlikely)

    def test_symbols_and_unknown_kanji_break_the_reading(self):
        self.assertEqual(L.windows('かき け'),())
        ts=[token('かき','かき'),token('未知','',2,False),token('け','け',4)]
        self.assertEqual(L.evidence('かき未知け',ts),[])

    def test_source_gap_does_not_create_a_join(self):
        self.assertEqual(L.evidence('かき け',[token('かき','かき'),token('け','け',3)]),[])

    def test_reading_is_mapped_to_whole_kanji_word(self):
        ts=[token('文字','かき'),token('語','け',2)]
        row=L.evidence('文字語',ts)[0]
        self.assertEqual((row['source_start'],row['source_end']),(0,3))
        self.assertEqual(row['surfaces'],['文字','語'])

    def test_saved_ime_precedes_analyzer(self):
        with patch('kanji_guess.ime_readings_for',return_value=['かきけ']):
            rows=L.evidence('文字',[token('文字','あいう')])
        self.assertEqual(rows[0]['gram'],'かきけ')
        self.assertEqual(rows[0]['reading_sources'],['saved_ime_pair'])

    def test_whole_ime_pair_precedes_conflicting_token_readings(self):
        with patch('kanji_guess.ime_readings_for',side_effect=lambda s:['あいう'] if s=='文字語' else []):
            rows=L.evidence('文字語',[token('文字','かき'),token('語','け',2)])
        self.assertEqual(rows,[])

    def test_unaligned_whole_ime_pair_does_not_invent_token_boundaries(self):
        with patch('kanji_guess.ime_readings_for',side_effect=lambda s:['かきけ'] if s=='文字語' else []):
            rows=L.evidence('文字語',[token('文字','あい'),token('語','う',2)])
        self.assertEqual(rows[0]['alignment'],'whole_ime_span')
        self.assertFalse(rows[0]['supported'])

    def test_alternative_reading_prevents_false_certainty(self):
        with patch('inflected_lexicon.dictionary_readings',side_effect=lambda s: ('あい',) if s=='文字' else ('う',)):
            rows=L.evidence('文字語',[token('文字','かき'),token('語','け',2)])
        self.assertFalse(rows[0]['supported'])

    def test_rare_valid_word_and_normal_boundary_are_not_new_anomalies(self):
        ts=[token('かき','かき'),token('け','け',2)]
        self.assertEqual(L.nominal_slot_spans('かきけ',ts),[])
        row=L.evidence('文字',[token('文字','かきけ')])[0]
        self.assertFalse(row['supported'])

    def test_local_repair_cost_includes_following_characters(self):
        self.assertNotEqual(L.edit_cost('かき','あき',after='け'),
                            L.edit_cost('かき','あき',after='く'))

    def test_deletion_checks_new_join_and_empty_reading_is_valid(self):
        self.assertIsNotNone(L.edit_cost('かあきく','かきく'))
        self.assertIsNone(L.edit_cost('か',''))
        self.assertEqual(L.windows(''),())

    def test_dakuten_is_one_reading_character(self):
        self.assertEqual([w.gram for w in L.windows('かがきく',1,2)],['かがき','がきく'])

    def test_adjacent_readings_stop_at_uncertain_reading_and_spaces(self):
        ts=[token('かき','かき'),token('対象','たいしょう',2),token('けく','けく',4)]
        self.assertEqual(L.adjacent_readings('かき対象けく',ts,2,4),('かき','けく'))
        ts[-1]=token('けく','けく',5)
        self.assertEqual(L.adjacent_readings('かき対象 けく',ts,2,4),('かき',''))

    def test_invalid_range_is_not_silently_scored(self):
        with self.assertRaises(ValueError):L.windows('あいう',0,4)

    def test_nominal_slot_needs_grammar_and_reading_evidence(self):
        a=token('文字','かき')
        b=('持つ','動詞:自立','け',2,4,True,'基本形')
        c=('を','助詞:格助詞','を',4,5,True,'')
        with patch('inflected_lexicon.has_nominal_entry',return_value=False):
            self.assertEqual(L.nominal_slot_spans('文字持つを',[a,b,c]),[('文字','持つを',0,5)])
            nominal=(b[0],'名詞:一般')+b[2:]
            self.assertEqual(L.nominal_slot_spans('文字持つを',[a,nominal,c]),[])
            self.assertEqual(L.nominal_slot_spans('文字持つを',[a,b[:5],c]),[])

    def test_nominal_alternative_and_known_compound_are_preserved(self):
        a=token('文字','かき');b=('持つ','動詞:自立','け',2,4,True,'基本形')
        c=('を','助詞:格助詞','を',4,5,True,'')
        with patch('inflected_lexicon.has_nominal_entry',return_value=True):
            self.assertEqual(L.nominal_slot_spans('文字持つを',[a,b,c]),[])

        with patch('inflected_lexicon.has_nominal_entry',return_value=False), \
             patch('inflected_lexicon.dictionary_readings',return_value=('かきけ',)):
            self.assertEqual(L.nominal_slot_spans('文字持つを',[a,b,c]),[])

    def test_bare_clause_object_uses_first_predicate_base_form(self):
        import morphology as M
        part=lambda pos,base:SimpleNamespace(pos=pos,base_form=base,has_reading=True)
        M.allows_bare_clause_object.cache_clear()
        try:
            with patch.object(M,'tokenize',return_value=[part('名詞','心'),part('助詞','から'),part('動詞','知る')]):
                self.assertTrue(M.allows_bare_clause_object('文語の述語'))
            with patch.object(M,'tokenize',return_value=[part('動詞','置く'),part('動詞','知る')]):
                self.assertFalse(M.allows_bare_clause_object('別の述語'))
            with patch.object(M,'tokenize',return_value=[part('記号','。'),part('動詞','知る')]):
                self.assertFalse(M.allows_bare_clause_object('別の文'))
        finally:M.allows_bare_clause_object.cache_clear()


if __name__=='__main__':unittest.main()
