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
      stability: 'Good',
      samples: 0,
      notes: ''
    };
  }

  updateTranscription(text) {
    this.user_transcription = text;
  }

  updatePostureData(data) {
    this.posture_data = { ...this.posture_data, ...data };
  }

  toPayload() {
    return {
      session_id: this.session_id,
      question_text: this.question_text,
      user_transcription: this.user_transcription,
      topic: this.topic,
      difficulty_level: this.difficulty_level,
      timestamp: this.timestamp,
      posture_data: this.posture_data
    };
  }
}

// ============================================================
// GLOBAL STATE
// ============================================================
let currentSession = null;
let recognition = null;
let videoStream = null;
let transcriptText = "";
let postureInterval = null;
let recordingStartTime = null;
let timerInterval = null;

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

// ============================================================
// INITIALIZATION
// ============================================================
document.addEventListener('DOMContentLoaded', function() {
  document.getElementById('difficulty-select').addEventListener('change', function(e) {
    document.getElementById('level-display').textContent = 
      e.target.options[e.target.selectedIndex].text;
  });
});

// ============================================================
// START INTERVIEW - CREATE SESSION
// ============================================================
async function startInterview() {
  const topic = document.getElementById("topic-input").value.trim();
  const difficulty = document.getElementById("difficulty-select").value;

  if (!topic) {
    alert('Please enter an interview topic');
    return;
  }

  document.getElementById('level-display').textContent = 
    document.getElementById("difficulty-select").options[
      document.getElementById("difficulty-select").selectedIndex
    ].text;
  
  showLoading(true, 'Generating your interview question...');

  try {
    // Create new interview session
    const res = await fetch("http://127.0.0.1:5000/hr-questions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
        topic: topic, 
        level: difficulty, 
        count: 1 
      })
    });

    if (!res.ok) {
      const err = await res.text();
      throw new Error(err);
    }


    const data = await res.json();
    
    // Create immutable session object
    currentSession = new InterviewSessionClient(data);
    
    // Update UI with session data
    document.getElementById("question-display").innerText = currentSession.question_text;
    document.getElementById("topic-display").innerText = currentSession.topic;
    document.getElementById("level-display").innerText = currentSession.difficulty_level;
    document.getElementById("session-display").innerText = 
      currentSession.session_id.substring(0, 8) + '...';

    // Initialize camera
    await startCamera();
    
    // Show main interface
    document.getElementById('setup-section').style.display = 'none';
    document.getElementById('main-grid').classList.remove('hidden');
    
  } catch (e) {
    console.error('Interview start error:', e);
    alert('Failed to start interview. Please try again.');
  }
  
  showLoading(false);
}

// ============================================================
// CAMERA & POSTURE ANALYSIS
// ============================================================
async function startCamera() {
  try {
    videoStream = await navigator.mediaDevices.getUserMedia({ video: true });
    const video = document.getElementById("video");
    video.srcObject = videoStream;
    await video.play();
    
    startPostureAnalysis();
    updateStatusBadge('posture-status', 'Camera Active', 'status-active');
    
  } catch (err) {
    console.error('Camera error:', err);
    updateStatusBadge('posture-status', 'Camera Error', 'status-error');
    alert('Camera access denied. Please enable camera permissions.');
  }
}

function startPostureAnalysis() {
  const canvas = document.getElementById('canvas');
  const ctx = canvas.getContext('2d');
  const video = document.getElementById('video');
  
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;

  let stableCount = 0;
  let sampleCount = 0;

  postureInterval = setInterval(() => {
    if (video.videoWidth > 0) {
      ctx.drawImage(video, 0, 0);
      const headY = canvas.height * 0.3;
      const sampleColor = ctx.getImageData(canvas.width / 2, headY, 1, 1).data;
      
      // Simple skin tone detection
      if (sampleColor[0] > 50 && sampleColor[1] > 50) {
        stableCount++;
      }
      sampleCount++;

      const stability = stableCount > sampleCount * 0.7 ? 'Stable' : 'Unstable';
      
      currentSession.updatePostureData({
        samples: sampleCount,
        stability: stability,
        notes: 'Head position tracked'
      });
    }
  }, 1000);
}

// ============================================================
// RECORDING CONTROLS
// ============================================================
function startRecording() {
  if (!SpeechRecognition) {
    alert('Speech Recognition not supported in this browser. Please use Chrome or Edge.');
    return;
  }

  if (!currentSession) {
    alert('Please start an interview session first');
    return;
  }

  recognition = new SpeechRecognition();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = 'en-US';
  
  transcriptText = "";
  recordingStartTime = Date.now();

  recognition.onresult = (e) => {
    let interimTranscript = '';
    let finalTranscript = transcriptText;

    for (let i = e.resultIndex; i < e.results.length; i++) {
      const transcript = e.results[i][0].transcript;
      if (e.results[i].isFinal) {
        finalTranscript += transcript + ' ';
      } else {
        interimTranscript += transcript;
      }
    }

    transcriptText = finalTranscript;
    const displayText = finalTranscript + interimTranscript;
    
    document.getElementById("transcript-display").innerText = 
      displayText || "Listening...";
    
    currentSession.updateTranscription(transcriptText.trim());
  };

  recognition.onerror = (e) => {
    console.error('Recognition error:', e.error);
    if (e.error === 'no-speech') {
      updateStatusBadge('transcript-status', 'No speech detected', 'status-warning');
    }
  };

  recognition.onend = () => {
  console.log("Speech recognition ended");
};


  try {
    recognition.start();
    toggleRecording(true);
    startTimer();
    updateStatusBadge('transcript-status', 'Recording...', 'status-recording');
  } catch (e) {
    console.error('Failed to start recording:', e);
    alert('Failed to start recording. Please try again.');
  }
}

async function stopRecording() {
  if (recognition) {
    recognition.stop();
  }
  
  clearInterval(postureInterval);
  stopTimer();
  
  toggleRecording(false);
  updateStatusBadge('transcript-status', 'Processing...', 'status-processing');
  
  // Finalize session data
  currentSession.updateTranscription(transcriptText.trim());
  
  if (!transcriptText.trim()) {
    alert('No transcription detected. Please try recording again.');
    updateStatusBadge('transcript-status', 'Ready', 'status-inactive');
    return;
  }

  await analyzeResponse();
}

// ============================================================
// ANALYSIS - SEND STRUCTURED PAYLOAD
// ============================================================
async function analyzeResponse() {
  showLoading(true, 'Analyzing your interview response...');
  
  try {
    // Prepare structured payload
    const payload = {
      session_id: currentSession.session_id,
      transcript: currentSession.user_transcription,
      posture_data: currentSession.posture_data
    };

    console.log('Sending structured payload:', payload);

    const res = await fetch("http://127.0.0.1:5000/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) throw new Error('Analysis failed');

    const data = await res.json();
    
    // Display feedback
    document.getElementById("feedback-display").innerHTML = 
      formatFeedback(data.feedback);
    document.getElementById("feedback-section").classList.remove("hidden");
    
    // Scroll to feedback
    document.getElementById("feedback-section").scrollIntoView({ 
      behavior: 'smooth', 
      block: 'start' 
    });
    
  } catch (e) {
    console.error('Analysis error:', e);
    alert('Failed to analyze response. Please try again.');
  }
  
  showLoading(false);
  updateStatusBadge('transcript-status', 'Analysis Complete', 'status-active');
}

// ============================================================
// UTILITY FUNCTIONS
// ============================================================
function startTimer() {
  const timerDisplay = document.getElementById('timer-display');
  const timerElement = document.getElementById('recording-timer');
  timerElement.classList.remove('hidden');

  timerInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
    const minutes = Math.floor(elapsed / 60).toString().padStart(2, '0');
    const seconds = (elapsed % 60).toString().padStart(2, '0');
    timerDisplay.textContent = `${minutes}:${seconds}`;
    
    currentSession.updatePostureData({ duration: elapsed });
  }, 1000);
}

function stopTimer() {
  if (timerInterval) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
  document.getElementById('recording-timer').classList.add('hidden');
}

function toggleRecording(recording) {
  document.getElementById("record-btn").classList.toggle("hidden", recording);
  document.getElementById("stop-btn").classList.toggle("hidden", !recording);
  document.getElementById("recording-indicator").classList.toggle("hidden", !recording);
}

function updateStatusBadge(elementId, text, statusClass) {
  const element = document.getElementById(elementId);
  element.textContent = text;
  element.className = 'status-badge ' + statusClass;
}

function showLoading(show, text = 'Processing...') {
  const loadingElement = document.getElementById("loading");
  const mainGrid = document.getElementById("main-grid");
  
  if (show) {
    loadingElement.classList.remove("hidden");
    document.querySelector('.loading-text').textContent = text;
  } else {
    loadingElement.classList.add("hidden");
  }
}

function formatFeedback(feedback) {
  // Convert markdown-style feedback to HTML
  return feedback
      .replace(/## (.*?)(\n|$)/g, '<h3>$1</h3>')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/- (.*?)(\n|$)/g, '<li>$1</li>')
      .replace(/(<li>[\s\S]*?<\/li>)/g, '<ul>$1</ul>')
      .replace(/\n/g, '<br>');
}

function resetInterview() {
  // Stop all streams
  if (videoStream) {
    videoStream.getTracks().forEach(track => track.stop());
  }
  if (recognition) {
    recognition.stop();
  }
  if (postureInterval) {
    clearInterval(postureInterval);
  }
  if (timerInterval) {
    clearInterval(timerInterval);
  }
  
  // Reset state
  currentSession = null;
  transcriptText = "";
  
  // Reload page
  location.reload();
}

// ============================================================
// ERROR HANDLING
// ============================================================
window.addEventListener('error', function(e) {
  console.error('Global error:', e.error);
});

window.addEventListener('unhandledrejection', function(e) {
  console.error('Unhandled promise rejection:', e.reason);
});