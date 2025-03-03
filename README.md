# Korean localization for Aotenjo

Korean localization for [Aotenjo: Infinite Hands](https://store.steampowered.com/app/3066570/Aotenjo_Infinite_Hands/)

Patch themselves are in Releases section. The repo holds the dev environment.

## Requirement

* Python >= 3.7
* Powershell
* Unity Editor 2022.3.34f1
* [nesrak1's AddressablesTools](https://github.com/nesrak1/AddressablesTools/releases)

## Usage

* Setting up:

```powershell
./setup-dev.ps1
```

Dependencies for `x.py` are installed in `.venv`. Use `.venv/Scripts/activate` / `deactivate` to activate / deactivate virtual environment.

* Extracting localization asset:

```powershell
python x.py extract -v GAME_VERSION [--dir GAME_PATH]
```

* Generation of font charset:

```powershell
python x.py make-charset -v GAME_VERSION
```

* Generation of zip:

```powershell
python x.py make-zip -v GAME_VERSION -a PATH_TO_EXAMPLE_EXE [--dir GAME_PATH]
```

Check `x.py`'s `--help` for details.

## Current limitations

* Font asset needs to be generated manually from Unity Editor before `make-zip`.
