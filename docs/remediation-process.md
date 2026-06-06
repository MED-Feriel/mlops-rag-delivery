# Processus de remédiation des vulnérabilités (MLOPS-119)

Les vulnérabilités sont détectées par **Trivy** (filesystem + image) en CI
(`.github/workflows/security.yml`), par **Dependabot** (`.github/dependabot.yml`)
et, en local, par `safety` / `pip-audit`.

## SLA par sévérité

| Sévérité | Délai de correction | Action |
|----------|---------------------|--------|
| **CRITICAL** | < 24 h | hotfix immédiat ; build bloqué (policy gate : tolérance 0) |
| **HIGH** | sprint en cours | correction prioritaire ; gate bloque au-delà de 3 |
| **MEDIUM** | ≤ 2 sprints | planifiée |
| **LOW** | best-effort | suivi |

## Procédure

1. **Détection** — Trivy (CI/hebdo) ou Dependabot ouvre une alerte (onglet
   Security via SARIF).
2. **Évaluation** — impact réel sur notre usage (la dépendance/chemin vulnérable
   est-il exécuté ?).
3. **Correction** — bump de version (PR Dependabot) ou patch ; à défaut,
   workaround temporaire + `.trivyignore` documenté avec échéance.
4. **Validation** — re-scan Trivy vert (policy gate).
5. **Déploiement** — via la CD ; pour un secret compromis, voir
   [`security.md`](security.md) (rotation).

## Scan local

```bash
# Image
trivy image --severity CRITICAL,HIGH rag-api:latest
# Filesystem / dépendances
trivy fs --severity CRITICAL,HIGH .
pip install safety pip-audit
pip-audit -r docker/api/requirements.txt
safety check -r docker/api/requirements.txt
```

## Gate CI (rappel)

`security.yml` échoue si **≥ 1 CRITICAL** ou **> 3 HIGH** sur l'image API. Le
scan filesystem utilise `ignore-unfixed: true` pour ne pas bloquer sur des CVE
base-image sans correctif amont (suivies, non bloquantes).
