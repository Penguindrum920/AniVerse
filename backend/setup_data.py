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
        import traceback
        traceback.print_exc()
        return False

def organize_downloaded_files(download_dir: Path, backend_dir: Path):
    """Move downloaded files to correct locations"""
    print(f"\n{'='*50}")
    print("ORGANIZING DOWNLOADED FILES")
    print(f"{'='*50}")
    print(f"Source: {download_dir}")
    print(f"Destination: {backend_dir}")
    
    if not download_dir.exists():
        print(f"ERROR: Download directory {download_dir} does not exist!")
        return False
    
    # List all downloaded items
    items = list(download_dir.iterdir())
    print(f"Found {len(items)} items in download folder:")
    
    for item in items:
        print(f"\n  Processing: {item.name} (is_dir={item.is_dir()})")
        
        try:
            # Move CSV files to dataset folder
            if item.suffix.lower() == '.csv':
                dataset_dir = backend_dir / "dataset"
                dataset_dir.mkdir(parents=True, exist_ok=True)
                dest = dataset_dir / item.name
                print(f"    Moving CSV to {dest}")
                shutil.move(str(item), str(dest))
                print(f"    ✓ Moved successfully")
            
            # Move chroma_db folder
            elif item.name == 'chroma_db' and item.is_dir():
                dest = backend_dir / "chroma_db"
                if dest.exists():
                    print(f"    Removing existing {dest}")
                    shutil.rmtree(dest)
                print(f"    Moving chroma_db to {dest}")
                shutil.move(str(item), str(dest))
                print(f"    ✓ Moved successfully")
            
            # Move manga_chroma_db folder
            elif item.name == 'manga_chroma_db' and item.is_dir():
                dest = backend_dir / "manga_chroma_db"
                if dest.exists():
                    print(f"    Removing existing {dest}")
                    shutil.rmtree(dest)
                print(f"    Moving manga_chroma_db to {dest}")
                shutil.move(str(item), str(dest))
                print(f"    ✓ Moved successfully")
            
            # Handle nested directories (GDrive sometimes creates nested folders)
            elif item.is_dir():
                print(f"    Recursively processing subdirectory: {item.name}")
                organize_downloaded_files(item, backend_dir)
        except Exception as e:
            print(f"    ERROR moving {item.name}: {e}")
            import traceback
            traceback.print_exc()
    
    return True

def verify_data(backend_dir: Path):
    """Verify all required data files exist"""
    print(f"\n{'='*50}")
    print("VERIFYING DATA FILES")
    print(f"{'='*50}")
    
    dataset_path = backend_dir / "dataset" / "anime.csv"
    chroma_path = backend_dir / "chroma_db"
    manga_chroma_path = backend_dir / "manga_chroma_db"
    
    print(f"Dataset (anime.csv): {dataset_path.exists()} - {dataset_path}")
    print(f"ChromaDB: {chroma_path.exists()} - {chroma_path}")
    print(f"Manga ChromaDB: {manga_chroma_path.exists()} - {manga_chroma_path}")
    
    if chroma_path.exists():
        print(f"  ChromaDB contents: {list(chroma_path.iterdir())}")
    if manga_chroma_path.exists():
        print(f"  Manga ChromaDB contents: {list(manga_chroma_path.iterdir())}")
    
    return dataset_path.exists() and chroma_path.exists()

def setup_data():
    """Download all required data files"""
    backend_dir = Path(__file__).parent
    
    print(f"\n{'='*50}")
    print("ANIVERSE DATA SETUP")
    print(f"{'='*50}")
    print(f"Backend directory: {backend_dir}")
    
    # Check if data already exists
    dataset_dir = backend_dir / "dataset"
    chroma_dir = backend_dir / "chroma_db"
    
    dataset_exists = (dataset_dir / "anime.csv").exists()
    chroma_exists = chroma_dir.exists() and any(chroma_dir.iterdir()) if chroma_dir.exists() else False
    
    print(f"Dataset exists: {dataset_exists}")
    print(f"ChromaDB exists: {chroma_exists}")
    
    if dataset_exists and chroma_exists:
        print("All data files present, skipping download.")
        verify_data(backend_dir)
        return True
    
    # Download from GDrive
    print(f"\n{'='*50}")
    print("DOWNLOADING DATA FROM GOOGLE DRIVE")
    print(f"{'='*50}")
    
    download_dir = backend_dir / "data_download"
    success = download_folder_from_gdrive(GDRIVE_FOLDER_ID, str(download_dir))
    
    if success:
        organize_downloaded_files(download_dir, backend_dir)
        
        # Cleanup download folder
        if download_dir.exists():
            print(f"\nCleaning up download folder: {download_dir}")
            try:
                shutil.rmtree(download_dir)
                print("✓ Cleanup complete")
            except Exception as e:
                print(f"Warning: Could not cleanup: {e}")
        
        # Verify the data
        verify_data(backend_dir)
    else:
        print("\n" + "!"*50)
        print("WARNING: Failed to download data from GDrive!")
        print("The server may not function correctly without data files.")
        print("!"*50)
    
    return success

if __name__ == "__main__":
    setup_data()
