"""Tests for the configuration file: defaults, validation, and finding the project root."""

from pathlib import Path

import pytest

from kotlin_qa.config import TOOLS, ConfigError, find_root, load_config


def write(root: Path, text: str) -> None:
    (root / "qa").mkdir(exist_ok=True)
    (root / "qa" / "kotlin-qa.toml").write_text(text, encoding="utf-8")


def test_a_project_without_a_file_gets_the_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    assert config.root == tmp_path
    assert config.record.path == "qa/record.toml"
    assert config.docs_dir == "qa/defences"
    assert config.rule_dirs == ("qa/rules",)
    assert config.scan_exclude == ()
    assert all(config.tools[tool] for tool in TOOLS if tool != "summary")
    assert config.summary_file is None
    assert config.gradle.test_task == "testDebugUnitTest"
    assert config.gradle.lint_task == "lintDebug"
    assert config.gradle.build_task == "assembleDebug"
    assert config.gradle.wrapper == "./gradlew"
    assert config.checks == ()


def test_keys_override_the_defaults(tmp_path: Path) -> None:
    write(
        tmp_path,
        'docs_dir = "docs/defences"\n'
        'rule_dirs = ["qa/rules", "qa/more"]\n'
        'scan_exclude = ["vendor/**"]\n'
        "[tools]\nlint = false\n"
        '[summary]\nfile = "CLAUDE.md"\n'
        '[gradle]\ntest_task = "testReleaseUnitTest"\nbuild_task = "assembleRelease"\n'
        "[record]\nmax_total = 3\n",
    )
    config = load_config(tmp_path)
    assert config.docs_dir == "docs/defences"
    assert config.rule_dirs == ("qa/rules", "qa/more")
    assert config.scan_exclude == ("vendor/**",)
    assert config.tools["lint"] is False
    assert config.tools["test"] is True
    assert config.summary_file == "CLAUDE.md"
    assert config.gradle.test_task == "testReleaseUnitTest"
    assert config.gradle.build_task == "assembleRelease"
    assert config.record.max_total == 3
    assert config.record.max_per_rule == 5


def test_a_project_check_is_read(tmp_path: Path) -> None:
    write(
        tmp_path,
        '[[check]]\nname = "shellcheck"\nphase = "detectors"\n'
        'description = "Every shell script passes ShellCheck."\n'
        'command = ["shellcheck", "{files}"]\nfiles = ["**/*.sh"]\n'
        'doc = "qa/defences/shellcheck.md"\n',
    )
    (check,) = load_config(tmp_path).checks
    assert check.name == "shellcheck"
    assert check.phase == "detectors"
    assert check.command == ("shellcheck", "{files}")
    assert check.files == ("**/*.sh",)


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("colour = 1\n", "unknown key colour"),
        ("[tools]\nnonsense = true\n", "unknown tool nonsense"),
        ("[tools]\nlint = 1\n", "tools.lint must be true or false"),
        ("[gradle]\nwrapper = 3\n", "gradle.wrapper must be a string"),
        ("[gradle]\nspeed = 3\n", "unknown key gradle.speed"),
        ("[record]\nmax_total = 0\n", "record.max_total must be a positive integer"),
        ('rule_dirs = "qa/rules"\n', "rule_dirs must be a list of strings"),
        ('[[check]]\nname = "x"\n', "check #1: command is missing"),
        (
            '[[check]]\nname = "Bad Name"\ncommand = ["x"]\ndescription = "d"\ndoc = "d.md"\n',
            "check #1: name must be lower case",
        ),
        (
            '[[check]]\nname = "fmt"\ncommand = ["x"]\ndescription = "d"\ndoc = "d.md"\n',
            "check #1: name fmt is already a tool",
        ),
        (
            '[[check]]\nname = "x"\ncommand = ["x"]\ndescription = "d"\ndoc = "d.md"\n'
            'phase = "later"\n',
            "check #1: phase must be",
        ),
        ("this is not toml", "cannot parse"),
    ],
)
def test_a_bad_configuration_is_refused_naming_the_key(
    tmp_path: Path, text: str, fragment: str
) -> None:
    write(tmp_path, text)
    with pytest.raises(ConfigError, match=fragment):
        load_config(tmp_path)


def test_the_root_is_the_nearest_directory_holding_the_file(tmp_path: Path) -> None:
    write(tmp_path, "")
    nested = tmp_path / "app" / "src"
    nested.mkdir(parents=True)
    assert find_root(nested) == tmp_path


def test_without_a_file_the_root_is_where_the_command_ran(tmp_path: Path) -> None:
    assert find_root(tmp_path) == tmp_path
