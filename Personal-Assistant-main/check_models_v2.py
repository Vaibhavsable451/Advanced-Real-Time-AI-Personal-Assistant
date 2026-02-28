import os
from dotenv import load_dotenv
import requests
import json

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    with open("models_output.txt", "w") as f:
        f.write("GOOGLE_API_KEY not found in .env")
else:
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    response = requests.get(url)
    if response.status_code == 200:
        models = response.json().get('models', [])
        with open("models_output.txt", "w") as f:
            for m in models:
                f.write(f"- {m['name']} ({m['supportedGenerationMethods']})\n")
    else:
        with open("models_output.txt", "w") as f:
            f.write(f"Error fetching models: {response.status_code} - {response.text}")
