import requests

from datetime import datetime
from langchain_core.language_models.llms import LLM
from typing import Optional, List

from agents.helpers.token_tracker import token_tracker

# AnythingLLM wrapper
class AnythingLLMLLM(LLM):
    """Wrapper to connect LangChain to a local AnythingLLM instance."""
    base_url: str
    api_key: str
    workspace_slug: str
    
    @property
    def _llm_type(self) -> str:
        return "anythingllm"
    
    def _call(self, prompt: str, stop: Optional[List[str]] = None, phase: str = "unknown") -> str:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        # TEMP: temporary solution to create a new thread with identifier for each prompt to avoid context issues
        now = datetime.now()
        ts = now.strftime("%Y%m%dT%H%M%SZ")
        thread_slug = f"test_{ts}"
        thread_name = f"Test {now.isoformat(timespec='seconds')}Z"

        # Set API - Create new thread
        create_url = f"{self.base_url}/workspace/{self.workspace_slug}/thread/new"
        create_body = {
            "slug": thread_slug,
            "name": thread_name
        }

        # Set API - Chat
        chat_url = f"{self.base_url}/workspace/{self.workspace_slug}/thread/{thread_slug}/chat"
        chat_body = {
            "message": prompt,
            "mode": "chat"
        }

        try:
            # Create new thread
            new_thread_resp = requests.post(create_url, json=create_body, headers=headers)
            new_thread_resp.raise_for_status()
            print(f"Created new thread: {thread_name} ({thread_slug})")

            # Send chat message
            response = requests.post(chat_url, json=chat_body, headers=headers)
            response.raise_for_status()
            json_response = response.json()

            output_text = json_response.get("textResponse", json_response.get("message", ""))

            # Estimate tokens (rough: 1 token ≈ 4 chars)
            input_tokens = len(prompt) // 4
            output_tokens = len(output_text) // 4

            # Log to tracker
            token_tracker.log_call(
                provider="anythingllm",
                phase=phase,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model="anythingllm"
            )

            return output_text

        except requests.exceptions.RequestException as e:
            raise ValueError(f"Error from AnythingLLM API: {e}")

    # Test AnythingLLM workspace connection
    def test_connection(self):
        print("Testing connection to AnythingLLM...")
        print(f"URL: {self.base_url}/workspace/{self.workspace_slug}/chat")
        
        try:
            response = requests.post(
                f"{self.base_url}/workspace/{self.workspace_slug}/chat",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"message": "Hello, what model is currently being used?", "mode": "chat"},
            )
            
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                print("Connection successful")
                print("Response:", response.json())
                return True
            else:
                print(f"Connection failed ({response.status_code})")
                print("Response:", response.text)
                return False
                
        except Exception as e:
            print(f"Error connecting to AnythingLLM: {e}")
            return False
