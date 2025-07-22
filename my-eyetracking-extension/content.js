// -------------------- 사용자 ID 설정 --------------------

let userId = localStorage.getItem('eyetracking_user_id');
if (!userId) {
  userId = prompt("🆔 사용자 ID를 입력하세요 (예: 수험번호):");
  if (userId) {
    localStorage.setItem('eyetracking_user_id', userId);
  } else {
    alert("❌ 사용자 ID가 필요합니다. 새로고침 후 다시 시도하세요.");
    throw new Error("사용자 ID가 설정되지 않았습니다.");
  }
}

// -------------------- 상태 플래그 --------------------

let isCalibrating = true;  // ✅ 캘리브레이션 중 여부

// -------------------- 서버 전송 함수 --------------------

function reportViolation(type = "unknown") {
  fetch("https://innoitsa-test.onrender.com/report_violation", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      user_id: userId,
      timestamp: new Date().toISOString(),
      event: "violation_detected",
      type: type
    })
  }).then(res => {
    if (!res.ok) console.error("🚨 서버로 위반 보고 실패", res.status);
  }).catch(err => {
    console.error("❌ 서버 통신 오류:", err);
  });
}

// -------------------- WebGazer 초기화 --------------------

webgazer.clearData(); // ✅ 초기화: 이전 캘리브레이션, gaze 데이터 제거

if (typeof webgazer !== 'undefined') {
  console.log("WebGazer.js is loaded in content script.");

  let lastSentTime = 0;

  webgazer.setGazeListener(function(data, elapsedTime) {
    if (!data) return;

    const now = Date.now();
    if (now - lastSentTime < 500) return;
    lastSentTime = now;

    chrome.runtime.sendMessage({
      type: "gazeData",
      x: data.x,
      y: data.y
    });

    checkGazePosition(data.x, data.y);  // 👈 시선 감지

  }).begin();

  webgazer.showPredictionPoints(true);
  webgazer.showVideo(true);

} else {
  console.error("WebGazer.js is not defined. Make sure it's loaded correctly.");
}

// -------------------- Calibration Logic --------------------

const calibrationPoints = [
  [10, 10], [45, 10], [80, 10],
  [10, 45], [45, 45], [80, 45],
  [10, 80], [45, 80], [80, 80],
  [25, 25], [65, 25], [45, 70]
];

let currentCalibrationIndex = 0;
const requiredClicksPerDot = 5;
let clickCount = 0;

function createCalibrationDot(left, top) {
  const dot = document.createElement('div');
  dot.style.position = 'fixed';
  dot.style.width = '30px';
  dot.style.height = '30px';
  dot.style.borderRadius = '50%';
  dot.style.backgroundColor = 'red';
  dot.style.zIndex = 99999;
  dot.style.left = `${left}vw`;
  dot.style.top = `${top}vh`;
  dot.style.cursor = 'pointer';
  dot.style.boxShadow = '0 0 10px rgba(255, 0, 0, 0.8)';
  dot.id = 'calibration-dot';
  dot.title = `이 점을 ${requiredClicksPerDot}번 클릭해 주세요`;

  dot.addEventListener('click', () => {
    const x = (left / 100) * window.innerWidth;
    const y = (top / 100) * window.innerHeight;

    webgazer.recordScreenPosition(x, y, 'click');
    clickCount++;

    dot.style.backgroundColor = `rgba(255, 0, 0, ${1 - (clickCount / requiredClicksPerDot) * 0.7})`;

    if (clickCount >= requiredClicksPerDot) {
      dot.remove();
      currentCalibrationIndex++;
      clickCount = 0;

      if (currentCalibrationIndex < calibrationPoints.length) {
        const [nextLeft, nextTop] = calibrationPoints[currentCalibrationIndex];
        createCalibrationDot(nextLeft, nextTop);
      } else {
        alert("✅ 캘리브레이션 완료! 시선 추적이 시작됩니다.");
        isCalibrating = false;
        removeSafeFrameOverlay();  // ✅ 프레임 제거
      }
    }
  });

  document.body.appendChild(dot);
}

createCalibrationDot(...calibrationPoints[currentCalibrationIndex]);

// -------------------- 얼굴 인식 상태 경고 감지 --------------------

function monitorFaceDetection() {
  const faceBox = document.querySelector('#webgazerFaceFeedbackBox');
  if (!faceBox) {
    console.warn("⚠️ 얼굴 인식 박스를 찾을 수 없습니다.");
    return;
  }

  setInterval(() => {
    if (isCalibrating) return;  // ✅ 캘리브레이션 중에는 무시
    const borderColor = window.getComputedStyle(faceBox).borderColor;
    if (borderColor === 'rgb(255, 0, 0)') {
      showWarning("face_outside_webcam_frame");
    }
  }, 500);
}

// -------------------- 시선이 안전 프레임을 벗어나면 경고 --------------------

const gazeTimeout = 1000;
let gazeOutsideSince = null;

const safeFrame = {
  left: 50,
  right: window.innerWidth - 50,
  top: 100,
  bottom: window.innerHeight - 100
};

function createSafeFrameOverlay() {
  const overlay = document.createElement('div');
  overlay.id = 'safe-frame-overlay';
  overlay.style.position = 'fixed';
  overlay.style.left = `${safeFrame.left}px`;
  overlay.style.top = `${safeFrame.top}px`;
  overlay.style.width = `${safeFrame.right - safeFrame.left}px`;
  overlay.style.height = `${safeFrame.bottom - safeFrame.top}px`;
  overlay.style.border = '2px dashed limegreen';
  overlay.style.zIndex = 99998;
  overlay.style.pointerEvents = 'none';
  document.body.appendChild(overlay);
}

function removeSafeFrameOverlay() {
  const overlay = document.getElementById('safe-frame-overlay');
  if (overlay) overlay.remove();
}

function checkGazePosition(x, y) {
  if (isCalibrating) return;  // ✅ 캘리브레이션 중에는 검사 안 함

  const isOutside = (
    x < safeFrame.left || x > safeFrame.right ||
    y < safeFrame.top || y > safeFrame.bottom
  );

  const now = Date.now();

  if (isOutside) {
    if (!gazeOutsideSince) {
      gazeOutsideSince = now;
    } else if (now - gazeOutsideSince >= gazeTimeout) {
      showWarning("eye_outside_frame");
    }
  } else {
    gazeOutsideSince = null;
    hideWarning();
  }
}

// -------------------- 경고 메시지 공통 함수 --------------------

const warningId = 'face-or-gaze-warning';

function showWarning(type = "unknown") {
  if (!document.getElementById(warningId)) {
    const warning = document.createElement('div');
    warning.id = warningId;
    warning.innerText = "⚠️ 집중하세요! 얼굴 또는 시선이 벗어났습니다!";
    warning.style.position = 'fixed';
    warning.style.top = '10px';
    warning.style.left = '50%';
    warning.style.transform = 'translateX(-50%)';
    warning.style.padding = '12px 20px';
    warning.style.backgroundColor = 'rgba(255, 0, 0, 0.85)';
    warning.style.color = 'white';
    warning.style.fontSize = '18px';
    warning.style.borderRadius = '10px';
    warning.style.zIndex = 100000;
    warning.style.boxShadow = '0 0 10px rgba(0,0,0,0.3)';
    document.body.appendChild(warning);

    reportViolation(type);
  }
}

function hideWarning() {
  const existing = document.getElementById(warningId);
  if (existing) existing.remove();
}

// -------------------- 초기 실행 --------------------

window.addEventListener('load', () => {
  setTimeout(() => {
    createSafeFrameOverlay();   // ✅ 처음엔 프레임 보이게
    monitorFaceDetection();
  }, 3000);
});
