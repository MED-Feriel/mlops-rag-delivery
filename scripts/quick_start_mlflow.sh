#!/usr/bin/env bash
# quick_start_mlflow.sh — Guide visuel de démarrage MLflow

cat << 'EOF'

╔════════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║                    🚀 MLflow QUICK START GUIDE                           ║
║                                                                            ║
║              Tracking • Experiments • Model Registry • Dashboard           ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝


📋 PRÉREQUIS
═══════════════════════════════════════════════════════════════════════════

✓ Python 3.11+
✓ MLflow 2.10.0 (pip install mlflow==2.10.0)
✓ Virtual environment activé
✓ PYTHONPATH configuré


🎯 3 ÉTAPES POUR DÉMARRER
═══════════════════════════════════════════════════════════════════════════

┌─ ÉTAPE 1: SETUP INITIAL ────────────────────────────────────────────────┐
│                                                                          │
│  $ cd /home/mlopsadmin/project/mlops-rag-delivery                      │
│  $ ./scripts/setup_mlflow.sh                                           │
│                                                                          │
│  ✓ Install MLflow                                                      │
│  ✓ Crée mlflow.db                                                      │
│  ✓ Crée expériences par défaut                                         │
│  ✓ Configure variables d'env                                           │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘

┌─ ÉTAPE 2: DÉMARRER LE SERVER ───────────────────────────────────────────┐
│                                                                          │
│  $ ./scripts/mlflow_start.sh                                           │
│                                                                          │
│  ▶ MLflow Server démarré sur le port 5000                              │
│  ▶ Accéder: http://localhost:5000                                      │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘

┌─ ÉTAPE 3: EXÉCUTER LA DÉMO ─────────────────────────────────────────────┐
│                                                                          │
│  $ source .venv/bin/activate                                           │
│  $ export PYTHONPATH=$(pwd)                                            │
│  $ python scripts/demo_mlflow_tracking.py --mode=all                   │
│                                                                          │
│  Démos disponibles:                                                    │
│  • --mode=tracking    → Tracking simple des expériences                │
│  • --mode=comparison  → Comparaison des runs                           │
│  • --mode=registry    → Model Registry                                 │
│  • --mode=artifacts   → Logging détaillé avec artifacts               │
│  • --mode=all         → Tous les démos                                 │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘


💡 EXEMPLE D'UTILISATION SIMPLE
═══════════════════════════════════════════════════════════════════════════

from src.monitoring.mlflow_tracker import MLflowTracker, MLflowRun

# 1. Créer un tracker
tracker = MLflowTracker(
    tracking_uri="http://localhost:5000",
    experiment_name="my_experiments"
)

# 2. Utiliser le context manager
with MLflowRun(tracker, "my_run_1", tags={"version": "1.0"}):
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

    # Logger des fichiers
    tracker.log_artifact("/path/to/model.pkl")

    # La run se ferme automatiquement


📊 VOIR LES RÉSULTATS
═══════════════════════════════════════════════════════════════════════════

Dans le dashboard: http://localhost:5000

1. Experiments
   ├─ Voir toutes les expériences
   ├─ Filtrer par tags
   └─ Sélectionner une expérience

2. Runs
   ├─ Voir toutes les runs
   ├─ Comparer les métriques
   ├─ Télécharger les artifacts
   └─ Voir les paramètres

3. Compare Runs
   ├─ Sélectionner 2+ runs
   ├─ Comparer les paramètres
   └─ Voir les graphiques


📈 COMPARER LES EXPÉRIENCES
═══════════════════════════════════════════════════════════════════════════

# Afficher les meilleures runs
comparison = tracker.compare_experiments("faithfulness", top_n=10)
print(comparison)

# Résumé formaté
print(rag_mlflow.compare_experiments_summary("faithfulness"))

# Trouver la meilleure run
best = tracker.get_best_run("answer_relevancy")
print(f"Run ID: {best['run_id']}")
print(f"Métriques: {best['metrics']}")


🧪 TESTER L'INTÉGRATION
═══════════════════════════════════════════════════════════════════════════

# Lancer les tests
$ pytest tests/test_mlflow_integration.py -v

# Résultats
TestMLflowTracker::test_initialization ✓
TestMLflowTracker::test_start_run ✓
TestMLflowTracker::test_log_params ✓
...
16 passed in 1.23s


📚 DOCUMENTATION DISPONIBLE
═══════════════════════════════════════════════════════════════════════════

1. docs/MLFLOW_README.md
   → Vue d'ensemble et exemples

2. docs/mlflow_guide.md
   → Guide complet (200+ lignes)
   → Tous les cas d'usage
   → Dépannage

3. MLFLOW_INTEGRATION_SUMMARY.txt
   → Résumé des fichiers créés
   → Checklist


🔧 TROUBLESHOOTING
═══════════════════════════════════════════════════════════════════════════

❌ Port 5000 déjà utilisé?
   → ./scripts/mlflow_start.sh vous demande un autre port

❌ MLflow pas installé?
   → pip install mlflow==2.10.0

❌ Pas de données dans le dashboard?
   → python scripts/demo_mlflow_tracking.py --mode=tracking

❌ Erreurs d'import?
   → source .venv/bin/activate
   → export PYTHONPATH=$(pwd)


🎯 PROCHAINES ÉTAPES
═══════════════════════════════════════════════════════════════════════════

1. ✓ Setup MLflow               (./scripts/setup_mlflow.sh)
2. ✓ Démarrer le server         (./scripts/mlflow_start.sh)
3. ✓ Exécuter la démo           (python scripts/demo_mlflow_tracking.py)
4. □ Intégrer dans votre code   (Voir exemples ci-dessus)
5. □ Tracker vos expériences    (Créer vos runs)
6. □ Comparer les résultats     (Dashboard)
7. □ Déployer en production     (Voir docs/mlflow_guide.md)


📞 SUPPORT
═══════════════════════════════════════════════════════════════════════════

Documentation: docs/mlflow_guide.md
Exemples: scripts/demo_mlflow_tracking.py
Tests: tests/test_mlflow_integration.py


═══════════════════════════════════════════════════════════════════════════

Prêt? Commencez par:

  $ cd /home/mlopsadmin/project/mlops-rag-delivery
  $ ./scripts/setup_mlflow.sh

Puis accédez: http://localhost:5000

═══════════════════════════════════════════════════════════════════════════

EOF
