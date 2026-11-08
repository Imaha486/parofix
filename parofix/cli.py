# -*- coding: utf-8 -*-
"""parofix コマンドラインインタフェース"""
import argparse
import glob
import json
import os
import subprocess
import sys

from . import __version__
from .audio import find_tool, fmt_time
from .bgmbin import BgmArchive
from .encoder import EncodeSpec, encode_track, POOL_INGAME
from .games import TARGETS, TRACK_NAMES, MENU_MAP
from .iso9660 import Iso9660, patch_iso, rebuild_iso
from .riff import AtracInfo, WAVE_FORMAT_AT3, WAVE_FORMAT_EXTENSIBLE


def log(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- 共通
def resolve_target(name):
    """'paro2' 等のキー、または ISO 内パスを (path, desc, pool) に解決"""
    if name in TARGETS:
        return TARGETS[name]
    return (name.replace("\\", "/").lstrip("/"), name, POOL_INGAME)


def load_archive_from_iso(iso_path, target):
    path, desc, pool = resolve_target(target)
    with Iso9660(iso_path) as iso:
        data = iso.read(path)
    return BgmArchive(data), path, desc, pool


def track_name(target, i):
    names = TRACK_NAMES.get(target)
    return names[i] if names and i < len(names) else ""


def print_archive(arc: BgmArchive, target=None):
    log(f"  トラック数: {len(arc)}")
    for i, t in enumerate(arc.tracks):
        info = AtracInfo(t)
        log(f"  [{i:3d}] {len(t):9,} B  {info.describe()}  {track_name(target, i) if target else ''}")


# ---------------------------------------------------------------- iso
def cmd_iso_list(a):
    with Iso9660(a.iso) as iso:
        log(f"System ID: {iso.system_id!r}  Volume ID: {iso.volume_id!r}  sectors: {iso.volume_space_size}")
        for e in iso.files():
            log(f"  LBA {e.extent:7d}  {e.size:11,} B  {e.path}")


def cmd_iso_extract(a):
    os.makedirs(a.out, exist_ok=True)
    with Iso9660(a.iso) as iso:
        n = iso.extract_all(a.out, progress=lambda p: log("  " + p) if a.verbose else None)
    log(f"{n} ファイルを {a.out} に展開しました")


def cmd_iso_build(a):
    rep = {}
    for s in a.replace:
        if "=" not in s:
            raise SystemExit("--replace は ISO内パス=ローカルファイル の形式で指定してください")
        k, v = s.split("=", 1)
        rep[k] = v
    if a.from_dir:
        # フォルダ内の全ファイルを ISO 内の同じ相対パスに差し替え（存在するものだけ）
        import hashlib
        with Iso9660(a.iso) as iso:
            known = {e.path.upper(): e for e in iso.files()}
            for root, _, files in os.walk(a.from_dir):
                for fn in files:
                    full = os.path.join(root, fn)
                    rel = "/" + os.path.relpath(full, a.from_dir).replace("\\", "/")
                    e = known.get(rel.upper())
                    if e is None:
                        continue
                    with open(full, "rb") as fh:
                        h = hashlib.md5(fh.read()).digest()
                    if os.path.getsize(full) == e.size and hashlib.md5(iso.read(e.path)).digest() == h:
                        continue  # 変更なし
                    rep[e.path] = full
        log(f"変更されたファイル: {len(rep)} 件")
    if not rep:
        raise SystemExit("差し替えるファイルがありません")
    out = a.out or default_output(a.iso)
    (patch_iso if a.append else rebuild_iso)(a.iso, out, rep, log=log)


def default_output(iso_path):
    stem, ext = os.path.splitext(iso_path)
    return stem + "_converted" + (ext or ".iso")


# ---------------------------------------------------------------- bgm
def _open_bgm(a):
    if a.iso:
        arc, path, desc, pool = load_archive_from_iso(a.iso, a.target)
        log(f"{desc}  ({path})")
        return arc, a.target if a.target in TARGETS else None
    arc = BgmArchive.load(a.file)
    return arc, a.target if a.target in TARGETS else None


def cmd_bgm_list(a):
    arc, target = _open_bgm(a)
    print_archive(arc, target)


def cmd_bgm_extract(a):
    arc, target = _open_bgm(a)
    os.makedirs(a.out, exist_ok=True)
    ff = find_tool("ffmpeg") if a.wav else None
    if a.wav and not ff:
        raise SystemExit("--wav には ffmpeg が必要です（bin/ か PATH に ffmpeg を置いてください）")
    for i, t in enumerate(arc.tracks):
        nm = track_name(target, i) if target else ""
        base = os.path.join(a.out, f"{i:03d}" + (("_" + nm) if nm else ""))
        with open(base + ".at3", "wb") as f:
            f.write(t)
        if a.wav:
            subprocess.run([ff, "-v", "error", "-y", "-i", base + ".at3", base + ".wav"], check=True)
    log(f"{len(arc)} トラックを {a.out} に書き出しました" + ("（.at3 と .wav）" if a.wav else "（.at3）"))


def cmd_bgm_build(a):
    arc = BgmArchive()
    if a.list:
        with open(a.list, encoding="utf-8") as f:
            files = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        base = os.path.dirname(os.path.abspath(a.list))
        files = [p if os.path.isabs(p) else os.path.join(base, p) for p in files]
    else:
        files = sorted(glob.glob(os.path.join(a.dir, "*.at3")))
    if not files:
        raise SystemExit("入力 .at3 がありません")
    for p in files:
        with open(p, "rb") as f:
            arc.tracks.append(f.read())
    arc.save(a.out)
    log(f"{len(arc)} トラック -> {a.out} ({os.path.getsize(a.out):,} bytes)")


def cmd_bgm_replace(a):
    arc, target = _open_bgm(a)
    for s in a.set:
        idx, p = s.split("=", 1)
        idx = int(idx)
        if not 0 <= idx < len(arc):
            raise SystemExit(f"トラック番号 {idx} は範囲外です (0-{len(arc)-1})")
        with open(p, "rb") as f:
            arc.tracks[idx] = f.read()
        log(f"  [{idx}] <- {p}")
    arc.save(a.out)
    log(f"-> {a.out}")


# ---------------------------------------------------------------- encode
def cmd_encode(a):
    d = {"wav": a.wav, "loop_start": a.loop_start, "loop_end": a.loop_end, "end": a.end,
         "no_loop": a.no_loop, "fade_out": a.fade_out, "gain_db": a.gain_db}
    defaults = {"encoder": a.encoder, "bitrate": a.bitrate, "max_bytes": a.max_bytes,
                "at3tool_path": a.at3tool, "auto_fallback": not a.no_fallback}
    spec = EncodeSpec(d, defaults)
    data = encode_track(spec, log=log)
    with open(a.out, "wb") as f:
        f.write(data)
    log(f"-> {a.out}  {AtracInfo(data).describe()}")


# ---------------------------------------------------------------- verify
def verify_track(t: bytes, pool: int):
    """PSP の sceAtrac が受け付ける条件（PPSSPP の AnalyzeAtracTrack 相当）を確認"""
    errs = []
    try:
        info = AtracInfo(t)
    except Exception as e:
        return [f"RIFF 解析失敗: {e}"]
    if info.fmt_tag not in (WAVE_FORMAT_AT3, WAVE_FORMAT_EXTENSIBLE):
        errs.append(f"fmt タグ不正 {info.fmt_tag:#06x}")
    if info.sample_rate != 44100:
        errs.append(f"サンプルレート {info.sample_rate} (44100 のみ)")
    if info.channels not in (1, 2):
        errs.append(f"チャンネル数 {info.channels}")
    if not info.block_align:
        errs.append("blockalign=0")
    if info.end_sample is None:
        errs.append("fact チャンクなし")
    extra = 0x170 if info.fmt_tag == WAVE_FORMAT_EXTENSIBLE else 0x45
    spf_shift = 11 if info.fmt_tag == WAVE_FORMAT_EXTENSIBLE else 10
    if info.loop:
        if info.loop[0] >= info.loop[1]:
            errs.append("ループ開始 >= 終了")
        if info.end_sample is not None and info.loop[1] + extra > (info.end_sample + info.first_sample_offset + extra - 1):
            errs.append("ループ終了が endSample 以降 (libatrac3plus が BAD_CODEC_PARAMS を返す)")
    if info.end_sample is not None and info.block_align:
        end_internal = info.end_sample + info.first_sample_offset + extra - 1
        need = (end_internal >> spf_shift) * info.block_align
        if not info.data_size > need:
            errs.append(f"data サイズ {info.data_size} が endSample 分のフレーム ({need}) 以下 (libatrac3plus が BAD_CODEC_PARAMS を返す)")
    if info.data_size and info.block_align and info.data_size % info.block_align:
        errs.append("data サイズがフレーム長の倍数でない")
    if len(t) > pool:
        errs.append(f"[警告] サイズ {len(t):,} がゲームの読み込みバッファ上限 {pool:,} を超過"
                    "（元から超えているトラックはゲーム内で未使用の可能性があります）")
    return errs


def _split_errs(errs):
    warns = [e for e in errs if e.startswith("[警告]")]
    hard = [e for e in errs if not e.startswith("[警告]")]
    return hard, warns


def cmd_verify(a):
    total_err = 0
    total_warn = 0

    def check_archive(arc, pool, label):
        nonlocal total_err, total_warn
        ne = nw = 0
        for i, t in enumerate(arc.tracks):
            hard, warns = _split_errs(verify_track(t, pool))
            if hard:
                ne += 1
                log(f"  [{label} #{i}] NG: " + " / ".join(hard))
            if warns and a.show_warnings:
                log(f"  [{label} #{i}] " + " / ".join(warns))
            if warns:
                nw += 1
        total_err += ne
        total_warn += nw
        return ne, nw

    if a.iso:
        targets = [a.target] if a.target else list(TARGETS)
        for tg in targets:
            try:
                arc, path, desc, pool = load_archive_from_iso(a.iso, tg)
            except Exception as e:
                log(f"[{tg}] 読み込み失敗: {e}")
                continue
            ne, nw = check_archive(arc, pool, tg)
            log(f"[{tg}] {desc}: {len(arc)} トラック  問題 {ne} 件" + (f"  (サイズ警告 {nw} 件)" if nw else ""))
    else:
        arc = BgmArchive.load(a.file)
        pool = resolve_target(a.target)[2] if a.target else POOL_INGAME
        ne, nw = check_archive(arc, pool, a.target or "file")
        log(f"{a.file}: {len(arc)} トラック  問題 {ne} 件" + (f"  (サイズ警告 {nw} 件)" if nw else ""))
    if total_warn and not a.show_warnings:
        log(f"※ 読み込みバッファ上限を超えるトラックが {total_warn} 件あります（元 ISO に最初から含まれる長尺曲なら無視して構いません。"
            "詳細は --show-warnings）")
    log("結果: " + ("すべて OK" if total_err == 0 else f"NG {total_err} 件"))
    return 1 if total_err else 0


# ---------------------------------------------------------------- identify
def _chroma_targets(arc, label, ff, tmpdir):
    from .identify import chroma_of_file
    out = []
    for i, t in enumerate(arc.tracks):
        p = os.path.join(tmpdir, f"{label}_{i:03d}.at3")
        with open(p, "wb") as f:
            f.write(t)
        out.append((i, chroma_of_file(p, ff)))
    return out


def cmd_identify(a):
    import tempfile
    from .identify import chroma_of_file, match_score
    ff = find_tool("ffmpeg")
    if not ff:
        raise SystemExit("identify には ffmpeg が必要です（bin/ か PATH に置いてください）")
    arc, path, desc, pool = load_archive_from_iso(a.iso, a.target)
    cds = []
    for pat in a.cd:
        cds += sorted(glob.glob(pat)) if any(ch in pat for ch in "*?[") else [pat]
    if a.cd_dir:
        for ext in ("*.wav", "*.flac", "*.mp3", "*.m4a", "*.ogg"):
            cds += sorted(glob.glob(os.path.join(a.cd_dir, ext)))
    if not cds:
        raise SystemExit("CD 音源ファイルが指定されていません (--cd-dir または --cd)")
    log(f"{desc}: ゲーム内 {len(arc)} トラック vs CD 音源 {len(cds)} ファイル を照合中...")
    with tempfile.TemporaryDirectory() as td:
        game = _chroma_targets(arc, "g", ff, td)
    cdc = []
    for p in cds:
        try:
            cdc.append((p, chroma_of_file(p, ff)))
        except Exception as e:
            log(f"  読み込み失敗: {p}: {e}")
    th = a.threshold
    # スロット毎の最良 CD
    log("")
    log("=== ゲーム内トラック → 最も近い CD 音源 ===")
    log("  No.  長さ    スコア  CD ファイル")
    unmatched_slots = []
    best_by_cd = {}
    for i, gc in game:
        info = AtracInfo(arc.tracks[i])
        best = (-1, None)
        for p, cc in cdc:
            s, _ = match_score(gc, cc)
            if s > best[0]:
                best = (s, p)
            if s > best_by_cd.get(p, (-1, None))[0]:
                best_by_cd[p] = (s, i)
        mark = "" if best[0] >= th else "  <-- CD に対応曲なし？（差し替え候補）"
        if best[0] < th:
            unmatched_slots.append(i)
        log(f"  {i:3d}  {fmt_time(info.end_sample or 0):>8}  {best[0]:5.3f}  {os.path.basename(best[1]) if best[1] else '-'}"
            f"  {track_name(a.target if a.target in TARGETS else None, i)}{mark}")
    log("")
    log("=== CD 音源 → 最も近いゲーム内トラック ===")
    unmatched_cd = []
    for p, cc in cdc:
        s, i = best_by_cd.get(p, (-1, None))
        mark = "" if s >= th else "  <-- ゲーム内に対応トラックなし？（差し替えられた原曲の候補）"
        if s < th:
            unmatched_cd.append(p)
        log(f"  {s:5.3f}  #{i if i is not None else '-':>3}  {os.path.basename(p)}{mark}")
    log("")
    log(f"しきい値 {th}: CD に一致しないゲーム内スロット = {unmatched_slots}")
    log(f"             ゲーム内に一致しない CD 曲 = {[os.path.basename(p) for p in unmatched_cd]}")
    log("→ 差し替え候補スロットに、ゲーム内に無い CD 曲を割り当てて config の replacements に記入してください。")


def cmd_menu_map(a):
    import tempfile
    from .identify import match_score
    ff = find_tool("ffmpeg")
    if not ff:
        raise SystemExit("menu-map には ffmpeg が必要です")
    arc, path, desc, pool = load_archive_from_iso(a.iso, a.target)
    menu, _, _, _ = load_archive_from_iso(a.iso, "menu")
    lo, hi = a.menu_range
    with tempfile.TemporaryDirectory() as td:
        game = _chroma_targets(arc, "g", ff, td)
        menu_c = []
        for i in range(lo, min(hi + 1, len(menu))):
            p = os.path.join(td, f"m_{i:03d}.at3")
            with open(p, "wb") as f:
                f.write(menu.tracks[i])
            from .identify import chroma_of_file
            menu_c.append((i, chroma_of_file(p, ff)))
    log(f"{desc} → ミュージックモード (menu {lo}-{hi}) 対応表")
    for i, gc in game:
        res = sorted(((match_score(gc, mc)[0], mi) for mi, mc in menu_c), reverse=True)[:3]
        log(f"  #{i:3d} {track_name(a.target if a.target in TARGETS else None, i):18s} -> "
            + ", ".join(f"menu {mi} ({s:.3f})" for s, mi in res))


# ---------------------------------------------------------------- loopfind
def cmd_loopfind(a):
    from .audio import load_audio, write_wav16, parse_time
    from .loopfind import find_loop, refine_loop, make_preview, coarse_period
    import numpy as np
    audio, sr = load_audio(a.wav)
    x = np.ascontiguousarray(audio.mean(1), dtype=np.float64)
    log(f"{a.wav}: {fmt_time(len(x))}  ループポイント検出中...")
    if a.near is not None:
        ls = parse_time(a.near)
        if a.period:
            P0 = parse_time(a.period)
        else:
            cands, _ = coarse_period(x, sr, log=log)
            P0 = cands[0][1]
        r = refine_loop(x, P0, ls - int(a.near_span * sr / 2), sr, span_sec=a.near_span, step_sec=0.004, search=1500)
        results = [r] if r else []
    else:
        results = find_loop(x, sr, log=log)
    if not results:
        raise SystemExit("ループを検出できませんでした")
    r = results[0]
    log("")
    log(f"推定ループ:  loop_start = {r['loop_start']}  ({fmt_time(r['loop_start'])})")
    log(f"             loop_end   = {r['loop_end']}  ({fmt_time(r['loop_end'])})   1周 {(r['loop_end']-r['loop_start'])/sr:.3f}s")
    log(f"             継ぎ目一致度 = {r['seam_score']:.3f}  (1.0 で完全一致。0.8 以上なら概ね自然に繋がる)")
    log("config には  \"loop_start\": %d, \"loop_end\": %d  と書けます" % (r['loop_start'], r['loop_end']))
    if a.preview:
        write_wav16(a.preview, make_preview(audio, r['loop_start'], r['loop_end']))
        log(f"継ぎ目確認用 WAV: {a.preview}（loop_end 手前 4 秒 → ループで戻る → 6 秒、を 2 回）")


# ---------------------------------------------------------------- run (全自動)
def cmd_run(a):
    with open(a.config, encoding="utf-8") as f:
        cfg = json.load(f)
    base = os.path.dirname(os.path.abspath(a.config))

    def rel(p):
        return p if os.path.isabs(p) else os.path.join(base, p)

    iso_path = rel(a.iso or cfg["iso"])
    out_iso = rel(a.out or cfg.get("output") or "") if (a.out or cfg.get("output")) else default_output(iso_path)
    defaults = dict(cfg.get("defaults", {}))
    if defaults.get("at3tool_path"):
        defaults["at3tool_path"] = rel(defaults["at3tool_path"])
    work = rel(cfg.get("work_dir") or (os.path.splitext(os.path.basename(iso_path))[0] + "_work"))
    os.makedirs(work, exist_ok=True)
    log(f"入力 ISO : {iso_path}")
    log(f"出力 ISO : {out_iso}")
    log(f"作業フォルダ: {work}")

    # 差し替え指定を展開（also_music_mode の自動追加を含む）
    jobs = []
    for r in cfg.get("replacements", []):
        if r.get("disabled"):
            continue
        tg = r.get("target") or r.get("archive")
        if not tg:
            raise SystemExit("replacements の各要素には target を指定してください")
        if r.get("index") is None or not r.get("wav"):
            log(f"  [スキップ] target={tg}: index または wav が未設定です")
            continue
        r = dict(r)
        r["wav"] = rel(r["wav"])
        jobs.append((tg, int(r["index"]), r))
        if r.get("also_music_mode"):
            mi = MENU_MAP.get(tg, {}).get(int(r["index"]))
            if r.get("menu_index") is not None:
                mi = int(r["menu_index"])
            if mi is None:
                log(f"  [注意] {tg} #{r['index']} に対応するミュージックモードのトラックが不明です"
                    "（menu_index で指定できます）。スキップします")
            else:
                r2 = dict(r)
                r2.pop("also_music_mode", None)
                jobs.append(("menu", mi, r2))
    if not jobs:
        raise SystemExit("replacements が空です")

    # アーカイブ毎に処理
    by_target = {}
    for tg, idx, r in jobs:
        by_target.setdefault(tg, []).append((idx, r))

    patches = {}
    for tg, items in by_target.items():
        arc, path, desc, pool = load_archive_from_iso(iso_path, tg)
        log("")
        log(f"=== {desc} ({path}) : {len(arc)} トラック ===")
        for idx, r in items:
            if not 0 <= idx < len(arc):
                raise SystemExit(f"{tg}: トラック番号 {idx} は範囲外です (0-{len(arc)-1})")
            orig = AtracInfo(arc.tracks[idx])
            log(f"  [{idx}] {track_name(tg if tg in TARGETS else None, idx)} 元: {orig.describe()}")
            d = dict(defaults)
            d["max_bytes"] = r.get("max_bytes", pool)
            spec = EncodeSpec(r, d)
            data = encode_track(spec, log=log, label=f"[{tg} #{idx}] ")
            errs = verify_track(data, pool)
            if errs:
                raise SystemExit(f"{tg} #{idx}: 検証エラー: " + " / ".join(errs))
            arc.tracks[idx] = data
            keep = os.path.join(work, f"{tg}_{idx:03d}.at3")
            with open(keep, "wb") as f:
                f.write(data)
        built = arc.build()
        keep_bin = os.path.join(work, f"{tg}_{os.path.basename(path)}")
        with open(keep_bin, "wb") as f:
            f.write(built)
        log(f"  -> {os.path.basename(path)} 再生成: {len(built):,} bytes")
        patches[path] = built

    if a.no_iso:
        log("--no-iso 指定のため ISO は作成しません")
        return 0
    log("")
    if a.append or cfg.get("append_mode"):
        patch_iso(iso_path, out_iso, patches, log=log)
    else:
        rebuild_iso(iso_path, out_iso, patches, log=log)

    # 出来上がりを再読込して確認
    log("")
    log("=== 出力 ISO の確認 ===")
    for tg in by_target:
        arc, path, desc, pool = load_archive_from_iso(out_iso, tg)
        log(f"  {desc}: {len(arc)} トラック")
        for idx, _ in by_target[tg]:
            errs = verify_track(arc.tracks[idx], pool)
            log(f"    [{idx}] {AtracInfo(arc.tracks[idx]).describe()}  " + ("OK" if not errs else "NG: " + " / ".join(errs)))
    log("")
    log(f"完成: {out_iso}")
    return 0


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(prog="parofix",
                                 description="パロディウス ポータブル (PSP) BGM 差し替えツールセット v" + __version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("iso-list", help="ISO 内のファイル一覧")
    p.add_argument("iso"); p.set_defaults(fn=cmd_iso_list)

    p = sub.add_parser("iso-extract", help="ISO を展開")
    p.add_argument("iso"); p.add_argument("out"); p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(fn=cmd_iso_extract)

    p = sub.add_parser("iso-build", help="元 ISO にファイルを差し替えて新しい ISO を作成")
    p.add_argument("iso")
    p.add_argument("-r", "--replace", action="append", default=[], metavar="ISO内パス=ファイル")
    p.add_argument("--from-dir", help="展開フォルダ（同じ相対パスのファイルを全部差し替え）")
    p.add_argument("--append", action="store_true", help="元の配置を維持し末尾追記で差し替える（ISO が大きくなる）")
    p.add_argument("-o", "--out"); p.set_defaults(fn=cmd_iso_build)

    def add_src(p):
        g = p.add_mutually_exclusive_group(required=True)
        g.add_argument("--iso", help="ISO から直接読む（--target と併用）")
        g.add_argument("--file", help="bgm.bin ファイル")
        p.add_argument("--target", default="paro2", help="paro2/paro3/paro4/paro5/msx/menu または ISO 内パス")

    p = sub.add_parser("bgm-list", help="BGM アーカイブのトラック一覧"); add_src(p); p.set_defaults(fn=cmd_bgm_list)
    p = sub.add_parser("bgm-extract", help="BGM アーカイブを .at3 (と .wav) に展開"); add_src(p)
    p.add_argument("out"); p.add_argument("--wav", action="store_true", help="ffmpeg で WAV にもデコード")
    p.set_defaults(fn=cmd_bgm_extract)
    p = sub.add_parser("bgm-replace", help="BGM アーカイブ内のトラックを .at3 で差し替え"); add_src(p)
    p.add_argument("--set", action="append", default=[], metavar="番号=file.at3", required=True)
    p.add_argument("-o", "--out", required=True); p.set_defaults(fn=cmd_bgm_replace)
    p = sub.add_parser("bgm-build", help=".at3 群から BGM アーカイブを新規作成")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dir", help="*.at3 を名前順に格納"); g.add_argument("--list", help="1 行 1 ファイルの一覧テキスト")
    p.add_argument("-o", "--out", required=True); p.set_defaults(fn=cmd_bgm_build)

    p = sub.add_parser("encode", help="WAV を 1 曲エンコード (.at3)")
    p.add_argument("wav"); p.add_argument("-o", "--out", required=True)
    p.add_argument("--loop-start"); p.add_argument("--loop-end"); p.add_argument("--end")
    p.add_argument("--no-loop", action="store_true"); p.add_argument("--fade-out")
    p.add_argument("--gain-db", type=float, default=0.0)
    p.add_argument("--encoder", default="atracdenc", choices=["atracdenc", "at3tool", "custom"])
    p.add_argument("--bitrate", type=int, default=132)
    p.add_argument("--at3tool", help="at3tool.exe のパス")
    p.add_argument("--max-bytes", type=int, default=POOL_INGAME)
    p.add_argument("--no-fallback", action="store_true"); p.set_defaults(fn=cmd_encode)

    p = sub.add_parser("verify", help="アーカイブ/ISO の BGM が PSP で読める形式か検査")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--iso"); g.add_argument("--file")
    p.add_argument("--target")
    p.add_argument("--show-warnings", action="store_true", help="サイズ警告の詳細も表示")
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("identify", help="CD 音源とゲーム内トラックを照合し差し替えスロットを推定")
    p.add_argument("--iso", required=True); p.add_argument("--target", required=True)
    p.add_argument("--cd-dir"); p.add_argument("--cd", action="append", default=[])
    p.add_argument("--threshold", type=float, default=0.7); p.set_defaults(fn=cmd_identify)

    p = sub.add_parser("menu-map", help="ゲーム内トラックとミュージックモードの対応表を作成")
    p.add_argument("--iso", required=True); p.add_argument("--target", required=True)
    p.add_argument("--menu-range", type=int, nargs=2, default=[0, 255]); p.set_defaults(fn=cmd_menu_map)

    p = sub.add_parser("loopfind", help="CD 音源のループポイント（1周目→2周目の繰り返し）を自動検出")
    p.add_argument("wav")
    p.add_argument("--near", help="ループ開始のおおよその位置を指定して、その付近で継ぎ目が最も滑らかな点を探す (例 0:10.0)")
    p.add_argument("--period", help="--near と併用: 1周の長さを指定 (省略時は自動)")
    p.add_argument("--near-span", type=float, default=0.6, help="--near の探索幅 秒 (既定 0.6)")
    p.add_argument("--preview", help="継ぎ目確認用 WAV の出力先")
    p.set_defaults(fn=cmd_loopfind)

    p = sub.add_parser("run", help="設定ファイルに従って全自動で _converted.iso を作成")
    p.add_argument("config"); p.add_argument("--iso"); p.add_argument("-o", "--out")
    p.add_argument("--no-iso", action="store_true", help="bgm.bin の生成までで止める")
    p.add_argument("--append", action="store_true", help="ISO を再構築せず末尾追記方式で差し替える")
    p.set_defaults(fn=cmd_run)

    a = ap.parse_args(argv)
    try:
        return a.fn(a) or 0
    except (RuntimeError, ValueError, FileNotFoundError) as e:
        log("エラー: " + str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
