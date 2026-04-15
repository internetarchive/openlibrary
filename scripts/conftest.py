"""
Pytest configuration for the scripts directory.

BACKGROUND
----------
When running `pytest --doctest-modules .`, pytest attempts to import every Python
module it encounters to run doctests. This includes standalone scripts in the
scripts/ directory.

PROBLEM
------
Many files in scripts/ are designed to be run directly as command-line tools,
not imported as modules. These scripts often contain module-level code that:

1. Calls sys.exit() when validation fails (e.g., missing required env vars)
2. Parses command-line arguments at import time
3. Imports modules that don't exist in the test environment
4. Executes the main program logic at module level

When pytest tries to import these files to run doctests, the module-level
code executes and causes pytest to crash (via SystemExit) or fail to import.

For example:
- scripts/obfi/hide.py validates SEED_PATH at module level and calls sys.exit(1)
- scripts/open_syllabus_project_parser.py executes its CLI at module level

SOLUTION APPROACHES
-------------------

Option A: Fix every standalone script (too invasive)
    - Move all module-level validation/execution into `if __name__ == "__main__":`
    - Pros: Makes scripts import-safe, best practice
    - Cons: Requires fixing dozens of scripts, high risk of breaking functionality

Option B: Keep using --ignore=scripts (loses test coverage)
    - Makefile: `pytest . --ignore=scripts --doctest-modules`
    - Pros: Simple, no conftest needed
    - Cons: Excludes scripts/tests/ from test suite, losing ~109 tests

Option C: Explicitly test scripts/tests/ directory (Makefile change only)
    - Makefile: `pytest . scripts/tests/ --ignore=infogami --ignore=vendor --ignore=node_modules --doctest-modules`
    - Pros: Simple, no conftest needed
    - Cons: Still tries to import scripts/ files because we're testing `.`

Option D: Use pytest collection hook (this file - CURRENT SOLUTION)
    - Create scripts/conftest.py with pytest_ignore_collect hook
    - Hooks into pytest's collection phase to skip standalone scripts
    - Allows scripts/tests/ to be tested while excluding problematic scripts
    - Pros: Minimal invasiveness, solves the problem elegantly
    - Cons: Requires understanding of pytest hooks

WHY THIS IS THE BEST OPTION
--------------------------
1. Least invasive: Doesn't require modifying dozens of scripts
2. Preserves test coverage: All tests in scripts/tests/ run (109 tests added)
3. Follows pytest best practices: Using collection hooks is a supported pattern
4. Clear and maintainable: Logic is centralized in one file
5. Safe: Only affects collection in the scripts/ directory

If Option A were feasible (fixing all scripts), that would be ideal. However,
given the scope and risk, Option D provides the best balance of simplicity,
safety, and functionality.
"""

from pathlib import Path


def pytest_ignore_collect(collection_path, config):
    """
    Prevent pytest from collecting doctests from standalone scripts.

    This hook is called during pytest's collection phase. When pytest runs with
    --doctest-modules, it tries to collect every Python file as a potential
    test module. For files in scripts/, we want to skip standalone scripts
    but still allow files in scripts/tests/ to be collected.

    Args:
        collection_path: Path to the file/directory being considered for collection
        config: Pytest configuration object (unused but required by hook signature)

    Returns:
        True: Skip this file (don't collect it)
        None: Allow pytest to process this file normally
    """

    scripts_dir = Path(__file__).parent.resolve()
    tests_dir = scripts_dir / "tests"

    # If this is in the scripts directory but not in the tests subdirectory,
    # we need to decide whether to skip it
    if collection_path.is_relative_to(
        scripts_dir
    ) and not collection_path.is_relative_to(tests_dir):
        # Allow test files even if they're not in tests/ subdirectory
        if "test_" in collection_path.name or "_test.py" in collection_path.name:
            return None
        # Ignore __pycache__ and hidden directories/files
        if "__pycache__" in collection_path.name or collection_path.name.startswith(
            "."
        ):
            return True
        # For Python files, skip them unless they're test files
        if collection_path.suffix == ".py" and collection_path.parent != tests_dir:
            return True

    # For everything else (including scripts/tests/), let pytest decide
    return None
