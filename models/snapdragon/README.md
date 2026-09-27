# Snapdragon model assets

Compiled Qualcomm AI Hub outputs belong in this directory and are not committed.
On a development PC with x64 Python:

```bash
pip install qai_hub_models_cli
qai-hub-models fetch whisper_small --runtime qnn --precision w8a8 --chipset qualcomm-snapdragon-x-elite
qai-hub-models fetch mobilenet_v2 --runtime qnn --precision w8a8 --chipset qualcomm-snapdragon-x-elite
qai-hub-models fetch yolov7 --runtime qnn --precision w8a8 --chipset qualcomm-snapdragon-x-elite
```

Llama-3.2-3B chat export uses AI Hub Workbench and a Qualcomm account:

```bash
pip install "qai_hub_models[llama-v3-2-3b-chat-quantized]"
python -m qai_hub_models.models.llama_v3_2_3b_chat_quantized.export \
  --device "Snapdragon X Elite CRD" --skip-inferencing --skip-profiling
```

Copy the resulting context binaries or ONNX graphs here, then run EDITH-X on the
Snapdragon HP PC with `QNN_BACKEND_PATH` pointing at `QnnHtp.dll`. X Elite
binaries also run on Snapdragon X and X Plus PCs.
