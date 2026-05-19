const repo = "https://github.com/CoSciBlog/BallonsTranslator-vibe.git"
const branch = "dev"

module.exports = {
  requires: {
    bundle: "ai"
  },
  run: [
    {
      method: "shell.run",
      params: {
        path: ".",
        env: {
          PYTHONUNBUFFERED: "1"
        },
        message: [
          `python -u scripts/launch_step.py "Configuring update repository" -- git remote set-url origin ${repo}`,
          `python -u scripts/launch_step.py "Fetching BallonsTranslator-vibe updates" -- git fetch --progress origin ${branch}`,
          `python -u scripts/launch_step.py "Fast-forwarding local checkout" -- git pull --ff-only --progress origin ${branch}`
        ]
      }
    },
    {
      method: "shell.run",
      params: {
        venv: "env",
        path: ".",
        env: {
          HF_HUB_ENABLE_HF_TRANSFER: "1",
          PYTHONUNBUFFERED: "1",
          PIP_PROGRESS_BAR: "on"
        },
        message: [
          "python -u scripts/launch_step.py \"Refreshing pip, wheel, and setuptools\" -- python -m pip install --upgrade pip wheel setuptools --progress-bar on",
          "python -u scripts/launch_step.py \"Refreshing BallonsTranslator requirements\" -- uv pip install -r requirements.txt"
        ]
      }
    },
    {
      method: "fs.link",
      params: {
        venv: "env"
      }
    }
  ]
}
