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
    # 1. CLEAN UP STRINGS
    cat = str(usda_cat).lower()
    name_lower = str(name).lower()
    
    # --- PHASE 1: CHECK OFFICIAL USDA CATEGORY FIRST (More Accurate) ---
    
    # SWEETS
    if "candy" in cat or "sweets" in cat or "sugars" in cat or "chocolate" in cat: return "sweet"
    if "beverages" in cat and ("sugar" in name_lower or "carbonated" in cat or "soda" in name_lower): return "sweet"
    if "baked" in cat and ("cookie" in name_lower or "cake" in name_lower or "brownie" in name_lower or "pie" in name_lower): return "sweet"

    # VEGETABLES
    if "vegetable" in cat: return "veg"
    
    # FRUITS
    if "fruit" in cat and "juice" not in cat: return "fruit" # Keep juice separate if you want

    # DAIRY
    if "milk" in cat or "dairy" in cat or "cheese" in cat or "yogurt" in cat: return "dairy"

    # PROTEIN
    if "beef" in cat or "pork" in cat or "poultry" in cat or "sausages" in cat or "meats" in cat or "fish" in cat or "egg" in cat or "seafood" in cat:
        return "protein"

    # GRAINS
    if "grain" in cat or "cereal" in cat or "baked products" in cat or "pasta" in cat:
        return "grain"
    
    # FATS
    if "fats" in cat or "oils" in cat or "butter" in cat: return "fat"
    if "nut" in cat and "butter" in name_lower: return "fat" # Peanut butter

    # --- PHASE 2: FALLBACK TO NAME SEARCH (If Category was vague) ---
    
    if "berry" in name_lower or "apple" in name_lower or "banana" in name_lower or "grape" in name_lower: return "fruit"
    if "spinach" in name_lower or "carrot" in name_lower or "corn" in name_lower or "broccoli" in name_lower: return "veg"
    if "steak" in name_lower or "chicken" in name_lower or "burger" in name_lower: return "protein"
    if "bread" in name_lower or "rice" in name_lower or "toast" in name_lower or "oat" in name_lower: return "grain"
    if "soda" in name_lower or "coke" in name_lower: return "sweet"

    # Default
    return "grain"

@app.route('/api/search', methods=['GET'])
def search_food():
    query = request.args.get('q')
    if not query: return jsonify({"error": "No query"}), 400

    print(f"🔎 Searching USDA for: {query.upper()}...") 

    payload = {
        "api_key": API_KEY,
        "query": query.upper(),
        # We need "Survey (FNDDS)" because it has the best category names like "Milk" or "Meat"
        "dataType": ["Foundation", "SR Legacy", "Branded", "Survey (FNDDS)"], 
        "pageSize": 50 
    }

    try:
        r = session.get(BASE_URL, params=payload, timeout=20)
        if r.status_code == 400:
            time.sleep(0.5)
            r = session.get(BASE_URL, params=payload, timeout=20)

        if r.status_code != 200:
            print(f"❌ API ERROR: {r.status_code}")
            return jsonify([]), 200

        data = r.json()
        raw_foods = []
        branded_foods = []
        
        for item in data.get('foods', []):
            nutrients = {n['nutrientId']: n['value'] for n in item.get('foodNutrients', [])}
            protein = nutrients.get(203, 0)
            fat = nutrients.get(204, 0)
            sugar = nutrients.get(269, nutrients.get(2000, 0))
            calories = nutrients.get(208, 0)

            name = item.get('description')
            # HERE IS THE MAGIC: We fetch the official category now!
            usda_cat = item.get('foodCategory', '') 
            
            category = map_usda_category(usda_cat, name)
            
            # ... (Rest of logic is same) ...
            
            cooked_in = None
            special = None
            lower_name = name.lower()
            ingredients = item.get('ingredients', '').lower()
            
            if "soybean" in ingredients or "canola" in ingredients or "sunflower" in ingredients or "corn oil" in ingredients:
                cooked_in = "seed_oil"
            if "tallow" in lower_name or "raw milk" in lower_name or "grass-fed" in lower_name:
                special = "rfk_bonus"

            food_obj = {
                "name": name,
                "category": category,
                "protein_g": protein,
                "fat_g": fat,
                "sugar_g": sugar,
                "calories": calories,
                "cooked_in": cooked_in,
                "special": special
            }

            if item.get('dataType') in ["SR Legacy", "Foundation", "Survey (FNDDS)"]:
                raw_foods.append(food_obj)
            else:
                branded_foods.append(food_obj)

        final_results = (raw_foods + branded_foods)[:20]
        print(f"✅ Found {len(final_results)} sorted results.")
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