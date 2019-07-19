FROM alvarezwegaw/python-gdal:2.7.16

#Install needed packages (GLU + OPENGL+ CMAKE + x11 libraries) + cleanup
RUN apt-get update && apt-get install -y \
  libgl1-mesa-dev \
  libglu1-mesa-dev \
  cmake \
  libxrandr-dev libxinerama-dev libxi-dev libxcursor-dev \
  && rm -rf /var/lib/apt/lists/*

# upgrade pip
RUN pip install --upgrade pip

# add requirements.txt to the image
COPY requirements.txt /requirements.txt

# install python dependencies
RUN pip install -r requirements.txt

#uninstall and reinstall gdal after numpy so it can use _gdal_arrays
RUN pip uninstall gdal -y \ 
  && pip install numpy \
  && pip install GDAL==$(gdal-config --version) --global-option=build_ext --global-option="-I/usr/include/gdal"

# copy let it snow source files
COPY let-it-snow-16-corrected /let-it-snow

# download and istall OTB
RUN wget https://www.orfeo-toolbox.org/packages/OTB-6.6.1-Linux64.run \
   && chmod +x OTB-6.6.1-Linux64.run \
   && ./OTB-6.6.1-Linux64.run \
   && rm OTB-6.6.1-Linux64.run \
   && . /OTB-6.6.1-Linux64/otbenv.profile

# Add env variables for OTB
ENV OTB_APPLICATION_PATH=/OTB-6.6.1-Linux64/lib/otb/applications:$OTB_APPLICATION_PATH \
  PYTHONPATH=/OTB-6.6.1-Linux64/lib/python:$PYTHONPATH \
  # ENV PATH=/OTB-6.6.1-Linux64/bin:/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
  PATH=/OTB-6.6.1-Linux64/bin:$PATH \
  # Very important for LIS (else we are unable to add the LIS modules) 
  LD_LIBRARY_PATH=/OTB-6.6.1-Linux64/lib/:$LD_LIBRARY_PATH

# create the build directory
RUN mkdir /build

# Create build configuration file (the only thing in this file is
# the LIS_DATA_ROOT "/data")
COPY config.cmake /build/config.cmake

WORKDIR /build

# Build and install LIS
RUN cmake -C config.cmake /let-it-snow/ \
   && make \
   && make install \
   && rm -rf /let-it-snow/

# Add env variables for LIS
ENV PATH=/usr/local/bin:/usr/local/app:$PATH \
  LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH \
  OTB_APPLICATION_PATH=/usr/local/lib:$OTB_APPLICATION_PATH \
  PYTHONPATH=/usr/local/lib:/usr/local/lib/python2.7/site-packages:$PYTHONPATH 

WORKDIR /

RUN wget http://step.esa.int/thirdparties/sen2cor/2.8.0/Sen2Cor-02.08.00-Linux64.run \
   && bash /Sen2Cor-02.08.00-Linux64.run --target /sen2cor/ \
   && rm /Sen2Cor-02.08.00-Linux64.run

COPY . /app

# add project path to pythonpath
ENV PYTHONPATH $PYTHONPATH:/app

WORKDIR /app
#Maybe cleanup to save a bit of diskspace?

CMD ["celery", "-A", "snowcover_gpl", "worker", "-Q","snowcover_gpl", "-l","INFO", "--concurrency=1", "--without-gossip", "--without-mingle", "--without-heartbeat"]