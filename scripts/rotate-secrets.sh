#!/usr/bin/env bash
# rotate-secrets.sh — Rotation d'un secret applicatif (MLOPS-118).
#
# Génère une nouvelle valeur forte, la pousse dans Vault, propage si besoin
# (ex: mot de passe Postgres), puis redémarre l'API pour la recharger (via le
# Secret resynchronisé par External Secrets Operator).
#
# TEMPLATE : nécessite `vault` (authentifié) et `kubectl` (contexte du cluster).
# Usage : ./scripts/rotate-secrets.sh <jwt|postgres|admin|service>
set -euo pipefail

SECRET="${1:-}"
NS="${K8S_NAMESPACE:-rag-livraison}"
if [ -z "$SECRET" ]; then
  echo "Usage: $0 <jwt|postgres|admin|service>" >&2
  exit 1
fi
command -v vault >/dev/null || { echo "❌ 'vault' introuvable" >&2; exit 1; }
command -v kubectl >/dev/null || { echo "❌ 'kubectl' introuvable" >&2; exit 1; }

NEW_SECRET="$(openssl rand -base64 32)"
echo "→ rotation de rag/${SECRET}"

case "$SECRET" in
  jwt)     vault kv put secret/rag/jwt     secret="$NEW_SECRET" ;;
  admin)   vault kv put secret/rag/admin   password="$NEW_SECRET" ;;
  service) vault kv put secret/rag/service token="$NEW_SECRET" ;;
  postgres)
    vault kv put secret/rag/postgres password="$NEW_SECRET"
    # Propager le nouveau mot de passe à PostgreSQL lui-même.
    kubectl -n "$NS" exec postgres-0 -- \
      psql -U postgres -c "ALTER USER postgres PASSWORD '$NEW_SECRET';" \
      || echo "⚠️  ALTER USER à exécuter manuellement (pod postgres introuvable)"
    ;;
  *) echo "❌ secret inconnu: $SECRET" >&2; exit 1 ;;
esac

# ESO resynchronise le Secret k8s ; on redémarre l'API pour le recharger.
kubectl -n "$NS" rollout restart deployment/api
echo "✅ rag/${SECRET} roté + API redémarrée (rotation conseillée ≤ 30 jours)."
