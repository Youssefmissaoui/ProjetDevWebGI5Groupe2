-- Ajout de quelques utilisateurs pour tester le login et la validation admin
INSERT INTO users (username, password, role, is_validated) VALUES 
('admin', 'hash_du_mot_de_passe', 'admin', 1),
('test_user', 'hash_du_mot_de_passe', 'user', 0); -- Compte en attente de validation

-- Ajout des objets demandés
INSERT INTO objects (name, type, status, temperature, room) VALUES 
('Thermostat Salon', 'thermostat', 1, 22.5, 'Salon'),
('Lampe Chambre', 'lampe', 0, NULL, 'Chambre'),
('Caméra Entrée', 'camera', 1, NULL, 'Entrée');

-- Quelques objets supplémentaires pour bien tester la barre de recherche et les filtres
INSERT INTO objects (name, type, status, temperature, room) VALUES 
('Lumière Plafond', 'lampe', 1, NULL, 'Salon'),
('Thermostat Chambre', 'thermostat', 0, 19.0, 'Chambre');