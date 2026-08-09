# CorrectNote — かな入力誤字補正メモ帳
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
exe に janome が正しく同梱されているかを確認するスクリプト。

かな入力メモ帳の本体には組み込まず、確認専用として使う。
このスクリプトだけを PyInstaller で単独の exe にすると、
「janome が入っていないPCでも動くか」を安全に確認できる
（本体アプリを壊す心配がない）。

作り方（ビルドする側のPCで）:
    py -m PyInstaller --onefile --console check_janome.py

確認方法:
    1. 上のコマンドで dist\\check_janome.exe を作る
    2. janome を pip install していない、別のPC（や仮想環境）に
       check_janome.exe だけをコピーする
    3. ダブルクリックして実行する
    4. 「OK」と出れば、本体の KanaMemo.exe も同じ仕組みで
       janome 同梱に問題が無いと確認できる
"""

import sys

print('=' * 50)
print('janome 同梱チェック')
print('=' * 50)

ok = True

try:
    import janome
    print(f'[OK] janome の import に成功: version='
          f'{getattr(janome, "__version__", "不明")}')
except Exception as e:
    ok = False
    print(f'[NG] janome の import に失敗: {e}')

try:
    from janome.tokenizer import Tokenizer
    t = Tokenizer()
    result = list(t.tokenize('かな入力のテストです'))
    print(f'[OK] 形態素解析に成功: {len(result)} 語に分割')
    for tok in result[:5]:
        print(f'       {tok.surface}\t{tok.part_of_speech}\t{tok.reading}')
except Exception as e:
    ok = False
    print(f'[NG] 形態素解析に失敗: {e}')

# 辞書モジュール（sysdic）が実際に読めるかも確認する。
# ここが読めないと「import はできるが辞書が空」という
# 分かりにくい壊れ方をするため、明示的に見る。
try:
    import importlib
    m = importlib.import_module('janome.sysdic.entries_compact0')
    print(f'[OK] 辞書モジュール（entries_compact0）の読み込みに成功')
except Exception as e:
    ok = False
    print(f'[NG] 辞書モジュールの読み込みに失敗: {e}')

print()
if ok:
    print('総合結果: OK — janome は正しく同梱されています。')
else:
    print('総合結果: NG — 同梱に問題があります。'
          'kana_memo.spec の collect_all(\'janome\') を確認してください。')

print()
input('確認できたら Enter キーで終了します...')
sys.exit(0 if ok else 1)
