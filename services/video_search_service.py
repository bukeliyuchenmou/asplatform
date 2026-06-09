from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException


class VideoSearchService:
    def __init__(self, base_url: str, course_key: str, timeout: float = 12.0):
        self.base_url = base_url.rstrip("/")
        self.course_key = course_key
        self.timeout = timeout

    async def search_course(self, keywords: str) -> dict[str, Any]:
        print(keywords)
        if not self.course_key:
            raise HTTPException(
                status_code=500,
                detail="视频搜索接口未配置 course_key",
            )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/course/getSeoPromotionCourseLink",
                    headers={
                        "Content-Type": "application/json",
                        "X-Course-Key": self.course_key,
                    },
                    json={"keywords": keywords},
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=exc.response.status_code,
                detail="视频搜索接口请求失败",
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail="无法连接视频搜索接口",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=502,
                detail="视频搜索接口返回了无效 JSON",
            ) from exc

        if payload.get("code") != 200:
            raise HTTPException(
                status_code=502,
                detail=payload.get("message") or "视频搜索接口返回失败",
            )

        data = payload.get("data") or {}
        return {
            "is_match": bool(data.get("is_match")),
            "course_title": data.get("course_title") or "",
            "lesson_url": data.get("lesson_url") or "",
        }
