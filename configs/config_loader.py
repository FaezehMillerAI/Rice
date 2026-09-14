"""
Configuration Loader Module for Rice Pathogen SALM.
Supports loading from YAML, environment variables, or CLI overrides.
"""
import os
import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

try:
    import yaml
except ImportError:
    yaml = None

@dataclass
class ModelConfig:
    base_model_name_or_path: str = "Qwen/Qwen2.5-1.5B-Instruct"
    fallback_model_name: str = "meta-llama/Llama-3.2-1B-Instruct"
    torch_dtype: str = "bfloat16"
    trust_remote_code: bool = True
    device_map: str = "auto"

@dataclass
class LoRAConfig:
    r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    bias: str = "none"
    target_modules: List[str] = field(default_factory=lambda: [
        "q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"
    ])
    task_type: str = "CAUSAL_LM"

@dataclass
class TrainingHyperparameters:
    output_dir: str = "outputs/salm_qwen1.5b_sft"
    num_train_epochs: int = 3
    per_device_train_batch_size: int = 4
    per_device_eval_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    learning_rate: float = 2e-4
    lr_scheduler_type: str = "cosine"
    warmup_ratio: float = 0.05
    weight_decay: float = 0.01
    max_grad_norm: float = 1.0
    max_seq_length: int = 2048
    response_loss_only: bool = True
    seed: int = 42

def load_training_config(config_path: str = "configs/training_sft_config.yaml") -> Dict[str, Any]:
    """Loads YAML config with fallback to default values."""
    if os.path.exists(config_path) and yaml is not None:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {
        "model": ModelConfig().__dict__,
        "lora": LoRAConfig().__dict__,
        "training": TrainingHyperparameters().__dict__
    }

if __name__ == "__main__":
    cfg = load_training_config()
    print("Loaded Config successfully:")
    print(json.dumps(cfg, indent=2))
