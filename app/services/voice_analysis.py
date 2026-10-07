from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.ml.classifier import ClassificationResult
from app.ml.model_manager import ModelManager
from app.services.audio_features import (
    extract_audio_features,
    feature_vector,
)


@dataclass(frozen=True)
class VoiceAnalysisResult:
    audio_path: str
    ai_probability: float
    human_probability: float
    synthetic_probability: float
    label: str
    feature_count: int

    def to_dict(self) -> dict:
        return {
            "audio_path": self.audio_path,
            "ai_probability": self.ai_probability,
            "human_probability": self.human_probability,
            "synthetic_probability": self.synthetic_probability,
            "label": self.label,
            "feature_count": self.feature_count,
        }


class VoiceAnalysisService:
    """
    Coordinates audio feature extraction and ML inference.

    This service does not train models.
    It only loads an already-trained classifier and performs inference.
    """

    def __init__(
        self,
        model_manager: ModelManager,
    ) -> None:
        self.model_manager = model_manager

    def analyze(
        self,
        audio_path: str | Path,
    ) -> VoiceAnalysisResult:
        audio_path = Path(audio_path)

        if not audio_path.exists():
            raise FileNotFoundError(
                f"Audio file not found: {audio_path}"
            )

        features = extract_audio_features(audio_path)

        vector = feature_vector(features)

        classifier = self.model_manager.load()

        prediction: ClassificationResult = classifier.predict(
            vector
        )

        return VoiceAnalysisResult(
            audio_path=str(audio_path),
            ai_probability=prediction.ai_probability,
            human_probability=prediction.human_probability,
            synthetic_probability=prediction.synthetic_probability,
            label=prediction.label,
            feature_count=len(vector),
        )