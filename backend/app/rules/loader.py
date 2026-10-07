"""rules/*.yaml 불러오기. 엔진은 코드에 기준값을 두지 않고 여기서 읽은 값만 쓴다 (FR-045)."""
from functools import lru_cache
from pathlib import Path

import yaml

from app.config import rules_dir

RULE_FILES = ("fields", "verdict", "alert", "linkage", "special_terms", "todos", "guarantors")


def load_rules(directory: Path) -> dict[str, dict]:
    rules = {}
    for name in RULE_FILES:
        with open(directory / f"{name}.yaml", encoding="utf-8") as f:
            rules[name] = yaml.safe_load(f)
    return rules


@lru_cache
def get_rules() -> dict[str, dict]:
    return load_rules(rules_dir())
