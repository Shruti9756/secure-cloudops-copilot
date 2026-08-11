from app.db.session import get_session_factory


def test_session_factory_is_cached() -> None:
    assert get_session_factory() is get_session_factory()


def test_session_factory_creates_a_session() -> None:
    session = get_session_factory()()

    try:
        assert session.bind is not None
    finally:
        session.close()
