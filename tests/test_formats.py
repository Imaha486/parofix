# -*- coding: utf-8 -*-
"""ISO 不要の単体テスト:  python -m pytest tests/  または  python tests/test_formats.py"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from parofix.bgmbin import BgmArchive, HEADER_SIZE  # noqa: E402
from parofix.riff import build_riff, AtracInfo, rewrite_atrac_header  # noqa: E402
from parofix.audio import parse_time  # noqa: E402


def fake_at3(frames=10, block=384, end_sample=None, fso=1093, loop=None):
    fmt = struct.pack("<HHIIHH", 0x270, 2, 44100, 16537, block, 0) + bytes.fromhex("0e000100001000000000000001000000")
    data = bytes(frames * block)
    riff = build_riff([(b"fmt ", fmt), (b"data", data)])
    return rewrite_atrac_header(riff, end_sample or max(1, frames * 1024 - 2048), fso, loop)


def test_bgm_roundtrip():
    arc = BgmArchive()
    arc.tracks = [fake_at3(3), fake_at3(7), fake_at3(1)]
    blob = arc.build()
    assert blob[0] == 3
    assert struct.unpack_from("<I", blob, 1)[0] == HEADER_SIZE
    arc2 = BgmArchive(blob)
    assert arc2.tracks == arc.tracks
    assert arc2.build() == blob


def test_riff_header():
    t = fake_at3(10, end_sample=5000, loop=(100, 4999))
    info = AtracInfo(t)
    assert info.codec == "ATRAC3" and info.bitrate_kbps == 132
    assert info.end_sample == 5000 and info.first_sample_offset == 1093
    assert info.loop == (100 + 1093, 4999 + 1093)
    assert info.loop_real() == (100, 4999)


def test_parse_time():
    assert parse_time("1:23.456") == round(83.456 * 44100)
    assert parse_time("12.5s") == round(12.5 * 44100)
    assert parse_time(123456) == 123456
    assert parse_time("123456") == 123456


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
