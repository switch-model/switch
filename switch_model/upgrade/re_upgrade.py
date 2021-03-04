from __future__ import print_function

import os
from switch_model.upgrade.manager import upgrade_plugins

upgrade_module, upgrade_from, upgrade_to = upgrade_plugins[-1]

if __name__ == "__main__":
    print(
        "Re-running upgrade from {} to {} for all subdirectories of current directory".format(
            upgrade_from, upgrade_to
        )
    )

    for dirpath, dirnames, filenames in os.walk("."):
        if "switch_inputs_version.txt" in filenames:
            print("upgrading {}".format(dirpath))
            upgrade_module.upgrade_input_dir(dirpath)
