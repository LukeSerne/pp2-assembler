# Assembler for the PP2
# - because Computer Systems doesn't fix their own assembler
#
# Made in 2018 by Luke Serné
import sys
import os

import assembler as asm

def main():
    # check if enough arguments were passed, show help
    if len(sys.argv) == 0:
        showHelp("not enough arguments given\n\n")
        return

    # if -h or --help was passed, show help
    if '-h' in sys.argv or '--help' in sys.argv:
        showHelp("")
        return

    # set verbosity
    #verbose = '-v' in sys.argv
    verbose = True

    # drop all things in sys.argv that start with -, so we only have the input
    # and optionally the output file left.
    iofiles = [arg for arg in sys.argv[1:] if not arg[0].startswith("-")]

    if not iofiles:
        # no input given
        showHelp("no input file given\n\n")
        return

    if len(iofiles) == 1:
        # no output given, so use the name of the input (without extension) and
        # append ".hex"
        name, _ = os.path.splitext(iofiles[0])
        iofiles.append(name + ".hex")

    # create the assembler with the input and output file names
    assembler = asm.Assembler(iofiles[0], iofiles[1], verbose)

    # assemble
    assembler.assemble()

def showHelp(str_):
    """
    Shows the help info for the program
    """
    str_ += "usage: %s [-h | --help] [-v] infile.asm [outfile.hex]\n" % sys.argv[0]
    str_ += "\n"
    str_ += "arguments:\n"
    str_ += "  -h, --help       shows this help message\n"
    str_ += "  -v               verbose: print the decoded output to console\n"
    str_ += "  infile.asm       the input file to assemble\n"
    str_ += "  outfile.hex      optional: the output file\n"
    print(str_)

if __name__ == "__main__":
    main()
