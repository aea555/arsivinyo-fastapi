from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    success: Literal[False] = False
    code: str
    status_code: int
    message: str | None = None
    data: dict[str, Any] | None = None


class ApiReadyResponse(BaseModel):
    success: Literal[True] = True
    code: Literal["API_READY"] = "API_READY"
    status_code: Literal[200] = 200
    message: str
    data: None = None


class DownloadRequest(BaseModel):
    url: str | None = Field(
        default=None,
        description="Public media URL to download (YouTube, Instagram, TikTok, X, etc.).",
        examples=["https://www.youtube.com/shorts/vNxl7L3Zuck"],
    )
    cookie_profile: str | None = Field(
        default=None,
        description=(
            "Optional deterministic cookie profile for platform cookie pools. "
            "Matches filename or filename stem under cookies/<platform>/."
        ),
        examples=["primary", "twitter_main.txt"],
    )


class DownloadStartedData(BaseModel):
    task_id: str = Field(description="Async task identifier to poll via /status/{task_id}.")
    estimated_size_mb: float | None = Field(
        default=None,
        description="Pre-flight estimated size in MB if detectable.",
    )


class DownloadStartedResponse(BaseModel):
    success: Literal[True] = True
    code: Literal["DOWNLOAD_STARTED"] = "DOWNLOAD_STARTED"
    status_code: Literal[202] = 202
    message: str | None = None
    data: DownloadStartedData


class TaskStatusData(BaseModel):
    task_id: str
    status: str = Field(
        description="Celery task status (PENDING, STARTED, PROGRESS, SUCCESS, FAILURE, RETRY)."
    )
    success: bool | None = Field(
        default=None,
        description="Populated when the worker returns a wrapped result payload.",
    )
    code: str | None = Field(
        default=None,
        description="Application-level result code from the worker payload.",
    )
    status_code: int | None = None
    message: str | None = None
    data: dict[str, Any] | None = None


class TaskStatusResponse(BaseModel):
    success: bool
    code: str
    status_code: int
    message: str | None = None
    data: TaskStatusData
