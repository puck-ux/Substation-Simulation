FROM python:3.9-bullseye
RUN apt-get update && apt-get install -y \
    gcc g++ cmake libssl-dev git \
    && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/ChargePoint/pydnp3.git && \
    cd pydnp3 && \
    git submodule update --init --recursive && \
    sed -i 's/#include <python2.7\/Python.h>//' src/asiodnp3/ConsoleLogger.h && \
    pip install .
RUN pip install pymodbus flask requests
WORKDIR /app
COPY master.py .
EXPOSE 5001
CMD ["python", "master.py"]