# MLOps RAG Delivery

Système RAG (Retrieval-Augmented Generation) pour la supervision
d'une plateforme de livraison de repas. Projet de Fin d'Études —
ENSTICP 2025.

## Stack technique

| Composant         | Technologie              |
|-------------------|--------------------------|
| LLM               | Gemma3:1b (Ollama)       |
| Vector Store      | Qdrant (384 dim, Cosine) |
| Embedding         | all-MiniLM-L6-v2         |
| Orchestration ETL | Apache Airflow           |
| API               | FastAPI                  |
| Évaluation RAG    | RAGAS                    |
| Monitoring        | Prometheus + Grafana     |
| Logs              | ELK Stack                |
| MLOps             | MLflow                   |

## Démarrage rapide

```bash
git clone <repo>
cd mlops-rag-delivery
cp .env.example .env
make up        # Démarre tous les services
make generate  # Génère les données PostgreSQL
make simulate  # Lance le simulateur Kafka
make query     # Teste le RAG
```

## Interfaces disponibles

| Service   | URL                              | Credentials |
|-----------|----------------------------------|-------------|
| API RAG   | http://localhost:8080/docs       | —           |
| Qdrant UI | http://localhost:6333/dashboard  | —           |
| Airflow   | http://localhost:8081            | admin/admin |
| MLflow    | http://localhost:5000            | —           |
| Grafana   | http://localhost:3000            | admin/admin |
| Kibana    | http://localhost:5601            | —           |

## Résultats RAGAS

| Métrique          | Score                       |
|-------------------|-----------------------------|
| Faithfulness      | _à compléter après Prompt B_ |
| Answer Relevancy  | _à compléter_               |
| Context Precision | _à compléter_               |
| Context Recall    | _à compléter_               |

## Tests

```bash
python3 -m pytest tests/unit/ -v   # 26 tests unitaires
```

## Structure du projet

```
src/
├── api/            # FastAPI endpoints, OpenAI-compatible routes
├── embeddings/     # all-MiniLM-L6-v2 embedder
├── evaluation/     # RAGAS scoring pipeline
├── ingestion/      # ETL : extract / clean / chunk / normalize
├── llm/            # Gemma3:1b client (Ollama)
├── monitoring/     # MLflow tracker, model versioning
├── rag/            # Pipeline RAG complet
├── retrieval/      # Service de retrieval Qdrant
├── simulator/      # Producteur Kafka (events livraison)
└── vector_store/   # Wrapper Qdrant
```
