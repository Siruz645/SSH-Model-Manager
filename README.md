# SSH Model Manager for ComfyUI

A cross-platform desktop application built with Python and PyQt6 designed to manage, download, and upload models for remote ComfyUI servers.

## Features

- **🚀 SFTP Uploads (Drag & Drop):** Simply drag and drop any model file from your computer directly into the application window to upload it to your remote server via pipelined SFTP.
- **🔗 Direct Link Downloads:** Paste a download link (from Civitai, HuggingFace, etc.) and the application will instruct the remote server to download it directly.
- **🔑 Token Injection:** Automatically injects your HuggingFace or Civitai API tokens into the requests so you can download private or gated models without entering keys every time.
- **📦 Model Packages:** Group multiple models into custom "Packages". Export these packages to `.json` files (e.g. if you created a workflow, you can attach this json so others can easily download everything needed), or import a package via drag-and-drop to mass-download its contents.
- **⚡ Background Scanning:** The app automatically scans your server's `models` directory every 10 seconds and syncs it with your local catalog, detecting `.safetensors`, `.pt`, and `.bin` files.
- **⏸️ Queue Management:** Download and upload multiple files sequentially. You can pause, resume, and cancel active jobs. Canceling a job automatically cleans up any partial files from the server.
- **🧹 Deletion:** Delete files from the remote server to free up space while keeping the model cataloged in your library for future downloads.
- **📥 Library Cataloging:** Add model files already present on the server to your library (with custom download URLs) for quick future downloads.
- **🌍 Multilingual UI:** Support for 3 languages (English, Russian, Chinese).

## Prerequisites

- Python 3.9+

## Installation & Usage

**For Windows Users (Easiest Method):**
1. Clone the repository or download the ZIP.
2. Double-click `start.bat`.
   *(It will automatically create a virtual environment, install the required dependencies, and launch the app).*

**Manual Installation (Linux/Mac/Advanced):**
1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/SSHModelManager.git
   cd SSHModelManager
   ```

2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the application:
   ```bash
   python main.py
   ```

## Usage Guide

### 1. Connection
In the first tab, you can enter your server's SSH credentials. You can also quickly paste a full SSH command (e.g., `ssh root@192.168.1.10 -p 22`) and the fields will auto-fill. The password field can be left empty; you can also specify the path to your SSH key and enter the key passphrase if required. Don't forget to enter your API tokens if you plan to download restricted models!

### 2. Downloads
Paste URLs here to start remote downloads, or drag and drop files from your desktop to start SFTP uploads. Active tasks can be paused or cancelled at any time.

### 3. Library
View all downloaded or scanned models on your server.
- Check the boxes next to models and click **Create Package** to group them.
- Right-click any package to **Export** it to a `.json` file, or delete it.
- **Drag & Drop** any previously exported `.json` file into the window to instantly import the package and bulk-download all its models.
- **Mass Queueing:** Select entire packages or individual files and click "Add Selected to Queue" to batch download them.

## Technologies Used
- **PyQt6**: For the modern, responsive Graphical User Interface.
- **Paramiko**: For secure SSH connections and pipelined SFTP file transfers.
- **SQLite**: For lightweight, local caching of your model library.

## License

Custom License (see [LICENSE](LICENSE) file).
