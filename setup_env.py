#!/usr/bin/env python3
"""
Environment Bootstrapper

This script creates (if needed) and initializes a Python virtual environment in './.venv',
and installs/updates all required dependencies for the Compose Manager CLI.
"""
import os
import sys
import subprocess

VENV_DIR = ".venv"
REQUIREMENTS = [
    "click",            # CLI framework
    "ruamel.yaml",      # YAML round-trip editing
    "rich",             # Rich console output
    "questionary",      # Interactive prompts
    "pyyaml"            # safe_yaml for config file
]

def run(cmd, **kwargs):
    return subprocess.check_call(cmd, shell=False, **kwargs)

def create_virtualenv():
    if not os.path.isdir(VENV_DIR):
        print(f"Creating virtual environment in '{VENV_DIR}'...")
        run([sys.executable, "-m", "venv", VENV_DIR])
    else:
        print(f"Virtual environment '{VENV_DIR}' already exists.")

def get_executable(name):
    """Return the path to an executable within the venv."""
    if os.name == 'nt':
        return os.path.join(VENV_DIR, 'Scripts', name + ('.exe' if not name.endswith('.exe') else ''))
    else:
        return os.path.join(VENV_DIR, 'bin', name)

def install_requirements():
    pip = get_executable('pip')
    python = get_executable('python')
    print("Upgrading pip...")
    run([pip, 'install', '--upgrade', 'pip'])
    print("Installing/updating required packages...")
    run([pip, 'install'] + REQUIREMENTS)

def main():
    create_virtualenv()
    install_requirements()
    print("\nBootstrap complete!\nTo activate the virtual environment, run:")
    if os.name == 'nt':
        print(f"    {VENV_DIR}\\Scripts\\activate.bat")
    else:
        print(f"    source {VENV_DIR}/bin/activate")

if __name__ == '__main__':
    main()
