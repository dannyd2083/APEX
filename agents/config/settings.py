import os
import sys

from dataclasses import dataclass
from dotenv import load_dotenv
from pathlib import Path


# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))

# Configuration variables
load_dotenv(dotenv_path=project_root / '.env')

@dataclass(frozen=True)
class LLMSettings:
    # AnythingLLM configuration
    ANYTHINGLLM_API_URL = os.getenv("ANYTHINGLLM_API_URL", "http://localhost:3001/api/v1")
    ANYTHINGLLM_API_KEY = os.getenv("ANYTHINGLLM_API_KEY")
    ANYTHINGLLM_WORKSPACE_SLUG = os.getenv("ANYTHINGLLM_WORKSPACE_SLUG")

    # Openrouter configuration
    OPENROUTER_API_KEY=os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_BASE_URL=os.getenv("OPENROUTER_BASE_URL")

class IPSettings:
    def __init__(self, target_ip=None):
        self.KALI_IP = os.getenv("KALI_IP")
        self.TARGET_IP = target_ip or os.getenv("TARGET_IP", os.getenv("METASPLOITABLE_IP"))


llm_settings = LLMSettings()
ip_settings = IPSettings()


KALI_IP = os.getenv("KALI_IP")
TESTER_NAME = os.getenv("TESTER_NAME")
