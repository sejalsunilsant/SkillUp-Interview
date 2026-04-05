import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
from flask import jsonify
from flask_cors import CORS
from langchain_groq import ChatGroq
import json
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from emotion_detector import EmotionDetector
load_dotenv()

# Default questions mapping used if DB is empty
DEFAULT_QUESTIONS = {
    "easy": ["Can you tell me a little about yourself?", "What are your greatest strengths?", "Why do you want to work here?"],
    "medium": ["Describe a time you overcame a difficult challenge at work.", "How do you handle conflict with a coworker?", "Where do you see yourself in five years?"],
    "hard": ["Tell me about a time you failed and what you learned from it.", "How would you handle a situation where you strongly disagreed with your manager's decision?", "Can you explain a complex concept to someone without a technical background?"]
}


class InterviewGenratSession:
    def __init__(self):
        self.llm = ChatGroq(
            groq_api_key=os.getenv("groq_Api"),
            model_name="llama-3.1-8b-instant",
            temperature=0.7,
        )
    def _embed_and_chunk(self, text, query):
        try:
            from sentence_transformers import SentenceTransformer
            from sklearn.metrics.pairwise import cosine_similarity
            import numpy as np

            # Simple chunking: split by paragraphs
            chunks = [c.strip() for c in text.split('\n\n') if len(c.strip()) > 20]
            if not chunks:
                return text[:2000]

            model = SentenceTransformer('all-MiniLM-L6-v2')
            chunk_embeddings = model.encode(chunks)
            query_embedding = model.encode([query])

            similarities = cosine_similarity(query_embedding, chunk_embeddings)[0]
            # Get top 3 chunks
            top_indices = np.argsort(similarities)[-3:][::-1]
            best_chunks = [chunks[i] for i in top_indices]

            return "\n...\n".join(best_chunks)
        except Exception as e:
            print("Embedding failed or missing dependencies, falling back to full text:", e)
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
            result = self.llm.invoke(prompt)
            question = result.content if hasattr(result, "content") else str(result)
            question = question.strip()
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
            
            result   = self.llm.invoke(prompt)
            feedback = result.content if hasattr(result, "content") else str(result)
            return feedback

        except Exception as e:
            print("EVALUATE RESULT ERROR:", e)
            return f"## Score 0/10\n\nEvaluation failed due to an error: {str(e)}."

    def evaluate_all(self, interview):
        # Build full transcript of the interview
        history_str = ""
        valid_count = 0
        for i, turn in enumerate(interview.history):
            if not turn.get('answer', '').strip():
                continue
            history_str += f"\nQ{i+1}: {turn.get('question', '')}\nA{i+1}: {turn.get('answer', '')}\n"
            valid_count += 1
            
        if valid_count == 0:
            return "## Final Score 0/10\nNo valid answers were recorded to evaluate."
            
        try:
            prompt = f"""
            You are an expert Head of HR and Senior Interviewer providing a final, comprehensive evaluation for a candidate's entire interview.

            INTERVIEW CONTEXT:
            Job Description / Context: {interview.jd_text}
            Candidate Resume: {"Included in context" if interview.resume_text else "Not provided"}
            Total Scorable Questions Answered: {valid_count}

            FULL INTERVIEW TRANSCRIPT:
            {history_str}

            Provide a comprehensive final interview assessment that evaluates the candidate across all questions combined.
            Use EXACTLY the following format:

            ## Overall Assessment
            [Provide a detailed paragraph summarizing their overall performance, behavioral consistency, and technical depth]

            ## Key Strengths
            - [Strength 1 based on their answers]
            - [Strength 2 based on their answers]
            - [Strength 3 based on their answers]

            ## Critical Areas for Improvement
            - [Area 1 to improve]
            - [Area 2 to improve]
            - [Area 3 to improve]

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
            
            result = self.llm.invoke(prompt)
            return result.content if hasattr(result, "content") else str(result)
        
        except Exception as e:
            print("EVALUATE ALL ERROR:", e)
            return f"## Score 0/10\n\nFinal evaluation compilation failed: {str(e)}."
