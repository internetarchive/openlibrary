#!/usr/bin/env python3
"""
./run_olserver.py -h
usage: run_olserver.py [-h] [--python {2.7,3.8,3.9}] [--staging | --local]
          [{covers,db,home,infobase,memcached,solr,web,haproxy,nginx} ...]

positional arguments:
  {covers,db,home,infobase,memcached,solr,web,haproxy,nginx}
                        services to be started

optional arguments:
  -h, --help            show this help message and exit
  --python {2.7,3.8,3.9}
                        Python version
  --staging             create a non-production staging instance
  --local               create a non-production localhost instance

---

./run_olserver.py web nginx --staging
Namespace(services=['web', 'nginx'], python=3.8, staging=True, local=False)
"""

import os
from argparse import ArgumentParser, Namespace
from collections import namedtuple
from logging import getLogger
from platform import node
from string import digits
from subprocess import run
from typing import Dict

import yaml

logger = getLogger(__file__)

default_services = {
    "ol-covers": ("covers", "covers_nginx", "memcached"),
    "ol-home": ("infobase", "infobase_nginx"),
    "ol-solr": ("solr",),
    "ol-web": ("web",),
    "ol-www": [],
}

possible_services = {
    "covers": "Open Library coverstore image service",
    "db": "PostgreSQL relational database for Open Library",
    "home": "Open Library home server",
    "infobase": "Infogami infobase server",
    "memcached": "Memcached memory object caching system",
    "solr": "Apache Solr search platform",
    "web": "Open Library web server",
    "haproxy": "HAProxy Load Balancer",
    "nginx": "NGINX Load Balancer",
}

python_versions = {2.7: "2.7.6", 3.8: "3.8.6", 3.9: "3.9.0"}


def do_run(command: str = "ls -la") -> None:
    print(command)
    print(run(command.split(), text=True, check=True))


def get_buildable_services(compose_filepath: str = "docker-compose.yml"):
    with open(compose_filepath) as in_file:
        return list(yaml.safe_load(in_file)["services"])


def get_args(hostname: str = node()):
    parser = ArgumentParser()
    parser.add_argument(
        "services",
        choices=possible_services,
        default="web",
        nargs="*",
        help="services to be started",
    )
    parser.add_argument(
        "--python",
        type=float,
        choices=python_versions,
        default=3.8,
        help="Python version",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--staging",
        action="store_true",
        help="create a non-production staging instance",
    )
    group.add_argument(
        "--local",
        action="store_true",
        help="create a non-production localhost instance",
    )
    return parser.parse_args()


def get_environment_variables(args: Namespace, hostname: str = node()) -> Dict:
    compose_files = ["docker-compose.yml"]
    if int(args.python) == 3:
        compose_files.append("docker-compose.infogami-local.yml")
    if args.staging:
        compose_files.append("docker-compose.staging.yml")
    elif args.local:
        compose_files.append("docker-compose.override.yml")
    else:
        compose_files.append("docker-compose.production.yml")
    return {
        "COMPOSE_FILE": ":".join(compose_files),
        "HOSTNAME": hostname,
        "PATH": os.getenv("PATH"),
        "PYENV_VERSION": python_versions[args.python],
    }


build_and_up = namedtuple("build_and_up", "build up")


def get_build_and_up_commands(args: Namespace, hostname: str = node()) -> build_and_up:
    """
    sudo docker-compose up -d --no-deps web
    """
    build_web = "docker-compose build --pull web"
    if args.staging:
        return build_and_up(build=build_web, up="docker-compose up -d web")
    elif args.local:
        return build_and_up(build=build_web, up="docker-compose up -d memcached web")

    # Production build: Either use args.services or services based on the hostname
    services = args.services or default_services[hostname.rstrip(digits)]
    if "covers" in services:
        services.append("covers_nginx")
    if "infobase" in services:
        services.append("infobase_nginx")
    services_str = " ".join(sorted(set(services)))
    return build_and_up(
        build=f"sudo docker-compose build --pull {services_str}",
        up=f"sudo docker-compose up -d --no-deps {services_str}",
    )


def git_sync_for_production() -> None:
    def sync_dir(dir_path: str = "/opt/openlibrary"):
        do_run("cd" + dir_path)
        do_run("git status")
        do_run("sudo git checkout master")
        do_run("sudo git pull origin master")

    sync_dir("/opt/olsystem")
    sync_dir("/opt/openlibrary")
    sync_dir("/opt/openlibrary/vendor/infogami")
    if os.path.isdir("/opt/booklending_utils"):
        sync_dir("/opt/booklending_utils")
    do_run("cd /opt/openlibrary")


if __name__ == "__main__":
    # Ensure that possible_services contains all services defined in docker-compose.yml
    buildable_services = get_buildable_services()
    for service in buildable_services:
        if service not in possible_services:
            raise ValueError(f"{service} is not in possible_services")

    args = get_args()
    commands = get_build_and_up_commands(args)
    env = get_environment_variables(args)

    if not args.staging and not args.local:
        git_sync_for_production()

    print(commands.build, env)
    print(run(commands.build.split(), env=env, text=True, check=True))
    do_run("docker-compose down")
    print(run(commands.up.split(), env=env, text=True, check=True))
    do_run("docker-compose logs -f --tail=10")
