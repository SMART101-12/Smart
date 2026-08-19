from smart_v2.ai.service import AIService


class DummyModel:
    def predict(self, features):
        return [1 for _ in features]


def test_ai_service_predict():
    features = [
        {"close": 100, "volume": 1000},
        {"close": 105, "volume": 1200},
    ]

    result = AIService().predict(features, DummyModel())

    assert result == [1, 1]
