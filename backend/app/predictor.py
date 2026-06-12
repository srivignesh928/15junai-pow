"""
=========================================================

Project : AI Powered Vehicle Valuation System

Module  : Model Loader

=========================================================
"""

import joblib
from pathlib import Path

# Load model once when API starts

BASE_DIR = Path(__file__).resolve().parents[2]

MODEL_PATH = BASE_DIR / "models" / "vehicle_price_model_v1.pkl"

model = joblib.load(MODEL_PATH)


def predict_price(input_df):

    """
    Predict vehicle price.

    Parameters
    ----------
    input_df : pandas.DataFrame

    Returns
    -------
    float
    """

    prediction = model.predict(input_df)

    return float(prediction[0])


def estimate_damage_cost(description: str | None = None) -> float:
    if not description:
        return 0.0

    text = description.lower().strip()
    if not text:
        return 0.0

    major_keywords = [
        "major",
        "engine",
        "transmission",
        "frame",
        "accident",
        "flood",
        "airbag",
        "total",
        "fire",
        "rollover",
    ]
    medium_keywords = [
        "crack",
        "broken",
        "collision",
        "door",
        "window",
        "bumper",
        "fender",
        "headlight",
        "taillight",
        "windshield",
        "radiator",
    ]
    minor_keywords = [
        "scratch",
        "scuff",
        "dent",
        "dented",
        "chip",
        "chipped",
        "paint",
    ]

    if any(keyword in text for keyword in major_keywords):
        return 90000.0
    if any(keyword in text for keyword in medium_keywords):
        return 50000.0
    if any(keyword in text for keyword in minor_keywords):
        return 20000.0

    return min(15000.0 + len(text) * 18.0, 40000.0)


def calculate_confidence_score(payload: dict) -> int:
    score = 60
    weights = {
        "oem": 7,
        "model": 7,
        "variant": 6,
        "fuel": 5,
        "transmission": 5,
        "body": 5,
        "owner_type": 3,
        "City": 3,
        "state": 3,
        "km": 4,
        "car_age": 4,
    }
    for key, weight in weights.items():
        if payload.get(key) not in [None, "", 0]:
            score += weight

    if payload.get("damage_description"):
        score += 2

    return min(max(int(score), 45), 95)


def compute_suggested_price(predicted_price: float, damage_cost: float) -> float:
    floor_price = predicted_price * 0.72
    suggested = predicted_price - damage_cost
    return round(max(suggested, floor_price), 2)


def calculate_dynamic_profit_margin(predicted_price: float, payload: dict) -> float:
    """
    Calculate dynamic profit margin based on vehicle characteristics.
    
    Base margin: 10%
    Adjustments based on real-world risk factors:
    - Brand type (luxury/mass/budget)
    - Price range (expensive = slower sale)
    - Car age (older = more risk)
    - Mileage (high km = wear & tear)
    - Damage condition (repair uncertainty)
    - Ownership history (multiple owners = harder to sell)
    
    Returns margin as decimal (e.g., 0.12 for 12%)
    Range: 5% to 25%
    """
    base_margin = 0.10  # 10% base
    
    # 1. Brand Type Adjustment
    if payload.get("premium_brand", 0) == 1:
        base_margin += 0.05  # +5% for luxury brands (slow sale, high risk)
    
    # 2. Price Range Adjustment
    if predicted_price > 2000000:  # > 20 lakhs
        base_margin += 0.05  # +5% for expensive cars (fewer buyers)
    elif predicted_price > 1000000:  # > 10 lakhs
        base_margin += 0.03  # +3% for mid-range premium
    elif predicted_price < 300000:  # < 3 lakhs
        base_margin -= 0.02  # -2% for budget cars (fast turnover)
    
    # 3. Car Age Adjustment
    car_age = payload.get("car_age", 0)
    if car_age > 10:
        base_margin += 0.05  # +5% for very old cars (mechanical issues)
    elif car_age > 7:
        base_margin += 0.02  # +2% for old cars (maintenance needed)
    elif car_age < 3:
        base_margin -= 0.02  # -2% for newer cars (low risk, high demand)
    
    # 4. Mileage Adjustment
    km = payload.get("km", 0)
    if km > 100000:  # > 1 lakh km
        base_margin += 0.02  # +2% for high mileage (heavy wear)
    
    # 5. Damage Condition Adjustment
    damage_desc = payload.get("damage_description", "")
    if damage_desc:
        damage_lower = damage_desc.lower()
        if any(word in damage_lower for word in ["major", "accident", "engine", "transmission", "frame", "flood", "fire"]):
            base_margin += 0.05  # +5% for major damage (high uncertainty)
        elif any(word in damage_lower for word in ["broken", "collision", "crack", "door", "window", "bumper"]):
            base_margin += 0.03  # +3% for medium damage (known repairs)
        elif any(word in damage_lower for word in ["scratch", "dent", "minor", "scuff", "chip"]):
            base_margin += 0.01  # +1% for minor damage (small repairs)
    
    # 6. Ownership History Adjustment
    owner_type = payload.get("owner_type", "").lower()
    if "second" in owner_type:
        base_margin += 0.01  # +1% for second owner
    elif "third" in owner_type:
        base_margin += 0.02  # +2% for third owner
    elif "fourth" in owner_type or "4" in owner_type:
        base_margin += 0.03  # +3% for fourth+ owner
    
    # Cap the margin between 5% and 25%
    final_margin = min(max(base_margin, 0.05), 0.25)
    
    return final_margin


def calculate_transaction_price(predicted_price: float, damage_cost: float, transaction_type: str, payload: dict = None) -> dict:
    """
    Calculate transaction-specific pricing based on transaction type.
    
    Parameters
    ----------
    predicted_price : float
        Base predicted market value
    damage_cost : float
        Estimated damage repair cost
    transaction_type : str
        One of: "selling", "buying_resale", "buying_personal"
    
    Returns
    -------
    dict with transaction_price, profit_margin, price_range_min, price_range_max
    """
    market_value = predicted_price - damage_cost
    floor_price = predicted_price * 0.72
    market_value = max(market_value, floor_price)
    
    if transaction_type == "selling":
        # Selling mode: show suggested selling price
        return {
            "transaction_price": round(market_value, 2),
            "profit_margin": None,
            "price_range_min": None,
            "price_range_max": None
        }
    
    elif transaction_type == "buying_resale":
        # Buying for resale: calculate max buy price with DYNAMIC profit margin
        if payload is None:
            profit_margin = 0.10  # fallback to 10%
        else:
            profit_margin = calculate_dynamic_profit_margin(predicted_price, payload)
        
        max_buy_price = market_value / (1 + profit_margin)
        profit_amount = market_value - max_buy_price
        return {
            "transaction_price": round(max_buy_price, 2),
            "profit_margin": round(profit_amount, 2),
            "price_range_min": round(max_buy_price * 0.95, 2),
            "price_range_max": round(max_buy_price, 2)
        }
    
    elif transaction_type == "buying_personal":
        # Buying for personal use: show fair buy price (lower than market)
        fair_buy_price = market_value * 0.95  # 5% below market value
        fair_min = market_value * 0.90  # 10% below market
        fair_max = market_value * 0.98  # 2% below market
        return {
            "transaction_price": round(fair_buy_price, 2),
            "profit_margin": None,
            "price_range_min": round(fair_min, 2),
            "price_range_max": round(fair_max, 2)
        }
    
    else:
        # Default to selling
        return {
            "transaction_price": round(market_value, 2),
            "profit_margin": None,
            "price_range_min": None,
            "price_range_max": None
        }
