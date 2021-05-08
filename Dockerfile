FROM jemand771/chromedriver-base-python

WORKDIR /tmp
ADD requirements.txt .
RUN pip install -r requirements.txt && \
    rm requirements.txt

ENV DISCORD_TOKEN=

WORKDIR /app
ADD *.py ./

CMD ["python3", "bot.py"]