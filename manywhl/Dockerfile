FROM python:3.14-slim AS kajol-manywhl

WORKDIR /app
COPY kajol /usr/local/lib/python3.14/site-packages/kajol

RUN python -m pip install "tomlkit" "requests" "packaging" "llvmlite" \
                          "shellingham"
RUN python -m kajol python install 3.15.0rc1
RUN python -m kajol python install 3.14
#RUN python -m kajol python install 3.13
#RUN python -m kajol python install 3.12

CMD ["bash"]