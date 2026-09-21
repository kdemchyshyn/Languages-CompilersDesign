import sys

def CompileError(message):
    print("compilation error: " + message, file=sys.stderr)
    sys.exit(1)