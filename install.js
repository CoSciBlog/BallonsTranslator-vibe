module.exports = {
  requires: {
    bundle: "ai"
  },
  run: [
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
          "python -u scripts/launch_step.py \"Installing/upgrading pip, wheel, and compatible setuptools\" -- python -m pip install --upgrade pip wheel setuptools==71.1.0 --progress-bar on",
          "python -m pip uninstall -y pyqt6-tools pyqt6-plugins qt6-tools qt6-applications",
          "python -u scripts/launch_step.py \"Installing BallonsTranslator requirements from requirements.txt\" -- uv pip install -r requirements.txt"
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
