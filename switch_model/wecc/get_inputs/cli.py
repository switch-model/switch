""" Script to retrieve the input data from the switch-wecc database and apply post-processing steps.
"""
import argparse
import importlib
import os

from switch_model.utilities import query_yes_no, StepTimer
from switch_model.wecc.get_inputs.get_inputs import query_db
from switch_model.wecc.utilities import load_config

def main():
    timer = StepTimer()

    # Create command line tool, just provides help information
    parser = argparse.ArgumentParser(
        description="Write SWITCH input files from database tables.",
        epilog="""
        This tool will populate the inputs folder with the data from the PostgreSQL database.
        config.yaml specifies the scenario parameters.
        The environment variable DB_URL specifies the url to connect to the database. """,
    )
    parser.add_argument(
        "--skip-cf",
        default=False,
        action="store_true",
        help="Skip creation variable_capacity_factors.csv. Useful when debugging and one doesn't"
        "want to wait for the command.",
    )
    parser.add_argument(
        "--post-process-only",
        default=False,
        action="store_true",
        help="Run only post process steps.",
    )
    parser.add_argument(
        "--post-process-step", default=None, help="Run only this post process step."
    )
    parser.add_argument(
        "--overwrite",
        default=False,
        action="store_true",
        help="Overwrite previous input files without prompting to confirm.",
    )
    args = parser.parse_args()  # Makes switch get_inputs --help works

    # Load values from config.yaml
    full_config = load_config()
    switch_to_input_dir(full_config, overwrite=args.overwrite)

    if not args.post_process_only and args.post_process_step is None:
        query_db(full_config, skip_cf=args.skip_cf)

    print("\nRunning post processing...")

    # Get location of post process scripts
    post_process_path = ".".join(__name__.split(".")[:-1]) + ".post_process_steps"

    def run_post_process(module):
        """ Run a function from a given module """

        # This uses python module syntax with a dot. Example: import foo.bar.test
        mod = importlib.import_module(f".{module}", post_process_path)

        post_process = getattr(mod, "post_process")

        # Get specific configuration for the post process if specified
        post_config = None
        if "post_process_config" in full_config and full_config["post_process_config"] is not None:
            post_config = full_config["post_process_config"].get(module, None)

        # Run post process
        post_process(post_config)

    # Run all post process specified, otherwise run single one
    if args.post_process_step is None:
        for module in full_config["post_process_steps"]:
            run_post_process(module)
    else:
        run_post_process(getattr(args, "post_process_step"))

    print(f"\nScript took {timer.step_time_as_str()} seconds.")


def switch_to_input_dir(config, overwrite):
    inputs_dir = config["inputs_dir"]

    # Create inputs_dir if it doesn't exist
    if not os.path.exists(inputs_dir):
        os.makedirs(inputs_dir)
        print("Inputs directory created.")
    else:
        if not overwrite and not query_yes_no(
            "Inputs directory already exists. Allow contents to be overwritten?"
        ):
            raise SystemExit("User cancelled run.")

    os.chdir(inputs_dir)
    return inputs_dir


if __name__ == "__main__":
    main()
