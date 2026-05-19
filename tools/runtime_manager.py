import argparse
import importlib
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from importlib import metadata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
INSTALL_LOG = LOG_DIR / "runtime_install.log"
CHECK_LOG = LOG_DIR / "runtime_check.log"
PROFILE_FILE = ROOT / ".runtime_profile.json"
REQ_DIR = ROOT / "requirements"

PROFILE_CHOICES = ["auto", "nvidia_compat_cu118", "nvidia_blackwell_cu128", "cpu_fallback"]
RUNTIME_PACKAGES = [
    "torch",
    "torchvision",
    "torchaudio",
    "numpy",
    "opencv-python",
    "opencv-contrib-python",
    "opencv-python-headless",
    "transformers",
    "tokenizers",
    "huggingface_hub",
    "accelerate",
    "diffusers",
    "safetensors",
]

COMPAT_CORE = ["numpy==1.26.4", "opencv-python==4.10.0.84"]
COMPAT_TORCH = ["torch==2.4.1+cu118", "torchvision==0.19.1+cu118", "torchaudio==2.4.1+cu118"]
COMPAT_HF = [
    "transformers==4.46.3",
    "tokenizers==0.20.3",
    "huggingface_hub==0.26.5",
    "accelerate==0.34.2",
    "diffusers==0.31.0",
    "safetensors==0.7.0",
]


def setup_logger(name, path):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    file_handler = logging.FileHandler(path, mode="a", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


install_logger = setup_logger("runtime_install", INSTALL_LOG)
check_logger = setup_logger("runtime_check", CHECK_LOG)


def parse_version_tuple(value):
    numbers = []
    for part in str(value).split("."):
        match = re.match(r"(\d+)", part)
        if not match:
            break
        numbers.append(int(match.group(1)))
    return tuple(numbers)


def package_version(dist_name):
    try:
        version = metadata.version(dist_name)
        return version or "not installed"
    except metadata.PackageNotFoundError:
        return "not installed"


def collect_versions():
    return {
        "torch": package_version("torch"),
        "torchvision": package_version("torchvision"),
        "torchaudio": package_version("torchaudio"),
        "numpy": package_version("numpy"),
        "opencv": package_version("opencv-python"),
        "transformers": package_version("transformers"),
        "tokenizers": package_version("tokenizers"),
        "huggingface_hub": package_version("huggingface-hub"),
        "accelerate": package_version("accelerate"),
        "diffusers": package_version("diffusers"),
        "safetensors": package_version("safetensors"),
    }


def log_versions(logger, label):
    logger.info("%s package versions: %s", label, json.dumps(collect_versions(), sort_keys=True))


def fallback_compute_capability(gpu_name):
    name = gpu_name.lower()
    if "rtx 50" in name or any(model in name for model in ("5070", "5080", "5090")) or "blackwell" in name:
        return 12.0
    if "rtx 40" in name or re.search(r"\b4\d{3}\b", name):
        return 8.9
    if "rtx 30" in name or re.search(r"\b3\d{3}\b", name):
        return 8.6
    if "rtx 20" in name or re.search(r"\b2\d{3}\b", name):
        return 7.5
    if "gtx 16" in name:
        return 7.5
    if "gtx 10" in name:
        return 6.1
    return None


def run_command(command, logger, cwd=ROOT, check=False):
    logger.info("Running command: %s", " ".join(str(part) for part in command))
    result = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True)
    if result.stdout:
        logger.info("stdout:\n%s", result.stdout.rstrip())
    if result.stderr:
        logger.info("stderr:\n%s", result.stderr.rstrip())
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {' '.join(command)}")
    return result


def run_pip(args, logger, check=True):
    return run_command([sys.executable, "-m", "pip"] + args, logger, check=check)


def query_nvidia_smi(query_fields):
    return subprocess.run(
        ["nvidia-smi", f"--query-gpu={query_fields}", "--format=csv,noheader"],
        capture_output=True,
        text=True,
    )


def read_nvidia_header_cuda_version():
    try:
        result = subprocess.run(["nvidia-smi"], capture_output=True, text=True)
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    match = re.search(r"CUDA Version:\s*([0-9.]+)", result.stdout)
    return match.group(1) if match else None


def detect_environment():
    env = {
        "os": platform.system(),
        "platform": sys.platform,
        "python_version": platform.python_version(),
        "venv_path": sys.prefix,
        "pip_version": "unknown",
        "nvidia_smi_available": shutil.which("nvidia-smi") is not None,
        "gpu_name": None,
        "vram": None,
        "driver_version": None,
        "cuda_version": None,
        "compute_capability": None,
        "gpus": [],
        "warnings": [],
    }

    pip_result = run_command([sys.executable, "-m", "pip", "--version"], check_logger, check=False)
    if pip_result.returncode == 0 and pip_result.stdout:
        parts = pip_result.stdout.split()
        if len(parts) >= 2:
            env["pip_version"] = parts[1]

    if not env["nvidia_smi_available"]:
        return env

    fields = ["name", "compute_cap", "driver_version", "cuda_version", "memory.total"]
    result = query_nvidia_smi(",".join(fields))
    if result.returncode != 0:
        env["warnings"].append(result.stderr.strip())
        fields = ["name", "driver_version", "memory.total"]
        result = query_nvidia_smi(",".join(fields))

    if result.returncode != 0:
        env["warnings"].append(result.stderr.strip())
        return env

    header_cuda = read_nvidia_header_cuda_version()
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < len(fields):
            continue

        values = dict(zip(fields, parts))
        gpu_name = values.get("name")
        cc = None
        if values.get("compute_cap"):
            try:
                cc = float(values["compute_cap"])
            except ValueError:
                cc = None
        if cc is None and gpu_name:
            cc = fallback_compute_capability(gpu_name)

        gpu = {
            "name": gpu_name,
            "vram": values.get("memory.total"),
            "driver_version": values.get("driver_version"),
            "cuda_version": values.get("cuda_version") or header_cuda,
            "compute_capability": cc,
        }
        env["gpus"].append(gpu)

        if env["gpu_name"] is None:
            env["gpu_name"] = gpu["name"]
            env["vram"] = gpu["vram"]
            env["driver_version"] = gpu["driver_version"]
            env["cuda_version"] = gpu["cuda_version"]

        if cc is not None and (env["compute_capability"] is None or cc > env["compute_capability"]):
            env["compute_capability"] = cc

    return env


def choose_runtime_profile(env):
    if not env.get("nvidia_smi_available") or not env.get("gpus"):
        return "cpu_fallback"

    cc = env.get("compute_capability")
    if cc is None:
        return "nvidia_compat_cu118"
    if cc >= 12.0:
        return "nvidia_blackwell_cu128"
    if cc >= 6.0:
        return "nvidia_compat_cu118"
    return "cpu_fallback"


def load_profile_state():
    if not PROFILE_FILE.exists():
        return None
    try:
        return json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def uninstall_runtime_packages():
    log_versions(install_logger, "Before uninstall")
    run_pip(["uninstall", "-y"] + RUNTIME_PACKAGES, install_logger, check=False)


def install_base_requirements():
    base_file = REQ_DIR / "base.txt"
    if base_file.exists():
        run_pip(["install", "-r", str(base_file)], install_logger)
    else:
        run_pip(["install", "-r", "requirements.txt"], install_logger)


def install_profile(profile):
    install_logger.info("Starting runtime installation for profile: %s", profile)
    env = detect_environment()
    install_logger.info("Detected environment: %s", json.dumps(env, indent=2))
    log_versions(install_logger, "Before installation")

    if profile == "nvidia_blackwell_cu128":
        py_version = parse_version_tuple(platform.python_version())
        if py_version < (3, 10) or py_version >= (3, 14):
            raise RuntimeError(
                "nvidia_blackwell_cu128 requires a Python version supported by current PyTorch cu128 wheels "
                "(expected Python >=3.10 and <3.14). Current Python: " + platform.python_version()
            )

    uninstall_runtime_packages()
    install_base_requirements()

    if profile == "nvidia_compat_cu118":
        run_pip(["install"] + COMPAT_CORE, install_logger)
        run_pip(
            ["install", "--no-deps", "--index-url", "https://download.pytorch.org/whl/cu118"] + COMPAT_TORCH,
            install_logger,
        )
        run_pip(["install", "--no-deps"] + COMPAT_HF, install_logger)
    elif profile == "nvidia_blackwell_cu128":
        run_pip(["install", "numpy", "opencv-python"], install_logger)
        run_pip(
            ["install", "--no-deps", "--index-url", "https://download.pytorch.org/whl/cu128", "torch", "torchvision", "torchaudio"],
            install_logger,
        )
        run_pip(["install", "-r", str(REQ_DIR / "runtime-nvidia-blackwell-cu128.txt")], install_logger)
    elif profile == "cpu_fallback":
        install_logger.warning("CPU fallback selected. OCR, inpainting, and text detection can be slow.")
        run_pip(["install", "numpy", "opencv-python"], install_logger)
        run_pip(
            ["install", "--no-deps", "--index-url", "https://download.pytorch.org/whl/cpu", "torch", "torchvision", "torchaudio"],
            install_logger,
        )
        run_pip(["install", "-r", str(REQ_DIR / "runtime-cpu.txt")], install_logger)
    else:
        raise ValueError(f"Unknown runtime profile: {profile}")

    run_pip(["check"], install_logger, check=False)
    log_versions(install_logger, "After installation")
    install_logger.info("Runtime installation completed for profile: %s", profile)


def classify_known_error(error_text):
    lowered = error_text.lower()
    if "infer_schema" in lowered or "unsupported type torch.tensor" in lowered:
        return "known_infer_schema_torch_transformers_incompatibility"
    if "keyerror" in lowered and "manga_ocr" in lowered:
        return "known_manga_ocr_registry_failure"
    return None


def import_check(module_name, status):
    try:
        module = importlib.import_module(module_name)
        check_logger.info("Import OK: %s", module_name)
        return module
    except Exception:
        tb = traceback.format_exc()
        known = classify_known_error(tb)
        status["ok"] = False
        status["errors"].append({"test": f"import {module_name}", "error": tb, "known_issue": known})
        check_logger.error("Import failed: %s\n%s", module_name, tb)
        if known:
            check_logger.error("Known incompatibility detected: %s", known)
        return None


def health_check(profile):
    check_logger.info("Running health check for profile: %s", profile)
    env = detect_environment()
    check_logger.info("Detected environment: %s", json.dumps(env, indent=2))
    status = {"ok": True, "errors": []}
    versions = collect_versions()
    cuda_available = False
    cuda_device_name = None
    cuda_device_capability = None

    import_check("numpy", status)
    import_check("cv2", status)
    torch_mod = import_check("torch", status)
    import_check("torchvision", status)
    import_check("transformers", status)
    import_check("diffusers", status)

    if torch_mod is not None:
        try:
            cuda_available = bool(torch_mod.cuda.is_available())
            check_logger.info("torch.cuda.is_available(): %s", cuda_available)
            if cuda_available:
                cuda_device_name = torch_mod.cuda.get_device_name(0)
                cuda_device_capability = torch_mod.cuda.get_device_capability(0)
                check_logger.info("CUDA device: %s, capability: %s", cuda_device_name, cuda_device_capability)
                x = torch_mod.randn((1024, 1024), device="cuda")
                y = x @ x
                del y
                torch_mod.cuda.synchronize()
                check_logger.info("CUDA matrix multiplication test passed.")
            elif profile.startswith("nvidia"):
                status["ok"] = False
                status["errors"].append({"test": "torch.cuda.is_available", "error": "CUDA is not available for NVIDIA profile."})
        except Exception:
            tb = traceback.format_exc()
            status["ok"] = False
            status["errors"].append({"test": "cuda runtime", "error": tb, "known_issue": classify_known_error(tb)})
            check_logger.error("CUDA runtime test failed:\n%s", tb)

    sys.path.insert(0, str(ROOT))
    import_check("modules.ocr.ocr_manga", status)
    import_check("modules.ocr.ocr_paddleVL_manga", status)
    import_check("modules.textdetector.detector_ctd", status)

    try:
        from modules.base import init_module_registries
        from modules import OCR, TEXTDETECTORS

        init_module_registries(["ocr", "textdetector"])
        if "manga_ocr" not in OCR.module_dict:
            status["ok"] = False
            status["errors"].append({"test": "OCR registry", "error": "manga_ocr is not registered in OCR.module_dict"})
        else:
            check_logger.info("Registry OK: manga_ocr is available.")
        if "ctd" not in TEXTDETECTORS.module_dict:
            check_logger.warning("CTD registry key 'ctd' not found. Available text detectors: %s", sorted(TEXTDETECTORS.module_dict))
    except Exception:
        tb = traceback.format_exc()
        known = classify_known_error(tb)
        status["ok"] = False
        status["errors"].append({"test": "module registry", "error": tb, "known_issue": known})
        check_logger.error("Registry check failed:\n%s", tb)

    if profile == "nvidia_blackwell_cu128" and not status["ok"]:
        warning = (
            "RTX 50xx erkannt. CUDA funktioniert möglicherweise, aber die aktuelle OCR/Transformers-Kombination "
            "ist mit BallonsTranslator-vibe noch nicht stabil. Bitte alternatives OCR-Modul wählen oder "
            "Compat-Profil auf RTX 3090 verwenden."
        )
        check_logger.error(warning)
        print(warning, flush=True)

    if not status["ok"]:
        diagnosis = {
            "profile": profile,
            "gpu": env.get("gpu_name"),
            "compute_capability": env.get("compute_capability"),
            "versions": versions,
            "cuda_available": cuda_available,
            "cuda_device_name": cuda_device_name,
            "cuda_device_capability": cuda_device_capability,
            "failed_tests": status["errors"],
            "next_action": next_action(profile, status),
        }
        check_logger.error("Runtime health diagnosis:\n%s", json.dumps(diagnosis, indent=2))
        print("Runtime health check failed. See logs/runtime_check.log for full diagnostics.", flush=True)
        print(json.dumps(diagnosis, indent=2), flush=True)
    else:
        check_logger.info("Health check passed.")

    return status["ok"], versions, cuda_available


def next_action(profile, status):
    errors = json.dumps(status.get("errors", []))
    if "CUDA is not available" in errors and profile.startswith("nvidia"):
        return "Check NVIDIA driver/CUDA visibility, then run with --repair-runtime."
    if "manga_ocr" in errors or "infer_schema" in errors:
        if profile == "nvidia_blackwell_cu128":
            return "Use another OCR module on RTX 50xx or test the stable nvidia_compat_cu118 profile on RTX 3090."
        return "Run python launch.py --runtime-profile nvidia_compat_cu118 --repair-runtime."
    if "No module named" in errors:
        return "Run with --repair-runtime to reinstall the selected runtime profile."
    return "Inspect logs/runtime_check.log and rerun with --repair-runtime if the package set is inconsistent."


def save_profile_state(env, profile, versions, cuda_available, is_ok):
    state = {
        "selected_profile": profile,
        "gpu_name": env.get("gpu_name") or "Unknown",
        "compute_capability": env.get("compute_capability"),
        "torch_version": versions.get("torch", "Unknown"),
        "torchvision_version": versions.get("torchvision", "Unknown"),
        "numpy_version": versions.get("numpy", "Unknown"),
        "transformers_version": versions.get("transformers", "Unknown"),
        "diffusers_version": versions.get("diffusers", "Unknown"),
        "cuda_available": cuda_available,
        "last_health_check_ok": is_ok,
        "timestamp": datetime.now().isoformat(),
    }
    PROFILE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    check_logger.info("Saved runtime profile state: %s", json.dumps(state, indent=2))


def show_profile():
    env = detect_environment()
    selected = choose_runtime_profile(env)
    state = load_profile_state()
    print(json.dumps({"detected_profile": selected, "environment": env, "saved_state": state}, indent=2))


def main():
    parser = argparse.ArgumentParser(description="GPU-aware runtime manager for BallonsTranslator-vibe.")
    parser.add_argument("--runtime-profile", choices=PROFILE_CHOICES, default="auto")
    parser.add_argument("--repair-runtime", action="store_true")
    parser.add_argument("--skip-runtime-check", action="store_true")
    parser.add_argument("--no-auto-install", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--show-profile", action="store_true")
    parser.add_argument("--detect", action="store_true")
    args = parser.parse_args()

    env = detect_environment()
    profile = choose_runtime_profile(env) if args.runtime_profile == "auto" else args.runtime_profile

    if args.detect:
        print(json.dumps(env, indent=2))
        return
    if args.show_profile:
        show_profile()
        return
    if args.check:
        ok, versions, cuda_available = health_check(profile)
        save_profile_state(env, profile, versions, cuda_available, ok)
        sys.exit(0 if ok else 1)

    state = load_profile_state()
    needs_install = args.repair_runtime
    if state is None:
        needs_install = True
    elif state.get("selected_profile") != profile or not state.get("last_health_check_ok", False):
        needs_install = True

    if needs_install:
        if args.no_auto_install:
            check_logger.error("--no-auto-install is set but runtime profile %s needs installation or repair.", profile)
            sys.exit(1)
        install_profile(profile)
    else:
        install_logger.info("Existing healthy runtime profile found; skipping dependency installation.")

    if args.skip_runtime_check:
        check_logger.info("Skipping runtime health check by request.")
        return

    ok, versions, cuda_available = health_check(profile)
    save_profile_state(env, profile, versions, cuda_available, ok)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
