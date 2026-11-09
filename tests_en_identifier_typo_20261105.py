# -*- coding: utf-8 -*-
"""2026-11-05 うに「スペル間違いの英単語は補正されても、前か後ろにアンダーバーをつけると補正されない。変数の打ち間違い」:
「_」でつないだ名前の中の語も、名前の外と同じ1つの打ち違いの直しを当てる。例はすべて作った例。"""
import unittest

import en_space as E


def fixed(line):
    out = list(line)
    for s, e, f in sorted(E._identifier_fixes(line), reverse=True):
        out[s:e] = f
    return ''.join(out)


class IdentifierTypoTests(unittest.TestCase):
    def test_fixed(self):
        cases = {
            'call recieve_data now': 'call receive_data now',
            'call _recieve now': 'call _receive now',
            'print(total_lenght_)': 'print(total_length_)',
            'MAX_RETRUN_COUNT = 5': 'MAX_RETURN_COUNT = 5',
            'Get_Reponse_Data': 'Get_Response_Data',
        }
        for line, want in cases.items():
            self.assertEqual(fixed(line), want, line)

    def test_left(self):
        for line in ('os.path.join(base_dir, file_name)', 'col_colno and line_lineno',
                     'see /usr/lib/x86_64_linux', 'my_hogehoge_var', 'addr_recv_idx', 'getUserNmae_x',
                     'recieve data', 'kaiin_bangou'):
            self.assertEqual(E._identifier_fixes(line), [], line)


if __name__ == '__main__':
    unittest.main()
