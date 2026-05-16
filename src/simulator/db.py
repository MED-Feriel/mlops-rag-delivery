"""Helper Postgres asyncpg — connexion via variables d'environnement."""

import os
import asyncpg


def pg_dsn() -> str:
    return (
        f"postgres://{os.getenv('POSTGRES_USER', 'postgres')}:"
        f"{os.getenv('POSTGRES_PASSWORD', 'secret')}@"
        f"{os.getenv('POSTGRES_HOST', 'postgres')}:"
        f"{os.getenv('POSTGRES_PORT', '5432')}/"
        f"{os.getenv('POSTGRES_DB', 'livraison')}"
    )


async def connect() -> asyncpg.Connection:
    return await asyncpg.connect(pg_dsn())
