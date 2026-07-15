# Smart Home - Projet Flask

## Description

Smart Home est une application web Flask de gestion d'objets connectes pour une maison intelligente.

Le projet permet de :

- creer un compte utilisateur
- se connecter avec un email ou un nom d'utilisateur
- attendre la validation du compte par un administrateur
- afficher les objets connectes
- ajouter, modifier et supprimer des objets
- rechercher des objets avec des filtres
- controler certains objets comme une lampe, une TV ou un thermostat

L'application utilise Flask pour le backend, des templates HTML pour le frontend et SQLite pour la base de donnees.

## Fonctionnalites principales

### 1. Authentification

- inscription utilisateur
- connexion
- deconnexion
- validation des comptes par un admin

### 2. Securite du compte

L'inscription impose :

- un nom d'utilisateur unique
- un email valide
- un mot de passe fort

Le mot de passe doit contenir :

- au moins 8 caracteres
- au moins 1 majuscule
- au moins 1 minuscule
- au moins 1 chiffre
- au moins 1 caractere special

### 3. Gestion des objets

L'utilisateur connecte peut :

- voir tous les objets
- ajouter un objet
- modifier un objet
- supprimer un objet
- gerer un objet depuis une page de controle

### 4. Recherche et filtres

Le dashboard permet :

- une recherche texte
- un filtre par type
- un filtre par statut

Exemples de recherche :

- `thermostat actif`
- `lampe chambre`
- `tv salon`

### 5. Espace admin

L'administrateur peut :

- voir les comptes en attente
- valider les nouveaux comptes
- voir les utilisateurs deja valides
- suivre le nombre total d'objets

## Types d'objets supportes

Le projet prend en charge plusieurs types d'objets :

- thermostat
- lampe
- camera
- alarme
- prise
- capteur
- tv
- ventilateur
- enceinte
- serrure
- volet
- projecteur
- arrosage

## Exemples d'actions disponibles

Quelques comportements deja implementes :

- lampe : allumer / eteindre
- TV : allumer / eteindre
- thermostat : allumer / eteindre / temperature + / temperature -
- camera : activer / desactiver
- alarme : armer / desactiver
- ventilateur : demarrer / arreter
- enceinte : lancer la musique / couper la musique
- serrure : verrouiller / deverrouiller
- volet : ouvrir / fermer
- arrosage : lancer / couper l'arrosage

## Technologies utilisees

- Python
- Flask
- Werkzeug
- SQLite
- HTML / CSS

## Installation

### Prerequis

- Python 3
- pip

### Installation des dependances

```bash
pip install "Flask>=3.0,<4.0"
```

Flask installe aussi Werkzeug, utilise dans le projet pour le hash des mots de passe.

## Lancement du projet

Depuis le dossier du projet :

```bash
python app.py
```

Ensuite, ouvrir dans le navigateur :

```text
http://127.0.0.1:5000
```

## Compte administrateur par defaut

Le projet cree automatiquement un compte admin si besoin :

- email : `admin@smarthome.com`
- nom d'utilisateur : `admin`
- mot de passe : `Admin123!`

## Routes principales

- `/` : page d'accueil
- `/register` : inscription
- `/login` : connexion
- `/logout` : deconnexion
- `/dashboard` : affichage des objets
- `/add_object` : ajout d'objet
- `/edit_object/<id>` : modification d'objet
- `/delete_object/<id>` : suppression d'objet
- `/object/<id>` : page de gestion / controle d'un objet
- `/admin` : panneau administrateur
- `/admin/validate/<id>` : validation d'un compte utilisateur

## Base de donnees

La base utilise SQLite avec le fichier :

- `smart_home.db`

Le schema principal contient deux tables :

### Table `users`

- `id`
- `username`
- `email`
- `password`
- `role`
- `is_validated`

### Table `objects`

- `id`
- `name`
- `type`
- `status`
- `temperature`
- `room`

Le script de reference de la base est dans :

- `BD.sql`

## Objets d'exemple

Au demarrage, l'application ajoute automatiquement plusieurs objets d'exemple si besoin :

- Thermostat Salon
- Lampe Chambre
- Camera Entree
- TV Salon
- Ventilateur Bureau
- Serrure Porte Entree
- Enceinte Cuisine

## Structure du projet

```text
devweb/
|-- app.py
|-- BD.sql
|-- smart_home.db
|-- static/
|   |-- style.css
|   |-- tv_on.png
|   |-- tv_off.png
|   |-- remote.png
|-- templates/
|   |-- base.html
|   |-- home.html
|   |-- login.html
|   |-- register.html
|   |-- dashboard.html
|   |-- add_object.html
|   |-- edit_object.html
|   |-- control_object.html
|   |-- admin.html
```

## Fichiers importants

- `app.py` : logique Flask, routes, auth, validation admin, recherche et gestion des objets
- `BD.sql` : schema SQL de reference
- `smart_home.db` : base SQLite utilisee par l'application
- `templates/` : pages HTML
- `static/style.css` : style principal

## Parcours utilisateur typique

1. un utilisateur cree un compte via `/register`
2. l'admin se connecte et valide le compte dans `/admin`
3. l'utilisateur se connecte via `/login`
4. il accede au dashboard
5. il peut rechercher, filtrer, ajouter ou modifier des objets
6. il peut ouvrir la page d'un objet pour l'allumer, l'eteindre ou effectuer d'autres actions

## Remarques

- la base peut etre creee ou mise a jour automatiquement au lancement de l'application
- le projet contient encore quelques anciens templates historiques, mais les pages principales actuellement utilisees sont celles listees plus haut
- le fichier `Insertion.sql` correspond a un ancien jeu de donnees et ne reflete pas completement l'etat actuel du schema

## Auteur / contexte

Projet realise comme mini application de gestion d'une maison intelligente avec Flask, interface HTML/CSS et base SQLite.
