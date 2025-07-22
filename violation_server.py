import os
import json
import string
import random
import sqlite3
from flask import Flask, request, jsonify, render_template, redirect, session, url_for
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'your-secret-key'
CORS(app, supports_credentials=True)
socketio = SocketIO(app, cors_allowed_origins="*")

def generate_random_id(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

# -------------------- DB 설정 --------------------
DB_FILE = 'admin_users.db'

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                org_id TEXT
            )
        ''')
        conn.commit()

init_db()

# -------------------- 로그인 매니저 --------------------
login_manager = LoginManager()
login_manager.init_app(app)

class Admin(UserMixin):
    def __init__(self, id, email, org_id):
        self.id = id
        self.email = email
        self.org_id = org_id

@login_manager.user_loader
def load_user(admin_id):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT id, email, org_id FROM admins WHERE id=?", (admin_id,))
        row = c.fetchone()
        if row:
            return Admin(*row)
    return None

# -------------------- 라우터: 인증 --------------------

@app.route("/register_admin", methods=["POST"])
def register_admin():
    data = request.json
    email = data.get("email")
    password = data.get("password")
    if not email or not password:
        return jsonify({"success": False, "message": "이메일과 비밀번호가 필요합니다."}), 400

    hashed_pw = generate_password_hash(password)
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO admins (email, password) VALUES (?, ?)", (email, hashed_pw))
            conn.commit()
        return jsonify({"success": True})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "이미 존재하는 이메일입니다."}), 409

@app.route("/login_admin", methods=["POST"])
def login_admin():
    data = request.json
    email = data.get("email")
    password = data.get("password")

    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT id, password, org_id FROM admins WHERE email=?", (email,))
        row = c.fetchone()
        if row and check_password_hash(row[1], password):
            user = Admin(row[0], email, row[2])
            login_user(user)
            return jsonify({"success": True})
    return jsonify({"success": False, "message": "이메일 또는 비밀번호가 올바르지 않습니다."}), 401

@app.route("/logout_admin")
@login_required
def logout_admin():
    logout_user()
    return redirect("/")

@app.route('/generate_org_id', methods=['POST'])
@login_required
def generate_org_id():
    org_id = generate_random_id()
    org_path = f"data/{org_id}"
    os.makedirs(org_path, exist_ok=True)

    # 기본 users.json, user_data.json 생성
    with open(f"{org_path}/users.json", "w") as f:
        json.dump({}, f)
    with open(f"{org_path}/user_data.json", "w") as f:
        json.dump({}, f)

    return jsonify({"org_id": org_id})
# -------------------- 라우터: 관리자 페이지 --------------------

@app.route("/admin")
@login_required
def admin_page():
    # ✅ 사용자 데이터 초기화
    org_id = current_user.org_id
    user_data_path = f"data/{org_id}/user_data.json"
    users_path = f"data/{org_id}/users.json"

    # 두 JSON 파일을 빈 딕셔너리로 초기화
    for path in [user_data_path, users_path]:
        if os.path.exists(path):
            with open(path, "w") as f:
                json.dump({}, f)

    return render_template("admin.html")

@app.route("/institution_id")
@login_required
def get_institution_id():
    return jsonify({"org_id": current_user.org_id})

# -------------------- 고유 ID 생성 --------------------

@app.route("/generate_org_id", methods=["POST"])
@login_required
def generate_org_id():
    org_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE admins SET org_id=? WHERE id=?", (org_id, current_user.id))
        conn.commit()

    # 폴더 생성
    os.makedirs(f"data/{org_id}", exist_ok=True)
    for filename in ["users.json", "user_data.json"]:
        path = f"data/{org_id}/{filename}"
        if not os.path.exists(path):
            with open(path, "w") as f:
                json.dump({}, f)

    return jsonify({"success": True, "org_id": org_id})

# -------------------- 사용자 등록 --------------------

@app.route("/register_user", methods=["POST"])
def register_user():
    data = request.json
    org_id = data.get("org_id")
    user_id = data.get("user_id")
    name = data.get("name")
    if not (org_id and user_id and name):
        return "Missing data", 400

    path = f"data/{org_id}/users.json"
    os.makedirs(os.path.dirname(path), exist_ok=True)

    if os.path.exists(path):
        with open(path, "r") as f:
            users = json.load(f)
    else:
        users = {}

    users[user_id] = {"name": name}
    with open(path, "w") as f:
        json.dump(users, f)

    return "User registered", 200

# -------------------- 위반 보고 --------------------

@app.route("/report_violation", methods=["POST"])
def report_violation():
    data = request.json
    org_id = data.get("org_id")
    user_id = data.get("user_id")
    violation_type = data.get("violation_type")
    if not (org_id and user_id and violation_type):
        return "Missing data", 400

    data_path = f"data/{org_id}/user_data.json"
    users_path = f"data/{org_id}/users.json"

    os.makedirs(os.path.dirname(data_path), exist_ok=True)

    if os.path.exists(data_path):
        with open(data_path, "r") as f:
            user_data = json.load(f)
    else:
        user_data = {}

    if user_id not in user_data:
        name = "이름 없음"
        if os.path.exists(users_path):
            with open(users_path, "r") as f:
                users = json.load(f)
                name = users.get(user_id, {}).get("name", "이름 없음")
        user_data[user_id] = {"name": name, "eye_outside_frame": 0, "face_outside_webcam_frame": 0}

    user_data[user_id][violation_type] += 1
    with open(data_path, "w") as f:
        json.dump(user_data, f)

    socketio.emit("new_violation", {
        "user_id": user_id,
        "violation_type": violation_type,
        "name": user_data[user_id]["name"]
    }, room=org_id)

    return "Violation reported", 200

# -------------------- Socket.IO 연결 --------------------

@socketio.on("join")
def on_join(data):
    org_id = data.get("org_id")
    join_room(org_id)
    print(f"Socket joined room: {org_id}")

# -------------------- 요약 --------------------

@app.route("/violation_summary")
@login_required
def violation_summary():
    org_id = current_user.org_id
    path = f"data/{org_id}/user_data.json"
    if os.path.exists(path):
        with open(path, "r") as f:
            return jsonify(json.load(f))
    else:
        return jsonify({})

# -------------------- 시작 --------------------

if __name__ == '__main__':
    socketio.run(app, host="0.0.0.0", port=5000)
