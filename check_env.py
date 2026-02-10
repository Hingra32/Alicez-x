
import sys
import os

print("Python Executable:", sys.executable)
print("sys.path:", sys.path)

try:
    import flask
    print("Flask is installed and importable.")
except ImportError:
    print("Flask is NOT installed or importable in this environment.")

# Check if flask is found in pip list
try:
    import subprocess
    pip_list_output = subprocess.check_output([sys.executable, "-m", "pip", "list"], text=True)
    if "Flask" in pip_list_output:
        print("Flask found in pip list for this Python executable.")
    else:
        print("Flask NOT found in pip list for this Python executable.")
except Exception as e:
    print(f"Could not run pip list: {e}")
