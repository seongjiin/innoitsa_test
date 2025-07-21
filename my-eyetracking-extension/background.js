// background.js

chrome.runtime.onMessage.addListener(function(message, sender, sendResponse) {
    if (message.type === "gazeData") {
        console.log("🧿 시선 좌표 수신:", message.x, message.y);

        // 이전에는 서버로 좌표 전송했지만 지금은 필요 없음
        // fetch("http://localhost:5000/eyedata", {
        //     method: "POST",
        //     headers: {
        //         "Content-Type": "application/json"
        //     },
        //     body: JSON.stringify({
        //         x: message.x,
        //         y: message.y
        //     })
        // }).then(response => {
        //     if (!response.ok) {
        //         console.error("⚠️ 서버 응답 오류:", response.status);
        //     }
        // }).catch(error => {
        //     console.error("❌ 서버 전송 실패:", error);
        // });
    }
});
