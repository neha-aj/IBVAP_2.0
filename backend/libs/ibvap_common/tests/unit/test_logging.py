from ibvap_common.logging import (
    correlated_headers,
    correlation_id_context,
    get_correlation_id,
)


def test_no_context_bound_gives_empty_correlation_id_and_headers() -> None:
    assert get_correlation_id() == ""
    assert correlated_headers() == {}


def test_correlation_id_context_binds_and_resets() -> None:
    with correlation_id_context("abc-123"):
        assert get_correlation_id() == "abc-123"
        assert correlated_headers() == {"X-Correlation-ID": "abc-123"}
    assert get_correlation_id() == ""
    assert correlated_headers() == {}


def test_empty_correlation_id_falls_back_to_a_minted_one() -> None:
    with correlation_id_context(""):
        cid = get_correlation_id()
        assert cid != ""
        assert correlated_headers() == {"X-Correlation-ID": cid}


def test_nested_contexts_restore_the_outer_id_on_exit() -> None:
    with correlation_id_context("outer"):
        with correlation_id_context("inner"):
            assert get_correlation_id() == "inner"
        assert get_correlation_id() == "outer"
    assert get_correlation_id() == ""
