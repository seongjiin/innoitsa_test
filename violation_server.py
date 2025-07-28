import os
import json
import string
import random
import sqlite3
import hashlib
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_cors import CORS
from flask_socketio import SocketIO

# -------------------- 설정 --------------------
BASE_DATA_DIR = "data"
TEMPLATES_DIR = "templates"
STATIC_DIR = "static"
USERS_FILE_NAME = "users.json"
DB_FILE_NAME = "violation_logs.db"
ADMIN_DB_FILE = "admin_users.db"
SECRET_KEY = "supersecretkey"

# -------------------- Flask 설정 --------------------
app = Flask(__name__, template_folder=TEMPLATES_DIR, static_folder=STATIC_DIR)
app.secret_key = SECRET_KEY
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")


# -------------------- 헬퍼 함수 --------------------
def generate_org_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def init_admin_db():
    conn = sqlite3.connect(ADMIN_DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            org_id TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def create_org_directory(org_id):
    org_dir = os.path.join(BASE_DATA_DIR, org_id)
    os.makedirs(org_dir, exist_ok=True)

    users_path = os.path.join(org_dir, USERS_FILE_NAME)
    if not os.path.exists(users_path):
        with open(users_path, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)

    db_path = os.path.join(org_dir, DB_FILE_NAME)
    if not os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE violations (
                user_id TEXT PRIMARY KEY,
                face_out_count INTEGER DEFAULT 0,
                gaze_out_count INTEGER DEFAULT 0
            )
        ''')
        conn.commit()
        conn.close()


# -------------------- 관리자 회원가입 --------------------
@app.route("/signup", methods=["POST"])
def signup():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"status": "error", "message": "이메일과 비밀번호 필요"}), 400

    org_id = generate_org_id()
    create_org_directory(org_id)
    hashed_pw = hash_password(password)

    try:
        conn = sqlite3.connect(ADMIN_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO admins (email, password, org_id) VALUES (?, ?, ?)", (email, hashed_pw, org_id))
        conn.commit()
        conn.close()
    except sqlite3.IntegrityError:
        return jsonify({"status": "error", "message": "이미 존재하는 이메일"}), 409

    return jsonify({"status": "success", "org_id": org_id})


# -------------------- 관리자 로그인 --------------------
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    hashed_pw = hash_password(password)

    conn = sqlite3.connect(ADMIN_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT org_id FROM admins WHERE email = ? AND password = ?", (email, hashed_pw))
    row = cursor.fetchone()
    conn.close()

    if row:
        session["org_id"] = row[0]
        return jsonify({"status": "success", "org_id": row[0]})
    else:
        return jsonify({"status": "error", "message": "로그인 실패"}), 401

# -------------------- 아무말 출력 --------------------
@app.route("/")
def index():
    return "✅ 서버가 정상적으로 실행 중입니다."

# -------------------- 대시보드 --------------------
@app.route("/dashboard/<org_id>")
def dashboard(org_id):
    org_path = os.path.join(BASE_DATA_DIR, org_id, "user_data.json")
    if not os.path.exists(org_path):
        with open(org_path, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)
    return render_template("admin.html", org_id=org_id)


# -------------------- 사용자 등록 --------------------
@app.route("/register_user", methods=["POST"])
def register_user():
    data = request.get_json()
    name = data.get("name")
    exam_id = data.get("exam_id")
    org_id = data.get("org_id")

    if not name or not exam_id or not org_id:
        return jsonify({"status": "error", "message": "정보 누락"}), 400

    user_entry = {"id": exam_id, "name": name}
    users_path = os.path.join(BASE_DATA_DIR, org_id, USERS_FILE_NAME)

    if not os.path.exists(users_path):
        return jsonify({"status": "error", "message": "존재하지 않는 기관"}), 404

    with open(users_path, "r", encoding="utf-8") as f:
        users = json.load(f)

    users = [u for u in users if u["id"] != exam_id]
    users.append(user_entry)

    with open(users_path, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

    return jsonify({"status": "success", "message": f"{name} 등록 완료"})


# -------------------- 위반 보고 --------------------
@app.route("/report_violation", methods=["POST"])
def report_violation():
    data = request.get_json()
    user_id = data.get('user_id')
    violation_type = data.get('type')
    org_id = data.get('org_id')

    if not user_id or not violation_type or not org_id:
        return jsonify({"error": "필수 데이터 누락"}), 400

    data_file = os.path.join(BASE_DATA_DIR, org_id, "user_data.json")

    if os.path.exists(data_file):
        with open(data_file, 'r', encoding='utf-8') as f:
            admin_data = json.load(f)
    else:
        admin_data = {}

    if user_id not in admin_data:
        admin_data[user_id] = {}

    if violation_type not in admin_data[user_id]:
        admin_data[user_id][violation_type] = 0

    admin_data[user_id][violation_type] += 1

    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(admin_data, f, ensure_ascii=False, indent=2)

    socketio.emit("violation_update", {
        "user_id": user_id,
        "violation_type": violation_type,
        "count": admin_data[user_id][violation_type]
    })

    return jsonify({"status": "success"}), 200


# -------------------- 요약 조회 --------------------
@app.route('/violation_summary/<org_id>')
def violation_summary(org_id):
    data_file = os.path.join(BASE_DATA_DIR, org_id, "user_data.json")
    if not os.path.exists(data_file):
        return jsonify({})
    with open(data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify(data)


# -------------------- 서버 실행 --------------------
if __name__ == "__main__":
    init_admin_db()
    print("✅ 서버 시작됨")
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
