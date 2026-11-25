"""Merge adapters offline with fake HF/PEFT models; never load real weights."""

from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import eval.evaluate_unified as unified


def model_spec(*, adapter="local-adapter"):
    return {
        "adapter": adapter, "adapter_config": {}, "base_model": "local-base",
        "tokenizer": "local-tokenizer", "chat_template_kwargs": {},
    }


def arguments(*flags):
    return unified.build_parser().parse_args(["--no-warmup", *flags])


class FakeDevice:
    def __init__(self, kind="cuda"):
        self.type = kind

    def __str__(self):
        return "cuda:0" if self.type == "cuda" else self.type


class FakeTensor:
    shape = (1, 3)

    def __init__(self, dtype="torch.float32", device=None):
        self.dtype, self.device = dtype, device or FakeDevice()

    def to(self, device):
        return self


class FakeModel:
    def __init__(self, name, events, *, lora=False):
        self.name, self.events = name, events
        self.config = SimpleNamespace(max_position_embeddings=8192, _commit_hash="offline-test")
        self.generation_config = SimpleNamespace(eos_token_id=99)
        self.weights = {"model.embed_tokens.weight": FakeTensor(), "lm_head.weight": FakeTensor()}
        if lora:
            self.weights["layer.q_proj.lora_A.default.weight"] = FakeTensor()
        self.to = Mock(side_effect=self.move)
        self.eval = Mock(side_effect=lambda: events.append(("eval", name)))
        self.generate = Mock()

    @property
    def dtype(self):
        return self.weights["model.embed_tokens.weight"].dtype

    def move(self, *args, device=None, dtype=None):
        device = device if device is not None else args[0] if args else None
        self.events.append(("to", self.name, device, dtype))
        for weight in self.weights.values():
            if device is not None:
                weight.device = FakeDevice(str(device))
            if dtype is not None:
                weight.dtype = dtype
        return self

    def named_parameters(self):
        return iter(self.weights.items())

    def get_input_embeddings(self):
        return SimpleNamespace(weight=self.weights["model.embed_tokens.weight"])

    def get_output_embeddings(self):
        return SimpleNamespace(weight=self.weights["lm_head.weight"])


class FakeOutput:
    def __getitem__(self, key):
        row, position = key
        if row != 0 or position.start != 3:
            raise AssertionError("Decode only the new completion tokens")
        return [7, 8, 99]


class OfflineRuntime:
    def __init__(self, *, cuda_available=True, bf16_supported=True):
        self.events, self.inference_active = [], False
        self.base = FakeModel("base", self.events)
        self.merged = FakeModel("merged", self.events)

        class FakePeftModel(FakeModel):
            pass

        self.wrapper = FakePeftModel("wrapper", self.events, lora=True)
        self.merge_result, self.merge_error = self.merged, None

        @contextmanager
        def inference_mode():
            self.inference_active = True
            try:
                yield
            finally:
                self.inference_active = False

        self.torch = SimpleNamespace(
            float32="torch.float32", float16="torch.float16", bfloat16="torch.bfloat16",
            cuda=SimpleNamespace(
                is_available=Mock(return_value=cuda_available),
                is_bf16_supported=Mock(return_value=bf16_supported),
                reset_peak_memory_stats=Mock(), synchronize=Mock(),
                max_memory_allocated=Mock(return_value=2 * 1024**2),
            ),
            backends=SimpleNamespace(mps=SimpleNamespace(is_available=Mock(return_value=False))),
            inference_mode=inference_mode,
            autocast=Mock(side_effect=AssertionError("Ordinary merged inference must not add autocast")),
        )
        self.tokenizer = SimpleNamespace(
            pad_token=None, eos_token="EOS", pad_token_id=0, model_max_length=8192,
            apply_chat_template=Mock(return_value={
                "input_ids": FakeTensor("torch.int64"),
                "attention_mask": FakeTensor("torch.int64"),
            }), decode=Mock(return_value="UNCHANGED_GENERATED_TEXT"),
        )

        def load_base(*args, **kwargs):
            self.events.append(("load_base", kwargs["dtype"]))
            for weight in self.base.weights.values():
                weight.dtype = kwargs["dtype"]
            return self.base

        def load_adapter(model, *args, **kwargs):
            if model is not self.base:
                raise AssertionError("Load the adapter on the original base model")
            self.events.append(("load_adapter", model.dtype))
            for weight in self.wrapper.weights.values():
                weight.dtype = model.dtype
            return self.wrapper

        def merge(**kwargs):
            self.events.append(("merge", self.wrapper.dtype))
            if self.merge_error is not None:
                raise self.merge_error
            return self.merge_result

        self.wrapper.merge_and_unload = Mock(side_effect=merge)
        FakePeftModel.from_pretrained = Mock(side_effect=load_adapter)
        self.transformers = SimpleNamespace(
            AutoModelForCausalLM=SimpleNamespace(from_pretrained=Mock(side_effect=load_base)),
            AutoTokenizer=SimpleNamespace(from_pretrained=Mock(return_value=self.tokenizer)),
            BitsAndBytesConfig=Mock(), set_seed=Mock(),
        )
        self.peft = SimpleNamespace(
            PeftModel=FakePeftModel,
            prepare_model_for_kbit_training=Mock(side_effect=AssertionError("No QLoRA preparation")),
        )

    def load(self, spec=None, args=None):
        with (
            patch.object(unified, "_require_transformers_dependencies") as require,
            patch.dict("sys.modules", {
                "torch": self.torch, "transformers": self.transformers, "peft": self.peft,
            }),
        ):
            generator = unified.HFGenerator(spec or model_spec(), args or arguments())
        return generator, require


class AdapterMergeTests(unittest.TestCase):
    def test_merge_uses_fp32_original_base_then_casts_the_plain_model_once(self):
        runtime = OfflineRuntime()
        generator, require = runtime.load()
        require.assert_called_once_with(adapter=True, load_in_4bit=False)
        options = runtime.transformers.AutoModelForCausalLM.from_pretrained.call_args.kwargs
        self.assertEqual(options["dtype"], runtime.torch.float32)
        self.assertNotIn("quantization_config", options)
        self.assertNotIn("device_map", options)
        runtime.transformers.BitsAndBytesConfig.assert_not_called()
        runtime.peft.prepare_model_for_kbit_training.assert_not_called()
        runtime.peft.PeftModel.from_pretrained.assert_called_once_with(
            runtime.base, "local-adapter", is_trainable=False,
        )
        runtime.wrapper.merge_and_unload.assert_called_once_with(safe_merge=True)
        self.assertEqual(runtime.events, [
            ("load_base", "torch.float32"), ("load_adapter", "torch.float32"),
            ("merge", "torch.float32"), ("to", "merged", "cuda", "torch.bfloat16"),
            ("eval", "merged"),
        ])
        self.assertIs(generator.model, runtime.merged)
        self.assertNotIsInstance(generator.model, runtime.peft.PeftModel)
        self.assertFalse(any("lora_" in name for name, _ in generator.model.named_parameters()))
        runtime.base.to.assert_not_called()
        runtime.wrapper.to.assert_not_called()
        runtime.wrapper.eval.assert_not_called()

    def test_default_inference_dtype_matches_base_across_devices(self):
        for device, supported, expected in (
            ("cpu", True, "torch.float32"), ("cuda", True, "torch.bfloat16"),
            ("cuda", False, "torch.float16"), ("mps", True, "torch.float16"),
        ):
            with self.subTest(device=device, bf16=supported):
                base, tuned = OfflineRuntime(bf16_supported=supported), OfflineRuntime(bf16_supported=supported)
                plain, _ = base.load(model_spec(adapter=None), arguments("--device", device))
                merged, _ = tuned.load(args=arguments("--device", device))
                self.assertEqual(plain.runtime_metadata["compute_dtype"], expected)
                self.assertEqual(merged.runtime_metadata["compute_dtype"], expected)
                self.assertEqual(plain.model.dtype, merged.model.dtype)
                self.assertEqual(base.transformers.AutoModelForCausalLM.from_pretrained.call_args.kwargs["dtype"], expected)
                self.assertEqual(tuned.transformers.AutoModelForCausalLM.from_pretrained.call_args.kwargs["dtype"], "torch.float32")
                tuned.merged.to.assert_called_once_with(device=device, dtype=expected)

    def test_explicit_inference_dtype_is_applied_only_after_fp32_merge(self):
        for dtype in ("float32", "float16", "bfloat16"):
            with self.subTest(dtype=dtype):
                runtime = OfflineRuntime()
                generator, _ = runtime.load(args=arguments("--device", "cpu", "--dtype", dtype))
                self.assertEqual(runtime.events[0], ("load_base", "torch.float32"))
                runtime.merged.to.assert_called_once_with(device="cpu", dtype="torch." + dtype)
                self.assertEqual(generator.runtime_metadata["compute_dtype"], "torch." + dtype)

    def test_four_bit_adapter_request_fails_before_dependency_checks_or_file_loading(self):
        runtime = OfflineRuntime()
        with (
            patch.object(unified, "_require_transformers_dependencies",
                         side_effect=AssertionError("Reject the conflicting flag before imports")) as require,
            patch.dict("sys.modules", {
                "torch": runtime.torch, "transformers": runtime.transformers, "peft": runtime.peft,
            }),
        ):
            with self.assertRaisesRegex(ValueError, "omit --load-in-4bit"):
                unified.HFGenerator(model_spec(), arguments("--load-in-4bit"))
        require.assert_not_called()
        runtime.transformers.AutoTokenizer.from_pretrained.assert_not_called()
        runtime.transformers.AutoModelForCausalLM.from_pretrained.assert_not_called()

    def test_failed_safe_merge_does_not_fall_back_to_peft_inference(self):
        runtime = OfflineRuntime()
        runtime.merge_error = ValueError("nonfinite adapter delta")
        with self.assertRaisesRegex(RuntimeError, "LoRA merge failed.*nonfinite adapter delta") as raised:
            runtime.load()
        self.assertIs(raised.exception.__cause__, runtime.merge_error)
        runtime.wrapper.merge_and_unload.assert_called_once_with(safe_merge=True)
        for model in (runtime.base, runtime.wrapper, runtime.merged):
            model.to.assert_not_called()
            model.eval.assert_not_called()
            model.generate.assert_not_called()

    def test_merge_rejects_a_retained_peft_wrapper_or_leftover_lora_parameters(self):
        for retained_wrapper in (True, False):
            with self.subTest(retained_wrapper=retained_wrapper):
                runtime = OfflineRuntime()
                runtime.merge_result = runtime.wrapper if retained_wrapper else FakeModel("leftover", runtime.events, lora=True)
                with self.assertRaisesRegex(RuntimeError, "plain model.*adapter layers removed"):
                    runtime.load()
                runtime.wrapper.to.assert_not_called()
                runtime.wrapper.eval.assert_not_called()
                runtime.merge_result.to.assert_not_called()
                runtime.merge_result.eval.assert_not_called()

    def test_metadata_distinguishes_fp32_merge_from_ordinary_inference_dtype(self):
        runtime = OfflineRuntime()
        generator, _ = runtime.load()
        meta = generator.runtime_metadata
        self.assertEqual(meta["profile"], "merged_lora")
        self.assertTrue(meta["adapter_merged"])
        self.assertEqual(meta["merge_method"], "merge_and_unload")
        self.assertTrue(meta["merge_safe"])
        self.assertEqual(meta["merge_dtype"], "torch.float32")
        self.assertEqual(meta["compute_dtype"], "torch.bfloat16")
        self.assertIsInstance(meta["merge_s"], float)
        self.assertGreaterEqual(meta["merge_s"], 0)
        self.assertFalse(meta["load_in_4bit"])
        self.assertIsNone(meta["autocast_dtype"])
        self.assertEqual(meta["model_class"], type(runtime.merged).__name__)

    def test_plain_base_metadata_does_not_claim_an_adapter_merge(self):
        runtime = OfflineRuntime()
        generator, _ = runtime.load(model_spec(adapter=None))
        meta = generator.runtime_metadata
        self.assertEqual(meta["profile"], "explicit_inference")
        self.assertFalse(meta["adapter_merged"])
        self.assertFalse(meta["merge_safe"])
        self.assertIsNone(meta["merge_method"])
        self.assertIsNone(meta["merge_dtype"])
        self.assertIsNone(meta["merge_s"])
        runtime.peft.PeftModel.from_pretrained.assert_not_called()
        runtime.wrapper.merge_and_unload.assert_not_called()

    def test_generate_calls_only_plain_model_with_no_extra_autocast(self):
        for adapter in (None, "local-adapter"):
            with self.subTest(adapter=adapter):
                runtime = OfflineRuntime()
                generator, _ = runtime.load(model_spec(adapter=adapter))

                def generate(**kwargs):
                    self.assertTrue(runtime.inference_active)
                    return FakeOutput()

                generator.model.generate.side_effect = generate
                result = generator.generate([{"role": "user", "content": "Offline test"}], max_new_tokens=8)
                self.assertEqual(result["raw_output"], "UNCHANGED_GENERATED_TEXT")
                self.assertEqual(result["generated_tokens"], 3)
                self.assertFalse(result["output_budget_exhausted"])
                self.assertFalse(runtime.inference_active)
                runtime.torch.autocast.assert_not_called()
                runtime.wrapper.generate.assert_not_called()

    def test_saved_training_quantization_is_provenance_and_does_not_select_a_profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / "training-run"
            checkpoint = run / "checkpoint-10"
            checkpoint.mkdir(parents=True)
            (checkpoint / "adapter_config.json").write_text(json.dumps({
                "base_model_name_or_path": "Qwen/Qwen2.5-1.5B-Instruct", "peft_type": "LORA",
            }), encoding="utf-8")
            (run / "run_config.json").write_text(json.dumps({
                "quantization": {"load_in_4bit": True, "bnb_4bit_quant_type": "nf4"},
                "training": {"max_seq_length": 3072},
            }), encoding="utf-8")
            spec = unified.resolve_model_spec(None, str(checkpoint))
            self.assertNotIn("training_quantization", spec)
            self.assertEqual(spec["training_config_path"], str((run / "run_config.json").resolve()))
            self.assertEqual(len(spec["training_config_sha256"]), 64)
            runtime = OfflineRuntime()
            generator, _ = runtime.load(spec)
            self.assertEqual(generator.runtime_metadata["profile"], "merged_lora")
            runtime.transformers.BitsAndBytesConfig.assert_not_called()


if __name__ == "__main__":
    unittest.main()
