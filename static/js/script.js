// ============================================================
// STRUCTURED SESSION OBJECT
// ============================================================
class InterviewSessionClient {
  constructor(sessionData) {
    this.session_id = sessionData.session_id;
    this.question_text = sessionData.question;
    this.user_transcription = "";
    this.topic = sessionData.topic;
    this.difficulty_level = sessionData.difficulty_level;
    this.timestamp = sessionData.timestamp;
    this.posture_data = {
      duration: 0,
      stability: "Initialising",
      emotion: "Neutral",
      dominant_emotion: "Neutral",
      emotion_summary: {},
      notes: "Emotion detector starting…",
    };
  }

  updateTranscription(text) {
    this.user_transcription = text;
  }

  updateEmotionData(data) {
    this.posture_data = {
      duration: data.duration || 0,
      stability: data.stability || "Unknown",
      emotion: data.emotion || "Neutral",
      dominant_emotion: data.dominant_emotion || "Neutral",
      emotion_summary: data.emotion_summary || {},
      all_probabilities: data.all_probabilities || {},
      notes: data.notes || "",
    };
  }

  toPayload() {
    return {
      session_id: this.session_id,
      transcript: this.user_transcription,
      posture_data: this.posture_data,
    };
  }
}

// ============================================================
// AVATAR MANAGER — video (speaking) / image (idle + listening)
// ============================================================
class AvatarManager {
  constructor() {
    this.currentState = 'idle';

    // IDs for <video> elements (shown while speaking)
    this.videoIds = ['hr-avatar-setup', 'hr-avatar-main'];

    // IDs for <img> elements (shown while idle / listening)
    this.imageIds = ['hr-image-setup', 'hr-image-main'];

    // IDs for the container (for ring-pulse CSS class)
    this.containerIds = ['hr-container-setup', 'hr-container-main'];

    // IDs for the text state labels
    this.stateLabelIds = ['avatar-state-setup', 'avatar-state-main'];
  }

  // ── Internal: show video, hide image ──────────────────────
  _showVideo() {
    this.videoIds.forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      
      // Ensure video is visible and playing
      el.classList.remove('hr-media-hidden');
      el.style.opacity = '1';
      el.style.zIndex = '2';
      
      try {
        // If the video is paused or at the end, reset and play
        if (el.paused) {
          const playPromise = el.play();
          if (playPromise !== undefined) {
            playPromise.catch(err => {
              console.warn(`[Avatar] Video ${id} play failed:`, err);
            });
          }
        }
      } catch (e) {
        console.warn(`[Avatar] Video ${id} error:`, e);
      }
    });
    this.imageIds.forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        el.classList.add('hr-media-hidden');
        el.style.opacity = '0';
        el.style.zIndex = '1';
      }
    });
  }

  _showImage() {
    this.imageIds.forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        el.classList.remove('hr-media-hidden');
        el.style.opacity = '1';
        el.style.zIndex = '2';
      }
    });
    this.videoIds.forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.classList.add('hr-media-hidden');
      el.style.opacity = '0';
      el.style.zIndex = '1';
      try {
        el.pause();
        el.currentTime = 0;
      } catch (e) {
        console.warn('[Avatar] pause error:', e);
      }
    });
  }



  // ── Internal: update ring class on containers ─────────────
  _setContainerClass(cls) {
    // Find all containers by class (works even without explicit IDs)
    const containers = document.querySelectorAll('.hr-visual-container');
    containers.forEach(c => {
      c.classList.remove('is-speaking', 'is-listening');
      if (cls) c.classList.add(cls);
    });
  }

  // ── Internal: update state label text ────────────────────
  _setLabel(text, stateClass) {
    this.stateLabelIds.forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.textContent = text;
      el.className = 'avatar-state-label ' + (stateClass || 'state-idle');
    });
  }

  // ── Public: initialise after DOM ready ───────────────────
  init(id, initialState = 'speaking') {
    console.log('[Avatar] Initialised, anchor:', id);
    this.currentState = 'none'; // force re-trigger
    this.setState(initialState);
  }

  // ── Public: transition to a new state ────────────────────
  setState(state) {
    if (this.currentState === state) return;
    this.currentState = state;
    console.log('[Avatar] State →', state);

    switch (state) {
      case 'speaking':
        this._showVideo();
        this._setContainerClass('is-speaking');
        this._setLabel('Speaking…', 'state-speaking');
        break;

      case 'listening':
        this._showImage();
        this._setContainerClass('is-listening');
        this._setLabel('Listening…', 'state-listening');
        break;

      case 'idle':
      default:
        this._showImage();
        this._setContainerClass(null);
        this._setLabel('Ready', 'state-idle');
        break;
    }
  }

  // ── Public: speak text with word highlighting ─────────────
  speak(text) {
    if (!text || text.includes('Configuring')) return;

    this.setState('speaking');
    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);

    // Pick best available voice
    const voices = window.speechSynthesis.getVoices();
    const bestVoice = voices.find(v =>
      v.lang.startsWith('en') &&
      (v.name.includes('Google') || v.name.includes('Female') || v.name.includes('Samantha'))
    );
    if (bestVoice) utterance.voice = bestVoice;
    utterance.rate = 0.95;
    utterance.pitch = 1.05;

    // Word highlight
    const display = document.getElementById('question-display');
    if (display) {
      const words = text.split(' ');
      display.innerHTML = words
        .map(w => `<span style="opacity:0.5;transition:opacity 0.12s,font-weight 0.12s">${w}</span>`)
        .join(' ');

      let wordIndex = 0;
      utterance.onboundary = (event) => {
        if (event.name === 'word') {
          const spans = display.querySelectorAll('span');
          spans.forEach(s => {
            s.style.opacity = '0.5';
            s.style.fontWeight = '';
          });
          if (spans[wordIndex]) {
            spans[wordIndex].style.opacity = '1';
            spans[wordIndex].style.fontWeight = '700';
            wordIndex++;
          }
        }
      };
    }

    utterance.onend = () => {
      setTimeout(() => {
        this.setState('listening');
      }, 300);
    };


    utterance.onerror = (e) => {
      console.warn('[Avatar] Speech error:', e.error);
      this.setState('idle');
      if (display) display.innerText = text;
    };

    window.speechSynthesis.speak(utterance);
  }

  startListening() { this.setState('listening'); }
  stopListening() { this.setState('idle'); }
}

// ============================================================
// GLOBAL STATE
// ============================================================
let currentSession = null;
let recognition = null;
let videoStream = null;
let transcriptText = "";
let emotionPollTimer = null;
let recordingStartTime = null;
let timerInterval = null;
let isRecording = false;
let localEmotionHistory = {};
let emotionTotalFrames = 0;

const avatarManager = new AvatarManager();

const SpeechRecognition =
  window.SpeechRecognition || window.webkitSpeechRecognition;

const API_BASE = window.location.origin;
console.log('[SkillUp] App initialised at:', API_BASE);

// ============================================================
// DOM READY
// ============================================================
document.addEventListener('DOMContentLoaded', async function () {

  // Ensure voices load (some browsers need this event)
  window.speechSynthesis.onvoiceschanged = () => {
    console.log('[Speech] Voices loaded:', window.speechSynthesis.getVoices().length);
  };

  avatarManager.init('hr-avatar-setup');

  // Difficulty select sync
  const diffSelect = document.getElementById('difficulty-select');
  if (diffSelect) {
    diffSelect.addEventListener('change', function (e) {
      const levelEl = document.getElementById('level-display');
      if (levelEl) levelEl.textContent = e.target.options[e.target.selectedIndex].text;
    });
  }

  // Load saved resume
  try {
    const res = await fetch(`${API_BASE}/api/profile/resume`);
    if (res.ok) {
      const data = await res.json();
      const el = document.getElementById('resume-text');
      if (el) {
        el.value = data.resume_text || '';
        el.placeholder = 'Paste your resume text here or upload a PDF.';
      }
    }
  } catch (e) {
    console.error('Failed to fetch resume:', e);
  }

  // Check daily limit
  try {
    const statusRes = await fetch(`${API_BASE}/user-profile`);
    if (statusRes.ok) {
      const profile = await statusRes.json();
      if (profile.streak_info && profile.streak_info.today_status === 'Completed') {
        const startBtn = document.querySelector('button[onclick="startInterview()"]');
        if (startBtn) {
          startBtn.disabled = true;
          startBtn.innerHTML = '🏆 Today\'s Interview Completed';
          startBtn.style.opacity = '0.7';
          startBtn.style.cursor = 'not-allowed';
          startBtn.style.background = 'linear-gradient(135deg, #48cfad 0%, #1abc9c 100%)';
        }
        const introBox = document.querySelector('.avatar-intro');
        if (introBox) {
          introBox.innerText = "You've already completed today's interview. Come back tomorrow!";
          introBox.style.color = '#48cfad';
        }
      }
    }
  } catch (e) {
    console.error('Failed to check daily limit:', e);
  }
});

// ============================================================
// RESUME SAVE / UPLOAD
// ============================================================
async function saveResume() {
  const resumeText = document.getElementById('resume-text').value;
  const statusEl = document.getElementById('resume-status');
  statusEl.textContent = 'Saving...';
  try {
    const res = await fetch(`${API_BASE}/api/profile/resume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resume_text: resumeText }),
    });
    statusEl.textContent = res.ok ? 'Saved!' : 'Failed to save.';
    if (res.ok) setTimeout(() => (statusEl.textContent = ''), 2000);
  } catch (e) {
    console.error('Save resume error:', e);
    statusEl.textContent = 'Error saving.';
  }
}

async function uploadResumeFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  const statusEl = document.getElementById('resume-status');
  statusEl.textContent = 'Uploading & Extracting...';
  const formData = new FormData();
  formData.append('resume', file);
  try {
    const res = await fetch(`${API_BASE}/api/profile/resume`, { method: 'POST', body: formData });
    if (res.ok) {
      const fetchRes = await fetch(`${API_BASE}/api/profile/resume`);
      const data = await fetchRes.json();
      document.getElementById('resume-text').value = data.resume_text;
      statusEl.textContent = 'Extracted and Saved!';
      setTimeout(() => (statusEl.textContent = ''), 2000);
    } else {
      statusEl.textContent = 'Failed to process PDF.';
    }
  } catch (e) {
    console.error('Upload resume error:', e);
    statusEl.textContent = 'Error parsing PDF.';
  }
}

// ============================================================
// START INTERVIEW
// ============================================================
async function startInterview() {
  const jd = document.getElementById('jd-input').value.trim();
  const difficulty = document.getElementById('difficulty-select').value;

  if (!jd) { alert('Please enter a job description'); return; }

  showLoading(true, 'Initialising local facial analysis…');
  avatarManager.setState('speaking');

  try {
    // Load face-api models
    const MODEL_URL = '/static/models/';
    await faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL);
    await faceapi.nets.faceExpressionNet.loadFromUri(MODEL_URL);

    // Boot backend session
    const startRes = await fetch(`${API_BASE}/start-session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });

    if (startRes.status === 403) {
      const data = await startRes.json();
      alert(data.message);
      showLoading(false);
      return;
    }

    if (!startRes.ok) throw new Error('Failed to start session backend');

    showLoading(true, 'Generating your first interview question…');

    // Fetch first question
    const res = await fetch(`${API_BASE}/hr-questions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jd, level: difficulty }),
    });
    if (!res.ok) throw new Error(await res.text());

    const data = await res.json();
    currentSession = new InterviewSessionClient(data);

    updateInterviewUI(data);

    await startCamera();

    startEmotionPolling();

    document.getElementById('setup-section').style.display = 'none';
    document.getElementById('main-grid').classList.remove('hidden');

    // Re-init avatar for the main grid
    avatarManager.init('hr-avatar-main');

  } catch (e) {
    console.error('Interview start error:', e);
    alert('Failed to start interview. Please try again.');
  }

  showLoading(false);
}

function updateInterviewUI(data) {
  document.getElementById('question-display').innerText = data.question;
  document.getElementById('topic-display').innerText = data.topic;
  document.getElementById('level-display').innerText = data.difficulty_level;
  document.getElementById('session-display').innerText =
    data.session_id.substring(0, 8) + '…';

  document.getElementById('transcript-display').innerText =
    'Click "Start Recording" to begin transcription…';
  document.getElementById('feedback-section').classList.add('hidden');

  // DON'T set to idle here — we want to stay in speaking mode while the question appears
  // and then speakQuestion() will handle the transition back to listening after finishing.

  // Auto-speak new question
  setTimeout(() => speakQuestion(), 500);
}

async function nextQuestion() {
  const difficulty = document.getElementById('difficulty-select').value;
  showLoading(true, 'Generating next question…');
  avatarManager.setState('speaking');

  try {
    if (recognition) recognition.stop();
    stopEmotionPolling();

    const res = await fetch(`${API_BASE}/hr-questions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        level: difficulty,
        session_id: currentSession ? currentSession.session_id : null,
      }),
    });

    if (!res.ok) throw new Error('Failed to fetch next question');

    const data = await res.json();
    currentSession = new InterviewSessionClient(data);

    updateInterviewUI(data);
    startEmotionPolling();

    document.querySelector('.question-section').scrollIntoView({ behavior: 'smooth', block: 'start' });

  } catch (e) {
    console.error('Next question error:', e);
    alert('Failed to get next question. Please try again.');
  }

  showLoading(false);
}

// ============================================================
// CAMERA
// ============================================================
async function startCamera() {
  try {
    videoStream = await navigator.mediaDevices.getUserMedia({ video: true });
    const video = document.getElementById('video');
    video.srcObject = videoStream;
    await video.play();
    updateStatusBadge('posture-status', 'Camera Active', 'status-active');
  } catch (err) {
    console.error('Camera error:', err);
    updateStatusBadge('posture-status', 'Camera Error', 'status-error');
    alert('Camera access denied. Please enable camera permissions.');
  }
}

// ============================================================
// EMOTION POLLING (browser face-api.js)
// ============================================================
function startEmotionPolling() {
  if (emotionPollTimer) clearInterval(emotionPollTimer);
  localEmotionHistory = {};
  emotionTotalFrames = 0;

  emotionPollTimer = setInterval(async () => {
    const video = document.getElementById('video');
    if (!video || video.readyState < 2 || video.videoWidth === 0) return;

    try {
      const detection = await faceapi
        .detectSingleFace(video, new faceapi.TinyFaceDetectorOptions())
        .withFaceExpressions();

      let data = {};

      if (detection) {
        const expressions = detection.expressions;
        let maxEmotion = 'neutral', maxScore = 0;
        for (const [emo, score] of Object.entries(expressions)) {
          if (score > maxScore) { maxScore = score; maxEmotion = emo; }
        }

        emotionTotalFrames++;
        localEmotionHistory[maxEmotion] = (localEmotionHistory[maxEmotion] || 0) + 1;

        let dominant_overall = 'neutral', max_overall = 0;
        let emotion_summary = {};
        for (const [emo, count] of Object.entries(localEmotionHistory)) {
          const pct = Math.round((count / emotionTotalFrames) * 100);
          emotion_summary[emo] = pct;
          if (count > max_overall) { max_overall = count; dominant_overall = emo; }
        }

        data = {
          emotion: maxEmotion,
          confidence: +(maxScore * 100).toFixed(1),
          face_detected: true,
          all_probabilities: expressions,
          dominant_emotion: dominant_overall,
          emotion_summary,
          stability: 'Active',
          notes: 'Analysed locally',
          duration: timerInterval
            ? Math.floor((Date.now() - recordingStartTime) / 1000)
            : 0,
        };

      } else {
        data = {
          emotion: 'Unknown',
          confidence: 0,
          face_detected: false,
          all_probabilities: {},
          dominant_emotion: currentSession
            ? currentSession.posture_data.dominant_emotion
            : 'Unknown',
          emotion_summary: currentSession
            ? currentSession.posture_data.emotion_summary
            : {},
          stability: 'Face not detected',
          notes: 'No face found',
          duration: timerInterval
            ? Math.floor((Date.now() - recordingStartTime) / 1000)
            : 0,
        };
      }

      if (currentSession) currentSession.updateEmotionData(data);

      const coach = getCoaching(data.emotion);
      const label = data.face_detected
        ? `${coach.icon} ${data.emotion} — ${coach.tip.split('—')[0].split('.')[0]}`
        : '👤 No Face Detected';
      updateStatusBadge(
        'posture-status',
        label,
        data.face_detected ? 'status-active' : 'status-warning'
      );

      const panel = document.getElementById('emotion-panel');
      if (panel) panel.innerHTML = buildEmotionPanelHTML(data);

    } catch (err) {
      console.error('face-api error:', err);
    }
  }, 1000);
}

function stopEmotionPolling() {
  if (emotionPollTimer) {
    clearInterval(emotionPollTimer);
    emotionPollTimer = null;
  }
}

// ── Coaching data ──────────────────────────────────────────
const EMOTION_COACHING = {
  angry: { icon: '😤', tip: 'Take a slow breath — relax your jaw and shoulders.', extra: 'Interviewers respond best to calm, measured answers. Pause before speaking.', color: '#ff6b6b' },
  disgust: { icon: '😒', tip: 'Soften your expression — try a gentle, neutral face.', extra: 'Even a slight frown can read as disinterest. Aim for open, curious eyes.', color: '#f39c12' },
  fear: { icon: '😨', tip: "You've got this! Breathe deeply and stand tall.", extra: 'Anxiety is normal — channel it into enthusiasm for the topic.', color: '#9b59b6' },
  sad: { icon: '😔', tip: 'Lift your chin and bring energy into your voice.', extra: 'A warm, upbeat tone signals confidence even when nerves creep in.', color: '#3498db' },
  surprise: { icon: '😲', tip: 'Steady your expression — show composed confidence.', extra: 'Wide eyes or raised brows can look unsure. Settle into a calm, ready look.', color: '#1abc9c' },
  neutral: { icon: '😐', tip: 'Add a little warmth — a gentle smile goes a long way!', extra: 'Engaged eye contact and small nods show the interviewer you\'re present.', color: '#7f8c8d' },
  happy: { icon: '😊', tip: 'Great energy! Keep smiling and stay confident.', extra: 'Your positivity is coming through — maintain this throughout your answer.', color: '#2ecc71' },
};

function getCoaching(emotion) {
  const key = (emotion || 'neutral').toLowerCase();
  return EMOTION_COACHING[key] || EMOTION_COACHING['neutral'];
}

function buildEmotionPanelHTML(data) {
  const emotion = data.emotion || 'neutral';
  const coach = getCoaching(emotion);
  const dominant = data.dominant_emotion || emotion;
  const domCoach = getCoaching(dominant);

  const rows = Object.entries(data.emotion_summary || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)
    .map(([e, pct]) =>
      `<div class="emotion-row">
         <span class="emotion-label">${e}</span>
         <div class="emotion-bar-wrap"><div class="emotion-bar" style="width:${pct}%"></div></div>
         <span class="emotion-pct">${pct}%</span>
       </div>`
    ).join('');

  return `
    <div class="emotion-summary">
      <div style="background:rgba(255,255,255,0.04);border-left:3px solid ${coach.color};
                  border-radius:6px;padding:10px 12px;margin-bottom:10px;">
        <div style="font-size:1.2rem;margin-bottom:4px;">
          ${coach.icon}
          <strong style="color:${coach.color};font-size:0.85rem;margin-left:4px;">
            ${emotion.charAt(0).toUpperCase() + emotion.slice(1)} detected
          </strong>
        </div>
        <div style="color:#e0e0f0;font-size:0.88rem;font-weight:600;margin-bottom:3px;">
          ${coach.tip}
        </div>
        <div style="color:#9999bb;font-size:0.80rem;">${coach.extra}</div>
      </div>
      ${dominant.toLowerCase() !== emotion.toLowerCase() ? `
        <div style="font-size:0.78rem;color:#888aaa;margin-bottom:8px;">
          📊 Session trend: <strong style="color:${domCoach.color}">${dominant}</strong>
          — ${domCoach.tip}
        </div>` : ''}
      ${rows ? `<div style="margin-top:6px;">${rows}</div>` : ''}
    </div>`;
}

// ============================================================
// RECORDING CONTROLS
// ============================================================
function startRecording() {
  if (!SpeechRecognition) {
    alert('Speech Recognition not supported. Please use Chrome or Edge.');
    return;
  }
  if (!currentSession) {
    alert('Please start an interview session first');
    return;
  }

  // Avatar enters listening mode
  avatarManager.startListening();

  recognition = new SpeechRecognition();
  recognition.continuous = true;
  recognition.interimResults = true;
  transcriptText = '';
  recordingStartTime = Date.now();

  recognition.onresult = (e) => {
    let interimTranscript = '';
    let finalTranscript = transcriptText;

    for (let i = e.resultIndex; i < e.results.length; i++) {
      const t = e.results[i][0].transcript;
      if (e.results[i].isFinal) {
        finalTranscript += t + ' ';
      } else {
        interimTranscript += t;
      }
    }

    transcriptText = finalTranscript;
    document.getElementById('transcript-display').innerText =
      (finalTranscript + interimTranscript) || 'Listening…';

    currentSession.updateTranscription(transcriptText.trim());
  };

  recognition.onerror = (e) => {
    console.error('Recognition error:', e.error);
    if (e.error === 'no-speech') {
      updateStatusBadge('transcript-status', 'No speech detected (will keep listening)', 'status-warning');
    } else if (e.error === 'not-allowed' || e.error === 'audio-capture') {
      isRecording = false;
      updateStatusBadge('transcript-status', 'Microphone error or permission denied', 'status-error');
      toggleRecording(false);
      stopTimer();
    }
  };

  recognition.onend = () => {
    console.log('[Speech] Recognition ended.');
    if (isRecording) {
      setTimeout(() => {
        if (isRecording) {
          try { recognition.start(); }
          catch (e) { console.error('Failed to restart recording:', e); }
        }
      }, 250);
    }
  };

  try {
    isRecording = true;
    recognition.start();
    toggleRecording(true);
    startTimer();
    updateStatusBadge('transcript-status', 'Recording…', 'status-recording');
  } catch (e) {
    console.error('Failed to start recording:', e);
    alert('Failed to start recording. Please try again.');
  }
}

async function stopRecording() {
  isRecording = false;
  if (recognition) recognition.stop();

  stopTimer();
  stopEmotionPolling();
  toggleRecording(false);
  updateStatusBadge('transcript-status', 'Processing…', 'status-processing');

  // Avatar back to idle
  avatarManager.stopListening();

  currentSession.updateTranscription(transcriptText.trim());

  if (!transcriptText.trim()) {
    alert('No transcription detected. Please try recording again.');
    updateStatusBadge('transcript-status', 'Ready', 'status-inactive');
    return;
  }

  await analyzeResponse();
}

// ============================================================
// ANALYSIS
// ============================================================
async function analyzeResponse() {
  showLoading(true, 'Saving your response…');

  try {
    const payload = currentSession.toPayload();
    console.log('[Submit] Payload:', payload);

    const res = await fetch(`${API_BASE}/submit-answer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) throw new Error('Analysis failed');

    document.getElementById('feedback-display').innerHTML =
      '<b>Response Saved Successfully!</b><br><br>' +
      'Click <i>Next Question</i> to proceed or click <i>Finish Interview</i> ' +
      'if you are ready to evaluate your overall performance.';
    document.getElementById('feedback-section').classList.remove('hidden');
    document.getElementById('feedback-section').scrollIntoView({ behavior: 'smooth', block: 'start' });

  } catch (e) {
    console.error('Submission error:', e);
    alert('Failed to save response. Please try again.');
  }

  showLoading(false);
  updateStatusBadge('transcript-status', 'Answer Saved', 'status-active');
}

async function finishInterview() {
  showLoading(true, 'Compiling your final comprehensive HR Evaluation… (This may take up to 2 minutes)');
  try {
    const res = await fetch(`${API_BASE}/finish-interview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: currentSession.session_id }),
    });

    if (!res.ok) throw new Error('Failed evaluating');
    const data = await res.json();
    window.location.href = `/feedback/${data.session_id}`;
  } catch (e) {
    alert('Error fetching final performance review.');
  }
  showLoading(false);
}

// ============================================================
// UTILITY FUNCTIONS
// ============================================================
function startTimer() {
  document.getElementById('recording-timer').classList.remove('hidden');
  timerInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
    const mm = Math.floor(elapsed / 60).toString().padStart(2, '0');
    const ss = (elapsed % 60).toString().padStart(2, '0');
    document.getElementById('timer-display').textContent = `${mm}:${ss}`;
    if (currentSession) currentSession.posture_data.duration = elapsed;
  }, 1000);
}

function stopTimer() {
  if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
  document.getElementById('recording-timer').classList.add('hidden');
}

function toggleRecording(recording) {
  document.getElementById('record-btn').classList.toggle('hidden', recording);
  document.getElementById('stop-btn').classList.toggle('hidden', !recording);
  document.getElementById('recording-indicator').classList.toggle('hidden', !recording);
}

function updateStatusBadge(elementId, text, statusClass) {
  const el = document.getElementById(elementId);
  if (el) { el.textContent = text; el.className = 'status-badge ' + statusClass; }
}

function showLoading(show, text = 'Processing…') {
  const loadingEl = document.getElementById('loading');
  if (show) {
    loadingEl.classList.remove('hidden');
    document.querySelector('.loading-text').textContent = text;
  } else {
    loadingEl.classList.add('hidden');
  }
}

function formatFeedback(feedback) {
  return feedback
    .replace(/## (.*?)(\n|$)/g, '<h3>$1</h3>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/- (.*?)(\n|$)/g, '<li>$1</li>')
    .replace(/(<li>[\s\S]*?<\/li>)/g, '<ul>$1</ul>')
    .replace(/\n/g, '<br>');
}

async function resetInterview() {
  isRecording = false;
  if (videoStream) videoStream.getTracks().forEach(t => t.stop());
  if (recognition) recognition.stop();
  stopEmotionPolling();
  stopTimer();

  try { await fetch(`${API_BASE}/stop-session`, { method: 'POST' }); } catch (_) { }

  currentSession = null;
  transcriptText = '';
  location.reload();
}

// ============================================================
// VOICE SYNTHESIS
// ============================================================
function speakQuestion() {
  const text = document.getElementById('question-display').innerText;

  if (!text || text.includes('Configuring')) return;

  // FORCE speaking state BEFORE speech starts
  avatarManager.setState('speaking');

  // small delay ensures UI updates before audio starts
  setTimeout(() => {
    avatarManager.speak(text);
  }, 200);
}


function stopSpeaking() {
  if (window.speechSynthesis.speaking) {
    window.speechSynthesis.cancel();
    const btn = document.getElementById('speak-btn');
    if (btn) btn.classList.remove('speaking');
    avatarManager.setState('idle');
    console.log('[Speech] Stopped by user.');
  }
}

// ============================================================
// GLOBAL ERROR HANDLING
// ============================================================
window.addEventListener('error', e => console.error('Global error:', e.error));
window.addEventListener('unhandledrejection', e => console.error('Unhandled rejection:', e.reason));