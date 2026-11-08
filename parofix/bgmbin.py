# -*- coding: utf-8 -*-
"""
パロディウス ポータブルの BGM アーカイブ (bgm.bin / at3bgm.bin / AllBgmbgm.bin) の読み書き

形式（PSP 版実行ファイルの解析結果、"BgmPackTool" 生成）:
    +0      u8   トラック数 N (最大 255)
    +1+7*i  u32  トラック i のデータ先頭オフセット（ファイル先頭から, 0x800 境界）
    +5+7*i  u24  トラック i の確保サイズ（0x800 の倍数）
    ヘッダは 0x800 バイトで、トラックデータは 0x800 から並ぶ
    各トラックは RIFF/WAVE 形式の ATRAC3plus（44.1kHz ステレオ）、smpl チャンクにループ情報
"""
import struct

ALIGN = 0x800
HEADER_SIZE = 0x800


def _align(n, a=ALIGN):
    return (n + a - 1) // a * a


class BgmArchive:
    def __init__(self, data: bytes = b""):
        self.tracks = []  # list[bytes]（RIFF 1 本ずつ、パディングは含まない）
        if data:
            self._parse(data)

    @classmethod
    def load(cls, path):
        with open(path, "rb") as f:
            return cls(f.read())

    def _parse(self, d: bytes):
        n = d[0]
        if n == 0:
            raise ValueError("トラック数が 0 です")
        for i in range(n):
            off = struct.unpack_from("<I", d, 1 + 7 * i)[0]
            alloc = int.from_bytes(d[5 + 7 * i:8 + 7 * i], "little")
            if off + 8 > len(d) or d[off:off + 4] != b"RIFF":
                raise ValueError(f"トラック {i}: RIFF ヘッダがありません (offset={off:#x})")
            riff_size = struct.unpack_from("<I", d, off + 4)[0] + 8
            size = min(riff_size, alloc) if alloc else riff_size
            self.tracks.append(bytes(d[off:off + size]))

    def build(self) -> bytes:
        n = len(self.tracks)
        if not 1 <= n <= 255:
            raise ValueError("トラック数は 1〜255 の範囲である必要があります")
        if 1 + 7 * n > HEADER_SIZE:
            raise ValueError("ヘッダ領域 (0x800) に収まりません")
        header = bytearray(HEADER_SIZE)
        header[0] = n
        out = bytearray()
        off = HEADER_SIZE
        for i, t in enumerate(self.tracks):
            alloc = _align(len(t))
            if alloc >= 1 << 24:
                raise ValueError(f"トラック {i} が大きすぎます ({len(t)} bytes)")
            struct.pack_into("<I", header, 1 + 7 * i, off)
            header[5 + 7 * i:8 + 7 * i] = alloc.to_bytes(3, "little")
            out += t
            out += b"\x00" * (alloc - len(t))
            off += alloc
        return bytes(header) + bytes(out)

    def save(self, path):
        with open(path, "wb") as f:
            f.write(self.build())

    def __len__(self):
        return len(self.tracks)
