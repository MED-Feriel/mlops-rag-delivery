-- Schéma livraison v3.0.0
-- DROP -> CREATE pour repartir propre à chaque appel à static_generator.
-- Les IDs sont assignés par l'application (pas de SERIAL) pour permettre
-- aux 4 services d'émettre des events Kafka avec des commande_id corrects
-- avant l'INSERT final.

DROP TABLE IF EXISTS avis_clients CASCADE;
DROP TABLE IF EXISTS paiements CASCADE;
DROP TABLE IF EXISTS livraisons CASCADE;
DROP TABLE IF EXISTS incidents CASCADE;
DROP TABLE IF EXISTS commandes CASCADE;
DROP TABLE IF EXISTS clients CASCADE;
DROP TABLE IF EXISTS livreurs CASCADE;
DROP TABLE IF EXISTS restaurants CASCADE;
DROP TABLE IF EXISTS zones CASCADE;

CREATE TABLE zones (
    id INTEGER PRIMARY KEY,
    nom VARCHAR(100) NOT NULL UNIQUE,
    poids FLOAT NOT NULL,
    delai_extra_min INTEGER DEFAULT 0,
    lat FLOAT,
    lng FLOAT
);

CREATE TABLE restaurants (
    id INTEGER PRIMARY KEY,
    nom VARCHAR(200) NOT NULL,
    zone_id INTEGER REFERENCES zones(id),
    type_cuisine VARCHAR(50),
    ouvert BOOLEAN DEFAULT TRUE,
    note_moyenne FLOAT,
    categorie VARCHAR(30),
    heure_ouverture SMALLINT DEFAULT 10,
    heure_fermeture SMALLINT DEFAULT 23,
    telephone VARCHAR(20),
    delai_prep_moyen SMALLINT DEFAULT 15,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE livreurs (
    id INTEGER PRIMARY KEY,
    prenom VARCHAR(80),
    nom VARCHAR(120) NOT NULL,
    zone_principale_id INTEGER REFERENCES zones(id),
    statut VARCHAR(50) DEFAULT 'actif',
    note_moyenne FLOAT,
    telephone VARCHAR(40),
    vehicule_type VARCHAR(10) CHECK (vehicule_type IN ('moto','voiture','velo')),
    annee_experience SMALLINT DEFAULT 1,
    note_ponctualite NUMERIC(2,1) DEFAULT 4.0,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE clients (
    id INTEGER PRIMARY KEY,
    prenom VARCHAR(80),
    nom VARCHAR(120) NOT NULL,
    zone_id INTEGER REFERENCES zones(id),
    telephone VARCHAR(40),
    email VARCHAR(120),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE commandes (
    id INTEGER PRIMARY KEY,
    restaurant_id INTEGER REFERENCES restaurants(id),
    livreur_id INTEGER REFERENCES livreurs(id),
    client_id INTEGER REFERENCES clients(id),
    zone_id INTEGER REFERENCES zones(id),
    montant FLOAT NOT NULL,
    frais_livraison FLOAT DEFAULT 0,
    montant_total FLOAT NOT NULL,
    statut VARCHAR(30) NOT NULL,
    methode_paiement VARCHAR(20),
    delai_estime_min INTEGER,
    delai_reel_min INTEGER,
    note_livreur FLOAT,
    commentaire TEXT,
    canal_commande VARCHAR(15) CHECK (canal_commande IN ('app_mobile','web','telephone')),
    delai_preparation_reel_min SMALLINT,
    created_at TIMESTAMP NOT NULL,
    livre_at TIMESTAMP
);

CREATE TABLE livraisons (
    id INTEGER PRIMARY KEY,
    commande_id INTEGER REFERENCES commandes(id),
    livreur_id INTEGER REFERENCES livreurs(id),
    lat_depart FLOAT,
    lng_depart FLOAT,
    lat_arrivee FLOAT,
    lng_arrivee FLOAT,
    distance_km FLOAT,
    duree_trajet_estime_min INTEGER,
    duree_trajet_reel_min INTEGER,
    statut VARCHAR(30),
    created_at TIMESTAMP NOT NULL,
    terminee_at TIMESTAMP
);

CREATE TABLE paiements (
    id INTEGER PRIMARY KEY,
    commande_id INTEGER REFERENCES commandes(id),
    montant FLOAT NOT NULL,
    methode VARCHAR(20),
    statut VARCHAR(20),
    tentatives INTEGER DEFAULT 1,
    cause_echec VARCHAR(40),
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE incidents (
    id INTEGER PRIMARY KEY,
    commande_id INTEGER REFERENCES commandes(id),
    type VARCHAR(40) NOT NULL,
    severite VARCHAR(20) NOT NULL,
    description TEXT,
    resolu BOOLEAN DEFAULT FALSE,
    source_service VARCHAR(40),
    created_at TIMESTAMP NOT NULL,
    resolu_at TIMESTAMP
);

CREATE TABLE avis_clients (
    id INTEGER PRIMARY KEY,
    commande_id INTEGER REFERENCES commandes(id),
    note INTEGER,
    commentaire TEXT,
    sentiment VARCHAR(20),
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_commandes_created_at ON commandes(created_at);
CREATE INDEX idx_commandes_statut ON commandes(statut);
CREATE INDEX idx_commandes_zone ON commandes(zone_id);
CREATE INDEX idx_commandes_restaurant ON commandes(restaurant_id);
CREATE INDEX idx_livraisons_commande ON livraisons(commande_id);
CREATE INDEX idx_paiements_commande ON paiements(commande_id);
CREATE INDEX idx_paiements_statut ON paiements(statut);
CREATE INDEX idx_incidents_resolu ON incidents(resolu);
CREATE INDEX idx_incidents_severite ON incidents(severite);
CREATE INDEX idx_incidents_created_at ON incidents(created_at);
CREATE INDEX idx_incidents_type ON incidents(type);
CREATE INDEX idx_avis_commande ON avis_clients(commande_id);
CREATE INDEX idx_avis_sentiment ON avis_clients(sentiment);
