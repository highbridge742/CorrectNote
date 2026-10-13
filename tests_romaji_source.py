# -*- coding: utf-8 -*-
import unittest
from romaji_source import source_keys,_feed
from halfwidth import ROMAJI_TO_KANA,romaji_to_kana


class SourceKeyTests(unittest.TestCase):
    def test_streaming_decoder_matches_every_existing_pair(self):
        for left in ROMAJI_TO_KANA:
            for right in ROMAJI_TO_KANA:
                text=left+right;pending='';out=''
                for ch in text:
                    got=_feed(pending,ch)
                    if got is None:break
                    emitted,pending=got;out+=emitted
                else:
                    got=_feed(pending,'',True)
                    if got is not None:
                        out+=got[0]
                        self.assertEqual(out,romaji_to_kana(text)[0],text)
                        continue
                self.assertTrue(any(c.isascii() and c.isalpha() for c in romaji_to_kana(text)[0]),text)

    def test_existing_spellings_share_a_reading_without_an_edit(self):
        for text,reading in [('shashin','しゃしん'),('syasin','しゃしん'),('chotto','ちょっと'),
                ('tyotto','ちょっと'),('gakkou','がっこう'),('maccha','まっちゃ'),
                ('kanni','かんい'),('shinnnyuu','しんにゅう')]:
            evidence=source_keys(text,reading)
            self.assertTrue(evidence.proved,(text,evidence));self.assertEqual(evidence.edits,0)

    def test_substitution_and_intrusion_use_distinct_original_key_directions(self):
        source='tanhonotunagari';e=source_keys(source,'たんごのつながり')
        self.assertEqual(e.operations,(('adjacent_substitution',3,'h','g'),))
        e=source_keys('tangonotunagqari','たんごのつながり')
        self.assertEqual(e.operations,(('adjacent_intrusion',12,'q',''),))
        # Every removed key keeps its original neighbors. Intermediate
        # shortening cannot invent the physical relation of this pair.
        self.assertFalse(source_keys('yubinkyoku','べんきょう').proved)
        self.assertFalse(source_keys('matcha','まっちゃ').proved)

    def test_transposition_and_missing_key_are_explicit_evidence(self):
        e=source_keys('tangonotungaari','たんごのつながり')
        self.assertEqual(e.operations,(('transposition',10,'ga','ag'),))
        e=source_keys('tangonotuagari','たんごのつながり')
        self.assertEqual(e.operations,(('missing_key',9,'','n'),))
        self.assertFalse(source_keys('tangonotuagari','たんごのつながり',missing_keys=False).proved)

    def test_repeated_key_collapse_remains_an_explicit_option(self):
        for text,reading in [('tangonottunagari','たんごのつながり'),('gakkkou','がっこう')]:
            self.assertFalse(source_keys(text,reading).proved)
            evidence=source_keys(text,reading,duplicate_keys=True)
            self.assertTrue(evidence.proved,evidence)
            self.assertTrue(any(op[0]=='duplicate_deletion' for op in evidence.operations))

    def test_many_spellings_do_not_need_enumeration(self):
        text='si'*40;evidence=source_keys(text,'し'*40)
        self.assertTrue(evidence.proved);self.assertEqual(evidence.visited,len(text)+1)

    def test_limits_are_not_a_completed_negative_result(self):
        self.assertEqual(source_keys('tanhonotunagari','たんごのつながり',state_limit=1).state,'state_limit')
        self.assertEqual(source_keys('si'*65,'し'*65).state,'input_limit')
        evidence=source_keys('yubinkyoku','べんきょう')
        self.assertEqual(evidence.state,'complete');self.assertFalse(evidence.proved)
        self.assertEqual(source_keys('print(shorui)','しょるい').state,'not_applicable')


if __name__=='__main__':unittest.main()
