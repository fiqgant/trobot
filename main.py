"""Entrypoint: uvicorn serving the trobot FastAPI app.

Run: python main.py  (inside the "cv" conda env)
"""
import logging

import uvicorn

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # ws="wsproto": uvicorn 0.34.x's default "websockets" implementation
    # rejects real browser handshakes with 400 against websockets>=14 (a
    # known uvicorn/websockets version incompatibility) -- wsproto doesn't
    # have that issue and ships with uvicorn[standard] already.
    uvicorn.run("app.server:app", host="0.0.0.0", port=8000, log_level="info", ws="wsproto")
