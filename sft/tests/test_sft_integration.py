"""Offline smoke test of the installed TRL collator and one LoRA update."""

import importlib.util
import math
import tempfile
import unittest

from sft.tests.test_trainer import CharacterChatTokenizer, example
from sft.trainer import tokenize_examples


HAS_TRAINING_DEPS = all(
    importlib.util.find_spec(package) is not None
    for package in ("torch", "transformers", "datasets", "peft", "trl", "tokenizers")
)


@unittest.skipUnless(HAS_TRAINING_DEPS, "optional training dependencies are not installed")
class SFTIntegrationTests(unittest.TestCase):
    def test_pretokenized_labels_survive_trl_and_train_one_step(self):
        import torch
        from datasets import Dataset
        from peft import LoraConfig, TaskType, get_peft_model
        from tokenizers import Tokenizer
        from tokenizers.models import WordLevel
        from transformers import LlamaConfig, LlamaForCausalLM, PreTrainedTokenizerFast
        from trl import SFTConfig, SFTTrainer

        rows, _ = tokenize_examples([example()], CharacterChatTokenizer(), 2048)
        tokenizer_backend = Tokenizer(WordLevel(
            {"[PAD]": 0, "[EOS]": 1, "[UNK]": 2, **{f"token_{i}": i for i in range(3, 128)}},
            unk_token="[UNK]",
        ))
        tokenizer = PreTrainedTokenizerFast(
            tokenizer_object=tokenizer_backend, pad_token="[PAD]", eos_token="[EOS]", unk_token="[UNK]"
        )
        model = LlamaForCausalLM(LlamaConfig(
            vocab_size=128, hidden_size=16, intermediate_size=32,
            num_hidden_layers=1, num_attention_heads=2, num_key_value_heads=2,
            max_position_embeddings=2048, pad_token_id=0, eos_token_id=1,
        ))
        model = get_peft_model(model, LoraConfig(
            r=2, lora_alpha=4, target_modules=["q_proj", "v_proj"], task_type=TaskType.CAUSAL_LM
        ))
        initial = {
            name: parameter.detach().clone()
            for name, parameter in model.named_parameters() if parameter.requires_grad
        }
        with tempfile.TemporaryDirectory() as output_dir:
            settings = SFTConfig(
                output_dir=output_dir, max_steps=1, max_length=2048,
                per_device_train_batch_size=1, learning_rate=1e-3,
                completion_only_loss=True, packing=False, use_cpu=True,
                gradient_checkpointing=False, bf16=False, fp16=False,
                save_strategy="no", eval_strategy="no", logging_strategy="no",
                report_to="none", disable_tqdm=True,
            )
            trainer = SFTTrainer(
                model=model, args=settings, train_dataset=Dataset.from_list(rows),
                processing_class=tokenizer,
            )
            processed = trainer.train_dataset[0]
            self.assertEqual(processed["labels"], rows[0]["labels"])
            batch = trainer.data_collator([processed])
            self.assertEqual(batch["labels"][0].tolist(), rows[0]["labels"])
            self.assertTrue(any(label == -100 for label in processed["labels"]))
            self.assertTrue(any(label != -100 for label in processed["labels"]))
            result = trainer.train()
        self.assertEqual(result.global_step, 1)
        self.assertTrue(math.isfinite(result.training_loss))
        self.assertTrue(any(
            not torch.equal(initial[name], parameter.detach())
            for name, parameter in model.named_parameters() if name in initial
        ), "at least one LoRA parameter must actually be updated")


if __name__ == "__main__":
    unittest.main()
