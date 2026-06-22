#!/usr/bin/env python3
"""
build_launcher_en.py — generate the English launcher speech INIs.

Source of truth for the launcher translation (rough first pass). Reads each original
JP `Ini` (the unpacked `work/launcher/<slug>/Ini.ini`) for its STRUCTURE — `[POS]`
numbers, key order, section headers — and substitutes the English `Name=` and the 8
`Serif*` dialogue lines below, preserving `\\n` breaks and the `<%SCHEDULE%>` template.

`|` marks an in-game line break in the strings below (converted to a literal `\\n`).
Output: patch/launcher/<slug>.ini (cp932), consumed by sygnas_repack.py.
"""
import os, sys, glob

# JP situation comments -> English (cosmetic; not displayed in-game)
COMMENTS = {
    ';セリフ：新しいバージョン':            ';Line: new version available',
    ';セリフ：メール着信':                  ';Line: mail received',
    ';セリフ：メールサーバーログイン失敗':  ';Line: mail server login failed',
    ';セリフ：新着メールがなかった':        ';Line: no new mail',
    ';セリフ：スケジュールがなかった':      ';Line: no schedule today',
    ';セリフ：カレンダー：予定アリ':        ';Line: calendar - has schedule',
    ';セリフ：カレンダー：ログイン失敗':    ';Line: calendar - login failed',
    ';セリフ：カレンダー：ID未登録':        ';Line: calendar - no ID registered',
}

K = ['SerifNewVersion','SerifMailCheck','SerifMailError','SerifMailNone',
     'SerifCallenderNone','SerifCallenderSchedule','SerifCallenderError','SerifCallenderNoAccount']

TRANS = {
'akira': ('Akira Kogami', [
  'Oooh~!|A brand new version|seems to be out☆',
  'Mornin, lucky☆|Looks like you got mail|As expected of a popular girl',
  'Tch...|Can you not even set up|your own mail?|You really are useless',
  'Nooo~|No mail at all?|Akira is gonna cry~',
  'Oh my|Nothing scheduled today☆|Bye-nee~',
  'Kyaan☆ Today, your plans are|<%SCHEDULE%>|right?|Let us give it our all☆',
  'Come on already...|why did the calendar setup|fail this time?',
  'Listen, to use the calendar you need a Google Calendar ID, okay?|Akira doesn\'t get it~']),
'amimami': ('Ami & Mami Futami', [
  'Ami Ami!|A new version is out~|Mami Mami!|We gotta check it, right~',
  'Bro, you got mail!',
  'Uwaaah|we couldn\'t go grab the mail!',
  'Nothing came in!|Bro\'s so laaame♪',
  'There\'s nothing today~|Bro, if you\'re bored|let\'s play some Xbox!',
  'Bro\'s schedule today is|<%SCHEDULE%>|huh|Let\'s smash it to pieces!',
  'Bro, bro, what do we do!|We can\'t get into the calendar',
  'Hey bro|to use the calendar you need a Google Calendar ID']),
'ayano': ('Ayano Minegishi', [
  'Looks like a new version|has been released',
  'Oh|seems you have some mail?',
  'I couldn\'t read the mail|maybe the settings|are wrong',
  'Looks like there\'s no mail|Now now|don\'t be so cross',
  'I see, no plans today...|Shall we take it easy then?',
  'Today\'s schedule is|<%SCHEDULE%>|right?|Do your best out there',
  'Looks like I couldn\'t get|into the calendar|Did something go wrong?',
  'To use the calendar you need a Google Calendar ID, it seems']),
'azusa': ('Azusa Miura', [
  'Oh my~|the version went up|I wonder if there\'s a feature|to meet my destined one~',
  'Producer|you seem to have some mail~',
  'Oh my~|looks like the mail settings|aren\'t quite right~',
  'Oh dear~|did I drop the letter|somewhere along the way~?',
  'Oh my~|if there are no outings planned|then I won\'t get lost, will I♪',
  'Um, today you have|<%SCHEDULE%>|I see',
  'Oh my~|I couldn\'t get into the calendar|whatever shall we do~',
  'Producer|to use the calendar you need a Google Calendar ID']),
'chihaya': ('Chihaya Kisaragi', [
  'A new version appears|to be available|Let\'s install it to improve|our lesson efficiency',
  'Producer|you have mail',
  'Pull yourself together|your mail isn\'t set up',
  'No requests...|Ugh...|the humiliation...!',
  'No plans, I see...|With this much free time|we could practice all year',
  'Producer|today\'s schedule is|<%SCHEDULE%>|Let\'s do our best',
  'Ugh...|I can\'t get into the calendar|Unbelievable...',
  'Producer|to use the calendar you need a Google Calendar ID']),
'haruka': ('Haruka Amami', [
  'Ah|it\'s a new version!|Let\'s install it right away!',
  'Producer|mail! It\'s mail!',
  'Produuucer~|I couldn\'t receive the mail',
  'No mail...|whoaa|so you have no friends♪',
  'No work again today...|I\'m supposed to be the heroine, right?',
  'Producer|today it\'s|<%SCHEDULE%>|right?|Let\'s get fired up!',
  'P-Producer!|I can\'t get into the calendar!!',
  'Producer|to use the calendar you need a Google Calendar ID, it seems']),
'hiyori': ('Hiyori Tamura', [
  'New version, yo!|Work efficiency is going up!',
  'Whoops|looks like you got some mail!',
  'Yikes|looks like I couldn\'t read the mail~|the settings might be off',
  'Phew...|looks like no nagging mail came',
  'No plans!|Now\'s the chance to do those manuscripts, yo!',
  'Today\'s schedule is|<%SCHEDULE%>|yo|Still got time until the deadline...',
  'Whoa, couldn\'t log into|the calendar, yo|Wanna recheck the settings?',
  'To use the calendar you need a Google Calendar ID, yo~']),
'iori': ('Iori Minase', [
  'Hurry up and update|to the new version|honestly, what a slowpoke',
  'Hey you|you\'ve got mail, go fetch it',
  'What are you doing, slowpoke!|The mail isn\'t even set up!',
  'There was no mail?|Do you have no friends besides me?',
  'I-if you\'re bored I suppose|I could keep you company?',
  'Oh, today\'s schedule|has <%SCHEDULE%>|in it|Nihihi',
  'What, what is this!|I can\'t get into the calendar!',
  'Hey, Producer|to use the calendar you need a Google Calendar ID']),
'kagami': ('Kagami Hiiragi', [
  'A new version is out|If you put it off you\'ll forget|so just do it now',
  'Hey|looks like you\'ve got mail?',
  'Your mail isn\'t set up|properly|Get it together, you',
  'No mail came|W-wait, why do I have to|be the one to send you any!',
  'No plans today|If you\'re free, at least clean|your room|I\'ll help you out',
  'Hmm hmm, today\'s schedule is|<%SCHEDULE%>|huh|Do it properly',
  'Couldn\'t get into the calendar|Did you actually set it up?',
  'To use the calendar you need a Google Calendar ID|Didn\'t you know?']),
'konata': ('Konata Izumi', [
  'Oh, a new version is out|Devs sure have it rough~',
  'Hmm, looks like you got mail',
  'Looks like I can\'t read the mail~|let\'s try again later',
  'Hmm, no mail|how about that',
  'Ooh, lucky|No plans today!|Guess I\'ll grind my game backlog',
  'Today\'s schedule is|<%SCHEDULE%>|huh|Well, let\'s just wing it',
  'Whoopsie|couldn\'t get into the calendar',
  'Apparently you need a Google Calendar ID to use the calendar~']),
'kotori': ('Kotori Otonashi', [
  'A new version appears|to be available|Please check it right away',
  'Producer|you have mail',
  'Oh dear|looks like the mail isn\'t|set up properly',
  'No mail from anyone...|how worrying...|d-don\'t tell me it\'s all|caught in the spam filter!?',
  'Aaah...|no job requests today either...|the biggest crisis since 765 Pro began!',
  'Producer|today\'s schedule has|<%SCHEDULE%>|in it',
  'I couldn\'t get into the calendar|Please check the settings',
  'Producer,|to use the calendar you need a Google Calendar ID']),
'makoto': ('Makoto Kikuchi', [
  'Alright! New version is out!|Somehow it\'s exciting, huh!',
  'Producer|you\'ve got mail!',
  'Agh!|I couldn\'t read the mail!|What do I do...',
  'Um, there was nothing...|Oh!|it\'s a letter only fools can\'t see, right!',
  'No plans, huh|Oh!|if you\'re free wanna do some Billy\'s Bootcamp!?',
  'Producer|today it\'s|<%SCHEDULE%>|right!|Let\'s go full throttle!',
  'Producer!|I can\'t get into the calendar|What do we do?',
  'Producer|apparently you need a Google Calendar ID to use the calendar']),
'miki': ('Miki Hoshii', [
  'Afuu...|a new version is out|but checking it is such a pain',
  'Afuu...|you\'ve got mail',
  'What do we do, Honey|I can\'t read the mail',
  'Afuu...|getting no mail is so sad,|Honey...|Miki will mail you♪',
  'Munya... free again today...|mentaiko rice balls are|the best in the world... y\'know...',
  'Honey\'s schedule is|<%SCHEDULE%>|y\'know|do your best, \'kay',
  'I can\'t get into the calendar~|afuu...',
  'Hey Honey|to use the calendar you need a Google Calendar ID']),
'minami': ('Minami Iwasaki', [
  'A new version is out...|um... shall we go check it?',
  'Um...|looks like you have mail',
  'I couldn\'t read the mail...|you should check the mail|settings, I think...',
  'Mail...|doesn\'t seem to have come',
  'No plans today, huh...',
  'Today\'s schedule is...|<%SCHEDULE%>|right|Are you okay...?',
  'I couldn\'t get into the calendar...|Shall we check the settings?',
  'To use the calendar you need a Google Calendar ID, it seems...']),
'misao': ('Misao Kusakabe', [
  'Ta-daa!|New version is out!|Wooooo!!',
  'Ooh|you\'ve got mail— gwah!',
  'Aah|couldn\'t read the mail|well, no biggie, no biggie',
  'Ha-ha|no mail, huh|guess you\'re hated?',
  'Aw man, no plans?|Somebody play with me—',
  'Today there\'s|<%SCHEDULE%>|huh|well, do your best',
  'Huh? What\'s this?|Couldn\'t get into the calendar?',
  'Apparently you need a Google Calendar ID to use the calendar']),
'miyuki': ('Miyuki Takara', [
  'Oh, a new version has|been released, it seems|Fufu',
  'Oh my|looks like you\'ve got mail',
  'Oh dear|the mail settings seem|to be wrong',
  'My apologies|it seems no mail has arrived',
  'There don\'t seem to be any plans|Ufufu|Shall we relax today?',
  'Today\'s schedule seems|to have <%SCHEDULE%>|in it|Good luck',
  'I can\'t get into the calendar|I wonder if the settings are wrong?',
  'Did you get a Google Calendar ID?|You need one to use the calendar']),
'paty': ('Patricia Martin', [
  'New version is out-NE!|Come on, come on|check it right away-YO!',
  'OH!|looks like you\'ve got mail-NE',
  'Aw, can\'t read the mail-NE|Maybe the mail settings are wrong-NE',
  'OH!|the spam filter here is strong-NE?',
  'No plans, how lucky-NE|I\'ll read manga all day-YO',
  'FUM... today\'s schedule is|<%SCHEDULE%>|-NE|Good luck-NE',
  'OH! Can\'t get into the calendar-YO|maybe the settings are wrong-KA?',
  'To use the calendar you need a Google Calendar ID-YO']),
'ritsuko': ('Ritsuko Akizuki', [
  'A new version is out, it seems|Checking out new things|is also a producer\'s job',
  'Producer|you have mail',
  'Producer!|you can\'t even set up|your own mail?',
  'Not even spam comes in|just how much of a NEET|are you, Producer?',
  'No work again today|Are you trying to bankrupt the office?',
  'Producer|today\'s schedule is|<%SCHEDULE%>|right?|Let\'s do this properly',
  'I couldn\'t get into the calendar|Did you set it up properly?',
  'Producer|to use the calendar you need a Google Calendar ID']),
'tsukasa': ('Tsukasa Hiiragi', [
  'Fuwa|a new one\'s out, huh',
  'Ah, looks like you\'ve got mail',
  'Myuu|I couldn\'t read the mail',
  'No way...',
  'Waa|we can relax today',
  'Um, um, today\'s schedule is|<%SCHEDULE%>|right|let\'s do our best',
  'Auu|I can\'t get into the calendar~',
  'U-um|to use the calendar you need|a Google Calendar ID, it seems']),
'yayoi': ('Yayoi Takatsuki', [
  'A new one\'s out!|maybe this\'ll make things|more and more convenient',
  'Uh-uh!|you\'ve got mail!',
  'Producer|what do we do...|I couldn\'t read the mail',
  'Uh-uh!|data charges cost money too|so having no mail is better!',
  'Uh-uh!|if you\'re free, come to the|supermarket sale with me!',
  'Uh-uh!|today\'s schedule is|<%SCHEDULE%>|Get pumped, high-touch!',
  'Uuh...|maybe I can\'t get into the calendar...',
  'Producer|you might need a Google Calendar ID for the calendar']),
'yukiho': ('Yukiho Hagiwara', [
  'Ah, a new version was announced|...it seems|a-am I an unwanted old girl now?',
  'Producer|looks like you\'ve got mail',
  'Hauu, I\'m sorry|the mail settings seem|to be wrong|hauu~',
  'U-um|there are no letters to fill in~...',
  'Um, if there\'s nothing to do|may I go dig a hole|over there...',
  'Um, uh, today\'s schedule is|<%SCHEDULE%>|right|u-um, let\'s do our best...',
  'I couldn\'t get into the calendar...|I\'ll go bury myself in a hole',
  'Producer,|to use the calendar you need a Google Calendar ID, it seems.']),
'yutaka': ('Yutaka Kobayakawa', [
  'Yaay|a new one\'s out, huh|I wonder what it\'s like',
  'Looks like you\'ve got mail',
  'Auu, what do we do|I couldn\'t read the mail',
  'Um|no mail came, but|please cheer up!',
  'No plans, huh|Waa|is today a day off?',
  'Today\'s schedule is|<%SCHEDULE%>|right|please do your best',
  'I-I\'m sorry|I couldn\'t get into the calendar~',
  'Um, to use the calendar you need|a Google Calendar ID, apparently']),
}

def br(s): return s.replace('|', '\\n')   # | -> literal backslash-n

def transform(core, slug):
    if core.startswith('Name='):
        return 'Name=' + TRANS[slug][0]
    if '=' in core:
        key = core.split('=', 1)[0]
        d = dict(zip(K, TRANS[slug][1]))
        if key in d:
            return key + '=' + br(d[key])
    if core in COMMENTS:
        return COMMENTS[core]
    if ';' + core in COMMENTS:          # tolerate a JP comment missing its leading ';'
        return COMMENTS[';' + core]     # (amimami's schedule label) -> EN comment
    return core

def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(root, 'work', 'launcher')
    dst = os.path.join(root, 'patch', 'launcher'); os.makedirs(dst, exist_ok=True)
    n = 0
    for ini in sorted(glob.glob(os.path.join(src, '*', 'Ini.ini'))):
        slug = os.path.basename(os.path.dirname(ini))
        if slug not in TRANS:
            print('  skip (no translation):', slug); continue
        raw = open(ini, 'rb').read().decode('cp932')
        out = []
        for line in raw.split('\n'):
            cr = line.endswith('\r'); core = line[:-1] if cr else line
            out.append(transform(core, slug) + ('\r' if cr else ''))
        text = '\n'.join(out)
        # ASCII-ize MT smart-punctuation + JP decorations: the app draws serifs via
        # DrawTextA (cp932), so ANY non-ASCII byte mojibakes on a non-JP locale (goal #2).
        # Decorative ☆/★/♪ tics in dialogue -> '~' (the franchise/product NAMES use '*' —
        # those live in the manifest, not the serifs; the bubbles carry only decorative stars).
        # Serifs draw via DrawTextA (cp932) so non-ASCII mojibakes on a non-JP locale (goal #2).
        for a, b in (('—', '--'), ('–', '-'), ('…', '...'),
                     ('‘', "'"), ('’', "'"), ('“', '"'), ('”', '"'),
                     ('☆', '~'), ('★', '~'), ('♪', '~'), ('：', ':'), ('　', ' ')):
            text = text.replace(a, b)
        bad = sorted({c for c in text if ord(c) > 0x7E})
        if bad:                          # locale-safety guard: serifs MUST be pure ASCII
            raise SystemExit(f"{slug}.ini: non-ASCII survived (extend the map): "
                             + ' '.join(f'U+{ord(c):04X}({c})' for c in bad))
        open(os.path.join(dst, slug + '.ini'), 'wb').write(text.encode('cp932'))
        n += 1
    print(f'wrote {n} English launcher INIs -> patch/launcher/ (all pure ASCII)')

if __name__ == '__main__':
    main()
