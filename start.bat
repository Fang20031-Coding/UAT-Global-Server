@echo off
setlocal

git pull

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

python main.py