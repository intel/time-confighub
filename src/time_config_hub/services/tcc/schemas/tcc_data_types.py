# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
TCC Configuration Domain Model - Schema Data Types

This module defines the core dataclasses representing TCC configuration
entities. These classes encapsulate the configuration aspects of the platform,
including:

  1) CPU scheduling (core isolation) configuration
  2) CPU frequency control (governor selection, min/max frequencies, C-state overrides)
  3) Uncore frequency control
  4) Platform QoS resource configuration

*******************************************************************************
Dependency Note:
*******************************************************************************
These dataclasses are designed to align with the structure and semantics of the
TCC configuration defined in the YANG model
(`resources/yang_modules/vendor/intel/intel-tcc-config.yang`).

To ensure correctness and consistency:
  - The dataclass definitions must remain synchronized with the YANG schema.
  - Any schema changes (e.g., new nodes, attributes, or constraints) should be
    reflected here.

"""

from dataclasses import dataclass, field
from typing import Literal, Optional


# ==========================================
# TCC Basic Data Types Definition
# ==========================================

PowerGovernor = Literal[
    "performance",
    "powersave",
    "ondemand",
    "schedutil",
    "userspace",
    "conservative"
]


IdleAction = Literal[
    "enable",
    "disable"
]


# Avoid mutable defaults: use default_factory with helpers for lists/dicts.
# Pyright: The helper instantiates a new collection on every call,
# ensuring each dataclass instance receives its own unique copy.
def _default_state_overrides() -> list["StateOverride"]:
    return []


def _default_cpu_assignments() -> list["CpuAssignment"]:
    return []


def _default_frequency_profiles() -> dict[str, "FrequencyProfile"]:
    return {}


def _default_isolate_assignments() -> list["CpuIsolateAssignment"]:
    return []


def _default_ring_freqs() -> list["CpuRingRatio"]:
    return []


def _default_cpu_qos_associations() -> list["CpuQosAssociation"]:
    return []


@dataclass
class CpuIsolateAssignment:
    """Represents a single CPU isolation assignment."""
    cpu_id: int
    isolate: bool


@dataclass
class ResourceMonitoringConfig:
    """Resource monitoring configuration for a CPU."""
    enabled: bool
    rmid_id: Optional[int] = None           # When enabled=true, identifies the RMID to use for monitoring
    rmid_label: Optional[str] = None        # Optional human-readable label for the RMID, useful for logging and debugging


@dataclass
class CpuQosAssociation:
    """Represents a single CPU to QoS class association."""
    cpu_id: int
    class_of_service_id: int
    resource_monitoring: ResourceMonitoringConfig


@dataclass
class ProfileInfo:
    """Basic profile information."""

    profile_id: str
    profile_description: Optional[str] = None


@dataclass
class StateOverride:
    """Represents an override for a specific C-state."""
    state_id: int
    action: IdleAction


@dataclass
class IdleConfig:
    """Idle configuration for a frequency profile."""
    enable_all: bool = False
    disable_by_latency_us: Optional[int] = None  # If set, disables C-states with exit latency above this threshold
    state_overrides: list[StateOverride] = field(default_factory=_default_state_overrides)


@dataclass
class FrequencyConfig:
    """Represents frequency configuration for a profile."""
    governor: PowerGovernor
    min_freq_mhz: int
    max_freq_mhz: int

    def validate(self) -> None:
        # must: max >= min
        if self.max_freq_mhz < self.min_freq_mhz:
            raise ValueError(f"Invalid frequency configuration: max_freq_mhz ({self.max_freq_mhz}) must be >= min_freq_mhz ({self.min_freq_mhz})")
        # must: if governor == "performance" then min_freq_mhz == max_freq_mhz
        if self.governor == "performance" and self.min_freq_mhz != self.max_freq_mhz:
            raise ValueError(f"Invalid frequency configuration: for 'performance' governor, min_freq_mhz ({self.min_freq_mhz}) must equal max_freq_mhz ({self.max_freq_mhz})")


@dataclass
class FrequencyProfile:
    """Represents a CPU frequency profile."""
    profile_id: str
    frequency_config: FrequencyConfig
    idle_config: Optional[IdleConfig] = field(default_factory=IdleConfig)


@dataclass
class CpuAssignment:
    """Represents assignment of a CPU to a frequency profile."""
    cpu_id: int
    profile_ref: str  # Reference to FrequencyProfile.profile_id


@dataclass
class ProfileAssignment:
    """Represents the CPU to frequency profile assignments."""
    cpu_assignments: list[CpuAssignment] = field(default_factory=_default_cpu_assignments)


@dataclass
class CpuRingRatio:
    """Represents uncore frequency configuration for a single CPU."""
    cpu_id: int
    min_ring_ratio: int
    max_ring_ratio: int
    # Constraint: min_ring_ratio == max_ring_ratio


# ==========================================
# TCC Data Model
# ==========================================

@dataclass
class CpuSchedulingPlan:
    """CPU scheduling configuration."""
    assignments: list[CpuIsolateAssignment] = field(default_factory=_default_isolate_assignments)


@dataclass
class CpuFrequency:
    frequency_profiles: dict[str, FrequencyProfile] = field(default_factory=_default_frequency_profiles)  # profile_id -> FrequencyProfile
    profile_assignments: ProfileAssignment = field(default_factory=ProfileAssignment)  # CPU to profile assignments

    def validate(self) -> None:
        for profile in self.frequency_profiles.values():
            profile.frequency_config.validate()

        # leafref integrity: profile_ref must exist in frequency_profiles
        for a in self.profile_assignments.cpu_assignments:
            if a.profile_ref not in self.frequency_profiles:
                raise ValueError(f"Invalid profile assignment: CPU {a.cpu_id} references undefined profile '{a.profile_ref}'")


@dataclass
class CpuUncoreFrequency:
    """Uncore frequency configuration."""
    ring_freqs: list[CpuRingRatio] = field(default_factory=_default_ring_freqs)


@dataclass
class PlatformQosResourceConfig:
    """Platform QoS resource configuration container."""

    cpu_qos_associations: list[CpuQosAssociation] = field(default_factory=_default_cpu_qos_associations)


@dataclass
class TccConfigProfile:
    """
    Top-level TCC profile containing all configuration sections.
    """

    profile_id: str
    profile_description: Optional[str] = None
    cpu_scheduling: Optional[CpuSchedulingPlan] = None
    cpu_frequency: Optional[CpuFrequency] = None
    uncore_frequency: Optional[CpuUncoreFrequency] = None
    platform_qos_resource_config: Optional[PlatformQosResourceConfig] = None
