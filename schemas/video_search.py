from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class VideoSearchRequest(BaseModel):
    query: str
    token: Optional[str] = None
    conversation_id: Optional[int] = None


class VideoSearchToolArguments(BaseModel):
    keywords: str


class VideoSearchCourse(BaseModel):
    is_match: bool = False
    course_title: str = ""
    lesson_url: str = ""


class VideoSearchResponse(BaseModel):
    reply: str
    tool_name: str = "course_video_search"
    tool_arguments: VideoSearchToolArguments
    course: VideoSearchCourse


class VideoSearchMessageResponse(BaseModel):
    id: int
    role: str
    content: str = ""
    tool_name: Optional[str] = None
    tool_arguments: Optional[str] = None
    video_result: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    created_at: str


class VideoSearchConversationResponse(BaseModel):
    id: int
    title: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    created_at: str
    updated_at: str


class VideoSearchConversationDetail(VideoSearchConversationResponse):
    messages: list[VideoSearchMessageResponse]
