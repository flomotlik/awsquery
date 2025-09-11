"""
Security policy validation for AWS Query Tool.

This module handles loading and validating AWS operations against security policies
to ensure only permitted read-only operations are executed.
"""

import json
import sys
import fnmatch
from .utils import debug_print


def load_security_policy():
    """Load and parse AWS ReadOnly policy from policy.json"""
    try:
        with open('policy.json', 'r') as f:
            policy = json.load(f)
        
        debug_print(f"DEBUG: Loaded policy with keys: {list(policy.keys())}")
        
        allowed_actions = set()
        
        # Handle nested PolicyVersion structure
        if 'PolicyVersion' in policy:
            debug_print(f"DEBUG: Found PolicyVersion structure")
            policy_doc = policy['PolicyVersion'].get('Document', {})
            statements = policy_doc.get('Statement', [])
        else:
            # Handle direct Statement structure
            statements = policy.get('Statement', [])
        
        debug_print(f"DEBUG: Found {len(statements)} statements in policy")
        
        for i, statement in enumerate(statements):
            effect = statement.get('Effect')
            actions = statement.get('Action', [])
            debug_print(f"DEBUG: Statement {i}: Effect={effect}, Actions count={len(actions) if isinstance(actions, list) else 1}")
            
            if effect == 'Allow':
                if isinstance(actions, str):
                    actions = [actions]
                allowed_actions.update(actions)
                debug_print(f"DEBUG: Added {len(actions)} actions from statement {i}")
        
        debug_print(f"DEBUG: Total allowed actions loaded: {len(allowed_actions)}")
        if len(allowed_actions) < 10:  # Show first few if small set
            debug_print(f"DEBUG: Sample actions: {list(allowed_actions)[:5]}")
        
        return allowed_actions
    except FileNotFoundError:
        print("ERROR: policy.json not found. This file is required for security validation.", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print("ERROR: Invalid JSON in policy.json. This file is required for security validation.", file=sys.stderr)
        sys.exit(1)


def validate_security(service, action, allowed_actions):
    """Validate service:action against security policy"""
    service_action = f"{service}:{action}"
    
    if not allowed_actions:
        debug_print(f"DEBUG: No allowed_actions provided, allowing {service_action} by default")
        return True
    
    debug_print(f"DEBUG: Validating {service_action} against {len(allowed_actions)} policy rules")
    
    # Direct match
    if service_action in allowed_actions:
        debug_print(f"DEBUG: Direct match found for {service_action}")
        return True
    
    # Wildcard match
    for allowed in allowed_actions:
        if fnmatch.fnmatch(service_action, allowed):
            debug_print(f"DEBUG: Wildcard match: {service_action} matches {allowed}")
            return True
    
    debug_print(f"DEBUG: No match found for {service_action}")
    return False


def action_to_policy_format(action):
    """Convert CLI-style action name to PascalCase format used in security policy"""
    # Convert kebab-case to PascalCase: "create-capacity-provider" -> "CreateCapacityProvider"
    # Convert snake_case to PascalCase: "create_capacity_provider" -> "CreateCapacityProvider"
    
    # First normalize to words separated by spaces
    words = action.replace('-', ' ').replace('_', ' ').split()
    
    # Capitalize each word and join
    pascal_case = ''.join(word.capitalize() for word in words)
    
    return pascal_case