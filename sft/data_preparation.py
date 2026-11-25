"""Load scenarios and prepare prompt/completion training examples."""

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from contracts.response import encode_model_response
from engine.retriever import KGRetriever
from engine.prompting import build_prompt, select_public_case


def load_scenarios(path: str | Path) -> list[dict[str, Any]]:
    """Load a JSON array or wrap one JSON object in a list."""
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    return [document] if isinstance(document, dict) else document


def build_examples(
    scenarios: list[dict[str, Any]],
    retriever: KGRetriever | None = None,
) -> list[dict[str, Any]]:
    """Build public prompts and copied JSON targets with audit metadata."""
    kg_retriever = retriever if retriever is not None else KGRetriever()
    examples = []
    for scenario in scenarios:
        public_case = select_public_case(scenario)
        retrieval = kg_retriever.retrieve(deepcopy(public_case))
        target = encode_model_response(scenario["target_response"])
        examples.append({
            "scenario_id": scenario["scenario_id"],
            "family_id": scenario.get("family_id") or scenario["scenario_id"],
            "prompt": build_prompt(public_case, retrieval),
            "completion": [{
                "role": "assistant",
                "content": json.dumps(target, ensure_ascii=False, separators=(",", ":")),
            }],
            "metadata": {
                "annotations": deepcopy(scenario.get("annotations", {})),
                "retrieved_context": deepcopy(retrieval),
            },
        })
    return examples
