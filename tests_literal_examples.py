import unittest
import corrector as C
from literal_examples import protected_ranges, subtract_ranges

class LiteralExampleTests(unittest.TestCase):
    def test_explicit_input_output_spelling_examples_are_literal_data(self):
        for line in ('「あいう」は入力例です。','「あいう」が出力の例でした。',
                     '「あいう」も表記例ではありません。','入力例：「あいう」',
                     '出力の例として「あいう」を示します。','「あいう」という入力例を説明します。',
                     'あいうという表記の例です。'):
            with self.subTest(line=line):
                self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['あいう'])

    def test_example_action_longer_noun_and_unclosed_quote_remain_outside_label(self):
        for line in ('「あいう」は入力例を作ります。','「あいう」は入力例題です。',
                     '「あいう」という出力例外','入力例を調べます。「あいう」を確認します。',
                     '入力例ではない「あいう」','「あいうは入力例です。'):
            with self.subTest(line=line):self.assertEqual(protected_ranges(line),[])
        line='「あいう」は入力例です。「えお」を確認します。'
        self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['あいう'])

    def test_explicit_error_examples_only(self):
        for line in ('「あいう」という誤入力', '誤入力例：「あいう」', '入力ミスの例『あいう』', '“あいう”といった誤字を直す'):
            with self.subTest(line=line):
                ranges=protected_ranges(line)
                self.assertEqual([line[a:b] for a,b in ranges],['あいう'])
        for line in ('「あいう」', '（あいう）という誤字', '「あいう」という言葉', '「あいう」という誤入力装置', '誤入力例ではない「あいう」', '「あいう', '「あいう』という誤字'):
            with self.subTest(line=line):self.assertEqual(protected_ranges(line),[])

    def test_unquoted_error_example_has_a_sentence_boundary(self):
        line='保存が官僚しました。糸を汲むという誤変換の例です。'
        self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['糸を汲む'])
        for text in ('「糸を汲むという誤変換の例です。','（糸を汲む）という誤変換',
                     '糸を汲むという誤変換装置'):
            with self.subTest(text=text):self.assertEqual(protected_ranges(text),[])

    def test_explicit_example_case_marker_stays_literal(self):
        for prefix in ('誤変換の例として','タイプミスの例としては','誤字の例としての'):
            line=prefix+'「保存が官僚した」を示します。'
            with self.subTest(prefix=prefix):
                self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['保存が官僚した'])
        self.assertEqual(protected_ranges('事例として「保存が官僚した」を話しました。'),[])

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

    def test_insertions_at_boundaries_do_not_insert_inside_the_protected_text(self):
        from literal_examples import overlaps
        self.assertFalse(overlaps(2,2,[(2,5)]))
        self.assertFalse(overlaps(5,5,[(2,5)]))
        self.assertTrue(overlaps(3,3,[(2,5)]))
        self.assertTrue(overlaps(1,3,[(2,5)]))
        self.assertTrue(overlaps(4,6,[(2,5)]))

    def test_normalizer_cannot_remove_literal(self):
        source='「あいう」という誤入力'
        def engine(line):return dict(corrected=line.replace(' ',''),odd_spans=[],odd_reasons=[],unsure_spans=[])
        self.assertEqual(C._with_literal_examples(engine)(source)['corrected'],source)

    def test_unlabelled_quote_goes_through_unchanged(self):
        seen=[]
        def engine(line):seen.append(line);return {'corrected':line+'!'}
        self.assertEqual(C._with_literal_examples(engine)('「あいう」')['corrected'],'「あいう」!')
        self.assertEqual(seen,['「あいう」'])


    def test_explicit_copular_error_classification_preserves_the_quoted_spelling(self):
        for case in ('は','が','も'):
            for tail in ('誤入力です。','誤字だった。','入力ミスではない。',
                         '誤変換の例でした。','誤記ではありません。'):
                line='「あいう」'+case+tail
                self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['あいう'],line)

    def test_error_action_or_longer_word_is_not_a_copular_example_label(self):
        for tail in ('は誤字を検出します。','が誤入力装置です。',
                     'という誤字装置','は誤字の原因です。'):
            line='「あいう」'+tail
            self.assertEqual(protected_ranges(line),[],line)

    def test_linguistic_assertion_preserves_the_expression_under_discussion(self):
        for tail in ('は成立している。','は、成立しているが説明が必要です。',
                     'は日本語として成立していない。','が自然です。',
                     'は不自然だった。','は正しいですか。','はおかしいでしょう。'):
            line='「見本の誤字」'+tail
            self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['見本の誤字'],line)
        for tail in ('は自然に消えます。','は正しく表示します。','は自然数です。',
                     'は成立条件を満たします。','と書きました。'):
            self.assertEqual(protected_ranges('「見本の誤字」'+tail),[],tail)

    def test_expression_judgment_does_not_freeze_another_occurrence(self):
        line='「見本の誤字」は自然だが、見本の誤字を確認します。'
        self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['見本の誤字'])
        self.assertEqual(protected_ranges('「見本の誤字は自然だ。'),[])


    def test_literal_error_label_and_demonstration_preserve_exact_occurrence(self):
        for before,after in (
            ('誤変換の例は','です。'),
            ('誤りを示すために','と記しました。'),
            ('修正前の表記は','です。'),
        ):
            line=before+'「見本の誤字」'+after+'見本の誤字を直します。'
            self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['見本の誤字'],line)
        for line in ('誤字を直して「見本の誤字」と書きました。',
                     '誤変換の例を直して「見本の誤字」と書きます。',
                     '誤りを説明したあとで「見本の誤字」と話しました。'):
            self.assertEqual(protected_ranges(line),[],line)

    def test_explicit_wrong_right_comparison_preserves_both_spellings(self):
        line='×「見本の誤字」→○「見本の正字」と比較します。'
        self.assertEqual([line[a:b] for a,b in protected_ranges(line)],['見本の誤字','見本の正字'])
        for line in ('「見本の誤字」→「見本の正字」へ移動します。',
                     '×「見本の誤字」を選んで「見本の正字」を描きます。',
                     '×「見本の誤字」→○「見本の正字'):
            self.assertEqual(protected_ranges(line),[],line)


if __name__=='__main__':unittest.main()

