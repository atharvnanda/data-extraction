from pipeline.db import get_conn


def get_db_connection():
    """FastAPI dependency — yields a Postgres connection and closes it after the request."""
    conn = get_conn()
    try:
        yield conn
    finally:
        conn.close()
