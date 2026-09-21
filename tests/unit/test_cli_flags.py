"""Consolidated tests for CLI flag handling in all positions.

This test suite ensures that CLI flags (-d, -j, -k, --region, --profile) work
correctly regardless of their position in the command line, including after
the -- separator.
"""

import json
import sys
from unittest.mock import Mock, patch

import pytest

from awsquery.cli import main
from awsquery.errors import set_structured_errors


@pytest.fixture(autouse=True)
def reset_structured_errors():
    # main() flips this module-level switch under --format json/ndjson
    yield
    set_structured_errors(False)


class TestCLIFlagHandling:
    """Test that CLI flags work in all positions."""

    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.validate_readonly")
    def test_debug_flag_positions(self, mock_validate, mock_execute, mock_session):
        """Test -d flag works in various positions."""
        mock_validate.return_value = True
        mock_execute.return_value = [{"Instances": []}]
        mock_session.return_value = Mock()

        test_cases = [
            ["awsquery", "-d", "ec2", "describe-instances"],  # Before service
            ["awsquery", "ec2", "-d", "describe-instances"],  # Between service and action
            ["awsquery", "ec2", "describe-instances", "-d"],  # After action
            ["awsquery", "ec2", "describe-instances", "prod", "-d"],  # After filters
            ["awsquery", "ec2", "describe-instances", "--", "Name", "-d"],  # After separator
            ["awsquery", "ec2", "describe-instances", "--", "-d", "Name"],  # Right after separator
        ]

        with patch("awsquery.cli.flatten_response", return_value=[]):
            with patch("awsquery.cli.filter_resources", return_value=[]):
                with patch("awsquery.cli.format_table_output", return_value=""):
                    for argv in test_cases:
                        sys.argv = argv
                        # Reset debug mode
                        from awsquery import utils

                        utils.set_debug_enabled(False)

                        try:
                            main()
                        except SystemExit:
                            pass

                        assert utils.get_debug_enabled() is True, f"Debug not enabled for: {argv}"

    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.validate_readonly")
    def test_json_flag_positions(self, mock_validate, mock_execute, mock_session):
        """Test -j flag works in various positions."""
        mock_validate.return_value = True
        mock_execute.return_value = [{"Instances": [{"InstanceId": "i-123"}]}]
        mock_session.return_value = Mock()

        test_cases = [
            ["awsquery", "-j", "ec2", "describe-instances"],
            ["awsquery", "ec2", "describe-instances", "-j"],
            ["awsquery", "ec2", "describe-instances", "--", "InstanceId", "-j"],
        ]

        with patch("awsquery.cli.flatten_response") as mock_flatten:
            with patch("awsquery.cli.filter_resources") as mock_filter:
                with patch("awsquery.cli.format_json_output") as mock_json:
                    mock_flatten.return_value = [{"InstanceId": "i-123"}]
                    mock_filter.return_value = [{"InstanceId": "i-123"}]
                    mock_json.return_value = '{"InstanceId": "i-123"}'

                    for argv in test_cases:
                        sys.argv = argv
                        mock_json.reset_mock()

                        try:
                            main()
                        except SystemExit:
                            pass

                        mock_json.assert_called_once()

    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.validate_readonly")
    def test_keys_flag_positions(self, mock_validate, mock_execute, mock_session):
        """Test -k flag works in various positions."""
        mock_validate.return_value = True
        mock_session.return_value = Mock()

        test_cases = [
            ["awsquery", "-k", "ec2", "describe-instances"],
            ["awsquery", "ec2", "describe-instances", "-k"],
            ["awsquery", "ec2", "describe-instances", "--", "Name", "-k"],
        ]

        with patch("awsquery.cli.execute_with_tracking") as mock_tracking:
            from awsquery.core import CallResult

            result = CallResult()
            result.final_success = True
            result.last_successful_response = [{"Instances": [{"InstanceId": "i-123"}]}]
            mock_tracking.return_value = result

            with patch("awsquery.cli.keys_from_result", return_value=(["InstanceId"], None)):
                with patch("builtins.print"):
                    for argv in test_cases:
                        sys.argv = argv
                        mock_tracking.reset_mock()

                        try:
                            main()
                        except SystemExit:
                            pass

                        mock_tracking.assert_called_once()

    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.validate_readonly")
    def test_region_profile_flags(self, mock_validate, mock_execute, mock_session):
        """Test --region and --profile flags in various positions."""
        mock_validate.return_value = True
        mock_execute.return_value = [{"Instances": []}]
        mock_session.return_value = Mock()

        test_cases = [
            (
                ["awsquery", "--region", "us-west-2", "ec2", "describe-instances"],
                {"region": "us-west-2", "profile": None},
            ),
            (
                ["awsquery", "ec2", "describe-instances", "--region", "eu-west-1"],
                {"region": "eu-west-1", "profile": None},
            ),
            (
                ["awsquery", "ec2", "describe-instances", "--", "Name", "--region", "ap-south-1"],
                {"region": "ap-south-1", "profile": None},
            ),
            (
                ["awsquery", "--profile", "prod", "ec2", "describe-instances"],
                {"region": None, "profile": "prod"},
            ),
            (
                [
                    "awsquery",
                    "ec2",
                    "describe-instances",
                    "--profile",
                    "dev",
                    "--region",
                    "us-east-1",
                ],
                {"region": "us-east-1", "profile": "dev"},
            ),
        ]

        with patch("awsquery.cli.flatten_response", return_value=[]):
            with patch("awsquery.cli.filter_resources", return_value=[]):
                with patch("awsquery.cli.format_table_output", return_value=""):
                    for argv, expected in test_cases:
                        sys.argv = argv
                        mock_session.reset_mock()

                        try:
                            main()
                        except SystemExit:
                            pass

                        mock_session.assert_called_once_with(
                            region=expected["region"], profile=expected["profile"]
                        )

    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.validate_readonly")
    def test_multiple_flags_after_separator(self, mock_validate, mock_execute, mock_session):
        """Test multiple flags work when placed after -- separator."""
        mock_validate.return_value = True
        mock_execute.return_value = [{"Instances": [{"InstanceId": "i-123"}]}]
        mock_session.return_value = Mock()

        # Test all flags can appear after the separator
        sys.argv = [
            "awsquery",
            "ec2",
            "describe-instances",
            "--",
            "-j",  # JSON flag after separator
            "-d",  # Debug flag after separator
            "--region",
            "us-west-2",  # Region after separator
            "--profile",
            "prod",  # Profile after separator
            "InstanceId",  # Column filter mixed with flags
        ]

        with patch("awsquery.cli.flatten_response") as mock_flatten:
            with patch("awsquery.cli.filter_resources") as mock_filter:
                with patch("awsquery.cli.format_json_output") as mock_json:
                    mock_flatten.return_value = [{"InstanceId": "i-123"}]
                    mock_filter.return_value = [{"InstanceId": "i-123"}]
                    mock_json.return_value = '{"InstanceId": "i-123"}'

                    try:
                        main()
                    except SystemExit:
                        pass

                    # All flags should be recognized
                    from awsquery import utils

                    assert utils.get_debug_enabled() is True
                    mock_json.assert_called_once()
                    mock_session.assert_called_once_with(region="us-west-2", profile="prod")

                    # Column filter should still work
                    json_args = mock_json.call_args[0]
                    assert "InstanceId" in json_args[1]

    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.validate_readonly")
    def test_flags_with_value_and_column_filters(self, mock_validate, mock_execute, mock_session):
        """Test flags work correctly with both value and column filters."""
        mock_validate.return_value = True
        mock_execute.return_value = [
            {"Instances": [{"InstanceId": "i-123", "State": {"Name": "running"}}]}
        ]
        mock_session.return_value = Mock()

        sys.argv = [
            "awsquery",
            "ec2",
            "describe-instances",
            "prod",
            "running",  # value filters
            "-d",  # flag between filters
            "--",
            "InstanceId",
            "State.Name",  # column filters
            "-j",  # flag after column filters
        ]

        with patch("awsquery.cli.flatten_response") as mock_flatten:
            with patch("awsquery.cli.filter_resources") as mock_filter:
                with patch("awsquery.cli.format_json_output") as mock_json:
                    mock_flatten.return_value = [
                        {"InstanceId": "i-123", "State": {"Name": "running"}}
                    ]
                    mock_filter.return_value = [
                        {"InstanceId": "i-123", "State": {"Name": "running"}}
                    ]
                    mock_json.return_value = '{"InstanceId": "i-123", "State": {"Name": "running"}}'

                    try:
                        main()
                    except SystemExit:
                        pass

                    # Verify value filters
                    filter_args = mock_filter.call_args[0]
                    assert "prod" in filter_args[1]
                    assert "running" in filter_args[1]

                    # Verify column filters
                    json_args = mock_json.call_args[0]
                    assert "InstanceId" in json_args[1]
                    assert "State.Name" in json_args[1]

                    # Verify flags
                    from awsquery import utils

                    assert utils.get_debug_enabled() is True
                    mock_json.assert_called_once()

    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.validate_readonly")
    def test_json_flag_with_defaulted_action(self, mock_validate, mock_execute, mock_session):
        """-j flag applies to a service with no explicit action."""
        mock_validate.return_value = True
        mock_execute.return_value = [{"Instances": [{"InstanceId": "i-123"}]}]
        mock_session.return_value = Mock()

        sys.argv = ["awsquery", "ec2", "-j"]

        with patch("awsquery.cli.flatten_response") as mock_flatten:
            with patch("awsquery.cli.filter_resources") as mock_filter:
                with patch("awsquery.cli.format_json_output") as mock_json:
                    mock_flatten.return_value = [{"InstanceId": "i-123"}]
                    mock_filter.return_value = [{"InstanceId": "i-123"}]
                    mock_json.return_value = '{"InstanceId": "i-123"}'

                    try:
                        main()
                    except SystemExit:
                        pass

                    mock_json.assert_called_once()
                    mock_execute.assert_called_once_with(
                        "ec2",
                        "describe-instances",
                        parameters={},
                        session=mock_session.return_value,
                    )

    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.validate_readonly")
    def test_debug_flag_announces_defaulted_action_on_stderr(
        self, mock_validate, mock_execute, mock_session, capsys
    ):
        """-d with a bare service prints the 'Using default action' line on stderr."""
        mock_validate.return_value = True
        mock_execute.return_value = [{"Instances": []}]
        mock_session.return_value = Mock()

        sys.argv = ["awsquery", "-d", "ec2"]

        with patch("awsquery.cli.flatten_response", return_value=[]):
            with patch("awsquery.cli.filter_resources", return_value=[]):
                with patch("awsquery.cli.format_table_output", return_value=""):
                    try:
                        main()
                    except SystemExit:
                        pass

        captured = capsys.readouterr()
        assert "Using default action for ec2: describe-instances" in captured.err
        assert "Using default action for ec2: describe-instances" not in captured.out

    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.validate_readonly")
    def test_parameter_flag_reaches_execute_aws_call_for_defaulted_action(
        self, mock_validate, mock_execute, mock_session
    ):
        """-p MaxResults=5 reaches execute_aws_call for a defaulted service action."""
        mock_validate.return_value = True
        mock_execute.return_value = [{"Instances": []}]
        mock_session.return_value = Mock()

        sys.argv = ["awsquery", "ec2", "-p", "MaxResults=5"]

        with patch("awsquery.cli.flatten_response", return_value=[]):
            with patch("awsquery.cli.filter_resources", return_value=[]):
                with patch("awsquery.cli.format_table_output", return_value=""):
                    try:
                        main()
                    except SystemExit:
                        pass

        mock_execute.assert_called_once_with(
            "ec2",
            "describe-instances",
            parameters={"MaxResults": 5},
            session=mock_session.return_value,
        )

    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.validate_readonly")
    def test_validate_readonly_receives_kebab_defaulted_action(
        self, mock_validate, mock_execute, mock_session
    ):
        """validate_readonly is reached with the kebab spelling for a defaulted action."""
        mock_validate.return_value = True
        mock_execute.return_value = [{"Instances": []}]
        mock_session.return_value = Mock()

        sys.argv = ["awsquery", "ec2"]

        with patch("awsquery.cli.flatten_response", return_value=[]):
            with patch("awsquery.cli.filter_resources", return_value=[]):
                with patch("awsquery.cli.format_table_output", return_value=""):
                    try:
                        main()
                    except SystemExit:
                        pass

        mock_validate.assert_called_once_with("ec2", "describe-instances", allow_unsafe=False)


INSTANCES_RESPONSE = [
    {
        "Reservations": [
            {"Instances": [{"InstanceId": f"i-{index}", "State": {"Name": "running"}}]}
            for index in range(5)
        ]
    }
]


def run_cli(argv, response=None):
    """Run main() with AWS access mocked out, returning the exit code."""
    original_argv = sys.argv
    sys.argv = argv
    response = INSTANCES_RESPONSE if response is None else response
    try:
        with patch("awsquery.cli.execute_aws_call", return_value=response), patch(
            "awsquery.cli.create_session", return_value=Mock()
        ):
            try:
                main()
                return 0
            except SystemExit as exc:
                return 0 if exc.code is None else int(exc.code)
    finally:
        sys.argv = original_argv


class TestOutputFormatFlag:

    @pytest.mark.parametrize(
        "output_format,first_line",
        [
            ("csv", "InstanceId"),
            ("tsv", "InstanceId"),
            ("ndjson", '{"InstanceId":"i-0"}'),
            ("json", "{"),
            ("table", "+--------------+"),
        ],
    )
    def test_accepted_formats_render(self, output_format, first_line, capsys):
        code = run_cli(
            [
                "awsquery",
                "--format",
                output_format,
                "ec2",
                "describe-instances",
                "--",
                "InstanceId$",
            ]
        )

        assert code == 0
        assert capsys.readouterr().out.splitlines()[0].startswith(first_line)

    @pytest.mark.parametrize("output_format", ["xml", "yaml", "JSON", "", "csv "])
    def test_rejected_formats_exit_with_usage_code(self, output_format, capsys):
        code = run_cli(["awsquery", "--format", output_format, "ec2", "describe-instances"])

        assert code == 2
        assert "invalid choice" in capsys.readouterr().err

    def test_json_shorthand_matches_format_json(self, capsys):
        run_cli(["awsquery", "ec2", "describe-instances", "-j", "--", "InstanceId$"])
        shorthand = capsys.readouterr().out

        run_cli(["awsquery", "ec2", "describe-instances", "--format", "json", "--", "InstanceId$"])
        explicit = capsys.readouterr().out

        assert json.loads(shorthand) == json.loads(explicit)
        assert shorthand == explicit

    def test_default_format_is_table(self, capsys):
        run_cli(["awsquery", "ec2", "describe-instances", "--", "InstanceId$"])

        assert capsys.readouterr().out.startswith("+")

    def test_format_after_separator_is_preserved(self, capsys):
        code = run_cli(
            ["awsquery", "ec2", "describe-instances", "--", "InstanceId$", "--format", "csv"]
        )

        assert code == 0
        assert capsys.readouterr().out.splitlines()[0] == "InstanceId"

    def test_machine_formats_keep_stdout_parseable(self, capsys):
        run_cli(
            ["awsquery", "ec2", "describe-instances", "--format", "ndjson", "--", "InstanceId$"]
        )

        lines = capsys.readouterr().out.splitlines()
        assert [json.loads(line)["InstanceId"] for line in lines] == [f"i-{i}" for i in range(5)]


class TestLimitFlag:

    def test_truncates_rows_and_notes_it_on_stderr(self, capsys):
        code = run_cli(
            [
                "awsquery",
                "--format",
                "csv",
                "--limit",
                "2",
                "ec2",
                "describe-instances",
                "--",
                "InstanceId$",
            ]
        )

        captured = capsys.readouterr()
        assert code == 0
        assert captured.out.splitlines() == ["InstanceId", "i-0", "i-1"]
        assert "Showing 2 of 5 rows (--limit 2)" in captured.err

    def test_notice_never_reaches_stdout(self, capsys):
        run_cli(
            [
                "awsquery",
                "--format",
                "ndjson",
                "--limit",
                "3",
                "ec2",
                "describe-instances",
                "--",
                "InstanceId$",
            ]
        )

        captured = capsys.readouterr()
        assert "Showing" not in captured.out
        assert [json.loads(line) for line in captured.out.splitlines()] == [
            {"InstanceId": "i-0"},
            {"InstanceId": "i-1"},
            {"InstanceId": "i-2"},
        ]

    def test_json_output_stays_parseable_under_limit(self, capsys):
        run_cli(
            ["awsquery", "-j", "--limit", "2", "ec2", "describe-instances", "--", "InstanceId$"]
        )

        assert len(json.loads(capsys.readouterr().out)["results"]) == 2

    def test_limit_larger_than_result_set_prints_no_notice(self, capsys):
        run_cli(
            [
                "awsquery",
                "--format",
                "csv",
                "--limit",
                "99",
                "ec2",
                "describe-instances",
                "--",
                "InstanceId$",
            ]
        )

        captured = capsys.readouterr()
        assert len(captured.out.splitlines()) == 6
        assert "Showing" not in captured.err

    def test_limit_equal_to_result_set_prints_no_notice(self, capsys):
        run_cli(
            [
                "awsquery",
                "--format",
                "csv",
                "--limit",
                "5",
                "ec2",
                "describe-instances",
                "--",
                "InstanceId$",
            ]
        )

        captured = capsys.readouterr()
        assert len(captured.out.splitlines()) == 6
        assert "Showing" not in captured.err

    def test_limit_after_separator_is_preserved(self, capsys):
        run_cli(
            [
                "awsquery",
                "ec2",
                "describe-instances",
                "--",
                "InstanceId$",
                "--format",
                "csv",
                "--limit",
                "1",
            ]
        )

        captured = capsys.readouterr()
        assert captured.out.splitlines() == ["InstanceId", "i-0"]
        assert "Showing 1 of 5 rows" in captured.err

    def test_zero_limit_emits_no_rows(self, capsys):
        run_cli(
            [
                "awsquery",
                "--format",
                "csv",
                "--limit",
                "0",
                "ec2",
                "describe-instances",
                "--",
                "InstanceId$",
            ]
        )

        captured = capsys.readouterr()
        assert captured.out == ""
        assert "Showing 0 of 5 rows" in captured.err

    def test_negative_limit_exits_with_usage_code(self, capsys):
        code = run_cli(["awsquery", "--limit", "-1", "ec2", "describe-instances"])

        assert code == 2
        assert "--limit must not be negative" in capsys.readouterr().err


class TestLimitAndHintLimitIndependence:

    def test_row_limit_applies_while_hint_limit_is_set(self, capsys):
        run_cli(
            [
                "awsquery",
                "--format",
                "csv",
                "--limit",
                "4",
                "-i",
                "::2",
                "ec2",
                "describe-instances",
                "--",
                "InstanceId$",
            ]
        )

        captured = capsys.readouterr()
        assert captured.out.splitlines() == ["InstanceId", "i-0", "i-1", "i-2", "i-3"]
        assert "Using hint limit 2" in captured.err
        assert "Showing 4 of 5 rows" in captured.err

    def test_hint_limit_alone_does_not_truncate_rows(self, capsys):
        run_cli(
            [
                "awsquery",
                "--format",
                "csv",
                "-i",
                "::2",
                "ec2",
                "describe-instances",
                "--",
                "InstanceId$",
            ]
        )

        captured = capsys.readouterr()
        assert len(captured.out.splitlines()) == 6
        assert "Showing" not in captured.err

    def test_row_limit_alone_leaves_no_hint_message(self, capsys):
        run_cli(
            [
                "awsquery",
                "--format",
                "csv",
                "--limit",
                "2",
                "ec2",
                "describe-instances",
                "--",
                "InstanceId$",
            ]
        )

        captured = capsys.readouterr()
        assert "Using hint" not in captured.err
        assert captured.out.splitlines() == ["InstanceId", "i-0", "i-1"]


class TestIntrospectionFlagPositions:

    @pytest.mark.parametrize(
        "argv",
        [
            ["awsquery", "--docs"],
            ["awsquery", "--docs", "ec2", "describe-instances"],
            ["awsquery", "ec2", "describe-instances", "--docs"],
            ["awsquery", "ec2", "describe-instances", "--", "--docs"],
        ],
    )
    def test_docs_flag_positions(self, argv, capsys):
        code = run_cli(argv)

        captured = capsys.readouterr()
        assert code == 0
        assert captured.out.startswith("# awsquery")
        assert "## Flags" in captured.out

    @pytest.mark.parametrize(
        "argv",
        [
            ["awsquery", "--list-services"],
            ["awsquery", "--list-services", "ec2"],
            ["awsquery", "ec2", "describe-instances", "--list-services"],
            ["awsquery", "ec2", "describe-instances", "--", "--list-services"],
        ],
    )
    def test_list_services_flag_positions(self, argv, capsys):
        code = run_cli(argv)

        services = capsys.readouterr().out.splitlines()
        assert code == 0
        assert "ec2" in services
        assert services == sorted(services)

    @pytest.mark.parametrize(
        "argv",
        [
            ["awsquery", "--list-actions", "ec2"],
            ["awsquery", "ec2", "--list-actions"],
            ["awsquery", "ec2", "describe-instances", "--list-actions"],
            ["awsquery", "ec2", "--", "--list-actions"],
        ],
    )
    def test_list_actions_flag_positions(self, argv, capsys):
        code = run_cli(argv)

        actions = capsys.readouterr().out.splitlines()
        assert code == 0
        assert "describe-instances" in actions
        assert "terminate-instances" not in actions

    @pytest.mark.parametrize(
        "argv",
        [
            ["awsquery", "--schema", "ec2", "describe-instances"],
            ["awsquery", "ec2", "--schema", "describe-instances"],
            ["awsquery", "ec2", "describe-instances", "--schema"],
            ["awsquery", "ec2", "describe-instances", "--", "--schema"],
        ],
    )
    def test_schema_flag_positions(self, argv, capsys):
        code = run_cli(argv)

        out = capsys.readouterr().out
        assert code == 0
        assert out.splitlines()[0] == "ec2 describe-instances (readonly, paginated)"
        assert "Instances.InstanceId" in out

    def test_list_actions_without_service_exits_with_usage_code(self, capsys):
        code = run_cli(["awsquery", "--list-actions"])

        captured = capsys.readouterr()
        assert code == 2
        assert "--list-actions needs a service name" in captured.err
        assert captured.out == ""

    @pytest.mark.parametrize(
        "argv,loader",
        [
            (["awsquery", "--list-services", "--format", "json"], list),
            (["awsquery", "ec2", "--list-actions", "--format", "json"], list),
            (["awsquery", "--schema", "ec2", "describe-instances", "--format", "json"], dict),
        ],
    )
    def test_json_format_makes_introspection_machine_readable(self, argv, loader, capsys):
        code = run_cli(argv)

        assert code == 0
        assert isinstance(json.loads(capsys.readouterr().out), loader)

    @pytest.mark.parametrize(
        "argv",
        [
            ["awsquery", "--docs"],
            ["awsquery", "--list-services"],
            ["awsquery", "ec2", "--list-actions"],
            ["awsquery", "--schema", "ec2", "describe-instances"],
        ],
    )
    def test_introspection_never_calls_aws(self, argv, capsys):
        original_argv = sys.argv
        sys.argv = argv
        try:
            with patch("awsquery.cli.execute_aws_call") as mock_execute, patch(
                "awsquery.cli.create_session"
            ) as mock_session:
                try:
                    main()
                except SystemExit:
                    pass
        finally:
            sys.argv = original_argv

        capsys.readouterr()
        assert mock_execute.call_count == 0
        assert mock_session.call_count == 0

    def test_unknown_service_for_list_actions_exits_with_usage_code(self, capsys):
        code = run_cli(["awsquery", "not-a-service", "--list-actions"])

        captured = capsys.readouterr()
        assert code == 2
        assert "Unknown service 'not-a-service'" in captured.err
        assert captured.out == ""


def run_keys_cli(argv, response=None):
    """Run main() in --keys mode with a canned tracked response."""
    from awsquery.core import CallResult

    result = CallResult(service="ec2", operation="describe-instances")
    result.final_success = True
    result.last_successful_response = INSTANCES_RESPONSE if response is None else response

    original_argv = sys.argv
    sys.argv = argv
    try:
        with patch("awsquery.cli.execute_with_tracking", return_value=result), patch(
            "awsquery.cli.create_session", return_value=Mock()
        ):
            try:
                main()
                return 0
            except SystemExit as exc:
                return 0 if exc.code is None else int(exc.code)
    finally:
        sys.argv = original_argv


class TestBareInvocationFormats:

    def test_table_prints_the_human_service_line(self, capsys):
        code = run_cli(["awsquery"])

        out = capsys.readouterr().out
        assert code == 0
        assert out.startswith("Available services: ")
        assert "ec2" in out

    def test_json_prints_a_json_array(self, capsys):
        code = run_cli(["awsquery", "--format", "json"])

        services = json.loads(capsys.readouterr().out)
        assert code == 0
        assert isinstance(services, list)
        assert "ec2" in services

    @pytest.mark.parametrize("output_format", ["ndjson", "csv", "tsv"])
    def test_line_formats_print_one_bare_name_per_line(self, output_format, capsys):
        code = run_cli(["awsquery", "--format", output_format])

        lines = capsys.readouterr().out.splitlines()
        assert code == 0
        assert "ec2" in lines
        assert lines == sorted(lines)
        assert all(line == line.strip() and "," not in line for line in lines)

    def test_every_format_lists_the_same_services(self, capsys):
        run_cli(["awsquery", "--format", "json"])
        from_json = json.loads(capsys.readouterr().out)

        run_cli(["awsquery", "--format", "ndjson"])
        from_ndjson = capsys.readouterr().out.splitlines()

        run_cli(["awsquery"])
        from_table = capsys.readouterr().out.split(": ", 1)[1].strip().split(", ")

        assert from_json == from_ndjson == from_table


class TestListActionsFormats:
    # The default (table) rendering is covered by test_list_actions_flag_positions.

    def test_json_prints_a_json_array(self, capsys):
        code = run_cli(["awsquery", "ec2", "--list-actions", "--format", "json"])

        actions = json.loads(capsys.readouterr().out)
        assert code == 0
        assert "describe-instances" in actions

    @pytest.mark.parametrize("output_format", ["ndjson", "csv", "tsv"])
    def test_line_formats_print_one_bare_name_per_line(self, output_format, capsys):
        code = run_cli(["awsquery", "ec2", "--list-actions", "--format", output_format])

        lines = capsys.readouterr().out.splitlines()
        assert code == 0
        assert "describe-instances" in lines
        assert all(line == line.strip() and line and '"' not in line for line in lines)

    def test_every_format_lists_the_same_actions(self, capsys):
        run_cli(["awsquery", "ec2", "--list-actions", "--format", "json"])
        from_json = json.loads(capsys.readouterr().out)

        run_cli(["awsquery", "ec2", "--list-actions", "--format", "csv"])
        from_csv = capsys.readouterr().out.splitlines()

        assert from_json == from_csv


class TestKeysOutputFormat:

    def test_table_indents_each_key(self, capsys):
        code = run_keys_cli(["awsquery", "-k", "ec2", "describe-instances"])

        lines = capsys.readouterr().out.splitlines()
        assert code == 0
        assert all(line.startswith("  ") for line in lines)
        assert "  Instances.0.InstanceId" in lines

    def test_json_wraps_keys_in_an_object(self, capsys):
        code = run_keys_cli(["awsquery", "-k", "--format", "json", "ec2", "describe-instances"])

        payload = json.loads(capsys.readouterr().out)
        assert code == 0
        assert "Instances.0.InstanceId" in payload["keys"]

    def test_ndjson_emits_one_json_string_per_line(self, capsys):
        code = run_keys_cli(["awsquery", "-k", "--format", "ndjson", "ec2", "describe-instances"])

        keys = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
        assert code == 0
        assert "Instances.0.InstanceId" in keys

    @pytest.mark.parametrize("output_format", ["csv", "tsv"])
    def test_delimited_formats_carry_a_key_header(self, output_format, capsys):
        code = run_keys_cli(
            ["awsquery", "-k", "--format", output_format, "ec2", "describe-instances"]
        )

        lines = capsys.readouterr().out.splitlines()
        assert code == 0
        assert lines[0] == "key"
        assert "Instances.0.InstanceId" in lines[1:]

    def test_every_format_reports_the_same_keys(self, capsys):
        run_keys_cli(["awsquery", "-k", "--format", "json", "ec2", "describe-instances"])
        from_json = json.loads(capsys.readouterr().out)["keys"]

        run_keys_cli(["awsquery", "-k", "--format", "ndjson", "ec2", "describe-instances"])
        from_ndjson = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

        run_keys_cli(["awsquery", "-k", "--format", "csv", "ec2", "describe-instances"])
        from_csv = capsys.readouterr().out.splitlines()[1:]

        assert from_json == from_ndjson == from_csv

    def test_progress_notice_never_reaches_stdout(self, capsys):
        run_keys_cli(["awsquery", "-k", "--format", "json", "ec2", "describe-instances"])

        captured = capsys.readouterr()
        assert "Showing all available keys" in captured.err
        assert "Showing all available keys" not in captured.out
        assert json.loads(captured.out)["keys"]


class TestDefaultColumnsNotice:

    @pytest.mark.parametrize("output_format", ["table", "csv", "tsv", "ndjson"])
    def test_notice_goes_to_stderr(self, output_format, capsys):
        code = run_cli(["awsquery", "--format", output_format, "ec2", "describe-instances"])

        captured = capsys.readouterr()
        assert code == 0
        assert "Using default columns: -- " in captured.err
        assert "InstanceId$" in captured.err
        assert "Using default columns" not in captured.out

    def test_json_suppresses_the_notice(self, capsys):
        code = run_cli(["awsquery", "--format", "json", "ec2", "describe-instances"])

        captured = capsys.readouterr()
        assert code == 0
        assert "Using default columns" not in captured.err
        assert json.loads(captured.out)["results"]

    def test_json_shorthand_suppresses_the_notice(self, capsys):
        run_cli(["awsquery", "-j", "ec2", "describe-instances"])

        assert "Using default columns" not in capsys.readouterr().err

    def test_user_columns_replace_the_notice(self, capsys):
        run_cli(["awsquery", "--format", "csv", "ec2", "describe-instances", "--", "InstanceId$"])

        captured = capsys.readouterr()
        assert "Using default columns" not in captured.err
        assert captured.out.splitlines()[0] == "InstanceId"


class TestOfflineActionValidation:

    def test_unknown_action_exits_with_usage_code(self, capsys):
        code = run_cli(["awsquery", "ec2", "describe-unicorns"])

        captured = capsys.readouterr()
        assert code == 2
        assert "Unknown action 'describe-unicorns' for service 'ec2'" in captured.err
        assert "Run: awsquery ec2 --list-actions" in captured.err
        assert captured.out == ""

    def test_unknown_service_exits_with_usage_code(self, capsys):
        code = run_cli(["awsquery", "not-a-service", "describe-things"])

        captured = capsys.readouterr()
        assert code == 2
        assert "Unknown service 'not-a-service'" in captured.err
        assert "Run: awsquery --list-services" in captured.err
        assert captured.out == ""

    def test_existing_unsafe_action_reaches_the_readonly_refusal(self, monkeypatch, capsys):
        monkeypatch.setenv("AWSQUERY_NON_INTERACTIVE", "1")

        code = run_cli(["awsquery", "ec2", "terminate-instances"])

        captured = capsys.readouterr()
        assert code == 2
        assert "'ec2:terminate-instances' may not be read-only" in captured.err
        assert "--allow-unsafe" in captured.err
        assert "Unknown action" not in captured.err

    def test_default_action_injection_validates_clean(self, capsys):
        code = run_cli(["awsquery", "ec2"])

        captured = capsys.readouterr()
        assert code == 0
        assert "Unknown action" not in captured.err
        assert captured.out.startswith("+")

    def test_validation_happens_before_any_session_is_built(self):
        original_argv = sys.argv
        sys.argv = ["awsquery", "ec2", "describe-unicorns"]
        try:
            with patch("awsquery.cli.create_session") as mock_session, patch(
                "awsquery.cli.execute_aws_call"
            ) as mock_execute:
                with pytest.raises(SystemExit):
                    main()
        finally:
            sys.argv = original_argv

        assert mock_session.call_count == 0
        assert mock_execute.call_count == 0


EMPTY_RESPONSE = [{"Reservations": []}]


class TestKeysEmptyResult:

    def test_json_stdout_is_an_empty_keys_document(self, capsys):
        code = run_keys_cli(
            ["awsquery", "-k", "--format", "json", "ec2", "describe-instances"],
            response=EMPTY_RESPONSE,
        )

        captured = capsys.readouterr()
        assert code == 0
        assert json.loads(captured.out) == {"keys": []}

    def test_json_stderr_carries_the_notice_envelope(self, capsys):
        run_keys_cli(
            ["awsquery", "-k", "--format", "json", "ec2", "describe-instances"],
            response=EMPTY_RESPONSE,
        )

        payload = json.loads(
            [line for line in capsys.readouterr().err.splitlines() if line.startswith("{")][0]
        )
        # A consumer branching on "error" must not read an empty result as a failure
        assert "error" not in payload
        assert payload["notice"]["code"] == 0
        assert payload["notice"]["type"] == "EmptyResult"

    def test_csv_stdout_is_the_bare_header(self, capsys):
        code = run_keys_cli(
            ["awsquery", "-k", "--format", "csv", "ec2", "describe-instances"],
            response=EMPTY_RESPONSE,
        )

        assert code == 0
        assert capsys.readouterr().out == "key\n"

    @pytest.mark.parametrize("argv_tail", [["--format", "ndjson"], []])
    def test_line_formats_emit_nothing_on_stdout(self, argv_tail, capsys):
        code = run_keys_cli(
            ["awsquery", "-k", "ec2", "describe-instances"] + argv_tail, response=EMPTY_RESPONSE
        )

        assert code == 0
        assert capsys.readouterr().out.strip() == ""

    @pytest.mark.parametrize(
        "argv_tail", [["--format", "json"], ["--format", "csv"], ["--format", "ndjson"], []]
    )
    def test_nothing_claims_an_error_on_a_zero_exit(self, argv_tail, capsys):
        code = run_keys_cli(
            ["awsquery", "-k", "ec2", "describe-instances"] + argv_tail, response=EMPTY_RESPONSE
        )

        captured = capsys.readouterr()
        assert code == 0
        assert "ERROR" not in captured.err
        assert "Error:" not in captured.err
        assert "ERROR" not in captured.out

    def test_empty_result_is_not_reported_as_a_failed_call(self, capsys):
        run_keys_cli(
            ["awsquery", "-k", "--format", "json", "ec2", "describe-instances"],
            response=EMPTY_RESPONSE,
        )

        stderr = capsys.readouterr().err
        assert "No successful response" not in stderr
        assert "No data to extract keys from" in stderr


class TestIntrospectionErrorBoundary:

    @pytest.mark.parametrize(
        "argv,first_token",
        [
            (["awsquery", "--list-services"], "accessanalyzer"),
            (["awsquery", "ec2", "--list-actions"], "describe-instances"),
        ],
    )
    def test_flags_still_answer_and_exit_zero(self, argv, first_token, capsys):
        code = run_cli(argv)

        out = capsys.readouterr().out
        assert code == 0
        assert first_token in out.splitlines()

    def test_schema_still_answers_and_exits_zero(self, capsys):
        code = run_cli(["awsquery", "--schema", "ec2", "describe-instances"])

        out = capsys.readouterr().out
        assert code == 0
        assert out.splitlines()[0] == "ec2 describe-instances (readonly, paginated)"

    def test_docs_still_answer_and_exit_zero(self, capsys):
        code = run_cli(["awsquery", "--docs"])

        assert code == 0
        assert capsys.readouterr().out.startswith("# awsquery")

    def test_unexpected_failure_inside_a_flag_is_classified(self, capsys):
        original_argv = sys.argv
        sys.argv = ["awsquery", "--list-services"]
        try:
            with patch("awsquery.cli.list_services", side_effect=RuntimeError("model store gone")):
                with pytest.raises(SystemExit) as exit_info:
                    main()
        finally:
            sys.argv = original_argv

        captured = capsys.readouterr()
        assert exit_info.value.code == 1
        assert captured.err.startswith("ERROR: ")
        assert "model store gone" in captured.err
        assert "Traceback" not in captured.err
        assert captured.out == ""

    def test_unexpected_failure_is_structured_under_json(self, capsys):
        original_argv = sys.argv
        sys.argv = ["awsquery", "--list-services", "--format", "json"]
        try:
            with patch("awsquery.cli.list_services", side_effect=RuntimeError("model store gone")):
                with pytest.raises(SystemExit) as exit_info:
                    main()
        finally:
            sys.argv = original_argv

        captured = capsys.readouterr()
        error = json.loads(captured.err)["error"]
        assert exit_info.value.code == 1
        assert error["code"] == 1
        assert error["type"] == "RuntimeError"
        assert captured.out == ""

    def test_usage_failure_inside_a_flag_keeps_its_own_exit_code(self, capsys):
        code = run_cli(["awsquery", "--list-actions"])

        captured = capsys.readouterr()
        assert code == 2
        assert "--list-actions needs a service name" in captured.err
        assert captured.out == ""
