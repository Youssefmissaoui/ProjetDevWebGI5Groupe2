-- Création de la table des utilisateurs
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL, -- Le backend devra stocker un mot de passe haché
    role VARCHAR(20) DEFAULT 'user', -- Peut être 'user' ou 'admin'
    is_validated BOOLEAN DEFAULT 0 -- 0 (faux/en attente) ou 1 (vrai/validé)
);

-- Création de la table des objets connectés
CREATE TABLE objects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    type VARCHAR(50) NOT NULL, -- ex: thermostat, lampe, camera
    status BOOLEAN DEFAULT 1, -- 1 (actif) ou 0 (inactif)
    temperature FLOAT NULL, -- Peut être NULL si l'objet n'est pas un thermostat
    room VARCHAR(50) NOT NULL -- ex: Salon, Chambre, Entrée
);
