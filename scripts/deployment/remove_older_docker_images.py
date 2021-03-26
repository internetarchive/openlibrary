#!/usr/bin/env python3

"""
Removes the oldest Docker images for a given repo so that only IMAGES_TO_KEEP or fewer
images remain.  Usage: remove_older_docker_images.py my_repo_name (default: "oldev")

% docker image ls oldev
REPOSITORY   TAG       IMAGE ID       CREATED        SIZE
oldev        latest    c468ac0b4ce7   2 hours ago   2.49GB
oldev        latest    68ac0b4ce7c4   4 hours ago   2.49GB
oldev        latest    ac0b4ce7c468   6 hours ago   2.49GB
oldev        latest    0b4ce7c468ac   8 hours ago   2.49GB

./remove_older_docker_images.py oldev  # would remove just 1 image created 8 hours ago
"""

import sys

import docker  # python3 -m pip install --upgrade pip

IMAGES_TO_KEEP = 3
try:
    _, REPO = sys.argv
except ValueError:
    REPO = "oldev"

client = docker.from_env()
image_dict = {image.attrs['Created']: image for image in client.images.list(name=REPO)}
images = sorted(image_dict, reverse=True)  # avoid dict changed size during iteration
print(f"Removing {len(images) - IMAGES_TO_KEEP} of {len(images)} {REPO} images:")
print("\n".join(images))
while len(images) > IMAGES_TO_KEEP:
    date_created = images.pop()
    print(f"Removing: {date_created}")
    client.images.remove(image_dict[date_created].id, force=True)
print(f"{REPO} images remaining:")
print("\n".join(image.attrs['Created'] for image in client.images.list(name=REPO)))
