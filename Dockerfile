FROM python:3.14-slim
WORKDIR /app
COPY . .

RUN pip install --root-user-action ignore --no-cache-dir -r requirements.txt

ARG VERSION_TAG=unknown
ENV MQTT4DSMR_VERSION=$VERSION_TAG

CMD [ "python3", "mqtt4dsmr.py" ]
