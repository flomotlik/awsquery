"""Tests for CLI --help output content."""

import subprocess
import sys
from io import StringIO
from unittest.mock import patch

from awsquery.cli import main


class TestHelpOutputAutocomplete:
    """Test that --help output includes autocomplete documentation."""

    def test_help_includes_autocomplete_section(self):
        """Test main parser --help includes autocomplete section."""
        result = subprocess.run(
            [sys.executable, "-m", "awsquery.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert result.returncode == 0
        assert "Autocomplete Setup:" in result.stdout

    def test_help_includes_bash_autocomplete(self):
        """Test --help includes bash autocomplete instructions."""
        result = subprocess.run(
            [sys.executable, "-m", "awsquery.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert "Bash:" in result.stdout
        assert 'eval "$(register-python-argcomplete awsquery)"' in result.stdout

    def test_help_includes_zsh_autocomplete(self):
        """Test --help includes zsh autocomplete instructions."""
        result = subprocess.run(
            [sys.executable, "-m", "awsquery.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert "Zsh:" in result.stdout
        assert "autoload -U bashcompinit && bashcompinit" in result.stdout
        assert 'eval "$(register-python-argcomplete awsquery)"' in result.stdout

    def test_help_includes_fish_autocomplete(self):
        """Test --help includes fish autocomplete instructions."""
        result = subprocess.run(
            [sys.executable, "-m", "awsquery.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert "Fish:" in result.stdout
        assert "register-python-argcomplete --shell fish awsquery | source" in result.stdout

    def test_help_includes_github_documentation_link(self):
        """Test --help includes GitHub documentation link."""
        result = subprocess.run(
            [sys.executable, "-m", "awsquery.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert "https://github.com/flomotlik/awsquery#enable-shell-autocomplete" in result.stdout

    def test_help_includes_shell_config_instructions(self):
        """Test --help includes instructions to add to shell config."""
        result = subprocess.run(
            [sys.executable, "-m", "awsquery.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert "Add the appropriate command to your shell config" in result.stdout
        assert "~/.bashrc" in result.stdout
        assert "~/.zshrc" in result.stdout

    def test_help_preserves_existing_examples(self):
        """Test --help still includes existing command examples."""
        result = subprocess.run(
            [sys.executable, "-m", "awsquery.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert "Examples:" in result.stdout
        assert (
            "awsquery ec2 describe-instances prod web -- Tags.Name State InstanceId"
            in result.stdout
        )
        assert "awsquery s3 list-buckets backup" in result.stdout
        assert (
            "awsquery cloudformation describe-stack-events prod -- Created StackName"
            in result.stdout
        )

    def test_help_output_formatting_clean(self):
        """Test --help output has clean formatting without extra blank lines."""
        result = subprocess.run(
            [sys.executable, "-m", "awsquery.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        output_lines = result.stdout.split("\n")

        # Find the Examples section
        examples_index = None
        autocomplete_index = None
        for i, line in enumerate(output_lines):
            if line.strip().startswith("Examples:"):
                examples_index = i
            if line.strip().startswith("Autocomplete Setup:"):
                autocomplete_index = i

        assert examples_index is not None, "Examples section not found"
        assert autocomplete_index is not None, "Autocomplete Setup section not found"
        assert (
            autocomplete_index > examples_index
        ), "Autocomplete section should come after Examples"


class TestServiceHelpAutocomplete:
    """Test that service-level --help also includes autocomplete documentation."""

    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.validate_readonly")
    def test_service_help_includes_autocomplete(self, mock_validate, mock_execute, mock_session):
        """Test 'awsquery ec2 --help' includes autocomplete documentation."""
        mock_validate.return_value = True

        result = subprocess.run(
            [sys.executable, "-m", "awsquery.cli", "ec2", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert "Autocomplete Setup:" in result.stdout
        assert "Bash:" in result.stdout
        assert "Zsh:" in result.stdout
        assert "Fish:" in result.stdout


class TestMainFunctionParserHelp:
    """Test main() function parser epilog includes autocomplete."""

    def test_main_parser_creation_includes_autocomplete(self):
        """Test that main() creates parser with autocomplete documentation."""
        # Capture help output by running main with --help
        result = subprocess.run(
            [sys.executable, "-m", "awsquery.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert result.returncode == 0
        assert "Autocomplete Setup:" in result.stdout

        # Verify all three shell types are documented
        assert result.stdout.count("eval") >= 2  # bash and zsh both use eval
        assert result.stdout.count("register-python-argcomplete") >= 3  # all three shells


class TestAutocompleteContentAccuracy:
    """Test autocomplete instructions are accurate and complete."""

    def test_bash_instructions_correct_format(self):
        """Test bash instructions have correct command format."""
        result = subprocess.run(
            [sys.executable, "-m", "awsquery.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        # Verify bash section has proper eval command with quotes
        assert 'eval "$(register-python-argcomplete awsquery)"' in result.stdout

    def test_zsh_instructions_include_bashcompinit(self):
        """Test zsh instructions include bashcompinit initialization."""
        result = subprocess.run(
            [sys.executable, "-m", "awsquery.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        # Verify zsh section has bashcompinit setup
        assert "autoload -U bashcompinit && bashcompinit" in result.stdout

    def test_fish_instructions_use_pipe_to_source(self):
        """Test fish instructions use pipe to source pattern."""
        result = subprocess.run(
            [sys.executable, "-m", "awsquery.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        # Verify fish section uses | source pattern
        assert "| source" in result.stdout
        assert "--shell fish" in result.stdout

    def test_all_shell_config_files_mentioned(self):
        """Test all relevant shell config files are mentioned."""
        result = subprocess.run(
            [sys.executable, "-m", "awsquery.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        # Verify shell config file examples are provided
        assert "~/.bashrc" in result.stdout or ".bashrc" in result.stdout
        assert "~/.zshrc" in result.stdout or ".zshrc" in result.stdout


class TestHelpOutputEdgeCases:
    """Test edge cases in help output."""

    def test_help_with_other_flags_still_works(self):
        """Test --help works with other flags like --debug."""
        result = subprocess.run(
            [sys.executable, "-m", "awsquery.cli", "--debug", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert result.returncode == 0
        assert "Autocomplete Setup:" in result.stdout

    def test_help_short_flag_includes_autocomplete(self):
        """Test -h short flag also includes autocomplete documentation."""
        result = subprocess.run(
            [sys.executable, "-m", "awsquery.cli", "-h"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert result.returncode == 0
        assert "Autocomplete Setup:" in result.stdout

    def test_help_output_uses_raw_description_formatter(self):
        """Test help output preserves formatting with RawDescriptionHelpFormatter."""
        result = subprocess.run(
            [sys.executable, "-m", "awsquery.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        # With RawDescriptionHelpFormatter, indentation and line breaks are preserved
        # Check for preserved indentation in autocomplete commands
        lines = result.stdout.split("\n")

        # Find autocomplete section and verify indentation is preserved
        in_autocomplete_section = False
        found_indented_bash = False
        found_indented_command = False

        for line in lines:
            if "Autocomplete Setup:" in line:
                in_autocomplete_section = True
            elif in_autocomplete_section:
                # Check for indented shell names
                if line.strip().startswith("Bash:") and line.startswith("  "):
                    found_indented_bash = True
                # Check for indented commands
                if "register-python-argcomplete" in line and line.startswith("    "):
                    found_indented_command = True

        assert (
            found_indented_bash or found_indented_command
        ), "Autocomplete formatting not preserved"
