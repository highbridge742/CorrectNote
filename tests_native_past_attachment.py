"""Past attachment uses the original predicate and preserves uncertain words."""
import unittest

import corrector as C
import oddness as O
from tests_analysis_async import initial


class NativePastAttachmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = initial()
        cls.tok = staticmethod(C.make_tokenizer(cls.a.store))

    def marks(self, text):
        return O.is_odd_run(text, self.tok, with_spans=True,
            store=self.a.store, dict_index=self.a.dict_index, complete_line=True)

    def test_past_attachment_is_owned_by_the_unchanged_completed_predicate(self):
        for text in ('資料を保存するたら連絡します。',
                     'しりょうをほぞんするたられんらくし'):
            with self.subTest(text=text):
                start = text.index('するたら')
                self.assertIn(('する', 'たら', start, start + 4), self.marks(text))

    def test_native_pairs_inside_uncertain_words_do_not_establish_a_source_defect(self):
        for text in ('するたらこ', 'ぷねらをするたら',
                     '資料を保存したら連絡します。',
                     'しりょうをほぞんしたられんらくし',
                     '資料を確認するたびに保存します。',
                     '先生が来たら始めます。', '本を読んだら返します。',
                     '買うたらええ。', 'この形に沿うたらええ。',
                     'やめろったら。', '見たり聞いたりします。'):
            with self.subTest(text=text):
                self.assertFalse(self.marks(text))

    def test_final_chain_validation_reuses_the_same_native_attachment(self):
        original = '資料を保存したら連絡します。'
        changed = '資料を保存するたら連絡します。'
        self.assertFalse(O.changed_auxiliary_chain_allowed(changed, 5, 7, original))
        self.assertTrue(O.changed_auxiliary_chain_allowed(original, 5, 6, original))


    def test_narrow_and_wide_candidates_cannot_drop_original_written_object_proof(self):
        source = '資料を保存するた。'
        for part, surface in (('た', 'と'), ('するた', 'すると'),
                              ('資料を保存するた', '資料を保存すると')):
            with self.subTest(part=part):
                start = source.index(part)
                end = start + len(part)
                result, reason = C._check_replacement(source,
                    (start, end, surface, 'かな入力'), self.a.store, self.tok,
                    self.a.dict_index, conv_taken=((start,end),))
                self.assertIsNone(result)
                self.assertEqual(reason, 'unproven_original_object_predicate')
        result, reason = C._check_replacement(source,
            (0, len(source), '資料を保存した。', 'かな入力'),
            self.a.store, self.tok, self.a.dict_index,
            conv_taken=((0,len(source)),))
        self.assertIsNotNone(result, reason)


if __name__ == '__main__':
    unittest.main()
