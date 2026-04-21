from flask import Flask, request, redirect, session
import sqlite3

app = Flask(__name__)
app.secret_key = "secret123"

# 🔹 connexion DB
def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

# 🔹 initialisation DB
def init_db():
    conn = get_db()

    # USERS
    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        password TEXT,
        role TEXT,
        is_validated INTEGER
    )
    """)

    # OBJECTS
    conn.execute("""
    CREATE TABLE IF NOT EXISTS objects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        type TEXT,
        status TEXT,
        temperature INTEGER,
        room TEXT
    )
    """)

    # admin par défaut
    admin = conn.execute("SELECT * FROM users WHERE username='admin'").fetchone()
    if not admin:
        conn.execute(
            "INSERT INTO users (username, password, role, is_validated) VALUES (?, ?, ?, ?)",
            ("admin", "admin", "admin", 1)
        )

    conn.commit()
    conn.close()

init_db()

# 🔹 HOME
@app.route('/')
def home():
    return """
    <h1>Maison Intelligente</h1>
    <a href="/login_page">Login</a><br>
    <a href="/register_page">Register</a>
    """

# 🔹 PAGE LOGIN
@app.route('/login_page')
def login_page():
    return """
    <h2>Login</h2>
    <form action="/login" method="post">
        <input name="username" placeholder="Username"><br>
        <input name="password" type="password" placeholder="Password"><br>
        <button>Login</button>
    </form>
    <br>
    <a href="/">Retour</a>
    """

# 🔹 PAGE REGISTER
@app.route('/register_page')
def register_page():
    return """
    <h2>Register</h2>
    <form action="/register" method="post">
        <input name="username" placeholder="Username"><br>
        <input name="password" type="password" placeholder="Password"><br>
        <button>Register</button>
    </form>
    <br>
    <a href="/">Retour</a>
    """

# 🔹 REGISTER
@app.route('/register', methods=['POST'])
def register():
    username = request.form['username']
    password = request.form['password']

    conn = get_db()
    conn.execute(
        "INSERT INTO users (username, password, role, is_validated) VALUES (?, ?, ?, ?)",
        (username, password, "user", 0)
    )
    conn.commit()
    conn.close()

    return redirect('/login_page')

# 🔹 LOGIN
@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']

    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE username=? AND password=?",
        (username, password)
    ).fetchone()
    conn.close()

    if user:
        if user["is_validated"] == 0:
            return "Compte non validé par admin"

        # 🔥 SESSION
        session['user'] = user['username']
        session['role'] = user['role']

        if user["role"] == "admin":
            return redirect('/admin')
        else:
            return redirect('/dashboard')

    return "Identifiants incorrects"

# 🔹 DASHBOARD
@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect('/login_page')

    conn = get_db()
    objects = conn.execute("SELECT * FROM objects").fetchall()
    conn.close()

    html = f"<h1>Dashboard</h1><p>Bienvenue {session['user']}</p>"

    for obj in objects:
        html += f"""
        <p>
        {obj['name']} | {obj['type']} | {obj['status']} | {obj['temperature']}°C | {obj['room']}
        </p>
        """

    html += """
    <h3>Ajouter un objet</h3>
    <form action="/add_object" method="post">
        <input name="name" placeholder="Nom"><br>
        <input name="type" placeholder="Type"><br>
        <input name="status" placeholder="Status"><br>
        <input name="temperature" placeholder="Température"><br>
        <input name="room" placeholder="Pièce"><br>
        <button>Ajouter</button>
    </form>
    """

    html += """
    <br><a href="/logout">Logout</a>
    """

    return html

# 🔹 AJOUT OBJET
@app.route('/add_object', methods=['POST'])
def add_object():
    if 'user' not in session:
        return redirect('/login_page')

    name = request.form['name']
    type = request.form['type']
    status = request.form['status']
    temperature = request.form['temperature']
    room = request.form['room']

    conn = get_db()
    conn.execute(
        "INSERT INTO objects (name, type, status, temperature, room) VALUES (?, ?, ?, ?, ?)",
        (name, type, status, temperature, room)
    )
    conn.commit()
    conn.close()

    return redirect('/dashboard')

# 🔹 ADMIN
@app.route('/admin')
def admin():
    if 'role' not in session or session['role'] != 'admin':
        return "Accès interdit"

    conn = get_db()
    users = conn.execute("SELECT * FROM users").fetchall()
    conn.close()

    html = "<h1>Admin Panel</h1>"

    for user in users:
        html += f"""
        <p>
        ID: {user['id']} | {user['username']} | Validé: {user['is_validated']}
        </p>
        """

    html += """
    <h3>Valider un utilisateur</h3>
    <form action="/admin/validate" method="post">
        <input type="number" name="id" placeholder="ID utilisateur">
        <button>Valider</button>
    </form>
    """

    html += """
    <br><a href="/logout">Logout</a>
    """

    return html

# 🔹 VALIDATION ADMIN
@app.route('/admin/validate', methods=['POST'])
def validate():
    if 'role' not in session or session['role'] != 'admin':
        return "Accès interdit"

    user_id = request.form['id']

    conn = get_db()
    conn.execute(
        "UPDATE users SET is_validated=1 WHERE id=?",
        (user_id,)
    )
    conn.commit()
    conn.close()

    return redirect('/admin')

# 🔹 LOGOUT
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login_page')

# 🔹 RUN
app.run(debug=True)