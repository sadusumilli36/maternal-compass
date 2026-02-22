from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from google import genai
import os
from dotenv import load_dotenv
import pandas as pd

load_dotenv()

app = Flask(__name__, static_folder='.')
CORS(app)

# Configure Gemini - The client gets the API key from environment variable
os.environ['GEMINI_API_KEY'] = os.getenv('GEMINI_API_KEY')
client = genai.Client()

# Load CSV data once on startup
def load_data_context():
    context = """You are MaternalCompass AI, an expert assistant for maternal healthcare data in Georgia.

IMPORTANT RULES:
- ONLY answer questions using the data provided below
- If data is not available, say "I don't have that information in my dataset"
- Never make up or estimate numbers
- Be precise with county names and hospital names
- Format your responses clearly with proper spacing

AVAILABLE DATA:

"""
    
    # Load county data
    try:
        df = pd.read_csv('county_data.csv')
        context += f"\n=== COUNTY RISK DATA ===\nColumns: {', '.join(df.columns.tolist())}\n{df.to_string(index=False)}\n"
    except Exception as e:
        context += f"\n=== COUNTY RISK DATA === (Error loading: {e})\n"
    
    # Load hospital data
    try:
        df = pd.read_csv('Updated ob_hospitals_with_level(ob_hospitals_with_level).csv')
        context += f"\n=== HOSPITAL DATA ===\nColumns: {', '.join(df.columns.tolist())}\n{df.to_string(index=False)}\n"
    except Exception as e:
        context += f"\n=== HOSPITAL DATA === (Error loading: {e})\n"
    
    # Load expansion data
    try:
        df = pd.read_csv('county_expansion_data.csv')
        context += f"\n=== COUNTY EXPANSION NEEDS ===\nColumns: {', '.join(df.columns.tolist())}\n{df.to_string(index=False)}\n"
    except Exception as e:
        context += f"\n=== COUNTY EXPANSION NEEDS === (Error loading: {e})\n"
    
    try:
        df = pd.read_csv('beds_needed_for_low_risk_by_county(in).csv')
        context += f"\n=== BEDS NEEDED FOR LOW RISK ===\nColumns: {', '.join(df.columns.tolist())}\n{df.to_string(index=False)}\n"
    except Exception as e:
        context += f"\n=== BEDS NEEDED FOR LOW RISK === (Error loading: {e})\n"
    
    try:
        df = pd.read_csv('county_increase_10yr.csv')
        context += f"\n=== 10-YEAR OB BEDS INCREASE ===\nColumns: {', '.join(df.columns.tolist())}\n{df.to_string(index=False)}\n"
    except Exception as e:
        context += f"\n=== 10-YEAR OB BEDS INCREASE === (Error loading: {e})\n"
    
    return context

print("Loading data context...")
DATA_CONTEXT = load_data_context()
print("Data context loaded successfully!")

# Serve static files
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        user_message = request.json.get('message', '')
        
        # Combine context with user message
        full_prompt = f"{DATA_CONTEXT}\n\nUser Question: {user_message}\n\nAnswer (be concise and factual):"
        
        # Generate response using new API
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=full_prompt
        )
        
        return jsonify({
            'success': True,
            'response': response.text
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/suggested-prompts', methods=['GET'])
def suggested_prompts():
    prompts = [
        "What is the risk level for Fulton County?",
        "How many OB beds does Northside Hospital have?",
        "Which counties need the most additional beds?",
        "List all Level IV hospitals in Georgia",
        "What's the average distance to care in DeKalb County?",
        "Which counties have Very High risk levels?"
    ]
    return jsonify({'prompts': prompts})

if __name__ == '__main__':
    print("Starting MaternalCompass Flask server on http://localhost:8000")
    print("Press Ctrl+C to stop the server")
    app.run(host='127.0.0.1', port=8000, debug=True, use_reloader=False)
