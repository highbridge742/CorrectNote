# -*- coding: utf-8 -*-
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
前回の解析結果を控えておき、次の起動で作り直さずに済ませる。

うにさんの指摘（2026-08-11）:
「1000行あると待ち時間が長い」「前回終了時にキャッシュ保存して、
次回起動時に見たら速くなりませんか」。

977行のタブで解析に 6.08 秒かかっており、その内訳は
文脈語彙 0.6秒・内容語 0.5秒・**補正そのもの 5.0秒**。
補正の結果まで控えれば、起動時はこの全部を飛ばせる。

**なぜ控えを信じてよいか**

起動した時点では、まだ何も学習していない。語彙も文脈ベクトルも
判断も、前回保存したときのまま。つまり **入力がすべて同じ**なので、
計算し直しても同じ結果にしかならない。逆に言えば、
**入力のどれか1つでも違えば控えは使えない**。ここを取り違えると
「古い補正結果を、新しい語彙のもとで表示してしまう」ことになり、
「正しく書いたものを壊さない」に反する。だから照合は厳しくする:

  - 本文（タブの文字列そのもの）が1文字も違わないこと
  - 語彙・文脈ベクトル・辞書索引・判断・選び直しの**中身**が
    同じこと（ファイルの更新時刻ではなく**状態**を見る。
    起動時に英単語を覚え直すのでファイルは必ず書き換わり、
    更新時刻で見ると控えが一度も使えない）
  - 入力方式（かな／ローマ字）が同じこと
  - **直前に確定した語（recent_words）が空**であること。
    これは補正の材料になるが、起動直後は必ず空。空でない状態で
    作った控えは、起動時の状態と食い違うので使わない
  - エンジンの版（下の ENGINE_STAMP）が同じこと

ひとつでも合わなければ、控えをまるごと捨てて普通に解析する。
**疑わしいときは使わない**（設計原則3と同じ構え）。

**この控えはユーザーのメモそのもの**（原文と補正結果）を含むので、
`.gitignore` に入れてリポジトリへは絶対に上げないこと。
"""

import json
import os
import zlib

# エンジンの版。**補正の中身を変えたら必ず上げること。**
# 上げ忘れると、古い版の結果を新しいエンジンのものとして表示して
# しまう。開発中（.py で動かしているとき）は下の
# `_engine_source_stamp()` が原型ファイルの大きさも見るので
# 自動で食い違いに気付けるが、exe では効かない。
# 2026-08-11c: 項目48-U（前の語に付く語の手前では割らない）で
# 補正の答えが変わった（実機のメモで10行）。上げないと、
# 古い答えを新しいエンジンのものとして表示してしまう。
# 2026-08-11d: 項目48-V（正しく読めた語の途中から窓を始めない）。
# 2026-08-11e: 項目48-W（読めているカタカナ語は溶かさない）。
# 2026-08-11f: 項目48-AA（わざと書いた単体の濁点を消さない）。
# 2026-08-11g: 項目48-AE（連接コストで「読める」を判断する）。
# 2026-08-11j: 項目48-AM（残す側の物差しを絞った。_is_solid）。
# 2026-08-11k: 項目48-AP（送り仮名が無ければ、語幹の読みは使わない）。
# 2026-08-11m: 項目48-AQ（記号が語と数を繋いでいたら式・識別子）。
#              **`l` は数字の1と紛れるので飛ばした。**
# 2026-08-11n: 項目48-AU（漢字1文字は「解析が崩れた印」にしない）。
# 2026-08-11p: 項目48-AV（候補そのものの近さを、支持の証拠にしない）。
# 2026-08-12a: 項目48-AO（打つ順番が入れ替わった濁点・半濁点）／
#              48-AY（48-AV の取り消し）／48-AW・48-BA・48-BB
#              （最初から持っている単語リスト）。
# 2026-08-12b: 項目48-BH〜48-BM（ひらがな→カタカナの種／英語側の
#              audit／文字の並びの検品）。
# 2026-08-12c: 項目48-BN（文字の並びの表をメモから育てる）。
# 2026-08-12d: 項目48-BO / 48-BP（解析の速さ。**補正結果は1行も
#              変わらない**が、控えの作り方が変わるので上げる）。
#              **この表は ENGINE_STAMP を上げなくても育つ**ので、
#              見分けに `charngram` を足した。
# 2026-08-12e: 項目48-BT（控えの見分けを件数から revision へ）／
#              48-BU（触らない語を SCOWL size 70 へ広げた。
#              `callout → fallout` が消える）。
# 2026-08-12f: 項目48-BV（文脈語彙の控えの見分けを shape_revision へ）。
#              消したはずの語が文脈語彙に残っていた。
# 2026-08-13a: 項目48-BY（方針2に「証拠の太さ」の関門を足した）。
#              共通の共起相手が1語だけの類似度を信じていて、
#              `判断の精度` が `判断の制度` に化けていた。
# 2026-08-19a: 項目48-FU（シフトを押し損ねた拗音を漢字にして戻す。
#              `きようちよう ⇒ 強調`）。**新しい直しが増える**ので
#              上げる。実機メモは1行も変わらない（見本の門で守る）。
# 2026-08-19b: 項目48-FX（濁音・半濁音は2打鍵。1文字違いは隣接キーの
#              ときだけ。隣接判定は入力方式で変わる）。
#              **触らなくなるものが増える**（実機メモ 89 → 86 行）。
# 2026-08-19c: 項目48-FY（`つあがり` はローマ字限定。ローマ字では
#              かな1文字の違いが**脱字**のことがあるので通す）。
#              ローマ字入力のときだけ答えが変わる。
# 2026-08-19d: 項目48-FZ（混合塊の経路にも 48-FX の門を通す）。
#              `_resolve_reading_list` / `_resolve_kanji_split` へ
#              `input_method` を渡した。
# 2026-08-19e: 項目48-GB（打ち切りの取りこぼしを直した＋読みの木）。
#              **速さだけの変更ではない**——打ち切りが取りこぼして
#              いた候補が見えるようになるので、まれに答えが変わる
#              （実機メモ・readcheck では diff 0行だった）。
# 2026-08-19f: 項目48-GC（木の取りこぼしを直した＋先の見込み）。
#              置き換えの費用表を `ALL_KANA` で作っていたので、
#              **を・ゐ・ゎ を含む読みへ辿り着けなかった**。
#              取りこぼしていた候補が戻るので、答えが変わりうる
#              （実機メモ・readcheck では diff 0行だった）。
# 2026-08-19g: 項目48-GE（読みを割り出すビームを、読みの木に乗せた）。
#              `set` を回す順で決まっていた**同点の決着**が、
#              並べ直した木の順に変わる。readcheck で1件動いた
#              （化けが別の化けになっただけ。合計は同じ。
#                しかも前の版では**種次第でどちらにもなっていた**）。
# 2026-08-19h: 項目48-GG（末尾の機能語を「途中まで」剥がした形も
#              芯の候補にする）。`あぎらかを → あきらかを`。
#              **新しく届く直しが増える**ので上げる。
# 2026-08-19i: 項目48-GH（直前が漢字のとき剥がした窓の先頭を、
#              2文字までなら**全部**戻す）。`昨日こもれひを →
#              昨日こもれびを`。**新しく届く直しが増える**。
# 2026-08-19j: 項目48-GI（ひらがな連続の道にも、48-FX の
#              「1文字違いは隣のキーのときだけ」を掛けた）。
#              **触らなくなるものが増える**（`こかかん → こうかん`
#              が止まる。かな入力では `きーぼーそ` も止まる）。
# 2026-08-19k: 項目48-GJ（ひらがな連続で先頭を助詞と見て切るのは、
#              **直前に語があるときだけ**）／項目48-GK（**拗音で
#              終わる読みを「活用の断片」扱いしない**。辞書・解除・
#              削除・場所・後者・神社… 534件が直し先として
#              見えていなかった）。**答えが大きく変わる。**
# 2026-08-20a: 項目48-GZ（門の掛け忘れ 5例目・6例目）。
#              **独立したひらがな連続の道**に、芯の再構築が持って
#              いた形だけの門5つを同じに掛けた（末尾の機能語を
#              剥がすと1文字／`を` を含む／終わりが機能語の途中／
#              擬態語／語頭・語末に立たない文字——端は**切った端
#              にだけ**）。あわせて**芯の頭側**に「守る語＋1文字は
#              触らない」を足した。`1つにする。→ 1つくる。` と
#              `ああつにする。→ あいつにする。` が**触らない**に
#              変わる。**触らなくなるものが増える**（実機メモは
#              1行だけ変わる）。
# 2026-08-20b: 項目48-HA（設計25(甲)＋(乙)）。**IME が確定した
#              「表記 → 打った読み」の対を覚え、逆算より先に使う。**
#              `奥悠久子帝` のように**逆算では読みが1つも作れない**
#              塊でも、打った行なら読みが手に入る（項目48-GU の壁①②
#              が消える）。**土俵が広がる向きの変更**なので、
#              いままで「読めないから触らない」で守られていた塊が
#              判断の対象になる（項目48-GU の但し書き）。
#              **対が空なら答えは1件も変わらない**（差していない
#              ときは素通り）。見分けに `ime_readings` を足した。
# 2026-08-20c: 項目48-HB（設計25(乙) の引き方を変えた・案B）。
#              表記の完全一致では**実質引けなかった**（実機51行で
#              変わった行 0・項目48-HA §7-b。対は「IME が一度に
#              確定した範囲」、エンジンが聞くのは「塊」で、塊は語では
#              ないため）。**塊の中を対の表記で切り分けて読みを
#              組み立てる**ようにした（`該当あの範囲` ＝ `該当`＋
#              `あ`＋`の`＋`範囲`）。かなは素通し・覆えない字は逆算で
#              補い、**対を1つも使わない組み立ては返さない**。
#              **1文字だけの対は塊の中では使わない**（`表→おもて` が
#              `時刻表` に紛れないように）。**対が空なら答えは
#              1件も変わらない**のは今までどおり。
ENGINE_STAMP = '2026-09-04e'   # 48-ME〜MN 一番下の守り・タブを跨がない範囲・う挿入・お/ごの接頭・かなの漢語を変換・長さと手・変換の錨に2字の漢語・かな連続を「を」で区切る・48-LC の床を2字の漢語で越える・音読みを形で見分ける・紫の誤検知2種・の でも区切る／横ずれは採らない・印の範囲だけ開く・組み立ての受け皿を手を当てた読みにも・**拗音の小書きどうし**・錨は先頭でなくてよい・**名詞どうしの複合は作れる**・**要素の1字（素辞項）**・連用形＋1字は見ない・**本道でも語の組み立て**・**書かれ方は変えない**・打ち切りは順を決めてから・直した読みをそのまま漢字へ・丸ごと1語の床を2へ・**ローマ字入力はローマ字の隣接キーだけを見る**・異様な1字の漢字をかなに開く・ナ形容詞の語幹＋動詞は異様／そこに に を入れる・数字の直後の連なりは触らない・打った読みの記録を門にしない・副詞＋に の後ろには用言・活用形の接続・漢字で書く既知語で芯を切る・複合辞は1語・**接尾辞＋用言**・未然形の誤爆を潰す・開いた読みの手当ても入力方式で・ナ形容詞の語幹は名簿で・**印を落としただけなら元に戻す**・**索引に2字漢語の帯と段（kango_tier）・索引の顔で決める（48-OJ）**・形容動詞語幹＋化（48-OK）・1字の ん と余分な隣のキー（48-OL）・印のキーの隣を開いた読みにも（48-OM）・名詞に続く機能語（48-ON）・**48-MI に索引の顔を既定 ON（48-OO）**・う の位置ずれ（48-OP）・田部井号して（48-OQ）・固有名詞は後段へ（48-OR）・F2 の単位（48-OS/OT）・**口語の縮約とら抜き（48-OU）**・1字の訓読み名詞＋動詞（48-OV）・感動詞＋格助詞だけ（48-OW）・名詞＋疑問の代名詞（48-OX）・**カタカナ語の出どころ（48-OY/OY')**・切り詰めは採らない（48-OZ）・組の余り（48-PA）・連打の畳みと伸ばし棒に①（48-PB/PB'）・**音訓表の穴を埋める（48-PE）**・読みの型の表（48-PD）・音訓の型で②の順位（48-PC）・読める読みが在ったら敷居を上げる（48-PF）・**文法の仕事をしている隙間は書き換えない（48-PG）**・尻尾まで変わる変換は漢語の変換ではない（48-PH）・**助詞のトークンで区切る（48-PI）**・よく使う語の動詞の活用（48-PJ）・**動詞基本形＋名詞は「読める」に数えない（48-PL）**・補助動詞は て形のあとだけ（48-PP）・てんの（48-PS）・接尾＋接尾（48-KZ(G)）・**余分な隣のキーは①が立つ塊だけ（48-PL(b')）**・直し先が語＋1字助詞なら採らない（48-PK）・カタカナのサ変＋語→後（48-PQ）・**異様の対の範囲だけを読みで置き換える受け皿（48-PO）**・読みの立たないカタカナ断片は塊に含める（48-PT）・**壊れた形の見本の並記に引きずられない（48-PX/PY）**

# 控えの形式の版。作りを変えたら上げる（古い控えは捨てられる）。
CACHE_VERSION = 1

# 控えに残す行数の上限（全タブ合計）。メモが極端に大きいときに
# 控えのほうが重くならないようにする。
MAX_CACHED_LINES = 20000


def _crc(text):
    return zlib.crc32(text.encode('utf-8', 'ignore'))


def _vocab_stamp(store):
    """
    語彙の見分け。**中身から作る**（ファイルの更新時刻ではない）。

    起動時に英単語を覚え直すので vocabulary.json は毎回書き換わる。
    更新時刻で見ると控えが一度も使えない。中身を見れば、
    「同じメモから同じものを覚え直しただけ」なら同じ値になる。

    最後に使った日（last_seen）は入れない。覚え直しのたびに変わる
    が、補正の判断には**使用回数のほうしか効かない**ため
    （減衰は last_seen を見るが、日をまたがなければ同じ）。
    順番に依らないよう XOR で畳む（並べ替えの手間を省くため）。
    """
    try:
        entries = store.to_list()
    except Exception:
        return None
    n = 0
    total = 0
    mixed = 0
    for e in entries:
        n += 1
        c = int(e.get('count') or 0)
        total += c
        mixed ^= _crc(f"{e.get('reading')}\t{e.get('surface')}\t{c}")
    return [n, total, mixed]


def _context_vec_stamp(context_vec):
    """文脈ベクトルの見分け（語数と、共起相手の総数）。"""
    if context_vec is None:
        return None
    try:
        co = context_vec._co
        return [len(co), sum(len(v) for v in co.values())]
    except Exception:
        return None


def _small_store_stamp(obj, methods):
    """
    判断（decisions）・選び直し（choices）の見分け。

    どちらも件数は多くない（実機で 0〜数件）ので、中身をそのまま
    文字列にして畳んでよい。**件数だけでは足りない**: 1つ取り消して
    1つ足すと件数が変わらないため。
    """
    if obj is None:
        return None
    parts = []
    for name in methods:
        try:
            got = getattr(obj, name)()
        except Exception:
            return None
        parts.append(sorted(repr(x) for x in (got or ())))
    try:
        return [len(obj), _crc(repr(parts))]
    except Exception:
        return [-1, _crc(repr(parts))]


def _charngram_stamp():
    """
    文字の並びの表の見分け（項目48-BN）。

    **この表はメモから育つ**ので、`ENGINE_STAMP` を上げなくても
    中身が変わる。控えたまま使うと、育つ前の判断が残る。
    育てた行数と3連の種類だけ見れば足りる。
    """
    try:
        import charngram
        return list(charngram.stats())
    except Exception:
        return []


def _dict_index_stamp(dict_index):
    if dict_index is None:
        return None
    try:
        st = dict_index.stats()
        return [st.get('readings'), st.get('surfaces')]
    except Exception:
        return None


def _engine_source_stamp(app_dir):
    """
    エンジンの原型ファイルの見分け。

    開発中は .py が手元にあるので、その大きさを見て
    「エンジンが変わったのに ENGINE_STAMP を上げ忘れた」を
    自動で拾う。exe では原型が無いので空になり、
    ENGINE_STAMP と APP_VERSION だけが頼りになる。
    """
    # **最初に呼ばれたとき（起動時の読み込み）の大きさを覚えて、以後は
    # それを返す**（項目48-IW・2026-08-23・実機で発覚）。
    #
    # 保存のたびにディスクを見ると、**動いているエンジンと指紋がずれる**:
    # 古いエンジンで起動したまま `corrector.py` を差し替え、閉じるときに
    # 控えを保存 → 指紋は新しいファイルの大きさ・答えは古いエンジン。
    # 起動し直したアプリは指紋が一致するので**古い答えをそのまま使う**
    # （`外しょつする → 外ショーツする` が直した後も残った）。
    # 指紋は「この答えを出したエンジン」を表すものなので、読み込んだ
    # ときの大きさで固定する。
    global _ENGINE_SOURCES_SEEN
    try:
        _seen = _ENGINE_SOURCES_SEEN
    except NameError:
        _seen = None
    if _seen is not None and _seen[0] == app_dir:
        return list(_seen[1])
    out = []
    for name in ('corrector.py', 'vocabulary.py', 'kana_layout.py',
                 'halfwidth.py', 'loanword.py', 'morphology.py',
                 'kanji_guess.py', 'context_vec.py', 'dict_index.py',
                 'okurigana.py', 'naturalness.py', 'charngram.py',
                 'ngram_ja.py',
                 # **単語リストも補正の答えを変える**（項目48-BU で
                 # 触らない語を広げたら `callout` の扱いが変わった）。
                 # 中身だけ差し替えたときに気付けるよう、ここに置く。
                 'seed_english.py', 'seed_katakana.py',
                 # **1語として在るかの表**（項目48-FC）。
                 # 差し替えると補正の答えが変わるので見張る。
                 'seed_japanese.py', 'seed_japanese.txt.gz'):
        try:
            out.append(os.path.getsize(os.path.join(app_dir, name)))
        except Exception:
            pass
    _ENGINE_SOURCES_SEEN = (app_dir, list(out))
    return out


_ENGINE_SOURCES_SEEN = None


def _ime_readings_stamp(ime_readings):
    """
    **IME の読みの対**の見分け（設計25(乙)・項目48-BN と同じ形）。

    この置き場は**打つたびに育つ**ので、`ENGINE_STAMP` を上げなくても
    補正の答えが変わる。控えたまま使うと、**対を覚える前の判断**が
    残る（`奥悠久子帝` を打つ前に解析した行が、そのまま残る）。
    """
    if ime_readings is None:
        return None
    try:
        return list(ime_readings.stamp())
    except Exception:
        return None


def build_fingerprint(app_dir, app_version, input_method, recent_words,
                      store=None, context_vec=None, dict_index=None,
                      decisions=None, choices=None, ime_readings=None):
    """
    「この控えを作ったときの状況」をひとまとめにする。

    recent_words: 直前に確定した語。**空でないなら控えは作らない**
        （起動直後は必ず空なので、食い違いのもとになる）。
    戻り値: 照合に使う辞書。作ってはいけない状況なら None。
    """
    if recent_words:
        return None
    return {
        'cache_version': CACHE_VERSION,
        'engine': ENGINE_STAMP,
        'app_version': app_version,
        'engine_sources': _engine_source_stamp(app_dir),
        'input_method': input_method,
        'vocab': _vocab_stamp(store),
        'context_vec': _context_vec_stamp(context_vec),
        'dict_index': _dict_index_stamp(dict_index),
        'charngram': _charngram_stamp(),
        'ime_readings': _ime_readings_stamp(ime_readings),
        'decisions': _small_store_stamp(
            decisions, ('rejected_list', 'protected_list')),
        'choices': _small_store_stamp(choices, ('all_records',)),
    }


def _pack(result):
    """
    1行ぶんの結果を、控えに残せる形にする。

    `correct_line` が返す鍵をそのまま持つ（`changed` は
    original と corrected から作り直せるので持たない）。
    **鍵を増やしたら、ここと `_unpack` の両方に足すこと。**
    足し忘れると、その情報だけが控え経由で失われる。
    """
    return {
        'o': result.get('original', ''),
        'c': result.get('corrected', ''),
        'd': [list(x) for x in (result.get('details') or ())],
        's': [list(x) for x in (result.get('spans') or ())],
        'u': [list(x) for x in (result.get('unsure_spans') or ())],
        'os': [list(x) for x in (result.get('original_spans') or ())],
        # 異様と見た範囲（項目48-IR・紫）
        'od': [list(x) for x in (result.get('odd_spans') or ())],
        # **なぜ異様と見たのか**（項目48-MD・2026-08-31）。
        # 候補一覧の「－ 補正根拠 －」だけが読む。控えから欠けても
        # 画面がその場で測り直せるので、古い控えでも困らない。
        'or': [list(x) for x in (result.get('odd_reasons') or ())],
    }


def _unpack(item):
    """控えから1行ぶんの結果に戻す。"""
    original = item.get('o', '')
    corrected = item.get('c', '')
    return {
        'original': original,
        'corrected': corrected,
        'changed': corrected != original,
        'details': [tuple(x) for x in (item.get('d') or ())],
        'unsure_spans': [tuple(x) for x in (item.get('u') or ())],
        'spans': [tuple(x) for x in (item.get('s') or ())],
        'original_spans': [tuple(x) for x in (item.get('os') or ())],
        'odd_spans': [tuple(x) for x in (item.get('od') or ())],
        'odd_reasons': [tuple(x) for x in (item.get('or') or ())],
    }


def save(path, fingerprint, tabs):
    """
    控えを書き出す。

    tabs: {タブの本文（文字列）: [1行ぶんの結果, ...]}
        本文そのものを鍵にするので、タブの並べ替えにも耐える。
    fingerprint が None（作ってはいけない状況）なら、
    **古い控えを消して**何も書かない。残しておくと、次の起動で
    食い違った控えを読もうとしてしまう。
    """
    if not path:
        return False
    if fingerprint is None:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
        return False
    entries = []
    total = 0
    for text, results in (tabs or {}).items():
        if not text or results is None:
            continue
        lines = text.split('\n')
        if len(lines) != len(results):
            continue        # 食い違っている控えは残さない
        if total + len(lines) > MAX_CACHED_LINES:
            continue
        total += len(lines)
        entries.append({'text': text,
                        'results': [_pack(r) for r in results]})
    if not entries:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
        return False
    data = {'fingerprint': fingerprint, 'tabs': entries}
    try:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def load(path, fingerprint):
    """
    控えを読む。状況が少しでも違えば {} を返す（使わない）。

    戻り値: {タブの本文: [1行ぶんの結果, ...]}
    """
    if not path or fingerprint is None or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    if data.get('fingerprint') != fingerprint:
        return {}       # 状況が違う。まるごと捨てる
    out = {}
    for entry in data.get('tabs') or ():
        try:
            text = entry['text']
            results = [_unpack(x) for x in entry['results']]
        except Exception:
            continue
        if len(text.split('\n')) != len(results):
            continue
        # 控えの中身と本文が食い違っていないかも見る
        # （ここが崩れていたら、その控えは信用できない）。
        if any(r['original'] != l
               for r, l in zip(results, text.split('\n'))):
            continue
        out[text] = results
    return out
