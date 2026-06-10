"""Installer helper: write .env and config.json with proper UTF-8 encoding.

Called by Inno Setup during installation:
    python write_config.py <env_path> <config_path> <api_key>
"""
import sys
import json
import os

def main():
    if len(sys.argv) < 4:
        print("Usage: write_config.py <env_path> <config_path> <api_key>")
        sys.exit(1)

    env_path = sys.argv[1]
    config_path = sys.argv[2]
    api_key = sys.argv[3]

    # Write .env (UTF-8, no BOM)
    env_dir = os.path.dirname(env_path)
    if env_dir:
        os.makedirs(env_dir, exist_ok=True)
    with open(env_path, 'w', encoding='utf-8') as f:
        f.write(f"DEEPSEEK_API_KEY={api_key}\n")
        f.write(f"DEEPSEEK_API_BASE=https://api.deepseek.com/v1\n")

    # Write config.json (UTF-8)
    config_dir = os.path.dirname(config_path)
    if config_dir:
        os.makedirs(config_dir, exist_ok=True)
    config = {
        "service_mode": "custom",
        "service_token": "",
        "deepseek_api_key": api_key,
        "balance_yuan": 5.00,
    }
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print("OK")

if __name__ == "__main__":
    main()
