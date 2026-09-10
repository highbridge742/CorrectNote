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
from vocabulary import VocabularyStore, find_known_readings_flex, dup_repair_enabled
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
              LW.fix_katakana_word(typed, fresh),
              None if typed == 'ププラネタリウム' and not dup_repair_enabled()
              else 'プラネタリウム')
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
    check('英字の重複も設定に従う（PPlanetarium）',
          LW.fix_english_word('PPlanetarium', fresh),
          'Planetarium' if dup_repair_enabled() else None)
    # **打ち間違い／綴り間違いとして説明が付くか**（項目48-BJ）
    check('キーが隣なら置換を通す（Plaqnetarium の q）',
          LW.typo_explains_seed_english('plaqnetarium', 'planetarium'), True)
    check('母音どうしの取り違えは通す（seperate）',
          LW.typo_explains_seed_english('seperate', 'separate'), True)
    check('離れたキーの置換は通さない（iconic→ironic）',
          LW.typo_explains_seed_english('iconic', 'ironic'), False)
    check('離れたキーの余分な1文字は通さない（pchanged→changed）',
          LW.typo_explains_seed_english('pchanged', 'changed'), False)
    check('英字の重複の説明も設定に従う（Pllanetarium）',
          LW.typo_explains_seed_english('pllanetarium', 'planetarium'), dup_repair_enabled())
    # **触らない語の一覧は、直し先より広い**（項目48-BK）
    check('触らない語は直し先より多い',
          len(LW._english_seed_all()) > len(LW._english_seed()), True)
    # 大文字小文字は書いた人に合わせる
    check('大文字を保つ',
          LW.fix_english_word('Plaqnetarium', fresh), 'Planetarium')
    # 同じ字の2連続は畳む（うにさんの指定・項目48-AX）
    for typed in ('Planetariumm', 'PPlanetarium', 'Plannetarium'):
        check(f'2連続を畳む（{typed}）',
              LW.fix_english_word(typed, fresh), 'Planetarium' if dup_repair_enabled() else None)

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
          LW.typo_explains_seed_word('ぷぷらねたりうむ', 'ぷらねたりうむ'),
          dup_repair_enabled())
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
        ('ププラネタリウム', 'プラネタリウム' if dup_repair_enabled() else None),  # 48-VL: 重複は既定オフ
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
              None if typed == 'Pplanetarium' and not dup_repair_enabled() else 'Planetarium')
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
          fix('P:lanetariumm'), 'Planetarium' if dup_repair_enabled() else None)
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

    # --- ★★ **48-QG' が保留した判断を、測って決めた**（項目48-VG・
    #     2026-09-08）。
    #
    #     48-QG'（2026-09-05）の書き置き:「`_K2K_MIN_USAGE = 10` は
    #     `count` が {1,2} しか取らなくなったので絶対に越えられない。
    #     **`solid` へ置き換えるかは測ってから決める（巡3）**」。
    #
    #     ★ 眠っていたあいだ、**呼び手2本が丸ごと死んでいた**——
    #     `_shift_lost_kanji`（48-FU・うにさんが頼んだ
    #     `きようちよう ⇒ 強調`）と、かな→漢字（48-EA）。
    #     `きようちようしたい` も `しゆうせいします` も素通りしていた。
    #
    #     測った（一式 f38 → f39・初期と育ちの両方）:
    #       readcheck  直り・化けとも **1文字も動かない**（控えがバイト同一）
    #       紫の印     **動かない**（控えがバイト同一）
    #       実機メモ   **+1 直り**——`たんごの繋がり → 単語の繋がり`
    #                  （**48-EA の説明に書いてある見本そのもの**）
    #       fpcheck / seedcheck / 画面32 / 守る18 / 実機メモ9 /
    #       readcheck10 / 語彙4,000語  **すべて差0**
    #
    #     「習慣的か」を写せる数字はもう無い（`world` は辞書から
    #     取り込んだ語にしか付かず、本人が覚えた語は 0＝別の軸）。
    #     48-QG' の決まり「**移せないなら二値にする**」に従って
    #     `solid`（2回以上書いた）にした。
    check('立っている漢字だけの読みは返る（項目48-VG）',
          pick('たんご', store), '単語')
    # ★ **立っている漢字が2つ以上なら返さない**（回数が在った頃は
    #   「多いほう」を採れたが、二値では順位が付かない。決められない
    #   ものは触らない・設計38〜40）。
    store.add('こうえん', '講演', 'その他')
    store.add('こうえん', '講演', 'その他')
    store.add('こうえん', '公園', 'その他')
    store.add('こうえん', '公園', 'その他')
    check('立っている漢字が2つなら返らない（項目48-VG）',
          pick('こうえん', store), None)

    # --- 回数に依らない門は、そのまま生きている ---
    check('かなでも書く語は返らない（つながり）',
          pick('つながり', store), None)
    check('漢字の表記が無い語は返らない（かよわい）',
          pick('かよわい', store), None)
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
    # **項目48-NA で改めた**（2026-08-31）。名詞どうしの複合は
    # 日本語では既定で作れるので、**構造では `野外文章` と
    # `初期語彙` を割れない**。頻度で裁いていた最後の門を外した
    # ——実機メモの43個の印のうち **37個が誤検知**だった。
    check('野外＋文章 も、名詞どうしなので作れる（48-NA）',
          oddness.can_join('野外', '名詞:一般', '文章', '名詞:一般'), True)

    check('塊まるごとが表の語（同音異義語）なら中の対は見ない',
          oddness.is_odd_run('同音異義語', tok_of(
              [('同音', '名詞:一般'), ('異義', '名詞:一般'),
               ('語', '名詞:接尾')])), [])
    # 48-NA で改めた——`同音異義` は**正しい日本語**（誤検知だった）
    check('同音異義 は名詞どうしなので立たない（48-NA）',
          oddness.is_odd_run('同音異義', tok_of(
              [('同音', '名詞:一般'), ('異義', '名詞:一般')])), [])
    check('送り仮名まで含めて語（見做す）なら立たない',
          oddness.is_odd_run('見做して', tok_of(
              [('見', '名詞:一般'), ('做', '名詞:一般'),
               ('し', '動詞:自立'), ('て', '助詞:接続助詞')])), [])
    check('差釣れません は今までどおり立つ',
          oddness.is_odd_run('差釣れません', tok_of(
              [('差', '名詞:一般'), ('釣れ', '動詞:自立'),
               ('ませ', '助動詞'), ('ん', '助動詞')])), [('差', '釣れ')])
    check('野外文章 も立たない（48-NA）',
          oddness.is_odd_run('野外文章', tok_of(
              [('野外', '名詞:一般'), ('文章', '名詞:一般')])), [])

    # **紫で見せる位置**（項目48-IR）。解析の始まり・終わりを使う。
    # 位置つきで返せること自体は、**1字がらみの並び**で確かめる
    # （48-NA で 野外文章 は印が立たなくなった）
    check('位置つきで返せる',
          oddness.odd_spans('差釣れます', tok_of(
              [('差', '名詞:一般'), ('釣れ', '動詞:自立'),
               ('ます', '助動詞')])), [(0, 3)])

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
    from vocabulary import VocabularyStore, find_known_readings_flex, dup_repair_enabled
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
    # **項目48-MX で改めた**（2026-08-31）。ここは元々
    # 「ローマ字では ょ→ゅ（o→u）は隣のキーでない」で落としていたが、
    # **同じ誤りが入力の設定で通ったり通らなかったりしていた**
    # （かな入力では ゅ(0,7) と ょ(0,8) が隣のキーなので通っていた）。
    # 拗音の小書き3文字は、ローマ字でも ya/yu/yo という**同じ枠の
    # 母音1字違い**なので、どちらでも1回の誤りで説明が付く。
    check('拗音の小書きどうしは、ローマ字でもかなと同じに直る（48-MX）',
          run('これからな学外しょつする', 5, 12, method='romaji'),
          (4, '長く外出する', 'その他'))
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
    # 48-LB（2026-08-29）→ **項目48-NG（2026-09-01）で床を 10 → 2**。
    # くぐれるのは**丸ごと1語**だけ（48-JG の化け 空白くい・高橋よう は
    # どちらも2語の組なのでくぐれない——上の2つの「漢字1字の差」の
    # 検査が守りの本体）。**10 という数はうにさんの育ちの 平仮名(16) に
    # 合わせただけ**で、初期状態の 平仮名(2) が通れなかった。
    check('くぐり抜けは 丸ごと1語 だけ（項目48-LB → 48-NG）',
          "and not (surf in getattr(_surfaces, 'whole', ())" in src
          and 'and cnt >= _WHOLE_KANJI_FLOOR):' in src, True)

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
    from vocabulary import VocabularyStore, find_known_readings_flex, dup_repair_enabled

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
    （初期語彙の 下降 は立っていない。**`count>=2` の門は、うにさんの
    2026-09-05 の指定で `solid` の意味になった**——回数の記録そのものを
    廃したので、この門は「この人の語として立っているか」を聞く形に
    なっている。等価であることは構造で示してある〔項目48-QG〕）。
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
    表が証拠——`count>=2` の門は、うにさんの 2026-09-05 の指定で
    `solid`〔立っているか〕の意味になった。項目48-QG）。
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
    from vocabulary import VocabularyStore, find_known_readings_flex, dup_repair_enabled

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
    # **項目48-NA で改めた**（2026-08-31）。名詞どうしの複合は
    # 構造では割れない（意味だけが違う）ので、この2つは印が
    # 立たなくなった。**守りは1字がらみの並びで確かめる**。
    check('差＋釣れ は今までどおり異様（1字がらみ）',
          O.can_join('差', '名詞:一般', '釣れ', '動詞:自立'), False)
    t3 = toks(('差', '名詞:一般', 'さ'),
              ('釣れ', '動詞:自立', 'つれ'))
    check('差釣れ の印は残る',
          O.is_odd_run('差釣れ', lambda _l: t3), [('差', '釣れ')])
    check('野外＋文章 は名詞どうしなので作れる（48-NA）',
          O.can_join('野外', '名詞:一般', '文章', '名詞:一般'), True)
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

    # ------------------------------------------------------------
    # 48-QY **紫下げの門は、描画の直前の1本**（`visible_odd_spans`）
    # ------------------------------------------------------------
    # エンジン（`_odd_spans_for_line`）は**素の紫**を返し、
    # 落とすのは画面へ塗る直前だけ。こうすると「紫を1つ下げる」ために
    # 解析をやり直す必要が無くなる（うにさんの報告——他の行の補正の色が
    # 一度消えて再度つく）。
    d3 = DecisionStore()
    d3.protect('奥悠久子帝')
    check('決めた範囲と重なる紫は落ちる',
          C.visible_odd_spans('奥悠久子帝です', [(0, 5)], d3), [])
    check('**印のほうが狭くても外れる**（重なりで外す）',
          C.visible_odd_spans('奥悠久子帝です', [(2, 5)], d3), [])
    check('重ならない紫は残る',
          C.visible_odd_spans('奥悠久子帝です', [(5, 7)], d3), [(5, 7)])
    check('決めていなければ、そのまま返す',
          C.visible_odd_spans('奥悠久子帝です', [(0, 5)], DecisionStore()),
          [(0, 5)])
    check('判断置き場が無くても落ちない',
          C.visible_odd_spans('奥悠久子帝です', [(0, 5)], None), [(0, 5)])
    check('紫が無い行では何もしない',
          C.visible_odd_spans('奥悠久子帝です', [], d3), [])

    # ★★ **エンジン側は もう落とさない**（門を2か所に増やさない・48-GN）
    check('`_odd_spans_for_line` は `decisions` を受け取らない',
          'decisions' in C._odd_spans_for_line.__code__.co_varnames, False)

    # ★★ **塗り口に門が掛かっていること**（学び22——ここが唯一の口）
    import io as _io
    _src = _io.open('app.py', encoding='utf-8').read()
    check('app の塗り口が `visible_odd_spans` を通している',
          'corrector.visible_odd_spans(' in _src, True)
    check('紫下げは `_reanalyze_all` を呼ばない（answer_changed=False）',
          'answer_changed=False' in _src, True)
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
    # ★★ **優勢は「回数の 20倍」から「書かれている読みが語彙に在るか」へ**
    # （項目48-QG'・2026-09-05）。回数の記録をやめたので 20倍は二度と
    # 越えられない。残るのは前半——もとの `base_count == 0`＝
    # **その読みの語が語彙に1つも無いとき**だけ通す形。
    #
    # ★ `solid` で聞く形は**測って外した**。育ちには count 1 の語が
    # 13,866件あり、solid で聞くとそれが全部「立っていない」側へ落ちて
    # **門が旧より広く開く**——`除雪用 → 常設用`・`助演者 → 上演者` など
    # **正しく書いた語を 21件壊した**（実測）。
    st = _St({'しゅうりょ': [],
              'しゅうりょう': [{'surface': '終了', 'count': 2},
                               {'surface': '修了', 'count': 1}]})
    check('囚虜時 → 終了時（しゅうりょ の語が無い・終了 は立っている）',
          C._run_reading_merge_fixes('囚虜時', tok_shuryo, st),
          [(0, 3, '終了時')])

    # **書かれている読みの語が語彙に在るなら触らない**
    # （count 1 でも触らない——旧の `base_count >= 1` と同じ）
    st2 = _St({'しゅうりょ': [{'surface': '囚虜', 'count': 1}],
               'しゅうりょう': [{'surface': '終了', 'count': 2}]})
    check('書かれている読みの語が在るなら触らない（count 1 でも）',
          C._run_reading_merge_fixes('囚虜時', tok_shuryo, st2), [])

    # **直し先が立っていなければ通さない**
    st2b = _St({'しゅうりょ': [],
                'しゅうりょう': [{'surface': '終了', 'count': 1}]})
    check('直し先が立っていなければ触らない',
          C._run_reading_merge_fixes('囚虜時', tok_shuryo, st2b), [])

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

    # ------------------------------------------------------------------
    # **項目48-OP: 長音「う」の位置ずれ**（2026-09-03）。
    # うにさんの一覧2行目 `にゆりょうくみす ⇒ にゅうりょくみす`（入力ミス）。
    # う を**足す**（手(ii)）のでは届かない——にゅりょうくみす に う を
    # 足すと にゅう＋りょう＋く＋みす で敷き詰まってしまい、そこから
    # 先の変換が立たない。打ったのは **う の場所が1拍ずれた**形なので、
    # **拗音の小書きの直後どうしで移す**。
    print('--- 項目48-OP（長音 う の位置ずれ） ---')

    check('生の変種: にゅ|りょう → にゅう|りょ',
          C._kv_move_u_variants('にゅりょうくみす'),
          {'にゅうりょくみす': 2})
    check('生の変種: 後ろへも動かす（両向き）',
          C._kv_move_u_variants('しゅうりょじ'), {'しゅりょうじ': 4})
    check('拗音が1つなら手は無い',
          C._kv_move_u_variants('しゅうかん'), {})
    check('動かす う は拗音の直後に在るものだけ',
          C._kv_move_u_variants('きゃくしゃ'), {})

    check('にゆりょうくみす → 入力ミス（う の位置ずれ・48-OP）',
          C._misplaced_large_kana_fixes('にゆりょうくみす', _St2(), di4),
          [(0, 8, '入力ミス', 'かな入力')])

    # **元が敷き詰まっているなら、崩して並べ替えない**（門）。
    # にゅうりょくみす は世の中の読みで敷き詰まるので、位置ずれの
    # 変種（にゅりょうくみす）は列挙すらされない
    check('敷き詰まっている読みは位置ずれを試さない',
          C._misplaced_large_kana_fixes('にゅうりょくみす', _St2(), di4),
          [(0, 8, '入力ミス', 'かな入力')])

    # **手(ii)（う挿入）が先**——`しゅうりょじ`（48-MG）は両方の手が
    # 立つ（(ii) しゅうりょうじ → 終了時 ／ (iii) しゅりょうじ）。
    # 順を逆にすると 48-MG の答えを位置ずれが横取りする
    _csrc = open('corrector.py', encoding='utf-8').read()
    check('順は 手(ii) → 手(iii)（48-MG を横取りしない）',
          _csrc.index('# 手(ii): う挿入')
          < _csrc.index('# 手(iii): う の位置ずれ（項目48-OP）'), True)
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

    # (4) 48-VZ: 候補が複数でも、語の裏付けから最上位を選ぶ。
    st4 = _St()
    st4.data = {'さいだい': (('最大', 40),), 'さいてい': (('最低', 30),)}
    del C._ODD_PENDING[:]
    check('候補が複数でも最大化を選ぶ',
          C._kana_run_hand_fixes('さいたいか', st4, _di), [(0, 5, '最大化', 'かな入力')])
    check('補正先があるので紫だけにしない', list(C._ODD_PENDING), [])

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
    # ★ 48-UI で入口に「同梱の表が1語なら、できあがっている」が入った。
    #    `変換` は表に在るので **(A) で True**——(0) の接尾とは別の道
    #    （2字の塊は len >= 3 の (0) には届かない）。
    check('変換 は表に在るので入口で組み上がり（48-UI・(A)）',
          C._chunk_is_intact('変換', tok_a), True)
    check('表に無い塊は今までどおり組み上がりではない（素帰任・乳リュク）',
          (C._chunk_is_intact('素帰任', tok_a),
           C._chunk_is_intact('乳リュク', tok_a)), (False, False))

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

    # --- 7巡目（2026-09-06・項目48-RZ〜48-SC）---
    print('--- 項目48-RZ〜48-SC（格助詞の連続・人名＋を・濁点の位置ずれ・④の選び方） ---')
    import pos_grammar as _P7
    check('48-RZ 格助詞の連続は説明が付かない（これをにする）',
          _P7.explain_kana_run('これをにする'), False)
    check('48-RZ 行頭の裸の助詞は立てない（もみとにもどります）',
          _P7.explain_kana_run('もみとにもどります', bare_head=True), False)
    check('48-RZ 直した形は説明が付く（もとにもどります）',
          _P7.explain_kana_run('もとにもどります', bare_head=True), True)
    check('48-RZ へと は置ける（えきへとむかう）',
          _P7.explain_kana_run('えきへとむかう'), True)
    check('48-RZ にも・とは は置ける（あなたにはむり）',
          _P7.explain_kana_run('あなたにはむり'), True)
    check('48-RZ 行頭でなければ助詞で始まれる（をよむ・直前が漢字）',
          _P7.explain_kana_run('をよむ', after_kanji=True, bare_head=True), True)
    check('48-RZ とにかく は語（行頭でも）',
          _P7.explain_kana_run('とにかく', bare_head=True), True)
    check('48-SB 濁点の位置ずれ（つつぎ → つづき）',
          C._moved_dakuten_variants('つつぎ'), ['つづき'])
    check('48-SB 頭へは移さない（ぎつ）',
          C._moved_dakuten_variants('ぎつ'), [])
    check('48-SB 濁音の無い並びは何も出ない（かたい）',
          C._moved_dakuten_variants('かたい'), [])
    check('48-SB 半濁点も同じ（はぱ → ぱは は頭が変わるので出ない）',
          C._moved_dakuten_variants('はぱ'), [])
    check("48-SB' 位置ずれは設計27の手に門付きで（_typo_repairs には置かない）",
          "_add(r, '濁点の位置ずれ', 1.0)" in src
          and 'つづき' not in C._typo_repairs('つつぎ'), True)
    # --- 9巡目（48-SM〜48-SO・2026-09-06） ---
    _osrc9 = open('oddness.py', encoding='utf-8').read()
    import oddness as _O9
    check('48-SN 形容詞の語幹1字＋名詞はくっつく（強炭酸）',
          _O9.can_join('強', '形容詞:自立', '炭酸', '名詞:一般'), True)
    check('48-SN 名簿の1字（厚）も同じ（解析が地域と言っても）',
          _O9.can_join('厚', '名詞:固有名詞:地域:一般', '爪', '名詞:一般'), True)
    check('48-SN 地名＋名詞はくっつく（九州方言）',
          _O9.can_join('九州', '名詞:固有名詞:地域:一般', '方言', '名詞:一般'), True)
    check('48-SN 名詞＋地名もくっつく（現代九州）',
          _O9.can_join('現代', '名詞:一般', '九州', '名詞:固有名詞:地域:一般'), True)
    check('48-SN 人名＋名詞は今までどおり（固有名詞は _plain_noun から外したまま）',
          _O9.can_join('都築', '名詞:固有名詞:人名:姓', '方言', '名詞:一般'), False)
    check('48-SN 何にでも付く接尾（付き・入り・済み・用…）',
          all(x in _O9._SUFFIX_TAIL_FREE for x in ('付き', '入り', '済み', '用')), True)
    check('48-SN 何にでも付く尾は can_join でも通す（素＋同士）',
          _O9.can_join('素', '名詞:一般', '同士', '名詞:一般'), True)
    check('48-SM is_odd_run に skip_join の読みがある',
          'skip_join=False' in _osrc9 and _osrc9.count('if skip_join:') == 2, True)
    check('48-SM 見たことのない並びだけの塊は、1語（＋接辞）で漢字を減らさないものに限る（4つの出口）',
          'def _sm_single_unit(' in src and src.count('_sm_ok(') == 5, True)
    check('48-SO 敬語の接頭辞（お・ご）の隙間は落とさない（にご → に も。機能語の並びには足さない）',
          "or (_b and _a.replace(_b, '', 1) in ('お', 'ご'))):" in src
          and "{'っ', 'よい', 'いい', 'お'}" in src, True)
    check("48-SM' 置き換えは1語か、内容語が元より減るもの（_sm_content_count）",
          'def _sm_content_count(' in src and 'return _n1 <= 1 or _n1 < _sm_n0' in src, True)
    import pos_grammar as _PG9
    check('48-SQ 語の表を使わない読み: しやすさ（し＋やす＋さ）は文法だけで説明が付く',
          _PG9.explain_kana_run('しやすさ', no_words=True), True)
    check('48-SQ 語の表を使わない読み: たかちゃん は 名前＋敬称',
          _PG9.explain_kana_run('たかちゃん', no_words=True), True)
    check('48-SQ 語の表を使わない読み: きゅうずいを（語＋語＋を）は付かない',
          _PG9.explain_kana_run('きゅうずいを', no_words=True), False)
    check('48-SQ/48-TH 2段: 機能語だけで説明が付く連続は触らない／用言の活用で説明が付く連続は芯が「明らかに自然になる直し」だけ',
          "if (source != 'token_windows' and len(run) >= 3" in src
          and 'and not _is_all_functional(run)):' in src
          and '_sq_pure = _pg_sq.explain_kana_run(run, no_words=True,' in src
          and 'readable_hint=(window_readable or _sq_readable),' in src, True)
    check("48-TH' 48-IS の判定は用言の活用＋機能語の説明を受け入れる（やめたら・ひどくて は読める）",
          C._kana_run_explained('やめたら') and C._kana_run_explained('ひどくて')
          and not C._kana_run_explained('ぬぷぐさぞ'), True)
    check('48-TH stems_only: やめたら・ひどくて は活用で説明が付く（no_words では付かない）',
          _PG9.explain_kana_run('やめたら', stems_only=True)
          and _PG9.explain_kana_run('ひどくて', stems_only=True)
          and not _PG9.explain_kana_run('やめたら', no_words=True), True)
    check("48-TH''' stems_only は用言1つ＋語尾・機能語だけ（かぎかえを・したれやなぎ は付かない／やめたら・ありえない・たべていく は付く）",
          not _PG9.explain_kana_run('かぎかえを', stems_only=True, before_kanji=False)
          and not _PG9.explain_kana_run('したれやなぎ', stems_only=True, before_kanji=False)
          and _PG9.explain_kana_run('やめたら', stems_only=True)
          and _PG9.explain_kana_run('ありえない', stems_only=True)
          and _PG9.explain_kana_run('たべていく', stems_only=True)
          and _PG9.explain_kana_run('あまりにもひどくて', stems_only=True), True)
    check("48-TH'''' stems_only は終止の直後に用言を始めない（おくゆく・ほうれんぞう・てたとおす・がいししょう は付かない／やめたらいく・やめるし・すねると は付く）",
          not _PG9.explain_kana_run('おくゆく', stems_only=True, before_kanji=False)
          and not _PG9.explain_kana_run('ほうれんぞうを', stems_only=True, before_kanji=False)
          and not _PG9.explain_kana_run('てたとおすを', stems_only=True, before_kanji=False)
          and not _PG9.explain_kana_run('がいししょうを', stems_only=True, before_kanji=False)
          and not _PG9.explain_kana_run('すいあけるを', stems_only=True, before_kanji=False)
          and _PG9.explain_kana_run('みてた', stems_only=True, after_kanji=True)
          and _PG9.explain_kana_run('やめたらいく', stems_only=True)
          and _PG9.explain_kana_run('やめるし', stems_only=True)
          and _PG9.explain_kana_run('すねると', stems_only=True)
          and _PG9.explain_kana_run('たべていく', stems_only=True), True)
    check('48-TJ 末尾の お/ご は、直後が漢字でないと分かれば接頭辞と読まない（よれご）',
          _PG9.explain_kana_run('よれご', stems_only=True) is True
          and _PG9.explain_kana_run('よれご', stems_only=True,
                                    before_kanji=True) is True
          and _PG9.explain_kana_run('よれご', stems_only=True,
                                    before_kanji=False) is False
          and _PG9.explain_kana_run('そのご', no_words=True,
                                    before_kanji=True) is True, True)
    check('48-TJ 48-IS の判定と芯にも before_kanji が通る',
          C._kana_run_explained('よれご', before_kanji=False) is False
          and 'before_kanji=before_kanji,' in src
          and '_bk_core = before_kanji if c_e >= len(window) else False' in src
          and 'and is_kanji(line[max(b, run_end)])),' in src, True)
    vsrc48tr = open('vocabulary.py', encoding='utf-8').read()
    check('48-TR 文脈語彙は1行を1回だけ刻む（同じ行を2回解析しない）',
          'def _extract(toks):' in vsrc48tr
          and 'def _extract_all(toks):' in vsrc48tr
          and '_toks = tuple(tokenize(line))' in vsrc48tr
          and 'for tok in tokenize(line):' not in vsrc48tr[
              vsrc48tr.index('def build_context_vocab_cached('):], True)
    # ---- 48-TX **英語の辞書に載っている語は、ローマ字として読み直さない**
    import halfwidth as _H48
    import loanword as _L48
    check('48-TX 英語の辞書に載る語は、そう書いたもの（門が在る）',
          _H48._is_dictionary_english('attention')
          and _H48._is_dictionary_english('Amazon')      # 大小は問わない
          and not _H48._is_dictionary_english('mojinyuuryoku'), True)
    check('48-TX 名簿は既に在るもの（`_english_seed_all`。新しい表を作らない）',
          '_lw._english_seed_all()' in open(
              'halfwidth.py', encoding='utf-8').read(), True)
    check('48-TX 門は correct_romaji の中（呼び手すべてに掛かる）',
          '_is_dictionary_english(text)' in open(
              'halfwidth.py', encoding='utf-8').read(), True)
    from vocabulary import VocabularyStore as _VS48
    _st48tx = _VS48()
    for _ in range(3):
        _st48tx.add('あまぞん', 'アマゾン', 'IT・PC操作')
        _st48tx.add('もじにゅうりょく', '文字入力', 'IT・PC操作')
    check('48-TX 語彙に アマゾン が在っても amazon は化けない',
          _H48.correct_romaji('amazon', _st48tx, find_known_readings_flex),
          None)
    check('48-TX ローマ字のべた打ちは今までどおり直る',
          bool(_H48.correct_romaji('mojinyuuryoku', _st48tx,
                                   find_known_readings_flex)), True)

    # ---- 48-TY **生やすカタカナに、費用表を証拠にしない**（48-RO の続き）
    import oddness as _O48
    check('48-TY 綴りを聞く形が在る（spelling=True で費用表を外す）',
          'def _katakana_word_known(surf, dict_index=None, spelling=False):'
          in _osrc9 and 'if not spelling:' in _osrc9, True)
    check('48-TY 生やす側は綴りで聞く（48-LA の出口）',
          src.count('_odd._katakana_word_known(k[:i], dict_index, spelling=True)')
          == 1
          and '_odd._katakana_word_known(k, dict_index, spelling=True)' in src,
          True)
    check('48-TY シヤワー は綴りとしては語でない（費用表しか言っていない）',
          (_O48._katakana_word_known('シヤワー', None),
           _O48._katakana_word_known('シヤワー', None, spelling=True)),
          (True, False))
    check('48-TY 異様かを聞く側は今までどおり（広く採る＝守る側）',
          _O48._katakana_word_known('メモ', None), True)
    check('48-TY 外来語の表に在る語は、綴りでも語（シャワー・ダブル・クリック）',
          all(_O48._katakana_word_known(k, None, spelling=True)
              for k in ('シャワー', 'ダブル', 'クリック')), True)
    check('48-TY 世の語2つの複合は今までどおり（ダブル＋クリック）',
          C._katakana_known_or_compound('ダブルクリック', None)
          and not C._katakana_known_or_compound('リュクカミス', None), True)

    # ---- 48-UA **かなを綴りに変える門に、外来語の表を足した**（イージー → EG）
    check('48-UA 外来語の表も「1語として在る」の出どころ（ひらがなで聞く）',
          'from loanword import _katakana_seed_all as _ks' in src
          and '_AB.to_hiragana(body) in (_ks() or {})' in src, True)
    check('48-UA イージー・オーケー・キューピー は1語（綴りに変えない）',
          all(C._kana_run_is_ordinary_word(w, _st48tx, None)
              for w in ('イージー', 'オーケー', 'キューピー')), True)
    check('48-UA エフ・エイチディーエムアイ は表に無い（今までどおり通る）',
          any(C._kana_run_is_ordinary_word(w, _st48tx, None)
              for w in ('エフ', 'エイチディーエムアイ')), False)

    # ---- 48-UB **剥がす長さは 0 から見立てまで全部試す**
    check('48-UB 剥がす長さを全部試す（2通りだけにしない）',
          'for head in range(0, head_n + 1):' in src
          and 'for tail in range(0, tail_n + 1):' in src, True)
    check('48-UB 少ない側から試す（本体が長いほうが確か・降順にしない）',
          'range(tail_n, -1, -1)' not in src
          and 'range(head_n, -1, -1)' not in src, True)
    # **実際に届くか**（見立てが1文字多い形。ひらがなの HDMI）
    _tok48ub = C.make_tokenizer(_st48tx)
    _hd = C._fix_kana_alphabet('えいちでぃーえむあいの端子', _st48tx,
                               _tok48ub, None)
    check('48-UB ひらがなの えいちでぃーえむあい も HDMI に届く',
          [x[2] for x in _hd], ['HDMI'])
    check('48-UB カタカナの側は今までどおり',
          [x[2] for x in C._fix_kana_alphabet('エイチディーエムアイを確認',
                                              _st48tx, _tok48ub, None)],
          ['HDMI'])

    # ---- 48-UE **芯まるごとが同梱の表の語なら「読める」**
    check('48-UE 表がまるごと1語だと言うなら、解析の割り方で覆さない',
          'if _sj_rd.is_unit(core) is True:' in src
          and '_core_readable = True' in src, True)
    # ---- 48-UF **機能語の並びの異様は、まるごと1語の連続には言わない**
    check('48-UF まるごと1語なら異様と言わない（48-IT）',
          'if not original_ok and not doubled and finals < 3:' in src
          and 'if _sj_ff.is_unit(window) is True:' in src, True)
    check('48-UF 押しすぎ・終助詞3連はそのまま（打鍵の形が証拠）',
          'odd = doubled or finals >= 3 or not original_ok' in src, True)
    _ff48 = C._fix_functional_run
    check('48-UF 表の語 かきすて・かいとる は直さない',
          (_ff48('かきすて'), _ff48('かいとる')), (None, None))
    check('48-UF 48-IT の的は今までどおり（すねると・ににして・いいですよわね）',
          (_ff48('すねると'), _ff48('ににして'), _ff48('いいですよわね')),
          ('すると', 'にして', 'いいですよね'))
    check('48-UF 送り仮名の2度押しも今までどおり（さされるので）',
          _ff48('さされるので', after_kanji=True), 'されるので')

    # ---- 48-UG **48-FC の門を、漢字塊と混合塊にも**（学び22）
    check('48-UG 漢字塊も「同梱の表が1語」なら読める扱い',
          'if _sj_kr.is_unit(chunk) is True:' in src, True)
    check("48-UG' 混合塊も同じ門で降りる",
          'if _sj_mx.is_unit(chunk) is True:' in src, True)
    check("48-UG'' フォールバックは同じ `_readable` を見る（判定を2度書かない）",
          'if _readable:' in src
          and src.count(
              'if looks_like_real_word(chunk, store, tokenize_fn):') == 1, True)
    check("48-UG''' 門は4つの道すべてに在る（造語・漢字塊・混合塊・割り直し）",
          (src.count('_sj.is_unit(chunk)')
           + src.count('_sj_kr.is_unit(chunk)')
           + src.count('_sj_mx.is_unit(chunk)')
           + src.count('_sj_sp.is_unit(chunk)')) >= 4, True)

    # ---- 48-UH **カタカナの「触らない語」に、同梱の日本語の表も足す**
    import loanword as _L48h
    check('48-UH カタカナの門は打った綴りで表に聞く',
          '_sj_kw.is_unit(word) is True' in open(
              'loanword.py', encoding='utf-8').read(), True)
    # ---- 48-UI **入口（48-KI）に「表が1語なら、できあがっている」**
    check('48-UI 入口に門が在る（道ごとに書かない・48-GN）',
          'if _sj_in.is_unit(chunk) is True:' in src
          and src.index('_sj_in.is_unit(chunk)')
              < src.index("chunk[-1] in '中時'"), True)
    check('48-UI None（表が読めない）は意見なし＝今までどおり',
          'is True' in src[src.index('_sj_in.is_unit(chunk)') - 10:
                          src.index('_sj_in.is_unit(chunk)') + 40], True)

    # ---- 48-UK **漢字の直後のかな連続からは、巻き込みで字を落とさない**
    check('48-UK 送り仮名は2字で終わらない（門を連続まるごとに広げた）',
          'if not after_kanji:' in src
          and 'after_kanji and i < 2' not in src, True)
    check('48-UK 望ましい・目覚ましい の ましい は落とさない',
          (_ff48('ましい', after_kanji=True),
           _ff48('しくない', after_kanji=True)), (None, None))
    check('48-UK 漢字の直後でなければ今までどおり（すねると）',
          _ff48('すねると'), 'すると')
    check('48-UK 押しすぎ（同じ助詞の2度打ち）は漢字の直後でも直す',
          _ff48('さされるので', after_kanji=True), 'されるので')

    # ---- 48-UL **1つの既知語の中に収まっている窓は、語の断片**
    def _tok48ul(_x=None):
        # `ひっくり返す` を1語（0〜6・読みが立つ）とする作り物
        return [('ひっくり返す', '動詞:自立', 'ヒックリカエス', 0, 6, True)]
    _tks = _tok48ul()
    check('48-UL 語より短い範囲は「語の中の断片」',
          C._span_inside_one_token(_tks, 0, 4), True)
    check('48-UL 語ちょうどの範囲は断片ではない（今までどおり見る）',
          C._span_inside_one_token(_tks, 0, 6), False)
    check('48-UL 読みの立たない語は証拠にしない',
          C._span_inside_one_token(
              [('あいうえお', '名詞:一般', '', 0, 5, False)], 0, 3), False)
    check('48-UL 断片は窓として外す（48-IT の控えを積む**前**に・定義と1か所）',
          src.count('_span_inside_one_token(tokens, a, b)') == 2
          and src.index('_span_inside_one_token(tokens, a, b)',
                        src.index('for w_s, w_e in windows:'))
              < src.index('pending_ff.append((a, b, _ff))'), True)
    check('48-UL 空の範囲は「語の中」ではない',
          C._span_inside_one_token(
              [('さまざま', '名詞:形容動詞語幹', 'サマザマ', 0, 4, True)], 2, 2),
          False)
    check("48-UL'' 囲む語は表も「語だ」と言うものだけ（解析の当て推量は証拠にしない）",
          '_sj_sp1.is_unit(t[0]) is not True' in src, True)
    check("48-UL'' 表に無い語（ぎょうが・おもろし）で囲まれても断片扱いにしない",
          (C._span_inside_one_token(
              [('ぎょうが', '名詞:サ変接続', 'ギョウガ', 0, 4, True)], 0, 3),
           C._span_inside_one_token(
               [('おもろし', '形容詞:自立', 'オモロシ', 0, 4, True)], 0, 3)),
          (False, False))
    check("48-UL'' 表に在る語（さまざま）で囲まれたら断片扱い",
          C._span_inside_one_token(
              [('さまざま', '名詞:形容動詞語幹', 'サマザマ', 0, 4, True)], 0, 3),
          True)

    # ---- 48-UN **語の途中から始まる窓は、見本なしでは組み直さない**
    _tk48un = [('思いやり', '名詞:一般', 'オモイヤリ', 0, 4, True)]
    check('48-UN 語の途中の位置（1）は「語の途中」',
          C._starts_inside_word(_tk48un, 1), True)
    check('48-UN 語頭・語尾は「語の途中」ではない',
          (C._starts_inside_word(_tk48un, 0),
           C._starts_inside_word(_tk48un, 4)), (False, False))
    check('48-UN 表に無い語（ぎょうが）で囲まれても掛からない',
          C._starts_inside_word(
              [('ぎょうが', '名詞:サ変接続', 'ギョウガ', 0, 4, True)], 1),
          False)
    check('48-UN 見本なしの組み直し**3本すべて**に掛ける（学び22）',
          'if _lu and _starts_inside_word(tokens, _lu_a):' in src
          and 'if _lu_x and _cov and _starts_inside_word(' in src
          and src.count('_starts_inside_word(tokens, _lu_a)') == 2
          and src.count('_starts_inside_word(tokens, _cov[0][0])') == 1,
          True)
    check('48-UN 見本（同じ行の並記）の道には掛けない',
          '_starts_inside_word' not in src[
              src.index('_lq = _lq_attested_insertion('):
              src.index('_lq = _lq_attested_insertion(') + 1200], True)

    # ---- 48-UO **本人が書いた語は、機能語の並びの異様ではない**
    # ★ 材料は 48-UQ を通る形（文法の形をしている並び）で試すこと——
    #   通らない並びは 48-UQ が先に降りるので、この門を測れない。
    _st48uo = _VS48()
    for _ in range(3):
        _st48uo.add('すねると', '拗ねると', 'その他')
    check('48-UO 「立っているか」は決められた読み方で聞く（entry_is_solid）',
          'from vocabulary import entry_is_solid as _eis' in src, True)
    check('48-UO 本人の語彙に在る読みなら直さない',
          _ff48('すねると', store=_st48uo), None)
    check('48-UO 語彙を渡さなければ今までどおり',
          _ff48('すねると'), 'すると')
    _st48uo2 = _VS48()      # 空の語彙（本人が何も書いていない状態）
    check('48-UO 48-IT の的は語彙に無いので今までどおり',
          (_ff48('すねると', store=_st48uo2),
           _ff48('ににして', store=_st48uo2),
           _ff48('さされるので', after_kanji=True, store=_st48uo2)),
          ('すると', 'にして', 'されるので'))
    check('48-UO/48-UP 呼び手2つに同じ材料を渡す（予想と本番を揃える）',
          'store=store, tokenize_fn=tokenize_fn)' in src
          and 'store=store, tokenize_fn=tokenize_fn):' in src[
              src.index('def _psplit_cut('):
              src.index('def _psplit_is_kana_loanword(')], True)

    # ---- 48-UP **内容語が2つ以上ある窓は、機能語の並びではない**
    def _tok48up(text):
        # `すねる`＋`が`＋`あり`＋`ました` の作り物（内容語2つ）
        if text == 'すねるがありました':
            return [('すねる', '動詞:自立', 'スネル', 0, 3, True),
                    ('が', '助詞:格助詞:一般', 'ガ', 3, 4, True),
                    ('あり', '動詞:自立', 'アリ', 4, 6, True),
                    ('まし', '助動詞', 'マシ', 6, 8, True),
                    ('た', '助動詞', 'タ', 8, 9, True)]
        # `すねる`＋`と`（内容語1つ）
        return [('すねる', '動詞:自立', 'スネル', 0, 3, True),
                ('と', '助詞:接続助詞', 'ト', 3, 4, True)]
    check('48-UP 内容語が2つの窓には言わない',
          _ff48('すねるがありました', tokenize_fn=_tok48up), None)
    check('48-UP 内容語が1つなら今までどおり（すねると）',
          _ff48('すねると', tokenize_fn=_tok48up), 'すると')
    check('48-UP 数えるのは 48-SM の `_sm_content_count`（判定を作らない）',
          '_n_ct = _sm_content_count(window, tokenize_fn)' in src, True)
    check('48-UP 解析できなければ意見なし（99 は門にしない）',
          'if _n_ct is not None and 2 <= _n_ct < 99:' in src, True)
    check('48-UP 渡されなければ今までどおり',
          _ff48('すねるがありました'), 'するがありました')

    # ---- 48-UQ **巻き込みを疑うのは、文法の形をしているときだけ**
    check('48-UQ 文法の形をしていない並びからは1字も落とさない',
          (_ff48('こうい'), _ff48('たいう'), _ff48('どこく'),
           _ff48('まんし')), (None, None, None, None))
    check('48-UQ 文法の形をしている的は今までどおり',
          (_ff48('すねると'), _ff48('はいてく'), _ff48('いいですよわね')),
          ('すると', 'はいく', 'いいですよね'))
    check('48-UQ 押しすぎ・終助詞3連には掛けない（打鍵の形が証拠）',
          (_ff48('ににして'), _ff48('さされるので', after_kanji=True)),
          ('にして', 'されるので')),
    check('48-UQ 判定は 48-TH と同じ `explain_kana_run(stems_only=True)`',
          "_pg_mk.explain_kana_run(window," in src
          and 'stems_only=True' in src, True)

    # ---- 48-UR **英単語の出し入れでは、文脈語彙の控えを捨てない**
    _st48ur = _VS48()
    _n0 = _st48ur.shape_revision_ja()
    _r0 = _st48ur.shape_revision()
    _st48ur.add('en:planetarium', 'Planetarium', '英語')
    check('48-UR 英単語を足しても日本語の顔ぶれは進まない',
          (_st48ur.shape_revision_ja() == _n0,
           _st48ur.shape_revision() > _r0), (True, True))
    _st48ur.add('たんご', '単語', 'その他')
    check('48-UR 日本語の語を足したら進む',
          _st48ur.shape_revision_ja() > _n0, True)
    _n1 = _st48ur.shape_revision_ja()
    _st48ur.remove('en:planetarium', 'Planetarium')
    check('48-UR 英単語を消しても進まない',
          _st48ur.shape_revision_ja(), _n1)
    _st48ur.remove('たんご', '単語')
    check('48-UR 日本語の語を消したら進む',
          _st48ur.shape_revision_ja() > _n1, True)
    _vsrc48ur = open('vocabulary.py', encoding='utf-8').read()
    check('48-UR 文脈語彙の控えは日本語の顔ぶれで見分ける',
          'store_size = store.shape_revision_ja()' in _vsrc48ur, True)
    check('48-UR 読みを渡さない呼びは今までどおり両方進める（安全側）',
          'if reading is None or not str(reading).startswith(' in _vsrc48ur,
          True)

    # ---- 48-UT **塊の末尾の「活用した用言」は書き換えない**
    def _tok48ut(text):
        if text == 'じょうを見ました':
            return [('じ', '助動詞', 'ジ', 0, 1, True),
                    ('ょうを', '名詞:一般', '', 1, 4, False),
                    ('見', '動詞:自立', 'ミ', 4, 5, True),
                    ('まし', '助動詞', 'マシ', 5, 7, True),
                    ('た', '助動詞', 'タ', 7, 8, True)]
        if text == '簡易流力':
            return [('簡易', '名詞:一般', 'カンイ', 0, 2, True),
                    ('流', '名詞:接尾:一般', 'リュウ', 2, 3, True),
                    ('力', '名詞:接尾:一般', 'リョク', 3, 4, True)]
        return [(text, '名詞:一般', '', 0, len(text), True)]
    check('48-UT 末尾の用言（漢字を含む動詞:自立）を見つける',
          C._trailing_predicate('じょうを見ました', _tok48ut), '見ました')
    check('48-UT 名詞の接尾には掛からない（簡易流力・目もち長）',
          C._trailing_predicate('簡易流力', _tok48ut), '')
    check('48-UT 組み立ての出口に門が在る',
          '_tp = _trailing_predicate(chunk, tokenize_fn)' in src
          and "if _tp and not _conv[0].endswith(_tp):" in src, True)
    check('48-UT 解析できなければ意見なし（空を返す）',
          C._trailing_predicate('あ', lambda t: (_ for _ in ()).throw(
              RuntimeError('x'))), '')

    # ---- 48-UU **48-RK の割り直しも「末尾の助詞は動かさない」を守る**
    check('48-UU 3本目の道にも印を渡す（48-DJ の run_keep_tail）',
          'if (_khc is not None and run_keep_tail' in src
          and 'not _khc.endswith(run_keep_tail)):' in src, True)
    check('48-UU 印を渡す道が3本になった（従来の探索・芯・割り直し）',
          src.count('run_keep_tail') >= 6, True)

    # ---- 48-UV **2つ目が新しい語の頭なら「押しすぎ」ではない**
    def _tok48uv(text):
        # これ|は|はなし|です（切れ目は 2 と 3）
        if text == 'これははなしです':
            return [('これ', '名詞:代名詞:一般', 'コレ', 0, 2, True),
                    ('は', '助詞:係助詞', 'ハ', 2, 3, True),
                    ('はなし', '名詞:一般', 'ハナシ', 3, 6, True),
                    ('です', '助動詞', 'デス', 6, 8, True)]
        # なんと|とか（3 で始まるのは**助詞**）
        if text == 'なんととか':
            return [('なんと', '副詞:一般', 'ナント', 0, 3, True),
                    ('とか', '助詞:並立助詞', 'トカ', 3, 5, True)]
        # わ|かかし（2 では語が始まらない）
        if text == 'わかかし':
            return [('わ', '助詞:終助詞', 'ワ', 0, 1, True),
                    ('かかし', '名詞:一般', 'カカシ', 1, 4, True)]
        return [(text, '名詞:一般', '', 0, len(text), True)]
    check('48-UV これは＋はなし は語の切れ目',
          C._doubled_is_word_boundary('これははなしです', 2, _tok48uv), True)
    check('48-UV 2つ目が助詞なら切れ目ではない（なんと＋とか）',
          C._doubled_is_word_boundary('なんととか', 2, _tok48uv), False)
    check('48-UV 解析が i+1 で語を始めないなら切れ目ではない（わ＋かかし）',
          C._doubled_is_word_boundary('わかかし', 1, _tok48uv), False)
    check('48-UV 窓の頭（前が2文字未満）は切れ目ではない',
          (C._doubled_is_word_boundary('ににして', 0, _tok48uv),
           C._doubled_is_word_boundary('さされるので', 0, _tok48uv)),
          (False, False))
    check('48-UV 解析を渡さなければ今までどおり（押しすぎと見る）',
          C._doubled_is_word_boundary('これははなしです', 2), False)
    check('48-UV 押しすぎの判定に掛かっている',
          'and not _doubled_is_word_boundary(window, i,' in src, True)
    check('48-UV 的は今までどおり（ににして・さされるので・かかして）',
          (_ff48('ににして'), _ff48('さされるので', after_kanji=True),
           _ff48('かかして', after_kanji=True)),
          ('にして', 'されるので', 'かして'))
    check('48-UV これははなし は直さない（解析つき）',
          _ff48('これははなしです', tokenize_fn=_tok48uv), None)

    # ---- 48-UX **測って外した**（窓の輪には広げない）
    check('48-UX 窓の輪には掛けない（測って外した・説明が残っている）',
          '項目48-UX は測って外した' in src
          and 'if _starts_inside_word(tokens, a, kana_only=True):'
              not in src, True)
    check("48-UX' かなだけの語に限る引数は残す（48-UN が使う形の記録）",
          'def _starts_inside_word(tokens, a, kana_only=False):' in src,
          True)

    # ---- 48-UZ **ABAB の型も、1つの語の中の断片には掛けない**
    check('48-UZ 2つの道どちらにも門が在る（学び22）',
          src.count('or _span_inside_one_token(tokens, run_start,') == 2,
          True)
    check('48-UZ 判定は 48-UL と同じ関数（新しく書かない）',
          '_span_inside_one_token(tokens, run_start,' in src
          and 'def _span_inside_one_token(tokens, a, b):' in src, True)

    # ---- 48-VA **カタカナの連なりがまるごと表の語なら、その一部を開かない**
    check('48-VA 字の種類で伸ばして表に聞く（解析の切れ目は当てにならない）',
          'def _kata_run_is_word(line, a, b):' in src
          and 'if _kata_run_is_word(line, _ma, _mb):' in src, True)
    check('48-VA 伸びなければ False（連なりそのものは今までどおり）',
          C._kata_run_is_word('ショートライン', 0, 7), False)
    check('48-VA 連なりの一部なら True（ショートライン の中の ショートラ）',
          C._kata_run_is_word('ショートラインを確認しました。', 0, 5), True)
    # ★ 同梱の日本語の表は**広い**——`リュク` も `カミス` も載っている
    #   （48-RK の材料の性質）。だから門は「**伸びたときだけ**」効く:
    #   連なりそのものは伸びないので False（今までどおり開く）。
    check('48-VA 連なりそのものは False（伸びない＝今までどおり開く）',
          C._kata_run_is_word('文字リュクです', 2, 5), False)
    check('48-VA かな・漢字が混じる範囲は False',
          C._kata_run_is_word('乳リュク', 0, 4), False)

    # ---- 48-VB **塊＋送り仮名が表の語なら、その塊は語の一部**
    check('48-VB 漢字塊の「読める」に足してある',
          'if not _readable and _chunk_with_okurigana_is_word(' in src
          and 'def _chunk_with_okurigana_is_word(line, a, b):' in src, True)
    check('48-VB 足すのはうしろのひらがなだけ（4字まで）',
          'for k in range(1, 5):' in src
          and 'not is_hiragana(line[e - 1])' in src, True)
    check('48-VB うしろに何も無ければ False',
          C._chunk_with_okurigana_is_word('揺さ振', 0, 3), False)
    check('48-VB 漢字が続くだけなら False',
          C._chunk_with_okurigana_is_word('文字入力', 0, 2), False)
    check("48-VB' 読み繋ぎの道にも掛ける（学び22。2か所＋定義）",
          src.count('_chunk_with_okurigana_is_word(') == 3, True)

    # ---- 48-VC **`en:` の読みを控える**（覚え直しが 25,000 件を 120 回なめていた）
    _st48vc = _VS48()
    _st48vc.add('たんご', '単語', 'その他')
    _st48vc.add('en:planetarium', 'Planetarium', '英語')
    _st48vc.add('en:document', 'Document', '英語')
    check('48-VC 控えは走査と同じ中身',
          sorted(_st48vc.english_readings()),
          sorted(r for r in _st48vc._by_reading if r.startswith('en:')))
    _st48vc.remove('en:document', 'Document')
    check('48-VC 消したら控えからも消える',
          sorted(_st48vc.english_readings()),
          sorted(r for r in _st48vc._by_reading if r.startswith('en:')))
    _st48vc.add('en:callout', 'Callout', '英語')
    check('48-VC 足したら控えにも入る',
          sorted(_st48vc.english_readings()),
          sorted(r for r in _st48vc._by_reading if r.startswith('en:')))
    check('48-VC 日本語の読みは控えに入らない',
          'たんご' in _st48vc.english_readings(), False)
    _lwsrc48 = open('loanword.py', encoding='utf-8').read()
    check('48-VC 控えが無い語彙でも動く（走査に戻る）',
          "_er = getattr(store, 'english_readings', None)" in _lwsrc48
          and 'if callable(_er):' in _lwsrc48, True)

    check('48-TB 1語の辞書語の塊は読みに手を当てない（_single_known_token）',
          'def _single_known_token(' in src
          and 'if _single_known_token(chunk, tokenize_fn):' in src, True)
    check('48-TC 読みの立つ2字以上の漢字語は解析の読みのまま（別読みの組を落とす）',
          "_keep_rd = [r for r in readings if all(f in r for f in _fixed_rd)]" in src, True)
    check('48-TD 語の組は辞書の語だけの漢字の塊を丸ごと組み替えない',
          'def _seq_recomposes_known_kanji(' in src
          and 'if _seq_recomposes_known_kanji(chunk, win.get' in src, True)
    check('48-TE 形容詞語幹1字＋動詞連用形（浅煎り）はくっつく',
          _O9.can_join('浅', '形容詞:自立', '煎り', '動詞:自立'), True)
    check('48-TE 連体詞＋くらい は異様ではない（どのくらい）',
          "and b_sf in ('くらい', 'ぐらい', 'ほど'))):" in _osrc9, True)
    check('48-TF てる・でる の縮約は機能語',
          'てる' in C.AUXILIARY_TAILS and 'でない' in C.AUXILIARY_TAILS, True)
    check('48-TG 数字の直後の助数詞（かな）は連続の頭に入れない',
          'for _cnt in _KANA_COUNTERS:' in src and 'つ' in C._KANA_COUNTERS, True)
    check("48-SM 漢字を減らしてかな（カタカナも）を増やさない（48-ND (b) の線。余分な打鍵の除去と語境界の復元を認め、漢字語をかなの断片へ崩す置換を止める）",
          "if (sum(1 for _c in _repl if is_kanji(_c)) < _sm_nk" in src
          and '_kana = lambda _c: is_hiragana(_c) or is_katakana(_c)' in src, True)
    check('48-SU 世の語2つの複合のカタカナも語（ダブル＋クリック）',
          C._katakana_known_or_compound('ダブルクリック', None)
          and not C._katakana_known_or_compound('リュクカミス', None), True)
    # 別ループの m_start を漢字ループでも使う誤りを、文字列の個数で
    # 正解にしていた。実際の引数式を異なる位置と行頭で評価する。
    import ast as _ast_sr
    _prev_sr = [kw.value for node in _ast_sr.walk(_ast_sr.parse(src))
                if isinstance(node, _ast_sr.Call)
                and isinstance(node.func, _ast_sr.Name)
                and node.func.id == 'compose_from_intruded'
                for kw in node.keywords if kw.arg == 'prev_char']
    def _eval_prev_sr(m, k):
        return sorted(eval(compile(_ast_sr.Expression(value), '<prev_char>', 'eval'),
                           {'line':'012345', 'm_start':m, 'k_start':k})
                      for value in _prev_sr)
    check('48-SR 数量の直前の字は各ループの位置を使う（行頭は空）',
          'は数字の直後から始まる（数え方）ので' in src
          and _eval_prev_sr(2,5) == ['1','4']
          and _eval_prev_sr(0,0) == ['',''], True)
    check('48-SU 生やすカタカナは世の語（48-LA の出口）',
          'def _new_katakana_known(' in src
          and "_why['生やしたカタカナが世の語ではない（48-SU）'] += 1" in src, True)
    check('48-SV 真ん中の漢字は読みが同じときだけ助詞に（48-PG の線）',
          'and p1 not in _gap_readings(middle):' in src, True)
    check("48-SW/48-SW' 読みの立つ名詞＋接尾は切り直さない（1字に限らない）・用言に読み替えない",
          "if (L == 2 and '接尾' in pos[1] and run[0][0]" in src
          and 'def _d42_has_yougen(' in src, True)
    check("48-SW' 頭が数詞の連なりを外す門は置かない（設計42 の的 二階席 が 二｜階｜席）",
          "if '数' in pos[0]:" not in src, True)
    check('48-SX 得る（可能）: 機能語は うる だけ・自動機は R のあとの うる／え（とりうる・ありえない）',
          'うる' in C.BASIC_VERB_FORMS and 'える' not in C.BASIC_VERB_FORMS
          and _PG9.explain_kana_run('とりうる') and _PG9.explain_kana_run('ありえない'), True)
    check('48-SQ 名前＋敬称の名前は2字以上（せくん は名前の形ではない）',
          _PG9.explain_kana_run('せくん', no_words=True), False)
    check("48-SK' 索引の顔の1語は サ変／になる の尾だけ",
          "'にする', 'にし', 'となる', 'とし', 'として')))):" in src, True)
    check('48-SB 芯の再構築は 守る語＋1字 の門より先に見る',
          src.index('_md = _moved_dakuten_fix(core, store, dict_index)')
          < src.index("if is_protected_word(core[:-1]):"), True)
    _tk = lambda sf, pos: (sf, pos, '', 0, len(sf), True)
    check('48-SA 話す は人を を で受けない',
          C._verb_takes_no_person_object(_tk('話す', '動詞:自立')), True)
    check('48-SA 話し（連用形）も',
          C._verb_takes_no_person_object(_tk('話し', '動詞:自立')), True)
    check('48-SA 呼ぶ は受ける（表の外）',
          C._verb_takes_no_person_object(_tk('呼ぶ', '動詞:自立')), False)
    check('48-SA 説明（サ変）も',
          C._verb_takes_no_person_object(_tk('説明', '名詞:サ変接続')), True)
    check('48-SA 名詞の 話 は動詞ではない',
          C._verb_takes_no_person_object(_tk('話', '名詞:一般')), False)
    check('48-SC 優勢は回数なしで決める（_lu_dominant）',
          '_lu_dominant' in src and 'def _lu_dominant(' in src, True)
    check('48-SC 述語の尾は1つの部品（_lu_predicate_tail）',
          'def _lu_predicate_tail(' in src, True)
    check('48-SC/48-SJ 手の段は 0手 → ゛ → 隣のキー → 落とす → 遠い（脱字は自動には使わない）',
          'tiers = [[run], mark, cheap, drop, far]' in src, True)
    check('48-SJ 動詞の基本形＋です は組まない',
          "and t[0] in ('です', 'でした', 'ます', 'ました')" in src, True)
    check('48-SI 伸ばしを含む連続の①は 48-LU だけ',
          '伸ばしを含む連続に①。語の列として組み直し' in src, True)
    check('48-SK 内容語1つ＋です・ます は solid のときだけ',
          "if len(cset) == 1 and mn < 3:" in src, True)
    check('48-SC 内容語を3つ直に並べない・名詞の直後に動詞の部品を置かない',
          '_run_c >= 3' in src and "_pp.startswith('動詞')" in src, True)
    check("48-SC/48-SB' かな→かな はこの道では受け入れない（芯の持ち場）",
          'かな→かな はこの道では受け入れない' in src
          and '_mdk' not in src, True)
    check('48-SC 行全体の①の範囲で組み直す（_lu_scope）',
          'def _lu_scope(' in src and 'odd_known=_lu_odd' in src, True)
    check('48-SF 候補一覧の口（lu_run_candidates）',
          'def lu_run_candidates(' in src, True)
    check('48-SA の口は 48-PQ と同じ場所',
          '_person_object_fixes(line, store, tokenize_fn, dict_index)' in src,
          True)

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
    check('野外＋文章 は名詞どうしなので作れる（48-NA）',
          oddness.can_join('野外', '名詞:一般', '文章', '名詞:一般'), True)
    check('1字がらみは今までどおり残る（差＋釣れ）',
          oddness.can_join('差', '名詞:一般', '釣れ', '動詞:自立'), False)

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
          C._odd_spans_for_line('柚須苅田', tok_yusu, (), _St(), None),
          [(0, 4)])

    # 本人がよく使う姓なら立てない
    st2 = _St()
    st2.data = {'ゆす': (('柚須', 3),)}
    check('語彙に実績のある姓は立てない',
          C._odd_spans_for_line('柚須苅田', tok_yusu, (), st2, None), [])

    # 姓＋名（48-JL の守りの形）はこの規則の対象外
    def tok_takahashi(_line):
        return [('高橋', '名詞:固有名詞:人名:姓', 'タカハシ', 0, 2, True),
                ('祐太', '名詞:固有名詞:人名:名', 'ユウタ', 2, 4, True)]

    check('姓＋名は見ない',
          C._odd_spans_for_line('高橋祐太', tok_takahashi, (),
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

def test_span_over_space_48mf():
    """
    **補正の範囲は、空白を跨がない**（項目48-MF・2026-08-31。
    うにさんの画面「・**赤い補正範囲がタブスペースに掛かっている**」）。

    行を丸ごと直し直す道は10か所あり、どれも直したあとで
    `difflib` に元の行と突き合わせさせていた。`difflib` は文字の
    並びしか見ないので**タブを跨ぐ**:

        元   にゆうりよくみす<TAB>にゅうりょくみす<TAB>入力ミス
        後   入力ミス<TAB>入力ミス<TAB>入力ミス
        範囲 [0:17] = 'にゆうりよくみす<TAB>にゅうりょくみす' ⇒ '入力ミス'

    直した**文字列**は正しいのに、**どこを直したか**が壊れていた。
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

    print('--- 項目48-MF（補正の範囲は空白を跨がない） ---')

    check('タブの区画ごとに範囲を作る',
          C._diff_spans('にゆうりよくみす\tにゅうりょくみす\t入力ミス',
                        '入力ミス\t入力ミス\t入力ミス'),
          [(0, 8, 0, 4), (9, 17, 5, 9)])
    check('半角空白も区画の切れ目',
          C._diff_spans('あか あお', 'アカ あお'), [(0, 2, 0, 2)])
    check('全角空白も区画の切れ目',
          C._diff_spans('あか　あお', 'あか　アオ'),
          [(3, 5, 3, 5)])
    check('変わらない区画は範囲にしない',
          C._diff_spans('あか\tあお', 'あか\tあお'), [])
    # 空白そのものを直した行は、今までどおり行ごと突き合わせる
    check('空白の並びが変われば行ごと（空白が直しの中身）',
          C._diff_spans('あか あお', 'あかあお'), [(2, 3, 2, 2)])
    check('区切りの中身が違えば行ごと',
          C._diff_spans('あか あお', 'あか\tあお'), [(2, 3, 2, 3)])

    # **範囲は必ず空白を含まない**（上の作りの言い換え。ここが崩れたら
    # 画面の赤がまたタブの上に乗る）
    space_ok = True
    for before, after in (
            ('にゆうりよくみす\tにゅうりょくみす\t入力ミス',
             '入力ミス\t入力ミス\t入力ミス'),
            ('あ\tい\tう', 'ア\tイ\tウ'),
            ('たんこ\tたんご', 'たんご\tたんご')):
        for i1, i2, _j1, _j2 in C._diff_spans(before, after):
            if any(c in ' \t　' for c in before[i1:i2]):
                space_ok = False
    check('作った範囲に空白が入らない', space_ok, True)

    # **10か所とも通す**（学び22——片方だけに置くと、そちらを迂回する）
    src = open('corrector.py', encoding='utf-8').read()
    check('行ごとの突き合わせは _diff_spans だけ（生の difflib は無い）',
          'difflib.SequenceMatcher(None, line, corrected' in src, False)
    check('行を直し直す道は10か所とも _diff_spans を通る',
          src.count('for i1, i2, j1, j2 in _diff_spans(line, corrected):'),
          10)
    return all_ok

def test_u_insert_compose_48mg():
    """
    **う挿入の変換を、48-KX'（語幹＋接尾）にも聞く**（項目48-MG・
    2026-08-31。うにさんの画面「**しゅうりょじ　が補正されない**」）。

        しゅうりょじ  ①異様（48-KS が立つ）
                      ③う挿入 → しゅうりょうじ（敷き詰まる）
                      ⑤変換 …… `_convert_odd_kana_run` は**語彙の
                         実績2以上の4字語**を先頭に要求する。初期状態に
                         `しゅうりょう` は無いので None ＝落ちていた

    ところが 48-KX'（語幹（実績）＋接尾）は `しゅうりょうじ` を
    `終了時` に組めていた。**変換の道が2本あるのに、う挿入の門は
    1本しか聞いていなかった**（学び22 の型）。

    **門は緩めない**——う が語幹の内側に落ちることは今までどおり
    問う。そのために 48-KX' に「語幹の終わり」を返す口を足した。
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

    print("--- 項目48-MG（う挿入の変換を 48-KX' にも聞く） ---")

    class _St(object):
        def __init__(self, entries):
            self._e = entries

        def reading_of(self, _s):
            return None

        def lookup(self, r):
            return self._e.get(r, [])

    class _Di(object):
        def surfaces_for_reading(self, _r):
            return []

        def readings_for_surface(self, _s):
            return []

    st = _St({'しゅうりょう': [{'surface': '終了', 'count': 554}]})

    # 語幹の終わりを返す口（`with_head`）。**足しても既定の形は
    # 4つ組のまま**——古い読み手が壊れない。
    got4 = C._compose_kana_run_fixes('しゅうりょうじ', st, _Di())
    check('既定では今までどおり4つ組',
          [len(x) for x in got4], [4] * len(got4))
    got5 = C._compose_kana_run_fixes('しゅうりょうじ', st, _Di(),
                                     with_head=True)
    check('with_head なら語幹の終わりが5つ目に付く',
          [x[4] for x in got5] if got5 else 'なし',
          [6] if got5 else 'なし')      # しゅうりょう＝6字

    src = open('corrector.py', encoding='utf-8').read()
    check("う挿入は 48-KX' にも聞く",
          '_compose_kana_run_fixes(base, store, dict_index,' in src, True)
    check('門は残っている（う が語幹の内側に落ちること）',
          'if u_pos >= conv[1]:' in src, True)
    return all_ok

def test_honorific_prefix_48mh():
    """
    **頭の「お」「ご」は美化語の接頭**（項目48-MH・2026-08-31）。

        おせわになりました → **おわになりました**   ← 同梱の見本を壊す

    `せわになりました` は「よく使う語＋機能語」で説明が付くのに、
    頭に `お` が付いた途端に「説明できない＝異様」になり、
    `せ` を隣接キーの巻き込みと見て落としていた
    （`seedcheck` の唯一の壊し・v1.3.0 にも在った）。

    **`_is_functional_strict` は 48-LN で同じ判定を既に持っていた。**
    `_kana_run_explained_common` に無かっただけ——学び22
    「片方だけに置くと、そちらを迂回して素通りする」そのもの。
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

    print('--- 項目48-MH（頭の お・ご は美化語の接頭） ---')

    src = open('corrector.py', encoding='utf-8').read()
    check('2つの道の**両方**が頭の お を知っている',
          src.count("run[0] == 'お'") + src.count("run[0] in 'おご'"), 2)

    # 表が読める環境（janome の有無に依らない・oddness の表）でだけ測る
    import oddness
    if not oddness.available():
        print('   （語の表が無い環境なので、判定そのものは測らない）')
        return all_ok

    check('お＋よく使う語＋機能語は説明が付く（＝異様ではない）',
          C._kana_run_explained_common('おせわになりました'), True)
    check('ご＋よく使う語も同じ',
          C._kana_run_explained_common('ごれんらくします'),
          C._kana_run_explained_common('れんらくします'))
    check('お を外した形が説明できなければ、通さない',
          C._kana_run_explained_common('おすねると'), False)
    check('同梱の見本を壊さない（おせわになりました）',
          C._fix_functional_run('おせわになりました'), None)
    return all_ok

def test_free_suffix_intact_48me():
    """
    **何にでも自由に付く1字で終わる塊は、もうできあがっている**
    （項目48-ME・2026-08-31。うにさんの画面の誤検知
    `一番下に → 一番化に`）。

    解析は `一番下` を 一番（名詞）＋下（名詞:接尾）と読み、しかも
    **下 の読みを `か`** と言う（支配下・管理下 の か）。造語の道
    （48-EX）はその読み `いちばんか` を**そのまま** `一番`＋`化` と
    綴り直していた。**誤打はひとつも直していない**。

    `oddness.can_join` は既に「名詞＋位置の1字は繋げてよい」（6-3'）と
    言っている（画面に紫も出ない）。**判定は立っているのに、造語の道が
    それを見ずに走っていた**——入口は `_chunk_is_intact` ただ1つ
    （48-KI）。
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

    print('--- 項目48-ME（自由に付く1字で終わる塊は触らない） ---')

    src = open('corrector.py', encoding='utf-8').read()
    check('造語の道が入口（_chunk_is_intact）を通る',
          'はもうできあがっている（48-KI の入口）' in src, True)
    check('名簿は作らない（oddness の閉じた3つの類を借りる）',
          ('_odd1._POSITION_KANJI' in src and '_odd1._LAYOUT_KANJI' in src
           and '_odd1._AGGREGATE_KANJI' in src), True)

    import oddness
    if not oddness.available():
        print('   （語の表が無い環境なので、判定そのものは測らない）')
        return all_ok

    def tok(_line):
        return []

    for word, want in (('一番下', True), ('一番上', True),
                       ('画面上', True), ('空白行', True), ('漢字塊', True),
                       # うにさんの直したい塊は、どれもこの類で終わらない
                       ('殺意代価', False), ('再退化', False),
                       ('誘い消化', False), ('背景食', False),
                       ('最大家事', False)):
        check(f'{word} はできあがっている＝{want}',
              C._chunk_is_intact(word, tok), want)
    check('頭が語でなければ通さない（表に無い頭）',
          C._chunk_is_intact('鰐蟹下', tok), False)
    check('自由に付く類でない字で終われば、通さない',
          C._chunk_is_intact('一番価', tok), False)
    return all_ok


def test_kango_convert_48mi():
    """
    **かなのまま残った漢語を、漢字に変換する**（項目48-MI・2026-08-31。
    うにさんの画面「・**平仮名が漢字変換されない**」）。

    設計指針 U0:「**かなのまま打ちたいことの確信がなければ漢字変換
    する**」。変換の道（`_convert_odd_kana_run`）は在るのに、走るのは
    **異様と判定された連続だけ**だった。`かくにん` は語として説明が
    付く（＝異様ではない）ので、その道に一度も乗らない。

    門は6つ。とくに:
      (5) その読みの**漢字表記がただ1つ**（せんたく＝洗濯／選択 は触らない）
      (6) 直し先の頭が**漢語**（音読みだけで組める。ひらがな→平仮名 は
          平が訓読みなので落ちる）
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

    print('--- 項目48-MI（かなのまま残った漢語を変換） ---')

    # 引用の中は「その語を言及している」形（変換しない）
    check('かぎ括弧にそっくり入っていれば引用',
          C._is_quoted_whole('本来の読みは「しゅるい」です', 7, 11), True)
    check('括弧の外なら引用ではない',
          C._is_quoted_whole('かくにんします', 0, 4), False)
    check('開きと閉じが対でなければ引用ではない',
          C._is_quoted_whole('「しゅるいです', 1, 5), False)

    import kanji_onkun
    if kanji_onkun.available():
        check('確認は漢語（確＝かく音・認＝にん音）',
              C._is_kango('確認', 'かくにん'), True)
        check('平仮名は漢語ではない（平＝ひら訓）',
              C._is_kango('平仮名', 'ひらがな'), False)
        check('送り仮名の付く語は漢語ではない',
              C._is_kango('考える', 'かんがえる'), False)
        check('1字は漢語ではない', C._is_kango('本', 'ほん'), False)

    class _St(object):
        def __init__(self, d):
            self._d = d

        def lookup(self, r):
            return self._d.get(r, [])

    class _Di(object):
        def surfaces_for_reading(self, _r):
            return []

    st = _St({'かくにん': [{'surface': '確認', 'count': 3}],
              'せんたく': [{'surface': '選択', 'count': 3},
                           {'surface': '洗濯', 'count': 1}]})
    check('漢字表記が1つなら通す',
          sorted(C._kanji_faces_for_reading('かくにん', st, _Di())), ['確認'])
    check('**回数を問わず**数える（洗濯は実績1でも数える）',
          sorted(C._kanji_faces_for_reading('せんたく', st, _Di())),
          ['洗濯', '選択'])

    src = open('corrector.py', encoding='utf-8').read()
    check('この道はいちばん最後に載せる（手が立つ場所に割り込まない）',
          src.index('_kango_kana_fixes(line, store, dict_index)')
          > src.index('_reopen_mixed_run_fixes(line, store, tokenize_fn'),
          True)
    check('切り替えの口がある（CN_KANGO_CONV=0）',
          "CN_KANGO_CONV" in src, True)
    return all_ok


def test_one_hand_length_48mj():
    """
    **長さが変わる直しは、手が1つのときだけ**（項目48-MJ・2026-08-31。
    うにさんの画面 `きょだいか ⇒ **きょうか**`）。

    長さが変わる＝脱字か重複打鍵で、どちらも**1打の誤り**。そこに
    置き換えを重ねた「2手で、しかも長さも違う」直しは、誤りの説明では
    なく**近い語への寄せ**になる（語彙に `きょだい` が無いので
    「読めない並び」に見え、空いた席へ知っている語が吸い込む・
    48-HH と同じ型）。**同じ長さの2手はそのまま**。

    実測（初期状態・きれいな写しどうし）:

        readcheck romaji  直った 1887 → **1888** ／ 化けた 103 → **102**
        readcheck kana    直った 1885 → **1886** ／ 化けた 106 → **105**
        fpcheck           kana/romaji とも 差0
        seedcheck         直る 38 → **39** ／ 壊し 0
        実機メモ           化け `ごけいへんか → ごむいんか` が消えた
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    print('--- 項目48-MJ（長さが変わる直しは手が1つだけ） ---')
    src = open('corrector.py', encoding='utf-8').read()
    check('門が在る',
          'if len(cand_reading) != (end - start) and edits > 1:' in src, True)
    check('門は「ひらがな連続の道」に掛かっている',
          src.index('項目48-MJ') < src.index('直す（ひらがな連続の道）'),
          True)
    return all_ok


def test_conversion_anchor_48mk():
    """
    **変換の錨に「2字の漢語」を足す**（項目48-MK・2026-08-31。
    うにさんの画面の見出し「**原文が補正されない**」）。

    初期語彙 17,090件のうち**実績2以上は 401件だけ**（＝種の語）で、
    残りは janome から取り込んだ count 1。変換の道はどれも
    「先頭は実績2以上」を要求するので、**初期状態では種の401語しか
    直し先になれなかった**（`さいだいか → 最大化` が届かない）。

    **`count` を上げてはいけない**——実測（1,190語の2字漢語を
    count=2 に上げた写し）で `語彙素 → **合意**`・`長尾真 → **長官**`・
    同音異義語の一覧が潰れた（readcheck 化けた 102 → 110）。
    `count` は**全部の道が「本人が使う語」として読む**ため。

    そこで**変換の錨だけを別に言う**（`_is_conversion_anchor`）。
    3つの締めが要った（どれも readcheck で1つずつ 測った）:

      ・広げた錨は **`_convert_odd_kana_run` の (い) の枝へ渡さない**
        （`こほううに → 広報**ウニ**`）
      ・広げた錨は **読みの漢字表記がただ1つ**のときだけ
        （`ちゅかい → **注解**`）
      ・`_compose_kana_run_fixes` では、広げた錨なら
        **組んだ表記が世の中で1語**であることまで要る
        （`ちゅういか → **注意化**`——48-KX' の `鋳物化` と同じ穴）
      ・**異様と判定していない連続を変換する道（48-MI）は、
        いちばん厳しい錨だけ**（`こうどう → **行動**`）

    最終（初期状態・きれいな写しどうし）:

        readcheck romaji  直った 1888 → **1889** ／ 化けた 102 → **102**
        readcheck kana    直った 1886 → **1887** ／ 化けた 105 → **105**
        fpcheck           kana/romaji とも **0**
        seedcheck         直る 39/40 ／ 壊し 0（どちらも同値）
        実機メモ           `がいしょつする → 外出する`・
                          `さいだいか → 最大化`・`さいしょうか → 最小化`
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

    print('--- 項目48-MK（変換の錨に2字の漢語） ---')

    check('実績2以上はそのまま錨',
          C._is_conversion_anchor({'surface': 'つながり', 'count': 2},
                                  'つながり'), True)
    import kanji_onkun
    if kanji_onkun.available():
        check('2字の漢語は実績1でも錨',
              C._is_conversion_anchor({'surface': '最大', 'count': 1},
                                      'さいだい'), True)
        check('和語は錨にしない（送り仮名がある）',
              C._is_conversion_anchor({'surface': '考える', 'count': 1},
                                      'かんがえる'), False)
        check('訓読みの2字は錨にしない',
              C._is_conversion_anchor({'surface': '平仮', 'count': 1},
                                      'ひらがな'), False)
    check('空の記録は錨にしない', C._is_conversion_anchor(None, 'あ'), False)

    src = open('corrector.py', encoding='utf-8').read()
    check('広げた錨は (い) の枝へ渡さない',
          '広げた錨（2字の漢語）は、(い) の枝へは渡さない' in src, True)
    check('広げた錨は「読みの漢字表記がただ1つ」のときだけ',
          '広げた錨（2字の漢語）は、読みの漢字表記がただ1つのときだけ'
          in src, True)
    check('組む道では「直し先が1語」まで要る',
          '直し先が1語として在らない' in src, True)
    check('異様でない連続の変換は、いちばん厳しい錨だけ',
          'strict_anchor=True' in src, True)
    return all_ok

def test_split_at_wo_48mn():
    """
    **かな連続を、助詞「を」で区切る**（項目48-MN・2026-08-31・
    うにさんの指定）:

        「**「を」は単語で出てこないので、助詞として判定して
          前後を区切るとよいです**」

    現代語で `を` は助詞にしかならず、**語の読みの中に現れない**。
    この事実はもともと **「`を` を含む範囲は触らない」** の根拠として
    3か所で使っていた（48-CL・48-DO）。**触らないのではなく、そこで
    区切って両側をふつうに見る**——同じ事実の、もっと素直な使い方。

        ぱそみん**を**つかう   v1.3.0 は紫だけ → **パソコンをつかう**

    実測（初期状態・きれいな写しどうし）:

        readcheck romaji  直った 1889 → **1949**（+60）／
                          化けた 102 → **101**
        readcheck kana    直った 1887 → **1948**（+61）／
                          化けた 105 → **103**
        fpcheck           kana/romaji とも **0**
        seedcheck         直る 39/40 ／ 壊し 0（どちらも同値）
        実機メモ           **差0**（うにさんのメモは を の前後が漢字なので
                          かな連続が短く、割る場所がそもそも無い）

    **3つの門は残す**——別の道から `を` を跨ぐ範囲が来たときの守り。
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

    print('--- 項目48-MN（かな連続を「を」で区切る） ---')

    def split(runs, **kw):
        return list(C.split_runs_at_particle(runs, **kw))

    check('を を含まない連続は、そのまま',
          split([(0, 5, 'あいうえお')]), [(0, 5, 'あいうえお')])
    check('を の前後で割る（位置もずれない）',
          split([(0, 7, 'つづきをはなす')]),
          [(0, 3, 'つづき'), (4, 7, 'はなす')])
    check('行の途中の連続でも位置が合う',
          split([(10, 17, 'つづきをはなす')]),
          [(10, 13, 'つづき'), (14, 17, 'はなす')])
    check('を が2つあっても割れる',
          split([(0, 8, 'あをいうをえ')]),
          [(2, 4, 'いう')])
    check('短い切れ端は捨てる（既定は2字）',
          split([(0, 4, 'あをいう')]), [(2, 4, 'いう')])
    check('捨てる長さは指定できる',
          split([(0, 7, 'つづきをはなす')], min_len=4), [])
    check('頭が を でも落ちない',
          split([(0, 4, 'をあいう')]), [(1, 4, 'あいう')])
    check('尻が を でも落ちない',
          split([(0, 4, 'あいうを')]), [(0, 3, 'あいう')])
    check('を だけなら何も出ない', split([(0, 1, 'を')]), [])

    src = open('corrector.py', encoding='utf-8').read()
    check('かな連続の道は**2本とも**割ってから回す（学び22）',
          src.count('split_runs_at_particle(') , 3)   # 定義1＋呼び出し2
    # **門は残す**（別の道から を を跨ぐ範囲が来たときの守り）
    check('「を を含むので対象外」の門は残っている',
          src.count('を』を含むので') + src.count("'を' in core")
          + src.count("'を' in target") + src.count("'を' in window"), 4)
    return all_ok

def test_kango_stem_48mp():
    """
    **48-LC の実績の床を、2字の漢語でも越えられるようにする**
    （項目48-MP・2026-08-31。うにさんの画面「**原文が補正されない**」の
    `歳で以下 ⇒ 最大化`）。

    48-LC（読みに手を1つ加えると優勢な単位）は、直し先の語幹に
    **実績10以上**を要求する。初期状態の語彙は**実績2以上が種の
    401語だけ**なので、`最大`（実績1）にも届かない——**門ではなく
    枠の話**（48-MK と同じ形）。

    広げると面が増えて**実績では裁けなくなる**（どれも実績1）:

        歳で以下 → 裁定化(1) と 最大化(1) が並ぶ
        一致率  → **一途率**  ／  形態的 → **生態的**（実測の化け）

    受け止めるのは「**直し先が世の中で1語であること**」——
    表を「直す証拠」ではなく「**直し先が在ること**」の条件に使う
    （48-KF が入れなかった向きの逆・48-MK と同じ）。
    `最大化` は世の中に在り、`裁定化`・`一途率`・`生態的` は無い。

    **床を越えた面（実績で立った面）はそのまま**——今までの答えは
    1つも動かない。実測（初期状態・きれいな写しどうし）:

        readcheck romaji  1949/101 → **1949/101**（そのまま）
        readcheck kana    1948/103 → **1948/103**（そのまま）
        fpcheck           kana/romaji とも 0
        seedcheck         直る 39/40 ／ 壊し 0
        実機メモ           **3行**（全部 `歳で以下 → 最大化`＝的）
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

    print('--- 項目48-MP（2字の漢語も語幹にしてよい） ---')

    class _St(object):
        def __init__(self, d):
            self._d = d

        def lookup(self, r):
            return self._d.get(r, [])

    st = _St({'さいだい': [{'surface': '最大', 'count': 1}],
              'つながり': [{'surface': '繋がり', 'count': 1}]})

    check('床に届かない語幹は、今までどおり通さない',
          C._peel_one_suffix('さいだいか', 10, st), [])
    import kanji_onkun
    if kanji_onkun.available():
        check('kango_ok なら 2字の漢語は通す',
              C._peel_one_suffix('さいだいか', 10, st, kango_ok=True),
              [('最大化', 1, 4)])
        check('漢語でない語幹は kango_ok でも通さない（送り仮名）',
              C._peel_one_suffix('つながりか', 10, st, kango_ok=True), [])
    check('床を越える語幹は kango_ok に依らず通る',
          C._peel_one_suffix('さいだいか', 1, st), [('最大化', 1, 4)])

    src = open('corrector.py', encoding='utf-8').read()
    check('広げるのは「張り合う読みが無い」ときだけ',
          'kango_ok=(base_count == 0)' in src, True)
    check('広げた面には「世の中で1語」を要求する',
          'if base_count == 0 and any(c0 < need' in src, True)
    check('床を越えた面はそのまま（今までの答えを動かさない）',
          "fv[1] >= need or _sj3.is_unit(f) is True" in src, True)
    return all_ok

def test_on_shape_48mq():
    """
    **音読みは、印ではなく形で見分ける**（項目48-MQ・2026-08-31）。

    `kanji_onkun.json` の印（`on` / `kun` / `?`）は**穴が多い**——
    `効` の こう・`力` の りょく・`形` の けい・`致` の ち は、どれも
    音読みなのに `'?'` のまま。印だけを見ると `効率`（こうりつ）も
    `形態`（けいたい）も `入力`（にゅうりょく）も「漢語ではない」に
    なっていた（48-MI/MK/MP の3つがまとめて空振りする）。

    **印の穴は、形で埋められる。** 音読みは字音の作りから
    **1〜3拍の閉じた形**しか取らない:

        [頭の1字][拗音?][ん・う・い・く・き・つ・ち・っ?]

    訓読みはこの形に収まらない（かたち・ちから・おお・みと・
    あざな・まつむろ）。**語を並べた表ではなく、形の決まり。**
    1字の読みだけは形で分けられない（`じ`＝音／`こ`＝訓）ので、
    そこは印を見る（`kun`・`na`・`gai` を落とす）。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import kanji_onkun as ok

    print('--- 項目48-MQ（音読みを形で見分ける） ---')

    on_like = ('こう', 'りょく', 'けい', 'ち', 'だい', 'しょう', 'かく',
               'にん', 'じ', 'きょ', 'ぶん', 'そつ', 'いっ', 'しゅっ',
               'さい', 'たい', 'せき', 'りつ')
    kun_like = ('かたち', 'ちから', 'おお', 'みと', 'あざな', 'まつむろ',
                'たし', 'ひと', 'あらわ', 'こころざし')
    check('音読みの形は通る',
          [r for r in on_like if not ok.is_on_shape(r)], [])
    check('訓読みの形は通らない',
          [r for r in kun_like if ok.is_on_shape(r)], [])
    check('小書き・長音・撥音では始まらない',
          [r for r in ('っこ', 'ーん', 'んか', 'ゃく')
           if ok.is_on_shape(r)], [])
    check('4拍以上は音読みの形ではない',
          ok.is_on_shape('しゅうかく'), False)
    check('空は通さない', ok.is_on_shape(''), False)

    if not ok.available():
        print('   （音訓の表が無い環境なので、印との合わせ技は測らない）')
        return all_ok

    # 印が `kun`・`na` なら、形が合っていても落とす
    check('印が訓なら落とす（入＝い）', ok.is_on_reading('入', 'い'), False)
    check('印が訓なら落とす（小＝こ）', ok.is_on_reading('小', 'こ'), False)
    check('印が `?` でも、形が合えば通す（効＝こう）',
          ok.is_on_reading('効', 'こう'), True)
    check('印が `?` でも、形が合えば通す（力＝りょく）',
          ok.is_on_reading('力', 'りょく'), True)
    check('表に読みが1つも無い字でも、形で通る（巨＝きょ）',
          ok.is_on_reading('巨', 'きょ'), True)

    import corrector as C
    kango = ('確認 かくにん', '入力 にゅうりょく', '効率 こうりつ',
             '形態 けいたい', '一致 いっち', '最大 さいだい',
             '学校 がっこう', '種類 しゅるい')
    wago = ('平仮名 ひらがな', '考える かんがえる', '間違い まちがい',
            '繋がり つながり')
    check('漢語は漢語と言える',
          [x for x in kango if not C._is_kango(*x.split())], [])
    check('和語は漢語と言わない',
          [x for x in wago if C._is_kango(*x.split())], [])
    return all_ok

def test_purple_false_positives_48mr():
    """
    **紫の誤検知を2つ落とす**（項目48-MR・2026-08-31。うにさんの画面の
    「・補正の誤検知」の欄）。

        通常の文と**異なり全て**ひらがなであり、   ← 2か所に紫

    (1) `異なり|全て` —— `全て` は述語を修飾していて、`異なり全て`
        という複合語ではない。`oddness.can_join` の (6'')「後ろが
        副詞にもなれる語＝何にでも付く」と**同じ判定**を、48-JC の枝
        （動詞の連用形＋名詞）にも掛ける。あの枝は `can_join` を
        通らないので、片方だけに置くと迂回される（学び22）。

    (2) `てひらがなであり` —— `全` ＋ `て` で `全て` が閉じたあとの
        `ひらがな` が置けなかった。「語と語を直接つなげない」の決まりは
        `たん|あご` `すき|にん` のような**かなだけの並び**を止める
        ためのもので、**漢字が語の切れ目を保証している**ここでは要らない。
        ただし**用言（動詞）の形のときは今までどおり**——連用形の直後は
        複合動詞の場所で、開けると `入れ|ちいさい`（`入れていない` の
        壊れた形）まで説明が付き、**本物の異様を取りこぼす**。

    実測（初期状態・実機メモ全タブ）:

        紫の印  179 → **175**（消えたのは この2種4個だけ）
        readcheck kana/romaji・fpcheck・seedcheck・実機メモ 全部 **差0**
        中立文の紫（`probe_pos_fp` 300語）**60 → 60**
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import pos_grammar as pg

    print('--- 項目48-MR（紫の誤検知を2つ落とす） ---')

    # (2) 用言かどうかの見分け（表は作らない・活用の形だけ）
    words = {'入れる', '書く', '全て', '思い', '引き継ぎ', '見る'}
    check('一段の連用形は用言（入れ→入れる）',
          pg._looks_verb('入れ', words), True)
    check('五段の連用形は用言（書き→書く）',
          pg._looks_verb('書き', words), True)
    check('全て は用言ではない', pg._looks_verb('全て', words), False)
    check('引き継ぎ は用言ではない',
          pg._looks_verb('引き継ぎ', words), False)
    check('空は用言ではない', pg._looks_verb('', words), False)

    src = open('oddness.py', encoding='utf-8').read()
    check('48-JC の枝にも副詞性の門を掛けた',
          '後ろが副詞にもなれる語なら、複合語ではなく修飾' in src, True)
    psrc = open('pos_grammar.py', encoding='utf-8').read()
    check('漢字で閉じた語のあとは文節の頭（用言でなければ）',
          "'Bw' if _looks_verb(w0, words) else 'Bf'" in psrc, True)

    import oddness
    if not oddness.available():
        print('   （語の表が無い環境なので、判定そのものは測らない）')
        return all_ok

    check('全て のあとに語を置ける（漢字が切れ目を保証する）',
          pg.explain_kana_run('てひらがなであり', after_kanji=True,
                              kanji_stem='全'), True)
    check('入れ のあとには置けない（連用形＝複合動詞の場所）',
          pg.explain_kana_run('れちいさい', after_kanji=True,
                              kanji_stem='入'), False)
    return all_ok

def test_split_at_no_48ms():
    """
    **`の` でも区切る——ただし右側が語のときだけ**（項目48-MS・
    2026-08-31）。48-MN（`を`）の続き。

        やんご**の**つながり  → `やんご` ／ `つながり`

    `やんごの` 単独なら `たんごの` に直っていたのに、後ろに語が続くと
    窓が丸ごとになって芯が立たなかった（うにさんの一覧
    `やん後の繋がり ⇒ 単語の繋がり`）。

    **`の` は無条件では割れない**——`もの` `その` `など` のように
    **語の中にも現れる**（`を` との違い）。右側が**表か語彙の語**
    なら、その `の` は連体化の助詞だと言える。

    **項目48-MT（同じ長さの直しは、置き換えだけで説明が付くこと）も
    一緒に測った**。`の` で割ると `かなちで|の|ほせい` になり、
    左が `さかなで` に化けた（頭に さ を足して ち を消す＝字が横に
    ずれている）。打鍵の誤りは**その場**で起きるので、
    **位置ごとの違いの数が編集の数より多い**直しは採らない。
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

    print("--- 項目48-MS/MT（`の` で区切る・横ずれは採らない） ---")

    def split(runs, **kw):
        return list(C.split_runs_at_particle(runs, **kw))

    known = lambda f: f in ('つながり', 'ほせい', 'あいう')

    check('known を渡さなければ、の では割らない',
          split([(0, 8, 'やんごのつながり')]), [(0, 8, 'やんごのつながり')])
    check('右側が語なら の で割る',
          split([(0, 8, 'やんごのつながり')], known=known),
          [(0, 3, 'やんご'), (4, 8, 'つながり')])
    check('右側が語でなければ割らない',
          split([(0, 8, 'やんごのつなかり')], known=known),
          [(0, 8, 'やんごのつなかり')])
    check('左が短すぎれば割らない',
          split([(0, 6, 'あのつながり')], known=known),
          [(0, 6, 'あのつながり')])
    check('を と の の両方が在れば両方で割る',
          split([(0, 12, 'あいうをやんごのつながり')], known=known),
          [(0, 3, 'あいう'), (4, 7, 'やんご'), (8, 12, 'つながり')])
    check('を は known が無くても割る（今までどおり）',
          split([(0, 7, 'つづきをはなす')]),
          [(0, 3, 'つづき'), (4, 7, 'はなす')])

    src = open('corrector.py', encoding='utf-8').read()
    check('の の見分けは表と語彙の両方を見る（名簿を作らない）',
          '_split_known' in src, True)
    check('横ずれの門が在る（48-MT）',
          'if _hamming > edits:' in src, True)
    check('横ずれの門は「同じ長さ」のときだけ',
          'if len(cand_reading) == (end - start):' in src, True)
    return all_ok

def test_mark_span_reopen_48mv():
    """
    **連なりが長いときは、印の立った範囲だけを開く**（項目48-MV・
    2026-08-31。うにさんの一覧 `乳リュク見ています ⇒ 入力見ています`）。

    48-LA（混ざった連なりを連なりごと開く）の枠は**3〜8字**。
    `乳リュク見ています` は9字で外れていたが、**印は `乳リュク`(0..4)
    に立っている**。印は「どこが異様か」を言っているので、そこを開けば
    よい——連なり全体を開くのは切り出しがずれているときの手当てで、
    印が場所を教えているときは要らない。

    **開くのは「漢字＋世の中に無いカタカナ」の塊だけ**。1件ずつ
    測って締めた:

        昨日どっききょ**を見**ました。 → **を見 → 読**
            ひらがなを含む印は助詞・活用の尾を巻き込む（readcheck 8行）
        文字が元の**カール位置**に…／**クリック化ドラッグ**で操作
            世の中に在るカタカナ語は正しく書けている（tests_mock 3件）

    **「解析が読みを立てられたか」では見ない**——janome の無い環境では
    全部が「立たず」になり、正しいカタカナ語まで開く。**同梱の
    カタカナ語の表（9,094語）**を見れば環境に依らない。

    あわせて**カタカナを含む塊は縮んでよい**（設計27 の受け入れの
    「長さ ±1」）——カタカナは読みを字で綴った形なので1字≒1拍、
    漢字は1字≒2拍。`乳リュク`(4) → `入力`(2) は字数では縮みすぎに
    見えるが、**読みは にゅうりゅく → にゅうりょく で同じ長さ**。
    伸びる側は今までどおり ±1（膨らむ化けを止める）。

    実測（初期状態）: readcheck kana/romaji・fpcheck・seedcheck とも
    **差0**。実機メモは **4行が直り**（乳リュク → 入力）、
    紫の印 174 → **170**。
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

    print('--- 項目48-MV（印の範囲だけ開く） ---')

    check('世の中に無いカタカナが在れば True（リュク）',
          C._has_unknown_katakana('乳リュク'), True)
    check('世の中に在るカタカナ語なら False（ドラッグ）',
          C._has_unknown_katakana('クリック化ドラッグ'), False)
    check('カール も表に在る', C._has_unknown_katakana('カール位置'), False)
    check('カタカナが無ければ False', C._has_unknown_katakana('誤字し'), False)
    check('1字のカタカナは数えない', C._has_unknown_katakana('乳ク'), False)

    src = open('corrector.py', encoding='utf-8').read()
    check('長い連なりは印の範囲だけを開く',
          '印の範囲だけ開いて' in src, True)
    check('ひらがなを含む印は開かない',
          'if any(is_hiragana(_c) for _c in _piece):' in src, True)
    check('開くのは「読みの立たない断片を含む印」だけ',
          '_frag_marks' in src, True)
    check('カタカナを含む塊は縮んでよい（伸びる側は ±1 のまま）',
          'if _dl > 1:' in src and 'and len(surf) >= 2)' in src, True)
    # **効かなかったものは入れない**（小書きどうしの取り違え）
    check('小書きどうしの手は入れていない（測って差0だった）',
          '_SMALL_KANA_SWAP' in src, False)
    return all_ok

def test_assemble_after_hand_48mw():
    """
    **語の組み立ての受け皿を、手を当てた読みにも掛ける**
    （項目48-MW・2026-08-31。うにさんの一覧 `にゅ力ミス`・`二ゅ力ミス`・
    `に有力ミス` ⇒ すべて `入力ミス`）。

    設計27（異様を開いて直す）には「どれも組めなかったときの受け皿」
    として**語の組み立て**（`_convert_odd_kana_run`・48-LA）が在るが、
    **開いた読みそのものにしか掛かっていなかった**:

        にゅ力ミス → 開く → `にゅりょくみす`
                     組み立て …… 頭 `にゅりょく` は語彙に無い → 落ちる
                     **う を戻すと** `にゅうりょくみす`
                       ＝ にゅうりょく（入力・実績3）＋みす（ミス）

    `にゅうりよくみす`（かなだけ）は 48-KV が う を戻してから
    組み立てへ来るのに、**漢字の混ざった `にゅ力ミス` は来られなかった**
    ——**同じ誤りなのに、書かれ方で届いたり届かなかったり**していた。

    **順位には割り込まない**（`best` が無いときだけの受け皿のまま）。
    先に足すと `雛仮名 → 表明`・`にゅうりょ組ス → 入力ます`・
    `由良仮名 → 遊猟かなり` になった（実測）。**組めているならそちらが上。**

    実測（初期状態）: readcheck kana/romaji・fpcheck・seedcheck とも
    **差0**。実機メモは **6行が直り**、紫の印 170 → **166**。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    print('--- 項目48-MW（組み立ての受け皿を、手を当てた読みにも） ---')
    src = open('corrector.py', encoding='utf-8').read()

    # **項目48-NP で `not _ime_same` を外した**（2026-09-01）——
    # 打った記録の床は 2語の組のための門で、組み立ての道には
    # 掛けない。受け皿が「best が無いときだけ」なのは変わらない
    check('受け皿は best が無いときだけ',
          'if best is None and assemble:' in src, True)
    check('開いた読みと、手を当てた読みの両方に掛ける',
          '_try += [v for v in _fx if v not in _tried]' in src, True)
    check('受け入れは本道と同じ（長さ ±1）',
          'if _dl2 > 1:' in src, True)
    check('受け入れは本道と同じ（異様さが消えたか）',
          'if _odd.is_odd_run(_conv[0], tokenize_fn,' in src, True)
    # **同じ判定を2度書かない**——組み立ての中身は
    # `_convert_odd_kana_run` に任せる（48-GN）
    check('組み立てそのものは書き写さない',
          src.count('def _convert_odd_kana_run'), 1)
    return all_ok


def test_small_yoon_slip_48mx():
    """
    **拗音の小書きどうし**（ゃ・ゅ・ょ）は、どちらの入力でも
    1回の誤りで説明が付く（項目48-MX・2026-08-31。うにさんの一覧
    `がいしょつする ⇒ 外出する`）。

        かな入力    や(0,6) ゆ(0,7) よ(0,8) の**隣り合う3キー**を
                    Shift と一緒に押す。`kana_key_distance` は
                    ゃ-ゅ・ゅ-ょ を 1.0 と答えるので**この道は
                    既に通っていた**。ゃ-ょ だけ 2.0 で落ちていた
        ローマ字    ya / yu / yo ——**同じ2字の枠の、母音1字違い**。
                    `_KANA_TO_ROMAJI` で見ると o と u は QWERTY で
                    隣ではない（間に i）ので落ちていた

    **同じ誤りが、入力の設定で通ったり通らなかったりしていた**
    （学び22 の形）。異様判定も候補も既に立っていて、止めていたのは
    この門だけだった:

        [芯] 'がいしょつ' 似た読み=[('がいしゅつ', 1.0, 1), ...]
        [芯] → 'がいしゅつ' は1文字違うだけで、その違いは
              **隣のキーでは説明が付かない（romaji）**ので採らない

    3文字・3組の閉じた集まりなので、広がらない。
    実測（初期状態）: readcheck kana/romaji・fpcheck・seedcheck とも
    **差0**。紫の印 166 → **163**。
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

    print('--- 項目48-MX（拗音の小書きどうし） ---')
    for m in ('romaji', 'kana'):
        check(f'ゅ ⇔ ょ（{m}）', C.adjacent_slip('ょ', 'ゅ', m), True)
        check(f'ゃ ⇔ ょ（{m}）', C.adjacent_slip('ゃ', 'ょ', m), True)
        check(f'ゃ ⇔ ゅ（{m}）', C.adjacent_slip('ゃ', 'ゅ', m), True)
    # **広げすぎていないこと**——大書きの や・ゆ・よ どうしは
    # ローマ字では2字目の母音が離れたキーなので、今までどおり
    check('よ ⇔ ゆ（romaji）は今までどおり',
          C.adjacent_slip('よ', 'ゆ', 'romaji'), False)
    check('あ ⇔ い（romaji）は今までどおり',
          C.adjacent_slip('あ', 'い', 'romaji'), False)
    check('小書き ⇔ 大書き は今までどおり通る',
          C.adjacent_slip('ゅ', 'ゆ', 'romaji'), True)
    check('表は1か所だけ', len(C._SMALL_YOON), 3)
    return all_ok


def test_anchor_not_at_head_48my():
    """
    **変換の錨は、先頭でなくてよい**（項目48-MY・2026-08-31。
    うにさんの一覧 `引き月資料 ⇒ 引き継ぎ資料`）。

    `_convert_odd_kana_run`（48-KV の⑤）は「**先頭の区切りが
    語彙 count>=2**」を錨にしていた。錨が言いたいのは
    「**この並びは当てずっぽうではない**」であって、
    「先頭が実績を持つ」ではない:

        ひきつぎ | しりょう
        引き継ぎ(実績1)  資料(**実績3**)   → 引き継ぎ資料

    先頭が弱いときは締める:

        ・**(い) の枝だけ**（先頭＋機能語 の (あ) は通さない——
          あの枝は先頭だけが証拠なので、その先頭に実績が要る）
        ・**2つ目は語彙の実績2以上**（`_content_piece` の
          辞書の索引には落とさない。そこが 48-MK の
          `こほううに → 広報ウニ` の出どころ）
        ・**先頭の表記は語彙にただ1つ**のときだけ（どの漢字かを
          当てずっぽうにしない・設計38〜40）

    48-MK の門（漢字だけの表記がただ1つか）は**掛けない**。あれは
    「実績の**無い**語を錨にする」ための門で、漢字だけの表記を
    数えるので `引き継ぎ` のような送り仮名つきは必ず落ちる。

    実測（初期状態）: readcheck kana/romaji・fpcheck・seedcheck とも
    **差0**。紫の印 166 → **163**（48-MX と合わせて）。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    print('--- 項目48-MY（錨は先頭でなくてよい） ---')
    src = open('corrector.py', encoding='utf-8').read()

    check('弱い先頭の枝が在る', '_weak = True' in src, True)
    check('弱い先頭は (あ) の枝を通さない',
          'if (not _weak and not _short and not only_born_particle' in src
          and 'and _tail_kana_ok(ln1)):' in src, True)
    check('弱い先頭では2つ目は強い語（実績2以上か、段1がただ1つの索引の顔・48-ON）',
          'piece = _strong_piece(_frag)' in src, True)
    check('弱い先頭は表記が語彙にただ1つ',
          "len({e['surface'] for e in _cand}) == 1" in src, True)
    check('48-MK の門は弱い先頭には掛けない',
          'if (not _weak and not _idx' in src, True)
    check('いちばん厳しい錨（48-MI）は今までどおり',
          'strict_anchor=True' in src, True)
    # **同じ判定を2度書かない**（48-GN）——錨の中身は1か所
    check('錨の見分けは1か所', src.count('def _is_conversion_anchor'), 1)
    return all_ok


def test_noun_compound_48na():
    """
    **名詞どうしの複合は、日本語では既定で作れる**（項目48-NA・
    2026-08-31）。

    2字以上の名詞を2つ並べれば、その場で語になる——初期語彙・
    日本語文章・単語辞書・国語辞書・人称単数・自由形態素・文法範疇・
    大陸選手権。**辞書に無くても日本語として正しい。**

    `can_join` はここまでの門を全部くぐったあと、最後に
    (5)「後ろに立った実績があるか」＝**頻度**で裁いていた。頻度は
    「珍しいが正しい複合語」を落とす。実機メモ全タブで **43個の印**が
    立ち、うち **37個が誤検知**だった。

    **`野外文章` と `初期語彙` は、構造では割れない。** どちらも
    名詞:一般＋名詞:一般 で、違うのは意味だけ。エンジンは意味を
    持たないので、**構造が「作れる」と言う以上、印は立てない**。

    **固有名詞は外す**——`柚須苅田` のような人名・地名の並びは
    打ち間違いのことがある。

    実測: 初期状態は readcheck/fpcheck/seedcheck/実機メモ **すべて差0**。
    育ちは readcheck 直った 1646 → **1648**・化け 160 → **158**。
    紫の印 163 → **120**。


    **要素・単位をつくる1字の名詞**（項目48-NB）も一緒に見る。
    `語彙素` は 語彙(名詞:一般)＋素(名詞:一般) と割れて印が立って
    いた（形態素・音素・水素 は1語として辞書に在るので露わにならず、
    **辞書に無い組み合わせだけ**が異様に見えていた）。

    **1字の尻尾を「後ろに立った実績」で数える形は、測って落とした**
    ——表（`seed_japanese`）は語の一覧なので1字の漢字が入っておらず、
    `_RIGHT` に1字の項目が**ひとつも無かった**。数えるようにすると
    2,208種が立つが、**地名の接尾が桁違いに多く**（町7399・駅2942・
    村1583・県1030）、床をどこに置いても `月`(72) が通って
    **`引き月資料` の的が消えた**。閉じた文法の類に戻した。
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

    print('--- 項目48-NA/NB（名詞どうしの複合・要素の1字） ---')
    if not O.available():
        print('（表が無いので飛ばす）')
        return True

    N = '名詞:一般'
    check('名詞＋名詞（2字以上どうし）は作れる',
          O.can_join('初期', N, '語彙', N), True)
    check('日本語＋文章も同じ', O.can_join('日本語', N, '文章', N), True)
    check('単語＋辞書も同じ', O.can_join('単語', N, '辞書', N), True)
    check('野外＋文章も同じ（構造では割れない）',
          O.can_join('野外', N, '文章', N), True)
    check('固有名詞は外す（人名・地名の並びは守る）',
          O.can_join('柚須', '名詞:固有名詞:人名:姓',
                     '苅田', '名詞:固有名詞:地域:一般'), False)
    check('1字が相手なら今までどおり（引き月の的を守る）',
          O.can_join('引き', N, '月', N), False)
    check('要素の1字（素）は付く', O.can_join('語彙', N, '素', N), True)
    check('要素の1字（辞）も付く', O.can_join('接頭', N, '辞', N), True)
    check('要素の表は3字', len(O._ELEMENT_KANJI), 3)
    check('1字の尻尾は「後ろに立った実績」では数えない',
          any(len(k) == 1 for k in (O._RIGHT or {})), False)
    return all_ok


def test_renyou_one_char_48nc():
    """
    **動詞の連用形＋1字の名詞は、見ない**（項目48-NC・2026-08-31）。

    48-JC（`買い脊柱` が異様）を入れたときの記録に
    「**誤爆は `伸ばし棒`（話し言葉の複合）の1行**」とある。
    **その形が、後ろ1字**だった——連用形＋1字の名詞は、日本語で
    いちばん作りやすい複合名詞:

        伸ばし**棒**・押し**ピン**・引き**戸**・巻き**尺**・
        差し**歯**・貼り**紙**・立ち**位**

    48-JC の的 `買い脊柱` は**後ろが2字**なので残る。

    **`can_join` にも聞く形（48-KF の枝と同じ門）は、測って落とした。**
    紫の誤検知は2つ消える（`繰り返し文字`・`繰り返し傾向`）が、
    **育ちの readcheck で化けが1つ増えた**（157 → 158）。
    1字の門だけなら **直った 1648 → 1650・化け 157 のまま**。
    ★★「効果のあるものだけ入れる」——2つ入れると打ち消し合って
    1648/157（＝入れない場合と同じ）になった。

    実測: 初期状態は readcheck/fpcheck/seedcheck/実機メモ すべて差0。
    紫の印は `伸ばし棒` の2個だけが消えた。
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

    def tok_of(pairs):
        def _t(_line):
            pos = 0
            for sf, ps in pairs:
                yield (sf, ps, sf, pos)
                pos += len(sf)
        return _t

    print('--- 項目48-NC（連用形＋1字の名詞） ---')
    check('伸ばし棒 は立たない（後ろが1字）',
          O.is_odd_run('伸ばし棒', tok_of(
              [('伸ばし', '動詞:自立'), ('棒', '名詞:一般')])), [])
    check('買い脊柱 は今までどおり立つ（後ろが2字）',
          O.is_odd_run('買い脊柱', tok_of(
              [('買い', '動詞:自立'), ('脊柱', '名詞:一般')])),
          [('買い', '脊柱')])
    src = open('oddness.py', encoding='utf-8').read()
    check('can_join を足す形は入れていない（測って落とした）',
          'CN_NC2' in src, False)
    return all_ok


def test_assemble_on_main_path_48mz():
    """
    **本道でも「語の組み立て」を受け皿にする**（項目48-MZ・2026-08-31。
    うにさんの一覧 `引き月資料 ⇒ 引き継ぎ資料`）＋
    **組み立ては書かれ方を変えない**（項目48-ND）。

    材料は48-MY で全部そろっていた:

        引き継ぎ(実績1) ＋ 資料(実績3)          ← 48-MY で錨が立つ
        ひきつき → ひきつぎ（濁点の付け忘れ）    ← `_fixes` が作る
        `_convert_odd_kana_run('ひきつぎしりょう')` → **引き継ぎ資料**

    足りないのは道1本——語の組み立ての受け皿（48-LA／48-MW）は
    `assemble=True` のときだけで、渡すのは `_reopen_mixed_run_fixes`
    の1か所。**本道（漢字塊の道）は渡していなかった。**

    **錨は本人の語彙だけ**（`vocab_only=True`）——48-MK の広げた錨
    （2字の漢語・実績0）も `_content_piece` の辞書の索引も使わない。
    それでも育ちで3行壊れたので、**書かれ方**の門を3つ足した（48-ND）:

        接周辞 → **結集言葉**            漢字が増えた（3字 → 4字）
        由良仮名 → **有料借りや**        漢字だけの塊に、かなが残った
        音訓送り仮名 → **音訓送りかなり** 漢字が減って、かなが増えた

    (b) は一度きつく書いて失敗した——「漢字の数を減らさない」だけに
    したら `奥悠久子帝 → 奥行固定`（**的**）まで落ちた。**かなが
    増えたかどうか**を一緒に見て、漢字どうしの入れ替えを通す形に直した。

    実測: 初期は readcheck/fpcheck/seedcheck **差0**・実機メモ
    **+2行**・未解決 ◎15 → **16**・紫だけ 6 → **5**・紫の印 112 → **110**。
    育ちは実機メモ **+2行**（`奥悠久子帝 → 奥行固定`）・**壊し0**。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    print('--- 項目48-MZ/48-ND（本道の受け皿・書かれ方は変えない） ---')
    src = open('corrector.py', encoding='utf-8').read()

    check('本道から組み立てを呼ぶ',
          'assemble=True, vocab_only=True' in src, True)
    check('錨は本人の語彙だけ（辞書の索引に落とさない）',
          'if vocab_only:\n            return None' in src, True)
    check('広げた錨（2字の漢語）は使わない',
          'if (strict_anchor or vocab_only)' in src, True)
    check('(a) 元に無かったカタカナは生やさない',
          'and not any(is_katakana(c) for c in chunk):' in src, True)
    check('(b) 漢字を減らして、そのぶんかなを増やさない',
          '_nh = sum(1 for c in chunk if is_hiragana(c))' in src, True)
    check('(c) 漢字だけの塊は長くならない',
          'if _is_all_kanji(chunk) and len(_conv[0]) > len(chunk):'
          in src, True)
    # **同じ判定を2度書かない**（48-GN）——受け皿の中身は1か所
    check('組み立てそのものは書き写さない',
          src.count('def _convert_odd_kana_run'), 1)
    return all_ok


def test_stable_across_launches_48ne():
    """
    **打ち切るなら、良いものを残す**（項目48-NE・2026-08-31）。
    **新しい直しではなく、ずっと在った壊れかたを見つけたもの。**

    設計48-LU（語の列として組み直す）の `seg_full` は、組を `set` に
    貯めながら **8件を超えたら break** していた。`set` の回る順は
    **起動ごとに変わる**（Python は文字列のハッシュに毎回ちがう種を
    混ぜる）ので、**どの8件が残るかが起動ごとに変わって**いた:

        きんて  → `きて`        ／ **消えて**
        うそさい → そのまま      ／ **ウソ記載**
        さんとう → そのまま      ／ **山道**

    **使う人から見れば「直るときと直らないときがある」。**
    `hashcheck.py` はまさにこれを見る道具だが、**初期状態では拮抗が
    ほとんど起きない**ので 0 のまま通っていた。**育ちの語彙で回すと
    落ちる**（romaji 250語・種4通りで5件以上）。

    直しかたは「**順を決めてから切る**」。貯めるのは全部、切るのは
    並べたあと。軸は **実績の高い順 → 内容語の少ない順 → 表記 →
    組み方**（48-IE の実績の軸・48-LU (B) の語数と同じ向き）。

    **軸は全順序にすること。** 最初は `(-実績, 組の長さ, 表記)` で
    並べてまだ揺れた——`さえ|問う|が|あり|ました` の `あり` を
    機能語と見るか内容語と見るかで2つの組ができ、**表記も実績も
    組の長さも同じ**だった。**内容語の数**を軸に足して全順序にした。

    実測: 育ち hashcheck **5件以上 → 0**・育ち readcheck（種固定）
    直った 1645 → **1648**・化け 159 → **156**。初期は
    readcheck/fpcheck/seedcheck/実機メモ **すべて差0**。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    print('--- 項目48-NE（起動ごとに答えが変わらない） ---')
    src = open('corrector.py', encoding='utf-8').read()

    check('set を回りながら打ち切る形は残っていない',
          'if len(outs) > CAP:' in src, False)
    check('並べてから切る', "-t[1],\n                sum(1 for _pc in "
          "t[2] if _pc[0] == 'c')," in src, True)
    check('軸は全順序（表記と組み方まで）',
          "t[0], t[2])))[:CAP + 1]" in src, True)
    check('打ち切りの幅は変えていない', 'CAP = 8' in src, True)

    # **答えが種で変わらないこと**を、この場でも1つ確かめる
    import os
    import subprocess
    import sys
    code = (
        'import corrector as C\n'
        'from vocabulary import VocabularyStore\n'
        'st = VocabularyStore()\n'
        "for _ in range(12):\n"
        "    st.add('やまみち', '山道', 'その他')\n"
        "    st.add('とう', '問う', 'その他')\n"
        "    st.add('さえ', 'さえ', 'その他')\n"
        'tok = C.make_tokenizer(st)\n'
        "r = C.correct_line('さんとうがありました。', st, tok,\n"
        '                   __import__("vocabulary")'
        '.find_known_readings_flex,\n'
        "                   input_method='romaji')\n"
        "print(r['corrected'])\n")
    outs = set()
    for seed in ('0', '1', '12345'):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONUTF8='1')
        try:
            got = subprocess.run([sys.executable, '-c', code], env=env,
                                 capture_output=True, text=True,
                                 encoding='utf-8', timeout=180)
            outs.add((got.stdout or '').strip())
        except Exception as e:
            outs.add(f'ERR {e}')
    check(f'種を変えても同じ答え（{sorted(outs)}）', len(outs), 1)
    return all_ok


def test_convert_after_core_48nf():
    """
    **直した読みを、そのまま漢字へ**（項目48-NF・2026-09-01。
    うにさんの一覧 `がいしょつする ⇒ 外出する`・`すきにん ⇒ 確認`・
    `ひらんがな ⇒ 平仮名`）。

    変換の道（48-MI `_kango_kana_fixes`）は**元の行**のかな連続を見る。
    `がいしょつ` は語ではないので何も起きない。芯の再構築が
    `がいしゅつ` に直したあと、**その読みを見る道が一つも無かった**:

        [芯] 'がいしょつ' → 'がいしゅつ' に直す
        [窓] 芯の再構築で 'がいしょつ' を 'がいしゅつ' に直す
        （ここで終わり。**外出 は語彙に在る**のに）

    ここは**異様だと判定して芯を建て直した場所**なので、48-MI が使う
    「いちばん厳しい錨」ではなく**ふつうの錨**（48-MK）でよい——
    48-MI が厳しいのは「**異様と判定していない**連続」を触るからで、
    ここはその逆。うにさんの指定（48-KV ⑤）「**かなのまま打ちたい
    ことの確信がなければ漢字変換する**」。

    **門は4つ。全部、壊してから足した**（1行ずつ読んで見つけた）:

        (1) 芯が窓の頭から始まること
        (2) **変換の頭が、芯とぴたり同じ長さ**であること
        (3) **尻尾が元のまま**であること（48-KV ⑤ の (あ) の枝だけ）
        (4) **直前に、ひとりぼっちのひらがなが1字だけ立っていない**こと

        窓ごと差し替え     → びじすねが… → **ビジネスネガありました**
        (い) の枝を通す    → のりこえ|こる → **乗り越えコル**
        直前の1字を無視    → 昨日**も**おしろう → **も面白う**

    (4) は一度きつく書いて的を巻き添えにした（「直前がひらがななら
    通さない」にしたら `これから**ながく**がいしょつする ⇒
    これからながく外出する` まで落ちた）。**1字だけかどうか**を見る
    形に直した——48-KX の「頭の1字ひらがな」と同じ見立て。

    実測: 初期は実機メモ **15行が直り**（すきにん→確認・ひらんがな→
    平仮名・がいしょつする→外出する）、未解決 ◎16 → **17**。
    育ちは readcheck（種固定）1648/156 → **1651/156**（直った +3・
    化け据え置き）、実機メモ **10行が直る・壊し0**。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    print('--- 項目48-NF（直した読みを、そのまま漢字へ） ---')
    src = open('corrector.py', encoding='utf-8').read()

    check('(1) 芯が窓の頭から始まること',
          'c_s == 0 and core_fix' in src, True)
    check('(2) 変換の頭が芯とぴたり同じ長さ',
          '_cc[1] == len(core_fix)' in src, True)
    check('(3) 尻尾が元のまま',
          "_cc[0].endswith(_rest)" in src, True)
    check('(4) 直前のひとりぼっちの1字ひらがなを見る',
          '_head_free = (a - _bk) != 1' in src, True)
    check('採るのは芯の範囲だけ（窓ごとは触らない）',
          'replacements.append((a + c_s, a + c_e, _core_conv,' in src, True)
    check('変換で縮む範囲は長さの検査から外す',
          'for spans in (lu_taken, conv_taken)' in src, True)
    # **同じ判定を2度書かない**（48-GN）——変換の中身は1か所
    check('変換そのものは書き写さない',
          src.count('def _convert_odd_kana_run'), 1)
    return all_ok


def test_whole_word_floor_48ng():
    """
    **1字の漢字の読み替えの門を、丸ごと1語がくぐれる床を下げた**
    （項目48-NG・2026-09-01。うにさんの一覧 `雛仮名 ⇒ 平仮名`）。

    48-JG が塞いでいる化けは `空白行 → 空白くい`(実績96) と
    `高橋佑 → 高橋よう`(実績3)。**どちらも2語の組**で、丸ごと1語では
    ない。48-LB はそこに気づいて「丸ごと1語で実績10以上なら通す」と
    抜け道を作ったが、**10 という数はうにさんの育ちの `平仮名`(16) に
    合わせただけ**だった。初期状態では:

        ひらがな → 平仮名(実績**2**) ／ ひらがな(実績**2**)
        雛仮名 → **ひらがな**（かな表記が勝っていた）

    `_kanji_pref`（元が漢字なら漢字の表記を先に）は在るのに、
    **48-JG の門が 平仮名 を候補から落としていた**ので出番が無かった。

    2 に下げて全部測ると、初期・育ちとも readcheck/fpcheck/seedcheck は
    **差0**、実機メモは **+2行**（`雛仮名 → 平仮名`）で壊し0、
    未解決の一覧は ◎ 17 → **18** ／ ○ 1 → **0**。
    **床は「丸ごと1語かどうか」で効いていて、数では効いていなかった。**
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

    print('--- 項目48-NG（丸ごと1語の床） ---')
    check('床は 2', C._WHOLE_KANJI_FLOOR, 2)
    src = open('corrector.py', encoding='utf-8').read()
    check('門をくぐれるのは丸ごと1語だけ（2語の組は今までどおり）',
          "surf in getattr(_surfaces, 'whole', ())" in src, True)
    check('測るための切り替え口が在る', 'CN_WHOLE_FLOOR' in src, True)
    return all_ok


def test_romaji_cost_wiring_48nj():
    """
    **ローマ字入力のときは、ローマ字のキーで測る**（項目48-NJ・
    2026-09-01）——**測って、既定では入れないことにした**。
    ここで見張るのは「**切ってあること**」と「配線が在ること」。

    `vocabulary.find_known_readings_flex` は `input_method` を受け取らず、
    費用は `kana_layout` の**かなキー配列の距離**だけで決まっていた:

        や → た   かな **99.0**（無関係）／ ローマ字 ya→ta は **隣**
        や → か   かな **1.0**（隣）    ／ ローマ字 ya→ka は 隣ではない

    `readcheck romaji 600 --adjacent`（項目48-NI で足した材料）を
    `tools_local/probe_romaji_cost.py` で数えると、**ローマ字では隣キー
    1打・かなでは遠い**行が **275**。正解の読みは**全部 候補に挙がって
    いる**が、**4位以下が94件**（費用 2.0〜3.0 が181件）。

    足す形と、置き換える形の実測（初期状態）:

        足す（union）        直った 1949 → **1948**・化け 103 → **104**
        **置き換える（排他）**  直った **1949 のまま**・化け 103 → **99**
        `--adjacent` の材料  隣接キー 直った 255 → **273**・化け 47 → **32**

    fpcheck 0/0・seedcheck 直る39/40 壊し0・実機メモ（かな）差0。
    **育ちでは下がるが、うにさんの指定で優先度は低い**
    （「育ちは主に同音異義語のために使うが、それでも優先度は低い」）。

    切り替えの口 `CN_ROMAJI_COST=0` で昔の形（かな配列だけ）に戻せる。
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
    import kana_layout as K

    print('--- 項目48-NI/NJ（隣接キーの材料・ローマ字の隣接） ---')
    check('既定は入っている', K._romaji_cost_on(), True)

    got = dict(K.nearby_candidates('や', input_method='romaji'))
    kana = dict(K.nearby_candidates('や'))
    # **ローマ字では ya→ta が隣**（QWERTY の t と y）
    check('ローマ字では ya→ta が隣に居る', got.get('た'), 0.5)
    # **かな配列の隣は見ない**——`や`(0,6) の隣 `ん` は、
    # ローマ字入力の人にとって根拠ではない（うにさんの指定）
    check('かな配列の隣（ん）は、ローマ字では入れない', got.get('ん'), None)
    check('かな入力では今までどおり ん が隣に居る', kana.get('ん'), 1.0)
    check('かな入力では た は隣ではない（音の似かたで 1.4）',
          kana.get('た'), 1.4)
    # **同じキーの変わり者は、どちらでも残す**（小書き・濁点）
    check('ローマ字でも 小書き は残る', got.get('ゃ'), 0.3)
    check('ローマ字でも 濁点 は残る',
          dict(K.nearby_candidates('か', input_method='romaji')).get('が'),
          0.3)
    _old = os.environ.get('CN_ROMAJI_COST')
    os.environ['CN_ROMAJI_COST'] = '0'
    try:
        K.nearby_candidates.cache_clear()
        check('CN_ROMAJI_COST=0 で昔の形（かな配列）に戻る',
              dict(K.nearby_candidates(
                  'や', input_method='romaji')).get('ん'), 1.0)
    finally:
        if _old is None:
            os.environ.pop('CN_ROMAJI_COST', None)
        else:
            os.environ['CN_ROMAJI_COST'] = _old
        K.nearby_candidates.cache_clear()

    src = open('vocabulary.py', encoding='utf-8').read()
    check('探索が入力方式を受け取る', 'input_method=None' in src, True)
    # キャッシュの書き方ではなく、入力方式ごとに結果が分離することを測る。
    import vocabulary as V
    from unittest.mock import Mock, patch
    fake_store = Mock(); fake_store._by_reading = {}
    V._FLEX_CACHE.clear()
    with patch.object(V, '_find_known_readings_flex_uncached',
                      side_effect=lambda *a, **kw: [kw['input_method']]) as search:
        first = V.find_known_readings_flex('fixture', fake_store, input_method='kana')
        second = V.find_known_readings_flex('fixture', fake_store, input_method='romaji')
        again = V.find_known_readings_flex('fixture', fake_store, input_method='kana')
        check('控えの鍵にも入力方式が入る',
              (first, second, again, search.call_count),
              (['kana'], ['romaji'], ['kana'], 2))
    V._FLEX_CACHE.clear()
    csrc = open('corrector.py', encoding='utf-8').read()
    # **入口で1回だけ結ぶ**（呼び出しは何十か所もある・学び22）
    check('入口で1回だけ結ぶ', '入口で1回だけ結ぶ' in csrc, True)
    # **`readcheck.py` はリポジトリが追跡していない**（測る道具は
    # 入れない決まり）。**無ければこの1件だけ飛ばす**——
    # **有るのに落ちるのと、無いから測れないのは別**（項目48-MC で
    # 同じ罠を踏んで置いた形。CI は追跡ファイルだけで回る）。
    import os as _os
    if _os.path.exists('readcheck.py'):
        rsrc = open('readcheck.py', encoding='utf-8').read()
        check('隣接キーの材料が在る（既定では足さない）',
              "'--adjacent' in sys.argv" in rsrc, True)
    else:
        print('..  隣接キーの材料（readcheck.py が無いので飛ばす）')
    return all_ok


def test_open_odd_single_kanji_48nk():
    """
    **異様な1字の漢字を、読みのかなに開く**（項目48-NK・2026-09-01）。

    うにさんの指定:

        「**『見』を『み』と読んでるのに1文字で区切っているのが
          変ですよね。**」（`設計の**見**して、 ⇒ 設計の**み**して`）

    解析は `設計|の|見(み)|し|て` と切り、紫も `('見','し')` に立って
    いた——**判定は在って、直す道が無かった**。ここまでの道はどれも
    「かなを漢字に直す」向きで、**漢字をかなに開き戻す**道が無い。

    門は3つ。どれも**この行の中だけ**を見る（語彙も辞書も引かない）:

      (1) **紫の中に居る1字の漢字**で、読みが3拍まで
      (2) 開くと、**隣のかなと合わさって1つの機能語になる**
          （`の`＋`み` → `のみ`＝助詞:副助詞）。**ここが証拠**——
          うにさんの「1文字で区切っているのが変」そのもの
      (3) 開いたら**異様さが消える**

    実機メモ全タブ（1,740行）で **当たり4件・全部が的・誤爆0**
    （`tools_local/probe_open_single.py`）。実測（初期・同じ
    `session.json` どうし）: readcheck/fpcheck/seedcheck **差0**、
    実機メモ **5行が直り壊し0**、紫の印 112 → **107**、
    うにさんの画面20行 **◎4 → ◎5**。
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

    def tok_of(pairs):
        def _t(_line):
            pos = 0
            for sf, ps, rd in pairs:
                yield (sf, ps, rd, pos, pos + len(sf), True)
                pos += len(sf)
        return _t

    print('--- 項目48-NK（異様な1字の漢字を、かなに開く） ---')
    src = open('corrector.py', encoding='utf-8').read()
    check('関数が在る', 'def _open_odd_single_kanji' in src, True)
    check('(1) 紫の中に居ること',
          'if not any(a <= start < b for a, b in marks):' in src, True)
    check('(2) 隣のかなと合わさって機能語になること',
          "'助詞' in (u[1] or '') or '助動詞' in (u[1] or '')" in src, True)
    from types import SimpleNamespace
    tail_tok=tok_of([('たり','助詞:並立助詞','たり')])
    still_odd=SimpleNamespace(odd_spans=lambda text,tok:[(0,2)])
    check('(3) 開いたら異様さが消えること',
          C._open_one_kana('た李',1,'り',tail_tok,still_odd),None)
    check('同じ口（_kv）に載せている',
          'for _o1 in _open_odd_single_kanji(line, tokenize_fn):'
          in src, True)
    # **読みは解析の1つだけに頼らない**（48-NK'・うにさんが「見る」の
    # 他の例を挙げてくれた: 着き・居い・似に・煮に・得え・来き）。
    # 1字で立つ漢字に解析が与える読みは**たいてい音読み**
    # （着→ちゃく・居→きょ）。**同梱の `kanji_onkun` に一覧が在る**
    check('訓読みも試す（表は kanji_onkun を借りる）',
          "_ok.readings_of(surf)" in src, True)
    check('音読みは試さない',
          "_ok.kind_of(surf, _r) != 'on'" in src, True)
    check('読みの表を新しく作らない（同梱の表を借りる）',
          'import kanji_onkun as _ok' in src, True)
    # **数字の直後は触らない**（48-NO）
    check('数字の直後の連なりは触らない（48-NO）',
          'if _preceded_by_digit(line, start):' in src, True)
    # **語彙も辞書も引かない**（この行の中だけで決まる）
    check('語彙を引かない', 'store' in
          src[src.index('def _open_odd_single_kanji'):
              src.index('def _reopen_mixed_run_fixes')], False)
    return all_ok


def test_na_stem_48nm_48nn():
    """
    **ナ形容詞の語幹は「だ」の活用形しか従えない**（項目48-NM／48-NN・
    2026-09-01・うにさんの列挙）:

        有力な／有力に／有力で／有力だ／有力なら／有力ならば／
        有力です／有力だった／有力だした／有力ではない／
        有力じゃない／有力でしょう／有力だろう／有力。／有力！

    「だ」＝断定の助動詞。「な」＝その連体形。「に」「で」＝格助詞・
    接続助詞、または「だ」の連用形。——**後ろに来られるのは
    「だ」の活用形と、助詞・記号だけ。**

    **名詞は入れない。** うにさんの整理:「『重要ポイント』は
    ナ形容詞ではなく**複合名詞**」「**安全チェックは、複合名詞**」。
    解析は 重要・自由・自然・安全・特殊 を全部 `形容動詞語幹` と言うが
    **どれも名詞でもある**ので、名詞が続けば複合名詞（48-NA が裁く）。
    実測でも、名詞まで広げると **8件増えて全部が誤検知**だった
    （自由形態素・自然発生・単純計算・特殊動詞）。

    **動詞・形容詞は複合名詞になりようがない**ので、そこだけ採る
    （48-NM）。そして**そこに「に」を入れる**（48-NN）——うにさんの
    「**隣接キーの疑惑よりも先に、1文字の接続詞を疑うべきでしょうか**」
    への答えは **はい**。1字の助詞は閉じた集まりなので候補が広がらず、
    入れて読めれば**それが本来の入力**。しかも語幹＋動詞のあいだに
    入る助詞は**「に」ただ1つ**に決まる（文法が答えを1つにする）。

        静か歩く → **静かに歩く**
        静かに歩く → そのまま ／ 重要ポイントです → そのまま
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

    print('--- 項目48-NM/NN（ナ形容詞の語幹） ---')
    N = '名詞:形容動詞語幹'
    check('語幹＋動詞は異様', O.can_join('有力', N, '探す', '動詞:自立'),
          False)
    check('語幹＋形容詞も異様',
          O.can_join('静か', N, '楽しい', '形容詞:自立'), False)
    check('語幹＋名詞は触らない（複合名詞・うにさんの整理）',
          O.can_join('重要', N, 'ポイント', '名詞:一般'), True)
    check('語幹＋名詞（漢語）も触らない',
          O.can_join('自由', N, '形態素', '名詞:一般'), True)
    check('語幹＋サ変名詞も触らない',
          O.can_join('簡易', N, '入力', '名詞:サ変接続'), True)
    # 48-KW（かなを含む語幹＋名詞）は今までどおり
    check('かなを含む語幹＋名詞は今までどおり異様（48-KW）',
          O.can_join('好き', N, '任', '名詞:一般'), False)

    src = open('corrector.py', encoding='utf-8').read()
    check('「に」を入れる道が在る（48-NN）',
          'def _insert_na_ni' in src, True)
    check('入れるのは「に」ただ1つ',
          "line[:start] + 'に' + line[start:]" in src, True)
    check('入れたら異様さが消えることを見る',
          'if _odd_nn.odd_spans(fixed, tokenize_fn):' in src, True)
    check('同じ口（_kv）に載せている',
          'for _ni in _insert_na_ni(line, tokenize_fn):' in src, True)
    # **「する」の活用は入れない**（サ変動詞・実測で `安定している` を
    # `安定にしている` にした）。名簿は `oddness._SURU_FORMS` に任せる
    check('「する」の活用は入れない',
          "if b[0] in _odd_suru._SURU_FORMS:" in src, True)
    # **1字がらみでは動かない**（48-HU と同じ門）。`これは**んさち**
    # です。` は `はんさ`（煩瑣）＋`ち`（1字の動詞）と切れ、
    # `はんさにち` を作った（readcheck で実測）
    check('1字がらみでは動かない',
          'if len(a[0]) < 2 or len(b[0]) < 2:' in src, True)
    check('名簿を2つ作らない（_SURU_FORMS を借りる）',
          src.count("_SURU_FORMS = ") , 0)
    return all_ok


def test_ime_record_not_over_assemble_48np():
    """
    **打った記録は、語の組み立ての道には掛けない**（項目48-NP・
    2026-09-01・うにさんの指定）:

        「**有力はまだ直りませんね。有力の後ろに続いてミスが来る
          はずないのですが。**」

    `に有力ミス` は**うにさん自身が変換して確定した**並びなので、
    `ime_readings.json` に記録が残る。48-LB の門（本人確定の記録が
    ある塊は、丸ごと1語・実績20以上だけが上書きできる）が
    **全部の道を塞いでいた**——だから実機だけ直らず、
    `ime_readings.json` の無い初期状態では直っていた。
    **ものさしと実機が食い違っていた**（うにさんの画面が正しい）。

    だが**その記録は「IME がそう変換した」ことしか言っていない**
    ——打ち間違いのまま変換して確定しても同じ記録が残る（48-LB
    自身がそう書いている）。**在り得ない並びなら、記録は「本人が
    選んだ」の証拠にならない。**

    床（実績20以上）を置いた理由は **48-IS の化け（かぎ各国・
    漢字近い）が2語の組だったから**。**語の組み立て（48-LA）は
    2語の組ではない**——読みを語で敷き詰める別の道で、受け入れは
    48-MZ/48-ND で書かれ方まで見る。**この道にだけ床を外した。**

    実測: 初期は readcheck/fpcheck/seedcheck/紫/画面20行 **すべて差0**。
    育ちの実機メモは **1行だけ・しかも的**（`に有力ミス → 入力ミス`）。
    うにさんの画面20行は **◎4 → ◎5**。

    **この項目は途中の形だった。** 同じ日にうにさんから
    「**`ime_readings`（本人が確定した記録）の守りが想定外です**」と
    正され、**門ごと取り除いた**（項目48-NQ）。ここで見張るのは
    「もう残っていないこと」。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    print('--- 項目48-NP（打った記録は組み立てに掛けない） ---')
    src = open('corrector.py', encoding='utf-8').read()
    check('組み立ての受け皿から記録の床を外した',
          'if best is None and assemble:' in src, True)
    # **48-NQ で門ごと取り除いた**（同じ日・うにさんの
    # 「`ime_readings` の守りが想定外です」）。48-NP は
    # 「組み立ての道にだけ掛けない」という**途中の形**だった。
    check('門はもう残っていない（48-NQ で全部外した）',
          '_ime_same' in src, False)
    return all_ok


def test_ime_record_is_not_a_gate_48nq():
    """
    **打った読みの記録（`ime_readings`）を、補正を止める門には使わない**
    （項目48-NQ・2026-09-01・うにさんの指定）:

        「**`ime_readings`（本人が確定した記録）の守りが想定外です。
          一度打って打ち直したものは、自動の補正判断として記録
          します。学習メニューの補正の判断に登録される認識です。
          あとから手動で解除できなければ困る類いです。
          手動で編集のない入力履歴は同音異義語などに用いられる
          だけです。**」

    **設計を取り違えていた。** 「本人が確定した」の記録は
    **`decisions`（補正の判断）**のほう——学習メニューに出て、
    **あとから手動で解除できる**。置換の最終検査で
    `decisions.blocks(...)` が見ている（そこは今までどおり）。

    `ime_readings` は**手動で編集のない入力履歴**にすぎない。
    使い道は**同音異義語などの手がかり**だけで、
    `kanji_guess._with_ime_readings` が打った読みを候補の**先頭に
    置く**（設計25(乙)）——そちらは残す。

    48-IS/48-LB の門（打った読みが解析の読みと同じなら触らない／
    丸ごと1語・実績20以上だけ受け入れる）は**外して測ったら1行も
    動かなかった**（育ちの実機メモ0行・readcheck も同じ）。
    守っていたはずの `鍵括弧`・`漢字塊` は、いま **48-ME（できあがった
    塊の入口）**ほかが守っている。**もう要らない門だった。**
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    print('--- 項目48-NQ（打った記録は門にしない） ---')
    src = open('corrector.py', encoding='utf-8').read()
    check('門はもう無い', '_ime_same' in src, False)
    check('本人確定・丸ごと20未満 の断りも無い',
          '本人確定の記録・丸ごと20未満' in src, False)
    # **同音異義語の手がかりとしては残す**（設計25(乙)）
    ksrc = open('kanji_guess.py', encoding='utf-8').read()
    check('打った読みを候補の先頭に置く道は残っている',
          'def _with_ime_readings' in ksrc, True)
    check('差し口も残っている',
          'def set_ime_readings_provider' in ksrc, True)
    # **本当の「本人が確定した」は decisions**（手動で解除できる）
    check('置換の最終検査で decisions を見ている',
          'decisions.blocks(original, new_surface)' in src, True)
    return all_ok


def test_adverb_ni_dangling_48nr_48ns():
    """
    **副詞＋に の後ろには用言が来る**（項目48-NR／48-NS・2026-09-01・
    うにさんの指定）:

        「『そのままに市内』に焦点を当てます。**そのまま：副詞。
          に：格助詞。後ろに来るべき品詞は、主に動詞（または
          動詞句）**。『そのままに』全体が文中で副詞（連用修飾語）
          として機能するため、原則として後ろには動詞（用言）が
          配置されます。」

        そのままに**市内** → そのままに**しない**

    **素直に「に の後ろは用言」とすると反例が多い**（実機メモで実測）:

        完全に別物 ／ 非常に困難 ／ 急に雨が降る ／ すぐに確認

    3つ重ねると、うにさんの的だけが残った（1,791行で **2件・誤爆0**）:

      (a) 前が**もともとの副詞**（副詞:一般／副詞:助詞類接続）。
          `完全``非常``急` は 名詞:形容動詞語幹 なので外れる
      (b) 後ろの名詞が**動詞句になれない**
          （`確認``完了` はサ変＝述語になる。`市内` はならない）
      (c) **その先に用言が1つも無い**＝修飾する相手が居ない
          （`実際に横**に並んで**`・`すぐに元**に戻す**` は自然）

    直し（48-NS）は 48-NK と同じ向き＝**漢字をかなに開き戻す**。
    証拠は「開くと**用言が現れる**」——`市内`(しない) を開くと
    `し`（動詞）＋`ない`（助動詞）になる。**同音異義語を文法が裁く。**

    実測: 初期・育ちとも readcheck/fpcheck/seedcheck/紫 **すべて差0**、
    実機メモは**2行だけ・両方が的**、画面20行は **◎5 → 6**
    （沈黙 10 → 9）。
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

    def spans_of(pairs):
        out, pos = [], 0
        for sf, ps in pairs:
            out.append((pos, pos + len(sf), (sf, ps, sf, pos,
                                             pos + len(sf), True)))
            pos += len(sf)
        return out

    print('--- 項目48-NR/NS（副詞＋に の後ろは用言） ---')
    check('そのままに|市内 は異様',
          O.adverb_ni_dangling(spans_of([
              ('そのまま', '副詞:一般'), ('に', '助詞:副詞化'),
              ('市内', '名詞:一般')]), 1), True)
    check('そのままに|し|ない は異様でない（用言が在る）',
          O.adverb_ni_dangling(spans_of([
              ('そのまま', '副詞:一般'), ('に', '助詞:格助詞:一般'),
              ('し', '動詞:自立'), ('ない', '助動詞')]), 1), False)
    check('すぐに|確認 は異様でない（サ変＝述語になる）',
          O.adverb_ni_dangling(spans_of([
              ('すぐ', '副詞:助詞類接続'), ('に', '助詞:副詞化'),
              ('確認', '名詞:サ変接続')]), 1), False)
    check('完全に|別物 は異様でない（前が形容動詞語幹）',
          O.adverb_ni_dangling(spans_of([
              ('完全', '名詞:形容動詞語幹'), ('に', '助詞:副詞化'),
              ('別物', '名詞:一般')]), 1), False)
    check('すぐに|元|に|戻す は異様でない（先に用言が在る）',
          O.adverb_ni_dangling(spans_of([
              ('すぐ', '副詞:助詞類接続'), ('に', '助詞:副詞化'),
              ('元', '名詞:一般'), ('に', '助詞:格助詞:一般'),
              ('戻す', '動詞:自立')]), 1), False)

    src = open('corrector.py', encoding='utf-8').read()
    check('直しの道が在る（48-NS）', 'def _open_adv_ni_noun' in src, True)
    check('判定は oddness に任せる（2度書かない）',
          '_odd_ns.adverb_ni_dangling(spans, i)' in src, True)
    check('開くと用言が現れることを見る',
          "q.startswith('動詞') or q.startswith('形容詞')" in src, True)
    check('同じ口（_kv）に載せている',
          'for _an in _open_adv_ni_noun(line, tokenize_fn):' in src, True)
    return all_ok


def test_infl_connection_48nt():
    """
    **活用形の接続を異様判定に使う**（項目48-NT・2026-09-01）。

    うにさんの指定:

        「**今回のような品詞の組み合わせの判定は、AIが判断できる
          はずです。異様さとは、品詞の文法が間違っていることが
          大半だと思われます。**」

    **品詞だけでは足りない**——`書け`（仮定形）と `食べ`（連用形）は
    どちらも `動詞:自立` なのに、後ろに来られるものが違う。
    `make_tokenizer` の**7つ目に活用形**を通した。

    **厳密に決まるものだけ**を入れる（連用形・基本形は後ろが広い）:

        未然形系 → 助動詞・**動詞:接尾**（れる/せる）・記号
        仮定形   → 助詞:接続助詞（ば）。**用言のときだけ**
                   （助動詞の たら・なら は後ろが自由）
        命令形   → **入れない**（`とはいえ存在` で誤爆した）

    当たり: `ほせ|い`(ほせい)・`こ|て`(おくゆくこてい)・
    `かいせ|きか`(かいせきかせなかせく)・`そも|もそ`。

    **閉じた品詞の表（連体詞・接頭詞）は測って捨てた**——40件の
    外れが全部誤爆（`お|解り` は尊敬語で正しい・`同じ|です` も正しい）。
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

    def t(sf, pos, form=''):
        return (sf, pos, sf, 0, len(sf), True, form)

    print('--- 項目48-NT（活用形の接続） ---')
    check('ほせ（未然レル接続）| い（名詞） は異様',
          O.infl_mismatch(t('ほせ', '動詞:自立', '未然レル接続'),
                          t('い', '名詞:一般')), True)
    check('さ（未然レル接続）| れ（動詞:接尾） は異様でない',
          O.infl_mismatch(t('さ', '動詞:自立', '未然レル接続'),
                          t('れ', '動詞:接尾')), False)
    check('書か（未然形）| ない（助動詞） は異様でない',
          O.infl_mismatch(t('書か', '動詞:自立', '未然形'),
                          t('ない', '助動詞')), False)
    check('書け（仮定形）| ば は異様でない',
          O.infl_mismatch(t('書け', '動詞:自立', '仮定形'),
                          t('ば', '助詞:接続助詞')), False)
    check('書け（仮定形）| 存在（名詞） は異様',
          O.infl_mismatch(t('書け', '動詞:自立', '仮定形'),
                          t('存在', '名詞:サ変接続')), True)
    check('助動詞の仮定形（たら）の後ろは自由',
          O.infl_mismatch(t('たら', '助動詞', '仮定形'),
                          t('多重', '名詞:一般')), False)
    check('連用形は見ない（後ろが広すぎる）',
          O.infl_mismatch(t('食べ', '動詞:自立', '連用形'),
                          t('物', '名詞:一般')), False)
    check('口語の終助詞は見ない（知らなーい）',
          O.infl_mismatch(t('知ら', '動詞:自立', '未然形'),
                          t('なー', '助詞:終助詞')), False)
    check('活用形が無い形（janome 無し）は必ず False',
          O.infl_mismatch(('ほせ', '動詞:自立', 'ほせ', 0, 2, True),
                          ('い', '名詞:一般', 'い', 2, 3, True)), False)

    src = open('corrector.py', encoding='utf-8').read()
    check('解析の語に**7つ目の活用形**を通している',
          "getattr(t, 'infl_form', '') or ''" in src, True)
    osrc = open('oddness.py', encoding='utf-8').read()
    check('判定は oddness に1つだけ（2度書かない）',
          osrc.count('def infl_mismatch') == 1, True)
    import ast
    odd_fn = next(n for n in ast.parse(osrc).body
                  if isinstance(n, ast.FunctionDef) and n.name == 'is_odd_run')
    odd_calls = {n.func.id for n in ast.walk(odd_fn)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    check('is_odd_run から呼んでいる',
          {'infl_mismatch', 'suffix_then_yougen'} <= odd_calls, True)
    check('**印を位置順にそろえて出す**（重なりの併合が崩れる）',
          'out.sort(key=lambda t: (t[2], t[3]))' in osrc, True)
    return all_ok


def test_known_kanji_tail_core_48nu():
    """
    **後ろが「漢字で書く既知語」なら、その手前も芯にする**
    （項目48-NU・2026-09-01）。

    `おくゆくこてい` は末尾の剥がしが貪欲すぎて `くこてい` を語尾と
    みなし、芯が `おくゆ` になっていた。残る `くこてい` は
    **既知語 `こてい`(固定) の1字手前から始まる**——語尾ではなく
    **語の途中を切っている**。そこから直すと「終わりの字を保つ」の
    制限と噛み合って `おゆ`(お湯) に削られ、**`おゆくこてい` に
    化けていた**（うにさんの画面18行目・育ちの実機メモ）。

    やることは3つ:

      (1) **後ろが漢字で書く既知語なら、その手前を芯に足す**
          （`おくゆく` → `おくゆき`＝奥行）
      (2) **その既知語の途中で切れる芯は落とす**（`おくゆ`）
      (3) 後ろがそれ自体で1つの語なら、**「終わりの字を保つ」は
          掛けない**（あの制限は「芯が語幹の途中で切れている」
          ことが前提。`あらゆ`＋`る`）

    **境目にしてよいのは「漢字で書く語」だけ**——`_known`（実績2
    以上）だけで開けたら2つ壊した（測って絞った）:

        こてい   → **固定**(99)   漢字で書く。境目にしてよい
        どうして → どうして(35)   かなで書く副詞。**境目にしない**
                   （`たぶいどうして` → `ぶたいどうして` に壊した）
        くみす   → くみす(4)      かなで書く動詞。**境目にしない**
                   （`にゅうりょくみす` → `入力くみす` に壊した）

    **元の注記は「逆向きはやって壊したのでやめた」と言っていた**が、
    壊れた理由も注記自身が書いていた——「前側は語の途中から始まって
    いることが多く（**直前の漢字の送り仮名**）」。つまり壊したのは
    `after_kanji` のときだけで、族ごと捨てる理由ではなかった。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    print('--- 項目48-NU（漢字で書く既知語で切る） ---')
    src = open('corrector.py', encoding='utf-8').read()
    check('境目は「漢字で書く語」だけ',
          'def _known_kanji_word(frag):' in src, True)
    check('実績2以上＋漢字の表記を見る',
          "any(is_kanji(c) for c in (en['surface'] or ''))" in src, True)
    check('**独立したかな連続のときだけ**開ける（送り仮名は信用しない）',
          'for i in range(min_len, n - 2):' in src
          and '_known_kanji_word(window[i:])' in src, True)
    check('既知語の途中で切れる芯は落とす',
          'out = [(x, e) for (x, e) in out if e >= _known_tail_at]'
          in src, True)
    check('後ろが1語なら「終わりの字を保つ」は掛けない',
          'and not _rest_is_own_word(rest, store):' in src, True)
    check('その助けは3字以上・実績2以上',
          'if not rest or len(rest) < 3:' in src, True)

    import corrector as C

    class _S:
        def __init__(self, d):
            self.d = d

        def lookup(self, w):
            return self.d.get(w, [])

    st = _S({'こてい': [{'surface': '固定', 'count': 99}],
             'どうして': [{'surface': 'どうして', 'count': 35}],
             'くみす': [{'surface': 'くみす', 'count': 4}]})
    cores = C.window_cores('おくゆくこてい', st, after_kanji=False)
    check('おくゆく が芯に出る', (0, 4) in cores, True)
    check('おくゆ（既知語の途中）は落ちる', (0, 3) in cores, False)
    cores2 = C.window_cores('たぶいどうして', st, after_kanji=False)
    check('たぶい は芯にしない（どうして はかなで書く語）',
          (0, 3) in cores2, False)
    cores3 = C.window_cores('おくゆくこてい', st, after_kanji=True)
    check('直前が漢字なら開けない（送り仮名は語の途中）',
          (0, 4) in cores3, False)
    check('_rest_is_own_word: こてい は語',
          C._rest_is_own_word('こてい', st), True)
    check('_rest_is_own_word: 2字は語とみなさない',
          C._rest_is_own_word('てい', st), False)
    return all_ok


def test_compound_words_48nv_48nw():
    """
    **複合辞は1語として扱う**（項目48-NV）と、**読みの注記の中では
    活用形の接続を見ない**（項目48-NW）。2026-09-01・うにさんの指定:

        「**とはいえ、の4文字で接続詞判定するべきです。**
          ・と ➔ 格助詞（引用）・は ➔ 副助詞
          ・いえ ➔ 動詞「言う」の仮定形
          元々は『〜と言うとしても』という慣用フレーズが、1つの
          決まった繋ぎ言葉として定着したため、現代では単体で
          『接続詞』として扱われています」

    解析器は `とはいえ` を **と／は／いえ(動詞・命令ｅ)** に割り、
    画面の「－ 品詞判定 －」に**フィラー**と出していた。

    **1語だけの手当てではない。** IPAdic 自身が `だからといって`・
    `したがって`・`にあたって`・`ともあれ`・`要するに` を**すでに
    1語で登録している**。ここはその**抜けを埋める表**。

    載せる決まりは3つ——(あ) 全体が1つの接続詞・助詞として働く／
    (い) IPAdic が割ってしまう／(う) **割れた読みのほうが正しい場面が
    無い**。(う) で外したもの: `をもって`（ペンをもって書く＝持って）・
    `というのは`（AというのはBだ）・`にせよ` 単体（参考にせよ）。

    **掛ける所は3つ**（学び22）:
      corrector._from_janome ／ corrector._fallback ／
      **explain._tokens_for**（画面の品詞判定。ここは
      `morphology.tokenize` を**直に呼ぶ**ので、補正の道だけに
      掛けると欄だけ と／は／いえ のまま残る）
    判定（どこからどこが複合辞か）は **`compound_ranges` ただ1つ**。

    48-NW は 48-NT の受け皿——`精肉（**せい**にく）` のような
    **読みの注記**の中では解析がほぼ必ず壊れるので、活用形の接続を
    見ない。判定は `corrector.is_reading_gloss`（48-LN）を借りる。
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

    print('--- 項目48-NV（複合辞は1語） ---')
    check('とはいえ が表に在る（うにさんの指定）',
          C.COMPOUND_FUNCTION_WORDS.get('とはいえ'), '接続詞')
    check('にせよ 単体は載せない（参考にせよ＝動詞）',
          'にせよ' in C.COMPOUND_FUNCTION_WORDS, False)
    check('をもって は載せない（ペンをもって＝持って）',
          'をもって' in C.COMPOUND_FUNCTION_WORDS, False)
    check('というのは は載せない（AというのはBだ）',
          'というのは' in C.COMPOUND_FUNCTION_WORDS, False)
    check('触らない語にも合流している（名簿は1つ）',
          C.is_protected_word('とはいえ'), True)

    # compound_ranges は表層の並びだけを見る（形を知らない）
    check('と/は/いえ → 0..2 が とはいえ',
          C.compound_ranges(['と', 'は', 'いえ', '存在']),
          [(0, 2, 'とはいえ')])
    check('1語で来ているものは繋ぎ直さない',
          C.compound_ranges(['とはいえ', '存在']), [])
    check('いちばん長い一致を採る',
          C.compound_ranges(['いずれ', 'に', 'し', 'て', 'も']),
          [(0, 4, 'いずれにしても')])
    check('語の境目に合わないものは繋がない',
          C.compound_ranges(['とはい', 'え存在']), [])

    # 繋ぎ方（要素数は入力に合わせる）
    def t7(sf, pos, rd, s, e, k=True, inf=''):
        return (sf, pos, rd, s, e, k, inf)

    got = C.merge_compound_words([
        t7('と', '助詞:格助詞:引用', 'ト', 0, 1),
        t7('は', '助詞:係助詞', 'ハ', 1, 2),
        t7('いえ', '動詞:自立', 'イエ', 2, 4, True, '命令ｅ'),
        t7('存在', '名詞:サ変接続', 'ソンザイ', 4, 6)])
    check('繋いだ語は 接続詞', got[0][1], '接続詞')
    check('位置は 0-4（画面の印がここに乗る）', (got[0][3], got[0][4]), (0, 4))
    check('読みは繋げたもの', got[0][2], 'トハイエ')
    check('**活用形は空**（命令ｅ を残さない）', got[0][6], '')
    check('7要素のまま返る', len(got[0]), 7)
    check('後ろの語はそのまま', got[1][0], '存在')

    got6 = C.merge_compound_words([
        ('と', '助詞', 'と', 0, 1, True),
        ('は', '助詞', 'は', 1, 2, True),
        ('いえ', '動詞', 'いえ', 2, 4, True)])
    check('6要素の道では6要素のまま返る（janome 無しの印を壊さない）',
          len(got6[0]), 6)

    src = open('corrector.py', encoding='utf-8').read()
    check('janome の道に掛けている',
          'return merge_compound_words(out)' in src, True)
    check('janome の無い道にも掛けている（学び22）',
          src.count('return merge_compound_words(out)') == 2, True)
    esrc = open('explain.py', encoding='utf-8').read()
    check('**画面の品詞判定にも掛けている**（学び22）',
          'compound_ranges' in esrc, True)
    check('画面側でも活用形は空にする',
          "out[_a:_b + 1] = [(_w, _CFW[_w], '', _w," in esrc, True)
    check('判定は corrector に1本だけ（48-GN）',
          src.count('def compound_ranges') == 1
          and 'def compound_ranges' not in esrc, True)

    print('--- 項目48-NW（読みの注記の中は見ない） ---')
    import oddness as O
    check('精肉（せいにく） の せ は注記の中',
          O.in_reading_gloss('精肉（せいにく）との区別', 3), True)
    check('注記の中ほどでも中と分かる',
          O.in_reading_gloss('同音異義語（どうおんいぎご）また', 8), True)
    check('括弧が閉じたあとは中でない',
          O.in_reading_gloss('精肉（せいにく）との区別', 9), False)
    check('括弧の前は中でない',
          O.in_reading_gloss('精肉（せいにく）との区別', 1), False)
    check('括弧の直前が漢字でなければ注記ではない',
          O.in_reading_gloss('ああ（せいにく）', 3), False)
    osrc = open('oddness.py', encoding='utf-8').read()
    check('活用形の輪に掛けている',
          'if in_reading_gloss(text, a_s):' in osrc, True)
    check('判定は 48-LN を借りている（2度書かない）',
          'from corrector import is_reading_gloss' in osrc, True)
    check('**命令形は入れない**（48-NX → **48-NZ(a) で撤去**。'
          '「後ろに自立語は来ない」は正しくない——頑張れ日本）',
          '命令ｅ' in osrc.split('_AFTER_INFL')[1].split('}')[0], False)
    return all_ok


def test_logical_pos_rules_48nx_48ny():
    """
    **論理的に正しい文法判定を重ねる**（項目48-NX・48-NY・2026-09-01・
    うにさんの指定）:

        「**実機メモなど、サンプル文字列の極一部です。ここで効果が
          なくても、実用時に効果がある想定でいるべきです。論理的に
          正しいものを重ねていくことが必要です。**」

    ——**ものさしの標本は世界の全部ではない。** 誤爆が0で、日本語
    文法として正しい規則なら、標本で当たりが0でも入れる。
    「効果のあるものだけ入れる」は**仕掛けを増やさない**ための決まりで
    あって、**文法そのものを入れない**理由にはしない。

    ### 48-NX 命令形の後ろは、助詞と記号だけ

        書け。／書け！   → 記号
        書けと言った     → 助詞:格助詞:引用
        書けよ           → 助詞:終助詞
        **書け本・書け行く → 異様**（自立語は直に続かない）

    48-NT では「`とはいえ存在` で誤爆する」ので外していた。
    その理由は **48-NV（複合辞を1語に）と 48-NW（読みの注記）で
    消えた**。実測でも誤爆0。

    ### 48-NY 接尾辞の直後に、自立の用言は来ない

        「『田部井号して』……**ここでは接尾辞と判定されています。
          接尾辞の次が接続助詞なのが異様です。**」

        田部井 / **号**(名詞:接尾:一般) / **し**(動詞:自立) / て

    接尾辞は前の語にくっついて名詞句を作るので、**助詞を伴って**
    文に入る。助詞を飛ばして用言に繋がることはない。

    **外すのは2つ**——(あ) サ変接続・助数詞・副詞可能ほかの細分類
    （3**回**行く・少し**ずつ**進める・速度**化**する）、
    (い) **数量表現の末尾**（`1行分開いていて` の `分` は
    `名詞:接尾:一般` で助数詞ではない。左へ辿って **数** に
    行き着くなら副詞的に使えるので外す。**測って見つけた**）。
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

    def sp(pairs):
        """(表記, 品詞[, 活用形]) の並びから spans を作る。"""
        out, pos = [], 0
        for it in pairs:
            sf, ps = it[0], it[1]
            inf = it[2] if len(it) > 2 else ''
            out.append((pos, pos + len(sf),
                        (sf, ps, sf, pos, pos + len(sf), True, inf)))
            pos += len(sf)
        return out

    def t(sf, ps, inf=''):
        return (sf, ps, sf, 0, len(sf), True, inf)

    osrc = open('oddness.py', encoding='utf-8').read()

    print('--- 項目48-NZ(a)（命令形は撤去した） ---')
    # **入れて、測って、撤去した**（同じ日に）。理由は「当たりが0
    # だから」ではなく、**私の書いた文法が間違っていたから**:
    #     頑張れ**日本**        ← 呼びかけ（呼格）。名詞が来る
    #     遅かれ**早かれ**壊れます ← 形容詞の命令形の慣用
    #     やめろ**ー**          ← 引き伸ばし
    #     宙に浮け**ない**      ← `浮け` は可能動詞。解析の取り違え
    # うにさんの決まりは「**論理的に正しいもの**を重ねる」であって
    # 「誤爆が測れなければ入れる」ではない。
    check('命令形は表に無い',
          any(k in osrc.split('_AFTER_INFL')[1].split('}')[0]
              for k in ('命令ｅ', '命令ｒｏ')), False)
    check('頑張れ|日本 は異様でない（呼びかけ）',
          O.infl_mismatch(t('頑張れ', '動詞:自立', '命令ｅ'),
                          t('日本', '名詞:固有名詞:地域:国')), False)

    print('--- 項目48-NZ(b)(c)(d)（未然形の誤爆を潰した） ---')
    check('(b) 助動詞の未然形は見ない（そうだろー。）',
          O.infl_mismatch(t('だろ', '助動詞', '未然形'),
                          t('ー', '名詞:一般')), False)
    check('(b) 動詞の未然形は見る（ほせ|い）',
          O.infl_mismatch(t('ほせ', '動詞:自立', '未然レル接続'),
                          t('い', '名詞:一般')), True)
    check('(c) 文語の 未然形＋ば は異様でない（急がば回れ）',
          O.infl_mismatch(t('急が', '動詞:自立', '未然形'),
                          t('ば', '助詞:接続助詞')), False)
    check('(d) 直前が「数」なら見ない（1つも動いていない）',
          O.infl_mismatch(t('つも', '動詞:自立', '未然ウ接続'),
                          t('動い', '動詞:自立'),
                          t('1', '名詞:数')), False)
    check('(d) 直前が数でなければ見る',
          O.infl_mismatch(t('つも', '動詞:自立', '未然ウ接続'),
                          t('動い', '動詞:自立'),
                          t('門', '名詞:一般')), True)

    print('--- 項目48-NY（接尾辞の直後に用言は来ない） ---')
    # うにさんが名指しした `田部井号して` は、**サ変の「する」**が
    # 後ろなので **48-JC（既にある判定）の持ち場**。48-NY は
    # そこへ重ねない（項目48-GN「同じ判定を2度書かない」）——
    # 重ねたら `無効化して` を壊した（測って踏んだ）。
    # **印は 48-JC のほうが立てている**（下で確かめる）。
    check('号|し は 48-NY では見ない（サ変は 48-JC の持ち場）',
          O.suffix_then_yougen(sp([('田部井', '名詞:固有名詞:人名:姓'),
                                   ('号', '名詞:接尾:一般'),
                                   ('し', '動詞:自立')]), 1), False)
    check('**それでも 田部井号して には印が立つ**（48-JC が言う）',
          bool(O.is_odd_run('田部井号して', lambda _t: [
              ('田部井', '名詞:固有名詞', '', 0, 3, True),
              ('号', '名詞:接尾', '', 3, 4, True),
              ('し', '動詞:自立', '', 4, 5, True),
              ('て', '助詞:接続助詞', '', 5, 6, True)])), True)
    check('さん（接尾:人名）| 行く は異様',
          O.suffix_then_yougen(sp([('田中', '名詞:固有名詞:人名:姓'),
                                   ('さん', '名詞:接尾:人名'),
                                   ('行く', '動詞:自立')]), 1), True)
    check('都（接尾:地域）| 行く は異様',
          O.suffix_then_yougen(sp([('東京', '名詞:固有名詞:地域:一般'),
                                   ('都', '名詞:接尾:地域'),
                                   ('行く', '動詞:自立')]), 1), True)
    check('**さ（接尾:特殊）| 増す は異様でない**（48-NZ(e)。'
          '「高さ増す」「暑さ増す」は見出しの書き方でふつう）',
          O.suffix_then_yougen(sp([('高', '形容詞:自立'),
                                   ('さ', '名詞:接尾:特殊'),
                                   ('増す', '動詞:自立')]), 1), False)
    check('化（接尾:サ変接続）| する は異様でない',
          O.suffix_then_yougen(sp([('速度', '名詞:一般'),
                                   ('化', '名詞:接尾:サ変接続'),
                                   ('する', '動詞:自立')]), 1), False)
    check('回（接尾:助数詞）| 行く は異様でない（数量詞は副詞的）',
          O.suffix_then_yougen(sp([('3', '名詞:数'),
                                   ('回', '名詞:接尾:助数詞'),
                                   ('行く', '動詞:自立')]), 1), False)
    check('**1行分|開い は異様でない**（左へ辿ると 数 に行き着く）',
          O.suffix_then_yougen(sp([('1', '名詞:数'),
                                   ('行', '名詞:接尾:助数詞'),
                                   ('分', '名詞:接尾:一般'),
                                   ('開い', '動詞:自立')]), 2), False)
    check('**〜化して は見ない**（サ変の する は 48-JC が見る・48-GN）',
          O.suffix_then_yougen(sp([('無効', '名詞:形容動詞語幹'),
                                   ('化', '名詞:接尾'),
                                   ('し', '動詞:自立')]), 1), False)
    check('確認済み|送る は異様（数ではない）',
          O.suffix_then_yougen(sp([('確認', '名詞:サ変接続'),
                                   ('済み', '名詞:接尾:一般'),
                                   ('送る', '動詞:自立')]), 1), True)
    check('後ろが名詞なら見ない（複合名詞は作れる・48-NA）',
          O.suffix_then_yougen(sp([('田中', '名詞:固有名詞:人名:姓'),
                                   ('さん', '名詞:接尾:人名'),
                                   ('宅', '名詞:接尾:一般')]), 1), False)
    check('後ろが助詞なら見ない',
          O.suffix_then_yougen(sp([('田中', '名詞:固有名詞:人名:姓'),
                                   ('さん', '名詞:接尾:人名'),
                                   ('が', '助詞:格助詞:一般')]), 1), False)

    check('同じ輪に載せている（判定を2度書かない）',
          'infl_mismatch(a, b, _prev) or suffix_then_yougen(spans, i)'
          in osrc, True)
    check('数量表現を外す道が在る',
          "if pp.startswith('名詞:数'):" in osrc, True)
    check('**同じ対を二重に出さない**（語の対の表と重なる）',
          'if _one not in out:' in osrc, True)
    return all_ok


def test_chunk_near_by_method_48oa():
    """
    **開いた読みに手を当てるときも、入力方式の隣接キーで見る**
    （項目48-OA・2026-09-01）。

    うにさんの一覧 `たぶいごうして ⇒ たぶいどうして` の `ご→ど` は
    **費用1.4**で、この道の門（1.0）にちょうど落ちていた。

    2つ直した:

      (1) **入力方式を渡す**——48-NJ'（うにさんの指定「ローマ字入力は
          ローマ字の隣接キーを見てください。かな入力の隣接は見ません」）
          を `vocabulary.find_known_readings_flex` には掛けたのに、
          **開いた読みに手を当てるこの道には掛け忘れていた**（学び22）
      (2) **幅を 1.0 → 1.4**。芯の再構築は費用3.0まで見ているので、
          1手の置き換えに 1.4 は狭いほうの数字

    **測って差0**（初期 readcheck 1949/99・1948/105 ／ fpcheck 0/0 ／
    seedcheck 39/40 壊し0 ／ 実機メモ 255/250 ／ 紫117 ／
    画面20行 ◎6——全部据え置き）。
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

    print('--- 項目48-OA（開いた読みの手当ても入力方式で） ---')
    # **幅は 1.4 に広げて、同じ日に 1.0 へ戻した**。
    # readcheck・fpcheck・seedcheck・紫は全部差0だったが、
    # **実機メモの dump を突き合わせたら1行壊していた**——
    # `引き月資料 → 引き継ぎ資料`（正）が **`引き抜き資料`**（誤）に。
    # `ひきつきしりょう` は**濁点1つ**（つき→つぎ）で `引き継ぎ` に
    # 届くのに、幅を広げると **つ→ぬ**（1.4）で `引き抜き` が入り、
    # **実績で勝ってしまう**（候補に費用の順が無いのが元）。
    # **件数だけ見て「差0」と言ったのが誤り**（変わった行は255で
    # 同じだったが中身が入れ替わっていた・48-NL と同じ型）。
    # **幅は 1.4**（項目48-OQ(e)・2026-09-03）。1.0 へ戻してあったのは
    # 「候補に費用の順が無い」ため（`引き月資料 → 引き抜き資料`）。
    # `_fixes` を**安い順**に並べたので、濁点(0.3)が隣接キー(1.4)に
    # 勝つ形になり、広げても守れる
    check('幅は 1.4（費用の順を付けてから広げた・48-OQ(e)）',
          C._CHUNK_NEAR_MAX, 1.4)
    src = open('corrector.py', encoding='utf-8').read()
    check('入力方式を渡している',
          '_near(ch, input_method=input_method)' in src, True)
    check('幅は定数から引く',
          'if alt != ch and d <= _CHUNK_NEAR_MAX:' in src, True)
    try:
        from kana_layout import nearby_candidates as near
        d = dict(near('ご', input_method='romaji')).get('ど')
        check('ご→ど は 1.4（**いまの門 1.0 には入らない**。'
              '費用の順を付けるのが次の宿題）', d, 1.4)
    except Exception as e:
        check('kana_layout が読める', str(e), '')
    return all_ok


def test_naadj_two_faces_48nm2():
    """
    **ナ形容詞の語幹の「2つの顔」**（項目48-NM'・2026-09-01・
    うにさんの指定）:

        「**元気**の2つの顔
          ・**ナ形容詞の語幹**の顔——元気**な**人／元気**に**遊ぶ
          ・**名詞**の顔——元気**を**出す／元気**が**ある／元気**の**源
          『元気出して』は『元気**を**出して』から**格助詞が省略された
          形**。**AIならここまで行けるはずです。アプリの判定がすべてと
          思わないで。**」

    **格助詞は落とせる。活用語尾は落とせない。**
    `静か歩く` は `静かが/静かを歩く` がどちらも成り立たないので、
    落ちたのは語尾「に」しかない＝**異様**。

    ### ★ 直す前の姿（実測）——**いちばん悪い組み合わせだった**

        静か歩く           紫 **[]**       ← うにさんの的が印にならない
        アクティブなっていない 紫 **[]**       ← 同上
        元気出して！        紫 [(0,4)]      ← **誤爆**
        品薄続く           紫 [(0,4)]      ← **誤爆**
        大変助かる         紫 [(0,5)]      ← **誤爆**（副詞の顔）

    的が2つとも落ちていたのは、`is_odd_run` の2枚の壁
    （「右は漢字始まり」「左が漢字終わりで右が名詞」）に当たって
    **`can_join` まで届いていなかった**から。48-NM の注記の
    「実機メモでは増減0」は、判定が無いのではなく**道が無かった**。

    ### 直したこと

      (1) 一律 False をやめ、**表に載っている語だけ**にした
          （`_NAADJ_STEM_ONLY`・121語）。**掛ける側**に持つので、
          知らない語は**黙る**（壊さない ＞ 直る）
      (2) **「なる」の前だけは名簿が要らない**（`_NAADJ_NARU`）——
          アクティブ**に**なっていない・品薄**に**なっている
      (3) `is_odd_run` の壁を**この形だけ**迂回させた
      (4) **48-NN（に を入れる直し）も同じ判定を呼ぶ**ようにした
          ——あちらが**自分の品詞の見方を別に持っていた**ので、
          印を直しても `元気出して！` を `元気に出して！` に
          壊していた（実測。48-GN そのもの）
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

    print('--- 項目48-NM\'（ナ形容詞の語幹の2つの顔） ---')
    N = '名詞:形容動詞語幹'
    check('静か|歩く は異様（表に在る）',
          O.naadj_stem_bare('静か', N, '歩く', '動詞:自立'), True)
    check('**元気|出し は異様でない**（名詞の顔・を落ち）',
          O.naadj_stem_bare('元気', N, '出し', '動詞:自立'), False)
    check('**品薄|続く は異様でない**（名詞の顔）',
          O.naadj_stem_bare('品薄', N, '続く', '動詞:自立'), False)
    check('**大変|助かる は異様でない**（副詞の顔）',
          O.naadj_stem_bare('大変', N, '助かる', '動詞:自立'), False)
    check('**散々|言わ は異様でない**（副詞の顔）',
          O.naadj_stem_bare('散々', N, '言わ', '動詞:自立'), False)
    check('アクティブ|なっ は異様（**なる の前は名簿が要らない**）',
          O.naadj_stem_bare('アクティブ', N, 'なっ', '動詞:自立'), True)
    check('カタカナ語でも なる 以外は黙る（ラフ|描く）',
          O.naadj_stem_bare('ラフ', N, '描く', '動詞:自立'), False)
    check('容易|なら は異様でない（文語）',
          O.naadj_stem_bare('容易', N, 'なら', '動詞:自立'), False)
    check('上品|ぶる は異様でない',
          O.naadj_stem_bare('上品', N, 'ぶる', '動詞:自立'), False)
    check('後ろが名詞なら見ない（複合名詞は作れる・48-NA）',
          O.naadj_stem_bare('静か', N, '部屋', '名詞:一般'), False)
    check('語幹でなければ見ない',
          O.naadj_stem_bare('確認', '名詞:サ変接続', 'し', '動詞:自立'), False)

    check('表は121語', len(O._NAADJ_STEM_ONLY), 121)
    for w in ('静か', '有力', '簡単', '綺麗', '大切'):
        check(f'表に {w} が在る', w in O._NAADJ_STEM_ONLY, True)
    for w in ('元気', '品薄', '大変', '十分', '無理', '必要', '便利',
              'アクティブ', 'ラフ', 'ダメ'):
        check(f'表に {w} は**無い**', w in O._NAADJ_STEM_ONLY, False)

    osrc = open('oddness.py', encoding='utf-8').read()
    check('can_join から呼んでいる',
          'if naadj_stem_bare(a, ap, b, bp):' in osrc, True)
    check('**is_odd_run の壁を迂回させている**',
          'if naadj_stem_bare(a_sf, ap, b_sf, bp):' in osrc, True)
    csrc = open('corrector.py', encoding='utf-8').read()
    check('**48-NN も同じ判定を呼ぶ**（品詞の見方を2度書かない）',
          'if not _odd_nn.naadj_stem_bare(a[0], ap, b[0], bp):'
          in csrc, True)
    return all_ok


def test_mark_drop_reverts_48og():
    """
    **印を落としただけで何も直せなかったら、元に戻す**
    （項目48-OG・2026-09-02）。

    `normalize_marks` は、かなに付けられない濁点・半濁点を
    「濁点キーの誤打」として**落とす**。そこから先で語に届けば
    正しい後始末だが、**届かなかったときは落とした形をそのまま
    答えにしていた**:

        硬い゛に取り掛かる → **硬いに取り掛かる**
          （本来は かたい゛ → かだい → 課題に取り掛かる。
            `課題` が初期語彙に無いので、そこまでは届かない）
        フア゜ラネタリウム → **フアラネタリウム**

    ★★「**判断がつかないものは触らない**（色を付けて知らせるだけに
    する）」に反していた。落とす見立ては「かなを打った直後に濁点キーを
    叩いた」というもので、**その先で語に届いてはじめて裏が取れる**。

    **印は打った人が打ったもの**なので、消すと
      ・打った人の文が変わる（壊さない ＞ 直る）
      ・**次に直すための材料が消える**（どこが変だったか分からない）

    **合成は今までどおり**（`たんこ゛の → たんごの`）——合成が1つでも
    起きていれば「落としただけ」ではないので、この道に入らない。
    `もじ゛つ → 文字列`（48-JP）・`。゛しじとう → 。゛しじょう` も無傷。

    実測: 初期 readcheck 1949/99・1948/105 ／ fpcheck 0/0 ／
    seedcheck 39/40 壊し0 ——**全部据え置き**。
    実機メモは**4行だけ・全部が「消すのをやめた」ぶん**。
    画面の一覧は**化け 2 → 1**。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    print('--- 項目48-OG（落としただけなら元に戻す） ---')
    src = open('corrector.py', encoding='utf-8').read()
    check('落とした位置を受け取っている',
          'normalize_marks(line, dropped=_mark_dropped)' in src, True)
    check('**落としただけか**を見分けている',
          '_only_dropped = (_cut == normalized)' in src, True)
    check('落としただけ＆何も直せないなら戻す',
          "if _only_dropped and not inner['changed'] \\" in src, True)
    check('戻すときは changed を立てない',
          "'corrected': line,\n                'changed': False," in src, True)
    check('戻したときも紫は出す（気づきの印は残す）',
          "'odd_spans': _odd_spans_for_line(" in src, True)

    from morphology import normalize_marks
    d = []
    check('たんこ゛ は合成される（落としたのではない）',
          (normalize_marks('たんこ゛の', dropped=d), d), ('たんごの', []))
    d = []
    check('い゛ は落とされる（付けられない）',
          (normalize_marks('かたい゛に', dropped=d), len(d)), ('かたいに', 1))
    d = []
    check('記号の後ろの ゛ は落とさない（前がかなでない）',
          (normalize_marks('。゛しじとう', dropped=d), d),
          ('。゛しじとう', []))
    return all_ok


def test_index_face_48oj():
    """
    **項目48-OJ〜48-ON（2026-09-02・Fable）: 索引に2字漢語の帯と段、
    索引の顔で決める。**

    うにさん（2026-09-02）「そのような基本的な単語が見つからない場所が
    あってもよいのか」→ 語彙（count）には入れず、索引（世の中の語）に
    持つ。順位は AI の判断（`kango_tier.json`）。**段1がただ1つ**のとき
    だけ決める（段2で決めると 手動補正 → 主導性）。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    print('--- 項目48-OJ〜48-ON（索引の顔・段・開いた読みへの手） ---')
    src = open('corrector.py', encoding='utf-8').read()
    di = open('dict_index.py', encoding='utf-8').read()
    ji = open('janome_import.py', encoding='utf-8').read()
    bm = open('bundle_manifest.py', encoding='utf-8').read()

    check('族の決まりは janome_import.is_two_kanji_noun ただ1つ',
          'def is_two_kanji_noun(' in ji and 'is_two_kanji_noun' in di, True)
    check('索引は漢字2字名詞の費用上限と一般語分類を使う',
          'cost <= KANJI2_COST_LIMIT' in di and 'kango_tier.tier(surface) <= 2' in di, True)
    check('索引の並びは 段 → コスト',
          'pairs.sort(key=lambda cv: (_tier(cv[1]), cv[0], cv[1]))' in di, True)
    check('kango_tier.json は同梱の名簿に在る',
          "Item('kango_tier.json', 'kango_tier'" in bm, True)
    check('決めているのは _index_face 1つ', src.count('def _index_face('), 1)
    check('段1がただ1つのときだけ決める（段2では決めない）',
          'top = [s for t, s in tiers if t == 1]' in src, True)
    check('語彙に実績2以上が在れば決めない',
          "if any((e.get('count', 0) or 0) >= 2 for e in store.lookup(reading)):\n"
          "            return None" in src, True)
    check('錨は弱い先頭・count1 の漢語錨より先に索引の顔',
          '_face = _index_face(first, store, dict_index)' in src, True)
    check('48-MI（strict_anchor）からは呼ばない（切り替え CN_MI_INDEX のときだけ）',
          'if ((not strict_anchor or index_anchor) and not vocab_only' in src, True)
    check('(あ) は名詞に続く機能語で始まる尾だけ（48-ON）',
          'if _idx and not _noun_tail_start(text[ln1:]):' in src, True)
    # **48-RQ（2026-09-05）で狭い門を開けた**——語＋助詞＋語 は
    # 「手が生んだ助詞」（born）のときだけ。N2 の2件（打たれたままの
    # 助詞）はこの門で止まる
    check('語＋助詞＋語 は「手が生んだ助詞」のときだけ開ける（48-RQ）',
          'for _gap in (0, 1):' in src
          and 'if not born or ln1 not in born:' in src, True)
    # **2〜3字の先頭は「本人の語彙のカタカナ語」だけ開けた**
    # （項目48-OQ(b)・2026-09-03）。漢字の2〜3字は 48-ON で測って
    # 壊れた（ぶんうつ → 文打つ・外しょつする → 外施設する）ので、
    # **カタカナだけ**に絞ってある
    check('先頭は2字まで下りる（48-OQ(b)）',
          'for ln1 in range(min(10, n), 1, -1):' in src, True)
    check('短い先頭はカタカナ語か、2つ目が世の中のカタカナ語（48-OQ(b)/48-OR(c)）',
          "_short_kanji = _short and not all(is_katakana(_c) or _c == 'ー'"
          in src
          and 'if _short_kanji and piece != _world_katakana_piece(_frag):'
          in src, True)
    check("48-LA'（遅れた濁点）にも索引の顔",
          '_f = _index_face(v, store, dict_index)' in src, True)
    check('_peel_one_suffix の索引の顔は kango_ok のときだけ',
          'if dict_index is not None and kango_ok and not any(' in src, True)
    check('compose の索引の代替は帯を見ない（①が立っていない道）',
          'for s in _surfaces_no_band(dict_index, stem):' in src, True)
    check('帯を見ないのは compose・48-MI の門・(い) の辞書の先頭の3か所（helper 経由・定義1＋呼び手3）',
          src.count('_surfaces_no_band(dict_index, '), 4)
    check('索引が帯を持つ（dict_index._band）', 'self._band = band' in di, True)
    check('索引の版は 9（用言・活用形の読みを共有）', 'CACHE_VERSION = 9' in di, True)
    check('造語の道: 手を当てた読みの語幹は直し先が1語のときだけ（48-OJ）',
          'が本人の語彙に無く、直し先' in src, True)
    check('形容動詞語幹＋化 は1語（48-OK・2か所）',
          src.count('_na_adj_ka_word(f') >= 2, True)
    check('1字の ん は断片（48-OL）',
          "if sf == 'ん':\n                return True" in src, True)
    check('余分な隣のキー（48-OL）', "'余分な隣のキー'" in src, True)
    check('48-MI に索引の顔（48-OO・2026-09-03 に既定 ON・CN_MI_INDEX=0 で切る）',
          "index_anchor=(os.environ.get('CN_MI_INDEX')" in src
          and "!= '0'))" in src, True)
    check('印のキーの隣を開いた読みにも・2回重ね（48-OM）',
          "_add(r2, '同じ誤りの繰り返し（印の隣×2）', 2.0)" in src, True)
    check('_fixes の候補は費用の安い順（48-OQ(e)）',
          'key=lambda r: _cost.get(r, 9.9))' in src, True)

    import kango_tier
    check('kango_tier が読める', kango_tier.available(), True)
    check('課題=1・過大=2・参向=3',
          (kango_tier.tier('課題'), kango_tier.tier('過大'), kango_tier.tier('参向')),
          (1, 2, 3))
    check('効率=1・高率=2', (kango_tier.tier('効率'), kango_tier.tier('高率')), (1, 2))
    import json
    onk = json.load(open('kanji_onkun.json', encoding='utf-8'))['readings']
    check('音訓表に 巨(きょ)・移(い)',
          (onk.get('巨', {}).get('きょ'), onk.get('移', {}).get('い')), ('on', 'on'))

    import corrector as C
    check('名詞に続く機能語: に・から は通る',
          (C._noun_tail_start('になる'), C._noun_tail_start('から')), (True, True))
    check('名詞に続く機能語: こう（副詞）は通らない',
          C._noun_tail_start('こうになる'), False)
    check('かなの増えは文法のかなだけ: 解析が長く は通る',
          C._kana_growth_is_grammar('解析が長く'), True)
    check('かなの増えは文法のかなだけ: 昨年こうになる は通らない',
          C._kana_growth_is_grammar('昨年こうになる'), False)
    return all_ok


def test_pos_and_units_20260903():
    """
    **2026-09-03（項目48-OQ・48-OR・48-OS）**——うにさんの画面の
    `田部井号して`・`右田でブルクリック`・F2 の範囲。
    """
    all_ok = [True]

    def check(label, got, want):
        ok = got == want
        all_ok[0] = all_ok[0] and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import corrector as C
    import oddness as O
    import units as U

    print('--- 項目48-OQ（田部井号して の3つ＋順と費用） ---')
    src = open('corrector.py', encoding='utf-8').read()

    check('(a) 名詞に直付きした1字の漢字の接尾は断片',
          "_suffix_frags.add((_t[3], _t[4]))" in src
          and "if (t[3], t[4]) in _suffix_frags:" in src, True)
    check('(a) 左が数詞なら開かない',
          "_lp.startswith('名詞:数')" in src, True)
    check('(b) 先頭は2字まで下りる',
          'for ln1 in range(min(10, n), 1, -1):' in src, True)
    check('(b) 短い先頭はカタカナ語（漢字は 48-OR(c) の枝だけ）',
          "_short_kanji = _short and not all(is_katakana(_c) or _c == 'ー'"
          in src, True)
    check("(b') 短い先頭は組み立ての受け皿だけ（育ちで測って足した門）",
          'if _short and not short_head:' in src
          and 'vocab_only=vocab_only, short_head=True,' in src, True)
    check('(48-OR(c)) 世の中のカタカナ語は4字以上・組み立ての受け皿だけ',
          "if strict_anchor or vocab_only or not short_head or len(frag) < 4:"
          in src, True)
    check('(48-OR(b)) 余分な字に濁点',
          "_add(rd[:i] + _TYPO_DAKUTEN[u] + rd[i + 2:]," in src, True)
    check('(48-OR) 印と同じ並びを見る（断片の見立て）',
          '_odd.downgraded_tokens(toks, store, dict_index)' in src, True)
    check('(48-OR(c)) 印で決まらなければ連なりごと（開ける印が在るとき・12字まで）',
          'if not (_long_openable or _outside_broken):' in src
          and 'if _long_done or len(run) > 12:' in src, True)
    check("(48-OR(c')) 印の外にも読みの立たない語が在れば連なりごと",
          'for _ma, _mb in ([] if _outside_broken else _frag_marks):' in src,
          True)

    # **48-OO の受け皿(3)**——世の中がかなで書く語は変換しない
    check('世の中の費用: たくさん < 沢山（かなのまま）',
          C._table_cost('たくさん') < C._table_cost('沢山'), True)
    check('世の中の費用: 一番 < いちばん（変換する）',
          C._table_cost('一番') < C._table_cost('いちばん'), True)
    check('世の中の費用: 効率 < こうりつ・参考 < さんこう（変換する）',
          (C._table_cost('効率') < C._table_cost('こうりつ'),
           C._table_cost('参考') < C._table_cost('さんこう')), (True, True))
    check('48-MI にだけ掛ける（門の場所）',
          '# **世の中がその語をかなで書いているなら、かなのまま**' in src
          and src.count('_c_kana = _table_cost(run[:head_end])') == 1, True)

    # **48-OO の受け皿(1)**——読みの見出し
    check('読みの見出し: かんしん（関心、感心、歓心など）',
          C.is_reading_headword('かんしん（関心、感心、歓心など）です', 0, 4),
          True)
    check('言い添えは見出しではない: こうりつ（効率）',
          C.is_reading_headword('こうりつ（効率）を上げる', 0, 4), False)
    check('括弧が続かなければ見出しではない',
          C.is_reading_headword('かんしんがあります', 0, 4), False)

    # **48-OO の受け皿(2)**——濁点1つ違いの段1
    import kango_tier as _kt
    check('段1どうしは拮抗（会館 / 海岸）',
          (_kt.tier('会館'), _kt.tier('海岸')), (1, 1))
    check('相手が段2なら決める（感動 / 完投）',
          (_kt.tier('感動'), _kt.tier('完投')), (1, 2))
    check('(c) 元に無かったカタカナの例外は1か所',
          src.count('def _grown_katakana_is_own_word') == 1, True)
    check('(d) 開いた読みは解析の読みに近い順',
          'sorted(readings, key=lambda r: _reading_gap(r, _ar))' in src, True)
    check('(e) 手は費用の安い順',
          'key=lambda r: _cost.get(r, 9.9))' in src, True)
    check("(e') 脱字（打っていない字を足す）は隣接キーより高い",
          __import__('kana_layout').kana_repair_cost('あう', 'あいう', 1.5) > 1.5, True)
    check('(e) 幅は 1.4', C._CHUNK_NEAR_MAX, 1.4)

    # 編集距離（純粋関数）
    check('読みの隔たり: たべい → たぶい は1',
          C._reading_gap('たぶいごうして', 'たべいごうして'), 1)
    check('読みの隔たり: たべい → たぶせい は2',
          C._reading_gap('たぶせいごうして', 'たべいごうして'), 2)

    # 「する」の付き方（janome が要る。無ければ意見なし＝True）
    def _tok(parts):
        def fn(text):
            out, pos = [], 0
            for surf, p in parts:
                out.append((surf, p, surf, pos, pos + len(surf), True, ''))
                pos += len(surf)
            return out
        return fn

    check('タブ＋移動(サ変接続)＋して は通る',
          C._suru_attach_ok('タブ移動して', _tok(
              [('タブ', '名詞:一般'), ('移動', '名詞:サ変接続'),
               ('し', '動詞:自立'), ('て', '助詞:接続助詞')])), True)
    check('以降(副詞可能)＋して は通さない',
          C._suru_attach_ok('タブ以降して', _tok(
              [('タブ', '名詞:一般'), ('以降', '名詞:副詞可能'),
               ('し', '動詞:自立'), ('て', '助詞:接続助詞')])), False)
    check('名詞＋名詞＋する は後ろがサ変接続のときだけ',
          C._suru_attach_ok('タブ違法して', _tok(
              [('タブ', '名詞:一般'), ('違法', '名詞:形容動詞語幹'),
               ('し', '動詞:自立'), ('て', '助詞:接続助詞')])), False)
    check('単独の 安定して は通る（前に名詞が無い）',
          C._suru_attach_ok('安定して', _tok(
              [('安定', '名詞:形容動詞語幹'), ('し', '動詞:自立'),
               ('て', '助詞:接続助詞')])), True)

    # (f) 未然形＋打消の ん
    def _tok_infl(parts):
        def fn(text):
            out, pos = [], 0
            for surf, p, infl in parts:
                out.append((surf, p, surf, pos, pos + len(surf), True, infl))
                pos += len(surf)
            return out
        return fn

    check('つまらん（未然形＋ん）は説明が付く',
          C._kana_run_explained('つまらん', False, _tok_infl(
              [('つまら', '動詞:自立', '未然形'),
               ('ん', '助動詞', '基本形')])), True)
    check('未然形でなければ足さない（さんらん）',
          C._kana_run_explained('さんらん', False, _tok_infl(
              [('さん', '名詞:一般', ''), ('らん', '名詞:一般', '')])), False)
    check('活用形を見る（未然形でなければ足さない）',
          "== '未然形'" in src, True)

    print('--- 項目48-OR（固有名詞の判定は後段へ） ---')
    osrc = open('oddness.py', encoding='utf-8').read()
    check('落とすのは spans を作る1か所（定義1＋呼び手1）',
          osrc.count('_proper_noun_is_trusted(t, store, dict_index)'), 2)
    check('_NOUN_NG から固有名詞は外さない',
          "_NOUN_NG = ('固有名詞'" in osrc, True)
    check('相手は漢字始まり または 世の中のカタカナ語',
          'or _katakana_word_known(_other,' in osrc, True)

    class _T(object):
        def __init__(self, sf, pos, rd):
            self.t = (sf, pos, rd, 0, len(sf), True, '')

    def _trust(sf, pos, rd, store=None, di=None):
        return O._proper_noun_is_trusted((sf, pos, rd, 0, len(sf), True, ''),
                                         store, di)

    check('store も dict_index も無ければ落とさない',
          _trust('右田', '名詞:固有名詞:地域:一般', 'ミギタ'), True)

    class _St(object):
        def lookup(self, r):
            return []

    class _Di(object):
        def __init__(self, w):
            self._w = set(w)

        def is_world_reading(self, r):
            return r in self._w

    st, di = _St(), _Di({'ぶる'})
    check('漢字だけの姓は信用する（48-JL の持ち場）',
          _trust('高橋', '名詞:固有名詞:人名:姓', 'タカハシ', st, di), True)
    check('読みが世の中に無い地名は信用しない（右田）',
          _trust('右田', '名詞:固有名詞:地域:一般', 'ミギタ', st, di), False)
    check('カタカナの人名は表に在るときだけ（ブルは無い）',
          _trust('ブル', '名詞:固有名詞:人名:姓', 'ブル', st, di), False)
    check('カタカナでも人名でなければ信用する（ドイツ）',
          _trust('ドイツ', '名詞:固有名詞:地域:国', 'ドイツ', st, di), True)

    # **そもそも落としてよい形か**（測って足した門・48-OR）
    def _tk(parts):
        out, pos = [], 0
        for surf, p in parts:
            out.append((surf, p, surf, pos, pos + len(surf), True, ''))
            pos += len(surf)
        return out

    _hira = _tk([('ひ', '動詞:自立'), ('ら', '名詞:接尾:一般'),
                 ('が', '助詞:格助詞:一般'),
                 ('なを', '名詞:固有名詞:人名:名'), ('漢字', '名詞:一般')])
    check('ひらがなだけの固有名詞は落とさない（なを）',
          O._proper_noun_downgradable(_hira, 3), False)
    _tate = _tk([('縦', '名詞:一般'), ('シュー', '名詞:固有名詞:人名:姓'),
                 ('という', '助詞:格助詞:連語')])
    check('カタカナの連なりの端は落とさない（縦｜シュー｜という）',
          O._proper_noun_downgradable(_tate, 1), False)
    _bul = _tk([('右田', '名詞:固有名詞:地域:一般'),
                 ('で', '助詞:格助詞:一般'),
                 ('ブル', '名詞:固有名詞:人名:姓'),
                 ('クリック', '名詞:一般')])
    check('カタカナの連なりの途中は落とす（ブル｜クリック）',
          O._proper_noun_downgradable(_bul, 2), True)
    check('漢字の固有名詞は落としてよい形（右田）',
          O._proper_noun_downgradable(_bul, 0), True)

    print('--- 項目48-OS（F2 の単位） ---')
    usrc = open('units.py', encoding='utf-8').read()
    check('前処理は2つの道の両方に（48-OI と 48-OS）',
          usrc.count('tokens = _merge_small_kana_heads(tokens)') == 2
          and usrc.count('tokens = _split_unreadable_kana_tail(tokens)') == 2,
          True)
    check('機能語の尾を剥がす: にゅうりゅく｜みています',
          U._peel_function_tail('にゅうりゅくみています'),
          ('にゅうりゅく', 'みています'))
    check('剥がさない: きょじえかくらん',
          U._peel_function_tail('きょじえかくらん'), ('きょじえかくらん', ''))

    def _tok2(parts):
        def fn(text):
            out, pos = [], 0
            for surf, p, known in parts:
                out.append((surf, p, surf, pos, pos + len(surf), known, ''))
                pos += len(surf)
            return out
        return fn

    def _units(text, parts):
        r = {'original': text, 'corrected': text,
             'original_spans': [], 'spans': [], 'details': []}
        _t, us = U.build_suspect_units(r, _tok2(parts))
        return [(u['text'], u['start'], u['end']) for u in us]

    check('F2 の単位: に｜ゅうりゅくみています → にゅうりゅく｜みています',
          _units('にゅうりゅくみています',
                 [('に', '助詞:格助詞:一般', True),
                  ('ゅうりゅくみています', '名詞:一般', False)]),
          [('にゅうりゅく', 0, 6), ('みています', 6, 11)])
    check('読みが立つ塊は割らない（おもいます）',
          _units('おもいます', [('おもいます', '動詞:自立', True)]),
          [('おもいます', 0, 5)])
    check('剥がして中身が空になるなら割らない（しています）',
          _units('しています', [('しています', '名詞:一般', False)]),
          [('しています', 0, 5)])

    print('--- 項目48-OT（接頭詞を置き去りにしない） ---')
    check('み｜ぎたてぶるくりっく → ひとつ',
          _units('みぎたてぶるくりっく',
                 [('み', '接頭詞:名詞接続', True),
                  ('ぎたてぶるくりっく', '名詞:一般', False)]),
          [('みぎたてぶるくりっく', 0, 10)])
    check('後ろの読みが立つなら繋がない（お｜にぎり）',
          _units('おにぎり', [('お', '接頭詞:名詞接続', True),
                              ('にぎり', '名詞:一般', True)]),
          [('お', 0, 1), ('にぎり', 1, 4)])
    check('前処理は両方の道に（48-OT も2か所）',
          usrc.count('tokens = _merge_prefix_into_unreadable(tokens)') == 2,
          True)
    return all_ok[0]


def test_colloquial_20260903b():
    """
    **口語省略と、それ以外の品詞の型**（項目48-OU〜48-PB'・2026-09-03・
    2巡目）。うにさんの検討「助詞の省略・い抜き・ら抜き・撥音化・
    末尾の省略は**正しい口語**」——紫が立ったら誤爆。
    """
    all_ok = [True]

    def check(label, got, want):
        ok = got == want
        all_ok[0] = all_ok[0] and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import corrector as C
    import oddness as O
    import pos_grammar as P

    print('--- 項目48-OU（口語の縮約・ら抜き） ---')
    psrc = open('pos_grammar.py', encoding='utf-8').read()

    def isw(f):
        return False            # 表だけで見る（環境に依らない）

    def ex(run, stem=''):
        return P.explain_kana_run(run, bool(stem), False, stem, isw)

    check('い抜き: やってる・しってる・まってて', 
          (ex('やってる'), ex('しってる'), ex('まってて')),
          (True, True, True))
    check('ておく → とく: やっとく・よんどく',
          (ex('やっとく'), ex('よんどく')), (True, True))
    check('ていく → てく: もってく', ex('もってく'), True)
    check('ってば: だからってば', ex('だからってば'), True)
    check('ら抜き: たべれる・みれる・きれる',
          (ex('たべれる'), ex('みれる'), ex('きれる')), (True, True, True))
    check('ら抜き（漢字の語幹）: 食＋べれる・決＋めれる',
          (ex('べれる', '食'), ex('めれる', '決')), (True, True))
    check('1字の語幹は音便のときだけ（ひらん は説明が付かない）',
          ex('ひらん'), False)
    check('門の形（音便だけ）', "if _onbin_only and run[j] not in 'っん':"
          in psrc, True)
    check('とく/どく は TSU と N に', "('とく', 'END')" in psrc
          and "('どく', 'END')" in psrc, True)
    check('TE でも _PIECES を見る', "for piece, st2 in _PIECES.get('TE', ())"
          in psrc, True)

    # **守り**（画面33行の紫の的が紫のまま。表だけで見る）
    check('紫の的は説明が付かないまま',
          (ex('にゅうりょくみす'), ex('きょじえかくらん'), ex('すきにん'),
           ex('たんあご'), ex('わくわうし')),
          (False, False, False, False, False))

    print('--- 項目48-OV（1字の訓読み名詞＋動詞） ---')
    check('水（みず・訓）＋飲む は置ける',
          O.can_join('水', '名詞:一般', '飲む', '動詞:自立', 'みず'), True)
    check('手（て・訓）＋洗う は置ける',
          O.can_join('手', '名詞:一般', '洗う', '動詞:自立', 'て'), True)
    check('差（さ・音）＋釣れ は置けない（48-HT の的）',
          O.can_join('差', '名詞:一般', '釣れ', '動詞:自立', 'さ'), False)
    check('読みを渡さなければ今までどおり',
          O.can_join('水', '名詞:一般', '飲む', '動詞:自立'), False)
    check('見（動詞）＋し は名詞ではないので、読みを渡しても変わらない',
          O.can_join('見', '動詞:自立', 'し', '動詞:自立', 'み'),
          O.can_join('見', '動詞:自立', 'し', '動詞:自立'))

    print('--- 項目48-OW（感動詞のあとは格助詞だけ断る） ---')
    osrc = open('oddness.py', encoding='utf-8').read()
    check('格助詞だけに絞った',
          "elif ap.startswith('感動詞') and '格助詞' in bp:" in osrc, True)

    print('--- 項目48-OX（名詞＋疑問の代名詞） ---')
    check('ご飯＋何 は置ける',
          O.can_join('ご飯', '名詞:一般', '何', '名詞:代名詞:一般'), True)
    check('ご飯＋彼 は置けない（人称は入れない）',
          O.can_join('ご飯', '名詞:一般', '彼', '名詞:代名詞:一般'), False)

    print('--- 項目48-OY（カタカナ語の出どころ） ---')
    check('出どころは4つ（費用の表と索引の読みを足した）',
          '_C._table_cost(surf) is not None' in osrc
          and 'dict_index.is_world_reading(_h(surf))' in osrc, True)
    check("連なりの途中は世の中の語でも断片（48-OY')",
          'if not kata_split and _katakana_word_known(surf, dict_index):'
          in osrc, True)

    print('--- 項目48-OZ（切り詰めは採らない） ---')
    csrc = open('corrector.py', encoding='utf-8').read()
    check('開いた読みへの手からも切り詰めを外す',
          'and not _is_repeat_collapse(rd, _r)]:' in csrc, True)

    print('--- 項目48-PA（組の余り） ---')
    check('1字の余りは格助詞だけ',
          "if len(_g) == 1 and _g in 'はがをにでとものへやか':" in csrc, True)

    print("--- 項目48-PB/PB'（畳みと伸ばし棒に①） ---")
    check('48-PB は測って外した（枝は残す）',
          '**項目48-PB は測って外した**' in csrc, True)
    check('設計40-B にも①（explain_kana_run）を掛けた',
          'import pos_grammar as _pg40' in csrc, True)
    return all_ok[0]


def test_reading_patterns_20260903c():
    """
    **重箱・湯桶の表と、音訓表の穴**（項目48-PC〜48-PF・2026-09-03・
    3巡目）。うにさんの提案「漢字の重箱読み、湯桶読みの一覧を作って
    おいて、そこに一致する単語はそのルールで読み、一致しないものは
    音音読みで分析する」。
    """
    all_ok = [True]

    def check(label, got, want):
        ok = got == want
        all_ok[0] = all_ok[0] and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import kanji_onkun as OK
    import kanji_guess as KG

    print('--- 項目48-PD（読みの型の表） ---')
    check('表が読めている（同梱物の見張り）', OK.patterns_available(), True)
    check('重箱・湯桶・訓訓を引ける',
          (OK.pattern_of('一手'), OK.pattern_of('身分'),
           OK.pattern_of('背中')),
          ('重箱', '湯桶', '訓訓'))
    check('音音は載せない（＝既定）', OK.pattern_of('確認'), None)
    check('印が ? の読みは音読みの形で決める（表を2つ作らない）',
          (OK.on_or_kun('手', 'て'), OK.on_or_kun('確', 'かく')),
          ('kun', 'on'))
    check('音訓の並び → 型の名前',
          (OK.pattern_name(('on', 'kun')), OK.pattern_name(('kun', 'on')),
           OK.pattern_name(('kun', 'kun'))),
          ('重箱', '湯桶', '訓訓'))

    print('--- 項目48-PE（音訓表の穴） ---')
    check('辞書から逆算した音読みが入っている（程・勤・悲）',
          (OK.kind_of('程', 'てい'), OK.kind_of('勤', 'きん'),
           OK.kind_of('悲', 'ひ')),
          ('on', 'on', 'on'))
    check('もとの読みは押しのけていない（後ろへ足した）',
          OK.readings_of('程')[0], 'てい')
    check('出どころを notice に書いた',
          '2026-09-03' in open('kanji_onkun.json',
                               encoding='utf-8').read(1200), True)

    print('--- 項目48-PC（音訓の型で②の順位） ---')
    check('世の中の読みに合えば足さない（確認・背中・一手・手本）',
          (KG._pattern_penalty('確認', ('かく', 'にん')),
           KG._pattern_penalty('背中', ('せ', 'なか')),
           KG._pattern_penalty('一手', ('いっ', 'て')),
           KG._pattern_penalty('手本', ('て', 'ほん'))),
          (0, 0, 0, 0))
    check('世の中の読みと違えば +2（背中＝はいちゅう・入力＝いりょく）',
          (KG._pattern_penalty('背中', ('はい', 'ちゅう')),
           KG._pattern_penalty('入力', ('い', 'りょく'))),
          (2, 2))
    check('**読みが何通りもある語には何も言わない**（仮名＝かな／かめい）',
          (KG._pattern_penalty('仮名', ('か', 'な')),
           KG._pattern_penalty('仮名', ('か', 'めい'))),
          (0, 0))
    check('表が読みを知らないときは音訓の型で（一齣＝ひとこま・重箱）',
          KG._pattern_penalty('一齣', ('ひと', 'こま')), 1)
    check('**語でない切れ目には何も言わない**（保存先 の 存先）',
          KG._pattern_penalty('保存先', ('ほ', 'ぞん', 'さき')), 0)
    check('漢字が1つだけなら点は付かない（本＝もと）',
          KG._pattern_penalty('本', ('もと',)), 0)
    ksrc = open('kanji_guess.py', encoding='utf-8').read()
    check('門にしない（rank に足すだけ）',
          'prank + _pattern_penalty(text, parts)' in ksrc, True)
    check('語かどうかの出どころは2つだけ',
          '_c._table_cost(pair) is not None' in ksrc, True)
    check('読みは表に直に聞く（型を推さない）',
          '_c._table_readings_for_surface(pair)' in ksrc, True)

    print('--- 項目48-PF（読める読みが在ったら敷居を上げる） ---')
    csrc = open('corrector.py', encoding='utf-8').read()
    check('下位の読みに readable_hint を渡す',
          'readable_hint=_readable_seen,' in csrc, True)
    check('門は閉じない（項目48-AE のまま）',
          '**下位の読みは敷居を上げる**' in csrc, True)

    print('--- 項目48-PG（文法の仕事をしている隙間は書き換えない） ---')
    check('言い淀みだけ落としてよい（フィラー・感動詞）',
          "k in ('フィラー', '感動詞') for k in kinds)" in csrc, True)
    check('設計23 の受け入れで、もとの隙間と見比べる',
          'for _a, _b in zip(_og, _gaps):' in csrc, True)
    check('漢字の隙間は読みが同じときだけ書き換える（化→か は残す）',
          'if _b and _b in _gap_readings(_a):' in csrc, True)
    # `あの` が フィラー と読まれるのは**本物の janome があるとき**
    # （モックの解析には フィラー が無い）。ここでは**仕事をしている
    # 機能語を False と言うこと**だけを見る（環境に依らない側）。
    # **解析が品詞を言えない環境では、この門は黙る**（モックは '*'）。
    # 見るのは「言えないなら False」の側だけ（環境に依らない）。
    check('解析が言えないときは意見を持たない',
          (C._gap_does_grammar_work(''), C._gap_does_grammar_work('まで')),
          (False, False))

    print('--- 項目48-PL（動詞基本形＋名詞は「読める」に数えない） ---')
    csrc0 = open('corrector.py', encoding='utf-8').read()
    check('①ではなく④の敷居の側（3か所に掛ける）',
          (csrc0.count('_verb_noun_joined(') >= 4,
           '`_looks_like_valid_japanese` そのものには入れない' in csrc0),
          (True, True))
    check('非自立・接尾の名詞は除く（書くこと・する時）',
          "not (pos or '').startswith('名詞:接尾')" in csrc0, True)
    check("判定の芯は述語1本（48-GN・units と explain も同じものを見る）",
          csrc0.count('def _verb_noun_pair('), 1)
    print("--- 項目48-PL(b')（余分な隣のキーは①が立つ塊だけ） ---")
    # 2026-09-03 は「無条件で開くと育ちで正しい文を3行壊す」で外していた。
    # うにさんの正し（2026-09-04）「**正しい文が異様と判定されているのが
    # 問題**」——分けるのは手の強さではなく**①**。動詞基本形＋名詞の
    # 直付き（品詞のつながりが異様）が立つ塊だけに、この手を開く。
    check("余分な隣のキーは①が立つ塊だけに開く（48-PL(b')）",
          ('def _typo_repairs(core, extra_key=False, input_method=' in csrc0
           and "_typo_repairs(_ar, extra_key=True," in csrc0
           and '_verb_noun_joined(chunk, tokenize_fn)' in csrc0), True)
    check('extra_key を渡す呼び手は説明の門ただ1つ（候補を作る側には無い）',
          csrc0.count('_typo_repairs(_ar, extra_key=True,'), 1)
    check('extra_key の巻き戻しそのもの（かいすせき → かいせき・す は い の隣）',
          ('かいせき' in C._typo_repairs('かいすせき', extra_key=True)
           and 'かいせき' not in C._typo_repairs('かいすせき')), True)

    print("--- 項目48-PK（直し先が「既知語＋1字助詞」なら採らない） ---")
    # 育った語彙の `かなで`(65)＝**かな＋で を学習で1語に取り込んだ
    # もの**を直し先にすると、`かなちで`（かな打ちで の脱字）が
    # そこへ吸い込まれる（うにさんの画面17行・育ちだけの化け・実測）。

    class _StPK:
        def lookup(self, r):
            return ([{'surface': 'かな', 'count': 1231}]
                    if r == 'かな' else [])
    check('かなで ＝ かな＋で は語ではない（直し先にしない）',
          C._target_splits_word_particle('かなで', _StPK()), True)
    check('頭が語彙に無ければ黙る',
          C._target_splits_word_particle('たぶで', _StPK()), False)
    check('見るのは格助詞・係助詞だけ（さかな の な で割らない）',
          ('な' in C._PK_PARTICLES, 'で' in C._PK_PARTICLES),
          (False, True))
    check('A道と芯の両方に掛けている（学び22——A道だけでは芯が拾った・実測）',
          csrc0.count('_target_splits_word_particle('), 3)

    print('--- 項目48-PQ（カタカナのサ変名詞＋接尾 語 → 後） ---')

    def tok_pq(line):
        table = {'スクロール': ('名詞:サ変接続', 'スクロール'),
                 'カタカナ': ('名詞:一般', 'カタカナ'),
                 '検索': ('名詞:サ変接続', 'ケンサク'),
                 '語': ('名詞:接尾:一般', 'ゴ'),
                 'の': ('助詞:連体化', 'ノ'),
                 '見えた': ('動詞:自立', 'ミエタ')}
        out = []
        pos = 0
        rest = line
        while rest:
            for w, (p, rd) in sorted(table.items(),
                                     key=lambda kv: -len(kv[0])):
                if rest.startswith(w):
                    out.append((w, p, rd, pos, pos + len(w), True))
                    pos += len(w)
                    rest = rest[len(w):]
                    break
            else:
                out.append((rest[0], '名詞:一般', '', pos, pos + 1, False))
                pos += 1
                rest = rest[1:]
        return out
    check('スクロール語 → 語 を 後 に（カタカナのサ変名詞だけ）',
          C._katakana_go_after_fixes('スクロール語の見えた', tok_pq),
          [(5, 6, '後', 'その他')])
    check('カタカナ語（サ変でない頭）は触らない',
          C._katakana_go_after_fixes('カタカナ語の補正', tok_pq), [])
    check('漢語のサ変＋語（検索語）は触らない——表で守れない正しい語',
          C._katakana_go_after_fixes('検索語の一覧', tok_pq), [])

    print('--- 項目48-PO（異様の対の範囲だけを読みで置き換える受け皿） ---')
    # 当たりは ci_smoke（も水戸に戻ります → もとに戻ります）。ここは形:
    check('受け皿は設計27の「決めない」の手前に1つ',
          csrc0.count('_po_replace_odd_span(chunk, _odd_pairs'), 1)
    check('置き換えた範囲は「知っている語」だけ（語彙 count>=2 か費用の表。'
          'is_world_reading は くみと まで True で使えない——実測）',
          ("_known_odd = _table_cost(fixed_odd) is not None" in csrc0
           and 'is_world_reading(fixed_odd)' not in csrc0), True)
    check('手を当てた読み全体が 48-IS で説明が付くこと',
          '_kana_run_explained(_v)' in csrc0, True)
    check('異様の対が1組だけのときしか動かない',
          'if not odd_pairs or len(odd_pairs) != 1 or not ar:' in csrc0,
          True)
    check('対の外に「書いてあるまま保たれる残り」があること（ふだく→いだく を止めた門）',
          'if not pre_rd and not post_rd:' in csrc0, True)
    check('対に漢字を含むこと（かなだけの連なりは既存の道の持ち場）',
          'if not any(is_kanji(c) for c in (a_sf + b_sf)):' in csrc0, True)

    print('--- 項目48-PT（読みの立たないカタカナ断片は塊に含める） ---')
    # 48-HU の守りは「読みが立つカタカナ語に接している」ときだけに絞る。
    # 解析課背中|セク → 解析課背中セク（セク は読み立たず→含める）
    line_pt = '解析課背中セク、'
    toks_pt = [('解析', '名詞:サ変接続', 'カイセキ', 0, 2, True),
               ('課', '名詞:接尾', 'カ', 2, 3, True),
               ('背中', '名詞:一般', 'セナカ', 3, 5, True),
               ('セク', '名詞:固有名詞:組織', '', 5, 7, False),
               ('、', '記号:読点', '、', 7, 8, True)]
    check('読みの立たない断片なら塊に含める（解析課背中セク）',
          C._pt_extend_over_dead_katakana(line_pt, 0, 5, toks_pt), (0, 7))
    toks_pt2 = [('文字', '名詞:一般', 'モジ', 0, 2, True),
                ('乳', '名詞:一般', 'チチ', 2, 3, True),
                ('リュク', '名詞:一般', '', 3, 6, False)]
    check('文字乳リュク も1塊になる（新しい◎の入口）',
          C._pt_extend_over_dead_katakana('文字乳リュク', 0, 3, toks_pt2),
          (0, 6))
    toks_pt3 = [('添付', '名詞:サ変接続', 'テンプ', 0, 2, True),
                ('画像', '名詞:一般', 'ガゾウ', 2, 4, True),
                ('ソフト', '名詞:一般', 'ソフト', 4, 7, True)]
    check('読みが立つカタカナ語に接しているなら守る（48-HU 本来の形）',
          C._pt_extend_over_dead_katakana('添付画像ソフト', 0, 4, toks_pt3),
          None)

    print('--- 項目48-PX/48-PY（壊れた形の見本の並記に引きずられない） ---')
    # 未解決.txt の注記の行（`糸を察して → 意図をさして　（触る前は
    # 「意図を察して」…）`）で、**壊れた形の見本が並記**になり、
    # 正しい側が壊された（察して→さして・より→よ。どちらも1字削除の
    # 変種）。①で受け止める——文法として完成している所は動かさない。

    def tok_px(line):
        table = {'察し': ('動詞:自立', 'サッシ', '連用形'),
                 '泳い': ('動詞:自立', 'オヨイ', '連用タ接続'),
                 '差': ('名詞:一般', 'サ', ''),
                 '釣れ': ('動詞:自立', 'ツレ', '連用形'),
                 'ませ': ('助動詞', 'マセ', '未然形'),
                 'ん': ('助動詞', 'ン', '基本形'),
                 '前': ('名詞:副詞可能', 'マエ', ''),
                 'より': ('助詞:格助詞:一般', 'ヨリ', ''),
                 'クリック': ('名詞:サ変接続', 'クリック', ''),
                 'ば': ('助詞:接続助詞', 'バ', ''),
                 'ドラッグ': ('名詞:サ変接続', 'ドラッグ', ''),
                 'て': ('助詞:接続助詞', 'テ', ''),
                 'で': ('助詞:接続助詞', 'デ', '')}
        out = []
        pos = 0
        rest = line
        while rest:
            for w, (p, rd, infl) in sorted(table.items(),
                                           key=lambda kv: -len(kv[0])):
                if rest.startswith(w):
                    out.append((w, p, rd, pos, pos + len(w), True, infl))
                    pos += len(w)
                    rest = rest[len(w):]
                    break
            else:
                out.append((rest[0], '名詞:一般', '', pos, pos + 1,
                            False, ''))
                pos += 1
                rest = rest[1:]
        return out
    check('連用形＋接続助詞 て はできあがっている（察して・48-PX）',
          C._chunk_is_intact('察して', tok_px), True)
    check('連用タ接続＋で も同じ（泳いで）',
          C._chunk_is_intact('泳いで', tok_px), True)
    check('4トークンの塊は対象外（差釣れません → されません の的は残る）',
          C._chunk_is_intact('差釣れません', tok_px), False)
    check('働いている格助詞は書き換えない（前[より]前・48-PY）',
          C._middle_is_working_particle('前より前', 1, 3, tok_px), True)
    check('接続助詞（ば）は名詞の後ろでは働いていない——直しは止めない',
          C._middle_is_working_particle('クリックばドラッグ', 4, 5, tok_px),
          False)
    check('範囲が語の境目に合わないときは名乗らない',
          C._middle_is_working_particle('前より前', 1, 2, tok_px), False)
    check('判定は1回だけ書き、3分割の口から呼ぶ（48-GN）',
          csrc0.count('_middle_is_working_particle('), 2)

    print('--- 項目48-PP（補助動詞は て形のあとだけ） ---')
    check('いる・ある は入れない（測って絞った）',
          ('いる' not in C._AUX_VERB_AFTER_TE
           and 'ある' not in C._AUX_VERB_AFTER_TE
           and 'おく' in C._AUX_VERB_AFTER_TE), True)
    check('て形のあとだけ func、それ以外は word として置く',
          "if (kinds - {'word'}):" in csrc0
          and 'def _aux_needs_te(run, i, frag):' in csrc0, True)
    check('48-IS の機能語に んの は足さない（測って外した）',
          '48-IS の機能語に `んの` は足さない' in csrc0, True)

    print('--- 項目48-KZ(G)（接尾に接尾は付かない） ---')
    osrc0 = open('oddness.py', encoding='utf-8').read()
    check('名詞:接尾:一般 どうしだけ',
          "if ('名詞:接尾:一般' in ap and '名詞:接尾:一般' in bp" in osrc0,
          True)
    check('a+b が表の語なら黙る（次号・語派・強勢が自動で外れる）',
          '(a_sf + b_sf) not in (_load() or ())' in osrc0, True)
    import oddness as _O_kz
    check('閉じた表は 語系 の1組だけ',
          _O_kz._SUFFIX_PAIR_OK, frozenset((('語', '系'),)))

    print('--- 項目48-PS（ているの → てんの） ---')
    psrc0 = open('pos_grammar.py', encoding='utf-8').read()
    check('て形のあとの んの・んだ・んです',
          ("('んの', 'END')" in psrc0 and "('んです', 'END')" in psrc0), True)
    import pos_grammar as _P_ps
    check('サ変の連用形 し は閉じた枝（白名簿には足さない）',
          ("if stem == 'し':" in psrc0
           and 'し' not in _P_ps._BASIC_STEMS_1), True)

    print('--- 項目48-PH（尻尾まで変わる変換は漢語の変換ではない） ---')
    check('48-MI で尻尾が元のままかを確かめる',
          "if tail and not surface.endswith(run[head_end:]):" in csrc, True)

    print('--- 項目48-PI（助詞のトークンで区切る） ---')
    # 切る／切らないの判定そのもの（解析が要るので、当たりは
    # `ci_smoke_test.py` の側で見張る。ここは**形**を見る）
    check('区切る字は格助詞・係助詞の1字だけ',
          C._RUN_SPLIT_IF_TOKEN, 'がにはでとへも')
    check('を・の の区切りは今までどおり',
          (C._RUN_SPLIT_ALWAYS, C._RUN_SPLIT_IF_WORD), ('を', 'の'))
    check('右の頭に立てない字（語の途中で切れた印）',
          'ゃ' in C._PSPLIT_NG_HEAD and 'っ' in C._PSPLIT_NG_HEAD
          and 'か' not in C._PSPLIT_NG_HEAD, True)
    check('左4字・右2字より短いなら切らない（試作 v2 で壊した形）',
          'if k < 4 or n - k - 1 < 2:' in csrc, True)
    check('①が立っている連続だけ（説明が付くなら触らない）',
          'if _kana_run_explained(run, tokenize_fn=tokenize_fn):' in csrc,
          True)
    check('右側はかなの文法で説明が付くこと',
          "if not _pg.explain_kana_run(run[k + 1:]):" in csrc, True)
    check('★ 区切りは最後の手（まるごとで直るなら切らない）',
          'if any(not (run_end <= _r[0] or run_start >= _r[1])' in csrc,
          True)
    check('48-IT の控えが在るときも切らない',
          'if (run_start, run_end) in _psplit_seen or pending_ff:' in csrc,
          True)
    check('右は流さない（左だけ worklist に戻す）',
          '_psplit_work.insert(0, (run_start, run_start + _k, run[:_k]))'
          in csrc, True)
    check('左のぶんの紫だけ取り消す（右は通し直さないので残す）',
          'if _sp[0] >= _cut_abs]' in csrc, True)
    check('かなで書いた外来語なら切らない（あとの道が丸ごと直す）',
          'if _psplit_is_kana_loanword(run, store):' in csrc, True)
    check('左がそれ自体で説明が付くなら切らない',
          'if _kana_run_explained(run[:k], tokenize_fn=tokenize_fn):'
          in csrc, True)
    check('左を 48-IT が書き換える形なら切らない（本番と同じ材料で予想）',
          'if _fix_functional_run(run[:k], after_kanji=after_kanji,' in csrc
          and 'store=store, tokenize_fn=tokenize_fn):' in csrc
          and 'after_kanji=(run_start > 0' in csrc, True)
    check('左が「世の中に在る読み」なら切らない（芯の再構築と同じ判定）',
          'if dict_index.is_world_reading(run[:k]):' in csrc, True)
    check('同じ助詞の連続に活用形の免除は入れない（測って外した）',
          '**同じ1字の助詞の連続に、活用形の免除は入れない**' in csrc, True)
    check('現代語の五段が在る行だけ（ず・づ・ふ・ぷ・ゆ は幻）',
          C._GODAN_LIVE, ('う', 'く', 'ぐ', 'す', 'つ', 'ぬ', 'ぶ', 'む', 'る'))
    check('辞書形が動詞であることを解析に聞く（鉄・リス・突を弾く）',
          'and _is_verb_word(stem + u)' in csrc, True)
    check('品詞を言えないときは黙る（janome の無い環境）',
          (C._is_verb_word(''), C._is_common_verb_form('て')),
          (False, False))
    check('7字より短い連続は相手にしない（左4＋助詞1＋右2）',
          (C._psplit_cut('かいすせき', None),
           C._psplit_cut('', None)), (None, None))
    return all_ok[0]
