"""Доставка кодов входа в разработке: лог сервера и файл var/dev-login-codes.txt."""

import pytest

from app.core.config import Settings
from app.services.code_sender import DevLogSender, SenderNotConfigured, default_sender


def test_dev_sender_appends_fresh_code_last(tmp_path):
    path = tmp_path / "codes.txt"
    sender = default_sender(Settings(env="development", dev_codes_file=path))
    sender.send("+79000000003", "111111")
    sender.send("+79000000003", "222222")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [line.split()[-1] for line in lines] == ["111111", "222222"]


def test_test_env_never_writes_codes_to_disk(tmp_path):
    sender = default_sender(Settings(env="test", dev_codes_file=tmp_path / "codes.txt"))
    assert isinstance(sender, DevLogSender) and sender.codes_file is None


def test_production_without_provider_refuses_to_start():
    with pytest.raises(SenderNotConfigured):
        default_sender(Settings(env="production"))
