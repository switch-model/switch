# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""
Save a complete text dump of the model and solution, suitable
for development, debugging or using diff tools to compare two runs. 
I do not recommend using this with large datasets or in a production
environment.

"""
import os, sys

def save_results(model, instance, outdir):
    """
    Dump the model & solution using instance.pprint()

    """
    stdout_copy = sys.stdout  # make a copy of current sys.stdout to return to eventually
    out_path = os.path.join(outdir, "model_dump_concise.txt")
    out_file = open(out_path, "w", buffering=1)
    sys.stdout = out_file
    instance.display()
    sys.stdout = stdout_copy
