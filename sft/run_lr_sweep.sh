#!/usr/bin/env bash
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

models=(
  qwen2.5-1.5b
  qwen3-4b
  phi4-mini
  smollm3-3b
  qwen3.5-4b
  llama3.2-3b
)

configs=(
  configs/sft/training_config_lr5e-4.yaml
  configs/sft/training_config_lr1e-3.yaml
)

mkdir -p outputs/sft/logs
exec 9>outputs/sft/logs/lr_sweep.lock
if ! flock -n 9; then
  echo "Another learning-rate sweep queue is already active." >&2
  exit 2
fi

timestamp() {
  date '+%Y-%m-%d %H:%M:%S %Z'
}

wait_for_pid="${WAIT_FOR_PID:-}"
if [[ -n "$wait_for_pid" ]]; then
  if [[ ! "$wait_for_pid" =~ ^[1-9][0-9]*$ ]]; then
    echo "WAIT_FOR_PID must be a positive integer, got: $wait_for_pid" >&2
    exit 2
  fi

  echo "[$(timestamp)] Waiting for baseline queue PID $wait_for_pid to finish."
  while kill -0 "$wait_for_pid" 2>/dev/null; do
    predecessor_command="$(ps -p "$wait_for_pid" -o args= 2>/dev/null || true)"
    if [[ -z "$predecessor_command" ]]; then
      break
    fi
    if [[ "$predecessor_command" != *"run_all_models.sh"* ]]; then
      echo "[$(timestamp)] PID $wait_for_pid no longer belongs to run_all_models.sh; continuing."
      break
    fi
    sleep 30
  done
  echo "[$(timestamp)] Baseline queue finished; starting learning-rate sweep."
fi

resolve_output_dir() {
  uv run --locked python -c \
    'import sys; from sft.trainer import load_config, resolve_output_paths; print(resolve_output_paths(load_config(sys.argv[1], sys.argv[2]))["directory"])' \
    "$1" "$2"
}

echo "[$(timestamp)] Preflighting all learning-rate sweep output directories."
for config in "${configs[@]}"; do
  for model in "${models[@]}"; do
    output_dir="$(resolve_output_dir "$config" "$model")" || {
      echo "Unable to resolve output directory for $config / $model" >&2
      exit 2
    }
    if [[ -e "$output_dir" ]]; then
      echo "Refusing to reuse existing output path: $output_dir" >&2
      exit 3
    fi
  done
done

failures=()
for config in "${configs[@]}"; do
  echo
  echo "[$(timestamp)] Starting configuration: $config"
  for model in "${models[@]}"; do
    output_dir="$(resolve_output_dir "$config" "$model")"
    echo
    echo "[$(timestamp)] START model=$model output=$output_dir"
    if uv run --locked python -u -m sft.trainer --config "$config" --model "$model"; then
      echo "[$(timestamp)] DONE model=$model output=$output_dir"
    else
      status=$?
      failures+=("$config | $model | exit=$status")
      echo "[$(timestamp)] FAILED model=$model exit=$status; continuing with the queue." >&2
    fi
  done
done

echo
if ((${#failures[@]})); then
  echo "[$(timestamp)] Sweep completed with ${#failures[@]} failure(s):" >&2
  printf '  %s\n' "${failures[@]}" >&2
  exit 1
fi

echo "[$(timestamp)] Sweep completed successfully: all 12 training runs finished."
