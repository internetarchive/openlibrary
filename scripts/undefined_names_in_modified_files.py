#!/usr/bin/env python3

# Legacy Python sees type hints as syntax errrors.
# flake8: noqa

import sys
from subprocess import PIPE, run
from typing import Tuple


def do_run(command: str) -> Tuple[int, str]:
    print("$ {}".format(command))
    completed_process = run(command.split(), stdout=PIPE)
    return completed_process.returncode, completed_process.stdout.decode()


if __name__ == "__main__":
    returncode, results = do_run("git diff origin/master --name-only")
    filenames = " ".join(
        ("../" + line.strip()) for line in results.splitlines() if line.endswith(".py")
    )
    if filenames:
        returncode, results = do_run(
            "flake8 --select=F821 --show-source --statistics " + filenames
        )
        print(results)
        sys.exit(returncode)
