import os
import google.generativeai as genai
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import re
import requests
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import json

# Hardcoded API keys for the demo
GEMINI_API_KEY = "AIzaSyC9q05qjQCJOYYBncmL1j9UE4PfLPoOV-4"
PAYSTACK_SECRET_KEY = "sk_test_5df5b996188b4a99fbc47ca2ba7063ac2465111e"

# Configure the Generative AI API with the API key
genai.configure(api_key=GEMINI_API_KEY)

# Try different model names until one works
model = None
try:
    # Try the most common working model names
    model = genai.GenerativeModel('gemini-pro')
    print("✓ Using gemini-pro model")
except Exception as e:
    print(f"✗ Model error: {e}")
    try:
        # Try the newer model name
        model = genai.GenerativeModel('gemini-1.0-pro')
        print("✓ Using gemini-1.0-pro model")
    except Exception as e2:
        print(f"✗ Model error: {e2}")
        try:
            # Try with full model path
            model = genai.GenerativeModel('models/gemini-pro')
            print("✓ Using models/gemini-pro model")
        except Exception as e3:
            print(f"✗ All model attempts failed: {e3}")
            model = None

# Initialize Flask app
app = Flask(__name__, static_folder='../frontend')
CORS(app)  # Enable CORS for all routes

# --- SECURITY SETUP --- #
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

def sanitize_input(text):
    """Sanitize user input to prevent injection attacks."""
    if text is None:
        return ""
    sanitized_text = re.sub(r'[<>{}()\[\]]', '', text)
    return sanitized_text[:500]  # Limit input length

# --- ROUTES --- #

@app.route('/')
def serve_frontend():
    return send_from_directory('../frontend', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('../frontend', path)

@app.route('/test', methods=['GET'])
def test():
    return jsonify({"message": "SecureRecipe Backend is LIVE! 🍳"})

@app.route('/test-ai', methods=['GET'])
def test_ai():
    """Test if Gemini AI is working properly"""
    try:
        if model is None:
            return jsonify({"status": "error", "message": "AI model not configured"})
        
        # Test with a simple prompt
        test_prompt = "Hello, are you working? Respond with 'Yes, I am working!'"
        response = model.generate_content(test_prompt)
        
        return jsonify({
            "status": "success", 
            "message": "AI is working!",
            "response": response.text
        })
    except Exception as e:
        return jsonify({
            "status": "error", 
            "message": "AI is not working",
            "error": str(e)
        })

@app.route('/generate-recipes', methods=['POST'])
@limiter.limit("5 per minute")
def generate_recipes():
    try:
        # Get the JSON data from the request
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data received"}), 400

        user_ingredients = data.get('ingredients', '')
        clean_ingredients = sanitize_input(user_ingredients)

        if not clean_ingredients:
            return jsonify({"error": "Please provide valid ingredients."}), 400

        # If AI model is not available, use mock data
        if model is None:
            print("Using mock data instead of AI")
            recipes = get_mock_recipes(clean_ingredients)
            return jsonify({"recipes": recipes})

        # Try to use AI to generate recipes
        prompt = f"""
        Act as a professional chef with 20 years of experience. Create 2 unique and delicious recipes based on: {clean_ingredients}

        IMPORTANT: 
        - Make each recipe completely different in style (e.g., one Italian, one Asian, one Mexican)
        - Use different cooking methods (baking, grilling, frying, etc.)
        - Include varied flavor profiles (spicy, sweet, savory, etc.)

        For each recipe, provide:
        1) A creative and descriptive name
        2) A complete list of all ingredients needed
        3) Detailed, step-by-step cooking instructions
        4) Estimated preparation and cooking time

        Format the response as a valid JSON array with these exact keys for each recipe:
        - "recipe_name"
        - "ingredients" 
        - "instructions"
        - "cook_time"

        Make the recipes genuinely different from each other!
        """

        response = model.generate_content(prompt)
        ai_response = response.text

        try:
            start_index = ai_response.find('[')
            end_index = ai_response.rfind(']') + 1
            
            if start_index == -1 or end_index == 0:
                raise ValueError("Could not find JSON array in AI response")
                
            json_str = ai_response[start_index:end_index]
            recipes = json.loads(json_str)
            
            # Validate the response structure
            if not isinstance(recipes, list):
                raise ValueError("AI response is not a list")
                
            for recipe in recipes:
                if not all(key in recipe for key in ['recipe_name', 'ingredients', 'instructions', 'cook_time']):
                    raise ValueError("AI response missing required fields")
                    
        except (json.JSONDecodeError, ValueError) as e:
            print(f"AI response parsing failed: {e}")
            print(f"Raw AI response: {ai_response}")
            recipes = get_mock_recipes(clean_ingredients)

        return jsonify({"recipes": recipes})

    except Exception as e:
        print(f"Server Error: {e}")
        # Fall back to mock data if anything goes wrong
        recipes = get_mock_recipes(clean_ingredients)
        return jsonify({"recipes": recipes})

@app.route('/search-recipes', methods=['POST'])
@limiter.limit("5 per minute")
def search_recipes():
    try:
        # Get the JSON data from the request
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data received"}), 400

        search_query = data.get('query', '')
        clean_query = sanitize_input(search_query)

        if not clean_query:
            return jsonify({"error": "Please provide a valid search term."}), 400

        # If AI model is not available, use mock data
        if model is None:
            print("Using mock data for search")
            recipes = get_mock_search_results(clean_query)
            return jsonify({"recipes": recipes})

        # Try to use AI to search for recipes
        prompt = f"""
        Act as a professional chef. Suggest 3 delicious recipes that match this search: {clean_query}.
        For each recipe, provide:
        1) A creative name.
        2) A list of main ingredients.
        3) Clear, step-by-step instructions.
        4) An estimated cooking time.
        
        Format the entire response as a valid JSON array. Each object in the array must have these exact keys:
        - "recipe_name"
        - "ingredients"
        - "instructions"
        - "cook_time"
        """

        response = model.generate_content(prompt)
        ai_response = response.text

        try:
            start_index = ai_response.find('[')
            end_index = ai_response.rfind(']') + 1
            
            if start_index == -1 or end_index == 0:
                raise ValueError("Could not find JSON array in AI response")
                
            json_str = ai_response[start_index:end_index]
            recipes = json.loads(json_str)
            
            # Validate the response structure
            if not isinstance(recipes, list):
                raise ValueError("AI response is not a list")
                
            for recipe in recipes:
                if not all(key in recipe for key in ['recipe_name', 'ingredients', 'instructions', 'cook_time']):
                    raise ValueError("AI response missing required fields")
                    
        except (json.JSONDecodeError, ValueError) as e:
            print(f"AI search response parsing failed: {e}")
            print(f"Raw AI response: {ai_response}")
            recipes = get_mock_search_results(clean_query)

        return jsonify({"recipes": recipes})

    except Exception as e:
        print(f"Search Error: {e}")
        # Fall back to mock data if anything goes wrong
        recipes = get_mock_search_results(clean_query)
        return jsonify({"recipes": recipes})

def get_mock_recipes(ingredients):
    """Return varied mock recipes based on input ingredients"""
    ingredients_lower = ingredients.lower()
    
    # Different recipe types based on input
    if "chicken" in ingredients_lower and "rice" in ingredients_lower:
        return [
            {
                "recipe_name": "Asian Chicken Stir-Fry",
                "ingredients": "chicken, rice, soy sauce, ginger, garlic, vegetables, sesame oil",
                "instructions": "1. Cook rice according to package instructions. 2. Cut chicken into strips and marinate in soy sauce. 3. Stir-fry garlic and ginger in sesame oil. 4. Add chicken and cook until done. 5. Add vegetables and stir-fry until crisp-tender. 6. Serve over rice.",
                "cook_time": "25 minutes"
            },
            {
                "recipe_name": "Mediterranean Chicken Bowl", 
                "ingredients": "chicken, rice, olive oil, lemon, herbs, cucumbers, tomatoes, feta cheese",
                "instructions": "1. Grill chicken with herbs and lemon. 2. Prepare rice. 3. Chop fresh vegetables. 4. Assemble bowls with rice, chicken, and fresh vegetables. 5. Drizzle with olive oil and lemon juice. 6. Top with feta cheese.",
                "cook_time": "30 minutes"
            }
        ]
    elif "pasta" in ingredients_lower:
        return [
            {
                "recipe_name": "Creamy Garlic Pasta",
                "ingredients": "pasta, garlic, cream, parmesan, butter, herbs",
                "instructions": "1. Cook pasta al dente. 2. Sauté garlic in butter. 3. Add cream and simmer. 4. Stir in parmesan until melted. 5. Combine with pasta. 6. Garnish with fresh herbs.",
                "cook_time": "20 minutes"
            },
            {
                "recipe_name": "Tomato Basil Pasta",
                "ingredients": "pasta, tomatoes, basil, garlic, olive oil, parmesan",
                "instructions": "1. Cook pasta al dente. 2. Sauté garlic in olive oil. 3. Add chopped tomatoes and cook until softened. 4. Toss with pasta and fresh basil. 5. Top with grated parmesan.",
                "cook_time": "15 minutes"
            }
        ]
    elif "beef" in ingredients_lower:
        return [
            {
                "recipe_name": "Beef Stir-Fry",
                "ingredients": "beef, vegetables, soy sauce, ginger, garlic, rice",
                "instructions": "1. Slice beef thinly against the grain. 2. Stir-fry with garlic and ginger. 3. Add vegetables and cook until crisp-tender. 4. Add soy sauce and simmer. 5. Serve over rice.",
                "cook_time": "20 minutes"
            },
            {
                "recipe_name": "Beef and Potato Stew",
                "ingredients": "beef, potatoes, carrots, onions, broth, herbs",
                "instructions": "1. Brown beef cubes in a pot. 2. Add chopped vegetables and broth. 3. Simmer for 1-2 hours until tender. 4. Season with herbs and spices. 5. Serve hot.",
                "cook_time": "1 hour 30 minutes"
            }
        ]
    else:
        # Default varied recipes
        return [
            {
                "recipe_name": "Savory Skillet Dish",
                "ingredients": f"{ingredients}, spices, oil, herbs",
                "instructions": "1. Prepare all ingredients. 2. Heat oil in a skillet. 3. Cook main ingredients until tender. 4. Add spices and seasonings. 5. Simmer for 10 minutes. 6. Serve hot with your favorite sides.",
                "cook_time": "30 minutes"
            },
            {
                "recipe_name": "Fresh Garden Salad",
                "ingredients": f"{ingredients}, lettuce, dressing, nuts, cheese",
                "instructions": "1. Wash and chop all vegetables. 2. Combine in a large bowl. 3. Add protein if available. 4. Toss with your favorite dressing. 5. Top with nuts and cheese. 6. Serve immediately.",
                "cook_time": "15 minutes"
            }
        ]

def get_mock_search_results(query):
    """Return mock search results for demo purposes"""
    query_lower = query.lower()
    
    if "pasta" in query_lower:
        return [
            {
                "recipe_name": "Creamy Garlic Pasta",
                "ingredients": "pasta, garlic, cream, parmesan cheese, olive oil, herbs",
                "instructions": "1. Cook pasta according to package instructions. 2. Sauté garlic in olive oil until fragrant. 3. Add cream and simmer for 5 minutes. 4. Add grated parmesan and stir until melted. 5. Combine with drained pasta and garnish with herbs.",
                "cook_time": "20 minutes"
            }
        ]
    elif "dessert" in query_lower or "sweet" in query_lower:
        return [
            {
                "recipe_name": "Chocolate Brownies",
                "ingredients": "chocolate, butter, sugar, eggs, flour, cocoa powder",
                "instructions": "1. Melt chocolate and butter together. 2. Mix in sugar and eggs. 3. Fold in flour and cocoa powder. 4. Bake at 350°F for 25-30 minutes. 5. Let cool before serving.",
                "cook_time": "40 minutes"
            }
        ]
    elif "curry" in query_lower:
        return [
            {
                "recipe_name": "Chicken Curry",
                "ingredients": "chicken, curry powder, coconut milk, onions, garlic, ginger",
                "instructions": "1. Sauté onions, garlic, and ginger until soft. 2. Add chicken and cook until browned. 3. Add curry powder and cook for 1 minute. 4. Add coconut milk and simmer for 20 minutes. 5. Serve with rice or bread.",
                "cook_time": "35 minutes"
            }
        ]
    elif "meat" in query_lower:
        return [
            {
                "recipe_name": "Grilled Meat Platter",
                "ingredients": "assorted meats, spices, olive oil, herbs",
                "instructions": "1. Season meats with spices and herbs. 2. Preheat grill to medium-high. 3. Grill meats to desired doneness. 4. Let rest for 5 minutes. 5. Slice and serve with sides.",
                "cook_time": "25 minutes"
            }
        ]
    else:
        return [
            {
                "recipe_name": f"Delicious {query.title()}",
                "ingredients": f"Fresh ingredients for {query}",
                "instructions": f"1. Prepare all ingredients. 2. Follow standard cooking techniques for {query}. 3. Cook until done. 4. Season to taste. 5. Serve and enjoy!",
                "cook_time": "30 minutes"
            }
        ]

@app.route('/verify-payment', methods=['POST'])
def verify_payment():
    try:
        data = request.get_json()
        reference = data.get('reference')
        
        if not reference:
            return jsonify({"error": "Payment reference is required."}), 400
            
        paystack_url = f'https://api.paystack.co/transaction/verify/{reference}'
        headers = {'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}'}
        paystack_response = requests.get(paystack_url, headers=headers)
        verification_data = paystack_response.json()

        if verification_data.get('status') and verification_data['data']['status'] == 'success':
            customer_email = verification_data['data']['customer']['email']
            return jsonify({
                "status": "success",
                "message": "Payment verified! Premium features unlocked.",
                "email": customer_email
            })
        else:
            return jsonify({"status": "failed", "message": "Payment verification failed."}), 400

    except Exception as e:
        print(f"Payment Verification Error: {e}")
        return jsonify({"error": "Payment verification failed."}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')