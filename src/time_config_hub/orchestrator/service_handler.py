# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
Service Handler

Hooks up a :class:`~.models.ServiceRequest` to the appropriate service
object on a :class:`~.time_hub_service.TimeHubService` hub and executes it.

Keeping this here, rather than inside the orchestrator, means it can be
reused by:

- :class:`~.orchestrator.Orchestrator._dispatch_service_command`
  (CLI → IPC → Orchestrator path).
- Workflow stage handlers that need to issue atomic service operations
  (e.g. ``stage_apply_config``) without re-implementing the mapping.

Public API
----------
.. function:: handle_service_request(hub, request) -> Optional[Any]

    Execute the command described by *request* against *hub* and return
    any data payload (STATUS queries), or ``None`` for side-effect
    commands (apply, reset, validate).
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Protocol

from .models import ServiceCommand, ServiceRequest, ServiceType
from time_config_hub.services.common.service_interfaces import (
    TCCServiceInterface,
    TSNServiceInterface,
)

__all__ = ["handle_service_request"]

logger = logging.getLogger("orchestrator.service_handler")
logger.setLevel(logging.DEBUG)

class _ServiceHub(Protocol):
    """Structural interface required by :func:`handle_service_request`.

    Any object that exposes ``tsn`` and ``tcc`` service properties satisfies
    this contract — :class:`~.time_hub_service.TimeHubService` and test stubs
    alike.
    """

    @property
    def tsn(self) -> TSNServiceInterface: ...

    @property
    def tcc(self) -> TCCServiceInterface: ...


def handle_service_request(
    hub: _ServiceHub,
    request: ServiceRequest,
) -> Optional[Any]:
    """Hook up *request* to the appropriate service on *hub* and execute it.

    Has no knowledge of result wrapping, logging, or orchestration state —
    those concerns belong to the caller.

    :param _ServiceHub hub: The service hub to execute against.
    :param ServiceRequest request: The request to handle.
    :return: Data payload for query commands (e.g. STATUS), ``None`` for
        side-effect commands (apply, reset, validate).
    :rtype: Optional[Any]
    :raises Exception: Propagates any exception raised by the underlying
        service method so the caller can handle it uniformly.
    """

    logger.info("[Orchestrator] Handling service request: service_type=%s, command=%s",
                request.service_type, request.command)

    if request.service_type == ServiceType.TSN:
        tsn: TSNServiceInterface = hub.tsn
        if request.command == ServiceCommand.APPLY:
            logger.debug("[tsn] apply: %s (dry_run=%s)", request.config_path, request.dry_run)
            return tsn.apply(request.config_path or "", dry_run=request.dry_run)
        elif request.command == ServiceCommand.STATUS:
            logger.debug("[tsn] status: interface=%s", request.interface)
            return tsn.status(interface=request.interface or "")
        elif request.command == ServiceCommand.RESET:
            logger.debug("[tsn] reset: interface=%s", request.interface)
            return tsn.reset(interface=request.interface or "")
        elif request.command == ServiceCommand.VALIDATE:
            logger.debug("[tsn] validate: %s", request.config_path)
            return tsn.validate(request.config_path or "")

    elif request.service_type == ServiceType.TCC:
        tcc: TCCServiceInterface = hub.tcc
        if request.command == ServiceCommand.APPLY:
            logger.debug("[tcc] apply: %s (dry_run=%s)", request.config_path, request.dry_run)
            return tcc.apply(request.config_path or "", dry_run=request.dry_run)
        elif request.command == ServiceCommand.STATUS:
            logger.debug("[tcc] status")
            return tcc.status()
        elif request.command == ServiceCommand.RESET:
            logger.debug("[tcc] reset")
            return tcc.reset()
        elif request.command == ServiceCommand.VALIDATE:
            logger.debug("[tcc] validate: %s", request.config_path)
            return tcc.validate(request.config_path or "")

    else:
        logger.error(
            "[UNSUPPORTED] service_type=%s command=%s",
            request.service_type,
            request.command,
        )

    return None
