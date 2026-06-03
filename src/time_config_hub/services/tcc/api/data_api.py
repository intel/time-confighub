# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
TCC Data Access API for querying and accessing configuration data.

Provides high-level methods to query TCC subsystem containers, access individual
configuration elements, and validate TCC profiles.
"""

from typing import Any, Dict, List, Optional, Set

from time_config_hub.services.tcc.schemas.tcc_data_mapping import TCCRawToDataModelMapping
from time_config_hub.services.tcc.schemas.tcc_data_types import (
    CpuFrequency,
    CpuSchedulingPlan,
    FrequencyProfile,
)


class TCCDataAPI:
    """
    High-level data access API for TCC configuration.

    Provides methods to:
    - Query available containers
    - Access CPU scheduling configuration
    - Access CPU frequency profiles and assignments
    - Validate configuration consistency
    """

    def __init__(self, documents: List[Dict[str, Any]]):
        """
        Initialize TCC Data API with parsed documents.

        :param List[Dict[str, Any]] documents: Parsed configuration documents from UniversalParser
        :raises InvalidInputDataError: If profile-id is missing from documents
        """
        self.mapped_data = TCCRawToDataModelMapping.documents_to_tcc_data_model(documents)

    @property
    def profile_id(self) -> str:
        """Get the TCC profile ID."""
        return self.mapped_data.profile_id

    @property
    def profile_description(self) -> Optional[str]:
        """Get the TCC profile description."""
        return self.mapped_data.profile_description

    def get_available_subsystem_containers(self) -> Set[str]:
        """
        Get set of available TCC subsystem containers in the profile.

        :return: Set of container names
        :rtype: Set[str]
        """
        containers = set()

        if self.mapped_data.cpu_scheduling:
            containers.add("cpu-scheduling")

        if self.mapped_data.cpu_frequency:
            containers.add("cpu-frequency")

        if self.mapped_data.uncore_frequency:
            containers.add("uncore-frequency")

        if self.mapped_data.platform_qos_resource_config:
            containers.add("platform-qos-resource-config")

        return containers

    def get_cpu_scheduling(self) -> Optional[CpuSchedulingPlan]:
        """
        Get CPU scheduling configuration.

        :return: CpuSchedulingPlan instance or None if not configured
        :rtype: Optional[CpuSchedulingPlan]
        """
        return self.mapped_data.cpu_scheduling

    def get_isolated_cpus(self) -> List[int]:
        """
        Get list of CPU IDs marked as isolated.

        :return: List of isolated CPU IDs
        :rtype: List[int]
        """
        if not self.mapped_data.cpu_scheduling:
            return []

        isolated = []
        for assignment in self.mapped_data.cpu_scheduling.assignments:
            if assignment.isolate:
                isolated.append(assignment.cpu_id)
        return isolated

    def get_non_isolated_cpus(self) -> List[int]:
        """
        Get list of CPU IDs NOT marked as isolated (housekeeping).

        :return: List of non-isolated CPU IDs
        :rtype: List[int]
        """
        if not self.mapped_data.cpu_scheduling:
            return []

        non_isolated = []
        for assignment in self.mapped_data.cpu_scheduling.assignments:
            if not assignment.isolate:
                non_isolated.append(assignment.cpu_id)
        return non_isolated

    def get_cpu_frequency_profiles(self) -> Optional[CpuFrequency]:
        """
        Get CPU frequency profile configuration.

        :return: CpuFrequency instance or None if not configured
        :rtype: Optional[CpuFrequency]
        """
        return self.mapped_data.cpu_frequency

    def get_frequency_profile(self, profile_id: str) -> Optional[FrequencyProfile]:
        """
        Get a specific frequency profile by ID.

        :param str profile_id: Profile ID to retrieve
        :return: FrequencyProfile instance or None if not found
        :rtype: Optional[FrequencyProfile]
        """
        if not self.mapped_data.cpu_frequency:
            return None
        return self.mapped_data.cpu_frequency.frequency_profiles.get(profile_id)

    def get_all_frequency_profiles(self) -> Dict[str, FrequencyProfile]:
        """
        Get all defined frequency profiles.

        :return: Dictionary mapping profile ID to FrequencyProfile instance
        :rtype: Dict[str, FrequencyProfile]
        """
        if not self.mapped_data.cpu_frequency:
            return {}
        return self.mapped_data.cpu_frequency.frequency_profiles

    def get_cpu_frequency_assignment(self, cpu_id: int) -> Optional[str]:
        """
        Get frequency profile assigned to a specific CPU.

        :param int cpu_id: CPU ID to query
        :return: Profile ID assigned to the CPU, or None if not assigned
        :rtype: Optional[str]
        """
        if not self.mapped_data.cpu_frequency:
            return None
        for assignment in self.mapped_data.cpu_frequency.profile_assignments.cpu_assignments:
            if assignment.cpu_id == cpu_id:
                return assignment.profile_ref
        return None

    def get_frequency_profile_for_cpu(self, cpu_id: int) -> Optional[FrequencyProfile]:
        """
        Get the frequency profile configuration for a specific CPU.

        :param int cpu_id: CPU ID to query
        :return: FrequencyProfile instance or None if CPU not assigned a profile
        :rtype: Optional[FrequencyProfile]
        """
        if not self.mapped_data.cpu_frequency:
            return None
        profile_id = self.get_cpu_frequency_assignment(cpu_id)
        if not profile_id:
            return None
        return self.mapped_data.cpu_frequency.frequency_profiles.get(profile_id)

    def get_cpus_for_frequency_profile(self, profile_id: str) -> List[int]:
        """
        Get all CPUs assigned to a specific frequency profile.

        :param str profile_id: Profile ID to query
        :return: List of CPU IDs assigned to the profile
        :rtype: List[int]
        """
        if not self.mapped_data.cpu_frequency:
            return []

        cpu_ids = []
        for assignment in self.mapped_data.cpu_frequency.profile_assignments.cpu_assignments:
            if assignment.profile_ref == profile_id:
                cpu_ids.append(assignment.cpu_id)
        return cpu_ids

    def validate_consistency(self) -> List[str]:
        """
        Validate configuration consistency and return any warnings/errors.

        Checks for:
        - CPUs assigned in scheduling but not in frequency profiles
        - Undefined profile references
        - Missing or inconsistent configurations

        :return: List of validation messages (empty if valid)
        :rtype: List[str]
        """
        issues: List[str] = []

        # Check CPU scheduling vs frequency assignments
        if self.mapped_data.cpu_scheduling and self.mapped_data.cpu_frequency:
            scheduled_cpus = {a.cpu_id for a in self.mapped_data.cpu_scheduling.assignments}
            assigned_cpus = {
                assignment.cpu_id
                for assignment in self.mapped_data.cpu_frequency.profile_assignments.cpu_assignments
            }

            missing_assignments = scheduled_cpus - assigned_cpus
            if missing_assignments:
                issues.append(
                    f"CPUs scheduled but not assigned to frequency profile: {missing_assignments}"
                )

            extra_assignments = assigned_cpus - scheduled_cpus
            if extra_assignments:
                issues.append(f"CPUs assigned to frequency profile but not scheduled: {extra_assignments}")

        # Check profile references are valid
        if self.mapped_data.cpu_frequency:
            valid_profiles = set(self.mapped_data.cpu_frequency.frequency_profiles.keys())
            referenced_profiles = {
                assignment.profile_ref
                for assignment in self.mapped_data.cpu_frequency.profile_assignments.cpu_assignments
            }
            undefined_refs = referenced_profiles - valid_profiles

            if undefined_refs:
                issues.append(f"Undefined profile references: {undefined_refs}")

        return issues

    def summary(self) -> str:
        """
        Generate a human-readable summary of the TCC configuration.

        :return: Formatted configuration summary
        :rtype: str
        """
        lines = [
            f"TCC Profile: {self.mapped_data.profile_id}",
            f"Description: {self.mapped_data.profile_description or '(none)'}",
            f"Selected TCC Subsystems: {sorted(self.get_available_subsystem_containers())}",
        ]

        isolated = self.get_isolated_cpus()
        if isolated:
            lines.append(f"Isolated CPUs: {isolated}")

        freq_profiles = self.get_all_frequency_profiles()
        if freq_profiles:
            lines.append(f"Frequency Profiles: {list(freq_profiles.keys())}")
            for profile_id, profile in freq_profiles.items():
                cpus = self.get_cpus_for_frequency_profile(profile_id)
                lines.append(
                    f"  {profile_id}: {profile.frequency_config.governor} "
                    f"({profile.frequency_config.min_freq_mhz}-{profile.frequency_config.max_freq_mhz} MHz), CPUs: {cpus}"
                )

        return "\n".join(lines)
