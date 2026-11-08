# -*- coding: utf-8 -*-
"""
ループポイント自動検出

CD 収録のゲーム BGM は「イントロ → 1周目 → 2周目 → フェードアウト」という構成が普通。
1周目と2周目は同じ譜面だが、FM 音源の位相や録音の揺らぎでサンプル単位では一致しないことが多い。
そこで

  1. スペクトログラムの自己類似度で周期 P（曲 1 周の長さ）を求める        （数十 ms 精度）
  2. 類似度が持続し始める位置からイントロの終わり（ループ開始の候補域）を求める
  3. 候補域内で loop_start を少しずつ動かし、各位置で ±数十 ms の範囲で周期をサンプル単位に合わせ直し、
     「loop_end の直後に本来鳴る音」と「loop_start の直後に鳴る音」の波形一致度（＝継ぎ目の滑らかさ）が
     最大になる (loop_start, loop_end) を選ぶ

戻り値は実サンプル位置（44.1kHz 基準）。
"""
import numpy as np
from numpy.fft import rfft, irfft

SR = 44100


def _spec(x, n=2048, hop=512):
    frames = (len(x) - n) // hop
    win = np.hanning(n)
    S = np.empty((frames, n // 2 + 1))
    for i in range(frames):
        S[i] = np.abs(rfft(x[i * hop:i * hop + n] * win))
    S = np.log1p(S)
    S -= S.mean(1, keepdims=True)
    S /= np.linalg.norm(S, axis=1, keepdims=True) + 1e-9
    return S


def _norm_xcorr(a, b):
    a = a - a.mean()
    b = b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 0 else 0.0


def _xcorr_best(a, seg):
    """窓 a を長い区間 seg 上でスライドさせ、正規化相関が最大の位置を返す (corr, offset)"""
    n = len(a) + len(seg)
    A = rfft(a - a.mean(), 2 * n)
    B = rfft(seg - seg.mean(), 2 * n)
    c = irfft(np.conj(A) * B)[:len(seg) - len(a) + 1]
    e = np.sqrt(np.convolve((seg - seg.mean()) ** 2, np.ones(len(a)), "valid") * ((a - a.mean()) ** 2).sum()) + 1e-9
    r = c / e
    k = int(np.argmax(r))
    return float(r[k]), k


def coarse_period(x, sr=SR, min_period_sec=8.0, max_period_sec=None, hop=512, log=None):
    """スペクトル自己類似度による周期候補 [(similarity, period_samples, sim_curve), ...]"""
    S = _spec(x, hop=hop)
    fr = sr / hop
    if max_period_sec is None:
        max_period_sec = len(x) / sr * 0.75
    res = []
    for lag in range(int(min_period_sec * fr), int(max_period_sec * fr)):
        L = len(S) - lag
        if L < fr * 5:
            break
        sim = (S[:L] * S[lag:]).sum(1)
        res.append((float(sim.mean()), lag))
    res.sort(reverse=True)
    cands = []
    for m, lag in res:
        if all(abs(lag - l2) > fr * 1.0 for _, l2, _ in cands):
            L = len(S) - lag
            cands.append((m, lag * hop, (S[:L] * S[lag:]).sum(1)))
        if len(cands) >= 4:
            break
    if log:
        log("  周期候補: " + ", ".join(f"{p / sr:.2f}s (類似度 {m:.3f})" for m, p, _ in cands))
    return cands, fr


def find_intro_end(sim_curve, fr, hop, thresh=None):
    """類似度が持続し始めるフレーム → サンプル位置（イントロ終端のおおよその位置）"""
    sim = np.asarray(sim_curve)
    if thresh is None:
        thresh = max(0.6, np.percentile(sim, 70) - 0.1)
    k = int(2.0 * fr)
    for i in range(len(sim) - k):
        if (sim[i:i + k] > thresh).mean() >= 0.8:
            return int(i * hop)
    return 0


def refine_loop(x, P0, start_from, sr=SR, span_sec=6.0, step_sec=0.01, search=3000, win_sec=0.5, log=None):
    """
    loop_start を start_from から span_sec の範囲で走査し、継ぎ目が最も滑らかな (loop_start, loop_end) を返す。
    """
    W = int(win_sec * sr)
    step = max(1, int(step_sec * sr))
    best = None
    n = len(x)
    t = max(0, start_from)
    end_t = min(start_from + int(span_sec * sr), n - P0 - W - search)
    while t < end_t:
        a = x[t:t + W]
        lo = t + P0 - search
        if lo < 0:
            t += step
            continue
        seg = x[lo:t + P0 + W + search]
        c, k = _xcorr_best(a, seg)
        P = P0 - search + k
        # 窓内の音量が極端に小さい位置（無音）は避ける
        energy = float(np.sqrt((a * a).mean()))
        score = c * min(1.0, energy / (np.sqrt((x * x).mean()) * 0.3 + 1e-9))
        if best is None or score > best[0]:
            best = (score, t, P, c)
        t += step
    if best is None:
        return None
    score, ls, P, c = best
    # loop_start 近傍 ±step をサンプル単位で詰める（継ぎ目の相関を最大化）
    fine_best = (c, ls, P)
    for d in range(-step, step + 1, max(1, step // 50)):
        t2 = ls + d
        if t2 < 0 or t2 + P + W > n:
            continue
        for dP in range(-8, 9):
            PP = P + dP
            cc = _norm_xcorr(x[t2:t2 + W], x[t2 + PP:t2 + PP + W])
            if cc > fine_best[0]:
                fine_best = (cc, t2, PP)
    c, ls, P = fine_best
    return dict(loop_start=int(ls), loop_end=int(ls + P), period=int(P), seam_score=float(c))


def find_loop(audio, sr=SR, min_period_sec=8.0, max_period_sec=None, start_hint=None, log=None):
    """
    audio: float (N, ch) または (N,)
    返り値: list[dict(loop_start, loop_end, period, seam_score, similarity, intro_sec, period_sec)]（良い順）
    """
    x = audio.mean(axis=1) if audio.ndim == 2 else audio
    x = np.ascontiguousarray(x, dtype=np.float64)
    hop = 512
    cands, fr = coarse_period(x, sr, min_period_sec, max_period_sec, hop, log)
    results = []
    for sim_mean, P0, curve in cands[:2]:
        intro = find_intro_end(curve, fr, hop) if start_hint is None else int(start_hint)
        r = refine_loop(x, P0, max(0, intro - int(0.5 * sr)), sr, log=log)
        if r is None:
            continue
        r.update(similarity=sim_mean, intro_sec=r["loop_start"] / sr, period_sec=r["period"] / sr)
        # 2 周目全体の一致度（音楽的に正しい周期かの目安）
        L = min(len(x) - r["loop_end"], r["period"])
        r["overall"] = _norm_xcorr(x[r["loop_start"]:r["loop_start"] + L],
                                   x[r["loop_end"]:r["loop_end"] + L]) if L > sr else 0.0
        results.append(r)
    results.sort(key=lambda r: (r["similarity"] * 0.5 + r["seam_score"] * 0.5), reverse=True)
    if log:
        for r in results:
            log(f"  候補: loop_start={r['loop_start']} ({r['intro_sec']:.3f}s)  loop_end={r['loop_end']} "
                f"({r['loop_end'] / sr:.3f}s)  周期={r['period_sec']:.3f}s  継ぎ目一致度={r['seam_score']:.3f}  "
                f"曲全体類似度={r['similarity']:.3f}")
    return results


def seam_score(audio, loop_start, loop_end, sr=SR, win_sec=0.5):
    """指定ループの継ぎ目の滑らかさ（1.0 が完全一致）"""
    x = audio.mean(axis=1) if audio.ndim == 2 else audio
    W = int(win_sec * sr)
    if loop_end + W > len(x):
        W = len(x) - loop_end
    return _norm_xcorr(x[loop_start:loop_start + W], x[loop_end:loop_end + W])


def make_preview(audio, loop_start, loop_end, sr=SR, pre_sec=4.0, post_sec=6.0, repeats=2):
    """継ぎ目確認用: loop_end の pre_sec 前 → (ループで戻る) → loop_start から post_sec を repeats 回"""
    parts = []
    body = audio[loop_start:loop_end]
    pre = audio[max(loop_start, loop_end - int(pre_sec * sr)):loop_end]
    for _ in range(repeats):
        parts.append(pre)
        parts.append(body[:int(post_sec * sr)])
    return np.concatenate(parts)
