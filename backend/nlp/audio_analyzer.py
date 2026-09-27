"""Vocal stress feature extraction.

Honesty rules baked into this module
------------------------------------
* Every result carries `method`. The prototype ships a **heuristic** feature
  extractor, so the default is `method="heuristic-demo"`. It is labelled that
  way in the counsellor UI, in the API payload and in the README. We never
  present these numbers as the output of a trained classifier.
* A synthetic demo signal (generated in the browser because no microphone is
  available) is tagged `notes="synthetic_demo_signal"` and forced to
  `heuristic-demo` even if a real model is ever wired in.
* If the audio cannot be decoded at all we return `vocal_stress_score=None`
  and `method="unavailable"`. We never invent a number.

Feature extraction order of preference
--------------------------------------
1. `librosa` (if installed) - autocorrelation/pyin F0, RMS energy, silence
   segmentation, spectral-flux onset rate as a syllable-rate proxy.
2. Pure-numpy autocorrelation fallback so the demo still works in an
   environment without librosa.

Upload contract
---------------
Browsers record to `audio/webm;codecs=opus`, which librosa cannot read without
an ffmpeg binary. The frontend therefore decodes to 16 kHz mono PCM WAV via the
Web Audio API before upload. This module still accepts whatever it is given and
degrades explicitly.
"""

from __future__ import annotations

import io
import logging
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from config import settings

log = logging.getLogger(__name__)

TARGET_SR = 16000
FRAME_MS = 40.0
MIN_ANALYSABLE_SEC = 0.35
#: RMS below this (relative to the clip's own peak frame) counts as a pause.
PAUSE_RELATIVE_THRESHOLD = 0.18
MIN_PAUSE_SEC = 0.18
#: Plausible syllable-rate window for adult conversational speech.
RATE_LOW, RATE_HIGH = 1.5, 7.5

# Human-readable reference ranges, used to normalise features to 0-100.
# These are broad conversational-speech norms for adults, not clinical cutoffs,
# and they are exposed in the payload so a reviewer can see the assumptions.
REFERENCE_RANGES = {
    "pitch_mean_hz": {"typical_low": 85.0, "typical_high": 210.0, "note": "Broad adult conversational range; varies widely with speaker and language."},
    "pitch_var_hz": {"elevated_above": 900.0, "note": "F0 variance; wide swings co-occur with arousal, but also with prosody and dialect."},
    "jitter_proxy_ratio": {"typical_low": 0.01, "typical_high": 0.09, "note": "Cycle-to-cycle F0 instability proxy."},
    "pause_ratio": {"typical_low": 0.08, "typical_high": 0.55, "note": "Fraction of clip below the relative energy floor."},
    "speaking_rate_syl_sec": {"typical_low": 1.5, "typical_high": 7.5, "note": "Onset-flux proxy for syllable rate, not a measured articulatory rate."},
}


@dataclass
class AudioRiskResult:
    pitch_mean: Optional[float] = None
    pitch_var: Optional[float] = None
    jitter_proxy: Optional[float] = None
    pause_count: Optional[int] = None
    pause_ratio: Optional[float] = None
    speaking_rate: Optional[float] = None
    energy_rms: Optional[float] = None
    duration_sec: Optional[float] = None
    vocal_stress_score: Optional[float] = None
    method: str = "heuristic-demo"
    confidence: float = 0.0
    notes: Optional[str] = None
    features: Dict[str, Any] = None  # type: ignore[assignment]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "pitch_mean": self.pitch_mean,
            "pitch_var": self.pitch_var,
            "jitter_proxy": self.jitter_proxy,
            "pause_count": self.pause_count,
            "pause_ratio": self.pause_ratio,
            "speaking_rate": self.speaking_rate,
            "energy_rms": self.energy_rms,
            "duration_sec": self.duration_sec,
            "vocal_stress_score": self.vocal_stress_score,
            "method": self.method,
            "confidence": self.confidence,
            "notes": self.notes,
            "features": self.features or {},
            "reference_ranges": REFERENCE_RANGES,
        }


# --------------------------------------------------------------------------
# Decoding
# --------------------------------------------------------------------------

def _read_wav_bytes(data: bytes) -> Optional[Tuple[np.ndarray, int]]:
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            channels = wav.getnchannels()
            width = wav.getsampwidth()
            rate = wav.getframerate()
            frames = wav.readframes(wav.getnframes())
    except (wave.Error, EOFError):
        return None

    if width == 1:
        data_arr = np.frombuffer(frames, dtype=np.uint8).astype(np.float32)
        samples = (data_arr - 128.0) / 128.0
    elif width == 2:
        data_arr = np.frombuffer(frames, dtype="<i2").astype(np.float32)
        samples = data_arr / 32768.0
    elif width == 4:
        data_arr = np.frombuffer(frames, dtype="<i4").astype(np.float32)
        samples = data_arr / 2147483648.0
    else:
        return None

    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)

    target_rate = TARGET_SR
    if rate != target_rate and rate > 0:
        # Linear resample. Adequate for 16 kHz feature work and avoids a hard
        # librosa dependency in the fallback path.
        n_out = int(round(len(samples) * target_rate / rate))
        if n_out < 1 or len(samples) < 2:
            return None
        x_old = np.linspace(0.0, 1.0, num=len(samples), endpoint=False)
        x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
        samples = np.interp(x_new, x_old, samples).astype(np.float32)
        rate = target_rate

    return samples, rate


def _load_via_soundfile(path: Path) -> Optional[Tuple[np.ndarray, int]]:
    try:
        import soundfile as sf  # type: ignore

        data, rate = sf.read(str(path), dtype="float32", always_2d=False)
        if data.ndim > 1:
            data = data.mean(axis=1)
        if rate != TARGET_SR:
            import librosa  # type: ignore

            data = librosa.resample(data, orig_sr=rate, target_sr=TARGET_SR)
            rate = TARGET_SR
        return np.asarray(data, dtype=np.float32), rate
    except Exception as exc:  # noqa: BLE001
        log.info("soundfile could not decode %s (%s)", path.name, type(exc).__name__)
        return None


def _load(path: str | Path) -> Optional[Tuple[np.ndarray, int, str]]:
    p = Path(path)
    if not p.exists():
        log.warning("Audio file not found: %s", p)
        return None

    if settings.audio_backend != "heuristic":
        loaded = _load_via_soundfile(p)
        if loaded is not None:
            return loaded[0], loaded[1], "soundfile"

    loaded = _read_wav_bytes(p.read_bytes())
    if loaded is not None:
        return loaded[0], loaded[1], "numpy-wav"
    return None


# --------------------------------------------------------------------------
# Feature extraction
# --------------------------------------------------------------------------

def _frames(samples: np.ndarray, rate: int) -> np.ndarray:
    frame_len = max(1, int(rate * FRAME_MS / 1000.0))
    n_frames = max(1, len(samples) // frame_len)
    trimmed = samples[: n_frames * frame_len]
    if trimmed.size == 0:
        return np.zeros((1, frame_len), dtype=np.float32)
    return trimmed.reshape(n_frames, frame_len)


def _rms_per_frame(frames: np.ndarray) -> np.ndarray:
    return np.sqrt(np.mean(np.square(frames), axis=1) + 1e-12)


def _energy_peak_count(rms: np.ndarray) -> int:
    """Count energy-envelope peaks as a syllable-rate proxy.

    One shared definition for both extractors, on purpose. librosa's
    `onset_detect` returned roughly five times as many events as this on the
    same signal, so a clip scored differently depending on whether librosa
    happened to be installed. The number is a proxy either way, and a proxy
    with one definition is worth more than a "better" metric that changes
    meaning with the environment.
    """
    if rms.size <= 2:
        return 0
    flux = np.diff(rms, prepend=rms[0])
    positive = flux[flux > 0]
    if not positive.size:
        return 0
    threshold = float(np.mean(positive)) * 1.6
    return int(np.sum(positive > threshold))


def _f0_autocorrelation(frames: np.ndarray, rate: int, fmin: float, fmax: float) -> List[float]:
    """Normalised-autocorrelation F0 estimate per frame (NSDF-lite)."""
    frame_len = frames.shape[1]
    min_lag = max(2, int(rate / fmax))
    max_lag = min(frame_len - 1, int(rate / fmin))
    if max_lag <= min_lag:
        return []

    windowed = frames - frames.mean(axis=1, keepdims=True)
    out: List[float] = []
    for row in windowed:
        energy = float(np.dot(row, row))
        if energy <= 1e-9:
            continue
        corr = np.correlate(row, row, mode="full")[frame_len - 1 :]
        segment = corr[min_lag : max_lag + 1]
        if segment.size == 0:
            continue
        lag = int(np.argmax(segment)) + min_lag
        peak = float(corr[lag]) / energy
        if peak < 0.28:  # below this the frame is unvoiced/silence
            continue
        out.append(rate / lag)
    return out


def _librosa_features(samples: np.ndarray, rate: int) -> Optional[Dict[str, Any]]:
    if settings.audio_backend == "heuristic":
        return None
    try:
        import librosa  # type: ignore
    except Exception:  # noqa: BLE001
        return None

    try:
        f0, voiced_flag, voiced_probs = librosa.pyin(
            samples, fmin=70.0, fmax=400.0, sr=rate, frame_length=1024, hop_length=256
        )
        rms = librosa.feature.rms(y=samples, frame_length=1024, hop_length=256)[0]
        # Derive librosa's relative threshold from the same constant the numpy
        # path uses. librosa's default top_db=30 is about twice as insensitive
        # as PAUSE_RELATIVE_THRESHOLD, so the *same* clip was scored differently
        # depending on which backend happened to be installed.
        top_db = abs(20.0 * float(np.log10(PAUSE_RELATIVE_THRESHOLD)))
        non_silent = librosa.effects.split(samples, top_db=top_db)
    except Exception as exc:  # noqa: BLE001
        log.warning("librosa feature extraction failed (%s); using numpy path", type(exc).__name__)
        return None

    voiced = f0[~np.isnan(f0)] if f0 is not None else np.array([])
    voiced_ratio = float(np.mean(voiced_flag)) if voiced_flag is not None else 0.0

    total_sec = len(samples) / rate

    # Pauses are the *gaps between* speech segments, not the segments. Getting
    # this backwards inflated pause_ratio for long unbroken speech and
    # suppressed it for genuinely halting speech, which is the opposite of what
    # the feature is for. Walk the segment list and measure the holes.
    silence_sec = 0.0
    pause_count = 0
    cursor = 0
    for start, end in (*non_silent, (len(samples), len(samples))):
        gap_sec = (int(start) - cursor) / rate
        if gap_sec > 0.0:
            silence_sec += gap_sec
            if gap_sec >= MIN_PAUSE_SEC:
                pause_count += 1
        cursor = max(cursor, int(end))
    pause_ratio = min(1.0, silence_sec / total_sec) if total_sec else 0.0

    # Shared energy-peak rate proxy, computed on the shared 40 ms frame grid so
    # it is numerically comparable with the numpy path.
    shared_rms = _rms_per_frame(_frames(samples, rate))

    return {
        "pitch_values": voiced,
        "pitch_var": float(np.var(voiced)) if voiced.size > 1 else 0.0,
        "voiced_ratio": voiced_ratio,
        "voiced_prob_mean": float(np.mean(voiced_probs)) if voiced_probs is not None and np.size(voiced_probs) else 0.0,
        "energy_rms": float(np.mean(rms)) if rms.size else 0.0,
        "energy_dynamic_range": float(np.percentile(rms, 90) - np.percentile(rms, 10)) if rms.size else 0.0,
        "pause_count": pause_count,
        "pause_ratio": pause_ratio,
        "speaking_rate": _energy_peak_count(shared_rms) / total_sec if total_sec else 0.0,
        "backend": "librosa",
    }


def _numpy_features(samples: np.ndarray, rate: int) -> Dict[str, Any]:
    frames = _frames(samples, rate)
    rms = _rms_per_frame(frames)
    peak = float(np.max(rms)) if rms.size else 0.0
    floor = max(1e-5, peak * PAUSE_RELATIVE_THRESHOLD)
    silent = rms < floor
    total_sec = len(samples) / rate
    pause_ratio = float(np.mean(silent)) if silent.size else 0.0

    # Count contiguous silent runs at least MIN_PAUSE_SEC long.
    run_frames = max(1, int(MIN_PAUSE_SEC / (FRAME_MS / 1000.0)))
    pause_count = 0
    run = 0
    for is_silent in silent:
        if is_silent:
            run += 1
        else:
            if run >= run_frames:
                pause_count += 1
            run = 0
    if run >= run_frames:
        pause_count += 1

    f0_values = _f0_autocorrelation(frames, rate, fmin=70.0, fmax=400.0)
    peaks = _energy_peak_count(rms)

    return {
        "pitch_values": np.asarray(f0_values, dtype=np.float64),
        "pitch_var": float(np.var(f0_values)) if len(f0_values) > 1 else 0.0,
        "voiced_ratio": len(f0_values) / max(1, len(rms)),
        "voiced_prob_mean": 0.0,
        "energy_rms": float(np.mean(rms)) if rms.size else 0.0,
        "energy_dynamic_range": float(np.percentile(rms, 90) - np.percentile(rms, 10)) if rms.size else 0.0,
        "pause_count": pause_count,
        "pause_ratio": pause_ratio,
        "speaking_rate": peaks / total_sec if total_sec else 0.0,
        "backend": "numpy",
    }


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------

def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _norm(value: float, low: float, high: float) -> float:
    """Map value into 0-1 where `high` maps to 1 and `low` to 0."""
    if high <= low:
        return 0.0
    return _clamp01((value - low) / (high - low))


def _high_norm(value: float, anchor: float) -> float:
    """0-1 ramp where `anchor` is the fully-stressed value."""
    if anchor <= 0:
        return 0.0
    return _clamp01(value / anchor)


def score_vocal_stress(features: Dict[str, Any]) -> tuple[float, List[str]]:
    """Weighted sum of bounded feature normalisations. Returns (score, reasons)."""
    reasons: List[str] = []
    weights = {
        "jitter_proxy": 0.22,
        "pitch_var": 0.20,
        "pause_ratio": 0.18,
        "speaking_rate": 0.14,
        "energy_dynamic": 0.16,
        "pitch_level": 0.10,
    }
    parts: Dict[str, float] = {}

    pitch_values = features.get("pitch_values")
    pitch_mean = float(np.mean(pitch_values)) if pitch_values is not None and np.size(pitch_values) else 0.0
    pitch_var = float(features.get("pitch_var") or 0.0)

    if pitch_values is not None and np.size(pitch_values) > 1:
        successive = np.abs(np.diff(pitch_values))
        jitter = float(np.mean(successive) / pitch_mean) if pitch_mean > 0 else 0.0
    else:
        jitter = 0.0
    jitter_n = _norm(jitter, REFERENCE_RANGES["jitter_proxy_ratio"]["typical_low"], REFERENCE_RANGES["jitter_proxy_ratio"]["typical_high"])
    parts["jitter_proxy"] = jitter_n
    if jitter_n > 0.55:
        reasons.append(f"unstable_pitch(jitter_proxy={jitter:.3f})")

    pitch_var_n = _high_norm(pitch_var, REFERENCE_RANGES["pitch_var_hz"]["elevated_above"])
    parts["pitch_var"] = pitch_var_n
    if pitch_var_n > 0.6:
        reasons.append(f"wide_pitch_variation(var={pitch_var:.0f}Hz)")

    pause_ratio = float(features.get("pause_ratio") or 0.0)
    pause_n = _norm(pause_ratio, REFERENCE_RANGES["pause_ratio"]["typical_low"], REFERENCE_RANGES["pause_ratio"]["typical_high"])
    parts["pause_ratio"] = pause_n
    if pause_n > 0.6:
        reasons.append(f"prolonged_pauses(ratio={pause_ratio:.2f}, count={features.get('pause_count')})")

    rate = float(features.get("speaking_rate") or 0.0)
    rate_n = _norm(rate, REFERENCE_RANGES["speaking_rate_syl_sec"]["typical_low"], REFERENCE_RANGES["speaking_rate_syl_sec"]["typical_high"])
    parts["speaking_rate"] = rate_n
    if rate_n > 0.7:
        reasons.append(f"elevated_speaking_rate({rate:.1f}/s proxy)")

    dyn = float(features.get("energy_dynamic_range") or 0.0)
    energy_n = _norm(dyn, 0.0, 0.08)
    parts["energy_dynamic"] = energy_n
    if energy_n > 0.65:
        reasons.append("unstable_loudness")

    pitch_level_n = _norm(pitch_mean, REFERENCE_RANGES["pitch_mean_hz"]["typical_low"], REFERENCE_RANGES["pitch_mean_hz"]["typical_high"])
    parts["pitch_level"] = pitch_level_n
    if pitch_level_n > 0.8:
        reasons.append(f"raised_pitch_level({pitch_mean:.0f}Hz)")

    score = sum(weights[k] * parts[k] for k in weights) * 100.0
    return round(_clamp01(score / 100.0) * 100.0, 2), reasons


def analyze_audio_file(
    path: str | Path,
    provenance: str = "real",
) -> AudioRiskResult:
    """Extract vocal-stress features from a WAV file.

    `provenance` must be "real" or "synthetic_demo". A synthetic signal is
    never presented as a real measurement: it is forced to
    `method="heuristic-demo"` and annotated.
    """
    loaded = _load(path)
    if loaded is None:
        return AudioRiskResult(
            vocal_stress_score=None,
            method="unavailable",
            confidence=0.0,
            notes="Audio could not be decoded. Upload 16 kHz mono PCM WAV.",
            features={},
        )

    samples, rate, decoder = loaded
    if samples.size == 0:
        return AudioRiskResult(
            vocal_stress_score=None, method="unavailable", confidence=0.0,
            notes="Empty audio payload.", features={},
        )

    duration = len(samples) / float(rate)
    if duration < MIN_ANALYSABLE_SEC:
        return AudioRiskResult(
            duration_sec=round(duration, 3),
            vocal_stress_score=None,
            method="unavailable",
            confidence=0.0,
            notes=f"Clip too short to analyse (need > {MIN_ANALYSABLE_SEC}s of speech).",
            features={},
        )

    # Trim leading/trailing digital silence so pause ratios are not inflated.
    envelope = np.abs(samples)
    if envelope.size:
        peak = float(np.max(envelope))
        if peak > 1e-4:
            active = np.where(envelope > peak * 0.02)[0]
            if active.size > 2:
                pad = int(0.05 * rate)
                samples = samples[max(0, active[0] - pad) : min(len(samples), active[-1] + pad)]

    features = _librosa_features(samples, rate) or _numpy_features(samples, rate)
    score, reasons = score_vocal_stress(features)

    pitch_values = features.get("pitch_values")
    pitch_mean = float(np.mean(pitch_values)) if pitch_values is not None and np.size(pitch_values) else None
    pitch_var = float(features.get("pitch_var") or 0.0)
    successive = (
        np.abs(np.diff(pitch_values))
        if pitch_values is not None and np.size(pitch_values) > 1
        else np.array([])
    )
    jitter = float(np.mean(successive) / pitch_mean) if successive.size and pitch_mean else 0.0

    voiced_ratio = float(features.get("voiced_ratio") or 0.0)
    confidence = 0.2 + 0.45 * _clamp01(voiced_ratio) + 0.2 * _clamp01(duration / 8.0)
    if features.get("backend") == "numpy":
        confidence -= 0.08
    if provenance == "synthetic_demo":
        confidence = min(confidence, 0.35)
    confidence = round(max(0.05, min(0.9, confidence)), 3)

    notes_bits = [f"decoder={decoder}", f"backend={features.get('backend')}"]
    if reasons:
        notes_bits.append("signals: " + ", ".join(reasons))
    if provenance == "synthetic_demo":
        notes_bits.insert(0, "synthetic_demo_signal")

    return AudioRiskResult(
        pitch_mean=round(pitch_mean, 2) if pitch_mean else None,
        pitch_var=round(pitch_var, 2),
        jitter_proxy=round(jitter, 4),
        pause_count=int(features.get("pause_count") or 0),
        pause_ratio=round(float(features.get("pause_ratio") or 0.0), 4),
        speaking_rate=round(float(features.get("speaking_rate") or 0.0), 2),
        energy_rms=round(float(features.get("energy_rms") or 0.0), 5),
        duration_sec=round(float(len(samples) / rate), 2),
        vocal_stress_score=score,
        method="heuristic-demo",
        confidence=confidence,
        notes="; ".join(notes_bits)[:250],
        features={
            "voiced_ratio": round(voiced_ratio, 4),
            "energy_dynamic_range": round(float(features.get("energy_dynamic_range") or 0.0), 5),
            "decoder": decoder,
            "provenance": provenance,
            "sample_rate": rate,
            "extractor": str(features.get("backend") or "unknown"),
            "scoring": "0.22*jitter + 0.20*pitch_var + 0.18*pause_ratio + 0.14*rate + 0.16*loudness_dynamics + 0.10*pitch_level, each bounded to 0-1, x100",
        },
    )


def generate_demo_clip(
    path: Path,
    duration_sec: float = 12.0,
    stressed: bool = True,
) -> Path:
    """Write a synthetic, clearly-labelled demo clip.

    Used by the voice tab when a microphone is unavailable so a judge demo is
    never blocked by permissions. The signal is generated from a simple
    amplitude/F0-modulated harmonic stack - it is a test fixture for the
    feature extractor, not a recording of a person.
    """
    rate = TARGET_SR
    n = int(duration_sec * rate)
    t = np.arange(n) / rate
    rng = np.random.default_rng(20260101)

    f0_base = 168.0 if stressed else 132.0
    # Stressed fixture: fast pitch jitter, wide F0 swings, bursty loudness and
    # long silences. Calm fixture: stable pitch, even loudness, even pacing.
    jitter = 0.055 if stressed else 0.012
    f0 = f0_base * (1.0 + jitter * np.sin(2 * np.pi * 5.5 * t) + 0.02 * np.sin(2 * np.pi * 1.3 * t))
    phase = 2 * np.pi * np.cumsum(f0) / rate

    signal = np.zeros(n, dtype=np.float64)
    for harmonic in range(1, 9):
        signal += (1.0 / harmonic) * np.sin(phase * harmonic)

    if stressed:
        env = 0.55 + 0.45 * np.sin(2 * np.pi * 1.7 * t)
        # Speech-like pauses, placed proportionally so a short clip does not
        # try to write past its own end. A pause that is too short to hold a
        # fade-in and a fade-out is skipped rather than silently truncated,
        # which is what raised a shape-mismatch error on a 4-second clip.
        ramp = int(0.08 * rate)
        for start_frac, length_frac in ((0.28, 0.13), (0.66, 0.16)):
            s = int(start_frac * duration_sec * rate)
            e = min(n, s + int(length_frac * duration_sec * rate))
            if e - s < 3 * ramp:
                continue
            env[s : s + ramp] = np.linspace(1.0, 0.0, ramp)
            env[s + ramp : e - ramp] = 0.02
            env[e - ramp : e] = np.linspace(0.0, 1.0, ramp)
    else:
        env = np.ones(n)

    signal = signal * env * 0.28 + rng.normal(0.0, 0.006, n)
    peak = float(np.max(np.abs(signal))) or 1.0
    pcm = (np.clip(signal / peak, -1.0, 1.0) * 32767).astype("<i2")

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm.tobytes())
    return path


def math_check() -> float:
    """Tiny self-check used by the test suite: a 5 s 440 Hz tone should be
    detected near 440 Hz F0 with near-zero jitter."""
    path = settings.upload_dir / "_selftest_tone.wav"
    rate = TARGET_SR
    n = rate * 3
    t = np.arange(n) / rate
    wave_data = 0.4 * np.sin(2 * np.pi * 440.0 * t)
    pcm = (wave_data * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm.tobytes())
    result = analyze_audio_file(path, provenance="synthetic_demo")
    path.unlink(missing_ok=True)
    return result.pitch_mean or 0.0


__all__ = [
    "AudioRiskResult",
    "analyze_audio_file",
    "generate_demo_clip",
    "score_vocal_stress",
    "REFERENCE_RANGES",
    "math_check",
]
