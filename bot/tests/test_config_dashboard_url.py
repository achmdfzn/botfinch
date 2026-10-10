"""Test validasi DASHBOARD_URL wajib https:// (Subagent D2, tugas 2a).

Aturan: dashboard_url diawali "http://" ditolak saat startup, kecuali host
localhost/127.0.0.1/[::1] (pengembangan lokal). Alasan: DASHBOARD_SECRET
dikirim via header Authorization di tiap request push/pull.
"""
import pytest

from src.config import Settings


@pytest.fixture(autouse=True)
def _token_valid(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "token-palsu-buat-tes")


def _masalah_url(monkeypatch, url: str) -> list:
    if url:
        monkeypatch.setenv("DASHBOARD_URL", url)
    else:
        monkeypatch.delenv("DASHBOARD_URL", raising=False)
    return [m for m in Settings().validate() if "DASHBOARD_URL" in m]


def test_http_ke_host_publik_ditolak(monkeypatch):
    assert _masalah_url(monkeypatch, "http://dashboard.contoh.com") != []


def test_http_ke_ip_publik_ditolak(monkeypatch):
    assert _masalah_url(monkeypatch, "http://203.0.113.10:3000") != []


def test_https_ke_host_publik_lolos(monkeypatch):
    assert _masalah_url(monkeypatch, "https://dashboard.contoh.com") == []


def test_http_localhost_lolos(monkeypatch):
    assert _masalah_url(monkeypatch, "http://localhost:3000") == []


def test_http_127_0_0_1_lolos(monkeypatch):
    assert _masalah_url(monkeypatch, "http://127.0.0.1:3000") == []


def test_http_ipv6_loopback_lolos(monkeypatch):
    assert _masalah_url(monkeypatch, "http://[::1]:3000") == []


def test_kosong_lolos_sinkronisasi_mati(monkeypatch):
    assert _masalah_url(monkeypatch, "") == []
