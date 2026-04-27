import sqlite3
import time
import unicodedata
from functools import wraps
from pathlib import Path
import re

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = "smart-home-secret-2026"

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "smart_home.db"
ADMIN_EMAIL = "admin@smarthome.com"
EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

DEFAULT_OBJECT_TYPES = [
    "thermostat",
    "lampe",
    "camera",
    "alarme",
    "prise",
    "capteur",
    "tv",
    "ventilateur",
    "enceinte",
    "serrure",
    "volet",
    "projecteur",
    "arrosage",
]

TYPE_LABELS = {
    "thermostat": "Thermostat",
    "lampe": "Lampe",
    "camera": "Camera",
    "alarme": "Alarme",
    "prise": "Prise",
    "capteur": "Capteur",
    "tv": "TV",
    "ventilateur": "Ventilateur",
    "enceinte": "Enceinte",
    "serrure": "Serrure connectee",
    "volet": "Volet roulant",
    "projecteur": "Projecteur",
    "arrosage": "Arrosage automatique",
    "light": "Lampe",
    "door": "Porte",
    "window": "Fenetre",
    "vacuum": "Aspirateur",
    "oven": "Four",
    "washing_machine": "Machine a laver",
    "fridge": "Refrigerateur",
    "coffee_machine": "Machine a cafe",
}

LEGACY_TYPE_MAP = {
    "light": "lampe",
    "door": "porte",
    "window": "fenetre",
}

STATUS_OPTIONS = ["actif", "inactif"]


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def normalize_text(value):
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    without_accents = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return without_accents.lower().strip()


def normalize_status_value(value):
    token = normalize_text(value)
    if token in {"1", "true", "actif", "on", "active"}:
        return "actif"
    return "inactif"


def type_label(value):
    if not value:
        return "Objet"
    return TYPE_LABELS.get(value, value.replace("_", " ").title())


def is_valid_email(email):
    return bool(EMAIL_REGEX.fullmatch(email or ""))


def password_is_valid(password):
    if len(password) < 8:
        return False, "Le mot de passe doit contenir au moins 8 caracteres."
    if not re.search(r"[A-Z]", password):
        return False, "Le mot de passe doit contenir au moins une majuscule."
    if not re.search(r"[a-z]", password):
        return False, "Le mot de passe doit contenir au moins une minuscule."
    if not re.search(r"\d", password):
        return False, "Le mot de passe doit contenir au moins un chiffre."
    if not re.search(r"[^A-Za-z0-9]", password):
        return False, "Le mot de passe doit contenir au moins un caractere special."
    return True, ""


def build_placeholder_email(username, user_id):
    safe_username = re.sub(r"[^a-z0-9]+", "", normalize_text(username))
    if not safe_username:
        safe_username = "user"
    return f"{safe_username}{user_id}@legacy.local"


def table_exists(conn, table_name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def table_columns(conn, table_name):
    rows = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    return [row["name"] for row in rows]


def rename_legacy_table(conn, table_name):
    legacy_name = f"{table_name}_legacy_{int(time.time())}"
    conn.execute(f'ALTER TABLE "{table_name}" RENAME TO "{legacy_name}"')


def ensure_expected_schema(conn):
    required_users = {"id", "username", "email", "password", "role", "is_validated"}
    required_objects = {"id", "name", "type", "status", "temperature", "room"}

    if table_exists(conn, "users"):
        user_columns = set(table_columns(conn, "users"))
        legacy_user_columns = {"id", "username", "password", "role", "is_validated"}

        if required_users.issubset(user_columns):
            pass
        elif legacy_user_columns.issubset(user_columns):
            conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
            rows = conn.execute(
                "SELECT id, username, role FROM users ORDER BY id ASC"
            ).fetchall()
            admin_email_assigned = False

            for row in rows:
                is_admin_row = row["role"] == "admin" or row["username"] == "admin"
                if is_admin_row and not admin_email_assigned:
                    email = ADMIN_EMAIL
                    admin_email_assigned = True
                else:
                    email = build_placeholder_email(row["username"], row["id"])
                conn.execute(
                    "UPDATE users SET email = ? WHERE id = ?",
                    (email, row["id"]),
                )
        else:
            rename_legacy_table(conn, "users")

    if table_exists(conn, "objects"):
        if not required_objects.issubset(set(table_columns(conn, "objects"))):
            rename_legacy_table(conn, "objects")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            is_validated INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'actif',
            temperature REAL,
            room TEXT NOT NULL
        )
        """
    )

    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)"
    )


def ensure_default_admin(conn):
    admin = conn.execute(
        """
        SELECT id
        FROM users
        WHERE username = ? OR email = ? OR role = 'admin'
        ORDER BY id ASC
        LIMIT 1
        """,
        ("admin", ADMIN_EMAIL),
    ).fetchone()

    if admin:
        conn.execute(
            """
            UPDATE users
            SET username = ?, email = ?, role = 'admin', is_validated = 1
            WHERE id = ?
            """,
            ("admin", ADMIN_EMAIL, admin["id"]),
        )
        return

    conn.execute(
        """
        INSERT INTO users (username, email, password, role, is_validated)
        VALUES (?, ?, ?, 'admin', 1)
        """,
        ("admin", ADMIN_EMAIL, generate_password_hash("Admin123!")),
    )


def migrate_legacy_devices(conn):
    if not table_exists(conn, "devices"):
        return

    objects_count = conn.execute("SELECT COUNT(*) AS total FROM objects").fetchone()["total"]
    if objects_count:
        return

    legacy_rows = conn.execute(
        """
        SELECT name, type, location, power_state, primary_value
        FROM devices
        ORDER BY id ASC
        """
    ).fetchall()

    for row in legacy_rows:
        object_type = LEGACY_TYPE_MAP.get(row["type"], row["type"])
        status = normalize_status_value(row["power_state"])
        temperature = row["primary_value"] if object_type == "thermostat" else None

        conn.execute(
            """
            INSERT INTO objects (name, type, status, temperature, room)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                row["name"],
                object_type,
                status,
                temperature,
                row["location"],
            ),
        )


def ensure_sample_objects(conn):
    sample_objects = [
        {
            "name": "Thermostat Salon",
            "type": "thermostat",
            "status": "actif",
            "temperature": 21.5,
            "room": "Salon",
        },
        {
            "name": "Lampe Chambre",
            "type": "lampe",
            "status": "inactif",
            "temperature": None,
            "room": "Chambre",
        },
        {
            "name": "Camera Entree",
            "type": "camera",
            "status": "actif",
            "temperature": None,
            "room": "Entree",
        },
        {
            "name": "TV Salon",
            "type": "tv",
            "status": "actif",
            "temperature": None,
            "room": "Salon",
        },
        {
            "name": "Ventilateur Bureau",
            "type": "ventilateur",
            "status": "inactif",
            "temperature": None,
            "room": "Bureau",
        },
        {
            "name": "Serrure Porte Entree",
            "type": "serrure",
            "status": "actif",
            "temperature": None,
            "room": "Entree",
        },
        {
            "name": "Enceinte Cuisine",
            "type": "enceinte",
            "status": "inactif",
            "temperature": None,
            "room": "Cuisine",
        },
    ]

    for sample in sample_objects:
        existing = conn.execute(
            "SELECT id FROM objects WHERE lower(name) = lower(?)",
            (sample["name"],),
        ).fetchone()
        if existing:
            continue

        conn.execute(
            """
            INSERT INTO objects (name, type, status, temperature, room)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                sample["name"],
                sample["type"],
                sample["status"],
                sample["temperature"],
                sample["room"],
            ),
        )


def serialize_object(row):
    temperature = row["temperature"]
    if temperature in ("", None):
        parsed_temperature = None
    else:
        try:
            parsed_temperature = float(temperature)
        except (TypeError, ValueError):
            parsed_temperature = None

    return {
        "id": row["id"],
        "name": row["name"],
        "type": row["type"],
        "status": normalize_status_value(row["status"]),
        "temperature": parsed_temperature,
        "room": row["room"],
    }


def fetch_object_by_id(conn, object_id):
    row = conn.execute(
        "SELECT * FROM objects WHERE id = ?",
        (object_id,),
    ).fetchone()
    if not row:
        return None
    return serialize_object(row)


def get_available_object_types(conn, current_type=""):
    types = list(DEFAULT_OBJECT_TYPES)
    rows = conn.execute(
        """
        SELECT DISTINCT type
        FROM objects
        WHERE type IS NOT NULL AND type <> ''
        ORDER BY type ASC
        """
    ).fetchall()

    for row in rows:
        value = row["type"].strip()
        if value and value not in types:
            types.append(value)

    if current_type and current_type not in types:
        types.append(current_type)

    return types


def object_matches_search(object_data, search_text):
    tokens = [normalize_text(part) for part in search_text.split() if part.strip()]
    if not tokens:
        return True

    haystack = " ".join(
        [
            object_data["name"],
            object_data["type"],
            type_label(object_data["type"]),
            object_data["room"],
            object_data["status"],
        ]
    )
    normalized_haystack = normalize_text(haystack)
    return all(token in normalized_haystack for token in tokens)


def list_objects(conn, search_text="", type_filter="", status_filter=""):
    rows = conn.execute("SELECT * FROM objects ORDER BY id DESC").fetchall()
    objects = [serialize_object(row) for row in rows]

    normalized_type_filter = normalize_text(type_filter)
    normalized_status_filter = normalize_text(status_filter)

    if normalized_type_filter:
        objects = [
            object_data
            for object_data in objects
            if normalize_text(object_data["type"]) == normalized_type_filter
        ]

    if normalized_status_filter:
        objects = [
            object_data
            for object_data in objects
            if normalize_text(object_data["status"]) == normalized_status_filter
        ]

    if search_text:
        objects = [
            object_data
            for object_data in objects
            if object_matches_search(object_data, search_text)
        ]

    return objects


def get_object_state_label(object_data):
    object_type = normalize_text(object_data["type"])
    is_active = object_data["status"] == "actif"

    if object_type == "lampe":
        return "Allumee" if is_active else "Eteinte"
    if object_type == "tv":
        return "Allumee" if is_active else "Eteinte"
    if object_type == "camera":
        return "Active" if is_active else "Inactive"
    if object_type == "alarme":
        return "Armee" if is_active else "Desactivee"
    if object_type == "prise":
        return "Sous tension" if is_active else "Coupee"
    if object_type == "capteur":
        return "En surveillance" if is_active else "En veille"
    if object_type == "ventilateur":
        return "En marche" if is_active else "Arrete"
    if object_type == "enceinte":
        return "En lecture" if is_active else "Silencieuse"
    if object_type == "serrure":
        return "Verrouillee" if is_active else "Deverrouillee"
    if object_type == "volet":
        return "Ouvert" if is_active else "Ferme"
    if object_type == "projecteur":
        return "En projection" if is_active else "Eteint"
    if object_type == "arrosage":
        return "Arrosage actif" if is_active else "Arroseur coupe"
    if object_type == "thermostat":
        return "En marche" if is_active else "Arrete"
    return "Actif" if is_active else "Inactif"


def get_object_actions(object_data):
    object_type = normalize_text(object_data["type"])
    is_active = object_data["status"] == "actif"

    if object_type == "thermostat":
        actions = [
            {
                "value": "turn_off" if is_active else "turn_on",
                "label": "Eteindre" if is_active else "Allumer",
                "class": "btn-danger" if is_active else "btn-success",
            }
        ]
        if is_active:
            actions.extend(
                [
                    {
                        "value": "temp_up",
                        "label": "Temperature +",
                        "class": "btn-primary",
                    },
                    {
                        "value": "temp_down",
                        "label": "Temperature -",
                        "class": "btn-secondary",
                    },
                ]
            )
        return actions

    if object_type == "lampe":
        return [
            {
                "value": "turn_off" if is_active else "turn_on",
                "label": "Eteindre" if is_active else "Allumer",
                "class": "btn-danger" if is_active else "btn-success",
            }
        ]

    if object_type == "tv":
        return [
            {
                "value": "turn_off" if is_active else "turn_on",
                "label": "Eteindre la TV" if is_active else "Allumer la TV",
                "class": "btn-danger" if is_active else "btn-success",
            }
        ]

    if object_type == "camera":
        return [
            {
                "value": "deactivate" if is_active else "activate",
                "label": "Desactiver" if is_active else "Activer",
                "class": "btn-danger" if is_active else "btn-success",
            }
        ]

    if object_type == "alarme":
        return [
            {
                "value": "disarm" if is_active else "arm",
                "label": "Desactiver" if is_active else "Armer",
                "class": "btn-danger" if is_active else "btn-success",
            }
        ]

    if object_type == "prise":
        return [
            {
                "value": "turn_off" if is_active else "turn_on",
                "label": "Couper" if is_active else "Alimenter",
                "class": "btn-danger" if is_active else "btn-success",
            }
        ]

    if object_type == "ventilateur":
        return [
            {
                "value": "turn_off" if is_active else "turn_on",
                "label": "Arreter" if is_active else "Demarrer",
                "class": "btn-danger" if is_active else "btn-success",
            }
        ]

    if object_type == "enceinte":
        return [
            {
                "value": "stop_playback" if is_active else "play",
                "label": "Couper la musique" if is_active else "Lancer la musique",
                "class": "btn-danger" if is_active else "btn-success",
            }
        ]

    if object_type == "serrure":
        return [
            {
                "value": "unlock" if is_active else "lock",
                "label": "Deverrouiller" if is_active else "Verrouiller",
                "class": "btn-danger" if is_active else "btn-success",
            }
        ]

    if object_type == "volet":
        return [
            {
                "value": "close" if is_active else "open",
                "label": "Fermer" if is_active else "Ouvrir",
                "class": "btn-danger" if is_active else "btn-success",
            }
        ]

    if object_type == "projecteur":
        return [
            {
                "value": "turn_off" if is_active else "turn_on",
                "label": "Eteindre le projecteur" if is_active else "Allumer le projecteur",
                "class": "btn-danger" if is_active else "btn-success",
            }
        ]

    if object_type == "arrosage":
        return [
            {
                "value": "stop_watering" if is_active else "start_watering",
                "label": "Couper l'arrosage" if is_active else "Lancer l'arrosage",
                "class": "btn-danger" if is_active else "btn-success",
            }
        ]

    return [
        {
            "value": "deactivate" if is_active else "activate",
            "label": "Desactiver" if is_active else "Activer",
            "class": "btn-danger" if is_active else "btn-success",
        }
    ]


def apply_object_action(object_data, action):
    updated_object = dict(object_data)
    object_type = normalize_text(object_data["type"])

    if action in {"turn_on", "activate", "arm", "lock", "open", "play", "start_watering"}:
        updated_object["status"] = "actif"
        if object_type == "thermostat" and updated_object["temperature"] is None:
            updated_object["temperature"] = 20.0
        return updated_object, None

    if action in {"turn_off", "deactivate", "disarm", "unlock", "close", "stop_playback", "stop_watering"}:
        updated_object["status"] = "inactif"
        return updated_object, None

    if action == "temp_up":
        if object_type != "thermostat":
            return None, "Seul un thermostat peut changer de temperature."
        if updated_object["status"] != "actif":
            return None, "Allumez le thermostat avant de regler la temperature."

        current_temperature = updated_object["temperature"]
        if current_temperature is None:
            current_temperature = 20.0

        updated_object["temperature"] = min(35.0, round(current_temperature + 0.5, 1))
        return updated_object, None

    if action == "temp_down":
        if object_type != "thermostat":
            return None, "Seul un thermostat peut changer de temperature."
        if updated_object["status"] != "actif":
            return None, "Allumez le thermostat avant de regler la temperature."

        current_temperature = updated_object["temperature"]
        if current_temperature is None:
            current_temperature = 20.0

        updated_object["temperature"] = max(5.0, round(current_temperature - 0.5, 1))
        return updated_object, None

    return None, "Action non prise en charge pour cet objet."


def validate_object_form(form_data):
    name = form_data.get("name", "").strip()
    object_type = form_data.get("type", "").strip().lower()
    status = normalize_status_value(form_data.get("status", ""))
    room = form_data.get("room", "").strip()
    temperature_raw = form_data.get("temperature", "").strip()

    if not name or not object_type or not room:
        return None, "Tous les champs obligatoires doivent etre remplis."

    if status not in STATUS_OPTIONS:
        return None, "Le statut choisi est invalide."

    temperature = None
    if object_type == "thermostat":
        if not temperature_raw:
            return None, "La temperature est obligatoire pour un thermostat."
        try:
            temperature = float(temperature_raw.replace(",", "."))
        except ValueError:
            return None, "La temperature doit etre un nombre valide."
    elif temperature_raw:
        try:
            temperature = float(temperature_raw.replace(",", "."))
        except ValueError:
            return None, "La temperature doit etre un nombre valide."

    return {
        "name": name,
        "type": object_type,
        "status": status,
        "temperature": temperature,
        "room": room,
    }, None


def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            flash("Connectez-vous pour acceder a cette page.", "error")
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)

    return wrapped_view


def admin_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            flash("Connectez-vous pour acceder a cette page.", "error")
            return redirect(url_for("login"))

        if session.get("role") != "admin":
            flash("Acces reserve a l administrateur.", "error")
            return redirect(url_for("dashboard"))
        return view_func(*args, **kwargs)

    return wrapped_view


@app.template_filter("type_label")
def type_label_filter(value):
    return type_label(value)


@app.route("/")
def home():
    if session.get("user_id"):
        if session.get("role") == "admin":
            return redirect(url_for("admin"))
        return redirect(url_for("dashboard"))
    return render_template("home.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        form_data = {"username": username, "email": email}

        if not username or not email or not password or not confirm_password:
            flash("Tous les champs sont obligatoires.", "error")
            return render_template("register.html", form_data=form_data)

        if len(username) < 3 or " " in username:
            flash("Le nom d utilisateur doit contenir au moins 3 caracteres sans espace.", "error")
            return render_template("register.html", form_data=form_data)

        if not is_valid_email(email):
            flash("Entrez une adresse email valide.", "error")
            return render_template("register.html", form_data=form_data)

        valid_password, password_message = password_is_valid(password)
        if not valid_password:
            flash(password_message, "error")
            return render_template("register.html", form_data=form_data)

        if password != confirm_password:
            flash("Les deux mots de passe ne correspondent pas.", "error")
            return render_template("register.html", form_data=form_data)

        conn = get_db_connection()
        try:
            existing_username = conn.execute(
                "SELECT id FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            existing_email = conn.execute(
                "SELECT id FROM users WHERE lower(email) = ?",
                (email,),
            ).fetchone()

            if existing_username:
                flash("Ce nom d utilisateur existe deja.", "error")
                return render_template("register.html", form_data=form_data)

            if existing_email:
                flash("Cette adresse email existe deja.", "error")
                return render_template("register.html", form_data=form_data)

            conn.execute(
                """
                INSERT INTO users (username, email, password, role, is_validated)
                VALUES (?, ?, ?, 'user', 0)
                """,
                (username, email, generate_password_hash(password)),
            )
            conn.commit()
        finally:
            conn.close()

        flash("Compte cree. Un admin doit maintenant le valider.", "success")
        return redirect(url_for("login"))

    return render_template("register.html", form_data={})


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        identifier = request.form.get("email", "").strip()
        normalized_identifier = identifier.lower()
        password = request.form.get("password", "")

        conn = get_db_connection()
        try:
            user = conn.execute(
                """
                SELECT *
                FROM users
                WHERE lower(email) = ? OR lower(username) = ?
                """,
                (normalized_identifier, normalized_identifier),
            ).fetchone()
        finally:
            conn.close()

        if not user or not check_password_hash(user["password"], password):
            flash("Email ou mot de passe incorrect.", "error")
            return render_template("login.html", email=identifier)

        if user["role"] != "admin" and not int(user["is_validated"]):
            flash("Votre compte doit etre valide par un admin avant la connexion.", "error")
            return render_template("login.html", email=identifier)

        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["email"] = user["email"]
        session["role"] = user["role"]
        session["is_validated"] = int(user["is_validated"])

        if user["role"] == "admin":
            return redirect(url_for("admin"))
        return redirect(url_for("dashboard"))

    return render_template("login.html", email="")


@app.route("/logout")
def logout():
    session.clear()
    flash("Deconnexion reussie.", "success")
    return redirect(url_for("home"))


@app.route("/dashboard")
@login_required
def dashboard():
    search_text = request.args.get("search", "").strip()
    type_filter = request.args.get("type", "").strip()
    status_filter = request.args.get("status", "").strip()

    conn = get_db_connection()
    try:
        objects = list_objects(conn, search_text, type_filter, status_filter)
        object_types = get_available_object_types(conn)
    finally:
        conn.close()

    active_count = sum(1 for object_data in objects if object_data["status"] == "actif")
    inactive_count = sum(1 for object_data in objects if object_data["status"] == "inactif")

    return render_template(
        "dashboard.html",
        objects=objects,
        object_types=object_types,
        search_text=search_text,
        type_filter=type_filter,
        status_filter=status_filter,
        active_count=active_count,
        inactive_count=inactive_count,
    )


@app.route("/add_object", methods=["GET", "POST"])
@app.route("/admin/add-device", methods=["GET", "POST"])
@login_required
def add_object():
    conn = get_db_connection()
    try:
        object_types = get_available_object_types(conn)

        if request.method == "POST":
            object_data, error_message = validate_object_form(request.form)
            if error_message:
                flash(error_message, "error")
                return render_template(
                    "add_object.html",
                    object_types=object_types,
                    form_data=request.form,
                )

            conn.execute(
                """
                INSERT INTO objects (name, type, status, temperature, room)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    object_data["name"],
                    object_data["type"],
                    object_data["status"],
                    object_data["temperature"],
                    object_data["room"],
                ),
            )
            conn.commit()

            flash("Objet ajoute avec succes.", "success")
            return redirect(url_for("dashboard"))
    finally:
        conn.close()

    return render_template("add_object.html", object_types=object_types, form_data={})


@app.route("/edit_object/<int:object_id>", methods=["GET", "POST"])
@app.route("/admin/edit-device/<int:object_id>", methods=["GET", "POST"])
@login_required
def edit_object(object_id):
    conn = get_db_connection()
    try:
        object_data = fetch_object_by_id(conn, object_id)
        if not object_data:
            flash("Objet introuvable.", "error")
            return redirect(url_for("dashboard"))

        object_types = get_available_object_types(conn, object_data["type"])

        if request.method == "POST":
            updated_object, error_message = validate_object_form(request.form)
            if error_message:
                flash(error_message, "error")
                fallback_object = {
                    "id": object_id,
                    "name": request.form.get("name", "").strip(),
                    "type": request.form.get("type", "").strip().lower(),
                    "status": normalize_status_value(request.form.get("status", "")),
                    "temperature": request.form.get("temperature", "").strip(),
                    "room": request.form.get("room", "").strip(),
                }
                return render_template(
                    "edit_object.html",
                    object_data=fallback_object,
                    object_types=object_types,
                )

            conn.execute(
                """
                UPDATE objects
                SET name = ?, type = ?, status = ?, temperature = ?, room = ?
                WHERE id = ?
                """,
                (
                    updated_object["name"],
                    updated_object["type"],
                    updated_object["status"],
                    updated_object["temperature"],
                    updated_object["room"],
                    object_id,
                ),
            )
            conn.commit()

            flash("Objet modifie avec succes.", "success")
            return redirect(url_for("dashboard"))
    finally:
        conn.close()

    return render_template(
        "edit_object.html",
        object_data=object_data,
        object_types=object_types,
    )


@app.route("/delete_object/<int:object_id>", methods=["POST"])
@app.route("/admin/delete-device/<int:object_id>", methods=["POST"])
@login_required
def delete_object(object_id):
    conn = get_db_connection()
    try:
        deleted = conn.execute(
            "DELETE FROM objects WHERE id = ?",
            (object_id,),
        )
        conn.commit()
        deleted_rows = deleted.rowcount
    finally:
        conn.close()

    if deleted_rows:
        flash("Objet supprime avec succes.", "success")
    else:
        flash("Objet introuvable.", "error")
    return redirect(url_for("dashboard"))


@app.route("/object/<int:object_id>", methods=["GET", "POST"])
@app.route("/device/<int:object_id>", methods=["GET", "POST"])
@login_required
def control_object(object_id):
    conn = get_db_connection()
    try:
        object_data = fetch_object_by_id(conn, object_id)
        if not object_data:
            flash("Objet introuvable.", "error")
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            action = request.form.get("action", "").strip()
            updated_object, error_message = apply_object_action(object_data, action)

            if error_message:
                flash(error_message, "error")
            else:
                conn.execute(
                    """
                    UPDATE objects
                    SET status = ?, temperature = ?
                    WHERE id = ?
                    """,
                    (
                        updated_object["status"],
                        updated_object["temperature"],
                        object_id,
                    ),
                )
                conn.commit()
                flash("Action appliquee avec succes.", "success")

            return redirect(url_for("control_object", object_id=object_id))
    finally:
        conn.close()

    return render_template(
        "control_object.html",
        object_data=object_data,
        state_label=get_object_state_label(object_data),
        actions=get_object_actions(object_data),
    )


@app.route("/admin")
@admin_required
def admin():
    conn = get_db_connection()
    try:
        pending_users = conn.execute(
            """
            SELECT id, username, email, role, is_validated
            FROM users
            WHERE role = 'user' AND is_validated = 0
            ORDER BY id DESC
            """
        ).fetchall()

        validated_users = conn.execute(
            """
            SELECT id, username, email, role, is_validated
            FROM users
            WHERE role = 'user' AND is_validated = 1
            ORDER BY id DESC
            """
        ).fetchall()

        total_objects = conn.execute(
            "SELECT COUNT(*) AS total FROM objects"
        ).fetchone()["total"]
    finally:
        conn.close()

    return render_template(
        "admin.html",
        pending_users=pending_users,
        validated_users=validated_users,
        total_objects=total_objects,
    )


@app.route("/admin/validate/<int:user_id>", methods=["POST"])
@app.route("/admin/approve/<int:user_id>", methods=["POST"])
@admin_required
def validate_user(user_id):
    conn = get_db_connection()
    try:
        result = conn.execute(
            """
            UPDATE users
            SET is_validated = 1
            WHERE id = ? AND role = 'user'
            """,
            (user_id,),
        )
        conn.commit()
    finally:
        conn.close()

    if result.rowcount:
        flash("Compte valide avec succes.", "success")
    else:
        flash("Utilisateur introuvable.", "error")
    return redirect(url_for("admin"))


def init_db():
    conn = get_db_connection()
    try:
        ensure_expected_schema(conn)
        ensure_default_admin(conn)
        migrate_legacy_devices(conn)
        ensure_sample_objects(conn)
        conn.commit()
    finally:
        conn.close()


init_db()


if __name__ == "__main__":
    app.run(debug=True)
