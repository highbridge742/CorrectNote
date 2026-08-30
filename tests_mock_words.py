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
**語の見分け**（辞書・カタカナ・外来語・英単語・字の並び）の試験。

`tests_mock.py` から分けたもの（2026-08-20・項目48-GQ）。
**走らせる入口は `tests_mock.py` のまま。**
"""
import corrector as C
from vocabulary import VocabularyStore, find_known_readings_flex
from seed_vocabulary import load_seed


def test_seed_dictionary():
    """
    **最初から持っている単語リスト**（種）の回帰テスト
    （2026-08-12・項目48-AW / 48-BA / 48-BB / 48-BC）。

    ここで留め金を掛けるのは3つ:

      1. **入れ物が分かれていること**。種を「その人が使っている語」
         の入れ物に混ぜると、使用実績を尋ねている関門が全部
         素通りになる（第34回はこれで3件落ちた）。
      2. **初期状態で効くこと**。種を持った理由がこれ。
      3. **短いカタカナ語を直し先にしないこと**。
         `アンコモン → アンチモン` が、種を入れたときに出た
         いちばん危ない壊れ方だった。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import loanword as LW
    from vocabulary import VocabularyStore

    print('--- 最初から持っている単語リスト（種）---')

    fresh = VocabularyStore()       # **入れたばかりの状態**

    # --- 1. 入れ物が分かれている ---
    check('覚えた語の入れ物に種は入らない（カタカナ）',
          LW._katakana_vocabulary(fresh), {})
    check('覚えた語の入れ物に種は入らない（英語）',
          LW._english_vocabulary(fresh), {})
    check('直し先には種が入っている（カタカナ）',
          len(LW._katakana_targets(fresh)) > 1000, True)
    check('直し先には種が入っている（英語）',
          len(LW._english_targets(fresh)) > 10000, True)
    # 使用実績を尋ねる関門は、種を見に行かない
    check('種の語だけでは複合語とみなさない',
          LW.is_known_compound(['ショートカット', 'インストール'], fresh),
          False)

    # --- 2. 初期状態で効く ---
    for typed in ('プセネタリウム', 'プネラタリウム', 'プネタリウム',
                  'ププラネタリウム', 'プラニネタリウム'):
        check(f'初期状態でも直る（{typed}）',
              LW.fix_katakana_word(typed, fresh), 'プラネタリウム')
    check('正しく書いた語は初期状態でも触らない',
          LW.fix_katakana_word('プラネタリウム', fresh), None)
    # 拮抗は決める（項目48-IU）: キーード は キーボード／キーワード の
    # どちらにも1字足せば届く。使用実績 → 同梱の表の一般的さ で決める。
    check('拮抗は使用実績→一般的さで決める（キーード → キーボード）',
          LW.fix_katakana_word('キーード', fresh), 'キーボード')
    _grown = VocabularyStore()
    for _ in range(5):
        _grown.add('きーわーど', 'キーワード', 'その他')
    _grown.add('きーぼーど', 'キーボード', 'その他')
    check('使用実績が多いほうが先（本人が キーワード をよく打つなら）',
          LW.fix_katakana_word('キーード', _grown), 'キーワード')

    for typed, want in (('seperate', 'separate'),
                        ('definately', 'definitely'),
                        ('occured', 'occurred'),
                        ('accomodate', 'accommodate')):
        check(f'初期状態でも直る（{typed}）',
              LW.fix_english_word(typed, fresh), want)
    # **辞書に載っている語は正しく書けている。触らない**
    for word in ('committee', 'possible', 'planetarium', 'receives'):
        check(f'辞書にある語は触らない（{word}）',
              LW.fix_english_word(word, fresh), None)
    # 識別子や固有名詞は辞書に無いが、これも壊さない（項目48-BJ/BK）
    for word in ('tkinter', 'janome', 'Cowork', 'corrector',
                 'iconic', 'footer', 'neighbours', 'lineno'):
        check(f'辞書に無い語も壊さない（{word}）',
              LW.fix_english_word(word, fresh), None)
    # **小文字のあとに大文字が来る語は識別子**（項目48-BK）
    for word in ('UniDic', 'AttributeError', 'RegisterHotKey',
                 'DwmSetWindowAttribute'):
        check(f'CamelCase は触らない（{word}）',
              LW.fix_english_word(word, fresh), None)
    # ただし大文字が続くだけの形は、うにさんの見本なので止めない
    check('大文字が続くだけなら直す（PPlanetarium）',
          LW.fix_english_word('PPlanetarium', fresh), 'Planetarium')
    # **打ち間違い／綴り間違いとして説明が付くか**（項目48-BJ）
    check('キーが隣なら置換を通す（Plaqnetarium の q）',
          LW.typo_explains_seed_english('plaqnetarium', 'planetarium'), True)
    check('母音どうしの取り違えは通す（seperate）',
          LW.typo_explains_seed_english('seperate', 'separate'), True)
    check('離れたキーの置換は通さない（iconic→ironic）',
          LW.typo_explains_seed_english('iconic', 'ironic'), False)
    check('離れたキーの余分な1文字は通さない（pchanged→changed）',
          LW.typo_explains_seed_english('pchanged', 'changed'), False)
    check('重複打鍵は通す（Pllanetarium）',
          LW.typo_explains_seed_english('pllanetarium', 'planetarium'), True)
    # **触らない語の一覧は、直し先より広い**（項目48-BK）
    check('触らない語は直し先より多い',
          len(LW._english_seed_all()) > len(LW._english_seed()), True)
    # 大文字小文字は書いた人に合わせる
    check('大文字を保つ',
          LW.fix_english_word('Plaqnetarium', fresh), 'Planetarium')
    # 同じ字の2連続は畳む（うにさんの指定・項目48-AX）
    for typed in ('Planetariumm', 'PPlanetarium', 'Plannetarium'):
        check(f'2連続を畳む（{typed}）',
              LW.fix_english_word(typed, fresh), 'Planetarium')

    # --- 3. 打ち間違いとして説明が付かない1手は通さない ---
    # うにさんの指摘「**カタカナ6文字以上は少ないです**」で、
    # 長さで守るのをやめた（項目48-BF）。守っているのは
    # 「その1手が打ち間違いとして説明が付くか」（項目48-BD）。
    seed = LW._katakana_seed()
    check('短いカタカナ語も直し先に入っている（ドラッグ）',
          'ドラッグ' in seed.values(), True)
    check('プラネタリウムは直し先に入っている',
          'プラネタリウム' in seed.values(), True)
    # うにさんのメモの実例（MTG の用語）。これが壊れたら駄目。
    # アンコモン → アンチモン は こ→ち の置換で距離1だが、
    # **こ と ち はキーが遠い**ので押し間違いとして説明が付かない。
    check('アンコモンを壊さない',
          LW.fix_katakana_word('アンコモン', fresh), None)
    check('こ→ち は押し間違いとして説明が付かない',
          LW.typo_explains_seed_word('あんこもん', 'あんちもん'), False)
    check('せ→ら は説明が付く（プセネタリウム）',
          LW.typo_explains_seed_word('ぷせねたりうむ', 'ぷらねたりうむ'), True)
    check('重複打鍵は説明が付く（ププラネタリウム）',
          LW.typo_explains_seed_word('ぷぷらねたりうむ', 'ぷらねたりうむ'), True)
    check('隣接キーが入り込んだのは説明が付く（プラニネタリウム）',
          LW.typo_explains_seed_word('ぷらにねたりうむ', 'ぷらねたりうむ'), True)
    check('かなでない1文字が紛れたのは説明が付く',
          LW.typo_explains_seed_word('ぷらねたりう５む', 'ぷらねたりうむ'), True)
    check('語の頭に別の語が付いた形は説明が付かない（リダイレクト）',
          LW.typo_explains_seed_word('りだいれくと', 'だいれくと'), False)
    check('リダイレクトを壊さない',
          LW.fix_katakana_word('リダイレクト', fresh), None)
    check('イレギュラーを壊さない',
          LW.fix_katakana_word('イレギュラー', fresh), None)
    # **辞書に載っている語は正しく書けている。触らない**（48-BE）。
    # 守る側の一覧は、直し先の門を通す**前**の全語を使う。
    check('守る側の種は、直し先の種より多い',
          len(LW._katakana_seed_all()) > len(LW._katakana_seed()), True)
    for w in ('ダイレクト', 'レギュラー', 'バーコード', 'スクロール'):
        check(f'辞書にある語は触らない（{w}）',
              LW.fix_katakana_word(w, fresh), None)

    # --- ひらがなから寄せてよい語だけを寄せる（項目48-BH）---
    kana_only = LW._katakana_seed_kana_only()
    check('ひらがなから寄せてよい語は、全語より少ない',
          0 < len(kana_only) < len(LW._katakana_seed_all()), True)
    for reading, want in (('ぷらねたりうむ', 'プラネタリウム'),
                          ('しょーとかっと', 'ショートカット'),
                          ('すくろーる', 'スクロール')):
        check(f'ひらがなの外来語を寄せる（{reading}）',
              LW.katakana_for_hiragana(reading, fresh), want)
    # 同じ読みで漢字・ひらがなの表記もある語は寄せない
    for reading in ('かたつむり', 'さくら', 'ぼたん', 'ひまわり',
                    'かぶとむし', 'あじさい'):
        check(f'かなのまま書いてよい語は寄せない（{reading}）',
              LW.katakana_for_hiragana(reading, fresh, min_length=3), None)
    check('ドラッグは4文字でも根拠が揃えば寄せる',
          LW.katakana_for_hiragana('どらっぐ', fresh, min_length=4),
          'ドラッグ')
    # **短い語には、もう1つ理由が要る**（項目48-BI）。
    # `しゅぷーる` は実機のメモ tab0 493行。前後は「ぎょえん」
    # 「うにゅーん」で、外来語のつもりではない。
    check('よく使う短い語は寄せる（すくろーる）',
          LW.katakana_for_hiragana('すくろーる', fresh), 'スクロール')
    check('馴染みの薄い短い語は寄せない（しゅぷーる）',
          LW.katakana_for_hiragana('しゅぷーる', fresh), None)
    check('長い語は馴染みを問わず寄せる（ぷらねたりうむ）',
          LW.katakana_for_hiragana('ぷらねたりうむ', fresh),
          'プラネタリウム')

    # --- 距離1の間引きが、本物の距離と食い違わないこと ---
    words = sorted(LW._katakana_seed())[:120]
    mismatch = [(a, b) for a in words[:40] for b in words
                if LW.within_one_edit(a, b)
                != (LW.edit_distance(a, b, limit=1) <= 1)]
    check('速い距離判定が本物と食い違わない', mismatch, [])

    return all_ok


def test_katakana_compound_guard():
    """
    `loanword.dictionary_explains` の回帰テスト。

    実機で出た誤爆:
        コールバック → オールバック（コール＋バック に割れる）
        キログラム   → プログラム  （単体だと未知語。単位のため）
        ハーモニカ   → ハーモニー  （ハー＋モニカ に割れる）
        バックアップ → ロックアップ

    janome の無い環境でも動くよう、字句解析は自前の関数を渡す
    （`dictionary_explains` は tokenize_fn を受け取る作りにしてある）。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import loanword as LW

    print('--- 検証レポート 2-C（カタカナ複合語の関門） ---')

    # 辞書に見立てた語。「キログラム」は**単位**なので、
    # 数字の後ろでしか語にならない、という IPAdic の作りを再現する。
    DICT = {'コール', 'バック', 'ハー', 'モニカ', 'バックアップ',
            'プラモ', 'タリウム', 'ドラッグ'}
    UNIT = {'キログラム'}

    def fake_tokenize(line):
        out = []
        i, n = 0, len(line)
        while i < n:
            if line[i].isdigit():
                out.append((line[i], '名詞:数', '', i, i + 1, False))
                i += 1
                # 数字の直後だけ、単位が1語として立つ
                for u in UNIT:
                    if line.startswith(u, i):
                        out.append((u, '名詞:接尾', '', i, i + len(u), True))
                        i += len(u)
                        break
                continue
            hit = None
            for w in sorted(DICT, key=len, reverse=True):
                if line.startswith(w, i):
                    hit = w
                    break
            if hit:
                out.append((hit, '名詞:一般', '', i, i + len(hit), True))
                i += len(hit)
                continue
            j = i + 1
            while j < n and not line[j].isdigit():
                nxt = any(line.startswith(w, j) for w in DICT)
                if nxt:
                    break
                j += 1
            out.append((line[i:j], '名詞:一般', '', i, j, False))
            i = j
        return out

    def explains(word):
        return LW.dictionary_explains(word, fake_tokenize)

    # --- 触ってはいけないもの（辞書で説明が付く） ---
    check('複合で説明が付く（コールバック）', explains('コールバック'), True)
    check('複合で説明が付く（ハーモニカ）', explains('ハーモニカ'), True)
    check('1語で説明が付く（バックアップ）', explains('バックアップ'), True)
    check('数字の後でだけ語になる単位（キログラム）',
          explains('キログラム'), True)

    # --- 直してよいもの（辞書で説明が付かない） ---
    for typo in ('プセネタリウム', 'プネラタリウム', 'ププラネタリウム',
                 'プラニネタリウム', 'プネタリウム', 'プラネタリウムケ'):
        check(f'辞書で説明が付かないので直せる（{typo}）',
              explains(typo), False)

    # --- 承知の上の取りこぼし ---
    # 辞書の語2つに割れる打ち間違いは、これ以降は直せない。
    # 実機のメモと SPEC.md 全体で測った結果、割れて困るのは
    # 正しい語のほうだったので、この取りこぼしを選んでいる。
    check('辞書の語2つに割れる誤字は取りこぼす（プラモタリウム）',
          explains('プラモタリウム'), True)

    # --- 壊れた材料でも落ちない ---
    check('字句解析が無ければ False', LW.dictionary_explains('コール', None),
          False)
    check('空文字は False', explains(''), False)

    def boom(_line):
        raise RuntimeError('字句解析が壊れた')

    check('字句解析が例外を投げても落ちない',
          LW.dictionary_explains('コールバック', boom), False)

    return all_ok


def test_loanword_and_english():
    """
    うにさんの指定（2026-08-10）で追加した経路の回帰テスト。

    janome の無い環境でも動くよう、語彙は自前で組み立てる
    （loanword.py は形態素解析に頼らない）。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import loanword as LW
    from vocabulary import VocabularyStore

    store = VocabularyStore()
    for _ in range(5):
        store.add('ぷらねたりうむ', 'プラネタリウム', 'その他')
        store.add('こんびにえんす', 'コンビニエンス', 'その他')
        store.add('どらっぐ', 'ドラッグ', 'その他')
        store.add('しょーとかっと', 'ショートカット', 'その他')
        store.add('きー', 'キー', 'その他')

    # --- カタカナの誤字（うにさんの31例の代表）---
    kata = [
        ('プセネタリウム', 'プラネタリウム'),    # 隣接キー
        ('プネラタリウム', 'プラネタリウム'),    # 順序の入れ替わり
        ('プネタリウム', 'プラネタリウム'),      # 脱字
        ('ププラネタリウム', 'プラネタリウム'),  # 同じキーが2度
        ('プラニネタリウム', 'プラネタリウム'),  # 余分な1文字
        ('コンビニエス', 'コンビニエンス'),
    ]
    for typed, want in kata:
        check(f'カタカナ {typed}', LW.fix_katakana_word(typed, store), want)

    # 正しい語は触らない
    check('正しいカタカナは触らない',
          LW.fix_katakana_word('プラネタリウム', store), None)
    # 長音の有無だけの違いは直さない（ダイアログ／ダイアローグ）
    store2 = VocabularyStore()
    for _ in range(5):
        store2.add('だいあろーぐ', 'ダイアローグ', 'その他')
    check('長音の有無だけの違いは直さない',
          LW.fix_katakana_word('ダイアログ', store2), None)
    # 使っている語の複合は縮めない
    check('複合語とみなせる並び',
          LW.is_known_compound(['ショートカット', 'キー'], store), True)
    check('使っていない語の並びは複合語とみなさない',
          LW.is_known_compound(['プラモ', 'タリウム'], store), False)

    # --- ひらがなで書いた外来語をカタカナに ---
    check('ひらがなの外来語をカタカナに',
          LW.katakana_for_hiragana('ぷらねたりうむ', store), 'プラネタリウム')
    check('短い読みはカタカナに直さない',
          LW.katakana_for_hiragana('どらっぐ', store), None)
    check('根拠が揃えば4文字でもカタカナに',
          LW.katakana_for_hiragana('どらっぐ', store, min_length=4),
          'ドラッグ')

    # --- 紛れた1文字 ---
    check('カタカナに挟まれた1文字は並びに含める',
          LW.find_katakana_runs('プラネ１リウム'),
          [(0, 7, 'プラネ１リウム')])
    check('末尾にくっついた文字は含めない',
          LW.find_katakana_runs('（東京上野キャンパス）'),
          [(5, 10, 'キャンパス')])

    # --- 英単語 ---
    store3 = VocabularyStore()
    LW.relearn_english_from_texts(
        ['I like the Planetarium. Planetarium again. Pplanetarium'], store3)
    check('多いほうの形だけを覚える',
          sorted(LW._english_vocabulary(store3)), ['planetarium'])
    for typed in ('Pplanetarium', 'Palnetarium', 'Panetarium',
                  'Ploanetarium'):
        check(f'英単語 {typed}', LW.fix_english_word(typed, store3),
              'Planetarium')
    check('覚えている語は触らない',
          LW.fix_english_word('Planetarium', store3), None)
    check('短い語は対象外', LW.fix_english_word('Plnet', store3), None)

    # --- 誤字のほうが多いメモでも、正しい語を壊さない（2026-08-10）---
    # 実機の語彙に Plaqnetarium が129回で入り、Planetarium と打つと
    # そちらへ直されていた。回数だけで代表形を決めない。
    check('英語らしい綴り', LW.looks_like_english('Planetarium'), True)
    check('q の後が u でない綴り',
          LW.looks_like_english('Plaqnetarium'), False)
    check('母音の無い綴り', LW.looks_like_english('bcdfgh'), False)
    check('同じ字が3つ続く綴り', LW.looks_like_english('aaabbb'), False)
    for w in ('details', 'callout', 'Language', 'Windows', 'strengths',
              'rhythm', 'queue'):
        check(f'ふつうの英単語は英語らしい（{w}）',
              LW.looks_like_english(w), True)

    store4 = VocabularyStore()
    LW.relearn_english_from_texts(
        [('Plaqnetarium ' * 16) + ('Planetarium ' * 2)], store4)
    # 2026-08-12（項目48-BA）: 期待値を1語に変えた。
    # **種の辞書を持つようにしたので、`plaqnetarium` は
    # 「辞書にある語の1文字違い＝打ち間違い」と分かる**。
    # 覚える側の関門（fix_english_word で直せる語は覚えない）が
    # そのまま効いて、**誤字が語彙に入らなくなった**。
    # 種を持つ前は、正しい形を守るために両方覚えるしかなかった。
    check('誤字のほうが多くても正しい形だけを覚える',
          sorted(LW._english_vocabulary(store4)), ['planetarium'])
    check('正しく打った語が誤字へ直されない',
          LW.fix_english_word('Planetarium', store4), None)
    # ここが「英語らしくない綴りは直す側になれない」の本題。
    # 誤字が16回・正しい形が2回でも、**誤字のほうが直る**。
    # SPEC の項目48-o に「`Plaqnetarium → Planetarium` が直るように
    # した」と書いてある、その状態。
    #
    # 2026-08-11 に期待値を None から 'Planetarium' に直した。
    # それまで None だったのは、`relearn_english_from_texts` が
    # どの語も回数1で覚えていたせいで `_override`（回数1の語は、
    # 3回以上書かれた語にしか負けない）が効いていたから。
    # 回数をメモの実出現数にしたら本来の道が通るようになった。
    # **コードに合わせて期待値を緩めたのではなく、SPEC が言っている
    # 動きにようやく追いついた**、という直し。
    check('誤字が多いメモでも、誤字のほうが正しい形に直る',
          LW.fix_english_word('Plaqnetarium', store4), 'Planetarium')

    store5 = VocabularyStore()
    LW.relearn_english_from_texts(
        [('Planetarium ' * 16) + ('Plaqnetarium ' * 2)], store5)
    check('正しい形が多ければ誤字は今までどおり直る',
          LW.fix_english_word('Plaqnetarium', store5), 'Planetarium')

    # 誤字のほうを何度書いていても、正しい形が語彙にあれば直る
    # （実機: Plaqnetarium 65回 / Planetarium 9回で直らなかった）
    store6 = VocabularyStore()
    for _ in range(20):
        store6.add(LW.english_reading('Plaqnetarium'), 'Plaqnetarium', '英語')
    for _ in range(3):
        store6.add(LW.english_reading('Planetarium'), 'Planetarium', '英語')
    check('回数が多くても英語らしくない綴りは直る',
          LW.fix_english_word('Plaqnetarium', store6), 'Planetarium')
    check('英語らしい綴りは何度も書いていれば触らない',
          LW.fix_english_word('Planetarium', store6), None)

    # --- 濁点キーの打ち間違い（とせ → ど）---
    check('濁点キーの隣を押した形',
          C.dakuten_typo_fix('とせらっぐ', store), 'ドラッグ')
    check('短い並びは対象外',
          C.dakuten_typo_fix('とせら', store), None)
    check('語彙にそのままある並びは触らない',
          C.dakuten_typo_fix('こんびにえんす', store), None)

    # --- 記号の言い換え ---
    from candidates import symbol_candidates, is_symbol_word
    check('〜 は F2 の対象', is_symbol_word('〜'), True)
    check('〜 の候補の先頭は から',
          [c['surface'] for c in symbol_candidates('〜')][0], 'から')
    check('普通の語に記号の候補は出ない', symbol_candidates('文字'), [])

    # --- 同一キーの文字（C-4・2026-08-11） ---
    # うにさんの指定:「（は、ゆを候補に出したり、！は、ぬや１を
    # 候補に出したり、同一キーにある文字を候補に出す」
    check('（ は F2 の対象', is_symbol_word('（'), True)
    check('（ の候補に ゆ',
          'ゆ' in [c['surface'] for c in symbol_candidates('（')], True)
    check('！ の候補に ぬ と １',
          all(w in [c['surface'] for c in symbol_candidates('！')]
              for w in ('ぬ', '１')), True)
    check('？ の候補に め',
          'め' in [c['surface'] for c in symbol_candidates('？')], True)
    check('） の候補に よ',
          'よ' in [c['surface'] for c in symbol_candidates('）')], True)
    check('自分自身は候補に入らない',
          '（' in [c['surface'] for c in symbol_candidates('（')], False)
    # かな・英字・数字には出さない（普通の語の候補が押し出される）
    check('かなには同一キーの候補を出さない',
          symbol_candidates('ゆ'), [])
    check('数字には同一キーの候補を出さない',
          symbol_candidates('8'), [])
    check('長音には同一キーの候補を出さない',
          symbol_candidates('ー'), [])
    check('゛ は対象外（うにさんの指定でスルー）',
          symbol_candidates('゛'), [])
    # 句読点は候補は出せるが、F2 の通り道からは外す（項目41の反省）
    check('。 は F2 で止まらない', is_symbol_word('。'), False)
    check('、 は F2 で止まらない', is_symbol_word('、'), False)
    check('。 を直に選べば候補は出る',
          'る' in [c['surface'] for c in symbol_candidates('。')], True)
    return all_ok


# ============================================================
# 項目48-EB: 記号が紛れた英単語（P:lanetarium）
# ============================================================
def test_miskeyed_english():
    """
    英字の並びに**かなのキーの記号**が紛れた形を直す。

    `find_english_runs` は前後に `. _ - @ / :` が付いた並びを
    わざと外している（識別子・URL・パス。`:` は 2026-08-10 に
    「`P:lanetarium` から `lanetarium` を覚えてしまう」ため足した）。
    **覚える側の門はそのまま**にして、直す側にだけ道を足した形。

    記号を抜いた綴りが知っている語になるときだけ通す。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import loanword as LW
    from vocabulary import VocabularyStore

    print('--- 記号が紛れた英単語 ---')

    store = VocabularyStore()

    def fix(line):
        got = LW.find_miskeyed_english(line, store)
        return got[0][2] if got else None

    # --- 通ってほしいもの ---
    check('P:lanetarium → Planetarium', fix('P:lanetarium'), 'Planetarium')
    check('Pl:anetarium → Planetarium', fix('Pl:anetarium'), 'Planetarium')
    check('記号を抜いたうえで打ち間違いも直す',
          fix('P:lanetariumm'), 'Planetarium')
    check('文の途中でも拾う',
          fix('これは P:lanetarium です'), 'Planetarium')

    # --- 通ってはいけないもの ---
    check('パスは直さない（C:\\Users）', fix('C:\\Users'), None)
    check('key:value は直さない', fix('key:value'), None)
    check('識別子の下線は対象の記号にしない（looks_like）',
          fix('looks_like'), None)
    check('ドットは対象の記号にしない（file.name）',
          fix('planetarium.name'), None)
    check('ハイフンは対象の記号にしない（e-mail の形）',
          fix('plane-tarium'), None)
    check('抜いても知らない綴りなら直さない',
          fix('abcd:efghij'), None)
    check('短すぎる綴りは直さない', fix('ab:cd'), None)
    check('正しく書けているものは触らない', fix('Planetarium'), None)
    check('記号が無ければこの道に入らない', fix('Planetariumm'), None)

    return all_ok


# ============================================================
# 項目48-EC: ひらがなで書いた外来語の打ち間違い
# ============================================================
def test_kana_loanword_typo():
    """
    `かーそね` → `カーソル`。うにさんの見本（2026-08-16）:

        かーそねを持って行った ⇒ カーソルを持って行った

    2つの穴が重なっていた:
      1. **4文字のカタカナ語が丸ごと落ちていた**（`MIN_LENGTH` が 5）。
         `かーそる` と正しく打ってもカタカナにならなかった
      2. ひらがなで書いた外来語の**打ち間違い**を直す道が無かった

    4文字まで下げる根拠は**並記**（直した結果が同じ行にある）。
    並記を外すと、守っているセリフ・擬音を軒並み壊す
    （実機メモで実測。12件中6件）ので、**通さない条件を厚く**確かめる。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import loanword as LW
    from vocabulary import VocabularyStore

    print('--- ひらがなで書いた外来語の打ち間違い ---')

    store = VocabularyStore()
    for _ in range(30):
        store.add('かーそる', 'カーソル', 'IT・PC操作')

    # --- 4文字まで下げられること ---
    check('5文字の下限のままなら 4文字は返らない',
          LW.katakana_for_hiragana('かーそる', store), None)
    check('4文字まで下げれば返る',
          LW.katakana_for_hiragana('かーそる', store, min_length=4),
          'カーソル')
    check('打ち間違いも 4文字まで下げれば直る',
          LW.katakana_for_hiragana_typo('かーそね', store, min_length=4),
          'カーソル')
    check('下限のままなら打ち間違いも直らない',
          LW.katakana_for_hiragana_typo('かーそね', store), None)

    # --- 通ってはいけないもの ---
    check('3文字は 4文字の下限でも返らない',
          LW.katakana_for_hiragana('かーそ', store, min_length=4), None)
    check('知らない並びは直らない',
          LW.fix_katakana_word(LW.hiragana_to_katakana('ぬけぬけ'), store,
                               min_length=4), None)
    check('正しく書けているカタカナは触らない',
          LW.fix_katakana_word('カーソル', store, min_length=4), None)

    # 漢字・ひらがなの表記も覚えている読みは「外来語だと言い切れない」
    for _ in range(30):
        store.add('たんご', '単語', 'その他')
        store.add('たんご', 'タンゴ', 'その他')
    check('漢字の表記もある読みはカタカナに寄せない',
          LW.katakana_for_hiragana('たんご', store, min_length=4), None)

    # **同じ門を、打ち間違いの道にも置く**（2026-08-16）。
    # これが無いと、同じ行にカタカナ語があるだけで正しい語が壊れる。
    # 語彙から作った「危ない組」で、4文字まで下げたときの誤検知
    # 31件が**すべてこの形**だった（かめい→カメラ・きろく→キック）。
    for _ in range(30):
        store.add('かめい', '仮名', 'その他')
        store.add('かめら', 'カメラ', 'その他')
    check('正しく書けているかな語は、打ち間違いの道でも触らない',
          LW.katakana_for_hiragana_typo('かめい', store, min_length=3), None)

    # **語の頭は動かさない**。助詞を食う形を塞ぐ（2026-08-16 に踏んだ）。
    #
    #     ドラッグとどらっぐ → ドラッグ**ドラッグ**
    #
    # かなの連続 `とどらっぐ` の頭の `と`（助詞）を1文字消して
    # 当てていた。頭の1文字が保たれることだけを求める。
    check('頭の助詞を食わない（とかーそる → カーソル にしない）',
          LW.katakana_for_hiragana_typo('とかーそる', store, min_length=4),
          None)
    check('門が無ければ食ってしまうことの確認',
          LW.fix_katakana_word(LW.hiragana_to_katakana('とかーそる'), store,
                               min_length=4), 'カーソル')
    check('末尾に1文字余っても直る',
          LW.katakana_for_hiragana_typo('かーそるん', store, min_length=4),
          'カーソル')

    check('ひらがな→カタカナの変換が正しい',
          LW.hiragana_to_katakana('かーそね'), 'カーソネ')

    return all_ok


# ============================================================
# 検証レポート（2026-08-10）2-C: カタカナ複合語が縮む
# ============================================================
def test_char_ngram():
    """
    **日本語の文字の並びの検品**（2026-08-12・項目48-BM）。

    「何にも属さない文字列」を出さないための出口の関門。
    留め金を掛けるのは3つ:

      1. 表が読めていること（`ngram_ja.py` は .py なので
         PyInstaller が必ず持っていく）
      2. **正しく書けている語を止めないこと**（いちばん大事。
         項目48-AR はここで 23.3% を誤判定して却下になった）
      3. 表が無いときは**止めないこと**（黙って厳しくならない）
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import charngram as CN

    print('--- 日本語の文字の並びの検品（項目48-BM）---')
    check('表が読めている', CN.available(), True)

    # **正しく書けている語を止めない**
    for w in ('メモ帳', '単語の繋がり', '平仮名', 'プラネタリウム',
              '文字入力', '改行と行の削除', '正確な位置', '選択操作',
              '間違いの補正', '長い文章', '確認', '実装'):
        check(f'正しい語を止めない（{w}）', CN.looks_unnatural(w), False)

    # かな・漢字以外が混じるものは判断しない（材料に無い）
    for w in ('Planetarium', 'CorrectNote', 'ver1.2.0', 'メモ帳v4'):
        check(f'英数が混じるものは判断しない（{w}）',
              CN.looks_unnatural(w), False)
    check('短すぎるものは判断しない', CN.looks_unnatural('あ'), False)

    # 点の向き（低いほど日本語の並びらしくない）
    check('壊れた並びのほうが点が低い',
          CN.score('ややて二死確保ぬ') < CN.score('単語の繋がり'), True)
    check('メモちょが は メモ帳 より点が低い',
          CN.score('メモちょが') < CN.score('メモ帳'), True)

    # --- メモから育てる（項目48-BN）---
    import os, tempfile
    saved_path, saved_learned, saved_seen = (CN._STORE_PATH, CN._LEARNED,
                                             CN._SEEN)
    saved_table, saved_ctx = CN._TABLE, CN._CONTEXT
    tmp = tempfile.mkdtemp()
    try:
        CN._STORE_PATH = os.path.join(tmp, 'charngram.json')
        CN._LEARNED, CN._SEEN = {}, set()
        CN._rebuild()
        before = CN.stats()
        check('直すところが無かった行を覚える',
              CN.learn('きょうはとてもよい天気なので散歩に出かけました'),
              True)
        check('同じ行は二度数えない',
              CN.learn('きょうはとてもよい天気なので散歩に出かけました'),
              False)
        check('誤字の見本が載っている行は材料にしない',
              CN.learn('たんご ⇒ 単語'), False)
        check('英数が混じる行も材料にしない',
              CN.learn('ここで correct_line を呼ぶ'), False)
        after = CN.stats()
        check('育てたぶんが増えている', after[1] > before[1], True)
        check('覚えた行が1行', after[2], 1)
        check('書き出せる', CN.save(), True)
        check('変わっていなければ書き出さない', CN.save(), False)
        # **起動し直しても数え直さない**（`hash()` は使えない・学び20）
        CN._LEARNED, CN._SEEN = None, None
        CN._read_learned()
        check('起動し直しても覚えた行が残る', len(CN._SEEN), 1)
        check('起動し直しても同じ行は数えない',
              CN.learn('きょうはとてもよい天気なので散歩に出かけました'),
              False)
    finally:
        CN._STORE_PATH, CN._LEARNED, CN._SEEN = (saved_path, saved_learned,
                                                 saved_seen)
        CN._TABLE, CN._CONTEXT = saved_table, saved_ctx
        try:
            import shutil
            shutil.rmtree(tmp)
        except Exception:
            pass

    # **表が無いときは止めない**
    saved_t, saved_m = CN._TABLE, CN._MISSING
    try:
        CN._TABLE, CN._MISSING = None, True
        check('表が無ければ止めない', CN.looks_unnatural('ややて二死確保ぬ'),
              False)
        check('表が無ければ点は 0', CN.score('ややて二死確保ぬ'), 0.0)
    finally:
        CN._TABLE, CN._MISSING = saved_t, saved_m

    return all_ok


# ============================================================
# 項目48-EA: 漢字にしたかったのに、かなのまま残った語
# ============================================================
def test_kana_to_kanji():
    """
    **IMEが一部だけ変換できた形**を見分けて、残ったかなを漢字にする。

    うにさんの指定（2026-08-16）:

    > 漢字変換したかったかどうかの**意図を察します**。誤入力に
    > よって IME が一部を漢字変換できずに平仮名のまま通すケースが
    > あります。その場合は**漢字が一部入っていたりする**ので、
    > それを判定して漢字変換したかったが平仮名になったものを
    > 見分けます。

    見分ける印は「ひらがなの連続が**漢字と地続き**」であること。
    これは「ひらがなで打たれたものはひらがなのまま直す」の例外
    なので、**通す条件より通さない条件のほうを厚く**確かめる。
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

    print('--- かな→漢字（漢字と地続きのときだけ） ---')

    store = VocabularyStore()
    for _ in range(40):
        store.add('たんご', '単語', 'その他')      # 漢字でしか書かない
        store.add('つながり', '繋がり', 'その他')
        store.add('つながり', 'つながり', 'その他')  # かなでも書く
        store.add('かよわい', 'かよわい', 'その他')  # 漢字の表記が無い
    for _ in range(4):
        store.add('ほせい', '補正', 'その他')       # 実績が乏しい

    pick = C._kanji_surface_for_reading

    # --- 通ってほしいもの ---
    check('漢字でしか書かない語は返る', pick('たんご', store), '単語')

    # --- 通ってはいけないもの ---
    check('かなでも書く語は返らない（つながり）',
          pick('つながり', store), None)
    check('漢字の表記が無い語は返らない（かよわい）',
          pick('かよわい', store), None)
    check('使用実績が乏しければ返らない（補正 4回）',
          pick('ほせい', store), None)
    check('語彙に無い読みは返らない', pick('ぬけぬけ', store), None)

    # --- 「誤字の見本らしい行」の見分け ---
    ex = C._LOOKS_LIKE_EXAMPLE
    check('引用符のある行は見本とみなす',
          bool(ex.search('「たんこ」に直せば「たんご」に補正できます')), True)
    check('矢印のある行は見本とみなす',
          bool(ex.search('たんご ⇒ 単語')), True)
    check('英数のある行は見本とみなす',
          bool(ex.search('たんごのつながり 10 10')), True)
    check('ふつうの文は見本とみなさない',
          bool(ex.search('たんごの繋がり')), False)

    # --- 「漢字と地続き」の見分け ---
    def touching(line, s, e):
        return ((s > 0 and C.is_kanji(line[s - 1]))
                or (e < len(line) and C.is_kanji(line[e])))
    check('直後が漢字なら地続き（たんごの繋がり）',
          touching('たんごの繋がり', 0, 4), True)
    check('直前が漢字なら地続き（かな打ちでのほせい）',
          touching('かな打ちでのほせい', 3, 9), True)
    check('前後に漢字が無ければ地続きでない（かくごっ）',
          touching('かくごっ', 0, 4), False)
    check('前後に漢字が無ければ地続きでない（たんごのつながり）',
          touching('たんごのつながり', 0, 8), False)

    check('栓を切れる', isinstance(C._KANA_TO_KANJI, bool), True)

    return all_ok


def test_oddness_rules():
    """
    **異様さの印（`oddness.py`）の、AI が落とし込んだ規則**（項目48-IP）。

    うにさんの指定「AIの基準を活用した異様さの判定が重要」。
    印は設計27 の入口（`_reopen_odd_chunk`）と受け入れ（異様さが消えたか）
    の両方で使うので、**正しい語に立たないこと**を先に固定する。

    足した2つ（どちらも語の一覧ではない）:
      (1') 否定の接頭辞（不・非・未・無）を頭に持つ語は何にでも付く
           → `型不一致` に立たない
      塊まるごと（＋送り仮名2字まで）が表の語なら、その中の対は見ない
           → `同音異義語`（解析は 同音|異義|語 と割る）`見做す` に立たない
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    print('--- 異様さの印（項目48-IP） ---')
    import oddness
    if not oddness.available():
        print('   （seed_japanese.txt.gz が無いので飛ばす）')
        return True

    def tok_of(parts):
        """(表記, 品詞) の並びから、`make_tokenizer` が返す形を作る。"""
        def fn(text):
            out, pos = [], 0
            for surf, p in parts:
                out.append((surf, p, '', pos, pos + len(surf), True))
                pos += len(surf)
            return out
        return fn

    check('否定の接頭辞: 型＋不一致 はくっつく',
          oddness.can_join('型', '名詞:一般', '不一致', '名詞:一般'), True)
    check('否定の接頭辞でも、残りが語でなければ通さない',
          oddness.can_join('型', '名詞:一般', '不釣', '名詞:一般'), False)
    check('素＋帰任 は今までどおり異様（1字＋動作性名詞）',
          oddness.can_join('素', '名詞:一般', '帰任', '名詞:サ変接続'), False)
    check('野外＋文章 は今までどおり異様',
          oddness.can_join('野外', '名詞:一般', '文章', '名詞:一般'), False)

    check('塊まるごとが表の語（同音異義語）なら中の対は見ない',
          oddness.is_odd_run('同音異義語', tok_of(
              [('同音', '名詞:一般'), ('異義', '名詞:一般'),
               ('語', '名詞:接尾')])), [])
    check('塊が語でなければ（同音異義）対はそのまま立つ',
          oddness.is_odd_run('同音異義', tok_of(
              [('同音', '名詞:一般'), ('異義', '名詞:一般')])),
          [('同音', '異義')])
    check('送り仮名まで含めて語（見做す）なら立たない',
          oddness.is_odd_run('見做して', tok_of(
              [('見', '名詞:一般'), ('做', '名詞:一般'),
               ('し', '動詞:自立'), ('て', '助詞:接続助詞')])), [])
    check('差釣れません は今までどおり立つ',
          oddness.is_odd_run('差釣れません', tok_of(
              [('差', '名詞:一般'), ('釣れ', '動詞:自立'),
               ('ませ', '助動詞'), ('ん', '助動詞')])), [('差', '釣れ')])
    check('野外文章 は今までどおり立つ',
          oddness.is_odd_run('野外文章', tok_of(
              [('野外', '名詞:一般'), ('文章', '名詞:一般')])),
          [('野外', '文章')])

    # **紫で見せる位置**（項目48-IR）。解析の始まり・終わりを使う。
    check('位置つきで返せる',
          oddness.odd_spans('野外文章です', tok_of(
              [('野外', '名詞:一般'), ('文章', '名詞:一般'),
               ('です', '助動詞')])), [(0, 4)])

    def tok_with_gap(text):
        # 行頭の空白2つを解析が落とした形（位置だけ正しい）
        return [('素', '名詞:一般', '', 2, 3, True),
                ('帰任', '名詞:サ変接続', '', 3, 5, True)]
    check('解析が落とした空白のぶんずれない（行頭の空白）',
          oddness.odd_spans('  素帰任', tok_with_gap), [(2, 5)])
    return all_ok


def test_odd_rules_48is():
    """
    **異様なものをそのままにしない**（項目48-IS・2026-08-23）。

    うにさんの指定:「壊れるリスクを恐れすぎて前へ進んでいない」
    「拮抗したら何もしないは逆効果。異様であれば最有力の候補に補正する。
      優先順位が付かなければ平仮名1文字の頻度で決める」
    「`ひ|らん|が|な` が読めるは意味が分かりません」

    ここで固定するのは判断の部品3つ:
      - `_kana_run_explained`  かなの語と機能語で説明できるか（新しい「読める」）
      - `_break_tie_by_kana_frequency`  字の頻度で決める
      - `_covered_by_known`  活用語尾（します）も部品に数える
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    print('--- 異様なものをそのままにしない（項目48-IS） ---')
    import corrector as C
    import oddness
    if not oddness.available():
        print('   （seed_japanese.txt.gz が無いので飛ばす）')
        return True

    check('ひらんがな は説明できない（ひ 1字が残る）',
          C._kana_run_explained('ひらんがな'), False)
    check('すきにん は説明できない（すき|にん は語の直結）',
          C._kana_run_explained('すきにん'), False)
    check('たんあご は説明できない（たん|あご は語の直結）',
          C._kana_run_explained('たんあご'), False)
    check('かくにん は説明できる（表の語そのもの）',
          C._kana_run_explained('かくにん'), True)
    check('たんごのつながり は説明できる（語＋助詞＋語）',
          C._kana_run_explained('たんごのつながり'), True)
    check('そのためです は説明できる（機能語だけ）',
          C._kana_run_explained('そのためです'), True)
    check('漢字を含む並びは意見なし（True）',
          C._kana_run_explained('漢字かな'), True)

    check('字の頻度: い・ん の多い読みが勝つ',
          C._break_tie_by_kana_frequency(
              [('ぬぺ', 1.0, 1), ('いん', 1.0, 1)]), 'いん')
    check('字の頻度: 同点なら None（呼び出し側が先頭を採る）',
          C._break_tie_by_kana_frequency(
              [('いん', 1.0, 1), ('んい', 1.0, 1)]), None)

    from vocabulary import VocabularyStore
    store = VocabularyStore()
    for _ in range(3):
        store.add('かくにん', '確認', 'その他')
    check('敷き詰め: 活用語尾 します も部品に数える',
          C._covered_by_known('かくにんします', store, False), True)
    check('敷き詰め: 語彙に無い並びは通らない',
          C._covered_by_known('のりんします', store, False), False)
    return all_ok


def test_kana_fix_48it():
    """
    **平仮名を平仮名に補正する**（項目48-IT・2026-08-23）。うにさんの指定:

      「ような書式ににして」の「ににして」は異様。文字列ではなく要素で
      判定する。「に」の連続を押しすぎと捉えれば「にして」。
      「すねると」は「ね」「る」が隣接キーで巻き込み。片方が消えて
      「すねと」「すると」が候補、自然に繋がるほうを採る。
      「かーそね」は2文字目から隣接キーを試し「かーそれ」→ カーソル。
      見つからなければ脱字も疑う。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    print('--- 平仮名を平仮名に補正する（項目48-IT） ---')
    import corrector as C
    f = C._fix_functional_run
    check('押しすぎ: ににして → にして', f('ににして'), 'にして')
    check('巻き込み: すねると → すると', f('すねると'), 'すると')
    check('巻き込み: いいですよわね → いいですよね',
          f('いいですよわね'), 'いいですよね')
    check('機能語だけで説明が付く並びは触らない（させないわよ）',
          f('させないわよ'), None)
    check('隣のキーが無ければ触らない（わしらの）', f('わしらの'), None)
    check('漢字の直後の送り仮名は落とさない（変わらない の わらない）',
          f('わらない', after_kanji=True), None)
    check('うまく から ま を落とした形は機能語の並びにならない',
          f('がうまく'), None)
    check('かーそね → カーソル は2文字目以降の隣のキー1つ',
          C._loan_typo_plausible('かーそね', 'カーソル'), True)
    check('1文字目の置き換えでは説明しない',
          C._loan_typo_plausible('さーそる', 'カーソル'), False)
    # 実機のメモで壊した形（要素の決まりで守る）
    check('「し」は1字の部品（効きますし は異様ではない）',
          f('ますし'), None)
    check('したいということで は異様ではない',
          f('したいということで'), None)
    check('1つ目が機能語の尻尾なら連続ではない（ことと＝こと＋と）',
          f('ないことと'), None)
    check('「ん」は1字の助詞の直後に置けない（これはん にはしない）',
          f('これははん'), None)
    check('外来語の印が無い並びの脱字・余分は打ち間違いの形と見ない（たんこ → タコ）',
          C._loan_typo_plausible('たんこ', 'タコ'), False)
    check('同（げんい → ゲンセイ）',
          C._loan_typo_plausible('げんい', 'ゲンセイ'), False)
    check('印（長音）があれば脱字も疑う（きーぼど → キーボード）',
          C._loan_typo_plausible('きーぼど', 'キーボード'), True)
    check('かなで書いた語が表のカタカナ語なら触らない（すりーぷ＝スリープ → スープ にしない・項目48-IU）',
          C._loan_typo_plausible('すりーぷ', 'スープ'), False)
    check('2字の並びは隣のキーでも触らない（めね → メモ にしない）',
          C._loan_typo_plausible('めね', 'メモ'), False)
    check('なければ は機能語（成立しなければ は異様ではない）',
          f('しなければ'), None)
    return all_ok


def test_resplit_48iw():
    """
    **違和感の範囲を左端から要素で割り直す**（設計32・項目48-IW・2026-08-23）。
    うにさんの分析:

      「これからな学外しょつする」を左から読んで違和感があるのは
      「な学外しょつする」。「これから」で区切りがあると考え、「学外」を
      がくがい と読むより先に、頭の「な」と「学」が繋がるかを人は考える。
      ここから「ながい」が出せれば前の「これから」とも合う。残る
      「外しょつ」は がいしょつ → がいしゅつ と思えれば、あとは難しくない。

    janome 無し（簡易分割）で、要素の決まりだけを確かめる。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    print('--- 違和感の範囲を左端から要素で割り直す（設計32・項目48-IW） ---')
    import corrector as C
    from vocabulary import VocabularyStore, find_known_readings_flex
    store = VocabularyStore()
    for _ in range(2):
        store.add('ながく', '長く', 'その他')
        store.add('これから', 'これから', 'その他')
        store.add('がく', 'ガク', 'その他')        # 読みに開くだけの表記
    store.add('がいしゅつ', '外出', 'その他')      # 初期語彙と同じ回数1
    store.add('がくがい', '学外', 'その他')        # 漢字の並び自体は在る語
    tok = C.make_tokenizer(store)
    f = C._resplit_by_elements

    def run(line, start, end, method='kana'):
        chunk = line[start:end]
        return f(line, start, end, chunk, tok(line), store, tok,
                 dict_index=None, input_method=method)

    check('な＋学(がく)＝長く・外(がい)＋しょつ→がいしゅつ＝外出・する は機能語',
          run('これからな学外しょつする', 5, 12), (4, '長く外出する', 'その他'))
    check('行全体でも同じ（B道の しょつ→しょーつ より先に決まる）',
          C.correct_line('これからな学外しょつする', store, tok,
                         find_known_readings_flex,
                         input_method='kana')['corrected'],
          'これから長く外出する')
    check('頭の語は漢字の読みをかなに開くだけ（がく→ガク）では採らない',
          run('これから学外しょつする', 4, 11), None)
    check('頭のかなが語の途中（大きな の な）なら足さない',
          run('大きな学外しょつする', 3, 10), None)
    check('尻尾の語の読みが在る語（がいしゅつ）なら、それは正しい語。触らない',
          run('これからな学外しゅつする', 5, 12), None)
    check('読みの立たない語が無ければ入口に入らない（違和感の印）',
          run('これからな学外がいしゅつ', 5, 12), None)
    check('ローマ字入力では ょ→ゅ（o→u）は隣のキーでないので直さない',
          run('これからな学外しょつする', 5, 12, method='romaji'), None)
    check('尾が機能語で説明できなければ採らない（しょつぷ）',
          run('これからな学外しょつぷ', 5, 11), None)
    # 育ちの readcheck で壊した形（2026-08-23）: 頭のかな無しで正しい語
    # `昨日` を 咲く＋平地 に割った。頭のかなが無ければ割る理由が無い
    store.add('さく', '咲く', 'その他'); store.add('さく', '咲く', 'その他')
    store.add('ひらち', '平地', 'その他')
    store.add('きのう', '昨日', 'その他')
    check('頭のかなが無ければ、正しい語（昨日）を割らない',
          run('昨日ゅちうかいを見ました。', 0, 7), None)
    # 漢字1字: 頭の語なし・尻尾の語（がい＋しょつ → がいしゅつ）と尾だけ
    # （うにさんの実機 `外しょつする`・2026-08-23）
    check('漢字1字: 外(がい)＋しょつ → 外出・する は機能語',
          run('外しょつする', 0, 6), (0, '外出する', 'その他'))
    check('漢字1字でも、尻尾の読みが在る語なら触らない（外しゅつする）',
          run('外しゅつする', 0, 6), None)
    # 控えの指紋は「起動したときのエンジン」を表す（項目48-IW・実機で発覚）。
    # 動いている途中で corrector.py が差し替わっても、指紋は変わらない
    import analysis_cache, os, tempfile
    _d = tempfile.mkdtemp(prefix='cn_stamp_')
    _f = os.path.join(_d, 'corrector.py')
    with open(_f, 'w', encoding='utf-8') as _fh:
        _fh.write('# a' + chr(10))
    analysis_cache._ENGINE_SOURCES_SEEN = None
    _s1 = analysis_cache._engine_source_stamp(_d)
    with open(_f, 'a', encoding='utf-8') as _fh:
        _fh.write('# 差し替え' + chr(10))
    _s2 = analysis_cache._engine_source_stamp(_d)
    analysis_cache._ENGINE_SOURCES_SEEN = None
    check('控えの指紋は起動時の大きさで固定（途中の差し替えでずれない）',
          _s1 == _s2 and bool(_s1), True)
    return all_ok


def test_common_odd_48ix():
    """
    **共通して補正される判定**（項目48-IX・2026-08-23）。うにさんの指定:

      「待ち外 が異様と判定できればよい。田部井号して が異様と判定できれば
        補正できそう。これら単語にだけ効く局所的なものではなく、共通して
        補正される判定を」

    (1) 設計30: 打った読み（IME の対）が語彙の語にそのまま在り、いまの表記が
        語として無いなら組み直す（待ち外 → 間違い）
    (2) 印: 漢字の名詞（一般・接尾・固有）＋「し／する」直付きは異様
        （号して・誤字して）。形容動詞語幹・〜化・お〜する は文法で除く
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    print('--- 共通して補正される判定（項目48-IX） ---')
    import corrector as C
    import kanji_guess as K
    from vocabulary import VocabularyStore
    store = VocabularyStore()
    for _ in range(2):
        store.add('まちがい', '間違い', 'その他')
        store.add('かんりょう', '完了', 'その他')
        store.add('かんりょう', '官僚', 'その他')     # 官僚 は語として在る
    tok = C.make_tokenizer(store)
    pairs = {'待ち外': ['まちがい'], '官僚': ['かんりょう'], '待機': ['たいき']}
    old = K._IME_READINGS_PROVIDER
    K.set_ime_readings_provider(lambda s: pairs.get(s, []))
    try:
        f = C._ime_exact_respell
        check('打った読み まちがい が語彙の 間違い にそのまま在り、待ち外 は語として無い → 間違い',
              f('待ち外', store, tok, None), ('間違い', 'その他'))
        check('いまの表記が語彙に在る（官僚）なら本人の選択。触らない',
              f('官僚', store, tok, None), None)
        check('対が無い表記には何も言わない',
              f('待機', store, tok, None), None)
        K.set_ime_readings_provider(None)
        check('対の置き場が無ければ素通り', f('待ち外', store, tok, None), None)
    finally:
        K.set_ime_readings_provider(old)

    import oddness
    if not oddness.available():
        print('   （seed_japanese.txt.gz が無いので印の確認は飛ばす）')
        return all_ok

    def tok_of(parts):
        def fn(text):
            out, pos = [], 0
            for surf, p in parts:
                out.append((surf, p, '', pos, pos + len(surf), True))
                pos += len(surf)
            return out
        return fn

    check('号(接尾)＋し 直付きは異様（田部井号して）',
          oddness.is_odd_run('田部井号して', tok_of([('田部井', '名詞:固有名詞'), ('号', '名詞:接尾'), ('し', '動詞:自立'), ('て', '助詞:接続助詞')])),
          [('号', 'し')])
    check('誤字(一般)＋し も異様',
          oddness.is_odd_run('誤字して', tok_of([('誤字', '名詞:一般'), ('し', '動詞:自立'), ('て', '助詞:接続助詞')])),
          [('誤字', 'し')])
    check('動作性名詞（サ変接続）＋し は正しい（確認して）',
          oddness.is_odd_run('確認して', tok_of([('確認', '名詞:サ変接続'), ('し', '動詞:自立'), ('て', '助詞:接続助詞')])),
          [])
    check('形容動詞語幹＋し は正しい（安定して）',
          oddness.is_odd_run('安定して', tok_of([('安定', '名詞:形容動詞語幹'), ('し', '動詞:自立'), ('て', '助詞:接続助詞')])),
          [])
    check('〜化＋し は正しい（無効化して）',
          oddness.is_odd_run('無効化して', tok_of([('無効', '名詞:形容動詞語幹'), ('化', '名詞:接尾'), ('し', '動詞:自立'), ('て', '助詞:接続助詞')])),
          [])
    check('お＋連用形＋する は正しい（お渡しする）',
          oddness.is_odd_run('お渡しする', tok_of([('お', '接頭詞:名詞接続'), ('渡し', '名詞:一般'), ('する', '動詞:自立')])),
          [])
    check('カタカナ語＋する は見ない（ドラッグする）',
          oddness.is_odd_run('ドラッグする', tok_of([('ドラッグ', '名詞:一般'), ('する', '動詞:自立')])),
          [])
    return all_ok


def test_kana_alphabet_48iz():
    """
    **かなで書いたアルファベットの読みを英字に戻す**（項目48-IZ・2026-08-23）。
    うにさんの指定「平仮名かカタカナで、アルファベットの発音を書いたら
    アルファベットに補正する」。項目48-IB で「いまの経路に無い機能」と
    して残してあった5組。

    見張るのは**門**のほう。表（`alphabet.py`）は足しても壊れないが、
    門をゆるめると普通の日本語が英字になる。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    print('--- かな書きのアルファベット（項目48-IZ） ---')
    import alphabet as A
    import corrector as C
    from vocabulary import VocabularyStore

    # --- 表と分解（`alphabet.py` 単体）---
    check('エフ → F', A.spell_out('エフ'), 'F')
    check('えいちでぃーえむあい → HDMI', A.spell_out('えいちでぃーえむあい'), 'HDMI')
    check('えいちでーえむあい も HDMI（でー も D）',
          A.spell_out('えいちでーえむあい'), 'HDMI')
    check('えいち は H（えい＋ち に切らない＝長いほうから当てる）',
          A.spell_out('えいち'), 'H')
    check('1文字でも余ったら None（カーソル）', A.spell_out('カーソル'), None)
    check('1文字でも余ったら None（ディスプレイ）',
          A.spell_out('ディスプレイ'), None)
    check('ですます は綴りではない', A.spell_out('ですます'), None)

    # --- 門（`corrector.py` 側）---
    store = VocabularyStore()
    tok = C.make_tokenizer(store)

    def fix(line):
        out, prev = [], 0
        for s0, e0, rep in C._fix_kana_alphabet(line, store, tok, None):
            out.append(line[prev:s0]); out.append(rep); prev = e0
        out.append(line[prev:])
        return ''.join(out)

    check('エフ2 → F2（字1つでも、数字が続くなら綴り）', fix('エフ2'), 'F2')
    check('えふ2 → F2', fix('えふ2'), 'F2')
    check('エフエフ9 → FF9', fix('エフエフ9'), 'FF9')
    check('えいちでぃーえむあい → HDMI', fix('えいちでぃーえむあい'), 'HDMI')
    check('えいちでーえむあい → HDMI', fix('えいちでーえむあい'), 'HDMI')
    check('末尾の助詞は剥がす（ゆーえすびーの端子）',
          fix('ゆーえすびーの端子'), 'USBの端子')
    check('数字の後ろの助詞は英数字ではない（えふ2を押す）',
          fix('えふ2を押す'), 'F2を押す')

    # 守る側
    check('(2) 字1つで数字が続かないなら触らない（える）', fix('える'), 'える')
    check('(2) 同じく あい', fix('あい'), 'あい')
    check('(3) 1語として在るなら触らない（わいわい）',
          fix('わいわい'), 'わいわい')
    check('(3) だぶる も語（W にしない）', fix('だぶる'), 'だぶる')
    check('(6) 同じ字の繰り返しだけなら触らない（きゅーきゅー）',
          fix('きゅーきゅー'), 'きゅーきゅー')
    check('(1) まるごと読めなければ触らない（カーソル）',
          fix('カーソル'), 'カーソル')
    check('(1) ディスプレイ も触らない', fix('ディスプレイ'), 'ディスプレイ')
    check('(4) 直前が漢字なら触らない（送り仮名と区別が付かない）',
          fix('見えふ2'), '見えふ2')
    check('(5) 直前が英字なら触らない', fix('Xえふ2'), 'Xえふ2')
    check('日本語の文はそのまま', fix('これから長く外出する'),
          'これから長く外出する')
    check('機能語だけの行はそのまま', fix('いいですよね'), 'いいですよね')
    return all_ok


def test_kbest_48jc():
    """
    **半角入力の候補を k 本追い、異様さで裁く**（項目48-JC・2026-08-25）。

    うにさんの指定（2026-08-24）:
      「`買い脊柱` が異様という判定が要ります。
        **異様ならさらに次の変換候補を追ってもらいます**」

    2つの部品を見る:
      (1) `oddness.is_odd_run` の**連用形＋名詞の門**——`買い脊柱` に
          立ち、複合動詞（貼り付け）・連体形（閉じる機能）・
          形容詞（正しい単語）・表の語（買い物）には立たない
      (2) `kana_to_kanji_where_possible` の **judge**——異様なら
          その変換を封じて次の候補を組む。judge 無しは今までどおり
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    print('--- 候補を k 本追い、異様さで裁く（項目48-JC） ---')
    import oddness
    if not oddness.available():
        print('   （seed_japanese.txt.gz が無いので飛ばす）')
        return True

    def tok_of(parts):
        """(表記, 品詞) の並びから、`make_tokenizer` が返す形を作る。"""
        def fn(text):
            out, pos = [], 0
            for surf, p in parts:
                out.append((surf, p, '', pos, pos + len(surf), True))
                pos += len(surf)
            return out
        return fn

    # --- (1) 連用形＋名詞の門 ---
    check('買い脊柱 に立つ（動詞の連用形＋名詞）',
          oddness.is_odd_run('買い脊柱', tok_of(
              [('買い', '動詞:自立'), ('脊柱', '名詞:一般')])),
          [('買い', '脊柱')])
    check('貼り付け は立たない（後ろが動詞＝複合動詞）',
          oddness.is_odd_run('貼り付け', tok_of(
              [('貼り', '動詞:自立'), ('付け', '動詞:自立')])), [])
    check('閉じる機能 は立たない（連体形＝う段）',
          oddness.is_odd_run('閉じる機能', tok_of(
              [('閉じる', '動詞:自立'), ('機能', '名詞:サ変接続')])), [])
    check('正しい単語 は立たない（前が形容詞）',
          oddness.is_odd_run('正しい単語', tok_of(
              [('正しい', '形容詞:自立'), ('単語', '名詞:一般')])), [])
    check('買い物 は立たない（塊まるごとが表の語）',
          oddness.is_odd_run('買い物', tok_of(
              [('買い', '動詞:自立'), ('物', '名詞:非自立')])), [])
    check('読み込み は立たない（後ろが動詞の名詞化でなく動詞そのもの）',
          oddness.is_odd_run('読み込み', tok_of(
              [('読み', '動詞:自立'), ('込み', '動詞:非自立')])), [])

    # --- (2) judge で次の候補を追う ---
    from halfwidth import kana_to_kanji_where_possible as _k2k

    class _FS:
        """lookup だけの偽の語彙（買い30・脊柱2・解析608）。"""
        def __init__(self, m):
            self.m = m

        def lookup(self, r):
            return self.m.get(r, [])

    fs = _FS({'かい': [{'surface': '買い', 'count': 30}],
              'せきちゅう': [{'surface': '脊柱', 'count': 2}],
              'かいせき': [{'surface': '解析', 'count': 608}]})

    check('judge 無しは今までどおり（被覆 7/7 が勝つ）',
          _k2k('かいせきちゅう', fs), '買い脊柱')
    check('judge が空を返せば同じ答え',
          _k2k('かいせきちゅう', fs, judge=lambda t: []), '買い脊柱')
    check('異様なら次の候補＋閉じた接尾（買い脊柱 → 解析中）',
          _k2k('かいせきちゅう', fs,
               judge=lambda t: [(0, len(t))] if t == '買い脊柱' else []),
          '解析中')
    check('全部異様と言われたら、変換を全部封じてかなのまま返す',
          _k2k('かいせきちゅう', fs, judge=lambda t: [(0, len(t))]),
          'かいせきちゅう')
    check('judge が例外を出しても止まらない（意見なし扱い）',
          _k2k('かいせきちゅう', fs,
               judge=lambda t: (_ for _ in ()).throw(RuntimeError())),
          '買い脊柱')

    # --- 変換できた語の直後の閉じた接尾（項目48-JE・ちゅう → 中）---
    # うにさんの正解メモ `tepga(4 ⇒ 解析中`。1字の表記は語彙からは
    # 採らない門があるので、**漢字2字以上に変換できた語の直後**に
    # 限った閉じた文法の類（回数は見ない・48-HU とはぶつからない）。
    fs2 = _FS({'かいせき': [{'surface': '解析', 'count': 608}]})
    check('接尾: 変換できた語の直後の ちゅう は 中（解析中）',
          _k2k('かいせきちゅう', fs2), '解析中')
    check('接尾: 後ろが助詞でも付く（解析中に）',
          _k2k('かいせきちゅうに', fs2), '解析中に')
    check('接尾: ひらがなが続くなら語の途中かもしれないので付けない'
          '（ちゅうい＝注意）',
          _k2k('かいせきちゅうい', fs2), '解析ちゅうい')
    check('接尾: 前に変換できた語が無ければ付けない',
          _k2k('ちゅうに', fs2), 'ちゅうに')
    check('接尾: judge が接尾の範囲を異様と言ったら置かない',
          _k2k('かいせきちゅう', fs2,
               judge=lambda t: [(0, len(t))] if '中' in t else []),
          '解析ちゅう')

    # --- 配線の見張り（学び22: 裁く口は半角の道4本全部に）---
    src_c = open('corrector.py', encoding='utf-8').read()
    check('corrector の半角の道4本全部が judge を渡している'
          '（全角・かな配列・ローマ字・かな打ちのローマ字）',
          src_c.count('judge=_odd_judge'), 4)
    import re as _re
    src_h = open('halfwidth.py', encoding='utf-8').read()
    _calls = [m.end() for m in _re.finditer(
        r'(?<!def )kana_to_kanji_where_possible\(', src_h)]
    check('halfwidth の中の kana_to_kanji 呼び出しが全部 judge を運ぶ',
          (len(_calls) >= 6,
           all('judge=judge' in src_h[p:p + 120] for p in _calls)),
          (True, True))
    return all_ok


def test_odd_recognition_48jg():
    """
    **異様の認識を広げる**（項目48-JG・2026-08-25）。

    うにさんの指定「異様であれば何かしらの補正をします。そのままには
    しません。**異様であると認識しているのかが重要です。紫の表示が
    なければその判定が必要です**」。

    見るもの:
      (1) 辞書に無い断片＋漢字始まりの内容語 の印（にゅ力・乳リュク）
          と、その盾（一般語の表 `general_words`・擬態語・かな崩し）
      (2) 区画の1字（行・欄…）と位置の1字（縦…）の後ろ側は意見しない
          （空白行・A4用紙縦 の誤検知）
      (3) 姓＋名（辞書の固有名詞どうし）は意見しない（高橋佑）。
          **片側だけ・読みの立たない固有名詞では黙らせない**（悠久子帝）
      (4) 設計27 の門: 読みを編集した直しで表の差が漢字1字なら採らない
          （空白くい・高橋よう の型）
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    print('--- 異様の認識を広げる（項目48-JG） ---')
    import oddness
    if not oddness.available():
        print('   （seed_japanese.txt.gz が無いので飛ばす）')
        return True

    def tok_of(parts):
        """(表記, 品詞, 読みが立つか) から make_tokenizer の形を作る。"""
        def fn(text):
            out, pos = [], 0
            for surf, p, known in parts:
                out.append((surf, p, surf if known else '',
                            pos, pos + len(surf), known))
                pos += len(surf)
            return out
        return fn

    # (1) 辞書に無い断片
    check('ゅ（小書き1字）＋力 に立つ',
          oddness.is_odd_run('にゅ力ミス', tok_of(
              [('に', '助詞:格助詞', True), ('ゅ', '名詞:一般', False),
               ('力', '名詞:接尾', True), ('ミス', '名詞:サ変接続', True)])),
          [('ゅ', '力')])
    check('乳＋リュク（カタカナ断片）に立つ',
          oddness.is_odd_run('乳リュク', tok_of(
              [('乳', '名詞:一般', True), ('リュク', '名詞:一般', False)])),
          [('乳', 'リュク')])
    check('ょじえかく（かな断片）＋乱 に立つ',
          oddness.is_odd_run('ょじえかく乱', tok_of(
              [('ょじえかく', '名詞:一般', False),
               ('乱', '名詞:一般', True)])),
          [('ょじえかく', '乱')])
    check('アプリ は辞書に無くても一般語の表が守る（アプリ内）',
          oddness.is_odd_run('アプリ内', tok_of(
              [('アプリ', '名詞:一般', False), ('内', '名詞:接尾', True)])),
          [])
    check('擬態語（ぱちりと）は立たない',
          oddness.is_odd_run('ぱちりと雨傘', tok_of(
              [('ぱちりと', '名詞:一般', False),
               ('雨傘', '名詞:一般', True)])), [])
    check('かな崩し（ぴよピヨ・相手が漢字でない）は立たない',
          oddness.is_odd_run('ぴよピヨ', tok_of(
              [('ぴよ', '名詞:一般', False), ('ピヨ', '名詞:一般', False)])),
          [])

    # (2) 区画・位置の1字の後ろ側
    check('空白＋行 はくっつく（区画の1字）',
          oddness.can_join('空白', '名詞:一般', '行', '名詞:一般'), True)
    check('用紙＋縦 はくっつく（位置の1字の後ろ側）',
          oddness.can_join('用紙', '名詞:一般', '縦', '名詞:一般'), True)

    # (3) 姓＋名
    check('高橋＋佑（辞書の固有名詞どうし）は立たない',
          oddness.is_odd_run('高橋佑', tok_of(
              [('高橋', '名詞:固有名詞', True),
               ('佑', '名詞:固有名詞', True)])), [])
    check('読みの立たない固有名詞（未知語の推測）では黙らせない',
          oddness.is_odd_run('高橋子帝', tok_of(
              [('高橋', '名詞:固有名詞', True),
               ('子帝', '名詞:固有名詞', False)])) != [], True)
    check('姓の後ろは名前として保護する（2字の名でも・項目48-JL）',
          oddness.is_odd_run('高橋祐太', tok_of(
              [('高橋', '名詞:固有名詞:人名:姓', True),
               ('祐太', '名詞:固有名詞', False)])), [])

    # (4) 設計27 の門（純粋関数）
    from corrector import _single_kanji_diff
    check('空白行 → 空白くい は「漢字1字の差」',
          _single_kanji_diff('空白行', '空白くい'), True)
    check('高橋佑 → 高橋よう も「漢字1字の差」',
          _single_kanji_diff('高橋佑', '高橋よう'), True)
    check('野外文章 → 長い文章 は違う（2字）',
          _single_kanji_diff('野外文章', '長い文章'), False)
    src = open('corrector.py', encoding='utf-8').read()
    check('門は「読みを編集した直し」にだけ掛かる（fixed != rd）',
          'if fixed != rd and _single_kanji_diff(chunk, surf) \\' in src,
          True)
    # 48-LB（2026-08-29）: 丸ごと1語・実績10以上だけ、この門を
    # くぐれる（雛仮名 → 平仮名16。48-JG の化けは2語の組なので
    # くぐれない——上の2つの「漢字1字の差」の検査が守りの本体）
    check('くぐり抜けは 丸ごと1語＋実績10 だけ（項目48-LB）',
          "and not (surf in getattr(_surfaces, 'whole', ())" in src
          and 'and cnt >= 10):' in src, True)

    # --- 方針2 が惜しく止まった語の紫（項目48-JH・2026-08-25）---
    # うにさんの指定「異様であると認識しているのかが重要」。
    # 答えは変えず、(b) 差で勝ったが証拠が細く棄却／(c) 並記があるのに
    # 共起が決めない、の2つだけ紫に出す。**並記の右側（自分より前に
    # 同読みの別表記が書かれている出現）には付けない**。
    import corrector as CC
    line = '半角が治りました。 ⇒ 半角が直りました。'
    del CC._HOMOPHONE_UNSURE[:]
    CC._flag_homophone_unsure('治り', ['直り'], '')
    check('並記の左側（治り）に紫が付く',
          CC._odd_spans_for_line(line, lambda t: [], ()),
          [(line.find('治り'), line.find('治り') + 2)])
    del CC._HOMOPHONE_UNSURE[:]
    CC._flag_homophone_unsure('直り', ['治り'], '')
    check('並記の右側（直り・正しい側）には付かない',
          CC._odd_spans_for_line(line, lambda t: [], ()), [])
    del CC._HOMOPHONE_UNSURE[:]
    check('行の処理の頭で控えを毎回空にしている',
          'del _HOMOPHONE_UNSURE[:]' in src, True)
    check('紫を出すのは (b) 棄却と (c) 並記の2か所だけ（(a) は外した）',
          src.count('_flag_homophone_unsure(') >= 2
          and '認識（紫）をここで出すのは**試して外した**' in src, True)

    # --- 設計34: `誤 ⇒ 正` の並記で左を右に合わせる（項目48-JI）---
    def tok_r(parts):
        """(表記, 読み, 読みが立つか) から make_tokenizer の形を作る。"""
        def fn(text):
            out, pos = [], 0
            for surf, rd, known in parts:
                out.append((surf, '名詞:一般', rd, pos, pos + len(surf),
                            known))
                pos += len(surf)
            return out
        return fn

    def arrow(line, lparts, rparts):
        toks = {True: tok_r(lparts), False: tok_r(rparts)}
        p = line.find('⇒')

        def fn(text):
            return toks[text == line[:p]](text)
        return CC._arrow_respell(line, fn)

    line = '半角が治りました。 ⇒ 半角が直りました。'
    got = arrow(line,
                [('半角', 'ハンカク', True), ('が', 'ガ', True),
                 ('治り', 'ナオリ', True), ('まし', 'マシ', True),
                 ('た', 'タ', True), ('。', '。', True)],
                [('半角', 'ハンカク', True), ('が', 'ガ', True),
                 ('直り', 'ナオリ', True), ('まし', 'マシ', True),
                 ('た', 'タ', True), ('。', '。', True)])
    check('⇒ の左右の差分（治り/直り）の読みが同じなら左を右に合わせる',
          got, [(3, 5, '直り', 'その他')])
    got = arrow('再退化 ⇒ 最大化',
                [('再', 'サイ', True), ('退化', 'タイカ', True)],
                [('最大', 'サイダイ', True), ('化', 'カ', True)])
    check('濁点違い（タイカ/ダイカ）は同音ではないので触らない', got, [])
    got = arrow('局所的手図ます ⇒ 局所的すぎます',
                [('局所', 'キョクショ', True), ('的', 'テキ', True),
                 ('手図', '', False), ('ます', 'マス', True)],
                [('局所', 'キョクショ', True), ('的', 'テキ', True),
                 ('すぎ', 'スギ', True), ('ます', 'マス', True)])
    check('読みが立たない差分は照合できないので触らない', got, [])
    got = arrow('度のファイルを ⇒ どのファイルを',
                [('度', 'ド', True), ('の', 'ノ', True),
                 ('ファイル', 'ファイル', True), ('を', 'ヲ', True)],
                [('どの', 'ドノ', True),
                 ('ファイル', 'ファイル', True), ('を', 'ヲ', True)])
    check('漢字 → かな（度の → どの）も読みが同じなら合わせる',
          got, [(0, 2, 'どの', 'その他')])
    check('漢字を含まない差分（- ⇒ ほ）は見ない',
          CC._arrow_respell('- ⇒ ほ', tok_r([('-', '-', False)])), [])

    # --- 設計35: AI が焼いた同音異義語の対の表（項目48-JJ）---
    # うにさんの指定「**見本がなくても補正できないといけません**」。
    # 対の単語（手がかり語）だけで直す。回数・履歴・育った共起は見ない。
    from homophone_pairs import find_fix, KEEP
    check('対の表: 動作 が手がかりなら 思い → 重い',
          find_fix('思い', ('動作',)), '重い')
    check('対の表: 重い は「ます」に接続できない（と思います を守る）',
          find_fix('思い', ('動作',), after='ます。'), None)
    check('対の表: 慣用（思いのほか）を守る',
          find_fix('思い', ('処理',), after='のほか'), None)
    check('対の表: 書かれている側の手がかりが在れば KEEP（正しいと確認）',
          find_fix('思い', ('気持ち', '動作')), KEEP)
    check('対の表: 半角 が手がかりなら 治り → 直り',
          find_fix('治り', ('半角',)), '直り')
    check('対の表: 風邪 の話なら KEEP（治り が正しい）',
          find_fix('治り', ('風邪',)), KEEP)
    check('対の表: 傷 の話でも KEEP（傷が治りました の化けを塞ぐ・48-JL）',
          find_fix('治り', ('傷', '半角')), KEEP)
    check('対の表: 文字 が手がかりなら 売っ → 打っ',
          find_fix('売っ', ('文字',)), '打っ')
    check('対の表: 許していない送り仮名（思う）には触らない',
          find_fix('思う', ('動作',)), None)
    check('対の表: 手がかりがどちらも無ければ意見しない',
          find_fix('治り', ('昨日', '天気')), None)

    # --- 逆向きの対（項目48-JL・うにさんの×つきの的）---
    # 直前1文字の門（prev）は fpcheck の実測から——手がかり語には
    # 助詞が見えず、`ハンドルについて話しました` を 離し に変えた。
    check('逆向き: 絵**を**書く → 描く',
          find_fix('書く', ('絵',), prev='を'), '描く')
    check('逆向き: 顔**を**書く → 描く',
          find_fix('書く', ('顔',), prev='を'), '描く')
    check('逆向き: 絵**について**書く は触らない（直前が を でない）',
          find_fix('書く', ('絵',), prev='て'), None)
    check('逆向き: 文章 の話なら 書く は KEEP',
          find_fix('書く', ('文章',), prev='を'), KEEP)
    check('逆向き: 手**を**話す → 離す',
          find_fix('話す', ('手',), prev='を'), '離す')
    check('逆向き: 手**について**話す は触らない',
          find_fix('話す', ('手',), prev='て'), None)
    check('逆向き: 続き の話なら 話す は KEEP',
          find_fix('話す', ('続き',), prev='を'), KEEP)
    check('逆向き: 私**の**重い（行末）→ 私の思い',
          find_fix('重い', ('私',), after='', prev='の'), '思い')
    check('逆向き: 私**が**重い は正しい（体重の話）',
          find_fix('重い', ('私',), after='', prev='が'), None)
    check('逆向き: 後ろに名詞が続くなら 重い は正しい（私の重い鞄）',
          find_fix('重い', ('私',), after='鞄を', prev='の'), None)
    check('逆向き: 荷物 の話なら 重い は KEEP',
          find_fix('重い', ('私', '荷物'), prev='の'), KEEP)
    check('爪: 上**に**爪**、**（中止形）→ 詰め',
          find_fix('爪', ('上',), after='、', prev='に'), '詰め')
    check('爪: 爪を切る は KEEP',
          find_fix('爪', ('切',), after='を', prev='の'), KEEP)
    check('爪: 上に爪を立てる は触らない（後ろが を）',
          find_fix('爪', ('上',), after='を立', prev='に'), None)
    import corrector as _CC2
    check('KEEP は他の同音の道も止める印（_D35_KEEP）として返る',
          _CC2._design35_fix('治り', 'なおり', ('傷',), '')
          is _CC2._D35_KEEP, True)

    # --- 設計36（項目48-JM）: 1字漢字をかなに開いて連体詞が成立するなら
    # 開く（度の → どの・見本なし）。うにさんの指定「1字でスキップするのは
    # 脱字だけ」「無変換の どの が自然」。実際の動きは実機の写しの trace で
    # 確かめた（度の強い眼鏡・家の・手の・その度・一度・温度 は不変）。
    # ここでは配線と門の形を見張る。
    _src_c = open('corrector.py', encoding='utf-8').read()
    check('設計36 が correct_line に配線されている',
          '設計36: 1字の漢字を、かなに開いて機能語として成立するなら開く'
          in _src_c, True)
    check('設計36 の門: 1語の連体詞になるときだけ（ての を弾く）',
          ".startswith('連体詞')" in _src_c, True)
    check('設計36 の門: その先が名詞のときだけ（度の強い眼鏡 を守る）',
          "_nx[1] or '').startswith('名詞')" in _src_c, True)

    # --- 設計38: 場違いな小書きを隣のキーで戻す（項目48-JN）---
    # 隣接キー総当たり（7,962崩し）で見つけた「別のもの」の最大族。
    # 正しい文に場違いな小書きは無い＝異様の判定が構造だけで立つ。
    class _S38:
        def lookup(self, r):
            table = {'もじにゅうりょく': 2, 'へんかん': 5}
            n = table.get(r, 0)
            return [{'surface': r, 'count': n}] if n else []
    _s38 = _S38()
    got = CC._misplaced_small_kana_fixes('もじゃゅうりょく', _s38)
    check('小書き2連（ゃゅ）は前の字を隣のキーのい段へ（に）',
          got, [(0, 8, 'もじにゅうりょく', 'かな入力')])
    got = CC._misplaced_small_kana_fixes('へゃかん', _s38)
    check('い段でない字の後の小書きは、小書きを隣のキーへ（ん）',
          got, [(0, 4, 'へんかん', 'かな入力')])
    check('正しい小書き（きょ・しょ）には触らない',
          CC._misplaced_small_kana_fixes('きょうもしょっぷへ', _s38), [])
    check('候補が2つ以上並んだら決めない（ただ1つのときだけ）',
          CC._misplaced_small_kana_fixes('もじゃゅうりょく', type(
              'S', (), {'lookup': lambda self, r: [
                  {'surface': r, 'count': 2}]})()), [])
    check('設計38 は かな連続の道より先に走り、範囲を渡す',
          '_d38_taken' in _src_c
          and 'hiragana_taken = list(_d38_taken)' in _src_c, True)
    check('引用の守り: 「X」で括られた語は言及であって使用ではない',
          CC._design35_fix('治り', 'なおり', ('半角',),
                           '※「 」を右クリックすると候補が出る'), None)
    check('設計35 は2つの入口に置かれている（evaluate_candidate と'
          '活用形の道・学び22）',
          open('corrector.py', encoding='utf-8').read()
          .count('_fix35 = _design35_fix('), 2)

    # --- 1字の芯（項目48-JK）。うにさんの問い「1文字を弾いているのは
    # なぜですか？」——1字の門は「証拠が1字ぶんしか無い」への守りで
    # あって、1字そのものの禁止ではない。対の表の証拠は手がかり語なので、
    # 表に載っている字（糸）だけ土俵に上げる。
    from homophone_pairs import SINGLE_LEFT
    check('対の表の1字の芯が名簿にある（糸）', '糸' in SINGLE_LEFT, True)
    check('対の表: 察し が手がかりなら 糸 → 意図',
          find_fix('糸', ('察し',)), '意図')
    check('対の表: 縫い物の糸は KEEP（この表記で正しい）',
          find_fix('糸', ('縫', '布')), KEEP)
    check('対の表: 手がかりが無ければ 糸 に意見しない',
          find_fix('糸', ('赤い',)), None)
    return all_ok


def test_misplaced_dakuten_48jp():
    """
    **設計39: 場違いな濁点を、隣のキーの通常字に置き換えて戻す**
    （項目48-JP・2026-08-25。【Opus への実装方針】1番）。

    かな入力では濁点が独立したキーなので、隣を叩くと**印だけが
    取り残される**（`もじれつ` の れ → ゛ で `もじ゛つ`）。
    `normalize_marks` はこれを誤打として**落とす**ので、
    そこから先の探索は材料を失っていた（48-JN の台帳の「別のもの」）。

    見るもの:
      (1) 落とす前に隣のキーで戻す（もじ゛つ → もじれつ）
      (2) **わざと書いた印は触らない**（行頭・記号の後ろ）
      (3) 合成できる印・打つ順番の入れ替え（48-AO）は触らない
      (4) **印を落としても語になるなら身を引く**（決められない）
      (5) 1つの連続に落とされる印が2つ以上あれば決めない
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    print('--- 設計39: 場違いな濁点を隣のキーで戻す（項目48-JP） ---')
    import corrector as C

    class _Store:
        def __init__(self, words):
            self.words = set(words)

        def lookup(self, reading):
            return [{'count': 5}] if reading in self.words else []

    st = _Store(['もじれつ', 'たんご', 'へんかん'])
    check('場違いな濁点を隣のキーで戻す（もじ゛つ → もじれつ）',
          C._misplaced_dakuten_fixes('もじ゛つ', st), [(0, 4, 'もじれつ')])
    check('文の中でも同じ（範囲は連続だけ）',
          C._misplaced_dakuten_fixes('この もじ゛つ を見る', st),
          [(3, 7, 'もじれつ')])
    check('戻して語にならなければ触らない',
          C._misplaced_dakuten_fixes('かい゛き', st), [])
    check('行頭の印は触らない（わざと書いた印）',
          C._misplaced_dakuten_fixes('゛んかん', st), [])
    check('記号の後ろの印は触らない（@ ⇒ ゛）',
          C._misplaced_dakuten_fixes('@ ⇒ ゛', st), [])
    check('合成できる印は触らない（たんこ゛）',
          C._misplaced_dakuten_fixes('たんこ゛', st), [])
    check('打つ順番の入れ替え（48-AO）は触らない（たん゛こ）',
          C._misplaced_dakuten_fixes('たん゛こ', st), [])
    check('印が1つも無ければ何もしない',
          C._misplaced_dakuten_fixes('もじれつ', st), [])

    st2 = _Store(['もじれつ', 'もじつ'])
    check('印を落としても語になるなら身を引く（今までどおり）',
          C._misplaced_dakuten_fixes('もじ゛つ', st2), [])

    st3 = _Store(['もじれつ'])
    check('連続に落とされる印が2つ以上あれば決めない',
          C._misplaced_dakuten_fixes('も゛じ゛つ', st3), [])

    # 語＋助詞の尾でも立つ（設計38 と同じ物差しを使っている）
    st4 = _Store(['もじれつ'])
    check('語＋助詞の尾でも立つ（もじ゛つを）',
          C._misplaced_dakuten_fixes('もじ゛つを', st4), [(0, 5, 'もじれつを')])

    # 落とす決まりは normalize_marks だけが持つ（学び22）
    from morphology import normalize_marks
    dropped = []
    check('normalize_marks が落とした印の位置を教える',
          (normalize_marks('もじ゛つ', swap_across=True, dropped=dropped),
           dropped), ('もじつ', [2]))
    dropped = []
    normalize_marks('@ ⇒ ゛', swap_across=True, dropped=dropped)
    check('わざと書いた印は落とさない（名簿にも出ない）', dropped, [])
    return all_ok


def test_long_vowel_48js():
    """
    **設計40: 伸ばし棒（ー）の打ち間違いを、隣のキーで戻す**
    （項目48-JS・2026-08-26。【Opus への実装方針】2番「ー と隣キーの相互」）。

    かな配列では `ー` の隣が **ろ・れ・け・む・め**。48-JN の台帳から
    ー が絡む崩しだけを数えると、**向きで形が違う**:

      (A) 連続の**先頭の ー** ——`ー` は直前のかなの母音を伸ばす印なので
          頭には立てない（48-EL の裏返し）。**構造だけで異様が立つ**
      (B) `ー` のはずが隣のキーになった ——構造では立たないので、
          「連続がそれ自体では語でない」「直し先がカタカナを含む表記」
          「ただ1つ」の3つで締める

    見るもの:
      (1) 頭の ー を戻す（ーんらく → れんらく）
      (2) ー のはずの字を戻す（ぺめすと → ぺーすと）
      (3) **正しい語には触らない**（くれる・かれ）
      (4) **ー だけの連続**（区切り線）と、**引き伸ばし**（あー）に触らない
      (5) 2つ以上が語になったら決めない
      (6) 短い連続（3字未満）は見ない
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    print('--- 設計40: 伸ばし棒の打ち間違いを戻す（項目48-JS） ---')
    import corrector as C

    class _Store:
        """読み → 表記。表記のカタカナで「外来語か」を見分ける。"""

        def __init__(self, words):
            self.words = dict(words)

        def lookup(self, reading):
            surf = self.words.get(reading)
            return ([{'count': 9, 'surface': surf, 'reading': reading}]
                    if surf else [])

    st = _Store({'ぺーすと': 'ペースト', 'かーそる': 'カーソル',
                 'れんらく': '連絡', 'めもちょう': 'メモ帳',
                 'くれる': 'くれる', 'かれ': '彼',
                 'けーす': 'ケース', 'ろーす': 'ロース'})

    def fix(line):
        return [(s, e, f) for s, e, f in
                C._misplaced_long_vowel_fixes(line, st)]

    # (1) 頭の ー（構造だけで立つ異様）
    check('頭の伸ばし棒を隣のキーで戻す（ーんらく → れんらく）',
          fix('ーんらく'), [(0, 4, 'れんらく')])
    check('同（ーもちょう → めもちょう）',
          fix('ーもちょう'), [(0, 5, 'めもちょう')])
    # (5) 2つ以上が語になったら決めない（けーす と ろーす）
    check('2つ以上が語になったら決めない（ーーす）', fix('ーーす'), [])
    # (4) 触らないもの
    check('ー だけの連続は区切り線（触らない）', fix('ーーーーー'), [])
    check('引き伸ばしには触らない（あーー）', fix('あーー'), [])
    check('末尾の伸ばしにも触らない（こんにちはー）',
          fix('こんにちはー'), [])
    # **前がカタカナ・漢字・ひらがななら、頭の ー はその語のもの**
    # （`レディーまで` の ー は レディー の一部）。ここを外すと
    # **正しいカタカナ語から ー を削る**（fpcheck 誤検知5件・実測）。
    check('カタカナ語の伸ばし棒を、次の連続の頭と読まない',
          fix('ここからレディーまで歩きます。'), [])
    check('同（バーナーについて）', fix('バーナーについて話しました。'), [])
    check('落とすのは直しではない（ーまで → まで にしない）',
          fix('ーまで'), [])

    # (2) ー のはずが隣のキーになった
    #
    # **画面に出す形は `katakana_for_hiragana`（項目48-r）が決める**
    # ——表記がカタカナだけの外来語ならカタカナで書く。あちらには
    # あちらの門があるので、ここで見るのは「**どの連続を直したか**」。
    # `かーそる` はカタカナで書かれ、`ぺーすと` はこの偽の入れ物では
    # あちらの門に掛かって読みのまま（本物の語彙では `ペースト`）。
    check('隣のキーを伸ばし棒に戻す（ぺめすと → ぺーすと）',
          fix('ぺめすと'), [(0, 4, 'ぺーすと')])
    check('同（かけそる → カーソル。カタカナ語はカタカナで書く）',
          fix('かけそる'), [(0, 4, 'カーソル')])
    check('文の中でも連続だけを見る',
          fix('この ぺろすと を見る'), [(3, 7, 'ぺーすと')])

    # (3) 正しい語には触らない
    check('それ自体が語なら触らない（くれる）', fix('くれる'), [])
    check('正しく書けた外来語には触らない（かーそる）', fix('かーそる'), [])
    check('直し先がカタカナを含まなければ採らない',
          fix('れんらこ'), [])          # れんらく はカタカナを含まない
    # (6) 短い連続
    check('3字未満の連続は見ない', fix('けー'), [])
    check('伸ばし棒も隣のキーも無ければ何もしない', fix('あいうえお'), [])
    return all_ok


def test_head_typo_48jt():
    """
    **設計41: かな連続の「頭の1字」の打ち間違いを、隣のキーで戻す**
    （項目48-JT・2026-08-26。【Opus への実装方針】3番「先頭の崩れ」）。

    48-JN の台帳で**いちばん弱いのが先頭**（戻し率 29%）。語頭は探索の
    錨なので、そこが崩れると起点が消える。

    **測って、入れなかった**（既定は切り。`CORRECTNOTE_DESIGN41=1` で入る）。
    族をまたいだ「1手はこれだけ」で締めると先頭の台帳は
    **569(30%) → 1679(91%)** まで直るが、**readcheck では得が測れず
    損だけ出る**（あちらの崩しは 濁点・重複・脱字・順序違い の4族で、
    **隣接キーの置換が入っていない**）——初期で 直った 1856→1853・
    **化けた 92→97**。増えた5件は**正しい語が語彙に無い**行だった。
    詳しくは `corrector.py` の `_head_typo_fixes` の上の説明。

    ここでは**切り替えを入れて、判断の中身**を見張る（入れ直すときに
    門が崩れていないことを確かめられるように）。

    見るもの:
      (1) 頭の1字を戻す（とくじょ → さくじょ）
      (2) **連続がそれ自体で語なら触らない**（いちばん大事な門）
      (3) 2つ以上が語になったら決めない
      (4) **前が漢字・カタカナなら見ない**（送り仮名・複合語の途中）
      (5) 3字未満の連続は見ない
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    print('--- 設計41: 頭の1字を隣のキーで戻す（項目48-JT・既定は切り） ---')
    import corrector as C

    # 既定では切ってあるので、ここだけ入れて中身を見る
    _was, C._DESIGN41_ON = C._DESIGN41_ON, True
    C._DESIGN41_MIN = 3

    class _Store:
        def __init__(self, words):
            self.words = dict(words)

        def lookup(self, reading):
            surf = self.words.get(reading)
            return ([{'count': 9, 'surface': surf, 'reading': reading}]
                    if surf else [])

    st = _Store({'さくじょ': '削除', 'かくにん': '確認', 'せんたく': '選択',
                 'めもちょう': 'メモ帳', 'ください': '下さい',
                 'にってい': '日程'})

    def fix(line):
        return C._head_typo_fixes(line, st)

    # (1) 頭の1字を戻す（と→さ は隣・る→め は隣）
    check('頭の1字を隣のキーで戻す（とくじょ → さくじょ）',
          fix('とくじょ'), [(0, 4, 'さくじょ')])
    check('同（るもちょう → めもちょう）',
          fix('るもちょう'), [(0, 5, 'めもちょう')])
    check('同（わんたく → せんたく。わ と せ は隣）',
          fix('わんたく'), [(0, 4, 'せんたく')])
    check('語＋助詞の尾でも立つ（とくじょを）',
          fix('とくじょを'), [(0, 5, 'さくじょを')])
    check('文の中でも連続だけを見る',
          fix('※ とくじょ ※'), [(2, 6, 'さくじょ')])

    # (2) それ自体で語なら触らない
    check('それ自体で語なら触らない（さくじょ）', fix('さくじょ'), [])
    check('同（ください）', fix('ください'), [])

    # (3) 決められないときは触らない
    st2 = _Store({'さくじょ': '削除', 'とくじょ': '特除'})
    check('崩した形がそれ自体で語なら触らない',
          C._head_typo_fixes('とくじょ', st2), [])
    st3 = _Store({'さくじょ': '削除', 'しくじょ': '仕除'})
    check('2つ以上が語になったら決めない',
          C._head_typo_fixes('とくじょ', st3), [])

    # (4) 前が漢字・カタカナなら見ない（送り仮名・複合語の途中）
    check('前が漢字なら見ない（送り仮名かもしれない）',
          fix('補正とくじょ'), [])
    check('前がカタカナなら見ない', fix('メモとくじょ'), [])
    check('前が記号なら見る（語の始まりの証拠）',
          fix('、とくじょ'), [(1, 5, 'さくじょ')])

    # (5) 短い連続
    check('3字未満の連続は見ない', fix('とく'), [])
    check('頭が伸ばし棒の連続は設計40 が受け持つ', fix('ーくじょ'), [])

    # (6) 別の族の1手もあるなら身を引く（既存の道が決める）
    st4 = _Store({'さくじょ': '削除', 'とくじょう': '特上'})
    check('別の族（脱字）の1手もあるなら決めない',
          C._head_typo_fixes('とくじょ', st4), [])
    check('1手で届く語を族ごとに数える（頭・脱字の両方が出る）',
          sorted(C._one_edit_words('とくじょ', st4).items()),
          [('さくじょ', '頭'), ('とくじょう', '脱字')])

    C._DESIGN41_ON = _was
    check('**既定では動かない**（切り替えが要る）',
          C._head_typo_fixes('とくじょ', st), [])
    return all_ok


def test_recut_candidate_48ju():
    """
    **区切り直しの候補**（項目48-JU・2026-08-26）。

    うにさんの的「切り替え時二階席が走っていて ⇒ 切り替え時に解析が
    走っていて」。同音異義語の探索は**その読み全体で1語**しか探せない
    ので、`にかいせき` から `解析` には届いても、**助詞をまたいだ**
    `に解析` には構造上どうやっても届かない。読みの DP
    （`kana_to_kanji_where_possible`）を**候補として**足したのが
    `kind='recut'`。

    **自動では直さない。** 同じ DP をトークンの並びに当てると実機メモ
    1,342行で 育ち **4,350**・初期 **2,431** か所が書き換わる
    （項目48-JU §2）。ここは**申し出**であって直しではない。

    見張るもの: 門3つ（元と違う／DP が実際に変換した／漢字かカタカナを
    含む）と、**並びが打ち間違いより上**であること、そして
    `MENU_KINDS` が**ひとつの表**であること（`app.py` の3か所が
    これを回す。学び22）。janome 無しで回る。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    from candidates import (build_range_candidates, MENU_KINDS,
                            KIND_LABELS)
    from vocabulary import VocabularyStore, find_known_readings_flex

    print('--- 項目48-JU（区切り直しの候補） ---')

    store = VocabularyStore()
    for _ in range(3):
        store.add('かいせき', '解析', 'その他')
        store.add('もじ', '文字', 'その他')

    def kinds(cands, kind):
        return [c['surface'] for c in cands if c['kind'] == kind]

    # (1) 助詞をまたいだ形に届く
    got = build_range_candidates([('二', 'に'), ('階', 'かい'),
                                  ('席', 'せき')],
                                 store, find_known_readings_flex)
    check('に解析 が区切り直しとして立つ', kinds(got, 'recut'), ['に解析'])

    # (2) 打ち間違いより上に並ぶ
    names = [c['surface'] for c in got]
    typos = [i for i, c in enumerate(got) if c['kind'] == 'typo']
    check('打ち間違いより上',
          (not typos) or names.index('に解析') < min(typos), True)

    # (3) 門1: 元と同じなら出さない
    got2 = build_range_candidates([('解析', 'かいせき')],
                                  store, find_known_readings_flex)
    check('元と同じ形は出さない', kinds(got2, 'recut'), [])

    # (4) 門2: DP が何も変換できないなら出さない（かなのまま）
    got3 = build_range_candidates([('余', 'よ'), ('白', 'はく')],
                                  store, find_known_readings_flex)
    check('読みのまま返る形は出さない（かな表記と同じもの）',
          kinds(got3, 'recut'), [])

    # (5) 門3: 漢字もカタカナも無い形は出さない
    got4 = build_range_candidates([('で', 'で'), ('来', 'き'),
                                   ('ません', 'ません')],
                                  store, find_known_readings_flex)
    check('かなだけの形は区切り直しに出さない', kinds(got4, 'recut'), [])

    # (6) 見出しの表はひとつ
    ks = [k for k, _l in MENU_KINDS]
    check('MENU_KINDS に recut が居る', 'recut' in ks, True)
    check('KIND_LABELS は MENU_KINDS から作る', KIND_LABELS,
          dict(MENU_KINDS))
    check('見出しの順も打ち間違いより上',
          ks.index('recut') < ks.index('typo'), True)
    src = open('app.py', encoding='utf-8').read()
    check('app.py の3か所とも MENU_KINDS を回す',
          src.count('for kind, label in MENU_KINDS:'), 3)
    check('app.py に見出しの写しが残っていない',
          "'打ち間違いの可能性'" in src, False)
    return all_ok


def test_resegment_48jv():
    """
    **設計42: 読みを語の境目で切り直す**（項目48-JV・2026-08-26）。

    うにさんの的「**切り替え時二階席が走っていて ⇒ 切り替え時に解析が
    走っていて**」。打ち間違いは1つも無く、**同じ読みを IME が別の場所で
    切った**形。

    うにさんの決まり（2026-08-26 再指定）:
    「**原文が異様であり、候補が複数の時は、何かしらに決める**」。
    だから**先に異様判定を立てて**、立ったら決める。「ただ1つのときだけ
    採る」（設計38〜40）は**判定が立っていないとき**の門で、ここでは使わない。

    janome 無しで回すため、区切りは**手で作って**渡す
    （`_resegment_fixes` は tokenize_fn を受け取るだけなので、
    本物の解析器は要らない）。
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

    print('--- 項目48-JV（設計42・読みを語の境目で切り直す） ---')

    store = VocabularyStore()
    for _ in range(3):
        store.add('かいせき', '解析', 'その他')
        store.add('せき', '席', 'その他')

    def toks(*items):
        """(表記, 品詞, 読み) から、tokenize_fn が返す形を組む。"""
        out, pos = [], 0
        for surf, p, rd in items:
            out.append((surf, p, rd, pos, pos + len(surf), True))
            pos += len(surf)
        return out

    def fix(line, tokens):
        return C._resegment_fixes(line, lambda _l: tokens, store)

    NIKAISEKI = (('二', '名詞:数', 'に'), ('階', '名詞:接尾:助数詞', 'かい'),
                 ('席', '名詞:一般', 'せき'))

    # (1) 的そのもの——前が名詞（時）なら切り直す
    t = toks(('時', '名詞:接尾:副詞可能', 'じ'), *NIKAISEKI,
             ('が', '助詞:格助詞', 'が'))
    check('時二階席が → 時に解析が', fix('時二階席が', t),
          [(1, 4, 'に解析')])

    # (2) **行の頭に助詞は立てない**（二階席が取れました）
    t2 = toks(*NIKAISEKI, ('が', '助詞:格助詞', 'が'))
    check('行頭では切り直さない', fix('二階席が', t2), [])

    # (3) **助詞の直後にも立てない**（劇場の二階席）
    t3 = toks(('劇場', '名詞:一般', 'げきじょう'), ('の', '助詞:連体化', 'の'),
              *NIKAISEKI)
    check('助詞の直後では切り直さない', fix('劇場の二階席', t3), [])

    # (4) **連体詞の直後にも立てない**（この二階席）
    t4 = toks(('この', '連体詞', 'この'), *NIKAISEKI)
    check('連体詞の直後では切り直さない', fix('この二階席', t4), [])

    # (5) **単独で立つ語が混じっていたら触らない**（タブ機能）
    store2 = VocabularyStore()
    for _ in range(3):
        store2.add('きのう', '昨日', 'その他')
        store2.add('たぶ', 'タブ', 'その他')
    t5 = toks(('時', '名詞:接尾', 'じ'), ('タブ', '名詞:一般', 'たぶ'),
              ('機能', '名詞:一般', 'きのう'))
    check('単独で立つ語が居るなら触らない',
          C._resegment_fixes('時タブ機能', lambda _l: t5, store2), [])

    # (6) **数え方は異様ではない**（二本）
    t6 = toks(('線', '名詞:一般', 'せん'), ('二', '名詞:数', 'に'),
              ('本', '名詞:接尾:助数詞', 'ほん'))
    check('数詞＋助数詞で閉じる連なりは触らない',
          fix('線二本', t6), [])

    # (7) **直前が数詞なら数え方の続き**（1行分）
    t7 = toks(('1', '名詞:数', 'いち'), ('行', '名詞:接尾', 'ぎょう'),
              ('分', '名詞:接尾', 'ぶん'))
    check('直前が数詞なら触らない', fix('1行分', t7), [])

    # (8) 部品の門
    check('_d42_known_unit は1字を語と見ない',
          C._d42_known_unit('席', store), False)
    check('_d42_covered は語＋助詞で埋まるものだけ通す',
          (C._d42_covered('に解析', store), C._d42_covered('と切っそう', store)),
          (True, False))
    return all_ok


def test_particle_merge_48jz():
    """
    **設計43: 助詞をはさんだ読みを1語へ寄せる**（項目48-JZ・2026-08-27）。

    うにさんの的（的リスト・実装方針4の A族「寄せる」）:

        全体と押して       ⇒ 全体通して      （と＋押し ＝ とおし ＝ 通し）
        長いことで来ません   ⇒ 長いことできません（で＋来 ＝ でき）

    「繋いだ読みが語彙の語」は証拠にならない（初期の実機メモで候補18か所が
    全部誤爆の向き・2026-08-27 実測）ので、**閉じた対の表＋対ごとの門**。
    実機メモに `F9F10と押しても同じです` という**正しい並び**が在るため、
    と＋押し は手がかり語（全体・全部・全文）の直後だけ。
    `バスで来ません` `そのことで来ません` は正しい日本語なので、
    で＋来 は **形容詞＋こと**（期間の言い回し）の直後だけ。

    janome 無しで回すため、区切りは手で作って渡す（設計42 の見張りと同じ）。
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

    print('--- 項目48-JZ（設計43・助詞をはさんだ読みを1語へ寄せる） ---')

    def toks(*items):
        out, pos = [], 0
        for surf, p, rd in items:
            out.append((surf, p, rd, pos, pos + len(surf), True))
            pos += len(surf)
        return out

    def fix(line, tokens):
        return C._particle_merge_fixes(line, lambda _l: tokens)

    # (1) 的そのもの——全体と押して → 全体通して
    t = toks(('全体', '名詞:一般', 'ぜんたい'), ('と', '助詞:格助詞', 'と'),
             ('押し', '動詞:自立', 'おし'), ('て', '助詞:接続助詞', 'て'))
    check('全体と押して → 通し に寄せる', fix('全体と押して', t),
          [(2, 4, '通')])

    # (2) 的そのもの——長いことで来ません → できません
    t2 = toks(('長い', '形容詞:自立', 'ながい'), ('こと', '名詞:非自立', 'こと'),
              ('で', '助詞:格助詞', 'で'), ('来', '動詞:自立', 'き'),
              ('ませ', '助動詞', 'ませ'), ('ん', '助動詞', 'ん'))
    check('長いことで来ません → でき に寄せる', fix('長いことで来ません', t2),
          [(4, 6, 'でき')])

    # (3) **手がかり語が無ければ触らない**（F9F10と押しても・実機の正しい行）
    t3 = toks(('F9F10', '名詞:固有名詞', 'えふ'), ('と', '助詞:格助詞', 'と'),
              ('押し', '動詞:自立', 'おし'), ('て', '助詞:接続助詞', 'て'),
              ('も', '助詞:係助詞', 'も'))
    check('手がかり語が無ければ触らない', fix('F9F10と押しても', t3), [])

    # (4) **形容詞＋こと でなければ触らない**（バスで来ません・そのことで来ません）
    t4 = toks(('バス', '名詞:一般', 'ばす'), ('で', '助詞:格助詞', 'で'),
              ('来', '動詞:自立', 'き'), ('ませ', '助動詞', 'ませ'),
              ('ん', '助動詞', 'ん'))
    check('名詞＋で来ません は触らない', fix('バスで来ません', t4), [])
    t5 = toks(('その', '連体詞', 'その'), ('こと', '名詞:非自立', 'こと'),
              ('で', '助詞:格助詞', 'で'), ('来', '動詞:自立', 'き'),
              ('ませ', '助動詞', 'ませ'), ('ん', '助動詞', 'ん'))
    check('連体詞＋ことで来ません は触らない（両義）',
          fix('そのことで来ません', t5), [])

    # (5) **送りの列が合わなければ触らない**（全体と押つ…のような崩れ）
    t6 = toks(('全体', '名詞:一般', 'ぜんたい'), ('と', '助詞:格助詞', 'と'),
              ('押つ', '動詞:自立', 'おつ'))
    check('送りの列が違えば触らない', fix('全体と押つ', t6), [])

    # (6) 一度伝えた判断（blocks）は覆さない
    class _Blocks:
        def blocks(self, a, b):
            return a == 'と押' and b == '通'
    check('blocks が立っていれば触らない',
          C._particle_merge_fixes('全体と押して', lambda _l: t, _Blocks()), [])

    # (7) 速い門——対の並びが無い行は tokenize すら呼ばない
    def _boom(_l):
        raise AssertionError('呼ばれないはず')
    check('対の並びが無い行は何もしない',
          C._particle_merge_fixes('ふつうの行です', _boom), [])
    return all_ok


def test_parallel_pair_48ka():
    """
    **設計44: 並記の親戚——「〜中か」に続く同音の対**（項目48-KA・2026-08-27）。

    的（引き継ぎ D）: 上昇中か加工中華 ⇒ 上昇中か下降中か

    `加工 → 下降` は同音（かこう）の対、`中華 → 中か` は読みの再分割。
    **片方だけでは開かない**（`上昇中か加工中か` は、かえって読めない）。
    並列の相手（上昇⇔下降）が閉じた証拠なので使用実績は見ない
    （初期語彙の 下降 は実績1。count>=2 の門はうにさんの指定で触らない）。
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

    print('--- 項目48-KA（設計44・並記の親戚） ---')

    def toks(*items):
        out, pos = [], 0
        for surf, p, rd in items:
            out.append((surf, p, rd, pos, pos + len(surf), True))
            pos += len(surf)
        return out

    def fix(line, tokens, dec=None):
        return C._parallel_pair_fixes(line, lambda _l: tokens, dec)

    BASE = (('上昇', '名詞:サ変接続', 'じょうしょう'),
            ('中', '名詞:接尾:副詞可能', 'ちゅう'),
            ('か', '助詞:並立助詞', 'か'),
            ('加工', '名詞:サ変接続', 'かこう'),
            ('中華', '名詞:一般', 'ちゅうか'))

    # (1) 的そのもの——**2か所を原子的に**直す
    t = toks(*BASE)
    check('上昇中か加工中華 → 下降・中か の2か所',
          fix('上昇中か加工中華', t),
          [(4, 6, '下降'), (6, 8, '中か')])

    # (2) 並列の相手が表に無ければ開かない（検討中か加工中華）
    t2 = toks(('検討', '名詞:サ変接続', 'けんとう'), *BASE[1:])
    check('相手が表に無ければ触らない', fix('検討中か加工中華', t2), [])

    # (3) 読みが対と違えば開かない（上昇中か下降中華 は前半が直し済み）
    t3 = toks(*BASE[:3], ('下降', '名詞:サ変接続', 'かこう'),
              ('中華', '名詞:一般', 'ちゅうか'))
    check('もう直し先の表記なら B 側は触らない…',
          fix('上昇中か下降中華', t3), [])

    # (4) 錨（中か）が無ければ開かない
    t4 = toks(('上昇', '名詞:サ変接続', 'じょうしょう'),
              ('が', '助詞:格助詞', 'が'),
              ('加工', '名詞:サ変接続', 'かこう'),
              ('中華', '名詞:一般', 'ちゅうか'))
    check('並列の錨が無ければ触らない', fix('上昇が加工中華', t4), [])

    # (5) 一度伝えた判断（blocks）は覆さない（どちらか一方でも）
    class _B1:
        def blocks(self, a, b):
            return a == '加工' and b == '下降'
    check('blocks（加工→下降）で全体が止まる',
          fix('上昇中か加工中華', toks(*BASE), _B1()), [])

    class _B2:
        def blocks(self, a, b):
            return a == '中華'
    check('blocks（中華→中か）でも全体が止まる',
          fix('上昇中か加工中華', toks(*BASE), _B2()), [])

    # (6) 速い門——対の並びが無い行は tokenize すら呼ばない
    def _boom(_l):
        raise AssertionError('呼ばれないはず')
    check('中華 の無い行は何もしない',
          C._parallel_pair_fixes('ふつうの行です', _boom), [])
    check('中か の無い行は何もしない',
          C._parallel_pair_fixes('中華を食べます', _boom), [])
    return all_ok


def test_backslash_key_48kb():
    """
    **設計45: `\\` は ろ／ー の2つのキー**（項目48-KB・2026-08-27）。

    日本語キーボードには 0x5C を出すキーが2つある（ろ＝右 Shift の左・
    ー＝¥）。半角のまま打つとどちらも同じ文字になるので、既定（ろ）で
    読めないときは ー と読んだ形も試し、**同梱のカタカナ語の表に
    ただ1つ**当たるなら採る。

    的（うにさんの正解メモ・実装方針5）: `rh\\\\.` ⇒ スクロール
    （すくろーる。初期語彙の スクロール は実績1なので、回数を見ない
    表が証拠——count>=2 の門はうにさんの指定で触らない）。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    from halfwidth import (halfwidth_to_kana_variants, correct_halfwidth,
                           looks_like_halfwidth_input)
    from vocabulary import VocabularyStore, find_known_readings_flex

    print('--- 項目48-KB（設計45・\\ は ろ／ー の2つのキー） ---')

    bs = '\\'
    line = 'rh' + bs * 2 + '.'

    # (1) 門が `\` を句読点として剥がさない（剥がすと rh が英字だけに見えた）
    check('rh\\\\. は半角入力に見える', looks_like_halfwidth_input(line), True)

    # (2) 変種は ー 側の組み合わせ（既定＝全部 ろ は含まない）
    check('変種の並び', halfwidth_to_kana_variants(line),
          ['すくーろる', 'すくろーる', 'すくーーる'])

    # (3) 的そのもの——表にただ1つ当たるので スクロール
    store = VocabularyStore()
    check('rh\\\\. → スクロール',
          correct_halfwidth(line, store, find_known_readings_flex),
          'スクロール')

    # (4) 守り——英文の行末の \ や Windows のパスは触らない
    check('英文＋行末の \\ は触らない',
          correct_halfwidth('and ' + bs, store, find_known_readings_flex),
          None)
    check('Windows のパスは触らない',
          correct_halfwidth('C:' + bs + 'CorrectNote' + bs + 'app.py',
                            store, find_known_readings_flex), None)

    # (5) 曖昧なキーが多すぎる行は諦める（式・罫線の類）
    check('\\ が4つ以上は変種を作らない',
          halfwidth_to_kana_variants(bs * 4), [])
    return all_ok


def test_adverb_join_48ke():
    """
    **副詞は、後ろに立つ相手を選ばない**（項目48-KE・2026-08-27）。

    `一度無効にして` が `一度向かうにして` に化けた——**うにさん自身の
    文**（実機メモ tab4:50。CLAUDE.md ★★③ に引く「過去の決まりも
    見直したり、**一度無効にしたり**して」そのもの）。

    根は `oddness.can_join` の副詞性の門が **`名詞:副詞可能` しか見て
    いなかった**こと。解析は本物の副詞を `副詞:一般` と書くので、
    `一度` は門を全部素通りして異様に立ち、設計27 が いちどむこう →
    隣接キー(こ→か) → `一度向かう`（実績37）へ引っぱっていた。
    初期では `向かう` が語彙に無いので化けないが、**印は初期でも
    立っていた**＝判定そのものの誤り。

    **学び22 の型**——副詞性の門を片方の書き方にだけ掛けたので、
    もう片方がそこを迂回して素通りした。`_adverbial` の1か所に寄せた。

    `一度` は `無効` と複合語を作っているのではなく、`無効にする`
    という述語ごと修飾している。だから相性を問う相手ではない。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import oddness as O
    if not O.available():
        print('--- 項目48-KE: 表が読めないので飛ばす')
        return True

    print('--- 項目48-KE（副詞は相性を問わない） ---')

    def toks(*items):
        out, pos = [], 0
        for surf, p, rd in items:
            out.append((surf, p, rd, pos, pos + len(surf), True))
            pos += len(surf)
        return out

    # (1) 的そのもの——本物の副詞（`副詞:一般`）が前に立つ
    check('一度＋無効 はくっつける',
          O.can_join('一度', '副詞:一般', '無効', '名詞:形容動詞語幹'), True)
    t = toks(('一度', '副詞:一般', 'いちど'),
             ('無効', '名詞:形容動詞語幹', 'むこう'),
             ('に', '助詞:格助詞:一般', 'に'),
             ('し', '動詞:自立', 'し'), ('て', '助詞:接続助詞', 'て'))
    check('一度無効にして に印は立たない',
          O.is_odd_run('一度無効にして', lambda _l: t), [])

    # (2) `〜化` が付いた形も同じ（前の版はここにも印が立っていた）
    t2 = toks(('一度', '副詞:一般', 'いちど'),
              ('無効', '名詞:形容動詞語幹', 'むこう'),
              ('化', '名詞:接尾:サ変接続', 'か'))
    check('一度無効化 に印は立たない',
          O.is_odd_run('一度無効化', lambda _l: t2), [])

    # (3) **回帰なし**——`名詞:副詞可能` は今までどおり通る
    check('名詞:副詞可能 も通る（回帰なし）',
          O.can_join('全部', '名詞:副詞可能', '無効', '名詞:形容動詞語幹'),
          True)
    # (3') 後ろが副詞の側にも同じ門を掛けた（学び22）
    check('後ろが副詞でも通る',
          O.can_join('作業', '名詞:一般', 'すぐ', '副詞:一般'), True)

    # (4) **守り**——本物の異様は残る（副詞が絡まない並びは元のまま）
    check('野外＋文章 は今までどおり異様',
          O.can_join('野外', '名詞:一般', '文章', '名詞:一般'), False)
    t3 = toks(('野外', '名詞:一般', 'やがい'),
              ('文章', '名詞:一般', 'ぶんしょう'))
    check('野外文章 の印は残る',
          O.is_odd_run('野外文章', lambda _l: t3), [('野外', '文章')])
    check('殺意＋代価 は今までどおり異様',
          O.can_join('殺意', '名詞:一般', '代価', '名詞:一般'), False)
    return all_ok


def test_stem_run_48kf():
    """
    **動詞の名詞化が前に立つ形も、異様を見る**（項目48-KF・2026-08-27）。

    うにさんの正解メモ: `引き月資料` は **`引き継ぎ資料` のタイプミス**
    （ひきつぎ を ひきつき と打った＝濁点の脱け）。

    `is_odd_run` の「A がかな終わり」の枝は `ap.startswith('動詞')` しか
    通していなかった（48-JC の `買い脊柱` の道）。解析は `引き` を
    **`名詞:一般`** と言うので、そこで落ちていた。**材料は在ったのに
    道が無かった**——`can_join('引き','名詞:一般','月','名詞:一般')` は
    元から **False** と言っている。

    **門は can_join そのもの。** 実機メモ全タブで測ると
    （`tools_local/diag_stem_run.py`・育ち初期とも同じ）:

        can_join を要求しない形  12組（読み込み中・打ち補正・押し間違い・
                                  付き入力…**全部正しい日本語**）
        can_join が False だけ   **1組＝的そのものだけ・誤爆0**

    動詞の枝と違って直に立てないのは、**名詞のほうが正しい複合語を
    ずっと多く作る**ため。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import oddness as O
    if not O.available():
        print('--- 項目48-KF: 表が読めないので飛ばす')
        return True

    print('--- 項目48-KF（送り仮名つき名詞＋名詞） ---')

    def toks(*items):
        out, pos = [], 0
        for surf, p, rd in items:
            out.append((surf, p, rd, pos, pos + len(surf), True))
            pos += len(surf)
        return out

    # (1) 的——材料（can_join）は元から False と言っていた
    check('引き＋月 はくっつけない',
          O.can_join('引き', '名詞:一般', '月', '名詞:一般'), False)
    t = toks(('引き', '名詞:一般', 'ひき'), ('月', '名詞:一般', 'つき'),
             ('資料', '名詞:一般', 'しりょう'))
    check('引き月資料 に印が立つ',
          O.is_odd_run('引き月資料', lambda _l: t), [('引き', '月')])

    # (2) **守り**——can_join が True と言う並びは立てない
    for a, ap, b, bp, label in (
            ('読み込み', '名詞:一般', '中', '名詞:接尾', '読み込み中'),
            ('押し', '名詞:一般', '間違い', '名詞:一般', '押し間違い'),
            ('付き', '名詞:一般', '入力', '名詞:サ変接続', '付き入力')):
        tt = toks((a, ap, 'x'), (b, bp, 'y'))
        check(f'{label} は立てない',
              O.is_odd_run(a + b, lambda _l: tt), [])

    # (3) **回帰なし**——48-JC の動詞の道はそのまま
    t2 = toks(('買い', '動詞:自立', 'かい'), ('脊柱', '名詞:一般', 'せきちゅう'))
    check('買い脊柱（動詞の道）は今までどおり立つ',
          O.is_odd_run('買い脊柱', lambda _l: t2), [('買い', '脊柱')])
    # (3') 形容詞・副詞・連体詞は今までどおり見ない（日本語の背骨）
    t3 = toks(('正しい', '形容詞:自立', 'ただしい'),
              ('単語', '名詞:一般', 'たんご'))
    check('正しい単語 は見ない',
          O.is_odd_run('正しい単語', lambda _l: t3), [])
    # (3'') **う段どまり**（連体形）は今までどおり見ない
    t4 = toks(('閉じる', '動詞:自立', 'とじる'),
              ('機能', '名詞:サ変接続', 'きのう'))
    check('閉じる機能 は見ない',
          O.is_odd_run('閉じる機能', lambda _l: t4), [])
    return all_ok


def test_odd_mark_48jw():
    """
    **直せなくても、異様の印は立てる**（項目48-JW・2026-08-26）。

    うにさんの指定:

      「**異様であると認識しているのかが重要です。紫の表示がなければ
        その判定が必要です**」
      「**補正できないと判断する場合でも、紫の色は付けます。** 紫を
        付けるものは候補が多かろうが何かしらに補正してしまうので紫が
        残らないことが多いですが、**それでも補正先がない場合は
        紫だけが残ります**」

    設計42（項目48-JV）は異様判定を持っているのに、**決められなかった
    ときに何も残していなかった**。台帳 `_D42_ODD` に置いて、
    `_odd_spans_for_line` が紫に混ぜる。

    ついでに**同じところに2つ印を立てない**（`oddness` と台帳が同じ
    範囲を見ることがある。内側に入っている範囲も落とす）。
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

    print('--- 項目48-JW（直せなくても印は立てる） ---')

    store = VocabularyStore()
    for _ in range(3):
        store.add('かいせき', '解析', 'その他')

    def toks(*items):
        out, pos = [], 0
        for surf, p, rd in items:
            out.append((surf, p, rd, pos, pos + len(surf), True))
            pos += len(surf)
        return out

    # (1) 異様と見たのに決められない → **台帳に残る**
    del C._D42_ODD[:]
    t = toks(('の', '名詞:非自立', 'の'), ('利', '名詞:一般', 'り'),
             ('倍', '名詞:接尾', 'ばい'))
    got = C._resegment_fixes('の利倍', lambda _l: t, store)
    check('直せない（戻り値は空）', got, [])
    # **見えるのは `_odd_spans_for_line` を通したあと**（内側は落ちる）
    check('**印は残る**',
          C._odd_spans_for_line('の利倍', lambda _l: [], ()), [(0, 3)])

    # (2) 決められたら印は残さない（直しの色になる）
    del C._D42_ODD[:]
    t2 = toks(('時', '名詞:接尾:副詞可能', 'じ'), ('二', '名詞:数', 'に'),
              ('階', '名詞:接尾:助数詞', 'かい'), ('席', '名詞:一般', 'せき'))
    got2 = C._resegment_fixes('時二階席', lambda _l: t2, store)
    check('直せたら印は残さない', (got2, list(C._D42_ODD)),
          ([(1, 4, 'に解析')], []))

    # (3) 何にでも付く1字（位置・区画）は異様ではない
    del C._D42_ODD[:]
    t3 = toks(('欄', '名詞:一般', 'らん'), ('内', '名詞:接尾:一般', 'ない'))
    C._resegment_fixes('欄内', lambda _l: t3, store)
    check('位置・区画の1字が居るなら印を立てない', list(C._D42_ODD), [])

    # (4) 固有名詞が混じっていたら判定しない
    del C._D42_ODD[:]
    t4 = toks(('田無', '名詞:固有名詞:地域:一般', 'たなし'),
              ('駅', '名詞:接尾:地域', 'えき'))
    C._resegment_fixes('田無駅', lambda _l: t4, store)
    check('固有名詞が居るなら印を立てない', list(C._D42_ODD), [])

    # (5) 同じところに2つ印を立てない（内側は落とす）
    del C._D42_ODD[:]
    C._D42_ODD.extend([(0, 3), (1, 3)])
    got5 = C._odd_spans_for_line('あいうえお', lambda _l: [], ())
    check('内側に入っている印は落とす', got5, [(0, 3)])

    # (6) 直せた範囲と重なる印は消える
    del C._D42_ODD[:]
    C._D42_ODD.append((0, 3))
    got6 = C._odd_spans_for_line('あいうえお', lambda _l: [], [(1, 2)])
    check('直せた範囲と重なる印は消える', got6, [])
    del C._D42_ODD[:]
    return all_ok


def test_48kh_disabled_on_purpose():
    """
    **項目48-KH（正の判定）は、意図的に無効にしてある**
    （2026-08-28・うにさんの指示）。

        「外しましょう。**ただし、まだ消しません。無効にして、
          読まれないようにします。意図的にその状態にしてることが
          わかるようにする**」

    この見張りは「うっかり切れた」と「意図して切った」を分けるため
    に在る。**戻すときは、この見張りも一緒に直す**——旗を True に
    したのに見張りが False のままなら、そこで鳴る。

    外せた理由は 48-KP（K3）で**根が直った**から。48-KH は
    `切り替え時 → 切り返し` を止める**迂回**で、止めていた本体は
    「`替` の音訓 かえ ＋ 送り仮名 え で `きりかええじ` という
    二重の読みを作っていたこと」だった。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import ast
    import corrector as C
    import oddness

    print('--- 項目48-KH（意図的に無効） ---')
    check('旗は False（意図的に切ってある）', C._USE_48KH_SOUND_RUN, False)
    check('入口はいつでも「できあがっていない」と答える',
          C._chunk_is_intact('切り替え時', None), False)
    # **判定そのものは消していない**（戻せる形で残す）
    check('oddness.is_sound_run は残っている',
          callable(getattr(oddness, 'is_sound_run', None)), True)
    # **呼び元は1か所だけ**（そこを切れば全部止まる＝学び22 の裏返し）
    src = open('corrector.py', encoding='utf-8').read()
    n = sum(1 for x in ast.walk(ast.parse(src))
            if isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute)
            and x.func.attr == 'is_sound_run')
    check('is_sound_run の呼び元は corrector に1か所だけ', n, 1)
    # 入口という**構えは残す**（K1 でここへ移す先）
    check('入口 _chunk_is_intact は在る',
          callable(getattr(C, '_chunk_is_intact', None)), True)
    return all_ok


def test_okurigana_double_48kp():
    """
    **送り仮名で二重になる読みを、作るところで直す**
    （項目48-KP・2026-08-28）。

    引き継ぎ H2（2026-08-27）が「**読みを作るところで直すのが本筋**」と
    名指ししていた根:

        `替` の音訓に `かえ` が在り、本文の送り仮名 `え` と繋ぐと
        **`きりかええじ`（え が二重）** ができる。48-KH/KI は
        「この塊は正しい」と先に言って迂回しただけで、
        **二重になる読みを作ること自体は直していなかった**。

    見張るのは `_trim_okurigana_from_readings`（純関数）:

      - 読みのお尻が、後ろに続く平仮名の頭と重なるぶんだけ削る
      - **読みが丸ごと消える形は削らない**（`野`＝の に助詞 `の`・
        `荷`＝に に `に`——送り仮名ではなく助詞）
      - 送り仮名が無ければ何もしない
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import kanji_guess as KG
    T = KG._trim_okurigana_from_readings

    print('--- 項目48-KP（送り仮名で二重になる読み） ---')
    # 替 かえ ＋ え → か（塊の最後の字なので next_char で見る）
    check('替 の かえ は、送り仮名 え のぶんを削る',
          T('替', 0, ['たい', 'かえ', 'がえ'], 'え'), ['たい', 'か', 'が'])
    check('込 の こみ は、送り仮名 み のぶんを削る',
          T('込', 0, ['こみ', 'ごみ'], 'み'), ['こ', 'ご'])
    check('活用が続いても、重なる頭のぶんだけ削る（えて → え）',
          T('替', 0, ['かえ'], 'えて'), ['か'])
    check('重ならなければ削らない',
          T('本', 0, ['ほん', 'もと'], 'を'), ['ほん', 'もと'])
    check('送り仮名が無ければ何もしない',
          T('本', 0, ['ほん'], None), ['ほん'])
    # **丸ごと消える形は削らない**（助詞との区別が付かないため）
    check('野（の）＋助詞 の は削らない（読みが空になる）',
          T('野', 0, ['や', 'の'], 'の'), ['や', 'の'])
    check('荷（に）＋助詞 に は削らない',
          T('荷', 0, ['に'], 'に'), ['に'])
    # 塊の中に送り仮名が在る形（next_char を貰わない道）
    check('塊の中の送り仮名でも効く（込み）',
          T('込み', 0, ['こみ', 'ごみ'], None), ['こ', 'ご'])

    # **両方の道に掛かっている**（学び22）
    import ast
    src = open('kanji_guess.py', encoding='utf-8').read()
    n = sum(1 for x in ast.walk(ast.parse(src))
            if isinstance(x, ast.Call) and isinstance(x.func, ast.Name)
            and x.func.id == '_trim_okurigana_from_readings')
    check('逆算と対の組み立ての両方に掛ける（学び22）', n, 2)

    # 通しの確かめ（表が在るときだけ）
    got = KG.reading_combos('切り替え時')
    if got:
        check('きりかええじ（え が二重）を作らない',
              any('かええ' in r for r in got), False)
        check('きりかえじ には届く', 'きりかえじ' in got, True)
    return all_ok


def test_no_purple_when_left_alone_48ko():
    """
    **「もう直さない」と決めた文字列には、紫を付けない**
    （項目48-KO・2026-08-28）。

    うにさんの指定:「候補の一番下から、**もう直さないと選択学習
    したものは、紫の色がつかないように**して」。

    候補一覧のいちばん下の2つが、どちらもこの意味になる:

        「この補正は不要（X のまま）」  → `decisions.reject`
        「「X」は今後直さない」         → `decisions.protect`

    紫は「**異様だと判定した**」という印（CLAUDE.md ★★）なので、
    本人が「これでよい」と決めた文字列に立て続けるのは判定として
    間違っている。**決めた側が上。**

    印のほうが**狭くても**外れること（`奥悠久子帝` を決めたら
    `久子帝` の印も消える）を見張る——重なりで外しているため。
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
    from decisions import DecisionStore

    print('--- 項目48-KO（もう直さないと決めたものに紫を付けない） ---')

    d = DecisionStore()
    check('決めていなければ、何も外さない',
          C._decided_spans('奥悠久子帝です', d), [])
    d.protect('奥悠久子帝')
    check('「今後直さない」の範囲が出る',
          C._decided_spans('奥悠久子帝です', d), [(0, 5)])
    check('同じ行に2度出れば2つとも出る',
          C._decided_spans('奥悠久子帝と奥悠久子帝', d), [(0, 5), (6, 11)])

    d2 = DecisionStore()
    d2.reject('野外文章', '屋外文章')
    check('「この補正は不要」の側も外す対象になる',
          C._decided_spans('これは野外文章です', d2), [(3, 7)])
    check('決めた文字列は left_alone_texts に出る',
          sorted(d2.left_alone_texts()), ['野外文章'])

    check('判断置き場が無くても落ちない',
          C._decided_spans('奥悠久子帝', None), [])

    # **印のほうが狭くても外れる**（重なりで外す）
    d3 = DecisionStore()
    d3.protect('奥悠久子帝')
    spans = C._odd_spans_for_line('奥悠久子帝', None, (), d3)
    check('解析できないときは今までどおり []', spans, [])
    return all_ok


class _Store:
    """`_swap_to_word` の見張り用の、ごく小さな語彙。"""

    def __init__(self, words):
        self._w = set(words)

    def lookup(self, t):
        return [{'count': 5}] if t in self._w else []


def test_swap_tie_48kn():
    """
    **順序違いの拮抗を、読みの並びで裁く**（項目48-KN・2026-08-28）。

    うにさんの指定:「自然な文であれば補正しなくていいので、**異様な
    文に対してのみ活用**することを検討して。**効果のあるものを活かす**
    ようにしたい」。

    `_swap_to_word`（48-HJ）は入れ替えの戻し先を1通りに絞ったあと、
    **畳み・脱字・濁点でも在る語に届くなら降りて**いた（＝決め手が
    無いので直さない）。そこは CLAUDE.md ★★「異様だと判定したら
    何かしらに決める。候補が複数あることは身を引く理由にならない」に
    当たる場所で、しかも問いの形は**入れ替えか否か**——読みの表が
    いちばん強い問い（順序違いの向き 92.8%・項目48-KL の A）。

    見張るのは `_swap_beats_rivals`（純関数・表があるときだけ意見を
    言う）と、切り替えの向き（**既定で入っている**・`CN_SWAP_TIE=0`
    で切れる）。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import os
    import corrector as C

    print('--- 項目48-KN（順序違いの拮抗を読みの表で裁く） ---')
    keep = os.environ.get('CN_SWAP_TIE')
    try:
        os.environ.pop('CN_SWAP_TIE', None)
        check('既定で入っている', C._swap_tie_enabled(), True)
        os.environ['CN_SWAP_TIE'] = '0'
        check('CN_SWAP_TIE=0 で切れる', C._swap_tie_enabled(), False)
    finally:
        if keep is None:
            os.environ.pop('CN_SWAP_TIE', None)
        else:
            os.environ['CN_SWAP_TIE'] = keep

    # 表が無い環境（janome 無しの CI もここを通る）では**黙る**＝
    # いままでどおり降りる。答えが環境で変わらないようにしておく。
    try:
        import yomigram
        has = yomigram.available()
    except Exception:
        has = False
    if has:
        check('入れ替えの側が自然なら押し切る（こうんか → こうかん）',
              C._swap_beats_rivals('こうかん', ['こうんかん']), True)
        check('差が無ければ黙る（同じ文字列どうし）',
              C._swap_beats_rivals('こうかん', ['こうかん']), False)
        check('相手が無ければ呼ばれない前提（空の相手には黙る）',
              C._swap_beats_rivals('こうかん', []), False)
    else:
        check('表が無ければ黙る（いままでどおり降りる）',
              C._swap_beats_rivals('こうかん', ['こうんかん']), False)

    # **末尾の助詞は入れ替えで動かさない**（項目48-KR・48-DJ を
    # この道にも掛けた）。`かいんに` の `に` は枠の助詞で、
    # 入れ替えると `かいにん`（解任）に吸われて**助詞ごと消える**。
    check('末尾の助詞を巻き込む入れ替えは見ない（かいんに＋keep_tail）',
          C._swap_to_word('かいんに', _Store({'かいにん'}), keep_tail='に'),
          None)
    # **助詞かどうかは呼び元（run_tail_particle）が決める。**
    # `か` `さ` `ぞ` は語の最後の字でもあるので、ここで文字の集合から
    # 決めてはいけない——自前に書いて 初期 readcheck 直った−11 だった
    check('keep_tail が空なら、語末の入れ替えは見る（こうんか）',
          C._swap_to_word('こうんか', _Store({'こうかん'})),
          ('こうかん', 'こうかん'))
    check('同じ並びでも keep_tail が来れば見ない',
          C._swap_to_word('こうんか', _Store({'こうかん'}), keep_tail='か'),
          None)
    import ast as _ast
    _src = open('corrector.py', encoding='utf-8').read()
    _fn = next(n for n in _ast.parse(_src).body
               if isinstance(n, _ast.FunctionDef)
               and n.name == '_swap_to_word')
    check('末尾の助詞の門が入れ替えの道に在る（48-DJ を全部の道に）',
          any(isinstance(n, _ast.Name) and n.id == 'keep_tail'
              for n in _ast.walk(_fn)), True)
    # **呼び元は2か所とも渡す**（学び22）
    _n = sum(1 for n in _ast.walk(_ast.parse(_src))
             if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Name)
             and n.func.id == '_swap_to_word'
             and any(k.arg == 'keep_tail' for k in n.keywords))
    check('入れ替えの道の呼び元2か所とも keep_tail を渡す', _n, 2)

    # **畳みは表に裁かせない**（うにさんの判断・2026-08-28）。
    # `てんんか` は `てんかん` ではなく **`てんか` のまま**が正しい
    # ——天下・点火・添加・転嫁のほうが日常的で、readcheck の
    # 「正解」ラベル（壊す前の語）は日本語の尤もらしさを見ていない。
    # 押し切らせるのは**脱字と濁点の2族だけ**。
    import ast
    src = open('corrector.py', encoding='utf-8').read()
    fn = next(n for n in ast.parse(src).body
              if isinstance(n, ast.FunctionDef) and n.name == '_swap_to_word')
    n_append = sum(1 for n in ast.walk(fn)
                   if isinstance(n, ast.Call)
                   and isinstance(n.func, ast.Attribute)
                   and n.func.attr == 'append'
                   and isinstance(n.func.value, ast.Name)
                   and n.func.value.id == 'rivals')
    check('押し切る相手は脱字と濁点の2族だけ（畳みは外す）', n_append, 2)
    return all_ok


def test_abab_48km():
    """
    **2文字2回（ABAB型）へ1手で戻る崩れ**（項目48-KM・2026-08-28）。

    うにさんの指定:「日本語の繰り返しの特徴は、『そもそも』『わくわく』
    『ぴかぴか』のような2文字2回繰り返し傾向で、『そももそ』『そもそみ』
    などは補正の材料になります」。

    見張るのは `_abab_fix_body`（純関数・切り替えに依らない）:
      - 2候補並ぶのは構造のせい（ABBA は両側に開く）。決め方は
        ①在る語がただ1つならそれ ②1つ目の単位を型とする（48-CV）
      - **`しました` を `しましま`（縞々）にしない**——語彙に載らない
        活用形は `_kana_run_explained`（48-IT）が受け止める。
        この門が無いと fpcheck 誤検知 116件（7.73%）だった（実測）
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

    print('--- 項目48-KM（2文字2回の型） ---')
    nothing = lambda _t: False
    check('そももそ → そもそも（入れ替え・1つ目の単位）',
          C._abab_fix_body('そももそ', nothing),
          ('そもそも', '入れ替え'))
    check('そもそみ → そもそも（隣のキー・1つ目の単位）',
          C._abab_fix_body('そもそみ', nothing),
          ('そもそも', '隣のキー'))
    check('わくわう → わくわく（在る語がただ1つ）',
          C._abab_fix_body('わくわう', lambda t: t == 'わくわく'),
          ('わくわく', '隣のキー'))
    check('わうわく → わくわく（1つ目の単位より在る語）',
          C._abab_fix_body('わうわく', lambda t: t == 'わくわく'),
          ('わくわく', '隣のキー'))
    check('しました は触らない（活用形＝説明が付く並び）',
          C._abab_fix_body('しました', lambda t: t == 'しましま'),
          None)
    check('かたかな は触らない（在る語）',
          C._abab_fix_body('かたかな',
                           lambda t: t in ('かたかな', 'かたかた')),
          None)
    check('どれどれ は触らない（もう ABAB）',
          C._abab_fix_body('どれどれ', nothing),
          None)
    check('小書きが絡む形は対象外（しゃしん）',
          C._abab_fix_body('しゃしん', nothing),
          None)
    return all_ok


def test_pos_grammar_48ks():
    """
    **品詞と活用の文法で、かな連続の異様に紫を立てる**
    （項目48-KS・2026-08-29）。

    うにさんの指定:「文節の末尾が「い」だからイ形容詞、「な」だから
    ナ形容詞、ウ段だから動詞。補助動詞には「て」が付く。品詞を判定
    したり、品詞の組み合わせとしての予測など動いていますか？
    無ければ検討してください」。

    見張るもの:
      1. **述語の尻尾**（漢字の語幹＋活用語尾＋助動詞の連なり）が
         「説明が付く」になること——今まで False だった 85% の側
      2. 的（植えた誤字）には印が立つこと
      3. 守り（正しい文・擬音・名前）には立たないこと
      4. `CN_POS_ODD=0` で切れること
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import os
    import pos_grammar as PG

    print('--- 項目48-KS（品詞と活用の文法・かな連続の紫） ---')

    # 1. 活用の文法（説明が付く側）
    check('り＋ます（五段連用形＋ます）は説明が付く',
          PG.explain_kana_run('ります', after_kanji=True), True)
    check('え＋ているように（一段語幹＋て＋補助動詞）は説明が付く',
          PG.explain_kana_run('えているように', after_kanji=True), True)
    check('く＋なったので（イ形容詞連用形＋なる）は説明が付く',
          PG.explain_kana_run('くなったのでそれはそれでよいですが',
                              after_kanji=True), True)
    check('よかったね（イ形容詞の語幹推定 よ＋かった）は説明が付く',
          PG.explain_kana_run('よかったね'), True)
    check('た＋されます（未然形＋使役受身）は説明が付く',
          PG.explain_kana_run('たされます', after_kanji=True), True)
    check('ゆすかりた は説明が付かない',
          PG.explain_kana_run('ゆすかりた'), False)
    check('ひらんがな は説明が付かない',
          PG.explain_kana_run('ひらんがな'), False)

    # 2. 的（印が立つ）
    for t in ('ゆすかりた', 'たんほの', 'ひらんがな', 'おわりのくてんる'):
        check(f'的 {t!r} に印が立つ',
              bool(PG.odd_kana_spans(t)), True)
    check('的 れちいさい（漢字のあと）に印が立つ',
          [x for x in PG.odd_kana_spans('Pythonを入れちいさいPC')],
          [(8, 13)])

    # 3. 守り（立たない）
    for g in ('よかったね', '思いがけず', 'まずまとめて伝えます。',
              '文字が震えているように見えますが、',
              '作ることができるし、', 'じゅるる', 'なんだお前は！',
              'うにさんの読みが正しかった',
              'お解りになりますまいがお米粒は',
              '紙へ包むどころではありません。',
              '定めなければうっかり戦争も出来ない訳だ。'):
        check(f'守り {g!r} は無傷',
              PG.odd_kana_spans(g), [])

    # 4. correct_line 経由——★★ の約束「判定したら 直る か 紫」
    import corrector as C
    from tests_mock_common import build_store
    store = build_store()
    tok = C.make_tokenizer(store)
    r = C.correct_line('ゆすかりた', store, tok, lambda *a, **k: [])
    check('ゆすかりた は 直る か 紫が付く',
          bool(r['changed'] or r['odd_spans']), True)
    r = C.correct_line('文字が震えているように見えますが、',
                       store, tok, lambda *a, **k: [])
    check('自然な文に紫は付かない（correct_line 経由）',
          r['odd_spans'], [])

    # 5. 切り替え
    os.environ['CN_POS_ODD'] = '0'
    try:
        r = C.correct_line('ゆすかりた', store, tok, lambda *a, **k: [])
        check('CN_POS_ODD=0 で紫が消える（答えは元から変えない）',
              [] if not r['changed'] else r['odd_spans'], [])
    finally:
        del os.environ['CN_POS_ODD']

    # 6. **小書きで終わる断片＋未知のカタカナ断片**（oddness 側の口。
    #    `にゅカミス`——にゅ も カミス も辞書に無いので、「相手は
    #    載っている語」の条件では拾えなかった型）
    import oddness as O
    if O.available():
        check('にゅカミス に印が立つ（oddness）',
              bool(O.is_odd_run('にゅカミス', tok)), True)
        check('ぴよピヨ は無傷（小書きで終わらない＝かな崩し）',
              O.is_odd_run('ぴよピヨ', tok), [])
    return all_ok


def test_run_reading_merge_48kt():
    """
    **読みを繋ぐと、よくある1語**（項目48-KT・2026-08-29）。

    うにさんの正解メモ「待ち外の補正 ⇒ 間違いの補正」。
    待ち外 ＝ 待ち（まち）＋外（がい・接尾）で、繋ぐと まちがい＝間違い。
    janome の無い環境では品詞が取れないので、**品詞列を手で差して**
    判定と門を見張る（材料の形は本物の janome の出力と同じ）。
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

    print('--- 項目48-KT（読みを繋ぐと1語） ---')

    class _St(object):
        """語彙の代役: まちがい → 間違い(2回) だけを知っている。"""
        def reading_of(self, s):
            return None

        def lookup(self, r):
            if r == 'まちがい':
                return [{'surface': '間違い', 'count': 2}]
            if r == 'かじ':
                return [{'surface': '火事', 'count': 2},
                        {'surface': '家事', 'count': 2}]
            return []

    st = _St()

    def tok_machigai(_line):
        return [('待ち', '名詞:一般', 'マチ', 0, 2, True),
                ('外', '名詞:接尾:一般', 'ガイ', 2, 3, True),
                ('の', '助詞:連体化', 'ノ', 3, 4, True),
                ('補正', '名詞:サ変接続', 'ホセイ', 4, 6, True)]

    check('待ち外の補正 → 間違い（直し先がただ1つ）',
          C._run_reading_merge_fixes('待ち外の補正', tok_machigai, st),
          [(0, 3, '間違い')])

    # **前に名詞が付いているなら見ない**（最大|化時 の 化時）
    def tok_kaji(_line):
        return [('最大', '名詞:一般', 'サイダイ', 0, 2, True),
                ('化', '名詞:接尾:サ変接続', 'カ', 2, 3, True),
                ('時', '名詞:接尾:副詞可能', 'ジ', 3, 4, True)]

    del C._ODD_PENDING[:]
    check('最大化時 の 化時 は見ない（前に名詞が付いている）',
          C._run_reading_merge_fixes('最大化時', tok_kaji, st), [])
    check('紫も積まない（判定の外）', list(C._ODD_PENDING), [])

    # **読みが立っていないなら判定しない**（janome の推測読み）
    def tok_unknown(_line):
        return [('待ち', '名詞:一般', 'マチ', 0, 2, True),
                ('外', '名詞:接尾:一般', 'ガイ', 2, 3, False)]

    check('読みが立っていなければ触らない',
          C._run_reading_merge_fixes('待ち外', tok_unknown, st), [])

    # **頭が接尾なら語の頭ではない**（高|さ|位置 の さ位置。育ちの
    # 実測で 高さ位置 → 高才智 と化けた——受け止める判定）
    class _St2(_St):
        def lookup(self, r):
            if r == 'さいち':
                return [{'surface': '才智', 'count': 3}]
            return _St.lookup(self, r)

    def tok_saichi(_line):
        return [('高', '接頭詞:名詞接続', 'タカ', 0, 1, True),
                ('さ', '名詞:接尾:特殊', 'サ', 1, 2, True),
                ('位置', '名詞:一般', 'イチ', 2, 4, True)]

    check('高さ位置 の さ位置 は見ない（頭が接尾）',
          C._run_reading_merge_fixes('高さ位置', tok_saichi, _St2()), [])

    # **直し先が複数なら、紫だけ残す**（48-JW の形）
    def tok_two(_line):
        return [('化', '名詞:一般', 'カ', 0, 1, True),
                ('時', '名詞:接尾:副詞可能', 'ジ', 1, 2, True)]

    del C._ODD_PENDING[:]
    check('表記が複数なら直さない',
          C._run_reading_merge_fixes('化時', tok_two, st), [])
    check('そのかわり紫だけ残す', list(C._ODD_PENDING), [(0, 2)])
    del C._ODD_PENDING[:]
    return all_ok


def test_kt_hands_48ku():
    """
    **接尾の枠を保った「う挿入」**（項目48-KU・2026-08-29）。

    うにさんの一覧「囚虜時　しゅうりょじ ⇒ しゅうりょうじ　終了時」。
    前の部分の読みに長音の脱字（う）を1つ戻すと、ずっとよく使う語に
    なる形。品詞列を手で差して、門を見張る。
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

    print('--- 項目48-KU（接尾の枠を保った う挿入） ---')

    class _St(object):
        def __init__(self, entries):
            self._e = entries

        def reading_of(self, s):
            return None

        def lookup(self, r):
            return self._e.get(r, [])

    def tok_shuryo(_line):
        return [('囚虜', '名詞:一般', 'シュウリョ', 0, 2, True),
                ('時', '名詞:接尾:副詞可能', 'ジ', 2, 3, True)]

    st = _St({'しゅうりょ': [{'surface': '囚虜', 'count': 6}],
              'しゅうりょう': [{'surface': '終了', 'count': 554},
                               {'surface': '修了', 'count': 1}]})
    check('囚虜時 → 終了時（優勢 554 >= 20×6）',
          C._run_reading_merge_fixes('囚虜時', tok_shuryo, st),
          [(0, 3, '終了時')])

    st2 = _St({'しゅうりょ': [{'surface': '囚虜', 'count': 6}],
               'しゅうりょう': [{'surface': '終了', 'count': 100}]})
    check('優勢が 20倍未満（100 < 120）なら触らない',
          C._run_reading_merge_fixes('囚虜時', tok_shuryo, st2), [])

    # **前が漢字1字なら見ない**（秒数 → 表数 の誤爆を受け止めた門）
    def tok_byosu(_line):
        return [('秒', '名詞:一般', 'ビョウ', 0, 1, True),
                ('数', '名詞:接尾:一般', 'スウ', 1, 2, True)]

    st3 = _St({'びょう': [{'surface': '秒', 'count': 1}],
               'びょうう': [{'surface': '病雨', 'count': 99}]})
    check('1字の漢字＋接尾は見ない（秒数）',
          C._run_reading_merge_fixes('秒数', tok_byosu, st3), [])

    # **後ろが接尾でないなら見ない**（状態・資料は一般名詞）
    def tok_jotai(_line):
        return [('初期', '名詞:一般', 'ショキ', 0, 2, True),
                ('状態', '名詞:一般', 'ジョウタイ', 2, 4, True)]

    st4 = _St({'しょき': [], 'しょきう': [{'surface': '書きう', 'count': 99}],
               'しょうき': [{'surface': '詳記', 'count': 99}]})
    check('後ろが一般名詞なら見ない（初期状態）',
          C._run_reading_merge_fixes('初期状態', tok_jotai, st4), [])
    return all_ok


def test_shift_toggle_48kv():
    """
    **場違いな大書き（Shift の押し忘れ）を小書きに戻す**
    （項目48-KV・2026-08-29）。

    うにさんの一覧「にゆうりよくみす　にゅうりょくみす　入力ミス」。
    ① 48-KS の異様判定が立つ連続だけ開く／③ い段＋大書き やゆよ →
    小書き（全部まとめて）／④ 世の中の読みで敷き詰められるときだけ。
    janome の無い環境では世の中の読みを差して見張る。
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

    print('--- 項目48-KV（場違いな大書き） ---')

    class _Di(object):
        """dict_index の代役: 世の中の読みを2つだけ知っている。"""
        def __init__(self, world):
            self._w = set(world)

        def is_world_reading(self, r):
            return r in self._w

        def readings_for_surface(self, s):
            return []

    class _St(object):
        def reading_of(self, s):
            return None

        def lookup(self, r):
            return []

    di = _Di({'にゅうりょく', 'みす'})
    st = _St()

    check('にゆうりよくみす → にゅうりょくみす（2か所まとめて）',
          C._misplaced_large_kana_fixes('にゆうりよくみす', st, di),
          [(0, 8, 'にゅうりょくみす', 'かな入力')])

    # **元が読める並びなら触らない**（がいしゅつする 型の守り）
    di2 = _Di({'にゅうりょく', 'みす', 'にゆうりよくみす'})
    check('元がまるごと世の中の読みなら開かない',
          C._misplaced_large_kana_fixes('にゆうりよくみす', st, di2), [])

    # **直しても読めないなら証拠不足**
    di3 = _Di(set())
    check('直した形が敷き詰められないなら触らない',
          C._misplaced_large_kana_fixes('にゆうりよくみす', st, di3), [])

    # **異様と判定していない連続は開かない**（よかったね は正しい文）
    check('正しい文は開かない',
          C._misplaced_large_kana_fixes('よかったね', st, di), [])

    check('dict_index が無ければ意見なし',
          C._misplaced_large_kana_fixes('にゆうりよくみす', st, None), [])

    # ⑤ **変換が既定**（うにさんの指定・2026-08-29 の2度目の正し:
    # 「かなのまま打ちたいことの確信がなければ漢字変換する」）
    class _Di2(_Di):
        def surfaces_for_reading(self, r):
            return {'みす': ['ミス']}.get(r, [])

    class _St2(_St):
        def lookup(self, r):
            if r == 'にゅうりょく':
                return [{'surface': '入力', 'count': 3}]
            return []

    di4 = _Di2({'にゅうりょく', 'みす'})
    check('にゆうりよくみす → 入力ミス（シフト補正した漢字変換）',
          C._misplaced_large_kana_fixes('にゆうりよくみす', _St2(), di4),
          [(0, 8, '入力ミス', 'かな入力')])
    check('にゅうりょくみす（手なし）も変換する',
          C._misplaced_large_kana_fixes('にゅうりょくみす', _St2(), di4),
          [(0, 8, '入力ミス', 'かな入力')])
    check('にゅりょくみす（う挿入）も変換する',
          C._misplaced_large_kana_fixes('にゅりょくみす', _St2(), di4),
          [(0, 7, '入力ミス', 'かな入力')])

    # **う挿入は変換（錨つき）まで立つときだけ**——かな止まりで出すと
    # たんほの → たんほうの を作った（実測）
    di5 = _Di({'たんほう'})
    check('う挿入のかな止まりは出さない（たんほの）',
          C._misplaced_large_kana_fixes('たんほの', _St(), di5), [])

    # **細切れの敷き詰めでは変換しない**（先頭の区切りは語彙 count>=2
    # かつ4字以上。すきにん → 好きにん・がいしょつする → 害しようつする
    # を作らない・育ちの実測で受け止めた門）
    class _St3(_St):
        def lookup(self, r):
            if r == 'すき':
                return [{'surface': '好き', 'count': 5}]
            return []

    class _Di3(_Di):
        def surfaces_for_reading(self, r):
            return {'にん': ['人']}.get(r, [])

    di6 = _Di3({'すき', 'にん'})
    check('すきにん は変換しない（先頭の区切りが2字）',
          C._misplaced_large_kana_fixes('すきにん', _St3(), di6), [])
    return all_ok


def test_pos_open_48kw():
    """
    **開く判定の品詞強化**（項目48-KW・2026-08-29）。

    うにさんの指示「平仮名に正しく開くことができれば補正が効いている
    ものがあります。漢字を平仮名に開く判定を改善します。それには
    品詞の強化が必要かもしれない」。

      1. かな交じりの形容動詞語幹＋名詞の直付き＝異様（好き任。
         ナ形容詞は「な」を経て名詞に付く——「な」だからナ形容詞）
      2. 助詞の「ん」＋漢字の名詞＝異様（平ん仮名。撥音は語の途中の
         音で、名詞と名詞の間には立てない）
      3. 動詞の連体形＋数詞＋助数詞で、読みの1字を落とすと優勢の語
         （貸す九人 → かくにん＝確認）
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
    import oddness as O

    print('--- 項目48-KW（開く判定の品詞強化） ---')

    if O.available():
        check('好き（かな交じりの形容動詞語幹）＋任 はくっつけない',
              O.can_join('好き', '名詞:形容動詞語幹', '任', '名詞:一般'),
              False)
        check('安全（漢語の語幹）＋確認 はくっつける',
              O.can_join('安全', '名詞:形容動詞語幹', '確認',
                         '名詞:サ変接続') is not False, True)
        check('静か＋さ（接尾）はくっつける',
              O.can_join('静か', '名詞:形容動詞語幹', 'さ',
                         '名詞:接尾:特殊') is not False, True)

        def tok_hiran(_line):
            return [('平', '名詞:一般', 'タイラ', 0, 1, True),
                    ('ん', '助詞:格助詞:一般', 'ン', 1, 2, True),
                    ('仮名', '名詞:一般', 'カメイ', 2, 4, True)]

        check('助詞の ん＋漢字の名詞 は異様（平ん仮名）',
              O.is_odd_run('平ん仮名', tok_hiran), [('ん', '仮名')])

        def tok_nchi(_line):
            return [('僕', '名詞:代名詞', 'ボク', 0, 1, True),
                    ('ん', '助詞:格助詞:一般', 'ン', 1, 2, True),
                    ('家', '名詞:一般', 'イエ', 2, 3, True)]

        check('ん家（おれんち）は見ない',
              O.is_odd_run('僕ん家', tok_nchi), [])

    # 3. 貸す九人（品詞列を手で差す）
    class _St(object):
        def reading_of(self, s):
            return None

        def lookup(self, r):
            if r == 'かくにん':
                return [{'surface': '確認', 'count': 3}]
            return []

    def tok_kasu(_line):
        return [('貸す', '動詞:自立', 'カス', 0, 2, True),
                ('九', '名詞:数', 'キュウ', 2, 3, True),
                ('人', '名詞:接尾:助数詞', 'ニン', 3, 4, True)]

    check('貸す九人 → 確認（読みの1字落とし＋優勢）',
          C._run_reading_merge_fixes('貸す九人', tok_kasu, _St()),
          [(0, 4, '確認')])

    def tok_atsumaru(_line):
        return [('集まる', '動詞:自立', 'アツマル', 0, 3, True),
                ('十', '名詞:数', 'ジュウ', 3, 4, True),
                ('人', '名詞:接尾:助数詞', 'ニン', 4, 5, True)]

    check('集まる十人 は触らない（読みがどの語にも届かない）',
          C._run_reading_merge_fixes('集まる十人', tok_atsumaru, _St()), [])
    return all_ok


def test_head_particle_48kx():
    """
    **行頭の1字助詞＋漢字の名詞は異様**（項目48-KX・2026-08-29）。

    うにさんの一覧「も水戸に戻ります（もとにもどります）」
    「に有力ミス（にゅうりょくみす）」。係助詞・格助詞は前の句が
    要る——「文の頭だから接続詞。文の間だから助詞」の裏返し。
    **本当の行頭だけ**（読点・閉じ括弧のあとの助詞は前の句を受ける
    正しい形。緩めると実機メモ36行が誤爆した・実測）。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import oddness as O

    print('--- 項目48-KX（行頭の1字助詞） ---')
    if not O.available():
        print('  （表が無いので飛ばす）')
        return all_ok

    def tok_mito(_line):
        return [('も', '助詞:係助詞', 'モ', 0, 1, True),
                ('水戸', '名詞:固有名詞', 'ミト', 1, 3, True),
                ('に', '助詞:格助詞', 'ニ', 3, 4, True),
                ('戻り', '動詞:自立', 'モドリ', 4, 6, True),
                ('ます', '助動詞', 'マス', 6, 8, True)]

    check('行頭の も＋水戸 は異様',
          O.is_odd_run('も水戸に戻ります', tok_mito), [('も', '水戸')])

    def tok_quote(_line):
        return [('「」', '記号:括弧閉', '', 0, 2, True),
                ('を', '助詞:格助詞', 'ヲ', 2, 3, True),
                ('付与', '名詞:サ変接続', 'フヨ', 3, 5, True)]

    check('閉じ括弧のあとの を は正しい形（見ない）',
          O.is_odd_run('「」を付与', tok_quote), [])

    def tok_bullet(_line):
        return [('・', '記号:一般', '', 0, 1, True),
                ('も', '助詞:係助詞', 'モ', 1, 2, True),
                ('水戸', '名詞:固有名詞', 'ミト', 2, 4, True)]

    check('行頭の中黒は読み飛ばして判定する',
          O.is_odd_run('・も水戸', tok_bullet), [('も', '水戸')])
    return all_ok


def test_mishi_48kx():
    """
    **1字の漢字の動詞＋「し」は異様**（項目48-KX の2つ目・2026-08-29）。
    `設計の見して`（せっけいのみして）。門は「前に漢字が付くなら
    見ない」（自走して が 自|走|し と割れて誤爆した・実測）と
    「次の字まで含めて語になるなら見ない」（来し方）。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import oddness as O

    print('--- 項目48-KX（1字の動詞＋し） ---')
    if not O.available():
        print('  （表が無いので飛ばす）')
        return all_ok

    def tok_mishi(_line):
        return [('設計', '名詞:サ変接続', 'セッケイ', 0, 2, True),
                ('の', '助詞:連体化', 'ノ', 2, 3, True),
                ('見', '動詞:自立', 'ミ', 3, 4, True),
                ('し', '動詞:自立', 'シ', 4, 5, True),
                ('て', '助詞:接続助詞', 'テ', 5, 6, True)]

    check('設計の見して の 見し は異様',
          O.is_odd_run('設計の見して', tok_mishi), [('見', 'し')])

    def tok_jisou(_line):
        return [('自', '接頭詞:名詞接続', 'ジ', 0, 1, True),
                ('走', '動詞:自立', 'ソウ', 1, 2, True),
                ('し', '動詞:自立', 'シ', 2, 3, True),
                ('て', '助詞:接続助詞', 'テ', 3, 4, True)]

    check('自走して は見ない（前に漢字）',
          O.is_odd_run('自走して', tok_jisou), [])
    return all_ok


def test_te_i_piece_48ky():
    """
    **て・で の直後の「い」（補助動詞 いる）は機能語の部品**
    （項目48-KY・2026-08-29）。無いと `していたり` が機能語の並びとして
    異様になり、い を落として `してたり` に壊した（うにさんの一覧
    32行目・実測）。がうく の穴は開かない——い を置けるのは
    て・で の直後だけ。
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

    print('--- 項目48-KY（て＋い の部品） ---')
    check('していたり は機能語で説明が付く',
          C._is_functional_strict('していたり'), True)
    check('でいたり も付く', C._is_functional_strict('でいたり'), True)
    check('がうく は付かない（穴は開かない）',
          C._is_functional_strict('がうく'), False)
    check('していたり を 48-IT が直さない',
          C._fix_functional_run('していたり', False), None)
    check('ににして は今までどおり直す',
          C._fix_functional_run('ににして', False), 'にして')
    return all_ok


def test_compose_kana_run_48ky():
    """
    **かな連続を「語幹（実績2以上）＋接尾」で漢字に組む**
    （項目48-KY・2026-08-29）。しゅうりょうじ → 終了時。
    語幹の実績の門: 辞書だけの語幹（鋳物）は組まない。
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

    print('--- 項目48-KY（語幹＋接尾で組む前段） ---')

    class _St(object):
        def __init__(self, table):
            self._t = table

        def reading_of(self, s):
            return None

        def lookup(self, r):
            return self._t.get(r, [])

    class _Di(object):
        def surfaces_for_reading(self, r):
            return []

        def readings_for_surface(self, s):
            return []

        def is_world_reading(self, r):
            return False

    st = _St({'しゅうりょう': [{'surface': '終了', 'count': 3}]})
    check('しゅうりょうじ → 終了時（語幹の実績3）',
          C._compose_kana_run_fixes('しゅうりょうじ', st, _Di()),
          [(0, 7, '終了時', 'かな入力')])

    st2 = _St({'いもの': [{'surface': '鋳物', 'count': 1}]})
    check('実績1の語幹では組まない（いものか）',
          C._compose_kana_run_fixes('いものか', st2, _Di()), [])
    check('dict_index が無ければ意見なし',
          C._compose_kana_run_fixes('しゅうりょうじ', st, None), [])
    return all_ok


def test_small_kana_neighbor_48ky():
    """
    **拗音・小書き母音の前は ひらがな・括弧・行頭に限る**（項目48-KY・
    うにさんの指定）と、**「を」の直後の助詞は異様**（同）。
    促音 っ は除く（打っ・持っ＝漢字の送り仮名が100か所超・全部正しい）。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import pos_grammar as PG
    import oddness as O

    print('--- 項目48-KY（小書きの前・を＋助詞） ---')
    check('二ゅ（漢字のあとの拗音）に印',
          (0, 2) in PG.odd_kana_spans('二ゅ力ミス'), True)
    check('打っ（促音の送り仮名）は無傷',
          PG.odd_kana_spans('文字を打って'), [])
    check('「ゅ」（括弧の中）は無傷',
          PG.odd_kana_spans('「ゅ」の字'), [])

    if O.available():
        def tok_wo(_line):
            return [('再起動', '名詞:サ変接続', 'サイキドウ', 0, 3, True),
                    ('を', '助詞:格助詞', 'ヲ', 3, 4, True),
                    ('など', '助詞:副助詞', 'ナド', 4, 6, True),
                    ('を', '助詞:格助詞', 'ヲ', 6, 7, True)]

        check('を＋など は異様',
              O.is_odd_run('再起動をなどを', tok_wo), [('を', 'など')])

        def tok_womo(_line):
            return [('これ', '名詞:代名詞', 'コレ', 0, 2, True),
                    ('を', '助詞:格助詞', 'ヲ', 2, 3, True),
                    ('も', '助詞:係助詞', 'モ', 3, 4, True)]

        check('をも は正しい形（見ない）',
              O.is_odd_run('これをも', tok_womo), [])
    return all_ok


def test_pos_pair_rules_48kz():
    """
    **品詞対の規則の束**（項目48-KZ・2026-08-29・うにさんの指定6件を
    測って締めた形）。的の見本は cases_pos_rules_20260829.tsv。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import oddness as O

    print('--- 項目48-KZ（品詞対の規則の束） ---')
    if not O.available():
        print('  （表が無いので飛ばす）')
        return all_ok

    def tk(*rows):
        toks = []
        p = 0
        for sf, pos in rows:
            toks.append((sf, pos, sf, p, p + len(sf), True))
            p += len(sf)
        return lambda _l: toks

    check('(A) 赤い＋だ は異様',
          O.is_odd_run('赤いだ', tk(('赤い', '形容詞:自立'),
                                    ('だ', '助動詞'))), [('赤い', 'だ')])
    check('(A) よい＋です は正しい（丁寧形）',
          O.is_odd_run('よいです', tk(('よい', '形容詞:自立'),
                                      ('です', '助動詞'))), [])
    check('(B) 戻す＋する は異様（ウ段＋動詞）',
          O.is_odd_run('戻すする', tk(('戻す', '動詞:自立'),
                                      ('する', '動詞:自立'))),
          [('戻す', 'する')])
    check('(B) やる＋やる は見ない（繰り返し）',
          O.is_odd_run('やるやる', tk(('やる', '動詞:自立'),
                                      ('やる', '動詞:自立'))), [])
    check('(C) はい＋を は異様',
          O.is_odd_run('はいを', tk(('はい', '感動詞'),
                                    ('を', '助詞:格助詞'))),
          [('はい', 'を')])
    check('(D) を＋に は異様',
          O.is_odd_run('をに', tk(('を', '助詞:格助詞'),
                                  ('に', '助詞:格助詞'))), [('を', 'に')])
    check('(D) から＋が は正しい（ここからが本番）',
          O.is_odd_run('からが', tk(('から', '助詞:格助詞'),
                                    ('が', '助詞:格助詞'))), [])
    check('(E) しかし＋を は異様',
          O.is_odd_run('しかしを', tk(('しかし', '接続詞'),
                                      ('を', '助詞:格助詞'))),
          [('しかし', 'を')])
    check('(F) ぬ＋ぬ は異様（強調ぬぬ）',
          O.is_odd_run('ぬぬ', tk(('ぬ', '助動詞'), ('ぬ', '助動詞'))),
          [('ぬ', 'ぬ')])
    check('(R2) その＋が は異様',
          O.is_odd_run('そのが', tk(('その', '連体詞'),
                                    ('が', '助詞:格助詞'))),
          [('その', 'が')])
    check('(R2) ある＋が は見ない（あるがまま）',
          O.is_odd_run('あるが', tk(('ある', '連体詞'),
                                    ('が', '助詞:格助詞'))), [])
    check('(R3) 平＋ね＋仮名 は異様',
          O.is_odd_run('平ね仮名', tk(('平', '名詞:一般'),
                                      ('ね', '助詞:終助詞'),
                                      ('仮名', '名詞:一般'))),
          [('平ね', '仮名')])
    return all_ok


def test_adjective_tail_48kz():
    """
    **形容詞の語幹＋「て」→「い」**（項目48-KZ S2・うにさんの案
    「文節最後の文字を隣接キーと疑ったらイ形容詞として自然に
    繋がったり」）。動作が重て、→ 動作が重い、。
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

    print('--- 項目48-KZ S2（形容詞の語幹＋て） ---')

    class _St(object):
        def reading_of(self, s):
            return 'おもい' if s == '重い' else None

        def lookup(self, r):
            return []

    def tok_omote(_line):
        return [('動作', '名詞:サ変接続', 'ドウサ', 0, 2, True),
                ('が', '助詞:格助詞', 'ガ', 2, 3, True),
                ('重', '形容詞:自立', 'オモ', 3, 4, True),
                ('て', '助詞:接続助詞', 'テ', 4, 5, True)]

    check('重て → て の位置を い に',
          C._adjective_tail_fixes('動作が重て', _St(), tok_omote),
          [(4, 5, 'い')])

    def tok_kaite(_line):
        return [('書い', '動詞:自立', 'カイ', 0, 2, True),
                ('て', '助詞:接続助詞', 'テ', 2, 3, True)]

    check('書いて（動詞のて形）は見ない',
          C._adjective_tail_fixes('書いて', _St(), tok_kaite), [])

    class _St0(object):
        def reading_of(self, s):
            return None

        def lookup(self, r):
            return []

    check('語幹＋い が引けなければ触らない',
          C._adjective_tail_fixes('動作が重て', _St0(), tok_omote), [])
    return all_ok


def test_lc_hand_unit_48lc():
    """
    **読みに手を1つ加えると、優勢な単位**（項目48-LC・2026-08-29）。

    うにさんの一覧の〜化の族（再退化 ⇒ 最大化 など）。janome の
    無い環境では品詞が取れないので、品詞列を手で差して判定と門を
    見張る（48-KT の見張りと同じ形）。
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

    print('--- 項目48-LC（読みの1手先に優勢な単位） ---')

    class _St(object):
        data = {}

        def reading_of(self, s):
            return None

        def lookup(self, r):
            return [dict(surface=s, count=c)
                    for s, c in self.data.get(r, ())]

    # (1) ゛追加 → 語幹＋接尾の組み立て（再退化 ⇒ 最大化）
    st = _St()
    st.data = {'さいだい': (('最大', 40),)}

    def tok_saitaika(_line):
        return [('再', '接頭詞:名詞接続', 'サイ', 0, 1, True),
                ('退化', '名詞:サ変接続', 'タイカ', 1, 3, True)]

    check('再退化 → 最大化（゛追加・語幹＋接尾）',
          C._run_reading_merge_fixes('再退化', tok_saitaika, st),
          [(0, 3, '最大化')])

    # (2) そのままの読みで 語幹＋接尾 が組める＝正しい複合語は触らない
    #     （符号化 → 不幸化 を受け止める判定・48-KU の実測）
    st2 = _St()
    st2.data = {'ふごう': (('符号', 12),), 'ふこう': (('不幸', 30),)}

    def tok_fugouka(_line):
        return [('符号', '名詞:一般', 'フゴウ', 0, 2, True),
                ('化', '名詞:接尾:サ変接続', 'カ', 2, 3, True)]

    check('符号化 は触らない（そのままで 符号＋化 が組める）',
          C._run_reading_merge_fixes('符号化', tok_fugouka, st2), [])

    # (3) 面が競う（20倍に届かない）→ 紫だけ（48-JW の形）
    st3 = _St()
    st3.data = {'さいだい': (('最大', 40),), 'さいてい': (('最低', 30),)}
    del C._ODD_PENDING[:]
    check('最大化40と最低化30が競うなら直さない',
          C._run_reading_merge_fixes('再退化', tok_saitaika, st3), [])
    check('紫は積む（判定は立った）', list(C._ODD_PENDING), [(0, 3)])

    # (4) 1字トークンの読みの丸ごと削除は打ち間違いではない
    #     （スクロール語 → スクロール と「語」を消した・実測）
    st4 = _St()
    st4.data = {'すくろーる': (('スクロール', 50),)}

    def tok_sukuro(_line):
        return [('スクロール', '名詞:一般', 'スクロール', 0, 5, True),
                ('語', '名詞:接尾:一般', 'ゴ', 5, 6, True)]

    del C._ODD_PENDING[:]
    check('スクロール語 の 語 は消さない',
          C._run_reading_merge_fixes('スクロール語', tok_sukuro, st4), [])
    check('紫も積まない', list(C._ODD_PENDING), [])

    # (5) L=3・後ろの語は触っていない2語の組（引き月資料 ⇒ 引き継ぎ資料）
    st5 = _St()
    st5.data = {'ひきつぎ': (('引き継ぎ', 82),)}

    def tok_hikitsuki(_line):
        return [('引き', '名詞:一般', 'ヒキ', 0, 2, True),
                ('月', '名詞:一般', 'ツキ', 2, 3, True),
                ('資料', '名詞:一般', 'シリョウ', 3, 5, True)]

    check('引き月資料 → 引き継ぎ資料（後ろは元のまま）',
          C._run_reading_merge_fixes('引き月資料', tok_hikitsuki, st5),
          [(0, 5, '引き継ぎ資料')])
    return all_ok


def test_kana_run_hand_48ld():
    """
    **素のかな連なりに手を1つ加えると、優勢な単位**（項目48-LD・
    2026-08-29）。さいたいか → 最大化。文字列基準（トークン不要）
    なので janome 無しでもそのまま見張れる。
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

    print('--- 項目48-LD（かな連なりの1手先の優勢な単位） ---')

    class _St(object):
        data = {}

        def reading_of(self, s):
            return None

        def lookup(self, r):
            return [dict(surface=s, count=c)
                    for s, c in self.data.get(r, ())]

    _di = object()          # LD は辞書を「在るか」しか見ない

    # (1) ゛追加 → 語幹＋接尾（さいたいか ⇒ 最大化）
    st = _St()
    st.data = {'さいだい': (('最大', 40),)}
    check('さいたいか → 最大化（゛追加・語幹＋接尾）',
          C._kana_run_hand_fixes('さいたいか', st, _di),
          [(0, 5, '最大化', 'かな入力')])

    # (2) そのまま語＋語に割れる形は、手を出さずそのまま組む（⑤既定）。
    #     手の版が ぎ→ぐ で 引き継ぐ資料 に壊した実測の受け止め
    st2 = _St()
    st2.data = {'ひきつぎ': (('引き継ぎ', 82),),
                'しりょう': (('資料', 21),),
                'ひきつぐ': (('引き継ぐ', 50),)}
    check('ひきつぎしりょう → 引き継ぎ資料（そのまま語＋語）',
          C._kana_run_hand_fixes('ひきつぎしりょう', st2, _di),
          [(0, 8, '引き継ぎ資料', 'かな入力')])

    # (3) そのままで語彙の語なら触らない
    st3 = _St()
    st3.data = {'さいしょう': (('最小', 800),)}
    check('さいしょう は語彙の語なので触らない',
          C._kana_run_hand_fixes('さいしょう', st3, _di), [])

    # (4) 面が競う（20倍に届かない）→ 紫だけ
    st4 = _St()
    st4.data = {'さいだい': (('最大', 40),), 'さいてい': (('最低', 30),)}
    del C._ODD_PENDING[:]
    check('最大化40と最低化30が競うなら直さない',
          C._kana_run_hand_fixes('さいたいか', st4, _di), [])
    check('紫は積む（判定は立った）', list(C._ODD_PENDING), [(0, 5)])

    # (5) 前後に漢字・カタカナが付く連なりは文の一部なので見ない
    st5 = _St()
    st5.data = {'さいだい': (('最大', 40),)}
    check('漢字に続くかなは見ない',
          C._kana_run_hand_fixes('値さいたいか', st5, _di), [])
    return all_ok


def test_onbin_48ll():
    """
    **音便と た/だ の相補分布**（項目48-LL・2026-08-30）。
    読んて → 読んで・泳いた → 泳いだ。品詞列を手で差して見張る。
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

    print('--- 項目48-LL（音便のあとの た/だ） ---')

    class _Di(object):
        world = {'およぐ'}

        def is_world_reading(self, r):
            return r in self.world or r in ('かく', 'きく', 'かぐ')

    class _St(object):
        def reading_of(self, s):
            return None

        def lookup(self, r):
            return []

    def tok_yonta(_line):
        return [('読ん', '動詞:自立', 'ヨン', 0, 2, True),
                ('た', '助動詞', 'タ', 2, 3, True)]

    check('読んた → た を だ に（撥音便）',
          C._onbin_dakuten_fixes('読んた', _St(), tok_yonta, _Di()),
          [(2, 3, 'だ')])

    def tok_oyoita(_line):
        return [('泳い', '動詞:自立', 'オヨイ', 0, 2, True),
                ('た', '助動詞', 'タ', 2, 3, True)]

    check('泳いた → だ（ガ行のイ音便・およぐ在り およく無し）',
          C._onbin_dakuten_fixes('泳いた', _St(), tok_oyoita, _Di()),
          [(2, 3, 'だ')])

    def tok_kaite(_line):
        return [('書い', '動詞:自立', 'カイ', 0, 2, True),
                ('て', '助詞:接続助詞', 'テ', 2, 3, True)]

    check('書いて は触らない（かく が在る）',
          C._onbin_dakuten_fixes('書いて', _St(), tok_kaite, _Di()), [])

    def tok_isoite(_line):
        return [('急い', '動詞:自立', 'イソイ', 0, 2, True),
                ('て', '助詞:接続助詞', 'テ', 2, 3, True)]

    class _Di2(_Di):
        world = {'いそぐ'}

    check('急いて は名簿で触らない（急く せく が正しいことがある）',
          C._onbin_dakuten_fixes('急いて', _St(), tok_isoite, _Di2()), [])

    def tok_nante(_line):
        return [('なんて', '助詞:副助詞', 'ナンテ', 0, 3, True),
                ('こと', '名詞:非自立:一般', 'コト', 3, 5, True)]

    check('なんて は動詞ではないので見ない',
          C._onbin_dakuten_fixes('なんてこと', _St(), tok_nante, _Di()),
          [])
    return all_ok


def test_zero_edge_48lm():
    """
    **実績0の語ふたつは、縁を信じない**（項目48-LM・2026-08-30）。
    解す咳 → 解析（余分な す が作った切り方の産物）。
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

    print('--- 項目48-LM（実績0の語ふたつ・縁を信じない） ---')

    class _St(object):
        data = {}

        def reading_of(self, s):
            return None

        def lookup(self, r):
            return [dict(surface=s, count=c)
                    for s, c in self.data.get(r, ())]

    st = _St()
    st.data = {'かいせき': (('解析', 618),)}

    def tok_kaisuseki(_line):
        return [('解す', '動詞:自立', 'カイス', 0, 2, True),
                ('咳', '名詞:一般', 'セキ', 2, 3, True)]

    check('解す咳 → 解析（どちらも実績0・す を消すと優勢）',
          C._run_reading_merge_fixes('解す咳', tok_kaisuseki, st),
          [(0, 3, '解析')])

    # 構成する語に実績があるなら入らない（誤判定 の型）
    st2 = _St()
    st2.data = {'かいせき': (('解析', 618),), 'せき': (('咳', 3),)}
    check('片方に実績があれば触らない',
          C._run_reading_merge_fixes('解す咳', tok_kaisuseki, st2), [])
    return all_ok


def test_gloss_guards_48ln():
    """
    **読みの注記の規則と、誤検知9件の受け止め**（項目48-LN・
    2026-08-30・うにさんの規則「直前に漢字があり、括弧に入った
    平仮名は、平仮名として書きたい意図がある。英語読みも同様」）。
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

    print('--- 項目48-LN（読みの注記・誤検知の門） ---')

    line = '接頭辞（せっとうじ、prefix）'
    check('漢字＋括弧の中の平仮名は読みの注記',
          C.is_reading_gloss(line, line.index('せ')), True)
    check('英字＋括弧も同様（KyTea（キューティー））',
          C.is_reading_gloss('KyTea（キューティー）', 6), True)
    check('括弧の外は注記ではない',
          C.is_reading_gloss('接頭辞のせっとうじ', 4), False)
    check('前が平仮名の括弧は注記ではない',
          C.is_reading_gloss('これ（せつめい）', 3), False)

    check('させていく は機能語で説明が付く（させて）',
          C._is_functional_strict('させていく'), True)
    check('おかれている も説明が付く（頭の お）',
          C._is_functional_strict('おかれている'), True)

    src = open('corrector.py', encoding='utf-8').read()
    check('手を掛けた2語の組の門がある（断片の例外つき）',
          "_why['手を掛けた2語の組'] += 1" in src
          and 'and not _chunk_has_unknown:' in src, True)
    check('頭が前の語にぶら下がる塊は開かない',
          'ぶら下がる品詞。開かない' in src, True)
    check('中黒の列挙の門がある',
          '列挙の中黒' in src, True)
    return all_ok


def test_fp_guards_48lp():
    """
    **画面の誤検知4件の受け止め**（項目48-LP・2026-08-30）。

        変換中 → 変換かな          動作の語＋中/時 は組み上がり
        さんこうになる → …にな。   終助詞の直前が格助詞なら言い切りでない
        すくろーるご → スクロール   外来語は語の尻も食わない
        がいしょつ → がいショーツ   小書きで始まる窓は嘘の境目
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

    print('--- 項目48-LP（画面の誤検知4件の判定直し） ---')

    # (a) 動作の語（サ変）＋中/時 は、できあがっている塊
    def tok_a(text):
        pos = {'変換': '名詞:サ変接続', '囚虜': '名詞:一般'}.get(
            text, '名詞:一般')
        return [(text, pos, '', 0, len(text), True)]
    check('変換中 は組み上がり（サ変＋中）',
          C._chunk_is_intact('変換中', tok_a), True)
    check('囚虜時 は組み上がりではない（頭が一般名詞）',
          C._chunk_is_intact('囚虜時', tok_a), False)
    check('変換 だけでは対象外（接尾が無い）',
          C._chunk_is_intact('変換', tok_a), False)

    # (d) 小書きで始まる窓は、手前のトークンごと含める
    def tok_d(run):
        if run == 'がいしょつする':
            return [('がいし', '動詞:自立', 'ガイシ', 0, 3, True),
                    ('ょつする', '名詞:固有名詞:組織', '', 3, 7, False)]
        return [(run, '名詞:一般', '', 0, len(run), False)]
    check('がいし|ょつする の窓は塊全体（がいしょつする）',
          C.token_windows('がいしょつする', tok_d), [(0, 7)])

    # (b)(c) は janome・語彙が要るので、判定の文言で見張る
    src = open('corrector.py', encoding='utf-8').read()
    check('言い切りの門（終助詞の直前は助動詞か終助詞）がある',
          '終助詞の直前は、助動詞か終助詞であること' in src, True)
    src_lw = open('loanword.py', encoding='utf-8').read()
    check('外来語の尻食いの門がある（loanword）',
          '語の尻も食わない' in src_lw, True)
    check('外来語の並記の口にも残りの検査がある（48-DL と同じ物差し）',
          src.count('語の途中に見える') >= 3, True)

    # (c) の精密形: 消してよい尻は語の頭に立てない字（ん・ー・小書き）
    import loanword as LW
    from vocabulary import VocabularyStore
    _st = VocabularyStore()
    for _ in range(30):
        _st.add('すくろーる', 'スクロール', 'IT・PC操作')
        _st.add('たぶ', 'タブ', 'IT・PC操作')
    check('すくろーるご → スクロール にしない（ご は次の語の頭）',
          LW.katakana_for_hiragana_typo('すくろーるご', _st, min_length=4),
          None)
    check('たぶい → タブ にしない（い は 移動 の頭）',
          LW.katakana_for_hiragana_typo('たぶい', _st, min_length=3), None)
    check('すくろーるん → スクロール は今までどおり（ん は頭に立てない）',
          LW.katakana_for_hiragana_typo('すくろーるん', _st, min_length=4),
          'スクロール')

    # --- 48-LS: 読みの並記（逆向き）と並記からの脱字の変種 ---
    def tok_g(text):
        if text == '食事券':
            return [('食事', '名詞:サ変接続', 'ショクジ', 0, 2, True),
                    ('券', '名詞:接尾:一般', 'ケン', 2, 3, True)]
        return [(text, '名詞:一般', '', 0, len(text), False)]
    check('かな＋括弧の中にその表記＝読みの並記（触らない）',
          C._reading_spelled_in_bracket('しょくじけん（食事券）', 0, 6,
                                        tok_g), True)
    check('読みが一致しない括弧は対象外',
          C._reading_spelled_in_bracket('せっていを（食事券）', 0, 5,
                                        tok_g), False)
    check('括弧が無ければ対象外',
          C._reading_spelled_in_bracket('しょくじけん', 0, 6, tok_g),
          False)
    check('読みの変種は同じ行の並びからだけ（かなち→かなうち）',
          C._attest_insert_variants('かなち', ' かなうちでのほせい '),
          ['かなうち'])
    check('端の挿入は変種にしない（のかなち）',
          C._attest_insert_variants('かなち', 'のかなち'), [])
    from kanji_guess import find_mixed_kana_runs as _fmk
    check('ひらがな頭＋漢字1字の塊が列挙に乗る（かな地）',
          (0, 3, 'かな地') in _fmk('かな地での補正'), True)
    return all_ok


def test_compose_48lu():
    """
    **見本なしの組み直し**（項目48-LU・2026-08-30 19回目。うにさんの
    指定「正しい文の見本がなくても異様な文字列を正しく漢字に補正する
    必要があります」。18回目の 48-LT〔行の後ろの並記への変換〕は
    開発用の形に寄りかかっていたので撤去した）。
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

    print('--- 項目48-LU（見本なしの組み直し） ---')

    class _St(object):
        data = {}

        def lookup(self, r):
            return [dict(surface=s2, count=c)
                    for s2, c in self.data.get(r, ())]

    st = _St()
    st.data = {'かな': (('かな', 1219),), 'うち': (('打ち', 1099),),
               'ほせい': (('補正', 1520),)}

    # 文法で説明の付く連なりには掛けない（①異様か判定する、が先）
    check('説明の付く連なりは組まない（たんごのつながり）',
          C._lu_compose_odd_run('たんごのつながり', st), None)
    check('説明の付く連なりは組まない（せっけいのみして）',
          C._lu_compose_odd_run('せっけいのみして', st), None)

    # janome の無い環境では、自然さの門が開かないので組まない（安全側）
    check('自然さの測れない環境では組まない',
          C._lu_compose_odd_run('かなうちでのほせい', st,
                                tokenize_fn=None), None)

    src = open('corrector.py', encoding='utf-8').read()
    check('手は先頭の字に掛けない（頭の1字は打った字）',
          '手は先頭の字に掛けない' in src, True)
    check('拮抗は複合語の対の共起でも裁く（A0・かな×打ち）',
          '拮抗を複合語の対の共起' in src, True)
    check('数字の直後の連なりには掛けない（1つだけ の守り）',
          '数字の直後の連なりには掛けない' in src, True)
    check('実績0の姓＋用言は紫（48-LV・柚須借りた）',
          '実績0の姓＋用言' in src, True)
    check('゛のずれも1手（つつぎ→つづき・遅れた濁点の族）',
          '゛が1つ隣にずれた形も1手' in src, True)
    check('同じ変種の組は漢字の多い側（続きをはなす／続きを話す）',
          '漢字の多い側' in src, True)

    # 48-LW: 略語の隣のキー（純粋関数なので janome なしで測れる）
    import loanword as LW
    from vocabulary import VocabularyStore as _VS
    _st2 = _VS()
    check('YRL → URL（Y と U は QWERTY の隣・種の名簿）',
          LW.find_miskeyed_acronym('YRLは', _st2), [(0, 3, 'URL')])
    check('知っている略語は触らない（IME）',
          LW.find_miskeyed_acronym('IMEは', _st2), [])
    check('半角英数の続く並びは略語と見ない（CN1）',
          LW.find_miskeyed_acronym('ABC1', _st2), [])
    check('組の頭は内容語（文は機能語では始まらない）',
          '組の頭は内容語' in src, True)
    check('拮抗は 周りの語 → 語数 の順で裁く',
          '拮抗を周りの語' in src and '拮抗を語数で裁いた' in src, True)
    check('48-LT（行の後ろの並記への変換）は撤去済み',
          '_spelled_target_after' not in src
          and '_lt_in_quotes' not in src, True)
    return all_ok

def test_fp_guards_48lj():
    """
    **うにさんの「補正の誤検知」2件の受け止め**（項目48-LJ/LK・
    2026-08-30）。文節最後 → 隣接最後（別読み経由の書き換え）と
    補正できてたものが → 補正できたものが（てた を知らない）。
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
    import oddness

    print('--- 項目48-LJ/LK（誤検知2件の判定直し） ---')

    # (LK) てた＝ていた の話し言葉。機能語の並びとして説明が付く
    check('できてたものが は機能語で説明が付く',
          C._is_functional_strict('できてたものが'), True)
    check('できてたものが を巻き込みで直さない',
          C._fix_functional_run('できてたものが', after_kanji=True), None)
    check('いってたよ も説明が付く',
          C._is_functional_strict('いってたよ'), True)

    # (LJ) 位置・順序の2字名詞は何の後ろにも付く（文節最後）
    check('文節＋最後 はくっつく（位置・順序の名簿）',
          oddness.can_join('文節', '名詞:一般', '最後', '名詞:一般'), True)
    check('画面＋中央 もくっつく',
          oddness.can_join('画面', '名詞:一般', '中央', '名詞:一般'), True)
    check('野外＋文章 は今までどおり（的の側は残る）',
          oddness.can_join('野外', '名詞:一般', '文章', '名詞:一般'), False)

    # (LJ) 設計27 の門（48-LN でさらに強い形に置き換わった）:
    # 作った読みに手を掛けない・手を掛けた2語の組は採らない
    src = open('corrector.py', encoding='utf-8').read()
    check('手を掛けた2語の組の門がある（項目48-LJ→LN）',
          "_why['手を掛けた2語の組'] += 1" in src, True)
    return all_ok


def test_sei_pair_48le():
    """
    **姓＋姓の連なり（どちらも語彙の実績0）は異様**（項目48-LE・
    2026-08-29）。柚須苅田（ゆすかりた の IME 変換）に紫。
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

    print('--- 項目48-LE（姓＋姓・実績0 の紫） ---')

    class _St(object):
        data = {}

        def reading_of(self, s):
            return None

        def lookup(self, r):
            return [dict(surface=s, count=c)
                    for s, c in self.data.get(r, ())]

    def tok_yusu(_line):
        return [('柚須', '名詞:固有名詞:人名:姓', 'ユス', 0, 2, True),
                ('苅田', '名詞:固有名詞:人名:姓', 'カリタ', 2, 4, True)]

    del C._ODD_PENDING[:]
    check('柚須苅田 に紫（どちらも実績0）',
          C._odd_spans_for_line('柚須苅田', tok_yusu, (), None, _St(),
                                None),
          [(0, 4)])

    # 本人がよく使う姓なら立てない
    st2 = _St()
    st2.data = {'ゆす': (('柚須', 3),)}
    check('語彙に実績のある姓は立てない',
          C._odd_spans_for_line('柚須苅田', tok_yusu, (), None, st2,
                                None), [])

    # 姓＋名（48-JL の守りの形）はこの規則の対象外
    def tok_takahashi(_line):
        return [('高橋', '名詞:固有名詞:人名:姓', 'タカハシ', 0, 2, True),
                ('祐太', '名詞:固有名詞:人名:名', 'ユウタ', 2, 4, True)]

    check('姓＋名は見ない',
          C._odd_spans_for_line('高橋祐太', tok_takahashi, (), None,
                                _St(), None), [])
    return all_ok


def test_mixed_run_reopen_48la():
    """
    **混ざった連なり（かな＋漢字＋カタカナ）を連なりごと開く**
    （項目48-LA・2026-08-29）。にゅうりょ組ス → 入力ミス。
    janome の無い環境では開く道具が働かないので、**入口の形**
    （壊れず・意見なしで戻る）だけ見張る。実際の的は写しの
    probe_unresolved で。
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
    from tests_mock_common import build_store
    store = build_store()
    tok = C.make_tokenizer(store)

    print('--- 項目48-LA（混ざった連なりを開く・入口の形） ---')
    check('tokenize_fn が無ければ意見なし',
          C._reopen_mixed_run_fixes('にゅうりょ組ス', store, None), [])
    got = C._reopen_mixed_run_fixes('漢字塊の話', store, tok)
    check('印の立たない連なりは触らない（漢字塊）', got, [])
    got2 = C._reopen_mixed_run_fixes('これは長い正しい文です。', store, tok)
    check('普通の文は触らない', got2, [])
    return all_ok
