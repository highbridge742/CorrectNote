import unittest
import corrector as C
from literal_examples import protected_ranges, subtract_ranges

class LiteralExampleTests(unittest.TestCase):
    def test_explicit_error_examples_only(self):
        for line in ('「あいう」という誤入力', '誤入力例：「あいう」', '入力ミスの例『あいう』', '“あいう”といった誤字を直す'):
            with self.subTest(line=line):
                ranges=protected_ranges(line)
                self.assertEqual([line[a:b] for a,b in ranges],['あいう'])
        for line in ('「あいう」', '（あいう）という誤字', '「あいう」という言葉', '「あいう」という誤入力装置', '誤入力例ではない「あいう」', '「あいう', '「あいう』という誤字'):
            with self.subTest(line=line):self.assertEqual(protected_ranges(line),[])

    def test_quoted_keystrokes_are_text_being_reported(self):
        for tail in ('と入力しました。','と入力したら','とタイプします。','と打った。','と打っても','と打鍵する。','とキー入力した。'):
            line='「あいう」'+tail
            with self.subTest(tail=tail):
                self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['あいう'])
        for tail in ('と書きました。','と入力仕様を比較した。','とタイプライター','という言葉'):
            self.assertEqual(protected_ranges('「あいう」'+tail),[])

    def test_partial_repair_keeps_a_reading_with_multiple_written_forms(self):
        line='きせいせん（規制線、紀勢線、棋聖戦）'
        tk=lambda s:[(s,'名詞','きせいせんきせいせんきせいせん',0,len(s),True,'')]
        self.assertTrue(C._reading_spelled_in_bracket(line,0,3,tk))
        self.assertTrue(C._reading_spelled_in_bracket(line,3,5,tk))
        self.assertFalse(C._reading_spelled_in_bracket('あいう（注釈）',0,3,tk))
        self.assertFalse(C._reading_spelled_in_bracket('あいう（注釈',0,3,tk))

    def test_label_boundary_uses_actual_text_not_truncated_slice(self):
        for count in range(80):
            prefix='「あいう」'+' '*count
            self.assertEqual(protected_ranges(prefix+'という誤入力装置'),[])
            self.assertEqual(protected_ranges(prefix+'という誤入力'),[(1,4)])

    def test_nested_and_multiple_quotes(self):
        line='「あ『い』う」という誤字と「😀え」という誤入力'
        self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['あ『い』う','😀え'])

    def test_escaped_ascii_quote(self):
        line='"a\\"b"という誤入力'
        self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['a\\"b'])

    def test_evidence_is_split_with_reason(self):
        self.assertEqual(subtract_ranges([(0,10,'reason')],[(2,4),(6,8)]),[(0,2,'reason'),(4,6,'reason'),(8,10,'reason')])

    def test_engine_receives_no_literal_characters(self):
        source='前「😀誤字」という誤入力、後'
        seen=[]
        def engine(line):
            seen.append(line)
            return dict(original=line,corrected=line,changed=False,odd_spans=[(0,len(line))],odd_reasons=[(0,len(line),'rule')],unsure_spans=[])
        result=C._with_literal_examples(engine)(source)
        self.assertNotIn('😀誤字',seen[0])
        self.assertEqual(len(seen[0]),len(source))
        self.assertEqual(result['corrected'],source)
        self.assertEqual(result['odd_spans'],[(0,2),(5,len(source))])

    def test_outside_edits_and_offsets_survive(self):
        source='甲「😀誤字」という誤入力、乙'
        def engine(line):
            return dict(original=line,corrected=line.replace('甲','甲甲').replace('乙','丙'),changed=True,original_spans=[],details=[],odd_spans=[],odd_reasons=[],unsure_spans=[])
        result=C._with_literal_examples(engine)(source)
        self.assertEqual(result['corrected'],'甲甲「😀誤字」という誤入力、丙')
        for (a,b),(old,new,_) in zip(result['original_spans'],result['details']):self.assertEqual(source[a:b],old)
        for (a,b),(_,new,_) in zip(result['spans'],result['details']):self.assertEqual(result['corrected'][a:b],new)

    def test_normalizer_cannot_remove_literal(self):
        source='「あいう」という誤入力'
        def engine(line):return dict(corrected=line.replace(' ',''),odd_spans=[],odd_reasons=[],unsure_spans=[])
        self.assertEqual(C._with_literal_examples(engine)(source)['corrected'],source)

    def test_unlabelled_quote_goes_through_unchanged(self):
        seen=[]
        def engine(line):seen.append(line);return {'corrected':line+'!'}
        self.assertEqual(C._with_literal_examples(engine)('「あいう」')['corrected'],'「あいう」!')
        self.assertEqual(seen,['「あいう」'])

if __name__=='__main__':unittest.main()
