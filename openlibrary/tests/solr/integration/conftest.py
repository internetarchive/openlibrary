import subprocess
import time
from pathlib import Path

import httpx
import pytest

from openlibrary.solr.utils import set_solr_base_url


def get_project_root():
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent.parent.parent


def wait_for_solr_ready(solr_url: str, max_wait: int = 60) -> bool:
    """Wait for Solr to be ready to accept requests."""

    ping_url = f"{solr_url}/admin/ping?wt=json"
    start_time = time.time()

    while time.time() - start_time < max_wait:
        try:
            response = httpx.get(ping_url, timeout=2)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "OK":
                    return True
        except (httpx.RequestError, httpx.TimeoutException, KeyError, ValueError):
            pass

        try:
            query_url = f"{solr_url}/select?q=*:*&rows=0&wt=json"
            response = httpx.get(query_url, timeout=2)
            if response.status_code == 200:
                data = response.json()
                if "response" in data:
                    return True
        except (httpx.RequestError, httpx.TimeoutException, ValueError):
            pass

        time.sleep(1)
    return False


@pytest.fixture(scope="session")
def solr_container():

    project_root = get_project_root()
    container_name = "openlibrary-solr-integration-test"
    port = "8984"

    try:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            check=False,
            capture_output=True,
            cwd=project_root,
        )
    except FileNotFoundError:
        pytest.skip("Docker not available")

    solr_config_path = project_root / "conf" / "solr"
    if not solr_config_path.exists():
        pytest.skip("Solr config directory not found")

    try:
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                container_name,
                "-p",
                f"{port}:8983",
                "-v",
                f"{solr_config_path}:/opt/solr/server/solr/configsets/olconfig:ro",
                "-e",
                "SOLR_MODULES=analysis-extras",
                "-e",
                "SOLR_OPTS=-Dsolr.autoSoftCommit.maxTime=1000 -Dsolr.autoCommit.maxTime=120000",
                "solr:9.9.0",
                "solr-precreate",
                "openlibrary",
                "/opt/solr/server/solr/configsets/olconfig",
            ],
            check=True,
            capture_output=True,
            cwd=project_root,
        )

        solr_base_url = f"http://localhost:{port}/solr/openlibrary"

        if not wait_for_solr_ready(solr_base_url, max_wait=120):
            logs_output = subprocess.run(
                ["docker", "logs", container_name],
                capture_output=True,
                text=True,
                check=False,
            )
            logs = logs_output.stdout + logs_output.stderr

            subprocess.run(
                ["docker", "rm", "-f", container_name],
                check=False,
                capture_output=True,
            )
            pytest.fail(
                f"Solr container failed to start within timeout.\n"
                f"Container logs:\n{logs[-2000:]}"  # Last 2000 chars
            )

        yield solr_base_url

    except subprocess.CalledProcessError as e:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            check=False,
            capture_output=True,
        )
        pytest.fail(f"Failed to start Solr container: {e.stderr.decode()}")
    except FileNotFoundError:
        pytest.skip("Docker not available")
    finally:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            check=False,
            capture_output=True,
        )


@pytest.fixture(autouse=True)
def setup_solr_url(solr_container):
    """
    Automatically configure Solr URL for integration tests.

    """
    set_solr_base_url(solr_container)
