"""Privately configure a server-side OpenAI key for the local Streamlit demo."""
import getpass
import os
import tempfile
from pathlib import Path

import toml


def save_key(key, path=Path('.streamlit/secrets.toml')):
    if not isinstance(key, str) or not key.strip():
        raise ValueError('An API key is required.')
    path = Path(path)
    settings = toml.loads(path.read_text()) if path.exists() else {}
    settings['OPENAI_API_KEY'] = key.strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            os.chmod(temporary, 0o600)
            file.write(toml.dumps(settings))
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    # Enforce the documented location where Git excludes the secrets file.
    if not Path('streamlit_app.py').is_file():
        raise SystemExit('Run this command from the repository root.')
    key = getpass.getpass('Paste your OpenAI API key (input hidden): ')
    try:
        save_key(key)
    except (ValueError, OSError):
        raise SystemExit('Could not save the key. Check the local secrets file and directory permissions.')
    print('OpenAI key configured for the local Streamlit demo. Restart Streamlit to load it.')


if __name__ == '__main__':
    main()
