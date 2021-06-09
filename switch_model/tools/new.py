"""
Script that prepares a folder to be used by switch.

This script:
- Creates a template config.yaml file in the repository.
"""
import shutil
import os
from switch_model.utilities import query_yes_no


def create_config():
    dest = os.path.join(os.getcwd(), "config.yaml")

    if os.path.exists(dest) and not query_yes_no("config.yaml already exists. Do you want to reset it?"):
        return

    shutil.copyfile(
        os.path.join(os.path.dirname(__file__), "config.template.yaml"),
        dest
    )
    print("IMPORTANT: Edit config.yaml to specify your options.")


def main():
    create_config()

