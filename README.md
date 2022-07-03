# Introduction
Simulate the rolldown in a game of TFT.

# Setup
Install the necessary python libraries:
```
python -m pip install -r requirements.txt
```
If you do not have Windows 11, use the Windows Command Prompt (no additional setup needed).


If you're using WSL or Linux, follow the instructions below. Windows 11 is required for WSL.
Install the necessary apt packages:
```
./packages.sh
```

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
