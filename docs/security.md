# Sécurité — mlops-rag-delivery

Couvre l'authentification (MLOPS-117) et la gestion des secrets (MLOPS-118).

## Résultat de l'audit initial

| Point | État |
|-------|------|
| `.env` commité dans Git | ✅ **Jamais** (historique propre, aucun secret en clair dans les diffs) |
| Secrets en dur dans `src/` | ✅ Aucun (lecture via settings / variables d'env) |
| Conteneurs non-root | ✅ Les 3 Dockerfiles (api/simulator/etl) tournent en `USER` non-root |
| Auth API | ✅ JWT + clés API + RBAC + rate-limit + audit (MLOPS-117) |
| Creds par défaut faibles | ⚠️ `docker-compose.yml` (grafana/airflow `admin`, airflow conn `secret`) et défauts `settings.py` → à externaliser (voir Remédiation) |

## Liste des secrets à configurer

| Secret | Variable / clé Vault | Usage |
|--------|----------------------|-------|
| Mot de passe Postgres | `POSTGRES_PASSWORD` · `rag/postgres` | DB métier / Airflow |
| Secret JWT | `JWT_SECRET` · `rag/jwt` | signature des tokens API |
| Mot de passe admin API | `ADMIN_PASSWORD` · `rag/admin` | login `/auth/token` |
| Jeton de service | `API_SERVICE_TOKEN` · `rag/service` | Open WebUI / machine-to-machine |
| Mot de passe Grafana | `GRAFANA_PASSWORD` | UI Grafana |
| Mot de passe Airflow | `AIRFLOW_PASSWORD` | UI Airflow |
| (selon déploiement) | `QDRANT_API_KEY`, `KAFKA_SECRET`, `ELASTIC_PASSWORD` | services managés |

## Générer un secret fort

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"   # 64 hex
# ou
openssl rand -base64 32
```

## Rotation des secrets (≤ 30 jours)

Script : [`scripts/rotate-secrets.sh`](../scripts/rotate-secrets.sh)

```bash
./scripts/rotate-secrets.sh jwt        # rote rag/jwt, redéploie l'API
./scripts/rotate-secrets.sh postgres   # rote + ALTER USER Postgres + redéploie
```

Procédure : génère une valeur forte → `vault kv put secret/rag/<x>` → ESO
resynchronise le Secret k8s → `kubectl rollout restart deployment/api`.

## Abstraction applicative

[`src/infra/secrets_manager.py`](../src/infra/secrets_manager.py) expose une
interface unique avec 3 backends, choisis via `SECRETS_BACKEND` :

```python
from src.infra.secrets_manager import get_secrets_manager
jwt = get_secrets_manager().get_secret("JWT_SECRET")   # env | vault | aws
```

### Vault (dev)
```bash
vault server -dev
export VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=<root>
vault kv put secret/rag/jwt secret="$(openssl rand -hex 32)"
SECRETS_BACKEND=vault VAULT_ADDR=$VAULT_ADDR VAULT_TOKEN=$VAULT_TOKEN ...
```

### AWS Secrets Manager
```bash
aws secretsmanager create-secret --name rag/jwt --secret-string "$(openssl rand -hex 32)"
export SECRETS_BACKEND=aws AWS_REGION=eu-west-1
```

### External Secrets Operator (Kubernetes)
```bash
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets -n external-secrets --create-namespace
kubectl -n rag-livraison create secret generic vault-token --from-literal=token=<VAULT_TOKEN>
kubectl apply -f k8s/external-secrets/secret-store.yaml
kubectl apply -f k8s/external-secrets/external-secret.yaml
# → ESO matérialise le Secret "rag-secrets" consommé par les Deployments.
```

## Remédiation des creds en dur (docker-compose)

`docker-compose.yml` contient des identifiants de **développement** en clair
(`GF_SECURITY_ADMIN_PASSWORD: admin`, `_AIRFLOW_WWW_USER_PASSWORD: admin`, conn
Airflow `postgres:secret`). Acceptable en local, **à externaliser en prod** via
substitution `${GRAFANA_PASSWORD:?}` / `${AIRFLOW_PASSWORD:?}` alimentée par le
`.env` (lui-même hors-Git). Suivi comme tâche de remédiation.

## Hygiène Git

`.gitignore` exclut `.env*`, `*.key`, `*.pem`, `secrets/`, `*.secret`. Ne jamais
committer de secret. En cas de fuite : révoquer/roter immédiatement, puis purger
l'historique (`git filter-repo`).
