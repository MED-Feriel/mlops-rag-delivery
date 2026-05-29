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
# zone(s) en DERNIER (priorité basse) : ne s'applique que si aucune zone précise
# n'est nommée (sinon le filtre zone= prend le relais) et qu'aucune autre source
# ne matche. Permet de router "quelle zone a les délais les plus longs ?" vers
# les snapshots de zones plutôt que vers une recherche non filtrée.
_SOURCE_KEYWORDS: dict[str, str] = {
    r"\bavis\b|\bcommentaire[s]?\b|\bnote[s]?\b": "avis_clients",
    r"\bincident[s]?\b": "incidents",
    r"\brestaurant[s]?\b": "restaurants",
    r"\bzone[s]?\b|\bquartier[s]?\b": "zones",
}

# ── Routage Familles temps réel (prioritaire) ──────────────────
# Famille 3 : état système / monitoring → snapshot Prometheus (source=prometheus)
# Famille 2 : logs applicatifs / erreurs récentes → logs ES (source=elasticsearch)
# Ces sources ne contiennent que quelques docs face aux 167K docs métier : sans
# filtre explicite elles ne remontent jamais dans le top-k vectoriel.
_FAMILLE3_PATTERN = (
    r"\bétat de santé\b|\bsanté de la plateforme\b|\bsanté du système\b"
    r"|\bsanté système\b|\bétat du système\b|\bétat système\b"
    r"|\btaux de succès\b|\bsuccess.rate\b|\blatence[s]?\b|\blatency\b"
    r"|\bmétrique[s]?\b|\bmonitoring\b|\bprometheus\b|\bgrafana\b"
    r"|\bservices? up\b|\bperformance\b|\bdébit\b"
    r"|\bthroughput\b|\bmémoire\b|\bcpu\b|\bscore contexte\b|\bhealth\b"
    r"|\bétat de la plateforme\b|\brag est[- ]il\b|\bsnapshot\b|\bsystème\b"
    # État d'un/des service(s) : "services sont en panne", "service down",
    # "quels services actifs"… → snapshot Prometheus. Exige le mot "service"
    # à proximité de panne/down/actif pour ne PAS capter "panne dns" ou
    # "panne du restaurant" (qui restent des incidents métier).
    r"|\bservices?\b[^.\n]{0,20}\b(en panne|panne|down|inactif|arrêté|hors service|actif)"
    r"|\b(en panne|down|inactif|hors service)\b[^.\n]{0,20}\bservices?\b"
    r"|\bquels services\b"
)
_FAMILLE2_PATTERN = (
    r"\blogs?\b|\berreur[s]? récente[s]?\b|\bwarn(ing)?s?\b"
    r"|\bmessage[s]? d'erreur\b|\bdans les logs\b"
)
# Note : "panne"/"crash" ne déclenchent PAS la Famille 2 (sinon "panne dns" et
# "panne du restaurant" seraient mal routés vers les logs ES au lieu de leurs
# type_event métier). Ils restent dans _LOG_LEVEL_KEYWORDS ci-dessous, donc
# n'agissent que si la Famille 2 est déjà déclenchée par "logs"/"erreur".

# ── Famille 2 : niveau de log + service applicatif ─────────────
# Ordre important : warn testé avant error (sinon "logs" matcherait error).
_LOG_LEVEL_KEYWORDS: dict[str, str] = {
    r"\bwarning\b|\bavertissement\b|\bwarn\b": "log_warn",
    r"\blog(s)?\b|\berreur(s)?\b|\bpanne\b|\bcrash\b": "log_error",
}
_LOG_SERVICE_KEYWORDS: dict[str, str] = {
    r"\bpayment.service\b|\bpaiement.service\b|\bpaiement\b": "payment-service",
    r"\bdispatch\b|\btracking\b": "tracking-service",
}

# ── Famille 1 : catégorie restaurant + véhicule livreur ────────
_CATEGORIE_KEYWORDS: dict[str, str] = {
    r"\bpizza\b": "Pizza",
    r"\bfast.?food\b": "Fast Food",
    r"\bburger[s]?\b": "Burgers",
    r"\bcouscous\b": "Couscous",
    r"\bshawarma\b|\bchawarma\b": "Shawarma",
}
_VEHICULE_KEYWORDS: dict[str, str] = {
    r"\bmoto[s]?\b": "moto",
    r"\bvoiture[s]?\b": "voiture",
    r"\bvelo[s]?\b|\bvélo[s]?\b": "velo",
}

# ── Famille 4 : intention de synthèse / diagnostic ─────────────
# Pour ces questions ("causes", "pourquoi", "résume"…), on NE veut PAS appliquer
# le filtre type_event (ex: "causes de retard" → type_event=retard) car cela
# exclut le document de synthèse `synthese-incidents` qui contient justement la
# ventilation des causes/facteurs. On laisse donc remonter les docs agrégés.
_SYNTHESE_PATTERN = (
    r"\bcauses?\b|\bpourquoi\b|\braisons?\b|\bfacteurs?\b"
    r"|\bsynth[èe]se\b|\br[ée]sum[eé]\b|\borigine[s]?\b|\bexplique"
    r"|\bfr[ée]quent|\br[ée]current"
)

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

    # Routage Familles 2/3 EN PREMIER : si la question vise l'état système ou les
    # logs, on filtre directement sur la source temps réel et on court-circuite
    # le matching générique (type_event/source) qui sur-contraindrait à tort.
    famille: str | None = None
    if re.search(_FAMILLE3_PATTERN, q_lower):
        qdrant_filters["source"] = "prometheus"
        matched["famille"] = "3_metriques"
        famille = "3"
    elif re.search(_FAMILLE2_PATTERN, q_lower):
        qdrant_filters["source"] = "elasticsearch"
        matched["famille"] = "2_logs"
        famille = "2"
        # Niveau de log (log_warn/log_error) et service applicatif si précisés.
        lvl = _match_any(q_lower, _LOG_LEVEL_KEYWORDS)
        if lvl:
            qdrant_filters["type_event"] = lvl
            matched["log_level"] = lvl
        svc = _match_any(q_lower, _LOG_SERVICE_KEYWORDS)
        if svc:
            qdrant_filters["source_service"] = svc
            matched["source_service"] = svc

    # Famille 1 : entité métier ciblée (catégorie resto / véhicule livreur).
    # Ces filtres remplacent le type_event générique (docs snapshot, pas métier).
    metier_entity = False
    if not famille:
        categorie = _match_any(q_lower, _CATEGORIE_KEYWORDS)
        if categorie:
            qdrant_filters["categorie"] = categorie
            matched["categorie"] = categorie
            metier_entity = True
        vehicule = _match_any(q_lower, _VEHICULE_KEYWORDS)
        if vehicule:
            qdrant_filters["vehicule_type"] = vehicule
            matched["vehicule_type"] = vehicule
            metier_entity = True

    crit = _match_any(q_lower, _CRITICITE_KEYWORDS)
    if crit:
        qdrant_filters["criticite"] = crit
        matched["criticite"] = crit

    zone = _extract_zone(query)
    if zone:
        qdrant_filters["zone"] = zone
        matched["zone"] = zone

    # Intention de synthèse/diagnostic (F4) → on laisse remonter les docs agrégés
    # (synthese-*) en n'appliquant PAS le filtre type_event qui les exclurait.
    is_synthese = bool(re.search(_SYNTHESE_PATTERN, q_lower))
    if is_synthese:
        matched["synthese"] = True

    # type_event ne s'applique pas aux sources temps réel (ES/Prometheus), aux
    # requêtes ciblant une entité métier (resto/livreur), ni aux synthèses.
    if not famille and not metier_entity and not is_synthese:
        type_event = _match_any(q_lower, _TYPE_EVENT_KEYWORDS)
        if type_event:
            qdrant_filters["type_event"] = type_event
            matched["type_event"] = type_event

    # Source générique : moins prioritaire (peut surcontrainer). On ne l'applique
    # que si aucune autre règle (famille/type_event/criticité) n'a matché.
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

    # Incrément métrique Prometheus "rag_query_family_total" — famille déduite
    # de l'intent extrait. On choisit l'étiquette la plus informative dispo
    # (familles >> type_event >> source >> criticité >> "generique").
    famille_label = (
        matched.get("famille")
        or matched.get("type_event")
        or matched.get("source")
        or (f"criticite:{matched['criticite']}" if matched.get("criticite") else None)
        or "generique"
    )
    try:
        from src.monitoring.prometheus_metrics import RAG_QUERY_FAMILY_TOTAL

        RAG_QUERY_FAMILY_TOTAL.labels(famille=str(famille_label)).inc()
    except Exception:
        # En tests / hors API container, ignorer si module non importable.
        pass

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
