"""AI layer. AI consumes processed/validated data and never owns acquisition."""

from .service import AIService
from .training import AITrainingService, LearningMemory, TrainingConfig

__all__ = ["AIService", "AITrainingService", "LearningMemory", "TrainingConfig"]
