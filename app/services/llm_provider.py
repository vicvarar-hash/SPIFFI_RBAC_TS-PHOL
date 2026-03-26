import os
import json
from openai import OpenAI
from typing import Optional, Dict, Any

class LLMProvider:
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.client = None
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key)

    def is_configured(self) -> bool:
        return self.client is not None

    def query(self, system_prompt: str, user_prompt: str) -> str:
        if not self.client:
            raise ValueError("OpenAI client not configured. Provide an API key.")
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )
        return response.choices[0].message.content
