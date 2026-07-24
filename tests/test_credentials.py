from genshin_autotts.credentials import CredentialStore


def test_credentials_are_encrypted_before_writing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "genshin_autotts.credentials._protect",
        lambda payload: b"protected:" + payload[::-1],
    )
    monkeypatch.setattr(
        "genshin_autotts.credentials._unprotect",
        lambda payload: payload.removeprefix(b"protected:")[::-1],
    )
    store = CredentialStore(tmp_path / "credentials.dat")

    store.save_provider(
        "volcengine",
        {"app_id": "app-id", "access_token": "secret-token"},
    )

    persisted = (tmp_path / "credentials.dat").read_bytes()
    assert b"secret-token" not in persisted
    assert store.get_provider("volcengine") == {
        "app_id": "app-id",
        "access_token": "secret-token",
    }


def test_environment_credentials_take_precedence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GENSHIN_AUTOTTS_ALIYUN_APP_KEY", "env-app-key")
    monkeypatch.setenv("GENSHIN_AUTOTTS_ALIYUN_ACCESS_TOKEN", "env-token")
    store = CredentialStore(tmp_path / "missing.dat")

    assert store.get_provider("aliyun") == {
        "app_key": "env-app-key",
        "access_token": "env-token",
    }
