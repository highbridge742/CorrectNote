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

