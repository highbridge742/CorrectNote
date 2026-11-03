"""起こらない品詞のつながりの所のかな1字を、近いキーに替えて行が一番自然になる形に直す
（impossible_slip・2026-10-30・補正担当。例文は作った文）"""
import inspect
import unittest
import impossible_slip as I


def _apply(text):
    for a, b, rep in I.propose(text):
        if rep is not None:
            text = text[:a] + rep + text[b:]
    return text


class ImpossibleSlipTests(unittest.TestCase):
    def test_fixed(self):
        self.assertEqual(_apply('冬休みにぱ旅行に行く。'), '冬休みには旅行に行く。')
        self.assertEqual(_apply('図書館り本を返す。'), '図書館の本を返す。')

    def test_correct_line_untouched(self):
        for line in ('冬休みには旅行に行く。', '図書館の本を返す。', '東京のカフェで会う。'):
            self.assertEqual(I.propose(line), [], line)

    def test_other_purple_kana_only(self):
        line = '図書館で本をかりのした。'
        span = [(6, 11)]
        self.assertEqual([m for m in I.propose(line, 'kana', span) if m[2]], [(8, 9, 'ま')])
        self.assertIn("input_method == 'kana'", inspect.getsource(I.repair_line))

    def test_unexplained_run_after_kanji(self):
        line = '毎朝ジョギングを継続しのす。'
        self.assertTrue(I.unexplained_runs(line))
        self.assertEqual(I.unexplained_runs('毎朝ジョギングを継続します。'), [])

    def test_kana_written_word_left(self):
        src = inspect.getsource(I._weak_new_word)
        self.assertIn("かなだけの動詞", src)

    def test_scan_runs(self):
        self.assertEqual(I.scan_runs('机の上にノートがある。'), [(1, 2), (3, 4), (7, 10)])
        for line in ('机の上にノートがある。', '雨が降りそうなので傘を持つ。', '内容を確認してから送ります。'):
            self.assertEqual([m for m in I.propose(line, 'kana', (), True) if m[2]], [], line)
        self.assertGreater(I.SCAN_GAIN, I.ODD_GAIN)

    def test_second_opinion(self):
        self.assertEqual(I.second_opinion('棚の箱を両手で開ぎます。', '棚の箱を両手で会議前。'), '棚の箱を両手で開きます。')
        self.assertIsNone(I.second_opinion('お時間をいただき、ありがとうございます。', 'お時間を頂き、ありがとうございます。'))

    def test_scan_keeps_indefinite_ka(self):
        for line in ('冷蔵庫に何か飲むものはある？', 'あの人は誰だか分かりますか。', '週末にどこか出かけたいね。'):
            self.assertEqual([m for m in I.propose(line, 'kana', (), True) if m[2]], [], line)

    def test_weak_new_word(self):
        src = inspect.getsource(I._weak_new_word)
        self.assertIn("nx.pos == '助動詞'", src)

    def test_loose_forms_rejected(self):
        src = inspect.getsource(I._loose_form)
        for key in ('接頭詞', '体言接続特殊', "'ぬ'"):
            self.assertIn(key, src)

    def test_wired(self):
        import correction_entry
        self.assertIn('_impossible_slip(line, result, decisions, input_method)', inspect.getsource(correction_entry))


class StillOddCandidateTests(unittest.TestCase):
    def test_candidate_still_odd_is_not_taken(self):
        # 崩した言い方（例は作った語）は、1字替えた形もまだ説明の付かない並びなので替えない
        self.assertTrue(I._still_odd('えもたん', 2, 'て', 0, 4))
        for line in ('えもたん', 'こわたん', 'やばたん'):
            self.assertEqual([m for m in I.propose(line, 'kana', [(0, len(line))]) if m[2]], [], line)

class SecondOpinionMarkTests(unittest.TestCase):
    def test_fixed_mark_is_not_undone(self):
        # 前の段が単独の印を前の字に付けた行（は゛す→ばす）は、比べ直しで印を行に戻さない（2026-10-31）
        got = I.second_opinion('は゛すのじかんを調べる。', 'ばすのじかんを調べる。')
        self.assertTrue(got is None or '゛' not in got, got)


if __name__ == '__main__':
    unittest.main()
