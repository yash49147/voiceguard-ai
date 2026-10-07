from pathlib import Path
import wave

import numpy as np

from app.services.audio_features import (
    TARGET_SAMPLE_RATE,
    extract_audio_features,
    feature_vector,
)


def create_test_wav(
    path: Path,
    duration_seconds: float = 5.0,
    sample_rate: int = 16000,
) -> None:
    total_samples = int(duration_seconds * sample_rate)

    time = np.arange(total_samples) / sample_rate

    # Deterministic test signal:
    # two simple sine-wave frequencies.
    signal = (
        0.35 * np.sin(2 * np.pi * 220 * time)
        + 0.15 * np.sin(2 * np.pi * 440 * time)
    )

    signal = np.clip(signal, -1.0, 1.0)

    pcm = (signal * 32767).astype(np.int16)

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())


def test_extract_audio_features(tmp_path):
    audio_path = tmp_path / "test.wav"

    create_test_wav(audio_path)

    features = extract_audio_features(audio_path)

    assert features.sample_rate == TARGET_SAMPLE_RATE
    assert 4.9 <= features.duration_seconds <= 5.1

    assert len(features.mfcc_mean) == 13
    assert len(features.mfcc_std) == 13

    assert np.isfinite(features.pitch_mean)
    assert np.isfinite(features.pitch_std)

    assert np.isfinite(features.spectral_centroid_mean)
    assert np.isfinite(features.spectral_centroid_std)

    assert np.isfinite(features.spectral_bandwidth_mean)
    assert np.isfinite(features.spectral_bandwidth_std)

    assert np.isfinite(features.spectral_rolloff_mean)
    assert np.isfinite(features.spectral_rolloff_std)

    assert np.isfinite(features.zero_crossing_rate_mean)
    assert np.isfinite(features.zero_crossing_rate_std)

    assert np.isfinite(features.rms_mean)
    assert np.isfinite(features.rms_std)


def test_feature_vector_has_fixed_size(tmp_path):
    audio_path = tmp_path / "test.wav"

    create_test_wav(audio_path)

    features = extract_audio_features(audio_path)
    vector = feature_vector(features)

    assert vector.shape == (38,)
    assert vector.dtype == np.float32
    assert np.all(np.isfinite(vector))


def test_feature_extraction_is_deterministic(tmp_path):
    audio_path = tmp_path / "test.wav"

    create_test_wav(audio_path)

    features_1 = extract_audio_features(audio_path)
    features_2 = extract_audio_features(audio_path)

    vector_1 = feature_vector(features_1)
    vector_2 = feature_vector(features_2)

    np.testing.assert_allclose(
        vector_1,
        vector_2,
        rtol=1e-5,
        atol=1e-6,
    )


def test_missing_audio_file():
    missing_path = Path("does_not_exist.wav")

    try:
        extract_audio_features(missing_path)
        assert False, "Expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_empty_audio_rejected(tmp_path):
    audio_path = tmp_path / "empty.wav"

    audio_path.write_bytes(b"")

    try:
        extract_audio_features(audio_path)
        assert False, "Expected an audio loading error"
    except Exception:
        pass