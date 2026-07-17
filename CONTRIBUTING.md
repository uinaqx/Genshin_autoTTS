# Contributing

1. Create a Python 3.10-3.12 virtual environment.
2. Install the project with `python -m pip install -e ".[dev]"`.
3. Run `python -m pytest` and `ruff check .` before submitting changes.
4. Do not commit game files, extracted text maps, model weights, generated audio,
   authentication tokens, runtime configuration, logs, screenshots, or caches.

Contributions should preserve the external companion architecture: the project
must not inject code into a game, read game memory, alter game files, automate
inputs, or bypass anti-cheat systems.
