FROM ubuntu:24.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    git \
    cmake \
    g++ \
    gperf \
    make \
    libssl-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

RUN git clone --recursive https://github.com/tdlib/telegram-bot-api.git

WORKDIR /src/telegram-bot-api

RUN mkdir build && \
    cd build && \
    cmake -DCMAKE_BUILD_TYPE=Release .. && \
    cmake --build . --target telegram-bot-api -j2


FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    libssl3 \
    zlib1g \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder \
    /src/telegram-bot-api/build/telegram-bot-api \
    /usr/local/bin/telegram-bot-api

RUN mkdir -p /var/lib/telegram-bot-api

WORKDIR /var/lib/telegram-bot-api

EXPOSE 8081

ENTRYPOINT ["telegram-bot-api"]