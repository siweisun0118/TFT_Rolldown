# Introduction
Simulate the rolldown in a game of TFT

# Setup
Install the necessary python libraries:
```
python -m pip install -r requirements.txt
```
For the UI portion for Linux, also install the necessary apt packages:
```
./packages.sh
```
If you're using WSL, you might need Windows 11.
If you're using Command Prompt on Windows, you do not need to run `./packages.sh` or Windows 11.

# Usage
For the terminal-only rolldown simulator, use the following command:
```
python rolldown.py {input_directory}
```

For the work-in-progress UI, run the following command:
```
python user_interface.py {input_directory}
```

The input directory should have the following tree structure:
```
TFT_Set_6/
├── champions
├── champions.json
├── items
├── items.json
├── traits
└── traits.json
```
See ./TFT_Set_6/ for an example.
