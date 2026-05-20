from importlib import import_module


_credentials = import_module("scripts.credentials")

getMinerUToken = _credentials.getMinerUToken
getPaddleOcrToken = _credentials.getPaddleOcrToken
