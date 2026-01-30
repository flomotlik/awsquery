"""Smart column selection algorithm for automatic field filtering."""

from typing import Dict, List, Optional

from .utils import debug_print

# Include float/double for numeric fields (Codex fix)
SIMPLE_TYPES = ("string", "boolean", "integer", "timestamp", "long", "float", "double")

WELL_KNOWN_NESTED_SCALARS = {
    "Endpoint": {"Address": "string", "Port": "integer"},
    "State": {"Name": "string", "Code": "string"},
    "Status": {"Code": "string", "Message": "string"},
}

TIER8_ALLOWLIST = frozenset(
    {
        "AllocatedStorage",
        "BackupRetentionPeriod",
        "DatabaseName",
        "Description",
        "MasterUsername",
        "OwnerAccount",
        "PreferredBackupWindow",
        "StorageType",
    }
)

# Tier exact-name lists per spec
TIER3_EXACT_NAMES = [
    "DBInstanceClass",
    "Engine",
    "EngineVersion",
    "InstanceType",
    "NodeType",
    "Runtime",
    "Type",
    "Version",
]

TIER4_EXACT_NAMES = [
    "Address",
    "AvailabilityZone",
    "DNSName",
    "Endpoint",
    "Port",
    "ReaderEndpoint",
    "SubnetId",
    "VpcId",
]

TIER5_EXACT_NAMES = [
    "CreationTime",
    "CreateTime",
    "CreatedTime",
    "CreateDate",
    "CreatedAt",
    "createdAt",
    "LaunchTime",
    "StartTime",
    "ClusterCreateTime",
    "SnapshotCreateTime",
]

TIER7_EXACT_NAMES = [
    "DeletionProtection",
    "Enabled",
    "Encrypted",
    "IsDefault",
    "MultiAZ",
    "PubliclyAccessible",
    "StorageEncrypted",
]


def flatten_well_known_scalars(fields: Dict[str, str]) -> Dict[str, str]:
    """Expand well-known nested scalars while avoiding duplicate paths.

    Only adds nested scalar paths when the parent is a structure type.
    If the parent is already a scalar, it's selected directly.
    """
    result = dict(fields)

    for parent_field, nested_fields in WELL_KNOWN_NESTED_SCALARS.items():
        parent_type = fields.get(parent_field)

        if parent_type is None:
            continue

        if parent_type in SIMPLE_TYPES:
            continue

        for child_name, child_type in nested_fields.items():
            nested_path = f"{parent_field}.{child_name}"
            if nested_path not in result:
                result[nested_path] = child_type

    return result


def _is_list_element_path(field: str) -> bool:
    """Check if field is a list element path like 'Items.0' or 'Tags.0.Key'."""
    parts = field.split(".")
    return any(part.isdigit() for part in parts)


def _get_base_name(field: str) -> str:
    """Extract base field name from dotted path."""
    return field.split(".")[-1]


def _get_path_depth(field: str) -> int:
    """Return the nesting depth of a field (number of dots)."""
    return field.count(".")


def _select_by_suffix_no_limit(
    candidates: List[str], suffixes: List[str], already_selected: set
) -> List[str]:
    """Select all fields matching suffixes with priority ordering (no limit)."""
    selected = []

    for suffix in suffixes:
        for field in sorted(candidates, key=lambda f: (_get_path_depth(f), f)):
            if field in already_selected or field in selected:
                continue
            base = _get_base_name(field)
            if base.endswith(suffix):
                selected.append(field)

    return selected


def _select_by_suffix(
    candidates: List[str], suffixes: List[str], limit: int, already_selected: set
) -> List[str]:
    """Select fields matching suffixes with priority ordering up to limit."""
    selected = []

    for suffix in suffixes:
        for field in sorted(candidates, key=lambda f: (_get_path_depth(f), f)):
            if field in already_selected or field in selected:
                continue
            base = _get_base_name(field)
            if base.endswith(suffix):
                selected.append(field)
                if len(selected) >= limit:
                    return selected

    return selected


def _select_exact_names(
    candidates: List[str], exact_names: List[str], limit: int, already_selected: set
) -> List[str]:
    """Select fields matching exact names up to limit."""
    selected = []

    for name in exact_names:
        for field in sorted(candidates, key=lambda f: (_get_path_depth(f), f)):
            if field in already_selected or field in selected:
                continue
            base = _get_base_name(field)
            if base == name:
                selected.append(field)
                if len(selected) >= limit:
                    return selected
                break

    return selected


def smart_select_columns(
    fields: Dict[str, str], max_columns: int = 6, operation: Optional[str] = None
) -> Optional[List[str]]:
    """Shape-aware column selection based on API operation and field analysis.

    Args:
        fields: Dict mapping field names to their types
        max_columns: Maximum columns to select (default 6)
        operation: Operation name (e.g., 'describe_db_instances') for context

    Returns columns selected by importance heuristic. Returns None if no eligible fields.
    """
    expanded = flatten_well_known_scalars(fields)

    # Filter to simple types and exclude list element paths (*.0)
    simple_fields = [
        f for f, t in expanded.items() if t in SIMPLE_TYPES and not _is_list_element_path(f)
    ]

    if not simple_fields:
        debug_print("No simple-type fields found, returning None for fallback")
        return None

    # Sort by depth first (prefer top-level), then alphabetically
    simple_fields.sort(key=lambda f: (_get_path_depth(f), f))

    selected: List[str] = []
    selected_set: set = set()

    def _add(field: str) -> bool:
        """Add field if not already selected. Returns True if max reached."""
        if field not in selected_set:
            selected.append(field)
            selected_set.add(field)
        return len(selected) >= max_columns

    # Extract resource type from operation name for primary identifier detection
    resource_type = None
    if operation:
        # describe_db_instances -> DBInstance, list_functions -> Function
        parts = operation.replace("-", "_").split("_")
        if len(parts) >= 2:
            # Skip verb (describe, list, get), join rest, singularize
            resource_parts = parts[1:]
            resource_type = "".join(p.capitalize() for p in resource_parts)
            if resource_type.endswith("s") and not resource_type.endswith("ss"):
                resource_type = resource_type[:-1]  # Simple singularize

    def _score_field(field: str) -> int:
        """Score field by importance (lower is better)."""
        base = _get_base_name(field)
        depth = _get_path_depth(field)
        score = depth * 100  # Penalize nested fields

        # Primary identifier - must match resource type (case-insensitive)
        if base.endswith("Identifier"):
            if resource_type and resource_type.lower() in base.lower():
                return score + 1  # Primary identifier for this resource
            return score + 50  # Reference to another resource

        # Status/State - very important
        if base in ("Status", "State"):
            return score + 5
        if base.endswith("Status") or base.endswith("State"):
            if resource_type and resource_type.lower() in base.lower():
                return score + 5  # Primary status for this resource
            return score + 15

        # Core type fields
        if base in ("Engine", "EngineVersion", "Type", "Version", "Runtime"):
            return score + 10
        if base in TIER3_EXACT_NAMES:
            return score + 11
        # Family/Group fields (e.g., DBParameterGroupFamily)
        if base.endswith("Family") or base.endswith("Group"):
            return score + 12
        # Major version fields
        if base.startswith("Major") and "Version" in base:
            return score + 13

        # Network/location
        if base in TIER4_EXACT_NAMES:
            return score + 20

        # Generic Id/Name (less specific, could be references)
        if base.endswith("Id") and not base.endswith("Identifier"):
            return score + 40
        if base.endswith("Name"):
            return score + 41

        # ARN
        if base.endswith("Arn") or base.endswith("ARN"):
            return score + 50

        # Booleans - exact matches
        if base in TIER7_EXACT_NAMES:
            return score + 60
        # Supports* booleans (e.g., SupportsReadReplica)
        if base.startswith("Supports"):
            return score + 62

        # Allowlist
        if base in TIER8_ALLOWLIST:
            return score + 70

        # Timestamps - often optional/empty, lower priority
        if base in TIER5_EXACT_NAMES:
            return score + 75

        # Description fields
        if "Description" in base:
            return score + 80

        # Everything else - low priority
        return score + 1000

    # Score and sort all fields
    scored = [(f, _score_field(f)) for f in simple_fields]
    scored.sort(key=lambda x: x[1])

    # Select top fields by score
    for field, score in scored:
        if _add(field):
            break

    return selected if selected else None
