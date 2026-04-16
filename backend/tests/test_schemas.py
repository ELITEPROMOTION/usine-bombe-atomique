"""Tests des schemas Pydantic (contrats API)."""
import pytest
from pydantic import ValidationError
from app.schemas import TaskCreate, UserCreate, LoginRequest


def test_task_create_accepts_valid():
    t = TaskCreate(prompt="Generer une API REST", priority="high")
    assert t.prompt == "Generer une API REST"
    assert t.priority == "high"


def test_task_create_rejects_empty_prompt():
    with pytest.raises(ValidationError):
        TaskCreate(prompt="")


def test_user_create_rejects_short_password():
    with pytest.raises(ValidationError):
        UserCreate(email="a@b.c", password="1234", full_name="Test")


def test_login_request_validates_email():
    with pytest.raises(ValidationError):
        LoginRequest(email="not-an-email", password="whatever123")
