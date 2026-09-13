# Repository Layout

```
/workspace/
├── README.md
├── .gitignore
├── .cursor/environment.json
├── scripts/cloud-agent-install.sh
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── __init__.py
│       ├── main.py
│       ├── core/          (config, security)
│       ├── api/v1/        (chat, agents, sandbox, telemetry, memory)
│       ├── engine/
│       │   ├── swarm/     (graph, nodes, state)
│       │   ├── tools/     (registry)
│       │   ├── sandbox/   (manager)
│       │   └── compiler/  (pipeline)
│       └── models/        (schemas, database)
└── frontend/
    ├── package.json
    ├── next.config.mjs
    ├── tsconfig.json
    ├── tailwind.config.ts
    ├── postcss.config.mjs
    └── src/
        ├── app/           (layout, page, command-center, globals.css)
        ├── components/    (NeuralStream, ViewportEngine, MonacoWorkbench)
        └── lib/websocket.tsx
```
