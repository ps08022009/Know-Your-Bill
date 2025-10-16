import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from transformers import pipeline
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Load API key from environment variable for security
API_KEY = os.getenv("CONGRESS_API_KEY", "Im5PSE4YRX9G2FZhVchtfXnwNuRQ9oKmU1G6YztB")

# Initialize models once at startup (not on every request)
print("Loading models...")
summarizer = pipeline("summarization", model="facebook/bart-large-cnn", device=-1)
semantic_model = SentenceTransformer('all-MiniLM-L6-v2')
print("Models loaded successfully")

def fetch_bill_details(bill_number):
    """Fetch detailed information for a specific bill"""
    url = f"https://api.congress.gov/v3/bill/118/hr/{bill_number}"
    params = {"api_key": API_KEY}
    
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        bill_data = r.json().get("bill", {})
        
        # Extract sponsor info
        sponsors = bill_data.get("sponsors", [])
        sponsor_name = "N/A"
        if sponsors and len(sponsors) > 0:
            sponsor = sponsors[0]
            first_name = sponsor.get("firstName", "")
            last_name = sponsor.get("lastName", "")
            party = sponsor.get("party", "")
            state = sponsor.get("state", "")
            
            # Build full name
            full_name = f"{first_name} {last_name}".strip()
            if full_name and party and state:
                sponsor_name = f"{full_name} ({party}-{state})"
            elif full_name:
                sponsor_name = full_name
        
        # Extract latest action with date
        latest_action = bill_data.get("latestAction", {})
        action_text = latest_action.get("text", "N/A")
        action_date = latest_action.get("actionDate", "N/A")
        
        print(f"Bill {bill_number}: sponsor={sponsor_name}, status={action_text}, date={action_date}")
        
        return {
            "sponsor": sponsor_name,
            "status": action_text,
            "date": action_date
        }
    
    except Exception as e:
        print(f"Error fetching bill {bill_number} details: {e}")
        return {
            "sponsor": "N/A",
            "status": "N/A",
            "date": "N/A"
        }

def fetch_latest_bills(limit=250):
    """Fetch bills from Congress API with error handling"""
    url = f"https://api.congress.gov/v3/bill/118/hr"
    params = {
        "api_key": API_KEY,
        "limit": limit,
        "sort": "updateDate+desc"
    }
    
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        bills_data = r.json().get("bills", [])
        
        bills = []
        for bill in bills_data:
            title = bill.get("title", "")
            bill_number = bill.get("number", "")
            
            # Create description for semantic search
            description = title
            if bill.get("latestAction"):
                latest_action = bill["latestAction"].get("text", "")
                description += f" {latest_action}"
            
            bills.append({
                "number": bill_number,
                "title": title,
                "description": description,
                "url": f"https://www.congress.gov/bill/118th-congress/house-bill/{bill_number}"
            })
        
        return bills
    
    except requests.exceptions.RequestException as e:
        print(f"Error fetching bills: {e}")
        return []

def find_relevant_bills(query, bills, top_k=12):
    """Use semantic similarity to find relevant bills"""
    if not bills:
        return []
    
    # Encode query
    query_embedding = semantic_model.encode([query])
    
    # Encode bill descriptions
    bill_texts = [f"{b['title']} {b['description']}" for b in bills]
    bill_embeddings = semantic_model.encode(bill_texts)
    
    # Calculate similarity
    similarities = cosine_similarity(query_embedding, bill_embeddings)[0]
    
    # Get top k indices
    top_indices = np.argsort(similarities)[-top_k:][::-1]
    
    # Filter by minimum similarity threshold (lowered for more results)
    relevant_bills = []
    for idx in top_indices:
        if similarities[idx] > 0.15:  # Lowered threshold for more inclusive results
            bill = bills[idx].copy()
            bill['relevance_score'] = float(similarities[idx])
            relevant_bills.append(bill)
    
    # If we still don't have enough results, add more with lower threshold
    if len(relevant_bills) < 6:
        for idx in top_indices:
            if similarities[idx] > 0.1 and len(relevant_bills) < 8:
                bill = bills[idx].copy()
                bill['relevance_score'] = float(similarities[idx])
                if bill not in relevant_bills:
                    relevant_bills.append(bill)
    
    return relevant_bills

def summarize_text(text, max_length=200, min_length=80):
    """Summarize text with error handling"""
    try:
        # Skip if text is already short
        if len(text.split()) < min_length:
            return text
        
        # Truncate if too long for model
        max_input = 1024
        words = text.split()
        if len(words) > max_input:
            text = " ".join(words[:max_input])
        
        result = summarizer(
            text, 
            max_length=max_length, 
            min_length=min_length, 
            do_sample=False,
            truncation=True
        )
        return result[0]["summary_text"]
    
    except Exception as e:
        print(f"Summarization error: {e}")
        # Return truncated original if summarization fails
        return " ".join(text.split()[:80]) + "..."

@app.route("/search_bills", methods=["POST"])
def search_bills():
    """Search for relevant bills based on query"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400
        
        query = data.get("query", "").strip()
        
        if not query:
            return jsonify({"error": "Query parameter is required"}), 400
        
        # Fetch bills
        print(f"Fetching bills for query: {query}")
        bills = fetch_latest_bills(limit=250)
        
        if not bills:
            return jsonify({"error": "Unable to fetch bills from Congress API"}), 503
        
        # Find relevant bills using semantic search
        print(f"Finding relevant bills...")
        relevant_bills = find_relevant_bills(query, bills, top_k=12)
        
        if not relevant_bills:
            return jsonify({
                "query": query,
                "bills": [],
                "message": "No relevant bills found for your query"
            })
        
        # Summarize each relevant bill and fetch details
        results = []
        for bill in relevant_bills:
            print(f"Processing bill H.R. {bill['number']}")
            
            # Fetch detailed bill information
            details = fetch_bill_details(bill["number"])
            
            summary = summarize_text(bill["description"])
            results.append({
                "number": bill["number"],
                "title": bill["title"],
                "summary": summary,
                "sponsor": details["sponsor"],
                "status": details["status"],
                "date": details["date"],
                "relevance_score": bill["relevance_score"],
                "url": bill["url"]
            })
        
        print(f"Returning {len(results)} results")
        return jsonify({
            "query": query,
            "bills": results,
            "total_found": len(results)
        })
    
    except Exception as e:
        print(f"Error processing request: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Internal server error"}), 500

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy"})

@app.route("/models_ready", methods=["GET"])
def models_ready():
    """Check if AI models are loaded and ready"""
    try:
        # Test if models are accessible
        test_text = "test"
        semantic_model.encode([test_text])
        summarizer("This is a test.", max_length=50, min_length=10, do_sample=False)
        return jsonify({"ready": True, "status": "Models loaded successfully"})
    except Exception as e:
        return jsonify({"ready": False, "status": f"Models not ready: {str(e)}"}), 503

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)