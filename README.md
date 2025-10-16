Dependencies:
- Linux
- docker
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

Initial Setup:
```sh
git clone --recurse-submodules https://github.com/jlmcmchl/compound-eyes
```

Build mrcal:
```sh
docker build -t mrcal-builder -f Dockerfile.mrcal .
docker run --rm -t mrcal-builder -v $(pwd)/mrcal:/mrcal -w /mrcal make
```

Run:
```sh
PYTHONPATH=$PYTHONPATH:./mrcal uv run main.py
```