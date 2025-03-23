# app.py
from flask import Flask
import time

app = Flask(__name__)


@app.route('/')
def index():
    # Simulate some work by sleeping for 1 second
    time.sleep(1)
    return "Hello from local VM!"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
