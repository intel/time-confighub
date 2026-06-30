# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
Orchestrator IPC Module

This module contains server and client components for orchestration over
a Unix domain socket.

The daemon exposes a streaming socket at /run/tch-orchestrator.sock.
The CLI connects to it to submit orchestration requests.

Message Protocol (newline-delimited JSON):
    Client → Server:  ServiceRequest as JSON + '\n'
    Server → Client:  OrchestratorResult as JSON + '\n'

All requests must carry a ``command`` field (see :class:`~.models.ServiceCommand`).
Workflow orchestration requests use ``command="pipeline"`` with an embedded
``pipeline_config`` payload.  Direct service commands (apply, status, reset,
validate) use the corresponding command value without ``pipeline_config``.
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
    PipelineConfig,
    ServiceResult,
    ServiceCommand,
    ServiceRequest,
    ServiceType,
    Target,
)
from .orchestrator import Orchestrator

# ======================================================================
# Public API & Configuration
# ======================================================================

__all__ = [
    "OrchestratorServer",
    "start_server",
    "send_pipeline_request",
    "send_service_request",
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

def _deserialize_config(data: dict) -> PipelineConfig:
    """
    Build an OrchestratorConfig from a plain dict (JSON payload).

    :param dict data: The input data dictionary parsed from JSON.
    :return: An OrchestratorConfig instance.
    :rtype: OrchestratorConfig
    :raises KeyError: If required fields are missing in the input data.
    :raises ValueError: If fields have invalid values (e.g., unknown topology type).
    """

    targets = [Target(**t) for t in data.get("targets", [])]
    return PipelineConfig(
        topology_type=DeploymentTopologyType(data["topology_type"]),
        targets=targets,
        tcc_config=data["tcc_config"],
        tsn_config=data["tsn_config"],
        stages_to_run=data.get("stages_to_run", []),
        dry_run=data.get("dry_run", False),
        test_duration=data.get("test_duration"),
        timeout=data.get("timeout"),
    )


def _deserialize_service_request(data: dict) -> ServiceRequest:
    """
    Build a ServiceRequest from a plain dict (JSON payload).

    :param dict data: The input data dictionary parsed from JSON.
    :return: A ServiceRequest instance.
    :rtype: ServiceRequest
    :raises KeyError: If required fields are missing.
    :raises ValueError: If fields have invalid enum values.
    """
    orch_config_data = data.get("pipeline_config")
    orch_config = _deserialize_config(orch_config_data) if orch_config_data else None
    svc_type_raw = data.get("service_type")
    return ServiceRequest(
        command=ServiceCommand(data["command"]),
        service_type=ServiceType(svc_type_raw) if svc_type_raw else None,
        config_path=data.get("config_path"),
        interface=data.get("interface"),
        dry_run=data.get("dry_run", False),
        pipeline_config=orch_config,
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

            if "command" not in payload:
                raise ValueError(
                    "Payload missing required 'command' field. "
                    "All requests must be sent as a ServiceRequest. "
                    "Use send_service_request() on the client side."
                )

            request = _deserialize_service_request(payload)
            logger.info(
                "Received service request: command=%s, service=%s",
                request.command.value,
                request.service_type.value if request.service_type else "pipeline",
            )
            result = Orchestrator().execute(request)

            response = json.dumps(asdict(result))
            self.wfile.write((response + "\n").encode("utf-8"))
            self.wfile.flush()

        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
            logger.warning("Bad request from client: %s", exc)
            error_result = ServiceResult(
                success=False, logs=[], errors=[f"Bad request: {exc}"]
            )
            try:
                self.wfile.write(
                    (json.dumps(asdict(error_result)) + "\n").encode("utf-8")
                )
                self.wfile.flush()
            except OSError:
                pass

        except Exception as exc:
            logger.exception("Error during request handling")
            error_result = ServiceResult(
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


def start_server(socket_path: str = SOCKET_PATH) -> OrchestratorServer:
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
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="OrchestratorServerThread")
    thread.start()

    logger.info("Orchestrator server started on %s", socket_path)
    return server


# ======================================================================
# CLI-facing request helper
#  It supports both individual service commands (apply, status, reset, validate) and full pipeline requests (pipeline).
#  The CLI should use send_service_request() for individual commands and send_pipeline_request() for pipeline workflows.
# ======================================================================

def send_pipeline_request(
    config: PipelineConfig,
    socket_path: str = SOCKET_PATH,
    timeout: float = CLIENT_TIMEOUT,
) -> ServiceResult:
    """Client-side helper: send an orchestration workflow request to the daemon.

    Wraps *config* in a :class:`~.models.ServiceRequest` with
    ``command=PIPELINE`` and delegates to :func:`send_service_request`.
    This is the standard entry point for the CLI ``tch pipeline`` command.

    :param PipelineConfig config: The orchestration configuration to send.
    :param str socket_path: Path for the Unix domain socket.
    :param float timeout: Socket timeout in seconds.
    :return: The result of the orchestration request.
    :rtype: ServiceResult
    :raises socket.timeout: If the daemon does not respond within *timeout* seconds.
    """
    request = ServiceRequest(
        command=ServiceCommand.PIPELINE,  # Trigger the full multi-stage workflow pipeline
        pipeline_config=config,
    )
    return send_service_request(request, socket_path=socket_path, timeout=timeout)


def send_service_request(
    request: ServiceRequest,
    socket_path: str = SOCKET_PATH,
    timeout: float = CLIENT_TIMEOUT,
) -> ServiceResult:
    """Client-side helper: send a ServiceRequest to the daemon and return result.

    Serializes the :class:`~.models.ServiceRequest` as JSON and forwards it
    to the orchestrator daemon over a Unix domain socket.  The daemon
    dispatches the command through :meth:`Orchestrator.execute` and returns
    an :class:`~.models.ServiceResult`.

    :param ServiceRequest request: The service command to send.
    :param str socket_path: Path to the Unix domain socket.
    :param float timeout: Socket timeout in seconds.
    :return: The result returned by the daemon.
    :rtype: ServiceResult
    :raises socket.timeout: If the daemon does not respond within *timeout* seconds.
    """
    payload = asdict(request)
    payload["command"] = request.command.value
    payload["service_type"] = request.service_type.value if request.service_type else None
    if request.pipeline_config is not None:
        payload["pipeline_config"]["topology_type"] = request.pipeline_config.topology_type.value

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
        return ServiceResult(**result_dict)
    except ConnectionRefusedError:
        raise ConnectionError(f"Could not connect to orchestrator daemon at {socket_path}. Is it running?")
    except socket.timeout:
        raise TimeoutError(f"Timed out waiting for response from orchestrator daemon at {socket_path}")
    except ConnectionError:
        raise  # Internal connection error and re-raised as it is
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise ConnectionError(f"Invalid response from orchestrator daemon at {socket_path}: {e}")
    except OSError as e:
        raise ConnectionError(f"OS error while communicating with orchestrator daemon: {e}")
    finally:
        sock.close()
