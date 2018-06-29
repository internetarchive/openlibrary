# Build images

```
docker build -t olbase:latest -f docker/Dockerfile.olbase .

docker build -t oldev:latest -f docker/Dockerfile.oldev .
```

# Run container

Interactive, all services:

`docker run -it --rm -p80:80 -p7000:7000 -p8983:8983 oldev`

Interactive bash (for checking the container):

`docker run -it --rm -p80:80 -p7000:7000 -p8983:8983 oldev bash`

Background, detached, mode:

`docker run -d -p80:80 -p7000:7000 -p8983:8983 oldev`

