import pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def root():
    return ROOT


@pytest.fixture
def fixtures():
    return FIXTURES
