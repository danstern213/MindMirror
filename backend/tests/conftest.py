import os

# Settings() requires these; tests never talk to the real services.
for key, value in {
    "SUPABASE_URL": "http://localhost:54321",
    "SUPABASE_KEY": "test-key",
    "OPENAI_API_KEY": "test-key",
    "SECRET_KEY": "test-secret",
}.items():
    os.environ.setdefault(key, value)
