import sys
from pdf_redactor.ui.cli import run_cli
from pdf_redactor.ui.gui import run_gui

def main():
    if len(sys.argv) == 1:
        run_gui()
    else:
        run_cli()

if __name__ == '__main__':
    main()
