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
関数呼び出しのキーワード引数が、受け側の定義に実在するかを調べる。

「受け側に引数を足したつもりで、ラッパーに足し漏れる」という編集ミスは、
構文としては正しいため py_compile では見つからない。実行時には
TypeError になるが、その呼び出しが try/except の中にあると
例外ごと握りつぶされ、「何も起きない」という一番分かりにくい
壊れ方をする（実例: app.py の correct_line ラッパーが
nearby_words / recent_words を受け漏れ、全行の解析が
黙って仮置きのまま残った）。

そこで namecheck.py / methodcheck.py と同じ流儀で、静的に確かめる。

    py kwargcheck.py app.py corrector.py vocabulary.py ...

見るもの:
  - 同じファイル内のモジュール直下の関数への呼び出し
  - `import mod` した別ファイル（同時に渡されたもの）の
    モジュール直下の関数への `mod.func(...)` 呼び出し
  - `from mod import func` で取り込んだ関数への呼び出し

**kwargs を受ける関数・見つからない関数は黙って素通しする
（誤検知で騒ぐより、確実な違反だけを報告する）。
"""
import ast
import os
import sys


def _func_params(node):
    """関数定義から (受け付ける引数名の集合, **kwargsの有無) を返す。"""
    a = node.args
    names = set()
    for arg in a.posonlyargs + a.args + a.kwonlyargs:
        names.add(arg.arg)
    return names, (a.kwarg is not None)


def module_functions(tree):
    """モジュール直下の関数定義を集める。name -> (引数集合, **kwargs有無)"""
    out = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = _func_params(node)
    return out


def module_imports(tree):
    """
    import の対応を集める。
      'corrector'            <- import corrector
      'C'                    <- import corrector as C
    戻り値: {ローカル名: モジュール名}
    """
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out[a.asname or a.name.split('.')[0]] = a.name
    return out


def from_imports(tree):
    """
    from mod import func の対応を集める。
    戻り値: {ローカル名: (モジュール名, 関数名)}
    """
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for a in node.names:
                if a.name != '*':
                    out[a.asname or a.name] = (node.module, a.name)
    return out


def check(paths):
    # 1周目: 全ファイルの関数定義を控える
    trees = {}
    defs = {}       # モジュール名 -> {関数名: (引数集合, **kwargs)}
    for path in paths:
        modname = os.path.splitext(os.path.basename(path))[0]
        try:
            tree = ast.parse(open(path, encoding='utf-8').read())
        except SyntaxError as e:
            print(f'{path}: 構文エラー {e}')
            continue
        trees[path] = (modname, tree)
        defs[modname] = module_functions(tree)

    problems = []

    # 2周目: 呼び出しを検査する
    for path, (modname, tree) in trees.items():
        local_funcs = defs.get(modname, {})
        imports = module_imports(tree)
        fimports = from_imports(tree)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = None       # (表示名, 引数集合, **kwargs有無)
            f = node.func
            if isinstance(f, ast.Name):
                if f.id in local_funcs:
                    names, has_kw = local_funcs[f.id]
                    target = (f.id, names, has_kw)
                elif f.id in fimports:
                    m, fn = fimports[f.id]
                    if m in defs and fn in defs[m]:
                        names, has_kw = defs[m][fn]
                        target = (f'{m}.{fn}', names, has_kw)
            elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                m = imports.get(f.value.id)
                if m in defs and f.attr in defs[m]:
                    names, has_kw = defs[m][f.attr]
                    target = (f'{m}.{f.attr}', names, has_kw)
            if target is None:
                continue
            name, params, has_kw = target
            if has_kw:
                continue
            for kw in node.keywords:
                if kw.arg is None:      # **展開は静的には見ない
                    continue
                if kw.arg not in params:
                    problems.append(
                        (path, node.lineno, name, kw.arg))
    return problems


if __name__ == '__main__':
    paths = sys.argv[1:]
    if not paths:
        print('使い方: py kwargcheck.py ファイル...')
        sys.exit(2)
    problems = check(paths)
    for path, lineno, name, arg in problems:
        print(f'{path}:{lineno}: {name}() は引数 {arg} を受け付けません')
    if problems:
        sys.exit(1)
    print('キーワード引数の食い違いはありません')
