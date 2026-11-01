"""Background music synthesised in numpy, so the video carries no licensed track: a short build-up, then a four-on-the-
floor drop locked to the beats where entries appear, with a whoosh and an impact on every entry. Change the chords,
tempo or sounds here; nothing is sampled.

    from music import track; track(beats, total, path)   # beats = entry times (s); the bar grid is built from them
"""
import numpy as np
from scipy.signal import butter, lfilter, sosfilt

SR = 48000
RNG = np.random.default_rng(3)
NOTE = {n: i for i, n in enumerate(['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'])}


def hz(name):
    """'A3' -> 220 Hz."""
    n, o = name[:-1], int(name[-1])
    return 440.0 * 2 ** ((NOTE[n] + 12 * (o + 1) - 69) / 12)


def env(n, a=0.005, d=0.1, s=0.0, r=0.05, hold=None):
    """Attack-decay-sustain-release envelope over n samples (hold = samples before release, default all)."""
    t = np.arange(n) / SR
    hold = n / SR - r if hold is None else hold
    e = np.where(t < a, t / max(a, 1e-6), s + (1 - s) * np.exp(-(t - a) / max(d, 1e-6)))
    rel = np.clip(1 - (t - hold) / max(r, 1e-6), 0, 1)
    return e * np.where(t > hold, rel, 1)


def saw(f, n, detune=0.0, voices=1, phase_rng=True):
    t = np.arange(n) / SR
    out = np.zeros(n)
    for v in range(voices):
        dv = (v - (voices - 1) / 2) / max(voices - 1, 1) * detune
        ph = RNG.random() if phase_rng else 0
        out += 2 * ((t * f * (1 + dv) + ph) % 1) - 1
    return out / voices


def lowpass(x, fc, order=2):
    return sosfilt(butter(order, min(fc, SR / 2 * 0.95), 'low', fs=SR, output='sos'), x)


def highpass(x, fc, order=2):
    return sosfilt(butter(order, fc, 'high', fs=SR, output='sos'), x)


def sweep_lowpass(x, f0, f1):
    """A one-pole lowpass whose cutoff glides exponentially from f0 to f1 (block-wise)."""
    out = np.zeros_like(x)
    blocks = np.array_split(np.arange(len(x)), 64)
    zi = None
    for i, idx in enumerate(blocks):
        fc = f0 * (f1 / f0) ** (i / (len(blocks) - 1))
        b, a = butter(2, min(fc, SR / 2 * 0.95), 'low', fs=SR)
        if zi is None:
            zi = np.zeros(max(len(a), len(b)) - 1)
        out[idx], zi = lfilter(b, a, x[idx], zi=zi)
    return out


def add(buf, x, t, gain=1.0, pan=0.0):
    i = int(round(t * SR))
    if i >= buf.shape[0]:
        return
    if i < 0:
        x, i = x[-i:], 0
    n = min(len(x), buf.shape[0] - i)
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    buf[i:i + n, 0] += x[:n] * gain * l * 1.414
    buf[i:i + n, 1] += x[:n] * gain * r * 1.414


# ---------------------------------------------------------------- instruments


def kick(n=int(0.45 * SR)):
    t = np.arange(n) / SR
    f = 45 + 110 * np.exp(-t / 0.035)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) * env(n, 0.001, 0.22, 0, 0.05)
    click = lowpass(RNG.normal(size=n), 4000) * env(n, 0.0005, 0.004)
    return np.tanh(1.6 * (x + 0.3 * click))


def clap(n=int(0.3 * SR)):
    x = RNG.normal(size=n)
    x = highpass(lowpass(x, 5000), 900)
    e = np.zeros(n)
    for k, dt in enumerate((0, 0.009, 0.018)):
        i = int(dt * SR)
        e[i:] += env(n - i, 0.001, 0.012 if k < 2 else 0.11)
    return x * e * 0.8


def hat(n=int(0.12 * SR), open_=False):
    x = highpass(RNG.normal(size=n), 7000)
    return x * env(n, 0.001, 0.09 if open_ else 0.025) * 0.5


def supersaw_chord(notes, dur, cutoff=4500):
    n = int(dur * SR)
    x = sum(saw(hz(m), n, detune=0.012, voices=5) for m in notes) / len(notes)
    return lowpass(x, cutoff) * env(n, 0.01, 10, 1, 0.05)


def pluck(note, dur=0.22):
    n = int(dur * SR)
    x = saw(hz(note), n, detune=0.006, voices=3)
    return sweep_lowpass(x, 6000, 600) * env(n, 0.002, 0.09)


def bass(note, dur):
    n = int(dur * SR)
    f = hz(note)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * f * t) + 0.25 * lowpass(saw(f, n), 900)
    return np.tanh(1.3 * x) * env(n, 0.004, 10, 1, 0.03)


def whoosh(dur=0.5, up=False):
    n = int(dur * SR)
    x = RNG.normal(size=n)
    x = sweep_lowpass(x, 300, 9000) if up else sweep_lowpass(x, 9000, 400)
    t = np.linspace(0, 1, n)
    shape = np.sin(np.pi * t) ** 1.5 if not up else t ** 2.5
    return x * shape * 0.6


def impact(n=int(1.2 * SR)):
    t = np.arange(n) / SR
    f = 38 + 60 * np.exp(-t / 0.08)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.35)
    noise = lowpass(RNG.normal(size=n), 1800) * np.exp(-t / 0.08) * 0.4
    return np.tanh(1.4 * (x + noise))


def crash(n=int(2.0 * SR)):
    x = highpass(RNG.normal(size=n), 4500)
    return x * env(n, 0.002, 0.7) * 0.35


# ---------------------------------------------------------------- the track


PROG = [  # one chord per entry (two bars); a minor pop progression
    (['A3', 'C4', 'E4'], 'A2'), (['F3', 'A3', 'C4'], 'F2'), (['C4', 'E4', 'G4'], 'C2'), (['G3', 'B3', 'D4'], 'G2'),
]
ARP = [0, 1, 2, 1, 2, 0, 2, 1]  # chord tones for the eighth-note lead, shifted up an octave


def track(beats, total, path=None, fade=0.25):
    period = beats[1] - beats[0]
    # quarter notes per entry: 4, 8 or 16, whichever puts the tempo nearest 130 BPM (3.3 s -> 8 = 145 BPM,
    # 2 s -> 4 = 121 BPM)
    nq = min((4, 8, 16), key=lambda n: abs(60 / (period / n) - 130))
    q = period / nq  # quarter note
    buf = np.zeros((int(total * SR) + SR, 2))
    t0 = beats[0]
    if t0 >= 0.5:
        # build-up: filtered chord swell, rising noise, a snare roll that speeds up into the drop
        n_in = int(t0 * SR)
        pad = supersaw_chord(PROG[3][0], t0, cutoff=12000)
        pad = sweep_lowpass(pad, 300, 5000) * np.linspace(0.25, 1, n_in)
        add(buf, pad, 0, 0.32)
        add(buf, whoosh(t0, up=True), 0, 0.5)
        k = 0.0
        step = q
        while t0 - k > 0.15:
            add(buf, clap(), t0 - k, 0.12 + 0.4 * (1 - (t0 - k) / t0))
            k += step
            step = max(q / 4, step * 0.82)
    # the drop: four on the floor from the first beat to the end
    n_q = int((total - t0) / q) + 1
    for i in range(n_q):
        t = t0 + i * q
        bar_beat = i % 4
        add(buf, kick(), t, 0.42)
        if bar_beat in (1, 3):
            add(buf, clap(), t, 0.5, pan=0.05)
        add(buf, hat(open_=True), t + q / 2, 0.1, pan=0.3)
        add(buf, hat(), t + q / 4, 0.035, pan=-0.3)
        add(buf, hat(), t + 3 * q / 4, 0.035, pan=-0.3)
    # chords (sidechained to the kick), bass on the offbeats, lead arpeggio
    for e in range(int(np.ceil((total - t0) / period))):
        chord, root = PROG[e % len(PROG)]
        ts = t0 + e * period
        dur = min(period, total + 0.5 - ts)
        c = supersaw_chord(chord, dur)
        tt = np.arange(len(c)) / SR
        duck = 1 - 0.75 * np.exp(-(tt % q) / 0.09)
        add(buf, c * duck, ts, 1.3)
        for i in range(nq):
            add(buf, bass(root, q / 2 * 0.9), ts + i * q + q / 2, 0.38)
        for i in range(2 * nq):
            note = chord[ARP[i % 8]]
            up = note[:-1] + str(int(note[-1]) + 1)
            add(buf, pluck(up), ts + i * q / 2, 0.8, pan=0.25 if i % 2 else -0.25)
    # every entry: whoosh into it, impact on it; the last one gets a crash
    for i, b in enumerate(beats):
        if b < 0.2:  # an opening entry at 0 s gets the impact but no whoosh into it
            add(buf, impact(), b, 0.3)
            continue
        add(buf, whoosh(0.45), b - 0.18, 0.35)
        add(buf, impact(), b, 0.3)
        if i in (0, len(beats) - 1):
            add(buf, crash(), b, 0.3)
    buf = buf[:int(total * SR)]
    buf = np.stack([lowpass(buf[:, c], 11000, 4) for c in range(2)], 1)
    nf = int(fade * SR)
    buf[-nf:] *= np.linspace(1, 0, nf)[:, None]
    buf = np.tanh(buf * 1.1)
    buf *= 0.89 / np.abs(buf).max()
    if path:
        import wave
        with wave.open(path, 'wb') as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((buf * 32767).astype('<i2').tobytes())
    return buf
