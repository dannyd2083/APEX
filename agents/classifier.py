"""
Failure Classifier Module

Classifies failed attack chains as CORRECTABLE or FUNDAMENTAL
to determine whether to attempt remediation or skip to next chain.
"""

import json
import os
from typing import Dict, List, Tuple

# Load prompt template
def load_classifier_prompt() -> str:
    """Load the classifier prompt template."""
    prompt_path = os.path.join(os.path.dirname(__file__), 'prompts', 'classifier_prompt.txt')
    with open(prompt_path, 'r') as f:
        return f.read()


def classify_failures(
    failed_chain_context: List[Dict],
    target_ip: str,
    llm
) -> Tuple[List[Dict], List[Dict], Dict]:
    """
    Classify failed attack chains as CORRECTABLE or FUNDAMENTAL.

    Args:
        failed_chain_context: List of failed chain data with execution logs
        target_ip: The target IP address
        llm: The LLM instance to use for classification

    Returns:
        Tuple of (correctable_chains, fundamental_chains, raw_classification)
    """
    if not failed_chain_context:
        return [], [], {}

    # Load and prepare prompt
    prompt_template = load_classifier_prompt()
    prompt = (
        prompt_template
        .replace("__TARGET_IP__", target_ip)
        .replace("__FAILED_CHAINS__", json.dumps(failed_chain_context, indent=2))
    )

    # Call LLM for classification
    print("\n[CLASSIFIER] Analyzing failed chains...")
    response = llm._call(prompt)

    # Parse response
    classification_result = extract_classification_json(response)

    if not classification_result or 'classifications' not in classification_result:
        print("[CLASSIFIER] WARNING: Could not parse classification response. Treating all as CORRECTABLE.")
        return failed_chain_context, [], {}

    # Separate chains by classification
    correctable_chains = []
    fundamental_chains = []

    # Build lookup of original chain data
    chain_lookup = {chain['chain_name']: chain for chain in failed_chain_context}

    for item in classification_result.get('classifications', []):
        chain_name = item.get('chain_name')
        classification = item.get('classification', 'CORRECTABLE').upper()
        reasoning = item.get('reasoning', 'No reasoning provided')
        error_type = item.get('error_type', 'unknown')
        suggested_fix = item.get('suggested_fix')

        if chain_name not in chain_lookup:
            print(f"[CLASSIFIER] WARNING: Unknown chain '{chain_name}' in classification")
            continue

        chain_data = chain_lookup[chain_name]
        chain_data['classification'] = classification
        chain_data['classification_reasoning'] = reasoning
        chain_data['error_type'] = error_type
        if suggested_fix:
            chain_data['suggested_fix'] = suggested_fix

        if classification == 'FUNDAMENTAL':
            fundamental_chains.append(chain_data)
            print(f"[CLASSIFIER] {chain_name}: FUNDAMENTAL - {reasoning}")
        else:
            correctable_chains.append(chain_data)
            fix_msg = f" | Fix: {suggested_fix}" if suggested_fix else ""
            print(f"[CLASSIFIER] {chain_name}: CORRECTABLE - {reasoning}{fix_msg}")

    # Summary
    summary = classification_result.get('summary', {})
    print(f"\n[CLASSIFIER] Summary: {len(correctable_chains)} correctable, {len(fundamental_chains)} fundamental")

    return correctable_chains, fundamental_chains, classification_result


def extract_classification_json(response: str) -> Dict:
    """Extract JSON from LLM response."""
    import re

    # Try to parse directly first
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # Try to find JSON in code blocks
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find JSON object directly
    json_match = re.search(r'\{[\s\S]*\}', response)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    return {}
