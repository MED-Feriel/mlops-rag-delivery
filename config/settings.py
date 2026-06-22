from pydantic_settings import BaseSettings
from pydantic import field_validator
from functools import lru_cache


class Settings(BaseSettings):
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "livraison"
    postgres_user: str = "postgres"
    postgres_password: str = "secret"
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_group_id: str = "rag-etl-group"
    qdrant_host: str = "localhost"
    qdrant_port: int = 6335
    qdrant_collection: str = "livraison_rag"
    qdrant_vector_size: int = 384
    ollama_host: str = "localhost"
    ollama_port: int = 11434
    ollama_model: str = "gemma3:1b"
    ollama_timeout: int = 120
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    embedding_batch_size: int = 64
    chunk_size: int = 512
    chunk_overlap: int = 64
    retrieval_top_k: int = 8
    retrieval_score_threshold: float = 0.20
    retrieval_hybrid: bool = True  # dense + BM25 + RRF (False = dense pur)
    # ── Cache Redis des embeddings de questions ────────────────
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_ttl_embedding_sec: int = 3600  # 1h
    redis_max_cache_size: int = 10000
    embedding_cache_enabled: bool = True  # False = désactive le cache
    # ── Cache de réponses RAG (B.2) — OFF par défaut : données temps réel,
    # risque de péremption ; n'activer que pour démo/FAQ stables, TTL court.
    answer_cache_enabled: bool = False
    redis_ttl_answer_sec: int = 300  # 5 min
    mlflow_tracking_uri: str = "http://localhost:5000"
    mlflow_experiment: str = "rag-livraison"
    # ── Authentification API (JWT) ──────────────────────────────
    # Désactivée par défaut pour la démo locale / Open WebUI ; activer
    # (AUTH_ENABLED=true) pour un déploiement entreprise.
    auth_enabled: bool = False
    jwt_secret: str = "change-me-en-prod-secret-jwt-aleatoire"
    jwt_algorithm: str = "HS256"
    jwt_expiry_min: int = 60
    auth_username: str = "admin"
    auth_password: str = "admin"
    # Jeton de service (service-to-service) — utilisé par Open WebUI comme
    # OPENAI_API_KEY quand l'auth est activée. Vide = désactivé.
    api_service_token: str = ""
    # ── RBAC + rate limiting + CORS (MLOPS-117) ──────────────────────────
    admin_username: str = "admin"
    admin_password: str = "admin"
    readonly_username: str = "reader"
    readonly_password: str = "reader"
    # Clés API service-à-service : {clé: {"name": ..., "roles": [...]}}.
    # Via env : API_KEYS='{"rag_xxx":{"name":"svc","roles":["service"]}}'.
    api_keys: dict = {}
    # Origines CORS autorisées (liste, ou CSV en env). Éviter "*" en prod.
    cors_origins: list = ["*"]
    # Limites de débit par minute, par rôle (par identité, pas par IP).
    rate_limit_user: int = 60
    rate_limit_admin: int = 300
    rate_limit_service: int = 500
    logstash_host: str = "localhost"
    logstash_port: int = 5044
    ragas_metrics: list = ["faithfulness", "answer_relevancy", "context_precision"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, v):
        """Accepte une liste OU une chaîne CSV (ex: env CORS_ORIGINS=a,b)."""
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def postgres_url(self) -> str:
        return f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"  # noqa: E501

    class Config:
        env_file = ".env.local"  # Utiliser .env.local en priorité pour les tests locaux
        case_sensitive = False
        extra = "ignore"  # Ignorer les champs supplémentaires du .env


@lru_cache()
def get_settings() -> Settings:
    return Settings()
