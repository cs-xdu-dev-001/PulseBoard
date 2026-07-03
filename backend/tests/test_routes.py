from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import DataSource, Gpu, GpuMetric, Machine, MachineMetric, VpsMetric, VpsNode


def make_client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    return TestClient(app), TestingSession


def seed_dashboard(session_factory):
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        source = DataSource(
            name="lab-gpu",
            url="http://example/api/latest",
            status="ok",
            consecutive_failures=0,
            last_success_at=now,
        )
        machine = Machine(name="a100", status="connected", last_seen_at=now)
        db.add_all([source, machine])
        db.flush()
        gpu = Gpu(
            machine_id=machine.id,
            gpu_index=0,
            name="NVIDIA A100 80GB PCIe",
            memory_total_mb=81920,
            current_status="available",
            last_seen_at=now,
        )
        db.add(gpu)
        db.flush()
        db.add(
            MachineMetric(
                machine_id=machine.id,
                collected_at=now,
                status="connected",
                cpu_percent=12.4,
                memory_percent=10.7,
                memory_total_mb=1000,
                memory_used_mb=107,
                disks={"/data": {"percentage": 84.6}},
            )
        )
        db.add(
            MachineMetric(
                machine_id=machine.id,
                collected_at=now,
                status="connected",
                cpu_percent=99.0,
                memory_percent=99.0,
                memory_total_mb=1000,
                memory_used_mb=990,
                disks={"/data": {"percentage": 99.0}},
            )
        )
        db.add(
            GpuMetric(
                gpu_id=gpu.id,
                collected_at=now - timedelta(minutes=5),
                utilization=10,
                memory_total_mb=81920,
                memory_used_mb=1000,
                status="available",
            )
        )
        db.add(
            GpuMetric(
                gpu_id=gpu.id,
                collected_at=now,
                utilization=6,
                memory_total_mb=81920,
                memory_used_mb=901,
                status="available",
            )
        )
        db.add(
            GpuMetric(
                gpu_id=gpu.id,
                collected_at=now,
                utilization=5,
                memory_total_mb=81920,
                memory_used_mb=900,
                status="available",
            )
        )
        db.add(
            GpuMetric(
                gpu_id=gpu.id,
                collected_at=now + timedelta(hours=8),
                utilization=99,
                memory_total_mb=81920,
                memory_used_mb=80000,
                status="saturated",
            )
        )
        vps = VpsNode(
            name="vpn-gateway",
            url="http://vpn.example:9100",
            status="online",
            last_seen_at=now,
            traffic_baseline_bytes=1000,
        )
        db.add(vps)
        db.flush()
        db.add(
            VpsMetric(
                node_id=vps.id,
                collected_at=now,
                status="online",
                cpu_percent=22.5,
                memory_percent=61.0,
                memory_total_bytes=1000,
                memory_available_bytes=390,
                disks={"/": {"percentage": 72.0}},
                network_interfaces={"eth0": {"rx_bytes_per_sec": 1024, "tx_bytes_per_sec": 2048}},
                network_rx_bytes_per_sec=1024,
                network_tx_bytes_per_sec=2048,
                load1=0.42,
                load5=0.55,
                load15=0.61,
                uptime_seconds=3600,
                traffic_used_gb=71.23,
                traffic_total_gb=250,
                traffic_used_percent=28.492,
            )
        )
        db.add(
            VpsMetric(
                node_id=vps.id,
                collected_at=now + timedelta(hours=8),
                status="online",
                cpu_percent=99.0,
                memory_percent=99.0,
                memory_total_bytes=1000,
                memory_available_bytes=10,
                disks={"/": {"percentage": 99.0}},
                network_interfaces={},
            )
        )
        db.commit()


def test_dashboard_current_returns_source_machine_and_gpu_cards():
    client, session_factory = make_client()
    seed_dashboard(session_factory)

    response = client.get("/api/dashboard/current")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"]["status"] == "ok"
    assert payload["summary"]["available_gpus"] == 1
    assert payload["machines"][0]["name"] == "a100"
    assert payload["machines"][0]["cpu_percent"] == 99.0
    assert payload["gpus"][0]["machine_name"] == "a100"
    assert payload["gpus"][0]["status"] == "available"
    assert payload["summary"]["vps_total"] == 1
    assert payload["summary"]["vps_abnormal"] == 0
    assert payload["vps_nodes"][0]["name"] == "vpn-gateway"
    assert payload["vps_nodes"][0]["traffic_quota"]["used_gb"] == 71.23


def test_gpu_history_returns_points_for_requested_range():
    client, session_factory = make_client()
    seed_dashboard(session_factory)

    response = client.get("/api/history/gpus?range=1h")

    assert response.status_code == 200
    payload = response.json()
    assert payload["range"] == "1h"
    assert payload["series"][0]["gpu_index"] == 0
    assert len(payload["series"][0]["points"]) == 2
    assert payload["series"][0]["points"][0]["utilization"] == 10
    assert payload["series"][0]["points"][1]["utilization"] == 5
    assert all(point["utilization"] != 99 for point in payload["series"][0]["points"])


def test_machine_history_deduplicates_same_timestamp_points():
    client, session_factory = make_client()
    seed_dashboard(session_factory)

    response = client.get("/api/history/machines?range=1h")

    assert response.status_code == 200
    payload = response.json()
    assert payload["series"][0]["name"] == "a100"
    assert len(payload["series"][0]["points"]) == 1
    assert payload["series"][0]["points"][0]["cpu_percent"] == 99.0


def test_vps_history_returns_points_for_requested_range():
    client, session_factory = make_client()
    seed_dashboard(session_factory)

    response = client.get("/api/history/vps?range=1h")

    assert response.status_code == 200
    payload = response.json()
    assert payload["range"] == "1h"
    assert payload["series"][0]["name"] == "vpn-gateway"
    assert payload["series"][0]["points"][0]["cpu_percent"] == 22.5
    assert payload["series"][0]["points"][0]["traffic_used_percent"] == 28.492
    assert all(point["cpu_percent"] != 99 for point in payload["series"][0]["points"])
