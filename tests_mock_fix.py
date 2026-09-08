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
**補正そのもの**（直る・直しすぎない・同音・記号）の試験。

`tests_mock.py` から分けたもの（2026-08-20・項目48-GQ）。
**走らせる入口は `tests_mock.py` のまま。**
"""
import corrector as C
from vocabulary import VocabularyStore, find_known_readings_flex, dup_repair_enabled
from seed_vocabulary import load_seed

from tests_mock_common import build_store, mock_tokenize


def run_cases(store, cases, title):
    """cases: [(入力, 変化すべきか, 期待する結果 or None), ...]"""
    print(f'--- {title} ---')
    all_ok = True
    for item in cases:
        line, should_change = item[0], item[1]
        expected = item[2] if len(item) > 2 else None
        r = C.correct_line(line, store, mock_tokenize, find_known_readings_flex)
        ok = (r['changed'] == should_change)
        if ok and expected is not None:
            ok = (r['corrected'] == expected)
        all_ok = all_ok and ok
        mark = 'OK ' if ok else 'NG '
        print(f'{mark}{line}')
        if r['changed']:
            print(f'      => {r["corrected"]}')
        if not ok and expected:
            print(f'      期待: {expected}')
    return all_ok


def run_overcorrection_cases():
    """
    実機7巡目（2026-08-09）の誤検知への関門。

    count の水増し（学習の不具合・項目46）で「使用実績のある語」が
    12000件を超えた実機で、正しい文章が大量に書き換えられた。
    水増し自体は止めたが、判断の関門も規模に耐える形に直した。
    その関門の回帰テスト。
    """
    import corrector as _C
    from vocabulary import (VocabularyStore, find_known_readings_flex,
                            weighted_edit_distance)
    from halfwidth import correct_halfwidth, correct_romaji

    print('--- 誤検知の関門（実機7巡目・2026-08-09） ---')
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    st = VocabularyStore()
    for _r, _s, _c in (('ぱん', 'パン', 'その他'),
                       ('はんかく', '半角', 'IT・PC操作'),
                       ('たんご', '単語', '学業・勉強'),
                       ('あまぞん', 'アマゾン', 'その他'),
                       ('ねむり', '眠り', 'その他'),
                       ('あらかじめ', 'あらかじめ', 'その他'),
                       ('じめん', '地面', 'その他'),
                       ('まきこむ', '巻き込む', '日常会話')):
        for _ in range(4):
            st.add(_r, _s, _c)
    fn = _C.make_tokenizer(st)

    # --- 数字だけの並びを半角かな入力と解釈しない ---
    # 実機で 電話番号：03-6230-9666 が けわあほオフ… に化けた。
    check('電話番号を かな に変換しない',
          correct_halfwidth('03-6230-9666', st,
                            find_known_readings_flex), None)
    check('数字と記号だけの列に触らない',
          correct_halfwidth('12/25 10:30', st,
                            find_known_readings_flex), None)

    # --- 頭が大文字の英単語をローマ字と解釈しない ---
    # 実機で Amazon が アマゾン に化けた。
    check('頭が大文字の英単語はローマ字扱いしない',
          correct_romaji('Amazon', st, find_known_readings_flex), None)

    # --- 読みの候補列のどれかが正しい読みとして通るなら塊ごと触らない ---
    # 実機で パン屋 の読み ぱんや（既知語＋助詞）を差し置いて、
    # 別の読み ぱんおく（屋=おく）が はんかく に訂正され
    # 「パン屋の」→「半角の」と壊れた。
    check('正しい読みが通る塊は、別の読みで訂正しない',
          _C._resolve_reading_list('パン屋', ['ぱんや', 'ぱんおく'],
                                   st, fn), None)
    check('正しい読みが無い塊は従来どおり直せる（たん子→単語）',
          _C._resolve_reading_list('たん子', ['たんこ'], st, fn),
          ('単語', '学業・勉強'))

    # --- 語頭に立たない文字で始まる芯は、切り出しがずれている ---
    # 実機で 竹かんむり の芯 んむり が ねむり に訂正され
    # かねむり に化けた（うっかり→うしっかり も同じ構図）。
    check('ん で始まる芯は直さない（かんむり を守る）',
          _C.rebuild_window_core('かんむり', st, fn, after_kanji=True),
          None)

    # --- 既知語の腹を切った芯は直さない ---
    # 実機で あらかじめお渡し の芯 じめお が じめん に訂正され
    # あらかじめん渡し に化けた。
    check('あらかじめ の途中を切った芯は直さない',
          _C.rebuild_window_core('あらかじめお', st, fn,
                                 after_kanji=False), None)

    # --- 同じ長さのまま2文字以上を置き換える候補は採らない ---
    # 実機で まごころ が まきこむ に化けた（2文字置換で別の語に
    # 乗り換えていた）。
    check('まごころ を まきこむ に乗り換えない',
          _C.rebuild_window_core('まごころの', st, fn,
                                 after_kanji=False), None)

    # --- 実機8巡目（2026-08-09・項目47-c）の関門 ---
    st2 = VocabularyStore()
    for _r, _s2, _c in (('すみび', '炭火', 'その他'),
                        ('たび', '旅', 'その他'),
                        ('つかり', '浸かり', 'その他'),
                        ('おやま', 'おやま', 'その他'),
                        ('ぱせり', 'パセリ', 'その他')):
        for _ in range(4):
            st2.add(_r, _s2, _c)
    fn2 = _C.make_tokenizer(st2)

    # 送り仮名の頭＋正しい語（話す＋たびに）を芯にしない
    check('すたび を すみび に直さない（送り仮名＋たび）',
          _C.rebuild_window_core('すたびに', st2, fn2,
                                 after_kanji=True), None)
    # 助詞を1文字消しただけの候補（つばかり→つかり）は採らない
    check('つばかり から ば を消して つかり にしない',
          _C.rebuild_window_core('つばかり', st2, fn2,
                                 after_kanji=True), None)
    # 機能語の途中で切れた芯（おきま＋して）は直さない
    check('おきまして の芯 おきま を おやま にしない',
          _C.rebuild_window_core('おきまして', st2, fn2,
                                 after_kanji=True), None)
    # 擬態語「〜りと」は語彙と突き合わせない
    check('ぱちりと を ぱせりと にしない（擬態語）',
          _C.rebuild_window_core('ぱちりと', st2, fn2,
                                 after_kanji=False), None)

    # --- 実機9巡目（2026-08-09・項目47-d）の関門 ---
    st3 = VocabularyStore()
    for _r, _s3 in (('らんど', 'ランド'), ('みどころ', '見どころ'),
                    ('おうじ', '応じ')):
        for _ in range(4):
            st3.add(_r, _s3)
    fn3 = _C.make_tokenizer(st3)
    # 逆接の ども／ねども は機能語（劣らねども）
    check('らねども の芯 らねど を らんど にしない',
          _C.rebuild_window_core('らねども', st3, fn3,
                                 after_kanji=True), None)
    # む も送り仮名の頭（包む＋どころ）
    check('むどころ を みどころ にしない（送り仮名 む）',
          _C.rebuild_window_core('むどころ', st3, fn3,
                                 after_kanji=True), None)
    # 促音で終わる芯は切り出しがずれている（往って の おうっ）
    check('おうっ を おうじ にしない（語末に立たない っ）',
          _C.rebuild_window_core('おうっ', st3, fn3,
                                 after_kanji=False), None)

    return all_ok


def run_kanji_guess_cases(store):
    """
    語として成立しない漢字列を、読みに戻して推測する。

    かな入力の誤打はIMEを通って漢字になるため、画面に出るのは
    漢字の誤変換になる。「素帰任」は語として存在しないので、
    文脈を見るまでもなく「ありえない」と分かり、
    読みに戻せば機械的に「確認」まで導ける。

    ここで最も大事なのは **正しい漢字列を壊さないこと**。
    「文字化け対策」のような、正しい語に別の語が続いただけの
    ごく普通の複合語を誤変換と見なして壊してはいけない。
    """
    from kanji_guess import (find_kanji_runs, reading_combos,
                             looks_like_real_word, suggest_for_run)
    from vocabulary import find_known_readings_flex

    print('--- ありえない漢字列の推測（読みに戻して直す） ---')
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    tokenize_fn = C.make_tokenizer(store)

    # --- 塊の切り出し ---
    check('漢字の連続を塊として取り出す',
          [t for _s, _e, t in find_kanji_runs('素帰任しておいて')],
          ['素帰任'])
    check('誤変換に混ざった小さなカタカナも塊に含める',
          [t for _s, _e, t in find_kanji_runs('時ッ層')], ['時ッ層'])
    check('日常の漢字だけの2文字は、正しい語とみなして触らない',
          find_kanji_runs('確認です'), [])
    # 長さで一律に切らず、異様さで判断する。
    # 「魔訶」は2文字だが「訶」が日常では使わない漢字なので調べる。
    # 「見切」は日常の漢字だけなので触らない
    # （触ると「見切れます」を「右れます」に壊した実例がある）。
    check('漢字の間の送り仮名を含めて1つの塊にする',
          [t for _s, _e, t in find_kanji_runs('見切れ魔訶')],
          ['見切れ魔訶'])
    check('正しい「見切れます」は塊として取り出さない',
          find_kanji_runs('見切れます'), [])
    # 助詞「の」で切れるので、「単語」と「繋」が別々になる。
    # どちらも日常の漢字なので、結果として調べる塊は残らない。
    check('助詞をまたいで1つの塊にしない',
          find_kanji_runs('単語の繋がり'), [])
    check('助詞をまたぐと塊が分かれる',
          [t for _s, _e, t in find_kanji_runs('魔訶の魔訶')],
          ['魔訶', '魔訶'])
    check('「見切れ魔訶」から「みきれまか」を導ける',
          'みきれまか' in reading_combos('見切れ魔訶'), True)

    # --- 読みに戻す ---
    combos = reading_combos('素帰任')
    check('「素帰任」から「すきにん」を導ける',
          'すきにん' in combos, True)
    check('「時ッ層」から「じっそう」を導ける',
          'じっそう' in reading_combos('時ッ層'), True)

    # --- 実在する語かどうかの見分け ---
    # looks_like_real_word は形態素解析による全体一致だけを見る
    # （モックの分割器では「文字化」を1語として扱い、読みが
    #   確定しないため False になる。これは実機の janome では
    #   「文字」+「化」に分割され True になる想定）。
    # 保護そのものは strangeness 側（シード語彙・辞書の部分一致）が
    # 別途担っているので、ここが False でも実害は無い
    # （下の「壊さないこと」のテストで確認する）。
    check('中に既知の語が無いものは、ありえない列とみなす',
          looks_like_real_word('素帰任', store, tokenize_fn), False)

    # --- 実際に届くか ---
    got = suggest_for_run('素帰任', store, find_known_readings_flex,
                          tokenize_fn=tokenize_fn)
    check('「素帰任」から「確認」に届く', got[0] if got else None, '確認')
    got2 = suggest_for_run('時ッ層', store, find_known_readings_flex,
                           tokenize_fn=tokenize_fn)
    check('「時ッ層」から「実装」に届く', got2[0] if got2 else None, '実装')

    # --- 補正エンジン全体を通して ---
    def corrected(line):
        return C.correct_line(
            line, store, tokenize_fn, find_known_readings_flex)['corrected']

    check('文の中の「素帰任」が直る',
          corrected('素帰任しておいてください。'),
          '確認しておいてください。')

    # --- カタカナと漢字が混ざった塊 ---
    # かな入力の誤打では、IMEが途中までをカタカナ、残りを漢字に
    # 変換してしまうことがある（「タン子」「タン具」）。
    # 分解して「たんこ」に戻せば「たんご」＝「単語」に届く。
    check('カタカナと漢字が混ざった塊も調べる',
          [t for _s, _e, t in find_kanji_runs('タン子の繋がり')],
          ['タン子'])
    check('カタカナだけの語は触らない（外来語を壊さないため）',
          find_kanji_runs('ネイルとスタン'), [])
    check('「タン子」から「単語」に届く',
          corrected('タン子の繋がり'), '単語の繋がり')
    check('「タン具」から「単語」に届く',
          corrected('タン具の繋がり'), '単語の繋がり')

    # --- 文末の語尾 ---
    # 文末記号が続く塊は、活用語尾で終わる語の可能性が高い。
    # 「見切れ魔訶。」の「まか」は打ち間違いとして「ます」に近いが、
    # 活用した形は語彙に載りにくいので、語尾を補って探す。
    from kanji_guess import _looks_sentence_end, _tail_variants
    check('句点の手前は文末とみなす',
          _looks_sentence_end('見切れ魔訶。', 5), True)
    check('助詞が続く場合は文末とみなさない',
          _looks_sentence_end('見切れ魔訶が', 5), False)
    check('行末は文末とみなす',
          _looks_sentence_end('見切れ魔訶', 5), True)
    check('語尾を差し替えた候補を作る',
          'みきれます' in _tail_variants('みきれまか'), True)

    # 活用した形が語彙にあれば、文末の塊が直る。
    store.add('みきれます', '見切れます', 'IT・PC操作')
    store._by_reading['みきれます']['見切れます']['count'] = 3
    check('文末の「見切れ魔訶。」が直る',
          corrected('見切れ魔訶。'), '見切れます。')

    # --- 異様さの度合いで、踏み込む深さを変える ---
    # 「分割時」のような、辞書に無いだけのふつうの熟語を
    # 壊してはいけない（実機で「分割」を「分科」に壊した）。
    # 一方「素帰任」のように、どこを切っても語にならない列は、
    # 2箇所直してでも「確認」に届けにいく価値がある。
    from kanji_guess import strangeness
    check('ふつうの熟語は異様さ0（＝打鍵の推測をしない）',
          strangeness('分割時', store), 0)
    check('「単語登録」も異様さ0', strangeness('単語登録', store), 0)
    check('どこを切っても語にならない列は異様さが高い',
          strangeness('素帰任', store) >= 2, True)
    check('カタカナと漢字の混在は異様さが高い',
          strangeness('タン子', store) >= 2, True)
    check('日常で使わない漢字を含むと異様さが高い',
          strangeness('見切れ魔訶', store) >= 2, True)
    check('「分割時」は塊として取り出されても直さない',
          corrected('分割時、元に戻す'), '分割時、元に戻す')
    check('「分割モード」を壊さない',
          corrected('分割モードで元に戻せる'), '分割モードで元に戻せる')

    # ぴったり2文字の塊（「分割」単体）が、部分文字列の検査から
    # 漏れて常に「異様」判定になっていた欠陥への回帰テスト。
    # range(n-1, 1, -1) は n=2 のとき空になるため、2文字の熟語は
    # そのままだと既知語を含むかを一度も調べられなかった
    # （実機で7000件超の語彙でも「分割」が「分科」に壊れた）。
    check('2文字の塊（分割）も、既知語なら異様さ0',
          strangeness('分割', store), 0)
    check('2文字の塊でも直さない',
          corrected('分割'), '分割')

    # 異様さの判定は、ユーザーの使用回数（count）に一切頼らない。
    #
    # 以前は「塊の一部が使用実績のある既知語なら安全」としていたが、
    # これは語彙が育つほど脆くなる。検証時の貼り付けの繰り返しで
    # 「帰任」の使用回数だけが人工的に積み上がると、無関係な
    # 「素帰任」まで「帰任を含むから安全」と誤って保護してしまう
    # （実機の7000件超の語彙、count=90 で実際に発生した）。
    # 「帰任をいくら使っていても、素帰任の不自然さとは無関係」
    # という指摘のとおり、使用回数がどれだけ大きくても
    # （シード語彙にも辞書にも無い語である限り）
    # 保護の根拠にはならない。
    store.add('きにん', '帰任', '日常会話')
    e = store._by_reading['きにん']['帰任']
    e['count'] = 90    # 汚染された使用回数を模した値
    check('使用回数がどれだけ多くても、辞書に無い語は保護の根拠にしない',
          strangeness('素帰任', store) >= 2, True)
    check('汚染された使用回数があっても「確認」に届く',
          corrected('素帰任'), '確認')

    # 複数のもっともらしい訂正候補がある場合、機械的に最も
    # 訂正コストの低いもの（＝より自然な打ち間違い）を採用する。
    #
    # 「素帰任」は「そきにん→責任」（1箇所訂正）にも
    # 「すきにん→確認」（2箇所訂正）にも届きうる。どちらも
    # 正しい日本語であり、機械的な決め手は訂正コストの大小しかない
    # （実機で「責任」が選ばれた例があり、これは仕様として
    #   受け入れる。うにさんの意図と食い違う場合は、選び直し
    #   （右クリック・F2）で対応する）。
    from kanji_guess import suggest_for_run
    store.add('せきにん', '責任', '仕事・ビジネス')
    e2 = store._by_reading['せきにん']['責任']
    e2['count'] = 5
    got = suggest_for_run('素帰任', store, find_known_readings_flex,
                          tokenize_fn=tokenize_fn)
    check('訂正コストが低い方（1箇所訂正）を優先する',
          got[0] if got else None, '責任')

    # --- 正しい文を壊さないこと（こちらのほうが重要） ---
    keep = [
        '文字化け対策',      # 「文字」＋「化け」。正しい複合語
        '単語登録機能',
        '画面表示設定',
        '漢字変換候補',
        '入力補正機能',
        '日本語入力の話',
        '再帰関数の実装',
        '検索置換機能',
        '山田太郎さんに連絡',   # 人名
        '東京都渋谷区',         # 地名
        'ネイルも髪も推し仕様にした',   # カタカナの俗語・固有名詞
        'MTGスタン率直に言って',
        '見切れます',           # 正しい活用形
        '確認します。',         # 文末でも壊さない
        '実装しました。',
        '単語の繋がり。',
        '分割時、元に戻す',     # 辞書に無いだけの正しい熟語
        '分割モードで元に戻せる',
        '削除時の処理',
        '引用モードになります',
        '簡易入力の横幅',
    ]
    broken = [t for t in keep if corrected(t) != t]
    check('正しい漢字列を壊さない', broken, [])

    return all_ok


def run_original_spans_cases(store):
    """
    correct_line() が返す original_spans（元テキスト上の置換範囲）。

    「自動では直さず、疑わしい箇所に色をつけるだけ」の表示
    （統合レイアウト・簡易入力ウィンドウで使う予定）のために追加した。
    spans が補正後テキスト上の位置であるのに対し、
    original_spans は常に元のテキスト（変更前）上の位置でなければならない。
    """
    print('--- 元テキスト上の疑わしい箇所（original_spans） ---')
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    r = C.correct_line('もんたい、ぱそみん', store, mock_tokenize,
                       find_known_readings_flex)
    check('original_spans が details と同じ件数',
          len(r['original_spans']), len(r['details']))
    all_match = all(
        r['original'][s:e] == original
        for (s, e), (original, _c, _cat) in zip(r['original_spans'],
                                                 r['details']))
    check('original_spans が元テキストの該当箇所と一致する', all_match, True)

    # 補正が無い行では両方とも空
    r2 = C.correct_line('ヤバい', store, mock_tokenize,
                        find_known_readings_flex)
    check('補正が無ければ original_spans も空', r2['original_spans'], [])

    # 半角・ローマ字経由（文字数が変わる）でも元テキスト基準になっている
    r3 = C.correct_line('mojinyuuryoku', store, mock_tokenize,
                        find_known_readings_flex)
    if r3['original_spans']:
        s, e = r3['original_spans'][0]
        check('半角/ローマ字経路でも元テキストの範囲を指す',
              r3['original'][s:e], 'mojinyuuryoku')

    return all_ok


def run_regression_cases(store):
    """
    実機で報告された誤検知・誤変換の再発防止。

    いずれも「正しく書けているものを壊さない」ことが目的。
    """
    print('--- 実機報告の誤検知（変化しないのが正解） ---')
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    # 同音の実在語どうしが、文脈だけで置き換わってはいけない。
    # 「性格」と「正確」、「彷徨」と「方向」はどちらも実在語で、
    # どちらが正しいかは自動では決められない。
    from vocabulary import build_context_vocab

    def known_tokenize(line):
        """実在語として認識できている前提のトークナイザ。"""
        toks = mock_tokenize(line)
        return [(s, p, r, st, en, True)
                for s, p, r, st, en, _k, *_ in toks]

    pairs = [
        ('性格改善', ['正確な作業']),
        ('街を彷徨う', ['方向を変える']),
    ]
    for text, other_lines in pairs:
        ctx = build_context_vocab(other_lines + [text], store)
        r = C.correct_line(text, store, known_tokenize,
                           find_known_readings_flex, context_vocab=ctx)
        check(f'{text} が文脈で書き換えられない', r['corrected'], text)

    # メールアドレス・URL は半角のまま残す
    for text in ['someone742@example.com', 'https://example.com/abc',
                 'www.google.co.jp']:
        r = C.correct_line(text, store, mock_tokenize,
                           find_known_readings_flex)
        check(f'{text} が変換されない', r['corrected'], text)

    # かな入力の半角打ちは従来どおり変換される（@ は濁点キー）
    for text, want in [('md@i(4l)h', '文字入力'),
                       ('mojinyuuryoku', '文字入力')]:
        r = C.correct_line(text, store, mock_tokenize,
                           find_known_readings_flex)
        check(f'{text} は従来どおり変換される', r['corrected'], want)

    return all_ok


def report_known_issues(store):
    """
    実機で報告された未解決の問題の再現確認（合否には含めない）。

    このサンドボックスには janome が無いため、実機と同じ分割に
    ならないものが多い。ここでは「この環境で再現するか」だけを見て、
    修正の際の手がかりにする。
    """
    print('--- 実機報告の問題（参考: この環境での挙動） ---')

    cases = [
        # (入力, 実機で望む結果)
        # 誤字が反応しない（未実装の同音異義語・複数語またぎが大半）
        ('新規チャットに映るので', '新規チャットに移るので'),
        ('時ッ層', '実装'),
        ('待ち外の補正', '間違いの補正'),
        ('売った文字', '打った文字'),
        ('糸を察して', '意図を察して'),
        # 正しい文が壊された（実機報告）
        ('チェックがうまく動いてない', 'チェックがうまく動いてない'),
        ('「文字の入力」にします。', '「文字の入力」にします。'),
        ('判断をします。', '判断をします。'),
        ('単語のつながりのほうが文脈が合う', '単語のつながりのほうが文脈が合う'),
        ('一回り小さくします', '一回り小さくします'),
        ('Pythonを入れていないPC', 'Pythonを入れていないPC'),
        # 「単語の繋がり」にしたいが直らない
        ('タン具の繋がり', '単語の繋がり'),
        ('高後の綱切り', '単語の繋がり'),
        ('タン子の繋がり', '単語の繋がり'),
        ('単語の綱刷り', '単語の繋がり'),
        ('単語ま繋がり', '単語の繋がり'),
        ('たんこ゛の繋がり', 'たんごの繋がり'),
        ('たんこ゜のつながり', 'たんごのつながり'),
    ]
    for text, want in cases:
        r = C.correct_line(text, store, mock_tokenize,
                           find_known_readings_flex)
        got = r['corrected']
        if got == want:
            mark = '一致  '
        elif got == text:
            mark = '無反応'
        else:
            mark = '別結果'
        print(f'{mark} {text!r} -> {got!r}' +
              ('' if got == want else f'  (望み: {want!r})'))
    print('（一致以外は実機での診断が必要。diagnose.py のケースに追加済み）')


# ============================================================
# 項目48-P: メモに書かれている語を候補に出す／かなを繋ぐ
# ============================================================
def test_attested_candidates():
    """
    うにさんの指摘（2026-08-11・F-1）:「『ひらがな』部分を
    ドラッグしましたが、候補に『平仮名』がありませんでした。
    1文字ずつに分解されているのが違和感あります」。

    `平仮名` は janome の辞書にあるが**コスト 5614** で索引の上限
    4000 に弾かれ、自動学習も「同じ読みに別表記が既にある語は
    覚えない」規則で覚えられない。どこからも出てこなかった。
    **本人がメモに書いている語**を候補の出どころに足して直した。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    from candidates import build_candidates, build_range_candidates
    from units import _merge_kana_runs
    from vocabulary import VocabularyStore, find_known_readings_flex, dup_repair_enabled

    print('--- 項目48-P（メモの語を候補に／かなを繋ぐ） ---')

    store = VocabularyStore()
    for _ in range(3):
        store.add('ひらがな', 'ひらがな', '学業・勉強')
    attested = {'ひらがな': ['平仮名'], 'なおり': ['治り', '直り']}

    def names(cands, kind=None):
        return [c['surface'] for c in cands
                if kind is None or c['kind'] == kind]

    c = build_candidates('ひらがな', 'ひらがな', store,
                         find_known_readings_flex, attested=attested)
    check('メモに書かれている表記が候補に出る',
          '平仮名' in names(c, 'homophone'), True)
    # 2026-08-27（項目48-KC）から、attested を渡さなくても**同梱の表**
    # （seed_japanese_cost・読み→表記）から「漢字にする」候補が出る
    # （うにさんの報告「わずかな・なぜか——平仮名だから候補が出ない。
    # この場合は漢字変換候補を並べてください」）。前はここが
    # 「渡さなければ出ない」の見張りだった。
    c0 = build_candidates('ひらがな', 'ひらがな', store,
                          find_known_readings_flex)
    check('渡さなくても、表から「漢字にする」候補が出る（項目48-KC）',
          '平仮名' in names(c0, 'kanji'), True)

    r = build_range_candidates([('ひ', 'ひ'), ('ら', 'ら'),
                                ('が', 'が'), ('な', 'な')],
                               store, find_known_readings_flex,
                               attested=attested)
    check('ドラッグ範囲の候補にも出る', '平仮名' in names(r), True)

    c2 = build_candidates('治り', 'なおり', store,
                          find_known_readings_flex, attested=attested)
    check('同じ読みで書かれた別表記も出る（治り→直り）',
          '直り' in names(c2, 'homophone'), True)

    # --- 1文字ずつに切れたかなを繋ぐ ---
    def u(text, kind='plain', detail=None):
        return {'text': text, 'base': text, 'reading': text,
                'kind': kind, 'detail': detail, 'start': 0, 'end': len(text),
                'prev': '', 'next': ''}

    known = lambda s: s in ('ひらがな', 'つながり')

    got = [x['text'] for x in _merge_kana_runs(
        [u('「'), u('ひ'), u('ら'), u('が'), u('な'), u('」')], known)]
    check('本人が書いている並びは繋ぐ', got, ['「', 'ひらがな', '」'])

    got = [x['text'] for x in _merge_kana_runs(
        [u('ひ'), u('ら'), u('が'), u('な'), u('を')], known)]
    check('助詞は巻き込まない', got, ['ひらがな', 'を'])

    got = [x['text'] for x in _merge_kana_runs(
        [u('あ'), u('い'), u('う'), u('え')], known)]
    check('根拠が無い並びは触らない', got, ['あ', 'い', 'う', 'え'])

    got = [x['text'] for x in _merge_kana_runs(
        [u('ひ'), u('ら'), u('が'), u('な')], None)]
    check('判定関数が無ければ触らない', got, ['ひ', 'ら', 'が', 'な'])

    got = [x['text'] for x in _merge_kana_runs(
        [u('ひ'), u('ら', 'fixed'), u('が'), u('な')], known)]
    check('補正が当たっている単位は繋がない',
          got, ['ひ', 'ら', 'が', 'な'])

    # --- 機能語だけの並びを繋ぐ（項目48-GL）---
    #
    # うにさんの指摘（2026-08-20）:「ひらがな部分は1文字で切れすぎ。
    # 漢字の単語はよいが、その間のひらがなは細切れになるので
    # 拾いにくく、またそれぞれの補正候補も大げさ」
    #
    # 実測（実機メモ200行）: 単位 3,245 のうち1文字のひらがなが
    # 961（30%）。ひらがなの連なり 586 か所のうち 190（32%）が
    # 3個以上に割れていた。
    from units import _merge_functional_runs

    def _run(texts, kinds=None, pos=None):
        at = 0
        out = []
        for i, t in enumerate(texts):
            k = (kinds or {}).get(i, 'plain')
            out.append({'text': t, 'base': t, 'reading': t, 'kind': k,
                        'detail': None, 'start': at, 'end': at + len(t),
                        'prev': '', 'next': '',
                        'pos': (pos or {}).get(i, '')})
            at += len(t)
        return out

    got = _merge_functional_runs(_run(['し', 'て', 'ください']))
    check('機能語だけの並びは1つにまとめる',
          [x['text'] for x in got], ['してください'])
    check('まとめた単位には印が付く（候補を出さない）',
          [bool(x.get('functional')) for x in got], [True])

    # **先頭の `に` は1文字で切る**（うにさんの指定・下の
    # 「に、で、は、も同様に」）。残りはまとめる。
    got = [x['text'] for x in
           _merge_functional_runs(_run(['に', 'なっ', 'て', 'い', 'ます']))]
    check('活用語尾の並びもまとめる（先頭の に は切る）',
          got, ['に', 'なっています'])

    # **内容語は巻き込まない。**
    got = [x['text'] for x in
           _merge_functional_runs(_run(['ひらがな', 'を', 'つかい', 'ます']))]
    check('内容語は巻き込まない（ひらがな・つかい）',
          got, ['ひらがな', 'を', 'つかい', 'ます'])

    # 1文字の助詞は、繋がらなくても**候補を出さない印**を付ける
    got = _merge_functional_runs(_run(['ひらがな', 'を', 'つかい', 'ます']))
    check('1文字の助詞にも印が付く',
          [bool(x.get('functional')) for x in got],
          [False, True, False, False])

    # 補正が当たっている単位は、まとめない（色と対応が崩れる）
    got = [x['text'] for x in _merge_functional_runs(
        _run(['し', 'て', 'ください'], {1: 'suspect'}))]
    check('補正が当たっている単位はまとめない',
          got, ['し', 'て', 'ください'])

    # **格助詞 が・を は1文字で切る**（うにさんの指定・2026-08-20
    # 「が、を1文字で切りましょう。それが正しい形です」）。
    # 前の内容語に付く助詞であって、うしろの塊の一部ではない。
    got = [x['text'] for x in
           _merge_functional_runs(_run(['が', 'できる', 'ように', 'します']))]
    check('が は1文字で切る（項目48-GL）',
          got, ['が', 'できるようにします'])

    got = [x['text'] for x in _merge_functional_runs(
        _run(['を', 'し', 'て', 'も'],
             pos={0: '助詞:格助詞', 1: '動詞:自立',
                  2: '助詞:接続助詞', 3: '助詞:係助詞'}))]
    check('を も1文字で切る', got, ['を', 'しても'])

    # まとまりの**途中**の `が`（接続助詞）は役目が違うので触らない
    got = [x['text'] for x in _merge_functional_runs(
        _run(['ます', 'が'], pos={0: '助動詞:*', 1: '助詞:接続助詞'}))]
    check('まとまりの途中の が は切らない', got, ['ますが'])

    # --- に・で・は・も も1文字で切る（うにさんの追加指定）---
    got = [x['text'] for x in _merge_functional_runs(
        _run(['これ', 'は', '正しく'],
             pos={0: '名詞:代名詞', 1: '助詞:係助詞', 2: '副詞:一般'}))]
    check('内容語のうしろの は は1文字で切る', got, ['これ', 'は', '正しく'])

    got = [x['text'] for x in _merge_functional_runs(
        _run(['て', 'も'], pos={0: '助詞:接続助詞', 1: '助詞:係助詞'}))]
    check('機能語のうしろの も は切らない（ても）', got, ['ても'])

    # --- 活用する語は、うしろの活用語尾と繋ぐ（見ています）---
    from units import _merge_stem_with_tail
    got = [x['text'] for x in _merge_stem_with_tail(_merge_functional_runs(
        _run(['見', 'て', 'い', 'ます'],
             pos={0: '動詞:自立', 1: '助詞:接続助詞',
                  2: '動詞:非自立', 3: '助動詞:*'})))]
    check('見ています は分けない（項目48-GL）', got, ['見ています'])

    # 名詞は繋がない（うにさんの「漢字の単語はよい」）
    got = [x['text'] for x in _merge_stem_with_tail(_merge_functional_runs(
        _run(['変更', 'し', 'て', 'ください'],
             pos={0: '名詞:サ変接続', 1: '動詞:自立',
                  2: '助詞:接続助詞', 3: '動詞:非自立'})))]
    check('名詞は活用語尾と繋がない（変更｜してください）',
          got, ['変更', 'してください'])

    got = [x['text'] for x in _merge_kana_runs(
        [u('たん'), u('ご')], lambda s: s == 'たんご')]
    check('1文字より長い単位は触らない', got, ['たん', 'ご'])

    # 2文字だけの組は繋がない（う＋え を 上 にしてしまわない）
    got = [x['text'] for x in _merge_kana_runs(
        [u('う'), u('え')], lambda s: s == 'うえ')]
    check('2文字の組は繋がない', got, ['う', 'え'])

    return all_ok


# ============================================================
# 検証レポート（2026-08-10）2-E / 2-F: 半角経路のガードの穴
# ============================================================
def test_halfwidth_guards():
    """
    半角経路が、正しく書いた英数字を壊さないか。

    **半角まわりは実機のメモにいちばんよく出る形**なので、
    「直ってほしい」より「触ってはいけない」を厚く確かめる。
    うにさん提示の変換例12件が全部通ることも、ここで押さえる。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import halfwidth as H
    import loanword as LW
    from vocabulary import VocabularyStore, find_known_readings_flex, dup_repair_enabled

    print('--- 検証レポート 2-E / 2-F（半角経路） ---')
    store = build_store()

    def conv(text):
        return H.correct_halfwidth(text, store, find_known_readings_flex)

    def romaji(text):
        return H.correct_romaji(text, store, find_known_readings_flex)

    # --- 2-E: 数字＋単位・版数・項目番号 ---
    # 数字のほうが英字より多いか同じなら、数値とみなす。
    for text in ('2.5kg', '12.5cm', '1.5L', '35mm', 'v1.1.0', '48-B.',
                 '33-b.', '3.5GHz', '1,980', '03-1234-5678', '1.2.3'):
        check(f'数値・単位は触らない（{text}）', conv(text), None)

    # 数字が英字より少ない並びは、今までどおり対象
    # （かな配列で日本語を打つと英字キーが優勢になる）。
    check('英字が優勢なら対象に残る（md@i(4l)h）',
          conv('md@i(4l)h'), '文字入力')

    # --- 2-F: 英単語がかなに化ける ---
    # 記号がまったく無い英小文字だけの並びは、かな配列の経路の対象外。
    for text in ('after', 'ctypes', 'before', 'response', 'corrected',
                 'change', 'window', 'tkinter'):
        check(f'記号の無い英単語は触らない（{text}）', conv(text), None)
    # 前後の記号（Markdown の ** や読点）は剥がしてから見る
    for text in ('**after', '**ctypes', "'corrected',", '(response)'):
        check(f'前後の記号を剥がしても英単語（{text}）', conv(text), None)

    # うにさん提示の半角入力の実例は、すべて記号を含む。
    for text in ('md@i(4l)h', 'qyb@kzut@l', '^ytyx;ue', 'c4w@r,',
                 'bkzg@f', 'i(4l)hoy', 'fythkjji(4l)h', 'hd(4r.bsw@',
                 'md[ki)4l)h', 'cmcmbk:\\rf'):
        check(f'記号を含む実例は対象に残る（{text}）',
              H.looks_like_halfwidth_input(text), True)

    # --- 2-F: ローマ字経路 ---
    # 戻したかなが丸ごと説明できるときだけ採る。
    check('ローマ字べた打ちは通る（mojinyuuryoku）',
          romaji('mojinyuuryoku'), '文字入力')
    check('ローマ字べた打ちは通る（gakkou）', romaji('gakkou'), '学校')
    check('たまたまローマ字として読める英単語は触らない（change）',
          romaji('change'), None)

    # --- 2-A の残り: 語尾だけが違う形は打ち間違いではない ---
    check('change と changed は同じ語',
          LW._same_word_family('change', 'changed'), True)
    check('window と windows は同じ語',
          LW._same_word_family('window', 'windows'), True)
    check('receives と received は同じ語',
          LW._same_word_family('receives', 'received'), True)
    check('study と studies は同じ語',
          LW._same_word_family('study', 'studies'), True)
    check('planetarium と plaqnetarium は別の語',
          LW._same_word_family('planetarium', 'plaqnetarium'), False)

    estore = VocabularyStore()
    for _ in range(60):
        estore.add('en:changed', 'changed', '英語')
        estore.add('en:windows', 'Windows', '英語')
        estore.add('en:buttons', 'buttons', '英語')
    for typed in ('change', 'window', 'button'):
        check(f'語尾違いへは直さない（{typed}）',
              LW.fix_english_word(typed, estore), None)

    # 語尾違いでない誤字は、今までどおり直る
    pstore = VocabularyStore()
    LW.relearn_english_from_texts(
        ['I like the Planetarium. Planetarium again.'], pstore)
    check('語尾違いでない誤字は直る（Palnetarium）',
          LW.fix_english_word('Palnetarium', pstore), 'Planetarium')

    # --- 誤字を並べた行があるメモでも、正しい綴りを見つける ---
    # 実機・2026-08-11: 試験用に誤字を7種類並べた行があり、正しい
    # `Planetarium` は1回しか書かれていなかった。回数の順に覚えると
    # 誤字が先に入り、正しい綴りが「その誤字の打ち間違い」として
    # 捨てられ、**以後どの誤字も直らなくなった**。
    # 誤字は正しい綴りの周りに集まるので、**1文字違いの仲間が
    # いちばん多いもの**を先に覚える。
    memo = ['・以下は「Planetarium」に自動補正します。',
            'lanetarium', 'Panetarium', 'Pllanetarium',
            'Planetariumm', 'Pklanetarium', 'lanetarium']
    hstore = VocabularyStore()
    LW.relearn_english_from_texts(['\n'.join(memo)], hstore)
    check('誤字が多くても正しい綴りだけを覚える',
          sorted(LW._english_vocabulary(hstore)), ['planetarium'])
    for typed in ('lanetarium', 'Panetarium', 'Pllanetarium',
                  'Planetariumm', 'Pklanetarium'):
        check(f'並べた誤字が直る（{typed}）',
              LW.fix_english_word(typed, hstore),
              None if typed in ('Pllanetarium', 'Planetariumm') and not dup_repair_enabled() else 'Planetarium')
    check('正しい綴りは触らない',
          LW.fix_english_word('Planetarium', hstore), None)

    # --- 打鍵のたびに使用回数が増えない（実機・2026-08-11）---
    # learn_english_words は打鍵が落ち着くたびにメモ全文で呼ばれる。
    # 呼ばれるたびに store.add していたので、**2回打鍵を止めただけで
    # どの誤字も own >= 2（＝何度も書いている語＝正しい）に化け、
    # 英単語の補正が丸ごと効かなくなっていた**。
    istore = VocabularyStore()
    memo2 = 'I opened the Planetarium window. Planetarium again.'
    first = LW.learn_english_words(memo2, istore)
    before = {w: LW._english_count(istore, w)
              for w in LW._english_vocabulary(istore)}
    for _ in range(9):
        LW.learn_english_words(memo2, istore)
    after = {w: LW._english_count(istore, w)
             for w in LW._english_vocabulary(istore)}
    check('1回目は新しい語を覚える', first > 0, True)
    check('2回目以降は何も覚えない',
          LW.learn_english_words(memo2, istore), 0)
    check('10回呼んでも使用回数が増えない', after, before)
    check('新しい語が出てくれば、それだけ覚える',
          LW.learn_english_words(memo2 + ' rendered', istore), 1)

    # 覚え直しは、メモに**2回以上**出てきた語を「立った語」にする
    # （どの語も立たないと own >= 2 の判定が死ぬ）。
    #
    # ★★ 回数そのものは記録しない（項目48-QG・2026-09-05）。
    # `relearn_english_from_texts` は出現回数ぶん `store.add` を
    # 呼ぶので、**2回以上出た語は solid（＝メモリ上の count 2）**、
    # 1回だけの語は立たない（count 1）。`own >= 2` の門は、
    # 「何度も書いている語＝正しい」という意味のまま生き残る。
    cstore = VocabularyStore()
    LW.relearn_english_from_texts(['charlie ' * 5 + 'foxtrot'], cstore)
    check('何度も書いた語は立つ／1回だけの語は立たない',
          (LW._english_count(cstore, 'charlie'),
           LW._english_count(cstore, 'foxtrot')), (2, 1))
    check('回数そのものは残らない（5回書いても 2 のまま）',
          LW._english_count(cstore, 'charlie') <= 2, True)

    # 記号がくっついた英字は語として覚えない
    # （`P:lanetarium` から `lanetarium` を覚えていた）。
    check("':' がくっついた英字は覚えない",
          LW.find_english_runs('P:lanetarium'), [])
    check("':' の後ろでも覚えない",
          LW.find_english_runs('Pl:anetarium'), [])
    check('ふつうの英単語は今までどおり拾う',
          LW.find_english_runs('the Planetarium is'),
          [(4, 15, 'Planetarium')])

    return all_ok


# ============================================================
# 検証レポート（2026-08-10）2-D / 3-A / 3-B / 3-D
# ============================================================
def test_report_small_fixes():
    """
    検証レポートの小粒な指摘4件の回帰テスト。

    どれも「条件が揃うと壊れる」種類で、実機のメモでは表に
    出ていなかったもの。**表に出ていないからこそ、テストで
    留め金を掛けておかないと静かに戻る。**
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import unicodedata
    import corrector as C
    from morphology import normalize_marks

    print('--- 検証レポート 2-D / 3-A / 3-B / 3-D ---')

    # --- 2-D: 分解済み（NFD）のカタカナから濁点・半濁点が消える ---
    # macOS 由来のファイル名やクリップボードを貼ると起きる。
    # 合成表がひらがなの鍵しか持っておらず、合成先が見つからないと
    # 濁点そのものを捨てていた（バックアップ → ハックアッフ）。
    for word in ('バックアップ', 'ガンダム', 'プログラミング',
                 'ドラッグ', 'パワー', 'ヴァイオリン'):
        nfd = unicodedata.normalize('NFD', word)
        check(f'NFD のカタカナで濁点が消えない（{word}）',
              normalize_marks(nfd), word)
    for word in ('ばっくあっぷ', 'ぱわー', 'どらっぐ'):
        nfd = unicodedata.normalize('NFD', word)
        check(f'NFD のひらがなも今までどおり（{word}）',
              normalize_marks(nfd), word)

    # 合成できない濁点は今までどおり落とす（濁点キーの誤打）。
    check('合成できない濁点は落とす（かなの場合）',
          normalize_marks('こ゜'), 'ご')
    check('合成しようのない濁点は消える',
          normalize_marks('あ゙'), 'あ')

    # --- わざと単体で書いた濁点は消さない（2026-08-11・項目48-AA）---
    # うにさんのメモにある JISかな配列の対応表（`@ ⇒ ゛`）が
    # `@ ⇒ ` に化けていた。**正しく書いたものを消していた。**
    # 落とす根拠は「かなを打った直後に濁点キーを叩いた」ことなので、
    # 前がかなでなければ根拠が無い。
    check('記号の後ろの濁点は残す', normalize_marks('@ ⇒ ゛'), '@ ⇒ ゛')
    check('記号の後ろの半濁点は残す',
          normalize_marks('[ ⇒ ゜'), '[ ⇒ ゜')
    check('行頭の濁点は残す', normalize_marks('゛あいう'), '゛あいう')
    check('英字の後ろの濁点は残す', normalize_marks('A゛'), 'A゛')
    check('かなの後ろは今までどおり落とす', normalize_marks('ん゛'), 'ん')
    check('合成できるものは今までどおり合成する',
          normalize_marks('たんこ゛のつながり'), 'たんごのつながり')

    # --- 打つ順番が入れ替わった印（2026-08-11・項目48-AO）---
    # うにさんの指定:「ふ、半濁点、あ の3つの順番が入れ替わり、
    # ふ、あ、半濁点となったので、他の順序入れ替えと同等の扱い」。
    # **既定では今までどおり落とす。** 跨いだ合成は、落としたほうで
    # 補正が届かなかったときだけ correct_line が呼び直す
    # （先に跨ぐと `たん゛子` が `だん子→担子` に化ける）。
    check('既定では今までどおり印を落とす',
          normalize_marks('フア゜ラネタリウム'), 'フアラネタリウム')
    check('跨いで合成すると順序の入れ替わりが解ける',
          normalize_marks('フア゜ラネタリウム', swap_across=True),
          'プアラネタリウム')
    check('跨いでも間の1打は消さない',
          normalize_marks('たん゛子', swap_across=True), 'だん子')
    check('跨ぐときも記号の後ろの印は残す',
          normalize_marks('@ ⇒ ゛', swap_across=True), '@ ⇒ ゛')
    check('跨げる相手が無ければ今までどおり落とす',
          normalize_marks('ん゛', swap_across=True), 'ん')

    # 表を二重に持たない作りになっているか（片方だけ直る事故の防止）。
    import morphology as M
    check('濁点の合成表にカタカナが入っている',
          (M._DAKUTEN_COMPOSE.get('カ'), M._DAKUTEN_COMPOSE.get('ウ')),
          ('ガ', 'ヴ'))
    check('半濁点の合成表にカタカナが入っている',
          M._HANDAKUTEN_COMPOSE.get('ハ'), 'パ')

    # --- 3-D: 到達しない分岐を落とした ---
    # find_hiragana_runs が返す並びに '゛' '゜' は入らない
    # （is_hiragana が False）ので、表に置いても意味が無かった。
    check("濁点キーの読み替え表に '゜' を持たない",
          '゜' in C._DAKUTEN_TYPO_CHARS, False)
    check("半濁点キーの読み替え表に '゛' を持たない",
          '゛' in C._HANDAKUTEN_TYPO_CHARS, False)
    check('生きている読み替えは残っている',
          (C._DAKUTEN_TYPO_CHARS, C._HANDAKUTEN_TYPO_CHARS),
          (('せ',), ('む',)))

    # --- 3-A: 再帰呼び出しで input_method が落ちない ---
    # 濁点が分離した文字を1つ含む行で、内側の呼び出しに
    # input_method を渡し忘れると既定の 'kana' に落ちる。
    # ローマ字入力の人だけ補正が効かなくなる。
    import inspect
    src = inspect.getsource(C.correct_line)
    inner = src[src.find('inner = correct_line('):]
    inner = inner[:inner.find(')\n') + 1]
    check('濁点合成の再帰に input_method を渡している',
          'input_method=input_method' in inner, True)

    # --- 3-B: janome の sys.exit を止めている ---
    # `sys.exit` は SystemExit で、`except Exception` では捕まらない。
    # 素通りすると、起動が無言で失敗する／打鍵の3秒後に無言で消える。
    import janome_import as JI
    for name in ('learn_from_text', 'repair_conjugated_fragments'):
        fn_src = inspect.getsource(getattr(JI, name))
        check(f'{name} が SystemExit を受け止めている',
              'except SystemExit' in fn_src, True)

    return all_ok


# ============================================================
# 方針2: 同音異義語の文脈置換（_homophone_by_context）
# ============================================================
def test_homophone_by_context():
    """
    正しく書けている実在語を、周りの語だけを根拠に置き換える経路。

    このエンジンで唯一「明確な誤りだと言えないもの」を直す道なので、
    **通す条件より、通さない条件のほうを厚く**確かめる。
    数値は実機のメモ全文で測って決めたもの（corrector.py の
    _HOMOPHONE_MIN_MARGIN / _HOMOPHONE_MIN_USAGE のコメント参照）。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import corrector as C
    from vocabulary import VocabularyStore
    from context_vec import ContextVectorStore

    print('--- 方針2（同音異義語の文脈置換） ---')

    store = VocabularyStore()
    for _ in range(30):
        store.add('せんたく', '選択', 'その他')      # 使用実績あり
        store.add('めいし', '名詞', 'その他')
    for _ in range(4):
        store.add('いか', '医科', 'その他')           # 実績が乏しい語

    cv = ContextVectorStore()
    # 「選択」は範囲・操作と、「名詞」は文字・品詞と一緒に出てくる、
    # というメモを書いた状態を作る。「洗濯」「名刺」は出てこない。
    for _ in range(6):
        cv.observe_line(['範囲', '選択', '操作', '解除'])
        cv.observe_line(['選択', '操作', '範囲', '指定'])
        cv.observe_line(['文字', '名詞', '品詞', '解析'])
        cv.observe_line(['名詞', '品詞', '文字', '判定'])

    def pick(surface, reading, around):
        return C._homophone_by_context(surface, reading, store, cv, around)

    # --- 通ってほしいもの ---
    check('周りが範囲・操作なら 洗濯 → 選択',
          pick('洗濯', 'せんたく', ['範囲', '操作']),
          ('選択', 'その他', C.EVIDENCE_VECTOR))
    check('周りが文字・品詞なら 名刺 → 名詞',
          pick('名刺', 'めいし', ['文字', '品詞']),
          ('名詞', 'その他', C.EVIDENCE_VECTOR))

    # --- 通ってはいけないもの ---
    check('周りに手がかりが無ければ触らない',
          pick('洗濯', 'せんたく', ['天気', '洗剤']), None)
    check('周りの語が空なら触らない',
          pick('洗濯', 'せんたく', []), None)
    check('文脈ベクトルが無ければ触らない',
          C._homophone_by_context('洗濯', 'せんたく', store, None,
                                  ['範囲', '操作']), None)
    check('置き換え先の使用実績が乏しければ触らない',
          pick('以下', 'いか', ['範囲', '操作']), None)
    check('同じ読みに別の表記が無ければ触らない',
          pick('選択', 'せんたく', ['範囲', '操作']), None)

    # 送り仮名を含む語は、**複合動詞の一部なら触らない**（項目48-IQ）。
    # 「書き換わりました」の 換わり を 変わり にしてしまう誤爆が
    # 実機のメモで出た（48-DZ）。`書き換わる` が表に在るので守られる。
    # 複合でない `換わり` は、共起が支持すれば直す（初期状態の同音の道）。
    for _ in range(30):
        store.add('かわり', '変わり', 'その他')
    # 活用形の道は共通の相手3語以上を要る（項目48-IQ）ので、
    # 共起の材料を少し厚くしておく。
    for _ in range(6):
        cv.observe_line(['文字', '変わり', '補正', '表示', '変換', '入力'])
    check('複合動詞の一部（書き換わり）は触らない',
          C._homophone_by_context('換わり', 'かわり', store, cv,
                                  ['文字', '補正'],
                                  attest_text='補正の文字列に書き換わりました。'),
          None)
    check('複合でなければ共起で 換わり → 変わり',
          C._homophone_by_context('換わり', 'かわり', store, cv,
                                  ['文字', '補正'],
                                  attest_text='文字が換わりました。'),
          ('変わり', 'その他', C.EVIDENCE_VECTOR))

    for _ in range(30):
        store.add('たんご', '単語', 'その他')
    check('カタカナを含む語は対象外',
          pick('タン語', 'たんご', ['文字', '品詞']), None)
    check('ひらがなだけの語は対象外',
          pick('めいし', 'めいし', ['文字', '品詞']), None)

    # 字数が違う置き換えはしない（同音でも別の語の可能性が上がる）。
    for _ in range(30):
        store.add('こうえん', '公園', 'その他')
        store.add('こうえん', '後援会', 'その他')
    for _ in range(6):
        cv.observe_line(['子供', '公園', '散歩', '広場'])
    check('字数が違う表記へは置き換えない',
          pick('講演', 'こうえん', ['子供', '散歩']),
          ('公園', 'その他', C.EVIDENCE_VECTOR))

    # 拮抗しているときは決め打ちしない（既定の 0.08 より厳しい
    # _HOMOPHONE_MIN_MARGIN を使っていることの確認）。
    cv2 = ContextVectorStore()
    for _ in range(6):
        cv2.observe_line(['資料', '選択', '洗濯', '準備'])
    check('僅差では決め打ちしない',
          C._homophone_by_context('洗濯', 'せんたく', store, cv2,
                                  ['資料', '準備']), None)

    return all_ok


# ============================================================
# 項目48-DZ: 活用形の同音を、並記があるときだけ直す
# ============================================================
def test_homophone_conjugated():
    """
    **漢字＋送り仮名**の語を、同じ読みの別表記へ直す経路（案A）。

    語彙は活用する語を**基本形でしか持っていない**
    （`janome_import.py` の設計判断）。一方メモから学んだ語は
    活用形のまま入る。この非対称のせいで `直り` のような
    「直す先」が語彙に無く、原理的に直せない形があった。

    ここでは語彙を増やさず、**比べるときだけ**送り仮名を合わせて
    活用形を作る（`打つ` ＋ `売っ` の `っ` → `打っ`）。

    **共起では裁けないことを実測してある**:
        治り 0.1485 対 直る 0.0309 ／ 映る 0.0357 対 移る 0.0133
        （**直すべき側のほうが点が低い**。符号が逆）
        換わり → 変わり は +0.211 で敷居 0.12 を超える（誤爆）
    そこで軸を変え、**直した結果が同じ行に文字通り書かれている
    ときだけ**通す（並記の関門。項目38・1-F と同じ形）。

    **通す条件より、通さない条件のほうを厚く**確かめる。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import corrector as C
    from vocabulary import VocabularyStore
    from context_vec import ContextVectorStore

    print('--- 活用形の同音（並記の関門＋共起・既定は入） ---')

    # 既定は**入**（項目48-IQ・2026-08-22・うにさんの指定「初期状態を
    # 重要視」）。並記が無ければ共起で測る。ここでは明示して入れる。
    _saved = C._CONJ_HOMOPHONE
    C._CONJ_HOMOPHONE = True

    store = VocabularyStore()
    for _ in range(40):
        store.add('うつ', '打つ', 'その他')        # 基本形だけ在る
        store.add('かわり', '変わり', 'その他')
    for _ in range(4):
        store.add('うる', '売る', 'その他')        # 実績が乏しい
    cv = ContextVectorStore()
    # 活用形の道は共通の相手3語以上を要る（項目48-IQ）
    for _ in range(6):
        cv.observe_line(['文字', '打つ', '入力', '補正', 'キー', '変換'])

    def pick(surface, reading, line, around=('文字', '入力')):
        return C._homophone_by_context(surface, reading, store, cv,
                                       list(around), attest_text=line)

    # --- 通ってほしいもの ---
    # `売る` は4回使われている（語彙に裏打ちあり）ので、並記の関門は
    # 向きを決めない。**共起**（文字・打つ）が 打っ を支持するので直る。
    check('同じ行に並記があれば 売っ → 打っ',
          pick('売っ', 'うっ', '売った文字 ⇒ 打った文字'),
          ('打っ', 'その他', C.EVIDENCE_VECTOR))
    check('送り仮名は元の形を残す（打つ ではなく 打っ）',
          (pick('売っ', 'うっ', '売った文字 ⇒ 打った文字') or (None,))[0],
          '打っ')

    # 並記が無くても、**共起が支持すれば直す**（項目48-IQ。
    # 初期状態の話題のまとまりがこの共起にあたる）。
    check('並記が無くても共起が支持すれば 売っ → 打っ',
          pick('売っ', 'うっ', '売った文字だけの行'),
          ('打っ', 'その他', C.EVIDENCE_VECTOR))
    check('共起の手がかりが無ければ触らない',
          pick('売っ', 'うっ', '売った文字だけの行', around=('天気', '洗剤')),
          None)

    # --- 通ってはいけないもの ---
    check('並記が無ければ 換わり → 変わり にしない（実機の誤爆）',
          pick('換わり', 'かわり',
               '補正の文字列に書き換わりました。',
               around=('文字', '補正')), None)
    check('**向きが逆にならない**（並記は左右どちらからも成り立つ）',
          pick('打っ', 'うっ', '売った文字 ⇒ 打った文字'), None)
    check('置き換え先の実績が乏しければ触らない（打っ → 売っ にしない）',
          pick('打っ', 'うっ', '打った文字 ⇒ 売った文字'), None)
    check('送り仮名が無い語はこの経路に入らない',
          pick('打', 'う', '打 ⇒ 売'), None)
    check('語幹がカタカナなら触らない',
          pick('ウっ', 'うっ', 'ウった ⇒ 打った'), None)
    check('送り仮名が長すぎる形は触らない',
          pick('売っため', 'うっため', '売っため ⇒ 打っため'), None)
    check('読みの末尾が送り仮名と合わない形は触らない',
          # 周りの語は設計35（対の表・48-JJ）の手がかり（文字・入力）を
          # 含まないものにする——含むと表が先に（正しく）直して、
          # この門の見張りにならない
          pick('売っ', 'うった', '売った文字 ⇒ 打った文字',
               around=('天気', '洗剤')), None)
    check('字数の違う語幹へは置き換えない（打ち込っ は候補にならない）',
          (pick('売っ', 'うっ', '売った ⇒ 打ち込った') or (None,))[0],
          '打っ')
    check('栓を切れば経路ごと消える',
          # こちらも手がかりの無い周りの語で（設計35 は別の設計で、
          # この栓の外に居る）
          (lambda: (setattr(C, '_CONJ_HOMOPHONE', False),
                    pick('売っ', 'うっ', '売った文字 ⇒ 打った文字',
                         around=('天気', '洗剤')),
                    setattr(C, '_CONJ_HOMOPHONE', True))[1])(), None)

    C._CONJ_HOMOPHONE = _saved
    check('既定は入（項目48-IQ）', C._CONJ_HOMOPHONE, True)

    return all_ok


# ============================================================
# 項目48-EG: 記号のつもりで打った、同じキーのかな
# ============================================================
def test_samekey_punctuation():
    """
    `（→ゆ` の**逆向き**。うにさんの指定（2026-08-16）:

        おおごえぬ      ⇒ おおごえ！   （かな入力・1 のキー）
        しつもんめ      ⇒ しつもん？   （かな入力・/ のキー）
        おわりのくてんる  ⇒ おわりのくてん。（かな入力・. のキー）
        おおごえ１      ⇒ おおごえ！   （ローマ字入力・Shift の押し忘れ）
        しつもん・      ⇒ しつもん？   （ローマ字入力）

    **危ないのは「る」と「め」**（おしえ**る**・むす**め**）。
    語彙＋辞書の 22,705 語で巻き込む数を数えて門を決めた:

        前が既知語だけ ......................... 90件
        ＋末尾が独立した語として切れる ........... 16件
        ＋全体が辞書に載っていない ................ 1件
        ＋前は末尾の既知語でもよい（ゆるめた）....... 4件

    **通す条件より、通さない条件のほうを厚く**確かめる。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import corrector as C
    from vocabulary import VocabularyStore

    print('--- 記号のつもりで打った同じキーのかな ---')

    store = VocabularyStore()
    for _ in range(30):
        store.add('おおごえ', '大声', 'その他')
        store.add('たいせい', '大声', 'その他')
        store.add('しつもん', '質問', 'その他')
        store.add('くてん', '句点', 'その他')
        store.add('かんがえる', '考える', 'その他')
        store.add('むすめ', '娘', 'その他')

    def tok(text):
        """末尾が独立して切れるかだけを見る、ごく簡単な作り物。

        janome の無い環境でも門の形を確かめられるようにする。
        `かんがえる` は1語、それ以外は1文字ずつに切れることにする。
        """
        if text == 'かんがえる':
            return [(text, '動詞:自立', text, 0, len(text), True)]
        return [(c, '名詞:一般', c, i, i + 1, True)
                for i, c in enumerate(text)]

    def fix(line):
        got = C._fix_samekey_punctuation(line, store, tok, None)
        if got is None:
            return None
        return line[:got[0]] + got[2] + line[got[1]:]

    # --- 通ってほしいもの ---
    check('おおごえぬ → おおごえ！', fix('おおごえぬ'), 'おおごえ！')
    check('しつもんめ → しつもん？', fix('しつもんめ'), 'しつもん？')
    check('おおごえ１ → おおごえ！', fix('おおごえ１'), 'おおごえ！')
    check('しつもん・ → しつもん？', fix('しつもん・'), 'しつもん？')
    check('手前が「末尾だけ既知語」でも通る（くてん）',
          fix('おわりのくてんる'), 'おわりのくてん。')
    check('文の途中にあっても行末なら直す',
          fix('これは おおごえぬ'), 'これは おおごえ！')

    # --- 末尾の連続（2026-08-16・うにさん指定）---
    # `！？` を打とうとして両方とも押し損なう形。3連まで。
    check('ぬめ → ！？', fix('おおごえぬめ'), 'おおごえ！？')
    check('めぬ → ？！', fix('しつもんめぬ'), 'しつもん？！')
    check('ぬぬ → ！！', fix('おおごえぬぬ'), 'おおごえ！！')
    check('ぬぬめ → ！！？', fix('おおごえぬぬめ'), 'おおごえ！！？')
    check('めめ → ？？', fix('しつもんめめ'), 'しつもん？？')
    check('１ぬ → ！！（全角数字との混じり）',
          fix('大声１ぬ'), '大声！！')
    check('め・ → ？？（かなと・の混じり）',
          fix('しつもんめ・'), 'しつもん？？')
    check('4連は直さない（3連まで）', fix('おおごえぬぬぬぬ'), None)

    # --- 通ってはいけないもの ---
    check('全体が語彙にあるなら触らない（かんがえる）',
          fix('かんがえる'), None)
    check('全体が語彙にあるなら触らない（むすめ）',
          fix('むすめ'), None)
    check('末尾が語の一部なら触らない',
          C._fix_samekey_punctuation(
              'かんがえる', VocabularyStore(), tok, None), None)
    # `終わりの句点る` は `点る`（ともる）が実在語で `る` を
    # 持って行くので**直らない**。拾おうとしてゆるめると、
    # 巻き込む正しい語が 1件 → 14件（つかれる・にえる・くわせる…）
    # に増えたので、ここはゆるめない（2026-08-16 に測って決めた）。
    check('語の切れ目をまたいで貼り付いた形は拾わない',
          C._fix_samekey_punctuation(
              '終わりの句点る', store,
              lambda t: [('終わり', '', '', 0, 3, True),
                         ('の', '', '', 3, 4, True),
                         ('句', '', '', 4, 5, True),
                         ('点る', '', '', 5, 7, True)], None), None)
    check('手前が既知語でなければ触らない', fix('ぬるぬるぬ'), None)
    check('行末が対象の文字でなければ触らない', fix('おおごえか'), None)
    check('短すぎる並びは触らない', fix('えぬ'), None)
    # **漢字に変換したあとの形が本命**（大声→Shift+1 を押し損なう）。
    # 読みでも表記でも引けること。
    check('漢字のあとでも直る（大声ぬ）', fix('大声ぬ'), '大声！')
    check('半角の記号は表に入れない（. / 1）',
          [c for c in '.  / 1' if c in C._SAMEKEY_PUNCT], [])
    check('表は かな と全角だけ',
          sorted(C._SAMEKEY_PUNCT), sorted(['ぬ', '１', 'め', '・', 'る']))

    # --- 括弧のつもりで打った同じキーのかな（゜…む／ゆ…よ）---
    # 開きと閉じが**対で在るときだけ**直す（2026-08-16）。
    print('--- 括弧のつもりで打った同じキーのかな ---')
    for _ in range(30):
        store.add('かぎ', 'かぎ', 'その他')
        store.add('かっこ', 'かっこ', 'その他')
        store.add('まるい', 'まるい', 'その他')

    def bfix(line):
        got = C._fix_kana_brackets(line, store, tok, None)
        if not got:
            return None
        out = list(line)
        for _s, _e, _r in got:
            out[_s] = _r
        return ''.join(out)

    check('゜…む → 「…」', bfix('゜かぎかっこむ'), '「かぎかっこ」')
    check('ゆ…よ → （…）', bfix('ゆまるいかっこよ'), '（まるいかっこ）')
    check('対でなければ触らない（閉じだけ）', bfix('かぎかっこむ'), None)
    check('対でなければ触らない（開きだけ）', bfix('ゆまるいかっこ'), None)
    # ゜は単体で本文に立てない文字なので、対がそろえば中身は問わない
    # （括弧を先に判定して、中身の補正はあとで考える。2026-08-16）
    check('゜の対は中身1文字でも開く', bfix('゜はむ'), '「は」')
    check('゜の対は中身に閉じが混ざってもよい',
          bfix('゜はむむ'), '「はむ」')
    check('閉じが IME でカタカナになった形（ム）も受ける',
          bfix('゜カギカッコム'), '「カギカッコ」')
    check('゜の対は敷き詰めを求めない', bfix('゜ぬぬぬぬむ'),
          '「ぬぬぬぬ」')
    for _ in range(30):
        store.add('いい', 'いい', 'その他')
    check('ゆ…よ は中身が語なら開く（いい）', bfix('ゆいいよ'), '（いい）')
    check('中身が助詞で始まるなら開かない（ゆ＝名詞の湯）',
          bfix('ゆがまるいよ'), None)
    # --- 行の途中の語連続（2026-08-16）---
    check('行の途中（括弧の中）でも直す',
          C._fix_samekey_punctuation_all('（おおごえぬ）', store, tok,
                                         None),
          [(5, 6, '！')])
    check('行の途中に対象が無ければ何もしない',
          C._fix_samekey_punctuation_all('かんがえる、むすめ', store,
                                         tok, None), [])

    # --- 8…9 の半角括弧（8ok9 → (ok)）---
    check('8ok9 → (ok)',
          C._fix_ascii_brackets('8ok9', store),
          [(0, 1, '('), (3, 4, ')')])
    check('8x9（1文字）は触らない',
          C._fix_ascii_brackets('8x9', store), [])
    check('知らない綴りは触らない',
          C._fix_ascii_brackets('8ab9', store), [])
    check('前後に英数字が続くなら触らない（0x8ab9）',
          C._fix_ascii_brackets('0x8ab9', store), [])

    check('ゆが語の一部（ゆめ 等）なら開かない',
          C._fix_kana_brackets(
              'ゆめかっこよ', store,
              lambda t: [('ゆめ', '名詞:一般', 'ゆめ', 0, 2, True),
                         ('かっこ', '名詞:一般', 'かっこ', 2, 5, True),
                         ('よ', '助詞:終助詞', 'よ', 5, 6, True)],
              None), [])

    return all_ok


# ============================================================
# 項目48-r/48-s: カタカナ語・英単語・濁点キーの打ち間違い
# ============================================================
def test_map_column():
    """
    統合表示の自動反映で、カーソルの桁を読み替える（項目48-v）。

    画面なしで確かめられるよう、純粋関数に切り出してある。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    # tkinter の無い環境でも動かせるよう、app.py から
    # この関数の定義だけを取り出して読み込む（既存のテストと同じ手）。
    _src = open('app.py', encoding='utf-8').read()
    _start = _src.index('def map_column(')
    _end = _src.index('\ndef ', _start + 10)
    _ns = {}
    exec(_src[_start:_end], _ns)
    map_column = _ns['map_column']

    # 行末に居たら、新しい行末へ
    check('行末はそのまま行末',
          map_column('プセネタリウム', 'プラネタリウム', 7), 7)
    check('長さが変わっても行末は行末',
          map_column('プネタリウム', 'プラネタリウム', 6), 7)
    # 行頭は行頭
    check('行頭は行頭', map_column('あいう', 'かきく', 0), 0)
    # 直した箇所より後ろに居たら、そのぶんずれる
    check('直した箇所の後ろはずれる',
          map_column('プネタリウムに行く', 'プラネタリウムに行く', 8), 9)
    # 1文字を1文字に置き換えた場合、その後ろの桁は動かない
    check('1文字の置き換えでは桁が動かない',
          map_column('プセネタリウム', 'プラネタリウム', 2), 2)
    # 複数文字が1文字になった箇所の**中**に居たら、その終わりへ
    check('直した箇所の中は、その終わりへ',
          map_column('abcXYZdef', 'abcQdef', 5), 4)
    # 変わっていない行は動かない
    check('変わっていなければ動かない',
          map_column('そのまま', 'そのまま', 2), 2)
    # 短くなる場合
    check('短くなっても行末は行末',
          map_column('ププラネタリウム', 'プラネタリウム', 8), 7)
    return all_ok
