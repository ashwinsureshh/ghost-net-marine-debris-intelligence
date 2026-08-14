"""Detect which machine this session/run is on, and what it may safely do.

MACHINE-WORKFLOW.md requires that we detect CUDA availability rather than
assume it from the OS. This script is the single implementation of that rule so
that no agent, notebook or Claude Code session has to guess.

Usage:
    python scripts/check_machine.py           # human-readable report
    python scripts/check_machine.py --json    # machine-readable

From Python:
    from scripts.check_machine import get_profile
    if not get_profile().can_train:
        ...fall back to spectral-index baseline / cloud API / smaller sample
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import platform
import shutil
import subprocess
import sys

# A CNN fine-tune on MARIDA-sized tiles needs headroom; below this we treat the
# GPU as present-but-not-trainable and fall back rather than OOM mid-run.
MIN_TRAIN_VRAM_GB = 6.0


@dataclasses.dataclass
class MachineProfile:
    role: str  # "workstation" | "laptop" | "unknown"
    os: str
    python: str
    has_nvidia_smi: bool
    cuda_available: bool
    gpu_name: str | None
    vram_gb: float | None
    compute_capability: str | None
    torch_version: str | None
    can_train: bool
    notes: list[str]

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


def _query_nvidia_smi() -> tuple[bool, str | None, float | None]:
    """Return (smi_present, gpu_name, vram_gb) without needing torch."""
    if shutil.which("nvidia-smi") is None:
        return False, None, None
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        # Driver present but not responding — treat as no usable GPU.
        return True, None, None
    if not out:
        return True, None, None
    name, _, mem = out.splitlines()[0].partition(",")
    try:
        vram_gb = round(float(mem.strip()) / 1024, 2)
    except ValueError:
        vram_gb = None
    return True, name.strip(), vram_gb


def _query_torch() -> tuple[str | None, bool, str | None, float | None, str | None]:
    """Return (torch_version, cuda_available, gpu_name, vram_gb, capability)."""
    try:
        import torch
    except ImportError:
        return None, False, None, None, None

    version = torch.__version__
    if not torch.cuda.is_available():
        return version, False, None, None, None

    props = torch.cuda.get_device_properties(0)
    cap = torch.cuda.get_device_capability(0)
    return (
        version,
        True,
        torch.cuda.get_device_name(0),
        round(props.total_memory / 1024**3, 2),
        f"sm_{cap[0]}{cap[1]}",
    )


def get_profile() -> MachineProfile:
    notes: list[str] = []
    smi_present, smi_name, smi_vram = _query_nvidia_smi()
    torch_version, cuda_ok, torch_name, torch_vram, capability = _query_torch()

    gpu_name = torch_name or smi_name
    vram_gb = torch_vram or smi_vram

    if torch_version is None:
        notes.append("PyTorch not installed for this interpreter.")
    elif smi_present and not cuda_ok:
        notes.append(
            "nvidia-smi found a GPU but torch.cuda is unavailable — most likely a "
            "CPU-only torch build. Reinstall from the CUDA index "
            "(see requirements-gpu.txt)."
        )

    # Blackwell (RTX 50-series) is sm_120 and needs a CUDA 12.8+ torch build.
    if capability == "sm_120" and torch_version:
        try:
            import torch

            if "sm_120" not in torch.cuda.get_arch_list():
                notes.append(
                    "This torch build has no sm_120 kernels — RTX 50-series will "
                    "fail at first CUDA op. Install a cu128+ build."
                )
        except Exception:  # pragma: no cover - defensive only
            pass

    can_train = bool(cuda_ok and vram_gb and vram_gb >= MIN_TRAIN_VRAM_GB)
    if cuda_ok and not can_train:
        notes.append(
            f"GPU present but under {MIN_TRAIN_VRAM_GB} GB usable — "
            "prefer the spectral-index baseline or a reduced batch size."
        )

    if cuda_ok:
        role = "workstation"
    elif platform.system() == "Darwin":
        role = "laptop"
        notes.append(
            "Apple Silicon / no CUDA: do not train the CNN detector or run "
            "large batch tile jobs here. Use the spectral-index baseline, a "
            "small cached sample, or defer to the workstation."
        )
    else:
        role = "unknown"
        notes.append("No CUDA and not macOS — treat as CPU-only.")

    return MachineProfile(
        role=role,
        os=f"{platform.system()} {platform.release()} ({platform.machine()})",
        python=platform.python_version(),
        has_nvidia_smi=smi_present,
        cuda_available=cuda_ok,
        gpu_name=gpu_name,
        vram_gb=vram_gb,
        compute_capability=capability,
        torch_version=torch_version,
        can_train=can_train,
        notes=notes,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()

    profile = get_profile()

    if args.json:
        print(json.dumps(profile.as_dict(), indent=2))
        return 0

    print("Machine profile")
    print("-" * 52)
    print(f"  role              : {profile.role}")
    print(f"  os                : {profile.os}")
    print(f"  python            : {profile.python}")
    print(f"  torch             : {profile.torch_version or 'not installed'}")
    print(f"  nvidia-smi        : {'yes' if profile.has_nvidia_smi else 'no'}")
    print(f"  cuda available    : {'yes' if profile.cuda_available else 'no'}")
    print(f"  gpu               : {profile.gpu_name or '-'}")
    print(f"  vram (GB)         : {profile.vram_gb if profile.vram_gb else '-'}")
    print(f"  compute capability: {profile.compute_capability or '-'}")
    print()
    print(f"  GPU training OK   : {'YES' if profile.can_train else 'NO'}")
    print()
    print("Suitable work here:")
    if profile.can_train:
        print("  - CNN detector training / fine-tuning (FR-1.4)")
        print("  - Batch processing over many Sentinel-2 tiles")
        print("  - Everything the laptop can do")
    else:
        print("  - Agent orchestration, API integration, everyday coding")
        print("  - Spectral-index baseline (FR-1.2), verification, drift,")
        print("    attribution, vessel correlation, prioritisation")
        print("  - Tests and docs on SMALL cached samples only")
    for note in profile.notes:
        print(f"\n  ! {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
