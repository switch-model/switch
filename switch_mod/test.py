import sys

def main():
    print "running {} as {}.".format(__file__, __name__)
    print "system path:"
    print "\n".join(sys.path)

if __name__ == "__main__":
    main()

