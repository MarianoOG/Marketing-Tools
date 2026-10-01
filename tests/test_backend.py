"""Backend tools, called through an in-memory MCP client. No API keys, no cost:
the image and YouTube providers are replaced with fakes."""

import asyncio
import io
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from PIL import Image

import backend.server as server
from backend.assets import jobs
from backend.config import IMG_DIR


def call(tool, progress=None, **arguments):
    async def handler(value, total, message):
        progress.append(message)

    async def run():
        async with Client(server.mcp) as client:
            result = await client.call_tool(
                tool, arguments, progress_handler=handler if progress is not None else None
            )
        content = result.structured_content
        if isinstance(content, dict) and content.keys() == {"result"}:
            return content["result"]
        return content

    return asyncio.run(run())


def png(color="red") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, "PNG")
    return buffer.getvalue()


def put(world, folder, filename):
    directory = IMG_DIR / world / folder
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_bytes(png())


@pytest.fixture
def fake_images(monkeypatch):
    monkeypatch.setattr(jobs._GENERATOR, "_openai_bytes", lambda *a, **k: png("red"))
    monkeypatch.setattr(jobs._GENERATOR, "_gemini_bytes", lambda *a, **k: png("green"))


def test_worlds_lifecycle():
    put("default", "characters", "fox_flat_2d_ab12cd34_openai.png")
    assert call("create_world", name="Night Market") == "night_market"
    assert "night_market" in call("list_worlds")
    assert call("rename_world", world="night_market", new_name="Day Market") == "day_market"
    call("delete_world", world="day_market")
    assert "day_market" not in call("list_worlds")
    with pytest.raises(ToolError, match="already exists"):
        call("create_world", name="default")


def test_list_move_copy_delete():
    put("listing", "characters", "hero_flat_2d_11111111_openai.png")
    put("listing", "locations", "market_anime_cel_22222222_gemini.png")
    call("create_world", name="elsewhere")

    page = call("list_assets", world="listing", limit=1)
    assert page["total"] == 2 and len(page["items"]) == 1
    everything = call("list_assets", world="listing", limit=None)["items"]
    hero = next(item for item in everything if item["name"] == "hero")
    assert hero["style"] == "flat_2d" and hero["provider"] == "openai" and hero["uid"] == "11111111"
    assert hero["path"] == "img/listing/characters/hero_flat_2d_11111111_openai.png"

    copied = call("copy_asset", path=hero["path"], target_world="elsewhere")
    assert copied == "img/elsewhere/characters/hero_flat_2d_11111111_openai.png"
    with pytest.raises(ToolError, match="already in elsewhere"):
        call("move_asset", path=hero["path"], target_world="elsewhere")

    call("delete_asset", path=copied)
    assert call("list_assets", world="elsewhere")["total"] == 0
    with pytest.raises(ToolError, match="not a library path"):
        call("delete_asset", path="../../etc/passwd")


def test_generation_job(fake_images):
    call("create_world", name="studio")
    job_id = call(
        "start_generation",
        asset_type="character",
        name="Lantern Fox",
        description="a fox holding a lantern",
        style="flat_2d",
        world="studio",
    )
    for _ in range(50):
        job = call("get_job", job_id=job_id)
        if job["state"] != "running":
            break
        time.sleep(0.1)

    assert job["state"] == "done", job
    assert set(job["results"]) == {"openai", "gemini"}
    names = {item["name"] for item in call("list_assets", world="studio")["items"]}
    assert names == {"lantern_fox"}
    assert call("running_jobs") == []


def test_scene_refuses_references_from_another_world(fake_images):
    put("first", "characters", "a_flat_2d_33333333_openai.png")
    call("create_world", name="second")
    job_id = call(
        "start_generation",
        asset_type="scene",
        name="mix",
        description="a scene",
        style="flat_2d",
        world="second",
        references=["img/first/characters/a_flat_2d_33333333_openai.png"],
    )
    for _ in range(50):
        job = call("get_job", job_id=job_id)
        if job["state"] != "running":
            break
        time.sleep(0.1)
    assert job["state"] == "failed" and "another world" in job["error"]


def test_search_creators_reports_progress(monkeypatch):
    now = datetime.now(timezone.utc)

    class FakeYouTube:
        def search_videos(self, keyword):
            return [{"video_id": "v1", "title": "t", "channel_id": "c1", "channel_name": "C"}]

        def get_video_statistics(self, ids):
            return {"v1": {"viewCount": 500, "publishedAt": now - timedelta(days=2),
                           "likeCount": 10, "commentCount": 1, "duration": "PT4M"}}

        def get_channel_statistics(self, ids):
            return {"c1": {"subscriberCount": 2000, "videoCount": 30, "viewCount": 9000,
                           "publishedAt": "2021-05-01T00:00:00Z", "uploadsPlaylistId": "UUc1"}}

    monkeypatch.setattr(server, "_youtube", FakeYouTube())
    progress = []
    channels = call("search_creators", progress=progress, keyword="math")

    assert list(channels) == ["c1"]
    assert channels["c1"]["subscriber_count"] == 2000
    assert isinstance(channels["c1"]["last_published"], str)  # ISO over the wire
    assert "Searching for videos..." in progress
