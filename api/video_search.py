from __future__ import annotations

import json
import re
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from api.dependencies import deduct_token_quota, verify_service_access
from config_loader import get
from database import get_db
from models import AdminUser, TokenRecord, VideoSearchConversation, VideoSearchMessage
from schemas.video_search import (
    VideoSearchConversationDetail,
    VideoSearchConversationResponse,
    VideoSearchMessageResponse,
    VideoSearchRequest,
    VideoSearchResponse,
    VideoSearchToolArguments,
    VideoSearchCourse,
)
from services import ai_service
from services.video_search_service import VideoSearchService
from utils.auth import check_permission, get_optional_admin
from utils.entitlements import entitlement_rank, get_token_entitlement_level
from utils.timezone import local_now

router = APIRouter(prefix="/api/video-search", tags=["video-search"])

VIDEO_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "course_video_search",
        "description": "根据用户学习需求搜索匹配的视频课程，返回课程标题和播放链接。",
        "parameters": {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "string",
                    "description": "用于视频课程检索的关键词，例如：肿瘤微环境治疗",
                }
            },
            "required": ["keywords"],
            "additionalProperties": False,
        },
    },
}

KEYWORD_NOISE_WORDS = (
    "帮我",
    "找一个",
    "找一下",
    "搜索",
    "推荐",
    "视频",
    "课程",
    "课时",
    "教程",
    "临床教学",
    "教学",
    "临床",
    "讲解",
    "介绍",
    "学习",
    "相关",
    "关于",
    "管理",
)


def _extract_json_object(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, re.S)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


def _fallback_keywords(query: str) -> str:
    return _clean_medical_keywords(query) or query.strip()


def _clean_medical_keywords(value: str) -> str:
    cleaned = value.strip()
    for word in KEYWORD_NOISE_WORDS:
        cleaned = cleaned.replace(word, " ")
    cleaned = re.sub(r"[，。！？、,.!?]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Prefer the disease/topic phrase before generic intent words.
    for splitter in ("的", "方面", "相关"):
        if splitter in cleaned:
            left = cleaned.split(splitter, 1)[0].strip()
            if len(left) >= 2:
                cleaned = left
                break

    words = [word.strip() for word in cleaned.split() if word.strip()]
    if len(words) > 3:
        return " ".join(words[:3])
    return cleaned


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _dt(value) -> str:
    return value.isoformat() if value else ""


def _serialize_message(message: VideoSearchMessage) -> VideoSearchMessageResponse:
    return VideoSearchMessageResponse(
        id=message.id,
        role=message.role,
        content=message.content or "",
        tool_name=message.tool_name,
        tool_arguments=message.tool_arguments,
        video_result=message.video_result,
        prompt_tokens=message.prompt_tokens or 0,
        completion_tokens=message.completion_tokens or 0,
        total_tokens=message.total_tokens or 0,
        created_at=_dt(message.created_at),
    )


def _serialize_conversation(conversation: VideoSearchConversation) -> VideoSearchConversationResponse:
    return VideoSearchConversationResponse(
        id=conversation.id,
        title=conversation.title or "未命名对话",
        prompt_tokens=conversation.prompt_tokens or 0,
        completion_tokens=conversation.completion_tokens or 0,
        total_tokens=conversation.total_tokens or 0,
        created_at=_dt(conversation.created_at),
        updated_at=_dt(conversation.updated_at),
    )


def _conversation_query(
    db: Session,
    current_user: Optional[AdminUser],
    token_record: Optional[TokenRecord],
):
    query = db.query(VideoSearchConversation)
    if current_user:
        return query.filter(VideoSearchConversation.admin_id == current_user.id)
    if token_record:
        return query.filter(VideoSearchConversation.token_id == token_record.id)
    return query.filter(VideoSearchConversation.id == -1)


def _get_or_create_conversation(
    db: Session,
    request: VideoSearchRequest,
    current_user: Optional[AdminUser],
    token_record: Optional[TokenRecord],
) -> VideoSearchConversation:
    if request.conversation_id:
        conversation = (
            _conversation_query(db, current_user, token_record)
            .filter(VideoSearchConversation.id == request.conversation_id)
            .first()
        )
        if conversation:
            return conversation

    title = request.query.strip().replace("\n", " ")[:80] or "视频搜索对话"
    conversation = VideoSearchConversation(
        token_id=token_record.id if token_record else None,
        admin_id=current_user.id if current_user else None,
        title=title,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def _check_video_search_entitlement(db: Session, token_record: Optional[TokenRecord]):
    if not token_record or not token_record.external_user_id:
        return
    entitlement_level = get_token_entitlement_level(db, token_record)
    if entitlement_rank(entitlement_level) < entitlement_rank("pro"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="调用视频需要高级会员")


async def _build_keywords(query: str) -> str:
    prompt = f"""你是一个医学视频课程搜索关键词生成器。
请根据用户需求，只提取最适合用于医学课程视频检索的核心医学主题。

只输出 JSON，不要 Markdown，不要解释。格式：
{{"keywords":"关键词"}}

要求：
- keywords 只保留疾病、病理机制、治疗方向、检查方法、手术方式、药物类别等医学核心词
- 不要输出“视频”“课程”“临床教学”“教学”“管理”“讲解”“介绍”“相关”“关于”等用户意图词
- 不要为了补全而加入泛词
- 如果用户说“找一个关于糖尿病并发症管理的临床教学视频”，keywords 应输出“糖尿病并发症”
- keywords 通常控制在 1 个医学短语，最多 2 个医学短语
- 如果用户需求是英文技术词，可以保留英文

用户需求：
{query}"""
    result = await ai_service.chat_completion([{"role": "user", "content": prompt}], temperature=0.2)
    payload = _extract_json_object(result.get("content", ""))
    keywords = str(payload.get("keywords") or "").strip()
    return _clean_medical_keywords(keywords) or _fallback_keywords(query)


def _get_video_search_service() -> VideoSearchService:
    return VideoSearchService(
        base_url=get("video_search.base_url", "https://api.shiyanjia.com"),
        course_key=get("video_search.course_key", ""),
        timeout=float(get("video_search.timeout", 12)),
    )


@router.post("/course", response_model=VideoSearchResponse)
async def search_course_video(
    request: VideoSearchRequest,
    db: Session = Depends(get_db),
    current_user: Optional[AdminUser] = Depends(get_optional_admin),
):
    if not current_user:
        token_record = await verify_service_access(db, request.token, "ai")
        _check_video_search_entitlement(db, token_record)
    else:
        check_permission(current_user, "ai")

    keywords = await _build_keywords(request.query)
    course_data = await _get_video_search_service().search_course(keywords)
    course = VideoSearchCourse(**course_data)

    if course.is_match:
        reply = f"已根据“{keywords}”找到相关视频：{course.course_title}"
    else:
        reply = f"已根据“{keywords}”搜索，但暂未匹配到合适的视频课程。"

    return VideoSearchResponse(
        reply=reply,
        tool_arguments=VideoSearchToolArguments(keywords=keywords),
        course=course,
    )


@router.get("/conversations", response_model=list[VideoSearchConversationResponse])
async def list_video_search_conversations(
    token: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Optional[AdminUser] = Depends(get_optional_admin),
):
    token_record = None
    if not current_user:
        token_record = await verify_service_access(db, token, "ai")
        _check_video_search_entitlement(db, token_record)
    else:
        check_permission(current_user, "ai")

    rows = (
        _conversation_query(db, current_user, token_record)
        .order_by(VideoSearchConversation.updated_at.desc(), VideoSearchConversation.id.desc())
        .limit(50)
        .all()
    )
    return [_serialize_conversation(row) for row in rows]


@router.get("/conversations/{conversation_id}", response_model=VideoSearchConversationDetail)
async def get_video_search_conversation(
    conversation_id: int,
    token: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Optional[AdminUser] = Depends(get_optional_admin),
):
    token_record = None
    if not current_user:
        token_record = await verify_service_access(db, token, "ai")
        _check_video_search_entitlement(db, token_record)
    else:
        check_permission(current_user, "ai")

    conversation = (
        _conversation_query(db, current_user, token_record)
        .filter(VideoSearchConversation.id == conversation_id)
        .first()
    )
    if not conversation:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="对话不存在")

    base = _serialize_conversation(conversation)
    return VideoSearchConversationDetail(
        **base.dict(),
        messages=[_serialize_message(message) for message in conversation.messages],
    )


@router.post("/chat/stream")
async def stream_video_search_chat(
    request: VideoSearchRequest,
    db: Session = Depends(get_db),
    current_user: Optional[AdminUser] = Depends(get_optional_admin),
):
    token_record = None
    if not current_user:
        token_record = await verify_service_access(db, request.token, "ai")
        _check_video_search_entitlement(db, token_record)
    else:
        check_permission(current_user, "ai")

    conversation = _get_or_create_conversation(db, request, current_user, token_record)
    prior_messages = list(conversation.messages)
    db.add(VideoSearchMessage(
        conversation_id=conversation.id,
        role="user",
        content=request.query,
    ))
    db.commit()

    async def generate():
        assistant_text = ""
        tool_payload = None
        video_payload = None
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        try:
            yield _sse("conversation", {
                "conversation": _serialize_conversation(conversation).dict(),
            })

            messages = [
                {
                    "role": "system",
                    "content": (
                        "你是一个视频学习助手。用户需要找视频、课程、课时、教程、演示时，"
                        "必须调用 course_video_search 工具。"
                        "调用工具时，keywords 只能填写医学核心主题，不要包含视频、课程、临床教学、教学、管理、讲解等意图词。"
                        "例如用户说“找一个关于糖尿病并发症管理的临床教学视频”，keywords 必须是“糖尿病并发症”。"
                        "如果用户需求不清楚，先用简短中文追问。"
                        "普通回复使用 Markdown。"
                    ),
                },
            ]
            for message in prior_messages[-12:]:
                if message.role in ("user", "assistant") and message.content:
                    messages.append({"role": message.role, "content": message.content})
            messages.append({"role": "user", "content": request.query})

            tool_calls = []
            async for event in ai_service.chat_completion_stream(
                messages,
                temperature=0.2,
                tools=[VIDEO_SEARCH_TOOL],
                tool_choice="auto",
            ):
                if event["type"] == "content":
                    assistant_text += event["content"]
                    yield _sse("message", {"delta": event["content"]})
                elif event["type"] == "tool_calls":
                    tool_calls = event["tool_calls"]
                elif event["type"] == "usage":
                    usage.update(event["usage"])

            if not tool_calls:
                assistant_message = VideoSearchMessage(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=assistant_text,
                    prompt_tokens=usage["prompt_tokens"],
                    completion_tokens=usage["completion_tokens"],
                    total_tokens=usage["total_tokens"],
                )
                db.add(assistant_message)
                conversation.prompt_tokens = (conversation.prompt_tokens or 0) + usage["prompt_tokens"]
                conversation.completion_tokens = (conversation.completion_tokens or 0) + usage["completion_tokens"]
                conversation.total_tokens = (conversation.total_tokens or 0) + usage["total_tokens"]
                conversation.updated_at = local_now()
                db.commit()
                db.refresh(assistant_message)
                if token_record and usage["total_tokens"] > 0:
                    deduct_token_quota(db, token_record.id, usage["total_tokens"])
                yield _sse("done", {
                    "ok": True,
                    "message": _serialize_message(assistant_message).dict(),
                })
                return

            for tool_call in tool_calls:
                function = tool_call.get("function") or {}
                tool_name = function.get("name") or ""
                if tool_name != "course_video_search":
                    continue

                try:
                    args = json.loads(function.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}

                keywords = _clean_medical_keywords(str(args.get("keywords") or "")) or _fallback_keywords(request.query)
                tool_payload = {"name": tool_name, "arguments": {"keywords": keywords}}
                yield _sse("tool_call", tool_payload)

                course_data = await _get_video_search_service().search_course(keywords)
                course = VideoSearchCourse(**course_data)
                video_payload = {
                    "keywords": keywords,
                    "course": course.model_dump() if hasattr(course, "model_dump") else course.dict(),
                }
                yield _sse(
                    "video",
                    video_payload,
                )

                if course.is_match:
                    final_text = f"\n\n已根据 **{keywords}** 找到相关视频：**{course.course_title}**。"
                else:
                    final_text = f"\n\n已根据 **{keywords}** 搜索，但暂未匹配到合适的视频课程。"
                assistant_text += final_text
                yield _sse("message", {"delta": final_text})

            assistant_message = VideoSearchMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=assistant_text,
                tool_name=tool_payload["name"] if tool_payload else None,
                tool_arguments=json.dumps(tool_payload["arguments"], ensure_ascii=False) if tool_payload else None,
                video_result=json.dumps(video_payload, ensure_ascii=False) if video_payload else None,
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
                total_tokens=usage["total_tokens"],
            )
            db.add(assistant_message)
            conversation.prompt_tokens = (conversation.prompt_tokens or 0) + usage["prompt_tokens"]
            conversation.completion_tokens = (conversation.completion_tokens or 0) + usage["completion_tokens"]
            conversation.total_tokens = (conversation.total_tokens or 0) + usage["total_tokens"]
            conversation.updated_at = local_now()
            db.commit()
            db.refresh(assistant_message)
            if token_record and usage["total_tokens"] > 0:
                deduct_token_quota(db, token_record.id, usage["total_tokens"])

            yield _sse("done", {
                "ok": True,
                "assistant_text": assistant_text,
                "message": _serialize_message(assistant_message).dict(),
            })
        except Exception as exc:
            error_message = str(exc)
            assistant_message = VideoSearchMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=assistant_text or error_message,
                tool_name=tool_payload["name"] if tool_payload else None,
                tool_arguments=json.dumps(tool_payload["arguments"], ensure_ascii=False) if tool_payload else None,
                video_result=json.dumps(video_payload, ensure_ascii=False) if video_payload else None,
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
                total_tokens=usage["total_tokens"],
            )
            db.add(assistant_message)
            conversation.prompt_tokens = (conversation.prompt_tokens or 0) + usage["prompt_tokens"]
            conversation.completion_tokens = (conversation.completion_tokens or 0) + usage["completion_tokens"]
            conversation.total_tokens = (conversation.total_tokens or 0) + usage["total_tokens"]
            conversation.updated_at = local_now()
            db.commit()
            db.refresh(assistant_message)
            if token_record and usage["total_tokens"] > 0:
                deduct_token_quota(db, token_record.id, usage["total_tokens"])
            yield _sse("error", {"message": error_message})
            yield _sse("done", {
                "ok": False,
                "message": _serialize_message(assistant_message).dict(),
            })

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
