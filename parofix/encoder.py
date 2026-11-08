# -*- coding: utf-8 -*-
"""WAV → PSP 用 ATRAC (RIFF) エンコード"""
import os
import subprocess
import tempfile

import numpy as np

from . import audio
from .riff import AtracInfo, rewrite_atrac_header

# atracdenc の ATRAC3 エンコーダは Sony 製 (at3tool) より 69 サンプル遅延が大きい
# （実測: デコード出力の遅れ 1162 = 1024 + 69 + 69）。PSP は fact[1] + 0x45 サンプルを
# 先頭から読み飛ばすので、fact[1] = 1093 にするとループ位置が元音源と一致する。
ATRACDENC_AT3_FSO = 1093
PAD_SAMPLES = 8192       # 末尾に足す無音。PSP の sceAtrac は「endSample 分のフレーム数より data が大きい」ことを要求する

# ゲーム側の BGM 読み込みバッファ（実行ファイル解析結果）
POOL_INGAME = 0x180000 - 0x10   # paro2 / paro4 / paro5 (1.5MB)
POOL_MENU = 0x480000 - 0x10     # paro_menu (ミュージックモード, 4.5MB)
POOL_MSX = 0x200000 - 0x10


class EncodeSpec:
    def __init__(self, d: dict, defaults: dict):
        g = lambda k, dv=None: d.get(k, defaults.get(k, dv))
        self.wav = d["wav"]
        self.loop_start = audio.parse_time(d.get("loop_start"))
        self.loop_end = audio.parse_time(d.get("loop_end"))
        self.end = audio.parse_time(d.get("end"))
        self.no_loop = bool(d.get("no_loop", False))
        self.fade_out = audio.parse_time(d.get("fade_out"))
        self.gain_db = float(g("gain_db", 0.0))
        self.encoder = g("encoder", "atracdenc")
        self.bitrate = int(g("bitrate", 132))
        self.at3tool_path = g("at3tool_path")
        self.at3tool_args = g("at3tool_args", "-e -br {bitrate} {in} {out}")
        self.atracdenc_path = g("atracdenc_path")
        self.custom_cmd = g("custom_cmd")
        self.custom_fso = g("custom_fso")
        self.max_bytes = int(g("max_bytes", POOL_INGAME))
        self.auto_fallback = bool(g("auto_fallback", True))
        self.invert_polarity = bool(g("invert_polarity", True))


def _run(cmd, log):
    log("    $ " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0:
        raise RuntimeError("エンコーダがエラー終了しました:\n" + r.stdout.decode(errors="replace")[-2000:])


def encode_atracdenc(wav_path, out_path, bitrate, exe, log):
    mode = {132: "atrac3", 66: "atrac3_lp4"}.get(bitrate)
    if mode is None:
        raise ValueError("atracdenc の ATRAC3 ビットレートは 132 か 66 のみ指定できます")
    _run([exe, "-e", mode, "--container", "riff", "-i", wav_path, "-o", out_path], log)
    return ATRACDENC_AT3_FSO


def encode_at3tool(wav_path, out_path, bitrate, exe, args_tmpl, log):
    args = args_tmpl.format(bitrate=bitrate, **{"in": wav_path, "out": out_path}).split()
    _run([exe] + args, log)
    return None  # fact は at3tool が書いたものを使う


def encode_track(spec: EncodeSpec, log=print, label=""):
    """EncodeSpec に従って WAV をエンコードし、ゲーム用 RIFF (bytes) を返す"""
    if not os.path.isfile(spec.wav):
        raise FileNotFoundError(f"音源ファイルがありません: {spec.wav}")
    a, sr = audio.load_audio(spec.wav)
    n = len(a)
    a = audio.apply_gain_db(a, spec.gain_db)

    wav_loop = audio.read_wav_smpl_loop(spec.wav)
    if spec.no_loop:
        loop = None
        trim_end = spec.end or n
    else:
        ls = spec.loop_start if spec.loop_start is not None else (wav_loop[0] if wav_loop else 0)
        le = spec.loop_end if spec.loop_end is not None else (wav_loop[1] if wav_loop else n)
        if le > n:
            log(f"    [警告] loop_end ({le}) が音声長 ({n}) を超えています。末尾に丸めます")
            le = n
        if not (0 <= ls < le):
            raise ValueError(f"ループ範囲が不正です: start={ls} end={le}")
        loop = (ls, le)
        trim_end = spec.end if spec.end else le
        if trim_end < le:
            raise ValueError("end は loop_end 以上にしてください")
    trim_end = min(trim_end, n)
    x = a[:trim_end]
    if spec.fade_out:
        x = audio.fade_out(x, spec.fade_out)
    x = np.concatenate([x, np.zeros((PAD_SAMPLES, 2), dtype=np.float32)])
    # fact の endSample は実音声長。PSP(libatrac3plus) は
    #   ・loopEnd <= endSample - 1
    #   ・data サイズ > ((endSample + 先頭オフセット) / フレーム長) * フレームバイト数
    # を要求するので、ループ曲は loop_end + 1、末尾の無音パディングは endSample に含めない。
    end_sample = (trim_end + 1) if loop is not None else trim_end
    if spec.encoder == "atracdenc" and spec.invert_polarity:
        # atracdenc の ATRAC3 出力は（ffmpeg/PSP デコーダで再生すると）極性が反転するので、あらかじめ反転しておく
        x = -x

    log(f"  {label}{os.path.basename(spec.wav)}: 長さ {audio.fmt_time(trim_end)}"
        + (f"  ループ {audio.fmt_time(loop[0])} - {audio.fmt_time(loop[1])}" if loop else "  ループなし"))

    bitrates = [spec.bitrate]
    if spec.auto_fallback and spec.encoder == "atracdenc" and spec.bitrate == 132:
        bitrates.append(66)

    last_err = None
    for br in bitrates:
        with tempfile.TemporaryDirectory() as td:
            wav_tmp = os.path.join(td, "in.wav")
            out_tmp = os.path.join(td, "out.at3")
            audio.write_wav16(wav_tmp, x)
            if spec.encoder == "atracdenc":
                exe = spec.atracdenc_path or audio.find_tool("atracdenc")
                if not exe:
                    raise RuntimeError("atracdenc が見つかりません（bin/ フォルダか PATH に置いてください）")
                fso = encode_atracdenc(wav_tmp, out_tmp, br, exe, log)
            elif spec.encoder == "at3tool":
                exe = spec.at3tool_path or audio.find_tool("at3tool") or audio.find_tool("psp_at3tool")
                if not exe:
                    raise RuntimeError("at3tool.exe が見つかりません（config の at3tool_path を設定してください）")
                fso = encode_at3tool(wav_tmp, out_tmp, br, exe, spec.at3tool_args, log)
            elif spec.encoder == "custom":
                cmd = spec.custom_cmd.format(bitrate=br, **{"in": wav_tmp, "out": out_tmp}).split()
                _run(cmd, log)
                fso = spec.custom_fso
            else:
                raise ValueError("encoder は atracdenc / at3tool / custom のいずれかです")
            with open(out_tmp, "rb") as f:
                raw = f.read()

        info = AtracInfo(raw)
        if fso is None:
            # at3tool 等: 先頭オフセットはエンコーダが書いた fact の値を使う
            fso = info.first_sample_offset
        result = rewrite_atrac_header(raw, end_sample, fso, loop)

        info = AtracInfo(result)
        log(f"    -> {info.codec} {info.bitrate_kbps}kbps  {len(result):,} bytes  "
            f"(上限 {spec.max_bytes:,})")
        if len(result) <= spec.max_bytes:
            return result
        last_err = (f"エンコード結果 {len(result):,} bytes がゲームの読み込みバッファ上限 "
                    f"{spec.max_bytes:,} bytes を超えています")
        log("    [警告] " + last_err + (" → 低ビットレートで再試行" if br != bitrates[-1] else ""))
    raise RuntimeError(last_err + "。loop_end / end を短くするか bitrate を下げてください")
