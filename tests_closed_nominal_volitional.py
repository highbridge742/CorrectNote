# -*- coding: utf-8 -*-
import unittest
import app,corrector as C,contextual_repair as Q,reading_segments as R,morphology as M,oddness as O
from tests_analysis_async import initial

@unittest.skipUnless(M.HAS_JANOME,'requires native Janome dictionary')
class ClosedNominalVolitionalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=initial();cls.tok=staticmethod(C.make_tokenizer(cls.a.store))
    def test_adjacent_particles_do_not_isolate_a_volitional_suffix(self):
        import app
        state = self.a
        row = app.correct_line('保存したがぞ背うを確認します。', state.store,
            input_method='kana', dict_index=state.dict_index,
            decisions=state.decisions, context_vec=None)
        self.assertNotIn('ぞよう', row['corrected'])

    def test_only_an_explicit_finished_boundary_supplies_the_source_judgment(self):
        for source,wanted in (('入力茶う',False),('入力茶う。',True),('入力茶う\t資料',True),
                              ('入力茶う 資料',False),('入力茶う  資料',True),('入力茶うを表示します。',True),
                              ('入力茶うは表示します。',False)):
            parts=self.tok(source);pair=next((p,q) for p,q in zip(parts,parts[1:]) if p[0]=='茶' and q[0]=='う')
            self.assertEqual(O.closed_nominal_volitional_mismatch(source,*pair),wanted,source)
        for source in ('会社に行こう。','お茶を飲もう。','入力しちゃう。','入力よう。',
                       '入力例：「入力茶う。」'):
            parts=self.tok(source)
            self.assertFalse(any(O.closed_nominal_volitional_mismatch(source,p,q) for p,q in zip(parts,parts[1:])),source)
    def test_completed_line_and_open_fragment_have_different_source_boundaries(self):
        # No preferred repair is assumed for this independently parsed source.
        source='名前う';pair=self.tok(source)[-2:]
        self.assertFalse(O.closed_nominal_volitional_mismatch(source,*pair))
        self.assertTrue(O.closed_nominal_volitional_mismatch(source,*pair,allow_line_end=True))

    def test_existing_phase_proof_also_provides_the_whole_candidate_spelling(self):
        for reading,word in (('にゅうりょくちゅう','入力中'),('さぎょうまえ','作業前'),
                             ('しゅつりょくまち','出力待ち')):
            words=Q._surfaces(reading,self.a.store,self.a.dict_index,compose=True)
            self.assertIn(word,words)
        self.assertFalse(R.native_temporal_nominal_faces('かんりょうちゅう'))
        self.assertFalse(R.native_temporal_nominal_faces('ぷねらちゅう'))
    def test_initial_stages_repair_closed_fields_and_keep_open_or_colloquial_text(self):
        from janome_import import import_from_janome
        a=self.a
        for phase in ('seed','fresh'):
            if phase=='fresh':import_from_janome(a.store)
            rows=[('入力茶う','入力中'),('入力茶う。','入力中。'),('入力茶う\t次の項目','入力中\t次の項目'),
                  ('入力茶う  資料','入力中  資料')]
            rows += [(t,t) for t in ('入力ちゃう。','入力しちゃう。','お茶うまい。',
                     '入力よう。','入力用。','編集中。','お茶を飲もう。','会社に行こう。',
                     '「入力茶う」と入力します。','入力例：「入力茶う。」')]
            for source,expected in rows:
                with self.subTest(phase=phase,source=source):
                    r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                        context_vec=a.context_vec if phase=='fresh' else None,decisions=a.decisions)
                    self.assertEqual(r['corrected'],expected);self.assertEqual(r.get('odd_spans'),[])
if __name__=='__main__':unittest.main()
