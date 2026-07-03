from pathlib import Path

from app.settings_config import load_app_settings, save_app_settings


def test_load_app_settings_masks_secret_values(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "PULSEBOARD_SOURCE_URL=http://gpu.local/api/latest",
                "PULSEBOARD_NODE_EXPORTERS=vpn=http://1.2.3.4:9100",
                "PULSEBOARD_LLM_DEEPSEEK_API_KEY=secret-key",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = load_app_settings(env_path)

    assert result["values"]["PULSEBOARD_SOURCE_URL"] == "http://gpu.local/api/latest"
    assert result["values"]["PULSEBOARD_NODE_EXPORTERS"] == "vpn=http://1.2.3.4:9100"
    assert result["secrets"]["PULSEBOARD_LLM_DEEPSEEK_API_KEY"]["configured"] is True
    assert "secret-key" not in str(result)


def test_save_app_settings_updates_allowed_keys_without_blank_secret_overwrite(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "PULSEBOARD_SOURCE_URL=http://old\nPULSEBOARD_LLM_DEEPSEEK_API_KEY=secret\n",
        encoding="utf-8",
    )

    save_app_settings(
        {
            "PULSEBOARD_SOURCE_URL": "http://new",
            "PULSEBOARD_LLM_DEEPSEEK_API_KEY": "",
            "UNSUPPORTED_KEY": "ignored",
        },
        env_path,
    )

    text = env_path.read_text(encoding="utf-8")
    assert "PULSEBOARD_SOURCE_URL=http://new" in text
    assert "PULSEBOARD_LLM_DEEPSEEK_API_KEY=secret" in text
    assert "UNSUPPORTED_KEY" not in text
