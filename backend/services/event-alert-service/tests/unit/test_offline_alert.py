from app.rules.offline_alert import is_connection_lost


def test_offline_status_is_connection_lost() -> None:
    assert is_connection_lost("offline") is True


def test_online_status_is_not_connection_lost() -> None:
    assert is_connection_lost("online") is False


def test_warning_status_is_not_connection_lost() -> None:
    assert is_connection_lost("warning") is False
