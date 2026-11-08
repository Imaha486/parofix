# -*- coding: utf-8 -*-
"""RIFF/WAVE チャンクの読み書き（AT3/AT3+ ヘッダ解析、smpl ループ付与）"""
import struct

WAVE_FORMAT_AT3 = 0x0270
WAVE_FORMAT_EXTENSIBLE = 0xFFFE


def parse_riff(data: bytes):
    """-> list[(chunk_id(bytes), payload(bytes))]  (RIFF/WAVE ヘッダ 12 バイトは除く)"""
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("RIFF/WAVE ではありません")
    total = struct.unpack_from("<I", data, 4)[0] + 8
    total = min(total, len(data))
    chunks = []
    p = 12
    while p + 8 <= total:
        cid = data[p:p + 4]
        sz = struct.unpack_from("<I", data, p + 4)[0]
        body = data[p + 8:p + 8 + sz]
        chunks.append((cid, body))
        p += 8 + sz + (sz & 1)
    return chunks


def build_riff(chunks):
    body = bytearray(b"WAVE")
    for cid, payload in chunks:
        body += cid + struct.pack("<I", len(payload)) + payload
        if len(payload) & 1:
            body += b"\x00"
    return b"RIFF" + struct.pack("<I", len(body)) + bytes(body)


class AtracInfo:
    """AT3 / AT3+ RIFF の要約"""

    def __init__(self, data: bytes):
        self.chunks = parse_riff(data)
        self.fmt_tag = None
        self.channels = None
        self.sample_rate = None
        self.byte_rate = None
        self.block_align = None
        self.end_sample = None
        self.first_sample_offset = 0
        self.loop = None  # (start, end)  smpl に書かれた生の値
        self.data_size = 0
        for cid, b in self.chunks:
            if cid == b"fmt ":
                (self.fmt_tag, self.channels, self.sample_rate,
                 self.byte_rate, self.block_align) = struct.unpack_from("<HHIIH", b, 0)
            elif cid == b"fact":
                if len(b) >= 4:
                    self.end_sample = struct.unpack_from("<I", b, 0)[0]
                if len(b) >= 8:
                    self.first_sample_offset = struct.unpack_from("<I", b, 4)[0]
            elif cid == b"smpl":
                nloops = struct.unpack_from("<I", b, 28)[0]
                if nloops >= 1 and len(b) >= 36 + 24:
                    s, e = struct.unpack_from("<II", b, 36 + 8)
                    self.loop = (s, e)
            elif cid == b"data":
                self.data_size = len(b)

    @property
    def codec(self):
        if self.fmt_tag == WAVE_FORMAT_AT3:
            return "ATRAC3"
        if self.fmt_tag == WAVE_FORMAT_EXTENSIBLE:
            return "ATRAC3plus"
        return f"unknown({self.fmt_tag})"

    @property
    def bitrate_kbps(self):
        if not self.block_align:
            return 0
        table = {280: 48, 376: 64, 560: 96, 744: 128, 936: 160, 1120: 192, 1488: 256, 1864: 320, 2048: 352,
                 192: 66, 304: 105, 384: 132}
        if self.block_align in table:
            return table[self.block_align]
        spf = 2048 if self.fmt_tag == WAVE_FORMAT_EXTENSIBLE else 1024
        return round(self.block_align * 8 * 44100 / spf / 1000)

    @property
    def duration_sec(self):
        return (self.end_sample or 0) / 44100.0

    def loop_real(self):
        """ループ位置（実サンプル位置 = smpl 値 - first_sample_offset）"""
        if not self.loop:
            return None
        return (self.loop[0] - self.first_sample_offset, self.loop[1] - self.first_sample_offset)

    def describe(self):
        lp = self.loop_real()
        loop_s = f"loop {lp[0]}-{lp[1]} ({lp[0]/44100:.2f}s-{lp[1]/44100:.2f}s)" if lp else "loop なし"
        return (f"{self.codec} {self.bitrate_kbps}kbps ch={self.channels} "
                f"{self.duration_sec:7.2f}s samples={self.end_sample} fso={self.first_sample_offset} {loop_s}")


def make_smpl_chunk(loop_start: int, loop_end: int) -> bytes:
    """PSP (at3tool) 互換の smpl チャンク: ループ 1 個"""
    hdr = struct.pack("<9I", 0, 0, 22676, 60, 0, 0, 0, 1, 24)
    loop = struct.pack("<6I", 0, 0, loop_start, loop_end, 0, 0)
    return hdr + loop


def rewrite_atrac_header(data: bytes, end_sample: int, first_sample_offset: int,
                         loop=None) -> bytes:
    """
    エンコーダ出力 (RIFF) の fact / smpl を書き換える。
    loop: (start, end) 実サンプル位置。None ならループなし。
    """
    chunks = parse_riff(data)
    fmt = None
    datab = None
    others = []
    for cid, b in chunks:
        if cid == b"fmt ":
            fmt = b
        elif cid == b"data":
            datab = b
        elif cid in (b"fact", b"smpl"):
            continue
        else:
            others.append((cid, b))
    if fmt is None or datab is None:
        raise ValueError("fmt/data チャンクがありません")
    fact = struct.pack("<II", end_sample, first_sample_offset)
    out = [(b"fmt ", fmt), (b"fact", fact)]
    if loop is not None:
        ls, le = loop
        out.append((b"smpl", make_smpl_chunk(ls + first_sample_offset, le + first_sample_offset)))
    out += others
    out.append((b"data", datab))
    return build_riff(out)
