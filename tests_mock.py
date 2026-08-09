# CorrectNote — かな入力誤字補正メモ帳
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
janome の実挙動を再現したモックと、補正エンジンの回帰テスト。

janome を入れられない環境でも、実機で起きた不具合を
再現・検証できるようにするためのもの。

    py tests_mock.py
"""

import corrector as C
from vocabulary import VocabularyStore, find_known_readings_flex
from seed_vocabulary import load_seed


def build_store(extra=()):
    store = VocabularyStore()
    load_seed(store)
    for reading, surface in extra:
        store.add(reading, surface, 'その他')
        entry = store._by_reading.get(reading, {}).get(surface)
        if entry:
            entry['count'] = 2
    return store


# (表記, 品詞:細分類, 読み, janomeが辞書から読みを引けたか)
# 実機の janome が返す品詞細分類・読みの有無を再現している。
WORDS = {
    # 実 janome は「変わります」の「わります」だけを渡されても
    # 「わり（名詞・ワリ）＋ます」と読める。この分割を模しておく
    # （「変わります」の途中に誤検知の色が付いた実機報告への対応。
    #   corrector 側は _looks_like_valid_japanese で読める窓を
    #   触らないようにしている）。
    'わり': ('名詞:一般', 'わり', True),
    # 実 janome は「取り違え」を動詞「取り違える」の連用形として
    # 1語で読める（トリチガエ）。モックがこれを1文字ずつの未知語に
    # すると、漢字塊「取り違」の送り仮名込み実在チェック
    # （looks_like_real_word('取り違え')）が実機と食い違い、
    # 「取り違え」→「種類え」の誤爆を再現・防止できない。
    '取り違え': ('動詞:自立', 'とりちがえ', True),
    # 実 janome はこれらを読みの確定した語（の並び）として読める。
    # mock が1語の未知語に潰すと、実機では起きない
    # 「誤補正→北西」「効果大→近代」「とみなす→とない」という
    # 誤爆が mock でだけ再現され、検証の物差しが狂う。
    '誤': ('接頭詞:名詞接続', 'ご', True),
    '補正': ('名詞:サ変接続', 'ほせい', True),
    '効果': ('名詞:一般', 'こうか', True),
    '大': ('名詞:接尾', 'だい', True),
    'みなす': ('動詞:自立', 'みなす', True),
    # 実 janome は連体詞「あらゆる」を1語（読み確定）で読める。
    # mock が未知語にすると、実機では _looks_like_valid_japanese が
    # 守る「あらゆる」が、mock でだけ「あわせる」に化ける。
    'あらゆる': ('連体詞:', 'あらゆる', True),
    # 実 janome が読める複合語の部品。mock が未知語にすると、
    # 実機では looks_like_real_word が守る「タブ機能」「キー入力」
    # 「ローマ字入力」が mock でだけ壊れる（1-C の検証で判明）。
    'タブ': ('名詞:一般', 'たぶ', True),
    '機能': ('名詞:サ変接続', 'きのう', True),
    'キー': ('名詞:一般', 'きー', True),
    '入力': ('名詞:サ変接続', 'にゅうりょく', True),
    'ローマ字': ('名詞:一般', 'ろーまじ', True),
    # 実 janome はこれらを読みの確定した語（の並び）として読める。
    # 1-D の検証に必要: 「カニ打ち」「叶う父」「かな地腕」は実機では
    # 実在語の並びとして読めてしまい、looks_like_real_word が守る側に
    # 回る。mock がこれらを未知語に潰すと、実機で必要な
    # 「読める並びを文脈の裏付けつきで直す」経路がローカルで
    # 検証できない（逆に、実機で起きない誤爆がローカルでだけ出る）。
    # 1-F の検証に必要: 実機の janome では 該当あの範囲・クリック化
    # ドラッグ・差釣れません・説明ぶん がいずれも実在語の並びとして
    # 読めてしまう（該当/あの/範囲/化/釣れ/説明 が辞書にある）。
    '該当': ('名詞:サ変接続', 'がいとう', True),
    '範囲': ('名詞:一般', 'はんい', True),
    'あの': ('連体詞:', 'あの', True),
    '化': ('名詞:接尾', 'か', True),
    '説明': ('名詞:サ変接続', 'せつめい', True),
    '釣れ': ('動詞:自立', 'つれ', True),
    '差': ('名詞:一般', 'さ', True),
    # 正しい複合語（カタカナ語＋漢字の接頭・接尾）を壊さないための
    # 検証に必要。実機の janome はこれらを読める。
    'コード': ('名詞:一般','こーど', True),
    # 実 janome は「ソフト」を1語で読める。mock が未知語にすると、
    # 「ソフト上」（正しい複合）の保護が実機と食い違う。
    'ソフト': ('名詞:一般', 'そふと', True),
    'ボタン': ('名詞:一般', 'ぼたん', True),
    '最大': ('名詞:一般', 'さいだい', True),
    '隣接': ('名詞:サ変接続', 'りんせつ', True),
    'カーソル': ('名詞:一般', 'かーそる', True),
    '位置': ('名詞:サ変接続', 'いち', True),
    '以内': ('名詞:非自立', 'いない', True),
    '日': ('名詞:接尾', 'にち', True),
    'カニ': ('名詞:一般', 'かに', True),
    '打ち': ('動詞:自立', 'うち', True),
    '叶う': ('動詞:自立', 'かなう', True),
    '父': ('名詞:一般', 'ちち', True),
    '地': ('名詞:接尾', 'ち', True),
    '腕': ('名詞:一般', 'うで', True),
    '料理': ('名詞:サ変接続', 'りょうり', True),
    # 実 janome の辞書には人名「安吾」（坂口安吾）が載っており、
    # 「田安吾」が 田＋安吾 と読めてしまう。固有名詞を実在の根拠に
    # しない修正（1-C）を mock でも再現するために追加。
    '安吾': ('名詞:固有名詞', 'あんご', True),
    '田': ('名詞:接尾', 'た', True),
    # 実 janome は促音「っ」単独も、動詞の未然形「やら」「ない」の
    # 並びも読める語として返す（読みが確定する）。
    # モックがこれらを未知語にすると、「知っている」「やらない」の
    # ような正しい活用に token_windows が窓を出してしまい、
    # 実機と違う誤検知が出る。実機の分割に合わせておく。
    'っ': ('動詞:非自立', 'っ', True),
    'やら': ('動詞:自立', 'やら', True),
    'そう': ('名詞:副詞可能', 'そう', True),
    'しそう': ('動詞:自立', 'しそう', True),
    'まま': ('名詞:非自立', 'まま', True),
    'よい': ('形容詞:自立', 'よい', True),
    'ない': ('助動詞:', 'ない', True),
    # --- 助詞・助動詞・記号 ---
    'は': ('助詞:係助詞', 'は', True),
    'が': ('助詞:格助詞', 'が', True),
    'を': ('助詞:格助詞', 'を', True),
    'に': ('助詞:格助詞', 'に', True),
    'と': ('助詞:格助詞', 'と', True),
    'も': ('助詞:係助詞', 'も', True),
    'の': ('助詞:連体化', 'の', True),
    'で': ('助詞:格助詞', 'で', True),
    'や': ('助詞:並立助詞', 'や', True),
    'ば': ('助詞:接続助詞', 'ば', True),
    'て': ('助詞:接続助詞', 'て', True),
    'から': ('助詞:格助詞', 'から', True),
    'より': ('助詞:格助詞', 'より', True),
    'かな': ('助詞:副助詞', 'かな', True),
    'という': ('助詞:格助詞', 'という', True),
    'た': ('助動詞:', 'た', True),
    'だ': ('助動詞:', 'だ', True),
    'な': ('助動詞:', 'な', True),
    'なく': ('助動詞:', 'なく', True),
    'です': ('助動詞:', 'です', True),
    'ます': ('助動詞:', 'ます', True),
    '、': ('記号:読点', '', False),
    '。': ('記号:句点', '', False),
    '「': ('記号:括弧開', '', False),
    '」': ('記号:括弧閉', '', False),
    '！': ('記号:一般', '', False),
    '？': ('記号:一般', '', False),
    '…': ('記号:一般', '', False),

    # --- 接尾語（単独では意味を成さない。誤補正の温床） ---
    '家': ('名詞:接尾', 'か', True),
    'あたり': ('名詞:接尾', 'あたり', True),
    'ドル': ('名詞:接尾', 'どる', True),
    '歳': ('名詞:接尾', 'さい', True),
    'か月': ('名詞:接尾', 'かげつ', True),
    'か所': ('名詞:接尾', 'かしょ', True),
    '向け': ('名詞:接尾', 'むけ', True),
    '寄り': ('名詞:接尾', 'より', True),
    '時': ('名詞:接尾', 'じ', True),
    '過ぎ': ('名詞:接尾', 'すぎ', True),
    '済み': ('名詞:接尾', 'ずみ', True),
    'さん': ('名詞:接尾', 'さん', True),
    '目': ('名詞:接尾', 'め', True),

    # --- 非自立 ---
    '以下': ('名詞:非自立', 'いか', True),
    'もの': ('名詞:非自立', 'もの', True),
    'おり': ('動詞:非自立', 'おり', True),
    'いる': ('動詞:非自立', 'いる', True),

    # --- 数 ---
    '1': ('名詞:数', '', False),
    '2': ('名詞:数', '', False),
    '7': ('名詞:数', '', False),
    '10': ('名詞:数', '', False),
    '100': ('名詞:数', '', False),
    '万': ('名詞:数', 'まん', True),

    # --- カタカナ語（辞書に無いものが多い） ---
    'ネイル': ('名詞:一般', '', False),
    'オオハシ': ('名詞:固有名詞', '', False),
    'コイツ': ('名詞:一般', '', False),
    'トガシ': ('名詞:固有名詞', '', False),
    'キシモト': ('名詞:固有名詞', '', False),
    'ナルト': ('名詞:固有名詞', '', False),
    'キルア': ('名詞:固有名詞', '', False),
    'ゴン': ('名詞:固有名詞', '', False),
    'ブラフ': ('名詞:一般', '', False),
    'ワロタ': ('名詞:一般', '', False),
    'スタン': ('名詞:一般', '', False),
    'ファット': ('名詞:一般', '', False),
    'マナ': ('名詞:一般', '', False),
    'オケ': ('名詞:一般', '', False),
    'コピ': ('名詞:一般', '', False),
    'インスト': ('名詞:一般', '', False),
    'ヤバい': ('形容詞:自立', '', False),
    'サクッと': ('副詞:一般', '', False),
    'デッキ': ('名詞:一般', 'でっき', True),
    'ヘアゴム': ('名詞:一般', '', False),
    'ハンター': ('名詞:一般', 'はんたー', True),
    'アンコモン': ('名詞:一般', '', False),
    'コモン': ('名詞:一般', '', False),
    'ターン': ('名詞:一般', 'たーん', True),
    'カウンター': ('名詞:一般', 'かうんたー', True),
    'ギャグ': ('名詞:一般', 'ぎゃぐ', True),
    'プライド': ('名詞:一般', 'ぷらいど', True),
    'MTG': ('名詞:固有名詞', '', False),
    'スタイル': ('名詞:一般', 'すたいる', True),

    # --- 一般的な語 ---
    '文字': ('名詞:一般', 'もじ', True),
    '高性能': ('名詞:一般', 'こうせいのう', True),
    '企業': ('名詞:一般', 'きぎょう', True),
    '専門': ('名詞:一般', 'せんもん', True),
    'トークン': ('名詞:一般', 'とーくん', True),
    'お子さん': ('名詞:一般', 'おこさん', True),
    '小書き': ('名詞:一般', 'こがき', False),
    'しゃ': ('名詞:一般', 'しゃ', False),
    '並び': ('名詞:一般', 'ならび', True),
    '間違い': ('名詞:一般', 'まちがい', True),
    '人': ('名詞:一般', 'ひと', True),
    '文法': ('名詞:一般', 'ぶんぽう', True),
    '理論': ('名詞:一般', 'りろん', True),
    '予約': ('名詞:サ変接続', 'よやく', True),
    '服': ('名詞:一般', 'ふく', True),
    '髪': ('名詞:一般', 'かみ', True),
    '推し': ('名詞:一般', 'おし', True),
    '仕様': ('名詞:一般', 'しよう', True),
    '後': ('名詞:非自立', 'あと', True),
    '明日': ('名詞:副詞可能', 'あした', True),
    '準備': ('名詞:サ変接続', 'じゅんび', True),
    '時間': ('名詞:副詞可能', 'じかん', True),
    '土地': ('名詞:一般', 'とち', True),
    '手札': ('名詞:一般', 'てふだ', True),
    '皆': ('名詞:代名詞', 'みんな', True),
    '結構': ('副詞:一般', 'けっこう', True),
    '面白く': ('形容詞:自立', 'おもしろく', True),
    '率直': ('名詞:形容動詞語幹', 'そっちょく', True),
    '持続': ('名詞:サ変接続', 'じぞく', True),
    '一般人': ('名詞:一般', 'いっぱんじん', True),
    '興味': ('名詞:一般', 'きょうみ', True),
    '念': ('名詞:一般', 'ねん', True),
    '歌': ('名詞:一般', 'うた', True),
    '作曲': ('名詞:サ変接続', 'さっきょく', True),
    '楽器': ('名詞:一般', 'がっき', True),
    '耳': ('名詞:一般', 'みみ', True),
    '聖戦士': ('名詞:一般', '', False),
    '王': ('名詞:一般', 'おう', True),
    '執筆': ('名詞:サ変接続', 'しっぴつ', True),
    '違い': ('名詞:一般', 'ちがい', True),
    '寝': ('動詞:自立', 'ね', True),
    '焼か': ('動詞:自立', 'やか', True),
    '使わ': ('動詞:自立', 'つかわ', True),
    '出せる': ('動詞:自立', 'だせる', True),
    '覚え': ('動詞:自立', 'おぼえ', True),
    '持っ': ('動詞:自立', 'もっ', True),
    'いく': ('動詞:非自立', 'いく', True),
    '言っ': ('動詞:自立', 'いっ', True),
    '知っ': ('動詞:自立', 'しっ', True),
    '作ら': ('動詞:自立', 'つくら', True),
    '言え': ('動詞:自立', 'いえ', True),
    '良かっ': ('形容詞:自立', 'よかっ', True),
    '弱': ('形容詞:自立', 'よわ', True),
    '強い': ('形容詞:自立', 'つよい', True),
    '全く': ('副詞:一般', 'まったく', True),
    'あえて': ('副詞:一般', 'あえて', True),
}


def mock_tokenize(line):
    """janome を模した分割。WORDS に無い文字は未知語として扱う。"""
    out = []
    i, n = 0, len(line)
    while i < n:
        hit = None
        for w in sorted(WORDS, key=len, reverse=True):
            if line.startswith(w, i):
                hit = w
                break
        if hit:
            pos, reading, known = WORDS[hit]
            out.append((hit, pos, reading, i, i + len(hit),
                        bool(known and reading)))
            i += len(hit)
            continue
        # 未知語: 同じ文字種が続く範囲をまとめて1語とする
        ch = line[i]
        j = i + 1
        if C.is_hiragana(ch):
            while j < n and C.is_hiragana(line[j]) and line[j] not in WORDS:
                j += 1
        elif C.is_katakana(ch):
            while j < n and C.is_katakana(line[j]):
                j += 1
        elif C.is_kanji(ch):
            while j < n and C.is_kanji(line[j]):
                j += 1
        w = line[i:j]
        reading = w if C.is_hiragana(ch) else ''
        out.append((w, '名詞:一般', reading, i, j, False))
        i = j
    return out


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


def run_decision_cases(store):
    """
    ユーザーの判断（クリックによる確定・除外）が効くことを確かめる。

    誤補正を止められること、止めた判断を取り消せること、
    そして「止めた判断が無関係な補正まで巻き添えにしない」ことを見る。
    """
    from decisions import DecisionStore

    print('--- ユーザーの判断による補正の抑止 ---')
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    def corrected(line, dec):
        return C.correct_line(line, store, mock_tokenize,
                              find_known_readings_flex, decisions=dec)

    # 補正が効いている状態を確認してから、それを止める
    base = corrected('もばなゅうりょく', None)
    check('判断なしなら従来どおり補正される',
          base['corrected'], 'もじにゅうりょく')

    dec = DecisionStore()

    # 1. この置換だけをやめる
    dec.reject('もばなゅうりょく', 'もじにゅうりょく')
    r = corrected('もばなゅうりょく', dec)
    check('「この補正は不要」と言われた置換は行わない',
          r['corrected'], 'もばなゅうりょく')
    check('補正しなかったので changed は False', r['changed'], False)

    # 2. 取り消せば元に戻る
    dec.unreject('もばなゅうりょく', 'もじにゅうりょく')
    r = corrected('もばなゅうりょく', dec)
    check('判断を取り消すと再び補正される',
          r['corrected'], 'もじにゅうりょく')

    # 3. 語そのものを守る（助詞を巻き込んだ範囲でも止まること）
    dec2 = DecisionStore()
    dec2.protect('もばなゅうりょく')
    r = corrected('もばなゅうりょく', dec2)
    check('守った語は補正されない', r['corrected'], 'もばなゅうりょく')

    # 4. 無関係な語の補正まで巻き添えにしない
    r = corrected('ぱそみん', dec2)
    check('別の語の補正は従来どおり効く', r['corrected'], 'ぱそこん')

    # 5. 1文字の語は守れない（広い範囲を巻き添えにするため）
    dec3 = DecisionStore()
    check('1文字の語は保護対象にしない', dec3.protect('あ'), False)

    # 6. 保存と読み込みで判断が失われないこと
    import tempfile, os as _os
    path = _os.path.join(tempfile.mkdtemp(), 'decisions.json')
    dec4 = DecisionStore(path)
    dec4.reject('もばなゅうりょく', 'もじにゅうりょく')
    dec4.protect('縦シュー')
    dec4.save()
    reloaded = DecisionStore(path)
    check('保存した「直さない」判断が読み込める',
          reloaded.is_rejected('もばなゅうりょく', 'もじにゅうりょく'), True)
    check('保存した「触らない」判断が読み込める',
          reloaded.is_protected('縦シュー'), True)

    return all_ok


def run_choice_cases(store):
    """
    語の選び直し（手動学習）の一連の動きを確かめる。

    候補の並び順（同音異義語が先頭）、選び直しの表示への反映、
    文脈（前後の語）による使い分け、再選択による上書き、
    保存と読み込み、を見る。
    """
    from choices import ChoiceStore
    from candidates import build_candidates
    from units import build_line_units, unit_at

    print('--- 語の選び直し（手動学習） ---')
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    # 同音異義語を用意する
    store.add('こうえん', '公園', '日常会話')
    store._by_reading['こうえん']['公園']['count'] = 5
    store.add('こうえん', '講演', '仕事・ビジネス')
    store._by_reading['こうえん']['講演']['count'] = 4
    store._invalidate_cache()

    # --- 候補の生成 ---
    cands = build_candidates('こうえん', 'こうえん', store,
                             find_known_readings_flex)
    kinds = [c['kind'] for c in cands]
    check('同音異義語が候補の先頭に並ぶ',
          kinds[:2], ['homophone', 'homophone'])
    check('同音の2語がどちらも入っている',
          {c['surface'] for c in cands if c['kind'] == 'homophone'}
          >= {'公園', '講演'}, True)
    check('打ち間違いの候補も含まれる',
          any(c['kind'] == 'typo' for c in cands), True)
    check('カタカナ表記も候補に入る',
          any(c['surface'] == 'コウエン' for c in cands), True)

    cands2 = build_candidates('ぱそみん', 'ぱそみん', store,
                              find_known_readings_flex)
    check('誤打から届く語（パソコン）が候補に入る',
          any(c['surface'] == 'パソコン' for c in cands2), True)

    # --- 選び直しの反映 ---
    ch = ChoiceStore()
    line = 'あしたのこうえんにいく'
    r = C.correct_line(line, store, mock_tokenize, find_known_readings_flex)
    text, units = build_line_units(r, mock_tokenize, ch)
    u = unit_at(units, text.index('こうえん'))
    check('クリック位置から語の単位が引ける', u['text'], 'こうえん')
    check('前後の語が単位に入っている', (u['prev'], u['next']), ('の', 'に'))

    ch.record(u['base'], '公園', 'こうえん', u['prev'], u['next'])
    text2, units2 = build_line_units(r, mock_tokenize, ch)
    check('選び直した語が表示に反映される', '公園' in text2, True)
    u2 = unit_at(units2, text2.index('公園'))
    check('選び直した語は kind=chosen になる', u2['kind'], 'chosen')
    check('表示が崩れない（前後がそのまま残る）',
          text2, 'あしたの公園にいく')

    # --- 文脈による使い分け ---
    ch.record('こうえん', '講演', 'こうえん', 'だいがくで', 'を')
    check('元の文脈では元の選択が出る',
          ch.lookup('こうえん', 'の', 'に'), '公園')
    check('別の文脈では別の選択が出る',
          ch.lookup('こうえん', 'だいがくで', 'を'), '講演')
    check('未知の文脈で選択が割れているなら決めない',
          ch.lookup('こうえん', 'まったくべつの', 'ばしょ'), None)

    # --- 再選択（何度でも変更できる） ---
    ch.record('こうえん', '講演', 'こうえん', 'の', 'に')
    check('同じ文脈での再選択は上書きされる',
          ch.lookup('こうえん', 'の', 'に'), '講演')
    ch.forget('こうえん', 'の', 'に')
    check('選び直しを取り消せる',
          ch.lookup('こうえん', 'の', 'に'), '講演')  # 残る記録の弱い一致は無い(2択)→
    # ↑取り消し後は「だいがくで|を」の記録しか無いので、文脈不一致では
    #   選択が1通り＝弱い一致で「講演」が出る。この動きも仕様として確認する。

    # --- 保存と読み込み ---
    import tempfile, os as _os
    path = _os.path.join(tempfile.mkdtemp(), 'choices.json')
    ch2 = ChoiceStore(path)
    ch2.record('こうえん', '公園', 'こうえん', 'の', 'に')
    ch2.save()
    reloaded = ChoiceStore(path)
    check('保存した選び直しが読み込める',
          reloaded.lookup('こうえん', 'の', 'に'), '公園')

    # --- ドラッグ選択（区切りが実態と合わないときの救済） ---
    # 実機のjanomeは「ひらがなを」を ひ/ら/が/なを と割る。
    # ユーザーがドラッグで「ひらがな」を選べば、区切りに関係なく
    # 選び直しが機能しなければならない。
    from units import make_range_unit

    def janome_like(text):
        toks = ['漢字', 'を', '平仮名', 'に', 'ひらい', 'たり', '、',
                'ひ', 'ら', 'が', 'なを', '漢字', 'に', 'し', 'たり', '、']
        out, pos = [], 0
        for w in toks:
            rd = w if all('\u3041' <= c <= '\u3096' for c in w) else ''
            out.append((w, '名詞:一般', rd, pos, pos + len(w), True))
            pos += len(w)
        return out

    text = '漢字を平仮名にひらいたり、ひらがなを漢字にしたり、'
    result = {'corrected': text, 'spans': [], 'details': []}
    ch3 = ChoiceStore()
    t1, units1 = build_line_units(result, janome_like, ch3)
    sel = make_range_unit(t1, units1, 13, 17)
    check('ドラッグ範囲から選び直しの単位が作れる', sel['text'], 'ひらがな')
    check('範囲のかなは読みとして扱える', sel['reading'], 'ひらがな')
    ch3.record(sel['base'], '平仮名', sel['reading'],
               sel['prev'], sel['next'])
    t2, units2 = build_line_units(result, janome_like, ch3)
    check('トークン区切りに関係なく置換される',
          t2, '漢字を平仮名にひらいたり、平仮名を漢字にしたり、')
    u_wo = unit_at(units2, t2.index('平仮名を', 10) + 3)
    check('切られた語の残り（を）が断片として残る', u_wo['text'], 'を')
    u_ch = unit_at(units2, t2.index('平仮名', 10))
    check('置換後の再クリックで chosen 単位が引ける',
          (u_ch['kind'], u_ch['base']), ('chosen', 'ひらがな'))
    ch3.forget(u_ch['base'], u_ch['prev'], u_ch['next'])
    t3, _ = build_line_units(result, janome_like, ch3)
    check('範囲の選び直しも取り消せる', t3, text)

    # --- 1文字の語の巻き添え防止 ---
    # 「し」→「歯」を1箇所で選んでも、文中の他の「し」まで
    # 置き換わってはいけない（1文字は文脈一致がないと引き当てない）。
    ch4 = ChoiceStore()
    ch4.record('し', '歯', 'し', 'むし', 'が')
    check('1文字の語は文脈が合えば引ける',
          ch4.lookup('し', 'むし', 'が'), '歯')
    check('1文字の語は文脈が合わなければ引かない',
          ch4.lookup('し', 'かん', 'に'), None)
    r_sh = {'corrected': 'にします', 'spans': [], 'details': []}
    t_sh, _ = build_line_units(r_sh, mock_tokenize, ch4)
    check('無関係な「し」は置き換わらない', t_sh, 'にします')

    # --- 疑わしい箇所の表示（自動では直さない・統合レイアウト用） ---
    from units import build_suspect_units

    def word_level_tokenize(text):
        """実機のjanomeのように単語単位でトークンを返す簡易版。"""
        segs = [('もんたい', 'もんたい'), ('、', '、'), ('ぱそみん', 'ぱそみん')]
        out, pos = [], 0
        for w, r in segs:
            if text[pos:pos + len(w)] != w:
                return []
            out.append((w, '名詞:一般', r, pos, pos + len(w), True))
            pos += len(w)
        return out

    r_sus = C.correct_line('もんたい、ぱそみん', store, mock_tokenize,
                           find_known_readings_flex)
    text_sus, units_sus = build_suspect_units(r_sus, word_level_tokenize,
                                              ChoiceStore())
    check('入力そのままが表示される（自動補正しない）',
          text_sus, 'もんたい、ぱそみん')
    check('疑わしい語が単語単位でまとまる',
          [u['text'] for u in units_sus], ['もんたい', '、', 'ぱそみん'])
    check('疑わしい語は kind=suspect になる',
          units_sus[0]['kind'], 'suspect')
    check('疑わしい語の detail が取れる',
          units_sus[0]['detail'][1], 'もんだい')
    check('記号など疑わしくない部分は plain',
          units_sus[1]['kind'], 'plain')

    ch5 = ChoiceStore()
    ch5.record('もんたい', '選んだ表記', 'もんたい', '', '、')
    _t, units_hint = build_suspect_units(r_sus, word_level_tokenize, ch5)
    check('過去に選び直した語には chosen_hint が付く（文字は変えない）',
          (units_hint[0]['kind'], units_hint[0]['chosen_hint'],
           units_hint[0]['text']),
          ('chosen_hint', '選んだ表記', 'もんたい'))

    # --- 辞書索引による候補（実機報告ケース） ---
    # 個人語彙に無い語（平仮名 等）や、漢字が別読みで誤変換された語
    # （時=とき だが意図は じ）も候補に出せることを確かめる。
    from candidates import build_range_candidates

    class FakeDict:
        """janome 辞書索引の代役。実機の辞書内容を模す。"""
        ready = True
        BY_READING = {
            'ひらがな': ['平仮名', 'ひらがな'],
            'じっそう': ['実装', '実相'],
            'まちがい': ['間違い'],
            'いと': ['糸', '意図'],
            'うった': ['売った', '打った'],
        }
        BY_SURFACE = {
            '時': ['とき', 'じ'], 'ッ': ['っ'], '層': ['そう'],
            'タン': ['たん'], '具': ['ぐ'], '子': ['こ', 'し'],
            '待ち': ['まち'], '外': ['がい', 'そと'],
            '高': ['こう', 'たか'], '後': ['ご', 'あと'],
            '綱': ['つな'], '刷り': ['ずり', 'すり'],
            '売っ': ['うっ'], '打っ': ['うっ'],
        }
        def surfaces_for_reading(self, r, limit=12):
            return self.BY_READING.get(r, [])[:limit]
        def readings_for_surface(self, s, limit=6):
            return self.BY_SURFACE.get(s, [])[:limit]

    fd = FakeDict()

    cands_h = build_candidates('ひらがな', 'ひらがな', store,
                               find_known_readings_flex, dict_index=fd)
    check('個人語彙に無い「平仮名」が辞書索引から候補に出る',
          any(c['surface'] == '平仮名' for c in cands_h), True)

    def seg_case(segments, want_surface):
        cs = build_range_candidates(segments, store,
                                    find_known_readings_flex, dict_index=fd)
        return any(c['surface'] == want_surface for c in cs)

    check('タン具（たん＋ぐ）→ 単語 が候補に出る',
          seg_case([('タン', 'たん'), ('具', 'ぐ')], '単語'), True)
    check('時ッ層（別読み じ の組合せ）→ 実装 が候補に出る',
          seg_case([('時', 'とき'), ('ッ', 'っ'), ('層', 'そう')], '実装'),
          True)
    cs_js = build_range_candidates(
        [('時', 'とき'), ('ッ', 'っ'), ('層', 'そう')],
        store, find_known_readings_flex, dict_index=fd)
    js = [c for c in cs_js if c['surface'] == '実装']
    check('実装は同音として（typoより上に）並ぶ',
          js and js[0]['kind'], 'homophone')
    check('待ち外（まち＋がい）→ 間違い が候補に出る',
          seg_case([('待ち', 'まち'), ('外', 'がい')], '間違い'), True)
    check('タン子（たん＋こ）→ 単語 が候補に出る',
          seg_case([('タン', 'たん'), ('子', 'こ')], '単語'), True)
    check('高後（こう＋ご）で候補が空にならない',
          len(build_range_candidates([('高', 'こう'), ('後', 'ご')],
                                     store, find_known_readings_flex,
                                     dict_index=fd)) > 0, True)
    cands_ito = build_candidates('糸', 'いと', store,
                                 find_known_readings_flex, dict_index=fd)
    check('糸のクリックで同音の「意図」が候補に出る',
          any(c['surface'] == '意図' for c in cands_ito), True)

    # --- 活用形に埋め込まれた不規則動詞の同音（来ている／着ている） ---
    # 「来る」「着る」は活用すると同じ語幹の読み「き」になるため、
    # 通常の同音探索・辞書索引のどちらにも載っていない
    # （実機報告: 「きている」「戻ってきている」等で候補が出ない）。
    from candidates import verb_stem_candidates

    check('「きている」から来ている／着ているが作れる',
          set(verb_stem_candidates('きている')),
          {'来ている', '着ている'})
    check('「きた」から来た／着たが作れる',
          set(verb_stem_candidates('きた')), {'来た', '着た'})
    check('複合表現でも頭を残したまま展開できる（戻ってきている）',
          set(verb_stem_candidates('もどってきている')),
          {'もどって来ている', 'もどって着ている'})
    check('関係ない語尾では展開しない',
          verb_stem_candidates('たべている'), [])

    cands_kiteiru = build_candidates('きている', 'きている', store,
                                     find_known_readings_flex)
    check('「きている」のクリックで来ている／着ているが候補に出る',
          {c['surface'] for c in cands_kiteiru} >= {'来ている', '着ている'},
          True)
    kinds_ki = {c['surface']: c['kind'] for c in cands_kiteiru}
    check('来ている／着ているは同音として優先表示される',
          (kinds_ki.get('来ている'), kinds_ki.get('着ている')),
          ('homophone', 'homophone'))

    range_cands = build_range_candidates(
        [('もどって', 'もどって'), ('き', 'き'), ('て', 'て'), ('いる', 'いる')],
        store, find_known_readings_flex)
    check('ドラッグ範囲「もどってきている」でも展開される',
          any(c['surface'] == 'もどって来ている' for c in range_cands), True)

    # --- 活用形の選び直し（売った → 打った） ---
    # 「売った」全体は辞書に無いので、語幹「売っ」を差し替えて
    # 語尾「た」を残す形で候補を作れることを確かめる。
    # 語尾まで変えた「打つ」では解決しない（実機report）。
    class FD2(FakeDict):
        BY_READING = dict(FakeDict.BY_READING, **{'うっ': ['打っ', '撃っ']})
        BY_SURFACE = dict(FakeDict.BY_SURFACE, **{'売っ': ['うっ'],
                                                  'た': ['た']})
    cs_utta = build_range_candidates([('売っ', 'うっ'), ('た', 'た')],
                                     store, find_known_readings_flex,
                                     dict_index=FD2())
    check('売った → 打った（語尾を保った差し替え）が候補に出る',
          any(c['surface'] == '打った' for c in cs_utta), True)
    check('打ったは同音として上位に並ぶ',
          cs_utta[0]['kind'], 'homophone')

    # 送り仮名を合わせる（原形の候補を元の活用形に直す）
    from candidates import align_okurigana
    check('売っ に対し 打つ は 打っ になる',
          align_okurigana('売っ', '打つ'), '打っ')
    check('動い に対し 働く は 働い になる',
          align_okurigana('動い', '働く'), '働い')
    check('送り仮名が無い語はそのまま',
          align_okurigana('時', '実装'), '実装')

    # 辞書索引が無くても、語幹の差し替えで活用形に届くこと
    cs_noidx = build_range_candidates([('売っ', 'うっ'), ('た', 'た')],
                                      store, find_known_readings_flex,
                                      dict_index=None)
    surfaces_noidx = [c['surface'] for c in cs_noidx]
    check('索引が無くても 打った が候補に出る',
          '打った' in surfaces_noidx, True)
    check('語尾を落とした 打つ より 打った が先に出る',
          surfaces_noidx.index('打った')
          < (surfaces_noidx.index('打つ') if '打つ' in surfaces_noidx else 999),
          True)

    # --- 壊れた記録で起動できなくなることが無いか ---
    # 過去に halfwidth_to_kana の3つ組（文字列, 数, 数）を
    # そのまま候補にしてしまう不具合があり、その時期の選び直しが
    # choices.json に **配列** として残っている。読み戻すとリストに
    # なり、行の組み立てが ''.join() で落ちて起動できなくなった
    # （実機で TypeError: expected str instance, list found）。
    import json as _json
    import os as _os
    broken_path = '_broken_choices.json'
    with open(broken_path, 'w', encoding='utf-8') as f:
        _json.dump([
            {'original': 'たんご', 'chosen': ['たんこ゛のつなか゛り', 10, 10],
             'reading': None, 'prev': '', 'next': '', 'count': 1},
            {'original': ['壊れた'], 'chosen': '単語',
             'prev': '', 'next': '', 'count': 1},
            {'original': '文字', 'chosen': '文字入力',
             'prev': '', 'next': '', 'count': 1},
        ], f, ensure_ascii=False)
    broken = ChoiceStore(broken_path)
    _os.remove(broken_path)
    check('壊れた記録は読み飛ばし、正しい記録だけ残す', len(broken), 1)
    check('壊れた記録は引き当てに出てこない',
          broken.lookup('たんご'), None)
    check('正しい記録は普通に引ける',
          broken.lookup('文字'), '文字入力')
    check('表記が文字列でない記録は覚えない',
          broken.record('てすと', ['あ', 1, 2]), False)

    # 壊れた記録が混ざっていても、行の組み立てが落ちないこと
    bad = ChoiceStore()
    bad._by_original['たんご'] = [
        {'original': 'たんご', 'chosen': ['こわれた', 1, 2],
         'prev': '', 'next': '', 'count': 1}]
    r_bad = {'original': 'たんごの繋がり', 'corrected': 'たんごの繋がり',
             'changed': False, 'details': [], 'spans': [],
             'original_spans': [], 'unsure_spans': []}
    try:
        text_bad, _units_bad = build_line_units(r_bad, mock_tokenize, bad)
        ok_bad = (text_bad == 'たんごの繋がり')
    except Exception:
        ok_bad = False
    check('壊れた記録があっても行の組み立てが落ちない', ok_bad, True)

    return all_ok


def run_dict_index_cases():
    """
    辞書索引が作れることを確かめる。

    実機の診断で、janome の辞書エントリから品詞が取り出せず
    全件が空になることが判明した。品詞で絞り込んでいたため
    索引が丸ごと空になり、候補が一切出なくなっていた。
    同じ壊れ方を繰り返さないための試験。
    """
    import dict_index as D

    print('--- 辞書索引の構築 ---')
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    # 実機と同じ形（品詞が空、長音が「ー」）のエントリを流し込む。
    # コストは実際の除外フィルタ（GENERAL_COST_LIMIT=4500）を
    # 下回る値にしておく。ここで確かめたいのは「品詞が空でも
    # 索引が作れるか」であり、除外フィルタそのものの検証は別に行う。
    sample = [
        ('平仮名', 'ひらがな', '', '', '', 3200),
        ('実装', 'じっそう', '', '', '', 2000),
        ('実相', 'じっそう', '', '', '', 2500),
        ('時', 'とき', '', '', '', 3000),
        ('時', 'じ', '', '', '', 3800),
        ('打っ', 'うっ', '', '', '', 3200),
        ('そういう', 'そーゆう', '', '', '', 3301),
    ]
    orig_iter, orig_has, orig_min = (D.iter_janome_entries, D.HAS_JANOME,
                                     D._MIN_READINGS)
    try:
        D.iter_janome_entries = lambda min_len=1, max_len=8: iter(sample)
        D.HAS_JANOME = True
        D._MIN_READINGS = 1
        idx = D.DictIndex(None)
        idx.ensure_built()
        check('品詞が空の辞書でも索引が作れる',
              idx.stats()['readings'] > 0, True)
        check('読みから表記を引ける（ひらがな→平仮名）',
              idx.surfaces_for_reading('ひらがな'), ['平仮名'])
        check('コストの低い語が先に並ぶ（実装→実相）',
              idx.surfaces_for_reading('じっそう'), ['実装', '実相'])
        check('表記から別の読みを引ける（時→とき,じ）',
              idx.readings_for_surface('時'), ['とき', 'じ'])
        check('長音「ー」を含む読みも入る',
              idx.surfaces_for_reading('そーゆう'), ['そういう'])
    finally:
        D.iter_janome_entries, D.HAS_JANOME, D._MIN_READINGS = (
            orig_iter, orig_has, orig_min)

    # --- 地名・人名・難語の除外（実機で「多すぎる」と報告された） ---
    # 品詞が空で判定できない環境でも、コスト（使用頻度）と
    # 表記パターンによる既存の除外フィルタ（janome_import._should_exclude、
    # 語彙取り込み機能と共通）が効いて絞り込まれることを確かめる。
    # ここでは実際の _should_exclude をそのまま使う（差し替えない）。
    pruning_sample = [
        ('食べる', 'たべる', '', '', '', 2000),      # 日常語: 残る
        ('学校', 'がっこう', '', '', '', 2500),       # 日常語: 残る
        ('殺伐たる', 'さつばつたる', '', '', '', 4349),  # 難語（実機の実測値）: 除外
        ('雑然たる', 'ざつぜんたる', '', '', '', 4349),  # 難語: 除外
        ('共和国', 'きょうわこく', '', '', '', 3000),   # 地名接尾語: 除外
        ('大英帝国', 'だいえいていこく', '', '', '', 3000),  # 帝国は対象外だが念のため
        ('ヤンキー・ドゥードル', 'やんきーどぅーどる', '', '', '', 3000),  # 記号混じり: 除外
    ]
    orig_iter, orig_has, orig_min = (D.iter_janome_entries, D.HAS_JANOME,
                                     D._MIN_READINGS)
    try:
        D.iter_janome_entries = lambda min_len=1, max_len=8: iter(
            pruning_sample)
        D.HAS_JANOME = True
        D._MIN_READINGS = 1
        idx2 = D.DictIndex(None)
        idx2.ensure_built()
        check('日常語（食べる）は索引に残る',
              idx2.surfaces_for_reading('たべる'), ['食べる'])
        check('日常語（学校）は索引に残る',
              idx2.surfaces_for_reading('がっこう'), ['学校'])
        check('コストの高い難語は除外される',
              idx2.surfaces_for_reading('さつばつたる'), [])
        check('地名の接尾語（共和国）で終わる語は除外される',
              idx2.surfaces_for_reading('きょうわこく'), [])
        check('記号混じりの語は除外される',
              idx2.surfaces_for_reading('やんきーどぅーどる'), [])
    finally:
        D.iter_janome_entries, D.HAS_JANOME, D._MIN_READINGS = (
            orig_iter, orig_has, orig_min)

    return all_ok


def run_context_vec_cases():
    """
    語の共起から作る軽量な文脈ベクトル（context_vec.py）。

    同音異義語（公園／講演）のように読みだけでは決められない語を、
    周辺の語との意味的な近さで選び分けられるかを見る。

    合わせて、このアプリの一貫した方針である
    「判断がつかないものは触らない」が、文脈スコアにも
    適用されていることを確かめる（手がかりが無い・僅差の場合に
    None を返し、決め打ちしないこと）。
    """
    from context_vec import ContextVectorStore
    from candidates import _reorder_by_context

    print('--- 文脈ベクトル（共起による同音異義語の選び分け） ---')
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    cv = ContextVectorStore()
    # 「公園」は散歩・子供と、「講演」は会場・資料と一緒に出てくる、
    # という状況をメモから学んだ状態を作る。
    for _ in range(3):
        cv.observe_line(['明日', '公園', '散歩', '子供'])
        cv.observe_line(['公園', '遊具', '子供', '広場'])
        cv.observe_line(['講演', '会場', '聴衆', '資料'])
        cv.observe_line(['資料', '講演', '準備', '会場'])

    check('一緒に出てくる語は似ていると判定する',
          cv.similarity('公園', '散歩') > 0.3, True)
    check('無関係な語は似ていないと判定する',
          cv.similarity('公園', '聴衆'), 0.0)

    check('周辺が子供・散歩なら「公園」を選ぶ',
          cv.pick_best_by_context(['公園', '講演'], ['子供', '散歩']),
          '公園')
    check('周辺が会場・資料なら「講演」を選ぶ',
          cv.pick_best_by_context(['公園', '講演'], ['会場', '資料']),
          '講演')

    # 「判断がつかないものは触らない」の確認。
    check('手がかりの無い周辺語では決め打ちしない',
          cv.pick_best_by_context(['公園', '講演'], ['天気']), None)
    check('周辺語が無ければ決め打ちしない',
          cv.pick_best_by_context(['公園', '講演'], []), None)
    check('候補が1つだけなら選び分けるまでもない',
          cv.pick_best_by_context(['公園'], ['子供']), None)
    check('知らない語同士は似ているとみなさない',
          cv.similarity('未知語A', '未知語B'), 0.0)

    # 候補一覧の並び替えと絞り込み。
    # 「打ち間違いの候補が10件近く出るが、大半が文脈的に不自然」
    # 「『単語として成立』の候補に『単行』『飛び』が出る」
    # という実機からの指摘に対応する部分。
    cv2 = ContextVectorStore()
    for _ in range(3):
        cv2.observe_line(['文字', '入力', '補正', '変換'])
        cv2.observe_line(['入力', '変換', '確定', '文字'])
        cv2.observe_line(['料理', '野菜', '食事'])

    cands = [
        {'surface': '料理', 'reading': 'x', 'kind': 'typo'},
        {'surface': '変換', 'reading': 'x', 'kind': 'typo'},
        {'surface': '野菜', 'reading': 'x', 'kind': 'typo'},
        {'surface': '補正', 'reading': 'x', 'kind': 'typo'},
    ]
    _reorder_by_context(cands, cv2, ['文字', '入力'])
    order = [c['surface'] for c in cands]
    check('文脈に合う打ち間違い候補だけが残る',
          sorted(order), ['変換', '補正'])
    check('残った候補は文脈スコアの高い順に並ぶ',
          order[0] in ('補正', '変換'), True)

    # 同音異義語は、文脈に合わなくても消さない。
    # 書き手が本当にその語を選びたい可能性が常にあるため。
    homo = [
        {'surface': '野菜', 'reading': 'x', 'kind': 'homophone'},
        {'surface': '補正', 'reading': 'x', 'kind': 'homophone'},
    ]
    _reorder_by_context(homo, cv2, ['文字', '入力'])
    check('同音異義語は文脈に合わなくても候補に残す',
          sorted(c['surface'] for c in homo), ['補正', '野菜'])

    # 打ち間違い候補が全滅する場合は、何も落とさない
    # （選択肢が減りすぎるより、雑音が混じるほうがまし）。
    all_far = [
        {'surface': '野菜', 'reading': 'x', 'kind': 'typo'},
        {'surface': '食事', 'reading': 'x', 'kind': 'typo'},
    ]
    _reorder_by_context(all_far, cv2, ['文字', '入力'])
    check('打ち間違いが全滅する場合は絞り込まない',
          len(all_far), 2)

    # 種類（同音→打ち間違い→かな）の大枠は崩さない、という約束。
    mixed = [
        {'surface': '料理', 'reading': 'x', 'kind': 'homophone'},
        {'surface': '補正', 'reading': 'x', 'kind': 'typo'},
    ]
    _reorder_by_context(mixed, cv2, ['文字', '入力'])
    check('文脈スコアが高くても、種類の並び順は入れ替えない',
          [c['kind'] for c in mixed], ['homophone', 'typo'])

    # 手がかりが無ければ、元の並びをそのまま保つ。
    untouched = [
        {'surface': '知らない語1', 'reading': 'x', 'kind': 'typo'},
        {'surface': '知らない語2', 'reading': 'x', 'kind': 'typo'},
    ]
    _reorder_by_context(untouched, cv2, ['文字'])
    check('手がかりが無ければ元の並びを保つ',
          [c['surface'] for c in untouched], ['知らない語1', '知らない語2'])

    # 保存と読み込み。
    import tempfile
    import os as _os
    path = _os.path.join(tempfile.mkdtemp(), 'context_vec.json')
    cv.save(path)
    cv3 = ContextVectorStore(path)
    check('保存した共起が読み込める',
          cv3.pick_best_by_context(['公園', '講演'], ['子供', '散歩']),
          '公園')

    with open(path, 'w', encoding='utf-8') as f:
        f.write('{ 壊れた内容')
    cv4 = ContextVectorStore(path)
    check('壊れたファイルでも起動が止まらない', len(cv4), 0)

    # --- 初期状態（使い込む前）でも効くこと ---
    # 「使い込むほど効く」に頼らず、初回起動の時点から
    # 候補の並びがまともである必要がある（実機からの指摘）。
    seeded = ContextVectorStore()
    check('初期の話題を読み込む前は空', len(seeded), 0)
    check('初期の話題を読み込める', seeded.ensure_seeded(), True)
    check('二度は読み込まない（重ねて数えない）',
          seeded.ensure_seeded(), False)

    check('初期状態で「単語」と「文章」は近い',
          seeded.similarity('単語', '文章') > 0.3, True)
    check('初期状態で「単語」と「文字」は近い',
          seeded.similarity('単語', '文字') > 0.3, True)
    check('初期状態で「単語」と「単行」は近くない',
          seeded.similarity('単語', '単行'), 0.0)
    check('初期状態で「文章」と「野菜」は近くない',
          seeded.similarity('文章', '野菜'), 0.0)

    # 実機で報告された、候補に雑音が多い2つの場面。
    # 初期状態のまま（何も使い込んでいない）で確かめる。
    noisy = [
        {'surface': '単行', 'reading': 'x', 'kind': 'typo'},
        {'surface': '飛び', 'reading': 'x', 'kind': 'typo'},
        {'surface': '文章', 'reading': 'x', 'kind': 'typo'},
        {'surface': '文字', 'reading': 'x', 'kind': 'typo'},
    ]
    _reorder_by_context(noisy, seeded, ['成立', '文章'])
    left = [c['surface'] for c in noisy]
    check('「単語として成立」で「単行」「飛び」が候補から消える',
          ('単行' not in left and '飛び' not in left), True)
    check('「単語として成立」で意味の近い候補は残る',
          ('文章' in left and '文字' in left), True)

    noisy2 = [
        {'surface': '花粉症', 'reading': 'x', 'kind': 'typo'},
        {'surface': '表記', 'reading': 'x', 'kind': 'typo'},
    ]
    _reorder_by_context(noisy2, seeded, ['分から', '文章'])
    left2 = [c['surface'] for c in noisy2]
    check('「分からない文章」で「花粉症」が候補から消える',
          '花粉症' not in left2, True)

    # 初期の話題は保存され、次回起動で読み直されないこと。
    path2 = _os.path.join(tempfile.mkdtemp(), 'context_vec.json')
    seeded.save(path2)
    reopened = ContextVectorStore(path2)
    check('初期の話題を読んだ記録が保存される', reopened.seeded, True)
    check('読み込み直しても初期の話題は効いている',
          reopened.similarity('単語', '文章') > 0.3, True)

    return all_ok


def run_context_material_cases():
    """
    文脈の材料集め（同じ行の外側）。

    同音異義語をどちらにするかは、その行の中だけでは決まらない。
    上下の行と、直前に確定した語を材料として集める仕組みを見る。
    集めた並びの **順序がそのまま優先度** になる（context_score は
    先頭に近いものほど重く数える）ので、順序も含めて固定する。
    """
    from context_vec import build_nearby_words, RecentWords
    import corrector as C

    print('--- 文脈の材料集め（上下の行・直前の履歴） ---')
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    words = {0: ['公園', '散歩'], 1: ['天気'], 2: ['対象行'],
             3: ['講演', '発表'], 4: ['会場']}

    def words_of(i):
        return words.get(i, [])

    check('近い行から順に集める',
          build_nearby_words(5, 2, words_of, radius=1),
          ['天気', '講演', '発表'])
    check('半径を広げると遠い行も入る（近い行が先）',
          build_nearby_words(5, 2, words_of, radius=2),
          ['天気', '講演', '発表', '公園', '散歩', '会場'])
    check('対象行そのものは含めない',
          '対象行' in build_nearby_words(5, 2, words_of, radius=2), False)
    check('先頭行では上が無くても落ちない',
          build_nearby_words(5, 0, words_of, radius=1), ['天気'])
    check('末尾行では下が無くても落ちない',
          build_nearby_words(5, 4, words_of, radius=1), ['講演', '発表'])
    check('上限を超えたら打ち切る',
          len(build_nearby_words(5, 2, words_of, radius=2, limit=3)), 3)
    check('1行しかなければ空', build_nearby_words(1, 0, words_of), [])

    def _boom(i):
        raise RuntimeError('分割に失敗')

    check('行の分割に失敗しても止まらない',
          build_nearby_words(3, 1, _boom), [])

    # --- 直前の変換履歴 ---
    recent = RecentWords(limit=3)
    recent.add('公園')
    recent.add('散歩')
    check('新しい順に並ぶ', recent.words(), ['散歩', '公園'])
    recent.add('公園')
    check('同じ語は先頭へ繰り上げ、重複しない',
          recent.words(), ['公園', '散歩'])
    recent.add_all(['天気', '会場'])
    check('上限を超えたら古いものから捨てる',
          recent.words(), ['会場', '天気', '公園'])
    recent.add('し')
    check('1文字の語は覚えない（どこにでも出るため）',
          recent.words(), ['会場', '天気', '公園'])
    recent.add(None)
    check('文字列でないものを渡しても落ちない', len(recent), 3)
    recent.clear()
    check('消せる', recent.words(), [])

    # --- 補正エンジンへの合流（同じ行 → 履歴 → 上下の行 の順） ---
    toks = [('公園', '名詞', 'こうえん', 0, 2, True),
            ('に', '助詞', 'に', 2, 3, True),
            ('行く', '動詞', 'いく', 3, 5, True)]
    got = C._surrounding_content_words(
        toks, 2, 3, nearby_words=['講演', '会場'],
        recent_words=['散歩'])
    check('同じ行の語を先頭に、次が履歴、最後が上下の行',
          got, ['公園', '行く', '散歩', '講演', '会場'])
    check('材料を渡さなければ従来どおり同じ行だけ',
          C._surrounding_content_words(toks, 2, 3), ['公園', '行く'])
    check('同じ語が重なっても1回だけ数える',
          C._surrounding_content_words(toks, 2, 3,
                                       nearby_words=['公園', '会場'],
                                       recent_words=['公園']),
          ['公園', '行く', '会場'])

    return all_ok


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

    check('短い語「たん」が語彙にあっても たんほ→たんご は直る',
          _fix('たんほの繋がり'), 'たんごの繋がり')
    check('短い語「あがり」が語彙にあっても つあがり→つながり は直る',
          _fix('単語のつあがり'), '単語のつながり')
    check('使用実績が圧倒的な語を選ぶ（単語696回 対 単に4回）',
          _fix('たんほの繋がり'), 'たんごの繋がり')
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
    check('連用形の送り仮名を剥がして芯を取り出す',
          [w for _a, _b in [(0, 0)]
           for w in ['ちでのほらい'[a:b] for a, b
                     in _C.window_cores('ちでのほらい', st2,
                                        after_kanji=True)]],
          ['ほらい'])
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

    # 5-g. 引用された「たんほの」は、窓経路の拮抗判定で たんご に届く
    #      （主経路が助詞ごと たんに に飲み込まない）
    check('「たんほの」→「たんごの」',
          _fix('「たんほの」の先頭'), '「たんごの」の先頭')

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
    check('単=の繋がり → 単語の繋がり',
          _fix('単=の繋がり'), '単語の繋がり')

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
    check('塊: たｂｂご（2連を1つの混入として拾う）',
          [r[2] for r in find_ascii_mixed_runs('たｂｂごの繋がり')],
          ['たｂｂご'])
    check('3連以上は意図した英語とみなす',
          find_ascii_mixed_runs('たｂｂｂごの繋がり'), [])
    check('たｂｂごの繋がり → 単語の繋がり（ｂｂ→ん）',
          _fix('たｂｂごの繋がり'), '単語の繋がり')
    check('たｍｍごの繋がり → 単語の繋がり',
          _fix('たｍｍごの繋がり'), '単語の繋がり')
    check('たｈｈの繋がり → たんの繋がり（ｈｈ→ん）',
          _fix('たｈｈの繋がり'), 'たんの繋がり')
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
    check('単語の地長利 → 単語の繋がり（別読みの組み合わせ）',
          _fix('単語の地長利'), '単語の繋がり')
    check('目もち長 → メモ帳（挿入を含む誤変換）',
          _fix('目もち長'), 'メモ帳')
    check('乳リュク → 入力', _fix('乳リュク'), '入力')
    check('文字乳リュク → 文字入力（前に漢字があっても拾う）',
          _fix('文字乳リュク'), '文字入力')
    check('壊さない: 補正ツールを使う',
          _fix('補正ツールを使う'), '補正ツールを使う')
    check('簡易流力 → 簡易入力（実在語＋壊れた側の分割解決）',
          _fix('簡易流力'), '簡易入力')
    check('たん゛子の繋がり → 単語の繋がり（濁点分離との複合）',
          _fix('たん゛子の繋がり'), '単語の繋がり')

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
    for _t in ('説明ぶんを書く', '差釣れません。', 'クリック化ドラッグで操作',
               '該当あの範囲を選ぶ'):
        check(f'並記なしは触らない(1-F): {_t}', _fix_f(_t), _t)
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
    # カタカナ語をひらがなで打った誤打（ーが2つ）は引き続き直る
    check('きーぼーそ は引き続き直る（ー2つ・位置保存）',
          _fix('きーぼーそ'), 'きーぼーど')
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

    # 5-i. 語の区切りが取れない行でも、色は補正箇所だけに付く
    from units import build_suspect_units as _bsu

    def _tok_skip_space(line):
        return [t for t in mock_tokenize(line) if t[0].strip()]

    _r5 = _C.correct_line('　たんほの繋がりです', st2, mock_tokenize,
                          find_known_readings_flex)
    _t5, _u5 = _bsu(_r5, _tok_skip_space)
    check('先頭スペース行でも行全体は suspect にならない',
          [u['kind'] for u in _u5][:1], ['plain'])
    check('補正箇所には suspect が付く',
          any(u['kind'] == 'suspect' and u['text'] == 'たんほ'
              for u in _u5), True)

    return all_ok


def run_tab_cases():
    """タブ管理の受け皿（session.py・2026-08-09）。"""
    from session import SessionStore, new_tab

    print('--- タブ管理（SessionStore） ---')
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    st = SessionStore()
    st.set_single('あ', None, True)
    check('タブ追加で末尾に増えて選択される',
          (st.add_tab(), st.active, len(st.tabs)), (1, 1, 2))
    st.update_active(new_tab('い'))
    check('選択中のタブだけ書き換わる',
          (st.tabs[0]['text'], st.tabs[1]['text']), ('あ', 'い'))
    st.add_tab(new_tab('う'))
    check('選択中でないタブを閉じても表示は変わらない',
          st.remove_tab(0), False)
    check('前のタブを閉じたら選択位置が繰り上がる', st.active, 1)
    check('選択中のタブを閉じたら表示が変わる',
          st.remove_tab(1), True)
    check('最後の1つを閉じると空のタブが残る',
          (st.remove_tab(0), len(st.tabs), st.tabs[0]['text']),
          (True, 1, ''))
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


def run_settings_cases():
    """
    アプリの設定（グローバルホットキーのオン/オフ）の保存。

    既定値（両方オン）、保存と読み込み、壊れたファイルでも
    起動が止まらないこと、片方だけオフにできることを見る。
    """
    import tempfile
    import os as _os
    from settings import Settings, active_hotkeys

    print('--- 設定（グローバルホットキーのオン/オフ） ---')
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    path = _os.path.join(tempfile.mkdtemp(), 'settings.json')

    s = Settings(path)
    check('既定値は両方オン', (s.get('hotkey_insert_enabled'),
                          s.get('hotkey_minus_enabled')), (True, True))
    check('既定でホットキーが2つとも有効', len(active_hotkeys(s)), 2)
    check('簡易入力の説明は既定で表示する', s.get('show_quick_hint'), True)

    s.set('hotkey_insert_enabled', False)
    s.save()
    s2 = Settings(path)
    check('保存した設定が読み込める',
          (s2.get('hotkey_insert_enabled'), s2.get('hotkey_minus_enabled')),
          (False, True))
    check('片方だけオフにすると有効なホットキーが1つになる',
          active_hotkeys(s2), [('minus', 'Ctrl+Shift+-')])

    with open(path, 'w', encoding='utf-8') as f:
        f.write('{ 壊れた内容')
    s3 = Settings(path)
    check('壊れた設定ファイルでも既定値で動く',
          s3.get('hotkey_insert_enabled'), True)

    import json
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'hotkey_insert_enabled': 'はい'}, f)
    s4 = Settings(path)
    check('不正な型（bool以外）は無視して既定値を使う',
          s4.get('hotkey_insert_enabled'), True)

    # 古い名前（hotkey_equals_enabled）で保存された設定を引き継げるか。
    # 「オフにする」と決めた意思が、名前を変えたせいで
    # 勝手にオンへ戻ってしまわないことを確かめる。
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'hotkey_equals_enabled': False}, f)
    s5 = Settings(path)
    check('古い名前で保存されたオフ設定を引き継ぐ',
          s5.get('hotkey_minus_enabled'), False)
    check('引き継いだ設定が有効ホットキーにも反映される',
          active_hotkeys(s5), [('insert', 'Ctrl+Insert')])

    # --- ホットキーのキー定義（hotkeys.py） ---
    # Windows 以外では登録処理そのものは動かないが、
    # 定義表の整合性はどの環境でも確かめられる。
    import hotkeys as HK

    check('設定が返す名前は全てキー定義にある',
          all(name in HK.HOTKEY_DEFS
              for name in ('insert', 'minus')), True)
    check('名前ごとに表示名がある',
          sorted(HK.HOTKEY_LABELS), sorted(HK.HOTKEY_DEFS))
    check('名前ごとに組み合わせの数だけ id がある',
          all(len(HK._HOTKEY_IDS[n]) == len(HK.HOTKEY_DEFS[n])
              for n in HK.HOTKEY_DEFS), True)

    all_ids = [i for ids in HK._HOTKEY_IDS.values() for i in ids]
    check('id が重複していない', len(all_ids), len(set(all_ids)))
    check('id から名前を引ける',
          all(HK.GlobalHotkeys._name_for_id(i) is not None
              for i in all_ids), True)
    check('知らない id には None を返す',
          HK.GlobalHotkeys._name_for_id(999), None)

    # JIS配列で「-」が刻印されているキーは VK_OEM_MINUS(0xBD)。
    # かつて使っていた VK_OEM_PLUS(0xBB) は JIS では「;」のキーで、
    # そのままでは押しても反応しなかった。
    check('2つ目のホットキーは Ctrl+Shift+VK_OEM_MINUS',
          HK.HOTKEY_DEFS['minus'],
          [(HK.MOD_CONTROL | HK.MOD_SHIFT, 0xBD)])
    check('Ctrl+Insert は修飾キーが Ctrl だけ',
          HK.HOTKEY_DEFS['insert'], [(HK.MOD_CONTROL, 0x2D)])
    check('設定の名前とキー定義の名前が揃っている',
          sorted(n for n, _l in active_hotkeys(Settings(None))),
          sorted(HK.HOTKEY_DEFS))

    # --- 一時解除（起動中だけ効く。設定ファイルには書かない） ---
    # Ctrl+Insert は Windows の「コピー」と同じ組み合わせなので、
    # その場で切れる逃げ道が要る。ただし次回起動時には戻す。
    from settings import effective_hotkeys

    s6 = Settings(None)
    check('一時解除が無ければ設定どおり',
          effective_hotkeys(s6), {'insert', 'minus'})
    check('一時解除したものだけが外れる',
          effective_hotkeys(s6, {'insert'}), {'minus'})
    check('2つとも一時解除できる',
          effective_hotkeys(s6, {'insert', 'minus'}), set())
    check('一時解除は設定ファイルの値を変えない',
          (s6.get('hotkey_insert_enabled'),
           s6.get('hotkey_minus_enabled')), (True, True))

    s7 = Settings(None)
    s7.set('hotkey_minus_enabled', False)
    check('設定でオフのものを一時解除しても矛盾しない',
          effective_hotkeys(s7, {'minus'}), {'insert'})
    check('設定でオフなら一時解除の有無に関わらず登録しない',
          effective_hotkeys(s7), {'insert'})

    # 一時解除の名前は、キー定義の名前と同じでなければならない
    # （綴りがずれると「解除したのに効き続ける」ことになる）
    check('一時解除に使う名前がキー定義と揃っている',
          effective_hotkeys(Settings(None)) <= set(HK.HOTKEY_DEFS), True)

    # --- 画面レイアウトの設定 ---
    from settings import (LAYOUT_LABELS, LAYOUT_SPLIT, LAYOUT_UNIFIED,
                          LAYOUT_CHOICES)

    s8 = Settings(None)
    check('レイアウトの既定は左右分割', s8.get('layout'), LAYOUT_SPLIT)
    check('選択肢は2つ', sorted(LAYOUT_CHOICES),
          sorted([LAYOUT_SPLIT, LAYOUT_UNIFIED]))
    check('選択肢すべてに表示名がある',
          sorted(LAYOUT_LABELS), sorted(LAYOUT_CHOICES))
    check('表示名が指定どおり',
          (LAYOUT_LABELS[LAYOUT_SPLIT], LAYOUT_LABELS[LAYOUT_UNIFIED]),
          ('入力エリアと補正エリアを左右に並べる',
           '入力と補正をひとつのエリアにまとめる'))

    s8.path = path
    s8.set('layout', LAYOUT_UNIFIED)
    s8.save()
    check('選んだレイアウトが次回起動時に復元される',
          Settings(path).get('layout'), LAYOUT_UNIFIED)

    # 知らない値が書かれていても既定値で動く（設定ファイルを
    # 手で編集した場合や、将来値を減らした場合に備える）
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'layout': 'three_pane'}, f)
    check('知らないレイアウト名は既定値に落とす',
          Settings(path).get('layout'), LAYOUT_SPLIT)

    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'layout': True}, f)
    check('レイアウトに真偽値が入っていても既定値に落とす',
          Settings(path).get('layout'), LAYOUT_SPLIT)

    # 真偽値の設定とレイアウトが混在していても、互いに壊さない
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'layout': LAYOUT_UNIFIED, 'dark_mode': True,
                   'find_regex': False}, f)
    s9 = Settings(path)
    check('レイアウトと真偽値の設定を同時に読める',
          (s9.get('layout'), s9.get('dark_mode'), s9.get('find_regex')),
          (LAYOUT_UNIFIED, True, False))

    # --- 検索オプション ---
    s10 = Settings(None)
    check('正規表現は既定でオン', s10.get('find_regex'), True)
    check('折り返し検索は既定でオン', s10.get('find_wrap'), True)
    check('大文字小文字の区別は既定でオフ',
          s10.get('find_match_case'), False)
    check('単語単位は既定でオフ', s10.get('find_whole_word'), False)

    s10.path = path
    s10.set('find_regex', False)
    s10.set('find_match_case', True)
    s10.save()
    s11 = Settings(path)
    check('検索オプションが次回起動時に復元される',
          (s11.get('find_regex'), s11.get('find_match_case')),
          (False, True))

    # --- ホットキーの診断（実機で「押しても出ない」と報告されたため） ---
    g = HK.GlobalHotkeys()
    st = g.status()
    check('状態にsupportedが含まれる', 'supported' in st, True)
    check('状態に登録済みの一覧が含まれる',
          isinstance(st['registered'], set), True)
    check('起動前は何も登録されていない', st['registered'], set())
    check('状態の名前がキー定義と揃っている',
          sorted(st['enabled']), sorted(HK.HOTKEY_DEFS))

    # 起動の前後どちらで set_enabled を呼んでも取りこぼさないこと。
    # 実機で「押しても簡易入力が出ない・状態にエラー番号すら出ない
    # （＝登録を試みていない）」となった原因が、
    #   スレッド: _thread_id を入れて、まだ全部オフの状態で同期
    #   メイン  : _enabled を True にしたが _thread_id は None に見えた
    # という並びでどちらも登録しないまま終わる競合だった。
    # 世代番号で取りこぼしを検出する仕組みが働くことを確かめる。
    g2 = HK.GlobalHotkeys()
    check('設定を変える前の世代は 0', g2._want_generation, 0)
    g2.set_enabled('insert', True)
    check('設定を変えると世代が進む', g2._want_generation, 1)
    check('未同期なら世代がずれている',
          g2._want_generation != g2._done_generation, True)
    # 実際の登録（_sync_registration）は Win32 API を呼ぶので、
    # Windows 以外では動かせない。世代の追いつきだけ手で再現して、
    # 取りこぼし検出の条件が正しいことを確かめる。
    g2._done_generation = g2._want_generation
    check('同期が済めば世代が揃う',
          g2._want_generation == g2._done_generation, True)

    # 起動前に設定しておいた内容が、状態として残ること
    g3 = HK.GlobalHotkeys()
    g3.set_enabled('insert', True)
    g3.set_enabled('minus', False)
    check('起動前の設定が状態に反映される',
          (g3.status()['enabled']['insert'],
           g3.status()['enabled']['minus']), (True, False))
    check('起動前の設定でも世代が進んでいる', g3._want_generation, 2)

    # --- 半角のまま打った文字列のかな変換 ---
    # 実機で候補に「たんこ゛のつなか゛り 10 10」と出た。
    # halfwidth_to_kana は (文字列, 変換できた数, 対象数) の
    # タプルを返すのに、文字列だと思って使ったのが原因。
    # 戻り値の形と、濁点が合成されることを固定しておく。
    from halfwidth import halfwidth_to_kana, romaji_to_kana
    from morphology import normalize_marks

    got = halfwidth_to_kana('qyb@kzut@l')
    check('halfwidth_to_kana は3つ組を返す', len(got), 3)
    check('halfwidth_to_kana の1つ目は文字列',
          isinstance(got[0], str), True)
    check('濁点を合成すると読める語になる',
          normalize_marks(got[0]), 'たんごのつながり')
    check('全部かなに変換できている', got[1], got[2])

    got2 = romaji_to_kana('tanngo')
    check('romaji_to_kana も3つ組を返す', len(got2), 3)
    check('ローマ字もかなになる', got2[0], 'たんご')

    # 変換率が低いものは候補にしない（記号列がかな混じりになるだけ）
    got3 = romaji_to_kana('qyb@kzut@l')
    check('ローマ字として読めないものは変換率が低い',
          got3[1] / got3[2] < 0.7, True)

    # --- 文頭の「?」を「・」の誤入力として補正する ---
    import corrector as C
    from vocabulary import VocabularyStore as _VS, find_known_readings_flex as _fk
    from seed_vocabulary import load_seed as _ls

    _store = _VS()
    _ls(_store)
    _fn = C.make_tokenizer(_store)

    r1 = C.correct_line('?上に爪、', _store, _fn, _fk)
    check('文頭の?は・に補正される', r1['corrected'][0], '・')
    check('文頭の?の補正で changed になる', r1['changed'], True)

    r2 = C.correct_line('文中に?がある場合', _store, _fn, _fk)
    check('文中の?は触らない', '?' in r2['corrected'], True)

    r3 = C.correct_line('?とは何ですか', _store, _fn, _fk)
    check('文頭の?のみのケースでも補正される', r3['corrected'][0], '・')

    # --- 行番号ガターにスクロール束縛を重ねていないか（静的確認） ---
    # LineNumberGutter 自身が <Button-1>/<B1-Motion> で行選択を
    # 実装しているので、app.py 側で同じイベントに add=True で
    # スクロール判定を重ねると、ドラッグのたびに競合して
    # 選択よりスクロールが勝ってしまっていた（実機で報告された）。
    _src = open('app.py', encoding='utf-8').read()
    check('行番号ガターにButtonPress-1でのスクロール束縛を重ねていない',
          "gutter.bind('<ButtonPress-1>'" in _src, False)
    check('行番号ガターにB1-Motionでのスクロール束縛を重ねていない',
          ("gutter.bind('<B1-Motion>',\n"
           "                       lambda e, g=gutter: self._drag_motion")
          in _src, False)

    # --- タイトル名の変更（実機からの指定） ---
    check('アプリの表示名がCorrectNoteになっている',
          "APP_TITLE = 'CorrectNote'" in _src, True)

    # --- 括弧で括るボタンの4種が揃っている ---
    check('括弧の組が4種とも定義されている',
          all(pair in _src for pair in
              ("('「', '」')", "('『', '』')",
               "('【', '】')", "('“', '”')")), True)

    # --- タイトルバーのダークモード適用にupdate_idletasksが入っている ---
    # ウィンドウの実体化前に GetParent を呼ぶと違うハンドルを
    # 取ってしまう不具合があったため、修正が消えていないか確認する。
    check('タイトルバー適用の前にupdate_idletasksを呼んでいる',
          'self.root.update_idletasks()' in _src, True)
    check('タイトルバー再描画にSWP_FRAMECHANGEDを使っている',
          'SWP_FRAMECHANGED' in _src, True)

    # --- メニューバーがMenubuttonベースの自作になっている ---
    # tk.Menu を root.config(menu=...) で使うと、Windowsでは
    # メニューバー本体（帯そのもの）がダークモードでも白いままに
    # なる不具合があった。Frame+Menubutton の自作に置き換えたことを
    # 確認する。
    check('メニューバーはMenubuttonの帯として作られている',
          "tk.Menubutton(" in _src, True)
    check('root.config(menu=...)は使っていない',
          "self.root.config(menu=" in _src, False)

    # --- 文頭の?の候補に、自動補正の提案（detail）を使っている ---
    check('文頭?の候補にdetailの提案を使っている',
          "corrected_text = detail" in _src or
          "_typed, corrected_text, _cat = detail" in _src, True)

    # --- 統合レイアウト・簡易入力の「元に戻す」履歴 ---
    check('統合レイアウトに変更履歴を持つ',
          "_editor_changes" in _src, True)
    check('簡易入力に変更履歴を持つ',
          "_quick_changes" in _src, True)
    # ひとつ前だけでなく、それより前の選び直しにも戻れること
    # （実機からの要望でスタック化した）
    check('変更履歴はスタックとして持つ',
          "def _push_change" in _src and "def _find_change" in _src, True)

    # --- 分割時の補正欄で右クリックが左クリックと同じ経路を通る ---
    check('補正欄の右ボタンはドラッグ経路(_on_result_press)を使う',
          "self.result_view.bind('<Button-3>', self._on_result_press)"
          in _src, True)
    check('補正欄の右クリック専用メニューは削除されている',
          "def _on_result_right_click" in _src, False)

    # --- 候補一覧から「この範囲をコピー」が削除されている ---
    check('候補一覧に「この範囲をコピー」が無い',
          "この範囲をコピー" in _src, False)

    # --- 辞書索引から地名を弾く（実機で「地名が多すぎる」と報告） ---
    # 実機の janome は品詞が全件空文字で取れないビルドがあるため、
    # sub_pos == '固有名詞' の判定に頼れない。品詞を空文字にして、
    # 表記のパターンだけで弾けることを確かめる。
    from janome_import import _should_exclude as _excl

    for _place in ('神奈川県', '横浜市', '渋谷区', '富士山', '琵琶湖',
                   '淡路島', '東京駅', '浅草寺', '大阪城'):
        check(f'地名を弾く: {_place}',
              _excl(_place, '', '', '', 3000), True)

    # 一般語を巻き込まないこと。「山」「川」などの1文字語尾は
    # 3文字以上の語にだけ適用しているのが効いているか。
    for _word in ('説明文', '入力', '変換', '谷間', '市場', '区別',
                  '都合', '町内', '沢山', '会社', '文章'):
        check(f'一般語は残す: {_word}',
              _excl(_word, '', '', '', 3000), False)

    # --- 複合語の後ろに付く語が初期語彙にある ---
    # 「せつめいぶん」→「説明ぶん」のように後半がひらがなのまま
    # 残ってしまう問題への対応。
    from halfwidth import kana_to_kanji_where_possible as _k2k
    _vs = _VS()
    _ls(_vs)
    check('せつめいぶん が 説明文 になる', _k2k('せつめいぶん', _vs), '説明文')
    check('めもちょう が メモ帳 になる', _k2k('めもちょう', _vs), 'メモ帳')

    # --- 受身・可能の助動詞の連用形を助動詞として扱う ---
    # 「されません」が「さ」＋「れません」に分かれたとき、
    # 「れません」が内容語とみなされて補正対象になり、
    # 色が付いてしまっていた（実機で報告）。
    from corrector import _is_all_auxiliary as _aux
    for _w in ('れません', 'されません', 'られません', 'せません',
               'ません', 'てください'):
        check(f'助動詞だけの並びとみなす: {_w}', _aux(_w), True)

    # 内容語まで助動詞扱いしていないこと（守りすぎの防止）
    for _w in ('もじにゅうりょく', 'せつめい', 'たんご'):
        check(f'内容語は助動詞扱いしない: {_w}', _aux(_w), False)

    # --- Esc の処理が1箇所に集約されている ---
    # <Key-Escape> を個別に束縛すると <KeyPress>(add=True) と
    # 実行順序が保証されず、押しても解除されないことがあった。
    check('エディタに個別のKey-Escape束縛が残っていない',
          "self.editor.bind('<Key-Escape>'" in _src, False)
    check('Escの受け皿(_on_global_escape)がある',
          "def _on_global_escape" in _src, True)

    # --- 簡易入力の最小化を消さない ---
    check('簡易入力にtoolwindow属性を使っていない',
          "attributes('-toolwindow'" in _src, False)

    # --- カタカナ+漢字の地名・小地名を弾く ---
    # 実機の辞書索引に「アナマ岩」「アボ鼻」「ウノ瀬」等が大量に
    # あると報告された。地形を表す漢字で終わる語を弾く。
    for _place in ('アナマ岩', 'アボ鼻', 'ウノ瀬', 'カナデ鼻',
                   'アシカ碆', 'ウロウ根', 'アヤメ平', 'アラル海',
                   'オイネが森', 'カデュセ網', 'エーメ立神',
                   'アシリベツの滝', 'エンロク泣セ岩'):
        check(f'小地名を弾く: {_place}',
              _excl(_place, '', '', '', 3000), True)

    # 同じ形（カタカナ+漢字）でも、地形の漢字で終わらない
    # 実用的な複合語は残すこと
    for _word in ('コピー機', 'メモ帳', 'テスト版', 'カタカナ表記'):
        check(f'実用的な複合語は残す: {_word}',
              _excl(_word, '', '', '', 3000), False)

    # 全部漢字の一般語を巻き込まないこと
    for _word in ('火山岩', '石灰岩', '現場', '名前'):
        check(f'漢字の一般語は残す: {_word}',
              _excl(_word, '', '', '', 3000), False)

    # --- 解析の行差分（動作が重い件への対応） ---
    # 行数が変わったときも、変わっていない行は使い回すこと。
    # 以前は改行を打つたびに全行を補正し直していたため、
    # 行数が増えるほど入力が重くなっていた。
    def _recompute(lines, prev, prev_results):
        """app.py の _analyze と同じ差分の取り方を再現する"""
        calls = []

        def _fresh(line):
            calls.append(line)
            return f'R({line})'

        if len(prev_results) != len(prev):
            return [_fresh(l) for l in lines], calls
        head = 0
        while (head < len(lines) and head < len(prev)
               and lines[head] == prev[head]):
            head += 1
        tail = 0
        while (tail < len(lines) - head and tail < len(prev) - head
               and lines[len(lines) - 1 - tail] == prev[len(prev) - 1 - tail]):
            tail += 1
        middle = [_fresh(l) for l in lines[head:len(lines) - tail]]
        res = (prev_results[:head] + middle
               + (prev_results[len(prev) - tail:] if tail else []))
        return res, calls

    for _lines, _prev, _name, _max_calls in (
            (['a', 'b', 'c'], ['a', 'b', 'c'], '変化なし', 0),
            (['a', 'X', 'c'], ['a', 'b', 'c'], '中央を変更', 1),
            (['a', 'b', 'c', 'd'], ['a', 'b', 'c'], '末尾に追加', 1),
            (['a', 'N', 'b', 'c'], ['a', 'b', 'c'], '中央に挿入', 1),
            (['a', 'c'], ['a', 'b', 'c'], '中央を削除', 0),
            (['a', 'b'], ['a', 'b', 'c'], '末尾を削除', 0),
            (['X', 'a', 'b', 'c'], ['a', 'b', 'c'], '先頭に挿入', 1)):
        _pr = [f'R({l})' for l in _prev]
        _res, _calls = _recompute(_lines, _prev, _pr)
        check(f'行差分の結果が正しい: {_name}',
              _res, [f'R({l})' for l in _lines])
        check(f'行差分の再計算が最小: {_name}',
              len(_calls) <= _max_calls, True)

    # --- 引用モードで行番号から引用できる ---
    check('行番号ガターに引用のコールバックがある',
          "on_pick_lines" in _src, True)
    check('行番号からの引用処理がある',
          "def _pick_lines" in _src, True)

    # ============================================================
    # 隣接漢字ひらがな補正の再挑戦（窓方式・実機からの指示）
    # ============================================================
    # 方針:
    #   - 語彙・機能語で説明できない「窓」だけを探索する
    #   - 唯一の答え（訂正1回・コスト小・2位と差が大きい）のとき
    #     だけ置き換える
    #   - 確信が持てなければ置き換えず unsure_spans（色だけ）で返す
    #   - 入力方式（かな/ローマ字）で隣接キーの検査方向を変える
    import corrector as _C2

    def _cl(text, im='kana'):
        # tokenize は実 janome の挙動を模した mock_tokenize を使う。
        # janome の無いフォールバックだと読みが取れず、
        # _looks_like_valid_japanese（読める窓は触らないガード）が
        # 一切効かないため、実機の挙動を再現できない。
        return _C2.correct_line(text, _store, mock_tokenize, _fk,
                                input_method=im)

    # --- 補正されるべきもの ---
    _r = _cl('単語のつあがり')
    check('つあがり→つながり（かな）', _r['corrected'], '単語のつながり')
    _r = _cl('単語のちながり')
    check('ちながり→つながり（かな）', _r['corrected'], '単語のつながり')
    _r = _cl('たんほの繋がり', im='romaji')
    check('たんほ→たんご（ローマ字: h/g が QWERTY で隣接）',
          _r['corrected'], 'たんごの繋がり')

    # --- 配列上で遠い取り違え・連打も直す（方針の変更点） ---
    # 以前は「かな入力では確信が持てない」として色だけ付けていた。
    # 「ひらがなに直し、隣接キーや脱字などを考慮して再構築する」
    # という指定に合わせ、隣接キーで説明が付かない取り違えも
    # 直すようにした（rebuild_window_core / find_similar_readings）。
    _r = _cl('たんほの繋がり', im='kana')
    check('たんほ→たんご（かな入力でも直す。ほ と ご は配列上は遠い）',
          _r['corrected'], 'たんごの繋がり')
    _r = _cl('たああんごの繋がり')
    check('たああんご→たんご（同じキーの連打を取り除く）',
          _r['corrected'], 'たんごの繋がり')
    _r = _cl('たんごのちながり')
    check('ちながり→つながり（助詞を剥がした芯で照合する）',
          _r['corrected'], 'たんごのつながり')

    # --- まだ確信が持てず、色だけ付くもの ---
    _r = _cl('かな打ちでのほらい')
    check('ほらい は置き換えない', _r['changed'], False)
    check('ほらい は色が付く', len(_r['unsure_spans']) > 0, True)

    # --- 機能語だけの並びは、似た語に引き寄せられてはいけない ---
    # 「かったのかな」は かった＋の＋かな と全部が機能語で説明できる。
    # 単語として成立していないのではなく、そもそも単語が無い。
    # ここを素通しすると「良かたかな」に壊れる（実際に壊れた）。
    check('機能語だけの並びと判定する',
          _C2._is_all_functional('かったのかな'), True)
    check('促音を含む活用語尾も機能語として説明できる',
          _C2._is_all_functional('っている'), True)
    check('内容語を含む並びは機能語だけではない',
          _C2._is_all_functional('たんほ'), False)

    # --- 壊してはいけないもの（前回の再挑戦で壊れた実例） ---
    for _t in ('知っている人向けの文法で作られている',
               '電車が遅れて遅刻しそうです',
               '土地を手札にブラフって皆やらないの？',
               '今のMTGスタン率直に言って面白くないな？',
               'よろしくおねがいします'):
        _r = _cl(_t)
        check(f'壊さない: {_t}', _r['corrected'], _t)
        check(f'色も付けない: {_t}', _r['unsure_spans'], [])

    # --- 設定: 入力方式 ---
    from settings import INPUT_METHOD_CHOICES
    check('入力方式の選択肢は kana と romaji',
          sorted(INPUT_METHOD_CHOICES), ['kana', 'romaji'])
    import tempfile as _tf
    _im_path = _tf.mktemp(suffix='_im.json')
    s12 = Settings(None)
    check('入力方式の既定はローマ字入力（2026-08-09 変更）', s12.get('input_method'), 'romaji')
    s12.path = _im_path
    s12.set('input_method', 'kana')
    s12.save()
    s13 = Settings(_im_path)
    check('入力方式が保存・復元される', s13.get('input_method'), 'kana')
    # 壊れた値は既定に戻る
    import json as _json
    with open(_im_path, 'w', encoding='utf-8') as _f:
        _json.dump({'input_method': 'qwerty!!'}, _f)
    s14 = Settings(_im_path)
    check('不正な入力方式は既定に戻る', s14.get('input_method'), 'romaji')

    # --- 正しい文への誤検知（実機で報告された3例） ---
    # 「まま」「ほう」（形式名詞）「よい」が説明できず、
    # 正しい表現に unsure の色が付いてしまっていた。
    # 「わります」は janome が「わり＋ます」と読めるので、
    # _looks_like_valid_japanese のガードで触らない。
    for _t in ('色付きのままでよいですが',
               '取得したほうがよいです',
               'チェック方向は変わります'):
        _r = _cl(_t)
        check(f'正しい文に色を付けない: {_t}',
              _r['unsure_spans'], [])
        check(f'正しい文を変えない: {_t}', _r['corrected'], _t)

    # --- ダークモードの unsure の見やすさ ---
    # 「文字と色が近くて見えなくなる」と報告されたため、
    # 背景・文字色の両方と明るさの差があることを数値で固定する。
    import re as _re2
    _dark_m = _re2.search(r"DARK_PALETTE = \{(.*?)\}",
                          open('app.py', encoding='utf-8').read(), _re2.S)
    _dark = dict(_re2.findall(r"'(\w+)': '(#[0-9a-fA-F]{6})'",
                              _dark_m.group(1))) if _dark_m else {}
    def _brightness2(hexstr):
        h = hexstr.lstrip('#')
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        return 0.299 * r + 0.587 * g + 0.114 * b

    _dark_unsure = _dark.get('UNSURE_BG')
    check('ダークにUNSURE_BGが定義されている', bool(_dark_unsure), True)
    if _dark_unsure:
        check('ダーク: unsureが背景と区別できる',
              abs(_brightness2(_dark_unsure) - _brightness2(_dark['PANEL']))
              >= 20, True)
        _ink = _dark.get('INK', '#e6e4dd')
        check('ダーク: unsureが文字色と区別できる',
              abs(_brightness2(_dark_unsure) - _brightness2(_ink)) >= 60,
              True)

    # --- 窓の切り出し: 短い断片の連結（実機の観察に基づく方式） ---
    # 誤字を含むひらがな列は、janome に掛けると1〜2文字の短い断片が
    # ぱらぱらと連続する形に割れる。「短い断片＋読みの取れない
    # トークン」の連なりを連結して窓にする token_windows が、
    # 語彙の規模に左右されず窓を出せることを固定する。
    check('壊れた列に窓が出る: たんほの',
          len(_C2.token_windows('たんほの', mock_tokenize)) > 0, True)
    check('壊れた列に窓が出る: ちでのほらい',
          len(_C2.token_windows('ちでのほらい', mock_tokenize)) > 0, True)
    check('正しい活用に窓を出さない: っている',
          _C2.token_windows('っている', mock_tokenize), [])
    check('正しい表現に窓を出さない: ままでよい',
          _C2.token_windows('ままでよい', mock_tokenize), [])
    check('正しい表現に窓を出さない: しそうです',
          _C2.token_windows('しそうです', mock_tokenize), [])

    # --- テーマ切替のパレット代入の整合 ---
    # _apply_theme のタプル代入に色を列挙し忘れると、その色だけ
    # テーマを切り替えても前の値のまま残る。UNSURE_BG の足し忘れで
    # 「ダークモードで白背景に白文字」になった（実機で2度報告）。
    # 左辺・右辺・_PALETTE_KEYS が常に一致することを固定する。
    import re as _re3
    _m3 = _re3.search(
        r"\((BG, PANEL.*?)\) = \((.*?)\)\n", _src, _re3.S)
    check('パレット代入が見つかる', _m3 is not None, True)
    if _m3:
        _left = [x.strip() for x in
                 _m3.group(1).replace('\n', ' ').split(',')]
        _right_keys = _re3.findall(r"pal\['(\w+)'\]", _m3.group(2))
        check('パレット代入の左辺と右辺の数が一致',
              len(_left), len(_right_keys))
        check('パレット代入の順序が一致', _left, _right_keys)
        _keys_m = _re3.search(r"_PALETTE_KEYS = \[(.*?)\]", _src, _re3.S)
        _keys = _re3.findall(r"'(\w+)'", _keys_m.group(1))
        check('パレット代入が_PALETTE_KEYSと同じ集合',
              sorted(_left), sorted(_keys))

    # --- ダークモードの見やすさ ---
    # 網掛け（補正候補あり）とオンマウスの色が、暗い背景の上で
    # 区別できるか。「色が付いているのが見えない」と報告されたため、
    # 背景との明るさの差を数値で確かめて、退行を防ぐ。
    import re as _re

    def _rgb(hexstr):
        h = hexstr.lstrip('#')
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

    def _brightness(hexstr):
        r, g, b = _rgb(hexstr)
        return 0.299 * r + 0.587 * g + 0.114 * b

    src = open('app.py', encoding='utf-8').read()
    dark_block = src[src.index('DARK_PALETTE = {'):]
    dark_block = dark_block[:dark_block.index('}')]
    dark = dict(_re.findall(r"'(\w+)': '(#[0-9a-fA-F]{6})'", dark_block))

    check('ダークモードの色定義が読める',
          all(k in dark for k in ('PANEL', 'SUSPECT_BG', 'HOVER_BG')), True)

    # 背景（PANEL）との明るさの差。小さすぎると見分けが付かない。
    gap_suspect = abs(_brightness(dark['SUSPECT_BG'])
                      - _brightness(dark['PANEL']))
    gap_hover = abs(_brightness(dark['HOVER_BG'])
                    - _brightness(dark['PANEL']))
    check('ダーク: 網掛けが背景と区別できる明るさ差がある',
          gap_suspect >= 12, True)
    check('ダーク: オンマウスが背景と区別できる明るさ差がある',
          gap_hover >= 12, True)

    # ダークモードの網掛け・オンマウス色が背景と区別できるか。
    # 「色が付いているのが見えない」と報告されたため、
    # 背景との差が一定以上あることを数値で確かめる。

    return all_ok


def run_theme_palette_cases():
    """
    ダークモードの配色（LIGHT_PALETTE / DARK_PALETTE）の整合性。

    tkinter が無いためアプリ全体は import できない。
    配色定義のブロックだけを抜き出して検証する。
    キーが一致していること、色コードとして正しい形式であること、
    パレット内で色が重複していないこと（重複があると
    「元の色→新しい色」の対応付けが曖昧になり、意図しない部品まで
    色が変わってしまう）、ライトとダークで実際に見た目が変わることを見る。
    """
    import re

    print('--- ダークモードの配色 ---')
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    src = open('app.py', encoding='utf-8').read()
    start = src.index("BG = '#f6f4ee'")
    end_marker = src.index('DARK_PALETTE = {')
    depth, i, started = 0, end_marker, False
    while i < len(src):
        if src[i] == '{':
            depth += 1
            started = True
        elif src[i] == '}':
            depth -= 1
            if started and depth == 0:
                i += 1
                break
        i += 1
    snippet = src[start:i]
    ns = {}
    exec(snippet, ns)

    keys, light, dark = ns['_PALETTE_KEYS'], ns['LIGHT_PALETTE'], ns['DARK_PALETTE']
    check('LIGHT/DARKのキーが一致している',
          set(keys) == set(light) == set(dark), True)

    hexre = re.compile(r'^#[0-9a-fA-F]{6}$')
    check('色コードが全て正しい形式（#RRGGBB）',
          all(hexre.match(v) for v in list(light.values())
              + list(dark.values())), True)
    check('LIGHTパレット内に重複した色が無い',
          len(set(light.values())) == len(light), True)
    check('DARKパレット内に重複した色が無い',
          len(set(dark.values())) == len(dark), True)
    check('全てのキーでライトとダークの値が異なる',
          all(light[k] != dark[k] for k in keys), True)

    return all_ok


def run_drag_scroll_cases():
    """
    タッチパネルでの1本指スクロールの向き判定（app.classify_drag）。

    このサンドボックスに tkinter が無いため app.py 全体は import
    できない。判定ロジックは純粋関数として切り出してあるので、
    そこだけ AST 経由で取り出して確かめる。
    """
    import ast

    print('--- ドラッグ方向の判定（タッチスクロール） ---')
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    src = open('app.py', encoding='utf-8').read()
    tree = ast.parse(src)
    func = next(n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == 'classify_drag')
    ns = {}
    exec(compile(ast.Module(body=[func], type_ignores=[]), '<f>', 'exec'), ns)
    classify_drag = ns['classify_drag']

    check('小さな動きは判定しない（誤反応を防ぐ）',
          classify_drag(2, 2), None)
    check('縦方向優位の動きはスクロール（下ドラッグ）',
          classify_drag(2, 30), 'scroll')
    check('縦方向優位の動きはスクロール（上ドラッグ）',
          classify_drag(0, -25), 'scroll')
    check('横方向優位の動きは範囲選択（単語選択との衝突を避ける）',
          classify_drag(30, 2), 'other')
    check('斜めでも縦が十分大きければスクロール',
          classify_drag(10, 20), 'scroll')

    # --- 語を拾うモード（F1 / =）で差し込む文字列の決定 ---
    func2 = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef)
                and n.name == 'resolve_pick_text')
    ns2 = {}
    exec(compile(ast.Module(body=[func2], type_ignores=[]), '<f>', 'exec'),
         ns2)
    resolve_pick_text = ns2['resolve_pick_text']

    check('ドラッグ範囲があればそれを差し込む',
          resolve_pick_text('単語の繋がり', '単語'), '単語の繋がり')
    check('範囲が無ければクリックした語を差し込む',
          resolve_pick_text('', '文字入力'), '文字入力')
    check('空白だけの範囲はクリックした語に譲る',
          resolve_pick_text('   ', '文字入力'), '文字入力')
    check('どちらも無ければ差し込まない',
          resolve_pick_text('', ''), '')

    # --- 見出し（説明）を表示するかの判定 ---
    func3 = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef)
                and n.name == 'header_should_show')
    ns3 = {}
    exec(compile(ast.Module(body=[func3], type_ignores=[]), '<f>', 'exec'),
         ns3)
    header_should_show = ns3['header_should_show']

    check('先頭では見出しを表示する', header_should_show(0.0), True)
    check('少し下げただけなら誤差として表示のまま',
          header_should_show(0.0001), True)
    check('下へスクロールしたら隠す', header_should_show(0.3), False)
    check('末尾までスクロールしたら隠す', header_should_show(1.0), False)

    # tkinter の yscrollcommand は、環境によって値を文字列
    # （Tcl 経由の '0.0' 等）のまま渡してくることがある。
    # float 前提で比較すると TypeError になり、スクロールする
    # たびにエラーが出て起動できなくなる不具合が実機で発生した。
    # 文字列で渡されても同じ結果になることを確認する。
    check('文字列で渡されても先頭なら表示する',
          header_should_show('0.0'), True)
    check('文字列で渡されても下へスクロールしたら隠す',
          header_should_show('0.3'), False)
    check('数値に変換できない値では例外を出さず表示側に倒す',
          header_should_show('abc'), True)
    check('None が渡っても例外を出さず表示側に倒す',
          header_should_show(None), True)

    # --- ブックマークの次/前を探す ---
    func4 = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef)
                and n.name == 'next_bookmark')
    ns4 = {}
    exec(compile(ast.Module(body=[func4], type_ignores=[]), '<f>', 'exec'),
         ns4)
    next_bookmark = ns4['next_bookmark']

    bm = {3, 10, 25}
    check('次のブックマークを探す', next_bookmark(5, bm, forward=True), 10)
    check('最後のブックマークより後ろなら先頭に循環する',
          next_bookmark(30, bm, forward=True), 3)
    check('前のブックマークを探す', next_bookmark(15, bm, forward=False), 10)
    check('先頭のブックマークより前なら末尾に循環する',
          next_bookmark(1, bm, forward=False), 25)
    check('ブックマークが無ければ None', next_bookmark(5, set()), None)
    check('ちょうどブックマークの行にいても次へ進む',
          next_bookmark(10, bm, forward=True), 25)

    # --- 分割解析のやり残し行の読み替え ---
    # 全行解析は少しずつに分けて行うため、途中で打鍵があると
    # やり残しが出る。その行は内容が変わっていないので差分では
    # 拾われず、読み替えて持ち越さないと二度と解析されない。
    func5 = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef)
                and n.name == 'remap_pending_lines')
    ns5 = {}
    exec(compile(ast.Module(body=[func5], type_ignores=[]), '<f>', 'exec'),
         ns5)
    remap = ns5['remap_pending_lines']

    # 10行の文書。head=2（先頭2行は不変）、tail=5（末尾5行は不変）
    # のまま行数が変わらない編集
    check('行数が変わらなければ番号はそのまま',
          remap([1, 8], 2, 5, 10, 10), [1, 8])
    check('変わった範囲の中の行は読み替えない（改めて解析されるため）',
          remap([3, 4], 2, 5, 10, 10), [])
    # 1行増えた場合、末尾側の不変行は1つ後ろへずれる
    check('行が増えたら末尾側のやり残しは後ろへずらす',
          remap([1, 8], 2, 5, 10, 11), [1, 9])
    check('行が減ったら末尾側のやり残しは前へずらす',
          remap([1, 8], 2, 5, 10, 9), [1, 7])
    check('先頭側のやり残しは行数が変わってもずれない',
          remap([0, 1], 2, 5, 10, 20), [0, 1])
    check('範囲の外に出る番号は捨てる', remap([9], 2, 0, 10, 3), [])
    check('重複は取り除いて昇順に並べる',
          remap([8, 1, 8], 2, 5, 10, 10), [1, 8])
    check('やり残しが無ければ空', remap([], 2, 5, 10, 10), [])

    # --- IMEが確定した文字を編集キーと取り違える問題 ---
    # 実機のキー記録で確定した事実:
    #   keysym=Delete keycode=46 char='.' で届き、Tk の Delete の
    #   動きが走って文字が入らず、カーソル位置の1文字が消えていた。
    func6 = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef)
                and n.name == 'ime_confirmed_char')
    ns6 = {'_IME_MISREAD_KEYSYMS': frozenset({
        'Delete', 'Insert', 'Prior', 'Next', 'Home', 'End',
        'Left', 'Right', 'Up', 'Down',
        'Clear', 'Select', 'Print', 'Execute', 'Help'})}
    exec(compile(ast.Module(body=[func6], type_ignores=[]), '<f>', 'exec'),
         ns6)
    ime_char = ns6['ime_confirmed_char']

    check('Deleteとして届いた「.」は文字として入れる',
          ime_char('Delete', '.'), '.')
    check('Insertとして届いた「-」は文字として入れる',
          ime_char('Insert', '-'), '-')
    check('Leftとして届いた「%」も文字として入れる',
          ime_char('Left', '%'), '%')
    check('本物のDeleteキー（文字を伴わない）は触らない',
          ime_char('Delete', ''), None)
    check('制御文字を伴うDeleteは本物とみなす',
          ime_char('Delete', '\x7f'), None)
    check('本物の矢印キーは触らない', ime_char('Right', ''), None)
    check('普通の文字入力には関与しない', ime_char('period', '.'), None)
    check('BackSpaceは対象外（取り違えの並びに無い）',
          ime_char('BackSpace', '\x08'), None)
    check('複数文字が来たら触らない（取り違えではない）',
          ime_char('Delete', 'abc'), None)

    # --- 左右のスクロール同期で使う「折り返しの本数」の数え方 ---
    # Tk の count -displaylines は、環境によって整数ではなく
    # 1要素のタプルで返ることがある（yscrollcommand の first/last が
    # 文字列で届いたのと同種の型ゆれ。SPEC.md「過去の失敗と学び」7）。
    # どちらでも同じ結果になり、例外も出さないことを固定する。
    cls_node = next(n for n in ast.walk(tree)
                   if isinstance(n, ast.ClassDef)
                   and any(isinstance(i, ast.FunctionDef)
                           and i.name == '_displaylines_between'
                           for i in n.body))
    func7 = next(i for i in cls_node.body
                if isinstance(i, ast.FunctionDef)
                and i.name == '_displaylines_between')
    func7.decorator_list = []       # staticmethod を外して単体で呼ぶ
    ns7 = {}
    exec(compile(ast.Module(body=[func7], type_ignores=[]), '<f>', 'exec'),
         ns7)
    count_lines = ns7['_displaylines_between']

    class _FakeText:
        def __init__(self, value):
            self.value = value

        def count(self, a, b, c):
            if isinstance(self.value, Exception):
                raise self.value
            return self.value

    check('整数で返る環境', count_lines(_FakeText(3), '1.0', '1.5'), 3)
    check('タプルで返る環境でも同じ',
          count_lines(_FakeText((3,)), '1.0', '1.5'), 3)
    check('None が返っても 0 として扱う',
          count_lines(_FakeText(None), '1.0', '1.5'), 0)
    check('空のタプルでも 0', count_lines(_FakeText(()), '1.0', '1.5'), 0)
    check('負の値は 0 に丸める', count_lines(_FakeText(-2), '1.0', '1.5'), 0)
    check('例外が出ても 0 を返して止まらない',
          count_lines(_FakeText(RuntimeError()), '1.0', '1.5'), 0)

    return all_ok


def run_session_cases():
    """
    自動保存と前回の続きの復元（session.py）。

    「保存せずに閉じても書きかけが残る」ことが目的なので、
    控えが確実に残ること、壊れた控えで起動が止まらないこと、
    そして起動のたびに空行が積み上がらないことを確かめる。
    """
    import tempfile
    import os as _os
    import json as _json
    from session import SessionStore, new_tab, tab_title, is_blank

    print('--- 自動保存と前回の続き ---')
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    path = _os.path.join(tempfile.mkdtemp(), 'session.json')

    # --- 保存して読み直す ---
    s = SessionStore(path)
    s.set_single('書きかけの内容', None, saved=False,
                 cursor='2.3', scroll=0.25)
    check('控えを書き出せる', s.save(), True)

    s2 = SessionStore(path)
    check('控えを読み込める', s2.load(), True)
    tab = s2.current()
    check('本文が戻る', tab['text'], '書きかけの内容')
    check('カーソル位置が戻る', tab['cursor'], '2.3')
    check('スクロール位置が戻る', tab['scroll'], 0.25)
    check('未保存であることが戻る', tab['saved'], False)

    # --- タブの配列として保存されている（将来のタブ対応のため） ---
    with open(path, encoding='utf-8') as f:
        raw = _json.load(f)
    check('タブの配列として保存されている',
          isinstance(raw.get('tabs'), list), True)

    # --- 壊れた控えでも起動を止めない ---
    with open(path, 'w', encoding='utf-8') as f:
        f.write('{ 壊れた内容')
    check('壊れた控えは読み込まない（起動は止めない）',
          SessionStore(path).load(), False)

    # --- 形式が違えば読まない（古い控えでの誤復元を防ぐ） ---
    with open(path, 'w', encoding='utf-8') as f:
        _json.dump({'version': 99, 'tabs': [{'text': 'x'}]}, f)
    check('形式が違う控えは読み込まない',
          SessionStore(path).load(), False)

    # --- 起動のたびに末尾の空行が積み上がらない ---
    # 起動時に空行を足し、終了時に控えるという往復を繰り返しても
    # 本文が太っていかないこと（放置すると際限なく増える）
    trailing = 24

    def pad(text):
        have = len(text) - len(text.rstrip('\n'))
        need = trailing - have
        return text + '\n' * need if need > 0 else text

    s3 = SessionStore(path)
    s3.set_single('本文', None)
    s3.save()
    for _ in range(10):
        cur = SessionStore(path)
        cur.load()
        editor_text = pad(cur.current()['text'])       # 起動時
        cur.set_single(editor_text.rstrip('\n'), None)  # 終了時に控える
        cur.save()
    final = SessionStore(path)
    final.load()
    check('起動を繰り返しても空行が積み上がらない',
          final.current()['text'], '本文')

    # --- タブの名前と空判定 ---
    check('保存済みならファイル名がタブ名になる',
          tab_title(new_tab('a', path='/x/y/memo.txt')), 'memo.txt')
    check('未保存なら「無題」', tab_title(new_tab('a')), '無題')
    check('空行だけの内容は空とみなす', is_blank(new_tab('  \n\n')), True)

    # --- ブックマークも控えに含まれる（次回起動時に消えないように） ---
    s5 = SessionStore(path)
    s5.set_single('本文', None, bookmarks={7, 2, 15})
    s5.save()
    reloaded5 = SessionStore(path)
    reloaded5.load()
    check('ブックマークが並び替えて保存される',
          reloaded5.current()['bookmarks'], [2, 7, 15])

    return all_ok


def run_search_cases():
    """
    検索と置換（search.py）。

    置換は本文を書き換えるので、位置ずれで壊さないことが最重要。
    特に「置換で長さが変わったときに以降の位置がずれる」失敗は
    起きやすいので、重点的に確かめる。
    """
    import search as S

    print('--- 検索と置換 ---')
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    text = 'abc ABC 単語のつながり abc 単語'

    # --- 大文字小文字 ---
    check('既定では大文字小文字を区別しない',
          len(S.find_all(text, S.build_pattern('abc'))), 3)
    check('区別する設定なら一致が減る',
          len(S.find_all(text, S.build_pattern('abc', match_case=True))), 2)

    # --- 次を検索・前を検索・折り返し ---
    p = S.build_pattern('abc', match_case=True)
    check('次を検索', S.find_next(text, p, 0), (0, 3))
    check('現在位置より後ろを探す', S.find_next(text, p, 1), (16, 19))
    check('末尾まで行ったら先頭に戻る', S.find_next(text, p, 100), (0, 3))
    check('折り返しを切ると見つからない',
          S.find_next(text, p, 100, wrap=False), None)
    check('前を検索', S.find_next(text, p, 25, backwards=True), (16, 19))

    # --- 記号を含む検索（正規表現でないときは文字そのもの） ---
    check('メタ文字は文字として扱う',
          S.find_all('abc a.c', S.build_pattern('a.c')), [(4, 7)])
    check('正規表現にすればメタ文字として働く',
          len(S.find_all('abc a.c', S.build_pattern('a.c', regex=True))), 2)

    # --- 単語単位 ---
    check('単語単位では部分一致を除く',
          S.find_all('abc abcd', S.build_pattern('abc', whole_word=True)),
          [(0, 3)])

    # --- 置換 ---
    check('すべて置換',
          S.replace_all(text, S.build_pattern('単語'), '語彙')[0],
          'abc ABC 語彙のつながり abc 語彙')
    check('置換した件数を返す',
          S.replace_all(text, S.build_pattern('単語'), '語彙')[1], 2)

    # 置換で長さが変わっても、以降の位置がずれないこと。
    # 前から順に置き換えると必ず壊れる部分なので、必ず確かめる。
    check('置換で長さが伸びても壊れない',
          S.replace_all('aXaXa', S.build_pattern('X'), 'LONG')[0],
          'aLONGaLONGa')
    check('置換で長さが縮んでも壊れない',
          S.replace_all('aLONGaLONGa', S.build_pattern('LONG'), 'X')[0],
          'aXaXa')

    # --- 正規表現の後方参照 ---
    check('後方参照が使える',
          S.replace_all('a@b c@d', S.build_pattern(r'(\w+)@(\w+)', regex=True),
                        r'\2:\1', regex=True)[0],
          'b:a d:c')
    check('正規表現でないときは \\1 をそのまま入れる',
          S.replace_all('a@b', S.build_pattern('a@b'), r'\1')[0], r'\1')

    # --- 誤りの扱い ---
    def expect_error(fn):
        try:
            fn()
            return False
        except S.SearchError:
            return True

    check('正規表現の書き間違いは理由を返す',
          expect_error(lambda: S.build_pattern('(', regex=True)), True)
    check('空の検索語は誤りとして扱う',
          expect_error(lambda: S.build_pattern('')), True)

    # --- 長さ0の一致で止まらないこと ---
    # 「^」や「\b」は長さ0で一致するため、素朴に実装すると
    # 同じ位置から進めず無限に回る
    check('長さ0の一致は飛ばす（無限に回らない）',
          S.find_all('abc', S.build_pattern(r'\b', regex=True)), [])

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
        return [(s, p, r, st, en, True) for s, p, r, st, en, _k in toks]

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


if __name__ == '__main__':
    store = build_store()

    typo_cases = [
        # --- 置換（隣接キーの押し間違い） ---
        ('もばなゅうりょく', True, 'もじにゅうりょく'),
        ('もばなゅいりょく', True, 'もじにゅうりょく'),
        ('ぱそみん', True, 'ぱそこん'),
        ('へんかく', True, 'へんかん'),
        ('けんさこ', True, 'けんさく'),
        ('きーぼーそ', True, 'きーぼーど'),
        # --- 濁点・半濁点・小書きの誤り ---
        ('ぱぞこん', True, 'ぱそこん'),
        ('はそこん', True, 'ぱそこん'),
        ('もんたい', True, 'もんだい'),
        ('しゆうせい', True, 'しゅうせい'),
        # --- 脱字（押し忘れ） ---
        ('もじにゅうりょ', True, 'もじにゅうりょく'),
        ('じにゅうりょく', True, 'もじにゅうりょく'),
        # --- 余分な打鍵（押しすぎ・重複） ---
        ('もじにゅううりょく', True, 'もじにゅうりょく'),
        ('ぱそここん', True, 'ぱそこん'),
        ('もんじにゅうりょく', True, 'もじにゅうりょく'),
        # --- 半角モードのまま打ってしまった入力 ---
        ('md@i(4l)h', True, '文字入力'),
        ('md[ki)4l)h', True, '文字入力'),   # 半角＋隣接キー誤打
        ('qyb@kzut@l', True, '単語の繋がり'),   # 複数の語＋助詞
        ('^ytyx;ue', True, '変換されない'),
        ('up@uo<5eqyb@t@b@^ytyx;wm', True, 'なぜなら、英単語がご変換されても'),
        ('c4w@r,', True, 'そうですね'),
        ('bkzg@f', True, 'この次は'),
        # 「入力欄」を初期語彙に入れたので、後半も漢字になる
        # （以前は「らん」が語彙に無く「入力らん」で止まっていた）
        ('i(4l)hoy', True, '入力欄'),
        ('fythkjji(4l)h', True, '半角のまま入力'),
        ('cmcmbk:\\rf', True, 'そもそもこのけろすは'),
        ('b@^ytyg)94w@gjr', True, 'ご変換許容できます'),
        ('hlZhw@ms@dqmkft@hd(4r.bsw@', True,
         'クリックでもどしたものは学習することで'),
        # --- ローマ字のまま打ってしまった入力 ---
        ('mojinyuuryoku', True, '文字入力'),
        ('mojinonyuuryoku', True, '文字の入力'),
        ('gakkou', True, '学校'),
        ('pasokon', True, 'パソコン'),
        # --- 入力モードの取り違え（全角化・かな打ちのままローマ字） ---
        ('ｍｄ＠い（４ｌ）ｈ', True, '文字入力'),
        ('ｍｏｊｉｎｙｕｕｒｙｏｋｕ', True, '文字入力'),
        ('もらまにみらみんななすんらのな', True, '文字の入力'),
        # --- 濁点・半濁点が分離した入力 ---
        ('こ゜こ゜は', True, 'ごごは'),
        ('たんこ゛', True, 'たんご'),
        # --- もとからあるケース ---
        ('もばにゅうりょく', True, 'もじにゅうりょく'),
        ('もじなゅうりょく', True, 'もじにゅうりょく'),
        ('もじにうりょく', True, 'もじにゅうりょく'),
        ('もじにゅうのりょく', True, 'もじにゅうりょく'),
        ('もじにゅりうょく', True, 'もじにゅうりょく'),
        ('ぱそみんは、', True, 'ぱそこんは、'),
    ]

    keep_cases = [
        ('以下', False), ('言えば良かったのかな', False),
        ('1歳7か月のお子さん', False), ('間違いが1～2か所ではなく', False),
        ('知っている人向けの文法で作られている', False),
        ('理論寄りだった', False), ('10時過ぎに', False), ('予約済み', False),
        ('イブキさん', False),
        # カタカナ語（固有名詞・俗語・専門用語。辞書に無くて当然）
        ('持っていくものも服もネイルも髪も推し仕様にした', False),
        ('ネコワ…じゃなくてオオハシがついたヘアゴム', False),
        ('コイツなりのギャグ？', False),
        ('土地デッキもサクッと焼かれて', False),
        ('ヤバい…', False),
        ('あえて全くマナを使わず出せる聖戦士の', False),
        ('ゴンのプライドが王みたい', False),
        ('キシモトとトガシの執筆スタイルの違い', False),
        ('ナルトとハンター×ハンターの', False),
        ('土地を手札にブラフって皆やらないの？', False),
        ('結構面白くてワロタwww', False),
        ('今のMTGスタン率直に言って面白くないな？', False),
        ('アンコモンとコモンが弱過ぎでやってられない', False),
        ('一般人インストに興味が無いです', False),
        ('ハンターハンターのキルアって念を覚えたの', False),
        ('歌とオケ', False),
        ('作曲、楽器、耳コピ', False),
        ('ないです…時間が', False),
        # 一般的な日本語文（補正を強化しても壊さないこと）
        ('明日は雨が降るかもしれません', False),
        ('会議の資料を準備しておきます', False),
        ('電車が遅れて遅刻しそうです', False),
        ('ひらがなだけのぶんしょうです', False),
        ('こんかいのけっかはよかったです', False),
        ('しごとがおわったらかえります', False),
        ('とりあえずやってみます', False),
        ('よろしくおねがいします', False),
        ('たぶんそうだとおもう', False),
        ('だいたいそんなかんじ', False),
        ('どうしても', False),
        # 意図して打った英単語（かなに変換してはいけない）
        ('Python', False), ('hello', False), ('javascript', False),
        ('function', False), ('import', False), ('return', False),
        ('world', False), ('test', False), ('update', False),
        ('delete', False), ('select', False), ('create', False),
        ('insert', False), ('random', False), ('server', False),
        ('JavaScript', False), ('SELECT', False), ('README', False),
        # コード・URL・日付（記号を含むが日本語ではない）
        ('foo.bar()', False), ('array[0]', False), ('a==b', False),
        ('user@example.com', False), ('http://example.com', False),
        ('print("hi")', False), ('if(x>0)', False), ('self.name', False),
        ('list.append(1)', False), ('key:value', False),
        ('path/to/file', False), ('v1.2.3', False), ('2026-07-30', False),
        ('tel:03-1234', False),
        ('03-6230-9666', False), ('Amazon', False),
        # 日常で見る古い言い回し・漢数字・カタカナ語＋動詞の境目
        # （実機9巡目・2026-08-09）
        ('どういう方法を以てお取りなさいますか', False),
        ('西洋料理屋へ往って給仕人に', False),
        ('玉子五十個入の孵卵器', False),
        ('ソラ来たぞ、', False),
        ('TODO', False),
        ('ＡＩ', False), ('Ｐｙｔｈｏｎ', False), ('１２３', False),
        # 普通のかな文（ローマ字と誤解釈してはいけない）
        ('こんにちは', False), ('ありがとうございます', False),
        ('きょうはいいてんきですね', False), ('がっこうにいきます', False),
        ('ともだちとあそぶ', False), ('かいものにでかける', False),
        ('べんきょうをがんばる', False), ('やさいをたべる', False),
    ]

    ok1 = run_cases(store, typo_cases, '誤打の補正（変化するのが正解）')
    print()
    ok2 = run_cases(store, keep_cases, '誤検知の防止（変化しないのが正解）')
    print()
    ok3 = run_decision_cases(store)
    print()
    ok4 = run_choice_cases(store)
    print()
    ok5 = run_regression_cases(store)
    print()
    ok6 = run_dict_index_cases()
    print()
    ok7 = run_drag_scroll_cases()
    print()
    ok8 = run_session_cases()
    print()
    ok9 = run_search_cases()
    print()
    ok10 = run_theme_palette_cases()
    print()
    ok11 = run_original_spans_cases(store)
    print()
    ok12 = run_settings_cases()
    print()
    ok13 = run_context_vec_cases()
    print()
    ok15 = run_context_material_cases()
    print()
    ok16 = run_rebuild_cases()
    print()
    ok17 = run_overcorrection_cases()
    print()
    ok18 = run_tab_cases()
    print()
    ok14 = run_kanji_guess_cases(store)
    print()
    report_known_issues(store)
    print()
    print('ALL OK:', ok1 and ok2 and ok3 and ok4 and ok5 and ok6 and ok7
          and ok8 and ok9 and ok10 and ok11 and ok12 and ok13 and ok14
          and ok15 and ok16 and ok17 and ok18)
