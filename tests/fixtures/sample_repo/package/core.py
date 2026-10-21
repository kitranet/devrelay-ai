import os
from collections import Counter as CounterAlias
from .helpers import helper


class Worker:
    def run(self):
        return helper(CounterAlias())


async def start_worker():
    return Worker()


def outer():
    def inner():
        return os.name
    return inner()
