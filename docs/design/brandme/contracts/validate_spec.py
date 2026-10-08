"""Validate the specification package; this is not an application test suite."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from urllib.parse import unquote

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError as exc:
    raise SystemExit("Install contracts/requirements.txt in your Python environment first.") from exc


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def load(name: str):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    json_files = sorted(HERE.glob("*.json"))
    for path in json_files:
        json.loads(path.read_text(encoding="utf-8"))

    schema = load("domain.schema.json")
    Draft202012Validator.check_schema(schema)
    examples = load("contract-examples.json")
    for expected_valid, key in [(True, "valid"), (False, "invalid")]:
        for index, example in enumerate(examples[key]):
            definition = example["definition"]
            require(definition in schema["$defs"], f"Unknown definition {definition}")
            selected = {
                "$schema": schema["$schema"], "$defs": schema["$defs"],
                "$ref": "#/$defs/" + definition,
            }
            errors = list(Draft202012Validator(selected, format_checker=FormatChecker()).iter_errors(example["value"]))
            require(bool(errors) != expected_valid,
                    f"{key}[{index}] {definition}: unexpected validation result: {[e.message for e in errors]}")

    catalog = load("acceptance-catalog.json")
    requirements = catalog["requirements"]
    ids = [item["id"] for item in requirements]
    require(len(ids) == len(set(ids)), "Duplicate acceptance ID")
    require(len(ids) == 150, "Update documented requirement count after deliberate catalog change")
    methods = {"integration", "security", "inspection", "browser", "usability", "performance", "visual",
               "asset", "accessibility", "provider", "device", "contract", "network", "operations"}
    for item in requirements:
        require(bool(re.fullmatch(r"BM-[A-Z]+-\d{3}", item["id"])), "Invalid acceptance ID")
        require(item["stage"] in {f"W{i:02}" for i in range(12)}, f"Invalid stage: {item['id']}")
        require(item["verification"] in methods, f"Invalid evidence method: {item['id']}")
        require(item["priority"] == "MUST" and item["initial_status"] == "not_run", "Requirements cannot claim execution")
        require(len(item["procedure"]) > 15 and len(item["pass_condition"]) > 20, "Acceptance condition too vague")
        require((HERE / item["source"]).is_file(), f"Missing source: {item['source']}")

    sources = (ROOT / "07-repository-audit-sources.md").read_text()
    source_ids = set(re.findall(r"^### (S\d{2})\b", sources, re.M))
    require(len(source_ids) == 27, "Source catalog must contain S01–S27")
    markdown_files = sorted(ROOT.rglob("*.md"))
    links = 0
    for path in markdown_files:
        body = path.read_text(encoding="utf-8")
        for source_id in re.findall(r"\b(S\d{2})\b", body):
            require(source_id in source_ids, f"Unknown source {source_id} in {path.name}")
        for target in re.findall(r"\[[^\]\n]+\]\(([^)\s]+)\)", body):
            if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I) or target.startswith("#"):
                continue
            local = unquote(target.split("#", 1)[0])
            require((path.parent / local).exists(), f"Broken local link in {path.name}: {target}")
            links += 1

    tokens = load("design-tokens.json")
    scenario = load("demo-scenario.json")
    rewards = load("reward-rules.json")
    require(len(rewards["rules"]) == 8, "Expected eight initial reward rules")
    require(len({rule["id"] for rule in rewards["rules"]}) == 8, "Duplicate reward rule")
    require(rewards["window_timezone"] == "UTC", "Reward cap window must be explicit")
    response_rule = next(rule for rule in rewards["rules"] if rule["id"] == "friend_decision_response")
    require(response_rule["points"] == 10 and response_rule["cap_points"] == 100, "Response reward drift")
    require(set(response_rule["equal_choice_eligibility"]) == {"yes", "pass", "alternative"}, "Biased voting reward")
    product_chapter = (ROOT / "01-product-experience.md").read_text()
    visual_chapter = (ROOT / "02-visual-motion-spatial.md").read_text()
    axes = [axis["key"] for axis in scenario["persona_axes"]]
    require(len(axes) == len(set(axes)) == 12, "Expected twelve unique axes")
    require(set(axes) == set(schema["$defs"]["AxisKey"]["enum"]), "Axis vocabulary drift")
    for axis in axes:
        require(f"`{axis}`" in product_chapter, f"Missing prose axis {axis}")
    for pair in tokens["color"].values():
        for color in pair.values():
            require(color in visual_chapter, f"Color token drift: {color}")
    segments = tokens["motion"]["closet_add_segments_ms"]
    require(segments == sorted(set(segments)) and segments[0] == 0 and segments[-1] == 900,
            "Invalid garment animation timeline")
    require(sum(b-a for a, b in zip(segments, segments[1:])) == tokens["motion"]["closet_add_ms"],
            "Animation duration mismatch")
    require(len(scenario["rooms"]) == 3 and len(scenario["products"]) == 6, "Demo asset scope drift")
    for room in scenario["rooms"]:
        require(room["name"] in visual_chapter, f"Undocumented room {room['name']}")
    for example in examples["valid"]:
        if example["definition"] == "CheckoutQuote":
            q = example["value"]
            amounts = [q[k] for k in ["subtotal", "tax", "shipping", "discount", "total"]]
            require(len({m["currency"] for m in amounts}) == 1, "Mixed quote currency")
            require(sum(int(line["line_total"]["amount_minor"]) for line in q["lines"]) == int(q["subtotal"]["amount_minor"]),
                    "Quote line arithmetic drift")
            calculated = sum(int(q[k]["amount_minor"]) for k in ["subtotal", "tax", "shipping"]) - int(q["discount"]["amount_minor"])
            require(calculated == int(q["total"]["amount_minor"]), "Quote total arithmetic drift")
        if example["definition"] == "ClosetPlacement":
            rotation = example["value"]["rotation_quaternion"]
            require(math.isclose(sum(x*x for x in rotation), 1, abs_tol=1e-6), "Example quaternion not normalized")

    words = sum(len(path.read_text().split()) for path in markdown_files)
    print(f"PASS: {len(json_files)} JSON files; {len(schema['$defs'])} definitions; "
          f"{len(examples['valid'])} positive and {len(examples['invalid'])} negative examples.")
    print(f"PASS: {len(requirements)} unique acceptance criteria; {links} local links; "
          f"{len(source_ids)} source IDs; token/axis/room/timeline/quote consistency.")
    print(f"Documentation: {len(markdown_files)} Markdown files, approximately {words:,} words.")
    print("Scope: documentation validation only; application/provider/network tests were not run.")


if __name__ == "__main__":
    main()
