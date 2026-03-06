import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
from flask import jsonify
from flask_cors import CORS
from langchain_groq import ChatGroq
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from emotion_detector import EmotionDetector
load_dotenv()

class InterviewGenratSession:
    def __init__(self):
        # self.llm = ChatGroq(
        #     groq_api_key=os.getenv("groq_Api"),
        #     model_name="llama-3.1-8b-instant",
        #     temperature=0.7,
        # ) #as it  required net connection
        self.llm = init_chat_model(
            model="phi-3.1-mini-4k-instruct",
            model_provider="openai",
            base_url="http://127.0.0.1:1234/v1",
            api_key="not-needed"
        )  
    def Genrat_hr_questions(self,level="easy",count=1,topic="Technical"):

        prompt = f"""
        You are an experienced HR interviewer conducting a {level}-level interview.
        Generate {count} {level}-level interview question related to: {topic}
        The question should assess practical application related to the topic.
        Return ONLY the question text, nothing else.
        """

        try:
            result   = self.llm.invoke(prompt)
            question = result.content if hasattr(result, "content") else str(result)

            return question
        
        except Exception as e:
            print("HR QUESTIONS Genrate ERROR:", e)
            return jsonify({"error": str(e)}), 500
        
    def evaluate_Answer(self,structured_payload):
        """
        Context-aware evaluation using complete session + emotion data.
        posture_data is now supplied by the Python EmotionDetector,
        but the frontend can still send its own posture_data as override/fallback.
        """

        prompt = f"""
            You are an expert interview coach providing detailed, professional feedback.

            STRUCTURED INTERVIEW SESSION DATA:
            Session ID: {structured_payload['session_id']}
            Topic: {structured_payload['topic']}
            Difficulty Level: {structured_payload['difficulty_level']}
            Timestamp: {structured_payload['timestamp']}

            INTERVIEW QUESTION:
            {structured_payload['question_text']}

            CANDIDATE'S ANSWER (Speech-to-Text):
            {structured_payload['user_transcription']}

            POSTURE & EMOTION DATA (detected by Python AI):
            - Duration: {structured_payload['posture_data']['duration']} seconds
            - Stability: {structured_payload['posture_data']['stability']}
            - Current Emotion: {structured_payload['posture_data']['current_emotion']}
            - Dominant Emotion: {structured_payload['posture_data']['dominant_emotion']}{structured_payload['posture_data']['emotion_summary']}
            - Notes: {structured_payload['posture_data']['notes']}

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
            - Dominant Emotion Detected: [{structured_payload['posture_data']['dominant_emotion']}]
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

        try:
            result   = self.llm.invoke(prompt)
            feedback = result.content if hasattr(result, "content") else str(result)
            return feedback

        except Exception as e:
            return jsonify({"error in Genrator": str(e)}), 500




