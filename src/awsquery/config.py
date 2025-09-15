"""Configuration management for AWS Query Tool."""

import os
from functools import lru_cache

import yaml

from .utils import debug_print


@lru_cache(maxsize=1)
def load_default_filters():
    """Load default filters with caching and error handling"""
    # Load default_filters.yaml from the package directory only
    config_path = os.path.join(os.path.dirname(__file__), "default_filters.yaml")

    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
            debug_print(f"Loaded default filters configuration from {config_path}")
            return config
    except FileNotFoundError:
        debug_print(f"Warning: {config_path} not found, no defaults will be applied")
        return {}
    except yaml.YAMLError as e:
        debug_print(f"Warning: Could not parse {config_path}: {e}")
        return {}
    except Exception as e:
        debug_print(f"Warning: Could not load default filters from {config_path}: {e}")
        return {}


def get_default_columns(service, action):
    """Get default columns for service.action combination"""
    config = load_default_filters()

    service_config = config.get(service.lower(), {})
    action_config = service_config.get(action.lower(), {})

    columns = action_config.get("columns", [])
    if columns:
        debug_print(f"Found default columns for {service}.{action}: {columns}")
    else:
        debug_print(f"No default columns configured for {service}.{action}")

    return columns


def apply_default_filters(service, action, user_columns=None):
    """Apply default filters if no user columns specified"""
    if user_columns:
        debug_print("User specified columns, skipping defaults")
        return user_columns

    defaults = get_default_columns(service, action)
    if defaults:
        debug_print(f"Using default columns for {service}.{action}: {defaults}")
        return defaults

    debug_print(f"No default columns found for {service}.{action}")
    return None  # No filtering applied
