# 🔧 Commandes pour déboguer CI/CD

**Date** : 2026-06-07  
**Projet** : mlops-rag-delivery

---

## 🌐 **Voir l'état des workflows GitHub**

### **1. Lister tous les runs récents**
```bash
# Voir les 10 derniers runs de tous les workflows
gh run list

# Voir uniquement les runs de main branch
gh run list --branch main

# Voir les runs d'une branche spécifique
gh run list --branch feature/sprint-securite

# Format table (plus lisible)
gh run list --json status,name,headBranch,createdAt --branch main
```

### **2. Voir détails d'un workflow spécifique**
```bash
# Voir tous les runs du workflow CI
gh run list --workflow=ci.yml

# Voir tous les runs du workflow CD
gh run list --workflow=cd.yml

# Voir tous les runs du workflow Model Validation
gh run list --workflow=model_validation.yml

# Voir tous les runs du workflow Security
gh run list --workflow=security.yml
```

### **3. Voir logs d'un run spécifique**
```bash
# Voir le dernier run (avec ID)
gh run view

# Voir logs complets d'un run (colorisé)
gh run view {RUN_ID}

# Voir les logs d'un job spécifique dans le run
gh run view {RUN_ID} --job {JOB_ID}

# Afficher les logs dans le terminal
gh run view {RUN_ID} --log

# Télécharger les logs artifacts
gh run download {RUN_ID} -D ./github-artifacts
```

### **4. Télécharger artifacts d'un run**
```bash
# Lister les artifacts d'un run
gh run view {RUN_ID} --json artifacts

# Télécharger tous les artifacts
gh run download {RUN_ID}

# Télécharger dans un dossier spécifique
gh run download {RUN_ID} -D ./my-artifacts

# Artifacts typiques:
# - ragas-report/        (model_validation workflow)
# - coverage.xml         (test artifacts)
# - trivy-results.sarif  (security scan)
```

---

## 🔁 **Déclencher/Re-exécuter les workflows**

### **Re-exécuter un run entier**
```bash
# Re-exécuter un run spécifique
gh run rerun {RUN_ID}

# Re-exécuter et attendre la fin
gh run rerun {RUN_ID} --wait

# Verbose output pendant l'attente
gh run rerun {RUN_ID} --wait --verbose
```

### **Déclencher manuellement un workflow**
```bash
# Trigger CI sur feature branch
gh workflow run ci.yml --ref feature/sprint-securite

# Trigger CI sur main
gh workflow run ci.yml --ref main

# Trigger Model Validation
gh workflow run model_validation.yml --ref main

# Trigger Security scan
gh workflow run security.yml --ref feature/sprint-securite

# Attendre la fin après trigger
gh run list --workflow=ci.yml --branch feature/sprint-securite --json status
```

### **CD (seulement possible sur main après CI pass)**
```bash
# CD est auto-triggered par push main, pas besoin de le déclencher manuellement
# Mais on peut voir les runs CD:
gh run list --workflow=cd.yml

# Voir logs du dernier CD
gh run view $(gh run list --workflow=cd.yml --limit 1 --json databaseId -q) --log
```

---

## 🏃 **Exécuter les tests localement (avant de pusher)**

### **Setup local**
```bash
# Cloner et entrer dans le repo
git clone https://github.com/merrad/mlops-rag-delivery.git
cd mlops-rag-delivery

# Setup Python 3.11
python3.11 -m venv venv
source venv/bin/activate  # ou: venv\Scripts\activate (Windows)

# Installer dépendances
pip install --upgrade pip
pip install -r requirements.txt
pip install pytest pytest-cov flake8 black
```

### **1. Lint check**
```bash
# Lint avec flake8
flake8 src/ tests/ --max-line-length=120 --extend-ignore=E203,W503

# Format check avec black
black --check src/ tests/

# Auto-format (danger!)
black src/ tests/

# Linter output format
flake8 src/ tests/ --format=json > flake8_report.json
```

### **2. Unit tests + coverage**
```bash
# Run unit tests
pytest tests/unit/ -v

# Avec coverage
pytest tests/unit/ --cov=src --cov-report=term-missing -v

# Coverage report en HTML
pytest tests/unit/ --cov=src --cov-report=html
# Ouvrir: htmlcov/index.html

# Check coverage threshold
coverage report --fail-under=70

# Voir les lignes pas couvertes
pytest tests/unit/ --cov=src --cov-report=term-missing:skip-covered
```

### **3. Integration tests**
```bash
# Lancer Qdrant en background
docker run -d -p 6333:6333 --name qdrant-test qdrant/qdrant:latest

# Attendre que Qdrant soit prêt
sleep 3
curl http://localhost:6333/health

# Run integration tests
QDRANT_HOST=localhost QDRANT_PORT=6333 pytest tests/integration/ -v

# Cleanup
docker stop qdrant-test && docker rm qdrant-test
```

---

## 🔒 **Tests de sécurité localement**

### **Trivy filesystem scan**
```bash
# Installer Trivy
curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin

# Scan filesystem
trivy fs . --severity CRITICAL,HIGH

# Scan avec format JSON
trivy fs . --format json -o trivy_fs_report.json

# Scan spécifique répertoire (plus rapide)
trivy fs src/ --severity CRITICAL,HIGH
```

### **Trivy image scan**
```bash
# Build image
docker build -t rag-api:local -f docker/api/Dockerfile .

# Scan image
trivy image rag-api:local --severity CRITICAL,HIGH

# Format SARIF (comme workflow)
trivy image rag-api:local --format sarif -o trivy_image_report.sarif

# Policy check (0 CRITICAL, <= 3 HIGH)
trivy image rag-api:local --exit-code 1 --severity CRITICAL
```

---

## 📊 **RAGAS Evaluation localement**

### **Prerequisite**
```bash
# Lancer services minimum
docker compose up -d qdrant api ollama

# Attendre que tout soit prêt (2-3 min)
sleep 180
curl http://localhost:8080/health
```

### **Exécuter RAGAS eval**
```bash
# Depuis projet root
python scripts/run_ragas_eval.py

# Output: 
#   - Logs dans stdout
#   - ragas.json avec scores
#   - Summary avec pass/fail

# Ou avec options
python scripts/run_ragas_eval.py --output ./ragas_report.json

# Voir les résultats
cat ragas_report.json | jq '.[]'

# Check thresholds
cat ragas_report.json | jq '.faithfulness, .answer_relevancy'
```

---

## 🐛 **Déboguer un workflow échoué**

### **Scénario 1 : Lint échoue**
```bash
# Reproduire localement
flake8 src/ tests/ --max-line-length=120 --extend-ignore=E203,W503

# Voir les erreurs
# Format: {file}:{line}:{col}: {code} {message}

# Fixer (auto-format)
black src/ tests/

# Re-check
black --check src/ tests/
flake8 src/ tests/ ...
```

### **Scénario 2 : Tests échouent (coverage < 70%)**
```bash
# Voir quel fichier manque de coverage
pytest tests/unit/ --cov=src --cov-report=term-missing

# Ligne par ligne manquée
coverage report --precision=3

# Voir les tests manquants
# → Ajouter tests pour couvrir les lignes manquantes

# Re-check
pytest tests/unit/ --cov=src --cov-report=term-missing
coverage report --fail-under=70
```

### **Scénario 3 : Security scan échoue (CVE CRITICAL)**
```bash
# Voir les vulns
trivy image rag-api:local --severity CRITICAL

# Analyser chaque CVE
# Options:
#   1. Updater base image (FROM xxx:latest)
#   2. Updater dépendance Python coupable
#   3. Si unfixable: documenter et ignorer

# Exemple: update base image
# Dockerfile:
#   FROM python:3.11-slim  → FROM python:3.11-slim-bookworm
# docker build -t rag-api:local -f docker/api/Dockerfile .
# trivy image rag-api:local --severity CRITICAL

# Re-check après fix
```

### **Scénario 4 : RAGAS seuils non atteints**
```bash
# Lancer eval et voir scores
python scripts/run_ragas_eval.py

# Voir les seuils dans le script
cat scripts/run_ragas_eval.py | grep -E "threshold|faith|relev"

# Options pour améliorer:
#   1. Améliorer prompt (src/rag/prompt_builder.py)
#   2. Améliorer retrieval (meilleure indexation)
#   3. Ajouter données (plus de documents RAG)
#   4. Baisser les seuils (pas recommandé)

# Après changement:
python scripts/run_ragas_eval.py
```

---

## 📈 **Monitoring des workflows en temps réel**

### **Watch status (bash)**
```bash
#!/bin/bash
# Voir l'état en temps réel (update toutes les 5 sec)

watch -n 5 'gh run list --limit 10 --json status,name,headBranch,createdAt -q'
```

### **Get run ID rapide**
```bash
# Get dernier run ID
LAST_RUN=$(gh run list --limit 1 --json databaseId -q)

# Watch ce run
gh run view $LAST_RUN --watch

# Ou attendre qu'il finisse
gh run view $LAST_RUN --wait

# Voir le résultat
gh run view $LAST_RUN --json conclusion
```

### **Parse workflow output**
```bash
# Extraire les métadonnées d'un run
gh run view {RUN_ID} --json \
  status,name,conclusion,createdAt,updatedAt,headBranch

# Format: JSON pour parsing
gh run list --json status,name,headBranch --jq '.[].status' | sort | uniq -c
```

---

## 📋 **Checklist avant de pusher (local CI simulation)**

```bash
#!/bin/bash
# Script de pré-check avant git push

set -e

echo "🔍 Running local CI checks..."

# 1. Lint
echo "1. Lint (flake8)..."
flake8 src/ tests/ --max-line-length=120 --extend-ignore=E203,W503 || exit 1

echo "2. Format (black)..."
black --check src/ tests/ || exit 1

# 2. Unit tests
echo "3. Unit tests..."
pytest tests/unit/ -q || exit 1

# 3. Coverage
echo "4. Coverage check..."
pytest tests/unit/ --cov=src --cov-report=term-missing -q || exit 1
coverage report --fail-under=70 || exit 1

# 4. Integration tests (optional, needs Qdrant)
if command -v docker &> /dev/null; then
  echo "5. Integration tests..."
  docker run -d -p 6333:6333 --name qdrant-check qdrant/qdrant:latest
  sleep 3
  QDRANT_HOST=localhost QDRANT_PORT=6333 pytest tests/integration/ -q || true
  docker stop qdrant-check && docker rm qdrant-check
fi

echo "✅ All checks passed! Ready to git push"
```

---

## 🚀 **Commandes raccourcis**

```bash
# Alias pour simplifier la vie
alias gh-runs='gh run list --json status,name,headBranch -q'
alias gh-last='gh run view $(gh run list --limit 1 --json databaseId -q)'
alias gh-watch='gh-last --watch'
alias gh-log='gh run view $(gh run list --limit 1 --json databaseId -q) --log'

# Ajouter à ~/.bashrc ou ~/.zshrc
```

---

## 📞 **Support & Links**

```
Documentation GitHub Actions: https://docs.github.com/en/actions
CLI Reference: gh help workflow
Trivy Docs: https://aquasecurity.github.io/trivy/
RAGAS Docs: https://docs.ragas.io/
```

---

**Généré le** : 2026-06-07  
**Pour** : Debugging rapide du CI/CD  

