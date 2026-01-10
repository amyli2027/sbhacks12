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
    name_lower = str(name).lower()
    
    if "candy" in cat or "chocolate" in name_lower or "reeses" in name_lower or "snack" in cat: return "sweet"
    if "cookie" in name_lower or "pastry" in cat or "croissant" in name_lower or "cake" in name_lower: return "sweet"
    if "soda" in name_lower or "beverage" in cat or "drink" in name_lower or "juice" in name_lower: return "sweet"
    if "chips" in name_lower or "fries" in name_lower or "doritos" in name_lower: return "veg" 
    if "fruit" in cat: return "fruit"
    if "vegetable" in cat or "pod" in cat: return "veg"
    if "beef" in cat or "pork" in cat or "poultry" in cat or "sausage" in cat or "fish" in cat or "egg" in cat: return "protein"
    if "cereal" in cat or "grain" in cat or "bread" in cat or "pasta" in cat: return "grain"
    if "dairy" in cat or "milk" in cat or "cheese" in cat or "yogurt" in cat: return "dairy"
    if "fats" in cat or "oil" in cat or "butter" in cat or "margarine" in cat: return "fat"
    return "grain"

@app.route('/api/search', methods=['GET'])
def search_food():
    query = request.args.get('q')
    if not query: return jsonify({"error": "No query"}), 400

    print(f"🔎 Searching USDA for: {query.upper()}...") 

    payload = {
        "api_key": API_KEY,
        # AUTO-CAPS FIX: Forces "CELERY" to help find vegetables
        "query": query.upper(),
        "dataType": ["Foundation", "SR Legacy", "Branded", "Survey (FNDDS)"], 
        "pageSize": 100
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
            category = map_usda_category(item.get('foodCategory', ''), name)
            data_type = item.get('dataType', '') 
            
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

            if data_type in ["SR Legacy", "Foundation", "Survey (FNDDS)"]:
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