from pydantic import BaseModel


class TableItem(BaseModel):
    t1: int
    t2: int


class TimerData(BaseModel):
    # расписание
    dbegin: int | None = None
    dskip: int | None = None
    table: list[TableItem] | None = None

    # циклический
    t1: int | None = None
    t2: int | None = None


class Timer(BaseModel):
    m: int
    data: TimerData


class Env(BaseModel):
    timers: list[Timer]


class Config(BaseModel):
    env: Env
