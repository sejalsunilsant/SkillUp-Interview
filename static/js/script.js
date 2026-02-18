// ============================================================
// STRUCTURED SESSION OBJECT
// ============================================================
class InterviewSessionClient {
  constructor(sessionData) {
    this.session_id         = sessionData.session_id;
    this.question_text      = sessionData.question;
    this.user_transcription = "";
    this.topic              = sessionData.topic;
    this.difficulty_level   = sessionData.difficulty_level;
    this.timestamp          = sessionData.timestamp;
    // Emotion data is now populated by polling /emotion-status
    this.posture_data = {
      duration:         0,
      stability:        "Initialising",
      emotion:          "Neutral",
      dominant_emotion: "Neutral",
      emotion_summary:  {},
      notes:            "Emotion detector starting…",
    };
  }

  updateTranscription(text) {
    this.user_transcription = text;
  }

  // Called by the emotion polling loop
  updateEmotionData(data) {
    this.posture_data = {
      duration:           data.duration          || 0,
      stability:          data.stability         || "Unknown",
      emotion:            data.emotion           || "Neutral",
      dominant_emotion:   data.dominant_emotion  || "Neutral",
      emotion_summary:    data.emotion_summary   || {},
      all_probabilities:  data.all_probabilities || {},
      notes:              data.notes             || "",
    };
  }

  toPayload() {
    return {
      session_id:      this.session_id,
      transcript:      this.user_transcription,
      posture_data:    this.posture_data,
    };
  }
}

// ============================================================
// GLOBAL STATE
// ============================================================
let currentSession   = null;
let recognition      = null;
let videoStream      = null;
let transcriptText   = "";
let emotionPollTimer = null;   // replaces postureInterval
let recordingStartTime = null;
let timerInterval    = null;

const SpeechRecognition =
  window.SpeechRecognition || window.webkitSpeechRecognition;

const API_BASE = "http://127.0.0.1:5000";

// ============================================================
// INITIALIZATION
// ============================================================
document.addEventListener("DOMContentLoaded", function () {
  document.getElementById("difficulty-select").addEventListener("change", function (e) {
    document.getElementById("level-display").textContent =
      e.target.options[e.target.selectedIndex].text;
  });
});

// ============================================================
// START INTERVIEW
// ============================================================
async function startInterview() {
  const topic      = document.getElementById("topic-input").value.trim();
  const difficulty = document.getElementById("difficulty-select").value;

  if (!topic) {
    alert("Please enter an interview topic");
    return;
  }

  document.getElementById("level-display").textContent =
    document.getElementById("difficulty-select").options[
      document.getElementById("difficulty-select").selectedIndex
    ].text;

  showLoading(true, "Starting emotion detector…");

  try {
    // ── 1. Boot Python emotion detector ──────────────────────────────────────
    const startRes = await fetch(`${API_BASE}/start-session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    if (!startRes.ok) throw new Error("Failed to start emotion detector");

    showLoading(true, "Generating your interview question…");

    // ── 2. Fetch question & create session ────────────────────────────────────
    const res = await fetch(`${API_BASE}/hr-questions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, level: difficulty, count: 1 }),
    });
    if (!res.ok) throw new Error(await res.text());

    const data     = await res.json();
    currentSession = new InterviewSessionClient(data);

    // ── 3. Update UI ──────────────────────────────────────────────────────────
    document.getElementById("question-display").innerText  = currentSession.question_text;
    document.getElementById("topic-display").innerText     = currentSession.topic;
    document.getElementById("level-display").innerText     = currentSession.difficulty_level;
    document.getElementById("session-display").innerText   =
      currentSession.session_id.substring(0, 8) + "…";

    // ── 4. Camera (display only – Python handles analysis) ───────────────────
    await startCamera();

    // ── 5. Start emotion polling ──────────────────────────────────────────────
    startEmotionPolling();

    document.getElementById("setup-section").style.display = "none";
    document.getElementById("main-grid").classList.remove("hidden");

  } catch (e) {
    console.error("Interview start error:", e);
    alert("Failed to start interview. Please try again.");
  }

  showLoading(false);
}

// ============================================================
// CAMERA  (display only – no JS analysis)
// ============================================================
async function startCamera() {
  try {
    videoStream = await navigator.mediaDevices.getUserMedia({ video: true });
    const video = document.getElementById("video");
    video.srcObject = videoStream;
    await video.play();
    updateStatusBadge("posture-status", "Camera Active", "status-active");
  } catch (err) {
    console.error("Camera error:", err);
    updateStatusBadge("posture-status", "Camera Error", "status-error");
    alert("Camera access denied. Please enable camera permissions.");
  }
}

// ============================================================
// EMOTION POLLING  — browser sends frames to /detect-emotion
// ============================================================
function startEmotionPolling() {
  if (emotionPollTimer) clearInterval(emotionPollTimer);

  emotionPollTimer = setInterval(async () => {
    const video = document.getElementById("video");
    if (!video || video.readyState < 2 || video.videoWidth === 0) return;

    // Capture current frame from the live video element
    const canvas = document.createElement("canvas");
    canvas.width  = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    const imageDataUrl = canvas.toDataURL("image/jpeg", 0.8);

    try {
      const res = await fetch(`${API_BASE}/detect-emotion`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ image: imageDataUrl }),
      });
      if (!res.ok) return;
      const raw = await res.json();

      // /detect-emotion returns confidence 0-1; convert to % for display
      const data = {
        emotion:          raw.emotion          || "Unknown",
        confidence:       raw.confidence != null ? +(raw.confidence * 100).toFixed(1) : 0,
        face_detected:    raw.face_detected    || false,
        all_probabilities: raw.all_probabilities || {},
        // These accumulate server-side; fetch from /emotion-status in parallel
        dominant_emotion: raw.dominant_emotion || raw.emotion || "Unknown",
        emotion_summary:  raw.emotion_summary  || {},
        stability:        raw.stability        || "Analyzing",
        notes:            raw.notes            || "",
        duration:         raw.duration         || 0,
      };

      // Also fetch the running session stats (dominant emotion, history %)
      const statsRes = await fetch(`${API_BASE}/emotion-status`);
      if (statsRes.ok) {
        const stats = await statsRes.json();
        data.dominant_emotion = stats.dominant_emotion || data.dominant_emotion;
        data.emotion_summary  = stats.emotion_summary  || data.emotion_summary;
        data.stability        = stats.stability        || data.stability;
        data.duration         = stats.duration         || data.duration;
        data.notes            = stats.notes            || data.notes;
      }

      if (currentSession) currentSession.updateEmotionData(data);

      // Update posture-status badge with coaching icon
      const coach    = getCoaching(data.emotion);
      const label    = data.face_detected
        ? `${coach.icon} ${data.emotion} — ${coach.tip.split("—")[0].split(".")[0]}`
        : `👤 No Face Detected`;
      updateStatusBadge("posture-status", label, data.face_detected ? "status-active" : "status-warning");

      // Update emotion panel
      const emotionPanel = document.getElementById("emotion-panel");
      if (emotionPanel) emotionPanel.innerHTML = buildEmotionPanelHTML(data);

    } catch (err) {
      // Network error — don't flood console
    }
  }, 1500);  // send a frame every 1.5 s
}

function stopEmotionPolling() {
  if (emotionPollTimer) {
    clearInterval(emotionPollTimer);
    emotionPollTimer = null;
  }
}

// Coaching tips keyed by detected emotion
const EMOTION_COACHING = {
  angry:     {
    icon:  "😤",
    tip:   "Take a slow breath — relax your jaw and shoulders.",
    extra: "Interviewers respond best to calm, measured answers. Pause before speaking.",
    color: "#ff6b6b",
  },
  disgust:   {
    icon:  "😒",
    tip:   "Soften your expression — try a gentle, neutral face.",
    extra: "Even a slight frown can read as disinterest. Aim for open, curious eyes.",
    color: "#f39c12",
  },
  fear:      {
    icon:  "😨",
    tip:   "You've got this! Breathe deeply and stand tall.",
    extra: "Anxiety is normal — channel it into enthusiasm for the topic.",
    color: "#9b59b6",
  },
  sad:       {
    icon:  "😔",
    tip:   "Lift your chin and bring energy into your voice.",
    extra: "A warm, upbeat tone signals confidence even when nerves creep in.",
    color: "#3498db",
  },
  surprise:  {
    icon:  "😲",
    tip:   "Steady your expression — show composed confidence.",
    extra: "Wide eyes or raised brows can look unsure. Settle into a calm, ready look.",
    color: "#1abc9c",
  },
  neutral:   {
    icon:  "😐",
    tip:   "Add a little warmth — a gentle smile goes a long way!",
    extra: "Engaged eye contact and small nods show the interviewer you're present.",
    color: "#7f8c8d",
  },
  happy:     {
    icon:  "😊",
    tip:   "Great energy! Keep smiling and stay confident.",
    extra: "Your positivity is coming through — maintain this throughout your answer.",
    color: "#2ecc71",
  },
};

function getCoaching(emotion) {
  const key = (emotion || "neutral").toLowerCase();
  return EMOTION_COACHING[key] || EMOTION_COACHING["neutral"];
}

/** Build coaching-instruction panel instead of raw emotion bars */
function buildEmotionPanelHTML(data) {
  const emotion  = data.emotion || "neutral";
  const coach    = getCoaching(emotion);
  const dominant = data.dominant_emotion || emotion;
  const domCoach = getCoaching(dominant);

  // Emotion history bars (kept small, secondary)
  const rows = Object.entries(data.emotion_summary || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)
    .map(([e, pct]) =>
      `<div class="emotion-row">
         <span class="emotion-label">${e}</span>
         <div class="emotion-bar-wrap">
           <div class="emotion-bar" style="width:${pct}%"></div>
         </div>
         <span class="emotion-pct">${pct}%</span>
       </div>`
    ).join("");

  return `
    <div class="emotion-summary">

      <!-- Live coaching instruction -->
      <div style="
        background: rgba(255,255,255,0.04);
        border-left: 3px solid ${coach.color};
        border-radius: 6px;
        padding: 10px 12px;
        margin-bottom: 10px;
      ">
        <div style="font-size:1.2rem; margin-bottom:4px;">${coach.icon}
          <strong style="color:${coach.color}; font-size:0.85rem; margin-left:4px;">
            ${emotion.charAt(0).toUpperCase() + emotion.slice(1)} detected
          </strong>
        </div>
        <div style="color:#e0e0f0; font-size:0.88rem; font-weight:600; margin-bottom:3px;">
          ${coach.tip}
        </div>
        <div style="color:#9999bb; font-size:0.80rem;">
          ${coach.extra}
        </div>
      </div>

      <!-- Dominant-emotion coaching (if different from live) -->
      ${dominant.toLowerCase() !== emotion.toLowerCase() ? `
      <div style="font-size:0.78rem; color:#888aaa; margin-bottom:8px;">
        📊 Session trend: <strong style="color:${domCoach.color}">${dominant}</strong>
        — ${domCoach.tip}
      </div>` : ""}

      <!-- History breakdown bars -->
      ${rows ? `<div style="margin-top:6px;">${rows}</div>` : ""}
    </div>`;
}

// ============================================================
// RECORDING CONTROLS
// ============================================================
function startRecording() {
  if (!SpeechRecognition) {
    alert("Speech Recognition not supported. Please use Chrome or Edge.");
    return;
  }
  if (!currentSession) {
    alert("Please start an interview session first");
    return;
  }

  recognition               = new SpeechRecognition();
  recognition.continuous    = true;
  recognition.interimResults= true;
  recognition.lang          = "en-US";

  transcriptText     = "";
  recordingStartTime = Date.now();

  recognition.onresult = (e) => {
    let interimTranscript = "";
    let finalTranscript   = transcriptText;

    for (let i = e.resultIndex; i < e.results.length; i++) {
      const t = e.results[i][0].transcript;
      if (e.results[i].isFinal) {
        finalTranscript += t + " ";
      } else {
        interimTranscript += t;
      }
    }

    transcriptText = finalTranscript;
    document.getElementById("transcript-display").innerText =
      (finalTranscript + interimTranscript) || "Listening…";

    currentSession.updateTranscription(transcriptText.trim());
  };

  recognition.onerror = (e) => {
    console.error("Recognition error:", e.error);
    if (e.error === "no-speech") {
      updateStatusBadge("transcript-status", "No speech detected", "status-warning");
    }
  };

  recognition.onend = () => console.log("Speech recognition ended");

  try {
    recognition.start();
    toggleRecording(true);
    startTimer();
    updateStatusBadge("transcript-status", "Recording…", "status-recording");
  } catch (e) {
    console.error("Failed to start recording:", e);
    alert("Failed to start recording. Please try again.");
  }
}

async function stopRecording() {
  if (recognition) recognition.stop();

  stopTimer();
  stopEmotionPolling();

  toggleRecording(false);
  updateStatusBadge("transcript-status", "Processing…", "status-processing");

  currentSession.updateTranscription(transcriptText.trim());

  if (!transcriptText.trim()) {
    alert("No transcription detected. Please try recording again.");
    updateStatusBadge("transcript-status", "Ready", "status-inactive");
    return;
  }

  await analyzeResponse();
}

// ============================================================
// ANALYSIS
// ============================================================
async function analyzeResponse() {
  showLoading(true, "Analysing your interview response…");

  try {
    const payload = currentSession.toPayload();
    console.log("Sending structured payload:", payload);

    const res = await fetch(`${API_BASE}/evaluate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) throw new Error("Analysis failed");

    const data = await res.json();

    document.getElementById("feedback-display").innerHTML =
      formatFeedback(data.feedback);
    document.getElementById("feedback-section").classList.remove("hidden");
    document.getElementById("feedback-section").scrollIntoView({
      behavior: "smooth",
      block: "start",
    });

  } catch (e) {
    console.error("Analysis error:", e);
    alert("Failed to analyse response. Please try again.");
  }

  showLoading(false);
  updateStatusBadge("transcript-status", "Analysis Complete", "status-active");
}

// ============================================================
// UTILITY FUNCTIONS
// ============================================================
function startTimer() {
  const timerElement = document.getElementById("recording-timer");
  timerElement.classList.remove("hidden");

  timerInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
    const mm = Math.floor(elapsed / 60).toString().padStart(2, "0");
    const ss = (elapsed % 60).toString().padStart(2, "0");
    document.getElementById("timer-display").textContent = `${mm}:${ss}`;
    if (currentSession) {
      currentSession.posture_data.duration = elapsed;
    }
  }, 1000);
}

function stopTimer() {
  if (timerInterval) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
  document.getElementById("recording-timer").classList.add("hidden");
}

function toggleRecording(recording) {
  document.getElementById("record-btn").classList.toggle("hidden", recording);
  document.getElementById("stop-btn").classList.toggle("hidden", !recording);
  document.getElementById("recording-indicator").classList.toggle("hidden", !recording);
}

function updateStatusBadge(elementId, text, statusClass) {
  const el = document.getElementById(elementId);
  if (el) {
    el.textContent = text;
    el.className   = "status-badge " + statusClass;
  }
}

function showLoading(show, text = "Processing…") {
  const loadingEl = document.getElementById("loading");
  if (show) {
    loadingEl.classList.remove("hidden");
    document.querySelector(".loading-text").textContent = text;
  } else {
    loadingEl.classList.add("hidden");
  }
}

function formatFeedback(feedback) {
  return feedback
    .replace(/## (.*?)(\n|$)/g, "<h3>$1</h3>")
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/- (.*?)(\n|$)/g, "<li>$1</li>")
    .replace(/(<li>[\s\S]*?<\/li>)/g, "<ul>$1</ul>")
    .replace(/\n/g, "<br>");
}

async function resetInterview() {
  // Stop all streams
  if (videoStream)      videoStream.getTracks().forEach((t) => t.stop());
  if (recognition)      recognition.stop();
  stopEmotionPolling();
  stopTimer();

  // Tell backend to stop detector
  try {
    await fetch(`${API_BASE}/stop-session`, { method: "POST" });
  } catch (_) {}

  currentSession = null;
  transcriptText = "";
  location.reload();
}

// ============================================================
// ERROR HANDLING
// ============================================================
window.addEventListener("error", (e)              => console.error("Global error:", e.error));
window.addEventListener("unhandledrejection", (e)  => console.error("Unhandled rejection:", e.reason));