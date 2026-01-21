"""Download datasets and embeddings from Google Drive on startup"""
import os
import subprocess
import sys
from pathlib import Path

# Google Drive folder ID (extracted from the share link)
GDRIVE_FOLDER_ID = "1tvoY4Ks3elgRgC81uRsZRDhDcclmu5hO"

# Files to download with their GDrive file IDs
# You'll need to get individual file IDs from GDrive
GDRIVE_FILES = {
    # Format: "local_path": "gdrive_file_id"
    # These will be filled in once you share the individual files
}

def install_gdown():
    """Install gdown if not present"""
    try:
        import gdown
    except ImportError:
        print("Installing gdown...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "gdown", "-q"])
        import gdown
    return gdown

def download_folder_from_gdrive(folder_id: str, output_dir: str):
    """Download entire folder from GDrive"""
    gdown = install_gdown()
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    print(f"Downloading from GDrive folder {folder_id} to {output_dir}...")
    
    try:
        url = f"https://drive.google.com/drive/folders/{folder_id}"
        gdown.download_folder(url, output=output_dir, quiet=False, remaining_ok=True)
        print(f"Download complete: {output_dir}")
        return True
    except Exception as e:
        print(f"Error downloading: {e}")
        return False

def setup_data():
    """Download all required data files"""
    backend_dir = Path(__file__).parent
    
    # Check if data already exists
    dataset_dir = backend_dir / "dataset"
    chroma_dir = backend_dir / "chroma_db"
    manga_chroma_dir = backend_dir / "manga_chroma_db"
    
    needs_download = False
    
    if not (dataset_dir / "anime.csv").exists():
        print("Dataset not found, will download...")
        needs_download = True
    
    if not chroma_dir.exists() or not any(chroma_dir.iterdir()):
        print("ChromaDB embeddings not found, will download...")
        needs_download = True
        
    if not needs_download:
        print("All data files present, skipping download.")
        return True
    
    # Download from GDrive
    print("=" * 50)
    print("DOWNLOADING DATA FROM GOOGLE DRIVE")
    print("=" * 50)
    
    success = download_folder_from_gdrive(GDRIVE_FOLDER_ID, str(backend_dir / "data_download"))
    
    if success:
        # Move files to correct locations
        download_dir = backend_dir / "data_download"
        
        # Check what was downloaded and move to correct places
        print("Organizing downloaded files...")
        
        # You may need to adjust these paths based on how files are structured in GDrive
        for item in download_dir.iterdir():
            print(f"  Found: {item.name}")
    
    return success

if __name__ == "__main__":
    setup_data()
