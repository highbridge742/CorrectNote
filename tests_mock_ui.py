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
