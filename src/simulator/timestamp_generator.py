"""
Génération des timestamps de commandes — distribution bimodale (déjeuner + dîner)
× facteur jour de la semaine × facteur saison (été ×1.30, autres ×1.0).
"""

import random
from datetime import datetime, timedelta, timezone
from typing import Generator

import numpy as np


JOURS_SEMAINE = [
    "lundi",
    "mardi",
    "mercredi",
    "jeudi",
    "vendredi",
    "samedi",
    "dimanche",
]


def generate_timestamps(
    config: dict,
    jours_override: int | None = None,
) -> Generator[datetime, None, None]:
    """
    Génère des timestamps répartis sur `volume.jours_historique` jours
    (ou `jours_override` si fourni) suivant :
      - bimodale 11h30-14h (déjeuner) + 19h-21h30 (dîner)
      - facteur jour de la semaine (jeudi +37.5%, vendredi -30%)
      - facteur été (juil-aoû-sep +30%)
    Le nombre exact dépend de ces facteurs ; ±10% du nominal attendu.
    """
    nb_jours = (
        jours_override
        if jours_override is not None
        else config["volume"]["jours_historique"]
    )
    nb_par_jour = config["volume"]["nb_commandes_par_jour"]
    temporal = config["temporal"]
    start_date = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(days=nb_jours)

    for day_offset in range(nb_jours):
        current_date = start_date + timedelta(days=day_offset)
        jour_nom = JOURS_SEMAINE[current_date.weekday()]
        facteur_jour = temporal["facteur_jour"].get(jour_nom, 1.0)

        mois = current_date.month
        facteur_saison = 1.0
        if mois in temporal.get("saison_ete", {}).get("mois", []):
            facteur_saison = temporal["saison_ete"]["facteur"]

        nb_commandes_jour = int(nb_par_jour * facteur_jour * facteur_saison)

        pic_dej = temporal["pic_dejeuner"]
        pic_din = temporal["pic_diner"]
        mid_dej = (pic_dej["debut"] + pic_dej["fin"]) / 2
        mid_din = (pic_din["debut"] + pic_din["fin"]) / 2

        heures = []
        for _ in range(nb_commandes_jour):
            if random.random() < 0.55:  # 55% au dîner
                h = float(np.random.normal(mid_din, 0.8))
            else:
                h = float(np.random.normal(mid_dej, 0.7))
            h = max(7.0, min(23.5, h))
            heures.append(h)

        heures.sort()
        for h in heures:
            hh = int(h)
            mm = int((h - hh) * 60)
            ss = random.randint(0, 59)
            yield current_date.replace(hour=hh, minute=mm, second=ss)
