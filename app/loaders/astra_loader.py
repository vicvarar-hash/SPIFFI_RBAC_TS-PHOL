import json
import os
from typing import List
from app.models.astra import AstraTask

def load_astra_dataset(file_path: str) -> List[AstraTask]:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"ASTRA dataset not found at {file_path}")
    
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    tasks = []
    for item in data:
        normalized_task = AstraTask(
            task=item["input"]["task"],
            candidate_tools=item["input"]["tools"],
            candidate_mcp=item["input"]["mcp_servers"],
            groundtruth_tools=item["groundtruth"]["tools"],
            groundtruth_mcp=item["groundtruth"]["mcp_servers"],
            match_tag=item.get("match_tag", "unknown")
        )
        tasks.append(normalized_task)
    
    return tasks
