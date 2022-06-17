FROM python:3.10.5

# Install and fix dependencies
RUN apt-get -y update && \
    apt-get install -y --fix-missing \
    build-essential \
    cmake \
    gfortran \
    git \
    wget \
    curl \
    graphicsmagick \
    libgraphicsmagick1-dev \
    libatlas-base-dev \
    libavcodec-dev \
    libavformat-dev \
    libgtk2.0-dev \
    libjpeg-dev \
    liblapack-dev \
    libswscale-dev \
    pkg-config \
    python3-dev \
    python3-numpy \
    software-properties-common \
    zip \
    unzip

# Install dlib for face_recongition package
RUN cd ~ && \
    mkdir -p dlib && \
    git clone -b 'v19.9' --single-branch https://github.com/davisking/dlib.git dlib/ && \
    cd  dlib/ && \
    python3 setup.py install --yes USE_AVX_INSTRUCTIONS

# Install Chrome and Chromedriver for Selenium
COPY install-selenium.sh .
RUN  chmod +x install-selenium.sh && \
    ./install-selenium.sh && \
    mv chromedriver/ app/

# Install other Python packages
COPY requirements.txt .
RUN pip3 install -r requirements.txt

# Clean up
RUN cd ~ && \
    rm google-chrome-stable_current_amd64.deb && \
    rm chromedriver_linux64.zip && \
    rm install-selenium.sh && \
    apt-get clean && rm -rf /tmp/* /var/tmp/

WORKDIR /app

COPY ./app .