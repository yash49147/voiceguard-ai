from pathlib import Path

import numpy as np
import pytest

from app.ml.classifier import VoiceClassifier
from app.ml.model_manager import ModelManager
from app.services.voice_analysis import VoiceAnalysisService
from tests.test_audio_features import create_test_wav


def create_test_classifier() -> VoiceClassifier:
    rng = np.random.default_rng(42)

    human = rng.normal(
        loc=0.0,
        scale=1.0,
        size=(20, 38),
    )

    synthetic = rng.normal(
        loc=2.0,
        scale=1.0,
        size=(20, 38),
    )

    X = np.vstack([
        human,
        synthetic,
    ])

    y = np.array(
        [0] * 20 + [1] * 20,
        dtype=np.int32,
    )

    classifier = VoiceClassifier()
    classifier.fit(X, y)

    return classifier


def test_voice_analysis_pipeline(tmp_path):
    audio_path = tmp_path / "test.wav"
    model_path = tmp_path / "voice_classifier.joblib"

    create_test_wav(audio_path)

    classifier = create_test_classifier()

    manager = ModelManager(model_path)
    manager.save(classifier)

    service = VoiceAnalysisService(manager)

    result = service.analyze(audio_path)

    assert result.feature_count == 38

    assert 0.0 <= result.ai_probability <= 100.0
    assert 0.0 <= result.human_probability <= 1.0
    assert 0.0 <= result.synthetic_probability <= 1.0

    assert (
        result.human_probability
        + result.synthetic_probability
    ) == pytest.approx(1.0)

    assert result.label in {
        "human",
        "synthetic",
    }


def test_analysis_rejects_missing_audio(tmp_path):
    model_path = tmp_path / "voice_classifier.joblib"

    classifier = create_test_classifier()

    manager = ModelManager(model_path)
    manager.save(classifier)

    service = VoiceAnalysisService(manager)

    missing_audio = tmp_path / "missing.wav"

    try:
        service.analyze(missing_audio)
        assert False, "Expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_analysis_uses_persisted_model(tmp_path):
    audio_path = tmp_path / "test.wav"
    model_path = tmp_path / "voice_classifier.joblib"

    create_test_wav(audio_path)

    classifier = create_test_classifier()

    manager = ModelManager(model_path)
    manager.save(classifier)

    # Create a new manager to prove that inference uses
    # the persisted model rather than the original object.
    loaded_manager = ModelManager(model_path)

    service = VoiceAnalysisService(
        loaded_manager
    )

    result = service.analyze(audio_path)

    assert result.feature_count == 38
    assert result.label in {
        "human",
        "synthetic",
    }