# Changelog

## 1.2.2 (2026-11-08)
- `verify`: サイズ上限超過を「警告」として別集計（NG と区別）、`--show-warnings` 追加
- `docs/tutorial.html`（環境構築〜CD 吸い出し〜変換のチュートリアル）を同梱
- `run.bat` が同じフォルダの `venv` を自動で有効化

## 1.2.0 (2026-11-08)
- **修正**: 差し替えた曲だけ無音になる問題。PSP の libatrac3plus は
  `data サイズ > ((endSample + 先頭オフセット) / フレーム長) × フレームバイト数` と
  `loopEnd <= endSample - 1` を要求する。fact の endSample に末尾の無音パディングを含めないようにした
- `verify` に上記 2 条件の検査を追加
- PPSSPP (headless) で変換 ISO の実再生を確認

## 1.1.0 (2026-11-08)
- `loopfind` コマンド（ループ位置の自動検出、`--near`, `--preview`）
- atracdenc ATRAC3 出力の極性反転を補正

## 1.0.0 (2026-11-07)
- 初版: ISO 展開/再構築、bgm.bin 解析・生成、WAV→ATRAC3 変換、identify、全自動 run
