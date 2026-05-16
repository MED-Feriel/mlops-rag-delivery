from pydantic_settings import BaseSettings
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
    qdrant_port: int = 6336  # Port mappé: 6336->6334
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
    mlflow_tracking_uri: str = "http://localhost:5000"
    mlflow_experiment: str = "rag-livraison"
    logstash_host: str = "localhost"
    logstash_port: int = 5044
    ragas_metrics: list = ["faithfulness", "answer_relevancy", "context_precision"]

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
