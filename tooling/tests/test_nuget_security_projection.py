import xml.etree.ElementTree as ET

import pytest

from tooling.security import nuget_scan_document


def test_literal_project_property_and_exact_range_reach_the_scanner_as_one_version():
    original = b'<Project><PropertyGroup><Version>4.0.0</Version></PropertyGroup><ItemGroup><PackageReference Include="STRling" Version="[$(Version)]" Condition="release-only"/><PackageReference Include="FSharp.Core" Version="9.0.300"/></ItemGroup></Project>'
    projected = ET.fromstring(nuget_scan_document(original))
    packages = projected.findall("ItemGroup/PackageReference")
    assert [(row.get("Include"), row.get("Version")) for row in packages] == [
        ("STRling", "4.0.0"),
        ("FSharp.Core", "9.0.300"),
    ]
    assert packages[0].get("Condition") == "release-only"
    assert b"[$(Version)]" in original


@pytest.mark.parametrize(
    "version", ["[4.0.0,5.0.0)", "4.*", "$(OtherVersion)", "latest", ""]
)
def test_scan_refuses_to_choose_an_unresolved_or_floating_dependency(version):
    with pytest.raises(ValueError):
        nuget_scan_document(
            (
                '<Project><ItemGroup><PackageReference Include="fixture" Version="'
                + version
                + '"/></ItemGroup></Project>'
            ).encode()
        )


@pytest.mark.parametrize(
    "properties", ["", "<Version>3.0.0</Version><Version>4.0.0</Version>"]
)
def test_scan_refuses_missing_or_ambiguous_project_version(properties):
    with pytest.raises(ValueError, match="ambiguous"):
        nuget_scan_document(
            (
                "<Project><PropertyGroup>"
                + properties
                + '</PropertyGroup><ItemGroup><PackageReference Include="STRling" Version="[$(Version)]"/></ItemGroup></Project>'
            ).encode()
        )


def test_scan_refuses_conflicting_attribute_and_child_version():
    with pytest.raises(ValueError, match="duplicate"):
        nuget_scan_document(
            b'<Project><ItemGroup><PackageReference Include="fixture" Version="4.0.0"><Version>3.0.0</Version></PackageReference></ItemGroup></Project>'
        )
