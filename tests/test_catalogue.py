"""Pinned PySPG adapter checks; enumerating configurations performs no economics.

Origins: pre-reset catalogue.source_identity/finite_catalogue contract and
their audited upstream iterator. These checks import no historical model.
"""
import unittest

from cpm_abm import catalogue


class CatalogueTests(unittest.TestCase):
    """Check source identity, deterministic enumeration and configuration isolation."""

    def test_pinned_upstream_and_compatibility_bytes(self):
        """Retained source files and the narrow Python3 iterator conversion match their manifests."""
        identity = catalogue.source_identity()
        self.assertEqual(identity["repository"], "https://github.com/tessonec/PySPG")
        self.assertEqual(identity["commit"], "2e6b4bb8512cd73838c190b8c9a616b7ebef188a")
        self.assertEqual(identity["upstream_sha256"], "ab997003b0b50572e48bb6c56654c5250cbe596ccdba0f15ffbd118cfb1ed73e")
        self.assertEqual(identity["converted_sha256"], "9bc1163dc905acc644ca9289acc9e137547bf19482fbb28a49b4433ae4a07689")
        self.assertGreater(identity["verified_upstream_files"], 0)

    def test_explicit_cartesian_order(self):
        """The last declared dimension advances fastest with no omitted or invented point."""
        points = list(catalogue.finite_catalogue(dict(r_out=[0.0, .0037], a0=[0.0, .75])))
        self.assertEqual(points, [dict(r_out=0.0,a0=0.0), dict(r_out=0.0,a0=.75),
                                  dict(r_out=.0037,a0=0.0), dict(r_out=.0037,a0=.75)])

    def test_returned_configurations_are_independent(self):
        """Mutating a completed job cannot alter later jobs or the supplied value list."""
        source = dict(setting=[dict(values=[])], index=[1,2])
        jobs = catalogue.finite_catalogue(source)
        first = next(jobs)
        first["setting"]["values"].append("changed")
        second = next(jobs)
        self.assertEqual(second["setting"]["values"], [])
        self.assertEqual(source["setting"][0]["values"], [])

    def test_empty_or_implicit_domains_are_rejected(self):
        """A missing domain, empty domain or unmaterialized range cannot launch enumeration."""
        for parameters in ({}, dict(r_out=[]), dict(r_out=range(2)), {"": [1]}):
            with self.assertRaises(ValueError):
                list(catalogue.finite_catalogue(parameters))
