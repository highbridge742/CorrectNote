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
**画面まわり**（設定・配色・ドラッグ・タブ・検索・保存）の試験。

`tests_mock.py` から分けたもの（2026-08-20・項目48-GQ）。
**走らせる入口は `tests_mock.py` のまま。**
"""
import corrector as C
from vocabulary import VocabularyStore, find_known_readings_flex
from seed_vocabulary import load_seed

from tests_mock_common import mock_tokenize


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

    # --- 辞書の1件を取り込むかどうか（2026-08-10 に作り直した）---
    # 以前は「品詞が取れないビルドがある」という前提で、表記の
    # パターン（山・川・岩・鼻…で終わる、カタカナ5文字以下…）だけで
    # 地名を弾こうとしていた。実際には**品詞が読めていなかった**のが
    # 原因で（compact 側を見ていたが、品詞は extra 側にある）、
    # 手書きのふるいは日常語まで巻き添えにしていた。
    from janome_import import (accept_entry as _acc,
                               _parse_compact as _pc,
                               _parse_extra_pos as _pep)

    # 品詞は extra 側から取る。コストは4番目から取る（最大値の
    # 当てずっぽうではない）。
    check('compact から表記とコストを取る',
          _pc(('焼崎鼻', 1288, 1288, 8538)), ('焼崎鼻', '', 8538))
    check('extra から品詞を取る',
          _pep(('名詞,固有名詞,一般,*', '*', '*', '焼崎鼻',
                'ヤケザキバナ', 'ヤケザキバナ')),
          '名詞,固有名詞,一般,*')
    check('並びが違っても品詞を拾える',
          _pep(('*', '*', ('名詞,一般,*,*',), 'ドラッグ')),
          '名詞,一般,*,*')

    # 地名・人名は**品詞（固有名詞）で**弾く
    for _place in ('神奈川県', '横浜市', '渋谷区', '富士山', '琵琶湖',
                   '淡路島', '東京駅', '浅草寺', '大阪城',
                   'アナマ岩', 'アボ鼻', 'ウノ瀬', 'カナデ鼻',
                   'アシカ碆', 'ウロウ根', 'アヤメ平', '巽ノ瀬',
                   'イチロー', 'オックスフォード'):
        check(f'固有名詞は取り込まない: {_place}',
              _acc(_place, '名詞', '固有名詞', '一般', 3000), False)

    # 日常語は取り込む（以前のふるいで落ちていたものを含む）
    for _word, _sub, _cost in (('ドラッグ', '一般', 3647),
                               ('クリック', '一般', 3657),
                               ('コピー', 'サ変接続', 3871),
                               ('ファイル', 'サ変接続', 4426),
                               ('メモ帳', '一般', 4000),
                               ('コピー機', '一般', 4000),
                               ('入力', 'サ変接続', 4460),
                               ('変換', 'サ変接続', 4463),
                               ('該当', 'サ変接続', 4427),
                               ('説明文', '一般', 3000),
                               ('谷間', '一般', 3000),
                               ('市場', '一般', 3000),
                               ('文章', '一般', 3000)):
        check(f'日常語は取り込む: {_word}',
              _acc(_word, '名詞', _sub, '*', _cost), True)

    # 品詞以外の理由で落とすもの
    check('記号を含む語は取り込まない',
          _acc('ヤンキー・ドゥードル', '名詞', '一般', '*', 3000), False)
    check('品詞が対象外なら取り込まない',
          _acc('しかし', '接続詞', '*', '*', 3000), False)
    check('コストが高すぎる語は取り込まない',
          _acc('帰農', '名詞', '一般', '*', 9000), False)

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

    # （カタカナ+漢字の小地名は、上の accept_entry の回帰で見ている）
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
    # **`つあがり` はローマ字限定**（項目48-FY・うにさんの確認・
    # 2026-08-19「つあがり、これはローマ字限定補正です。
    # かな入力では対象外です」）。
    # ローマ字なら `tuagari` → `tunagari` の**脱字**、
    # かな入力なら あ(3) と な(U) の**遠い置き換え**になる。
    _r = _cl('単語のつあがり', im='romaji')
    check('つあがり→つながり（**ローマ字限定**。n の脱字）',
          _r['corrected'], '単語のつながり')
    _r = _cl('単語のちながり')
    check('ちながり→つながり（かな）', _r['corrected'], '単語のつながり')
    _r = _cl('たんほの繋がり', im='romaji')
    check('たんほ→たんご（ローマ字: h/g が QWERTY で隣接）',
          _r['corrected'], 'たんごの繋がり')

    # --- 配列上で遠い取り違えは、**かな入力では直さない** ---
    #
    # **ここは2度向きが変わっている。記録として両方残す。**
    #
    #   〜第38回  「かな入力では確信が持てない」として色だけ付けた
    #   第39回頃  「ひらがなに直し、隣接キーや脱字などを考慮して
    #             再構築する」の指定に合わせ、遠い取り違えも直した
    #   項目48-FX（2026-08-19）**うにさんの指定で、また直さない側へ**:
    #             「かな入力において、濁音、半濁音は2打鍵である
    #               ことを考慮します。… 1文字違うだけでは補正
    #               しません、その違いが隣接キーかどうか。
    #               隣接判定はかな入力とローマ字入力で変わる。」
    #
    # `ご` は `こ(B)＋゛(@)` の2打鍵。`ほ(-)` とは遠い。
    # **ローマ字入力なら `ho → go` は隣**なので、すぐ上の
    # romaji の組は今までどおり直る。**そこが分かれ目。**
    _r = _cl('たんほの繋がり', im='kana')
    check('たんほ→たんご は、かな入力では直さない（項目48-FX）',
          _r['corrected'], 'たんほの繋がり')
    # ★★ **重複打鍵の直しは 2026-09-08 から既定オフ**（項目48-VH・
    # うにさんの指定「**同一キーの連続重複を1つに補正する機能自体を
    # 無効にしてください。無効でしばらく様子を見て問題がなければ
    # 機能削除します**」）。**消さずに、意図を裏返して残す**——
    # 削るときに何を削るのかが、ここを読めば分かる。
    # 戻すのは `CN_NO_DUP=0`（**import より前**に置くこと。
    #  `vocabulary._REPEAT_GAP_COST` は読み込みのときに決まる）。
    _r = _cl('たああんごの繋がり')
    check('48-VH たああんご は直さない（連打の巻き戻しは既定オフ）',
          _r['corrected'], 'たああんごの繋がり')
    import vocabulary as _v_dup
    check('48-VH 栓は 1 か所で決めている（既定オフ）',
          _v_dup.dup_repair_enabled(), False)
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
    #
    # ここは以前、色の名前を**手で並べたタプル代入**だった。列挙し
    # 忘れた色はテーマを切り替えても前の値のまま残る——`UNSURE_BG`
    # の足し忘れで「ダークモードで白背景に白文字」になり、**実機で
    # 2度**報告された。このテストはその見張りとして書かれた。
    #
    # **3度目が出た**（項目48-IF・2026-08-21。空白の印の色6つを
    # 足すときに、やはりここへ足し忘れた）。**同じ形の不具合が3度
    # 出たら、形のほうを直す。** 並べるのをやめて、名簿
    # （`_PALETTE_KEYS`）から回すようにした。
    #
    # だから見張りも作り直す。見るのは**名簿から回していること**と、
    # **名簿と2つのパレットの鍵が完全に一致すること**の2つ。
    # こうしておけば、色を足したときに足し忘れる場所は**無い**。
    import re as _re3
    check('パレットは名簿(_PALETTE_KEYS)から回している',
          'globals().update({k: pal[k] for k in _PALETTE_KEYS})' in _src,
          True)
    check('手で並べたタプル代入は残っていない',
          _re3.search(r"\(BG, PANEL,.*?\) = \(", _src, _re3.S) is None,
          True)
    _keys_m = _re3.search(r"_PALETTE_KEYS = \[(.*?)\]", _src, _re3.S)
    _keys = _re3.findall(r"'(\w+)'", _keys_m.group(1)) if _keys_m else []
    check('名簿が空でない', len(_keys) >= 19, True)
    _dark_m = _re3.search(r"DARK_PALETTE = \{(.*?)\n\}", _src, _re3.S)
    _dark_keys = (_re3.findall(r"'(\w+)':", _dark_m.group(1))
                  if _dark_m else [])
    check('名簿とダークの鍵が一致', sorted(_keys), sorted(_dark_keys))

    # --- 空白の印は「地色の箱」に戻さない（項目48-IG） ---
    #
    # 地色の箱には**2つの困り事**があって、実機で報告された:
    #   (1) 折り返しの境目に来た空白は**右端まで引き伸ばされる**ので、
    #       半角か全角か分からなくなる（画素で 6px→27px/63px を確認）
    #   (2) 箱は**必ず行の高さいっぱい**に描かれる。タグに小さい字を
    #       指定しても縮むのは**幅**（＝本文がずれる）だけで、
    #       塗られる高さは変わらない（画素を数えて確認）
    # だから半角・全角は**下線**にした。ここはその見張りである。
    # タブだけは Tk が下線を引かないので地色のまま（薄く・枠なし）。
    _ws_m = _re3.search(r"for _t, _c in \(\('ws_sp_a'.*?"
                        r"def _schedule_whitespace_paint",
                        _src, _re3.S)
    _ws_src = _ws_m.group(0) if _ws_m else ''
    check('半角・全角の印は下線', 'underline=True' in _ws_src, True)
    # **中央の線（打ち消し線）はやめた**（項目48-II）。
    # **伸ばし棒 `ー` と紛れる**と実機で報告された。高さは
    # 「うんと薄い四角」で出す（Tk は四角を低くできない。測った）。
    check('中央の線は引かない（伸ばし棒と紛れる）',
          'overstrike=False' in _ws_src, True)
    # **スペースに地色は付けない**（項目48-IJ）。
    # 「地色は目立つ」とうにさんから報告された。地色を持つのは
    # タブだけ（Tk はタブに線を引けないため）。
    check('スペースに地色を付けない', "background=''" in _ws_src, True)
    check('線の色は灰色（無彩色）', 'WS_LINE_A' in _ws_src, True)
    check('印を下げる offset は使わない（行の間隔が伸びる）',
          'offset=' not in _ws_src, True)
    # **折り返しの境目では四角を消す**（項目48-II）。
    # Tk は表示行の最後の塊の地色を右端まで塗るので、そのままだと
    # 半角が全角より広く見える（項目48-IG で直したところ）。
    check('折り返しの境目で帯を消す仕組みがある（タブ用）',
          'def _wrap_edge_columns' in _src and 'WS_NOBOX' in _src, True)

    # --- 本文より下の左ドラッグは、スクロールにしない（項目48-IM） ---
    #
    # 束縛のところには前から「左ボタンは範囲選択に専念させる。
    # スクロールは右ドラッグに移す」と書いてあったのに、
    # `_on_editor_blank_press` だけが左ドラッグを横取りしていた
    # （学び22）。指（タッチ）の1本指スクロールは残す。
    _bp = _re3.search(r"def _on_editor_blank_press\(self, event\):(.*?)"
                      r"def _on_editor_blank_drag", _src, _re3.S)
    _bp_src = _bp.group(1) if _bp else ''
    check('本文より下でも、マウスの左ドラッグはスクロールにしない',
          'if not is_touch_pointer():' in _bp_src, True)
    check('指（タッチ）の1本指スクロールは残っている',
          'is_touch_pointer' in _bp_src and '_blank_drag' in _bp_src, True)

    # --- 終端の罫線（項目48-IM） ---
    #
    # 空行には字が無いので、下線も打ち消し線も引けない（描いて確認）。
    # **その行の字を小さくして、地色を敷く**しかない。
    # カーソルがその行に居る間は引かない——引くと行が4pxになり、
    # **カーソルまで4pxになって見えなくなる**。
    _er = _re3.search(r"def _paint_end_rule\(self\):(.*?)"
                      r"\n    def ", _src, _re3.S)
    _er_src = _er.group(1) if _er else ''
    check('終端の罫線を引く仕組みがある', bool(_er_src), True)
    # **基準は「最後の改行」ではなく「最後の文字」**（うにさんの指定・
    # 2026-08-22）。`Ctrl+A`（`_on_select_all`）が選ぶ範囲の終わりと
    # 同じ数え方（`strip()`）で、中身のある最後の行を探し、その
    # **ひとつ下の行**に引く。末尾に空行がいくつ続いても、罫線は
    # **文字のすぐ下**に来る。
    check('中身のある最後の行を Ctrl+A と同じ数え方で探す',
          'lines[k - 1].strip():' in _er_src, True)
    check('引くのは、そのひとつ下の行',
          'target = last_text + 1' in _er_src, True)
    check('その下に行が無ければ引かない',
          'if target > len(lines):' in _er_src, True)
    check('カーソルがその行に居る間は引かない',
          'if cur == target:' in _er_src, True)
    check('罫線は字を小さくして作る（下線では描かれない）',
          'END_RULE_FONT_SIZE' in _src, True)

    # --- 印を置く欄は名簿1つ（項目48-IH） ---
    #
    # うにさんの指定「**簡易入力にも実装してください。オプションは
    # 共通です**」。欄ごとに書き足すと、学び22「片方だけに置くと、
    # そちらを迂回して素通りする」がまた出る。`_whitespace_targets`
    # 1箇所から回す形にして、**簡易入力欄が入っていること**を見る。
    _tg = _re3.search(r"def _whitespace_targets\(self\):(.*?)"
                      r"def _configure_whitespace_tags", _src, _re3.S)
    _tg_src = _tg.group(1) if _tg else ''
    for _name in ('editor', 'result_view', '_quick_text'):
        check(f'空白の印を置く欄に {_name} が入っている',
              f"'{_name}'" in _tg_src, True)
    check('塗るのは名簿から回している',
          _src.count('self._whitespace_targets()') >= 2, True)

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
    # 項目48-IG で「半角と全角は同じ色」の例外を入れたが、
    # **項目48-II で色の役割を分けた**（線＝`WS_LINE_*`／
    # 四角＝`WS_BOX_*`／タブ＝`WS_TAB_*`）ので、重複はもう無い。
    # 元々この見張りを置いた理由（「元の色→新しい色」で対応を付ける
    # ので曖昧になる）は項目48-IF で消えているが、
    # 「別の意味の色が同じ」を捕まえる見張りとしては残す。

    def _uniq(pal):
        vals = list(pal.values())
        return len(set(vals)) == len(vals)

    # **線は灰色**（うにさんの指定・項目48-IJ）。
    # R=G=B かどうかで見る（背景に寄せた暖色・寒色の灰は不可）。
    for _pal, _nm in ((light, 'LIGHT'), (dark, 'DARK')):
        for _k in ('WS_LINE_A', 'WS_LINE_B'):
            _h = _pal[_k].lstrip('#')
            _rgb = tuple(int(_h[i:i + 2], 16) for i in (0, 2, 4))
            check(f'{_nm} の {_k} は灰色（R=G=B）',
                  _rgb[0] == _rgb[1] == _rgb[2], True)

    # **線は背景に近い**（項目48-IK・うにさんの指定「存在感を減らして」）。
    # 明るすぎると「存在感が強い」と戻ってしまい、暗すぎると見えない。
    # 5段階を描いて選んだ幅（差 45/29・ダークは 37/20）から外れたら鳴る。
    def _lum(hexstr):
        h = hexstr.lstrip('#')
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        return 0.299 * r + 0.587 * g + 0.114 * b

    for _pal, _nm in ((light, 'LIGHT'), (dark, 'DARK')):
        _bg = _lum(_pal['PANEL'])
        _ga = abs(_lum(_pal['WS_LINE_A']) - _bg)
        _gb = abs(_lum(_pal['WS_LINE_B']) - _bg)
        check(f'{_nm}: 濃いほうの線は背景に近い（差 25〜60）',
              25 <= _ga <= 60, True)
        check(f'{_nm}: 淡いほうの線は見える程度に残る（差 15〜40）',
              15 <= _gb <= 40, True)
        check(f'{_nm}: 2色に数え分けられる段差がある（8以上）',
              abs(_ga - _gb) >= 8, True)

    check('LIGHTパレット内に重複した色が無い', _uniq(light), True)
    check('DARKパレット内に重複した色が無い', _uniq(dark), True)
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

    # --- 簡易入力の縦幅も、同じ受け皿を通す（2026-09-04） ---
    # `_adjust_quick_size` が生の count('1.0','end','displaylines') を
    # int() に掛けていて、この環境（Python 3.9）ではタプルが返るため
    # 毎回 TypeError → 論理行数への退避になっていた。折り返しのある
    # 窓で「改行しても縦に伸びない」（実機の報告・2026-09-04）の原因。
    # 見張り: _adjust_quick_size は _displaylines_between を通し、
    # 生の count('…','displaylines') を直に呼ばないこと（学び22）。
    func8 = next(i for i in cls_node.body
                 if isinstance(i, ast.FunctionDef)
                 and i.name == '_adjust_quick_size')
    _calls8 = [n for n in ast.walk(func8) if isinstance(n, ast.Call)]
    check('簡易入力の縦幅は型ゆれの受け皿を通す',
          any(isinstance(c.func, ast.Attribute)
              and c.func.attr == '_displaylines_between'
              for c in _calls8), True)
    check('簡易入力の縦幅が生の count を呼んでいない',
          any(isinstance(c.func, ast.Attribute) and c.func.attr == 'count'
              and any(isinstance(a, ast.Constant)
                      and a.value == 'displaylines' for a in c.args)
              for c in _calls8), False)

    # --- キー名を指定した束縛は、IME の取り違えの受け皿を黙らせる ---
    # （項目48-IN・2026-08-22）。Tk は同じ欄に <KeyPress> と <Delete> の
    # 両方があると、keysym=Delete の打鍵では <Delete> だけを呼ぶ。
    # <KeyPress> に張った _on_ime_ascii_key は一度も呼ばれない。
    # テンキーの小数点は IME が入っていると keysym=Delete char='.' で
    # 届く（実機で測った）ので、<Delete> の個別束縛（項目48-ED）に
    # 横取りされて文字が消えていた。
    #
    # 見張り: 取り違えの対象のキー名（_IME_MISREAD_KEYSYMS）へ、
    # Ctrl/Alt 無しで個別に束縛している行は、全部
    #   (a) self._ime_first(...) で包んであるか、
    #   (b) 渡す先のメソッドが最初の行で _ime_fkey_insert を呼ぶか
    # のどちらかでなければならない。
    assign8 = next(n for n in tree.body
                   if isinstance(n, ast.Assign)
                   and any(getattr(t, 'id', '') == '_IME_MISREAD_KEYSYMS'
                           for t in n.targets))
    ns8 = {}
    exec(compile(ast.Module(body=[assign8], type_ignores=[]), '<f>', 'exec'),
         ns8)
    misread = ns8['_IME_MISREAD_KEYSYMS']
    app_cls = next(n for n in tree.body
                   if isinstance(n, ast.ClassDef)
                   and n.name == 'CorrectNoteApp')
    methods = {n.name: n for n in app_cls.body
               if isinstance(n, ast.FunctionDef)}

    def guarded_inside(name):
        fn = methods.get(name)
        if fn is None or not fn.body:
            return False
        body = fn.body
        if (isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)):
            body = body[1:]          # docstring を飛ばす
        first = body[0] if body else None
        if not isinstance(first, ast.Assign):
            return False
        value = first.value
        if isinstance(value, ast.IfExp):      # `x if event is not None else None`
            value = value.body
        return (isinstance(value, ast.Call)
                and isinstance(value.func, ast.Attribute)
                and value.func.attr == '_ime_fkey_insert')

    flagged = []
    unguarded = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'bind'
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            continue
        seq = node.args[0].value
        if not seq.startswith('<') or seq.startswith('<<'):
            continue
        parts = seq.strip('<>').split('-')
        # Ctrl/Alt を伴う束縛は IME の確定と型が違う（確定は
        # 修飾なしで届く）ので、同じ鍵に当たらない。
        if any(p in ('Control', 'Alt', 'Meta', 'Command', 'Mod1')
               for p in parts[:-1]):
            continue
        if parts[-1] not in misread:
            continue
        flagged.append(f'{node.lineno}: {seq}')
        if len(node.args) < 2:
            unguarded.append(f'{node.lineno}: {seq}（渡す先が無い）')
            continue
        h = node.args[1]
        wrapped = (isinstance(h, ast.Call)
                   and isinstance(h.func, ast.Attribute)
                   and h.func.attr == '_ime_first')
        inside = (isinstance(h, ast.Attribute) and guarded_inside(h.attr))
        if not (wrapped or inside):
            unguarded.append(f'{node.lineno}: {seq}')
    check('取り違えの対象のキー名への個別束縛が app.py に在る'
          '（見張りが空振りしていない）', len(flagged) >= 8, True)
    check('その束縛は全部 _ime_first で包むか、中で _ime_fkey_insert を'
          '先に呼ぶ', unguarded, [])

    # _ime_first そのものの動き（偽の self で回す）
    func8 = methods['_ime_first']
    ns9 = {'tk': __import__('types').SimpleNamespace(Listbox=type('LB', (), {}))}
    exec(compile(ast.Module(body=[func8], type_ignores=[]), '<f>', 'exec'),
         ns9)
    ime_first = ns9['_ime_first']

    class _Ev:
        def __init__(self, keysym, char, widget=None):
            self.keysym = keysym
            self.char = char
            self.widget = widget

    class _Self:
        def __init__(self):
            self.calls = []

        def _on_f2_range_keypress(self, e):
            self.calls.append('C-1')
            return None

        def _on_ime_ascii_key(self, e):
            self.calls.append('受け皿')
            return 'break' if e.char == '.' else None

        def _on_dropdown_keypress(self, e):
            self.calls.append('一覧C-1')
            return 'break' if e.char == '.' else None

    s = _Self()
    handler_calls = []
    wrapped = ime_first(s, lambda e: handler_calls.append(e) or 'done')
    check('IME が確定した `.`（keysym=Delete）は受け皿が先に取る',
          wrapped(_Ev('Delete', '.')), 'break')
    check('そのとき元の処理（範囲を消す）は呼ばれない', handler_calls, [])
    check('順番は <KeyPress> と同じ（C-1 → 受け皿）',
          s.calls, ['C-1', '受け皿'])
    s.calls.clear()
    check('本物の Delete（文字なし）は元の処理へ渡す',
          wrapped(_Ev('Delete', '')), 'done')
    check('そのとき元の処理に届いている', len(handler_calls), 1)
    check('イベント無しで呼ばれても元の処理へ渡す', wrapped(None), 'done')
    s.calls.clear()
    lb = ns9['tk'].Listbox()
    check('候補一覧（Listbox）では一覧の C-1 だけに回す',
          wrapped(_Ev('Delete', '.', lb)), 'break')
    check('一覧では受け皿（欄へ書く道）を通らない', s.calls, ['一覧C-1'])

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

    # ------------------------------------------------------------
    # 48-RA **新しく作るタブは1行目にブックマークが付く**
    # ------------------------------------------------------------
    # うにさんの指定（2026-09-05）「新規タブができた際、**1行目を
    # 自動でブックマークオンにする**」。
    #
    # ★★ **`new_tab` の既定にしてはいけない**——`new_tab` は
    # 「控えからの復元」と「1.5秒ごとの自動保存」も通る工場なので、
    # そこに置くと**本人が外した印が打つたびに戻る**。
    from session import fresh_tab
    check('新しく作るタブは1行目に印が付く',
          fresh_tab()['bookmarks'], [1])
    check('**素の `new_tab` は付けない**（復元と自動保存が通る道）',
          new_tab()['bookmarks'], [])
    check('呼び手が渡したら、そちらが勝つ（控えから戻す道）',
          fresh_tab(bookmarks=[3, 7])['bookmarks'], [3, 7])
    check('**空だと分かっている控えは空のまま**（外した印は戻らない）',
          new_tab(bookmarks=[])['bookmarks'], [])

    st2 = SessionStore()
    st2.reset_fresh()
    check('起動して新しく作る1枚にも印が付く',
          st2.tabs[0]['bookmarks'], [1])
    # **決めているのは `fresh_tab` の1か所**——呼び手は定数を知らない
    check('`set_single` は今までどおり印を付けない（控えを戻す道）',
          SessionStore().set_single('あ', None, True) or
          None, None)
    st2.add_tab()
    check('タブを足したら、そのタブにも印が付く',
          st2.tabs[1]['bookmarks'], [1])
    st2.add_tab(new_tab('控えから', bookmarks=[5]))
    check('控えを渡して足したら、その中身のまま',
          st2.tabs[2]['bookmarks'], [5])
    # **外した印が、閉じ直しても戻らないこと**
    st2.tabs[1]['bookmarks'] = []
    st2.update_active(new_tab('い', bookmarks=[]))
    check('自動保存の作り直しで印は戻らない',
          st2.tabs[2]['bookmarks'], [])
    while len(st2.tabs) > 1:
        st2.remove_tab(len(st2.tabs) - 1)
    st2.remove_tab(0)
    check('最後の1つを閉じた補充にも印が付く',
          st2.tabs[0]['bookmarks'], [1])

    # **決めているのは1か所**（48-GN）——「1行目に印を付ける」と
    # 書いてよいのは `session.fresh_tab` だけ。**app は定数を知らない**
    import io as _io2
    _sess = _io2.open('session.py', encoding='utf-8').read()
    check('`FRESH_TAB_BOOKMARKS` の代入は session.py に1つだけ',
          _sess.count('FRESH_TAB_BOOKMARKS = '), 1)
    _appsrc = _io2.open('app.py', encoding='utf-8').read()
    check('**app は定数を持ち出さない**（決め所を増やさない）',
          'FRESH_TAB_BOOKMARKS' in _appsrc, False)

    # ★★ **ファイルを開く道は `fresh_tab` を通さない**（案B・48-RA）
    # ——うにさんの指定は「新規タブ」であって、開いたファイルに
    # 前のタブの印を引き継ぐことではない（壊さない ＞ 直る）
    check('`open_file` は素の `new_tab` を渡す',
          'self.session.add_tab(new_tab())' in _appsrc, True)
    check('`open_file` は印を空にしたまま',
          _appsrc.count('self.bookmarks.clear()') >= 2, True)
    return all_ok


def run_design33_cases():
    """
    設計33（1段目）——手で消した補正を「拒否」として学ぶ
    （`設計33_消した操作を拒否として学ぶ_20260824.md`・2026-08-25）。

    tkinter が無くても回せるよう、消え方の見分け（design33_classify・
    純粋関数）と、仮の記録の確定（_design33_flush・偽の self で回す）を
    AST 経由で取り出して確かめる。配線（どこから呼ばれるか）も
    AST で見張る——**片方だけに置くと、そちらを迂回して素通りする**
    （学び22）ので、呼び元3つ（打鍵・本文の差し替え・閉じる）を数える。
    """
    import ast
    import types

    print('--- 設計33（消した補正を拒否として学ぶ・1段目） ---')
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

    # --- 消え方の見分け（純粋関数） ---
    func = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef)
                and n.name == 'design33_classify')
    ns = {}
    exec(compile(ast.Module(body=[func], type_ignores=[]), '<f>', 'exec'), ns)
    classify = ns['design33_classify']

    applied = '今日は間違いだ'
    spans = ((3, 6, 'fixed', '待ち外'),)
    check('甲: 消えた範囲＝補正の範囲で後ろが残っている（仮ではない）',
          classify(applied, spans, '今日はだ'),
          [('待ち外', '間違い', False)])
    check('行末の語を消した形は乙（仮）',
          classify('今日は間違い', spans, '今日は'),
          [('待ち外', '間違い', True)])
    check('乙: 消しながら戻った（語ごと後ろが消えた）は仮',
          classify(applied, spans, '今日'),
          [('待ち外', '間違い', True)])
    check('消しの途中（語が半分残っている）は拾わない',
          classify(applied, spans, '今日は間'), [])
    check('行がまるごと消えた形は拾わない（段落ごと消しと区別が付かない）',
          classify(applied, spans, ''), [])
    check('空白だけ残った形も拾わない', classify(applied, spans, '   '), [])
    check('文字を足しただけの編集は拾わない',
          classify(applied, spans, '今日は間違いだな'), [])
    check('補正の範囲より広く消した形は拾わない（範囲＝補正の範囲だけ）',
          classify(applied, spans, '今日だ'), [])
    check('変わっていなければ何も返さない',
          classify(applied, spans, applied), [])
    check('F2 の選び直し（chosen）は対象にしない',
          classify(applied, ((3, 6, 'chosen', '待ち外'),), '今日はだ'), [])
    check('元の語と補正後が同じ（直していない）span は対象にしない',
          classify(applied, ((3, 6, 'fixed', '間違い'),), '今日はだ'), [])
    applied2 = 'あ間違いい相違う'
    spans2 = ((1, 4, 'fixed', '待ち外'), (5, 7, 'fixed', 'そうと'))
    check('消しながら戻って2語とも消えたら、両方とも仮で拾う',
          classify(applied2, spans2, 'あ'),
          [('待ち外', '間違い', True), ('そうと', '相違', True)])
    check('前の語だけを狙って消したら、その語だけ甲',
          classify(applied2, spans2, 'あい相違う'),
          [('待ち外', '間違い', False)])

    # --- 仮の記録の確定（偽の self で回す） ---
    app_cls = next(n for n in tree.body
                   if isinstance(n, ast.ClassDef)
                   and n.name == 'CorrectNoteApp')
    methods = {n.name: n for n in app_cls.body
               if isinstance(n, ast.FunctionDef)}
    ns2 = {}
    for name in ('_design33_row_of', '_design33_drop',
                 '_design33_add', '_design33_flush'):
        exec(compile(ast.Module(body=[methods[name]], type_ignores=[]),
                     '<f>', 'exec'), ns2)

    class _FakeEditor:
        def __init__(self, lines):
            self.lines = dict(lines)     # row -> text
            self.marks = {}

        def index(self, mark):
            return f'{self.marks[mark]}.0'

        def mark_set(self, name, idx):
            self.marks[name] = int(str(idx).split('.')[0])

        def mark_gravity(self, name, g):
            pass

        def mark_unset(self, name):
            self.marks.pop(name, None)

        def get(self, a, b):
            return self.lines[int(str(a).split('.')[0])]

    class _FakeDecisions:
        def __init__(self):
            self.rejected = []
            self.saved = 0

        def is_rejected(self, o, c):
            return (o, c) in self.rejected

        def reject(self, o, c):
            if (o, c) in self.rejected:
                return False
            self.rejected.append((o, c))
            return True

        def save(self):
            self.saved += 1

    class _FakeApp:
        _design33_row_of = ns2['_design33_row_of']
        _design33_drop = ns2['_design33_drop']
        _design33_add = ns2['_design33_add']
        _design33_flush = ns2['_design33_flush']

        def __init__(self, lines):
            self.editor = _FakeEditor(lines)
            self._d33_pending = []
            self._d33_mark_seq = 0
            self.decisions = _FakeDecisions()
            self.invalidated = 0
            self._invalidate_analysis_cache = \
                lambda **kw: setattr(self, 'invalidated', self.invalidated + 1)
            self.status = types.SimpleNamespace(config=lambda **kw: None)

    s = _FakeApp({2: '今日はだ', 3: 'ほかの行'})
    s._design33_add(2, '待ち外', '間違い', False)
    check('仮の記録が置かれる', len(s._d33_pending), 1)
    s._design33_add(2, '待ち外', '間違い', True)
    check('同じ組は増えず、甲の証拠（仮ではない）が残る',
          (len(s._d33_pending), s._d33_pending[0]['provisional']),
          (1, False))
    s._design33_flush(2)
    check('カーソルがその行に居る間は確定しない',
          (len(s._d33_pending), s.decisions.rejected), (1, []))
    s._design33_flush(3)
    check('行から離れたら確定する（reject・save・控えの捨て直し）',
          (s._d33_pending, s.decisions.rejected,
           s.decisions.saved, s.invalidated),
          ([], [('待ち外', '間違い')], 1, 1))

    s2 = _FakeApp({2: 'また間違いと書いた'})
    s2._design33_add(2, '待ち外', '間違い', True)
    s2._design33_flush(None)
    check('行に補正後の形が戻っていれば、確定せずに捨てる'
          '（Ctrl+Z・打ち直して結局その形にした）',
          (s2._d33_pending, s2.decisions.rejected), ([], []))

    s3 = _FakeApp({2: '今日はだ'})
    s3.decisions.rejected.append(('待ち外', '間違い'))
    s3._design33_add(2, '待ち外', '間違い', False)
    check('既に拒否済みの組は仮の記録を作らない', s3._d33_pending, [])

    # --- 配線の見張り（学び22: 呼び元を全部数える） ---
    def calls_in(method_name, callee):
        fn = methods.get(method_name)
        if fn is None:
            return False
        return any(isinstance(n, ast.Call)
                   and isinstance(n.func, ast.Attribute)
                   and n.func.attr == callee
                   for n in ast.walk(fn))

    check('打鍵（_on_change）から見張りが呼ばれる',
          calls_in('_on_change', '_design33_watch'), True)
    check('本文の差し替え（_autofix_reset）で仮の記録を確定する',
          calls_in('_autofix_reset', '_design33_flush'), True)
    check('閉じるとき（_on_close）にも確定する',
          calls_in('_on_close', '_design33_flush'), True)
    # 「一度伝えた判断は二度と覆らない」（decisions.py）を曲げない——
    # 確定（flush）以外の場所から reject を呼ばないこと
    check('見張り（watch）と仮置き（add）は DecisionStore に書かない',
          (calls_in('_design33_watch', 'reject'),
           calls_in('_design33_add', 'reject')), (False, False))
    return all_ok


def run_scroll_cache_cases():
    """
    **画面の端でスクロールを止めない／解析中のスクロールをその場で出す／
    タブへ戻ったときに解析し直さない**（項目48-JO・うにさんの報告・
    2026-08-25）。

        「右クリックドラッグのスクロールを端で止めない。カーソルが
          画面の上下端に到達しても、そこからマウスを上下に動かしたら
          スクロールする。**カーソルが端にあったら必ずスクロールする
          わけではない**」
        「解析が終わってからタブ移動して戻ってくるとまた解析している」
        「解析中にスクロールすると、解析が終わるまで補正が反映されない。
          スクロールしてからタブ移動して戻ってくると、その範囲がすぐ
          補正反映される」

    画面の要る動きは `probes/probe_edge_scroll.py` /
    `probes/probe_scroll_paint.py` で見る。ここでは tkinter 無しでも
    回せるもの——**控えの鍵の作り方**（純粋関数）と**配線**（学び22）を
    見張る。
    """
    import ast
    import copy
    import types

    print('--- 端でのスクロール・解析中の反映・タブの控え（48-JO） ---')
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
    app_cls = next(n for n in tree.body
                   if isinstance(n, ast.ClassDef)
                   and n.name == 'CorrectNoteApp')
    methods = {n.name: n for n in app_cls.body
               if isinstance(n, ast.FunctionDef)}

    def take(name, ns):
        """メソッドを1つ取り出す（飾りは外す。3.9 では staticmethod を
        そのままでは呼べないため）。"""
        fn = copy.deepcopy(methods[name])
        fn.decorator_list = []
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<f>', 'exec'),
             ns)
        return ns[name]

    # --- 控えの鍵（末尾の空行は数に入れない） ---
    ns = {}
    key = take('_analysis_key', ns)
    check('末尾の空行を落とす', key('あ\nい\n\n\n'), 'あ\nい')
    check('落とすのは末尾だけ（間の空行は残す）',
          key('あ\n\nい\n\n'), 'あ\n\nい')
    check('画面の本文とタブの控えが同じ鍵になる',
          key('あ\nい' + '\n' * 24) == key('あ\nい'), True)
    check('空のタブは鍵にならない', key('\n\n\n'), '')
    check('None でも落ちない', key(None), '')

    # --- 覚える → 使う（末尾の空行の数が変わっても当たる） ---
    ns2 = dict(ns)
    for _n in ('_remember_tab_results', '_use_analysis_cache',
               '_blank_result'):
        take(_n, ns2)

    class _FakeSettings:
        def get(self, k, d=None):
            return 'kana'

    class _Fake:
        ANALYSIS_CACHE_TABS = 12
        _analysis_key = staticmethod(ns['_analysis_key'])
        _blank_result = ns2['_blank_result']
        _remember_tab_results = ns2['_remember_tab_results']
        _use_analysis_cache = ns2['_use_analysis_cache']

        def __init__(self):
            self._analysis_cache = {}
            self._analyze_text = ''
            self.line_results = []
            self.settings = _FakeSettings()
            self.scheduled = 0
            # **前のタブの値**（項目48-QZ）。控えから戻す道が
            # これを置き直さないと、塗りの合図が一度も出ない
            self._analyze_shown_visible = True
            self._analyze_painted_pos = 999
            self._analyze_visible_n = 999
            self._analyze_last_paint_ms = 12345.0
            self._analyze_band = ('前のタブ',)

        def _schedule_analysis_chunk(self):
            self.scheduled += 1

        def _visible_first(self, todo):
            """画面に見えている行を先に（本物は並べ替える）。"""
            self.visible_first_called = getattr(
                self, 'visible_first_called', 0) + 1
            return list(todo), min(len(todo), 30)

    def _res(lines):
        return [{'original': l, 'corrected': l, 'changed': False,
                 'details': [], 'spans': [], 'original_spans': [],
                 'unsure_spans': []} for l in lines]

    # 末尾に空行が**無い**状態で解析した（メモの下のほうに打った形）
    typed = 'あ\nい\nう'
    f = _Fake()
    f._analyze_text = typed
    f.line_results = _res(typed.split('\n'))
    f._remember_tab_results()
    check('覚えた鍵は空行を落とした形', list(f._analysis_cache), ['あ\nい\nう'])
    check('覚えたのは空行を除いた行数ぶん',
          len(f._analysis_cache['あ\nい\nう']), 3)

    # タブから読み直すと末尾に空行が 24 行足される（_pad_blank_lines）
    padded = typed + '\n' * 24
    f._analyze_text, f.line_results = '', []
    got = f._use_analysis_cache(padded, padded.split('\n'))
    check('空行を足された本文でも控えが当たる', got, True)
    check('行数は画面の本文に合わせて埋める',
          len(f.line_results), len(padded.split('\n')))
    check('埋めたのは空行だけ',
          [r['original'] for r in f.line_results[3:]] == [''] * 24, True)
    check('解析の続き（単位の組み立て）は予約されている', f.scheduled, 1)

    # ------------------------------------------------------------
    # 48-QZ **控えから戻した回も「見えているぶんから塗る」**
    # ------------------------------------------------------------
    # うにさんの報告（2026-09-05）「**タブ移動でも**（補正の色が）
    # 一度消えて再度つく」。`_load_active_tab` が本文を入れ替えると
    # タグが全部消えるのに、控えから戻す道は塗りの合図が使う3つの値を
    # **前のタブのまま持ち越して**いたので、色が戻るのは**全行の単位を
    # 組み終えたあと**だった。
    check('見えている行から先に組む（並べ替えを通る）',
          getattr(f, 'visible_first_called', 0), 1)
    check('**「見えているぶんは出した」の旗を下ろす**',
          f._analyze_shown_visible, False)
    check('**塗った位置を 0 に戻す**（前のタブの行数が残ると永久に偽）',
          f._analyze_painted_pos, 0)
    check('**見えているぶんの数を置き直す**（前のタブの数を使わない）',
          f._analyze_visible_n, len(f.line_results))
    check('前の塗りの時刻も持ち越さない', f._analyze_last_paint_ms, 0.0)
    check('画面の範囲の控えも持ち直す', f._analyze_band, None)
    check('単位の組み立てだけの印が立つ', f._analyze_units_only, True)
    check('組む行は全部（並べ替えても件数は同じ）',
          sorted(f._analyze_todo), list(range(len(padded.split('\n')))))

    # 中身が違えば当たらない
    f2 = _Fake()
    f2._analyze_text = typed
    f2.line_results = _res(typed.split('\n'))
    f2._remember_tab_results()
    other = 'あ\nい\nえ' + '\n' * 24
    check('1文字でも違えば控えは当たらない',
          f2._use_analysis_cache(other, other.split('\n')), False)
    f3 = _Fake()
    f3._analyze_text = typed
    f3.line_results = _res(typed.split('\n'))
    f3._remember_tab_results()
    tail = typed + '\nか' + '\n' * 24
    check('落とした末尾が空行でなければ当たらない',
          f3._use_analysis_cache(tail, tail.split('\n')), False)

    # --- 鍵を作るのは1か所だけ（学び22・「決めているのは最初の行」） ---
    def uses_key(name):
        fn = methods.get(name)
        if fn is None:
            return False
        return any(isinstance(n, ast.Attribute) and n.attr == '_analysis_key'
                   for n in ast.walk(fn))

    for _m in ('_remember_tab_results', '_use_analysis_cache',
               '_invalidate_analysis_cache', '_save_analysis_cache',
               '_start_background_tabs'):
        check(f'{_m} は鍵を _analysis_key で作る', uses_key(_m), True)

    # --- 画面が動いたら、並べ替えの有無に関わらず塗る ---
    view = methods['_after_view_moved']
    body = view.body
    idx_paint = idx_moved = None
    for i, node in enumerate(body):
        if idx_paint is None and any(
                isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == '_refresh_after_analysis'
                for n in ast.walk(node)):
            idx_paint = i
        if idx_moved is None and any(
                isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == '_reprioritise_visible'
                for n in ast.walk(node)):
            idx_moved = i
    check('画面が動いたら塗る道がある', idx_paint is not None, True)
    check('塗るのは並べ替えより前（並べ替えなくても出す）',
          idx_paint is not None and idx_moved is not None
          and idx_paint < idx_moved, True)

    # --- 端で戻す（自動スクロールにはしない） ---
    def calls_in(name, callee):
        fn = methods.get(name)
        if fn is None:
            return False
        return any(isinstance(n, ast.Call)
                   and isinstance(n.func, ast.Attribute)
                   and n.func.attr == callee
                   for n in ast.walk(fn))

    check('ドラッグの動きから戻しを呼ぶ',
          calls_in('_drag_motion', '_edge_warp'), True)
    # --- UE4 と同じ形（項目48-JQ）: 隠して戻す → 離したら戻して見せる ---
    check('掴んだらカーソルを隠す',
          calls_in('_drag_motion', '_scroll_cursor_hide'), True)
    check('離したらカーソルを戻して見せる',
          (calls_in('_drag_release', '_restore_pointer'),
           calls_in('_drag_release', '_scroll_cursor_restore')), (True, True))
    check('掴み直すときも後始末する（保険）',
          calls_in('_drag_press', '_scroll_cursor_restore'), True)
    check('戻せない道具では、カーソルを見せ直す',
          calls_in('_edge_warp', '_scroll_cursor_restore'), True)
    warp = methods.get('_edge_warp')
    check('端に**着く前**に戻す（速く振ったときの取りこぼしを減らす）',
          warp is not None and any(
              isinstance(n, ast.Attribute) and n.attr == 'DRAG_WARP_EDGE'
              for n in ast.walk(warp)), True)
    check('戻しは画面の端を見て決める',
          warp is not None and any(
              isinstance(n, ast.Attribute)
              and n.attr in ('winfo_pointery', 'winfo_screenheight')
              for n in ast.walk(warp)), True)
    check('端に居るだけでは進めない（時計で送らない）',
          warp is not None and not any(
              isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and n.func.attr in ('after', 'after_idle', '_on_wheel_units')
              for n in ast.walk(warp)), True)
    check('戻したぶんはスクロールにしない（warp_to を先に消費する）',
          any(isinstance(n, ast.Constant) and n.value == 'warp_to'
              for n in ast.walk(methods['_drag_motion'])), True)

    # --- 2026-08-28 うにさんの追加実装2件 -------------------------
    # ② 「右ドラッグのスクロールでマウスを素早く動かすと、カーソルが
    #    表示に戻ることがあります」——隠していたのは**掴んだ欄だけ**
    #    だった（学び22）。速く振ると戻しが間に合う前に隣の欄・窓の外へ
    #    出て、そこのカーソルが見える。全部の欄と窓に掛ける。
    check('カーソル隠しは全部の欄に掛ける（掴んだ欄だけにしない）',
          calls_in('_scroll_cursor_hide', '_scroll_panes'), True)
    _panes = methods.get('_scroll_panes')
    for _nm in ('editor', 'editor_gutter', 'result_view', 'result_gutter',
                'root'):
        check(f'隠す欄に {_nm} が入っている',
              _panes is not None and any(
                  isinstance(n, ast.Constant) and n.value == _nm
                  for n in ast.walk(_panes)), True)
    check('隠した欄は**全部**戻す（1つだけ戻して終わらない）',
          any(isinstance(n, ast.For) for n in
              ast.walk(methods['_scroll_cursor_restore'])), True)
    check('端の戻しは横も欄の中へ収める（外へ戻すとカーソルが見える）',
          any(isinstance(n, ast.Attribute) and n.attr == 'winfo_width'
              for n in ast.walk(methods['_edge_warp'])), True)

    # ① 「右クリックをダブルクリックしてそのまま押し続けている間、
    #    フォントサイズを一時的に5にします。…クリックを離すと元に戻る」
    check('俯瞰の字の大きさは 5',
          next((n.value.value for n in tree.body
                if isinstance(n, ast.Assign)
                and getattr(n.targets[0], 'id', '') == 'OVERVIEW_FONT_SIZE'),
               None), 5)
    check('右ダブルクリックで俯瞰に入る',
          calls_in('_on_right_double', '_overview_enter'), True)
    check('入る前に候補一覧を閉じる（1回目の離しで開いていることがある）',
          calls_in('_on_right_double', '_close_dropdown'), True)
    check('入るときに字を小さくする',
          calls_in('_overview_enter', '_overview_fonts'), True)
    check('入るときにカーソルを隠す（スクロールの掴みと同じ形）',
          calls_in('_overview_enter', '_scroll_cursor_hide'), True)
    check('掴みは最初から scroll の型（8画素の判定を待たない）',
          any(isinstance(n, ast.Constant) and n.value == 'scroll'
              for n in ast.walk(methods['_overview_enter'])), True)
    check('字を変えたら行の高さを捨てる（スクロール量が合わなくなる）',
          any(isinstance(n, ast.Attribute) and n.attr == '_line_h'
              for n in ast.walk(methods['_overview_fonts'])), True)
    check('行番号の字も一緒に変える（本文だけだと高さがずれる）',
          any(isinstance(n, ast.Constant) and n.value == 'editor_gutter'
              for n in ast.walk(methods['_overview_fonts'])), True)
    # **出口は1か所**（離しの道は欄ごとに別々・学び22）
    check('離しは _drag_release 1か所で俯瞰から出す',
          calls_in('_drag_release', '_overview_exit'), True)
    check('出るときに字を戻す',
          calls_in('_overview_exit', '_overview_fonts'), True)
    # 出たあとも**見ていた行のまま**（行き先を決める道具）。
    # 置き直しは字を変える側（`_overview_fonts` → `_overview_settle`）に
    # 在る——入るときも同じ副作用が出るので、片方に書くと迂回する
    check('字を変えたら、落ち着いてから行を置き直す',
          calls_in('_overview_fonts', '_overview_settle'), True)
    check('置き直しは yview で行う',
          any(isinstance(n, ast.Attribute) and n.attr == 'yview'
              for n in ast.walk(methods['_overview_settle'])), True)
    # 補正欄からの逆流の門（`_on_editor_scroll` と対・学び22）。
    # 字の入れ替えの報せは idle より後にも来るので、`_syncing` だけ
    # では足りない（probe_overview で実測）
    check('補正欄の報せは同期中・字の入れ替え中は聞かない',
          (any(isinstance(n, ast.Attribute) and n.attr == '_syncing'
               for n in ast.walk(methods['_on_result_scroll'])),
           any(isinstance(n, ast.Constant) and n.value == '_font_swap'
               for n in ast.walk(methods['_on_result_scroll']))),
          (True, True))
    check('字を入れ替える間は逆流の門を閉じる',
          any(isinstance(n, ast.Attribute) and n.attr == '_font_swap'
              for n in ast.walk(methods['_overview_fonts'])), True)

    # --- 2026-08-28・うにさんの報告2度目 ---------------------------
    # 「右クリックダブルクリックはフォントサイズ5でよいですが、
    #   **行間をもっと詰めて広い範囲が映るようにします**」
    _tight = next((n.value for n in tree.body
                   if isinstance(n, ast.Assign)
                   and getattr(n.targets[0], 'id', '') == 'OVERVIEW_TIGHT'),
                  None)
    _tight_keys = ([k.value for k in _tight.keys]
                   if isinstance(_tight, ast.Dict) else [])
    _tight_vals = ([getattr(v, 'value', None) for v in _tight.values]
                   if isinstance(_tight, ast.Dict) else [])
    check('俯瞰は行間も詰める（spacing1/2/3 と pady を落とす）',
          sorted(_tight_keys),
          ['pady', 'spacing1', 'spacing2', 'spacing3'])
    check('行と行のあいだの余白は 0 にする',
          [v for k, v in zip(_tight_keys, _tight_vals)
           if k.startswith('spacing')], [0, 0, 0])
    check('字を変えるところで行間も一緒に変える（片方だけにしない）',
          calls_in('_overview_fonts', '_overview_tighten'), True)
    check('元の余白はその場で読んで控える（同じ数を2か所に書かない）',
          any(isinstance(n, ast.Attribute) and n.attr == 'cget'
              for n in ast.walk(methods['_overview_tighten'])), True)
    check('二重に控えない（控えが元の値で上書きされない）',
          any(isinstance(n, ast.Return) for n in
              ast.walk(methods['_overview_tighten'])), True)
    check('戻すときは控えを使い切る（pop）',
          any(isinstance(n, ast.Attribute) and n.attr == 'pop'
              for n in ast.walk(methods['_overview_tighten'])), True)

    # 行の高さは**実際に描かれている高さ**を読む。ふだんの字
    # （`EDITOR_FONT`）の linespace を返していたので、俯瞰の間も
    # 19px のままでドラッグが半分しか送らなかった
    check('行の高さは dlineinfo（字も行間も込みの本当の高さ）で測る',
          any(isinstance(n, ast.Attribute) and n.attr == 'dlineinfo'
              for n in ast.walk(methods['_get_line_height'])), True)
    check('行の高さの下限は 10 ではない（俯瞰は 9px ほど）',
          any(isinstance(n, ast.Constant) and n.value == 10
              for n in ast.walk(methods['_get_line_height'])), False)

    # 「右クリックドラッグスクロールは、分割モードの入力欄なら問題ない
    #   のですが、**補正欄で実行すると端でカーソルの表示が元に戻ります**。
    #   補正欄はそもそもカーソルの形が違うので対応漏れかと」
    #
    # 補正欄だけ `<Motion>`／`<Leave>` がカーソルの形を書き換える道を
    # 持っていた。**掴んでいる間は形を変えない**を1か所に置く（学び22）
    check('カーソルの形を変える道は1か所（_set_pane_cursor）',
          '_set_pane_cursor' in methods, True)
    check('掴んでいる間は形を変えない（_scroll_cursor を見る）',
          any(isinstance(n, ast.Constant) and n.value == '_scroll_cursor'
              for n in ast.walk(methods['_set_pane_cursor'])), True)
    for _nm in ('_on_result_motion', '_on_result_leave',
                '_start_pick_mode', '_end_pick_mode'):
        check(f'{_nm} はカーソルを直に書き換えない',
              calls_in(_nm, '_set_pane_cursor'), True)
    # **できている欄の形を後から書き換える**場所は、隠す側の2つと
    # `_set_pane_cursor` だけ（作るときの `tk.Button(cursor='hand2')`
    # は数えない——形が変わらないので迂回にならない）
    def _reconfigs_cursor(fn):
        for c in ast.walk(fn):
            if (isinstance(c, ast.Call)
                    and isinstance(c.func, ast.Attribute)
                    and c.func.attr in ('config', 'configure')
                    and any(k.arg == 'cursor' for k in c.keywords)):
                return True
        return False

    check('カーソルを後から書き換えるのは、隠す側と _set_pane_cursor だけ',
          sorted(nm for nm, fn in methods.items() if _reconfigs_cursor(fn)),
          ['_scroll_cursor_hide', '_scroll_cursor_restore',
           '_set_pane_cursor'])

    # --- 2026-08-27（うにさんの報告6件）の見張り ---
    def refs(name, attr):
        fn = methods.get(name)
        if fn is None:
            return False
        return any(isinstance(n, ast.Attribute) and n.attr == attr
                   for n in ast.walk(fn))

    def has_const(name, value):
        fn = methods.get(name)
        if fn is None:
            return False
        return any(isinstance(n, ast.Constant) and n.value == value
                   for n in ast.walk(fn))

    # ① 端の戻しの競合——戻す前に並んでいた古い報せは**捨てて待つ**
    #    （時計ではなく回数。解析の区切りが挟まると間合いが数百msに
    #    伸びるので、時計の猶予は破綻する——probe_edge_scroll で実測）
    check('古い報せは捨てて待つ（warp_skip・回数の門）',
          has_const('_drag_motion', 'warp_skip')
          and refs('_drag_motion', 'DRAG_WARP_SKIP_MAX'), True)
    # ② 離したら「戻り先に着いてから」見せる（先に見せると
    #    移動先で一瞬見えてから飛ぶのが見える）
    check('離しの見せ直しは戻り先に着いてから',
          calls_in('_restore_pointer', '_show_cursor_when_settled'), True)
    check('着かないままでも最後は見せる',
          calls_in('_show_cursor_when_settled', '_scroll_cursor_restore'),
          True)
    # ③ 解析の先端のすぐ先を見ているときも、片付いた行から塗る
    #    （旗が立ったあとの区切りでも、見えている範囲なら出す）
    check('区切りの塗りは見えている範囲を確かめて出す',
          calls_in('_analyze_chunk', '_visible_band'), True)
    # ④ 学習が控えを捨てても、裏のタブの歩みを立て直す
    check('控えを捨てたら裏の歩みも立て直す',
          refs('_invalidate_analysis_cache', '_start_background_tabs'), True)
    check('裏の歩みは表の解析が済むまで始めない（取り合いの門）',
          refs('_start_background_tabs', '_analyze_pos')
          or has_const('_start_background_tabs', '_analyze_pos'), True)
    # ⑤ F2: 左右キーは捨てない・一覧が閉じていても渡り歩ける
    #    （2026-08-27 の2度目の報告で「印を使い切る」形から変えた）
    check('左右キーの離しでは F2 の記憶を捨てない',
          (has_const('_on_change', 'Left'),
           has_const('_on_change', 'Right')), (True, True))
    check('一覧が閉じていても左右キーで渡り歩く',
          calls_in('_on_f2_range_move', '_f2_move'), True)
    # ⑤b 左右キーの行き先に薄い色（f2_next）
    check('選んだとき・伸び縮みしたときに行き先を塗り直す',
          (calls_in('_show_unit_candidates', '_paint_f2_neighbors'),
           calls_in('_on_f2_range_resize', '_paint_f2_neighbors')),
          (True, True))
    check('行き先の先読みは渡り歩きと同じ規則（_f2_next_stop）',
          calls_in('_f2_peek', '_f2_next_stop'), True)
    check('記憶を捨てるとき薄い色も消す',
          has_const('_clear_f2_target', 'f2_next'), True)
    # ⑥ F2: 調整した範囲の終わりの次の文字から次の範囲へ
    check('右キーは調整済みの範囲から作る',
          calls_in('_f2_move', '_f2_resized_next'), True)
    check('範囲は make_range_unit で作る（ドラッグ選択と同じ道）',
          '_f2_resized_next' in methods
          and any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                  and n.func.id == 'make_range_unit'
                  for n in ast.walk(methods['_f2_resized_next'])), True)
    # ⑦ 最大化はタスクバーを隠さない（▢ と OS の両方の道・学び22）
    check('▢ の最大化で作業領域へ収める',
          calls_in('_toggle_maximized', '_clamp_zoom_to_workarea'), True)
    check('OS からの最大化も <Configure> で収める',
          calls_in('_on_resize', '_clamp_zoom_to_workarea'), True)

    # --- 2026-08-27 の2度目の報告の見張り ---
    # ①' 戻しは**その場で**動かす（Tk の warp は idle まで遅れるので、
    #     実機のドラッグ中は間に合わない——だからプローブは通るのに
    #     実機で再発した）
    check('戻しは _warp_pointer（端でも離しでも・学び22）',
          (calls_in('_edge_warp', '_warp_pointer'),
           calls_in('_restore_pointer', '_warp_pointer')), (True, True))
    check('Windows では SetCursorPos（同期）で動かす',
          refs('_warp_pointer', 'SetCursorPos'), True)
    # ③' 裏の歩みは、触っていない間まとめて進める
    check('裏の歩みは一歩の形（_bg_step_once）を回す',
          calls_in('_bg_step', '_bg_step_once'), True)
    check('触っていない間の判定（ANALYZE_BG_IDLE_MS）を見る',
          refs('_bg_step', 'ANALYZE_BG_IDLE_MS'), True)
    # ⑦' 最大化は枠の太さを実測して、中身を作業領域にぴったり収める
    check('収め直しは枠の太さを実測する（GetClientRect）',
          refs('_clamp_zoom_to_workarea', 'GetClientRect'), True)

    # --- 2026-08-30 の報告（項目48-MA）---
    # 「上の端へのドラッグで最大化 → タスクバーから最小化 → もう一度
    #   押すと、**タスクバーが隠れる**」。最小化の間は `<Configure>` が
    #   届かないので「最大化していない→している」の変わり目が来ず、
    #   1回きりの門を通れなかった。**変わり目を数えるのをやめ**、
    #   収まっていればすぐ帰る形にした（何度呼んでもよい）。
    check('変わり目の控え（_was_zoomed）はもう使わない（48-MA）',
          '_was_zoomed' in src, False)
    check('収まっていればすぐ帰る（何度呼んでも安い）',
          refs('_clamp_zoom_to_workarea', 'state')
          and 'return      # もう収まっている' in src, True)
    check('最小化から戻ったときも掛ける（<Map>・学び22）',
          "'<Map>'" in src
          and '_clamp_zoom_to_workarea' in src.split("'<Map>'")[1][:120],
          True)

    # --- 2026-08-30 の報告（項目48-MB）---
    # 「解析中、タブキーの空白が伸びたり縮んだりしています」。
    # `_paint_whitespace` が**先に印を剥がしてから**組み直しており、
    # 組む途中の `display lineend`（`_wrap_edge_columns`）が Tk に
    # 画面を作り直させるので、**剥がれた姿が描かれていた**。
    # 直しは「**先に組む → 前と同じなら触らない**」。
    _ws = ast.get_source_segment(src, methods['_paint_whitespace']) or ''
    _strip = _ws.find('tag_remove')
    _build = _ws.find('_wrap_edge_columns')
    check('印を剥がすのは、組み終わったあと（48-MB）',
          _strip > _build > 0, True)
    check('前と同じなら塗り直さない（見比べを持つ）',
          '_ws_paint_sig' in _ws, True)
    _st = ast.get_source_segment(src, methods['_paint_line_tab_stops']) or ''
    check('タブの止まりも、前と同じなら敷き直さない',
          '_ws_stop_sig' in _st, True)

    # --- 2026-08-31 の報告（項目48-MO）---
    # 「右のタブスペースが短いままでした。解析は済んでいます。
    #   ただこのあと最小化や戻したり、何かしたら正しいタブスペース幅に
    #   直りました」
    # 48-MB の「前と同じなら触らない」は**印が残っていること**を
    # 前提にしていた。**補正欄は解析のたびに中身を作り直す**
    # （`delete('1.0','end')` → `insert`）ので、そこで印が全部消える。
    # 作り直した中身が前と同じ字なら、次の塗りは「前と同じ」と言って
    # **何も敷かない**。窓を動かすと lo/hi が変わって控えが外れるので
    # 「最小化して戻したら直った」。
    check('「前と同じ」と言う前に、印が在るかを確かめる道具がある',
          '_tags_still_there' in methods, True)
    check('タブの止まり: 控えだけで帰らない（48-MO）',
          '_tags_still_there' in _st, True)
    check('空白の印: 同じ確かめを掛けている（片方だけにしない・学び22）',
          '_tags_still_there' in _ws, True)
    # 確かめは**控えが合っているときだけ**（毎回引くと重い）
    check('確かめるのは、控えが合っているときだけ',
          _st.index('_ws_stop_sig') < _st.index('_tags_still_there'), True)

    # --- 2026-08-27 の3度目の報告の見張り（項目48-KD）---
    # ①'' 動かされた量は**実カーソル位置**で数える（報せの座標は
    #     戻しの前の古いものかもしれない。速いドラッグでは戻り先
    #     ±60px の照合が実際の動きだけで破れる）
    check('動かされた量は実位置で数える（winfo_pointery）',
          refs('_drag_motion', 'winfo_pointery'), True)
    check('同期の戻し（SetCursorPos）は握手を置かない',
          has_const('_edge_warp', 'sync'), True)
    # ⑤c 行き先の先読みは、実際の一覧と**同じ組み立て**で
    #     「開くか」を数える（候補の出ない語はその奥へ）
    check('先読みも一覧も同じ組み立て（_editor_dropdown_items）',
          (calls_in('_f2_peek', '_editor_dropdown_items'),
           calls_in('_open_editor_dropdown', '_editor_dropdown_items')),
          (True, True))

    return all_ok


def run_icon_cases():
    """
    **アプリのアイコンの配線**（項目48-JR・うにさんの指定
    「ノートまたは書く媒体に対して補正されて入っていくイメージ」）。

    アイコンは**4か所に置かないと片方だけ効く**（学び22）:

        クラスの絵       `app.py` の `_apply_window_icon`
                         （Tk の `iconphoto` / `iconbitmap`）
        **窓そのもの**   `_set_window_icons_win32`（`WM_SETICON`。
                         **Alt+Tab はここを見る**・項目48-LY）
        exe そのもの     `correctnote.spec` / `kana_memo.spec` の `icon=`
        exe への同梱     `bundle_manifest.py` の名簿

    絵そのものが見えるかは `probes/probe_icon.py`（xvfb で
    `_NET_WM_ICON` を読む）と `tools_local/probe_icon_win.py`
    （Windows の実機で `WM_GETICON` を聞く）。ここでは**配線**だけを
    見張る。
    """
    import ast
    import os

    print('--- アプリのアイコンの配線（項目48-JR） ---')
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
    top = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) \
                and isinstance(node.value, ast.Constant):
            top[node.targets[0].id] = node.value.value
    check('絵の名前を app.py が持っている',
          (top.get('ICON_ICO'), top.get('ICON_PNG')),
          ('correctnote.ico', 'correctnote.png'))

    app_cls = next(n for n in tree.body
                   if isinstance(n, ast.ClassDef) and n.name == 'CorrectNoteApp')
    methods = {n.name: n for n in app_cls.body
               if isinstance(n, ast.FunctionDef)}
    fn = methods.get('_apply_window_icon')
    check('窓にアイコンを付ける道がある', fn is not None, True)

    def calls(node, name):
        return node is not None and any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == name for n in ast.walk(node))

    def uses(node, name):
        return node is not None and any(
            (isinstance(n, ast.Name) and n.id == name)
            or (isinstance(n, ast.Attribute) and n.attr == name)
            for n in ast.walk(node))

    check('PNG と .ico の両方を試す（片方だけだと羽根に戻る場所が残る）',
          (calls(fn, 'iconphoto'), calls(fn, 'iconbitmap')), (True, True))
    check('同梱物として読む（app_dir ではなく bundled_path）',
          (uses(fn, 'bundled_path'), uses(fn, 'app_dir')), (True, False))
    check('PhotoImage を握る（捨てると絵が消える）',
          uses(fn, '_icon_image'), True)
    check('起動時に呼ばれる',
          calls(methods.get('__init__'), '_apply_window_icon'), True)

    # --- 窓そのものの絵（Alt+Tab が見るほう・項目48-LY） ---
    # うにさんの報告（2026-08-30）「Alt+Tab でウインドウ選択時に、
    # アプリアイコンが出てこない」。Tk の iconphoto / iconbitmap は
    # Windows では**クラスの絵**しか置かず、窓に聞く WM_GETICON は
    # 0 のままだった（tools_local/probe_icon_win.py で実測）。
    win_fn = methods.get('_set_window_icons_win32')
    check('窓そのものに絵を付ける道がある（48-LY）', win_fn is not None, True)
    hwnd_fn = methods.get('_window_hwnd_win32')
    hwnd_src = ast.get_source_segment(src, hwnd_fn) if hwnd_fn else ''
    check('HWNDを64bitのまま最上位窓まで辿る',
          ('GetAncestor' in (hwnd_src or ''),
           'c_void_p' in (hwnd_src or '')), (True, True))
    win_src = ast.get_source_segment(src, win_fn) if win_fn else ''
    check('WM_SETICON を送る', 'WM_SETICON' in (win_src or ''), True)
    check('.ico から寸法を指定して読む（256 を縮めた眠い絵にしない）',
          ('LoadImageW' in (win_src or ''),
           'SM_CXICON' in (win_src or '')), (True, True))
    check('大小の両方を置く',
          ('ICON_BIG' in (win_src or ''),
           'ICON_SMALL' in (win_src or '')), (True, True))
    check('アイコンの控えを握る（捨てると Windows が絵を失う）',
          uses(win_fn, '_win_icon_big'), True)
    check('_apply_window_icon から呼ばれる',
          calls(fn, '_set_window_icons_win32'), True)
    # **簡易入力の窓にも掛ける**（学び22——片方だけに置くと迂回する）
    check('簡易入力の窓にも掛ける',
          calls(methods.get('_open_quick_capture'),
                '_set_window_icons_win32'), True)

    # --- 絵の中身（項目48-LY・矢を落とした） ---
    # うにさんの指定（2026-08-30）「アプリアイコンの右側にある矢印を
    # 消して、その分ノートを大きくする」。**描く道具はただ1つ**なので、
    # そこに矢が戻っていないかだけ見る。
    # **道具は公開リポジトリに入らない**（`tools_local/` は .gitignore）。
    # 無い場所（CI・配布した一式）では**この1件だけ飛ばす**——
    # 有るのに失敗するのと、無いから測れないのは別（学び56。
    # まっさらなフォルダで回して気付いた・2026-08-30）。
    _icon_tool = os.path.join('tools_local', 'make_icon.py')
    if os.path.exists(_icon_tool):
        icon_src = open(_icon_tool, encoding='utf-8').read()
        check('絵を描く道具に矢は残っていない（48-LY）',
              'def arrow(' in icon_src, False)
    else:
        print('-- 絵を描く道具は無い（tools_local/）。この1件は飛ばす')

    # `.ico` に小さい寸法まで入っている（タスクバーは 16px を使う）。
    # Pillow を使わずにヘッダだけ読む（アプリ側は Pillow に依存しない）。
    with open('correctnote.ico', 'rb') as f:
        head = f.read(6)
        n = int.from_bytes(head[4:6], 'little')
        sizes = set()
        for _ in range(n):
            e = f.read(16)
            sizes.add((e[0] or 256, e[1] or 256))
    check('.ico に 16〜256px が入っている',
          {(16, 16), (24, 24), (32, 32), (48, 48),
           (64, 64), (128, 128), (256, 256)} <= sizes, True)

    main_fn = next((n for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == 'main'),
                   None)
    check('タスクバーの名札を、窓を作る前に名乗る',
          main_fn is not None and any(
              isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
              and n.func.id == '_set_app_user_model_id'
              for n in ast.walk(main_fn)), True)
    appid_fn = next((n for n in tree.body
                     if isinstance(n, ast.FunctionDef)
                     and n.name == '_set_app_user_model_id'), None)
    appid_src = ast.get_source_segment(src, appid_fn) if appid_fn else ''
    check('exeでも同じタスクバーの名札を明示する',
          "getattr(sys, 'frozen'" in (appid_src or ''), False)

    # --- 同梱の名簿（bundle_manifest.py ただ1つ） ---
    import bundle_manifest
    names = set(bundle_manifest.NAMES)
    check('名簿に .ico と .png が載っている',
          {'correctnote.ico', 'correctnote.png'} <= names, True)

    # --- exe そのものの絵（spec は2つとも） ---
    for spec_name in ('correctnote.spec', 'kana_memo.spec'):
        if not os.path.exists(spec_name):
            check(f'{spec_name} が在る', False, True)
            continue
        text = open(spec_name, encoding='utf-8').read()
        check(f'{spec_name} が exe に絵を付ける',
              "icon='correctnote.ico'" in text, True)
    return all_ok

def run_explain_cases():
    """
    **候補一覧の「－ 品詞判定 －」「－ 補正根拠 －」**（項目48-MD・
    うにさんの指定・2026-08-31）。

        「メニューに『補正候補に品詞の判定を表示する』を追加し、
          デフォルトオフ。（…）このメニューがオンになると、
          まったく候補がない単語に対しても補正候補を出し、その場合は
          『－ 品詞判定 －』の項目だけが見える。
          Shift + 左右で範囲を変えた場合は『判定できません』と表示する」

    ここで見張るのは **4つ**:

      ① `explain.py` の言葉（janome の無いここでは、渡した
         `tokenize_fn` の品詞だけで組み立てる道を通る）
      ② **画面との配線**——候補一覧は3つある（補正欄・メモ欄・
         簡易入力）ので、**3つとも**説明を足しているか。
         足す場所が「候補が無ければ開かない」門より**前**か
         （学び22「片方だけに置くと、そちらを迂回する」）
      ③ 既定が**両方オフ**か（うにさんの指定）
      ④ 紫の理由が**解析の控えを通り抜ける**か
    """
    import ast
    import explain

    print('--- 候補一覧の品詞判定と補正根拠（項目48-MD） ---')
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    # --- ① 言葉 ------------------------------------------------
    # 品詞は「大分類:細分類」でも「大分類」だけでも読めること。
    check('イ形容詞と呼ぶ（janome は「形容詞」）',
          explain.pos_name('形容詞:自立', '早い', '基本形', '早い'),
          'イ形容詞・終止形')
    check('ナ形容詞の語幹と呼ぶ（janome は「名詞,形容動詞語幹」）',
          explain.pos_name('名詞:形容動詞語幹', 'きれい'), 'ナ形容詞の語幹')
    check('活用している形は、その形で書く',
          explain.pos_name('動詞:自立', '走っ', '連用タ接続', '走る'),
          '動詞・連用形（た接続）／原形 走る')
    check('形の変わらない品詞は、そのまま',
          (explain.pos_name('名詞'), explain.pos_name('連体詞'),
           explain.pos_name('接続詞'), explain.pos_name('感動詞')),
          ('名詞', '連体詞', '接続詞', '感動詞'))
    check('姓と名を分けて出す（項目48-JL の細分類）',
          explain.pos_name('名詞:固有名詞:人名:姓', '柚須'),
          '固有名詞（人名・姓）')
    check('辞書に読みが無いことは必ず添える',
          explain.pos_name('名詞:一般', 'たんほ', has_reading=False),
          '名詞（辞書に無い語）')
    # --- 項目48-PW（品詞判定の変な言い方を直す・2026-09-04） ---
    # うにさんの指定「品詞の判定を見れば見るほど変なので、品詞判定を
    # よく見て、細かく見て修正をしていってください」。
    check('小書きで始まる読みの無い語は「断片」と言う（ょじえかくらん）',
          explain.pos_name('名詞:一般', 'ょじえかくらん', has_reading=False),
          '断片（小書き `ょ` で始まる——語の頭に立たない）')
    check('独立した ー は固有名詞ではなく長音（かー の判定も変、の直し）',
          explain.pos_name('名詞:固有名詞:一般', 'ー', has_reading=False),
          '長音（前の字と合わせて1拍）')
    check('1字の助詞は行の文脈の品詞で言う（が を単独で解析し直さない）',
          explain.pos_lines('が', None, pos_hint='助詞:格助詞:一般'),
          ['助詞（格助詞）'])
    check('活用形のヒントも効く（た ＝ 助動詞・終止形）',
          explain.pos_lines('た', None, pos_hint='助動詞',
                            infl_hint='基本形'),
          ['助動詞・終止形'])

    def tok_vn(line):
        """動詞終止形＋名詞の直付き（たぶ|い）を返す作り物の割り方。"""
        return [('たぶ', '動詞:自立', 'タブ', 0, 2, True, '基本形'),
                ('い', '名詞:一般', 'イ', 2, 3, True, '')]
    # ★★ **かなだけの範囲では、割り方ごと当て推量**（項目48-RL・
    # 2026-09-05・うにさんの報告「`たぶいごうして`——動詞終止形から
    # 名詞と繋がる**誤判定**。この文法は変ですよね」）。
    # 48-QE（1拍の内側で切れた割り方）と同じ性質なので、同じ扱いに。
    check('かなだけなら「成り立たない割り方」と言う（鎖を見せない）',
          explain.pos_lines('たぶい', tok_vn),
          ['判定できません（「たぶ」を動詞と読むと、終止形に'
           '名詞「い」が直付きになる——成り立たない割り方）'])
    check('隣がかなで続いていれば、そう添える（48-RG と同じ口）',
          explain.pos_lines('たぶい', tok_vn, next_text='ごうして')[0]
          .endswith('後ろの「ごうして」とひとつづきのかな連続）'), True)
    check('**48-RH が効く**（頭が `判定できません` なので候補の行が付く）',
          explain.pos_lines('たぶい', tok_vn)[0].startswith(
              explain.UNKNOWN_POS), True)

    def tok_vn_kanji(line):
        """漢字を含む形（解す|咳）——**今までどおり鎖＋※**。"""
        return [('解す', '動詞:自立', 'カイス', 0, 2, True, '基本形'),
                ('咳', '名詞:一般', 'セキ', 2, 3, True, '')]
    # ★★ **漢字を含む範囲は巻き戻さない**——うにさん自身が
    # その言い方（`解す咳`）で報告した形（48-PL）
    check('漢字を含むなら、今までどおり鎖＋※',
          explain.pos_lines('解す咳', tok_vn_kanji)[-1],
          '※ 品詞のつながりが異様（動詞の終止形に名詞が直付き）')
    check('漢字を含むなら鎖も見せる',
          explain.pos_lines('解す咳', tok_vn_kanji)[0],
          '解す ＝ 動詞・終止形')
    check('品詞が立たなければ、そう言う',
          explain.pos_name(''), '判定できません')

    def tok(line):
        """janome の無い環境でも回せる、作り物の割り方。"""
        table = {'貸す': '動詞:自立', '九': '名詞:数', '人': '名詞:接尾'}
        out = []
        for w, p in table.items():
            i = line.find(w)
            if i >= 0:
                out.append((w, p, '', i, i + len(w), True))
        out.sort(key=lambda t: t[3])
        return out or [(line, '名詞:一般', '', 0, len(line), True)]

    check('割れた語は1語ずつ1行（丸めない）',
          explain.pos_lines('貸す九人', tok),
          ['貸す ＝ 動詞', '九 ＝ 数詞', '人 ＝ 接尾辞'])

    # --- 打鍵の型（うにさんの挙げた言葉のとおりに） --------------
    check('隣接キーへ補正',
          explain.hand_labels('おくゆくこてい', 'おくゆきこてい', 'kana'),
          ['隣接キーへ補正'])
    check('隣接キーの巻き込みを補正',
          explain.hand_labels('もみとにもどります', 'もとにもどります',
                              'kana'),
          ['隣接キーの巻き込みを補正'])
    check('文字の順序を補正（入れ替えは1手・Damerau）',
          explain.hand_labels('そももそ', 'そもそも', 'kana'),
          ['文字の順序を補正'])
    check('脱字を補正',
          explain.hand_labels('しゅうりょじ', 'しゅうりょうじ', 'kana'),
          ['脱字を補正'])
    check('重複した打鍵を補正',
          explain.hand_labels('てんんか', 'てんか', 'kana'),
          ['重複した打鍵を補正'])
    check('Shift の押し忘れ（小書き）を補正',
          explain.hand_labels('にゆうりよくみす', 'にゅうりょくみす', 'kana'),
          ['Shift の押し忘れ（小書き）を補正'])
    check('濁点・半濁点を補正',
          explain.hand_labels('つつぎ', 'つづき', 'kana'),
          ['濁点・半濁点を補正'])
    check('手が多すぎるときは数だけ言う',
          explain.hand_labels('あいうえおかきくけこ', 'なにぬねのはひふへほ',
                              'kana'),
          ['読みを組み直して補正（10か所）'])
    check('同じものなら手は無い', explain.hand_labels('あい', 'あい'), [])

    # --- エンジンが控えた理由が在れば、それを使う（測り直さない）---
    check('控えた理由をそのまま出す',
          explain.odd_reason('好き任', line='好き任', start=0, end=3,
                             recorded=[(0, 3, 'これが理由')]),
          'これが理由')
    check('狭いほうの理由を採る（広い印は隣を巻き込む）',
          explain.odd_reason('任', line='好き任', start=2, end=3,
                             recorded=[(0, 3, 'ひろい'), (2, 3, 'せまい')]),
          'せまい')
    check('重ならない控えは使わない',
          explain.odd_reason('好き', line='好き任', start=0, end=2,
                             recorded=[(2, 3, 'よその理由')]),
          explain.NO_ODD_REASON)

    # 3行の並び（学習が効いていなければ2行）
    rows = explain.reason_lines('好き任', '確認', line='好き任', start=0,
                                end=3, recorded=[(0, 3, 'これが理由')])
    check('根拠は 理由 → した内容 の順', rows[0], 'これが理由')
    check('学習が効いていなければ3行目は出さない', len(rows), 2)
    check('直したのに判定が立っていなければ、はっきり書く',
          explain.reason_lines('あいう', 'あいえ')[0],
          '異様だという判定は立っていない（補正は別の道から届いた）')
    check('補正が無ければ「印だけ」',
          explain.reason_lines('あいう', '')[1], '補正はしていない（印だけ）')

    class _Choices:
        def lookup(self, base, prev, next_):
            return '確認' if base == '好き任' else None

    rows = explain.reason_lines('好き任', '確認', choices=_Choices())
    check('選び直しで直ったものには「学習による選び直し」',
          rows[-1], '学習による選び直し')

    # --- ②' `_analysis_items` を、作り物のアプリで直に回す --------
    #   tkinter は要らない（設定・語彙・単位だけを渡す）。
    import app as _app

    class _Settings(dict):
        def get(self, k, d=None):
            return dict.get(self, k, d)

    class _Store(object):
        _tokenize_fn = staticmethod(lambda line: [])

        def reading_of(self, _s):
            return None

        def lookup(self, _r):
            return []

    def _fake_items(corrected):
        me = _app.CorrectNoteApp.__new__(_app.CorrectNoteApp)
        me.settings = _Settings({'show_pos_info': True,
                                 'show_reason_info': True,
                                 'input_method': 'kana'})
        me.store = _Store()
        me.dict_index = None
        me.choices = None
        me.line_results = []
        unit = {'text': '確認', 'base': '確認', 'kind': 'plain',
                'detail': (('かくにん', '確認', 'かな入力')
                           if corrected else None),
                'prev': '', 'next': ''}
        return _app.CorrectNoteApp._analysis_items(me, 1, unit)

    # --- ② 画面との配線 ----------------------------------------
    src = open('app.py', encoding='utf-8').read()
    tree = ast.parse(src)
    app_cls = next((n for n in tree.body
                    if isinstance(n, ast.ClassDef)
                    and n.name == 'CorrectNoteApp'), None)
    funcs = {n.name: n for n in (app_cls.body if app_cls else [])
             if isinstance(n, ast.FunctionDef)}

    check('説明を組み立てるのは1か所（_analysis_items）',
          '_analysis_items' in funcs, True)

    def calls_analysis(name):
        fn = funcs.get(name)
        if fn is None:
            return None
        return any(isinstance(n, ast.Call)
                   and isinstance(n.func, ast.Attribute)
                   and n.func.attr == '_analysis_items'
                   for n in ast.walk(fn))

    for name in ('_open_dropdown', '_editor_dropdown_items',
                 '_open_quick_dropdown'):
        check(f'{name} が説明を足す（3つとも・学び22）',
              calls_analysis(name), True)

    def before_gate(name):
        """説明を足すのが「候補が無ければ開かない」門より前か。"""
        fn = funcs.get(name)
        if fn is None:
            return None
        add = gate = None
        for n in ast.walk(fn):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                    and n.func.attr == '_analysis_items':
                add = n.lineno if add is None else min(add, n.lineno)
            if isinstance(n, ast.Compare) and isinstance(n.left, ast.Call) \
                    and isinstance(n.left.func, ast.Name) \
                    and n.left.func.id == 'len':
                gate = n.lineno if gate is None else min(gate, n.lineno)
        if add is None or gate is None:
            return None
        return add < gate

    for name in ('_open_dropdown', '_open_quick_dropdown'):
        check(f'{name}: 候補ゼロでも開くよう、門より前に足す',
              before_gate(name), True)

    check('Shift+左右で作り替えた範囲に印を付ける（2か所とも）',
          src.count("unit['resized'] = True"), 2)

    # --- 項目48-ML: **いちばん下の説明が、見える行の外へ出ない** ---
    # うにさんの画面「品詞判定が出ないものがあります」。一覧は
    # 16行で切られていて、候補の多い語（`やん` は21項目）では説明が
    # 外へ出ていた。**しかも上下キーは見出しを飛ばすので届かない。**
    ns = {}
    for name in ('DROPDOWN_ROWS', 'DROPDOWN_ROWS_MAX'):
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1                     and getattr(node.targets[0], 'id', None) == name:
                ns[name] = node.value.value
    check('見せる行数を1か所で決めている',
          sorted(ns), ['DROPDOWN_ROWS', 'DROPDOWN_ROWS_MAX'])
    check('これまでの16行は変えていない', ns.get('DROPDOWN_ROWS'), 16)

    def _rows(n_items, head_at=None):
        """`_make_dropdown` の高さの決め方（同じ式をここで回す）。"""
        rows = min(n_items, ns['DROPDOWN_ROWS'])
        if head_at is not None:
            rows = min(n_items,
                       max(rows, ns['DROPDOWN_ROWS'] + (n_items - head_at)),
                       ns['DROPDOWN_ROWS_MAX'])
        return rows

    check('説明が無ければ、今までどおり16行で切る', _rows(30), 16)
    check('説明が無ければ、少ない項目はそのまま', _rows(6), 6)
    # うにさんの画面の `やん`（21項目・説明は17行目＝添字16から）
    check('やん（21項目）は全部見える', _rows(21, 16), 21)
    check('繋がり（19項目）も全部見える', _rows(19, 14), 19)
    check('項目が多すぎるときは、説明ぶんだけ伸ばして止める',
          _rows(60, 54), ns['DROPDOWN_ROWS'] + 6)
    check('説明が長くても、伸ばしすぎない（上限で止まる）',
          _rows(60, 40), ns['DROPDOWN_ROWS_MAX'])
    check('高さの式が `_make_dropdown` に在る',
          'rows = min(len(items), DROPDOWN_ROWS)' in src, True)

    # --- 項目48-MM: **補正根拠は、補正した単語にだけ** ---
    #   うにさんの指定（2026-08-31）「補正根拠の項目は、補正した単語に
    #   だけ表示して、そうでないものは**項目ごと省きます**」
    check('直していない語には見出しごと出さない',
          '補正根拠は、補正した単語にだけ' in src, True)
    check('その門は「－ 補正根拠 －」を足すより前に在る',
          src.index("if unit.get('resized') or not fixed or fixed == typed:")
          < src.index('items.append((ANALYSIS_HEAD_WHY, None))'), True)
    # 直していない語の `_analysis_items` は、**品詞判定だけ**を返す
    # （`explain.reason_lines` は道具のために言葉を持ったままでよい）
    check('直していない語の説明は品詞判定だけ',
          [t for t, _cb in _fake_items(corrected=False)
           if t.startswith('－')], ['－ 品詞判定 －'])
    check('直した語には根拠も付く',
          [t for t, _cb in _fake_items(corrected=True)
           if t.startswith('－')], ['－ 品詞判定 －', '－ 補正根拠 －'])

    # --- F2 の行き先の色（**もっと薄く**・うにさんの指定・2026-08-31）---
    def _lum(h):
        h = h.lstrip('#')
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    import re as _re
    fn_next = funcs.get('_paint_f2_neighbors')
    body = ast.get_source_segment(src, fn_next) if fn_next else ''
    got = _re.findall(r"'(#[0-9a-f]{6})'", body or '')
    check('行き先の色を1か所で決めている（ダークとライトの2つ）',
          len(got), 2)
    if len(got) == 2:
        dark, light = got
        # 選んでいる範囲（`f2_focus` ＝ #7a5a2b / #ffd9a0）より
        # **うんと薄い**こと。地色はダーク #25292d・ライト #ffffff。
        check('ダーク: 行き先は選択の1/3より薄い',
              _lum(dark) - _lum('#25292d')
              < (_lum('#7a5a2b') - _lum('#25292d')) / 3, True)
        check('ライト: 行き先は選択の1/3より薄い',
              _lum('#ffffff') - _lum(light)
              < (_lum('#ffffff') - _lum('#ffd9a0')) / 3, True)
        check('それでも地色と同じではない（見えなくならない）',
              dark != '#25292d' and light != '#ffffff', True)

    check('見出しの文字列は1か所で決めている',
          src.count("ANALYSIS_HEAD_POS = ") == 1
          and src.count("'－ 品詞判定 －'") == 1, True)
    check('印が付いた範囲は「判定できません」',
          "items.append(('  判定できません', None))" in src, True)

    for label in ('補正候補に品詞の判定を表示する', '補正候補に根拠を表示する'):
        check(f'表示メニューに「{label}」がある',
              f"label='{label}'" in src, True)

    # --- ③ 既定は両方オフ ---------------------------------------
    import tempfile
    import os as _os
    from settings import Settings
    s = Settings(_os.path.join(tempfile.mkdtemp(), 'settings.json'))
    check('品詞判定の既定はオフ', s.get('show_pos_info'), False)
    check('補正根拠の既定はオフ', s.get('show_reason_info'), False)

    # --- ④ 理由は控えを通り抜ける -------------------------------
    import analysis_cache as AC
    packed = AC._pack({'original': 'あ', 'corrected': 'あ',
                       'odd_reasons': [(0, 1, 'わけ')]})
    check('紫の理由が解析の控えを通り抜ける',
          AC._unpack(packed).get('odd_reasons'), [(0, 1, 'わけ')])
    check('理由の無い古い控えでも落ちない',
          AC._unpack({'o': 'あ', 'c': 'あ'}).get('odd_reasons'), [])
    return all_ok


def test_menu_and_keys_48oc_48od_48oe():
    """
    **v1.4.0 のあとの3件**（うにさんの指定・2026-09-02）。

    ### 48-OC 品詞をオフ・根拠をオンにすると、根拠が出なかった

        「**メニューで品詞をオフ、根拠をオンにした場合、根拠が
          出ません**」

    `_analysis_items` が「品詞がオフなら **[]**」で早く帰っていた。
    根拠は品詞の下に並べる形だが、**上が無ければ根拠から始めれば
    よい**だけで、上に依存する理由は無い。あわせて「根拠を上げたら
    品詞も一緒に上げる」もやめた——**押したメニューと違うものが
    効くのは分かりにくい**。

    ### 48-OD Shift+スペース／Ctrl+スペース

        「Shift+スペースで、行内を選択できるようにします」
        「Ctrl+スペースで、選択行のブックマークをオンオフします」

    行内の選択は**改行を含めない**（行番号のクリックで選ぶ形は
    次の行の頭までを選ぶので、コピーに改行が付いてくる）。
    ブックマークは複数行にまたがるとき**全部に付いていれば全部外し、
    そうでなければ全部に付ける**（揃うほうへ動かす）。

    ### 48-OE 説明書の名前から版を外す

        「更新のたびに説明書が増えるので、末尾の v6 を取り、
          アプリのバージョンが更新されたことを検知したら説明書を
          更新する形に変更する」

    書き出した印を**ファイル名**で残していたので、名前に版が
    要った。印を **`APP_VERSION`** で残せば名前は固定でよい。
    古い `CorrectNote_説明書v<数字>.html` は書き出しのときに片付ける。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    src = open('app.py', encoding='utf-8').read()

    print('--- 項目48-OC（品詞と根拠は別々） ---')
    check('2つの設定を別々に読む',
          "_pos_on = bool(self.settings.get('show_pos_info'))" in src
          and "_why_on = bool(self.settings.get('show_reason_info'))" in src,
          True)
    check('**どちらもオフのときだけ空で帰る**',
          'if not (_pos_on or _why_on):' in src, True)
    check('品詞はオンのときだけ組む', 'if _pos_on:' in src, True)
    check('根拠がオフならそこで帰る', 'if not _why_on:' in src, True)
    check('**根拠を上げても品詞は上げない**（押したものだけ効く）',
          "self.settings.set('show_pos_info', True)" in src, False)

    print('--- 項目48-OD（Shift+スペース／Ctrl+スペース） ---')
    check("Shift+スペースを束縛している（48-SZ' で _ime_first に包んだ）",
          "self._ime_first(self._on_select_line_text))" in src, True)
    check("Ctrl+スペースを束縛している（48-SZ' で _ime_first に包んだ）",
          "self._ime_first(self._on_toggle_bookmark_key))" in src, True)
    check('**メモ欄と補正欄の両方に掛けている**（学び22）',
          'for _w in (self.editor, self.result_view):' in src, True)
    check('行の中身を選ぶ処理が在る',
          'def _on_select_line_text(self, event=None):' in src, True)
    check('**改行を含めない**（行の end まで）',
          "head, tail = f'{row}.0', f'{row}.end'" in src, True)
    check('ブックマークの切り替え処理が在る',
          'def _on_toggle_bookmark_key(self, event=None):' in src, True)
    check('**全部付いていれば全部外す**',
          'if all(r in self.bookmarks for r in rows):' in src, True)
    check('空白は入れない（break を返す）',
          src.count("        return 'break'") >= 2, True)

    print('--- 項目48-OE（説明書は版で検知） ---')
    import app as A
    check('名前に版が入っていない',
          A.MANUAL_FILENAME, 'CorrectNote_説明書.html')
    check('片付ける相手の形が在る',
          A.MANUAL_OLD_GLOB, 'CorrectNote_説明書v*.html')
    check('**印は APP_VERSION で残す**',
          "self.settings.set('manual_extracted', APP_VERSION)" in src, True)
    check('**印も APP_VERSION で見る**',
          "if self.settings.get('manual_extracted') == APP_VERSION:"
          in src, True)
    check('古い説明書を片付ける（数字の形だけ）',
          "r'CorrectNote_説明書v\d+\.html'" in src, True)
    import os
    check('説明書のファイルが在る',
          os.path.exists('CorrectNote_説明書.html'), True)
    check('古い名前は残っていない',
          any(f.startswith('CorrectNote_説明書v')
              for f in os.listdir('.')), False)
    return all_ok


def test_small_kana_head_units_48oi():
    """
    **小書きで始まる単位は、左の語に繋ぐ**（項目48-OI・2026-09-02・
    うにさんの観察）:

        「F2の範囲を見ると、**小文字の頭で区切ることが多い**ですね。」

    解析が実際にそう切っていた（実測）:

        に | **ゅ**うりゅく        き | **ょ**じえかくらん
        ゆり | **ょ**うくみす

    拗音の小書き（ゃゅょ）・小書き母音（ぁぃぅぇぉ）・促音（っ）・
    長音（ー）は**前の字と合わせて1拍**なので、**語の頭に立てない**。
    補正の道には既にこの守りが在る（`corrector._SMALL_KANA_HEADS`
    ——窓の切り出しと芯の切り出しの2か所）のに、**F2 の単位を作る側に
    掛かっていなかった**（学び22）。

    表は `corrector._SMALL_KANA_HEADS` ただ1つを借りる（48-GN）。
    位置は**前の語の始まりから後ろの語の終わりまで**——画面の色と
    選択がここに乗るので、ずれると印が隣の字に付く。

    補正の答えは1文字も変わらない（初期 readcheck 1949/99・
    fpcheck 0・seedcheck 39/40 壊し0 —— 全部据え置き）。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import units as U

    def t(sf, pos, start):
        return (sf, pos, sf, start, start + len(sf), True)

    print('--- 項目48-OI（小書きで始まる単位は左に繋ぐ） ---')
    got = U._merge_small_kana_heads([t('に', '助詞', 0),
                                     t('ゅうりゅく', '名詞', 1)])
    check('に|ゅうりゅく → にゅうりゅく ひとつ',
          [g[0] for g in got], ['にゅうりゅく'])
    check('位置は前の頭から後ろの尻まで', (got[0][3], got[0][4]), (0, 6))
    check('品詞は後ろの語のもの（中身のある側）', got[0][1], '名詞')

    got = U._merge_small_kana_heads([t('き', '動詞', 0),
                                     t('ょじえかくらん', '名詞', 1)])
    check('き|ょじえかくらん → ひとつ', [g[0] for g in got],
          ['きょじえかくらん'])

    got = U._merge_small_kana_heads([t('コーヒー', '名詞', 0),
                                     t('を', '助詞', 4),
                                     t('飲む', '動詞', 5)])
    check('ふつうの並びは触らない', [g[0] for g in got],
          ['コーヒー', 'を', '飲む'])

    got = U._merge_small_kana_heads([t('あ', '名詞', 0),
                                     t('っ', '名詞', 5)])
    check('**くっついていなければ繋がない**（あいだに空白）',
          [g[0] for g in got], ['あ', 'っ'])

    got = U._merge_small_kana_heads([t('カ', '名詞', 0),
                                     t('ッター', '名詞', 1)])
    check('カタカナの小書きも見る', [g[0] for g in got], ['カッター'])

    src = open('units.py', encoding='utf-8').read()
    check('表は corrector のものを借りる（2つ作らない）',
          'from corrector import _SMALL_KANA_HEADS as _SMALL' in src, True)
    check('単位を組む前に掛けている',
          'tokens = _merge_small_kana_heads(tokens)' in src, True)
    return all_ok


def test_refit_broken_units_48pv():
    """
    **壊れたかなの連なりの単位を、エンジンの知識で切り直す**
    （項目48-PV・2026-09-04・うにさんの報告4件——たぶいごうして・
    つつぎをはなす・きょじえかくらん・はしでかーそるの）。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import units as U

    def t(sf, pos, start, known=True, infl=''):
        return (sf, pos, sf if known else '', start, start + len(sf),
                known, infl)

    def one_tok(s):
        """部分の解析の代わり（連結が合えばそのまま1語）。"""
        return [(s, '名詞:一般', s, 0, len(s), True, '')]

    print('--- 項目48-PV(A)（読みの立たない塊の中の を で切る） ---')
    got = U._refit_split_wo([t('つつ', '助詞:接続助詞', 0),
                             t('ぎをはなす', '名詞:一般', 2, known=False)],
                            one_tok)
    check('つつ|ぎをはなす → つつぎ|を|はなす',
          [g[0] for g in got], ['つつぎ', 'を', 'はなす'])
    check('位置が繋がっている',
          [(g[3], g[4]) for g in got], [(0, 3), (3, 4), (4, 7)])
    got = U._refit_split_wo([t('かき', '名詞', 0), t('を', '助詞', 2),
                             t('たべた', '動詞', 3)], one_tok)
    check('正しい並び（読みが立つ）は触らない',
          [g[0] for g in got], ['かき', 'を', 'たべた'])

    print('--- 項目48-PV(C)（断片を隣と繋いで既知語に） ---')
    known = {'かーそる'}.__contains__
    got = U._refit_join_known([t('はし', '名詞:一般', 0),
                               t('で', '助詞:格助詞', 2),
                               t('かー', '名詞:一般', 3, known=False),
                               t('そる', '動詞:自立', 5),
                               t('の', '助詞:終助詞', 7)], known)
    check('かー|そる → かーそる（本人の語彙に在る読み）',
          [g[0] for g in got], ['はし', 'で', 'かーそる', 'の'])
    check('繋いだ単位は読みが立つ扱い', got[2][5], True)
    got = U._refit_join_known([t('まる', '名詞', 0),
                               t('で', '助詞:格助詞', 2)],
                              {'まるで'}.__contains__)
    check('読みの立つ並びは繋がない（本物の助詞を飲まない）',
          [g[0] for g in got], ['まる', 'で'])

    print('--- 項目48-PV(C\')（長い塊から右端の既知語を切り出す） ---')
    got = U._refit_extract_known(
        [t('きょじえかくらん', '名詞:一般', 0, known=False)],
        {'かくらん'}.__contains__)
    check('きょじえかくらん → きょじえ|かくらん',
          [g[0] for g in got], ['きょじえ', 'かくらん'])
    got = U._refit_extract_known(
        [t('ぷらねたりうむ', '名詞:一般', 0, known=False)],
        {'ぷらねたりうむ', 'たりうむ'}.__contains__)
    check('塊それ自体が既知語なら切り出さない（ぷらねたりうむ）',
          [g[0] for g in got], ['ぷらねたりうむ'])
    got = U._refit_extract_known(
        [t('よいしょーー', '名詞:一般', 0, known=False)],
        {'よいしょ', 'しょーー'}.__contains__)
    check('末尾の ー を除いて既知語なら切り出さない（伸ばしの形）',
          [g[0] for g in got], ['よいしょーー'])
    got = U._refit_extract_known(
        [t('にゅうりよくみす', '名詞:一般', 0, known=False)],
        {'くみす'}.__contains__)
    check('3字の浅い当たりでは切らない（くみす）',
          [g[0] for g in got], ['にゅうりよくみす'])

    print('--- 項目48-RM（右端の既知語＋続く漢字で辞書語） ---')
    # うにさんの報告（2026-09-05）「`きょじえかく乱`——F2 で
    # `きょじえかく` が範囲と出て品詞判定できないと出る。
    # **判定できる範囲にする**」
    def tok_kakuran(text):
        table = {
            'かく乱': [('かく乱', '名詞:サ変接続', 'カクラン', 0, 3,
                        True, '')],
            'く乱': [('く', '助詞:接続助詞', 'ク', 0, 1, True, ''),
                     ('乱', '名詞:一般', 'ラン', 1, 2, True, '')],
        }
        return table.get(text, [(text, '名詞:一般', '', 0, len(text),
                                 False, '')])

    got = U._refit_extract_known_with_kanji(
        [t('きょじえかく', '名詞:一般', 0, known=False),
         t('乱', '名詞:一般', 6)], tok_kakuran)
    check('きょじえかく|乱 → きょじえ|かく乱',
          [g[0] for g in got], ['きょじえ', 'かく乱'])
    check('切り出した先は読みが立つ扱い', got[1][5], True)
    check('品詞も辞書語のものになる', got[1][1], '名詞:サ変接続')
    # **1語に割れないなら何もしない**
    got = U._refit_extract_known_with_kanji(
        [t('あいうえおか', '名詞:一般', 0, known=False),
         t('乱', '名詞:一般', 6)], tok_kakuran)
    check('1語に割れないなら触らない',
          [g[0] for g in got], ['あいうえおか', '乱'])
    # **残る頭が2字未満なら切らない**
    got = U._refit_extract_known_with_kanji(
        [t('かかく', '名詞:一般', 0, known=False),
         t('乱', '名詞:一般', 3)], tok_kakuran)
    check('残る頭が短いなら切らない',
          [g[0] for g in got], ['かかく', '乱'])

    print('--- 項目48-RJ（学習は「変わったとき」だけ） ---')
    from vocabulary import VocabularyStore as _VS
    _st = _VS(path=None)
    check('新しく足したら True', _st.add('てすと', 'テスト'), True)
    check('**2回目は solid に上がるので True**',
          _st.add('てすと', 'テスト'), True)
    check('**3回目は何も変わらないので False**',
          _st.add('てすと', 'テスト'), False)
    check('読み・表記が無ければ False', _st.add('', 'テスト'), False)
    import io as _io4
    _jsrc = _io4.open('janome_import.py', encoding='utf-8').read()
    check('`learn_from_text` は `add` の戻りを数える',
          'if store.add(reading, surface, category):' in _jsrc, True)
    _asrc4 = _io4.open('app.py', encoding='utf-8').read()
    check('**控えを捨てる回は預かりも捨てる／残す回は残す**',
          ('if keep_current:' in _asrc4
           and 'self._bg_parked = {}' in _asrc4), True)

    print('--- 項目48-RN／48-RO（固有名詞の当て推量・カタカナの断片） ---')
    import katakana_frag as _kf
    check('`セク` は断片', _kf.is_fragment('セク'), True)
    check('**`ブレ` は断片ではない**（48-OY の的）',
          _kf.is_fragment('ブレ'), False)
    check('**`プレイ` も断片ではない**', _kf.is_fragment('プレイ'), False)
    check('表が読める', _kf.available(), True)
    import oddness as _odd4
    check('`_katakana_word_known(セク)` が False',
          _odd4._katakana_word_known('セク'), False)
    check('`_katakana_word_known(ブレ)` は True',
          _odd4._katakana_word_known('ブレ'), True)
    # **表の検品**——同じ綴りが「語」と「断片」の両方に載っていないこと
    # **判定の材料（`tools_local/katakana_frag_src/`）は公開しない決まり**
    # （項目48-QF）。**無ければこの2件だけ飛ばす**——
    # **有るのに落ちるのと、無いから測れないのは別**（項目48-OB で
    # `readcheck.py` に置いたのと同じ形。**CI は追跡ファイルだけで回る**ので、
    # ここに栓が無いと新しく clone した写しで tests_mock がまるごと落ちる
    # ——項目48-TL・2026-09-06 に実際に落ちた）
    import glob as _glob
    _frag, _word = set(), set()
    _src4 = _glob.glob('tools_local/katakana_frag_src/judgments_*.tsv')
    for _p4 in _src4:
        for _ln in _io4.open(_p4, encoding='utf-8'):
            if _ln.startswith('#') or '\t' not in _ln:
                continue
            _c = _ln.split('\t')
            (_frag if _c[1].strip() == '断片' else _word).add(_c[0].strip())
    if _src4:
        check('**語と断片の両方に載っている綴りは無い**',
              sorted(_frag & _word), [])
        check('表に載っているのは断片だけ（json）',
              set(_kf._load()) <= _frag, True)
    else:
        print('..  カタカナ2字の表の検品（判定の材料が無いので飛ばす）')

    print('--- 項目48-TO/TP/TQ（ドロップ・同じファイル・タブの右クリック）---')
    # うにさんの指定（2026-09-07）:
    #   ・ファイルをアプリにドロップしたら、新規タブにテキスト情報を表示する
    #   ・同一のファイルを開いた場合は、タブを増やさず、重複するタブを表示する
    #   ・タブを右クリックしたらメニューを出し、「エクスプローラで選択」で
    #     フォルダを開いて該当のファイルが選択された状態にする
    import app as _A_to
    _src_to = _io4.open('app.py', encoding='utf-8').read()
    _App = _A_to.CorrectNoteApp

    # 48-TP **開く道は1本**（学び22——門は全部の道に掛ける）
    check('48-TP ファイルを開く入口は `_open_paths` 1つ',
          'def _open_paths(' in _src_to
          and _src_to.count('self._open_paths(') >= 2, True)
    check('48-TP 「開く…」も同じ入口を通る',
          "askopenfilename(" in _src_to
          and _src_to.index('def open_file(') < _src_to.index(
              'self._open_paths([path])'), True)
    check('48-TP 重複の判定は1か所（`_find_tab_by_path`）',
          _src_to.count('def _find_tab_by_path(') == 1
          and _src_to.count('self._find_tab_by_path(') == 1, True)

    # 同じファイルかの見分け（大文字小文字・相対・空）
    import os as _os_to
    _here = _os_to.path.abspath('app.py')
    check('48-TP 大文字小文字の違いは同じファイル',
          _App._same_file(_here, _here.upper()), True)
    check('48-TP 相対でも同じファイル',
          _App._same_file('app.py', _here), True)
    check('48-TP 別のファイルは別',
          _App._same_file(_here, _os_to.path.abspath('session.py')), False)
    check('48-TP 無題どうしを同じ扱いにしない',
          (_App._same_file(None, None), _App._same_file('', 'x')),
          (False, False))

    # 48-TO ドロップの受け——**窓の手続きから Tk を触らない**
    check('48-TO ドロップの仕掛けが在る（SetWindowSubclass ＋ DragAcceptFiles）',
          'def _setup_file_drop(' in _src_to
          and 'SetWindowSubclass' in _src_to
          and 'DragAcceptFiles' in _src_to, True)
    check('48-TO ★ 手続きの中では Tk を呼ばず、受け皿に積むだけ',
          'self._drop_queue.append(got)' in _src_to
          and 'def _drain_drop_queue(' in _src_to, True)
    _proc = _src_to[_src_to.index('def _on_message('):
                    _src_to.index('self._drop_proc = SUBCLASSPROC')]
    check('48-TO 手続きの中に root. の呼び出しが1つも無い',
          'self.root' in _proc, False)
    check('48-TO 閉じるときに差し替えを外す',
          'def _teardown_file_drop(' in _src_to
          and 'self._teardown_file_drop()' in _src_to[
              _src_to.index('def _on_close('):], True)
    check('48-TO ctypes の戻り値の型を決めている（64bit のハンドルを切らない）',
          'DragQueryFileW.restype' in _src_to
          and 'DefSubclassProc.restype' in _src_to, True)
    check('48-TO 道の長さは先に聞く（決め打ちの入れ物で黙って切らない）',
          'need = shell32.DragQueryFileW(wparam, i, None, 0)' in _src_to
          and 'create_unicode_buffer(need + 1)' in _src_to, True)

    # テキストでないもの・フォルダは開かない
    check('48-TO テキストでないファイルは開かない（NUL を見る）',
          "b'\\x00' in raw[:8192]" in _src_to, True)
    check('48-TO フォルダは開かない', "os.path.isdir(path)" in _src_to, True)

    # 48-TQ タブの右クリックは、このアプリの一覧に揃える
    check('48-TQ 右クリックは `_make_dropdown`（tk.Menu の popup を作らない）',
          'def _on_tab_right_press(' in _src_to
          and 'self._make_dropdown(self._tab_menu_items(' in _src_to
          and 'tk_popup' not in _src_to, True)
    check('48-TQ 札の3か所すべてに結ぶ（文字・✕・枠）',
          "for _w in (f, lb, x):" in _src_to
          and "_w.bind('<Button-3>'," in _src_to, True)
    check('48-TQ エクスプローラへは1つの文字列で渡す（空白を含む道）',
          """'explorer /select,"%s"' % path""" in _src_to, True)
    check('48-TQ 今見ているタブの道は current_file が本物',
          'def _tab_path(' in _src_to
          and 'index == self.session.active and self.current_file' in _src_to,
          True)

    # ---- 検品で見つかって塞いだ穴（2026-09-07）
    check("48-TO' 行末を均す（開いて保存で CR が増えない）",
          "text.replace(_cr + _lf, _lf).replace(_cr, _lf)" in _src_to
          and '.splitlines(' not in _src_to[
              _src_to.index('def _read_text_file('):
              _src_to.index('def _place_in_new_tab(')], True)
    check("48-TO'' 2度掛けない／失敗したら掛けた分を外す／管理者でも通す",
          "if getattr(self, '_drop_proc', None) is not None:" in _src_to
          and 'ChangeWindowMessageFilterEx' in _src_to
          and _src_to.count('self._teardown_file_drop()') == 2, True)
    check("48-TP' 新しい本文には、前のタブの当て直しを掛けない",
          'self._pending_scroll = 0.0' in _src_to[
              _src_to.index('def _place_in_new_tab('):
              _src_to.index('def _open_paths(')], True)
    # ★★ **本文を入れ替える道すべてで、前の文書に結び付いたものを下ろす**
    _pl = _src_to[_src_to.index('def _place_in_new_tab('):
                  _src_to.index('def _open_paths(')]
    _ld = _src_to[_src_to.index('def _load_active_tab('):]
    _ld = _ld[:_ld.index("self.editor.insert('1.0', tab.get('text'")]
    check("48-TP'' ファイルを開く道で下ろす（自動反映と F2 の的）",
          'self._autofix_reset()' in _pl
          and 'self._clear_f2_target()' in _pl, True)
    check("48-TP'' タブを移る道でも下ろす（学び22。v1.6.0 から在った穴）",
          'self._autofix_reset()' in _ld
          and 'self._clear_f2_target()' in _ld, True)
    check("48-TP'' 落とす前に一覧を閉じる（焦点が動くと的が残る）",
          'self._close_dropdown()' in _src_to[
              _src_to.index('def _on_files_dropped('):], True)
    # ---- 48-TW **窓は本体だけではない**（学び22——門は全部の道に掛ける）
    check('48-TW 掛ける口が分かれている（本体以外の窓にも掛けられる）',
          'def _attach_file_drop(' in _src_to
          and 'def _detach_file_drop(' in _src_to, True)
    check('48-TW 簡易入力の窓にも掛ける',
          'self._quick_drop_hwnds = self._attach_file_drop(win)' in _src_to,
          True)
    _qc = _src_to[_src_to.index('def _close_quick_capture('):]
    _qc = _qc[:_qc.index('def ', 10)]
    check('48-TW 閉じるときに外す——**destroy の前**（死んだ番号を残さない）',
          '_detach_file_drop' in _qc
          and _qc.index('_detach_file_drop') < _qc.index('win.destroy()'),
          True)
    check('48-TW 同じ窓に2度掛けない（控えに在る番号は飛ばす）',
          'if h in self._drop_hwnds:' in _src_to, True)
    check('48-TW 行き先は窓によらず同じ1本（48-GN——窓ごとに書き分けない）',
          _src_to.count('self._open_paths(list(paths))'), 1)
    check('48-TW 掛け直しのときも、前の窓の分を外してから手放す',
          '_detach_file_drop' in _src_to[
              _src_to.index('def _open_quick_capture('):
              _src_to.index("win = tk.Toplevel(self.root)")], True)

    # ★★ **裏のスレッドで語彙を書き換えない**（48-TT・検品で止められた）。
    # `VocabularyStore` は錠前を持たないので、主スレッドが辞書を回している
    # 最中に出し入れすると落ちる。覚え直しは主スレッドのまま。
    check('48-TT 裏のスレッドは語彙を書き換えない',
          'self._learn_english_from_tabs' not in _src_to[
              _src_to.index('def _start_warmup('):
              _src_to.index('def _poll_warmup(')], True)
    check('48-TT 覚え直しは主スレッド（_poll_warmup）で',
          'self._learn_english_from_tabs()' in _src_to[
              _src_to.index('def _poll_warmup('):
              _src_to.index('def _apply_vocab_restore(')], True)
    check('48-TT 覚え直したあとの解析は、裏で回す入口へ渡す',
          'self._warm_then_analyze()' in _src_to[
              _src_to.index('def _poll_warmup('):
              _src_to.index('def _apply_vocab_restore(')], True)
    check('48-TT 覚え直しの中身は1か所（loanword を呼ぶのは1つの関数だけ）',
          _src_to.count('from loanword import relearn_english_from_texts')
          == 1, True)
    check("48-TT' 下ごしらえの最中は解析へ進まない",
          "if getattr(self, '_warmup', None) is not None:" in _src_to[
              _src_to.index('def _analyze_if_changed('):
              _src_to.index('def _analyze(')], True)
    _csrc48tv = _io4.open('corrector.py', encoding='utf-8').read()
    _lsrc48tv = _io4.open('loanword.py', encoding='utf-8').read()
    check('48-TV 語彙を読み損ねたとき、空の表を控えに焼き付けない',
          'return []' in _csrc48tv[
              _csrc48tv.index('def _romaji_reading_table('):
              _csrc48tv.index('def _romaji_reading_table(') + 1600]
          and _lsrc48tv.count('return {}       # 同上') == 1, True)
    check('48-TV 覚え直しに失敗したら知らせる（黙って英単語を失わない）',
          '英単語の覚え直しに失敗しました' in _src_to, True)
    check('48-TS ファイルを開く道も、下ごしらえを裏で回す入口を通る',
          'self._warm_then_analyze()' in _src_to[
              _src_to.index('def _open_paths('):
              _src_to.index('def _setup_file_drop(')]
          and "self._analyze_cause = 'ファイルを開く'" in _src_to, True)
    check('48-TS きっかけの名前は呼び手が決めていればそれを使う',
          _src_to.count("or 'タブの切り替え')") == 2, True)
    check("48-TP''' realpath は最後の手段（切れた道で固まらない）",
          'os.path.basename(na) != os.path.basename(nb)' in _src_to, True)

    print('--- 項目48-TM（消えたときの記録は、本文と命運を共にする）---')
    # うにさんの指定（2026-09-07）「**本文にない履歴が問題**であって、
    # アプリ内に打った文字の情報が残ることは構いません。
    # **アプリ内の文字を消したら連動して履歴が消えれば**よいです」。
    # `ime_readings.keep_only_in`（48-QM）と同じ形にした。
    import app as _A_tm
    _src_tm = _io4.open('app.py', encoding='utf-8').read()
    check('48-TM 掃除の口が在り、ime_readings と同じ2か所から呼ばれる',
          'def _sz_prune_log(' in _src_tm
          and _src_tm.count('self._sz_prune_log()') == 2, True)
    check('48-TM 既定で切にする門は残っていない',
          '_sz_enabled' in _src_tm, False)
    _f_tm = _A_tm.CorrectNoteApp._sz_filter_log
    _blob_tm = (
        "=== 2026-09-07 01:00:00  行 3  KeyRelease=space state=1\n"
        "  前 (7字): 'いまも在る行'\n"
        "  後 (2字): 'いま'\n"
        "  消えた: 'も在る行'\n"
        "=== 2026-09-07 01:00:05  行 9  KeyRelease=U state=1\n"
        "  前 (8字): 'もう消した行'\n"
        "  後 (1字): 'も'\n"
        "  消えた: 'う消した行'\n")
    _kept_tm = _f_tm(_blob_tm, ['ここに いまも在る行 が書いてある'])
    check('48-TM 本文に在る記録は残る', 'いまも在る行' in _kept_tm, True)
    check('48-TM 本文から消えた記録は落ちる', 'もう消した行' in _kept_tm, False)
    check('48-TM 本文が取れなかったら触らない（紙が1枚も無い）',
          _f_tm(_blob_tm, []), _blob_tm)
    check('48-TM 中身の無い紙なら全部落とす', _f_tm(_blob_tm, ['']), '')
    check('48-TM 的（前の行）が読めない記録は落とす',
          _f_tm("=== 壊れた記録\n  なにも無い\n", ['いまも在る行']), '')
    print("--- 項目48-RI（壊れた連なりの**左端**から既知語を切り出す） ---")
    # うにさんの報告（2026-09-05）「`かんいりゅうりょく` を F2 で見ると
    # `いりゅうりょく` で区切られ、品詞として判定できないと出ます」。
    # 解析は `かん＋いり＋ゅうりょく` と刻み、48-PV(C) が断片を左と
    # 繋いで `いりゅうりょく` を作る。**左端を切り出す手が無かった。**
    got = U._refit_extract_known_head(
        [t('かん', '名詞:一般', 0),
         t('いり', '動詞:自立', 2),
         t('ゅうりょく', '名詞:一般', 4, known=False)],
        {'かんい'}.__contains__)
    check('かん|いり|ゅうりょく → かんい|りゅうりょく',
          [g[0] for g in got], ['かんい', 'りゅうりょく'])
    check('切り出した頭は読みが立つ扱い', got[0][5], True)

    # ★★ **もう切れている場所では何もしない**（実測で足した門）
    # ——切り方が変わらないのに触ると、**品詞だけ落ちる**
    got = U._refit_extract_known_head(
        [t('もくもく', '副詞:一般', 0),
         t('しゅー', '名詞:一般', 4, known=False)],
        {'もくもく'}.__contains__)
    check('もう切れている場所では触らない（品詞を落とさない）',
          [(g[0], g[1]) for g in got],
          [('もくもく', '副詞:一般'), ('しゅー', '名詞:一般')])

    # ★★ **残りは4字以上**（実測で足した門）——正しいかなの文を割らない
    got = U._refit_extract_known_head(
        [t('みて', '動詞:自立', 0),
         t('います', '名詞:一般', 2, known=False)],
        {'みてい'}.__contains__)
    check('残りが短いなら切らない（みています を みてい|ます にしない）',
          [g[0] for g in got], ['みて', 'います'])

    # 48-PV(C') と同じ2つの門
    got = U._refit_extract_known_head(
        [t('ぷらね', '名詞:一般', 0),
         t('たりうむ', '名詞:一般', 3, known=False)],
        {'ぷらねたりうむ', 'ぷらね'}.__contains__)
    check('連なりそれ自体が既知語なら切り出さない',
          [g[0] for g in got], ['ぷらね', 'たりうむ'])
    got = U._refit_extract_known_head(
        [t('かんいりゅうりょく', '名詞:一般', 0, known=False)],
        {'かんい'}.__contains__)
    check('1トークンだけの連なりは右端の手にまかせる',
          [g[0] for g in got], ['かんいりゅうりょく'])
    # **読みが立っている連なりは触らない**（壊れていない）
    got = U._refit_extract_known_head(
        [t('かんい', '名詞:一般', 0),
         t('りゅうりょく', '名詞:一般', 3)],
        {'かんい'}.__contains__)
    check('壊れていない連なりは触らない',
          [g[0] for g in got], ['かんい', 'りゅうりょく'])

    print('--- 項目48-RF（紫の項目は1本・補正欄からも引ける） ---')
    import io as _io3
    _src3 = _io3.open('app.py', encoding='utf-8').read()
    check('紫の項目を組むのは1か所だけ',
          _src3.count("'― 紫の印 ―'"), 1)
    check('その1本は `_odd_menu_items`',
          'def _odd_menu_items(self, row, src_start, src_end):' in _src3,
          True)
    check('メモ欄も補正欄も、その1本を呼ぶ',
          _src3.count('self._odd_menu_items('), 2)
    check('対応表は1本（`_span_pairs`）',
          _src3.count('def _span_pairs(self, row):'), 1)
    check('行きも帰りもその1本を使う',
          _src3.count('self._span_pairs(row)'), 2)
    check('**当てずっぽうでは出さない**（写した字が合うときだけ）',
          "if _orig == unit.get('text'):" in _src3, True)

    print('--- 項目48-PV(B)（壊れた連なりの末尾を「末尾にくる言葉」で） ---')
    got = U._refit_run_tail([t('たぶ', '動詞:自立', 0, infl='基本形'),
                             t('い', '名詞:一般', 2),
                             t('ごうし', '名詞:サ変接続', 3),
                             t('て', '助詞:格助詞:連語', 6)], one_tok)
    check('たぶ|い|ごうし|て → たぶ|い|ごう|して',
          [g[0] for g in got], ['たぶ', 'い', 'ごう', 'して'])
    check('位置が繋がっている',
          [(g[3], g[4]) for g in got],
          [(0, 2), (2, 3), (3, 5), (5, 7)])
    got = U._refit_run_tail([t('おもい', '動詞:自立', 0, infl='連用形'),
                             t('まして', '助動詞', 3)], one_tok)
    check('壊れていない連なりは触らない（おもい|まして）',
          [g[0] for g in got], ['おもい', 'まして'])

    src = open('units.py', encoding='utf-8').read()
    check('両方の道に掛けている（学び22）',
          src.count('tokens = _refit_broken_kana_units('
                    'tokens, tokenize_fn, known_kana_word'), 2)
    check('異様の述語は corrector の1本を借りる（48-GN）',
          'from corrector import _verb_noun_pair as _vnp' in src, True)

    print('--- 項目48-RQ〜48-RS（せ＝゛の隣を先に疑う・'
          '語＋手が生んだ助詞＋語） ---')
    # うにさんの指定（2026-09-05）「背中セクよりも先に、せ が ゛ の
    # 隣接打ち間違いを疑う。解析課の か が が に繋がれば接続詞として
    # 自然で、後ろの文とも繋がる」
    import corrector as _C5
    # 48-RR: 同じ誤りの繰り返しが1つの仮説として作られる
    _one = list(_C5._mark_slip_repairs('かいせきかせなかせく'))
    _two = sorted({r2 for r in _one for r2 in _C5._mark_slip_repairs(r)})
    check('印の隣×1 は2つ', sorted(_one),
          ['かいせきかせながく', 'かいせきがなかせく'])
    check('印の隣×2（同じ誤りの繰り返し）は かいせきがながく',
          _two, ['かいせきがながく'])
    check('born: 手が変えた位置は が の2か所',
          sorted(_C5._born_positions('かいせきかせなかせく',
                                     'かいせきがながく')), [4, 6])
    check('born: 1手なら1か所',
          _C5._born_positions('りゅうりょく', 'にゅうりょく'), {0})
    check('born: 同じ読みなら空', _C5._born_positions('あいう', 'あいう'),
          set())
    _src5 = open('corrector.py', encoding='utf-8').read()
    check('記録名は「同じ誤りの繰り返し」',
          "_add(r2, '同じ誤りの繰り返し（印の隣×2）', 2.0)" in _src5, True)
    # 48-RS: 1字の機能語だけの説明は7字以上には認めない
    check('かいせきかせなかせく は機能語だけではない',
          _C5._is_all_functional('かいせきかせなかせく'), False)
    check('かいせきがながく も（正しい読みだが機能語の並びではない）',
          _C5._is_all_functional('かいせきがながく'), False)
    check('になっていて は今までどおり機能語だけ',
          _C5._is_all_functional('になっていて'), True)
    check('がおわった も今までどおり', _C5._is_all_functional('がおわった'),
          True)
    check('2字以上の機能語を使う説明は、長くても通る（のではないでしょうか）',
          _C5._is_all_functional('のではないでしょうか'), True)
    check('同（してもらえませんか）',
          _C5._is_all_functional('してもらえませんか'), True)
    check('上限は 6', _C5._ALL_FUNC_ONECHAR_MAX, 6)
    # 48-RQ: 語＋手が生んだ助詞＋語 の門（形だけ・エンジンは写しで測る）
    check('_gap は (0, 1)', 'for _gap in (0, 1):' in _src5, True)
    check('born を見ている（(i)）', 'if not born or ln1 not in born:' in _src5,
          True)
    check('でで は開けない（(vi)）',
          'if ln1 + 1 < n and text[ln1 + 1] == text[ln1]:' in _src5, True)
    check('A/B の道にも掛けている（学び22）',
          '_wbp = _word_born_particle_fix(run, store, dict_index,' in _src5,
          True)
    check('D の道でも born を渡している',
          'born=(_born_positions(_rd, _v)' in _src5, True)
    check('48-RK より先に置いてある（先に疑う）',
          _src5.index('_wbp = _word_born_particle_fix(')
          < _src5.rindex('_khc = _fix_known_head_compound(\n'), True)

    print('--- 項目48-RU（入れ子で通した行の紫を捨てない） ---')
    # `・「解析課背中セク、」は、まず「背中セク」が…` で前の塊を直したら、
    # 後ろの `背中セク` の紫まで消えていた。内側の印は内側に渡した行の
    # 位置なので、外の行へ**写す**（equal の塊の中だけ）
    _outer = '・「解析課背中セク、」は、まず「背中セク」が'
    _inner = '・「解析が長く、」は、まず「背中セク」が'
    check('写し替え: 後ろの塊の紫が外の位置に来る',
          _C5._map_inner_spans(_outer, _inner, [(14, 18)]), [(16, 20)])
    check('写した先の字が同じ', _outer[16:20], '背中セク')
    check('直した範囲に掛かる印は写さない（＝直せた範囲は消える）',
          _C5._map_inner_spans(_outer, _inner, [(2, 8)]), [])
    check('同じ行なら そのまま',
          _C5._map_inner_spans('あいう', 'あいう', [(0, 2)]), [(0, 2)])
    check('印が無ければ空', _C5._map_inner_spans(_outer, _inner, []), [])
    check('**入れ子の返し口で `odd_spans` を捨てているのは `empty` だけ**',
          _src5.count("'odd_spans': [],"), 1)
    check('入れ子10か所とも写している',
          _src5.count("'odd_spans': _map_inner_spans("), 10)

    print('--- 項目48-RV〜48-RY（品詞のつながり・読みの切れ目・預かり） ---')
    # 48-RV(c): 手を当てていない読みの立つ語の読みの中に、組の境目を置かない
    _ti = [('背中', True), ('セク', False)]
    _al = [['せなか'], ['せく']]
    check('はいなかせく → ハイ｜仲良く（境目2）は 背中 の読みの中なので不可',
          _C5._hand_boundaries_ok(_ti, _al, 'はいなかせく', 'はいなかよく', [2]),
          False)
    check('境目4（背中｜よく）なら置いてよい',
          _C5._hand_boundaries_ok(_ti, _al, 'はいなかせく', 'はいなかよく', [4]),
          True)
    check('手が触った語は守らない（かせ→が で 背中 が変わる 解析が長く）',
          _C5._hand_boundaries_ok(
              [('解析', True), ('課', True), ('背中', True), ('セク', False)],
              [['かいせき'], ['か'], ['せなか'], ['せく']],
              'かいせきかせなかせく', 'かいせきがながく', [4]), True)
    check('格下げした固有名詞は守らない（たぶ｜いどう）',
          _C5._hand_boundaries_ok(
              [('田部井', False), ('号', True), ('し', True), ('て', True)],
              [['たぶい'], ['ごう'], ['し'], ['て']],
              'たぶいごうして', 'たぶいどうして', [2]), True)
    check('揃え方が分からなければ意見なし',
          _C5._hand_boundaries_ok([('あ', True)], [['い']], 'う', 'え', [1]),
          True)
    check('48-RV(a) 2語の組は名詞＋名詞（源を見張る）',
          "_why['品詞のつながり'] += 1" in _src5, True)
    check('48-RV(b) 短い部品は is_unit',
          '_sj_sf.is_unit(x + y) is not True' in _src5, True)
    check("48-RW' 直した読みを変換の道に通す（かな連続まるごと）",
          '_cv = _convert_fixed_kana_run(_whole, store, dict_index)' in _src5,
          True)
    check("48-RW' 2語の組の判定は1本（_two_word_faces）",
          _src5.count('def _two_word_faces(') == 1
          and 'return _two_word_faces(v, lo_a, store)' in _src5, True)
    check('48-RW は外してある（呼び手が無い）',
          _src5.count('as_kana_run=True') == 0, True)
    import io as _io6
    _asrc6 = _io6.open('app.py', encoding='utf-8').read()
    check('48-RY 途中の状態を預ける', '_fg_parked' in _asrc6
          and "'todo': _fg_todo[_fg_pos:]" in _asrc6, True)
    check('48-RY 戻ったら預かりから続ける',
          "self._trace_analysis('預かりから続き'" in _asrc6, True)
    check('48-RY 裏は表が済ませた行を飛ばす',
          "if st['results'][i] is None:" in _asrc6, True)
    check('48-RX 学習は直した範囲・紫の範囲を潰す',
          "_r.get('original_spans')" in _asrc6
          and "_r.get('odd_spans')" in _asrc6, True)
    check('48-RV(e) 尾が接頭の お で終わる形は無い',
          "if i < n and text[n - 1] == 'お':" in _src5, True)
    check('48-RV(e) 1字の助詞だけの尾は2字以上には認めない',
          'if n - i >= 2 and not multi[n]:' in _src5, True)
    check('48-RV(e) 2つ目がかなだけなら部品ではない',
          "if all(is_hiragana(c) or c == 'ー' for c in piece):" in _src5,
          True)
    check('48-RV(e) 読みが2字以下の部品に手の変更が掛かっていれば採らない',
          'if (born and ln2 <= 2' in _src5, True)

    # --- 7巡目（2026-09-06・項目48-SE〜48-SH）---
    print('--- 項目48-SE〜48-SH（F2 の単位・候補・検索の履歴・控えの整理） ---')
    _usrc7 = _io6.open('units.py', encoding='utf-8').read()
    check('48-SE 助詞＋述語の尾を切る（_refit_particle_predicate）',
          'def _refit_particle_predicate(' in _usrc7, True)
    check('48-SE 外来語の頭を切る（_refit_loanword_head）',
          'def _refit_loanword_head(' in _usrc7, True)
    check('48-SE 単位の切り直しに ①（紫・直した範囲）を渡す',
          'odd_spans=_odd_sp' in _usrc7
          and "result.get('original_spans')" in _usrc7, True)
    check('48-SE ①の連なりは頭を1つの単位に（たぶいごう｜して）',
          '_odd_run and len(head) >= 3' in _usrc7, True)
    check('48-SE 述語の判定は1本（_predicate_text）',
          _usrc7.count('def _predicate_text(') == 1, True)
    check('48-SE カタカナ語の直後の ご は 後（名詞:接尾）',
          "'名詞:接尾', 'ご'" in _usrc7, True)
    check('48-SF 紫のかな連続の中の単位には連続まるごとの候補',
          'def _odd_run_candidates(' in _asrc6
          and '_run_c = self._odd_run_candidates(row, unit)' in _asrc6, True)
    check('48-SF 選ぶと連続まるごとが置き換わる（span）',
          "if isinstance(cand, dict) and cand.get('span'):" in _asrc6, True)
    check('48-SG 検索の履歴は保存しない（settings にも session にも書かない）',
          '_find_history' in _asrc6
          and "settings.set('find_history'" not in _asrc6, True)
    check('48-SG 前回の検索語を欄に置く',
          "initial = getattr(self, '_find_last_text', '') or ''" in _asrc6,
          True)
    check('48-SG 覚える場所は1か所（_current_pattern）',
          _asrc6.count('self._remember_find_text(_q)') == 1, True)
    check('48-SG 下キーで履歴（IME の受け皿で包む）',
          "e_find.bind('<Down>', self._ime_first(" in _asrc6, True)
    check('48-SG 履歴一覧の Up は受け皿が先',
          "lb.bind('<Up>', self._on_find_history_up)" in _asrc6, True)
    check("48-SG' 開いた直後の検索は先頭から（タブ移動のあと末尾のカーソルでも）",
          "if hit is None and getattr(self, '_find_fresh', False):" in _asrc6
          and "self._find_fresh = True" in _asrc6, True)
    check('48-SL 検索ウインドウを開いたままタブを移っても焦点は検索ウインドウに残す（全部の道＝_load_active_tab で受ける）',
          'def _find_follow_tab(' in _asrc6
          and 'if not self._find_follow_tab():' in _asrc6
          and _asrc6.count('self._find_follow_tab()') == 1, True)
    check('48-SL 移った先の検索は新しい検索・履歴の一覧は閉じる・焦点が無いときは奪わない',
          _asrc6.count('self._find_fresh = True') == 2
          and 'has_focus = self.root.focus_displayof() is not None' in _asrc6, True)
    check('48-SY 右ボタン（右ドラッグ・右ダブルクリック＝俯瞰）も「触っている」に数える',
          "'<ButtonPress-3>', '<B3-Motion>', '<Double-Button-3>'," in _asrc6
          and "if getattr(self, '_overview', None) is not None:" in _asrc6
          and "if _d and _d.get('mode') == 'scroll':" in _asrc6
          and 'if self._analyze_yields <= self.ANALYZE_MAX_YIELD or _held:' in _asrc6, True)
    import app as _A9
    check("48-SZ' 非 ASCII の字を伴う KeyPress は、キー名が何であれ IME の確定（映＝space・さ＝U）",
          _A9.ime_confirmed_char('space', '映') == '映'
          and _A9.ime_confirmed_char('U', 'さ') == 'さ'
          and _A9.ime_confirmed_char('space', ' ') is None
          and _A9.ime_confirmed_char('??', '反') is None
          and _A9.ime_confirmed_char('Delete', '.') == '.', True)
    check("48-SZ' <Shift-space>・<Control-space> は _ime_first で包む",
          "_w.bind('<Shift-space>'," in _asrc6
          and 'self._ime_first(self._on_select_line_text))' in _asrc6
          and 'self._ime_first(self._on_toggle_bookmark_key))' in _asrc6, True)
    check('48-TA 右を押してから動いていたら、離しは候補一覧を開かない（左右同時のドラッグ）',
          "self._r3_press = (int(event.x_root), int(event.y_root))" in _asrc6
          and "_p = getattr(self, '_r3_press', None)" in _asrc6
          and "self.root.tk.call('tk::CancelRepeat')" in _asrc6, True)
    check('48-SZ 消えたときの証拠を残す見張り（KeyPress の控え・KeyRelease で縮みを見る・deletion_log.txt）',
          'def _sz_check_shrink(' in _asrc6
          and "self._sz_note_key(event)" in _asrc6
          and "self._sz_check_shrink(event)" in _asrc6
          and "'deletion_log.txt'" in _asrc6, True)
    check('48-SL 履歴の一覧を Enter／Esc で閉じるときは、焦点を先に検索欄へ返す（48-SG の穴）',
          '焦点を先に検索欄へ返してから閉じる' in _asrc6
          and "entry.focus_set()       # 先に返す（項目48-SL・上と同じ）" in _asrc6, True)
    check('48-SH 控えは今在るタブの本文のぶんだけ（_prune_analysis_cache）',
          'def _prune_analysis_cache(' in _asrc6
          and _asrc6.count('self._prune_analysis_cache(keep=') == 2, True)
    check('48-SH いま見ているタブは、いま解析している本文のほう',
          'if _i == _cur and k0:' in _asrc6, True)
    # _remember_find_text の動き（偽の self で）
    import ast as _ast7
    _tree7 = _ast7.parse(_asrc6)
    _fn7 = None
    for _node in _ast7.walk(_tree7):
        if isinstance(_node, _ast7.FunctionDef) \
                and _node.name == '_remember_find_text':
            _fn7 = _node
            break
    _ns7 = {}
    exec(compile(_ast7.Module(body=[_fn7], type_ignores=[]), '<f7>', 'exec'),
         _ns7)

    class _S7:
        pass
    _s7 = _S7()
    _s7._find_history = []
    _s7._find_last_text = ''
    for _q in ('abc', 'def', 'abc', ''):
        _ns7['_remember_find_text'](_s7, _q)
    check('48-SG 新しいものが先・同じ語は1つ・空は覚えない',
          (_s7._find_history, _s7._find_last_text), (['abc', 'def'], 'abc'))
    for _k in range(30):
        _ns7['_remember_find_text'](_s7, 'q%d' % _k)
    check('48-SG 履歴は20件まで', len(_s7._find_history), 20)
    return all_ok


def test_unit_reading_and_rows_20260904():
    """
    **単位まとめの読みの引き継ぎ（項目48-QA）と、候補一覧の高さ
    （項目48-QB）**（2026-09-04・うにさんの画面 `たぶい` の候補一覧）。

    48-QA: `_merge_stem_with_tail` が text/base だけ伸ばして
        **reading を語幹のまま**にしていた——`たぶい` の候補が全部
        `たぶ` の話（同音の語 タブ・かな表記 たぶ）になり、
        `見ています` の読みが `み` のままだった。
    48-QB: 一覧の高さ「16＋説明の行数」は、説明の見出しが16行目より
        下から始まる語（候補が16件超）で足りない——`たぶい` は
        品詞判定の下2行（`い ＝ 名詞` と ※の注記）が画面の外に出た。
        根拠だけオン（48-OC）のときは全く伸びなかった。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import units as U

    def mk(text, reading, pos='', start=0, functional=None):
        return {'text': text, 'base': text, 'reading': reading,
                'pos': pos, 'kind': 'plain', 'detail': None,
                'chosen_hint': None, 'functional': functional,
                'start': start, 'end': start + len(text),
                'prev': '', 'next': ''}

    print('--- 項目48-QA（語幹＋尾の単位は、読みも繋ぐ） ---')
    got = U._merge_stem_with_tail(
        [mk('見', 'み', pos='動詞:自立'),
         mk('ています', 'ています', start=1, functional=True)])
    check('見｜ています → 見ています', [g['text'] for g in got],
          ['見ています'])
    check('読みが みています になる', got[0]['reading'], 'みています')
    got = U._merge_stem_with_tail(
        [mk('たぶ', 'たぶ', pos='動詞:自立'),
         mk('い', '', start=2, functional=True)])
    check('尾の読みが無ければ文字そのもの（たぶ＋い）',
          got[0]['reading'], 'たぶい')
    got = U._merge_stem_with_tail(
        [mk('見', '', pos='動詞:自立'),
         mk('ています', 'ています', start=1, functional=True)])
    check('語幹の読みが立たないなら、読みは名乗らない',
          got[0]['reading'], '')

    print('--- 項目48-QB（説明の塊ぜんぶが見える高さ） ---')
    src = open('app.py', encoding='utf-8').read()
    check('見出しは品詞判定と補正根拠の両方を見る（48-OC の続き）',
          'if _t in (ANALYSIS_HEAD_POS, ANALYSIS_HEAD_WHY):' in src, True)
    check('「16＋説明の行数」の足りない式は残っていない',
          'DROPDOWN_ROWS + (len(items) - _i)' in src, False)
    check('高さは項目の総数（上限 ROWS_MAX）',
          'rows = min(len(items), DROPDOWN_ROWS_MAX)' in src, True)
    return all_ok


def test_pos_from_row_context_48qc_48qd():
    """
    **品詞判定は、行の解析が1語と見た範囲ではその品詞を名乗る**
    （項目48-QC）と、**当て推量の札を名乗らせない**（項目48-QD）。
    2026-09-04・うにさんの指定「品詞の判定を見れば見るほど変」。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import explain
    import units as U

    def tok(text):
        """割り直すと鎖になるもの（画面に出ていた当て推量）。"""
        table = {
            'かな': [('か', '助詞:副助詞', 'カ', 0, 1, True, ''),
                     ('な', '助詞:終助詞', 'ナ', 1, 2, True, '')],
            '日間': [('日', '名詞:固有名詞:地域:国', 'ニチ', 0, 1, True, ''),
                     ('間', '名詞:接尾:一般', 'カン', 1, 2, True, '')],
            '押し': [('押し', '動詞:自立', 'オシ', 0, 2, True, '連用形')],
        }
        return table.get(text, [(text, '名詞:一般', text, 0, len(text),
                                 True, '')])

    print('--- 項目48-QC（行の解析が1語と見た範囲は、その品詞で言う） ---')
    check('かな は 名詞（か＋な の鎖にしない）',
          explain.pos_lines('かな', tok, pos_hint='名詞:一般',
                            atomic_hint=True, known_hint=True),
          ['名詞'])
    check('まとめた単位（atomic でない）は鎖のまま',
          explain.pos_lines('かな', tok, pos_hint='名詞:一般',
                            atomic_hint=False, known_hint=True),
          ['か ＝ 助詞（副助詞）', 'な ＝ 助詞（終助詞）'])
    check('読みが立たない塊（known でない）も鎖のまま',
          explain.pos_lines('かな', tok, pos_hint='名詞:一般',
                            atomic_hint=True, known_hint=False),
          ['か ＝ 助詞（副助詞）', 'な ＝ 助詞（終助詞）'])
    # **原形は janome の道でしか取れない**——`_tokens_for` の代わりの道
    # （`tokenize_fn`）は原形を持たないので、ここ（janome 無し）では
    # 原形の付かない形が正しい。原形そのものの言い方は `pos_name` で、
    # 借りる条件は下の見張りで確かめる。
    check('janome 無しの道では原形が取れない（付けずに言い切る）',
          explain.pos_lines('押し', tok, pos_hint='動詞:自立',
                            infl_hint='連用形',
                            atomic_hint=True, known_hint=True),
          ['動詞・連用形'])
    check('原形の言い方（活用して形が変わっているときだけ添える）',
          (explain.pos_name('動詞:自立', '押し', '連用形', '押す'),
           explain.pos_name('動詞:自立', '押す', '基本形', '押す')),
          ('動詞・連用形／原形 押す', '動詞・終止形'))
    check('大分類が食い違うなら原形は添えない（行では名詞の 押し）',
          explain.pos_lines('押し', tok, pos_hint='名詞:一般',
                            atomic_hint=True, known_hint=True),
          ['名詞'])
    esrc = open('explain.py', encoding='utf-8').read()
    check('原形を借りるのは「1語に割れて大分類が一致」のときだけ',
          ('_one = _tokens_for(text, tokenize_fn)' in esrc
           and '== _major_and_sub(pos_hint)[0]):' in esrc), True)

    print('--- 項目48-QD（当て推量の札を名乗らせない） ---')
    check('ナイ形容詞語幹 は「イ形容詞の語幹」ではない（問題・間違い）',
          explain.pos_name('名詞:ナイ形容詞語幹', '問題'),
          '名詞（「ない」に続く）')
    check('読みの立たない英字を「組織名」と呼ばない（the・Ctrl・https）',
          explain.pos_name('名詞:固有名詞:組織', 'Ctrl', has_reading=False),
          '英字（解析は品詞を言えない）')
    check('読みが立つ英字は今までどおり',
          explain.pos_name('名詞:一般', 'PC', has_reading=True), '名詞')
    check('記号だけの並びは記号（`://` を 名詞（サ変）と言わない）',
          explain.pos_name('名詞:サ変接続', '://', has_reading=False), '記号')
    check('数字に「辞書に無い語」とは書かない',
          explain.pos_name('名詞:数', '30', has_reading=False), '数詞')
    check('接尾辞は下の段まで言う（助数詞・ナ形容詞を作る）',
          (explain.pos_name('名詞:接尾:助数詞', '本'),
           explain.pos_name('名詞:接尾:形容動詞語幹', '的'),
           explain.pos_name('名詞:接尾:一般', '書')),
          ('接尾辞（助数詞）', '接尾辞（ナ形容詞を作る）', '接尾辞'))

    print('--- 項目48-QE（1拍の内側で切れた割り方からは品詞を言わない） ---')
    def tok2(text):
        """janome が実際にこう割っていたもの（画面に出ていた形）。"""
        table = {
            'しゅるい': [('し', '動詞:自立', 'シ', 0, 1, True, '連用形'),
                         ('ゅるい', '名詞:一般', '', 1, 4, False, '')],
            '外しょつする': [('外し', '動詞:自立', 'ハズシ', 0, 2, True, '連用形'),
                             ('ょつ', '名詞:一般', '', 2, 4, False, ''),
                             ('する', '動詞:自立', 'スル', 4, 6, True, '基本形')],
        }
        return table.get(text, [(text, '名詞:一般', text, 0, len(text),
                                 True, '')])

    # **文言の先頭で見る**（項目48-RG）——隣の字を渡すと後ろに
    # 「。前の『…』とひとつづきのかな連続」が付くので、完全一致に
    # すると事実を添えた瞬間に落ちる
    check('しゅるい は「し ＝ 動詞」と言わない',
          [x.startswith('判定できません（`しゅ` は1拍——語の途中で切れています')
           for x in explain.pos_lines('しゅるい', tok2, prev_text='かん')],
          [True])
    check('隣を渡さなければ、今までと同じ文言のまま',
          explain.pos_lines('しゅるい', tok2),
          ['判定できません（`しゅ` は1拍——語の途中で切れています）'])

    # ------------------------------------------------------------
    # 48-RG **「判定できません」だけで終わらせず、言える事実を添える**
    # ------------------------------------------------------------
    # うにさんの指定（2026-09-05）「**判定できないなら、できる範囲で
    # 判定するべきです**」。48-QE の「壊れた割り方から品詞を言わない」は
    # 正しいので動かさない。**品詞は言わずに、見れば分かる事実を足す。**
    check('前がかなで続いていれば、そう言う',
          explain.pos_lines('しゅるい', tok2, prev_text='かん'),
          ['判定できません（`しゅ` は1拍——語の途中で切れています。'
           '前の「かん」とひとつづきのかな連続）'])
    check('両隣がかなで続いていれば、両方言う',
          explain.pos_lines('しゅるい', tok2, prev_text='かん',
                            next_text='で'),
          ['判定できません（`しゅ` は1拍——語の途中で切れています。'
           '前の「かん」・後ろの「で」とひとつづきのかな連続）'])
    check('**かなで繋がらない隣は言わない**（漢字の隣）',
          explain.pos_lines('しゅるい', tok2, prev_text='漢字'),
          ['判定できません（`しゅ` は1拍——語の途中で切れています）'])
    check('**品詞は言わない**（言えないから）',
          any('動詞' in x or '名詞' in x
              for x in explain.pos_lines('しゅるい', tok2,
                                         prev_text='かん')),
          False)
    check('判定が付く語には何も足さない',
          explain.pos_lines('かな', tok, pos_hint='名詞:一般',
                            prev_text='かん', next_text='で'),
          explain.pos_lines('かな', tok, pos_hint='名詞:一般'))
    check('漢字を含むときは、割れた2語ぶんだけ言い直す（する は残す）',
          explain.pos_lines('外しょつする', tok2),
          ['外しょつ ＝ 判定できません（`しょ` は1拍——語の途中で切れています）',
           'する ＝ 動詞・終止形'])
    check('促音は1拍の組に入れない（`っけ`・`って` は語）',
          (explain._mora_cut([('でし',), ('た',)]),
           explain._mora_cut([('往っ',), ('て',)]),
           explain._mora_cut([('きゃー',), ('っ',)])),
          (None, None, None))
    check('`ヶ`・`ヵ` も入れない（`ヶ月` は接尾辞）',
          explain._mora_cut([('1',), ('ヶ月',)]), None)
    check('拍を作らない小書き（とぉ・たぁ）は触らない',
          (explain._mora_cut([('ちょっと',), ('ぉ',)]),
           explain._mora_cut([('あいた',), ('ぁ',)])),
          (None, None))
    check('カタカナでも1拍は1拍（シュ）',
          explain._mora_cut([('シ',), ('ュー',)]), (1, 'シュ'))
    check('成り立たない割り方に「つながりが異様」は付けない',
          any('つながりが異様' in x
              for x in explain.pos_lines('しゅるい', tok2)),
          False)

    print('--- 学び22（単位を作る道は2本ある。両方が品詞を運ぶこと） ---')
    src = open('units.py', encoding='utf-8').read()
    check('前処理の前の姿を、両方の道で控えている',
          src.count('_raw_spans = {(_t[3], _t[4], _t[0]) for _t in tokens}'),
          2)
    check('まとめた単位は3か所とも atomic を落とす',
          src.count("head['atomic'] = False"), 3)
    check('build_line_units の emit も品詞を運ぶ',
          ("def emit(shown, base, reading, kind, detail, prev, next_,\n"
           "             pos='', infl='', atomic=False, known=False):") in src,
          True)
    return all_ok


def test_privacy_no_counts_48qg_48qh_48qj():
    """
    ★★ **回数と履歴を記録していないことの見張り**
    （項目48-QG/QH/QJ/QL/QM・2026-09-05）。

    うにさんの指定:

        「変換の根拠に、履歴が影響した、履歴に何回あったという表示が
          ありました。**履歴として記録されることをユーザは望みません。**
          人に見られたくないデータが保存されている。
          **この回数を記録する仕組みを削除します。**
          代わりに同音異義語の一覧表を作成し、最後にどの変換をしたか、
          それぞれ履歴1回分記録します。
          同音異義語ではない単語の回数は残しません」

    見るのは**出来上がったファイルと画面の言葉**——実装の形ではなく、
    **外へ出るもの**を測る（次の人が中を作り直しても、この見張りは
    そのまま効く）。
    """
    import io as _io
    import json as _json
    import os as _os
    import tempfile as _tempfile

    print('--- 項目48-QG/QH/QJ（回数と履歴を記録しない） ---')
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    from vocabulary import VocabularyStore, entry_is_solid

    tmp = _tempfile.mkdtemp()
    vpath = _os.path.join(tmp, 'vocabulary.json')

    # --- (1) 保存した語彙に count / last_seen が無い ---
    st = VocabularyStore(vpath)
    st.add('たんご', '単語', 'その他')
    st.add('たんご', '単語', 'その他')            # 2度目＝立つ
    st.add('もじ', '文字', 'その他')              # 1度だけ＝立たない
    st.add('えいご', 'English', '英語', world=5)
    st.save()
    with open(vpath, encoding='utf-8') as f:
        raw = f.read()
        data = _json.loads(raw)
    check('保存した語彙に count が無い', 'count' in raw, False)
    check('保存した語彙に last_seen が無い', 'last_seen' in raw, False)
    check('持つ鍵は reading/surface/category/solid/world だけ',
          sorted({k for e in data for k in e}),
          ['category', 'reading', 'solid', 'surface', 'world'])
    check('2度書いた語は立つ',
          [e['solid'] for e in data if e['surface'] == '単語'], [True])
    check('1度だけの語は立たない',
          [e['solid'] for e in data if e['surface'] == '文字'], [False])

    # --- (1') ★★ **メモリ上の `count` は 1 か 2 しか取らない** ---
    # 巡1 の足場（`solid` の写し）が写しのままであることの見張り。
    # ここが崩れると、約60か所の `count >= 2` の門が「回数の門」に
    # 戻ってしまう（＝うにさんの指定に反する記録が復活する）。
    # **新しく回数を数えるコードを書いたら、ここで落ちる。**
    for _ in range(50):
        st.add('たんご', '単語', 'その他')
        st.add('もじ', '文字', 'その他')
    check('メモリ上の count は 1 か 2 しか取らない',
          sorted({e.get('count') for e in st.to_list()}), [1, 2])
    check('count は solid の写し（食い違わない）',
          all((e.get('count') == 2) == bool(e.get('solid'))
              for e in st.to_list()), True)

    # --- (2) 読み直しても同じ／立った語は何度足しても変わらない ---
    st2 = VocabularyStore(vpath)
    check('読み直しても立ち方が同じ',
          (entry_is_solid(st2.lookup('たんご')[0]),
           entry_is_solid(st2.lookup('もじ')[0])), (True, False))
    _rev = st2.revision()
    st2.add('たんご', '単語', 'その他')
    st2.add('たんご', '単語', 'その他')
    check('立った語をもう一度書いても何も変わらない',
          st2.revision(), _rev)

    # --- (3) 旧形式（count・last_seen 付き）は読みながら潰れる ---
    old = [
        {'reading': 'かんしん', 'surface': '関心', 'category': 'その他',
         'count': 37, 'last_seen': 1788000000.0},
        {'reading': 'かんしん', 'surface': '感心', 'category': 'その他',
         'count': 1, 'last_seen': 1788000001.0},
    ]
    opath = _os.path.join(tmp, 'old_vocabulary.json')
    with open(opath, 'w', encoding='utf-8') as f:
        _json.dump(old, f, ensure_ascii=False)
    st3 = VocabularyStore(opath)
    check('旧形式を読んだら印が立つ（移行の合図）',
          st3.legacy_on_disk, True)
    check('count>=2 だった語だけが立つ',
          {e['surface']: entry_is_solid(e) for e in st3.lookup('かんしん')},
          {'関心': True, '感心': False})
    st3.save()
    with open(opath, encoding='utf-8') as f:
        raw3 = f.read()
    check('保存し直すとファイルからも回数が消える',
          ('count' in raw3 or 'last_seen' in raw3), False)
    check('消したあとは移行の合図が下りる', st3.legacy_on_disk, False)

    # --- (4) 補正根拠の3行目に「回」が出ない（項目48-QJ） ---
    import explain as _EX
    import last_choice as _LC
    lc = _LC.LastChoiceStore()
    lc.bind(st2, None)
    lc.remember('たんご', '単語', 'たんご')
    got = _EX.learn_reason('たんこ', '単語',
                           {'base': 'たんご', 'reading': 'たんご'},
                           lc, st2)
    check('枠で決まったら、そう書く（回数は書かない）',
          got, '学習による選び直し')
    check('補正根拠に「回」が出ない', '回' in (got or ''), False)
    check('SEED_COUNT_MAX は撤去した',
          hasattr(_EX, 'SEED_COUNT_MAX'), False)

    # --- (4') **枠は答えを変えるので、控えの見分けに入っていること**
    # （項目48-QH。`charngram`＝48-BN・`ime_readings`＝48-HA と同じ罠。
    #   掛け忘れは毎回、実機で化けてから見つかっている）
    import analysis_cache as _AC
    from last_choice import LastChoiceStore
    st4 = VocabularyStore()
    for _s in ('公園', '講演'):
        st4.add('こうえん', _s, 'その他')
        st4.add('こうえん', _s, 'その他')
    lc4 = LastChoiceStore()
    lc4.bind(st4, None)

    def _fp():
        return _AC.build_fingerprint(tmp, '1.0.0', 'kana', (),
                                     store=st4, choices=lc4)['choices']
    _before = _fp()
    lc4.remember('こうえん', '講演', 'こうえん')
    check('枠を入れると控えの見分けが変わる', _before != _fp(), True)
    lc5 = LastChoiceStore()
    lc5.bind(st4, None)
    lc5.remember('こうえん', '講演', 'こうえん')
    check('同じ中身なら同じ見分け',
          _fp(), _AC.build_fingerprint(tmp, '1.0.0', 'kana', (),
                                       store=st4, choices=lc5)['choices'])

    # --- (5) 旧 choices.json を1枠へ畳んで消す（項目48-QI） ---
    from last_choice import migrate_from_choices
    cpath = _os.path.join(tmp, 'choices.json')
    lpath = _os.path.join(tmp, 'last_choice.json')
    with open(cpath, 'w', encoding='utf-8') as f:
        _json.dump([
            {'original': 'こうえん', 'chosen': '公園', 'reading': 'こうえん',
             'prev': 'あしたの', 'next': 'に', 'count': 3,
             'updated': 100.0},
            {'original': 'こうえん', 'chosen': '講演', 'reading': 'こうえん',
             'prev': 'だいがくで', 'next': 'を', 'count': 9,
             'updated': 200.0},
        ], f, ensure_ascii=False)
    n, r = migrate_from_choices(cpath, lpath, store=st2)
    check('元の choices.json は消える', _os.path.exists(cpath), False)
    check('語ごとに1件だけ残る', n, 1)
    lc2 = LastChoiceStore(lpath)
    check('残るのはいちばん新しい選択',
          lc2.lookup('こうえん'), '講演')

    # ★ **読みの枠も、いちばん新しい選択が取る**（項目48-QI）。
    # 旧 `choices.json` は `updated` の**降順**に並んでいるので、
    # そのまま流し込むと**いちばん古い選択が読みの枠を取る**
    # （読みの枠は1つしか無く、あとに入れたほうが勝つため）。
    st6 = VocabularyStore()
    for _s in ('公園', '講演', '後援'):
        st6.add('こうえん', _s, 'その他')
        st6.add('こうえん', _s, 'その他')
    cpath2 = _os.path.join(tmp, 'choices2.json')
    lpath2 = _os.path.join(tmp, 'last_choice2.json')
    with open(cpath2, 'w', encoding='utf-8') as f:
        _json.dump([
            {'original': 'こうえn', 'chosen': '公園', 'reading': 'こうえん',
             'prev': '', 'next': '', 'count': 1, 'updated': 200.0},
            {'original': 'こうえん', 'chosen': '講演', 'reading': 'こうえん',
             'prev': '', 'next': '', 'count': 1, 'updated': 100.0},
        ], f, ensure_ascii=False)
    migrate_from_choices(cpath2, lpath2, store=st6)
    check('読みの枠は、いちばん新しい選択が取る',
          LastChoiceStore(lpath2).surface_for_reading('こうえん'), '公園')
    with open(lpath, encoding='utf-8') as f:
        rawl = f.read()
    check('畳んだ先に回数・時刻・前後の文が無い',
          any(k in rawl for k in ('count', 'updated', 'prev', 'next')),
          False)

    # --- (6) 育ちのデータは、学習の口ごと止まっている（項目48-QL） ---
    src = open('app.py', encoding='utf-8').read()
    i = src.find('def _learn_context_vec_now')
    check('文脈ベクトルは覚えない（口はある・中で返す）',
          'return' in src[i:i + 1400] and 'observe_line' not in src[i:i + 1400],
          True)
    j = src.find('def _learn_charngram')
    check('字の並びも覚えない',
          'charngram.learn' not in src[j:j + 900], True)
    check('起動時に育ちのファイルを消す',
          "os.remove(_grown)" in src, True)

    # --- (7) 打鍵の記録は、本文に残っている語だけ（項目48-QM） ---
    from ime_readings import IMEReadings
    ir = IMEReadings(_os.path.join(tmp, 'ime.json'))
    ir.remember('奥悠久子帝', 'おくゆうきこてい')
    ir.remember('文字入力', 'もじにゅうりょく')
    dropped = ir.keep_only_in(['きょうは文字入力の練習をした'])
    check('本文に無い対は落ちる', dropped, 1)
    check('本文に在る対は残る',
          (ir.readings_for('文字入力'), ir.readings_for('奥悠久子帝')),
          (['もじにゅうりょく'], []))
    check('本文が1つも取れないときは何もしない（読み込みの途中）',
          ir.keep_only_in([]), 0)
    # **本文が本当に空なら、打鍵の記録も残さない**（うにさんの指定
    # 「アプリの文字が消えれば打ったキー情報も消えます」そのもの）。
    check('中身の無い紙が渡されたら全部落とす',
          ir.keep_only_in(['', '']), 1)
    check('落としたあとは空', len(ir), 0)

    # ------------------------------------------------------------
    # 48-QU **紫を下げる台帳と、補正を止める台帳を分ける**
    # ------------------------------------------------------------
    # 紫の右クリックの「この文字列は正しい」に食わせるのは、
    # **日本語として真っ当な短い並び**（紫の範囲は形態素の連なりで、
    # 2字がふつうに出る）。`decisions.blocks()` は**部分一致**で
    # 止めるので、そこへ入れると**それを含む行の補正が全部止まる**。
    from decisions import DecisionStore
    d = DecisionStore()
    check('短すぎる（1字）ものは受け付けない', d.leave_odd_alone('あ'), False)
    check('紫を下げる台帳に入る', d.leave_odd_alone('本語'), True)
    check('同じものは二度入らない', d.leave_odd_alone('本語'), False)
    # ★★ ここが 48-QU の要点
    check('補正は止めない（部分一致で巻き添えにしない）',
          d.blocks('本語がある', '日本語がある'), False)
    check('補正を止める台帳には入っていない',
          [e['word'] for e in d.protected_list()], [])
    check('紫を下げる口には出る', sorted(d.left_alone_texts()), ['本語'])
    check('一覧に出る', [e['word'] for e in d.odd_only_list()], ['本語'])
    # 取り消し口は1つのまま（学習メニューは `unprotect` だけを呼ぶ）
    check('取り消せる', d.unprotect('本語'), True)
    check('取り消したら紫が戻る', sorted(d.left_alone_texts()), [])
    # `protect`（補正も止める）のほうは、今までどおり部分一致で止める
    check('protect は今までどおり止める',
          (d.protect('縦シュー'), d.blocks('縦シューが', 'なにか')),
          (True, True))
    # 保存と読み込みで、台帳の区別が残ること
    _dp = _os.path.join(tmp, 'dec.json')
    d.leave_odd_alone('本語')
    d.save(_dp)
    d2 = DecisionStore(_dp)
    check('読み直しても台帳の区別が残る',
          (sorted(e['word'] for e in d2.protected_list()),
           sorted(e['word'] for e in d2.odd_only_list()),
           d2.blocks('本語がある', '日本語がある'),
           d2.blocks('縦シューが', 'なにか')),
          (['縦シュー'], ['本語'], False, True))

    return all_ok


def test_quick_autofix_undo_48vd():
    """
    ★★ **簡易入力の自動補正を取り消せること**（項目48-VD・
    うにさんの報告・2026-09-07「簡易入力で自動補正された場合、
    それを取り消す手段がない」）。

    見るのは2つ。

      **(a) 並びを書く場所が1つ**（48-GN）——メモ欄と簡易入力の
      どちらの一覧も `_autofix_menu_items` を呼ぶこと。片方だけを
      直したときに、ここで止まる。

      **(b) 台帳を渡す道が揃っている**（学び22）——`correct_line`
      を呼ぶところは**全部** `decisions=` を渡すこと。渡していない
      道が1本でも在ると、そこでは「この補正は不要」が効かず、
      元へ戻しても次の解析でまた直る（今回の不具合そのもの）。

    実機（Tk）は要らない。**文字と AST だけ**で測る。
    振る舞いは `tools_local/probe_quick_undo.py` と
    `tools_local/probe_autofix_menu_pair.py`。
    """
    import ast as _ast
    import io as _io

    print('--- 項目48-VD（簡易入力の自動補正を取り消す） ---')
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    src = _io.open('app.py', encoding='utf-8').read()
    tree = _ast.parse(src)
    funcs = {}
    for node in _ast.walk(tree):
        if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            funcs[node.name] = node

    def calls_in(name, callee):
        fn = funcs.get(name)
        if fn is None:
            return None
        return any(isinstance(x, _ast.Call)
                   and isinstance(x.func, _ast.Attribute)
                   and x.func.attr == callee
                   for x in _ast.walk(fn))

    def body(name):
        i = src.index('def %s(' % name)
        j = src.index(chr(10) + '    def ', i + 1)
        return src[i:j]

    # ---- (a) 並びは1か所 ------------------------------------
    check('48-VD 並びを組み立てる口が在る',
          '_autofix_menu_items' in funcs, True)
    for _name in ('_editor_dropdown_items', '_open_quick_dropdown'):
        check(f'48-VD {_name} が同じ口を呼ぶ（48-GN）',
              calls_in(_name, '_autofix_menu_items'), True)
    # ラベルは自動補正の口にしか無い（欄ごとに書き分けていない）。
    # ※ 分割表示の**補正欄**は別の仕掛け（`unit['detail']` から
    #   `_reject_correction` を呼ぶ。メモ欄には原文が残っている
    #   ので戻す物が無い）。そちらは数えない。
    _mi = body('_autofix_menu_items')
    _ed = body('_editor_dropdown_items')
    _qd = body('_open_quick_dropdown')
    for _lab in ('― 自動補正 ―', 'この補正は不要（',
                 'は今後直さない', '元の入力に戻す（'):
        check(f'48-VD ラベル {_lab!r} は自動補正の口だけが持つ',
              (_lab in _mi, _lab in _ed, _lab in _qd),
              (True, False, False))

    # ---- (b) 台帳は全部の道へ（学び22） ----------------------
    _calls = [x for x in _ast.walk(tree)
              if isinstance(x, _ast.Call)
              and ((isinstance(x.func, _ast.Name)
                    and x.func.id == 'correct_line')
                   or (isinstance(x.func, _ast.Attribute)
                       and x.func.attr == 'correct_line'))]
    _no_dec = [x.lineno for x in _calls
               if not any(k.arg == 'decisions' for k in x.keywords)]
    check('48-VD correct_line を呼ぶ道は全部 decisions を渡す',
          _no_dec, [])
    # 数え漏れの見張り: いま在るのは4本（起動時の下見・簡易入力・
    # メモ欄の解析・貼り付けの下見）。**減ったら気づく**。
    check('48-VD correct_line を呼ぶ道が減っていない',
          len(_calls) >= 4, True)

    # ---- 控えの名簿は面ごとに分かれている ---------------------
    check('48-VD 面を決める口が在る（_autofix_pane）',
          '_autofix_pane' in funcs and '_autofix_pane_of' in funcs,
          True)
    _pane = body('_autofix_pane')
    check('48-VD 面の口は**属性名**を返す（_autofix_reset が差し替える）',
          "'_autofix_records'" in _pane
          and "'_quick_autofix_records'" in _pane, True)
    check('48-VD 簡易入力の名簿は別に持つ（保存する原文に混ぜない）',
          'self._quick_autofix_records = []' in src, True)
    check('48-VD 保存の原文はメモ欄の名簿だけを読む',
          '_autofix_live_records()' in body('editor_source_text'), True)

    # ---- 設計33 はメモ欄だけ ---------------------------------
    _reset = body('_autofix_reset')
    check('48-VD 設計33 の確定はメモ欄のときだけ（面で括る）',
          '_design33_flush' in _reset
          and "if key == '_autofix_records':" in _reset, True)

    # ---- 窓の一生 ---------------------------------------------
    _qc = body('_close_quick_capture')
    check('48-VD 閉じるときの片付けは **destroy の前**（48-TW と同じ）',
          '_autofix_reset' in _qc
          and _qc.index('_autofix_reset') < _qc.index('win.destroy()'),
          True)
    check('48-VD 窓を建てる／掴み直す両方で控えを空にする',
          body('_open_quick_capture').count(
              'self._quick_autofix_records = []'), 2)

    # ---- 自動反映が控えを作り、色は塗り直す -------------------
    _apply = body('_apply_quick_autofix')
    check('48-VD 簡易入力の自動反映が控えを作る',
          '_autofix_remember' in _apply, True)
    check('48-VD 「元の入力に戻す」を使った行は上書きしない',
          "if rec is not None and rec['manual']:" in _apply, True)
    check('48-VD 2周目に original を書き換えない（原文の化けを防ぐ）',
          "rec['original']" in _apply, False)
    check('48-VD 色は控えから塗り直す（付けっぱなしにしない）',
          '_repaint_autofix_tags(w=text_widget)' in _apply
          and "text_widget.tag_add(" not in _apply, True)

    # ---- Ctrl+Z も同じ道 --------------------------------------
    check('48-VD 簡易入力の Ctrl+Z を束ねている',
          "text.bind('<Control-z>', self._on_quick_ctrl_z)" in src,
          True)
    check('48-VD Ctrl+Z は _undo_autofix を通る（Tk の取り消しではない）',
          calls_in('_on_quick_ctrl_z', '_undo_autofix'), True)
    check('48-VD 控えが無ければ素通し（ふつうの取り消しを殺さない）',
          'return None' in body('_on_quick_ctrl_z'), True)

    # ---- 判断を書いたら簡易入力も塗り直す ----------------------
    check('48-VD 台帳を書いたら簡易入力も解析し直す（学び22）',
          calls_in('_after_decision', '_analyze_quick'), True)

    return all_ok


def run_review_regressions_48vi_vm():
    """保存の故障・表示行の往復・重複オフを、実際の処理で確かめる。"""
    import ast
    import os
    import tempfile
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import patch
    from session import SessionStore, new_tab
    import loanword
    from vocabulary import VocabularyStore
    from seed_vocabulary import load_seed

    all_ok = True
    def check(label, got, want):
        nonlocal all_ok
        ok = got == want
        all_ok = all_ok and ok
        print(('OK ' if ok else 'NG ') + label)
        if not ok:
            print('    got:', repr(got), 'want:', repr(want))

    tree = ast.parse(Path('app.py').read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name == 'CorrectNoteApp')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef)
                  and n.name == '_write_to_file')
    namespace = {'os': os}
    exec(compile(ast.Module(body=[method], type_ignores=[]), 'app.py', 'exec'), namespace)
    save = namespace['_write_to_file']
    with tempfile.TemporaryDirectory() as directory:
        dest = Path(directory) / 'memo.txt'
        original = b'original document'
        def editor(text='new document'):
            return SimpleNamespace(editor_source_text=lambda: text, _dirty=True,
                                   current_file='old-path', _refresh_title=lambda: None,
                                   status=SimpleNamespace(config=lambda **kw: None),
                                   _save_session=lambda: None)
        real_fdopen = os.fdopen
        class FailingStream:
            def __init__(self, fd, *args, **kwargs):
                self.stream = real_fdopen(fd, *args, **kwargs)
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.stream.close()
                if stage == 'close':
                    raise OSError('simulated close failure')
            def __getattr__(self, key):
                return getattr(self.stream, key)
            def write(self, text):
                if stage == 'write':
                    self.stream.write(text[:3])
                    raise OSError('simulated disk full')
                return self.stream.write(text)
            def flush(self):
                if stage == 'flush':
                    raise OSError('simulated flush failure')
                return self.stream.flush()

        for stage in ('write', 'flush', 'close', 'replace', 'encoding'):
            dest.write_bytes(original)
            fake = editor('new\ud800text' if stage == 'encoding' else 'new document')
            with patch('os.fdopen', FailingStream):
                if stage == 'replace':
                    with patch('os.replace', side_effect=OSError('simulated replace failure')):
                        ok = save(fake, str(dest))
                else:
                    ok = save(fake, str(dest))
            check('48-VJ ' + stage + ' failure keeps original',
                  (ok, dest.read_bytes(), fake._dirty, fake.current_file),
                  (False, original, True, 'old-path'))
            check('48-VJ ' + stage + ' cleans temporary file',
                  sorted(p.name for p in Path(directory).iterdir()), ['memo.txt'])
        fake = editor('new document\n')
        check('48-VJ successful overwrite', save(fake, str(dest)), True)
        check('48-VJ completed document and saved state',
              (dest.read_bytes(), fake._dirty), (b'new document', False))
        fresh = Path(directory) / 'new.txt'
        check('48-VJ first save', save(editor(), str(fresh)), True)

        state_path = str(Path(directory) / 'session.json')
        state = SessionStore(state_path)
        state.tabs = [new_tab(text='example', top=120, scroll=0.5)]
        state.save()
        restored = SessionStore(state_path)
        restored.load()
        check('48-VI top survives save/load', restored.current()['top'], 120)
        state.tabs[0].pop('top')
        state.save()
        restored.load()
        check('48-VI old session keeps scroll fallback',
              (restored.current()['top'], restored.current()['scroll']), (None, 0.5))

    store = VocabularyStore()
    load_seed(store)
    for enabled in (False, True):
        with patch.dict(os.environ, {'CN_NO_DUP': '0' if enabled else '1'}):
            for typed, restored in (('クリッック', 'クリック'), ('ファイイル', 'ファイル'),
                                    ('プラネタリウウム', 'プラネタリウム')):
                check('48-VL duplicate setting ' + str(enabled) + ' ' + typed,
                      loanword.fix_katakana_word(typed, store), restored if enabled else None)
    for enabled in (False, True):
        with patch.dict(os.environ, {'CN_NO_DUP': '0' if enabled else '1'}):
            for typed in ('keybooard', 'keyboarrd', 'keyboaard'):
                check('48-VL English duplicate setting ' + str(enabled) + ' ' + typed,
                      loanword.fix_english_word(typed, store), 'keyboard' if enabled else None)
            check('48-VL legitimate doubled letters survive',
                  loanword.fix_english_word('bookkeeper', store), None)
    return all_ok


def run_pos_context_48vo():
    """文脈の判定は同形語の反例と、位置・読みの保存まで見る。"""
    from morphology import Token, contextualize_tokens
    from unittest.mock import patch
    good = True

    def check(label, value):
        nonlocal good
        print('OK' if value else 'NG', '48-VO', label)
        good = good and bool(value)

    def token(word, pos, sub, start, reading='', known=True):
        return Token(word, pos, word, reading or word, start, start+len(word), known, sub)

    for next_word, next_pos, expected in (
            ('に', '助詞', '名詞'), ('だ', '助動詞', '名詞'),
            ('です', '助動詞', '名詞'), ('遠い', '形容詞', '助詞'),
            ('の', '助詞', '助詞'), ('による', '助詞', '助詞')):
        original = [token('東京','名詞','固有名詞:地域:一般',0),
                    token('より','助詞','格助詞:一般',2),
                    token(next_word,next_pos,'',4)]
        got = contextualize_tokens(original)
        check('より＋'+next_word, got[1].pos == expected)
        check('元の解析を汚さない', original[1].pos == '助詞')
    # 空白をまたいだ判断、読みを言えない未知語からの断定はしない。
    for known, start in ((False,4),(True,5)):
        original = [token('未知','名詞','一般',0,known=known),
                    token('より','助詞','格助詞:一般',2), token('に','助詞','格助詞',start)]
        check('未知語・空白で断定しない', contextualize_tokens(original)[1].pos == '助詞')
    with patch('seed_japanese.is_unit', side_effect=lambda w: w == '爪切り'):
        original = [token('電動','名詞','一般',0,'でんどう'),
                    token('爪','名詞','一般',2,'つめ'),
                    token('切り','名詞','接尾:一般',3,'きり')]
        got = contextualize_tokens(original)
        check('既知の複合名詞', [t.surface for t in got] == ['電動','爪切り'])
        check('範囲と読み', (got[1].start,got[1].end,got[1].reading) == (2,5,'つめきり'))
        original[2].pos = '動詞'
        check('連用形の動詞を名詞にしない', len(contextualize_tokens(original)) == 3)
        original[2].pos = '名詞'; original[1].pos_sub = '固有名詞:人名:姓'
        check('名前の分類を消さない', len(contextualize_tokens(original)) == 3)
    with patch('seed_japanese.is_unit', return_value=True):
        for head, tail in (('銅','色'), ('かく','ら')):
            original = [token(head,'名詞','一般',0),
                        token(tail,'名詞','接尾:一般',len(head))]
            check('名詞化でない接尾辞をまとめない '+head+tail,
                  len(contextualize_tokens(original)) == 2)
    original = [token('十','名詞','数',0,'じゅう'), token('六','名詞','数',1,'ろく'),
                token('茶','名詞','一般',2,'ちゃ')]
    got = contextualize_tokens(original)
    check('連続した数詞の単位', [(t.surface,t.pos_sub) for t in got] == [('十六','数'),('茶','一般')])
    check('数の読みも維持', got[0].reading == 'じゅうろく' and got[0].end == 2)
    original[1].start=2; original[1].end=3
    check('別欄の数を結ばない', contextualize_tokens(original)[0].surface == '十')
    return good


def run_drag_edges_48vp():
    """実カーソルを動かさず、モニター座標と連続ドラッグを再現する。"""
    import ast
    import types
    from pathlib import Path
    from unittest.mock import patch
    import ctypes
    tree = ast.parse(Path(__file__).with_name('app.py').read_text(encoding='utf-8'))
    wanted = {'_edge_warp', '_drag_motion', '_warp_pointer'}
    methods = [n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name in wanted]
    env = {'sys': types.SimpleNamespace(platform='win32')}
    exec(compile(ast.Module(body=methods, type_ignores=[]), 'app.py', 'exec'), env)

    class Pane:
        def winfo_pointerx(self): return self.left + 100
        def winfo_pointery(self): return self.py
        def winfo_rootx(self): return self.left
        def winfo_rooty(self): return self.top
        def winfo_height(self): return self.height
        def winfo_width(self): return 900
        def winfo_screenheight(self): return 1440
        def event_generate(self, *args, **kwargs): self.fallback = True

    class Drag:
        DRAG_WARP_EDGE = 64
        DRAG_WARP_TOLERANCE = 60
        DRAG_WARP_SKIP_MAX = 8
        _overview = None
        _edge_warp = env['_edge_warp']
        _drag_motion = env['_drag_motion']
        def _warp_pointer(self, w, x, y):
            self.warps += 1
            w.py = w.top + y
            return 'sync'
        def _scroll_cursor_restore(self): self.restored = True
        def _get_line_height(self): return 20
        def _on_wheel_units(self, n): self.lines += n

    try:
        # 主画面／背の低い副画面／上に置いた副画面／下に置いた副画面／
        # 画面外にはみ出す欄／小さい欄。それぞれ上下へ20回、戻しを跨ぐ。
        cases = [((0, 0, 1920, 1400), 100, 1100),
                 ((1920, 0, 3840, 1040), 100, 900),
                 ((0, -1080, 1920, -40), -980, 900),
                 ((0, 1440, 1920, 2480), 1540, 900),
                 ((0, 0, 1920, 1040), -1200, 2100),
                 ((0, 0, 1920, 1040), 400, 100)]
        for area, top, height in cases:
            env['monitor_work_area'] = lambda x, y, a=area: a
            for direction in (-1, 1):
                w = Pane()
                w.left, w.top, w.height = area[0], top, height
                w.py = (max(top, area[1]) + min(top + height, area[3])) // 2
                a = Drag()
                a.warps = a.lines = 0
                a._drag = dict(widget=w, mode='scroll', start_x=100,
                               start_y=w.py-top, last_y=w.py-top, accum=0)
                expected = 0
                for _ in range(20):
                    previous = w.py
                    w.py = area[1] + 2 if direction < 0 else area[3] - 2
                    expected += w.py - previous
                    event = types.SimpleNamespace(x=100, y=w.py-top)
                    a._drag_motion(event, w)
                    assert a.warps == _ + 1, (area, top, direction, a.warps)
                    assert area[1]+64 < w.py < area[3]-64
                    # warp生成イベント／手を止めた報せではスクロールしない。
                    before = a.lines
                    a._drag_motion(event, w)
                    assert a.lines == before
                assert a.lines == -int(expected / 20), (a.lines, expected)
                assert not a._drag.get('no_warp')
        # API失敗を同期成功と誤認しない。Tkの代替経路も確認する。
        w = Pane()
        w.left = w.top = 0
        for result, expected in ((1, 'sync'), (0, 'async')):
            native = types.SimpleNamespace(user32=types.SimpleNamespace(
                SetCursorPos=lambda x, y, r=result: r))
            with patch.object(ctypes, 'windll', native, create=True):
                assert env['_warp_pointer'](None, w, 20, 30) == expected
        # 取得できない環境では従来の画面サイズを使える。
        env['monitor_work_area'] = lambda x, y: None
        w.height, w.py = 1300, 1438
        a._edge_warp({}, w, types.SimpleNamespace(x=100))
        assert 64 < w.py < 1375
    except Exception as exc:
        print('NG 48-VP 右ドラッグ:', repr(exc))
        return False
    print('OK 48-VP: 6配置×上下×20回、静止、API失敗、取得失敗')
    return True


def run_passive_48vq():
    """Janomeなしでも活用情報のある列を入口で検証する。"""
    def tokens(parts):
        out, start = [], 0
        for surface, pos, infl in parts:
            out.append((surface, pos, surface, start, start+len(surface), True, infl))
            start += len(surface)
        return out
    a = ('示さ', '動詞:自立', '未然形')
    b = ('れる', '動詞:接尾', '基本形')
    cases = [([a,b], True),
             ([('書か','動詞:自立','未然形'),
               ('せ','動詞:接尾','未然形'),('られる','動詞:接尾','基本形')], True),
             ([('示す','動詞:自立','基本形'),b], False),
             ([('示し','動詞:自立','連用形'),b], False),
             ([('示さ','名詞:一般',''),b], False),
             ([a,b,('ない','助動詞','基本形')], False),
             ([a,b,('ます','助動詞','基本形')], False),
             ([a,b,('られる','動詞:接尾','基本形')], False)]
    ok = True
    for parts, expected in cases:
        text = ''.join(p[0] for p in parts)
        ts = tokens(parts)
        got = C._chunk_is_intact(text, lambda _: ts)
        good = got == expected
        ok = ok and good
        print(('OK' if good else 'NG'), '48-VQ', text, got)
    # 読み・活用の証拠が欠ける解析は、同じ表記でも決めつけない。
    ts = tokens([a,b])
    for damaged in ([ts[0][:5]+(False,ts[0][6]),ts[1]],
                    [ts[0][:6],ts[1][:6]]):
        good = not C._chunk_is_intact('示される', lambda _: damaged)
        ok = ok and good
        print(('OK' if good else 'NG'), '48-VQ 情報不足を完成形にしない')
    from morphology import Token, contextualize_tokens
    for head, reading, base, gap, expected in (
            ('読ま','よま','読む',0,'接尾'), ('待た','また','待つ',0,'接尾'),
            ('飲ま','のま','飲む',0,'接尾'), ('話さ','はなさ','話す',0,'自立'),
            ('食べ','たべ','食べる',0,'自立'), ('見','み','見る',0,'自立'),
            ('読ま','よま','読む',1,'自立')):
        end = len(head)
        ts = [Token(head,'動詞',base,reading,0,end,True,'自立','未然形'),
              Token('さ','動詞','する','さ',end+gap,end+gap+1,True,'自立','未然レル接続'),
              Token('れる','動詞','れる','れる',end+gap+1,end+gap+3,True,'接尾','基本形')]
        result = contextualize_tokens(ts)
        good = result[1].pos_sub == expected and [(t.surface,t.start,t.end) for t in result] == [(t.surface,t.start,t.end) for t in ts]
        ok = ok and good
        print(('OK' if good else 'NG'), '48-VQ 使役受身の文脈',head,gap)
    return ok


def run_structured_words_48vr():
    from unittest.mock import patch
    import halfwidth as H
    import seed_japanese
    def pair(a, ap, ar, b, bp, br):
        return [(a,ap,ar,0,len(a),True,''),
                (b,bp,br,len(a),len(a+b),True,'')]
    cases = [
        ('規則','名詞:一般','きそく','性','名詞:接尾:一般','せい',True),
        ('規則','名詞:一般','きそく','的','名詞:接尾:形容動詞語幹','てき',True),
        ('小売り','名詞:サ変接続','こうり','坂','名詞:接尾:一般','ざか',False),
        ('囚虜','名詞:一般','しゅうりょ','時','名詞:接尾:副詞可能','じ',False),
        ('規則','名詞:固有名詞:人名','きそく','性','名詞:接尾:一般','せい',False),
        ('規則','名詞:一般','きそく','性','名詞:接尾:一般','しょう',False)]
    ok=True
    for *args, expected in cases:
        ts=pair(*args); text=args[0]+args[3]
        # 語幹だけを辞書語にする。完成形の辞書保護と取り違えない。
        with patch.object(seed_japanese,'is_unit',side_effect=lambda w: w==args[0]):
            got=C._chunk_is_intact(text,lambda _:ts)
        good=got==expected;ok=ok and good
        print(('OK' if good else 'NG'),'48-VR 派生語',text,got)
    # ローカル辞書に依らず、既知語と打鍵の断片を区別する形を確認。
    with patch.object(H,'_is_dictionary_english',side_effect=lambda w:w.lower() in {'example','integer','unknown'}):
        for text, expected in (('name:example',False),('type:integer',False),
                               ('status:unknown',False),('(Example)',False),
                               ('md@i(4l)h',True),('md[ki)4l)h',True)):
            got=H.looks_like_halfwidth_input(text)
            good=got==expected;ok=ok and good
            print(('OK' if good else 'NG'),'48-VR 英字の構造',text,got)
    return ok


def run_contextual_predicate_48vs():
    from morphology import Token, contextualize_tokens
    ok = True
    for head, known, gap, tail, pos, sub, base, expected in (
        ('同じ', True, 0, 'だけ', '助詞', '副助詞', 'だけ', '名詞'),
        ('おなじ', True, 0, 'くらい', '助詞', '副助詞', 'くらい', '名詞'),
        ('同じ', True, 0, 'に', '助詞', '格助詞:一般', 'に', '名詞'),
        ('同じ', True, 0, 'な', '助動詞', '', 'だ', '名詞'),
        ('同じ', True, 0, 'です', '助動詞', '', 'です', '名詞'),
        ('同じ', True, 0, '本', '名詞', '一般', '本', '連体詞'),
        ('同じ', True, 0, 'よう', '名詞', '非自立:助動詞語幹', 'よう', '連体詞'),
        ('同じ', True, 1, 'だけ', '助詞', '副助詞', 'だけ', '連体詞'),
        ('同じ', False, 0, 'だけ', '助詞', '副助詞', 'だけ', '連体詞'),
        ('この', True, 0, 'だけ', '助詞', '副助詞', 'だけ', '連体詞'),
        ('大きな', True, 0, 'に', '助詞', '格助詞:一般', 'に', '連体詞')):
        start = len(head) + gap
        ts = [Token(head, '連体詞', head, head, 0, len(head), known),
              Token(tail, pos, base, tail, start, start+len(tail), True, sub)]
        got = contextualize_tokens(ts)
        good = (got[0].pos == expected and
                [(t.surface,t.start,t.end) for t in got] ==
                [(t.surface,t.start,t.end) for t in ts] and
                contextualize_tokens(got) == got)
        ok = ok and good
        print(('OK' if good else 'NG'), '48-VS 述語用法',head,tail,gap,known)
    return ok


def run_tab_scroll_48vt():
    from types import SimpleNamespace
    from app import CorrectNoteApp
    calls = []
    fake = SimpleNamespace(
        _syncing=False, _font_swap=False,
        result_gutter=SimpleNamespace(sync_yview=lambda *a: calls.append('result')),
        editor_gutter=SimpleNamespace(sync_yview=lambda *a: calls.append('editor')),
        v_scrollbar=SimpleNamespace(set=lambda *a: calls.append('bar')),
        editor=object(), result_view=object(),
        _update_header_visibility=lambda *a: calls.append('header'),
        _on_view_moved=lambda: calls.append('moved'),
        _sync_partner_to_line=lambda *a: calls.append('reverse'))
    CorrectNoteApp._on_result_scroll(fake, '0.0', '1.0')
    ok = calls == ['result']
    print(('OK' if ok else 'NG'), '48-VT 補正欄の再描画は入力欄を動かさない', calls)
    calls.clear(); fake._syncing=True
    CorrectNoteApp._on_result_scroll(fake, '0.0', '1.0')
    ok = ok and not calls
    return ok


def run_lexical_pos_48vu():
    from types import SimpleNamespace
    from unittest.mock import patch
    import morphology as M
    import pos_grammar as P
    ok = True

    def check(label, got, expected):
        nonlocal ok
        good = got == expected
        ok = ok and good
        print(('OK' if good else 'NG'), '48-VU', label, got)

    class Dictionary:
        def lookup(self, raw, matcher):
            assert M._TOKENIZE_LOCK.locked()
            if raw.decode('utf-8') == 'よい':
                return [(0, 'よ', 0, 0, 0), (1, 'よい', 0, 0, 0),
                        (2, 'よい', 0, 0, 0), (3, 'よい', 0, 0, 0)]
            if raw.decode('utf-8') == '読み':
                return [(4, '読み', 0, 0, 0)]
            return [(0, 'よ', 0, 0, 0)]  # 接頭部分の一致は完全一致ではない。

        def lookup_extra(self, key):
            assert M._TOKENIZE_LOCK.locked()
            return {1: ('名詞,一般,*,*', '*', '*', 'よい', '', ''),
                    2: ('動詞,自立,*,*', '*', '連用形', 'よう', '', ''),
                    3: ('形容詞,自立,*,*', '*', '基本形', 'よい', '', ''),
                    4: ('動詞,自立,*,*', '*', '連用形', '読む', '', '')}[key]

    M.dictionary_base_pos.cache_clear()
    try:
        with patch.object(M, 'HAS_JANOME', True), patch.object(
                M, '_TOKENIZER', SimpleNamespace(sys_dic=Dictionary(), matcher=object())):
            check('先頭候補だけでなく同形の形容詞も残す',
                  M.dictionary_base_pos('よい'), frozenset(('名詞,一般,*,*', '形容詞,自立,*,*')))
            check('連用形を基本形として扱わない', M.dictionary_base_pos('読み'), frozenset())
            check('部分一致しかない語は判定不能', M.dictionary_base_pos('よいもの'), None)
            check('空文字', M.dictionary_base_pos(''), None)
            with patch.object(Dictionary, 'lookup', side_effect=SystemExit(1)):
                check('辞書の終了例外でも継続する', M.dictionary_base_pos('失敗'), None)
        with patch.object(M, 'HAS_JANOME', False):
            check('辞書がない環境', M.dictionary_base_pos('未登録'), None)
    finally:
        M.dictionary_base_pos.cache_clear()

    # 同形のイ形容詞がある場合を落とさず、形容動詞の活用だけを区別する。
    kinds = {'きれい': frozenset(('名詞,形容動詞語幹,*,*',)),
             'あつい': frozenset(('名詞,形容動詞語幹,*,*','形容詞,自立,*,*')),
             '嫌い': frozenset(('名詞,形容動詞語幹,*,*',))}
    P._load_tables()
    with patch.object(M, 'dictionary_base_pos', side_effect=kinds.get), patch.object(
            P, '_TABLES', (frozenset(kinds), set(), set())):
        check('形容動詞からイ形容詞の活用を作らない', P.explain_kana_run('きれくない'), False)
        check('同形のイ形容詞の過去形', P.explain_kana_run('あつかった'), True)
        check('漢字の語幹でも同じ判定', P.explain_kana_run('かった', after_kanji=True, kanji_stem='嫌'), False)
        check('形容動詞の述語は残す', P.explain_kana_run('きれいだった'), True)
        check('未知の派生語の推定は残す', P._possible_i_adjective('未知語'), True)
    return ok


def run_view_latency_48vv():
    from types import SimpleNamespace
    from app import CorrectNoteApp as A, LineNumberGutter as G
    class Scheduler:
        def __init__(self): self.jobs={};self.serial=0
        def after(self,delay,fn):
            self.serial+=1;self.jobs[self.serial]=(delay,fn);return self.serial
        def after_cancel(self,job):self.jobs.pop(job,None)
    class Harness(A):
        def __init__(self):
            self.root=Scheduler();self.calls=[];self.marked=False
            self.editor_gutter=self.result_gutter=SimpleNamespace(redraw=lambda:self.calls.append('paint'))
        def _clamp_zoom_to_workarea(self):pass
        def _schedule_whitespace_paint(self):self.calls.append('space')
        def _mark_typed_from_shadow(self):self.marked=True
        def _warm_then_analyze(self):self.calls.append('warm')
        def editor_source_text(self):return '本文\n'*10000
        def _use_analysis_cache(self,text,lines):self.calls.append('cache');return self.cached
        def _schedule_analysis_chunk(self):self.calls.append('chunk queued')
    h=Harness();ok=True
    for _ in range(100):h._on_resize()
    ok=ok and not h.calls and len(h.root.jobs)==1
    h._analyze_units_only=True;h._analyze_chunk()
    ok=ok and h.calls==['chunk queued']
    h.calls.clear();h._analyze();ok=ok and not h.calls
    h._resume_tab_analysis();ok=ok and not h.calls
    h.root.jobs.clear();h._view_change_until=0;h.cached=True
    h._resume_tab_analysis();ok=ok and h.calls==['cache'] and h.marked
    h.calls.clear();h.cached=False;h._resume_tab_analysis()
    ok=ok and h.calls==['cache','warm']
    h.calls.clear();h._finish_resize();ok=ok and h.calls==['paint','paint','space']
    calls=[]
    class Target:
        def index(self,i):return {'end-1c':'100000.0','@0,0':'70000.0','@0,499':'70024.0'}[i]
        def winfo_height(self):return 500
        def dlineinfo(self,i):calls.append(i);return (0,0,20,20,15)
    class Gutter:
        target=Target();bookmarks={70010};font='font'
        def __getitem__(self,k):return 60
        def delete(self,*a):pass
        def create_text(self,*a,**kw):pass
        def create_oval(self,*a,**kw):pass
    G.redraw(Gutter())
    ok=ok and len(calls)==25 and calls[0]=='70000.0' and calls[-1]=='70024.0'
    print(('OK' if ok else 'NG'),'48-VV 10万行のガターは可視25行だけ・サイズ変更100回を統合・解析を待機・控えを優先')
    return ok


def run_tab_render_48vw():
    from types import SimpleNamespace
    from unittest.mock import patch
    import app
    class View:
        def __init__(self):self.text='';self.inserts=0;self.tags={}
        def config(self,**kw):pass
        def delete(self,*a):self.text='';self.tags={}
        def insert(self,index,text):self.inserts+=1;self.text+=text
        def tag_add(self,tag,*ranges):self.tags.setdefault(tag,[]).extend(ranges)
        def yview(self):return (0,1)
    class Harness(app.CorrectNoteApp):
        def __init__(self):
            self.root=SimpleNamespace(focus_get=lambda:None)
            self.store=SimpleNamespace(_tokenize_fn=lambda text:[])
            self.choices=None;self.editor=View();self.result_view=View();self._syncing=False
            self.editor_gutter=self.result_gutter=SimpleNamespace(sync_yview=lambda *a:None)
            self._analyze_units_only=True;self._analyze_todo=[0,1,2];self._analyze_pos=1
            self.line_results=[dict(original='元',corrected='補正'),dict(original='未準備',corrected='直し'),dict(original='',corrected='',pending=True)]
            self._units_cache={('元','補正'):('選択済み',[dict(kind='chosen',start=0,end=4)])}
        def _sync_partner_to_line(self,*a):pass
        def _paint_whitespace(self):pass
    h=Harness()
    with patch.object(app,'build_line_units',side_effect=AssertionError('描画中に解析した')):
        h._render_corrected()
    ok=(h.result_view.text=='選択済み\n直し\n' and h.result_view.inserts==1
        and h.line_units[1:]==[[],[]] and h.result_view.tags['chosen']==['1.0+0c','1.0+4c']
        and ('未準備','直し') not in h._units_cache)
    # 統合表示も、未準備の行は表示中の本文を残して分割処理へ任せる。
    h.unified_autofix_on=lambda:False
    h._suspect_units_cache={('元','補正',False):('元',[])}
    with patch.object(app,'build_suspect_units',side_effect=AssertionError('統合表示で解析した')):
        h._build_editor_units()
    ok=ok and h.line_texts==['元','未準備','']
    # 二つの本文の控えを混ぜず、戻ったときにだけ復元する。
    first=h._units_cache;h._analyze_text='一つ目';h._suspect_units_cache={'original':1}
    h._swap_tab_units('二つ目');ok=ok and not h._units_cache
    second={('別','別'):('別',[])};h._units_cache=second;h._analyze_text='二つ目'
    h._swap_tab_units('一つ目\n');ok=ok and h._units_cache is first and h._suspect_units_cache=={'original':1}
    h._invalidate_units_cache();ok=ok and not h._tab_units_cache and not h._units_cache
    for i in range(10):
        h._analyze_text=str(i);h._units_cache={i:[]};h._swap_tab_units(str(i+1))
    ok=ok and len(h._tab_units_cache)<=3
    print(('OK' if ok else 'NG'),'48-VW 描画中に全行を再解析しない・一括挿入・タブ別の控えと破棄')
    return ok


def run_window_drag_48vx():
    from types import SimpleNamespace
    from app import CorrectNoteApp as A
    class Root:
        def __init__(self):self.jobs={};self.serial=0;self.moves=[];self.flushes=0
        def after(self,ms,fn):self.serial+=1;self.jobs[self.serial]=fn;return self.serial
        def after_idle(self,fn):return self.after(0,fn)
        def after_cancel(self,job):self.jobs.pop(job,None)
        def geometry(self,value):self.moves.append(value)
        def state(self):return 'normal'
        def update_idletasks(self):self.flushes+=1
    class Harness(A):
        def __init__(self):
            self.root=Root();self.pressed=True;self.paints=0
            self.editor_gutter=self.result_gutter=SimpleNamespace(redraw=self._redraw_window_now)
        def _window_drag_button_down(self):return self.pressed
        def _redraw_window_now(self):self.paints+=1
        def _schedule_analysis_chunk(self):self.root.after(100,self._analyze_chunk)
        def _clamp_zoom_to_workarea(self):pass
    h=Harness();h._begin_native_window_drag()
    h._view_change_until=0;h._last_interaction=0;h._analyze_units_only=True
    for _ in range(100):
        h._analyze_yields=1000;h._analyze_chunk();h._poll_window_drag()
    ok=h._view_changing() and h._interacting() and h.paints==0
    h._finish_resize();h._paint_whitespace();h._after_view_moved();h._bg_step()
    ok=ok and h.paints==0
    h.pressed=False;h._poll_window_drag();h._view_change_until=0
    ok=ok and not h._view_changing()
    # フォールバックも、ドラッグ中にアイドル処理や全窓再描画を強制しない。
    h._win_drag=(10,20)
    for i in range(100):
        h._on_window_drag(SimpleNamespace(x_root=100+i,y_root=200+i));h._apply_window_drag()
    ok=ok and len(h.root.moves)==100 and h.root.flushes==0 and h.paints==0
    h._win_drag_to=(600,700);h._end_window_drag()
    ok=ok and h.root.moves[-1]=='+600+700' and h.paints==1 and h._win_drag is None
    # 同じ幅・高さの通知では、折り返しを塗り直さない。
    h.root.jobs.clear();event=SimpleNamespace(widget='editor',width=800,height=600)
    h._on_resize(event);job=h._resize_paint_job
    for _ in range(100):h._on_resize(event)
    ok=ok and h._resize_paint_job==job and len(h.root.jobs)==1
    # OSタイトルバーのConfigureも、ウインドウ移動の待機に結び付く。
    h.pressed=True
    for x in (100,101):
        h._note_interaction(SimpleNamespace(widget=h.root,type='22',x=x,y=100,width=800,height=600))
    ok=ok and h._native_window_drag
    print(('OK' if ok else 'NG'),'48-VX OS/Tk移動中は解析と再描画を待機・同寸法の通知を無視・最後の位置を反映')
    return ok


def run_nominal_suffix_48vy():
    """名詞化の接続、送り仮名、辞書なし、普通名詞への過剰適用を検査。"""
    import morphology as M
    import pos_grammar as P
    from unittest.mock import patch
    P._load_tables()
    kinds = {'便利': frozenset(('名詞,形容動詞語幹,*,*',)),
             '静か': frozenset(('名詞,形容動詞語幹,*,*',)),
             '作業': frozenset(('名詞,サ変接続,*,*',))}
    ok = True
    with patch.object(M, 'dictionary_base_pos', side_effect=kinds.get):
        for stem, run, expected in (
                ('便利', 'さの', True), ('便利', 'さを', True),
                ('便利', 'さが', True), ('便利', 'さについて', True),
                ('静', 'かさの', True), ('静', 'さの', False),
                ('作業', 'さの', False), ('未知', 'さの', False),
                ('便利', 'さっ', False), ('便利', 'さをに', False)):
            actual = P.explain_kana_run(run, after_kanji=True,
                                       kanji_stem=stem, no_words=True)
            if actual != expected:
                print('[NG] 48-VY', stem, run, actual, expected)
                ok = False
    print('48-VY 名詞化の接続:', ok)
    return ok


def run_screen_repairs_48vz():
    import corrector as C
    import morphology as M
    import pos_grammar as P
    import seed_japanese as S
    from unittest.mock import patch
    from types import SimpleNamespace
    ok = True
    def check(label, actual, expected):
        nonlocal ok
        if actual != expected:
            ok = False
            print('[NG] 48-VZ', label, actual, expected)
    store = SimpleNamespace(lookup=lambda r: [])
    faces = {'さいだい':['最大'], 'さいてい':['最低'],
             'じどう':['児童','自動'], 'さいたい':['妻帯']}
    index = SimpleNamespace(surfaces_for_reading=lambda r: faces.get(r, []))
    units = {'最大化','最低化','自動化'}
    methods = []
    def near(ch, input_method=None):
        methods.append(input_method)
        return [('だ',0.3),('て',0.8)] if ch == 'た' else []
    with patch.object(S,'is_unit',side_effect=lambda s:s in units), \
         patch.object(C,'_na_adj_ka_word',return_value=False), \
         patch.object(C,'_table_cost',side_effect=lambda s: {'最大化':100,'最低化':200}.get(s)), \
         patch.object(C,'_is_functional_strict',return_value=False), \
         patch.object(P,'explain_kana_run',return_value=False), \
         patch('kana_layout.nearby_candidates',side_effect=near):
        check('元の語でも全表記を照合', C._known_suffix_word_faces('じどうか',store,index), [('自動化',1,3)])
        check('語幹だけ存在する架空の派生は不可', C._known_suffix_word_faces('さいたいか',store,index), [])
        check('候補が複数でも先頭に決める', C._kana_run_hand_fixes('さいたいか',store,index,input_method='romaji'), [(0,5,'最大化','かな入力')])
        check('正常な語は読み替えない', C._kana_run_hand_fixes('じどうか',store,index), [])
        check('入力方式を候補探索へ渡す', set(methods), {'romaji'})
    def compound(last_known=True, gap=0):
        return [M.Token('書き','動詞','書く','かき',0,2,True,'自立','連用形'),
                M.Token('込み','動詞','込む','こみ',2+gap,4+gap,last_known,'自立','連用形'),
                M.Token('可能','名詞','可能','かのう',4+gap,6+gap,True,'形容動詞語幹')]
    with patch.object(S,'is_unit',side_effect=lambda s:s=='書き込み'):
        tokens=M.contextualize_tokens(compound())
        check('既知の連用形複合語を名詞にする',[(t.surface,t.pos,t.start,t.end) for t in tokens], [('書き込み','名詞',0,4),('可能','名詞',4,6)])
        check('未知の動詞は結合しない',len(M.contextualize_tokens(compound(False))),3)
        check('空白をまたいで結合しない',len(M.contextualize_tokens(compound(gap=1))),3)
    seen=[]
    @C._with_correction_source
    def nested(line):
        seen.append(C._CORRECTION_SOURCE.get())
        if line=='original': return nested('generated')
        return line
    check('入れ子でも最初の本文',nested('original'),'generated')
    check('入れ子の文脈',seen,['original','original'])
    check('終了時に本文を破棄',C._CORRECTION_SOURCE.get(),None)
    @C._with_correction_source
    def failing(line): raise ValueError('test')
    try: failing('private text')
    except ValueError: pass
    check('例外時も本文を破棄',C._CORRECTION_SOURCE.get(),None)
    print('48-VZ 画面の補正・名詞化・入力方式・元の本文:',ok)
    return ok
