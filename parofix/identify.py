# -*- coding: utf-8 -*-
"""
クロマ特徴量（12 音階エネルギー）による曲の照合

用途:
  * CD リッピング WAV と、ゲーム内 BGM アーカイブの各トラックを突き合わせ、
    「どのトラック番号がどの曲か」「CD に対応曲が無い（= 差し替えられた）スロットはどれか」を推定する
  * ゲーム内トラックとミュージックモード (AllBgmbgm.bin) の対応表作成
AT3/AT3+ のデコードに ffmpeg を使う。
"""
import os
import subprocess
import tempfile

import numpy as np

from .audio import find_tool

SR = 11025
NFFT = 2048
HOP = 1024


def _decode_to_mono(src_path, ffmpeg):
    with tempfile.TemporaryDirectory() as td:
        tmp = os.path.join(td, "m.wav")
        subprocess.run([ffmpeg, "-v", "error", "-y", "-i", src_path, "-ac", "1", "-ar", str(SR),
                        "-c:a", "pcm_s16le", tmp], check=True)
        with open(tmp, "rb") as f:
            d = f.read()
    # data チャンクを探す
    p = 12
    while p + 8 <= len(d):
        cid = d[p:p + 4]
        sz = int.from_bytes(d[p + 4:p + 8], "little")
        if cid == b"data":
            return np.frombuffer(d[p + 8:p + 8 + sz], dtype="<i2").astype(np.float32)
        p += 8 + sz + (sz & 1)
    raise ValueError("WAV data chunk not found")


_PC = None


def _pitch_classes():
    global _PC
    if _PC is None:
        freqs = np.fft.rfftfreq(NFFT, 1 / SR)
        pc = np.full(len(freqs), -1)
        m = (freqs > 60) & (freqs < 4000)
        pc[m] = (np.round(12 * np.log2(freqs[m] / 440.0)) % 12).astype(int)
        _PC = pc
    return _PC


def chroma(a: np.ndarray):
    pc = _pitch_classes()
    frames = max(0, (len(a) - NFFT) // HOP)
    out = np.zeros((frames, 12), dtype=np.float64)
    win = np.hanning(NFFT)
    masks = [pc == k for k in range(12)]
    for i in range(frames):
        X = np.abs(np.fft.rfft(a[i * HOP:i * HOP + NFFT] * win)) ** 2
        for k in range(12):
            out[i, k] = X[masks[k]].sum()
    out = np.log1p(out)
    out -= out.mean(1, keepdims=True)
    out /= (np.linalg.norm(out, axis=1, keepdims=True) + 1e-9)
    return out


def match_score(q, t):
    """短い方を長い方の上でスライドさせ、フレーム毎コサイン類似度の平均の最大値"""
    if len(q) == 0 or len(t) == 0:
        return 0.0, 0
    if len(t) < len(q):
        q, t = t, q
    best, best_off = -1.0, 0
    step = 2
    for off in range(0, len(t) - len(q) + 1, step):
        s = float((q * t[off:off + len(q)]).sum(1).mean())
        if s > best:
            best, best_off = s, off
    return best, best_off


def chroma_of_file(path, ffmpeg=None, cache=None):
    if cache is not None and path in cache:
        return cache[path]
    ff = ffmpeg or find_tool("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg が見つかりません（識別機能には ffmpeg が必要です）")
    c = chroma(_decode_to_mono(path, ff))
    if cache is not None:
        cache[path] = c
    return c
