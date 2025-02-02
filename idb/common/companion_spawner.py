#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved.

import asyncio
import atexit
import json
import logging
import os
import signal
from asyncio import StreamReader
from asyncio.subprocess import Process
from typing import List

from idb.common.constants import IDB_LOGS_PATH


class CompanionSpawnerException(Exception):
    pass


class CompanionSpawner:
    def __init__(self, companion_path: str) -> None:
        self.companion_path = companion_path
        self.companion_processes: List[Process] = []
        atexit.register(self.kill_spawned_companion)

    async def _read_stream(self, stream: StreamReader) -> int:
        port = 0
        while True:
            line = await stream.readline()
            logging.debug(f"read line from companion : {line}")
            if line:
                update = json.loads(line.decode())
                if update:
                    logging.debug(f"got update from companion {update}")
                    port = update["grpc_port"]
                    break
            else:
                break
        return port

    def _log_file_path(self, target_udid: str) -> str:
        os.makedirs(name=IDB_LOGS_PATH, exist_ok=True)
        return IDB_LOGS_PATH + "/" + target_udid

    def kill_spawned_companion(self) -> None:
        for p in self.companion_processes:
            os.kill(p.pid, signal.SIGTERM)

    async def spawn_companion(self, target_udid: str) -> int:
        if not self.companion_path:
            raise CompanionSpawnerException(
                f"couldn't instantiate a companion for {target_udid} because\
                 the companion_path is not available"
            )
        cmd: List[str] = [
            self.companion_path,
            "--udid",
            target_udid,
            "--grpc-port",
            "0",
        ]

        with open(self._log_file_path(target_udid), "a") as log_file:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                stderr=log_file,
            )
            self.companion_processes.append(process)
            logging.debug(f"started companion at process id {process.pid}")
            if process.stdout:
                port = await self._read_stream(process.stdout)
                if not port:
                    raise CompanionSpawnerException("failed to spawn companion")
                return port
            raise CompanionSpawnerException("process has no stdout")

    def close(self) -> None:
        logging.info("Stopping companion spawner")
        for process in self.companion_processes:
            logging.info("Stopping companion")
            process.terminate()
