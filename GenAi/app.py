from flask import Flask, request, jsonify
from flask_cors import CORS
from langchain_groq import ChatGroq
import os
from dotenv import load_dotenv
from datetime import datetime
import uuid

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

llm = ChatGroq(
    groq_api_key=os.getenv("groq_Api"),
    model_name="llama-3.1-8b-instant",   
    temperature=0.7
)

# ============================================================
# STRUCTURED INTERVIEW SESSION SCHEMA
# ============================================================
class InterviewSession:
    """
    Immutable interview session object that stores all context
    """
    def __init__(self, question_text, topic, difficulty_level):
        self.session_id = str(uuid.uuid4())
        self.question_text = question_text
        self.user_transcription = None
        self.topic = topic
        self.difficulty_level = difficulty_level
        self.timestamp = datetime.utcnow().isoformat()
        self.posture_data = None
        self.feedback = None
    
    def to_dict(self):
        return {
            "session_id": self.session_id,
            "question_text": self.question_text,
            "user_transcription": self.user_transcription,
            "topic": self.topic,
            "difficulty_level": self.difficulty_level,
            "timestamp": self.timestamp,
            "posture_data": self.posture_data,
            "feedback": self.feedback
        }

# In-memory storage (use database in production)
sessions = {}

# ============================================================
# STEP 1: Generate HR Question & Create Session
# ============================================================
@app.route("/hr-questions", methods=["POST"])
def hr_questions():
    """
    Generate interview question and create immutable session object
    """
    data = request.json
    level = data.get("level", "easy")
    count = data.get("count", 1)
    topic = data.get("topic", "Technical")

    prompt = f"""
    You are an experienced HR interviewer conducting a {level}-level interview.
    
    Generate {count} {level}-level interview question related to: {topic}
    
    The question should assess:
    -related to topic based on prctical application
    Return ONLY the question text, nothing else.
    """

    try:
        result = llm.invoke(prompt)
        question = result.content if hasattr(result, "content") else str(result)
        
        # Create immutable session object
        session = InterviewSession(
            question_text=question.strip(),
            topic=topic,
            difficulty_level=level
        )
        
        # Store session
        sessions[session.session_id] = session
        
        return jsonify({
            "session_id": session.session_id,
            "question": session.question_text,
            "topic": session.topic,
            "difficulty_level": session.difficulty_level,
            "timestamp": session.timestamp
        })
    
    except Exception as e:
        print("HR QUESTIONS ERROR:", e)
        return jsonify({"error": str(e)}), 500


# ============================================================
# STEP 2-4: Evaluate Response with Structured Payload
# ============================================================
@app.route("/evaluate", methods=["POST"])
def evaluate():
    """
    Context-aware evaluation using complete session object
    """
    data = request.json
    session_id = data.get("session_id")
    transcript = data.get("transcript", "")
    posture_data = data.get("posture_data", {})
    
    if not transcript.strip():
        return jsonify({"error": "Empty transcript"}), 400

    # Retrieve session
    if session_id not in sessions:
        return jsonify({"error": "Invalid session ID"}), 400
    
    session = sessions[session_id]
    
    # Update session with user response (maintain immutability concept)
    session.user_transcription = transcript
    session.posture_data = posture_data
    
    # Create structured payload for LLM
    structured_payload = {
        "session_id": session.session_id,
        "question_text": session.question_text,
        "user_transcription": session.user_transcription,
        "topic": session.topic,
        "difficulty_level": session.difficulty_level,
        "timestamp": session.timestamp,
        "posture_data": {
            "duration": posture_data.get('duration', 0),
            "stability": posture_data.get('stability', 'Unknown'),
            "notes": posture_data.get('notes', 'Not available')
        }
    }

    # Build comprehensive evaluation prompt
    prompt = f"""
    You are an expert interview coach providing detailed feedback.
    
    STRUCTURED INTERVIEW SESSION DATA:
    Session ID: {structured_payload['session_id']}
    Topic: {structured_payload['topic']}
    Difficulty Level: {structured_payload['difficulty_level']}
    Timestamp: {structured_payload['timestamp']}
    
    INTERVIEW QUESTION:
    {structured_payload['question_text']}
    
    CANDIDATE'S ANSWER (Speech-to-Text):
    {structured_payload['user_transcription']}
    
    POSTURE & BODY LANGUAGE DATA:
    - Duration: {structured_payload['posture_data']['duration']} seconds
    - Stability: {structured_payload['posture_data']['stability']}
    - Notes: {structured_payload['posture_data']['notes']}
    
    Please provide structured feedback in the following format:
    
    ## Overall Assessment
    [Provide a brief overall evaluation - 2-3 sentences]
    
    ## Content Analysis (Answer Quality)
    - Relevance: [How well did they address the question?]
    - Depth: [Did they provide sufficient detail and examples?]
    - Structure: [Was the answer well-organized?]
    
    ## Communication Skills
    - Clarity: [Was the answer clear and easy to understand?]
    - Confidence: [Based on word choice and phrasing]
    - Professionalism: [Appropriate language and tone?]
    
    ## Body Language & Posture
    - Stability: [Comment on their physical presence]
    - Engagement: [Based on duration and consistency]
    
    ## Strengths
    [List 2-3 specific things they did well]
    
    ## Areas for Improvement
    [List 2-3 specific suggestions for improvement]
    
    ## Score: [X]/10
    
    ## Final Recommendation
    [One sentence summary and encouragement]
    ##Answer in markdown format.
    return actual answer of question which HR expects.
    Answer the question in Candidate style that HR except
    """

    try:
        result = llm.invoke(prompt)
        feedback = result.content if hasattr(result, "content") else str(result)
        
        # Store feedback in session
        session.feedback = feedback
        
        return jsonify({
            "session_id": session.session_id,
            "feedback": feedback,
            "session_data": structured_payload
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# Get Session Data
# ============================================================
@app.route("/session/<session_id>", methods=["GET"])
def get_session(session_id):
    """
    Retrieve complete session data
    """
    if session_id not in sessions:
        return jsonify({"error": "Session not found"}), 404
    
    return jsonify(sessions[session_id].to_dict())


if __name__ == "__main__":
    app.run(debug=True, port=5000)