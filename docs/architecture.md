# Architecture — mlops-rag-delivery (v2.0.0)

## Stack
- Vector Store : **Qdrant** (collection `livraison_rag`, 384 dim, distance Cosine)
- LLM : **Gemma3:1b** via Ollama
- Embedding : `paraphrase-multilingual-MiniLM-L12-v2` (sentence-transformers 2.5.1)
- RAG : LangChain 0.1.9
- Évaluation : **RAGAS 0.1.7** (faithfulness, answer_relevancy, context_precision, context_recall)
- Streaming : Kafka 7.5.0
- Orchestration : Airflow 2.9.0
- Observabilité : ELK 8.12.0 + Prometheus + Grafana
- API : FastAPI 0.110.0
- MLOps : MLflow 2.10.0

## Conteneurs
- `simulator` (port 8090) — léger : faker / asyncpg / kafka / httpx
- `api` (port 8080) — lourd : langchain / sentence-transformers / ragas
- ETL — moyen : kafka / qdrant-client / sentence-transformers

## Flux RAG
1. ETL extrait depuis PostgreSQL + Kafka
2. clean → normalize → document_builder → chunk → embedder → Qdrant
3. /query : embed question → retrieve top_k → build context → Gemma3:1b
4. /query/stream : pareil mais SSE
5. Évaluation RAGAS quotidienne via DAG Airflow → MLflow
