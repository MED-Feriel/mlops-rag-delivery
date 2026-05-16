"""ETL runner — Postgres -> documents -> embeddings -> Qdrant.

À exécuter dans le conteneur `api` (qui possède sentence-transformers + qdrant-client).
Avec tracking MLflow intégré pour monitoring et débogage.
"""

from __future__ import annotations

import asyncio
import structlog
import time
import mlflow
from datetime import datetime

from config.settings import get_settings
from src.ingestion.extract import extract_all
from src.ingestion.clean import clean
from src.ingestion.chunk import chunk_documents
from src.ingestion.document_builder import build_documents
from src.embeddings.embedder import Embedder
from src.vector_store.qdrant_client import QdrantVectorStore

log = structlog.get_logger()


async def run() -> None:
    s = get_settings()

    # Configuration MLflow (via settings → env MLFLOW_TRACKING_URI ou défaut)
    mlflow.set_tracking_uri(s.mlflow_tracking_uri)

    with mlflow.start_run(run_name=f"etl_pipeline_{datetime.now().isoformat()}"):
        try:
            log.info("ETL démarré", postgres=s.postgres_host, qdrant=s.qdrant_host)
            mlflow.log_param("postgres_host", s.postgres_host)
            mlflow.log_param("qdrant_host", s.qdrant_host)
            mlflow.log_param("embedding_model", s.embedding_model)

            # EXTRACT
            start_extract = time.time()
            extract_result = await extract_all()
            extract_time = time.time() - start_extract
            counts = {k: len(v) for k, v in extract_result.items()}
            log.info("extract terminé", **counts, duration_s=extract_time)
            mlflow.log_metrics(
                {
                    "extract_duration_s": extract_time,
                    **{f"extracted_{k}": v for k, v in counts.items()},
                }
            )

            # CLEAN
            start_clean = time.time()
            extract_result = clean(extract_result)
            mlflow.log_metric("clean_duration_s", time.time() - start_clean)

            # BUILD DOCUMENTS
            start_build = time.time()
            ids, texts, metas = build_documents(extract_result)
            # CHUNK long texts (synthèses agrégées surtout)
            ids, texts, metas = chunk_documents(
                ids,
                texts,
                metas,
                chunk_size=s.chunk_size,
                chunk_overlap=s.chunk_overlap,
            )
            build_time = time.time() - start_build
            log.info("documents construits", n=len(ids), duration_s=build_time)
            mlflow.log_metrics(
                {"documents_count": len(ids), "build_duration_s": build_time}
            )

            if not ids:
                log.warning("aucun document à indexer — sortie")
                mlflow.log_param("status", "no_documents")
                return

            # EMBEDDING
            embedder = Embedder(
                model_name=s.embedding_model, batch_size=s.embedding_batch_size
            )
            store = QdrantVectorStore(
                host=s.qdrant_host, port=s.qdrant_port, collection=s.qdrant_collection
            )

            start_embedding = time.time()
            log.info("calcul embeddings", n=len(texts))
            vectors = embedder.embed(texts)
            embedding_time = time.time() - start_embedding
            log.info("embeddings terminés", duration_s=embedding_time)
            mlflow.log_metrics(
                {
                    "embedding_duration_s": embedding_time,
                    "vectors_count": len(vectors),
                    "vector_dimension": len(vectors[0]) if vectors else 0,
                }
            )

            # UPSERT QDRANT
            start_upsert = time.time()
            n = store.upsert(ids, vectors, texts, metas)
            upsert_time = time.time() - start_upsert
            log.info(
                "upsert Qdrant terminé",
                upserted=n,
                collection=s.qdrant_collection,
                duration_s=upsert_time,
            )
            mlflow.log_metrics(
                {"upserted_vectors": n, "upsert_duration_s": upsert_time}
            )

            # LOG STATUS
            mlflow.log_param("status", "success")
            mlflow.set_tags({"component": "etl_pipeline", "sprint": "sprint6"})
            log.info("ETL complété avec succès")

        except Exception as e:
            log.error("Erreur ETL", error=str(e))
            mlflow.log_param("status", "failed")
            mlflow.log_param("error", str(e))
            raise


if __name__ == "__main__":
    asyncio.run(run())
