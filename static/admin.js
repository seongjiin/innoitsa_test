window.addEventListener("DOMContentLoaded", async () => {
  try {
    const res = await fetch("/violation_summary");
    const data = await res.json();

    for (const user_id in data) {
      const face_count = data[user_id].face_out || 0;
      const gaze_count = data[user_id].gaze_out || 0;

      violationCounts[user_id] = {
        face: face_count,
        gaze: gaze_count
      };
    }

    renderViolations();  // 기존 데이터를 테이블에 반영
  } catch (e) {
    console.error("위반 현황 로딩 실패:", e);
  }
});


const socket = io();
const violationCounts = {};

// 🚨 사용자 실시간 위반 로그 표시
function renderViolations() {
  const container = document.getElementById("violation-log");
  container.innerHTML = "";

  for (const userId in violationCounts) {
    const { face, gaze } = violationCounts[userId];

    const entry = document.createElement("div");
    entry.className = "entry";
    entry.innerHTML = `
      <div class="user-id">🧑 사용자 ${userId}</div>
      <div class="counts">👁️ 시선 이탈: ${gaze ?? 0}회<br>📷 얼굴 이탈: ${face ?? 0}회</div>
    `;
    container.appendChild(entry);
  }
}

// 📡 실시간 업데이트 수신
socket.on("violation_update", (data) => {
  console.log("📦 실시간 데이터 수신:", data);

  const user_id = data.user_id;
  const face_count = data.face_count ?? 0;
  const gaze_count = data.gaze_count ?? 0;

  // 누적 방식으로 저장
  if (!violationCounts[user_id]) {
    violationCounts[user_id] = { face: 0, gaze: 0 };
  }

  violationCounts[user_id].face += face_count;
  violationCounts[user_id].gaze += gaze_count;

  renderViolations();
});

// ✅ 사용자 등록 요청
function registerUser() {
  const name = document.getElementById("name").value.trim();
  const examId = document.getElementById("exam_id").value.trim();

  if (!name || !examId) {
    alert("이름과 수험번호를 모두 입력하세요.");
    return;
  }

  fetch("/register_user", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, exam_id: examId })
  })
  .then((res) => res.json())
  .then((data) => {
    alert(data.message || "등록 완료");
    document.getElementById("name").value = "";
    document.getElementById("exam_id").value = "";
  })
  .catch((err) => {
    console.error("등록 실패:", err);
    alert("서버 오류로 등록에 실패했습니다.");
  });
}

// ✅ 기관 고유 ID 불러오기
fetch("/institution_id")
  .then((res) => res.json())
  .then((data) => {
    document.getElementById("institutionCode").textContent = data.id;
  })
  .catch(() => {
    document.getElementById("institutionCode").textContent = "불러오기 실패";
  });
