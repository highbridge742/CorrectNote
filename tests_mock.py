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
    run_tab_cases,
    run_design33_cases,
    run_scroll_cache_cases,
    run_icon_cases,
    run_explain_cases,
    test_menu_and_keys_48oc_48od_48oe,
    test_small_kana_head_units_48oi,
    test_refit_broken_units_48pv,
    test_unit_reading_and_rows_20260904,
    test_pos_from_row_context_48qc_48qd,
    test_privacy_no_counts_48qg_48qh_48qj)
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
    test_kana_to_kanji,
    test_oddness_rules,
    test_odd_rules_48is,
    test_kana_fix_48it,
    test_resplit_48iw,
    test_common_odd_48ix,
    test_kana_alphabet_48iz,
    test_kbest_48jc,
    test_odd_recognition_48jg,
    test_misplaced_dakuten_48jp,
    test_long_vowel_48js,
    test_head_typo_48jt,
    test_recut_candidate_48ju,
    test_resegment_48jv,
    test_odd_mark_48jw,
    test_particle_merge_48jz,
    test_parallel_pair_48ka,
    test_backslash_key_48kb,
    test_adverb_join_48ke,
    test_stem_run_48kf,
    test_abab_48km,
    test_swap_tie_48kn,
    test_no_purple_when_left_alone_48ko,
    test_okurigana_double_48kp,
    test_48kh_disabled_on_purpose,
    test_pos_grammar_48ks,
    test_run_reading_merge_48kt,
    test_kt_hands_48ku,
    test_shift_toggle_48kv,
    test_pos_open_48kw,
    test_head_particle_48kx,
    test_mishi_48kx,
    test_te_i_piece_48ky,
    test_compose_kana_run_48ky,
    test_small_kana_neighbor_48ky,
    test_pos_pair_rules_48kz,
    test_adjective_tail_48kz,
    test_mixed_run_reopen_48la,
    test_lc_hand_unit_48lc,
    test_kana_run_hand_48ld,
    test_sei_pair_48le,
    test_fp_guards_48lj,
    test_onbin_48ll,
    test_zero_edge_48lm,
    test_gloss_guards_48ln,
    test_fp_guards_48lp,
    test_compose_48lu,
    test_span_over_space_48mf,
    test_u_insert_compose_48mg,
    test_honorific_prefix_48mh,
    test_free_suffix_intact_48me,
    test_kango_convert_48mi,
    test_one_hand_length_48mj,
    test_conversion_anchor_48mk,
    test_split_at_wo_48mn,
    test_kango_stem_48mp,
    test_on_shape_48mq,
    test_purple_false_positives_48mr,
    test_split_at_no_48ms,
    test_mark_span_reopen_48mv,
    test_assemble_after_hand_48mw,
    test_small_yoon_slip_48mx,
    test_anchor_not_at_head_48my,
    test_noun_compound_48na,
    test_renyou_one_char_48nc,
    test_assemble_on_main_path_48mz,
    test_stable_across_launches_48ne,
    test_convert_after_core_48nf,
    test_whole_word_floor_48ng,
    test_romaji_cost_wiring_48nj,
    test_open_odd_single_kanji_48nk,
    test_na_stem_48nm_48nn,
    test_ime_record_not_over_assemble_48np,
    test_ime_record_is_not_a_gate_48nq,
    test_adverb_ni_dangling_48nr_48ns,
    test_infl_connection_48nt,
    test_known_kanji_tail_core_48nu,
    test_compound_words_48nv_48nw,
    test_logical_pos_rules_48nx_48ny,
    test_chunk_near_by_method_48oa,
    test_naadj_two_faces_48nm2,
    test_mark_drop_reverts_48og,
    test_index_face_48oj,
    test_pos_and_units_20260903,
    test_colloquial_20260903b,
    test_reading_patterns_20260903c)
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
        # 複数の語＋助詞。**`つながり` はひらがなのまま**（項目48-IO）。
        # 初期語彙は `つながり`／`繋がり` の2表記を同じ回数で持ち、
        # 以前は投入時刻のマイクロ秒差で `繋がり` が勝っていた
        # （Linux だけ。Windows は時計の刻みで同点＝`つながり`）。
        # 時刻を揃えたので、表の並び順（ひらがなが先）で決まる。
        ('qyb@kzut@l', True, '単語のつながり'),
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
    ok34 = test_oddness_rules()
    print()
    ok35 = test_odd_rules_48is()
    print()
    ok36 = test_kana_fix_48it()
    print()
    ok37 = test_resplit_48iw()
    print()
    ok38 = test_common_odd_48ix()
    print()
    ok39 = test_kana_alphabet_48iz()
    print()
    ok40 = run_design33_cases()
    print()
    ok41 = test_kbest_48jc()
    print()
    ok42 = test_odd_recognition_48jg()
    print()
    ok43 = run_scroll_cache_cases()
    print()
    ok44 = test_misplaced_dakuten_48jp()
    print()
    ok45 = run_icon_cases()
    print()
    ok46 = test_long_vowel_48js()
    print()
    ok47 = test_head_typo_48jt()
    print()
    ok48 = test_recut_candidate_48ju()
    print()
    ok49 = test_resegment_48jv()
    print()
    ok50 = test_odd_mark_48jw()
    print()
    ok51 = test_particle_merge_48jz()
    print()
    ok52 = test_parallel_pair_48ka()
    print()
    ok53 = test_backslash_key_48kb()
    print()
    ok54 = test_adverb_join_48ke()
    print()
    ok55 = test_stem_run_48kf()
    print()
    ok56 = test_abab_48km()
    ok57 = test_swap_tie_48kn()
    ok58 = test_no_purple_when_left_alone_48ko()
    ok59 = test_okurigana_double_48kp()
    ok60 = test_48kh_disabled_on_purpose()
    ok61 = test_pos_grammar_48ks()
    ok62 = test_run_reading_merge_48kt()
    ok63 = test_kt_hands_48ku()
    ok64 = test_shift_toggle_48kv()
    ok65 = test_pos_open_48kw()
    ok66 = test_head_particle_48kx()
    ok67 = test_mishi_48kx()
    ok68 = test_te_i_piece_48ky()
    ok69 = test_compose_kana_run_48ky()
    ok70 = test_small_kana_neighbor_48ky()
    ok71 = test_pos_pair_rules_48kz()
    ok72 = test_adjective_tail_48kz()
    ok73 = test_mixed_run_reopen_48la()
    ok74 = test_lc_hand_unit_48lc()
    ok75 = test_kana_run_hand_48ld()
    ok76 = test_sei_pair_48le()
    ok77 = test_fp_guards_48lj()
    ok78 = test_onbin_48ll()
    ok79 = test_zero_edge_48lm()
    ok80 = test_gloss_guards_48ln()
    ok81 = test_fp_guards_48lp()
    ok82 = test_compose_48lu()
    ok83 = run_explain_cases()
    ok84 = test_span_over_space_48mf()
    ok85 = test_u_insert_compose_48mg()
    ok86 = test_honorific_prefix_48mh()
    ok87 = test_free_suffix_intact_48me()
    ok88 = test_kango_convert_48mi()
    ok89 = test_one_hand_length_48mj()
    ok90 = test_conversion_anchor_48mk()
    ok91 = test_split_at_wo_48mn()
    ok92 = test_kango_stem_48mp()
    ok93 = test_on_shape_48mq()
    ok94 = test_purple_false_positives_48mr()
    ok95 = test_split_at_no_48ms()
    ok96 = test_mark_span_reopen_48mv()
    ok97 = test_assemble_after_hand_48mw()
    ok98 = test_small_yoon_slip_48mx()
    ok99 = test_anchor_not_at_head_48my()
    ok100 = test_noun_compound_48na()
    ok101 = test_renyou_one_char_48nc()
    ok102 = test_assemble_on_main_path_48mz()
    ok103 = test_stable_across_launches_48ne()
    ok104 = test_convert_after_core_48nf()
    ok105 = test_whole_word_floor_48ng()
    ok106 = test_romaji_cost_wiring_48nj()
    ok107 = test_open_odd_single_kanji_48nk()
    ok108 = test_na_stem_48nm_48nn()
    ok109 = test_ime_record_not_over_assemble_48np()
    ok110 = test_ime_record_is_not_a_gate_48nq()
    ok111 = test_adverb_ni_dangling_48nr_48ns()
    ok112 = test_infl_connection_48nt()
    ok113 = test_known_kanji_tail_core_48nu()
    ok114 = test_compound_words_48nv_48nw()
    ok115 = test_logical_pos_rules_48nx_48ny()
    ok116 = test_chunk_near_by_method_48oa()
    ok117 = test_naadj_two_faces_48nm2()
    ok118 = test_menu_and_keys_48oc_48od_48oe()
    ok119 = test_mark_drop_reverts_48og()
    ok120 = test_small_kana_head_units_48oi()
    ok121 = test_index_face_48oj()
    ok122 = test_pos_and_units_20260903()
    ok123 = test_colloquial_20260903b()
    ok124 = test_reading_patterns_20260903c()
    ok125 = test_refit_broken_units_48pv()
    ok126 = test_unit_reading_and_rows_20260904()
    ok127 = test_pos_from_row_context_48qc_48qd()
    print()
    ok128 = test_privacy_no_counts_48qg_48qh_48qj()
    print()
    print('ALL OK:', ok1 and ok2 and ok3 and ok4 and ok5 and ok6 and ok7
          and ok8 and ok9 and ok10 and ok11 and ok12 and ok13 and ok14
          and ok15 and ok16 and ok17 and ok18 and ok19 and ok20 and ok21
          and ok22 and ok23 and ok24 and ok25 and ok26 and ok27
          and ok28 and ok29 and ok30 and ok31 and ok32
          and ok33 and ok34 and ok35 and ok36 and ok37 and ok38
          and ok39 and ok40 and ok41 and ok42 and ok43 and ok44 and ok45
          and ok46 and ok47 and ok48 and ok49 and ok50 and ok51 and ok52
          and ok53 and ok54 and ok55 and ok56 and ok57 and ok58 and ok59
          and ok60 and ok61 and ok62 and ok63 and ok64 and ok65 and ok66 and ok67 and ok68 and ok69 and ok70 and ok71 and ok72 and ok73 and ok74 and ok75 and ok76 and ok77 and ok78 and ok79 and ok80 and ok81 and ok82 and ok83 and ok84 and ok85 and ok86 and ok87 and ok88 and ok89 and ok90 and ok91 and ok92 and ok93 and ok94 and ok95 and ok96 and ok97 and ok98 and ok99 and ok100 and ok101 and ok102 and ok103 and ok104 and ok105 and ok106 and ok107 and ok108 and ok109 and ok110 and ok111 and ok112 and ok113 and ok114 and ok115 and ok116 and ok117 and ok118 and ok119 and ok120 and ok121 and ok122 and ok123 and ok124 and ok125 and ok126 and ok127 and ok128)
