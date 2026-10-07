from __future__ import annotations

from pathlib import Path

import joblib

from app.ml.classifier import VoiceClassifier


MODEL_DIR = Path("data/models")
MODEL_PATH = MODEL_DIR / "voice_classifier.joblib"


class ModelManager:
    """
    Handles persistence of the trained voice classifier.
    """

    def __init__(
        self,
        model_path: Path = MODEL_PATH,
    ) -> None:
        self.model_path = Path(model_path)

    def save(self, classifier: VoiceClassifier) -> None:
        if not classifier.is_fitted:
            raise ValueError(
                "Cannot save an unfitted classifier"
            )

        self.model_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        joblib.dump(
            classifier,
            self.model_path,
        )

    def load(self) -> VoiceClassifier:
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Model not found: {self.model_path}"
            )

        classifier = joblib.load(self.model_path)

        if not isinstance(classifier, VoiceClassifier):
            raise TypeError(
                "Stored model is not a VoiceClassifier"
            )

        if not classifier.is_fitted:
            raise ValueError(
                "Stored classifier is not fitted"
            )

        return classifier