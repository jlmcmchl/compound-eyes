Dependencies:
- Linux
- docker
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

Initial Setup:
```sh
git clone https://github.com/jlmcmchl/compound-eyes
```

Build mrcal:
```sh
docker build -t mrcal -f Dockerfile.mrcal .
```

Run:
```sh
uv run main.py
```