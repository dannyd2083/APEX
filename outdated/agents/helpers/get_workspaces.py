import requests
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Configuration variables
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / '.env')
ANYTHINGLLM_API_URL = os.getenv("ANYTHINGLLM_API_URL", "http://localhost:3001/api/v1")
ANYTHINGLLM_API_KEY = os.getenv("ANYTHINGLLM_API_KEY")

# Get the names, IDs, and slugs of all available workspaces
def get_workspaces():
    """Fetch and display all available workspaces."""
    print("=" * 60)
    print("Fetching Workspaces from AnythingLLM")
    print("=" * 60)
    print(f"\nAPI URL: {ANYTHINGLLM_API_URL}")
    print(f"Endpoint: {ANYTHINGLLM_API_URL}/workspaces\n")
    
    try:
        response = requests.get(
            f"{ANYTHINGLLM_API_URL}/workspaces",
            headers={
                "Authorization": f"Bearer {ANYTHINGLLM_API_KEY}",
                "Content-Type": "application/json",
            },
        )
        
        print(f"Status Code: {response.status_code}\n")
        
        if response.status_code == 200:
            data = response.json()
            workspaces = data.get("workspaces", [])
            
            if not workspaces:
                print("No workspaces found")
                return
            
            print(f"Successfully connected. Found {len(workspaces)} workspace(s):\n")
            print("=" * 60)
            
            for i, ws in enumerate(workspaces, 1):
                print(f"\nWorkspace #{i}:")
                print(f"  Name: {ws.get('name', 'N/A')}")
                print(f"  Slug: {ws.get('slug', 'N/A')}")
                print(f"  ID: {ws.get('id', 'N/A')}")
                print("-" * 60)
            
        elif response.status_code == 401:
            print("Authentication failed.")
            print("Check your API key in AnythingLLM: Settings > Tools > Developer API")
            
        elif response.status_code == 404:
            print("Endpoint not found!")
            
        else:
            print(f"Unexpected response ({response.status_code})")
            print(f"Response: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("Connection Error!")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    print(ANYTHINGLLM_API_KEY)
    get_workspaces()