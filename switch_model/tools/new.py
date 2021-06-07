"""
Script that prepares a folder to be used by switch.

This script:
- Creates a template config.yaml file in the repository.
"""
import shutil
import os
import argparse
from switch_model.utilities import query_yes_no


def copy_template_to_workdir(template_name):
    dest = os.path.join(os.getcwd(), template_name)

    if os.path.exists(dest) and not query_yes_no(f"{template_name} already exists. Do you want to reset it?"):
        return

    shutil.copyfile(
        os.path.join(os.path.dirname(__file__), f"templates/{template_name}"),
        dest
    )


def create_run_config():
    copy_template_to_workdir("config.yaml")
    print("IMPORTANT: Edit config.yaml to specify your options.")


def create_sampling_config():
    copy_template_to_workdir("sampling.yaml")
    print("IMPORTANT: Edit sampling.yaml to specify your options.")


def main():
    parser = argparse.ArgumentParser(description="Tool to setup either a new scenario folder or a new sampling config.")
    parser.add_argument(
        "type",
        choices=["scenario", "sampling_config"],
        help="Pick between setting up a new scenario folder or a sampling strategy."
    )
    args = parser.parse_args()
    if args.type == "scenario":
        create_run_config()
    elif args.type == "sampling_config":
        create_sampling_config()
