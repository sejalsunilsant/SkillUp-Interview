import os

# Pre-download FER models (FER usually downloads at runtime if not present)
# We can just import and initialize it
try:
    from fer import FER
    print("Initializing FER...")
    FER()
    print("✅ FER initialized.")
except Exception as e:
    print(f"⚠️ FER initialization skipped or failed: {e}")

try:
    print("Initializing Gemini Cloud Embeddings...")
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    # This will check if the package is correctly installed and if the model name is valid
    # It might fail if GEMINI_API_KEY is not set, but we can catch that.
    # Actually, during build time, we don't have the API key.
    # So we just check if the import and class instantiation works with a dummy key.
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/text-embedding-004", # Updating to a more modern model as hint for 2026
        google_api_key="dummy_key"
    )
    print("✅ Embedding class initialized (using dummy key).")
except Exception as e:
    print(f"⚠️ Embedding initialization failed: {e}")
