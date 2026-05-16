#!/bin/bash
# setup_mlflow.sh — Configuration complète MLflow pour le projet RAG
# Usage: ./scripts/setup_mlflow.sh

set -e

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   MLflow Setup pour mlops-rag-delivery                        ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}\n"

# 1. Vérifier les prérequis
echo -e "${YELLOW}📋 Étape 1: Vérification des prérequis${NC}"
echo "---"

# Vérifier Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗ Python3 non trouvé${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} Python3: $(python3 --version)"

# Vérifier pip
if ! command -v pip &> /dev/null; then
    echo -e "${RED}✗ pip non trouvé${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} pip: $(pip --version)"

# 2. Installer MLflow si nécessaire
echo -e "\n${YELLOW}📦 Étape 2: Installation des dépendances MLflow${NC}"
echo "---"

if python3 -c "import mlflow" 2>/dev/null; then
    MLFLOW_VERSION=$(python3 -c "import mlflow; print(mlflow.__version__)")
    echo -e "${GREEN}✓${NC} MLflow déjà installé: $MLFLOW_VERSION"
else
    echo "Installation de MLflow..."
    pip install mlflow==2.10.0 -q
    echo -e "${GREEN}✓${NC} MLflow 2.10.0 installé"
fi

# 3. Créer la structure MLflow
echo -e "\n${YELLOW}🗂️  Étape 3: Création de la structure MLflow${NC}"
echo "---"

mkdir -p mlflow_artifacts
mkdir -p .mlflow_cache
echo -e "${GREEN}✓${NC} Dossiers créés"

# 4. Initialiser la base de données MLflow
echo -e "\n${YELLOW}💾 Étape 4: Initialisation de la base de données${NC}"
echo "---"

if [ ! -f "mlflow.db" ]; then
    echo "Création de mlflow.db..."
    touch mlflow.db
    echo -e "${GREEN}✓${NC} Base de données créée"
else
    echo -e "${GREEN}✓${NC} Base de données existante: mlflow.db"
fi

# 5. Configurer les variables d'environnement
echo -e "\n${YELLOW}⚙️  Étape 5: Configuration des variables d'environnement${NC}"
echo "---"

if ! grep -q "MLFLOW_TRACKING_URI" .env 2>/dev/null; then
    echo -e "\n# MLflow Configuration" >> .env
    echo "MLFLOW_TRACKING_URI=http://localhost:5000" >> .env
    echo "MLFLOW_EXPERIMENT_NAME=rag-livraison" >> .env
    echo -e "${GREEN}✓${NC} Variables d'environnement ajoutées"
else
    echo -e "${GREEN}✓${NC} Variables d'environnement existantes"
fi

# 6. Créer les expériences par défaut
echo -e "\n${YELLOW}🔬 Étape 6: Création des expériences par défaut${NC}"
echo "---"

# Créer un script Python pour initialiser les expériences
cat > /tmp/init_mlflow_experiments.py << 'EOF'
import mlflow
import sqlite3

mlflow.set_tracking_uri("sqlite:///mlflow.db")

experiments = [
    "rag-livraison",
    "rag-evaluation",
    "demo_basic",
    "demo_comparison",
    "demo_artifacts",
    "github-actions"
]

for exp_name in experiments:
    try:
        exp = mlflow.get_experiment_by_name(exp_name)
        if exp is None:
            mlflow.create_experiment(exp_name)
            print(f"✓ Expérience créée: {exp_name}")
        else:
            print(f"✓ Expérience existe: {exp_name}")
    except Exception as e:
        print(f"⚠ Erreur pour {exp_name}: {e}")

print("\n✅ Initialisation des expériences complétée")
EOF

python3 /tmp/init_mlflow_experiments.py 2>/dev/null || echo -e "${YELLOW}⚠${NC} Expériences seront créées au démarrage de MLflow"
rm -f /tmp/init_mlflow_experiments.py

# 7. Rendre les scripts exécutables
echo -e "\n${YELLOW}🔧 Étape 7: Configuration des scripts${NC}"
echo "---"

chmod +x scripts/mlflow_start.sh 2>/dev/null || true
chmod +x scripts/demo_mlflow_tracking.py 2>/dev/null || true
echo -e "${GREEN}✓${NC} Scripts rendus exécutables"

# 8. Résumé final
echo -e "\n${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   ✅ SETUP MLFLOW COMPLÉTÉ AVEC SUCCÈS                         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}\n"

echo -e "${GREEN}📊 Prochaines étapes:${NC}\n"

echo -e "1️⃣  Démarrer MLflow Server:"
echo -e "   ${BLUE}cd /home/mlopsadmin/project/mlops-rag-delivery${NC}"
echo -e "   ${BLUE}./scripts/mlflow_start.sh${NC}"
echo ""

echo -e "2️⃣  Accéder au dashboard:"
echo -e "   ${BLUE}http://localhost:5000${NC}"
echo ""

echo -e "3️⃣  Exécuter la démo:"
echo -e "   ${BLUE}source .venv/bin/activate${NC}"
echo -e "   ${BLUE}export PYTHONPATH=\$(pwd)${NC}"
echo -e "   ${BLUE}python scripts/demo_mlflow_tracking.py --mode=all${NC}"
echo ""

echo -e "4️⃣  Lire la documentation:"
echo -e "   ${BLUE}cat docs/MLFLOW_README.md${NC}"
echo -e "   ${BLUE}cat docs/mlflow_guide.md${NC}"
echo ""

echo -e "${YELLOW}📁 Fichiers créés/modifiés:${NC}"
echo "  • src/monitoring/mlflow_tracker.py (NEW)"
echo "  • src/rag/rag_with_mlflow.py (NEW)"
echo "  • src/evaluation/ragas_evaluator.py (UPDATED)"
echo "  • scripts/mlflow_start.sh (NEW)"
echo "  • scripts/demo_mlflow_tracking.py (NEW)"
echo "  • tests/test_mlflow_integration.py (NEW)"
echo "  • docs/mlflow_guide.md (NEW)"
echo "  • docs/MLFLOW_README.md (NEW)"
echo ""

echo -e "${YELLOW}🗂️  Répertoires créés:${NC}"
echo "  • mlflow_artifacts/ (Pour les modèles et datasets)"
echo "  • .mlflow_cache/ (Cache local)"
echo ""

echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}\n"
