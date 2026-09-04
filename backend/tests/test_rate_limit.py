from app.main import limiter


def test_default_rate_limit_returns_429_after_sixty_requests(client):
    limiter._storage.reset()
    try:
        statuses = [client.get("/health").status_code for _ in range(61)]
        assert statuses[:60] == [200] * 60
        assert statuses[60] == 429
    finally:
        limiter._storage.reset()
