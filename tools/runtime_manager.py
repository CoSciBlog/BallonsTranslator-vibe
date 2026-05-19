import os
import sys
import json
import logging
import argparse
import subprocess
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

INSTALL_LOG = os.path.join(LOG_DIR, "runtime_install.log")
CHECK_LOG = os.path.join(LOG_DIR, "runtime_check.log")
PROFILE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".runtime_profile.json")
REQ_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "requirements")

def setup_logger(name, log_file):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger

install_logger = setup_logger("install", INSTALL_LOG)
check_logger = setup_logger("check", CHECK_LOG)

def get_fallback_compute_cap(gpu_name):
    name_lower = gpu_name.lower()
    if "rtx 50" in name_lower or "blackwell" in name_lower:
        return 12.0
    if "rtx 40" in name_lower:
        return 8.9
    if "rtx 30" in name_lower:
        return 8.6
    if "rtx 20" in name_lower:
        return 7.5
    if "gtx 16" in name_lower:
        return 7.5
    if "gtx 10" in name_lower:
        return 6.1
    return None

def detect_environment():
    env = {
        "os": sys.platform,
        "python_version": sys.version.split(' ')[0],
        "venv_path": sys.prefix,
        "pip_version": "unknown",
        "nvidia_smi_available": False,
        "gpus": [],
        "driver_version": None,
        "cuda_version": None,
        "compute_capability": None
    }
    
    try:
        pip_res = subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True, text=True, check=True)
        env["pip_version"] = pip_res.stdout.split(' ')[1]
    except Exception:
        pass

    try:
        smi_res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,compute_cap,driver_version,cuda_version,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True
        )
        if smi_res.returncode == 0:
            env["nvidia_smi_available"] = True
            lines = smi_res.stdout.strip().split('\n')
            for line in lines:
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 5:
                    gpu = {
                        "name": parts[0],
                        "compute_cap_str": parts[1],
                        "driver_version": parts[2],
                        "cuda_version": parts[3],
                        "memory": parts[4]
                    }
                    if env["driver_version"] is None:
                        env["driver_version"] = parts[2]
                        env["cuda_version"] = parts[3]
                    
                    cc = None
                    try:
                        cc = float(parts[1])
                    except ValueError:
                        cc = get_fallback_compute_cap(parts[0])
                    
                    gpu["compute_cap"] = cc
                    if env["compute_capability"] is None or (cc is not None and cc > env["compute_capability"]):
                        env["compute_capability"] = cc
                    env["gpus"].append(gpu)
    except FileNotFoundError:
        pass
    except Exception as e:
        check_logger.warning(f"Error running nvidia-smi: {e}")

    return env

def choose_runtime_profile(env):
    if not env["nvidia_smi_available"] or not env["gpus"]:
        return "cpu_fallback"
    
    cc = env["compute_capability"]
    if cc is None:
        return "nvidia_compat_cu118"  # fallback but health check is mandatory
    if cc >= 12.0:
        return "nvidia_blackwell_cu128"
    if cc >= 6.0:
        return "nvidia_compat_cu118"
    
    return "cpu_fallback"

def run_pip_command(args, logger):
    cmd = [sys.executable, "-m", "pip"] + args
    logger.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"Pip command failed: {result.stderr}")
    else:
        logger.info(f"Pip command success.")
        logger.debug(result.stdout)
    return result.returncode == 0

def uninstall_packages(logger):
    packages = [
        "torch", "torchvision", "torchaudio", "numpy",
        "opencv-python", "opencv-contrib-python", "opencv-python-headless",
        "transformers", "tokenizers", "huggingface_hub",
        "accelerate", "diffusers", "safetensors"
    ]
    run_pip_command(["uninstall", "-y"] + packages, logger)

def install_profile(profile):
    install_logger.info(f"Starting installation for profile: {profile}")
    uninstall_packages(install_logger)

    run_pip_command(["install", "-r", "requirements.txt"], install_logger)

    if profile == "nvidia_compat_cu118":
        run_pip_command(["install", "numpy==1.26.4"], install_logger)
        run_pip_command(["install", "opencv-python==4.10.0.84"], install_logger)
        run_pip_command(["install", "--no-deps", "torch==2.4.1+cu118", "torchvision==0.19.1+cu118", "torchaudio==2.4.1+cu118", "--index-url", "https://download.pytorch.org/whl/cu118"], install_logger)
        run_pip_command(["install", "--no-deps", "-r", os.path.join(REQ_DIR, "runtime-nvidia-compat-cu118.txt")], install_logger)
    elif profile == "nvidia_blackwell_cu128":
        run_pip_command(["install", "numpy", "opencv-python"], install_logger)
        run_pip_command(["install", "--no-deps", "torch", "torchvision", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cu128"], install_logger)
        run_pip_command(["install", "-r", os.path.join(REQ_DIR, "runtime-nvidia-blackwell-cu128.txt")], install_logger)
    else:
        run_pip_command(["install", "numpy", "opencv-python"], install_logger)
        run_pip_command(["install", "torch", "torchvision", "torchaudio"], install_logger)
        run_pip_command(["install", "-r", os.path.join(REQ_DIR, "runtime-cpu.txt")], install_logger)
        install_logger.warning("CPU-Fallback aktiv. OCR, Inpainting und Text Detection können deutlich langsamer sein.")

    run_pip_command(["check"], install_logger)
    install_logger.info("Installation completed.")

def health_check(profile):
    check_logger.info(f"Running health check for profile: {profile}")
    status = {"ok": True, "errors": []}
    
    def try_import(name, desc=""):
        try:
            mod = __import__(name)
            check_logger.info(f"Successfully imported {name} {desc}")
            return mod
        except Exception as e:
            status["ok"] = False
            err_msg = f"Failed to import {name}: {str(e)}"
            check_logger.error(err_msg)
            status["errors"].append(err_msg)
            if "infer_schema" in str(e) or "unsupported type torch.Tensor" in str(e):
                check_logger.error("KNOWN ISSUE: infer_schema error detected. This is a Torch/Transformers/Custom-Op incompatibility.")
            return None

    versions = {}
    
    np_mod = try_import("numpy")
    if np_mod: versions["numpy"] = np_mod.__version__
    
    cv2_mod = try_import("cv2")
    if cv2_mod: versions["opencv"] = cv2_mod.__version__
    
    torch_mod = try_import("torch")
    if torch_mod: versions["torch"] = torch_mod.__version__
    
    try_import("torchvision")
    try_import("transformers")
    try_import("diffusers")
    
    cuda_available = False
    if torch_mod:
        cuda_available = torch_mod.cuda.is_available()
        if cuda_available:
            check_logger.info(f"CUDA is available. Device: {torch_mod.cuda.get_device_name(0)}, Capability: {torch_mod.cuda.get_device_capability(0)}")
            try:
                x = torch_mod.randn((1024, 1024), device="cuda")
                y = x @ x
                torch_mod.cuda.synchronize()
                check_logger.info("CUDA basic matrix multiplication test passed.")
            except Exception as e:
                status["ok"] = False
                err_msg = f"CUDA basic test failed: {e}"
                check_logger.error(err_msg)
                status["errors"].append(err_msg)
        else:
            if profile.startswith("nvidia"):
                check_logger.warning("CUDA is NOT available but an NVIDIA profile is active.")
                status["ok"] = False
                status["errors"].append("CUDA not available for NVIDIA profile.")

    # Application specific imports
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try_import("modules.ocr.ocr_manga", desc="(Manga OCR)")
    try_import("modules.ocr.ocr_paddleVL_manga", desc="(Paddle OCR)")
    try_import("modules.textdetector.detector_ctd", desc="(CTD Detector)")
    
    if not status["ok"]:
        check_logger.error(f"Health check failed for profile {profile}.")
        if profile == "nvidia_blackwell_cu128":
            check_logger.error("RTX 50xx / Blackwell wurde erkannt. CUDA funktioniert möglicherweise, aber die aktuelle OCR-/Transformers-/Torch-Kombination ist mit BallonsTranslator-vibe noch nicht stabil. Bitte alternatives OCR-Modul wählen, Paketprofil anpassen oder das stabile nvidia_compat_cu118-Profil auf einer RTX 3090 verwenden.")
    else:
        check_logger.info("Health check passed.")

    return status["ok"], versions, cuda_available

def save_profile_state(env, profile, versions, cuda_available, is_ok):
    state = {
        "selected_profile": profile,
        "gpu_name": env["gpus"][0]["name"] if env["gpus"] else "Unknown",
        "compute_capability": env["compute_capability"],
        "torch_version": versions.get("torch", "Unknown"),
        "numpy_version": versions.get("numpy", "Unknown"),
        "opencv_version": versions.get("opencv", "Unknown"),
        "cuda_available": cuda_available,
        "last_health_check_ok": is_ok,
        "timestamp": datetime.now().isoformat()
    }
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    check_logger.info(f"Saved runtime profile state to {PROFILE_FILE}")

def main():
    parser = argparse.ArgumentParser(description="Runtime and Dependency Manager for GPU-aware environments.")
    parser.add_argument("--runtime-profile", choices=["auto", "nvidia_compat_cu118", "nvidia_blackwell_cu128", "cpu_fallback"], default="auto")
    parser.add_argument("--repair-runtime", action="store_true")
    parser.add_argument("--skip-runtime-check", action="store_true")
    parser.add_argument("--no-auto-install", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--show-profile", action="store_true")
    parser.add_argument("--detect", action="store_true")
    
    args = parser.parse_args()

    env = detect_environment()

    if args.detect:
        print(json.dumps(env, indent=2))
        return

    if args.show_profile:
        if os.path.exists(PROFILE_FILE):
            with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                print(f.read())
        else:
            print("No profile state found.")
        return

    profile = args.runtime_profile
    if profile == "auto":
        profile = choose_runtime_profile(env)

    if args.check:
        health_check(profile)
        return

    needs_install = False
    
    if args.repair_runtime:
        needs_install = True
    elif not os.path.exists(PROFILE_FILE):
        needs_install = True
    else:
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            try:
                state = json.load(f)
                if state.get("selected_profile") != profile or not state.get("last_health_check_ok", False):
                    needs_install = True
            except Exception:
                needs_install = True

    if needs_install and not args.no_auto_install:
        install_profile(profile)
    elif args.no_auto_install and needs_install:
        check_logger.error("--no-auto-install is set but runtime needs repair. Exiting.")
        sys.exit(1)

    if not args.skip_runtime_check:
        is_ok, versions, cuda_available = health_check(profile)
        save_profile_state(env, profile, versions, cuda_available, is_ok)
        if not is_ok:
            sys.exit(1)
    else:
        check_logger.info("Skipping runtime check as requested.")

if __name__ == "__main__":
    main()
