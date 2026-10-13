# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
# -*- coding: utf-8 -*-
import json
import unittest
from unittest.mock import mock_open, patch

from pos_font import (POS_CATEGORIES, POS_FONT_DEFAULTS, font_size,
                      has_adjustments, normalize_colors,
                      normalize_multipliers, spans)
from settings import Settings


class PosFontTests(unittest.TestCase):
    def test_default_multipliers_enlarge_verbs_adjectives_adverbs_auxiliaries(self):
        enlarged=('名詞','動詞','形容詞','副詞','助動詞')
        for key in enlarged:
            self.assertEqual(POS_FONT_DEFAULTS[key],1.1)
        self.assertEqual(POS_FONT_DEFAULTS['数詞'],1.2)
        self.assertTrue(all(POS_FONT_DEFAULTS[key]==1.0 for key in POS_CATEGORIES
                            if key not in enlarged+('数詞',)))
        self.assertEqual(Settings().get('editor_font_size'),10)
        self.assertLess(POS_CATEGORIES.index('名詞'),
                        POS_CATEGORIES.index('名詞（サ変）'))
        self.assertLess(POS_CATEGORIES.index('名詞（サ変）'),
                        POS_CATEGORIES.index('動詞'))
        self.assertEqual(Settings().get('pos_font_multipliers'),
                         POS_FONT_DEFAULTS)
        self.assertTrue(has_adjustments(POS_FONT_DEFAULTS))
        self.assertFalse(has_adjustments({key:1.0 for key in POS_CATEGORIES}))

    def test_font_size_uses_decimal_ceiling_not_binary_float_rounding(self):
        self.assertEqual(font_size(10,1.1),11)
        self.assertEqual(font_size(11,1.1),13)
        self.assertEqual(font_size(14,1.1),16)
        self.assertEqual(font_size(11,1.0),11)
        self.assertEqual(font_size(11,0.9),10)

    def test_token_spans_require_matching_text_and_map_unknown_pos_to_other(self):
        text='資料は😀'
        tokens=(('資料','名詞:一般','シリョウ',0,2,True),
                ('は','助詞:係助詞','ハ',2,3,True),
                ('😀','未知品詞','',3,4,False),
                ('誤り','形容詞','',0,2,True))
        self.assertEqual(spans(text,tokens),
            (('名詞',0,2),('助詞',2,3),('その他',3,4)))

    def test_latin_letters_and_their_periods_and_underscores_are_eigo(self):
        # 2026-10-13 うにさん：英字が名詞扱いだった。英字の前後のピリオドと
        # アンダーバーも英字の設定にする。数字は数詞のまま。
        text='Noteのfile_name.txtを開く。e.g.とv1.2と＿ＡＢ．'
        pos={'の':'助詞:連体化','を':'助詞:格助詞','開く':'動詞:自立','と':'助詞:並立助詞'}
        tokens=[];at=0
        for surface in ('Note','の','file','_','name','.','txt','を','開く','。',
                        'e','.','g','.','と','v1.2','と','＿','ＡＢ','．'):
            label=pos.get(surface,'記号:一般' if surface in '._。＿．' else '名詞:固有名詞')
            tokens.append((surface,label,'',at,at+len(surface),True));at+=len(surface)
        runs=spans(text,tokens)
        def kind(fragment,start=0):
            i=text.index(fragment,start)
            return {m for m,a,z in runs if a<i+len(fragment) and z>i}
        self.assertEqual(kind('Note'),{'英字'})
        self.assertEqual(kind('file_name.txt'),{'英字'})
        self.assertEqual(kind('e.g.'),{'英字'})
        self.assertEqual(kind('＿ＡＢ．'),{'英字'})
        self.assertEqual(kind('v'),{'英字'})
        self.assertEqual(kind('1.2'),{'数詞'})
        self.assertEqual(kind('。'),{'記号'})
        self.assertEqual(kind('の'),{'助詞'})
        # Every character keeps exactly one run.
        covered=[i for m,a,z in runs for i in range(a,z)]
        self.assertEqual(covered,list(range(len(text))))
        self.assertIn('英字',POS_CATEGORIES)
        self.assertEqual(normalize_multipliers({})['英字'],1.0)
        self.assertEqual(normalize_colors({'名詞':'#112233','英字':''})['英字'],'')

    def test_sahen_nouns_have_an_independent_display_bucket(self):
        text='勉強を開始する'
        tokens=(('勉強','名詞:サ変接続','ベンキョウ',0,2,True),
                ('を','助詞:格助詞','ヲ',2,3,True),
                ('開始','名詞:サ変可能','カイシ',3,5,True),
                ('する','動詞:自立','スル',5,7,True))
        self.assertEqual(spans(text,tokens),(
            ('名詞（サ変）',0,2),('助詞',2,3),
            ('名詞（サ変）',3,5),('動詞',5,7)))
        ordinary=(('資料','名詞:一般','シリョウ',0,2,True),)
        self.assertEqual(spans('資料',ordinary),(('名詞',0,2),))

    def test_numerals_have_their_own_bucket_even_inside_joined_nouns(self):
        text='2026年に百人、3個と３本目'
        tokens=(('2026','名詞:数','',0,4,True),
                ('年','名詞:接尾:助数詞','ネン',4,5,True),
                ('に','助詞:格助詞:一般','ニ',5,6,True),
                ('百','名詞:数','ヒャク',6,7,True),
                ('人','名詞:接尾:助数詞','ニン',7,8,True),
                ('、','記号:読点','、',8,9,True),
                ('3個','名詞:一般','',9,11,True),
                ('と','助詞:並立助詞','ト',11,12,True),
                ('３本目','名詞:一般','',12,15,True))
        self.assertEqual(spans(text,tokens),(
            ('数詞',0,4),('名詞',4,5),('助詞',5,6),('数詞',6,7),
            ('名詞',7,8),('記号',8,9),('数詞',9,10),('名詞',10,11),
            ('助詞',11,12),('数詞',12,13),('名詞',13,15)))
        self.assertLess(POS_CATEGORIES.index('名詞（サ変）'),
                        POS_CATEGORIES.index('数詞'))
        self.assertEqual(POS_FONT_DEFAULTS['数詞'],1.2)
        self.assertEqual(spans('一般',(('一般','名詞:一般','',0,2,True),)),
                         (('名詞',0,2),))

    def test_decimal_points_and_commas_inside_numbers_are_numerals(self):
        text='3.14と1,000と２．５、1、2'
        tokens=(('3','名詞:数','',0,1,True),('.','記号:一般','',1,2,True),
                ('14','名詞:数','',2,4,True),('と','助詞:並立助詞','ト',4,5,True),
                ('1','名詞:数','',5,6,True),(',','記号:読点','',6,7,True),
                ('000','名詞:数','',7,10,True),('と','助詞:並立助詞','ト',10,11,True),
                ('２．５','名詞:数','',11,14,True),('、','記号:読点','、',14,15,True),
                ('1','名詞:数','',15,16,True),('、','記号:読点','、',16,17,True),
                ('2','名詞:数','',17,18,True))
        result=spans(text,tokens)
        numerals=''.join(text[a:z] for major,a,z in result if major=='数詞')
        self.assertEqual(numerals,'3.141,000２．５12')
        self.assertIn(('記号',14,15),result)

    def test_settings_merge_valid_saved_values_and_ignore_bad_entries(self):
        settings=Settings()
        saved={'名詞':1.4,'動詞':1.25,'形容詞':True,
               '助詞':float('inf'),'未知':1.8,'記号':0.4}
        data=json.dumps({'pos_font_multipliers':saved},ensure_ascii=False)
        with patch('settings.os.path.exists',return_value=True), \
                patch('builtins.open',mock_open(read_data=data)):
            settings.load('synthetic-settings.json')
        result=settings.get('pos_font_multipliers')
        self.assertEqual(result['名詞'],1.4)
        self.assertEqual(result['動詞'],1.25)
        self.assertEqual(result['形容詞'],1.1)
        self.assertEqual(result['副詞'],1.1)
        self.assertEqual(result['名詞（サ変）'],1.0)
        self.assertEqual(result['助詞'],1.0)
        self.assertEqual(result['記号'],1.0)
        self.assertEqual(set(result),set(POS_CATEGORIES))


class PosColorTests(unittest.TestCase):
    def test_colors_default_per_mode(self):
        # 2026-10-13 うにさん：名詞はダークで緑・ごく明るい、ライトで青緑・濃い。
        # 英字と記号はダークでグレー・明るい、ライトでグレー・やや濃い。
        from pos_font import (normalize_colors,has_colors,POS_COLOR_DEFAULTS,
                              POS_COLOR_DEFAULTS_LIGHT,PALETTE_NAMES,current_colors)
        colors=normalize_colors(Settings().get('pos_font_colors'))
        light=normalize_colors(Settings().get('pos_font_colors_light'),False)
        names=lambda c:{k:PALETTE_NAMES[v] for k,v in c.items() if v}
        self.assertEqual(names(colors),{'名詞':'緑・ごく明るい','数詞':'緑・とても明るい',
                                        '英字':'グレー・明るい','記号':'グレー・明るい'})
        self.assertEqual(names(light),{'名詞':'青緑・濃い','数詞':'緑・やや濃い',
                                       '英字':'グレー・やや濃い','記号':'グレー・やや濃い'})
        self.assertEqual(colors,POS_COLOR_DEFAULTS)
        self.assertEqual(light,POS_COLOR_DEFAULTS_LIGHT)
        self.assertEqual(colors['名詞（サ変）'],'');self.assertEqual(light['名詞（サ変）'],'')
        self.assertTrue(has_colors(Settings().get('pos_font_colors')))
        settings=Settings()
        self.assertEqual(current_colors(settings),light)
        settings.set('dark_mode',True)
        self.assertEqual(current_colors(settings),colors)
        # A saved empty string still means "keep the pane's colour".
        self.assertEqual(normalize_colors({'数詞':''})['数詞'],'')

    def test_colors_ignore_invalid_values(self):
        from pos_font import normalize_colors,has_colors,POS_COLOR_DEFAULTS
        colors=normalize_colors({'動詞':'#FF0000','名詞':'red','助詞':'#12345',
                                 '未知':'#000000','副詞':'','数詞':5})
        self.assertEqual(set(colors),set(POS_CATEGORIES))
        self.assertEqual(colors['動詞'],'#ff0000')
        self.assertEqual(colors['名詞'],POS_COLOR_DEFAULTS['名詞'])
        self.assertEqual(colors['助詞'],'')
        self.assertEqual(colors['数詞'],POS_COLOR_DEFAULTS['数詞'])
        self.assertTrue(has_colors(colors))
        data=json.dumps({'pos_font_defaults':'3',
                         'pos_font_colors':{'動詞':'#00b050','名詞':5}},ensure_ascii=False)
        settings=Settings()
        with patch('settings.os.path.exists',return_value=True), \
                patch('builtins.open',mock_open(read_data=data)):
            settings.load('synthetic-settings.json')
        self.assertEqual(settings.get('pos_font_colors')['動詞'],'#00b050')
        self.assertEqual(settings.get('pos_font_colors')['名詞'],POS_COLOR_DEFAULTS['名詞'])

    def test_choosing_a_colour_changes_only_the_current_mode(self):
        # ライトとダークで別管理（2026-10-13 うにさん）。
        import app
        from unittest.mock import Mock
        from pos_font import POS_COLOR_DEFAULTS,POS_COLOR_DEFAULTS_LIGHT
        a=app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.settings=Settings();a._refresh_pos_font_style=Mock();a.settings.save=Mock()
        a._choose_pos_font_colors({'名詞':'#112233'},save=False)
        self.assertEqual(a.settings.get('pos_font_colors_light')['名詞'],'#112233')
        self.assertEqual(a.settings.get('pos_font_colors_light')['記号'],
                         POS_COLOR_DEFAULTS_LIGHT['記号'])
        self.assertEqual(a.settings.get('pos_font_colors'),{})
        a.settings.set('dark_mode',True)
        a._choose_pos_font_colors({'名詞':'#445566'},save=False)
        self.assertEqual(a.settings.get('pos_font_colors')['名詞'],'#445566')
        self.assertEqual(a.settings.get('pos_font_colors')['数詞'],POS_COLOR_DEFAULTS['数詞'])
        self.assertEqual(a.settings.get('pos_font_colors_light')['名詞'],'#112233')

    def test_palette_is_a_hue_by_shade_grid(self):
        from pos_font import PALETTE_ROWS,PALETTE,PALETTE_NAMES,HUES,SHADES
        self.assertEqual(len(PALETTE_ROWS),len(SHADES))
        self.assertTrue(all(len(row)==len(HUES) for row in PALETTE_ROWS))
        self.assertEqual(len(set(PALETTE)),len(PALETTE))
        self.assertTrue(all(len(c)==7 and c.startswith('#') for c in PALETTE))
        self.assertEqual(normalize_colors({'動詞':PALETTE[5]})['動詞'],PALETTE[5])
        self.assertEqual(PALETTE_NAMES[PALETTE_ROWS[0][1]],'赤・ごく明るい')
        self.assertEqual(PALETTE_NAMES[PALETTE_ROWS[1][1]],'赤・とても明るい')
        self.assertEqual(SHADES[0][0],'ごく明るい')
        brightness=lambda c:sum(int(c[i:i+2],16) for i in (1,3,5))
        for column in zip(*PALETTE_ROWS):
            values=[brightness(c) for c in column]
            self.assertEqual(values,sorted(values,reverse=True))
            self.assertEqual(len(set(values)),len(values))

    def test_old_settings_move_untouched_entries_to_the_new_defaults(self):
        from pos_font import POS_COLOR_DEFAULTS
        def load(saved):
            settings=Settings()
            with patch('settings.os.path.exists',return_value=True), \
                    patch('builtins.open',mock_open(read_data=json.dumps(saved,ensure_ascii=False))):
                settings.load('synthetic-settings.json')
            return settings
        # Saved before the change: 数詞 at the old 1.0 and every colour empty.
        old=load({'pos_font_multipliers':{'数詞':1.0,'名詞':1.3},
                  'pos_font_colors':{key:'' for key in POS_CATEGORIES}})
        self.assertEqual(old.get('pos_font_multipliers')['数詞'],1.2)
        self.assertEqual(old.get('pos_font_multipliers')['名詞'],1.3)
        self.assertEqual(old.get('pos_font_colors'),POS_COLOR_DEFAULTS)
        self.assertEqual(old.get('pos_font_defaults'),'3')
        # Chosen values are kept.
        chosen=load({'pos_font_multipliers':{'数詞':1.5},
                     'pos_font_colors':{'記号':'#123456'}})
        self.assertEqual(chosen.get('pos_font_multipliers')['数詞'],1.5)
        self.assertEqual(chosen.get('pos_font_colors')['記号'],'#123456')
        # Saved after the change: an emptied colour stays empty.
        new=load({'pos_font_defaults':'2','pos_font_multipliers':{'数詞':1.0},
                  'pos_font_colors':{'数詞':''}})
        self.assertEqual(new.get('pos_font_multipliers')['数詞'],1.0)
        self.assertEqual(new.get('pos_font_colors')['数詞'],'')
        self.assertEqual(new.get('pos_font_colors_light')['数詞'],'')

    def test_version_2_settings_take_the_new_noun_symbol_and_light_colours(self):
        from pos_font import (POS_COLOR_DEFAULTS,POS_COLOR_DEFAULTS_LIGHT,
                              palette_color,display_color)
        def load(saved):
            settings=Settings()
            with patch('settings.os.path.exists',return_value=True), \
                    patch('builtins.open',mock_open(read_data=json.dumps(saved,ensure_ascii=False))):
                settings.load('synthetic-settings.json')
            return settings
        old=dict(POS_COLOR_DEFAULTS);old.pop('英字')
        old.update({'名詞':'','記号':palette_color('黄','とても明るい'),
                    '動詞':palette_color('赤','ごく明るい')})
        s=load({'pos_font_defaults':'2','pos_font_multipliers':{'名詞':1.0,'動詞':1.3},
                'pos_font_colors':old})
        self.assertEqual(s.get('pos_font_multipliers')['名詞'],1.1)
        self.assertEqual(s.get('pos_font_multipliers')['動詞'],1.3)
        dark=s.get('pos_font_colors');light=s.get('pos_font_colors_light')
        for key in ('名詞','数詞','英字','記号'):
            self.assertEqual(dark[key],POS_COLOR_DEFAULTS[key],key)
            self.assertEqual(light[key],POS_COLOR_DEFAULTS_LIGHT[key],key)
        # A chosen colour stays; light keeps the mirrored colour it showed.
        self.assertEqual(dark['動詞'],palette_color('赤','ごく明るい'))
        self.assertEqual(light['動詞'],palette_color('赤','濃い'))
        self.assertEqual(s.get('pos_font_defaults'),'3')
        # Version 2 colours already chosen as the new dark defaults (うにさん's
        # own file): light takes the new light defaults, not the mirror.
        same=dict(old);same.update({'名詞':POS_COLOR_DEFAULTS['名詞'],
                                    '英字':POS_COLOR_DEFAULTS['英字'],
                                    '記号':POS_COLOR_DEFAULTS['記号']})
        s=load({'pos_font_defaults':'2','pos_font_colors':same})
        for key in ('名詞','数詞','英字','記号'):
            self.assertEqual(s.get('pos_font_colors')[key],POS_COLOR_DEFAULTS[key],key)
            self.assertEqual(s.get('pos_font_colors_light')[key],POS_COLOR_DEFAULTS_LIGHT[key],key)
        self.assertEqual(s.get('pos_font_colors_light')['動詞'],palette_color('赤','濃い'))
        # A noun size chosen as 1.3 stays.
        kept=load({'pos_font_defaults':'2','pos_font_multipliers':{'名詞':1.3}})
        self.assertEqual(kept.get('pos_font_multipliers')['名詞'],1.3)
        # Version 3 files keep both modes as saved.
        three=load({'pos_font_defaults':'3','pos_font_multipliers':{'名詞':1.0},
                    'pos_font_colors':{'名詞':''},'pos_font_colors_light':{'記号':''}})
        self.assertEqual(three.get('pos_font_multipliers')['名詞'],1.0)
        self.assertEqual(three.get('pos_font_colors')['名詞'],'')
        self.assertEqual(three.get('pos_font_colors_light')['記号'],'')
        self.assertEqual(three.get('pos_font_colors_light')['名詞'],
                         POS_COLOR_DEFAULTS_LIGHT['名詞'])

    def test_cursor_row_only_marks_replace_the_old_all_rows_switch(self):
        def load(saved):
            settings=Settings()
            with patch('settings.os.path.exists',return_value=True), \
                    patch('builtins.open',mock_open(read_data=json.dumps(saved))):
                settings.load('synthetic-settings.json')
            return settings.get('ctrl_boundaries_cursor_row_only')
        self.assertIs(Settings().get('ctrl_boundaries_cursor_row_only'),True)
        self.assertIs(load({'ctrl_boundaries_all_rows':True}),False)
        self.assertIs(load({'ctrl_boundaries_all_rows':False}),True)
        self.assertIs(load({'ctrl_boundaries_all_rows':True,
                            'ctrl_boundaries_cursor_row_only':True}),True)
        self.assertNotIn('ctrl_boundaries_all_rows',Settings().values)

    def test_ctrl_marks_start_on_and_old_settings_turn_them_on_once(self):
        # 印は Ctrl を押している間だけ出るので既定オン。前の版で保存された
        # オフも一度オンにする。新しい版で保存した「オフ」は残す（2026-10-12 うにさん）。
        def load(saved):
            settings=Settings()
            with patch('settings.os.path.exists',return_value=True), \
                    patch('builtins.open',mock_open(read_data=json.dumps(saved))):
                settings.load('synthetic-settings.json')
            return (settings.get('show_ctrl_boundaries'),
                    settings.get('ctrl_boundaries_cursor_row_only'))
        self.assertIs(Settings().get('show_ctrl_boundaries'),True)
        for old in ({},{'ctrl_boundaries_defaults':'2'}):
            self.assertEqual(load({'show_ctrl_boundaries':False,**old,
                                   'ctrl_boundaries_cursor_row_only':False}),(True,False))
        self.assertEqual(load({'show_ctrl_boundaries':False,'ctrl_boundaries_defaults':'3',
                               'ctrl_boundaries_cursor_row_only':False}),(False,False))

    def test_light_mode_mirrors_the_shade_of_chosen_colours(self):
        # 2026-10-12 うにさん：ライトとダークで色を切り替える。ダーク向けの
        # 明るい色は、ライトでは同じ色合いの濃い色で出す
        from pos_font import display_color, palette_color, PALETTE
        pale=palette_color('黄','とても明るい')
        self.assertEqual(display_color(pale,True),pale)
        self.assertEqual(display_color(pale,False),palette_color('黄','やや濃い'))
        self.assertEqual(display_color(palette_color('緑','ごく明るい'),False),
                         palette_color('緑','濃い'))
        self.assertEqual(display_color('',False),'')
        for color in PALETTE:
            self.assertEqual(display_color(display_color(color,False),False),color)
        # A colour outside the palette: lightness mirrored, same hue.
        self.assertEqual(display_color('#ffffff',False),'#000000')

if __name__=='__main__':
    unittest.main()
