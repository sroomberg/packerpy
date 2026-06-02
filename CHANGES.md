# Changelog

## v3.0.0
- Add GoogleComputeBuilder source
- Add AzureArmBuilder source

## v2.0.5
- Fix `verify_packer_installation` to use list args and catch `FileNotFoundError`
- Add generic type to `PackerClient.run()` return annotation
- Raise `PackerBuildError` on failed init and build commands
- Add test optional-dependencies group to `pyproject.toml`
- Install packer in CI and remove pip install fallback
- Add tests for `PackerClient` and `PackerBuilder`
- Trigger publish workflow on tag push

## v2.0.4
- Fix version for `typing_extensions`
- Add back `typing_extensions`

## v2.0.3
- Remove redundant variable
- Fix publish workflow

## v2.0.2
- Add type hints, docstrings, and public exports across the codebase
- Add `@override` decorators to all overriding methods

## v2.0.1
- Migrate to `pyproject.toml`, add ruff formatting, add PyPI publish workflow
- Add CI workflow for linting and tests
- Set minimum Python version to 3.10
- Add Python 3.11 and 3.13 to CI and publish workflows

## v1.0.4
- Initial release
