"""Guards against drift between the packaged agent reference and the real CLI."""

import argparse
import json
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from awsquery.cli import OUTPUT_FORMATS, main
from awsquery.errors import ExitCode
from awsquery.introspection import build_schema

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_PATH = REPO_ROOT / "src" / "awsquery" / "agent-reference.md"
MIRROR_PATH = REPO_ROOT / "llms-full.txt"

BACKTICKED = re.compile(r"`([^`]+)`")


class _ParserCaptured(Exception):
    pass


def cli_parser():
    """Return the parser main() builds; main() exposes no parser factory."""
    captured = {}

    def capture(self, args=None, namespace=None):
        captured["parser"] = self
        raise _ParserCaptured

    original_argv = sys.argv
    sys.argv = ["awsquery"]
    try:
        with patch.object(argparse.ArgumentParser, "parse_known_args", capture):
            with pytest.raises(_ParserCaptured):
                main()
    finally:
        sys.argv = original_argv
    return captured["parser"]


def documented_flag_rows():
    text = REFERENCE_PATH.read_text(encoding="utf-8")
    section = text.split("## Flags", 1)[1].split("\n## ", 1)[0]
    return [
        (line.split("|")[1].strip(), line.split("|")[2].strip())
        for line in section.splitlines()
        if line.startswith("| `")  # table rows only, not the header or separator
    ]


def documented_flag_cells():
    return [flag_cell for flag_cell, _ in documented_flag_rows()]


def documented_long_flags():
    flags = []
    for cell in documented_flag_cells():
        for token in BACKTICKED.findall(cell):
            # Cells carry the metavar too ("--parameter K=V"); the flag is the first word
            name = token.split()[0]
            if name.startswith("--"):
                flags.append(name)
    return flags


def documented_exit_codes():
    text = REFERENCE_PATH.read_text(encoding="utf-8")
    section = text.split("| Code | Meaning |", 1)[1].split("\n## ", 1)[0]
    return [
        int(line.split("|")[1].strip())
        for line in section.splitlines()
        if re.match(r"^\| \d+ \|", line)
    ]


class TestLlmsMirror:

    def test_mirror_is_byte_identical_to_packaged_reference(self):
        assert MIRROR_PATH.read_bytes() == REFERENCE_PATH.read_bytes()

    def test_mirror_is_not_empty(self):
        assert MIRROR_PATH.read_bytes().startswith(b"# awsquery")


class TestDocumentedFlags:

    def test_flags_table_was_extracted(self):
        flags = documented_long_flags()

        assert "--format" in flags
        assert "--limit" in flags
        assert len(flags) >= 10

    def test_every_documented_long_flag_exists_in_the_parser(self):
        parser_flags = {
            option
            for action in cli_parser()._actions
            for option in action.option_strings
            if option.startswith("--")
        }

        missing = sorted(set(documented_long_flags()) - parser_flags)
        assert missing == []

    def test_every_parser_long_flag_is_documented(self):
        parser_flags = {
            option
            for action in cli_parser()._actions
            for option in action.option_strings
            if option.startswith("--") and option != "--help"
        }

        undocumented = sorted(parser_flags - set(documented_long_flags()))
        assert undocumented == []

    def test_documented_short_flags_exist_in_the_parser(self):
        parser_flags = {
            option for action in cli_parser()._actions for option in action.option_strings
        }
        documented_short = {
            token
            for cell in documented_flag_cells()
            for token in BACKTICKED.findall(cell)
            if token.startswith("-") and not token.startswith("--")
        }

        assert documented_short <= parser_flags


class TestDocumentedValues:

    def test_documented_output_formats_match_the_parser_choices(self):
        format_action = next(
            action for action in cli_parser()._actions if "--format" in action.option_strings
        )
        documented = {
            token
            for flag_cell, effect_cell in documented_flag_rows()
            if flag_cell.startswith("`--format")
            for token in BACKTICKED.findall(effect_cell)
        }

        assert set(format_action.choices) == set(OUTPUT_FORMATS)
        assert documented == set(OUTPUT_FORMATS)

    def test_documented_exit_codes_match_the_exit_code_enum(self):
        assert documented_exit_codes() == [int(code) for code in ExitCode]


SCHEMA_EXAMPLE_ANCHOR = "`--schema -j` returns:"


def documented_schema_example():
    text = REFERENCE_PATH.read_text(encoding="utf-8")
    # The example is the first fenced json block after the sentence introducing it
    block = text.split(SCHEMA_EXAMPLE_ANCHOR, 1)[1].split("```json", 1)[1].split("```", 1)[0]
    return json.loads(block)


class TestDocumentedSchemaShape:

    def test_example_block_was_extracted(self):
        assert documented_schema_example()["service"] == "ec2"

    def test_documented_keys_match_the_real_schema(self):
        documented = documented_schema_example()
        real = build_schema("ec2", "describe-instances")

        assert set(documented) == set(real)

    def test_schema_contract_is_the_documented_ten_keys(self):
        assert sorted(build_schema("ec2", "describe-instances")) == [
            "action",
            "data_field",
            "default_columns",
            "filter_hint",
            "input",
            "operation",
            "output_fields",
            "paginated",
            "readonly",
            "service",
        ]

    def test_documented_input_block_matches_the_real_one(self):
        documented = documented_schema_example()["input"]
        real = build_schema("ec2", "describe-instances")["input"]

        assert set(documented) == set(real) == {"required", "parameters"}

    def test_documented_scalar_values_match_the_real_schema(self):
        documented = documented_schema_example()
        real = build_schema("ec2", "describe-instances")

        for key in ("service", "action", "operation", "readonly", "paginated", "data_field"):
            assert documented[key] == real[key]
