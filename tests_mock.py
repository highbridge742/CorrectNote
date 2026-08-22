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
janome の実挙動を再現したモックと、補正エンジンの回帰テスト。

janome を入れられない環境でも、実機で起きた不具合を
再現・検証できるようにするためのもの。

    py tests_mock.py

**janome があると意味が変わる**（2026-08-15）
----------------------------------------------
この一式は「janome が**無い**環境のふるまい」を測るもの。
janome が入った python で走らせると、本物の形態素解析が
割り込んで **10件が NG に見える**。エンジンは何も悪くない。

一度これで読み違えた（`runprobe.sh` は tkinter の要る probe の
ために python3.12 を使うが、そちらには janome が入っている）。
**黙って赤くなると、直っているものを壊れたと読む。**
だから起動時に自分で見張る。
"""
import sys

try:                                   # pragma: no cover
    import janome                      # noqa: F401
    _HAS_JANOME = True
except Exception:                      # pragma: no cover
    _HAS_JANOME = False

if _HAS_JANOME and '--allow-janome' not in sys.argv:
    print('!! この python には janome が入っている。')
    print('!! tests_mock は **janome の無い環境**を測るもの。')
    print('!! 例: PYTHONPATH=/tmp/nojanome py tests_mock.py')
    print('!! （どうしても走らせるなら --allow-janome）')
    print('ALL OK: **測っていない**')
    raise SystemExit(2)

import corrector as C
from vocabulary import VocabularyStore, find_known_readings_flex
from seed_vocabulary import load_seed

import corrector as C
from vocabulary import VocabularyStore, find_known_readings_flex
from seed_vocabulary import load_seed

from tests_mock_common import build_store  # noqa: F401
from tests_mock_rebuild import (
    run_rebuild_cases)
from tests_mock_ui import (
    run_settings_cases,
    run_theme_palette_cases,
    run_drag_scroll_cases,
    run_session_cases,
    run_search_cases,
    run_tab_cases)
from tests_mock_memory import (
    run_choice_cases,
    run_decision_cases,
    run_dict_index_cases,
    run_context_vec_cases,
    run_context_material_cases,
    test_analysis_cache)
from tests_mock_words import (
    test_seed_dictionary,
    test_katakana_compound_guard,
    test_loanword_and_english,
    test_miskeyed_english,
    test_kana_loanword_typo,
    test_char_ngram,
    test_kana_to_kanji)
from tests_mock_fix import (
    run_cases,
    run_overcorrection_cases,
    run_kanji_guess_cases,
    run_original_spans_cases,
    run_regression_cases,
    report_known_issues,
    test_attested_candidates,
    test_halfwidth_guards,
    test_report_small_fixes,
    test_homophone_by_context,
    test_homophone_conjugated,
    test_samekey_punctuation,
    test_map_column)

if __name__ == '__main__':
    store = build_store()

    typo_cases = [
        # --- 置換（隣接キーの押し間違い） ---
        ('もばなゅうりょく', True, 'もじにゅうりょく'),
        ('もばなゅいりょく', True, 'もじにゅうりょく'),

# 2026-08-10（項目48-r）: うにさんの指定
# 「カタカナが適した単語はカタカナに補正する」により、
# 表記がカタカナだけの外来語は**カタカナで**書き出すようになった。
# ぱそこん → パソコン、きーぼーど → キーボード。
# 直す中身（どの語に届くか）は変わっていない。
        ('ぱそみん', True, 'パソコン'),
        ('へんかく', True, 'へんかん'),
        ('けんさこ', True, 'けんさく'),
        # **かな入力では直さない**（項目48-GI）。`そ → ど` は
        # 1文字違いで、`ど` は `と＋濁点` の2打鍵。ローマ字入力
        # （so → do）なら s と d が隣なので直る。
        ('きーぼーそ', False, 'きーぼーそ'),
        # --- 濁点・半濁点・小書きの誤り ---
        ('ぱぞこん', True, 'パソコン'),
        ('はそこん', True, 'パソコン'),
        ('もんたい', True, 'もんだい'),
        ('しゆうせい', True, 'しゅうせい'),
        # --- 脱字（押し忘れ） ---
        ('もじにゅうりょ', True, 'もじにゅうりょく'),
        ('じにゅうりょく', True, 'もじにゅうりょく'),
        # --- 余分な打鍵（押しすぎ・重複） ---
        ('もじにゅううりょく', True, 'もじにゅうりょく'),
        ('ぱそここん', True, 'パソコン'),
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
        ('ぱそみんは、', True, 'パソコンは、'),
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
    print()
    ok19 = test_loanword_and_english()
    print()
    ok20 = test_map_column()
    print()
    ok21 = test_homophone_by_context()
    print()
    ok22 = test_report_small_fixes()
    print()
    ok23 = test_katakana_compound_guard()
    print()
    ok24 = test_halfwidth_guards()
    print()
    ok25 = test_analysis_cache()
    print()
    ok26 = test_attested_candidates()
    print()
    ok27 = test_seed_dictionary()
    print()
    ok28 = test_char_ngram()
    print()
    ok29 = test_homophone_conjugated()
    print()
    ok30 = test_kana_to_kanji()
    print()
    ok31 = test_miskeyed_english()
    print()
    ok32 = test_kana_loanword_typo()
    print()
    ok33 = test_samekey_punctuation()
    print()
    print('ALL OK:', ok1 and ok2 and ok3 and ok4 and ok5 and ok6 and ok7
          and ok8 and ok9 and ok10 and ok11 and ok12 and ok13 and ok14
          and ok15 and ok16 and ok17 and ok18 and ok19 and ok20 and ok21
          and ok22 and ok23 and ok24 and ok25 and ok26 and ok27
          and ok28 and ok29 and ok30 and ok31 and ok32
          and ok33)
