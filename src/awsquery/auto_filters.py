"""Smart column selection algorithm for automatic field filtering."""

from typing import Dict, List, Optional

from .utils import debug_print

# Include float/double for numeric fields (Codex fix)
SIMPLE_TYPES = ('string', 'boolean', 'integer', 'timestamp', 'long', 'float', 'double')

WELL_KNOWN_NESTED_SCALARS = {
    'Endpoint': {'Address': 'string', 'Port': 'integer'},
    'State': {'Name': 'string', 'Code': 'string'},
    'Status': {'Code': 'string', 'Message': 'string'},
}

TIER8_ALLOWLIST = frozenset({
    'AllocatedStorage',
    'BackupRetentionPeriod',
    'DatabaseName',
    'Description',
    'MasterUsername',
    'OwnerAccount',
    'PreferredBackupWindow',
    'StorageType',
})

# Tier exact-name lists per spec
TIER3_EXACT_NAMES = [
    'DBInstanceClass', 'Engine', 'EngineVersion', 'InstanceType',
    'NodeType', 'Runtime', 'Type', 'Version'
]

TIER4_EXACT_NAMES = [
    'Address', 'AvailabilityZone', 'DNSName', 'Endpoint', 'Port',
    'ReaderEndpoint', 'SubnetId', 'VpcId'
]

TIER5_EXACT_NAMES = [
    'CreationTime', 'CreateTime', 'CreatedTime', 'CreateDate', 'CreatedAt',
    'createdAt', 'LaunchTime', 'StartTime', 'ClusterCreateTime', 'SnapshotCreateTime'
]

TIER7_EXACT_NAMES = [
    'DeletionProtection', 'Enabled', 'Encrypted', 'IsDefault',
    'MultiAZ', 'PubliclyAccessible', 'StorageEncrypted'
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
    parts = field.split('.')
    return any(part.isdigit() for part in parts)


def _get_base_name(field: str) -> str:
    """Extract base field name from dotted path."""
    return field.split('.')[-1]


def _select_by_suffix_no_limit(
    candidates: List[str],
    suffixes: List[str],
    already_selected: set
) -> List[str]:
    """Select all fields matching suffixes with priority ordering (no limit)."""
    selected = []

    for suffix in suffixes:
        for field in sorted(candidates):
            if field in already_selected or field in selected:
                continue
            base = _get_base_name(field)
            if base.endswith(suffix):
                selected.append(field)

    return selected


def _select_by_suffix(
    candidates: List[str],
    suffixes: List[str],
    limit: int,
    already_selected: set
) -> List[str]:
    """Select fields matching suffixes with priority ordering up to limit."""
    selected = []

    for suffix in suffixes:
        for field in sorted(candidates):
            if field in already_selected or field in selected:
                continue
            base = _get_base_name(field)
            if base.endswith(suffix):
                selected.append(field)
                if len(selected) >= limit:
                    return selected

    return selected


def _select_exact_names(
    candidates: List[str],
    exact_names: List[str],
    limit: int,
    already_selected: set
) -> List[str]:
    """Select fields matching exact names up to limit."""
    selected = []

    for name in exact_names:
        for field in sorted(candidates):
            if field in already_selected or field in selected:
                continue
            base = _get_base_name(field)
            if base == name:
                selected.append(field)
                if len(selected) >= limit:
                    return selected
                break

    return selected


def smart_select_columns(fields: Dict[str, str], max_columns: int = 10) -> Optional[List[str]]:
    """Select columns using 8-tier heuristic algorithm.

    Returns columns in tier order (not alphabetically sorted) to preserve
    tier priority. Returns None if no eligible fields found.
    """
    expanded = flatten_well_known_scalars(fields)

    # Filter to simple types and exclude list element paths (*.0)
    simple_fields = [
        f for f, t in expanded.items()
        if t in SIMPLE_TYPES and not _is_list_element_path(f)
    ]

    if not simple_fields:
        debug_print("No simple-type fields found, returning None for fallback")
        return None

    selected: List[str] = []

    def _add_to_selected(tier_fields: List[str]) -> bool:
        """Add fields to selected, return True if max reached."""
        for f in tier_fields:
            if f not in selected:
                selected.append(f)
                if len(selected) >= max_columns:
                    return True
        return False

    # TIER 1: Primary identifiers (*Identifier > *Id > *Name) - NO LIMIT within tier
    tier1 = _select_by_suffix_no_limit(
        simple_fields,
        ['Identifier', 'Id', 'Name'],
        already_selected=set(selected)
    )
    if _add_to_selected(tier1):
        return selected[:max_columns]

    # TIER 2: Status/State - exact matches first, then suffix, TOTAL LIMIT 2
    tier2_exact = _select_exact_names(
        simple_fields,
        ['Status', 'State'],
        limit=2,
        already_selected=set(selected)
    )
    tier2_suffix = []
    remaining_tier2 = 2 - len(tier2_exact)
    if remaining_tier2 > 0:
        tier2_suffix = _select_by_suffix(
            simple_fields,
            ['Status', 'State'],
            limit=remaining_tier2,
            already_selected=set(selected) | set(tier2_exact)
        )
    if _add_to_selected(tier2_exact + tier2_suffix):
        return selected[:max_columns]

    # TIER 3: Type/Classification - exact names, then suffix, limit 2 suffix
    tier3_exact = _select_exact_names(
        simple_fields,
        TIER3_EXACT_NAMES,
        limit=max_columns - len(selected),
        already_selected=set(selected)
    )
    if _add_to_selected(tier3_exact):
        return selected[:max_columns]

    tier3_suffix = _select_by_suffix(
        simple_fields,
        ['Class', 'Mode', 'Type', 'Version'],
        limit=2,
        already_selected=set(selected)
    )
    if _add_to_selected(tier3_suffix):
        return selected[:max_columns]

    # TIER 4: Network/Location - exact names, limit 3
    tier4 = _select_exact_names(
        simple_fields,
        TIER4_EXACT_NAMES,
        limit=3,
        already_selected=set(selected)
    )
    if _add_to_selected(tier4):
        return selected[:max_columns]

    # TIER 5: Timestamps - exact names, limit 1
    tier5 = _select_exact_names(
        simple_fields,
        TIER5_EXACT_NAMES,
        limit=1,
        already_selected=set(selected)
    )
    if _add_to_selected(tier5):
        return selected[:max_columns]

    # TIER 6: ARN - suffix match, limit 1
    tier6 = _select_by_suffix(
        simple_fields,
        ['Arn', 'ARN'],
        limit=1,
        already_selected=set(selected)
    )
    if _add_to_selected(tier6):
        return selected[:max_columns]

    # TIER 7: Boolean flags - exact names, limit 2
    tier7 = _select_exact_names(
        simple_fields,
        TIER7_EXACT_NAMES,
        limit=2,
        already_selected=set(selected)
    )
    if _add_to_selected(tier7):
        return selected[:max_columns]

    # TIER 8: Allowlist only - fill to max
    for field in sorted(simple_fields):
        if field in selected:
            continue
        base = _get_base_name(field)
        if base in TIER8_ALLOWLIST:
            selected.append(field)
            if len(selected) >= max_columns:
                break

    # Return in tier order (not sorted) - this preserves tier priority
    return selected[:max_columns] if selected else None
