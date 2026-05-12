from app.services.db_connectors import DatabaseConnector


def test_mysql_url_is_normalized_to_pymysql_driver() -> None:
    normalized = DatabaseConnector._normalize_url(
        "mysql",
        "mysql://user:pass@localhost/testdb",
    )

    assert normalized == "mysql+pymysql://user:pass@localhost/testdb"


def test_postgresql_url_is_normalized_to_psycopg_driver() -> None:
    normalized = DatabaseConnector._normalize_url(
        "postgresql",
        "postgresql://user:pass@localhost/testdb",
    )

    assert normalized == "postgresql+psycopg://user:pass@localhost/testdb"
