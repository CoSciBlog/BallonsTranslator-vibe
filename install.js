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
          HF_HUB_ENABLE_HF_TRANSFER: "1"
        },
        message: [
          "python -m pip install --upgrade pip wheel setuptools",
          "python -m pip uninstall -y pyqt6-tools pyqt6-plugins qt6-tools qt6-applications",
          "uv pip install -r requirements.txt"
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
