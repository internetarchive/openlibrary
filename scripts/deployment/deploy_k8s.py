#!/usr/bin/env python3
"""Point Kubernetes (us-west-1-p01) at one Open Library commit: deploy.sh's k8s step.

    deploy_k8s.py <deploy dir> [full commit SHA]   # SHA defaults to <deploy dir>/openlibrary's HEAD

Argo CD deploys whatever the ol-web chart's branch of application-manifests pins. Its bump script
pins olbase:<sha12> by digest and copies that commit's FastAPI routes; this commits and pushes that.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import NoReturn

REPO = os.environ.get("K8S_MANIFESTS_REPO", "git@git.archive.org:platform-engineering/application-manifests.git")
BRANCH = os.environ.get("K8S_MANIFESTS_BRANCH", "drini-ol-web")
RED, YELLOW, GREEN, BOLD = "31", "33", "32", "1"


def color(code: str, text: str) -> str:
    """ANSI color, only on a terminal: piped output (tee, logs) and NO_COLOR stay plain."""
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() and "NO_COLOR" not in os.environ else text


def fail(message: str) -> NoReturn:
    sys.exit(color(RED, f"[Error] {message}"))


def ask(prompt: str, default: str) -> bool:
    try:
        return (input(color(BOLD, prompt)).strip() or default).lower() in ("y", "yes")
    except EOFError:
        return default == "y"


def run(*cmd, cwd=None, check=True) -> int:
    return subprocess.run(cmd, cwd=cwd, check=check).returncode


def olbase_digest(tag: str) -> str:
    try:
        with urllib.request.urlopen(f"https://hub.docker.com/v2/repositories/openlibrary/olbase/tags/{tag}", timeout=30) as r:
            if digest := json.load(r).get("digest"):
                return digest
            raise ValueError("no digest in the response")
    except (OSError, ValueError) as e:  # network and HTTP errors are OSErrors
        fail(f"Couldn't get the digest of openlibrary/olbase:{tag} from Docker Hub ({e}); has olbase built it?")


def main(deploy_dir: Path, sha: str = "") -> None:
    if not sha and (deploy_dir / "openlibrary/.git").is_dir():
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=deploy_dir / "openlibrary", check=True, capture_output=True, text=True).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        fail("Pass the full 40-character commit SHA to deploy, or run the openlibrary step first.")
    tag = sha[:12]
    print(f"[Now] Deploying openlibrary {tag} to Kubernetes")

    # The VMs run olbase:latest; Kubernetes should run the same build.
    if (digest := olbase_digest(tag)) != (latest := olbase_digest("latest")):
        print(color(YELLOW, f"[Warning] olbase:{tag} ({digest}) is not olbase:latest ({latest}),"))
        print(color(YELLOW, "          so Kubernetes would run a different build from the VMs."))
        if not ask(f"Deploy olbase:{tag} to Kubernetes anyway? [y/N]...", "n"):
            sys.exit(1)

    manifests = deploy_dir / "application-manifests"
    shutil.rmtree(manifests, ignore_errors=True)
    run("git", "clone", "-q", "--depth=1", "--branch", BRANCH, REPO, str(manifests))
    previous = re.search(r"^  tag: ([0-9a-f]{12})$", (manifests / "ol-web/values.yaml").read_text(), re.MULTILINE)
    run(sys.executable, str(manifests / "ol-web/scripts/bump-openlibrary.py"), sha)
    if run("git", "diff", "--quiet", cwd=manifests, check=False) == 0:
        print(f"[Info] Kubernetes already runs {tag}.")
        return
    run("git", "--no-pager", "diff", "--stat", cwd=manifests)
    if not ask(f"[Now] Push this to {BRANCH}? Argo CD rolls it out. [Y/n]...", "y"):
        sys.exit("[Info] Not pushed; Kubernetes stays on its current version.")
    run("git", "commit", "-q", "-am", f"ol-web: deploy openlibrary {tag}", cwd=manifests)
    run("git", "push", "-q", "origin", f"HEAD:{BRANCH}", cwd=manifests)
    # Nothing here can see the cluster yet, so a person checks the rollout before the VMs restart.
    print(color(GREEN, "✓ Pushed.") + f" Argo CD rolls {tag} out in a few minutes. It's done when App Health is back to Healthy")
    print("  and each Deployment is down to one Replica Set, with every pod ready:")
    print("  https://argocd.p01.us-west-1.archive.org/applications/argocd/openlibrary?view=pods&podSortMode=parentResource")
    print("  Then check errors and latency: https://grafana.p01.us-west-1.archive.org/d/ra28gwx/k8s")
    if not ask(f"[Now] Are all Kubernetes pods on {tag} and healthy? [y/N]...", "n"):
        rollback = f"./scripts/deployment/deploy.sh k8s $(git rev-parse {previous[1]})" if previous else "./scripts/deployment/deploy.sh k8s <previous sha>"
        fail(f"Kubernetes isn't healthy on {tag}. To roll it back: {rollback}")


if __name__ == "__main__":
    try:
        main(Path(sys.argv[1]), *sys.argv[2:3])
    except subprocess.CalledProcessError as e:
        fail(f"{' '.join(e.cmd)} failed.")  # the command has already said why
    except KeyboardInterrupt:
        sys.exit(1)
