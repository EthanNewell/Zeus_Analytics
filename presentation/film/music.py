"""Оригинальная музыка к ролику — синтез кодом, без сэмплов и чужих записей.

100 BPM, ре минор, прогрессия Dm – B♭ – F – C. Разделы и их длина в тактах — из timeline.json,
те же, по которым смонтирована картинка, поэтому смены сцен приходятся на сильные доли.

    python3 presentation/film/music.py   → presentation/film/music.wav
"""

import json
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, fftconvolve, sosfilt

HERE = Path(__file__).parent
SR = 44100
TL = json.loads((HERE / "timeline.json").read_text())
BEAT = 60 / TL["bpm"]
BAR = 4 * BEAT
TOTAL_BARS = sum(s["bars"] for s in TL["sections"])
TAIL = 4.0
N = int((TOTAL_BARS * BAR + TAIL) * SR)
rng = np.random.default_rng(7)

# Раздел каждого такта.
BAR_MODE = []
for s in TL["sections"]:
    BAR_MODE += [s["music"]] * s["bars"]
SECTION_STARTS = np.cumsum([0] + [s["bars"] for s in TL["sections"]])[:-1]

# Dm – B♭ – F – C: корень и тоны аккорда (MIDI).
PROG = [(50, [62, 65, 69, 72]), (46, [62, 65, 70, 74]), (53, [60, 65, 69, 72]), (48, [60, 64, 67, 72])]


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def at(sec):
    return int(sec * SR)


def env_adsr(n, a, d, s, r):
    a, d, r = at(a), at(d), at(r)
    e = np.full(n, s, dtype=np.float64)
    if a:
        e[: min(a, n)] = np.linspace(0, 1, a)[: min(a, n)]
    if d and a < n:
        seg = e[a : min(a + d, n)]
        e[a : min(a + d, n)] = np.linspace(1, s, d)[: len(seg)]
    if r and n > r:
        e[n - r :] *= np.linspace(1, 0, r)
    return e


def additive_saw(freq, n, bright=8.0, detune=0.0, phase=0.0):
    t = np.arange(n) / SR
    out = np.zeros(n)
    k = 1
    while k * freq < 12000 and k < 40:
        amp = (1.0 / k) * np.exp(-(k - 1) / bright)
        out += amp * np.sin(2 * np.pi * k * freq * (1 + detune) * t + phase * k)
        k += 1
    return out


def add(buf, start, sig, pan=0.0, gain=1.0):
    i = at(start)
    j = min(i + len(sig), N)
    if j <= i:
        return
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    buf[0, i:j] += sig[: j - i] * gain * l * 1.414
    buf[1, i:j] += sig[: j - i] * gain * r * 1.414


def bandpass(x, lo, hi):
    return sosfilt(butter(2, [lo, hi], btype="band", fs=SR, output="sos"), x)


def highpass(x, f):
    return sosfilt(butter(2, f, btype="high", fs=SR, output="sos"), x)


def lowpass(x, f):
    return sosfilt(butter(2, f, btype="low", fs=SR, output="sos"), x)


pad = np.zeros((2, N))
bass = np.zeros((2, N))
arp = np.zeros((2, N))
drums = np.zeros((2, N))
fx = np.zeros((2, N))
kick_env = np.zeros(N)

BRIGHT = {"intro": 2.5, "build": 3.5, "rise": 5, "drop": 6, "break": 3, "peak": 9, "half": 4, "outro": 2.5}

for b in range(TOTAL_BARS):
    mode = BAR_MODE[b]
    t0 = b * BAR
    root, chord = PROG[b % 4]

    # Пэд: аккорд бара, мягкая атака, перехлёст на следующий бар.
    n = at(BAR + 1.2)
    for i, m in enumerate(chord[:3] if mode in ("intro", "outro") else chord):
        voice = sum(additive_saw(hz(m), n, BRIGHT[mode], d, ph) for d, ph in ((-0.004, 0), (0.0, 1.3), (0.005, 2.1)))
        voice *= env_adsr(n, 0.9 if mode in ("intro", "outro") else 0.35, 0.6, 0.8, 1.2)
        add(pad, t0, voice, pan=(-0.5, 0.5, -0.2, 0.3)[i], gain=0.035)

    # Бас: суб на корне; в «drop/peak» — восьмые с затуханием, в остальных — длинная нота.
    if mode in ("drop", "peak", "rise", "build"):
        steps = 8
        for k in range(steps):
            if mode == "build" and k % 2:
                continue
            nn = at(BEAT / 2 * 0.95)
            tt = np.arange(nn) / SR
            f = hz(root - 12)
            sig = np.sin(2 * np.pi * f * tt) + 0.35 * np.sin(2 * np.pi * 2 * f * tt) + 0.15 * np.sign(np.sin(2 * np.pi * f * tt))
            sig *= np.exp(-tt * (6 if mode != "build" else 3))
            add(bass, t0 + k * BEAT / 2, sig, gain=0.22)
    elif mode in ("intro", "break", "half", "outro"):
        nn = at(BAR)
        tt = np.arange(nn) / SR
        sig = np.sin(2 * np.pi * hz(root - 12) * tt) * env_adsr(nn, 0.4, 0.5, 0.7, 0.8)
        add(bass, t0, sig, gain=0.16)

    # Арпеджио: шестнадцатые по тонам аккорда, FM-щипок.
    if mode in ("rise", "drop", "peak", "break", "half"):
        pattern = [0, 1, 2, 3, 2, 1, 2, 3, 0, 2, 1, 3, 2, 1, 3, 2]
        for k in range(16):
            if mode == "half" and k % 2:
                continue
            if mode == "rise" and b % 4 < 2 and k % 2:
                continue
            m = chord[pattern[k]] + (12 if (mode == "peak" and k % 4 == 3) else 0)
            nn = at(0.28)
            tt = np.arange(nn) / SR
            f = hz(m + 12)
            idx = 2.2 * np.exp(-tt * 18)
            sig = np.sin(2 * np.pi * f * tt + idx * np.sin(2 * np.pi * 2 * f * tt)) * np.exp(-tt * 14)
            add(arp, t0 + k * BEAT / 4, sig, pan=0.35 if k % 2 else -0.35, gain=0.05 if mode != "break" else 0.035)

    # Барабаны.
    if mode in ("drop", "peak"):
        for k in range(4):
            kt = t0 + k * BEAT
            nn = at(0.42)
            tt = np.arange(nn) / SR
            f = 45 + 85 * np.exp(-tt * 30)
            ph = 2 * np.pi * np.cumsum(f) / SR
            sig = np.sin(ph) * np.exp(-tt * 7) + 0.3 * np.exp(-tt * 300) * rng.standard_normal(nn) * 0.3
            add(drums, kt, sig, gain=0.55)
            i = at(kt)
            e = np.exp(-np.arange(at(0.3)) / SR * 9)
            j = min(i + len(e), N)
            kick_env[i:j] = np.maximum(kick_env[i:j], e[: j - i])
        for k in (1, 3):
            nn = at(0.25)
            noise = bandpass(rng.standard_normal(nn), 900, 3200)
            tt = np.arange(nn) / SR
            clap = noise * (np.exp(-tt * 28) + 0.6 * np.exp(-np.maximum(tt - 0.012, 0) * 30) * (tt > 0.012))
            add(drums, t0 + k * BEAT, clap, pan=0.05, gain=0.16)
    if mode in ("build", "rise", "drop", "peak", "break", "half"):
        for k in range(8):
            nn = at(0.05 if k % 2 == 0 else 0.14)
            tt = np.arange(nn) / SR
            hat = highpass(rng.standard_normal(nn), 7000) * np.exp(-tt * (90 if k % 2 == 0 else 26))
            g = 0.05 if k % 2 else 0.03
            if mode in ("break", "half") and k % 2 == 0:
                continue
            add(drums, t0 + k * BEAT / 2, hat, pan=0.25 if k % 2 else -0.15, gain=g)
    if mode == "half":
        for k in (0, 2):
            nn = at(0.5)
            tt = np.arange(nn) / SR
            f = 42 + 70 * np.exp(-tt * 22)
            sig = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 5)
            add(drums, t0 + k * BEAT, sig, gain=0.45)

# Нарастание перед «падением» и перед пиком.
for s, sec in zip(SECTION_STARTS, TL["sections"]):
    if sec["music"] == "rise":
        dur = sec["bars"] * BAR
        nn = at(dur)
        tt = np.arange(nn) / SR
        noise = rng.standard_normal(nn)
        out = np.zeros(nn)
        chunk = 2048
        for i in range(0, nn, chunk):
            frac = i / nn
            lo = 300 + 6000 * frac ** 2
            out[i : i + chunk] = bandpass(noise[i : i + chunk], lo, min(lo * 2.2, 18000))
        out *= (tt / dur) ** 2.2 * 0.5
        sweep = np.sin(2 * np.pi * np.cumsum(220 * 2 ** (3 * tt / dur)) / SR) * (tt / dur) ** 3 * 0.12
        add(fx, s * BAR, out + sweep, gain=0.6)

# Удар на каждой смене сцены: суб и шумовой хвост.
for s, sec in zip(SECTION_STARTS, TL["sections"]):
    if s == 0:
        continue
    nn = at(2.2)
    tt = np.arange(nn) / SR
    boom = np.sin(2 * np.pi * np.cumsum(38 + 40 * np.exp(-tt * 6)) / SR) * np.exp(-tt * 2.2)
    tail = lowpass(rng.standard_normal(nn), 2500) * np.exp(-tt * 3.5) * 0.25
    add(fx, s * BAR, boom * 0.55 + tail, gain=0.5 if sec["music"] != "outro" else 0.7)

# Последний аккорд: длинный, раскрывается в тишину.
end = TOTAL_BARS * BAR
nn = at(TAIL + 0.5)
for i, m in enumerate([50, 57, 62, 65, 69]):
    v = additive_saw(hz(m), nn, 3, 0.003) * env_adsr(nn, 0.05, 1.0, 0.5, 3.2)
    add(pad, end - 0.02, v, pan=(-0.6, -0.3, 0, 0.3, 0.6)[i], gain=0.04)

# Сайдчейн: пэд и бас «дышат» под бочку.
duck = 1 - 0.55 * kick_env
pad *= duck
bass *= 1 - 0.7 * kick_env

# Реверберация: синтетический отклик 2,8 с на пэд, арпеджио и удары.
ir_n = at(2.8)
ir_t = np.arange(ir_n) / SR
ir = np.stack([rng.standard_normal(ir_n), rng.standard_normal(ir_n)]) * np.exp(-ir_t * 2.4)
ir = np.stack([lowpass(ir[0], 6000), lowpass(ir[1], 6000)])
ir /= np.abs(ir).sum(axis=1, keepdims=True) ** 0.5 * 40
send = pad * 0.6 + arp * 0.9 + fx * 0.4
wet = np.stack([fftconvolve(send[c], ir[c])[:N] for c in range(2)])

# Пинг-понг задержка на арпеджио (3/16).
d = at(BEAT * 0.75)
echo = np.zeros_like(arp)
for rep in range(1, 5):
    side = np.array([[0.4], [1.0]]) if rep % 2 else np.array([[1.0], [0.4]])
    echo[:, d * rep :] += arp[:, : N - d * rep] * 0.38**rep * side

mix = pad + bass + arp + echo * 0.6 + drums + fx + wet * 0.9
mix = np.stack([highpass(mix[c], 28) for c in range(2)])
fade_in = np.clip(np.arange(N) / at(1.5), 0, 1)
mix *= fade_in
mix = np.tanh(mix * 1.6) / np.tanh(1.6)
mix /= np.abs(mix).max() / 0.89
wavfile.write(HERE / "music.wav", SR, (mix.T * 32767).astype(np.int16))
print(f"готово: presentation/film/music.wav, {N / SR:.1f} с, {TOTAL_BARS} тактов")
