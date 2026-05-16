# MLflow Integration — RAG Livraison Delivery Platform

## 🎯 Objectif

Intégrer **MLflow 2.10.0** pour:
- ✅ **Tracker** les expériences RAG (paramètres, métriques, artefacts)
- ✅ **Comparer** les runs pour optimiser les performances
- ✅ **Gérer** le modèle registry en production
- ✅ **Tracer** les traces complètes des modèles

---

## 📁 Structure MLflow

```
src/monitoring/
├── mlflow_tracker.py        # Service MLflow principal (✨ NOUVEAU)
├── __init__.py

src/rag/
├── rag_with_mlflow.py       # Wrapper RAG + MLflow (✨ NOUVEAU)

src/evaluation/
├── ragas_evaluator.py       # Amélioré: log complét des artifacts

scripts/
├── mlflow_start.sh          # Script de démarrage (✨ NOUVEAU)
├── demo_mlflow_tracking.py  # Démo complète (✨ NOUVEAU)

docs/
├── mlflow_guide.md          # Guide complet (✨ NOUVEAU)

tests/
├── test_mlflow_integration.py  # Tests (✨ NOUVEAU)
```

---

## 🚀 Démarrage rapide

### 1. **Vérifier que MLflow est installé**
```bash
pip list | grep mlflow  # Doit afficher mlflow 2.10.0
```

### 2. **Démarrer le serveur MLflow**
```bash
cd /home/mlopsadmin/project/mlops-rag-delivery
source .venv/bin/activate
export PYTHONPATH=$(pwd)

# Option 1: Script automatisé
chmod +x scripts/mlflow_start.sh
./scripts/mlflow_start.sh

# Option 2: Commande directe
mlflow ui --host 0.0.0.0 --port 5000
```

### 3. **Accéder au dashboard**
```
http://localhost:5000
```

---

## 💡 Utilisation simple

### Exemple basique:
```python
from src.monitoring.mlflow_tracker import MLflowTracker, MLflowRun

# Créer un tracker
tracker = MLflowTracker(
    tracking_uri="http://localhost:5000",
    experiment_name="my_experiments"
)

# Utiliser le context manager
with MLflowRun(tracker, "run_1", tags={"version": "1.0"}):
    # Logger les paramètres
    tracker.log_params({"chunk_size": 512})

    # Logger les métriques
    tracker.log_metrics({"faithfulness": 0.85})

    # Logger des fichiers
    tracker.log_artifact("/path/to/file.json")
```

### Évaluation RAG:
```python
from src.evaluation.ragas_evaluator import RAGASEvaluator

evaluator = RAGASEvaluator(rag_pipeline)

questions = [
    {"question": "...", "ground_truth": "..."},
]

# Évalue et log automatiquement dans MLflow
scores = await evaluator.evaluate_and_log(
    questions,
    run_name="eval_batch_1",
    save_artifacts=True  # Sauve les détails
)
```

### Comparaison:
```python
# Comparer les meilleures runs
comparison = tracker.compare_experiments("faithfulness", top_n=10)
print(comparison)

# Trouver la meilleure run
best = tracker.get_best_run("answer_relevancy")
print(f"Meilleure run: {best['run_id']}")
```

---

## 📊 Dashboard MLflow Features

### 1. **Experiments**
- Voir toutes les expériences
- Filtrer par tags
- Trier par métrique
- Export en CSV

### 2. **Runs**
- Détails complets de chaque run
- Graphiques des métriques (avec steps)
- Télécharger les artifacts
- Comparer jusqu'à N runs

### 3. **Model Registry**
- Enregistrer les modèles
- Gérer les versions
- Transitions de stage (Staging → Production)
- Archiver les modèles obsolètes

---

## 📈 Métriques RAG à tracker

```python
metrics = {
    # Évaluation RAGAS
    "faithfulness": 0.85,           # Véracité
    "answer_relevancy": 0.78,       # Pertinence
    "context_precision": 0.82,      # Précision contexte
    "context_recall": 0.75,         # Rappel contexte

    # Performance
    "retrieval_time_ms": 150,
    "inference_time_ms": 800,

    # Données
    "num_documents_retrieved": 5,
    "avg_context_length": 2000,
}
```

---

## 🎯 Cas d'usage

### 1. **Baseline vs Optimized**
```python
# Run 1: Baseline
with MLflowRun(tracker, "baseline", tags={"type": "baseline"}):
    tracker.log_metrics({"faithfulness": 0.80})

# Run 2: Optimized
with MLflowRun(tracker, "optimized", tags={"type": "optimized"}):
    tracker.log_metrics({"faithfulness": 0.88})

# Comparer
comparison = tracker.compare_experiments("faithfulness")
```

### 2. **A/B Testing**
```python
# Version A: Embedding 1
with MLflowRun(tracker, "embedding_v1"):
    tracker.log_params({"embedding": "all-MiniLM-L6-v2"})
    tracker.log_metrics({"faithfulness": 0.82})

# Version B: Embedding 2
with MLflowRun(tracker, "embedding_v2"):
    tracker.log_params({"embedding": "paraphrase-multilingual"})
    tracker.log_metrics({"faithfulness": 0.89})
```

### 3. **Evaluation Batch**
```python
questions = [
    {"question": "Q1", "ground_truth": "A1"},
    {"question": "Q2", "ground_truth": "A2"},
]

await evaluator.evaluate_and_log(
    questions,
    run_name=f"eval_{datetime.now()}"
)
```

---

## 🔄 Intégration avec le pipeline ETL

Le tracker MLflow se met à jour automatiquement lors:
1. **Évaluation RAGAS** → Scores + artifacts
2. **Requêtes RAG** → Performance metrics
3. **Batch processing** → Résultats globaux

---

## 📚 Documentation complète

Voir [docs/mlflow_guide.md](docs/mlflow_guide.md) pour:
- Guide complet d'utilisation
- Tous les cas d'usage
- Dépannage
- Intégration CI/CD
- Exemples avancés

---

## 🧪 Tester l'intégration

```bash
# Tests unitaires
pytest tests/test_mlflow_integration.py -v

# Demo: Tracking simple
python scripts/demo_mlflow_tracking.py --mode=tracking

# Demo: Comparaison
python scripts/demo_mlflow_tracking.py --mode=comparison

# Demo: Model Registry
python scripts/demo_mlflow_tracking.py --mode=registry

# Demo: Tous
python scripts/demo_mlflow_tracking.py --mode=all
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│   Application RAG                               │
├─────────────────────────────────────────────────┤
│  ├─ rag_pipeline.query()                        │
│  ├─ evaluator.evaluate_and_log()                │
│  └─ rag_with_mlflow.query_and_log()             │
├─────────────────────────────────────────────────┤
│         MLflowTracker (src/monitoring/)         │
├─────────────────────────────────────────────────┤
│         MLflow Server (port 5000)               │
├─────────────────────────────────────────────────┤
│   ├─ SQLite DB (mlflow.db)                      │
│   ├─ Artifacts (./mlflow_artifacts/)            │
│   └─ Dashboard UI (http://localhost:5000)       │
└─────────────────────────────────────────────────┘
```

---

## 🔧 Configuration

Via `config/settings.py`:
```python
mlflow_tracking_uri: str = "http://localhost:5000"
mlflow_experiment: str = "rag-livraison"
```

Via `.env`:
```bash
MLFLOW_TRACKING_URI=http://localhost:5000
```

---

## 🌐 Production Setup

Pour la production, utiliser Docker Compose avec PostgreSQL:
```bash
# Voir config/mlflow_docker_config.py
docker-compose -f docker-compose.mlflow.yml up -d
```

---

## 📞 Support

**Dashboard MLflow:**
- http://localhost:5000

**Fichiers de log:**
- `./mlflow.db` (SQLite)
- `./mlflow_artifacts/` (Artifacts)

**Problèmes courants:**
- Port 5000 occupé? → `lsof -i :5000`
- MLflow pas installé? → `pip install mlflow==2.10.0`
- Pas de données? → Lancer `demo_mlflow_tracking.py`

---

**Version:** MLflow 2.10.0 | **Dernière mise à jour:** May 2026
