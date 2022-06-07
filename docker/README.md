# Welcome to the Docker Installation Guide for Open Library Developers

## Prerequisites & Troubleshooting

Before attempting to build openlibrary using the Docker instructions below, please follow this checklist. If you encounter an error, this section may serve as a troubleshooting guide:

- Install `docker-ce`: https://docs.docker.com/get-docker/ (tested with version 19.*)
- Install `docker-compose`: https://docs.docker.com/compose/install/
- Make sure you `git clone` openlibrary using `ssh` instead of `https` as git submodules (e.g. `infogami` and `acs`) may not fetch correctly otherwise. You can modify an existing openlibrary repository using `git remote rm origin` and then `git remote add origin git@github.com:internetarchive/openlibrary.git`. Then run `git submodule init; git submodule sync; git submodule update` to get rid of the issue.

## Setup/Teardown Commands

### For Windows Users Only

**Note:** If you get permission issues while executing these commands please run git bash shell as an Administrator.

```bash
# Configure Git to convert CRLF to LF line endings on commit
git config --global core.autocrlf input

# Enable Symlinks
git config core.symlinks true

# Reset the repo (removes any changes you've made to files!)
git reset --hard HEAD
```

### For Users of Macs Containing an M1 Chip

Please use [Docker Desktop >= 4.3.0](https://docs.docker.com/desktop/mac/release-notes/) and make sure that Docker Desktop Preferences `General / Use Docker Compose V2` is checked so that it is no longer required to install Rosetta 2 to run Docker.

If you are experiencing issues building JS, you may need to increase the RAM available to Docker. The defaults of 2GB ram and 1GB Swap are not enough. We recommend requirements of 4GB ram and 2GB swap. This resolved the error message of `Killed` when running `build-assets`.

### For All Users
All commands are from the project root directory:

```bash
# build images
docker-compose build # 15+ min (Win10Home/Dec 2018)

# start the app
docker-compose up    # Ctrl-C to stop
docker-compose up -d # or, start in detached (silent) mode

# stop the app (if started in detached mode)
docker-compose down

# start specific service
docker-compose up --no-deps -d solr

# remove all volumes (i.e. reset all databases); perform WHILE RUNNING
docker-compose stop
docker-compose rm -v
```

This exposes the following ports:

| Port | Service                |
| ---- | ---------------------- |
| 8080 | Open Library main site |
| 7000 | Infobase               |
| 8983 | Solr                   |
| 7075 | Cover store            |

For example, to access Solr admin, go to http://localhost:8983/solr/admin/

## Code Updates

While running the `oldev` container, gunicorn is configured to auto-reload modified files. To see the effects of your changes in the running container, the following apply:

- **Editing Python files or web templates (e.g. HTML)?** Simply save the file; gunicorn will auto-reload it.
    - Note that the home page `openlibrary\templates\home` is cached and each change will take time to apply unless you run `docker-compose restart memcached` which restarts the `memecached` container and renders the change directly. Changing any other web template, auto applies and doesn't need any further commands.
- **Editing frontend css or js?** Run `docker-compose run --rm home npm run-script build-assets`. This will re-generate the assets in the persistent `ol-build` volume mount (so the latest changes will be available between stopping / starting  `web` containers). Note, if you want to view the generated output you will need to attach to the container (`docker-compose exec web bash`) to examine the files in the volume, not in your local dir.
- **Watching for file changes (frontend)** To watch for js file changes, run `docker-compose run --rm home npm run-script watch`. Similarly, for css (.less) files, run `docker-compose run --rm home npm run-script watch-css`.
- **Editing pip packages?** Rebuild the `home` service: `docker-compose build home`
- **Editing npm packages?** Run `docker-compose run --rm home npm install` (see [#2032](https://github.com/internetarchive/openlibrary/issues/2032) for why)
- **Editing core dependencies?** You will most likely need to do a full rebuild. This shouldn't happen too frequently. If you are making this sort of change, you will know exactly what you are doing ;) See [Developing the Dockerfile](#developing-the-dockerfile).

## Useful Runtime Commands

See Docker's docs for more: https://docs.docker.com/compose/reference/overview

```bash
# Read a service's logs (replace `web` with service name)
docker-compose logs web # Show all logs (onetime)
docker-compose logs -f --tail=10 web # Show last 10 lines and follow

# Analyze a container
docker-compose exec web bash # Launch terminal in `web` service

# Run tests
docker-compose run --rm home make test

# Install Node.js modules (if you get an error running tests)
# Important: npm jobs need to be run inside the Docker environment.
docker-compose run --rm home npm install
# build JS/CSS assets:
docker-compose run --rm home npm run build-assets
```

## Fully Resetting Your Environment

Been away for a while? Are you getting strange errors you weren't getting before? Sometimes changes are made to the docker configs which could cause your local environment to break. To do a full reset of your docker environment so that you have the latest of everything:

```
# Stop the site
docker-compose down

# Build the latest oldev image, whilst also pulling the latest olbase image from docker hub
# (Takes a while; ~20min for me)
docker-compose build --pull

# Remove any old containers; if you use docker for something special, and have containers you don't want to lose, be careful with this. But you likely don't :)
docker container prune

# Remove volumes that might have outdated dependencies/code
docker volume rm openlibrary_ol-build openlibrary_ol-nodemodules openlibrary_ol-vendor

# Bring it back up again
docker-compose up -d
```

## Developing the Dockerfile

If you need to make changes to the dependencies in Dockerfile.olbase, rebuild it with:

```bash
docker build -t openlibrary/olbase:latest -f docker/Dockerfile.olbase . # 30+ min (Win10Home/Dec 2018)
```

This image is automatically rebuilt on deploy by ol-home0 and is pushed to at https://hub.docker.com/r/openlibrary/olbase.

If you're making changes you think might affect Docker Hub, you can create a branch starting with `docker-test`, e.g. `docker-test-py2py3` (no weird chars), to trigger a build in docker hub at e.g. `openlibrary/olbase:docker-test-py2py3`.

## Updating the Docker Image

Pull the changes into your openlibrary repository: ```git pull```

When pulling down new changes you will need to rebuild the JS/CSS assets:
```bash
# build JS/CSS assets:
docker-compose run --rm home npm run build-assets
```
Note: This is only if you already have an existing docker image, this command is unnecessary the first time you build.

## Other Commands

https://github.com/internetarchive/openlibrary/wiki/Deployment-Guide#ol-web1

```bash
# Launch a temporary container and run tests
docker-compose run --rm home make test

# Run Open Library using a local copy of Infogami for development

docker-compose down && \
    docker-compose -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.infogami-local.yml up -d && \
    docker-compose logs -f --tail=10 web

# In your browser, navigate to http://localhost:8080

# To test Open Library on another version of Python, modify Dockerfile.olbase and then
# rebuild olbase (see above) and oldev (`docker-compose build`)
```
