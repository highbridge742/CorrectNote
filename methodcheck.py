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
クラス内の self.xxx(...) 呼び出しが、実際に定義されているかを調べる。

「メソッドの def 行だけを誤って消してしまい、呼び出しだけが残る」
という編集ミスは、構文としては正しいため py_compile では見つからない。
tkinter が無くて起動できない環境では実行時にも気づけないので、
静的に確かめられるようにしておく。
"""
import ast
import sys


def check(path):
    tree = ast.parse(open(path, encoding='utf-8').read())
    problems = []

    # このファイルのどこかのクラスで def されている名前を全部集める。
    # 「他のクラスには在るのに、このクラスには無い」を見分けるため。
    _ALL_METHODS = set()
    for _n in ast.walk(tree):
        if isinstance(_n, ast.ClassDef):
            for _f in _n.body:
                if isinstance(_f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    _ALL_METHODS.add(_f.name)

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        # 外部のクラス（tk.Canvas 等）を継承している場合、
        # 親から受け継いだメソッドがこのファイルには現れないため、
        # 未定義かどうかを静的には判断できない。検査から外す。
        if node.bases:
            continue

        defined = set()
        for item in ast.walk(node):
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined.add(item.name)
            # クラス変数・インスタンス属性への代入も「存在するもの」に数える
            elif isinstance(item, ast.Assign):
                for t in item.targets:
                    if isinstance(t, ast.Attribute) and \
                            isinstance(t.value, ast.Name) and \
                            t.value.id == 'self':
                        defined.add(t.attr)
                    elif isinstance(t, ast.Name):
                        defined.add(t.id)
            elif isinstance(item, ast.AnnAssign):
                t = item.target
                if isinstance(t, ast.Attribute) and \
                        isinstance(t.value, ast.Name) and t.value.id == 'self':
                    defined.add(t.attr)

        # self.xxx(...) の形の呼び出しを集める
        for item in ast.walk(node):
            if not isinstance(item, ast.Call):
                continue
            f = item.func
            if not isinstance(f, ast.Attribute):
                continue
            if not (isinstance(f.value, ast.Name) and f.value.id == 'self'):
                continue
            if f.attr not in defined:
                problems.append((f.lineno, node.name, f.attr, '呼び出し'))

        # **値として渡す形も見る**（2026-08-18 に痛い目を見て足した）。
        #
        #     self.editor.bind('<Control-a>', self._on_select_all)
        #
        # これは**呼び出しではない**ので上の検査を素通りしていた。
        # `_on_select_all` を別のクラスに書いてしまい、
        # **アプリが起動しなくなった**（うにさんの画面で
        # AttributeError）。呼ぶ形だけ見ていては足りない。
        #
        # ただし「このファイルのどこかのクラスにはある名前」に絞る。
        # tkinter などから受け継いだ属性を誤って挙げないため。
        for item in ast.walk(node):
            if not isinstance(item, ast.Attribute):
                continue
            if not (isinstance(item.value, ast.Name)
                    and item.value.id == 'self'):
                continue
            if not isinstance(item.ctx, ast.Load):
                continue        # 代入の左辺は見ない
            if item.attr in defined:
                continue
            if item.attr not in _ALL_METHODS:
                continue        # このファイルのどこにも無い名前は判断しない
            problems.append((item.lineno, node.name, item.attr,
                             '値として使用'))

    return problems


ok = True
for path in (sys.argv[1:] or ['app.py']):
    for lineno, cls, name, how in check(path):
        ok = False
        print(f'{path}:{lineno}: {cls}.{name} が定義されていません（{how}）')
if ok:
    print('未定義のメソッド呼び出しはありません')
