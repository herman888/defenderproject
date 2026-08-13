"""Record a Hailo Dataflow Compiler attempt, including the complete compiler log."""
from __future__ import annotations
import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_common import NOT_MEASURED, metadata, write_artifact

SCHEMA = "larp.hailo-compilation.v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()


def cpu_fallback_status(log: str) -> tuple[str, list[str]]:
    """Report only an explicit CPU-fallback marker; silence is not evidence of no fallback."""
    mentions = [line for line in log.splitlines()
                if "cpu" in line.lower() and "fallback" in line.lower()]
    return ("YES", mentions) if mentions else ("NOT REPORTED IN COMPILER LOG", [])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="ONNX input accepted by the installed DFC")
    parser.add_argument("--input-width", type=int, default=640); parser.add_argument("--input-height", type=int, default=640)
    parser.add_argument("--quantization", default="int8"); parser.add_argument("--command", nargs="+", help="Exact DFC command to execute")
    args = parser.parse_args(); root = Path(__file__).resolve().parent.parent; model = Path(args.model)
    output = {"command": args.command or [], "returncode": None, "stdout": "", "stderr": "NOT RUN"}
    status, fallback = "BLOCKED", NOT_MEASURED
    if not model.is_file(): output["stderr"] = f"model not found: {model}"
    elif not args.command: output["stderr"] = "no Dataflow Compiler command supplied"
    elif shutil.which(args.command[0]) is None: output["stderr"] = f"compiler executable unavailable: {args.command[0]}"
    else:
        completed = subprocess.run(args.command, text=True, capture_output=True)
        output = {"command": args.command, "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
        status = "COMPILED" if completed.returncode == 0 else "FAILED"
        fallback, fallback_mentions = cpu_fallback_status(completed.stdout + completed.stderr)
    if status != "COMPILED":
        fallback_mentions = []
    record = {"schema": SCHEMA, **metadata(root, {"model": str(model), "input_resolution": [args.input_width, args.input_height], "quantization": args.quantization}),
              "measurement_status": status, "model_sha256": sha256(model) if model.is_file() else NOT_MEASURED,
              "compiler": output, "cpu_fallback": fallback, "cpu_fallback_log_lines": fallback_mentions,
              "target_device_inference_latency": NOT_MEASURED, "npu_utilization": NOT_MEASURED,
              "thermal": NOT_MEASURED, "power": NOT_MEASURED}
    print(write_artifact(root, "hailo", "compile", record)); return 0 if status == "COMPILED" else 2


if __name__ == "__main__": raise SystemExit(main())
