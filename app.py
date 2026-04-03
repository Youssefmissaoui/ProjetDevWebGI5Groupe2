from flask import Flask, request

app = Flask(__name__)

# "base de données" temporaire
users = []

# créer un admin au démarrage
users.append({
    "username": "admin",
    "password": "admin",
    "is_validated": 1,
    "role": "admin"
})

@app.route('/')
def home():
    return "Accueil"

# REGISTER
@app.route('/register', methods=['POST'])
def register():
    username = request.form['username']
    password = request.form['password']
    
    user = {
        "username": username,
        "password": password,
        "is_validated": 0,
        "role": "user"
    }
    
    users.append(user)
    
    return "Inscription réussie (en attente validation)"

# LOGIN
@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    
    for user in users:
        if user["username"] == username and user["password"] == password:
            
            if user["is_validated"] == 0:
                return "Compte non validé"
            
            if user["role"] == "admin":
                return "Bienvenue ADMIN"
            else:
                return "Bienvenue USER"
    
    return "Identifiants incorrects"

# ADMIN : voir utilisateurs
@app.route('/admin/users')
def admin_users():
    result = ""
    for i, user in enumerate(users):
        result += f"{i} - {user['username']} - validé: {user['is_validated']}<br>"
    return result

# ADMIN : valider utilisateur
@app.route('/admin/validate', methods=['POST'])
def validate():
    index = int(request.form['index'])
    
    users[index]["is_validated"] = 1
    
    return "Utilisateur validé"

app.run(debug=True)