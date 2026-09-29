import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.analyzer import analyze_source
from backend.app.paths import TEMPLATE_ROOT


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HEXA_DATA", str(tmp_path))
    monkeypatch.setenv("HEXA_SEED", "1")
    from backend.app import main

    # Settings and project roots are read per call, but the app object is cached.
    return TestClient(main.app)


def test_analyzer_finds_latch_delay_and_blocking():
    src = """
module m(
    input logic clk,
    input logic sel,
    input logic [7:0] a,
    input logic [3:0] b,
    output logic [7:0] y,
    output logic [7:0] q
);
    logic [7:0] unused_bus;
    always_comb begin
        if (sel) y = a;
    end
    always_ff @(posedge clk) begin
        q = a;
    end
    assign y = #5 a;
endmodule
"""
    diags = analyze_source("rtl/m.sv", src)
    rules = {d.rule for d in diags}
    assert "latch" in rules
    assert "blocking-seq" in rules
    assert "delay" in rules
    assert "unused" in rules
    for diag in diags:
        assert diag.why and diag.fix and diag.line


def test_path_escape_rejected(client):
    response = client.get("/api/projects/uart/file", params={"path": "../settings.json"})
    assert response.status_code == 400


def test_uart_verify_fails_then_passes(client):
    listed = client.get("/api/projects").json()["projects"]
    assert any(item["id"] == "uart" for item in listed)
    tb = client.post("/api/projects/uart/testbench/write", json={"path": "rtl/uart_rx.sv"})
    assert tb.status_code == 200, tb.text
    assert tb.json()["written"] is True
    first = client.post("/api/projects/uart/verify")
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["ok"] is False
    assert body["report"]["simulation"] == "FAIL"
    assert body["proposal"]["rule"] == "uart-sample-skew"
    assert body["proposal"]["can_apply"] is True
    assert "one clock" in body["proposal"]["root_cause"]
    applied = client.post(
        "/api/projects/uart/apply",
        json={"path": body["proposal"]["path"], "content": body["proposal"]["updated"]},
    )
    assert applied.status_code == 200, applied.text
    second = client.post("/api/projects/uart/verify")
    assert second.status_code == 200, second.text
    assert second.json()["ok"] is True
    assert second.json()["report"]["simulation"] == "PASS"
    assert second.json()["report"]["passed"] == 5


def test_counter_defect_and_fifo_generation(client):
    created = client.post("/api/projects", json={"name": "Count Demo", "template": "counter"})
    assert created.status_code == 200, created.text
    project = created.json()["id"]
    client.post(f"/api/projects/{project}/testbench/write", json={"path": "rtl/counter.sv"})
    failed = client.post(f"/api/projects/{project}/verify")
    assert failed.json()["proposal"]["rule"] == "counter-increment"
    assert failed.json()["ok"] is False
    client.post(
        f"/api/projects/{project}/apply",
        json={"path": failed.json()["proposal"]["path"], "content": failed.json()["proposal"]["updated"]},
    )
    passed = client.post(f"/api/projects/{project}/verify")
    assert passed.json()["ok"] is True

    fifo = client.post(f"/api/projects/{project}/generate/rtl", json={"prompt": "Create a parameterized 32-bit synchronous FIFO with full and empty flags."})
    assert fifo.status_code == 200
    payload = fifo.json()
    assert payload["ok"] is True
    assert payload["backend"] == "rule-engine"
    content = payload["files"][0]["content"]
    assert "full" in content and "empty" in content
    client.put(f"/api/projects/{project}/file", json={"path": payload["files"][0]["path"], "content": content})
    # Isolate the FIFO from the counter testbench by using a fresh project.
    fresh = client.post("/api/projects", json={"name": "FIFO", "template": "empty"})
    fid = fresh.json()["id"]
    client.put(f"/api/projects/{fid}/file", json={"path": "rtl/sync_fifo.sv", "content": content})
    written = client.post(f"/api/projects/{fid}/testbench/write", json={"path": "rtl/sync_fifo.sv"})
    assert written.json().get("written") is True, written.text
    result = client.post(f"/api/projects/{fid}/verify")
    assert result.status_code == 200, result.text
    assert result.json()["report"]["simulation"] == "PASS", result.json()["steps"]


def test_engine_does_not_claim_npu(client):
    status = client.get("/api/engine").json()
    assert status["npu_active"] is False
    assert status["backend_id"] == "rule-engine"
    assert status["telemetry"]["npu_utilization_pct"] is None
    assert status["telemetry"]["note"] == "Telemetry unavailable"


def test_cloud_flag_has_no_provider(client):
    current = client.get("/api/settings").json()
    current["allow_cloud"] = True
    saved = client.put("/api/settings", json=current)
    assert saved.status_code == 200
    engine = client.get("/api/engine").json()
    assert engine["cloud_allowed"] is True
    assert engine["cloud_configured"] is False
    assert engine["network"] == "Offline"


def test_open_prompt_is_refused(client):
    response = client.post("/api/projects/uart/generate/rtl", json={"prompt": "Design a cache-coherent interconnect."})
    assert response.status_code == 200
    assert response.json()["ok"] is False


def test_command_injection_rejected(client):
    response = client.post("/api/projects/uart/command", json={"command": "iverilog -g2012 rtl/uart_tx.sv; rm -rf /"})
    assert response.status_code == 400


def test_templates_exist():
    assert (TEMPLATE_ROOT / "uart" / "rtl" / "uart_rx.sv").is_file()
    assert (TEMPLATE_ROOT / "uart_good" / "rtl" / "uart_rx.sv").is_file()
    good = (TEMPLATE_ROOT / "uart_good" / "rtl" / "uart_rx.sv").read_text()
    assert "CLKS_PER_BIT - 1" in good
    assert "clk_count == CLKS_PER_BIT)" not in good
