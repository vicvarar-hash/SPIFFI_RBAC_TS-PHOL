from app.services.heuristic_service import HeuristicService
import os

def test_inference():
    # Ensure we are in the right directory
    svc = HeuristicService()
    
    test_tools = [
        "get_issue",               # Standard prefix
        "jira_get_issue",          # Underline namespaced
        "atlassian_list_projects", # Underline namespaced
        "search_docs",             # Standard
        "mongodb.search_docs",     # Dot namespaced
        "random_tool_name"         # No match
    ]
    
    print(f"{'Tool Name':<25} | {'Actions':<20} | {'Rule ID'}")
    print("-" * 60)
    
    for tool in test_tools:
        actions, rule_id = svc.infer_actions(tool)
        print(f"{tool:<25} | {str(actions):<20} | {rule_id}")

if __name__ == "__main__":
    test_inference()
