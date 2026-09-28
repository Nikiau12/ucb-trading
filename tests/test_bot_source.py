import ast
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def test_coin_info_calls_use_initialized_service_instance():
    tree = ast.parse((ROOT_DIR / "bot_mexc.py").read_text())
    loaded_names = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }

    assert "coin_info_service" not in loaded_names
    assert "coin_info_svc" in loaded_names


def test_persistent_menu_button_opens_the_mini_app():
    source = (ROOT_DIR / "bot_mexc.py").read_text()
    assert "MenuButtonWebApp" in source
    assert "set_chat_menu_button" in source
