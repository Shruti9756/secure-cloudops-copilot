from sqlalchemy.engine import make_url

from app.infrastructure.postgres import build_staging_database_url


def test_build_staging_database_url_preserves_special_password_characters() -> None:
    password = "synthetic@:/%#password"

    url = build_staging_database_url(
        host="example.internal",
        port=5432,
        database="securecloudops",
        username="securecloudops_admin",
        password=password,
    )

    assert url.drivername == "postgresql+psycopg"
    assert url.host == "example.internal"
    assert url.port == 5432
    assert url.database == "securecloudops"
    assert url.username == "securecloudops_admin"
    assert url.password == password
    assert url.query["sslmode"] == "require"
    assert make_url(url.render_as_string(hide_password=False)).password == password
    assert password not in str(url)
