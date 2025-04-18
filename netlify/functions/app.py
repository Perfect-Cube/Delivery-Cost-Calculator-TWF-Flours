import math
import itertools
import json # For request body check
from flask import Flask, request, jsonify, render_template # Keep render_template if UI exists
# Import serverless_wsgi to wrap the app
import serverless_wsgi

app = Flask(__name__)

# --- Data Definitions (Same as before) ---
PRODUCTS = {
    "A": {"center": "C1", "weight": 3.0}, "B": {"center": "C1", "weight": 2.0},
    "C": {"center": "C1", "weight": 8.0}, "D": {"center": "C2", "weight": 12.0},
    "E": {"center": "C2", "weight": 25.0}, "F": {"center": "C2", "weight": 15.0},
    "G": {"center": "C3", "weight": 0.5}, "H": {"center": "C3", "weight": 1.0},
    "I": {"center": "C3", "weight": 2.0},
}
DISTANCES = {
    ("C1", "L1"): 3.0, ("L1", "C1"): 3.0, ("C2", "L1"): 2.5, ("L1", "C2"): 2.5,
    ("C3", "L1"): 2.0, ("L1", "C3"): 2.0, ("C1", "C2"): 4.0, ("C2", "C1"): 4.0,
    ("C2", "C3"): 3.0, ("C3", "C2"): 3.0,
}
CENTERS = ["C1", "C2", "C3"]
LOCATIONS = ["C1", "C2", "C3", "L1"]

# --- Helper Functions (Same as before) ---
def get_distance(loc1, loc2):
    if loc1 == loc2: return 0.0
    dist = DISTANCES.get((loc1, loc2))
    if dist is None: dist = DISTANCES.get((loc2, loc1))
    return dist if dist is not None else float('inf')

def calculate_segment_cost(weight, distance):
    if distance <= 0 or distance == float('inf'): return 0.0
    epsilon = 1e-9
    if weight <= epsilon: cost_per_unit = 10.0 # Deadhead
    elif weight <= 5.0 + epsilon: cost_per_unit = 10.0
    else:
        additional_blocks = math.ceil(max(0.0, weight - 5.0 - epsilon) / 5.0)
        cost_per_unit = 10.0 + 8.0 * additional_blocks
    return cost_per_unit * distance

def _calculate_travel_cost_between_stops(loc_a, loc_b, weight_carried):
    direct_dist = get_distance(loc_a, loc_b)
    if direct_dist != float('inf'):
        return calculate_segment_cost(weight_carried, direct_dist)
    elif (loc_a, loc_b) in [("C1", "C3"), ("C3", "C1")]:
        dist_a_c2 = get_distance(loc_a, "C2") ; cost_a_c2 = calculate_segment_cost(weight_carried, dist_a_c2)
        dist_c2_b = get_distance("C2", loc_b) ; cost_c2_b = calculate_segment_cost(weight_carried, dist_c2_b)
        if cost_a_c2 == float('inf') or cost_c2_b == float('inf'): return float('inf')
        return cost_a_c2 + cost_c2_b
    else: return float('inf')

# --- Core Calculation Logic (_calculate_overall_minimum_cost - Same as before) ---
def _calculate_overall_minimum_cost(order_data):
    items_needed = {} ; needed_centers = set()
    weight_from_center = {c: 0.0 for c in CENTERS} ; total_weight = 0.0
    parse_error = None
    # 1. Parse/Validate
    try:
        for product_code, quantity in order_data.items():
            if not isinstance(quantity, int) or quantity < 0: parse_error = f"Invalid quantity '{quantity}' for {product_code}." ; break
            if quantity == 0: continue
            product_info = PRODUCTS.get(product_code);
            if not product_info: parse_error = f"Product {product_code} not found." ; break
            center = product_info["center"] ; weight = product_info["weight"] ; item_total_weight = weight * quantity
            items_needed[product_code] = quantity ; needed_centers.add(center)
            weight_from_center[center] += item_total_weight ; total_weight += item_total_weight
        if parse_error: return None, parse_error
        if not items_needed: return 0, None
    except Exception as e: return None, f"Error processing order: {str(e)}"

    min_overall_cost = float('inf')
    # 2. Iterate/Calculate Strategies
    for start_center in CENTERS:
        # Strategy 1: Simple Pickup
        cost_simple = float('inf') ; pickup_centers_to_visit = list(needed_centers - {start_center})
        if not pickup_centers_to_visit:
             if start_center in needed_centers or not needed_centers: cost_simple = _calculate_travel_cost_between_stops(start_center, 'L1', total_weight)
        else:
            min_perm_cost = float('inf')
            for order in itertools.permutations(pickup_centers_to_visit):
                current_perm_cost = 0.0 ; current_perm_weight = weight_from_center.get(start_center, 0.0) ; loc_a = start_center ; valid_path = True
                for loc_b in order:
                    segment_cost = _calculate_travel_cost_between_stops(loc_a, loc_b, current_perm_weight)
                    if segment_cost == float('inf'): valid_path = False; break
                    current_perm_cost += segment_cost ; current_perm_weight += weight_from_center.get(loc_b, 0.0) ; loc_a = loc_b
                if not valid_path: continue
                final_leg_cost = _calculate_travel_cost_between_stops(loc_a, 'L1', total_weight)
                if final_leg_cost == float('inf'): continue
                min_perm_cost = min(min_perm_cost, current_perm_cost + final_leg_cost)
            cost_simple = min_perm_cost

        # Strategy 2: Partial Delivery
        cost_partial = float('inf')
        if weight_from_center.get(start_center, 0) > 0 and len(needed_centers) > 1:
            w_leg1 = weight_from_center[start_center] ; cost_leg1 = _calculate_travel_cost_between_stops(start_center, "L1", w_leg1)
            if cost_leg1 != float('inf'):
                remaining_centers = list(needed_centers - {start_center}) ; weight_remaining = total_weight - w_leg1
                cost_pickup_and_final_leg = float('inf')
                if remaining_centers:
                    min_perm_pickup_cost = float('inf')
                    for order in itertools.permutations(remaining_centers):
                        current_pickup_cost = 0.0 ; current_pickup_weight = 0.0 ; loc_a = "L1" ; valid_pickup_path = True
                        for loc_b in order:
                            segment_cost = _calculate_travel_cost_between_stops(loc_a, loc_b, current_pickup_weight)
                            if segment_cost == float('inf'): valid_pickup_path = False; break
                            current_pickup_cost += segment_cost ; current_pickup_weight += weight_from_center.get(loc_b, 0.0) ; loc_a = loc_b
                        if not valid_pickup_path: continue
                        final_delivery_cost = _calculate_travel_cost_between_stops(loc_a, 'L1', weight_remaining)
                        if final_delivery_cost == float('inf'): continue
                        min_perm_pickup_cost = min(min_perm_pickup_cost, current_pickup_cost + final_delivery_cost)
                    cost_pickup_and_final_leg = min_perm_pickup_cost
                else: cost_pickup_and_final_leg = 0
                if cost_pickup_and_final_leg != float('inf'): cost_partial = cost_leg1 + cost_pickup_and_final_leg

        # Update Min
        min_overall_cost = min(min_overall_cost, cost_simple, cost_partial)
    # 3. Return Result
    if min_overall_cost == float('inf'): return None, "No valid delivery path found."
    return round(min_overall_cost), None

# --- Flask Routes ---

# IMPORTANT: The path here should match the *internal* function path later
# We use rewrites in netlify.toml to map user-facing paths to this.
# Let's make the base path '/' within the function context handle calculation.
@app.route('/', methods=['POST'])
def handle_calculate():
    """ Handles POST requests routed to this function for calculation """
    # Check if request body is JSON
    # serverless-wsgi might handle some header checks, but explicit is safer
    content_type = request.headers.get('Content-Type')
    if content_type is None or 'application/json' not in content_type:
         return jsonify({"error": "Request Content-Type must be application/json"}), 415

    try:
        order_data = request.get_json()
        if order_data is None: # Handle empty body or non-JSON parse
             raise json.JSONDecodeError("No JSON body found", "", 0)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON data in request body"}), 400
    except Exception as e: # Catch other potential issues during get_json
        return jsonify({"error": f"Error reading request body: {str(e)}"}), 400

    if not isinstance(order_data, dict):
         return jsonify({"error": "JSON data must be an object"}), 400

    validated_order = {}
    for product_code, quantity in order_data.items():
        if product_code not in PRODUCTS: return jsonify({"error": f"Product code '{product_code}' not found."}), 400
        if not isinstance(quantity, int) or quantity < 0: return jsonify({"error": f"Invalid quantity for {product_code}."}), 400
        if quantity > 0: validated_order[product_code] = quantity

    if not validated_order: return jsonify({"minimum_cost": 0}), 200

    cost, error = _calculate_overall_minimum_cost(validated_order)

    if error: return jsonify({"error": error}), 400
    else: return jsonify({"minimum_cost": cost}), 200

# Optional: Add a simple GET handler for the root if desired for basic check
# Make sure its path doesn't conflict if using rewrites
@app.route('/', methods=['GET'])
def handle_root_get():
    return jsonify({"message": "API Function is active. Use POST to this path for calculations."}), 200
    # Or render template if UI is kept AND pathing is handled correctly via rewrites
    # return render_template('index.html', ...) # Requires templates folder setup


# --- Serverless Handler ---
# This is the entry point for Netlify Functions (AWS Lambda)
def handler(event, context):
    # Use serverless_wsgi to handle the event and context, passing the Flask app
    return serverless_wsgi.handle(app, event, context)
