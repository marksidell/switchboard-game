#!/usr/bin/env bash
# Prepare a Deep Learning AMI instance for Qwen3-TTS (tts_task.md 4.5).
#
# Runs on the instance. Idempotent, so an interrupted session can rerun it.
#
# The image's layout, probed on "Deep Learning OSS Nvidia Driver AMI GPU
# PyTorch 2.7 (Ubuntu 22.04) 20260427" rather than guessed at:
#
#   /opt/pytorch          a venv on Python 3.12, holding torch 2.7.0+cu128 and
#                         torchaudio 2.7.0+cu128, both CUDA builds that match
#                         the driver on the image
#   /usr/bin/python3      Python 3.10, no torch, and no python3-venv package,
#                         so it cannot even create a virtual environment
#
# So the environment is built from /opt/pytorch's interpreter with
# --system-site-packages, inheriting the working CUDA torch without needing
# root and without mutating the image.
#
# Four failure modes this guards against, every one of them met for real:
#
#   1. pip will drag in its own torch and torchaudio unless stopped. Left to
#      itself it put torch 2.14.0+cu130 over the image's 2.7.0+cu128 —
#      torchaudio from PyPI pins an exact torch, which pulls the pair forward.
#      The result imports, reports cuda True and names the L4, and then dies on
#      the first real kernel with CUDNN_STATUS_SUBLIBRARY_LOADING_FAILED,
#      because cu130 wants a newer driver than this image has. Hence the
#      constraints file below, and hence the check runs a real convolution
#      instead of asking whether CUDA is "available".
#   2. The sox Python package shells out to the sox binary, absent here.
#   3. tts/script.py needs ruamel, which qwen-tts does not bring.
#   4. The image's own 40GB root cannot hold this install plus the model
#      weights; the launch asks for a bigger one (see tts/aws/common.sh).
set -euo pipefail

AMI_ENV=${AMI_ENV:-/opt/pytorch}
VENV=${VENV:-$HOME/tts-venv}

echo "=== disk ==="
df -h / | tail -1

echo "=== system packages ==="
sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq sox libsndfile1

echo "=== nvidia ==="
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader

echo "=== base interpreter ==="
if [ -x "$AMI_ENV/bin/python" ]; then
    BASE=$AMI_ENV/bin/python
else
    echo "  $AMI_ENV not found; falling back to the system python"
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv \
        || sudo apt-get install -y -qq \
           "python$(python3 -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")')-venv"
    BASE=$(command -v python3)
fi
"$BASE" -c "import sys; print(f'  {sys.executable}  {sys.version.split()[0]}')"
"$BASE" -c "import torch; print(f'  torch {torch.__version__}  cuda {torch.cuda.is_available()}')" \
    || echo "  (no torch in the base interpreter)"

echo "=== python environment ==="
"$BASE" -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install -q --upgrade pip

# Pin torch and torchaudio to whatever the image already has, so pip treats
# them as satisfied by --system-site-packages instead of replacing them. If
# some dependency genuinely needs newer, pip fails here, loudly, at setup,
# rather than ten minutes later in the middle of generation.
CONSTRAINTS=$(mktemp)
"$BASE" -c 'import importlib
for name in ("torch", "torchaudio"):
    try:
        mod = importlib.import_module(name)
    except ImportError:
        continue
    print(name + "==" + mod.__version__.split("+")[0])' > "$CONSTRAINTS"
echo "  constraining:"
sed 's/^/    /' "$CONSTRAINTS"
"$VENV/bin/pip" install -q -c "$CONSTRAINTS" qwen-tts
"$VENV/bin/pip" install -q "ruamel.yaml"
rm -f "$CONSTRAINTS"

echo "=== the check that matters ==="
"$VENV/bin/python" - <<'CHECK'
import sys
import torch

print(f"torch      {torch.__version__}")
try:
    import torchaudio
    print(f"torchaudio {torchaudio.__version__}")
except Exception as e:
    sys.exit(f"torchaudio will not import: {e}")

if not torch.cuda.is_available():
    sys.exit("torch reports no CUDA device. pip has most likely replaced the "
             "image's CUDA torch; this instance is useless as it stands and is "
             "costing money. Fix the install or terminate.")
print(f"device     {torch.cuda.get_device_name(0)}")
print(f"bf16       {torch.cuda.is_bf16_supported()}")

# cuda.is_available() is not enough on its own. A torch built for a newer CUDA
# than the driver supports answers True, names the GPU, and then fails on the
# first real kernel. Run one of each kind the model will use.
try:
    a = torch.randn(64, 64, device="cuda", dtype=torch.bfloat16)
    (a @ a).sum().item()
    print("matmul     ok")
    conv = torch.nn.Conv1d(4, 4, 3).cuda()
    conv(torch.randn(1, 4, 64, device="cuda")).sum().item()
    print("cudnn      ok")
except Exception as e:
    sys.exit(f"CUDA kernels do not run: {type(e).__name__}: {e}\n"
             "torch and the driver disagree — check the constraint step above.")

import qwen_tts  # noqa: F401
print("qwen_tts   imported")
CHECK

echo "=== disk after install ==="
df -h / | tail -1

echo "=== recording exactly what was installed ==="
"$VENV/bin/pip" freeze > "$HOME/requirements.lock"
wc -l < "$HOME/requirements.lock" | xargs echo "packages pinned:"
echo "setup complete"
