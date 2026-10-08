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

    def test_past_relative_keeps_the_complete_original_noun_reading(self):
        from particle_frames import unlinked_past_predicate_frames
        from reading_segments import _native_nominal_reading_faces
        self.assertIn('作品',_native_nominal_reading_faces('さくひん'))
        for tail in ('さくひんぷねら','ねます','かえります'):
            self.assertFalse(_native_nominal_reading_faces(tail))
        for text in ('評価したさくひん','再評価したさくひん','再編集したさくひん'):
            with self.subTest(text=text):
                self.assertFalse(unlinked_past_predicate_frames(text))
                self.assertFalse(C._odd_spans_for_line(text,self.tok,[],self.a.store,
                    self.a.dict_index,include_pending=False))
        for text in ('料理を食べた寝ます。','本を読んだ戻りますね。'):
            self.assertTrue(unlinked_past_predicate_frames(text),text)

    def test_accepted_written_spelling_keeps_final_anomaly_and_shared_gate(self):
        import app,kana_spelling as K
        from unittest.mock import patch
        source='さいひょうかしたさくひん'
        proposal=K.project(source,self.a.store,self.a.dict_index,self.a.decisions)
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal[0],'再評価した作品')
        result=app.correct_line(source,self.a.store,input_method='kana',dict_index=self.a.dict_index,
            decisions=self.a.decisions,context_vec=None)
        # The source noun boundary now survives the same final check;
        # require the completed spelling rather than the earlier partial.
        self.assertEqual(result['corrected'],proposal[0])
        self.assertFalse(result['odd_spans'])
        self.assertEqual(result['analysis_status'],'complete')
        with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
            result=app.correct_line(source,self.a.store,input_method='kana',dict_index=self.a.dict_index,
                decisions=self.a.decisions,context_vec=None)
            self.assertEqual(result['corrected'],source)
        quoted='「さいひょうかしたさくひん」と入力しました。'
        result=app.correct_line(quoted,self.a.store,input_method='kana',dict_index=self.a.dict_index,
            decisions=self.a.decisions,context_vec=None)
        self.assertEqual(result['corrected'],quoted)

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
