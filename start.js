module.exports = {
  daemon: true,
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
        message: "python -u launch.py --frozen"
      }
    }
  ]
}
