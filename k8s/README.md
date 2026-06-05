# Déploiement Kubernetes — mlops-rag-delivery

Manifestes pour déployer le **cœur RAG** (FastAPI + Qdrant + Ollama/Gemma3:1b)
en production. Volontairement **hors périmètre** (trop lourd pour une démo PFE) :
Airflow, ELK, MLflow, Postgres, Kafka, Redis.

## Ce qui est déployé

| Composant | Type | Notes |
|-----------|------|-------|
| `api` | Deployment (2 replicas) + HPA (2→8) | FastAPI RAG, port 8080 |
| `qdrant` | Deployment (1) + PVC 10Gi | base vectorielle, port 6333 |
| `ollama` | Deployment (1) + PVC 5Gi | LLM Gemma3:1b, port 11434 |
| `simulator` | Deployment (0) | désactivé (besoin Kafka+Postgres) |

> **3 corrections vs l'énoncé**, vérifiées dans le repo :
> - Port Qdrant interne = **6333** (le `6335` du docker-compose est le port *hôte* `6335:6333`).
> - Health Qdrant = **`/readyz`** + **`/livez`** (`/health` renvoie 404).
> - Image = `ghcr.io/med-feriel/mlops-rag-delivery/<service>:latest` (repo en minuscules).

## Prérequis

- Un cluster Kubernetes (k3s, minikube, kind, EKS/GKE/AKS…).
- **Ingress NGINX** installé (`ingress-nginx`).
- **metrics-server** installé (sinon le HPA reste en `<unknown>`).
- Une **StorageClass par défaut** (sinon décommenter `storageClassName` dans les PVC).
- Le modèle d'embedding est **téléchargé depuis HuggingFace** par un initContainer
  au démarrage de l'API → le cluster doit avoir accès à `huggingface.co`
  (sinon : baker le modèle dans l'image, voir plus bas).

## 1. Secrets (ne jamais committer de vraies valeurs)

**Secret applicatif** (mots de passe / JWT). Option recommandée — créer hors-Git :

```bash
kubectl create namespace rag-livraison

kubectl create secret generic rag-secrets -n rag-livraison \
  --from-literal=POSTGRES_PASSWORD='' \
  --from-literal=JWT_SECRET="$(openssl rand -hex 32)" \
  --from-literal=AUTH_PASSWORD='change-me' \
  --from-literal=API_SERVICE_TOKEN=''
```

*(Alternative : remplir les valeurs dans `secrets.yaml` puis `kubectl apply -f secrets.yaml`.
N'utilisez qu'UNE des deux méthodes.)*

**Secret de pull GHCR** (si le package est privé) :

```bash
kubectl create secret docker-registry ghcr-secret -n rag-livraison \
  --docker-server=ghcr.io \
  --docker-username=<github-user> \
  --docker-password=<GHCR_TOKEN>
```

*(Si vous rendez le package GHCR public, supprimez les blocs `imagePullSecrets` des deployments.)*

## 2. Déploiement

```bash
# Namespace d'abord
kubectl apply -f namespace.yaml

# Config + stockage
kubectl apply -f configmap.yaml
kubectl apply -f secrets.yaml          # uniquement si non créé via kubectl ci-dessus
kubectl apply -f pvc/

# Charges
kubectl apply -f deployments/
kubectl apply -f services/
kubectl apply -f hpa/
kubectl apply -f ingress/
```

Ou tout d'un coup (le namespace est inclus) :

```bash
kubectl apply -R -f .
```

## 3. Vérification

```bash
# Les pods montent (l'API attend son initContainer de téléchargement du modèle)
kubectl get pods -n rag-livraison -w

# Logs du téléchargement du modèle d'embedding
kubectl logs -n rag-livraison deploy/api -c embedding-model-downloader

# Logs du pull Gemma3:1b
kubectl logs -n rag-livraison deploy/ollama -c pull-gemma3

# HPA (doit afficher des % CPU, pas <unknown>)
kubectl get hpa -n rag-livraison

# Test rapide sans ingress
kubectl port-forward -n rag-livraison svc/api 8080:8080
curl http://localhost:8080/health
curl http://localhost:8080/prompt/version
```

## 4. Accès via l'Ingress

```bash
# Récupérer l'IP de l'ingress-nginx puis mapper l'hôte
echo "<INGRESS_IP>  rag.livraison.local" | sudo tee -a /etc/hosts

curl http://rag.livraison.local/health
curl -X POST http://rag.livraison.local/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"Quels restaurants ont le plus de retards ?","top_k":5}'
```

## ⚠️ Données : Qdrant démarre VIDE

Les manifestes déploient l'infra, mais la collection `livraison_rag` est **vide**
au premier démarrage. Tant qu'elle n'est pas peuplée, les requêtes renvoient la
réponse de secours « contexte vide ». Pour l'alimenter, lancer l'ETL (non
déployé ici) en pointant `QDRANT_HOST=qdrant`/`QDRANT_PORT=6333`, par ex. via un
`kubectl run` ponctuel de l'image ETL, ou en restaurant un snapshot Qdrant.

## Options production

- **Cluster air-gapped / HF indisponible** : retirer l'initContainer de
  téléchargement et **baker le modèle dans l'image** (`COPY models/ ...` dans un
  Dockerfile de prod), avec `HF_HUB_OFFLINE=1`.
- **Mutualiser le modèle** entre replicas : remplacer l'`emptyDir` `models` par
  un PVC **ReadWriteMany** pré-rempli (au lieu d'un téléchargement par pod).
- **Activer les caches** : déployer un Service `redis` puis passer
  `EMBEDDING_CACHE_ENABLED`/`ANSWER_CACHE_ENABLED` à `true` dans le ConfigMap.
- **Activer l'auth** : `AUTH_ENABLED=true` + `JWT_SECRET`/`AUTH_PASSWORD` dans le
  Secret, puis obtenir un token via `POST /auth/token`.
- **Épingler les images** `ollama/ollama` et `qdrant/qdrant` à des versions fixes.

## Désinstallation

```bash
kubectl delete namespace rag-livraison
```
