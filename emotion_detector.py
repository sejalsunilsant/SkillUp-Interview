import threading
import time
import os

# Must be set BEFORE tensorflow/fer is imported
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

import tensorflow as tf
tf.get_logger().setLevel('ERROR')

# Silence Keras per-batch progress bars globally
import absl.logging
absl.logging.set_verbosity(absl.logging.ERROR)

from fer import FER
from collections import deque, Counter


class EmotionDetector:
    """
    Frame-based emotion detector.
    The browser owns the camera and POSTs JPEG frames to /detect-emotion.
    This class receives those frames via process_frame() - no camera thread needed.
    """

    def __init__(
        self,
        smooth_window=10,
        min_confidence=0.40,
        # Kept for API compatibility but ignored:
        camera_index=0,
        show_preview=False,
    ):
        self.smooth_window   = smooth_window
        self.min_confidence  = min_confidence

        print("Loading FER model...")
        self.detector = FER(mtcnn=True)
        print("FER model loaded successfully")

        # Silence Keras "1/1 ━━━━ 0s 75ms/step" progress bars.
        # The attribute is name-mangled to _FER__emotion_classifier.
        try:
            _orig_predict = self.detector._FER__emotion_classifier.predict
            def _silent_predict(x, *args, **kwargs):
                kwargs.setdefault("verbose", 0)
                return _orig_predict(x, *args, **kwargs)
            self.detector._FER__emotion_classifier.predict = _silent_predict
        except Exception:
            pass  # If FER internals change, just skip silencing

        self._running    = False
        self.start_time  = None
        self.lock        = threading.Lock()

        self.current_emotion = {}
        self.emotion_history = []
        self.emotion_buffer  = deque(maxlen=self.smooth_window)

    # ------------------------------------------------------------------
    # Lifecycle - kept so app.py start/stop calls still work
    # ------------------------------------------------------------------

    def start(self):
        """Mark detector as active; no camera thread needed."""
        if self._running:
            return
        self._running   = True
        self.start_time = time.time()
        print("Emotion detector ready (frame-based mode)")

    def stop(self):
        """Reset state."""
        self._running        = False
        self.current_emotion = {}
        self.emotion_history = []
        self.emotion_buffer.clear()
        print("Emotion detector stopped")

    def is_running(self):
        return self._running

    # ------------------------------------------------------------------
    # Core - called by /detect-emotion with a frame from the browser
    # ------------------------------------------------------------------

    def process_frame(self, frame):
        """
        Analyse a single BGR frame (numpy array from cv2.imdecode).
        Updates internal history and returns the result dict.
        """
        try:
            results = self.detector.detect_emotions(frame)

            if not results:
                with self.lock:
                    self.current_emotion = {
                        "emotion": "No Face",
                        "confidence": 0,
                        "face_detected": False,
                    }
                return self.current_emotion.copy()

            emotions   = results[0]["emotions"]
            emotion    = max(emotions, key=emotions.get)
            confidence = emotions[emotion]

            result = {
                "emotion":           emotion,
                "confidence":        float(confidence),
                "face_detected":     True,
                "all_probabilities": emotions,
            }

            if confidence >= self.min_confidence:
                with self.lock:
                    self.emotion_buffer.append(emotion)
                    self.emotion_history.append(emotion)
                    self.current_emotion = result
            else:
                with self.lock:
                    self.current_emotion = result

            return result

        except Exception as e:
            err = {
                "emotion":       "Error",
                "confidence":    0,
                "face_detected": False,
                "error":         str(e),
            }
            with self.lock:
                self.current_emotion = err
            return err

    # ------------------------------------------------------------------
    # Live status - polled by /emotion-status
    # ------------------------------------------------------------------

    def get_current_emotion(self):
        with self.lock:
            duration = int(time.time() - self.start_time) if self.start_time else 0
            return {
                "emotion":           self.current_emotion.get("emotion", "Waiting..."),
                "confidence":        self.current_emotion.get("confidence", 0),
                "face_detected":     self.current_emotion.get("face_detected", False),
                "stability":         self._get_stability(),
                "notes":             "Live detection running",
                "duration":          duration,
                "dominant_emotion":  self._get_dominant_emotion(),
                "emotion_summary":   self._get_emotion_percentages(),
                "all_probabilities": self.current_emotion.get("all_probabilities", {}),
            }

    # ------------------------------------------------------------------
    # Session summary - called at evaluate time
    # ------------------------------------------------------------------

    def get_session_summary(self):
        with self.lock:
            duration = int(time.time() - self.start_time) if self.start_time else 0
            return {
                "duration":         duration,
                "stability":        self._get_stability(),
                "notes":            "Session completed",
                "emotion":          self.current_emotion.get("emotion", "Unknown"),
                "dominant_emotion": self._get_dominant_emotion(),
                "emotion_summary":  self._get_emotion_percentages(),
            }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_dominant_emotion(self):
        if not self.emotion_history:
            return "Unknown"
        return Counter(self.emotion_history).most_common(1)[0][0]

    def _get_emotion_percentages(self):
        if not self.emotion_history:
            return {}
        counter = Counter(self.emotion_history)
        total   = sum(counter.values())
        return {
            emotion: round((count / total) * 100, 1)
            for emotion, count in counter.items()
        }

    def _get_stability(self):
        if len(self.emotion_buffer) < 5:
            return "Analyzing"
        unique = len(set(self.emotion_buffer))
        if unique <= 2:
            return "Stable"
        elif unique <= 4:
            return "Moderate"
        return "Unstable"