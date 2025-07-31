const socket = io();
const violationCounts = {};
const orgId = window.orgId; // 서버에서 넘겨주는 org_id 사용

// ✅ 요약 정보 불러오기
window.addEventListener("DOMContentLoaded", async () => {
  try {
    const res = await fetch(`/violation_summary/${orgId}`);
    const data = await res.json();

    for (const user_id in data) {
      const face_count = data[user_id].face_outside_webcam_frame || 0;
      const gaze_count = data[user_id].eye_outside_frame || 0;

      violationCounts[user_id] = {
        face: face_count,
        gaze: gaze_count
      };
    }

    renderViolations();  // 기존 데이터 렌더링
    document.getElementById("institutionCode").textContent = orgId;
  } catch (e) {
    console.error("요약 정보 불러오기 실패:", e);
    document.getElementById("institutionCode").textContent = "불러오기 실패";
  }
});

// ✅ 사용자 등록
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
    body: JSON.stringify({ name, exam_id: examId, org_id: orgId })
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

// ✅ 실시간 로그 수신
socket.on("violation_update", (data) => {
  console.log("📦 실시간 데이터 수신:", data);

  const user_id = data.user_id;
  const face_count = data.face ?? 0;   // ✅ 키 이름 수정
  const gaze_count = data.gaze ?? 0;   // ✅ 키 이름 수정

  if (!violationCounts[user_id]) {
    violationCounts[user_id] = { face: 0, gaze: 0 };
  }

  violationCounts[user_id].face = face_count;
  violationCounts[user_id].gaze = gaze_count;

  renderViolations();
});

// ✅ 시각화
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
