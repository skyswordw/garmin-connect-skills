import json

from garmin_connect_skills.cli import main


def test_demo_and_doctor_do_not_need_account(tmp_path, capsys):
    root, output = tmp_path.resolve() / "state", tmp_path.resolve() / "demo"
    assert main(["--home", str(root), "--json", "doctor"]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["profiles"] == [] and info["garminconnect"] == "0.3.17" and not root.exists()
    assert main(["--home", str(root), "--json", "demo", "--output", str(output)]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["fictional"] is True
    report = output / info["report"]
    assert report.is_file() and "完全虚构" in report.read_text()
    manifest = json.loads((report.parent / "manifest.json").read_text())
    assert all(s["snapshot"]["provider"] == "fictional" for s in manifest["inputs"])
    assert not root.exists()


def test_noninteractive_login_never_reads_credentials(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr(
        "getpass.getpass", lambda *args: (_ for _ in ()).throw(AssertionError("no prompt"))
    )
    assert main(["--home", str(tmp_path.resolve()), "--json", "auth", "login"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "AUTH_REQUIRED"


def test_invalid_argv_does_not_echo_accidental_password(tmp_path, capsys):
    assert (
        main(["--home", str(tmp_path.resolve()), "auth", "login", "--password", "fictionalSECRET"])
        == 1
    )
    assert "fictionalSECRET" not in capsys.readouterr().err


def test_missing_offline_input_is_not_zero(store, profile, capsys):
    assert main(["--home", str(store.root), "--json", "fetch", "runs", "--offline"]) == 2
    info = json.loads(capsys.readouterr().out)
    assert info["items"][0]["snapshot"]["status"] == "error"
    assert "activities" not in info["items"][0]["snapshot"]["data"]
