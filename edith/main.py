import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from edith import __version__
from edith.runtime import device_profile
from edith.usecases import (
    InferenceResult,
    active_provider,
    build_plan,
    catalog_entries,
    classify_audio,
    classify_image,
    route_text,
)

app = FastAPI(
    title="EDITH-X",
    description="On-device AI use cases for Snapdragon-powered HP PCs",
    version=__version__,
)


class AgentStatus(BaseModel):
    name: str = "EDITH-X"
    version: str = __version__
    mode: str = "snapdragon-on-device"
    status: str = "ready"
    device: dict[str, object]


class TaskRequest(BaseModel):
    goal: str = Field(..., min_length=1, description="What the agent should accomplish")
    context: str | None = Field(default=None, description="Optional background context")


class TaskResponse(BaseModel):
    goal: str
    plan: list[str]
    status: str = "accepted"
    use_case: str
    confidence: float
    ai_hub_model: str
    ai_hub_runtime: str
    execution_provider: str


class RouteRequest(BaseModel):
    text: str = Field(..., min_length=1)


class RouteResponse(BaseModel):
    text: str
    use_case: str
    confidence: float
    scores: dict[str, float]
    ai_hub_model: str
    display_name: str
    runtime: str
    precision: str
    chipset: str
    fetch_command: str
    execution_provider: str


class RgbImage(BaseModel):
    width: int = Field(..., ge=1, le=256)
    height: int = Field(..., ge=1, le=256)
    rgb: list[int] = Field(..., description="Row-major RGB bytes, length width*height*3")


class VisionResponse(BaseModel):
    label: str
    confidence: float
    scores: dict[str, float]
    features: dict[str, float]
    ai_hub_model: str
    execution_provider: str


class AudioRequest(BaseModel):
    samples: list[float] = Field(..., min_length=1, max_length=16000)
    sample_rate_hz: int = Field(default=16000, ge=8000, le=48000)


class SpeechResponse(BaseModel):
    label: str
    confidence: float
    scores: dict[str, float]
    features: dict[str, float]
    ai_hub_model: str
    sample_rate_hz: int
    execution_provider: str


class HubModelResponse(BaseModel):
    model_id: str
    display_name: str
    domain: str
    use_cases: list[str]
    runtime: str
    precision: str
    chipset: str
    entry_point: str
    fetch_command: str
    notes: str


def _route_response(text: str) -> RouteResponse:
    result, model = route_text(text)
    return RouteResponse(
        text=text,
        use_case=result.label,
        confidence=result.confidence,
        scores=result.scores,
        ai_hub_model=model.model_id,
        display_name=model.display_name,
        runtime=model.runtime,
        precision=model.precision,
        chipset=model.chipset,
        fetch_command=model.fetch_command,
        execution_provider=result.execution_provider,
    )


def _vision_response(result: InferenceResult) -> VisionResponse:
    model_id = "yolov7" if result.label == "diagram" else "mobilenet_v2"
    return VisionResponse(
        label=result.label,
        confidence=result.confidence,
        scores=result.scores,
        features=result.features,
        ai_hub_model=model_id,
        execution_provider=result.execution_provider,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "edith-x"}


@app.get("/agent/status", response_model=AgentStatus)
def agent_status() -> AgentStatus:
    return AgentStatus(device=device_profile([active_provider()]))


@app.get("/api/v1/models", response_model=list[HubModelResponse])
def list_models() -> list[HubModelResponse]:
    return [
        HubModelResponse(
            model_id=model.model_id,
            display_name=model.display_name,
            domain=model.domain,
            use_cases=list(model.use_cases),
            runtime=model.runtime,
            precision=model.precision,
            chipset=model.chipset,
            entry_point=model.entry_point,
            fetch_command=model.fetch_command,
            notes=model.notes,
        )
        for model in catalog_entries()
    ]


@app.post("/agent/task", response_model=TaskResponse)
def submit_task(request: TaskRequest) -> TaskResponse:
    text = request.goal if not request.context else f"{request.goal}\n{request.context}"
    result, model = route_text(text)
    return TaskResponse(
        goal=request.goal,
        plan=build_plan(request.goal, result.label, model, result.execution_provider),
        use_case=result.label,
        confidence=result.confidence,
        ai_hub_model=model.model_id,
        ai_hub_runtime=model.runtime,
        execution_provider=result.execution_provider,
    )


@app.post("/api/v1/usecases/route", response_model=RouteResponse)
def route_use_case(request: RouteRequest) -> RouteResponse:
    return _route_response(request.text)


@app.post("/api/v1/usecases/vision", response_model=VisionResponse)
def vision_use_case(request: RgbImage) -> VisionResponse:
    expected = request.width * request.height * 3
    if len(request.rgb) != expected:
        raise HTTPException(status_code=422, detail=f"rgb length must be {expected}")
    image = np.asarray(request.rgb, dtype=np.uint8).reshape(request.height, request.width, 3)
    return _vision_response(classify_image(image))


@app.post("/api/v1/usecases/speech", response_model=SpeechResponse)
def speech_use_case(request: AudioRequest) -> SpeechResponse:
    result = classify_audio(np.asarray(request.samples, dtype=np.float32))
    return SpeechResponse(
        label=result.label,
        confidence=result.confidence,
        scores=result.scores,
        features=result.features,
        ai_hub_model="whisper_small",
        sample_rate_hz=request.sample_rate_hz,
        execution_provider=result.execution_provider,
    )
