# Welcome to the new Docker based Open Library development environment!

These current Dockerfiles are designed to be an alternative to the previous Vagrant based development environment.

## Setup/Teardown Commands

### For Windows Users Only

**Note:**
If you get permission issues while executing these commands please run git bash shell as an Administrator.

1. Set the line endings to type `input` by executing the following command:

   ```bash
   # Configure Git on Windows to properly handle line endings so Git will convert CRLF to LF on commit
   git config --global core.autocrlf input
   ```

2. Check whether `symlinks` are enabled or not. `openlibrary` makes use of symlinks which, by default, git on Windows checks out as plain text files. You can check that by executing the following command:

   ```bash
   git config core.symlinks
   ```

3. If `symlinks` are enabled then go to the next step. If `symlinks` are not enabled then enable it by executing the following command:

   ```bash
   git config core.symlinks true
   ```

4. Then hard reset the repository so that git will create proper symlinks by executing the following command:

   ```bash
   git reset --hard HEAD
   ```

5. Continue setup as shown below.

All commands are from the docker directory:

```bash
# build images
docker build -t olbase:latest -f Dockerfile.olbase ..
docker build -t oldev:latest -f Dockerfile.oldev ..
docker build -t olsolr:latest -f Dockerfile.olsolr ..

# start the app
docker-compose up # Ctrl-C to stop
docker-compose up -d # detached (silent) mode

# stop the app
docker-compose down

# start specific service
docker-compose up --no-deps -d solr

# remove all volumes (i.e. reset all databases); perform WHILE RUNNING
docker-compose stop
docker-compose rm -v
```

Note: You must build `olbase` first before `oldev`. `olbase` is intended to be the core Open Library image, acting as a base for production and development. `oldev` adds a pre-populated development database and any other tools that are helpful for local development and can only be run once on any given `olbase` image. Currently (Oct 2018) these docker images are only intended for development environments.

This exposes the following ports:

| Port | Service                |
| ---- | ---------------------- |
| 8080 | Open Library main site |
| 7000 | Infobase               |
| 8983 | Solr                   |

To access Solr admin:
http://localhost:8983/solr/admin/

If you are using Docker for Mac or Docker for Windows (or the older Docker Toolbox), use the Docker Machine IP instead of `localhost`. For example, `http://192.168.99.100:8080`. To find the IP address, use the command `docker-machine ip`. On Mac you can use the shell command `open http://$(docker-machine ip):8080`.

You can customise the host ports by modifying the `-p` publish mapping in the `docker run` command to suit your development environment.

## Code Updates

While running the `oldev` container, gunicorn is configured to auto-reload modified files. To see the effects of your changes in the running container, the following apply:

- Editing python files or web templates => simply save the file, gunicorn will auto-reload it.
- Working on frontend css or js => you must run `docker-compose exec web make css js`. This will re-generate the assets in the persistent `ol-build` volume mount, so the latest changes will be available between stopping / starting and removing `web` containers. Note, if you want to view the generated output you will need to attach to the container (`docker-compose exec web bash`) to examine the files in the volume, not in your local dir.
- Adding or changing core dependencies => you will most likely need to rebuild both `olbase` and `oldev` images. This shouldn't happen too frequently. If you are making this sort of change, you will know exactly what you are doing ;)

## Useful Runtime Commands

See the docs for more: https://docs.docker.com/compose/reference/overview

```bash
# Read a service's logs (replace `web` with service name)
docker-compose logs web # Show all logs (onetime)
docker-compose logs -f --tail=10 web # Show last 10 lines and follow

# Analyze a container
docker-compose exec web bash # Launch terminal in `web` service

# Run tests while container is running
docker-compose exec web make test

# Install Node.js modules (if you get an error running tests)
# Important: npm jobs need to be run inside the Docker environment.
docker-compose exec web npm install
# build JS/CSS assets:
docker-compose exec web npm run build-assets
```

## Other Commands

```bash
# Run tests in a temporary container
docker-compose run --rm web make test
```

## TODO

- Fix symlinks that are causing a problem in Windows, see issue https://github.com/internetarchive/openlibrary/issues/1051
