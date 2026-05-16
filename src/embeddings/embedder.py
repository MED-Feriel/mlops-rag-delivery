"""Embeddings via sentence-transformers paraphrase-multilingual-MiniLM-L12-v2 (384 dim)."""

from sentence_transformers import SentenceTransformer
import structlog

log = structlog.get_logger()


class Embedder:
    def __init__(
        self,
        model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
        batch_size: int = 64,
    ):
        self.model = SentenceTransformer(model_name)
        self.batch_size = batch_size

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]
