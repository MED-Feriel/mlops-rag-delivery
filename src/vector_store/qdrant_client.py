"""
Client Qdrant — vector store du projet RAG
Collection : livraison_rag — Vecteurs 384 dim — Distance Cosine
"""

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    UpdateStatus,
    HnswConfigDiff,
)
from typing import Optional
import uuid
import structlog

log = structlog.get_logger()


class QdrantVectorStore:
    def __init__(self, host: str, port: int, collection: str):
        self.client = QdrantClient(host=host, port=port)
        self.collection = collection
        self._ensure_collection()

    # Champs filtrables (payload index keyword) — alignés sur les meta des builders
    PAYLOAD_INDEXES = [
        "source",
        "source_service",
        "topic",
        "zone",
        "criticite",
        "type_event",
        "categorie",
        "vehicule_type",
    ]

    def _ensure_collection(self) -> None:
        existing = [c.name for c in self.client.get_collections().collections]
        if self.collection not in existing:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
                # HNSW tuning pour 100K+ vecteurs : meilleur rappel/latence
                hnsw_config=HnswConfigDiff(m=16, ef_construct=200),
            )
            for field in self.PAYLOAD_INDEXES:
                self.client.create_payload_index(
                    collection_name=self.collection,
                    field_name=field,
                    field_schema="keyword",
                )
            log.info("Collection Qdrant créée", collection=self.collection)
        else:
            # Collection déjà existante : garantir les index récents
            # (source_service, categorie, vehicule_type) sans recréer la
            # collection. create_payload_index est idempotent côté Qdrant.
            for field in ("source_service", "categorie", "vehicule_type"):
                try:
                    self.client.create_payload_index(
                        collection_name=self.collection,
                        field_name=field,
                        field_schema="keyword",
                    )
                except Exception as e:
                    log.debug(
                        "index déjà présent ou non créé", field=field, error=str(e)
                    )

    def upsert(
        self,
        ids: list[str],
        vectors: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> int:
        points = [
            PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_DNS, doc_id)),
                vector=vector,
                payload={"original_id": doc_id, "text": text, **meta},
            )
            for doc_id, vector, text, meta in zip(ids, vectors, documents, metadatas)
        ]
        result = self.client.upsert(
            collection_name=self.collection, points=points, wait=True
        )
        return len(points) if result.status == UpdateStatus.COMPLETED else 0

    def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        filters: Optional[dict] = None,
        score_threshold: float = 0.20,
    ) -> list[dict]:
        qdrant_filter = None
        if filters:
            qdrant_filter = Filter(
                must=[
                    FieldCondition(key=k, match=MatchValue(value=v))
                    for k, v in filters.items()
                ]
            )
        results = self.client.search(
            collection_name=self.collection,
            query_vector=query_vector,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True,
            score_threshold=score_threshold,
        )
        return [
            {
                "text": r.payload.get("text", ""),
                "score": r.score,
                "metadata": {k: v for k, v in r.payload.items() if k != "text"},
            }
            for r in results
        ]

    def reset(self) -> None:
        self.client.delete_collection(self.collection)
        self._ensure_collection()
        log.info("Collection Qdrant réinitialisée")

    def count(self) -> int:
        return self.client.get_collection(self.collection).points_count
