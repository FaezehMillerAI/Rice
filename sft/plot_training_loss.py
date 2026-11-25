"""Plot logged training and validation loss from a Trainer experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def find_latest_state(run_path: Path) -> tuple[Path, dict]:
    """Use the supplied state/checkpoint, or the run's furthest saved step."""
    run_path = run_path.expanduser().resolve()
    if run_path.is_file():
        candidates = [run_path]
    else:
        candidates = [run_path / "trainer_state.json", *run_path.glob("checkpoint-*/trainer_state.json")]
    loaded = [(path, json.loads(path.read_text(encoding="utf-8"))) for path in candidates if path.is_file()]
    return max(loaded, key=lambda item: (item[1]["global_step"], item[0].stat().st_mtime_ns))


def experiment_directory(run_path: Path) -> Path:
    directory = run_path.expanduser().resolve()
    if directory.is_file():
        directory = directory.parent
    return directory.parent if directory.name.startswith("checkpoint-") else directory


def default_title(directory: Path, state_path: Path) -> str:
    for path in (directory / "adapter_config.json", state_path.parent / "adapter_config.json", directory / "run_config.json"):
        if path.is_file():
            metadata = json.loads(path.read_text(encoding="utf-8"))
            model_id = (
                metadata["base_model_name_or_path"] if path.name == "adapter_config.json"
                else metadata["model"]["base_model_name_or_path"]
            )
            return f"{model_id.rstrip('/').split('/')[-1]}\n{directory.name}"
    return f"SFT training loss\n{directory.name}"


def extract_series(history: list[dict], value_key: str, x_axis: str) -> tuple[list, list]:
    points = sorted((row[x_axis], row[value_key]) for row in history if x_axis in row and value_key in row)
    return [point[0] for point in points], [point[1] for point in points]


def plot_losses(state: dict, output_path: Path, x_axis: str, title: str, dpi: int) -> tuple[int, int]:
    train_x, train_loss = extract_series(state["log_history"], "loss", x_axis)
    eval_x, eval_loss = extract_series(state["log_history"], "eval_loss", x_axis)
    figure, axis = plt.subplots(figsize=(10, 6))
    if train_loss:
        axis.plot(train_x, train_loss, color="#2563eb", linewidth=2, label="Train loss")
    if eval_loss:
        axis.plot(eval_x, eval_loss, color="#dc2626", linewidth=2, marker="o", markersize=4, label="Validation loss")
        best = min(range(len(eval_loss)), key=eval_loss.__getitem__)
        axis.scatter(
            eval_x[best], eval_loss[best], color="#f59e0b", marker="*", s=150,
            zorder=3, label=f"Best validation loss: {eval_loss[best]:.4f}",
        )
    axis.set_title(title)
    axis.set_xlabel("Optimizer step" if x_axis == "step" else "Epoch")
    axis.set_ylabel("Loss")
    axis.grid(True, alpha=0.25)
    if train_loss or eval_loss:
        axis.legend()
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(figure)
    return len(train_loss), len(eval_loss)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot logged SFT loss from a run, checkpoint, or trainer_state.json")
    parser.add_argument("--run-dir", type=Path, required=True, help="Experiment directory, checkpoint, or Trainer state file")
    parser.add_argument("--output-path", type=Path, help="Default: experiment directory/training_loss.png")
    parser.add_argument("--x-axis", choices=("step", "epoch"), default="step")
    parser.add_argument("--title", help="Default: model display name and experiment directory name")
    parser.add_argument("--dpi", type=int, default=300)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_path, state = find_latest_state(args.run_dir)
    directory = experiment_directory(args.run_dir)
    output = (args.output_path or directory / "training_loss.png").expanduser().resolve()
    title = args.title or default_title(directory, state_path)
    train_count, eval_count = plot_losses(state, output, args.x_axis, title, args.dpi)
    print(f"Trainer state: {state_path}")
    print(f"Title: {title.replace(chr(10), ' | ')}")
    print(f"Points: {train_count} train / {eval_count} validation")
    print(f"Figure saved to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
