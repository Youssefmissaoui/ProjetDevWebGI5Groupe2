import os
import re
import sqlite3
import smtplib
import random
import string
import time
from datetime import date, datetime
from email.mime.text import MIMEText
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
)

from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "smart_home_secret_key_2026"
DATABASE = "smart_home.db"


DEVICE_TYPES = {
    "light": "Lumière",
    "tv": "Télévision",
    "thermostat": "Thermostat",
    "door": "Porte intelligente",
    "window": "Fenêtre intelligente",
    "camera": "Caméra",
    "alarm": "Alarme",
    "vacuum": "Robot aspirateur",
    "oven": "Four intelligent",
    "washing_machine": "Machine à laver",
    "fridge": "Réfrigérateur",
    "coffee_machine": "Machine à café",
}

CONDITION_STATES = {
    "bon_etat": "Bon état",
    "nouveau": "Nouveau",
    "fragile": "Fragile",
    "en_panne": "En panne",
}


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def calculate_age(birth_date_str):
    birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d").date()
    today = date.today()
    age = today.year - birth_date.year - (
        (today.month, today.day) < (birth_date.month, birth_date.day)
    )
    return age


def password_is_valid(password):
    if len(password) < 8:
        return False, "Le mot de passe doit contenir au moins 8 caractères."
    if not re.search(r"[A-Z]", password):
        return False, "Le mot de passe doit contenir au moins une majuscule."
    if not re.search(r"\d", password):
        return False, "Le mot de passe doit contenir au moins un chiffre."
    if not re.search(r"[^\w\s]", password):
        return False, "Le mot de passe doit contenir au moins un caractère spécial."
    return True, ""


def generate_captcha(length=5):
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choice(chars) for _ in range(length))


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            birth_date TEXT NOT NULL,
            age INTEGER NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            status TEXT NOT NULL DEFAULT 'pending'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            location TEXT NOT NULL,
            condition_state TEXT NOT NULL DEFAULT 'bon_etat',
            power_state TEXT NOT NULL DEFAULT 'off',
            action_state TEXT NOT NULL DEFAULT 'idle',
            primary_value INTEGER NOT NULL DEFAULT 0,
            secondary_value INTEGER NOT NULL DEFAULT 0,
            mode TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    admin_email = "admin@smarthome.com"
    existing_admin = cursor.execute(
        "SELECT id FROM users WHERE email = ?",
        (admin_email,)
    ).fetchone()

    if not existing_admin:
        cursor.execute("""
            INSERT INTO users (
                first_name, last_name, birth_date, age,
                email, password, role, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "Admin",
            "System",
            "2000-01-01",
            26,
            admin_email,
            generate_password_hash("Admin@123"),
            "admin",
            "approved"
        ))

    conn.commit()
    conn.close()


def send_approval_email(to_email, first_name):
    sender_email = os.getenv("MAIL_SENDER")
    sender_password = os.getenv("MAIL_PASSWORD")
    smtp_server = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("MAIL_PORT", "587"))
    site_url = os.getenv("SITE_URL", "http://127.0.0.1:5000")

    if not sender_email or not sender_password:
        print("Email non envoyé : configuration SMTP absente.")
        return False

    subject = "Votre compte Maison Intelligente a été validé"
    body = f"""
Bonjour {first_name},

Votre compte a été validé par l'administrateur.

Vous pouvez maintenant accéder au site avec ce lien :
{site_url}

Cordialement,
L'équipe Maison Intelligente
""".strip()

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = to_email

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        return True
    except Exception as exc:
        print("Erreur lors de l'envoi du mail :", exc)
        return False


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Veuillez vous connecter.", "error")
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapper


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session or session.get("role") != "admin":
            flash("Accès réservé à l'administrateur.", "error")
            return redirect(url_for("home"))
        return view_func(*args, **kwargs)
    return wrapper


def can_control_device(device, role):
    if device["condition_state"] == "en_panne":
        return False, "Cet objet est en panne. Aucune action n'est autorisée."

    if device["condition_state"] in ["fragile", "nouveau"] and role != "admin":
        return False, "Seul l'administrateur peut manipuler un objet fragile ou nouveau."

    return True, ""


def get_device_defaults(device_type):
    defaults = {
        "light": {
            "power_state": "off",
            "action_state": "idle",
            "primary_value": 100,
            "secondary_value": 0,
            "mode": "normal",
        },
        "tv": {
            "power_state": "off",
            "action_state": "idle",
            "primary_value": 1,   # channel
            "secondary_value": 10,  # volume
            "mode": "tv",
        },
        "thermostat": {
            "power_state": "off",
            "action_state": "idle",
            "primary_value": 22,   # temperature
            "secondary_value": 0,
            "mode": "cool",
        },
        "door": {
            "power_state": "on",
            "action_state": "closed",
            "primary_value": 0,
            "secondary_value": 0,
            "mode": "locked",
        },
        "window": {
            "power_state": "on",
            "action_state": "closed",
            "primary_value": 0,
            "secondary_value": 0,
            "mode": "manual",
        },
        "camera": {
            "power_state": "off",
            "action_state": "inactive",
            "primary_value": 0,
            "secondary_value": 0,
            "mode": "monitoring",
        },
        "alarm": {
            "power_state": "off",
            "action_state": "disarmed",
            "primary_value": 0,
            "secondary_value": 0,
            "mode": "home",
        },
        "vacuum": {
            "power_state": "off",
            "action_state": "idle",
            "primary_value": 100,  # battery
            "secondary_value": 0,
            "mode": "auto",
        },
        "oven": {
            "power_state": "off",
            "action_state": "idle",
            "primary_value": 180,  # temp
            "secondary_value": 0,
            "mode": "bake",
        },
        "washing_machine": {
            "power_state": "off",
            "action_state": "idle",
            "primary_value": 60,  # minutes
            "secondary_value": 0,
            "mode": "normal",
        },
        "fridge": {
            "power_state": "on",
            "action_state": "closed",
            "primary_value": 4,   # temperature
            "secondary_value": -18,  # freezer
            "mode": "eco",
        },
        "coffee_machine": {
            "power_state": "off",
            "action_state": "idle",
            "primary_value": 1,   # cups
            "secondary_value": 0,
            "mode": "espresso",
        },
    }
    return defaults[device_type]


def device_summary(device):
    device_type = device["type"]
    if device_type == "light":
        return f"État: {'Allumée' if device['power_state'] == 'on' else 'Éteinte'} | Intensité: {device['primary_value']}%"
    if device_type == "tv":
        return f"État: {'Allumée' if device['power_state'] == 'on' else 'Éteinte'} | Chaîne: {device['primary_value']} | Volume: {device['secondary_value']}"
    if device_type == "thermostat":
        return f"État: {'Actif' if device['power_state'] == 'on' else 'Arrêt'} | Température: {device['primary_value']}°C | Mode: {device['mode']}"
    if device_type == "door":
        return f"Porte: {device['action_state']} | Verrou: {device['mode']}"
    if device_type == "window":
        return f"Fenêtre: {device['action_state']}"
    if device_type == "camera":
        return f"Caméra: {device['action_state']}"
    if device_type == "alarm":
        return f"Alarme: {device['action_state']} | Mode: {device['mode']}"
    if device_type == "vacuum":
        return f"Statut: {device['action_state']} | Batterie: {device['primary_value']}%"
    if device_type == "oven":
        return f"État: {'Allumé' if device['power_state'] == 'on' else 'Éteint'} | Température: {device['primary_value']}°C | Mode: {device['mode']}"
    if device_type == "washing_machine":
        return f"Statut: {device['action_state']} | Durée: {device['primary_value']} min | Programme: {device['mode']}"
    if device_type == "fridge":
        return f"Température: {device['primary_value']}°C | Congélateur: {device['secondary_value']}°C | Porte: {device['action_state']}"
    if device_type == "coffee_machine":
        return f"État: {'Allumée' if device['power_state'] == 'on' else 'Éteinte'} | Tasses: {device['primary_value']} | Mode: {device['mode']}"
    return "Objet connecté"


def get_device_actions(device):
    t = device["type"]
    p = device["power_state"]

    if t == "light":
        actions = [{"value": "turn_on", "label": "Allumer", "class": "btn-green"}] if p == "off" else [{"value": "turn_off", "label": "Éteindre", "class": "btn-red"}]
        actions += [{"value": "brightness_up", "label": "Intensité +", "class": "btn-blue"},
                    {"value": "brightness_down", "label": "Intensité -", "class": "btn-orange"}]
        return actions

    if t == "tv":
        actions = [{"value": "turn_on", "label": "Allumer", "class": "btn-green"}] if p == "off" else [{"value": "turn_off", "label": "Éteindre", "class": "btn-red"}]
        if p == "on":
            actions += [
                {"value": "channel_up", "label": "Chaîne +", "class": "btn-blue"},
                {"value": "channel_down", "label": "Chaîne -", "class": "btn-orange"},
                {"value": "volume_up", "label": "Volume +", "class": "btn-blue"},
                {"value": "volume_down", "label": "Volume -", "class": "btn-orange"},
            ]
        return actions

    if t == "thermostat":
        actions = [{"value": "turn_on", "label": "Allumer", "class": "btn-green"}] if p == "off" else [{"value": "turn_off", "label": "Éteindre", "class": "btn-red"}]
        actions += [
            {"value": "temp_up", "label": "Température +", "class": "btn-blue"},
            {"value": "temp_down", "label": "Température -", "class": "btn-orange"},
            {"value": "mode_heat", "label": "Mode chaud", "class": "btn-blue"},
            {"value": "mode_cool", "label": "Mode froid", "class": "btn-orange"},
        ]
        return actions

    if t == "door":
        return [
            {"value": "open", "label": "Ouvrir", "class": "btn-green"},
            {"value": "close", "label": "Fermer", "class": "btn-red"},
            {"value": "lock", "label": "Verrouiller", "class": "btn-blue"},
            {"value": "unlock", "label": "Déverrouiller", "class": "btn-orange"},
        ]

    if t == "window":
        return [
            {"value": "open", "label": "Ouvrir", "class": "btn-green"},
            {"value": "close", "label": "Fermer", "class": "btn-red"},
        ]

    if t == "camera":
        return [
            {"value": "activate", "label": "Activer", "class": "btn-green"},
            {"value": "deactivate", "label": "Désactiver", "class": "btn-red"},
        ]

    if t == "alarm":
        return [
            {"value": "arm_home", "label": "Activer maison", "class": "btn-green"},
            {"value": "arm_away", "label": "Activer absence", "class": "btn-blue"},
            {"value": "disarm", "label": "Désactiver", "class": "btn-red"},
        ]

    if t == "vacuum":
        return [
            {"value": "start_cleaning", "label": "Démarrer", "class": "btn-green"},
            {"value": "stop_cleaning", "label": "Arrêter", "class": "btn-red"},
            {"value": "dock", "label": "Retour base", "class": "btn-blue"},
        ]

    if t == "oven":
        actions = [{"value": "turn_on", "label": "Allumer", "class": "btn-green"}] if p == "off" else [{"value": "turn_off", "label": "Éteindre", "class": "btn-red"}]
        actions += [
            {"value": "temp_up", "label": "Température +", "class": "btn-blue"},
            {"value": "temp_down", "label": "Température -", "class": "btn-orange"},
            {"value": "mode_bake", "label": "Cuisson", "class": "btn-blue"},
            {"value": "mode_grill", "label": "Grill", "class": "btn-orange"},
        ]
        return actions

    if t == "washing_machine":
        return [
            {"value": "start_cycle", "label": "Démarrer", "class": "btn-green"},
            {"value": "pause_cycle", "label": "Pause", "class": "btn-orange"},
            {"value": "stop_cycle", "label": "Arrêter", "class": "btn-red"},
            {"value": "program_quick", "label": "Programme rapide", "class": "btn-blue"},
            {"value": "program_normal", "label": "Programme normal", "class": "btn-blue"},
        ]

    if t == "fridge":
        return [
            {"value": "temp_up", "label": "Température +", "class": "btn-orange"},
            {"value": "temp_down", "label": "Température -", "class": "btn-blue"},
            {"value": "open", "label": "Ouvrir porte", "class": "btn-green"},
            {"value": "close", "label": "Fermer porte", "class": "btn-red"},
        ]

    if t == "coffee_machine":
        actions = [{"value": "turn_on", "label": "Allumer", "class": "btn-green"}] if p == "off" else [{"value": "turn_off", "label": "Éteindre", "class": "btn-red"}]
        if p == "on":
            actions += [
                {"value": "brew", "label": "Préparer café", "class": "btn-blue"},
                {"value": "cups_up", "label": "Tasses +", "class": "btn-blue"},
                {"value": "cups_down", "label": "Tasses -", "class": "btn-orange"},
                {"value": "mode_espresso", "label": "Espresso", "class": "btn-blue"},
                {"value": "mode_lungo", "label": "Lungo", "class": "btn-orange"},
            ]
        return actions

    return []


def apply_device_action(device, action):
    d = dict(device)

    if action in ["turn_on", "activate"]:
        d["power_state"] = "on"
        if d["type"] == "camera":
            d["action_state"] = "active"
        if d["type"] == "coffee_machine":
            d["action_state"] = "ready"

    elif action in ["turn_off", "deactivate"]:
        d["power_state"] = "off"
        if d["type"] == "camera":
            d["action_state"] = "inactive"
        if d["type"] == "coffee_machine":
            d["action_state"] = "idle"

    elif action == "brightness_up":
        d["primary_value"] = min(100, d["primary_value"] + 10)
    elif action == "brightness_down":
        d["primary_value"] = max(0, d["primary_value"] - 10)

    elif action == "channel_up":
        d["primary_value"] += 1
    elif action == "channel_down":
        d["primary_value"] = max(1, d["primary_value"] - 1)
    elif action == "volume_up":
        d["secondary_value"] = min(100, d["secondary_value"] + 5)
    elif action == "volume_down":
        d["secondary_value"] = max(0, d["secondary_value"] - 5)

    elif action == "temp_up":
        if d["type"] == "fridge":
            d["primary_value"] = min(10, d["primary_value"] + 1)
        else:
            d["primary_value"] += 1
    elif action == "temp_down":
        if d["type"] == "fridge":
            d["primary_value"] = max(1, d["primary_value"] - 1)
        else:
            d["primary_value"] -= 1

    elif action == "mode_heat":
        d["mode"] = "heat"
    elif action == "mode_cool":
        d["mode"] = "cool"
    elif action == "mode_bake":
        d["mode"] = "bake"
    elif action == "mode_grill":
        d["mode"] = "grill"
    elif action == "mode_espresso":
        d["mode"] = "espresso"
    elif action == "mode_lungo":
        d["mode"] = "lungo"

    elif action == "open":
        d["action_state"] = "open"
    elif action == "close":
        d["action_state"] = "closed"
    elif action == "lock":
        d["mode"] = "locked"
    elif action == "unlock":
        d["mode"] = "unlocked"

    elif action == "arm_home":
        d["power_state"] = "on"
        d["action_state"] = "armed"
        d["mode"] = "home"
    elif action == "arm_away":
        d["power_state"] = "on"
        d["action_state"] = "armed"
        d["mode"] = "away"
    elif action == "disarm":
        d["power_state"] = "off"
        d["action_state"] = "disarmed"

    elif action == "start_cleaning":
        d["power_state"] = "on"
        d["action_state"] = "cleaning"
        d["primary_value"] = max(0, d["primary_value"] - 5)
    elif action == "stop_cleaning":
        d["power_state"] = "off"
        d["action_state"] = "idle"
    elif action == "dock":
        d["power_state"] = "on"
        d["action_state"] = "docked"

    elif action == "start_cycle":
        d["power_state"] = "on"
        d["action_state"] = "running"
    elif action == "pause_cycle":
        d["power_state"] = "on"
        d["action_state"] = "paused"
    elif action == "stop_cycle":
        d["power_state"] = "off"
        d["action_state"] = "idle"
    elif action == "program_quick":
        d["mode"] = "quick"
        d["primary_value"] = 30
    elif action == "program_normal":
        d["mode"] = "normal"
        d["primary_value"] = 60

    elif action == "brew":
        d["action_state"] = "brewing"
    elif action == "cups_up":
        d["primary_value"] = min(6, d["primary_value"] + 1)
    elif action == "cups_down":
        d["primary_value"] = max(1, d["primary_value"] - 1)

    return d


def update_device_in_db(device_id, updated):
    conn = get_db_connection()
    conn.execute("""
        UPDATE devices
        SET power_state = ?, action_state = ?, primary_value = ?, secondary_value = ?, mode = ?
        WHERE id = ?
    """, (
        updated["power_state"],
        updated["action_state"],
        updated["primary_value"],
        updated["secondary_value"],
        updated["mode"],
        device_id
    ))
    conn.commit()
    conn.close()


def build_device_query(base_query, search_value, device_type_filter, condition_filter):
    clauses = []
    params = []

    if search_value:
        clauses.append("(name LIKE ? OR location LIKE ?)")
        like_value = f"%{search_value}%"
        params.extend([like_value, like_value])

    if device_type_filter:
        clauses.append("type = ?")
        params.append(device_type_filter)

    if condition_filter:
        clauses.append("condition_state = ?")
        params.append(condition_filter)

    if clauses:
        base_query += " WHERE " + " AND ".join(clauses)

    base_query += " ORDER BY id DESC"
    return base_query, params


@app.context_processor
def inject_globals():
    return {
        "DEVICE_TYPES": DEVICE_TYPES,
        "CONDITION_STATES": CONDITION_STATES
    }


@app.route("/")
def home():
    if "user_id" in session:
        if session.get("role") == "admin":
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("user_dashboard"))
    return render_template("home.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "GET":
        session["captcha"] = generate_captcha()
        return render_template("register.html", captcha=session["captcha"])

    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    birth_date = request.form.get("birth_date", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "").strip()
    confirm_password = request.form.get("confirm_password", "").strip()
    captcha_input = request.form.get("captcha_input", "").strip().upper()

    if not all([first_name, last_name, birth_date, email, password, confirm_password, captcha_input]):
        flash("Tous les champs sont obligatoires.", "error")
        session["captcha"] = generate_captcha()
        return render_template("register.html", captcha=session["captcha"])

    try:
        age = calculate_age(birth_date)
    except ValueError:
        flash("Date de naissance invalide.", "error")
        session["captcha"] = generate_captcha()
        return render_template("register.html", captcha=session["captcha"])

    if age < 12:
        flash("Il faut avoir au moins 12 ans pour créer un compte.", "error")
        session["captcha"] = generate_captcha()
        return render_template("register.html", captcha=session["captcha"])

    valid_password, message = password_is_valid(password)
    if not valid_password:
        flash(message, "error")
        session["captcha"] = generate_captcha()
        return render_template("register.html", captcha=session["captcha"])

    if password != confirm_password:
        flash("La confirmation du mot de passe ne correspond pas.", "error")
        session["captcha"] = generate_captcha()
        return render_template("register.html", captcha=session["captcha"])

    if captcha_input != session.get("captcha", ""):
        flash("Captcha incorrect.", "error")
        session["captcha"] = generate_captcha()
        return render_template("register.html", captcha=session["captcha"])

    conn = get_db_connection()
    try:
        conn.execute("""
            INSERT INTO users (
                first_name, last_name, birth_date, age,
                email, password, role, status
            )
            VALUES (?, ?, ?, ?, ?, ?, 'user', 'pending')
        """, (
            first_name,
            last_name,
            birth_date,
            age,
            email,
            generate_password_hash(password)
        ))
        conn.commit()
        flash("Compte créé avec succès. En attente de validation par l'administrateur.", "success")
        return redirect(url_for("login"))
    except sqlite3.IntegrityError:
        flash("Cet email existe déjà.", "error")
        session["captcha"] = generate_captcha()
        return render_template("register.html", captcha=session["captcha"])
    finally:
        conn.close()


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()
        conn.close()

        if not user or not check_password_hash(user["password"], password):
            flash("Email ou mot de passe incorrect.", "error")
            return redirect(url_for("login"))

        if user["status"] == "pending":
            flash("Votre compte est en attente de validation par l'administrateur.", "error")
            return redirect(url_for("login"))
        if user["status"] == "rejected":
            flash("Votre compte a été refusé.", "error")
            return redirect(url_for("login"))
        if user["status"] == "blocked":
            flash("Votre compte a été bloqué par l'administrateur.", "error")
            return redirect(url_for("login"))

        session["user_id"] = user["id"]
        session["role"] = user["role"]
        session["full_name"] = f"{user['first_name']} {user['last_name']}"
        session["email"] = user["email"]

        return redirect(url_for("home"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Déconnexion réussie.", "success")
    return redirect(url_for("home"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    search_value = request.args.get("search", "").strip()
    device_type_filter = request.args.get("type", "").strip()
    condition_filter = request.args.get("condition", "").strip()

    conn = get_db_connection()

    pending_users = conn.execute("""
        SELECT * FROM users
        WHERE role = 'user' AND status = 'pending'
        ORDER BY id DESC
    """).fetchall()

    approved_users = conn.execute("""
        SELECT * FROM users
        WHERE role = 'user' AND status = 'approved'
        ORDER BY id DESC
    """).fetchall()

    blocked_users = conn.execute("""
        SELECT * FROM users
        WHERE role = 'user' AND status = 'blocked'
        ORDER BY id DESC
    """).fetchall()

    query, params = build_device_query(
        "SELECT * FROM devices",
        search_value,
        device_type_filter,
        condition_filter
    )
    devices = conn.execute(query, params).fetchall()

    conn.close()

    return render_template(
        "admin_dashboard.html",
        pending_users=pending_users,
        approved_users=approved_users,
        blocked_users=blocked_users,
        devices=devices,
        search_value=search_value,
        device_type_filter=device_type_filter,
        condition_filter=condition_filter,
        device_summary=device_summary
    )


@app.route("/admin/approve/<int:user_id>", methods=["POST"])
@admin_required
def approve_user(user_id):
    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ? AND role = 'user'",
        (user_id,)
    ).fetchone()

    if not user:
        conn.close()
        flash("Utilisateur introuvable.", "error")
        return redirect(url_for("admin_dashboard"))

    conn.execute(
        "UPDATE users SET status = 'approved' WHERE id = ?",
        (user_id,)
    )
    conn.commit()
    conn.close()

    send_approval_email(user["email"], user["first_name"])
    flash("Compte validé.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/reject/<int:user_id>", methods=["POST"])
@admin_required
def reject_user(user_id):
    conn = get_db_connection()
    conn.execute(
        "UPDATE users SET status = 'rejected' WHERE id = ? AND role = 'user'",
        (user_id,)
    )
    conn.commit()
    conn.close()
    flash("Compte refusé.", "error")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/block-user/<int:user_id>", methods=["POST"])
@admin_required
def block_user(user_id):
    conn = get_db_connection()
    conn.execute(
        "UPDATE users SET status = 'blocked' WHERE id = ? AND role = 'user'",
        (user_id,)
    )
    conn.commit()
    conn.close()
    flash("Utilisateur bloqué.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/unblock-user/<int:user_id>", methods=["POST"])
@admin_required
def unblock_user(user_id):
    conn = get_db_connection()
    conn.execute(
        "UPDATE users SET status = 'approved' WHERE id = ? AND role = 'user'",
        (user_id,)
    )
    conn.commit()
    conn.close()
    flash("Utilisateur débloqué.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/add-device", methods=["GET", "POST"])
@admin_required
def add_device():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        device_type = request.form.get("type", "").strip()
        location = request.form.get("location", "").strip()
        condition_state = request.form.get("condition_state", "").strip()

        if not all([name, device_type, location, condition_state]):
            flash("Tous les champs sont obligatoires.", "error")
            return redirect(url_for("add_device"))

        if device_type not in DEVICE_TYPES:
            flash("Type d'objet invalide.", "error")
            return redirect(url_for("add_device"))

        if condition_state not in CONDITION_STATES:
            flash("Condition invalide.", "error")
            return redirect(url_for("add_device"))

        defaults = get_device_defaults(device_type)

        conn = get_db_connection()
        conn.execute("""
            INSERT INTO devices (
                name, type, location, condition_state,
                power_state, action_state, primary_value, secondary_value, mode
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name,
            device_type,
            location,
            condition_state,
            defaults["power_state"],
            defaults["action_state"],
            defaults["primary_value"],
            defaults["secondary_value"],
            defaults["mode"],
        ))
        conn.commit()
        conn.close()

        flash("Objet ajouté avec succès.", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("add_device.html")


@app.route("/admin/edit-device/<int:device_id>", methods=["GET", "POST"])
@admin_required
def edit_device(device_id):
    conn = get_db_connection()
    device = conn.execute(
        "SELECT * FROM devices WHERE id = ?",
        (device_id,)
    ).fetchone()

    if not device:
        conn.close()
        flash("Objet introuvable.", "error")
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        device_type = request.form.get("type", "").strip()
        location = request.form.get("location", "").strip()
        condition_state = request.form.get("condition_state", "").strip()
        power_state = request.form.get("power_state", "").strip()
        action_state = request.form.get("action_state", "").strip()
        primary_value = request.form.get("primary_value", "0").strip()
        secondary_value = request.form.get("secondary_value", "0").strip()
        mode = request.form.get("mode", "").strip()

        if not all([name, device_type, location, condition_state, power_state]):
            conn.close()
            flash("Champs obligatoires manquants.", "error")
            return redirect(url_for("edit_device", device_id=device_id))

        try:
            primary_value = int(primary_value)
        except ValueError:
            primary_value = 0

        try:
            secondary_value = int(secondary_value)
        except ValueError:
            secondary_value = 0

        conn.execute("""
            UPDATE devices
            SET name = ?, type = ?, location = ?, condition_state = ?, power_state = ?,
                action_state = ?, primary_value = ?, secondary_value = ?, mode = ?
            WHERE id = ?
        """, (
            name, device_type, location, condition_state, power_state,
            action_state, primary_value, secondary_value, mode, device_id
        ))
        conn.commit()
        conn.close()

        flash("Objet modifié avec succès.", "success")
        return redirect(url_for("admin_dashboard"))

    conn.close()
    return render_template("edit_device.html", device=device)


@app.route("/admin/delete-device/<int:device_id>", methods=["POST"])
@admin_required
def delete_device(device_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    conn.commit()
    conn.close()
    flash("Objet supprimé avec succès.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/dashboard")
@login_required
def user_dashboard():
    search_value = request.args.get("search", "").strip()
    device_type_filter = request.args.get("type", "").strip()
    condition_filter = request.args.get("condition", "").strip()

    conn = get_db_connection()
    query, params = build_device_query(
        "SELECT * FROM devices",
        search_value,
        device_type_filter,
        condition_filter
    )
    devices = conn.execute(query, params).fetchall()
    conn.close()

    return render_template(
        "user_dashboard.html",
        devices=devices,
        search_value=search_value,
        device_type_filter=device_type_filter,
        condition_filter=condition_filter,
        device_summary=device_summary
    )


@app.route("/device/<int:device_id>", methods=["GET", "POST"])
@login_required
def device_control(device_id):
    conn = get_db_connection()
    device = conn.execute(
        "SELECT * FROM devices WHERE id = ?",
        (device_id,)
    ).fetchone()

    if not device:
        conn.close()
        flash("Objet introuvable.", "error")
        return redirect(url_for("user_dashboard"))

    allowed, reason = can_control_device(device, session.get("role"))
    actions = get_device_actions(device)

    if request.method == "POST":
        if not allowed:
            conn.close()
            flash(reason, "error")
            return redirect(url_for("device_control", device_id=device_id))

        action = request.form.get("action", "").strip()
        updated = apply_device_action(device, action)
        time.sleep(1)
        update_device_in_db(device_id, updated)
        flash("Action validée.", "success")

        conn = get_db_connection()
        device = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
        conn.close()
        actions = get_device_actions(device)

    else:
        conn.close()

    return render_template(
        "device_control.html",
        device=device,
        allowed=allowed,
        reason=reason,
        actions=actions,
        device_summary=device_summary,
        device_type_label=DEVICE_TYPES.get(device["type"], device["type"])
    )


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
