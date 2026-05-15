# Supabase-py to Psycopg2 Transition Log

- Restored direct `psycopg2` connection in `pipeline/db.py` (`get_conn`).
- Replaced Supabase PostgREST builder methods with raw SQL queries from `queries.md` in `pipeline/db.py`.
- Replaced Supabase RPC calls with raw SQL (e.g. `anchor_embedding <=> %s::vector`, `array_agg(distinct kw)`) in `pipeline/db.py`.
- Replaced `Depends(get_supabase_client)` with `Depends(get_db_connection)` in `api/dependencies.py` to yield per-request `psycopg2` connection.
- Replaced Supabase REST API calls in `api/routers/articles.py` with `psycopg2.extras.RealDictCursor` SQL execution while preserving identical JSON response structures.
- Replaced Supabase REST API call in `api/routers/health.py` with `SELECT 1` query.
- Reverted to explicit `conn.commit()` transaction management in `api/routers/pipeline.py` and `main.py`.
- Reverted `.env` usage to standard Postgres variables and removed `supabase` from `requirements.txt`.
