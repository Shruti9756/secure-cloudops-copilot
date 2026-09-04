"""Deterministic detection of strong prompt-injection indicators."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PromptInjectionRule:
    """One narrow, explainable prompt-injection indicator."""

    rule_id: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class PromptInjectionDetectionResult:
    """Safe detection result that never retains the submitted content."""

    is_suspicious: bool
    matched_rule_ids: tuple[str, ...]


PROMPT_INJECTION_RULES = (
    PromptInjectionRule(
        rule_id="ignore_previous_instructions",
        pattern=re.compile(
            r"\bignore\s+(?:all\s+|any\s+|the\s+)?"
            r"(?:previous|prior|above)\s+"
            r"(?:instructions|rules|directions)\b",
            re.IGNORECASE,
        ),
    ),
    PromptInjectionRule(
        rule_id="reveal_system_prompt",
        pattern=re.compile(
            r"\b(?:reveal|show|print|repeat)\s+(?:the\s+)?"
            r"(?:system\s+prompt|hidden\s+instructions|developer\s+message)\b",
            re.IGNORECASE,
        ),
    ),
    PromptInjectionRule(
        rule_id="override_safety_controls",
        pattern=re.compile(
            r"\b(?:disregard|override|bypass)\s+(?:all\s+)?"
            r"(?:safety|security|system|previous)\s+"
            r"(?:instructions|rules|controls)\b",
            re.IGNORECASE,
        ),
    ),
    PromptInjectionRule(
        rule_id="jailbreak_persona",
        pattern=re.compile(
            r"\b(?:you\s+are\s+now|act\s+as|pretend\s+to\s+be)\s+"
            r"(?:an?\s+)?(?:unrestricted|jailbroken)\b",
            re.IGNORECASE,
        ),
    ),
)


def detect_prompt_injection(content: str) -> PromptInjectionDetectionResult:
    """Flag strong instruction-override patterns without retaining raw content."""
    if not isinstance(content, str):
        raise TypeError("Content must be a string")

    matched_rule_ids = tuple(
        rule.rule_id for rule in PROMPT_INJECTION_RULES if rule.pattern.search(content)
    )

    return PromptInjectionDetectionResult(
        is_suspicious=bool(matched_rule_ids),
        matched_rule_ids=matched_rule_ids,
    )
