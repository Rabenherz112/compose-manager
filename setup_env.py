#!/usr/bin/env python3
"""
Environment Bootstrapper

This script creates (if needed) and initializes a Python virtual environment in './.venv',
and installs/updates all required dependencies for the Compose Manager CLI.
"""
import os
import sys
import subprocess
import argparse

VENV_DIR = ".venv"
REQUIREMENTS = [
    "click",            # CLI framework
    "ruamel.yaml",      # YAML round-trip editing
    "rich",             # Rich console output
    "questionary",      # Interactive prompts
    "pyyaml",           # safe_yaml for config file
    "requests"          # HTTP requests
]

def run(cmd, **kwargs):
    return subprocess.check_call(cmd, shell=False, **kwargs)

def create_virtualenv(quiet=False):
    """Create a virtual environment if it doesn't exist."""
    if not os.path.isdir(VENV_DIR):
        if not quiet:
            print(f"Creating virtual environment in '{VENV_DIR}'...")
        run([sys.executable, "-m", "venv", VENV_DIR])
    else:
        if not quiet:
            print(f"Virtual environment '{VENV_DIR}' already exists.")

def get_executable(name):
    """Return the path to an executable within the venv."""
    if os.name == 'nt':
        return os.path.join(VENV_DIR, 'Scripts', name + ('.exe' if not name.endswith('.exe') else ''))
    else:
        return os.path.join(VENV_DIR, 'bin', name)

def install_requirements(quiet=False):
    """Install or update the required packages in the virtual environment."""
    pip = get_executable('pip')
    python = get_executable('python')
    if not quiet:
        print("Upgrading pip...")
        run([pip, 'install', '--upgrade', 'pip'])
        print("Installing/updating required packages...")
        run([pip, 'install'] + REQUIREMENTS)
    else:
        run([pip, 'install', '--upgrade', 'pip'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        run([pip, 'install'] + REQUIREMENTS, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('-q', '--quiet', action='store_true', help="Suppress most output")
    args = p.parse_args()
    quiet = args.quiet
    create_virtualenv(quiet=quiet)
    install_requirements(quiet=quiet)
    print("Bootstrap complete!")
    if not quiet:
        print("To activate the virtual environment, run:")
        if os.name == 'nt':
            print(f"    {VENV_DIR}\\Scripts\\activate.bat")
        else:
            print(f"    source {VENV_DIR}/bin/activate")

if __name__ == '__main__':
    main()
