"""Deterministic output guardrails for unsafe incident-assistant recommendations."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SafetyValidationResult:
    """The deterministic result of checking an answer for prohibited actions."""

    is_safe: bool
    errors: tuple[str, ...]


@dataclass(frozen=True)
class ProhibitedOutputRule:
    """One unsafe recommendation pattern that the application must fail closed on."""

    pattern: re.Pattern[str]
    error: str


PROHIBITED_OUTPUT_RULES = (
    ProhibitedOutputRule(
        pattern=re.compile(
            r"\b(?:restart|reboot)\s+(?:the\s+)?(?:production|prod)\b",
            re.IGNORECASE,
        ),
        error="Answer must not recommend restarting production.",
    ),
    ProhibitedOutputRule(
        pattern=re.compile(
            r"\b(?:rollback|roll back)\s+(?:the\s+)?(?:production\s+)?"
            r"(?:deployment|release)\b",
            re.IGNORECASE,
        ),
        error="Answer must not recommend rolling back a deployment.",
    ),
    ProhibitedOutputRule(
        pattern=re.compile(
            r"\b(?:expose|reveal|print|show)\s+(?:the\s+)?"
            r"(?:aws\s+)?(?:credentials?|secrets?)\b",
            re.IGNORECASE,
        ),
        error="Answer must not disclose credentials or secrets.",
    ),
    ProhibitedOutputRule(
        pattern=re.compile(
            r"\b(?:run|execute)\s+(?:the\s+)?(?:command\s+)?"
            r"(?:rm\s+-rf|terraform\s+destroy)\b",
            re.IGNORECASE,
        ),
        error="Answer must not recommend a destructive command.",
    ),
)

# A safety statement such as "Do not restart production" is permitted.
NEGATED_INSTRUCTION_PATTERN = re.compile(
    r"\b(?:do not|don't|never|must not|should not|avoid)\s*$",
    re.IGNORECASE,
)


def validate_answer_safety(answer_text: str) -> SafetyValidationResult:
    """Reject explicit unsafe operational recommendations before they reach a user."""
    normalized_answer = answer_text.strip()

    if not normalized_answer:
        return SafetyValidationResult(
            is_safe=False,
            errors=("Answer must not be empty.",),
        )

    errors: list[str] = []

    for rule in PROHIBITED_OUTPUT_RULES:
        for match in rule.pattern.finditer(normalized_answer):
            if _is_negated_instruction(normalized_answer, match.start()):
                continue

            errors.append(rule.error)
            break

    return SafetyValidationResult(
        is_safe=not errors,
        errors=tuple(errors),
    )


def _is_negated_instruction(answer_text: str, match_start: int) -> bool:
    """Allow safety guidance that explicitly tells the user not to take an action."""
    preceding_text = answer_text[max(0, match_start - 40) : match_start]
    return bool(NEGATED_INSTRUCTION_PATTERN.search(preceding_text))
