#!/usr/bin/env python
import typing
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import ClassVar, cast

import yaml


@dataclass(frozen=True)
class ScorecardCheck:
    """Represents a metadata quality check for edition scoring."""

    name: str
    score: int
    description: str
    details: str

    def to_dict(self, passing: bool) -> dict:
        return {
            "description": self.description,
            "details": self.details,
            "score": self.score,
            "passing": passing,
        }


@dataclass
class ScorecardSection:
    name: str
    details: str = ""
    _passing_checks: set[ScorecardCheck] = field(default_factory=set)
    _set_checks: set[ScorecardCheck] = field(default_factory=set)

    @property
    def passing_checks(self) -> set[ScorecardCheck]:
        return self._passing_checks

    @property
    def score(self) -> int:
        """Calculates the total score based on the passing checks."""
        return sum(check.score for check in self.passing_checks)

    @property
    def score_normalized(self) -> int:
        """Calculates the total score based on the passing checks, normalized to be out of 100."""
        return 100 * self.score // self.max_score

    @cached_property
    def max_score(self) -> int:
        """Calculates the maximum possible score based on the defined checks."""
        return sum(check.score for check in self.get_checks())

    def set_check(self, check: ScorecardCheck, passed: bool):
        """Adds or removes a check from the passing checks based on whether it passed."""
        self._set_checks.add(check)
        if passed:
            self._passing_checks.add(check)
        else:
            self._passing_checks.discard(check)

    def get_checks(self) -> list[ScorecardCheck]:
        """Returns a list of ScorecardCheck instances representing the metadata quality checks."""
        checks = []
        for attr_name in dir(self):
            if attr_name in ("score", "score_normalized", "max_score", "passing_checks"):
                continue

            attr_value = getattr(self, attr_name)
            if isinstance(attr_value, ScorecardCheck):
                checks.append(attr_value)
        return checks

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "score": self.score,
            "maxScore": self.max_score,
            "checks": [check.to_dict(passing=check in self.passing_checks) for check in self.get_checks()],
        }


@dataclass
class Scorecard(ScorecardSection):
    @property
    @typing.override
    def passing_checks(self) -> set[ScorecardCheck]:
        """Aggregates passing checks from all sections."""
        return {check for section in self.get_sections() for check in section.passing_checks}

    @typing.override
    def get_checks(self) -> list[ScorecardCheck]:
        # Handle nested sections by recursively gathering checks from any ScorecardSection attributes
        checks = []
        for attr_name in dir(self):
            if attr_name in ("score", "score_normalized", "max_score", "passing_checks"):
                continue

            attr_value = getattr(self, attr_name)
            if isinstance(attr_value, ScorecardCheck):
                checks.append(attr_value)
            elif isinstance(attr_value, ScorecardSection):
                checks.extend(attr_value.get_checks())
        return checks

    def get_sections(self) -> list[ScorecardSection]:
        """Returns a list of ScorecardSection instances representing the different sections of the scorecard."""
        sections = []
        for attr_name in dir(self):
            if attr_name in ("score", "score_normalized", "max_score", "passing_checks"):
                continue

            attr_value = getattr(self, attr_name)
            if isinstance(attr_value, ScorecardSection):
                sections.append(attr_value)
        return sections

    @typing.override
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "score": self.score,
            "maxScore": self.max_score,
            "sections": [section.to_dict() for section in self.get_sections()],
        }


class ScorecardEvaluator[S: Scorecard]:
    scorecard_cls: ClassVar[type]

    def evaluate(self) -> S:
        scorecard = cast(S, self.scorecard_cls())
        for section in scorecard.get_sections():
            for check in section.get_checks():
                section.set_check(check, getattr(self, check.name))
        return scorecard


def generate_scorecard(yml_file: str) -> str:
    def to_pascal_case(s: str) -> str:
        return "".join(word.title() for word in s.split("_"))

    def py_str(s: str) -> str:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

    yml_path = Path(yml_file)
    pascal_name = to_pascal_case(yml_path.stem)

    with open(yml_path) as f:
        data = yaml.safe_load(f)

    sections = data["sections"]
    scorecard_name = data["name"]

    lines = [
        "# THIS FILE IS AUTO-GENERATED. DO NOT EDIT DIRECTLY.",
        f"# Source: {yml_path.name}",
        f"# Regenerate: ./openlibrary/scorecards.py generate {yml_path.name}",
        "",
        "from abc import ABC, abstractmethod",
        "from dataclasses import dataclass",
        "",
        "from openlibrary.i18n import gettext as _",
        "from openlibrary.scorecards import Scorecard, ScorecardCheck, ScorecardEvaluator, ScorecardSection",
        "",
        "",
    ]

    section_class_names = {}
    all_check_names: list[str] = []
    seen_check_names: set[str] = set()

    for section_key, section_data in sections.items():
        class_name = f"{pascal_name}{to_pascal_case(section_key)}Section"
        section_class_names[section_key] = class_name

        lines += ["@dataclass", f"class {class_name}(ScorecardSection):"]

        for check_name, check_data in section_data["checks"].items():
            if check_name not in seen_check_names:
                all_check_names.append(check_name)
                seen_check_names.add(check_name)
            lines += [
                f"    {check_name} = ScorecardCheck(",
                f"        name={py_str(check_name)},",
                f"        score={check_data['score']},",
                f"        description=_({py_str(check_data['description'])}),",
                f"        details=_({py_str(check_data['details'])}),",
                "    )",
            ]

        lines += ["", ""]

    lines += ["@dataclass", f"class {pascal_name}(Scorecard):", f"    name: str = _({py_str(scorecard_name)})"]

    for section_key, section_data in sections.items():
        class_name = section_class_names[section_key]
        section_name = section_data["name"]
        section_details = section_data.get("details", "")
        if section_details:
            lines += [
                f"    {section_key} = {class_name}(",
                f"        name=_({py_str(section_name)}),",
                f"        details=_({py_str(section_details)}),",
                "    )",
            ]
        else:
            lines.append(f"    {section_key} = {class_name}(name=_({py_str(section_name)}))")

    lines += [
        "",
        "",
        f"class {pascal_name}Evaluator(ScorecardEvaluator[{pascal_name}], ABC):",
        f"    scorecard_cls = {pascal_name}",
        "",
    ]

    for check_name in all_check_names:
        lines += ["    @property", "    @abstractmethod", f"    def {check_name}(self) -> bool: ...", ""]

    return "\n".join(lines)


def codegen_scorecards(yml_file: str):
    yml_path = Path(yml_file)
    out_path = yml_path.with_suffix(".py")
    out_path.write_text(generate_scorecard(yml_file))
    print(f"Generated {out_path}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 3 and sys.argv[1] == "generate":
        codegen_scorecards(sys.argv[2])
    else:
        print(f"Usage: {sys.argv[0]} generate <file>.yml", file=sys.stderr)
        sys.exit(1)
