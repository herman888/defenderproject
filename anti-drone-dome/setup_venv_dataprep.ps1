# setup_venv_dataprep.ps1
# Creates a throw-away Python venv just for fetch_public_datasets.py.
# Roboflow always installs opencv-python-headless, which breaks cv2.imshow
# in the main venv. This venv is isolated so the main env stays clean.
# Downloaded datasets land in data/public/ and are read by the main venv.

$VenvDir = "venv-dataprep"

if (Test-Path $VenvDir) {
    Write-Host "venv-dataprep already exists — skipping creation."
} else {
    Write-Host "Creating $VenvDir ..."
    python -m venv $VenvDir
}

Write-Host "Installing dependencies ..."
& "$VenvDir\Scripts\python.exe" -m pip install --quiet --upgrade pip
& "$VenvDir\Scripts\pip.exe" install roboflow pyyaml requests

Write-Host ""
Write-Host "Done. To use it:"
Write-Host "  $VenvDir\Scripts\Activate.ps1"
Write-Host "  `$env:ROBOFLOW_API_KEY = `"your_key_here`""
Write-Host "  python scripts\fetch_public_datasets.py"
Write-Host ""
Write-Host "When finished, deactivate with: deactivate"
