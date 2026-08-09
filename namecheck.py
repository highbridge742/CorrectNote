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

"""pyflakes が入らない環境向けの、簡易な未定義名チェッカー。

関数ごとにローカル束縛を集め、モジュールのグローバル・組み込み・
外側のスコープに無い名前を報告する。完全ではないが、
タイプミスや削除し忘れの参照を見つけるには十分。
"""
import ast
import builtins
import sys


class Scope:
    def __init__(self, parent=None):
        self.parent = parent
        self.names = set()

    def add(self, n):
        self.names.add(n)

    def has(self, n):
        s = self
        while s:
            if n in s.names:
                return True
            s = s.parent
        return False


BUILTIN = set(dir(builtins)) | {'__file__', '__name__', '__doc__', '__spec__'}


def collect_bindings(nodes, scope):
    """このスコープ直下で束縛される名前を集める（入れ子の関数本体は除く）"""
    for node in nodes:
        for n in ast.walk(node):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                              ast.ClassDef)):
                scope.add(n.name)
            elif isinstance(n, ast.Name) and isinstance(n.ctx,
                                                        (ast.Store, ast.Del)):
                scope.add(n.id)
            elif isinstance(n, ast.arg):
                scope.add(n.arg)
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                for a in n.names:
                    scope.add((a.asname or a.name).split('.')[0])
            elif isinstance(n, ast.ExceptHandler) and n.name:
                scope.add(n.name)
            elif isinstance(n, (ast.Global, ast.Nonlocal)):
                for name in n.names:
                    scope.add(name)


def check(path):
    src = open(path, encoding='utf-8').read()
    tree = ast.parse(src)
    module = Scope()
    module.names |= BUILTIN
    collect_bindings(tree.body, module)

    problems = []

    def walk_body(body, scope):
        for node in body:
            visit(node, scope)

    def visit(node, scope):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in node.decorator_list:
                visit(d, scope)
            for d in node.args.defaults + [x for x in node.args.kw_defaults
                                           if x]:
                visit(d, scope)
            inner = Scope(scope)
            collect_bindings(node.body, inner)
            for a in ast.walk(node.args):
                if isinstance(a, ast.arg):
                    inner.add(a.arg)
            walk_body(node.body, inner)
            return
        if isinstance(node, ast.ClassDef):
            inner = Scope(scope)
            collect_bindings(node.body, inner)
            walk_body(node.body, inner)
            return
        if isinstance(node, ast.Lambda):
            inner = Scope(scope)
            for a in ast.walk(node.args):
                if isinstance(a, ast.arg):
                    inner.add(a.arg)
            visit(node.body, inner)
            return
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp,
                             ast.GeneratorExp)):
            inner = Scope(scope)
            for gen in node.generators:
                collect_bindings([gen.target], inner)
            for gen in node.generators:
                visit(gen.iter, scope if gen is node.generators[0] else inner)
                for c in gen.ifs:
                    visit(c, inner)
            if isinstance(node, ast.DictComp):
                visit(node.key, inner)
                visit(node.value, inner)
            else:
                visit(node.elt, inner)
            return
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if not scope.has(node.id):
                problems.append((node.lineno, node.id))
            return
        for child in ast.iter_child_nodes(node):
            visit(child, scope)

    walk_body(tree.body, module)
    return problems


for path in sys.argv[1:]:
    for lineno, name in check(path):
        print(f'{path}:{lineno}: 未定義の可能性 {name}')
