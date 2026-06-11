# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
Orchestrator IPC Module

This module contains server and client components for orchestration over 
a Unix domain socket.

The daemon exposes a streaming socket at /run/tch-orchestrator.sock.
The CLI connects to it to submit orchestration requests.

Message Protocol (newline-delimited JSON):
    Client → Server:  OrchestratorConfig as JSON + '\\n'
    Server → Client:  OrchestratorResult as JSON + '\\n'
"""

import json
import logging
import os
import socket
import socketserver
import threading
from dataclasses import asdict
from pathlib import Path

from .models import (
    DeploymentTopologyType,
    OrchestratorConfig,
    OrchestratorResult,
    Target,
)
from .orchestrator import Orchestrator

# ======================================================================
# Public API & Configuration
# ======================================================================

__all__ = [
    "OrchestratorServer",
    "start_orchestrator_server",
    "send_orchestration_request",
    "SOCKET_PATH",
]

logger = logging.getLogger("orchestrator.service")

SOCKET_PATH = "/run/tch-orchestrator.sock"
# TODO: Refine these constants based on expected request/response sizes and wait for data requirements.
MAX_REQUEST_SIZE = 1_048_576    # 1 MB
CLIENT_TIMEOUT = 120            # seconds


# ======================================================================
# Server — handler, server class, and daemon startup
# ======================================================================

def _deserialize_config(data: dict) -> OrchestratorConfig:
    """
    Build an OrchestratorConfig from a plain dict (JSON payload).

    :param dict data: The input data dictionary parsed from JSON.
    :return: An OrchestratorConfig instance.
    :rtype: OrchestratorConfig
    :raises KeyError: If required fields are missing in the input data.
    :raises ValueError: If fields have invalid values (e.g., unknown topology type).
    """

    targets = [Target(**t) for t in data.get("targets", [])]
    return OrchestratorConfig(
        topology_type=DeploymentTopologyType(data["topology_type"]),
        targets=targets,
        tcc_config=data["tcc_config"],
        tsn_config=data["tsn_config"],
        stages_to_run=data.get("stages_to_run", []),
        dry_run=data.get("dry_run", False),
    )


class _OrchestrationHandler(socketserver.StreamRequestHandler):
    """
    Handle a single orchestration request.
    
    This handler reads a JSON payload from the client, deserializes it into an
    OrchestratorConfig, runs the orchestration workflow, and sends back an
    OrchestratorResult as JSON.
    """

    timeout = 30  # seconds to wait for client data before dropping connection

    def handle(self):
        try:
            raw = self.rfile.readline(MAX_REQUEST_SIZE)
            if not raw:
                return
            payload = json.loads(raw.decode("utf-8"))
            config = _deserialize_config(payload)
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
            logger.warning("Bad request from client: %s", exc)
            error_result = OrchestratorResult(
                success=False, logs=[], errors=[f"Bad request: {exc}"]
            )
            try:
                self.wfile.write(
                    (json.dumps(asdict(error_result)) + "\n").encode("utf-8")
                )
                self.wfile.flush()
            except OSError:
                pass
            return

        try:
            logger.info(
                "Received orchestration request: topology=%s, targets=%d",
                config.topology_type.value,
                len(config.targets),
            )

            result = Orchestrator(config=config).run()

            response = json.dumps(asdict(result))
            self.wfile.write((response + "\n").encode("utf-8"))
            self.wfile.flush()

        except Exception as exc:
            logger.exception("Error during orchestration")
            error_result = OrchestratorResult(
                success=False, logs=[], errors=[str(exc)]
            )
            try:
                self.wfile.write(
                    (json.dumps(asdict(error_result)) + "\n").encode("utf-8")
                )
                self.wfile.flush()
            except OSError:
                pass


class OrchestratorServer(socketserver.UnixStreamServer):
    """
    Single-threaded Unix-socket server for the Orchestrator daemon.

    This server listens for incoming orchestration requests on a Unix domain socket.
    Requests are processed one at a time in FIFO order.

    :param str socket_path: Path to the Unix domain socket to bind.
    :param handler_class: The request handler class to use for incoming connections.
    """

    def server_close(self):
        super().server_close()
        try:
            os.unlink(self.server_address)
        except OSError:
            pass


def start_orchestrator_server(socket_path: str = SOCKET_PATH) -> OrchestratorServer:
    """
    Start the orchestrator socket server in a daemon thread.

    Called by time_config_hub.service.Service.start() to embed the
    orchestrator server inside the existing tch.service daemon.

    :param str socket_path: Path for the Unix domain socket.
    :return: The running server instance (for later shutdown).
    :rtype: OrchestratorServer
    """

    # Ensure old socket is removed and parent directory exists
    sock_path = Path(socket_path)
    if sock_path.exists():
        sock_path.unlink()
    sock_path.parent.mkdir(parents=True, exist_ok=True)

    # Bind the socket with restricted permissions (owner+group rw only)
    old_umask = os.umask(0o117)
    try:
        server = OrchestratorServer(socket_path, _OrchestrationHandler)
    finally:
        os.umask(old_umask)

    # Start server in a daemon thread so it doesn't block the main service loop
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    logger.info("Orchestrator server started on %s", socket_path)
    return server


# ======================================================================
# Client — CLI-facing request helper
# ======================================================================

def send_orchestration_request(
    config: OrchestratorConfig,
    socket_path: str = SOCKET_PATH,
    timeout: float = CLIENT_TIMEOUT,
) -> OrchestratorResult:
    """Client-side helper: send config to the daemon and return result.

    Used by the CLI ``tch orchestrate`` command.

    :param OrchestratorConfig config: The orchestration configuration to send.
    :param str socket_path: Path for the Unix domain socket.
    :param float timeout: Socket timeout in seconds.
    :return: The result of the orchestration request.
    :rtype: OrchestratorResult
    :raises socket.timeout: If the daemon does not respond within *timeout* seconds.
    """
    payload = asdict(config)
    payload["topology_type"] = config.topology_type.value  # serialize enum

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(socket_path)
        sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))

        resp_data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            resp_data += chunk
            if len(resp_data) > MAX_REQUEST_SIZE:
                raise ConnectionError("Response from daemon exceeds size limit")
            if b"\n" in resp_data:
                break

        if not resp_data.strip():
            raise ConnectionError("Daemon closed connection without a response")

        result_dict = json.loads(resp_data.decode("utf-8").strip())
        return OrchestratorResult(**result_dict)
    finally:
        sock.close()