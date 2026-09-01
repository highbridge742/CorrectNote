# -*- coding: utf-8 -*-
"""
exe に同梱するもの（**`.py` ではないもの**）の名簿。

**名簿はここ1つにする。** 項目48-DK（`familiarity.json` と
`kanji_onkun.json` が spec に無く、exe に最初から入っていなかった）と
項目48-GC（速い側の材料を別の名簿から作っていて、いつのまにか
ずれていた）の、どちらも「**同じものを指す一覧が2つ以上あった**」
という同じ形の失敗だった。ここを唯一の名簿にして、使う側は全部
ここを読む。

    correctnote.spec   手元のビルド（build_exe.bat）
    kana_memo.spec     CI のビルド（build.yml）
    build_exe.bat      ビルドの**後**の点検（build/bundle_report.txt を読む）
    ci_smoke_test.py   出来上がったもので**読めているか**の見張り
    freshstate.py      初期状態を作るときの写し

**`.py` はここに書かない。** PyInstaller が import を辿って自動で
入れるし、`freshstate.py` は `*.py` を全部写す。ここに挙げるのは
「**自動では入らないもの**」だけ。

**育つデータ（`vocabulary.json`・`context_vec.json`・`charngram.json`
など）もここに書かない。** あれは同梱物ではなく、exe と同じフォルダに
実行時に作られるもの（`app.py` の `app_dir()`）。同梱すると、
配ったものに個人のメモや語彙が入ってしまう。
"""

import os
import sys
from collections import namedtuple

# name     ファイル名（exe の中では '.' 直下＝ sys._MEIPASS 直下に置く）
# module   「読めているか」を聞ける相手（`available()` を持つ）。無ければ None
# why      **入っていないと何が起きるか**。静かに効かなくなるものばかりなので、
#          報告にそのまま出す
# required 手元のビルドで、無ければ**赤くする**もの
Item = namedtuple('Item', 'name module why required')

ITEMS = (
    Item('CorrectNote_説明書v6.html', None,
         'メニューの「説明書をHTMLで展開」が出せなくなる',
         True),
    Item('familiarity.json', 'familiarity',
         '書籍を基準にした並べ替えが丸ごと効かなくなる（新聞基準に戻る）',
         False),
    Item('kanji_onkun.json', 'kanji_onkun',
         '漢字から読みを推す道が細る',
         False),
    Item('seed_japanese.txt.gz', 'seed_japanese',
         '正しく書けた語を守る門（項目48-FC）が効かなくなる',
         False),
    Item('seed_japanese_cost.txt.gz', None,
         '表記の別読み（仮名＝かな・項目48-IS）が引けず、'
         '異様な塊をひらがなに開く道が細る',
         False),
    Item('NOTICE_sudachi.txt', None,
         'SudachiDict（Apache-2.0）の表示が配布物から落ちる',
         False),
    # アイコン（項目48-JR）。**2つとも要る**——`.ico` は Windows の
    # 窓とタスクバー（`iconbitmap`）、`.png` は `iconphoto`（Tk は
    # `.ico` を PhotoImage で読めない）。exe そのものの絵は
    # `correctnote.spec` / `kana_memo.spec` の `icon=` が別に持つ。
    Item('correctnote.ico', None,
         '窓とタスクバーのアイコンが Tk の羽根に戻る（Windows）',
         True),
    Item('correctnote.png', None,
         '`iconphoto` の逃げ道が無くなる（`.ico` が使えない環境で羽根に戻る）',
         True),
)

# 使う側が name だけ欲しいとき
NAMES = tuple(i.name for i in ITEMS)

# 「読めているか」を聞ける相手がいるものだけ
WITH_MODULE = tuple(i for i in ITEMS if i.module)

RESULT_LINE_OK = 'RESULT=OK'
RESULT_LINE_NG = 'RESULT=NG'


def collect(here, label):
    """
    同梱するものを集める。

    **在るものだけ挙げる。** PyInstaller は `datas` に挙げた実物が
    無いとビルドごと止まるので、挙げてよいのは実在するものだけ。
    無いものは**報告に出す**（止めない。CI を赤くしない）。

    戻り値: (datas, report_lines, missing_required)
        datas           Analysis に渡す [(元のパス, '.'), ...]
        report_lines    そのまま人が読める行の並び
        missing_required 必須なのに無かった名前
    """
    datas, lines, missing_required, missing_optional = [], [], [], []
    lines.append('=' * 60)
    lines.append(f'exe に同梱したもの（{label}）')
    lines.append('=' * 60)
    for item in ITEMS:
        path = os.path.join(here, item.name)
        if os.path.exists(path):
            datas.append((path, '.'))
            size = os.path.getsize(path)
            lines.append(f'[OK] {item.name}  ({size:,} バイト)')
        elif item.required:
            missing_required.append(item.name)
            lines.append(f'[NG] {item.name} が**無い**')
            lines.append(f'     -> {item.why}')
        else:
            missing_optional.append(item.name)
            lines.append(f'[NG] {item.name} が**無い**（同梱せずに続ける）')
            lines.append(f'     -> {item.why}')
    lines.append('')
    if missing_required or missing_optional:
        lines.append('!! 足りないものがあります。'
                     'どれも「無ければ黙って効かない」造りなので、')
        lines.append('!! 出来上がった exe は**動くのに、その機能だけ静かに'
                     '効きません**。')
    else:
        lines.append('足りないものはありません。')
    lines.append('')
    lines.append('-' * 60)
    lines.append('exe と同じフォルダに、実行時に作られるもの（同梱しない）')
    lines.append('-' * 60)
    lines.append('  vocabulary.json / context_vec.json / dict_index.json /')
    lines.append('  charngram.json / session.json / settings.json /')
    lines.append('  decisions.json / choices.json / setup.json /')
    lines.append('  analysis_cache.json / ime_readings.json')
    lines.append('')
    lines.append('  **exe は、置いたフォルダを見ます。** 新しいフォルダで')
    lines.append('  動かせば、語彙もメモも空の**初期状態**から始まります')
    lines.append('  （初回起動で辞書を取り込むので、そのぶん時間がかかります）。')
    lines.append('  いまの語彙・メモのまま試したいときは、exe を')
    lines.append('  **そのデータの在るフォルダへ写して**動かしてください。')
    lines.append('')
    lines.append(RESULT_LINE_NG if (missing_required or missing_optional)
                 else RESULT_LINE_OK)
    return datas, lines, missing_required


def print_report(lines, label):
    """
    報告を画面（ビルドの記録）にも出す。**ここで絶対に落ちないこと。**

    GitHub Actions の Windows は**画面の文字集合が cp1252** で、
    日本語がそのまま出せない。`print` がそこで `UnicodeEncodeError`
    を投げ、**ビルドが丸ごと止まった**（2026-08-22・項目48-IL）。

    報告は「見えると助かるもの」であって、**ビルドを止めてよいもの
    ではない**。出せない字は置き換えてでも、必ず先へ進む。
    出す側（spec）で毎回書くと片方に書き忘れるので、**ここ1箇所**に
    置いて、`correctnote.spec` と `kana_memo.spec` の両方から呼ぶ。
    """
    enc = getattr(sys.stdout, 'encoding', None) or 'ascii'
    for line in lines:
        text = f'[{label}] {line}'
        try:
            print(text)
            continue
        except Exception:
            pass
        try:
            print(text.encode(enc, 'replace').decode(enc, 'replace'))
            continue
        except Exception:
            pass
        try:
            print(text.encode('ascii', 'replace').decode('ascii'))
        except Exception:
            pass                 # ここまで来たら、黙って先へ進む


def write_report(lines, here):
    """
    報告を `build/bundle_report.txt` に残す。

    **cp932 で書く。** `build_exe.bat` が `type` で出すので、
    日本語版 Windows のコンソール（cp932）で読めないと意味がない。
    """
    out_dir = os.path.join(here, 'build')
    try:
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, 'bundle_report.txt')
        try:
            with open(path, 'w', encoding='cp932', errors='replace') as f:
                f.write('\n'.join(lines) + '\n')
        except LookupError:      # cp932 の無い環境（Linux の CI など）
            with open(path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')
        return path
    except Exception:
        return None
