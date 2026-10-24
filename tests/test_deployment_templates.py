from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_nginx_template_rejects_unknown_hosts_and_avoids_host_reflection():
    config = (ROOT / "deploy" / "nginx" / "devrelay.conf.example").read_text(encoding="utf-8")

    assert "listen 80 default_server;" in config
    assert "listen [::]:80 default_server;" in config
    assert "listen 443 ssl default_server;" in config
    assert "listen [::]:443 ssl default_server;" in config
    assert "return 301 https://demo.example.org$request_uri;" in config
    assert "return 301 https://$host$request_uri;" not in config
    assert "proxy_set_header X-Forwarded-Host $host;" in config


def test_deployment_environment_examples_are_trackable_and_have_no_credentials():
    backend = ROOT / "deploy" / "env" / "backend.env.example"
    frontend = ROOT / "deploy" / "env" / "frontend.env.example"
    assert backend.is_file()
    assert frontend.is_file()

    backend_values = dict(
        line.split("=", 1)
        for line in backend.read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    )
    frontend_values = dict(
        line.split("=", 1)
        for line in frontend.read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    )
    assert backend_values["NEBIUS_API_KEY"] == ""
    assert frontend_values["DEMO_AUTH_USERNAME"] == ""
    assert frontend_values["DEMO_AUTH_PASSWORD"] == ""
    assert backend_values["INFERENCE_PROVIDER"] == "mock"
    assert backend_values["NEBIUS_LIVE_INFERENCE_ENABLED"] == "false"


def test_backend_and_frontend_services_use_separate_unprivileged_identities():
    backend = (ROOT / "deploy" / "systemd" / "devrelay-backend.service").read_text(encoding="utf-8")
    frontend = (ROOT / "deploy" / "systemd" / "devrelay-frontend.service").read_text(encoding="utf-8")

    assert "User=devrelay-backend" in backend
    assert "Group=devrelay-backend" in backend
    assert "User=devrelay-frontend" in frontend
    assert "Group=devrelay-frontend" in frontend
    assert "NoNewPrivileges=true" in backend and "NoNewPrivileges=true" in frontend
