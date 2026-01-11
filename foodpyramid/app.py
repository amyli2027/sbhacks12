import os
import time
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# ⚠️ YOUR API KEY
API_KEY = "pRAoUVvdllyd6skGURjLGBTuUf7jlKeBiN7Az3rQ"
BASE_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"

session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))

def map_usda_category(usda_cat, name):
    cat = str(usda_cat).lower()
    name = str(name).lower()
    
    # --- PHASE 1: THE "JUNK" FILTER (Highest Priority) ---
    # We check this FIRST so "Strawberry Cake" becomes SWEET, not Fruit.
    junk_keywords = [
        "candy", "chocolate", "cake", "cookie", "pie", "brownie", "ice cream",
        "pudding", "dessert", "snack", "syrup", "jam", "jelly", "soda", 
        "soft drink", "cola", "donut", "muffin", "pastry", "frosting"
    ]
    if any(k in name for k in junk_keywords) or any(k in cat for k in junk_keywords):
        return "sweet"

    # --- PHASE 2: EXPLICIT REAL FOODS (Override USDA Categories) ---
    # Check specifically for common whole foods to prevent "Grain/Veg" errors
    
    # FRUITS
    fruit_keywords = [
        "strawberry", "strawberries", "apple", "banana", "blueberry", "raspberries", 
        "blackberry", "grape", "melon", "watermelon", "citrus", "orange", 
        "peach", "pear", "mango", "pineapple", "cherry", "fruit"
    ]
    if any(k in name for k in fruit_keywords):
        return "fruit"
        
    # VEGETABLES
    veg_keywords = [
        "broccoli", "spinach", "kale", "lettuce", "salad", "carrot", "onion", 
        "pepper", "tomato", "cucumber", "celery", "asparagus", "cauliflower", 
        "cabbage", "vegetable", "corn", "potato", "bean", "pea"
    ]
    if any(k in name for k in veg_keywords):
        return "veg"

    # PROTEINS
    prot_keywords = [
        "beef", "steak", "chicken", "turkey", "pork", "ham", "bacon", "sausage", 
        "egg", "fish", "salmon", "tuna", "shrimp", "seafood", "meat", "burger"
    ]
    if any(k in name for k in prot_keywords):
        return "protein"

    # --- PHASE 3: USDA CATEGORY FALLBACK (If name didn't match above) ---
    if "dairy" in cat or "milk" in cat or "cheese" in cat or "yogurt" in cat: return "dairy"
    if "grain" in cat or "cereal" in cat or "pasta" in cat or "bread" in cat: return "grain"
    if "fat" in cat or "oil" in cat or "butter" in cat: return "fat"
    
    # Specific Name Fallbacks for things missed
    if "rice" in name or "oat" in name or "toast" in name or "bread" in name: return "grain"
    if "butter" in name or "oil" in name or "margerine" in name: return "fat"
    if "milk" in name or "cheese" in name or "cream" in name: return "dairy"

    # Default to grain if we are totally lost (avoids crashing)
    return "grain"

def get_nutrient(nutrient_list, *ids):
    """Helper to find a nutrient value checking multiple possible IDs"""
    for n in nutrient_list:
        if n['nutrientId'] in ids:
            return n['value']
    return 0

@app.route('/api/search', methods=['GET'])
def search_food():
    query = request.args.get('q')
    if not query: return jsonify({"error": "No query"}), 400

    print(f"🔎 Searching USDA for: {query}...") 

    # We send dataType as a comma-separated string to prevent 400 errors
    payload = {
        "api_key": API_KEY,
        "query": query,
        "dataType": "Foundation,SR Legacy,Branded,Survey (FNDDS)",
        "pageSize": 25
    }

    try:
        r = session.get(BASE_URL, params=payload, timeout=10)
        
        # Fallback to generic search if strict search fails
        if r.status_code != 200:
            print(f"⚠️ Specific search failed ({r.status_code}). Removing filters...")
            payload.pop("dataType") 
            time.sleep(1)
            r = session.get(BASE_URL, params=payload, timeout=10)

        if r.status_code != 200:
            print(f"❌ API FAILURE: {r.status_code} - {r.text}")
            return jsonify([]), 200

        data = r.json()
        final_results = []
        
        for item in data.get('foods', []):
            n_list = item.get('foodNutrients', [])
            
            # Legacy vs Foundation ID checks
            protein = get_nutrient(n_list, 203, 1003)
            fat = get_nutrient(n_list, 204, 1004)
            calories = get_nutrient(n_list, 208, 1008)
            sugar = get_nutrient(n_list, 269, 2000)

            srv_g = item.get('servingSize', 100)
            
            name = item.get('description')
            cat_str = item.get('foodCategory', '')
            
            # --- APPLY NEW CATEGORY LOGIC ---
            category = map_usda_category(cat_str, name)

            # Special Checks
            cooked_in = None
            special = None
            ing = item.get('ingredients', '').lower()
            name_lower = name.lower()

            if any(x in ing for x in ["soybean", "canola", "corn oil", "sunflower"]):
                cooked_in = "seed_oil"
            
            if "tallow" in name_lower or "grass-fed" in name_lower or "raw milk" in name_lower:
                special = "rfk_bonus"

            # Filter out empty entries
            if calories > 0 or protein > 0:
                final_results.append({
                    "name": name,
                    "category": category,
                    "protein_g": protein,
                    "fat_g": fat,
                    "sugar_g": sugar,
                    "calories": calories,
                    "cooked_in": cooked_in,
                    "special": special,
                    "serving_g": srv_g 
                })

        print(f"✅ Found {len(final_results)} results for '{query}'.")
        return jsonify(final_results)

    except Exception as e:
        print(f"❌ SYSTEM ERROR: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

if __name__ == '__main__':
    print("🚀 Server running. Open: http://127.0.0.1:5000/")
    app.run(debug=True, port=5000)