import pytest

from vibelens.config import Settings
from vibelens.embeddings import HashEmbedder
from vibelens.llm import ScriptedLLM
from vibelens.service import Service
from vibelens.store import Store


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(llm="scripted", embedder="hash", data_dir=tmp_path)


@pytest.fixture
def service(settings) -> Service:
    return Service(settings, ScriptedLLM(), Store(settings.data_dir, settings.embedding_dim), HashEmbedder(384))


async def ready(service: Service, video_id: str) -> list[dict]:
    return [e async for e in service.events(video_id)]
