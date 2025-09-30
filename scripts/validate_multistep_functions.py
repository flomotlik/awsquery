#!/usr/bin/env python3
"""
Comprehensive multi-step function validation script.

Scans all AWS services and operations to identify scenarios where:
1. An operation has required parameters
2. Our infer_list_operation() logic suggests operations to call
3. Those suggested operations don't actually exist in the service

This helps identify broken multi-step scenarios that need fixing.
"""

import argparse
import json
import sys
import os
from typing import Dict, List, Any
from datetime import datetime

import boto3
import botocore.session
import yaml

# Import awsquery modules
sys.path.insert(0, 'src')
from awsquery.core import infer_list_operation
from awsquery.security import get_service_valid_operations, is_readonly_operation
from awsquery.utils import normalize_action_name


def to_pascal_case(snake_case: str) -> str:
    """Convert snake_case to PascalCase."""
    return ''.join(word.capitalize() for word in snake_case.split('_'))


def scan_service(service_name: str) -> Dict[str, List[Any]]:
    """Scan a single AWS service for multi-step scenarios.

    Returns:
        dict: {
            'broken': [...],      # Operations where inference fails
            'valid': [...],       # Operations where inference works
            'conditional': [...], # Operations with conditional requirements
            'no_required': [...]  # Operations with no required params
        }
    """
    results = {
        'broken': [],
        'valid': [],
        'conditional': [],
        'no_required': []
    }

    try:
        old_profile = os.environ.pop("AWS_PROFILE", None)
        try:
            session = botocore.session.Session()
            service_model = session.get_service_model(service_name)
            valid_operation_names = set(service_model.operation_names)
        finally:
            if old_profile:
                os.environ["AWS_PROFILE"] = old_profile

        for operation_name in service_model.operation_names:
            # FILTER: Skip non-readonly operations
            if not is_readonly_operation(operation_name):
                results['no_required'].append({
                    'service': service_name,
                    'operation': operation_name,
                    'reason': 'Not a readonly operation (skipped)'
                })
                continue

            try:
                operation_model = service_model.operation_model(operation_name)
                input_shape = operation_model.input_shape

                # Check if operation has input parameters
                if not input_shape or not hasattr(input_shape, 'required_members'):
                    results['no_required'].append({
                        'service': service_name,
                        'operation': operation_name,
                        'reason': 'No input shape or required members'
                    })
                    continue

                required_params = list(input_shape.required_members)

                # Check for conditional requirements
                doc = operation_model.documentation if hasattr(operation_model, 'documentation') else ''
                has_conditional = any(pattern in doc.lower() for pattern in [
                    'must specify either',
                    'at least one of',
                    'required if',
                ])

                if has_conditional:
                    results['conditional'].append({
                        'service': service_name,
                        'operation': operation_name,
                        'documentation_hint': doc[:200] + '...' if len(doc) > 200 else doc
                    })

                if not required_params:
                    results['no_required'].append({
                        'service': service_name,
                        'operation': operation_name,
                        'reason': 'No required parameters'
                    })
                    continue

                # Group all parameters for this operation
                param_results = {}
                all_valid_ops = set()

                for param_name in required_params:
                    # Infer what list operations we would try
                    inferred_ops = infer_list_operation(
                        service_name,
                        param_name,
                        operation_name,
                        session=None
                    )

                    # Check which inferred operations actually exist
                    valid_inferred = []
                    invalid_inferred = []

                    for op in inferred_ops:
                        pascal_op = to_pascal_case(op)
                        if pascal_op in valid_operation_names:
                            valid_inferred.append(op)
                            all_valid_ops.add(op)
                        else:
                            invalid_inferred.append(op)

                    param_results[param_name] = {
                        'inferred_operations': inferred_ops,
                        'valid_operations': valid_inferred,
                        'invalid_operations': invalid_inferred
                    }

                # Create single scenario entry for the operation
                scenario = {
                    'service': service_name,
                    'operation': operation_name,
                    'required_parameters': required_params,
                    'parameters': param_results,
                    'all_valid_operations': sorted(list(all_valid_ops))
                }

                if all_valid_ops:
                    # At least one parameter has valid operations - SUCCESS
                    results['valid'].append(scenario)
                else:
                    # No valid operations found for any parameter - BROKEN
                    results['broken'].append(scenario)

            except Exception as e:
                print(f"  Error processing {service_name}.{operation_name}: {e}", file=sys.stderr)
                continue

    except Exception as e:
        print(f"  Error processing service {service_name}: {e}", file=sys.stderr)

    return results


def generate_report(all_results: Dict[str, Any]) -> str:
    """Generate comprehensive JSON report."""

    # Calculate statistics
    total_services = len(all_results['services'])
    total_operations = sum(r['total_operations'] for r in all_results['services'].values())
    total_broken = sum(len(r['broken']) for r in all_results['services'].values())
    total_valid = sum(len(r['valid']) for r in all_results['services'].values())
    total_conditional = sum(len(r['conditional']) for r in all_results['services'].values())

    total_readonly_scanned = total_operations  # Operations we actually scanned
    total_non_readonly_skipped = sum(
        sum(1 for item in r.get('no_required_details', []) if isinstance(item, dict) and item.get('reason') == 'Not a readonly operation (skipped)')
        for r in all_results['services'].values()
    )

    success_rate = (total_valid / (total_valid + total_broken) * 100) if (total_valid + total_broken) > 0 else 0

    report = {
        'generated_at': all_results['generated_at'],
        'statistics': {
            'total_services_scanned': total_services,
            'total_operations_analyzed': total_operations,
            'readonly_operations_scanned': total_readonly_scanned,
            'non_readonly_operations_skipped': total_non_readonly_skipped,
            'readonly_filtering_enabled': True,
            'multi_step_scenarios': {
                'valid': total_valid,
                'broken': total_broken,
                'success_rate_percent': round(success_rate, 2)
            },
            'conditional_requirements_found': total_conditional
        },
        'services': all_results['services'],
        'summary': {
            'most_broken_services': _get_most_broken_services(all_results['services'], top=10),
            'most_problematic_params': _get_most_problematic_params(all_results['services'], top=10)
        }
    }

    return json.dumps(report, indent=2)


def _get_most_broken_services(services: Dict, top: int = 10) -> List[Dict]:
    """Get services with most broken scenarios."""
    service_counts = []
    for service_name, results in services.items():
        broken_count = len(results.get('broken', []))
        if broken_count > 0:
            service_counts.append({
                'service': service_name,
                'broken_count': broken_count
            })

    return sorted(service_counts, key=lambda x: x['broken_count'], reverse=True)[:top]


def _get_most_problematic_params(services: Dict, top: int = 10) -> List[Dict]:
    """Get parameter names that cause the most problems."""
    param_counts = {}

    for service_name, results in services.items():
        for scenario in results.get('broken', []):
            # NEW: scenario now contains all parameters, iterate through them
            param_details = scenario.get('parameters', {})
            for param, details in param_details.items():
                # Only count if this parameter has no valid operations
                if not details.get('valid_operations'):
                    if param not in param_counts:
                        param_counts[param] = {'param_name': param, 'count': 0, 'examples': []}

                    param_counts[param]['count'] += 1
                    if len(param_counts[param]['examples']) < 3:
                        param_counts[param]['examples'].append(f"{service_name}.{scenario['operation']}")

    return sorted(param_counts.values(), key=lambda x: x['count'], reverse=True)[:top]


def generate_markdown_report(all_results: Dict[str, Any],
                              include_valid: bool = False,
                              include_excluded: bool = False,
                              include_partial: bool = False) -> str:
    """Generate markdown report from validation results.

    By default, shows ONLY completely unsolvable operations (no valid functions for ANY parameter).
    This creates a minimal, actionable report for debugging.

    Args:
        all_results: Complete validation results
        include_valid: Include operations where ALL parameters can be resolved
        include_excluded: Include excluded (non-readonly) operations
        include_partial: Include operations with partial solutions (some params solvable, some not)

    Returns:
        Markdown formatted report as string
    """
    lines = []
    stats = all_results.get('statistics', {})

    lines.append("# AWS Multi-Step Function Validation Report")
    lines.append("")
    lines.append(f"**Generated:** {all_results.get('generated_at', 'N/A')}")
    lines.append(f"**ReadOnly Filtering:** {'Enabled' if stats.get('readonly_filtering_enabled') else 'Disabled'}")
    lines.append("")

    lines.append("## Summary Statistics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Services Scanned | {stats.get('total_services_scanned', 0)} |")
    lines.append(f"| Operations Analyzed | {stats.get('total_operations_analyzed', 0):,} |")
    lines.append(f"| ReadOnly Operations | {stats.get('readonly_operations_scanned', 0):,} |")
    lines.append(f"| Non-ReadOnly Skipped | {stats.get('non_readonly_operations_skipped', 0):,} |")

    multi_step = stats.get('multi_step_scenarios', {})
    valid_count = multi_step.get('valid', 0)
    broken_count = multi_step.get('broken', 0)
    success_rate = multi_step.get('success_rate_percent', 0)

    lines.append(f"| **Multi-Step Scenarios** | |")
    lines.append(f"| - Valid (working) | {valid_count:,} ({success_rate:.2f}%) |")
    lines.append(f"| - Broken (not working) | {broken_count:,} ({100-success_rate:.2f}%) |")
    lines.append(f"| Conditional Requirements | {stats.get('conditional_requirements_found', 0)} |")
    lines.append("")

    summary = all_results.get('summary', {})
    most_broken = summary.get('most_broken_services', [])
    if most_broken:
        lines.append("## Most Broken Services")
        lines.append("")
        lines.append("| Rank | Service | Broken Scenarios |")
        lines.append("|------|---------|------------------|")
        for i, item in enumerate(most_broken[:10], 1):
            lines.append(f"| {i} | `{item['service']}` | {item['broken_count']} |")
        lines.append("")

    most_problematic = summary.get('most_problematic_params', [])
    if most_problematic:
        lines.append("## Most Problematic Parameters")
        lines.append("")
        lines.append("| Rank | Parameter | Failed Scenarios | Example Services |")
        lines.append("|------|-----------|------------------|------------------|")
        for i, item in enumerate(most_problematic[:10], 1):
            examples = ', '.join(f"`{ex}`" for ex in item.get('examples', [])[:3])
            lines.append(f"| {i} | `{item['param_name']}` | {item['count']} | {examples} |")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Unsolvable Operations (Completely Broken)")
    lines.append("")
    lines.append("These operations have required parameters and NO valid list/get operations could be found for ANY parameter.")
    lines.append("These are the highest priority to fix - they cannot work with current multi-step inference.")
    lines.append("")

    # Separate completely unsolvable (no valid ops at all) from partial (some valid ops)
    services_with_unsolvable = {}
    services_with_partial = {}

    for svc, data in sorted(all_results['services'].items()):
        if not data.get('broken'):
            continue

        unsolvable = []
        partial = []

        for scenario in data['broken']:
            all_valid = scenario.get('all_valid_operations', [])
            if not all_valid:
                # No valid operations for ANY parameter - completely unsolvable
                unsolvable.append(scenario)
            else:
                # Has some valid operations but still marked broken - partial solution
                partial.append(scenario)

        if unsolvable:
            services_with_unsolvable[svc] = unsolvable
        if partial:
            services_with_partial[svc] = partial

    if services_with_unsolvable:
        lines.append("### Services with Unsolvable Operations")
        lines.append("")
        for service in sorted(services_with_unsolvable.keys()):
            count = len(services_with_unsolvable[service])
            lines.append(f"- [`{service}`](#{service.replace('-', '')}unsolvable) ({count} operations)")
        lines.append("")
        lines.append("---")
        lines.append("")

        for service in sorted(services_with_unsolvable.keys()):
            lines.append(f"### Service: `{service}`")
            lines.append("")

            for scenario in services_with_unsolvable[service]:
                op = scenario['operation']
                required_params = scenario.get('required_parameters', [])
                param_details = scenario.get('parameters', {})

                lines.append(f"#### `{op}`")
                lines.append(f"- **Required Parameters:** {', '.join(f'`{p}`' for p in required_params)}")

                # Show parameter-by-parameter breakdown
                for param, details in param_details.items():
                    inferred = details.get('inferred_operations', [])
                    valid = details.get('valid_operations', [])

                    if inferred:
                        lines.append(f"  - `{param}`: Tried {len(inferred)} operations → ✗ None exist")
                    else:
                        lines.append(f"  - `{param}`: ✗ No operations could be inferred")

                lines.append("")

            lines.append("")
    else:
        lines.append("*No completely unsolvable operations found!*")
        lines.append("")

    # Optionally show partial solutions
    if include_partial and services_with_partial:
        lines.append("---")
        lines.append("")
        lines.append("## Partially Solvable Operations")
        lines.append("")
        lines.append("These operations have some parameters that can be resolved, but not all.")
        lines.append("")

        for service in sorted(services_with_partial.keys()):
            lines.append(f"### Service: `{service}`")
            lines.append("")

            for scenario in services_with_partial[service]:
                op = scenario['operation']
                required_params = scenario.get('required_parameters', [])
                param_details = scenario.get('parameters', {})
                all_valid = scenario.get('all_valid_operations', [])

                lines.append(f"#### `{op}`")
                lines.append(f"- **Required Parameters:** {', '.join(f'`{p}`' for p in required_params)}")
                lines.append(f"- **Partially Solvable:** Can resolve via {', '.join(f'`{op}`' for op in all_valid)}")

                # Show which params are solvable and which aren't
                for param, details in param_details.items():
                    valid = details.get('valid_operations', [])
                    if valid:
                        lines.append(f"  - `{param}`: ✓ {', '.join(f'`{op}`' for op in valid)}")
                    else:
                        lines.append(f"  - `{param}`: ✗ No solution")

                lines.append("")

            lines.append("")

    if include_valid:
        lines.append("---")
        lines.append("")
        lines.append("## Valid Multi-Step Scenarios")
        lines.append("")
        lines.append("These operations have required parameters AND valid list/get operations were found.")
        lines.append("These scenarios work correctly with awsquery's multi-step inference.")
        lines.append("")

        services_with_valid = [(svc, data) for svc, data in sorted(all_results['services'].items())
                               if data.get('valid')]

        if services_with_valid:
            for service, data in services_with_valid:
                if not data['valid']:
                    continue

                lines.append(f"### Service: `{service}`")
                lines.append("")

                for scenario in data['valid']:
                    op = scenario['operation']
                    required_params = scenario.get('required_parameters', [])
                    param_details = scenario.get('parameters', {})
                    all_valid_ops = scenario.get('all_valid_operations', [])

                    lines.append(f"#### `{op}`")
                    lines.append(f"- **Required Parameters:** {', '.join(f'`{p}`' for p in required_params)}")
                    lines.append(f"- **All Valid Operations:** {', '.join(f'`{op}`' for op in all_valid_ops)}")

                    # Show parameter-by-parameter breakdown
                    for param, details in param_details.items():
                        valid = details.get('valid_operations', [])
                        if valid:
                            lines.append(f"  - `{param}` → {', '.join(f'`{op}`' for op in valid)}")
                    lines.append(f"- **Status:** Working")
                    lines.append("")

                lines.append("")
        else:
            lines.append("*No valid scenarios found.*")
            lines.append("")

    if include_excluded:
        lines.append("---")
        lines.append("")
        lines.append("## Excluded Operations (Non-ReadOnly)")
        lines.append("")
        lines.append("These operations were skipped because they are not readonly operations.")
        lines.append("awsquery only validates readonly operations for security reasons.")
        lines.append("")

        for service, data in sorted(all_results['services'].items()):
            excluded = [item for item in data.get('no_required_details', [])
                        if isinstance(item, dict) and
                        item.get('reason') == 'Not a readonly operation (skipped)']

            if excluded:
                lines.append(f"### Service: `{service}`")
                lines.append("")
                lines.append("| Operation | Reason |")
                lines.append("|-----------|--------|")
                for item in excluded:
                    lines.append(f"| `{item['operation']}` | {item['reason']} |")
                lines.append("")

    return "\n".join(lines)


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description='Validate multi-step function inference across AWS services (ReadOnly operations only)'
    )
    parser.add_argument(
        '--output-format',
        choices=['json', 'yaml', 'markdown', 'all'],
        default='all',
        help='Output format for the report (default: all - generates JSON, YAML, and minimal markdown)'
    )
    parser.add_argument(
        '--include-valid',
        action='store_true',
        help='[Markdown only] Include operations where valid functions were found'
    )
    parser.add_argument(
        '--include-excluded',
        action='store_true',
        help='[Markdown only] Include excluded non-readonly operations'
    )
    parser.add_argument(
        '--include-partial',
        action='store_true',
        help='[Markdown only] Include operations with partial solutions (some params can be resolved)'
    )
    parser.add_argument(
        '--full-report',
        action='store_true',
        help='[Markdown only] Include all sections (equivalent to --include-valid --include-excluded --include-partial)'
    )

    args = parser.parse_args()

    if args.full_report:
        args.include_valid = True
        args.include_excluded = True
        args.include_partial = True

    print("=" * 80)
    print("AWS Multi-Step Function Validation (ReadOnly Operations Only)")
    print("=" * 80)
    print()

    old_profile = os.environ.pop("AWS_PROFILE", None)
    try:
        session = botocore.session.Session()
        all_services = session.get_available_services()
    finally:
        if old_profile:
            os.environ["AWS_PROFILE"] = old_profile

    print(f"Scanning {len(all_services)} AWS services (readonly operations only)...")
    print()

    all_results = {
        'generated_at': datetime.utcnow().isoformat(),
        'services': {}
    }

    # Scan each service
    for i, service_name in enumerate(sorted(all_services), 1):
        print(f"[{i}/{len(all_services)}] Scanning {service_name}...", end='', flush=True)

        results = scan_service(service_name)

        total_ops = len(results['broken']) + len(results['valid']) + len(results['no_required'])
        print(f" {total_ops} operations analyzed", flush=True)

        all_results['services'][service_name] = {
            'total_operations': total_ops,
            'broken': results['broken'],
            'valid': results['valid'],
            'conditional': results['conditional'],
            'no_required': len(results['no_required']),
            'no_required_details': results['no_required']  # Store details for statistics
        }

    print()
    print("=" * 80)
    print("Generating report...")
    print("=" * 80)

    report_json = generate_report(all_results)
    report = json.loads(report_json)

    # Generate JSON output
    if args.output_format in ['json', 'all']:
        output_file = 'multistep-validation-report.json'
        with open(output_file, 'w') as f:
            f.write(report_json)
        print(f"JSON report saved to: {output_file}")

    # Generate YAML output
    if args.output_format in ['yaml', 'all']:
        output_file_yaml = 'multistep-validation-report.yaml'
        with open(output_file_yaml, 'w') as f:
            yaml.dump(report, f, default_flow_style=False, sort_keys=False)
        print(f"YAML report saved to: {output_file_yaml}")

    # Generate minimal Markdown output (by default, only unsolvable operations)
    if args.output_format in ['markdown', 'all']:
        report_md = generate_markdown_report(
            report,
            include_valid=args.include_valid,
            include_excluded=args.include_excluded,
            include_partial=args.include_partial
        )

        output_file_md = 'multistep-validation-report.md'
        with open(output_file_md, 'w') as f:
            f.write(report_md)
        print(f"Markdown report saved to: {output_file_md}")

    stats = report['statistics']

    print()
    print("Summary:")
    print(f"  Services scanned: {stats['total_services_scanned']}")
    print(f"  Operations analyzed: {stats['total_operations_analyzed']}")
    print(f"  ReadOnly operations scanned: {stats.get('readonly_operations_scanned', 'N/A')}")
    print(f"  Non-readonly operations skipped: {stats.get('non_readonly_operations_skipped', 'N/A')}")
    print(f"  Multi-step scenarios:")
    print(f"    Valid: {stats['multi_step_scenarios']['valid']}")
    print(f"    Broken: {stats['multi_step_scenarios']['broken']}")
    print(f"    Success rate: {stats['multi_step_scenarios']['success_rate_percent']}%")
    print(f"  Conditional requirements found: {stats['conditional_requirements_found']}")
    print()

    if report['summary']['most_broken_services']:
        print("Most broken services:")
        for item in report['summary']['most_broken_services'][:5]:
            print(f"  {item['service']:20} {item['broken_count']} broken scenarios")

    print()
    print("=" * 80)
    print()
    print("Reports generated:")
    if args.output_format in ['json', 'all']:
        print("  - multistep-validation-report.json (full data)")
    if args.output_format in ['yaml', 'all']:
        print("  - multistep-validation-report.yaml (full data)")
    if args.output_format in ['markdown', 'all']:
        sections = ["unsolvable operations only (minimal)"]
        if args.include_partial:
            sections.append("partial solutions")
        if args.include_valid:
            sections.append("valid scenarios")
        if args.include_excluded:
            sections.append("excluded operations")
        print(f"  - multistep-validation-report.md ({', '.join(sections)})")
    print()
    print("=" * 80)


if __name__ == '__main__':
    main()