# -*- coding: utf-8 -*-
"""Independent fields retain their own correction and source coordinates."""
import unittest
import morphology as M

@unittest.skipUnless(M.HAS_JANOME,'requires native Janome dictionary')
class SeparatedFieldRepairTests(unittest.TestCase):
    def initial_stages(self):
        from tests_analysis_async import initial
        from janome_import import import_from_janome
        from last_choice import set_active
        try:
            for phase in ('seed','fresh'):
                a=initial();a.context_vec=None
                if phase=='fresh':import_from_janome(a.store)
                yield phase,a
        finally:set_active(None)

    def run_line(self,a,text):
        import app
        revision=a.store.revision()
        result=app.correct_line(text,a.store,dict_index=a.dict_index,
            decisions=a.decisions,context_vec=None,input_method='kana')
        self.assertEqual(a.store.revision(),revision)
        return result

    def test_closed_fields_repair_only_their_own_readings(self):
        # These expectations test grammar/key repair. General spelling of
        # already-correct kana is the separate, not-yet-promoted work.
        pairs=(('差し込み゛手、','差し込みで、'),('さしこみ゛て、','差し込みで、'),
               ('モーシろょん','モーション'),('もーしろょん','モーション'),
               ('他の行とえ同じ','他の行と同じ'),
               ('ほかのぎょうとえおなじ','他の行と同じ'),
               ('入力茶う\t','入力中\t'),
               ('資料を゜保存します。','資料を保存します。'),
               ('手順を゛説明します。','手順を説明します。'))
        for phase,a in self.initial_stages():
            for source,expected in pairs:
                with self.subTest(phase=phase,source=source):
                    r=self.run_line(a,source)
                    self.assertEqual(r['corrected'],expected)
                    self.assertEqual(r.get('odd_spans'),[])
                    originals=r.get('original_spans') or [];spans=r.get('spans') or []
                    self.assertEqual(len(originals),len(spans));edge=0;pieces=[]
                    for (lo,hi),(start,end) in zip(originals,spans):
                        self.assertGreaterEqual(lo,edge)
                        pieces.extend((source[edge:lo],r['corrected'][start:end]));edge=hi
                    pieces.append(source[edge:])
                    self.assertEqual(''.join(pieces),expected)

    def test_normal_incomplete_and_quoted_sources_keep_their_boundaries(self):
        texts=('このようなも。','雪のようなは。','このようなも\t','雪のようなは\t',
               'したあと','きりがないようなも','きりがないようなものです。',
               'きりがないようにも','その行と同じ','ほかのぎょうとおなじ',
               '差し込みで、','さしこみで、','もーしょん',
               '「さしこみ゛て」と入力します。','もんじにゅうりょく')
        for phase,a in self.initial_stages():
            for source in texts:
                with self.subTest(phase=phase,source=source):
                    self.assertEqual(self.run_line(a,source)['corrected'],source)

    def test_other_columns_do_not_supply_the_answer(self):
        for phase,a in self.initial_stages():
            for source in ('さしこみ゛て、','もーしろょん','ほかのぎょうとえおなじ','きりがないようなも'):
                expected=self.run_line(a,source+'\t')['corrected'].split('\t')[0]
                for annotation in ('優先して補正','全く関係のない文章','999999'):
                    with self.subTest(phase=phase,source=source,annotation=annotation):
                        r=self.run_line(a,source+'\t'+annotation)
                        self.assertEqual(r['corrected'].split('\t')[0],expected)

if __name__=='__main__':unittest.main()