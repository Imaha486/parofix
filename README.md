# parofix — パロディウス ポータブル (PSP) BGM 差し替えツールセット

**parofix** restores the BGM tracks of *Parodius Portable* (PSP, ULJM-05220) that were replaced for
licensing reasons, using your own rip of the soundtrack CD *Music from Konami Arcade Shooting*.
It parses the game's `bgm.bin` archives, encodes WAV to PSP-playable ATRAC3 with correct loop points,
and rebuilds the ISO. Pure Python 3.8+ (numpy only) plus a bundled open-source ATRAC encoder. Documentation is in Japanese.

* 初めての方は **[docs/tutorial.html](docs/tutorial.html)**（環境構築から変換までの手順）をどうぞ
* 作者: Imaha486 / 変更履歴: [CHANGELOG.md](CHANGELOG.md) / ライセンス: MIT（同梱バイナリは LGPL、[LICENSE](LICENSE) 参照）
* 参考記事: https://i486.mods.jp/ichild/parofix

PSP『パロディウス ポータブル』(ULJM-05220) の UMD イメージ (ISO) に含まれる BGM アーカイブを解析し、
CD からリッピングした音源（『ミュージック フロム コナミアーケードシューティング』など）で
差し替えて `元のファイル名_converted.iso` を作るためのツール群です。

```
ISO 展開 / 再構築   …… parofix.py iso-extract / iso-build   (ISO9660 を自前で読み書き。外部ライブラリ不要)
BGM アーカイブ操作  …… parofix.py bgm-list / bgm-extract / bgm-build / bgm-replace
WAV → ATRAC 変換    …… parofix.py encode                      (同梱 atracdenc、または Sony at3tool)
曲の自動識別        …… parofix.py identify / menu-map        (CD 音源とゲーム内曲の照合, ffmpeg 使用)
全自動              …… parofix.py run <設定ファイル>
```

---

## 1. 必要なもの

| 必須 | 内容 |
|---|---|
| Python 3.8 以上 | https://www.python.org/ （インストール時に "Add python.exe to PATH" を ON） |
| numpy | `pip install numpy` |
| UMDから吸い出した ISO | `PARODIUS-PORTABLE.ISO` にリネーム |
| CD 音源 | 44.1kHz / 16bit の WAV 推奨（他形式・他レートは ffmpeg があれば自動変換） |

| 任意 | 内容 |
|---|---|
| ffmpeg | `identify` / `menu-map` / `bgm-extract --wav`（AT3+ のデコード）に必要。`bin\ffmpeg.exe` に置くか PATH を通す |
| at3tool.exe | Sony 製 ATRAC3plus エンコーダ。あればオリジナルと同じ AT3+ 64kbps で差し替えられる（後述） |

同梱物:

```
parofix.py                 起動スクリプト
parofix/                   本体 (Python)
bin/atracdenc.exe          ATRAC3 エンコーダ Windows 64bit 版（オープンソース atracdenc を静的ビルド）
bin/atracdenc              同 Linux x86_64 版
bin/licenses/              atracdenc / libsndfile のライセンス (LGPL)
config/parodius_portable.json  設定ファイルの雛形
config/my_config_example.json  実際の CD 音源 3 曲で loopfind した値を入れた設定例
run.bat                    Windows 用: 設定ファイルをドラッグ＆ドロップで全自動実行
```

---

## 2. いちばん簡単な使い方（全自動）

1. `config\parodius_portable.json` をコピーして編集する
   * `"iso"` … ISO のファイル名（設定ファイルからの相対パス可）
   * `replacements` の各行の `"wav"` を CD 音源のファイル名に、`loop_start` / `loop_end` を
     その音源のループ位置に書き換える（§4 参照）
2. 実行
   ```
   python parofix.py run my_config.json
   ```
   または `run.bat` に設定ファイルをドラッグ＆ドロップ
3. `PARODIUS-PORTABLE_converted.ISO` ができる。`PARODIUS-PORTABLE_work\` に生成した .at3 と bgm.bin も残る

処理内容: ISO から対象の bgm.bin を読み出し → 指定トラックを CD 音源からエンコードした RIFF/ATRAC に差し替え →
bgm.bin を再生成 → ファイル領域を詰め直した新しい ISO を書き出し → 出来上がりを再読込して検査。

---

## 3. 解析でわかったこと（仕様メモ）

### 3.1 各ゲームの BGM アーカイブ

| target | ISO 内パス | ゲーム | 曲数 |
|---|---|---|---|
| `paro2` | `PSP_GAME/USRDIR/CDData/sound/BGM/bgm.bin` | パロディウスだ! | 34 |
| `paro4` | `PSP_GAME/USRDIR/data1/sound/BGM/bgm.bin` | 極上パロディウス | 46 |
| `paro3` | `PSP_GAME/USRDIR/data/sound/BGM/bgm.bin` | 実況おしゃべりパロディウス | 52 |
| `paro5` | `PSP_GAME/USRDIR/data/p5/sound/BGM/at3bgm.bin` | セクシーパロディウス | 43 |
| `msx` | `PSP_GAME/USRDIR/data/mxs/msx_paro_bgm.bin` | パロディウス (MSX) | 15 |
| `menu` | `PSP_GAME/USRDIR/data/menu/AllBgmbgm.bin` | ミュージックプレイヤーモード | 232 |

（`paroN_rel.bin` 実行モジュール内の `disc0:/...` パス文字列から特定。ISO 内に開発用ヘッダ `bgmcallno.h` が
残っており、極上・実況・セクシーはトラック名が判明しています。`bgm-list` で表示されます）

### 3.2 アーカイブ形式（"BgmPackTool" 形式）

```
+0x000  u8   トラック数 N
+0x001  (u32 オフセット, u24 確保サイズ) × N   ※7 バイト刻み
+0x800  トラック 0 本体, 以降 0x800 境界に整列
```
各トラックは RIFF/WAVE 形式の ATRAC3plus（44.1kHz ステレオ、ゲーム内 64kbps、ミュージックモード 96kbps）で、
`smpl` チャンクにループ位置が入っています。本ツールの読み書きは全アーカイブでバイト単位の往復一致を確認済みです。

### 3.3 ゲーム側の再生方法と制約

実行モジュールの逆アセンブルから、BGM は次のように再生されています。

* 1 曲分をメモリに読み込み、`sceAtracSetHalfwayBufferAndGetID` → `sceAtracGetSoundSample` → `sceAtracSetLoopNum`
  で再生。ヘッダの解釈（コーデック判別・ループ）は PSP の `sceAtrac3plus` ライブラリ任せ
  → ライブラリが対応する **ATRAC3 (非 plus) の RIFF もそのまま再生可能**
* 1 曲分のバッファ上限: ゲーム内 **0x180000 (1.5MB)**、ミュージックモード 0x480000 (4.5MB)。
  本ツールはこれを超えるとエラーにし、atracdenc 使用時は 132kbps → 66kbps へ自動で落とします
  （132kbps で約 95 秒、ループ 1 周分を切り出せば通常は十分です）

### 3.4 差し替えられている曲（Wikipedia / 攻略 wiki の記述による）

| ゲーム | 場面 | 原曲 | PSP 版 | 本ツールでの target / index |
|---|---|---|---|---|
| パロディウスだ! | ステージ4 (日本) | 剣の舞 | ハンガリー舞曲第5番 | `paro2` / **7 (推定・要確認)** |
| 極上パロディウス | ステージ1 (クレーン) | イン・ザ・ムード | 藁の中の七面鳥 | `paro4` / **11** (12SD_BGM1) |
| 極上パロディウス | ステージ3 ボス | マンボ No.5 | おもちゃの兵隊の観兵式 | `paro4` / **17** (18SD_BOSS3) |
| 実況おしゃべり | ステージ1 (ソウル) | ザッツ・ザ・ウェイ | BRILLIANT 2U | `paro3` / identify で確認 |
| 実況おしゃべり | ボーナス2 (サーキット) | P1-Grand Prix のテーマ | PARUTH | `paro3` / identify で確認 |
| セクシー | ステージ1 イントロ, 3A ボス, 4A | （複数） | （複数） | `paro5` / identify で確認 |

極上の 2 曲は開発用ヘッダの名前 (`12SD_BGM1`, `18SD_BOSS3`) から確定です。
パロディウスだ! は名前が残っていないため、曲長・ループ構造・ミュージックモードとの照合から **index 7
（62 秒, ループ 3.0s→60.4s）が最有力**と推定しています（次点は index 4）。`identify` で確認してください。

ミュージックモード (`menu`) 側の対応トラックは、クロマ特徴量による自動照合で
`paro2 #7 → menu 42`、`paro4 #17 → menu 76` を得ています（`parofix/games.py` の `MENU_MAP`）。
`paro4 #11`（極上 ST1）はミュージックモード側で同一曲が見つからず、候補は `menu 69` です。

---

## 4. 設定ファイルの書き方

```json
{
  "iso": "PARODIUS-PORTABLE.ISO",
  "defaults": { "encoder": "atracdenc", "bitrate": 132, "gain_db": 0 },
  "replacements": [
    { "target": "paro4", "index": 11, "wav": "cd/05 In The Mood.wav",
      "loop_start": "0:03.910", "loop_end": "0:50.870",
      "also_music_mode": true, "menu_index": 69 }
  ]
}
```

| キー | 意味 |
|---|---|
| `target` | `paro2` / `paro4` / `paro3` / `paro5` / `msx` / `menu`、または ISO 内パスを直接 |
| `index` | トラック番号（0 始まり）。`bgm-list` で一覧表示 |
| `wav` | 音源ファイル |
| `loop_start` | ループ開始。`"1:23.456"`（分:秒）、`"12.5s"`（秒）、`123456`（サンプル数）|
| `loop_end` | ループ終了。**2 周目で `loop_start` と同じ音になる位置**。音声はここで切られます |
| `end` | （任意）`loop_end` より後ろまで残したい時の終了位置 |
| `no_loop` | `true` でループなし（`fade_out` でフェード長を指定可） |
| `gain_db` | 音量補正 dB |
| `also_music_mode` | ミュージックモードの対応曲も同時に差し替え |
| `menu_index` | ミュージックモード側の番号（省略時は内蔵対応表） |
| `encoder` / `bitrate` | 行ごとの上書きも可 |

### ループ位置の自動検出 (`loopfind`)
```
python parofix.py loopfind cd\gokupa_st1_in_the_mood.flac --preview seam.wav
python parofix.py loopfind cd\gokupa_st1_in_the_mood.flac --near 0:10.02 --preview seam.wav
```
スペクトログラムの自己類似度で「1 周の長さ」を求め、1 周目と 2 周目の継ぎ目（loop_end の直後に鳴る音と
loop_start の直後に鳴る音）の波形一致度が最大になる位置をサンプル単位で探します。
`--near` でおおよそのループ開始位置（曲の切れ目）を与えると、その付近で最も滑らかに繋がる点を選びます。
`--preview` で継ぎ目だけを繰り返した確認用 WAV を書き出せます。
アーケード基板録音は 1 周目と 2 周目でテンポがわずかに揺れるため、継ぎ目一致度は 1.0 にならず 0.8〜0.97 程度が実用値です。

### ループ位置を手で決める場合
CD 音源は「イントロ → 1 周目 → 2 周目 → フェードアウト」が普通です。
Audacity 等で、1 周目の始まり (`loop_start`) と、2 周目の同じ箇所 (`loop_end`) をサンプル単位で読み取ってください。
`loop_end` 以降（フェード部分）は捨てられ、ゲーム内では `loop_start` に戻って無限ループします。
参考として `bgm-list` は元の PSP トラックのループ位置（秒）を表示するので、
元トラックとほぼ同じ長さになるよう合わせると違和感がありません。WAV に `smpl` ループが書き込んであれば自動で使います。

---

## 5. 曲の識別 (`identify`)

```
python parofix.py identify --iso PARODIUS-PORTABLE.ISO --target paro2 --cd-dir "cd\paroda"
```
CD 音源フォルダ内の全ファイルとゲーム内全トラックを照合し、

* ゲーム内トラックごとに最も近い CD 曲とスコア（同一曲なら 0.8〜1.0）
* **CD に一致する曲が無いゲーム内スロット = 差し替えられている曲**
* **ゲーム内に一致しない CD 曲 = 差し替えられた原曲**

を表示します。両者を組み合わせて `index` と `wav` を決めてください。
（ffmpeg が必要。曲数 × 曲数の照合なので数分かかることがあります）

`bgm-extract --wav` でゲーム内トラックを WAV に書き出して耳で確認することもできます:
```
python parofix.py bgm-extract --iso PARODIUS-PORTABLE.ISO --target paro2 out_paro2 --wav
```

---

## 6. 個別コマンド

```
python parofix.py iso-list    PARODIUS-PORTABLE.ISO
python parofix.py iso-extract PARODIUS-PORTABLE.ISO extracted\
python parofix.py iso-build   PARODIUS-PORTABLE.ISO --from-dir extracted\ -o out.iso
python parofix.py iso-build   PARODIUS-PORTABLE.ISO -r PSP_GAME/USRDIR/data1/sound/BGM/bgm.bin=new_bgm.bin

python parofix.py bgm-list    --iso PARODIUS-PORTABLE.ISO --target paro4
python parofix.py bgm-extract --iso PARODIUS-PORTABLE.ISO --target paro4 out\ [--wav]
python parofix.py bgm-replace --file bgm.bin --set 11=track11.at3 --set 17=track17.at3 -o new_bgm.bin
python parofix.py bgm-build   --dir at3folder\ -o new_bgm.bin      (000.at3, 001.at3 … の順)

python parofix.py encode in.wav -o out.at3 --loop-start 0:03.9 --loop-end 0:50.87 [--bitrate 132|66] [--encoder at3tool --at3tool at3tool.exe]
python parofix.py loopfind in.flac [--near 0:10.0] [--preview seam.wav]   (ループ位置の自動検出)
python parofix.py verify  --iso out.iso                           (PSP が受け付ける形式か検査)
python parofix.py menu-map --iso PARODIUS-PORTABLE.ISO --target paro4 --menu-range 65 107
python parofix.py run config.json [--append] [--no-iso]
```

ISO の再構築は既定で「ファイル領域を詰め直す」方式（ディレクトリやボリューム記述子は元のまま、
ファイル本体だけ順番に再配置）です。`--append` を付けると元の配置を一切動かさず末尾追記で差し替えます
（互換性は同じですが ISO が大きくなります）。どちらも PPSSPP / CFW 用の通常の ISO9660 イメージです。

---

## 7. エンコーダについて

### atracdenc（同梱・既定）
オープンソースの ATRAC エンコーダ (https://github.com/dcherednik/atracdenc, LGPL) を Windows 向けに
静的ビルドしたものです。**ATRAC3 132kbps (LP2)** で出力します。PSP の `sceAtrac3plus` ライブラリは
ATRAC3 と ATRAC3plus の両方を再生できるため、ゲーム側の変更なしで動きます。
（atracdenc の ATRAC3plus エンコーダは現状 352kbps 固定でバッファ上限を超えるため使用しません）

実測したエンコーダ遅延 (1162 サンプル) と極性反転を補正済みで、ループ位置は元音源どおりになります。

### at3tool（Sony 製・任意）
PSP SDK 付属の `at3tool.exe` をお持ちなら、オリジナルと同じ **ATRAC3plus 64kbps** で差し替えられます。
```json
"defaults": { "encoder": "at3tool", "bitrate": 64, "at3tool_path": "C:/tools/at3tool.exe" }
```
コマンドラインは既定 `-e -br {bitrate} {in} {out}`。違う場合は `"at3tool_args"` で変更できます。
ループ情報 (`smpl`) は本ツールが付加します。

---

## 8. 動作確認について

* 生成した ISO は、元 ISO と比較して差し替えた bgm.bin 以外の全ファイルが同一であることを検証済み
* 差し替えトラックは ffmpeg でデコードして元音源と波形一致（遅延補正後の相関 0.997）を確認済み
* PPSSPP（headless ビルド）で変換後 ISO を起動し、ミュージックモードおよび極上パロディウス ステージ1 で
  差し替えた ATRAC3 トラックが `sceAtracSetHalfwayBufferAndGetID` に受理され、音声出力が CD 音源と一致することを確認済み
* 実機 (CFW) での確認は未実施です

### libatrac3plus の隠れた要件（v1.2 で修正）
PSP の `sceAtrac` ライブラリ（PPSSPP の正確な再実装 `Atrac2` で確認）は RIFF ヘッダに対して

* `smpl` の loopEnd ≦ `fact` の endSample − 1
* `data` チャンクのバイト数 ＞ ((endSample + 先頭オフセット + 0x45) ÷ 1024) × フレームバイト数

を要求し、満たさないと `SCE_ERROR_ATRAC_BAD_CODEC_PARAMS (0x80630008)` で無音になります。
v1.1 以前は endSample に末尾の無音パディングまで含めていたため後者を満たさず、差し替え曲だけ鳴りませんでした。
v1.2 では endSample = 実音声長（ループ曲は loop_end + 1）とし、パディング（8192 サンプル）を endSample に含めないようにしています。
`verify` コマンドもこの 2 条件を検査します。

## 9. 注意
* ISO と CD 音源は正規に所有するものをお使いください。生成物（ISO・bgm.bin・.at3）の配布はしないでください。
  このリポジトリにはゲームデータや CD 音源は一切含まれていません。
* 元 ISO は書き換えません（常に新しいファイルに出力します）。
* 本ツールは KONAMI とは無関係の非公式ツールです。

## 10. 開発者向け
* 単体テスト: `python tests/test_formats.py`（ISO 不要）
* 同梱バイナリの再ビルド: [docs/BUILD-atracdenc.md](docs/BUILD-atracdenc.md)
* PSP 側の制約（libatrac3plus の RIFF 要件）の根拠は PPSSPP の `Core/HLE/AtracCtx2.cpp` / `Core/Util/AtracTrack.cpp`
