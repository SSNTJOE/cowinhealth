# -*- coding: utf-8 -*-
"""Temporary server so the recipe picker can be checked without MySQL."""
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.recipes import TEACHING_DISCLAIMER, countries, filter_recipes

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
def index():
    return FileResponse("app/static/index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "mysql": False}


@app.get("/api/me")
def me():
    return {"logged_in": False}


@app.get("/api/flags")
def flags():
    return {"conditions": [], "allergies": []}


@app.get("/api/recipes/countries")
def recipe_countries():
    return {"countries": countries(), "disclaimer": TEACHING_DISCLAIMER}


@app.get("/api/recipes")
def recipes(country: str, lang: str = "zh"):
    return filter_recipes(country, lang)
