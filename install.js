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
          "python -m pip install --upgrade pip wheel setuptools==71.1.0 --progress-bar on",
          "python -m pip uninstall -y pyqt6-tools pyqt6-plugins qt6-tools qt6-applications",
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
