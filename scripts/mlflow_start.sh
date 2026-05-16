#!/bin/bash
# mlflow_start.sh — Démarrage rapide de MLflow
# Usage: ./scripts/mlflow_start.sh [--port 5000] [--backend sqlite|postgresql]

set -e

# Configuration par défaut
PORT=${PORT:-5000}
BACKEND_STORE_URI="${BACKEND_STORE_URI:-sqlite:///mlflow.db}"
ARTIFACTS_STORE_PATH="${ARTIFACTS_STORE_PATH:-./mlflow_artifacts}"

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Démarrage de MLflow Server${NC}\n"

# Créer le dossier d'artifacts s'il n'existe pas
mkdir -p "$ARTIFACTS_STORE_PATH"
echo -e "${GREEN}✓${NC} Dossier d'artifacts: $ARTIFACTS_STORE_PATH"

# Vérifier si le port est disponible
if lsof -i :$PORT 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Port $PORT déjà en utilisation!${NC}"
    read -p "Utiliser un autre port? (Défaut: $((PORT+1))): " NEW_PORT
    PORT=${NEW_PORT:-$((PORT+1))}
fi

# Vérifier les dépendances
if ! command -v mlflow &> /dev/null; then
    echo -e "${RED}✗ MLflow n'est pas installé${NC}"
    echo "Installation: pip install mlflow==2.10.0"
    exit 1
fi

echo -e "${GREEN}✓${NC} MLflow version: $(mlflow --version 2>&1 | grep -oP 'mlflow, version \K[^\s]*')"

# Démarrer MLflow
echo -e "\n${BLUE}📊 Configuration:${NC}"
echo "  Port: $PORT"
echo "  Backend: $BACKEND_STORE_URI"
echo "  Artifacts: $ARTIFACTS_STORE_PATH"
echo ""

echo -e "${GREEN}▶ Démarrage du serveur...${NC}\n"

mlflow server \
    --host 0.0.0.0 \
    --port "$PORT" \
    --backend-store-uri "$BACKEND_STORE_URI" \
    --default-artifact-root "$ARTIFACTS_STORE_PATH"

echo -e "\n${GREEN}✓ MLflow Server arrêté${NC}"
