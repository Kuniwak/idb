#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved.

import os
import urllib.parse
from logging import Logger
from pathlib import Path
from typing import IO, AsyncIterator, Union

import aiofiles
import idb.common.gzip as gzip
import idb.common.tar as tar
from grpclib.const import Status
from grpclib.exceptions import GRPCError
from idb.common.types import InstalledArtifact
from idb.common.xctest import xctest_paths_to_tar
from idb.grpc.idb_pb2 import InstallRequest, InstallResponse, Payload
from idb.grpc.stream import Stream, drain_to_stream
from idb.grpc.types import CompanionClient
from idb.utils.typing import none_throws


CHUNK_SIZE = 16384
Destination = InstallRequest.Destination
Bundle = Union[str, IO[bytes]]


async def _generate_ipa_chunks(
    ipa_path: str, logger: Logger
) -> AsyncIterator[InstallRequest]:
    logger.debug(f"Generating Chunks for .ipa {ipa_path}")
    async with aiofiles.open(ipa_path, "r+b") as file:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                logger.debug(f"Finished generating .ipa chunks for {ipa_path}")
                return
            yield InstallRequest(payload=Payload(data=chunk))


async def _generate_app_chunks(
    app_path: str, logger: Logger
) -> AsyncIterator[InstallRequest]:
    logger.debug(f"Generating chunks for .app {app_path}")
    async for chunk in tar.generate_tar([app_path]):
        yield InstallRequest(payload=Payload(data=chunk))
    logger.debug(f"Finished generating .app chunks {app_path}")


async def _generate_xctest_chunks(
    path: str, logger: Logger
) -> AsyncIterator[InstallRequest]:
    logger.debug(f"Generating chunks for {path}")
    async for chunk in tar.generate_tar(xctest_paths_to_tar(path)):
        yield InstallRequest(payload=Payload(data=chunk))
    logger.debug(f"Finished generating chunks {path}")


async def _generate_dylib_chunks(
    path: str, logger: Logger
) -> AsyncIterator[InstallRequest]:
    logger.debug(f"Generating chunks for {path}")
    yield InstallRequest(name_hint=os.path.basename(path))
    async for chunk in gzip.generate_gzip(path):
        yield InstallRequest(payload=Payload(data=chunk))
    logger.debug(f"Finished generating chunks {path}")


async def _generate_dsym_chunks(
    path: str, logger: Logger
) -> AsyncIterator[InstallRequest]:
    logger.debug(f"Generating chunks for {path}")
    async for chunk in tar.generate_tar([path]):
        yield InstallRequest(payload=Payload(data=chunk))
    logger.debug(f"Finished generating chunks {path}")


async def _generate_framework_chunks(
    path: str, logger: Logger
) -> AsyncIterator[InstallRequest]:
    logger.debug(f"Generating chunks for {path}")
    async for chunk in tar.generate_tar([path]):
        yield InstallRequest(payload=Payload(data=chunk))
    logger.debug(f"Finished generating chunks {path}")


async def _generate_io_chunks(
    io: IO[bytes], logger: Logger
) -> AsyncIterator[InstallRequest]:
    logger.debug("Generating io chunks")
    while True:
        chunk = io.read(CHUNK_SIZE)
        if not chunk:
            logger.debug(f"Finished generating byte chunks")
            return
        yield InstallRequest(payload=Payload(data=chunk))
    logger.debug("Finished generating io chunks")


def _generate_binary_chunks(
    path: str, destination: Destination, logger: Logger
) -> AsyncIterator[InstallRequest]:
    if destination == InstallRequest.APP:
        if path.endswith(".ipa"):
            return _generate_ipa_chunks(ipa_path=path, logger=logger)
        elif path.endswith(".app"):
            return _generate_app_chunks(app_path=path, logger=logger)
    elif destination == InstallRequest.XCTEST:
        return _generate_xctest_chunks(path=path, logger=logger)
    elif destination == InstallRequest.DYLIB:
        return _generate_dylib_chunks(path=path, logger=logger)
    elif destination == InstallRequest.DSYM:
        return _generate_dsym_chunks(path=path, logger=logger)
    elif destination == InstallRequest.FRAMEWORK:
        return _generate_framework_chunks(path=path, logger=logger)
    raise GRPCError(
        status=Status(Status.FAILED_PRECONDITION),
        message=f"install invalid for {path} {destination}",
    )


async def _install_to_destination(
    client: CompanionClient, bundle: Bundle, destination: Destination
) -> InstalledArtifact:
    if isinstance(bundle, str):
        # Treat as a file path / url
        url = urllib.parse.urlparse(bundle)
        if url.scheme:
            payload = Payload(url=bundle)
        else:
            payload = Payload(file_path=str(Path(bundle).resolve(strict=True)))
        async with client.stub.install.open() as stream:
            await stream.send_message(InstallRequest(destination=destination))
            await stream.send_message(InstallRequest(payload=payload))
            await stream.end()
            response = await stream.recv_message()
            return InstalledArtifact(name=response.name, uuid=response.uuid)
    else:
        # Treat as a binary object (tar of .app or .ipa)
        async with client.stub.install.open() as stream:
            await stream.send_message(InstallRequest(destination=destination))
            response = await drain_to_stream(
                stream=stream,
                generator=_generate_io_chunks(io=bundle, logger=client.logger),
                logger=client.logger,
            )
            return InstalledArtifact(name=response.name, uuid=response.uuid)


async def install(client: CompanionClient, bundle: Bundle) -> InstalledArtifact:
    return await _install_to_destination(
        client=client, bundle=bundle, destination=InstallRequest.APP
    )


async def install_xctest(client: CompanionClient, bundle: Bundle) -> InstalledArtifact:
    return await _install_to_destination(
        client=client, bundle=bundle, destination=InstallRequest.XCTEST
    )


async def install_dylib(client: CompanionClient, dylib: Bundle) -> InstalledArtifact:
    return await _install_to_destination(
        client=client, bundle=dylib, destination=InstallRequest.DYLIB
    )


async def install_dsym(client: CompanionClient, dsym: Bundle) -> InstalledArtifact:
    return await _install_to_destination(
        client=client, bundle=dsym, destination=InstallRequest.DSYM
    )


async def install_framework(
    client: CompanionClient, framework_path: Bundle
) -> InstalledArtifact:
    return await _install_to_destination(
        client=client, bundle=framework_path, destination=InstallRequest.FRAMEWORK
    )


async def daemon(
    client: CompanionClient, stream: Stream[InstallResponse, InstallRequest]
) -> None:
    destination_message = none_throws(await stream.recv_message())
    payload_message = none_throws(await stream.recv_message())
    file_path = payload_message.payload.file_path
    url = payload_message.payload.url
    data = payload_message.payload.data
    destination = destination_message.destination
    async with client.stub.install.open() as forward_stream:
        await forward_stream.send_message(destination_message)
        if client.is_local or len(url):
            await forward_stream.send_message(payload_message)
            await forward_stream.end()
            response = none_throws(await forward_stream.recv_message())
        elif file_path:
            response = await drain_to_stream(
                stream=forward_stream,
                generator=_generate_binary_chunks(
                    path=file_path, destination=destination, logger=client.logger
                ),
                logger=client.logger,
            )
        elif data:
            await forward_stream.send_message(payload_message)
            response = await drain_to_stream(
                stream=forward_stream, generator=stream, logger=client.logger
            )
        else:
            raise Exception(f"Unrecognised payload message")
        await stream.send_message(response)


# pyre-ignore
CLIENT_PROPERTIES = [
    install,
    install_xctest,
    install_dsym,
    install_dylib,
    install_framework,
]
