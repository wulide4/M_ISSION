from pathlib import Path

from isd.application.task_service import TaskService
from isd.domain.enums import ChainLevel, CoordinateSource, FileKind, GnssSystem, PppStatus, ProjectStatus
from isd.domain.models import Project, ProjectFile, Station
from isd.infrastructure.db.sqlite import Database
from isd.infrastructure.filesystem.paths import WorkspacePaths
from isd.infrastructure.filesystem.result_store import ResultStore
from isd.infrastructure.repositories.project_file_repository import ProjectFileRepository
from isd.infrastructure.repositories.result_repository import ResultRepository
from isd.infrastructure.repositories.settings_repository import SettingsRepository
from isd.infrastructure.repositories.station_repository import StationRepository
from isd.infrastructure.repositories.task_log_repository import TaskLogRepository
from isd.infrastructure.repositories.task_repository import TaskRepository
from isd.infrastructure.repositories.task_step_repository import TaskStepRepository
from isd.infrastructure.repositories.validation_repository import ValidationIssueRepository
from isd.workers.task_worker import TaskWorkerManager


def _service(tmp_path: Path) -> TaskService:
    db_path = tmp_path / 'test.sqlite3'
    db = Database(db_path)
    migrations = Path(__file__).resolve().parents[1] / 'src' / 'isd' / 'infrastructure' / 'db' / 'migrations'
    db.init(migrations)
    conn = db.connect()

    workspace = WorkspacePaths(tmp_path / 'workspace')
    workspace.ensure()
    settings_repo = SettingsRepository(conn)

    return TaskService(
        workspace=workspace,
        task_repo=TaskRepository(conn),
        station_repo=StationRepository(conn),
        project_file_repo=ProjectFileRepository(conn),
        validation_repo=ValidationIssueRepository(conn),
        result_repo=ResultRepository(conn),
        task_log_repo=TaskLogRepository(conn),
        task_step_repo=TaskStepRepository(conn),
        worker=TaskWorkerManager(workspace, ResultStore()),
        settings_repo=settings_repo,
    )


def _seed_project(service: TaskService, project_id: str) -> None:
    now = '2026-04-20T00:00:00Z'
    project = Project(
        id=project_id,
        name='demo',
        description='',
        root_path=str(Path.cwd()),
        created_at=now,
        updated_at=now,
        default_output_path=str(Path.cwd() / 'workspace' / 'reports'),
        tags=[],
        status=ProjectStatus.ACTIVE,
    )
    service.task_repo.conn.execute(
        '''
        INSERT INTO projects(
            id,name,description,root_path,created_at,updated_at,data_range_start,data_range_end,default_output_path,tags_json,status
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        ''',
        (
            project.id,
            project.name,
            project.description,
            project.root_path,
            project.created_at,
            project.updated_at,
            None,
            None,
            project.default_output_path,
            '[]',
            project.status.value,
        ),
    )
    service.task_repo.conn.commit()


def _seed_station(service: TaskService, project_id: str, station_code: str, *, ppp: PppStatus = PppStatus.SUCCESS) -> None:
    station = Station(
        id=f'{project_id}:{station_code}',
        project_id=project_id,
        station_code=station_code,
        systems=[GnssSystem.GPS],
        coordinate_source=CoordinateSource.PRECISE_FILE,
        ppp_status=ppp,
    )
    service.station_repo.replace_for_project(project_id, [station])


def _seed_files(service: TaskService, project_id: str, files: list[ProjectFile]) -> None:
    service.project_file_repo.replace_for_project(project_id, files)


def test_validate_task_sigma_simplified_mode_without_sp3_clk_atx(tmp_path: Path):
    service = _service(tmp_path)
    project_id = 'p1'
    _seed_project(service, project_id)
    _seed_station(service, project_id, 'ABCD', ppp=PppStatus.SUCCESS)
    _seed_files(
        service,
        project_id,
        [
            ProjectFile(
                id='f1',
                project_id=project_id,
                station_id='ABCD',
                kind=FileKind.OBS,
                file_path='obs.24o',
                file_name='abcd0840.24o',
                file_date='2024-03-24',
                systems=[GnssSystem.GPS],
            ),
        ],
    )

    payload = {
        'config': {
            'project_id': project_id,
            'station_ids': ['ABCD'],
            'date_range': {'start': '2024-03-24', 'end': '2024-03-24'},
            'systems': ['GPS'],
            'metrics': ['SIGMA_PHI_F'],
            'chain_level': 'FORMAL',
            'sampling_mode': 'STANDARD_30S',
            'output_path': str(tmp_path / 'out'),
            'parallelism': 1,
            'enable_intermediate_save': True,
            'enable_intermediate_preview': True,
            'enable_nav_fallback': False,
            'enable_experimental_sigma_phi_f': False,
            'enable_1s_resample': False,
            'threshold_config': [],
            'algorithm_config': {},
        }
    }

    rsp = service.validate_task(payload)
    assert rsp.success is True
    # Per M_ISSION paper: sigma_phi_f can run in simplified mode without SP3/CLK/ATX
    assert rsp.data['canRun'] is True
    codes = {x['code'] for x in rsp.data['issues']}
    # Should have warnings about missing files, not blocking errors
    assert 'SIGMAPHI_NO_ATX_SIMPLIFIED' in codes or 'SIGMAPHI_SIMPLIFIED_MODE' in codes


def test_validate_task_allows_nav_fallback_for_sigma(tmp_path: Path):
    service = _service(tmp_path)
    assert service.settings_repo is not None
    service.settings_repo.set(
        "system",
        {
            "enableNavDegradedMode": True,
            "enableNonGpsSigmaPhiF": False,
            "enableExperimental1sResample": False,
            "rinexApproxSigmaPhiFPolicy": "WARNING",
        },
    )
    project_id = 'p_nav'
    _seed_project(service, project_id)
    _seed_station(service, project_id, 'ABCD', ppp=PppStatus.SUCCESS)
    _seed_files(
        service,
        project_id,
        [
            ProjectFile(
                id='f1',
                project_id=project_id,
                station_id='ABCD',
                kind=FileKind.OBS,
                file_path='obs.24o',
                file_name='abcd0840.24o',
                file_date='2024-03-24',
                systems=[GnssSystem.GPS],
            ),
            ProjectFile(
                id='f2',
                project_id=project_id,
                station_id=None,
                kind=FileKind.NAV,
                file_path='nav.nav',
                file_name='brdc0840.24n',
                file_date='2024-03-24',
            ),
            ProjectFile(
                id='f3',
                project_id=project_id,
                station_id=None,
                kind=FileKind.ATX,
                file_path='igs20.atx',
                file_name='igs20.atx',
            ),
        ],
    )

    payload = {
        'config': {
            'project_id': project_id,
            'station_ids': ['ABCD'],
            'date_range': {'start': '2024-03-24', 'end': '2024-03-24'},
            'systems': ['GPS'],
            'metrics': ['SIGMA_PHI_F'],
            'chain_level': 'FORMAL',
            'sampling_mode': 'STANDARD_30S',
            'output_path': str(tmp_path / 'out'),
            'parallelism': 1,
            'enable_intermediate_save': True,
            'enable_intermediate_preview': True,
            'enable_nav_fallback': True,
            'enable_experimental_sigma_phi_f': False,
            'enable_1s_resample': False,
            'threshold_config': [],
            'algorithm_config': {},
        }
    }
    rsp = service.validate_task(payload)
    assert rsp.success is True
    assert rsp.data['canRun'] is True
    assert rsp.data['derivedChainLevel'] == ChainLevel.DEGRADED.value
    codes = {x['code'] for x in rsp.data['issues']}
    assert 'NAV_FALLBACK_DEGRADED_MODE' in codes
    assert 'SIGMAPHI_NEED_SP3' not in codes
    assert 'SIGMAPHI_NEED_CLK' not in codes
    assert 'NON_FORMAL_CHAIN_LEVEL' in rsp.data['riskFlags']
    assert 'DEGRADED_CHAIN_LEVEL' in rsp.data['riskFlags']
    assert 'NAV_FALLBACK_ENABLED' in rsp.data['riskFlags']
    provider = rsp.data.get("providerSummary") or {}
    assert provider.get("providerChainHint") == ChainLevel.DEGRADED.value
    assert provider.get("allOrbitAvailable") is True
    assert provider.get("allOrbitFormalReady") is False
    assert provider.get("dateProviders", {}).get("2024-03-24", {}).get("orbitClockSource") == "NAV_FALLBACK"


def test_validate_task_blocks_unknown_station(tmp_path: Path):
    service = _service(tmp_path)
    project_id = 'p_station'
    _seed_project(service, project_id)

    payload = {
        'config': {
            'project_id': project_id,
            'station_ids': ['MISS'],
            'date_range': {'start': '2024-03-24', 'end': '2024-03-24'},
            'systems': ['GPS'],
            'metrics': ['ROTI'],
            'chain_level': 'FORMAL',
            'sampling_mode': 'STANDARD_30S',
            'output_path': str(tmp_path / 'out'),
            'parallelism': 1,
            'enable_intermediate_save': True,
            'enable_intermediate_preview': True,
            'enable_nav_fallback': False,
            'enable_experimental_sigma_phi_f': False,
            'enable_1s_resample': False,
            'threshold_config': [],
            'algorithm_config': {},
        }
    }
    rsp = service.validate_task(payload)
    assert rsp.success is True
    assert rsp.data['canRun'] is False
    codes = {x['code'] for x in rsp.data['issues']}
    assert 'STATION_NOT_FOUND' in codes


def test_validate_task_blocks_obs_data_gap(tmp_path: Path):
    service = _service(tmp_path)
    project_id = 'p_obs_gap'
    _seed_project(service, project_id)
    _seed_station(service, project_id, 'ABCD', ppp=PppStatus.SUCCESS)
    _seed_files(
        service,
        project_id,
        [
            ProjectFile(
                id='f1',
                project_id=project_id,
                station_id='ABCD',
                kind=FileKind.OBS,
                file_path='obs.24o',
                file_name='abcd0830.24o',
                file_date='2024-03-23',
                systems=[GnssSystem.GPS],
            ),
        ],
    )

    payload = {
        'config': {
            'project_id': project_id,
            'station_ids': ['ABCD'],
            'date_range': {'start': '2024-03-24', 'end': '2024-03-24'},
            'systems': ['GPS'],
            'metrics': ['ROTI'],
            'chain_level': 'FORMAL',
            'sampling_mode': 'STANDARD_30S',
            'output_path': str(tmp_path / 'out'),
            'parallelism': 1,
            'enable_intermediate_save': True,
            'enable_intermediate_preview': True,
            'enable_nav_fallback': False,
            'enable_experimental_sigma_phi_f': False,
            'enable_1s_resample': False,
            'threshold_config': [],
            'algorithm_config': {},
        }
    }
    rsp = service.validate_task(payload)
    assert rsp.success is True
    assert rsp.data['canRun'] is False
    codes = {x['code'] for x in rsp.data['issues']}
    assert 'OBS_DATA_MISSING_FOR_DATE' in codes


def test_validate_task_blocks_nav_fallback_when_global_switch_off(tmp_path: Path):
    service = _service(tmp_path)
    project_id = 'p_nav_block'
    _seed_project(service, project_id)
    _seed_station(service, project_id, 'ABCD', ppp=PppStatus.SUCCESS)
    _seed_files(
        service,
        project_id,
        [
            ProjectFile(
                id='f1',
                project_id=project_id,
                station_id='ABCD',
                kind=FileKind.OBS,
                file_path='obs.24o',
                file_name='abcd0840.24o',
                file_date='2024-03-24',
                systems=[GnssSystem.GPS],
            ),
            ProjectFile(
                id='f2',
                project_id=project_id,
                station_id=None,
                kind=FileKind.NAV,
                file_path='nav.nav',
                file_name='brdc0840.24n',
                file_date='2024-03-24',
            ),
            ProjectFile(
                id='f3',
                project_id=project_id,
                station_id=None,
                kind=FileKind.ATX,
                file_path='igs20.atx',
                file_name='igs20.atx',
            ),
        ],
    )
    payload = {
        'config': {
            'project_id': project_id,
            'station_ids': ['ABCD'],
            'date_range': {'start': '2024-03-24', 'end': '2024-03-24'},
            'systems': ['GPS'],
            'metrics': ['SIGMA_PHI_F'],
            'chain_level': 'FORMAL',
            'sampling_mode': 'STANDARD_30S',
            'output_path': str(tmp_path / 'out'),
            'parallelism': 1,
            'enable_intermediate_save': True,
            'enable_intermediate_preview': True,
            'enable_nav_fallback': True,
            'enable_experimental_sigma_phi_f': False,
            'enable_1s_resample': False,
            'threshold_config': [],
            'algorithm_config': {},
        }
    }
    rsp = service.validate_task(payload)
    assert rsp.success is True
    assert rsp.data['canRun'] is False
    codes = {x['code'] for x in rsp.data['issues']}
    assert 'NAV_FALLBACK_GLOBAL_DISABLED' in codes


def test_validate_task_blocks_rinex_approx_sigma_when_policy_blocking(tmp_path: Path):
    service = _service(tmp_path)
    assert service.settings_repo is not None
    service.settings_repo.set(
        "system",
        {
            "enableNavDegradedMode": False,
            "enableNonGpsSigmaPhiF": False,
            "enableExperimental1sResample": False,
            "rinexApproxSigmaPhiFPolicy": "BLOCKING",
        },
    )
    project_id = 'p_rinex_policy'
    _seed_project(service, project_id)
    station = Station(
        id=f'{project_id}:ABCD',
        project_id=project_id,
        station_code='ABCD',
        systems=[GnssSystem.GPS],
        coordinate_source=CoordinateSource.RINEX_APPROX,
        ppp_status=PppStatus.SUCCESS,
    )
    service.station_repo.replace_for_project(project_id, [station])
    _seed_files(
        service,
        project_id,
        [
            ProjectFile(
                id='obs',
                project_id=project_id,
                station_id='ABCD',
                kind=FileKind.OBS,
                file_path='obs.24o',
                file_name='abcd0840.24o',
                file_date='2024-03-24',
                systems=[GnssSystem.GPS],
            ),
            ProjectFile(
                id='sp3',
                project_id=project_id,
                station_id=None,
                kind=FileKind.SP3,
                file_path='igs24084.sp3',
                file_name='igs24084.sp3',
                file_date='2024-03-24',
            ),
            ProjectFile(
                id='clk',
                project_id=project_id,
                station_id=None,
                kind=FileKind.CLK,
                file_path='igs24084.clk',
                file_name='igs24084.clk',
                file_date='2024-03-24',
            ),
            ProjectFile(
                id='atx',
                project_id=project_id,
                station_id=None,
                kind=FileKind.ATX,
                file_path='igs20.atx',
                file_name='igs20.atx',
            ),
        ],
    )
    payload = {
        'config': {
            'project_id': project_id,
            'station_ids': ['ABCD'],
            'date_range': {'start': '2024-03-24', 'end': '2024-03-24'},
            'systems': ['GPS'],
            'metrics': ['SIGMA_PHI_F'],
            'chain_level': 'FORMAL',
            'sampling_mode': 'STANDARD_30S',
            'output_path': str(tmp_path / 'out'),
            'parallelism': 1,
            'enable_intermediate_save': True,
            'enable_intermediate_preview': True,
            'enable_nav_fallback': False,
            'enable_experimental_sigma_phi_f': False,
            'enable_1s_resample': False,
            'threshold_config': [],
            'algorithm_config': {},
        }
    }
    rsp = service.validate_task(payload)
    assert rsp.success is True
    assert rsp.data['canRun'] is False
    codes = {x['code'] for x in rsp.data['issues']}
    assert 'RINEX_APPROX_SIGMAPHI_BLOCKED' in codes


def test_validate_task_blocks_non_gps_sigma_when_global_switch_off(tmp_path: Path):
    service = _service(tmp_path)
    project_id = 'p_non_gps_global'
    _seed_project(service, project_id)
    _seed_station(service, project_id, 'ABCD', ppp=PppStatus.SUCCESS)
    _seed_files(
        service,
        project_id,
        [
            ProjectFile(
                id='obs',
                project_id=project_id,
                station_id='ABCD',
                kind=FileKind.OBS,
                file_path='obs.24o',
                file_name='abcd0840.24o',
                file_date='2024-03-24',
                systems=[GnssSystem.GLO],
            ),
            ProjectFile(
                id='sp3',
                project_id=project_id,
                station_id=None,
                kind=FileKind.SP3,
                file_path='igs24084.sp3',
                file_name='igs24084.sp3',
                file_date='2024-03-24',
            ),
            ProjectFile(
                id='clk',
                project_id=project_id,
                station_id=None,
                kind=FileKind.CLK,
                file_path='igs24084.clk',
                file_name='igs24084.clk',
                file_date='2024-03-24',
            ),
            ProjectFile(
                id='atx',
                project_id=project_id,
                station_id=None,
                kind=FileKind.ATX,
                file_path='igs20.atx',
                file_name='igs20.atx',
            ),
        ],
    )
    payload = {
        'config': {
            'project_id': project_id,
            'station_ids': ['ABCD'],
            'date_range': {'start': '2024-03-24', 'end': '2024-03-24'},
            'systems': ['GLO'],
            'metrics': ['SIGMA_PHI_F'],
            'chain_level': 'EXPERIMENTAL',
            'sampling_mode': 'STANDARD_30S',
            'output_path': str(tmp_path / 'out'),
            'parallelism': 1,
            'enable_intermediate_save': True,
            'enable_intermediate_preview': True,
            'enable_nav_fallback': False,
            'enable_experimental_sigma_phi_f': True,
            'enable_1s_resample': False,
            'threshold_config': [],
            'algorithm_config': {},
        }
    }
    rsp = service.validate_task(payload)
    assert rsp.success is True
    assert rsp.data['canRun'] is False
    codes = {x['code'] for x in rsp.data['issues']}
    assert 'SIGMAPHI_NON_GPS_GLOBAL_DISABLED' in codes


def test_validate_task_blocks_1s_sigma_when_global_switch_off(tmp_path: Path):
    service = _service(tmp_path)
    project_id = 'p_1s_global'
    _seed_project(service, project_id)
    # Explicitly disable 1s resample in system settings
    service.settings_repo.set("system", {"enableExperimental1sResample": False})
    _seed_station(service, project_id, 'ABCD', ppp=PppStatus.SUCCESS)
    _seed_files(
        service,
        project_id,
        [
            ProjectFile(
                id='obs',
                project_id=project_id,
                station_id='ABCD',
                kind=FileKind.OBS,
                file_path='obs.24o',
                file_name='abcd0840.24o',
                file_date='2024-03-24',
                systems=[GnssSystem.GPS],
            ),
            ProjectFile(
                id='sp3',
                project_id=project_id,
                station_id=None,
                kind=FileKind.SP3,
                file_path='igs24084.sp3',
                file_name='igs24084.sp3',
                file_date='2024-03-24',
            ),
            ProjectFile(
                id='clk',
                project_id=project_id,
                station_id=None,
                kind=FileKind.CLK,
                file_path='igs24084.clk',
                file_name='igs24084.clk',
                file_date='2024-03-24',
            ),
            ProjectFile(
                id='atx',
                project_id=project_id,
                station_id=None,
                kind=FileKind.ATX,
                file_path='igs20.atx',
                file_name='igs20.atx',
            ),
        ],
    )
    payload = {
        'config': {
            'project_id': project_id,
            'station_ids': ['ABCD'],
            'date_range': {'start': '2024-03-24', 'end': '2024-03-24'},
            'systems': ['GPS'],
            'metrics': ['SIGMA_PHI_F'],
            'chain_level': 'EXPERIMENTAL',
            'sampling_mode': 'EXPERIMENTAL_1S_RESAMPLED',
            'output_path': str(tmp_path / 'out'),
            'parallelism': 1,
            'enable_intermediate_save': True,
            'enable_intermediate_preview': True,
            'enable_nav_fallback': False,
            'enable_experimental_sigma_phi_f': False,
            'enable_1s_resample': True,
            'threshold_config': [],
            'algorithm_config': {},
        }
    }
    rsp = service.validate_task(payload)
    assert rsp.success is True
    assert rsp.data['canRun'] is False
    codes = {x['code'] for x in rsp.data['issues']}
    assert 'SAMPLING_1S_GLOBAL_DISABLED' in codes


def test_validate_task_provider_formal_chain_hint_when_precise_dependencies_ready(tmp_path: Path):
    service = _service(tmp_path)
    project_id = 'p_provider_formal'
    _seed_project(service, project_id)
    station = Station(
        id=f'{project_id}:ABCD',
        project_id=project_id,
        station_code='ABCD',
        systems=[GnssSystem.GPS],
        coordinate_source=CoordinateSource.PRECISE_FILE,
        ppp_status=PppStatus.SUCCESS,
    )
    service.station_repo.replace_for_project(project_id, [station])
    _seed_files(
        service,
        project_id,
        [
            ProjectFile(
                id='obs',
                project_id=project_id,
                station_id='ABCD',
                kind=FileKind.OBS,
                file_path='obs.24o',
                file_name='abcd0840.24o',
                file_date='2024-03-24',
                systems=[GnssSystem.GPS],
            ),
            ProjectFile(
                id='sp3',
                project_id=project_id,
                station_id=None,
                kind=FileKind.SP3,
                file_path='igs24084.sp3',
                file_name='igs24084.sp3',
                file_date='2024-03-24',
            ),
            ProjectFile(
                id='clk',
                project_id=project_id,
                station_id=None,
                kind=FileKind.CLK,
                file_path='igs24084.clk',
                file_name='igs24084.clk',
                file_date='2024-03-24',
            ),
            ProjectFile(
                id='atx',
                project_id=project_id,
                station_id=None,
                kind=FileKind.ATX,
                file_path='igs20.atx',
                file_name='igs20.atx',
            ),
        ],
    )
    payload = {
        'config': {
            'project_id': project_id,
            'station_ids': ['ABCD'],
            'date_range': {'start': '2024-03-24', 'end': '2024-03-24'},
            'systems': ['GPS'],
            'metrics': ['SIGMA_PHI_F'],
            'chain_level': 'FORMAL',
            'sampling_mode': 'STANDARD_30S',
            'output_path': str(tmp_path / 'out'),
            'parallelism': 1,
            'enable_intermediate_save': True,
            'enable_intermediate_preview': True,
            'enable_nav_fallback': False,
            'enable_experimental_sigma_phi_f': False,
            'enable_1s_resample': False,
            'threshold_config': [],
            'algorithm_config': {},
        }
    }
    rsp = service.validate_task(payload)
    assert rsp.success is True
    assert rsp.data['canRun'] is True
    assert rsp.data['derivedChainLevel'] == ChainLevel.FORMAL.value
    provider = rsp.data.get("providerSummary") or {}
    assert provider.get("providerChainHint") == ChainLevel.FORMAL.value
    assert provider.get("allCoordinateFormalReady") is True
    assert provider.get("allOrbitFormalReady") is True
    assert provider.get("allAntennaFormalReady") is True
