"""Evaluation checkpoint aliases, independent of training configuration files."""

BUILTIN_MODELS = {
    "qwen2.5-1.5b": {"id": "Qwen/Qwen2.5-1.5B-Instruct"},
    "qwen3-4b": {"id": "Qwen/Qwen3-4B-Instruct-2507"},
    "phi4-mini": {"id": "microsoft/Phi-4-mini-instruct"},
    "smollm3-3b": {
        "id": "HuggingFaceTB/SmolLM3-3B",
        "chat_template_kwargs": {"enable_thinking": False},
    },
    "qwen3.5-4b": {
        "id": "Qwen/Qwen3.5-4B",
        "chat_template_kwargs": {"enable_thinking": False},
    },
    "llama3.2-3b": {"id": "meta-llama/Llama-3.2-3B-Instruct"},
}
