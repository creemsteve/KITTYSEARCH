$ErrorActionPreference = 'Stop'
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean --onefile --name KittySearch --console kittysearch.py
Write-Host "Portable executable created at dist\KittySearch.exe"
