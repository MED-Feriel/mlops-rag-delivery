#!/usr/bin/env bash
# restore_embedding.sh — Restaure le modèle d'embedding local (offline-ready).
#
# Idempotent : si le modèle est déjà présent et complet (model.safetensors de
# taille plausible + fichiers tokenizer), ne fait RIEN. Sinon, (re)télécharge
# uniquement les fichiers manquants/partiels depuis HuggingFace, avec reprise
# (curl -C -).
#
# Pourquoi : l'API charge l'embedder depuis ./models (monté en lecture seule,
# HF_HUB_OFFLINE=1) pour rester robuste si HuggingFace est lent/indisponible et
# portable vers la VM entreprise. Ce script reconstruit ce dossier au besoin
# (nouveau clone, volume effacé, conteneur recréé).
#
# Usage :
#   ./scripts/restore_embedding.sh           # vérifie puis restaure si besoin
#   FORCE=1 ./scripts/restore_embedding.sh   # re-télécharge tout
#   MODEL_DIR=/chemin ./scripts/restore_embedding.sh
set -euo pipefail

REPO_ID="${EMBEDDING_REPO:-sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MODEL_DIR="${MODEL_DIR:-$REPO_ROOT/models/paraphrase-multilingual-MiniLM-L12-v2}"
MIN_SAFETENSORS_BYTES="${MIN_SAFETENSORS_BYTES:-400000000}"  # ~400 Mo (réel ≈ 470)
BASE_URL="https://huggingface.co/${REPO_ID}/resolve/main"

# Fichiers minimaux pour charger le modèle via sentence-transformers.
FILES=(
  "config.json"
  "model.safetensors"
  "tokenizer.json"
  "tokenizer_config.json"
  "special_tokens_map.json"
  "sentencepiece.bpe.model"
  "modules.json"
  "config_sentence_transformers.json"
  "sentence_bert_config.json"
  "1_Pooling/config.json"
)

file_size() { stat -c%s "$1" 2>/dev/null || echo 0; }

is_complete() {
  [ -d "$MODEL_DIR" ] || return 1
  local st="$MODEL_DIR/model.safetensors"
  [ -f "$st" ] || return 1
  [ "$(file_size "$st")" -ge "$MIN_SAFETENSORS_BYTES" ] || return 1
  local f
  for f in "${FILES[@]}"; do
    [ -f "$MODEL_DIR/$f" ] || return 1
  done
  return 0
}

if [ "${FORCE:-0}" != "1" ] && is_complete; then
  echo "✅ Modèle déjà présent et complet : $MODEL_DIR"
  echo "   model.safetensors = $(file_size "$MODEL_DIR/model.safetensors") octets"
  exit 0
fi

echo "⤓ Restauration du modèle d'embedding"
echo "   repo  : $REPO_ID"
echo "   cible : $MODEL_DIR"
mkdir -p "$MODEL_DIR/1_Pooling"

# Vérifier la connectivité HF en amont → message clair plutôt qu'un échec opaque.
if ! curl -sfI --max-time 10 "https://huggingface.co" >/dev/null 2>&1; then
  echo "❌ HuggingFace injoignable depuis cet hôte." >&2
  echo "   Lance ce script depuis une machine avec accès Internet (ex: l'hôte WSL)" >&2
  echo "   ou copie manuellement le dossier $MODEL_DIR depuis une autre machine." >&2
  exit 2
fi

for f in "${FILES[@]}"; do
  dest="$MODEL_DIR/$f"
  mkdir -p "$(dirname "$dest")"

  # Sauter les fichiers déjà complets (sauf FORCE) → évite un 416 sur curl -C -.
  if [ "${FORCE:-0}" != "1" ] && [ -f "$dest" ]; then
    if [ "$f" = "model.safetensors" ]; then
      if [ "$(file_size "$dest")" -ge "$MIN_SAFETENSORS_BYTES" ]; then
        echo "   = $f (déjà présent)"; continue
      fi
    elif [ "$(file_size "$dest")" -gt 0 ]; then
      echo "   = $f (déjà présent)"; continue
    fi
  fi

  echo "   → $f"
  [ "${FORCE:-0}" = "1" ] && rm -f "$dest"
  # -C - : reprise d'un partiel ; -L : suit le CDN ; --fail : HTTP erreur = échec.
  curl -fL -C - --retry 3 --retry-delay 2 -o "$dest" "$BASE_URL/$f" \
    || { echo "❌ Échec téléchargement de $f" >&2; exit 3; }
done

if is_complete; then
  echo "✅ Restauration OK — $MODEL_DIR"
  echo "   model.safetensors = $(file_size "$MODEL_DIR/model.safetensors") octets"
else
  echo "❌ Restauration incomplète (vérifie la taille de model.safetensors)." >&2
  exit 4
fi
