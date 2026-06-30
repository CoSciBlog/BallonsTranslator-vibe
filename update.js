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
          `git remote set-url origin ${repo}`,
          `git fetch --progress origin ${branch}`,
          `git pull --ff-only --progress origin ${branch}`
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
          "python -m pip install --upgrade pip wheel setuptools==71.1.0 --progress-bar on",
          "uv pip install -r requirements.txt",
          "python -m pip install -e . --no-deps"
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
