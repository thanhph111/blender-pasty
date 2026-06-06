FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        bzip2 \
        ca-certificates \
        coreutils \
        curl \
        dbus-x11 \
        findutils \
        git \
        kmod \
        libdecor-0-0 \
        libegl-mesa0 \
        libegl1 \
        libfontconfig1 \
        libfreetype6 \
        libgl1 \
        libgl1-mesa-dri \
        libgles2 \
        libice6 \
        libsm6 \
        libwayland-egl1 \
        libx11-6 \
        libx11-xcb1 \
        libxcursor1 \
        libxext6 \
        libxfixes3 \
        libxi6 \
        libxkbcommon0 \
        libxrandr2 \
        libxrender1 \
        libxxf86vm1 \
        mesa-utils \
        mesa-utils-extra \
        python3 \
        python3-venv \
        sway \
        tar \
        unzip \
        wl-clipboard \
        wtype \
        xauth \
        xclip \
        xvfb \
        xz-utils \
        ydotool \
        ydotoold \
    && rm -rf /var/lib/apt/lists/*

RUN curl https://mise.run | sh

ENV PATH="/root/.local/bin:${PATH}" \
    MISE_TRUSTED_CONFIG_PATHS=/workspace \
    VIRTUAL_ENV=""

WORKDIR /workspace
