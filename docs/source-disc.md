# The source disc — 「らき☆マス」 metadata & checksums

Identification and integrity data for the original SYGNAS disc this project patches. Two uses:

- **Sanity-check that you have the supported version** before building — the English patch is built
  against these *exact* files (the `binpatch` ops match specific byte strings; a different pressing or
  revision may not apply cleanly). Verify your `setup.exe` against the SHA-256 below first.
- **A preservation record** for an obscure 2007 doujin disc that is long out of print.

> Per the project's [hard rule](../README.md#hard-rule-no-redistribution-of-original-files), only
> **metadata** is recorded here — file names, sizes, dates, versions, and one-way hashes. No SYGNAS
> file content is reproduced or redistributed; these hashes don't let you reconstruct anything.

## The disc

| | |
|---|---|
| **Title** | らき☆マス デスクトップアクセサリ Ver1.00 — *Lucky☆Mas Desktop Accessory*, Ver1.00 |
| **Circle** | SYGNAS (ダダ) |
| **Catalog** | SGNS-0009 |
| **Released** | Comiket 73 — December 2007 |
| **Media** | CD-ROM (ISO 9660), image named `LuckyMaster.iso` |
| **Installer** | Inno Setup 5.1.10 |

## Disc image — root files

`LuckyMaster.iso` holds four files at its root (the image itself isn't kept in this project — these
are its extracted contents). `autorun.inf` points the disc's autorun at `setup.exe` with the
`rakimas.ico` icon; `お読みください.txt` is SYGNAS's Japanese readme.

| File | Size (bytes) | Modified | SHA-256 |
|---|---:|:--:|---|
| `setup.exe` | 91,972,657 | 2007-12-05 | `f3940514ad4ccdf0a7344a46c836efdb06c00d559d49520bc962f25eb224e02b` |
| `rakimas.ico` | 13,942 | 2007-12-02 | `1be80f0c07f3fd981af4781b93f537fc862dc57f18b5ceb0bb009b266232f8df` |
| `autorun.inf` | 47 | 2007-12-04 | `181d9c380190d55d30349607715c972a197fcaa9fccca133f91b229e3ea471a6` |
| `お読みください.txt` | 1,403 | 2007-12-02 | `653ef6b53078603194dd8b85e2eb0e720693f9ddb95de3b2ca960231c7e34968` |

### setup.exe — the one file you verify

This is the single file you feed the builder (`--setup`). Confirm it matches **before** building:

| | |
|---|---|
| **Size** | 91,972,657 bytes (≈87.7 MiB) |
| **SHA-256** | `f3940514ad4ccdf0a7344a46c836efdb06c00d559d49520bc962f25eb224e02b` |
| **MD5** | `4c600fefc688ab3701cafc1650f402fa` |
| **Built** | 2007-12-05 · Inno Setup 5.1.10 · AppVerName `らき☆マス デスクトップアクセサリ Ver1.00` |

```sh
sha256sum setup.exe
# expect: f3940514ad4ccdf0a7344a46c836efdb06c00d559d49520bc962f25eb224e02b
```

## The installed payload

`setup.exe` installs **164 files / 88 MB** to `…\SYGNAS\らき☆マス\` (the English build re-homes it to
`…\SYGNAS\LuckyMas\`). The component EXEs/DLLs were compiled **2007-11-19 → 2007-12-02**.

| Folder | Files | Size | What |
|---|---:|---:|---|
| `app/launcher` | 28 | 7.0M | the mascot launcher + calendar/mail companion (`Launch.exe`, `gcal.exe`, `gcalcore.dll`, 22 `.Xvi` serif packs, `gdiplus.dll`) |
| `app/copy` | 12 | 46M | the MinkIt copy-animation engine (`MinkIt.exe` / `MinkIt.dll`) + 10 `.mink` character containers |
| `app/calc` | 6 | 2.0M | the themed calculators (`WinCalc*.exe`, `data.pak`, `gmp.dll`, `mpfr.dll`) |
| `app/wallpaper` | 111 | 32M | 84 wallpapers (14 artists × resolutions) + the HTML picker |
| `sys` | 4 | 804K | the four screensavers (`.scr`) |

### Key binaries

Short SHA-256 prefixes; full hashes are in the manifest below.

| File | Size (bytes) | Compiled (PE) | SHA-256 |
|---|---:|:--:|---|
| `app/launcher/Launch.exe` | 344,064 | 2007-12-01 | `b0334270d71d…` |
| `app/launcher/gcal.exe` | 438,272 | 2007-12-02 | `0817d5df049d…` |
| `app/launcher/gcalcore.dll` | 319,488 | 2007-11-29 | `2963aa3eb345…` |
| `app/copy/MinkIt.exe` | 73,728 | 2007-11-27 | `f6fff2d15959…` |
| `app/copy/MinkIt.dll` | 94,208 | 2007-11-19 | `7803b55f4a49…` |
| `app/calc/WinCalc.exe` | 577,536 | 2007-11-30 | `faceac1ad25d…` |
| `app/calc/WinCalcImas.exe` | 102,400 | 2007-11-30 | `12f9016ab787…` |
| `app/calc/WinCalcLucky.exe` | 102,400 | 2007-11-30 | `229b9e9efc08…` |

### Screensavers — one binary, four names

The four `sys/*.scr` files are **byte-identical** (the same SHA-256, 198 KiB each) — a single
screensaver binary shipped under four filenames. Because a `.scr`'s filename *is* its
Display-Properties label, that one binary surfaces as four separate entries in the Screen Saver list:
`らき☆マス：アイマス3D` · `らき☆マス：アイマスコミック` · `らき☆マス：らき☆すたコミック` · `らき☆マス：ちびキャラズ`
(the English build renames them to *LuckyMas - iM@S 3D / iM@S Comic / Lucky Star Comic / Chibi Characters*).

They are **not referenced or launched by any executable or HTML page** — `.scr` appears in none of the
binaries, INIs, or pages, and the launcher menu has no screensaver entry. They reach the user purely
through Windows' own mechanism: the installer copies them to `{sys}` (system32), where the screensaver
subsystem enumerates them, and the disc's readme directs the user to **Control Panel ▸ Display ▸ Screen
Saver**. The launcher's only related item is a generic Display-Properties shortcut (`Exec009 =
{sys}\desk.cpl`) — the same applet — never a specific `.scr`.

> ⚠️ **Known issue (under investigation):** on a **non-Japanese-locale** XP the screensavers show the JP
> error 「スクリーンセーバーを完全に削除するには再起動してください」 instead of running. The 2006
> ASPack-packed engine picks its animation by reading its **own filename** in the system's legacy
> codepage, which can't represent the name on a non-JP locale (and the English rename isn't in its table).
> Whether it's fixable on an EN-locale box (rename revert · `Language for non-Unicode programs = Japanese`
> · binary patch) is being investigated — see [`next-builds.md`](next-builds.md) §"Session 17".

### Full file manifest (SHA-256)

Paths are relative to the install root. To check your own extracted/installed tree, save this block
as `source-disc.sha256` in that root and run `sha256sum -c source-disc.sha256`.

<details><summary>All 164 installed files</summary>

```
f9eebf8de38a8a558c687d1afc4575fb0ca61571611a555f92383440d08d8cff  app/SYGNAS.url
faceac1ad25dbae8dbed27fb89c37d7077040517be5cd264920dc636c660f3ec  app/calc/WinCalc.exe
12f9016ab7874d704c0d9c958ef69d5d7579b70bfaaa149947185dbe526734fa  app/calc/WinCalcImas.exe
229b9e9efc08c90d2d3680bf0d0b8b4c314266c6d2ccbc31315a8908a1014d24  app/calc/WinCalcLucky.exe
a63a9e96147ed99b2f83c973e5398fe9ef330ce29eae0a8191e93f7172664685  app/calc/data.pak
03a9bfe9f7bac491290d32b4dd6b49708b6fefca4e499d9311aeba81dfacc0a6  app/calc/gmp.dll
7d14152865ff540ed993950728f0d34e70978ebce23c078aeb69e4e681fc5d69  app/calc/mpfr.dll
7803b55f4a49951e9591e4e1fef5ee8e3f2d7f0386874e79ef5837752b43f015  app/copy/MinkIt.dll
f6fff2d15959b02a92f3c2bdc6d26e2617453dfa9e991f52fc229c2ab3f6ab09  app/copy/MinkIt.exe
459e98e5f0e5ff81634eeb3904a81ecb96c7ea04a6fe624acbd8a0c937d28cbb  app/copy/かがみ_copy.mink
3ac152326bee24f9803e1189b143da2e1165415f7e65f9be7990d4a945bd5c0e  app/copy/かがみ_dl.mink
5ef8a02e244723001ea9fd8aea29d96efbe01835d57f027c5230ff404074c2e1  app/copy/こなた_copy.mink
c1ae2cc35984ae475bd5897eb61f0a2ea3bc439586e9db3393f837a94aba1f13  app/copy/こなた_dl.mink
c7c2de6253c2af8bfdd278d388771aa11b85f291e5e43530d9ac85e6c80e4844  app/copy/やよい_copy.mink
e7677c865c53cf30b2536aed7d2cb2722ae6a2e6208d44e651133945b4c7f237  app/copy/やよい_dl.mink
90b01c5c46ed218ed95201ccd37e1c79b51ed4cd7a464d514f9c878967e5a22c  app/copy/千早_copy.mink
c29664258361f030255669831d003ace9916793bea420a482529421b2e2897ec  app/copy/千早_dl.mink
670728b6b274f0fb345aec87c75be1fc461f5f39d5ed21ca231be8cb84b25e93  app/copy/真_copy.mink
2aeb86d86ee5a1cc097e27bf4557ff82958daff0458d5cd0670318e3801f9445  app/copy/真_dl.mink
b0334270d71d65eb533699818610794af0ddcc07404a38181ee5e536ae30d153  app/launcher/Launch.exe
02fa11c3c118687d9361145760c6f53103c369495d6e6ce0349e35dcc8ab373e  app/launcher/Launch.ini
02fa11c3c118687d9361145760c6f53103c369495d6e6ce0349e35dcc8ab373e  app/launcher/Launch.ini.org
81a247ec311465051c96aa6e2912be45f1ee87099193e8b717e34e89f9206838  app/launcher/akira.Xvi
4d94e4e0727c49432ad01ae7070104488f68638bce40510dc8e5c5ca90665014  app/launcher/amimami.Xvi
62c85ec51ae3bc5330bb0c1b39ebea76e9abf8252fa91426896c7f4f435779c9  app/launcher/ayano.Xvi
30b246fa7b9dc4ca95eae5f5682117c84fbb154f1cc236252154b717348bc841  app/launcher/azusa.Xvi
d87485b41468adb01d6724fe5edfc30862ac1aa4e41a9808c32937bcc3a60329  app/launcher/chihaya.Xvi
0817d5df049d5c6d2e25860bdb821ce89a0849d3407c952e48e8d5b6f1cc18c8  app/launcher/gcal.exe
2963aa3eb345664b34f0a95149e50d005f3927dd037502f8268f272f2ade4cd7  app/launcher/gcalcore.dll
f1da32183b3da19f75fa4ef0974a64895266b16d119bbb1da9fe63867dba0645  app/launcher/gdiplus.dll
61bce38732aabf6859108813c9da16d03458b05dd9c8854be8c39e5034820e6b  app/launcher/haruka.Xvi
68b94298f42dc185ddc61cdcdfb10f6b796a6b53ef5658539685bdfbe26ea711  app/launcher/hiyori.Xvi
13c033416600e5027c2d84309e6f9de82884e37e7d3876c2d747586ce3478b4b  app/launcher/iori.Xvi
43bdffc45a7c0dc6768fc6115537e29fd4bace8e88b91d723ae12a94f5197835  app/launcher/kagami.Xvi
dbf6e9f3f3b65d0dae91b2ecc7b171a7bd1d628228067cb7a1a39c70d4568ccc  app/launcher/konata.Xvi
1c0a7ac257ea7b7d6e7424c98581f0c88d95f5f10459eeeed98e383bc1446a44  app/launcher/kotori.Xvi
3684811e49899586ac0311f0f66b42ae67736488d5d0747c212d54004d39738c  app/launcher/makoto.Xvi
93db9b4b68fac06bdf3e244ccdb2f202137d18051ba7877f353271714c33020f  app/launcher/miki.Xvi
cd004f7903947da3df3658d213246f757a783aea90da30a22e005d9677c4afe5  app/launcher/minami.Xvi
48b303b53f68c2b5afd2ef55066809a17e48061f426c56970d7e216f694e6a4a  app/launcher/misao.Xvi
aca37d8773253f222328d370f9d2918e06d4ea98e6834da703f913ed015c53f4  app/launcher/miyuki.Xvi
2e2c92a392ce4c75eadb0d28c8303d1578b413cd80902b71272180a6574156a4  app/launcher/paty.Xvi
b3ed260fe9d6d883e5bcf8be08c56b22226a9967bf07d18a706a4a45afa78ccb  app/launcher/ritsuko.Xvi
4108b82c5238b5d60b5ca7096d1b292d2cf6bc6fe08a5e2f084d393a48979c0f  app/launcher/tsukasa.Xvi
3ea13a9aa6da3be713adcbce4683041826f07ffefd2b2ad3d64012f62eeae2f6  app/launcher/yayoi.Xvi
8a69a6051fc20bedefc6260fb8b56c2b690d8f47e1db6242b0d48a21225b1926  app/launcher/yukiho.Xvi
205e9302014efb32337175c8e01f06f4268d5b8198f4586485d73c1067dd937e  app/launcher/yutaka.Xvi
1be80f0c07f3fd981af4781b93f537fc862dc57f18b5ceb0bb009b266232f8df  app/rakimas.ico
13bdf8c8b90c265166f27c3b402fd0013dabb4dc4f1c7c69d33fd04d944699a9  app/wallpaper/img/bg.jpg
9014665d69d4e69994a257716c69f2442ff72be0d45f96400ef2917d7f5a5e65  app/wallpaper/img/frame_body.gif
6eee8c424f8affe35ee39fc891503da5991a082c0994d52aad49114e7154b27e  app/wallpaper/img/frame_foot.gif
5e71becc1098674fc34adab308448a3c7464c72146231775a8990ba1a59adf40  app/wallpaper/img/h2_howto.jpg
7873a0496c8c2f68aafaa834fe76d58ebfc5a854a3ee846f525be3705ee7ea39  app/wallpaper/img/h2_list.jpg
e3bac76c3651c2248f7c355d65d407abdd480b6eed674dc9b9e307442745589a  app/wallpaper/img/head_bg.jpg
04b7cd6a279c4f41ebb80d5b6cbcdbd52477f67c9ee9591c383d260b1502666b  app/wallpaper/img/monitor_size.gif
944bacd1f22ca87ea767bc20893b5852a9e1557b3a6f5a2bd75048c7d43c1089  app/wallpaper/img/thumb_araki.jpg
8f8772802f644d140b050dd5f1b8d418ae58eb1633c2743a87688e2ba5bc0212  app/wallpaper/img/thumb_arata.jpg
de83c91a9b534f1bc89e0627abf715cbddde687b827b8870bb87ca4d33fe7325  app/wallpaper/img/thumb_asaba.jpg
de1577ba2ea7b3e364c1808b5a2ddda9eddba0863a5c30aa01115bfe7fa62dee  app/wallpaper/img/thumb_azuma.jpg
33ab43d4317c9cc92490dbf77c0dff8fbeca6ecacba4e2beb78b6b35f95d843e  app/wallpaper/img/thumb_herada.jpg
479d4971dc2f64e5003101880d535c4674b104fd75c7d95361d90c8e32e839ad  app/wallpaper/img/thumb_iso.jpg
714d560aa8702b77ae33fe947a40ef4005eec1d32a5b17dfe43285fe0e88804c  app/wallpaper/img/thumb_minamo.jpg
79a55c205aef7e0f0bc629408451908b283d294ba526c1f45c8bf8eb0d1c7fc0  app/wallpaper/img/thumb_miso.jpg
494ac102a49c4523f247c03b613b9d59cdaf1370e550b6f5ff9584fe973f26ee  app/wallpaper/img/thumb_miyabi.jpg
4598dbe2fd2874a6f13eddcde05e804608fd8b18fcfe3e32fb9129628b4d76d8  app/wallpaper/img/thumb_serip.jpg
2ad1d35826ce02cc9ed4c5aa9c22cf1b3f1f09e1a19d3f1f1c8be9917463ddd6  app/wallpaper/img/thumb_tanaka.jpg
ffb98dcdbab90b7fffec18de02ae927348cbf742280037d25d7caefe8de164ba  app/wallpaper/img/thumb_uni.jpg
a2512714b5c8742a26edc010581b1f950f965e6f35b5a0473427a560ca8d0a22  app/wallpaper/img/thumb_yone.jpg
e745e207c31acb8ab5a1466d77d90690f28663d60952dca808e4518263a9225c  app/wallpaper/img/tuhmb_gunp.jpg
1c0e4fefdcffefa7570af926b7782c259372c9897d56e0596ecd2accaee67286  app/wallpaper/lib/index.css
3c1684ca74b8051821868a898344c49eaa4363e25ae97e2700cbe4ee7a81ea70  app/wallpaper/lib/interface_scroll.js
c4748a3208104ae0dac75b05003e12c3981d113dd0999361e000b97e383361d1  app/wallpaper/lib/jq_rollover.js
2ea31bf46c7adc2ed09b63eee31737448e655b9ce2732715dbdfd31c003c5f5a  app/wallpaper/lib/jquery-compressed.js
02e277802b801a8d9ff40c3a451bcf136745eebd9fb41e81b68f2b5c59a653e3  app/wallpaper/lib/unit_common.css
d0920cf9c2b5fc937dc30bfc66cad6c86f56b6cecb96f32c8434f83606f9df05  app/wallpaper/らき☆マス_GUNP_1024_768.jpg
d36d12040b79b3c419656c2fe0d966934a8b23c975ad976f2600c1567678c16f  app/wallpaper/らき☆マス_GUNP_1280_1024.jpg
f4164c02d79bb62815d38080b6490bbff5ed6468943c2149f9ea62a3eda08594  app/wallpaper/らき☆マス_GUNP_1280_768.jpg
b1569122f3d631f1d0b0af85cf100715d687252aeca5d1336b03e6d964ae787e  app/wallpaper/らき☆マス_GUNP_1600_1200.jpg
5682eb76c5de099cb2647ed8daa9e41b6a654159237c3aa00ea0235757b1033d  app/wallpaper/らき☆マス_GUNP_1920_1200.jpg
e47360c8a18ca3036cfa7e0b9fd387785cd5404fcb43ebf92d26ef7379f67866  app/wallpaper/らき☆マス_GUNP_800_600.jpg
954e55680b9c47b3b59c006e752d237d53c7aaf0a11933c764d66974e2b85d75  app/wallpaper/らき☆マス_ISO_1024_768.jpg
d51a6779d39613caf80d59679b537d0202d5ac1626d4d442aac2a9930099210a  app/wallpaper/らき☆マス_ISO_1280_1024.jpg
036e71862f50b4c0fa163b0132349c33b8c97c33630fe57ddc570bea57527413  app/wallpaper/らき☆マス_ISO_1280_768.jpg
e87c2ab7e11c9803792aa9a9dcef75aab5412126e1f4fb3b488af154793a14fb  app/wallpaper/らき☆マス_ISO_1600_1200.jpg
9b13dae8c5f016d6c6c69cd1b935d9cf4352a729d4330ccbaaa7f29df917e2a6  app/wallpaper/らき☆マス_ISO_1920_1200.jpg
9e35795bb6efe4c812015f503614f725afd13fb177d1cf295e2b27a165c1b200  app/wallpaper/らき☆マス_ISO_800_600.jpg
ef59c5b2281980e88e4f339f8c4b55d5c34299d672d76f5bc859dc2f0e6f63b3  app/wallpaper/らき☆マス_あさば☆ひろむ_1024_768.jpg
c07a62eece6aa94b3117f8d01b5ed73784aaf989ae6f69ab8a37e53806e46537  app/wallpaper/らき☆マス_あさば☆ひろむ_1280_1024.jpg
ceaeb1360f6afcd803367055160def0a5619e7581cff8fcbdb1ef9038b404c05  app/wallpaper/らき☆マス_あさば☆ひろむ_1280_768.jpg
547d7ad762c129c72caf675bcea2ed8d50185292b14f88b48b839196bb38ac40  app/wallpaper/らき☆マス_あさば☆ひろむ_1600_1200.jpg
5e6099eb15738ef479eb03fe39ac4a24b17596e283f08b606f6522d3e80a909e  app/wallpaper/らき☆マス_あさば☆ひろむ_1920_1200.jpg
728c4e519f674f2f967921fb837ca5b6ae59d895fa5dbdd3bfec112b65eccaf8  app/wallpaper/らき☆マス_あさば☆ひろむ_800_600.jpg
47911b82d74011b6af208cd32b20595cad5d0a81f6f2555f05dd6d3acecd6b2a  app/wallpaper/らき☆マス_あずまゆき_1024_768.jpg
0c642e72f7e38249f6d4afb3a29869ef8102dffa7f3cda87cb64784445d78ae3  app/wallpaper/らき☆マス_あずまゆき_1280_1024.jpg
d05c56f27c6dd977fb6b3247a5492fd36392e455b26be780a30340495da68857  app/wallpaper/らき☆マス_あずまゆき_1280_768.jpg
c5a86bbd6f8d91f613160571fba55e70a07ee8375e1712ebd62889bd263d2762  app/wallpaper/らき☆マス_あずまゆき_1600_1200.jpg
29020763305ec055883991732f07cff36069d3acb5530c18b4682dcf5dd223e0  app/wallpaper/らき☆マス_あずまゆき_1920_1200.jpg
54435bddb13e11e38c3a250c9d12f4fe854b2770b667b9191832ca69fbd8727f  app/wallpaper/らき☆マス_あずまゆき_800_600.jpg
ef625e7144acbc518862a3844aebcfb76a5971866498213fad92771feae08e5d  app/wallpaper/らき☆マス_あらきかなお_1024_768.jpg
e904b74d07e44745f28597ca692861272c5416318bdbfae10be4c4c631c7c235  app/wallpaper/らき☆マス_あらきかなお_1280_1024.jpg
acd9afdac1d7c46104a1d0383bf67acabe5505ca7a3ccd5a7d711a3a589e16ad  app/wallpaper/らき☆マス_あらきかなお_1280_768.jpg
29afa407d9fa98f7f1c421bb04f5f02928cd68f15bff925f593d474c3632e389  app/wallpaper/らき☆マス_あらきかなお_1600_1200.jpg
9d5fd97d35b38eb907b633d6b77b4047b153027eb5357bd6f67fd39ec174fb91  app/wallpaper/らき☆マス_あらきかなお_1920_1200.jpg
3620e4ffbd574e6b342161a2d03dc3ba0a11d87312d411f5a013fd320f673ba3  app/wallpaper/らき☆マス_あらきかなお_800_600.jpg
0adbcc151e96fa0ab64fc917cdcf1468042619fa68ad4030bc683f9d6b69613f  app/wallpaper/らき☆マス_あらたとしひら_1024_768.jpg
b2869d0661711826c8da85fe094e27dcb9e47d0401e61cdcb1a4abb3d6ddef55  app/wallpaper/らき☆マス_あらたとしひら_1280_1024.jpg
4e476b2c701feb8b51ea0d3561d64b77a751a94b29abd45c8a507a98d3b1a767  app/wallpaper/らき☆マス_あらたとしひら_1280_768.jpg
ec4ff1a90e5ab1227d78c500a259baab19024b7a4466a25026c6863252eea03f  app/wallpaper/らき☆マス_あらたとしひら_1600_1200.jpg
f337d3877c615ba2c4bdcc9f425555345a85f0c13b1a902bc24925709b53458b  app/wallpaper/らき☆マス_あらたとしひら_1920_1200.jpg
327f93a0f2fb58fe54ebf0b02d8e5c7843c102513f951c60868a3cae387c8b4d  app/wallpaper/らき☆マス_あらたとしひら_800_600.jpg
de08e2962bc7b954c9bf0ab7393d9edf1b9f6cbc10a5027d5d79b66e7213846b  app/wallpaper/らき☆マス_いしざきうに_1024_768.jpg
e57785df7b98481fc3d24c83e790f5a5a2c90b4d4670172c5f90612208dfe798  app/wallpaper/らき☆マス_いしざきうに_1280_1024.jpg
d68d726f7bae9203a45664a647190ec1610af74bbbb4aeafbc66bc9f1cbb6564  app/wallpaper/らき☆マス_いしざきうに_1280_768.jpg
8a3a54476004d1c172e593756297840b99cca7ba6c14580eb8b460a3a16445e1  app/wallpaper/らき☆マス_いしざきうに_1600_1200.jpg
cc97250384141404cf34dfcb4cddac53daf663588be1adf9b5db56d6a019e8f5  app/wallpaper/らき☆マス_いしざきうに_1920_1200.jpg
c1ca21e600eb1100c8400c4bcad707f432a42225448193d4ec667d820ccfbf3c  app/wallpaper/らき☆マス_いしざきうに_800_600.jpg
3cc6ea5c5b71c10d9d4a870a8159152d9dc8b1ab2b1eb8d159d363998d86d2c0  app/wallpaper/らき☆マス_みそおでん_1024_768.jpg
d48b7669ede767c34e2b1b77e2114b381a28205172e9b9a8077abd0e6b412335  app/wallpaper/らき☆マス_みそおでん_1280_1024.jpg
211c2ccd50a7564890dfc51eed4b7f07d5935d31921baf1ed93e6a238bac28a0  app/wallpaper/らき☆マス_みそおでん_1280_768.jpg
f891f6ebef41ea6863e9f5b0abfd369628699968eaac80388282ef0860e68883  app/wallpaper/らき☆マス_みそおでん_1600_1200.jpg
e3366ad86879dde694bab2b8ad59dd5f76537b459273c15b95c34d3d3715514e  app/wallpaper/らき☆マス_みそおでん_1920_1200.jpg
64565aa802425d2aecd483026a1a2f097060b6449343aae57fc917e9680ee305  app/wallpaper/らき☆マス_みそおでん_800_600.jpg
4415fc6537342438d3b6a10e88f7a3e1171436cfebbf265405305c440f96e40e  app/wallpaper/らき☆マス_ヘラダミツル_1024_768.jpg
f9072b59ae886daf8750a4f90e7791e66d9bb8eb0b61cc740d6c648981005649  app/wallpaper/らき☆マス_ヘラダミツル_1280_1024.jpg
a4615fea11c2fd8a4cf13ff8962444c778dc476089a56085c0aaf5eed26d213b  app/wallpaper/らき☆マス_ヘラダミツル_1280_768.jpg
e2218195db0c8e79dfa2308bb0ce99edaa572f2330a14a514a95c564a34fff4a  app/wallpaper/らき☆マス_ヘラダミツル_1600_1200.jpg
0927d90be76b4d01494fdb7905e6956ac247586ce2afdd200f4a98b25710d13c  app/wallpaper/らき☆マス_ヘラダミツル_1920_1200.jpg
f1d8a6562ababe2a073ad511595502ab89da79749213165ef6270c8626ac90bd  app/wallpaper/らき☆マス_ヘラダミツル_800_600.jpg
29f3e6f7086f934fc326b9b22ef0127838d51f35658714d1c4408b87c8f90192  app/wallpaper/らき☆マス_水萌桜_1024_768.jpg
f5267a454bd8e1b45877362cbf9630a1554f436b35a395ff44f439d99289831f  app/wallpaper/らき☆マス_水萌桜_1280_1024.jpg
bed44857dc8a3b05453abb759bd5a128b26a14c763e7335b898b57618dd6cda0  app/wallpaper/らき☆マス_水萌桜_1280_768.jpg
8f1c67bec005b4576cf760e14c3bca49ce3ace3453ba5ab1a2aa9ee8d112185b  app/wallpaper/らき☆マス_水萌桜_1600_1200.jpg
334bb8b7851e54b6a11ab1b39b45cf79f369d84e7bd85fc12e4f56c92d8a172a  app/wallpaper/らき☆マス_水萌桜_1920_1200.jpg
946138e4b7f054ce99901f3b071e7f9f7ac00d80663674ad8a5d5e51bd78d666  app/wallpaper/らき☆マス_水萌桜_800_600.jpg
fd1f6d2ce71f5912dd26077a4013dcfdfc0ebc90e36058a20d1ed259b40698a0  app/wallpaper/らき☆マス_田中松太郎_1024_768.jpg
9fe95cc9bab82cb550fac63933011d09bcdbc8ade10dd33cd6a821e3244a910d  app/wallpaper/らき☆マス_田中松太郎_1280_1024.jpg
2ad022de18c7c41ead19a675bc4a3c4067acd9780c8ebb369a6cb8d0842a36e7  app/wallpaper/らき☆マス_田中松太郎_1280_768.jpg
ecbe24e8a6462fd90a9f3c5a86ea4c230c29e807f70bb980ea7dfee54605804c  app/wallpaper/らき☆マス_田中松太郎_1600_1200.jpg
a30785b3849cdb4ae5975d8bdd2d0df5fd2ae4dc16b71e15bdf8570a45c97791  app/wallpaper/らき☆マス_田中松太郎_1920_1200.jpg
92168f5fdc9d045bb8ed302154612dd0fcd56548f808e05b0e9c9367c47ea288  app/wallpaper/らき☆マス_田中松太郎_800_600.jpg
6631a93ebdfd5ea476a89881565c9d9428c511faae81df70f0ff524c1cb4157e  app/wallpaper/らき☆マス_芹沢謙_1024_768.jpg
60204ac9c2f3e1be960c051d91008e123aaccda83e1f85dcdfd8ac8c3d9a55d7  app/wallpaper/らき☆マス_芹沢謙_1280_1024.jpg
3c1149691c4a9f1f490fa451808de5686dc3c66a68eb173c3e8ef56ac06e6873  app/wallpaper/らき☆マス_芹沢謙_1280_768.jpg
4124bcac79fae2caafe130199b4d8eab622256e4b420bd69f146bff543351d88  app/wallpaper/らき☆マス_芹沢謙_1600_1200.jpg
4cccb48019f65353a0223b2df5b662e60420e5d5fc9ecb0760846a4af15402f0  app/wallpaper/らき☆マス_芹沢謙_1920_1200.jpg
5a666a588ea55f64c153aea3f829f130027342b64423f136fb1fc830ef45e9d1  app/wallpaper/らき☆マス_芹沢謙_800_600.jpg
7424b663e526ccd87062d83bc8bc7255aa475492b59151c35e095a9ec0e915fb  app/wallpaper/らき☆マス_藤枝雅_1024_768.jpg
56d38c94c07f11cebb1b0288a4c83d260c4f3b33719168a20d488b11c60518d7  app/wallpaper/らき☆マス_藤枝雅_1280_1024.jpg
c38c53f29043faf3c7cb50b8ab64997d7f4d57e1fe0832655070011fdb30f421  app/wallpaper/らき☆マス_藤枝雅_1280_768.jpg
ace4fb25c079ac5140c436763145c4ef6aaf08f0c1d0d9deed7b9ad0b2464389  app/wallpaper/らき☆マス_藤枝雅_1600_1200.jpg
5e0a9cf39765bd7011daf5b48c835f68956d0273d533ae24f629cb5cb6c80885  app/wallpaper/らき☆マス_藤枝雅_1920_1200.jpg
3ff3894d0efa9b11204d719c6c2f6810bb42c7028c853bcf00561968709117eb  app/wallpaper/らき☆マス_藤枝雅_800_600.jpg
063a3d3129f030947d76b98ae4a876a91f41ed60bd950669f48070d7f018656d  app/wallpaper/らき☆マス_高井夜音_1024_768.jpg
66a9ef2f20a09d0d5b16b8459f8c6e648e5e0c0592cd40d43b00728227de0640  app/wallpaper/らき☆マス_高井夜音_1280_1024.jpg
c8db9d1f60c91948520e0168cbd775e9ad29c2b23583a27c5a95024e67a689d5  app/wallpaper/らき☆マス_高井夜音_1280_768.jpg
3e235f8a43b399980022477c8a1b5778cf12eaf789d54b75877c20bf388e60eb  app/wallpaper/らき☆マス_高井夜音_1600_1200.jpg
5859a543003168431889a2362b0deea16b5319065e532c37d8359c394777c903  app/wallpaper/らき☆マス_高井夜音_1920_1200.jpg
4163cc34092b6155c9539780e7944f43cac67bcfa6b6f7d3d15cba3c5f2238d5  app/wallpaper/らき☆マス_高井夜音_800_600.jpg
1a5a7641897bad21e967c0b8dc37accb7213265e8b25b7702a75aa935f0a2cb0  app/wallpaper/壁紙えらび.html
653ef6b53078603194dd8b85e2eb0e720693f9ddb95de3b2ca960231c7e34968  app/お読みください.txt
6b4300590412d0c00bc70a5c0e20dba9aee55a8d1fc29e2874cec23a7be83135  sys/らき☆マス：ちびキャラズ.scr
6b4300590412d0c00bc70a5c0e20dba9aee55a8d1fc29e2874cec23a7be83135  sys/らき☆マス：らき☆すたコミック.scr
6b4300590412d0c00bc70a5c0e20dba9aee55a8d1fc29e2874cec23a7be83135  sys/らき☆マス：アイマス3D.scr
6b4300590412d0c00bc70a5c0e20dba9aee55a8d1fc29e2874cec23a7be83135  sys/らき☆マス：アイマスコミック.scr
```
</details>

---

*Hashes computed from the owner's own disc with `sha256sum` / `md5sum`; PE compile timestamps via
`rz-bin -I`; the Inno Setup version + AppVerName via `innoextract -l`. Regenerate the manifest with
`cd <install-root> && find . -type f | sort | while read f; do sha256sum "$f"; done`.*
