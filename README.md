Vue d'ensemble
Ce projet implémente un pipeline MLOps complet autour d'un système RAG pour une plateforme de livraison. Il permet de :

Stocker et interroger des données de livraison (commandes, incidents, logs)
Vectoriser les documents métier dans un Vector Store (Qdrant)
Suivre les expériences ML avec MLflow
Exposer une API RAG via FastAPI
Monitorer l'ensemble du système avec Prometheus + Grafana

Structure du projet
mlops-rag-delivery/
│
├── src/                          # Code source principal
│   ├── api/                      # Endpoints FastAPI
│   ├── data/                     # Scripts de génération de données
│   │   └── generate_data.py      # Génération de données synthétiques
│   ├── database/                 # Gestion de la base de données
│   │   └── migrations/
│   │       └── 001_initial_schema.sql
│   ├── embeddings/               # Logique de vectorisation
│   ├── ingestion/                # Pipeline d'ingestion de données
│   ├── monitoring/               # Métriques custom Prometheus
│   ├── pipelines/                # Pipelines ML
│   └── retrieval/                # Logique RAG (recherche + génération)
│
├── tests/                        # Tests automatisés
│   ├── unit/                     # Tests unitaires
│   └── integration/              # Tests d'intégration
│
├── dags/                         # DAGs Apache Airflow
│   ├── dag_ingestion_pipeline.py
│   ├── dag_monitoring_pipeline.py
│   └── dag_retraining_pipeline.py
│
├── config/                       # Configurations des services
│   ├── prometheus/
│   │   └── prometheus.yml
│   ├── grafana/
│   │   └── provisioning/
│   │       └── datasources/
│   ├── logstash/
│   │   ├── pipeline/
│   │   └── config/
│   └── airflow/
│
├── docs/                         # Documentation du projet
│   ├── architecture.md
│   ├── setup.md
│   └── api.md
│
├── logs/                         # Logs locaux (gitignorés)
├── plugins/                      # Plugins Airflow custom
├── docker/                       # Scripts Docker utilitaires
│
├── docker-compose.yml            # Stack complet (13 services)
├── requirements.txt              # Dépendances Python
├── .env                          # Variables d'environnement (non versionné)
├── .gitignore
├── .pre-commit-config.yaml       # Hooks qualité de code
└── README.md
