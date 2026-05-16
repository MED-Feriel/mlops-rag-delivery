# MLOps RAG Delivery

![CI](https://github.com/MED-Feriel/mlops-rag-delivery/actions/workflows/ci.yml/badge.svg)
![CD](https://github.com/MED-Feriel/mlops-rag-delivery/actions/workflows/cd.yml/badge.svg)
![Model Validation](https://github.com/MED-Feriel/mlops-rag-delivery/actions/workflows/model_validation.yml/badge.svg)

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

## CI/CD Setup

Trois workflows GitHub Actions sont fournis dans `.github/workflows/` :

| Workflow                | Trigger                                  | Rôle                                                 |
|-------------------------|------------------------------------------|------------------------------------------------------|
| `ci.yml`                | push (toutes branches), PR vers `main`   | Lint (flake8 + black), tests unitaires + couverture (≥30%), tests d'intégration |
| `cd.yml`                | push sur `main`                          | Build & push des images Docker `api` / `simulator` vers `ghcr.io` (tags `latest`, `${{ sha }}`, et `vX.Y.Z` si le message de commit contient `release vX.Y.Z`) |
| `model_validation.yml`  | cron nightly 03:00 UTC + dispatch manuel + PR sur code RAG | Exécute `scripts/run_ragas_eval.py` dans le container API ; échoue si `faithfulness < 0.65` ou `answer_relevancy < 0.60` ; commente le résultat sur la PR |

### Secrets GitHub à configurer

Dans **Settings → Secrets and variables → Actions**, ajouter :

| Secret              | Description                                                                 |
|---------------------|-----------------------------------------------------------------------------|
| `QDRANT_HOST`       | Hôte du service Qdrant utilisé pour les tests d'intégration et l'éval RAGAS |
| `QDRANT_PORT`       | Port Qdrant (par défaut `6333`)                                             |
| `POSTGRES_PASSWORD` | Mot de passe Postgres pour les jobs nécessitant une connexion DB            |
| `GHCR_TOKEN`        | Personal Access Token (scopes `write:packages`, `read:packages`) pour pousser sur `ghcr.io` |
| `CODECOV_TOKEN`     | (optionnel) Token Codecov pour l'upload de couverture                       |

### Tag de release

Pour publier une image versionnée, inclure `release vX.Y.Z` dans le message de commit poussé sur `main` :

```bash
git commit -m "release v1.2.0 - nouvelles features RAG"
git push origin main
```

Le workflow `cd.yml` détectera la version et taguera les images `api` et `simulator` avec `v1.2.0` en plus de `latest` et du SHA.
