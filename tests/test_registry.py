"""Tests for the manifest registry (registry.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mentalplay_arena.config import get_settings
from mentalplay_arena.registry import Registry

# The 21 module directories present under data/scales/.
EXPECTED_MODULES = {
    "ARI", "AUDIT", "BPRS", "CDRS", "C-SSRS", "EDE-Q", "GAD-7", "K-SADS",
    "PCL-5", "PHQ-9", "SAPAS", "SCARED-PD", "SCARED-SAD", "SCARED-SocP",
    "SCARED-SP", "SCAS-S", "SMQ", "SNAP-IV-ADHD", "SNAP-IV-ODD", "Y-BOCS", "YMRS",
}

EXPECTED_EVALUATION_SCOPE = [
    "K-SADS", "PDQ-4", "PID-5", "SCL-90", "IIP-32", "IRI-C", "DERS", "DASS-42", "WHODAS",
]


@pytest.fixture
def registry() -> Registry:
    return Registry(get_settings())


class TestRegistry:
    def test_total_scale_count(self, registry):
        # 14 LIST + 18 KV (from the original compute_score registry).
        assert len(registry.all_names()) >= 32

    def test_every_scale_has_format(self, registry):
        for name in registry.all_names():
            assert registry.scale(name).format in {"LIST", "KV"}, name

    def test_module_dirs_exist(self, registry):
        for name in registry.module_names():
            d = registry.scale_dir(name)
            assert d.is_dir(), f"module dir missing for {name}"
            assert (d / "config.yaml").exists(), f"config.yaml missing for {name}"
            assert (d / "inquiries.json").exists(), f"inquiries.json missing for {name}"
            assert (d / "scoring.py").exists(), f"scoring.py missing for {name}"

    def test_manifest_modules_match_disk(self, registry):
        from mentalplay_arena.config import get_settings as gs

        scales_dir = gs().resolve(gs().scales_dir)
        disk_modules = {p.name for p in scales_dir.iterdir() if p.is_dir()}
        assert set(registry.module_names()) == EXPECTED_MODULES
        assert disk_modules == EXPECTED_MODULES

    def test_evaluation_scope(self, registry):
        assert registry.evaluation_scope == EXPECTED_EVALUATION_SCOPE

    def test_unknown_scale_raises(self, registry):
        with pytest.raises(KeyError):
            registry.scale("NOPE")

    def test_legacy_scales_have_no_module(self, registry):
        for name in ["PDQ-4", "IIP-32", "DASS-42", "WHODAS"]:
            assert registry.scale(name).has_module is False
            with pytest.raises(KeyError):
                registry.scale_dir(name)

    def test_kv_dimensions_loaded(self, registry):
        whodas = registry.scale("WHODAS")
        assert set(whodas.dimensions) == {
            "Cognition", "Mobility", "Self_care", "Getting_along",
            "Life_activities", "Participation",
        }
        dass = registry.scale("DASS-42")
        assert "extremely severe" in dass.dimensions["Depression"]

    def test_list_labels_loaded(self, registry):
        ksads = registry.scale("K-SADS")
        assert len(ksads.labels) == 23
        assert "Schizophrenia" in ksads.labels

    def test_pdq4_dimension_thresholds(self, registry):
        pdq4 = registry.scale("PDQ-4")
        assert pdq4.dimension_thresholds["antisocial"] == 3
        assert pdq4.dimension_thresholds["borderline"] == 5
