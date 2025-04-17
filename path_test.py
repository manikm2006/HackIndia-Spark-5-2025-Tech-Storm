import os

pdf_path = "CSE 1st Year Section Wise.pdf"  # Simplest possible path
print("Trying to open:", pdf_path)
try:
    with open(pdf_path, "r") as f:  # Try to open in text mode (will fail, but tests path)
        print("File exists!")
except FileNotFoundError:
    print("File NOT found!")
print("Current working directory:", os.getcwd())
print("Script's directory:", os.path.dirname(os.path.abspath(__file__)))
