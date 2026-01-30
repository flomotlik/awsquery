"""AWS service model shape introspection for response parsing and validation.

This module provides shape-aware response parsing using boto3's service model
introspection to validate filters and identify data fields before making API calls.
"""

from typing import Dict, Optional, Tuple

from botocore.loaders import Loader
from botocore.model import ServiceModel

from .case_utils import to_pascal_case
from .utils import debug_print, simplify_key


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

        data_field = self.identify_data_field(output_shape)
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

    def identify_data_field(self, shape) -> Optional[str]:
        """Identify the main data field (vs metadata fields).

        Args:
            shape: Botocore shape object

        Returns:
            Field name containing main data, or None if cannot determine
        """
        if not shape or not hasattr(shape, "members") or not shape.members:
            return None

        # Skip known metadata fields
        metadata_fields = {
            "ResponseMetadata",
            "NextMarker",
            "NextToken",
            "IsTruncated",
            "Marker",
            "HasMoreDeliveryStreams",
            "MaxResults",
        }
        data_fields = {k: v for k, v in shape.members.items() if k not in metadata_fields}

        # Look for list fields first (most common pattern)
        list_fields = [(k, v) for k, v in data_fields.items() if v.type_name == "list"]

        if len(list_fields) == 1:
            return str(list_fields[0][0])
        elif len(list_fields) > 1:
            # Multiple lists - return first
            return str(list_fields[0][0])
        elif len(data_fields) == 1:
            # Single non-list field
            return str(list(data_fields.keys())[0])

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
