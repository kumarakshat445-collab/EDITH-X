# Repository layout

```
/workspace/
├── inkloom/
│   ├── main.py        HTTP API and UI
│   ├── engine.py      Local explainable review rules
│   ├── workflow.py    Roles, versions, approvals, insights
│   ├── seed.py        Lumen & Grove demo workspace
│   ├── db.py          SQLite schema
│   └── static/        Queue, review studio, library, insights, access
├── tests/test_inkloom.py
├── edith/main.py      Compatibility entrypoint that serves Inkloom
├── requirements.txt
└── scripts/cloud-agent-install.sh
```

Runtime data (the workspace database and uploads) is created under `data/` and is not committed.
