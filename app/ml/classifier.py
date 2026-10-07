from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class ClassificationResult:
    human_probability: float
    synthetic_probability: float
    ai_probability: float
    label: str


class VoiceClassifier:
    """
    Binary voice classifier.

    Class convention:
        0 = human
        1 = synthetic / AI

    The classifier is intentionally separated from audio feature
    extraction so the model can later be replaced with a stronger
    deepfake-detection architecture without changing the API layer.
    """

    def __init__(self) -> None:
        self.pipeline = Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(
                        max_iter=1000,
                        random_state=42,
                    ),
                ),
            ]
        )

        self.is_fitted = False

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
    ) -> None:
        X = np.asarray(X, dtype=np.float32)
        y = np.asarray(y, dtype=np.int32)

        if X.ndim != 2:
            raise ValueError(
                f"X must be 2-dimensional, got shape {X.shape}"
            )

        if X.shape[1] != 38:
            raise ValueError(
                f"Expected 38 features, got {X.shape[1]}"
            )

        if y.ndim != 1:
            raise ValueError(
                f"y must be 1-dimensional, got shape {y.shape}"
            )

        if len(X) != len(y):
            raise ValueError(
                "X and y must contain the same number of samples"
            )

        if not np.all(np.isfinite(X)):
            raise ValueError(
                "Training features contain non-finite values"
            )

        unique_labels = np.unique(y)

        if not np.array_equal(unique_labels, np.array([0, 1])):
            raise ValueError(
                "Training labels must contain both classes 0 and 1"
            )

        self.pipeline.fit(X, y)
        self.is_fitted = True

    def predict(
        self,
        feature_vector: np.ndarray,
    ) -> ClassificationResult:
        if not self.is_fitted:
            raise RuntimeError(
                "Classifier must be fitted before prediction"
            )

        vector = np.asarray(
            feature_vector,
            dtype=np.float32,
        )

        if vector.shape != (38,):
            raise ValueError(
                f"Expected feature vector shape (38,), got {vector.shape}"
            )

        if not np.all(np.isfinite(vector)):
            raise ValueError(
                "Feature vector contains non-finite values"
            )

        probabilities = self.pipeline.predict_proba(
            vector.reshape(1, -1)
        )[0]

        human_probability = float(probabilities[0])
        synthetic_probability = float(probabilities[1])

        ai_probability = synthetic_probability * 100.0

        label = (
            "synthetic"
            if synthetic_probability >= 0.5
            else "human"
        )

        return ClassificationResult(
            human_probability=human_probability,
            synthetic_probability=synthetic_probability,
            ai_probability=ai_probability,
            label=label,
        )