const API_URL = 'http://localhost:5000/api';
let videoStream = null, recognitionInterval = null;
let currentAudioBase64 = "", isAvatarBusy = false;

// 1. LEFT SIDE: CAMERA
document.querySelector('.btn-teal').addEventListener('click', async function() {
    if (videoStream) { stopCamera(); this.innerHTML = "Start Camera"; return; }
    try {
        videoStream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
        const video = document.createElement('video');
        video.autoplay = true; video.srcObject = videoStream;
        document.querySelector('.video-container').innerHTML = '';
        document.querySelector('.video-container').appendChild(video);
        this.innerHTML = "Stop Camera";
        this.classList.replace('btn-teal', 'btn-red');
        startAI(video);
    } catch (e) { alert('Camera access denied'); }
});

function stopCamera() {
    if(videoStream) videoStream.getTracks().forEach(t => t.stop());
    videoStream = null; clearInterval(recognitionInterval);
}

async function startAI(videoElement) {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    recognitionInterval = setInterval(async () => {
        if (!videoStream || isAvatarBusy) return;
        canvas.width = 320; canvas.height = 240;
        ctx.drawImage(videoElement, 0, 0, 320, 240);
        const frameData = canvas.toDataURL('image/jpeg', 0.4);

        try {
            const resp = await fetch(`${API_URL}/recognize-gesture`, {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ frame: frameData })
            });
            const data = await resp.json();
            if (data.success) {
                const textOutput = document.querySelector('.text-output');
                textOutput.classList.remove('empty');
                if (data.is_final) {
                    textOutput.innerHTML = `
                        <div style="background:#eef2ff; padding:15px; border-left:5px solid #22c55e; border-radius:10px;">
                            <strong style="font-size:18px;">"${data.gesture}"</strong><br>
                            <hr style="border:0; border-top:1px solid #e2e8f0; margin:10px 0;">
                            <strong style="color:#27ae60; font-size:26px; display:block; text-align:right;">${data.urdu_text}</strong>
                        </div>`;
                    currentAudioBase64 = data.audio;
                    if(data.audio) new Audio("data:audio/mp3;base64," + data.audio).play();
                } else {
                    textOutput.innerHTML = `<strong>${data.interim.toUpperCase().replace(/_/g, ' ')}</strong><br><span>Drop hands to finish...</span>`;
                }
            }
        } catch (e) {}
    }, 200); 
}

// Manual Voice Play
document.querySelector('.btn-green').addEventListener('click', () => {
    if (currentAudioBase64) new Audio("data:audio/mp3;base64," + currentAudioBase64).play();
    else alert("Sign a sentence first!");
});

// 2. RIGHT SIDE: VOICE RECORDING (FIXED)
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const voiceEngine = SpeechRecognition ? new SpeechRecognition() : null;

if (voiceEngine) {
    document.getElementById('startRecBtn').addEventListener('click', () => {
        voiceEngine.start();
        document.querySelector('.recording-status').innerHTML = 'Listening...';
    });
    voiceEngine.onresult = (e) => { document.querySelector('.text-input').value = e.results[0][0].transcript; };
}

// 3. RIGHT SIDE: AVATAR
document.querySelector('.btn-orange').addEventListener('click', async function() {
    const text = document.querySelector('.text-input').value.trim();
    if (!text) return;
    isAvatarBusy = true;
    const avatarBox = document.querySelectorAll('.video-container')[1];
    avatarBox.innerHTML = "<span>Interpreting...</span>";

    try {
        const resp = await fetch(`${API_URL}/text-to-sign`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ text })
        });
        const data = await resp.json();
        if (data.success && data.sequence.length > 0) {
            for (const item of data.sequence) {
                await new Promise((res) => {
                    avatarBox.innerHTML = `
                        <div style="position:absolute;top:10px;left:10px;background:rgba(0,0,0,0.7);color:white;padding:5px;z-index:10;border-radius:10px;">SIGN: ${item.word.toUpperCase()}</div>
                        <video autoplay muted style="width:100%;height:100%;object-fit:cover;border-radius:16px;">
                            <source src="${item.url}" type="video/mp4">
                        </video>`;
                    const v = avatarBox.querySelector('video');
                    v.onended = res; v.onerror = res;
                });
            }
            avatarBox.innerHTML = `<div class="video-placeholder"><span>Complete</span></div>`;
        } else { alert("Sign not found."); }
    } catch (e) { alert("Server error."); }
    isAvatarBusy = false;
});