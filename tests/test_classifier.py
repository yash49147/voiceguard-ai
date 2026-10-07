import numpy as np
import pytest

from app.ml.classifier import VoiceClassifier
from app.ml.model_manager import ModelManager


def create_training_data():
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

    X = np.vstack([human, synthetic])

    y = np.array(
        [0] * 20 + [1] * 20,
        dtype=np.int32,
    )

    return X, y


def test_classifier_requires_training():
    classifier = VoiceClassifier()

    vector = np.zeros(38, dtype=np.float32)

    with pytest.raises(RuntimeError):
        classifier.predict(vector)


def test_classifier_training_and_prediction():
    X, y = create_training_data()

    classifier = VoiceClassifier()
    classifier.fit(X, y)

    assert classifier.is_fitted is True

    result = classifier.predict(
        X[0].astype(np.float32)
    )

    assert 0.0 <= result.human_probability <= 1.0
    assert 0.0 <= result.synthetic_probability <= 1.0
    assert 0.0 <= result.ai_probability <= 100.0

    assert (
        result.human_probability
        + result.synthetic_probability
    ) == pytest.approx(1.0)

    assert result.label in {
        "human",
        "synthetic",
    }


def test_classifier_rejects_wrong_feature_count():
    X, y = create_training_data()

    classifier = VoiceClassifier()
    classifier.fit(X, y)

    wrong_vector = np.zeros(
        37,
        dtype=np.float32,
    )

    with pytest.raises(ValueError):
        classifier.predict(wrong_vector)


def test_classifier_rejects_invalid_training_shape():
    classifier = VoiceClassifier()

    X = np.zeros(
        (10, 37),
        dtype=np.float32,
    )

    y = np.array(
        [0] * 5 + [1] * 5,
        dtype=np.int32,
    )

    with pytest.raises(ValueError):
        classifier.fit(X, y)


def test_classifier_rejects_single_class_training():
    classifier = VoiceClassifier()

    X = np.zeros(
        (10, 38),
        dtype=np.float32,
    )

    y = np.zeros(
        10,
        dtype=np.int32,
    )

    with pytest.raises(ValueError):
        classifier.fit(X, y)


def test_model_save_and_load(tmp_path):
    X, y = create_training_data()

    classifier = VoiceClassifier()
    classifier.fit(X, y)

    model_path = tmp_path / "voice_classifier.joblib"

    manager = ModelManager(model_path)

    manager.save(classifier)

    assert model_path.exists()

    loaded_classifier = manager.load()

    assert loaded_classifier.is_fitted is True

    original_result = classifier.predict(
        X[0].astype(np.float32)
    )

    loaded_result = loaded_classifier.predict(
        X[0].astype(np.float32)
    )

    assert loaded_result.human_probability == pytest.approx(
        original_result.human_probability
    )

    assert loaded_result.synthetic_probability == pytest.approx(
        original_result.synthetic_probability
    )


def test_model_manager_rejects_missing_model(tmp_path):
    model_path = tmp_path / "missing.joblib"

    manager = ModelManager(model_path)

    with pytest.raises(FileNotFoundError):
        manager.load()