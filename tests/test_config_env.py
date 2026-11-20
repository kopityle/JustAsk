from app.core import config


EXPECTED_MESSAGE = (
    "[CONFIG] Файл .env не найден. Автоматически создан новый .env "
    "со сгенерированным JWT_SECRET."
)


def test_ensure_env_file_replaces_secret_from_example(tmp_path, monkeypatch, capsys):
    example = tmp_path / ".env.example"
    example.write_text(
        "JWT_SECRET=old_value\nLTI_CONSUMER_KEY=k\nFOO=bar\n", encoding="utf-8"
    )
    env_file = tmp_path / ".env"
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    monkeypatch.setattr(config, "ENV_EXAMPLE", example)

    config._ensure_env_file()

    content = env_file.read_text(encoding="utf-8")
    assert "JWT_SECRET=old_value" not in content
    assert "LTI_CONSUMER_KEY=k" in content
    assert "FOO=bar" in content
    secret = next(
        line.split("=", 1)[1]
        for line in content.splitlines()
        if line.startswith("JWT_SECRET=")
    )
    assert len(secret) >= 32
    assert EXPECTED_MESSAGE in capsys.readouterr().out

    # Повторный вызов не должен перезаписывать уже существующий файл.
    env_file.write_text("JWT_SECRET=keep_me\n", encoding="utf-8")
    config._ensure_env_file()
    assert env_file.read_text(encoding="utf-8") == "JWT_SECRET=keep_me\n"


def test_ensure_env_file_uses_fallback_template(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    monkeypatch.setattr(config, "ENV_EXAMPLE", tmp_path / "missing.env.example")

    config._ensure_env_file()

    content = env_file.read_text(encoding="utf-8")
    assert "{jwt_secret}" not in content
    assert "replace_with_moodle_consumer_key" in content
    secret = next(
        line.split("=", 1)[1]
        for line in content.splitlines()
        if line.startswith("JWT_SECRET=")
    )
    assert len(secret) >= 32
