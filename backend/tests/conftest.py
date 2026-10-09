import pytest

from backend.content import load_content


@pytest.fixture(scope="session")
def content():
    return load_content()


@pytest.fixture(scope="session")
def rules(content):
    return content.rules
