#!/bin/bash
set -eu

# Wrapper for GraphicsMagick that makes images with text
# Usage gm_label.sh <size> <text> <filename>
_size="$1"
_text="$2"
_out="$3"

/lustre-gseg/software/graphicsmagick/GraphicsMagick-1.3.35/bin/gm convert -pointsize 20 -background lightblue1 -fill black \
    -font /lustre-gseg/software/graphicsmagick/DejaVuSansMono-BoldOblique.ttf \
    label:"$_text" -background lightblue1 -extent "$_size" "$_out"
