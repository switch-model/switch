"""
Script that prepares a folder to be used by switch.

This script:
- Creates a template config.yaml file in the repository.
"""
import shutil
import os


def create_config():
    shutil.copyfile(
        os.path.join(os.path.dirname(__file__), "config.template.yaml"),
        os.path.join(os.getcwd(), "config.yaml")
    )
    print("IMPORTANT: Edit config.yaml to specify your options.")


def main():
    create_config()

