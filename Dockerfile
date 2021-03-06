FROM ubuntu:16.10

RUN apt-get update -y && \
    apt-get install -y software-properties-common

RUN apt-get update -y \
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
    libboost-all-dev \
    && apt-get -y clean all \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /

RUN wget https://github.com/Itseez/opencv/archive/3.1.0.zip \
    && unzip 3.1.0.zip \
    && rm 3.1.0.zip \
    && mkdir opencv-3.1.0/build \
    && cd opencv-3.1.0/build \
    # https://github.com/opencv/opencv/issues/6517
    && cmake -DENABLE_PRECOMPILED_HEADERS=OFF .. \
    && make -j8 \
    && make install \
    && rm -rf /opencv-3.1.0

RUN mkdir /home/synopsis
COPY . /home/synopsis

RUN apt-get update -y && \
    apt-get upgrade -y && \
    apt-get install -y python3-pip

RUN apt-get install -y pandoc

RUN apt-get install -y python3-scipy \
    && pip3 install -r /home/synopsis/requirements.txt

RUN wget https://github.com/Breakthrough/PySceneDetect/archive/v0.4.tar.gz \
    && tar -xzf v0.4.tar.gz \
    && cd PySceneDetect-0.4 \
    && python3 setup.py install \
    && cd ../ \
    && rm v0.4.tar.gz

# SSH
RUN apt-get install -y openssh-server
RUN mkdir /var/run/sshd
RUN echo 'root:root' | chpasswd
RUN sed -i 's/PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config

# SSH login fix. Otherwise user is kicked off after login
RUN sed 's@session\s*required\s*pam_loginuid.so@session optional pam_loginuid.so@g' -i /etc/pam.d/sshd

ENV NOTVISIBLE "in users profile"
RUN echo "export VISIBLE=now" >> /etc/profile

EXPOSE 22
CMD ["/usr/sbin/sshd", "-D"]
