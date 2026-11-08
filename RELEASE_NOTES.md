# parofix v1.2.2

PSP『パロディウス ポータブル』で権利上の理由により差し替えられた BGM
（パロディウスだ! ステージ4、極上パロディウス ステージ1・ステージ3ボス など）を、
手持ちのサウンドトラック CD の音源で復元するツールセットです。

## 使い方
1. `parofix-v1.2.2-win64.zip` を展開
2. `docs/tutorial.html` の手順どおりに Python / venv / numpy を用意
3. CD から 3 トラックを WAV で吸い出して `cd/` に置く
4. `python parofix.py run my_config.json` → `PARODIUS-PORTABLE_converted.ISO`

## 同梱物
- Python ツール本体（ISO 展開・再構築、bgm.bin 解析/生成、WAV→ATRAC3 変換、ループ検出、曲の識別、検査）
- `bin/atracdenc.exe` / `bin/atracdenc`（オープンソース ATRAC3 エンコーダの静的ビルド、LGPL）
- 設定ファイル例、チュートリアル HTML

## 動作確認
- PPSSPP: 変換 ISO の極上パロディウス ステージ1 / ミュージックモードで再生を確認
- 実機 CFW: 報告をお待ちしています

ゲームデータ・CD 音源は含まれません。正規に所有するものをお使いください。
