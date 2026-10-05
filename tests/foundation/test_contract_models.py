"""Generated Python contract models accept spec examples and reject invalid ones."""
import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "packages/contracts/python"))

from brandme_contracts import models  # noqa: E402

EXAMPLES = json.loads((REPO / "docs/design/brandme/contracts/contract-examples.json").read_text())


@pytest.mark.parametrize("ex", EXAMPLES["valid"], ids=lambda e: e["definition"])
def test_valid_examples_parse(ex):
    model = getattr(models, ex["definition"])
    model.model_validate(ex["value"])


# datamodel-code-generator cannot express JSON Schema if/then conditionals.
# These two invalid examples pass the pydantic models, so Python services must
# also validate wire input with jsonschema (asserted below).
CONDITIONAL_GAPS = {"DecisionResponse", "ChainOperation"}


@pytest.mark.parametrize("ex", EXAMPLES["invalid"], ids=lambda e: e["definition"])
def test_invalid_examples_rejected(ex):
    from jsonschema import Draft202012Validator, FormatChecker

    schema = json.loads((REPO / "packages/contracts/generated/domain.schema.json").read_text())
    validator = Draft202012Validator(
        {"$ref": f"#/$defs/{ex['definition']}", "$defs": schema["$defs"]}, format_checker=FormatChecker()
    )
    assert list(validator.iter_errors(ex["value"])), "jsonschema must reject"
    model = getattr(models, ex["definition"])
    if ex["definition"] in CONDITIONAL_GAPS:
        model.model_validate(ex["value"])  # documented gap: model alone accepts
    else:
        with pytest.raises(ValidationError):
            model.model_validate(ex["value"])
