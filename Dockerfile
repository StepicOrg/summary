FROM ubuntu:14.04

RUN apt-get update -y && \
    apt-get install -y software-properties-common

RUN add-apt-repository -y ppa:mc3man/trusty-media \
    && apt-get update -y \
    && apt-get dist-upgrade -y \
    && apt-get install -y ffmpeg

RUN apt-get update && \
    apt-get install -y \
    wget \
    build-essential \
    cmake \
    git \
    unzip \
    pkg-config \
    libswscale-dev \
    python3-dev \
    python3-numpy \
    libtbb2 \
    libtbb-dev \
    libpng-dev \
    libjasper-dev \
    libavformat-dev \
    && apt-get -y clean all \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /

RUN wget https://github.com/Itseez/opencv/archive/3.1.0.zip \
	&& unzip 3.1.0.zip \
	&& rm 3.1.0.zip \
	&& mkdir opencv-3.1.0/build \
	&& cd opencv-3.1.0/build \
	&& cmake .. \
	&& make -j8 \
	&& make install \
	&& rm -rf /opencv-3.1.0

RUN mkdir /home/synopsis
COPY . /home/synopsis

RUN apt-get update && \
    apt-get upgrade && \
    apt-get install -y python3-pip

RUN apt-get install -y python3-scipy \
    && pip3 install -r /home/synopsis/requirements.txt

RUN mkdir /home/synopsis/result
