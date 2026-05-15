from pipeline.db import get_client


def get_supabase_client():
    """FastAPI dependency — provides a Supabase client to route handlers."""
    return get_client()
