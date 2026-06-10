# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""Unit tests for TCCConfigDataAPI (services/tcc/api/data_api.py)."""

from unittest.mock import MagicMock, patch

import pytest

from time_config_hub.services.tcc.api.data_api import TCCConfigDataAPI
from time_config_hub.services.tcc.schemas.tcc_data_types import (
    CpuAssignment,
    CpuFrequency,
    CpuIsolateAssignment,
    CpuSchedulingPlan,
    FrequencyConfig,
    FrequencyProfile,
    ProfileAssignment,
    TccConfigProfile,
)


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


def _make_freq_profile(
    profile_id: str,
    governor: str = "performance",
    min_mhz: int = 2000,
    max_mhz: int = 2000,
) -> FrequencyProfile:
    return FrequencyProfile(
        profile_id=profile_id,
        frequency_config=FrequencyConfig(
            governor=governor,  # type: ignore[arg-type]
            min_freq_mhz=min_mhz,
            max_freq_mhz=max_mhz,
        ),
    )


def _make_cpu_frequency(
    profiles: dict,
    assignments: list[CpuAssignment],
) -> CpuFrequency:
    return CpuFrequency(
        frequency_profiles=profiles,
        profile_assignments=ProfileAssignment(cpu_assignments=assignments),
    )


def _make_tcc_profile(
    profile_id: str = "test-profile",
    description: str | None = "A test profile",
    cpu_scheduling: CpuSchedulingPlan | None = None,
    cpu_frequency: CpuFrequency | None = None,
) -> TccConfigProfile:
    return TccConfigProfile(
        profile_id=profile_id,
        profile_description=description,
        cpu_scheduling=cpu_scheduling,
        cpu_frequency=cpu_frequency,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_documents() -> list[dict]:
    """Minimal placeholder – TCCRawToDataModelMapping is always patched."""
    return [{"dummy": "doc"}]


@pytest.fixture
def minimal_profile() -> TccConfigProfile:
    """Profile with no optional sub-sections."""
    return _make_tcc_profile()


@pytest.fixture
def full_profile() -> TccConfigProfile:
    """Profile with CPU scheduling and frequency sections populated."""
    scheduling = CpuSchedulingPlan(
        assignments=[
            CpuIsolateAssignment(cpu_id=0, isolate=False),
            CpuIsolateAssignment(cpu_id=1, isolate=True),
            CpuIsolateAssignment(cpu_id=2, isolate=True),
            CpuIsolateAssignment(cpu_id=3, isolate=False),
        ]
    )

    rt_profile = _make_freq_profile("rt", governor="performance", min_mhz=3000, max_mhz=3000)
    be_profile = _make_freq_profile("be", governor="powersave", min_mhz=800, max_mhz=2400)

    frequency = _make_cpu_frequency(
        profiles={"rt": rt_profile, "be": be_profile},
        assignments=[
            CpuAssignment(cpu_id=0, profile_ref="be"),
            CpuAssignment(cpu_id=1, profile_ref="rt"),
            CpuAssignment(cpu_id=2, profile_ref="rt"),
            CpuAssignment(cpu_id=3, profile_ref="be"),
        ],
    )

    return _make_tcc_profile(
        profile_id="full-profile",
        description="Full test profile",
        cpu_scheduling=scheduling,
        cpu_frequency=frequency,
    )


def _make_api(profile: TccConfigProfile, mock_documents: list[dict]) -> TCCConfigDataAPI:
    """Instantiate TCCConfigDataAPI with the mapper patched to return *profile*."""
    with patch(
        "time_config_hub.services.tcc.api.data_api.TCCRawToDataModelMapping"
        ".documents_to_tcc_data_model",
        return_value=profile,
    ):
        return TCCConfigDataAPI(mock_documents)


# ---------------------------------------------------------------------------
# __init__ / construction
# ---------------------------------------------------------------------------


class TestTCCConfigDataAPIInit:
    """Tests for TCCConfigDataAPI.__init__ and property delegation."""

    def test_init_calls_mapper(self, mock_documents):
        profile = _make_tcc_profile()
        with patch(
            "time_config_hub.services.tcc.api.data_api.TCCRawToDataModelMapping"
            ".documents_to_tcc_data_model",
            return_value=profile,
        ) as mock_mapper:
            TCCConfigDataAPI(mock_documents)
            mock_mapper.assert_called_once_with(mock_documents)

    def test_profile_id_property(self, mock_documents):
        profile = _make_tcc_profile(profile_id="my-id")
        api = _make_api(profile, mock_documents)
        assert api.profile_id == "my-id"

    def test_profile_description_property(self, mock_documents):
        profile = _make_tcc_profile(description="hello")
        api = _make_api(profile, mock_documents)
        assert api.profile_description == "hello"

    def test_profile_description_none(self, mock_documents):
        profile = _make_tcc_profile(description=None)
        api = _make_api(profile, mock_documents)
        assert api.profile_description is None


# ---------------------------------------------------------------------------
# list_of_subsystem_configured
# ---------------------------------------------------------------------------


class TestListOfSubsystemsConfigured:
    def test_empty_when_no_subsections(self, mock_documents, minimal_profile):
        api = _make_api(minimal_profile, mock_documents)
        assert api.list_of_subsystem_configured() == set()

    def test_cpu_scheduling_subsystem(self, mock_documents):
        profile = _make_tcc_profile(
            cpu_scheduling=CpuSchedulingPlan(),
        )
        api = _make_api(profile, mock_documents)
        assert "cpu-scheduling" in api.list_of_subsystem_configured()

    def test_cpu_frequency_subsystem(self, mock_documents):
        profile = _make_tcc_profile(cpu_frequency=CpuFrequency())
        api = _make_api(profile, mock_documents)
        assert "cpu-frequency" in api.list_of_subsystem_configured()

    def test_returns_only_present_subsystems(self, mock_documents, full_profile):
        api = _make_api(full_profile, mock_documents)
        subsystems = api.list_of_subsystem_configured()
        assert subsystems == {"cpu-scheduling", "cpu-frequency"}

    def test_uncore_and_qos_subsystems(self, mock_documents):
        profile = TccConfigProfile(
            profile_id="p",
            uncore_frequency=MagicMock(),
            platform_qos_resource_config=MagicMock(),
        )
        api = _make_api(profile, mock_documents)
        subsystems = api.list_of_subsystem_configured()
        assert "uncore-frequency" in subsystems
        assert "platform-qos-resource-config" in subsystems


# ---------------------------------------------------------------------------
# cpu_scheduling
# ---------------------------------------------------------------------------


class TestCpuScheduling:
    def test_returns_none_when_absent(self, mock_documents, minimal_profile):
        api = _make_api(minimal_profile, mock_documents)
        assert api.cpu_scheduling() is None

    def test_returns_scheduling_plan(self, mock_documents, full_profile):
        api = _make_api(full_profile, mock_documents)
        result = api.cpu_scheduling()
        assert result is not None
        assert isinstance(result, CpuSchedulingPlan)


# ---------------------------------------------------------------------------
# isolated_cpus / non_isolated_cpus
# ---------------------------------------------------------------------------


class TestIsolatedCpus:
    def test_empty_when_no_scheduling(self, mock_documents, minimal_profile):
        api = _make_api(minimal_profile, mock_documents)
        assert api.isolated_cpus() == []

    def test_isolated_cpus(self, mock_documents, full_profile):
        api = _make_api(full_profile, mock_documents)
        assert sorted(api.isolated_cpus()) == [1, 2]

    def test_non_isolated_cpus(self, mock_documents, full_profile):
        api = _make_api(full_profile, mock_documents)
        assert sorted(api.non_isolated_cpus()) == [0, 3]

    def test_empty_when_no_scheduling_non_isolated(self, mock_documents, minimal_profile):
        api = _make_api(minimal_profile, mock_documents)
        assert api.non_isolated_cpus() == []

    def test_all_isolated(self, mock_documents):
        scheduling = CpuSchedulingPlan(
            assignments=[
                CpuIsolateAssignment(cpu_id=0, isolate=True),
                CpuIsolateAssignment(cpu_id=1, isolate=True),
            ]
        )
        profile = _make_tcc_profile(cpu_scheduling=scheduling)
        api = _make_api(profile, mock_documents)
        assert sorted(api.isolated_cpus()) == [0, 1]
        assert api.non_isolated_cpus() == []


# ---------------------------------------------------------------------------
# cpu_frequency_profiles / frequency_profile / all_frequency_profiles
# ---------------------------------------------------------------------------


class TestFrequencyProfiles:
    def test_returns_none_when_no_frequency(self, mock_documents, minimal_profile):
        api = _make_api(minimal_profile, mock_documents)
        assert api.cpu_frequency_profiles() is None

    def test_returns_cpu_frequency_object(self, mock_documents, full_profile):
        api = _make_api(full_profile, mock_documents)
        result = api.cpu_frequency_profiles()
        assert isinstance(result, CpuFrequency)

    def test_all_frequency_profiles_empty_when_no_section(self, mock_documents, minimal_profile):
        api = _make_api(minimal_profile, mock_documents)
        assert api.all_frequency_profiles() == {}

    def test_all_frequency_profiles(self, mock_documents, full_profile):
        api = _make_api(full_profile, mock_documents)
        profiles = api.all_frequency_profiles()
        assert set(profiles.keys()) == {"rt", "be"}

    def test_frequency_profile_found(self, mock_documents, full_profile):
        api = _make_api(full_profile, mock_documents)
        profile = api.frequency_profile("rt")
        assert profile is not None
        assert profile.profile_id == "rt"
        assert profile.frequency_config.governor == "performance"

    def test_frequency_profile_not_found(self, mock_documents, full_profile):
        api = _make_api(full_profile, mock_documents)
        assert api.frequency_profile("nonexistent") is None

    def test_frequency_profile_when_no_frequency_section(self, mock_documents, minimal_profile):
        api = _make_api(minimal_profile, mock_documents)
        assert api.frequency_profile("any") is None


# ---------------------------------------------------------------------------
# cpu_frequency_assignment / frequency_profile_for_cpu
# ---------------------------------------------------------------------------


class TestCpuFrequencyAssignment:
    def test_returns_none_when_no_frequency_section(self, mock_documents, minimal_profile):
        api = _make_api(minimal_profile, mock_documents)
        assert api.cpu_frequency_assignment(0) is None

    def test_returns_profile_ref_for_assigned_cpu(self, mock_documents, full_profile):
        api = _make_api(full_profile, mock_documents)
        assert api.cpu_frequency_assignment(1) == "rt"
        assert api.cpu_frequency_assignment(0) == "be"

    def test_returns_none_for_unassigned_cpu(self, mock_documents, full_profile):
        api = _make_api(full_profile, mock_documents)
        assert api.cpu_frequency_assignment(99) is None

    def test_frequency_profile_for_cpu_returns_correct_profile(self, mock_documents, full_profile):
        api = _make_api(full_profile, mock_documents)
        profile = api.frequency_profile_for_cpu(2)
        assert profile is not None
        assert profile.profile_id == "rt"

    def test_frequency_profile_for_cpu_unassigned(self, mock_documents, full_profile):
        api = _make_api(full_profile, mock_documents)
        assert api.frequency_profile_for_cpu(99) is None

    def test_frequency_profile_for_cpu_no_frequency_section(self, mock_documents, minimal_profile):
        api = _make_api(minimal_profile, mock_documents)
        assert api.frequency_profile_for_cpu(0) is None


# ---------------------------------------------------------------------------
# cpus_for_frequency_profile
# ---------------------------------------------------------------------------


class TestCpusForFrequencyProfile:
    def test_empty_when_no_frequency_section(self, mock_documents, minimal_profile):
        api = _make_api(minimal_profile, mock_documents)
        assert api.cpus_for_frequency_profile("rt") == []

    def test_returns_correct_cpus(self, mock_documents, full_profile):
        api = _make_api(full_profile, mock_documents)
        assert sorted(api.cpus_for_frequency_profile("rt")) == [1, 2]
        assert sorted(api.cpus_for_frequency_profile("be")) == [0, 3]

    def test_returns_empty_for_unknown_profile(self, mock_documents, full_profile):
        api = _make_api(full_profile, mock_documents)
        assert api.cpus_for_frequency_profile("ghost") == []


# ---------------------------------------------------------------------------
# validate_consistency
# ---------------------------------------------------------------------------


class TestValidateConsistency:
    def test_no_issues_with_minimal_profile(self, mock_documents, minimal_profile):
        api = _make_api(minimal_profile, mock_documents)
        assert api.validate_consistency() == []

    def test_no_issues_with_consistent_full_profile(self, mock_documents, full_profile):
        api = _make_api(full_profile, mock_documents)
        assert api.validate_consistency() == []

    def test_detects_scheduled_cpus_missing_frequency_assignment(self, mock_documents):
        scheduling = CpuSchedulingPlan(
            assignments=[
                CpuIsolateAssignment(cpu_id=0, isolate=False),
                CpuIsolateAssignment(cpu_id=1, isolate=True),
            ]
        )
        # Only CPU 0 is assigned a frequency profile; CPU 1 is missing
        frequency = _make_cpu_frequency(
            profiles={"rt": _make_freq_profile("rt")},
            assignments=[CpuAssignment(cpu_id=0, profile_ref="rt")],
        )
        profile = _make_tcc_profile(cpu_scheduling=scheduling, cpu_frequency=frequency)
        api = _make_api(profile, mock_documents)
        issues = api.validate_consistency()
        assert len(issues) == 1
        assert "1" in issues[0]

    def test_detects_extra_frequency_assignments(self, mock_documents):
        scheduling = CpuSchedulingPlan(
            assignments=[CpuIsolateAssignment(cpu_id=0, isolate=False)]
        )
        # CPU 5 has a frequency assignment but is not in scheduling
        frequency = _make_cpu_frequency(
            profiles={"rt": _make_freq_profile("rt")},
            assignments=[
                CpuAssignment(cpu_id=0, profile_ref="rt"),
                CpuAssignment(cpu_id=5, profile_ref="rt"),
            ],
        )
        profile = _make_tcc_profile(cpu_scheduling=scheduling, cpu_frequency=frequency)
        api = _make_api(profile, mock_documents)
        issues = api.validate_consistency()
        assert any("5" in issue for issue in issues)

    def test_detects_undefined_profile_references(self, mock_documents):
        frequency = _make_cpu_frequency(
            profiles={"rt": _make_freq_profile("rt")},
            assignments=[
                CpuAssignment(cpu_id=0, profile_ref="rt"),
                CpuAssignment(cpu_id=1, profile_ref="undefined-profile"),
            ],
        )
        profile = _make_tcc_profile(cpu_frequency=frequency)
        api = _make_api(profile, mock_documents)
        issues = api.validate_consistency()
        assert any("undefined-profile" in issue for issue in issues)

    def test_no_issues_when_only_scheduling_present(self, mock_documents):
        scheduling = CpuSchedulingPlan(
            assignments=[CpuIsolateAssignment(cpu_id=0, isolate=False)]
        )
        profile = _make_tcc_profile(cpu_scheduling=scheduling)
        api = _make_api(profile, mock_documents)
        assert api.validate_consistency() == []

    def test_no_issues_when_only_frequency_present(self, mock_documents):
        frequency = _make_cpu_frequency(
            profiles={"rt": _make_freq_profile("rt")},
            assignments=[CpuAssignment(cpu_id=0, profile_ref="rt")],
        )
        profile = _make_tcc_profile(cpu_frequency=frequency)
        api = _make_api(profile, mock_documents)
        assert api.validate_consistency() == []


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------


class TestSummary:
    def test_summary_contains_profile_id(self, mock_documents, full_profile):
        api = _make_api(full_profile, mock_documents)
        result = api.summary()
        assert "full-profile" in result

    def test_summary_contains_description(self, mock_documents, full_profile):
        api = _make_api(full_profile, mock_documents)
        result = api.summary()
        assert "Full test profile" in result

    def test_summary_no_description(self, mock_documents):
        profile = _make_tcc_profile(profile_id="p", description=None)
        api = _make_api(profile, mock_documents)
        result = api.summary()
        assert "(none)" in result

    def test_summary_contains_isolated_cpus(self, mock_documents, full_profile):
        api = _make_api(full_profile, mock_documents)
        result = api.summary()
        assert "Isolated CPUs" in result

    def test_summary_contains_frequency_profiles(self, mock_documents, full_profile):
        api = _make_api(full_profile, mock_documents)
        result = api.summary()
        assert "Frequency Profiles" in result
        assert "rt" in result
        assert "be" in result

    def test_summary_minimal_profile(self, mock_documents, minimal_profile):
        api = _make_api(minimal_profile, mock_documents)
        result = api.summary()
        assert "test-profile" in result
        assert "Isolated CPUs" not in result
        assert "Frequency Profiles" not in result
