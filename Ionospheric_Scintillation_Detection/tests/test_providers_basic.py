from isd.domain.enums import CoordinateSource, FileKind, GnssSystem, PppStatus
from isd.domain.models import ProjectFile, Station
from isd.providers.stub_providers import (
    BasicAntennaCorrectionProvider,
    BasicOrbitClockCorrectionProvider,
    BasicPreciseCoordinateProvider,
)


def _station() -> Station:
    return Station(
        id="p:ABCD",
        project_id="p",
        station_code="ABCD",
        systems=[GnssSystem.GPS],
        coordinate_source=CoordinateSource.RINEX_APPROX,
        ppp_status=PppStatus.NOT_STARTED,
    )


def test_basic_coordinate_provider_prefers_ppp_and_precise():
    provider = BasicPreciseCoordinateProvider()
    station = _station()
    files = [
        ProjectFile(
            id="obs",
            project_id="p",
            station_id="ABCD",
            kind=FileKind.OBS,
            file_path="obs.24o",
            file_name="obs.24o",
            file_date="2024-03-24",
            systems=[GnssSystem.GPS],
        )
    ]

    rsp1 = provider.resolve(station, "2024-03-24", files)
    assert rsp1.coordinate_source == CoordinateSource.RINEX_APPROX
    assert rsp1.available is True
    assert rsp1.formal_ready is False

    station.ppp_status = PppStatus.SUCCESS
    station.coordinate_source = CoordinateSource.PPP
    rsp2 = provider.resolve(station, "2024-03-24", files)
    assert rsp2.coordinate_source == CoordinateSource.PPP
    assert rsp2.formal_ready is True



def test_basic_orbit_and_antenna_provider_support_formal_and_fallback():
    orbit = BasicOrbitClockCorrectionProvider()
    antenna = BasicAntennaCorrectionProvider()
    station = _station()

    files_nav = [
        ProjectFile(
            id="nav",
            project_id="p",
            station_id=None,
            kind=FileKind.NAV,
            file_path="brdc.nav",
            file_name="brdc.nav",
            file_date="2024-03-24",
        )
    ]
    orbit_nav = orbit.resolve("2024-03-24", files_nav)
    assert orbit_nav.source == "NAV_FALLBACK"
    assert orbit_nav.available is True
    assert orbit_nav.formal_ready is False

    files_formal = [
        ProjectFile(
            id="sp3",
            project_id="p",
            station_id=None,
            kind=FileKind.SP3,
            file_path="igs.sp3",
            file_name="igs.sp3",
            file_date="2024-03-24",
        ),
        ProjectFile(
            id="clk",
            project_id="p",
            station_id=None,
            kind=FileKind.CLK,
            file_path="igs.clk",
            file_name="igs.clk",
            file_date="2024-03-24",
        ),
        ProjectFile(
            id="atx",
            project_id="p",
            station_id=None,
            kind=FileKind.ATX,
            file_path="igs20.atx",
            file_name="igs20.atx",
        ),
    ]
    orbit_formal = orbit.resolve("2024-03-24", files_formal)
    assert orbit_formal.source == "SP3_CLK"
    assert orbit_formal.formal_ready is True

    ant_formal = antenna.resolve(station, files_formal)
    assert ant_formal.source == "ATX_FILE"
    assert ant_formal.formal_ready is True
