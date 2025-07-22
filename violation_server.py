import os
import json
import string
import random
import sqlite3
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_socketio import SocketIO

# -------------------- 설정 --------------------
BASE_DATA_DIR = "data"
TEMPLATES_DIR = "templates"
STATIC_DIR = "static"
USERS_FILE_NAME = "users.json"
DB_FILE_NAME = "violation_logs.db"

# -------------------- 기관 디렉토리 초기화 --------------------
def init_org_data():
    org_file = "org_id.txt"
    if os.path.exists(org_file):
        with open(org_file, "r") as f:
            org_id = f.read().strip()
    else:
        org_id = generate_org_id()
        with open(org_file, "w") as f:
            f.write(org_id)

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

    return org_id

# ✅ 이제 호출해도 안전함
ORG_ID = init_org_data()

DATA_DIR = os.path.join(os.getcwd(), "data")
os.makedirs(DATA_DIR, exist_ok=True)

DATA_FILE = os.path.join(DATA_DIR, ORG_ID, "user_data.json")


BASE_DATA_DIR = "data"
TEMPLATES_DIR = "templates"
STATIC_DIR = "static"
USERS_FILE_NAME = "users.json"
DB_FILE_NAME = "violation_logs.db"

app = Flask(__name__, template_folder=TEMPLATES_DIR, static_folder=STATIC_DIR)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# -------------------- 고유 ID 생성 --------------------

def generate_org_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


# -------------------- 관리자 페이지 --------------------

@app.route("/admin")
def admin_page():
    # ✅ 접속 시마다 user_data.json 초기화
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f, ensure_ascii=False, indent=2)

    return render_template("admin.html", org_id=ORG_ID)


# -------------------- 기관 ID 조회 --------------------

@app.route("/institution_id")
def institution_id():
    return jsonify({"id": ORG_ID})

@app.route("/generate_org_id", methods=["POST"])
def generate_new_org_id():
    new_org_id = generate_org_id()
    org_path = os.path.join(BASE_DATA_DIR, new_org_id)
    os.makedirs(org_path, exist_ok=True)

    # 기본 데이터 초기화
    with open(os.path.join(org_path, "users.json"), "w", encoding="utf-8") as f:
        json.dump([], f, ensure_ascii=False, indent=2)
    with open(os.path.join(org_path, "user_data.json"), "w", encoding="utf-8") as f:
        json.dump({}, f, ensure_ascii=False, indent=2)

    # org_id.txt 파일 업데이트
    with open("org_id.txt", "w") as f:
        f.write(new_org_id)

    global ORG_ID, DATA_FILE
    ORG_ID = new_org_id
    DATA_FILE = os.path.join(BASE_DATA_DIR, ORG_ID, "user_data.json")

    print(f"✅ 새 기관 고유 ID 생성: {ORG_ID}")
    return jsonify({"org_id": ORG_ID})


# -------------------- 사용자 등록 --------------------

@app.route("/register_user", methods=["POST"])
def register_user():
    data = request.get_json()
    name = data.get("name")
    exam_id = data.get("exam_id")

    if not name or not exam_id:
        return jsonify({"status": "error", "message": "이름 또는 수험번호 누락"}), 400

    user_entry = {"id": exam_id, "name": name}
    users_path = os.path.join(BASE_DATA_DIR, ORG_ID, USERS_FILE_NAME)

    with open(users_path, "r", encoding="utf-8") as f:
        users = json.load(f)

    users = [u for u in users if u["id"] != exam_id]
    users.append(user_entry)

    with open(users_path, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

    return jsonify({"status": "success", "message": f"{name} 등록 완료"})

# -------------------- 실시간 위반 로그 전송 예시 (선택 사항) --------------------
# 예시용 소켓 이벤트
@socketio.on("send_violation")
def handle_violation(data):
    # data = { "user_id": "1234", "face_count": 2, "gaze_count": 1 }
    socketio.emit("violation_update", data)

# -------------------- 위반 기록 수신 및 중계 --------------------


@app.route('/report_violation', methods=['POST'])
def report_violation():
    data = request.get_json()
    print("🚨 위반 보고 도착:", data)  # ⭐️⭐️⭐️ 확인용 로그
    user_id = data.get('user_id')
    violation_type = data.get('type')

    # 👉 이 부분 추가!
    socketio.emit("violation_update", {
        "user_id": data["user_id"],
        "face_count": 1 if data["type"] == "face_outside_webcam_frame" else 0,
        "gaze_count": 1 if data["type"] == "eye_outside_frame" else 0,
    })
    
    if not user_id or not violation_type:
        return jsonify({"error": "Invalid data"}), 400

    # 데이터 파일 로드
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            admin_data = json.load(f)
    else:
        admin_data = {}

    if user_id not in admin_data:
        admin_data[user_id] = {}

    if violation_type not in admin_data[user_id]:
        admin_data[user_id][violation_type] = 0

    admin_data[user_id][violation_type] += 1

    # 👉 여기서 소켓으로 관리자 페이지에 실시간 전송
    face_count = admin_data[user_id].get("face_out", 0)
    gaze_count = admin_data[user_id].get("gaze_out", 0)
    socketio.emit("violation_update", {
        "user_id": user_id,
        "face": face_count,   # ✅ 수정됨
        "gaze": gaze_count    # ✅ 수정됨
    })


    # 파일 저장
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(admin_data, f, ensure_ascii=False, indent=2)

    return jsonify({"status": "success"}), 200

@app.route('/violation_summary')
def violation_summary():
    if not os.path.exists(DATA_FILE):
        return jsonify({})
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify(data)

# -------------------- 실행 --------------------

if __name__ == "__main__":
    print(f"✅ 기관 고유 ID: {ORG_ID}")
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))