#!/bin/bash
export PYTHONHTTPSVERIFY=0
export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
export NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt
export NODE_TLS_REJECT_UNAUTHORIZED=0

sudo apt-get install -y libxcb-shm0 libx11-xcb1 libxrandr2 libxcomposite1 libxcursor1 libxdamage1 libxi6 libxfixes3 libgtk-3-0 libpangocairo-1.0-0 libpango-1.0-0 libatk1.0-0 libcairo-gobject2 libcairo2 libgdk-pixbuf-xlib-2.0-0 libglib2.0-0 libasound2 libgbm1
    pip install -r requirements.txt

    playwright install

