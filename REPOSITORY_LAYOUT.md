# Repository Layout

```
/workspace/
├── README.md
├── docs/PROPOSAL.md
├── requirements.txt
├── .cursor/environment.json
├── scripts/
│   ├── cloud-agent-install.sh
│   └── fetch-ai-hub-models.sh
├── models/snapdragon/     (fetched QNN/ONNX assets, not committed)
├── edith/
│   ├── main.py            (FastAPI app)
│   ├── catalog.py         (Qualcomm AI Hub model catalog)
│   ├── runtime.py         (QNN-first ONNX Runtime providers)
│   ├── networks.py        (ONNX control graphs)
│   ├── features.py
│   ├── usecases.py
│   └── demo.py
└── tests/test_snapdragon_usecases.py
```
