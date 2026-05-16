# MLflow Integration Guide — mlops-rag-delivery

## 📊 Vue d'ensemble

MLflow intègre le tracking complet des expériences RAG pour:
- ✅ Logger les paramètres, métriques et artefacts
- ✅ Comparer les runs et expériences
- ✅ Gérer le Model Registry
- ✅ Tracer les traces complètes des modèles

**Services:**
- MLflow UI: http://localhost:5000
- Tracking URI: `http://localhost:5000`

---

## 🚀 Utilisation rapide

### 1. Démarrer MLflow
```bash
cd /home/mlopsadmin/project/mlops-rag-delivery
source .venv/bin/activate
export PYTHONPATH=$(pwd)

# Démarrer le serveur MLflow
mlflow ui --host 0.0.0.0 --port 5000 --backend-store-uri sqlite:///mlflow.db
```

### 2. Tracker une expérience simple
```python
from src.monitoring.mlflow_tracker import MLflowTracker

tracker = MLflowTracker(
    tracking_uri="http://localhost:5000",
    experiment_name="my_rag_experiments"
)

# Démarrer une run
run_id = tracker.start_run("baseline_v1", tags={"model": "gemma3"})

# Logger les paramètres
tracker.log_params({
    "chunk_size": 512,
    "top_k": 5,
    "temperature": 0.7
})

# Logger les métriques
tracker.log_metrics({
    "faithfulness": 0.85,
    "answer_relevancy": 0.78
})

# Terminer la run
tracker.end_run()
```

### 3. Context Manager (recommandé)
```python
from src.monitoring.mlflow_tracker import MLflowTracker, MLflowRun

tracker = MLflowTracker("http://localhost:5000", "my_experiments")

with MLflowRun(tracker, "my_run", tags={"version": "1.0"}):
    tracker.log_params({"param1": 123})
    tracker.log_metrics({"metric1": 0.95})
    # Automatiquement fermée à la fin du bloc
```

---

## 📈 Cas d'usage courants

### A. Logger une évaluation RAGAS

```python
from src.evaluation.ragas_evaluator import RAGASEvaluator

evaluator = RAGASEvaluator(rag_pipeline)

questions = [
    {"question": "...", "ground_truth": "..."},
]

scores = await evaluator.evaluate_and_log(
    questions,
    run_name="eval_batch_1",
    save_artifacts=True  # Sauvegarde les résultats détaillés
)
```

**Résultat:**
- Métriques RAGAS loggées
- Dataset d'évaluation sauvegardé
- Scores exportés en CSV et JSON

### B. Logger une requête RAG complète

```python
from src.rag.rag_with_mlflow import RAGWithMLflow

rag_mlflow = RAGWithMLflow(rag_pipeline, tracker)

result = await rag_mlflow.query_and_log(
    "Combien de commandes retardées ?",
    run_name="query_test_001",
    tags={"user": "admin", "source": "api"}
)
```

**Résultat:**
- Longueur de la requête
- Nombre de documents retrouvés
- Scores de pertinence

### C. Comparer des expériences

```python
# Afficher les top 10 runs par métrique
comparison_df = tracker.compare_experiments(
    metric_name="faithfulness",
    top_n=10
)
print(comparison_df)

# Afficher un résumé texte
print(rag_mlflow.compare_experiments_summary("faithfulness"))
```

**Output:**
```
📊 COMPARAISON EXPÉRIENCES — Métrique: faithfulness
================================================================================
#1 | Run: a1b2c3d4... | Score: 0.9234 | LLM: gemma3 | Embedding: paraphrase
#2 | Run: e5f6g7h8... | Score: 0.8956 | LLM: gemma3 | Embedding: all-MiniLM
...
```

### D. Trouver la meilleure run

```python
best = tracker.get_best_run("answer_relevancy")

if best:
    print(f"Run ID: {best['run_id']}")
    print(f"Métriques: {best['metrics']}")
    print(f"Paramètres: {best['params']}")
```

### E. Logger des modèles

```python
tracker.log_model(
    model_obj=rag_pipeline,
    artifact_path="rag_model_v1",
    model_flavor="custom"
)

# Enregistrer dans le Model Registry
tracker.register_model(
    run_id=run_id,
    artifact_path="rag_model_v1",
    model_name="rag_livraison",
    stage="Staging"  # ou "Production"
)
```

### F. Logger des artefacts (fichiers)

```python
# Logger un fichier unique
tracker.log_artifact("/path/to/model.pkl", artifact_path="models")

# Logger un dossier complet
tracker.log_artifact("/path/to/results_folder", artifact_path="results")
```

---

## 🎯 Pipeline d'évaluation complète

```python
from src.monitoring.mlflow_tracker import MLflowTracker
from src.evaluation.ragas_evaluator import RAGASEvaluator
from src.rag.rag_with_mlflow import RAGWithMLflow

# Setup
settings = Settings()
tracker = MLflowTracker(settings.mlflow_tracking_uri)
evaluator = RAGASEvaluator(rag_pipeline)
rag_mlflow = RAGWithMLflow(rag_pipeline, tracker)

# Batch d'évaluation
questions = [...]

with MLflowRun(tracker, "full_evaluation", tags={"batch": "prod"}):
    # Logger config
    tracker.log_params({
        "batch_size": len(questions),
        "model": "gemma3:1b",
        "embedding": "paraphrase-multilingual-MiniLM-L12-v2"
    })

    # Évaluer
    scores = await evaluator.evaluate_and_log(questions)

    # Logger résultats finaux
    tracker.log_metrics(scores)

    # Optionnel: enregistrer le modèle
    if scores["faithfulness"] > 0.85:
        tracker.register_model(
            run_id,
            "rag_model",
            "rag_production",
            stage="Staging"
        )
```

---

## 🔍 Dashboard MLflow

**Accès:**
http://localhost:5000

### Sections clés:

1. **Experiments**: Vue globale des expériences
   - Filtre par tags
   - Tri par métrique
   - Export CSV

2. **Runs**: Détails de chaque run
   - Paramètres et métriques
   - Graphiques d'évolution (steps)
   - Artefacts téléchargeables

3. **Models**: Model Registry
   - Versions du modèle
   - Stages (Staging, Production, Archived)
   - Historique des transitions

4. **Compare Runs**: Comparaison side-by-side
   - Différences de paramètres
   - Graphiques comparatifs
   - Parallélisation de 2 à N runs

---

## 📊 Métriques RAG recommandées

```python
metrics = {
    # Évaluation RAGAS
    "faithfulness": 0.85,              # Véracité des réponses
    "answer_relevancy": 0.78,          # Pertinence de la réponse
    "context_precision": 0.82,         # Précision du contexte
    "context_recall": 0.75,            # Rappel du contexte

    # Performance
    "retrieval_time_ms": 150,
    "llm_inference_time_ms": 800,
    "total_time_ms": 950,

    # Datasets
    "num_questions": 100,
    "num_documents_retrieved": 500,
    "avg_context_length": 2000,
}
```

---

## 🏷️ Tags recommandés

Pour filtrer rapidement dans MLflow UI:

```python
tags = {
    # Stage du développement
    "stage": "dev",                    # dev | staging | prod

    # Modèles utilisés
    "llm_model": "gemma3:1b",
    "embedding_model": "paraphrase-multilingual-MiniLM-L12-v2",

    # Type d'expérience
    "experiment_type": "baseline",     # baseline | optimization | comparison

    # Version
    "version": "1.0",

    # Utilisateur/équipe
    "author": "mlops-team",

    # Dataset
    "dataset": "production_logs",

    # Résultats
    "status": "success",               # success | failed | incomplete
}
```

---

## 🐛 Dépannage

### MLflow ne démarre pas
```bash
# Vérifier que le port 5000 est libre
lsof -i :5000

# Vérifier la base de données SQLite
ls -la mlflow.db

# Redémarrer avec verbosité
mlflow ui --host 0.0.0.0 --port 5000 --backend-store-uri sqlite:///mlflow.db --verbose
```

### Pas de runs visibles
```bash
# Vérifier l'expérience active
mlflow experiments list

# Créer l'expérience manquante
mlflow experiments create --experiment-name my_experiment

# Vérifier le tracking URI
echo $MLFLOW_TRACKING_URI
```

### Artefacts non sauvegardés
```bash
# Vérifier les permissions
ls -la /tmp/ragas_eval_*

# Vérifier l'espace disque
df -h

# Logger manuellement un fichier
tracker.log_artifact("/path/to/file", artifact_path="custom")
```

---

## 📚 Ressources

- [MLflow Documentation](https://mlflow.org/docs/)
- [MLflow Model Registry](https://mlflow.org/docs/latest/model-registry.html)
- [Logging Models](https://mlflow.org/docs/latest/python_api/index.html#logging-models)
- [Search Runs API](https://mlflow.org/docs/latest/python_api/mlflow.html#mlflow.search_runs)

---

## 🎓 Exemples complets

Voir `/scripts/demo_mlflow_tracking.py` pour des exemples complets:

```bash
# Demo: Tracking simple
python scripts/demo_mlflow_tracking.py --mode=tracking

# Demo: Comparaison des runs
python scripts/demo_mlflow_tracking.py --mode=comparison

# Demo: Model Registry
python scripts/demo_mlflow_tracking.py --mode=registry

# Demo: Tous les modes
python scripts/demo_mlflow_tracking.py --mode=all
```

---

## 🔄 Intégration CI/CD

Pour GitActions, ajouter les variables:

```yaml
env:
  MLFLOW_TRACKING_URI: http://mlflow-server:5000
  MLFLOW_EXPERIMENT_NAME: github-actions
```

Dans le pipeline:

```yaml
- name: Log results to MLflow
  run: |
    mlflow runs create \
      --experiment-name ${{ env.MLFLOW_EXPERIMENT_NAME }} \
      --run-name "${{ github.run_id }}" \
      --backend-store-uri ${{ env.MLFLOW_TRACKING_URI }}
```

---

**Dernière mise à jour:** May 2026 | **Version MLflow:** 2.10.0
