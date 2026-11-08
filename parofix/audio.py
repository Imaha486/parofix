# -*- coding: utf-8 -*-
"""WAV 入力の読み込み・整形（44.1kHz / 16bit / ステレオ へ統一）"""
import os
import re
import shutil
import struct
import subprocess
import tempfile
import wave

import numpy as np

SR = 44100


def find_tool(name, extra_dirs=()):
    """bin/ フォルダ → PATH の順に実行ファイルを探す"""
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [os.path.join(here, "..", "bin"), here] + list(extra_dirs)
    exts = [".exe", ""] if os.name == "nt" else ["", ".exe"]
    for d in cands:
        for ext in exts:
            p = os.path.join(d, name + ext)
            if os.path.isfile(p):
                return os.path.abspath(p)
    return shutil.which(name)


def parse_time(v, sr=SR):
    """
    位置指定を「サンプル数」に変換する。
      123456        -> サンプル数（整数）
      "123456"      -> サンプル数
      "12.5" / "12.5s" -> 秒
      "1:23.456"    -> 分:秒
      "0:01:23.4"   -> 時:分:秒
    """
    if v is None:
        return None
    if isinstance(v, bool):
        raise ValueError("時間指定が不正です")
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(round(v * sr))
    s = str(v).strip().lower()
    if s == "" or s == "none":
        return None
    if s.endswith("smp") or s.endswith("samples"):
        return int(float(re.sub(r"[a-z]+$", "", s)))
    if re.fullmatch(r"\d+", s):
        return int(s)
    if s.endswith("s"):
        return int(round(float(s[:-1]) * sr))
    if ":" in s:
        parts = s.split(":")
        total = 0.0
        for p in parts:
            total = total * 60 + float(p)
        return int(round(total * sr))
    return int(round(float(s) * sr))


def fmt_time(samples, sr=SR):
    sec = samples / sr
    m = int(sec // 60)
    return f"{m}:{sec - m*60:06.3f}"


def _read_wav_python(path):
    with wave.open(path, "rb") as w:
        ch = w.getnchannels()
        sw = w.getsampwidth()
        sr = w.getframerate()
        n = w.getnframes()
        raw = w.readframes(n)
    if sw == 2:
        a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sw == 1:
        a = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sw == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        a = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) |
             (b[:, 2].astype(np.int8).astype(np.int32) << 16)).astype(np.float32) / 8388608.0
    elif sw == 4:
        a = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError("未対応のサンプル幅: %d" % sw)
    return a.reshape(-1, ch), sr


def read_wav_smpl_loop(path):
    """WAV 自身に smpl ループが入っていれば (start, end) を返す（Audacity 等で付けた場合）"""
    try:
        with open(path, "rb") as f:
            d = f.read(1 << 20)
        if d[:4] != b"RIFF":
            return None
        p = 12
        while p + 8 <= len(d):
            cid = d[p:p + 4]
            sz = struct.unpack_from("<I", d, p + 4)[0]
            if cid == b"smpl":
                b = d[p + 8:p + 8 + sz]
                if len(b) >= 60 and struct.unpack_from("<I", b, 28)[0] >= 1:
                    s, e = struct.unpack_from("<II", b, 44)
                    return (s, e)
                return None
            if cid == b"data":
                return None
            p += 8 + sz + (sz & 1)
    except Exception:
        return None
    return None


def load_audio(path, ffmpeg=None):
    """
    任意の音声ファイルを float32 (N, 2) @44.1kHz で返す。
    標準の PCM WAV は Python だけで読む。それ以外 / 他サンプルレートは ffmpeg を使う。
    """
    ext = os.path.splitext(path)[1].lower()
    a = sr = None
    if ext == ".wav":
        try:
            a, sr = _read_wav_python(path)
        except Exception:
            a = None
    if a is None or sr != SR:
        ff = ffmpeg or find_tool("ffmpeg")
        if not ff:
            raise RuntimeError(
                f"{path}: 44.1kHz の PCM WAV ではありません。ffmpeg を bin/ か PATH に置くか、"
                "44.1kHz/16bit の WAV に変換してください。")
        with tempfile.TemporaryDirectory() as td:
            tmp = os.path.join(td, "conv.wav")
            subprocess.run([ff, "-v", "error", "-y", "-i", path, "-ar", str(SR), "-ac", "2",
                            "-c:a", "pcm_s16le", tmp], check=True)
            a, sr = _read_wav_python(tmp)
    if a.shape[1] == 1:
        a = np.repeat(a, 2, axis=1)
    elif a.shape[1] > 2:
        a = a[:, :2]
    return np.ascontiguousarray(a, dtype=np.float32), SR


def write_wav16(path, a: np.ndarray, sr=SR):
    x = np.clip(np.round(a * 32767.0), -32768, 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(x.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(x.tobytes())


def apply_gain_db(a, db):
    if not db:
        return a
    return a * (10 ** (db / 20.0))


def fade_out(a, n):
    if n <= 0 or len(a) == 0:
        return a
    n = min(n, len(a))
    ramp = np.linspace(1.0, 0.0, n, dtype=np.float32)[:, None]
    a = a.copy()
    a[-n:] *= ramp
    return a
