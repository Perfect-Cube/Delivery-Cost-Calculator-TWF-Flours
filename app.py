import math
from flask import Flask, request, jsonify, render_template
import itertools

app = Flask(__name__)

# --- Data Definitions ---

PRODUCTS = { # Same as before
    "A": {"center": "C1", "weight": 3.0}, "B": {"center": "C1", "weight": 2.0},
    "C": {"center": "C1", "weight": 8.0}, "D": {"center": "C2", "weight": 12.0},
    "E": {"center": "C2", "weight": 25.0}, "F": {"center": "C2", "weight": 15.0},
    "G": {"center": "C3", "weight": 0.5}, "H": {"center": "C3", "weight": 1.0},
    "I": {"center": "C3", "weight": 2.0},
}

# --- CORRECTED DISTANCES: No direct C1 <-> C3 ---
DISTANCES = {
    ("C1", "L1"): 3.0, ("L1", "C1"): 3.0,
    ("C2", "L1"): 2.5, ("L1", "C2"): 2.5,
    ("C3", "L1"): 2.0, ("L1", "C3"): 2.0,
    ("C1", "C2"): 4.0, ("C2", "C1"): 4.0,
    ("C2", "C3"): 3.0, ("C3", "C2"): 3.0,
    # ("C1", "C3"): 3.4, ("C3", "C1"): 3.4, # REMOVED
}

CENTERS = ["C1", "C2", "C3"]
LOCATIONS = ["C1", "C2", "C3", "L1"] # All possible locations

# --- Helper Functions ---

def get_distance(loc1, loc2):
    """Gets DIRECT distance between two locations."""
    if loc1 == loc2: return 0.0
    # Use original keys first, then try reverse for symmetric access
    dist = DISTANCES.get((loc1, loc2))
    if dist is None:
        dist = DISTANCES.get((loc2, loc1))
    # Return infinity if no DIRECT path defined in DISTANCES
    return dist if dist is not None else float('inf')

def calculate_segment_cost(weight, distance):
    """ Calculates cost for a single DIRECT travel segment. Includes deadhead cost."""
    if distance <= 0 or distance == float('inf'): return 0.0
    epsilon = 1e-9
    if weight <= epsilon: cost_per_unit = 10.0 # Deadhead
    elif weight <= 5.0 + epsilon: cost_per_unit = 10.0
    else:
        additional_blocks = math.ceil(max(0.0, weight - 5.0 - epsilon) / 5.0)
        cost_per_unit = 10.0 + 8.0 * additional_blocks
    return cost_per_unit * distance

def _calculate_travel_cost_between_stops(loc_a, loc_b, weight_carried):
    """
    Calculates travel cost between loc_a and loc_b, handling
    the C1 <-> C3 case via C2.
    Returns the cost for the travel segment(s).
    """
    direct_dist = get_distance(loc_a, loc_b)

    # If direct path exists (or A=B)
    if direct_dist != float('inf'):
        return calculate_segment_cost(weight_carried, direct_dist)

    # Handle C1 <-> C3 via C2 case specifically
    elif (loc_a == "C1" and loc_b == "C3") or (loc_a == "C3" and loc_b == "C1"):
        # Cost A -> C2
        dist_a_c2 = get_distance(loc_a, "C2")
        cost_a_c2 = calculate_segment_cost(weight_carried, dist_a_c2)

        # Cost C2 -> B (weight remains the same as nothing picked up at C2)
        dist_c2_b = get_distance("C2", loc_b)
        cost_c2_b = calculate_segment_cost(weight_carried, dist_c2_b)

        # Check if intermediate distances are valid
        if cost_a_c2 == float('inf') or cost_c2_b == float('inf'):
             print(f"Warning: Cannot route {loc_a} to {loc_b} via C2.")
             return float('inf') # Should not happen with current map

        return cost_a_c2 + cost_c2_b
    else:
        # No direct path and not the C1-C2-C3 case we handle
        print(f"Warning: No path defined between {loc_a} and {loc_b}")
        return float('inf') # Indicate no path found

# --- Calculation Logic ---

def _calculate_overall_minimum_cost(order_data):
    """
    Calculates the overall minimum cost considering Simple Pickup
    and Partial Delivery, routing C1<->C3 via C2.
    Returns (cost, error_message).
    """
    items_needed = {}
    needed_centers = set()
    weight_from_center = {c: 0.0 for c in CENTERS}
    total_weight = 0.0
    parse_error = None

    # --- 1. Parse and Validate Order ---
    try: # (Same parsing logic as before)
        for product_code, quantity in order_data.items():
            if not isinstance(quantity, int) or quantity < 0:
                 parse_error = f"Invalid quantity '{quantity}' for product {product_code}." ; break
            if quantity == 0: continue
            product_info = PRODUCTS.get(product_code)
            if not product_info:
                parse_error = f"Product {product_code} not found." ; break
            center = product_info["center"] ; weight = product_info["weight"]
            item_total_weight = weight * quantity
            items_needed[product_code] = quantity ; needed_centers.add(center)
            weight_from_center[center] += item_total_weight
            total_weight += item_total_weight
        if parse_error: return None, parse_error
        if not items_needed: return 0, None
    except Exception as e: return None, f"Error processing order: {str(e)}"

    min_overall_cost = float('inf')

    # --- 2. Iterate through Start Centers ---
    for start_center in CENTERS:
        current_min_for_start = float('inf')

        # === Strategy 1: Simple Pickup ===
        cost_simple = float('inf')
        pickup_centers_to_visit = list(needed_centers - {start_center})

        # Base path starts at the starting center
        base_path = [start_center]

        # Generate permutations for visiting other centers
        if not pickup_centers_to_visit:
             # Only need start_center (or none needed, handled earlier)
             if start_center in needed_centers or not needed_centers :
                  cost_simple = _calculate_travel_cost_between_stops(start_center, 'L1', total_weight)
             # else: cost remains infinity if start_center not needed but others are (invalid start for simple pickup?)

        else: # Need to visit other centers
            min_perm_cost = float('inf')
            for order in itertools.permutations(pickup_centers_to_visit):
                current_perm_cost = 0.0
                current_perm_weight = weight_from_center.get(start_center, 0.0)
                loc_a = start_center

                # Calculate cost for pickup legs
                valid_path = True
                for loc_b in order:
                    segment_cost = _calculate_travel_cost_between_stops(loc_a, loc_b, current_perm_weight)
                    if segment_cost == float('inf'):
                         valid_path = False; break # Stop if any segment is impossible
                    current_perm_cost += segment_cost
                    current_perm_weight += weight_from_center.get(loc_b, 0.0) # Add weight picked at loc_b
                    loc_a = loc_b # Move to the next location
                
                if not valid_path: continue # Skip this permutation if impossible path

                # Calculate final leg cost (last pickup location to L1)
                final_leg_cost = _calculate_travel_cost_between_stops(loc_a, 'L1', total_weight)
                if final_leg_cost == float('inf'):
                     continue # Skip if final leg impossible

                total_path_cost = current_perm_cost + final_leg_cost
                min_perm_cost = min(min_perm_cost, total_path_cost)

            cost_simple = min_perm_cost # Min cost found across permutations


        # === Strategy 2: Plausible Partial Delivery (Start->L1->PickupRest->L1) ===
        cost_partial = float('inf')
        # Only possible if start has items and other centers are also needed
        if weight_from_center.get(start_center, 0) > 0 and len(needed_centers) > 1:
            # --- Leg 1: Start -> L1 (Drop start items) ---
            w_leg1 = weight_from_center[start_center]
            cost_leg1 = _calculate_travel_cost_between_stops(start_center, "L1", w_leg1)

            if cost_leg1 != float('inf'):
                # --- Legs 2 & 3: L1 -> Pickups -> L1 (Drop remaining) ---
                remaining_centers = list(needed_centers - {start_center})
                weight_remaining = total_weight - w_leg1
                cost_pickup_and_final_leg = float('inf')

                if remaining_centers:
                    min_perm_pickup_cost = float('inf')
                    for order in itertools.permutations(remaining_centers):
                        current_pickup_cost = 0.0
                        current_pickup_weight = 0.0 # Start empty from L1
                        loc_a = "L1"
                        valid_pickup_path = True

                        # Cost from L1 through pickup centers
                        for loc_b in order:
                            segment_cost = _calculate_travel_cost_between_stops(loc_a, loc_b, current_pickup_weight)
                            if segment_cost == float('inf'):
                                valid_pickup_path = False; break
                            current_pickup_cost += segment_cost
                            current_pickup_weight += weight_from_center.get(loc_b, 0.0)
                            loc_a = loc_b # loc_a is now last pickup center

                        if not valid_pickup_path: continue

                        # Cost from last pickup center to L1 (carrying remaining weight)
                        final_delivery_cost = _calculate_travel_cost_between_stops(loc_a, 'L1', weight_remaining)
                        if final_delivery_cost == float('inf'):
                            continue

                        total_pickup_route_cost = current_pickup_cost + final_delivery_cost
                        min_perm_pickup_cost = min(min_perm_pickup_cost, total_pickup_route_cost)

                    cost_pickup_and_final_leg = min_perm_pickup_cost
                else:
                     # Should not happen if len(needed_centers) > 1 and start removed?
                     # If somehow only start center was needed, this strategy doesn't apply well.
                     # Let's assume remaining_centers is always non-empty here based on initial check.
                     cost_pickup_and_final_leg = 0 # No further pickups needed? No, this case is covered by simple pickup.

                # Combine costs if valid
                if cost_pickup_and_final_leg != float('inf'):
                    cost_partial = cost_leg1 + cost_pickup_and_final_leg

            # else: cost_partial remains infinity if leg 1 failed

        # --- Determine Minimum for this Start Center ---
        current_min_for_start = min(cost_simple, cost_partial)
        min_overall_cost = min(min_overall_cost, current_min_for_start)

    # --- 3. Return Final Result ---
    final_cost = round(min_overall_cost) if min_overall_cost != float('inf') else 0 # Or maybe return error if inf?
    if min_overall_cost == float('inf'):
        return None, "No valid delivery path found for the order."

    return final_cost, None

# --- Flask Routes (API and Web UI - No changes needed here) ---
# Use the same Flask routes as in the previous version,
# they call _calculate_overall_minimum_cost which now has the updated logic.

@app.route('/', methods=['GET', 'POST'])
def index():
    cost = None ; error = None ; submitted_order_form = {}
    if request.method == 'POST':
        order_json = {}
        try:
            for product_code in PRODUCTS.keys():
                quantity_str = request.form.get(product_code, '0')
                quantity = int(quantity_str) if quantity_str and quantity_str.isdigit() else 0
                if quantity < 0: raise ValueError("Quantity cannot be negative")
                if quantity > 0: order_json[product_code] = quantity
                submitted_order_form[product_code] = quantity
        except ValueError as e: error = f"Invalid input: Quantities must be non-negative whole numbers. ({e})"
        except Exception as e: error = f"An error occurred processing the form: {str(e)}"

        if not error:
            if not order_json: cost = 0
            else:
                calculated_cost, calc_error = _calculate_overall_minimum_cost(order_json)
                if calc_error: error = calc_error
                else: cost = calculated_cost

    # Update note for HTML template
    assumption_note = "Travel between C1 and C3 requires routing via C2 (distance 4.0 + 3.0 = 7.0 units)."
    test_case_note = "Note: Calculated costs may differ from provided test cases (esp. Test Case 1) due to C1-C3 routing change."

    return render_template(
        'index.html',
        products=PRODUCTS,
        cost=cost,
        error=error,
        submitted_order=submitted_order_form,
        assumption_note=assumption_note, # Pass new notes
        test_case_note=test_case_note
    )

@app.route('/calculate', methods=['POST'])
def calculate_api():
    order_data = request.get_json()
    if not order_data: return jsonify({"error": "Invalid JSON input"}), 400
    validated_order = {}
    for product_code, quantity in order_data.items():
        if not isinstance(quantity, int) or quantity < 0:
             return jsonify({"error": f"Invalid quantity for {product_code}."}), 400
        if quantity > 0:
             if product_code not in PRODUCTS:
                  return jsonify({"error": f"Product {product_code} not found."}), 400
             validated_order[product_code] = quantity
    if not validated_order: return jsonify({"minimum_cost": 0}), 200

    cost, error = _calculate_overall_minimum_cost(validated_order)
    if error: return jsonify({"error": error}), 400 # Return error if no path found
    else: return jsonify({"minimum_cost": cost}), 200

# --- Main Execution ---
if __name__ == '__main__':
    app.run(debug=True)