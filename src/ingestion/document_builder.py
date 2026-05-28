"""Construit des documents textuels à partir des lignes Postgres."""

from __future__ import annotations

from datetime import datetime


def _fmt_dt(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M") if isinstance(dt, datetime) else str(dt or "")


def doc_incident(row: dict) -> tuple[str, str, dict]:
    text = (
        f"Incident #{row['id']} — Type: {row['type']} — Sévérité: {row['severite']} — "
        f"Statut: {'résolu' if row['resolu'] else 'NON RÉSOLU'}.\n"
        f"Survenu le {_fmt_dt(row['created_at'])} sur la commande #{row['commande_id']} "
        f"(statut={row['statut']}) en zone {row['zone_nom']}, "
        f"restaurant '{row['restaurant_nom']}', livreur {row['livreur_nom']}.\n"
        f"{row['description']}"
    )
    meta = {
        "source": "incidents",
        "topic": "incident",
        "type_event": row["type"],
        "criticite": row["severite"],
        "zone": row["zone_nom"],
        "resolu": bool(row["resolu"]),
    }
    return f"incident-{row['id']}", text, meta


def doc_commande(row: dict) -> tuple[str, str, dict]:
    retard = row["retard_min"]
    retard_str = f"retard de {retard} min" if retard and retard > 0 else "à l'heure"
    note = (
        f"note livreur {row['note_livreur']:.1f}/5"
        if row["note_livreur"]
        else "non notée"
    )
    text = (
        f"Commande #{row['id']} — {row['statut']} — créée le {_fmt_dt(row['created_at'])} "
        f"en zone {row['zone_nom']}.\n"
        f"Restaurant: {row['restaurant_nom']} — Livreur: {row['livreur_nom']} — "
        f"Montant: {row['montant']:.0f} DA — Paiement: {row['methode_paiement']}.\n"
        f"Délai estimé: {row['delai_estime_min']} min — Délai réel: "
        f"{row['delai_reel_min'] or 'N/A'} min ({retard_str}) — {note}.\n"
        f"Commentaire client: {row['commentaire'] or '(aucun)'}"
    )
    criticite = (
        "haute" if (retard or 0) > 30 else "moyenne" if (retard or 0) > 10 else "basse"
    )
    meta = {
        "source": "commandes",
        "topic": "commande",
        "type_event": row["statut"],
        "criticite": criticite,
        "zone": row["zone_nom"],
    }
    return f"commande-{row['id']}", text, meta


def doc_avis(row: dict) -> tuple[str, str, dict]:
    """Avis client : commentaire en langage naturel + contexte commande."""
    retard = None
    if row.get("delai_reel_min") and row.get("delai_estime_min"):
        retard = row["delai_reel_min"] - row["delai_estime_min"]
    retard_str = (
        f"retard {retard} min"
        if retard and retard > 0
        else "à l'heure" if retard is not None else "délai inconnu"
    )
    text = (
        f"Avis client — note {row['note']}/5 ({row['sentiment']}) — "
        f"commande #{row['commande_id']} ({row['statut']}) — "
        f"restaurant '{row['restaurant_nom']}', zone {row['zone_nom']}, "
        f"livreur {row['livreur_nom']}, {retard_str}.\n"
        f"Commentaire : {row['commentaire']}"
    )
    criticite = (
        "haute"
        if row["sentiment"] == "négatif"
        else "moyenne" if row["sentiment"] == "neutre" else "basse"
    )
    meta = {
        "source": "avis_clients",
        "topic": "avis_client",
        "type_event": row["sentiment"],
        "criticite": criticite,
        "zone": row["zone_nom"],
        "note": int(row["note"]),
    }
    return f"avis-{row['id']}", text, meta


def doc_restaurant(row: dict) -> tuple[str, str, dict]:
    n = row["nb_commandes_30j"] or 0
    taux_ann = (row["nb_annulees"] / n) if n else 0.0
    text = (
        f"Restaurant '{row['nom']}' (cuisine: {row['type_cuisine']}, zone: {row['zone_nom']}).\n"
        f"Sur les 30 derniers jours: {n} commandes, {row['nb_annulees']} annulées "
        f"({taux_ann*100:.1f}%), {row['nb_echouees']} échouées.\n"
        f"Note moyenne livreurs: {(row['note_moyenne_30j'] or 0):.2f}/5 — "
        f"Retard moyen: {(row['retard_moyen'] or 0):.1f} min — "
        f"Note référence: {(row['note_moyenne'] or 0):.2f}/5."
    )
    criticite = "haute" if taux_ann > 0.25 else "moyenne" if taux_ann > 0.1 else "basse"
    meta = {
        "source": "restaurants",
        "topic": "restaurant",
        "type_event": "snapshot",
        "criticite": criticite,
        "zone": row["zone_nom"],
    }
    return f"restaurant-{row['id']}", text, meta


def doc_zone(row: dict) -> tuple[str, str, dict]:
    n = row["nb_commandes_30j"] or 0
    taux_ann = (row["nb_annulees"] / n) if n else 0.0
    text = (
        f"Zone géographique: {row['nom']}.\n"
        f"30 derniers jours: {n} commandes, {row['nb_annulees']} annulées "
        f"({taux_ann*100:.1f}%).\n"
        f"Délai de livraison moyen: {(row['delai_moyen'] or 0):.1f} min — "
        f"Retard moyen: {(row['retard_moyen'] or 0):.1f} min — "
        f"Note moyenne livreurs: {(row['note_moyenne'] or 0):.2f}/5."
    )
    criticite = "haute" if (row["retard_moyen"] or 0) > 15 else "moyenne"
    meta = {
        "source": "zones",
        "topic": "zone",
        "type_event": "snapshot",
        "criticite": criticite,
        "zone": row["nom"],
    }
    return f"zone-{row['id']}", text, meta


def doc_synthese_incidents(rows: list[dict]) -> tuple[str, str, dict] | None:
    """Document récapitulatif : distribution des types et sévérités d'incidents (30j)."""
    if not rows:
        return None
    total = sum(r["n"] for r in rows)
    actifs = sum(r["n_actifs"] for r in rows)
    by_type: dict[str, int] = {}
    by_sev: dict[str, int] = {}
    for r in rows:
        by_type[r["type"]] = by_type.get(r["type"], 0) + r["n"]
        by_sev[r["severite"]] = by_sev.get(r["severite"], 0) + r["n"]

    types_lines = "\n".join(
        f"  - {t}: {n} incidents ({100*n/total:.1f}%)"
        for t, n in sorted(by_type.items(), key=lambda x: -x[1])
    )
    sev_lines = "\n".join(
        f"  - {s}: {n} incidents ({100*n/total:.1f}%)"
        for s, n in sorted(by_sev.items(), key=lambda x: -x[1])
    )
    text = (
        f"Synthèse des incidents, causes, facteurs et raisons des retards "
        f"sur les 30 derniers jours.\n"
        f"Total: {total} incidents — {actifs} encore actifs (non résolus).\n\n"
        f"CAUSES, FACTEURS ET RAISONS (types d'incidents par fréquence, "
        f"contribuant aux retards et problèmes) :\n{types_lines}\n\n"
        f"SÉVÉRITÉS (gravité des incidents) :\n{sev_lines}\n\n"
        f"Mots-clés : pourquoi, raisons, causes, facteurs, contribution, "
        f"explication, origine, source des problèmes."
    )
    meta = {
        "source": "synthese",
        "topic": "synthese_incidents",
        "type_event": "agregation",
        "criticite": "info",
        "zone": "all",
    }
    return "synthese-incidents", text, meta


def doc_top_restaurants(rows: list[dict]) -> tuple[str, str, dict] | None:
    if not rows:
        return None
    lines = []
    for i, r in enumerate(rows, 1):
        lines.append(
            f"  {i}. {r['nom']} (zone {r['zone_nom']}): {r['nb_commandes']} commandes, "
            f"{r['nb_annulees']} annulées, {r['nb_echouees']} échouées "
            f"({r['pct_problemes']}% de problèmes), retard moyen {(r['retard_moyen'] or 0):.1f} min."
        )
    text = (
        "Top 10 restaurants les plus problématiques sur les 30 derniers jours\n"
        "(classés par taux d'annulation+échec):\n\n" + "\n".join(lines)
    )
    meta = {
        "source": "synthese",
        "topic": "top_restaurants",
        "type_event": "agregation",
        "criticite": "haute",
        "zone": "all",
    }
    return "synthese-top-restaurants", text, meta


def doc_synthese_paiements(rows: list[dict]) -> tuple[str, str, dict] | None:
    if not rows:
        return None
    by_method: dict[str, dict] = {}
    for r in rows:
        m = r["methode_paiement"]
        by_method.setdefault(m, {}).update(
            {r["statut"]: r["n"], f"{r['statut']}_pct": r["pct_methode"]}
        )
    lines = []
    for m, data in by_method.items():
        total_m = sum(v for k, v in data.items() if not k.endswith("_pct"))
        echec = data.get("echouee", 0) + data.get("annulee", 0)
        pct_echec = 100 * echec / total_m if total_m else 0
        lines.append(
            f"  - {m}: {total_m} commandes, {echec} échecs/annulations ({pct_echec:.1f}%)"
        )
    text = (
        "Synthèse des paiements sur les 24 dernières heures, par méthode:\n"
        + "\n".join(lines)
    )
    meta = {
        "source": "synthese",
        "topic": "synthese_paiements",
        "type_event": "agregation",
        "criticite": "moyenne",
        "zone": "all",
    }
    return "synthese-paiements", text, meta


def doc_incidents_par_zone(rows: list[dict]) -> tuple[str, str, dict] | None:
    if not rows:
        return None
    by_zone: dict[str, list[tuple[str, int]]] = {}
    for r in rows:
        by_zone.setdefault(r["zone_nom"], []).append((r["type"], r["n"]))
    lines = []
    for zone, items in by_zone.items():
        types_str = ", ".join(f"{t}={n}" for t, n in items[:5])
        total_zone = sum(n for _, n in items)
        lines.append(f"  - {zone}: {total_zone} incidents — {types_str}")
    text = (
        "Répartition des incidents par zone sur les 30 derniers jours:\n"
        + "\n".join(lines)
    )
    meta = {
        "source": "synthese",
        "topic": "incidents_par_zone",
        "type_event": "agregation",
        "criticite": "info",
        "zone": "all",
    }
    return "synthese-incidents-par-zone", text, meta


def doc_tendance_volume(rows: list[dict]) -> tuple[str, str, dict] | None:
    if not rows:
        return None
    lines = []
    for r in rows[:14]:
        lines.append(
            f"  - {r['jour']}: {r['nb_commandes']} commandes, "
            f"{r['nb_annulees']} annulées, "
            f"note moy {(r['note_moyenne'] or 0):.2f}/5, "
            f"retard moy {(r['retard_moyen'] or 0):.1f} min"
        )
    text = (
        "Tendance journalière du volume sur les 14 derniers jours "
        "(le plus récent en premier):\n" + "\n".join(lines)
    )
    meta = {
        "source": "synthese",
        "topic": "tendance_volume",
        "type_event": "agregation",
        "criticite": "info",
        "zone": "all",
    }
    return "synthese-tendance-volume", text, meta


_KAFKA_TEMPLATES = {
    "incident_ouvert": (
        "Incident ouvert via Kafka — type {type}, sévérité {severite}, "
        "commande #{commande_id} en zone {zone}. {description}"
    ),
    "commande_creee": (
        "Nouvelle commande #{commande_id} créée en zone {zone}, "
        "restaurant {restaurant_nom}, montant {montant} DA, paiement {methode_paiement}."
    ),
    "commande_livree": (
        "Commande #{commande_id} livrée en zone {zone}, "
        "délai réel {delai_reel_min} min (estimé {delai_estime_min} min), "
        "note livreur {note_livreur}/5."
    ),
    "livraison_retardee": (
        "Livraison en retard — commande #{commande_id} en zone {zone}, "
        "retard {retard_min} min, livreur {livreur_nom}."
    ),
}


def doc_kafka_event(row: dict) -> tuple[str, str, dict] | None:
    """Convertit un événement Kafka en document texte indexable.

    Le template est choisi via ``event_type`` ; les champs manquants sont
    remplacés par 'N/A' pour ne jamais laisser 'None' dans le texte.
    """
    event_type = (row.get("event_type") or "").lower()
    template = _KAFKA_TEMPLATES.get(event_type)
    if not template:
        return None
    safe_row = {k: ("N/A" if v in (None, "") else v) for k, v in row.items()}
    try:
        text = template.format_map(_DefaultDict(safe_row))
    except Exception:
        return None
    criticite = row.get("severite") or (
        "haute" if (row.get("retard_min") or 0) > 30 else "moyenne"
    )
    doc_id = f"kafka-{row.get('_topic','x')}-{row.get('_partition',0)}-{row.get('_offset','?')}"
    meta = {
        "source": "kafka",
        "topic": row.get("_topic", "kafka"),
        "type_event": event_type,
        "criticite": criticite,
        "zone": row.get("zone", "all"),
    }
    return doc_id, text, meta


class _DefaultDict(dict):
    def __missing__(self, key: str) -> str:
        return "N/A"


def build_documents(
    extract_result: dict[str, list[dict]]
) -> tuple[list[str], list[str], list[dict]]:
    """Retourne (ids, textes, métadonnées) prêts pour Embedder + QdrantVectorStore.upsert."""
    ids: list[str] = []
    texts: list[str] = []
    metas: list[dict] = []

    # Documents par ligne
    per_row_builders = [
        ("incidents_actifs", doc_incident),
        ("avis_clients", doc_avis),
        ("commandes", doc_commande),
        ("restaurants", doc_restaurant),
        ("zones", doc_zone),
    ]
    for key, fn in per_row_builders:
        for row in extract_result.get(key, []):
            doc_id, text, meta = fn(row)
            ids.append(doc_id)
            texts.append(text)
            metas.append(meta)

    # Événements Kafka temps-réel
    for row in extract_result.get("kafka_events", []):
        result = doc_kafka_event(row)
        if result:
            doc_id, text, meta = result
            ids.append(doc_id)
            texts.append(text)
            metas.append(meta)

    # Documents agrégés (un seul doc par synthèse, contient toute l'info)
    aggregate_builders = [
        ("agg_incident_types", doc_synthese_incidents),
        ("agg_top_restaurants", doc_top_restaurants),
        ("agg_paiements", doc_synthese_paiements),
        ("agg_incidents_par_zone", doc_incidents_par_zone),
        ("agg_tendance_volume", doc_tendance_volume),
    ]
    for key, fn in aggregate_builders:
        result = fn(extract_result.get(key, []))
        if result:
            doc_id, text, meta = result
            ids.append(doc_id)
            texts.append(text)
            metas.append(meta)

    return ids, texts, metas
