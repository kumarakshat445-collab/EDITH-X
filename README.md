# HEXA-R

Private, offline copilot for Verilog and SystemVerilog. Inference, static checks, and simulation stay on this machine. Snapdragon Hexagon / Qualcomm AI Hub is used only when that backend actually loads.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd frontend && npm install && cd ..

# API
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000

# UI
cd frontend && npm run dev
```

Open `http://localhost:5173`.

Icarus Verilog (`iverilog`, `vvp`), Verilator, and Yosys are optional. If they are missing, the status bar says so and Settings explains how to point at each binary. Simulation is never reported as a pass when the tool did not run.

## What runs locally

- Monaco editor for Verilog / SystemVerilog
- Rule-engine static analysis (latches, delays, assignment style, widths, unused signals)
- Testbench generation for UART, counter, FIFO, ALU, shift register, mux, and a structural fallback
- Icarus Verilog compile and simulate, Yosys synthesis, Verilator lint
- Failure rules that propose a diff only when the source and the log match (UART sample skew, counter increment)
- VCD waveform viewer
- Task router that keeps static checks and simulation off the language-model path

The active engine is shown in the header. With no ONNX model and no Qualcomm QNN provider it reads **CPU fallback / HEXA-R RTL Analyst**. NPU utilization stays "Telemetry unavailable" until a provider reports it.

## Demo

Open the UART Controller project, generate the testbench, run **Verify RTL**. The loopback fails because the receiver samples one clock late. Apply the diff and verify again. The NPU page shows the backend that actually executed.

## Models

See `models/manifest.json`. Place an ONNX graph at `models/model.onnx` and a tokenizer under `models/tokenizer/` when you have a Qualcomm AI Hub export. The loader will not mark the NPU active until a session is created, and text answers still come from the rule engine until a generative runner is configured.
