
import sys
import os
import json

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.tool_classifier import ToolClassifier

def verify():
    classifier = ToolClassifier()
    
    test_tools = [
        "get_order_book",         # Curated Hummingbot
        "get_ticker",             # Curated Hummingbot
        "extract_key_facts",      # Curated Wikipedia
        "get_coordinates",        # Curated Wikipedia
        "analyze_market_trends",  # Heuristic (verb-based)
        "verify_identity_status", # Heuristic (verb-based)
        "predict_price_dip"       # Heuristic (verb-based)
    ]
    
    results = classifier.classify_tools(test_tools)
    
    print(f"{'Tool':<25} | {'Source':<20} | {'Capabilities':<30}")
    print("-" * 80)
    for r in results:
        print(f"{r['tool']:<25} | {r['source']:<20} | {list(r['capabilities'])}")

if __name__ == "__main__":
    verify()
