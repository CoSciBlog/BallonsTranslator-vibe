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
          PYTHONUNBUFFERED: "1",
          PIP_PROGRESS_BAR: "on"
        },
        message: [
          "python -u scripts/launch_step.py \"Installing test-only dependencies\" -- uv pip install --python {{platform === 'win32' ? 'env\\\\Scripts\\\\python.exe' : 'env/bin/python'}} -r requirements-test.txt",
          "python -u scripts/launch_step.py \"Running unittest suite\" -- python -m unittest discover -s tests -t . -p \"test*.py\""
        ]
      }
    }
  ]
}
