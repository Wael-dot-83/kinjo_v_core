import json
from unittest.mock import MagicMock

from slowapi.errors import RateLimitExceeded

from rate_limiter import rate_limit_exceeded_handler


def test_rate_limit_exceeded_handler_returns_429():
    # Create a mock Limit object with error_message
    mock_limit = MagicMock()
    mock_limit.error_message = "Rate limit exceeded"
    
    exc = RateLimitExceeded(mock_limit)
    exc.retry_after = 42

    response = rate_limit_exceeded_handler(None, exc)

    assert response.status_code == 429
    payload = json.loads(response.body)
    assert payload["error"]["code"] == "RATE_LIMITED"
    assert payload["error"]["details"]["retry_after"] == 42
    assert response.headers["Retry-After"] == "42"
