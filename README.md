# Blnq - PDF Redaction & Anonymization Tool

Blnq is a production-grade, heavily optimized desktop application for securely redacting sensitive information from both Digital and Scanned PDFs. 
Refactored and hardened for deep metadata scrubbing, multi-line phrase reconstruction, multithreaded OCR scanning, forensic audit logging, and complete standalone offline deployment.

## Installation

### Method 1: Download Installer (Recommended for Users)
The easiest way to install Blnq is by downloading the pre-compiled Windows installer.
1. Go to the [Releases](../../releases) page on GitHub.
2. Download the latest `BlnqInstaller.exe`.
3. Run the installer and follow the setup wizard to install Blnq with Desktop and Start Menu shortcuts.

### Method 2: Build from Source (For Developers)

#### Prerequisites
1. Python 3.9+
2. Clone this repository to your local machine:
    ```bash
    git clone https://github.com/whelve13/PDFRedact.git
    cd PDFRedact
    ```
3. Set up a virtual environment and install dependencies:
    ```bash
    python -m venv venv
    .\venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    ```

#### Running the Source Code
You can run the application GUI directly. Portable Tesseract-OCR binaries and dictionaries (eng, ron, rus) are natively bundled.
```bash
python src/main.py
```

#### Compiling the Standalone Executable
We utilize `PyInstaller` combined with a custom spec tree to automatically bake the application icon and offline Tesseract binaries directly into the executable space, requiring zero setup by the end-user.

1. Install PyInstaller:
    ```bash
    pip install pyinstaller
    ```
2. Run the build command targeting the pre-configured Spec file:
    ```bash
    pyinstaller Blnq.spec --noconfirm
    ```
3. Your portable, completely standalone `Blnq.exe` will be generated inside the `dist/` folder!
4. (Optional) Run the `installer/BlnqInstaller.iss` script using Inno Setup 6 to generate the Windows Setup Wizard `BlnqInstaller.exe`.

## Core Features
1. **Interactive Workspace**: Drag-and-drop PDF ingestion.
2. **Hybrid Phrase Detection**: Accurately maps regular expressions across line-breaks natively via PyMuPDF.
3. **Multithreaded OCR (OpenCV Pipeline)**: Bypasses the GIL by parallel-processing Tesseract over multiple CPU cores, pre-processing dark/noisy scans using Otsu's binarization thresholding and Gaussian Denoising.
4. **True Redaction**: Securely destroys underlying image pixels (`fitz.PDF_REDACT_IMAGE_PIXELS`) and scrubs leakable PDF metadata.
5. **Audit Logistics**: Optionally exports forensic-grade `.csv` logs tracking the exact timestamps, files, strings, and methodologies behind every executed redaction.
