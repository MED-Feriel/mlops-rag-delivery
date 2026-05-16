-- Schéma livraison v2.0.0
-- DROP -> CREATE pour repartir propre à chaque appel à static_generator

DROP TABLE IF EXISTS incidents CASCADE;
DROP TABLE IF EXISTS commandes CASCADE;
DROP TABLE IF EXISTS clients CASCADE;
DROP TABLE IF EXISTS livreurs CASCADE;
DROP TABLE IF EXISTS restaurants CASCADE;
DROP TABLE IF EXISTS zones CASCADE;

CREATE TABLE zones (
    id SERIAL PRIMARY KEY,
    nom VARCHAR(100) NOT NULL UNIQUE,
    poids FLOAT NOT NULL
);

CREATE TABLE restaurants (
    id SERIAL PRIMARY KEY,
    nom VARCHAR(200) NOT NULL,
    zone_id INTEGER REFERENCES zones(id),
    type_cuisine VARCHAR(50),
    ouvert BOOLEAN DEFAULT TRUE,
    note_moyenne FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE livreurs (
    id SERIAL PRIMARY KEY,
    nom VARCHAR(200) NOT NULL,
    zone_principale_id INTEGER REFERENCES zones(id),
    statut VARCHAR(50) DEFAULT 'actif',
    note_moyenne FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE clients (
    id SERIAL PRIMARY KEY,
    nom VARCHAR(200) NOT NULL,
    zone_id INTEGER REFERENCES zones(id),
    telephone VARCHAR(30),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE commandes (
    id SERIAL PRIMARY KEY,
    restaurant_id INTEGER REFERENCES restaurants(id),
    livreur_id INTEGER REFERENCES livreurs(id),
    client_id INTEGER REFERENCES clients(id),
    zone_id INTEGER REFERENCES zones(id),
    montant FLOAT NOT NULL,
    statut VARCHAR(30) NOT NULL,
    methode_paiement VARCHAR(20),
    delai_estime_min INTEGER,
    delai_reel_min INTEGER,
    note_livreur FLOAT,
    commentaire TEXT,
    created_at TIMESTAMP NOT NULL,
    livre_at TIMESTAMP
);

CREATE TABLE incidents (
    id SERIAL PRIMARY KEY,
    commande_id INTEGER REFERENCES commandes(id),
    type VARCHAR(40) NOT NULL,
    severite VARCHAR(20) NOT NULL,
    description TEXT,
    resolu BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL,
    resolu_at TIMESTAMP
);

CREATE INDEX idx_commandes_created_at ON commandes(created_at);
CREATE INDEX idx_commandes_statut ON commandes(statut);
CREATE INDEX idx_commandes_zone ON commandes(zone_id);
CREATE INDEX idx_commandes_restaurant ON commandes(restaurant_id);
CREATE INDEX idx_incidents_resolu ON incidents(resolu);
CREATE INDEX idx_incidents_severite ON incidents(severite);
CREATE INDEX idx_incidents_created_at ON incidents(created_at);
