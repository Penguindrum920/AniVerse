"""Download datasets and embeddings from Google Drive on startup"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Google Drive folder ID (extracted from the share link)
GDRIVE_FOLDER_ID = "1tvoY4Ks3elgRgC81uRsZRDhDcclmu5hO"

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

def organize_downloaded_files(download_dir: Path, backend_dir: Path):
    """Move downloaded files to correct locations"""
    print("Organizing downloaded files...")
    
    if not download_dir.exists():
        print(f"Download directory {download_dir} does not exist")
        return False
    
    # List all downloaded items
    for item in download_dir.iterdir():
        print(f"  Found: {item.name}")
        
        # Move CSV files to dataset folder
        if item.suffix == '.csv':
            dataset_dir = backend_dir / "dataset"
            dataset_dir.mkdir(parents=True, exist_ok=True)
            dest = dataset_dir / item.name
            print(f"    Moving to {dest}")
            shutil.move(str(item), str(dest))
        
        # Move chroma_db folder
        elif item.name == 'chroma_db' and item.is_dir():
            dest = backend_dir / "chroma_db"
            if dest.exists():
                shutil.rmtree(dest)
            print(f"    Moving to {dest}")
            shutil.move(str(item), str(dest))
        
        # Move manga_chroma_db folder
        elif item.name == 'manga_chroma_db' and item.is_dir():
            dest = backend_dir / "manga_chroma_db"
            if dest.exists():
                shutil.rmtree(dest)
            print(f"    Moving to {dest}")
            shutil.move(str(item), str(dest))
        
        # Handle nested directories (in case GDrive creates them)
        elif item.is_dir():
            print(f"    Recursively processing subdirectory: {item.name}")
            organize_downloaded_files(item, backend_dir)
    
    return True

def setup_data():
    """Download all required data files"""
    backend_dir = Path(__file__).parent
    
    # Check if data already exists
    dataset_dir = backend_dir / "dataset"
    chroma_dir = backend_dir / "chroma_db"
    
    dataset_exists = (dataset_dir / "anime.csv").exists()
    chroma_exists = chroma_dir.exists() and any(chroma_dir.iterdir()) if chroma_dir.exists() else False
    
    print(f"Dataset exists: {dataset_exists}")
    print(f"ChromaDB exists: {chroma_exists}")
    
    if dataset_exists and chroma_exists:
        print("All data files present, skipping download.")
        return True
    
    # Download from GDrive
    print("=" * 50)
    print("DOWNLOADING DATA FROM GOOGLE DRIVE")
    print("=" * 50)
    
    download_dir = backend_dir / "data_download"
    success = download_folder_from_gdrive(GDRIVE_FOLDER_ID, str(download_dir))
    
    if success:
        organize_downloaded_files(download_dir, backend_dir)
        
        # Cleanup download folder
        if download_dir.exists():
            shutil.rmtree(download_dir)
            print("Cleaned up download folder")
    else:
        print("WARNING: Failed to download data from GDrive!")
        print("The server may not function correctly without data files.")
    
    return success

if __name__ == "__main__":
    setup_data()
