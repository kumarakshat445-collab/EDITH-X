# HEXA-R model directory

The application never assumes a model is present.

```
models/
├── manifest.json
├── model.onnx          # optional — not shipped
└── tokenizer/          # optional — not shipped
```

`backend/app/inference.py` selects the first backend that can actually execute:

1. ONNX Runtime with `QNNExecutionProvider` (Qualcomm AI Hub / Hexagon NPU)
2. ONNX Runtime on CPU
3. HEXA-R RTL Analyst rule engine

Text generation from `model.onnx` stays disabled until a tokenizer and a generative runner are configured. A file on disk is not treated as a successful load. NPU utilization is reported only from a real provider telemetry source; otherwise the UI shows "Telemetry unavailable".
