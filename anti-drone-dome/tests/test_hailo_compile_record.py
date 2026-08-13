import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT / "scripts"))
from hailo_compile_record import SCHEMA, cpu_fallback_status, sha256

def test_compilation_contract_and_hash(tmp_path):
    model = tmp_path / "model.onnx"; model.write_bytes(b"model")
    assert SCHEMA == "larp.hailo-compilation.v1"
    assert len(sha256(model)) == 64
    assert cpu_fallback_status("all layers mapped")[0] == "NOT REPORTED IN COMPILER LOG"
    assert cpu_fallback_status("Layer foo: CPU fallback enabled")[0] == "YES"
