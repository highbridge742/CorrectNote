# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
**窓の組み直し**（`rebuild_window_core`）の試験。

`tests_mock.py` から分けたもの（2026-08-20・項目48-GQ）。
**走らせる入口は `tests_mock.py` のまま。**
"""
import corrector as C
from vocabulary import VocabularyStore, find_known_readings_flex
from seed_vocabulary import load_seed

from tests_mock_common import mock_tokenize


def run_rebuild_cases():
    """
    芯の再構築（rebuild_window_core / find_similar_readings）。

    「ひらがなに直し、隣接キーや脱字などを考慮して再構築する」
    という方針の中核。従来の探索は隣接キーの押し間違いしか
    扱えなかったので、配列上で遠い取り違えを別経路で拾う。

    やりすぎを許す方針に変わったぶん、**壊してはいけないものを
    壊さない**ことの確認を厚くする。
    """
    import corrector as _C
    from vocabulary import (weighted_edit_distance, find_similar_readings,
                            VocabularyStore)
    from seed_vocabulary import load_seed

    print('--- 芯の再構築（配列上で遠い取り違え・連打・脱字） ---')
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    st = VocabularyStore()
    load_seed(st)

    # --- 距離の数え方 ---
    check('同じ並びは距離0・訂正0',
          weighted_edit_distance('たんご', 'たんご'), (0.0, 0))
    cost_near, edits_near = weighted_edit_distance('たんこ', 'たんご')
    check('濁点の付け忘れは1箇所', edits_near, 1)
    cost_far, edits_far = weighted_edit_distance('たんほ', 'たんご')
    check('配列上で遠い取り違えも1箇所として数える', edits_far, 1)
    check('遠い取り違えのほうが高くつく', cost_far > cost_near, True)
    cost_rep, edits_rep = weighted_edit_distance('たああんご', 'たんご')
    cost_ins, _e = weighted_edit_distance('たかさんご', 'たんご')
    check('同じキーの連打は、別々の余計な打鍵より安い',
          cost_rep < cost_ins, True)
    check('連打は取り除いた文字数ぶんの訂正', edits_rep, 2)

    # --- 語彙からの引き当て ---
    def first(word):
        got = find_similar_readings(word, st)
        return got[0][0] if got else None

    check('たんほ → たんご', first('たんほ'), 'たんご')
    check('たああんご → たんご', first('たああんご'), 'たんご')
    check('つあがり → つながり', first('つあがり'), 'つながり')
    check('ちながり → つながり', first('ちながり'), 'つながり')
    check('自分自身は候補に含めない',
          'たんご' in [r for r, _c, _e in find_similar_readings('たんご', st)],
          False)
    check('長さが違いすぎる相手は見ない',
          [r for r, _c, _e in find_similar_readings('たんご', st,
                                                    max_len_diff=0,
                                                    max_cost=99)
           if len(r) != 3], [])
    check('空文字を渡しても落ちない', find_similar_readings('', st), [])

    # --- 芯の切り出し ---
    def cores(w):
        return [w[a:b] for a, b in _C.window_cores(w, st)]

    check('先頭の助詞を剥がす', cores('のつあがり')[0], 'つあがり')
    check('末尾の助詞を剥がす', cores('たんほの')[0], 'たんほ')
    check('語の先頭のかなは剥がさない（送り仮名と区別できないため）',
          cores('たああんごの')[0], 'たああんご')
    check('既知語＋助詞 の残りを切り離す',
          'ちながり' in cores('たんごのちながり'), True)
    check('機能語だけの並びは芯にしない', cores('っている'), [])

    # --- 再構築の判断（壊してはいけないもの） ---
    fn = _C.make_tokenizer(st)

    def rebuild(w):
        return _C.rebuild_window_core(w, st, fn)

    check('たんほ は直す', rebuild('たんほ')[2], 'たんご')
    check('切り詰め（芯の一部でしかない語）には直さない',
          rebuild('よろしくお'), None)
    check('直前が漢字なら先頭の送り仮名を剥がす',
          [w for w in ['きのままでよい']
           for a, b in _C.window_cores(w, st, after_kanji=True)][:1] or ['(無し)'],
          ['(無し)'])
    check('直前が漢字でなければ語頭のかなは剥がさない',
          'たああんご' in ['たああんごの'[a:b] for a, b
                        in _C.window_cores('たああんごの', st)], True)
    check('機能語だけの窓は芯を作らない',
          _C.window_cores('ではなく', st, after_kanji=True), [])
    check('のつあがり は芯だけ直す', rebuild('のつあがり'),
          (1, 5, 'つながり'))
    check('機能語だけの並びは直さない', rebuild('かったのかな'), None)
    check('既に語彙にある読みは直さない', rebuild('たんご'), None)
    check('2文字以下の芯は直さない', rebuild('たん'), None)
    check('決め手が無ければ直さない', rebuild('あいうえおかき'), None)

    # --- 語彙が育っても働くか（実機で丸ごと死んでいた経路） ---
    # 実機（7379語）では「たんほの」の先頭「たん」が語彙にあるという
    # だけで窓ごと捨てられ、この経路が一度も働いていなかった。
    # 短い語が語彙に入っていても直せることを固定する。
    st2 = VocabularyStore()
    load_seed(st2)
    for _ in range(694):
        st2.add('たんご', '単語')
    for _ in range(676):
        st2.add('つながり', '繋がり')
    for _r, _s in (('たんに', '単に'), ('たん', '痰'), ('あがり', '上がり'),
                   ('たんし', '担子')):
        for _ in range(4):
            st2.add(_r, _s)
    fn2 = _C.make_tokenizer(st2)

    def _fix(text):
        from vocabulary import find_known_readings_flex as _f
        return _C.correct_line(text, st2, fn2, _f)['corrected']

    def _fix_im(text, im):
        """入力方式を指定して直す（項目48-FX の門は方式で変わる）。"""
        from vocabulary import find_known_readings_flex as _f
        return _C.correct_line(text, st2, fn2, _f,
                               input_method=im)['corrected']

    # 語頭のかなを剥がしてはいけない（置換範囲がずれる）。
    # 実機（janome あり）で explain_cores が「たああんごの」の
    # 先頭「た」を活用語尾として剥がし、窓が「ああんご」になった。
    # そこを「たんご」に直すと「た」が取り残されて
    # **たたんごの繋がり** という壊れ方をした。
    check('直前が漢字でなければ窓の先頭は剥がさない',
          [w for _a, _b in _C.explain_cores('たああんごの', st2,
                                            after_kanji=False)
           for w in ['たああんごの'[_a:_b]]], ['たああんご'])
    check('直前が漢字なら窓の先頭を剥がす',
          [w for _a, _b in _C.explain_cores('のつあがり', st2,
                                            after_kanji=True)
           for w in ['のつあがり'[_a:_b]]], ['つあがり'])

    # **ここは項目48-FX（2026-08-19）で向きが変わった。**
    # うにさんの指定:
    #   「かな入力において、濁音、半濁音は2打鍵であることを
    #     考慮します。… 1文字違うだけでは補正しません、
    #     その違いが隣接キーかどうか。
    #     隣接判定はかな入力とローマ字入力で変わる。」
    # `ご` は `こ(B)＋゛(@)` の2打鍵で、`ほ(-)` とは遠い。
    # **かな入力では触らない**のが正しい。
    # ローマ字入力なら `ho → go` は隣なので、今までどおり直る
    # （`run_kana_cases` の romaji の組で確かめている）。
    check('たんほ→たんご は、かな入力では直さない（項目48-FX）',
          _fix('たんほの繋がり'), 'たんほの繋がり')
    # `あ(3のキー)` と `な(U)` も遠い。**ローマ字で見れば
    # `tuagari` → `tunagari` の脱字**なので、ローマ字入力では直る。
    # うにさんの確認（2026-08-19・項目48-FY）:
    #   「つあがり、これはローマ字限定補正です。
    #     かな入力では対象外です。」
    check('つあがり→つながり は、かな入力では直さない（項目48-FY）',
          _fix('単語のつあがり'), '単語のつあがり')
    check('遠い置き換えは、実績が圧倒的でも通さない（項目48-FX）',
          _fix('たんほの繋がり'), 'たんほの繋がり')
    check('語頭を取り残さない（たたんご にならない）',
          _fix('たああんごの繋がり'), 'たんごの繋がり')
    check('ちながり→つながり（既知語＋助詞 の残りを芯にする）',
          _fix('たんごのちながり'), 'たんごのつながり')

    # 送り仮名の剥がしと、末尾を落とさない芯。
    # 「かな打ちでのほらい」の窓は「ちでのほら」になる
    # （先頭に送り仮名「ち」が残り、末尾の「い」が語尾として落ちる）。
    # 「い」は「補正（ほせい）」の一部なので、落としたままだと
    # 芯が「ほら」になって直す先に届かない。
    for _ in range(693):
        st2.add('ほせい', '補正')
    for _ in range(648):
        st2.add('かな', 'かな')
    # 項目48-DY で「剥がさない形」（ちでのほらい 等）も候補に並ぶ
    # ようになった（世の中に在る語かどうかの裁きは
    # rebuild_window_core 側）。ここでは**剥がした芯 `ほらい` が
    # ちゃんと出ていること**を確かめる。
    _dy_cores = ['ちでのほらい'[a:b] for a, b
                 in _C.window_cores('ちでのほらい', st2,
                                    after_kanji=True)]
    check('連用形の送り仮名を剥がして芯を取り出す',
          'ほらい' in _dy_cores, True)
    check('ほらい→ほせい（末尾の「い」を語尾として落とさない）',
          _fix('かな打ちでのほらい'), 'かな打ちでのほせい')
    check('正しく書けた同じ形は触らない',
          _fix('かな打ちでの補正'), 'かな打ちでの補正')

    # --- 壊してはいけないもの（janome が無い環境でも） ---
    # 壊してはいけない文。かな連続そのものを窓にする最後の手当てを
    # 入れたぶん、正しい文が素通りすることの確認を厚くする。
    for _t in ('色付きのままでよい', '間違いが1～2か所ではなく',
               'よろしくおねがいします', 'したほうがよい',
               '言えば良かったのかな', '知っている人向けの文法で作られている',
               '単語のつながりのほうが文脈が合う',
               '漢字を平仮名にひらいたり、ひらがなを漢字にしたり、',
               '一回り小さくします', 'チェックがうまく動いてない',
               '判断をします。', '1歳7か月のお子さん', '理論寄りだった',
               '10時過ぎに', '予約済み', '以下',
               '持っていくものも服もネイルも髪も推し仕様にした'):
        check(f'壊さない: {_t}', _fix(_t), _t)

    # --- 実機で出た誤爆の再発防止（2026-08-08・2回目のセッション） ---
    # 修正が効いた直後の実機で、正しい文が4種類の経路で壊れた。
    # それぞれ別の関門で止まることを固定する。
    for _r, _s in (('にゅうりょく', '入力'), ('みえる', '見える'),
                   ('しゅるい', '種類')):
        for _ in range(5):
            st2.add(_r, _s)
    # 1. 送り仮名＋機能語の窓（見えません → 見えびせん）
    for _ in range(5):
        st2.add('えびせん', 'えびせん')
    check('送り仮名＋機能語の窓は芯を作らない（えません）',
          _C.window_cores('えません', st2, after_kanji=True), [])
    check('送り仮名＋機能語の窓は芯を作らない（えてました）',
          _C.window_cores('えてました', st2, after_kanji=True), [])
    check('壊さない: 即座に見えません。',
          _fix('即座に見えません。'), '即座に見えません。'),
    # 送り仮名で始まっても、残りが機能語で説明できなければ対象のまま
    check('送り仮名の後に内容語が続く窓は対象のまま',
          _C.window_cores('ちでのほらい', st2, after_kanji=True) != [],
          True)
    # 2. 小書きかなで始まる窓（にゅうりょく → ににゅうりょく／に入力）
    check('壊さない: にゅうりょく（語彙にある読みは触らない）',
          _fix('にゅうりょく'), 'にゅうりょく')
    check('壊さない: 文字にゅうりょく',
          _fix('文字にゅうりょく'), '文字にゅうりょく')
    # 3. 漢字塊＋送り仮名で実在語（取り違え → 種類え）。
    # このガードは「送り仮名込みなら janome が1語で読める」ことに
    # 依存するので、実 janome を模した mock_tokenize で確かめる
    # （フォールバック分割は 取/り/違/え と割ってしまい、
    #   実機の姿を再現できない）。
    def _fix_mock(text):
        from vocabulary import find_known_readings_flex as _f
        return _C.correct_line(text, st2, mock_tokenize, _f)['corrected']

    check('壊さない: F1機能と取り違えてました。',
          _fix_mock('F1機能と取り違えてました。'),
          'F1機能と取り違えてました。')

    # 4. 大文字で始まる英単語の半角誤爆（Shift+= → 特にはかれほ）
    from halfwidth import looks_like_halfwidth_input as _lh
    check('Shift+= は半角入力の誤りとみなさない', _lh('Shift+='), False)
    check('Ctrl+F は半角入力の誤りとみなさない', _lh('Ctrl+F'), False)
    check('Python は半角入力の誤りとみなさない', _lh('Python'), False)
    check('md@i(4l)h は引き続き対象（小文字始まり）',
          _lh('md@i(4l)h'), True)
    check('壊さない: 全角入力時の、Shift+=が効かず、',
          _fix('全角入力時の、Shift+=が効かず、'),
          '全角入力時の、Shift+=が効かず、')

    # --- 技術メモの貼り付けで出た誤爆の再発防止（2026-08-08・3回目） ---
    # 長い技術メモを貼ると、コードの識別子・英単語・活用の連なりが
    # 大量に壊れた（実機のスクリーンショットで確認）。
    print('--- 技術メモ貼り付けで出た誤爆の再発防止 ---')

    # 4-a. コード・英語の断片は半角経路で変換しない
    check('記号を挟まない先頭大文字語（(Shift）も英語とみなす',
          _lh('(Shift'), False)
    check('バッククォート付きは変換しない', _lh('`RegisterHotKey`'), False)
    check('snake_case は変換しない',
          _lh('_looks_like_valid_japanese'), False)
    check('メソッド参照は変換しない',
          _lh('kana_layout.nearby_candidates()'), False)
    check('小文字英字だけの語（ctypes）は変換しない', _lh('ctypes'), False)
    check('壊さない: 直接ctypes経由で使う方式を採用',
          _fix('直接ctypes経由で使う方式を採用'),
          '直接ctypes経由で使う方式を採用')

    # 4-b. 機能語の連なり・送り仮名＋機能語は、独立した連続でも触らない
    check('壊さない: やっていた（や＋っ＋ていた）',
          _fix('やっていた'), 'やっていた')
    check('壊さない: になっていた。',
          _fix('になっていた。'), 'になっていた。'),
    check('壊さない: 「えません」（引用で切り離された送り仮名＋機能語）',
          _fix('「えません」'), '「えません」')

    # 4-c. カタカナ語の分断（ー・ッ で塊が切れて断片が壊れる）
    from kanji_guess import find_kanji_runs as _runs
    check('ローマ字入力 は1つの塊（ー で分断しない）',
          [r[2] for r in _runs('ローマ字入力')], ['ローマ字入力'])
    check('ドラッグ変換 は1つの塊（ッ で分断しない）',
          [r[2] for r in _runs('ドラッグ変換')], ['ドラッグ変換'])
    check('キャッシュ化 は1つの塊',
          [r[2] for r in _runs('キャッシュ化')], ['キャッシュ化'])

    # 4-d. 活用語の頭（漢字＋かな＋漢字）は、確実な部分一致があれば
    #      踏み込まない（取り違→種類、切り出→説明 の再発防止）。
    #      janome 辞書の逆引き（実機の dict_index）を小さな偽物で模す。
    from kanji_guess import strangeness as _strg

    class _StubIndex:
        _d = {'取り': ['とり'], '切り': ['きり'], '引き': ['ひき']}
        def readings_for_surface(self, s):
            return self._d.get(s, [])
        def surfaces_for_reading(self, r):
            return []

    stub = _StubIndex()
    check('取り違 は踏み込まない（異様さ0）',
          _strg('取り違', st2, stub), 0)
    check('切り出 は踏み込まない（異様さ0）',
          _strg('切り出', st2, stub), 0)
    check('見切れ魔訶 は引き続き異様（稀な漢字）',
          _strg('見切れ魔訶', st2, stub) >= 2, True)

    # 4-e. 連打の重複削除は「切り詰め」ではない
    check('たたんご→たんご は連打の訂正',
          _C._is_repeat_collapse('たたんご', 'たんご'), True)
    check('よろしくお→よろしく は切り詰め',
          _C._is_repeat_collapse('よろしくお', 'よろしく'), False)
    check('たたんごの繋がり → たんごの繋がり',
          _fix('たたんごの繋がり'), 'たんごの繋がり')

    # --- 2回目の実機確認で出た誤爆の再発防止（2026-08-08・4回目） ---
    print('--- 2回目の実機確認で出た誤爆の再発防止 ---')
    # 誤爆の再現には、実機の語彙が偶然持っていた紛らわしい語が要る
    for _r, _s, _n in (('つかれた', '疲れた', 5), ('いっきに', '一気に', 5),
                       ('すとあ', 'ストア', 6), ('つよかっ', 'つよかっ', 20),
                       ('よかった', 'よかった', 30), ('あの', 'あの', 5)):
        for _ in range(_n):
            st2.add(_r, _s)

    # 5-a. 直前が漢字の窓は、先頭の送り仮名をどのかなでも許して守る
    check('壊さない: 気づかれず（気づく の送り仮名 づ）',
          _fix('気づかれず「ログ」という誤解'),
          '気づかれず「ログ」という誤解')
    check('壊さない: タブ機能を足すときに',
          _fix('タブ機能を足すときに'), 'タブ機能を足すときに')
    check('壊さない: 丸ごと死んでいた',
          _fix('丸ごと死んでいた'), '丸ごと死んでいた')
    check('壊さない: いちばん起こりやすい',
          _fix('いちばん起こりやすい'), 'いちばん起こりやすい')

    # 5-b. 窓を右に延ばすと機能語で説明が付くなら切り出し不良
    check('壊さない: 押すとそのホットキー',
          _fix('押すとそのホットキー'), '押すとそのホットキー')

    # 5-c. 促音・小書きで終わる読み（活用の断片）を当てない
    check('壊さない: つよかった（断片 つよかっ に化けない）',
          _fix('つよかった'), 'つよかった')

    # 5-d. 窓の直前の文字を足しただけの候補（境界の重複）を当てない
    check('壊さない: 通常のひらがな探索（ひひらがな にしない）',
          _fix('通常のひらがな探索の対象にならず、'),
          '通常のひらがな探索の対象にならず、')

    # 5-e. 末尾が助詞の範囲を、助詞ごと別の語に置き換えない
    check('壊さない: 「ひらがなを」（を が消えない）',
          _fix('（実機で「ひらがなを」→'), '（実機で「ひらがなを」→')

    # 5-f. 文字列リテラルを半角経路で変換しない
    check("'corrected', は変換しない", _lh("'corrected',"), False)

    # 5-g. 引用された「たんほの」——**項目48-FX で向きが変わった**。
    #      かな入力では `ほ → ご` が遠いので触らない。
    #      （それまでは窓経路の拮抗判定で たんご に届いていた）
    check('引用された「たんほの」は、かな入力では触らない（項目48-FX）',
          _fix('「たんほの」の先頭'), '「たんほの」の先頭')

    # 5-h. 塊＋送り仮名の実在チェック（起き続＝起き＋続けていた）
    class _StubIndex2(_StubIndex):
        _d = dict(_StubIndex._d, **{'起き': ['おき'], '続け': ['つづけ']})
    check('起き続 は踏み込まない（異様さ0。起き が辞書にある）',
          _strg('起き続', st2, _StubIndex2()), 0)

    # 5-i2. 芯の後ろに活用語尾が残る場合、芯の終わりの文字を保つ
    # （「あらゆる」の芯「あらゆ」＋語尾「る」。「あらい」を当てると
    #   あらいる になる。実機で発生）
    for _ in range(67):
        st2.add('あらい', '粗い')
    check('壊さない: 文中のあらゆる場所に',
          _fix('文中のあらゆる場所に'), '文中のあらゆる場所に')
    check('壊さない: あらゆる（独立でも）', _fix('あらゆる'), 'あらゆる')

    # --- 方針1-B: 半角英字・記号の混入（2026-08-08 実装） ---
    print('--- 方針1-B: 半角英字・記号の混入 ---')
    from kanji_guess import find_ascii_mixed_runs, kana_for_ascii

    check('b はかなキー「こ」に対応', kana_for_ascii('b'), ['こ'])
    check('全角ｂも同じ', kana_for_ascii('ｂ'), ['こ'])
    check('= は Shift 側の「ほ」', 'ほ' in kana_for_ascii('='), True)
    check('かなに対応しない文字は空', kana_for_ascii('`'), [])

    check('塊: たｂご',
          [r[2] for r in find_ascii_mixed_runs('たｂごの繋がり')],
          ['たｂご'])
    check('塊: 他b後',
          [r[2] for r in find_ascii_mixed_runs('他b後の繋がり')],
          ['他b後'])
    check('塊: 単=（混入が塊の末尾でもよい）',
          [r[2] for r in find_ascii_mixed_runs('単=の繋がり')],
          ['単='])
    check('塊: たんb後',
          [r[2] for r in find_ascii_mixed_runs('たんb後の繋がり')],
          ['たんb後'])
    check('先頭に来る英字は対象外（AとB案のB）',
          find_ascii_mixed_runs('AとB案'), [])
    check('英字2文字は対象外（意図した英語）',
          find_ascii_mixed_runs('たabごの繋がり'), [])
    check('隣が英数字なら対象外（Python3で）',
          find_ascii_mixed_runs('Python3で動く'), [])

    check('たｂごの繋がり → 単語の繋がり',
          _fix('たｂごの繋がり'), '単語の繋がり')
    check('他b後の繋がり → 単語の繋がり',
          _fix('他b後の繋がり'), '単語の繋がり')
    check('タj後の繋がり → 単語の繋がり',
          _fix('タj後の繋がり'), '単語の繋がり')
    check('たんb後の繋がり → 単語の繋がり（余計な打鍵として b を除く）',
          _fix('たんb後の繋がり'), '単語の繋がり')
    # **`=` だけは、かな入力では届かない**（項目48-FZ）。
    # `=` は `-`（＝`ほ`）のキーの Shift 側なので、混入を戻した読みは
    # `たんほ` になる。そこから `たんご` へは **ほ → ご** の
    # 置き換えで、`ご＝こ(B)＋゛(@)` の2打鍵ぶん遠い（項目48-FX）。
    # 上の `b` `j` の組は `こ` に戻るので、濁点を足すだけで届く。
    # **混入の戻しは効いている。遠いのは、その先の1文字。**
    check('単=の繋がり は、かな入力では届かない（項目48-FZ）',
          _fix('単=の繋がり'), '単=の繋がり')

    # 巻き込んではいけないもの（数字・ラベル・英語・句読点）
    for _t in ('第1章', 'その1つ', 'A案とB案', '約2倍になった',
               '図Aは省略', 'B案の検討', '全角1文字と2文字',
               # 全角・半角の句読点記号は意図した表記
               # （実機で「例：単語」が ：→け の読み替えから
               #   「英単語」に化けた）
               '・成立していない単語「例：単語の繋がり」',
               '例:単語です', '要点は3つ、結論：単語です'):
        check(f'壊さない: {_t}', _fix(_t), _t)
    check('数字・記号は混入とみなさない（例：単語）',
          find_ascii_mixed_runs('例：単語の繋がり'), [])

    # --- 同じ英字の2連（実機からの指摘: ローマ字打ちの
    #     「Nを2回押して ん」の習慣も踏まえ、2連は1打または ん） ---
    for _ in range(5):
        st2.add('たん', 'たん')
    # ★★ **「よく使うほう」はもう記録されない**（項目48-QG/QH・
    # 2026-09-05）。ここは元々 `たん`(5回) が `痰`(4回) に回数で
    # 勝つ前提だったが、うにさんの指定で回数の記録を廃したので、
    # 同じ読みに表記が2つあると**入った順**（＝先に登録した `痰`）で
    # 決まる。本人の意思を表すのは**最後に選んだ表記の枠**だけ。
    # そこで、この人は `たん` を選んでいる、という枠を差す。
    import last_choice as _LC
    _lc_tan = _LC.LastChoiceStore()
    _lc_tan.bind(st2, None)
    _lc_tan.remember('たん', 'たん', 'たん')
    _LC.set_active(_lc_tan)
    check('枠: たん の読みは同音（本人の語彙に2表記）',
          _lc_tan.surface_for_reading('たん'), 'たん')
    check('塊: たｂｂご（2連を1つの混入として拾う）',
          [r[2] for r in find_ascii_mixed_runs('たｂｂごの繋がり')],
          ['たｂｂご'])
    check('3連以上は意図した英語とみなす',
          find_ascii_mixed_runs('たｂｂｂごの繋がり'), [])
    check('たｂｂごの繋がり → 単語の繋がり（ｂｂ→ん）',
          _fix('たｂｂごの繋がり'), '単語の繋がり')
    check('たｍｍごの繋がり → 単語の繋がり',
          _fix('たｍｍごの繋がり'), '単語の繋がり')
    check('たｈｈの繋がり → たんの繋がり（ｈｈ→ん・枠が決める）',
          _fix('たｈｈの繋がり'), 'たんの繋がり')
    # **枠を外すと決まらない**（＝黙る。`痰` を勝手に書かない）。
    # 回数を廃したあとの正しい姿——判断がつかないものは触らない。
    _LC.set_active(None)
    check('枠が無ければ たｈｈ は決めない（痰 に化けない）',
          _fix('たｈｈの繋がり'), 'たｈｈの繋がり')
    _LC.set_active(_lc_tan)
    check('壊さない: ふつうにaabbと打つ',
          _fix('ふつうにaabbと打つ'), 'ふつうにaabbと打つ')

    # --- 候補づくり: 配列上で遠い取り違えも候補に出す
    #     （実機からの指摘: 乱後・やん後 等で候補が1つも出ない） ---
    from candidates import build_candidates as _bc
    _c1 = _bc('乱後', 'らんご', st2, find_known_readings_flex)
    check('乱後（らんご）の候補に 単語 が出る',
          any(c['surface'] == '単語' for c in _c1), True)
    _c2 = _bc('かんじょ', 'かんじょ', st2, find_known_readings_flex)
    check('かんじょ の候補に 漢字 が出る',
          any(c['surface'] == '漢字' for c in _c2), True)
    _c3 = _bc('やん後', 'やんご', st2, find_known_readings_flex)
    check('やん後 にも何かしらの候補が出る', len(_c3) > 0, True)

    # --- 既知語＋助詞の芯は触らない（たんごの→たんこう の再発防止） ---
    # 濁点を合成した「たんごの」が窓全体の芯になったとき、
    # ご→こ（濁点差で安い）＋の→う で「たんこう」に化けた（実機）。
    for _ in range(30):
        st2.add('たんこう', '単行')
    check('既知語＋助詞の芯（たんごの）は触らない',
          _C.rebuild_window_core('たんごの', st2, mock_tokenize), None)
    check('たんこ゛の繋がり → たんごの繋がり（たんこう にしない）',
          _fix('たんこ゛の繋がり'), 'たんごの繋がり')
    check('活用語尾は数えない（ほらい→ほせい は生きている）',
          _C.rebuild_window_core('ほらい', st2, mock_tokenize)[2], 'ほせい')

    # --- 濁点合成の補正にも色（スパン）を付ける ---
    # 正規化（たんこ゛→たんご）で行が変わると、詳細もスパンも
    # 空のまま返っていて、補正されたのに色が付かなかった（実機）。
    _rn = _C.correct_line('たんこ゛の繋がり', st2, mock_tokenize,
                          find_known_readings_flex)
    check('濁点合成でも changed', _rn['changed'], True)
    check('濁点合成でもスパンが付く', len(_rn['spans']) > 0, True)
    check('濁点合成でも元位置のスパンが付く',
          len(_rn['original_spans']) > 0, True)
    check('濁点合成でも詳細が付く',
          _rn['details'], [('こ゛', 'ご', 'かな入力')])
    _rn2 = _C.correct_line('たんこ゛のちながり', st2, mock_tokenize,
                           find_known_readings_flex)
    check('合成＋かな補正の複合でも両方にスパンが付く',
          len(_rn2['spans']), 2)

    # --- 方針1-C: 漢字列の再構築の残り（2026-08-08 実装） ---
    print('--- 方針1-C: 漢字列の再構築 ---')
    import kanji_guess as _KG
    from kanji_guess import (find_trailing_kanji_runs,
                             find_leading_kanji_runs)
    check('塊: たん子（かな2＋漢字1）',
          [r[2] for r in find_trailing_kanji_runs('たん子の繋がり')],
          ['たん子'])
    check('塊: 乳リュク（漢字1＋カタカナ）',
          [r[2] for r in find_leading_kanji_runs('乳リュク')],
          ['乳リュク'])
    check('送り仮名が続く形は拾わない（足すときに）',
          find_trailing_kanji_runs('タブ機能を足すときに'), [])
    check('目もち長 は1つの塊（「も」で分断しない）',
          [r[2] for r in _KG.find_kanji_runs('目もち長')], ['目もち長'])
    check('単語の繋がり は「の」で区切る（1塊にしない）',
          '単語の繋' in [r[2] for r in _KG.find_kanji_runs('単語の繋がり')],
          False)

    check('たん子の繋がり → 単語の繋がり',
          _fix('たん子の繋がり'), '単語の繋がり')
    check('タン子の繋がり → 単語の繋がり',
          _fix('タン子の繋がり'), '単語の繋がり')
    check('田安吾の繋がり → 単語の繋がり（脱字を含む誤変換）',
          _fix('田安吾の繋がり'), '単語の繋がり')
    # ★★ `つながり` は種の表に **つながり／繋がり の両方**が在る。
    # 回数を廃したので、どちらを書くかは**最後に選んだ表記の枠**で
    # 決まる（項目48-QH）。枠が `繋がり` を指していれば `繋がり`。
    _lc_tan.remember('つながり', '繋がり', 'つながり')
    check('単語の地長利 → 単語の繋がり（別読みの組み合わせ・枠が決める）',
          _fix('単語の地長利'), '単語の繋がり')
    # **注意: これは mock でしか通らない**（2026-08-11 に確認）。
    # 実 janome ＋ うにさんの語彙（15000語）では `目もち長` が
    # 「正しい日本語として読める」ことになり、守りの関門が先に
    # 効いて直らない。**テストが通っても実機で直っているとは
    # 限らない。** 実機側は `realcheck.py` で数えること。
    check('目もち長 → メモ帳（挿入を含む誤変換・**mock のみ**）',
          _fix('目もち長'), 'メモ帳')
    check('乳リュク → 入力', _fix('乳リュク'), '入力')
    check('文字乳リュク → 文字入力（前に漢字があっても拾う）',
          _fix('文字乳リュク'), '文字入力')
    check('壊さない: 補正ツールを使う',
          _fix('補正ツールを使う'), '補正ツールを使う')
    # これも **mock でしか通らない**（上の注意と同じ理由）。
    check('簡易流力 → 簡易入力（実在語＋壊れた側の分割解決・'
          '**mock のみ**）',
          _fix('簡易流力'), '簡易入力')
    check('たん゛子の繋がり → 単語の繋がり（濁点分離との複合）',
          _fix('たん゛子の繋がり'), '単語の繋がり')

    # --- 前の語に付く語の手前では割らない（2026-08-11・項目48-U）---
    #
    # 「打った行」を 打っ|た行 と割ると、`た`（打つの助動詞）が
    # 次の語の頭になり、たぎょう → さぎょう → **打っ作業**に化ける。
    # README.md の「打った行」で実際に壊れていた。
    #
    # **この症状そのものは mock では再現しない。** mock の辞書は
    # 小さく、`打った行` は別の道（塊まるごと）で `だいたい` に
    # 化ける（この直しの前後で変わらない・別件）。症状の確認は
    # 実 janome ＋ 実機の語彙で行った（README + 全6タブの総点検で、
    # **変わったのはこの1行だけ**）。
    # ここでは、切り口を禁じる仕組みそのものを見る。
    check('打っ|た行 の切り口は禁じられている（た が助動詞）',
          2 in _C._left_attaching_cuts('打った行', mock_tokenize), True)
    check('割ってよい切り口は禁じない（野外|文章）',
          _C._left_attaching_cuts('野外文章', mock_tokenize),
          frozenset())
    check('先頭は禁じない（塊の頭は語の頭）',
          0 in _C._left_attaching_cuts('たまご', mock_tokenize), False)
    check('解析できなければ何も禁じない',
          _C._left_attaching_cuts('打った行', None), frozenset())
    # 禁じた結果、その切り方では組み直さないこと
    check('禁じた切り口では _resolve_kanji_split が答えを出さない',
          _C._resolve_kanji_split('打った行', st2, mock_tokenize), None)
    # 既存の分割解決は生きている（簡易|流力）
    check('簡易流力 の分割解決は生きている',
          _fix('簡易流力'), '簡易入力')

    # --- 正しく読めた語の途中から窓を始めない（項目48-V）---
    #
    # `変わらない` の `らない` が `きない` に化けていた。
    # 〜らない は日常語なので、ありふれた文が片っ端から壊れる。
    # `_tokens_all_known_in_span` が範囲の**頭**を切れ目に
    # 合わせろと求めていたため、語の途中から始まる窓が
    # この守りを素通りしていた（partial_start で緩めた）。
    for _t in ('何も変わらない', 'よく分からない', 'なかなか終わらない',
               '誰も知らない', '見つからないので探す',
               '下ごしらえをする', '会うたびに話す'):
        check(f'壊さない: {_t}', _fix(_t), _t)
    # 仕組みそのものを、実 janome と同じ切り方を手で組んで見る。
    # （mock の辞書は小さく、`変わらない` を 変/わら/ない と切って
    #   しまうので、実機の切り方を再現できない）
    #   実 janome: 変わら(動詞・4〜7・読める) + ない(助動詞・7〜9)
    _toks = [('総', '接頭詞:名詞接続', 'そう', 0, 1, True),
             ('時間', '名詞:副詞可能', 'じかん', 1, 3, True),
             ('は', '助詞:係助詞', 'は', 3, 4, True),
             ('変わら', '動詞:自立', 'かわら', 4, 7, True),
             ('ない', '助動詞:*', 'ない', 7, 9, True)]
    check('頭が語の途中でも守る（partial_start=True・らない）',
          _C._tokens_all_known_in_span(_toks, 6, 9, partial_start=True),
          True)
    check('今までは素通りしていた（partial_start=False）',
          _C._tokens_all_known_in_span(_toks, 6, 9), False)
    check('切れ目に合っていれば今までどおり守る',
          _C._tokens_all_known_in_span(_toks, 4, 9), True)
    # 読めない断片が混じっていれば、今までどおり調べに行く
    _toks2 = [('打ち', '動詞:自立', 'うち', 2, 4, True),
              ('で', '助詞:格助詞', 'で', 4, 5, True),
              ('の', '助詞:連体化', 'の', 5, 6, True),
              ('ほらい', '名詞:一般', 'ほらい', 6, 9, False)]
    check('読めない断片があれば守らない（ほらい は調べに行く）',
          _C._tokens_all_known_in_span(_toks2, 3, 9, partial_start=True),
          False)
    # --- 辞書が読めているカタカナ語は溶かさない（項目48-W）---
    # `左ペイン` が `索引` に化けていた（左 の別読み さ を当てて
    # さぺいん → さくいん）。`ペイン` は壊れていない語。
    # 3文字以上に限る。2文字（カニ・タン）まで守ると
    # カニ打ち→かな打ち・タン子→単語 が通らなくなる。
    check('ペイン（3文字・読める）は守る',
          _C._has_solid_katakana_word('左ペイン', mock_tokenize)
          or _C._has_solid_katakana_word(
              '左ペイン',
              lambda t: [('左', '名詞:一般', 'ひだり', 0, 1, True),
                         ('ペイン', '名詞:一般', 'ぺいん', 1, 4, True)]),
          True)
    check('カニ（2文字）は守らない',
          _C._has_solid_katakana_word(
              'カニ打ち',
              lambda t: [('カニ', '名詞:一般', 'かに', 0, 2, True),
                         ('打ち', '名詞:接尾', 'うち', 2, 4, True)]),
          False)
    check('読めないカタカナ（リュク）は守らない',
          _C._has_solid_katakana_word(
              '乳リュク',
              lambda t: [('乳', '名詞:一般', 'ちち', 0, 1, True),
                         ('リュク', '名詞:一般', '', 1, 4, False)]),
          False)
    check('解析できなければ守らない',
          _C._has_solid_katakana_word('左ペイン', None), False)
    check('カタカナ語を守る塊は溶かさない',
          _C._katakana_melt_ok(
              '左ペイン', '索引', st2,
              lambda t: [('左', '名詞:一般', 'ひだり', 0, 1, True),
                         ('ペイン', '名詞:一般', 'ぺいん', 1, 4, True)]),
          False)
    # 既存のカタカナの当たりは生きている
    check('タン子 → 単語 は生きている', _fix('タン子の繋がり'),
          '単語の繋がり')
    check('乳リュク → 入力 は生きている', _fix('文字乳リュク'),
          '文字入力')

    # 頭にかかる語が1文字なら信用しない（解析が崩れた印）
    _toks3 = [('つ', '助動詞:*', 'つ', 0, 1, True),
              ('あがり', '名詞:一般', 'あがり', 1, 4, True)]
    check('頭にかかる語が1文字なら守らない',
          _C._tokens_all_known_in_span(_toks3, 0, 4, partial_start=True),
          False)

    # 壊してはいけないもの（実在語の複合・カタカナ語）
    for _t in ('タブ機能を足すときに', 'メモ帳', '分割時',
               'ドラッグ変換すると選択が消える', 'その辺は', 'いい子だ',
               '目も疲れた', '気も楽になる', '補正後の文字'):
        check(f'壊さない: {_t}', _fix(_t), _t)

    # 固有名詞（人名 安吾）は実在の根拠にしない。
    # mock は実 janome 同様 田＋安吾 と読める（読みが確定する）が、
    # それでも「田安吾」を直せること。
    _r_ango = _C.correct_line('田安吾の繋がり', st2, mock_tokenize,
                              find_known_readings_flex)
    check('田安吾の繋がり → 単語の繋がり（人名判定を越えて）',
          _r_ango['corrected'], '単語の繋がり')

    # 「〜てしまう」の活用は機能語（ハテ島に化けない）
    check('壊さない: スクロールしてしまいます。',
          _fix('スクロールしてしまいます。'), 'スクロールしてしまいます。')
    check('してしまいます は機能語だけの並び',
          _C._is_all_functional('してしまいます'), True)

    # --- 方針1-D: カタカナ・かなの混じった塊（2026-08-08 実装） ---
    # 実機の対象一覧: カニ打ちでの補正／かな地腕の補正／叶う父での補正
    #   → いずれも かな打ちでの補正。
    # どれも実機の janome では実在語の並びとして読めてしまう
    # （カニ＋打ち／叶う＋父。mock にも同じ語を足してある）ため、
    # 「読める並びを、語の組と文脈の裏付けで直す」経路の検証になる。
    print('--- 方針1-D: カタカナ・かな混じりの再構築 ---')
    from kanji_guess import find_mixed_kana_runs
    check('塊: カニ打ち（カタカナ2＋漢字1＋送り仮名）',
          [r[2] for r in find_mixed_kana_runs('カニ打ちでの補正')],
          ['カニ打ち'])
    check('塊: かな地腕（ひらがな2＋漢字2）',
          [r[2] for r in find_mixed_kana_runs('かな地腕の補正')],
          ['かな地腕'])
    check('カタカナだけ・漢字が続く形は拾わない',
          find_mixed_kana_runs('ドラッグ変換すると'), [])
    check('語の途中からは拾わない（目もち長）',
          find_mixed_kana_runs('目もち長'), [])

    # 実機相当の使用実績（テストメモの自動学習で カニ・叶う も
    # 大きく膨らんでいる。実機の count を模す）と、実機で育つ共起
    # （かな↔打ち↔補正）を用意する。
    st3 = VocabularyStore()
    load_seed(st3)
    for _r, _s, _n in (('かな', 'かな', 852), ('うち', '打ち', 746),
                       ('かに', 'カニ', 403), ('かなう', '叶う', 401),
                       ('きょう', '今日', 3), ('ほせい', '補正', 897),
                       ('りょうり', '料理', 5)):
        for _ in range(_n):
            st3.add(_r, _s)
    from context_vec import ContextVectorStore
    cv3 = ContextVectorStore()
    for _ in range(30):
        cv3.observe_line(['かな', '打ち', '補正', '単語'])
        cv3.observe_line(['補正', '候補', '自動', '入力'])
    _nearby = ['かな', '打ち', '補正', '成立', '単語', '候補']

    def _fix_d(text, nearby=None):
        from vocabulary import find_known_readings_flex as _f
        return _C.correct_line(
            text, st3, mock_tokenize, _f,
            context_vec=cv3,
            nearby_words=_nearby if nearby is None else nearby)['corrected']

    check('カニ打ちでの補正 → かな打ちでの補正（かに→かな）',
          _fix_d('カニ打ちでの補正'), 'かな打ちでの補正')
    check('かな地腕の補正 → かな打ちでの補正（ちう→うち＋助詞）',
          _fix_d('かな地腕の補正'), 'かな打ちでの補正')
    check('叶う父での補正 → かな打ちでの補正（連打畳み＋語の組）',
          _fix_d('叶う父での補正'), 'かな打ちでの補正')
    check('正しい かな打ちでの補正 は触らない',
          _fix_d('かな打ちでの補正'), 'かな打ちでの補正')

    # 同じ形でも「明確に誤り」と言えないものは触らない
    check('壊さない: カニ料理（相方の料理が かな と共起しない）',
          _fix_d('カニ料理を食べる'), 'カニ料理を食べる')
    check('壊さない: カニ料理（無関係な文脈でも）',
          _fix_d('カニ料理を食べる', nearby=['料理', '食べる']),
          'カニ料理を食べる')
    check('壊さない: 叶う父です（文脈の裏付けが無い）',
          _fix_d('叶う父です', nearby=['料理', '食べる']),
          '叶う父です')
    check('壊さない: 周りの語が無ければ カニ打ち も触らない',
          _fix_d('カニ打ちでの話', nearby=['話す']),
          'カニ打ちでの話')
    for _t in ('タブ機能を足すときに', 'メモ帳', 'その辺は', 'いい子だ',
               '目も疲れた', 'ローマ字入力',
               'ドラッグ変換すると選択が消える', '補正ツールを使う'):
        check(f'壊さない(1-D): {_t}', _fix_d(_t), _t)

    # --- 方針1-F: 助詞の混入・脱落（2026-08-08 実装） ---
    # 実機の対象一覧の4例。いずれも実機の janome では実在語の並びと
    # して読めてしまうため、直すのは「直した結果が同じ行（並記）や
    # 周りの語に書かれているとき」だけ。⇒で正解を並べたメモの形が
    # まさにそれに当たる。
    print('--- 方針1-F: 助詞の混入・脱落 ---')
    check('塊: 説明ぶん（漢字＋かな尾）',
          [r[2] for r in find_mixed_kana_runs('説明ぶん ⇒ 説明文')],
          ['説明ぶん'])
    check('塊: クリック化ドラッグ（カタカナ＋漢字1＋カタカナ）',
          [r[2] for r in find_mixed_kana_runs('クリック化ドラッグ、')],
          ['クリック化ドラッグ'])
    st4 = VocabularyStore()
    load_seed(st4)
    for _r, _s, _n in (('せつめいぶん', '説明文', 3),
                       ('せつめい', '説明', 772), ('ぶん', 'ぶん', 486),
                       ('されません', 'されません', 3),
                       ('がいとう', '該当', 413), ('はんい', '範囲', 791),
                       ('くりっく', 'クリック', 843),
                       ('どらっぐ', 'ドラッグ', 797)):
        for _ in range(_n):
            st4.add(_r, _s)

    def _fix_f(text, nearby=()):
        from vocabulary import find_known_readings_flex as _f
        return _C.correct_line(text, st4, mock_tokenize, _f,
                               context_vec=cv3,
                               nearby_words=list(nearby))['corrected']

    check('説明ぶん ⇒ 説明文（変換し損ねの並記）',
          _fix_f('説明ぶん ⇒ 説明文'), '説明文 ⇒ 説明文')
    check('差釣れません ⇒ されません（挿入打鍵の削除）',
          _fix_f('差釣れません。 ⇒ されません。'),
          'されません。 ⇒ されません。')
    check('クリック化ドラッグ ⇒ クリックかドラッグ（助詞が漢字化）',
          _fix_f('クリック化ドラッグ、 ⇒ クリックかドラッグ'),
          'クリックかドラッグ、 ⇒ クリックかドラッグ')
    check('該当あの範囲を ⇒ 該当の範囲を（混入かなの削除）',
          _fix_f('該当あの範囲を ⇒ 該当の範囲を'),
          '該当の範囲を ⇒ 該当の範囲を')
    check('上下の行の並記でも直る（該当あの範囲を）',
          _fix_f('該当あの範囲を選ぶ', nearby=['該当', '範囲', '選ぶ']),
          '該当の範囲を選ぶ')

    # 並記が無ければ触らない（読める並びを文脈なしで壊さない）
    #
    # **設計23（項目48-HM）で、ここは3件だけ変わった。**
    # 近接条件（並記・周りの語）に**単位の表**を並べたので、
    # 「近くに書いてある」以外の証拠でも通るようになった。
    # 表が言えるのは**漢字・カタカナだけの語**についてだけで、
    # かなを含む語（活用形）には使わない——`差釣れません。` は
    # 今までどおり触らない。
    for _t in ('差釣れません。',):
        check(f'並記なしは触らない(1-F): {_t}', _fix_f(_t), _t)
    # **並記が無くても、単位の表が言うなら直す**（設計23・48-HM）
    for _t, _want in (('説明ぶんを書く', '説明文を書く'),
                      ('クリック化ドラッグで操作', 'クリックかドラッグで操作'),
                      ('該当あの範囲を選ぶ', '該当の範囲を選ぶ')):
        check(f'並記なしでも単位の表で直る(設計23): {_t}',
              _fix_f(_t), _want)
    # 正しい文章を壊さない
    for _t in ('システム化プロジェクトを進める', '補正されませんでした。',
               '説明する', '該当の範囲を選ぶ', '刺されませんでした。',
               'タブ機能を足すときに', 'チェック方向は変わります。',
               '最後の漢字で止まるため', 'エンターを押しても消えます'):
        check(f'壊さない(1-F): {_t}', _fix_f(_t), _t)

    # --- 実機で報告された「正しい文を壊す」誤爆の解消（2026-08-08） ---
    # カタカナ語＋漢字の接頭・接尾の複合を、漢字1＋カタカナの塊
    # （leading）が切れ目をまたいで拾って壊していた。
    # ありえない は機能語の並び（あり＋え＋ない）と判定されず
    # 語彙の あんない（案内）に化けていた。
    print('--- 正しい複合語・機能語列を壊さない ---')
    for _t in ('隣接キーや脱字、', '文字コードを選べるようにします。',
               '最大化ボタンを消して', '非アクティブ時のキー',
               '「素帰任」はありえない。'.replace('素帰任', 'そのまま'),
               'ありえないことです',
               '文字が元のカーソル位置に挿入されます。'):
        check(f'壊さない: {_t}', _fix_d(_t), _t)
    check('ありえない は機能語の並び',
          _C._is_all_functional('ありえない'), True)
    # 乳リュク（カタカナ側が実在しない）は引き続き直る
    check('文字乳リュク は引き続き直る', _fix('文字乳リュク'), '文字入力')

    # --- 検証範囲の拡大で出た誤爆の解消（2026-08-08・項目40） ---
    print('--- 検証範囲の拡大で出た誤爆 ---')
    # 実機相当の汚染語彙（大衆3・事項61・日常20・行内758 等）を再現
    st5 = VocabularyStore()
    load_seed(st5)
    for _r, _s, _n in (('たいしゅー', '大衆', 3), ('じこう', '事項', 61),
                       ('にちじょう', '日常', 20), ('ばいきん', 'バイ菌', 3),
                       ('こうない', '行内', 758), ('こぴー', 'コピー', 862),
                       ('しくみ', '仕組み', 200), ('もれ', '漏れ', 50),
                       ('ていじ', '提示', 48), ('はいち', '配置', 92),
                       ('かーそる', 'カーソル', 893), ('いち', '位置', 893)):
        for _ in range(_n):
            st5.add(_r, _s)

    def _fix_g(text):
        from vocabulary import find_known_readings_flex as _f
        return _C.correct_line(text, st5, mock_tokenize, _f,
                               context_vec=cv3,
                               nearby_words=[])['corrected']

    for _t in ('縦シューというのは縦スクロール式のシューティング',
               '作曲、楽器、耳コピ、耳コピー',
               '少し追記してみました。検討してみて下さい。',
               '何倍にもブチ上がります。',
               '隠されたバフ効果を集めれば、',
               '過去7日以内',
               '非アクティブ時のキー',
               '文字が元のカール位置に挿入されます。',
               '53859 bytes).', 'In response,',
               'sexual innuendo; sex-related',
               'we have added more detailed information',
               'Check the categories,'):
        check(f'壊さない(項目40): {_t}', _fix_g(_t), _t)
    check('してみました は機能語の並び',
          _C._is_all_functional('してみました'), True)
    # 連打の畳み込みは各連続から最低1文字残る形だけ
    check('たたんご→たんご は連打の畳み込み',
          _C._is_repeat_collapse('たたんご', 'たんご'), True)
    check('みみこぴー→こぴー は畳み込みではない（頭の切り落とし）',
          _C._is_repeat_collapse('みみこぴー', 'こぴー'), False)
    # カタカナを溶かす置き換えは、シード語彙か使用実績のある語だけ
    check('タン子→単語 は許す（シード語彙）',
          _C._katakana_melt_ok('タン子', '単語', st5), True)
    check('縦シュー→大衆 は許さない（実績3回）',
          _C._katakana_melt_ok('縦シュー', '大衆', st5), False)
    # 数字の直後の塊は当てずっぽうの探索に掛けない（7日以内→行内）
    check('壊さない: 過去7日以内', _fix_g('過去7日以内'), '過去7日以内')
    check('壊さない: 約2倍になる', _fix_g('約2倍になる'), '約2倍になる')
    check('数字直後でも 素帰任 は従来どおり直る（数字が前に無い）',
          _fix_g('素帰任'), '確認')
    # --- 実機確認3巡目で残った・新たに出た誤爆（2026-08-08） ---
    # (1) 空白を挟んだ数字の直後も「形で守る」対象。
    #     実機では「過去 7 日以内」（数字の前後に空白）の 日以内 だけが
    #     行内 に化けたままだった。janome の分割が揺れて
    #     「読める」判定に乗らない環境を、日・以内 の読みが確定しない
    #     tokenizer で模して再現する。
    def _tok_waver(line):
        return [(t[0], t[1], t[2], t[3], t[4],
                 False if t[0] in ('日', '以内') else t[5])
                for t in mock_tokenize(line)]

    def _fix_w(text):
        from vocabulary import find_known_readings_flex as _f
        return _C.correct_line(text, st5, _tok_waver, _f,
                               context_vec=cv3,
                               nearby_words=[])['corrected']

    check('壊さない: 過去 7 日以内（空白入り・分割揺れ）',
          _fix_w('過去 7 日以内'), '過去 7 日以内')
    check('壊さない: 過去　７　日以内（全角空白・全角数字）',
          _fix_w('過去　７　日以内'), '過去　７　日以内')
    # (2) 連体詞「ある」＋名詞 は正しい並び。自動学習が拾った
    #     連用形（あるい→歩い。実機の語彙に count 4 で存在）に
    #     「ある行」が化けた（実機・総点検の両方で再現）。
    for _ in range(4):
        st5.add('あるい', '歩い')
    check('壊さない: 折り返しがある行を途中までスクロール',
          _fix_g('折り返しがある行を途中までスクロール'),
          '折り返しがある行を途中までスクロール')
    check('ある は機能語（連体詞）として説明が付く',
          _C._is_all_functional('ある'), True)

    # --- 叫び声・擬音・掛け声には踏み込まない（2026-08-08 合意） ---
    # うにさんの検証（4コマ・セリフ素材の貼り付け）で、
    # 話し言葉が軒並み語彙の別の語に化けた。
    # 対象外にするのは「ヤッホーのような叫び声に近い合図」だけ。
    # 行ごと・セリフごとの除外はしない（セリフではない括弧書きも
    # あるし、セリフの中の普通の言い回し・文章は補正対象、と修正合意）。
    # 「末尾がーの語は誤検知が多い」という指摘に基づく形の判定と、
    # 直後に！？♡…が付く短いかな（おたから！）だけを対象外にする。
    print('--- 叫び声・擬音・掛け声を壊さない ---')
    # 実機の汚染語彙を模す（セリフ検証で実際に化けた先の語）
    for _r, _s, _n in (('あるい', '歩い', 4), ('すこあ', 'スコア', 20),
                       ('えいご', '英語', 50), ('にちや', '日夜', 6),
                       ('さいてき', '最適', 30), ('ちょっと', 'ちょっと', 30),
                       ('こうもく', '項目', 40), ('おくら', 'おくら', 5),
                       ('きいろ', 'きいろ', 5), ('わから', 'わから', 5),
                       ('ふわふわ', 'ふわふわ', 5), ('ためいき', 'タメ息', 5)):
        for _ in range(_n):
            st5.add(_r, _s)
    # 叫び声・合図（直後に！？♡…が付く短いかな）と、
    # セリフ内の正しい言い回し（機能語の並びとして守られる）
    for _t in ('おたから！', 'ねこだまし！', 'なんだお前は！',
               '止めるんだ！', 'させないわよ！', 'ちょっとぉ！',
               '「でもいいんだ」', '「ガチ過ぎないか…」',
               'きゅっ♡', 'どこへ飛ぶかはー？', 'もうやめろ…'):
        check(f'叫び声・正しいセリフ: {_t}', _fix_g(_t), _t)
    # --- 実機確認5巡目の指摘（2026-08-08）---
    # 化けた先の語を実機相当で持たせて再現性を保つ
    for _r, _s, _n in (('りえ', 'りえ', 5), ('はじめて', 'はじめて', 30),
                       ('はじめ', '初め', 3),
                       ('ねんだい', '年代', 5), ('にやん', 'にやん', 5)):
        for _ in range(_n):
            st5.add(_r, _s)
    # 「だよねえ」のような言い回しの末尾（ねえ・ねぇ・よねえ）は対象外
    for _t in ('釣れないねえ', '釣れないねぇ', 'いいよねえ', 'だよね'):
        check(f'言い回しの末尾: {_t}', _fix_g(_t), _t)
    # 意向形「よう」: 既知語＋機能語の並びは正しい形
    check('はじめようか は直さない', _fix_g('はじめようか'), 'はじめようか')
    # え段＋え の俗語（おもしろい→おもしれえ）は意図した表記
    for _t in ('おもしれえ', 'すげえ'):
        check(f'俗語の伸ばし: {_t}', _fix_g(_t), _t)
    # 拗音を開くだけの訂正はしない（にゃん→にやん）
    for _t in ('にゃん', 'ひゃっ', '「にゃん」にゃん「」'):
        check(f'拗音を開かない: {_t}', _fix_g(_t), _t)
    # 逆方向（シフトの押し忘れ）は従来どおり直る
    check('しゆうせい→しゅうせい は直る（大書き→小書き）',
          _fix('しゆうせい'), 'しゅうせい')
    # 小書きが減る同長の置換はしない（きゅっ→きやっ。実機6巡目）
    st5.add('きやっ', 'きやっ')
    st5.add('きやっ', 'きやっ')
    check('きゅっ♡ は触らない（小書きが減る置換をしない）',
          _fix_g('きゅっ♡'), 'きゅっ♡')
    # 授受の補助動詞（〜てもらう）は機能語の並び（実機6巡目:
    # 消してもらっては→消してもけってい困る）
    st5.add('けってい', '決定')
    st5.add('けってい', '決定')
    check('消してもらっては困る は触らない',
          _fix_g('消してもらっては困る'), '消してもらっては困る')
    # 接頭の「お」: なんだお（なん＋だ＋お）に単語は無い
    for _t in ('なんだお', 'なんだお前は！'):
        check(f'接頭のお: {_t}', _fix_g(_t), _t)

    # セリフ（括弧書き・！付き）の中の普通の文章は補正対象のまま。
    # 行ごと対象外にはしない、という修正合意（2026-08-08）の固定。
    check('「」の中の誤変換も直る', _fix_g('「たん子の繋がりです」'),
          '「単語の繋がりです」')
    check('！で終わる行の誤変換も直る', _fix_g('たん子の繋がりです！'),
          '単語の繋がりです！')
    # 伸ばし言葉・擬音の形（ー・小書き・繰り返し・末尾っ）
    for _t in ('みかーん', 'きゅーん', 'うれしー', 'こわーい',
               'もしもーし', 'すりーぷ', 'よかったー', 'だれかー',
               'はわはわ', 'わうわう', 'うほうほ', 'きゅきゅ',
               'あいたぁ', '中においでぇ', 'かくごっ', 'ふぇぇん',
               '月夜さまーっ', 'つんぼよーん'):
        check(f'擬音・伸ばし: {_t}', _fix_g(_t), _t)
    # カタカナ語をひらがなで打った誤打（ーが2つ）。
    #
    # **ここは項目48-GI（2026-08-19）で向きが変わった。**
    # `そ → ど` は1文字違いなので、項目48-FX の門が掛かる:
    #
    #     ローマ字入力  so → do   **s と d は隣**    → 直る
    #     かな入力      そ → ど   ど は と＋濁点の2打鍵 → **直さない**
    #
    # うにさんの指定（2026-08-19）「1文字違うだけでは補正しません、
    # その違いが隣接キーかどうか。隣接判定はかな入力とローマ字入力で
    # 変わる」のとおり。48-FX で6件向きが変わったのと同じ話で、
    # **この道（ひらがな連続）にだけ門が掛かっていなかった**のを
    # 48-GI で掛け直したため、ここも揃った。
    check('きーぼーそ は**ローマ字入力なら**直る（ー2つ・位置保存）',
          _fix_im('きーぼーそ', 'romaji'), 'キーボード')
    check('きーぼーそ は**かな入力では**直さない（項目48-GI）',
          _fix_im('きーぼーそ', 'kana'), 'きーぼーそ')
    # 話し言葉の代名詞・疑問詞・副詞の保護
    for _t in ('わしらの縄張りに', 'どうなんだ', 'ロゴを刻んだんだ',
               'ちょっとしたメモを補正付きで書ける',
               '変換ミスが起こりやすい語は',
               'そこからすぐ上は', 'ついて来な'):
        check(f'話し言葉・副詞の並び: {_t}', _fix_g(_t), _t)
    # 数字の直後の塊（カタカナ混じり・空白入りも）は形で守る
    for _t in ('4コマ目', '最大 30 日間無料で'):
        check(f'数字の直後: {_t}', _fix_g(_t), _t)
    # 固有名詞・意図した表記
    for _t in ('田無駅、北口', '&sort=releasedate',
               'ソフト上の不具合がある'):
        check(f'意図した表記: {_t}', _fix_g(_t), _t)
    # 語彙の整理（VocabularyStore.remove）
    _sr = VocabularyStore()
    _sr.add('たいしゅー', '大衆')
    check('語彙の削除ができる', _sr.remove('たいしゅー', '大衆'), True)
    check('削除した語彙は引けない', _sr.lookup('たいしゅー'), [])
    check('無い語彙の削除は False', _sr.remove('x', 'y'), False)

    # --- 入力方式の自動判定（ime_watch。判定ロジックのみ検証） ---
    # IMM32 の呼び出しは Windows でしか動かないため、
    # 変換モードの値の読み取り（純粋関数）だけをここで固定する。
    import ime_watch
    check('IME_CMODE_ROMAN が立っていれば ローマ字入力',
          ime_watch.mode_from_conversion(0x0019), 'romaji')
    check('IME_CMODE_ROMAN が無ければ かな入力',
          ime_watch.mode_from_conversion(0x0009), 'kana')
    check('Windows 以外では判定しない（None）',
          ime_watch.current_input_method(12345)
          if not ime_watch.HAS_SUPPORT else None, None)
    from settings import Settings, DEFAULTS
    check('自動判定は既定でオン', DEFAULTS.get('input_method_auto'), True)
    # 自動反映の既定（うにさんの指定・2026-08-30・項目48-LX）。
    # 統合表示と簡易入力の**両方**がオン。片方だけ落ちると
    # 「簡易入力だけ直らない」に戻るので、見張りをここに置く。
    check('統合表示の自動反映は既定でオン',
          DEFAULTS.get('unified_autofix'), True)
    check('簡易入力の自動反映は既定でオン（48-LX）',
          DEFAULTS.get('quick_autofix'), True)

    # 5-i. 語の区切りが取れない行でも、色は補正箇所だけに付く
    from units import build_suspect_units as _bsu

    def _tok_skip_space(line):
        return [t for t in mock_tokenize(line) if t[0].strip()]

    # **材料を `たんほ` から `たああんご` に替えた**（項目48-FX）。
    # `たんほ → たんご` はかな入力では触らなくなったので、
    # 「補正箇所に色が付くか」を測る材料にならない。
    # 連打の巻き戻し（たああんご → たんご）は今までどおり直る。
    _r5 = _C.correct_line('　たああんごの繋がりです', st2, mock_tokenize,
                          find_known_readings_flex)
    _t5, _u5 = _bsu(_r5, _tok_skip_space)
    check('先頭スペース行でも行全体は suspect にならない',
          [u['kind'] for u in _u5][:1], ['plain'])
    check('補正箇所には suspect が付く',
          any(u['kind'] == 'suspect' and u['text'] == 'たああんご'
              for u in _u5), True)

    return all_ok
