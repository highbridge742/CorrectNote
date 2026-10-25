# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""Backups of each tab's text (2026-10-23 うにさん).

「保存のたびにそのタブのバックアップを作る。朝4時（ローカル時刻）をまたぐまでは同じ1つを上書き、
またいだら新しいバックアップに切り替える。1タブにつき残す数はパラメータ（既定5、0〜20、0なら作らない）。
超えた古いものから捨てる」.

Saving means writing the tab to its file and the periodic save of the open tabs (session.json), so a
tab never written to a file is kept too. A tab is known by its file's path, or, before it has one, by
an id kept with the tab in the session (backup_id). Each tab has a folder under backups/ in the app's
data folder (app_dir: next to the exe, or the package's LocalAppData under MSIX); each backup is one
UTF-8 file named by its time. Writing goes through a .tmp file and a replace; any failure is ignored,
so it never stops the save it follows.
"""
import datetime
import hashlib
import json
import os
import re
import uuid

DAY_STARTS_AT = 4            # o'clock: a backup "day" runs from 4:00 to 3:59 the next morning
FOLDER = 'backups'
_NAME = re.compile(r'^(\d{8}-\d{6})(-m)?\.txt$')
_STAMP = '%Y%m%d-%H%M%S'
# Manual backups (2026-10-23 うにさん「ファイルメニューに『手動でバックアップを作成（最大n個）』。手動は毎日の
# バックアップとは別管理（別の数え方・別の上限）」): the same folder, named with -m, counted on their own
MANUAL = '-m'


def now():
    return datetime.datetime.now()


def backup_day(moment):
    return (moment - datetime.timedelta(hours=DAY_STARTS_AT)).date()


def new_id():
    return uuid.uuid4().hex


def tab_key(tab):
    """The name the tab's backups go under: the id it got while it had no file (it keeps its backups
    after "save as"), else its file's path (a file opened in a tab). None if neither."""
    if tab.get('backup_id'):
        return 'id:' + tab['backup_id']
    path = tab.get('path')
    if path:
        return 'path:' + os.path.normcase(os.path.abspath(path))
    return None


def folder_for(base, key):
    return os.path.join(base, FOLDER, hashlib.sha1(key.encode('utf-8')).hexdigest()[:16])


def list_backups(base, key, manual=False):
    """[(time, file path)] newest first: the daily ones, or with manual=True the manual ones."""
    return [(when, path) for when, path, by_hand in list_all(base, key) if by_hand == manual]


def list_all(base, key):
    """[(time, file path, manual)] newest first, daily and manual together."""
    if not key:
        return []
    folder = folder_for(base, key)
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    out = []
    for name in names:
        match = _NAME.match(name)
        if not match:
            continue
        try:
            out.append((datetime.datetime.strptime(match.group(1), _STAMP), os.path.join(folder, name),
                        bool(match.group(2))))
        except ValueError:
            continue
    return sorted(out, reverse=True)


def read(path):
    with open(path, 'rb') as f:
        return f.read().decode('utf-8', 'replace')


def remove(path):
    try:
        os.remove(path)
        return True
    except OSError:
        return False


def save(base, key, text, keep, title='', moment=None):
    """Keep `text` as this tab's backup. Same backup day as the newest one: that one is replaced
    (and named by the new time); else a new one. Then only the newest `keep` stay.
    Returns the file written, or None (nothing kept: keep 0, no key, or a failure)."""
    if not key or keep <= 0 or text is None:
        return None
    moment = moment or now()
    try:
        folder = folder_for(base, key)
        os.makedirs(folder, exist_ok=True)
        existing = list_backups(base, key)
        target = os.path.join(folder, moment.strftime(_STAMP) + '.txt')
        if existing and existing[0][1] != target and read(existing[0][1]) == text \
                and backup_day(existing[0][0]) == backup_day(moment):
            return existing[0][1]            # nothing new since: leave it as it is
        tmp = target + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(text.encode('utf-8'))
        os.replace(tmp, target)
        if existing and backup_day(existing[0][0]) == backup_day(moment) and existing[0][1] != target:
            remove(existing[0][1])           # the same day's one: replaced by the new time
        for _when, old in list_backups(base, key)[keep:]:
            remove(old)
        _write_info(folder, key, title)
        return target
    except Exception:
        return None


def save_manual(base, key, text, keep, title='', moment=None):
    """A manual backup of `text`: always a new one (the daily ones are not touched), then only the
    newest `keep` manual ones stay. Returns the file written, or None (keep 0, no key, or a failure)."""
    if not key or keep <= 0 or text is None:
        return None
    moment = moment or now()
    try:
        folder = folder_for(base, key)
        os.makedirs(folder, exist_ok=True)
        target = os.path.join(folder, moment.strftime(_STAMP) + MANUAL + '.txt')
        while os.path.exists(target):          # made twice in one second: each click keeps its own
            moment += datetime.timedelta(seconds=1)
            target = os.path.join(folder, moment.strftime(_STAMP) + MANUAL + '.txt')
        tmp = target + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(text.encode('utf-8'))
        os.replace(tmp, target)
        for _when, old in list_backups(base, key, manual=True)[keep:]:
            remove(old)
        _write_info(folder, key, title)
        return target
    except Exception:
        return None


def _write_info(folder, key, title):
    try:
        info = os.path.join(folder, 'tab.json')
        with open(info + '.tmp', 'w', encoding='utf-8') as f:
            json.dump({'key': key, 'title': title}, f, ensure_ascii=False)
        os.replace(info + '.tmp', info)
    except OSError:
        pass
