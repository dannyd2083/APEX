import json
import os
from datetime import datetime
from agents.config.settings import project_root, TESTER_NAME
from langchain_core.messages import BaseMessage

RESULTS_FOLDER = "results"
ATTACK_CHAIN_FILE_NAME = "attack_chain_output"
EXECUTION_FILE_NAME = "execution_output"
REMEDIATION_FILE_NAME = "remediation_output"
EXECUTION_FIX_FILE_NAME = "execution_fix_output"

def load_attack_chain_json(file_path: str):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Attack chain JSON file not found: {file_path}")

    with open(file_path, "r") as f:
        try:
            data = json.load(f)
            return data
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse attack chain JSON: {e}")

def strip_markdown_code_blocks(text):
    """Strip markdown code blocks from text."""
    import re
    # Match ```json ... ``` or ``` ... ```
    pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
    match = re.search(pattern, text)
    if match:
        return match.group(1).strip()
    return text

def extract_json_from_llm_response(response):
    """
    Converts LLM output (which may be LangChain messages, Pydantic objects,
    or JSON-as-string) into clean, valid Python dict usable for JSON dumping.
    """
    # Case 1: LangChain message list
    if isinstance(response, list) and all(isinstance(x, BaseMessage) for x in response):
        for msg in response:
            if msg.__class__.__name__ == "AIMessage":
                try:
                    cleaned = strip_markdown_code_blocks(msg.content)
                    return json.loads(cleaned)
                except:
                    return {"raw_output": msg.content}
        return {"error": "No AIMessage in response"}

    # Case 2: Response is a BaseMessage
    if isinstance(response, BaseMessage):
        try:
            cleaned = strip_markdown_code_blocks(response.content)
            return json.loads(cleaned)
        except:
            return {"raw_output": response.content}

    # Case 3: Response is already a dict
    if isinstance(response, dict):
        return response

    # Case 4: Response is a JSON string
    if isinstance(response, str):
        try:
            cleaned = strip_markdown_code_blocks(response)
            return json.loads(cleaned)
        except:
            return {"raw_output": response}

    return {"raw_output": str(response)}

def make_json_safe(obj):
    """
    Recursively convert any object into JSON-serializable structures.
    """
    if isinstance(obj, BaseMessage):
        return {"type": obj.__class__.__name__, "content": obj.content}
    if isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [make_json_safe(v) for v in obj]
    if hasattr(obj, "dict"):
        return make_json_safe(obj.dict())
    if hasattr(obj, "__dict__"):
        return make_json_safe(obj.__dict__)
    try:
        json.dumps(obj)
        return obj
    except:
        return str(obj)

class SaveResults:
    FOLDER_PATH = project_root / RESULTS_FOLDER

    def __post_init__(self):
        self.FOLDER_PATH.mkdir(parents=True, exist_ok=True)
    
    def _get_file_by_type(self, type):
        if type == "ac":
            return ATTACK_CHAIN_FILE_NAME
        elif type == "exec":
            return EXECUTION_FILE_NAME
        elif type == "reval":
            return REMEDIATION_FILE_NAME
        elif type == "exec_fix":
            return EXECUTION_FIX_FILE_NAME
        return "unknown_output"

    def save_json_results(self, type: str, init_time: datetime, content: str):
        # Replace colons with dashes for Windows compatibility
        safe_time = str(init_time).replace(":", "-")
        filename = f"{self._get_file_by_type(type)}_{TESTER_NAME}_{safe_time}.json"
        full_file_path = self.FOLDER_PATH / filename

        safe_exec = make_json_safe(content)
        with open(full_file_path, 'w', encoding="utf-8") as json_file:
            json.dump(safe_exec, json_file, indent=4, ensure_ascii=False)

save_result = SaveResults()