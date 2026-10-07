from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf


TARGET_SAMPLE_RATE = 16000


@dataclass
class AudioFeatures:
    sample_rate: int
    duration_seconds: float

    mfcc_mean: list[float]
    mfcc_std: list[float]

    pitch_mean: float
    pitch_std: float

    spectral_centroid_mean: float
    spectral_centroid_std: float

    spectral_bandwidth_mean: float
    spectral_bandwidth_std: float

    spectral_rolloff_mean: float
    spectral_rolloff_std: float

    zero_crossing_rate_mean: float
    zero_crossing_rate_std: float

    rms_mean: float
    rms_std: float

    def to_dict(self) -> dict:
        return {
            "sample_rate": self.sample_rate,
            "duration_seconds": self.duration_seconds,
            "mfcc_mean": self.mfcc_mean,
            "mfcc_std": self.mfcc_std,
            "pitch_mean": self.pitch_mean,
            "pitch_std": self.pitch_std,
            "spectral_centroid_mean": self.spectral_centroid_mean,
            "spectral_centroid_std": self.spectral_centroid_std,
            "spectral_bandwidth_mean": self.spectral_bandwidth_mean,
            "spectral_bandwidth_std": self.spectral_bandwidth_std,
            "spectral_rolloff_mean": self.spectral_rolloff_mean,
            "spectral_rolloff_std": self.spectral_rolloff_std,
            "zero_crossing_rate_mean": self.zero_crossing_rate_mean,
            "zero_crossing_rate_std": self.zero_crossing_rate_std,
            "rms_mean": self.rms_mean,
            "rms_std": self.rms_std,
        }


def _safe_mean(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=np.float64)
    finite_values = values[np.isfinite(values)]

    if finite_values.size == 0:
        return 0.0

    return float(np.mean(finite_values))


def _safe_std(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=np.float64)
    finite_values = values[np.isfinite(values)]

    if finite_values.size == 0:
        return 0.0

    return float(np.std(finite_values))


def _extract_pitch(y: np.ndarray, sr: int) -> np.ndarray:
    """
    Extract fundamental frequency (F0) using librosa.pyin.

    Unvoiced frames can produce NaN values. Those are removed before
    calculating statistical features.
    """
    f0, _, _ = librosa.pyin(
        y,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C7"),
        sr=sr,
    )

    if f0 is None:
        return np.array([], dtype=np.float64)

    return f0[np.isfinite(f0)]


def extract_audio_features(
    audio_path: str | Path,
    target_sr: int = TARGET_SAMPLE_RATE,
) -> AudioFeatures:
    """
    Extract deterministic audio features from a WAV/audio file.

    The audio is:
    1. Loaded with librosa.
    2. Converted to mono.
    3. Resampled to target_sr.
    4. Converted into MFCC, pitch, and spectral features.
    5. Aggregated into mean/std statistics.
    """
    audio_path = Path(audio_path)

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    y, sr = librosa.load(
        audio_path,
        sr=target_sr,
        mono=True,
    )

    if y.size == 0:
        raise ValueError("Audio file contains no samples.")

    if not np.all(np.isfinite(y)):
        raise ValueError("Audio contains invalid numeric samples.")

    duration_seconds = float(len(y) / sr)

    # MFCC: 13 coefficients.
    mfcc = librosa.feature.mfcc(
        y=y,
        sr=sr,
        n_mfcc=13,
        n_fft=1024,
        hop_length=256,
    )

    # Fundamental frequency / pitch.
    pitch = _extract_pitch(y, sr)

    # Spectral features.
    spectral_centroid = librosa.feature.spectral_centroid(
        y=y,
        sr=sr,
        n_fft=1024,
        hop_length=256,
    )

    spectral_bandwidth = librosa.feature.spectral_bandwidth(
        y=y,
        sr=sr,
        n_fft=1024,
        hop_length=256,
    )

    spectral_rolloff = librosa.feature.spectral_rolloff(
        y=y,
        sr=sr,
        n_fft=1024,
        hop_length=256,
        roll_percent=0.85,
    )

    zero_crossing_rate = librosa.feature.zero_crossing_rate(
        y,
        frame_length=1024,
        hop_length=256,
    )

    rms = librosa.feature.rms(
        y=y,
        frame_length=1024,
        hop_length=256,
    )

    return AudioFeatures(
        sample_rate=sr,
        duration_seconds=duration_seconds,
        mfcc_mean=[
            _safe_mean(coefficient)
            for coefficient in mfcc
        ],
        mfcc_std=[
            _safe_std(coefficient)
            for coefficient in mfcc
        ],
        pitch_mean=_safe_mean(pitch),
        pitch_std=_safe_std(pitch),
        spectral_centroid_mean=_safe_mean(spectral_centroid),
        spectral_centroid_std=_safe_std(spectral_centroid),
        spectral_bandwidth_mean=_safe_mean(spectral_bandwidth),
        spectral_bandwidth_std=_safe_std(spectral_bandwidth),
        spectral_rolloff_mean=_safe_mean(spectral_rolloff),
        spectral_rolloff_std=_safe_std(spectral_rolloff),
        zero_crossing_rate_mean=_safe_mean(zero_crossing_rate),
        zero_crossing_rate_std=_safe_std(zero_crossing_rate),
        rms_mean=_safe_mean(rms),
        rms_std=_safe_std(rms),
    )

def feature_vector(features: AudioFeatures) -> np.ndarray:
    """
    Convert AudioFeatures into a fixed-length numeric vector.

    Vector layout:
        13 MFCC means
        13 MFCC standard deviations
        2 pitch features
        2 spectral centroid features
        2 spectral bandwidth features
        2 spectral rolloff features
        2 zero-crossing-rate features
        2 RMS features

    Total = 38 features.
    """
    values = (
        features.mfcc_mean
        + features.mfcc_std
        + [
            features.pitch_mean,
            features.pitch_std,
            features.spectral_centroid_mean,
            features.spectral_centroid_std,
            features.spectral_bandwidth_mean,
            features.spectral_bandwidth_std,
            features.spectral_rolloff_mean,
            features.spectral_rolloff_std,
            features.zero_crossing_rate_mean,
            features.zero_crossing_rate_std,
            features.rms_mean,
            features.rms_std,
        ]
    )

    vector = np.asarray(values, dtype=np.float32)

    if vector.shape != (38,):
        raise ValueError(
            f"Expected 38 features, got {vector.shape}"
        )

    if not np.all(np.isfinite(vector)):
        raise ValueError("Feature vector contains non-finite values.")

    return vector