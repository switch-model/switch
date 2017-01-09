# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.
import sys

def main():
    print "running {} as {}.".format(__file__, __name__)
    print "system path:"
    print "\n".join(sys.path)

if __name__ == "__main__":
    main()

