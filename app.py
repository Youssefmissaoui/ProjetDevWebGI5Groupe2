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
            state TEXT NOT NULL DEFAULT 'off',
            condition_state TEXT NOT NULL DEFAULT 'bon_etat',
            current_channel INTEGER NOT NULL DEFAULT 1
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
    """
    Envoi facultatif.
    Configure ces variables d'environnement si tu veux un vrai envoi :
    MAIL_SENDER
    MAIL_PASSWORD
    MAIL_SERVER
    MAIL_PORT
    SITE_URL
    """
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
    condition_state = device["condition_state"]

    if condition_state == "en_panne":
        return False, "Cet objet est en panne. Aucune action n'est autorisée."

    if condition_state in ["fragile", "nouveau"] and role != "admin":
        return False, "Seul l'administrateur peut manipuler un objet fragile ou nouveau."

    return True, ""


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

    hashed_password = generate_password_hash(password)

    conn = get_db_connection()
    try:
        conn.execute("""
            INSERT INTO users (
                first_name, last_name, birth_date, age,
                email, password, role, status
            )
            VALUES (?, ?, ?, ?, ?, ?, 'user', 'pending')
        """, (first_name, last_name, birth_date, age, email, hashed_password))
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

    devices = conn.execute("""
        SELECT * FROM devices
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "admin_dashboard.html",
        pending_users=pending_users,
        approved_users=approved_users,
        blocked_users=blocked_users,
        devices=devices
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

        if device_type not in ["light", "tv"]:
            flash("Type d'objet invalide.", "error")
            return redirect(url_for("add_device"))

        conn = get_db_connection()
        conn.execute("""
            INSERT INTO devices (name, type, location, state, condition_state, current_channel)
            VALUES (?, ?, ?, 'off', ?, 1)
        """, (name, device_type, location, condition_state))
        conn.commit()
        conn.close()

        flash("Objet ajouté avec succès.", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("add_device.html")


@app.route("/admin/delete-device/<int:device_id>", methods=["POST"])
@admin_required
def delete_device(device_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    conn.commit()
    conn.close()
    flash("Objet supprimé avec succès.", "success")
    return redirect(url_for("admin_dashboard"))


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
        state = request.form.get("state", "").strip()
        condition_state = request.form.get("condition_state", "").strip()
        current_channel = request.form.get("current_channel", "1").strip()

        if not all([name, device_type, location, state, condition_state]):
            conn.close()
            flash("Tous les champs sont obligatoires.", "error")
            return redirect(url_for("edit_device", device_id=device_id))

        if device_type not in ["light", "tv"]:
            conn.close()
            flash("Type d'objet invalide.", "error")
            return redirect(url_for("edit_device", device_id=device_id))

        if state not in ["on", "off"]:
            conn.close()
            flash("État invalide.", "error")
            return redirect(url_for("edit_device", device_id=device_id))

        if condition_state not in ["bon_etat", "nouveau", "fragile", "en_panne"]:
            conn.close()
            flash("Condition invalide.", "error")
            return redirect(url_for("edit_device", device_id=device_id))

        try:
            current_channel_int = max(1, int(current_channel))
        except ValueError:
            current_channel_int = 1

        if device_type != "tv":
            current_channel_int = 1

        conn.execute("""
            UPDATE devices
            SET name = ?, type = ?, location = ?, state = ?, condition_state = ?, current_channel = ?
            WHERE id = ?
        """, (
            name,
            device_type,
            location,
            state,
            condition_state,
            current_channel_int,
            device_id
        ))
        conn.commit()
        conn.close()

        flash("Objet modifié avec succès.", "success")
        return redirect(url_for("admin_dashboard"))

    conn.close()
    return render_template("edit_device.html", device=device)


@app.route("/dashboard")
@login_required
def user_dashboard():
    conn = get_db_connection()
    devices = conn.execute("""
        SELECT * FROM devices
        ORDER BY id DESC
    """).fetchall()
    conn.close()
    return render_template("user_dashboard.html", devices=devices)


@app.route("/device/light/<int:device_id>", methods=["GET", "POST"])
@login_required
def light_control(device_id):
    conn = get_db_connection()
    device = conn.execute("""
        SELECT * FROM devices
        WHERE id = ? AND type = 'light'
    """, (device_id,)).fetchone()

    if not device:
        conn.close()
        flash("Lumière introuvable.", "error")
        return redirect(url_for("user_dashboard"))

    allowed, reason = can_control_device(device, session.get("role"))

    if request.method == "POST":
        if not allowed:
            conn.close()
            flash(reason, "error")
            return redirect(url_for("light_control", device_id=device_id))

        action = request.form.get("action")
        time.sleep(2)

        if action == "on":
            conn.execute("UPDATE devices SET state = 'on' WHERE id = ?", (device_id,))
            flash("Action validée : la lumière a été allumée.", "success")
        elif action == "off":
            conn.execute("UPDATE devices SET state = 'off' WHERE id = ?", (device_id,))
            flash("Action validée : la lumière a été éteinte.", "success")
        else:
            flash("Action invalide.", "error")

        conn.commit()
        device = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()

    conn.close()
    return render_template("light.html", device=device, allowed=allowed, reason=reason)


@app.route("/device/tv/<int:device_id>", methods=["GET", "POST"])
@login_required
def tv_control(device_id):
    conn = get_db_connection()
    device = conn.execute("""
        SELECT * FROM devices
        WHERE id = ? AND type = 'tv'
    """, (device_id,)).fetchone()

    if not device:
        conn.close()
        flash("Télévision introuvable.", "error")
        return redirect(url_for("user_dashboard"))

    allowed, reason = can_control_device(device, session.get("role"))

    if request.method == "POST":
        if not allowed:
            conn.close()
            flash(reason, "error")
            return redirect(url_for("tv_control", device_id=device_id))

        action = request.form.get("action")
        state = device["state"]
        channel = device["current_channel"]

        time.sleep(1)

        if action == "on":
            state = "on"
        elif action == "off":
            state = "off"
        elif action == "channel_up" and state == "on":
            channel += 1
        elif action == "channel_down" and state == "on":
            channel = max(1, channel - 1)

        conn.execute("""
            UPDATE devices
            SET state = ?, current_channel = ?
            WHERE id = ?
        """, (state, channel, device_id))
        conn.commit()

        device = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
        flash("Télévision mise à jour.", "success")

    conn.close()
    return render_template("tv.html", device=device, allowed=allowed, reason=reason)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)