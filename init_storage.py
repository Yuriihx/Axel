"""Run once at server startup, before Gunicorn binds its public port."""
import os
from postgres_store import PostgresStore


if __name__ == "__main__":
    if os.environ.get("AXEL_STORAGE_MODE") != "postgres":
        raise SystemExit("Configure AXEL_STORAGE_MODE=postgres para a hospedagem gratuita.")
    store = PostgresStore(os.environ.get("DATABASE_URL", ""))
    store.initialize()
    store.check()
    print("Armazenamento PostgreSQL do AXEL pronto.")
