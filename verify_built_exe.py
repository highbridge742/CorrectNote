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

# -*- coding: utf-8 -*-
"""Verify that a PyInstaller EXE contains the current CorrectNote version."""

import ast
import marshal
import sys
from pathlib import Path
from types import CodeType

from PyInstaller.archive.readers import CArchiveReader


def assigned_string(path, name):
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if any(isinstance(target, ast.Name) and target.id == name
                   for target in node.targets):
                assert isinstance(node.value.value, str), name
                return node.value.value
    raise AssertionError('{} was not found in {}'.format(name, path))


def strings(code):
    for value in code.co_consts:
        if isinstance(value, str):
            yield value
        elif isinstance(value, CodeType):
            yield from strings(value)


def script_code(data):
    for start in (0, 16):
        try:
            value = marshal.loads(data[start:])
        except (EOFError, ValueError, TypeError):
            continue
        if isinstance(value, CodeType):
            return value
    raise AssertionError('The bundled app script is not readable bytecode')


def same_code(bundled, source):
    """Compare executable bytecode and constants, ignoring only source paths."""
    if isinstance(bundled, CodeType) or isinstance(source, CodeType):
        if not isinstance(bundled, CodeType) or not isinstance(source, CodeType):
            return False
        fields = ('co_code', 'co_names', 'co_varnames', 'co_freevars',
                  'co_cellvars', 'co_flags', 'co_argcount',
                  'co_kwonlyargcount', 'co_posonlyargcount', 'co_firstlineno')
        return (all(getattr(bundled, field) == getattr(source, field)
                    for field in fields)
                and same_code(bundled.co_consts, source.co_consts))
    if isinstance(bundled, (tuple, list)) or isinstance(source, (tuple, list)):
        return (type(bundled) is type(source)
                and len(bundled) == len(source)
                and all(same_code(a, b) for a, b in zip(bundled, source)))
    return bundled == source


def main(exe_path):
    root = Path(__file__).resolve().parent
    exe = Path(exe_path).resolve()
    assert exe.is_file() and exe.stat().st_size > 0, exe
    app_version = assigned_string(root / 'app.py', 'APP_VERSION')
    engine_stamp = assigned_string(root / 'analysis_cache.py', 'ENGINE_STAMP')

    archive = CArchiveReader(str(exe))
    app = script_code(archive.extract('app'))
    assert app_version in strings(app), ('APP_VERSION missing from EXE', app_version)
    pyz = archive.open_embedded_archive('PYZ.pyz')
    assert engine_stamp in strings(pyz.extract('analysis_cache')), (
        'ENGINE_STAMP missing from EXE', engine_stamp)
    for module in ('contextual_repair', 'ime_colloquial', 'seed_japanese'):
        assert module in pyz.toc, ('module missing from EXE', module)
    assert 'seed_japanese.txt.gz' in archive.toc, (
        'seed lexicon missing from EXE', exe)
    private = {'vocabulary.json', 'session.json', 'last_choice.json',
               'ime_readings.json', 'analysis_cache.json', 'context_vec.json',
               'charngram.json', 'decisions.json', 'settings.json', 'setup.json'}
    assert not any(name.replace('\\', '/').rsplit('/', 1)[-1] in private
                   for name in archive.toc), (
        'personal data included in EXE', exe)
    modules = sorted({'app'} | {path.stem for path in root.glob('*.py')
                               if path.stem in pyz.toc})
    for module in modules:
        bundled = app if module == 'app' else pyz.extract(module)
        source_file = root / (module + '.py')
        source = compile(source_file.read_text(encoding='utf-8'),
                         module + '.py', 'exec')
        assert same_code(bundled, source), (
            'EXE contains stale Python code', module)
    from bundle_manifest import NAMES as BUNDLED_FILES
    for name in BUNDLED_FILES:
        assert name in archive.toc, ('asset missing from EXE', name)
        assert archive.extract(name) == (root / name).read_bytes(), (
            'EXE contains stale asset', name)
    print('EXE_VERIFIED APP_VERSION={} ENGINE_STAMP={} modules={} assets={} bytes={}'.format(
        app_version, engine_stamp, len(modules), len(BUNDLED_FILES), exe.stat().st_size))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: verify_built_exe.py EXE_PATH')
    main(sys.argv[1])
