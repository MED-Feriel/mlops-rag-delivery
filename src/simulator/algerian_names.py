"""
Noms et prénoms algériens — aucun nom Faker anglais/français.
50 prénoms hommes, 30 prénoms femmes, 50 noms famille, 40+ noms restaurants.
Mélange arabe classique + dialectal + quelques kabyles.
"""

import random

PRENOMS_HOMMES = [
    "Mohamed",
    "Ahmed",
    "Ali",
    "Youcef",
    "Karim",
    "Amine",
    "Mehdi",
    "Riad",
    "Sofiane",
    "Nassim",
    "Bilal",
    "Hamza",
    "Omar",
    "Abdelkader",
    "Rachid",
    "Fares",
    "Walid",
    "Samir",
    "Nadir",
    "Mourad",
    "Djamel",
    "Farid",
    "Redouane",
    "Hakim",
    "Nabil",
    "Khaled",
    "Toufik",
    "Brahim",
    "Lotfi",
    "Mounir",
    "Anis",
    "Ismail",
    "Yassine",
    "Abderrahmane",
    "Hichem",
    "Tarek",
    "Zouhir",
    "Azzedine",
    "Salim",
    "Raouf",
    "Lamine",
    "Adel",
    "Noureddine",
    "Said",
    "Mokrane",
    "Rafik",
    "Mustapha",
    "Djillali",
    "Bachir",
    "Slimane",
]

PRENOMS_FEMMES = [
    "Fatima",
    "Amina",
    "Sara",
    "Nour",
    "Yasmine",
    "Meriem",
    "Khadija",
    "Samira",
    "Lina",
    "Djamila",
    "Houria",
    "Nabila",
    "Siham",
    "Souad",
    "Rania",
    "Asma",
    "Imane",
    "Amel",
    "Wafa",
    "Farida",
    "Karima",
    "Zineb",
    "Lamia",
    "Hanane",
    "Naima",
    "Dalila",
    "Leila",
    "Malika",
    "Sabrina",
    "Aicha",
]

NOMS_FAMILLE = [
    "Benmoussa",
    "Khelifi",
    "Boudiaf",
    "Hadjadj",
    "Mebarki",
    "Belkacem",
    "Djebbar",
    "Ait Ahmed",
    "Zeroual",
    "Boussouf",
    "Benali",
    "Mansouri",
    "Bouazza",
    "Cherif",
    "Hamadi",
    "Tlemcani",
    "Sahraoui",
    "Mokhtari",
    "Guerroudj",
    "Benamar",
    "Ferhat",
    "Sellami",
    "Boudjelal",
    "Remili",
    "Kaci",
    "Ouahab",
    "Belaidi",
    "Meziane",
    "Amrouche",
    "Taleb",
    "Rahmani",
    "Bouchikhi",
    "Henni",
    "Ghezali",
    "Aoudia",
    "Mekideche",
    "Bahloul",
    "Lahouel",
    "Touati",
    "Saidani",
    "Benguedda",
    "Kermiche",
    "Guesmia",
    "Boualem",
    "Meghni",
    "Rebahi",
    "Chaouche",
    "Fenniche",
    "Abdessemed",
    "Berkani",
]

NOMS_RESTAURANTS_BASE = [
    "Chez El Hadj",
    "La Table de Dely",
    "El Baraka",
    "Le Palais d'Hydra",
    "Pizza Express Alger",
    "Grillade El Wiam",
    "El Djazair Food",
    "Chez Bouzid",
    "La Terrasse de Kouba",
    "El Safir Restaurant",
    "Tacos DZ",
    "Le Coin Gourmand",
    "Snack El Amir",
    "Restaurant El Moustakbal",
    "La Cuisine de Mama",
    "Fast Burger Alger",
    "Chez Mourad",
    "El Riadh Grillades",
    "Le Comptoir du Port",
    "Pizza du Sahel",
    "Chez Khadija",
    "El Nakhil",
    "La Brise de Mer",
    "Poulet Express DZ",
    "Chez Ahmed Grillades",
    "El Yasmine Resto",
    "Le Petit Algerois",
    "Chawarma House",
    "Chez Fatima",
    "El Kahwa",
    "Grillade de Bab Ezzouar",
    "La Table Kabyle",
    "Chez Omar",
    "El Bahdja Food",
    "Le Délice d'Alger",
    "Chez Rachid",
    "La Maison du Couscous",
    "El Fen Restaurant",
    "Pizzeria du Telemly",
    "Chez Samir Express",
]

_TEMPLATES = [
    "Chez {p}",
    "Restaurant {n}",
    "Grillade {n}",
    "El {a} Resto",
    "La Table de {z}",
    "Snack {p}",
    "{p} Express",
    "Pizzeria {z}",
    "Fast Food {z}",
    "Le Coin de {p}",
    "{p} & Fils",
    "El {a} Food",
]

_ADJECTIFS = [
    "Baraka",
    "Nour",
    "Salam",
    "Rahma",
    "Wiam",
    "Safir",
    "Djazair",
    "Bahdja",
    "Yasmine",
    "Riadh",
    "Amir",
    "Firdaws",
]


def random_nom_complet(genre: str = "homme") -> tuple[str, str]:
    prenom = random.choice(PRENOMS_FEMMES if genre == "femme" else PRENOMS_HOMMES)
    return prenom, random.choice(NOMS_FAMILLE)


def random_nom_restaurant(zone: str = "Alger", idx: int = 0) -> str:
    if idx < len(NOMS_RESTAURANTS_BASE):
        return NOMS_RESTAURANTS_BASE[idx]
    t = random.choice(_TEMPLATES)
    return t.format(
        p=random.choice(PRENOMS_HOMMES[:20]),
        n=random.choice(NOMS_FAMILLE[:20]),
        z=zone,
        a=random.choice(_ADJECTIFS),
    )


def random_telephone() -> str:
    prefix = random.choice(["05", "06", "07"])
    d = "".join(str(random.randint(0, 9)) for _ in range(8))
    return f"+213 {prefix}{d[:2]} {d[2:4]} {d[4:6]} {d[6:8]}"


def random_email(prenom: str, nom: str) -> str:
    domain = random.choice(["gmail.com", "outlook.com", "yahoo.fr", "hotmail.com"])
    return f"{prenom.lower()}.{nom.lower().replace(' ', '')}@{domain}"
