import time
from typing import Any
from click import command
import httpx
import os
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from openai import BaseModel
from data.models import Config, Env, Timer

BASE_URL = os.getenv("YIELDIZER_URL", "http://127.0.0.1:3001")


def _get_urls(base_url: str) -> list[str]:
    parsed = urlparse(base_url)
    host = parsed.hostname
    port = parsed.port or 80

    urls = [base_url]

    if host == "127.0.0.1" or host == "localhost":
        if ":" not in host:
            urls.append(f"http://[::1]:{port}{parsed.path or ''}")

    return urls


URLS = _get_urls(BASE_URL)


@dataclass
class SensorValues:
    ph: float
    ec: float
    temp_solution: float
    level: str
    temp_air: float
    humidity_air: float
    co2: int
    light: float


@dataclass
class GreenhouseState:
    values: SensorValues
    description: str
    uptime: int
    wifi: int
    errors: list


async def fetch_state() -> GreenhouseState:

    def fetch_value(values: Any, index: int, default: str | float):
        if index < len(values) and "v" in values[index]:
            return values[index]["v"]
        return default

    async with httpx.AsyncClient(timeout=10.0) as client:
        for base in URLS:
            for path in ["/state"]:
                url = f"{base}{path}" if base.endswith("/") else f"{base}{path}"
                try:
                    resp = await client.get(url)
                except Exception:
                    continue
                if resp.status_code == 200:
                    data = resp.json()
                    v = data.get("values", [])
                    state = GreenhouseState(
                        values=SensorValues(
                            ph=float(fetch_value(v, 0, 0.0)),
                            ec=float(fetch_value(v, 1, 0.0)),
                            temp_solution=float(fetch_value(v, 2, 0.0)),
                            level=str(fetch_value(v, 3, "none")),
                            temp_air=float(fetch_value(v, 4, 0.0)),
                            humidity_air=v[5]["v"] if len(v) > 5 else 0.0,
                            co2=int(fetch_value(v, 5, 0)),
                            light=float(fetch_value(v, 6, 0.0)),
                        ),
                        description=data.get("description", ""),
                        uptime=data.get("uptime", 0),
                        wifi=data.get("wifi", 0),
                        errors=data.get("errors", []),
                    )
                    return state
                else:
                    continue
    # raise ConnectionError(f"Cannot reach Yieldizer at {BASE_URL}")
    return GreenhouseState(
        values=SensorValues(
            ph=0,
            ec=0.5,
            temp_solution=1,
            level="meow",
            temp_air=25,
            humidity_air=10,
            co2=2,
            light=10,
        ),
        description=" I use arch, BTW ",
        uptime=123,
        wifi=1,
        errors=[],
    )


async def send_timers(timers: list[Timer]):
    return await post(
        "/cfg", Config(env=Env(timers=timers)).model_dump_json(exclude_none=True)
    )


async def post(path: str, body: str) -> bool:
    async with httpx.AsyncClient(timeout=30.0) as client:
        form_data = {"jdata": body}
        for base in URLS:
            try:
                url = f"{base}{path}" if base.endswith("/") else f"{base}{path}"
                print(f"POST on {url} with {body}")
                resp = await client.post(url, data=form_data)
                print(f"Response: {resp.status_code} {resp.text}")
                if resp.status_code == 200:
                    return resp.text == "ok"
            except Exception as e:
                print(f"Error: {e}")
                continue
    return False


async def send_command(command: dict) -> bool:
    async with httpx.AsyncClient(timeout=30.0) as client:
        for base in URLS:
            for path in ["/cmd", "/api/cmd"]:
                try:
                    url = f"{base}{path}" if base.endswith("/") else f"{base}{path}"
                    print(f"POST on {url} with {command}")
                    resp = await client.post(url, json=command)
                    if resp.status_code == 200:
                        return resp.text == "ok"
                except Exception as e:
                    print(f"Error: {e}")
                    continue
    return False


async def set_parameter(ns: str, key: str, value) -> bool:
    return await send_command({"type": "set", "ns": ns, "key": key, "value": value})


async def set_climate(param: str, value: dict) -> bool:
    return await send_command({"type": "set_climate", "param": param, **value})
