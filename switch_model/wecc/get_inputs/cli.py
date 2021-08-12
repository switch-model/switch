""" Script to retrieve the input data from the switch-wecc database and apply post-processing steps.
"""
import argparse
import importlib
import os

from switch_model.utilities import query_yes_no, StepTimer
from switch_model.wecc.get_inputs.get_inputs import query_db
from switch_model.wecc.utilities import load_config
# from switch_model.wecc.get_inputs.post_process_steps import *
# from switch_model.wecc.get_inputs.register_post_process import run_post_process, _registered_steps


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
    parser.add_argument("--skip-cf", default=False, action='store_true',
                        help="Skip creation variable_capacity_factors.csv. Useful when debugging and one doesn't"
                             "want to wait for the command.")
    parser.add_argument("--post-process", default=False, action='store_true', help="Run only post process steps.")
    parser.add_argument("--post-process-step", default=None, help="Run only this post process step.")
    parser.add_argument("--overwrite", default=False, action='store_true',
                        help="Overwrite previous input files without prompting to confirm.")
    args = parser.parse_args()  # Makes switch get_inputs --help works

    # Load values from config.yaml
    full_config = load_config()
    switch_to_input_dir(full_config, overwrite=args.overwrite)

    if args.post_process is None:
        query_db(full_config, skip_cf=args.skip_cf)

    print("Post-processing...")

    post_process_path = '.'.join(__name__.split('.')[:-1]) + ".post_process_steps"

    def run_post_process(module):
        mod = importlib.import_module(f".{module}", post_process_path)
        post_process = getattr(mod, "post_process")

        # Configuration specific for the post_process
        post_config = full_config.get(module, None)

        # Run post process
        post_process(full_config, post_config)

    # Get additional post-process from the config file
    if args.post_process_step is None:
        for module in full_config["post_process"]:
            run_post_process(module)
        # run_post_process(full_config, step_name=args.post_process)
    else:
        run_post_process(getattr(args, "post_process_step"))
        # breakpoint()
            # post_process_path = '.'.join(__name__.split('.')[:-1]) + ".post_process_steps"
            # mod = importlib.import_module(f".{module}", post_process_path)
            # post_process = getattr(mod, "post_process")

            # # Configuration specific for the post_process 
            # post_config = full_config.get(module, None)

            # # Run post process
            # post_process(full_config, post_config)

    print(f"\nScript took {timer.step_time_as_str()} seconds to build input tables.")


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
