# ETS2 Mac Texture Tools

This repository contains two Python scripts I made while trying to get an older Euro Truck Simulator 2 graphics mod working properly on my Apple Silicon Mac through CrossOver.

The main problems I ran into were broken or corrupted DDS textures and sky textures showing incorrect colors. I ended up using two separate scripts because these problems needed different fixes.

## fix.py

`fix.py` is the general texture conversion script.

It scans the mod folder for DDS files and first tries to read them with ImageMagick. If ImageMagick cannot read a file, the script tries the built-in macOS `sips` tool as a fallback.

It also checks the dimensions of each texture. If the width or height is not a multiple of four, the script adjusts the dimensions before writing the texture back as a DXT5 DDS file.

I made this because manually checking and converting a large number of texture files was not practical.

## rbgwfix.py

`rbgwfix.py` was made later for a separate problem with the RBGW sky textures.

Some of the sky textures were displaying with incorrect colors. During testing, I found that swapping the red and blue channels corrected the affected textures.

I did not apply this correction to every texture. I checked the affected files individually and marked the ones that actually needed the fix. The final list contains 68 specific RBGW texture files.

Because of this, `rbgwfix.py` is specific to the RBGW files I tested. It is not a general tool for automatically detecting broken sky textures.

## Requirements

The scripts were made and tested on macOS.

You will need Python 3 and ImageMagick.

`fix.py` also uses the built-in macOS `sips` command as a fallback for some DDS files.

To check whether ImageMagick is installed, run:

`magick -version`

## Usage

To check what `fix.py` would process without changing any files:

`python3 fix.py "/path/to/mod" --dry-run`

To process the textures and keep backup copies:

`python3 fix.py "/path/to/mod" --backup-dir "/path/to/backup"`

To check which of the RBGW target files are present:

`python3 rbgwfix.py "/path/to/mod" --dry-run`

To run the RBGW sky correction with backups:

`python3 rbgwfix.py "/path/to/mod" --backup-dir "/path/to/backup"`

## How this project developed

I started with the general DDS conversion script while troubleshooting texture problems in the mod.

After testing the converted files in game, I still had a separate problem with the sky colors. I tried different ways of narrowing down which textures were responsible, then checked the files individually and ended up with 68 specific RBGW textures that needed their red and blue channels swapped.

The current `rbgwfix.py` uses that manually checked list instead of modifying the entire mod.

Most of the work involved changing the scripts, running them on the mod files, launching ETS2, checking the results in game, and gradually narrowing down which files were actually causing the problems.

## Notes

These scripts were made for the specific problems I encountered and should not be treated as universal ETS2 mod repair tools.

Both scripts can overwrite DDS files, so keeping backups is recommended.

I used AI tools for help with parts of the Python code, ImageMagick commands, and debugging. I handled the in-game testing, file checking, problem isolation, and verification of which textures needed to be changed.
