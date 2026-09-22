"""Unit tests for security.auth (T-29) – no HTTP, pure logic."""

from security.auth import (
    RateLimiter,
    has_scope,
    normalise_path,
    parse_api_keys,
    scope_for_path,
)


def test_parse_api_keys_scoped_and_bare():
    keys = parse_api_keys("k1:predict:read,scan:read; k2:admin; bare")
    assert keys["k1"] == ["predict:read", "scan:read"]
    assert keys["k2"] == ["admin"]
    assert keys["bare"] == ["predict:read"]  # bare key defaults to predict:read
    assert parse_api_keys("") == {}


def test_parse_api_keys_ignores_unknown_scopes():
    keys = parse_api_keys("k:predict:read,bogus:scope")
    assert keys["k"] == ["predict:read"]


def test_admin_implies_all_scopes():
    assert has_scope(["admin"], "alerts:write")
    assert not has_scope(["predict:read"], "scan:read")
    assert has_scope(["scan:read"], "scan:read")


def test_scope_rules_and_v1_normalisation():
    assert normalise_path("/v1/predict") == "/predict"
    assert normalise_path("/v1/v1/x") == "/v1/x"
    assert scope_for_path("/v1/predict") == "predict:read"
    assert scope_for_path("/hotspots") == "scan:read"
    assert scope_for_path("/train/status") == "admin"
    assert scope_for_path("/email/ward-alert") == "alerts:write"
    assert scope_for_path("/health") is None
    assert scope_for_path("/v1/health") is None
    assert scope_for_path("/unmatched-thing") is None


def test_rate_limiter_blocks_after_limit():
    rl = RateLimiter()
    for _ in range(3):
        assert rl.allow("id1", "predict:read", 3)[0]
    allowed, retry = rl.allow("id1", "predict:read", 3)
    assert not allowed
    assert retry >= 1
    # separate identity unaffected
    assert rl.allow("id2", "predict:read", 3)[0]
    # separate bucket unaffected
    assert rl.allow("id1", "scan:read", 3)[0]
