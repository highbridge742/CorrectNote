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

        def _schedule_analysis_chunk(self):
            self.scheduled += 1

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
    check('タブの止まりも、前と同じなら敷き直さない',
          '_ws_stop_sig' in (ast.get_source_segment(
              src, methods['_paint_line_tab_stops']) or ''), True)

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
