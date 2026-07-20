"""rules.yaml loader: happy path, validation failures, and the shipped default file."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.models import Severity
from app.rules.builtin import MaxTradesPerDay
from app.rules.engine import RuleConfigError, available_rules
from app.rules.loader import (
    bootstrap_rules_file,
    bootstrap_rules_file_at,
    find_rules_file,
    load_rules_config,
)

VALID = """
account:
  account_size: "25000"
rules:
  max_trades_per_day:
    n: 4
  stop_required:
    within_minutes: 5
    severity: warn
"""


def write_yaml(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "rules.yaml"
    path.write_text(content, encoding="utf-8")
    return path


class TestLoadRulesConfig:
    def test_valid_config(self, tmp_path: Path):
        config = load_rules_config(write_yaml(tmp_path, VALID))
        assert config.settings.account_size == Decimal("25000")
        assert config.settings.timezone == "America/New_York"  # default applies
        assert config.enabled_rule_ids() == ["max_trades_per_day", "stop_required"]
        (per_day, stop) = config.rules
        assert isinstance(per_day, MaxTradesPerDay)
        assert per_day.params.n == 4
        assert per_day.severity is Severity.VIOLATION
        assert stop.severity is Severity.WARN  # override honored

    def test_enabled_false_skips_rule_but_keeps_params_valid(self, tmp_path: Path):
        path = write_yaml(
            tmp_path,
            VALID + '  max_daily_loss:\n    enabled: false\n    amount: "500"\n',
        )
        config = load_rules_config(path)
        assert "max_daily_loss" not in config.enabled_rule_ids()

    def test_unknown_rule_id(self, tmp_path: Path):
        path = write_yaml(tmp_path, "account:\n  account_size: '1'\nrules:\n  nope:\n    x: 1\n")
        with pytest.raises(RuleConfigError, match="unknown rule 'nope'"):
            load_rules_config(path)

    def test_bad_params_name_the_rule(self, tmp_path: Path):
        path = write_yaml(
            tmp_path, "account:\n  account_size: '1'\nrules:\n  max_trades_per_day:\n    n: 0\n"
        )
        with pytest.raises(RuleConfigError, match="max_trades_per_day.*invalid params"):
            load_rules_config(path)

    def test_missing_account_section(self, tmp_path: Path):
        path = write_yaml(tmp_path, "rules:\n  max_trades_per_day:\n    n: 3\n")
        with pytest.raises(RuleConfigError, match="missing required 'account'"):
            load_rules_config(path)

    def test_invalid_account_settings(self, tmp_path: Path):
        path = write_yaml(tmp_path, "account:\n  acct_size: '25000'\nrules: {}\n")
        with pytest.raises(RuleConfigError, match="invalid account settings"):
            load_rules_config(path)

    def test_invalid_severity(self, tmp_path: Path):
        path = write_yaml(
            tmp_path,
            "account:\n  account_size: '1'\nrules:\n"
            "  max_trades_per_day:\n    n: 3\n    severity: fatal\n",
        )
        with pytest.raises(RuleConfigError, match="invalid severity 'fatal'"):
            load_rules_config(path)

    def test_r_param_without_r_value_setting(self, tmp_path: Path):
        path = write_yaml(
            tmp_path, "account:\n  account_size: '25000'\nrules:\n  max_daily_loss:\n    r: '3'\n"
        )
        with pytest.raises(RuleConfigError, match="requires 'r_value'"):
            load_rules_config(path)

    def test_unknown_top_level_key(self, tmp_path: Path):
        path = write_yaml(tmp_path, VALID + "extra_section: {}\n")
        with pytest.raises(RuleConfigError, match=r"unknown top-level key\(s\)"):
            load_rules_config(path)

    def test_not_yaml_mapping(self, tmp_path: Path):
        with pytest.raises(RuleConfigError, match="expected a mapping"):
            load_rules_config(write_yaml(tmp_path, "- just\n- a\n- list\n"))

    def test_missing_file(self, tmp_path: Path):
        with pytest.raises(RuleConfigError, match="rules file not found"):
            load_rules_config(tmp_path / "absent.yaml")

    def test_yaml_float_money_stays_exact(self, tmp_path: Path):
        # Unquoted YAML numbers arrive as floats; they must round-trip exactly.
        path = write_yaml(tmp_path, "account:\n  account_size: 25000.5\nrules: {}\n")
        assert load_rules_config(path).settings.account_size == Decimal("25000.5")


class TestFindRulesFile:
    def test_finds_in_parent_directory(self, tmp_path: Path):
        target = write_yaml(tmp_path, VALID)
        nested = tmp_path / "backend" / "deep"
        nested.mkdir(parents=True)
        assert find_rules_file(nested) == target

    def test_none_when_absent(self, tmp_path: Path):
        # tmp_path's parents hold no rules.yaml (pytest tmp roots are isolated)
        assert find_rules_file(tmp_path) is None


class TestShippedTemplate:
    def test_example_template_loads_and_enables_all_rules(self):
        """rules.example.yaml is the checked-in template (the live rules.yaml
        is gitignored and user-owned), so its exact contents CAN be pinned."""
        example = Path(__file__).resolve().parents[2] / "rules.example.yaml"
        config = load_rules_config(example)
        assert config.settings.account_size == Decimal("25000")
        assert set(config.enabled_rule_ids()) == set(available_rules())


class TestBootstrapRulesFile:
    def test_copies_example_into_place(self, tmp_path: Path):
        (tmp_path / "rules.example.yaml").write_text(VALID, encoding="utf-8")
        created = bootstrap_rules_file(tmp_path)
        assert created == tmp_path / "rules.yaml"
        assert load_rules_config(created).enabled_rule_ids() == [
            "max_trades_per_day",
            "stop_required",
        ]

    def test_finds_example_in_parent_directory(self, tmp_path: Path):
        (tmp_path / "rules.example.yaml").write_text(VALID, encoding="utf-8")
        nested = tmp_path / "backend" / "deep"
        nested.mkdir(parents=True)
        assert bootstrap_rules_file(nested) == tmp_path / "rules.yaml"

    def test_never_overwrites_existing_rules_yaml(self, tmp_path: Path):
        (tmp_path / "rules.example.yaml").write_text(VALID, encoding="utf-8")
        live = write_yaml(tmp_path, "account:\n  account_size: '1889.94'\nrules: {}\n")
        assert bootstrap_rules_file(tmp_path) == live
        assert load_rules_config(live).settings.account_size == Decimal("1889.94")

    def test_none_when_no_example_anywhere(self, tmp_path: Path):
        # tmp_path's parents hold no rules.example.yaml (pytest tmp roots are isolated)
        assert bootstrap_rules_file(tmp_path) is None


class TestBootstrapRulesFileAt:
    """TRADEGUARD_RULES may point somewhere empty (a fresh Docker volume);
    the template is copied *to that path*, parent directories included."""

    def test_creates_target_from_template(self, tmp_path: Path):
        (tmp_path / "rules.example.yaml").write_text(VALID, encoding="utf-8")
        target = tmp_path / "data" / "rules.yaml"
        assert bootstrap_rules_file_at(target, start=tmp_path) is True
        assert load_rules_config(target).enabled_rule_ids() == [
            "max_trades_per_day",
            "stop_required",
        ]

    def test_existing_target_is_never_touched(self, tmp_path: Path):
        (tmp_path / "rules.example.yaml").write_text(VALID, encoding="utf-8")
        live = write_yaml(tmp_path, "account:\n  account_size: '1889.94'\nrules: {}\n")
        assert bootstrap_rules_file_at(live, start=tmp_path) is False
        assert load_rules_config(live).settings.account_size == Decimal("1889.94")

    def test_quiet_noop_without_a_template(self, tmp_path: Path):
        target = tmp_path / "data" / "rules.yaml"
        assert bootstrap_rules_file_at(target, start=tmp_path) is False
        assert not target.exists()
