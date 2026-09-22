"""AWS service model shape introspection for response parsing and validation.

This module provides shape-aware response parsing using boto3's service model
introspection to validate filters and identify data fields before making API calls.
"""

import re
from typing import Dict, List, Optional, Tuple

from botocore.loaders import Loader
from botocore.model import ServiceModel

from .case_utils import to_pascal_case
from .config import get_data_field_override
from .utils import debug_print, simplify_key

# Response members that carry pagination or protocol state, never resource data.
METADATA_FIELDS = frozenset(
    {
        "ResponseMetadata",
        "NextMarker",
        "NextToken",
        "IsTruncated",
        "Marker",
        "HasMoreDeliveryStreams",
        "MaxResults",
    }
)

# Verbs AWS puts in front of the noun an operation acts on.
_OPERATION_VERBS = (
    "BatchDescribe",
    "BatchGet",
    "Describe",
    "Estimate",
    "Generate",
    "Lookup",
    "Retrieve",
    "Search",
    "Simulate",
    "Preview",
    "Query",
    "Scan",
    "List",
    "Get",
)

# Verbs that promise a collection whatever the noun looks like (ListObjectsV2 -> Contents).
_COLLECTION_VERBS = ("List", "Search", "Scan", "Query", "Lookup")

_WORD_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_VERSION_SUFFIX = re.compile(r"V\d+$")


def _split_verb(operation: str) -> Tuple[str, str]:
    """Split an operation name into its leading verb and the noun it acts on.

    A bare verb (dynamodb Scan, kendra Query) leaves no noun.
    """
    for verb in _OPERATION_VERBS:
        if operation.startswith(verb):
            return verb, operation[len(verb) :]
    return "", operation


def _singularize(word: str) -> str:
    """Crude English singular, enough to line up member names with operation nouns."""
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("ses", "xes", "zes", "ches", "shes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us", "sis")):
        return word[:-1]
    return word


def _words(name: str) -> List[str]:
    """Split a camel/pascal name into lowercase words, with the last one singularized."""
    words = [w.lower() for w in _WORD_BOUNDARY.split(_VERSION_SUFFIX.sub("", name)) if w]
    if words:
        words[-1] = _singularize(words[-1])
    return words


def _is_plural(word: str) -> bool:
    """True when the trailing noun reads as a plural (Stacks, Policies, Addresses)."""
    words = [w.lower() for w in _WORD_BOUNDARY.split(_VERSION_SUFFIX.sub("", word)) if w]
    return bool(words) and _singularize(words[-1]) != words[-1]


def _prefer_structures(shape, members: List[str]) -> str:
    """Pick the sibling list that holds structures.

    A bare list of names or ids next to a list of structures is an index of that same
    data: kinesis ListStreams returns StreamNames and StreamSummaries, and only the
    summaries carry fields to render.
    """
    structured = [m for m in members if shape.members[m].member.type_name == "structure"]
    return (structured or members)[0]


def _names_the_same_thing(noun: str, member: str) -> bool:
    """True when a list member name refers to the noun the operation is named after.

    Matching is by trailing words, so ListBuckets/Buckets and DescribeDimensionKeys/Keys
    line up while GetType/directParentTypes does not: a member that merely ends in a
    one-word noun describes something else the object points at.
    """
    op_words, member_words = _words(noun), _words(member)
    if not op_words or not member_words:
        return False
    if op_words == member_words:
        return True
    if len(member_words) < len(op_words):
        return op_words[-len(member_words) :] == member_words
    return len(op_words) > 1 and member_words[-len(op_words) :] == op_words


class ShapeCache:
    """Cache AWS service model shapes for performance and response introspection."""

    def __init__(self):
        """Initialize shape cache with empty cache and botocore loader."""
        self._cache: Dict[str, ServiceModel] = {}
        self._loader = Loader()

    def get_service_model(self, service: str) -> Optional[ServiceModel]:
        """Load service model with caching.

        Args:
            service: AWS service name (e.g., 'ec2', 's3')

        Returns:
            ServiceModel instance or None if loading fails
        """
        if service not in self._cache:
            try:
                # Use LATEST API version, not oldest - critical for accuracy
                api_versions = self._loader.list_api_versions(service, "service-2")
                if not api_versions:
                    debug_print(f"No API versions found for service '{service}'")
                    return None

                api_version = api_versions[-1]  # Use LATEST version
                debug_print(f"Loading service model for {service} with API version {api_version}")
                service_data = self._loader.load_service_model(service, "service-2", api_version)
                self._cache[service] = ServiceModel(service_data)
            except Exception as e:
                debug_print(f"Could not load service model for '{service}': {e}")
                return None

        return self._cache[service]

    def get_operation_shape(self, service: str, operation: str):
        """Get output shape for an operation.

        Args:
            service: AWS service name
            operation: Operation name (kebab-case or snake_case)

        Returns:
            Operation output shape or None if not found
        """
        service_model = self.get_service_model(service)
        if not service_model:
            return None

        # Convert to PascalCase using case_utils
        pascal_operation = to_pascal_case(operation)

        try:
            operation_model = service_model.operation_model(pascal_operation)
            return operation_model.output_shape
        except Exception:
            # Case-insensitive fallback for AWS acronyms (SAML, MFA, DB, etc.)
            # case_utils doesn't preserve these, so we need fuzzy matching
            pascal_lower = pascal_operation.lower()
            for op_name in service_model.operation_names:
                if op_name.lower() == pascal_lower:
                    try:
                        operation_model = service_model.operation_model(op_name)
                        debug_print(f"Found operation via case-insensitive match: {op_name}")
                        return operation_model.output_shape
                    except Exception:
                        pass

            debug_print(
                f"Could not get operation model for {service}:{operation} ({pascal_operation})"
            )
            return None

    def get_response_fields(
        self, service: str, operation: str
    ) -> Tuple[Optional[str], Dict[str, str], Dict[str, str]]:
        """Get available fields for an operation.

        Returns:
            Tuple of (data_field, simplified_fields, full_fields)
            - data_field: Main data field name (vs metadata)
            - simplified_fields: Field names as they appear after flattening (what filters match)
            - full_fields: Complete field paths with structure
        """
        output_shape = self.get_operation_shape(service, operation)
        if not output_shape:
            return None, {}, {}

        data_field = self.identify_data_field(output_shape, service, operation)
        all_fields = self._flatten_shape(output_shape)

        # Adjust paths if there's a data field that gets extracted
        if data_field and data_field in all_fields:
            adjusted_fields = {}
            prefix = f"{data_field}."
            data_field_type = all_fields[data_field]

            for field_path, field_type in all_fields.items():
                if field_path.startswith(prefix):
                    # Remove data field prefix since it's extracted during processing
                    adjusted_fields[field_path[len(prefix) :]] = field_type
                elif field_path == data_field:
                    # This is the data field itself
                    if data_field_type == "list":
                        # Simple list - might be returned as is
                        adjusted_fields["value"] = "list"
                    elif data_field_type == "map":
                        # Map type - keys are dynamic, accept any field name for validation
                        adjusted_fields["*"] = "map-wildcard"
                    elif data_field_type in ("string", "integer", "boolean", "timestamp"):
                        # Primitive type - keep the field name available
                        adjusted_fields[data_field] = data_field_type
                    else:
                        # Other type - keep as is
                        adjusted_fields[data_field] = data_field_type
                else:
                    # Metadata field - usually filtered out
                    adjusted_fields[field_path] = field_type

            # Create simplified keys map (what filters actually match against)
            simplified_fields = {}
            for full_key, field_type in adjusted_fields.items():
                simple_key = simplify_key(full_key)
                if simple_key not in simplified_fields:
                    simplified_fields[simple_key] = field_type

            return data_field, simplified_fields, adjusted_fields

        # Create simplified keys for non-extracted case
        simplified_fields = {}
        for full_key, field_type in all_fields.items():
            simple_key = simplify_key(full_key)
            if simple_key not in simplified_fields:
                simplified_fields[simple_key] = field_type

        return data_field, simplified_fields, all_fields

    def identify_data_field(self, shape, service: str, operation: str) -> Optional[str]:
        """Identify the member holding the resources, or None when the response is one object.

        A list member only holds "the resources" when the response *is* a collection.
        A response that is a single object (GetFunctionConfiguration) merely *contains*
        lists, and picking one of them throws the object's own fields away. The operation
        name decides: a list named after the operation noun is the collection
        (ListBuckets -> Buckets), and so is any list under a collection verb or a plural
        noun (ListObjectsV2 -> Contents, DescribeInstances -> Reservations).

        Operations whose object is only a wrapper around one collection are indistinguishable
        in the service model, so data_fields.yaml names them.

        Args:
            shape: Botocore shape object
            service: AWS service name, for the data_fields.yaml lookup
            operation: Operation name - the shape alone cannot tell a collection from an
                object, so this is required

        Returns:
            Field name containing main data, or None if the response is a single object
        """
        if not shape or not hasattr(shape, "members") or not shape.members:
            return None

        override = get_data_field_override(service, operation)
        if override:
            if override in shape.members:
                return str(override)
            debug_print(
                f"data_fields.yaml names '{override}' for {service}:{operation}, "
                f"which the service model no longer has - falling back to the shape"
            )  # pragma: no mutate

        data_fields = {k: v for k, v in shape.members.items() if k not in METADATA_FIELDS}
        list_fields: List[str] = [k for k, v in data_fields.items() if v.type_name == "list"]

        if not list_fields:
            # Single non-list field is the payload; several mean the response is the object.
            return str(next(iter(data_fields))) if len(data_fields) == 1 else None

        if len(data_fields) == 1:
            # Nothing but the list, so there is no object to lose.
            return list_fields[0]

        verb, noun = _split_verb(to_pascal_case(operation))

        named = [m for m in list_fields if _names_the_same_thing(noun, m)]
        if named:
            return _prefer_structures(shape, named)

        if verb in _COLLECTION_VERBS or _is_plural(noun):
            return _prefer_structures(shape, list_fields)

        # A single object that happens to carry child collections.
        debug_print(f"{operation}: response is a single object, keeping its own fields")
        return None

    def _flatten_shape(
        self, shape, prefix: str = "", max_depth: int = 5, current_depth: int = 0
    ) -> Dict[str, str]:
        """Recursively flatten shape structure to field paths with types.

        Uses awsquery's actual flattening format:
        - Lists use numeric indices: Roles.0.RoleId
        - Maps become dynamic key-value pairs

        Args:
            shape: Botocore shape object
            prefix: Current field path prefix
            max_depth: Maximum nesting depth
            current_depth: Current depth in recursion

        Returns:
            Dict mapping field paths to type names
        """
        fields: Dict[str, str] = {}

        if current_depth > max_depth:
            return fields

        if not shape:
            return fields

        if shape.type_name == "structure":
            for member_name, member_shape in shape.members.items():
                field_path = f"{prefix}.{member_name}" if prefix else member_name
                fields[field_path] = member_shape.type_name

                if member_shape.type_name == "structure":
                    # Recurse into nested structures
                    nested = self._flatten_shape(
                        member_shape, field_path, max_depth, current_depth + 1
                    )
                    fields.update(nested)
                elif (
                    member_shape.type_name == "list"
                    and hasattr(member_shape, "member")
                    and member_shape.member
                ):
                    # For lists, show what's inside using numeric index (awsquery format)
                    if member_shape.member.type_name == "structure":
                        # List of structures - use .0 to show first item fields
                        nested = self._flatten_shape(
                            member_shape.member,
                            f"{field_path}.0",
                            max_depth,
                            current_depth + 1,
                        )
                        fields.update(nested)
                    else:
                        # List of primitives - use .0 notation
                        fields[f"{field_path}.0"] = member_shape.member.type_name
                elif member_shape.type_name == "map" and hasattr(member_shape, "value"):
                    # Maps (dict) - mark as map so we know column filters can match any key
                    fields[field_path] = "map"

        return fields

    def get_fields_for_auto_select(self, service: str, operation: str) -> Dict[str, str]:
        """Get fields in format suitable for auto_filters.smart_select_columns().

        Returns dict mapping field names to their types, needed for type-based
        deduplication of nested scalars.
        """
        _, simplified_fields, _ = self.get_response_fields(service, operation)
        return simplified_fields


# One parsed service model per process: the JSON is multi-megabyte for large
# services, and the query path would otherwise parse it once per call site.
_shared_cache: Optional[ShapeCache] = None


def get_shape_cache() -> ShapeCache:
    """The process-wide ShapeCache. Build ShapeCache() directly for an isolated one."""
    global _shared_cache  # pylint: disable=global-statement
    if _shared_cache is None:
        _shared_cache = ShapeCache()
    return _shared_cache


def reset_shape_cache() -> None:
    """Drop the shared cache so nothing leaks between tests."""
    global _shared_cache  # pylint: disable=global-statement
    _shared_cache = None
