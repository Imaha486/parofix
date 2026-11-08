# 同梱バイナリ (bin/atracdenc, bin/atracdenc.exe) のビルド手順

`bin/` の atracdenc は LGPL-2.1 のオープンソース実装
[dcherednik/atracdenc](https://github.com/dcherednik/atracdenc)
（コミット `cb170709f836cb43dc0312455188c791159d81dc`）を、libsndfile 1.2.2 と共に静的リンクしたものです。
同じものは以下で再現できます（Ubuntu 24.04 で確認）。

## Linux 版

```bash
sudo apt install build-essential cmake ninja-build libsndfile1-dev
git clone https://github.com/dcherednik/atracdenc.git && cd atracdenc
git checkout cb170709f836cb43dc0312455188c791159d81dc
git submodule update --init --recursive
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DATRACDENC_PCM_IO_BACKEND=libsndfile -DBUILD_TESTING=OFF
cmake --build build -j
strip build/src/atracdenc
```

## Windows 版（Linux 上で MinGW-w64 クロスコンパイル）

`tools/build_atracdenc_win.sh` を実行すると、libsndfile を静的ビルドしたうえで
atracdenc.exe（外部 DLL 依存なし、KERNEL32/msvcrt/SHELL32 のみ）を生成します。

```bash
sudo apt install g++-mingw-w64-x86-64 cmake ninja-build
bash tools/build_atracdenc_win.sh
# -> bin/atracdenc.exe
```

Windows 上で直接ビルドする場合は atracdenc の README（MSYS2 / MSVC の手順）を参照してください。
