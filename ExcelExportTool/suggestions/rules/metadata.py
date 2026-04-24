"""Rule metadata schema for suggestion rules."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RuleMetadata:
    rule_id: str
    name: str
    category: str
    target: str
    output: str
    description: str

    def to_dict(self) -> dict[str, str]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "category": self.category,
            "target": self.target,
            "output": self.output,
            "description": self.description,
        }
