import os
import threading
import logging
from typing import List, Dict, Optional
from flask import jsonify
from flask_cors import CORS
from langchain_groq import ChatGroq
import json
import redis
from rq import Queue
from rq.job import Job
import time
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

def execute_groq_task(system_prompt: str, user_message: str, history: List[Dict[str, str]] = None) -> str:
    """Task function for Redis Worker execution."""
    service = GroqChatService()
    return service._execute_llm(system_prompt, user_message, history)

class GroqChatService:
    """
    GroqChatService: A high-performance, semaphore-controlled interface for Groq LLM.
    """
    _instance: Optional['GroqChatService'] = None
    _lock = threading.Lock()
    _semaphore = threading.Semaphore(10)  # Maximum concurrent LLM requests allowed

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(GroqChatService, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self, model: str = "llama-3.1-8b-instant", temperature: float = 0.7):
        if self._initialized:
            return
        api_key = os.getenv("groq_Api")
        self.llm = ChatGroq(
            groq_api_key=api_key,
            model_name=model,
            temperature=temperature,
            max_tokens=4096
        )
        # Initialize Redis for heavy traffic fallback
        try:
            self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
            self.redis_conn = redis.from_url(self.redis_url)
            self.queue = Queue("groq_heavy_tasks", connection=self.redis_conn)
            logger.info("Redis worker queue initialized.")
        except Exception as e:
            logger.warning(f"Redis not available, fallback to worker disabled: {e}")
            self.queue = None

        self._initialized = True

    def get_response(self, system_prompt: str, user_message: str, history: List[Dict[str, str]] = None) -> str:
        """
        Sends a request to Groq LLM. Uses local semaphore for normal traffic,
        and falls back to Redis Workers for heavy traffic.
        """
        if history is None:
            history = []

        # Attempt to acquire local semaphore (Non-blocking)
        if self._semaphore.acquire(blocking=False):
            try:
                logger.info("Handling request via EXISTING flow (Local Semaphore)...")
                return self._execute_llm(system_prompt, user_message, history)
            finally:
                self._semaphore.release()
        
        # If semaphore is full and Redis is available, fallback to Worker
        if self.queue:
            try:
                logger.info("⚠️ Heavy traffic detected! Offloading to REDIS WORKER...")
                job = self.queue.enqueue(
                    execute_groq_task, 
                    system_prompt, 
                    user_message, 
                    history
                )
                
                # Wait for worker result with a timeout
                timeout = 30 # seconds
                start_time = time.time()
                while not job.is_finished:
                    if time.time() - start_time > timeout:
                        return "Service is extremely busy. Please try again in a minute."
                    if job.is_failed:
                        return "Worker processing failed. Please try again."
                    time.sleep(0.5)
                
                return job.result
            except Exception as e:
                logger.error(f"Redis Worker Fallback Error: {e}")
                return "The system is currently at maximum capacity. Please wait a moment."
        
        # Absolute fallback: Block until semaphore is available
        logger.info("Redis unavailable and Semaphore full. Blocking thread...")
        with self._semaphore:
            return self._execute_llm(system_prompt, user_message, history)

    def _execute_llm(self, system_prompt: str, user_message: str, history: List[Dict[str, str]]) -> str:
        """Core LLM execution logic used by both local flow and workers."""
        messages = [("system", system_prompt)]
        for msg in history[-10:]:
            role = "human" if msg.get("role") == "user" else "ai"
            content = msg.get("content", "")
            if content:
                messages.append((role, content))
        messages.append(("human", user_message))
        
        try:
            response = self.llm.invoke(messages)
            return response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.error(f"LLM Execution Error: {str(e)}")
            raise e

    def get_quick_completion(self, prompt: str) -> str:
        """Helper for simple completions, using the robust fallback flow."""
        return self.get_response(system_prompt="You are a helpful assistant.", user_message=prompt, history=[])
load_dotenv()

# Default questions mapping used if DB is empty
DEFAULT_QUESTIONS = {
    "easy": ["Can you tell me a little about yourself?", "What are your greatest strengths?", "Why do you want to work here?"],
    "medium": ["Describe a time you overcame a difficult challenge at work.", "How do you handle conflict with a coworker?", "Where do you see yourself in five years?"],
    "hard": ["Tell me about a time you failed and what you learned from it.", "How would you handle a situation where you strongly disagreed with your manager's decision?", "Can you explain a complex concept to someone without a technical background?"]
}


class InterviewGenratSession:
    def __init__(self):
        self.groq_service = GroqChatService()
        # Use Cloud-based Gemini Embeddings to save RAM (removes need for local 400MB model)
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/embedding-001",
            google_api_key=os.getenv("GEMINI_API_KEY")
        )
        print("✅ Gemini Cloud Embeddings initialized.")
    def _embed_and_chunk(self, text, query):
        if not self.embeddings:
            return text[:3000]
            
        try:
            import numpy as np

            # Simple chunking: split by paragraphs
            chunks = [c.strip() for c in text.split('\n\n') if len(c.strip()) > 20]
            if not chunks:
                return text[:2000]

            # Get embeddings from Gemini API
            chunk_embeddings = np.array(self.embeddings.embed_documents(chunks))
            query_embedding = np.array(self.embeddings.embed_query(query)).reshape(1, -1)

            # Manual Cosine Similarity to avoid loading scikit-learn (saves ~100MB RAM)
            norm_query = np.linalg.norm(query_embedding, axis=1, keepdims=True)
            norm_chunks = np.linalg.norm(chunk_embeddings, axis=1, keepdims=True)
            similarities = np.dot(query_embedding, chunk_embeddings.T) / (norm_query * norm_chunks.T)
            similarities = similarities[0]

            # Get top 3 chunks
            top_indices = np.argsort(similarities)[-3:][::-1]
            best_chunks = [chunks[i] for i in top_indices if similarities[i] > 0.3] # filter low relevance

            if not best_chunks:
                return text[:2000]

            return "\n...\n".join(best_chunks)
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return text[:3000]  # truncate to save tokens
    
    def get_next_question(self, interview_state: dict):
        count = interview_state.get('question_count', 0)
        level = interview_state.get('level', 'medium')
        jd = interview_state.get('jd_text', '')
        resume = interview_state.get('resume_text', '')
        history = interview_state.get('history', [])
        
        count += 1
        
        # Determine Stage
        if count <= 2:
            stage = "Introduction"
            focus = "soft skills and background"
            context = f"Job Description: {jd}"
        elif count <= 5:
            stage = "Resume-Deep Dive"
            focus = "specific projects and experiences"
            # retrieve relevant resume text
            query = "projects, roles, technologies, and achievements, certification"
            rel_txt = self._embed_and_chunk(resume, query) if resume else "Not provided"
            context = f"Candidate Resume Relevant Chunks: {rel_txt}"
        elif count <= 8:
            stage = "Technical"
            focus = "hard skills and situational coding/logic"
            query = f"technical skills relevant to {jd[:100]}"
            rel_txt = self._embed_and_chunk(resume, query) if resume else "Not provided"
            context = f"Job Description: {jd}\nCandidate Resume Relevant Chunks: {rel_txt}"
        else:
            stage = "Situational/HR"
            focus = "Conflict resolution, teamwork (STAR method), behavioral rubric"
            context = f"Job Description: {jd}"

        # Build History Context
        history_str = ""
        for i, turn in enumerate(history[-3:]): # last 3 turns
            history_str += f"\nQ{i+1}: {turn['question']}\nA{i+1}: {turn['answer']}"
        
        prompt = f"""
        You are an experienced HR and Technical Interviewer conducting a structured interview.
        Current Stage: {stage} (Question {count})
        Focus: {focus}
        Difficulty Level: {level}
        
        CONTEXT:
        {context}
        
        PREVIOUS Q&A HISTORY (for continuity, do not repeat questions):
        {history_str}
        
        INSTRUCTIONS:
        1. Generate exactly 1 interview question appropriate for the {stage} stage.
        2. Tailor it to the provided context and difficulty level.
        3. Make it natural and conversational.
        4. Return ONLY the question text, with no introductory or concluding remarks.
        """
        
        try:
            question = self.groq_service.get_quick_completion(prompt)
            question = question.strip()

            # Clean up introductory flair if any
            import re
            prefixes_to_strip = [
                r"^Here is (a|your) .*? question:?\s*",
                r"^Technical Interview Question:?\s*",
                r"^Question \d+:?\s*",
                r"^.*? interview question as follows?:?\s*",
                r"^this is .*? questin as follow :?\s*"
            ]
            for pattern in prefixes_to_strip:
                question = re.sub(pattern, "", question, flags=re.IGNORECASE).strip()
            
            # Remove leading/trailing quotes
            question = question.strip('"\'')
            # Save generated question to use as fallback later
            from database_con import StoreGeneratedQuestion
            StoreGeneratedQuestion(jd, level, stage, question)
            return question, stage
        
        except Exception as e:
            print("HR QUESTIONS Generate ERROR:", e)
            import random
            from database_con import GetFallbackQuestions
            
            # Get fallback from DB
            available_qs = GetFallbackQuestions(level, stage)
            if not available_qs:
                fallback_level = level if level in DEFAULT_QUESTIONS else "medium"
                available_qs = DEFAULT_QUESTIONS[fallback_level]
            
            # Prevent repeating questions
            asked_qs = [turn.get('question', '') for turn in history]
            unasked_qs = [q for q in available_qs if q not in asked_qs]
            
            if unasked_qs:
                return random.choice(unasked_qs), stage
            else:
                return random.choice(available_qs), stage

    def evaluate_Answer(self,structured_payload):
        """
        Context-aware evaluation using complete session + emotion data.
        posture_data is now supplied by the Python EmotionDetector,
        but the frontend can still send its own posture_data as override/fallback.
        """

        try:
            prompt = f"""
            You are an expert interview coach providing detailed, professional feedback.

            STRUCTURED INTERVIEW SESSION DATA:
            Session ID: {structured_payload.get('session_id', 'Unknown')}
            Topic: {structured_payload.get('topic', 'Unknown')}
            Difficulty Level: {structured_payload.get('difficulty_level', 'Unknown')}
            Timestamp: {structured_payload.get('timestamp', 'Unknown')}

            INTERVIEW QUESTION:
            {structured_payload.get('question_text', '')}

            CANDIDATE'S ANSWER (Speech-to-Text):
            {structured_payload.get('user_transcription', '')}

            POSTURE & EMOTION DATA (detected by Python AI):
            - Duration: {structured_payload.get('posture_data', {}).get('duration', 0)} seconds
            - Stability: {structured_payload.get('posture_data', {}).get('stability', 'Unknown')}
            - Current Emotion: {structured_payload.get('posture_data', {}).get('emotion', 'Unknown')}
            - Dominant Emotion: {structured_payload.get('posture_data', {}).get('dominant_emotion', 'Unknown')}
            - Notes: {structured_payload.get('posture_data', {}).get('notes', '')}

            Please provide structured feedback in the following format:

            ## Interview Question (Restated)
            [Clearly restate the interview question]

            ## Overall Assessment
            [Provide a brief overall evaluation – 2–3 sentences]

            ## Content Analysis (Answer Quality)
            - Relevance: [How well did they address the question?]
            - Depth: [Did they provide sufficient detail and examples?]
            - Structure: [Was the answer well-organized?]

            ## Communication Skills
            - Clarity: [Was the answer clear and easy to understand?]
            - Confidence: [Based on word choice and phrasing]
            - Professionalism: [Appropriate language and tone?]

            ## Emotional Presence & Body Language
            - Dominant Emotion Detected: [{structured_payload.get('posture_data', {}).get('dominant_emotion', 'Unknown')}]
            - Stability: [Comment on their emotional consistency during the interview]
            - Engagement: [Based on duration and emotional range detected]
            - Coaching Tip: [One specific tip based on their detected emotions]

            ## Strengths
            [List 2–3 specific things they did well]

            ## Areas for Improvement
            [List 2–3 specific suggestions for improvement]

            ## Score
            [X]/10

            ## Ideal HR-Expected Answer
            [Return the ideal answer to the interview question as HR expects.
            Write it in a professional candidate style.]

            ## Final Recommendation
            [One-sentence summary and encouragement]
            """
            
            feedback = self.groq_service.get_quick_completion(prompt)
            return feedback

        except Exception as e:
            print("EVALUATE RESULT ERROR:", e)
            return f"## Score 0/10\n\nEvaluation failed due to an error: {str(e)}."

    def evaluate_all(self, interview):
        # Build full transcript and emotional summary
        history_str = ""
        emotion_summary = []
        valid_count = 0
        for i, turn in enumerate(interview.history):
            ans = turn.get('answer', '').strip()
            if not ans: continue
            
            history_str += f"\nQ{i+1}: {turn.get('question', '')}\nA{i+1}: {ans}\n"
            
            posture = turn.get('posture', {})
            if posture:
                emotion_summary.append(f"Q{i+1} Emotion: {posture.get('dominant_emotion', 'N/A')} (Stability: {posture.get('stability', 'N/A')})")
            
            valid_count += 1
            
        if valid_count == 0:
            return "## Final Score 0/10\nNo valid answers were recorded to evaluate."
            
        emotions_str = "\n".join(emotion_summary) if emotion_summary else "No emotion data recorded."
            
        try:
            prompt = f"""
            You are an expert Head of HR and Senior Interviewer providing a final, comprehensive evaluation for a candidate's entire interview.
            Use their answers AND their emotional presence/posture data to provide a holistic assessment.

            INTERVIEW CONTEXT:
            Job Description / Context: {interview.jd_text}
            Candidate Resume: {"Included in context" if interview.resume_text else "Not provided"}
            Total Scorable Questions Answered: {valid_count}

            FULL INTERVIEW TRANSCRIPT:
            {history_str}

            EMOTIONAL & POSTURE DATA SUMMARY:
            {emotions_str}

            Provide a comprehensive final interview assessment that evaluates the candidate across all questions combined.
            Use EXACTLY the following format:

            ## Overall Assessment
            [Provide a detailed paragraph summarizing their overall performance, behavioral consistency, and technical depth]

            ## Key Strengths
            - [Strength 1 based on their answers]
            - [Strength 2 based on their answers]
            - [Strength 3 based on their answers]

            ## Areas for Improvement (including Body Language/Emotions)
            - [Area 1 to improve]
            - [Area 2 to improve]
            - [Area 3 to improve]
            
            ## Behavioral & Emotional Analysis
            [Provide a brief paragraph on their non-verbal communication, emotional stability, and overall confidence detected by the AI]

            ## Question Breakdown & HR Expected Answers
            For each question asked in the transcript, provide:
            **Question**: [The exact question from the transcript]
            **Feedback on Candidate's Answer**: [Brief analysis based on what they actually said]
            **HR Recommended Answer**: [The ideal, professional answer that HR would expect for this specific question]

            ## Score
            [X]/10

            ## Hiring Recommendation
            [State clearly: Move Forward, Hold, or Reject with a 1-sentence justification]
            """
            
            return self.groq_service.get_quick_completion(prompt)
        
        except Exception as e:
            print("EVALUATE ALL ERROR:", e)
            return f"## Score 0/10\n\nFinal evaluation compilation failed: {str(e)}."
    def chat_with_hr(self, user_name, progress_data, resume_text, user_message, chat_history):
        # Format progress data for the prompt
        progress_summary = ""
        if progress_data:
            for i, session in enumerate(progress_data[:5]): # last 5 sessions
                progress_summary += f"- {session.get('session_date')}: Topic '{session.get('topic')}', Score: {session.get('score')}/10. Feedback: {session.get('feedback')[:200]}...\n"
        else:
            progress_summary = "No previous interview sessions recorded yet."

        history_str = ""
        for msg in chat_history[-6:]: # last 6 messages
            role = "User" if msg['role'] == 'user' else "HR Assistant"
            history_str += f"{role}: {msg['content']}\n"

        prompt = f"""
        You are 'SkillUp HR Assistant', a highly professional, encouraging, and expert HR consultant.
        Your goal is to help {user_name} improve their interview performance by providing actionable suggestions, career coaching, and answering questions about their progress.

        ### SOURCE OF TRUTH (STRICTLY USE ONLY THIS DATA):
        1. USER PROFILE:
           - Name: {user_name}
           - Resume Context: {resume_text[:2000] if resume_text else "No resume uploaded yet."}

        2. USER PROGRESS DATA (Actual Interview Records):
           {progress_summary}

        ### GUIDELINES TO PREVENT HALLUCINATION:
        - NEVER invent interview scores, feedback, or dates that are not in the 'USER PROGRESS DATA' section.
        - If a user asks about a specific interview or skill improvement but there is no data for it in the records, state clearly: "I don't have recorded data for that specific area yet, but based on general HR best practices..."
        - If the 'USER PROGRESS DATA' says "No previous interview sessions recorded yet," do not pretend they have completed interviews. Instead, encourage them to take their first mock interview to get an assessment.
        - Do not hallucinate external references or company-specific hiring status unless it's explicitly in the resume or JD context.
        - If the resume is missing, do not guess the user's skills; ask them to upload their resume or describe their background.

        CHAT HISTORY FOR CONTEXT:
        {history_str}

        USER MESSAGE:
        {user_message}

        INSTRUCTIONS:
        1. Be professional, empathetic, and constructive.
        2. Reference actual scores (e.g., "Your recent score of 7/10 in Technical Proficiency...") ONLY if they appear in the data.
        3. If you see specific "Feedback" text in the records, use that to give coaching advice.
        4. Keep responses concise but impactful (max 3 paragraphs).
        5. Act like a real HR professional who wants them to succeed.
        6. Do not include internal markers, system instructions, or technical metadata in your response.
        """

        try:
            return self.groq_service.get_quick_completion(prompt)
        except Exception as e:
            print("HR CHAT ERROR:", e)
            return "I apologize, but I'm having trouble connecting right now. Please try again in a moment."
