DROP TABLE IF EXISTS objects;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    is_validated INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE objects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'actif',
    temperature REAL,
    room TEXT NOT NULL
);

-- The Flask app creates the default admin account automatically:
-- email: admin@smarthome.com
-- password: Admin123!

INSERT INTO objects (name, type, status, temperature, room) VALUES
    ('Thermostat Salon', 'thermostat', 'actif', 21.5, 'Salon'),
    ('Lampe Chambre', 'lampe', 'inactif', NULL, 'Chambre'),
    ('Camera Entree', 'camera', 'actif', NULL, 'Entree'),
    ('TV Salon', 'tv', 'actif', NULL, 'Salon'),
    ('Ventilateur Bureau', 'ventilateur', 'inactif', NULL, 'Bureau'),
    ('Serrure Porte Entree', 'serrure', 'actif', NULL, 'Entree'),
    ('Enceinte Cuisine', 'enceinte', 'inactif', NULL, 'Cuisine');
