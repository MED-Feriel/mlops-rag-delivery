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

            # EMBEDDING + UPSERT (batched pour mémoire + progression)
            embedder = Embedder(
                model_name=s.embedding_model, batch_size=s.embedding_batch_size
            )
            store = QdrantVectorStore(
                host=s.qdrant_host, port=s.qdrant_port, collection=s.qdrant_collection
            )
            # Reset collection pour repartir propre
            store.reset()
            log.info("Qdrant collection réinitialisée", collection=s.qdrant_collection)

            # Batch limité par la taille payload Qdrant (32 MB) : ~3800 docs max
            BATCH = 2000
            PROGRESS_EVERY = 10000
            total = len(ids)
            n_upserted = 0
            t_embed_total = 0.0
            t_upsert_total = 0.0
            t0 = time.time()

            log.info(
                "démarrage embedding+upsert batched", total=total, batch_size=BATCH
            )
            for start in range(0, total, BATCH):
                end = min(start + BATCH, total)
                b_texts = texts[start:end]
                b_ids = ids[start:end]
                b_metas = metas[start:end]

                t1 = time.time()
                b_vectors = embedder.embed(b_texts)
                t_embed_total += time.time() - t1

                t2 = time.time()
                n_upserted += store.upsert(b_ids, b_vectors, b_texts, b_metas)
                t_upsert_total += time.time() - t2

                # Log toutes les PROGRESS_EVERY vecteurs (ou à la fin)
                if (end // PROGRESS_EVERY) > (
                    (start) // PROGRESS_EVERY
                ) or end == total:
                    elapsed = time.time() - t0
                    rate = end / max(elapsed, 0.001)
                    eta_s = (total - end) / max(rate, 0.001)
                    log.info(
                        "progress",
                        processed=end,
                        total=total,
                        pct=round(100 * end / total, 1),
                        rate_per_sec=round(rate, 1),
                        eta_s=round(eta_s, 1),
                    )

            mlflow.log_metrics(
                {
                    "embedding_duration_s": t_embed_total,
                    "upsert_duration_s": t_upsert_total,
                    "vectors_count": total,
                    "upserted_vectors": n_upserted,
                    "vector_dimension": 384,
                }
            )
            log.info(
                "embedding+upsert terminés",
                total=total,
                upserted=n_upserted,
                embed_s=round(t_embed_total, 1),
                upsert_s=round(t_upsert_total, 1),
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
