---
applyTo: "Python"
---
# Project general coding standards

## Code Formatting
- Use 4 spaces for indentation (no tabs).
- Use Sphinx-style docstrings for all public modules, classes, and methods.
  Example:

  ```python
  def send_message(sender: str, recipient: str, message_body: str, priority: int = 1) -> int:
      """Send a message to a recipient.

      :param str sender: The person sending the message
      :param str recipient: The recipient of the message
      :param str message_body: The body of the message
      :param int priority: The priority of the message, can be a number 1-5
      :return: The message id
      :rtype: int
      :raises ValueError: If the message_body exceeds 160 characters
      """
      ...
  ```

## Linters & Formatters (CI)
- CI uses Ruff for linting and Black for formatting checks.
- Ruff config lives in `pyproject.toml`.
- Black config lives in `black_config.toml` (CI runs `black --check --config black_config.toml .`).

Recommended local commands:
- `ruff check .`
- `black --config black_config.toml .`

## Change Discipline
- Prefer small, targeted diffs. Avoid refactors unrelated to the task.
- If you add/modify a feature, update docs/tests that are directly impacted.

## Dependencies
- Prefer adding dev-only tools under `[project.optional-dependencies].dev` in `pyproject.toml`.
- Avoid adding new runtime dependencies unless required by the change.
