# Welcome to the Installation Guide for Open Library Developers

1. [Pull code locally](#clone-the-open-library-repository)
2. [Install Docker](#install-docker) and [Test Docker](#test-docker)
3. [Prepare your system](#prepare-your-system)
4. [Build the project](#build-the-project)
5. [Run the app](#run-the-app)
6. [Update code dependencies](#code-updates)
7. [Teardown commands](#teardown-commands)
8. [Full reset](#fully-resetting-your-environment)
9. [Useful docker commands](#Useful-Runtime-Commands)
10. [Troubleshooting](#troubleshooting)
11. [Developing the Dockerfile](#Developing-the-Dockerfile) and [Debugging and Profiling docker images](#Debugging-and-Profiling-the-docker-image)
12. [Technical Notes](#Technical-notes)

## Pull code locally

Refer to these [these instructions](https://github.com/internetarchive/openlibrary/wiki/Git-Cheat-Sheet#forking-and-cloning-the-open-library-repository) to fork and clone the Open Library Repository:

```
git clone git@github.com:YOUR_USERNAME/openlibrary.git
```

> [!IMPORTANT]  
> When cloning the openlibrary repository, `SSH` (i.e. `git clone git@github.com:internetarchive/openlibrary.git`) must be used and *not* `https`, otherwise git submodules (e.g. `infogami` and `acs`) may not be fetched correctly. If you accidentally cloned the repository using `git clone https://...`, follow these steps: [Modifying a repository wrongly cloned with https](https://github.com/internetarchive/openlibrary/wiki/Git-Cheat-Sheet#modifying-a-repository-wrongly-cloned-with-https-or-one-that-is-missing-the-infogami-module).

## Prepare your system

> [!IMPORTANT]
> **Windows** users should see [Fix line endings, symlinks, and git submodules](https://github.com/internetarchive/openlibrary/wiki/Git-Cheat-Sheet#fix-line-endings-symlinks-and-git-submodules-only-for-windows-users-not-using-a-linux-vm). Skipping those steps will likely prevent the containers from coming up.

We recommend adjusting Docker's resource settings to use at least 4GB of RAM and 2GB of swap. The defaults of 2GB RAM and 1GB swap are likely to cause the error `Killed` when running `build-assets` to build `js` dependencies.

## Install Docker

**Linux** users (including those using a VM), can install `Docker Engine` or `Docker Desktop` (see the [Docker FAQ](https://docs.docker.com/desktop/faqs/linuxfaqs/) to determine which is right for you).

- Docker Engine: https://docs.docker.com/engine/install/#server (tested with 19.*)

**Windows** and **macOS** users should use `Docker Desktop` as of early 2023.

- Docker Desktop: https://docs.docker.com/get-docker/

For **macs** using an `M1 Chip`, please use [Docker Desktop >= 4.3.0](https://docs.docker.com/desktop/mac/release-notes/) and make sure that Docker Desktop Preferences `General / Use Docker Compose V2` is checked, enabling Docker to run without requiring `Rosetta 2`.

### Test Docker
Before continuing, ensure Docker is correctly configured by running the `hello-world` container.

```
docker run hello-world
```

The output should include a `Hello from Docker!` message that will confirm everything is working with Docker and you can continue.

If Docker is unable to pull the `hello-world:latest` image from Docker Hub, try disabling your VPN if one is installed.

Linux users, note the lack of `sudo` before `docker run hello-world`. See the [Linux post-installation instructions](https://docs.docker.com/engine/install/linux-postinstall/) if you see the following error:
```
docker: permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock: Post "http://%2Fvar%2Frun%2Fdocker.sock/v1.24/containers/create": dial unix /var/run/docker.sock: connect: permission denied.
See 'docker run --help'.
```

## Build the project

Change (`cd`) into the project root directory, where `compose.yaml` is (i.e. `path/to/your/forked/and/cloned/openlibrary`) and run:

```
docker compose build
```

This may take from a few minutes to more than 15 on older hardware. If for some reason the build fails, it's worth running again, as sometimes downloads time out.

> [!IMPORTANT]
> If you are running arm64 (see: [#10276](https://github.com/internetarchive/openlibrary/issues/10276)) and this command fails, [for now](https://github.com/internetarchive/openlibrary/issues/10276#issuecomment-2573844779) you may have to run [this workaround](https://github.com/internetarchive/openlibrary/issues/10276#issuecomment-2576717718).

If you **hit errors** while building the project, please jump to the [Troubleshooting Guide](#troubleshooting) and [browse our open and closed docker issues](https://github.com/internetarchive/openlibrary/issues?q=is%3Aissue%20label%3A%22Module%3A%20Docker%22%20)

## Run the app
```sh
docker compose up    # Ctrl-C to stop
docker compose up -d # or, start in detached (silent) mode
```

You will know the environment is done loading when the text stops furiously scrolling by and you see the following repeating every few seconds on the console:

```
infobase_1      | 172.19.0.5:45716 - - [16/Feb/2023 16:54:10] "HTTP/1.1 GET /openlibrary.org/log/2023-02-16:0" - 200 OK
infobase_1      | 172.19.0.5:45730 - - [16/Feb/2023 16:54:15] "HTTP/1.1 GET /openlibrary.org/log/2023-02-16:0" - 200 OK
infobase_1      | 172.19.0.5:41790 - - [16/Feb/2023 16:54:20] "HTTP/1.1 GET /openlibrary.org/log/2023-02-16:0" - 200 OK
```

At this point, visit http://localhost:8080 and you should see the Open Library banner image with "development version" emblazoned upon it to signify that it's running from your local development server. From here you can [log in locally](http://localhost:8080/account/login).

As a next step, we encourage you to proceed to the ["Getting Started" guide](https://github.com/internetarchive/openlibrary/blob/master/CONTRIBUTING.md) for tips on using git, finding a good first issue to work on, and understanding the codebase.

## Code Updates

> [!TIP]
> When the Open Library code within your local docker image falls behind the code upstream, you can typically ```git pull`` the latest changes from github without having to rebuild all your docker image(s).`

These instructions are intended for contributors who have **already** `built` Open Library using docker, but the contributor may have made or pulled changes to their codebase that conflict with what's baked into the image.

Building the Open Library project can take a while and most of its images don't change often, so we only want to rebuild them when necessary. When a docker image is created, its dependencies (`pip`, `npm`, `apt-get`) are frozen in time and will be inherited by any container based from it.

Occasionally, there will be cases when changes we pull or make to our codebase will require changes to our docker environment -- for instance, the addition of a python dependency, npm package, or changes to our js/vue/less that require assets to be rebuilt. In most of these cases, because the `openlibrary` repo is volume mounted, we can use the pattern `docker compose run --rm home <command>` to spin up a temporary container with instructions that run build commands to ensure our environment has all the necessary dependencies. For instance, if changes have been made to:

| Change | Fix  |
|------|-----------|
| **`pip` python package dependencies** (e.g. `requirements.txt`) | rebuild just the `home` image with: ```docker compose build home``` |
| **`npm` packages** | run ```docker compose run --rm home npm install --no-audit``` (see [#2032](https://github.com/internetarchive/openlibrary/issues/2032) for why) |
| **`js`, `vue`, `css`/`less`** and other static front-end assets | perform a complete rebuild of assets using ```docker compose run --rm home npm run build-assets```, or follow the [Frontend Guide](https://github.com/internetarchive/openlibrary/wiki/Frontend-Guide#css-js-and-html) to rebuild only certain asset types. |

> [!WARNING]
> In the off-chance you find yourself needing to edit core dependencies like `apt-get` or networking, you will most likely need to do a [full rebuild](#fully-resetting-your-environment). If you are making this sort of change, you will know exactly what you are doing. See [Developing the Dockerfile](#developing-the-dockerfile).

> [!TIP]
> In addition to using ```docker compose run --rm home <command>``` to spin up a temporary container to produce an artifact, you can also use ```docker compose exec -it home <command>``` to run the fix directly on the running container. This may also allow you to test one-off changes that might otherwise require a [full rebuild](#fully-resetting-your-environment). Use caution with this approach as you may end up breaking your container and causing a restart loop.

## Teardown commands

```sh
cd path/to/your/cloned/openlibrary
# stop the app (if started in detached mode)
docker compose down

# start specific service
docker compose up --no-deps -d solr

# remove all volumes (i.e. reset all databases); perform WHILE RUNNING
docker compose stop
docker compose rm -v
```

This exposes the following ports:

| Port | Service                |
| ---- | ---------------------- |
| 8080 | Open Library main site |
| 7000 | Infobase               |
| 8983 | Solr                   |
| 7075 | Cover store            |

For example, to access Solr admin, go to http://localhost:8983/solr/admin/

## Fully Resetting Your Environment

Been away for a while? Are you getting strange errors you weren't getting before? Sometimes changes are made to the docker configs which could cause your local environment to break. To do a full reset of your docker environment so that you have the latest of everything:

```
# Stop the site
docker compose down

# Build the latest oldev image, without cache, whilst also pulling the latest olbase image from docker hub.
# This can take from a few minutes to more than 20 on older hardware.
docker compose build --pull --no-cache

# Remove any old containers/images
# If you use docker for other things, and have containers/images you don't want to lose, be careful with this. But you likely don't :)
docker container prune --filter label="com.docker.compose.project=openlibrary" --force
docker image prune --filter label="com.docker.compose.project=openlibrary" --force

# Remove volumes that might have outdated dependencies/code
docker volume rm openlibrary_ol-build openlibrary_ol-nodemodules openlibrary_ol-vendor

# Bring it back up again
docker compose up  # or docker compose up -d
```

## Troubleshooting

### "openlibrary-web-1 | exec docker/ol-web-start.sh: no such file or directory" OR "/usr/bin/env: 'python\r': No such file or directory"

These errors may appear in different containers or with different file names, but look for file-not-found type errors where `\r` is in the filename, or there's `exec`, a path that seems to exist, and a `no such file or directory` error, e.g. `openlibrary-web-1 | exec docker/ol-web-start.sh: no such file or directory`

The likely cause here is that text files were given CRLF line endings during cloning+checkout. See [Fix line endings, symlinks, and git submodules](https://github.com/internetarchive/openlibrary/wiki/Git-Cheat-Sheet#fix-line-endings-symlinks-and-git-submodules-only-for-windows-users-not-using-a-linux-vm).

Note: after fixing this error, be on the lookout for another error that will appear almost immediately after running `docker compose up` that mentions something about the `role` of `openlibrary` not existing. Read on for how to address that.

### An error similar to: FATAL: role "openlibrary" does not exist

Look for errors that appear very soon after running `docker compose up` that come from the `openlibrary-db-1` container when it first starts mentioning something about the `role` of `openlibrary` not existing.

In this case, try the steps in [Fully Resetting Your Environment](#fully-resetting-your-environment)

Note: please update this README with the exact wording of the error if you run into it.

### "OSError: [Errno 12] Cannot allocate memory: '/openlibrary/openlibrary/core'"

`OSError: [Errno 12] Cannot allocate memory:` could occur in conjunction with `/openlibrary/openlibrary/core` or any number of files. Simply try increasing free RAM or increasing swap/page file/virtual memory for your operating system.

### "No module named 'infogami'"

The following should populate the target of the `infogami` symbolic link (i.e. `vendor/infogami/`):
```
cd path/to/your/cloned/openlibrary
git submodule init; git submodule sync; git submodule update
```
Windows users may need to see [Fix line endings, symlinks, and git submodules](https://github.com/internetarchive/openlibrary/wiki/Git-Cheat-Sheet#fix-line-endings-symlinks-and-git-submodules-only-for-windows-users-not-using-a-linux-vm).

### "no configuration file provided: not found" when running `docker compose <command>`

Ensure you're running `docker compose` commands from within the `local-openlibrary-dev-directory`.

### ConnectionError: HTTPConnectionPool(host='solr', port=8983)
The full error is something like (line breaks added):
```
/openlibrary/openlibrary/templates/home/index.html: error in processing
 template: ConnectionError: HTTPConnectionPool(host='solr', port=8983):
Max retries exceeded with url: /solr/openlibrary/select (Caused by
NameResolutionError("<urllib3.connection.HTTPConnection object at
0x77a95c4e7f90>: Failed to resolve 'solr' ([Errno -2] Name or service
not known)")) (falling back to default template)
```
The following should get everything running again:
```sh
docker compose down
docker container ls -a
# If you see any openlibrary container here, remove them with `docker rm -f NAME`
docker network ls
# If you see any open library networks here, remove them with `docker network rm NAME
docker compose up  # or docker compose up -d
```
If you're curious and want to understand what happened, and why the above likely fixes it, first, verify the `solr` container is running (e.g. `docker ps | grep solr`, and then look for something like `openlibrary-solr-1` that isn't `solr-updater`.) If the `solr` container isn't running, simply start it with `docker compose up solr` (or `docker compose up -d solr`) and that should fix it. If `solr` is running, verify too that you can also connect to solr at http://localhost:8983/solr/#/. If you can't, something else is likely wrong.

If the `solr` container is running and the error persists, one cause seems to be that the containers sometimes become disconnected from `openlibrary_webnet` (though this could happen with `openlibrary_dbnet` too). `openlibrary-web-1`/`web` should be connected to both `openlibrary_webnet` and `openlibrary_dbnet`, but when this problem occurs, instead only one is connected. E.g.:
```sh
docker container inspect --format '{{.NetworkSettings.Networks}}' openlibrary-web-1
# output: map[openlibrary_dbnet:0xc00037c1c0]
```
Because you've read this far, you can now directly fix the problem without removing the containers and networks. Simply reconnect the container to the network:
```
docker network connect openlibrary_webnet openlibrary-web-1  # or `openlibrary_dbnet` as the case may be.
docker container inspect --format '{{.NetworkSettings.Networks}}' openlibrary-web-1
# output: map[openlibrary_dbnet:0xc00016c460 openlibrary_webnet:0xc00016c540]
```
No restart is required. If `webnet` no longer exists, recreating it _should_ fix things: `docker network create openlibrary_webnet`.

To understand a bit more about what's going on here, there are docker networks configured in `compose.yaml`. The containers should be able to resolve one another based on the container names (e.g. `web` and `solr`), assuming `compose.yaml` has them on the same netork. For more, see [Networking in Compose](https://docs.docker.com/compose/networking/).

## Technical notes

re: `docker-compose` and `docker compose`

As of early 2023, following the installation instructions on Docker's website will install either Docker Desktop, which includes Docker Compose v2, or `docker-ce` and `docker-compose-plugin` (Linux only), both of which obviate the need to install `docker-compose` v1 separately.

Further, Compose V1 will [no longer be supported by the end of June 2023](https://docs.docker.com/compose/compose-v2/) and will be removed from Docker Desktop. These directions are written for Compose V2, hence the use of `docker compose` rather than `docker-compose`. `docker compose` is [meant to be a drop-in replacement](https://docs.docker.com/compose/compose-v2/#differences-between-compose-v1-and-compose-v2) for `docker-compose`.

If for some reason one cannot use a current version of Docker that includes the Docker Compose plugin, it can [be installed separately](https://docs.docker.com/compose/install/)

Finally, as of this writing (early 2023), the `docker-compose` that comes with relatively recent Linux distributions (e.g. Ubuntu 22.04) still works if it is already installed.

## Useful Runtime Commands

See Docker's docs for more: https://docs.docker.com/compose/reference/overview

```bash
# Read a service's logs (replace `web` with service name)
docker compose logs web # Show all logs (onetime)
docker compose logs -f --tail=10 web # Show last 10 lines and follow

# Analyze a container
docker compose exec web bash # Launch terminal in `web` service

# Run tests
docker compose run --rm home make test

# Install Node.js modules (if you get an error running tests)
# Important: npm jobs need to be run inside the Docker environment.
docker compose run --rm home npm install --no-audit
# build JS/CSS assets:
docker compose run --rm home npm run build-assets
```

https://github.com/internetarchive/openlibrary/wiki/Deployment-Guide#ol-web1

```bash
# Launch a temporary container and run tests
docker compose run --rm home make test

# Run Open Library using a local copy of Infogami for development

docker compose down && \
    docker compose -f compose.yaml -f compose.override.yaml -f compose.infogami-local.yaml up -d && \
    docker compose logs -f --tail=10 web

# In your browser, navigate to http://localhost:8080

# To test Open Library on another version of Python, modify Dockerfile.olbase and then
# rebuild olbase (see above) and oldev (`docker compose build`)
```

## Developing the Dockerfile

If you need to make changes to the dependencies in Dockerfile.olbase, rebuild it with:

```bash
docker build -t openlibrary/olbase:latest -f docker/Dockerfile.olbase . # 30+ min (Win10Home/Dec 2018)
```

This image is automatically rebuilt on deploy by ol-home0 and is pushed to at https://hub.docker.com/r/openlibrary/olbase.

If you're making changes you think might affect Docker Hub, you can create a branch starting with `docker-test`, e.g. `docker-test-py2py3` (no weird chars), to trigger a build in docker hub at e.g. `openlibrary/olbase:docker-test-py2py3`.


## Debugging and Profiling the Docker Image

See [Debugging and Performance Profiling](https://github.com/internetarchive/openlibrary/wiki/Debugging-and-Performance-Profiling) for more information on how to attach a debugger when running in the Docker Container.


