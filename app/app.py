from flask import Flask, jsonify, Response
from functools import lru_cache
from typing import Tuple

app = Flask(__name__)

@lru_cache(maxsize=None)
def fib(n: int) -> int:
    if n < 2:
        return n
    return fib(n-1) + fib(n-2)

@app.route('/fib/<int:n>')
def get_fib(n: int) -> Tuple[Response, int]:
    if n < 0:
        return jsonify({"error": "Please provide a non-negative integer"}), 400
    result = fib(n)
    return jsonify({"n": n, "fib": result}), 200

@app.route('/health')
def health_check() -> Tuple[Response, int]:
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
