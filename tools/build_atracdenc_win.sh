#!/bin/bash
# atracdenc.exe を Linux 上で MinGW-w64 クロスビルドする（libsndfile 静的リンク）
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK=${WORK:-/tmp/atracdenc-win-build}
ATRACDENC_COMMIT=cb170709f836cb43dc0312455188c791159d81dc
SNDFILE_VER=1.2.2
mkdir -p "$WORK" && cd "$WORK"

cat > mingw.cmake <<EOT
set(CMAKE_SYSTEM_NAME Windows)
set(CMAKE_SYSTEM_PROCESSOR x86_64)
set(CMAKE_C_COMPILER x86_64-w64-mingw32-gcc-posix)
set(CMAKE_CXX_COMPILER x86_64-w64-mingw32-g++-posix)
set(CMAKE_RC_COMPILER x86_64-w64-mingw32-windres)
set(CMAKE_FIND_ROOT_PATH /usr/x86_64-w64-mingw32 $WORK/prefix)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
EOT

# libsndfile (static, no external codecs)
if [ ! -f prefix/lib/libsndfile.a ]; then
  curl -sSL -o libsndfile.tar.xz https://github.com/libsndfile/libsndfile/releases/download/$SNDFILE_VER/libsndfile-$SNDFILE_VER.tar.xz
  tar xf libsndfile.tar.xz
  cmake -S libsndfile-$SNDFILE_VER -B sf_build -DCMAKE_TOOLCHAIN_FILE=$WORK/mingw.cmake -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_SHARED_LIBS=OFF -DENABLE_EXTERNAL_LIBS=OFF -DENABLE_MPEG=OFF -DBUILD_PROGRAMS=OFF -DBUILD_EXAMPLES=OFF \
    -DBUILD_TESTING=OFF -DENABLE_CPACK=OFF -DCMAKE_INSTALL_PREFIX=$WORK/prefix
  cmake --build sf_build -j && cmake --install sf_build
fi

# atracdenc
if [ ! -d atracdenc ]; then
  git clone https://github.com/dcherednik/atracdenc.git
  (cd atracdenc && git checkout $ATRACDENC_COMMIT && git submodule update --init --recursive)
fi
cmake -S atracdenc -B at_build -DCMAKE_TOOLCHAIN_FILE=$WORK/mingw.cmake -DCMAKE_BUILD_TYPE=Release \
  -DATRACDENC_PCM_IO_BACKEND=libsndfile -DBUILD_TESTING=OFF \
  -DLIBSNDFILE_INCLUDE_DIR=$WORK/prefix/include -DSNDFILE_LIBRARIES=$WORK/prefix/lib/libsndfile.a \
  -DCMAKE_EXE_LINKER_FLAGS="-static -static-libgcc -static-libstdc++"
cmake --build at_build -j
x86_64-w64-mingw32-strip -o "$ROOT/bin/atracdenc.exe" at_build/src/atracdenc.exe
cp atracdenc/LICENSE "$ROOT/bin/licenses/atracdenc-LICENSE.txt"
cp libsndfile-$SNDFILE_VER/COPYING "$ROOT/bin/licenses/libsndfile-COPYING.txt"
echo "built: $ROOT/bin/atracdenc.exe"
