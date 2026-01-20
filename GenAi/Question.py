from langchain_groq import ChatGroq
from dotenv import load_dotenv
import os

load_dotenv()

llm = ChatGroq(
    groq_api_key=os.getenv("groq_Api"),
    model_name="llama-3.1-8b-instant",   # ✅ FIXED MODEL
    temperature=0.7
)

response = llm.invoke("Say hello in one sentence")
print(response.content)
