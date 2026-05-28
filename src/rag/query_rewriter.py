"""
Query rewriter — extraction d'intent par règles avant retrieval.

Transforme une question utilisateur en (question_originale, filtres_qdrant,
plage_dates). Les filtres sont ADDITIFS : "incidents critiques à Hydra en
mars 2026" → {criticite=critique, zone=Hydra} + plage [2026-03-01, 2026-03-31].

Le filtrage par sévérité/zone/source/type passe via Qdrant payload index
(MatchValue exact). Le filtrage par date est post-retrieval (les payloads
n'embarquent pas created_at, on parse le texte des documents).

Aucun LLM n'est appelé — pure regex/keyword matching pour rester rapide
et déterministe.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional


# ── Sévérité / criticité ───────────────────────────────────────
_CRITICITE_KEYWORDS: dict[str, str] = {
    r"\bcritique[s]?\b": "critique",
    r"\bsévérité critique\b": "critique",
    r"\bcritical\b": "critique",
    r"\binfrastructure\b": "critique",  # implicite pour DNS/outage
    r"\bhaute[s]?\b": "haute",
    r"\bsévérité haute\b": "haute",
    r"\bmoyenne[s]?\b": "moyenne",
    r"\bbasse[s]?\b": "basse",
}

# ── Zones (les 15 zones du référentiel Alger) ──────────────────
_ZONES_CANONIQUES = [
    "Dely Ibrahim",
    "Hydra",
    "Bab Ezzouar",
    "Kouba",
    "El Harrach",
    "Alger Centre",
    "Bordj El Bahri",
    "Bouzareah",
    "Bordj El Kiffan",
    "Staoueli",
    "Cheraga",
    "Sidi Abdellah",
    "Rouiba",
    "Dar El Beida",
    "Bab El Oued",
]

# ── Sources (table d'origine du document) ──────────────────────
_SOURCE_KEYWORDS: dict[str, str] = {
    r"\bavis\b|\bcommentaire[s]?\b|\bnote[s]?\b": "avis_clients",
    r"\bincident[s]?\b": "incidents",
    r"\brestaurant[s]?\b": "restaurants",
}

# ── Types d'événement ──────────────────────────────────────────
_TYPE_EVENT_KEYWORDS: dict[str, str] = {
    r"\bretard[s]?\b|\bretardé[s]?\b|\ben retard\b|\bperturbé[s]?\b|\bbloqué[s]?\b": "retard",
    r"\bdns\b|\brésolution\b|\bpanne dns\b": "dns_failure",
    r"\bpanne de paiement\b|\béchec paiement\b|\berreur paiement\b|\bpaiement échoué\b": "paiement_echoue",
    r"\bconvoi\b|\blivreur bloqué\b": "livreur_bloque",
    r"\bpic de charge\b|\bsurcharge\b|\bcanicule\b": "pic_charge",
    r"\brestaurant fermé\b|\bfermeture\b": "restaurant_ferme",
    r"\badresse incorrect[e]?\b|\badresse introuvable\b": "adresse_incorrecte",
}

# ── Sentiment des avis ─────────────────────────────────────────
_SENTIMENT_KEYWORDS: dict[str, str] = {
    r"\bnégatif[s]?\b|\bplainte[s]?\b|\bmécontent[s]?\b": "négatif",
    r"\bpositif[s]?\b|\bsatisfait[s]?\b|\bélogieux\b": "positif",
    r"\bneutre[s]?\b": "neutre",
}

# ── Mois (FR) ──────────────────────────────────────────────────
_MOIS_FR: dict[str, int] = {
    "janvier": 1,
    "février": 2,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
    "decembre": 12,
}


def _match_any(query_lower: str, patterns: dict[str, str]) -> Optional[str]:
    """Retourne la 1ère valeur dont le pattern matche, ou None."""
    for pat, value in patterns.items():
        if re.search(pat, query_lower):
            return value
    return None


def _extract_zone(query: str) -> Optional[str]:
    """Match case-insensible mais retourne le nom canonique."""
    q_lower = query.lower()
    for zone in _ZONES_CANONIQUES:
        if zone.lower() in q_lower:
            return zone
    return None


def _extract_date_range(query: str) -> Optional[tuple[datetime, datetime]]:
    """
    Détecte des expressions temporelles courantes :
      - "en mars 2026" / "mars 2026" → [2026-03-01, 2026-03-31 23:59]
      - "en mars" (sans année) → mois courant ou plus proche dans l'historique
      - "ces 30 derniers jours" → [now-30j, now]
      - "cette semaine" / "cette année" : non géré (retourne None)
    """
    q_lower = query.lower()

    # "N derniers jours"
    m = re.search(r"(\d+)\s*derniers?\s*jours?", q_lower)
    if m:
        n = int(m.group(1))
        end = datetime.now()
        start = end - timedelta(days=n)
        return (start, end)

    # "mois année" — ex: "mars 2026"
    for nom, num in _MOIS_FR.items():
        m = re.search(rf"\b{nom}\s+(\d{{4}})\b", q_lower)
        if m:
            year = int(m.group(1))
            start = datetime(year, num, 1)
            # dernier jour du mois
            if num == 12:
                end = datetime(year + 1, 1, 1) - timedelta(seconds=1)
            else:
                end = datetime(year, num + 1, 1) - timedelta(seconds=1)
            return (start, end)

    # "en <mois>" sans année — on prend l'année courante
    for nom, num in _MOIS_FR.items():
        if re.search(rf"\b(en|au mois de)\s+{nom}\b", q_lower) or re.search(
            rf"\bdu mois de\s+{nom}\b", q_lower
        ):
            year = datetime.now().year
            start = datetime(year, num, 1)
            if num == 12:
                end = datetime(year + 1, 1, 1) - timedelta(seconds=1)
            else:
                end = datetime(year, num + 1, 1) - timedelta(seconds=1)
            return (start, end)

    return None


# Regex pour extraire une date "YYYY-MM-DD HH:MM" du texte des documents
_DOC_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})")


def parse_doc_timestamp(text: str) -> Optional[datetime]:
    """Extrait la 1ère date trouvée dans le texte d'un document (format `YYYY-MM-DD HH:MM`)."""
    m = _DOC_DATE_RE.search(text)
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def rewrite_query(query: str) -> dict:
    """
    Analyse la question et retourne un dict :
      {
        "question": <str inchangée>,
        "qdrant_filters": <dict | None>,  # à passer à retrieve(filters=...)
        "date_range": <(start, end) | None>,  # filtrage post-retrieval
        "matched": <dict des règles activées>,  # debug/observability
      }

    Les filtres sont additifs : si plusieurs catégories matchent (criticité +
    zone + date), elles sont toutes appliquées simultanément.
    """
    q_lower = query.lower()
    qdrant_filters: dict = {}
    matched: dict = {}

    crit = _match_any(q_lower, _CRITICITE_KEYWORDS)
    if crit:
        qdrant_filters["criticite"] = crit
        matched["criticite"] = crit

    zone = _extract_zone(query)
    if zone:
        qdrant_filters["zone"] = zone
        matched["zone"] = zone

    type_event = _match_any(q_lower, _TYPE_EVENT_KEYWORDS)
    if type_event:
        qdrant_filters["type_event"] = type_event
        matched["type_event"] = type_event

    # Source : moins prioritaire (peut surcontrainer). On ne l'applique
    # que si aucun type_event ni criticité ne sont déjà extraits, ou si
    # la mention est explicite ("avis", "incident").
    if not matched:
        source = _match_any(q_lower, _SOURCE_KEYWORDS)
        if source:
            qdrant_filters["source"] = source
            matched["source"] = source

    sentiment = _match_any(q_lower, _SENTIMENT_KEYWORDS)
    if sentiment:
        # Pas de filtre Qdrant direct (le champ n'est pas indexé comme keyword),
        # on l'ajoute pour observability mais on s'en sert plus tard si on
        # indexe ce champ.
        matched["sentiment"] = sentiment

    date_range = _extract_date_range(query)
    if date_range:
        matched["date_range"] = (date_range[0].isoformat(), date_range[1].isoformat())

    return {
        "question": query,
        "qdrant_filters": qdrant_filters or None,
        "date_range": date_range,
        "matched": matched,
    }


def filter_by_date_range(
    chunks: list[dict], date_range: Optional[tuple[datetime, datetime]]
) -> list[dict]:
    """
    Filtrage post-retrieval par plage de dates : parse la date au format
    `YYYY-MM-DD HH:MM` du texte de chaque chunk. Les docs sans date
    parsable sont conservés (synthèses, snapshots — ils peuvent être
    pertinents indépendamment du mois).
    """
    if not date_range:
        return chunks
    start, end = date_range
    kept = []
    for c in chunks:
        ts = parse_doc_timestamp(c.get("text", ""))
        if ts is None:
            kept.append(c)
            continue
        if start <= ts <= end:
            kept.append(c)
    return kept
