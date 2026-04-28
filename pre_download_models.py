from sentence_transformers import SentenceTransformer
import os

# Pre-download SentenceTransformer model
print("Pre-downloading SentenceTransformer model...")
model = SentenceTransformer('all-MiniLM-L6-v2')
print("✅ SentenceTransformer model downloaded.")

# Pre-download FER models (FER usually downloads at runtime if not present)
# We can just import and initialize it
try:
    from fer import FER
    print("Initializing FER...")
    FER()
    print("✅ FER initialized.")
except Exception as e:
    print(f"⚠️ FER initialization skipped or failed: {e}")
