from switch_model.utilities import StepTimer

from switch_model.tools.graph.main import graph_scenarios


def add_arguments(parser):
    parser.add_argument("--graph-dir", type=str, default=None,
                        help="Name of the folder where the graphs should be saved")
    parser.add_argument("--overwrite", default=False, action="store_true",
                        help="Don't prompt before overwriting the existing output folder")
    parser.add_argument("--skip-long", default=False, action="store_true",
                        help="Skips plots that take a long time to generate and have specified is_long=True.")
    parser.add_argument("--modules", default=None, nargs='+',
                        help="Modules to load the graphing functions for. "
                             "If not specified reads the modules from modules.txt.")
    parser.add_argument("-f", "--figures", default=None, nargs='+',
                        help="Name of the figures to graph. Figure names are the first argument in the @graph() decorator."
                             " If unspecified graphs all the figures.")
    parser.add_argument("--ignore-modules-txt", default=False, action="store_true",
                        help="When true modules in modules txt are not loaded")


def graph_scenarios_from_cli(scenarios, args):
    if args.ignore_modules_txt:
        if args.modules is None:
            args.modules = []  # Provide an empty list of modules

    timer = StepTimer()
    graph_scenarios(scenarios, graph_dir=args.graph_dir, overwrite=args.overwrite, module_names=args.modules,
                    figures=args.figures, skip_long=args.skip_long)

    # If more than 30 seconds have elapsed, send an audible notification to indicate completion.
    if timer.step_time() > 30:
        print("\a")
