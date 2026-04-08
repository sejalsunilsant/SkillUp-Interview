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
let isRecording      = false;
let localEmotionHistory = {};
let emotionTotalFrames = 0;

const SpeechRecognition =
  window.SpeechRecognition || window.webkitSpeechRecognition;

const API_BASE = "http://127.0.0.1:5000";

// ============================================================
// INITIALIZATION
// ============================================================
document.addEventListener("DOMContentLoaded", async function () {
  const diffSelect = document.getElementById("difficulty-select");
  if (diffSelect) {
    diffSelect.addEventListener("change", function (e) {
      document.getElementById("level-display").textContent =
        e.target.options[e.target.selectedIndex].text;
    });
  }

  // Fetch resume on load
  try {
    const res = await fetch(`${API_BASE}/api/profile/resume`);
    if (res.ok) {
      const data = await res.json();
      const resumeTextEl = document.getElementById("resume-text");
      if (resumeTextEl) {
          resumeTextEl.value = data.resume_text || "";
          resumeTextEl.placeholder = "Paste your resume text here or upload a PDF.";
      }
    }
  } catch (e) {
    console.error("Failed to fetch resume:", e);
  }
});

async function saveResume() {
  const resumeText = document.getElementById("resume-text").value;
  const statusEl = document.getElementById("resume-status");
  statusEl.textContent = "Saving...";
  try {
    const res = await fetch(`${API_BASE}/api/profile/resume`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resume_text: resumeText })
    });
    if (res.ok) {
      statusEl.textContent = "Saved!";
      setTimeout(() => statusEl.textContent = "", 2000);
    } else {
      statusEl.textContent = "Failed to save.";
    }
  } catch (e) {
    console.error("Save resume error:", e);
    statusEl.textContent = "Error saving.";
  }
}

async function uploadResumeFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  
  const statusEl = document.getElementById("resume-status");
  statusEl.textContent = "Uploading & Extracting...";
  
  const formData = new FormData();
  formData.append("resume", file);
  
  try {
    const res = await fetch(`${API_BASE}/api/profile/resume`, {
      method: "POST",
      body: formData
    });
    if (res.ok) {
      // Refresh textarea
      const fetchRes = await fetch(`${API_BASE}/api/profile/resume`);
      const data = await fetchRes.json();
      document.getElementById("resume-text").value = data.resume_text;
      statusEl.textContent = "Extracted and Saved!";
      setTimeout(() => statusEl.textContent = "", 2000);
    } else {
      statusEl.textContent = "Failed to process PDF.";
    }
  } catch (e) {
    console.error("Upload resume error:", e);
    statusEl.textContent = "Error parsing PDF.";
  }
}

// ============================================================
// START INTERVIEW
// ============================================================
async function startInterview() {
  const jd         = document.getElementById("jd-input").value.trim();
  const difficulty = document.getElementById("difficulty-select").value;

  if (!jd) {
    alert("Please enter a job description");
    return;
  }

  showLoading(true, "Initializing local facial analysis...");

  try {
    const MODEL_URL = '/static/models/';
    await faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL);
    await faceapi.nets.faceExpressionNet.loadFromUri(MODEL_URL);

    // ── 1. Boot Python emotion detector (optional cleanup/state) ──────────────────────────────────────
    const startRes = await fetch(`${API_BASE}/start-session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    if (!startRes.ok) throw new Error("Failed to start session backend");

    showLoading(true, "Generating your first interview question…");

    // ── 2. Fetch question & create session using JSON ─────────────────────
    const res = await fetch(`${API_BASE}/hr-questions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jd: jd, level: difficulty })
    });
    if (!res.ok) throw new Error(await res.text());

    const data     = await res.json();
    currentSession = new InterviewSessionClient(data);

    // ── 3. Update UI ──────────────────────────────────────────────────────────
    updateInterviewUI(data);

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

function updateInterviewUI(data) {
    document.getElementById("question-display").innerText  = data.question;
    document.getElementById("topic-display").innerText     = data.topic;
    document.getElementById("level-display").innerText     = data.difficulty_level;
    document.getElementById("session-display").innerText   =
      data.session_id.substring(0, 8) + "…";
    
    // Clear previous transcript and feedback
    document.getElementById("transcript-display").innerText = "Click \"Start Recording\" to begin transcription…";
    document.getElementById("feedback-section").classList.add("hidden");

    // Automatically speak the new question
    setTimeout(() => speakQuestion(), 500);
}

async function nextQuestion() {
    const difficulty = document.getElementById("difficulty-select").value;
    showLoading(true, "Generating next question…");
    
    try {
        // Stop current session polling and recording if active
        if (recognition) recognition.stop();
        stopEmotionPolling();
        
        // Fetch new question (backend uses session-stored JD/Resume)
        const res = await fetch(`${API_BASE}/hr-questions`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ level: difficulty, session_id: currentSession ? currentSession.session_id : null })
        });
        
        if (!res.ok) throw new Error("Failed to fetch next question");
        
        const data = await res.json();
        currentSession = new InterviewSessionClient(data);
        
        // Update UI
        updateInterviewUI(data);
        
        // Restart emotion polling for new question
        startEmotionPolling();
        
        // Scroll to question
        document.querySelector(".question-section").scrollIntoView({
            behavior: "smooth",
            block: "start"
        });
        
    } catch (e) {
        console.error("Next question error:", e);
        alert("Failed to get next question. Please try again.");
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
// EMOTION POLLING  — browser uses face-api.js locally
// ============================================================
function startEmotionPolling() {
  if (emotionPollTimer) clearInterval(emotionPollTimer);

  localEmotionHistory = {};
  emotionTotalFrames = 0;

  emotionPollTimer = setInterval(async () => {
    const video = document.getElementById("video");
    if (!video || video.readyState < 2 || video.videoWidth === 0) return;

    try {
      const detection = await faceapi.detectSingleFace(video, new faceapi.TinyFaceDetectorOptions()).withFaceExpressions();
      let data = {};
      if (detection) {
        // Find dominant emotion
        const expressions = detection.expressions;
        let maxEmotion = "neutral";
        let maxScore = 0;
        for (const [emo, score] of Object.entries(expressions)) {
          if (score > maxScore) {
            maxScore = score;
            maxEmotion = emo;
          }
        }
        
        emotionTotalFrames++;
        localEmotionHistory[maxEmotion] = (localEmotionHistory[maxEmotion] || 0) + 1;
        
        let dominant_overall = "neutral";
        let max_overall = 0;
        let emotion_summary = {};
        for (const [emo, count] of Object.entries(localEmotionHistory)) {
          const pct = Math.round((count / emotionTotalFrames) * 100);
          emotion_summary[emo] = pct;
          if (count > max_overall) {
            max_overall = count;
            dominant_overall = emo;
          }
        }
        
        data = {
          emotion: maxEmotion,
          confidence: +(maxScore * 100).toFixed(1),
          face_detected: true,
          all_probabilities: expressions,
          dominant_emotion: dominant_overall,
          emotion_summary: emotion_summary,
          stability: "Active",
          notes: "Analyzed locally",
          duration: timerInterval ? Math.floor((Date.now() - recordingStartTime) / 1000) : 0,
        };
      } else {
        data = {
          emotion: "Unknown",
          confidence: 0,
          face_detected: false,
          all_probabilities: {},
          dominant_emotion: currentSession ? currentSession.posture_data.dominant_emotion : "Unknown",
          emotion_summary: currentSession ? currentSession.posture_data.emotion_summary : {},
          stability: "Face not detected",
          notes: "No face found",
          duration: timerInterval ? Math.floor((Date.now() - recordingStartTime) / 1000) : 0,
        };
      }

      if (currentSession) currentSession.updateEmotionData(data);

      const coach    = getCoaching(data.emotion);
      const label    = data.face_detected
        ? `${coach.icon} ${data.emotion} — ${coach.tip.split("—")[0].split(".")[0]}`
        : `👤 No Face Detected`;
      updateStatusBadge("posture-status", label, data.face_detected ? "status-active" : "status-warning");

      const emotionPanel = document.getElementById("emotion-panel");
      if (emotionPanel) emotionPanel.innerHTML = buildEmotionPanelHTML(data);

    } catch (err) {
      console.error("Local face-api error:", err);
    }
  }, 1000);  // analyze every 1 second
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

  recognition = new SpeechRecognition();
  recognition.continuous = true;
  recognition.interimResults= true;
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
      updateStatusBadge("transcript-status", "No speech detected (will keep listening)", "status-warning");
    } else if (e.error === "not-allowed" || e.error === "audio-capture") {
      isRecording = false;
      updateStatusBadge("transcript-status", "Microphone error or permission denied", "status-error");
      toggleRecording(false);
      stopTimer();
    }
  };

  recognition.onend = () => {
    console.log("Speech recognition ended.");
    if (isRecording) {
      console.log("Restarting speech recognition...");
      setTimeout(() => {
        if (isRecording) {
          try {
            recognition.start();
          } catch (e) {
            console.error("Failed to restart recording:", e);
          }
        }
      }, 250); // Small delay to prevent 'already started' DOMException
    }
  };

  try {
    isRecording = true;
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
  isRecording = false;
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
  showLoading(true, "Saving your response…");

  try {
    const payload = currentSession.toPayload();
    console.log("Sending structured payload:", payload);

    const res = await fetch(`${API_BASE}/submit-answer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) throw new Error("Analysis failed");

    const data = await res.json();

    document.getElementById("feedback-display").innerHTML =
      "<b>Response Saved Successfully!</b><br><br>Click <i>Next Question</i> to proceed or click <i>Finish Interview</i> if you are ready to evaluate your overall performance.";
    document.getElementById("feedback-section").classList.remove("hidden");
    document.getElementById("feedback-section").scrollIntoView({
      behavior: "smooth",
      block: "start",
    });

  } catch (e) {
    console.error("Submission error:", e);
    alert("Failed to save response. Please try again.");
  }

  showLoading(false);
  updateStatusBadge("transcript-status", "Answer Saved", "status-active");
}

async function finishInterview() {
  showLoading(true, "Compiling your final comprehensive HR Evaluation… (This may take up to 2 minutes)");
  try {
    const res = await fetch(`${API_BASE}/finish-interview`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ session_id: currentSession.session_id })
    });
    
    if (!res.ok) throw new Error("Failed evaluating");
    const data = await res.json();
    
    // Redirect to the new feedback page
    window.location.href = `/feedback/${data.session_id}`;
  } catch(e) {
    alert("Error fetching final performance review.");
  }
  showLoading(false);
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
  isRecording = false;
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
// VOICE SYNTHESIS (Speak Question)
// ============================================================
function speakQuestion() {
  const text = document.getElementById("question-display").innerText;
  if (!text || text.includes("Configuring")) return;

  // Cancel any ongoing speech
  window.speechSynthesis.cancel();

  const utterance = new SpeechSynthesisUtterance(text);
  
  // Try to find a professional sounding English voice
  const voices = window.speechSynthesis.getVoices();
  const preferredVoice = voices.find(v => 
    v.lang.startsWith('en') && (v.name.includes('Google') || v.name.includes('Female'))
  );
  
  if (preferredVoice) utterance.voice = preferredVoice;
  
  utterance.pitch = 1.0;
  utterance.rate = 0.95; // Slightly slower for clarity

  const btn = document.getElementById("speak-btn");
  
  utterance.onstart = () => {
    if (btn) btn.classList.add("speaking");
  };
  
  utterance.onend = () => {
    if (btn) btn.classList.remove("speaking");
  };

  utterance.onerror = () => {
    if (btn) btn.classList.remove("speaking");
  };

  window.speechSynthesis.speak(utterance);
}

/** Stop ongoing speech synthesis */
function stopSpeaking() {
  if (window.speechSynthesis.speaking) {
    window.speechSynthesis.cancel();
    const btn = document.getElementById("speak-btn");
    if (btn) btn.classList.remove("speaking");
    console.log("Speech stopped by user.");
  }
}

// Ensure voices are loaded (some browsers need this)
window.speechSynthesis.onvoiceschanged = () => {
  console.log("Speech synthesis voices loaded.");
};

// ============================================================
// ERROR HANDLING
// ============================================================
window.addEventListener("error", (e)              => console.error("Global error:", e.error));
window.addEventListener("unhandledrejection", (e)  => console.error("Unhandled rejection:", e.reason));