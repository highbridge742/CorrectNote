# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch
import kanji_guess as K


class ReadingEvidenceTests(unittest.TestCase):
    def test_exact_pair_first_and_duplicates_have_observed_source(self):
        out=[]
        result=K._reading_result(['いった','おこなった'],[],
                                 [('いった',0),('こうった',1)],out)
        self.assertEqual(result,[('いった',0),('おこなった',0),('こうった',1)])
        self.assertEqual([r['source'] for r in out],
                         ['saved_ime_pair','saved_ime_pair','character_reading_reconstruction'])
        self.assertTrue(all(not r['occurrence_verified'] for r in out))

    def test_segment_does_not_claim_winner_when_character_rank_is_better(self):
        out=[]
        K._reading_result([], [('あ',2),('い',1)], [('あ',0),('い',1)],out)
        self.assertEqual([r['source'] for r in out],
                         ['character_reading_reconstruction','saved_ime_segment_reconstruction'])

    def test_unreadable_character_still_returns_ime_evidence(self):
        with patch.object(K,'ime_readings_for',return_value=['よみ']), \
             patch.object(K,'readings_for_char',return_value=[]):
            out=K.reading_combos_with_evidence('仮')
        self.assertEqual(out,[dict(reading='よみ',rank=0,order=1,
                                  source='saved_ime_pair',occurrence_verified=False)])

    def test_detailed_api_uses_one_search_and_preserves_ranked_api(self):
        with patch.object(K,'ime_readings_for',return_value=[]), \
             patch.object(K,'_ime_segment_combos',return_value=[]), \
             patch.object(K,'readings_for_char',return_value=['あ','い']) as chars, \
             patch.object(K,'_pattern_penalty',return_value=0):
            out=K.reading_combos_with_evidence('仮')
            self.assertEqual(chars.call_count,1)
            plain=K.reading_combos_with_rank('仮')
        self.assertEqual([(r['reading'],r['rank']) for r in out],plain)

    def test_empty_sources_do_not_invent_evidence(self):
        out=[]
        self.assertEqual(K._reading_result([],[],[],out),[])
        self.assertEqual(out,[])

    def test_unobserved_api_returns_legacy_result(self):
        self.assertEqual(K._reading_result([],[],[('あ',1),('い',2)],None),
                         [('あ',1),('い',2)])


if __name__=='__main__':unittest.main()
