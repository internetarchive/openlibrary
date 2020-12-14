# Welcome to the new Docker based Open Library development environment!

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

### Prerequisites & Troubleshooting

Before attempting to build openlibrary using the docker instructions below, please follow this checklist. If you encounter an error, this section may serve as a troubleshooting guide:

- Install `docker-ce`: https://docs.docker.com/get-docker/ (tested with version 19.*)
- Install `docker-compose`: https://docs.docker.com/compose/install/
- Make sure you `git clone` openlibrary using `ssh` instead of `https` as git submodules (e.g. `infogami` and `acs`) may not fetch correctly otherwise. You can modify an existing openlibrary repository using `git remote rm origin` and then `git remote add origin git@github.com:internetarchive/openlibrary.git`

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

Note: You must build `olbase` first before `oldev`. `olbase` is intended to be the core Open Library image, acting as a base for production and development. `oldev` adds a pre-populated development database and any other tools that are helpful for local development and can only be run once on any given `olbase` image. This development environment also has a small number of books in the database for testing purposes. Currently (Oct 2018) these docker images are only intended for development environments.

This exposes the following ports:

| Port | Service                |
| ---- | ---------------------- |
| 8080 | Open Library main site |
| 7000 | Infobase               |
| 8983 | Solr                   |

For example, to access Solr admin, go to http://localhost:8983/solr/admin/

## Code Updates

While running the `oldev` container, gunicorn is configured to auto-reload modified files. To see the effects of your changes in the running container, the following apply:

- **Editing python files or web templates?** Simply save the file; gunicorn will auto-reload it.
- **Editing frontend css or js?** Run `docker-compose exec home npm run-script build-assets`. This will re-generate the assets in the persistent `ol-build` volume mount (so the latest changes will be available between stopping / starting  `web` containers). Note, if you want to view the generated output you will need to attach to the container (`docker-compose exec web bash`) to examine the files in the volume, not in your local dir.
- **Editing pip packages?** Rebuild the `home` service: `docker-compose build home`
- **Editing npm packages?** Run `docker-compose exec home npm install` (see [#2032](https://github.com/internetarchive/openlibrary/issues/2032) for why)
- **Editing core dependencies?** You will most likely need to do a full rebuild. This shouldn't happen too frequently. If you are making this sort of change, you will know exactly what you are doing ;)

## Useful Runtime Commands

See Docker's docs for more: https://docs.docker.com/compose/reference/overview

```bash
# Read a service's logs (replace `web` with service name)
docker-compose logs web # Show all logs (onetime)
docker-compose logs -f --tail=10 web # Show last 10 lines and follow

# Analyze a container
docker-compose exec home bash # Launch terminal in `home` service

# Run tests while container is running
docker-compose exec home make test

# Install Node.js modules (if you get an error running tests)
# Important: npm jobs need to be run inside the Docker environment.
docker-compose exec home npm install
# build JS/CSS assets:
docker-compose exec home npm run build-assets
```

## Rebuilding the Docker Image

If you need to make changes to the dependencies in Dockerfile.olbase, rebuild it with:

```bash
docker build -t openlibrary/olbase:latest -f docker/Dockerfile.olbase . # 30+ min (Win10Home/Dec 2018)
```

This image is automatically rebuilt when master is pushed to at https://hub.docker.com/r/openlibrary/olbase .

If you're making changes you think might affect Docker Hub, you can create a branch starting with `docker-test`, e.g. `docker-test-py2py3` (no weird chars), to trigger a build in docker hub at e.g. `openlibrary/olbase:docker-test-py2py3`.

## Updating the Docker Image

Pull the changes into your openlibrary repository: ```git pull```

When pulling down new changes you will need to rebuild the JS/CSS assets:
```bash
# build JS/CSS assets:
docker-compose exec home npm run build-assets
```
Note: This is only if you already have an existing docker image, this command is unnecessary the first time you build.

## Other Commands

https://github.com/internetarchive/openlibrary/wiki/Deployment-Guide#ol-web1

```bash
# Launch a temporary container and run tests
docker-compose run --rm home make test

# Launch a temporary container on Python 3 using the local Infogami and then open in local webbrowser
# PYENV_VERSION can be set to: 2.7.6, 3.8.6, or 3.9.0
docker-compose down && \
    PYENV_VERSION=3.8.6 docker-compose -f docker-compose.yml -f docker-compose.infogami-local.yml up -d && \
    docker-compose logs -f --tail=10 web
# In your browser, navigate to http://localhost:8080
```
