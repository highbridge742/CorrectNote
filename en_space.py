"""
英文の**半角スペースの入れ忘れ**を直す（項目48-ES・2026-10-14）。

うにさんの指定（2026-10-13）:

    英文の半角スペース入れ忘れを補正する。スペースを入れずに英文が
    成立している場合は入れない。隣接キーや文字の順番間違えの補正の
    あとにスペース補正を考える。

順番:

  1. 語としてそのまま知っている綴り（英語の品詞辞書 `en_pos`・
     英単語の種 `seed_english`・**固有名詞と5字以下の語の名簿
     `seed_english_names`**・本人が2回以上書いた語）は**触らない**。
     `GitHub` `iPhone` のように途中に大文字がある語、`HTML` のような
     大文字だけの語、数字や `. _ - @ / : '` がくっついた並び
     （識別子・URL・パス・短縮形）も触らない。
  2. **隣接キー・文字の順番の直しを先に考える。** 6字以上は
     `loanword.fix_english_word` が先に済ませている（corrector の
     英語の段でこちらより前に走る）。ここでは、
       - 1字の隣接キー違い／隣り合う2字の入れ替えで知っている語に
         届くなら、**スペースは考えない**（分けない）。
       - そのうち**入れ替え**で届く先が機能語ただ1つなら、それに直す
         （`teh → the`・`adn → and`・`thier → their`）。隣接キー違いは
         短い語だと紛れが多いので、直さずに手を引くだけにする。
  3. それでも知らない綴りなら、**知っている語2つ（だめなら3つ）に
     ちょうど1通りに分けられ、その並びが英語の語順として成り立つ**
     ときだけスペースを入れる。
       - 1字の語は `a` と `I` だけ。2字の語は名簿（`_SHORT_WORDS`）だけ。
       - 分けた語のどれかが機能語（`_FUNCTION_WORDS`・冠詞・前置詞・
         代名詞・助動詞など）であること。スペースの入れ忘れは
         ほぼ機能語の前後で起きる。これが無いと `facebook → face book`
         `playstation → play station` のような名前や合成語を割る。
       - **語順の門**（`_pair_ok`）。機能語どうしは、主語＋助動詞
         （人称と数が合うもの）・助動詞＋主語・前置詞＋限定詞のように
         **英語として並ぶ組だけ**（`This is` `do you` `of the`）。
         `is is` `he he` `to by` `an on` `am in` のような並びは割らない。
         冠詞 `a／an` は後ろの語の頭の音と合い、機能語には掛からない
         （`Avery → a very` を割らない）。尻の冠詞は、冠詞が掛かる語が
         後ろに続くときだけ（`quitea pen → quite a pen`）。
       - **`I` の頭**は、I の後ろに来る語の名簿（`_AFTER_I`）にある
         ときだけ（`Iam` `Ihave` `Iwant`）。`Iran` `Ivan` `Ion` を割らない。
       - **文の途中の大文字の語は固有名詞**とみなして割らない
         （`met Justin`）。文頭（半角の区間の頭・`.!?` の後ろ）の大文字は
         文の書き出しなので、頭の語が文を始められる語のときだけ割る
         （`Thisis` `Thankyou` `Attachedis`。`Passat` `Costas` は割らない）。
       - 大文字は書いた形をそのまま残す（`Thisis → This is`）。
  4. **英文の中でだけ**直す。ローマ字の打ちかけ（`shoruiga`）を
     割らないよう、同じ半角の区間にほかの知っている英単語があるか、
     行が半角だけのときに限る。ローマ字として全部読める並び
     （`howare` `anata`）は、知っている語が2つ以上並び、かつ
     かなに読み直して日本語にならないときだけ見る。
     日本語の中の1語でも、**機能語だけにちょうど分かれる**並び
     （`Thisis` `Itwas`）は直す。
  5. **コードは見ない。** `=` `[]` `{}` `<>` `;` `_` `#` バッククォートなどが
     混じる区間、
     関数呼び出しの形（`isinstance(`）は英文ではない。`is＋名詞`
     （isfile）・`名詞＋no/by/in`（lineno・groupby・mixin）のような
     名前の組み立ても割らない（`_identifier_shape`）。

よそのやり方（2026-10-14・うにさんの指定で調べた）:
  - SymSpell（LookupCompound）は、綴りの直しとスペースの入れ忘れを
    いっしょに扱い、分け方は語の頻度（ナイーブベイズ）と2語の並びの
    辞書で選ぶ。**直しを先に考えてから分ける**のはここと同じ。
    頻度の表は持たないので、代わりに語順の門（上の 3）を書き下した。
  - Hunspell は `REP ^alot$ a_lot` のように、よくある入れ忘れを
    辞書に並びごと持つ。`a lot` `at least` などは分け方で届く。
  - aspell の run-together は 3字未満の部品を認めない。ここも
    1〜2字は名簿の語だけ。
  - 固有名詞は SCOWL の大文字の見出し語をそのまま名簿にした
    （`seed_english_names.py`）。頻出語6万を1語ずつ当てて、
    `Justin → Just in` `Norway → Nor way` `meat → me at` と割った
    278語のうち 156語がこれで塞がる。残りは語順の門で塞いだ。

測り方（2026-10-14・第2版）:
  - Python 3.13 標準ライブラリ＋ GPL などの英文 25万行（空行を除く）に
    当てて、割ったのは 5か所（`mailfrom` `headersonly`——どちらも
    引数の名前が docstring の地の文に出たもの）。
  - 頻出語 6万（wordfreq）を 4つの枠に入れて1語ずつ当てると、第1版は
    278語を割った（`Justin` `Norway` `meat` `Iran` …）。第2版は 35語で、
    どれも直したい並び（`ofthe` `teh` `thier` `iam` `noone` `thankyou`）か
    小文字の略語（`cna → can` `hsa → has`）。
  - うにさんの日本語の材料（誤字集・保留集・自然文・日常・規則・かな文・
    fpcheck）は 1行も変わらない。

短縮形（`I'm` `don't`）は、アポストロフィの前後に付いた並びを
触らないことで**ひとかたまりのまま**残す（区切りの扱いは表示側の
品詞判定と合わせて決める・未決）。

戻り値の形は `loanword.find_miskeyed_english` と同じ
`[(開始, 終了, 直した表記), ...]`。
"""
import re

_WORD_RE = re.compile(r'[A-Za-z]+')
# くっついていたら英単語として扱わない記号（loanword._GLUED_SYMBOLS に
# 短縮形の ' と ’ を足したもの）
_GLUED = "._-@/:'’\\#&+=%$~*"

# 1字・2字で語として認める綴り（これ以外の短い片は分け先にしない）
_SHORT_WORDS = frozenset((
    'a', 'i',
    'am', 'an', 'as', 'at', 'be', 'by', 'do', 'go', 'he', 'if',
    'in', 'is', 'it', 'me', 'my', 'no', 'of', 'ok', 'on', 'or',
    'so', 'to', 'up', 'us', 'we',
))

# ---- 機能語を役目ごとに分けた名簿（語順の門が見る）----
_SUBJ_3S = frozenset(('he', 'she', 'it', 'this', 'that', 'there', 'here',
                      'who', 'what', 'which'))          # 三人称単数の主語
_SUBJ_PL = frozenset(('we', 'you', 'they', 'these', 'those'))
_SUBJ = _SUBJ_3S | _SUBJ_PL | frozenset(('i',))
_OBJ = frozenset(('me', 'him', 'her', 'us', 'them'))   # 目的語の代名詞
_POSS = frozenset(('my', 'your', 'our', 'their', 'his', 'her', 'its'))
_ARTICLES = frozenset(('a', 'an', 'the'))
_DET = _ARTICLES | _POSS | frozenset((
    'this', 'that', 'these', 'those', 'some', 'any', 'each', 'every',
    'no', 'all', 'other', 'such'))
_MODAL = frozenset(('can', 'could', 'will', 'would', 'shall', 'should',
                    'may', 'might', 'must'))
_AUX_3S = frozenset(('is', 'was', 'has', 'does', 'did', 'had')) | _MODAL
_AUX_PL = frozenset(('are', 'were', 'have', 'do', 'did', 'had')) | _MODAL
_AUX_I = frozenset(('am', 'was', 'have', 'do', 'did', 'had')) | _MODAL
_AUX_FINITE = _AUX_3S | _AUX_PL | _AUX_I
_AUX = _AUX_FINITE | frozenset(('be', 'been', 'being'))
_PREP = frozenset(('in', 'on', 'at', 'to', 'for', 'of', 'by', 'with',
                   'from', 'into', 'onto', 'upon', 'about', 'after',
                   'than', 'as', 'up', 'out'))
_CONJ = frozenset(('and', 'or', 'but', 'nor', 'so', 'if', 'yet', 'while',
                   'when', 'where', 'because', 'that'))
_WH = frozenset(('what', 'who', 'whom', 'how', 'why', 'when', 'where',
                 'which', 'whose'))
_ADV = frozenset(('not', 'too', 'very', 'just', 'also', 'then', 'now',
                  'never', 'always', 'still', 'only', 'even', 'really',
                  'here', 'there'))

# 分けた語のどれかがこれであること（スペースの入れ忘れの手掛かり）
_FUNCTION_WORDS = frozenset(
    _SUBJ | _OBJ | _DET | _AUX | _PREP | _CONJ | _WH | _ADV)

# `I` の後ろに来る語（`Iam` `Ihave` `Iwant`）。これ以外は割らない
# （`Iran` `Ivan` `Ion` `Isis` `Ito` は名前）
_AFTER_I = frozenset('''
am was will would can could have had do did want need like love think
know see saw go went got get hope feel felt said say use used make made
take took try tried ask asked tell told call called read wrote write
work live look looked found find mean meant miss wish guess agree also
just really never always still shall should might must may wonder
believe remember forgot forget understand suppose hate prefer hear heard
play played watch watched eat ate drink buy bought sent send gave give
keep kept left lost learn learned met meet moved move paid pay put run
sat sit slept sleep spent spend stay stayed stood stand talk talked
taught teach thought turn turned wait waited walk walked wake woke wear
wore win won worked worry apologize appreciate assume bet care check
come came consider decided decide doubt expect explain finish finished
forgive imagine join joined laughed laugh lived mentioned noticed notice
open opened owe own pass passed plan planned promise propose realize
realized recall receive received recommend refuse regret reply replied
return returned seem share shared show showed speak spoke start started
stop stopped study studied suggest support swear thank trust visited
visit wanted needed liked loved hoped knew wished guessed wondered
believed remembered understood supposed hated preferred agreed missed
too and or myself personally honestly usually often sometimes already
actually totally definitely probably certainly rarely recently finally
simply only even now once first
'''.split())

# 文頭（大文字で書き出した語）で、頭の語になれる内容語
# （機能語と `I` は無条件）。名前になりやすい語は入れない
# （`well`＝Welland・`new`＝Newsome・`red`＝Redis）
_STARTERS = frozenset('''
please thank thanks welcome let see hope nice good glad happy sorry
looking look come take keep make give send tell call check try feel dear
hello hi hey yes best kind many much time today tomorrow yesterday first
next last people everyone someone anyone nothing something everything
anything maybe perhaps probably actually finally anyway however
therefore since although though unless until before during once whether
another both either neither none most more less often sometimes usually
again long great love life god ok okay right sure fine wow cheers
regards attached enclosed following regarding according due back done
got get go going wait stop start open close click press select choose
enter type run read write note remember forget imagine consider suppose
guess think know believe wish want need like say said ask question
problem name email sounds seems looks
'''.split())

# 識別子の頭によく付く語（isfile・onerror・infile・todata・theweek）。
# 機能語の頭＋内容語でも、これらは割らない
_ID_HEADS = frozenset(('is', 'has', 'in', 'on', 'to', 'from', 'my', 'no',
                       'at', 'any', 'some', 'this', 'the', 'out',
                       'get', 'set', 'do', 'all', 'by', 'as'))
# 識別子の尻によく付く語（lineno・fileno・groupby・sortby・mixin）。
# `it` `up` `on` `of` `us` は外した（timeit・builtin は名前の名簿へ。
# `takeit` `wakeup` `comeon` `kindof` `tellus` を直すため・2026-10-14）。
# `in` は残す——g を落とした話し言葉（lookin・talkin・workin）が
# 頻出語に 60 語あり、`look in` と割ってしまうため
_ID_TAILS = frozenset(('no', 'by', 'in'))

# 尻の `us` を許す頭（`tellus` `contactus` `joinus`）。それ以外は
# ラテン語・名前（Markus・Maximus・Loftus・erectus）
_US_HEADS = frozenset('''
tell let contact join help give show email follow visit call send ask
thank meet see keep make take bring leave teach text love trust forgive
excuse remind pay allow told gave sent asked helped showed left met saw
made kept brought taught reminded paid allowed with without among between
'''.split())

# 尻の冠詞（`quitea` `isa` `needa`）を許す内容語の頭
_ART_HEADS = frozenset('''
got get need want quite like make made take took give gave find found buy
see saw use add put read write wrote sent send bring brought ask asked
tell told show open start create build pick choose chose order book rent
hire call wait spend spent cost pay paid win won become became seem seems
such half once twice what
'''.split())

# 頭の冠詞 `a／an` の後ろに来られない語（動詞・副詞。`Aran → a ran`
# `Arun → a run` を割らない）
_NOT_AFTER_ARTICLE = frozenset('''
go ran run did made got said went saw came took gave knew told felt kept
left lost met paid put read sat set sent sold spent stood won wrote seem
mean does done goes gone been were are was has have had very much many
more most also just again ago away back down off out over lain laid lied
seen shown thrown risen sworn flown blown akin alike alive alone aware
asleep awake ashamed afraid aloof ajar amiss askew agog afloat ablaze
afire
'''.split())

# `so` の後ろの内容語（`somuch` `sofar`）。それ以外の so＋内容語は
# 名前（Socrates・Soto）
_SO_TAILS = frozenset('''
much many far long good bad sorry happy glad nice cool great sad true
hard easy fast slow big small little few late early close high low quick
quickly funny cute pretty hot cold warm sweet tired busy excited proud
lucky
'''.split())

# 疑問詞＋内容語で割ってよい組（`howmuch` `whattime`）
_WH_TAILS = {
    'how': frozenset(('much', 'many', 'long', 'far', 'often', 'old',
                      'soon', 'come', 'about')),
    'what': frozenset(('time', 'kind', 'else', 'about')),
    'who': frozenset(('else',)),
    'where': frozenset(('else',)),
    'which': frozenset(('one', 'way')),
}

# `to`＋動詞（`tobe` `tosee` `togo`）。`to`＋名詞は識別子（tolist・tofile）
_TO_VERBS = frozenset('''
be been have do see go get make take find know use help work read write
start stop keep give come say tell ask try learn play run move live look
think feel call put meet pay buy sell win lose send show bring hold turn
stand walk talk wait watch open close build check change create remove
delete update enter leave join sign let mean need want love like hate
hear eat drink sleep cook clean wash drive fly swim sing dance draw paint
teach study speak understand remember forget believe decide continue
finish happen become begin grow die fight save spend cut break fix fall
rise fill fit follow lead carry catch cover cross drop pick pull push
reach return ride roll search seek serve shake share shoot shut sit smile
suggest support throw touch travel visit vote wake wear wish worry
explain improve install download upload click type print copy paste test
debug deploy compile import export edit
'''.split())

# 品詞辞書が無いときの短い語の控え（en_pos・seed_english_names があれば
# そちらと合わせる）。5字以下だけ。6字以上は seed_english が持っている。
_FALLBACK_SHORT = frozenset('''
able about above act add after again age ago air all also always and
animal answer any apple are area arm art ask away baby back bad bag
ball bank base bed been before begin best big bird black blue boat
body book both box boy bread break bring brown build bus busy but buy
call came can car card care carry case cat catch cause chair check
child city class clean clear close cold come cook cool copy cost
could count cover cry cup cut dark data day dear deep did die dish
does dog done door down draw dream dress drink drive drop dry during
each early earth east easy eat egg end enjoy enough even ever every
eye face fact fall far farm fast fat feel feet few file fill find
fine fire first fish five fix floor fly food foot for form found four
free fresh from front fruit full fun game gave get girl give glad
glass goes going gold gone good got great green group grow had hair
half hall hand happy hard has hat have head hear heart heavy help
her here high hill him his hit hold hole home hope horse hot hour
house how huge idea image inch into its job join just keep key kind
king knew know lady land large last late laugh learn least leave
left leg less let letter life light like line list little live long
look lose lost lot loud love low made main make man many map mark
may mean meet men milk mind miss money month more most mother move
much music must name near neck need never new news next nice night
nine none nor north nose not note now number off often old once one
only open order other our out over own page paint paper park part
party pass past pay pen people pick piece place plan plant play
please point poor post power press print put question quick quiet
rain ran read ready real red rest rich ride right ring rise river
road rock room round rule run sad safe said sale same save saw say
school sea seat see seem seen self sell send set seven shall she ship
shoe shop short should show shut sick side sign since sing sir sit
six size sky sleep slow small smile snow soft some son song soon
sorry sound south space speak speed spend stand star start state
stay step still stop store story street study such sun sure swim
table take talk tall tea teach team tell ten test than thank that
the their them then there these they thing think this those three
time today told too took top total touch town tree true try turn
two type under until upon use used user very view visit voice wait
walk wall want warm was wash watch water way wear week well went were
west what when where which while white who whole why wide wife will
win wind window wish with woman women word words work world would
write wrong year yes yet you young your yours
again agree alone along among begin being below cannot catch cheap
child clock dance doing drawn eight eaten every exact extra field
fight funny given goods guess heard hours human least level lunch
maybe meant money mouth movie never ought owner plane radio reach
river scene sheet shirt skill sleep sport stand store sweet taken
teeth thick third three throw tired train truck twice uncle usual
voice waste woman worry worse worth young
abuse adult agent ahead alarm alert alike alive allow aloud alpha
apart arise aside asset audio avoid awake award aware awful basic
begun below blank blind block board bonus brief broad brush chain
chart chase chief civil claim click climb coach cream crowd daily
debug delay depth digit dirty doubt draft enter equal error event
exist faith false fancy fault final flash fleet focus force frame
fully giant grade grand grant grape graph grass guard guide habit
hello hobby hurry ideal index inner input issue items joint judge
label large later layer legal limit local logic login lucky major
match media metal minor mixed model motor mount naked nerve noise
novel nurse occur ocean offer older other outer panel phase phone
photo pilot pitch pizza plain plate pound price pride prime prior
proof proud quiet quite quote raise range rapid ratio refer relax
reply reset rough route royal scale scope score sense serve setup
shape share sharp shift shock shoot short sight silly since skirt
slide smart solid solve sorry spare speak spell split staff stage
start steal steel stick stock stone storm style sugar suite super
table taste theme thing thumb tight title token topic tough tower
track trade trail treat trend trial trick trust truth twist union
unity upper upset urban usage valid value video virus vital vivid
whose wrist yield
exit abuse act add ago aid aim art bit box bug buy cap cow cry cue dad
due dry ear eye fan fee fit fix fog fox fun gap gas god gun guy hat
hit hug ice ill ink jam jar jet joy key kid kit lab lap law lay leg
lid lie lip log mad mix mom mud net nod nut oak odd oil pad pan pet
pie pin pop pot pub rat raw ray rib rid rod row rub sad sex shy sin
sip sir sky spy sue sum tap tax tie tip toe ton toy van war web wet
win wit zoo
meat goat awe acre odor lien tsar acme fete dodo toon hehe anon atop
afar anew onus abed amok awash afoot amiss aback ado taxi tapas lapis
nous penis meme mommy bet pat cot tis fro ion bene anno spilt aries
strat bleu entre garde mayan amor amore areal ashy abut ajar akin agog
afire aloft aloof await atone amass avail avert abide abode abet ode
odes heme tome fora doin goin bein nothin somethin gonna wanna gotta
kinda sorta dunno lemme gimme outta yall yeah yep nope okay noway
ah ahs oh ooh hmm umm uh um eh aw ha yo ya
'''.split())

# アポストロフィを落とした短縮形（`arent` `dont` `werent`）。
# `a rent` `we rent` と割らない。直すのは短縮形の側の仕事（未決）
_APOSTROPHE_LESS = frozenset('''
arent isnt wasnt werent dont doesnt didnt cant couldnt wont wouldnt
shouldnt mustnt neednt havent hasnt hadnt aint im ive youre youve youll
youd theyre theyve theyll theyd weve well wed hes shes itll thats whats
theres heres wheres whos hows lets oclock yall
'''.split())

# 書いた人の意図が分かる名前・製品名・コードの名前と、名簿に無い語
# （頻出語6万を当てて見つけたもの・2026-10-14）
_NAMES = frozenset((
    'init', 'todo', 'async', 'args', 'kwargs', 'stdin', 'stdout', 'stderr',
    'atexit', 'readme', 'goto', 'runas', 'tolist', 'todict',
    'youtube', 'youtuber', 'youtubers', 'github', 'gitlab', 'facebook',
    'linkedin', 'wordpress', 'onedrive', 'dropbox', 'playstation',
    'photoshop', 'powerpoint', 'onenote', 'whatsapp', 'wechat', 'chatgpt',
    'iphone', 'ipad', 'macbook', 'airpods', 'javascript', 'typescript',
    'nodejs', 'pytorch', 'tensorflow', 'gmail', 'hotmail', 'outlook',
    'instagram', 'tiktok', 'netflix', 'spotify', 'paypal', 'airbnb',
    'firefox', 'thunderbird', 'correctnote', 'notion', 'figma', 'slack',
    'discord', 'onepiece', 'asus', 'aws', 'hwy', 'btu', 'ayn',
    'hasan', 'usman', 'amit', 'amin', 'arun', 'noam', 'imran', 'iman',
    'alain', 'addis', 'artis', 'asme', 'orme', 'cotto', 'cueto', 'aslam',
    'aviva', 'anova', 'asics', 'anakin', 'loomis', 'landis', 'gillis',
    'mattis', 'adamson', 'costas', 'mansour', 'notting', 'mayberry',
    'haddad', 'hadfield', 'farhad', 'passat', 'newsome',
    'shemale', 'shoutout', 'jihadi', 'jihadis',
    'timeit', 'mixin', 'mixins', 'builtin', 'builtins', 'sizeof', 'typeof',
    'instanceof', 'addon', 'addons', 'logon', 'signon', 'fixup', 'dedup',
    'mailto', 'readonly', 'endswith', 'startswith', 'whatis', 'getattr',
    'setattr', 'hasattr', 'isinstance', 'tostring', 'tolower', 'toupper',
    'groupon', 'menon', 'manon', 'shimon', 'petit', 'godin', 'followon',
))

# よくあるスペースの入れ忘れで、辞書に語として載っている・頭が識別子の
# 形のために門で止まるもの。**辞書より先に**この形に直す（Hunspell が
# `REP ^alot$ a_lot` と辞書に並びごと持つのと同じ考え・2026-10-14）
_FORCE_SPLIT = {
    'thankyou': 'thank you', 'noone': 'no one', 'nevermind': 'never mind',
    'incase': 'in case', 'aswell': 'as well', 'infact': 'in fact',
    'infront': 'in front', 'atleast': 'at least', 'allright': 'all right',
    'ofcourse': 'of course', 'inspite': 'in spite', 'eventhough': 'even though',
    'inorder': 'in order', 'ontime': 'on time', 'athome': 'at home',
    'atwork': 'at work', 'atonce': 'at once', 'assoon': 'as soon',
    'aslong': 'as long', 'alittle': 'a little', 'afew': 'a few',
    # 2026-10-16: wordfreq ではよく書かれる綴りなので、打ち違いの道
    # （en_typo）は「書いたとおり」とみなす。ここで名指しで分ける
    'alot': 'a lot',
}

# 英字の隣接（入れ替え・1字違いで届く語を探すとき）。表は `keyboard_layout`
# が持ち、配列・形の選択（項目48-KB）で差し替わる。既定は QWERTY のまま。
import keyboard_layout as _KEYBOARD
_QWERTY_POS = {}
_QWERTY_NEAR = frozenset()


def _rebuild_keyboard():
    global _QWERTY_POS, _QWERTY_NEAR
    _QWERTY_POS = dict(_KEYBOARD.letter_positions())
    _QWERTY_NEAR = _KEYBOARD.letter_near_pairs()


_KEYBOARD.on_change(_rebuild_keyboard)


def _near(a, b):
    return (a, b) in _QWERTY_NEAR


_LEX_CACHE = None
_TOUCH_CACHE = None
_COMMON = frozenset(_FALLBACK_SHORT | _SHORT_WORDS | _FUNCTION_WORDS)


def _names_module():
    try:
        import seed_english_names
        return seed_english_names
    except Exception:
        return None


def _base_lexicon():
    """
    **分け先**になれる語（小文字）。直し先の英単語の種（SCOWL size 35・
    6字以上）＋5字以下のふつうの語（`seed_english_names.SHORT_WORDS`）
    ＋短い語の控え。

    品詞辞書 `en_pos` は**入れない**（触らない側だけ）。分け先は狭く、
    触らない側は広く（項目48-BK と同じ考え）。品詞辞書に名前や外来語が
    混じると `adios → a dios` `walther → walt her` と割る（偽の辞書で実測）。
    """
    global _LEX_CACHE
    if _LEX_CACHE is not None:
        return _LEX_CACHE
    out = set(_COMMON)
    try:
        import loanword
        out |= set(loanword._english_seed())
    except Exception:
        pass
    names = _names_module()
    if names is not None:
        out |= set(getattr(names, 'SHORT_WORDS', ()))
    _LEX_CACHE = frozenset(out)
    return _LEX_CACHE


def _pos_words():
    """品詞辞書 `en_pos` の語（小文字）。無ければ空。**触らない側だけ**に使う。"""
    try:
        import en_pos
        if en_pos.available():
            return frozenset(w.lower() for w in en_pos.words())
    except Exception:
        pass
    return frozenset()


_INFLECTIONS = (('ies', 'y'), ('ied', 'y'), ('ying', 'ie'), ('ing', 'e'),
                ('ing', ''), ('es', ''), ('ed', 'e'), ('ed', ''),
                ('s', ''), ('d', ''), ('ers', 'e'), ('ers', ''),
                ('er', 'e'), ('er', ''), ('ly', ''), ('ly', 'e'),
                ('ness', ''), ('ment', ''), ('able', ''), ('able', 'e'))


class _Union:
    """いくつかの集合を合わせて引く（写しを作らない）。"""
    def __init__(self, *sets):
        self.sets = sets

    def __contains__(self, key):
        return any(key in st for st in self.sets)


def _touch_lexicon():
    """
    **触らない**語（小文字）。分け先より広い。

    品詞辞書 `en_pos` の全語、`seed_english` の全語（SCOWL size 70）、
    固有名詞の名簿（`seed_english_names.PROPER_NAMES`）、
    アポストロフィを落とした短縮形も見る。語形変化から
    引き戻した語幹（`inputs → input`）は `_stem_supported` が
    その場で見る（236,938語を前もって展開すると、最初の英字の行で
    2秒止まるため）。
    """
    global _TOUCH_CACHE
    if _TOUCH_CACHE is not None:
        return _TOUCH_CACHE
    try:
        import loanword
        seed_all = loanword._english_seed_all()
    except Exception:
        seed_all = frozenset()
    names = _names_module()
    proper = (frozenset(getattr(names, 'PROPER_NAMES', ()))
              if names is not None else frozenset())
    _TOUCH_CACHE = _Union(_base_lexicon(), _pos_words(), seed_all, proper,
                          _NAMES, _APOSTROPHE_LESS)
    return _TOUCH_CACHE


def _stem_supported(key, touch):
    """
    key が、知っている語の**語幹**として引き戻せるか。

    語形が2つ以上あるか（複数形どうし `tother／tothers` は1つと
    数える）、4字以上で複数形 `key + s` があるときだけ認める。
    `tother → tothe` のような1語だけの偽の語幹で、`tothe` を
    正しい語と見なさないため。分け先には使わない。
    """
    if len(key) < 3:
        return False
    forms = set()
    for suf, rep in _INFLECTIONS:
        if rep and not key.endswith(rep):
            continue
        form = (key[:-len(rep)] if rep else key) + suf
        if form != key and form in touch:
            forms.add(form)
    base = {f for f in forms if not (f.endswith('s') and f[:-1] in forms)}
    return len(base) >= 2 or (len(key) >= 4 and key + 's' in forms)


def _known(key, store):
    """そのまま知っている綴りか（小文字の key）。"""
    touch = _touch_lexicon()
    if key in touch or _stem_supported(key, touch):
        return True
    # 知っている語の語形変化（tried・lots・exits・youtubers）も知っている綴り
    for suf, rep in _INFLECTIONS:
        if key.endswith(suf) and len(key) - len(suf) + len(rep) >= 3:
            if key[:-len(suf)] + rep in touch:
                return True
    if store is None:
        return False
    try:
        import loanword
        return loanword._english_count(store, key) >= 2
    except Exception:
        return False


def _part_ok(part, lex):
    """
    分けた先の1語になれるか。

    3字までの語は、控えのふつうの語だけ（品詞辞書の短い語には
    略語や語の切れ端が混じる。`uname → una me`・`ustar → us tar`
    を避ける）。
    """
    if len(part) <= 2:
        return part in _SHORT_WORDS
    if len(part) == 3:
        return part in _COMMON
    return part in lex


def _romaji_like(key):
    """ローマ字として全部読めるか（anata・shoruiga）。"""
    try:
        from halfwidth import romaji_to_kana
    except Exception:
        return False
    kana, _c, _t = romaji_to_kana(key)
    return not any('a' <= ch <= 'z' for ch in kana)


def _one_edit_words(key, lex, keep_head=False):
    """
    (入れ替えで届く語の集合, 隣接キー1字違いで届く語の集合)

    keep_head: 頭の1字は動かさない（大文字で書き始めた語。
    `Iam` を `aim` にしない——大文字はそこが語の頭だという印）。
    """
    swaps, nears = set(), set()
    for i in range(1 if keep_head else 0, len(key) - 1):
        if key[i] != key[i + 1]:
            cand = key[:i] + key[i + 1] + key[i] + key[i + 2:]
            if _part_ok(cand, lex):
                swaps.add(cand)
    for i, ch in enumerate(key):
        if keep_head and i == 0:
            continue
        for alt in _QWERTY_POS:
            if _near(ch, alt):
                cand = key[:i] + alt + key[i + 1:]
                if _part_ok(cand, lex):
                    nears.add(cand)
    return swaps, nears


def _splits(key, lex, parts):
    """key を parts 個の知っている語に分ける仕方をすべて返す。"""
    if parts == 1:
        return [[key]] if _part_ok(key, lex) else []
    out = []
    for i in range(1, len(key)):
        head = key[:i]
        if not _part_ok(head, lex):
            continue
        for rest in _splits(key[i:], lex, parts - 1):
            out.append([head] + rest)
    return out


def _identifier_shape(parts):
    """
    **プログラムの名前の組み立て**に見える分け方か（項目48-ES）。

    スペースの入れ忘れは、機能語どうし（`tothe` `isin`）か、
    内容語の後ろに機能語（`wantto` `seeyou`）の形がほとんど。
    `is＋名詞`（isfile）・`on＋名詞`（onerror）のような
    **機能語の頭＋内容語**と、`名詞＋no/by/in/it`（lineno・groupby・
    mixin・timeit）は、Python の標準ライブラリの英文を全部当てると
    名前ばかりだった（実測・2026-10-14）。割らない。
    """
    if len(parts) != 2:
        return False
    head, tail = parts
    if head in _ID_HEADS and tail not in _FUNCTION_WORDS:
        return True
    if tail in _ID_TAILS and head not in _FUNCTION_WORDS:
        return True
    return False


# ---- 語順の門 ----

def _aux_pair_ok(h, t):
    """助動詞 h の後ろに機能語 t が来られるか（`is it` `do you` `has been`）。"""
    if t == 'not':
        return True
    if t in _SUBJ:
        if h in ('is', 'was', 'has', 'does'):
            return t in _SUBJ_3S
        if h == 'am':
            return t == 'i'
        if h in ('are', 'were', 'have', 'do'):
            return t in _SUBJ_PL or t == 'i'
        return True                     # did・had・can・will…は何でも
    if h in ('do', 'does', 'did') and t in ('it', 'so'):
        return True                     # do it・do so
    if t in _DET:
        if h == 'am' or t == 'no':
            return False                # am a・do no
        return not (t == 'all' and h in _MODAL)      # Mayall
    if t == 'been':
        return h in ('has', 'have', 'had')
    if t in ('be', 'have'):
        return h in _MODAL
    if t == 'being':
        return h in ('is', 'was', 'are', 'were', 'am')
    if t in ('also', 'just', 'still', 'never', 'always', 'only', 'even',
             'really', 'now', 'then'):
        return True
    if t in ('so', 'too', 'here', 'there'):
        return h not in _MODAL
    if t in ('to', 'in', 'on', 'at', 'for', 'of', 'by', 'with', 'from',
             'about', 'up', 'out', 'as'):
        return h in ('is', 'was', 'are', 'were', 'am', 'has', 'have', 'had')
    return False


def _pair_ok(h, t):
    """
    機能語 h ＋ 機能語 t が、英語の語順として並ぶ組か。

    `This is` `do you` `of the` `want to`〔機能語側〕のような組だけを
    認める。`is is` `he he` `to by` `am in` `an on` は認めない。
    1語がいくつかの役目を持つ（that・her・as・so）ので、どの役目でも
    成り立てばよい。
    """
    if h == t:
        return False
    # 主語＋助動詞（人称・数を合わせる）
    if h == 'i' and (t in _AUX_I or t in _AFTER_I):
        return True
    if h in _SUBJ_3S and t in _AUX_3S:
        return True
    if h in _SUBJ_PL and t in _AUX_PL:
        return True
    if h in _SUBJ and t in ('also', 'just', 'still', 'never', 'always',
                            'too', 'and', 'or', 'but'):
        return True
    # 疑問詞
    if h in _WH and (t in _AUX_FINITE or t in _DET or t in _SUBJ
                     or t in ('to', 'about', 'not', 'if')):
        return True
    # 助動詞
    if h in _AUX_FINITE and _aux_pair_ok(h, t):
        return True
    if h in ('be', 'been', 'being') and (
            (t in _PREP and t not in ('than', 'as', 'after', 'up', 'out',
                                      'to'))
            or t in _DET or (t in _ADV and t != 'not')):
        return True
    # 前置詞
    if h in _PREP:
        if h == 'to' and t in ('be', 'been', 'have', 'do'):
            return True
        if h in ('up', 'out'):
            if (h, t) in (('up', 'to'), ('out', 'of')):
                return True
            if (t in _DET or t in _OBJ
                    or t in ('it', 'you', 'there', 'here', 'with', 'for',
                             'on', 'in', 'at', 'and', 'or', 'what')):
                return True
        elif h == 'as':
            if (t in _DET or t in _SUBJ or t in _OBJ or t in _AUX_FINITE
                    or t in ('if', 'to', 'of', 'in', 'for', 'with', 'from',
                             'on', 'at')):
                return True
        elif h == 'than':
            if (t in _DET or t in _SUBJ or t in _OBJ or t in _AUX_FINITE
                    or t in ('not', 'just')):
                return True
        else:
            if (t in _DET or t in _OBJ
                    or t in ('it', 'you', 'what', 'which', 'whom', 'who')):
                return True
            if t in ('here', 'there') and h in ('in', 'from'):
                return True
    # 接続詞
    if h in _CONJ:
        if h == 'so':
            if ((t in _SUBJ or (t in _DET and t != 'no')
                 or t in _AUX_FINITE or t in ('if', 'that', 'as', 'not'))):
                return True
        elif h == 'if':
            if (t in _SUBJ or t in _DET or t in _AUX_FINITE
                    or t in ('not', 'so', 'only', 'there', 'here')):
                return True
        elif h in ('and', 'or', 'but', 'nor', 'yet'):
            if (t in _SUBJ or t in _DET or t in _OBJ or t in _AUX_FINITE
                    or t in _ADV
                    or t in ('so', 'if', 'when', 'where', 'why', 'how',
                             'who', 'what', 'which', 'that', 'yet', 'as',
                             'while', 'because', 'to', 'in', 'on', 'at',
                             'for', 'of', 'by', 'with', 'from', 'about',
                             'into', 'onto', 'upon', 'after', 'than', 'up',
                             'out', 'be', 'been', 'being')):
                return True
        elif h in ('while', 'when', 'where', 'because'):
            if (t in _SUBJ or t in _DET or t in _AUX_FINITE or t in _OBJ
                    or t in ('not', 'to', 'in', 'on', 'at', 'of', 'there',
                             'here')):
                return True
        elif h == 'that':
            if (t in _SUBJ or t in _DET or t in _OBJ or t in _AUX_FINITE
                    or t in ('not', 'if', 'when', 'so', 'to', 'in', 'on',
                             'at', 'of', 'for', 'by', 'with', 'from',
                             'there', 'here')):
                return True
    # 限定詞
    if h == 'all' and t in ('the', 'of', 'that', 'this', 'these', 'those',
                            'my', 'your', 'our', 'their', 'his', 'her',
                            'its', 'in', 'on', 'at', 'about', 'for', 'you',
                            'we', 'they', 'it', 'who', 'but', 'or', 'and',
                            'too'):
        return True
    if h == 'such' and t in ('a', 'an', 'as', 'that'):
        return True
    if h == 'other' and t == 'than':
        return True
    if h == 'the' and t in ('other', 'only', 'very'):
        return True
    if h in ('some', 'any', 'each', 'every', 'no') and t == 'other':
        return True
    # 副詞
    if h == 'not' and (
            t in _DET or t in _OBJ or t in _SUBJ
            or t in ('to', 'in', 'on', 'at', 'for', 'by', 'with', 'from',
                     'of', 'about', 'as', 'be', 'so', 'that', 'all', 'only',
                     'even', 'just', 'yet', 'now', 'here', 'there', 'too',
                     'very', 'really', 'always', 'never', 'if', 'when',
                     'what', 'how', 'why', 'who', 'which', 'because')):
        return True
    if h == 'just' and t in (
            'the', 'a', 'an', 'to', 'as', 'so', 'be', 'not', 'now', 'do',
            'did', 'does', 'is', 'was', 'are', 'were', 'has', 'have',
            'had', 'can', 'will', 'would', 'could', 'should', 'may',
            'might', 'must', 'what', 'how', 'when', 'where', 'who',
            'which', 'that', 'this', 'these', 'those', 'my', 'your',
            'our', 'their', 'his', 'her', 'its', 'some', 'any', 'each',
            'every', 'no', 'all', 'about', 'because', 'then', 'there',
            'here', 'too', 'very', 'really', 'also', 'still', 'never',
            'always', 'only', 'even', 'you', 'we', 'they', 'he', 'she',
            'it', 'me', 'them', 'him'):
        return True
    if h in ('here', 'there') and t in (
            'is', 'are', 'was', 'were', 'has', 'have', 'had', 'will',
            'would', 'can', 'could', 'should', 'may', 'might', 'must',
            'you', 'we', 'they', 'he', 'she', 'it', 'the', 'a', 'an',
            'this', 'that', 'these', 'those', 'my', 'your', 'our',
            'their', 'his', 'her', 'its', 'some', 'any', 'no', 'all',
            'in', 'on', 'at', 'to', 'for', 'by', 'with', 'from', 'about',
            'and', 'or', 'but', 'so', 'too', 'also', 'if', 'when',
            'where'):
        return True
    if h in ('then', 'now') and (
            t in _SUBJ or t in _DET or t in _AUX_FINITE
            or t in ('in', 'on', 'at', 'to', 'for', 'by', 'with', 'from',
                     'about', 'there', 'here', 'and', 'or', 'but', 'so',
                     'if', 'when', 'not', 'just', 'also', 'only', 'even',
                     'never', 'always', 'still', 'too', 'that', 'what',
                     'how', 'where', 'why', 'who', 'which')):
        return True
    if h in ('also', 'still', 'never', 'always', 'only', 'even',
             'really') and (
            t in _DET or t in _AUX_FINITE or t in _SUBJ
            or t in ('to', 'in', 'on', 'at', 'for', 'by', 'with', 'from',
                     'about', 'as', 'not', 'so', 'if', 'when', 'be',
                     'been', 'there', 'here', 'and', 'or', 'but', 'then',
                     'now', 'just', 'really', 'very', 'too')):
        return True
    # 目的語の代名詞（me too）
    if h in _OBJ and t == 'too':
        return True
    return False


def _fn_content_ok(h, t):
    """機能語 h ＋ 内容語 t（`he said` `not good` `a lot`）。"""
    if h in _ID_HEADS:
        return False                    # isfile・onerror・thedata
    if h == 'i':
        return t in _AFTER_I
    if h in _WH:
        return t in _WH_TAILS.get(h, ())
    if h in _OBJ:
        return False                    # meat・herman・usman
    if h in ('a', 'an'):
        if t in _NOT_AFTER_ARTICLE or len(t) < 3:
            return False
        vowel = t[0] in 'aeiou'
        return vowel if h == 'an' else not vowel
    if h in _SUBJ or h in _POSS:
        return True                     # he said・your name（her は目的語側）
    if h in _MODAL:
        return t in _TO_VERBS or t in _AFTER_I     # will go・may cause（Mayberry は割らない）
    if h in ('does', 'did'):
        return False
    if h in _AUX:
        return True                     # was good・be able・have fun
    if h in ('into', 'onto', 'upon', 'about', 'after', 'than'):
        return True
    if h == 'so':
        return t in _SO_TAILS
    if h == 'yet':
        return t in ('another', 'again', 'more')
    if h in _CONJ or h in _PREP:
        return False                    # Norway・Orwell・Andover・Socrates
    if h in ('not', 'just', 'very', 'too', 'also', 'still', 'never',
             'always', 'only', 'even', 'really', 'now', 'then', 'here',
             'there'):
        return True
    if h in ('each', 'every', 'other'):
        return True                     # eachtime・everytime
    return False


def _content_fn_ok(h, t):
    """内容語 h ＋ 機能語 t（`want to` `see you` `name is` `know that`）。"""
    if t in ('a', 'an'):
        return h in _ART_HEADS          # 冠詞が掛かる語は呼ぶ側が見る
    if t in ('am', 'be', 'been', 'being', 'all', 'and', 'or', 'but', 'nor',
             'yet', 'very', 'too'):
        return False                    # Northam・Goodall・Armand・Trainor
    if t == 'us':
        return h in _US_HEADS           # tell us・contact us（Markus・Loftus は名前）
    if t == 'on' and (h[-1:] in ('s', 't') or len(h) <= 3):
        return False                    # Grayson・Easton・Menon（come on・hold on は直す）
    if t in _OBJ or t in ('it', 'you'):
        return True
    if t in _PREP or t in _AUX or t in _DET or t in _SUBJ:
        return True
    if t in _CONJ:
        return True                     # so・if・as・than・when・where…
    if t in _WH:
        return True
    if t in _ADV:
        return True
    return False


def _parts_ok(parts, word, next_word, at_start):
    """
    分け方 parts（小文字）が、英語の語順として成り立つか。

    at_start: 大文字で書き出した語が文頭にあるか。True なら頭の語は
    文を始められる語（機能語・I・`_STARTERS`）に限る。False
    （文の途中の大文字）なら固有名詞とみなし、`I` の頭だけ認める。
    None は分からないとき（覚える側の門）。
    """
    cap = word[:1].isupper()
    head = parts[0]
    if cap and at_start is False and head != 'i':
        return False
    if cap and at_start and head != 'i' and head not in _FUNCTION_WORDS \
            and head not in _STARTERS:
        return False
    if len(parts) == 3:
        a, b, c = parts
        if a == 'i':
            if b not in _AFTER_I:
                return False
            if c not in ('to', 'a', 'an', 'not', 'you', 'it', 'so', 'in',
                         'at', 'on', 'the', 'my', 'that', 'this', 'up',
                         'out', 'for', 'with', 'them', 'him', 'her', 'us'):
                return False
        else:
            if not all(p in _FUNCTION_WORDS for p in parts):
                return False
            if not (_pair_ok(a, b) and _pair_ok(b, c)):
                return False
    else:
        h, t = parts
        if _identifier_shape(parts):
            return False
        hf, tf = h in _FUNCTION_WORDS, t in _FUNCTION_WORDS
        if hf and tf:
            if not _pair_ok(h, t):
                return False
        elif hf:
            if not _fn_content_ok(h, t):
                return False
        elif not _content_fn_ok(h, t):
            return False
    if parts[-1] in ('a', 'an') and not _tail_article_ok(parts[-1], next_word):
        return False
    # 分けた尻が次の語と同じ（`Loomis is → loom is is`）なら名前
    if next_word and parts[-1] == next_word.lower():
        return False
    if (len(parts) == 2 and parts[1] in ('is', 'was', 'has', 'does', 'are',
                                         'were', 'have')
            and parts[0] not in _FUNCTION_WORDS
            and parts[0] not in _STARTERS
            and not _pos_has(parts[0], 'N')):
        return False                    # 動詞＋is（add is）は名前
        # 文を始められる語（_STARTERS: Attached is／Enclosed is の倒置）は
        # 品詞が動詞だけでも通す（PC の en_pos で attached=V が割れなかった・
        # 表示スレッドの報告 2026-10-15・第4版）
    return True


def _pos_has(key, codes):
    """
    品詞辞書 `en_pos` が使えるとき、key の品詞に codes のどれかがあるか。
    辞書が無い・載っていない語は True（分からないときは止めない）。
    """
    try:
        import en_pos
        if not en_pos.available():
            return True
        have = en_pos.codes_for(key) or ''
        return (not have) or any(c in have for c in codes)
    except Exception:
        return True


def _tail_article_ok(art, next_word):
    """
    尻の冠詞 `a／an` が、後ろの語に掛かれるか。

    後ろに小文字で始まる内容語があり、頭の音が合うこと。品詞辞書が
    使えるなら、その語が名詞か形容詞であること（`Hasan Ali` `Allan
    went` を割らない）。
    """
    if not next_word or len(next_word) < 2 or not next_word[0].islower():
        return False
    key = next_word.lower()
    if key in _FUNCTION_WORDS:
        return False
    vowel = key[0] in 'aeiou'
    if (vowel if art == 'an' else not vowel) is False:
        return False
    try:
        import en_pos
        if en_pos.available():
            codes = en_pos.codes_for(key) or ''
            if codes and not any(c in codes for c in 'NJ'):
                return False
    except Exception:
        pass
    return True


def split_unknown_word(word, lex=None, next_word=None, at_start=None):
    """
    知らない綴りを、ちょうど1通りに分けられ、語順が成り立つなら
    分けた表記を返す。分けられない・紛れる・語順が立たないなら None。
    大文字は書いた位置に残す。

    next_word: 後ろに続く英単語（尻の冠詞が掛かる語）。
    at_start: 大文字で書き出した語が文頭か（`_parts_ok` を見よ）。
    """
    lex = lex if lex is not None else _base_lexicon()
    key = word.lower()
    for parts in (2, 3):
        cands = [c for c in _splits(key, lex, parts)
                 if any(p in _FUNCTION_WORDS for p in c)
                 # 1字の i は大文字で書いたときだけ（I）
                 and not any(p == 'i' and word[sum(map(len, c[:k]))] != 'I'
                             for k, p in enumerate(c))]
        if len(cands) > 1:
            return None         # 紛れる（the year／they ear）。触らない
        if len(cands) == 1:
            # 語順が立たないなら触らない。紛れの数えには入れる
            if not _parts_ok(cands[0], word, next_word, at_start):
                return None
            out, at = [], 0
            for p in cands[0]:
                out.append(word[at:at + len(p)])
                at += len(p)
            return ' '.join(out)
    return None


_CODE_CHARS = frozenset('=[]{}<>;`_#|\\\\$%^*~')
# `attrs.items` `self.name` のような点でつないだ名前、`self`・`def`・
# `return` など。記号が無くてもコードの行（`for aname, value in x.items():`）
_DOTTED_RE = re.compile(r'[A-Za-z0-9_)\]]\.[A-Za-z_(]|"[A-Za-z_]+"\s*:')
_CODE_WORDS = frozenset(('self', 'def', 'return', 'import', 'lambda', 'elif',
                         'yield', 'assert', 'raise', 'except', 'cls'))


_STATEMENT_RE = re.compile(
    r'^\s*(if|for|while|elif|with|def|class|return|import|from|try|except)\b')


def _looks_like_code(text):
    """半角の区間がプログラムの行に見えるか（記号の無い行の分）。"""
    if _DOTTED_RE.search(text):
        return True
    words = _WORD_RE.findall(text)
    if any(w in _CODE_WORDS for w in words):
        return True
    if text.rstrip().endswith(':') and ('(' in text or _STATEMENT_RE.match(text)):
        return True
    # 名前に括弧が付いた呼び出し（`foo(abot)`。`file(s)` の複数の印は除く・
    # 2026-10-16）
    if _CALL_RE.search(text):
        return True
    # 引用符でくくった1語と括弧（`hasattr(f, "readinto")`）
    return '(' in text and re.search(r'["\'][A-Za-z_]+["\']', text) is not None


_CALL_RE = re.compile(r'[A-Za-z0-9_]\((?!e?s\))[^()]*\)')
# この字の後ろは文頭（引用符・括弧・箇条書きの印・文末の記号）
_SENTENCE_BREAK = frozenset('.!?:;\n-*>|)…—–"\'(“‘「『[（')


def _ascii_stretch(line, s, e):
    """[s, e) を含む、半角だけの区間。"""
    a = s
    while a > 0 and line[a - 1].isascii() and line[a - 1] != '\n':
        a -= 1
    b = e
    while b < len(line) and line[b].isascii() and line[b] != '\n':
        b += 1
    return a, b


def _at_sentence_start(line, s, a):
    """s から始まる語が文頭か（半角の区間の頭か、文末の記号の後ろ）。"""
    i = s
    while i > a and line[i - 1] in ' \t"\'(“‘「『[（':
        i -= 1
    if i <= a:
        return True
    return line[i - 1] in _SENTENCE_BREAK


def _reads_as_japanese(key, store):
    """ローマ字として読んだかなが、日本語として意味を成すか。"""
    if store is None:
        return False
    try:
        from halfwidth import romaji_to_kana, makes_sense_as_japanese
        kana, _c, _t = romaji_to_kana(key)
        return bool(makes_sense_as_japanese(kana, store))
    except Exception:
        return False


def _english_context(line, s, e, key, store):
    """
    英文の中にある並びか。

    同じ半角の区間にある、ほかの知っている英単語を数える。
    ローマ字としては読めない語（`the` `want`）が1つでもあれば英文。
    並び自身がローマ字として全部読める（`howare` `wantto`）ときは、
    知っている語が2つ以上並び、かつローマ字のかなが日本語として
    意味を成さないときだけ英文とみなす（`anata to are` を割らない）。
    """
    a, b = _ascii_stretch(line, s, e)
    # **コードは英文ではない**（`isinstance` `fileno` `thisline` を
    # 割らない）。記号が混じる区間、関数呼び出しの形は見ない。
    if any(ch in _CODE_CHARS for ch in line[a:b]):
        return False
    if line[e:e + 1] == '(' or _looks_like_code(line[a:b]):
        return False
    others = [m.group(0) for m in _WORD_RE.finditer(line, a, b)
              if not (m.start() == s and m.end() == e)]
    known = [w for w in others
             if (len(w) >= 2 or w == 'I') and _known(w.lower(), store)]
    strong = any(w != 'I' and not _romaji_like(w.lower()) for w in known)
    if _romaji_like(key):
        if _reads_as_japanese(key, store):
            return False
        return strong or len(known) >= 2
    if known:
        return True
    return line.isascii() and a == 0 and b == len(line)


# 3字の語の入れ替えで直してよい先（`teh → the`・`adn → and`）
_SWAP3 = frozenset(('the', 'and', 'you', 'not', 'for', 'was', 'are', 'can',
                    'all', 'who', 'how', 'but', 'has', 'had', 'his', 'her',
                    'our', 'out', 'did', 'she', 'why', 'any', 'its', 'him',
                    'may', 'too', 'nor', 'yet', 'now'))


def find_missing_spaces(line, store=None, _again=True):
    """
    行の中の英単語について、順番の入れ替え・スペースの入れ忘れを直す。

    戻り値: [(開始, 終了, 直した表記), ...]
    """
    if not line or not any('a' <= ch.lower() <= 'z' for ch in line):
        return []
    lex = _base_lexicon()
    out = []
    for m in _WORD_RE.finditer(line):
        word = m.group(0)
        s, e = m.start(), m.end()
        if len(word) < 3:
            continue
        if s > 0 and (line[s - 1].isdigit() or line[s - 1] in _GLUED):
            continue
        # 文を終える `.` はくっついた記号ではない（2026-10-16・文末の語）
        if e < len(line) and (line[e].isdigit() or line[e] in _GLUED) \
                and not _sentence_period(line, e):
            continue
        key = word.lower()
        # 途中に大文字（GitHub・iPhone）／大文字だけ（HTMLCSS）は名前
        if word.isupper() or any(c.isupper() for c in word[1:]):
            continue
        a, b = _ascii_stretch(line, s, e)
        if key in _FORCE_SPLIT:
            # よくある入れ忘れは辞書より先に直す。コードの行は除く
            if not (any(ch in _CODE_CHARS for ch in line[a:b])
                    or _looks_like_code(line[a:b])):
                out.append((s, e, _recase(word, _FORCE_SPLIT[key])))
            continue
        if _known(key, store):
            continue
        if _quoted(line, s, e):
            # 引用符に挟まれた語は、書いたとおりに挙げた語（"teh" は誤字の例）
            continue
        nxt = _WORD_RE.match(line, e + 1) if line[e:e + 1] == ' ' else None
        nxt = nxt.group(0) if nxt else None
        at_start = _at_sentence_start(line, s, a) if word[:1].isupper() else None
        if not _english_context(line, s, e, key, store):
            # 英文の外でも、**機能語だけ**にちょうど分かれる並び
            # （`Thisis` `Itwas` `isthe`）は、名前にもローマ字にもならない
            lone = (None if _romaji_like(key) else
                    split_unknown_word(word, lex, nxt, at_start))
            parts = lone.lower().split(' ') if lone else ()
            if (lone and len(key) >= 5 and parts[-1] not in _ID_TAILS
                    and all(p in _FUNCTION_WORDS for p in parts)):
                swaps, nears = _one_edit_words(key, lex, word[:1].isupper())
                if not (swaps or nears):
                    out.append((s, e, lone))
            continue
        # 2026-10-16（うにさんの選択「英語の補正を強化」）: 1つの打ち違いで
        # 届く語のうち、使われやすさで1つに決まるものへ直す（`en_typo`。
        # wnat → want・tge → the・shouls → should）。分け方もあるときは、
        # 分けた語のほうが使われやすければ分ける（iam → i am。aim ではない）。
        typo = _typo_fix(word, store, re.match(r'\s*[A-Za-z]', line[e:]) is not None,
                         at_start)
        # 2026-10-23: 前後の語が選ぶ語があればそれに、前後のどちらとも
        # 組にならない語なら直さない（`en_context`）
        chosen = _context_fix(line, s, e, word, typo)
        if chosen is not None:
            typo = chosen or None
            if chosen:
                out.append((s, e, chosen))
                continue
        if typo:
            split = split_unknown_word(word, lex, nxt, at_start)
            if split and _split_outweighs(split, typo):
                out.append((s, e, split))
            else:
                out.append((s, e, typo))
            continue
        # 隣接キー・順番の入れ替えを先に考える
        swaps, nears = _one_edit_words(key, lex, word[:1].isupper())
        if swaps or nears:
            # 直すのは、入れ替えの先が機能語ただ1つのときだけ
            # （teh→the・adn→and・thier→their）。3字は紛れが多い
            # （cpu→cup・ord→rod・urn→run）ので、先を `_SWAP3` に限る
            target = next(iter(swaps)) if len(swaps) == 1 else ''
            if (target and not nears and len(key) <= 5 and word.islower()
                    and target in _FUNCTION_WORDS
                    and (len(key) >= 4 or target in _SWAP3)):
                out.append((s, e, target))
            continue
        fixed = split_unknown_word(word, lex, nxt, at_start)
        if fixed:
            out.append((s, e, fixed))
    # 2026-10-16: 語は知っているが、文の中で読むと違う語（`dont` `i think`
    # `come form` `more then`）。`en_typo.line_fixes` が前後の語で決める。
    try:
        import en_typo
        out.extend(en_typo.line_fixes(line, store, [(a, b) for a, b, _f in out]))
    except Exception:
        pass
    if out and _again:
        # 2026-10-23: 隣り合う2語の打ち違い（`knosw hen`）は、片方を直した
        # 行で読み直すと、もう片方の前後が見える。直していない所の直しだけ足す
        out.extend(_second_look(line, store, out))
    return out


def _second_look(line, store, out):
    """out を当てた行をもう一度読み、out に触れない語の直しを元の行の
    位置に戻して返す。"""
    out = sorted(out)
    fixed, moved, at = [], [], 0      # moved: (元の始まり, 元の終わり, ずれ)
    shift = 0
    for s, e, f in out:
        if s < at:
            return []                 # 重なる直し（起きないはず）
        fixed.append(line[at:s])
        moved.append((at, s, shift))
        fixed.append(f)
        shift += len(f) - (e - s)
        at = e
    fixed.append(line[at:])
    moved.append((at, len(line), shift))
    more = []
    for s, e, f in find_missing_spaces(''.join(fixed), store, _again=False):
        for a, b, d in moved:
            if a + d <= s and e <= b + d:
                more.append((s - d, e - d, f))
                break
    return more


def _sentence_period(line, e):
    try:
        import loanword
        return loanword._sentence_period(line, e)
    except Exception:
        return False


def _typo_fix(word, store, followed=True, at_start=None):
    """`en_typo` の直し（使われやすさで1つに決まる打ち違い）。無ければ None。
    followed: 後ろに語が続く（冠詞は語の前にしか立たない）。
    at_start: 大文字で書き出した語が文頭か（文の中の大文字は名前）。"""
    try:
        import en_typo
        return en_typo.fix_word(word, store, followed, at_start)
    except Exception:
        return None


def _context_fix(line, s, e, word, typo):
    """`en_context.unknown_fix`: 前後の語が選ぶ語・'' (typo を捨てる)・None。"""
    try:
        import en_context
        return en_context.unknown_fix(line, s, e, word, typo)
    except Exception:
        return None


def _quoted(line, s, e):
    """引用符にそのまま挟まれた語（"cmp"）。書いたとおりの語として残す。"""
    try:
        import en_typo
        return en_typo._quoted(line, s, e)
    except Exception:
        return False


def _split_outweighs(split, typo):
    """分けた語がどれも、直した語より使われやすいか。直した語が分けた
    頭の語そのものなら、打った字を残して分ける（`hasa` は has でなく
    has a。`asoon` は soon のまま・`arther` は rather のまま）。"""
    try:
        import en_typo
        parts = split.lower().split(' ')
        if len(parts) == 2 and parts[0] == typo.lower():
            return True
        return min(en_typo.zipf(p) for p in parts) > en_typo.zipf(typo)
    except Exception:
        return False


def _recase(word, fixed):
    """分けた表記 fixed（小文字）に、word の大文字を書いた位置のまま戻す。"""
    out, at = [], 0
    for p in fixed.split(' '):
        out.append(word[at:at + len(p)])
        at += len(p)
    return ' '.join(out)


def would_split(word, store=None):
    """覚える側の門: この綴りはスペースの入れ忘れとして割られるか。"""
    key = (word or '').lower()
    if not key.isalpha():
        return False
    if key in _FORCE_SPLIT:
        return True
    if _known(key, store):
        return False
    if any(c.isupper() for c in word[1:]):
        return False
    swaps, nears = _one_edit_words(key, _base_lexicon(),
                                   word[:1].isupper())
    if swaps or nears:
        return False
    return split_unknown_word(word) is not None
